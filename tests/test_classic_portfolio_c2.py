"""C2 golden, adversarial, replay, and boundary coverage."""

from __future__ import annotations

import itertools
import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import highspy
import pytest

from nfl_dfs.classic_portfolio import (
    ClassicCandidate,
    ClassicCandidateBank,
    _group_matches,
    _stack_matches,
    assignment_artifact_bytes,
    audit_classic_portfolio,
    build_classic_candidate_bank,
    candidate_bank_bytes,
    exact_classic_assignments,
    solve_classic_portfolio,
)
from nfl_dfs.classic_portfolio_policy import (
    classic_portfolio_policy_template,
    parse_normalized_classic_policy_bytes,
    validate_classic_portfolio_policy_bytes,
    write_normalized_classic_portfolio_policy,
)
from nfl_dfs.contracts import EngineMode, GameContract, SalaryPlayer, SlateContract
from nfl_dfs.hashing import sha256_bytes, sha256_file
from nfl_dfs.lineups import validate_lineup
from nfl_dfs.prior_review import run_prior_review
from nfl_dfs.projection import build_projection_package

from .test_classic_prior_review import AS_OF, _fixture


def _slate() -> SlateContract:
    games = (
        GameContract(
            game_id="NE@SEA",
            away_team="NE",
            home_team="SEA",
            lock_at=datetime(2026, 9, 13, 18, 0, tzinfo=timezone.utc),
        ),
        GameContract(
            game_id="DAL@PHI",
            away_team="DAL",
            home_team="PHI",
            lock_at=datetime(2026, 9, 13, 20, 25, tzinfo=timezone.utc),
        ),
        GameContract(
            game_id="BUF@NYJ",
            away_team="BUF",
            home_team="NYJ",
            lock_at=datetime(2026, 9, 13, 20, 25, tzinfo=timezone.utc),
        ),
    )
    game_by_team = {
        team: game
        for game in games
        for team in (game.away_team, game.home_team)
    }
    depths = {"QB": 2, "RB": 4, "WR": 6, "TE": 3, "DST": 2}
    rows: list[SalaryPlayer] = []
    identifier = 82000000
    for team_index, team in enumerate(game_by_team):
        game = game_by_team[team]
        opponent = game.home_team if team == game.away_team else game.away_team
        for position, depth in depths.items():
            for ordinal in range(1, depth + 1):
                identifier += 1
                rows.append(
                    SalaryPlayer(
                        dk_id=str(identifier),
                        name=f"{team} {position} {ordinal}",
                        position=position,
                        roster_positions=(
                            (position, "FLEX")
                            if position in {"RB", "WR", "TE"}
                            else (position,)
                        ),
                        salary=3500 + 75 * ordinal + 20 * team_index,
                        team=team,
                        opponent=opponent,
                        game_id=game.game_id,
                        lock_at=game.lock_at,
                        underlying_id=f"{team}|{position}|{ordinal}",
                    )
                )
    return SlateContract(
        mode=EngineMode.CLASSIC,
        draft_group="DG-C2",
        games=games,
        scoring_version="draftkings_nfl_scoring_2026_fixture_v1",
        salary_hash=sha256_bytes(b"salary"),
        players=tuple(rows),
    )


def _policy(
    count: int,
    *,
    controls: dict[str, object] | None = None,
    limits: dict[str, object] | None = None,
):
    slate = _slate()
    entry_ids = tuple(f"E{index:03d}" for index in range(1, count + 1))
    entry_bytes = b"entry"
    document = classic_portfolio_policy_template(
        slate,
        entry_ids,
        entry_sha256=sha256_bytes(entry_bytes),
        controls=controls,
        limits=limits,
    )
    raw = json.dumps(document, ensure_ascii=False, indent=2).encode("utf-8")
    validation = validate_classic_portfolio_policy_bytes(
        raw,
        slate=slate,
        entry_ids=entry_ids,
        entry_sha256=sha256_bytes(entry_bytes),
    )
    assert validation.valid, validation.blockers()
    assert validation.policy is not None
    return slate, validation.policy, raw, entry_bytes


def _objective(slate: SlateContract) -> dict[str, float]:
    return {
        row.dk_id: 40.0 - index / 1000.0
        for index, row in enumerate(slate.players)
    }


def _audit(slate, policy, source, original_entry_bytes, bank, selection, **mutations):
    candidate = candidate_bank_bytes(policy, bank)
    pairs = exact_classic_assignments(
        policy.entry_ids,
        [bank.candidates[index].roster for index in selection.selected_candidate_indexes],
    )
    assignment = assignment_artifact_bytes(
        policy,
        pairs,
        candidate_bank_sha256=sha256_bytes(candidate),
    )
    values = {
        "normalized_policy_bytes": policy.canonical_bytes(),
        "expected_normalized_policy_sha256": policy.normalized_sha256,
        "source_policy_bytes": source,
        "expected_source_policy_sha256": sha256_bytes(source),
        "salary_bytes": b"salary",
        "expected_salary_sha256": slate.salary_hash,
        "entry_bytes": original_entry_bytes,
        "expected_entry_sha256": sha256_bytes(original_entry_bytes),
        "bound_artifacts": {"team_prior_sha256": (b"team-prior", sha256_bytes(b"team-prior"))},
        "candidate_bytes": candidate,
        "expected_candidate_sha256": sha256_bytes(candidate),
        "assignment_bytes": assignment,
        "expected_assignment_sha256": sha256_bytes(assignment),
    }
    values.update(mutations)
    return audit_classic_portfolio(slate=slate, **values), candidate, assignment


def test_policy_binds_complete_identity_integer_limits_and_canonicalizes_order() -> None:
    slate, policy, raw, entry_bytes = _policy(3)
    payload = json.loads(raw)
    payload["bindings"]["people"].reverse()
    payload["bindings"]["games"].reverse()
    payload["bindings"]["teams"].reverse()
    reordered = validate_classic_portfolio_policy_bytes(
        json.dumps(payload, separators=(",", ":")).encode(),
        slate=slate,
        entry_ids=policy.entry_ids,
        entry_sha256=sha256_bytes(entry_bytes),
    )
    assert reordered.valid
    assert reordered.policy is not None
    assert reordered.normalized_sha256 == policy.normalized_sha256
    assert parse_normalized_classic_policy_bytes(policy.canonical_bytes()) == policy
    normalized = policy.as_mapping()
    assert normalized["bindings"]["salary_sha256"] == slate.salary_hash
    assert normalized["bindings"]["entry_sha256"] == sha256_bytes(entry_bytes)
    assert normalized["bindings"]["entry_ids"] == list(policy.entry_ids)
    assert normalized["effective"]["hard_controls_are_never_relaxed"] is True


