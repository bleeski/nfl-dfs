"""Session 71b: `nfl results-report`, the write-once `nfl_results_report_v1` file and its refusals.

Fixtures are synthetic bytes built with Session 69's and Session 71's helpers, taken in through `results-intake` and
written with `write_bytes`; the account export carries winnings and never enters the repository. Every test but the
two that run the registered file through the command uses 200 resamples, so the suite stays fast.
"""

from __future__ import annotations

import dataclasses
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from nfl_dfs import cli, entry_history
from nfl_dfs import results_report as rr
from nfl_dfs.contracts import GateClass
from nfl_dfs.gate_registry import load_gate_registry
from nfl_dfs.hashing import sha256_bytes
from tests.test_entry_history import _history, _row
from tests.test_gate_registry import scanned_codes
from tests.test_results_report import STANDARD, TOP_HEAVY, _contest, _worse_slates

REPO = Path(__file__).resolve().parents[1]
REGISTERED = rr.load_results_metrics()
FAST = dataclasses.replace(REGISTERED, bootstrap={**REGISTERED.bootstrap, "resamples": 200})
RAW = _history(*STANDARD)
ERA = "2026-09-09"
FIVE_SLATES = _history(*[_contest(day, f"2026-09-{10 + day:02d}", 100 * day, TOP_HEAVY) for day in range(1, 6)])


def _intake(tmp_path: Path, raw: bytes = RAW, root: Path | None = None) -> tuple[Path, str]:
    source = tmp_path / "downloads" / f"{sha256_bytes(raw)[:12]}.csv"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(raw)
    root = root or tmp_path / "results"
    outcome = entry_history.run_intake(source, root)
    assert outcome.status in ("COMPLETE", "ALREADY_PRESENT"), outcome.problems
    return root, outcome.source_sha256


def _target(root: Path, sha: str, era: str = ERA) -> Path:
    return root / "reports" / sha / f"results_report.era-{era}.w1.json"


def _run(root: Path, sha: str, era: str | None = None, metrics: rr.ResultsMetrics = FAST) -> rr.ReportOutcome:
    return rr.run_results_report(sha, root, era, metrics=metrics)


def _command(capsys, *argv: str) -> tuple[int, dict]:
    # Session 77 moved the command's default to v2; these tests pin the v1 report, so they name it.
    code = cli.main(["results-report", "--metrics-version", "nfl_results_metrics_v1", *argv])
    return code, json.loads(capsys.readouterr().out)


# ------------------------------------------------------------------------------------------- the writer


def test_the_command_writes_the_report_once_and_hashes_it(tmp_path, capsys):
    root, sha = _intake(tmp_path)
    target = _target(root, sha)
    code, printed = _command(capsys, "--source-sha256", sha, "--results-root", str(root))
    assert (code, printed["status"], printed["exit_code"], printed["problems"]) == (0, "COMPLETE", 0, [])
    written = target.read_bytes()
    assert printed["files"]["report"] == {"path": str(target), "state": "WRITTEN", "sha256": sha256_bytes(written)}
    assert (printed["contract"], printed["source_sha256"]) == ("nfl_results_report_v1", sha)
    assert printed["engine_era_start"] == {"date": ERA, "is_default": True}
    payload = json.loads(written)
    assert (payload["schema_version"], payload["writer"], payload["source"]["sha256"]) == (
        "nfl_results_report_v1", "w1", sha)
    assert written == rr.canonical_bytes(payload)  # sorted keys, compact, one trailing LF
    again_code, again = _command(capsys, "--source-sha256", sha, "--results-root", str(root))
    assert (again_code, again["status"], again["files"]["report"]["state"]) == (0, "ALREADY_PRESENT", "ALREADY_PRESENT")
    assert again["files"]["report"]["sha256"] == printed["files"]["report"]["sha256"]
    assert target.read_bytes() == written


def test_two_runs_in_two_processes_give_byte_identical_artifacts(tmp_path):
    files = []
    for seed in ("0", "12345"):
        root, sha = _intake(tmp_path / seed, FIVE_SLATES)
        environment = {**os.environ, "PYTHONHASHSEED": seed}
        done = subprocess.run((sys.executable, "-m", "nfl_dfs.cli", "results-report", "--source-sha256", sha,
                               "--results-root", str(root), "--metrics-version", "nfl_results_metrics_v1"),
                              capture_output=True, timeout=300, env=environment, check=False)
        assert done.returncode == 0, done.stdout[-400:] + done.stderr[-400:]
        files.append(_target(root, sha).read_bytes())
    assert files[0] == files[1]
    assert json.loads(files[0])["bootstrap"]["resamples"] == 10_000  # the registered count, not the tests' 200


