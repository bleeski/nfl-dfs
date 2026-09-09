"""Prior-only DraftKings points per salary row, derived from frozen artifacts.

What this computes, precisely: the DraftKings score of each person's *expected
stat line*. That is not the same quantity as his expected DraftKings score, and
the gap is not a rounding detail. `scoring.score_offense` awards a flat +3 at
100 receiving yards and `scoring.score_defense` steps between points-allowed
tiers, so feeding an expectation into a threshold function understates a player
who clears the threshold half the time and overstates one who never does. The
metric is therefore named for what it is, and every person sitting near a
threshold is reported as threshold-sensitive rather than quietly scored.

It is also explicitly not a ceiling. Ranking on points-of-the-expected-stat-line
maximizes a central estimate, which is the wrong objective for a top-heavy
tournament. Nothing here models ownership, leverage, correlation or duplication.

Every number traces to a frozen artifact: the two model-input CSVs `project`
publishes, plus the hash-pinned prior-season team-week artifact inside the prior
package for the three splits the model-input contract cannot carry (passing
versus rushing touchdowns, interceptions versus lost fumbles, and the
field-goal distance mix). Nothing is fitted and nothing is hand-typed.
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

from .contracts import EngineMode, SlateContract
from .kicker_roles import (
    KICKER_ROLE_SHARE_TOLERANCE,
    KickerRoleResolution,
    allocation_from_model_people,
    validate_kicker_scoring_allocation,
)
from .opportunity import OpportunityModel, PlayerOpportunity
from .scoring import (
    DefenseStatLine,
    KickerStatLine,
    OffensiveStatLine,
    apply_captain_multiplier,
    score_defense,
    score_kicker,
    score_offense,
)


SCORE_VERSION = "prior_points_of_expected_statline_v2"

# Distance buckets in the prior-season team artifact, mapped onto the three
# tiers DraftKings actually pays. Reading a published bucket layout is not the
# same as inventing a distribution.
_FG_BUCKETS = (
    ("fg_made_0_19", "field_goals_0_39"),
    ("fg_made_20_29", "field_goals_0_39"),
    ("fg_made_30_39", "field_goals_0_39"),
    ("fg_made_40_49", "field_goals_40_49"),
    ("fg_made_50_59", "field_goals_50_plus"),
    ("fg_made_60_", "field_goals_50_plus"),
)
_TEAM_SPLIT_COLUMNS = (
    "season",
    "week",
    "team",
    "season_type",
    "passing_tds",
    "rushing_tds",
    "passing_interceptions",
    "fumbles_lost_total",
    "pat_made",
    "pat_att",
    *(column for column, _tier in _FG_BUCKETS),
)
# Yardage thresholds that make the score discontinuous, and how close is close
# enough to say so.
_BONUS_THRESHOLDS = (
    ("passing_yards", 300.0),
    ("rushing_yards", 100.0),
    ("receiving_yards", 100.0),
)
_BONUS_WINDOW = 20.0
RECEIVING_POSITIONS = frozenset({"RB", "WR", "TE"})


class PriorScoreError(ValueError):
    """A named fail-closed scoring error."""


@dataclass(frozen=True)
class TeamSplits:
    """Prior-season splits the model-input contract has no field for."""

    team: str
    games: int
    pass_touchdown_fraction: float
    interception_fraction: float
    field_goal_mix: dict[str, float]
    pat_success_rate: float


def read_team_splits(
    path: str | Path, *, prior_season: int, teams: Iterable[str]
) -> dict[str, TeamSplits]:
    """Derive the three splits from the frozen prior-season team-week artifact."""

    wanted = {team.upper() for team in teams}
    try:
        with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            missing = [c for c in _TEAM_SPLIT_COLUMNS if c not in (reader.fieldnames or ())]
            if missing:
                raise PriorScoreError(f"TEAM_SPLIT_COLUMNS_MISSING:{sorted(missing)}")
            rows = [
                row
                for row in reader
                if (row.get("season") or "").strip() == str(prior_season)
                and (row.get("season_type") or "").strip().upper() == "REG"
                and (row.get("team") or "").strip().upper() in wanted
            ]
    except OSError as exc:
        raise PriorScoreError(f"TEAM_SPLIT_ARTIFACT_UNREADABLE:{path}:{exc}") from exc

    def number(row: Mapping[str, str], column: str) -> float:
        raw = (row.get(column) or "").strip()
        if raw in {"", "NA", "NaN", "null"}:
            return 0.0
        try:
            return float(raw)
        except ValueError as exc:
            raise PriorScoreError(
                f"TEAM_SPLIT_VALUE_NOT_NUMERIC:{column}:{raw!r}"
            ) from exc

    splits: dict[str, TeamSplits] = {}
    for team in sorted(wanted):
        team_rows = [r for r in rows if (r.get("team") or "").strip().upper() == team]
        if not team_rows:
            raise PriorScoreError(f"TEAM_SPLIT_COVERAGE_MISSING:{team}:{prior_season}")
        passing = sum(number(r, "passing_tds") for r in team_rows)
        rushing = sum(number(r, "rushing_tds") for r in team_rows)
        offensive = passing + rushing
        if offensive <= 0:
            raise PriorScoreError(f"TEAM_SPLIT_NO_TOUCHDOWNS:{team}")
        interceptions = sum(number(r, "passing_interceptions") for r in team_rows)
        fumbles = sum(number(r, "fumbles_lost_total") for r in team_rows)
        turnovers = interceptions + fumbles
        made = {}
        for column, tier in _FG_BUCKETS:
            made[tier] = made.get(tier, 0.0) + sum(number(r, column) for r in team_rows)
        total_made = sum(made.values())
        if total_made <= 0:
            raise PriorScoreError(f"TEAM_SPLIT_NO_FIELD_GOALS:{team}")
        pat_made = sum(number(r, "pat_made") for r in team_rows)
        pat_att = sum(number(r, "pat_att") for r in team_rows)
        splits[team] = TeamSplits(
            team=team,
            games=len(team_rows),
            pass_touchdown_fraction=passing / offensive,
            # A team with no turnovers at all would be a data fault, but the
            # split only matters when there are turnovers to split.
            interception_fraction=(interceptions / turnovers) if turnovers > 0 else 0.0,
            field_goal_mix={tier: value / total_made for tier, value in sorted(made.items())},
            pat_success_rate=(pat_made / pat_att) if pat_att > 0 else 0.0,
        )
    return splits


@dataclass(frozen=True)
class TeamVolume:
    team: str
    attempts: float
    carries: float
    pass_yards_per_attempt: float
    rush_yards_per_attempt: float
    sacks_allowed: float
    passing_touchdowns: float
    rushing_touchdowns: float
    interceptions: float
    lost_fumbles: float
    field_goals: float
    implied_points: float


def team_volumes(
    model: OpportunityModel, splits: Mapping[str, TeamSplits]
) -> dict[str, TeamVolume]:
    """Turn each team's prior rates into the volumes a stat line needs."""

    projections = {team.team: team for team in model.teams}
    if len(projections) != 2:
        raise PriorScoreError(f"EXPECTED_TWO_TEAMS:{sorted(projections)}")
    volumes: dict[str, TeamVolume] = {}
    for team, projection in sorted(projections.items()):
        split = splits.get(team)
        if split is None:
            raise PriorScoreError(f"TEAM_SPLIT_MISSING:{team}")
        dropbacks = projection.plays_mean * projection.pass_rate
        attempts = dropbacks - projection.sacks_allowed_mean
        if attempts <= 0:
            raise PriorScoreError(f"NONPOSITIVE_PASS_ATTEMPTS:{team}")
        carries = projection.plays_mean * (1.0 - projection.pass_rate)
        if carries <= 0:
            raise PriorScoreError(f"NONPOSITIVE_CARRIES:{team}")
        volumes[team] = TeamVolume(
            team=team,
            attempts=attempts,
            carries=carries,
            pass_yards_per_attempt=projection.pass_yards_per_attempt,
            rush_yards_per_attempt=projection.rush_yards_per_attempt,
            sacks_allowed=projection.sacks_allowed_mean,
            passing_touchdowns=projection.touchdowns_mean * split.pass_touchdown_fraction,
            rushing_touchdowns=projection.touchdowns_mean
            * (1.0 - split.pass_touchdown_fraction),
            interceptions=projection.turnovers_mean * split.interception_fraction,
            lost_fumbles=projection.turnovers_mean * (1.0 - split.interception_fraction),
            field_goals=projection.field_goals_mean,
            # A team's own implied total is half the game total shifted by its
            # own betting spread, which is negative when the team is favoured.
            implied_points=(projection.market_total - projection.market_spread) / 2.0,
        )
    return volumes


