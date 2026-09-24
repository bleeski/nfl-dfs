"""Bounded SD4 Showdown portfolio enforcement and independent assignment audit.

This module deliberately optimizes only the prior-only central score already
produced by the selection path.  It does not import field, payout, ownership,
duplication, simulator, or portfolio-economics code.
"""

from __future__ import annotations

import csv
import io
import json
import math
import time
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, Mapping, Sequence

import highspy
import numpy as np

from .contracts import EngineMode, SlateContract
from .hashing import sha256_bytes
from .lineups import validate_lineup
from .optimizer import LIMIT_INCUMBENT_STATUS, LineupOptimizer
from .portfolio_policy import (
    EffectivePersonLimit,
    NormalizedPortfolioPolicy,
    canonical_decimal_json_bytes,
)


ENFORCEMENT_VERSION = "prior_only_showdown_portfolio_enforcement_sd4_v1"
AUDIT_VERSION = "prior_only_showdown_portfolio_audit_sd4_v1"
DEFAULT_CANDIDATE_LIMIT = 32
DEFAULT_CANDIDATE_SECONDS = 30.0
DEFAULT_CANDIDATE_PER_SOLVE_SECONDS = 2.0
DEFAULT_SELECTION_SECONDS = 10.0
# Policy-bearing requests scale the bounded bank with the requested entry
# count. These are still bounds on a bounded search, not a full-slate claim.
CANDIDATE_LIMIT_PER_ENTRY = 4
CANDIDATE_SECONDS_PER_ENTRY = 2.0
SELECTION_SECONDS_PER_ENTRY = 1.0
# A stratified bank seeds enough Captain slots to cover the entry count with
# this many spare slots, and the greedy feasible chain aims this far past it.
STRATUM_ENTRY_MARGIN = 2


def scaled_candidate_limit(entry_count: int) -> int:
    """Bank size for a policy of `entry_count` entries: `max(32, 4 * entries)`."""

    return max(DEFAULT_CANDIDATE_LIMIT, CANDIDATE_LIMIT_PER_ENTRY * int(entry_count))


def scaled_candidate_seconds(entry_count: int) -> float:
    """Total bank generation budget for a policy: `max(30s, 2s * entries)`."""

    return max(DEFAULT_CANDIDATE_SECONDS, CANDIDATE_SECONDS_PER_ENTRY * int(entry_count))


def scaled_selection_seconds(entry_count: int) -> float:
    """Joint MILP budget for a policy: `max(10s, 1s * entries)`."""

    return max(DEFAULT_SELECTION_SECONDS, SELECTION_SECONDS_PER_ENTRY * int(entry_count))


@dataclass(frozen=True)
class PolicyCandidate:
    roster: tuple[str, ...]
    canonical_key: str
    people: frozenset[str]
    captain_person: str
    prior_points: float
    source_solver_status: str
    source_solver_seconds: float


@dataclass(frozen=True)
class CandidateStratum:
    """One bounded sub-enumeration of the candidate bank.

    `kind` is `captain` (a fixed Captain row), `exclusion` (one capped person
    removed), `chain` (a greedy portfolio-feasible sequence under the policy's
    own caps and overlap) or `fill` (the plain top-K enumeration). `target`
    is how many lineups the stratum was asked for, `enumerated` how many the
    sub-problem produced and `added` how many were new canonical candidates.
    `terminal` names why the stratum stopped; `MODEL_INFEASIBLE` there means
    the sub-problem ran out of legal lineups and is a record, not an error.
    """

    kind: str
    person: str | None
    target: int
    enumerated: int
    added: int
    solve_count: int
    terminal: str

    def as_report(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "person": self.person,
            "target": self.target,
            "enumerated": self.enumerated,
            "added": self.added,
            "solve_count": self.solve_count,
            "terminal": self.terminal,
        }


@dataclass(frozen=True)
class CandidateBank:
    candidates: tuple[PolicyCandidate, ...]
    status: str
    complete: bool
    candidate_limit: int
    total_time_limit_seconds: float
    per_solve_time_limit_seconds: float
    elapsed_seconds: float
    solve_count: int
    terminal_model_status: str | None
    policy_aware: bool = False
    strata: tuple[CandidateStratum, ...] = ()

    @property
    def limit_incumbent_candidates(self) -> int:
        return sum(
            candidate.source_solver_status == "FEASIBLE_LIMIT"
            for candidate in self.candidates
        )

    @property
    def canonical_count(self) -> int:
        return len({candidate.canonical_key for candidate in self.candidates})

    @property
    def blocking(self) -> bool:
        return self.status in {
            "CANDIDATE_BANK_TIME_LIMIT",
            "CANDIDATE_BANK_SEARCH_LIMIT",
            "CANDIDATE_BANK_SOLVER_ERROR",
        }

    def strata_summary(self) -> dict[str, object]:
        """Per-stratum counts of new canonical candidates, keyed by person."""

        captain: dict[str, int] = {}
        exclusion: dict[str, int] = {}
        chain = 0
        fill = 0
        for stratum in self.strata:
            if stratum.kind == "captain" and stratum.person is not None:
                captain[stratum.person] = captain.get(stratum.person, 0) + stratum.added
            elif stratum.kind == "exclusion" and stratum.person is not None:
                exclusion[stratum.person] = exclusion.get(stratum.person, 0) + stratum.added
            elif stratum.kind == "chain":
                chain += stratum.added
            elif stratum.kind == "fill":
                fill += stratum.added
        return {
            "captain": dict(sorted(captain.items())),
            "exclusion": dict(sorted(exclusion.items())),
            "chain": chain,
            "fill": fill,
        }

    def as_report(self) -> dict[str, object]:
        return {
            "status": self.status,
            "complete": self.complete,
            "coverage": (
                "COMPLETE_MODELED_BANK"
                if self.complete
                else "BOUNDED_INCOMPLETE_ACTUAL_CANDIDATE_BANK"
            ),
            "candidate_count": len(self.candidates),
            "canonical_count": self.canonical_count,
            "candidate_limit": self.candidate_limit,
            "total_time_limit_seconds": self.total_time_limit_seconds,
            "per_solve_time_limit_seconds": self.per_solve_time_limit_seconds,
            "elapsed_seconds": round(self.elapsed_seconds, 6),
            "solve_count": self.solve_count,
            "terminal_model_status": self.terminal_model_status,
            "limit_incumbent_candidates": self.limit_incumbent_candidates,
            "policy_aware": self.policy_aware,
            "strata": self.strata_summary(),
            "strata_detail": [stratum.as_report() for stratum in self.strata],
            "search_scope": "BOUNDED_STRATIFIED_ENUMERATION_NOT_A_FULL_SLATE_SEARCH",
        }


