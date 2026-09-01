from __future__ import annotations

import pytest
from hypothesis import given, strategies as st

from nfl_dfs.scoring import (
    DefenseStatLine,
    KickerStatLine,
    OffensiveStatLine,
    apply_captain_multiplier,
    score_defense,
    score_kicker,
    score_offense,
)


def test_offense_all_categories_and_bonuses() -> None:
    stats = OffensiveStatLine(
        passing_yards=300,
        passing_tds=2,
        interceptions=1,
        rushing_yards=100,
        rushing_tds=1,
        receiving_yards=100,
        receiving_tds=1,
        receptions=5,
        return_tds=1,
        fumbles_lost=1,
        two_point_conversions=1,
        offensive_fumble_recovery_tds=1,
    )
    assert score_offense(stats) == pytest.approx(78.0)


def test_kicker_distance_buckets() -> None:
    assert score_kicker(KickerStatLine(2, 1, 1, 1)) == 14


@pytest.mark.parametrize(
    ("points_allowed", "expected"),
    [(0, 10), (1, 7), (6, 7), (7, 4), (13, 4), (14, 1), (20, 1), (21, 0), (27, 0), (28, -1), (34, -1), (35, -4)],
)
def test_defense_points_allowed_boundaries(points_allowed: int, expected: int) -> None:
    assert score_defense(DefenseStatLine(points_allowed=points_allowed)) == expected


def test_defense_event_categories() -> None:
    stats = DefenseStatLine(
        sacks=2,
        interceptions=1,
        fumble_recoveries=1,
        return_tds=1,
        interception_return_tds=1,
        fumble_return_tds=1,
        blocked_kick_return_tds=1,
        safeties=1,
        blocked_kicks=1,
        defensive_conversion_returns=1,
        points_allowed=21,
    )
    assert score_defense(stats) == 36


@given(st.floats(min_value=-100, max_value=200, allow_nan=False, allow_infinity=False))
def test_captain_multiplier_applied_once(score: float) -> None:
    assert apply_captain_multiplier(score, True) == pytest.approx(1.5 * score)
    assert apply_captain_multiplier(score, False) == score
