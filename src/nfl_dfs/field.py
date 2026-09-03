from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Iterable

import numpy as np

from .contracts import EngineMode, SlateContract
from .lineups import validate_lineup
from .ownership import OwnershipState


@dataclass(frozen=True)
class FieldLineup:
    roster: tuple[str, ...]
    canonical_key: str
    multiplicity: int


def _weighted_sample(
    rng: np.random.Generator,
    ids: list[str],
    weights: list[float],
    count: int,
) -> list[str]:
    probabilities = np.asarray(weights, dtype=float)
    probabilities = np.clip(probabilities, 1e-12, None)
    probabilities /= probabilities.sum()
    selected = rng.choice(len(ids), size=count, replace=False, p=probabilities)
    return [ids[int(index)] for index in selected]


def generate_opponent_field(
    slate: SlateContract,
    ownership: OwnershipState,
    *,
    field_size: int,
    seed: int,
    maximum_attempt_factor: int = 200,
) -> tuple[FieldLineup, ...]:
    if isinstance(field_size, bool) or not isinstance(field_size, int) or field_size < 1:
        raise ValueError("field_size must be positive")
    if maximum_attempt_factor < 1:
        raise ValueError("maximum_attempt_factor must be positive")
    rng = np.random.default_rng(seed)
    players = list(slate.players)
    missing_ownership = sorted(
        player.dk_id for player in players if player.dk_id not in ownership.ownership
    )
    if missing_ownership:
        raise ValueError(
            f"ownership state does not cover salary IDs: {missing_ownership[:10]}"
        )
    ownership_values = np.array(
        [ownership.ownership[player.dk_id] for player in players], dtype=float
    )
    if not np.isfinite(ownership_values).all() or np.any(ownership_values < 0):
        raise ValueError("ownership values must be finite and non-negative")
    by_id = {player.dk_id: player for player in players}
    if slate.mode is EngineMode.CLASSIC:
        classic_pools = {
            position: [player for player in players if player.position == position]
            for position in ("QB", "RB", "WR", "TE", "DST")
        }
        classic_ids = {
            position: [player.dk_id for player in pool]
            for position, pool in classic_pools.items()
        }
        classic_base_weights = {
            position: np.array(
                [ownership.ownership[player.dk_id] for player in pool], dtype=float
            )
            for position, pool in classic_pools.items()
        }
        stack_weights: dict[tuple[str, str], np.ndarray] = {}
        for qb_team in {player.team for player in classic_pools["QB"]}:
            opponent = next(player.opponent for player in classic_pools["QB"] if player.team == qb_team)
            for position, pool in classic_pools.items():
                boosts = np.array(
                    [
                        (2.5 if player.team == qb_team and position in {"WR", "TE"} else 1.0)
                        * (1.6 if player.team == opponent and position in {"RB", "WR", "TE"} else 1.0)
                        for player in pool
                    ],
                    dtype=float,
                )
                stack_weights[(qb_team, position)] = classic_base_weights[position] * boosts
    else:
        cpt_pool = [player for player in players if player.role == "CPT"]
        cpt_ids = [player.dk_id for player in cpt_pool]
        cpt_weights = [ownership.ownership[player.dk_id] for player in cpt_pool]
        all_flex = [player for player in players if player.role == "FLEX"]
        flex_by_excluded_person = {
            person: [player for player in all_flex if player.underlying_id != person]
            for person in {player.underlying_id for player in cpt_pool}
        }
    canonical_roster: dict[str, tuple[str, ...]] = {}
    counts: Counter[str] = Counter()
    accepted = 0
    attempts = 0
    while accepted < field_size and attempts < field_size * maximum_attempt_factor:
        attempts += 1
        if slate.mode is EngineMode.CLASSIC:
            qb = _weighted_sample(
                rng,
                classic_ids["QB"],
                classic_base_weights["QB"].tolist(),
                1,
            )
            qb_player = by_id[qb[0]]
            flex_position = rng.choice(["RB", "WR", "TE"], p=[0.42, 0.48, 0.10])
            rb_count = 2 + int(flex_position == "RB")
            wr_count = 3 + int(flex_position == "WR")
            te_count = 1 + int(flex_position == "TE")
            chosen: dict[str, list[str]] = {"QB": qb}
            for position, count in (("RB", rb_count), ("WR", wr_count), ("TE", te_count), ("DST", 1)):
                chosen[position] = _weighted_sample(
                    rng,
                    classic_ids[position],
                    stack_weights[(qb_player.team, position)].tolist(),
                    count,
                )
            roster = (
                chosen["QB"][0],
                chosen["RB"][0],
                chosen["RB"][1],
                chosen["WR"][0],
                chosen["WR"][1],
                chosen["WR"][2],
                chosen["TE"][0],
                (chosen[flex_position][-1]),
                chosen["DST"][0],
            )
        else:
            captain = _weighted_sample(
                rng,
                cpt_ids,
                cpt_weights,
                1,
            )[0]
            captain_person = by_id[captain].underlying_id
            flex_pool = flex_by_excluded_person[captain_person]
            flex = _weighted_sample(
                rng,
                [player.dk_id for player in flex_pool],
                [ownership.ownership[player.dk_id] for player in flex_pool],
                5,
            )
            roster = (captain, *flex)
        validation = validate_lineup(slate, roster)
        if not validation.valid or validation.lineup is None:
            continue
        key = validation.lineup.canonical_key
        canonical_roster.setdefault(key, validation.lineup.roster)
        counts[key] += 1
        accepted += 1
    if accepted != field_size:
        raise RuntimeError(
            f"could generate only {accepted}/{field_size} legal field lineups in {attempts} attempts"
        )
    return tuple(
        FieldLineup(canonical_roster[key], key, counts[key]) for key in sorted(counts)
    )


def field_marginal_ownership(
    field: Iterable[FieldLineup], slate: SlateContract
) -> dict[str, float]:
    total = sum(lineup.multiplicity for lineup in field)
    counts: Counter[str] = Counter()
    for lineup in field:
        for dk_id in lineup.roster:
            counts[dk_id] += lineup.multiplicity
    return {player.dk_id: counts[player.dk_id] / total for player in slate.players}


def scale_field_multiplicities(
    field: Iterable[FieldLineup], target_size: int
) -> tuple[FieldLineup, ...]:
    lineups = tuple(field)
    source_size = sum(lineup.multiplicity for lineup in lineups)
    if source_size <= 0 or target_size <= 0:
        raise ValueError("field sizes must be positive")
    raw = np.array(
        [lineup.multiplicity * target_size / source_size for lineup in lineups], dtype=float
    )
    scaled = np.floor(raw).astype(int)
    remainder = target_size - int(scaled.sum())
    if remainder:
        order = np.argsort(-(raw - scaled), kind="stable")
        scaled[order[:remainder]] += 1
    return tuple(
        FieldLineup(lineup.roster, lineup.canonical_key, int(count))
        for lineup, count in zip(lineups, scaled, strict=True)
        if count > 0
    )
