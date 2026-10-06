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
from dataclasses import dataclass, field, replace
from decimal import Decimal
from typing import Callable, Mapping, Sequence

import highspy
import numpy as np

from .contest_assignment import CONTEST_ASSIGNMENT_VERSION, Claim as ContestAssignmentClaim
from .contracts import EngineMode, SlateContract
from .dk import parse_entry_bytes
from .entry_groups import prefilled_cell_id
from .hashing import sha256_bytes
from .lineups import roster_canonical_key, validate_lineup
from .optimizer import LIMIT_INCUMBENT_STATUS, LineupOptimizer
from .portfolio_policy import (
    OPEN_RANGE,
    OPEN_STRUCTURAL_BOUNDS,
    NORMALIZED_POLICY_SCHEMA_VERSIONS,
    EffectivePersonLimit,
    NormalizedPortfolioPolicy,
    PersonBinding,
    StructuralBoundRange,
    StructuralBounds,
    canonical_decimal_json_bytes,
    structural_bound_violations,
    thesis_roster_violations,
    thesis_widened_bounds,
)
from .showdown_theses import (
    ACTIVE,
    DROPPED,
    MAX_ROW_WEIGHT,
    THESIS_BUILD_VERSION,
    THESIS_PORTFOLIO_VERSION,
    CountBound,
    ShowdownThesis,
    admitted_quarterbacks,
    allot_rows,
    apply_thesis_rows,
    backup_quarterbacks,
    thesis_excluded_dk_ids,
    thesis_portfolio_measures,
    thesis_violations,
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
    # Session 23c: the active theses this roster follows (recomputed with `thesis_roster_violations`, never
    # inherited from the stratum that found it), in declared order. Empty when the policy has no thesis.
    serves: tuple[str, ...] = ()


@dataclass(frozen=True)
class ThesisContext:
    """One active thesis as the bank and the probe apply it (Session 23c).

    `rows` is its allotment (a v3 thesis owns every entry), `backups` the quarterbacks out of its own pool,
    `bounds` the structural bounds its rows obey (a v4 thesis's own `effective_bounds`, a v3 policy's
    widened `structural_bounds`) and `excluded_dk_ids` the rows it keeps out of every lineup built under it.
    """

    thesis: ShowdownThesis
    rows: int
    backups: frozenset[str] = frozenset()
    bounds: StructuralBounds = OPEN_STRUCTURAL_BOUNDS
    excluded_dk_ids: tuple[str, ...] = ()

    @property
    def name(self) -> str:
        return self.thesis.name


def thesis_contexts(
    slate: SlateContract,
    policy: NormalizedPortfolioPolicy | None,
    thesis_backups: Mapping[str, frozenset[str]] | None = None,
) -> tuple[ThesisContext, ...]:
    """The policy's active theses in declared order, each with the rows and bounds its lineups obey.

    `thesis_backups` maps a thesis name to the quarterbacks the depth evidence puts out of that thesis's
    pool (v4: they differ by thesis, because a thesis may name one). A v3 thesis gets none here: its
    backups arrive in the run's exclusions, as in Session 23b.
    """

    if policy is None or not policy.active_theses:
        return ()
    v4 = policy.thesis_schema == "v4"
    backups = thesis_backups or {}
    contexts = []
    for thesis in policy.active_theses:
        gone = frozenset(backups.get(thesis.name, ())) if v4 else frozenset()
        contexts.append(ThesisContext(
            thesis=thesis,
            rows=thesis.rows if v4 else policy.entry_count,
            backups=gone,
            bounds=thesis.effective_bounds if v4 and thesis.effective_bounds is not None else policy.structural_bounds,
            excluded_dk_ids=thesis_excluded_dk_ids(slate, thesis, gone),
        ))
    return tuple(contexts)


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
    # Session 23c: each active thesis with its allotment and how many bank candidates follow it.
    theses: tuple[tuple[str, int, int], ...] = ()

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
            **({"theses": {name: {"rows": rows, "serving": serving} for name, rows, serving in self.theses}}
               if self.theses else {}),
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
    # Session 23c: the thesis each pick fills, aligned with `selected_candidate_indexes` (empty without theses).
    selected_theses: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        # A time- or search-limited incumbent passes like the optimum (Session 08).
        return self.status in {"OPTIMAL", LIMIT_INCUMBENT_STATUS}

    def as_report(self) -> dict[str, object]:
        return {
            **({"selected_theses": list(self.selected_theses)} if self.selected_theses else {}),
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
    max_person_share: Mapping[str, object] = field(default_factory=dict)
    contest_assignment: Mapping[str, object] = field(default_factory=dict)
    theses: Mapping[str, object] = field(default_factory=dict)

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
            "max_person_share": dict(self.max_person_share),
            **({"contest_assignment": dict(self.contest_assignment)} if self.contest_assignment else {}),
            **({"theses": dict(self.theses)} if self.theses else {}),
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
                "STRUCTURAL_HYGIENE_BOUNDS",
                "SALARY_ENTRY_SOURCE_POLICY_NORMALIZED_POLICY_ASSIGNMENT_HASHES",
                "SELECTOR_SUMMARY_RECONCILIATION",
            ],
        }


