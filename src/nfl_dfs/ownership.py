from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np

from .contracts import EngineMode, SlateContract


@dataclass(frozen=True)
class OwnershipBracket:
    low: float
    base: float
    high: float

    def __post_init__(self) -> None:
        values = (self.low, self.base, self.high)
        if not all(np.isfinite(value) for value in values):
            raise ValueError("ownership bracket values must be finite")
        if not 0.0 <= self.low <= self.base <= self.high <= 1.0:
            raise ValueError(
                "ownership bracket must satisfy 0 <= LOW <= BASE <= HIGH <= 1"
            )


@dataclass(frozen=True)
class OwnershipState:
    name: str
    ownership: dict[str, float]
    label: str = "COLD_START_OWNERSHIP_PRIOR"


def _rank_percentile(values: np.ndarray, descending: bool = True) -> np.ndarray:
    order = np.argsort(-values if descending else values, kind="stable")
    ranks = np.empty(len(values), dtype=float)
    ranks[order] = np.linspace(1.0, 0.0, len(values), endpoint=False)
    return ranks


def cold_start_states(
    slate: SlateContract,
    projection_mean: Mapping[str, float],
    team_total: Mapping[str, float],
    brackets: Mapping[str, OwnershipBracket] | None = None,
) -> tuple[OwnershipState, ...]:
    players = list(slate.players)
    salaries = np.array([player.salary for player in players], dtype=float)
    projections = np.array([projection_mean.get(player.dk_id, 0.0) for player in players])
    values = projections / np.maximum(salaries, 1.0) * 1000.0
    utilities = (
        0.20 * _rank_percentile(salaries)
        + 0.35 * _rank_percentile(projections)
        + 0.25 * _rank_percentile(values)
        + 0.20 * np.array([team_total.get(player.team, 0.0) for player in players])
        / max(max(team_total.values(), default=1.0), 1.0)
    )
    bracket_map = brackets or {}
    if slate.mode is EngineMode.CLASSIC:
        targets = {"QB": 1.0, "RB": 2.5, "WR": 3.5, "TE": 1.0, "DST": 1.0}
        groups = [player.position for player in players]
    else:
        targets = {"CPT": 1.0, "FLEX": 5.0}
        groups = [player.role or "" for player in players]

    base = np.zeros(len(players), dtype=float)
    for group, target in targets.items():
        indices = np.array([i for i, value in enumerate(groups) if value == group], dtype=int)
        logits = 2.1 * utilities[indices]
        probabilities = np.exp(logits - logits.max())
        base[indices] = target * probabilities / probabilities.sum()

    state_multipliers = {
        "BASE": 1.0,
        "CHALK_SURGE": 1.25,
        "CHALK_FADE": 0.80,
        "LATE_VALUE_SURGE": 1.10,
        "SHARP_FIELD": 1.05,
    }
    states: list[OwnershipState] = []
    for state_name, chalk_multiplier in state_multipliers.items():
        adjusted = base.copy()
        median_utility = float(np.median(utilities))
        for i, player in enumerate(players):
            if utilities[i] >= median_utility:
                adjusted[i] *= chalk_multiplier
            bracket = bracket_map.get(player.dk_id)
            if bracket:
                selected = {
                    "CHALK_FADE": bracket.low,
                    "BASE": bracket.base,
                    "CHALK_SURGE": bracket.high,
                    "LATE_VALUE_SURGE": bracket.high,
                    "SHARP_FIELD": bracket.base,
                }[state_name]
                adjusted[i] = selected
        for group, target in targets.items():
            indices = np.array([i for i, value in enumerate(groups) if value == group], dtype=int)
            total = adjusted[indices].sum()
            if total <= 0:
                adjusted[indices] = target / len(indices)
            else:
                adjusted[indices] *= target / total
        states.append(
            OwnershipState(
                state_name,
                {player.dk_id: float(adjusted[i]) for i, player in enumerate(players)},
            )
        )
    return tuple(states)


def ownership_roster_total(state: OwnershipState) -> float:
    return float(sum(state.ownership.values()))
