"""Session 23d: `nfl_contest_facts_v1`, the paid fraction and the `FIRST_PLACE_OBJECTIVE` label.

The parser is strict (a whole file is refused, every bad row named), the label is integer arithmetic on
supplied numbers and takes no contest name, the block is deterministic and canonical, and the review's
recompute never raises: every failure it meets is one registered `P` code. Fixtures are bytes written with
`write_bytes`, never text, so the Windows runner sees the same hashes as Linux.
"""

from __future__ import annotations

import copy
import hashlib
import inspect
import json
from fractions import Fraction
from pathlib import Path

import pytest

from nfl_dfs import contest_facts
from nfl_dfs.contracts import GateClass
from nfl_dfs.gate_registry import load_gate_registry

HEADER_LINE = "contest_id,field_size,places_paid,entry_fee"
LABEL = "FIRST_PLACE_OBJECTIVE"
# entry id, contest id, entry fee as the template parser holds it (a float)
ENTRIES = (
    ("9001", "111", 20.0),
    ("9002", "111", 20.0),
    ("9003", "222", 5.0),
    ("9004", "333", 0.25),
)
GOOD_ROWS = ("111,1000,49,20", "222,200,40,$5.00", "333,50,5,0.25")


def _facts(*rows: str, eol: str = "\n", bom: bool = False, header: str = HEADER_LINE) -> bytes:
    text = eol.join([header, *rows]) + eol
    return (b"\xef\xbb\xbf" if bom else b"") + text.encode("utf-8")


def _write(tmp_path: Path, raw: bytes, name: str = "facts.csv") -> Path:
    path = tmp_path / name
    path.write_bytes(raw)
    return path


def _problems(raw: bytes) -> tuple[str, ...]:
    with pytest.raises(contest_facts.ContestFactsRefused) as caught:
        contest_facts.parse_contest_facts(raw)
    return caught.value.problems


def _head(problem: str) -> str:
    return problem.split(":", 1)[0]


def _block(tmp_path: Path, *rows: str, entries=ENTRIES) -> dict:
    return contest_facts.build_block(_write(tmp_path, _facts(*rows)), entries)


# ---------------------------------------------------------------------------- the parser accepts


@pytest.mark.parametrize(
    "kwargs",
    [{}, {"eol": "\r\n"}, {"bom": True}, {"bom": True, "eol": "\r\n"}],
    ids=["lf", "crlf", "bom", "bom_crlf"],
)
def test_a_good_file_parses_to_exact_integers_whatever_its_line_endings(kwargs):
    rows = contest_facts.parse_contest_facts(_facts(*GOOD_ROWS, **kwargs))
    assert [(r.contest_id, r.field_size, r.places_paid, r.fee_cents) for r in rows] == [
        ("111", 1000, 49, 2000),
        ("222", 200, 40, 500),
        ("333", 50, 5, 25),
    ]


def test_a_contest_that_pays_every_place_is_a_legal_row_and_a_spaced_header_still_parses():
    rows = contest_facts.parse_contest_facts(_facts("1,100,100,1", header=" contest_id , field_size ,places_paid, entry_fee "))
    assert [(r.field_size, r.places_paid) for r in rows] == [(100, 100)]


def test_the_size_cap_is_exact_one_megabyte_parses_and_one_byte_more_does_not():
    base = _facts(*GOOD_ROWS)
    assert len(contest_facts.parse_contest_facts(base + b"\n" * (contest_facts.MAX_BYTES - len(base)))) == 3
    assert _head(_problems(base + b"\n" * (contest_facts.MAX_BYTES + 1 - len(base)))[0]) == "CONTEST_FACTS_FILE_TOO_LARGE"


def test_cells_are_trimmed_a_dollar_sign_is_allowed_and_a_zero_fee_is_a_freeroll():
    rows = contest_facts.parse_contest_facts(_facts(" 7 , 100 , 10 , $0 ", "8,100,10,0.10"))
    assert [(r.contest_id, r.field_size, r.places_paid, r.fee_cents) for r in rows] == [
        ("7", 100, 10, 0), ("8", 100, 10, 10)]


# ------------------------------------------------------- one named refusal per kind of bad input