def _finite_positive(value: float, label: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{label} must be positive and finite")
    return number


def _apply_structural_bounds(
    optimizer: LineupOptimizer, slate: SlateContract, bounds: StructuralBounds
) -> None:
    """Bind `bounds` as real MILP rows on `optimizer` (Session 23), not a post-filter.

    `qb_count`, `kicker_count` and `dst_count` are plain selected-count bounds
    over a position; `salary_left` is a total-salary band; `pass_catchers_
    with_rostered_qb` reuses the Classic QB-correlation big-M rows (per QB
    row, whichever role he is rostered in); `offense_against_own_dst` is
    pairwise "not both" rows between every DST row and every other same-team
    row. An open (`None`) side never adds a row, matching v1's fully-open
    default.
    """

    if bounds.qb_count != OPEN_RANGE:
        optimizer.add_selected_count_bounds(
            [row.dk_id for row in slate.players if row.position == "QB"],
            minimum=bounds.qb_count.minimum or 0,
            maximum=bounds.qb_count.maximum,
        )
    if bounds.kicker_count_maximum is not None:
        optimizer.add_selected_count_bounds(
            [row.dk_id for row in slate.players if row.position == "K"],
            maximum=bounds.kicker_count_maximum,
        )
    if bounds.dst_count_maximum is not None:
        optimizer.add_selected_count_bounds(
            [row.dk_id for row in slate.players if row.position == "DST"],
            maximum=bounds.dst_count_maximum,
        )
    if bounds.salary_left != OPEN_RANGE:
        salary_minimum = (
            None if bounds.salary_left.maximum is None else slate.salary_cap - bounds.salary_left.maximum
        )
        salary_maximum = (
            None if bounds.salary_left.minimum is None else slate.salary_cap - bounds.salary_left.minimum
        )
        optimizer.add_salary_band(minimum=salary_minimum, maximum=salary_maximum)
    if bounds.pass_catchers_with_rostered_qb != OPEN_RANGE:
        optimizer.add_classic_qb_correlation_bounds(
            kind="PASS_CATCHER",
            minimum=bounds.pass_catchers_with_rostered_qb.minimum or 0,
            maximum=(
                bounds.pass_catchers_with_rostered_qb.maximum
                if bounds.pass_catchers_with_rostered_qb.maximum is not None
                else 5
            ),
        )
    if bounds.offense_against_own_dst:
        optimizer.add_no_offense_with_dst()


@dataclass(frozen=True)
class LockstepResult:
    """What `run_lockstep` found: the lineups in the order they were taken, and why each thesis stopped.

    `exhausted` are theses whose model was proved to hold no further lineup; `unproven` are theses a solver
    limit stopped before either its target or a proof, which proves nothing about them. `blocking` is the
    bank's own blocking status when a limit stopped a solve with no roster.
    """

    rosters: tuple[tuple[str, tuple[str, ...]], ...]
    found: Mapping[str, int]
    wanted: Mapping[str, int]
    exhausted: tuple[str, ...]
    unproven: tuple[str, ...]
    solve_count: int
    blocking: str | None = None
    terminal: str | None = None


def _blocking_status(model_status: str) -> str:
    """The bank's blocking status for a solve a limit or an error stopped with no roster."""

    if model_status == "kTimeLimit":
        return "CANDIDATE_BANK_TIME_LIMIT"
    if model_status in {"kIterationLimit", "kSolutionLimit"}:
        return "CANDIDATE_BANK_SEARCH_LIMIT"
    return "CANDIDATE_BANK_SOLVER_ERROR"


def run_lockstep(
    slate: SlateContract,
    objective: Mapping[str, float],
    contexts: Sequence[ThesisContext],
    *,
    excluded_ids: Sequence[str],
    forbidden_rosters: Sequence[tuple[str, ...]] = (),
    chain_policy: NormalizedPortfolioPolicy | None,
    targets: Mapping[str, int],
    per_solve_seconds: float,
    total_seconds: float,
    on_roster: Callable[[str, tuple[str, ...], object], None] | None = None,
    perturbation_offset: int = 0,
    sequential: bool = False,
) -> LockstepResult:
    """One optimizer per thesis, taking rows round-robin in declared order (Session 23c).

    With `sequential`, a thesis takes all its rows before the next one starts: declared order as a
    strict priority, which is what the structural probe means by "an earlier thesis wins".

    Each thesis's model carries that thesis's rows, bounds and exclusions; every lineup any of them finds is
    a no-good in all of them, so no two theses ever take the same roster, and every prefilled roster is a
    no-good from the start (R29). With `chain_policy` the chain also keeps itself a legal portfolio under the
    policy's own caps: a person or Captain that reaches its maximum leaves every model, and every later lineup
    shares at most the overlap limit with every earlier one. That is the bank's chain stratum, whose lineups
    are a portfolio already legal under every cap whenever greedy succeeds. With none, it is the structural
    probe (`probe_thesis_rows`): thesis rules and the run's exclusions only.

    Declared order is the priority: an earlier thesis takes its lineups first. A solve a limit stopped
    proves nothing and is `unproven`, never `exhausted`.
    """

    started = time.perf_counter()
    names = [context.name for context in contexts]
    wanted = {name: max(0, int(targets.get(name, 0))) for name in names}
    optimizers: dict[str, LineupOptimizer] = {}
    for context in contexts:
        optimizer = LineupOptimizer(
            slate,
            excluded_ids=tuple(sorted({*(str(item) for item in excluded_ids), *context.excluded_dk_ids})),
            time_limit_seconds=min(total_seconds, per_solve_seconds),
        )
        _apply_structural_bounds(optimizer, slate, context.bounds)
        apply_thesis_rows(optimizer, slate, context.thesis)
        for roster in forbidden_rosters:
            optimizer.add_no_good(roster)
        optimizers[context.name] = optimizer
    by_id = {row.dk_id: row for row in slate.players}
    limits = {item.person.underlying_id: item for item in chain_policy.effective_limits} if chain_policy else {}
    overlap = chain_policy.effective_pairwise_person_overlap if chain_policy is not None else 6
    chain_people: Counter[str] = Counter()
    chain_captains: Counter[str] = Counter()
    closed: set[str] = set()
    found = {name: 0 for name in names}
    exhausted: list[str] = []
    unproven: list[str] = []
    taken: list[tuple[str, tuple[str, ...]]] = []
    solves = 0
    blocking: str | None = None
    live = [name for name in names if wanted[name] > 0]
    while live and blocking is None:
        for name in (live[:1] if sequential else list(live)):
            remaining = total_seconds - (time.perf_counter() - started)
            if remaining <= 0:
                blocking = "CANDIDATE_BANK_TIME_LIMIT"
                unproven.extend(item for item in live if item not in unproven)
                live = []
                break
            optimizer = optimizers[name]
            optimizer.set_time_limit(min(per_solve_seconds, remaining))
            cycle = perturbation_offset + solves
            perturbed = {
                row.dk_id: float(objective.get(row.dk_id, 0.0)) + 1e-9 * (((cycle + 1) * (index + 17)) % 997)
                for index, row in enumerate(slate.players)
            }
            result = optimizer.solve(perturbed)
            solves += 1
            if result.status == "INFEASIBLE":
                exhausted.append(name)
                live.remove(name)
                continue
            kept_at_limit = (
                result.status == "FEASIBLE_LIMIT"
                and result.roster is not None
                and result.model_status in {"kTimeLimit", "kIterationLimit", "kSolutionLimit"}
            )
            if not kept_at_limit and (result.status != "OPTIMAL" or result.roster is None):
                blocking = _blocking_status(result.model_status)
                unproven.append(name)
                live.remove(name)
                break
            roster = tuple(result.roster)
            if validate_lineup(slate, roster).lineup is None:
                blocking = "CANDIDATE_BANK_SOLVER_ERROR"
                unproven.append(name)
                live.remove(name)
                break
            found[name] += 1
            taken.append((name, roster))
            if on_roster is not None:
                on_roster(name, roster, result)
            people = frozenset(by_id[dk_id].underlying_id for dk_id in roster)
            captain = by_id[roster[0]].underlying_id
            for other in optimizers.values():
                other.add_no_good(roster)
                if chain_policy is not None and overlap < 6:
                    other.add_person_overlap_limit(roster, overlap)
            if chain_policy is not None:
                for member in people:
                    chain_people[member] += 1
                    limit = limits.get(member)
                    if limit is None or chain_people[member] < limit.combined_max_entries:
                        continue
                    for dk_id in (limit.person.cpt_dk_id, limit.person.flex_dk_id):
                        if dk_id not in closed:
                            closed.add(dk_id)
                            for other in optimizers.values():
                                other.add_no_good([dk_id])
                chain_captains[captain] += 1
                limit = limits.get(captain)
                if (limit is not None and chain_captains[captain] >= limit.captain_max_entries
                        and limit.person.cpt_dk_id not in closed):
                    closed.add(limit.person.cpt_dk_id)
                    for other in optimizers.values():
                        other.add_no_good([limit.person.cpt_dk_id])
                # A thesis keeps room for the rows it still has to take. Its Captain room is what its Captain set
                # may still captain (each person's Captain and combined room, the smaller); once that is no more
                # than the rows it has left, the set's members leave every model's FLEX slots (their Captain rows
                # stay open). Without it greedy spends a star's cap on the first theses's FLEX slots and leaves
                # his own thesis unbuildable: a chain that is no witness at all.
                for context in contexts:
                    left = wanted[context.name] - found[context.name]
                    if left <= 0:
                        continue
                    members = [limits[person] for person in sorted(context.thesis.captain_people) if person in limits]
                    room = sum(
                        max(0, min(item.captain_max_entries - chain_captains[item.person.underlying_id],
                                   item.combined_max_entries - chain_people[item.person.underlying_id]))
                        for item in members)
                    if room > left:
                        continue
                    for item in members:
                        if item.person.flex_dk_id not in closed:
                            closed.add(item.person.flex_dk_id)
                            for other in optimizers.values():
                                other.add_no_good([item.person.flex_dk_id])
            if found[name] >= wanted[name]:
                live.remove(name)
    if blocking is not None:
        unproven.extend(item for item in live if item not in unproven)
    return LockstepResult(
        rosters=tuple(taken), found=dict(found), wanted=wanted, exhausted=tuple(exhausted),
        unproven=tuple(unproven), solve_count=solves, blocking=blocking,
        terminal=blocking or ("MODEL_INFEASIBLE" if exhausted else "TARGET_REACHED"),
    )


@dataclass(frozen=True)
class ShortThesis:
    name: str
    found: int
    wanted: int


@dataclass(frozen=True)
class ThesisProbe:
    """`probe_thesis_rows`: which theses cannot fill their rows with lineups distinct from the others'."""

    short: tuple[ShortThesis, ...]
    unproven: tuple[str, ...]
    found: Mapping[str, int]
    solve_count: int


def probe_thesis_rows(
    slate: SlateContract,
    objective: Mapping[str, float],
    policy: NormalizedPortfolioPolicy,
    *,
    excluded_ids: Sequence[str] = (),
    forbidden_rosters: Sequence[tuple[str, ...]] = (),
    thesis_backups: Mapping[str, frozenset[str]] | None = None,
    per_solve_seconds: float,
    total_seconds: float,
) -> ThesisProbe:
    """Can every active thesis get its allotted rows, distinct from one another and from prefilled rosters?

    Before any bank (Session 23c): the lockstep run with the caps off, under each thesis's own rules and the
    run's exclusions alone, because those never loosen. A thesis that cannot is "structurally short" and the
    ladder drops it by name, its rows going to the others. An independent per-thesis check would pass two
    theses that each have room and collide; this one does not. It is greedy in declared order, which is the
    priority, so a near-duplicate thesis can be named short; the reason says how many it found. A solve a
    limit stopped proves nothing, so that thesis is `unproven`, not short.
    """

    # The policy's structural bounds (a salary band, a quarterback count) are preferences the ladder loosens, so
    # the probe leaves them open: a thesis that cannot spend a salary band is a bank the ladder repairs by
    # dropping the band, not a thesis to drop. A thesis's own team and position counts are its rows and stay.
    contexts = tuple(replace(context, bounds=OPEN_STRUCTURAL_BOUNDS) for context in thesis_contexts(
        slate, policy, thesis_backups))
    result = run_lockstep(
        slate, objective, contexts, excluded_ids=excluded_ids, forbidden_rosters=forbidden_rosters,
        chain_policy=None, targets={context.name: context.rows for context in contexts},
        per_solve_seconds=per_solve_seconds, total_seconds=total_seconds, sequential=True)
    short = tuple(
        ShortThesis(name, result.found[name], result.wanted[name])
        for name in result.exhausted if result.found[name] < result.wanted[name])
    return ThesisProbe(short=short, unproven=result.unproven, found=result.found, solve_count=result.solve_count)


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
        forbidden_rosters: Sequence[tuple[str, ...]] = (),
        structural_bounds: StructuralBounds = OPEN_STRUCTURAL_BOUNDS,
        contexts: Sequence[ThesisContext] = (),
        report_theses: bool = False,
    ) -> None:
        self.slate = slate
        self.objective = objective
        self.excluded_ids = tuple(sorted({str(dk_id) for dk_id in excluded_ids}))
        # The template's prefilled rosters (Session 11): cut from every solve and
        # held as already seen, so no candidate the joint solve sees repeats one.
        self.forbidden = tuple(tuple(map(str, roster)) for roster in forbidden_rosters)
        # Session 23: a legal DraftKings roster the policy's structural bounds
        # still reject never enters the bank; it is no-good'd and the search
        # continues, the same way an already-seen candidate is.
        self.structural_bounds = structural_bounds
        # Session 23b: an active thesis's team and position counts are rows on every
        # stratum's model too; its Captain set and exclusions arrive as excluded rows.
        # Session 23c: with several theses each stratum is run under one of them (`context`), and every
        # candidate records which of them it follows. One thesis is the default context of every stratum.
        self.contexts = tuple(contexts)
        self.default_context = self.contexts[0] if len(self.contexts) == 1 else None
        # A v3 bank's report is exactly what Session 23b wrote; only a v4 bank names its theses.
        self.report_theses = report_theses
        self.candidate_limit = candidate_limit
        self.total_budget = total_budget
        self.per_solve_budget = per_solve_budget
        self.started = time.perf_counter()
        self.by_id = {row.dk_id: row for row in slate.players}
        self.candidates: list[PolicyCandidate] = []
        self.canonical_seen: set[str] = {roster_canonical_key(slate, roster) for roster in self.forbidden}
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

    def excluded_for(self, context: ThesisContext | None) -> tuple[str, ...]:
        """The rows every stratum run under `context` keeps out: the run's own and the thesis's."""

        if context is None:
            return self.excluded_ids
        return tuple(sorted({*self.excluded_ids, *context.excluded_dk_ids}))

    def serves(self, roster: Sequence[str]) -> tuple[str, ...]:
        """The active theses `roster` follows, recomputed (rules, its own bounds and its backup rule)."""

        return tuple(
            context.name for context in self.contexts
            if not thesis_roster_violations(self.slate, roster, context.thesis, context.backups))

    def _add(self, roster: tuple[str, ...], canonical: str, result) -> bool:
        """Add `roster` as a new canonical candidate; False when it was already seen."""

        if canonical in self.canonical_seen:
            return False
        self.candidates.append(
            PolicyCandidate(
                roster=roster,
                canonical_key=canonical,
                people=frozenset(self.by_id[dk_id].underlying_id for dk_id in roster),
                captain_person=self.by_id[roster[0]].underlying_id,
                prior_points=sum(float(self.objective.get(dk_id, 0.0)) for dk_id in roster),
                source_solver_status=result.status,
                source_solver_seconds=result.elapsed_seconds,
                serves=self.serves(roster),
            )
        )
        self.canonical_seen.add(canonical)
        self.rosters.append(roster)
        return True

    def lockstep_chain(
        self, policy: NormalizedPortfolioPolicy, targets: Mapping[str, int]
    ) -> CandidateStratum:
        """The chain stratum for several theses: one lockstep run under the policy's own caps (Session 23c)."""

        wanted = sum(targets.values())
        if self.blocking_status is not None:
            return self.record(CandidateStratum("chain", None, wanted, 0, 0, 0, "NOT_RUN_AFTER_BLOCKER"))
        remaining = self.total_budget - self.elapsed()
        if remaining <= 0:
            self.blocking_status = "CANDIDATE_BANK_TIME_LIMIT"
            self.terminal = "TOTAL_TIME_LIMIT"
            return self.record(CandidateStratum("chain", None, wanted, 0, 0, 0, "TIME_LIMIT"))
        added = [0]

        def on_roster(_name: str, roster: tuple[str, ...], result) -> None:
            canonical = validate_lineup(self.slate, roster).lineup.canonical_key
            added[0] += int(self._add(roster, canonical, result))

        result = run_lockstep(
            self.slate, self.objective, self.contexts, excluded_ids=self.excluded_ids,
            forbidden_rosters=self.forbidden, chain_policy=policy, targets=targets,
            per_solve_seconds=self.per_solve_budget, total_seconds=remaining, on_roster=on_roster,
            perturbation_offset=self.solve_count)
        self.solve_count += result.solve_count
        if result.blocking is not None:
            self.blocking_status = result.blocking
            self.terminal = result.blocking
        terminal = {"CANDIDATE_BANK_TIME_LIMIT": "TIME_LIMIT", "CANDIDATE_BANK_SEARCH_LIMIT": "SEARCH_LIMIT",
                    "CANDIDATE_BANK_SOLVER_ERROR": "SOLVER_ERROR"}.get(result.blocking or "", None) or (
            "TARGET_REACHED" if all(result.found[name] >= result.wanted[name] for name in result.wanted)
            else "MODEL_INFEASIBLE")
        return self.record(CandidateStratum(
            "chain", None, wanted, len(result.rosters), added[0], result.solve_count, terminal))

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
        context: ThesisContext | None = None,
    ) -> CandidateStratum:
        """Run one stratum; `reserve` keeps that many bank slots for later strata.

        `context` (Session 23c) is the thesis the stratum runs under: its rows and bounds are on the model,
        its exclusions are excluded rows. With none, the one thesis of a single-thesis bank is the context.
        """

        context = context if context is not None else self.default_context
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
            excluded_ids=tuple(sorted(set(self.excluded_for(context)) | {str(x) for x in extra_excluded_ids})),
            time_limit_seconds=min(self.total_budget, self.per_solve_budget),
        )
        _apply_structural_bounds(
            optimizer, self.slate, context.bounds if context is not None else self.structural_bounds)
        if context is not None:
            apply_thesis_rows(optimizer, self.slate, context.thesis)
        for dk_id in required_ids:
            optimizer.add_required_row(dk_id)
        if seed_no_goods:
            for roster in self.rosters:
                optimizer.add_no_good(roster)
        for roster in self.forbidden:
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
            # The policy's structural hygiene bounds (Session 23) are MILP rows
            # on `optimizer` itself (`_apply_structural_bounds` above), not a
            # post-solve filter: every roster the solver returns already
            # satisfies them, the same way every other policy cap does. The
            # independent audit re-verifies them from the exact roster IDs.
            people = frozenset(self.by_id[dk_id].underlying_id for dk_id in roster)
            captain = self.by_id[roster[0]].underlying_id
            canonical = validation.lineup.canonical_key
            enumerated += 1
            if self._add(roster, canonical, result):
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
            # One fill per thesis when several theses are active: the bank is complete only when every thesis's
            # own enumeration ran out of lineups (a single thesis, or none, is the last fill as before).
            last = fills[-max(1, len(self.contexts)):] if len(self.contexts) > 1 else fills[-1:]
            complete = bool(fills) and len(last) == max(1, len(self.contexts)) and all(
                stratum.terminal == "MODEL_INFEASIBLE" for stratum in last)
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
            theses=tuple(
                (context.name, context.rows, sum(1 for candidate in self.candidates if context.name in candidate.serves))
                for context in self.contexts) if self.report_theses else (),
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
    entries: int | None = None,
) -> tuple[tuple[SeededCaptain, ...], int]:
    """Choose the seeded Captains and the per-Captain depth `k`.

    Eligible people are ordered by descending CPT-row objective, then person
    ID. Excluded people, people whose effective Captain maximum is zero and
    zero-objective rows are skipped. Captains are seeded until their summed
    effective Captain maxima cover the entry count plus `STRATUM_ENTRY_MARGIN`
    slots, and `k = ceil(entries / seeded) + 1` so the joint MILP can spread
    the entries across them without running out of choices.

    `entries` (Session 23c) is how many rows the strata must serve: the policy's whole entry count by
    default, one thesis's allotment when a portfolio of theses seeds each thesis for its own rows.
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
    rows = policy.entry_count if entries is None else int(entries)
    needed = rows + STRATUM_ENTRY_MARGIN
    for item in eligible:
        seeded.append(item)
        covered += item.captain_max_entries
        if covered >= needed:
            break
    depth = math.ceil(rows / len(seeded)) + 1 if seeded else 0
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
    forbidden_rosters: Sequence[tuple[str, ...]] = (),
    thesis_backups: Mapping[str, frozenset[str]] | None = None,
) -> CandidateBank:
    """Enumerate a deterministic bounded bank of legal policy candidates.

    `forbidden_rosters` (Session 11) are the template's prefilled rosters; no
    candidate equals one, so the joint solve never sees one.

    `thesis_backups` (Session 23c, v4) maps a thesis name to the quarterbacks out of its own pool. With
    two or more active theses the strata run once per thesis, each for its own allotment of rows, and
    every candidate records the theses it follows (`serves`); the joint solve then picks every row at once.

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
    # Session 23b: an active thesis keeps every other Captain row and its own exclusions
    # out of every stratum, so the Captain strata seed only the thesis's Captains. The
    # run's backup quarterbacks arrive in `excluded_ids` from the selector.
    contexts = thesis_contexts(slate, policy, thesis_backups)
    enumerator = _StratifiedEnumerator(
        slate,
        objective,
        excluded_ids=excluded_ids,
        candidate_limit=candidate_limit,
        total_budget=total_budget,
        per_solve_budget=per_solve_budget,
        forbidden_rosters=forbidden_rosters,
        structural_bounds=policy.structural_bounds if policy is not None else OPEN_STRUCTURAL_BOUNDS,
        contexts=contexts,
        report_theses=policy is not None and policy.thesis_schema == "v4",
    )
    if policy is None:
        enumerator.enumerate(kind="fill", target=candidate_limit)
        return enumerator.bank(policy_aware=False)

    entry_count = policy.entry_count
    if len(contexts) > 1:
        return _multi_thesis_bank(enumerator, policy, objective, contexts, candidate_limit)
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

    seeded, depth = plan_captain_strata(
        policy, objective, excluded_ids=enumerator.excluded_for(enumerator.default_context))
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


