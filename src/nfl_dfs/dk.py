from __future__ import annotations

import csv
import io
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

from .contracts import (
    EngineMode,
    EntryAuthorization,
    GameContract,
    SalaryPlayer,
    SlateContract,
)
from .hashing import sha256_bytes

PARSER_VERSION = "dk_csv_v1"
_GAME_RE = re.compile(
    r"^(?P<away>[A-Z]{2,3})@(?P<home>[A-Z]{2,3})\s+"
    r"(?P<date>\d{2}/\d{2}/\d{4})\s+(?P<time>\d{2}:\d{2}[AP]M)\s+ET$"
)
CLASSIC_COLUMNS = ("QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX", "DST")
SHOWDOWN_COLUMNS = ("CPT", "FLEX", "FLEX", "FLEX", "FLEX", "FLEX")
_DRAFT_GROUP_COLUMNS = ("Draft Group", "Draft Group ID", "DraftGroup")


class DraftKingsParseError(ValueError):
    pass


@dataclass(frozen=True)
class EntryTemplate:
    path: Path
    raw_hash: str
    header: tuple[str, ...]
    roster_columns: tuple[str, ...]
    authorizations: tuple[EntryAuthorization, ...]
    encoding: str

    @property
    def mode(self) -> EngineMode:
        if self.roster_columns == CLASSIC_COLUMNS:
            return EngineMode.CLASSIC
        if self.roster_columns == SHOWDOWN_COLUMNS:
            return EngineMode.SHOWDOWN
        raise DraftKingsParseError(
            f"DK_ENTRY_GEOMETRY_UNKNOWN: unsupported roster columns: {self.roster_columns}"
        )

    @property
    def roster_start_index(self) -> int:
        try:
            return self.header.index("Entry Fee") + 1
        except ValueError as exc:
            raise DraftKingsParseError(
                "DK_ENTRY_HEADER_INVALID: entry template header lacks Entry Fee"
            ) from exc


def single_contest_problems(template: EntryTemplate) -> tuple[str, ...]:
    """Return fail-closed reasons when one entry file spans contest economics."""
    contest_ids = {entry.contest_id for entry in template.authorizations}
    entry_fees = {entry.entry_fee for entry in template.authorizations}
    problems: list[str] = []
    if len(contest_ids) != 1:
        problems.append(
            "MULTI_CONTEST_ENTRY_FILE_UNSUPPORTED: reserved entries must share one Contest ID"
        )
    if len(entry_fees) != 1:
        problems.append(
            "MIXED_ENTRY_FEES_UNSUPPORTED: reserved entries must share one entry fee"
        )
    return tuple(problems)


def require_single_contest(template: EntryTemplate) -> None:
    problems = single_contest_problems(template)
    if problems:
        raise DraftKingsParseError("; ".join(problems))


def _read_csv_bytes(raw: bytes, source: Path) -> tuple[str, list[list[str]], str]:
    digest = sha256_bytes(raw)
    encodings = ("utf-8-sig",) if raw.startswith(b"\xef\xbb\xbf") else ("utf-8", "cp1252")
    last_error: UnicodeDecodeError | None = None
    for encoding in encodings:
        try:
            text = raw.decode(encoding)
            return encoding, list(csv.reader(io.StringIO(text, newline=""))), digest
        except UnicodeDecodeError as exc:
            last_error = exc
    raise DraftKingsParseError(
        f"DK_CSV_ENCODING_UNSUPPORTED: unsupported CSV encoding: {source}"
    ) from last_error


def _read_text_csv(path: Path) -> tuple[str, list[list[str]], str]:
    return _read_csv_bytes(path.read_bytes(), path)


def _parse_fee(raw: str) -> float:
    cleaned = raw.strip().replace("$", "").replace(",", "")
    if not cleaned:
        raise DraftKingsParseError("DK_ENTRY_FEE_INVALID: entry fee is blank")
    try:
        value = float(cleaned)
    except ValueError as exc:
        raise DraftKingsParseError(f"DK_ENTRY_FEE_INVALID: invalid entry fee: {raw!r}") from exc
    if not math.isfinite(value) or value < 0:
        raise DraftKingsParseError(f"DK_ENTRY_FEE_INVALID: invalid entry fee: {raw!r}")
    return value


