"""Session 12, review V12: `late-swap` refuses an `--as-of` that disagrees with the release clock.

A stale `--as-of` makes locked slots look replaceable, and the byte audit audits against the same
authorization, so it would pass a file that edits them. The refusal runs inside `govern_late_swap`
before any run directory, hash or read, takes the clock as a required argument, and the CLI always
fills it from `evidence.release_clock`. There is no flag that turns the check off.
"""

from __future__ import annotations

import ast
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

import nfl_dfs.cli as cli_module
import nfl_dfs.late_swap as late_swap_module
from nfl_dfs.cli import main
from nfl_dfs.late_swap import (
    AS_OF_CLOCK_TOLERANCE,
    LateSwapClockError,
    LateSwapRunError,
    govern_late_swap,
)

from .conftest import FIXTURE_ROOT
from .test_governed_late_swap import AS_OF, _case

REPO = Path(__file__).resolve().parents[1]
ONE_MICROSECOND = timedelta(microseconds=1)


def _govern_with_clock(case, clock_now: datetime, *, run_id: str = "clock-case", as_of: datetime = AS_OF):
    return govern_late_swap(
        run_id=run_id,
        salaries_path=case["salaries"],
        current_entries_path=case["current"],
        prior_manifest_path=case["prior_manifest"],
        prior_assignments_path=case["prior_assignments"],
        proposed_assignments_path=case["proposed_assignments"],
        eligibility_evidence_path=case["eligibility"],
        inactive_reports_path=case["inactive"],
        output_directory=case["output_dir"],
        as_of=as_of,
        clock=lambda: clock_now,
    )


def test_the_registered_tolerance_is_120_seconds() -> None:
    """Ben's threshold to set; the constant and its reason live in late_swap.py."""

    assert AS_OF_CLOCK_TOLERANCE == timedelta(seconds=120)


@pytest.mark.parametrize(
    "offset",
    [timedelta(0), timedelta(seconds=-60), timedelta(seconds=60)],
    ids=["at-the-clock", "a-minute-early", "a-minute-late"],
)
def test_an_as_of_inside_the_tolerance_ships(tmp_path: Path, classic_slate, classic_entries, offset) -> None:
    case = _case(tmp_path, classic_slate, classic_entries)
    manifest, _ = _govern_with_clock(case, AS_OF + offset)
    assert manifest.status == "CERTIFIED", manifest.blockers
    assert Path(manifest.output_path or "").exists()


@pytest.mark.parametrize("sign", [1, -1], ids=["clock-ahead", "clock-behind"])
def test_an_as_of_exactly_at_the_tolerance_ships(tmp_path: Path, classic_slate, classic_entries, sign) -> None:
    case = _case(tmp_path, classic_slate, classic_entries)
    manifest, _ = _govern_with_clock(case, AS_OF + sign * AS_OF_CLOCK_TOLERANCE)
    assert manifest.status == "CERTIFIED", manifest.blockers


@pytest.mark.parametrize(
    "offset",
    [
        AS_OF_CLOCK_TOLERANCE + ONE_MICROSECOND,
        -(AS_OF_CLOCK_TOLERANCE + ONE_MICROSECOND),
        timedelta(hours=1),
        -timedelta(hours=1),
    ],
    ids=["just-past-stale", "just-past-future", "an-hour-stale", "an-hour-future"],
)
def test_an_as_of_past_the_tolerance_is_refused_by_name_before_any_read_or_write(
    tmp_path: Path, monkeypatch, offset
) -> None:
    def must_not_hash(*_args, **_kwargs):
        raise AssertionError("an input was hashed before the clock check")

    monkeypatch.setattr(late_swap_module, "sha256_file", must_not_hash)
    output_directory = tmp_path / "out"
    missing = tmp_path / "missing.csv"
    with pytest.raises(LateSwapClockError, match=r"^LATE_SWAP_AS_OF_CLOCK_MISMATCH:") as caught:
        govern_late_swap(
            run_id="stale-as-of",
            salaries_path=missing,
            current_entries_path=missing,
            prior_manifest_path=missing,
            prior_assignments_path=missing,
            proposed_assignments_path=missing,
            eligibility_evidence_path=missing,
            inactive_reports_path=missing,
            output_directory=output_directory,
            as_of=AS_OF,
            clock=lambda: AS_OF + offset,
        )
    assert isinstance(caught.value, LateSwapRunError)
    assert not output_directory.exists()


def test_a_clock_that_is_not_timezone_aware_is_refused_by_the_same_code(tmp_path: Path) -> None:
    with pytest.raises(LateSwapClockError, match=r"^LATE_SWAP_AS_OF_CLOCK_MISMATCH:.*timezone"):
        govern_late_swap(
            run_id="naive-clock",
            salaries_path=tmp_path / "a.csv",
            current_entries_path=tmp_path / "a.csv",
            prior_manifest_path=tmp_path / "a.csv",
            prior_assignments_path=tmp_path / "a.csv",
            proposed_assignments_path=tmp_path / "a.csv",
            eligibility_evidence_path=tmp_path / "a.csv",
            inactive_reports_path=tmp_path / "a.csv",
            output_directory=tmp_path / "out",
            as_of=AS_OF,
            clock=lambda: datetime(2026, 9, 13, 15, 0, 0),
        )
    assert not (tmp_path / "out").exists()