def _multi_thesis_bank(
    enumerator: _StratifiedEnumerator,
    policy: NormalizedPortfolioPolicy,
    objective: Mapping[str, float],
    contexts: Sequence[ThesisContext],
    candidate_limit: int,
) -> CandidateBank:
    """The bank for two or more active theses (Session 23c): each stratum kind, per thesis, kind-major.

    Every thesis is seeded (captain strata, then exclusion strata, each sized to that thesis's own rows)
    before the chain and before any thesis's fill, so a search that runs out of time still holds candidates
    for every thesis. The chain is one lockstep run across all of them under the policy's own caps: the
    portfolio already legal under every cap that the joint solve is handed. Each thesis's fill then tops
    it up to a share of the bank proportional to its rows, holding back slots for the theses still to come.
    """

    entry_count = policy.entry_count
    constrained = policy.effective_pairwise_person_overlap < 6 or any(
        not limit.excluded
        and (0 < limit.combined_max_entries < entry_count or 0 < limit.captain_max_entries < entry_count)
        for limit in policy.effective_limits
    )
    total_rows = sum(context.rows for context in contexts)
    reserve = min(total_rows, candidate_limit) if constrained else 0
    for context in contexts:
        seeded, depth = plan_captain_strata(
            policy, objective, excluded_ids=enumerator.excluded_for(context), entries=context.rows)
        for captain in seeded:
            enumerator.enumerate(
                kind="captain", person=captain.person, target=depth, required_ids=(captain.cpt_dk_id,),
                reserve=reserve, context=context)
    capped = sorted(
        (limit for limit in policy.effective_limits
         if not limit.excluded and 0 < limit.combined_max_entries < entry_count),
        key=lambda limit: (-float(objective.get(limit.person.flex_dk_id, 0.0)), limit.person.underlying_id),
    )

    def serving(context: ThesisContext) -> int:
        return sum(1 for candidate in enumerator.candidates if context.name in candidate.serves)

    for context in contexts:
        gone = set(enumerator.excluded_for(context))
        for limit in capped:
            person = limit.person.underlying_id
            # The person may sit in at most `combined_max_entries` of the portfolio's rows, so at least
            # `entries - cap` of them are without him, and any thesis may have to supply all of its own rows
            # among those: it needs `min(rows, entries - cap) + 1` candidates without him (the spare is the
            # single-thesis bank's own).
            depth_without = min(context.rows, entry_count - limit.combined_max_entries) + 1
            already = sum(1 for candidate in enumerator.candidates
                          if context.name in candidate.serves and person not in candidate.people)
            if already >= depth_without or limit.person.flex_dk_id in gone:
                enumerator.record(CandidateStratum("exclusion", person, depth_without, 0, 0, 0, "ALREADY_COVERED"))
                continue
            enumerator.enumerate(
                kind="exclusion", person=person, target=depth_without,
                extra_excluded_ids=(limit.person.cpt_dk_id, limit.person.flex_dk_id), reserve=reserve,
                context=context)
    if constrained:
        enumerator.lockstep_chain(policy, {context.name: context.rows for context in contexts})
    else:
        enumerator.record(CandidateStratum("chain", None, 0, 0, 0, 0, "NOT_REQUIRED_UNCONSTRAINED"))
    for index, context in enumerate(contexts):
        floor = context.rows + STRATUM_ENTRY_MARGIN
        share = max(floor, math.ceil(candidate_limit * context.rows / entry_count))
        later = sum(max(0, other.rows + STRATUM_ENTRY_MARGIN - serving(other)) for other in contexts[index + 1:])
        enumerator.enumerate(
            kind="fill", target=max(0, share - serving(context)), seed_no_goods=True, reserve=later, context=context)
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
    # Session 23c: with a portfolio of theses, `y[i, t]` says candidate i fills thesis t (only for a thesis it
    # follows). A pick fills exactly one thesis, each thesis gets exactly its allotment, and a candidate that
    # follows none of the active theses is never picked: no row is filler (brief principle 1).
    quota = {thesis.name: thesis.rows for thesis in policy.active_theses} if policy.thesis_schema == "v4" else {}
    thesis_pairs: list[tuple[int, str]] = [
        (index, name) for index, candidate in enumerate(candidates) for name in candidate.serves if name in quota]
    thesis_offset = candidate_count * 2
    variable_count = candidate_count * 2 + len(thesis_pairs)
    lower = np.zeros(variable_count, dtype=np.float64)
    upper = np.ones(variable_count, dtype=np.float64)
    # R29: a lineup fills at most one entry, whatever the policy says.
    upper[count_offset:used_offset] = 1.0
    if quota:
        followed = {index for index, _name in thesis_pairs}
        for index in range(candidate_count):
            if index not in followed:
                upper[count_offset + index] = 0.0

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
    if quota:
        by_candidate: dict[int, dict[int, float]] = {}
        by_thesis: dict[str, dict[int, float]] = {name: {} for name in quota}
        for offset, (index, name) in enumerate(thesis_pairs):
            by_candidate.setdefault(index, {})[thesis_offset + offset] = 1.0
            by_thesis[name][thesis_offset + offset] = 1.0
        for index, coefficients in by_candidate.items():
            _add_row(model, 0.0, 0.0, {**coefficients, count_offset + index: -1.0})
        for name, coefficients in by_thesis.items():
            if coefficients:
                _add_row(model, float(quota[name]), float(quota[name]), coefficients)
            else:
                # A thesis no candidate follows can never get its rows: the empty row is an honest infeasibility.
                _add_row(model, float(quota[name]), float(quota[name]), {used_offset: 0.0})

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
    selected_theses: tuple[str, ...] = ()
    if quota:
        raw_pairs = np.asarray(solution.col_value[thesis_offset:thesis_offset + len(thesis_pairs)])
        filled = {
            index: name for (index, name), value in zip(thesis_pairs, raw_pairs) if value > 0.5}
        # Each pick fills exactly one thesis and each thesis exactly its allotment, or the solve is wrong.
        if (any(index not in filled for index in selected)
                or {name: sum(1 for pick in selected if filled[pick] == name) for name in quota} != quota):
            return PolicySelection(
                status="PORTFOLIO_SELECTION_SOLVER_ERROR",
                selected_candidate_indexes=(),
                elapsed_seconds=elapsed,
                time_limit_seconds=budget,
                objective_prior_points=None,
                mip_gap=gap,
                node_count=nodes,
                model_status="INVALID_THESIS_ASSIGNMENT",
                infeasibility_scope=None,
            )
        selected_theses = tuple(filled[index] for index in selected)
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
        selected_theses=selected_theses,
    )