@dataclass(frozen=True)
class PolicySelection:
    status: str
    selected_candidate_indexes: tuple[int, ...]
    elapsed_seconds: float
    time_limit_seconds: float
    objective_prior_points: float | None
    mip_gap: float | None
    node_count: int | None
    model_status: str
    infeasibility_scope: str | None

    @property
    def passed(self) -> bool:
        # A time- or search-limited incumbent passes like the optimum (Session 08).
        return self.status in {"OPTIMAL", LIMIT_INCUMBENT_STATUS}

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
            "optimality_scope": (
                "ACTUAL_CANDIDATE_BANK" if self.status == "OPTIMAL" else None
            ),
            "infeasibility_scope": self.infeasibility_scope,
        }


@dataclass(frozen=True)
class PortfolioAudit:
    problems: tuple[str, ...]
    entry_ids: tuple[str, ...]
    canonical_lineups: tuple[tuple[str, str], ...]
    combined_person_counts: tuple[tuple[str, int], ...]
    captain_counts: tuple[tuple[str, int], ...]
    pairwise_person_overlap: tuple[tuple[str, str, int], ...]
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
            "combined_person_counts": dict(self.combined_person_counts),
            "captain_counts": dict(self.captain_counts),
            "pairwise_person_overlap": [
                {"entry_id_a": left, "entry_id_b": right, "people": overlap}
                for left, right, overlap in self.pairwise_person_overlap
            ],
            "hashes": dict(self.hashes),
            "checks_run": [
                "EXACT_ENTRY_ID_SEQUENCE_AND_COVERAGE",
                "ASSIGNMENT_ARTIFACT_SEQUENCE_AND_ROSTERS",
                "NORMALIZED_POLICY_ARTIFACT_REPARSE",
                "INDEPENDENT_DRAFTKINGS_LINEUP_LEGALITY",
                "CANONICAL_CAPTAIN_AND_ORDER_FREE_FLEX_IDENTITY",
                "COMBINED_PERSON_MAXIMA",
                "CAPTAIN_MAXIMA",
                "CANONICAL_UNIQUENESS",
                "EVERY_PAIRWISE_UNDERLYING_PERSON_OVERLAP",
                "SALARY_ENTRY_SOURCE_POLICY_NORMALIZED_POLICY_ASSIGNMENT_HASHES",
                "SELECTOR_SUMMARY_RECONCILIATION",
            ],
        }