def test_a_naive_as_of_keeps_its_own_refusal_and_is_not_a_clock_error(tmp_path: Path) -> None:
    with pytest.raises(LateSwapRunError, match="--as-of must include a timezone") as caught:
        govern_late_swap(
            run_id="naive-as-of",
            salaries_path=tmp_path / "a.csv",
            current_entries_path=tmp_path / "a.csv",
            prior_manifest_path=tmp_path / "a.csv",
            prior_assignments_path=tmp_path / "a.csv",
            proposed_assignments_path=tmp_path / "a.csv",
            eligibility_evidence_path=tmp_path / "a.csv",
            inactive_reports_path=tmp_path / "a.csv",
            output_directory=tmp_path / "out",
            as_of=datetime(2026, 9, 13, 15, 0, 0),
            clock=lambda: AS_OF,
        )
    assert not isinstance(caught.value, LateSwapClockError)


def _cli_args(case, run_id: str, as_of: str) -> list[str]:
    return [
        "late-swap",
        "--run-id", run_id,
        "--salaries", str(FIXTURE_ROOT / "DKSalaries Salary CSV Classic.csv"),
        "--current-entries", str(case["current"]),
        "--prior-manifest", str(case["prior_manifest"]),
        "--prior-assignments", str(case["prior_assignments"]),
        "--proposed-assignments", str(case["proposed_assignments"]),
        "--eligibility-evidence", str(case["eligibility"]),
        "--inactive-reports", str(case["inactive"]),
        "--output-dir", str(case["output_dir"]),
        "--as-of", as_of,
    ]


def test_the_cli_refuses_a_stale_as_of_with_exit_2_and_the_rerun_hint(
    tmp_path: Path, classic_slate, classic_entries, capsys
) -> None:
    """The real release clock is years past the fixture's `AS_OF`, so this is a stale timestamp."""

    case = _case(tmp_path, classic_slate, classic_entries)
    code = main(_cli_args(case, "cli-stale", AS_OF.isoformat()))
    payload = json.loads(capsys.readouterr().out)
    assert code == 2
    assert payload["status"] == "DO_NOT_UPLOAD"
    assert payload["blockers"][0].startswith("LATE_SWAP_AS_OF_CLOCK_MISMATCH:")
    assert payload["manifest"] is None and payload["output_path"] is None
    assert "--as-of" in payload["next_action"] and "120" in payload["next_action"]
    assert not (case["output_dir"] / "cli-stale").exists()


def test_the_cli_accepts_an_as_of_inside_the_tolerance(
    tmp_path: Path, classic_slate, classic_entries, monkeypatch, capsys
) -> None:
    case = _case(tmp_path, classic_slate, classic_entries)
    monkeypatch.setattr("nfl_dfs.cli.release_clock", lambda: AS_OF + timedelta(seconds=30))
    code = main(_cli_args(case, "cli-fresh", AS_OF.isoformat()))
    payload = json.loads(capsys.readouterr().out)
    assert code == 0, payload["blockers"]
    assert payload["status"] == "CERTIFIED"
    assert Path(payload["output_path"]).exists()


def _callers_of(name: str):
    """Every call of `name` under src/ and scripts/, with the file and function that holds it."""

    found: list[tuple[str, str, ast.Call]] = []
    for base in (REPO / "src" / "nfl_dfs", REPO / "scripts"):
        for path in sorted(base.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                callee = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
                if callee != name:
                    continue
                holder = node
                while holder in parents and not isinstance(holder, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    holder = parents[holder]
                found.append((path.name, getattr(holder, "name", "<module>"), node))
    return found


def test_the_cli_is_the_only_caller_and_always_passes_the_release_clock() -> None:
    """No flag turns the check off: the one production call passes `clock=release_clock`.

    `release_clock` is the module-global name, evaluated at call time, so a test that pins the clock
    patches `nfl_dfs.cli.release_clock`, and a caller that omitted the argument would not run at all.
    """

    callers = _callers_of("govern_late_swap")
    assert [(file, function) for file, function, _ in callers] == [("cli.py", "command_late_swap")]
    call = callers[0][2]
    clock = [keyword.value for keyword in call.keywords if keyword.arg == "clock"]
    assert len(clock) == 1 and isinstance(clock[0], ast.Name) and clock[0].id == "release_clock"
    tree = ast.parse((REPO / "src" / "nfl_dfs" / "cli.py").read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "evidence"
        for alias in node.names
    }
    assert "release_clock" in imported
    assert cli_module.release_clock.__module__ == "nfl_dfs.evidence"