def test_all_supported_bound_types_stack_groups_exclusion_and_audit() -> None:
    slate = _slate()
    people = {row.underlying_id: row for row in slate.players}
    excluded = people["NYJ|WR|6"]
    target = people["NE|QB|1"]
    group_people = [people["DAL|RB|1"], people["DAL|WR|1"]]
    controls = {
        "player_exposure_bounds": [
            {"underlying_id": target.underlying_id, "dk_id": target.dk_id, "minimum_entries": 1, "maximum_entries": 2, "hard": True}
        ],
        "team_exposure_bounds": [
            {"team": "NE", "minimum_entries": 1, "maximum_entries": 3, "hard": True}
        ],
        "game_exposure_bounds": [
            {"game_id": "NE@SEA", "minimum_entries": 1, "maximum_entries": 3, "hard": True}
        ],
        "exact_exclusions": [
            {"underlying_id": excluded.underlying_id, "dk_id": excluded.dk_id}
        ],
        "groups": [
            {
                "group_id": "dal-skill",
                "members": [
                    {"underlying_id": row.underlying_id, "dk_id": row.dk_id}
                    for row in group_people
                ],
                "minimum_players": 1,
                "maximum_players": 2,
                "minimum_entries": 1,
                "maximum_entries": 3,
                "strength": "HARD",
            }
        ],
        "stack_rules": [
            {
                "rule_id": "hard-qb-stack",
                "rule_type": "QB_PASS_CATCHER",
                "minimum_value": 1,
                "maximum_value": 4,
                "minimum_entries": 2,
                "maximum_entries": 3,
                "strength": "HARD",
            },
            {
                "rule_id": "advisory-bringback",
                "rule_type": "QB_BRINGBACK",
                "minimum_value": 1,
                "maximum_value": 6,
                "minimum_entries": 0,
                "maximum_entries": 3,
                "strength": "ADVISORY",
            },
        ],
        "max_pairwise_person_overlap": 8,
        "require_unique_lineups": True,
    }
    slate, policy, source, entry_bytes = _policy(3, controls=controls)
    bank = build_classic_candidate_bank(slate, _objective(slate), policy)
    selection = solve_classic_portfolio(policy, bank)
    assert selection.passed, (bank.as_report(), selection.as_report())
    audit, _candidate, _assignment = _audit(
        slate, policy, source, entry_bytes, bank, selection
    )
    assert audit.passed, audit.problems
    assert dict(audit.player_counts)[target.underlying_id] >= 1
    assert dict(audit.player_counts)[target.underlying_id] <= 2
    assert dict(audit.group_counts)["dal-skill"] >= 1
    assert dict(audit.stack_counts)["hard-qb-stack"] >= 2
    assert dict(audit.player_counts).get(excluded.underlying_id, 0) == 0
    assert all(value <= 8 for *_entries, value in audit.pairwise_overlap)
    assert any(
        stratum.kind == "player_cap_exclusion"
        and stratum.subject == target.underlying_id
        for stratum in bank.strata
    )


@pytest.mark.parametrize("entry_count", (1, 3, 20, 150))
def test_golden_portfolios_cover_every_entry_without_cycles(entry_count: int) -> None:
    slate, policy, _source, _entry = _policy(entry_count)
    bank = build_classic_candidate_bank(slate, _objective(slate), policy)
    selected = solve_classic_portfolio(policy, bank)
    assert selected.passed, (entry_count, bank.as_report(), selected.as_report())
    rosters = [bank.candidates[index].roster for index in selected.selected_candidate_indexes]
    assignments = exact_classic_assignments(policy.entry_ids, rosters)
    assert tuple(entry for entry, _roster in assignments) == policy.entry_ids
    assert len({tuple(roster) for _entry, roster in assignments}) == entry_count
    assert all(validate_lineup(slate, roster).valid for _entry, roster in assignments)
    assert bank.feasible_chain_status == "POLICY_FEASIBLE"
    assert bank.peak_traced_python_bytes > 0
    assert {
        "QB_SINGLE",
        "QB_DOUBLE",
        "NAKED_QB",
        "ZERO_BRINGBACK",
        "ONE_BRINGBACK",
        "TWO_PLUS_BRINGBACK",
    }.issubset(bank.coverage()["families"])


def test_candidate_bank_and_assignment_replay_are_byte_deterministic() -> None:
    slate, policy, _source, _entry = _policy(20)
    first = build_classic_candidate_bank(slate, _objective(slate), policy)
    second = build_classic_candidate_bank(slate, _objective(slate), policy)
    assert candidate_bank_bytes(policy, first) == candidate_bank_bytes(policy, second)
    first_selection = solve_classic_portfolio(policy, first)
    second_selection = solve_classic_portfolio(policy, second)
    assert first_selection.selected_candidate_indexes == second_selection.selected_candidate_indexes
    first_pairs = exact_classic_assignments(policy.entry_ids, [first.candidates[index].roster for index in first_selection.selected_candidate_indexes])
    second_pairs = exact_classic_assignments(policy.entry_ids, [second.candidates[index].roster for index in second_selection.selected_candidate_indexes])
    candidate_hash = sha256_bytes(candidate_bank_bytes(policy, first))
    assert assignment_artifact_bytes(policy, first_pairs, candidate_bank_sha256=candidate_hash) == assignment_artifact_bytes(policy, second_pairs, candidate_bank_sha256=candidate_hash)


@pytest.mark.parametrize(
    ("mutator", "expected"),
    [
        (lambda values: {"source_policy_bytes": values["source_policy_bytes"] + b" "}, "SOURCE_POLICY_SHA256_MISMATCH"),
        (lambda values: {"normalized_policy_bytes": values["normalized_policy_bytes"] + b" "}, "NORMALIZED_POLICY"),
        (lambda values: {"salary_bytes": values["salary_bytes"] + b" "}, "SALARY_SHA256_MISMATCH"),
        (lambda values: {"entry_bytes": values["entry_bytes"] + b" "}, "ENTRY_SHA256_MISMATCH"),
        (lambda values: {"bound_artifacts": {"team_prior_sha256": (b"changed", sha256_bytes(b"team-prior"))}}, "TEAM_PRIOR_SHA256_MISMATCH"),
        (lambda values: {"candidate_bytes": values["candidate_bytes"] + b" "}, "CANDIDATE_BANK"),
        (lambda values: {"assignment_bytes": values["assignment_bytes"] + b" "}, "ASSIGNMENT"),
    ],
)
def test_every_artifact_mutation_fails_independent_audit(mutator, expected) -> None:
    slate, policy, source, entry_bytes = _policy(3)
    bank = build_classic_candidate_bank(slate, _objective(slate), policy)
    selection = solve_classic_portfolio(policy, bank)
    passed, candidate, assignment = _audit(slate, policy, source, entry_bytes, bank, selection)
    assert passed.passed
    values = {
        "source_policy_bytes": source,
        "normalized_policy_bytes": policy.canonical_bytes(),
        "salary_bytes": b"salary",
        "entry_bytes": entry_bytes,
        "candidate_bytes": candidate,
        "assignment_bytes": assignment,
    }
    changes = mutator(values)
    audit, _candidate, _assignment = _audit(
        slate, policy, source, entry_bytes, bank, selection, **changes
    )
    assert not audit.passed
    assert any(expected in problem for problem in audit.problems)


