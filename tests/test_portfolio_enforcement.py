"""SD4 bounded joint enforcement and independent final-assignment audit."""

from __future__ import annotations

import json
from dataclasses import replace
from types import SimpleNamespace

import highspy
import numpy as np
import pytest

from nfl_dfs.hashing import sha256_bytes
from nfl_dfs.portfolio_enforcement import (
    DEFAULT_CANDIDATE_LIMIT,
    DEFAULT_CANDIDATE_SECONDS,
    DEFAULT_SELECTION_SECONDS,
    CandidateBank,
    PolicyCandidate,
    audit_policy_assignments,
    build_policy_candidate_bank,
    exact_assignments_for_entries,
    plan_captain_strata,
    scaled_candidate_limit,
    scaled_candidate_seconds,
    scaled_selection_seconds,
    solve_policy_portfolio,
)
from nfl_dfs.portfolio_policy import (
    portfolio_policy_template,
    validate_portfolio_policy_bytes,
)
from nfl_dfs.selection import select_prior_lineups

from .test_participation import _POOL, _slate
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


class _SelectionStub:
    """SD3's joint model calls, recorded; the result is whatever the test sets."""

    model_status = highspy.HighsModelStatus.kOptimal
    info = SimpleNamespace(mip_gap=float("inf"), mip_node_count=0)
    solution = SimpleNamespace(value_valid=False, col_value=[])

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
        return self.model_status

    def getInfo(self):
        return self.info

    def getSolution(self):
        return self.solution


@pytest.mark.parametrize(
    "model_status",
    [
        highspy.HighsModelStatus.kTimeLimit,
        highspy.HighsModelStatus.kIterationLimit,
        highspy.HighsModelStatus.kSolutionLimit,
    ],
)
def test_sd3_limit_with_a_valid_incumbent_returns_it_validated(tmp_path, model_status) -> None:
    """Session 08: SD3 returns a limit's valid integer incumbent, labelled, never optimal."""

    slate = _slate(tmp_path)
    policy, _ = _policy(slate)
    people = [row.underlying_id for row in policy.people]
    bank = _bank(
        _candidate(people[:6], 20, "a"),
        _candidate(people[3:9], 19, "b", captain=people[3]),
        _candidate(people[6:12], 18, "c", captain=people[6]),
        complete=False,
    )

    class Stub(_SelectionStub):
        info = SimpleNamespace(mip_gap=0.04, mip_node_count=12)
        # Counts, then the used indicators, per candidate.
        solution = SimpleNamespace(value_valid=True, col_value=[1.0, 0.0, 1.0, 1.0, 0.0, 1.0])

    Stub.model_status = model_status
    result = solve_policy_portfolio(policy, bank, solver_factory=Stub)
    assert result.status == "FEASIBLE_LIMIT_ACTUAL_CANDIDATE_BANK"
    assert result.passed
    assert result.selected_candidate_indexes == (0, 2)
    assert (result.mip_gap, result.node_count, result.model_status) == (0.04, 12, model_status.name)
    assert result.objective_prior_points == pytest.approx(38.0)
    assert result.as_report()["optimality_scope"] is None
    # An incumbent failing the optimum's checks fails closed.
    Stub.solution = SimpleNamespace(value_valid=True, col_value=[0.5, 0.5, 1.0, 1.0, 1.0, 1.0])
    failed = solve_policy_portfolio(policy, bank, solver_factory=Stub)
    assert (failed.status, failed.model_status) == ("PORTFOLIO_SELECTION_SOLVER_ERROR", "INVALID_INTEGER_SOLUTION")