# (code, raw bytes). Row numbers count the header as row 1, so the first data row is `row=2`.
HEADER_VARIANTS = (
    "contest_id,field_size,places_paid",                       # a missing column
    "contest_id,field_size,places_paid,entry_fee,extra",       # an extra one
    "field_size,contest_id,places_paid,entry_fee",             # reordered
    "Contest ID,field_size,places_paid,entry_fee",             # renamed
)
BAD = [
    ("CONTEST_FACTS_FILE_EMPTY", b""),
    ("CONTEST_FACTS_FILE_TOO_LARGE", b"x" * (contest_facts.MAX_BYTES + 1)),
    ("CONTEST_FACTS_NOT_TEXT", b"\xff\xfe\x00\x01" + _facts("1,100,10,1")),
    ("CONTEST_FACTS_NOT_TEXT", _facts("1,100,10,1\x00")),
    *[("CONTEST_FACTS_HEADER_INVALID", _facts("1,100,10,1", header=header)) for header in HEADER_VARIANTS],
    ("CONTEST_FACTS_NO_ROWS", _facts()),
    ("CONTEST_FACTS_ROW_MISSHAPEN", _facts("1,100,10")),                          # truncated
    ("CONTEST_FACTS_ROW_MISSHAPEN", _facts("1,100,10,1,9")),                      # overlong
    ("CONTEST_FACTS_ROW_MISSHAPEN", HEADER_LINE.encode() + b'\n"1,100,10,1\n'),   # an unterminated quote
    ("CONTEST_FACTS_ROW_MISSHAPEN", _facts("1,100,10,1")[:-8]),                   # cut mid-row
    ("CONTEST_FACTS_CONTEST_ID_INVALID", _facts(",100,10,1")),
    ("CONTEST_FACTS_CONTEST_ID_INVALID", _facts("abc,100,10,1")),
    ("CONTEST_FACTS_CONTEST_ID_INVALID", _facts("-5,100,10,1")),
    ("CONTEST_FACTS_CONTEST_ID_INVALID", _facts("1.5,100,10,1")),
    ("CONTEST_FACTS_CONTEST_ID_INVALID", _facts("١٢٣,100,10,1")),  # Arabic-Indic digits
    ("CONTEST_FACTS_CONTEST_ID_INVALID", _facts("1" * 19 + ",100,10,1")),
    ("CONTEST_FACTS_CONTEST_ID_DUPLICATE", _facts("5,100,10,1", "5,200,10,1")),
    ("CONTEST_FACTS_FIELD_SIZE_INVALID", _facts("1,,10,1")),
    ("CONTEST_FACTS_FIELD_SIZE_INVALID", _facts("1,abc,10,1")),
    ("CONTEST_FACTS_FIELD_SIZE_INVALID", _facts('1,"1,000",10,1')),
    ("CONTEST_FACTS_FIELD_SIZE_INVALID", _facts("1,1e3,10,1")),
    ("CONTEST_FACTS_FIELD_SIZE_INVALID", _facts("1,1000.0,10,1")),
    ("CONTEST_FACTS_FIELD_SIZE_INVALID", _facts("1," + "9" * 5000 + ",10,1")),     # no int-conversion crash
    ("CONTEST_FACTS_FIELD_SIZE_INVALID", _facts("1,1234567890123,10,1")),         # 13 digits
    ("CONTEST_FACTS_FIELD_SIZE_NOT_POSITIVE", _facts("1,0,10,1")),
    ("CONTEST_FACTS_FIELD_SIZE_NOT_POSITIVE", _facts("1,-100,10,1")),
    ("CONTEST_FACTS_PLACES_PAID_INVALID", _facts("1,100,,1")),
    ("CONTEST_FACTS_PLACES_PAID_INVALID", _facts("1,100,ten,1")),
    ("CONTEST_FACTS_PLACES_PAID_INVALID", _facts("1,100,10.5,1")),
    ("CONTEST_FACTS_PLACES_PAID_NOT_POSITIVE", _facts("1,100,0,1")),
    ("CONTEST_FACTS_PLACES_PAID_NOT_POSITIVE", _facts("1,100,-1,1")),
    ("CONTEST_FACTS_PLACES_PAID_EXCEEDS_FIELD_SIZE", _facts("1,100,101,1")),
    ("CONTEST_FACTS_ENTRY_FEE_INVALID", _facts("1,100,10,")),
    ("CONTEST_FACTS_ENTRY_FEE_INVALID", _facts("1,100,10,abc")),
    ("CONTEST_FACTS_ENTRY_FEE_INVALID", _facts("1,100,10,-1")),
    ("CONTEST_FACTS_ENTRY_FEE_INVALID", _facts("1,100,10,1.234")),
    ("CONTEST_FACTS_ENTRY_FEE_INVALID", _facts("1,100,10,.5")),
    ("CONTEST_FACTS_ENTRY_FEE_INVALID", _facts("1,100,10,$")),
    ("CONTEST_FACTS_ENTRY_FEE_INVALID", _facts("1,100,10,1e1")),
]