def test_conflicting_policy_and_structural_capacity_fail_before_solver() -> None:
    slate = _slate()
    entries = ("E1", "E2", "E3")
    entry_sha = sha256_bytes(b"entry")
    document = classic_portfolio_policy_template(slate, entries, entry_sha256=entry_sha)
    document["controls"]["player_exposure_bounds"] = [
        {
            "underlying_id": row.underlying_id,
            "dk_id": row.dk_id,
            "minimum_entries": 0,
            "maximum_entries": 0,
            "hard": True,
        }
        for row in slate.players
    ]
    validation = validate_classic_portfolio_policy_bytes(
        json.dumps(document).encode(),
        slate=slate,
        entry_ids=entries,
        entry_sha256=entry_sha,
    )
    assert not validation.valid
    assert any("CAPACITY_INSUFFICIENT" in blocker for blocker in validation.blockers())


def test_candidate_bank_reports_structural_lineup_infeasibility() -> None:
    slate, policy, _source, _entry = _policy(1)
    all_qbs = tuple(row.dk_id for row in slate.players if row.position == "QB")
    bank = build_classic_candidate_bank(
        slate,
        _objective(slate),
        policy,
        excluded_ids=all_qbs,
    )
    assert bank.status == "STRUCTURAL_INFEASIBILITY"
    assert bank.blocking


def test_exhaustive_modeled_infeasibility_and_incomplete_bank_exhaustion_are_distinct() -> None:
    slate, policy, _source, _entry = _policy(3)
    real = build_classic_candidate_bank(slate, _objective(slate), policy)
    one = real.candidates[:2]
    exhaustive = ClassicCandidateBank(
        one, "EXHAUSTIVE_COMPLETION", True, 2, 3, 0.0, 1, 2, 0, 0.0, "kInfeasible", (), (), "MODELED_BANK_INFEASIBILITY"
    )
    incomplete = ClassicCandidateBank(
        one, "BOUNDED_COMPLETION", False, 2, 3, 0.0, 1, 2, 0, 0.0, "kOptimal", (), (), "INCOMPLETE_BANK_EXHAUSTION"
    )
    assert solve_classic_portfolio(policy, exhaustive).status == "MODELED_BANK_INFEASIBILITY"
    assert solve_classic_portfolio(policy, incomplete).status == "INCOMPLETE_BANK_EXHAUSTION"


@pytest.mark.parametrize(
    ("model_status", "expected"),
    [
        ("kTimeLimit", "CANDIDATE_BANK_TIMEOUT"),
        ("kIterationLimit", "CANDIDATE_BANK_SEARCH_LIMIT"),
        ("kSolveError", "CANDIDATE_BANK_SOLVER_ERROR"),
    ],
)
def test_candidate_timeout_search_limit_and_solver_error_are_distinct(
    monkeypatch, model_status, expected
) -> None:
    from nfl_dfs import classic_portfolio as module

    class StubOptimizer:
        def __init__(self, *_args, **_kwargs):
            pass

        def add_required_row(self, *_args):
            pass

        def add_selected_count_bounds(self, *_args, **_kwargs):
            pass

        def add_classic_qb_correlation_bounds(self, *_args, **_kwargs):
            pass

        def add_no_good(self, *_args):
            pass

        def set_time_limit(self, *_args):
            pass

        def solve(self, *_args):
            return SimpleNamespace(
                status="NO_SOLUTION",
                roster=None,
                model_status=model_status,
                node_count=None,
                mip_gap=None,
            )

    monkeypatch.setattr(module, "LineupOptimizer", StubOptimizer)
    slate, policy, _source, _entry = _policy(1)
    bank = build_classic_candidate_bank(slate, _objective(slate), policy)
    assert bank.status == expected
    assert bank.blocking


def _legal_rosters(slate: SlateContract, count: int) -> list[tuple[str, ...]]:
    """Distinct legal Classic rosters from the fixture slate, with no solver.

    QB, RB1, RB2, three WRs and the TE from one team, the opponent's WR1 at
    FLEX (a bring-back, so both default stack rules match), and a DST from
    another game. Every roster is checked by `validate_lineup`.
    """

    rows = {}
    for row in slate.players:
        rows.setdefault((row.team, row.position), []).append(row)
    games = {row.team: row.game_id for row in slate.players}
    opponents = {row.team: row.opponent for row in slate.players}
    teams = sorted(games)
    rosters: list[tuple[str, ...]] = []
    for team in teams:
        dst_team = next(other for other in teams if games[other] != games[team])
        qb, rb, te = rows[(team, "QB")][0], rows[(team, "RB")], rows[(team, "TE")][0]
        flex = rows[(opponents[team], "WR")][0]
        dst = rows[(dst_team, "DST")][0]
        for wrs in itertools.combinations(rows[(team, "WR")], 3):
            roster = tuple(
                row.dk_id for row in (qb, rb[0], rb[1], *wrs, te, flex, dst)
            )
            assert validate_lineup(slate, roster).lineup is not None, roster
            rosters.append(roster)
            if len(rosters) == count:
                return rosters
    raise AssertionError("fixture slate has too few rosters")


def _constructed_bank(slate, policy, rosters, *, chain=(), status="BOUNDED_COMPLETION"):
    """A bank built by hand, so no wall-clock HiGHS limit decides a test."""

    objective = _objective(slate)
    by_id = {row.dk_id: row for row in slate.players}
    candidates = []
    for roster in rosters:
        validation = validate_lineup(slate, roster)
        assert validation.lineup is not None
        rows = [by_id[dk_id] for dk_id in roster]
        people = frozenset(row.underlying_id for row in rows)
        candidates.append(
            ClassicCandidate(
                roster=tuple(roster),
                canonical_key=validation.lineup.canonical_key,
                people=people,
                teams=frozenset(row.team for row in rows),
                games=frozenset(row.game_id for row in rows),
                prior_points=sum(objective[dk_id] for dk_id in roster),
                families=(),
                group_matches=_group_matches(people, policy.groups),
                stack_matches=_stack_matches(slate, roster, policy.stack_rules),
                source_stratum="constructed",
                source_solver_status="OPTIMAL",
                source_model_status="kOptimal",
                source_mip_gap=0.0,
                source_node_count=1,
            )
        )
    return ClassicCandidateBank(
        tuple(candidates), status, False, len(candidates), policy.entry_count, 0.0, 0,
        len(candidates), 0, 0.0, "kOptimal", (), tuple(chain),
        "POLICY_FEASIBLE" if chain else "NOT_RUN",
    )


class _StubHighs:
    """The joint model's calls, recorded; the result is whatever the test sets."""

    model_status = highspy.HighsModelStatus.kOptimal
    info = SimpleNamespace(mip_gap=float("inf"), mip_node_count=0)
    solution = SimpleNamespace(value_valid=False, col_value=[])
    starts: list = []

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

    def setSolution(self, count, indexes, values):
        type(self).starts.append((count, list(indexes), list(values)))

    def run(self):
        pass

    def getModelStatus(self):
        return self.model_status

    def getInfo(self):
        return self.info

    def getSolution(self):
        return self.solution


