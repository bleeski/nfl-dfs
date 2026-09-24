"""C2 bounded Classic candidate bank, joint selection, and independent audit.

Only the prior-only central estimate enters the objective.  This module does
not import field, ownership, duplication, payout, economics, simulation, or C3
export code.
"""

from __future__ import annotations

import json
import math
import time
import tracemalloc
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, Mapping, Sequence

import highspy
import numpy as np

from .candidate_families import classify_candidate
from .classic_portfolio_policy import (
    GroupRule,
    NormalizedClassicPortfolioPolicy,
    StackRule,
    parse_normalized_classic_policy_bytes,
)
from .contracts import EngineMode, SlateContract
from .hashing import sha256_bytes
from .lineups import roster_canonical_key, validate_lineup
from .optimizer import LIMIT_INCUMBENT_STATUS, LineupOptimizer
from .portfolio_policy import canonical_decimal_json_bytes


ENFORCEMENT_VERSION = "prior_only_classic_portfolio_enforcement_c2_v1"
CANDIDATE_BANK_SCHEMA = "nfl_classic_candidate_bank_c2_v1"
ASSIGNMENT_SCHEMA = "nfl_classic_portfolio_assignment_c2_v1"
AUDIT_VERSION = "prior_only_classic_portfolio_audit_c2_v1"

# A time- or search-limited incumbent passes like the optimum (Session 08),
# under `LIMIT_INCUMBENT_STATUS`, which SD3 shares.
ACCEPTED_SELECTION_STATUSES = frozenset(
    {"OPTIMAL_ACTUAL_CANDIDATE_BANK", LIMIT_INCUMBENT_STATUS}
)
# The HiGHS model statuses a limit stops on, with the bank's termination label
# and the code a bank stopped by one reports when it cannot go on (Session 08).
_BANK_LIMITS = {
    "kTimeLimit": ("TIMEOUT", "CANDIDATE_BANK_TIMEOUT"),
    "kIterationLimit": ("SEARCH_LIMIT", "CANDIDATE_BANK_SEARCH_LIMIT"),
    "kSolutionLimit": ("SEARCH_LIMIT", "CANDIDATE_BANK_SEARCH_LIMIT"),
}
# A bank stopped at a limit that still holds the entry count and a
# POLICY_FEASIBLE witness is not blocking; its status names the limit.
LIMIT_STOP_BANK_STATUSES = {
    "CANDIDATE_BANK_TIMEOUT": "BOUNDED_TIME_LIMIT_STOP",
    "CANDIDATE_BANK_SEARCH_LIMIT": "BOUNDED_SEARCH_LIMIT_STOP",
}
ACCEPTED_BANK_STATUSES = frozenset(
    {"BOUNDED_COMPLETION", "EXHAUSTIVE_COMPLETION", *LIMIT_STOP_BANK_STATUSES.values()}
)


@dataclass(frozen=True)
class ClassicCandidate:
    roster: tuple[str, ...]
    canonical_key: str
    people: frozenset[str]
    teams: frozenset[str]
    games: frozenset[str]
    prior_points: float
    families: tuple[str, ...]
    group_matches: tuple[str, ...]
    stack_matches: tuple[str, ...]
    source_stratum: str
    source_solver_status: str
    source_model_status: str
    source_mip_gap: float | None
    source_node_count: int | None

    def canonical_mapping(self, index: int) -> dict[str, object]:
        return {
            "index": index,
            "roster": list(self.roster),
            "canonical_key": self.canonical_key,
            "people": sorted(self.people),
            "teams": sorted(self.teams),
            "games": sorted(self.games),
            "prior_points": Decimal(format(self.prior_points, ".9f")),
            "families": list(self.families),
            "group_matches": list(self.group_matches),
            "stack_matches": list(self.stack_matches),
            "source_stratum": self.source_stratum,
            "source_solver_status": self.source_solver_status,
            "source_model_status": self.source_model_status,
            "source_mip_gap": (
                None
                if self.source_mip_gap is None
                else Decimal(format(self.source_mip_gap, ".12f"))
            ),
            "source_node_count": self.source_node_count,
        }


@dataclass(frozen=True)
class ClassicCandidateStratum:
    kind: str
    subject: str | None
    requested: int
    solves: int
    qualifying: int
    added: int
    termination: str

    def as_mapping(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "subject": self.subject,
            "requested": self.requested,
            "solves": self.solves,
            "qualifying": self.qualifying,
            "added": self.added,
            "termination": self.termination,
        }


@dataclass(frozen=True)
class ClassicCandidateBank:
    candidates: tuple[ClassicCandidate, ...]
    status: str
    exhaustive: bool
    requested_candidates: int
    requested_entries: int
    elapsed_seconds: float
    peak_traced_python_bytes: int
    solve_count: int
    solver_node_count: int
    solver_max_gap: float | None
    terminal_model_status: str | None
    strata: tuple[ClassicCandidateStratum, ...]
    feasible_chain_indexes: tuple[int, ...]
    feasible_chain_status: str

    @property
    def blocking(self) -> bool:
        return self.status in {
            "CANDIDATE_BANK_TIMEOUT",
            "CANDIDATE_BANK_SEARCH_LIMIT",
            "CANDIDATE_BANK_SOLVER_ERROR",
            "STRUCTURAL_INFEASIBILITY",
        }

    def coverage(self) -> dict[str, object]:
        families: Counter[str] = Counter()
        groups: Counter[str] = Counter()
        stacks: Counter[str] = Counter()
        for candidate in self.candidates:
            families.update(candidate.families)
            groups.update(candidate.group_matches)
            stacks.update(candidate.stack_matches)
        return {
            "families": dict(sorted(families.items())),
            "groups": dict(sorted(groups.items())),
            "stack_rules": dict(sorted(stacks.items())),
        }

    def as_report(self) -> dict[str, object]:
        return {
            "enforcement_version": ENFORCEMENT_VERSION,
            "status": self.status,
            "completion_scope": (
                "EXHAUSTIVE_MODELED_LINEUP_SPACE"
                if self.exhaustive
                else "BOUNDED_ACTUAL_CANDIDATE_BANK"
            ),
            "requested_candidates": self.requested_candidates,
            "produced_candidates": len(self.candidates),
            "canonical_unique_candidates": len(
                {candidate.canonical_key for candidate in self.candidates}
            ),
            "requested_entries": self.requested_entries,
            "elapsed_seconds": round(self.elapsed_seconds, 6),
            "peak_traced_python_bytes": self.peak_traced_python_bytes,
            "solve_count": self.solve_count,
            "solver_node_count": self.solver_node_count,
            "solver_max_gap": self.solver_max_gap,
            "terminal_model_status": self.terminal_model_status,
            "limit_incumbent_candidates": sum(
                candidate.source_solver_status == "FEASIBLE_LIMIT"
                for candidate in self.candidates
            ),
            "coverage": self.coverage(),
            "policy_feasible_chain": {
                "status": self.feasible_chain_status,
                "candidate_indexes": list(self.feasible_chain_indexes),
                "length": len(self.feasible_chain_indexes),
                "ordering": "BEFORE_TOP_K_FILL",
            },
            "strata": [stratum.as_mapping() for stratum in self.strata],
            "optimality_claim": "NONE_FULL_SLATE",
        }