def test_sd3_real_highs_node_limit_returns_a_validated_incumbent(tmp_path) -> None:
    """Real HiGHS: a feasible start and a zero-node limit give kSolutionLimit with a valid incumbent."""

    slate = _slate(tmp_path)
    policy, _ = _policy(slate)
    people = [row.underlying_id for row in policy.people]
    candidates = (
        _candidate(people[:6], 20, "a"),
        _candidate(people[3:9], 19, "b", captain=people[3]),
        _candidate(people[6:12], 18, "c", captain=people[6]),
    )
    bank = _bank(*candidates, complete=False)

    class Started(highspy.Highs):
        def run(self):
            # The weaker pair, b and c: counts 1 and used indicators 1.
            start = np.asarray([1, 2, 4, 5], dtype=np.int32)
            self.setSolution(len(start), start, np.ones(len(start), dtype=np.float64))
            self.setOptionValue("mip_max_nodes", 0)
            self.setOptionValue("presolve", "off")  # presolve alone solves three candidates
            return super().run()

    result = solve_policy_portfolio(policy, bank, solver_factory=Started)
    assert (result.status, result.model_status) == ("FEASIBLE_LIMIT_ACTUAL_CANDIDATE_BANK", "kSolutionLimit")
    assert sorted(result.selected_candidate_indexes) == [1, 2]
    assert result.as_report()["optimality_scope"] is None
    optimum = solve_policy_portfolio(policy, bank)
    assert optimum.status == "OPTIMAL" and optimum.objective_prior_points > result.objective_prior_points


def _legal_showdown_rosters(slate, count):
    """Distinct legal Showdown rosters built by hand, checked by `validate_lineup`."""

    from itertools import combinations

    from nfl_dfs.lineups import validate_lineup

    captains = [row for row in slate.players if row.role == "CPT"]
    flex = sorted((row for row in slate.players if row.role == "FLEX"), key=lambda row: (row.salary, row.dk_id))
    rosters = []
    for captain in captains:
        others = [row for row in flex if row.underlying_id != captain.underlying_id]
        for chosen in combinations(others[:8], 5):
            roster = (captain.dk_id, *(row.dk_id for row in chosen))
            if validate_lineup(slate, roster).lineup is not None:
                rosters.append(roster)
                break
        if len(rosters) == count:
            return rosters
    raise AssertionError("fixture slate has too few rosters")


def test_a_limit_stopped_showdown_candidate_solve_keeps_its_roster_labelled(tmp_path, monkeypatch) -> None:
    from nfl_dfs import portfolio_enforcement as module

    slate = _slate(tmp_path)
    rosters = _legal_showdown_rosters(slate, 2)
    script = [("FEASIBLE_LIMIT", "kTimeLimit", rosters[0]), ("FEASIBLE_LIMIT", "kSolutionLimit", rosters[1])]

    class Scripted:
        def __init__(self, *_args, **_kwargs):
            pass

        def set_time_limit(self, _seconds):
            pass

        def add_no_good(self, *_args):
            pass

        def solve(self, _scores):
            if not script:
                return SimpleNamespace(status="INFEASIBLE", roster=None, model_status="kInfeasible",
                                       elapsed_seconds=0.0)
            status, model_status, roster = script.pop(0)
            return SimpleNamespace(status=status, roster=roster, model_status=model_status,
                                   elapsed_seconds=0.5)

    monkeypatch.setattr(module, "LineupOptimizer", Scripted)
    bank = build_policy_candidate_bank(slate, {row.dk_id: 1.0 for row in slate.players}, candidate_limit=2)
    assert not bank.blocking and bank.status == "CANDIDATE_LIMIT_REACHED_INCOMPLETE"
    assert [candidate.roster for candidate in bank.candidates] == rosters
    assert {candidate.source_solver_status for candidate in bank.candidates} == {"FEASIBLE_LIMIT"}
    assert bank.as_report()["limit_incumbent_candidates"] == 2


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


# --------------------------------------------------------------------------- #
# R18: the candidate bank is policy-aware (stratified) and stays deterministic
# --------------------------------------------------------------------------- #


def _dominated_objective(slate, dominant_person):
    """An objective where one person captains every plain top-K lineup."""

    objective = {}
    for index, row in enumerate(slate.players):
        value = float(index)
        if row.underlying_id == dominant_person:
            value = 1000.0 if row.role == "CPT" else 500.0
        objective[row.dk_id] = value
    return objective