@pytest.mark.parametrize(
    ("model_status", "expected"),
    [
        (highspy.HighsModelStatus.kTimeLimit, "PORTFOLIO_SELECTION_TIMEOUT"),
        (highspy.HighsModelStatus.kIterationLimit, "PORTFOLIO_SELECTION_SEARCH_LIMIT"),
        (highspy.HighsModelStatus.kSolveError, "PORTFOLIO_SELECTION_SOLVER_ERROR"),
    ],
)
def test_nonoptimal_and_solver_error_selection_states_fail_closed(model_status, expected) -> None:
    """No incumbent keeps today's codes.

    Deterministic since Session 08: the bank is constructed, not built on the
    template's wall-clock HiGHS limits, which under load once blocked the bank
    before this stub ran.
    """

    slate, policy, _source, _entry = _policy(1)
    bank = _constructed_bank(slate, policy, _legal_rosters(slate, 4))

    class StubHighs(_StubHighs):
        pass

    StubHighs.model_status = model_status
    result = solve_classic_portfolio(policy, bank, solver_factory=StubHighs)
    assert result.status == expected
    assert not result.passed


@pytest.mark.parametrize(
    "model_status",
    [
        highspy.HighsModelStatus.kTimeLimit,
        highspy.HighsModelStatus.kIterationLimit,
        highspy.HighsModelStatus.kSolutionLimit,
    ],
)
def test_nonoptimal_limit_with_a_valid_incumbent_returns_it_validated(model_status) -> None:
    """A limit that leaves a valid integer incumbent returns it, labelled, never optimal."""

    slate, policy, source, entry = _policy(3)
    # The witness (3, 4, 5) scores below the incumbent (0, 1, 3), so HiGHS's stands.
    bank = _constructed_bank(slate, policy, _legal_rosters(slate, 6), chain=(3, 4, 5))

    class StubHighs(_StubHighs):
        starts = []
        info = SimpleNamespace(mip_gap=0.0125, mip_node_count=37)
        solution = SimpleNamespace(value_valid=True, col_value=[1.0, 1.0, 0.0, 1.0, 0.0, 0.0])

    StubHighs.model_status = model_status
    result = solve_classic_portfolio(policy, bank, solver_factory=StubHighs)
    assert result.status == "FEASIBLE_LIMIT_ACTUAL_CANDIDATE_BANK"
    assert result.passed and not result.proven_optimal
    assert sorted(result.selected_candidate_indexes) == [0, 1, 3]
    assert (result.mip_gap, result.node_count, result.model_status) == (0.0125, 37, model_status.name)
    report = result.as_report()
    assert report["optimality_scope"] is None
    assert (report["mip_start"], report["incumbent_source"]) == ("POLICY_FEASIBLE_WITNESS", "JOINT_SOLVE")
    assert StubHighs.starts == [(3, [3, 4, 5], [1.0, 1.0, 1.0])]  # the witness seeded it
    audit, _candidate, _assignment = _audit(slate, policy, source, entry, bank, result)
    assert audit.passed, audit.problems


def test_nonoptimal_limit_never_delivers_less_than_the_witness() -> None:
    """An incumbent below the witness gives way to it; a limit with none returns it."""

    slate, policy, source, entry = _policy(3)
    bank = _constructed_bank(slate, policy, _legal_rosters(slate, 6), chain=(0, 1, 2))

    class Weaker(_StubHighs):
        model_status = highspy.HighsModelStatus.kTimeLimit
        solution = SimpleNamespace(value_valid=True, col_value=[0.0, 0.0, 0.0, 1.0, 1.0, 1.0])

    class Empty(_StubHighs):
        model_status = highspy.HighsModelStatus.kIterationLimit

    for stub in (Weaker, Empty):
        result = solve_classic_portfolio(policy, bank, solver_factory=stub)
        assert result.status == "FEASIBLE_LIMIT_ACTUAL_CANDIDATE_BANK", stub
        assert sorted(result.selected_candidate_indexes) == [0, 1, 2]
        assert result.as_report()["incumbent_source"] == "POLICY_FEASIBLE_WITNESS"
        assert result.model_status == stub.model_status.name and not result.proven_optimal
        audit, _candidate, _assignment = _audit(slate, policy, source, entry, bank, result)
        assert audit.passed, audit.problems

    class Broken(_StubHighs):
        model_status = highspy.HighsModelStatus.kSolveError

    # A solver error is not a limit: the witness never covers it.
    assert solve_classic_portfolio(policy, bank, solver_factory=Broken).status == "PORTFOLIO_SELECTION_SOLVER_ERROR"


@pytest.mark.parametrize(
    "col_value",
    [
        [0.5, 0.5, 1.0, 1.0, 0.0, 0.0],  # not integral
        [1.0, 1.0, 0.0, 0.0, 0.0, 0.0],  # two lineups for three entries
    ],
)
def test_nonoptimal_incumbent_failing_the_optimums_checks_fails_closed(col_value) -> None:
    slate, policy, _source, _entry = _policy(3)
    bank = _constructed_bank(slate, policy, _legal_rosters(slate, 6))

    class StubHighs(_StubHighs):
        model_status = highspy.HighsModelStatus.kTimeLimit
        solution = SimpleNamespace(value_valid=True, col_value=col_value)

    result = solve_classic_portfolio(policy, bank, solver_factory=StubHighs)
    assert (result.status, result.model_status) == ("PORTFOLIO_SELECTION_SOLVER_ERROR", "INVALID_INTEGER_SOLUTION")
    assert not result.passed and result.selected_candidate_indexes == ()


def _node_limited_highs() -> highspy.Highs:
    """Real HiGHS, stopped before its first branch-and-bound node: a search limit, no clock."""

    model = highspy.Highs()
    model.setOptionValue("mip_max_nodes", 0)
    return model


@pytest.mark.parametrize("presolve", ["on", "off"])
def test_nonoptimal_real_highs_time_limit_returns_the_witness_validated(presolve) -> None:
    """A real HiGHS time limit, 1e-9 s: the clock can only stop it sooner, never change the outcome.

    With presolve on, HiGHS returns the witness start itself; with presolve off
    it loses the start that early, and the selector returns the witness.
    """

    slate, policy, source, entry = _policy(3)
    rosters = _legal_rosters(slate, 12)
    bank = _constructed_bank(slate, policy, rosters, chain=(9, 10, 11))

    def factory() -> highspy.Highs:
        model = highspy.Highs()
        model.setOptionValue("presolve", presolve)
        return model

    result = solve_classic_portfolio(policy, bank, time_limit_seconds=1e-9, solver_factory=factory)
    assert (result.status, result.model_status) == ("FEASIBLE_LIMIT_ACTUAL_CANDIDATE_BANK", "kTimeLimit")
    assert sorted(result.selected_candidate_indexes) == [9, 10, 11]
    assert result.as_report()["incumbent_source"] in {"JOINT_SOLVE", "POLICY_FEASIBLE_WITNESS"}
    assert result.as_report()["optimality_scope"] is None and not result.proven_optimal
    audit, _candidate, _assignment = _audit(slate, policy, source, entry, bank, result)
    assert audit.passed, audit.problems


