from __future__ import annotations

import numpy as np

from nfl_dfs.opportunity import (
    OpportunityModel,
    PlayerOpportunity,
    TeamProjection,
    conserve_team_shares,
)
from nfl_dfs.simulation import simulate_factor_bank


def _model(slate) -> OpportunityModel:
    teams = []
    for game in slate.games:
        for team in (game.away_team, game.home_team):
            teams.append(
                TeamProjection(
                    team=team,
                    game_id=game.game_id,
                    plays_mean=64,
                    pass_rate=0.58,
                    pass_yards_per_attempt=6.8,
                    rush_yards_per_attempt=4.2,
                    touchdowns_mean=2.6,
                    field_goals_mean=1.5,
                    turnovers_mean=1.2,
                    sacks_allowed_mean=2.4,
                    uncertainty=0.25,
                    market_total=45,
                    market_spread=0,
                    market_observed_at="2026-09-13T12:00:00-04:00",
                    weather_state="INDOOR_OR_CLEAR",
                    era="2026",
                )
            )
    people = {}
    for player in slate.players:
        people.setdefault(player.underlying_id, player)
    players = []
    for player in people.values():
        position = player.position
        players.append(
            PlayerOpportunity(
                underlying_id=player.underlying_id,
                source_dk_id=player.dk_id,
                team=player.team,
                position=position,
                qb_attempt_share=1.0 if position == "QB" else 0.0,
                carry_share=1.0 if position in {"QB", "RB", "WR", "TE"} else 0.0,
                target_share=1.0 if position in {"RB", "WR", "TE"} else 0.0,
                catch_rate=0.68 if position in {"RB", "WR", "TE"} else 0.0,
                yards_per_target=7.2 if position in {"RB", "WR", "TE"} else 0.0,
                rushing_td_share=1.0 if position in {"QB", "RB", "WR", "TE"} else 0.0,
                receiving_td_share=1.0 if position in {"RB", "WR", "TE"} else 0.0,
                role_capacity=1.0,
                evidence_state="PASS",
            )
        )
    return conserve_team_shares(OpportunityModel(tuple(teams), tuple(players)))


def test_simulation_reproducible_float32_and_separate_purpose(classic_slate) -> None:
    model = _model(classic_slate)
    first = simulate_factor_bank(
        classic_slate, model, scenarios=50, seed=123, purpose="SELECT"
    )
    second = simulate_factor_bank(
        classic_slate, model, scenarios=50, seed=123, purpose="SELECT"
    )
    referee = simulate_factor_bank(
        classic_slate, model, scenarios=50, seed=124, purpose="REFEREE"
    )
    assert first.outcomes.dtype == np.float32
    assert np.array_equal(first.outcomes, second.outcomes)
    assert not np.array_equal(first.outcomes, referee.outcomes)
    assert np.isfinite(first.outcomes).all()
    assert np.isclose(first.weights.sum(), 1)
    assert first.diagnostics["passing_receiving_accounting"] == 1.0
    assert first.diagnostics["passing_receiving_max_abs_error"] == 0.0
    assert first.diagnostics["share_conservation_max_abs_error"] == 0.0


def test_showdown_simulates_one_outcome_per_person(showdown_slate) -> None:
    result = simulate_factor_bank(
        showdown_slate, _model(showdown_slate), scenarios=20, seed=8, purpose="DESIGN", tail_oversample=True
    )
    assert len(result.person_ids) == 63
    assert result.outcomes.shape == (20, 63)
