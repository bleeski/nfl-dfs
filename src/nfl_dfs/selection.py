"""Prior-only NFL lineup selection for Showdown and Classic.

R02, selection side. This is the step that turns a frozen prior package into
assignments, and it is deliberately narrow: it calls the MILP in `optimizer.py`
against the prior score in `prior_score.py`, over the pool the participation
contract permits. It never imports `field.py`, `economics.py` or the portfolio
objective, because those carry the R05, R06 and R07 defects and a prior-only
profile must not touch them.

Two consequences the caller has to carry forward. The objective maximizes a
central estimate, so the first lineup is close to the chalkiest legal lineup;
there is no ownership model here and therefore no leverage. And a portfolio of
more than one entry is differentiated structurally, by forbidding a repeat
captain, which is uniqueness rather than a claim about correlated equity.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence

from .contracts import EngineMode, SlateContract
from .classic_portfolio import (
    ENFORCEMENT_VERSION as CLASSIC_ENFORCEMENT_VERSION,
    build_classic_candidate_bank,
    candidate_bank_bytes,
    solve_classic_portfolio,
)
from .classic_portfolio_policy import NormalizedClassicPortfolioPolicy
from .hashing import sha256_bytes
from .kicker_roles import resolve_kicker_roles
from .lineups import roster_canonical_key, validate_lineup
from .opportunity import OpportunityModel
from .offensive_roles import resolve_offensive_roles, verify_offensive_resolution
from .qb_depth_roles import resolve_qb_depth_roles, verify_qb_depth_resolution
from .optimizer import LineupOptimizer
from .participation import ParticipationContract, excluded_dk_ids, selectable_pool_problems
from .portfolio_enforcement import (
    DEFAULT_CANDIDATE_PER_SOLVE_SECONDS,
    ENFORCEMENT_VERSION,
    build_policy_candidate_bank,
    scaled_candidate_limit,
    scaled_candidate_seconds,
    scaled_selection_seconds,
    solve_policy_portfolio,
)
from .portfolio_policy import NormalizedPortfolioPolicy
from .prior_score import PriorScores, TeamSplits, score_pool


PROFILE_VERSION = "prior_only_showdown_selection_v1"
CLASSIC_PROFILE_VERSION = "prior_only_classic_selection_c1_v1"


class SelectionError(ValueError):
    """A named fail-closed selection error.

    `status` and `facts` (Session 10) carry the failure structured, so the
    relaxation controller reads the status a bank or joint solve reported
    instead of parsing the message.
    """

    def __init__(self, message: str, *, status: str | None = None,
                 facts: Mapping[str, object] | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.facts = dict(facts or {})

    def as_report(self, *, error: str) -> dict[str, object]:
        return {"status": self.status, "origin": "SELECTION", "facts": dict(self.facts), "error": error}


@dataclass(frozen=True)
class SelectedLineup:
    index: int
    roster: tuple[str, ...]
    captain_dk_id: str
    salary: int
    prior_points: float
    canonical_key: str
    solver_status: str
    solver_seconds: float

    def as_payload(self, names: Mapping[str, str]) -> dict[str, object]:
        return {
            "index": self.index,
            "roster": list(self.roster),
            "captain": (
                names.get(self.captain_dk_id, self.captain_dk_id)
                if self.captain_dk_id
                else None
            ),
            "captain_dk_id": self.captain_dk_id or None,
            "salary": self.salary,
            "salary_remaining": 50_000 - self.salary,
            "prior_points": round(self.prior_points, 3),
            "canonical_key": self.canonical_key,
            "solver_status": self.solver_status,
            "solver_seconds": round(self.solver_seconds, 3),
            "players": [names.get(dk_id, dk_id) for dk_id in self.roster],
        }


POOL_SCORES_SCHEMA = "nfl_prior_pool_scores_v1"

# Environment fallback for the two entry points that cannot yet take a keyword:
# `cowork-run --profile prior_review` and the `select` subcommand both reach
# selection through fixed request plumbing. Backlog P1-4 replaces this whole
# function with a first-class, hash-bound artifact emitted by the engine and
# removes both the variable and the parameter; until then this is the documented
# way to get the gated scores out, and `scripts/build_classic_portfolio.py`
# consumes exactly this schema.
POOL_SCORES_PATH_ENV = "NFL_DFS_DUMP_SCORES"


def resolve_pool_scores_path(explicit: str | Path | None) -> Path | None:
    """Where to write the scored pool, or None when nobody asked for it."""

    raw = explicit if explicit is not None else os.environ.get(POOL_SCORES_PATH_ENV) or None
    if raw is None:
        return None
    path = Path(raw).expanduser()
    if path.is_dir():
        raise SelectionError(f"POOL_SCORES_PATH_IS_A_DIRECTORY:{path}")
    parent = path.parent if str(path.parent) else Path(".")
    if not parent.is_dir():
        raise SelectionError(f"POOL_SCORES_PARENT_MISSING:{parent}")
    return path


def write_pool_scores(scores: PriorScores, path: str | Path) -> Path:
    """Write the gated per-player scores as a schema-versioned JSON document.

    This is a diagnostic export, not a release artifact: it binds no hashes and
    carries no evidence decision, so nothing downstream may treat its presence
    as authorization. It exists because on 2026-09-13 the engine's own scores
    were the one artifact that reached the shipped portfolio, and they left
    through an unnamed environment variable read in the middle of the scoring
    path.
    """

    target = Path(path).expanduser()
    payload = {
        "schema_version": POOL_SCORES_SCHEMA,
        "score_version": scores.score_version,
        "status": "DIAGNOSTIC_NOT_AN_UPLOAD_AUTHORIZATION",
        "by_dk_id": dict(sorted(scores.by_dk_id.items())),
        "by_person": dict(sorted(scores.by_person.items())),
        "threshold_sensitive": sorted(scores.threshold_sensitive),
        "omissions": sorted(scores.omissions),
    }
    target.write_text(
        json.dumps(payload, indent=2, sort_keys=False, default=str), encoding="utf-8"
    )
    return target


def select_prior_lineups(
    slate: SlateContract,
    model: OpportunityModel,
    splits: Mapping[str, TeamSplits],
    contract: ParticipationContract,
    *,
    count: int,
    differentiate_captain: bool = True,
    max_person_overlap: int | None = 4,
    time_limit_seconds: float = 10.0,
    role_evidence_json: str | Path | None = None,
    offensive_role_evidence_json: str | Path | None = None,
    qb_depth_role_evidence_json: str | Path | None = None,
    as_of: datetime | None = None,
    portfolio_policy: NormalizedPortfolioPolicy | NormalizedClassicPortfolioPolicy | None = None,
    policy_candidate_limit: int | None = None,
    policy_candidate_seconds: float | None = None,
    policy_candidate_per_solve_seconds: float = DEFAULT_CANDIDATE_PER_SOLVE_SECONDS,
    policy_selection_seconds: float | None = None,
    pool_scores_path: str | Path | None = None,
    forbidden_rosters: Sequence[tuple[str, ...]] = (),
    fill_count: int = 0,
    fill_time_limit_seconds: float | None = None,
) -> tuple[tuple[SelectedLineup, ...], PriorScores, dict[str, object]]:
    """Solve for `count` distinct legal lineups over the permitted pool.

    The `policy_*` bounds default to `None`, meaning "scale with the policy's
    entry count" (`max(32, 4 * entries)` candidates, `max(30s, 2s * entries)`
    of bank generation, `max(10s, 1s * entries)` for the joint solve). An
    explicit value is used as given, so tests and diagnostics can pin small
    bounds. `forbidden_rosters` (Session 11) are the entry template's prefilled
    rosters: C1 and sequential Showdown cut each from every solve, and the C2
    and SD3 banks never hold one, so no selected lineup repeats one (R29).

    `fill_count` (Session 11b) is the fillable rows a subset SD3 policy leaves
    unbound (a C2 subset is Session 11c's). After the joint solve, sequential
    Showdown fills them: every policy lineup and every forbidden roster is a no-good, and only
    the run's own exclusions apply (request, status, official, role), never the
    policy's. The fill's lineups follow the policy's in the returned tuple and
    its report is the policy report's `unbound_fill`; a fill that runs out of
    distinct lineups raises, and nothing is returned (all or nothing).
    """

    if slate.mode not in {EngineMode.SHOWDOWN, EngineMode.CLASSIC}:
        raise SelectionError(f"MODE_NOT_SUPPORTED:{slate.mode.value}")
    forbidden_rosters = tuple(tuple(map(str, roster)) for roster in forbidden_rosters)
    forbidden_keys = {roster_canonical_key(slate, roster) for roster in forbidden_rosters}
    if count < 1:
        raise SelectionError(f"LINEUP_COUNT_INVALID:{count}")
    if portfolio_policy is not None and count != portfolio_policy.entry_count:
        raise SelectionError(
            "PORTFOLIO_POLICY_ENTRY_COUNT_MISMATCH:"
            f"count={count}:policy_entries={portfolio_policy.entry_count}"
        )
    if fill_count < 0 or (fill_count and portfolio_policy is None):
        raise SelectionError(
            "PORTFOLIO_POLICY_ENTRY_COUNT_MISMATCH:"
            f"fill_count={fill_count}:an unbound fill needs a subset policy"
        )
    if fill_count and isinstance(portfolio_policy, NormalizedClassicPortfolioPolicy):
        raise SelectionError(
            "CLASSIC_POLICY_SUBSET_UNSUPPORTED:a C2 policy binding a subset of the fillable rows is"
            " Session 11c's (C3's package is bound to the C2 bank); bind every fillable row or omit"
            " the policy"
        )
    if (
        isinstance(portfolio_policy, NormalizedPortfolioPolicy)
        and slate.mode is not EngineMode.SHOWDOWN
    ):
        raise SelectionError(
            "PORTFOLIO_POLICY_MODE_UNSUPPORTED_C1:Classic policy, candidate-bank, "
            "and joint portfolio selection belong to C2"
        )
    if (
        isinstance(portfolio_policy, NormalizedClassicPortfolioPolicy)
        and slate.mode is not EngineMode.CLASSIC
    ):
        raise SelectionError(
            "CLASSIC_PORTFOLIO_POLICY_MODE_MISMATCH:Classic C2 policy requires Classic"
        )
    problems = selectable_pool_problems(slate, contract)
    if problems:
        raise SelectionError("SELECTABLE_POOL_INFEASIBLE:" + ";".join(problems))

    kicker_roles = resolve_kicker_roles(
        slate,
        contract,
        evidence_path=role_evidence_json,
        as_of=as_of,
    )
    # The depth chart moves quarterback attempts onto the named starter before
    # anything reads a share, so a backup cannot carry his prior-season split
    # into the projection and then be removed by a policy exclusion that lands
    # after scoring. It touches `qb_attempt_share` and nothing else.
    qb_depth = resolve_qb_depth_roles(
        slate, model, contract, evidence_path=qb_depth_role_evidence_json, as_of=as_of,
    )
    offense = resolve_offensive_roles(
        slate,
        qb_depth.model,
        contract,
        evidence_path=offensive_role_evidence_json,
        as_of=as_of,
    )
    scores = score_pool(slate, offense.model, splits, kicker_roles=kicker_roles, offensive_roles=offense)
    # Scoring may leave out an unresolved role change (R28); its resolution is
    # the one every exclusion and report below reads.
    offense = scores.offensive_role_resolution
    pool_scores_target = resolve_pool_scores_path(pool_scores_path)
    if pool_scores_target is not None:
        write_pool_scores(scores, pool_scores_target)
    zero_share_people = set(kicker_roles.zero_share_people)
    excluded_set = (
            sorted(
                set(excluded_dk_ids(slate, contract))
                | {
                player.dk_id
                for player in slate.players
                    if player.underlying_id in zero_share_people or player.underlying_id in offense.excluded_people
                }
            )
    )
    # The run's own exclusions bind every row; a policy's own exclusions and zero
    # caps (below) bind only the rows it binds, so the unbound fill uses these.
    run_excluded = tuple(sorted(set(excluded_set)))
    if isinstance(portfolio_policy, NormalizedPortfolioPolicy):
        for limit in portfolio_policy.effective_limits:
            if limit.combined_max_entries == 0:
                excluded_set.extend((limit.person.cpt_dk_id, limit.person.flex_dk_id))
    elif isinstance(portfolio_policy, NormalizedClassicPortfolioPolicy):
        by_person = {player.underlying_id: player for player in slate.players}
        for limit in portfolio_policy.player_bounds:
            if limit.maximum_entries == 0:
                excluded_set.append(by_person[limit.entity_id].dk_id)
    excluded = tuple(sorted(set(excluded_set)))
    objective = _objective(slate, scores, excluded)

    def fill(policy_lineups: list[SelectedLineup]) -> tuple[list[SelectedLineup], dict[str, object]]:
        return _fill_unbound(
            slate, _objective(slate, scores, run_excluded), run_excluded, contract,
            policy_lineups=policy_lineups, forbidden_rosters=forbidden_rosters, count=fill_count,
            differentiate_captain=differentiate_captain, max_person_overlap=max_person_overlap,
            time_limit_seconds=(time_limit_seconds if fill_time_limit_seconds is None
                                else fill_time_limit_seconds),
        )

    by_id = {player.dk_id: player for player in slate.players}
    selected: list[SelectedLineup] = []
    if isinstance(portfolio_policy, NormalizedClassicPortfolioPolicy):
        bank = build_classic_candidate_bank(
            slate,
            objective,
            portfolio_policy,
            excluded_ids=excluded,
            forbidden_rosters=forbidden_rosters,
        )
        if bank.blocking:
            raise SelectionError(
                f"{bank.status}:model_status={bank.terminal_model_status}:"
                f"candidates={len(bank.candidates)}:requested={bank.requested_candidates}",
                status=bank.status,
                facts={"stage": "CANDIDATE_BANK", "candidates": len(bank.candidates),
                       "requested_candidates": bank.requested_candidates,
                       "model_status": bank.terminal_model_status, "exhaustive": bank.exhaustive,
                       "elapsed_seconds": round(bank.elapsed_seconds, 3)},
            )
        portfolio_solve = solve_classic_portfolio(portfolio_policy, bank)
        if not portfolio_solve.passed:
            raise SelectionError(
                f"{portfolio_solve.status}:model_status={portfolio_solve.model_status}:"
                f"candidate_bank={len(bank.candidates)}:scope={portfolio_solve.infeasibility_scope}",
                status=portfolio_solve.status,
                facts={"stage": "JOINT_SELECTION", "candidates": len(bank.candidates),
                       "requested_candidates": bank.requested_candidates,
                       "model_status": portfolio_solve.model_status, "exhaustive": bank.exhaustive,
                       "scope": portfolio_solve.infeasibility_scope},
            )
        for index, candidate_index in enumerate(
            portfolio_solve.selected_candidate_indexes, start=1
        ):
            candidate = bank.candidates[candidate_index]
            validation = validate_lineup(slate, candidate.roster)
            if validation.lineup is None:
                raise SelectionError(
                    f"CLASSIC_PORTFOLIO_SOLVER_PRODUCED_ILLEGAL_LINEUP:index={index}:"
                    f"{validation.errors}"
                )
            selected.append(
                SelectedLineup(
                    index=index,
                    roster=candidate.roster,
                    captain_dk_id="",
                    salary=validation.lineup.salary,
                    prior_points=candidate.prior_points,
                    canonical_key=validation.lineup.canonical_key,
                    solver_status=portfolio_solve.status,
                    solver_seconds=portfolio_solve.elapsed_seconds,
                )
            )
        exposure: Counter[str] = Counter()
        team_exposure: Counter[str] = Counter()
        game_exposure: Counter[str] = Counter()
        people_by_lineup: list[frozenset[str]] = []
        for lineup in selected:
            rows = [by_id[dk_id] for dk_id in lineup.roster]
            people = frozenset(row.underlying_id for row in rows)
            people_by_lineup.append(people)
            exposure.update(people)
            team_exposure.update({row.team for row in rows})
            game_exposure.update({row.game_id for row in rows})
        overlaps = [
            {
                "entry_id_a": portfolio_policy.entry_ids[left],
                "entry_id_b": portfolio_policy.entry_ids[right],
                "people": len(people_by_lineup[left] & people_by_lineup[right]),
            }
            for left in range(len(selected))
            for right in range(left + 1, len(selected))
        ]
        bank_raw = candidate_bank_bytes(portfolio_policy, bank)
        report = {
            "profile_version": "prior_only_classic_selection_c2_v1",
            "mode": slate.mode.value,
            "score_version": scores.score_version,
            "objective": "MAXIMIZE_PRIOR_POINTS_OF_THE_EXPECTED_STAT_LINE",
            "objective_version": portfolio_policy.objective_version,
            "objective_limits": [
                "CENTRAL_ESTIMATE_NOT_A_CEILING",
                "NO_OWNERSHIP_LEVERAGE_OR_DUPLICATION_TERM",
                "NO_FIELD_OR_PAYOUT_ECONOMICS_CONSULTED",
                # A limit incumbent is never called optimal (Session 08).
                "OPTIMAL_ONLY_OVER_ACTUAL_CANDIDATE_BANK"
                if portfolio_solve.proven_optimal
                else "LIMIT_INCUMBENT_NOT_PROVEN_OPTIMAL_OVER_ACTUAL_CANDIDATE_BANK",
            ],
            "lineups": len(selected),
            "selected_lineup_count": len(selected),
            "excluded_rows": len(excluded),
            "kicker_role_excluded_people": sorted(zero_share_people),
            "kicker_roles": kicker_roles.as_report(),
            "offensive_roles": offense.report,
            "qb_depth_roles": qb_depth.report,
            "salary_rank_divergence": scores.as_report()["salary_rank_divergence"],
            "selectable_people": len(contract.selectable_people),
            "person_exposure": dict(sorted(exposure.items())),
            "team_exposure": dict(sorted(team_exposure.items())),
            "game_exposure": dict(sorted(game_exposure.items())),
            "pairwise_person_overlap": overlaps,
            "threshold_sensitive": list(scores.threshold_sensitive),
            "score_omissions": list(scores.omissions),
            "portfolio_policy": {
                "enforcement_version": CLASSIC_ENFORCEMENT_VERSION,
                "enforcement_status": "PASS",
                "normalized_policy_sha256": portfolio_policy.normalized_sha256,
                "entry_ids": list(portfolio_policy.entry_ids),
                "candidate_bank": bank.as_report(),
                "candidate_bank_artifact": json.loads(bank_raw.decode("utf-8")),
                "candidate_bank_canonical_json": bank_raw.decode("utf-8"),
                "candidate_bank_sha256": sha256_bytes(bank_raw),
                "solve": portfolio_solve.as_report(),
            },
            "never_calls": [
                "field.py",
                "ownership.py",
                "economics.py",
                "portfolio.py",
                "review_export.py",
                "readable_review.py",
            ],
        }
        verify_offensive_resolution(offense, at=as_of or datetime.now(timezone.utc))
        verify_qb_depth_resolution(qb_depth, at=as_of or datetime.now(timezone.utc))
        _refuse_prefilled_repeats(selected, forbidden_keys)
        return tuple(selected), scores, report

    if isinstance(portfolio_policy, NormalizedPortfolioPolicy):
        entry_count = portfolio_policy.entry_count
        candidate_limit = (
            scaled_candidate_limit(entry_count)
            if policy_candidate_limit is None
            else policy_candidate_limit
        )
        candidate_seconds = (
            scaled_candidate_seconds(entry_count)
            if policy_candidate_seconds is None
            else policy_candidate_seconds
        )
        selection_seconds = (
            scaled_selection_seconds(entry_count)
            if policy_selection_seconds is None
            else policy_selection_seconds
        )
        bank = build_policy_candidate_bank(
            slate,
            objective,
            excluded_ids=excluded,
            candidate_limit=candidate_limit,
            total_time_limit_seconds=candidate_seconds,
            per_solve_time_limit_seconds=policy_candidate_per_solve_seconds,
            policy=portfolio_policy,
            forbidden_rosters=forbidden_rosters,
        )
        if bank.blocking:
            raise SelectionError(
                f"{bank.status}:model_status={bank.terminal_model_status}:"
                f"candidates={len(bank.candidates)}:budget={bank.total_time_limit_seconds}",
                status=bank.status,
                facts={"stage": "CANDIDATE_BANK", "candidates": len(bank.candidates),
                       "requested_candidates": bank.candidate_limit,
                       "model_status": bank.terminal_model_status, "complete": bank.complete,
                       "budget_seconds": bank.total_time_limit_seconds},
            )
        portfolio_solve = solve_policy_portfolio(
            portfolio_policy,
            bank,
            time_limit_seconds=selection_seconds,
        )
        if not portfolio_solve.passed:
            raise SelectionError(
                f"{portfolio_solve.status}:model_status={portfolio_solve.model_status}:"
                f"candidate_bank={len(bank.candidates)}:complete={bank.complete}",
                status=portfolio_solve.status,
                facts={"stage": "JOINT_SELECTION", "candidates": len(bank.candidates),
                       "requested_candidates": bank.candidate_limit,
                       "model_status": portfolio_solve.model_status, "complete": bank.complete},
            )
        for index, candidate_index in enumerate(
            portfolio_solve.selected_candidate_indexes, start=1
        ):
            candidate = bank.candidates[candidate_index]
            validation = validate_lineup(slate, candidate.roster)
            if validation.lineup is None:
                raise SelectionError(
                    f"PORTFOLIO_SOLVER_PRODUCED_ILLEGAL_LINEUP:index={index}:"
                    f"{validation.errors}"
                )
            selected.append(
                SelectedLineup(
                    index=index,
                    roster=candidate.roster,
                    captain_dk_id=candidate.roster[0],
                    salary=validation.lineup.salary,
                    prior_points=candidate.prior_points,
                    canonical_key=validation.lineup.canonical_key,
                    solver_status=portfolio_solve.status,
                    solver_seconds=portfolio_solve.elapsed_seconds,
                )
            )
        exposure: dict[str, int] = {}
        captain_exposure: dict[str, int] = {}
        people_by_lineup: list[frozenset[str]] = []
        for lineup in selected:
            people = frozenset(by_id[dk_id].underlying_id for dk_id in lineup.roster)
            people_by_lineup.append(people)
            for person in people:
                exposure[person] = exposure.get(person, 0) + 1
            captain = by_id[lineup.captain_dk_id].underlying_id
            captain_exposure[captain] = captain_exposure.get(captain, 0) + 1
        overlaps = [
            {
                "entry_id_a": portfolio_policy.entry_ids[left],
                "entry_id_b": portfolio_policy.entry_ids[right],
                "people": len(people_by_lineup[left] & people_by_lineup[right]),
            }
            for left in range(len(selected))
            for right in range(left + 1, len(selected))
        ]
        report = {
            "profile_version": PROFILE_VERSION,
            "score_version": scores.score_version,
            "objective": "MAXIMIZE_PRIOR_POINTS_OF_THE_EXPECTED_STAT_LINE",
            "objective_limits": [
                "CENTRAL_ESTIMATE_NOT_A_CEILING",
                "NO_OWNERSHIP_LEVERAGE_OR_DUPLICATION_TERM",
                "NO_FIELD_OR_PAYOUT_ECONOMICS_CONSULTED",
            ],
            "differentiation": {
                "captain": "EXPLICIT_POLICY_MAXIMUM",
                "max_person_overlap": portfolio_policy.effective_pairwise_person_overlap,
                "basis": "EXACT_NORMALIZED_USER_POLICY_NOT_A_CORRELATED_EQUITY_CLAIM",
            },
            "lineups": len(selected),
            "selected_lineup_count": len(selected),
            "excluded_rows": len(excluded),
            "kicker_role_excluded_people": sorted(zero_share_people),
            "kicker_roles": kicker_roles.as_report(),
            "offensive_roles": offense.report,
            "qb_depth_roles": qb_depth.report,
            "salary_rank_divergence": scores.as_report()["salary_rank_divergence"],
            "selectable_people": len(contract.selectable_people),
            "person_exposure": dict(sorted(exposure.items())),
            "captain_exposure": dict(sorted(captain_exposure.items())),
            "pairwise_person_overlap": overlaps,
            "forbidden_captain_rows": [],
            "threshold_sensitive": list(scores.threshold_sensitive),
            "score_omissions": list(scores.omissions),
            "portfolio_policy": {
                "enforcement_version": ENFORCEMENT_VERSION,
                "enforcement_status": "PASS",
                "normalized_policy_sha256": portfolio_policy.normalized_sha256,
                "entry_ids": list(portfolio_policy.entry_ids),
                "candidate_bank": bank.as_report(),
                "solve": portfolio_solve.as_report(),
            },
            "never_calls": ["field.py", "economics.py", "portfolio economics"],
        }
        if fill_count:
            selected, report["unbound_fill"] = fill(selected)
        verify_offensive_resolution(offense, at=as_of or datetime.now(timezone.utc))
        verify_qb_depth_resolution(qb_depth, at=as_of or datetime.now(timezone.utc))
        _refuse_prefilled_repeats(selected, forbidden_keys)
        return tuple(selected), scores, report

    selection_profile_version = (
        PROFILE_VERSION
        if slate.mode is EngineMode.SHOWDOWN
        else CLASSIC_PROFILE_VERSION
    )
    run = _sequential_lineups(
        slate, objective, excluded, contract, count=count, first_index=1,
        forbidden_rosters=forbidden_rosters, differentiate_captain=differentiate_captain,
        max_person_overlap=max_person_overlap, time_limit_seconds=time_limit_seconds,
    )
    selected = run.selected
    report = {
        "profile_version": selection_profile_version,
        "mode": slate.mode.value,
        "score_version": scores.score_version,
        "objective": "MAXIMIZE_PRIOR_POINTS_OF_THE_EXPECTED_STAT_LINE",
        "objective_limits": [
            "CENTRAL_ESTIMATE_NOT_A_CEILING",
            "NO_OWNERSHIP_LEVERAGE_OR_DUPLICATION_TERM",
            "NO_FIELD_OR_PAYOUT_ECONOMICS_CONSULTED",
        ],
        "differentiation": run.differentiation(slate),
        "lineups": len(selected),
        "excluded_rows": len(excluded),
        "kicker_role_excluded_people": sorted(zero_share_people),
        "kicker_roles": kicker_roles.as_report(),
        "offensive_roles": offense.report,
        "qb_depth_roles": qb_depth.report,
        "salary_rank_divergence": scores.as_report()["salary_rank_divergence"],
        "selectable_people": len(contract.selectable_people),
        "person_exposure": run.person_exposure(slate),
        "forbidden_captain_rows": run.forbidden_captains,
        "non_optimal_lineups": [
            lineup.index for lineup in selected if lineup.solver_status != "OPTIMAL"
        ],
        "threshold_sensitive": list(scores.threshold_sensitive),
        "score_omissions": list(scores.omissions),
        "never_calls": ["field.py", "economics.py", "portfolio economics"],
    }
    verify_offensive_resolution(offense, at=as_of or datetime.now(timezone.utc))
    verify_qb_depth_resolution(qb_depth, at=as_of or datetime.now(timezone.utc))
    _refuse_prefilled_repeats(selected, forbidden_keys)
    return tuple(selected), scores, report


@dataclass
class _Sequential:
    """One run of sequential selection: C1, or Showdown's captain-differentiated chain."""

    selected: list[SelectedLineup]
    forbidden_captains: list[str]
    captain_repeats_from_index: int | None
    differentiate_captain: bool
    effective_overlap: int | None

    def differentiation(self, slate: SlateContract) -> dict[str, object]:
        by_id = {player.dk_id: player for player in slate.players}
        return {
            "captain": (
                "NOT_APPLICABLE_CLASSIC"
                if slate.mode is EngineMode.CLASSIC
                else (
                    "DISTINCT_UNTIL_POOL_EXHAUSTED_THEN_REPEATED"
                    if self.captain_repeats_from_index is not None
                    else (
                        "DISTINCT_PER_ENTRY"
                        if self.differentiate_captain
                        else "UNCONSTRAINED"
                    )
                )
            ),
            "captain_repeats_from_index": self.captain_repeats_from_index,
            "captain_exposure": dict(
                sorted(
                    Counter(
                        by_id[lineup.captain_dk_id].underlying_id
                        for lineup in self.selected
                        if lineup.captain_dk_id
                    ).items(),
                    key=lambda item: (-item[1], item[0]),
                )
            ),
            "max_person_overlap": self.effective_overlap,
            "basis": (
                "SEQUENTIAL_EXACT_LINEUP_NO_GOODS_ONLY_C1_NOT_A_PORTFOLIO_POLICY"
                if slate.mode is EngineMode.CLASSIC
                else "STRUCTURAL_UNIQUENESS_NOT_A_CORRELATED_EQUITY_CLAIM"
            ),
        }

    def person_exposure(self, slate: SlateContract) -> dict[str, int]:
        by_id = {player.dk_id: player for player in slate.players}
        exposure: dict[str, int] = {}
        for lineup in self.selected:
            for dk_id in lineup.roster:
                person = by_id[dk_id].underlying_id
                exposure[person] = exposure.get(person, 0) + 1
        return dict(sorted(exposure.items(), key=lambda item: (-item[1], item[0])))


def _sequential_lineups(
    slate: SlateContract,
    objective: Mapping[str, float],
    excluded: Sequence[str],
    contract: ParticipationContract,
    *,
    count: int,
    first_index: int,
    forbidden_rosters: Sequence[tuple[str, ...]],
    differentiate_captain: bool,
    max_person_overlap: int | None,
    time_limit_seconds: float,
    stage: str = "SEQUENTIAL",
) -> _Sequential:
    """`count` distinct lineups, one solve each, none equal to a forbidden roster.

    C1 (Classic) and sequential Showdown, and since Session 11b the fill of the
    rows a subset policy leaves unbound. Lineups are numbered from `first_index`.
    """

    by_id = {player.dk_id: player for player in slate.players}
    optimizer = LineupOptimizer(
        slate, excluded_ids=excluded, time_limit_seconds=time_limit_seconds
    )
    for roster in forbidden_rosters:
        optimizer.add_no_good(roster)
    effective_overlap = (
        max_person_overlap if slate.mode is EngineMode.SHOWDOWN else None
    )
    selected: list[SelectedLineup] = []
    forbidden_captains: list[str] = []
    captain_repeats_from: int | None = None  # position in this run, 1-based
    for position in range(1, count + 1):
        index = first_index + position - 1
        result = optimizer.solve(objective)
        if (
            result.roster is None
            and slate.mode is EngineMode.SHOWDOWN
            and differentiate_captain
            and selected
        ):
            # Every selectable person has already captained one lineup, so the
            # distinct-captain rule alone makes the next solve infeasible. That
            # is a structural limit of the pool, not a reason to hand back
            # nothing: rebuild the model without the captain no-goods, keep
            # every exact-roster and overlap cut, and continue with captain
            # repetition permitted. The index where repetition began is
            # reported so the review can see it.
            optimizer = LineupOptimizer(
                slate, excluded_ids=excluded, time_limit_seconds=time_limit_seconds
            )
            for roster in forbidden_rosters:
                optimizer.add_no_good(roster)
            for earlier in selected:
                optimizer.add_no_good(earlier.roster)
                if effective_overlap is not None:
                    optimizer.add_person_overlap_limit(earlier.roster, effective_overlap)
            differentiate_captain = False
            captain_repeats_from = position
            result = optimizer.solve(objective)
        if result.roster is None:
            where = ("" if stage == "SEQUENTIAL" else
                     ":stage=UNBOUND_FILL:no distinct lineup is left for a row the policy leaves"
                     " unbound, so this review delivers nothing")
            raise SelectionError(
                f"SOLVER_RETURNED_NO_LINEUP:index={index}:status={result.status}"
                f":selectable_people={len(contract.selectable_people)}{where}",
                status="SOLVER_RETURNED_NO_LINEUP",
                facts={"stage": stage, "index": index, "selected": len(selected),
                       "requested": count, "selectable_people": len(contract.selectable_people)},
            )
        roster = tuple(result.roster)
        validation = validate_lineup(slate, roster)
        if validation.lineup is None:
            raise SelectionError(
                f"SOLVER_PRODUCED_ILLEGAL_LINEUP:index={index}:{validation.errors}"
            )
        blocked = set(excluded) & set(roster)
        if blocked:
            raise SelectionError(
                f"SOLVER_SELECTED_AN_EXCLUDED_ROW:index={index}:{sorted(blocked)}"
            )
        captain = roster[0] if slate.mode is EngineMode.SHOWDOWN else ""
        selected.append(
            SelectedLineup(
                index=index,
                roster=roster,
                captain_dk_id=captain,
                salary=validation.lineup.salary,
                prior_points=sum(objective[dk_id] for dk_id in roster),
                canonical_key=validation.lineup.canonical_key,
                solver_status=result.status,
                solver_seconds=result.elapsed_seconds,
            )
        )
        if position == count:
            break
        # Forbid this exact roster, cap how much personnel may carry over, and
        # optionally forbid a repeat captain. Without the overlap cap the next
        # solve returns the same six people with a rotated captain.
        optimizer.add_no_good(roster)
        if effective_overlap is not None:
            optimizer.add_person_overlap_limit(roster, effective_overlap)
        if differentiate_captain and slate.mode is EngineMode.SHOWDOWN:
            optimizer.add_no_good([captain])
            forbidden_captains.append(captain)

    keys = [lineup.canonical_key for lineup in selected]
    if len(set(keys)) != len(keys):
        raise SelectionError("DUPLICATE_LINEUP_SELECTED")
    distinct_captain_span = (
        selected[: captain_repeats_from - 1]
        if captain_repeats_from is not None
        else selected
    )
    if slate.mode is EngineMode.SHOWDOWN and (
        differentiate_captain or captain_repeats_from is not None
    ):
        captains = [lineup.captain_dk_id for lineup in distinct_captain_span]
        if len(set(captains)) != len(captains):
            raise SelectionError("DUPLICATE_CAPTAIN_SELECTED")

    if effective_overlap is not None and len(selected) > 1:
        for earlier in range(len(selected)):
            for later in range(earlier + 1, len(selected)):
                first = {by_id[dk].underlying_id for dk in selected[earlier].roster}
                second = {by_id[dk].underlying_id for dk in selected[later].roster}
                shared = len(first & second)
                if shared > effective_overlap:
                    raise SelectionError(
                        f"OVERLAP_LIMIT_BREACHED:{earlier + 1}v{later + 1}:{shared}"
                        f">{effective_overlap}"
                    )
    return _Sequential(
        selected=selected,
        forbidden_captains=forbidden_captains,
        captain_repeats_from_index=(
            None if captain_repeats_from is None else first_index + captain_repeats_from - 1
        ),
        differentiate_captain=differentiate_captain,
        effective_overlap=effective_overlap,
    )


def _objective(slate: SlateContract, scores: PriorScores, excluded: Sequence[str]) -> dict[str, float]:
    """Prior points by DraftKings ID, zero for every excluded row.

    Every row of an unavailable person is scoreless as well as excluded, so a
    solver bug that ignored the exclusion could not profit from it either.
    """

    blocked = set(excluded)
    objective = {
        dk_id: (0.0 if dk_id in blocked else value)
        for dk_id, value in scores.by_dk_id.items()
    }
    for player in slate.players:
        objective.setdefault(player.dk_id, 0.0)
    return objective


def _fill_unbound(
    slate: SlateContract,
    objective: Mapping[str, float],
    excluded: Sequence[str],
    contract: ParticipationContract,
    *,
    policy_lineups: list[SelectedLineup],
    forbidden_rosters: Sequence[tuple[str, ...]],
    count: int,
    differentiate_captain: bool,
    max_person_overlap: int | None,
    time_limit_seconds: float,
) -> tuple[list[SelectedLineup], dict[str, object]]:
    """The rows a subset policy leaves unbound, filled after its joint solve (Session 11b).

    C1 (Classic) or sequential Showdown, under the run's own exclusions only,
    with every policy lineup and every prefilled roster as a no-good (R29).
    """

    run = _sequential_lineups(
        slate, objective, excluded, contract, count=count, first_index=len(policy_lineups) + 1,
        forbidden_rosters=(*forbidden_rosters, *(lineup.roster for lineup in policy_lineups)),
        differentiate_captain=differentiate_captain, max_person_overlap=max_person_overlap,
        time_limit_seconds=time_limit_seconds, stage="UNBOUND_FILL",
    )
    policy_keys = {lineup.canonical_key for lineup in policy_lineups}
    repeated = [lineup.index for lineup in run.selected if lineup.canonical_key in policy_keys]
    if repeated:
        raise SelectionError(
            f"DUPLICATE_LINEUP_SELECTED:unbound fill indexes {repeated} repeat a policy lineup")
    classic = slate.mode is EngineMode.CLASSIC
    report = {
        "source": "C1" if classic else "SHOWDOWN_SEQUENTIAL",
        "profile_version": CLASSIC_PROFILE_VERSION if classic else PROFILE_VERSION,
        "lineups": len(run.selected),
        "lineup_indexes": [lineup.index for lineup in run.selected],
        "no_good_rosters": {"policy_lineups": len(policy_lineups),
                            "prefilled_rosters": len(forbidden_rosters)},
        "exclusions": "THE_RUN_S_OWN_NOT_THE_POLICY_S",
        "excluded_rows": len(excluded),
        "differentiation": run.differentiation(slate),
        "person_exposure": run.person_exposure(slate),
        "forbidden_captain_rows": run.forbidden_captains,
        "non_optimal_lineups": [
            lineup.index for lineup in run.selected if lineup.solver_status != "OPTIMAL"
        ],
    }
    return [*policy_lineups, *run.selected], report


def _refuse_prefilled_repeats(selected: Sequence[SelectedLineup], forbidden_keys: set[str]) -> None:
    """The backstop (Session 11): no selected lineup is a prefilled roster (R29)."""

    repeated = [lineup.index for lineup in selected if lineup.canonical_key in forbidden_keys]
    if repeated:
        raise SelectionError(f"ENTRY_PREFILLED_LINEUP_REPEATED:selection_indexes={repeated}")


def assignments_for_entries(
    entry_ids: Sequence[str], lineups: Sequence[SelectedLineup]
) -> dict[str, tuple[str, ...]]:
    """Map reserved entries onto lineups, cycling if there are fewer lineups.

    Cycling is explicit rather than silent: asking for two lineups across five
    entries means three entries repeat, and the caller reports that.
    """

    if not entry_ids:
        raise SelectionError("NO_RESERVED_ENTRIES")
    if not lineups:
        raise SelectionError("NO_LINEUPS_TO_ASSIGN")
    return {
        entry_id: lineups[index % len(lineups)].roster
        for index, entry_id in enumerate(entry_ids)
    }
