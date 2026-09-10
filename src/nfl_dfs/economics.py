from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np

from .contracts import PayoutTier, SlateContract
from .field import FieldLineup
from .reference_settlement import ReferenceFieldEntry, evaluate_reference_settlement
from .simulation import SimulationResult, lineup_score_matrix


@dataclass(frozen=True)
class CandidateEconomics:
    rosters: tuple[tuple[str, ...], ...]
    gross_payout: np.ndarray
    ranks: np.ndarray
    tie_counts: np.ndarray
    duplicate_counts: np.ndarray
    rounded_scores: np.ndarray | None = None
    cumulative_payout: np.ndarray | None = None

    def __post_init__(self) -> None:
        if self.gross_payout.ndim != 2:
            raise ValueError("gross payout must be scenarios by candidates")
        shape = self.gross_payout.shape
        if shape[0] < 1 or shape[1] < 1:
            raise ValueError("candidate economics must contain scenarios and candidates")
        if self.ranks.shape != shape or self.tie_counts.shape != shape:
            raise ValueError("rank and tie matrices must match gross payout shape")
        if shape[1] != len(self.rosters) or self.duplicate_counts.shape != (shape[1],):
            raise ValueError("candidate economics arrays do not match the roster bank")
        if (
            not np.isfinite(self.gross_payout).all()
            or np.any(self.gross_payout < 0)
            or np.any(self.ranks < 1)
            or np.any(self.tie_counts < 1)
            or np.any(self.duplicate_counts < 0)
        ):
            raise ValueError("candidate economics values are invalid")
        if self.rounded_scores is not None and self.rounded_scores.shape != shape:
            raise ValueError("candidate score matrix shape mismatch")
        if self.rounded_scores is not None and not np.isfinite(self.rounded_scores).all():
            raise ValueError("candidate scores must be finite")
        if self.cumulative_payout is not None and (
            self.cumulative_payout.ndim != 1
            or not np.isfinite(self.cumulative_payout).all()
            or np.any(np.diff(self.cumulative_payout) < -1e-9)
        ):
            raise ValueError("cumulative payout lookup is invalid")


