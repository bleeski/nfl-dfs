"""DraftKings entry-history intake (Session 69, `nfl_dk_entry_history_v1`).

Ben downloads his account's contest entry history from DraftKings by hand; nothing in this repository fetches it. One
row per entry, every sport, every season: the place, the points, the field size, the fee and the winnings of each entry,
keyed by the Entry ID (`Entry_Key`) and the Contest ID (`Contest_Key`) the engine fills. Every later results session
(70 to 74) reads it through this contract.

The file is refused whole, never repaired and never used in part, and every bad row is named in file order with its row
number (the header is row 1). Structure is checked on every row of every sport: decoding, the header, the cell count
and quoting, the last line's terminator, the sport and game type, the entry key's form and uniqueness, the contest key's
form. Value rules (the contest time, place, points, money, field size, places paid and per-contest agreement) run on
every row by the same code; a failure on an NFL row, or in a contest with an NFL row, refuses the file, and a failure on
any other sport's row is a named note. The export is cumulative, so one unforeseen row in a sport this engine never
reads must not refuse every future export. A format change that breaks NFL rows is a new contract version, never a
relaxation of this one.

A `Places_Paid` above `Contest_Entries` is kept and named (a free contest that ran under its guaranteed size pays more
places than it had entries), never refused. Notes are not gate codes: they stop nothing. No problem or note ever echoes
a cell value, and the summary carries no money.

`run_intake` (Session 69b, `nfl results-intake`) keeps one hash-named, write-once snapshot of an accepted file under
`<results root>/inbox/` and writes the NFL rows and the summary under `<results root>/normalized/<sha256>/`, each file
written once and never overwritten. A refused file writes nothing.

`does_not_establish`: expected value or ROI, win or cash probability, an edge, calibration, which entries the engine
built, upload clearance.
"""

from __future__ import annotations

import contextlib
import csv
import io
import os
import re
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Mapping, Sequence
from zoneinfo import ZoneInfo

from .contest_facts import canonical_bytes
from .hashing import sha256_bytes, sha256_file

CONTRACT_VERSION = "nfl_dk_entry_history_v1"
SUMMARY_VERSION = "nfl_dk_entry_history_intake_v1"
HEADER = (
    "Sport",
    "Game_Type",
    "Entry_Key",
    "Entry",
    "Contest_Key",
    "Contest_Date_EST",
    "Place",
    "Points",
    "Winnings_Non_Ticket",
    "Winnings_Ticket",
    "Contest_Entries",
    "Entry_Fee",
    "Prize_Pool",
    "Places_Paid",
)
NFL = "NFL"
EASTERN = ZoneInfo("America/New_York")
MAX_BYTES = 64 * 1024 * 1024
MONEY_COLUMNS = ("Winnings_Non_Ticket", "Winnings_Ticket", "Entry_Fee", "Prize_Pool")
# Columns every row of one contest must agree on. `Entry` is not one: DraftKings appends an ` (n/m)` entry ordinal.
AGREEMENT_COLUMNS = (
    "Sport", "Game_Type", "Contest_Date_EST", "Contest_Entries", "Entry_Fee", "Prize_Pool", "Places_Paid")

DOES_NOT_ESTABLISH = (
    "EXPECTED_VALUE_OR_ROI",
    "WIN_OR_CASH_PROBABILITY",
    "AN_EDGE_OR_ITS_ABSENCE",
    "CALIBRATION",
    "WHICH_ENTRIES_THE_ENGINE_BUILT",
    "UPLOAD_CLEARANCE",
)