def _finite_positive(value: float, label: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{label} must be positive and finite")
    return number


class _StratifiedEnumerator:
    """Deterministic bounded enumeration shared by every candidate stratum.

    Every stratum builds its own `LineupOptimizer` over the same exclusions,
    optionally pins rows (`captain`), removes rows (`exclusion`) or applies
    the policy's own caps and overlap as it goes (`chain`), then enumerates
    with exact-roster no-good cuts and the vanishing deterministic
    perturbation. Candidates are deduplicated by canonical key across strata.
    The total wall-clock budget, the per-solve budget and the candidate limit
    are shared, so the bank stays bounded no matter how many strata run.
    """

    def __init__(
        self,
        slate: SlateContract,
        objective: Mapping[str, float],
        *,
        excluded_ids: Sequence[str],
        candidate_limit: int,
        total_budget: float,
        per_solve_budget: float,
    ) -> None:
        self.slate = slate
        self.objective = objective
        self.excluded_ids = tuple(sorted({str(dk_id) for dk_id in excluded_ids}))
        self.candidate_limit = candidate_limit
        self.total_budget = total_budget
        self.per_solve_budget = per_solve_budget
        self.started = time.perf_counter()
        self.by_id = {row.dk_id: row for row in slate.players}
        self.candidates: list[PolicyCandidate] = []
        self.canonical_seen: set[str] = set()
        self.rosters: list[tuple[str, ...]] = []
        self.solve_count = 0
        self.terminal: str | None = None
        self.blocking_status: str | None = None
        self.strata: list[CandidateStratum] = []

    @property
    def remaining_capacity(self) -> int:
        return self.candidate_limit - len(self.candidates)

    def elapsed(self) -> float:
        return time.perf_counter() - self.started

    def record(self, stratum: CandidateStratum) -> CandidateStratum:
        self.strata.append(stratum)
        return stratum

    def enumerate(
        self,
        *,
        kind: str,
        target: int,
        person: str | None = None,
        required_ids: Sequence[str] = (),
        extra_excluded_ids: Sequence[str] = (),
        seed_no_goods: bool = False,
        chain_policy: NormalizedPortfolioPolicy | None = None,
        reserve: int = 0,
    ) -> CandidateStratum:
        """Run one stratum; `reserve` keeps that many bank slots for later strata."""

        reserve = max(0, int(reserve))
        capacity = self.remaining_capacity - reserve
        requested = max(0, int(target))
        target = max(0, min(requested, capacity))
        limit_terminal = "CAPACITY_RESERVED" if reserve and requested > capacity else "CANDIDATE_LIMIT"
        if self.blocking_status is not None:
            return self.record(CandidateStratum(kind, person, requested, 0, 0, 0, "NOT_RUN_AFTER_BLOCKER"))
        if target <= 0:
            return self.record(CandidateStratum(kind, person, requested, 0, 0, 0, limit_terminal))
        optimizer = LineupOptimizer(
            self.slate,
            excluded_ids=tuple(sorted(set(self.excluded_ids) | {str(x) for x in extra_excluded_ids})),
            time_limit_seconds=min(self.total_budget, self.per_solve_budget),
        )
        for dk_id in required_ids:
            optimizer.add_required_row(dk_id)
        if seed_no_goods:
            for roster in self.rosters:
                optimizer.add_no_good(roster)
        chain_limits: dict[str, EffectivePersonLimit] = {}
        chain_overlap = 6
        chain_people: Counter[str] = Counter()
        chain_captains: Counter[str] = Counter()
        chain_forbidden: set[str] = set()
        if chain_policy is not None:
            chain_limits = {
                item.person.underlying_id: item for item in chain_policy.effective_limits
            }
            chain_overlap = chain_policy.effective_pairwise_person_overlap

        enumerated = 0
        added = 0
        solves = 0
        terminal = "TARGET_REACHED"
        while enumerated < target and self.remaining_capacity > reserve:
            remaining = self.total_budget - self.elapsed()
            if remaining <= 0:
                terminal = "TIME_LIMIT"
                self.blocking_status = "CANDIDATE_BANK_TIME_LIMIT"
                self.terminal = "TOTAL_TIME_LIMIT"
                break
            optimizer.set_time_limit(min(self.per_solve_budget, remaining))
            cycle = self.solve_count
            perturbed = {
                row.dk_id: float(self.objective.get(row.dk_id, 0.0))
                + 1e-9 * (((cycle + 1) * (index + 17)) % 997)
                for index, row in enumerate(self.slate.players)
            }
            result = optimizer.solve(perturbed)
            self.solve_count += 1
            solves += 1
            self.terminal = result.model_status
            if result.status == "INFEASIBLE":
                terminal = "MODEL_INFEASIBLE"
                break
            # A solve stopped by a time or search limit that still returned a
            # roster keeps it, labelled `FEASIBLE_LIMIT` (Session 08), as the
            # Classic bank does. A bank stopped with no roster still blocks: it
            # has no jointly solved witness to show it can fill the entries.
            kept_at_limit = (
                result.status == "FEASIBLE_LIMIT"
                and result.roster is not None
                and result.model_status in {"kTimeLimit", "kIterationLimit", "kSolutionLimit"}
            )
            if not kept_at_limit and (result.status != "OPTIMAL" or result.roster is None):
                if result.model_status == "kTimeLimit":
                    self.blocking_status = "CANDIDATE_BANK_TIME_LIMIT"
                    terminal = "TIME_LIMIT"
                elif result.model_status in {"kIterationLimit", "kSolutionLimit"}:
                    self.blocking_status = "CANDIDATE_BANK_SEARCH_LIMIT"
                    terminal = "SEARCH_LIMIT"
                else:
                    self.blocking_status = "CANDIDATE_BANK_SOLVER_ERROR"
                    terminal = "SOLVER_ERROR"
                break
            validation = validate_lineup(self.slate, result.roster)
            if validation.lineup is None:
                self.blocking_status = "CANDIDATE_BANK_SOLVER_ERROR"
                self.terminal = "ILLEGAL_SOLVER_ROSTER"
                terminal = "ILLEGAL_SOLVER_ROSTER"
                break
            roster = tuple(result.roster)
            people = frozenset(self.by_id[dk_id].underlying_id for dk_id in roster)
            captain = self.by_id[roster[0]].underlying_id
            canonical = validation.lineup.canonical_key
            enumerated += 1
            if canonical not in self.canonical_seen:
                self.candidates.append(
                    PolicyCandidate(
                        roster=roster,
                        canonical_key=canonical,
                        people=people,
                        captain_person=captain,
                        prior_points=sum(
                            float(self.objective.get(dk_id, 0.0)) for dk_id in roster
                        ),
                        source_solver_status=result.status,
                        source_solver_seconds=result.elapsed_seconds,
                    )
                )
                self.canonical_seen.add(canonical)
                self.rosters.append(roster)
                added += 1
            optimizer.add_no_good(roster)
            if chain_policy is not None:
                # Keep the chain itself a legal portfolio under the policy: once
                # a person or Captain reaches its integer maximum inside the
                # chain, its rows leave the model; every later chain lineup
                # also respects the configured pairwise overlap against this one.
                if chain_overlap < 6:
                    optimizer.add_person_overlap_limit(roster, chain_overlap)
                for member in people:
                    chain_people[member] += 1
                    limit = chain_limits.get(member)
                    if limit is None or chain_people[member] < limit.combined_max_entries:
                        continue
                    for dk_id in (limit.person.cpt_dk_id, limit.person.flex_dk_id):
                        if dk_id not in chain_forbidden:
                            chain_forbidden.add(dk_id)
                            optimizer.add_no_good([dk_id])
                chain_captains[captain] += 1
                limit = chain_limits.get(captain)
                if (
                    limit is not None
                    and chain_captains[captain] >= limit.captain_max_entries
                    and limit.person.cpt_dk_id not in chain_forbidden
                ):
                    chain_forbidden.add(limit.person.cpt_dk_id)
                    optimizer.add_no_good([limit.person.cpt_dk_id])
        else:
            if enumerated < requested:
                terminal = limit_terminal
        return self.record(
            CandidateStratum(kind, person, requested, enumerated, added, solves, terminal)
        )

    def bank(self, *, policy_aware: bool) -> CandidateBank:
        if self.blocking_status is not None:
            status = self.blocking_status
            complete = False
        else:
            fills = [stratum for stratum in self.strata if stratum.kind == "fill"]
            complete = bool(fills) and fills[-1].terminal == "MODEL_INFEASIBLE"
            status = (
                "COMPLETE_MODELED_BANK" if complete else "CANDIDATE_LIMIT_REACHED_INCOMPLETE"
            )
        return CandidateBank(
            candidates=tuple(self.candidates),
            status=status,
            complete=complete,
            candidate_limit=self.candidate_limit,
            total_time_limit_seconds=self.total_budget,
            per_solve_time_limit_seconds=self.per_solve_budget,
            elapsed_seconds=self.elapsed(),
            solve_count=self.solve_count,
            terminal_model_status=self.terminal,
            policy_aware=policy_aware,
            strata=tuple(self.strata),
        )


@dataclass(frozen=True)
class SeededCaptain:
    person: str
    cpt_dk_id: str
    captain_max_entries: int
    objective: float


def plan_captain_strata(
    policy: NormalizedPortfolioPolicy,
    objective: Mapping[str, float],
    *,
    excluded_ids: Sequence[str] = (),
) -> tuple[tuple[SeededCaptain, ...], int]:
    """Choose the seeded Captains and the per-Captain depth `k`.

    Eligible people are ordered by descending CPT-row objective, then person
    ID. Excluded people, people whose effective Captain maximum is zero and
    zero-objective rows are skipped. Captains are seeded until their summed
    effective Captain maxima cover the entry count plus `STRATUM_ENTRY_MARGIN`
    slots, and `k = ceil(entries / seeded) + 1` so the joint MILP can spread
    the entries across them without running out of choices.
    """

    excluded = {str(dk_id) for dk_id in excluded_ids}
    eligible: list[SeededCaptain] = []
    for limit in policy.effective_limits:
        if limit.excluded or limit.combined_max_entries < 1 or limit.captain_max_entries < 1:
            continue
        cpt = limit.person.cpt_dk_id
        if cpt in excluded or limit.person.flex_dk_id in excluded:
            continue
        value = float(objective.get(cpt, 0.0))
        if not math.isfinite(value) or value <= 0.0:
            continue
        eligible.append(
            SeededCaptain(limit.person.underlying_id, cpt, limit.captain_max_entries, value)
        )
    eligible.sort(key=lambda item: (-item.objective, item.person))
    seeded: list[SeededCaptain] = []
    covered = 0
    needed = policy.entry_count + STRATUM_ENTRY_MARGIN
    for item in eligible:
        seeded.append(item)
        covered += item.captain_max_entries
        if covered >= needed:
            break
    depth = math.ceil(policy.entry_count / len(seeded)) + 1 if seeded else 0
    return tuple(seeded), depth


def build_policy_candidate_bank(
    slate: SlateContract,
    objective: Mapping[str, float],
    *,
    excluded_ids: Sequence[str] = (),
    candidate_limit: int = DEFAULT_CANDIDATE_LIMIT,
    total_time_limit_seconds: float = DEFAULT_CANDIDATE_SECONDS,
    per_solve_time_limit_seconds: float = DEFAULT_CANDIDATE_PER_SOLVE_SECONDS,
    policy: NormalizedPortfolioPolicy | None = None,
) -> CandidateBank:
    """Enumerate a deterministic bounded bank of legal policy candidates.

    Without a policy this is the plain top-K enumeration by prior points. With
    a policy the same machinery runs in strata so the joint MILP has something
    to choose from under the policy's caps: the best lineups for each seeded
    Captain, the best lineups without each combined-capped person, a greedy
    chain that already satisfies every cap and the overlap limit, and finally
    the plain top-K fill for whatever candidate budget remains. All strata
    share one candidate limit and one wall-clock budget; the result is still a
    bounded bank, and `complete` is claimed only when the fill enumeration
    proves the modeled lineup space exhausted.
    """

    if slate.mode is not EngineMode.SHOWDOWN:
        raise ValueError("PORTFOLIO_CANDIDATE_MODE_UNSUPPORTED:SHOWDOWN_REQUIRED")
    if isinstance(candidate_limit, bool) or int(candidate_limit) < 1:
        raise ValueError("candidate_limit must be a positive integer")
    candidate_limit = int(candidate_limit)
    total_budget = _finite_positive(total_time_limit_seconds, "total candidate budget")
    per_solve_budget = _finite_positive(
        per_solve_time_limit_seconds, "per-solve candidate budget"
    )
    enumerator = _StratifiedEnumerator(
        slate,
        objective,
        excluded_ids=excluded_ids,
        candidate_limit=candidate_limit,
        total_budget=total_budget,
        per_solve_budget=per_solve_budget,
    )
    if policy is None:
        enumerator.enumerate(kind="fill", target=candidate_limit)
        return enumerator.bank(policy_aware=False)

    entry_count = policy.entry_count
    # The chain is the stratum that hands the joint MILP a portfolio already
    # legal under every cap and the overlap limit, so its slots are reserved
    # while the Captain and exclusion strata run. Every stratum uses its own
    # optimizer, so the reservation changes nothing about which lineups a
    # stratum finds; it only decides who is truncated when the limit binds.
    constrained = policy.effective_pairwise_person_overlap < 6 or any(
        not limit.excluded
        and (
            0 < limit.combined_max_entries < entry_count
            or 0 < limit.captain_max_entries < entry_count
        )
        for limit in policy.effective_limits
    )
    chain_target = entry_count + STRATUM_ENTRY_MARGIN if constrained else 0
    reserve = min(chain_target, candidate_limit)

    seeded, depth = plan_captain_strata(policy, objective, excluded_ids=enumerator.excluded_ids)
    for captain in seeded:
        enumerator.enumerate(
            kind="captain",
            person=captain.person,
            target=depth,
            required_ids=(captain.cpt_dk_id,),
            reserve=reserve,
        )

    capped = sorted(
        (
            limit
            for limit in policy.effective_limits
            if not limit.excluded and 0 < limit.combined_max_entries < entry_count
        ),
        key=lambda limit: (
            -float(objective.get(limit.person.flex_dk_id, 0.0)),
            limit.person.underlying_id,
        ),
    )
    for limit in capped:
        person = limit.person.underlying_id
        depth_without = entry_count - limit.combined_max_entries + 1
        already_without = sum(
            1 for candidate in enumerator.candidates if person not in candidate.people
        )
        if already_without >= depth_without:
            enumerator.record(
                CandidateStratum("exclusion", person, depth_without, 0, 0, 0, "ALREADY_COVERED")
            )
            continue
        enumerator.enumerate(
            kind="exclusion",
            person=person,
            target=depth_without,
            extra_excluded_ids=(limit.person.cpt_dk_id, limit.person.flex_dk_id),
            reserve=reserve,
        )

    if constrained:
        enumerator.enumerate(kind="chain", target=chain_target, chain_policy=policy)
    else:
        enumerator.record(CandidateStratum("chain", None, 0, 0, 0, 0, "NOT_REQUIRED_UNCONSTRAINED"))

    enumerator.enumerate(
        kind="fill", target=enumerator.remaining_capacity, seed_no_goods=True
    )
    return enumerator.bank(policy_aware=True)


def _add_row(
    model: highspy.Highs,
    lower: float,
    upper: float,
    coefficients: Mapping[int, float],
) -> None:
    indexes = np.asarray(list(coefficients), dtype=np.int32)
    values = np.asarray([coefficients[index] for index in indexes], dtype=np.float64)
    model.addRow(lower, upper, len(indexes), indexes, values)


def solve_policy_portfolio(
    policy: NormalizedPortfolioPolicy,
    bank: CandidateBank,
    *,
    time_limit_seconds: float = DEFAULT_SELECTION_SECONDS,
    solver_factory: Callable[[], highspy.Highs] = highspy.Highs,
) -> PolicySelection:
    """Select one exact portfolio jointly over the actual candidate bank."""

    budget = _finite_positive(time_limit_seconds, "portfolio selection budget")
    started = time.perf_counter()
    candidates = bank.candidates
    if not candidates:
        return PolicySelection(
            status=(
                "MODELED_BANK_INFEASIBLE_PROVEN"
                if bank.complete
                else "CANDIDATE_BANK_EXHAUSTED_INCOMPLETE"
            ),
            selected_candidate_indexes=(),
            elapsed_seconds=time.perf_counter() - started,
            time_limit_seconds=budget,
            objective_prior_points=None,
            mip_gap=None,
            node_count=None,
            model_status="NOT_RUN_EMPTY_BANK",
            infeasibility_scope=("COMPLETE_MODELED_BANK" if bank.complete else None),
        )

    count = policy.entry_count
    candidate_count = len(candidates)
    count_offset = 0
    used_offset = candidate_count
    variable_count = candidate_count * 2
    lower = np.zeros(variable_count, dtype=np.float64)
    upper = np.ones(variable_count, dtype=np.float64)
    repetition_allowed = (
        not policy.require_unique_lineups
        and policy.effective_pairwise_person_overlap >= 6
    )
    upper[count_offset:used_offset] = float(count if repetition_allowed else 1)

    model = solver_factory()
    model.setOptionValue("output_flag", False)
    model.setOptionValue("time_limit", budget)
    model.setOptionValue("mip_rel_gap", 0.0)
    model.setOptionValue("random_seed", 0)
    model.addVars(variable_count, lower, upper)
    indexes = np.arange(variable_count, dtype=np.int32)
    model.changeColsIntegrality(
        variable_count,
        indexes,
        np.full(variable_count, highspy.HighsVarType.kInteger),
    )
    model.changeObjectiveSense(highspy.ObjSense.kMaximize)
    costs = np.zeros(variable_count, dtype=np.float64)
    for index, candidate in enumerate(candidates):
        costs[index] = candidate.prior_points + 1e-9 * (
            (candidate_count - index) / (candidate_count + 1)
        )
    model.changeColsCost(variable_count, indexes, costs)

    _add_row(model, float(count), float(count), {index: 1.0 for index in range(candidate_count)})
    for index in range(candidate_count):
        count_index = count_offset + index
        used_index = used_offset + index
        _add_row(model, -highspy.kHighsInf, 0.0, {count_index: 1.0, used_index: -float(count)})
        _add_row(model, -highspy.kHighsInf, 0.0, {count_index: -1.0, used_index: 1.0})

    limits = {item.person.underlying_id: item for item in policy.effective_limits}
    for person, limit in limits.items():
        coefficients = {
            index: 1.0
            for index, candidate in enumerate(candidates)
            if person in candidate.people
        }
        if coefficients:
            _add_row(
                model,
                -highspy.kHighsInf,
                float(limit.combined_max_entries),
                coefficients,
            )
        captain_coefficients = {
            index: 1.0
            for index, candidate in enumerate(candidates)
            if candidate.captain_person == person
        }
        if captain_coefficients:
            _add_row(
                model,
                -highspy.kHighsInf,
                float(limit.captain_max_entries),
                captain_coefficients,
            )

    if policy.require_unique_lineups:
        by_canonical: dict[str, list[int]] = {}
        for index, candidate in enumerate(candidates):
            by_canonical.setdefault(candidate.canonical_key, []).append(index)
        for group in by_canonical.values():
            _add_row(
                model,
                -highspy.kHighsInf,
                1.0,
                {index: 1.0 for index in group},
            )

    overlap_cap = policy.effective_pairwise_person_overlap
    if overlap_cap < 6:
        for left in range(candidate_count):
            for right in range(left + 1, candidate_count):
                if len(candidates[left].people & candidates[right].people) > overlap_cap:
                    _add_row(
                        model,
                        -highspy.kHighsInf,
                        1.0,
                        {used_offset + left: 1.0, used_offset + right: 1.0},
                    )

    model.run()
    elapsed = time.perf_counter() - started
    model_status = model.getModelStatus()
    model_status_name = model_status.name
    info = model.getInfo()
    solution = model.getSolution()
    gap = float(info.mip_gap) if np.isfinite(info.mip_gap) else None
    nodes = int(info.mip_node_count)

    if model_status == highspy.HighsModelStatus.kInfeasible:
        return PolicySelection(
            status=(
                "MODELED_BANK_INFEASIBLE_PROVEN"
                if bank.complete
                else "CANDIDATE_BANK_EXHAUSTED_INCOMPLETE"
            ),
            selected_candidate_indexes=(),
            elapsed_seconds=elapsed,
            time_limit_seconds=budget,
            objective_prior_points=None,
            mip_gap=gap,
            node_count=nodes,
            model_status=model_status_name,
            infeasibility_scope=("COMPLETE_MODELED_BANK" if bank.complete else None),
        )
    limits = {
        highspy.HighsModelStatus.kTimeLimit,
        highspy.HighsModelStatus.kIterationLimit,
        highspy.HighsModelStatus.kSolutionLimit,
    }
    if model_status in limits and solution.value_valid:
        # A limit with a valid integer incumbent (Session 08): the same checks
        # as the optimum below, and no optimality scope.
        status = LIMIT_INCUMBENT_STATUS
    elif model_status == highspy.HighsModelStatus.kTimeLimit:
        status = "PORTFOLIO_SELECTION_TIME_LIMIT"
    elif model_status in {
        highspy.HighsModelStatus.kIterationLimit,
        highspy.HighsModelStatus.kSolutionLimit,
    }:
        status = "PORTFOLIO_SELECTION_SEARCH_LIMIT"
    elif model_status != highspy.HighsModelStatus.kOptimal or not solution.value_valid:
        status = "PORTFOLIO_SELECTION_SOLVER_ERROR"
    else:
        status = "OPTIMAL"
    if status not in {"OPTIMAL", LIMIT_INCUMBENT_STATUS}:
        return PolicySelection(
            status=status,
            selected_candidate_indexes=(),
            elapsed_seconds=elapsed,
            time_limit_seconds=budget,
            objective_prior_points=None,
            mip_gap=gap,
            node_count=nodes,
            model_status=model_status_name,
            infeasibility_scope=None,
        )

    raw_counts = np.asarray(solution.col_value[:candidate_count])
    rounded_counts = np.rint(raw_counts).astype(int)
    if (
        np.max(np.abs(raw_counts - rounded_counts)) > 1e-6
        or np.any(rounded_counts < 0)
        or int(rounded_counts.sum()) != count
    ):
        return PolicySelection(
            status="PORTFOLIO_SELECTION_SOLVER_ERROR",
            selected_candidate_indexes=(),
            elapsed_seconds=elapsed,
            time_limit_seconds=budget,
            objective_prior_points=None,
            mip_gap=gap,
            node_count=nodes,
            model_status="INVALID_INTEGER_SOLUTION",
            infeasibility_scope=None,
        )
    selected = tuple(
        index
        for index, multiplicity in enumerate(rounded_counts)
        for _ in range(int(multiplicity))
    )
    selected = tuple(
        sorted(
            selected,
            key=lambda index: (
                -candidates[index].prior_points,
                candidates[index].canonical_key,
                candidates[index].roster,
                index,
            ),
        )
    )
    return PolicySelection(
        status=status,
        selected_candidate_indexes=selected,
        elapsed_seconds=elapsed,
        time_limit_seconds=budget,
        objective_prior_points=sum(candidates[index].prior_points for index in selected),
        mip_gap=gap,
        node_count=nodes,
        model_status=model_status_name,
        infeasibility_scope=None,
    )


def exact_assignments_for_entries(
    entry_ids: Sequence[str], rosters: Sequence[Sequence[str]]
) -> dict[str, tuple[str, ...]]:
    """Assign exactly one roster to every Entry ID without cycling."""

    entries = tuple(str(entry).strip() for entry in entry_ids)
    if not entries:
        raise ValueError("PORTFOLIO_ASSIGNMENT_ENTRY_SET_EMPTY")
    if any(not entry for entry in entries):
        raise ValueError("PORTFOLIO_ASSIGNMENT_ENTRY_ID_BLANK")
    duplicates = sorted(entry for entry, total in Counter(entries).items() if total > 1)
    if duplicates:
        raise ValueError(f"PORTFOLIO_ASSIGNMENT_DUPLICATE_ENTRY_ID:{duplicates}")
    if len(rosters) != len(entries):
        raise ValueError(
            "PORTFOLIO_ASSIGNMENT_COVERAGE_MISMATCH:"
            f"entries={len(entries)}:lineups={len(rosters)}:cycling=disabled"
        )
    return {
        entry: tuple(str(dk_id).strip() for dk_id in roster)
        for entry, roster in zip(entries, rosters, strict=True)
    }


def ordered_assignment_sha256(
    assignments: Mapping[str, Sequence[str]] | Sequence[tuple[str, Sequence[str]]],
) -> str:
    pairs = list(assignments.items()) if isinstance(assignments, Mapping) else list(assignments)
    payload = {
        "entry_assignments": [
            {"entry_id": str(entry), "roster": [str(dk_id) for dk_id in roster]}
            for entry, roster in pairs
        ]
    }
    return sha256_bytes(canonical_decimal_json_bytes(payload))


def _assignment_pairs_from_csv_bytes(raw: bytes) -> tuple[tuple[str, tuple[str, ...]], ...]:
    text = raw.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text, newline=""))
    try:
        header = tuple(next(reader))
    except StopIteration as exc:
        raise ValueError("PORTFOLIO_AUDIT_ASSIGNMENT_ARTIFACT_EMPTY") from exc
    expected = ("Entry ID", "CPT", "FLEX", "FLEX", "FLEX", "FLEX", "FLEX")
    if header != expected:
        raise ValueError(f"PORTFOLIO_AUDIT_ASSIGNMENT_ARTIFACT_HEADER:{header}")
    pairs: list[tuple[str, tuple[str, ...]]] = []
    for row_number, row in enumerate(reader, start=2):
        if not row or not any(cell.strip() for cell in row):
            continue
        if len(row) != len(expected):
            raise ValueError(
                f"PORTFOLIO_AUDIT_ASSIGNMENT_ARTIFACT_WIDTH:row={row_number}:width={len(row)}"
            )
        pairs.append((row[0].strip(), tuple(cell.strip() for cell in row[1:])))
    return tuple(pairs)


