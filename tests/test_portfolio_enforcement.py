"""SD4 bounded joint enforcement and independent final-assignment audit."""

from __future__ import annotations

import json
from dataclasses import replace
from types import SimpleNamespace

import highspy
import pytest

from nfl_dfs.hashing import sha256_bytes
from nfl_dfs.portfolio_enforcement import (
    CandidateBank,
    PolicyCandidate,
    audit_policy_assignments,
    build_policy_candidate_bank,
    exact_assignments_for_entries,
    solve_policy_portfolio,
)
from nfl_dfs.portfolio_policy import (
    portfolio_policy_template,
    validate_portfolio_policy_bytes,
)
from nfl_dfs.selection import select_prior_lineups

from .test_participation import _slate
from .test_prior_selection import _prepared


def _policy(slate, entry_ids=("1", "2"), **controls):
    document = portfolio_policy_template(slate, entry_ids, controls=controls)
    raw = json.dumps(document, ensure_ascii=False).encode("utf-8")
    validation = validate_portfolio_policy_bytes(
        raw, slate=slate, entry_ids=entry_ids
    )
    assert validation.valid, validation.blockers()
    assert validation.policy is not None
    return validation.policy, raw


def _candidate(people, points, key, *, captain=None):
    people = tuple(people)
    return PolicyCandidate(
        roster=(key,),
        canonical_key=key,
        people=frozenset(people),
        captain_person=captain or people[0],
        prior_points=float(points),
        source_solver_status="OPTIMAL",
        source_solver_seconds=0.001,
    )


def _bank(*candidates, complete=True, status=None):
    return CandidateBank(
        candidates=tuple(candidates),
        status=status or ("COMPLETE_MODELED_BANK" if complete else "CANDIDATE_LIMIT_REACHED_INCOMPLETE"),
        complete=complete,
        candidate_limit=max(1, len(candidates)),
        total_time_limit_seconds=10.0,
        per_solve_time_limit_seconds=1.0,
        elapsed_seconds=0.01,
        solve_count=len(candidates) + int(complete),
        terminal_model_status="kInfeasible" if complete else None,
    )


def test_joint_milp_finds_portfolio_that_projection_order_greedy_misses(tmp_path) -> None:
    slate = _slate(tmp_path)
    policy, _raw = _policy(slate, max_pairwise_person_overlap=3)
    people = [binding.underlying_id for binding in policy.people]
    chalk = _candidate(people[:6], 100, "chalk")
    alternative_a = _candidate((*people[:4], *people[6:8]), 90, "a")
    alternative_b = _candidate((*people[2:6], *people[8:10]), 89, "b")

    greedy = [chalk]
    greedy.extend(
        candidate
        for candidate in (alternative_a, alternative_b)
        if all(len(candidate.people & chosen.people) <= 3 for chosen in greedy)
    )
    assert len(greedy) == 1

    result = solve_policy_portfolio(
        policy, _bank(chalk, alternative_a, alternative_b)
    )
    assert result.status == "OPTIMAL"
    assert set(result.selected_candidate_indexes) == {1, 2}
    assert result.objective_prior_points == pytest.approx(179.0)


def test_explicit_captain_max_allows_repeat_and_rejects_excess(tmp_path) -> None:
    slate = _slate(tmp_path)
    people = [row.underlying_id for row in _policy(slate)[0].people]
    first = _candidate(people[:6], 20, "a", captain=people[0])
    second = _candidate((*people[:3], *people[6:9]), 19, "b", captain=people[0])

    allowed, _ = _policy(
        slate,
        max_captain_exposure={"default_fraction": 1, "overrides": []},
        max_pairwise_person_overlap=6,
    )
    assert solve_policy_portfolio(allowed, _bank(first, second)).status == "OPTIMAL"

    rejected, _ = _policy(
        slate,
        max_captain_exposure={"default_fraction": 0.5, "overrides": []},
        max_pairwise_person_overlap=6,
    )
    result = solve_policy_portfolio(rejected, _bank(first, second))
    assert result.status == "MODELED_BANK_INFEASIBLE_PROVEN"
    assert result.infeasibility_scope == "COMPLETE_MODELED_BANK"


def test_combined_person_cap_aggregates_captain_and_flex_appearances(tmp_path) -> None:
    slate = _slate(tmp_path)
    base, _ = _policy(slate)
    people = [row.underlying_id for row in base.people]
    target = base.people[0]
    first = _candidate(people[:6], 20, "a", captain=target.underlying_id)
    second = _candidate((*people[:3], *people[6:9]), 19, "b", captain=people[1])
    capped, _ = _policy(
        slate,
        max_combined_person_exposure={
            "default_fraction": 1,
            "overrides": [{**target.as_mapping(), "fraction": 0.5}],
        },
        max_pairwise_person_overlap=6,
    )
    result = solve_policy_portfolio(capped, _bank(first, second))
    assert result.status == "MODELED_BANK_INFEASIBLE_PROVEN"


