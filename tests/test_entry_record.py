"""Session 72: the per-Entry-ID build record (`nfl_entry_build_record_v1`, `src/nfl_dfs/entry_record.py`).

The acceptance runs on the four committed delivered files (DET@CAR `final_v5`, ATL@NO `qa_iter3`, TB@DAL `final_v3`, Week 4
Classic `LATESWAP_v8`): every prior equals the slate's own committed pool scores (Showdown, a slot-order sum by exact DK ID) or
its portfolio record (Week 4, the record's own figure). The refusals, the determinism and the mutation cases run on copies of
those bytes, rewritten with `write_bytes`. The end-to-end case runs a real Showdown `run-slate` with the procedure's
`NFL_DFS_DUMP_SCORES` path. The record writes the run-folder fields null in this session (Session 72b fills them).
"""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

from nfl_dfs.classic_portfolio import stack_value
from nfl_dfs.classic_theses import _bringback, _stacked
from nfl_dfs.dk import parse_entries, parse_salaries
from nfl_dfs.entry_record import (
    SCHEMA_VERSION,
    EntryRecordRefused,
    build_records,
    record_bytes,
    write_record,
)
from nfl_dfs.portfolio_policy import structure_counts

REPO_ROOT = Path(__file__).resolve().parent.parent
SLATES = REPO_ROOT / "data" / "inbox" / "slates"

ACCEPTANCE = {
    "det-car": {"slug": "det-car-sd-2026-10-04", "file": "construction/DK_REVIEW_ENTRY_det-car-sd_final_v5.csv",
                "salaries": "input/DKSalaries.csv", "entries": "input/DKEntries.csv",
                "scores": "construction/pool_scores.json", "rows": 28},
    "atl-no": {"slug": "atl-no-sd-2026-10-05", "file": "construction/qa_iter3/DK_REVIEW_ENTRY_atl-no-sd_qa_iter3.csv",
               "salaries": "input/DKSalaries_143.csv", "entries": "input/DKEntries_116.csv",
               "scores": "construction/pool_scores.json", "rows": 36},
    "tb-dal": {"slug": "tb-dal-sd-2026-10-08", "file": "construction/DK_REVIEW_ENTRY_tb-dal-sd_final_v3.csv",
               "salaries": "input/DKSalaries.csv", "entries": "input/DKEntries.csv",
               "scores": "construction/pool_scores.json", "rows": 28},
    "wk4": {"slug": "wk4-classic-2026-10-04", "file": "DK_REVIEW_ENTRY_wk4_classic_LATESWAP_v8.csv",
            "salaries": "DKSalaries.csv", "entries": "DKEntries.csv",
            "portfolio": "construction/portfolio_lateswap_v8.json", "rows": 39},
}
ROW_KEYS = {"schema_version", "entry_id", "contest_id", "mode", "hashes", "salary_binding", "run", "roster",
            "captain_dk_id", "prior", "rank", "salary_left", "structure", "dk_status", "later_window_count",
            "stack_game", "does_not_establish"}


def _paths(label: str, root: Path | None = None) -> dict[str, Path]:
    spec = ACCEPTANCE[label]
    base = root if root is not None else SLATES / spec["slug"]
    return {key: base / spec[key] if root is None else root / Path(spec[key]).name
            for key in ("file", "salaries", "entries", "scores", "portfolio") if key in spec}


def _build(paths: dict[str, Path], **override):
    sources = {key: paths[key] for key in ("scores", "portfolio") if key in paths}
    sources.update(override)
    return build_records(paths["salaries"], paths["entries"], paths["file"], **sources)


def _copy(tmp_path: Path, label: str) -> dict[str, Path]:
    real = _paths(label)
    copies = _paths(label, tmp_path)
    for key, path in real.items():
        copies[key].write_bytes(path.read_bytes())
    return copies


def _csv_rows(path: Path) -> list[list[str]]:
    return list(csv.reader(io.StringIO(path.read_bytes().decode("utf-8-sig"), newline="")))


