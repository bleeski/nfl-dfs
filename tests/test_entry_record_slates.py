"""Session 72b on committed DraftKings bytes: the four Session 72 records do not move, and `(LOCKED)` cells read exactly.

Without a run folder every run field stays null and the four committed records are still the builder's bytes. Week 5
Classic's graded file is DraftKings' own late-swap export edited in place: its `Name (ID) (LOCKED)` cells read to their exact
IDs against that export as its template (33 Entry IDs, Ben's free entry among them), so the file the record refused in
Session 72 now builds. Recording it and the other committed slates is Session 72c's backfill.
"""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path

import pytest

from nfl_dfs.dk import parse_entries
from nfl_dfs.entry_record import EntryRecordRefused, build_records, record_bytes

SLATES = Path(__file__).resolve().parent.parent / "data" / "inbox" / "slates"
RECORD = "construction/entry_build_record.jsonl"
# Session 72's four, recorded without a run folder: their bytes must not move.
COMMITTED = {
    "det-car": ("det-car-sd-2026-10-04", "construction/DK_REVIEW_ENTRY_det-car-sd_final_v5.csv", "input/DKSalaries.csv",
                "input/DKEntries.csv", {"scores": "construction/pool_scores.json"}),
    "atl-no": ("atl-no-sd-2026-10-05", "construction/qa_iter3/DK_REVIEW_ENTRY_atl-no-sd_qa_iter3.csv",
               "input/DKSalaries_143.csv", "input/DKEntries_116.csv", {"scores": "construction/pool_scores.json"}),
    "tb-dal": ("tb-dal-sd-2026-10-08", "construction/DK_REVIEW_ENTRY_tb-dal-sd_final_v3.csv", "input/DKSalaries.csv",
               "input/DKEntries.csv", {"scores": "construction/pool_scores.json"}),
    "wk4": ("wk4-classic-2026-10-04", "DK_REVIEW_ENTRY_wk4_classic_LATESWAP_v8.csv", "DKSalaries.csv", "DKEntries.csv",
            {"portfolio": "construction/portfolio_lateswap_v8.json"}),
}
WK5 = SLATES / "wk5-classic-2026-10-11"
BUF_LAR = SLATES / "buf-lar-sd-2026-10-12"
_ID = re.compile(r"\(([0-9]+)\)(?:\s*\(LOCKED\))?\s*$")


def _csv_rows(path: Path) -> list[list[str]]:
    return list(csv.reader(io.StringIO(path.read_bytes().decode("utf-8-sig"), newline="")))


@pytest.mark.parametrize("label", list(COMMITTED), ids=list(COMMITTED))
def test_without_run_dir_the_run_fields_stay_null_and_the_committed_records_do_not_move(label):
    slug, file, salaries, entries, source = COMMITTED[label]
    base = SLATES / slug
    rows = build_records(base / salaries, base / entries, base / file, **{k: base / v for k, v in source.items()})
    assert (base / RECORD).read_bytes() == record_bytes(rows)
    for row in rows:
        assert row["run"] == {"run_id": None, "method": None, "policy_sha256": None, "thesis": None,
                              "reasons": dict.fromkeys(("run_id", "method", "policy_sha256", "thesis"),
                                                       "RUN_FOLDER_NOT_SUPPLIED")}
        assert row["stack_game"]["market"] is None and row["stack_game"]["market_reason"] == "RUN_FOLDER_NOT_SUPPLIED"


def test_week_5_classics_late_swap_export_reads_every_locked_cell_to_its_exact_id():
    file, template = WK5 / "DK_LATESWAP_wk5_classic_v10.csv", WK5 / "live" / "DKEntries_current_1914Z.csv"
    rows = _csv_rows(file)
    start = rows[0].index("Entry Fee") + 1
    cells = {row[0]: [cell.strip() for cell in row[start:start + 9]] for row in rows[1:] if row and row[0].strip().isdigit()}
    locked = sum(cell.endswith("(LOCKED)") for roster in cells.values() for cell in roster)
    assert locked == 187 and len(cells) == 33  # DraftKings marks every started player's cell
    records = build_records(WK5 / "input" / "DKSalaries.csv", template, file)
    assert [row["entry_id"] for row in records] == [entry.entry_id for entry in parse_entries(template).authorizations]
    for row in records:
        assert row["roster"] == [_ID.search(cell).group(1) for cell in cells[row["entry_id"]]]


@pytest.mark.parametrize("cell, code", [
    ("{name} ({dk_id}) (LOCKED)", None),
    ("{name} ({dk_id})  (LOCKED) ", None),
    ("(LOCKED)", "ENTRY_RECORD_CELL_NOT_AN_EXACT_DK_ID"),
    ("{name} (LOCKED)", "ENTRY_RECORD_CELL_NOT_AN_EXACT_DK_ID"),
    ("{name} ({dk_id}) (LOCKED) (LOCKED)", "ENTRY_RECORD_CELL_NOT_AN_EXACT_DK_ID"),
], ids=["locked", "spaced", "bare-locked", "no-id", "twice"])
def test_a_locked_cell_is_read_to_its_exact_id_and_nothing_else(tmp_path, cell, code):
    """One cell of BUF@LAR's delivered file rewritten as DraftKings writes a started player: only the file's hash moves."""

    salaries, entries = BUF_LAR / "input" / "DKSalaries.csv", BUF_LAR / "input" / "DKEntries.csv"
    original, scores = BUF_LAR / "construction" / "DK_REVIEW_ENTRY_buf-lar-sd_final_v2.csv", BUF_LAR / "construction" / "pool_scores.json"
    rows = _csv_rows(original)
    start = rows[0].index("Entry Fee") + 1
    row = next(row for row in rows[1:] if row and row[0].strip().isdigit())
    row[start + 1] = cell.format(name="Some Player", dk_id=row[start + 1].strip())
    copy = tmp_path / "file.csv"
    buffer = io.StringIO(newline="")
    csv.writer(buffer, lineterminator="\r\n").writerows(rows)
    copy.write_bytes(buffer.getvalue().encode("utf-8"))
    if code is not None:
        with pytest.raises(EntryRecordRefused) as caught:
            build_records(salaries, entries, copy, scores=scores)
        assert caught.value.code == code
        return
    locked = build_records(salaries, entries, copy, scores=scores)
    plain = build_records(salaries, entries, original, scores=scores)
    for one, other in zip(locked, plain, strict=True):
        one["hashes"].pop("file_sha256"), other["hashes"].pop("file_sha256")
        assert one == other
