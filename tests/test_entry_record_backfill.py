"""Session 72c, the backfill: every other committed slate with a delivered file has its build record.

Each record is the builder's bytes on the slate's committed inputs with no run folder (none was kept). Its priors come from
the one source the Session 72c card names: a dump only where it reproduces the slate's hand-pass record, otherwise
`NO_PRIOR_SOURCE` (PHI@CHI, Week 4 afternoon). MIN@NO's graded file is `final_v10`, with `final_v7` under its own stem until
Ben names the file he uploaded. Session 72's four records are pinned in `tests/test_entry_record_slates.py`.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from pathlib import Path

import pytest

from nfl_dfs.dk import parse_entries
from nfl_dfs.entry_record import build_records, record_bytes

SLATES = Path(__file__).resolve().parent.parent / "data" / "inbox" / "slates"
RECORD = "construction/entry_build_record.jsonl"
MIN, WK5 = "min-no-sd-2026-10-11", "wk5-classic-2026-10-11"
# label: slug, record, salaries, entries, graded file, the card's SHA-256 prefix, prior source (None: NO_PRIOR_SOURCE)
BACKFILL = {
    "buf-lar": ("buf-lar-sd-2026-10-12", RECORD, "input/DKSalaries.csv", "input/DKEntries.csv",
                "construction/DK_REVIEW_ENTRY_buf-lar-sd_final_v2.csv", "675d5d30", "construction/pool_scores.json"),
    "bal-atl": ("bal-atl-sd-2026-10-11", RECORD, "input/DKSalaries_176.csv", "input/DKEntries_150.csv",
                "construction/DK_REVIEW_ENTRY_bal-atl-sd_final_v6.csv", "3b14e785", "construction/pool_scores_r3.json"),
    "min-no": (MIN, RECORD, "input/DKSalaries_169.csv", "input/DKEntries_141.csv",
               "construction/DK_REVIEW_ENTRY_min-no-sd_final_v10.csv", "e5a20eeb", "construction/pool_scores_r3.json"),
    "min-no-v7": (MIN, "construction/entry_build_record.DK_REVIEW_ENTRY_min-no-sd_final_v7.jsonl", "input/DKSalaries_169.csv",
                  "input/DKEntries_141.csv", "construction/DK_REVIEW_ENTRY_min-no-sd_final_v7.csv", "11ddfc46",
                  "construction/pool_scores_r3.json"),
    "phi-chi": ("phi-chi-sd-2026-09-28", RECORD, "bdc34f2b-DKSalaries_119.csv", "5ed750e7-DKEntries_97.csv",
                "DK_REVIEW_ENTRY_phi-chi-sd-v4.csv", "967f0872", None),
    "wk4-pm": ("wk4-afternoon-2026-10-04", RECORD, "DKSalaries.csv", "DKEntries.csv",
               "DK_REVIEW_ENTRY_wk4_afternoon_FINAL.csv", "0c0e9f6b", None),
    "wk5-pm": ("wk5-afternoon-2026-10-11", RECORD, "input/DKSalaries.csv", "input/DKEntries.csv",
               "DK_REVIEW_ENTRY_wk5_afternoon_v3.csv", "ec1fb926", "construction/pool_scores.json"),
    # The template is the late-swap export the file edits in place, which holds 33 Entry IDs including Ben's free entry.
    "wk5": (WK5, RECORD, "input/DKSalaries.csv", "live/DKEntries_current_1914Z.csv", "DK_LATESWAP_wk5_classic_v10.csv",
            "4ed31af6", "construction/pool_scores.json"),
}
# Week 5 Classic's files before the late swap were built on the blank template (32 Entry IDs).
BEFORE_LATE_SWAP = {"wk5": "input/DKEntries.csv"}
PARETO = "construction.pareto_redeploy.after.prior_sum"
# (label, file, total, the hand-pass record that states the total, its key): each dump's sum over a file a hand pass read
# or wrote, two decimals.
HAND_PASS = [
    ("buf-lar", "construction/DK_REVIEW_ENTRY_buf-lar-sd_r2.csv", 3047.27, "construction/ceiling_pass_record_v2.json",
     "before.total_prior"),
    ("buf-lar", "construction/DK_REVIEW_ENTRY_buf-lar-sd_final_v2.csv", 3128.37, "construction/ceiling_pass_record_v2.json",
     "after.total_prior"),
    ("bal-atl", "construction/DK_REVIEW_ENTRY_bal-atl-sd_r3_engine.csv", 2286.27, "construction/judgment_v1_record.json",
     "before.total_prior"),
    ("bal-atl", "construction/DK_REVIEW_ENTRY_bal-atl-sd_judgment_v1.csv", 2214.92, "construction/judgment_v1_record.json",
     "after.total_prior"),
    ("min-no", "construction/DK_REVIEW_ENTRY_min-no-sd_judgment_v6.csv", 2113.62, "construction/judgment_v6_record.json",
     "after.total_prior"),
    ("min-no", "construction/DK_REVIEW_ENTRY_min-no-sd_final_v7.csv", 2113.62, "construction/pareto_v8_record.json",
     "before.prior"),
    ("wk5-pm", "DK_REVIEW_ENTRY_wk5_afternoon_v2.csv", 3003.32, "construction/portfolio_v2_final.json", PARETO),
    ("wk5-pm", "DK_REVIEW_ENTRY_wk5_afternoon_v3.csv", 3011.11, "construction/portfolio_v3_redeploy.json", PARETO),
    ("wk5", "DK_REVIEW_ENTRY_wk5_classic_v5.csv", 4134.34, "construction/portfolio_v5_redeploy.json", PARETO),
]
# A cell's exact DK ID: bare digits, `Name (ID)`, or DraftKings' late-swap `Name (ID) (LOCKED)`.
_ID = re.compile(r"(?:.*\()?([0-9]+)\)?(?:\s*\(LOCKED\))?")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _cells(path: Path) -> dict[str, list[str]]:
    """Each Entry ID's roster as the file's own cells give it, read without the builder."""

    rows = list(csv.reader(io.StringIO(path.read_bytes().decode("utf-8-sig"), newline="")))
    start = rows[0].index("Entry Fee") + 1
    stop = rows[0].index("", start)
    return {row[0].strip(): [_ID.fullmatch(cell.strip()).group(1) for cell in row[start:stop]]
            for row in rows[1:] if row and row[0].strip().isdigit()}


def _total(label: str, file: str, source: str | None = None) -> float:
    slug, _record, salaries, entries, _file, _prefix, scores = BACKFILL[label]
    base = SLATES / slug
    rows = build_records(base / salaries, base / BEFORE_LATE_SWAP.get(label, entries), base / file,
                         scores=base / (source or scores))
    return sum(row["prior"]["points"] for row in rows)


@pytest.mark.parametrize("label", list(BACKFILL), ids=list(BACKFILL))
def test_every_other_committed_slate_record_equals_its_source(label):
    slug, record, salaries, entries, file, prefix, source = BACKFILL[label]
    base = SLATES / slug
    assert _sha(base / file).startswith(prefix), f"{label}: {file} is {_sha(base / file)[:8]}, the card's file is {prefix}"
    rows = build_records(base / salaries, base / entries, base / file, **({"scores": base / source} if source else {}))
    assert (base / record).read_bytes() == record_bytes(rows)
    assert [row["entry_id"] for row in rows] == [entry.entry_id for entry in parse_entries(base / entries).authorizations]
    cells = _cells(base / file)
    dump = json.loads((base / source).read_bytes()) if source else None
    for row in rows:
        assert row["roster"] == cells[row["entry_id"]]
        assert row["run"] == {"run_id": None, "method": None, "policy_sha256": None, "thesis": None,
                              "reasons": dict.fromkeys(("run_id", "method", "policy_sha256", "thesis"),
                                                       "RUN_FOLDER_NOT_SUPPLIED")}
        assert row["stack_game"]["market"] is None and row["stack_game"]["market_reason"] == "RUN_FOLDER_NOT_SUPPLIED"
        prior = row["prior"]
        if dump is None:
            assert (prior["points"], prior["source"], prior["reason"], row["rank"],
                    row["hashes"]["prior_source_sha256"]) == (None, None, "NO_PRIOR_SOURCE", None, None)
            continue
        assert (prior["source"], prior["score_version"], prior["reason"]) == (
            "POOL_SCORES_SUM", dump["score_version"], None)
        assert prior["points"] == sum(float(dump["by_dk_id"][dk_id]) for dk_id in cells[row["entry_id"]])
        assert row["rank"] == 1 + sum(other["prior"]["points"] > prior["points"] for other in rows)
        assert row["hashes"]["prior_source_sha256"] == _sha(base / source)


def test_the_backfill_sources_reproduce_the_hand_pass_records():
    for label, file, total, record, key in HAND_PASS:
        stated = json.loads((SLATES / BACKFILL[label][0] / record).read_bytes())
        for part in key.split("."):
            stated = stated[part]
        summed = _total(label, file)
        assert round(summed, 2) == total and abs(stated - summed) < 0.005, f"{label} {file}: {summed} against {stated}"
    # Pins, the builder's own figures rather than a hand pass. BAL@ATL's r2 dump is not the one its judgment pass read.
    # MIN@NO's two later passes (Ben's 16:41Z and 16:44Z asks; the changelog's +2.52 and +0.2) score on the same r3 dump.
    assert round(_total("bal-atl", "construction/DK_REVIEW_ENTRY_bal-atl-sd_r3_engine.csv",
                        "construction/pool_scores_r2.json"), 2) == 2420.31
    assert [round(_total("min-no", f"construction/DK_REVIEW_ENTRY_min-no-sd_final_v{n}.csv"), 2) for n in (7, 9, 10)] == [
        2113.62, 2116.14, 2116.36]
    # Week 5 Classic's graded file against its own late-swap record: 32 of 32 rows agree. The one row the engine never
    # built is Ben's free entry, and it is recorded with its prior and rank.
    rows = {row["entry_id"]: row for row in map(json.loads, (SLATES / WK5 / RECORD).read_bytes().splitlines())}
    lineups = json.loads((SLATES / WK5 / "construction/portfolio_v10_lateswap.json").read_bytes())["lineups"]
    assert set(rows) - {lineup["entry_id"] for lineup in lineups} == {"5291960735"} and len(lineups) == 32
    for lineup in lineups:
        row = rows[lineup["entry_id"]]
        assert set(row["roster"]) == set(lineup["roster"]) and abs(row["prior"]["points"] - lineup["prior_points"]) < 0.005
    assert rows["5291960735"]["prior"]["points"] is not None and rows["5291960735"]["rank"] == 33


def test_the_slates_with_no_committed_delivered_file_have_no_record():
    for slug, template in (("det-buf-2026-09-17", "53fe7f5a-DKEntries_74.csv"),
                           ("wk3-classic-2026-09-27", "de631c27-DKEntries_95.csv")):
        folder = SLATES / slug
        assert (folder / template).is_file()  # the folder is there, so an empty search below is a finding
        for pattern in ("DK_REVIEW_ENTRY_*", "DK_LATESWAP_*", "entry_build_record*"):
            assert not list(folder.rglob(pattern)), f"{slug}: {pattern}"