def exact_assignments_for_entries(
    entry_ids: Sequence[str],
    rosters: Sequence[Sequence[str]],
    *,
    unfilled_entry_ids: Sequence[str] = (),
) -> dict[str, tuple[str, ...]]:
    """Assign exactly one roster to every Entry ID without cycling.

    `unfilled_entry_ids` (Session 39b) are the Entry IDs the caller names as
    left without a lineup because the fill ran out of distinct ones (R29). They
    must be the tail of `entry_ids`, in order, and the rosters must cover every
    other Entry ID exactly: a shortfall nobody named is still a coverage
    mismatch, and the gap is never filled by repeating a roster.
    """

    entries = tuple(str(entry).strip() for entry in entry_ids)
    named = tuple(str(entry).strip() for entry in unfilled_entry_ids)
    if named:
        if len(named) > len(entries) or entries[len(entries) - len(named):] != named:
            raise ValueError(
                "PORTFOLIO_ASSIGNMENT_COVERAGE_MISMATCH:"
                f"the unfilled rows {list(named)} are not the tail of {list(entries)}:cycling=disabled"
            )
        entries = entries[: len(entries) - len(named)]
    if not entries and not named:
        raise ValueError("PORTFOLIO_ASSIGNMENT_ENTRY_SET_EMPTY")
    if any(not entry for entry in (*entries, *named)):
        raise ValueError("PORTFOLIO_ASSIGNMENT_ENTRY_ID_BLANK")
    duplicates = sorted(entry for entry, total in Counter((*entries, *named)).items() if total > 1)
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
    structural_bounds: StructuralBounds = OPEN_STRUCTURAL_BOUNDS
    theses: tuple[ShowdownThesis, ...] = ()
    # "v3" (one thesis), "v4" (a portfolio) or None, from the normalized schema the bytes declare.
    thesis_schema: str | None = None


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


