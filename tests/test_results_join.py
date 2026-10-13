"""Session 73: the results join (`nfl_results_join_v1`, `nfl_entry_results_v1`).

Session 69's entry history joined to Session 72's build records on exact Entry ID: each Entry ID's class (a locked blank
with or without a record among them), the within-slate rank check of prior points against realized DraftKings points,
and per-slate results written once beside each record with place, field size, points and percentile only. History
fixtures are synthetic bytes built with Session 69's builders and written with `write_bytes` (Ben's real export carries
account winnings and never enters the repository). The real committed records and templates are read, never written:
every case on the real slates tree calls the pure `build_join`.

The card's four figures (-0.03, +0.38, +0.63, +0.06) need the real export (operator item O13). The cases here pin the
pairing, the exclusions and the arithmetic on the real records with a permutation whose rho is known in closed form.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
from fractions import Fraction
from pathlib import Path

import pytest

from nfl_dfs import cli, entry_history, player_grading
from nfl_dfs import results_join as rj
from nfl_dfs.contracts import GateClass
from nfl_dfs.dk import parse_entry_bytes
from nfl_dfs.gate_registry import load_gate_registry
from nfl_dfs.hashing import canonical_json_bytes, sha256_bytes
from tests.test_entry_history import _history, _row
from tests.test_gate_registry import scanned_codes

REPO = Path(__file__).resolve().parents[1]
SLATES = REPO / "data" / "inbox" / "slates"
ZERO_SHA = "0" * 64
SHOWDOWN, CLASSIC = "Showdown Captain Mode", "Classic"
# Distinctive money, so a byte test cannot pass or fail by coincidence.
FEE, PRIZE, WON, TICKET = "$7.77", "$9,876.54", "$1,234.56", "$43.21"
MONEY_FRAGMENTS = (b"987654", b"123456", b"4321", b"777")
REAL_ROW = json.loads((SLATES / "det-car-sd-2026-10-04" / "construction" / "entry_build_record.jsonl")
                      .read_bytes().splitlines()[0])


# ------------------------------------------------------------------------------------------- builders


_REAL = object()


def _record_row(entry_id: str, contest_id: str, points: float | None, *, mode: str = "SHOWDOWN",
                reason: str | None = None, roster: object = _REAL) -> dict:
    prior = dict(REAL_ROW["prior"], points=points, reason=None if points is not None else reason or "NO_PRIOR_SOURCE")
    return dict(REAL_ROW, entry_id=entry_id, contest_id=contest_id, mode=mode, prior=prior,
                roster=REAL_ROW["roster"] if roster is _REAL else roster)


def _record_bytes(rows: list[dict]) -> bytes:
    return b"".join(canonical_json_bytes(row) + b"\n" for row in rows)


def _slates(tmp_path: Path, folders: dict[str, list[dict]], extra: dict[str, dict[str, bytes]] | None = None) -> Path:
    root = tmp_path / "slates"
    for name, rows in folders.items():
        construction = root / name / "construction"
        construction.mkdir(parents=True, exist_ok=True)
        (construction / rj.RECORD_NAME).write_bytes(_record_bytes(rows))
    for name, files in (extra or {}).items():
        construction = root / name / "construction"
        construction.mkdir(parents=True, exist_ok=True)
        for file_name, data in files.items():
            (construction / file_name).write_bytes(data)
    return root


def _entry(entry_id: str, contest: str, points: str, place: int, *, game_type: str = SHOWDOWN,
           date: str = "2026-10-04 20:20:00", entries: int = 1000, fee: str = FEE) -> list[str]:
    paid = fee != "$0.00"
    return _row(Game_Type=game_type, Entry_Key=entry_id, Entry=f"NFL synthetic {entry_id}", Contest_Key=contest,
                Contest_Date_EST=date, Place=str(place), Points=points,
                Winnings_Non_Ticket=WON if paid else "$0.00", Winnings_Ticket=TICKET if paid else "$0.00",
                Contest_Entries=str(entries), Entry_Fee=fee, Prize_Pool=PRIZE if paid else "$0.00",
                Places_Paid="200" if paid else "0")


def _parse(*rows: list[str]) -> entry_history.EntryHistory:
    return entry_history.parse_entry_history(_history(*rows))


def _intake(tmp_path: Path, raw: bytes, root: Path | None = None) -> tuple[Path, str]:
    source = tmp_path / "downloads" / f"{sha256_bytes(raw)[:12]}.csv"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(raw)
    root = root or tmp_path / "results"
    outcome = entry_history.run_intake(source, root)
    assert outcome.status in ("COMPLETE", "ALREADY_PRESENT"), outcome.problems
    return root, outcome.source_sha256


def _by_entry(report: dict) -> dict[str, dict]:
    return {item["entry_id"]: item for item in report["entries"]}


def _check(report: dict, slate: str) -> dict:
    [found] = [item for item in report["rank_check"]["slates"] if item["slate"] == slate]
    return found


# Two small synthetic slates: A (Showdown, four paid rows and a free one) and B (Classic, three rows).
A_RECORD = [_record_row(f"91000000{i}", "300000001" if i < 5 else "300000002", 10.0 * i) for i in range(1, 6)]
B_RECORD = [_record_row(f"92000000{i}", "300000003", 20.0 + i, mode="CLASSIC") for i in range(1, 4)]
A_HISTORY = [
    _entry("910000001", "300000001", "40", 30), _entry("910000002", "300000001", "30", 60),
    _entry("910000003", "300000001", "60", 10), _entry("910000004", "300000001", "50", 20),
    _entry("910000005", "300000002", "90", 2, entries=50, fee="$0.00"),
]
B_HISTORY = [_entry(f"92000000{i}", "300000003", str(100 + i), 400 - i, game_type=CLASSIC,
                    date="2026-10-04 13:00:00", entries=500) for i in range(1, 4)]


def _ab(tmp_path: Path) -> Path:
    return _slates(tmp_path, {"a-sd": A_RECORD, "b-classic": B_RECORD})


# ------------------------------------------------------------------------------------ acceptance


REVIEW_SLATES = {
    "det-car": "det-car-sd-2026-10-04",
    "atl-no": "atl-no-sd-2026-10-05",
    "tb-dal": "tb-dal-sd-2026-10-08",
    "wk4": "wk4-classic-2026-10-04",
}


def _swapped_history(slate) -> tuple[list[list[str]], Fraction]:
    """Realized points that swap each adjacent pair of the prior order: rho is 1 - 6*sum(d^2)/(n(n^2-1)) exactly."""

    rows = sorted(slate.rows, key=lambda row: row["prior"]["points"])
    n = len(rows)
    swapped = [k ^ 1 if (k ^ 1) < n else k for k in range(n)]
    history = []
    for k, row in enumerate(rows):
        game_type = SHOWDOWN if row["mode"] == "SHOWDOWN" else CLASSIC
        history.append(_entry(row["entry_id"], row["contest_id"], str(swapped[k] + 1), n - swapped[k],
                              game_type=game_type))
    squares = sum((swapped[k] - k) ** 2 for k in range(n))
    return history, 1 - Fraction(6 * squares, n * (n * n - 1))


@pytest.mark.parametrize("label", list(REVIEW_SLATES), ids=list(REVIEW_SLATES))
def test_the_rank_check_on_the_four_review_slates(label):
    """The pairing, exclusions and arithmetic on the real records; the review's own figures wait on O13's export."""

    records = rj.load_records(SLATES)
    [slate] = [item for item in records.slates if item.slate == REVIEW_SLATES[label]]
    history, expected = _swapped_history(slate)
    report, results = rj.build_join(_parse(*history), records, source_sha256=ZERO_SHA)
    check = _check(report, slate.slate)
    assert check["all"] == {"n": len(slate.rows), "rho": round(float(expected), 6), "note": None}
    assert check["paid"] == check["all"] and check["excluded"] == {}
    assert set(results) == {slate.slate}
    assert [item["class"] for item in results[slate.slate]["entries"]] == ["JOINED"] * len(slate.rows)


def test_the_pooled_figure_is_the_unweighted_mean_of_the_four_review_slates():
    records = rj.load_records(SLATES)
    history, expected = [], []
    for name in REVIEW_SLATES.values():
        [slate] = [item for item in records.slates if item.slate == name]
        rows, rho = _swapped_history(slate)
        history += rows
        expected.append(round(float(rho), 6))
    report, results = rj.build_join(_parse(*history), records, source_sha256=ZERO_SHA)
    pooled = report["rank_check"]["pooled"]["all"]
    assert pooled == {"slates": 4, "rows": 28 + 36 + 28 + 39, "mean_rho": round(sum(expected) / 4, 6)}
    assert len(results) == 4


def test_det_buf_blank_entry_ids_are_locked_blank_no_record():
    template = parse_entry_bytes((SLATES / "det-buf-2026-09-17" / "53fe7f5a-DKEntries_74.csv").read_bytes())
    entries = template.authorizations
    assert len(entries) == 13 and len({entry.contest_id for entry in entries}) == 6
    game_type = SHOWDOWN if template.mode.value == "SHOWDOWN" else CLASSIC
    rows = [_entry(entry.entry_id, entry.contest_id, "110.95" if index == 12 else "0", 5 if index == 12 else 400,
                   game_type=game_type, date="2026-09-17 20:15:00", entries=500)
            for index, entry in enumerate(entries)]
    records = rj.load_records(SLATES)
    report, results = rj.build_join(_parse(*rows), records, source_sha256=ZERO_SHA)
    found = _by_entry(report)
    blanks = [found[entry.entry_id] for entry in entries[:12]]
    assert {item["class"] for item in blanks} == {"LOCKED_BLANK_NO_RECORD"}
    # No record holds any of DET@BUF's six contests: its folder has the template and no delivered file.
    assert {(item["reason"], item["date"], item["game_type"], item["slate"]) for item in blanks} == {
        ("CONTEST_IN_NO_RECORD", "2026-09-17", game_type, None)}
    scorer = found[entries[12].entry_id]
    assert (scorer["class"], scorer["reason"], scorer["blank"]) == ("ENTERED_NO_RECORD", "CONTEST_IN_NO_RECORD", False)
    assert report["class_counts"]["LOCKED_BLANK_NO_RECORD"] == 12
    assert [item["entry_id"] for item in rj.headline(report)["blanks"]] == [entry.entry_id for entry in entries[:12]]
    # None of the recorded Entry IDs is in this export, so no slate's results file is written. Counted from the tree,
    # never pinned, so the next slate's record does not move this test; the alternate (MIN@NO `final_v7`) never joins.
    assert results == {}
    assert report["class_counts"]["RECORDED_NOT_IN_HISTORY"] == sum(len(slate.rows) for slate in records.slates)
    assert "min-no-sd-2026-10-11/construction/entry_build_record.DK_REVIEW_ENTRY_min-no-sd_final_v7.jsonl" in (
        records.alternates)


def test_the_join_is_deterministic(tmp_path):
    raw = _history(*A_HISTORY, *B_HISTORY)
    digests = []
    for name in ("one", "two"):
        base = tmp_path / name
        slates = _ab(base)
        root, sha = _intake(base, raw)
        outcome = rj.run_results_join(sha, root, slates)
        assert outcome.status == "COMPLETE" and outcome.exit_code == 0
        files = [Path(outcome.files["report"]["path"])] + [
            Path(state["path"]) for _, state in sorted(outcome.files["slates"].items())]
        digests.append([hashlib.sha256(path.read_bytes()).hexdigest() for path in files])
        assert [outcome.files["report"]["sha256"]] + [state["sha256"] for _, state in sorted(
            outcome.files["slates"].items())] == digests[-1]
        again = rj.run_results_join(sha, root, slates)
        assert again.status == "ALREADY_PRESENT" and again.exit_code == 0
    assert digests[0] == digests[1] and len(digests[0]) == 3


def _repo_state():
    spec = importlib.util.spec_from_file_location("repo_state_s73", REPO / "scripts" / "repo_state.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _digest_state(**extra) -> dict:
    return {
        "git": {"branch": "claude/x", "head": "abc1234", "dirty_paths": 0, "untracked_paths": 0,
                "behind_origin_main": "0", "origin_main_fetch": {"ok": True}, "recent_commits": []},
        "ready_chunks": [], "in_progress_chunks": [], "changelog_headings": [],
        "claims": {"active": [], "stale": []}, "verification": {"known": False},
        "calibration": {"slates_graded": 0, "slates_recorded": 0, "model_status": "PRIOR_ONLY",
                        "release_decision": "DO_NOT_UPLOAD"},
        "ben_flags": [], **extra,
    }


def test_repo_state_reports_entry_graded_slates(tmp_path, monkeypatch):
    repo_state = _repo_state()
    monkeypatch.setattr(repo_state, "SLATES_DIR", tmp_path)
    (tmp_path / "a-sd" / "construction").mkdir(parents=True)
    (tmp_path / "b-sd" / "construction").mkdir(parents=True)
    none = repo_state.entry_grading()
    assert none["slates_graded"] == 0
    assert "entry grading: 0 slates with results joined on Entry ID" in repo_state.digest(
        _digest_state(entry_grading=none))  # the count shows at zero too
    (tmp_path / "a-sd" / "construction" / rj.RESULTS_NAME).write_bytes(b"{}\n")
    (tmp_path / "b-sd" / "construction" / "entry_build_record.jsonl").write_bytes(b"{}\n")
    graded = repo_state.entry_grading()
    assert graded["slates_graded"] == 1 and graded["results_file"] == rj.RESULTS_NAME
    text = repo_state.digest(_digest_state(entry_grading=graded))
    assert "entry grading: 1 slates with results joined on Entry ID" in text
    assert "calibration: 0/0 slates graded" in text  # P0's player-week line is unchanged and separate
    assert "entry grading" not in repo_state.digest(_digest_state())  # an old-shape state still renders
    monkeypatch.setattr(repo_state, "git_state", lambda now=None: _digest_state()["git"])
    state = repo_state.build_state()
    assert state["entry_grading"]["slates_graded"] == 1
    assert "entry grading: 1 slates" in repo_state.digest(state)


# ------------------------------------------------------------------------------------- arithmetic


def test_a_realized_tie_takes_the_average_rank(tmp_path):
    rows = [_record_row(f"93000000{i}", "300000009", float(i)) for i in range(1, 5)]
    history = [_entry(f"93000000{i}", "300000009", points, 10 * i)
               for i, points in zip(range(1, 5), ("10", "20", "20", "40"))]
    report, _ = rj.build_join(_parse(*history), rj.load_records(_slates(tmp_path, {"t-sd": rows})),
                              source_sha256=ZERO_SHA)
    # Ranks (1, 2, 3, 4) against (1, 2.5, 2.5, 4): 4.5 / sqrt(5 * 4.5) = sqrt(0.9).
    assert _check(report, "t-sd")["all"]["rho"] == round(math.sqrt(0.9), 6) == 0.948683


def test_too_few_rows_and_zero_variance_are_named(tmp_path):
    few = [_record_row(f"94000000{i}", "300000010", float(i)) for i in range(1, 3)]
    flat = [_record_row(f"95000000{i}", "300000011", float(i)) for i in range(1, 4)]
    records = rj.load_records(_slates(tmp_path, {"few-sd": few, "flat-sd": flat}))
    history = [_entry(row["entry_id"], "300000010", "50", 10) for row in few] + [
        _entry(row["entry_id"], "300000011", "70", 10, date="2026-10-05 20:20:00") for row in flat]
    report, _ = rj.build_join(_parse(*history), records, source_sha256=ZERO_SHA)
    assert _check(report, "few-sd")["all"] == {"n": 2, "rho": None, "note": "FEWER_THAN_3"}
    assert _check(report, "flat-sd")["all"] == {"n": 3, "rho": None, "note": "ZERO_VARIANCE"}
    assert report["rank_check"]["pooled"]["all"] == {"slates": 0, "rows": 0, "mean_rho": None}


def test_paid_rows_are_a_second_population_and_the_pooled_mean_skips_undefined_slates(tmp_path):
    records = rj.load_records(_ab(tmp_path))
    report, _ = rj.build_join(_parse(*A_HISTORY, *B_HISTORY), records, source_sha256=ZERO_SHA)
    a = _check(report, "a-sd")
    expected_all = player_grading.spearman([10, 20, 30, 40, 50], [40, 30, 60, 50, 90])[0]
    expected_paid = player_grading.spearman([10, 20, 30, 40], [40, 30, 60, 50])[0]
    assert a["all"] == {"n": 5, "rho": expected_all, "note": None} and expected_all == 0.8
    assert a["paid"] == {"n": 4, "rho": expected_paid, "note": None} and expected_paid == 0.6
    b = _check(report, "b-classic")
    assert b["all"]["rho"] == 1.0
    pooled = report["rank_check"]["pooled"]
    assert pooled["all"] == {"slates": 2, "rows": 8, "mean_rho": round((0.8 + 1.0) / 2, 6)}
    assert pooled["paid"] == {"slates": 2, "rows": 7, "mean_rho": round((0.6 + 1.0) / 2, 6)}


# ---------------------------------------------------------------------------- missing, bad, disagreeing


def test_every_class_and_reason_is_named(tmp_path):
    record = A_RECORD + [
        _record_row("910000006", "300000001", 70.0),  # not in the export
        _record_row("910000007", "300000001", 80.0),  # a locked blank with a file
        _record_row("910000008", "300000001", 90.0),  # its contest disagrees
        _record_row("910000009", "300000098", 99.0),  # its game type disagrees (its own contest agrees)
        _record_row("910000010", "300000096", 98.0),  # a Showdown game type that is not Captain Mode
        _record_row("910000011", "300000001", 97.0),  # a blank whose contest disagrees
    ]
    unfilled = _record_row("960000001", "300000020", None, reason="UNFILLED", roster=None)
    slates = _slates(tmp_path, {"a-sd": record, "u-sd": [unfilled]})
    history = [*A_HISTORY,
               _entry("910000007", "300000001", "0", 990),
               _entry("910000008", "300000099", "55", 500),
               _entry("910000009", "300000098", "56", 499, game_type=CLASSIC),
               _entry("910000010", "300000096", "57", 498, game_type="Showdown Tiers"),
               _entry("910000011", "300000095", "0", 497),
               _entry("960000001", "300000020", "0", 77, date="2026-10-06 20:20:00"),
               _entry("910000077", "300000001", "61", 9),  # in A's own contest, no record row
               _entry("910000088", "300000077", "44", 5),  # A's date and game type, a contest no record holds
               _entry("990000001", "300000097", "0", 600, date="2026-09-17 20:15:00"),  # a blank, no record at all
               _entry("990000002", "300000097", "88", 3, date="2026-09-17 20:15:00")]
    report, results = rj.build_join(_parse(*history), rj.load_records(slates), source_sha256=ZERO_SHA)
    found = _by_entry(report)
    assert {key: (found[key]["class"], found[key]["reason"], found[key]["slate"]) for key in (
        "910000006", "910000007", "910000008", "910000009", "910000010", "910000011", "960000001", "910000077",
        "910000088", "990000001", "990000002")} == {
        "910000006": ("RECORDED_NOT_IN_HISTORY", "NOT_IN_EXPORT", "a-sd"),
        "910000007": ("LOCKED_BLANK_WITH_FILE", "RECORD_ROW_FILLED", "a-sd"),
        "910000008": ("ROW_DISAGREES", "CONTEST", "a-sd"),
        "910000009": ("ROW_DISAGREES", "GAME_TYPE", "a-sd"),
        "910000010": ("ROW_DISAGREES", "GAME_TYPE", "a-sd"),
        "910000011": ("ROW_DISAGREES", "CONTEST", "a-sd"),
        "960000001": ("LOCKED_BLANK_WITH_FILE", "RECORD_ROW_UNFILLED", "u-sd"),
        "910000077": ("ENTERED_NO_RECORD", "RECORD_LACKS_ENTRY_ID", "a-sd"),
        "910000088": ("ENTERED_NO_RECORD", "CONTEST_IN_NO_RECORD", None),
        "990000001": ("LOCKED_BLANK_NO_RECORD", "CONTEST_IN_NO_RECORD", None),
        "990000002": ("ENTERED_NO_RECORD", "CONTEST_IN_NO_RECORD", None),
    }
    assert found["910000001"]["class"] == "JOINED" and found["910000001"]["slate"] == "a-sd"
    # The export's own zero stays visible whatever the class, so a blank on a disagreeing row is never hidden.
    assert [item["entry_id"] for item in rj.headline(report)["blanks"]] == [
        "910000007", "910000011", "960000001", "990000001"]
    assert found["910000006"]["blank"] is None and found["910000008"]["blank"] is False
    a = _check(report, "a-sd")
    assert a["all"]["n"] == 5
    assert a["excluded"] == {"LOCKED_BLANK_WITH_FILE": 1, "RECORDED_NOT_IN_HISTORY": 1, "ROW_DISAGREES": 4}
    # The results file names every recorded Entry ID; only rows the export binds carry numbers.
    lines = {item["entry_id"]: item for item in results["a-sd"]["entries"]}
    assert lines["910000006"]["place"] is None and lines["910000008"]["points_hundredths"] is None
    assert lines["910000007"] == {"entry_id": "910000007", "class": "LOCKED_BLANK_WITH_FILE", "place": 990,
                                  "contest_entries": 1000, "points_hundredths": 0, "percentile": "99.0000"}
    assert lines["910000003"]["percentile"] == "1.0000" and lines["910000003"]["points_hundredths"] == 6000


def test_a_slate_with_no_prior_source_is_excluded_by_name_and_still_written(tmp_path):
    rows = [_record_row(f"97000000{i}", "300000030", None) for i in range(1, 5)]
    slates = _slates(tmp_path, {"n-sd": rows})
    raw = _history(*[_entry(row["entry_id"], "300000030", str(10 + i), 10 + i) for i, row in enumerate(rows)])
    root, sha = _intake(tmp_path, raw)
    outcome = rj.run_results_join(sha, root, slates)
    report = json.loads(Path(outcome.files["report"]["path"]).read_bytes())
    check = _check(report, "n-sd")
    assert check["all"] == {"n": 0, "rho": None, "note": "FEWER_THAN_3"}
    assert check["excluded"] == {"NO_PRIOR_SOURCE": 4}
    assert outcome.files["slates"]["n-sd"]["state"] == "WRITTEN"


def test_a_non_nfl_row_never_joins_and_alternate_records_are_listed_not_joined(tmp_path):
    alternate = _record_bytes([_record_row("980000001", "300000040", 5.0)])
    slates = _slates(tmp_path, {"a-sd": A_RECORD}, extra={"a-sd": {"entry_build_record.DK_x_v7.jsonl": alternate}})
    mlb = _row(Sport="MLB", Entry_Key="910000001", Contest_Key="300000050", Contest_Date_EST="2026-07-04 19:05:00")
    history = [mlb, *A_HISTORY[1:], _entry("980000001", "300000040", "12", 4, date="2026-10-07 20:20:00")]
    records = rj.load_records(slates)
    assert records.alternates == ("a-sd/construction/entry_build_record.DK_x_v7.jsonl",)
    report, _ = rj.build_join(_parse(*history), records, source_sha256=ZERO_SHA)
    found = _by_entry(report)
    assert (found["910000001"]["class"], found["910000001"]["reason"]) == ("RECORDED_NOT_IN_HISTORY", "NOT_IN_EXPORT")
    assert found["980000001"]["class"] == "ENTERED_NO_RECORD"
    assert report["alternate_records"] == ["a-sd/construction/entry_build_record.DK_x_v7.jsonl"]
    assert report["non_nfl_rows_ignored"] == 1


def _good() -> list[dict]:
    return [_record_row("990000101", "300000060", 1.0), _record_row("990000102", "300000060", 2.0)]


BAD_RECORDS = {
    "not-json": lambda: _record_bytes(_good()) + b"{not json\n",
    "missing-key": lambda: _record_bytes([{key: value for key, value in _good()[0].items() if key != "contest_id"}]),
    "schema": lambda: _record_bytes([dict(_good()[0], schema_version="nfl_entry_build_record_v2")]),
    "nan-prior": lambda: _record_bytes(_good()).replace(b'"points":1.0', b'"points":NaN'),
    "inf-prior": lambda: _record_bytes(_good()).replace(b'"points":1.0', b'"points":1e999'),  # json reads inf
    "bool-prior": lambda: _record_bytes([dict(_good()[0], prior=dict(_good()[0]["prior"], points=True))]),
    "entry-id": lambda: _record_bytes([dict(_good()[0], entry_id="0123")]),
    "unterminated": lambda: _record_bytes(_good())[:-1],
    "empty": lambda: b"",
    "duplicate": lambda: _record_bytes(_good() + _good()[:1]),
}


@pytest.mark.parametrize("case", list(BAD_RECORDS), ids=list(BAD_RECORDS))
def test_a_bad_record_is_refused_by_name(tmp_path, case):
    root = tmp_path / "slates" / "bad-sd" / "construction"
    root.mkdir(parents=True)
    (root / rj.RECORD_NAME).write_bytes(BAD_RECORDS[case]())
    with pytest.raises(rj.ResultsJoinRefused) as caught:
        rj.load_records(tmp_path / "slates")
    assert caught.value.code == "RESULTS_JOIN_RECORD_INVALID"
    assert caught.value.detail.startswith("bad-sd/construction/entry_build_record.jsonl:")


def test_an_entry_id_in_two_slates_records_is_refused(tmp_path):
    slates = _slates(tmp_path, {"a-sd": _good(), "b-sd": _good()[:1]})
    with pytest.raises(rj.ResultsJoinRefused) as caught:
        rj.load_records(slates)
    assert (caught.value.code, caught.value.detail) == (
        "RESULTS_JOIN_RECORD_INVALID", "entry_id=990000101:slates=a-sd,b-sd")


def test_input_refusals_write_nothing(tmp_path):
    slates = _ab(tmp_path)
    raw = _history(*A_HISTORY)
    root, sha = _intake(tmp_path, raw)
    bad = rj.run_results_join("ABC", root, slates)
    assert (bad.status, bad.problems, bad.exit_code) == (
        "REFUSED", ("RESULTS_JOIN_INPUT_INVALID:field=source_sha256",), 2)
    absent = rj.run_results_join("f" * 64, root, slates)
    assert absent.problems == ("RESULTS_JOIN_SNAPSHOT_INVALID:reason=absent",)
    # One changed snapshot byte withholds every artifact (tests.md's mutation rule for a writer).
    snapshot = root / "inbox" / f"{sha}.csv"
    snapshot.write_bytes(raw.replace(b"NFL synthetic", b"NFL Synthetic"))
    changed = rj.run_results_join(sha, root, slates)
    assert changed.problems == ("RESULTS_JOIN_SNAPSHOT_INVALID:reason=hash",)
    no_slates = rj.run_results_join(sha, root, tmp_path / "nowhere")
    assert no_slates.problems == ("RESULTS_JOIN_INPUT_INVALID:field=slates_root",)
    for outcome in (bad, absent, changed, no_slates):
        assert outcome.files["report"]["state"] == "NOT_ATTEMPTED" and outcome.files["slates"] == {}
    assert not (root / "reports").exists()
    assert not list(slates.glob(f"*/construction/{rj.RESULTS_NAME}"))


def test_a_parser_refusal_passes_through_by_its_own_code(tmp_path):
    raw = _history(*A_HISTORY, A_HISTORY[0])  # a duplicate Entry ID: Session 69's own refusal
    sha = sha256_bytes(raw)
    (tmp_path / "results" / "inbox").mkdir(parents=True)
    (tmp_path / "results" / "inbox" / f"{sha}.csv").write_bytes(raw)
    outcome = rj.run_results_join(sha, tmp_path / "results", _ab(tmp_path))
    assert outcome.status == "REFUSED" and outcome.problems[0].startswith("ENTRY_HISTORY_ENTRY_KEY_DUPLICATE")
    assert not (tmp_path / "results" / "reports").exists()


def test_a_bad_record_refuses_the_run_by_name(tmp_path):
    slates = _slates(tmp_path, {"a-sd": A_RECORD})
    (slates / "a-sd" / "construction" / rj.RECORD_NAME).write_bytes(b"{}\n")
    root, sha = _intake(tmp_path, _history(*A_HISTORY))
    outcome = rj.run_results_join(sha, root, slates)
    assert outcome.status == "REFUSED" and outcome.problems[0].startswith("RESULTS_JOIN_RECORD_INVALID:a-sd/")


# ------------------------------------------------------------------------------------------ write-once


def test_a_later_export_confirms_or_names_a_difference_slate_by_slate(tmp_path):
    slates = _ab(tmp_path)
    first_root, first = _intake(tmp_path, _history(*A_HISTORY))
    written = rj.run_results_join(first, first_root, slates)
    assert written.files["slates"]["a-sd"]["state"] == "WRITTEN"
    assert written.files["slates"]["b-classic"]["state"] == "NOT_IN_EXPORT"
    a_file = slates / "a-sd" / "construction" / rj.RESULTS_NAME
    a_bytes = a_file.read_bytes()
    assert json.loads(a_bytes)["source_sha256"] == first

    # Another export with the same results for A (and B now present): A is confirmed, untouched; B is written.
    second_root, second = _intake(tmp_path, _history(*A_HISTORY, *B_HISTORY), tmp_path / "results2")
    confirmed = rj.run_results_join(second, second_root, slates)
    assert confirmed.status == "COMPLETE" and confirmed.exit_code == 0
    assert confirmed.files["slates"]["a-sd"]["state"] == "CONFIRMED_BY_EXPORT"
    assert confirmed.files["slates"]["b-classic"]["state"] == "WRITTEN"
    assert a_file.read_bytes() == a_bytes

    # A third export disagrees about one A entry: that slate alone is refused, and nothing is overwritten.
    changed = [_entry("910000001", "300000001", "41", 29)] + A_HISTORY[1:]
    third_root, third = _intake(tmp_path, _history(*changed, *B_HISTORY), tmp_path / "results3")
    differ = rj.run_results_join(third, third_root, slates)
    assert differ.status == "REFUSED" and differ.exit_code == 2
    assert differ.problems == ("RESULTS_JOIN_RESULTS_DIFFER:file=a-sd",)
    assert differ.files["slates"]["a-sd"]["state"] == "REFUSED" and differ.files["slates"]["a-sd"]["recovery"]
    assert differ.files["slates"]["b-classic"]["state"] == "CONFIRMED_BY_EXPORT"
    assert differ.files["report"]["state"] == "WRITTEN"
    assert a_file.read_bytes() == a_bytes


def test_a_new_record_gets_a_new_report_and_never_refuses_the_rerun(tmp_path):
    slates = _slates(tmp_path, {"a-sd": A_RECORD})
    root, sha = _intake(tmp_path, _history(*A_HISTORY, *B_HISTORY))
    first = rj.run_results_join(sha, root, slates)
    # A later slate's record is committed; the same export is joined again.
    _slates(tmp_path, {"b-classic": B_RECORD})
    second = rj.run_results_join(sha, root, slates)
    assert second.status == "COMPLETE" and second.exit_code == 0 and second.problems == ()
    assert second.files["report"]["state"] == "WRITTEN"
    assert Path(first.files["report"]["path"]).is_file() and first.files["report"]["path"] != second.files["report"][
        "path"]
    assert second.files["slates"]["a-sd"]["state"] == "ALREADY_PRESENT"
    assert second.files["slates"]["b-classic"]["state"] == "WRITTEN"
    digest = json.loads(Path(second.files["report"]["path"]).read_bytes())["records_digest"]
    assert digest == rj.records_digest(rj.load_records(slates))
    assert Path(second.files["report"]["path"]).name == rj.report_name(digest) == f"results_join.records-{digest[:16]}.w1.json"


def test_a_hand_edited_results_file_is_never_confirmed(tmp_path):
    slates = _ab(tmp_path)
    root, sha = _intake(tmp_path, _history(*A_HISTORY))
    rj.run_results_join(sha, root, slates)
    target = slates / "a-sd" / "construction" / rj.RESULTS_NAME
    edited = dict(json.loads(target.read_bytes()), note="added by hand", source_sha256="f" * 64)
    target.write_bytes(canonical_json_bytes(edited) + b"\n")
    other_root, other = _intake(tmp_path, _history(*A_HISTORY, *B_HISTORY), tmp_path / "results2")
    outcome = rj.run_results_join(other, other_root, slates)
    assert outcome.files["slates"]["a-sd"]["state"] == "REFUSED"
    assert outcome.problems == ("RESULTS_JOIN_ARTIFACT_CONFLICT:file=a-sd",)


def test_each_record_mode_maps_to_a_registered_engine_game_type():
    from nfl_dfs.results_report import load_results_metrics

    assert set(rj.GAME_TYPES.values()) == set(load_results_metrics().engine_game_types)


def test_another_file_at_a_results_name_is_never_overwritten(tmp_path):
    slates = _ab(tmp_path)
    target = slates / "a-sd" / "construction" / rj.RESULTS_NAME
    target.write_bytes(b"not json\n")
    (slates / "b-classic" / "construction" / rj.RESULTS_NAME).write_bytes(b'{"schema_version":"other"}\n')
    root, sha = _intake(tmp_path, _history(*A_HISTORY, *B_HISTORY))
    outcome = rj.run_results_join(sha, root, slates)
    assert outcome.problems == ("RESULTS_JOIN_ARTIFACT_CONFLICT:file=a-sd",
                                "RESULTS_JOIN_ARTIFACT_CONFLICT:file=b-classic")
    assert target.read_bytes() == b"not json\n" and outcome.exit_code == 2


def test_a_write_failure_is_named_by_its_exception_class(tmp_path, monkeypatch):
    slates = _ab(tmp_path)
    root, sha = _intake(tmp_path, _history(*A_HISTORY))

    def no_link(source, target):
        raise PermissionError("held")

    monkeypatch.setattr(entry_history.os, "link", no_link)
    outcome = rj.run_results_join(sha, root, slates)
    assert outcome.status == "WRITE_FAILED" and outcome.exit_code == 2
    assert outcome.problems == ("RESULTS_JOIN_WRITE_FAILED:file=report:exception=PermissionError",
                                "RESULTS_JOIN_WRITE_FAILED:file=a-sd:exception=PermissionError")


# ------------------------------------------------------------------------------------------ boundaries


def test_the_results_file_carries_no_money(tmp_path):
    slates = _ab(tmp_path)
    root, sha = _intake(tmp_path, _history(*A_HISTORY, *B_HISTORY))
    outcome = rj.run_results_join(sha, root, slates)
    for name in ("a-sd", "b-classic"):
        payload = json.loads((slates / name / "construction" / rj.RESULTS_NAME).read_bytes())
        assert set(payload) == {"schema_version", "writer", "contract", "source_sha256", "slate", "record_name",
                                "entries", "does_not_establish"}
        assert {key for item in payload["entries"] for key in item} == {
            "entry_id", "class", "place", "contest_entries", "points_hundredths", "percentile"}
        text = json.dumps({key: value for key, value in payload.items() if key != "source_sha256"}).encode()
        assert not [fragment for fragment in MONEY_FRAGMENTS if fragment in text]
        assert b"$" not in text
    printed = json.dumps(outcome.as_dict()["headline"]).encode()
    assert not [fragment for fragment in MONEY_FRAGMENTS if fragment in printed] and b"$" not in printed
    # The gitignored report holds the paid counts; the fixture's fees are really in the export.
    assert outcome.as_dict()["headline"]["rank_check"][0]["paid_n"] == 4


def _command(capsys, *argv: str) -> tuple[int, dict]:
    code = cli.main(["results-join", *argv])
    return code, json.loads(capsys.readouterr().out)


def test_the_command_prints_the_outcome_and_exits_by_status(tmp_path, capsys):
    slates = _ab(tmp_path)
    root, sha = _intake(tmp_path, _history(*A_HISTORY))
    code, printed = _command(capsys, "--source-sha256", sha, "--results-root", str(root), "--slates-root", str(slates))
    assert code == 0 and printed["status"] == "COMPLETE" and printed["contract"] == rj.CONTRACT_VERSION
    assert printed["headline"]["class_counts"]["JOINED"] == 5
    code, printed = _command(capsys, "--source-sha256", "nope", "--results-root", str(root), "--slates-root", str(slates))
    assert code == 2 and printed["problems"] == ["RESULTS_JOIN_INPUT_INVALID:field=source_sha256"]


@pytest.mark.parametrize("inside", ["data/runs/x", "data/standings/y", "tests/fixtures/supplied/z"],
                         ids=["runs", "standings", "supplied"])
def test_the_slates_root_may_not_be_a_snapshot_folder(inside, capsys):
    with pytest.raises(SystemExit) as caught:
        cli.main(["results-join", "--source-sha256", ZERO_SHA, "--slates-root", str(REPO / inside)])
    assert caught.value.code == 2 and "immutable snapshots" in capsys.readouterr().err


def test_every_join_code_is_registered_p_in_results_join_and_emitted_by_this_module():
    registry = load_gate_registry()
    assert registry.families["results_join"].gate_class is GateClass.P
    assert {code for code, name in registry.codes.items() if name == "results_join"} == set(rj.JOIN_CODES)
    scanned = scanned_codes()
    for code in rj.JOIN_CODES:
        assert scanned.get(code) == frozenset({"results_join.py"}), code


def test_the_contract_names_every_class_reason_state_and_key():
    text = (REPO / "docs" / "DATA_CONTRACTS.md").read_text(encoding="utf-8")
    section = text[text.index("## NFL results join, nfl_results_join_v1"):]
    section = section[: section.index("\n## ", 1)]
    names = {*rj.CLASSES, *rj.CAUSES, *rj.STATES, *rj.JOIN_CODES, rj.CONTRACT_VERSION, rj.RESULTS_VERSION,
             rj.RESULTS_NAME, "source_sha256", "record_name", "entries", "contest_entries", "points_hundredths",
             "percentile", "alternate_records", "non_nfl_rows_ignored", "rank_check", "pooled", "excluded",
             "class_counts", "mean_rho", "records_digest", "blank", *rj.DOES_NOT_ESTABLISH}
    assert not sorted(name for name in names if f"`{name}`" not in section)
