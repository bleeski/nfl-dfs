from __future__ import annotations

import csv
import io
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
from .hashing import sha256_file

PARSER_VERSION = "dk_csv_v1"
_GAME_RE = re.compile(
    r"^(?P<away>[A-Z]{2,3})@(?P<home>[A-Z]{2,3})\s+"
    r"(?P<date>\d{2}/\d{2}/\d{4})\s+(?P<time>\d{2}:\d{2}[AP]M)\s+ET$"
)
CLASSIC_COLUMNS = ("QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX", "DST")
SHOWDOWN_COLUMNS = ("CPT", "FLEX", "FLEX", "FLEX", "FLEX", "FLEX")


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
        raise DraftKingsParseError(f"unsupported roster columns: {self.roster_columns}")


def _read_text_csv(path: Path) -> tuple[str, list[list[str]]]:
    raw = path.read_bytes()
    encodings = ("utf-8-sig",) if raw.startswith(b"\xef\xbb\xbf") else ("utf-8", "cp1252")
    last_error: UnicodeDecodeError | None = None
    for encoding in encodings:
        try:
            text = raw.decode(encoding)
            return encoding, list(csv.reader(io.StringIO(text, newline="")))
        except UnicodeDecodeError as exc:
            last_error = exc
    raise DraftKingsParseError(f"unsupported CSV encoding: {path}") from last_error


def _parse_fee(raw: str) -> float:
    cleaned = raw.strip().replace("$", "").replace(",", "")
    if not cleaned:
        raise DraftKingsParseError("entry fee is blank")
    try:
        return float(cleaned)
    except ValueError as exc:
        raise DraftKingsParseError(f"invalid entry fee: {raw!r}") from exc


def parse_entries(path: str | Path) -> EntryTemplate:
    csv_path = Path(path).resolve()
    encoding, rows = _read_text_csv(csv_path)
    if not rows or len(rows[0]) < 10:
        raise DraftKingsParseError("entry CSV has no usable header")
    header = tuple(rows[0])
    try:
        fee_index = header.index("Entry Fee")
    except ValueError as exc:
        raise DraftKingsParseError("entry CSV lacks Entry Fee") from exc
    roster_end = len(header)
    for marker in ("", "Instructions"):
        if marker in header[fee_index + 1 :]:
            roster_end = min(roster_end, header.index(marker, fee_index + 1))
    roster_columns = tuple(header[fee_index + 1 : roster_end])
    if roster_columns not in {CLASSIC_COLUMNS, SHOWDOWN_COLUMNS}:
        raise DraftKingsParseError(f"unknown DraftKings template geometry: {roster_columns}")

    authorizations: list[EntryAuthorization] = []
    seen_entries: set[str] = set()
    for row in rows[1:]:
        padded = row + [""] * max(0, roster_end - len(row))
        entry_id = padded[0].strip()
        if not entry_id:
            continue
        if not entry_id.isdigit():
            raise DraftKingsParseError(f"non-numeric Entry ID: {entry_id!r}")
        if entry_id in seen_entries:
            raise DraftKingsParseError(f"duplicate Entry ID: {entry_id}")
        contest_id = padded[2].strip()
        if not contest_id.isdigit():
            raise DraftKingsParseError(f"invalid Contest ID for Entry {entry_id}")
        cells = tuple(cell.strip() for cell in padded[fee_index + 1 : roster_end])
        authorizations.append(
            EntryAuthorization(
                entry_id=entry_id,
                contest_id=contest_id,
                contest_name=padded[1].strip(),
                entry_fee=_parse_fee(padded[3]),
                existing_cells=cells,
            )
        )
        seen_entries.add(entry_id)
    if not authorizations:
        raise DraftKingsParseError("entry CSV contains no authorized entries")
    return EntryTemplate(
        path=csv_path,
        raw_hash=sha256_file(csv_path),
        header=header,
        roster_columns=roster_columns,
        authorizations=tuple(authorizations),
        encoding=encoding,
    )


def _parse_game_info(raw: str) -> tuple[str, str, str, datetime]:
    match = _GAME_RE.match(raw.strip())
    if not match:
        raise DraftKingsParseError(f"invalid Game Info: {raw!r}")
    away = match.group("away")
    home = match.group("home")
    lock = datetime.strptime(
        f"{match.group('date')} {match.group('time')}", "%m/%d/%Y %I:%M%p"
    ).replace(tzinfo=ZoneInfo("America/New_York"))
    return f"{away}@{home}", away, home, lock