def _optional_integer_at(value: object, label: str, *, minimum: int = 0) -> int | None:
    if value is None:
        return None
    return _integer_at(value, label, minimum=minimum)


def _structural_bounds_at(value: object, label: str) -> StructuralBounds:
    """Strictly reparse `controls.structural_bounds` (Session 23); always present."""

    item = _mapping_at(value, label)

    def _range(key: str) -> StructuralBoundRange:
        sub = _mapping_at(item.get(key), f"{label}.{key}")
        return StructuralBoundRange(
            _optional_integer_at(sub.get("minimum"), f"{label}.{key}.minimum"),
            _optional_integer_at(sub.get("maximum"), f"{label}.{key}.maximum"),
        )

    qb_count = _range("qb_count")
    pass_catchers = _range("pass_catchers_with_rostered_qb")
    salary_left = _range("salary_left")
    kicker_count = _optional_integer_at(item.get("kicker_count"), f"{label}.kicker_count")
    dst_count = _optional_integer_at(item.get("dst_count"), f"{label}.dst_count")
    offense_against_own_dst = item.get("offense_against_own_dst")
    if not isinstance(offense_against_own_dst, bool):
        raise ValueError(f"{label}.offense_against_own_dst must be boolean")
    return StructuralBounds(
        qb_count, pass_catchers, salary_left, kicker_count, dst_count, offense_against_own_dst
    )