# The codes the parser names; each is emitted as a full literal below (the gate registry scan reads them).
PARSE_CODES = (
    "ENTRY_HISTORY_FILE_EMPTY",
    "ENTRY_HISTORY_FILE_TOO_LARGE",
    "ENTRY_HISTORY_NOT_TEXT",
    "ENTRY_HISTORY_HEADER_INVALID",
    "ENTRY_HISTORY_NO_ROWS",
    "ENTRY_HISTORY_ROW_MISSHAPEN",
    "ENTRY_HISTORY_SPORT_INVALID",
    "ENTRY_HISTORY_GAME_TYPE_INVALID",
    "ENTRY_HISTORY_ENTRY_KEY_INVALID",
    "ENTRY_HISTORY_ENTRY_KEY_DUPLICATE",
    "ENTRY_HISTORY_CONTEST_KEY_INVALID",
    "ENTRY_HISTORY_CONTEST_DATE_INVALID",
    "ENTRY_HISTORY_PLACE_INVALID",
    "ENTRY_HISTORY_PLACE_OUTSIDE_FIELD",
    "ENTRY_HISTORY_POINTS_INVALID",
    "ENTRY_HISTORY_MONEY_INVALID",
    "ENTRY_HISTORY_CONTEST_ENTRIES_INVALID",
    "ENTRY_HISTORY_PLACES_PAID_INVALID",
    "ENTRY_HISTORY_CONTEST_DISAGREES",
    "ENTRY_HISTORY_NO_NFL_ROWS",
)
# Data notes. Not gate codes: they are built by `_note`, never `_problem`, and nothing they name stops anything.
NOTE_KINDS = (
    "PLACES_PAID_ABOVE_CONTEST_ENTRIES",
    "CONTEST_TIME_AMBIGUOUS",
    "CONTEST_TIME_NONEXISTENT",
    "NON_NFL_RULE_NOT_MET",
)

_SPORT = re.compile(r"[A-Z][A-Z0-9]{0,15}")
_KEY = re.compile(r"[1-9][0-9]{0,17}")
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}")
_COUNT = re.compile(r"0|[1-9][0-9]{0,8}")
_POSITIVE = re.compile(r"[1-9][0-9]{0,8}")
_POINTS = re.compile(r"-?(?:0|[1-9][0-9]{0,8})(?:\.[0-9]{1,2})?")
# At most three comma groups ($999,999,999,999.99), read as exact integer cents.
_MONEY = re.compile(r"\$(?:0|[1-9][0-9]{0,2}(?:,[0-9]{3}){0,3})\.[0-9]{2}")


class EntryHistoryRefused(Exception):
    """The whole file is refused; `problems` names every bad row in file order."""

    def __init__(self, problems: Sequence[str]):
        super().__init__(";".join(problems))
        self.problems = tuple(problems)


@dataclass(frozen=True)
class HistoryRow:
    """One entry. A value is None only on a non-NFL row whose cell broke a value rule (named in a note)."""

    row: int
    sport: str
    game_type: str
    entry_key: str
    entry_name: str
    contest_key: str
    contest_start_text: str
    contest_start: str | None
    place: int | None
    points_hundredths: int | None
    winnings_non_ticket_cents: int | None
    winnings_ticket_cents: int | None
    contest_entries: int | None
    entry_fee_cents: int | None
    prize_pool_cents: int | None
    places_paid: int | None
    places_paid_above_entries: bool

    @property
    def is_nfl(self) -> bool:
        return self.sport == NFL


@dataclass(frozen=True)
class EntryHistory:
    rows: tuple[HistoryRow, ...]
    notes: tuple[dict, ...] = field(default=())

    @property
    def nfl_rows(self) -> tuple[HistoryRow, ...]:
        return tuple(row for row in self.rows if row.is_nfl)


def _problem(code: str, detail: str = "") -> str:
    return f"{code}:{detail}" if detail else code


def _note(kind: str, number: int, sport: str, **detail: object) -> dict:
    return {"kind": kind, "row": number, "sport": sport, **detail}


# ------------------------------------------------------------------------------------ cell readers


def _count(text: str, pattern: re.Pattern[str] = _COUNT) -> int | None:
    return int(text) if pattern.fullmatch(text) else None


def _hundredths(text: str) -> int | None:
    return int(Decimal(text) * 100) if _POINTS.fullmatch(text) else None


def _cents(text: str) -> int | None:
    return int(text[1:].replace(",", "").replace(".", "")) if _MONEY.fullmatch(text) else None


