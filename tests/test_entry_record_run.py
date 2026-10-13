"""Session 72b: the per-Entry-ID build record reads a run folder (`run_dir`, `run_data`; `--run-dir`, `--run-data`).

Every case runs on a real Showdown `run-slate` through the shared helper (`tests/run_slate_helper.py`): one with the real
projection producer, so its ledger binds `team_projections.csv` by hash, and three on the projection stub (a run that ends
at rung 4, one that ships the baseline alone, one built from a v4 portfolio of theses). The expected values are read
independently: the delivered bytes, the CSV through `csv`, the policy file's own SHA-256, the claim's JSON. A mutation is
made on a copy of the run's folders, never on the fixture.
"""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import io
import json
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from nfl_dfs.dk import parse_salaries
from nfl_dfs.entry_record import EntryRecordRefused, build_records, record_bytes
from nfl_dfs.lineups import validate_lineup

from .run_slate_helper import run_paths, run_showdown_slate, thesis_policy

REPO_ROOT = Path(__file__).resolve().parent.parent
REVIEW_FILE = "review/DK_REVIEW_ENTRY_ne-sea.csv"
BASELINE_FILE = "baseline/DK_BASELINE_ENTRY_V1_baseline.csv"
KEPT = ["EXPECTED_VALUE_OR_ROI", "WIN_OR_CASH_PROBABILITY", "AN_EDGE_OR_ITS_ABSENCE", "CALIBRATION", "UPLOAD_CLEARANCE"]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _finished(tmp_path_factory, label: str, **kwargs) -> SimpleNamespace:
    root = tmp_path_factory.mktemp(label)
    with pytest.MonkeyPatch.context() as patch:
        code, report, out, slate = run_showdown_slate(root, patch, run_id=label, **kwargs)
    paths = run_paths(root, label)
    pointer = json.loads((out / "LATEST_DELIVERABLE.json").read_bytes())
    return SimpleNamespace(code=code, report=report, slate=slate, paths=paths, label=label,
                           delivered=out / pointer["file"]["path"])


@pytest.fixture(scope="module")
def real(tmp_path_factory):
    return _finished(tmp_path_factory, "s72b-real", real_projection=True)


@pytest.fixture(scope="module")
def rung4(tmp_path_factory):
    return _finished(tmp_path_factory, "s72b-rung4", window=40.0)


@pytest.fixture(scope="module")
def baseline(tmp_path_factory):
    return _finished(tmp_path_factory, "s72b-baseline", window=-60.0)


@pytest.fixture(scope="module")
def theses(tmp_path_factory):
    return _finished(tmp_path_factory, "s72b-theses", entries=6, policy=thesis_policy)


def _record(run, file: Path | None = None, *, run_dir=None, run_data=None, folders=True):
    if folders:
        run_dir = run_dir if run_dir is not None else run.paths["run_dir"]
        run_data = run_data if run_data is not None else run.paths["run_data"]
    return build_records(run.paths["salaries"], run.paths["entries"], file if file is not None else run.delivered,
                         run_dir=run_dir, run_data=run_data)


def _refused(code: str, run, file=None, **folders) -> EntryRecordRefused:
    with pytest.raises(EntryRecordRefused) as caught:
        _record(run, file, **folders)
    assert caught.value.code == code, caught.value
    return caught.value


def _copy(run, tmp_path: Path) -> dict[str, Path]:
    """Both run folders copied under another parent, so the run's own absolute paths name the originals."""

    copies = {"run_dir": tmp_path / "moved" / "outputs" / run.label, "run_data": tmp_path / "moved" / "runs" / run.label}
    for key, target in copies.items():
        shutil.copytree(run.paths[key], target)
    return copies


def _rewrite_json(path: Path, change) -> None:
    document = json.loads(path.read_bytes())
    change(document)
    path.write_bytes(json.dumps(document, sort_keys=True).encode("utf-8"))


def _projected(folder: Path) -> Path:
    return folder / "prior_review" / "projected"