def _people_at(value: object, label: str, *, nonempty: bool = False) -> tuple[PersonBinding, ...]:
    if not isinstance(value, list) or (nonempty and not value):
        raise ValueError(f"{label} must be a{' nonempty' if nonempty else 'n'} array")
    people = []
    for index, raw in enumerate(value):
        item = _mapping_at(raw, f"{label}[{index}]")
        keys = ("underlying_id", "cpt_dk_id", "flex_dk_id")
        if set(item) != set(keys) or any(not isinstance(item[key], str) or not item[key] for key in keys):
            raise ValueError(f"{label}[{index}] must bind one person's exact CPT and FLEX IDs")
        people.append(PersonBinding(*(str(item[key]) for key in keys)))
    return tuple(people)


def _count_bounds_at(value: object, label: str, key: str) -> tuple[CountBound, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    bounds = []
    for index, raw in enumerate(value):
        item = _mapping_at(raw, f"{label}[{index}]")
        if set(item) != {key, "minimum", "maximum"} or not isinstance(item[key], str):
            raise ValueError(f"{label}[{index}] must hold {key}, minimum and maximum")
        low = _integer_at(item["minimum"], f"{label}[{index}].minimum")
        high = _integer_at(item["maximum"], f"{label}[{index}].maximum")
        if low > high or high > 6:
            raise ValueError(f"{label}[{index}] must be an ordered count from 0 through 6")
        bounds.append(CountBound(str(item[key]), low, high))
    return tuple(bounds)


def _theses_at(value: object, label: str, *, v4: bool = False) -> tuple[ShowdownThesis, ...]:
    """Strictly reparse `controls.theses`: one thesis (Session 23b, normalized_v3), or one or more with
    `row_weight`, `rows` and `effective_bounds` (Session 23c, normalized_v4).

    A v4 thesis's `rows` and `effective_bounds` are read here and checked against what the bytes imply by
    `_parse_audited_policy_controls`: the audit never trusts a number the policy merely states.
    """

    if not isinstance(value, list) or not value or (not v4 and len(value) != 1):
        raise ValueError(f"{label} must hold {'at least one thesis' if v4 else 'exactly one thesis'}")
    theses = []
    for index, raw in enumerate(value):
        where = f"{label}[{index}]"
        item = _mapping_at(raw, where)
        expected = {"name", "teams", "captain_set", "team_bounds", "position_bounds", "excluded_people",
                    "named_backup_quarterbacks", "status", "dropped_reason", "unavailable_captains"}
        if v4:
            expected = expected | {"row_weight", "rows", "effective_bounds"}
        if set(item) != expected:
            raise ValueError(f"{where} fields are not the normalized thesis fields")
        name, teams, status = item["name"], item["teams"], item["status"]
        if not isinstance(name, str) or not name or status not in {ACTIVE, DROPPED}:
            raise ValueError(f"{where} name or status is invalid")
        if not isinstance(teams, list) or not teams or any(not isinstance(team, str) for team in teams):
            raise ValueError(f"{where}.teams must be a nonempty array of team codes")
        unavailable = []
        for position, entry in enumerate(item["unavailable_captains"] if isinstance(item["unavailable_captains"], list)
                                         else [None]):
            entry = _mapping_at(entry, f"{where}.unavailable_captains[{position}]")
            if set(entry) != {"underlying_id", "source"} or not all(isinstance(entry[key], str) for key in entry):
                raise ValueError(f"{where}.unavailable_captains[{position}] is invalid")
            unavailable.append((str(entry["underlying_id"]), str(entry["source"])))
        reason = item["dropped_reason"]
        if (status == DROPPED) != isinstance(reason, str) or (reason is not None and not isinstance(reason, str)):
            raise ValueError(f"{where}.dropped_reason must be text exactly when the thesis is dropped")
        extra: dict[str, object] = {}
        if v4:
            weight = _integer_at(item["row_weight"], f"{where}.row_weight", minimum=1)
            if weight > MAX_ROW_WEIGHT:
                raise ValueError(f"{where}.row_weight must be at most {MAX_ROW_WEIGHT}")
            extra = {"row_weight": weight, "rows": _integer_at(item["rows"], f"{where}.rows"),
                     "effective_bounds": _structural_bounds_at(item["effective_bounds"], f"{where}.effective_bounds")}
        theses.append(ShowdownThesis(
            name=name, teams=tuple(teams),
            captain_set=_people_at(item["captain_set"], f"{where}.captain_set", nonempty=True),
            team_bounds=_count_bounds_at(item["team_bounds"], f"{where}.team_bounds", "team"),
            position_bounds=_count_bounds_at(item["position_bounds"], f"{where}.position_bounds", "position"),
            excluded_people=_people_at(item["excluded_people"], f"{where}.excluded_people"),
            named_backup_quarterbacks=_people_at(item["named_backup_quarterbacks"],
                                                 f"{where}.named_backup_quarterbacks"),
            status=status, dropped_reason=reason, unavailable_captains=tuple(unavailable), **extra))
    if len({item.name for item in theses}) != len(theses):
        raise ValueError(f"{label} repeats a thesis name")
    return tuple(theses)


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
    schema_version = root.get("schema_version")
    if schema_version not in NORMALIZED_POLICY_SCHEMA_VERSIONS:
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
    structural_bounds = _structural_bounds_at(controls.get("structural_bounds"), "controls.structural_bounds")
    # normalized_v3 and v4 carry theses and normalized_v2 never does (Sessions 23b and 23c).
    thesis_schema = {NORMALIZED_POLICY_SCHEMA_VERSIONS[1]: "v3", NORMALIZED_POLICY_SCHEMA_VERSIONS[2]: "v4"}.get(
        schema_version)
    if (thesis_schema is not None) != ("theses" in controls):
        raise ValueError("controls.theses must be present exactly in a normalized_v3 or normalized_v4 policy")
    theses = (_theses_at(controls["theses"], "controls.theses", v4=thesis_schema == "v4")
              if "theses" in controls else ())
    if thesis_schema == "v4":
        # A number the policy states is checked against what its own bytes imply: the allotment of the entries
        # across the active theses by weight, and each thesis's own widening of the declared bounds.
        active = [item for item in theses if item.active]
        expected_rows = (allot_rows([(item.name, int(item.row_weight)) for item in active], len(entry_ids))
                         if active else {})
        for item in theses:
            if item.rows != expected_rows.get(item.name, 0):
                raise ValueError(
                    f"thesis {item.name!r} rows {item.rows} are not the allotment {expected_rows.get(item.name, 0)}"
                    " of the entries by weight")
            expected_bounds = thesis_widened_bounds(structural_bounds, item)[0] if item.active else structural_bounds
            if item.effective_bounds != expected_bounds:
                raise ValueError(
                    f"thesis {item.name!r} effective bounds are not the declared bounds widened for its rows alone")
    return _AuditedPolicyControls(
        salary_sha256=salary_sha256,
        entry_ids=entry_ids,
        require_unique_lineups=require_unique,
        max_pairwise_person_overlap=overlap,
        person_limits=tuple(person_limits),
        structural_bounds=structural_bounds,
        theses=theses,
        thesis_schema=thesis_schema,
    )


def contest_assignment_reading(
    claim: ContestAssignmentClaim,
    artifact_pairs: Sequence[tuple[str, Sequence[str]]],
    problems: list[str],
    entry_bytes: bytes,
) -> dict[str, object]:
    """Recompute the assignment step's claims from the assignment file's rosters.

    A changed multiset or a moved filled row is a `V` problem and fails the audit.
    A reported statistic the bytes do not bear out is a `P` finding: the recomputed
    numbers replace the reported ones and the audit still passes, because the
    lineups and their rows are intact.
    """

    final = {str(entry).strip(): tuple(str(dk_id).strip() for dk_id in roster) for entry, roster in artifact_pairs}
    # A filled row's roster is read from the template's own bytes, never from the claim.
    fixed_ids = {row.entry_id for row in claim.rows if row.pool is None and row.roster is not None}
    for authorization in parse_entry_bytes(entry_bytes, source_name="audited_entry_csv").authorizations:
        if authorization.entry_id in fixed_ids and authorization.entry_id not in final:
            cells = tuple(prefilled_cell_id(cell) for cell in authorization.existing_cells)
            if all(cells):
                final[authorization.entry_id] = tuple(str(cell) for cell in cells)
    found, recomputed = claim.audit(final)
    blocking = [item for item in found if not item.startswith("CONTEST_ASSIGNMENT_STATS_MISMATCH")]
    problems.extend(_audit_problem(item.split(":", 1)[0], item.split(":", 1)[1] if ":" in item else "")
                    for item in blocking)
    return {
        "contest_assignment_version": CONTEST_ASSIGNMENT_VERSION,
        "status": "FAIL" if blocking else ("STATS_MISMATCH" if found else "PASS"),
        "findings": list(found),
        "contests": recomputed,
        "checks_run": [
            "ASSIGNED_LINEUP_MULTISET_EQUALS_THE_SELECTED_ONE_PER_POOL",
            "FILLED_ROWS_UNCHANGED",
            "PER_CONTEST_STATISTICS_RECOMPUTED_FROM_THE_ASSIGNMENT_BYTES",
        ],
    }


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
    unbound_entry_ids: Sequence[str] = (),
    unfilled_entry_ids: Sequence[str] = (),
    contest_assignment: ContestAssignmentClaim | None = None,
) -> PortfolioAudit:
    """Recompute every SD4 control from exact final roster IDs and artifacts.

    `assignments` are the policy's rows. Since Session 11b a policy may bind a
    subset of the fillable rows; the assignment artifact then also holds
    `unbound_entry_ids`, the rows the fill wrote, and must hold exactly those
    beside the policy's. Their rosters are the readable review's to check.

    `unfilled_entry_ids` (Session 39b) are unbound rows the fill named as left
    without a lineup: the artifact must hold every other unbound row and none of
    these, and a row that is neither present nor named still fails.
    """

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

    contest_reading: dict[str, object] = {}
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
        bound = set(expected_entries)
        others = [entry for entry, _roster in artifact_pairs if entry not in bound]
        if tuple(pair for pair in artifact_pairs if pair[0] in bound) != tuple(normalized_pairs):
            problems.append(
                _audit_problem(
                    "PORTFOLIO_AUDIT_ASSIGNMENT_ARTIFACT_MISMATCH",
                    "assignment rows, order, or roster IDs differ from the final in-memory assignment",
                )
            )
        unbound = [str(entry).strip() for entry in unbound_entry_ids]
        named_unfilled = [str(entry).strip() for entry in unfilled_entry_ids]
        delivered_unbound = [entry for entry in unbound if entry not in set(named_unfilled)]
        if (
            not set(named_unfilled) <= set(unbound)
            or len(set(named_unfilled)) != len(named_unfilled)
            or sorted(others) != sorted(delivered_unbound)
            or len(set(others)) != len(others)
        ):
            problems.append(
                _audit_problem(
                    "PORTFOLIO_AUDIT_ASSIGNMENT_ARTIFACT_MISMATCH",
                    f"rows outside the policy {others} are not exactly the unbound rows"
                    f" {unbound} less the named unfilled rows {named_unfilled}",
                )
            )
        if contest_assignment is not None:
            # Session 50: every claim of the contest-assignment step is recomputed
            # from these exact bytes; the optimizer's own numbers are only compared.
            contest_reading = contest_assignment_reading(
                contest_assignment, artifact_pairs, problems, entry_bytes)

    by_id = {row.dk_id: row for row in slate.players}
    canonical: list[tuple[str, str]] = []
    people_by_entry: dict[str, frozenset[str]] = {}
    combined: Counter[str] = Counter()
    captains: Counter[str] = Counter()
    structural_bounds = (
        audited_policy.structural_bounds if audited_policy is not None else policy.structural_bounds
    )
    # Session 23b: the active thesis, recomputed per roster from the reparsed bytes. Its
    # backup quarterbacks come from the depth evidence's own report (`starters_by_team`),
    # never from the selector's list of whom it excluded.
    audited_theses = audited_policy.theses if audited_policy is not None else policy.theses
    thesis_schema = audited_policy.thesis_schema if audited_policy is not None else policy.thesis_schema
    thesis = next((item for item in audited_theses if item.active), None)
    portfolio = thesis_schema == "v4" and thesis is not None
    depth_report = (selector_summary or {}).get("qb_depth_roles")
    backups, unevaluated = (
        backup_quarterbacks(slate, thesis, depth_report) if thesis is not None and not portfolio
        else (frozenset(), ()))
    thesis_entries: dict[str, list[str]] = {}
    # Session 23c (v4): every roster is recomputed against every active thesis, each with its own backup
    # rule and its own bounds. `followed_by` is every thesis a roster follows; `rules_by` what it breaks
    # under each, kept so the thesis it is claimed for can name the rules when it does not follow it.
    active_theses = [item for item in audited_theses if item.active] if portfolio else []
    thesis_backups = {item.name: backup_quarterbacks(slate, item, depth_report)[0] for item in active_theses}
    followed_by: dict[str, list[str]] = {}
    rules_by: dict[str, dict[str, tuple[str, ...]]] = {}
    for entry, roster in normalized_pairs:
        validation = validate_lineup(slate, roster)
        if not validation.valid or validation.lineup is None:
            problems.extend(
                _audit_problem("PORTFOLIO_AUDIT_LINEUP_ILLEGAL", f"entry={entry}:{detail}")
                for detail in validation.errors
            )
            continue
        # Session 23: every structural hygiene bound recomputed from the exact
        # roster IDs, never trusted from the generator's own claims. In a v4 portfolio each thesis owns the
        # bounds its rows obey (its `effective_bounds`), checked below against the thesis the row fills.
        if not portfolio:
            for violation in structural_bound_violations(slate, roster, structural_bounds):
                problems.append(
                    _audit_problem(
                        "PORTFOLIO_AUDIT_STRUCTURAL_BOUND_VIOLATED", f"entry={entry}:bound={violation}"
                    )
                )
        if portfolio:
            rules_by[entry] = {
                item.name: thesis_roster_violations(slate, roster, item, thesis_backups[item.name])
                for item in active_theses}
            followed_by[entry] = [name for name, rules in rules_by[entry].items() if not rules]
        elif thesis is not None:
            thesis_entries[entry] = list(thesis_violations(slate, roster, thesis, backups))
            problems.extend(
                _audit_problem("PORTFOLIO_AUDIT_THESIS_VIOLATED", f"entry={entry}:thesis={thesis.name}:rule={rule}")
                for rule in thesis_entries[entry])
        people = frozenset(by_id[dk_id].underlying_id for dk_id in roster)
        captain = by_id[roster[0]].underlying_id
        canonical.append((entry, validation.lineup.canonical_key))
        people_by_entry[entry] = people
        combined.update(people)
        captains[captain] += 1
    portfolio_report: dict[str, object] = {}
    if portfolio:
        portfolio_report = _audit_thesis_portfolio(
            slate, normalized_pairs, canonical, active_theses, followed_by, rules_by, selector_summary,
            audited_theses, thesis_backups, depth_report, problems)

    if audited_policy is not None:
        limits = {
            person: (combined_limit, captain_limit)
            for person, combined_limit, captain_limit in audited_policy.person_limits
        }
        overlap_limit = audited_policy.max_pairwise_person_overlap
    else:
        limits = {
            item.person.underlying_id: (
                item.combined_max_entries,
                item.captain_max_entries,
            )
            for item in policy.effective_limits
        }
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
    # R29: unconditional. A stored `require_unique_lineups: false` from before
    # Session 37 no longer switches the duplicate check off.
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

    # `max_person_share`: the portfolio-wide share cap Sessions 23b and 23c
    # reuse (docs/RUNBOOK.md, R34). Not a second gate: it is exactly the
    # already-audited combined-person maximum, reported with the person(s)
    # named for the review.
    denominator = len(people_by_entry)
    top_combined = max(combined.values(), default=0)
    max_person_share = {
        "share_percentage": round(100 * top_combined / denominator, 3) if denominator else 0.0,
        "entries": denominator,
        "people": sorted(person for person, count in combined.items() if count == top_combined),
    }
    return PortfolioAudit(
        problems=tuple(problems),
        entry_ids=actual_entries,
        canonical_lineups=tuple(canonical),
        combined_person_counts=tuple(sorted(combined.items())),
        captain_counts=tuple(sorted(captains.items())),
        pairwise_person_overlap=tuple(overlaps),
        hashes=tuple(sorted(actual_hashes.items())),
        max_person_share=max_person_share,
        contest_assignment=contest_reading,
        theses=portfolio_report or _audited_theses_report(audited_theses, thesis_entries, backups, unevaluated),
    )