def _write_csv(path: Path, rows: list[list[str]]) -> None:
    buffer = io.StringIO(newline="")
    csv.writer(buffer, lineterminator="\r\n").writerows(rows)
    path.write_bytes(buffer.getvalue().encode("utf-8"))


def _set_cell(path: Path, entry_id: str, column: int, value: str) -> None:
    rows = _csv_rows(path)
    row = next(row for row in rows if row and row[0] == entry_id)
    row[column] = value
    _write_csv(path, rows)


def _first_entry(path: Path) -> list[str]:
    return next(row for row in _csv_rows(path)[1:] if row and row[0].strip().isdigit())


def _refused(code: str, paths: dict[str, Path], **override) -> EntryRecordRefused:
    with pytest.raises(EntryRecordRefused) as caught:
        _build(paths, **override)
    assert caught.value.code == code, caught.value
    return caught.value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ------------------------------------------------------------------ acceptance


def test_the_four_acceptance_files_hold_131_entry_ids():
    assert sum(len(_build(_paths(label))) for label in ACCEPTANCE) == 131


@pytest.mark.parametrize("label", list(ACCEPTANCE), ids=list(ACCEPTANCE))
def test_the_priors_equal_each_runs_own_scores_for_all_131_entry_ids(label):
    """Each prior equals the slate's committed source, named by SHA-256 in the row.

    The committed dumps bind no run ID, so "the run's own" is the card's word for them: TB@DAL's is the delivered run's
    (changelog, 2026-10-08); DET@CAR's is a third run's that reproduces the hand pass's own record of this file
    (`final_v4_record.json`); ATL@NO's names no producing run. The record never claims more than the hash.
    """

    paths = _paths(label)
    rows = _build(paths)
    template = [entry.entry_id for entry in parse_entries(paths["entries"]).authorizations]
    delivered = {row[0]: row for row in _csv_rows(paths["file"])[1:] if row and row[0].strip().isdigit()}
    width = 9 if label == "wk4" else 6
    assert [row["entry_id"] for row in rows] == template and len(rows) == ACCEPTANCE[label]["rows"]
    for row in rows:
        assert row["roster"] == delivered[row["entry_id"]][4:4 + width]
        assert row["contest_id"] == delivered[row["entry_id"]][2]
    if "scores" in paths:
        scores = json.loads(paths["scores"].read_text(encoding="utf-8"))
        for row in rows:
            expected = 0.0
            for dk_id in row["roster"]:
                expected += scores["by_dk_id"][dk_id]
            assert row["prior"] == {"points": pytest.approx(expected, abs=1e-9), "score_version": scores["score_version"],
                                    "source": "POOL_SCORES_SUM", "unscored_dk_ids": [], "excluded_dk_ids_rostered": [],
                                    "reason": None}
        source = paths["scores"]
    else:
        lineups = {item["entry_id"]: item for item in json.loads(paths["portfolio"].read_text(encoding="utf-8"))["lineups"]}
        for row in rows:
            assert row["prior"] == {"points": lineups[row["entry_id"]]["prior_points"], "score_version": None,
                                    "source": "PORTFOLIO_RECORD", "unscored_dk_ids": [], "excluded_dk_ids_rostered": [],
                                    "reason": None}
        source = paths["portfolio"]
    points = [row["prior"]["points"] for row in rows]
    for row in rows:
        assert row["rank"] == 1 + sum(other > row["prior"]["points"] for other in points)
        assert row["hashes"] == {"salary_sha256": _sha256(paths["salaries"]), "entries_sha256": _sha256(paths["entries"]),
                                 "file_sha256": _sha256(paths["file"]), "prior_source_sha256": _sha256(source)}
        assert row["salary_binding"] == "ENTRIES_POOL_MATCH" and row["schema_version"] == SCHEMA_VERSION
        assert set(row) == ROW_KEYS
    if label == "det-car":  # the hand pass's own record of this file (`final_v4_record.json` `after`)
        assert (round(sum(points), 2), round(min(points), 2)) == (2754.79, 85.88)


