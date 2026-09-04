from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from openpyxl import load_workbook

from nfl_dfs import cli
from nfl_dfs.cowork import (
    CoworkInputError,
    CoworkRunRequest,
    discover_csv_inputs,
    required_next_inputs,
)


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "supplied"


def _attachment_pair(directory: Path) -> tuple[Path, Path]:
    salary = directory / "attachment-2.csv"
    entries = directory / "whatever-the-browser-called-this.csv"
    shutil.copyfile(FIXTURE_ROOT / "DKSalaries Salary CSV Classic.csv", salary)
    shutil.copyfile(FIXTURE_ROOT / "DKEntries CSV.csv", entries)
    return salary, entries


def test_cowork_rejects_nonfinite_economics_and_unsafe_run_ids() -> None:
    with pytest.raises(CoworkInputError, match="non-negative JSON number"):
        CoworkRunRequest.from_mapping({"advertised_prize_value": float("nan")})
    with pytest.raises(ValueError, match="run_id"):
        cli._resolved_run_id("../../outside", "slate")


def test_discovers_uploaded_csvs_by_schema_not_filename(tmp_path: Path) -> None:
    salary, entries = _attachment_pair(tmp_path)
    (tmp_path / "notes.csv").write_text("not,a,known,schema\n1,2,3,4\n", encoding="utf-8")

    discovered = discover_csv_inputs(tmp_path)

    assert discovered.classified == {
        "entry_csv": entries.resolve(),
        "salary_csv": salary.resolve(),
    }
    assert discovered.unclassified_csvs == ((tmp_path / "notes.csv").resolve(),)


def test_duplicate_schema_is_rejected_as_ambiguous(tmp_path: Path) -> None:
    salary, _ = _attachment_pair(tmp_path)
    shutil.copyfile(salary, tmp_path / "second-salary.csv")

    with pytest.raises(CoworkInputError, match="ambiguous Cowork CSV inputs"):
        discover_csv_inputs(tmp_path)


def test_request_resolves_relative_paths_and_rejects_unknown_fields(tmp_path: Path) -> None:
    salary, entries = _attachment_pair(tmp_path)
    request_path = tmp_path / "request.json"
    request_path.write_text(
        json.dumps(
            {
                "schema_version": "nfl_cowork_run_request_v1",
                "salary_csv": salary.name,
                "entry_csv": entries.name,
            }
        ),
        encoding="utf-8",
    )
    request = CoworkRunRequest.from_json(request_path)
    assert request.salary_csv == str(salary.resolve())
    assert request.entry_csv == str(entries.resolve())

    with pytest.raises(CoworkInputError, match="unknown Cowork request fields"):
        CoworkRunRequest.from_mapping({"invented_field": "silently unsafe"})


def test_request_rejects_traversal_and_external_absolute_paths(tmp_path: Path) -> None:
    attachments = tmp_path / "attachments"
    attachments.mkdir()
    external = tmp_path / "external.csv"
    external.write_text("outside\n", encoding="utf-8")

    with pytest.raises(CoworkInputError, match="must not contain traversal"):
        CoworkRunRequest.from_mapping(
            {"salary_csv": "../external.csv"}, base_dir=attachments
        )
    with pytest.raises(CoworkInputError, match="outside the supplied attachment"):
        CoworkRunRequest.from_mapping(
            {"salary_csv": str(external)}, base_dir=attachments
        )


def test_request_rejects_symlink_escape_when_supported(tmp_path: Path) -> None:
    attachments = tmp_path / "attachments"
    attachments.mkdir()
    external = tmp_path / "external.csv"
    external.write_text("outside\n", encoding="utf-8")
    link = attachments / "linked.csv"
    try:
        link.symlink_to(external)
    except OSError as exc:
        pytest.skip(f"symlink creation is unavailable on this platform: {exc}")

    with pytest.raises(CoworkInputError, match="outside the supplied attachment"):
        CoworkRunRequest.from_mapping(
            {"salary_csv": link.name}, base_dir=attachments
        )


@pytest.mark.skipif(os.name != "nt", reason="Windows junction behavior")
def test_request_rejects_windows_junction_escape(tmp_path: Path) -> None:
    attachments = tmp_path / "attachments"
    external = tmp_path / "external"
    attachments.mkdir()
    external.mkdir()
    (external / "outside.csv").write_text("outside\n", encoding="utf-8")
    junction = attachments / "linked"
    created = subprocess.run(
        ["cmd.exe", "/d", "/c", "mklink", "/J", str(junction), str(external)],
        check=False,
        capture_output=True,
        text=True,
    )
    if created.returncode != 0:
        pytest.fail(f"could not create Windows junction: {created.stderr or created.stdout}")
    try:
        with pytest.raises(CoworkInputError, match="outside the supplied attachment"):
            CoworkRunRequest.from_mapping(
                {"salary_csv": "linked/outside.csv"}, base_dir=attachments
            )
    finally:
        os.rmdir(junction)