@pytest.mark.parametrize("code,raw", BAD, ids=[f"{code[14:]}-{index}" for index, (code, _) in enumerate(BAD)])
def test_a_bad_file_is_refused_by_name_and_never_parsed_in_part(code, raw):
    problems = _problems(raw)
    assert _head(problems[0]) == code, problems
    assert all(_head(problem).startswith("CONTEST_FACTS_") for problem in problems)


def test_every_parser_code_has_a_case_above_and_nothing_else_is_emitted():
    assert {code for code, _ in BAD} == set(contest_facts.PARSE_CODES)
    assert len(contest_facts.PARSE_CODES) == len(set(contest_facts.PARSE_CODES)) == 14


def test_a_row_level_refusal_names_its_row_and_every_bad_row_is_listed_in_file_order():
    raw = _facts("1,100,10,1", "2,abc,10,1", "3,100,0,1", "4,100,10,-1", "1,100,10,1", "6,100,101,1")
    problems = _problems(raw)
    assert problems == (
        "CONTEST_FACTS_FIELD_SIZE_INVALID:row=3",
        "CONTEST_FACTS_PLACES_PAID_NOT_POSITIVE:row=4",
        "CONTEST_FACTS_ENTRY_FEE_INVALID:row=5",
        "CONTEST_FACTS_CONTEST_ID_DUPLICATE:row=6:first=2",
        "CONTEST_FACTS_PLACES_PAID_EXCEEDS_FIELD_SIZE:row=7",
    )


def test_one_bad_row_refuses_the_whole_file_and_no_row_is_kept():
    raw = _facts("1,1000,10,1", "2,1000,10,1", "3,1000,10,1", "4,1000,2000,1")
    with pytest.raises(contest_facts.ContestFactsRefused):
        contest_facts.parse_contest_facts(raw)


def test_a_fully_blank_line_between_rows_is_skipped_but_a_row_of_commas_is_not():
    raw = HEADER_LINE.encode() + b"\n1,100,10,1\n\n2,100,10,1\n"
    assert [r.contest_id for r in contest_facts.parse_contest_facts(raw)] == ["1", "2"]
    assert _head(_problems(_facts(",,,"))[0]) == "CONTEST_FACTS_CONTEST_ID_INVALID"


# ------------------------------------------------------------------------------- the label


@pytest.mark.parametrize(
    "places,field,expected",
    [
        (49, 1000, LABEL),    # 4.9%: just under
        (50, 1000, None),     # exactly 5%: not under
        (51, 1000, None),     # just over
        (1, 20, None),        # exactly 5% in a small field
        (1, 21, LABEL),       # 4.76%
        (1, 1, None),         # a one-entry field pays everyone
        (100, 100, None),     # places paid equal to the field
        (1, 100000, LABEL),
        (2, 39, None),
        (2, 41, LABEL),
    ],
)
def test_the_label_is_strictly_under_five_percent_in_integer_arithmetic(places, field, expected):
    assert contest_facts.first_place_label(places, field) == expected


def test_the_label_agrees_with_exact_fractions_over_a_grid_and_takes_no_contest_name():
    for field in range(1, 301):
        for places in range(1, field + 1):
            under = Fraction(places, field) < Fraction(1, 20)
            assert (contest_facts.first_place_label(places, field) == LABEL) is under, (places, field)
    assert list(inspect.signature(contest_facts.first_place_label).parameters) == ["places_paid", "field_size"]
    assert list(inspect.signature(contest_facts.build_block).parameters) == ["path", "entries"]


# --------------------------------------------------------------------------- the block


