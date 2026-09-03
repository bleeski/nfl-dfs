from __future__ import annotations

import csv
import io
import json
import math
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Iterable, Mapping


COWORK_REQUEST_VERSION = "nfl_cowork_run_request_v1"

ENTRY_HEADER_PREFIX = ("Entry ID", "Contest Name", "Contest ID", "Entry Fee")
SALARY_HEADER = {
    "Position",
    "Name",
    "ID",
    "Roster Position",
    "Salary",
    "Game Info",
    "TeamAbbrev",
    "AvgPointsPerGame",
    "Status",
}
PAYOUT_HEADER = ("rank_start", "rank_end", "prize_type", "value")
OFFICIAL_STATUS_HEADER = (
    "TEAM",
    "PLAYER_OR_GSIS_ID",
    "STATUS",
    "SOURCE_URL",
    "OBSERVED_AT",
)
TEAM_PROJECTION_HEADER = (
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
PLAYER_OPPORTUNITY_HEADER = (
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
OWNERSHIP_HEADER = ("DK_ID", "LOW", "BASE", "HIGH")
CLASSIC_ASSIGNMENT_HEADER = (
    "Entry ID",
    "QB",
    "RB",
    "RB",
    "WR",
    "WR",
    "WR",
    "TE",
    "FLEX",
    "DST",
)
SHOWDOWN_ASSIGNMENT_HEADER = (
    "Entry ID",
    "CPT",
    "FLEX",
    "FLEX",
    "FLEX",
    "FLEX",
    "FLEX",
)

PATH_FIELDS = (
    "salary_csv",
    "entry_csv",
    "payout_csv",
    "assignment_csv",
    "team_projection_csv",
    "player_opportunity_csv",
    "official_status_csv",
    "ownership_brackets_csv",
    "source_ledger_json",
)


class CoworkInputError(ValueError):
    pass


def confine_request_path(
    value: str | Path,
    *,
    base_dir: str | Path | None = None,
    allowed_roots: Iterable[str | Path] = (),
    allowed_files: Iterable[str | Path] = (),
    field_name: str = "request path",
) -> Path:
    raw = Path(str(value))
    if ".." in raw.parts:
        raise CoworkInputError(f"{field_name} must not contain traversal: {value}")
    if not raw.is_absolute():
        if base_dir is None:
            raise CoworkInputError(f"{field_name} must be absolute without a request base")
        raw = Path(base_dir) / raw
    resolved = raw.resolve()
    roots = tuple(Path(root).resolve() for root in allowed_roots)
    files = tuple(Path(path).resolve() for path in allowed_files)
    if resolved in files or any(resolved == root or resolved.is_relative_to(root) for root in roots):
        return resolved
    raise CoworkInputError(
        f"{field_name} is outside the supplied attachment, managed data, and per-run roots: "
        f"{resolved}"
    )


@dataclass(frozen=True)
class CoworkRunRequest:
    schema_version: str = COWORK_REQUEST_VERSION
    label: str = "slate"
    input_dir: str | None = None
    salary_csv: str | None = None
    entry_csv: str | None = None
    payout_csv: str | None = None
    assignment_csv: str | None = None
    team_projection_csv: str | None = None
    player_opportunity_csv: str | None = None
    official_status_csv: str | None = None
    ownership_brackets_csv: str | None = None
    source_ledger_json: str | None = None
    advertised_prize_value: float | None = None
    ticket_face_value: float | None = None
    field_size: int | None = None
    objective: str = "LARGE_GPP"
    manual_guardrail: bool = True
    profile: str = "diagnostic"

    @classmethod
    def from_mapping(
        cls,
        value: Mapping[str, object],
        *,
        base_dir: str | Path | None = None,
        allowed_roots: Iterable[str | Path] | None = None,
        allowed_files: Iterable[str | Path] = (),
    ) -> "CoworkRunRequest":
        allowed = {field.name for field in fields(cls)}
        unknown = sorted(set(value).difference(allowed))
        if unknown:
            raise CoworkInputError(f"unknown Cowork request fields: {unknown}")
        payload = dict(value)
        version = payload.get("schema_version", COWORK_REQUEST_VERSION)
        if version != COWORK_REQUEST_VERSION:
            raise CoworkInputError(
                f"unsupported Cowork request schema: {version!r}; "
                f"expected {COWORK_REQUEST_VERSION!r}"
            )
        root = Path(base_dir).resolve() if base_dir is not None else None
        roots = tuple(allowed_roots) if allowed_roots is not None else ((root,) if root else ())
        for name in ("input_dir", *PATH_FIELDS):
            raw = payload.get(name)
            if raw in (None, ""):
                payload[name] = None
                continue
            payload[name] = str(
                confine_request_path(
                    str(raw),
                    base_dir=root,
                    allowed_roots=roots,
                    allowed_files=allowed_files,
                    field_name=name,
                )
            )
        label = payload.get("label", "slate")
        if not isinstance(label, str) or not label.strip():
            raise CoworkInputError("label must be a non-empty string")
        objective = payload.get("objective", "LARGE_GPP")
        if objective not in {"LARGE_GPP", "SMALL_GPP", "CASH", "WTA", "SATELLITE"}:
            raise CoworkInputError("objective is not a supported contest objective")
        for name in ("advertised_prize_value", "ticket_face_value"):
            raw = payload.get(name)
            if raw is None:
                continue
            if (
                isinstance(raw, bool)
                or not isinstance(raw, (int, float))
                or not math.isfinite(raw)
                or raw < 0
            ):
                raise CoworkInputError(f"{name} must be a non-negative JSON number")
            payload[name] = float(raw)
        field_size = payload.get("field_size")
        if field_size is not None and (
            isinstance(field_size, bool) or not isinstance(field_size, int) or field_size < 2
        ):
            raise CoworkInputError("field_size must be a JSON integer of at least two")
        if not isinstance(payload.get("manual_guardrail", True), bool):
            raise CoworkInputError("manual_guardrail must be true or false")
        if payload.get("profile", "diagnostic") not in {"diagnostic", "registered"}:
            raise CoworkInputError("profile must be 'diagnostic' or 'registered'")
        return cls(**payload)

    @classmethod
    def from_json(
        cls,
        path: str | Path,
        *,
        allowed_roots: Iterable[str | Path] | None = None,
        allowed_files: Iterable[str | Path] = (),
    ) -> "CoworkRunRequest":
        source = Path(path).resolve()
        payload = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise CoworkInputError("Cowork run request must be a JSON object")
        roots = tuple(allowed_roots) if allowed_roots is not None else (source.parent,)
        return cls.from_mapping(
            payload,
            base_dir=source.parent,
            allowed_roots=roots,
            allowed_files=allowed_files,
        )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class DiscoveredInputs:
    classified: dict[str, Path]
    unclassified_csvs: tuple[Path, ...]


def _decode_csv(path: Path) -> list[list[str]]:
    raw = path.read_bytes()
    encodings = ("utf-8-sig",) if raw.startswith(b"\xef\xbb\xbf") else ("utf-8", "cp1252")
    last_error: UnicodeDecodeError | None = None
    for encoding in encodings:
        try:
            return list(csv.reader(io.StringIO(raw.decode(encoding), newline="")))
        except UnicodeDecodeError as exc:
            last_error = exc
    raise CoworkInputError(f"unsupported CSV encoding: {path}") from last_error


def classify_csv(path: str | Path) -> str | None:
    csv_path = Path(path).resolve()
    rows = _decode_csv(csv_path)
    if not rows:
        return None
    header = tuple(rows[0])
    header_set = set(header)
    if header[: len(ENTRY_HEADER_PREFIX)] == ENTRY_HEADER_PREFIX:
        return "entry_csv"
    if SALARY_HEADER.issubset(header_set):
        return "salary_csv"
    exact_headers = {
        PAYOUT_HEADER: "payout_csv",
        OFFICIAL_STATUS_HEADER: "official_status_csv",
        TEAM_PROJECTION_HEADER: "team_projection_csv",
        PLAYER_OPPORTUNITY_HEADER: "player_opportunity_csv",
        OWNERSHIP_HEADER: "ownership_brackets_csv",
        CLASSIC_ASSIGNMENT_HEADER: "assignment_csv",
        SHOWDOWN_ASSIGNMENT_HEADER: "assignment_csv",
    }
    return exact_headers.get(header)


def discover_csv_inputs(directory: str | Path) -> DiscoveredInputs:
    root = Path(directory).resolve()
    if not root.is_dir():
        raise CoworkInputError(f"Cowork input directory does not exist: {root}")
    candidates: dict[str, list[Path]] = {}
    unclassified: list[Path] = []
    for candidate in sorted(root.iterdir(), key=lambda item: item.name.casefold()):
        path = confine_request_path(
            candidate,
            allowed_roots=(root,),
            field_name="discovered attachment",
        )
        if not path.is_file() or path.suffix.casefold() != ".csv":
            continue
        kind = classify_csv(path)
        if kind is None:
            unclassified.append(path)
        else:
            candidates.setdefault(kind, []).append(path)
    ambiguous = {kind: paths for kind, paths in candidates.items() if len(paths) > 1}
    if ambiguous:
        details = "; ".join(
            f"{kind}={','.join(path.name for path in paths)}"
            for kind, paths in sorted(ambiguous.items())
        )
        raise CoworkInputError(f"ambiguous Cowork CSV inputs: {details}")
    return DiscoveredInputs(
        classified={kind: paths[0] for kind, paths in candidates.items()},
        unclassified_csvs=tuple(unclassified),
    )


def resolve_request_inputs(
    request: CoworkRunRequest,
    *,
    input_dir: str | Path | None = None,
    salary_csv: str | Path | None = None,
    entry_csv: str | Path | None = None,
    allowed_roots: Iterable[str | Path] = (),
) -> tuple[CoworkRunRequest, tuple[Path, ...]]:
    root_value = input_dir or request.input_dir
    root_path = (
        confine_request_path(
            root_value,
            allowed_roots=allowed_roots,
            field_name="input_dir",
        )
        if root_value not in (None, "")
        else None
    )
    discovered = (
        discover_csv_inputs(root_path)
        if root_path is not None
        else DiscoveredInputs(classified={}, unclassified_csvs=())
    )
    payload = request.to_dict()
    overrides = {"salary_csv": salary_csv, "entry_csv": entry_csv}
    explicit_file_values: list[Path] = []
    for value in overrides.values():
        if value in (None, ""):
            continue
        explicit_path = Path(str(value))
        if explicit_path.is_symlink():
            raise CoworkInputError(
                f"explicit attachment path must not be a symlink/reparse point: {value}"
            )
        explicit_file_values.append(explicit_path.resolve())
    explicit_files = tuple(explicit_file_values)
    roots = tuple(allowed_roots)
    for name in PATH_FIELDS:
        explicit = overrides.get(name)
        if explicit not in (None, ""):
            payload[name] = str(explicit)
        elif payload.get(name) in (None, "") and name in discovered.classified:
            payload[name] = str(discovered.classified[name])
    payload["input_dir"] = str(root_path) if root_path else None
    resolved = CoworkRunRequest.from_mapping(
        payload,
        allowed_roots=roots,
        allowed_files=explicit_files,
    )
    for required in ("salary_csv", "entry_csv"):
        if getattr(resolved, required) is None:
            raise CoworkInputError(
                f"could not identify exactly one {required} by CSV schema; "
                "attach the DraftKings salary and reserved-entry CSVs or provide explicit paths"
            )
    for name in PATH_FIELDS:
        value = getattr(resolved, name)
        if value is not None and not Path(value).is_file():
            raise CoworkInputError(f"{name} does not exist: {value}")
    return resolved, discovered.unclassified_csvs


def required_next_inputs(request: CoworkRunRequest) -> tuple[str, ...]:
    blockers: list[str] = []
    if request.payout_csv is None:
        blockers.append(
            "CONTEST_PAYOUT_REQUIRED: supply a complete payout CSV; do not infer tiers from the contest name"
        )
    if request.advertised_prize_value is None:
        blockers.append(
            "ADVERTISED_PRIZE_VALUE_REQUIRED: supply the contest's exact advertised cash-plus-ticket value"
        )
    if request.field_size is None:
        blockers.append(
            "FIELD_SIZE_REQUIRED: supply the contest's exact total entry count"
        )
    if request.objective == "SATELLITE" and request.ticket_face_value is None:
        blockers.append(
            "TICKET_FACE_VALUE_REQUIRED: supply the exact face value of each awarded ticket"
        )
    if request.assignment_csv is None:
        if request.team_projection_csv is None or request.player_opportunity_csv is None:
            blockers.append(
                "MODEL_INPUTS_REQUIRED: assemble both validated team-projection and player-opportunity CSVs from frozen approved evidence"
            )
        if request.source_ledger_json is None:
            blockers.append(
                "SOURCE_LEDGER_REQUIRED: bind the model inputs to a frozen provenance ledger before a Cowork model-assisted build"
            )
    if request.official_status_csv is None:
        blockers.append(
            "OFFICIAL_STATUS_REQUIRED: selected players need current exact-ID official activity evidence before certification"
        )
    return tuple(blockers)
