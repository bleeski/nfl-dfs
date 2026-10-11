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

`does_not_establish`: expected value or ROI, win or cash probability, an edge, calibration, which entries the engine
built, upload clearance.
"""

from __future__ import annotations

import csv
import io
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Mapping, Sequence
from zoneinfo import ZoneInfo

from .contest_facts import canonical_bytes

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
_MONEY = re.compile(r"\$(?:0|[1-9][0-9]{0,2}(?:,[0-9]{3})*)\.[0-9]{2}")


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
    return int(Decimal(text[1:].replace(",", "")) * 100) if _MONEY.fullmatch(text) else None


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
    extra = sum(1 for name in found if name not in HEADER) + max(0, len(found) - len(set(found)))
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
    first_contest: dict[str, tuple[int, bool, dict[str, str]]] = {}
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
        if not _KEY.fullmatch(contest_key):
            problems.append(_problem("ENTRY_HISTORY_CONTEST_KEY_INVALID", where))

        is_nfl = sport == NFL
        values, broken, time_kind = _value_rules(number, cells)
        first_number, first_is_nfl, first_cells = first_contest.setdefault(contest_key, (number, is_nfl, cells))
        disagreements = [
            _problem("ENTRY_HISTORY_CONTEST_DISAGREES", f"{where}:first={first_number}:column={column}")
            for column in AGREEMENT_COLUMNS
            if first_number != number and cells[column] != first_cells[column]
        ]
        if is_nfl:
            problems.extend(broken + disagreements)
        else:
            # A contest with an NFL row refuses on any disagreement; the row's own value rules stay its sport's notes.
            problems.extend(disagreements if first_is_nfl else ())
            rules = broken if first_is_nfl else broken + disagreements
            notes.extend(_note("NON_NFL_RULE_NOT_MET", number, sport, rule=rule) for rule in rules)
        entries, paid = values["contest_entries"], values["places_paid"]
        above = isinstance(entries, int) and isinstance(paid, int) and paid > entries
        if above:
            notes.append(_note("PLACES_PAID_ABOVE_CONTEST_ENTRIES", number, sport, entry_key=entry_key,
                               contest_key=contest_key, contest_date=cells["Contest_Date_EST"][:10],
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


__all__ = [
    "CONTRACT_VERSION",
    "EntryHistory",
    "EntryHistoryRefused",
    "HEADER",
    "HistoryRow",
    "canonical_bytes",
    "parse_entry_history",
    "summary_payload",
]
