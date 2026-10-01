"""Session 23b (chunk P8, R33 and R34): a Showdown game thesis, its contract and a single-thesis build.

The card's acceptance, each proved here:
- a fixture thesis that requires a kicker Captain builds one;
- a thesis whose required Captain is inactive is dropped and named, never relaxed;
- a backup quarterback is out of the pool unless the request (the thesis) names him;
- each lineup names its thesis.
Around them: the ladder carries a thesis byte for byte and refuses a rung that changes one,
the SD4 audit recomputes every thesis rule from the roster, R29 holds against prefilled
rosters, a policy without a thesis keeps its v2 bytes, and the build is deterministic.
"""

from __future__ import annotations

import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from nfl_dfs.dk import parse_entries, parse_salaries
from nfl_dfs.gate_registry import load_gate_registry
from nfl_dfs.hashing import sha256_bytes
from nfl_dfs.participation import build_participation_contract
from nfl_dfs.portfolio_enforcement import audit_policy_assignments
from nfl_dfs.portfolio_policy import (
    POLICY_SCHEMA_VERSION_V2,
    POLICY_SCHEMA_VERSION_V3,
    canonical_decimal_json_bytes,
    portfolio_policy_template,
    salary_person_bindings,
    validate_portfolio_policy_bytes,
)
from nfl_dfs.relaxation import (
    STRUCTURE,
    Failure,
    Ladder,
    intake_failure,
    overlap_step_text,
    selection_overlap_steps,
    showdown_relaxed_controls,
    supplied_rung,
)
from nfl_dfs.selection import SelectionError, select_prior_lineups

from . import test_qb_depth_roles as depth
from .test_prior_selection import _prepared

ROOT = Path(__file__).resolve().parents[1]
SUPPLIED = ROOT / "tests" / "fixtures" / "supplied"


def _people(slate):
    """Name -> exact identity mapping (underlying, CPT and FLEX IDs) from the salary bytes."""

    by_person = {item.underlying_id: item for item in salary_person_bindings(slate)}
    return {row.name: by_person[row.underlying_id].as_mapping() for row in slate.players}


def _thesis(slate, captains, **fields):
    people = _people(slate)
    thesis = {"name": fields.pop("name", "NE_WIN_CLOSE_LOW"), "teams": fields.pop("teams", ["NE"]),
              "captain_set": [people[name] for name in captains]}
    for key in ("excluded_people", "named_backup_quarterbacks"):
        if key in fields:
            thesis[key] = [people[name] for name in fields.pop(key)]
    thesis.update(fields)
    return thesis


def _validate(slate, thesis, entry_ids=("1", "2"), *, external=(), schema=POLICY_SCHEMA_VERSION_V3, **controls):
    document = portfolio_policy_template(
        slate, entry_ids, schema_version=schema,
        controls={"structural_bounds": {}, **controls, **({"theses": [thesis]} if thesis is not None else {})})
    raw = canonical_decimal_json_bytes(document)
    return validate_portfolio_policy_bytes(raw, slate=slate, entry_ids=entry_ids,
                                           externally_excluded_people=external), raw


def _policy(slate, thesis, entry_ids=("1", "2"), **controls):
    validation, raw = _validate(slate, thesis, entry_ids, **controls)
    assert validation.valid, validation.blockers()
    return validation.policy, raw


def _select(tmp_path, thesis_builder, count=2, **kwargs):
    tmp_path.mkdir(parents=True, exist_ok=True)
    slate, model, contract, splits = _prepared(tmp_path)
    policy, raw = _policy(slate, thesis_builder(slate), tuple(str(n) for n in range(1, count + 1)))
    lineups, _scores, report = select_prior_lineups(
        slate, model, splits, contract, count=count, portfolio_policy=policy, **kwargs)
    return slate, policy, raw, lineups, report


def _row(slate, dk_id):
    return next(row for row in slate.players if row.dk_id == dk_id)


# ------------------------------------------------------------------ acceptance: a kicker Captain