def _five_entry_captain_capped_policy(slate, **extra_controls):
    entry_ids = tuple(str(index) for index in range(1, 6))
    controls = {
        "max_captain_exposure": {"default_fraction": 0.2, "overrides": []},
        "max_pairwise_person_overlap": 6,
    }
    controls.update(extra_controls)
    policy, raw = _policy(slate, entry_ids, **controls)
    return entry_ids, policy, raw


def test_scaled_policy_bounds_grow_with_the_entry_count() -> None:
    assert scaled_candidate_limit(2) == DEFAULT_CANDIDATE_LIMIT
    assert scaled_candidate_limit(8) == DEFAULT_CANDIDATE_LIMIT
    assert scaled_candidate_limit(20) == 80
    assert scaled_candidate_seconds(5) == DEFAULT_CANDIDATE_SECONDS
    assert scaled_candidate_seconds(20) == 40.0
    assert scaled_selection_seconds(5) == DEFAULT_SELECTION_SECONDS
    assert scaled_selection_seconds(20) == 20.0


def test_policy_blind_bank_exhausts_where_the_stratified_bank_seeds_captains(
    tmp_path,
) -> None:
    slate = _slate(tmp_path)
    _entry_ids, policy, _raw = _five_entry_captain_capped_policy(slate)
    dominant = policy.people[0].underlying_id
    objective = _dominated_objective(slate, dominant)

    plain = build_policy_candidate_bank(slate, objective, candidate_limit=32)
    assert plain.policy_aware is False
    assert {candidate.captain_person for candidate in plain.candidates} == {dominant}
    assert plain.as_report()["strata"] == {
        "captain": {}, "exclusion": {}, "chain": 0, "fill": 32,
    }
    exhausted = solve_policy_portfolio(policy, plain)
    assert exhausted.status == "CANDIDATE_BANK_EXHAUSTED_INCOMPLETE"

    aware = build_policy_candidate_bank(
        slate, objective, candidate_limit=32, policy=policy
    )
    assert aware.policy_aware is True
    assert aware.status == "CANDIDATE_LIMIT_REACHED_INCOMPLETE"
    assert not aware.blocking
    assert len(aware.candidates) == aware.canonical_count == 32
    report = aware.as_report()
    # Captain maximum is one entry each, so at least seven Captains are
    # seeded (five entries plus a two-slot margin) at depth ceil(5/7)+1 = 2.
    seeded, depth = plan_captain_strata(policy, objective)
    assert len(seeded) == 7 and depth == 2
    assert seeded[0].person == dominant
    assert set(report["strata"]["captain"]) == {item.person for item in seeded}
    assert all(count == 2 for count in report["strata"]["captain"].values())
    assert report["strata"]["exclusion"] == {}
    # The chain walks the policy greedily (one entry per Captain here) for
    # entry_count + 2 lineups; with overlap six it mostly re-finds the Captain
    # strata's best lineups, which dedupe rather than count twice.
    chain = next(item for item in report["strata_detail"] if item["kind"] == "chain")
    assert chain["target"] == chain["enumerated"] == 7
    assert 0 <= chain["added"] <= 7
    assert report["strata"]["chain"] == chain["added"]
    assert report["strata"]["fill"] == 32 - sum(report["strata"]["captain"].values()) - report["strata"]["chain"]
    kinds = [item["kind"] for item in report["strata_detail"]]
    assert kinds == ["captain"] * 7 + ["chain", "fill"]
    assert all(item["terminal"] == "TARGET_REACHED" for item in report["strata_detail"])
    assert report["search_scope"].endswith("NOT_A_FULL_SLATE_SEARCH")

    result = solve_policy_portfolio(policy, aware)
    assert result.status == "OPTIMAL"
    chosen = [aware.candidates[index] for index in result.selected_candidate_indexes]
    assert len(chosen) == 5
    assert len({candidate.captain_person for candidate in chosen}) == 5
    assert len({candidate.canonical_key for candidate in chosen}) == 5