def test_nonoptimal_real_highs_node_limit_returns_the_witness_start_validated() -> None:
    """highspy 1.11.0 returns the witness MIP start as the incumbent under a node limit."""

    slate, policy, source, entry = _policy(3)
    rosters = _legal_rosters(slate, 12)
    objective = _objective(slate)
    weakest = sorted(range(len(rosters)), key=lambda index: sum(objective[d] for d in rosters[index]))[:3]
    bank = _constructed_bank(slate, policy, rosters, chain=tuple(weakest))
    result = solve_classic_portfolio(policy, bank, solver_factory=_node_limited_highs)
    assert result.status == "FEASIBLE_LIMIT_ACTUAL_CANDIDATE_BANK"
    assert result.model_status == "kSolutionLimit"
    assert result.as_report()["optimality_scope"] is None
    assert sorted(result.selected_candidate_indexes) == sorted(weakest)
    optimum = solve_classic_portfolio(policy, bank)
    assert optimum.status == "OPTIMAL_ACTUAL_CANDIDATE_BANK" and optimum.proven_optimal
    assert result.objective_prior_points < optimum.objective_prior_points  # an incumbent, not the optimum
    audit, _candidate, _assignment = _audit(slate, policy, source, entry, bank, result)
    assert audit.passed, audit.problems
    # With no witness to start from, the same limit leaves no incumbent: today's code.
    bare = replace(bank, feasible_chain_indexes=(), feasible_chain_status="NOT_RUN")
    unseeded = solve_classic_portfolio(policy, bare, solver_factory=_node_limited_highs)
    assert (unseeded.status, unseeded.passed) == ("PORTFOLIO_SELECTION_SEARCH_LIMIT", False)


class _ScriptedOptimizer:
    """A `LineupOptimizer` stand-in that plays a script, so no wall clock decides a bank.

    Every stratum's optimizer reads the same class-level script; when it runs
    out, each solve reports the model infeasible.
    """

    script: list = []

    def __init__(self, *_args, **_kwargs):
        pass

    def add_required_row(self, *_args):
        pass

    def add_selected_count_bounds(self, *_args, **_kwargs):
        pass

    def add_classic_qb_correlation_bounds(self, *_args, **_kwargs):
        pass

    def add_no_good(self, *_args):
        pass

    def add_person_overlap_limit(self, *_args):
        pass

    def set_time_limit(self, *_args):
        pass

    def solve(self, *_args):
        if not type(self).script:
            return SimpleNamespace(status="INFEASIBLE", roster=None, model_status="kInfeasible",
                                   node_count=0, mip_gap=None)
        status, model_status, roster = type(self).script.pop(0)
        return SimpleNamespace(status=status, roster=roster, model_status=model_status,
                               node_count=7, mip_gap=0.02 if status == "FEASIBLE_LIMIT" else 0.0)


def _scripted(monkeypatch, script):
    from nfl_dfs import classic_portfolio as module

    class Scripted(_ScriptedOptimizer):
        pass

    Scripted.script = list(script)
    monkeypatch.setattr(module, "LineupOptimizer", Scripted)
    return module


# The witness's joint solve still runs on real HiGHS; a selection budget no
# small bank can reach keeps its clock out of these tests.
_UNREACHABLE_SELECTION = {"selection_milliseconds": 3_600_000}
# The same for a real bank's candidate solves, whose outcome a search limit
# decides: no clock limit a small bank can reach.
UNREACHABLE_LIMITS = {
    "candidate_total_milliseconds": 3_600_000,
    "candidate_per_solve_milliseconds": 300_000,
    "selection_milliseconds": 3_600_000,
}


def test_a_limit_stopped_candidate_solve_keeps_its_roster_labelled(monkeypatch) -> None:
    slate, policy, _source, _entry = _policy(3, limits=_UNREACHABLE_SELECTION)
    rosters = _legal_rosters(slate, 12)
    script = [("FEASIBLE_LIMIT", "kTimeLimit", rosters[0]), ("FEASIBLE_LIMIT", "kSolutionLimit", rosters[1]),
              ("FEASIBLE_LIMIT", "kIterationLimit", rosters[2])]
    script += [("OPTIMAL", "kOptimal", roster) for roster in rosters[3:]]
    _scripted(monkeypatch, script)
    bank = build_classic_candidate_bank(slate, _objective(slate), policy)
    assert not bank.blocking and bank.status in {"BOUNDED_COMPLETION", "EXHAUSTIVE_COMPLETION"}
    kept = [candidate for candidate in bank.candidates if candidate.source_solver_status == "FEASIBLE_LIMIT"]
    assert [candidate.roster for candidate in kept] == rosters[:3]
    assert [candidate.source_model_status for candidate in kept] == ["kTimeLimit", "kSolutionLimit", "kIterationLimit"]
    assert all(candidate.source_mip_gap == 0.02 and candidate.source_node_count == 7 for candidate in kept)
    # Each counted toward its family stratum's target like any candidate.
    families = [stratum for stratum in bank.strata if stratum.kind == "family"]
    assert [(item.qualifying, item.termination) for item in families[:3]] == [(1, "TARGET_REACHED")] * 3
    assert bank.as_report()["limit_incumbent_candidates"] == 3
    assert solve_classic_portfolio(policy, bank).passed


@pytest.mark.parametrize("model_status", ["kTimeLimit", "kIterationLimit", "kSolutionLimit"])
def test_an_illegal_roster_at_a_limit_still_blocks_the_bank(monkeypatch, model_status) -> None:
    """The optimizer refusing its own incumbent is a solver error, never a limit stop."""

    slate, policy, _source, _entry = _policy(3, limits=_UNREACHABLE_SELECTION)
    rosters = _legal_rosters(slate, 40)
    illegal = (rosters[0][0],) * 9  # the same QB in every slot
    assert validate_lineup(slate, illegal).lineup is None
    script = [("OPTIMAL", "kOptimal", roster) for roster in rosters[:10]]
    script.append(("NO_SOLUTION", model_status, illegal))
    _scripted(monkeypatch, script)
    bank = build_classic_candidate_bank(slate, _objective(slate), policy)
    assert len(bank.candidates) >= policy.entry_count  # enough, and a witness: still blocked
    assert (bank.status, bank.blocking) == ("CANDIDATE_BANK_SOLVER_ERROR", True)
    assert ("stack", "ILLEGAL_SOLVER_ROSTER") in [(item.kind, item.termination) for item in bank.strata]


def _stop_in_the_fill(monkeypatch, module, *, after: int) -> None:
    """The bank's total budget runs out `after` solves into the top-k fill."""

    real_enumerate = module._Enumerator.enumerate
    real_elapsed = module._Enumerator.elapsed

    def enumerate_(self, *, kind, **kwargs):
        if kind == "top_k_fill":
            self.stop_after = self.solve_count + after
        return real_enumerate(self, kind=kind, **kwargs)

    def elapsed(self):
        stop = getattr(self, "stop_after", None)
        if stop is not None and self.solve_count >= stop:
            return self.total_budget + 0.25
        return real_elapsed(self)

    monkeypatch.setattr(module._Enumerator, "enumerate", enumerate_)
    monkeypatch.setattr(module._Enumerator, "elapsed", elapsed)