def test_a_thesis_that_requires_a_kicker_captain_builds_one_and_each_lineup_names_it(tmp_path):
    slate, policy, _raw, lineups, report = _select(tmp_path, lambda s: _thesis(
        s, ["NE Kicker"], position_bounds=[{"position": "K", "minimum": 1, "maximum": 2}]))
    assert len(lineups) == 2 and len({lineup.canonical_key for lineup in lineups}) == 2
    for lineup in lineups:
        captain = _row(slate, lineup.roster[0])
        assert (captain.name, captain.role) == ("NE Kicker", "CPT")
    theses = report["portfolio_policy"]["theses"]
    assert theses["entries"] == {"1": "NE_WIN_CLOSE_LOW", "2": "NE_WIN_CLOSE_LOW"}
    assert theses["theses"][0]["status"] == "ACTIVE"
    assert "EV_ROI_OR_WIN_PROBABILITY" in theses["does_not_establish"]
    assert policy.as_mapping()["schema_version"] == "nfl_showdown_portfolio_policy_normalized_v3"


def test_the_thesis_team_and_position_bounds_and_exclusions_bind_every_lineup(tmp_path):
    slate, _policy_, _raw, lineups, _report = _select(tmp_path, lambda s: _thesis(
        s, ["Starter QB", "Alpha WR"], excluded_people=["Lead RB"],
        team_bounds=[{"team": "NE", "minimum": 4, "maximum": 5}],
        position_bounds=[{"position": "DST", "minimum": 1, "maximum": 1}]), count=3)
    for lineup in lineups:
        rows = [_row(slate, dk_id) for dk_id in lineup.roster]
        assert rows[0].name in {"Starter QB", "Alpha WR"}
        assert 4 <= sum(row.team == "NE" for row in rows) <= 5
        assert sum(row.position == "DST" for row in rows) == 1
        assert "Lead RB" not in {row.name for row in rows}


def test_the_build_is_deterministic(tmp_path):
    first = _select(tmp_path / "a", lambda s: _thesis(s, ["NE Kicker", "Patriots"]), count=3)
    second = _select(tmp_path / "b", lambda s: _thesis(s, ["NE Kicker", "Patriots"]), count=3)
    assert [lineup.roster for lineup in first[3]] == [lineup.roster for lineup in second[3]]
    assert first[1].canonical_bytes() == second[1].canonical_bytes()
    assert first[4]["portfolio_policy"]["theses"] == second[4]["portfolio_policy"]["theses"]


def test_a_thesis_never_repeats_a_prefilled_roster(tmp_path):
    slate, _policy_, _raw, best, _report = _select(tmp_path / "free", lambda s: _thesis(s, ["NE Kicker"]), count=1)
    forbidden = (tuple(best[0].roster),)
    slate, _policy_, _raw, lineups, _report = _select(
        tmp_path / "prefilled", lambda s: _thesis(s, ["NE Kicker"]), count=2, forbidden_rosters=forbidden)
    assert all(lineup.roster != forbidden[0] for lineup in lineups)
    assert _row(slate, lineups[0].roster[0]).name == "NE Kicker"


# ------------------------------------------------------------------ acceptance: an inactive Captain


def test_a_thesis_whose_only_captain_is_inactive_is_dropped_and_named_not_relaxed(tmp_path):
    slate, model, contract, splits = _prepared(tmp_path)
    kicker = _people(slate)["NE Kicker"]["underlying_id"]
    thesis = _thesis(slate, ["NE Kicker"], position_bounds=[{"position": "K", "minimum": 1, "maximum": 1}])
    # The kicker is officially inactive: the run's own exclusion, as `run-slate` passes it.
    validation, _raw = _validate(slate, thesis, external=(kicker,))
    assert validation.valid, validation.blockers()
    (dropped,) = validation.policy.theses
    assert dropped.status == "DROPPED"
    assert dropped.unavailable_captains == ((kicker, "SOURCE_OR_PARTICIPATION_PRECEDENCE"),)
    assert any(issue.code == "THESIS_DROPPED" and kicker in issue.message for issue in validation.findings)
    # Dropped, never bent: the declared thesis is unchanged in the normalized bytes.
    normalized = validation.policy.as_mapping()["controls"]["theses"][0]
    assert normalized["captain_set"] == thesis["captain_set"]
    assert normalized["position_bounds"] == thesis["position_bounds"]

    inactive = build_participation_contract(slate, operator_excluded_dk_ids=(
        _people(slate)["NE Kicker"]["cpt_dk_id"], _people(slate)["NE Kicker"]["flex_dk_id"]))
    lineups, _scores, report = select_prior_lineups(
        slate, model, splits, inactive, count=2, portfolio_policy=validation.policy)
    assert len(lineups) == 2
    assert all(kicker not in {_row(slate, dk_id).underlying_id for dk_id in lineup.roster} for lineup in lineups)
    block = report["portfolio_policy"]["theses"]
    assert block["entries"] == {"1": None, "2": None}
    assert block["theses"][0]["status"] == "DROPPED"