@pytest.mark.parametrize("overlap", range(7))
def test_configured_pairwise_overlap_zero_through_six(tmp_path, overlap) -> None:
    slate = _slate(tmp_path)
    policy, _ = _policy(slate, max_pairwise_person_overlap=overlap)
    people = [row.underlying_id for row in policy.people]
    first_people = people[:6]
    second_people = (*people[:overlap], *people[6 : 12 - overlap])
    assert len(set(second_people)) == 6
    first = _candidate(first_people, 20, "a")
    second = _candidate(second_people, 19, "b")
    assert len(first.people & second.people) == overlap
    result = solve_policy_portfolio(policy, _bank(first, second))
    assert result.status == "OPTIMAL"


def test_same_people_with_different_captain_are_distinct_but_overlap_six(tmp_path) -> None:
    slate = _slate(tmp_path)
    policy, _ = _policy(slate, max_pairwise_person_overlap=6)
    people = [row.underlying_id for row in policy.people[:6]]
    first = _candidate(people, 20, "captain-a", captain=people[0])
    second = _candidate(people, 19, "captain-b", captain=people[1])
    result = solve_policy_portfolio(policy, _bank(first, second))
    assert result.status == "OPTIMAL"


def test_exact_assignment_coverage_never_cycles() -> None:
    with pytest.raises(ValueError, match="COVERAGE_MISMATCH.*cycling=disabled"):
        exact_assignments_for_entries(("1", "2", "3"), (("a",), ("b",)))
    with pytest.raises(ValueError, match="DUPLICATE_ENTRY_ID"):
        exact_assignments_for_entries(("1", "1"), (("a",), ("b",)))
    assert tuple(
        exact_assignments_for_entries(("2", "1"), (("a",), ("b",)))
    ) == ("2", "1")


def test_complete_vs_incomplete_bank_infeasibility_is_named_truthfully(tmp_path) -> None:
    slate = _slate(tmp_path)
    policy, _ = _policy(
        slate,
        max_captain_exposure={"default_fraction": 0.5, "overrides": []},
        max_pairwise_person_overlap=6,
    )
    people = [row.underlying_id for row in policy.people]
    candidates = (
        _candidate(people[:6], 20, "a", captain=people[0]),
        _candidate((*people[:3], *people[6:9]), 19, "b", captain=people[0]),
    )
    complete = solve_policy_portfolio(policy, _bank(*candidates, complete=True))
    incomplete = solve_policy_portfolio(policy, _bank(*candidates, complete=False))
    assert complete.status == "MODELED_BANK_INFEASIBLE_PROVEN"
    assert incomplete.status == "CANDIDATE_BANK_EXHAUSTED_INCOMPLETE"
    assert incomplete.infeasibility_scope is None


@pytest.mark.parametrize(
    ("model_status", "expected"),
    [
        ("kTimeLimit", "CANDIDATE_BANK_TIME_LIMIT"),
        ("kIterationLimit", "CANDIDATE_BANK_SEARCH_LIMIT"),
        ("kSolveError", "CANDIDATE_BANK_SOLVER_ERROR"),
    ],
)
def test_candidate_bank_timeout_search_limit_and_solver_error_are_distinct(
    tmp_path, monkeypatch, model_status, expected
) -> None:
    from nfl_dfs import portfolio_enforcement as module

    class StubOptimizer:
        def __init__(self, *_args, **_kwargs):
            pass

        def set_time_limit(self, _seconds):
            pass

        def solve(self, _scores):
            return SimpleNamespace(
                status="NO_SOLUTION",
                roster=None,
                model_status=model_status,
            )

    monkeypatch.setattr(module, "LineupOptimizer", StubOptimizer)
    slate = _slate(tmp_path)
    bank = build_policy_candidate_bank(
        slate, {row.dk_id: 1.0 for row in slate.players}, candidate_limit=2
    )
    assert bank.status == expected
    assert bank.blocking