def test_external_request_path_is_rejected_before_snapshot_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    attachments = tmp_path / "attachments"
    attachments.mkdir()
    entries = attachments / "entries.csv"
    shutil.copyfile(FIXTURE_ROOT / "DKEntries CSV.csv", entries)
    external_salary = tmp_path / "outside-salary.csv"
    shutil.copyfile(
        FIXTURE_ROOT / "DKSalaries Salary CSV Classic.csv", external_salary
    )
    request_path = attachments / "request.json"
    request_path.write_text(
        json.dumps(
            {
                "schema_version": "nfl_cowork_run_request_v1",
                "salary_csv": str(external_salary),
                "entry_csv": entries.name,
            }
        ),
        encoding="utf-8",
    )
    runs = tmp_path / "runs"
    monkeypatch.setattr(cli, "DEFAULT_RUNS_DIR", runs)
    args = argparse.Namespace(
        input_dir=str(attachments),
        request=str(request_path),
        salaries=None,
        entries=None,
        label="external-path",
        run_id="external-path",
        output_dir=str(tmp_path / "outputs"),
    )

    with pytest.raises(CoworkInputError, match="outside the supplied attachment"):
        cli.command_cowork_run(args)
    assert not runs.exists()


def test_two_file_request_names_every_remaining_hard_input() -> None:
    blockers = required_next_inputs(CoworkRunRequest())
    assert any(value.startswith("CONTEST_PAYOUT_REQUIRED:") for value in blockers)
    assert any(value.startswith("ADVERTISED_PRIZE_VALUE_REQUIRED:") for value in blockers)
    assert any(value.startswith("FIELD_SIZE_REQUIRED:") for value in blockers)
    assert any(value.startswith("MODEL_INPUTS_REQUIRED:") for value in blockers)
    assert any(value.startswith("SOURCE_LEDGER_REQUIRED:") for value in blockers)
    assert any(value.startswith("OFFICIAL_STATUS_REQUIRED:") for value in blockers)


def test_cowork_two_file_run_snapshots_and_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    attachments = tmp_path / "attachments"
    attachments.mkdir()
    _attachment_pair(attachments)
    runs = tmp_path / "runs"
    outputs = tmp_path / "outputs"
    monkeypatch.setattr(cli, "DEFAULT_RUNS_DIR", runs)
    monkeypatch.setattr(cli, "DEFAULT_OUTPUT_DIR", outputs)
    args = argparse.Namespace(
        input_dir=str(attachments),
        request=None,
        salaries=None,
        entries=None,
        label="cowork-fixture",
        run_id="cowork-fixture",
        output_dir=str(outputs),
    )

    assert cli.command_cowork_run(args) == 2

    request_path = runs / "cowork-fixture" / "run_request.json"
    report_path = outputs / "cowork-fixture" / "cowork_run.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    request = json.loads(request_path.read_text(encoding="utf-8"))
    assert report["status"] == "DO_NOT_UPLOAD"
    assert report["FILE_VALID"] is False
    assert report["EVIDENCE_STATE"] == "UNKNOWN"
    assert report["MODEL_STATUS"] == "UNVALIDATED"
    assert report["RELEASE_DECISION"] == "DO_NOT_UPLOAD"
    assert report["certification_basis"] == "MODEL_ASSISTED"
    assert report["stage"] == "RECONCILED"
    assert report["authorized_entries"] == 2
    assert Path(request["salary_csv"]).parent == runs / "cowork-fixture" / "inputs"
    assert Path(request["entry_csv"]).parent == runs / "cowork-fixture" / "inputs"
    assert not list(outputs.rglob("DK_UPLOAD_*.csv"))
    workbook = load_workbook(report["review_workbook"], data_only=False)
    assert workbook["Upload"]["B4"].value == "DO_NOT_UPLOAD"
    assert workbook["Upload"]["B5"].value is False
    assert workbook["Upload"]["B6"].value == "UNKNOWN"
    assert workbook["Upload"]["B7"].value == "UNVALIDATED"
    assert workbook["Upload"]["B8"].value == "DO_NOT_UPLOAD"
    assert workbook["Upload"]["B9"].value == "MODEL_ASSISTED"
    assert workbook["Run Control"]["B6"].value == request["salary_csv"]
    assert workbook["Run Control"]["B7"].value == request["entry_csv"]


class _PassingDoctor:
    pass_status = True

    @staticmethod
    def to_json() -> str:
        return '{"pass": true}'


