"""Session 23c acceptance: the 20-row NE@SEA Showdown spread across Ben's theses (chunk P8, "Done looks like").

The supplied NE@SEA fixture (`tests/fixtures/supplied/`) carries no priors, so, as in the Session 23 acceptance,
this proves the mechanism over the real salary bytes with a salary-shaped objective: the policy is written by
`scripts/make_showdown_policy.py` (repeatable `--thesis`), validated, banked, solved jointly and audited from the
final roster IDs. It is a mechanism check, never a pre-lock claim. The ATL@GB (2026-09-24) bytes are not in the
repository (the changelog records only their hashes), so that replay is not run and not invented.

The theses are written here from Ben's R33 list and the brief's table by structure alone (a team's best players by
salary at a position, never a model value, a spread or a total): a team wins big, a team wins close (high and low
scoring), a defensive battle, a shootout. A thesis is a choice, not a forecast, and with no ownership input leverage
is unmeasured.
"""

from __future__ import annotations

import importlib.util
import json
from collections import Counter
from itertools import combinations
from pathlib import Path

import pytest

from nfl_dfs.dk import parse_entries, parse_salaries
from nfl_dfs.entry_groups import plan_entries
from nfl_dfs.hashing import sha256_bytes
from nfl_dfs.portfolio_enforcement import (
    audit_policy_assignments,
    build_policy_candidate_bank,
    probe_thesis_rows,
    scaled_candidate_limit,
    scaled_candidate_seconds,
    scaled_selection_seconds,
    solve_policy_portfolio,
)
from nfl_dfs.portfolio_policy import thesis_roster_violations, validate_portfolio_policy_bytes
from nfl_dfs.showdown_theses import thesis_portfolio_measures

REPO_ROOT = Path(__file__).resolve().parents[1]
SUPPLIED = REPO_ROOT / "tests" / "fixtures" / "supplied"
SALARIES = SUPPLIED / "DKSalaries Salary CSV Showdown.csv"
ENTRIES = SUPPLIED / "DKEntries CSV 20 entries.csv"
GENERATOR = REPO_ROOT / "scripts" / "make_showdown_policy.py"
ENTRY_COUNT = 20
# The policy the generator writes by default is the registered concentration defaults: 0.60 a person, 0.20 a Captain.
PERSON_LIMIT = 12
CAPTAIN_LIMIT = 4
# The generator writes the salary band open when a thesis is supplied (`--salary-left-*` given is the operator's), so the
# acceptance runs on the generator's own default. `OPEN_BAND` gives the no-thesis comparison the same open band, and
# `DEFAULT_BAND` is the $1 to $500 hygiene default that the cheap theses cannot meet (the band test shows why).
OPEN_BAND = ("--salary-left-min", "0", "--salary-left-max", "50000")
DEFAULT_BAND = ("--salary-left-min", "1", "--salary-left-max", "500")


