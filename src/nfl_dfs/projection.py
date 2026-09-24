from __future__ import annotations

import csv
import io
import json
import os
import shutil
import tempfile
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Iterable, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from .contracts import (
    SOURCE_LEDGER_SCHEMA,
    EngineMode,
    EvidenceScope,
    SalaryPlayer,
    SlateContract,
    earliest_source_freshness,
    unavailable_people,
)
from .contracts import SourceFreshness as SourceFreshnessContract
from .dk import PARSER_VERSION as DK_PARSER_VERSION
from .dk import parse_salaries
from .evidence import validate_source_ledger
from .hashing import sha256_bytes, sha256_file
from .opportunity import PLAYER_COLUMNS, TEAM_COLUMNS, load_opportunity_model
from .sources import SourcePolicyError, validate_source_reference_policy


TEAM_SOURCE_SCHEMA = "nfl_team_projection_source_v1"
# v2 (Session 09) is v1 plus the weather state UNOBSERVED. A producer declares
# it only when a record carries that state, so every other package is v1.
TEAM_SOURCE_SCHEMA_V2 = "nfl_team_projection_source_v2"
PLAYER_SOURCE_SCHEMA = "nfl_player_opportunity_source_v1"
IDENTITY_MAP_SCHEMA = "nfl_projection_identity_map_v1"
TEAM_SOURCE_PARSER = "team_projection_source_v1"
PLAYER_SOURCE_PARSER = "player_opportunity_source_v1"
IDENTITY_MAP_PARSER = "projection_identity_map_v1"
LEDGER_FILENAME = "source_ledger.json"
TEAM_FILENAME = "team_projections.csv"
PLAYER_FILENAME = "player_opportunities.csv"
# R08: the producer referenced its inputs by absolute original path and
# archived nothing, so moving the package, deleting the attachments or crossing
# from Windows to Linux broke resolution. Every consumed source is now archived
# content-addressed inside the package and addressed by a package-relative
# POSIX path, which resolves identically on both runtimes.
SOURCES_DIRNAME = "sources"
INPUT_SCOPES: Mapping[str, EvidenceScope] = {
    "salary": EvidenceScope.SLATE_GEOMETRY,
    "team_source": EvidenceScope.TEAM_PRIOR,
    "player_source": EvidenceScope.PLAYER_PRIOR,
    "identity_map": EvidenceScope.IDENTITY_MAP,
}


class ProjectionBuildError(ValueError):
    """A named fail-closed projection-package error."""


class _FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


LicenseDecision = Literal[
    "OPERATOR_SUPPLIED",
    "PUBLIC_DOMAIN",
    "PERMITTED_PUBLIC_API",
    "PERMITTED_REPOSITORY_LICENSE",
    "SECONDARY_STATUS_ONLY",
]
EvidenceState = Literal["PASS", "UNKNOWN", "STALE", "CONFLICTED"]


class ArtifactMetadata(_FrozenModel):
    source_uri: str = Field(min_length=1)
    captured_at: datetime
    observed_at: datetime
    expires_at: datetime
    license_decision: LicenseDecision
    parser_version: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
    evidence_state: EvidenceState
    coverage: dict[str, object] = Field(min_length=1)

    @field_validator("captured_at", "observed_at", "expires_at")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timestamps must be timezone-aware")
        return value

    @model_validator(mode="after")
    def valid_time_order(self) -> "ArtifactMetadata":
        if self.observed_at > self.captured_at + timedelta(minutes=5):
            raise ValueError("observed_at cannot follow captured_at by more than five minutes")
        if self.expires_at < self.observed_at:
            raise ValueError("expires_at cannot precede observed_at")
        return self


class SalaryArtifactMetadata(ArtifactMetadata):
    artifact_id: str = Field(pattern=r"^[0-9a-f]{64}$")


def _numeric(value: object) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ValueError("must be a JSON number")
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("must be finite")
    return result


class TeamSourceRecord(_FrozenModel):
    provider_team_id: str = Field(min_length=1)
    game_id: str = Field(min_length=3)
    plays_mean: Decimal = Field(ge=Decimal("35"), le=Decimal("95"))
    pass_rate: Decimal = Field(ge=Decimal("0.2"), le=Decimal("0.85"))
    pass_yards_per_attempt: Decimal = Field(ge=Decimal("2"), le=Decimal("15"))
    rush_yards_per_attempt: Decimal = Field(ge=Decimal("1"), le=Decimal("10"))
    touchdowns_mean: Decimal = Field(ge=Decimal("0"), le=Decimal("10"))
    field_goals_mean: Decimal = Field(ge=Decimal("0"), le=Decimal("8"))
    turnovers_mean: Decimal = Field(ge=Decimal("0"), le=Decimal("6"))
    sacks_allowed_mean: Decimal = Field(ge=Decimal("0"), le=Decimal("10"))
    uncertainty: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    market_total: Decimal = Field(ge=Decimal("20"), le=Decimal("100"))
    market_spread: Decimal = Field(ge=Decimal("-40"), le=Decimal("40"))
    market_observed_at: datetime
    weather_state: Literal[
        "CLEAR",
        "INDOOR",
        "INDOOR_OR_CLEAR",
        "MIXED",
        "RAIN",
        "ROOF_CLOSED",
        "ROOF_OPEN",
        "SNOW",
        "UNOBSERVED",
        "WIND",
    ]
    era: str = Field(min_length=1)
    evidence_state: EvidenceState

    @field_validator(
        "plays_mean",
        "pass_rate",
        "pass_yards_per_attempt",
        "rush_yards_per_attempt",
        "touchdowns_mean",
        "field_goals_mean",
        "turnovers_mean",
        "sacks_allowed_mean",
        "uncertainty",
        "market_total",
        "market_spread",
        mode="before",
    )
    @classmethod
    def strict_finite_number(cls, value: object) -> Decimal:
        return _numeric(value)

    @field_validator("market_observed_at")
    @classmethod
    def market_timestamp_timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("market_observed_at must be timezone-aware")
        return value


