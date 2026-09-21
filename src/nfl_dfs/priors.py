"""Deterministic nflverse-to-prior adapter for DraftKings NFL slates.

R01 closure. The `project` command already validates and transforms frozen prior
artifacts; nothing produced them. This module does, from approved public
nflverse artifacts only, with every emitted number traceable to fetched bytes
through a documented transformation.

Two phases, because DraftKings and nflverse share no identifier. Phase one
(`propose`) fetches and freezes the raw artifacts and emits an identity
*proposal*: a normalized name/team/position crosswalk that is explicitly not
authoritative. Phase two (`freeze`) consumes an operator-reviewed decision file
and only then writes `match_method="EXACT"`, which is the only value
`projection.py` accepts. That gate exists because a normalized crosswalk match
is a proposal until a human has reviewed and frozen it.

What this module is not: it is not a projection model, and its output is not EV,
ROI, win probability, cash probability, calibrated ownership, or edge. It is a
prior-only opportunity-share package.
"""

from __future__ import annotations

import csv
import io
import json
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_EVEN
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from .contracts import (
    EngineMode,
    SalaryPlayer,
    SlateContract,
    unavailable_people,
)
from .dk import PARSER_VERSION as DK_PARSER_VERSION
from .dk import parse_salaries
from .hashing import sha256_bytes, sha256_file
from .projection import (
    IDENTITY_MAP_PARSER,
    IDENTITY_MAP_SCHEMA,
    PLAYER_SOURCE_PARSER,
    PLAYER_SOURCE_SCHEMA,
    TEAM_SOURCE_PARSER,
    TEAM_SOURCE_SCHEMA,
)
from .sources import (
    SourcePolicyError,
    fetch_public_artifact,
    validate_source_reference_policy,
)
from .venues import (
    RETRACTABLE_ROOF_HOME_TEAMS,
    resolve_blank_roof,
    roof_history,
    season_window,
)


ADAPTER_VERSION = "nflverse_prior_adapter_v2"
# v2 adds `markets[].venue_roof_history` and `venue_roof_history_seasons`, the
# counts the weather stage resolves a retractable venue's blank roof from. A v1
# proposal still reads correctly: the keys are absent, the counts are empty, and
# the blank roof asks for a capture exactly as it did before.
PROPOSAL_SCHEMA = "nfl_prior_identity_proposal_v2"
MANIFEST_SCHEMA = "nfl_prior_source_manifest_v1"
PACKAGE_SCHEMA = "nfl_prior_package_v1"

RAW_DIRNAME = "raw"
MANIFEST_FILENAME = "source_manifest.json"
PROPOSAL_FILENAME = "identity_proposals.json"
REVIEW_FILENAME = "identity_review.csv"
TEAM_PRIOR_FILENAME = "team_prior.json"
PLAYER_PRIOR_FILENAME = "player_prior.json"
IDENTITY_MAP_FILENAME = "identity_map.json"
PACKAGE_FILENAME = "prior_package.json"

REVIEW_COLUMNS = (
    "DK_ID",
    "DK_NAME",
    "DK_TEAM",
    "DK_POSITION",
    "PROPOSED_PROVIDER_PLAYER_ID",
    "PROPOSED_PROVIDER_NAME",
    "PROPOSED_PROVIDER_TEAM",
    "PROPOSED_PROVIDER_STATUS",
    "MATCH_METHOD",
    "DECISION",
    "REVIEWED_PROVIDER_PLAYER_ID",
)
ACCEPTED_DECISION = "ACCEPT"
# Operator token for a person with no identity in the approved artifacts who the
# availability contract already makes unselectable. See `_resolve_reviewed`.
EXCLUDED_UNRESOLVED_DECISION = "EXCLUDE_UNRESOLVED_UNAVAILABLE"
QUANTUM = Decimal("0.000001")

# Positions whose opportunity weights are structurally zero under the model
# contract in projection.py. Reported, never silently normalized.
NON_OPPORTUNITY_POSITIONS = frozenset({"K", "DST"})
RECEIVING_POSITIONS = frozenset({"RB", "WR", "TE"})

_NAME_SUFFIXES = frozenset({"JR", "SR", "II", "III", "IV", "V"})
_ROOF_WEATHER = {
    "dome": "INDOOR",
    "closed": "ROOF_CLOSED",
    "open": "ROOF_OPEN",
}
_OPERATOR_WEATHER_STATES = frozenset(
    {"CLEAR", "INDOOR_OR_CLEAR", "MIXED", "RAIN", "SNOW", "WIND"}
)


class PriorsBuildError(ValueError):
    """A named fail-closed prior-adapter error."""


# --------------------------------------------------------------------------- #
# Source specifications
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class NflverseSource:
    """One approved public artifact and the real staleness of its contents."""

    name: str
    url: str
    parser_version: str
    expires_after: timedelta
    staleness_basis: str
    required_columns: tuple[str, ...]
    license_decision: str = "PERMITTED_REPOSITORY_LICENSE"


_NFLDATA_RAW = "https://raw.githubusercontent.com/nflverse/nfldata/master/data"
_NFLVERSE_RELEASE = "https://github.com/nflverse/nflverse-data/releases/download"


def source_specifications(*, season: int, prior_season: int) -> tuple[NflverseSource, ...]:
    """Return the artifacts this adapter reads, with per-source expiry."""

    return (
        NflverseSource(
            name="games",
            url=f"{_NFLDATA_RAW}/games.csv",
            parser_version="nfldata_games_csv_v1",
            # Market lines move continuously; this file carries no book and no
            # publisher timestamp, so it is only good for the rest of the day.
            expires_after=timedelta(hours=12),
            staleness_basis="MARKET_LINE_MOVES_INTRADAY",
            required_columns=(
                "game_id",
                "season",
                "game_type",
                "week",
                "gameday",
                "away_team",
                "home_team",
                "spread_line",
                "total_line",
                "roof",
            ),
        ),
        NflverseSource(
            name="teams",
            url=f"{_NFLDATA_RAW}/teams.csv",
            parser_version="nfldata_teams_csv_v1",
            # A season's abbreviation crosswalk is fixed once the season starts.
            expires_after=timedelta(days=30),
            staleness_basis="SEASON_TEAM_CROSSWALK_IS_STATIC",
            required_columns=("season", "team", "full", "nickname", "draft_kings"),
        ),
        NflverseSource(
            name="team_stats",
            url=f"{_NFLVERSE_RELEASE}/stats_team/stats_team_week_{prior_season}.csv",
            parser_version="nflverse_stats_team_week_csv_v1",
            # A completed season is immutable apart from occasional stat
            # corrections, which nflverse republishes.
            expires_after=timedelta(days=7),
            staleness_basis="COMPLETED_SEASON_SUBJECT_TO_STAT_CORRECTIONS",
            required_columns=(
                "season",
                "week",
                "team",
                "season_type",
                "attempts",
                "carries",
                "sacks_suffered",
                "passing_yards",
                "rushing_yards",
                "passing_tds",
                "rushing_tds",
                "passing_interceptions",
                "fumbles_lost_total",
                "fg_made",
            ),
        ),
        NflverseSource(
            name="player_stats",
            url=f"{_NFLVERSE_RELEASE}/stats_player/stats_player_week_{prior_season}.csv",
            parser_version="nflverse_stats_player_week_csv_v1",
            expires_after=timedelta(days=7),
            staleness_basis="COMPLETED_SEASON_SUBJECT_TO_STAT_CORRECTIONS",
            required_columns=(
                "player_id",
                "player_display_name",
                "position",
                "season",
                "week",
                "season_type",
                "team",
                "attempts",
                "carries",
                "receptions",
                "targets",
                "receiving_yards",
                "rushing_tds",
                "receiving_tds",
            ),
        ),
        NflverseSource(
            name="snap_counts",
            url=f"{_NFLVERSE_RELEASE}/snap_counts/snap_counts_{prior_season}.csv",
            parser_version="nflverse_snap_counts_csv_v1",
            expires_after=timedelta(days=7),
            staleness_basis="COMPLETED_SEASON_SUBJECT_TO_STAT_CORRECTIONS",
            required_columns=(
                "season",
                "week",
                "game_type",
                "player",
                "pfr_player_id",
                "position",
                "team",
                "offense_snaps",
                "offense_pct",
            ),
        ),
        NflverseSource(
            name="players",
            url=f"{_NFLVERSE_RELEASE}/players/players.csv",
            parser_version="nflverse_players_csv_v1",
            # nflverse's canonical person index. It changes when a player signs
            # or is released, so it is a reference file rather than a live
            # roster, and it is only ever a fallback candidate source here.
            expires_after=timedelta(days=7),
            staleness_basis="CANONICAL_PERSON_INDEX_CHANGES_ON_SIGNINGS",
            required_columns=(
                "gsis_id",
                "display_name",
                "position",
                "latest_team",
                "status",
                "pfr_id",
            ),
        ),
        NflverseSource(
            name="weekly_rosters",
            url=f"{_NFLVERSE_RELEASE}/weekly_rosters/roster_weekly_{season}.csv",
            parser_version="nflverse_roster_weekly_csv_v1",
            # Rosters churn daily in season; this is the identity anchor, so it
            # gets the shortest non-market expiry.
            expires_after=timedelta(hours=24),
            staleness_basis="IN_SEASON_ROSTER_CHURN_IS_DAILY",
            required_columns=(
                "season",
                "week",
                "team",
                "position",
                "full_name",
                "gsis_id",
                "pfr_id",
                "status",
            ),
        ),
        NflverseSource(
            name="depth_charts",
            url=f"{_NFLVERSE_RELEASE}/depth_charts/depth_charts_{season}.csv",
            parser_version="nflverse_depth_charts_csv_v1",
            # P7. Measured on the published 2026 artifact on 2026-09-21: 190
            # snapshots, two on most days (2026-09-20 carries 06:02:02Z and
            # 12:14:30Z). 36 hours is the expiry the producer script
            # `make_offensive_role_evidence.py` has always used, kept rather
            # than tightened so the two paths cannot disagree about whether the
            # same capture is fresh.
            #
            # Expiry is not the interesting staleness here and must not be read
            # as a freshness guarantee. The last chart before a 13:00 ET Sunday
            # lock is 08:14 ET and official inactives publish about 11:30 ET, so
            # a perfectly unexpired chart is still blind to the only news that
            # decides who starts. That gap is what effective depth rank exists
            # to close; see `depth_roles.py`.
            expires_after=timedelta(hours=36),
            staleness_basis="DEPTH_CHART_REPUBLISHED_ABOUT_TWICE_DAILY_NEVER_BETWEEN_INACTIVES_AND_LOCK",
            required_columns=(
                "dt",
                "team",
                "player_name",
                "espn_id",
                "gsis_id",
                "pos_grp_id",
                "pos_grp",
                "pos_id",
                "pos_name",
                "pos_abb",
                "pos_slot",
                "pos_rank",
            ),
        ),
    )


# --------------------------------------------------------------------------- #
# Canonical serialization
# --------------------------------------------------------------------------- #