def _edit_team_csv(copies: dict[str, Path], edit) -> None:
    """Edit the copy's `team_projections.csv` and bind the ledger and the run report to the new bytes."""

    path = _projected(copies["run_data"]) / "team_projections.csv"
    raw = path.read_bytes()
    rows = list(csv.reader(io.StringIO(raw.decode("utf-8"), newline="")))
    edit(rows)
    buffer = io.StringIO(newline="")
    csv.writer(buffer, lineterminator="\r\n" if b"\r\n" in raw else "\n").writerows(rows)
    path.write_bytes(buffer.getvalue().encode("utf-8"))
    ledger = _projected(copies["run_data"]) / "source_ledger.json"
    _rewrite_json(ledger, lambda doc: doc["derived"].__setitem__("team_projections", _sha256(path)))
    _rewrite_json(copies["run_dir"] / "cowork_run.json", lambda doc: doc["prior_review_hashes"].update(
        {"projected:source_ledger": _sha256(ledger), "projected:team_projections": _sha256(path)}))


def _set_team_cell(team: str, column: str, value: str):
    def edit(rows):
        header = rows[0]
        row = next(row for row in rows[1:] if row and row[header.index("TEAM")] == team)
        row[header.index(column)] = value
    return edit


def _one_cell_changed(run, target: Path) -> str:
    """Write `run.delivered` to `target` with one roster cell of one row changed to a legal replacement."""

    slate = parse_salaries(run.paths["salaries"])
    rows = list(csv.reader(io.StringIO(run.delivered.read_bytes().decode("utf-8-sig"), newline="")))
    start = rows[0].index("Entry Fee") + 1
    row = next(row for row in rows[1:] if row and row[0].strip().isdigit())
    roster = row[start:start + 6]
    by_id = {player.dk_id: player for player in slate.players}
    rostered = {by_id[dk_id].underlying_id for dk_id in roster}
    for slot in range(5, 0, -1):
        for player in slate.players:
            if player.role != "FLEX" or player.underlying_id in rostered:
                continue
            trial = roster[:slot] + [player.dk_id] + roster[slot + 1:]
            if validate_lineup(slate, trial).valid:
                row[start + slot] = player.dk_id
                buffer = io.StringIO(newline="")
                csv.writer(buffer, lineterminator="\r\n").writerows(rows)
                target.write_bytes(buffer.getvalue().encode("utf-8"))
                return row[0]
    raise AssertionError("no legal one-cell replacement in the first row")


# ------------------------------------------------------------------ acceptance


def test_a_run_slates_own_file_records_engine_file_with_its_stage_and_rung(real):
    assert real.code == 0 and real.delivered.read_bytes() == (real.paths["run_dir"] / REVIEW_FILE).read_bytes()
    (normalized,) = sorted(real.paths["run_data"].glob("relaxation/*/portfolio_policy.normalized.json"))
    rows = _record(real)
    assert len(rows) == 20
    for row in rows:
        assert row["run"] == {
            "run_id": "s72b-real",
            "method": {"kind": "ENGINE_FILE", "stage": "PRIOR_ONLY_REVIEW_EXPORT", "final_rung": "DEFAULT",
                       "producer": "run-slate:prior_review:SHOWDOWN", "run_file": REVIEW_FILE},
            "policy_sha256": _sha256(normalized),
            "thesis": None,
            "reasons": {"thesis": "NO_THESIS_CLAIM"},
        }
        assert row["does_not_establish"] == KEPT  # the method is named, so which run built the file is established


def test_one_changed_cell_records_operator_file(real, tmp_path):
    """A copy with one cell changed, and the same change made in place in the run's own `review/` file."""

    copies = _copy(real, tmp_path)
    edited = tmp_path / "edited.csv"
    entry_id = _one_cell_changed(real, edited)
    in_place = copies["run_dir"] / REVIEW_FILE
    in_place.write_bytes(edited.read_bytes())
    (normalized,) = sorted(real.paths["run_data"].glob("relaxation/*/portfolio_policy.normalized.json"))
    for file, folders in ((edited, {}), (in_place, copies)):
        rows = _record(real, file, **folders)
        assert entry_id in {row["entry_id"] for row in rows}
        for row in rows:
            assert row["run"]["method"] == {"kind": "OPERATOR_FILE", "stage": "PRIOR_ONLY_REVIEW_EXPORT",
                                            "final_rung": "DEFAULT", "producer": None, "run_file": None}
            assert row["run"]["reasons"] == {"thesis": "NO_THESIS_CLAIM", "method.producer": "NO_RUN_FILE_MATCHES",
                                             "method.run_file": "NO_RUN_FILE_MATCHES"}
            # The hand pass started from the review the pointer names, so its policy still describes the rows.
            assert row["run"]["policy_sha256"] == _sha256(normalized)