def test_a_validation_drop_is_named_once_by_the_ladder_even_when_no_selection_reports(tmp_path):
    slate = parse_salaries(SUPPLIED / "DKSalaries Salary CSV Showdown.csv")
    captain = _two_captains(slate)["captain_set"]
    inactive = tuple(person["underlying_id"] for person in captain)  # both Captains officially inactive
    ladder, validation, _thesis_, _slate = _supplied_ladder(tmp_path, _two_captains, external=inactive)
    assert validation.policy.theses[0].status == "DROPPED"
    assert [record["limitation_code"] for record in ladder.records] == ["THESIS_DROPPED"]
    assert ladder.records[0]["class"] == "S" and ladder.records[0]["trigger_origin"] == "POLICY_VALIDATION"
    assert all(person in ladder.records[0]["limitation_text"] for person in inactive)
    # Every SD3 attempt fails before selection; rung 4 names only the policy drop beside it.
    ladder.next(Failure("MODELED_BANK_INFEASIBILITY", STRUCTURE, "joint infeasible"))
    ladder._no_policy(ladder.current, Failure("MODELED_BANK_INFEASIBILITY", STRUCTURE, "x"), 0.0, why="the test")
    codes = [record["limitation_code"] for record in ladder.records]
    assert codes.count("THESIS_DROPPED") == 1 and codes[-1] == "RELAXATION_POLICY_DROPPED"
    texts = ladder.texts()
    assert len(texts) == len(set(texts))


def test_a_positive_cap_that_floors_to_zero_never_drops_a_thesis(tmp_path):
    slate = parse_salaries(SUPPLIED / "DKSalaries Salary CSV Showdown.csv")
    captain = _two_captains(slate)["captain_set"]
    tiny = [{**person, "fraction": Decimal("0.04")} for person in captain]  # 0.04 x 20 floors to 0 rows
    _ladder, validation, _thesis_, _slate = _supplied_ladder(
        tmp_path, _two_captains,
        max_combined_person_exposure={"default_fraction": Decimal("0.8"), "overrides": tiny})
    assert validation.policy.theses[0].status == "ACTIVE"
    assert [issue.code for issue in validation.problems] == ["PORTFOLIO_POLICY_THESIS_CAPACITY_INSUFFICIENT"]


def test_a_thesis_no_lineup_can_follow_raises_thesis_unbuildable_before_any_bank(tmp_path):
    with pytest.raises(SelectionError) as raised:
        _select(tmp_path, lambda s: _thesis(s, ["Starter QB"], team_bounds=[{"team": "NE", "minimum": 0, "maximum": 0}]))
    assert raised.value.status == "THESIS_UNBUILDABLE"
    assert raised.value.facts["thesis"] == "NE_WIN_CLOSE_LOW"


# ------------------------------------------------------------------ the ladder never relaxes a thesis