def decimal_text(value: Decimal) -> str:
    """Render a Decimal as a stable plain JSON number with no exponent."""

    if not value.is_finite():
        raise PriorsBuildError("NONFINITE_DERIVED_VALUE")
    quantized = value.quantize(QUANTUM, rounding=ROUND_HALF_EVEN)
    if quantized == 0:
        return "0"
    rendered = format(quantized, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


def canonical_json_bytes(value: object) -> bytes:
    """Serialize to canonical JSON, emitting Decimals as real JSON numbers.

    `json.dumps(default=str)` would quote every Decimal, and `TeamSourceRecord`
    rejects a quoted number outright. Floats are refused because their repr is
    not a stable contract. Two runs over the same frozen inputs must produce
    byte-identical output, so key order is fixed and rendering is exact.
    """

    buffer = io.StringIO()
    _write_canonical(value, buffer)
    buffer.write("\n")
    return buffer.getvalue().encode("utf-8")


def _write_canonical(value: object, out: io.StringIO) -> None:
    if value is None:
        out.write("null")
    elif isinstance(value, bool):
        out.write("true" if value else "false")
    elif isinstance(value, Decimal):
        out.write(decimal_text(value))
    elif isinstance(value, int):
        out.write(str(value))
    elif isinstance(value, str):
        out.write(json.dumps(value, ensure_ascii=False))
    elif isinstance(value, Mapping):
        out.write("{")
        for index, key in enumerate(sorted(value)):
            if not isinstance(key, str):
                raise PriorsBuildError(f"NON_STRING_JSON_KEY:{key!r}")
            if index:
                out.write(",")
            out.write(json.dumps(key, ensure_ascii=False))
            out.write(":")
            _write_canonical(value[key], out)
        out.write("}")
    elif isinstance(value, (list, tuple)):
        out.write("[")
        for index, item in enumerate(value):
            if index:
                out.write(",")
            _write_canonical(item, out)
        out.write("]")
    elif isinstance(value, float):
        raise PriorsBuildError("FLOAT_IN_DERIVED_OUTPUT")
    else:
        raise PriorsBuildError(f"UNSERIALIZABLE_DERIVED_VALUE:{type(value).__name__}")


def _write_atomic(path: Path, payload: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)
    digest = sha256_file(path)
    if digest != sha256_bytes(payload):
        raise PriorsBuildError(f"WRITTEN_HASH_MISMATCH:{path.name}")
    return digest


# --------------------------------------------------------------------------- #
# Parsing helpers
# --------------------------------------------------------------------------- #


def _parse_timestamp(value: str | datetime, *, label: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError as exc:
            raise PriorsBuildError(f"{label}_INVALID:must be ISO 8601") from exc
    if parsed.tzinfo is None:
        raise PriorsBuildError(f"{label}_INVALID:timezone is required")
    return parsed.astimezone(timezone.utc)


def read_csv_rows(path: Path, required_columns: Sequence[str], *, label: str) -> list[dict[str, str]]:
    """Read a frozen CSV artifact, requiring the columns the adapter joins on."""

    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = tuple(reader.fieldnames or ())
            missing = [column for column in required_columns if column not in fieldnames]
            if missing:
                raise PriorsBuildError(f"SOURCE_COLUMNS_MISSING:{label}:{sorted(missing)}")
            return [row for row in reader if any((value or "").strip() for value in row.values())]
    except OSError as exc:
        raise PriorsBuildError(f"SOURCE_UNREADABLE:{label}:{exc}") from exc


def _decimal_cell(row: Mapping[str, str], column: str, *, label: str) -> Decimal:
    raw = (row.get(column) or "").strip()
    if raw in {"", "NA", "NaN", "null"}:
        return Decimal("0")
    try:
        parsed = Decimal(raw)
    except ArithmeticError as exc:
        raise PriorsBuildError(f"SOURCE_VALUE_NOT_NUMERIC:{label}:{column}:{raw!r}") from exc
    if not parsed.is_finite():
        raise PriorsBuildError(f"SOURCE_VALUE_NOT_FINITE:{label}:{column}")
    return parsed


def _required_decimal(row: Mapping[str, str], column: str, *, label: str) -> Decimal:
    raw = (row.get(column) or "").strip()
    if raw in {"", "NA", "NaN", "null"}:
        raise PriorsBuildError(f"SOURCE_VALUE_ABSENT:{label}:{column}")
    return _decimal_cell(row, column, label=label)


def _bounded(value: Decimal, low: str, high: str, *, label: str) -> Decimal:
    """Enforce a contract bound at the producer rather than deferring to pydantic.

    A value outside the published range means the transformation or the source
    is wrong. Clamping it would hide that, so this fails closed with the value.
    """

    quantized = value.quantize(QUANTUM, rounding=ROUND_HALF_EVEN)
    if quantized < Decimal(low) or quantized > Decimal(high):
        raise PriorsBuildError(
            f"DERIVED_VALUE_OUT_OF_CONTRACT:{label}:{decimal_text(quantized)}"
            f":expected[{low},{high}]"
        )
    return quantized


def _ratio(numerator: Decimal, denominator: Decimal, *, label: str) -> Decimal:
    if denominator <= 0:
        raise PriorsBuildError(f"ZERO_DENOMINATOR:{label}")
    return (numerator / denominator).quantize(QUANTUM, rounding=ROUND_HALF_EVEN)


def normalize_person_name(value: str) -> str:
    """Canonicalize a person name for crosswalk proposal only.

    Case, punctuation and generational suffixes vary between DraftKings and
    nflverse. Collapsing them produces a *candidate* key; a unique hit is still
    a proposal, never a certified identity.
    """

    cleaned = []
    for character in value.upper():
        if character.isalnum() or character == " ":
            cleaned.append(character)
        elif character in "-'.,":
            cleaned.append(" " if character in "-," else "")
        else:
            cleaned.append(" ")
    tokens = [token for token in "".join(cleaned).split() if token]
    while len(tokens) > 2 and tokens[-1] in _NAME_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


# --------------------------------------------------------------------------- #
# Fetch and freeze the raw artifacts
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class FrozenArtifact:
    """A fetched artifact, archived content-addressed inside the package."""

    name: str
    path: Path
    sha256: str
    byte_count: int
    source_uri: str
    captured_at: datetime
    observed_at: datetime
    expires_at: datetime
    license_decision: str
    parser_version: str
    staleness_basis: str
    coverage: dict[str, object]

    def manifest_entry(self, *, package_root: Path) -> dict[str, object]:
        return {
            "name": self.name,
            "artifact_id": self.sha256,
            "relative_path": str(self.path.relative_to(package_root)).replace("\\", "/"),
            "sha256": self.sha256,
            "byte_count": self.byte_count,
            "source_uri": self.source_uri,
            "captured_at": self.captured_at.isoformat(),
            "observed_at": self.observed_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "license_decision": self.license_decision,
            "parser_version": self.parser_version,
            "staleness_basis": self.staleness_basis,
            "coverage": self.coverage,
        }


def freeze_sources(
    specifications: Iterable[NflverseSource],
    *,
    package_root: Path,
    as_of: datetime,
) -> dict[str, FrozenArtifact]:
    """Fetch each approved artifact and archive its raw bytes in the package.

    Retrieval goes through `sources.fetch_public_artifact`, so the host
    allowlist, the license decision and the single permitted GitHub
    release-asset hop all still apply. Nothing here talks to the network
    directly.
    """

    raw_root = package_root / RAW_DIRNAME
    raw_root.mkdir(parents=True, exist_ok=True)
    frozen: dict[str, FrozenArtifact] = {}
    for specification in specifications:
        artifact = fetch_public_artifact(
            specification.url,
            raw_root,
            source=f"NFLVERSE_{specification.name.upper()}",
            license_decision=specification.license_decision,
            parser_version=specification.parser_version,
        )
        path = Path(artifact.path)
        captured = artifact.captured_at.astimezone(timezone.utc)
        if captured > as_of + timedelta(minutes=5):
            raise PriorsBuildError(f"FETCH_CLOCK_AHEAD_OF_AS_OF:{specification.name}")
        rows = read_csv_rows(path, specification.required_columns, label=specification.name)
        if not rows:
            raise PriorsBuildError(f"SOURCE_EMPTY:{specification.name}")
        frozen[specification.name] = FrozenArtifact(
            name=specification.name,
            path=path,
            sha256=artifact.sha256,
            byte_count=artifact.byte_count,
            source_uri=specification.url,
            captured_at=captured,
            # The artifact's content was observed at the moment it was fetched.
            # These files carry no publisher timestamp, so claiming any earlier
            # observation time would be an invention.
            observed_at=captured,
            expires_at=captured + specification.expires_after,
            license_decision=specification.license_decision,
            parser_version=specification.parser_version,
            staleness_basis=specification.staleness_basis,
            coverage={**dict(artifact.coverage), "rows": len(rows)},
        )
    return frozen


def _verify_frozen(frozen: Mapping[str, FrozenArtifact]) -> None:
    for name, artifact in sorted(frozen.items()):
        if not artifact.path.is_file():
            raise PriorsBuildError(f"FROZEN_ARTIFACT_MISSING:{name}:{artifact.path}")
        actual = sha256_file(artifact.path)
        if actual != artifact.sha256:
            raise PriorsBuildError(
                f"FROZEN_ARTIFACT_HASH_MISMATCH:{name}:expected={artifact.sha256}:actual={actual}"
            )


def load_frozen_manifest(package_root: Path) -> dict[str, FrozenArtifact]:
    """Rehydrate the frozen artifacts recorded by a propose run, hash-checked."""

    manifest_path = package_root / MANIFEST_FILENAME
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PriorsBuildError(f"MANIFEST_UNREADABLE:{manifest_path}:{exc}") from exc
    if payload.get("schema_version") != MANIFEST_SCHEMA:
        raise PriorsBuildError(f"MANIFEST_SCHEMA_UNKNOWN:{payload.get('schema_version')!r}")
    frozen: dict[str, FrozenArtifact] = {}
    for entry in payload.get("artifacts", []):
        path = (package_root / entry["relative_path"]).resolve()
        frozen[entry["name"]] = FrozenArtifact(
            name=entry["name"],
            path=path,
            sha256=entry["sha256"],
            byte_count=int(entry["byte_count"]),
            source_uri=entry["source_uri"],
            captured_at=_parse_timestamp(entry["captured_at"], label="CAPTURED_AT"),
            observed_at=_parse_timestamp(entry["observed_at"], label="OBSERVED_AT"),
            expires_at=_parse_timestamp(entry["expires_at"], label="EXPIRES_AT"),
            license_decision=entry["license_decision"],
            parser_version=entry["parser_version"],
            staleness_basis=entry["staleness_basis"],
            coverage=dict(entry.get("coverage") or {}),
        )
    if not frozen:
        raise PriorsBuildError("MANIFEST_HAS_NO_ARTIFACTS")
    _verify_frozen(frozen)
    return frozen


def _artifact_metadata(
    sources: Sequence[FrozenArtifact],
    *,
    parser_version: str,
    coverage: dict[str, object],
    horizon: datetime,
) -> dict[str, object]:
    """Compose emitted-artifact metadata from the artifacts that fed it.

    Expiry is the earliest expiry of any contributing source, capped at the
    game's lock time: a prior whose least durable input has gone stale is
    stale, and no prior for this game means anything after kickoff.
    """

    captured = max(item.captured_at for item in sources)
    observed = max(item.observed_at for item in sources)
    expires = min([item.expires_at for item in sources] + [horizon])
    if expires < observed:
        raise PriorsBuildError(
            f"SOURCE_EXPIRES_BEFORE_OBSERVATION:{parser_version}:{expires.isoformat()}"
        )
    return {
        "source_uri": sources[0].source_uri,
        "captured_at": captured.isoformat(),
        "observed_at": observed.isoformat(),
        "expires_at": expires.isoformat(),
        "license_decision": "PERMITTED_REPOSITORY_LICENSE",
        "parser_version": parser_version,
        "evidence_state": "PASS",
        "coverage": {
            **coverage,
            "adapter_version": ADAPTER_VERSION,
            "contributing_artifacts": {item.name: item.sha256 for item in sources},
            "expiry_basis": min(
                sources, key=lambda item: item.expires_at
            ).staleness_basis
            if min(item.expires_at for item in sources) <= horizon
            else "GAME_LOCK_HORIZON",
            "model_status": "PRIOR_ONLY",
            "not_a_claim_of": "EV_ROI_WIN_PROBABILITY_OWNERSHIP_OR_EDGE",
        },
    }


# --------------------------------------------------------------------------- #
# Slate geometry
# --------------------------------------------------------------------------- #


def showdown_people(slate: SlateContract) -> dict[str, dict[str, SalaryPlayer]]:
    """Group a Showdown pool by person, keeping both DraftKings roles.

    A Showdown pool lists every person twice. One person gets one prior record
    and one identity mapping, keyed to the FLEX row, because that is the row
    `projection.py` requires. The CPT row is retained so the reconciliation is
    reported rather than assumed.
    """

    if slate.mode is not EngineMode.SHOWDOWN:
        raise PriorsBuildError(f"MODE_NOT_SHOWDOWN:{slate.mode.value}")
    if len(slate.games) != 1:
        raise PriorsBuildError(f"SHOWDOWN_GAME_COUNT:{len(slate.games)}")
    people: dict[str, dict[str, SalaryPlayer]] = {}
    for player in slate.players:
        if player.role is None:
            raise PriorsBuildError(f"SHOWDOWN_ROW_WITHOUT_ROLE:{player.dk_id}")
        roles = people.setdefault(player.underlying_id, {})
        if player.role in roles:
            raise PriorsBuildError(f"DUPLICATE_SHOWDOWN_ROLE:{player.underlying_id}:{player.role}")
        roles[player.role] = player
    incomplete = sorted(person for person, roles in people.items() if set(roles) != {"CPT", "FLEX"})
    if incomplete:
        raise PriorsBuildError(f"SHOWDOWN_ROLE_PAIR_INCOMPLETE:{incomplete[:10]}")
    return people


def slate_people(slate: SlateContract) -> dict[str, dict[str, SalaryPlayer]]:
    """Return one exact current-DK row per person, preserving Showdown pairs.

    The projection contract consumes the FLEX row for Showdown and the sole
    salary row for Classic.  Keeping both behind one helper lets the source and
    identity transformations stay shared without inventing a second Classic
    prior engine.
    """

    if slate.mode is EngineMode.SHOWDOWN:
        return showdown_people(slate)
    if slate.mode is not EngineMode.CLASSIC:
        raise PriorsBuildError(f"MODE_NOT_SUPPORTED:{slate.mode.value}")
    if len(slate.games) < 2:
        raise PriorsBuildError(f"CLASSIC_GAME_COUNT:{len(slate.games)}")
    people: dict[str, dict[str, SalaryPlayer]] = {}
    for player in slate.players:
        if player.role is not None:
            raise PriorsBuildError(f"CLASSIC_ROW_HAS_ROLE:{player.dk_id}:{player.role}")
        if player.underlying_id in people:
            raise PriorsBuildError(f"DUPLICATE_CLASSIC_PERSON:{player.underlying_id}")
        people[player.underlying_id] = {"FLEX": player}
    return people


def resolve_team_crosswalk(
    slate: SlateContract,
    teams_rows: Sequence[Mapping[str, str]],
    *,
    season: int,
) -> dict[str, str]:
    """Bind each DraftKings team abbreviation to an nflverse team code.

    The two sides share no abbreviation (DraftKings writes LAR where nflverse
    writes LA), so nothing here guesses. DraftKings names its DST row after the
    team nickname, and `nfldata/teams.csv` publishes that nickname per season,
    which makes the join exact and entirely data-derived. A nickname that is not
    unique, or a team without a DST row, fails closed.
    """

    nickname_to_team: dict[str, list[str]] = {}
    for row in teams_rows:
        if (row.get("season") or "").strip() != str(season):
            continue
        nickname = normalize_person_name(row.get("nickname") or "")
        code = (row.get("team") or "").strip().upper()
        if nickname and code:
            nickname_to_team.setdefault(nickname, []).append(code)

    dk_teams = sorted({player.team for player in slate.players})
    expected_teams = 2 if slate.mode is EngineMode.SHOWDOWN else 2 * len(slate.games)
    if len(dk_teams) != expected_teams:
        raise PriorsBuildError(
            f"SLATE_TEAM_COUNT:mode={slate.mode.value}:teams={dk_teams}:"
            f"expected={expected_teams}"
        )

    crosswalk: dict[str, str] = {}
    for player in slate.players:
        if player.position != "DST":
            continue
        nickname = normalize_person_name(player.name)
        candidates = sorted(set(nickname_to_team.get(nickname, [])))
        if not candidates:
            raise PriorsBuildError(
                f"TEAM_NICKNAME_UNMATCHED:{player.team}:{player.name!r}:season={season}"
            )
        if len(candidates) > 1:
            raise PriorsBuildError(
                f"TEAM_NICKNAME_AMBIGUOUS:{player.name!r}:{candidates}"
            )
        existing = crosswalk.get(player.team)
        if existing is not None and existing != candidates[0]:
            raise PriorsBuildError(
                f"TEAM_NICKNAME_CONFLICT:{player.team}:{existing}:{candidates[0]}"
            )
        crosswalk[player.team] = candidates[0]

    missing = [team for team in dk_teams if team not in crosswalk]
    if missing:
        raise PriorsBuildError(f"TEAM_CROSSWALK_INCOMPLETE:{missing}:no DST row to bind")
    if len(set(crosswalk.values())) != len(dk_teams):
        raise PriorsBuildError(f"TEAM_CROSSWALK_NOT_INJECTIVE:{sorted(crosswalk.items())}")
    return crosswalk


def resolve_nflverse_games(
    slate: SlateContract,
    games_rows: Sequence[Mapping[str, str]],
    crosswalk: Mapping[str, str],
    *,
    season: int,
) -> dict[str, dict[str, str]]:
    """Bind every DK game to exactly one oriented nflverse schedule row."""

    resolved: dict[str, dict[str, str]] = {}
    for game in slate.games:
        expected = {crosswalk[game.away_team], crosswalk[game.home_team]}
        kickoff_date = game.lock_at.astimezone(game.lock_at.tzinfo).date().isoformat()
        matches = [
            row
            for row in games_rows
            if (row.get("season") or "").strip() == str(season)
            and {
                (row.get("away_team") or "").strip().upper(),
                (row.get("home_team") or "").strip().upper(),
            }
            == expected
            and (row.get("gameday") or "").strip() == kickoff_date
        ]
        if len(matches) != 1:
            raise PriorsBuildError(
                f"NFLVERSE_GAME_NOT_UNIQUE:{game.game_id}:{sorted(expected)}:"
                f"{kickoff_date}:matches={len(matches)}"
            )
        matched = dict(matches[0])
        if (matched.get("away_team") or "").strip().upper() != crosswalk[game.away_team]:
            raise PriorsBuildError(
                "NFLVERSE_GAME_ORIENTATION_CONFLICT:"
                f"game={game.game_id}:dk_away={game.away_team}:"
                f"nflverse_away={matched.get('away_team')}"
            )
        resolved[game.game_id] = matched
    if set(resolved) != {game.game_id for game in slate.games}:
        raise PriorsBuildError("NFLVERSE_GAME_COVERAGE_MISMATCH")
    return resolved


def resolve_nflverse_game(
    slate: SlateContract,
    games_rows: Sequence[Mapping[str, str]],
    crosswalk: Mapping[str, str],
    *,
    season: int,
) -> dict[str, str]:
    """Find the one nflverse schedule row for this DraftKings game.

    Matched on season, the exact pair of crosswalked team codes, and the
    DraftKings kickoff date in Eastern time. Anything other than exactly one
    match fails closed rather than picking a row.
    """

    if len(slate.games) != 1:
        raise PriorsBuildError(f"SINGLE_GAME_REQUIRED:{len(slate.games)}")
    return resolve_nflverse_games(
        slate, games_rows, crosswalk, season=season
    )[slate.games[0].game_id]


# --------------------------------------------------------------------------- #
# Identity proposals
# --------------------------------------------------------------------------- #


def _roster_candidates(
    roster_rows: Sequence[Mapping[str, str]],
    *,
    season: int,
    nflverse_teams: Iterable[str] | None,
) -> dict[str, dict[str, str]]:
    """Latest roster row per person, optionally restricted to given teams."""

    wanted = None if nflverse_teams is None else set(nflverse_teams)
    latest: dict[str, dict[str, str]] = {}
    for row in roster_rows:
        if (row.get("season") or "").strip() != str(season):
            continue
        team = (row.get("team") or "").strip().upper()
        if wanted is not None and team not in wanted:
            continue
        gsis = (row.get("gsis_id") or "").strip()
        if not gsis:
            continue
        try:
            week = int((row.get("week") or "0").strip() or 0)
        except ValueError:
            continue
        current = latest.get(gsis)
        if current is None or week >= int(current["week"]):
            latest[gsis] = {
                "gsis_id": gsis,
                "week": str(week),
                "team": team,
                "position": (row.get("position") or "").strip().upper(),
                "full_name": (row.get("full_name") or "").strip(),
                "pfr_id": (row.get("pfr_id") or "").strip(),
                "status": (row.get("status") or "").strip(),
            }
    return latest


def _players_index(player_rows: Sequence[Mapping[str, str]]) -> dict[str, dict[str, str]]:
    """nflverse's canonical person index, keyed by provider player id.

    The weekly roster is the better anchor because it is team-scoped and dated,
    but a person who has just signed, or who sits on a reserve list, can be
    absent from it while still appearing in a DraftKings pool. This index is the
    fallback that lets such a person be *reported* with a real candidate instead
    of an empty row the reviewer cannot act on.
    """

    index: dict[str, dict[str, str]] = {}
    for row in player_rows:
        gsis = (row.get("gsis_id") or "").strip()
        if not gsis:
            continue
        index[gsis] = {
            "gsis_id": gsis,
            "week": "0",
            "team": (row.get("latest_team") or "").strip().upper(),
            "position": (row.get("position") or "").strip().upper(),
            "full_name": (row.get("display_name") or "").strip(),
            "pfr_id": (row.get("pfr_id") or "").strip(),
            "status": (row.get("status") or "").strip(),
        }
    return index


@dataclass(frozen=True)
class IdentityProposal:
    dk_id: str
    captain_dk_id: str
    dk_name: str
    dk_team: str
    dk_position: str
    underlying_id: str
    nflverse_team: str
    provider_player_id: str
    provider_name: str
    provider_pfr_id: str
    provider_team: str
    provider_status: str
    match_method: str
    candidates: tuple[str, ...]

    @property
    def resolved(self) -> bool:
        return self.match_method in {
            "NORMALIZED_NAME_TEAM_POSITION",
            "NORMALIZED_NAME_TEAM",
            "PLAYERS_INDEX_NAME_TEAM_POSITION",
            "TEAM_DEFENSE_NICKNAME",
        }

    def as_payload(self) -> dict[str, object]:
        return {
            "dk_id": self.dk_id,
            "captain_dk_id": self.captain_dk_id,
            "dk_name": self.dk_name,
            "dk_team": self.dk_team,
            "dk_position": self.dk_position,
            "underlying_id": self.underlying_id,
            "nflverse_team": self.nflverse_team,
            "provider_player_id": self.provider_player_id,
            "provider_name": self.provider_name,
            "provider_pfr_id": self.provider_pfr_id,
            "provider_team": self.provider_team,
            "provider_status": self.provider_status,
            "match_method": self.match_method,
            "candidates": list(self.candidates),
        }


def propose_identities(
    slate: SlateContract,
    roster_rows: Sequence[Mapping[str, str]],
    crosswalk: Mapping[str, str],
    *,
    season: int,
    player_index_rows: Sequence[Mapping[str, str]] = (),
) -> tuple[IdentityProposal, ...]:
    """Propose one nflverse identity per person in the Showdown pool.

    Every match here is normalized, therefore a proposal. `projection.py` only
    accepts `match_method="EXACT"`, and this function never emits that value;
    `freeze_prior_package` does, and only for a reviewed decision.
    """

    people = slate_people(slate)
    candidates = _roster_candidates(
        roster_rows, season=season, nflverse_teams=crosswalk.values()
    )
    league_candidates = _roster_candidates(roster_rows, season=season, nflverse_teams=None)
    by_team_name_position: dict[tuple[str, str, str], list[dict[str, str]]] = {}
    by_team_name: dict[tuple[str, str], list[dict[str, str]]] = {}
    for row in candidates.values():
        key_name = normalize_person_name(row["full_name"])
        by_team_name_position.setdefault(
            (row["team"], key_name, row["position"]), []
        ).append(row)
        by_team_name.setdefault((row["team"], key_name), []).append(row)

    # A DraftKings pool routinely lists a person whose nflverse roster row still
    # says another team: a practice-squad elevation, or a signing the weekly
    # roster has not caught up with. Binding those automatically would be
    # exactly the normalized guess this design refuses, so they stay unresolved.
    # But an unresolved row with an empty candidate list gives the reviewer
    # nothing to act on, so the league-wide candidate is reported alongside the
    # team conflict that disqualified it.
    league_name_position: dict[tuple[str, str], list[dict[str, str]]] = {}
    league_name: dict[str, list[dict[str, str]]] = {}
    for row in league_candidates.values():
        key_name = normalize_person_name(row["full_name"])
        league_name_position.setdefault((key_name, row["position"]), []).append(row)
        league_name.setdefault(key_name, []).append(row)

    index_team_position: dict[tuple[str, str, str], list[dict[str, str]]] = {}
    index_name_position: dict[tuple[str, str], list[dict[str, str]]] = {}
    for row in _players_index(player_index_rows).values():
        key_name = normalize_person_name(row["full_name"])
        index_team_position.setdefault(
            (row["team"], key_name, row["position"]), []
        ).append(row)
        index_name_position.setdefault((key_name, row["position"]), []).append(row)

    proposals: list[IdentityProposal] = []
    for underlying_id in sorted(people):
        roles = people[underlying_id]
        flex = roles["FLEX"]
        captain = roles.get("CPT")
        nflverse_team = crosswalk[flex.team]
        normalized = normalize_person_name(flex.name)

        if flex.position == "DST":
            provider_id = f"nflverse:DST:{nflverse_team}:{season}"
            proposals.append(
                IdentityProposal(
                    dk_id=flex.dk_id,
                    captain_dk_id=captain.dk_id if captain is not None else "",
                    dk_name=flex.name,
                    dk_team=flex.team,
                    dk_position=flex.position,
                    underlying_id=underlying_id,
                    nflverse_team=nflverse_team,
                    provider_player_id=provider_id,
                    provider_name=flex.name,
                    provider_pfr_id="",
                    provider_team=nflverse_team,
                    provider_status="TEAM_ENTITY",
                    match_method="TEAM_DEFENSE_NICKNAME",
                    candidates=(provider_id,),
                )
            )
            continue

        exact_position = by_team_name_position.get(
            (nflverse_team, normalized, flex.position), []
        )
        name_only = by_team_name.get((nflverse_team, normalized), [])
        league_position = league_name_position.get((normalized, flex.position), [])
        league_only = league_name.get(normalized, [])
        index_position = index_team_position.get(
            (nflverse_team, normalized, flex.position), []
        )
        index_league = index_name_position.get((normalized, flex.position), [])
        if len(exact_position) == 1:
            chosen, method = exact_position[0], "NORMALIZED_NAME_TEAM_POSITION"
        elif len(exact_position) > 1:
            chosen, method = None, "AMBIGUOUS"
        elif len(name_only) == 1:
            chosen, method = name_only[0], "NORMALIZED_NAME_TEAM"
        elif len(name_only) > 1:
            chosen, method = None, "AMBIGUOUS"
        elif len(index_position) == 1:
            # The person is absent from the dated weekly roster but the
            # canonical index places them on this same team, so the team
            # constraint still holds and the row is worth pre-marking.
            chosen, method = index_position[0], "PLAYERS_INDEX_NAME_TEAM_POSITION"
        elif len(index_position) > 1:
            chosen, method = None, "AMBIGUOUS"
        elif len(league_position) == 1:
            chosen, method = league_position[0], "NAME_POSITION_OTHER_TEAM"
        elif len(league_only) == 1:
            chosen, method = league_only[0], "NAME_OTHER_TEAM"
        elif len(index_league) == 1:
            chosen, method = index_league[0], "PLAYERS_INDEX_OTHER_TEAM"
        elif league_only or index_league:
            chosen, method = None, "AMBIGUOUS"
        else:
            chosen, method = None, "UNMATCHED"

        pool = (
            exact_position
            or name_only
            or index_position
            or league_position
            or league_only
            or index_league
        )
        proposals.append(
            IdentityProposal(
                dk_id=flex.dk_id,
                captain_dk_id=captain.dk_id if captain is not None else "",
                dk_name=flex.name,
                dk_team=flex.team,
                dk_position=flex.position,
                underlying_id=underlying_id,
                nflverse_team=nflverse_team,
                provider_player_id=chosen["gsis_id"] if chosen else "",
                provider_name=chosen["full_name"] if chosen else "",
                provider_pfr_id=chosen["pfr_id"] if chosen else "",
                provider_team=chosen["team"] if chosen else "",
                provider_status=chosen["status"] if chosen else "",
                match_method=method,
                candidates=tuple(
                    f"{row['gsis_id']}|{row['full_name']}|{row['position']}"
                    f"|{row['team']}|{row['status']}"
                    for row in pool
                ),
            )
        )
    return tuple(proposals)


def review_csv_bytes(proposals: Iterable[IdentityProposal]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(REVIEW_COLUMNS)
    for proposal in proposals:
        writer.writerow(
            (
                proposal.dk_id,
                proposal.dk_name,
                proposal.dk_team,
                proposal.dk_position,
                proposal.provider_player_id,
                proposal.provider_name,
                proposal.provider_team,
                proposal.provider_status,
                proposal.match_method,
                ACCEPTED_DECISION if proposal.resolved else "",
                "",
            )
        )
    return buffer.getvalue().encode("utf-8")


def read_reviewed_decisions(path: Path) -> dict[str, dict[str, str]]:
    rows = read_csv_rows(path, REVIEW_COLUMNS, label="identity_review")
    decisions: dict[str, dict[str, str]] = {}
    for row in rows:
        dk_id = (row.get("DK_ID") or "").strip()
        if not dk_id:
            raise PriorsBuildError("REVIEW_ROW_WITHOUT_DK_ID")
        if dk_id in decisions:
            raise PriorsBuildError(f"REVIEW_DUPLICATE_DK_ID:{dk_id}")
        decisions[dk_id] = {key: (value or "").strip() for key, value in row.items()}
    if not decisions:
        raise PriorsBuildError("REVIEW_FILE_EMPTY")
    return decisions


# --------------------------------------------------------------------------- #
# Team prior transformation
# --------------------------------------------------------------------------- #


MINIMUM_PRIOR_GAMES = 4


def _team_weekly_rows(
    team_stat_rows: Sequence[Mapping[str, str]],
    *,
    nflverse_team: str,
    prior_season: int,
) -> list[Mapping[str, str]]:
    selected = [
        row
        for row in team_stat_rows
        if (row.get("season") or "").strip() == str(prior_season)
        and (row.get("team") or "").strip().upper() == nflverse_team
        and (row.get("season_type") or "").strip().upper() == "REG"
    ]
    if len(selected) < MINIMUM_PRIOR_GAMES:
        raise PriorsBuildError(
            f"TEAM_PRIOR_COVERAGE_INSUFFICIENT:{nflverse_team}:{prior_season}"
            f":games={len(selected)}:minimum={MINIMUM_PRIOR_GAMES}"
        )
    return sorted(selected, key=lambda row: int((row.get("week") or "0").strip() or 0))


def build_team_records(
    slate: SlateContract,
    *,
    crosswalk: Mapping[str, str],
    game_rows: Mapping[str, Mapping[str, str]],
    team_stat_rows: Sequence[Mapping[str, str]],
    weather_by_game: Mapping[str, str],
    market_observed_at: datetime,
    season: int,
    prior_season: int,
) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, object]]:
    """Derive one team-prior record per team, plus its identity mappings.

    Rate and volume fields come from the prior season's regular-season team
    weeks. Market fields come from the frozen schedule artifact. `uncertainty`
    is the coefficient of variation of that team's weekly offensive plays: a
    dispersion indicator over the same frozen bytes, not a calibrated variance
    and not a confidence interval.
    """

    records: list[dict[str, object]] = []
    mappings: list[dict[str, object]] = []
    diagnostics: dict[str, object] = {}

    expected_games = {game.game_id for game in slate.games}
    if set(game_rows) != expected_games or set(weather_by_game) != expected_games:
        raise PriorsBuildError(
            "TEAM_PRIOR_GAME_COVERAGE_MISMATCH:"
            f"schedule_missing={sorted(expected_games - set(game_rows))}:"
            f"weather_missing={sorted(expected_games - set(weather_by_game))}"
        )
    for game in slate.games:
        game_row = game_rows[game.game_id]
        total_line = _required_decimal(game_row, "total_line", label="games.total_line")
        spread_line = _required_decimal(game_row, "spread_line", label="games.spread_line")
        for dk_team in (game.away_team, game.home_team):
            nflverse_team = crosswalk[dk_team]
            label = f"team:{dk_team}"
            weeks = _team_weekly_rows(
                team_stat_rows, nflverse_team=nflverse_team, prior_season=prior_season
            )
            played = Decimal(len(weeks))

            def column(name: str) -> Decimal:
                return sum(
                    (_decimal_cell(row, name, label=f"{label}:{name}") for row in weeks),
                    Decimal("0"),
                )

            attempts = column("attempts")
            carries = column("carries")
            sacks = column("sacks_suffered")
            dropbacks = attempts + sacks
            plays = dropbacks + carries
            weekly_plays = [
                _decimal_cell(row, "attempts", label=label)
                + _decimal_cell(row, "sacks_suffered", label=label)
                + _decimal_cell(row, "carries", label=label)
                for row in weeks
            ]
            mean_plays = _ratio(plays, played, label=f"{label}:plays_mean")
            dispersion = (
                _ratio(statistics.stdev(weekly_plays), mean_plays, label=f"{label}:uncertainty")
                if len(weekly_plays) > 1
                else Decimal("1")
            )

        # nflverse publishes spread_line from the home team's point of view and
        # positive when the home team is favoured, so each team's own betting
        # spread is the negation for the home side.
            team_spread = -spread_line if dk_team == game.home_team else spread_line

            records.append(
                {
                "provider_team_id": f"nflverse:{nflverse_team}:{season}",
                "game_id": game.game_id,
                "plays_mean": _bounded(mean_plays, "35", "95", label=f"{label}:plays_mean"),
                "pass_rate": _bounded(
                    _ratio(dropbacks, plays, label=f"{label}:pass_rate"),
                    "0.2",
                    "0.85",
                    label=f"{label}:pass_rate",
                ),
                "pass_yards_per_attempt": _bounded(
                    _ratio(column("passing_yards"), attempts, label=f"{label}:pass_ypa"),
                    "2",
                    "15",
                    label=f"{label}:pass_yards_per_attempt",
                ),
                "rush_yards_per_attempt": _bounded(
                    _ratio(column("rushing_yards"), carries, label=f"{label}:rush_ypa"),
                    "1",
                    "10",
                    label=f"{label}:rush_yards_per_attempt",
                ),
                "touchdowns_mean": _bounded(
                    _ratio(
                        column("passing_tds") + column("rushing_tds"),
                        played,
                        label=f"{label}:touchdowns_mean",
                    ),
                    "0",
                    "10",
                    label=f"{label}:touchdowns_mean",
                ),
                "field_goals_mean": _bounded(
                    _ratio(column("fg_made"), played, label=f"{label}:field_goals_mean"),
                    "0",
                    "8",
                    label=f"{label}:field_goals_mean",
                ),
                "turnovers_mean": _bounded(
                    _ratio(
                        column("passing_interceptions") + column("fumbles_lost_total"),
                        played,
                        label=f"{label}:turnovers_mean",
                    ),
                    "0",
                    "6",
                    label=f"{label}:turnovers_mean",
                ),
                "sacks_allowed_mean": _bounded(
                    _ratio(sacks, played, label=f"{label}:sacks_allowed_mean"),
                    "0",
                    "10",
                    label=f"{label}:sacks_allowed_mean",
                ),
                "uncertainty": _bounded(
                    min(dispersion, Decimal("1")), "0", "1", label=f"{label}:uncertainty"
                ),
                "market_total": _bounded(total_line, "20", "100", label=f"{label}:market_total"),
                "market_spread": _bounded(
                    team_spread, "-40", "40", label=f"{label}:market_spread"
                ),
                "market_observed_at": market_observed_at.isoformat(),
                "weather_state": weather_by_game[game.game_id],
                "era": f"{season}_REG_PRIOR_FROM_{prior_season}_REG",
                "evidence_state": "PASS",
                }
            )
            mappings.append(
                {
                "provider_team_id": f"nflverse:{nflverse_team}:{season}",
                "team": dk_team,
                "game_id": game.game_id,
                "match_method": "EXACT",
                "evidence_state": "PASS",
                }
            )
            diagnostics[dk_team] = {
                "game_id": game.game_id,
                "nflverse_game_id": (game_row.get("game_id") or "").strip(),
                "nflverse_team": nflverse_team,
                "prior_games": len(weeks),
                "weeks": [int((row.get("week") or "0").strip() or 0) for row in weeks],
                "weather_state": weather_by_game[game.game_id],
            }
    return records, mappings, diagnostics


WEATHER_EVIDENCE_PARSER = "operator_weather_capture_v1"


def _weather_evidence_basis(
    source_uri: str | None, observed_at: str | datetime | None, *, as_of: datetime
) -> str:
    """Attribute an operator-supplied weather state to a real approved source.

    An outdoor game needs a value the frozen artifacts cannot supply. Recording
    it as bare `OPERATOR_SUPPLIED` leaves the one number a human injected with no
    provenance at all, so a URI may be attached and it is held to the same host
    and licence policy as every other source reference: `api.weather.gov` is
    already allowlisted as `PUBLIC_DOMAIN`.
    """

    if not source_uri:
        return "OPERATOR_SUPPLIED_UNATTRIBUTED"
    try:
        validate_source_reference_policy(
            source_uri,
            license_decision="PUBLIC_DOMAIN",
            parser_version=WEATHER_EVIDENCE_PARSER,
        )
    except SourcePolicyError as exc:
        raise PriorsBuildError(f"WEATHER_SOURCE_UNAPPROVED:{source_uri}:{exc}") from exc
    if observed_at is None:
        raise PriorsBuildError(
            "WEATHER_OBSERVED_AT_REQUIRED:a weather source URI needs its observation time"
        )
    observed = _parse_timestamp(observed_at, label="WEATHER_OBSERVED_AT")
    if observed > as_of:
        raise PriorsBuildError(
            f"WEATHER_OBSERVATION_IN_FUTURE:{observed.isoformat()}>{as_of.isoformat()}"
        )
    if as_of > observed + timedelta(hours=6):
        raise PriorsBuildError("WEATHER_CAPTURE_STALE:refresh the forecast; maximum age is six hours")
    return f"OPERATOR_CAPTURE:{source_uri}:observed_at={observed.isoformat()}"


def _venue_roof_history_for(
    game_row: Mapping[str, str],
    venue_roof_history: Mapping[str, Mapping[str, int]] | None,
) -> dict[str, int]:
    """This game's home venue history, or an empty map when it cannot speak.

    Empty for a venue with no retractable roof, so a reader of the proposal
    cannot mistake an outdoor venue's unanimous `outdoors` count for something
    the weather stage would act on.
    """

    home_team = (game_row.get("home_team") or "").strip().upper()
    if home_team not in RETRACTABLE_ROOF_HOME_TEAMS or not venue_roof_history:
        return {}
    return {
        str(roof): int(count)
        for roof, count in sorted(dict(venue_roof_history.get(home_team) or {}).items())
    }


def resolve_weather_state(
    game_row: Mapping[str, str],
    operator_weather_state: str | None,
    *,
    venue_roof_history: Mapping[str, Mapping[str, int]] | None = None,
    venue_roof_seasons: Iterable[int | str] | None = None,
) -> tuple[str, str]:
    """Resolve the weather enum, which has no UNKNOWN member.

    A fixed or retracted roof is decided by the frozen schedule artifact. An
    outdoor game is not: `api.weather.gov` is unreachable from a session, and
    the contract offers no way to say so. Rather than invent a value, an outdoor
    game requires an operator-supplied state and otherwise fails closed.

    One case sits between the two, and `venue_roof_history` is what resolves it.
    nflverse writes the `roof` column only after the game is played, so an
    unplayed game at a retractable-roof venue carries a blank cell that this
    function used to read as an unobserved outdoor game. With the counts from the
    same frozen schedule artifact in hand, a blank at one of those venues
    resolves from that venue's own unanimous history instead, under a basis
    naming the counts. See `venues.resolve_blank_roof` for the three bounds that
    keep it a prior rather than an observation. Omitting the argument keeps the
    behaviour that shipped before it existed.
    """

    roof = (game_row.get("roof") or "").strip().lower()
    if not roof and not operator_weather_state:
        resolved = resolve_blank_roof(
            (game_row.get("home_team") or "").strip(),
            venue_roof_history,
            seasons=venue_roof_seasons,
        )
        if resolved is not None:
            venue_roof, venue_basis = resolved
            return _ROOF_WEATHER[venue_roof], venue_basis
    derived = _ROOF_WEATHER.get(roof)
    if derived is not None:
        if operator_weather_state and operator_weather_state.upper() != derived:
            raise PriorsBuildError(
                f"WEATHER_STATE_CONFLICT:roof={roof}:derived={derived}"
                f":operator={operator_weather_state.upper()}"
            )
        return derived, f"DERIVED_FROM_SCHEDULE_ROOF:{roof or 'blank'}"
    if not operator_weather_state:
        raise PriorsBuildError(
            f"WEATHER_STATE_REQUIRED:roof={roof or 'blank'}"
            ":supply --weather-state; the enum has no UNKNOWN member and"
            " api.weather.gov is unreachable from a session"
        )
    supplied = operator_weather_state.upper()
    if supplied not in _OPERATOR_WEATHER_STATES:
        raise PriorsBuildError(
            f"WEATHER_STATE_UNSUPPORTED:{supplied}:expected {sorted(_OPERATOR_WEATHER_STATES)}"
        )
    return supplied, f"OPERATOR_SUPPLIED:roof={roof or 'blank'}"


# --------------------------------------------------------------------------- #
# Player prior transformation
# --------------------------------------------------------------------------- #

# Mirrors projection._PLAYER_GROUPS. The producer masks each weight to its
# eligible positions and normalizes it against the eligible team total, so the
# denominators here are the same sets that `project` will renormalize over.
_WEIGHT_GROUPS: tuple[tuple[str, str, frozenset[str]], ...] = (
    ("qb_attempt_weight", "attempts", frozenset({"QB"})),
    ("carry_weight", "carries", frozenset({"QB", "RB", "WR", "TE"})),
    ("target_weight", "targets", frozenset({"RB", "WR", "TE"})),
    ("rushing_td_weight", "rushing_tds", frozenset({"QB", "RB", "WR", "TE"})),
    ("receiving_td_weight", "receiving_tds", frozenset({"RB", "WR", "TE"})),
)
_RAW_COLUMNS = (
    "attempts",
    "carries",
    "targets",
    "receptions",
    "receiving_yards",
    "rushing_tds",
    "receiving_tds",
)


def _player_totals(
    player_stat_rows: Sequence[Mapping[str, str]], *, prior_season: int
) -> dict[str, dict[str, Decimal]]:
    """Sum each person's prior regular season, regardless of which team.

    Players change teams. Filtering by the current DraftKings team would silently
    zero a person who was productive elsewhere last year, so the join is on
    provider player id alone.
    """

    totals: dict[str, dict[str, Decimal]] = {}
    for row in player_stat_rows:
        if (row.get("season") or "").strip() != str(prior_season):
            continue
        if (row.get("season_type") or "").strip().upper() != "REG":
            continue
        player_id = (row.get("player_id") or "").strip()
        if not player_id:
            continue
        bucket = totals.setdefault(player_id, {name: Decimal("0") for name in _RAW_COLUMNS})
        for name in _RAW_COLUMNS:
            bucket[name] += _decimal_cell(row, name, label=f"player_stats:{name}")
    return totals


_SHARE_COLUMNS: dict[str, frozenset[str]] = {
    column: eligible for _field, column, eligible in _WEIGHT_GROUPS
}
TRANSFER_PRIOR_VERSION = "transfer_prior_own_old_team_share_v1"


def _team_week_totals(
    player_stat_rows: Sequence[Mapping[str, str]], *, prior_season: int
) -> dict[tuple[str, str], dict[str, Decimal]]:
    """Sum every column per (team, week) over all rows, not only pool members.

    A transfer's prior-team share needs the whole old team as its denominator,
    and only for the weeks the person actually played there, so a mid-season
    arrival or a missed month does not dilute the rate.
    """

    totals: dict[tuple[str, str], dict[str, Decimal]] = {}
    for row in player_stat_rows:
        if (row.get("season") or "").strip() != str(prior_season):
            continue
        if (row.get("season_type") or "").strip().upper() != "REG":
            continue
        key = ((row.get("team") or "").strip().upper(), (row.get("week") or "").strip())
        bucket = totals.setdefault(key, {name: Decimal("0") for name in _RAW_COLUMNS})
        for name in _RAW_COLUMNS:
            bucket[name] += _decimal_cell(row, name, label=f"player_stats:{name}")
    return totals


def transfer_prior_from_old_team(
    person_rows: Sequence[Mapping[str, str]],
    *,
    provider_id: str,
    position: str,
    team_week_totals: Mapping[tuple[str, str], Mapping[str, Decimal]],
    prior_season: int,
) -> dict[str, object]:
    """A transfer's own prior-season share of his old team's volume.

    Ben's 2026-09-10 direction for R17: use the stats we have from prior teams.
    The number is the person's own count divided by the old team's count in the
    weeks he had a row, per column, from the same frozen `player_stats` bytes
    that produce every other share. It is an honest cold-start prior for a
    person whose current-team role is unobserved, carried into the package as
    `EVIDENCE_STATE=UNKNOWN`; it is not a role confirmation and cannot certify.
    """

    own = _player_totals(person_rows, prior_season=prior_season).get(
        provider_id, {name: Decimal("0") for name in _RAW_COLUMNS}
    )
    pairs = sorted(
        {((row.get("team") or "").strip().upper(), (row.get("week") or "").strip())
         for row in person_rows}
    )
    denominators = {name: Decimal("0") for name in _RAW_COLUMNS}
    for pair in pairs:
        for name in _RAW_COLUMNS:
            denominators[name] += team_week_totals.get(pair, {}).get(name, Decimal("0"))
    own_share: dict[str, Decimal] = {}
    for column, eligible in _SHARE_COLUMNS.items():
        if position not in eligible or denominators[column] <= 0:
            own_share[column] = Decimal("0")
        else:
            own_share[column] = _bounded(
                _ratio(own[column], denominators[column], label=f"transfer:{provider_id}:{column}"),
                "0", "1", label=f"transfer:{provider_id}:{column}",
            )
    receiving = position in RECEIVING_POSITIONS and own["targets"] > 0
    catch_rate = (
        _bounded(_ratio(own["receptions"], own["targets"], label=f"transfer:{provider_id}:catch_rate"),
                 "0", "1", label=f"transfer:{provider_id}:catch_rate")
        if receiving else Decimal("0")
    )
    yards_per_target = (
        _bounded(_ratio(own["receiving_yards"], own["targets"], label=f"transfer:{provider_id}:ypt"),
                 "0", "30", label=f"transfer:{provider_id}:yards_per_target")
        if receiving else Decimal("0")
    )
    nonzero = any(value > 0 for value in own_share.values())
    return {
        "basis_version": TRANSFER_PRIOR_VERSION,
        "basis": "OWN_OLD_TEAM_SHARE" if nonzero else "OWN_OLD_TEAM_SHARE_ZERO",
        "old_teams": sorted({team for team, _week in pairs}),
        "old_team_weeks": len(pairs),
        "own_counts": {name: decimal_text(own[name]) for name in _RAW_COLUMNS},
        "old_team_counts": {name: decimal_text(denominators[name]) for name in _RAW_COLUMNS},
        "own_old_share": {name: decimal_text(value) for name, value in own_share.items()},
        "own_catch_rate": decimal_text(catch_rate),
        "own_yards_per_target": decimal_text(yards_per_target),
        "denominator_basis": "OLD_TEAM_ALL_PLAYERS_IN_WEEKS_WITH_A_ROW",
        "injection": "PSEUDO_COUNT_EQUALS_OWN_OLD_SHARE_TIMES_CURRENT_TEAM_POOL_INCUMBENT_TOTAL",
        "does_not_establish": ["CURRENT_TEAM_ROLE", "OFFICIAL_ACTIVE_STATUS", "MODEL_VALIDATION"],
    }


def _role_capacities(
    snap_rows: Sequence[Mapping[str, str]], *, prior_season: int
) -> dict[str, Decimal]:
    """Mean offensive snap share per person, keyed by Pro Football Reference id."""

    accumulated: dict[str, list[Decimal]] = {}
    for row in snap_rows:
        if (row.get("season") or "").strip() != str(prior_season):
            continue
        if (row.get("game_type") or "").strip().upper() != "REG":
            continue
        pfr_id = (row.get("pfr_player_id") or "").strip()
        if not pfr_id:
            continue
        accumulated.setdefault(pfr_id, []).append(
            _decimal_cell(row, "offense_pct", label="snap_counts:offense_pct")
        )
    return {
        pfr_id: _ratio(sum(values, Decimal("0")), Decimal(len(values)), label=f"capacity:{pfr_id}")
        for pfr_id, values in accumulated.items()
    }


def build_player_records(
    slate: SlateContract,
    resolved: Mapping[str, tuple[IdentityProposal, str]],
    *,
    crosswalk: Mapping[str, str],
    player_stat_rows: Sequence[Mapping[str, str]],
    snap_rows: Sequence[Mapping[str, str]],
    prior_season: int,
    season: int,
) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, object]]:
    """Derive one player-prior record and one identity mapping per person."""

    people = slate_people(slate)
    totals = _player_totals(player_stat_rows, prior_season=prior_season)
    capacities = _role_capacities(snap_rows, prior_season=prior_season)
    team_week_totals = _team_week_totals(player_stat_rows, prior_season=prior_season)

    raw: dict[str, dict[str, Decimal]] = {}
    history: dict[str, dict[str, object]] = {}
    transfer_priors: dict[str, dict[str, object]] = {}
    for underlying_id, (proposal, provider_id) in resolved.items():
        flex = people[underlying_id]["FLEX"]
        person_rows = [row for row in player_stat_rows
                       if row.get("player_id", "").strip() == provider_id
                       and row.get("season", "").strip() == str(prior_season)
                       and row.get("season_type", "").strip().upper() == "REG"]
        historical_teams = sorted({row.get("team", "").strip().upper() for row in person_rows})
        current_rows = [row for row in person_rows if row.get("team", "").strip().upper() == crosswalk[flex.team]]
        current_totals = _player_totals(current_rows, prior_season=prior_season)
        raw[underlying_id] = dict(current_totals.get(provider_id, {name: Decimal("0") for name in _RAW_COLUMNS}))
        if flex.position in {"QB", "RB", "WR", "TE"}:
            incomplete = any((row.get(column) or "").strip() in {"", "NA", "NaN", "null"}
                             for row in current_rows for column in _RAW_COLUMNS)
            transfer = bool(person_rows) and not current_rows
            state = ("MISSING_HISTORY" if not person_rows or incomplete else
                     "CURRENT_ROLE_UNKNOWN" if transfer else
                     "OBSERVED_HISTORY_ZERO" if not any(raw[underlying_id].values()) else
                     "OBSERVED_HISTORY")
            if incomplete:
                raw[underlying_id] = {name: Decimal("0") for name in _RAW_COLUMNS}
            history[underlying_id] = {
                "state": state, "historical_teams": historical_teams,
                "current_team": flex.team, "provider_current_team": crosswalk[flex.team],
                "incompatible_transfer": transfer, "prior_rows": len(person_rows),
                "current_team_rows": len(current_rows), "prior_season": prior_season,
                "receiving_efficiency_observed": raw[underlying_id]["targets"] > 0,
                "basis_version": "offensive_current_team_history_v1",
                "denominator_basis": "CURRENT_TEAM_ROWS_ONLY_CURRENT_SALARY_POOL",
            }
            if transfer and not incomplete:
                prior = transfer_prior_from_old_team(
                    person_rows,
                    provider_id=provider_id,
                    position=flex.position,
                    team_week_totals=team_week_totals,
                    prior_season=prior_season,
                )
                history[underlying_id]["transfer_prior"] = prior
                if prior["basis"] == "OWN_OLD_TEAM_SHARE":
                    transfer_priors[underlying_id] = prior
                    history[underlying_id]["receiving_efficiency_observed"] = (
                        Decimal(str(prior["own_catch_rate"])) > 0
                    )

    # Denominators are the DraftKings pool members for each team, which is the
    # same set projection.py normalizes over, so its renormalization is an
    # identity rather than a second, different transformation.
    by_team: dict[str, list[str]] = {}
    for underlying_id in sorted(resolved):
        by_team.setdefault(people[underlying_id]["FLEX"].team, []).append(underlying_id)

    # Transfer priors enter the same pool normalization as everyone else, as a
    # pseudo-count equal to the person's own old-team share times the current
    # team's incumbent pool total for that column. Incumbents' shares scale by
    # 1/(1+sum of transfer shares); the transfer gets s/(1+sum). Receptions and
    # receiving yards are scaled from the pseudo-targets by the person's own
    # catch rate and yards per target, so the efficiency stays his own.
    for dk_team, members in sorted(by_team.items()):
        incoming = [member for member in members if member in transfer_priors]
        if not incoming:
            continue
        incumbents = [member for member in members if member not in transfer_priors]
        for member in incoming:
            position = people[member]["FLEX"].position
            prior = transfer_priors[member]
            pseudo = {name: Decimal("0") for name in _RAW_COLUMNS}
            for column, eligible in _SHARE_COLUMNS.items():
                if position not in eligible:
                    continue
                pool_total = sum(
                    (raw[other][column] for other in incumbents
                     if people[other]["FLEX"].position in eligible),
                    Decimal("0"),
                )
                pseudo[column] = (
                    Decimal(str(prior["own_old_share"][column])) * pool_total
                ).quantize(QUANTUM, rounding=ROUND_HALF_EVEN)
            pseudo["receptions"] = (
                pseudo["targets"] * Decimal(str(prior["own_catch_rate"]))
            ).quantize(QUANTUM, rounding=ROUND_HALF_EVEN)
            pseudo["receiving_yards"] = (
                pseudo["targets"] * Decimal(str(prior["own_yards_per_target"]))
            ).quantize(QUANTUM, rounding=ROUND_HALF_EVEN)
            raw[member] = pseudo
            history[member]["transfer_prior"]["pseudo_counts"] = {
                name: decimal_text(value) for name, value in pseudo.items()
            }

    shares: dict[tuple[str, str], Decimal] = {}
    missing_support: list[str] = []
    for dk_team, members in sorted(by_team.items()):
        for field, column, eligible_positions in _WEIGHT_GROUPS:
            eligible = [
                member
                for member in members
                if people[member]["FLEX"].position in eligible_positions
            ]
            total = sum((raw[member][column] for member in eligible), Decimal("0"))
            if not eligible or total <= 0:
                if eligible and any(history.get(member, {}).get("state") in {"MISSING_HISTORY", "CURRENT_ROLE_UNKNOWN"} for member in eligible):
                    for member in members:
                        shares[(member, field)] = Decimal("0")
                    continue
                missing_support.append(f"{dk_team}:{field}:eligible={len(eligible)}")
                continue
            for member in members:
                position = people[member]["FLEX"].position
                shares[(member, field)] = (
                    _ratio(raw[member][column], total, label=f"{dk_team}:{field}")
                    if position in eligible_positions
                    else Decimal("0")
                )
    if missing_support:
        raise PriorsBuildError(
            "PRIOR_SUPPORT_MISSING:" + ";".join(sorted(missing_support))
            + ":no eligible person in this group has prior-season support, and"
            " uniform filling is prohibited"
        )

    records: list[dict[str, object]] = []
    mappings: list[dict[str, object]] = []
    zero_capacity: list[str] = []
    no_prior_rows: list[str] = []

    for underlying_id in sorted(resolved, key=lambda key: int(people[key]["FLEX"].dk_id)):
        proposal, provider_id = resolved[underlying_id]
        flex = people[underlying_id]["FLEX"]
        position = flex.position
        receiving = position in RECEIVING_POSITIONS
        counts = raw[underlying_id]
        capacity = capacities.get(proposal.provider_pfr_id, Decimal("0"))
        if provider_id not in totals:
            no_prior_rows.append(f"{flex.dk_id}:{flex.name}:{position}")
        if capacity <= 0:
            zero_capacity.append(f"{flex.dk_id}:{flex.name}:{position}")

        records.append(
            {
                "provider_player_id": provider_id,
                "provider_team_id": f"nflverse:{crosswalk[flex.team]}:{season}",
                "position": position,
                "qb_attempt_weight": shares[(underlying_id, "qb_attempt_weight")],
                "carry_weight": shares[(underlying_id, "carry_weight")],
                "target_weight": shares[(underlying_id, "target_weight")],
                "catch_rate": _bounded(
                    _ratio(counts["receptions"], counts["targets"], label=f"{flex.dk_id}:catch_rate")
                    if receiving and counts["targets"] > 0
                    else Decimal("0"),
                    "0",
                    "1",
                    label=f"{flex.dk_id}:catch_rate",
                ),
                "yards_per_target": _bounded(
                    _ratio(
                        counts["receiving_yards"], counts["targets"], label=f"{flex.dk_id}:ypt"
                    )
                    if receiving and counts["targets"] > 0
                    else Decimal("0"),
                    "0",
                    "30",
                    label=f"{flex.dk_id}:yards_per_target",
                ),
                "rushing_td_weight": shares[(underlying_id, "rushing_td_weight")],
                "receiving_td_weight": shares[(underlying_id, "receiving_td_weight")],
                "role_capacity": _bounded(
                    capacity, "0", "1", label=f"{flex.dk_id}:role_capacity"
                ),
                "evidence_state": (
                    "UNKNOWN" if history.get(underlying_id, {}).get("state")
                    in {"MISSING_HISTORY", "CURRENT_ROLE_UNKNOWN"} else "PASS"
                ),
            }
        )
        mappings.append(
            {
                "provider_player_id": provider_id,
                "provider_team_id": f"nflverse:{crosswalk[flex.team]}:{season}",
                "dk_id": flex.dk_id,
                "underlying_id": underlying_id,
                "team": flex.team,
                "position": position,
                "dk_role": "FLEX" if slate.mode is EngineMode.SHOWDOWN else None,
                "match_method": "EXACT",
                "evidence_state": "PASS",
            }
        )

    diagnostics = {
        "offensive_history_by_person": history,
        # R03, which tranche W3 owns. A zero-capacity person is still scored by
        # the simulator: the retained review probe shows a zero-capacity kicker
        # averaging 7.99 points across 984 of 1,000 scenarios. Reporting it,
        # not working around it, and not repairing it here.
        "zero_role_capacity_people": sorted(zero_capacity),
        "zero_role_capacity_count": len(zero_capacity),
        "zero_role_capacity_note": (
            "role_capacity 0 does not exclude a person from scoring; that is R03"
            " and tranche W3 owns the participation mask"
        ),
        "people_without_prior_season_rows": sorted(no_prior_rows),
        "non_opportunity_positions_present": sorted(
            {
                people[key]["FLEX"].position
                for key in resolved
                if people[key]["FLEX"].position in NON_OPPORTUNITY_POSITIONS
            }
        ),
    }
    return records, mappings, diagnostics