@dataclass(frozen=True)
class ClassicPortfolioSelection:
    status: str
    selected_candidate_indexes: tuple[int, ...]
    elapsed_seconds: float
    time_limit_seconds: float
    objective_prior_points: float | None
    mip_gap: float | None
    node_count: int | None
    model_status: str
    infeasibility_scope: str | None
    mip_start: str | None = None
    incumbent_source: str | None = None

    @property
    def passed(self) -> bool:
        return self.status in ACCEPTED_SELECTION_STATUSES

    @property
    def proven_optimal(self) -> bool:
        return self.status == "OPTIMAL_ACTUAL_CANDIDATE_BANK"

    def as_report(self) -> dict[str, object]:
        return {
            "status": self.status,
            "selected_candidate_indexes": list(self.selected_candidate_indexes),
            "selected_lineup_count": len(self.selected_candidate_indexes),
            "elapsed_seconds": round(self.elapsed_seconds, 6),
            "time_limit_seconds": self.time_limit_seconds,
            "objective_prior_points": self.objective_prior_points,
            "mip_gap": self.mip_gap,
            "node_count": self.node_count,
            "model_status": self.model_status,
            "optimality_scope": "ACTUAL_CANDIDATE_BANK" if self.proven_optimal else None,
            "infeasibility_scope": self.infeasibility_scope,
            "mip_start": self.mip_start,
            "incumbent_source": self.incumbent_source,
        }


@dataclass(frozen=True)
class ClassicPortfolioAudit:
    problems: tuple[str, ...]
    entry_ids: tuple[str, ...]
    canonical_lineups: tuple[tuple[str, str], ...]
    player_counts: tuple[tuple[str, int], ...]
    team_counts: tuple[tuple[str, int], ...]
    game_counts: tuple[tuple[str, int], ...]
    group_counts: tuple[tuple[str, int], ...]
    stack_counts: tuple[tuple[str, int], ...]
    pairwise_overlap: tuple[tuple[str, str, int], ...]
    hashes: tuple[tuple[str, str], ...]

    @property
    def passed(self) -> bool:
        return not self.problems

    def as_report(self) -> dict[str, object]:
        return {
            "audit_version": AUDIT_VERSION,
            "status": "PASS" if self.passed else "FAIL",
            "passed": self.passed,
            "problems": list(self.problems),
            "entry_ids": list(self.entry_ids),
            "canonical_lineups": dict(self.canonical_lineups),
            "player_counts": dict(self.player_counts),
            "team_counts": dict(self.team_counts),
            "game_counts": dict(self.game_counts),
            "group_counts": dict(self.group_counts),
            "stack_counts": dict(self.stack_counts),
            "pairwise_person_overlap": [
                {"entry_id_a": left, "entry_id_b": right, "people": overlap}
                for left, right, overlap in self.pairwise_overlap
            ],
            "hashes": dict(self.hashes),
            "checks_run": [
                "CANONICAL_NORMALIZED_POLICY_REPARSE",
                "EXACT_ENTRY_ID_SEQUENCE_AND_COVERAGE",
                "INDEPENDENT_DRAFTKINGS_LINEUP_LEGALITY",
                "COMPLETE_PERSON_TEAM_GAME_POSITION_AND_ROSTER_IDENTITY",
                "PLAYER_TEAM_GAME_GROUP_AND_STACK_INTEGER_BOUNDS",
                "EXACT_EXCLUSIONS",
                "CANONICAL_UNIQUENESS",
                "EVERY_PAIRWISE_PERSON_OVERLAP",
                "SALARY_ENTRY_PRIOR_PROJECTION_CURRENT_EVIDENCE_POLICY_BANK_ASSIGNMENT_HASHES",
            ],
        }


