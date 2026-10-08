"""Session 66: the thesis book shared by the Showdown QA and value-add scripts (`scripts/showdown_thesis_check.py`).

The two scripts read each Entry ID's thesis from a run's claim and check a roster against it with the one rule every
layer uses (`portfolio_policy.thesis_roster_violations`). The real runs below are the Session 23c `run-slate` fixture
(three theses, six rows, the contest step moves two lineups between Entry IDs), its THESIS_DROPPED variant, and a run
whose theses carry a team bound and a declared structural bound. A thesis is a choice, not a forecast: nothing here
writes a number, and every release truth stays `PRIOR_ONLY / DO_NOT_UPLOAD`.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

from nfl_dfs.dk import parse_entries, parse_salaries
from nfl_dfs.lineups import roster_canonical_key
from nfl_dfs.portfolio_policy import (
    POLICY_SCHEMA_VERSION_V2,
    POLICY_SCHEMA_VERSION_V4,
    PersonBinding,
    StructuralBoundRange,
    StructuralBounds,
)
from nfl_dfs.showdown_theses import CountBound, ShowdownThesis

from .test_readable_review_theses import _controls, _finished
from .test_showdown_theses import _people, _policy, _thesis, _validate
from .test_showdown_thesis_run_slate import _portfolio_controls
from .test_showdown_value_add import BASE, L0, L1, ids, salary_csv

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "showdown_thesis_check.py"


def check_module():
    """The shared module, registered under the name the scripts import, so a patched loader is the one they call."""

    if "showdown_thesis_check" not in sys.modules:
        spec = importlib.util.spec_from_file_location("showdown_thesis_check", SCRIPT)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules["showdown_thesis_check"] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:  # never leave a half-loaded module registered under the scripts' import name
            sys.modules.pop("showdown_thesis_check", None)
            raise
    return sys.modules["showdown_thesis_check"]


def dropped_controls(slate):
    built = _portfolio_controls(slate)
    built["theses"] = [
        built["theses"][0],
        _thesis(slate, ["Sea Kicker"], name="SEA_ALL_IN", teams=["SEA"],
                team_bounds=[{"team": "SEA", "minimum": 6, "maximum": 6}]),
        built["theses"][2],
    ]
    return built


def bounded_controls(slate):
    """The 23c theses with a team bound on the first and a declared structural bound (one quarterback at most)."""

    built = _controls(4)(slate)
    built["structural_bounds"] = {"qb_count": {"minimum": 0, "maximum": 1}}
    built["theses"][0] = _thesis(slate, ["Starter QB", "Alpha WR"], name="NE_WIN_BIG", teams=["NE"],
                                 team_bounds=[{"team": "NE", "minimum": 3, "maximum": 5}])
    return built


@pytest.fixture(scope="module")
def acceptance(tmp_path_factory):
    return _finished(tmp_path_factory, "s66-chk-acc", policy_controls=_controls(4))


@pytest.fixture(scope="module")
def dropped(tmp_path_factory):
    return _finished(tmp_path_factory, "s66-chk-drop", policy_controls=dropped_controls)


@pytest.fixture(scope="module")
def bounded(tmp_path_factory):
    return _finished(tmp_path_factory, "s66-chk-bnd", policy_controls=bounded_controls)


def policy_path(run) -> Path:
    return Path(run.report["prior_review_artifacts"]["portfolio_policy_normalized"])


def claim_path(run) -> Path:
    return Path(run.report["prior_review_artifacts"]["selection_report"])


def template_ids(run) -> list[str]:
    return [item.entry_id for item in parse_entries(run.entries).authorizations]


def rosters(run) -> dict[str, list[str]]:
    return {entry: list(roster) for entry, roster in run.delivered().items()}


def load(run, **over):
    return check_module().load_thesis_book(
        over.get("slate", run.slate), over.get("template_ids", template_ids(run)),
        over.get("rosters", rosters(run)), over.get("policy", policy_path(run)), over.get("claim", claim_path(run)))


def doctored_claim(tmp_path: Path, run, mutate) -> Path:
    record = json.loads(claim_path(run).read_text(encoding="utf-8"))
    mutate(record)
    path = tmp_path / "claim.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    return path


def dk_id(slate, name: str, role: str) -> str:
    return next(row.dk_id for row in slate.players if row.name == name and row.role == role)


def cpt_flex(slate, captain: str, *flex: str) -> list[str]:
    return [dk_id(slate, captain, "CPT"), *(dk_id(slate, name, "FLEX") for name in flex)]


# ----- the real runs: the claim, every binding, and decision (f) --------------------------------------------------


def test_a_real_run_loads_with_every_binding_and_names_each_entry_ids_thesis_after_the_contest_step(acceptance):
    run = acceptance
    assert run.report["prior_review_reports"]["contest_assignment"]["moved_rows"] > 0  # lineups really changed Entry IDs
    book = load(run)
    audit = run.reports["portfolio_policy_audit"]["theses"]["entries"]
    claim = json.loads(claim_path(run).read_text(encoding="utf-8"))["selection"]["portfolio_policy"]["theses"]
    assert sorted(book.theses) == ["NE_WIN_BIG", "NE_WIN_CLOSE_LOW", "SEA_WIN_BIG"]
    assert dict(book.entries) == claim["entries"] == {entry: item["thesis"] for entry, item in audit.items()}
    assert len(book.entries) == 6
    # The claim's thesis for each Entry ID is the thesis of the lineup that Entry ID holds in the delivered file.
    for entry, roster in rosters(run).items():
        assert claim["by_lineup"][roster_canonical_key(run.slate, roster)] == book.entries[entry]
        assert book.check(entry, roster) == (book.entries[entry], ())  # and each lineup follows it


def test_the_dropped_thesis_run_binds_to_the_rebuilt_policy_and_lists_only_active_theses(dropped):
    run = dropped
    book = load(run)
    assert sorted(book.theses) == ["NE_WIN_BIG", "SEA_WIN_BIG"]  # SEA_ALL_IN was dropped by the ladder
    assert set(book.entries.values()) == {"NE_WIN_BIG", "SEA_WIN_BIG"}
    # The claim hashes the rung's rebuilt normalized policy, which is the file on disk.
    assert "relaxation" in str(policy_path(run))
    for entry, roster in rosters(run).items():
        assert book.check(entry, roster) == (book.entries[entry], ())


def test_the_description_carries_the_three_hashes_and_says_the_backup_rule_was_not_evaluated(acceptance):
    book = load(acceptance)
    described = book.describe()
    assert described["policy_sha256"] == acceptance.hashes["portfolio_policy_normalized"]
    assert described["claim_sha256"] == acceptance.hashes["selection_report"]
    assert described["salary_sha256"] == acceptance.slate.salary_hash
    # Real runs carry no quarterback depth evidence: the backup rule did not run, and the output says so.
    assert described["backup_quarterback"] == "NOT_EVALUATED"
    assert described["backup_quarterbacks_unevaluated_teams"] == ["NE", "SEA"]
    assert described["theses"] == ["NE_WIN_BIG", "NE_WIN_CLOSE_LOW", "SEA_WIN_BIG"]
    assert load(acceptance).describe() == described  # deterministic


def _rewrite(path: Path, tmp_path: Path, **dump) -> Path:
    target = tmp_path / "policy.json"
    target.write_text(json.dumps(json.loads(path.read_bytes()), **dump), encoding="utf-8")
    return target


def _swap_two_theses(run, rost):
    book = load(run)
    first, other = next((a, b) for a in book.entries for b in book.entries if book.entries[a] != book.entries[b])
    rost[first], rost[other] = rost[other], rost[first]
    return first, other


CASES = {
    "salary": ("THESIS_POLICY_SALARY_MISMATCH",
               lambda tmp, run: {"slate": run.slate.model_copy(update={"salary_hash": "0" * 64})}),
    "claim_hash": ("THESIS_CLAIM_POLICY_MISMATCH", lambda tmp, run: {"claim": doctored_claim(
        tmp, run, lambda rec: rec["selection"]["portfolio_policy"].update(normalized_policy_sha256="0" * 64))}),
    "policy_not_canonical": ("THESIS_POLICY_UNREADABLE",
                             lambda tmp, run: {"policy": _rewrite(policy_path(run), tmp, indent=2)}),
    "policy_garbage": ("THESIS_POLICY_UNREADABLE",
                       lambda tmp, run: {"policy": (tmp / "g.json").write_bytes(b"{") and tmp / "g.json"}),
    "template": ("THESIS_POLICY_ENTRY_IDS_NOT_IN_TEMPLATE",
                 lambda tmp, run: {"template_ids": template_ids(run)[:-1]}),
    "unknown_thesis": ("THESIS_CLAIM_UNKNOWN_THESIS", lambda tmp, run: {"claim": doctored_claim(
        tmp, run, lambda rec: rec["selection"]["portfolio_policy"]["theses"]["entries"].update(
            {"900000001": "NO_SUCH_THESIS"}))}),
    "claim_missing": ("THESIS_CLAIM_MISSING", lambda tmp, run: {"claim": doctored_claim(
        tmp, run, lambda rec: rec["selection"]["portfolio_policy"].pop("theses"))}),
    "claim_unreadable": ("THESIS_CLAIM_UNREADABLE",
                         lambda tmp, run: {"claim": (tmp / "c.json").write_bytes(b"not json") and tmp / "c.json"}),
    "claim_entry_ids": ("THESIS_CLAIM_ENTRY_IDS_MISMATCH", lambda tmp, run: {"claim": doctored_claim(
        tmp, run, lambda rec: rec["selection"]["portfolio_policy"]["entry_ids"].reverse())}),
}


@pytest.mark.parametrize("case", sorted(CASES))
def test_each_binding_refuses_by_name_and_never_loads(case, acceptance, tmp_path):
    code, build = CASES[case]
    with pytest.raises(check_module().ThesisInputRefused) as caught:
        load(acceptance, **build(tmp_path, acceptance))
    assert caught.value.code == code, caught.value.detail


def test_lineups_moved_between_entry_ids_by_hand_are_refused_naming_the_entry_id(acceptance):
    rost = rosters(acceptance)
    first, other = _swap_two_theses(acceptance, rost)
    with pytest.raises(check_module().ThesisInputRefused) as caught:
        load(acceptance, rosters=rost)
    assert caught.value.code == "THESIS_CLAIM_DISAGREES_WITH_ROWS"
    assert first in caught.value.detail and other in caught.value.detail  # every disagreeing row is named


@pytest.mark.parametrize("version", ["v3", "v2"])
def test_a_policy_that_is_not_a_portfolio_of_theses_is_refused_not_skipped(version, acceptance, tmp_path):
    slate = acceptance.slate
    if version == "v3":
        policy, _source = _policy(slate, _thesis(slate, ["NE Kicker", "Patriots"], name="NE_WIN_CLOSE_LOW", teams=["NE"]),
                                  entry_ids=("1", "2"))
    else:  # a v2 policy declares no thesis at all
        validation, _source = _validate(slate, None, ("1", "2"), schema=POLICY_SCHEMA_VERSION_V2)
        assert validation.valid, validation.blockers()
        policy = validation.policy
    path = tmp_path / "p.json"
    path.write_bytes(policy.canonical_bytes())
    with pytest.raises(check_module().ThesisInputRefused) as caught:
        check_module().load_thesis_book(slate, ["1", "2"], {}, path, claim_path(acceptance))
    assert caught.value.code == "THESIS_POLICY_NOT_A_PORTFOLIO"


def test_a_thesis_the_policy_dropped_is_not_active_and_cannot_be_claimed(acceptance, tmp_path):
    slate = acceptance.slate
    ok = _thesis(slate, ["NE Kicker", "Patriots"], name="OK", teams=["NE"])
    gone = _thesis(slate, ["Sea Kicker"], name="GONE", teams=["SEA"])
    kicker = _people(slate)["Sea Kicker"]["underlying_id"]  # inactive for the run, so the policy drops the thesis by name
    validation, _source = _validate(slate, None, ("1", "2"), schema=POLICY_SCHEMA_VERSION_V4, theses=[ok, gone],
                                    external=(kicker,))
    assert validation.valid, validation.blockers()
    policy = validation.policy
    assert {item.name: item.status for item in policy.theses} == {"OK": "ACTIVE", "GONE": "DROPPED"}
    path = tmp_path / "p.json"
    path.write_bytes(policy.canonical_bytes())

    def claim(entries):
        record = {"selection": {"portfolio_policy": {
            "normalized_policy_sha256": policy.normalized_sha256, "entry_ids": ["1", "2"],
            "theses": {"entries": entries, "by_lineup": {}}}}}
        target = tmp_path / "claim.json"
        target.write_text(json.dumps(record), encoding="utf-8")
        return target

    check = check_module()
    assert list(check.load_thesis_book(slate, ["1", "2"], {}, path, claim({"1": "OK", "2": "OK"})).theses) == ["OK"]
    with pytest.raises(check.ThesisInputRefused) as caught:
        check.load_thesis_book(slate, ["1", "2"], {}, path, claim({"1": "OK", "2": "GONE"}))
    assert caught.value.code == "THESIS_CLAIM_UNKNOWN_THESIS"


def test_the_thesis_is_read_by_entry_id_so_an_edited_roster_keeps_its_entry_ids_thesis(acceptance):
    """Decision (f): a swap changes the canonical key, so `by_lineup[key]` would miss exactly the rows to check."""

    run = acceptance
    book = load(run)
    entry = sorted(book.entries)[0]
    roster = rosters(run)[entry]
    claim = json.loads(claim_path(run).read_text(encoding="utf-8"))["selection"]["portfolio_policy"]["theses"]
    held = {row.underlying_id for row in run.slate.players if row.dk_id in roster}
    outsider = next(row.dk_id for row in run.slate.players if row.role == "FLEX" and row.underlying_id not in held)
    edited = [*roster[:5], outsider]
    assert roster_canonical_key(run.slate, edited) not in claim["by_lineup"]
    name, _rules = book.check(entry, edited)
    assert name == book.entries[entry] == claim["entries"][entry]


def test_quarterback_depth_evidence_in_the_claim_names_a_backup_by_the_thesis_that_does_not_admit_him(acceptance, tmp_path):
    run = acceptance

    def make_every_quarterback_a_backup(record):
        record["selection"]["qb_depth_roles"]["starters_by_team"] = {"NE": "NE|QB|Nobody", "SEA": "SEA|QB|Nobody"}

    book = load(run, claim=doctored_claim(tmp_path, run, make_every_quarterback_a_backup))
    described = book.describe()
    assert described["backup_quarterback"] == "EVALUATED" and described["backup_quarterbacks_unevaluated_teams"] == []
    slate = run.slate
    roster = cpt_flex(slate, "Patriots", "Starter QB", "Alpha WR", "Lead RB", "Starting TE", "Sea Alpha WR")
    close = next(entry for entry, thesis in book.entries.items() if thesis == "NE_WIN_CLOSE_LOW")
    big = next(entry for entry, thesis in book.entries.items() if thesis == "NE_WIN_BIG")
    assert "backup_quarterback" in book.check(close, roster)[1]  # CLOSE_LOW names no quarterback
    assert "backup_quarterback" not in book.check(big, roster)[1]  # BIG's Captain set names Starter QB, so he is admitted
    # The unmodified real run has no evidence: the same roster is not judged on that rule, and says so.
    assert "backup_quarterback" not in load(run).check(close, roster)[1]


def test_a_real_run_with_a_team_bound_and_a_declared_structural_bound_names_those_rules(bounded):
    run = bounded
    book = load(run)
    for entry, roster in rosters(run).items():
        assert book.check(entry, roster) == (book.entries[entry], ())  # the engine's own rows follow
    big = next(entry for entry, thesis in book.entries.items() if thesis == "NE_WIN_BIG")
    two_quarterbacks = cpt_flex(run.slate, "Starter QB", "Sea QB", "Sea Alpha WR", "Sea Backup RB", "Sea Third RB",
                                "Seahawks")
    name, rules = book.check(big, two_quarterbacks)
    assert name == "NE_WIN_BIG"
    assert rules == ("team_bounds.NE", "structural_bounds.qb_count")


# ----- every rule name, on the synthetic DEN@KC slate -------------------------------------------------------------


def _person(slate, name: str) -> PersonBinding:
    rows = [row for row in slate.players if row.name == name]
    return PersonBinding(rows[0].underlying_id, next(r.dk_id for r in rows if r.role == "CPT"),
                         next(r.dk_id for r in rows if r.role == "FLEX"))


def _book(tmp_path, *, entry="E1", backups=frozenset(), **fields):
    slate = parse_salaries(salary_csv(tmp_path))
    thesis = ShowdownThesis(name="TH", teams=("KC", "DEN"), captain_set=(_person(slate, "KC QB"),), row_weight=1, rows=1,
                            effective_bounds=fields.pop("effective_bounds", StructuralBounds()), **fields)
    book = check_module().ThesisBook(slate=slate, theses={"TH": thesis}, entries={entry: "TH"}, backups={"TH": backups})
    return slate, book


def test_a_roster_that_follows_its_thesis_has_no_rules(tmp_path):
    _slate, book = _book(tmp_path)
    assert book.check("E1", ids(L0)) == ("TH", ())


def test_a_row_with_no_claimed_thesis_is_not_judged(tmp_path):
    slate, book = _book(tmp_path)
    assert book.check("E9", ids(L1)) is None
    unclaimed = check_module().ThesisBook(slate=slate, theses=book.theses, entries={"E1": None})
    assert unclaimed.check("E1", ids(L1)) is None


def test_the_captain_set_rule_is_named(tmp_path):
    _slate, book = _book(tmp_path)
    assert book.check("E1", ids(L1)) == ("TH", ("captain_set",))  # L1's Captain is DEN QB, the set is KC QB


def test_the_team_count_rule_is_named_per_team(tmp_path):
    _slate, book = _book(tmp_path, team_bounds=(CountBound("DEN", 3, 6),))
    assert book.check("E1", ids(L0)) == ("TH", ("team_bounds.DEN",))  # L0 holds two DEN people


def test_the_position_count_rule_is_named_per_position(tmp_path):
    _slate, book = _book(tmp_path, position_bounds=(CountBound("QB", 0, 0),))
    assert book.check("E1", ids(L0)) == ("TH", ("position_bounds.QB",))  # L0's Captain is a quarterback


def test_the_effective_structural_bounds_are_named_when_the_thesis_carries_them(tmp_path):
    bounds = StructuralBounds(qb_count=StructuralBoundRange(minimum=0, maximum=0))
    _slate, book = _book(tmp_path, effective_bounds=bounds)
    assert book.check("E1", ids(L0)) == ("TH", ("structural_bounds.qb_count",))


def test_an_excluded_person_is_named(tmp_path):
    slate = parse_salaries(salary_csv(tmp_path))
    _slate, book = _book(tmp_path, excluded_people=(_person(slate, "KC WR2"),))
    assert book.check("E1", ids(L0)) == ("TH", ("excluded_people",))


def test_a_backup_quarterback_is_named_from_the_theses_own_backup_set(tmp_path):
    slate = parse_salaries(salary_csv(tmp_path))
    backups = frozenset({_person(slate, "KC QB").underlying_id})
    _slate, book = _book(tmp_path, backups=backups)
    assert book.check("E1", ids(L0)) == ("TH", ("backup_quarterback",))


def test_rules_come_back_in_the_one_functions_order_captain_first(tmp_path):
    _slate, book = _book(tmp_path, team_bounds=(CountBound("DEN", 0, 3),), position_bounds=(CountBound("QB", 2, 2),))
    # L1's Captain is DEN QB (not in the set), it holds four DEN people (above 3) and one quarterback (not 2).
    assert book.check("E1", ids(BASE[1])) == ("TH", ("captain_set", "team_bounds.DEN", "position_bounds.QB"))


# ----- the module's own boundaries --------------------------------------------------------------------------------


def test_the_module_reads_no_projection_input_and_names_no_weather_or_roof_value():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "AvgPointsPerGame" not in text
    assert re.search(r"roof|weather", text, re.IGNORECASE) is None