def test_a_bank_stopped_by_its_total_budget_with_a_witness_does_not_block(monkeypatch) -> None:
    from nfl_dfs.deadline import bank_rate_observation

    slate, policy, _source, _entry = _policy(3, limits=_UNREACHABLE_SELECTION)
    rosters = _legal_rosters(slate, 40)
    module = _scripted(monkeypatch, [("OPTIMAL", "kOptimal", roster) for roster in rosters])
    _stop_in_the_fill(monkeypatch, module, after=2)
    bank = build_classic_candidate_bank(slate, _objective(slate), policy)
    assert bank.status == "BOUNDED_TIME_LIMIT_STOP" and not bank.blocking and not bank.exhaustive
    assert bank.feasible_chain_status == "POLICY_FEASIBLE"
    assert len(bank.candidates) >= policy.entry_count
    assert bank.strata[-1].kind == "top_k_fill" and bank.strata[-1].termination == "TIMEOUT"
    selection = solve_classic_portfolio(policy, bank)
    assert selection.proven_optimal and selection.as_report()["mip_start"] == "POLICY_FEASIBLE_WITNESS"
    # run-slate still records this host's rate from the bank's own report.
    report = {"selection": {"selection": {"portfolio_policy": {"candidate_bank": bank.as_report()}}}}
    blockers = ("CANDIDATE_BANK_STOPPED_AT_LIMIT: the candidate bank stopped at its BOUNDED_TIME_LIMIT_STOP",)
    observed = bank_rate_observation(report, blockers, declared_bank_seconds=30.0)
    assert observed == (len(bank.candidates), round(bank.elapsed_seconds, 6), "BANK_REPORT")


@pytest.mark.parametrize("model_status", ["kIterationLimit", "kSolutionLimit"])
def test_a_bank_stopped_by_a_search_limit_with_a_witness_does_not_block(monkeypatch, model_status) -> None:
    slate, policy, _source, _entry = _policy(3, limits=_UNREACHABLE_SELECTION)
    rosters = _legal_rosters(slate, 40)
    script = [("OPTIMAL", "kOptimal", roster) for roster in rosters[:10]]
    script.append(("NO_SOLUTION", model_status, None))
    _scripted(monkeypatch, script)
    bank = build_classic_candidate_bank(slate, _objective(slate), policy)
    assert bank.status == "BOUNDED_SEARCH_LIMIT_STOP" and not bank.blocking
    terminations = [(stratum.kind, stratum.termination) for stratum in bank.strata]
    stopped = terminations.index(("stack", "SEARCH_LIMIT"))
    # Later solver strata do not run; the solver-free witness chain still does.
    assert all(term == "NOT_RUN_AFTER_LIMIT_STOP" for kind, term in terminations[stopped + 1:]
               if kind != "policy_feasible_chain")
    assert ("policy_feasible_chain", "TARGET_REACHED") in terminations[stopped + 1:]
    assert bank.feasible_chain_status == "POLICY_FEASIBLE"
    assert solve_classic_portfolio(policy, bank).passed


def test_a_limit_stopped_bank_without_enough_or_without_a_witness_still_blocks(monkeypatch) -> None:
    slate, policy, _source, _entry = _policy(3, limits=_UNREACHABLE_SELECTION)
    rosters = _legal_rosters(slate, 40)
    # Two candidates for three entries.
    module = _scripted(monkeypatch, [("OPTIMAL", "kOptimal", rosters[0]), ("NO_SOLUTION", "kTimeLimit", None)])
    monkeypatch.setattr(module._Enumerator, "expand_validated_neighbors",
                        lambda self, *, kind, target, subject=None: None)
    few = build_classic_candidate_bank(slate, _objective(slate), policy)
    assert (few.status, few.blocking) == ("CANDIDATE_BANK_TIMEOUT", True)
    assert solve_classic_portfolio(policy, few).model_status == "NOT_RUN_BLOCKING_BANK"
    monkeypatch.undo()
    # Enough candidates, but the witness failed.
    module = _scripted(monkeypatch, [("OPTIMAL", "kOptimal", roster) for roster in rosters])
    _stop_in_the_fill(monkeypatch, module, after=2)
    real_solve = module.solve_classic_portfolio

    def no_witness(policy, bank, **kwargs):
        if bank.feasible_chain_status == "PENDING":
            return replace(real_solve(policy, bank, **kwargs), status="INCOMPLETE_BANK_EXHAUSTION",
                           selected_candidate_indexes=())
        return real_solve(policy, bank, **kwargs)

    monkeypatch.setattr(module, "solve_classic_portfolio", no_witness)
    unwitnessed = build_classic_candidate_bank(slate, _objective(slate), policy)
    assert len(unwitnessed.candidates) >= policy.entry_count
    assert unwitnessed.feasible_chain_status == "INCOMPLETE_BANK_EXHAUSTION"
    assert (unwitnessed.status, unwitnessed.blocking) == ("CANDIDATE_BANK_TIMEOUT", True)


def test_a_real_highs_candidate_solve_stopped_by_a_search_limit_keeps_its_roster(monkeypatch) -> None:
    """`mip_max_improving_sols=1`: real HiGHS stops some solves at kSolutionLimit with a roster."""

    from nfl_dfs import classic_portfolio as module
    from nfl_dfs.optimizer import LineupOptimizer

    class FirstImprovingSolution(LineupOptimizer):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._highs.setOptionValue("mip_max_improving_sols", 1)

    monkeypatch.setattr(module, "LineupOptimizer", FirstImprovingSolution)
    slate, policy, source, entry = _policy(3, limits=UNREACHABLE_LIMITS)
    bank = build_classic_candidate_bank(slate, _objective(slate), policy)
    assert not bank.blocking, bank.status
    kept = [candidate for candidate in bank.candidates if candidate.source_solver_status == "FEASIBLE_LIMIT"]
    assert kept and {candidate.source_model_status for candidate in kept} == {"kSolutionLimit"}
    selection = solve_classic_portfolio(policy, bank)
    assert selection.passed
    audit, _candidate, _assignment = _audit(slate, policy, source, entry, bank, selection)
    assert audit.passed, audit.problems


def test_c3_full_prior_review_writes_bound_review_package_and_replays(tmp_path: Path) -> None:
    salary, entry, package, role, status, _inactive = _fixture(
        tmp_path / "fixture", entries=3
    )
    from nfl_dfs.dk import parse_entries, parse_salaries

    slate = parse_salaries(salary)
    entries = parse_entries(entry)
    document = classic_portfolio_policy_template(
        slate,
        tuple(item.entry_id for item in entries.authorizations),
        entry_sha256=entries.raw_hash,
    )
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(json.dumps(document, indent=2), encoding="utf-8")
    validation = validate_classic_portfolio_policy_bytes(
        policy_path.read_bytes(),
        slate=slate,
        entry_ids=tuple(item.entry_id for item in entries.authorizations),
        entry_sha256=entries.raw_hash,
    )
    assert validation.policy is not None and validation.valid
    normalized = write_normalized_classic_portfolio_policy(
        tmp_path / "policy.normalized.json", validation.policy
    )

    def run(name: str):
        return run_prior_review(
            salary_csv=salary,
            entry_csv=entry,
            label="classic-c2",
            as_of=AS_OF,
            run_root=tmp_path / name / "run",
            output_root=tmp_path / name / "out",
            prior_package_dir=package,
            build_priors=True,
            official_status_csv=status,
            offensive_role_evidence_json=role,
            portfolio_policy=validation.policy,
            portfolio_policy_source_path=policy_path,
            portfolio_policy_source_sha256=sha256_file(policy_path),
            portfolio_policy_normalized_path=normalized,
            portfolio_policy_normalized_sha256=sha256_file(normalized),
            project=build_projection_package,
        )

    first = run("first")
    second = run("second")
    assert not first.blocked, first.blockers
    assert first.profile_version == "cowork_classic_prior_review_c3_v1"
    assert first.reports["classic_portfolio_audit"]["status"] == "PASS"
    for key in (
        "classic_candidate_bank",
        "classic_assignment",
        "classic_portfolio_audit",
        "selection_report",
        "complete_slate_coverage",
        "classic_selected_scores",
        "classic_export_audit",
        "bulk_entry_csv",
        "readable_review_json",
        "readable_review_html",
    ):
        assert Path(first.artifacts[key]).is_file()
        assert first.hashes[key] == second.hashes[key]
    assert json.loads(Path(first.artifacts["selection_report"]).read_text())["schema_version"] == "nfl_classic_prior_review_selection_c2_v1"
    # Since Q1C each run also writes `assignments.csv`, the nine-slot
    # `nfl_assignment_csv_v1` record `settle` reads. It is deterministic like
    # every other bound artifact, and it is not an upload shape: no Contest ID,
    # Contest Name, Entry Fee or instructions block, so DraftKings would reject
    # it. The upload-shape prohibitions below are unchanged.
    assert len(list(tmp_path.rglob("assignments.csv"))) == 2
    assert first.hashes["assignments"] == second.hashes["assignments"]
    assert len(list(tmp_path.rglob("DK_REVIEW_ENTRY_*.csv"))) == 2
    assert not list(tmp_path.rglob("DK_UPLOAD_*.csv"))