def test_a_supplied_file_labels_each_entry_from_its_contests_numbers(tmp_path):
    block = _block(tmp_path, *GOOD_ROWS)
    assert block["status"] == "APPLIED"
    assert block["schema_version"] == contest_facts.BLOCK_VERSION
    assert block["contest_facts_label_version"] == contest_facts.LABEL_VERSION
    by_entry = {row["entry_id"]: row for row in block["entries"]}
    # 49/1000 < 5%, 40/200 = 20%, 5/50 = 10%
    assert [by_entry[e]["label"] for e in ("9001", "9002", "9003", "9004")] == [LABEL, LABEL, None, None]
    assert by_entry["9001"]["paid_fraction"] == "49/1000"
    assert by_entry["9001"]["paid_fraction_decimal"] == "0.049000"
    assert by_entry["9003"]["paid_fraction"] == "1/5" and by_entry["9003"]["paid_fraction_decimal"] == "0.200000"
    assert block["entries_labelled"] == 2
    assert [row["contest_id"] for row in block["contests"]] == ["111", "222", "333"]
    assert block["facts_sha256"] == hashlib.sha256(_facts(*GOOD_ROWS)).hexdigest()
    assert block["problems"] == [] and block["unused_contest_ids"] == []


def test_the_block_says_what_it_does_not_establish_and_never_reads_as_a_claim_of_value():
    assert "EXPECTED_VALUE_OR_ROI" in contest_facts.DOES_NOT_ESTABLISH
    assert "WIN_OR_CASH_PROBABILITY" in contest_facts.DOES_NOT_ESTABLISH
    assert "UPLOAD_CLEARANCE" in contest_facts.DOES_NOT_ESTABLISH


def test_entries_keep_the_entry_files_order_and_the_decimal_rounds_half_even(tmp_path):
    entries = (("9", "3", 1.0), ("2", "128", 1.0), ("5", "1", 1.0), ("7", "5", 1.0))
    block = contest_facts.build_block(
        _write(tmp_path, _facts("3,3,2,1", "128,128,1,1", "1,128,3,1", "5,5,5,1")), entries)
    assert [row["entry_id"] for row in block["entries"]] == ["9", "2", "5", "7"]
    assert [row["contest_id"] for row in block["contests"]] == ["1", "128", "3", "5"]   # contests sort as text
    decimals = {row["contest_id"]: row["paid_fraction_decimal"] for row in block["contests"]}
    # 2/3 rounds up to 0.666667; 1/128 = 0.0078125 and 3/128 = 0.0234375 sit exactly on a half: to the even digit
    assert decimals == {"3": "0.666667", "128": "0.007812", "1": "0.023438", "5": "1.000000"}


def test_a_facts_row_for_a_contest_with_no_entry_is_ignored_and_named(tmp_path):
    block = _block(tmp_path, *GOOD_ROWS, "999,500,10,2")
    assert block["status"] == "APPLIED"
    assert block["unused_contest_ids"] == ["999"]
    assert block["facts_row_count"] == 4


def test_an_entry_whose_contest_has_no_row_is_unlabelled_and_the_block_is_partial(tmp_path):
    block = _block(tmp_path, "111,1000,49,20")
    assert block["status"] == "PARTIAL"
    states = {row["entry_id"]: (row["facts_state"], row["label"]) for row in block["entries"]}
    assert states == {
        "9001": ("SUPPLIED", LABEL), "9002": ("SUPPLIED", LABEL),
        "9003": ("NO_FACTS_ROW", None), "9004": ("NO_FACTS_ROW", None)}
    assert block["contests_without_row"] == ["222", "333"]


def test_a_file_for_another_slate_labels_nothing_and_says_so(tmp_path):
    block = _block(tmp_path, "7001,1000,10,20", "7002,1000,10,5")
    assert block["status"] == "PARTIAL" and block["entries_labelled"] == 0
    assert block["contests_without_row"] == ["111", "222", "333"]
    assert block["unused_contest_ids"] == ["7001", "7002"]


def test_a_fee_that_disagrees_with_the_entry_file_drops_only_that_contest(tmp_path):
    block = _block(tmp_path, "111,1000,49,25", "222,200,10,5", "333,50,1,0.25")
    assert block["status"] == "PARTIAL"
    states = {row["contest_id"]: row for row in block["contests"]}
    assert states["111"]["facts_state"] == "FEE_DISAGREES" and states["111"]["label"] is None
    assert states["111"]["facts_fee_cents"] == 2500 and states["111"]["entry_file_fee_cents"] == [2000]
    assert states["111"]["paid_fraction"] is None
    assert states["333"]["facts_state"] == "SUPPLIED" and states["333"]["label"] == LABEL  # 1/50 is 2%
    assert states["222"]["label"] is None                                                  # 10/200 is 5%: not under
    assert block["contests_fee_disagree"] == ["111"]