# ------------------------------------------------------------------ refusals by name


def test_an_entry_id_outside_the_template_is_refused_by_name(tmp_path):
    paths = _copy(tmp_path, "det-car")
    entry = _first_entry(paths["file"])[0]
    _set_cell(paths["file"], entry, 0, "9999999999")
    refusal = _refused("ENTRY_RECORD_ENTRY_ID_NOT_IN_TEMPLATE", paths)
    assert "9999999999" in refusal.detail


@pytest.mark.parametrize("case", ["missing-row", "contest-id", "header"])
def test_a_file_whose_geometry_differs_from_the_template_is_refused(tmp_path, case):
    paths = _copy(tmp_path, "det-car")
    entry = _first_entry(paths["file"])[0]
    if case == "missing-row":
        _write_csv(paths["file"], [row for row in _csv_rows(paths["file"]) if not row or row[0] != entry])
    elif case == "contest-id":
        _set_cell(paths["file"], entry, 2, "123")
    else:  # the same roster columns under another trailing header
        rows = _csv_rows(paths["file"])
        rows[0][rows[0].index("Instructions")] = "Notes"
        _write_csv(paths["file"], rows)
    detail = _refused("ENTRY_RECORD_FILE_GEOMETRY_DIFFERS", paths).detail
    assert entry in detail if case != "header" else "header" in detail


@pytest.mark.parametrize("cell", ["Jared Goff", "Jared Goff (44358497) (LOCKED)", ""], ids=["name", "locked", "blank"])
def test_a_roster_cell_without_an_exact_dk_id_is_refused_by_name(tmp_path, cell):
    paths = _copy(tmp_path, "det-car")
    entry = _first_entry(paths["file"])[0]
    _set_cell(paths["file"], entry, 5, cell)
    refusal = _refused("ENTRY_RECORD_CELL_NOT_AN_EXACT_DK_ID", paths)
    assert entry in refusal.detail and "slot 2" in refusal.detail


def test_a_dk_id_outside_the_salary_file_is_refused_by_name(tmp_path):
    paths = _copy(tmp_path, "det-car")
    entry = _first_entry(paths["file"])[0]
    _set_cell(paths["file"], entry, 5, "12345678")
    assert "12345678" in _refused("ENTRY_RECORD_DK_ID_NOT_IN_SALARY", paths).detail


@pytest.mark.parametrize("case", ["other-slate", "scores-outside", "excluded-outside", "portfolio-outside"])
def test_a_salary_file_mismatch_is_refused_by_name(tmp_path, case):
    if case == "other-slate":
        paths = _copy(tmp_path, "det-car")
        paths["salaries"].write_bytes(_paths("tb-dal")["salaries"].read_bytes())
    elif case in {"scores-outside", "excluded-outside"}:
        paths = _copy(tmp_path, "det-car")
        scores = json.loads(paths["scores"].read_text(encoding="utf-8"))
        if case == "scores-outside":
            scores["by_dk_id"]["99999999"] = 1.0
        else:
            scores["excluded_dk_ids"].append("99999999")
        paths["scores"].write_bytes(json.dumps(scores).encode("utf-8"))
    else:
        paths = _copy(tmp_path, "wk4")
        portfolio = json.loads(paths["portfolio"].read_text(encoding="utf-8"))
        portfolio["lineups"][0]["roster"][0] = "99999999"
        paths["portfolio"].write_bytes(json.dumps(portfolio).encode("utf-8"))
    _refused("ENTRY_RECORD_SALARY_MISMATCH", paths)


def test_a_classic_file_against_a_showdown_template_is_refused(tmp_path):
    paths = _copy(tmp_path, "det-car")
    paths["file"].write_bytes(_paths("wk4")["file"].read_bytes())
    _refused("ENTRY_RECORD_MODE_MISMATCH", paths)
    paths = _copy(tmp_path, "det-car")
    paths["salaries"].write_bytes(_paths("wk4")["salaries"].read_bytes())
    _refused("ENTRY_RECORD_MODE_MISMATCH", paths)