def test_cowork_build_failure_writes_machine_result_and_diagnostic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    attachments = tmp_path / "attachments"
    attachments.mkdir()
    _attachment_pair(attachments)
    runs = tmp_path / "runs"
    outputs = tmp_path / "outputs"
    monkeypatch.setattr(cli, "DEFAULT_RUNS_DIR", runs)
    monkeypatch.setattr(cli, "DEFAULT_OUTPUT_DIR", outputs)
    monkeypatch.setattr(cli, "doctor", lambda _root: _PassingDoctor())
    monkeypatch.setattr(cli, "_cowork_core_blockers", lambda _request: ())

    def fail_build(_args):
        raise KeyError("missing projection member")

    monkeypatch.setattr(cli, "command_build", fail_build)
    args = argparse.Namespace(
        input_dir=str(attachments),
        request=None,
        salaries=None,
        entries=None,
        label="build-failure",
        run_id="build-failure",
        output_dir=str(outputs),
    )

    assert cli.command_cowork_run(args) == 2
    report = json.loads(
        (outputs / "build-failure" / "cowork_run.json").read_text(encoding="utf-8")
    )
    diagnostic = json.loads(Path(report["diagnostic"]).read_text(encoding="utf-8"))
    assert report["status"] == "DO_NOT_UPLOAD"
    assert report["stage"] == "BUILD_OR_CERTIFY_FAILED"
    assert report["upload_csv"] is None
    assert diagnostic["error"] == "KeyError"
    assert "Traceback" in diagnostic["traceback"]
    assert not list(outputs.rglob("DK_UPLOAD_*.csv"))


def test_cowork_certification_failure_removes_upload_shaped_csv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    attachments = tmp_path / "attachments"
    attachments.mkdir()
    _attachment_pair(attachments)
    assignment = attachments / "assignments.csv"
    assignment.write_text(
        "Entry ID,QB,RB,RB,WR,WR,WR,TE,FLEX,DST\n",
        encoding="utf-8",
    )
    runs = tmp_path / "runs"
    outputs = tmp_path / "outputs"
    monkeypatch.setattr(cli, "DEFAULT_RUNS_DIR", runs)
    monkeypatch.setattr(cli, "DEFAULT_OUTPUT_DIR", outputs)
    monkeypatch.setattr(cli, "doctor", lambda _root: _PassingDoctor())
    monkeypatch.setattr(cli, "_cowork_core_blockers", lambda _request: ())

    def fail_certification(_args):
        upload = outputs / "certification-failure" / "DK_UPLOAD_certification-failure.csv"
        upload.write_text("unsafe\n", encoding="utf-8")
        raise OSError("simulated certification I/O failure")

    monkeypatch.setattr(cli, "_certify", fail_certification)
    args = argparse.Namespace(
        input_dir=str(attachments),
        request=None,
        salaries=None,
        entries=None,
        label="certification-failure",
        run_id="certification-failure",
        output_dir=str(outputs),
    )

    assert cli.command_cowork_run(args) == 2
    report_path = outputs / "certification-failure" / "cowork_run.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    diagnostic = json.loads(Path(report["diagnostic"]).read_text(encoding="utf-8"))
    assert report["status"] == "DO_NOT_UPLOAD"
    assert report["error"] == "OSError"
    assert diagnostic["removed_uploads"]
    assert not list(outputs.rglob("DK_UPLOAD_*.csv"))


def test_cli_reports_unexpected_exceptions_but_does_not_swallow_cancellation(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fail_doctor(_args):
        raise OSError("simulated doctor failure")

    monkeypatch.setattr(cli, "command_doctor", fail_doctor)
    assert cli.main(["doctor"]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result == {
        "EVIDENCE_STATE": "UNKNOWN",
        "FILE_VALID": False,
        "MODEL_STATUS": "UNVALIDATED",
        "RELEASE_DECISION": "DO_NOT_UPLOAD",
        "certification_basis": "MANUAL_GUARDRAIL",
        "error": "OSError",
        "message": "simulated doctor failure",
        "stage": "CLI_FAILED",
        "status": "DO_NOT_UPLOAD",
    }

    def cancel_doctor(_args):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "command_doctor", cancel_doctor)
    with pytest.raises(KeyboardInterrupt):
        cli.main(["doctor"])


def test_direct_certification_failure_removes_upload_and_keeps_diagnostic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_root = tmp_path / "outputs" / "direct-failure"

    def fail_certification(_args):
        output_root.mkdir(parents=True)
        (output_root / "DK_UPLOAD_direct-failure.csv").write_text(
            "unsafe\n", encoding="utf-8"
        )
        raise OSError("simulated manifest failure")

    monkeypatch.setattr(cli, "_certify", fail_certification)
    args = argparse.Namespace(
        run_id="direct-failure",
        label="direct-failure",
        output_dir=str(tmp_path / "outputs"),
    )

    with pytest.raises(OSError, match="manifest failure"):
        cli.command_certify(args)
    assert not list(output_root.glob("DK_UPLOAD_*.csv"))
    diagnostic = json.loads(
        (output_root / "certification_diagnostic.json").read_text(encoding="utf-8")
    )
    assert diagnostic["status"] == "DO_NOT_UPLOAD"
    assert diagnostic["upload_csv"] is None