def test_the_market_numbers_equal_the_ledger_bound_csv(real):
    projected = _projected(real.paths["run_data"])
    team_csv = projected / "team_projections.csv"
    ledger = json.loads((projected / "source_ledger.json").read_bytes())
    assert ledger["schema_version"] == "nfl_source_ledger_v2" and ledger["derived"]["team_projections"] == _sha256(team_csv)
    by_team = {row["TEAM"]: row for row in csv.DictReader(io.StringIO(team_csv.read_bytes().decode("utf-8")))}
    game = real.slate.games[0]
    expected = {team: {"total": float(by_team[team]["MARKET_TOTAL"]), "spread": float(by_team[team]["MARKET_SPREAD"]),
                       "reasons": {}} for team in (game.away_team, game.home_team)}
    # The helper fed each team its own numbers, so a swapped team or a total read as a spread cannot match.
    assert expected == {game.away_team: {"total": 46.5, "spread": 3.5, "reasons": {}},
                        game.home_team: {"total": 43.5, "spread": -3.5, "reasons": {}}}
    for row in _record(real):
        assert row["stack_game"] == {"game_id": game.game_id, "market": expected, "market_reason": None}


@pytest.mark.parametrize("which", ["salaries", "entries"])
def test_a_pointer_whose_salary_hash_differs_is_refused_by_name(real, tmp_path, which):
    copies = _copy(real, tmp_path)
    _rewrite_json(copies["run_dir"] / "LATEST_DELIVERABLE.json",
                  lambda doc: doc["inputs"][which].__setitem__("sha256", "0" * 64))
    refusal = _refused("ENTRY_RECORD_RUN_INPUTS_DIFFER", real, **copies)
    assert "pointer" in refusal.detail and which in refusal.detail


def test_without_run_dir_a_runs_own_file_keeps_every_run_field_null(real):
    for row in _record(real, folders=False):
        assert row["run"] == {"run_id": None, "method": None, "policy_sha256": None, "thesis": None,
                              "reasons": dict.fromkeys(("run_id", "method", "policy_sha256", "thesis"),
                                                       "RUN_FOLDER_NOT_SUPPLIED")}
        assert row["stack_game"]["market"] is None and row["stack_game"]["market_reason"] == "RUN_FOLDER_NOT_SUPPLIED"
        assert row["does_not_establish"] == KEPT[:4] + ["WHICH_RUN_BUILT_THE_FILE", "UPLOAD_CLEARANCE"]


# ------------------------------------------------------------------ what the run's own folders say


def test_a_rung_4_run_names_its_missing_policy(rung4):
    assert rung4.code == 0 and rung4.report["relaxation"]["final_rung"] == "4"
    for row in _record(rung4):
        assert row["run"]["method"] == {"kind": "ENGINE_FILE", "stage": "PRIOR_ONLY_REVIEW_EXPORT", "final_rung": "4",
                                        "producer": "run-slate:prior_review:SHOWDOWN", "run_file": REVIEW_FILE}
        assert row["run"]["policy_sha256"] is None and row["run"]["thesis"] is None
        assert row["run"]["reasons"] == {"policy_sha256": "NO_POLICY_AT_FINAL_RUNG", "thesis": "NO_THESIS_CLAIM"}
        # The stub's projection CSVs lie outside the run folder: a named null, never the absolute path as it stands.
        assert row["stack_game"]["market"] is None
        assert row["stack_game"]["market_reason"] == "ARTIFACT_OUTSIDE_RUN_FOLDER"


def test_a_run_that_shipped_the_baseline_names_it_and_claims_no_selection(baseline):
    assert baseline.code == 2 and baseline.delivered.name == Path(BASELINE_FILE).name
    for row in _record(baseline):
        assert row["run"]["method"] == {"kind": "ENGINE_FILE", "stage": "DEADLINE_IMPROVEMENT_SKIPPED",
                                        "final_rung": "DEFAULT", "producer": "run-slate:baseline",
                                        "run_file": BASELINE_FILE}
        assert row["run"]["reasons"] == {"policy_sha256": "FILE_NOT_FROM_THE_REVIEW_SELECTION",
                                         "thesis": "FILE_NOT_FROM_THE_REVIEW_SELECTION"}
        assert row["stack_game"]["market_reason"] == "SOURCE_LEDGER_NOT_FOUND"