def _parse_entries_rows(
    csv_path: Path,
    encoding: str,
    rows: list[list[str]],
    raw_hash: str,
) -> EntryTemplate:
    if not rows or len(rows[0]) < 10:
        raise DraftKingsParseError("DK_ENTRY_HEADER_INVALID: entry CSV has no usable header")
    header = tuple(rows[0])
    expected_prefix = ("Entry ID", "Contest Name", "Contest ID", "Entry Fee")
    if header[: len(expected_prefix)] != expected_prefix:
        raise DraftKingsParseError(
            f"DK_ENTRY_HEADER_INVALID: entry CSV must begin with the exact columns {expected_prefix}"
        )
    try:
        fee_index = header.index("Entry Fee")
    except ValueError as exc:
        raise DraftKingsParseError("DK_ENTRY_HEADER_INVALID: entry CSV lacks Entry Fee") from exc
    roster_end = len(header)
    for marker in ("", "Instructions"):
        if marker in header[fee_index + 1 :]:
            roster_end = min(roster_end, header.index(marker, fee_index + 1))
    roster_columns = tuple(header[fee_index + 1 : roster_end])
    if roster_columns not in {CLASSIC_COLUMNS, SHOWDOWN_COLUMNS}:
        raise DraftKingsParseError(
            f"DK_ENTRY_GEOMETRY_UNKNOWN: unknown DraftKings template geometry: {roster_columns}"
        )

    # A real DraftKings Classic entries export repeats the player-pool table to
    # the right of the entry block, starting in the Instructions column, so every
    # entry row past the six instruction lines is wider than the header. The
    # supplied fixture carries only two entries, both inside the instructions
    # block, so that shape was never parsed and the malformed-row guard below
    # rejected any export with more than a handful of entries. Locate the
    # embedded table from the file itself, so the guard still catches a row that
    # is genuinely misshapen rather than merely wide.
    embedded_pool_start: int | None = None
    for row in rows[1:]:
        if len(row) <= len(header):
            continue
        for index in range(roster_end, len(row)):
            if row[index].strip() == "Position":
                embedded_pool_start = index
                break
        if embedded_pool_start is not None:
            break

    authorizations: list[EntryAuthorization] = []
    seen_entries: set[str] = set()
    for row in rows[1:]:
        padded = row + [""] * max(0, roster_end - len(row))
        entry_id = padded[0].strip()
        if not entry_id:
            continue
        # Cells at or past `roster_end` are never read, so trailing width cannot
        # misalign a roster. Only unexplained cells between the roster block and
        # the embedded pool table can, and those still fail closed.
        if len(row) > len(header) and (
            embedded_pool_start is None
            or any(cell.strip() for cell in row[roster_end:embedded_pool_start])
        ):
            raise DraftKingsParseError(
                f"DK_ENTRY_ROW_MISSHAPEN: entry row for {entry_id!r} has more cells than the header"
            )
        if not entry_id.isdigit():
            raise DraftKingsParseError(f"DK_ENTRY_ID_INVALID: non-numeric Entry ID: {entry_id!r}")
        if entry_id in seen_entries:
            raise DraftKingsParseError(f"DK_ENTRY_ID_DUPLICATE: duplicate Entry ID: {entry_id}")
        contest_id = padded[2].strip()
        if not contest_id.isdigit():
            raise DraftKingsParseError(f"DK_CONTEST_ID_INVALID: invalid Contest ID for Entry {entry_id}")
        cells = tuple(cell.strip() for cell in padded[fee_index + 1 : roster_end])
        authorizations.append(
            EntryAuthorization(
                entry_id=entry_id,
                contest_id=contest_id,
                contest_name=padded[1].strip(),
                entry_fee=_parse_fee(padded[fee_index]),
                existing_cells=cells,
            )
        )
        seen_entries.add(entry_id)
    if not authorizations:
        raise DraftKingsParseError("DK_ENTRY_NONE_AUTHORIZED: entry CSV contains no authorized entries")
    return EntryTemplate(
        path=csv_path,
        raw_hash=raw_hash,
        header=header,
        roster_columns=roster_columns,
        authorizations=tuple(authorizations),
        encoding=encoding,
    )


def parse_entries(path: str | Path) -> EntryTemplate:
    csv_path = Path(path).resolve()
    encoding, rows, raw_hash = _read_text_csv(csv_path)
    return _parse_entries_rows(csv_path, encoding, rows, raw_hash)