def parse_salaries(path: str | Path, draft_group: str | None = None) -> SlateContract:
    csv_path = Path(path).resolve()
    encoding, rows = _read_text_csv(csv_path)
    del encoding
    if len(rows) < 2:
        raise DraftKingsParseError("salary CSV is empty")
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
        raise DraftKingsParseError(f"salary CSV missing columns: {sorted(missing)}")
    index = {name: header.index(name) for name in required}
    roster_values = {row[index["Roster Position"]].strip() for row in rows[1:] if row}
    if roster_values == {"CPT", "FLEX"}:
        mode = EngineMode.SHOWDOWN
    elif roster_values.issubset({"QB", "RB/FLEX", "WR/FLEX", "TE/FLEX", "DST"}):
        mode = EngineMode.CLASSIC
    else:
        raise DraftKingsParseError(f"unsupported salary roster positions: {sorted(roster_values)}")

    players: list[SalaryPlayer] = []
    games: dict[str, GameContract] = {}
    seen_ids: set[str] = set()
    for row_number, row in enumerate(rows[1:], start=2):
        if not row or not any(cell.strip() for cell in row):
            continue
        if len(row) < len(header):
            raise DraftKingsParseError(f"short salary row {row_number}")
        dk_id = row[index["ID"]].strip()
        if not dk_id.isdigit() or dk_id in seen_ids:
            raise DraftKingsParseError(f"invalid or duplicate DK ID at row {row_number}: {dk_id!r}")
        game_id, away, home, lock_at = _parse_game_info(row[index["Game Info"]])
        team = row[index["TeamAbbrev"]].strip()
        if team not in {away, home}:
            raise DraftKingsParseError(f"team {team} not in game {game_id} at row {row_number}")
        opponent = home if team == away else away
        try:
            salary = int(row[index["Salary"]])
        except ValueError as exc:
            raise DraftKingsParseError(f"invalid salary at row {row_number}") from exc
        roster_raw = row[index["Roster Position"]].strip()
        roster_positions = tuple(roster_raw.split("/"))
        position = row[index["Position"]].strip()
        role = roster_raw if mode is EngineMode.SHOWDOWN else None
        underlying = f"{team}|{position}|{row[index['Name']].strip()}"
        players.append(
            SalaryPlayer(
                dk_id=dk_id,
                name=row[index["Name"]].strip(),
                position=position,
                roster_positions=roster_positions,
                salary=salary,
                team=team,
                opponent=opponent,
                game_id=game_id,
                lock_at=lock_at,
                status_raw=row[index["Status"]].strip(),
                underlying_id=underlying,
                role=role,
            )
        )
        games[game_id] = GameContract(
            game_id=game_id, away_team=away, home_team=home, lock_at=lock_at
        )
        seen_ids.add(dk_id)

    _validate_salary_pool(players, mode)
    raw_hash = sha256_file(csv_path)
    return SlateContract(
        mode=mode,
        draft_group=draft_group or raw_hash[:16],
        games=tuple(sorted(games.values(), key=lambda game: (game.lock_at, game.game_id))),
        scoring_version="draftkings_nfl_scoring_2026_fixture_v1",
        salary_hash=raw_hash,
        players=tuple(players),
    )


def _validate_salary_pool(players: Iterable[SalaryPlayer], mode: EngineMode) -> None:
    pool = list(players)
    if not pool:
        raise DraftKingsParseError("salary pool has no players")
    if mode is EngineMode.SHOWDOWN:
        by_person: dict[str, dict[str, SalaryPlayer]] = defaultdict(dict)
        for player in pool:
            assert player.role is not None
            by_person[player.underlying_id][player.role] = player
        anomalies: list[str] = []
        for person, roles in by_person.items():
            if set(roles) != {"CPT", "FLEX"}:
                anomalies.append(f"{person}: missing role")
                continue
            if roles["CPT"].dk_id == roles["FLEX"].dk_id:
                anomalies.append(f"{person}: role IDs are not distinct")
            if roles["CPT"].salary != round(roles["FLEX"].salary * 1.5):
                anomalies.append(f"{person}: captain salary is not exactly 1.5x")
        if anomalies:
            raise DraftKingsParseError("; ".join(anomalies[:10]))
        if len(pool) != 2 * len(by_person):
            raise DraftKingsParseError("Showdown role row count does not reconcile")
    else:
        counts = Counter(player.position for player in pool)
        for required in ("QB", "RB", "WR", "TE", "DST"):
            if not counts[required]:
                raise DraftKingsParseError(f"Classic pool has no {required}")


def reconcile_template(template: EntryTemplate, slate: SlateContract) -> None:
    if template.mode is not slate.mode:
        raise DraftKingsParseError(
            f"template is {template.mode.value}, salary pool is {slate.mode.value}"
        )
    widths = {len(entry.existing_cells) for entry in template.authorizations}
    expected = 9 if slate.mode is EngineMode.CLASSIC else 6
    if widths != {expected}:
        raise DraftKingsParseError("entry roster cell count does not match slate mode")
