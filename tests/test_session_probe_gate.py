"""Acceptance for the pre-run session probe.

The statement under test: `run-slate` reports what this session can reach before
the run spends its window discovering it, and the probe can never be the reason
a run fails. `scripts/session_probe.py` already answered the question in three
seconds; on 2026-09-20 two slates were lost because nothing ran it.

No network here. The probe is exercised by pointing the helper at stub scripts.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nfl_dfs import cli


@pytest.fixture(autouse=True)
def _probe_enabled(monkeypatch):
    # conftest switches the probe off for the whole suite. These tests are the
    # ones that want it on.
    monkeypatch.delenv(cli.SESSION_PROBE_SKIP_ENV, raising=False)


def _stub(tmp_path: Path, body: str) -> Path:
    script = tmp_path / "stub_probe.py"
    script.write_text(body, encoding="utf-8")
    return script


def test_the_skip_environment_variable_turns_the_probe_off(monkeypatch) -> None:
    monkeypatch.setenv(cli.SESSION_PROBE_SKIP_ENV, "1")
    assert cli._session_probe(None) is None


def test_a_reachable_session_reports_that_it_can_complete_a_run(tmp_path, monkeypatch) -> None:
    script = _stub(
        tmp_path,
        "import json\n"
        "print(json.dumps({'verdict': 'CAN_COMPLETE_A_RUN', 'blocking_hosts': []}))\n",
    )
    monkeypatch.setattr(cli, "SESSION_PROBE_SCRIPT", script)
    report = cli._session_probe(None)
    assert report is not None
    assert report["verdict"] == "CAN_COMPLETE_A_RUN"


def test_a_blocked_host_is_reported_with_the_gate_it_feeds(tmp_path, monkeypatch, capsys) -> None:
    script = _stub(
        tmp_path,
        "import json, sys\n"
        "print(json.dumps({'verdict': 'CANNOT_COMPLETE_A_RUN', 'blocking_hosts': ["
        "{'host': 'api.weather.gov', 'gate': 'per-game Classic weather captures',"
        " 'detail': 'EGRESS_BLOCKED'}]}))\n"
        "sys.exit(2)\n",
    )
    monkeypatch.setattr(cli, "SESSION_PROBE_SCRIPT", script)
    report = cli._session_probe(None)
    assert report is not None
    # Exit code 2 is the probe's answer, not a failure of this helper.
    assert report["verdict"] == "CANNOT_COMPLETE_A_RUN"
    cli._announce_session_probe(report)
    printed = capsys.readouterr().err
    assert "CANNOT_COMPLETE_A_RUN" in printed
    assert "api.weather.gov" in printed
    assert "per-game Classic weather captures" in printed


def test_a_clear_verdict_says_nothing(tmp_path, monkeypatch, capsys) -> None:
    cli._announce_session_probe({"verdict": "CAN_COMPLETE_A_RUN"})
    assert capsys.readouterr().err == ""


def test_a_probe_that_crashes_never_fails_the_run(tmp_path, monkeypatch) -> None:
    script = _stub(tmp_path, "raise SystemExit('boom')\n")
    monkeypatch.setattr(cli, "SESSION_PROBE_SCRIPT", script)
    report = cli._session_probe(None)
    assert report == {
        "verdict": "PROBE_UNAVAILABLE",
        "detail": "JSONDecodeError:Expecting value: line 1 column 1 (char 0)",
    }


def test_a_missing_probe_script_is_reported_not_read_as_good_news(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(cli, "SESSION_PROBE_SCRIPT", tmp_path / "absent.py")
    report = cli._session_probe(None)
    assert report == {"verdict": "PROBE_UNAVAILABLE", "detail": "script missing"}


def test_non_object_output_is_refused(tmp_path, monkeypatch) -> None:
    script = _stub(tmp_path, "print('[]')\n")
    monkeypatch.setattr(cli, "SESSION_PROBE_SCRIPT", script)
    report = cli._session_probe(None)
    assert report == {
        "verdict": "PROBE_UNAVAILABLE",
        "detail": "report was not an object",
    }


def test_the_salary_csv_is_passed_through_for_the_lock_clock(tmp_path, monkeypatch) -> None:
    script = _stub(
        tmp_path,
        "import json, sys\n"
        "print(json.dumps({'verdict': 'CAN_COMPLETE_A_RUN', 'argv': sys.argv[1:]}))\n",
    )
    monkeypatch.setattr(cli, "SESSION_PROBE_SCRIPT", script)
    report = cli._session_probe("/tmp/DKSalaries.csv")
    assert report is not None
    assert report["argv"] == ["--json", "--salaries", "/tmp/DKSalaries.csv"]


def test_the_real_probe_script_is_where_the_run_expects_it() -> None:
    # The helper degrades gracefully when the script is gone, which would make a
    # rename silently stop probing. This is the test that notices.
    assert cli.SESSION_PROBE_SCRIPT.is_file()
    # Compare path parts, not a joined string. Windows renders this path with
    # backslashes, so a "scripts/session_probe.py" suffix test fails there for a
    # reason that has nothing to do with the rename this test exists to catch.
    assert cli.SESSION_PROBE_SCRIPT.parts[-2:] == ("scripts", "session_probe.py")