def _offensive_stat_line(
    player: PlayerOpportunity, volume: TeamVolume, touch_share: float
) -> OffensiveStatLine:
    attempts = volume.attempts * player.qb_attempt_share
    carries = volume.carries * player.carry_share
    targets = volume.attempts * player.target_share
    return OffensiveStatLine(
        passing_yards=attempts * volume.pass_yards_per_attempt,
        passing_tds=volume.passing_touchdowns * player.qb_attempt_share,
        interceptions=volume.interceptions * player.qb_attempt_share,
        rushing_yards=carries * volume.rush_yards_per_attempt,
        rushing_tds=volume.rushing_touchdowns * player.rushing_td_share,
        receiving_yards=targets * player.yards_per_target,
        receiving_tds=volume.passing_touchdowns * player.receiving_td_share,
        receptions=targets * player.catch_rate,
        fumbles_lost=volume.lost_fumbles * touch_share,
    )


def _kicker_stat_line(volume: TeamVolume, split: TeamSplits) -> KickerStatLine:
    mix = split.field_goal_mix
    return KickerStatLine(
        extra_points=(volume.passing_touchdowns + volume.rushing_touchdowns)
        * split.pat_success_rate,
        field_goals_0_39=volume.field_goals * mix.get("field_goals_0_39", 0.0),
        field_goals_40_49=volume.field_goals * mix.get("field_goals_40_49", 0.0),
        field_goals_50_plus=volume.field_goals * mix.get("field_goals_50_plus", 0.0),
    )


