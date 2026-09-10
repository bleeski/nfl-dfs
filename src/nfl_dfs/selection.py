"""Prior-only Showdown lineup selection.

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

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence

from .contracts import EngineMode, SlateContract
from .kicker_roles import resolve_kicker_roles
from .lineups import validate_lineup
from .opportunity import OpportunityModel
from .offensive_roles import resolve_offensive_roles, verify_offensive_resolution
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


class SelectionError(ValueError):
    """A named fail-closed selection error."""


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
            "captain": names.get(self.captain_dk_id, self.captain_dk_id),
            "captain_dk_id": self.captain_dk_id,
            "salary": self.salary,
            "salary_remaining": 50_000 - self.salary,
            "prior_points": round(self.prior_points, 3),
            "canonical_key": self.canonical_key,
            "solver_status": self.solver_status,
            "solver_seconds": round(self.solver_seconds, 3),
            "players": [names.get(dk_id, dk_id) for dk_id in self.roster],
        }


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
    as_of: datetime | None = None,
    portfolio_policy: NormalizedPortfolioPolicy | None = None,
    policy_candidate_limit: int | None = None,
    policy_candidate_seconds: float | None = None,
    policy_candidate_per_solve_seconds: float = DEFAULT_CANDIDATE_PER_SOLVE_SECONDS,
    policy_selection_seconds: float | None = None,
) -> tuple[tuple[SelectedLineup, ...], PriorScores, dict[str, object]]:
    """Solve for `count` distinct legal lineups over the permitted pool.

    The `policy_*` bounds default to `None`, meaning "scale with the policy's
    entry count" (`max(32, 4 * entries)` candidates, `max(30s, 2s * entries)`
    of bank generation, `max(10s, 1s * entries)` for the joint solve). An
    explicit value is used as given, so tests and diagnostics can pin small
    bounds.
    """

    if slate.mode is not EngineMode.SHOWDOWN:
        raise SelectionError(f"MODE_NOT_SUPPORTED:{slate.mode.value}")
    if count < 1:
        raise SelectionError(f"LINEUP_COUNT_INVALID:{count}")
    if portfolio_policy is not None and count != portfolio_policy.entry_count:
        raise SelectionError(
            "PORTFOLIO_POLICY_ENTRY_COUNT_MISMATCH:"
            f"count={count}:policy_entries={portfolio_policy.entry_count}"
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
    offense = resolve_offensive_roles(
        slate, model, contract, evidence_path=offensive_role_evidence_json, as_of=as_of,
    )
    scores = score_pool(slate, offense.model, splits, kicker_roles=kicker_roles, offensive_roles=offense)
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
    if portfolio_policy is not None:
        for limit in portfolio_policy.effective_limits:
            if limit.combined_max_entries == 0:
                excluded_set.extend((limit.person.cpt_dk_id, limit.person.flex_dk_id))
    excluded = tuple(sorted(set(excluded_set)))
    # Every row of an unavailable person is scoreless as well as excluded, so a
    # solver bug that ignored the exclusion could not profit from it either.
    objective = {
        dk_id: (0.0 if dk_id in set(excluded) else value)
        for dk_id, value in scores.by_dk_id.items()
    }
    for player in slate.players:
        objective.setdefault(player.dk_id, 0.0)

    by_id = {player.dk_id: player for player in slate.players}
    selected: list[SelectedLineup] = []
    forbidden_captains: list[str] = []
    if portfolio_policy is not None:
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
        )
        if bank.blocking:
            raise SelectionError(
                f"{bank.status}:model_status={bank.terminal_model_status}:"
                f"candidates={len(bank.candidates)}:budget={bank.total_time_limit_seconds}"
            )
        portfolio_solve = solve_policy_portfolio(
            portfolio_policy,
            bank,
            time_limit_seconds=selection_seconds,
        )
        if not portfolio_solve.passed:
            raise SelectionError(
                f"{portfolio_solve.status}:model_status={portfolio_solve.model_status}:"
                f"candidate_bank={len(bank.candidates)}:complete={bank.complete}"
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
        verify_offensive_resolution(offense, at=as_of or datetime.now(timezone.utc))
        return tuple(selected), scores, report

    optimizer = LineupOptimizer(
        slate, excluded_ids=excluded, time_limit_seconds=time_limit_seconds
    )
    captain_repeats_from_index: int | None = None
    for index in range(1, count + 1):
        result = optimizer.solve(objective)
        if result.roster is None and differentiate_captain and selected:
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
            for earlier in selected:
                optimizer.add_no_good(earlier.roster)
                if max_person_overlap is not None:
                    optimizer.add_person_overlap_limit(earlier.roster, max_person_overlap)
            differentiate_captain = False
            captain_repeats_from_index = index
            result = optimizer.solve(objective)
        if result.roster is None:
            raise SelectionError(
                f"SOLVER_RETURNED_NO_LINEUP:index={index}:status={result.status}"
                f":selectable_people={len(contract.selectable_people)}"
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
        captain = roster[0]
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
        if index == count:
            break
        # Forbid this exact roster, cap how much personnel may carry over, and
        # optionally forbid a repeat captain. Without the overlap cap the next
        # solve returns the same six people with a rotated captain.
        optimizer.add_no_good(roster)
        if max_person_overlap is not None:
            optimizer.add_person_overlap_limit(roster, max_person_overlap)
        if differentiate_captain:
            optimizer.add_no_good([captain])
            forbidden_captains.append(captain)

    keys = [lineup.canonical_key for lineup in selected]
    if len(set(keys)) != len(keys):
        raise SelectionError("DUPLICATE_LINEUP_SELECTED")
    distinct_captain_span = (
        selected[: captain_repeats_from_index - 1]
        if captain_repeats_from_index is not None
        else selected
    )
    if differentiate_captain or captain_repeats_from_index is not None:
        captains = [lineup.captain_dk_id for lineup in distinct_captain_span]
        if len(set(captains)) != len(captains):
            raise SelectionError("DUPLICATE_CAPTAIN_SELECTED")

    if max_person_overlap is not None and len(selected) > 1:
        for earlier in range(len(selected)):
            for later in range(earlier + 1, len(selected)):
                first = {by_id[dk].underlying_id for dk in selected[earlier].roster}
                second = {by_id[dk].underlying_id for dk in selected[later].roster}
                shared = len(first & second)
                if shared > max_person_overlap:
                    raise SelectionError(
                        f"OVERLAP_LIMIT_BREACHED:{earlier + 1}v{later + 1}:{shared}"
                        f">{max_person_overlap}"
                    )

    exposure: dict[str, int] = {}
    for lineup in selected:
        for dk_id in lineup.roster:
            person = by_id[dk_id].underlying_id
            exposure[person] = exposure.get(person, 0) + 1

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
            "captain": (
                "DISTINCT_UNTIL_POOL_EXHAUSTED_THEN_REPEATED"
                if captain_repeats_from_index is not None
                else ("DISTINCT_PER_ENTRY" if differentiate_captain else "UNCONSTRAINED")
            ),
            "captain_repeats_from_index": captain_repeats_from_index,
            "captain_exposure": dict(
                sorted(
                    Counter(
                        by_id[lineup.captain_dk_id].underlying_id for lineup in selected
                    ).items(),
                    key=lambda item: (-item[1], item[0]),
                )
            ),
            "max_person_overlap": max_person_overlap,
            "basis": "STRUCTURAL_UNIQUENESS_NOT_A_CORRELATED_EQUITY_CLAIM",
        },
        "lineups": len(selected),
        "excluded_rows": len(excluded),
        "kicker_role_excluded_people": sorted(zero_share_people),
        "kicker_roles": kicker_roles.as_report(),
        "offensive_roles": offense.report,
        "selectable_people": len(contract.selectable_people),
        "person_exposure": dict(
            sorted(exposure.items(), key=lambda item: (-item[1], item[0]))
        ),
        "forbidden_captain_rows": forbidden_captains,
        "non_optimal_lineups": [
            lineup.index for lineup in selected if lineup.solver_status != "OPTIMAL"
        ],
        "threshold_sensitive": list(scores.threshold_sensitive),
        "score_omissions": list(scores.omissions),
        "never_calls": ["field.py", "economics.py", "portfolio economics"],
    }
    verify_offensive_resolution(offense, at=as_of or datetime.now(timezone.utc))
    return tuple(selected), scores, report


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
