"""Session 23e (P2, Classic half): structural hygiene bounds and the share cap.

`nfl_classic_portfolio_policy_c2_v2` adds `controls.structural_bounds`
(`salary_left`, `offense_against_own_dst`) and `controls.max_person_share`; v1 is
never mutated. The bounds bind the candidate bank as real MILP rows, are
recomputed from roster bytes by the audit and the C3 review, and fold into the
Classic rung table.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from nfl_dfs.classic_portfolio import (
    audit_classic_portfolio,
    build_classic_candidate_bank,
    solve_classic_portfolio,
)
from nfl_dfs.classic_portfolio_policy import (
    OPEN_CLASSIC_STRUCTURAL_BOUNDS,
    POLICY_SCHEMA_VERSION,
    POLICY_SCHEMA_VERSION_V2,
    classic_portfolio_policy_template,
    parse_normalized_classic_policy_bytes,
    person_share_maximum,
    validate_classic_portfolio_policy_bytes,
)
from nfl_dfs.hashing import sha256_bytes
from nfl_dfs.relaxation import (
    classic_relaxed_controls,
    classic_rung_controls,
    classic_structural_bounds,
    classic_table_share,
)

from .test_classic_portfolio_c2 import _audit, _objective, _policy, _slate

# The synthetic slate's rosters leave about $11,000 to $19,000 unspent.
BAND = {"salary_left": {"minimum": 14_000, "maximum": 18_000}, "offense_against_own_dst": True}


def _validate(controls: dict[str, object], count: int = 5, *, schema_version: str | None = None):
    slate = _slate()
    entry_ids = tuple(f"E{index:03d}" for index in range(1, count + 1))
    document = classic_portfolio_policy_template(
        slate, entry_ids, entry_sha256=sha256_bytes(b"entry"), controls=controls, schema_version=schema_version)
    raw = json.dumps(document).encode("utf-8")
    return validate_classic_portfolio_policy_bytes(
        raw, slate=slate, entry_ids=entry_ids, entry_sha256=sha256_bytes(b"entry"))


# ------------------------------------------------------------------ the contract


def test_v1_is_unchanged_and_normalizes_with_both_controls_open() -> None:
    validation = _validate({})
    assert validation.valid and validation.policy is not None
    policy = validation.policy
    assert policy.structural_bounds == OPEN_CLASSIC_STRUCTURAL_BOUNDS and policy.max_person_share is None
    assert json.loads(json.dumps(classic_portfolio_policy_template(
        _slate(), ("E1",), entry_sha256="x")))["schema_version"] == POLICY_SCHEMA_VERSION
    assert all(bound.maximum_entries == policy.entry_count for bound in policy.player_bounds)


def test_a_v2_document_carries_structural_bounds_and_the_share_and_round_trips() -> None:
    validation = _validate({"structural_bounds": BAND, "max_person_share": 0.8}, count=5)
    assert validation.valid, validation.blockers()
    policy = validation.policy
    assert policy is not None
    assert classic_portfolio_policy_template(
        _slate(), ("E1",), entry_sha256="x", controls={"max_person_share": 0.8}
    )["schema_version"] == POLICY_SCHEMA_VERSION_V2
    assert policy.structural_bounds.salary_left.minimum == 14_000 and policy.structural_bounds.offense_against_own_dst
    assert policy.max_person_share == Decimal("0.8") and policy.max_person_share_entries == 4
    controls = policy.as_mapping()["controls"]
    assert controls["max_person_share"] == {"fraction": Decimal("0.8"), "maximum_entries": 4}
    assert controls["structural_bounds"]["salary_left"] == {"minimum": 14_000, "maximum": 18_000}
    assert parse_normalized_classic_policy_bytes(policy.canonical_bytes()) == policy


def test_the_share_is_the_default_maximum_of_a_person_with_no_explicit_row() -> None:
    slate = _slate()
    chosen = slate.players[0]
    explicit = {"underlying_id": chosen.underlying_id, "dk_id": chosen.dk_id,
                "minimum_entries": 0, "maximum_entries": 5, "hard": True}
    policy = _validate({"max_person_share": 0.6, "player_exposure_bounds": [explicit]}, count=5).policy
    assert policy is not None and person_share_maximum(Decimal("0.6"), 5) == 3
    maxima = {bound.entity_id: bound.maximum_entries for bound in policy.player_bounds}
    assert maxima[chosen.underlying_id] == 5  # an explicit row wins, as in Showdown
    assert {value for person, value in maxima.items() if person != chosen.underlying_id} == {3}


def test_a_v1_document_may_not_declare_the_v2_controls() -> None:
    for controls in ({"structural_bounds": BAND}, {"max_person_share": 0.8}):
        validation = _validate(controls, schema_version=POLICY_SCHEMA_VERSION)
        assert not validation.valid
        assert "CLASSIC_POLICY_STRUCTURAL_BOUND_TYPE_INVALID" in {issue.code for issue in validation.problems}


@pytest.mark.parametrize(("controls", "code"), [
    ({"structural_bounds": {"salary_left": {"minimum": 900, "maximum": 100}}}, "CLASSIC_POLICY_STRUCTURAL_BOUND_CONTRADICTORY"),
    ({"structural_bounds": {"salary_left": {"minimum": -1}}}, "CLASSIC_POLICY_STRUCTURAL_BOUND_OUT_OF_RANGE"),
    ({"structural_bounds": {"salary_left": {"maximum": 1.5}}}, "CLASSIC_POLICY_STRUCTURAL_BOUND_INTEGER_REQUIRED"),
    ({"structural_bounds": {"offense_against_own_dst": "yes"}}, "CLASSIC_POLICY_STRUCTURAL_BOUND_TYPE_INVALID"),
    ({"max_person_share": 0}, "CLASSIC_POLICY_MAX_PERSON_SHARE_INVALID"),
    ({"max_person_share": 1.2}, "CLASSIC_POLICY_MAX_PERSON_SHARE_INVALID"),
    ({"max_person_share": "0.8"}, "CLASSIC_POLICY_MAX_PERSON_SHARE_INVALID"),
    ({"max_person_share": 0.1}, "CLASSIC_POLICY_MAX_PERSON_SHARE_INVALID"),  # floors to no entry of 5
])
def test_bad_structural_or_share_values_are_refused_with_a_named_code(controls, code) -> None:
    validation = _validate({**controls}, schema_version=POLICY_SCHEMA_VERSION_V2)
    assert not validation.valid and code in {issue.code for issue in validation.problems}


def test_every_new_code_is_registered() -> None:
    from nfl_dfs.gate_registry import load_gate_registry

    registry = load_gate_registry()
    for code in ("CLASSIC_POLICY_MAX_PERSON_SHARE_INVALID", "CLASSIC_POLICY_STRUCTURAL_BOUND_CONTRADICTORY",
                 "CLASSIC_POLICY_STRUCTURAL_BOUND_INTEGER_REQUIRED", "CLASSIC_POLICY_STRUCTURAL_BOUND_OUT_OF_RANGE",
                 "CLASSIC_POLICY_STRUCTURAL_BOUND_TYPE_INVALID", "CLASSIC_AUDIT_STRUCTURAL_BOUND_VIOLATED",
                 "CLASSIC_C3_STRUCTURAL_BOUND_VIOLATED"):
        assert registry.family_of(code)


# ------------------------------------------------------ enforcement as MILP rows


def test_the_bank_holds_only_rosters_inside_the_bounds_and_the_bounds_are_real_rows() -> None:
    slate, policy, _source, _entry = _policy(5, controls={"structural_bounds": BAND})
    bank = build_classic_candidate_bank(slate, _objective(slate), policy)
    assert bank.candidates
    assert all(policy.structural_bounds.violations(slate, candidate.roster) == () for candidate in bank.candidates)
    by_id = {row.dk_id: row for row in slate.players}
    for candidate in bank.candidates:
        rows = [by_id[dk_id] for dk_id in candidate.roster]
        assert 14_000 <= slate.salary_cap - sum(row.salary for row in rows) <= 18_000
        dst_teams = {row.team for row in rows if row.position == "DST"}
        assert not [row for row in rows if row.team in dst_teams and row.position != "DST"]
    # Control: the same slate with the bounds open does propose rosters outside them.
    slate, open_policy, _source, _entry = _policy(5)
    open_bank = build_classic_candidate_bank(slate, _objective(slate), open_policy)
    assert any(policy.structural_bounds.violations(slate, candidate.roster) for candidate in open_bank.candidates)
    selection = solve_classic_portfolio(policy, bank)
    assert selection.passed


def test_bounds_no_roster_can_meet_fail_closed_with_a_named_bank_status() -> None:
    slate, policy, _source, _entry = _policy(
        3, controls={"structural_bounds": {"salary_left": {"minimum": 0, "maximum": 1000}}})
    bank = build_classic_candidate_bank(slate, _objective(slate), policy)
    assert not bank.candidates and bank.status == "STRUCTURAL_INFEASIBILITY"
    assert solve_classic_portfolio(policy, bank).passed is False


def test_the_audit_recomputes_the_bounds_from_roster_bytes_and_reports_the_share() -> None:
    slate, open_policy, _source, entry_bytes = _policy(5)
    bank = build_classic_candidate_bank(slate, _objective(slate), open_policy)
    selection = solve_classic_portfolio(open_policy, bank)
    # The same bank and assignment audited under a policy the rosters break.
    _slate_again, strict, strict_source, strict_entry = _policy(
        5, controls={"structural_bounds": {"salary_left": {"minimum": 0, "maximum": 1000}}})
    audit, _bank_bytes, _assignment = _audit(slate, strict, strict_source, strict_entry, bank, selection)
    assert not audit.passed
    assert any(problem.startswith("CLASSIC_AUDIT_STRUCTURAL_BOUND_VIOLATED:") and problem.endswith(":salary_left")
               for problem in audit.problems)
    report = audit.as_report()
    assert set(report["structural_bound_violations"]) == set(strict.entry_ids)
    assert report["max_person_share"]["entries"] == 5 and report["max_person_share"]["people"]
    assert report["max_person_share"]["declared_fraction"] is None


def test_the_audit_holds_the_share_cap_and_names_the_declared_share_and_the_top_person() -> None:
    slate, open_policy, _source, _entry = _policy(5)
    bank = build_classic_candidate_bank(slate, _objective(slate), open_policy)
    selection = solve_classic_portfolio(open_policy, bank)
    assert selection.passed
    # A share of 1 caps nobody: the audit passes and names what it declared.
    _s, whole, whole_source, whole_entry = _policy(5, controls={"max_person_share": 1})
    audit, _b, _a = _audit(slate, whole, whole_source, whole_entry, bank, selection)
    assert audit.passed, audit.problems
    share = audit.max_person_share
    assert share["declared_fraction"] == "1" and share["declared_maximum_entries"] == 5
    assert share["people"] and share["share_percentage"] <= 100.0
    # The same rosters under a 0.2 share (one entry in five) break the person bound.
    _s, tight, tight_source, tight_entry = _policy(5, controls={"max_person_share": 0.2})
    audit, _b, _a = _audit(slate, tight, tight_source, tight_entry, bank, selection)
    assert not audit.passed
    assert any(problem.startswith("CLASSIC_AUDIT_PLAYER_BOUND:") for problem in audit.problems)
    assert audit.max_person_share["declared_maximum_entries"] == 1 and audit.max_person_share["share_percentage"] > 20.0


# ------------------------------------------------------------- the rung table


def test_the_rung_table_drops_the_bounds_in_the_briefs_order_and_the_share_last() -> None:
    assert classic_structural_bounds(0).salary_left.maximum == 1000 and classic_structural_bounds(0).offense_against_own_dst
    assert classic_structural_bounds(1).salary_left.maximum is None and classic_structural_bounds(1).offense_against_own_dst
    assert classic_structural_bounds(2).open and classic_structural_bounds(3).open
    slate = _slate()
    for rung in range(4):
        controls = classic_rung_controls(slate, 5, rung)
        assert controls["max_person_share"] == 0.8  # the ceiling, on every policy rung
    assert classic_rung_controls(slate, 2, 0)["max_person_share"] is None  # two entries cannot be capped
    assert [classic_table_share(rung) for rung in range(4)] == [
        Decimal("0.5"), Decimal("0.5"), Decimal("0.65"), Decimal("0.80")]


def test_a_relaxation_never_tightens_the_bounds_or_the_share() -> None:
    slate = _slate()
    policy = _validate(classic_rung_controls(slate, 5, 0), count=5).policy
    assert policy is not None
    previous_share, previous_open = Decimal(1), 0
    for rung in range(4):
        relaxed = classic_relaxed_controls(policy, rung)
        assert relaxed["max_person_share"] is not None
        assert Decimal(str(relaxed["max_person_share"])) >= previous_share or rung == 0
        previous_share = Decimal(str(relaxed["max_person_share"]))
        bounds = relaxed["structural_bounds"]
        opened = int(bounds["salary_left"]["maximum"] is None) + int(not bounds["offense_against_own_dst"])
        assert opened >= previous_open
        previous_open = opened
    assert previous_open == 2


def test_a_hand_written_share_loosens_with_the_rung_and_a_policy_without_one_keeps_none() -> None:
    hand = _validate({"max_person_share": 0.4}, count=5).policy
    assert hand is not None
    assert [classic_relaxed_controls(hand, rung)["max_person_share"] for rung in range(4)] == [0.5, 0.5, 0.65, 0.8]
    assert classic_relaxed_controls(hand, None)["max_person_share"] == 0.4
    plain = _validate({}, count=5).policy
    assert plain is not None
    assert all(classic_relaxed_controls(plain, rung)["max_person_share"] is None for rung in range(4))
    assert all(classic_relaxed_controls(plain, rung)["structural_bounds"] == OPEN_CLASSIC_STRUCTURAL_BOUNDS.as_mapping()
               for rung in range(4))


# --------------------------------------------- the generator and the supplied fixture

from pathlib import Path  # noqa: E402

from nfl_dfs.classic_portfolio import _Enumerator  # noqa: E402
from nfl_dfs.dk import parse_entries, parse_salaries  # noqa: E402

from .test_classic_policy_generator import ENTRIES, SALARY, _generator, _run  # noqa: E402

TWENTY = Path(SALARY).parent / "DKEntries CSV 20 entries.csv"


def test_the_generator_writes_v2_with_the_bounds_and_the_share_and_says_so(tmp_path, capsys) -> None:
    module = _generator()
    out = tmp_path / "policy.json"
    from datetime import timedelta

    from .test_classic_policy_generator import IMPROVEMENT_STOP

    code = module.main(["--salaries", str(SALARY), "--entries", str(TWENTY), "--out", str(out), "--rung", "0",
                        "--host-rates", str(tmp_path / "absent.json")],
                       wall=lambda: IMPROVEMENT_STOP - timedelta(seconds=86_400.0))
    assert code == 0
    printed = capsys.readouterr().out
    assert "salary left:       $0 to $1,000" in printed and "no offense with own DST: on" in printed
    assert "max person share:  <= 80% of entries (16/20); the last cap to go" in printed
    document = json.loads(out.read_text(encoding="utf-8"))
    assert document["schema_version"] == POLICY_SCHEMA_VERSION_V2
    assert document["controls"]["max_person_share"] == 0.8
    assert document["controls"]["structural_bounds"] == {
        "salary_left": {"minimum": 0, "maximum": 1000}, "offense_against_own_dst": True}
    slate, entries = parse_salaries(SALARY), parse_entries(TWENTY)
    validation = validate_classic_portfolio_policy_bytes(
        out.read_bytes(), slate=slate, entry_ids=tuple(item.entry_id for item in entries.authorizations),
        entry_sha256=entries.raw_hash)
    assert validation.valid, validation.blockers()
    policy = validation.policy
    assert policy is not None and policy.max_person_share_entries == 16
    assert max(bound.maximum_entries for bound in policy.player_bounds) == 10  # rung 0's explicit 50% still binds


def test_rung_zero_on_the_supplied_classic_pool_proposes_only_rosters_that_pass_hygiene() -> None:
    """The card's acceptance on the fixture the repo has: 100% hygiene at rung 0, and an
    impossible bound fails closed. (A full bank on this 719-person pool measures 4 to 20 s a
    candidate on this host, Session 47, so the strata are driven directly.)"""

    slate, entries = parse_salaries(SALARY), parse_entries(TWENTY)
    entry_ids = tuple(item.entry_id for item in entries.authorizations)
    document = classic_portfolio_policy_template(
        slate, entry_ids, entry_sha256=entries.raw_hash, controls=classic_rung_controls(slate, len(entry_ids), 0))
    validation = validate_classic_portfolio_policy_bytes(
        json.dumps(document).encode("utf-8"), slate=slate, entry_ids=entry_ids, entry_sha256=entries.raw_hash)
    assert validation.valid and validation.policy is not None
    policy = validation.policy
    objective = {row.dk_id: row.salary / 1000.0 + (sum(map(ord, row.underlying_id)) % 97) / 50.0 for row in slate.players}
    enumerator = _Enumerator(slate, policy, objective, excluded_ids=())
    enumerator.enumerate(kind="top_k_fill", target=6)
    enumerator.expand_validated_neighbors(kind="policy_feasible_chain", target=6)
    assert len(enumerator.candidates) >= 8
    assert all(policy.structural_bounds.violations(slate, candidate.roster) == () for candidate in enumerator.candidates)
    for candidate in enumerator.candidates:
        left = slate.salary_cap - sum(row.salary for row in slate.players if row.dk_id in candidate.roster)
        assert 0 <= left <= 1000
    # An impossible band fails closed: the solver proves it, no candidate is proposed.
    impossible = classic_portfolio_policy_template(
        slate, entry_ids, entry_sha256=entries.raw_hash,
        controls={"structural_bounds": {"salary_left": {"minimum": 50_000, "maximum": 50_000}}})
    broken = validate_classic_portfolio_policy_bytes(
        json.dumps(impossible).encode("utf-8"), slate=slate, entry_ids=entry_ids, entry_sha256=entries.raw_hash)
    assert broken.valid and broken.policy is not None
    stopped = _Enumerator(slate, broken.policy, objective, excluded_ids=())
    stratum = stopped.enumerate(kind="top_k_fill", target=3)
    assert stratum.termination == "MODEL_INFEASIBLE" and not stopped.candidates


def test_the_c3_review_recomputes_the_bounds_and_reports_the_share_with_the_person_named(tmp_path) -> None:
    from nfl_dfs.classic_portfolio_policy import write_normalized_classic_portfolio_policy
    from nfl_dfs.hashing import sha256_file
    from nfl_dfs.prior_review import run_prior_review
    from nfl_dfs.projection import build_projection_package

    from .test_classic_prior_review import AS_OF, _fixture

    salary, entry, package, role, status, _inactive = _fixture(tmp_path / "fixture", entries=3)
    slate, entries = parse_salaries(salary), parse_entries(entry)
    entry_ids = tuple(item.entry_id for item in entries.authorizations)
    document = classic_portfolio_policy_template(
        slate, entry_ids, entry_sha256=entries.raw_hash,
        controls={"structural_bounds": {"offense_against_own_dst": True}, "max_person_share": 1})
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(json.dumps(document), encoding="utf-8")
    validation = validate_classic_portfolio_policy_bytes(
        policy_path.read_bytes(), slate=slate, entry_ids=entry_ids, entry_sha256=entries.raw_hash)
    assert validation.valid and validation.policy is not None
    normalized = write_normalized_classic_portfolio_policy(tmp_path / "policy.normalized.json", validation.policy)
    result = run_prior_review(
        salary_csv=salary, entry_csv=entry, label="classic-hygiene", as_of=AS_OF,
        run_root=tmp_path / "run", output_root=tmp_path / "out", prior_package_dir=package, build_priors=True,
        official_status_csv=status, offensive_role_evidence_json=role, portfolio_policy=validation.policy,
        portfolio_policy_source_path=policy_path, portfolio_policy_source_sha256=sha256_file(policy_path),
        portfolio_policy_normalized_path=normalized, portfolio_policy_normalized_sha256=sha256_file(normalized),
        project=build_projection_package)
    assert not result.blocked, result.blockers
    assert result.reports["classic_portfolio_audit"]["status"] == "PASS"
    assert result.reports["classic_portfolio_audit"]["max_person_share"]["declared_maximum_entries"] == 3
    review = json.loads(Path(result.artifacts["readable_review_json"]).read_text(encoding="utf-8"))
    exposure = review["exposure"]
    assert exposure["structural_bounds"]["offense_against_own_dst"] is True
    share = exposure["max_person_share"]
    assert share["entries"] == 3 and share["people"] and share["declared_fraction"] == "1"
    assert all(entry["structural_bound_violations"] == [] for entry in review["entries"])