def test_one_changed_snapshot_byte_is_refused(tmp_path):
    root, sha = _intake(tmp_path)
    assert _run(root, sha).status == "COMPLETE"
    first = _target(root, sha).read_bytes()
    snapshot = root / "inbox" / f"{sha}.csv"
    changed = snapshot.read_bytes().replace(b"142.36", b"142.37", 1)
    snapshot.write_bytes(changed)
    for path in (root / "reports").rglob("*.json"):
        path.unlink()
    outcome = _run(root, sha)
    assert (outcome.status, outcome.exit_code) == ("REFUSED", 2)
    assert outcome.problems == ("RESULTS_REPORT_SNAPSHOT_INVALID:reason=hash",)
    assert outcome.files["report"]["state"] == "NOT_ATTEMPTED"
    assert not list((root / "reports").rglob("*.json"))
    # The same change taken in through results-intake is a new snapshot with its own report.
    other_root, other_sha = _intake(tmp_path / "again", changed)
    assert other_sha != sha and _run(other_root, other_sha).status == "COMPLETE"
    assert _target(other_root, other_sha).read_bytes() != first


def test_two_eras_write_two_files_and_the_trigger_never_moves(tmp_path, capsys):
    # Three slates from 2026-10-11, each with a top-heavy contest finishing worse than a flatter one.
    root, sha = _intake(tmp_path, _history(*_worse_slates(3)))
    default = _run(root, sha)
    code, moved = _command(capsys, "--source-sha256", sha, "--results-root", str(root),
                           "--engine-era-start", "2026-10-12")
    assert (default.status, code, moved["status"]) == ("COMPLETE", 0, "COMPLETE")
    assert moved["engine_era_start"] == {"date": "2026-10-12", "is_default": False}
    first, second = json.loads(_target(root, sha).read_bytes()), json.loads(_target(root, sha, "2026-10-12").read_bytes())
    assert (first["engine_era_start"], second["engine_era_start"]) == (
        {"date": ERA, "is_default": True}, {"date": "2026-10-12", "is_default": False})
    assert (first["scopes"]["engine_era"]["slates"], second["scopes"]["engine_era"]["slates"]) == (3, 2)
    assert first["within_slate_trigger"] == second["within_slate_trigger"]
    assert first["within_slate_trigger"]["slates"] == 3  # the registered era's three slates, in both files
    assert sorted(path.name for path in (root / "reports" / sha).iterdir()) == [
        "results_report.era-2026-09-09.w1.json", "results_report.era-2026-09-09.w1.md",
        "results_report.era-2026-10-12.w1.json", "results_report.era-2026-10-12.w1.md"]


# ------------------------------------------------------------------------------------------- refusals


@pytest.mark.parametrize(("sha", "era", "field"), [
    pytest.param("short", None, "source_sha256", id="short"),
    pytest.param("upper", None, "source_sha256", id="upper"),
    pytest.param("not_hex", None, "source_sha256", id="not-hex"),
    pytest.param("good", "2026-9-9", "engine_era_start", id="era"),
])
def test_input_invalid_is_refused_and_writes_nothing(tmp_path, sha, era, field):
    root, good = _intake(tmp_path)
    given = {"short": good[:63], "upper": good.upper(), "not_hex": "g" * 64, "good": good}[sha]
    assert given != good or sha == "good"
    outcome = _run(root, given, era)
    assert (outcome.status, outcome.exit_code) == ("REFUSED", 2)
    assert outcome.problems == (f"RESULTS_REPORT_INPUT_INVALID:field={field}",)
    assert outcome.source_sha256 == (good if sha == "good" else None)
    assert not (root / "reports").exists()


def _patched_lstat(monkeypatch, snapshot: Path, mode: int | None) -> None:
    """The check reads one `os.lstat`: a patched mode reaches each branch on every platform (a real symlink needs a
    privilege on Windows, and a FIFO does not exist there). `None` makes the call itself fail, as EACCES does."""

    real_lstat = os.lstat

    def lstat(path, *args, **kwargs):
        if Path(path).name != snapshot.name:
            return real_lstat(path, *args, **kwargs)
        if mode is None:
            raise PermissionError(13, "Permission denied", str(path))
        return os.stat_result((mode, 0, 0, 1, 0, 0, 0, 0, 0, 0))

    monkeypatch.setattr(os, "lstat", lstat)


@pytest.mark.parametrize("damage", ["absent", "symlink", "unreadable", "fifo", "stat_denied", "open_denied", "hash",
                                    "past_the_cap"])