# --------------------------------------------------------------------------- #
# Phase one: propose
# --------------------------------------------------------------------------- #


def _require_salary(salaries: str | Path, salary_sha256: str) -> tuple[Path, SlateContract, str]:
    path = Path(salaries).resolve()
    if not path.is_file():
        raise PriorsBuildError(f"SALARY_ARTIFACT_MISSING:{path}")
    expected = salary_sha256.strip().lower()
    if len(expected) != 64 or any(character not in "0123456789abcdef" for character in expected):
        raise PriorsBuildError("EXPECTED_HASH_INVALID:salary")
    actual = sha256_file(path)
    if actual != expected:
        raise PriorsBuildError(
            f"SALARY_ARTIFACT_HASH_MISMATCH:expected={expected}:actual={actual}"
        )
    return path, parse_salaries(path), actual


def _require_absent(output_dir: Path) -> Path:
    resolved = Path(output_dir).resolve()
    if resolved.exists():
        raise PriorsBuildError(f"OUTPUT_PACKAGE_EXISTS:{resolved}")
    return resolved


def propose_prior_package(
    *,
    salaries: str | Path,
    salary_sha256: str,
    season: int,
    prior_season: int,
    as_of: str | datetime,
    output_dir: str | Path,
) -> dict[str, object]:
    """Fetch and freeze the approved artifacts, then emit an identity proposal.

    Publishes no prior artifact. The crosswalk it writes is explicitly a
    proposal and carries no `EXACT` match method.
    """

    when = _parse_timestamp(as_of, label="AS_OF")
    package_root = _require_absent(Path(output_dir))
    _, slate, salary_digest = _require_salary(salaries, salary_sha256)
    people = slate_people(slate)

    package_root.mkdir(parents=True)
    specifications = source_specifications(season=season, prior_season=prior_season)
    frozen = freeze_sources(specifications, package_root=package_root, as_of=when)
    _verify_frozen(frozen)

    specification_by_name = {item.name: item for item in specifications}
    teams_rows = read_csv_rows(
        frozen["teams"].path, specification_by_name["teams"].required_columns, label="teams"
    )
    games_rows = read_csv_rows(
        frozen["games"].path, specification_by_name["games"].required_columns, label="games"
    )
    roster_rows = read_csv_rows(
        frozen["weekly_rosters"].path,
        specification_by_name["weekly_rosters"].required_columns,
        label="weekly_rosters",
    )

    player_index_rows = read_csv_rows(
        frozen["players"].path,
        specification_by_name["players"].required_columns,
        label="players",
    )
    crosswalk = resolve_team_crosswalk(slate, teams_rows, season=season)
    game_rows = resolve_nflverse_games(slate, games_rows, crosswalk, season=season)
    # Counted once here and carried per game into `markets`, so the weather
    # stage resolves a retractable venue's blank roof from the artifact this
    # proposal froze rather than from a constant.
    venue_roof_seasons = season_window(season, prior_season)
    venue_roof_history = roof_history(games_rows, seasons=venue_roof_seasons)
    proposals = propose_identities(
        slate,
        roster_rows,
        crosswalk,
        season=season,
        player_index_rows=player_index_rows,
    )

    manifest = {
        "schema_version": MANIFEST_SCHEMA,
        "adapter_version": ADAPTER_VERSION,
        "as_of": when.isoformat(),
        "season": season,
        "prior_season": prior_season,
        "salary_artifact_id": salary_digest,
        "mode": slate.mode.value,
        "dk_game_ids": [game.game_id for game in slate.games],
        "dk_lock_times": {
            game.game_id: game.lock_at.isoformat() for game in slate.games
        },
        "nflverse_game_ids": {
            game_id: (row.get("game_id") or "").strip()
            for game_id, row in sorted(game_rows.items())
        },
        **(
            {
                "dk_game_id": slate.games[0].game_id,
                "dk_lock_at": slate.games[0].lock_at.isoformat(),
                "nflverse_game_id": (
                    game_rows[slate.games[0].game_id].get("game_id") or ""
                ).strip(),
            }
            if slate.mode is EngineMode.SHOWDOWN
            else {}
        ),
        "team_crosswalk": dict(sorted(crosswalk.items())),
        "artifacts": [
            frozen[name].manifest_entry(package_root=package_root) for name in sorted(frozen)
        ],
    }
    manifest_hash = _write_atomic(
        package_root / MANIFEST_FILENAME, canonical_json_bytes(manifest)
    )

    unresolved = [item for item in proposals if not item.resolved]
    proposal_payload = {
        "schema_version": PROPOSAL_SCHEMA,
        "adapter_version": ADAPTER_VERSION,
        "as_of": when.isoformat(),
        "season": season,
        "salary_artifact_id": salary_digest,
        "source_manifest_sha256": manifest_hash,
        "authoritative": False,
        "note": (
            "Normalized name/team/position matches are proposals. Review every row,"
            " set DECISION=ACCEPT and a REVIEWED_PROVIDER_PLAYER_ID where needed,"
            " then run priors-freeze. Nothing here is an EXACT identity yet."
        ),
        "proposals": [item.as_payload() for item in proposals],
    }
    proposal_hash = _write_atomic(
        package_root / PROPOSAL_FILENAME, canonical_json_bytes(proposal_payload)
    )
    review_hash = _write_atomic(package_root / REVIEW_FILENAME, review_csv_bytes(proposals))

    method_counts: dict[str, int] = {}
    for item in proposals:
        method_counts[item.match_method] = method_counts.get(item.match_method, 0) + 1

    return {
        "status": "DO_NOT_UPLOAD",
        "package_status": "IDENTITY_PROPOSAL_READY",
        "MODEL_STATUS": "PRIOR_ONLY",
        "package_dir": str(package_root),
        "source_manifest": str(package_root / MANIFEST_FILENAME),
        "identity_proposals": str(package_root / PROPOSAL_FILENAME),
        "identity_review": str(package_root / REVIEW_FILENAME),
        "hashes": {
            MANIFEST_FILENAME: manifest_hash,
            PROPOSAL_FILENAME: proposal_hash,
            REVIEW_FILENAME: review_hash,
        },
        "salary_artifact_id": salary_digest,
        "people": len(people),
        "salary_rows": len(slate.players),
        "team_crosswalk": dict(sorted(crosswalk.items())),
        "nflverse_game_id": (
            (game_rows[slate.games[0].game_id].get("game_id") or "").strip()
            if slate.mode is EngineMode.SHOWDOWN
            else None
        ),
        "nflverse_game_ids": {
            game_id: (row.get("game_id") or "").strip()
            for game_id, row in sorted(game_rows.items())
        },
        "markets": {
            game_id: {
                "total_line": (row.get("total_line") or "").strip(),
                "spread_line_home_favoured_positive": (
                    row.get("spread_line") or ""
                ).strip(),
                "roof": (row.get("roof") or "").strip(),
                # This venue's completed home games by recorded roof state, from
                # the same frozen artifact the roof above came from. The weather
                # stage reads it to resolve a retractable venue's blank cell; it
                # is carried per game so the report shows what the resolution
                # rested on. Empty for a venue with no retractable roof.
                "venue_roof_history": _venue_roof_history_for(
                    row, venue_roof_history
                ),
                # The window those counts were taken over, carried so the basis
                # string downstream names it and a replay can reproduce it.
                "venue_roof_history_seasons": list(venue_roof_seasons),
                "attribution": "NFLVERSE_SCHEDULE_ARTIFACT_NO_BOOK_NO_PUBLISHER_TIMESTAMP",
            }
            for game_id, row in sorted(game_rows.items())
        },
        "market": (
            {
                "total_line": (
                    game_rows[slate.games[0].game_id].get("total_line") or ""
                ).strip(),
                "spread_line_home_favoured_positive": (
                    game_rows[slate.games[0].game_id].get("spread_line") or ""
                ).strip(),
                "roof": (
                    game_rows[slate.games[0].game_id].get("roof") or ""
                ).strip(),
                "attribution": "NFLVERSE_SCHEDULE_ARTIFACT_NO_BOOK_NO_PUBLISHER_TIMESTAMP",
            }
            if slate.mode is EngineMode.SHOWDOWN
            else None
        ),
        "match_methods": dict(sorted(method_counts.items())),
        "unresolved": [item.as_payload() for item in unresolved],
        "blockers": (
            [f"IDENTITY_UNRESOLVED:{len(unresolved)}"] if unresolved else []
        ),
        "next": (
            f"Review {REVIEW_FILENAME}, then run priors-freeze with its SHA-256."
            if unresolved
            else f"Review {REVIEW_FILENAME} and run priors-freeze with its SHA-256."
        ),
        "warning": (
            "Proposal only. No prior artifact was published, no identity is EXACT, and"
            " nothing here establishes EV, ROI, win probability, calibrated ownership,"
            " or edge."
        ),
    }