def _supplied_ladder(tmp_path, thesis_builder, *, external=(), **controls):
    slate = parse_salaries(SUPPLIED / "DKSalaries Salary CSV Showdown.csv")
    entries = parse_entries(SUPPLIED / "DKEntries CSV 20 entries.csv")
    entry_ids = tuple(item.entry_id for item in entries.authorizations)
    thesis = thesis_builder(slate) if thesis_builder is not None else None
    document = portfolio_policy_template(
        slate, entry_ids, schema_version=POLICY_SCHEMA_VERSION_V3 if thesis else POLICY_SCHEMA_VERSION_V2,
        controls={
            "max_combined_person_exposure": {"default_fraction": Decimal("0.8"), "overrides": []},
            # Two Captains at 0.5 of 20 rows fill every Captain slot, so rung 0 is valid.
            "max_captain_exposure": {"default_fraction": Decimal("0.5"), "overrides": []},
            "max_pairwise_person_overlap": 4,
            "structural_bounds": {"qb_count": {"minimum": 1, "maximum": 1}, "salary_left": {"minimum": 1, "maximum": 500},
                                  "kicker_count": 1, "dst_count": 1, "offense_against_own_dst": True},
            **controls, **({"theses": [thesis]} if thesis else {})})
    validation = validate_portfolio_policy_bytes(
        canonical_decimal_json_bytes(document), slate=slate, entry_ids=entry_ids, externally_excluded_people=external)
    assert validation.policy is not None, validation.blockers()
    ladder = Ladder(slate=slate, entries=entries, folder=tmp_path / "relaxation", registry=load_gate_registry(),
                    externally_excluded_people=external,
                    supplied=supplied_rung(validation.policy, source_path=None, source_sha256=None,
                                           normalized_path=None, normalized_sha256=validation.policy.normalized_sha256))
    return ladder, validation, thesis, slate


def _two_captains(slate):
    names = sorted({row.name for row in slate.players if row.position in {"QB", "K"}})[:2]
    # Every field declared, so the declared bytes are the bytes a rung must carry.
    return _thesis(slate, names, name="SUPPLIED_THESIS", teams=sorted({row.team for row in slate.players}),
                   team_bounds=[], position_bounds=[{"position": "K", "minimum": 1, "maximum": 2}],
                   excluded_people=[], named_backup_quarterbacks=[])


def test_every_rung_carries_the_thesis_byte_for_byte(tmp_path):
    ladder, validation, thesis, _slate = _supplied_ladder(tmp_path, _two_captains)
    policy = validation.policy
    declared = canonical_decimal_json_bytes([thesis])
    for rung in (None, 1, 2, 3):
        assert canonical_decimal_json_bytes(showdown_relaxed_controls(policy, rung)["theses"]) == declared
    # A real walk: two structural rungs, each written v3 with the thesis unchanged, never dropped.
    for expected in (1, 2):
        made = ladder.next(Failure("MODELED_BANK_INFEASIBILITY", STRUCTURE, "joint infeasible"))
        assert made is not None and made.rung == expected
        written = json.loads(Path(made.source_path).read_text(encoding="utf-8"))
        assert written["schema_version"] == POLICY_SCHEMA_VERSION_V3
        assert canonical_decimal_json_bytes(written["controls"]["theses"]) == declared
        assert made.policy.active_thesis is not None
    assert not any(record["limitation_code"] == "THESIS_DROPPED" for record in ladder.records)


def test_a_rung_that_changed_a_thesis_is_refused(tmp_path, monkeypatch):
    from nfl_dfs import relaxation

    ladder, _validation, _thesis_, _slate = _supplied_ladder(tmp_path, _two_captains)
    original = relaxation.showdown_relaxed_controls

    def bent(policy, rung):  # a rung that loosens the thesis's Captain set: the ATL@GB defect
        controls = original(policy, rung)
        if rung is not None and "theses" in controls:
            controls["theses"][0]["captain_set"] = controls["theses"][0]["captain_set"] + [
                person.as_mapping() for person in policy.people
                if person.underlying_id not in policy.active_thesis.captain_people][:1]
        return controls

    monkeypatch.setattr(relaxation, "showdown_relaxed_controls", bent)
    with pytest.raises(ValueError, match="RELAXATION_RUNG_UNBUILDABLE"):
        ladder.next(Failure("MODELED_BANK_INFEASIBILITY", STRUCTURE, "joint infeasible"))


