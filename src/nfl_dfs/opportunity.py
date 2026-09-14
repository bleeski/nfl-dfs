from __future__ import annotations

import csv
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Iterable, Mapping

import numpy as np

from .contracts import SalaryPlayer, SlateContract, unavailable_people


class OpportunityError(ValueError):
    pass


@dataclass(frozen=True)
class TeamProjection:
    team: str
    game_id: str
    plays_mean: float
    pass_rate: float
    pass_yards_per_attempt: float
    rush_yards_per_attempt: float
    touchdowns_mean: float
    field_goals_mean: float
    turnovers_mean: float
    sacks_allowed_mean: float
    uncertainty: float
    market_total: float
    market_spread: float
    market_observed_at: str
    weather_state: str
    era: str


@dataclass(frozen=True)
class PlayerOpportunity:
    underlying_id: str
    source_dk_id: str
    team: str
    position: str
    qb_attempt_share: float
    carry_share: float
    target_share: float
    catch_rate: float
    yards_per_target: float
    rushing_td_share: float
    receiving_td_share: float
    role_capacity: float
    evidence_state: str


@dataclass(frozen=True)
class OpportunityModel:
    teams: tuple[TeamProjection, ...]
    players: tuple[PlayerOpportunity, ...]
    route_participation_state: str = "UNKNOWN"
    model_label: str = "OPPORTUNITY_DIAGNOSTIC_V1"
    offensive_history_by_person: dict[str, dict[str, object]] = field(default_factory=dict)


TEAM_COLUMNS = (
    "TEAM",
    "GAME_ID",
    "PLAYS_MEAN",
    "PASS_RATE",
    "PASS_YARDS_PER_ATTEMPT",
    "RUSH_YARDS_PER_ATTEMPT",
    "TOUCHDOWNS_MEAN",
    "FIELD_GOALS_MEAN",
    "TURNOVERS_MEAN",
    "SACKS_ALLOWED_MEAN",
    "UNCERTAINTY",
    "MARKET_TOTAL",
    "MARKET_SPREAD",
    "MARKET_OBSERVED_AT",
    "WEATHER_STATE",
    "ERA",
)
PLAYER_COLUMNS = (
    "DK_ID",
    "TEAM",
    "POSITION",
    "QB_ATTEMPT_SHARE",
    "CARRY_SHARE",
    "TARGET_SHARE",
    "CATCH_RATE",
    "YARDS_PER_TARGET",
    "RUSHING_TD_SHARE",
    "RECEIVING_TD_SHARE",
    "ROLE_CAPACITY",
    "EVIDENCE_STATE",
)

WEATHER_STATES = frozenset(
    {
        "CLEAR",
        "INDOOR",
        "INDOOR_OR_CLEAR",
        "MIXED",
        "RAIN",
        "ROOF_CLOSED",
        "ROOF_OPEN",
        "SNOW",
        "WIND",
    }
)


def _strict_dict_rows(path: Path, columns: tuple[str, ...]) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != columns:
            raise OpportunityError(f"{path.name} header must be exactly {columns}")
        rows: list[dict[str, str]] = []
        for row_number, row in enumerate(reader, start=2):
            if None in row or any(value is None for value in row.values()):
                raise OpportunityError(f"{path.name} row {row_number} has missing or extra cells")
            if any(value.strip() for value in row.values()):
                rows.append(dict(row))
        return rows


def _number(row: Mapping[str, str], field: str, row_number: int) -> float:
    try:
        value = float(row[field])
    except (TypeError, ValueError) as exc:
        raise OpportunityError(f"row {row_number}: {field} is not numeric") from exc
    if not np.isfinite(value):
        raise OpportunityError(f"row {row_number}: {field} must be finite")
    return value