def test_a_lineup_draftkings_would_reject_is_refused(tmp_path):
    paths = _copy(tmp_path, "det-car")
    row = _first_entry(paths["file"])
    _set_cell(paths["file"], row[0], 4, row[5])  # a FLEX row's ID in the Captain slot, the person twice
    assert row[0] in _refused("ENTRY_RECORD_LINEUP_INVALID", paths).detail


def test_an_unreadable_input_is_refused_by_name(tmp_path):
    paths = _copy(tmp_path, "det-car")
    paths["entries"].unlink()
    _refused("ENTRY_RECORD_INPUT_UNREADABLE", paths)
    paths = _copy(tmp_path, "det-car")
    paths["scores"].write_bytes(b"{not json")
    _refused("ENTRY_RECORD_PRIOR_SOURCE_INVALID", paths)


@pytest.mark.parametrize("case", ["no-schema", "other-schema", "nan-score", "bool-score", "both-sources",
                                  "roster-differs", "entry-missing", "entry-repeated", "assignment-differs",
                                  "assignment-extra", "nan-figure", "person-repeated", "no-assignments"])
def test_a_prior_source_that_disagrees_is_refused(tmp_path, case):
    if case in {"no-schema", "other-schema", "nan-score", "bool-score"}:
        paths = _copy(tmp_path, "det-car")
        scores = json.loads(paths["scores"].read_text(encoding="utf-8"))
        dk_id = _first_entry(paths["file"])[5]
        if case == "no-schema":
            scores = {"by_dk_id": scores["by_dk_id"]}
        elif case == "other-schema":  # every other key intact, so only the schema check can refuse it
            scores["schema_version"] = "nfl_prior_pool_scores_v0"
        else:
            scores["by_dk_id"][dk_id] = float("nan") if case == "nan-score" else True
        paths["scores"].write_bytes(json.dumps(scores).encode("utf-8"))
        _refused("ENTRY_RECORD_PRIOR_SOURCE_INVALID", paths)
        return
    if case == "both-sources":
        paths = _copy(tmp_path, "det-car")
        _refused("ENTRY_RECORD_PRIOR_SOURCE_INVALID", paths, portfolio=paths["scores"])
        return
    paths = _copy(tmp_path, "wk4")
    portfolio = json.loads(paths["portfolio"].read_text(encoding="utf-8"))
    if case == "roster-differs":
        first, second = portfolio["lineups"][0], portfolio["lineups"][1]
        spare = next(dk_id for dk_id in second["roster"] if dk_id not in first["roster"])
        first["roster"][-1] = spare  # both views changed alike, so only the comparison with the file can refuse it
        portfolio["assignments_by_entry_id"][first["entry_id"]] = list(first["roster"])
    elif case == "entry-repeated":  # the same Entry ID twice, the second with another figure
        portfolio["lineups"].append({**portfolio["lineups"][0], "prior_points": 1.0})
    elif case == "assignment-differs":  # the record's two views disagree for one Entry ID
        first = portfolio["lineups"][0]
        portfolio["assignments_by_entry_id"][first["entry_id"]] = portfolio["lineups"][1]["roster"]
    elif case == "assignment-extra":  # an Entry ID assigned in one view and absent from the other
        portfolio["assignments_by_entry_id"]["9999999999"] = portfolio["lineups"][0]["roster"]
    elif case == "nan-figure":
        portfolio["lineups"][0]["prior_points"] = float("nan")
    elif case == "person-repeated":  # the same set, one ID twice
        portfolio["lineups"][0]["roster"].append(portfolio["lineups"][0]["roster"][0])
    elif case == "no-assignments":
        del portfolio["assignments_by_entry_id"]
    else:  # both views lose the Entry ID alike
        dropped = portfolio["lineups"].pop()
        del portfolio["assignments_by_entry_id"][dropped["entry_id"]]
    paths["portfolio"].write_bytes(json.dumps(portfolio).encode("utf-8"))
    _refused("ENTRY_RECORD_PRIOR_SOURCE_INVALID", paths)