def _quota_assignment(followed: Mapping[str, Sequence[str]], rows: Mapping[str, int]) -> dict[str, str] | None:
    """One way to give each entry a thesis it follows with every thesis holding exactly its allotment, or None.

    A bipartite assignment by augmenting paths over entries and thesis slots: small (entries by theses),
    exact, and independent of whatever the selector claimed.
    """

    slots = [name for name, count in rows.items() for _ in range(count)]
    entries = list(followed)
    if len(entries) != len(slots):
        return None
    owner: dict[int, int] = {}

    def augment(entry_index: int, seen: set[int]) -> bool:
        for slot_index, name in enumerate(slots):
            if slot_index in seen or name not in followed[entries[entry_index]]:
                continue
            seen.add(slot_index)
            if slot_index not in owner or augment(owner[slot_index], seen):
                owner[slot_index] = entry_index
                return True
        return False

    if not all(augment(index, set()) for index in range(len(entries))):
        return None
    return {entries[entry_index]: slots[slot_index] for slot_index, entry_index in owner.items()}


def _audit_thesis_portfolio(
    slate: SlateContract,
    pairs: Sequence[tuple[str, tuple[str, ...]]],
    canonical: Sequence[tuple[str, str]],
    active: Sequence[ShowdownThesis],
    followed_by: Mapping[str, Sequence[str]],
    rules_by: Mapping[str, Mapping[str, tuple[str, ...]]],
    selector_summary: Mapping[str, object] | None,
    all_theses: Sequence[ShowdownThesis],
    backups_by_thesis: Mapping[str, frozenset[str]],
    depth_report: object,
    problems: list[str],
) -> dict[str, object]:
    """The v4 thesis checks and the report (Session 23c).

    Each Entry ID's thesis is read from the selector's claim, keyed by canonical lineup (so it survives the
    contest step moving lineups between Entry IDs), and must be an active thesis the roster follows under that
    thesis's own rules, bounds and backup rule; each thesis must hold exactly its allotment; and an assignment
    that meets every quota must exist whatever the claim says. With no claim the audit derives one.
    """

    names = {item.name for item in active}
    rows = {item.name: item.rows for item in active}
    claims = None
    if selector_summary is not None:
        block = (selector_summary.get("portfolio_policy") or {}).get("theses")
        if isinstance(block, Mapping) and isinstance(block.get("by_lineup"), Mapping):
            claims = block["by_lineup"]
    key_of = dict(canonical)
    roster_of = dict(pairs)
    assigned: dict[str, str | None] = {}
    broken: dict[str, list[str]] = {}
    for entry, followed in followed_by.items():
        if claims is not None:
            claimed = claims.get(key_of.get(entry, ""))
            if claimed not in names:
                problems.append(_audit_problem(
                    "PORTFOLIO_AUDIT_THESIS_CLAIM_INVALID", f"entry={entry}:claimed={claimed!r}"))
                assigned[entry] = None
                continue
            assigned[entry] = claimed
            if claimed not in followed:
                broken[entry] = list(rules_by[entry][claimed])
                problems.extend(
                    _audit_problem("PORTFOLIO_AUDIT_THESIS_VIOLATED", f"entry={entry}:thesis={claimed}:rule={rule}")
                    for rule in broken[entry])
    witness = _quota_assignment(followed_by, rows)
    if claims is None:
        # No claim to check: the matching's own assignment is the report, and a roster that follows no
        # thesis is named.
        assigned = dict(witness) if witness is not None else {entry: None for entry in followed_by}
        problems.extend(
            _audit_problem("PORTFOLIO_AUDIT_THESIS_VIOLATED", f"entry={entry}:thesis=NONE:rule=no_thesis_followed")
            for entry, followed in followed_by.items() if not followed)
    claimed_rows = Counter(name for name in assigned.values() if name is not None)
    if claims is not None:
        for name in sorted(rows):
            if claimed_rows.get(name, 0) != rows[name]:
                problems.append(_audit_problem(
                    "PORTFOLIO_AUDIT_THESIS_ROWS_MISMATCH",
                    f"thesis={name}:actual={claimed_rows.get(name, 0)}:rows={rows[name]}"))
    if witness is None:
        problems.append(_audit_problem(
            "PORTFOLIO_AUDIT_THESIS_ROWS_MISMATCH",
            "no assignment of lineups to theses gives every thesis exactly its allotment"))
    measures = thesis_portfolio_measures(
        slate, [(entry, roster_of[entry], assigned.get(entry)) for entry in followed_by],
        allotment={item.name: item.rows for item in all_theses}, followed=followed_by, broken=broken)
    admitted = frozenset().union(*(admitted_quarterbacks(slate, item) for item in active)) if active else frozenset()
    global_backups, unevaluated = backup_quarterbacks(slate, None, depth_report, admitted_people=admitted)
    return {
        "build_version": THESIS_PORTFOLIO_VERSION,
        "theses": [{"name": item.name, "status": item.status, "dropped_reason": item.dropped_reason,
                    "row_weight": item.row_weight, "rows": item.rows} for item in all_theses],
        "entries": measures["entries"],
        "measures": {key: value for key, value in measures.items() if key != "entries"},
        "backup_quarterbacks_excluded": sorted(global_backups),
        "backup_quarterbacks_unevaluated_teams": list(unevaluated),
        "assignment_source": "SELECTOR_CLAIM_RECOMPUTED" if claims is not None else "DERIVED_BY_THE_AUDIT",
    }


def _audited_theses_report(
    theses: Sequence[ShowdownThesis],
    entries: Mapping[str, Sequence[str]],
    backups: frozenset[str],
    unevaluated: Sequence[str],
) -> dict[str, object]:
    """Each audited row's thesis and whether its roster follows it (empty without a thesis)."""

    if not theses:
        return {}
    active = next((item for item in theses if item.active), None)
    return {
        "build_version": THESIS_BUILD_VERSION,
        "theses": [{"name": item.name, "status": item.status, "dropped_reason": item.dropped_reason}
                   for item in theses],
        "entries": {entry: {"thesis": active.name if active else None,
                            "follows": not broken, "broken_rules": list(broken)}
                    for entry, broken in entries.items()},
        "backup_quarterbacks_excluded": sorted(backups),
        "backup_quarterbacks_unevaluated_teams": list(unevaluated),
    }