# --------------------------------------------------------------------------- #
# Phase two: freeze
# --------------------------------------------------------------------------- #


def _resolve_reviewed(
    proposals: Sequence[IdentityProposal], decisions: Mapping[str, Mapping[str, str]]
) -> tuple[dict[str, tuple[IdentityProposal, str]], dict[str, str]]:
    by_dk_id = {item.dk_id: item for item in proposals}
    unexpected = sorted(set(decisions) - set(by_dk_id))
    if unexpected:
        raise PriorsBuildError(f"REVIEW_DK_ID_NOT_IN_PROPOSAL:{unexpected[:10]}")
    missing = sorted(set(by_dk_id) - set(decisions))
    if missing:
        raise PriorsBuildError(f"REVIEW_DK_ID_MISSING:{missing[:10]}")

    resolved: dict[str, tuple[IdentityProposal, str]] = {}
    rejected: list[str] = []
    excluded_unresolved: dict[str, str] = {}
    for dk_id, proposal in sorted(by_dk_id.items()):
        row = decisions[dk_id]
        for column, expected in (
            ("DK_NAME", proposal.dk_name),
            ("DK_TEAM", proposal.dk_team),
            ("DK_POSITION", proposal.dk_position),
        ):
            if row.get(column, "") != expected:
                raise PriorsBuildError(
                    f"REVIEW_ROW_ALTERED:{dk_id}:{column}:{row.get(column, '')!r}!={expected!r}"
                )
        decision = row.get("DECISION", "").upper()
        if decision == EXCLUDED_UNRESOLVED_DECISION:
            # Ben's ruling, 2026-09-13. A full Classic pool lists deep
            # practice-squad and UDFA people DraftKings itself flags OUT or IR
            # and nflverse has no record of under any spelling, so demanding a
            # complete identity map made the Classic path unpublishable on every
            # real main slate: an evidence gate no source could ever clear, which
            # CLAUDE.md classes as a defect rather than a constraint. The
            # documented rule is that only an unresolved person who is still
            # SELECTABLE stops a run. This token records that the operator read
            # the row, found no identity, and is dropping the person from the
            # map. `freeze_prior_package` re-derives unavailability from the
            # bound salary bytes before honouring any of it, and names every
            # drop in the returned report so it stays visible.
            excluded_unresolved[proposal.underlying_id] = (
                f"{dk_id}:{proposal.dk_name}:{proposal.dk_team}"
            )
            continue
        if decision != ACCEPTED_DECISION:
            rejected.append(f"{dk_id}:{proposal.dk_name}:{row.get('DECISION', '') or 'BLANK'}")
            continue
        provider_id = row.get("REVIEWED_PROVIDER_PLAYER_ID", "") or proposal.provider_player_id
        if not provider_id:
            rejected.append(f"{dk_id}:{proposal.dk_name}:NO_PROVIDER_ID")
            continue
        resolved[proposal.underlying_id] = (proposal, provider_id)

    if rejected:
        raise PriorsBuildError(
            "IDENTITY_NOT_ACCEPTED:" + ";".join(rejected[:10])
            + f":{len(rejected)} of {len(by_dk_id)} people are unaccepted; a partial"
            " identity map cannot be published"
        )
    provider_ids = [provider for _proposal, provider in resolved.values()]
    if len(set(provider_ids)) != len(provider_ids):
        duplicates = sorted({value for value in provider_ids if provider_ids.count(value) > 1})
        raise PriorsBuildError(f"REVIEWED_PROVIDER_ID_NOT_UNIQUE:{duplicates[:10]}")
    return resolved, excluded_unresolved