def _contest_start(text: str) -> tuple[str | None, str | None]:
    """The ISO time with its Eastern offset (`fold=0`), and the note kind when the wall time is ambiguous or skipped."""

    if not _DATE.fullmatch(text):
        return None, None
    try:
        local = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None, None
    first, second = local.replace(tzinfo=EASTERN, fold=0), local.replace(tzinfo=EASTERN, fold=1)
    kind = None
    if first.utcoffset() != second.utcoffset():
        round_trip = first.astimezone(timezone.utc).astimezone(EASTERN).replace(tzinfo=None)
        kind = "CONTEST_TIME_AMBIGUOUS" if round_trip == local else "CONTEST_TIME_NONEXISTENT"
    return first.isoformat(), kind


def _header_problem(header: Sequence[str]) -> str | None:
    """None for the exact header; otherwise what is wrong, by expected name and position, never the file's own text."""

    found = tuple(header)
    if found == HEADER:
        return None
    if len(found) == len(HEADER) and sorted(found) == sorted(HEADER):
        position = next(index for index, (got, want) in enumerate(zip(found, HEADER), start=1) if got != want)
        return _problem("ENTRY_HISTORY_HEADER_INVALID", f"order:position={position}")
    missing = [name for name in HEADER if name not in found]
    extra = len(found) - (len(HEADER) - len(missing))  # every column beyond one per expected name present
    return _problem("ENTRY_HISTORY_HEADER_INVALID", f"missing={'|'.join(missing)}:extra={extra}")


# ------------------------------------------------------------------------------------------ parser


def _records(raw: bytes) -> list[tuple[int, list[str]]]:
    """`(record number, cells)` for every non-blank record, or the refusal for bytes that are not a readable CSV."""

    if not raw:
        raise EntryHistoryRefused([_problem("ENTRY_HISTORY_FILE_EMPTY")])
    if len(raw) > MAX_BYTES:
        raise EntryHistoryRefused([_problem("ENTRY_HISTORY_FILE_TOO_LARGE")])
    if b"\x00" in raw:
        raise EntryHistoryRefused([_problem("ENTRY_HISTORY_NOT_TEXT")])
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise EntryHistoryRefused([_problem("ENTRY_HISTORY_NOT_TEXT")]) from None
    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    records: list[tuple[int, list[str]]] = []
    try:
        for number, cells in enumerate(reader, start=1):
            if cells:
                records.append((number, cells))
    except csv.Error:
        raise EntryHistoryRefused([_problem("ENTRY_HISTORY_ROW_MISSHAPEN", f"csv:line={reader.line_num}")]) from None
    if not records:
        raise EntryHistoryRefused([_problem("ENTRY_HISTORY_FILE_EMPTY")])
    return records


def _value_rules(number: int, cells: Mapping[str, str]) -> tuple[dict[str, object], list[str], str | None]:
    """The row's parsed values, the value rules it breaks (in column order) and its contest-time note kind."""

    broken: list[str] = []
    where = f"row={number}"
    start, time_kind = _contest_start(cells["Contest_Date_EST"])
    if start is None:
        broken.append(_problem("ENTRY_HISTORY_CONTEST_DATE_INVALID", where))
    entries = _count(cells["Contest_Entries"], _POSITIVE)
    place = _count(cells["Place"])
    if place is None:
        broken.append(_problem("ENTRY_HISTORY_PLACE_INVALID", where))
    elif place < 1 or (entries is not None and place > entries):
        broken.append(_problem("ENTRY_HISTORY_PLACE_OUTSIDE_FIELD", where))
    points = _hundredths(cells["Points"])
    if points is None:
        broken.append(_problem("ENTRY_HISTORY_POINTS_INVALID", where))
    money = {column: _cents(cells[column]) for column in MONEY_COLUMNS}

    def check_money(*columns: str) -> None:
        for column in columns:
            if money[column] is None:
                broken.append(_problem("ENTRY_HISTORY_MONEY_INVALID", f"{where}:column={column}"))

    check_money("Winnings_Non_Ticket", "Winnings_Ticket")
    if entries is None:
        broken.append(_problem("ENTRY_HISTORY_CONTEST_ENTRIES_INVALID", where))
    check_money("Entry_Fee", "Prize_Pool")
    paid = _count(cells["Places_Paid"])
    if paid is None:
        broken.append(_problem("ENTRY_HISTORY_PLACES_PAID_INVALID", where))
    values: dict[str, object] = {
        "contest_start": start,
        "place": place,
        "points_hundredths": points,
        "winnings_non_ticket_cents": money["Winnings_Non_Ticket"],
        "winnings_ticket_cents": money["Winnings_Ticket"],
        "contest_entries": entries,
        "entry_fee_cents": money["Entry_Fee"],
        "prize_pool_cents": money["Prize_Pool"],
        "places_paid": paid,
    }
    return values, broken, time_kind