def parse_entry_bytes(raw: bytes, *, source_name: str = "late-swap-output.csv") -> EntryTemplate:
    """Reparse candidate entry bytes without first persisting an upload-shaped file."""
    source = Path(source_name)
    encoding, rows, raw_hash = _read_csv_bytes(raw, source)
    return _parse_entries_rows(source, encoding, rows, raw_hash)


def embedded_pool_ids(raw: bytes) -> tuple[str, ...] | None:
    """The DraftKings IDs of the player table an entries export carries, or None.

    A real export repeats the draft group's player table to the right of the
    entry block (see `_parse_entries_rows`). Its `ID` column is the exact set of
    salary rows the entries were reserved against, so a salary file from another
    slate of the same mode shows up as a different set. Only the `ID` column is
    read; every other cell of the table stays untouched raw bytes.
    """

    _encoding, rows, _digest = _read_csv_bytes(raw, Path("entries.csv"))
    if not rows:
        return None
    width = len(rows[0])
    for number, row in enumerate(rows[1:], start=1):
        cells = [cell.strip() for cell in row]
        if len(cells) <= width or "Position" not in cells[width - 1 :]:
            continue
        start = cells.index("Position", width - 1)
        if "ID" not in cells[start:]:
            raise DraftKingsParseError(
                f"DK_ENTRY_POOL_TABLE_INVALID: the embedded player table at row {number + 1} has no ID column"
            )
        column = cells.index("ID", start)
        ids = tuple(
            later[column].strip()
            for later in rows[number + 1 :]
            if len(later) > column and later[column].strip()
        )
        if not ids or len(set(ids)) != len(ids) or not all(value.isdigit() for value in ids):
            raise DraftKingsParseError(
                "DK_ENTRY_POOL_TABLE_INVALID: the embedded player table's IDs are blank, "
                "repeated or not numeric"
            )
        return ids
    return None


def _parse_game_info(raw: str) -> tuple[str, str, str, datetime]:
    match = _GAME_RE.match(raw.strip())
    if not match:
        raise DraftKingsParseError(f"DK_SALARY_GAME_INFO_INVALID: invalid Game Info: {raw!r}")
    away = match.group("away")
    home = match.group("home")
    lock = datetime.strptime(
        f"{match.group('date')} {match.group('time')}", "%m/%d/%Y %I:%M%p"
    ).replace(tzinfo=ZoneInfo("America/New_York"))
    return f"{away}@{home}", away, home, lock