def test_fees_compare_in_whole_cents_so_a_float_fee_never_disagrees_with_itself(tmp_path):
    entries = (("1", "5", 0.1), ("2", "6", 1.1), ("3", "7", 0.07))
    block = contest_facts.build_block(
        _write(tmp_path, _facts("5,100,2,0.10", "6,100,2,1.10", "7,100,2,0.07")), entries)
    assert block["status"] == "APPLIED", block["contests"]


def test_the_label_follows_the_numbers_not_the_contest_name(tmp_path):
    # The module sees ids, fees and numbers only. A satellite whose numbers pay 40% is unlabelled; a "single
    # entry" contest paying 0.5% is labelled; the names are the caller's and never reach this function.
    block = _block(tmp_path, "111,1000,400,20", "222,2000,10,5", "333,50,5,0.25")
    by_contest = {row["contest_id"]: row["label"] for row in block["contests"]}
    assert by_contest == {"111": None, "222": LABEL, "333": None}


def test_the_block_is_deterministic_and_a_changed_byte_changes_its_bound_hash(tmp_path):
    first = _block(tmp_path, *GOOD_ROWS)
    second = contest_facts.build_block(tmp_path / "facts.csv", ENTRIES)
    assert first == second
    assert contest_facts.canonical_bytes(first) == contest_facts.canonical_bytes(second)
    changed = contest_facts.build_block(_write(tmp_path, _facts("111,1000,49,20", "222,200,40,$5.00", "333,50,5,0.26"),
                                               "changed.csv"), ENTRIES)
    assert changed["facts_sha256"] != first["facts_sha256"]
    assert contest_facts.canonical_bytes(changed) != contest_facts.canonical_bytes(first)


def test_canonical_bytes_are_sorted_compact_lf_terminated_and_hold_no_float(tmp_path):
    raw = contest_facts.canonical_bytes(_block(tmp_path, *GOOD_ROWS))
    assert raw.endswith(b"\n") and b"\r" not in raw and raw.count(b"\n") == 1
    assert raw == (json.dumps(json.loads(raw), sort_keys=True, separators=(",", ":")) + "\n").encode()

    def refuse(text):
        raise AssertionError(f"a float in the block: {text}")

    json.loads(raw, parse_float=refuse)


def test_no_file_supplied_is_a_status_and_labels_nothing():
    block = contest_facts.build_block(None, ENTRIES)
    assert block["status"] == "NOT_SUPPLIED" and block["entries_labelled"] == 0
    assert "does not say" in block["meaning"]
    assert block["entries"] == [] and block["contests"] == []
    assert contest_facts.limitations(block) == []


def test_a_unicode_digit_contest_id_in_the_entry_file_never_matches_an_ascii_row(tmp_path):
    entries = (("1", "١٢٣", 5.0), ("2", "123", 5.0))
    block = contest_facts.build_block(_write(tmp_path, _facts("123,100,2,5")), entries)
    states = {row["entry_id"]: row["facts_state"] for row in block["entries"]}
    assert states == {"1": "NO_FACTS_ROW", "2": "SUPPLIED"}


# ------------------------------------------------------ hostile states: never an exception, never an OK


def test_a_refused_file_is_a_refused_block_with_every_problem_and_no_label(tmp_path):
    block = _block(tmp_path, "111,abc,10,20", "222,200,40,5")
    assert block["status"] == "REFUSED"
    assert block["problems"] == ["CONTEST_FACTS_FIELD_SIZE_INVALID:row=2"]
    assert block["entries"] == [] and block["contests"] == [] and block["entries_labelled"] == 0
    assert block["facts_sha256"] == hashlib.sha256(_facts("111,abc,10,20", "222,200,40,5")).hexdigest()
    (limitation,) = contest_facts.limitations(block)
    assert limitation.startswith("CONTEST_FACTS_REFUSED:CONTEST_FACTS_FIELD_SIZE_INVALID:1")


def test_a_missing_or_unreadable_path_is_a_named_refusal_not_an_exception(tmp_path, monkeypatch):
    missing = contest_facts.build_block(tmp_path / "nowhere.csv", ENTRIES)
    assert missing["status"] == "REFUSED" and missing["problems"] == ["CONTEST_FACTS_UNREADABLE"]
    assert missing["facts_sha256"] is None
    folder = contest_facts.build_block(tmp_path, ENTRIES)
    assert folder["problems"] == ["CONTEST_FACTS_UNREADABLE"]
    path = _write(tmp_path, _facts(*GOOD_ROWS))
    monkeypatch.setattr(Path, "read_bytes", lambda self: (_ for _ in ()).throw(PermissionError("denied")))
    assert contest_facts.build_block(path, ENTRIES)["problems"] == ["CONTEST_FACTS_UNREADABLE"]