def _allocate_kicker_stat_line(line: KickerStatLine, share: float) -> KickerStatLine:
    """Allocate scoring events before any DraftKings scoring or CPT multiplier."""

    return KickerStatLine(
        extra_points=line.extra_points * share,
        field_goals_0_39=line.field_goals_0_39 * share,
        field_goals_40_49=line.field_goals_40_49 * share,
        field_goals_50_plus=line.field_goals_50_plus * share,
    )


def _defense_stat_line(opponent: TeamVolume) -> DefenseStatLine:
    """A defence scored entirely from what the other team gives up.

    Sacks are the opponent's sacks allowed and takeaways are his giveaways.
    Return touchdowns, safeties and blocked kicks have no basis in these
    artifacts and stay at zero, which understates a defence rather than
    inventing a rate for them.
    """

    return DefenseStatLine(
        sacks=opponent.sacks_allowed,
        interceptions=opponent.interceptions,
        fumble_recoveries=opponent.lost_fumbles,
        points_allowed=int(round(opponent.implied_points)),
    )


@dataclass(frozen=True)
class PriorScores:
    score_version: str
    by_dk_id: dict[str, float]
    by_person: dict[str, float]
    stat_lines: dict[str, object]
    threshold_sensitive: tuple[str, ...]
    omissions: tuple[str, ...]
    kicker_roles: dict[str, object]
    kicker_role_resolution: KickerRoleResolution

    def as_report(self) -> dict[str, object]:
        ranked = sorted(self.by_person.items(), key=lambda item: -item[1])
        return {
            "score_version": self.score_version,
            "metric": "DRAFTKINGS_POINTS_OF_THE_EXPECTED_STAT_LINE",
            "not_a_claim_of": "EV_ROI_CEILING_OWNERSHIP_LEVERAGE_OR_EDGE",
            "scored_people": len(self.by_person),
            "top_people": [
                {"person": person, "prior_points": round(value, 3)}
                for person, value in ranked[:12]
            ],
            "threshold_sensitive": list(self.threshold_sensitive),
            "threshold_note": (
                "DraftKings pays flat yardage bonuses and stepped points-allowed"
                " tiers. Scoring an expected stat line crosses those steps"
                " discontinuously, so a person listed here is near a step and his"
                " score is more fragile than the number suggests."
            ),
            "omissions": list(self.omissions),
            "kicker_roles": self.kicker_roles,
        }


