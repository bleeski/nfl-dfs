"""Session 69: `nfl_dk_entry_history_v1`, the DraftKings account entry-history export, and its intake summary.

The parser is strict: structure is checked on every row of every sport and refuses the whole file; value rules refuse on
an NFL row and are a named note on any other sport's row, because the export is cumulative and one unforeseen non-NFL row
must not refuse every future export. Every bad row is named in file order and no cell value is ever echoed. A
`Places_Paid` above `Contest_Entries` is kept and named, never refused, and is not a gate code. Fixtures are synthetic
bytes written with `write_bytes` (Ben's real export carries account winnings and never enters the repository).
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import pytest

from nfl_dfs import entry_history
from nfl_dfs.contracts import GateClass
from nfl_dfs.gate_registry import load_gate_registry
from tests.test_gate_registry import blocker_literals

REPO = Path(__file__).resolve().parents[1]
HEADER = (
    "Sport,Game_Type,Entry_Key,Entry,Contest_Key,Contest_Date_EST,Place,Points,Winnings_Non_Ticket,"
    "Winnings_Ticket,Contest_Entries,Entry_Fee,Prize_Pool,Places_Paid"
)
COLUMNS = tuple(HEADER.split(","))
BASE = {
    "Sport": "NFL",
    "Game_Type": "Classic",
    "Entry_Key": "4000000001",
    "Entry": "NFL $5 Synthetic Classic (1/2)",
    "Contest_Key": "100000001",
    "Contest_Date_EST": "2026-09-13 13:00:00",
    "Place": "12",
    "Points": "142.36",
    "Winnings_Non_Ticket": "$10.00",
    "Winnings_Ticket": "$0.00",
    "Contest_Entries": "1000",
    "Entry_Fee": "$5.00",
    "Prize_Pool": "$4,500.00",
    "Places_Paid": "200",
}


def _row(**cells: str) -> list[str]:
    values = dict(BASE, **cells)
    return [values[column] for column in COLUMNS]


# A second entry in the same contest, a free Showdown entry, and an MLB entry.
GOOD = (
    _row(),
    _row(Entry_Key="4000000002", Entry="NFL $5 Synthetic Classic (2/2)", Place="640", Points="88",
         Winnings_Non_Ticket="$0.00"),
    _row(Game_Type="Showdown Captain Mode", Entry_Key="4000000003", Entry='Free "Showdown", Week 2',
         Contest_Key="100000002", Contest_Date_EST="2026-09-14 20:15:00", Place="1", Points="201.5",
         Winnings_Non_Ticket="$1,250.50", Winnings_Ticket="$3.00", Contest_Entries="2", Entry_Fee="$0.00",
         Prize_Pool="$0.00", Places_Paid="0"),
    _row(Sport="MLB", Entry_Key="4000000004", Entry="MLB $1 Synthetic", Contest_Key="100000003",
         Contest_Date_EST="2026-07-04 19:05:00", Place="3", Points="0", Contest_Entries="50", Entry_Fee="$1.00",
         Prize_Pool="$45.00", Places_Paid="10"),
)


def _history(*rows: list[str], eol: str = "\r\n", bom: bool = False, header: str = HEADER,
             terminated: bool = True) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator=eol)
    buffer.write(header + eol)
    for row in rows:
        writer.writerow(row)
    text = buffer.getvalue()
    if not terminated:
        text = text[: -len(eol)]
    return (b"\xef\xbb\xbf" if bom else b"") + text.encode("utf-8")


def _problems(raw: bytes) -> tuple[str, ...]:
    with pytest.raises(entry_history.EntryHistoryRefused) as caught:
        entry_history.parse_entry_history(raw)
    return caught.value.problems


def _head(problem: str) -> str:
    return problem.split(":", 1)[0]


def _kinds(history) -> list[str]:
    return [note["kind"] for note in history.notes]


# ---------------------------------------------------------------------------------- the parser accepts


@pytest.mark.parametrize(
    "kwargs",
    [{}, {"eol": "\n"}, {"bom": True}, {"bom": True, "eol": "\n"}],
    ids=["crlf", "lf", "bom_crlf", "bom_lf"],
)
def test_crlf_lf_and_bom_read_the_same_rows(kwargs):
    history = entry_history.parse_entry_history(_history(*GOOD, **kwargs))
    first, second, showdown, mlb = history.rows
    assert (first.row, first.sport, first.game_type, first.entry_key, first.contest_key) == (
        2, "NFL", "Classic", "4000000001", "100000001")
    assert first.entry_name == "NFL $5 Synthetic Classic (1/2)"
    assert (first.place, first.points_hundredths, first.contest_entries, first.places_paid) == (12, 14236, 1000, 200)
    assert (first.winnings_non_ticket_cents, first.winnings_ticket_cents, first.entry_fee_cents,
            first.prize_pool_cents) == (1000, 0, 500, 450000)
    assert first.contest_start_text == "2026-09-13 13:00:00"
    assert first.contest_start == "2026-09-13T13:00:00-04:00"
    assert (second.place, second.points_hundredths, second.winnings_non_ticket_cents) == (640, 8800, 0)
    assert showdown.entry_name == 'Free "Showdown", Week 2'
    assert (showdown.points_hundredths, showdown.winnings_non_ticket_cents, showdown.winnings_ticket_cents,
            showdown.entry_fee_cents, showdown.places_paid) == (20150, 125050, 300, 0, 0)
    assert mlb.sport == "MLB" and mlb.row == 5
    assert [row.entry_key for row in history.nfl_rows] == ["4000000001", "4000000002", "4000000003"]
    assert history.notes == ()


def test_points_without_a_decimal_point_and_places_paid_zero_are_legal():
    history = entry_history.parse_entry_history(_history(_row(Points="0", Places_Paid="0"), _row(
        Entry_Key="4000000002", Points="-3.5", Place="1", Places_Paid="0")))
    assert [(row.points_hundredths, row.places_paid) for row in history.rows] == [(0, 0), (-350, 0)]


def test_a_fully_blank_line_is_skipped_and_row_numbers_count_the_header_as_row_one():
    raw = _history(GOOD[0]) + b"\r\n" + _history(GOOD[1], header="").lstrip(b"\r\n")
    history = entry_history.parse_entry_history(raw)
    assert [row.row for row in history.rows] == [2, 4]


def test_the_size_cap_is_exact(monkeypatch):
    raw = _history(*GOOD)
    monkeypatch.setattr(entry_history, "MAX_BYTES", len(raw))
    assert len(entry_history.parse_entry_history(raw).rows) == 4
    monkeypatch.setattr(entry_history, "MAX_BYTES", len(raw) - 1)
    assert _problems(raw) == ("ENTRY_HISTORY_FILE_TOO_LARGE",)


# ------------------------------------------------------------- one named refusal per kind of bad input

HEADER_VARIANTS = (
    HEADER.replace(",Places_Paid", ""),                          # a missing column
    HEADER + ",Extra",                                           # an extra one
    HEADER.replace("Sport,Game_Type", "Game_Type,Sport"),        # reordered
    HEADER.replace("Entry_Key", "Entry Key"),                    # renamed
)
BAD = [
    ("ENTRY_HISTORY_FILE_EMPTY", b""),
    ("ENTRY_HISTORY_FILE_EMPTY", b"\r\n\r\n"),
    ("ENTRY_HISTORY_NOT_TEXT", b"\xff\xfe" + _history(*GOOD)),
    ("ENTRY_HISTORY_NOT_TEXT", _history(_row(Entry="caf\xe9")).replace(b"caf\xc3\xa9", b"caf\xe9")),
    ("ENTRY_HISTORY_NOT_TEXT", _history(_row(Entry="a\x00b"))),
    *[("ENTRY_HISTORY_HEADER_INVALID", _history(*GOOD, header=header)) for header in HEADER_VARIANTS],
    ("ENTRY_HISTORY_NO_ROWS", _history()),
    ("ENTRY_HISTORY_ROW_MISSHAPEN", _history(_row()[:-1])),                         # a row cut short
    ("ENTRY_HISTORY_ROW_MISSHAPEN", _history(_row() + ["9"])),                      # overlong
    ("ENTRY_HISTORY_ROW_MISSHAPEN", _history(*GOOD, terminated=False)),             # last line unterminated
    ("ENTRY_HISTORY_ROW_MISSHAPEN", _history(*GOOD) + b'"NFL,Classic\r\n'),        # an unterminated quote
    ("ENTRY_HISTORY_SPORT_INVALID", _history(_row(Sport=""), *GOOD)),
    ("ENTRY_HISTORY_SPORT_INVALID", _history(_row(Sport="NFL "), *GOOD[1:])),
    ("ENTRY_HISTORY_SPORT_INVALID", _history(_row(Sport="nfl"), *GOOD[1:])),
    ("ENTRY_HISTORY_GAME_TYPE_INVALID", _history(_row(Game_Type=""))),
    ("ENTRY_HISTORY_GAME_TYPE_INVALID", _history(_row(Game_Type=" Classic"))),
    ("ENTRY_HISTORY_ENTRY_KEY_INVALID", _history(_row(Entry_Key=""))),
    ("ENTRY_HISTORY_ENTRY_KEY_INVALID", _history(_row(Entry_Key="04000000001"))),
    ("ENTRY_HISTORY_ENTRY_KEY_INVALID", _history(_row(Entry_Key="4" * 19))),
    ("ENTRY_HISTORY_ENTRY_KEY_INVALID", _history(_row(Entry_Key="٤٠"))),  # Arabic-Indic digits
    ("ENTRY_HISTORY_ENTRY_KEY_DUPLICATE", _history(_row(), _row(Contest_Key="100000009"))),
    ("ENTRY_HISTORY_CONTEST_KEY_INVALID", _history(_row(Contest_Key="10000000a"))),
    ("ENTRY_HISTORY_CONTEST_DATE_INVALID", _history(_row(Contest_Date_EST="2026-09-13"))),
    ("ENTRY_HISTORY_CONTEST_DATE_INVALID", _history(_row(Contest_Date_EST="2026-9-3 1:0:0"))),
    ("ENTRY_HISTORY_CONTEST_DATE_INVALID", _history(_row(Contest_Date_EST="2026-13-13 13:00:00"))),
    ("ENTRY_HISTORY_CONTEST_DATE_INVALID", _history(_row(Contest_Date_EST="2026-09-13T13:00:00"))),
    ("ENTRY_HISTORY_PLACE_INVALID", _history(_row(Place=""))),
    ("ENTRY_HISTORY_PLACE_INVALID", _history(_row(Place="1.0"))),
    ("ENTRY_HISTORY_PLACE_INVALID", _history(_row(Place="-1"))),
    ("ENTRY_HISTORY_PLACE_OUTSIDE_FIELD", _history(_row(Place="0"))),
    ("ENTRY_HISTORY_PLACE_OUTSIDE_FIELD", _history(_row(Place="1001"))),
    ("ENTRY_HISTORY_POINTS_INVALID", _history(_row(Points=""))),
    ("ENTRY_HISTORY_POINTS_INVALID", _history(_row(Points="12.345"))),
    ("ENTRY_HISTORY_POINTS_INVALID", _history(_row(Points="1e2"))),
    ("ENTRY_HISTORY_POINTS_INVALID", _history(_row(Points=".5"))),
    ("ENTRY_HISTORY_MONEY_INVALID", _history(_row(Entry_Fee="$1,2x"))),
    ("ENTRY_HISTORY_MONEY_INVALID", _history(_row(Entry_Fee="1.00"))),
    ("ENTRY_HISTORY_MONEY_INVALID", _history(_row(Entry_Fee="-$1.00"))),
    ("ENTRY_HISTORY_MONEY_INVALID", _history(_row(Prize_Pool="$1,23.00"))),
    ("ENTRY_HISTORY_MONEY_INVALID", _history(_row(Prize_Pool="$4500.00"))),
    ("ENTRY_HISTORY_MONEY_INVALID", _history(_row(Winnings_Ticket="$1.5"))),
    ("ENTRY_HISTORY_MONEY_INVALID", _history(_row(Winnings_Non_Ticket="$01.00"))),
    ("ENTRY_HISTORY_CONTEST_ENTRIES_INVALID", _history(_row(Contest_Entries="0"))),
    ("ENTRY_HISTORY_CONTEST_ENTRIES_INVALID", _history(_row(Contest_Entries="1,000"))),
    ("ENTRY_HISTORY_PLACES_PAID_INVALID", _history(_row(Places_Paid="-1"))),
    ("ENTRY_HISTORY_PLACES_PAID_INVALID", _history(_row(Places_Paid=""))),
    ("ENTRY_HISTORY_CONTEST_DISAGREES", _history(_row(), _row(Entry_Key="4000000002", Contest_Entries="999"))),
    ("ENTRY_HISTORY_NO_NFL_ROWS", _history(GOOD[3])),
]


@pytest.mark.parametrize("code,raw", BAD, ids=[f"{code[14:]}-{index}" for index, (code, _) in enumerate(BAD)])
def test_a_bad_file_is_refused_by_name_and_never_parsed_in_part(code, raw):
    problems = _problems(raw)
    assert _head(problems[0]) == code, problems
    assert all(_head(problem) in entry_history.PARSE_CODES for problem in problems), problems


def test_every_parser_code_has_a_case_and_nothing_else_is_emitted():
    assert {code for code, _ in BAD} | {"ENTRY_HISTORY_FILE_TOO_LARGE"} == set(entry_history.PARSE_CODES)
    assert len(entry_history.PARSE_CODES) == len(set(entry_history.PARSE_CODES)) == 20


# ------------------------------------------------------------------- the card's acceptance, by name


def test_a_header_only_file_is_refused_as_no_rows():
    assert _problems(_history()) == ("ENTRY_HISTORY_NO_ROWS",)
    assert _problems(_history(terminated=False)) == ("ENTRY_HISTORY_NO_ROWS",)


def test_a_row_cut_short_is_refused_by_row():
    assert _problems(_history(GOOD[0], GOOD[1][:9], GOOD[2])) == ("ENTRY_HISTORY_ROW_MISSHAPEN:row=3",)


def test_a_last_line_without_a_terminator_is_refused():
    # A cut inside the last cell (`10` to `1`) still parses as a row; the missing terminator is what names it.
    raw = _history(*GOOD)
    cut = raw[: raw.rindex(b"10\r\n")] + b"1"
    assert _problems(cut) == ("ENTRY_HISTORY_ROW_MISSHAPEN:row=5:unterminated",)


def test_a_duplicate_entry_key_names_both_rows():
    raw = _history(GOOD[0], GOOD[3], _row(Contest_Key="100000009"))
    assert _problems(raw) == ("ENTRY_HISTORY_ENTRY_KEY_DUPLICATE:row=4:first=2",)


def test_a_missing_column_is_refused_and_named():
    assert _problems(_history(*GOOD, header=HEADER_VARIANTS[0])) == (
        "ENTRY_HISTORY_HEADER_INVALID:missing=Places_Paid:extra=0",)
    assert _problems(_history(*GOOD, header=HEADER_VARIANTS[3])) == (
        "ENTRY_HISTORY_HEADER_INVALID:missing=Entry_Key:extra=1",)
    # A name given twice is an extra column, though every name in it is an expected one; each column counts once.
    assert _problems(_history(*GOOD, header=HEADER.replace("Game_Type", "Sport"))) == (
        "ENTRY_HISTORY_HEADER_INVALID:missing=Game_Type:extra=1",)
    assert _problems(_history(*GOOD, header=HEADER + ",X,X")) == ("ENTRY_HISTORY_HEADER_INVALID:missing=:extra=2",)


def test_a_reordered_header_is_refused():
    assert _problems(_history(*GOOD, header=HEADER_VARIANTS[2])) == ("ENTRY_HISTORY_HEADER_INVALID:order:position=1",)


def test_place_zero_and_place_above_contest_entries_are_refused():
    raw = _history(_row(Place="0"), _row(Entry_Key="4000000002", Place="1001"), _row(Entry_Key="4000000003",
                                                                                     Place="1000"))
    assert _problems(raw) == (
        "ENTRY_HISTORY_PLACE_OUTSIDE_FIELD:row=2",
        "ENTRY_HISTORY_PLACE_OUTSIDE_FIELD:row=3",
    )


def test_bad_money_is_refused_by_column():
    raw = _history(  # one contest each, so no row also disagrees with another
        _row(Entry_Fee="$1,2x"),
        _row(Entry_Key="4000000002", Contest_Key="100000002", Winnings_Non_Ticket="1.00"),
        _row(Entry_Key="4000000003", Contest_Key="100000003", Winnings_Ticket="-$1.00"),
        _row(Entry_Key="4000000004", Contest_Key="100000004", Prize_Pool="$1,23.00"),
    )
    assert _problems(raw) == (
        "ENTRY_HISTORY_MONEY_INVALID:row=2:column=Entry_Fee",
        "ENTRY_HISTORY_MONEY_INVALID:row=3:column=Winnings_Non_Ticket",
        "ENTRY_HISTORY_MONEY_INVALID:row=4:column=Winnings_Ticket",
        "ENTRY_HISTORY_MONEY_INVALID:row=5:column=Prize_Pool",
    )


def test_a_file_with_no_nfl_row_is_refused_and_says_so():
    mlb = GOOD[3]
    nba = _row(Sport="NBA", Entry_Key="4000000005", Contest_Key="100000005", Place="0")  # a note, not a refusal
    assert _problems(_history(mlb, nba)) == ("ENTRY_HISTORY_NO_NFL_ROWS",)


def test_undecodable_bytes_and_nul_are_refused_as_not_text():
    good = _history(*GOOD)
    assert _problems(good.replace(b"Synthetic Classic (1/2)", b"Synthetic Classic \x92(1/2)")) == (
        "ENTRY_HISTORY_NOT_TEXT",)
    assert _problems(good.replace(b"MLB $1", b"MLB \x00$1")) == ("ENTRY_HISTORY_NOT_TEXT",)


def test_places_paid_above_entries_is_kept_and_named_for_any_sport():
    nfl = _row(Contest_Entries="7112", Places_Paid="9910", Entry_Fee="$0.00", Prize_Pool="$0.00")
    nba = _row(Sport="NBA", Entry_Key="4000000009", Contest_Key="100000009", Contest_Date_EST="2024-02-22 19:00:00",
               Contest_Entries="3461", Places_Paid="3535", Entry_Fee="$0.00")
    every_place_paid = _row(Entry_Key="4000000010", Contest_Key="100000010", Contest_Entries="50", Places_Paid="50")
    history = entry_history.parse_entry_history(_history(nfl, GOOD[2], nba, every_place_paid))
    assert history.notes == (
        {"kind": "PLACES_PAID_ABOVE_CONTEST_ENTRIES", "row": 2, "sport": "NFL", "entry_key": "4000000001",
         "contest_key": "100000001", "contest_date": "2026-09-13", "places_paid": 9910, "contest_entries": 7112},
        {"kind": "PLACES_PAID_ABOVE_CONTEST_ENTRIES", "row": 4, "sport": "NBA", "entry_key": "4000000009",
         "contest_key": "100000009", "contest_date": "2024-02-22", "places_paid": 3535, "contest_entries": 3461},
    )
    flagged = [(row.entry_key, row.places_paid_above_entries) for row in history.rows]
    # A contest that pays every place (50 of 50) is ordinary and carries no flag.
    assert flagged == [("4000000001", True), ("4000000003", False), ("4000000009", True), ("4000000010", False)]


def test_no_note_kind_is_a_scanned_or_registered_code():
    source = Path(entry_history.__file__).read_text(encoding="utf-8")
    scanned = set(blocker_literals(source))
    registry = load_gate_registry()
    for kind in entry_history.NOTE_KINDS:
        assert kind not in scanned, kind
        assert kind not in registry.codes, kind
    assert set(entry_history.PARSE_CODES) <= scanned


def test_every_bad_row_is_named_in_file_order_and_no_row_is_kept():
    raw = _history(
        GOOD[0],
        _row(Entry_Key="4000000002", Place="x", Points="1.234"),
        _row(Entry_Key="4000000001", Contest_Key="100000007", Contest_Date_EST="2026-09-13 13:00"),
        _row(Entry_Key="4000000004", Contest_Entries="999"),
        _row(Entry_Key="4000000005", Entry_Fee="$5", Places_Paid="a"),
    )
    assert _problems(raw) == (
        "ENTRY_HISTORY_PLACE_INVALID:row=3",
        "ENTRY_HISTORY_POINTS_INVALID:row=3",
        "ENTRY_HISTORY_ENTRY_KEY_DUPLICATE:row=4:first=2",
        "ENTRY_HISTORY_CONTEST_DATE_INVALID:row=4",
        "ENTRY_HISTORY_CONTEST_DISAGREES:row=5:first=2:column=Contest_Entries",
        "ENTRY_HISTORY_MONEY_INVALID:row=6:column=Entry_Fee",
        "ENTRY_HISTORY_PLACES_PAID_INVALID:row=6",
        "ENTRY_HISTORY_CONTEST_DISAGREES:row=6:first=2:column=Entry_Fee",
        "ENTRY_HISTORY_CONTEST_DISAGREES:row=6:first=2:column=Places_Paid",
    )


@pytest.mark.parametrize("column,value", [
    ("Sport", "MLB"), ("Game_Type", "Showdown Captain Mode"), ("Contest_Date_EST", "2026-09-13 16:25:00"),
    ("Contest_Entries", "999"), ("Entry_Fee", "$3.00"), ("Prize_Pool", "$4,400.00"), ("Places_Paid", "199"),
])
def test_rows_of_one_contest_that_disagree_on_field_size_are_refused(column, value):
    raw = _history(GOOD[0], _row(Entry_Key="4000000002", **{column: value}))
    assert _problems(raw) == (f"ENTRY_HISTORY_CONTEST_DISAGREES:row=3:first=2:column={column}",)


def test_the_entry_label_may_differ_inside_a_contest():
    history = entry_history.parse_entry_history(_history(GOOD[0], GOOD[1]))
    assert [row.entry_name for row in history.rows] == [
        "NFL $5 Synthetic Classic (1/2)", "NFL $5 Synthetic Classic (2/2)"]


def test_a_non_nfl_value_failure_is_a_note_and_a_non_nfl_structural_failure_refuses():
    mlb = dict(Sport="MLB", Contest_Key="100000003")
    raw = _history(
        GOOD[0],
        _row(Entry_Key="4000000004", Place="0", **mlb),
        _row(Entry_Key="4000000005", Entry_Fee="$1", Contest_Date_EST="soon", **mlb),
    )
    history = entry_history.parse_entry_history(raw)
    assert history.notes == (
        {"kind": "NON_NFL_RULE_NOT_MET", "row": 3, "sport": "MLB", "rule": "ENTRY_HISTORY_PLACE_OUTSIDE_FIELD:row=3"},
        {"kind": "NON_NFL_RULE_NOT_MET", "row": 4, "sport": "MLB", "rule": "ENTRY_HISTORY_CONTEST_DATE_INVALID:row=4"},
        {"kind": "NON_NFL_RULE_NOT_MET", "row": 4, "sport": "MLB",
         "rule": "ENTRY_HISTORY_MONEY_INVALID:row=4:column=Entry_Fee"},
        {"kind": "NON_NFL_RULE_NOT_MET", "row": 4, "sport": "MLB",
         "rule": "ENTRY_HISTORY_CONTEST_DISAGREES:row=4:first=3:column=Contest_Date_EST"},
        {"kind": "NON_NFL_RULE_NOT_MET", "row": 4, "sport": "MLB",
         "rule": "ENTRY_HISTORY_CONTEST_DISAGREES:row=4:first=3:column=Entry_Fee"},
    )
    unread = history.rows[2]
    assert (unread.entry_fee_cents, unread.contest_start, unread.place) == (None, None, 12)
    # Structure is file-wide: the same MLB rows with a bad key or a short row refuse the file.
    assert _problems(_history(GOOD[0], _row(Entry_Key="x", **mlb))) == ("ENTRY_HISTORY_ENTRY_KEY_INVALID:row=3",)
    assert _problems(_history(GOOD[0], _row(**mlb)[:5])) == ("ENTRY_HISTORY_ROW_MISSHAPEN:row=3",)
    assert _problems(_history(GOOD[0], _row(Entry_Key="4000000001", **mlb))) == (
        "ENTRY_HISTORY_ENTRY_KEY_DUPLICATE:row=3:first=2",)


def test_a_contest_that_mixes_nfl_and_another_sport_refuses_and_names_every_fault():
    # The MLB row comes first, but its contest has an NFL row, so its own value fault refuses too and is named.
    raw = _history(_row(Sport="MLB", Place="x"), _row(Entry_Key="4000000002"))
    assert _problems(raw) == (
        "ENTRY_HISTORY_PLACE_INVALID:row=2",
        "ENTRY_HISTORY_CONTEST_DISAGREES:row=3:first=2:column=Sport",
    )


def test_an_invalid_contest_key_never_groups_rows_into_a_contest():
    raw = _history(_row(Contest_Key=""), _row(Entry_Key="4000000002", Contest_Key="", Contest_Entries="999"))
    assert _problems(raw) == (
        "ENTRY_HISTORY_CONTEST_KEY_INVALID:row=2",
        "ENTRY_HISTORY_CONTEST_KEY_INVALID:row=3",
    )


def test_money_is_exact_integer_cents_up_to_three_comma_groups_and_refused_beyond():
    history = entry_history.parse_entry_history(_history(_row(Prize_Pool="$999,999,999,999.99", Winnings_Non_Ticket="$0.07")))
    assert (history.rows[0].prize_pool_cents, history.rows[0].winnings_non_ticket_cents) == (99_999_999_999_999, 7)
    long_cell = "$1" + ",000" * 3000 + ".00"  # far under the csv cell limit
    for cell in ("$1,000,000,000,000.00", long_cell):
        assert _problems(_history(_row(Prize_Pool=cell))) == ("ENTRY_HISTORY_MONEY_INVALID:row=2:column=Prize_Pool",)


def test_counts_and_points_hold_at_most_nine_integer_digits():
    history = entry_history.parse_entry_history(_history(_row(
        Place="999999999", Contest_Entries="999999999", Places_Paid="999999999", Points="-999999999.99")))
    assert (history.rows[0].place, history.rows[0].points_hundredths) == (999_999_999, -99_999_999_999)
    for column in ("Place", "Contest_Entries", "Places_Paid", "Points"):
        assert len(_problems(_history(_row(**{column: "1000000000"})))) >= 1, column
    assert _problems(_history(_row(Points="01.5"))) == ("ENTRY_HISTORY_POINTS_INVALID:row=2",)


def test_contest_time_is_eastern_aware_and_ambiguous_or_nonexistent_rows_are_kept_and_named():
    raw = _history(
        _row(Contest_Date_EST="2026-12-20 13:00:00"),
        _row(Entry_Key="4000000002", Contest_Key="100000002", Contest_Date_EST="2026-11-01 01:30:00"),
        _row(Entry_Key="4000000003", Contest_Key="100000003", Contest_Date_EST="2026-03-08 02:30:00"),
    )
    history = entry_history.parse_entry_history(raw)
    assert [row.contest_start for row in history.rows] == [
        "2026-12-20T13:00:00-05:00",
        "2026-11-01T01:30:00-04:00",   # fold=0: the first 01:30, still daylight time
        "2026-03-08T02:30:00-05:00",   # a wall time the clocks skipped, read with the offset before the change
    ]
    assert history.notes == (
        {"kind": "CONTEST_TIME_AMBIGUOUS", "row": 3, "sport": "NFL", "entry_key": "4000000002",
         "contest_key": "100000002", "contest_start_text": "2026-11-01 01:30:00"},
        {"kind": "CONTEST_TIME_NONEXISTENT", "row": 4, "sport": "NFL", "entry_key": "4000000003",
         "contest_key": "100000003", "contest_start_text": "2026-03-08 02:30:00"},
    )


def test_a_short_form_date_is_refused_before_strptime_sees_it():
    # `datetime.strptime` accepts single-digit fields; the contract does not.
    for text in ("2026-9-3 13:00:00", "2026-09-13 1:00:00", "2026-09-13 13:0:00", " 2026-09-13 13:00:00"):
        assert _problems(_history(_row(Contest_Date_EST=text))) == ("ENTRY_HISTORY_CONTEST_DATE_INVALID:row=2",), text


def test_problem_details_never_echo_a_cell():
    secret_mlb = _row(Sport="MLB", Entry_Key="4000000009", Contest_Key="100000009", Winnings_Non_Ticket="$9,99SECRET")
    # A non-NFL row with an unreadable date that also pays more places than entries: its note names no date text.
    secret_date = _row(Sport="MLB", Entry_Key="4000000008", Contest_Key="100000008",
                       Contest_Date_EST="$9,999.00 SECRET", Contest_Entries="10", Place="1", Places_Paid="20")
    problems = _problems(_history(
        _row(Place="SECRETPLACE", Points="SECRETPOINTS", Entry_Fee="$SECRET.00", Contest_Date_EST="SECRETDATE")))
    notes = entry_history.parse_entry_history(_history(GOOD[0], secret_mlb, secret_date)).notes
    header_problems = _problems(_history(*GOOD, header=HEADER.replace("Points", "SECRETCOLUMN")))
    assert len(problems) == 4 and len(notes) == 3
    assert notes[2]["kind"] == "PLACES_PAID_ABOVE_CONTEST_ENTRIES" and notes[2]["contest_date"] is None
    text = json.dumps([problems, list(notes), header_problems])
    assert "SECRET" not in text and "9,99" not in text, text
    assert header_problems == ("ENTRY_HISTORY_HEADER_INVALID:missing=Points:extra=1",)


# ---------------------------------------------------------------------------------- the summary


def test_the_summary_counts_by_sport_game_type_and_paid_and_carries_no_money():
    mlb_bad_fee = _row(Sport="MLB", Entry_Key="4000000006", Contest_Key="100000006", Entry_Fee="$1")
    raw = _history(*GOOD, mlb_bad_fee)
    history = entry_history.parse_entry_history(raw)
    summary = entry_history.summary_payload(history, sha256="a" * 64, byte_count=len(raw))
    assert summary["schema_version"] == "nfl_dk_entry_history_intake_v1"
    assert summary["contract"] == "nfl_dk_entry_history_v1"
    assert (summary["source_sha256"], summary["source_bytes"]) == ("a" * 64, len(raw))
    assert (summary["rows_total"], summary["nfl_rows"]) == (5, 3)
    assert summary["rows_by_sport"] == {"MLB": 2, "NFL": 3}
    assert summary["rows_by_game_type"] == {
        "MLB": {"Classic": {"paid": 1, "free": 0, "fee_unreadable": 1}},
        "NFL": {"Classic": {"paid": 2, "free": 0, "fee_unreadable": 0},
                "Showdown Captain Mode": {"paid": 0, "free": 1, "fee_unreadable": 0}},
    }
    assert summary["notes"] == [{"kind": "NON_NFL_RULE_NOT_MET", "row": 6, "sport": "MLB",
                                 "rule": "ENTRY_HISTORY_MONEY_INVALID:row=6:column=Entry_Fee"}]
    assert summary["note_counts"] == {"NON_NFL_RULE_NOT_MET": 1}
    assert "EXPECTED_VALUE_OR_ROI" in summary["does_not_establish"]
    text = entry_history.canonical_bytes(summary).decode("utf-8")
    assert "$" not in text and "_cents" not in text and "Synthetic" not in text


def test_the_summary_is_deterministic_canonical_and_follows_the_bytes():
    raw = _history(*GOOD)
    history = entry_history.parse_entry_history(raw)
    once = entry_history.canonical_bytes(entry_history.summary_payload(history, sha256="b" * 64, byte_count=len(raw)))
    again = entry_history.canonical_bytes(entry_history.summary_payload(
        entry_history.parse_entry_history(raw), sha256="b" * 64, byte_count=len(raw)))
    assert once == again and once.endswith(b"}\n") and b"\r" not in once and b": " not in once
    decoded = json.loads(once)
    assert list(decoded) == sorted(decoded)
    moved = _history(GOOD[0], GOOD[1], _row(**dict(zip(COLUMNS, GOOD[2]), Entry_Fee="$1.00", Prize_Pool="$1.00")),
                     GOOD[3])
    other = entry_history.summary_payload(entry_history.parse_entry_history(moved), sha256="b" * 64,
                                          byte_count=len(moved))
    assert other["rows_by_game_type"]["NFL"]["Showdown Captain Mode"] == {"paid": 1, "free": 0, "fee_unreadable": 0}


# ----------------------------------------------------------------------- not a run input


def test_the_export_header_is_not_a_run_input_for_classify_csv(tmp_path):
    # Classification for runs is untouched: the export stays an unclassified CSV, so two exports in one
    # `--input-dir` are never run-slate's ambiguity refusal.
    from nfl_dfs.cowork import classify_csv, discover_csv_inputs

    folder = tmp_path / "inputs"
    folder.mkdir()
    for name in ("history.csv", "DKEntries.csv"):
        (folder / name).write_bytes(_history(*GOOD))
    assert classify_csv(folder / "history.csv") is None
    discovered = discover_csv_inputs(folder)
    assert discovered.classified == {} and len(discovered.unclassified_csvs) == 2


# -------------------------------------------------------------------------- the gate registry


def test_every_part_one_code_is_registered_as_p_in_entry_history():
    registry = load_gate_registry()
    for code in entry_history.PARSE_CODES:
        assert registry.codes[code] == "entry_history", code
    family = registry.families["entry_history"]
    assert family.gate_class is GateClass.P
    assert set(entry_history.PARSE_CODES) <= {code for code, name in registry.codes.items() if name == "entry_history"}


def test_the_contract_has_a_heading_the_registry_provenance_can_cite():
    headings = {
        line.lstrip("#").strip()
        for line in (REPO / "docs" / "DATA_CONTRACTS.md").read_text(encoding="utf-8").splitlines()
        if line.startswith("#")
    }
    assert load_gate_registry().families["entry_history"].provenance.ref in headings