def test_a_step_that_raises_is_named_and_never_stops_the_run(tmp_path, monkeypatch):
    path = _write(tmp_path, _facts(*GOOD_ROWS))
    monkeypatch.setattr(contest_facts, "parse_contest_facts", lambda raw: (_ for _ in ()).throw(RuntimeError("x;y")))
    block = contest_facts.build_block(path, ENTRIES)
    assert block["status"] == "REFUSED"
    assert block["problems"] == ["CONTEST_FACTS_STEP_FAILED:RuntimeError"]    # the class name only, never the message
    assert contest_facts.limitations(block)[0].startswith("CONTEST_FACTS_REFUSED:CONTEST_FACTS_STEP_FAILED")


def test_the_oversize_and_non_text_files_never_reach_the_parser_as_text(tmp_path):
    big = contest_facts.build_block(_write(tmp_path, b"x" * (contest_facts.MAX_BYTES + 1)), ENTRIES)
    assert big["problems"] == ["CONTEST_FACTS_FILE_TOO_LARGE"]
    nul = contest_facts.build_block(_write(tmp_path, _facts("1,100,10,1\x00"), "nul.csv"), ENTRIES)
    assert nul["problems"] == ["CONTEST_FACTS_NOT_TEXT"]


# ------------------------------------------------------------- limitations a run carries


def test_limitations_name_each_gap_and_an_applied_block_names_none(tmp_path):
    assert contest_facts.limitations(_block(tmp_path, *GOOD_ROWS)) == []
    partial = contest_facts.limitations(_block(tmp_path, "111,1000,49,20"))
    assert len(partial) == 1 and partial[0].startswith("CONTEST_FACTS_INCOMPLETE:2 entry contest(s)")
    assert "222" in partial[0] and "333" in partial[0]
    fee = contest_facts.limitations(_block(tmp_path, "111,1000,49,25", "222,200,40,5", "333,50,5,0.25"))
    assert len(fee) == 1 and fee[0].startswith("CONTEST_FACTS_FEE_DISAGREES_WITH_ENTRIES:1 contest(s)")
    both = contest_facts.limitations(_block(tmp_path, "111,1000,49,25"))
    assert [item.split(":", 1)[0] for item in both] == [
        "CONTEST_FACTS_INCOMPLETE", "CONTEST_FACTS_FEE_DISAGREES_WITH_ENTRIES"]
    assert all(";" not in item for item in [*partial, *fee, *both])


# --------------------------------------------- the review's recompute: guarded, one code, no exception


def _good_record(tmp_path) -> dict:
    return json.loads(contest_facts.canonical_bytes(_block(tmp_path, *GOOD_ROWS)))


def test_a_sound_block_reconciles_and_returns_exactly_what_it_was_given(tmp_path):
    record = _good_record(tmp_path)
    payload, problems = contest_facts.review_block(record, ENTRIES)
    assert problems == [] and payload == record


def test_no_record_means_no_section_and_no_problem():
    assert contest_facts.review_block(None, ENTRIES) == (None, [])


def _doctored(mutate):
    def build(record):
        mutate(record)
        return record
    return build


DOCTORED = {
    "a_field_size_of_zero": _doctored(lambda r: r["contests"][0].update(field_size=0)),
    "a_string_for_an_integer": _doctored(lambda r: r["contests"][0].update(places_paid="49")),
    "a_boolean_for_an_integer": _doctored(lambda r: r["contests"][0].update(places_paid=True)),
    "a_float_for_an_integer": _doctored(lambda r: r["contests"][0].update(field_size=1000.0)),
    "places_above_the_field": _doctored(lambda r: r["contests"][0].update(places_paid=5000)),
    "a_flipped_label": _doctored(lambda r: r["entries"][0].update(label=None)),
    "a_forged_label": _doctored(lambda r: r["entries"][2].update(label=LABEL)),
    "a_forged_fraction": _doctored(lambda r: r["entries"][0].update(paid_fraction="1/100")),
    "a_missing_key": _doctored(lambda r: r.pop("entries")),
    "a_missing_contest_key": _doctored(lambda r: r["contests"][0].pop("label")),
    "an_extra_entry": _doctored(lambda r: r["entries"].append(
        {"entry_id": "9999", "contest_id": "111", "facts_state": "SUPPLIED", "label": LABEL,
         "paid_fraction": "49/1000", "paid_fraction_decimal": "0.049000"})),
    "a_dropped_entry": _doctored(lambda r: r["entries"].pop()),
    "entries_out_of_order": _doctored(lambda r: r["entries"].reverse()),
    "a_wrong_contest_for_an_entry": _doctored(lambda r: r["entries"][0].update(contest_id="222")),
    "a_wrong_count": _doctored(lambda r: r.update(entries_labelled=7)),
    "a_wrong_status": _doctored(lambda r: r.update(status="PARTIAL")),
    "an_unknown_status": _doctored(lambda r: r.update(status="MAYBE")),
    "contests_not_a_list": _doctored(lambda r: r.update(contests="none")),
    "an_entry_not_a_mapping": _doctored(lambda r: r["entries"].__setitem__(0, "nope")),
    "a_changed_version": _doctored(lambda r: r.update(contest_facts_label_version="other")),
    "a_refused_block_that_carries_labels": _doctored(lambda r: r.update(status="REFUSED", problems=["CONTEST_FACTS_NOT_TEXT"])),
}