def test_stratified_bank_is_deterministic_across_runs(tmp_path) -> None:
    slate = _slate(tmp_path)
    _entry_ids, policy, _raw = _five_entry_captain_capped_policy(
        slate, max_pairwise_person_overlap=4
    )
    objective = _dominated_objective(slate, policy.people[0].underlying_id)
    first = build_policy_candidate_bank(slate, objective, candidate_limit=32, policy=policy)
    second = build_policy_candidate_bank(slate, objective, candidate_limit=32, policy=policy)
    assert [candidate.roster for candidate in first.candidates] == [
        candidate.roster for candidate in second.candidates
    ]
    assert first.status == second.status
    assert [item.as_report() for item in first.strata] == [
        item.as_report() for item in second.strata
    ]
    first_solve = solve_policy_portfolio(policy, first)
    second_solve = solve_policy_portfolio(policy, second)
    assert first_solve.status == second_solve.status == "OPTIMAL"
    assert first_solve.selected_candidate_indexes == second_solve.selected_candidate_indexes


def test_exclusion_strata_supply_lineups_without_a_combined_capped_person(tmp_path) -> None:
    slate = _slate(tmp_path)
    entry_ids = tuple(str(index) for index in range(1, 6))
    dominant = _policy(slate, entry_ids)[0].people[0]
    policy, _raw = _policy(
        slate,
        entry_ids,
        max_combined_person_exposure={
            "default_fraction": None,
            "overrides": [{**dominant.as_mapping(), "fraction": 0.6}],
        },
        max_pairwise_person_overlap=6,
    )
    limit = next(
        item for item in policy.effective_limits
        if item.person.underlying_id == dominant.underlying_id
    )
    assert limit.combined_max_entries == 3
    objective = _dominated_objective(slate, dominant.underlying_id)

    plain = build_policy_candidate_bank(slate, objective, candidate_limit=32)
    assert all(dominant.underlying_id in candidate.people for candidate in plain.candidates)
    assert solve_policy_portfolio(policy, plain).status == "CANDIDATE_BANK_EXHAUSTED_INCOMPLETE"

    aware = build_policy_candidate_bank(slate, objective, candidate_limit=32, policy=policy)
    report = aware.as_report()
    # Three of five entries may carry the person, so at least 5 - 3 + 1 = 3
    # lineups without them are enumerated in a dedicated stratum.
    exclusion = next(
        item for item in report["strata_detail"]
        if item["kind"] == "exclusion" and item["person"] == dominant.underlying_id
    )
    assert exclusion["target"] == 3
    assert exclusion["enumerated"] >= 3
    assert sum(
        1 for candidate in aware.candidates if dominant.underlying_id not in candidate.people
    ) >= 3
    result = solve_policy_portfolio(policy, aware)
    assert result.status == "OPTIMAL"
    chosen = [aware.candidates[index] for index in result.selected_candidate_indexes]
    assert sum(1 for candidate in chosen if dominant.underlying_id in candidate.people) <= 3


def test_infeasible_captain_stratum_is_recorded_not_raised(tmp_path) -> None:
    # A person priced beyond any legal lineup cannot captain (or flex). The
    # policy still lists them; their stratum ends MODEL_INFEASIBLE and the
    # bank continues instead of blocking.
    pool = tuple(
        (team, position, name, status, 40_000 if name == "Sea Alpha WR" else salary)
        for team, position, name, status, salary in _POOL
    )
    slate = _slate(tmp_path, pool=pool)
    entry_ids = tuple(str(index) for index in range(1, 6))
    policy, _raw = _policy(
        slate,
        entry_ids,
        max_captain_exposure={"default_fraction": 0.2, "overrides": []},
        max_pairwise_person_overlap=6,
    )
    unaffordable = next(
        binding.underlying_id for binding in policy.people if binding.underlying_id.endswith("Sea Alpha WR")
    )
    objective = _dominated_objective(slate, unaffordable)
    bank = build_policy_candidate_bank(slate, objective, candidate_limit=24, policy=policy)
    assert not bank.blocking
    stratum = next(
        item for item in bank.strata if item.kind == "captain" and item.person == unaffordable
    )
    assert stratum.terminal == "MODEL_INFEASIBLE"
    assert stratum.enumerated == stratum.added == 0
    assert stratum.solve_count == 1
    assert len(bank.candidates) == 24
    assert all(unaffordable not in candidate.people for candidate in bank.candidates)
    assert solve_policy_portfolio(policy, bank).status == "OPTIMAL"