@pytest.mark.parametrize(
    ("model_status", "expected"),
    [
        (highspy.HighsModelStatus.kTimeLimit, "PORTFOLIO_SELECTION_TIME_LIMIT"),
        (highspy.HighsModelStatus.kIterationLimit, "PORTFOLIO_SELECTION_SEARCH_LIMIT"),
        (highspy.HighsModelStatus.kSolveError, "PORTFOLIO_SELECTION_SOLVER_ERROR"),
    ],
)
def test_portfolio_timeout_search_limit_and_solver_error_are_distinct(
    tmp_path, model_status, expected
) -> None:
    slate = _slate(tmp_path)
    policy, _ = _policy(slate)
    people = [row.underlying_id for row in policy.people]
    bank = _bank(_candidate(people[:6], 10, "a"), complete=False)

    class StubHighs:
        def setOptionValue(self, *_args):
            pass

        def addVars(self, *_args):
            pass

        def changeColsIntegrality(self, *_args):
            pass

        def changeObjectiveSense(self, *_args):
            pass

        def changeColsCost(self, *_args):
            pass

        def addRow(self, *_args):
            pass

        def run(self):
            pass

        def getModelStatus(self):
            return model_status

        def getInfo(self):
            return SimpleNamespace(mip_gap=float("inf"), mip_node_count=0)

        def getSolution(self):
            return SimpleNamespace(value_valid=False, col_value=[])

    result = solve_policy_portfolio(policy, bank, solver_factory=StubHighs)
    assert result.status == expected


def _assignment_csv_bytes(pairs):
    rows = ["Entry ID,CPT,FLEX,FLEX,FLEX,FLEX,FLEX"]
    rows.extend(",".join((entry, *roster)) for entry, roster in pairs)
    return ("\n".join(rows) + "\n").encode("utf-8")


def _audit(
    tmp_path,
    entry_ids=("1", "2"),
    assignments=None,
    selector_summary=None,
    controls=None,
    policy_mutator=None,
    **mutations,
):
    slate = _slate(tmp_path)
    policy_controls = {
        "max_pairwise_person_overlap": 6,
        "require_unique_lineups": False,
    }
    policy_controls.update(controls or {})
    policy, source_policy = _policy(
        slate,
        entry_ids,
        **policy_controls,
    )
    objective = {row.dk_id: float(index) for index, row in enumerate(slate.players)}
    bank = build_policy_candidate_bank(
        slate,
        objective,
        candidate_limit=len(entry_ids),
        total_time_limit_seconds=5,
        per_solve_time_limit_seconds=1,
    )
    assert len(bank.candidates) == len(entry_ids)
    pairs = assignments or [
        (entry, bank.candidates[index].roster)
        for index, entry in enumerate(entry_ids)
    ]
    artifact = _assignment_csv_bytes(pairs)
    salary_bytes = (tmp_path / "DKSalaries.csv").read_bytes()
    entry_bytes = b"exact entry bytes"
    normalized = policy.canonical_bytes()
    policy_for_audit = policy_mutator(policy) if policy_mutator else policy
    values = {
        "salary_bytes": salary_bytes,
        "entry_bytes": entry_bytes,
        "expected_entry_sha256": sha256_bytes(entry_bytes),
        "source_policy_bytes": source_policy,
        "expected_source_policy_sha256": sha256_bytes(source_policy),
        "normalized_policy_bytes": normalized,
        "expected_normalized_policy_sha256": sha256_bytes(normalized),
        "assignment_artifact_bytes": artifact,
        "expected_assignment_artifact_sha256": sha256_bytes(artifact),
    }
    values.update(mutations)
    return audit_policy_assignments(
        slate=slate,
        policy=policy_for_audit,
        assignments=pairs,
        selector_summary=selector_summary,
        **values,
    )


def test_independent_audit_reparses_controls_from_normalized_artifact(tmp_path) -> None:
    def replace_selector_policy(policy):
        return replace(
            policy,
            effective_limits=tuple(
                replace(limit, combined_max_entries=0)
                for limit in policy.effective_limits
            ),
        )

    audit = _audit(tmp_path, policy_mutator=replace_selector_policy)
    codes = {problem.split(":", 1)[0] for problem in audit.problems}
    assert "PORTFOLIO_AUDIT_NORMALIZED_POLICY_BYTES_MISMATCH" in codes
    assert "PORTFOLIO_AUDIT_COMBINED_PERSON_CAP_EXCEEDED" not in codes


@pytest.mark.parametrize(
    ("assignments", "code"),
    [
        ([('1', ('x',) * 6), ('1', ('x',) * 6)], "PORTFOLIO_AUDIT_DUPLICATE_ENTRY_ID"),
        ([('1', ('x',) * 6)], "PORTFOLIO_AUDIT_MISSING_ENTRY_ID"),
        ([('1', ('x',) * 6), ('2', ('x',) * 6), ('3', ('x',) * 6)], "PORTFOLIO_AUDIT_EXTRA_ENTRY_ID"),
        ([('2', ('x',) * 6), ('1', ('x',) * 6)], "PORTFOLIO_AUDIT_ENTRY_ID_ORDER_MISMATCH"),
    ],
)
def test_audit_names_duplicate_missing_extra_and_reordered_assignments(
    tmp_path, assignments, code
) -> None:
    audit = _audit(tmp_path, assignments=assignments)
    assert any(problem.startswith(code) for problem in audit.problems)