def test_a_snapshot_that_is_not_its_bytes_is_refused_by_reason(tmp_path, monkeypatch, damage):
    root, sha = _intake(tmp_path)
    snapshot = root / "inbox" / f"{sha}.csv"
    reason = damage
    if damage == "absent":
        sha = sha256_bytes(b"never taken in")
    elif damage == "symlink":
        _patched_lstat(monkeypatch, snapshot, stat.S_IFLNK | 0o777)
    elif damage == "unreadable":
        snapshot.unlink()
        snapshot.mkdir()
    elif damage in ("fifo", "stat_denied"):  # a FIFO would block open() forever; a stat error is named, not raised
        _patched_lstat(monkeypatch, snapshot, stat.S_IFIFO | 0o644 if damage == "fifo" else None)
        reason = "unreadable"
    elif damage == "open_denied":  # a plain file a scanner or another process holds
        real_open = os.open

        def held(path, *args, **kwargs):
            if Path(path).name == snapshot.name:
                raise PermissionError(13, "Permission denied", str(path))
            return real_open(path, *args, **kwargs)

        monkeypatch.setattr(os, "open", held)
        reason = "unreadable"
    elif damage == "hash":
        snapshot.write_bytes(RAW + b"\r\n")
    else:
        monkeypatch.setattr(entry_history, "MAX_BYTES", len(RAW) - 1)
        reason = "hash"  # no intake writes a file past the cap, so its first MAX_BYTES + 1 bytes cannot hash to the name
    outcome = _run(root, sha)
    assert (outcome.status, outcome.exit_code) == ("REFUSED", 2)
    assert outcome.problems == (f"RESULTS_REPORT_SNAPSHOT_INVALID:reason={reason}",)
    assert outcome.headline is None and not (root / "reports").exists()


def test_a_parser_refusal_passes_through_by_its_own_code(tmp_path):
    root = tmp_path / "results"
    unparsed = b"not,an,entry,history\r\n1,2,3,4\r\n"
    sha = sha256_bytes(unparsed)
    (root / "inbox").mkdir(parents=True)
    (root / "inbox" / f"{sha}.csv").write_bytes(unparsed)
    outcome = _run(root, sha)
    with pytest.raises(entry_history.EntryHistoryRefused) as refused:
        entry_history.parse_entry_history(unparsed)
    assert (outcome.status, outcome.problems) == ("REFUSED", refused.value.problems)
    assert outcome.problems[0].startswith("ENTRY_HISTORY_HEADER_INVALID")
    assert not (root / "reports").exists()


def test_another_file_at_the_report_name_is_never_overwritten(tmp_path):
    root, sha = _intake(tmp_path)
    target = _target(root, sha)
    target.parent.mkdir(parents=True)
    target.write_bytes(b"{}\n")
    outcome = _run(root, sha)
    assert (outcome.status, outcome.problems) == ("REFUSED", ("RESULTS_REPORT_ARTIFACT_CONFLICT:file=report",))
    assert outcome.files["report"]["state"] == "REFUSED" and "results-report" in outcome.files["report"]["recovery"]
    assert outcome.files["report"]["sha256"] is None
    assert target.read_bytes() == b"{}\n"


def test_a_write_failure_is_named_by_its_exception_class(tmp_path, monkeypatch):
    root, sha = _intake(tmp_path)

    def no_link(source, target):
        raise PermissionError("held")

    monkeypatch.setattr(entry_history.os, "link", no_link)
    outcome = _run(root, sha)
    assert (outcome.status, outcome.exit_code) == ("WRITE_FAILED", 2)
    assert outcome.problems == ("RESULTS_REPORT_WRITE_FAILED:file=report:exception=PermissionError",)
    assert outcome.files["report"]["state"] == "WRITE_FAILED"
    assert not _target(root, sha).exists()


def test_a_metrics_defect_fails_the_command_by_name(tmp_path, capsys, monkeypatch):
    root, sha = _intake(tmp_path)
    broken = tmp_path / "metrics.json"
    broken.write_bytes(rr.DEFAULT_METRICS_PATH.read_bytes().replace(b'"seed": 20261010', b'"seed": true'))
    monkeypatch.setattr(rr, "DEFAULT_METRICS_PATH", broken)
    code, printed = _command(capsys, "--source-sha256", sha, "--results-root", str(root))
    assert (code, printed["stage"], printed["error"]) == (2, "CLI_FAILED", "ResultsMetricsError")
    assert "bootstrap.seed" in printed["message"]
    assert not (root / "reports").exists()


# ------------------------------------------------------------------------------------------- stdout


def _keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {key for item in value.values() for key in _keys(item)}
    if isinstance(value, list):
        return {key for item in value for key in _keys(item)}
    return set()


def _scalars(value: object) -> list[object]:
    if isinstance(value, dict):
        return [scalar for item in value.values() for scalar in _scalars(item)]
    if isinstance(value, list):
        return [scalar for item in value for scalar in _scalars(item)]
    return [value]