# ------------------------------------------------------------------ named nulls


@pytest.mark.parametrize("case", ["unscored", "excluded"])
def test_an_unscored_dk_id_is_a_named_null_and_an_excluded_one_keeps_its_number(tmp_path, case):
    paths = _copy(tmp_path, "det-car")
    scores = json.loads(paths["scores"].read_text(encoding="utf-8"))
    dk_id = _first_entry(paths["file"])[5]
    if case == "unscored":
        del scores["by_dk_id"][dk_id]
    else:
        scores["excluded_dk_ids"].append(dk_id)
    paths["scores"].write_bytes(json.dumps(scores).encode("utf-8"))
    rows = _build(paths)
    holding = [row for row in rows if dk_id in row["roster"]]
    assert holding
    for row in holding:
        if case == "unscored":  # no number exists: a named null, never 0
            assert row["prior"]["points"] is None and row["prior"]["unscored_dk_ids"] == [dk_id]
            assert row["prior"]["reason"] == "UNSCORED_DK_ID" and row["rank"] is None
            assert row["prior"]["excluded_dk_ids_rostered"] == []
        else:  # the dump's own number, the gate decision named beside it
            expected = 0.0
            for rostered in row["roster"]:
                expected += scores["by_dk_id"][rostered]
            assert row["prior"]["points"] == pytest.approx(expected, abs=1e-9) and row["prior"]["reason"] is None
            assert row["prior"]["excluded_dk_ids_rostered"] == [dk_id] and row["prior"]["unscored_dk_ids"] == []
    ranked = sorted(row["rank"] for row in rows if row["rank"] is not None)
    assert ranked[0] == 1 and len(ranked) == (len(rows) - len(holding) if case == "unscored" else len(rows))


def test_no_prior_source_is_a_named_null():
    paths = _paths("det-car")
    rows = build_records(paths["salaries"], paths["entries"], paths["file"])
    for row in rows:
        assert row["prior"] == {"points": None, "score_version": None, "source": None, "unscored_dk_ids": [],
                                "excluded_dk_ids_rostered": [], "reason": "NO_PRIOR_SOURCE"}
        assert row["rank"] is None and row["hashes"]["prior_source_sha256"] is None


@pytest.mark.parametrize("label", list(ACCEPTANCE), ids=list(ACCEPTANCE))
def test_a_market_total_the_ledger_lacks_is_a_named_null(label):
    paths = _paths(label)
    slate = parse_salaries(paths["salaries"])
    by_id = {player.dk_id: player for player in slate.players}
    for row in _build(paths):
        quarterbacks = [by_id[dk_id] for dk_id in row["roster"] if by_id[dk_id].position == "QB"]
        game = quarterbacks[0].game_id if label == "wk4" else slate.games[0].game_id
        assert row["stack_game"] == {"game_id": game, "market": None, "market_reason": "RUN_FOLDER_NOT_SUPPLIED"}
        assert row["run"] == {"run_id": None, "method": None, "policy_sha256": None, "thesis": None,
                              "reasons": dict.fromkeys(("run_id", "method", "policy_sha256", "thesis"), "RUN_FOLDER_NOT_SUPPLIED")}


def test_an_unfilled_entry_id_is_recorded_as_unfilled(tmp_path):
    paths = _copy(tmp_path, "det-car")
    entry = _first_entry(paths["file"])[0]
    rows = _csv_rows(paths["file"])
    row = next(row for row in rows if row and row[0] == entry)
    row[4:10] = [""] * 6
    _write_csv(paths["file"], rows)
    record = {row["entry_id"]: row for row in _build(paths)}
    blank = record[entry]
    assert blank["roster"] is None and blank["captain_dk_id"] is None and blank["rank"] is None
    assert blank["prior"]["reason"] == "UNFILLED" and blank["prior"]["points"] is None
    assert blank["structure"] is None and blank["dk_status"] is None and blank["salary_left"] is None
    assert blank["later_window_count"] is None and blank["stack_game"]["game_id"] is None
    assert sum(1 for row in record.values() if row["roster"] is not None) == 27