def test_the_baseline_of_a_run_that_improved_is_never_called_the_improvement(real):
    """The baseline's bytes delivered from a run whose pointer names the review: the match is by bytes, so the record
    names the baseline file, and the pointer's producer is not borrowed for it."""

    rows = _record(real, real.paths["run_dir"] / BASELINE_FILE)
    for row in rows:
        assert row["run"]["method"] == {"kind": "ENGINE_FILE", "stage": "PRIOR_ONLY_REVIEW_EXPORT",
                                        "final_rung": "DEFAULT", "producer": None, "run_file": BASELINE_FILE}
        assert row["run"]["reasons"] == {"method.producer": "FILE_IS_NOT_THE_POINTER_FILE",
                                         "policy_sha256": "FILE_NOT_FROM_THE_REVIEW_SELECTION",
                                         "thesis": "FILE_NOT_FROM_THE_REVIEW_SELECTION"}


def test_each_thesis_is_read_by_entry_id_from_the_runs_claim(theses):
    claim = json.loads(Path(theses.report["prior_review_artifacts"]["selection_report"]).read_bytes())
    entries = claim["selection"]["portfolio_policy"]["theses"]["entries"]
    rows = _record(theses)
    assert len(rows) == 6 and {row["run"]["thesis"] for row in rows} == {"NE_WIN_BIG", "NE_WIN_CLOSE_LOW", "SEA_WIN_BIG"}
    for row in rows:
        assert row["run"]["thesis"] == entries[row["entry_id"]] and "thesis" not in row["run"]["reasons"]
        assert row["run"]["method"]["final_rung"] == "SUPPLIED"


def test_a_folder_moved_to_another_machine_writes_the_same_record(real, tmp_path):
    """The run's paths rewritten as a Windows machine's, with the run ID repeated higher up the path: the record reads
    the copy's own files, and its bytes equal the record made in place."""

    copies = _copy(real, tmp_path)

    def windows(doc):
        for key, value in doc["prior_review_artifacts"].items():
            if isinstance(value, str) and "/runs/s72b-real/" in value:
                tail = value.split("/runs/s72b-real/", 1)[1].replace("/", "\\")
                doc["prior_review_artifacts"][key] = (
                    "C:\\Users\\ben\\s72b-real\\prior_review\\data\\runs\\s72b-real\\" + tail)

    _rewrite_json(copies["run_dir"] / "cowork_run.json", windows)
    assert record_bytes(_record(real, **copies)) == record_bytes(_record(real))


@pytest.mark.parametrize("case", ["blank", "missing-team"])
def test_a_market_number_the_csv_lacks_is_a_named_null(real, tmp_path, case):
    copies = _copy(real, tmp_path)
    away, home = real.slate.games[0].away_team, real.slate.games[0].home_team
    if case == "blank":
        _edit_team_csv(copies, _set_team_cell(home, "MARKET_SPREAD", ""))
        expected = {"total": 43.5, "spread": None, "reasons": {"spread": "MARKET_VALUE_BLANK"}}
    else:
        _edit_team_csv(copies, lambda rows: rows.remove(next(row for row in rows if row and row[0] == home)))
        expected = {"total": None, "spread": None, "reasons": dict.fromkeys(("total", "spread"),
                                                                            "TEAM_NOT_IN_TEAM_PROJECTIONS")}
    for row in _record(real, **copies):
        assert row["stack_game"]["market"] == {away: {"total": 46.5, "spread": 3.5, "reasons": {}}, home: expected}


@pytest.mark.parametrize("case", ["csv-byte", "not-a-number", "overflow", "ledger-byte", "stale-at-run-clock"])
def test_a_ledger_that_does_not_bind_its_csv_is_refused(real, tmp_path, case):
    copies = _copy(real, tmp_path)
    home = real.slate.games[0].home_team
    if case == "csv-byte":  # the CSV changed and nothing re-bound it
        path = _projected(copies["run_data"]) / "team_projections.csv"
        path.write_bytes(path.read_bytes().replace(b"43.5", b"43.6", 1))
    elif case in ("not-a-number", "overflow"):  # a decimal too large for a float is no number either
        _edit_team_csv(copies, _set_team_cell(home, "MARKET_TOTAL", "forty" if case == "not-a-number" else "1e999"))
    elif case == "ledger-byte":  # the ledger itself is not the one the run recorded writing
        ledger = _projected(copies["run_data"]) / "source_ledger.json"
        ledger.write_bytes(ledger.read_bytes() + b"\n")
    else:  # valid now, stale at the clock the run says it ran at: the ledger is checked at the run's clock, never now
        late = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        _rewrite_json(copies["run_dir"] / "cowork_run.json",
                      lambda doc: doc["prior_review_reports"]["projection"].__setitem__("replay_clock", late))
    _refused("ENTRY_RECORD_SOURCE_LEDGER_INVALID", real, **copies)