def test_plan_captain_strata_orders_by_objective_and_skips_excluded_and_zero(tmp_path) -> None:
    slate = _slate(tmp_path)
    entry_ids = tuple(str(index) for index in range(1, 6))
    people = _policy(slate, entry_ids)[0].people
    excluded_person = people[3]
    policy, _raw = _policy(
        slate,
        entry_ids,
        max_captain_exposure={"default_fraction": 0.4, "overrides": []},
        excluded_people=[excluded_person.as_mapping()],
        max_pairwise_person_overlap=6,
    )
    objective = {}
    for index, row in enumerate(slate.players):
        objective[row.dk_id] = float(index) if row.role == "CPT" else 1.0
    zero_person = people[5]
    objective[zero_person.cpt_dk_id] = 0.0
    seeded, depth = plan_captain_strata(
        policy, objective, excluded_ids=(people[7].cpt_dk_id, people[7].flex_dk_id)
    )
    # Captain maximum is two each; five entries plus the two-slot margin need
    # four seeded Captains, at depth ceil(5/4) + 1 = 3.
    assert len(seeded) == 4 and depth == 3
    assert [item.objective for item in seeded] == sorted(
        (item.objective for item in seeded), reverse=True
    )
    seeded_people = {item.person for item in seeded}
    assert excluded_person.underlying_id not in seeded_people
    assert zero_person.underlying_id not in seeded_people
    assert people[7].underlying_id not in seeded_people


def test_five_entry_captain_cap_selects_five_captains_and_passes_independent_audit(
    tmp_path,
) -> None:
    slate, model, contract, splits = _prepared(tmp_path)
    entry_ids = tuple(str(index) for index in range(1, 6))
    policy, source_policy = _policy(
        slate,
        entry_ids,
        max_captain_exposure={"default_fraction": 0.2, "overrides": []},
        max_pairwise_person_overlap=4,
    )
    lineups, _scores, report = select_prior_lineups(
        slate, model, splits, contract, count=5, portfolio_policy=policy
    )
    assert len(lineups) == 5
    by_id = {row.dk_id: row for row in slate.players}
    captains = {by_id[lineup.captain_dk_id].underlying_id for lineup in lineups}
    assert len(captains) == 5
    assert all(count == 1 for count in report["captain_exposure"].values())
    assert all(item["people"] <= 4 for item in report["pairwise_person_overlap"])
    enforcement = report["portfolio_policy"]
    bank_report = enforcement["candidate_bank"]
    assert bank_report["policy_aware"] is True
    assert bank_report["candidate_limit"] == 32
    assert bank_report["total_time_limit_seconds"] == 30.0
    assert enforcement["solve"]["time_limit_seconds"] == 10.0
    assert len(bank_report["strata"]["captain"]) >= 5
    assert bank_report["strata"]["chain"] > 0
    assert enforcement["solve"]["status"] == "OPTIMAL"

    assignments = exact_assignments_for_entries(
        entry_ids, [lineup.roster for lineup in lineups]
    )
    artifact = _assignment_csv_bytes(list(assignments.items()))
    salary_bytes = (tmp_path / "DKSalaries.csv").read_bytes()
    entry_bytes = b"exact entry bytes"
    normalized = policy.canonical_bytes()
    audit = audit_policy_assignments(
        slate=slate,
        policy=policy,
        assignments=assignments,
        salary_bytes=salary_bytes,
        entry_bytes=entry_bytes,
        expected_entry_sha256=sha256_bytes(entry_bytes),
        source_policy_bytes=source_policy,
        expected_source_policy_sha256=sha256_bytes(source_policy),
        normalized_policy_bytes=normalized,
        expected_normalized_policy_sha256=sha256_bytes(normalized),
        assignment_artifact_bytes=artifact,
        expected_assignment_artifact_sha256=sha256_bytes(artifact),
        selector_summary={
            "person_exposure": report["person_exposure"],
            "captain_exposure": report["captain_exposure"],
            "pairwise_person_overlap": report["pairwise_person_overlap"],
            "selected_lineup_count": report["selected_lineup_count"],
        },
    )
    assert audit.passed, audit.problems
    assert all(count == 1 for _person, count in audit.captain_counts)