def parse_salaries(path: str | Path, draft_group: str | None = None) -> SlateContract:
    csv_path = Path(path).resolve()
    encoding, rows, raw_hash = _read_text_csv(csv_path)
    del encoding
    if len(rows) < 2:
        raise DraftKingsParseError("DK_SALARY_EMPTY: salary CSV is empty")
    required = {
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
    header = rows[0]
    missing = required.difference(header)
    if missing:
        raise DraftKingsParseError(f"DK_SALARY_COLUMNS_MISSING: salary CSV missing columns: {sorted(missing)}")
    duplicated = sorted(name for name in required if header.count(name) != 1)
    if duplicated:
        raise DraftKingsParseError(
            f"DK_SALARY_COLUMNS_DUPLICATED: salary CSV required columns must appear exactly once: {duplicated}"
        )
    index = {name: header.index(name) for name in required}
    data_rows: list[tuple[int, list[str]]] = []
    for row_number, row in enumerate(rows[1:], start=2):
        if not row or not any(cell.strip() for cell in row):
            continue
        if len(row) < len(header):
            raise DraftKingsParseError(f"DK_SALARY_ROW_SHORT: short salary row {row_number}")
        data_rows.append((row_number, row))
    roster_values = {row[index["Roster Position"]].strip() for _, row in data_rows}
    if roster_values == {"CPT", "FLEX"}:
        mode = EngineMode.SHOWDOWN
    elif roster_values.issubset({"QB", "RB/FLEX", "WR/FLEX", "TE/FLEX", "DST"}):
        mode = EngineMode.CLASSIC
    else:
        raise DraftKingsParseError(
            f"DK_SALARY_ROSTER_POSITIONS_UNSUPPORTED: unsupported salary roster positions: "
            f"{sorted(roster_values)}"
        )

    present_draft_group_columns = [name for name in _DRAFT_GROUP_COLUMNS if name in header]
    if len(present_draft_group_columns) > 1:
        raise DraftKingsParseError(
            "DK_DRAFT_GROUP_AMBIGUOUS: salary CSV has ambiguous draft-group columns: "
            f"{present_draft_group_columns}"
        )
    embedded_draft_group: str | None = None
    if present_draft_group_columns:
        column = header.index(present_draft_group_columns[0])
        values = {
            row[column].strip()
            for _row_number, row in data_rows
            if row[column].strip()
        }
        if len(values) != 1:
            raise DraftKingsParseError(
                f"DRAFT_GROUP_MIXED_OR_BLANK:{sorted(values)}"
            )
        embedded_draft_group = next(iter(values))
        if draft_group is not None and draft_group != embedded_draft_group:
            raise DraftKingsParseError(
                "DK_DRAFT_GROUP_MISMATCH: salary draft group does not match the required "
                "contest draft group: "
                f"salary={embedded_draft_group!r}, required={draft_group!r}"
            )

    players: list[SalaryPlayer] = []
    games: dict[str, GameContract] = {}
    seen_ids: set[str] = set()
    for row_number, row in data_rows:
        dk_id = row[index["ID"]].strip()
        if not dk_id.isdigit() or dk_id in seen_ids:
            raise DraftKingsParseError(
                f"DK_SALARY_ID_INVALID: invalid or duplicate DK ID at row {row_number}: {dk_id!r}"
            )
        game_id, away, home, lock_at = _parse_game_info(row[index["Game Info"]])
        team = row[index["TeamAbbrev"]].strip()
        if team not in {away, home}:
            raise DraftKingsParseError(
                f"DK_SALARY_TEAM_NOT_IN_GAME: team {team} not in game {game_id} at row {row_number}"
            )
        opponent = home if team == away else away
        try:
            salary = int(row[index["Salary"]])
        except ValueError as exc:
            raise DraftKingsParseError(
                f"DK_SALARY_VALUE_INVALID: invalid salary at row {row_number}"
            ) from exc
        roster_raw = row[index["Roster Position"]].strip()
        roster_positions = tuple(roster_raw.split("/"))
        position = row[index["Position"]].strip()
        role = roster_raw if mode is EngineMode.SHOWDOWN else None
        name = row[index["Name"]].strip()
        if not name or not position or not team:
            raise DraftKingsParseError(
                f"DK_SALARY_ROW_BLANK_FIELD: blank name, position, or team at salary row {row_number}"
            )
        if salary <= 0:
            raise DraftKingsParseError(
                f"DK_SALARY_VALUE_INVALID: salary must be positive at row {row_number}"
            )
        if mode is EngineMode.CLASSIC:
            expected_roster = {
                "QB": "QB",
                "RB": "RB/FLEX",
                "WR": "WR/FLEX",
                "TE": "TE/FLEX",
                "DST": "DST",
            }
            if position not in expected_roster or roster_raw != expected_roster[position]:
                raise DraftKingsParseError(
                    f"DK_SALARY_POSITION_ROSTER_MISMATCH: Classic position/roster mismatch at row {row_number}: "
                    f"position={position!r}, roster={roster_raw!r}"
                )
        players.append(
            SalaryPlayer(
                dk_id=dk_id,
                name=name,
                position=position,
                roster_positions=roster_positions,
                salary=salary,
                team=team,
                opponent=opponent,
                game_id=game_id,
                lock_at=lock_at,
                status_raw=row[index["Status"]].strip(),
                underlying_id=f"{team}|{position}|{name}",
                role=role,
            )
        )
        game = GameContract(
            game_id=game_id, away_team=away, home_team=home, lock_at=lock_at
        )
        if game_id in games and games[game_id] != game:
            raise DraftKingsParseError(
                f"DK_SALARY_LOCK_CONFLICT: conflicting lock metadata for game {game_id} at row {row_number}"
            )
        games[game_id] = game
        seen_ids.add(dk_id)

    _validate_salary_pool(players, mode)
    return SlateContract(
        mode=mode,
        draft_group=embedded_draft_group or draft_group or f"salary-sha256:{raw_hash}",
        games=tuple(sorted(games.values(), key=lambda game: (game.lock_at, game.game_id))),
        scoring_version="draftkings_nfl_scoring_2026_fixture_v1",
        salary_hash=raw_hash,
        players=tuple(players),
    )


def _validate_salary_pool(players: Iterable[SalaryPlayer], mode: EngineMode) -> None:
    pool = list(players)
    if not pool:
        raise DraftKingsParseError("DK_SALARY_POOL_EMPTY: salary pool has no players")
    if mode is EngineMode.CLASSIC:
        if len({player.game_id for player in pool}) < 2:
            raise DraftKingsParseError(
                "DK_SLATE_SHAPE_INVALID: Classic salary pool must contain at least two games"
            )
        identity_counts: dict[str, int] = defaultdict(int)
        for player in pool:
            identity_counts[player.underlying_id] += 1
        collisions = sorted(
            identity for identity, count in identity_counts.items() if count > 1
        )
        if collisions:
            raise DraftKingsParseError(
                "DK_IDENTITY_COLLISION: ambiguous same-name/team/position identity collision; "
                "exact disambiguation "
                f"is required: {collisions}"
            )
        games_by_team: dict[str, set[str]] = defaultdict(set)
        for player in pool:
            games_by_team[player.team].add(player.game_id)
        conflicted_teams = {
            team: sorted(games)
            for team, games in games_by_team.items()
            if len(games) != 1
        }
        if conflicted_teams:
            raise DraftKingsParseError(
                f"DK_SLATE_SHAPE_INVALID: Classic team appears in multiple games: {conflicted_teams}"
            )
    if mode is EngineMode.SHOWDOWN:
        if len({player.game_id for player in pool}) != 1 or len(
            {player.team for player in pool}
        ) != 2:
            raise DraftKingsParseError(
                "DK_SLATE_SHAPE_INVALID: Showdown salary pool must contain exactly one game and two teams"
            )
        by_person: dict[str, dict[str, SalaryPlayer]] = defaultdict(dict)
        duplicate_roles: list[str] = []
        for player in pool:
            assert player.role is not None
            if player.role in by_person[player.underlying_id]:
                duplicate_roles.append(f"{player.underlying_id}:{player.role}")
            by_person[player.underlying_id][player.role] = player
        anomalies: list[str] = duplicate_roles
        for person, roles in by_person.items():
            if set(roles) != {"CPT", "FLEX"}:
                anomalies.append(f"{person}: missing role")
                continue
            if roles["CPT"].dk_id == roles["FLEX"].dk_id:
                anomalies.append(f"{person}: role IDs are not distinct")
            if roles["CPT"].salary != round(roles["FLEX"].salary * 1.5):
                anomalies.append(f"{person}: captain salary is not exactly 1.5x")
        if anomalies:
            raise DraftKingsParseError("DK_SHOWDOWN_ROLE_PAIR_INVALID: " + "; ".join(anomalies[:10]))
        if len(pool) != 2 * len(by_person):
            raise DraftKingsParseError(
                "DK_SHOWDOWN_ROLE_PAIR_INVALID: Showdown role row count does not reconcile"
            )
        if len(by_person) < 6:
            raise DraftKingsParseError(
                "DK_SLATE_SHAPE_INVALID: Showdown pool needs at least six underlying players"
            )
    else:
        counts = Counter(player.position for player in pool)
        minimum_counts = {"QB": 1, "RB": 2, "WR": 3, "TE": 1, "DST": 1}
        for required, minimum in minimum_counts.items():
            if counts[required] < minimum:
                raise DraftKingsParseError(
                    f"DK_SLATE_SHAPE_INVALID: Classic pool needs at least {minimum} {required} rows"
                )
        if counts["RB"] + counts["WR"] + counts["TE"] < 7:
            raise DraftKingsParseError(
                "DK_SLATE_SHAPE_INVALID: Classic pool lacks enough RB/WR/TE rows to fill FLEX"
            )


def reconcile_template(template: EntryTemplate, slate: SlateContract) -> None:
    if template.mode is not slate.mode:
        raise DraftKingsParseError(
            f"DK_TEMPLATE_MODE_MISMATCH: template is {template.mode.value}, "
            f"salary pool is {slate.mode.value}"
        )
    widths = {len(entry.existing_cells) for entry in template.authorizations}
    expected = 9 if slate.mode is EngineMode.CLASSIC else 6
    if widths != {expected}:
        raise DraftKingsParseError(
            "DK_TEMPLATE_MODE_MISMATCH: entry roster cell count does not match slate mode"
        )