def test_without_a_pointer_the_method_still_comes_from_the_runs_own_hashes(real, tmp_path):
    copies = _copy(real, tmp_path)
    (copies["run_dir"] / "LATEST_DELIVERABLE.json").unlink()
    for row in _record(real, **copies):
        assert row["run"]["method"]["kind"] == "ENGINE_FILE" and row["run"]["method"]["run_file"] == REVIEW_FILE
        assert row["run"]["method"]["producer"] is None
        assert row["run"]["reasons"] == {"method.producer": "DELIVERY_POINTER_NOT_FOUND", "thesis": "NO_THESIS_CLAIM"}


def test_without_the_run_report_every_run_field_is_a_named_null(real, tmp_path):
    copies = _copy(real, tmp_path)
    (copies["run_dir"] / "cowork_run.json").unlink()
    for row in _record(real, **copies):
        assert row["run"] == {"run_id": None, "method": None, "policy_sha256": None, "thesis": None,
                              "reasons": dict.fromkeys(("run_id", "method", "policy_sha256", "thesis"),
                                                       "RUN_REPORT_NOT_FOUND")}
        assert row["stack_game"]["market_reason"] == "RUN_REPORT_NOT_FOUND"
        assert row["does_not_establish"] == KEPT[:4] + ["WHICH_RUN_BUILT_THE_FILE", "UPLOAD_CLEARANCE"]


def test_the_output_folder_alone_names_what_only_the_run_data_holds(real):
    for row in _record(real, run_dir=real.paths["run_dir"], run_data=None, folders=False):
        assert row["run"]["method"]["kind"] == "ENGINE_FILE" and row["run"]["policy_sha256"] is not None
        assert row["run"]["reasons"] == {"thesis": "RUN_DATA_NOT_SUPPLIED"}
        assert row["stack_game"]["market_reason"] == "RUN_DATA_NOT_SUPPLIED"
    _refused("ENTRY_RECORD_RUN_FOLDER_INVALID", real, run_dir=None, run_data=real.paths["run_data"], folders=False)


@pytest.mark.parametrize("case", ["other-run", "not-json", "report-list", "no-run-id", "claim-bytes", "claim-policy",
                                  "claim-names", "file-gone", "intake", "columns", "repeated-team"])