# The kind each doctoring is named by: a number or type the recompute cannot read is `contests`, a row that does not
# rebuild from the entry file is `entries`, and anything else the rebuilt block disagrees on is `block`.
DOCTORED_KIND = {
    "a_field_size_of_zero": "contests", "a_string_for_an_integer": "contests", "a_boolean_for_an_integer": "contests",
    "a_float_for_an_integer": "contests", "places_above_the_field": "contests", "contests_not_a_list": "contests",
    "a_missing_contest_key": "contests",
    "a_flipped_label": "entries", "a_forged_label": "entries", "a_forged_fraction": "entries",
    "a_missing_key": "entries", "an_extra_entry": "entries", "a_dropped_entry": "entries",
    "entries_out_of_order": "entries", "a_wrong_contest_for_an_entry": "entries", "an_entry_not_a_mapping": "entries",
    "a_wrong_count": "block", "a_wrong_status": "block", "an_unknown_status": "block", "a_changed_version": "block",
    "a_refused_block_that_carries_labels": "block",
}


def test_every_doctoring_has_an_expected_kind():
    assert set(DOCTORED_KIND) == set(DOCTORED)
    assert set(DOCTORED_KIND.values()) == {"contests", "entries", "block"}


@pytest.mark.parametrize("name", sorted(DOCTORED))
def test_a_doctored_block_is_one_registered_code_of_the_right_kind_and_never_an_exception(tmp_path, name):
    record = DOCTORED[name](_good_record(tmp_path))
    payload, problems = contest_facts.review_block(record, ENTRIES)
    assert payload is None
    assert problems == [f"CONTEST_FACTS_REVIEW_MISMATCH:{DOCTORED_KIND[name]}"], problems


@pytest.mark.parametrize("not_a_mapping", [None, [], "text", 7, 1.5, True])
def test_a_record_that_is_not_a_mapping_is_a_mismatch_unless_it_is_absent(not_a_mapping):
    payload, problems = contest_facts.review_block(not_a_mapping, ENTRIES)
    if not_a_mapping is None:
        assert (payload, problems) == (None, [])
    else:
        assert payload is None and problems and problems[0].startswith("CONTEST_FACTS_REVIEW_MISMATCH:")


def test_a_block_from_another_template_is_a_mismatch(tmp_path):
    record = _good_record(tmp_path)
    other = (("8001", "111", 20.0), ("8002", "222", 5.0))
    payload, problems = contest_facts.review_block(record, other)
    assert payload is None and problems == ["CONTEST_FACTS_REVIEW_MISMATCH:entries"]
    changed_fee = (("9001", "111", 21.0), *ENTRIES[1:])
    payload, problems = contest_facts.review_block(record, changed_fee)
    assert payload is None and problems and problems[0].startswith("CONTEST_FACTS_REVIEW_MISMATCH:")


def test_the_review_recomputes_a_fee_disagreement_from_the_entry_file_itself(tmp_path):
    record = json.loads(contest_facts.canonical_bytes(
        _block(tmp_path, "111,1000,49,25", "222,200,40,5", "333,50,5,0.25")))
    payload, problems = contest_facts.review_block(record, ENTRIES)
    assert problems == [] and payload["status"] == "PARTIAL"
    forged = copy.deepcopy(record)
    for row in forged["entries"]:
        if row["contest_id"] == "111":
            row.update(facts_state="SUPPLIED", label=LABEL, paid_fraction="49/1000", paid_fraction_decimal="0.049000")
    assert contest_facts.review_block(forged, ENTRIES)[0] is None


