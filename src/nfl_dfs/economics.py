from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np

from .contracts import PayoutTier, SlateContract
from .field import FieldLineup
from .payouts import divided_payout
from .simulation import SimulationResult, lineup_score_matrix


@dataclass(frozen=True)
class CandidateEconomics:
    rosters: tuple[tuple[str, ...], ...]
    gross_payout: np.ndarray
    ranks: np.ndarray
    tie_counts: np.ndarray
    duplicate_counts: np.ndarray


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
        dtype=np.float32,
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
                scenario_outcomes[field_indices[start:stop]]
                * field_multipliers[start:stop]
            ).sum(axis=1)
            score_parts.append(np.round(scores.astype(np.float64), 6))
        field_scores = np.concatenate(score_parts) if score_parts else np.empty(0)
        order = np.argsort(field_scores, kind="stable")
        sorted_scores = field_scores[order]
        sorted_counts = field_counts[order]
        cumulative = np.concatenate(([0], np.cumsum(sorted_counts, dtype=np.int64)))
        total_field = int(cumulative[-1])
        for candidate_index in range(len(rosters)):
            candidate_score = round(float(candidate_scores[scenario, candidate_index]), 6)
            left = int(np.searchsorted(sorted_scores, candidate_score, side="left"))
            right = int(np.searchsorted(sorted_scores, candidate_score, side="right"))
            ranks[scenario, candidate_index] += total_field - int(cumulative[right])
            tie_counts[scenario, candidate_index] += int(cumulative[right] - cumulative[left])

    gross = np.zeros((scenarios, len(rosters)), dtype=np.float32)
    tiers = tuple(payout_tiers)
    for candidate_index in range(len(rosters)):
        for scenario in range(scenarios):
            gross[scenario, candidate_index] = divided_payout(
                int(ranks[scenario, candidate_index]),
                int(tie_counts[scenario, candidate_index]),
                tiers,
                ticket_face_value,
            )
    return CandidateEconomics(
        rosters=rosters,
        gross_payout=gross,
        ranks=ranks,
        tie_counts=tie_counts,
        duplicate_counts=duplicate_counts,
    )


def exact_toy_field_settlement(
    scores: list[float], tiers: tuple[PayoutTier, ...]
) -> list[float]:
    result = [0.0] * len(scores)
    for index, score in enumerate(scores):
        rank = 1 + sum(other > score for other in scores)
        ties = sum(other == score for other in scores)
        result[index] = divided_payout(rank, ties, tiers)
    return result