def test_a_run_folder_that_contradicts_itself_withholds_the_record(real, theses, tmp_path, case):
    run = theses if case in ("claim-policy", "claim-names") else real
    copies = _copy(run, tmp_path)
    report = copies["run_dir"] / "cowork_run.json"
    claim = copies["run_data"] / "prior_review" / "selection" / "selection_report.json"
    code = "ENTRY_RECORD_RUN_FOLDER_INVALID"
    if case == "other-run":
        _rewrite_json(copies["run_dir"] / "LATEST_DELIVERABLE.json", lambda doc: doc.__setitem__("run_id", "another"))
    elif case == "not-json":
        pointer = copies["run_dir"] / "LATEST_DELIVERABLE.json"
        pointer.write_bytes(pointer.read_bytes()[:-2])
    elif case == "report-list":
        report.write_bytes(b"[]")
    elif case == "no-run-id":  # and no pointer, so nothing else names the run
        _rewrite_json(report, lambda doc: doc.pop("run_id"))
        (copies["run_dir"] / "LATEST_DELIVERABLE.json").unlink()
    elif case == "claim-bytes":
        claim.write_bytes(claim.read_bytes() + b" ")
    elif case == "claim-policy":  # bound by the run's own hash, so only the policy the claim names differs
        _rewrite_json(claim, lambda doc: doc["selection"]["portfolio_policy"].__setitem__(
            "normalized_policy_sha256", "f" * 64))
        _rewrite_json(report, lambda doc: doc["prior_review_hashes"].__setitem__("selection_report", _sha256(claim)))
    elif case == "claim-names":  # bound by the run's own hash, so only the thesis value differs
        _rewrite_json(claim, lambda doc: doc["selection"]["portfolio_policy"]["theses"]["entries"].update(
            {next(iter(doc["selection"]["portfolio_policy"]["theses"]["entries"])): 5}))
        _rewrite_json(report, lambda doc: doc["prior_review_hashes"].__setitem__("selection_report", _sha256(claim)))
    elif case == "file-gone":  # the run recorded writing these bytes and its folder no longer holds them
        (copies["run_dir"] / REVIEW_FILE).unlink()
    elif case == "columns":
        _edit_team_csv(copies, lambda rows: rows[0].__setitem__(rows[0].index("MARKET_TOTAL"), "TOTAL"))
        code = "ENTRY_RECORD_SOURCE_LEDGER_INVALID"
    elif case == "repeated-team":
        _edit_team_csv(copies, lambda rows: rows.append(list(rows[1])))
        code = "ENTRY_RECORD_SOURCE_LEDGER_INVALID"
    else:
        _rewrite_json(report, lambda doc: doc.__setitem__("input_hashes", {"/elsewhere/salary.csv": "0" * 64}))
        code = "ENTRY_RECORD_RUN_INPUTS_DIFFER"
    _refused(code, run, **copies)


def test_the_same_run_folder_writes_byte_identical_records_and_the_script_reads_it(real, tmp_path, capsys):
    first = record_bytes(_record(real))
    assert first == record_bytes(_record(real))
    spec = importlib.util.spec_from_file_location("record_entries", REPO_ROOT / "scripts" / "record_entries.py")
    tool = importlib.util.module_from_spec(spec)
    sys.modules["record_entries"] = tool
    spec.loader.exec_module(tool)
    out = tmp_path / "construction" / "entry_build_record.jsonl"
    argv = ["--salaries", str(real.paths["salaries"]), "--entries", str(real.paths["entries"]),
            "--file", str(real.delivered), "--run-dir", str(real.paths["run_dir"]),
            "--run-data", str(real.paths["run_data"]), "--out", str(out)]
    assert tool.main(argv) == 0 and out.read_bytes() == first
    assert json.loads(capsys.readouterr().out)["sha256"] == hashlib.sha256(first).hexdigest()
    with pytest.raises(SystemExit) as stopped:
        tool.main(argv[:6] + argv[8:])  # --run-data without --run-dir
    assert stopped.value.code == 2 and "--run-data needs --run-dir" in capsys.readouterr().err


@pytest.mark.parametrize("case", ["no-stage", "no-relaxation", "policy-hash", "no-clock", "naive-clock", "no-claim",
                                  "no-opportunities"])
def test_what_the_run_report_does_not_say_is_named(real, tmp_path, case):
    copies = _copy(real, tmp_path)
    report = copies["run_dir"] / "cowork_run.json"
    projection = lambda doc: doc["prior_review_reports"]["projection"]  # noqa: E731
    edits = {
        "no-stage": lambda doc: doc.pop("stage"),
        "no-relaxation": lambda doc: doc.pop("relaxation"),
        "policy-hash": lambda doc: doc["relaxation"]["final_policy"].__setitem__("normalized_sha256", None),
        "no-clock": lambda doc: projection(doc).pop("replay_clock"),
        "naive-clock": lambda doc: projection(doc).__setitem__("replay_clock", "2026-10-13T07:41:12"),
    }
    if case in edits:
        _rewrite_json(report, edits[case])
    elif case == "no-claim":
        (copies["run_data"] / "prior_review" / "selection" / "selection_report.json").unlink()
    else:
        (_projected(copies["run_data"]) / "player_opportunities.csv").unlink()
    row = _record(real, **copies)[0]
    expected = {
        "no-stage": ("method.stage", "STAGE_NOT_RECORDED"),
        "no-relaxation": ("method.final_rung", "RELAXATION_NOT_RECORDED"),
        "policy-hash": ("policy_sha256", "POLICY_HASH_NOT_RECORDED"),
        "no-claim": ("thesis", "SELECTION_REPORT_NOT_FOUND"),
    }
    if case in expected:
        field, reason = expected[case]
        assert row["run"]["reasons"][field] == reason
    if case == "no-relaxation":
        assert row["run"]["policy_sha256"] is None and row["run"]["reasons"]["policy_sha256"] == "RELAXATION_NOT_RECORDED"
    if case in ("no-clock", "naive-clock"):
        assert row["stack_game"]["market_reason"] == "RUN_CLOCK_NOT_RECORDED"
    if case == "no-opportunities":
        assert row["stack_game"]["market_reason"] == "ARTIFACT_NOT_FOUND"