def test_an_unbuildable_thesis_is_dropped_by_name_and_the_same_policy_builds_without_it(tmp_path):
    ladder, validation, _thesis_, _slate = _supplied_ladder(tmp_path, _two_captains)
    made = ladder.next(Failure("THESIS_UNBUILDABLE", STRUCTURE, "no lineup", {"reason": "the test's reason"}))
    assert made is not None and made.rung is None and made.policy.theses == ()
    # Not a rung: every cap and bound is what it was declared.
    before, after = showdown_relaxed_controls(validation.policy, None), showdown_relaxed_controls(made.policy, None)
    assert {key: value for key, value in before.items() if key != "theses"} == after
    assert made.policy.structural_bounds == validation.policy.structural_bounds
    (record,) = ladder.records
    assert record["limitation_code"] == "THESIS_DROPPED" and record["constraint"] == "theses.SUPPLIED_THESIS"
    assert "the test's reason" in record["limitation_text"]


def test_a_bound_widened_for_a_thesis_is_named_and_restored_when_the_thesis_drops(tmp_path):
    def kickers(slate):
        return {**_two_captains(slate), "position_bounds": [{"position": "K", "minimum": 2, "maximum": 2}]}

    ladder, validation, _thesis_, _slate = _supplied_ladder(tmp_path, kickers)
    assert validation.policy.structural_bounds.kicker_count_maximum == 2  # declared 1
    (named,) = ladder.records
    assert named["limitation_code"] == "PORTFOLIO_POLICY_THESIS_OVERRIDES_BOUND"
    assert "kicker_count 1 to 2" in named["limitation_text"]
    made = ladder.next(Failure("THESIS_UNBUILDABLE", STRUCTURE, "no lineup", {"reason": "the test's reason"}))
    assert made.policy.theses == () and made.policy.structural_bounds.kicker_count_maximum == 1
    assert [record["limitation_code"] for record in ladder.records] == [
        "PORTFOLIO_POLICY_THESIS_OVERRIDES_BOUND", "THESIS_DROPPED"]


def test_rung_4_names_each_thesis_it_drops(tmp_path):
    ladder, _validation, _thesis_, _slate = _supplied_ladder(tmp_path, _two_captains)
    failure = Failure("MODELED_BANK_INFEASIBILITY", STRUCTURE, "joint infeasible")
    floor = ladder._no_policy(ladder.current, failure, 0.0, why="the test")
    assert floor is not None and floor.policy is None
    assert [record["limitation_code"] for record in ladder.records] == ["THESIS_DROPPED", "RELAXATION_POLICY_DROPPED"]
    assert ladder.records[0]["constraint"] == "theses.SUPPLIED_THESIS"


# ------------------------------------------------------------------ caps give way, the thesis does not


def test_captain_caps_that_starve_the_thesis_are_an_s_issue_the_ladder_loosens(tmp_path):
    slate, *_rest = _prepared(tmp_path)
    validation, _raw = _validate(slate, _thesis(slate, ["NE Kicker"]), ("1", "2", "3", "4", "5"),
                                 max_captain_exposure={"default_fraction": Decimal("0.4"), "overrides": []})
    codes = [issue.code for issue in validation.problems]
    assert codes == ["PORTFOLIO_POLICY_THESIS_CAPACITY_INSUFFICIENT"]
    assert intake_failure(codes, load_gate_registry()).kind == STRUCTURE


def test_a_count_bound_the_thesis_contradicts_gives_way_by_the_least_step(tmp_path):
    slate, *_rest = _prepared(tmp_path)
    thesis = _thesis(slate, ["NE Kicker"], position_bounds=[{"position": "K", "minimum": 2, "maximum": 2},
                                                            {"position": "QB", "minimum": 0, "maximum": 0}])
    validation, _raw = _validate(slate, thesis, structural_bounds={"kicker_count": 1, "qb_count": {"minimum": 1, "maximum": 1}})
    assert validation.valid, validation.blockers()
    bounds = validation.policy.structural_bounds
    assert (bounds.kicker_count_maximum, bounds.qb_count.minimum, bounds.qb_count.maximum) == (2, 0, 1)
    assert any(issue.code == "PORTFOLIO_POLICY_THESIS_OVERRIDES_BOUND" for issue in validation.findings)


