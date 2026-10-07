"""Session 23c layer 3: the ladder and the selector with a portfolio of Showdown theses.

A thesis no lineup can follow is dropped by name and its rows go to the others; no rung ever changes a thesis
(byte for byte, `row_weight` included); a thesis that names a backup quarterback admits him for its own rows
and no other thesis's. None of this relaxes a thesis. A thesis is a choice, not a forecast.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from nfl_dfs.dk import parse_entries, parse_salaries
from nfl_dfs.gate_registry import load_gate_registry
from nfl_dfs.portfolio_policy import (
    POLICY_SCHEMA_VERSION_V4,
    canonical_decimal_json_bytes,
    portfolio_policy_template,
    validate_portfolio_policy_bytes,
)
from nfl_dfs.relaxation import (
    STRUCTURE,
    Failure,
    Ladder,
    overlap_step_text,
    selection_overlap_steps,
    showdown_relaxed_controls,
    supplied_rung,
)
from nfl_dfs.selection import SelectionError, select_prior_lineups

from . import test_qb_depth_roles as depth
from .test_showdown_theses import _prepared, _row, _thesis
from .test_showdown_thesis_portfolio import SIX, _policy_v4, _three

ROOT = Path(__file__).resolve().parents[1]
SUPPLIED = ROOT / "tests" / "fixtures" / "supplied"


# ------------------------------------------------------------------ the ladder over the supplied NE@SEA fixture


def _supplied_portfolio(tmp_path, theses_builder, *, external=(), **controls):
    slate = parse_salaries(SUPPLIED / "DKSalaries Salary CSV Showdown.csv")
    entries = parse_entries(SUPPLIED / "DKEntries CSV 20 entries.csv")
    entry_ids = tuple(item.entry_id for item in entries.authorizations)
    theses = theses_builder(slate)
    document = portfolio_policy_template(
        slate, entry_ids, schema_version=POLICY_SCHEMA_VERSION_V4,
        controls={
            "max_combined_person_exposure": {"default_fraction": Decimal("0.8"), "overrides": []},
            "max_captain_exposure": {"default_fraction": Decimal("0.5"), "overrides": []},
            "max_pairwise_person_overlap": 4,
            "structural_bounds": {"qb_count": {"minimum": 1, "maximum": 1}, "salary_left": {"minimum": 1, "maximum": 500},
                                  "kicker_count": 1, "dst_count": 1, "offense_against_own_dst": True},
            **controls, "theses": theses})
    validation = validate_portfolio_policy_bytes(
        canonical_decimal_json_bytes(document), slate=slate, entry_ids=entry_ids, externally_excluded_people=external)
    assert validation.policy is not None, validation.blockers()
    ladder = Ladder(slate=slate, entries=entries, folder=tmp_path / "relaxation", registry=load_gate_registry(),
                    externally_excluded_people=external,
                    supplied=supplied_rung(validation.policy, source_path=None, source_sha256=None,
                                           normalized_path=None, normalized_sha256=validation.policy.normalized_sha256))
    return ladder, validation, theses, slate


def _fixture_portfolio(slate):
    """Three theses on the supplied fixture, each with its own Captain set, with every field declared."""

    teams = sorted({row.team for row in slate.players})

    def names(position, team):
        return sorted({row.name for row in slate.players if row.position == position and row.team == team})

    def thesis(captains, name, team, bounds):
        return {**_thesis(slate, captains, name=name, teams=[team], team_bounds=[], position_bounds=bounds,
                          excluded_people=[], named_backup_quarterbacks=[]), "row_weight": 1}

    return [
        thesis([names("QB", teams[0])[0]], "FIRST_WINS_BIG", teams[0], []),
        thesis([names("K", teams[0])[0]], "FIRST_WINS_CLOSE_LOW", teams[0],
               [{"position": "K", "minimum": 1, "maximum": 1}]),
        thesis([names("QB", teams[1])[0]], "SECOND_WINS_BIG", teams[1], []),
    ]


def _bytes(items):
    return canonical_decimal_json_bytes(items)


def test_an_unbuildable_thesis_among_several_is_dropped_by_name_and_its_rows_go_to_the_others(tmp_path):
    ladder, validation, theses, _slate = _supplied_portfolio(tmp_path, _fixture_portfolio)
    assert [item.rows for item in validation.policy.theses] == [7, 7, 6]
    failure = Failure("THESIS_UNBUILDABLE", STRUCTURE, "no lineup", {
        "thesis": "FIRST_WINS_CLOSE_LOW", "theses": ["FIRST_WINS_CLOSE_LOW"],
        "reason": "the test's reason", "reasons": {"FIRST_WINS_CLOSE_LOW": "the test's reason"}})
    made = ladder.next(failure)
    assert made is not None and made.rung is None
    policy = made.policy
    assert policy.thesis_schema == "v4"
    assert [item.name for item in policy.theses] == ["FIRST_WINS_BIG", "SECOND_WINS_BIG"]
    assert sum(item.rows for item in policy.theses) == 20  # the dropped thesis's rows were reallotted by weight
    # The survivors are exactly what Ben declared, byte for byte, and nothing else moved: not a rung.
    declared = {item["name"]: item for item in theses}
    assert [item.source_mapping() for item in policy.theses] == [declared[item.name] for item in policy.theses]
    before, after = showdown_relaxed_controls(validation.policy, None), showdown_relaxed_controls(policy, None)
    assert {key: value for key, value in before.items() if key != "theses"} == {
        key: value for key, value in after.items() if key != "theses"}
    # Only the removed thesis is recorded, once, with its own reason and where its rows went.
    (record,) = [item for item in ladder.records if item["limitation_code"] == "THESIS_DROPPED"]
    assert record["constraint"] == "theses.FIRST_WINS_CLOSE_LOW"
    assert "the test's reason" in record["limitation_text"] and "its rows went to FIRST_WINS_BIG, SECOND_WINS_BIG" in (
        record["limitation_text"])
    written = json.loads(Path(made.source_path).read_text(encoding="utf-8"))
    assert written["schema_version"] == POLICY_SCHEMA_VERSION_V4
    assert [item["name"] for item in written["controls"]["theses"]] == ["FIRST_WINS_BIG", "SECOND_WINS_BIG"]


def test_dropping_the_last_thesis_builds_the_policy_without_theses(tmp_path):
    ladder, validation, _theses, _slate = _supplied_portfolio(tmp_path, lambda slate: _fixture_portfolio(slate)[:1])
    assert [item.rows for item in validation.policy.theses] == [20]
    made = ladder.next(Failure("THESIS_UNBUILDABLE", STRUCTURE, "no lineup", {
        "thesis": "FIRST_WINS_BIG", "theses": ["FIRST_WINS_BIG"], "reason": "the test's reason"}))
    assert made.policy.theses == () and made.policy.thesis_schema is None
    written = json.loads(Path(made.source_path).read_text(encoding="utf-8"))
    assert written["schema_version"] == "nfl_showdown_portfolio_policy_v2" and "theses" not in written["controls"]
    (record,) = ladder.records
    # No thesis is left to take its rows, so the record says why it was dropped and does not claim they went anywhere.
    assert record["limitation_code"] == "THESIS_DROPPED" and "the test's reason" in record["limitation_text"]
    assert "its rows went" not in record["limitation_text"]


def test_a_failure_that_names_no_active_thesis_drops_every_one_as_session_23b_did(tmp_path):
    # The probe always names the theses it proved short. A failure that names none (or only one that is not active)
    # is the Session 23b shape: the thesis is what could not be built, so every active thesis goes, each by name.
    ladder, _validation, _theses, _slate = _supplied_portfolio(tmp_path, _fixture_portfolio)
    made = ladder.next(Failure("THESIS_UNBUILDABLE", STRUCTURE, "no lineup", {"reason": "the test's reason"}))
    assert made.policy.theses == ()
    dropped = [item for item in ladder.records if item["limitation_code"] == "THESIS_DROPPED"]
    assert [item["constraint"] for item in dropped] == [
        "theses.FIRST_WINS_BIG", "theses.FIRST_WINS_CLOSE_LOW", "theses.SECOND_WINS_BIG"]
    assert all("the test's reason" in item["limitation_text"] for item in dropped)


def test_every_rung_carries_every_thesis_of_a_portfolio_byte_for_byte(tmp_path):
    ladder, validation, theses, _slate = _supplied_portfolio(tmp_path, _fixture_portfolio)
    policy = validation.policy
    declared = _bytes(theses)
    for rung in (None, 1, 2, 3):
        assert _bytes(showdown_relaxed_controls(policy, rung)["theses"]) == declared
    for expected in (1, 2):
        made = ladder.next(Failure("MODELED_BANK_INFEASIBILITY", STRUCTURE, "joint infeasible"))
        assert made is not None and made.rung == expected
        written = json.loads(Path(made.source_path).read_text(encoding="utf-8"))
        assert written["schema_version"] == POLICY_SCHEMA_VERSION_V4
        assert _bytes(written["controls"]["theses"]) == declared
        assert [item.rows for item in made.policy.active_theses] == [7, 7, 6]
    assert not any(record["limitation_code"] == "THESIS_DROPPED" for record in ladder.records)


def test_a_rung_that_changed_one_thesis_of_a_portfolio_is_refused(tmp_path, monkeypatch):
    from nfl_dfs import relaxation

    ladder, _validation, _theses, _slate = _supplied_portfolio(tmp_path, _fixture_portfolio)
    original = relaxation.showdown_relaxed_controls

    def bent(policy, rung, **keyed):  # a rung that loosens the second thesis's weight: its rows would move
        controls = original(policy, rung, **keyed)
        if rung is not None and "theses" in controls:
            controls["theses"][1]["row_weight"] = 5
        return controls

    monkeypatch.setattr(relaxation, "showdown_relaxed_controls", bent)
    with pytest.raises(ValueError, match="RELAXATION_RUNG_UNBUILDABLE"):
        ladder.next(Failure("MODELED_BANK_INFEASIBILITY", STRUCTURE, "joint infeasible"))


def test_rung_4_names_every_thesis_it_drops(tmp_path):
    ladder, _validation, _theses, _slate = _supplied_portfolio(tmp_path, _fixture_portfolio)
    failure = Failure("MODELED_BANK_INFEASIBILITY", STRUCTURE, "joint infeasible")
    floor = ladder._no_policy(ladder.current, failure, 0.0, why="the test")
    assert floor is not None and floor.policy is None
    codes = [record["limitation_code"] for record in ladder.records]
    assert codes == ["THESIS_DROPPED"] * 3 + ["RELAXATION_POLICY_DROPPED"]
    assert [record["constraint"] for record in ladder.records[:3]] == [
        "theses.FIRST_WINS_BIG", "theses.FIRST_WINS_CLOSE_LOW", "theses.SECOND_WINS_BIG"]


def test_a_thesis_dropped_at_validation_is_named_with_where_its_rows_went(tmp_path):
    slate = parse_salaries(SUPPLIED / "DKSalaries Salary CSV Showdown.csv")
    kicker = sorted({row for row in slate.players if row.position == "K" and row.team == sorted(
        {item.team for item in slate.players})[0]}, key=lambda row: row.dk_id)[0]
    ladder, validation, _theses, _slate = _supplied_portfolio(
        tmp_path, _fixture_portfolio, external=(kicker.underlying_id,))
    by_name = {item.name: item for item in validation.policy.theses}
    assert not by_name["FIRST_WINS_CLOSE_LOW"].active and by_name["FIRST_WINS_CLOSE_LOW"].rows == 0
    assert by_name["FIRST_WINS_BIG"].rows + by_name["SECOND_WINS_BIG"].rows == 20
    (record,) = [item for item in ladder.records if item["limitation_code"] == "THESIS_DROPPED"]
    assert "its rows went to the other theses (FIRST_WINS_BIG, SECOND_WINS_BIG)" in record["limitation_text"]


def test_a_bound_one_thesis_widened_is_named_with_that_thesis_alone(tmp_path):
    def kickers(slate):
        portfolio = _fixture_portfolio(slate)
        portfolio[1] = {**portfolio[1], "position_bounds": [{"position": "K", "minimum": 2, "maximum": 2}]}
        return portfolio

    ladder, validation, _theses, _slate = _supplied_portfolio(tmp_path, kickers)
    bounds = {item.name: item.effective_bounds.kicker_count_maximum for item in validation.policy.theses}
    assert bounds == {"FIRST_WINS_BIG": 1, "FIRST_WINS_CLOSE_LOW": 2, "SECOND_WINS_BIG": 1}
    assert validation.policy.structural_bounds.kicker_count_maximum == 1
    (named,) = [item for item in ladder.records if item["limitation_code"] == "PORTFOLIO_POLICY_THESIS_OVERRIDES_BOUND"]
    assert "FIRST_WINS_CLOSE_LOW" in named["limitation_text"] and "kicker_count 1 to 2" in named["limitation_text"]


# ------------------------------------------------------------------ the selector over the synthetic NE@SEA slate


def _select_portfolio(tmp_path, theses_builder, count=6, controls=None, **kwargs):
    tmp_path.mkdir(parents=True, exist_ok=True)
    slate, model, contract, splits = _prepared(tmp_path)
    entries = tuple(str(n) for n in range(1, count + 1))
    policy, raw = _policy_v4(slate, theses_builder(slate), entries, **(controls or {}))
    lineups, _scores, report = select_prior_lineups(
        slate, model, splits, contract, count=count, portfolio_policy=policy, **kwargs)
    return slate, policy, raw, lineups, report


def test_a_portfolio_selects_and_each_lineup_names_the_thesis_it_fills(tmp_path):
    slate, policy, _raw, lineups, report = _select_portfolio(tmp_path, _three)
    assert len(lineups) == 6 and len({lineup.canonical_key for lineup in lineups}) == 6
    block = report["portfolio_policy"]["theses"]
    assert block["build_version"] == "showdown_thesis_portfolio_sd3_v1"
    counts = {name: sum(1 for lineup in lineups if lineup.thesis == name) for name in ("NE_WIN_BIG", "NE_WIN_CLOSE_LOW", "SEA_WIN_BIG")}
    assert counts == {"NE_WIN_BIG": 2, "NE_WIN_CLOSE_LOW": 2, "SEA_WIN_BIG": 2}
    assert block["by_lineup"] == {lineup.canonical_key: lineup.thesis for lineup in lineups}
    assert [item["rows"] for item in block["theses"]] == [2, 2, 2]
    # What the structural probe found before any bank, with no solver limit stopping it.
    assert block["probe"] == {"found": {"NE_WIN_BIG": 2, "NE_WIN_CLOSE_LOW": 2, "SEA_WIN_BIG": 2}, "unproven": []}
    assert "EV_ROI_OR_WIN_PROBABILITY" in block["does_not_establish"]
    # Every lineup follows its own thesis, and its payload names it.
    by_name = {item.name: item for item in policy.active_theses}
    from nfl_dfs.portfolio_policy import thesis_roster_violations

    for lineup in lineups:
        assert not thesis_roster_violations(slate, lineup.roster, by_name[lineup.thesis])
        assert lineup.as_payload({})["thesis"] == lineup.thesis
    captains = {_row(slate, lineup.roster[0]).name for lineup in lineups}
    assert "NE Kicker" in captains or "Patriots" in captains  # a kicker or DST Captain where a thesis calls for one


def test_the_probe_is_charged_to_the_banks_window_not_added_to_it(tmp_path, monkeypatch):
    # R31: the lock clock bounds the search stage, which the deadline controller sized as the bank's window plus the
    # joint solve. The probe takes the smaller of the per-solve limit and the bank's own, may take at most the bank's
    # whole window, and the bank is given what the probe left: probe plus bank never exceed `candidate_seconds`.
    from nfl_dfs import selection

    seen, bank = {}, {}
    real_probe, real_bank = selection.probe_thesis_rows, selection.build_policy_candidate_bank

    def watch_probe(*args, **kwargs):
        seen.update(kwargs)
        return real_probe(*args, **kwargs)

    def watch_bank(*args, **kwargs):
        bank.update(kwargs)
        return real_bank(*args, **kwargs)

    monkeypatch.setattr(selection, "probe_thesis_rows", watch_probe)
    monkeypatch.setattr(selection, "build_policy_candidate_bank", watch_bank)
    _select_portfolio(tmp_path, _three, time_limit_seconds=10.0, policy_candidate_seconds=12.0,
                      policy_candidate_per_solve_seconds=1.5)
    assert seen["per_solve_seconds"] == 1.5
    assert seen["total_seconds"] == 12.0  # min(10 s x (6 rows + 1), the bank's 12 s)
    assert 0.0 < bank["total_time_limit_seconds"] < 12.0  # the probe's time came out of the bank's window
    assert bank["total_time_limit_seconds"] >= selection.MINIMUM_BANK_SECONDS


def test_the_selection_is_deterministic(tmp_path):
    first = _select_portfolio(tmp_path / "a", _three)
    second = _select_portfolio(tmp_path / "b", _three)
    assert [(lineup.roster, lineup.thesis) for lineup in first[3]] == [(lineup.roster, lineup.thesis) for lineup in second[3]]
    assert first[1].canonical_bytes() == second[1].canonical_bytes()


def test_a_portfolio_never_repeats_a_prefilled_roster(tmp_path):
    _slate, _policy, _raw, free, _report = _select_portfolio(tmp_path / "free", _three)
    forbidden = tuple(lineup.roster for lineup in free[:3])
    _slate, _policy, _raw, lineups, _report = _select_portfolio(tmp_path / "prefilled", _three, forbidden_rosters=forbidden)
    assert not {lineup.roster for lineup in lineups} & set(forbidden)
    assert len({lineup.canonical_key for lineup in lineups}) == 6


_SEVEN = ("NE Kicker", "Starter QB", "Lead RB", "Alpha WR", "Patriots", "Sea QB", "Sea Alpha WR")


def test_selection_names_every_thesis_the_probe_proves_short(tmp_path):
    def colliding(slate):
        gone = sorted({row.name for row in slate.players} - set(_SEVEN))
        first = _thesis(slate, ["NE Kicker"], name="A", teams=["NE"], excluded_people=gone)
        return [first, {**first, "name": "B"}]

    tmp_path.mkdir(parents=True, exist_ok=True)
    slate, model, contract, splits = _prepared(tmp_path)
    policy, _raw = _policy_v4(slate, colliding(slate), tuple(str(n) for n in range(1, 9)))
    with pytest.raises(SelectionError) as raised:
        select_prior_lineups(slate, model, splits, contract, count=8, portfolio_policy=policy)
    error = raised.value
    assert error.status == "THESIS_UNBUILDABLE"
    # The plural names every thesis; the singular stays for the readers that already ask for it (Session 23b).
    assert error.facts["theses"] == ["B"] and error.facts["thesis"] == "B"
    assert "distinct from the other theses'" in error.facts["reasons"]["B"] and error.facts["reasons"]["B"] == error.facts["reason"]


def test_a_thesis_that_names_a_backup_quarterback_admits_him_for_its_own_rows_alone(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    slate, model, contract, splits = depth._setup(tmp_path)
    evidence = depth._package(tmp_path / "qb", slate, depth._orders())
    theses = [
        {**_thesis(slate, ["KC Alpha WR"], name="SHOOTOUT_NAMED", teams=["KC", "DEN"],
                   position_bounds=[{"position": "QB", "minimum": 2, "maximum": 2}],
                   excluded_people=["DEN Starter QB"], named_backup_quarterbacks=["KC Backup QB"])},
        _thesis(slate, ["KC Starter QB"], name="KC_WINS_BIG", teams=["KC"]),
    ]
    policy, _raw = _policy_v4(slate, theses, ("1", "2", "3", "4"))
    lineups, _scores, report = select_prior_lineups(
        slate, model, splits, contract, count=4, portfolio_policy=policy,
        qb_depth_role_evidence_json=evidence, as_of=depth.AS_OF)
    backup = depth._person(slate, "KC Backup QB")
    holders = {lineup.thesis for lineup in lineups
               if backup in {_row(slate, dk_id).underlying_id for dk_id in lineup.roster}}
    assert holders == {"SHOOTOUT_NAMED"}  # the thesis that named him, and no other
    assert sum(1 for lineup in lineups if lineup.thesis == "SHOOTOUT_NAMED") == 2
    # Admitted by some thesis, so he is not out of the run's own pool; the other thesis keeps him out itself.
    assert report["portfolio_policy"]["theses"]["backup_quarterbacks_excluded"] == []


def test_a_thesis_that_does_not_name_the_backup_cannot_use_him_because_another_thesis_does(tmp_path):
    # Two theses with the same structure: two quarterbacks, the Denver starter out, so the only second quarterback
    # is Kansas City's backup. One names him; the other does not. A quarterback is out of the run's own pool unless
    # some thesis names him, but the thesis that did not name him must still keep him out of its own rows, so it has
    # no lineup and the probe names it (and only it).
    tmp_path.mkdir(parents=True, exist_ok=True)
    slate, model, contract, splits = depth._setup(tmp_path)
    evidence = depth._package(tmp_path / "qb", slate, depth._orders())
    named = _thesis(slate, ["KC Alpha WR"], name="NAMED", teams=["KC", "DEN"],
                    position_bounds=[{"position": "QB", "minimum": 2, "maximum": 2}],
                    excluded_people=["DEN Starter QB"], named_backup_quarterbacks=["KC Backup QB"])
    policy, _raw = _policy_v4(slate, [named, {**named, "name": "UNNAMED", "named_backup_quarterbacks": []}],
                              ("1", "2", "3", "4"))
    with pytest.raises(SelectionError) as raised:
        select_prior_lineups(slate, model, splits, contract, count=4, portfolio_policy=policy,
                             qb_depth_role_evidence_json=evidence, as_of=depth.AS_OF)
    assert raised.value.status == "THESIS_UNBUILDABLE"
    assert raised.value.facts["theses"] == ["UNNAMED"]


def test_the_selection_step_names_a_portfolio_s_unevaluated_teams_once(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    slate, model, contract, splits = depth._setup(tmp_path)
    theses = [_thesis(slate, ["KC Alpha WR"], name="A", teams=["KC", "DEN"]),
              _thesis(slate, ["DEN Alpha WR"], name="B", teams=["KC", "DEN"])]
    policy, _raw = _policy_v4(slate, theses, ("1", "2", "3", "4"))
    _lineups, _scores, report = select_prior_lineups(slate, model, splits, contract, count=4, portfolio_policy=policy)
    assert report["portfolio_policy"]["theses"]["backup_quarterbacks_unevaluated_teams"] == ["DEN", "KC"]
    steps = selection_overlap_steps({"selection": {"selection": report}})
    assert [overlap_step_text(step).split(":", 1)[0] for step in steps] == ["THESIS_BACKUP_QB_UNEVALUATED"]