def evaluate_candidates_against_field(
    *,
    slate: SlateContract,
    simulations: SimulationResult,
    candidates: Iterable[tuple[str, ...]],
    field: Iterable[FieldLineup],
    payout_tiers: Iterable[PayoutTier],
    ticket_face_value: float | None = None,
    field_chunk_size: int = 128,
) -> CandidateEconomics:
    rosters = tuple(candidates)
    field_lineups = tuple(field)
    if not rosters:
        raise ValueError("candidate list is empty")
    if field_chunk_size < 1:
        raise ValueError("field_chunk_size must be positive")
    if any(lineup.multiplicity < 1 for lineup in field_lineups):
        raise ValueError("field lineup multiplicities must be positive")
    uniform_weight = 1.0 / len(simulations.weights)
    if not np.allclose(simulations.weights, uniform_weight, rtol=0.0, atol=1e-12):
        raise ValueError("candidate economics requires a uniformly weighted scenario bank")
    field_keys = [lineup.canonical_key for lineup in field_lineups]
    if len(set(field_keys)) != len(field_keys):
        raise ValueError("field canonical keys must be unique")
    scenarios = simulations.outcomes.shape[0]
    candidate_scores = lineup_score_matrix(slate, simulations, list(rosters))
    ranks = np.ones((scenarios, len(rosters)), dtype=np.int32)
    tie_counts = np.ones((scenarios, len(rosters)), dtype=np.int32)
    candidate_keys = []
    from .lineups import validate_lineup

    for roster in rosters:
        validation = validate_lineup(slate, roster)
        if not validation.valid or validation.lineup is None:
            raise ValueError(f"invalid candidate in economics evaluation: {validation.errors}")
        candidate_keys.append(validation.lineup.canonical_key)
    duplicate_by_key = {lineup.canonical_key: lineup.multiplicity for lineup in field_lineups}
    duplicate_counts = np.array(
        [duplicate_by_key.get(key, 0) for key in candidate_keys], dtype=np.int32
    )

    person_index = {person: i for i, person in enumerate(simulations.person_ids)}
    by_dk = {player.dk_id: player for player in slate.players}
    field_indices = np.array(
        [
            [person_index[by_dk[dk_id].underlying_id] for dk_id in lineup.roster]
            for lineup in field_lineups
        ],
        dtype=np.int32,
    )
    field_multipliers = np.array(
        [
            [1.5 if slate.mode.value == "SHOWDOWN" and slot == 0 else 1.0 for slot in range(len(lineup.roster))]
            for lineup in field_lineups
        ],
        dtype=np.float64,
    )
    field_counts = np.array([lineup.multiplicity for lineup in field_lineups], dtype=np.int32)

    # Process one scenario and one bounded lineup chunk at a time. This never
    # allocates or retains a field-by-scenario score matrix.
    for scenario in range(scenarios):
        scenario_outcomes = simulations.outcomes[scenario]
        score_parts: list[np.ndarray] = []
        for start in range(0, len(field_lineups), field_chunk_size):
            stop = min(start + field_chunk_size, len(field_lineups))
            scores = (
                scenario_outcomes[field_indices[start:stop]].astype(np.float64)
                * field_multipliers[start:stop]
            ).sum(axis=1, dtype=np.float64)
            score_parts.append(np.round(scores, 6))
        field_scores = np.concatenate(score_parts) if score_parts else np.empty(0)
        order = np.argsort(field_scores, kind="stable")
        sorted_scores = field_scores[order]
        sorted_counts = field_counts[order]
        cumulative = np.concatenate(([0], np.cumsum(sorted_counts, dtype=np.int64)))
        total_field = int(cumulative[-1])
        candidate_row = np.round(candidate_scores[scenario], 6)
        left = np.searchsorted(sorted_scores, candidate_row, side="left")
        right = np.searchsorted(sorted_scores, candidate_row, side="right")
        ranks[scenario] += total_field - cumulative[right]
        tie_counts[scenario] += cumulative[right] - cumulative[left]

    tiers = tuple(payout_tiers)
    maximum_occupied_rank = int(np.max(ranks + tie_counts - 1))
    maximum_payout_rank = max((tier.rank_end for tier in tiers), default=0)
    # Reserve headroom for up to 150 operator entries so portfolio settlement
    # can add their mutual ranks and ties without rebuilding the payout table.
    maximum_supported_rank = max(maximum_occupied_rank + 150, maximum_payout_rank)
    payout_by_rank = np.zeros(
        maximum_supported_rank + 1,
        dtype=np.float64,
    )
    for tier in tiers:
        if tier.prize_type == "TICKET":
            if ticket_face_value is None:
                raise ValueError("ticket face value is required for ticket prizes")
            value = tier.value * ticket_face_value
        else:
            value = tier.value
        start = min(tier.rank_start, maximum_supported_rank + 1)
        stop = min(tier.rank_end, maximum_supported_rank) + 1
        if start < stop:
            payout_by_rank[start:stop] = value
    cumulative_payout = np.cumsum(payout_by_rank, dtype=np.float64)
    occupied_end = ranks + tie_counts - 1
    gross = (
        cumulative_payout[occupied_end] - cumulative_payout[ranks - 1]
    ) / tie_counts
    return CandidateEconomics(
        rosters=rosters,
        gross_payout=gross,
        ranks=ranks,
        tie_counts=tie_counts,
        duplicate_counts=duplicate_counts,
        rounded_scores=np.round(candidate_scores, 6),
        cumulative_payout=cumulative_payout,
    )


def exact_toy_field_settlement(
    scores: list[float], tiers: tuple[PayoutTier, ...]
) -> list[float]:
    """Compatibility wrapper over the Q1 independent reference evaluator."""

    if not scores:
        return []
    result = evaluate_reference_settlement(
        (
            ReferenceFieldEntry(
                entry_id=str(index), score=score, lineup_key=f"toy-lineup-{index}"
            )
            for index, score in enumerate(scores)
        ),
        tiers,
        field_size=len(scores),
    )
    by_id = {row.entry_id: row for row in result.rows}
    return [float(by_id[str(index)].gross_prize.cents / 100) for index in range(len(scores))]