# ------------------------------------------------------------------ structure and descriptors


@pytest.mark.parametrize("label", list(ACCEPTANCE), ids=list(ACCEPTANCE))
def test_the_structure_counts_come_from_the_rule_functions(label):
    paths = _paths(label)
    slate = parse_salaries(paths["salaries"])
    by_id = {player.dk_id: player for player in slate.players}
    earliest = min(player.lock_at for player in slate.players)
    for row in _build(paths):
        roster = row["roster"]
        players = [by_id[dk_id] for dk_id in roster]
        counts = structure_counts(slate, roster)
        structure = row["structure"]
        for key in ("qb_count", "pass_catchers_with_rostered_qb", "kicker_count", "dst_count", "offense_against_own_dst"):
            assert structure[key] == counts[key], key
        # An independent oracle for the Session 23 counts, written from the salary rows.
        quarterbacks = [p for p in players if p.position == "QB"]
        dst_teams = {p.team for p in players if p.position == "DST"}
        assert counts == {
            "qb_count": len(quarterbacks),
            "pass_catchers_with_rostered_qb": [
                len([p for p in players if p.team == qb.team and p.position in ("WR", "TE")]) for qb in quarterbacks],
            "salary_left": slate.salary_cap - sum(p.salary for p in players),
            "kicker_count": len([p for p in players if p.position == "K"]),
            "dst_count": len([p for p in players if p.position == "DST"]),
            "offense_against_own_dst": len([p for p in players if p.position != "DST" and p.team in dst_teams]),
        }
        assert row["salary_left"] == counts["salary_left"] == slate.salary_cap - sum(p.salary for p in players)
        # Independent oracles for the two counts no rule function holds.
        dst_opponents = {p.opponent for p in players if p.position == "DST"}
        assert structure["offense_facing_rostered_dst"] == sum(
            1 for p in players if p.position != "DST" and p.team in dst_opponents)
        teams: dict[str, int] = {}
        for p in players:
            teams[p.team] = teams.get(p.team, 0) + 1
        assert structure["team_split"] == teams
        if counts["qb_count"] == 1:
            assert structure["bring_backs"] == stack_value(slate, roster, "QB_BRINGBACK")
            assert structure["rb_with_own_dst"] == stack_value(slate, roster, "RB_DST_PAIR")
            assert structure["stack_rule_reason"] is None
        else:
            assert structure["bring_backs"] is None and structure["rb_with_own_dst"] is None
            assert structure["stack_rule_reason"] == "STACK_RULE_NEEDS_ONE_QB"
        if label == "wk4":
            assert _stacked(by_id, roster) == (structure["pass_catchers_with_rostered_qb"][0] > 0)
            assert _bringback(by_id, roster) == (structure["bring_backs"] > 0)
            assert row["captain_dk_id"] is None
        else:
            assert row["captain_dk_id"] == roster[0] and by_id[roster[0]].role == "CPT"
        flags = {dk_id: by_id[dk_id].status_raw.strip() for dk_id in roster if by_id[dk_id].status_raw.strip()}
        assert row["dk_status"] == {"flags": flags, "q_count": sum(1 for value in flags.values() if value.upper() == "Q")}
        assert row["later_window_count"] == sum(1 for p in players if p.lock_at > earliest)


def test_the_record_carries_no_fee_contest_name_or_winnings():
    paths = _paths("det-car")
    data = record_bytes(_build(paths))
    entries = parse_entries(paths["entries"])
    for name in {entry.contest_name for entry in entries.authorizations}:
        assert name.encode("utf-8") not in data
    for word in (b"fee", b"Fee", b"winning", b"Winning", b"payout", b"prize"):
        assert word not in data
    for line in data.splitlines():
        assert set(json.loads(line)) == ROW_KEYS