def parse_entry_history(raw: bytes) -> EntryHistory:
    """Every row of one export, or `EntryHistoryRefused` naming every bad row. Never partial."""

    records = _records(raw)
    header_problem = _header_problem(records[0][1])
    if header_problem:
        raise EntryHistoryRefused([header_problem])
    body = records[1:]
    if not body:
        raise EntryHistoryRefused([_problem("ENTRY_HISTORY_NO_ROWS")])
    unterminated = body[-1][0] if not raw.endswith((b"\n", b"\r")) else None

    problems: list[str] = []
    notes: list[dict] = []
    rows: list[HistoryRow] = []
    first_entry: dict[str, int] = {}
    first_contest: dict[str, tuple[int, dict[str, str]]] = {}
    # A value fault refuses on any row of a contest that has an NFL row, whichever of its rows comes first.
    sport_at, contest_at = HEADER.index("Sport"), HEADER.index("Contest_Key")
    nfl_contests = {
        cells[contest_at] for _number, cells in body
        if len(cells) == len(HEADER) and cells[sport_at] == NFL and _KEY.fullmatch(cells[contest_at])
    }
    for number, raw_cells in body:
        where = f"row={number}"
        if len(raw_cells) != len(HEADER):
            problems.append(_problem("ENTRY_HISTORY_ROW_MISSHAPEN", where))
            continue
        if number == unterminated:
            problems.append(_problem("ENTRY_HISTORY_ROW_MISSHAPEN", f"{where}:unterminated"))
        cells = dict(zip(HEADER, raw_cells))
        sport, game_type = cells["Sport"], cells["Game_Type"]
        entry_key, contest_key = cells["Entry_Key"], cells["Contest_Key"]
        if not _SPORT.fullmatch(sport):
            problems.append(_problem("ENTRY_HISTORY_SPORT_INVALID", where))
        if not game_type or game_type != game_type.strip():
            problems.append(_problem("ENTRY_HISTORY_GAME_TYPE_INVALID", where))
        if not _KEY.fullmatch(entry_key):
            problems.append(_problem("ENTRY_HISTORY_ENTRY_KEY_INVALID", where))
        elif entry_key in first_entry:
            problems.append(_problem("ENTRY_HISTORY_ENTRY_KEY_DUPLICATE", f"{where}:first={first_entry[entry_key]}"))
        else:
            first_entry[entry_key] = number
        contest_known = bool(_KEY.fullmatch(contest_key))
        if not contest_known:
            problems.append(_problem("ENTRY_HISTORY_CONTEST_KEY_INVALID", where))

        is_nfl = sport == NFL
        values, broken, time_kind = _value_rules(number, cells)
        disagreements: list[str] = []
        if contest_known:  # an invalid key groups nothing, so it adds no disagreement of its own
            first_number, first_cells = first_contest.setdefault(contest_key, (number, cells))
            disagreements = [
                _problem("ENTRY_HISTORY_CONTEST_DISAGREES", f"{where}:first={first_number}:column={column}")
                for column in AGREEMENT_COLUMNS
                if first_number != number and cells[column] != first_cells[column]
            ]
        if is_nfl or contest_key in nfl_contests:
            problems.extend(broken + disagreements)
        else:
            notes.extend(_note("NON_NFL_RULE_NOT_MET", number, sport, rule=rule) for rule in broken + disagreements)
        entries, paid, start = values["contest_entries"], values["places_paid"], values["contest_start"]
        above = isinstance(entries, int) and isinstance(paid, int) and paid > entries
        if above:  # the date comes from the parsed time, never the raw cell
            notes.append(_note("PLACES_PAID_ABOVE_CONTEST_ENTRIES", number, sport, entry_key=entry_key,
                               contest_key=contest_key, contest_date=start[:10] if isinstance(start, str) else None,
                               places_paid=paid, contest_entries=entries))
        if time_kind:
            notes.append(_note(time_kind, number, sport, entry_key=entry_key, contest_key=contest_key,
                               contest_start_text=cells["Contest_Date_EST"]))
        rows.append(HistoryRow(
            row=number, sport=sport, game_type=game_type, entry_key=entry_key, entry_name=cells["Entry"],
            contest_key=contest_key, contest_start_text=cells["Contest_Date_EST"],
            places_paid_above_entries=above, **values))
    if not problems and not any(row.is_nfl for row in rows):
        problems.append(_problem("ENTRY_HISTORY_NO_NFL_ROWS"))
    if problems:
        raise EntryHistoryRefused(problems)
    return EntryHistory(tuple(rows), tuple(notes))