@pytest.mark.parametrize("mutate, schema, code", [
    (lambda thesis, people: {**thesis, "captain_set": []}, POLICY_SCHEMA_VERSION_V3, "PORTFOLIO_POLICY_THESIS_INVALID"),
    (lambda thesis, people: {**thesis, "excluded_people": thesis["captain_set"]}, POLICY_SCHEMA_VERSION_V3,
     "PORTFOLIO_POLICY_THESIS_INVALID"),
    (lambda thesis, people: {**thesis, "named_backup_quarterbacks": [people["NE Kicker"]]}, POLICY_SCHEMA_VERSION_V3,
     "PORTFOLIO_POLICY_THESIS_INVALID"),
    (lambda thesis, people: {**thesis, "teams": ["DAL"]}, POLICY_SCHEMA_VERSION_V3, "PORTFOLIO_POLICY_THESIS_INVALID"),
    (lambda thesis, people: {**thesis, "position_bounds": [{"position": "K", "minimum": 2, "maximum": 1}]},
     POLICY_SCHEMA_VERSION_V3, "PORTFOLIO_POLICY_THESIS_INVALID"),
    (lambda thesis, people: {**thesis, "team_bounds": [{"team": "NE", "minimum": 4}, {"team": "SEA", "minimum": 3}]},
     POLICY_SCHEMA_VERSION_V3, "PORTFOLIO_POLICY_THESIS_INVALID"),
    (lambda thesis, people: {**thesis, "odds": "likely"}, POLICY_SCHEMA_VERSION_V3, "PORTFOLIO_POLICY_UNKNOWN_FIELD"),
    (lambda thesis, people: thesis, POLICY_SCHEMA_VERSION_V2,
     "PORTFOLIO_POLICY_UNKNOWN_FIELD,PORTFOLIO_POLICY_THESIS_INVALID"),
])
def test_a_malformed_thesis_is_refused_by_name(tmp_path, mutate, schema, code):
    slate, *_rest = _prepared(tmp_path)
    thesis = mutate(_thesis(slate, ["NE Kicker"]), _people(slate))
    validation, _raw = _validate(slate, thesis, schema=schema)
    assert [issue.code for issue in validation.problems] == code.split(",")


def test_two_theses_wait_for_session_23c(tmp_path):
    slate, *_rest = _prepared(tmp_path)
    thesis = _thesis(slate, ["NE Kicker"])
    document = portfolio_policy_template(slate, ("1",), schema_version=POLICY_SCHEMA_VERSION_V3,
                                         controls={"theses": [thesis, {**thesis, "name": "OTHER"}]})
    validation = validate_portfolio_policy_bytes(canonical_decimal_json_bytes(document), slate=slate, entry_ids=("1",))
    assert [issue.code for issue in validation.problems] == ["PORTFOLIO_POLICY_THESIS_INVALID"]
    assert "23c" in validation.problems[0].message


def test_a_policy_without_a_thesis_keeps_its_v2_normalized_bytes(tmp_path):
    slate, *_rest = _prepared(tmp_path)
    validation, _raw = _validate(slate, None, schema=POLICY_SCHEMA_VERSION_V2)
    mapping = validation.policy.as_mapping()
    assert mapping["schema_version"] == "nfl_showdown_portfolio_policy_normalized_v2"
    assert "theses" not in mapping["controls"]


# ------------------------------------------------------------------ the audit recomputes the thesis


def _audit(tmp_path, slate, policy, raw, pairs, selector_summary=None):
    artifact = ("Entry ID,CPT,FLEX,FLEX,FLEX,FLEX,FLEX\n"
                + "".join(",".join((entry, *roster)) + "\n" for entry, roster in pairs)).encode("utf-8")
    normalized = policy.canonical_bytes()
    entry_bytes = b"exact entry bytes"
    return audit_policy_assignments(
        slate=slate, policy=policy, assignments=pairs, salary_bytes=(tmp_path / "DKSalaries.csv").read_bytes(),
        entry_bytes=entry_bytes, expected_entry_sha256=sha256_bytes(entry_bytes), source_policy_bytes=raw,
        expected_source_policy_sha256=sha256_bytes(raw), normalized_policy_bytes=normalized,
        expected_normalized_policy_sha256=sha256_bytes(normalized), assignment_artifact_bytes=artifact,
        expected_assignment_artifact_sha256=sha256_bytes(artifact), selector_summary=selector_summary)