class TeamSource(_FrozenModel):
    schema_version: Literal["nfl_team_projection_source_v1", "nfl_team_projection_source_v2"]
    metadata: ArtifactMetadata
    records: tuple[TeamSourceRecord, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def v1_never_holds_an_unobserved_game(self) -> "TeamSource":
        # v1 is never mutated: only v2 can say a game was not observed.
        if self.schema_version == TEAM_SOURCE_SCHEMA and any(
            record.weather_state == "UNOBSERVED" for record in self.records
        ):
            raise ValueError("UNOBSERVED weather needs nfl_team_projection_source_v2")
        return self


class PlayerSourceRecord(_FrozenModel):
    provider_player_id: str = Field(min_length=1)
    provider_team_id: str = Field(min_length=1)
    position: str = Field(min_length=1)
    qb_attempt_weight: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    carry_weight: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    target_weight: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    catch_rate: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    yards_per_target: Decimal = Field(ge=Decimal("0"), le=Decimal("30"))
    rushing_td_weight: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    receiving_td_weight: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    role_capacity: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    evidence_state: EvidenceState

    @field_validator(
        "qb_attempt_weight",
        "carry_weight",
        "target_weight",
        "catch_rate",
        "yards_per_target",
        "rushing_td_weight",
        "receiving_td_weight",
        "role_capacity",
        mode="before",
    )
    @classmethod
    def strict_finite_number(cls, value: object) -> Decimal:
        return _numeric(value)


class PlayerSource(_FrozenModel):
    schema_version: Literal["nfl_player_opportunity_source_v1"]
    metadata: ArtifactMetadata
    records: tuple[PlayerSourceRecord, ...] = Field(min_length=1)


class TeamIdentityMapping(_FrozenModel):
    provider_team_id: str = Field(min_length=1)
    team: str = Field(pattern=r"^[A-Z]{2,3}$")
    game_id: str = Field(min_length=3)
    match_method: str = Field(min_length=1)
    evidence_state: EvidenceState


class PlayerIdentityMapping(_FrozenModel):
    provider_player_id: str = Field(min_length=1)
    provider_team_id: str = Field(min_length=1)
    dk_id: str = Field(pattern=r"^[0-9]+$")
    underlying_id: str = Field(min_length=1)
    team: str = Field(pattern=r"^[A-Z]{2,3}$")
    position: str = Field(min_length=1)
    dk_role: str | None = None
    match_method: str = Field(min_length=1)
    evidence_state: EvidenceState


class ProjectionIdentityMap(_FrozenModel):
    schema_version: Literal["nfl_projection_identity_map_v1"]
    metadata: ArtifactMetadata
    salary_artifact: SalaryArtifactMetadata
    team_mappings: tuple[TeamIdentityMapping, ...] = Field(min_length=1)
    player_mappings: tuple[PlayerIdentityMapping, ...] = Field(min_length=1)


class ProjectionPackage(_FrozenModel):
    output_dir: str
    team_projections: str
    player_opportunities: str
    source_ledger: str
    hashes: dict[str, str]
    input_hashes: dict[str, str]
    # The package's own expiry, carried out of the producer so a consumer never
    # has to reopen a source to learn when this stops being usable.
    ledger_schema_version: str
    expires_at: str
    expiry_basis: str
    archived_sources: dict[str, str]


def _json_payload(path: Path) -> object:
    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            parse_float=Decimal,
            parse_int=Decimal,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON number {value}")
            ),
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ProjectionBuildError(f"SOURCE_JSON_INVALID:{path.name}:{exc}") from exc


def _load_contract(path: Path, model: type[BaseModel], code: str):
    payload = _json_payload(path)
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        raise ProjectionBuildError(f"{code}:{path.name}:{exc}") from exc