def test_an_unfilled_row_names_its_market_unfilled(real, tmp_path):
    rows = list(csv.reader(io.StringIO(real.delivered.read_bytes().decode("utf-8-sig"), newline="")))
    start = rows[0].index("Entry Fee") + 1
    row = next(row for row in rows[1:] if row and row[0].strip().isdigit())
    row[start:start + 6] = [""] * 6
    blanked = tmp_path / "blanked.csv"
    buffer = io.StringIO(newline="")
    csv.writer(buffer, lineterminator="\r\n").writerows(rows)
    blanked.write_bytes(buffer.getvalue().encode("utf-8"))
    records = {record["entry_id"]: record for record in _record(real, blanked)}
    assert records[row[0]]["stack_game"] == {"game_id": None, "market": None, "market_reason": "UNFILLED"}
    assert records[row[0]]["run"]["method"]["kind"] == "OPERATOR_FILE"


def test_a_run_id_that_names_a_child_folder_still_finds_its_artifact(tmp_path):
    """Only the last (run ID, `prior_review*`) pair anchors a recorded path: a run ID named like a folder below it, or a
    `..` in the tail, never moves the read outside the supplied folder."""

    from nfl_dfs.entry_record import _rebase

    target = tmp_path / "prior_review_attempt_2" / "selection" / "selection_report.json"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"{}")
    recorded = "D:\\x\\selection\\prior_review\\runs\\selection\\prior_review_attempt_2\\selection\\selection_report.json"
    assert _rebase(recorded, "selection", tmp_path) == (target, None)
    assert _rebase("/x/runs/selection/prior_review/../../secret.json", "selection", tmp_path) == (
        None, "ARTIFACT_OUTSIDE_RUN_FOLDER")
    assert _rebase("/x/runs/selection/prior_review/missing.json", "selection", tmp_path) == (None, "ARTIFACT_NOT_FOUND")
    assert _rebase(None, "selection", tmp_path) == (None, "ARTIFACT_NOT_FOUND")
    assert _rebase(5, "selection", tmp_path) == (None, "ARTIFACT_NOT_FOUND")


def test_a_second_copy_of_the_run_file_never_displaces_the_pointers_own(real, tmp_path):
    copies = _copy(real, tmp_path)
    extra = copies["run_dir"] / "a_copy" / "same.csv"
    extra.parent.mkdir()
    extra.write_bytes(real.delivered.read_bytes())  # sorts before review/, and holds the same bytes
    for row in _record(real, **copies):
        assert row["run"]["method"]["run_file"] == REVIEW_FILE
        assert row["run"]["method"]["producer"] == "run-slate:prior_review:SHOWDOWN"


def test_an_entry_id_the_claim_leaves_without_a_thesis_is_named(theses, tmp_path):
    copies = _copy(theses, tmp_path)
    claim = copies["run_data"] / "prior_review" / "selection" / "selection_report.json"
    first = parse_entries_ids(theses)[0]
    _rewrite_json(claim, lambda doc: doc["selection"]["portfolio_policy"]["theses"]["entries"].__setitem__(first, None))
    _rewrite_json(copies["run_dir"] / "cowork_run.json",
                  lambda doc: doc["prior_review_hashes"].__setitem__("selection_report", _sha256(claim)))
    rows = {row["entry_id"]: row for row in _record(theses, **copies)}
    assert rows[first]["run"]["thesis"] is None and rows[first]["run"]["reasons"]["thesis"] == "ENTRY_ID_HAS_NO_THESIS"
    assert sum(row["run"]["thesis"] is not None for row in rows.values()) == 5


def parse_entries_ids(run) -> list[str]:
    from nfl_dfs.dk import parse_entries

    return [entry.entry_id for entry in parse_entries(run.paths["entries"]).authorizations]