def test_independent_audit_catches_tampered_selector_summary(tmp_path) -> None:
    baseline = _audit(tmp_path)
    assert baseline.passed
    summary = {
        "person_exposure": dict(baseline.combined_person_counts),
        "captain_exposure": dict(baseline.captain_counts),
        "pairwise_person_overlap": [
            {"entry_id_a": left, "entry_id_b": right, "people": overlap}
            for left, right, overlap in baseline.pairwise_person_overlap
        ],
        "selected_lineup_count": 999,
        "enforcement_status": "PASS",
    }
    audit = _audit(tmp_path, selector_summary=summary)
    assert any(
        problem.startswith("PORTFOLIO_AUDIT_SELECTOR_SUMMARY_MISMATCH")
        for problem in audit.problems
    )


def test_audit_recomputes_canonical_duplicate_and_exact_caps(tmp_path) -> None:
    slate = _slate(tmp_path)
    objective = {row.dk_id: float(index) for index, row in enumerate(slate.players)}
    bank = build_policy_candidate_bank(slate, objective, candidate_limit=1)
    roster = bank.candidates[0].roster
    reversed_flex = (roster[0], *reversed(roster[1:]))
    captain_person = next(row for row in slate.players if row.dk_id == roster[0]).underlying_id
    binding = next(
        item
        for item in _policy(slate)[0].people
        if item.underlying_id == captain_person
    )
    audit = _audit(
        tmp_path,
        assignments=[("1", roster), ("2", reversed_flex)],
        controls={
            "require_unique_lineups": True,
            "max_combined_person_exposure": {
                "default_fraction": 1,
                "overrides": [{**binding.as_mapping(), "fraction": 0.5}],
            },
            "max_captain_exposure": {
                "default_fraction": 1,
                "overrides": [{**binding.as_mapping(), "fraction": 0.5}],
            },
        },
    )
    codes = {problem.split(":", 1)[0] for problem in audit.problems}
    assert "PORTFOLIO_AUDIT_CANONICAL_DUPLICATE" in codes
    assert "PORTFOLIO_AUDIT_COMBINED_PERSON_CAP_EXCEEDED" in codes
    assert "PORTFOLIO_AUDIT_CAPTAIN_CAP_EXCEEDED" in codes


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        ({"salary_bytes": b"changed salary"}, "PORTFOLIO_AUDIT_SALARY_SHA256_MISMATCH"),
        ({"source_policy_bytes": b"{}"}, "PORTFOLIO_AUDIT_SOURCE_POLICY_SHA256_MISMATCH"),
        ({"normalized_policy_bytes": b"{}"}, "PORTFOLIO_AUDIT_NORMALIZED_POLICY_SHA256_MISMATCH"),
        ({"assignment_artifact_bytes": b"changed"}, "PORTFOLIO_AUDIT_ASSIGNMENT_ARTIFACT_SHA256_MISMATCH"),
    ],
)
def test_audit_catches_bound_artifact_mutation(tmp_path, mutation, code) -> None:
    audit = _audit(tmp_path, **mutation)
    assert any(problem.startswith(code) for problem in audit.problems)


def test_candidate_bank_generation_is_deterministic_and_reports_incomplete_limit(tmp_path) -> None:
    slate = _slate(tmp_path)
    objective = {row.dk_id: float(index) for index, row in enumerate(slate.players)}
    first = build_policy_candidate_bank(slate, objective, candidate_limit=4)
    second = build_policy_candidate_bank(slate, objective, candidate_limit=4)
    assert first.status == second.status == "CANDIDATE_LIMIT_REACHED_INCOMPLETE"
    assert [candidate.roster for candidate in first.candidates] == [
        candidate.roster for candidate in second.candidates
    ]
    assert first.canonical_count == second.canonical_count == 4


def test_declared_five_entry_policy_rehearsal_uses_one_joint_solve(tmp_path) -> None:
    slate, model, contract, splits = _prepared(tmp_path)
    entry_ids = tuple(str(index) for index in range(1, 6))
    policy, _ = _policy(
        slate,
        entry_ids,
        max_pairwise_person_overlap=6,
        require_unique_lineups=True,
    )
    lineups, _scores, report = select_prior_lineups(
        slate,
        model,
        splits,
        contract,
        count=5,
        portfolio_policy=policy,
    )
    enforcement = report["portfolio_policy"]
    assert len(lineups) == 5
    assert len({lineup.canonical_key for lineup in lineups}) == 5
    assert enforcement["candidate_bank"]["candidate_count"] == 32
    assert enforcement["candidate_bank"]["status"] == (
        "CANDIDATE_LIMIT_REACHED_INCOMPLETE"
    )
    assert enforcement["solve"]["status"] == "OPTIMAL"
    assert enforcement["solve"]["selected_lineup_count"] == 5