def test_the_refused_and_the_not_supplied_blocks_reconcile_as_they_are(tmp_path):
    refused = json.loads(contest_facts.canonical_bytes(_block(tmp_path, "111,abc,10,20")))
    assert contest_facts.review_block(refused, ENTRIES) == (refused, [])
    stub = json.loads(contest_facts.canonical_bytes(contest_facts.build_block(None, ENTRIES)))
    assert contest_facts.review_block(stub, ENTRIES) == (stub, [])


def test_the_review_never_raises_whatever_it_is_given(tmp_path):
    hostile = [{}, {"status": "APPLIED"}, {"status": "APPLIED", "contests": [None], "entries": [[]]},
               {"status": "APPLIED", "contests": [{"contest_id": 1}], "entries": []},
               {"status": "PARTIAL", "contests": [], "entries": [], "facts_row_count": -1}]
    for record in hostile:
        payload, problems = contest_facts.review_block(record, ENTRIES)
        assert payload is None and len(problems) == 1 and problems[0].startswith("CONTEST_FACTS_REVIEW_MISMATCH:")
    assert contest_facts.review_block(_good_record(tmp_path), (("1", "111"),))[1] == [
        "CONTEST_FACTS_REVIEW_MISMATCH:template"]   # a template row the review cannot read


def test_the_artifact_loader_names_a_missing_changed_or_unreadable_file(tmp_path):
    good = _write(tmp_path, contest_facts.canonical_bytes(_block(tmp_path, *GOOD_ROWS)), "contest_facts.json")
    digest = hashlib.sha256(good.read_bytes()).hexdigest()
    record, problems = contest_facts.load_record(good, digest)
    assert problems == [] and record["status"] == "APPLIED"
    assert contest_facts.load_record(tmp_path / "gone.json", digest) == (None, ["CONTEST_FACTS_REVIEW_MISMATCH:missing"])
    assert contest_facts.load_record(good, "0" * 64) == (None, ["CONTEST_FACTS_REVIEW_MISMATCH:sha256"])
    assert contest_facts.load_record(good, None) == (None, ["CONTEST_FACTS_REVIEW_MISMATCH:sha256"])
    torn = _write(tmp_path, b'{"status": ', "torn.json")
    assert contest_facts.load_record(torn, hashlib.sha256(torn.read_bytes()).hexdigest()) == (
        None, ["CONTEST_FACTS_REVIEW_MISMATCH:invalid"])
    folder = contest_facts.load_record(tmp_path, digest)
    assert folder == (None, ["CONTEST_FACTS_REVIEW_MISMATCH:missing"])
    # a hash-correct artifact that is JSON `null` (or a list or a number) is a file the review cannot read, not "no file"
    for index, body in enumerate((b"null\n", b"[]\n", b"7\n", b'"text"\n', b"true\n")):
        odd = _write(tmp_path, body, f"odd{index}.json")
        assert contest_facts.load_record(odd, hashlib.sha256(body).hexdigest()) == (
            None, ["CONTEST_FACTS_REVIEW_MISMATCH:invalid"]), body


# ------------------------------------------------------------------------- the gate registry


def test_every_contest_facts_code_is_registered_in_the_right_family_and_class():
    registry = load_gate_registry()
    emitted = set(contest_facts.PARSE_CODES) | set(contest_facts.RUN_CODES)
    for code in emitted:
        assert registry.codes[code] == "contest_facts", code
    assert registry.codes["CONTEST_FACTS_REVIEW_MISMATCH"] == "presentation"
    family = registry.families["contest_facts"]
    assert family.gate_class is GateClass.P
    assert {code for code, name in registry.codes.items() if name == "contest_facts"} == emitted
    assert {code for code in registry.codes if code.startswith("CONTEST_FACTS_")} == emitted | {
        "CONTEST_FACTS_REVIEW_MISMATCH"}
    assert len(emitted) == 19


def test_the_contract_has_a_heading_the_registry_provenance_can_cite():
    headings = {
        line.lstrip("#").strip()
        for line in (Path(__file__).resolve().parents[1] / "docs" / "DATA_CONTRACTS.md")
        .read_text(encoding="utf-8").splitlines() if line.startswith("#")
    }
    assert load_gate_registry().families["contest_facts"].provenance.ref in headings
