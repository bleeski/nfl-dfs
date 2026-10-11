"""Session 69b: `nfl results-intake`, the write-once snapshot and the two normalized artifacts.

Every fixture is synthetic bytes built by Session 69's helpers; the account export itself carries winnings and never
enters git.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

from nfl_dfs import cli, cowork, entry_history
from nfl_dfs.contracts import GateClass
from nfl_dfs.gate_registry import load_gate_registry
from nfl_dfs.hashing import sha256_bytes
from tests.test_entry_history import BASE, COLUMNS, GOOD, HEADER, _history, _row
from tests.test_gate_registry import scanned_codes

REPO = Path(__file__).resolve().parents[1]
RAW = _history(*GOOD)
SHA = sha256_bytes(RAW)
EASTERN_TIME = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}-0[45]:00")


def _source(tmp_path: Path, raw: bytes = RAW, name: str = "history.csv") -> Path:
    source = tmp_path / "downloads" / name
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(raw)
    return source


def _intake(tmp_path: Path, raw: bytes = RAW, *, root: Path | None = None):
    root = root or tmp_path / "results"
    return entry_history.run_intake(_source(tmp_path, raw), root), root


def _paths(root: Path, sha: str = SHA) -> dict[str, Path]:
    folder = root / "normalized" / sha
    return {
        "snapshot": root / "inbox" / f"{sha}.csv",
        "entries": folder / "nfl_entries.w1.json",
        "summary": folder / "intake_summary.w1.json",
    }


def _states(outcome) -> dict[str, str]:
    return {name: report["state"] for name, report in outcome.files.items()}


def _tree(root: Path) -> list[str]:
    return sorted(path.relative_to(root).as_posix() for path in root.rglob("*")) if root.exists() else []


# ------------------------------------------------------------------------------------------ a first intake


def test_an_intake_writes_the_snapshot_and_both_artifacts(tmp_path):
    outcome, root = _intake(tmp_path)
    paths = _paths(root)

    assert (outcome.status, outcome.exit_code, outcome.problems) == ("COMPLETE", 0, ())
    assert _states(outcome) == {"snapshot": "WRITTEN", "entries": "WRITTEN", "summary": "WRITTEN"}
    assert {name: report["path"] for name, report in outcome.files.items()} == {
        name: str(path) for name, path in paths.items()}
    assert paths["snapshot"].read_bytes() == RAW
    assert _tree(root) == sorted([
        "inbox", f"inbox/{SHA}.csv", "normalized", f"normalized/{SHA}",
        f"normalized/{SHA}/nfl_entries.w1.json", f"normalized/{SHA}/intake_summary.w1.json"])

    # The summary file is exactly Session 69's summary, so its no-money, no-path and no-time tests cover it.
    history = entry_history.parse_entry_history(RAW)
    assert paths["summary"].read_bytes() == entry_history.canonical_bytes(
        entry_history.summary_payload(history, sha256=SHA, byte_count=len(RAW)))
    assert outcome.summary == entry_history.summary_payload(history, sha256=SHA, byte_count=len(RAW))


def test_the_entries_artifact_holds_the_nfl_rows_in_file_order_and_nothing_else(tmp_path):
    _outcome, root = _intake(tmp_path)
    raw = _paths(root)["entries"].read_bytes()
    payload = json.loads(raw)

    assert raw == entry_history.canonical_bytes(payload) and raw.isascii()
    assert set(payload) == {
        "schema_version", "contract", "writer", "sport", "source_sha256", "source_bytes", "nfl_rows", "entries",
        "does_not_establish"}
    assert {key: payload[key] for key in (
        "schema_version", "contract", "writer", "sport", "source_sha256", "source_bytes", "nfl_rows")} == {
        "schema_version": "nfl_dk_entry_history_entries_v1", "contract": "nfl_dk_entry_history_v1", "writer": "w1",
        "sport": "NFL", "source_sha256": SHA, "source_bytes": len(RAW), "nfl_rows": 3}
    assert payload["does_not_establish"] == list(entry_history.DOES_NOT_ESTABLISH)
    entries = payload["entries"]
    # The MLB row (source row 5) is counted in the summary and never normalized.
    assert [entry["source_row"] for entry in entries] == [2, 3, 4]
    assert "4000000004" not in raw.decode("ascii")
    first = entries[0]
    assert first == {
        "source_row": 2, "entry_key": "4000000001", "contest_key": "100000001", "game_type": "Classic",
        "entry_name": BASE["Entry"], "contest_start": "2026-09-13T13:00:00-04:00",
        "contest_start_text": "2026-09-13 13:00:00", "place": 12, "points_hundredths": 14236,
        "winnings_non_ticket_cents": 1000, "winnings_ticket_cents": 0, "contest_entries": 1000,
        "entry_fee_cents": 500, "prize_pool_cents": 450000, "places_paid": 200, "places_paid_above_entries": False,
    }
    assert all(set(entry) == set(first) for entry in entries)
    for entry in entries:
        assert None not in entry.values()
        assert EASTERN_TIME.fullmatch(entry["contest_start"])  # a real string, never a `default=str` repr


# ---------------------------------------------------------------------------------- determinism and mutation


def test_the_same_bytes_in_two_roots_give_byte_identical_files(tmp_path):
    root_a, root_b = tmp_path / "a", tmp_path / "b"
    first = entry_history.run_intake(_source(tmp_path / "one", name="history.csv"), root_a)
    second = entry_history.run_intake(_source(tmp_path / "two", name="draftkings-export.csv"), root_b)

    assert first.status == second.status == "COMPLETE"
    for name in ("snapshot", "entries", "summary"):
        assert _paths(root_a)[name].read_bytes() == _paths(root_b)[name].read_bytes(), name


def test_a_changed_entry_label_byte_changes_the_hash_and_only_entry_name(tmp_path):
    old_label, new_label = BASE["Entry"].encode(), BASE["Entry"].replace("Classic", "Classix").encode()
    changed = RAW.replace(old_label, new_label, 1)
    assert len(changed) == len(RAW) and changed != RAW

    _intake(tmp_path)
    outcome, root = _intake(tmp_path, changed)
    other = sha256_bytes(changed)

    assert outcome.status == "COMPLETE" and other != SHA
    assert sorted(path.name for path in (root / "normalized").iterdir()) == sorted([SHA, other])
    before = json.loads(_paths(root)["entries"].read_bytes())
    after = json.loads(_paths(root, other)["entries"].read_bytes())
    assert after["source_sha256"] == other
    assert [entry["entry_name"] for entry in after["entries"]][0] == new_label.decode()
    strip = ("entry_name",)
    assert [{k: v for k, v in e.items() if k not in strip} for e in before["entries"]] == [
        {k: v for k, v in e.items() if k not in strip} for e in after["entries"]]
    assert {k: v for k, v in before.items() if k not in ("entries", "source_sha256")} == {
        k: v for k, v in after.items() if k not in ("entries", "source_sha256")}
    summary_before = json.loads(_paths(root)["summary"].read_bytes())
    summary_after = json.loads(_paths(root, other)["summary"].read_bytes())
    assert summary_after == dict(summary_before, source_sha256=other)


def test_a_changed_place_byte_is_refused_and_writes_nothing(tmp_path):
    changed = RAW.replace(b",12,142.36,", b",1x,142.36,", 1)
    assert len(changed) == len(RAW) and changed != RAW

    outcome, root = _intake(tmp_path, changed)

    assert (outcome.status, outcome.exit_code) == ("REFUSED", 2)
    assert outcome.problems == ("ENTRY_HISTORY_PLACE_INVALID:row=2",)
    assert not root.exists()


# ------------------------------------------------------------------------------------------ a second run


def test_a_second_run_is_a_no_op_that_says_so(tmp_path, monkeypatch):
    _intake(tmp_path)
    root = tmp_path / "results"
    before = {name: path.stat() for name, path in _paths(root).items()}
    tree = _tree(root)

    def no_temporary(*_args, **_kwargs):
        raise AssertionError("a rerun writes no temporary file")

    monkeypatch.setattr(entry_history.tempfile, "mkstemp", no_temporary)
    outcome = entry_history.run_intake(_source(tmp_path), root)

    assert (outcome.status, outcome.exit_code, outcome.problems) == ("ALREADY_PRESENT", 0, ())
    assert set(_states(outcome).values()) == {"ALREADY_PRESENT"}
    for name, path in _paths(root).items():
        after = path.stat()
        assert (after.st_ino, after.st_mtime_ns) == (before[name].st_ino, before[name].st_mtime_ns), name
    assert _tree(root) == tree
    assert sorted(path.name for path in (root / "inbox").iterdir()) == [f"{SHA}.csv"]


def test_a_deleted_artifact_is_rebuilt_byte_for_byte(tmp_path):
    _outcome, root = _intake(tmp_path)
    entries = _paths(root)["entries"]
    original = entries.read_bytes()
    entries.unlink()

    outcome = entry_history.run_intake(_source(tmp_path), root)

    assert (outcome.status, outcome.exit_code) == ("COMPLETE", 0)
    assert _states(outcome) == {"snapshot": "ALREADY_PRESENT", "entries": "WRITTEN", "summary": "ALREADY_PRESENT"}
    assert entries.read_bytes() == original


# ------------------------------------------------------------------------------- never overwritten


def _flip(raw: bytes, at: int = 40) -> bytes:
    """One byte changed, the length kept: a damaged copy no size check can tell from the real one."""

    flipped = raw[:at] + bytes([raw[at] ^ 0x01]) + raw[at + 1:]
    assert len(flipped) == len(raw) and flipped != raw
    return flipped


@pytest.mark.parametrize("damage", ["truncated", "one_byte_flipped"])
def test_a_corrupt_snapshot_is_never_overwritten_and_stops_before_any_artifact(tmp_path, damage):
    root = tmp_path / "results"
    snapshot = _paths(root)["snapshot"]
    snapshot.parent.mkdir(parents=True)
    damaged = RAW[:-10] if damage == "truncated" else _flip(RAW)
    snapshot.write_bytes(damaged)

    outcome = entry_history.run_intake(_source(tmp_path), root)

    assert (outcome.status, outcome.exit_code) == ("REFUSED", 2)
    assert outcome.problems == ("ENTRY_HISTORY_SNAPSHOT_CORRUPT:file=snapshot",)
    assert _states(outcome) == {"snapshot": "REFUSED", "entries": "NOT_ATTEMPTED", "summary": "NOT_ATTEMPTED"}
    recovery = outcome.files["snapshot"]["recovery"]
    assert "never overwritten" in recovery and "delete it by hand" in recovery
    assert snapshot.read_bytes() == damaged
    assert not (root / "normalized").exists()


def test_a_directory_at_the_snapshot_name_is_refused_and_left_alone(tmp_path):
    root = tmp_path / "results"
    occupied = _paths(root)["snapshot"]
    occupied.mkdir(parents=True)
    (occupied / "kept.txt").write_bytes(b"kept")

    outcome = entry_history.run_intake(_source(tmp_path), root)

    assert outcome.problems == ("ENTRY_HISTORY_SNAPSHOT_CORRUPT:file=snapshot",)
    assert (occupied / "kept.txt").read_bytes() == b"kept"
    assert not (root / "normalized").exists()


@pytest.mark.parametrize("damage", ["replaced", "one_byte_flipped"])
@pytest.mark.parametrize("damaged", ["entries", "summary"])
def test_a_conflicting_artifact_is_never_overwritten_and_names_its_recovery(tmp_path, damaged, damage):
    _outcome, root = _intake(tmp_path)
    target = _paths(root)[damaged]
    other = b'{"damaged":true}\n' if damage == "replaced" else _flip(target.read_bytes())
    target.write_bytes(other)

    outcome = entry_history.run_intake(_source(tmp_path), root)

    assert (outcome.status, outcome.exit_code) == ("REFUSED", 2)
    assert outcome.problems == (f"ENTRY_HISTORY_ARTIFACT_CONFLICT:file={damaged}",)
    expected = {"snapshot": "ALREADY_PRESENT", "entries": "REFUSED", "summary": "NOT_ATTEMPTED"}
    if damaged == "summary":
        expected.update(entries="ALREADY_PRESENT", summary="REFUSED")
    assert _states(outcome) == expected
    recovery = outcome.files[damaged]["recovery"]
    assert "derived from the snapshot" in recovery and "writer version" in recovery
    assert target.read_bytes() == other
    assert _paths(root)["snapshot"].read_bytes() == RAW


# ------------------------------------------------------------------------------------------- refusals


@pytest.mark.parametrize(
    ("raw", "problems"),
    [
        (_history(*GOOD, _row(Entry_Key="4000000001")), ("ENTRY_HISTORY_ENTRY_KEY_DUPLICATE:row=6:first=2",)),
        (_history(_row(Sport="MLB")), ("ENTRY_HISTORY_NO_NFL_ROWS",)),
        (_history(), ("ENTRY_HISTORY_NO_ROWS",)),
        (b"", ("ENTRY_HISTORY_FILE_EMPTY",)),
    ],
    ids=["duplicate_entry", "no_nfl_rows", "header_only", "empty"],
)
def test_a_refused_file_writes_nothing_and_names_every_problem(tmp_path, raw, problems):
    outcome, root = _intake(tmp_path, raw)

    assert (outcome.status, outcome.exit_code, outcome.problems) == ("REFUSED", 2, problems)
    assert set(_states(outcome).values()) == {"NOT_ATTEMPTED"}
    assert {report["path"] for report in outcome.files.values()} == {None}
    assert outcome.summary is None and outcome.source_sha256 == sha256_bytes(raw)
    assert not root.exists()


def test_an_unreadable_path_names_its_exception_class_and_nothing_else(tmp_path):
    root = tmp_path / "results"
    missing = tmp_path / "secret-folder-name" / "history.csv"

    outcome = entry_history.run_intake(missing, root)

    assert (outcome.status, outcome.exit_code) == ("REFUSED", 2)
    assert outcome.problems == ("ENTRY_HISTORY_UNREADABLE:exception=FileNotFoundError",)
    assert outcome.source_sha256 is None
    assert "secret-folder-name" not in json.dumps(outcome.as_dict())
    assert not root.exists()


def test_a_file_too_large_carries_no_hash_of_its_prefix(tmp_path, monkeypatch):
    monkeypatch.setattr(entry_history, "MAX_BYTES", len(RAW) - 1)
    outcome, root = _intake(tmp_path)

    assert outcome.problems == ("ENTRY_HISTORY_FILE_TOO_LARGE",)
    assert outcome.source_sha256 is None and not root.exists()

    monkeypatch.setattr(entry_history, "MAX_BYTES", len(RAW))
    outcome, _root = _intake(tmp_path)
    assert (outcome.status, outcome.source_sha256) == ("COMPLETE", SHA)


SALARY_HEADER = "Position,Name + ID,Name,ID,Roster Position,Salary,Game Info,TeamAbbrev,AvgPointsPerGame,Status"
ENTRIES_HEADER = "Entry ID,Contest Name,Contest ID,Entry Fee,QB,RB,RB,WR,WR,WR,TE,FLEX,DST"


@pytest.mark.parametrize(
    ("header", "kind"),
    [
        (SALARY_HEADER, "salary_csv"),
        (ENTRIES_HEADER, "entry_csv"),
        (",".join(COLUMNS[1::-1] + COLUMNS[2:]), "none"),  # the export's header with two columns swapped
    ],
    ids=["dk_salaries", "dk_entries", "reordered_export"],
)
def test_another_file_kind_is_refused_and_named(tmp_path, header, kind):
    assert header != HEADER
    raw = (header + "\r\n" + ",".join("x" for _ in header.split(",")) + "\r\n").encode()

    outcome, root = _intake(tmp_path, raw)

    assert (outcome.status, outcome.exit_code) == ("REFUSED", 2)
    (problem,) = outcome.problems
    assert problem.startswith("ENTRY_HISTORY_HEADER_INVALID:") and problem.endswith(f":classified_as={kind}")
    assert not root.exists()


@pytest.mark.parametrize("error", [cowork.CoworkInputError("undecodable"), PermissionError("locked")],
                         ids=["cowork_input_error", "os_error"])
def test_a_classification_that_fails_is_named_unreadable(tmp_path, monkeypatch, error):
    def failing(_path):
        raise error

    monkeypatch.setattr(cowork, "classify_csv", failing)
    outcome, _root = _intake(tmp_path, (SALARY_HEADER + "\r\n").encode())

    (problem,) = outcome.problems
    assert problem.endswith(":classified_as=unreadable")


# ------------------------------------------------------------------------------------------- write failures


def test_a_write_failure_is_named_and_every_file_reports_its_state(tmp_path, monkeypatch):
    real_link = os.link

    def no_link_for_entries(source, target):
        if str(target).endswith("nfl_entries.w1.json"):
            raise PermissionError("no hard links here")
        return real_link(source, target)

    monkeypatch.setattr(entry_history.os, "link", no_link_for_entries)
    outcome, root = _intake(tmp_path)

    assert (outcome.status, outcome.exit_code) == ("WRITE_FAILED", 2)
    assert outcome.problems == ("ENTRY_HISTORY_WRITE_FAILED:file=entries:exception=PermissionError",)
    assert _states(outcome) == {"snapshot": "WRITTEN", "entries": "WRITE_FAILED", "summary": "NOT_ATTEMPTED"}
    assert list((root / "normalized" / SHA).iterdir()) == []  # no temporary left behind
    assert "no hard links here" not in json.dumps(outcome.as_dict())

    monkeypatch.setattr(entry_history.os, "link", real_link)
    again = entry_history.run_intake(_source(tmp_path), root)
    assert _states(again) == {"snapshot": "ALREADY_PRESENT", "entries": "WRITTEN", "summary": "WRITTEN"}


def test_bytes_that_differ_after_the_link_are_removed_and_named(tmp_path, monkeypatch):
    real_link = os.link

    def damaging_link(source, target):
        real_link(source, target)
        Path(target).write_bytes(b"not the bytes")  # the same file, through the new link

    monkeypatch.setattr(entry_history.os, "link", damaging_link)
    outcome, root = _intake(tmp_path)

    assert outcome.status == "WRITE_FAILED"
    assert outcome.problems == ("ENTRY_HISTORY_WRITE_FAILED:file=snapshot:exception=WrittenBytesDiffer",)
    assert list((root / "inbox").iterdir()) == []


def test_a_file_that_takes_the_name_after_the_link_is_never_deleted(tmp_path, monkeypatch):
    real_link = os.link

    def replaced_after_link(source, target):
        real_link(source, target)
        stranger = Path(target).with_name("stranger")
        stranger.write_bytes(b"someone else's bytes")
        os.replace(stranger, target)

    monkeypatch.setattr(entry_history.os, "link", replaced_after_link)
    outcome, root = _intake(tmp_path)

    assert outcome.problems == ("ENTRY_HISTORY_WRITE_FAILED:file=snapshot:exception=WrittenBytesDiffer",)
    assert _paths(root)["snapshot"].read_bytes() == b"someone else's bytes"


@pytest.mark.parametrize("arrived", ["other_bytes", "same_bytes"])
def test_a_name_that_appears_between_the_check_and_the_link_is_never_replaced(tmp_path, monkeypatch, arrived):
    other = _flip(RAW)

    def raced(_source, target):
        Path(target).write_bytes(other if arrived == "other_bytes" else RAW)
        raise FileExistsError(target)

    monkeypatch.setattr(entry_history.os, "link", raced)
    outcome, root = _intake(tmp_path)
    snapshot = _paths(root)["snapshot"]

    if arrived == "other_bytes":
        assert (outcome.status, outcome.problems) == ("REFUSED", ("ENTRY_HISTORY_SNAPSHOT_CORRUPT:file=snapshot",))
        assert snapshot.read_bytes() == other
        assert not (root / "normalized").exists()
    else:
        assert outcome.files["snapshot"]["state"] == "ALREADY_PRESENT"
        assert snapshot.read_bytes() == RAW
    assert sorted(path.name for path in (root / "inbox").iterdir()) == [f"{SHA}.csv"]


def test_a_symlink_at_the_name_is_refused_even_when_it_reaches_the_same_bytes(tmp_path, monkeypatch):
    # A real symlink needs a privilege on Windows; the check reads `is_symlink`, so a patched one tests the same branch
    # on every platform with no skip.
    root = tmp_path / "results"
    snapshot = _paths(root)["snapshot"]
    snapshot.parent.mkdir(parents=True)
    snapshot.write_bytes(RAW)
    real_is_symlink = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda self: self.name == snapshot.name or real_is_symlink(self))

    outcome = entry_history.run_intake(_source(tmp_path), root)

    assert outcome.problems == ("ENTRY_HISTORY_SNAPSHOT_CORRUPT:file=snapshot",)
    assert snapshot.read_bytes() == RAW


def test_a_temporary_file_that_cannot_be_deleted_never_hides_the_outcome(tmp_path, monkeypatch):
    real_unlink = Path.unlink

    def held_by_a_scanner(self, missing_ok=False):
        if self.name.endswith(".tmp"):
            raise PermissionError("held")
        return real_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", held_by_a_scanner)
    outcome, root = _intake(tmp_path)

    assert (outcome.status, outcome.problems) == ("COMPLETE", ())
    assert set(_states(outcome).values()) == {"WRITTEN"}
    assert _paths(root)["snapshot"].read_bytes() == RAW


# ------------------------------------------------------------------------------------- git, stdout, registry


def test_every_results_path_is_gitignored():
    paths = [f"data/results/inbox/{SHA}.csv", f"data/results/normalized/{SHA}/nfl_entries.w1.json",
             f"data/results/normalized/{SHA}/intake_summary.w1.json"]
    for path in paths:
        ignored = subprocess.run(("git", "check-ignore", "--quiet", "--no-index", path), cwd=REPO,
                                 capture_output=True, text=True, timeout=30, check=False)
        assert ignored.returncode == 0, path


def test_the_command_exits_0_0_2_and_stdout_carries_no_money(tmp_path, capsys):
    root = tmp_path / "results"
    source = _source(tmp_path)
    assert b"$" in RAW  # the fixture does carry money, so the checks below mean something

    printed = []
    for history in (source, source, _source(tmp_path, RAW.replace(b",12,142.36,", b",1x,142.36,"), "bad.csv")):
        code = cli.main(["results-intake", "--history", str(history), "--results-root", str(root)])
        printed.append((code, capsys.readouterr().out))

    assert [code for code, _out in printed] == [0, 0, 2]
    assert [json.loads(out)["status"] for _code, out in printed] == ["COMPLETE", "ALREADY_PRESENT", "REFUSED"]
    first = json.loads(printed[0][1])
    assert first["files"] == {name: {"path": str(path), "state": "WRITTEN"} for name, path in _paths(root).items()}
    assert first["summary"] == json.loads(_paths(root)["summary"].read_bytes())
    assert (first["source_sha256"], first["exit_code"], first["problems"]) == (SHA, 0, [])
    for _code, out in printed:
        assert "$" not in out and "_cents" not in out
    summary = _paths(root)["summary"].read_bytes()
    assert b"$" not in summary and b"_cents" not in summary


def test_the_default_results_root_is_the_repository_data_results_folder():
    args = cli.build_parser().parse_args(["results-intake", "--history", "x.csv"])
    assert Path(args.results_root) == REPO / "data" / "results"


def test_every_intake_code_is_registered_p_in_entry_history_and_emitted_by_this_module():
    registry = load_gate_registry()
    assert registry.families["entry_history"].gate_class is GateClass.P
    family = {code for code, name in registry.codes.items() if name == "entry_history"}
    assert family == set(entry_history.PARSE_CODES) | set(entry_history.INTAKE_CODES)
    scanned = scanned_codes()
    for code in entry_history.INTAKE_CODES:
        assert scanned.get(code) == frozenset({"entry_history.py"}), code