def _parse_as_of(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        result = value
    else:
        try:
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ProjectionBuildError("AS_OF_INVALID:must be ISO 8601") from exc
    if result.tzinfo is None:
        raise ProjectionBuildError("AS_OF_INVALID:timezone is required")
    return result.astimezone(timezone.utc)


def _require_hash(path: Path, expected: str, label: str) -> str:
    if not path.is_file():
        raise ProjectionBuildError(f"INPUT_ARTIFACT_MISSING:{label}:{path}")
    if len(expected) != 64 or any(character not in "0123456789abcdef" for character in expected):
        raise ProjectionBuildError(f"EXPECTED_HASH_INVALID:{label}")
    actual = sha256_file(path)
    if actual != expected:
        raise ProjectionBuildError(
            f"INPUT_ARTIFACT_HASH_MISMATCH:{label}:expected={expected}:actual={actual}"
        )
    return actual


def _validate_metadata(
    metadata: ArtifactMetadata,
    *,
    expected_parser: str,
    as_of: datetime,
    label: str,
) -> None:
    if metadata.parser_version != expected_parser:
        raise ProjectionBuildError(
            f"PARSER_VERSION_UNAPPROVED:{label}:{metadata.parser_version}"
        )
    try:
        validate_source_reference_policy(
            metadata.source_uri,
            license_decision=metadata.license_decision,
            parser_version=metadata.parser_version,
        )
    except SourcePolicyError as exc:
        raise ProjectionBuildError(f"SOURCE_LICENSE_UNAPPROVED:{label}:{exc}") from exc
    captured = metadata.captured_at.astimezone(timezone.utc)
    observed = metadata.observed_at.astimezone(timezone.utc)
    expires = metadata.expires_at.astimezone(timezone.utc)
    if captured > as_of or observed > as_of:
        raise ProjectionBuildError(f"FUTURE_EVIDENCE:{label}")
    if metadata.evidence_state == "CONFLICTED":
        raise ProjectionBuildError(f"CONFLICTED_EVIDENCE:{label}")
    if metadata.evidence_state == "STALE" or as_of > expires:
        raise ProjectionBuildError(f"STALE_EVIDENCE:{label}")
    if metadata.evidence_state != "PASS":
        raise ProjectionBuildError(f"UNKNOWN_EVIDENCE:{label}:{metadata.evidence_state}")


def _require_unique(values: Iterable[str], *, code: str) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    if duplicates:
        raise ProjectionBuildError(f"{code}:{sorted(duplicates)}")


def _decimal_text(value: Decimal) -> str:
    if not value.is_finite():
        raise ProjectionBuildError("NONFINITE_DERIVED_VALUE")
    if value == 0:
        return "0"
    rendered = format(value.normalize(), "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered


def _csv_bytes(header: tuple[str, ...], rows: Iterable[Iterable[object]]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _team_order(slate: SlateContract) -> tuple[str, ...]:
    return tuple(
        team
        for game in sorted(slate.games, key=lambda item: (item.lock_at, item.game_id))
        for team in (game.away_team, game.home_team)
    )


def _salary_people(slate: SlateContract) -> dict[str, SalaryPlayer]:
    result: dict[str, SalaryPlayer] = {}
    for player in slate.players:
        current = result.get(player.underlying_id)
        if current is None or (slate.mode is EngineMode.SHOWDOWN and player.role == "FLEX"):
            result[player.underlying_id] = player
    return result


def _validate_identities(
    slate: SlateContract,
    team_source: TeamSource,
    player_source: PlayerSource,
    identity_map: ProjectionIdentityMap,
) -> tuple[dict[str, TeamIdentityMapping], dict[str, tuple[PlayerIdentityMapping, SalaryPlayer]]]:
    for label, state in (
        (f"team:{row.provider_team_id}", row.evidence_state)
        for row in identity_map.team_mappings
    ):
        if state != "PASS":
            raise ProjectionBuildError(f"IDENTITY_EVIDENCE_NOT_PASS:{label}:{state}")
    for label, state in (
        (f"player:{row.provider_player_id}", row.evidence_state)
        for row in identity_map.player_mappings
    ):
        if state != "PASS":
            raise ProjectionBuildError(f"IDENTITY_EVIDENCE_NOT_PASS:{label}:{state}")
    for mapping in (*identity_map.team_mappings, *identity_map.player_mappings):
        if mapping.match_method != "EXACT":
            raise ProjectionBuildError(
                f"FUZZY_IDENTITY_FORBIDDEN:{getattr(mapping, 'provider_player_id', getattr(mapping, 'provider_team_id', 'unknown'))}:{mapping.match_method}"
            )

    _require_unique(
        (row.provider_team_id for row in team_source.records),
        code="AMBIGUOUS_TEAM_SOURCE_ID",
    )
    _require_unique(
        (row.provider_player_id for row in player_source.records),
        code="AMBIGUOUS_PLAYER_SOURCE_ID",
    )
    _require_unique(
        (row.provider_team_id for row in identity_map.team_mappings),
        code="DUPLICATE_TEAM_IDENTITY",
    )
    _require_unique(
        (row.team for row in identity_map.team_mappings),
        code="AMBIGUOUS_TEAM_IDENTITY",
    )
    _require_unique(
        (row.provider_player_id for row in identity_map.player_mappings),
        code="DUPLICATE_PLAYER_IDENTITY",
    )
    _require_unique(
        (row.dk_id for row in identity_map.player_mappings),
        code="DUPLICATE_DK_IDENTITY",
    )
    _require_unique(
        (row.underlying_id for row in identity_map.player_mappings),
        code="AMBIGUOUS_UNDERLYING_IDENTITY",
    )

    slate_teams = set(_team_order(slate))
    games_by_team = {
        team: game.game_id
        for game in slate.games
        for team in (game.away_team, game.home_team)
    }
    teams_by_provider = {row.provider_team_id: row for row in identity_map.team_mappings}
    if {row.team for row in identity_map.team_mappings} != slate_teams:
        raise ProjectionBuildError("TEAM_IDENTITY_COVERAGE_MISMATCH")
    if set(teams_by_provider) != {row.provider_team_id for row in team_source.records}:
        raise ProjectionBuildError("TEAM_SOURCE_IDENTITY_COVERAGE_MISMATCH")
    for mapping in identity_map.team_mappings:
        if games_by_team.get(mapping.team) != mapping.game_id:
            raise ProjectionBuildError(f"TEAM_GAME_IDENTITY_CONFLICT:{mapping.team}")
    for record in team_source.records:
        mapping = teams_by_provider[record.provider_team_id]
        if record.game_id != mapping.game_id:
            raise ProjectionBuildError(
                f"TEAM_SOURCE_GAME_CONFLICT:{record.provider_team_id}"
            )

    salary_by_id = {player.dk_id: player for player in slate.players}
    salary_people = _salary_people(slate)
    source_by_provider = {row.provider_player_id: row for row in player_source.records}
    mappings_by_provider = {
        row.provider_player_id: row for row in identity_map.player_mappings
    }
    if set(source_by_provider) != set(mappings_by_provider):
        raise ProjectionBuildError("PLAYER_IDENTITY_COVERAGE_MISMATCH")
    mapped_people = {row.underlying_id for row in identity_map.player_mappings}
    if not mapped_people <= set(salary_people):
        raise ProjectionBuildError(
            "SALARY_PERSON_IDENTITY_COVERAGE_MISMATCH:mapped people absent from the "
            f"salary bytes:{sorted(mapped_people - set(salary_people))[:10]}"
        )
    # A person may be absent from the identity map only when the salary bytes
    # themselves flag him unable to play, which the availability contract already
    # makes unselectable. Re-derived from those bytes rather than trusted from the
    # package, so an upstream drop cannot widen silently.
    selectable_unmapped = sorted(
        (set(salary_people) - mapped_people) - unavailable_people(slate.players)
    )
    if selectable_unmapped:
        raise ProjectionBuildError(
            "SALARY_PERSON_IDENTITY_COVERAGE_MISMATCH:selectable people with no "
            f"identity:{selectable_unmapped[:10]}"
        )

    resolved: dict[str, tuple[PlayerIdentityMapping, SalaryPlayer]] = {}
    for provider_id, source in source_by_provider.items():
        mapping = mappings_by_provider[provider_id]
        salary_player = salary_by_id.get(mapping.dk_id)
        if salary_player is None:
            raise ProjectionBuildError(f"DK_IDENTITY_MISSING:{mapping.dk_id}")
        team_mapping = teams_by_provider.get(mapping.provider_team_id)
        if team_mapping is None or source.provider_team_id != mapping.provider_team_id:
            raise ProjectionBuildError(f"PLAYER_TEAM_PROVIDER_CONFLICT:{provider_id}")
        if mapping.team != team_mapping.team or mapping.team != salary_player.team:
            raise ProjectionBuildError(f"PLAYER_TEAM_IDENTITY_CONFLICT:{provider_id}")
        if mapping.position != source.position or mapping.position != salary_player.position:
            raise ProjectionBuildError(f"PLAYER_POSITION_IDENTITY_CONFLICT:{provider_id}")
        if mapping.underlying_id != salary_player.underlying_id:
            raise ProjectionBuildError(f"PLAYER_UNDERLYING_IDENTITY_CONFLICT:{provider_id}")
        if slate.mode is EngineMode.SHOWDOWN:
            if mapping.dk_role != "FLEX" or salary_player.role != "FLEX":
                raise ProjectionBuildError(f"SHOWDOWN_ROLE_IDENTITY_CONFLICT:{provider_id}")
        elif mapping.dk_role is not None or salary_player.role is not None:
            raise ProjectionBuildError(f"CLASSIC_ROLE_IDENTITY_CONFLICT:{provider_id}")
        resolved[provider_id] = (mapping, salary_player)
    return teams_by_provider, resolved


_PLAYER_GROUPS: Mapping[str, frozenset[str]] = {
    "qb_attempt_weight": frozenset({"QB"}),
    "carry_weight": frozenset({"QB", "RB", "WR", "TE"}),
    "target_weight": frozenset({"RB", "WR", "TE"}),
    "rushing_td_weight": frozenset({"QB", "RB", "WR", "TE"}),
    "receiving_td_weight": frozenset({"RB", "WR", "TE"}),
}


def _player_rows(
    player_source: PlayerSource,
    resolved: Mapping[str, tuple[PlayerIdentityMapping, SalaryPlayer]],
) -> list[tuple[str, ...]]:
    records_by_team: dict[str, list[tuple[PlayerSourceRecord, PlayerIdentityMapping, SalaryPlayer]]] = defaultdict(list)
    for record in player_source.records:
        mapping, salary_player = resolved[record.provider_player_id]
        history = player_source.metadata.coverage.get("offensive_history_by_person", {})
        # R21 (Ben's ruling 2026-09-12, extended to Classic 2026-09-13) is a rule
        # about the BASIS of a person's role prior: an unresolved or missing
        # history carries a history-derived prior rather than a current fact, and
        # selects with that named.
        #
        # This test used to also require `salary_player.role == "FLEX"`. `role` is
        # a Showdown-only attribute -- it is "CPT" or "FLEX" on a Showdown slate
        # and None on every Classic row, and the identity check above already
        # refuses any Showdown record that is not "FLEX". So that clause was
        # never a position or roster-slot filter at all: it was true for every
        # Showdown record and false for every Classic one, which made it a mode
        # gate that switched R21 off entirely in Classic. On the 2026-09-13 Week 1
        # slate that surfaced as PLAYER_EVIDENCE_NOT_PASS and
        # ZERO_OR_MISSING_SHARE_GROUP, an evidence gate no source could clear in
        # the week when prior-season history is least informative. What bounds the
        # tolerance is the adapter version and the history state below; the role
        # never did.
        basis_unknown = (
            player_source.metadata.coverage.get("adapter_version") == "nflverse_prior_adapter_v2"
            and history.get(salary_player.underlying_id, {}).get("state")
            in {"MISSING_HISTORY", "CURRENT_ROLE_UNKNOWN"}
        )
        if record.evidence_state != "PASS" and not (basis_unknown and record.evidence_state == "UNKNOWN"):
            raise ProjectionBuildError(
                f"PLAYER_EVIDENCE_NOT_PASS:{record.provider_player_id}:{record.evidence_state}"
            )
        records_by_team[mapping.team].append((record, mapping, salary_player))
        for field, eligible_positions in _PLAYER_GROUPS.items():
            if salary_player.position not in eligible_positions and getattr(record, field) != 0:
                raise ProjectionBuildError(
                    f"POSITION_SHARE_CONFLICT:{record.provider_player_id}:{field}"
                )
        if salary_player.position not in {"RB", "WR", "TE"} and (
            record.catch_rate != 0 or record.yards_per_target != 0
        ):
            raise ProjectionBuildError(
                f"POSITION_EFFICIENCY_CONFLICT:{record.provider_player_id}"
            )

    normalized: dict[tuple[str, str], Decimal] = {}
    for team, values in records_by_team.items():
        for field, eligible_positions in _PLAYER_GROUPS.items():
            eligible = [item for item in values if item[2].position in eligible_positions]
            total = sum((getattr(item[0], field) for item in eligible), Decimal("0"))
            history = player_source.metadata.coverage.get("offensive_history_by_person", {})
            # The same mode gate described in `_player_rows` above was copied into
            # this group check. A share group whose every member carries a
            # history-derived basis is legitimately UNKNOWN rather than broken:
            # Miami's entire 2026 quarterback room is new (two transfers with a
            # prior-season row on another team, two with none), so the group's
            # own-team attempt share is genuinely zero.
            unknown_group = any(
                player_source.metadata.coverage.get("adapter_version") == "nflverse_prior_adapter_v2"
                and history.get(item[2].underlying_id, {}).get("state") in {"MISSING_HISTORY", "CURRENT_ROLE_UNKNOWN"}
                for item in eligible
            )
            if not eligible or (total <= 0 and not unknown_group):
                raise ProjectionBuildError(f"ZERO_OR_MISSING_SHARE_GROUP:{team}:{field}")
            for record, _mapping, _salary in values:
                normalized[(record.provider_player_id, field)] = (
                    getattr(record, field) / total
                    if record.position in eligible_positions and total > 0
                    else Decimal("0")
                )

    rows: list[tuple[str, ...]] = []
    for record in sorted(
        player_source.records,
        key=lambda item: int(resolved[item.provider_player_id][0].dk_id),
    ):
        mapping, _salary_player = resolved[record.provider_player_id]
        rows.append(
            (
                mapping.dk_id,
                mapping.team,
                mapping.position,
                _decimal_text(normalized[(record.provider_player_id, "qb_attempt_weight")]),
                _decimal_text(normalized[(record.provider_player_id, "carry_weight")]),
                _decimal_text(normalized[(record.provider_player_id, "target_weight")]),
                _decimal_text(record.catch_rate),
                _decimal_text(record.yards_per_target),
                _decimal_text(normalized[(record.provider_player_id, "rushing_td_weight")]),
                _decimal_text(normalized[(record.provider_player_id, "receiving_td_weight")]),
                _decimal_text(record.role_capacity),
                record.evidence_state,
            )
        )
    return rows


def _team_rows(
    slate: SlateContract,
    team_source: TeamSource,
    teams_by_provider: Mapping[str, TeamIdentityMapping],
    *,
    as_of: datetime,
) -> list[tuple[str, ...]]:
    by_team: dict[str, TeamSourceRecord] = {}
    for record in team_source.records:
        if record.evidence_state != "PASS":
            raise ProjectionBuildError(
                f"TEAM_EVIDENCE_NOT_PASS:{record.provider_team_id}:{record.evidence_state}"
            )
        observed = record.market_observed_at.astimezone(timezone.utc)
        if observed > as_of:
            raise ProjectionBuildError(f"FUTURE_MARKET_EVIDENCE:{record.provider_team_id}")
        team = teams_by_provider[record.provider_team_id].team
        by_team[team] = record
    rows: list[tuple[str, ...]] = []
    for team in _team_order(slate):
        record = by_team[team]
        rows.append(
            (
                team,
                record.game_id,
                _decimal_text(record.plays_mean),
                _decimal_text(record.pass_rate),
                _decimal_text(record.pass_yards_per_attempt),
                _decimal_text(record.rush_yards_per_attempt),
                _decimal_text(record.touchdowns_mean),
                _decimal_text(record.field_goals_mean),
                _decimal_text(record.turnovers_mean),
                _decimal_text(record.sacks_allowed_mean),
                _decimal_text(record.uncertainty),
                _decimal_text(record.market_total),
                _decimal_text(record.market_spread),
                record.market_observed_at.isoformat(),
                record.weather_state,
                record.era,
            )
        )
    return rows


def _dependency_bindings(
    metadata: ArtifactMetadata, extra: Mapping[str, str] | None = None
) -> dict[str, str]:
    """The artifact hashes this source was itself derived from.

    Only what the source recorded. `priors.py` writes the contributing frozen
    artifacts into its coverage, and the identity map binds the exact salary
    artifact it was frozen against. Nothing is inferred: an unrecorded
    dependency stays unrecorded rather than being invented here.
    """

    bindings: dict[str, str] = {}
    contributing = metadata.coverage.get("contributing_artifacts")
    if isinstance(contributing, dict):
        for name, digest in contributing.items():
            value = str(digest).strip().lower()
            if len(value) == 64 and all(
                character in "0123456789abcdef" for character in value
            ):
                bindings[str(name)] = value
    for name, digest in dict(extra or {}).items():
        bindings[name] = str(digest).strip().lower()
    return bindings


def _archived_relative_path(digest: str, source: Path) -> str:
    """A package-relative POSIX path for one archived source.

    The name is the content hash, so nothing of the attachment's own name
    survives into the package. An unusual or absent extension is not an error:
    the bytes still archive, under a neutral suffix.
    """

    suffix = source.suffix.lower()
    if len(suffix) > 6 or not suffix[1:].isalnum():
        suffix = ".bin"
    return f"{SOURCES_DIRNAME}/{digest}{suffix}"


def _ledger_entry(
    *,
    archived_path: str,
    digest: str,
    metadata: ArtifactMetadata,
    coverage: dict[str, object],
    scope: EvidenceScope,
    transformation_version: str,
    depends_on: Mapping[str, str],
) -> dict[str, object]:
    return {
        "artifact_id": digest,
        "path": archived_path,
        "source_uri": metadata.source_uri,
        "captured_at": metadata.captured_at.isoformat(),
        "observed_at": metadata.observed_at.isoformat(),
        "expires_at": metadata.expires_at.isoformat(),
        "license_decision": metadata.license_decision,
        "parser_version": metadata.parser_version,
        "evidence_state": metadata.evidence_state,
        "evidence_scope": scope.value,
        "transformation_version": transformation_version,
        "depends_on": dict(sorted(depends_on.items())),
        "coverage": coverage,
    }


def _canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, default=str) + "\n"
    ).encode("utf-8")


_SCOPE_CONTRACTS: Mapping[EvidenceScope, tuple[type[BaseModel], str]] = {
    EvidenceScope.TEAM_PRIOR: (TeamSource, "TEAM_SOURCE_INVALID"),
    EvidenceScope.PLAYER_PRIOR: (PlayerSource, "PLAYER_SOURCE_INVALID"),
    EvidenceScope.IDENTITY_MAP: (ProjectionIdentityMap, "IDENTITY_MAP_INVALID"),
}


def _archived_metadata(
    package_dir: Path, ledger, scope: EvidenceScope
) -> ArtifactMetadata:
    """Re-read one archived source's own metadata out of the package.

    The DraftKings salary CSV carries no metadata of its own; its recorded
    provenance lives in the identity map's `salary_artifact` block, which is
    where this reads it from.
    """

    if scope is EvidenceScope.SLATE_GEOMETRY:
        identity_entry = next(
            (
                entry
                for entry in ledger.entries
                if entry.evidence_scope is EvidenceScope.IDENTITY_MAP
            ),
            None,
        )
        if identity_entry is None:
            raise ProjectionBuildError("ARCHIVED_IDENTITY_MAP_MISSING:salary_provenance")
        identities = _load_contract(
            package_dir / identity_entry.path, ProjectionIdentityMap, "IDENTITY_MAP_INVALID"
        )
        return identities.salary_artifact
    model, code = _SCOPE_CONTRACTS[scope]
    entry = next(
        (item for item in ledger.entries if item.evidence_scope is scope), None
    )
    if entry is None:
        raise ProjectionBuildError(f"ARCHIVED_SOURCE_MISSING:{scope.value}")
    contract = _load_contract(package_dir / entry.path, model, code)
    return contract.metadata


def verify_projection_package(
    package_dir: str | Path,
    *,
    at: datetime,
    expected_outputs: Mapping[str, str] | None = None,
) -> object:
    """Re-verify a published package at an arbitrary clock, sources and all.

    R08's acceptance has two halves. `validate_source_ledger` covers the first:
    the ledger carries each source's expiry and re-evaluates it at the clock it
    is handed. This covers the second. The ledger is a plain JSON file, so a
    consumer could otherwise write a newer `expires_at` into it and revalidate,
    which is exactly "a new market timestamp renewing old player evidence".
    Every declared expiry, evidence state and observation time is therefore
    checked back against the archived source's own metadata, whose bytes are
    hash-bound. A forged ledger expiry is refused by the source it claims to
    describe.
    """

    root = Path(package_dir).resolve()
    ledger_path = root / LEDGER_FILENAME
    if not ledger_path.is_file():
        raise ProjectionBuildError(f"PACKAGE_LEDGER_MISSING:{ledger_path}")
    when = _parse_as_of(at)
    outputs = dict(expected_outputs or {})
    if not outputs:
        for name, filename in (
            ("team_projections", TEAM_FILENAME),
            ("player_opportunities", PLAYER_FILENAME),
        ):
            derived_path = root / filename
            if not derived_path.is_file():
                raise ProjectionBuildError(f"PACKAGE_OUTPUT_MISSING:{filename}")
            outputs[name] = sha256_file(derived_path)
    try:
        ledger = validate_source_ledger(
            ledger_path, expected_outputs=outputs, now=when
        )
    except Exception as exc:  # noqa: BLE001 - re-raised under a named code
        raise ProjectionBuildError(f"PACKAGE_LEDGER_INVALID:{exc}") from exc
    if ledger.schema_version != SOURCE_LEDGER_SCHEMA:
        raise ProjectionBuildError(
            f"PACKAGE_LEDGER_SCHEMA_UNSUPPORTED:{ledger.schema_version}"
        )
    # The entry set has to be complete, not merely internally consistent.
    # Checking only the entries that are present makes deleting an expired
    # entry exactly as effective as forging its expiry.
    scopes = [entry.evidence_scope for entry in ledger.entries]
    expected_scopes = sorted(scope.value for scope in INPUT_SCOPES.values())
    if sorted(scope.value for scope in scopes if scope is not None) != expected_scopes:
        raise ProjectionBuildError(
            "PACKAGE_SCOPE_COVERAGE_MISMATCH:expected="
            f"{expected_scopes}:actual="
            f"{sorted(scope.value for scope in scopes if scope is not None)}"
        )
    if sorted(ledger.derived) != sorted(outputs):
        raise ProjectionBuildError(
            f"PACKAGE_DERIVED_COVERAGE_MISMATCH:{sorted(ledger.derived)}"
        )
    for entry in ledger.entries:
        if entry.evidence_scope is None or entry.expires_at is None:
            raise ProjectionBuildError(f"PACKAGE_ENTRY_UNSCOPED:{entry.path}")
        metadata = _archived_metadata(root, ledger, entry.evidence_scope)
        declared = entry.expires_at.astimezone(timezone.utc)
        archived = metadata.expires_at.astimezone(timezone.utc)
        if declared != archived:
            raise ProjectionBuildError(
                f"LEDGER_EXPIRY_DISAGREES_WITH_ARCHIVED_SOURCE:"
                f"{entry.evidence_scope.value}:ledger={declared.isoformat()}"
                f":archived={archived.isoformat()}"
            )
        if (entry.evidence_state or "") != metadata.evidence_state:
            raise ProjectionBuildError(
                f"LEDGER_EVIDENCE_STATE_DISAGREES_WITH_ARCHIVED_SOURCE:"
                f"{entry.evidence_scope.value}"
            )
        if entry.observed_at is not None and entry.observed_at.astimezone(
            timezone.utc
        ) != metadata.observed_at.astimezone(timezone.utc):
            raise ProjectionBuildError(
                f"LEDGER_OBSERVATION_DISAGREES_WITH_ARCHIVED_SOURCE:"
                f"{entry.evidence_scope.value}"
            )
        if entry.source_uri != metadata.source_uri:
            raise ProjectionBuildError(
                f"LEDGER_SOURCE_URI_DISAGREES_WITH_ARCHIVED_SOURCE:"
                f"{entry.evidence_scope.value}"
            )
    return ledger


def build_projection_package(
    *,
    salaries: str | Path,
    salary_sha256: str,
    team_source: str | Path,
    team_source_sha256: str,
    player_source: str | Path,
    player_source_sha256: str,
    identity_map: str | Path,
    identity_map_sha256: str,
    as_of: str | datetime,
    output_dir: str | Path,
) -> ProjectionPackage:
    """Build and atomically publish deterministic prior-only model inputs."""

    final_dir = Path(output_dir).resolve()
    if final_dir.exists():
        raise ProjectionBuildError(f"OUTPUT_PACKAGE_EXISTS:{final_dir}")
    paths = {
        "salary": Path(salaries).resolve(),
        "team_source": Path(team_source).resolve(),
        "player_source": Path(player_source).resolve(),
        "identity_map": Path(identity_map).resolve(),
    }
    expected_hashes = {
        "salary": salary_sha256,
        "team_source": team_source_sha256,
        "player_source": player_source_sha256,
        "identity_map": identity_map_sha256,
    }
    input_hashes = {
        name: _require_hash(path, expected_hashes[name], name)
        for name, path in paths.items()
    }
    when = _parse_as_of(as_of)
    slate = parse_salaries(paths["salary"])
    teams = _load_contract(paths["team_source"], TeamSource, "TEAM_SOURCE_INVALID")
    players = _load_contract(
        paths["player_source"], PlayerSource, "PLAYER_SOURCE_INVALID"
    )
    identities = _load_contract(
        paths["identity_map"], ProjectionIdentityMap, "IDENTITY_MAP_INVALID"
    )
    _validate_metadata(
        teams.metadata,
        expected_parser=TEAM_SOURCE_PARSER,
        as_of=when,
        label="team_source",
    )
    _validate_metadata(
        players.metadata,
        expected_parser=PLAYER_SOURCE_PARSER,
        as_of=when,
        label="player_source",
    )
    _validate_metadata(
        identities.metadata,
        expected_parser=IDENTITY_MAP_PARSER,
        as_of=when,
        label="identity_map",
    )
    _validate_metadata(
        identities.salary_artifact,
        expected_parser=DK_PARSER_VERSION,
        as_of=when,
        label="salary",
    )
    if identities.salary_artifact.artifact_id != input_hashes["salary"]:
        raise ProjectionBuildError("SALARY_HASH_IDENTITY_CONFLICT")
    teams_by_provider, resolved = _validate_identities(
        slate, teams, players, identities
    )
    team_rows = _team_rows(slate, teams, teams_by_provider, as_of=when)
    player_rows = _player_rows(players, resolved)
    team_bytes = _csv_bytes(TEAM_COLUMNS, team_rows)
    player_bytes = _csv_bytes(PLAYER_COLUMNS, player_rows)
    derived_hashes = {
        "team_projections": sha256_bytes(team_bytes),
        "player_opportunities": sha256_bytes(player_bytes),
    }
    team_count = len(team_rows)
    person_count = len(player_rows)
    metadata_by_input: dict[str, ArtifactMetadata] = {
        "salary": identities.salary_artifact,
        "team_source": teams.metadata,
        "player_source": players.metadata,
        "identity_map": identities.metadata,
    }
    archived_sources = {
        name: _archived_relative_path(input_hashes[name], paths[name])
        for name in paths
    }
    ledger = {
        "schema_version": SOURCE_LEDGER_SCHEMA,
        "entries": [
            _ledger_entry(
                archived_path=archived_sources["salary"],
                digest=input_hashes["salary"],
                metadata=identities.salary_artifact,
                scope=INPUT_SCOPES["salary"],
                transformation_version="IDENTITY_AND_SLATE_GEOMETRY_ONLY_DK_CSV_V1",
                # The operator download is a root source. It is bound to the
                # identity map from the other direction, below.
                depends_on=_dependency_bindings(identities.salary_artifact),
                coverage={
                    **identities.salary_artifact.coverage,
                    "mode": slate.mode.value,
                    "salary_rows": len(slate.players),
                    "underlying_people": len(_salary_people(slate)),
                    "appg_policy": "HASHED_RAW_ONLY_NOT_USED_NUMERICALLY",
                },
            ),
            _ledger_entry(
                archived_path=archived_sources["team_source"],
                digest=input_hashes["team_source"],
                metadata=teams.metadata,
                scope=INPUT_SCOPES["team_source"],
                transformation_version="DIRECT_BOUNDED_TEAM_FIELDS_V1",
                depends_on=_dependency_bindings(teams.metadata),
                coverage={
                    **teams.metadata.coverage,
                    "accepted_records": team_count,
                    "expected_teams": team_count,
                    "as_of": when.isoformat(),
                },
            ),
            _ledger_entry(
                archived_path=archived_sources["player_source"],
                digest=input_hashes["player_source"],
                metadata=players.metadata,
                scope=INPUT_SCOPES["player_source"],
                transformation_version="POSITION_MASKED_TEAM_WEIGHT_NORMALIZATION_V1",
                depends_on=_dependency_bindings(players.metadata),
                coverage={
                    **players.metadata.coverage,
                    "accepted_records": person_count,
                    "expected_people": person_count,
                    "as_of": when.isoformat(),
                },
            ),
            _ledger_entry(
                archived_path=archived_sources["identity_map"],
                digest=input_hashes["identity_map"],
                metadata=identities.metadata,
                scope=INPUT_SCOPES["identity_map"],
                transformation_version="FROZEN_EXACT_PROVIDER_TO_DK_IDENTITY_V1",
                depends_on=_dependency_bindings(
                    identities.metadata,
                    {"salary": identities.salary_artifact.artifact_id},
                ),
                coverage={
                    **identities.metadata.coverage,
                    "accepted_team_mappings": len(identities.team_mappings),
                    "accepted_player_mappings": len(identities.player_mappings),
                    "match_method": "EXACT_ONLY",
                    "showdown_output_role": "FLEX" if slate.mode is EngineMode.SHOWDOWN else None,
                },
            ),
        ],
        "derived": derived_hashes,
    }
    ledger_bytes = _canonical_json_bytes(ledger)
    # The package's binding expiry is the earliest of its consumed sources,
    # evaluated by the one shared rule. It is never widened here: a source that
    # has already expired at `as_of` was refused by `_validate_metadata` above.
    binding = earliest_source_freshness(
        (
            SourceFreshnessContract(
                label=f"{INPUT_SCOPES[name].value}:{name}",
                expires_at=metadata_by_input[name].expires_at,
                basis=str(
                    metadata_by_input[name].coverage.get("expiry_basis", "")
                    or "UNRECORDED"
                ),
                observed_at=metadata_by_input[name].observed_at,
            )
            for name in sorted(metadata_by_input)
        ),
        at=when,
    )

    for name, path in paths.items():
        if sha256_file(path) != input_hashes[name]:
            raise ProjectionBuildError(f"INPUT_CHANGED_DURING_BUILD:{name}")

    final_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{final_dir.name}.tmp-", dir=final_dir.parent))
    published = False
    try:
        team_path = staging / TEAM_FILENAME
        player_path = staging / PLAYER_FILENAME
        ledger_path = staging / LEDGER_FILENAME
        team_path.write_bytes(team_bytes)
        player_path.write_bytes(player_bytes)
        ledger_path.write_bytes(ledger_bytes)
        archive_root = staging / SOURCES_DIRNAME
        archive_root.mkdir(parents=True, exist_ok=False)
        for name, relative in sorted(archived_sources.items()):
            archived = staging / relative
            archived.write_bytes(paths[name].read_bytes())
            if sha256_file(archived) != input_hashes[name]:
                raise ProjectionBuildError(f"ARCHIVED_SOURCE_HASH_MISMATCH:{name}")
        if sha256_file(team_path) != derived_hashes["team_projections"]:
            raise ProjectionBuildError("DERIVED_HASH_MISMATCH:team_projections")
        if sha256_file(player_path) != derived_hashes["player_opportunities"]:
            raise ProjectionBuildError("DERIVED_HASH_MISMATCH:player_opportunities")
        load_opportunity_model(
            slate, team_path, player_path,
            allow_empty_groups=bool(players.metadata.coverage.get("offensive_history_by_person")),
        )
        validate_source_ledger(
            ledger_path,
            expected_outputs=derived_hashes,
            now=when,
        )
        for name, path in paths.items():
            if sha256_file(path) != input_hashes[name]:
                raise ProjectionBuildError(f"INPUT_CHANGED_BEFORE_PUBLISH:{name}")
        os.replace(staging, final_dir)
        published = True
    finally:
        if not published and staging.exists():
            shutil.rmtree(staging)

    try:
        final_hashes = {
            "team_projections": sha256_file(final_dir / TEAM_FILENAME),
            "player_opportunities": sha256_file(final_dir / PLAYER_FILENAME),
            "source_ledger": sha256_file(final_dir / LEDGER_FILENAME),
        }
        if final_hashes["team_projections"] != derived_hashes["team_projections"]:
            raise ProjectionBuildError("PUBLISHED_HASH_MISMATCH:team_projections")
        if final_hashes["player_opportunities"] != derived_hashes["player_opportunities"]:
            raise ProjectionBuildError("PUBLISHED_HASH_MISMATCH:player_opportunities")
        for name, relative in sorted(archived_sources.items()):
            if sha256_file(final_dir / relative) != input_hashes[name]:
                raise ProjectionBuildError(f"PUBLISHED_ARCHIVE_MISMATCH:{name}")
    except Exception:
        if final_dir.is_dir():
            shutil.rmtree(final_dir)
        raise
    return ProjectionPackage(
        output_dir=str(final_dir),
        team_projections=str(final_dir / TEAM_FILENAME),
        player_opportunities=str(final_dir / PLAYER_FILENAME),
        source_ledger=str(final_dir / LEDGER_FILENAME),
        hashes=final_hashes,
        input_hashes=input_hashes,
        ledger_schema_version=SOURCE_LEDGER_SCHEMA,
        expires_at=binding.expires_at.astimezone(timezone.utc).isoformat(),
        expiry_basis=f"{binding.label}:{binding.basis}",
        archived_sources=dict(sorted(archived_sources.items())),
    )