def test_changing_avg_points_per_game_moves_only_the_salary_hash(tmp_path):
    paths = _copy(tmp_path, "det-car")
    before = _build(paths)
    rows = _csv_rows(paths["salaries"])
    column = rows[0].index("AvgPointsPerGame")
    for row in rows[1:]:
        if len(row) > column:
            row[column] = "123.45"
    _write_csv(paths["salaries"], rows)
    after = _build(paths)
    assert [row["hashes"]["salary_sha256"] for row in before] != [row["hashes"]["salary_sha256"] for row in after]
    for row in before + after:
        row["hashes"].pop("salary_sha256")
    assert before == after


# ------------------------------------------------------------------ determinism, mutation, write-once


def test_two_runs_write_byte_identical_records(tmp_path):
    for label in ("det-car", "wk4"):
        first, second = record_bytes(_build(_paths(label))), record_bytes(_build(_paths(label)))
        assert first == second and b"\r" not in first and first.endswith(b"\n")
        assert first.count(b"\n") == ACCEPTANCE[label]["rows"]
        assert write_record(tmp_path / f"{label}-a.jsonl", first) == "WRITTEN"
        assert write_record(tmp_path / f"{label}-b.jsonl", second) == "WRITTEN"
        assert (tmp_path / f"{label}-a.jsonl").read_bytes() == (tmp_path / f"{label}-b.jsonl").read_bytes() == first


@pytest.mark.parametrize("which, code", [
    ("salaries", "ENTRY_RECORD_ARTIFACT_CONFLICT"), ("entries", "ENTRY_RECORD_FILE_GEOMETRY_DIFFERS"),
    ("file", "ENTRY_RECORD_DK_ID_NOT_IN_SALARY"), ("scores", "ENTRY_RECORD_ARTIFACT_CONFLICT")],
    ids=["salaries", "entries", "file", "scores"])
def test_a_changed_input_byte_withholds_the_record(tmp_path, which, code):
    """A changed byte refuses before the write (a binding) or at it (the record's bytes differ); the record stays."""

    paths = _copy(tmp_path, "det-car")
    out = tmp_path / "entry_build_record.jsonl"
    assert write_record(out, record_bytes(_build(paths))) == "WRITTEN"
    kept = out.read_bytes()
    entry = _first_entry(paths["file"])
    if which == "salaries":  # one rostered person's DraftKings status (a salary breaks the CPT/FLEX pairing)
        rows = _csv_rows(paths["salaries"])
        target = next(row for row in rows if row and row[3] == entry[5])
        target[rows[0].index("Status")] = "Q"
        _write_csv(paths["salaries"], rows)
    elif which == "entries":  # one Contest ID
        _set_cell(paths["entries"], entry[0], 2, "123")
    elif which == "file":  # one digit of one DK ID
        _set_cell(paths["file"], entry[0], 5, "9" + entry[5][1:])
    else:  # one score
        scores = json.loads(paths["scores"].read_text(encoding="utf-8"))
        scores["by_dk_id"][entry[5]] += 0.5
        paths["scores"].write_bytes(json.dumps(scores).encode("utf-8"))
    with pytest.raises(EntryRecordRefused) as caught:
        write_record(out, record_bytes(_build(paths)))
    assert caught.value.code == code and out.read_bytes() == kept


def test_the_write_never_replaces_an_existing_record(tmp_path):
    data = record_bytes(_build(_paths("tb-dal")))
    out = tmp_path / "construction" / "entry_build_record.jsonl"
    assert write_record(out, data) == "WRITTEN"
    assert write_record(out, data) == "ALREADY_PRESENT"
    with pytest.raises(EntryRecordRefused) as caught:
        write_record(out, data + b"{}\n")
    assert caught.value.code == "ENTRY_RECORD_ARTIFACT_CONFLICT" and out.read_bytes() == data
    folder = tmp_path / "taken"
    folder.mkdir()
    with pytest.raises(EntryRecordRefused) as caught:
        write_record(folder, data)
    assert caught.value.code == "ENTRY_RECORD_ARTIFACT_CONFLICT"