def test_stdout_carries_no_money(tmp_path, capsys):
    rich = _row(Entry_Key="4000000099", Contest_Key="100000099", Winnings_Non_Ticket="$1,234.56",
                Winnings_Ticket="$43.21", Entry_Fee="$7.77", Prize_Pool="$9,876.54")
    root, sha = _intake(tmp_path, _history(*STANDARD, rich))
    code, printed = _command(capsys, "--source-sha256", sha, "--results-root", str(root))
    assert code == 0 and printed["headline"]["nfl"]["entries"] == 4
    keys = _keys(printed)
    for fragment in ("cents", "fee", "winnings", "prize", "return", "share", "concentration"):
        assert not [key for key in keys if fragment in key], fragment
    assert "net" not in keys
    scalars = _scalars(printed)
    assert not [value for value in scalars if isinstance(value, str) and "$" in value]
    for cents in (123456, 4321, 777, 987654):
        assert cents not in scalars and str(cents) not in json.dumps(printed["headline"])
    # The file beside it does carry the money; the fixture's figures are really there.
    assert json.loads(_target(root, sha).read_bytes())["scopes"]["nfl"]["overall"]["fees_cents"] == 1100 + 777


def test_the_headline_lists_blanks_by_date(tmp_path):
    rows = (_row(Points="0"), _row(Entry_Key="4000000002", Points="0", Place="900"),
            _row(Game_Type="Showdown Captain Mode", Entry_Key="4000000003", Contest_Key="100000002",
                 Contest_Date_EST="2026-09-17 20:15:00", Points="0"),
            _row(Entry_Key="4000000004", Contest_Key="100000004", Contest_Date_EST="2026-09-17 13:00:00",
                 Points="0"),
            _row(Entry_Key="4000000005", Contest_Key="100000005", Contest_Date_EST="2026-09-21 13:00:00"))
    root, sha = _intake(tmp_path, _history(*rows))
    outcome = _run(root, sha)
    nfl = outcome.headline["nfl"]
    assert nfl["blanks"] == 4 and nfl["blanks_by_date"] == {"2026-09-13": 2, "2026-09-17": 2}
    assert (nfl["entries"], nfl["slates"]) == (5, 4)
    assert set(outcome.headline) == {"nfl", "engine_era", "all_sport_check", "within_slate_trigger"}


def test_every_report_code_is_registered_p_in_results_report_and_emitted_by_this_module():
    registry = load_gate_registry()
    family = registry.families["results_report"]
    assert family.gate_class is GateClass.P
    assert {code for code, name in registry.codes.items() if name == "results_report"} == set(rr.REPORT_CODES)
    scanned = scanned_codes()
    for code in rr.REPORT_CODES:
        assert scanned.get(code) == frozenset({"results_report.py"}), code


DYNAMIC_KEYS = {"blanks_by_date", "left_out_rule_not_met", "parser_note_counts"}  # dates, sports, note kinds


def _named_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {key for name, item in value.items() if name not in DYNAMIC_KEYS
                             for key in _named_keys(item)}
    if isinstance(value, list):
        return {key for item in value for key in _named_keys(item)}
    return set()


def test_the_contract_names_every_written_key(tmp_path, capsys):
    capped = _row(Entry_Key="4000000077", Contest_Key="100000077", Contest_Date_EST="2026-09-20 13:00:00",
                  Places_Paid="1200")  # a capped row, so `notes` holds an entry
    root, sha = _intake(tmp_path, _history(*STANDARD, capped, *[_row(
        Entry_Key=str(4000000080 + day), Contest_Key=str(100000080 + day), Contest_Date_EST=f"2026-09-2{day} 13:00:00")
        for day in range(1, 6)]))
    code, printed = _command(capsys, "--source-sha256", sha, "--results-root", str(root))
    conflict = _run(root, sha, "2026-09-14")
    (root / "reports" / sha / "results_report.era-2026-09-14.w1.json").write_bytes(b"{}\n")
    refused_file = _run(root, sha, "2026-09-14").files
    payload = json.loads(_target(root, sha).read_bytes())
    assert code == 0 and conflict.status == "COMPLETE" and payload["notes"]
    assert payload["scopes"]["nfl"]["overall"]["uncertainty"]["percentile_excess"]["interval"] is not None
    text = (REPO / "docs" / "DATA_CONTRACTS.md").read_text(encoding="utf-8")
    section = text.split("\n## NFL results report, nfl_results_report_v1 (Session 71b)\n", 1)[1].split("\n## ", 1)[0]
    named = _named_keys(payload) | _named_keys(printed) | _named_keys(refused_file)
    missing = sorted(key for key in named if f"`{key}`" not in section)
    assert not missing, missing
    for code in rr.REPORT_CODES:
        assert code in section


def test_the_default_results_root_is_the_repository_data_results_folder():
    args = cli.build_parser().parse_args(["results-report", "--source-sha256", "0" * 64])
    assert Path(args.results_root) == REPO / "data" / "results" and args.engine_era_start is None