def test_the_audit_passes_a_thesis_build_and_names_each_entry_s_thesis(tmp_path):
    slate, policy, raw, lineups, _report = _select(tmp_path, lambda s: _thesis(s, ["NE Kicker"]))
    audit = _audit(tmp_path, slate, policy, raw, [(str(i), lineup.roster) for i, lineup in enumerate(lineups, 1)])
    assert audit.passed, audit.problems
    entries = audit.as_report()["theses"]["entries"]
    assert entries == {"1": {"thesis": "NE_WIN_CLOSE_LOW", "follows": True, "broken_rules": []},
                       "2": {"thesis": "NE_WIN_CLOSE_LOW", "follows": True, "broken_rules": []}}


def test_the_audit_catches_a_roster_that_breaks_the_thesis(tmp_path):
    slate, policy, raw, lineups, _report = _select(
        tmp_path, lambda s: _thesis(s, ["Starter QB"], position_bounds=[{"position": "K", "minimum": 0, "maximum": 0}]))
    # A roster another thesis built: a kicker Captain this thesis neither opens nor allows.
    other = _policy(slate, _thesis(slate, ["NE Kicker"]), ("1",))[0]
    _slate, model, contract, splits = _prepared(tmp_path)
    kicker_built, _scores, _report = select_prior_lineups(slate, model, splits, contract, count=1, portfolio_policy=other)
    audit = _audit(tmp_path, slate, policy, raw, [("1", kicker_built[0].roster), ("2", lineups[1].roster)])
    rules = {problem.rsplit("rule=", 1)[1] for problem in audit.problems
             if problem.startswith("PORTFOLIO_AUDIT_THESIS_VIOLATED:entry=1")}
    assert {"captain_set", "position_bounds.K"} <= rules
    entries = audit.as_report()["theses"]["entries"]
    assert entries["1"]["follows"] is False and entries["2"]["follows"] is True


# ------------------------------------------------------------------ acceptance: backup quarterbacks


def _depth_select(tmp_path, thesis_builder, *, package=True, count=2):
    tmp_path.mkdir(parents=True, exist_ok=True)
    slate, model, contract, splits = depth._setup(tmp_path)
    evidence = depth._package(tmp_path / "qb", slate, depth._orders()) if package else None
    policy, _raw = _policy(slate, thesis_builder(slate), tuple(str(n) for n in range(1, count + 1)))
    lineups, _scores, report = select_prior_lineups(
        slate, model, splits, contract, count=count, portfolio_policy=policy,
        qb_depth_role_evidence_json=evidence, as_of=depth.AS_OF)
    return slate, lineups, report


def _both_quarterbacks(slate, **fields):
    return _thesis(slate, ["KC Alpha WR"], name="SHOOTOUT", teams=["KC", "DEN"],
                   position_bounds=[{"position": "QB", "minimum": 2, "maximum": 2}], **fields)


def test_a_backup_quarterback_is_out_of_a_thesis_pool_by_depth_evidence(tmp_path):
    slate, lineups, report = _depth_select(tmp_path, _both_quarterbacks, count=3)
    backup = depth._person(slate, "KC Backup QB")
    assert all(backup not in {_row(slate, dk_id).underlying_id for dk_id in lineup.roster} for lineup in lineups)
    assert report["portfolio_policy"]["theses"]["backup_quarterbacks_excluded"] == [backup]
    assert report["portfolio_policy"]["theses"]["backup_quarterbacks_unevaluated_teams"] == []


def test_a_backup_quarterback_the_thesis_names_stays_in(tmp_path):
    # With the Denver starter out of the thesis, two quarterbacks are possible only with the backup.
    with pytest.raises(SelectionError) as raised:
        _depth_select(tmp_path / "unnamed", lambda s: _both_quarterbacks(s, excluded_people=["DEN Starter QB"]))
    assert raised.value.status == "THESIS_UNBUILDABLE"
    slate, lineups, report = _depth_select(tmp_path / "named", lambda s: _both_quarterbacks(
        s, excluded_people=["DEN Starter QB"], named_backup_quarterbacks=["KC Backup QB"]))
    backup = depth._person(slate, "KC Backup QB")
    assert all(backup in {_row(slate, dk_id).underlying_id for dk_id in lineup.roster} for lineup in lineups)
    assert report["portfolio_policy"]["theses"]["backup_quarterbacks_excluded"] == []