# ------------------------------------------------------------------------------------------ summary


def summary_payload(history: EntryHistory, *, sha256: str, byte_count: int) -> dict[str, object]:
    """Counts by sport, game type and paid against free, and the named notes. No money, no path, no time."""

    by_sport: Counter[str] = Counter(row.sport for row in history.rows)
    by_type: dict[str, dict[str, dict[str, int]]] = {}
    for row in history.rows:
        bucket = by_type.setdefault(row.sport, {}).setdefault(
            row.game_type, {"paid": 0, "free": 0, "fee_unreadable": 0})
        if row.entry_fee_cents is None:
            bucket["fee_unreadable"] += 1
        else:
            bucket["paid" if row.entry_fee_cents > 0 else "free"] += 1
    return {
        "schema_version": SUMMARY_VERSION,
        "contract": CONTRACT_VERSION,
        "source_sha256": sha256,
        "source_bytes": byte_count,
        "rows_total": len(history.rows),
        "nfl_rows": len(history.nfl_rows),
        "rows_by_sport": dict(sorted(by_sport.items())),
        "rows_by_game_type": by_type,
        "notes": list(history.notes),
        "note_counts": dict(sorted(Counter(note["kind"] for note in history.notes).items())),
        "does_not_establish": list(DOES_NOT_ESTABLISH),
    }


# ----------------------------------------------------------------------------- intake (Session 69b)

ENTRIES_VERSION = "nfl_dk_entry_history_entries_v1"
# A fix that changes a written byte takes a new writer version, so a file already on disk is never contradicted.
WRITER = "w1"
ENTRIES_NAME = f"nfl_entries.{WRITER}.json"
SUMMARY_NAME = f"intake_summary.{WRITER}.json"
FILES = ("snapshot", "entries", "summary")
# The codes the intake adds; each is emitted as a full literal below.
INTAKE_CODES = (
    "ENTRY_HISTORY_UNREADABLE",
    "ENTRY_HISTORY_SNAPSHOT_CORRUPT",
    "ENTRY_HISTORY_ARTIFACT_CONFLICT",
    "ENTRY_HISTORY_WRITE_FAILED",
)
SNAPSHOT_RECOVERY = (
    "Another file holds this snapshot's name, so it is not the bytes the name promises. It is never overwritten:"
    " check it, delete it by hand and rerun the intake."
)
ARTIFACT_RECOVERY = (
    "This folder is derived from the snapshot beside it. Delete the whole folder, which also deletes any good file in"
    " it, and rerun the intake to rebuild it; a fix that changes a written byte takes a new writer version instead."
)


class WrittenBytesDiffer(OSError):
    """The bytes read back after a write are not the bytes written."""


class _Stop(Exception):
    """A file this run may not write: something else already holds its name."""

    def __init__(self, code: str, recovery: str):
        super().__init__(code)
        self.code, self.recovery = code, recovery