def test_c2_required_player_without_current_activity_stops_before_publish(
    tmp_path: Path,
) -> None:
    salary, entry, package, role, status, _inactive = _fixture(
        tmp_path / "fixture", entries=1
    )
    from nfl_dfs.dk import parse_entries, parse_salaries

    slate = parse_salaries(salary)
    entries = parse_entries(entry)
    required = next(row for row in slate.players if row.position == "QB")
    status_lines = status.read_text(encoding="utf-8").splitlines()
    status.write_text(
        "\n".join(
            line for line in status_lines if f",{required.dk_id}," not in line
        )
        + "\n",
        encoding="utf-8",
        newline="",
    )
    document = classic_portfolio_policy_template(
        slate,
        tuple(item.entry_id for item in entries.authorizations),
        entry_sha256=entries.raw_hash,
        controls={
            "player_exposure_bounds": [
                {
                    "underlying_id": required.underlying_id,
                    "dk_id": required.dk_id,
                    "minimum_entries": 1,
                    "maximum_entries": 1,
                    "hard": True,
                }
            ]
        },
    )
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(json.dumps(document, indent=2), encoding="utf-8")
    validation = validate_classic_portfolio_policy_bytes(
        policy_path.read_bytes(),
        slate=slate,
        entry_ids=tuple(item.entry_id for item in entries.authorizations),
        entry_sha256=entries.raw_hash,
    )
    assert validation.policy is not None and validation.valid
    normalized = write_normalized_classic_portfolio_policy(
        tmp_path / "policy.normalized.json", validation.policy
    )
    outcome = run_prior_review(
        salary_csv=salary,
        entry_csv=entry,
        label="classic-c2-missing-activity",
        as_of=AS_OF,
        run_root=tmp_path / "run",
        output_root=tmp_path / "out",
        prior_package_dir=package,
        build_priors=True,
        official_status_csv=status,
        offensive_role_evidence_json=role,
        portfolio_policy=validation.policy,
        portfolio_policy_source_path=policy_path,
        portfolio_policy_source_sha256=sha256_file(policy_path),
        portfolio_policy_normalized_path=normalized,
        portfolio_policy_normalized_sha256=sha256_file(normalized),
        project=build_projection_package,
    )
    assert outcome.blocked
    assert outcome.blockers[0].startswith("SELECTED_CURRENT_EVIDENCE_REQUIRED:")
    assert required.underlying_id in outcome.blockers[0]
    assert "classic_candidate_bank" not in outcome.artifacts
    assert "classic_assignment" not in outcome.artifacts
    assert "selection_report" not in outcome.artifacts