def _finite_positive(value: float, label: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{label} must be positive and finite")
    return number


def stack_value(slate: SlateContract, roster: Sequence[str], rule_type: str) -> int:
    by_id = {row.dk_id: row for row in slate.players}
    rows = [by_id[str(dk_id)] for dk_id in roster]
    qb = next(row for row in rows if row.position == "QB")
    if rule_type == "QB_PASS_CATCHER":
        return sum(row.team == qb.team and row.position in {"WR", "TE"} for row in rows)
    if rule_type == "QB_BRINGBACK":
        return sum(
            row.team == qb.opponent and row.position in {"RB", "WR", "TE"}
            for row in rows
        )
    if rule_type == "RB_DST_PAIR":
        dst_teams = {row.team for row in rows if row.position == "DST"}
        return sum(row.position == "RB" and row.team in dst_teams for row in rows)
    if rule_type == "SECONDARY_GAME_CORRELATION":
        count = 0
        for game in slate.games:
            if game.game_id == qb.game_id:
                continue
            selected_teams = {
                row.team
                for row in rows
                if row.game_id == game.game_id and row.position != "DST"
            }
            if {game.away_team, game.home_team}.issubset(selected_teams):
                count += 1
        return count
    raise ValueError(f"CLASSIC_STACK_RULE_UNREGISTERED:{rule_type}")


def _group_matches(
    candidate_people: frozenset[str], groups: Sequence[GroupRule]
) -> tuple[str, ...]:
    return tuple(
        rule.group_id
        for rule in groups
        if rule.minimum_players
        <= len(candidate_people.intersection(rule.member_ids))
        <= rule.maximum_players
    )


def _stack_matches(
    slate: SlateContract, roster: Sequence[str], rules: Sequence[StackRule]
) -> tuple[str, ...]:
    return tuple(
        rule.rule_id
        for rule in rules
        if rule.minimum_value
        <= stack_value(slate, roster, rule.rule_type)
        <= rule.maximum_value
    )


class _Enumerator:
    def __init__(
        self,
        slate: SlateContract,
        policy: NormalizedClassicPortfolioPolicy,
        objective: Mapping[str, float],
        *,
        excluded_ids: Sequence[str],
        forbidden_rosters: Sequence[tuple[str, ...]] = (),
    ) -> None:
        self.slate = slate
        self.policy = policy
        self.objective = objective
        self.excluded_ids = tuple(sorted(set(map(str, excluded_ids))))
        # The template's prefilled rosters (Session 11): cut from every solve and
        # held as already seen, so no candidate the joint solve sees repeats one.
        self.forbidden = tuple(tuple(map(str, roster)) for roster in forbidden_rosters)
        self.started = time.perf_counter()
        self.total_budget = policy.search_limits.candidate_total_milliseconds / 1000.0
        self.per_solve_budget = policy.search_limits.candidate_per_solve_milliseconds / 1000.0
        self.limit = policy.search_limits.candidate_limit
        self.by_id = {row.dk_id: row for row in slate.players}
        self.candidates: list[ClassicCandidate] = []
        self.seen: set[str] = {roster_canonical_key(slate, roster) for roster in self.forbidden}
        self.rosters: list[tuple[str, ...]] = []
        self.strata: list[ClassicCandidateStratum] = []
        self.solve_count = 0
        self.node_count = 0
        self.max_gap: float | None = None
        self.terminal_model_status: str | None = None
        self.blocking_status: str | None = None
        # The limit a solve stopped the bank on (Session 08). Unlike a solver
        # error it blocks only when the bank ends without the entry count and
        # a POLICY_FEASIBLE witness (`build_classic_candidate_bank`).
        self.limit_stop: str | None = None

    def elapsed(self) -> float:
        return time.perf_counter() - self.started

    @property
    def remaining(self) -> int:
        return self.limit - len(self.candidates)

    def expand_validated_neighbors(
        self, *, kind: str, target: int, subject: str | None = None
    ) -> ClassicCandidateStratum:
        """Expand MILP seeds with deterministic, independently legal swaps.

        The seeds came from the exact Classic MILP.  Every neighbor changes one
        exact roster ID, is reparsed by ``validate_lineup``, is scored only with
        the same prior objective, and is deduplicated canonically.  This avoids
        making 150-entry scale depend on hundreds of accumulating no-good rows.
        """

        requested = max(0, int(target))
        target = min(requested, self.remaining)
        if target <= 0 or not self.candidates:
            record = ClassicCandidateStratum(
                kind,
                subject,
                requested,
                0,
                0,
                0,
                "CANDIDATE_LIMIT" if self.remaining <= 0 else "NO_MILP_SEED",
            )
            self.strata.append(record)
            return record
        seeds = tuple(self.candidates)
        alternatives = tuple(
            sorted(
                (
                    row
                    for row in self.slate.players
                    if row.dk_id not in self.excluded_ids
                ),
                key=lambda row: (
                    -float(self.objective.get(row.dk_id, 0.0)),
                    row.position,
                    row.underlying_id,
                    row.dk_id,
                ),
            )
        )
        qualifying = 0
        added = 0
        for seed in seeds:
            for slot, current in enumerate(seed.roster):
                for replacement in alternatives:
                    if qualifying >= target or self.remaining <= 0:
                        break
                    if replacement.dk_id == current:
                        continue
                    roster_list = list(seed.roster)
                    roster_list[slot] = replacement.dk_id
                    roster = tuple(roster_list)
                    validation = validate_lineup(self.slate, roster)
                    if validation.lineup is None:
                        continue
                    canonical = validation.lineup.canonical_key
                    if canonical in self.seen:
                        continue
                    rows = [self.by_id[dk_id] for dk_id in roster]
                    people = frozenset(row.underlying_id for row in rows)
                    features = classify_candidate(self.slate, roster)
                    self.candidates.append(
                        ClassicCandidate(
                            roster=roster,
                            canonical_key=canonical,
                            people=people,
                            teams=frozenset(row.team for row in rows),
                            games=frozenset(row.game_id for row in rows),
                            prior_points=sum(
                                float(self.objective.get(dk_id, 0.0))
                                for dk_id in roster
                            ),
                            families=features.family_labels,
                            group_matches=_group_matches(people, self.policy.groups),
                            stack_matches=_stack_matches(
                                self.slate, roster, self.policy.stack_rules
                            ),
                            source_stratum=(
                                kind if subject is None else f"{kind}:{subject}"
                            ),
                            source_solver_status="INDEPENDENTLY_VALIDATED_NEIGHBOR",
                            source_model_status="SEE_MILP_SEED",
                            source_mip_gap=None,
                            source_node_count=None,
                        )
                    )
                    self.seen.add(canonical)
                    self.rosters.append(roster)
                    qualifying += 1
                    added += 1
                if qualifying >= target or self.remaining <= 0:
                    break
            if qualifying >= target or self.remaining <= 0:
                break
        termination = (
            "TARGET_REACHED"
            if qualifying >= target
            else "CANDIDATE_LIMIT"
            if self.remaining <= 0
            else "VALIDATED_NEIGHBORS_EXHAUSTED"
        )
        record = ClassicCandidateStratum(
            kind, subject, requested, 0, qualifying, added, termination
        )
        self.strata.append(record)
        return record

    def enumerate(
        self,
        *,
        kind: str,
        target: int,
        subject: str | None = None,
        required_ids: Sequence[str] = (),
        extra_excluded_ids: Sequence[str] = (),
        selected_count_bounds: tuple[Sequence[str], int, int] | None = None,
        qb_correlation_bounds: tuple[str, int, int] | None = None,
        predicate: Callable[[tuple[str, ...]], bool] | None = None,
        seed_no_goods: bool = False,
        enforce_pairwise_overlap: bool = False,
    ) -> ClassicCandidateStratum:
        requested = max(0, int(target))
        target = min(requested, self.remaining)
        if self.blocking_status is not None:
            record = ClassicCandidateStratum(kind, subject, requested, 0, 0, 0, "NOT_RUN_AFTER_BLOCKER")
            self.strata.append(record)
            return record
        if self.limit_stop is not None:
            record = ClassicCandidateStratum(kind, subject, requested, 0, 0, 0, "NOT_RUN_AFTER_LIMIT_STOP")
            self.strata.append(record)
            return record
        if target <= 0:
            record = ClassicCandidateStratum(kind, subject, requested, 0, 0, 0, "CANDIDATE_LIMIT")
            self.strata.append(record)
            return record
        optimizer = LineupOptimizer(
            self.slate,
            excluded_ids=tuple(sorted(set(self.excluded_ids) | set(map(str, extra_excluded_ids)))),
            time_limit_seconds=min(self.total_budget, self.per_solve_budget),
            mip_gap=0.0,
        )
        for dk_id in required_ids:
            optimizer.add_required_row(str(dk_id))
        if selected_count_bounds is not None:
            ids, minimum, maximum = selected_count_bounds
            optimizer.add_selected_count_bounds(ids, minimum=minimum, maximum=maximum)
        if qb_correlation_bounds is not None:
            corr_kind, minimum, maximum = qb_correlation_bounds
            optimizer.add_classic_qb_correlation_bounds(
                kind=corr_kind, minimum=minimum, maximum=maximum
            )
        if seed_no_goods:
            for roster in self.rosters:
                optimizer.add_no_good(roster)
        for roster in self.forbidden:
            optimizer.add_no_good(roster)

        solves = 0
        qualifying = 0
        added = 0
        termination = "TARGET_REACHED"
        # A predicate stratum may reject candidates; cap its extra search so a
        # rare advisory family cannot consume the whole registered bank.
        solve_cap = max(target, min(self.limit, target * 12))
        while qualifying < target and solves < solve_cap and self.remaining > 0:
            remaining = self.total_budget - self.elapsed()
            if remaining <= 0:
                termination = "TIMEOUT"
                self.limit_stop = "CANDIDATE_BANK_TIMEOUT"
                break
            optimizer.set_time_limit(min(self.per_solve_budget, remaining))
            cycle = self.solve_count
            perturbed = {
                row.dk_id: float(self.objective.get(row.dk_id, 0.0))
                + 1e-9 * (((cycle + 1) * (index + 17)) % 997)
                for index, row in enumerate(self.slate.players)
            }
            result = optimizer.solve(perturbed)
            solves += 1
            self.solve_count += 1
            self.terminal_model_status = result.model_status
            if result.node_count is not None:
                self.node_count += result.node_count
            if result.mip_gap is not None:
                self.max_gap = (
                    result.mip_gap
                    if self.max_gap is None
                    else max(self.max_gap, result.mip_gap)
                )
            if result.status == "INFEASIBLE":
                termination = "MODEL_INFEASIBLE"
                break
            limit = _BANK_LIMITS.get(result.model_status)
            # A solve stopped by a time or search limit that still returned a
            # roster keeps it (Session 08): `LineupOptimizer.solve` validated it
            # and `validate_lineup` below checks it again, so it counts toward
            # the stratum like any candidate, labelled `FEASIBLE_LIMIT` with
            # its model status, gap and nodes. Without a roster the bank stops.
            kept_at_limit = (
                result.status == "FEASIBLE_LIMIT"
                and limit is not None
                and result.roster is not None
            )
            if result.roster is not None and result.status not in {"OPTIMAL", "FEASIBLE_LIMIT"}:
                # The optimizer refused its own incumbent as illegal. That is a
                # solver error at any model status, as an illegal optimal roster
                # is below; a limit never makes it a stop the bank survives.
                termination = "ILLEGAL_SOLVER_ROSTER"
                self.blocking_status = "CANDIDATE_BANK_SOLVER_ERROR"
                break
            if not kept_at_limit and (result.status != "OPTIMAL" or result.roster is None):
                if limit is not None:
                    termination, self.limit_stop = limit
                else:
                    termination = "SOLVER_ERROR"
                    self.blocking_status = "CANDIDATE_BANK_SOLVER_ERROR"
                break
            roster = tuple(result.roster)
            optimizer.add_no_good(roster)
            validation = validate_lineup(self.slate, roster)
            if validation.lineup is None:
                termination = "ILLEGAL_SOLVER_ROSTER"
                self.blocking_status = "CANDIDATE_BANK_SOLVER_ERROR"
                break
            if predicate is not None and not predicate(roster):
                continue
            qualifying += 1
            canonical = validation.lineup.canonical_key
            if canonical in self.seen:
                continue
            rows = [self.by_id[dk_id] for dk_id in roster]
            people = frozenset(row.underlying_id for row in rows)
            features = classify_candidate(self.slate, roster)
            self.candidates.append(
                ClassicCandidate(
                    roster=roster,
                    canonical_key=canonical,
                    people=people,
                    teams=frozenset(row.team for row in rows),
                    games=frozenset(row.game_id for row in rows),
                    prior_points=sum(float(self.objective.get(dk_id, 0.0)) for dk_id in roster),
                    families=features.family_labels,
                    group_matches=_group_matches(people, self.policy.groups),
                    stack_matches=_stack_matches(self.slate, roster, self.policy.stack_rules),
                    source_stratum=kind if subject is None else f"{kind}:{subject}",
                    source_solver_status=result.status,
                    source_model_status=result.model_status,
                    source_mip_gap=result.mip_gap,
                    source_node_count=result.node_count,
                )
            )
            self.seen.add(canonical)
            self.rosters.append(roster)
            added += 1
            if enforce_pairwise_overlap and self.policy.max_pairwise_person_overlap < 9:
                optimizer.add_person_overlap_limit(
                    roster, self.policy.max_pairwise_person_overlap
                )
        if solves >= solve_cap and qualifying < target:
            termination = "STRATUM_SEARCH_BOUND"
        elif self.remaining <= 0 and qualifying < requested:
            termination = "CANDIDATE_LIMIT"
        record = ClassicCandidateStratum(
            kind, subject, requested, solves, qualifying, added, termination
        )
        self.strata.append(record)
        return record


def _add_row(
    model: highspy.Highs,
    lower: float,
    upper: float,
    coefficients: Mapping[int, float],
) -> None:
    indexes = np.asarray(list(coefficients), dtype=np.int32)
    values = np.asarray([coefficients[index] for index in indexes], dtype=np.float64)
    model.addRow(lower, upper, len(indexes), indexes, values)


def _qualifying_coefficients(
    candidates: Sequence[ClassicCandidate], attribute: str, value: str
) -> dict[int, float]:
    return {
        index: 1.0
        for index, candidate in enumerate(candidates)
        if value in getattr(candidate, attribute)
    }


def solve_classic_portfolio(
    policy: NormalizedClassicPortfolioPolicy,
    bank: ClassicCandidateBank,
    *,
    time_limit_seconds: float | None = None,
    solver_factory: Callable[[], highspy.Highs] = highspy.Highs,
) -> ClassicPortfolioSelection:
    budget = _finite_positive(
        time_limit_seconds
        if time_limit_seconds is not None
        else policy.search_limits.selection_milliseconds / 1000.0,
        "Classic portfolio selection budget",
    )
    started = time.perf_counter()
    candidates = bank.candidates
    if bank.blocking:
        return ClassicPortfolioSelection(bank.status, (), time.perf_counter() - started, budget, None, None, None, "NOT_RUN_BLOCKING_BANK", None)
    if len(candidates) < policy.entry_count:
        status = "MODELED_BANK_INFEASIBILITY" if bank.exhaustive else "INCOMPLETE_BANK_EXHAUSTION"
        return ClassicPortfolioSelection(status, (), time.perf_counter() - started, budget, None, None, None, "NOT_RUN_INSUFFICIENT_BANK", "EXHAUSTIVE_MODELED_BANK" if bank.exhaustive else "BOUNDED_BANK")

    model = solver_factory()
    model.setOptionValue("output_flag", False)
    model.setOptionValue("time_limit", budget)
    model.setOptionValue("mip_rel_gap", 0.0)
    model.setOptionValue("random_seed", policy.seed)
    count = len(candidates)
    model.addVars(count, np.zeros(count), np.ones(count))
    indexes = np.arange(count, dtype=np.int32)
    model.changeColsIntegrality(count, indexes, np.full(count, highspy.HighsVarType.kInteger))
    model.changeObjectiveSense(highspy.ObjSense.kMaximize)
    costs = np.asarray(
        [
            candidate.prior_points + 1e-9 * ((count - index) / (count + 1))
            for index, candidate in enumerate(candidates)
        ],
        dtype=np.float64,
    )
    model.changeColsCost(count, indexes, costs)
    _add_row(model, float(policy.entry_count), float(policy.entry_count), {index: 1.0 for index in range(count)})

    for bound in policy.player_bounds:
        coefficients = {
            index: 1.0
            for index, candidate in enumerate(candidates)
            if bound.entity_id in candidate.people
        }
        _add_row(model, float(bound.minimum_entries), float(bound.maximum_entries), coefficients)
    for bound in policy.team_bounds:
        coefficients = {
            index: 1.0
            for index, candidate in enumerate(candidates)
            if bound.entity_id in candidate.teams
        }
        _add_row(model, float(bound.minimum_entries), float(bound.maximum_entries), coefficients)
    for bound in policy.game_bounds:
        coefficients = {
            index: 1.0
            for index, candidate in enumerate(candidates)
            if bound.entity_id in candidate.games
        }
        _add_row(model, float(bound.minimum_entries), float(bound.maximum_entries), coefficients)
    for group in policy.groups:
        if group.hard:
            _add_row(model, float(group.minimum_entries), float(group.maximum_entries), _qualifying_coefficients(candidates, "group_matches", group.group_id))
    for rule in policy.stack_rules:
        if rule.hard:
            _add_row(model, float(rule.minimum_entries), float(rule.maximum_entries), _qualifying_coefficients(candidates, "stack_matches", rule.rule_id))
    if policy.max_pairwise_person_overlap < 9:
        for left in range(count):
            for right in range(left + 1, count):
                if len(candidates[left].people & candidates[right].people) > policy.max_pairwise_person_overlap:
                    _add_row(model, -highspy.kHighsInf, 1.0, {left: 1.0, right: 1.0})

    # The bank's POLICY_FEASIBLE witness is a feasible point of this model: it
    # was selected under the same policy from a prefix of these candidates, and
    # every bound counts selected lineups only. As a MIP start it is the
    # incumbent HiGHS returns if a limit stops it before anything better
    # (Session 08; highspy 1.11.0 returns it under both a node and a time limit).
    chain = tuple(bank.feasible_chain_indexes)
    mip_start = None
    if len(chain) == policy.entry_count and all(0 <= index < count for index in chain):
        start = np.asarray(chain, dtype=np.int32)
        model.setSolution(len(start), start, np.ones(len(start), dtype=np.float64))
        mip_start = "POLICY_FEASIBLE_WITNESS"

    model.run()
    elapsed = time.perf_counter() - started
    model_status = model.getModelStatus()
    model_status_name = model_status.name
    info = model.getInfo()
    solution = model.getSolution()
    gap = float(info.mip_gap) if np.isfinite(info.mip_gap) else None
    nodes = int(info.mip_node_count)
    limits = {
        highspy.HighsModelStatus.kTimeLimit,
        highspy.HighsModelStatus.kIterationLimit,
        highspy.HighsModelStatus.kSolutionLimit,
    }
    if model_status == highspy.HighsModelStatus.kInfeasible:
        status = "MODELED_BANK_INFEASIBILITY" if bank.exhaustive else "INCOMPLETE_BANK_EXHAUSTION"
        return ClassicPortfolioSelection(status, (), elapsed, budget, None, gap, nodes, model_status_name, "EXHAUSTIVE_MODELED_BANK" if bank.exhaustive else "BOUNDED_BANK", mip_start)
    if model_status in limits and solution.value_valid:
        status = LIMIT_INCUMBENT_STATUS
    elif model_status == highspy.HighsModelStatus.kTimeLimit:
        status = "PORTFOLIO_SELECTION_TIMEOUT"
    elif model_status in {highspy.HighsModelStatus.kIterationLimit, highspy.HighsModelStatus.kSolutionLimit}:
        status = "PORTFOLIO_SELECTION_SEARCH_LIMIT"
    elif model_status != highspy.HighsModelStatus.kOptimal or not solution.value_valid:
        status = "PORTFOLIO_SELECTION_SOLVER_ERROR"
    else:
        status = "OPTIMAL_ACTUAL_CANDIDATE_BANK"
    # A limit never delivers less than the witness. HiGHS returns the start
    # itself with its default presolve, but with presolve off a limit reached
    # early loses it (probed on highspy 1.11.0), and an incumbent HiGHS found
    # without it can score lower. The witness is still a feasible point of
    # this model, so the better of the two is the incumbent, labelled.
    witness = chain if mip_start is not None else ()
    source = "JOINT_SOLVE"
    if status not in ACCEPTED_SELECTION_STATUSES:
        if not (witness and model_status in limits):
            return ClassicPortfolioSelection(status, (), elapsed, budget, None, gap, nodes, model_status_name, None, mip_start)
        status, selected, source = LIMIT_INCUMBENT_STATUS, witness, "POLICY_FEASIBLE_WITNESS"
    else:
        # An incumbent and an optimum pass the same checks.
        raw = np.asarray(solution.col_value[:count])
        rounded = np.rint(raw).astype(int)
        if np.max(np.abs(raw - rounded)) > 1e-6 or int(rounded.sum()) != policy.entry_count or np.any((rounded < 0) | (rounded > 1)):
            return ClassicPortfolioSelection("PORTFOLIO_SELECTION_SOLVER_ERROR", (), elapsed, budget, None, gap, nodes, "INVALID_INTEGER_SOLUTION", None, mip_start)
        selected = tuple(np.flatnonzero(rounded).tolist())
        if status == LIMIT_INCUMBENT_STATUS and witness and (
            sum(candidates[index].prior_points for index in witness)
            > sum(candidates[index].prior_points for index in selected) + 1e-9
        ):
            selected, source = witness, "POLICY_FEASIBLE_WITNESS"
    selected = tuple(sorted(selected, key=lambda index: (-candidates[index].prior_points, candidates[index].canonical_key, candidates[index].roster, index)))
    return ClassicPortfolioSelection(
        status,
        selected,
        elapsed,
        budget,
        sum(candidates[index].prior_points for index in selected),
        gap,
        nodes,
        model_status_name,
        None,
        mip_start,
        source,
    )


def build_classic_candidate_bank(
    slate: SlateContract,
    objective: Mapping[str, float],
    policy: NormalizedClassicPortfolioPolicy,
    *,
    excluded_ids: Sequence[str] = (),
    forbidden_rosters: Sequence[tuple[str, ...]] = (),
) -> ClassicCandidateBank:
    if slate.mode is not EngineMode.CLASSIC:
        raise ValueError("CLASSIC_CANDIDATE_MODE_UNSUPPORTED")
    by_person = {row.underlying_id: row for row in slate.players}
    policy_excluded_ids = [by_person[person].dk_id for person in policy.exact_exclusions]
    tracing_before = tracemalloc.is_tracing()
    if not tracing_before:
        tracemalloc.start()
    enumerator = _Enumerator(
        slate,
        policy,
        objective,
        excluded_ids=tuple(excluded_ids) + tuple(policy_excluded_ids),
        forbidden_rosters=forbidden_rosters,
    )

    family_specs = (
        ("QB_SINGLE", ("PASS_CATCHER", 1, 1)),
        ("QB_DOUBLE", ("PASS_CATCHER", 2, 4)),
        ("NAKED_QB", ("PASS_CATCHER", 0, 0)),
        ("ZERO_BRINGBACK", ("BRINGBACK", 0, 0)),
        ("ONE_BRINGBACK", ("BRINGBACK", 1, 1)),
        ("TWO_PLUS_BRINGBACK", ("BRINGBACK", 2, 6)),
    )
    for family, bounds in family_specs:
        enumerator.enumerate(kind="family", subject=family, target=1, qb_correlation_bounds=bounds)

    for bound in policy.player_bounds:
        row = by_person[bound.entity_id]
        if bound.minimum_entries > 0:
            enumerator.enumerate(kind="player_inclusion", subject=bound.entity_id, target=min(bound.minimum_entries, 4), required_ids=(row.dk_id,))
        if 0 < bound.maximum_entries < policy.entry_count:
            enumerator.enumerate(kind="player_cap_exclusion", subject=bound.entity_id, target=min(policy.entry_count - bound.maximum_entries + 1, 4), extra_excluded_ids=(row.dk_id,))

    for group in policy.groups:
        ids = tuple(by_person[person].dk_id for person in group.member_ids)
        enumerator.enumerate(
            kind="group",
            subject=group.group_id,
            target=max(1, min(4, group.minimum_entries or 1)),
            selected_count_bounds=(ids, group.minimum_players, group.maximum_players),
            predicate=lambda roster, rule=group: rule.group_id in _group_matches(
                frozenset(enumerator.by_id[dk_id].underlying_id for dk_id in roster),
                (rule,),
            ),
        )

    for rule in policy.stack_rules:
        qb_bounds = None
        if rule.rule_type == "QB_PASS_CATCHER":
            qb_bounds = ("PASS_CATCHER", rule.minimum_value, rule.maximum_value)
        elif rule.rule_type == "QB_BRINGBACK":
            qb_bounds = ("BRINGBACK", rule.minimum_value, rule.maximum_value)
        enumerator.enumerate(
            kind="stack",
            subject=rule.rule_id,
            target=max(1, min(4, rule.minimum_entries or 1)),
            qb_correlation_bounds=qb_bounds,
            predicate=lambda roster, stack_rule=rule: stack_rule.rule_id
            in _stack_matches(slate, roster, (stack_rule,)),
        )

    # Reserve an explicitly named, jointly checked policy-feasible subset before
    # the remaining plain objective fill.  It is a candidate-bank witness, not
    # a claim of full-slate feasibility or quality.
    enumerator.expand_validated_neighbors(
        kind="policy_feasible_chain",
        target=policy.entry_count,
    )
    provisional = ClassicCandidateBank(
        candidates=tuple(enumerator.candidates),
        status="BOUNDED_COMPLETION",
        exhaustive=False,
        requested_candidates=policy.search_limits.candidate_limit,
        requested_entries=policy.entry_count,
        elapsed_seconds=enumerator.elapsed(),
        peak_traced_python_bytes=0,
        solve_count=enumerator.solve_count,
        solver_node_count=enumerator.node_count,
        solver_max_gap=enumerator.max_gap,
        terminal_model_status=enumerator.terminal_model_status,
        strata=tuple(enumerator.strata),
        feasible_chain_indexes=(),
        feasible_chain_status="PENDING",
    )
    witness = solve_classic_portfolio(
        policy,
        provisional,
        time_limit_seconds=policy.search_limits.selection_milliseconds / 1000.0,
    )
    chain_indexes = witness.selected_candidate_indexes if witness.passed else ()
    chain_status = "POLICY_FEASIBLE" if witness.passed else witness.status

    enumerator.enumerate(
        kind="top_k_fill",
        target=enumerator.remaining,
        seed_no_goods=True,
    )
    fill = enumerator.strata[-1]
    exhaustive = (
        fill.termination == "MODEL_INFEASIBLE"
        and enumerator.blocking_status is None
        and enumerator.limit_stop is None
    )
    if (
        exhaustive
        and not enumerator.candidates
        and fill.termination == "MODEL_INFEASIBLE"
    ):
        status = "STRUCTURAL_INFEASIBILITY"
    elif enumerator.blocking_status is not None:
        status = enumerator.blocking_status
    elif enumerator.limit_stop is not None:
        # Stopped at a limit (Session 08): the bank keeps what it built, and it
        # blocks only when that is too few for the entry count or holds no
        # POLICY_FEASIBLE witness for the joint solve to start from.
        enough = (
            len(enumerator.candidates) >= policy.entry_count
            and chain_status == "POLICY_FEASIBLE"
        )
        status = (
            LIMIT_STOP_BANK_STATUSES[enumerator.limit_stop]
            if enough
            else enumerator.limit_stop
        )
    elif exhaustive:
        status = "EXHAUSTIVE_COMPLETION"
    else:
        status = "BOUNDED_COMPLETION"
    _current, peak = tracemalloc.get_traced_memory()
    if not tracing_before:
        tracemalloc.stop()
    return ClassicCandidateBank(
        candidates=tuple(enumerator.candidates),
        status=status,
        exhaustive=exhaustive,
        requested_candidates=policy.search_limits.candidate_limit,
        requested_entries=policy.entry_count,
        elapsed_seconds=enumerator.elapsed(),
        peak_traced_python_bytes=peak,
        solve_count=enumerator.solve_count,
        solver_node_count=enumerator.node_count,
        solver_max_gap=enumerator.max_gap,
        terminal_model_status=enumerator.terminal_model_status,
        strata=tuple(enumerator.strata),
        feasible_chain_indexes=chain_indexes,
        feasible_chain_status=chain_status,
    )


def candidate_bank_bytes(
    policy: NormalizedClassicPortfolioPolicy,
    bank: ClassicCandidateBank,
) -> bytes:
    payload = {
        "schema_version": CANDIDATE_BANK_SCHEMA,
        "normalized_policy_sha256": policy.normalized_sha256,
        "status": bank.status,
        "exhaustive": bank.exhaustive,
        "requested_candidates": bank.requested_candidates,
        "produced_candidates": len(bank.candidates),
        "requested_entries": bank.requested_entries,
        "canonical_unique_candidates": len({candidate.canonical_key for candidate in bank.candidates}),
        "coverage": bank.coverage(),
        "policy_feasible_chain_indexes": list(bank.feasible_chain_indexes),
        "policy_feasible_chain_status": bank.feasible_chain_status,
        "strata": [stratum.as_mapping() for stratum in bank.strata],
        "candidates": [candidate.canonical_mapping(index) for index, candidate in enumerate(bank.candidates)],
        "search_scope": "BOUNDED_CLASSIC_LINEUP_MILP_NOT_FULL_SLATE_OPTIMALITY",
    }
    return canonical_decimal_json_bytes(payload)


def exact_classic_assignments(
    entry_ids: Sequence[str], rosters: Sequence[Sequence[str]]
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    entries = tuple(str(entry) for entry in entry_ids)
    if not entries or any(not entry for entry in entries) or len(set(entries)) != len(entries):
        raise ValueError("CLASSIC_ASSIGNMENT_ENTRY_IDS_INVALID")
    if len(entries) != len(rosters):
        raise ValueError(f"CLASSIC_ASSIGNMENT_COVERAGE_MISMATCH:entries={len(entries)}:lineups={len(rosters)}:cycling=disabled")
    return tuple((entry, tuple(map(str, roster))) for entry, roster in zip(entries, rosters, strict=True))


def assignment_artifact_bytes(
    policy: NormalizedClassicPortfolioPolicy,
    assignments: Sequence[tuple[str, Sequence[str]]],
    *,
    candidate_bank_sha256: str,
) -> bytes:
    return canonical_decimal_json_bytes(
        {
            "schema_version": ASSIGNMENT_SCHEMA,
            "normalized_policy_sha256": policy.normalized_sha256,
            "candidate_bank_sha256": candidate_bank_sha256,
            "entry_assignments": [
                {"entry_id": str(entry), "roster": [str(dk_id) for dk_id in roster]}
                for entry, roster in assignments
            ],
        }
    )


def _strict_json(raw: bytes, label: str) -> Mapping[str, object]:
    def pairs(values: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in values:
            if key in result:
                raise ValueError(f"{label} duplicate key {key!r}")
            result[key] = value
        return result

    payload = json.loads(raw.decode("utf-8"), parse_float=Decimal, parse_int=int, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"{label} nonfinite {value}")), object_pairs_hook=pairs)
    if not isinstance(payload, Mapping) or canonical_decimal_json_bytes(payload) != raw:
        raise ValueError(f"{label} bytes are not canonical")
    return payload


def audit_classic_portfolio(
    *,
    slate: SlateContract,
    normalized_policy_bytes: bytes,
    expected_normalized_policy_sha256: str,
    source_policy_bytes: bytes,
    expected_source_policy_sha256: str,
    salary_bytes: bytes,
    expected_salary_sha256: str,
    entry_bytes: bytes,
    expected_entry_sha256: str,
    bound_artifacts: Mapping[str, tuple[bytes, str]],
    candidate_bytes: bytes,
    expected_candidate_sha256: str,
    assignment_bytes: bytes,
    expected_assignment_sha256: str,
) -> ClassicPortfolioAudit:
    problems: list[str] = []
    actual_hashes = {
        "salary_sha256": sha256_bytes(salary_bytes),
        "entry_sha256": sha256_bytes(entry_bytes),
        "source_policy_sha256": sha256_bytes(source_policy_bytes),
        "normalized_policy_sha256": sha256_bytes(normalized_policy_bytes),
        "candidate_bank_sha256": sha256_bytes(candidate_bytes),
        "assignment_sha256": sha256_bytes(assignment_bytes),
    }
    expected_hashes = {
        "salary_sha256": expected_salary_sha256,
        "entry_sha256": expected_entry_sha256,
        "source_policy_sha256": expected_source_policy_sha256,
        "normalized_policy_sha256": expected_normalized_policy_sha256,
        "candidate_bank_sha256": expected_candidate_sha256,
        "assignment_sha256": expected_assignment_sha256,
    }
    for name, (raw, expected) in sorted(bound_artifacts.items()):
        actual_hashes[name] = sha256_bytes(raw)
        expected_hashes[name] = expected
    for name, expected in expected_hashes.items():
        if actual_hashes[name] != expected:
            problems.append(f"CLASSIC_AUDIT_{name.upper()}_MISMATCH:actual={actual_hashes[name]}:expected={expected}")
    try:
        policy = parse_normalized_classic_policy_bytes(normalized_policy_bytes)
    except Exception as exc:  # noqa: BLE001 - every parser failure becomes a blocker
        policy = None
        problems.append(f"CLASSIC_AUDIT_NORMALIZED_POLICY_INVALID:{type(exc).__name__}:{exc}")
    try:
        bank = _strict_json(candidate_bytes, "candidate bank")
        if bank.get("schema_version") != CANDIDATE_BANK_SCHEMA:
            raise ValueError("candidate bank schema unsupported")
        bank_candidates = bank.get("candidates")
        if not isinstance(bank_candidates, list):
            raise ValueError("candidate bank candidates must be an array")
        bank_rosters = {tuple(str(dk_id) for dk_id in item["roster"]) for item in bank_candidates}
        if bank.get("normalized_policy_sha256") != expected_normalized_policy_sha256:
            raise ValueError("candidate bank policy binding mismatch")
    except Exception as exc:  # noqa: BLE001
        bank_rosters = set()
        problems.append(f"CLASSIC_AUDIT_CANDIDATE_BANK_INVALID:{type(exc).__name__}:{exc}")
    try:
        assignment = _strict_json(assignment_bytes, "assignment")
        if assignment.get("schema_version") != ASSIGNMENT_SCHEMA:
            raise ValueError("assignment schema unsupported")
        if assignment.get("candidate_bank_sha256") != expected_candidate_sha256:
            raise ValueError("assignment candidate-bank binding mismatch")
        if assignment.get("normalized_policy_sha256") != expected_normalized_policy_sha256:
            raise ValueError("assignment normalized-policy binding mismatch")
        raw_pairs = assignment.get("entry_assignments")
        if not isinstance(raw_pairs, list):
            raise ValueError("entry_assignments must be an array")
        pairs = tuple((str(item["entry_id"]), tuple(str(dk_id) for dk_id in item["roster"])) for item in raw_pairs)
    except Exception as exc:  # noqa: BLE001
        pairs = ()
        problems.append(f"CLASSIC_AUDIT_ASSIGNMENT_INVALID:{type(exc).__name__}:{exc}")

    expected_entries = policy.entry_ids if policy is not None else ()
    actual_entries = tuple(entry for entry, _roster in pairs)
    if actual_entries != expected_entries:
        problems.append(f"CLASSIC_AUDIT_ENTRY_ID_ORDER_OR_COVERAGE_MISMATCH:actual={actual_entries}:expected={expected_entries}")
    by_id = {row.dk_id: row for row in slate.players}
    canonical: list[tuple[str, str]] = []
    people_by_entry: dict[str, frozenset[str]] = {}
    player_counts: Counter[str] = Counter()
    team_counts: Counter[str] = Counter()
    game_counts: Counter[str] = Counter()
    group_counts: Counter[str] = Counter()
    stack_counts: Counter[str] = Counter()
    for entry, roster in pairs:
        if roster not in bank_rosters:
            problems.append(f"CLASSIC_AUDIT_ASSIGNMENT_OUTSIDE_CANDIDATE_BANK:{entry}")
        validation = validate_lineup(slate, roster)
        if validation.lineup is None:
            problems.extend(f"CLASSIC_AUDIT_LINEUP_ILLEGAL:{entry}:{error}" for error in validation.errors)
            continue
        rows = [by_id[dk_id] for dk_id in roster]
        people = frozenset(row.underlying_id for row in rows)
        teams = frozenset(row.team for row in rows)
        games = frozenset(row.game_id for row in rows)
        canonical.append((entry, validation.lineup.canonical_key))
        people_by_entry[entry] = people
        player_counts.update(people)
        team_counts.update(teams)
        game_counts.update(games)
        if policy is not None:
            group_counts.update(_group_matches(people, policy.groups))
            stack_counts.update(_stack_matches(slate, roster, policy.stack_rules))
    if len({key for _entry, key in canonical}) != len(canonical):
        problems.append("CLASSIC_AUDIT_CANONICAL_LINEUP_DUPLICATE")
    overlap = tuple(
        (left, right, len(people_by_entry[left] & people_by_entry[right]))
        for left_index, left in enumerate(actual_entries)
        for right in actual_entries[left_index + 1 :]
        if left in people_by_entry and right in people_by_entry
    )
    if policy is not None:
        for bound in policy.player_bounds:
            actual = player_counts[bound.entity_id]
            if not bound.minimum_entries <= actual <= bound.maximum_entries:
                problems.append(f"CLASSIC_AUDIT_PLAYER_BOUND:{bound.entity_id}:{actual}:expected={bound.minimum_entries}..{bound.maximum_entries}")
        for bound in policy.team_bounds:
            actual = team_counts[bound.entity_id]
            if not bound.minimum_entries <= actual <= bound.maximum_entries:
                problems.append(f"CLASSIC_AUDIT_TEAM_BOUND:{bound.entity_id}:{actual}:expected={bound.minimum_entries}..{bound.maximum_entries}")
        for bound in policy.game_bounds:
            actual = game_counts[bound.entity_id]
            if not bound.minimum_entries <= actual <= bound.maximum_entries:
                problems.append(f"CLASSIC_AUDIT_GAME_BOUND:{bound.entity_id}:{actual}:expected={bound.minimum_entries}..{bound.maximum_entries}")
        for group in policy.groups:
            if group.hard and not group.minimum_entries <= group_counts[group.group_id] <= group.maximum_entries:
                problems.append(f"CLASSIC_AUDIT_GROUP_BOUND:{group.group_id}:{group_counts[group.group_id]}:expected={group.minimum_entries}..{group.maximum_entries}")
        for rule in policy.stack_rules:
            if rule.hard and not rule.minimum_entries <= stack_counts[rule.rule_id] <= rule.maximum_entries:
                problems.append(f"CLASSIC_AUDIT_STACK_BOUND:{rule.rule_id}:{stack_counts[rule.rule_id]}:expected={rule.minimum_entries}..{rule.maximum_entries}")
        excluded = set(policy.exact_exclusions)
        selected_excluded = sorted(excluded.intersection(player_counts))
        if selected_excluded:
            problems.append(f"CLASSIC_AUDIT_EXACT_EXCLUSION_BREACH:{selected_excluded}")
        for left, right, actual in overlap:
            if actual > policy.max_pairwise_person_overlap:
                problems.append(f"CLASSIC_AUDIT_PAIRWISE_OVERLAP:{left}:{right}:{actual}>{policy.max_pairwise_person_overlap}")
        salary_people = tuple(
            sorted(
                (
                    row.underlying_id,
                    row.dk_id,
                    row.name,
                    row.team,
                    row.opponent,
                    row.game_id,
                    row.position,
                    tuple(sorted(row.roster_positions)),
                    row.salary,
                )
                for row in slate.players
            )
        )
        policy_people = tuple(
            sorted(
                (
                    row.underlying_id,
                    row.dk_id,
                    row.name,
                    row.team,
                    row.opponent,
                    row.game_id,
                    row.position,
                    row.roster_positions,
                    row.salary,
                )
                for row in policy.people
            )
        )
        salary_games = tuple(
            sorted(
                (
                    game.game_id,
                    game.away_team,
                    game.home_team,
                    game.lock_at.isoformat(),
                )
                for game in slate.games
            )
        )
        salary_teams = tuple(
            sorted({(row.team, row.opponent, row.game_id) for row in slate.players})
        )
        if (
            salary_people != policy_people
            or salary_games != policy.games
            or salary_teams != policy.teams
            or policy.draft_group != slate.draft_group
            or policy.salary_sha256 != actual_hashes["salary_sha256"]
            or policy.entry_sha256 != actual_hashes["entry_sha256"]
        ):
            problems.append("CLASSIC_AUDIT_COMPLETE_IDENTITY_BINDING_MISMATCH")
    return ClassicPortfolioAudit(
        tuple(problems),
        actual_entries,
        tuple(canonical),
        tuple(sorted(player_counts.items())),
        tuple(sorted(team_counts.items())),
        tuple(sorted(game_counts.items())),
        tuple(sorted((rule.group_id, group_counts[rule.group_id]) for rule in (policy.groups if policy else ()))),
        tuple(sorted((rule.rule_id, stack_counts[rule.rule_id]) for rule in (policy.stack_rules if policy else ()))),
        overlap,
        tuple(sorted(actual_hashes.items())),
    )