@dataclass(frozen=True)
class IntakeOutcome:
    """`COMPLETE` and `ALREADY_PRESENT` exit 0; `REFUSED` and `WRITE_FAILED` exit 2. Every file reports a state."""

    status: str
    problems: tuple[str, ...]
    files: dict[str, dict[str, str | None]]
    source_sha256: str | None = None
    summary: dict[str, object] | None = None

    @property
    def exit_code(self) -> int:
        return 0 if self.status in ("COMPLETE", "ALREADY_PRESENT") else 2

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "exit_code": self.exit_code,
            "problems": list(self.problems),
            "contract": CONTRACT_VERSION,
            "source_sha256": self.source_sha256,
            "files": self.files,
            "summary": self.summary,
            "does_not_establish": list(DOES_NOT_ESTABLISH),
        }


def entries_payload(history: EntryHistory, *, sha256: str, byte_count: int) -> dict[str, object]:
    """The NFL rows in file order. Fields are listed, not derived, so a later `HistoryRow` field never moves w1's bytes.

    An NFL row holds no null: a value that did not parse on an NFL row refuses the whole file.
    """

    entries = [
        {
            "source_row": row.row,
            "entry_key": row.entry_key,
            "contest_key": row.contest_key,
            "game_type": row.game_type,
            "entry_name": row.entry_name,
            "contest_start": row.contest_start,
            "contest_start_text": row.contest_start_text,
            "place": row.place,
            "points_hundredths": row.points_hundredths,
            "winnings_non_ticket_cents": row.winnings_non_ticket_cents,
            "winnings_ticket_cents": row.winnings_ticket_cents,
            "contest_entries": row.contest_entries,
            "entry_fee_cents": row.entry_fee_cents,
            "prize_pool_cents": row.prize_pool_cents,
            "places_paid": row.places_paid,
            "places_paid_above_entries": row.places_paid_above_entries,
        }
        for row in history.nfl_rows
    ]
    return {
        "schema_version": ENTRIES_VERSION,
        "contract": CONTRACT_VERSION,
        "writer": WRITER,
        "sport": NFL,
        "source_sha256": sha256,
        "source_bytes": byte_count,
        "nfl_rows": len(entries),
        "entries": entries,
        "does_not_establish": list(DOES_NOT_ESTABLISH),
    }


def _holds(path: Path, sha256: str) -> bool:
    """A plain file, never a symlink (which points at bytes that can change), holding exactly `sha256`."""

    return path.is_file() and not path.is_symlink() and sha256_file(path) == sha256


def _write_once(path: Path, data: bytes, *, code: str, recovery: str) -> str:
    """Write `data` at `path` only if nothing holds the name; never replace, never follow, never delete what is there.

    The same bytes already there is `ALREADY_PRESENT`, found before any temporary file is written. Anything else
    holding the name (other bytes, a directory, a symlink) is `code`. A new file goes through a temporary file in the
    same folder (flushed, fsynced, re-read) and a hard link, which fails rather than replaces when the name appears
    first; the linked file is re-read too. A filesystem with no hard links is an `OSError` for the caller to name.
    A temporary file that cannot be deleted (on Windows, Defender or the indexer can hold a fresh file) is left, its
    name starting with a dot, rather than hiding the file's real outcome.
    """

    sha256 = sha256_bytes(data)
    if _holds(path, sha256):
        return "ALREADY_PRESENT"
    if path.exists() or path.is_symlink():
        raise _Stop(code, recovery)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if sha256_file(temporary) != sha256:
            raise WrittenBytesDiffer()
        try:
            os.link(temporary, path)
        except FileExistsError:  # the name appeared after the check above
            if _holds(path, sha256):
                return "ALREADY_PRESENT"
            raise _Stop(code, recovery) from None
        if sha256_file(path) != sha256:
            if _same_file(path, temporary):  # this run's own fresh link, never a file that took the name after it
                path.unlink(missing_ok=True)
            raise WrittenBytesDiffer()
    finally:
        with contextlib.suppress(OSError):
            temporary.unlink(missing_ok=True)
    return "WRITTEN"


def _same_file(first: Path, second: Path) -> bool:
    try:
        return os.path.samefile(first, second)
    except OSError:
        return False