def load_opportunity_model(
    slate: SlateContract,
    team_csv: str | Path,
    player_csv: str | Path,
    *,
    allow_empty_groups: bool = False,
) -> OpportunityModel:
    team_rows = _strict_dict_rows(Path(team_csv), TEAM_COLUMNS)
    player_rows = _strict_dict_rows(Path(player_csv), PLAYER_COLUMNS)
    slate_teams = {player.team for player in slate.players}
    teams: list[TeamProjection] = []
    seen_teams: set[str] = set()
    for row_number, row in enumerate(team_rows, start=2):
        team = row["TEAM"].strip().upper()
        if team not in slate_teams or team in seen_teams:
            raise OpportunityError(f"row {row_number}: unknown or duplicate team {team}")
        numeric = {field: _number(row, field, row_number) for field in TEAM_COLUMNS[2:13]}
        if not 35 <= numeric["PLAYS_MEAN"] <= 95:
            raise OpportunityError(f"row {row_number}: PLAYS_MEAN outside [35,95]")
        if not 0.2 <= numeric["PASS_RATE"] <= 0.85:
            raise OpportunityError(f"row {row_number}: PASS_RATE outside [0.2,0.85]")
        if not 0 <= numeric["UNCERTAINTY"] <= 1:
            raise OpportunityError(f"row {row_number}: UNCERTAINTY outside [0,1]")
        numeric_bounds = {
            "PASS_YARDS_PER_ATTEMPT": (2.0, 15.0),
            "RUSH_YARDS_PER_ATTEMPT": (1.0, 10.0),
            "TOUCHDOWNS_MEAN": (0.0, 10.0),
            "FIELD_GOALS_MEAN": (0.0, 8.0),
            "TURNOVERS_MEAN": (0.0, 6.0),
            "SACKS_ALLOWED_MEAN": (0.0, 10.0),
            "MARKET_TOTAL": (20.0, 100.0),
            "MARKET_SPREAD": (-40.0, 40.0),
        }
        for field, (minimum, maximum) in numeric_bounds.items():
            if not minimum <= numeric[field] <= maximum:
                raise OpportunityError(
                    f"row {row_number}: {field} outside [{minimum:g},{maximum:g}]"
                )
        observed_at = row["MARKET_OBSERVED_AT"].strip()
        try:
            observed = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
            if observed.tzinfo is None:
                raise ValueError
        except ValueError as exc:
            raise OpportunityError(
                f"row {row_number}: MARKET_OBSERVED_AT must include a timezone"
            ) from exc
        matching_games = {
            game.game_id for game in slate.games if team in {game.away_team, game.home_team}
        }
        if row["GAME_ID"].strip() not in matching_games:
            raise OpportunityError(f"row {row_number}: TEAM/GAME_ID mismatch")
        weather_state = row["WEATHER_STATE"].strip().upper()
        if weather_state not in WEATHER_STATES:
            raise OpportunityError(
                f"row {row_number}: WEATHER_STATE must be one of {sorted(WEATHER_STATES)}"
            )
        era = row["ERA"].strip()
        if not era:
            raise OpportunityError(f"row {row_number}: ERA must not be blank")
        teams.append(
            TeamProjection(
                team=team,
                game_id=row["GAME_ID"].strip(),
                plays_mean=numeric["PLAYS_MEAN"],
                pass_rate=numeric["PASS_RATE"],
                pass_yards_per_attempt=numeric["PASS_YARDS_PER_ATTEMPT"],
                rush_yards_per_attempt=numeric["RUSH_YARDS_PER_ATTEMPT"],
                touchdowns_mean=numeric["TOUCHDOWNS_MEAN"],
                field_goals_mean=numeric["FIELD_GOALS_MEAN"],
                turnovers_mean=numeric["TURNOVERS_MEAN"],
                sacks_allowed_mean=numeric["SACKS_ALLOWED_MEAN"],
                uncertainty=numeric["UNCERTAINTY"],
                market_total=numeric["MARKET_TOTAL"],
                market_spread=numeric["MARKET_SPREAD"],
                market_observed_at=observed_at,
                weather_state=weather_state,
                era=era,
            )
        )
        seen_teams.add(team)
    if seen_teams != slate_teams:
        raise OpportunityError(f"team coverage mismatch: missing={sorted(slate_teams-seen_teams)}")

    by_dk_id = {player.dk_id: player for player in slate.players}
    seen_people: set[str] = set()
    players: list[PlayerOpportunity] = []
    for row_number, row in enumerate(player_rows, start=2):
        dk_id = row["DK_ID"].strip()
        salary_player = by_dk_id.get(dk_id)
        if salary_player is None:
            raise OpportunityError(f"row {row_number}: DK_ID {dk_id} not in salary pool")
        if salary_player.underlying_id in seen_people:
            raise OpportunityError(f"row {row_number}: duplicate underlying player")
        if row["TEAM"].strip().upper() != salary_player.team:
            raise OpportunityError(f"row {row_number}: player/team mismatch")
        if row["POSITION"].strip().upper() != salary_player.position:
            raise OpportunityError(f"row {row_number}: player/position mismatch")
        values = {field: _number(row, field, row_number) for field in PLAYER_COLUMNS[3:11]}
        for field in (
            "QB_ATTEMPT_SHARE",
            "CARRY_SHARE",
            "TARGET_SHARE",
            "CATCH_RATE",
            "RUSHING_TD_SHARE",
            "RECEIVING_TD_SHARE",
            "ROLE_CAPACITY",
        ):
            if not 0 <= values[field] <= 1:
                raise OpportunityError(f"row {row_number}: {field} outside [0,1]")
        if values["YARDS_PER_TARGET"] < 0:
            raise OpportunityError(f"row {row_number}: YARDS_PER_TARGET is negative")
        evidence_state = row["EVIDENCE_STATE"].strip().upper()
        if evidence_state not in {"PASS", "UNKNOWN", "STALE", "CONFLICTED"}:
            raise OpportunityError(f"row {row_number}: unsupported EVIDENCE_STATE")
        players.append(
            PlayerOpportunity(
                underlying_id=salary_player.underlying_id,
                source_dk_id=dk_id,
                team=salary_player.team,
                position=salary_player.position,
                qb_attempt_share=values["QB_ATTEMPT_SHARE"],
                carry_share=values["CARRY_SHARE"],
                target_share=values["TARGET_SHARE"],
                catch_rate=values["CATCH_RATE"],
                yards_per_target=values["YARDS_PER_TARGET"],
                rushing_td_share=values["RUSHING_TD_SHARE"],
                receiving_td_share=values["RECEIVING_TD_SHARE"],
                role_capacity=values["ROLE_CAPACITY"],
                evidence_state=evidence_state,
            )
        )
        seen_people.add(salary_player.underlying_id)
    slate_people = {player.underlying_id for player in slate.players}
    if seen_people != slate_people:
        # The same rule the frozen package and the projection identity check
        # apply (Ben's ruling 2026-09-13): a person may be absent from the model
        # inputs only when the salary bytes themselves flag him unable to play,
        # which the availability contract already makes unselectable. Re-derived
        # from the slate here, so an upstream drop can never widen into a
        # selectable person silently. A row for someone who is not on the slate
        # at all is always a hard stop; that direction is never tolerable.
        unexpected = sorted(seen_people.difference(slate_people))
        if unexpected:
            raise OpportunityError(
                f"player coverage mismatch; {len(unexpected)} rows are not on the "
                f"slate:{unexpected[:10]}"
            )
        selectable_missing = sorted(
            slate_people.difference(seen_people) - unavailable_people(slate.players)
        )
        if selectable_missing:
            raise OpportunityError(
                f"player coverage mismatch; missing {len(selectable_missing)} "
                f"selectable people:{selectable_missing[:10]}"
            )
    return conserve_team_shares(
        OpportunityModel(tuple(teams), tuple(players)), allow_empty_groups=allow_empty_groups
    )