@pytest.mark.parametrize("label", list(ACCEPTANCE), ids=list(ACCEPTANCE))
def test_the_committed_records_are_what_the_builder_writes(label):
    """The backfill: each committed slate's record is the builder's bytes on that slate's committed inputs."""

    committed = SLATES / ACCEPTANCE[label]["slug"] / "construction" / "entry_build_record.jsonl"
    assert committed.read_bytes() == record_bytes(_build(_paths(label)))


# ------------------------------------------------------------------ the procedure, end to end


def test_the_procedure_dump_lands_in_the_run_folder(tmp_path, monkeypatch):
    from .test_concentration_run_slate import _run

    run_id = "s72-dump"
    dump = tmp_path / "runs" / run_id / "pool_scores.json"
    monkeypatch.setenv("NFL_DFS_DUMP_SCORES", str(dump))
    code, report, _root, _slate = _run(tmp_path, monkeypatch, run_id=run_id)
    assert code == 0 and dump.is_file()
    scores = json.loads(dump.read_text(encoding="utf-8"))
    delivered = Path(report["latest_deliverable"]["path"])
    rows = build_records(tmp_path / "DKSalaries.csv", tmp_path / "DKEntries.csv", delivered, scores=dump)
    assert rows and all(row["roster"] is not None for row in rows)
    for row in rows:
        expected = 0.0
        for dk_id in row["roster"]:
            expected += scores["by_dk_id"][dk_id]
        assert row["prior"]["points"] == pytest.approx(expected, abs=1e-9)
        assert row["salary_binding"] == "ENTRIES_POOL_ABSENT"


# ------------------------------------------------------------------ the script


def _script():
    spec = importlib.util.spec_from_file_location("record_entries", REPO_ROOT / "scripts" / "record_entries.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["record_entries"] = module
    spec.loader.exec_module(module)
    return module


def test_the_script_writes_once_and_names_a_refusal(tmp_path, capsys):
    tool = _script()
    paths = _copy(tmp_path, "det-car")
    out = tmp_path / "construction" / "entry_build_record.jsonl"
    argv = ["--salaries", str(paths["salaries"]), "--entries", str(paths["entries"]), "--file", str(paths["file"]),
            "--scores", str(paths["scores"]), "--out", str(out)]
    assert tool.main(argv) == 0
    first = json.loads(capsys.readouterr().out)
    assert first == {"rows": 28, "state": "WRITTEN", "sha256": hashlib.sha256(out.read_bytes()).hexdigest()}
    assert out.read_bytes() == record_bytes(_build(paths))
    assert tool.main(argv) == 0
    assert json.loads(capsys.readouterr().out)["state"] == "ALREADY_PRESENT"
    _set_cell(paths["file"], _first_entry(paths["file"])[0], 0, "9999999999")
    assert tool.main(argv) == 2
    captured = capsys.readouterr()
    assert captured.err.startswith("REFUSED ENTRY_RECORD_ENTRY_ID_NOT_IN_TEMPLATE:") and captured.out == ""
    assert tool.main(argv[:-4] + ["--out", str(out)]) == 2  # no prior source is a null, but the file is still refused
    capsys.readouterr()
    for root in ("data/runs", "data/standings/inbox", "tests/fixtures/supplied"):
        inside = REPO_ROOT / root / "s72-never-written" / "entry_build_record.jsonl"
        with pytest.raises(SystemExit) as stopped:
            tool.main(argv[:-2] + ["--out", str(inside)])
        assert stopped.value.code == 2 and not inside.parent.exists()
        assert "immutable snapshots" in capsys.readouterr().err