def test_five_entry_combined_cap_on_the_top_person_is_satisfied(tmp_path) -> None:
    slate, model, contract, splits = _prepared(tmp_path)
    entry_ids = tuple(str(index) for index in range(1, 6))
    uncapped, _ = _policy(slate, entry_ids, max_pairwise_person_overlap=6)
    _lineups, _scores, baseline = select_prior_lineups(
        slate, model, splits, contract, count=5, portfolio_policy=uncapped
    )
    top_person, top_exposure = max(
        baseline["person_exposure"].items(), key=lambda item: (item[1], item[0])
    )
    assert top_exposure == 5
    binding = next(item for item in uncapped.people if item.underlying_id == top_person)
    capped, _ = _policy(
        slate,
        entry_ids,
        max_combined_person_exposure={
            "default_fraction": None,
            "overrides": [{**binding.as_mapping(), "fraction": 0.6}],
        },
        max_pairwise_person_overlap=6,
    )
    lineups, _scores, report = select_prior_lineups(
        slate, model, splits, contract, count=5, portfolio_policy=capped
    )
    assert len(lineups) == 5
    assert report["person_exposure"].get(top_person, 0) <= 3
    exclusion = report["portfolio_policy"]["candidate_bank"]["strata"]["exclusion"]
    assert top_person in exclusion
    assert report["portfolio_policy"]["solve"]["status"] == "OPTIMAL"


def test_policy_selection_is_deterministic_end_to_end(tmp_path) -> None:
    slate, model, contract, splits = _prepared(tmp_path)
    entry_ids = tuple(str(index) for index in range(1, 6))
    policy, _ = _policy(
        slate,
        entry_ids,
        max_captain_exposure={"default_fraction": 0.4, "overrides": []},
        max_pairwise_person_overlap=4,
    )
    runs = [
        select_prior_lineups(slate, model, splits, contract, count=5, portfolio_policy=policy)
        for _ in range(2)
    ]
    (first_lineups, _first_scores, first_report), (second_lineups, _second_scores, second_report) = runs
    assert [lineup.roster for lineup in first_lineups] == [
        lineup.roster for lineup in second_lineups
    ]
    first_bank = dict(first_report["portfolio_policy"]["candidate_bank"])
    second_bank = dict(second_report["portfolio_policy"]["candidate_bank"])
    for volatile in ("elapsed_seconds",):
        first_bank.pop(volatile)
        second_bank.pop(volatile)
    assert first_bank == second_bank
    assert (
        first_report["portfolio_policy"]["solve"]["selected_candidate_indexes"]
        == second_report["portfolio_policy"]["solve"]["selected_candidate_indexes"]
    )


def test_explicit_policy_bounds_still_override_the_scaled_defaults(tmp_path) -> None:
    slate, model, contract, splits = _prepared(tmp_path)
    entry_ids = tuple(str(index) for index in range(1, 6))
    policy, _ = _policy(slate, entry_ids, max_pairwise_person_overlap=6)
    _lineups, _scores, report = select_prior_lineups(
        slate,
        model,
        splits,
        contract,
        count=5,
        portfolio_policy=policy,
        policy_candidate_limit=12,
        policy_candidate_seconds=7.0,
        policy_selection_seconds=3.0,
    )
    bank_report = report["portfolio_policy"]["candidate_bank"]
    assert bank_report["candidate_limit"] == 12
    assert bank_report["candidate_count"] == 12
    assert bank_report["total_time_limit_seconds"] == 7.0
    assert report["portfolio_policy"]["solve"]["time_limit_seconds"] == 3.0
    # An unconstrained policy needs no feasible chain; the report says so.
    chain = next(item for item in bank_report["strata_detail"] if item["kind"] == "chain")
    assert chain["terminal"] == "NOT_REQUIRED_UNCONSTRAINED"
