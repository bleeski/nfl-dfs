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

from dataclasses import dataclass
from typing import Mapping, Sequence

from .contracts import EngineMode, SlateContract
from .lineups import validate_lineup
from .opportunity import OpportunityModel
from .optimizer import LineupOptimizer
from .participation import ParticipationContract, excluded_dk_ids, selectable_pool_problems
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
) -> tuple[tuple[SelectedLineup, ...], PriorScores, dict[str, object]]:
    """Solve for `count` distinct legal lineups over the permitted pool."""

    if slate.mode is not EngineMode.SHOWDOWN:
        raise SelectionError(f"MODE_NOT_SUPPORTED:{slate.mode.value}")
    if count < 1:
        raise SelectionError(f"LINEUP_COUNT_INVALID:{count}")
    problems = selectable_pool_problems(slate, contract)
    if problems:
        raise SelectionError("SELECTABLE_POOL_INFEASIBLE:" + ";".join(problems))

    scores = score_pool(slate, model, splits)
    excluded = excluded_dk_ids(slate, contract)
    # Every row of an unavailable person is scoreless as well as excluded, so a
    # solver bug that ignored the exclusion could not profit from it either.
    objective = {
        dk_id: (0.0 if dk_id in set(excluded) else value)
        for dk_id, value in scores.by_dk_id.items()
    }
    for player in slate.players:
        objective.setdefault(player.dk_id, 0.0)

    optimizer = LineupOptimizer(
        slate, excluded_ids=excluded, time_limit_seconds=time_limit_seconds
    )
    by_id = {player.dk_id: player for player in slate.players}
    selected: list[SelectedLineup] = []
    forbidden_captains: list[str] = []
    for index in range(1, count + 1):
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
    if differentiate_captain:
        captains = [lineup.captain_dk_id for lineup in selected]
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
            "captain": "DISTINCT_PER_ENTRY" if differentiate_captain else "UNCONSTRAINED",
            "max_person_overlap": max_person_overlap,
            "basis": "STRUCTURAL_UNIQUENESS_NOT_A_CORRELATED_EQUITY_CLAIM",
        },
        "lineups": len(selected),
        "excluded_rows": len(excluded),
        "selectable_people": len(contract.selectable_people),
        "person_exposure": dict(
            sorted(exposure.items(), key=lambda item: (-item[1], item[0]))
        ),
        "forbidden_captain_rows": forbidden_captains,
        "threshold_sensitive": list(scores.threshold_sensitive),
        "score_omissions": list(scores.omissions),
        "never_calls": ["field.py", "economics.py", "portfolio economics"],
    }
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