def _classified(problem: str, source: Path) -> str:
    """A header refusal also says what the run-input classifier takes the file for. Diagnosis only: a second read."""

    if not problem.startswith("ENTRY_HISTORY_HEADER_INVALID"):
        return problem
    from . import cowork

    try:
        kind = cowork.classify_csv(source) or "none"
    except (cowork.CoworkInputError, OSError):
        kind = "unreadable"
    return f"{problem}:classified_as={kind}"


def run_intake(history_path: str | Path, results_root: str | Path) -> IntakeOutcome:
    """Read the export once, refuse it whole or keep it: the snapshot, then the NFL rows, then the summary.

    The first file that cannot be written stops the run, and every file reports `WRITTEN`, `ALREADY_PRESENT`,
    `REFUSED`, `WRITE_FAILED` or `NOT_ATTEMPTED`. Nothing is created before the file parses.
    """

    source, root = Path(history_path), Path(results_root)
    files: dict[str, dict[str, str | None]] = {name: {"path": None, "state": "NOT_ATTEMPTED"} for name in FILES}
    try:
        with source.open("rb") as handle:
            raw = handle.read(MAX_BYTES + 1)  # one byte past the cap is enough to refuse a larger file
    except OSError as exc:
        return IntakeOutcome("REFUSED", (_problem("ENTRY_HISTORY_UNREADABLE", f"exception={type(exc).__name__}"),),
                             files)
    try:
        history = parse_entry_history(raw)
    except EntryHistoryRefused as refused:
        prefix_only = len(raw) > MAX_BYTES  # never name the hash of a prefix
        return IntakeOutcome("REFUSED", tuple(_classified(problem, source) for problem in refused.problems), files,
                             None if prefix_only else sha256_bytes(raw))
    sha256 = sha256_bytes(raw)
    summary = summary_payload(history, sha256=sha256, byte_count=len(raw))
    folder = root / "normalized" / sha256
    targets = {"snapshot": root / "inbox" / f"{sha256}.csv", "entries": folder / ENTRIES_NAME,
               "summary": folder / SUMMARY_NAME}
    for name, path in targets.items():
        files[name]["path"] = str(path)
    writes = (
        ("snapshot", lambda: _write_once(
            targets["snapshot"], raw, code="ENTRY_HISTORY_SNAPSHOT_CORRUPT", recovery=SNAPSHOT_RECOVERY)),
        ("entries", lambda: _write_once(
            targets["entries"], canonical_bytes(entries_payload(history, sha256=sha256, byte_count=len(raw))),
            code="ENTRY_HISTORY_ARTIFACT_CONFLICT", recovery=ARTIFACT_RECOVERY)),
        ("summary", lambda: _write_once(
            targets["summary"], canonical_bytes(summary), code="ENTRY_HISTORY_ARTIFACT_CONFLICT",
            recovery=ARTIFACT_RECOVERY)),
    )
    for name, write in writes:
        try:
            files[name]["state"] = write()
        except _Stop as stop:
            files[name].update(state="REFUSED", recovery=stop.recovery)
            return IntakeOutcome("REFUSED", (_problem(stop.code, f"file={name}"),), files, sha256, summary)
        except OSError as exc:
            files[name]["state"] = "WRITE_FAILED"
            written = _problem("ENTRY_HISTORY_WRITE_FAILED", f"file={name}:exception={type(exc).__name__}")
            return IntakeOutcome("WRITE_FAILED", (written,), files, sha256, summary)
    status = "ALREADY_PRESENT" if all(report["state"] == "ALREADY_PRESENT" for report in files.values()) else "COMPLETE"
    return IntakeOutcome(status, (), files, sha256, summary)


__all__ = [
    "CONTRACT_VERSION",
    "ENTRIES_VERSION",
    "EntryHistory",
    "EntryHistoryRefused",
    "HEADER",
    "HistoryRow",
    "INTAKE_CODES",
    "IntakeOutcome",
    "canonical_bytes",
    "entries_payload",
    "parse_entry_history",
    "run_intake",
    "summary_payload",
]
