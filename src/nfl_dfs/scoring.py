from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OffensiveStatLine:
    passing_yards: float = 0.0
    passing_tds: int = 0
    interceptions: int = 0
    rushing_yards: float = 0.0
    rushing_tds: int = 0
    receiving_yards: float = 0.0
    receiving_tds: int = 0
    receptions: int = 0
    return_tds: int = 0
    fumbles_lost: int = 0
    two_point_conversions: int = 0
    offensive_fumble_recovery_tds: int = 0


@dataclass(frozen=True)
class KickerStatLine:
    extra_points: int = 0
    field_goals_0_39: int = 0
    field_goals_40_49: int = 0
    field_goals_50_plus: int = 0


@dataclass(frozen=True)
class DefenseStatLine:
    sacks: int = 0
    interceptions: int = 0
    fumble_recoveries: int = 0
    return_tds: int = 0
    interception_return_tds: int = 0
    fumble_return_tds: int = 0
    blocked_kick_return_tds: int = 0
    safeties: int = 0
    blocked_kicks: int = 0
    defensive_conversion_returns: int = 0
    points_allowed: int = 0


def score_offense(stats: OffensiveStatLine) -> float:
    score = (
        0.04 * stats.passing_yards
        + 4 * stats.passing_tds
        - stats.interceptions
        + 0.1 * stats.rushing_yards
        + 6 * stats.rushing_tds
        + 0.1 * stats.receiving_yards
        + 6 * stats.receiving_tds
        + stats.receptions
        + 6 * stats.return_tds
        - stats.fumbles_lost
        + 2 * stats.two_point_conversions
        + 6 * stats.offensive_fumble_recovery_tds
    )
    if stats.passing_yards >= 300:
        score += 3
    if stats.rushing_yards >= 100:
        score += 3
    if stats.receiving_yards >= 100:
        score += 3
    return float(score)


def score_kicker(stats: KickerStatLine) -> float:
    return float(
        stats.extra_points
        + 3 * stats.field_goals_0_39
        + 4 * stats.field_goals_40_49
        + 5 * stats.field_goals_50_plus
    )


def _points_allowed_score(points: int) -> int:
    if points < 0:
        raise ValueError("points allowed cannot be negative")
    if points == 0:
        return 10
    if points <= 6:
        return 7
    if points <= 13:
        return 4
    if points <= 20:
        return 1
    if points <= 27:
        return 0
    if points <= 34:
        return -1
    return -4


def score_defense(stats: DefenseStatLine) -> float:
    return float(
        stats.sacks
        + 2 * stats.interceptions
        + 2 * stats.fumble_recoveries
        + 6 * stats.return_tds
        + 6 * stats.interception_return_tds
        + 6 * stats.fumble_return_tds
        + 6 * stats.blocked_kick_return_tds
        + 2 * stats.safeties
        + 2 * stats.blocked_kicks
        + 2 * stats.defensive_conversion_returns
        + _points_allowed_score(stats.points_allowed)
    )


def apply_captain_multiplier(score: float, is_captain: bool) -> float:
    return 1.5 * score if is_captain else score