def _normalize(values: np.ndarray, mask: np.ndarray, *, allow_empty: bool = False) -> np.ndarray:
    result = np.zeros_like(values, dtype=float)
    total = float(values[mask].sum())
    if mask.any() and total <= 0 and not allow_empty:
        raise OpportunityError("eligible opportunity shares cannot all be zero")
    elif total > 0:
        result[mask] = values[mask] / total
    return result


def conserve_team_shares(model: OpportunityModel, *, allow_empty_groups: bool = False) -> OpportunityModel:
    players = list(model.players)
    for team in {player.team for player in players}:
        indices = np.array([i for i, player in enumerate(players) if player.team == team])
        team_players = [players[i] for i in indices]
        positions = np.array([player.position for player in team_players])
        share_fields = {
            "qb_attempt_share": positions == "QB",
            "carry_share": np.isin(positions, ["QB", "RB", "WR", "TE"]),
            "target_share": np.isin(positions, ["RB", "WR", "TE"]),
            "rushing_td_share": np.isin(positions, ["QB", "RB", "WR", "TE"]),
            "receiving_td_share": np.isin(positions, ["RB", "WR", "TE"]),
        }
        normalized: dict[str, np.ndarray] = {}
        for field, mask in share_fields.items():
            values = np.array([getattr(player, field) for player in team_players], dtype=float)
            normalized[field] = _normalize(values, mask, allow_empty=allow_empty_groups)
        for local_index, global_index in enumerate(indices):
            players[global_index] = replace(
                players[global_index],
                **{field: float(values[local_index]) for field, values in normalized.items()},
            )
    return replace(model, players=tuple(players))


def remove_inactive_and_redistribute(
    model: OpportunityModel,
    inactive_underlying_ids: Iterable[str],
) -> OpportunityModel:
    inactive = set(inactive_underlying_ids)
    active = [player for player in model.players if player.underlying_id not in inactive]
    if len(active) == len(model.players):
        return model
    for team in {player.team for player in model.players}:
        if any(player.team == team for player in model.players) and not any(
            player.team == team for player in active
        ):
            raise OpportunityError(f"inactive set removes every player for {team}")
    redistributed = conserve_team_shares(replace(model, players=tuple(active)))
    for player in redistributed.players:
        for field in ("carry_share", "target_share", "rushing_td_share", "receiving_td_share"):
            if getattr(player, field) > player.role_capacity + 1e-9:
                raise OpportunityError(
                    f"redistribution exceeds role capacity for {player.underlying_id}:{field}"
                )
    return redistributed


def appg_is_absent_from_model_contract() -> bool:
    normalized = "|".join(
        field.lower().replace("_", "")
        for field in TeamProjection.__dataclass_fields__ | PlayerOpportunity.__dataclass_fields__
    )
    return "avg" + "points" not in normalized
