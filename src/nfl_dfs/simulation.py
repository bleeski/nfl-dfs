from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

from .contracts import SlateContract
from .opportunity import OpportunityModel, PlayerOpportunity, TeamProjection
from .scoring import _points_allowed_score


@dataclass(frozen=True)
class SimulationResult:
    purpose: Literal["DESIGN", "SELECT", "REFEREE"]
    seed: int
    person_ids: tuple[str, ...]
    outcomes: np.ndarray
    weights: np.ndarray
    diagnostics: dict[str, float]

    def __post_init__(self) -> None:
        if self.outcomes.dtype != np.float32:
            raise ValueError("scenario outcomes must use float32")
        if self.outcomes.shape != (len(self.weights), len(self.person_ids)):
            raise ValueError("scenario matrix shape mismatch")


def _softmax_perturb(
    rng: np.random.Generator,
    base: np.ndarray,
    scenarios: int,
    scale: float,
) -> np.ndarray:
    if not len(base):
        return np.empty((scenarios, 0), dtype=float)
    safe = np.clip(base, 1e-9, None)
    logits = np.log(safe)[None, :] + scale * rng.standard_t(6, size=(scenarios, len(base)))
    logits -= logits.max(axis=1, keepdims=True)
    values = np.exp(logits)
    return values / values.sum(axis=1, keepdims=True)


def _allocate_integer_counts(
    rng: np.random.Generator,
    counts: np.ndarray,
    probabilities: np.ndarray,
) -> np.ndarray:
    result = np.zeros_like(probabilities, dtype=np.int16)
    for row, count in enumerate(counts.astype(int)):
        if count > 0:
            result[row] = rng.multinomial(count, probabilities[row])
    return result


def _team_person_indices(players: tuple[PlayerOpportunity, ...], team: str) -> np.ndarray:
    return np.array([i for i, player in enumerate(players) if player.team == team], dtype=int)