def score_pool(
    slate: SlateContract,
    model: OpportunityModel,
    splits: Mapping[str, TeamSplits],
    *,
    kicker_roles: KickerRoleResolution | None = None,
) -> PriorScores:
    """Score every salary row, captain rows at the 1.5 multiplier."""

    if slate.mode is not EngineMode.SHOWDOWN:
        raise PriorScoreError(f"MODE_NOT_SUPPORTED:{slate.mode.value}")
    volumes = team_volumes(model, splits)
    if len(volumes) != 2:
        raise PriorScoreError(f"EXPECTED_TWO_TEAMS:{sorted(volumes)}")
    roles = kicker_roles or allocation_from_model_people(
        slate, [player.underlying_id for player in model.players]
    )
    validate_kicker_scoring_allocation(slate, roles)

    def touches(player: PlayerOpportunity) -> float:
        volume = volumes[player.team]
        return (
            volume.carries * player.carry_share
            + volume.attempts * player.target_share
            + volume.attempts * player.qb_attempt_share
        )

    team_touches: dict[str, float] = {}
    for player in model.players:
        team_touches[player.team] = team_touches.get(player.team, 0.0) + touches(player)

    by_person: dict[str, float] = {}
    stat_lines: dict[str, object] = {}
    sensitive: list[str] = []
    kicker_points_by_team: dict[str, dict[str, float]] = {}
    for player in model.players:
        if player.team not in volumes:
            raise PriorScoreError(f"PLAYER_TEAM_NOT_IN_POOL:{player.underlying_id}")
        volume = volumes[player.team]
        opponent_team = next(team for team in volumes if team != player.team)
        if player.position == "K":
            share = roles.shares_by_person.get(player.underlying_id)
            if share is None:
                raise PriorScoreError(
                    f"KICKER_ROLE_ALLOCATION_MISSING:{player.underlying_id}"
                )
            line = _allocate_kicker_stat_line(
                _kicker_stat_line(volume, splits[player.team]), share
            )
            points = score_kicker(line)
            kicker_points_by_team.setdefault(player.team, {})[
                player.underlying_id
            ] = float(points)
        elif player.position == "DST":
            line = _defense_stat_line(volumes[opponent_team])
            points = score_defense(line)
        else:
            total = team_touches.get(player.team, 0.0)
            share = touches(player) / total if total > 0 else 0.0
            line = _offensive_stat_line(player, volume, share)
            points = score_offense(line)
            for field, threshold in _BONUS_THRESHOLDS:
                value = getattr(line, field)
                if abs(value - threshold) <= _BONUS_WINDOW:
                    sensitive.append(
                        f"{player.underlying_id}:{field}={value:.1f}~{threshold:.0f}"
                    )
        # A negative prior score would let the solver treat a person as a cost
        # to be avoided rather than simply a poor choice; the floor keeps the
        # objective a ranking over non-negative contributions.
        by_person[player.underlying_id] = float(max(points, 0.0))
        stat_lines[player.underlying_id] = line

    kicker_conservation: dict[str, dict[str, object]] = {}
    for team, volume in sorted(volumes.items()):
        full_points = float(score_kicker(_kicker_stat_line(volume, splits[team])))
        allocated = sum(kicker_points_by_team.get(team, {}).values())
        has_recipient = bool(roles.team_allocations.get(team))
        expected = full_points if has_recipient else 0.0
        if not math.isclose(
            allocated,
            expected,
            rel_tol=0,
            abs_tol=KICKER_ROLE_SHARE_TOLERANCE,
        ):
            raise PriorScoreError(
                f"KICKER_SCORING_NOT_CONSERVED:team={team}:"
                f"allocated={allocated:.12g}:expected={expected:.12g}"
            )
        kicker_conservation[team] = {
            "unallocated_team_points": round(full_points, 6) if not has_recipient else 0.0,
            "allocated_points": round(allocated, 6),
            "full_team_points": round(full_points, 6),
            "recipients": dict(sorted(kicker_points_by_team.get(team, {}).items())),
        }

    by_dk_id: dict[str, float] = {}
    for salary_player in slate.players:
        base = by_person.get(salary_player.underlying_id)
        if base is None:
            continue
        by_dk_id[salary_player.dk_id] = apply_captain_multiplier(
            base, salary_player.role == "CPT"
        )
    if not by_dk_id:
        raise PriorScoreError("NO_SALARY_ROW_COULD_BE_SCORED")

    return PriorScores(
        score_version=SCORE_VERSION,
        by_dk_id=by_dk_id,
        by_person=by_person,
        stat_lines=stat_lines,
        threshold_sensitive=tuple(sorted(set(sensitive))),
        omissions=(
            "DEFENSIVE_RETURN_TOUCHDOWNS_SAFETIES_AND_BLOCKED_KICKS_NOT_MODELLED",
            "TWO_POINT_CONVERSIONS_AND_RETURN_TOUCHDOWNS_NOT_MODELLED",
            "POINTS_ALLOWED_TAKEN_FROM_THE_IMPLIED_TOTAL_AS_A_POINT_ESTIMATE",
            "NO_OWNERSHIP_LEVERAGE_CORRELATION_OR_DUPLICATION_TERM",
        ),
        kicker_roles={
            **roles.as_report(),
            "scoring_allocation": "TEAM_SCORING_EVENTS_BEFORE_DK_SCORING_AND_CPT_MULTIPLIER",
            "conservation": kicker_conservation,
        },
        kicker_role_resolution=roles,
    )