def test_with_no_depth_evidence_no_quarterback_is_guessed_out_and_the_gap_is_named(tmp_path):
    slate, lineups, report = _depth_select(tmp_path, _both_quarterbacks, package=False, count=3)
    block = report["portfolio_policy"]["theses"]
    assert block["backup_quarterbacks_excluded"] == []
    assert block["backup_quarterbacks_unevaluated_teams"] == ["DEN", "KC"]
    (step,) = selection_overlap_steps({"selection": {"selection": report}})
    assert overlap_step_text(step).startswith("THESIS_BACKUP_QB_UNEVALUATED:thesis SHOOTOUT: no quarterback depth")
    assert lineups


def test_the_audit_recomputes_the_backup_rule_from_the_depth_report(tmp_path):
    slate, model, contract, splits = depth._setup(tmp_path)
    evidence = depth._package(tmp_path / "qb", slate, depth._orders())
    # A roster that holds the backup, built under a thesis that names him.
    named, _raw = _policy(slate, _both_quarterbacks(
        slate, excluded_people=["DEN Starter QB"], named_backup_quarterbacks=["KC Backup QB"]), ("1",))
    holding, _scores, report = select_prior_lineups(
        slate, model, splits, contract, count=1, portfolio_policy=named,
        qb_depth_role_evidence_json=evidence, as_of=depth.AS_OF)
    backup = depth._person(slate, "KC Backup QB")
    assert backup in {_row(slate, dk_id).underlying_id for dk_id in holding[0].roster}
    # Audited against a thesis that does not name him, with the same depth report: refused.
    strict, strict_raw = _policy(slate, _both_quarterbacks(slate), ("1",))
    audit = _audit(tmp_path, slate, strict, strict_raw, [("1", holding[0].roster)], selector_summary=report)
    assert any(problem.endswith("rule=backup_quarterback") for problem in audit.problems)
    assert audit.as_report()["theses"]["backup_quarterbacks_excluded"] == [backup]


# ------------------------------------------------------------------ the generator


def test_the_generator_writes_v3_and_keeps_a_thesis_kicker_captain_open(tmp_path):
    slate = parse_salaries(SUPPLIED / "DKSalaries Salary CSV Showdown.csv")
    kicker = next(row for row in slate.players if row.position == "K")
    thesis_path = tmp_path / "thesis.json"
    thesis_path.write_text(json.dumps({"name": "KICKER_CAPTAIN", "teams": [kicker.team],
                                       "captain_set": [kicker.underlying_id]}), encoding="utf-8")
    out = tmp_path / "policy.json"
    subprocess.run([sys.executable, str(ROOT / "scripts" / "make_showdown_policy.py"),
                    "--salaries", str(SUPPLIED / "DKSalaries Salary CSV Showdown.csv"),
                    "--entries", str(SUPPLIED / "DKEntries CSV 20 entries.csv"), "--out", str(out),
                    "--thesis", str(thesis_path), "--captain-default", "1", "--combined-default", "1"], check=True, capture_output=True,
                   env={"PYTHONPATH": str(ROOT / "src"), "PATH": "/usr/bin:/bin"})
    document = json.loads(out.read_text(encoding="utf-8"))
    assert document["schema_version"] == POLICY_SCHEMA_VERSION_V3
    zeroed = {item["underlying_id"] for item in document["controls"]["max_captain_exposure"]["overrides"]
              if item["fraction"] == 0}
    assert kicker.underlying_id not in zeroed
    entries = parse_entries(SUPPLIED / "DKEntries CSV 20 entries.csv")
    validation = validate_portfolio_policy_bytes(out.read_bytes(), slate=slate,
                                                 entry_ids=[item.entry_id for item in entries.authorizations])
    assert validation.valid, validation.blockers()
    assert validation.policy.active_thesis.captain_people == {kicker.underlying_id}