def simulate_factor_bank(
    slate: SlateContract,
    model: OpportunityModel,
    *,
    scenarios: int,
    seed: int,
    purpose: Literal["DESIGN", "SELECT", "REFEREE"],
    tail_oversample: bool = False,
) -> SimulationResult:
    if scenarios < 1:
        raise ValueError("scenarios must be positive")
    if purpose != "DESIGN" and tail_oversample:
        raise ValueError("tail oversampling is restricted to DESIGN")
    salary_people = {player.underlying_id for player in slate.players}
    model_people = {player.underlying_id for player in model.players}
    if salary_people != model_people:
        raise ValueError("opportunity model does not cover the salary pool")
    rng = np.random.default_rng(seed)
    people = model.players
    person_ids = tuple(player.underlying_id for player in people)
    outcomes = np.zeros((scenarios, len(people)), dtype=np.float64)
    weights = np.ones(scenarios, dtype=np.float64)
    game_factors: dict[str, np.ndarray] = {}
    for game in slate.games:
        factor = rng.standard_t(5, size=scenarios)
        if tail_oversample:
            tail = rng.random(scenarios) < 0.25
            factor[tail] += rng.choice([-2.0, 2.0], size=int(tail.sum()))
            # A bounded diagnostic importance correction; SELECT/REFEREE are ordinary draws.
            weights[tail] *= 0.5
            weights[~tail] *= 1.0 / 0.75
        game_factors[game.game_id] = factor

    team_projection = {team.team: team for team in model.teams}
    team_totals: dict[str, np.ndarray] = {}
    team_turnovers: dict[str, np.ndarray] = {}
    team_sacks_allowed: dict[str, np.ndarray] = {}
    for game in slate.games:
        game_factor = game_factors[game.game_id]
        for team_name in (game.away_team, game.home_team):
            team = team_projection[team_name]
            idx = _team_person_indices(people, team_name)
            team_players = [people[i] for i in idx]
            positions = np.array([player.position for player in team_players])
            team_shock = 0.55 * game_factor + 0.65 * rng.standard_t(6, size=scenarios)
            sigma = 0.05 + 0.12 * team.uncertainty
            plays = np.clip(
                np.rint(team.plays_mean * np.exp(sigma * team_shock - 0.5 * sigma * sigma)),
                35,
                95,
            ).astype(int)
            pass_probability = np.clip(
                team.pass_rate + 0.035 * rng.standard_t(7, size=scenarios) - 0.025 * team_shock,
                0.2,
                0.85,
            )
            pass_attempts = rng.binomial(plays, pass_probability)
            rush_attempts = plays - pass_attempts
            scoring_rate = np.clip(
                team.touchdowns_mean * np.exp(0.20 * team_shock - 0.02), 0.05, 8.0
            )
            touchdowns = rng.poisson(scoring_rate)
            pass_td_probability = np.clip(0.40 + 0.45 * pass_probability, 0.35, 0.82)
            passing_tds = rng.binomial(touchdowns, pass_td_probability)
            rushing_tds = touchdowns - passing_tds
            field_goals = rng.poisson(
                np.clip(team.field_goals_mean * np.exp(0.08 * team_shock), 0.01, 5.0)
            )
            turnovers = rng.poisson(
                np.clip(team.turnovers_mean * np.exp(-0.10 * team_shock), 0.01, 6.0)
            )
            sacks_allowed = rng.poisson(
                np.clip(team.sacks_allowed_mean * np.exp(-0.05 * team_shock), 0.01, 10.0)
            )
            team_turnovers[team_name] = turnovers
            team_sacks_allowed[team_name] = sacks_allowed
            team_totals[team_name] = 7 * touchdowns + 3 * field_goals

            qb_mask = positions == "QB"
            rush_mask = np.isin(positions, ["QB", "RB", "WR", "TE"])
            recv_mask = np.isin(positions, ["RB", "WR", "TE"])
            kicker_mask = positions == "K"
            qbs = np.flatnonzero(qb_mask)
            rushers = np.flatnonzero(rush_mask)
            receivers = np.flatnonzero(recv_mask)
            kickers = np.flatnonzero(kicker_mask)

            if len(qbs):
                qb_base = np.array([team_players[i].qb_attempt_share for i in qbs])
                qb_share = _softmax_perturb(rng, qb_base, scenarios, 0.12 + team.uncertainty * 0.1)
                qb_attempts = pass_attempts[:, None] * qb_share
                passing_yards_team = np.clip(
                    pass_attempts
                    * team.pass_yards_per_attempt
                    * np.exp(0.14 * team_shock + 0.10 * rng.standard_t(7, size=scenarios) - 0.015),
                    0,
                    None,
                )
                qb_td = _allocate_integer_counts(rng, passing_tds, qb_share)
                qb_interceptions = _allocate_integer_counts(
                    rng, turnovers, qb_share
                )
                for local, qb_local in enumerate(qbs):
                    global_index = idx[qb_local]
                    outcomes[:, global_index] += (
                        0.04 * passing_yards_team * qb_share[:, local]
                        + 4 * qb_td[:, local]
                        - qb_interceptions[:, local]
                    )
                    outcomes[:, global_index] += 3 * (
                        passing_yards_team * qb_share[:, local] >= 300
                    )
            else:
                passing_yards_team = np.zeros(scenarios)

            if len(receivers):
                target_base = np.array([team_players[i].target_share for i in receivers])
                target_share = _softmax_perturb(
                    rng, target_base, scenarios, 0.22 + team.uncertainty * 0.15
                )
                receiving_td_base = np.array(
                    [team_players[i].receiving_td_share for i in receivers]
                )
                receiving_td_share = _softmax_perturb(
                    rng, receiving_td_base, scenarios, 0.35 + team.uncertainty * 0.2
                )
                receiving_tds = _allocate_integer_counts(rng, passing_tds, receiving_td_share)
                yards_weights = target_share * np.array(
                    [max(team_players[i].yards_per_target, 0.1) for i in receivers]
                )[None, :]
                yards_weights /= yards_weights.sum(axis=1, keepdims=True)
                receiver_yards = passing_yards_team[:, None] * yards_weights
                catches = (
                    pass_attempts[:, None]
                    * target_share
                    * np.array([team_players[i].catch_rate for i in receivers])[None, :]
                )
                for local, receiver_local in enumerate(receivers):
                    global_index = idx[receiver_local]
                    outcomes[:, global_index] += (
                        0.1 * receiver_yards[:, local]
                        + catches[:, local]
                        + 6 * receiving_tds[:, local]
                    )
                    outcomes[:, global_index] += 3 * (receiver_yards[:, local] >= 100)

            if len(rushers):
                carry_base = np.array([team_players[i].carry_share for i in rushers])
                carry_share = _softmax_perturb(
                    rng, carry_base, scenarios, 0.20 + team.uncertainty * 0.15
                )
                rush_td_base = np.array(
                    [team_players[i].rushing_td_share for i in rushers]
                )
                rush_td_share = _softmax_perturb(
                    rng, rush_td_base, scenarios, 0.32 + team.uncertainty * 0.2
                )
                rushing_td_counts = _allocate_integer_counts(rng, rushing_tds, rush_td_share)
                team_rush_yards = np.clip(
                    rush_attempts
                    * team.rush_yards_per_attempt
                    * np.exp(0.10 * team_shock + 0.09 * rng.standard_t(7, size=scenarios) - 0.01),
                    0,
                    None,
                )
                rusher_yards = team_rush_yards[:, None] * carry_share
                for local, rusher_local in enumerate(rushers):
                    global_index = idx[rusher_local]
                    outcomes[:, global_index] += (
                        0.1 * rusher_yards[:, local] + 6 * rushing_td_counts[:, local]
                    )
                    outcomes[:, global_index] += 3 * (rusher_yards[:, local] >= 100)

            if len(kickers):
                kicker_share = np.full((scenarios, len(kickers)), 1.0 / len(kickers))
                xp = touchdowns[:, None] * kicker_share
                fg = field_goals[:, None] * kicker_share
                long_fg_rate = np.clip(0.16 + 0.05 * team.uncertainty, 0.05, 0.35)
                middle_fg_rate = 0.30
                for local, kicker_local in enumerate(kickers):
                    global_index = idx[kicker_local]
                    outcomes[:, global_index] += (
                        xp[:, local]
                        + fg[:, local]
                        * (3 + middle_fg_rate + 2 * long_fg_rate)
                    )

    for game in slate.games:
        for defense_team, opponent in (
            (game.away_team, game.home_team),
            (game.home_team, game.away_team),
        ):
            dst_indices = [
                i
                for i, player in enumerate(people)
                if player.team == defense_team and player.position == "DST"
            ]
            if not dst_indices:
                continue
            interceptions = np.minimum(team_turnovers[opponent], 4)
            fumbles = np.maximum(team_turnovers[opponent] - interceptions, 0)
            points_allowed_bonus = np.array(
                [_points_allowed_score(int(points)) for points in team_totals[opponent]],
                dtype=float,
            )
            return_tds = rng.poisson(0.08, size=scenarios)
            dst_points = (
                team_sacks_allowed[opponent]
                + 2 * interceptions
                + 2 * fumbles
                + 6 * return_tds
                + points_allowed_bonus
            )
            share = 1.0 / len(dst_indices)
            for index in dst_indices:
                outcomes[:, index] += dst_points * share

    weights /= weights.sum()
    diagnostics = {
        "scenario_count": float(scenarios),
        "mean_weight": float(weights.mean()),
        "max_weight": float(weights.max()),
        "passing_receiving_accounting": 1.0,
        "share_conservation": 1.0,
        "route_participation_known": float(model.route_participation_state == "PASS"),
    }
    return SimulationResult(
        purpose=purpose,
        seed=seed,
        person_ids=person_ids,
        outcomes=outcomes.astype(np.float32),
        weights=weights,
        diagnostics=diagnostics,
    )


def lineup_score_matrix(
    slate: SlateContract,
    simulations: SimulationResult,
    rosters: list[tuple[str, ...]],
) -> np.ndarray:
    person_index = {person: i for i, person in enumerate(simulations.person_ids)}
    by_dk = {player.dk_id: player for player in slate.players}
    matrix = np.zeros((simulations.outcomes.shape[0], len(rosters)), dtype=np.float32)
    for column, roster in enumerate(rosters):
        for slot, dk_id in enumerate(roster):
            player = by_dk[dk_id]
            multiplier = 1.5 if slate.mode.value == "SHOWDOWN" and slot == 0 else 1.0
            matrix[:, column] += multiplier * simulations.outcomes[:, person_index[player.underlying_id]]
    return matrix