def test_one_cowork_command_dispatches_classic_c3_review_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nfl_dfs import cli
    from nfl_dfs.dk import parse_entries, parse_salaries
    from .test_prior_review_profile import _cowork_args

    salary, entry, package, role, status, _inactive = _fixture(
        tmp_path / "fixture", entries=3
    )
    attachments = tmp_path / "attachments"
    attachments.mkdir()
    attached_salary = attachments / "salary.csv"
    attached_entry = attachments / "entries.csv"
    attached_salary.write_bytes(salary.read_bytes())
    attached_entry.write_bytes(entry.read_bytes())
    slate = parse_salaries(attached_salary)
    entries = parse_entries(attached_entry)
    policy_path = tmp_path / "classic_policy.json"
    policy_path.write_text(
        json.dumps(
            classic_portfolio_policy_template(
                slate,
                tuple(item.entry_id for item in entries.authorizations),
                entry_sha256=entries.raw_hash,
            ),
            indent=2,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(cli, "DEFAULT_RUNS_DIR", tmp_path / "runs")
    code = cli.command_cowork_run(
        _cowork_args(
            tmp_path,
            attachments,
            label="classic-c2-cli",
            run_id="classic-c2-cli",
            prior_package_dir=str(package),
            build_priors=True,
            official_status_csv=str(status),
            offensive_role_evidence_json=str(role),
            portfolio_policy_json=str(policy_path),
            as_of=AS_OF.isoformat(),
        )
    )
    assert code == 0
    report = json.loads(
        (tmp_path / "outputs" / "classic-c2-cli" / "cowork_run.json").read_text(
            encoding="utf-8"
        )
    )
    assert report["stage"] == "PRIOR_ONLY_CLASSIC_C3_REVIEW_EXPORT"
    assert report["FILE_VALID"] is True
    assert report["MODEL_STATUS"] == "PRIOR_ONLY"
    assert report["RELEASE_DECISION"] == "DO_NOT_UPLOAD"
    assert report["portfolio_policy"]["enforcement_status"] == (
        "ENFORCED_AND_INDEPENDENTLY_AUDITED"
    )
    for key in (
        "classic_candidate_bank",
        "classic_assignment",
        "classic_portfolio_audit",
        "selection_report",
        "complete_slate_coverage",
        "classic_selected_scores",
        "classic_export_audit",
        "bulk_entry_csv",
        "readable_review_json",
        "readable_review_html",
    ):
        assert Path(report["prior_review_artifacts"][key]).is_file()
    assert Path(report["review_workbook"]).is_file()
    assert len(list(tmp_path.rglob("DK_REVIEW_ENTRY_*.csv"))) == 1
    assert not list(tmp_path.rglob("DK_UPLOAD_*.csv"))


def test_c3_enforcement_never_calls_quantitative_or_later_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nfl_dfs import (
        cli,
        economics,
        field,
        ownership,
        portfolio,
        prior_review as prior_module,
    )
    from nfl_dfs.dk import parse_entries, parse_salaries
    from .test_prior_review_profile import _cowork_args

    def forbidden(*_args, **_kwargs):
        raise AssertionError("prohibited C3-or-later path called")

    monkeypatch.setattr(economics, "evaluate_candidates_against_field", forbidden)
    monkeypatch.setattr(field, "generate_opponent_field", forbidden)
    monkeypatch.setattr(ownership, "cold_start_states", forbidden)
    monkeypatch.setattr(portfolio, "select_portfolio", forbidden)
    for name in (
        "evaluate_candidates_against_field",
        "generate_opponent_field",
        "cold_start_states",
        "select_portfolio",
        "write_assignments_csv",
    ):
        monkeypatch.setattr(cli, name, forbidden)

    # Since Q1C the Classic prior-review path does write `assignments.csv`, so
    # that a Classic run can bind its own selection into a pre-lock manifest and
    # become settleable. The real hazard the old blanket ban guarded against is
    # narrower and is still checked here: writing a Showdown-shaped six-column
    # CPT/FLEX file for a nine-slot Classic roster. A spy that asserts the mode
    # is a stronger check than refusing the call, because it also proves the
    # geometry is right rather than only that nothing happened.
    real_writer = prior_module.write_assignments_csv
    observed_modes: list[EngineMode] = []

    def spy(path, assignments, *, entry_order=None, mode=EngineMode.SHOWDOWN):
        observed_modes.append(mode)
        return real_writer(path, assignments, entry_order=entry_order, mode=mode)

    monkeypatch.setattr(prior_module, "write_assignments_csv", spy)

    salary, entry, package, role, status, _inactive = _fixture(
        tmp_path / "fixture", entries=1
    )
    attachments = tmp_path / "attachments"
    attachments.mkdir()
    attached_salary = attachments / "salary.csv"
    attached_entry = attachments / "entries.csv"
    attached_salary.write_bytes(salary.read_bytes())
    attached_entry.write_bytes(entry.read_bytes())
    slate = parse_salaries(attached_salary)
    entries = parse_entries(attached_entry)
    policy_path = tmp_path / "classic_policy.json"
    policy_path.write_text(
        json.dumps(
            classic_portfolio_policy_template(
                slate,
                tuple(item.entry_id for item in entries.authorizations),
                entry_sha256=entries.raw_hash,
            )
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(cli, "DEFAULT_RUNS_DIR", tmp_path / "runs")
    code = cli.command_cowork_run(
        _cowork_args(
            tmp_path,
            attachments,
            label="classic-c2-boundary",
            run_id="classic-c2-boundary",
            prior_package_dir=str(package),
            build_priors=True,
            official_status_csv=str(status),
            offensive_role_evidence_json=str(role),
            portfolio_policy_json=str(policy_path),
            as_of=AS_OF.isoformat(),
        )
    )
    assert code == 0
    # Nine-slot Classic geometry, never the six-column Showdown shape.
    assert observed_modes == [EngineMode.CLASSIC], observed_modes
    assert len(list(tmp_path.rglob("prior_only_readable_review.html"))) == 1
    assert len(list(tmp_path.rglob("DK_REVIEW_ENTRY_*.csv"))) == 1
    assert not list(tmp_path.rglob("DK_UPLOAD_*.csv"))


def test_c3_readable_reconciliation_failure_keeps_the_validated_csv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R28 (Session 05) changed this expectation, visibly.

    Until Session 05 this test was
    `test_c3_readable_reconciliation_failure_removes_new_review_outputs`: an
    unregistered forced code removed the CSV, its audit and the readable files.
    A presentation-only code (the readable JSON's hash, `P`) now keeps the
    independently validated CSV and its audit listed and published, and removes
    only the readable JSON and HTML. The unregistered code, which still
    withholds everything, moved to `tests/test_artifact_preservation.py`.
    """
    from nfl_dfs import cli
    from nfl_dfs import delivery
    from nfl_dfs.dk import parse_entries, parse_salaries
    from .test_prior_review_profile import _cowork_args

    salary, entry, package, role, status, _inactive = _fixture(
        tmp_path / "fixture", entries=1
    )
    attachments = tmp_path / "attachments"
    attachments.mkdir()
    attached_salary = attachments / "salary.csv"
    attached_entry = attachments / "entries.csv"
    attached_salary.write_bytes(salary.read_bytes())
    attached_entry.write_bytes(entry.read_bytes())
    slate = parse_salaries(attached_salary)
    entries = parse_entries(attached_entry)
    policy_path = tmp_path / "classic_policy.json"
    policy_path.write_text(
        json.dumps(
            classic_portfolio_policy_template(
                slate,
                tuple(item.entry_id for item in entries.authorizations),
                entry_sha256=entries.raw_hash,
            )
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(cli, "DEFAULT_RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(
        cli,
        "verify_readable_review_artifacts",
        lambda **_kwargs: ("READABLE_REVIEW_JSON_SHA256_MISMATCH:actual=forced:expected=pinned",),
    )
    code = cli.command_cowork_run(
        _cowork_args(
            tmp_path,
            attachments,
            label="classic-c3-display-failure",
            run_id="classic-c3-display-failure",
            prior_package_dir=str(package),
            build_priors=True,
            official_status_csv=str(status),
            offensive_role_evidence_json=str(role),
            portfolio_policy_json=str(policy_path),
            as_of=AS_OF.isoformat(),
        )
    )
    assert code == 2
    report = json.loads(
        (
            tmp_path
            / "outputs"
            / "classic-c3-display-failure"
            / "cowork_run.json"
        ).read_text(encoding="utf-8")
    )
    assert report["stage"] == "PRIOR_ONLY_CLASSIC_C3_REVIEW_EXPORT_READABLE_REVIEW_FAILED"
    assert report["FILE_VALID"] is True
    assert report["RELEASE_DECISION"] == "DO_NOT_UPLOAD"
    assert report["DELIVERY_STATE"] == "DELIVERABLE"
    assert report["blockers"][0].startswith(
        "CLASSIC_C3_READABLE_REVIEW_FAILED:ReadableReviewError:READABLE_REVIEW_JSON_SHA256_MISMATCH:"
    )
    assert report["export"]["bulk_entry_csv"] == report["bulk_entry_csv"]
    assert report["export"]["downstream_audit"] is not None
    assert report["export"]["readable_review_json"] is None
    for key in ("classic_export_audit", "bulk_entry_csv", "latest_deliverable"):
        assert key in report["prior_review_artifacts"] and key in report["prior_review_hashes"]
    for key in ("readable_review_json", "readable_review_html"):
        assert key not in report["prior_review_artifacts"]
    [csv_path] = list(tmp_path.rglob("DK_REVIEW_ENTRY_*.csv"))
    assert sha256_file(csv_path) == report["bulk_entry_sha256"]
    assert len(list(tmp_path.rglob("classic_review_export_audit.json"))) == 1
    assert not list(tmp_path.rglob("prior_only_readable_review.json"))
    assert not list(tmp_path.rglob("prior_only_readable_review.html"))
    assert not list(tmp_path.rglob("DK_UPLOAD_*.csv"))
    limitations = {
        item["code"]: item["class"] for item in report["release_truths"]["delivery_limitations"]
    }
    assert limitations["READABLE_REVIEW_JSON_SHA256_MISMATCH"] == "P"
    latest = delivery.read_latest(tmp_path / "outputs" / "classic-c3-display-failure")
    assert latest is not None and latest.deliverable.path == csv_path