def _generator():
    spec = importlib.util.spec_from_file_location("make_showdown_policy_thesis_acceptance", GENERATOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _top(slate, team, position, count):
    rows = sorted((row for row in slate.players
                   if row.team == team and row.position == position and row.role == "FLEX"
                   and row.status_raw not in {"OUT", "IR"}),
                  key=lambda row: (-row.salary, row.dk_id))
    return [row.underlying_id for row in rows[:count]]


def r33_theses(slate, *, variants: bool) -> list[dict]:
    """Ben's R33 list as structure. `variants` adds the close game's high and low scoring sub-variants for each team."""

    one, two = sorted({row.team for row in slate.players})

    def wins_big(team):
        return {"name": f"{team}_WINS_BIG", "teams": [team],
                "captain_set": [*_top(slate, team, "QB", 1), *_top(slate, team, "RB", 2), *_top(slate, team, "WR", 2),
                                *_top(slate, team, "DST", 1)],
                "team_bounds": [{"team": team, "minimum": 4, "maximum": 5}]}

    def close(team, other, *, high):
        if high:
            return {"name": f"{team}_WINS_CLOSE_HIGH", "teams": [team, other],
                    "captain_set": [*_top(slate, team, "QB", 1), *_top(slate, other, "QB", 1), *_top(slate, team, "WR", 2)],
                    "team_bounds": [{"team": team, "minimum": 3, "maximum": 4}],
                    "position_bounds": [{"position": "QB", "minimum": 1, "maximum": 2}]}
        return {"name": f"{team}_WINS_CLOSE_LOW" if variants else f"{team}_WINS_CLOSE", "teams": [team, other],
                "captain_set": [*_top(slate, team, "K", 1), *_top(slate, team, "DST", 1)],
                "team_bounds": [{"team": team, "minimum": 3, "maximum": 4}],
                "position_bounds": [{"position": "K", "minimum": 1, "maximum": 1},
                                    {"position": "DST", "minimum": 1, "maximum": 1},
                                    {"position": "WR", "minimum": 0, "maximum": 1}]}

    defensive = {"name": "DEFENSIVE_BATTLE", "teams": [one, two],
                 "captain_set": [*_top(slate, one, "K", 1), *_top(slate, two, "K", 1),
                                 *_top(slate, one, "DST", 1), *_top(slate, two, "DST", 1)],
                 "position_bounds": [{"position": "K", "minimum": 2, "maximum": 2},
                                     {"position": "DST", "minimum": 1, "maximum": 1},
                                     {"position": "QB", "minimum": 0, "maximum": 1},
                                     {"position": "WR", "minimum": 0, "maximum": 1}]}
    shootout = {"name": "OFFENSIVE_SHOOTOUT", "teams": [one, two],
                "captain_set": [*_top(slate, one, "QB", 1), *_top(slate, two, "QB", 1),
                                *_top(slate, one, "WR", 2), *_top(slate, two, "WR", 2)],
                "position_bounds": [{"position": "QB", "minimum": 2, "maximum": 2},
                                    {"position": "K", "minimum": 0, "maximum": 0},
                                    {"position": "DST", "minimum": 0, "maximum": 0}]}
    theses = [wins_big(one), wins_big(two)]
    if variants:
        theses += [close(one, two, high=True), close(one, two, high=False),
                   close(two, one, high=True), close(two, one, high=False)]
    else:
        theses += [close(one, two, high=False), close(two, one, high=False)]
    return [*theses, defensive, shootout]


def build_world(tmp_path, *, variants: bool, with_theses: bool = True, extra_flags=(), theses=None):
    """Write the thesis files, run the generator, validate: the policy a run would be handed."""

    tmp_path.mkdir(parents=True, exist_ok=True)
    slate = parse_salaries(SALARIES)
    fillable = list(plan_entries(parse_entries(ENTRIES), slate).fillable)[:ENTRY_COUNT]
    chosen = (theses if theses is not None else r33_theses(slate, variants=variants)) if with_theses else []
    args = ["--salaries", str(SALARIES), "--entries", str(ENTRIES), "--out", str(tmp_path / "policy.json"),
            *extra_flags]
    for entry_id in fillable:
        args += ["--entry-id", entry_id]
    for index, thesis in enumerate(chosen):
        path = tmp_path / f"thesis_{index}.json"
        path.write_text(json.dumps(thesis), encoding="utf-8")
        args += ["--thesis", str(path)]
    assert _generator().main(args) == 0
    raw = (tmp_path / "policy.json").read_bytes()
    validation = validate_portfolio_policy_bytes(raw, slate=slate, entry_ids=fillable)
    assert validation.valid, validation.blockers()
    objective = {row.dk_id: row.salary / 1000.0 for row in slate.players}
    unavailable = tuple(row.dk_id for row in slate.players if row.status_raw in {"OUT", "IR"})
    return slate, validation.policy, raw, objective, unavailable, fillable


def solve_world(slate, policy, objective, unavailable):
    """Bank and joint solve at the budgets a 20-entry policy run is given (`scaled_*`, unchanged by this session)."""

    bank = build_policy_candidate_bank(
        slate, objective, excluded_ids=unavailable, candidate_limit=scaled_candidate_limit(ENTRY_COUNT),
        total_time_limit_seconds=scaled_candidate_seconds(ENTRY_COUNT), per_solve_time_limit_seconds=2, policy=policy)
    selection = solve_policy_portfolio(
        policy, bank, time_limit_seconds=scaled_selection_seconds(ENTRY_COUNT))
    return bank, selection


def audit_world(slate, policy, raw, bank, selection, fillable):
    picks = [(bank.candidates[index], name)
             for index, name in zip(selection.selected_candidate_indexes, selection.selected_theses)]
    pairs = [(entry, candidate.roster) for entry, (candidate, _name) in zip(fillable, picks)]
    artifact = ("Entry ID,CPT,FLEX,FLEX,FLEX,FLEX,FLEX\n"
                + "".join(",".join((entry, *roster)) + "\n" for entry, roster in pairs)).encode("utf-8")
    normalized = policy.canonical_bytes()
    entry_bytes = ENTRIES.read_bytes()
    by_id = {row.dk_id: row for row in slate.players}
    people = {entry: frozenset(by_id[dk_id].underlying_id for dk_id in roster) for entry, roster in pairs}
    summary = {
        "portfolio_policy": {"theses": {"by_lineup": {candidate.canonical_key: name for candidate, name in picks}}},
        "person_exposure": dict(sorted(Counter(p for group in people.values() for p in group).items())),
        "captain_exposure": dict(sorted(Counter(by_id[roster[0]].underlying_id for _e, roster in pairs).items())),
        "pairwise_person_overlap": [
            {"entry_id_a": a, "entry_id_b": b, "people": len(people[a] & people[b])}
            for a, b in combinations([entry for entry, _r in pairs], 2)],
        "selected_lineup_count": len(pairs)}
    audit = audit_policy_assignments(
        slate=slate, policy=policy, assignments=pairs, salary_bytes=SALARIES.read_bytes(), entry_bytes=entry_bytes,
        expected_entry_sha256=sha256_bytes(entry_bytes), source_policy_bytes=raw,
        expected_source_policy_sha256=sha256_bytes(raw), normalized_policy_bytes=normalized,
        expected_normalized_policy_sha256=sha256_bytes(normalized), assignment_artifact_bytes=artifact,
        expected_assignment_artifact_sha256=sha256_bytes(artifact), selector_summary=summary)
    return audit, picks


# ------------------------------------------------------------------ the acceptance


@pytest.mark.parametrize(("variants", "allotment"), [
    (True, [3, 3, 3, 3, 2, 2, 2, 2]),   # both teams win big, each wins close high and low, a battle, a shootout
    (False, [4, 4, 3, 3, 3, 3]),        # R33's own six
])
def test_the_20_row_ne_sea_portfolio_is_spread_across_ben_s_theses(tmp_path, variants, allotment):
    slate, policy, raw, objective, unavailable, fillable = build_world(tmp_path, variants=variants)
    assert [item.rows for item in policy.theses] == allotment and all(item.active for item in policy.theses)
    # No thesis is short: each has room for its rows, distinct from every other thesis's.
    probe = probe_thesis_rows(slate, objective, policy, excluded_ids=unavailable, per_solve_seconds=2, total_seconds=60)
    assert not probe.short and not probe.unproven
    bank, selection = solve_world(slate, policy, objective, unavailable)
    assert selection.passed, (selection.status, bank.status)
    audit, picks = audit_world(slate, policy, raw, bank, selection, fillable)
    assert audit.passed, audit.problems
    report = audit.as_report()["theses"]
    measures = report["measures"]

    # Every lineup follows the thesis it names, and none repeats.
    by_name = {item.name: item for item in policy.theses}
    assert len({candidate.canonical_key for candidate, _name in picks}) == ENTRY_COUNT
    assert all(not thesis_roster_violations(slate, candidate.roster, by_name[name]) for candidate, name in picks)
    assert Counter(name for _candidate, name in picks) == {item.name: item.rows for item in policy.theses}
    assert all(entry["follows"] for entry in report["entries"].values())
    # No player over the share limit (0.60 of 20), and every person in more than half the rows is named.
    assert measures["most_rows_one_player_sinks"]["rows"] <= PERSON_LIMIT
    assert all(item["rows"] <= PERSON_LIMIT for item in measures["people_in_more_than_half"])
    # Captains well beyond the five at 25% the rejected ATL@GB file held, none over the 20% default.
    assert measures["distinct_captains"] > 5
    assert measures["max_captain_share_percentage"] <= 100 * CAPTAIN_LIMIT / ENTRY_COUNT
    assert max(item["count"] for item in measures["captains"].values()) <= CAPTAIN_LIMIT
    # A kicker Captain where theses call for one. These theses open kickers OR defenses, so which of the two the
    # prior picks is the engine's; the test below forces each. The loop only restates the audit's Captain-set rule.
    by_id = {row.dk_id: row for row in slate.players}
    assert any(by_id[candidate.roster[0]].position == "K" for candidate, _name in picks)
    for candidate, name in picks:
        opens = {person.underlying_id.split("|")[1] for person in by_name[name].captain_set}
        if opens <= {"K", "DST"}:
            assert by_id[candidate.roster[0]].position in {"K", "DST"}
    assert "LEVERAGE_NO_OWNERSHIP_INPUT_SO_LEVERAGE_IS_UNMEASURED" in measures["does_not_establish"]
    print(f"\n[{len(policy.theses)} theses] distinct captains {measures['distinct_captains']}, max captain share "
          f"{measures['max_captain_share_percentage']}%, people in more than half {len(measures['people_in_more_than_half'])},"
          f" most rows one player sinks {measures['most_rows_one_player_sinks']['rows']}, most rows one thesis sinks "
          f"{measures['most_rows_one_thesis_sinks']['rows']}, same-core pairs {len(measures['same_core_pairs'])}; "
          f"bank {len(bank.candidates)} in {bank.elapsed_seconds:.1f}s, joint {selection.status} in "
          f"{selection.elapsed_seconds:.2f}s")


def test_the_theses_leave_the_washout_measures_no_worse_than_the_same_fixture_without_them(tmp_path):
    # What this measures, and what it does not. With Session 56's registered defaults (a Captain cap of 0.20, overlap
    # 4) the same fixture with NO theses already holds 9 distinct Captains at 20% each, so the theses do not raise the
    # Captain count: eight of them give 7, R33's six give 9, and that measure is deliberately not asserted. The worst
    # single player is the 0.60 cap either way (12 of 20). What the theses add is structure (every row follows a named
    # game script, a kicker or defense Captain where one is called for), and on this fixture fewer people in more than
    # half the rows. The assertions below only say that nothing got worse; they would pass with no improvement at all,
    # and the printed columns are the evidence for the changelog.
    slate, policy, raw, objective, unavailable, fillable = build_world(tmp_path / "with", variants=True)
    bank, selection = solve_world(slate, policy, objective, unavailable)
    audit, _picks = audit_world(slate, policy, raw, bank, selection, fillable)
    after = audit.as_report()["theses"]["measures"]
    slate, plain, _raw, objective, unavailable, fillable = build_world(
        tmp_path / "without", variants=True, with_theses=False, extra_flags=OPEN_BAND)
    assert plain.theses == ()
    bank, selection = solve_world(slate, plain, objective, unavailable)
    assert selection.passed, selection.status
    entries = [(entry, bank.candidates[index].roster, None)
               for entry, index in zip(fillable, selection.selected_candidate_indexes)]
    before = thesis_portfolio_measures(slate, entries, allotment={}, followed={}, broken={})
    print(f"\nbefore (no theses): distinct captains {before['distinct_captains']}, max captain share "
          f"{before['max_captain_share_percentage']}%, people in more than half {len(before['people_in_more_than_half'])}, "
          f"most rows one player sinks {before['most_rows_one_player_sinks']['rows']}")
    print(f"after (8 theses):   distinct captains {after['distinct_captains']}, max captain share "
          f"{after['max_captain_share_percentage']}%, people in more than half {len(after['people_in_more_than_half'])}, "
          f"most rows one player sinks {after['most_rows_one_player_sinks']['rows']}")
    assert len(after["people_in_more_than_half"]) <= len(before["people_in_more_than_half"])
    assert after["most_rows_one_player_sinks"]["rows"] <= before["most_rows_one_player_sinks"]["rows"]
    assert after["max_captain_share_percentage"] <= before["max_captain_share_percentage"]


def test_a_salary_band_no_thesis_can_meet_never_costs_a_thesis_and_the_generator_opens_it(tmp_path):
    # The $1 to $500 band is a hygiene preference; a kicker, a defense and backs cannot spend $49,500. The probe tests
    # thesis rules only, so no thesis is named for the band. But `run-slate`'s ladder gives the caps way BEFORE a band
    # (Session 56: 0.80 and 0.40, then none, then rung 1), so a portfolio left on the band would lose its 0.60 person
    # cap and 0.20 Captain cap on the way (measured by the reviewer: five failed attempts, then rung 1 with both caps
    # off). That is why the generator writes the band open when a thesis is supplied.
    slate, policy, _raw, objective, unavailable, _fillable = build_world(
        tmp_path, variants=False, extra_flags=DEFAULT_BAND)
    assert (policy.structural_bounds.salary_left.minimum, policy.structural_bounds.salary_left.maximum) == (1, 500)
    probe = probe_thesis_rows(slate, objective, policy, excluded_ids=unavailable, per_solve_seconds=2, total_seconds=60)
    assert not probe.short
    bank, selection = solve_world(slate, policy, objective, unavailable)
    served = {name: serving for name, _rows, serving in bank.theses}
    assert served["NE_WINS_CLOSE"] == 0 and served["DEFENSIVE_BATTLE"] == 0
    assert not selection.passed and selection.status == "CANDIDATE_BANK_EXHAUSTED_INCOMPLETE"


def test_the_generator_writes_the_band_open_for_a_portfolio_and_leaves_it_alone_otherwise(tmp_path):
    slate = parse_salaries(SALARIES)
    theses = r33_theses(slate, variants=False)

    def band(label, **kwargs):
        policy = build_world(tmp_path / label, variants=False, **kwargs)[1]
        return (policy.structural_bounds.salary_left.minimum, policy.structural_bounds.salary_left.maximum)

    assert band("portfolio") == (0, 50000)
    assert band("none", with_theses=False) == (1, 500)  # a policy with no thesis keeps Session 23's default
    # One thesis without a weight is the Session 23b output, v3, and keeps the band it always had.
    assert band("one_thesis", theses=theses[:1]) == (1, 500)
    assert band("one_weighted", theses=[{**theses[0], "row_weight": 2}]) == (0, 50000)
    # Either flag, given, is the operator's and wins over the default for a portfolio.
    assert band("one_flag", extra_flags=("--salary-left-max", "400")) == (0, 400)
    assert band("both_flags", extra_flags=DEFAULT_BAND) == (1, 500)


def test_theses_that_require_a_kicker_or_a_defense_captain_get_one_in_every_one_of_their_rows(tmp_path):
    # R33's kicker and defense Captains were the thing nothing could force: the mean prior never chooses one. A thesis
    # that opens only kickers, or only defenses, makes every one of its rows open with one.
    slate = parse_salaries(SALARIES)
    one, two = sorted({row.team for row in slate.players})
    theses = r33_theses(slate, variants=False)
    theses[2] = {**theses[2], "captain_set": _top(slate, one, "K", 1)}
    assert theses[4]["name"] == "DEFENSIVE_BATTLE"
    theses[4] = {**theses[4], "captain_set": [*_top(slate, one, "DST", 1), *_top(slate, two, "DST", 1)]}
    slate, policy, raw, objective, unavailable, fillable = build_world(tmp_path, variants=False, theses=theses)
    bank, selection = solve_world(slate, policy, objective, unavailable)
    assert selection.passed, selection.status
    audit, picks = audit_world(slate, policy, raw, bank, selection, fillable)
    assert audit.passed, audit.problems
    by_id = {row.dk_id: row for row in slate.players}
    captains = {name: [by_id[candidate.roster[0]].position for candidate, picked in picks if picked == name]
                for name in (theses[2]["name"], "DEFENSIVE_BATTLE")}
    assert captains[theses[2]["name"]] == ["K"] * 3
    assert captains["DEFENSIVE_BATTLE"] == ["DST"] * 3
    assert {by_id[candidate.roster[0]].position for candidate, _name in picks} >= {"K", "DST"}


def test_the_build_is_deterministic(tmp_path):
    picks = []
    for name in ("a", "b"):
        slate, policy, _raw, objective, unavailable, _fillable = build_world(tmp_path / name, variants=False)
        bank, selection = solve_world(slate, policy, objective, unavailable)
        picks.append([(bank.candidates[index].roster, thesis)
                      for index, thesis in zip(selection.selected_candidate_indexes, selection.selected_theses)])
    assert picks[0] == picks[1] and len(picks[0]) == ENTRY_COUNT


# ------------------------------------------------------------------ the generator


def test_the_generator_writes_v4_for_a_portfolio_and_v3_for_one_thesis_without_a_weight(tmp_path):
    slate = parse_salaries(SALARIES)
    theses = r33_theses(slate, variants=False)
    schemas = {}
    for label, chosen in (("one", theses[:1]), ("weighted_one", [{**theses[0], "row_weight": 3}]), ("two", theses[:2])):
        built = build_world(tmp_path / label, variants=False, theses=chosen)
        schemas[label] = json.loads(built[2])["schema_version"]
    assert schemas == {"one": "nfl_showdown_portfolio_policy_v3", "weighted_one": "nfl_showdown_portfolio_policy_v4",
                       "two": "nfl_showdown_portfolio_policy_v4"}


def test_the_generator_carries_each_row_weight_and_keeps_every_required_captain_open(tmp_path):
    slate = parse_salaries(SALARIES)
    theses = r33_theses(slate, variants=False)
    theses[0] = {**theses[0], "row_weight": 3}
    _slate, policy, raw, _objective, _unavailable, _fillable = build_world(tmp_path, variants=False, theses=theses)
    assert [(item.name, item.row_weight) for item in policy.theses][:2] == [("NE_WINS_BIG", 3), ("SEA_WINS_BIG", 1)]
    assert policy.theses[0].rows > policy.theses[1].rows
    zeroed = {item["underlying_id"] for item in json.loads(raw)["controls"]["max_captain_exposure"]["overrides"]
              if item["fraction"] == 0}
    required = {person.underlying_id for item in policy.theses for person in item.captain_set}
    assert required and not required & zeroed  # a kicker or DST Captain a thesis needs is never zeroed by the default