def _audit_problem(code: str, detail: str) -> str:
    return f"{code}:{detail}"


@dataclass(frozen=True)
class _AuditedPolicyControls:
    salary_sha256: str
    entry_ids: tuple[str, ...]
    require_unique_lineups: bool
    max_pairwise_person_overlap: int
    person_limits: tuple[tuple[str, int, int], ...]


def _strict_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key {key!r}")
        value[key] = item
    return value


def _reject_json_constant(value: str) -> object:
    raise ValueError(f"nonfinite JSON number {value!r}")


def _mapping_at(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _integer_at(value: object, label: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{label} must be an integer >= {minimum}")
    return value


def _parse_audited_policy_controls(raw: bytes) -> _AuditedPolicyControls:
    """Strictly reparse only the normalized controls the audit must enforce."""

    payload = json.loads(
        raw.decode("utf-8"),
        object_pairs_hook=_strict_json_object,
        parse_float=Decimal,
        parse_constant=_reject_json_constant,
    )
    root = _mapping_at(payload, "normalized policy")
    if canonical_decimal_json_bytes(root) != raw:
        raise ValueError("normalized policy bytes are not canonical")
    if root.get("schema_version") != "nfl_showdown_portfolio_policy_normalized_v1":
        raise ValueError("normalized policy schema_version is unsupported")

    bindings = _mapping_at(root.get("bindings"), "bindings")
    salary_sha256 = bindings.get("salary_sha256")
    if not isinstance(salary_sha256, str) or not salary_sha256:
        raise ValueError("bindings.salary_sha256 must be a nonempty string")
    raw_entry_ids = bindings.get("entry_ids")
    if not isinstance(raw_entry_ids, list) or not raw_entry_ids:
        raise ValueError("bindings.entry_ids must be a nonempty array")
    entry_ids = tuple(raw_entry_ids)
    if any(not isinstance(entry, str) or not entry for entry in entry_ids):
        raise ValueError("bindings.entry_ids must contain nonempty strings")
    if len(set(entry_ids)) != len(entry_ids):
        raise ValueError("bindings.entry_ids contains duplicates")

    controls = _mapping_at(root.get("controls"), "controls")
    require_unique = controls.get("require_unique_lineups")
    if not isinstance(require_unique, bool):
        raise ValueError("controls.require_unique_lineups must be boolean")
    overlap = _integer_at(
        controls.get("effective_pairwise_person_overlap"),
        "controls.effective_pairwise_person_overlap",
    )
    if overlap > 6:
        raise ValueError("controls.effective_pairwise_person_overlap must be <= 6")

    effective = _mapping_at(root.get("effective"), "effective")
    denominator = _integer_at(
        effective.get("entry_count_denominator"),
        "effective.entry_count_denominator",
        minimum=1,
    )
    if denominator != len(entry_ids):
        raise ValueError("effective entry denominator does not match entry IDs")
    raw_people = effective.get("people")
    if not isinstance(raw_people, list) or not raw_people:
        raise ValueError("effective.people must be a nonempty array")
    person_limits: list[tuple[str, int, int]] = []
    for index, raw_person in enumerate(raw_people):
        person = _mapping_at(raw_person, f"effective.people[{index}]")
        underlying_id = person.get("underlying_id")
        if not isinstance(underlying_id, str) or not underlying_id:
            raise ValueError(f"effective.people[{index}].underlying_id is invalid")
        combined = _integer_at(
            person.get("combined_max_entries"),
            f"effective.people[{index}].combined_max_entries",
        )
        captain = _integer_at(
            person.get("captain_max_entries"),
            f"effective.people[{index}].captain_max_entries",
        )
        person_limits.append((underlying_id, combined, captain))
    if len({person for person, _combined, _captain in person_limits}) != len(
        person_limits
    ):
        raise ValueError("effective.people contains duplicate underlying IDs")
    return _AuditedPolicyControls(
        salary_sha256=salary_sha256,
        entry_ids=entry_ids,
        require_unique_lineups=require_unique,
        max_pairwise_person_overlap=overlap,
        person_limits=tuple(person_limits),
    )


def audit_policy_assignments(
    *,
    slate: SlateContract,
    policy: NormalizedPortfolioPolicy,
    assignments: Mapping[str, Sequence[str]] | Sequence[tuple[str, Sequence[str]]],
    salary_bytes: bytes,
    entry_bytes: bytes,
    expected_entry_sha256: str,
    source_policy_bytes: bytes,
    expected_source_policy_sha256: str,
    normalized_policy_bytes: bytes,
    expected_normalized_policy_sha256: str,
    assignment_artifact_bytes: bytes,
    expected_assignment_artifact_sha256: str,
    selector_summary: Mapping[str, object] | None = None,
) -> PortfolioAudit:
    """Recompute every SD4 control from exact final roster IDs and artifacts."""

    problems: list[str] = []
    try:
        audited_policy = _parse_audited_policy_controls(normalized_policy_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        audited_policy = None
        problems.append(
            _audit_problem(
                "PORTFOLIO_AUDIT_NORMALIZED_POLICY_INVALID",
                f"{type(exc).__name__}:{exc}",
            )
        )
    pairs = list(assignments.items()) if isinstance(assignments, Mapping) else list(assignments)
    normalized_pairs = [
        (str(entry).strip(), tuple(str(dk_id).strip() for dk_id in roster))
        for entry, roster in pairs
    ]
    actual_entries = tuple(entry for entry, _roster in normalized_pairs)
    expected_entries = (
        audited_policy.entry_ids if audited_policy is not None else policy.entry_ids
    )
    duplicates = sorted(entry for entry, total in Counter(actual_entries).items() if total > 1)
    if duplicates:
        problems.append(_audit_problem("PORTFOLIO_AUDIT_DUPLICATE_ENTRY_ID", str(duplicates)))
    missing = [entry for entry in expected_entries if entry not in set(actual_entries)]
    extra = [entry for entry in actual_entries if entry not in set(expected_entries)]
    if missing:
        problems.append(_audit_problem("PORTFOLIO_AUDIT_MISSING_ENTRY_ID", str(missing)))
    if extra:
        problems.append(_audit_problem("PORTFOLIO_AUDIT_EXTRA_ENTRY_ID", str(extra)))
    if missing and not extra:
        problems.append(
            _audit_problem(
                "PORTFOLIO_AUDIT_PARTIAL_ASSIGNMENT_COVERAGE",
                f"assigned={len(actual_entries)}:requested={len(expected_entries)}",
            )
        )
    if not missing and not extra and not duplicates and actual_entries != expected_entries:
        problems.append(
            _audit_problem(
                "PORTFOLIO_AUDIT_ENTRY_ID_ORDER_MISMATCH",
                f"actual={actual_entries}:expected={expected_entries}",
            )
        )

    actual_hashes = {
        "salary_sha256": sha256_bytes(salary_bytes),
        "entry_sha256": sha256_bytes(entry_bytes),
        "source_policy_sha256": sha256_bytes(source_policy_bytes),
        "normalized_policy_sha256": sha256_bytes(normalized_policy_bytes),
        "assignment_artifact_sha256": sha256_bytes(assignment_artifact_bytes),
        "ordered_assignment_sha256": ordered_assignment_sha256(normalized_pairs),
    }
    expected_hashes = {
        "salary_sha256": (
            audited_policy.salary_sha256
            if audited_policy is not None
            else policy.salary_sha256
        ),
        "entry_sha256": expected_entry_sha256,
        "source_policy_sha256": expected_source_policy_sha256,
        "normalized_policy_sha256": expected_normalized_policy_sha256,
        "assignment_artifact_sha256": expected_assignment_artifact_sha256,
    }
    for label, expected in expected_hashes.items():
        if actual_hashes[label] != expected:
            problems.append(
                _audit_problem(
                    f"PORTFOLIO_AUDIT_{label.upper()}_MISMATCH",
                    f"actual={actual_hashes[label]}:expected={expected}",
                )
            )
    if normalized_policy_bytes != policy.canonical_bytes():
        problems.append(
            _audit_problem(
                "PORTFOLIO_AUDIT_NORMALIZED_POLICY_BYTES_MISMATCH",
                "the audited artifact is not the exact canonical policy consumed by the selector",
            )
        )

    try:
        artifact_pairs = _assignment_pairs_from_csv_bytes(assignment_artifact_bytes)
    except (UnicodeDecodeError, csv.Error, ValueError) as exc:
        problems.append(
            _audit_problem(
                "PORTFOLIO_AUDIT_ASSIGNMENT_ARTIFACT_INVALID",
                f"{type(exc).__name__}:{exc}",
            )
        )
    else:
        if artifact_pairs != tuple(normalized_pairs):
            problems.append(
                _audit_problem(
                    "PORTFOLIO_AUDIT_ASSIGNMENT_ARTIFACT_MISMATCH",
                    "assignment rows, order, or roster IDs differ from the final in-memory assignment",
                )
            )

    by_id = {row.dk_id: row for row in slate.players}
    canonical: list[tuple[str, str]] = []
    people_by_entry: dict[str, frozenset[str]] = {}
    combined: Counter[str] = Counter()
    captains: Counter[str] = Counter()
    for entry, roster in normalized_pairs:
        validation = validate_lineup(slate, roster)
        if not validation.valid or validation.lineup is None:
            problems.extend(
                _audit_problem("PORTFOLIO_AUDIT_LINEUP_ILLEGAL", f"entry={entry}:{detail}")
                for detail in validation.errors
            )
            continue
        people = frozenset(by_id[dk_id].underlying_id for dk_id in roster)
        captain = by_id[roster[0]].underlying_id
        canonical.append((entry, validation.lineup.canonical_key))
        people_by_entry[entry] = people
        combined.update(people)
        captains[captain] += 1

    if audited_policy is not None:
        limits = {
            person: (combined_limit, captain_limit)
            for person, combined_limit, captain_limit in audited_policy.person_limits
        }
        require_unique_lineups = audited_policy.require_unique_lineups
        overlap_limit = audited_policy.max_pairwise_person_overlap
    else:
        limits = {
            item.person.underlying_id: (
                item.combined_max_entries,
                item.captain_max_entries,
            )
            for item in policy.effective_limits
        }
        require_unique_lineups = policy.require_unique_lineups
        overlap_limit = policy.effective_pairwise_person_overlap
    for person, total in sorted(combined.items()):
        limit = limits.get(person)
        if limit is None:
            problems.append(
                _audit_problem("PORTFOLIO_AUDIT_UNKNOWN_PERSON", f"person={person}")
            )
        elif total > limit[0]:
            problems.append(
                _audit_problem(
                    "PORTFOLIO_AUDIT_COMBINED_PERSON_CAP_EXCEEDED",
                    f"person={person}:actual={total}:maximum={limit[0]}",
                )
            )
    for person, total in sorted(captains.items()):
        limit = limits.get(person)
        if limit is None:
            problems.append(
                _audit_problem("PORTFOLIO_AUDIT_UNKNOWN_CAPTAIN", f"person={person}")
            )
        elif total > limit[1]:
            problems.append(
                _audit_problem(
                    "PORTFOLIO_AUDIT_CAPTAIN_CAP_EXCEEDED",
                    f"person={person}:actual={total}:maximum={limit[1]}",
                )
            )

    canonical_counts = Counter(key for _entry, key in canonical)
    if require_unique_lineups:
        for key, total in sorted(canonical_counts.items()):
            if total > 1:
                problems.append(
                    _audit_problem(
                        "PORTFOLIO_AUDIT_CANONICAL_DUPLICATE",
                        f"count={total}:canonical={key}",
                    )
                )
    overlaps: list[tuple[str, str, int]] = []
    for left_index, left in enumerate(expected_entries):
        if left not in people_by_entry:
            continue
        for right in expected_entries[left_index + 1 :]:
            if right not in people_by_entry:
                continue
            overlap = len(people_by_entry[left] & people_by_entry[right])
            overlaps.append((left, right, overlap))
            if overlap > overlap_limit:
                problems.append(
                    _audit_problem(
                        "PORTFOLIO_AUDIT_PAIRWISE_OVERLAP_EXCEEDED",
                        f"entries={left},{right}:actual={overlap}:maximum="
                        f"{overlap_limit}",
                    )
                )

    if selector_summary is not None:
        expected_summary = {
            "person_exposure": dict(sorted(combined.items())),
            "captain_exposure": dict(sorted(captains.items())),
            "pairwise_person_overlap": [
                {"entry_id_a": left, "entry_id_b": right, "people": overlap}
                for left, right, overlap in overlaps
            ],
            "selected_lineup_count": len(normalized_pairs),
        }
        for label, expected in expected_summary.items():
            if selector_summary.get(label) != expected:
                problems.append(
                    _audit_problem(
                        "PORTFOLIO_AUDIT_SELECTOR_SUMMARY_MISMATCH",
                        f"field={label}",
                    )
                )

    return PortfolioAudit(
        problems=tuple(problems),
        entry_ids=actual_entries,
        canonical_lineups=tuple(canonical),
        combined_person_counts=tuple(sorted(combined.items())),
        captain_counts=tuple(sorted(captains.items())),
        pairwise_person_overlap=tuple(overlaps),
        hashes=tuple(sorted(actual_hashes.items())),
    )