def freeze_prior_package(
    *,
    package_dir: str | Path,
    reviewed: str | Path,
    reviewed_sha256: str,
    salaries: str | Path,
    salary_sha256: str,
    as_of: str | datetime,
    output_dir: str | Path,
    weather_state: str | None = None,
    salary_observed_at: str | datetime | None = None,
    weather_source_uri: str | None = None,
    weather_observed_at: str | datetime | None = None,
    weather_evidence_by_game: Mapping[str, Mapping[str, object]] | None = None,
) -> dict[str, object]:
    """Publish the three artifacts `project` consumes, from a reviewed crosswalk."""

    when = _parse_timestamp(as_of, label="AS_OF")
    package_root = Path(package_dir).resolve()
    final_dir = _require_absent(Path(output_dir))
    salary_path, slate, salary_digest = _require_salary(salaries, salary_sha256)

    reviewed_path = Path(reviewed).resolve()
    if not reviewed_path.is_file():
        raise PriorsBuildError(f"REVIEW_FILE_MISSING:{reviewed_path}")
    expected_review = reviewed_sha256.strip().lower()
    actual_review = sha256_file(reviewed_path)
    if actual_review != expected_review:
        raise PriorsBuildError(
            f"REVIEW_FILE_HASH_MISMATCH:expected={expected_review}:actual={actual_review}"
        )

    frozen = load_frozen_manifest(package_root)
    manifest = json.loads((package_root / MANIFEST_FILENAME).read_text(encoding="utf-8"))
    if manifest.get("salary_artifact_id") != salary_digest:
        raise PriorsBuildError(
            "SALARY_ARTIFACT_CHANGED_SINCE_PROPOSAL:"
            f"proposal={manifest.get('salary_artifact_id')}:supplied={salary_digest}"
        )
    season = int(manifest["season"])
    prior_season = int(manifest["prior_season"])

    proposal_payload = json.loads((package_root / PROPOSAL_FILENAME).read_text(encoding="utf-8"))
    if proposal_payload.get("source_manifest_sha256") != sha256_file(
        package_root / MANIFEST_FILENAME
    ):
        raise PriorsBuildError("PROPOSAL_MANIFEST_BINDING_BROKEN")
    proposals = tuple(
        IdentityProposal(
            dk_id=item["dk_id"],
            captain_dk_id=item["captain_dk_id"],
            dk_name=item["dk_name"],
            dk_team=item["dk_team"],
            dk_position=item["dk_position"],
            underlying_id=item["underlying_id"],
            nflverse_team=item["nflverse_team"],
            provider_player_id=item["provider_player_id"],
            provider_name=item["provider_name"],
            provider_pfr_id=item["provider_pfr_id"],
            provider_team=item.get("provider_team", ""),
            provider_status=item.get("provider_status", ""),
            match_method=item["match_method"],
            candidates=tuple(item.get("candidates") or ()),
        )
        for item in proposal_payload.get("proposals", [])
    )
    if not proposals:
        raise PriorsBuildError("PROPOSAL_HAS_NO_ROWS")

    people = slate_people(slate)
    if {item.underlying_id for item in proposals} != set(people):
        raise PriorsBuildError("PROPOSAL_POOL_COVERAGE_MISMATCH")

    resolved, excluded_unresolved = _resolve_reviewed(
        proposals, read_reviewed_decisions(reviewed_path)
    )
    excluded_people = set(excluded_unresolved)
    if set(resolved) | excluded_people != set(people):
        raise PriorsBuildError("REVIEWED_POOL_COVERAGE_MISMATCH")
    # An identity may be dropped only for a person the salary bytes themselves
    # flag as unable to play, whom the availability contract already refuses to
    # select. Re-derived here from the bound salary bytes so the exclusion can
    # never be widened by the reviewed file alone.
    still_selectable = sorted(excluded_people - unavailable_people(slate.players))
    if still_selectable:
        raise PriorsBuildError(
            "IDENTITY_EXCLUDED_BUT_SELECTABLE:"
            + ";".join(excluded_unresolved[person] for person in still_selectable[:10])
        )

    specification_by_name = {
        item.name: item for item in source_specifications(season=season, prior_season=prior_season)
    }

    def rows(name: str) -> list[dict[str, str]]:
        return read_csv_rows(
            frozen[name].path, specification_by_name[name].required_columns, label=name
        )

    crosswalk = resolve_team_crosswalk(slate, rows("teams"), season=season)
    if crosswalk != {key: value for key, value in manifest["team_crosswalk"].items()}:
        raise PriorsBuildError("TEAM_CROSSWALK_CHANGED_SINCE_PROPOSAL")
    schedule_rows = rows("games")
    game_rows = resolve_nflverse_games(slate, schedule_rows, crosswalk, season=season)
    # Counted from the same artifact this package binds, so a replay recounts it.
    venue_roof_seasons = season_window(season, prior_season)
    venue_roof_history = roof_history(schedule_rows, seasons=venue_roof_seasons)
    outdoor_games = [
        game_id
        for game_id, row in sorted(game_rows.items())
        if (row.get("roof") or "").strip().lower() not in _ROOF_WEATHER
        and resolve_blank_roof(
            (row.get("home_team") or "").strip(),
            venue_roof_history if not (row.get("roof") or "").strip() else None,
            seasons=venue_roof_seasons,
        )
        is None
    ]
    evidence_by_game = dict(weather_evidence_by_game or {})
    if evidence_by_game and any(
        value is not None
        for value in (weather_state, weather_source_uri, weather_observed_at)
    ):
        raise PriorsBuildError(
            "WEATHER_EVIDENCE_INPUT_CONFLICT:use the per-game evidence map or the "
            "legacy single-game weather fields, not both"
        )
    unknown_weather_games = sorted(set(evidence_by_game).difference(game_rows))
    if unknown_weather_games:
        raise PriorsBuildError(
            f"WEATHER_EVIDENCE_UNKNOWN_GAMES:{unknown_weather_games}"
        )
    if len(outdoor_games) > 1 and weather_state:
        raise PriorsBuildError(
            "CLASSIC_WEATHER_SCOPE_AMBIGUOUS:"
            f"outdoor_games={outdoor_games}:one scalar weather state/source cannot be "
            "bound to multiple games; freeze a package only after each material game "
            "has exact source-bound weather evidence"
        )
    weather_by_game: dict[str, str] = {}
    weather_basis_by_game: dict[str, str] = {}
    weather_expiries: list[datetime] = []
    for game_id, row in sorted(game_rows.items()):
        game_evidence = dict(evidence_by_game.get(game_id) or {})
        roof = (row.get("roof") or "").strip().lower()
        supplied_state = None if roof in _ROOF_WEATHER else (
            (str(game_evidence.get("weather_state") or "") or None)
            if evidence_by_game
            else (weather_state if game_id in outdoor_games else None)
        )
        supplied_source_uri = (
            str(game_evidence.get("source_uri") or "") or None
            if evidence_by_game
            else weather_source_uri
        )
        supplied_observed_at = (
            game_evidence.get("observed_at")
            if evidence_by_game
            else weather_observed_at
        )
        resolved_weather, weather_basis = resolve_weather_state(
            row,
            supplied_state,
            venue_roof_history=venue_roof_history,
            venue_roof_seasons=venue_roof_seasons,
        )
        if weather_basis.startswith("OPERATOR_SUPPLIED") or (
            resolved_weather == "ROOF_OPEN" and supplied_source_uri
        ):
            evidence_basis = _weather_evidence_basis(
                supplied_source_uri, supplied_observed_at, as_of=when
            )
            if slate.mode is EngineMode.CLASSIC and evidence_basis.endswith("UNATTRIBUTED"):
                raise PriorsBuildError(
                    f"CLASSIC_WEATHER_SOURCE_REQUIRED:{game_id}:outdoor weather must "
                    "be bound to an approved captured source URI and observation time"
                )
            weather_basis = f"{weather_basis}|{evidence_basis}"
            if supplied_source_uri and supplied_observed_at is not None:
                weather_expiries.append(
                    _parse_timestamp(
                        supplied_observed_at, label="WEATHER_OBSERVED_AT"
                    )
                    + timedelta(hours=6)
                )
        weather_by_game[game_id] = resolved_weather
        weather_basis_by_game[game_id] = weather_basis

    lock_at = min(game.lock_at for game in slate.games).astimezone(timezone.utc)
    team_records, team_mappings, team_diagnostics = build_team_records(
        slate,
        crosswalk=crosswalk,
        game_rows=game_rows,
        team_stat_rows=rows("team_stats"),
        weather_by_game=weather_by_game,
        market_observed_at=frozen["games"].observed_at,
        season=season,
        prior_season=prior_season,
    )
    player_records, player_mappings, player_diagnostics = build_player_records(
        slate,
        resolved,
        crosswalk=crosswalk,
        player_stat_rows=rows("player_stats"),
        snap_rows=rows("snap_counts"),
        prior_season=prior_season,
        season=season,
    )

    team_payload = {
        "schema_version": TEAM_SOURCE_SCHEMA,
        "metadata": _artifact_metadata(
            [frozen["games"], frozen["teams"], frozen["team_stats"]],
            parser_version=TEAM_SOURCE_PARSER,
            coverage={
                "teams": len(team_records),
                "mode": slate.mode.value,
                "dk_game_ids": [game.game_id for game in slate.games],
                "nflverse_game_ids": {
                    game_id: (row.get("game_id") or "").strip()
                    for game_id, row in sorted(game_rows.items())
                },
                "prior_season": prior_season,
                "transformation": "NFLVERSE_PRIOR_SEASON_TEAM_WEEK_RATES_AND_SCHEDULE_MARKET_V1",
                "market_attribution": "NFLVERSE_SCHEDULE_NO_BOOK_NO_PUBLISHER_TIMESTAMP",
                "weather_basis_by_game": weather_basis_by_game,
                "weather_evidence_by_game": {
                    game_id: {
                        "source_sha256": evidence.get("sha256"),
                        "source_uri": evidence.get("source_uri"),
                        "observed_at": evidence.get("observed_at"),
                        "captured_at": evidence.get("captured_at"),
                        "expires_at": evidence.get("expires_at"),
                        "parser_version": evidence.get("parser_version"),
                        "license_decision": evidence.get("license_decision"),
                    }
                    for game_id, evidence in sorted(evidence_by_game.items())
                },
                "weather_basis": (
                    weather_basis_by_game[slate.games[0].game_id]
                    if slate.mode is EngineMode.SHOWDOWN
                    else "COMPLETE_GAME_MAP"
                ),
                "uncertainty_definition": "COEFFICIENT_OF_VARIATION_OF_WEEKLY_OFFENSIVE_PLAYS",
                "prior_games_by_team": team_diagnostics,
            },
            horizon=lock_at,
        ),
        "records": team_records,
    }
    if weather_expiries:
        metadata = team_payload["metadata"]
        source_expiry = _parse_timestamp(metadata["expires_at"], label="TEAM_SOURCE_EXPIRES_AT")
        weather_expiry = min(weather_expiries)
        if weather_expiry < source_expiry:
            metadata["expires_at"] = weather_expiry.isoformat()
            metadata["coverage"]["expiry_basis"] = "WEATHER_CAPTURE_SIX_HOUR_WINDOW"
    player_payload = {
        "schema_version": PLAYER_SOURCE_SCHEMA,
        "metadata": _artifact_metadata(
            [frozen["player_stats"], frozen["snap_counts"], frozen["weekly_rosters"]],
            parser_version=PLAYER_SOURCE_PARSER,
            coverage={
                "people": len(player_records),
                "prior_season": prior_season,
                "transformation": "NFLVERSE_PRIOR_SEASON_POOL_NORMALIZED_OPPORTUNITY_SHARES_V1",
                "role_capacity_definition": "MEAN_REGULAR_SEASON_OFFENSE_SNAP_SHARE",
                **player_diagnostics,
            },
            horizon=lock_at,
        ),
        "records": player_records,
    }
    identity_payload = {
        "schema_version": IDENTITY_MAP_SCHEMA,
        "metadata": _artifact_metadata(
            [frozen["weekly_rosters"], frozen["teams"], frozen["players"]],
            parser_version=IDENTITY_MAP_PARSER,
            coverage={
                "team_mappings": len(team_mappings),
                "player_mappings": len(player_mappings),
                "reviewed_decision_file_sha256": actual_review,
                "identity_proposal_sha256": sha256_file(package_root / PROPOSAL_FILENAME),
                "proposal_match_methods": dict(
                    sorted(
                        {
                            item.match_method: sum(
                                1 for other in proposals if other.match_method == item.match_method
                            )
                            for item in proposals
                        }.items()
                    )
                ),
                "transformation": "OPERATOR_REVIEWED_NORMALIZED_CROSSWALK_FROZEN_AS_EXACT_V1",
                "salary_role_reconciliation": {
                    "mode": slate.mode.value,
                    "people": len(people),
                    "salary_rows": len(slate.players),
                    "output_role": (
                        "FLEX" if slate.mode is EngineMode.SHOWDOWN else "CLASSIC"
                    ),
                    "captain_rows_reconciled": len(
                        [item for item in proposals if item.captain_dk_id]
                    ),
                },
                **(
                    {
                        "showdown_role_reconciliation": {
                            "people": len(people),
                            "salary_rows": len(slate.players),
                            "output_role": "FLEX",
                            "captain_rows_reconciled": len(proposals),
                        }
                    }
                    if slate.mode is EngineMode.SHOWDOWN
                    else {}
                ),
            },
            horizon=lock_at,
        ),
        "salary_artifact": {
            "artifact_id": salary_digest,
            "source_uri": "https://www.draftkings.com/",
            "captured_at": _salary_timestamp(salary_path, salary_observed_at, when).isoformat(),
            "observed_at": _salary_timestamp(salary_path, salary_observed_at, when).isoformat(),
            "expires_at": lock_at.isoformat(),
            "license_decision": "OPERATOR_SUPPLIED",
            "parser_version": DK_PARSER_VERSION,
            "evidence_state": "PASS",
            "coverage": {
                "operator_download": True,
                "mode": slate.mode.value,
                "salary_rows": len(slate.players),
                "underlying_people": len(people),
                "observation_basis": (
                    "OPERATOR_STATED" if salary_observed_at else "FILE_MODIFICATION_TIME"
                ),
                "appg_policy": "HASHED_RAW_ONLY_NOT_USED_NUMERICALLY",
            },
        },
        "team_mappings": team_mappings,
        "player_mappings": player_mappings,
    }

    final_dir.parent.mkdir(parents=True, exist_ok=True)
    final_dir.mkdir()
    published: dict[str, str] = {}
    archived_files: list[Path] = []
    try:
        # Keep the raw scoring inputs inside the package so a Cowork rerun or
        # copied package does not depend on the original proposal directory.
        archive_dir = final_dir / RAW_DIRNAME
        archive_dir.mkdir()
        for name in sorted(frozen):
            artifact = frozen[name]
            raw = Path(artifact.path).read_bytes()
            if sha256_bytes(raw) != artifact.sha256:
                raise PriorsBuildError(f"FROZEN_ARTIFACT_CHANGED_DURING_FREEZE:{name}")
            target = archive_dir / f"{artifact.sha256}.csv"
            if target not in archived_files:
                archived_files.append(target)
                _write_atomic(target, raw)
        for filename, payload in (
            (TEAM_PRIOR_FILENAME, team_payload),
            (PLAYER_PRIOR_FILENAME, player_payload),
            (IDENTITY_MAP_FILENAME, identity_payload),
        ):
            published[filename] = _write_atomic(
                final_dir / filename, canonical_json_bytes(payload)
            )
        package = {
            "schema_version": PACKAGE_SCHEMA,
            "adapter_version": ADAPTER_VERSION,
            "as_of": when.isoformat(),
            "season": season,
            "prior_season": prior_season,
            "package_dir": str(package_root),
            "salary_artifact_id": salary_digest,
            "reviewed_decision_file_sha256": actual_review,
            "artifacts": dict(sorted(published.items())),
            "frozen_sources": {name: frozen[name].sha256 for name in sorted(frozen)},
            "model_status": "PRIOR_ONLY",
        }
        published[PACKAGE_FILENAME] = _write_atomic(
            final_dir / PACKAGE_FILENAME, canonical_json_bytes(package)
        )
    except Exception:
        for archived in archived_files:
            archived.unlink(missing_ok=True)
        archive_dir = final_dir / RAW_DIRNAME
        if archive_dir.exists():
            for temporary in archive_dir.glob("*.tmp"):
                temporary.unlink()
            archive_dir.rmdir()
        for leftover in sorted(final_dir.glob("*")):
            leftover.unlink(missing_ok=True)
        final_dir.rmdir()
        raise

    return {
        "status": "DO_NOT_UPLOAD",
        "package_status": "PRIOR_ARTIFACTS_READY",
        "MODEL_STATUS": "PRIOR_ONLY",
        "output_dir": str(final_dir),
        "team_source": str(final_dir / TEAM_PRIOR_FILENAME),
        "player_source": str(final_dir / PLAYER_PRIOR_FILENAME),
        "identity_map": str(final_dir / IDENTITY_MAP_FILENAME),
        "hashes": dict(sorted(published.items())),
        "salary_artifact_id": salary_digest,
        "teams": len(team_records),
        "people": len(player_records),
        # Every person the operator dropped from the identity map, named rather
        # than merely counted. A silent drop is the failure this token exists to
        # avoid, so it travels with the package that was built without them.
        "excluded_unresolved_people": [
            excluded_unresolved[person] for person in sorted(excluded_people)
        ],
        "weather_basis": (
            weather_basis_by_game[slate.games[0].game_id]
            if slate.mode is EngineMode.SHOWDOWN
            else "COMPLETE_GAME_MAP"
        ),
        "weather_basis_by_game": weather_basis_by_game,
        "weather_state": (
            weather_by_game[slate.games[0].game_id]
            if slate.mode is EngineMode.SHOWDOWN
            else None
        ),
        "weather_by_game": weather_by_game,
        "diagnostics": {**player_diagnostics, "prior_games_by_team": team_diagnostics},
        "next": (
            "Run project with --salaries, --team-source, --player-source, --identity-map"
            " and each SHA-256 from hashes."
        ),
        "warning": (
            "These artifacts are PRIOR_ONLY opportunity shares. They do not establish EV,"
            " ROI, profitability, calibration, win probability, cash probability, ownership,"
            " edge, or upload readiness."
        ),
    }


def _salary_timestamp(
    salary_path: Path, stated: str | datetime | None, as_of: datetime
) -> datetime:
    """When the operator observed the DraftKings bytes.

    A stated download time is evidence the operator supplied. Absent that, the
    file's modification time is the only observation the filesystem recorded,
    and the basis is written into coverage so the weaker claim stays visible.
    """

    if stated is not None:
        observed = _parse_timestamp(stated, label="SALARY_OBSERVED_AT")
    else:
        observed = datetime.fromtimestamp(salary_path.stat().st_mtime, tz=timezone.utc)
    if observed > as_of:
        raise PriorsBuildError(
            f"SALARY_OBSERVATION_IN_FUTURE:{observed.isoformat()}>{as_of.isoformat()}"
        )
    return observed
