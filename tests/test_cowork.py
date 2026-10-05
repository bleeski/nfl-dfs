from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest
from openpyxl import load_workbook

from nfl_dfs import cli
from nfl_dfs.certification import certify_upload
from nfl_dfs.contracts import EvidenceRecord, EvidenceState
from nfl_dfs.cowork import (
    CoworkInputError,
    CoworkRunRequest,
    discover_csv_inputs,
    required_next_inputs,
)
from nfl_dfs.hashing import sha256_file
from nfl_dfs.optimizer import LineupOptimizer


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
        # The fixture slate locked on 2026-09-09; a replay names its deadline (Session 07).
        delivery_deadline_utc="2099-01-01T00:00:00+00:00",
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


def test_a_removed_run_folder_never_lets_a_rerun_reuse_its_output_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """V5, Session 38: `outputs/<run_id>` used `exist_ok=True` while
    `data/runs/<run_id>` was refused. Removing only the run folder (an
    operator cleaning up `data/runs/`, or a retry after a partial failure)
    left the output folder behind; a rerun under the same id then silently
    reused it, overwriting its `cowork_run.json` and reporting the earlier
    run's pointer as this run's.
    """
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
        label="reused-output",
        run_id="reused-output",
        output_dir=str(outputs),
        delivery_deadline_utc="2099-01-01T00:00:00+00:00",
    )

    assert cli.command_cowork_run(args) == 2
    report_path = outputs / "reused-output" / "cowork_run.json"
    original_bytes = report_path.read_bytes()

    shutil.rmtree(runs / "reused-output")
    assert not (runs / "reused-output").exists()
    assert (outputs / "reused-output").exists()

    with pytest.raises(ValueError, match="RUN_ID_COLLISION"):
        cli.command_cowork_run(args)
    # Nothing about the stray output folder's contents moved.
    assert report_path.read_bytes() == original_bytes
    assert not (outputs / "reused-output" / "cowork_diagnostic.json").exists()


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
        # The fixture slate locked on 2026-09-09; a replay names its deadline (Session 07).
        delivery_deadline_utc="2099-01-01T00:00:00+00:00",
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
        # The fixture slate locked on 2026-09-09; a replay names its deadline (Session 07).
        delivery_deadline_utc="2099-01-01T00:00:00+00:00",
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


def _manual_guardrail_assignments(slate, entries):
    scores = {player.dk_id: 50_000 / max(player.salary, 1) for player in slate.players}
    optimizer = LineupOptimizer(slate)
    result = {}
    for entry in sorted(entries.authorizations, key=lambda item: item.entry_id):
        solved = optimizer.solve(scores)
        assert solved.roster is not None
        result[entry.entry_id] = solved.roster
        optimizer.add_no_good(solved.roster)
    return result


def test_a_workbook_lock_after_certification_never_deletes_the_certified_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, classic_slate, classic_entries
) -> None:
    """V3, Session 38: `certify_upload` writes the CERTIFIED CSV and its
    manifest together, then `create_review_workbook` can raise
    `WorkbookLockedError` (the operator has the workbook open in Excel). The
    handler used to unconditionally delete whatever `DK_UPLOAD_*.csv` it
    found, taking the certified file with it even though its manifest still
    bound its exact bytes.
    """
    assignments = _manual_guardrail_assignments(classic_slate, classic_entries)
    now = datetime.now(timezone.utc)
    payout = tmp_path / "payouts.csv"
    payout.write_text(
        "rank_start,rank_end,prize_type,value\n1,1,CASH,10\n2,2,CASH,5\n",
        encoding="utf-8",
    )
    evidence = [
        EvidenceRecord(subject="slate", field="salary_pool", value=True, source_artifact_id=classic_slate.salary_hash, observed_at=now, hard_gate=True, state=EvidenceState.PASS, reason="parsed"),
        EvidenceRecord(subject="entries", field="entry_authorization", value=True, source_artifact_id=classic_entries.raw_hash, observed_at=now, hard_gate=True, state=EvidenceState.PASS, reason="reconciled"),
        EvidenceRecord(subject="contest", field="payout_contract", value=True, source_artifact_id=sha256_file(payout), observed_at=now, hard_gate=True, state=EvidenceState.PASS, reason="reconciled"),
        EvidenceRecord(subject="selected", field="official_inactive_status", value=True, source_artifact_id="a" * 64, observed_at=now, hard_gate=True, state=EvidenceState.PASS, reason="official exact IDs"),
        EvidenceRecord(subject="slate", field="weather_if_required", hard_gate=True, state=EvidenceState.NOT_APPLICABLE, reason="manual guardrail"),
        EvidenceRecord(subject="slate", field="market_line", hard_gate=True, state=EvidenceState.NOT_APPLICABLE, reason="manual guardrail"),
    ]

    def certify_then_lose_the_workbook(args):
        # A stand-in for `_certify`: the real `certify_upload` writes the
        # CERTIFIED CSV and manifest exactly as `_certify` would, and then
        # the workbook step (whatever runs after, inside real `_certify`)
        # raises. This exercises `command_certify`'s except handler against
        # a genuinely certified, hash-bound manifest without needing the
        # full CLI-argument evidence assembly (lock times, source URLs, and
        # so on) `_certify` itself would otherwise require.
        output_dir = Path(args.output_dir).resolve() / args.run_id
        manifest = certify_upload(
            run_id=args.run_id,
            slate=classic_slate,
            template=classic_entries,
            assignments=assignments,
            evidence=evidence,
            output_path=output_dir / f"DK_UPLOAD_{args.run_id}.csv",
            manifest_path=output_dir / f"DK_UPLOAD_{args.run_id}.manifest.json",
        )
        assert manifest.release_decision.value == "CERTIFIED_UPLOAD_PACKAGE"
        raise cli.WorkbookLockedError("operator_input.xlsx is open in Excel")

    monkeypatch.setattr(cli, "_certify", certify_then_lose_the_workbook)

    args = argparse.Namespace(
        run_id="workbook-lock",
        label="workbook-lock",
        output_dir=str(tmp_path / "outputs"),
        manual_guardrail=True,
    )

    with pytest.raises(cli.WorkbookLockedError):
        cli.command_certify(args)

    output_root = tmp_path / "outputs" / "workbook-lock"
    upload = output_root / "DK_UPLOAD_workbook-lock.csv"
    manifest_path = output_root / "DK_UPLOAD_workbook-lock.manifest.json"
    assert upload.is_file()
    assert manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["RELEASE_DECISION"] == "CERTIFIED_UPLOAD_PACKAGE"
    assert sha256_file(upload) == manifest["output_sha256"]
    diagnostic = json.loads(
        (output_root / "certification_diagnostic.json").read_text(encoding="utf-8")
    )
    assert diagnostic["certified_upload_preserved"] is True
    assert diagnostic["upload_csv"] == str(upload)


# --- Session 07: request v3 and its delivery deadline ------------------------


def test_a_v3_request_carries_an_aware_deadline_in_utc() -> None:
    # Session 61 moved the emitted version to v4; this test is about v3's field, so it names v3.
    from nfl_dfs.cowork import COWORK_REQUEST_VERSION_V3 as COWORK_REQUEST_VERSION

    request = CoworkRunRequest.from_mapping(
        {"schema_version": COWORK_REQUEST_VERSION, "delivery_deadline_utc": "2026-09-27T12:55:00-04:00"}
    )
    assert request.schema_version == "nfl_cowork_run_request_v3"
    assert request.delivery_deadline_utc == "2026-09-27T16:55:00+00:00"
    assert CoworkRunRequest().delivery_deadline_utc is None  # absent: R31's default applies
    for bad in ("2026-09-27T12:55:00", "tomorrow", 1790000000, "0001-01-01T00:00:00+01:00",
                "9999-12-31T23:59:59-01:00"):
        with pytest.raises(CoworkInputError, match="delivery_deadline_utc must be an ISO-8601"):
            CoworkRunRequest.from_mapping(
                {"schema_version": COWORK_REQUEST_VERSION, "delivery_deadline_utc": bad}
            )
    for out_of_range in ("0001-01-01T00:04:00+00:00", "3000-01-01T00:00:00Z"):
        with pytest.raises(CoworkInputError, match="years 2000 to 2999"):
            CoworkRunRequest.from_mapping(
                {"schema_version": COWORK_REQUEST_VERSION, "delivery_deadline_utc": out_of_range}
            )


def test_v1_and_v2_stay_accepted_and_may_not_carry_the_deadline() -> None:
    from nfl_dfs.cowork import COWORK_REQUEST_VERSION_V1, COWORK_REQUEST_VERSION_V2

    for version in (COWORK_REQUEST_VERSION_V1, COWORK_REQUEST_VERSION_V2):
        request = CoworkRunRequest.from_mapping({"schema_version": version, "label": "archived"})
        assert request.schema_version == version and request.delivery_deadline_utc is None
        with pytest.raises(CoworkInputError, match="introduced in 'nfl_cowork_run_request_v3'"):
            CoworkRunRequest.from_mapping(
                {"schema_version": version, "delivery_deadline_utc": "2026-09-27T16:55:00Z"}
            )
    # v3 may still carry v2's field: a later version carries every earlier one's.
    request = CoworkRunRequest.from_mapping(
        {"schema_version": "nfl_cowork_run_request_v3", "qb_depth_role_evidence_json": None}
    )
    assert request.schema_version == "nfl_cowork_run_request_v3"


def test_a_deadline_flag_on_a_reloaded_v2_request_makes_a_v3_run_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nfl_dfs.cowork import request_version_for

    assert request_version_for("nfl_cowork_run_request_v2", ["delivery_deadline_utc"]) == (
        "nfl_cowork_run_request_v3")
    assert request_version_for("nfl_cowork_run_request_v1", ["label"]) == "nfl_cowork_run_request_v1"
    attachments = tmp_path / "attachments"
    attachments.mkdir()
    salary, entries = _attachment_pair(attachments)
    request_path = attachments / "request.json"
    original = json.dumps({"schema_version": "nfl_cowork_run_request_v2", "salary_csv": salary.name,
                           "entry_csv": entries.name})
    request_path.write_text(original, encoding="utf-8")
    runs = tmp_path / "runs"
    monkeypatch.setattr(cli, "DEFAULT_RUNS_DIR", runs)
    args = argparse.Namespace(
        input_dir=str(attachments), request=str(request_path), salaries=None, entries=None,
        label="reloaded", run_id="reloaded", output_dir=str(tmp_path / "outputs"),
        delivery_deadline_utc="2099-01-01T00:00:00Z",
    )
    assert cli.command_cowork_run(args) == 2  # the diagnostic profile lacks its inputs
    written = json.loads((runs / "reloaded" / "run_request.json").read_text(encoding="utf-8"))
    assert written["schema_version"] == "nfl_cowork_run_request_v3"
    assert written["delivery_deadline_utc"] == "2099-01-01T00:00:00+00:00"
    assert request_path.read_text(encoding="utf-8") == original  # the v2 file is untouched
    report = json.loads((tmp_path / "outputs" / "reloaded" / "cowork_run.json").read_text(encoding="utf-8"))
    assert report["deadline"]["deadline_source"] == "REQUEST"


# --- Session 61: request v4 and the construction judgment ---------------------


def test_a_v4_request_carries_and_confines_the_construction_judgment(tmp_path: Path) -> None:
    from nfl_dfs.cowork import COWORK_REQUEST_VERSION

    assert COWORK_REQUEST_VERSION == "nfl_cowork_run_request_v4"
    judgment = tmp_path / "judgment.json"
    judgment.write_text("{}", encoding="utf-8")
    request = CoworkRunRequest.from_mapping(
        {"schema_version": COWORK_REQUEST_VERSION, "construction_judgment_json": str(judgment)},
        base_dir=tmp_path, allowed_roots=[tmp_path],
    )
    assert request.schema_version == "nfl_cowork_run_request_v4"
    assert request.construction_judgment_json == str(judgment.resolve())
    assert CoworkRunRequest().construction_judgment_json is None
    outside = tmp_path.parent / "elsewhere_judgment.json"
    outside.write_text("{}", encoding="utf-8")
    with pytest.raises(CoworkInputError, match="outside the supplied"):
        CoworkRunRequest.from_mapping(
            {"schema_version": COWORK_REQUEST_VERSION, "construction_judgment_json": str(outside)},
            base_dir=tmp_path, allowed_roots=[tmp_path],
        )


def test_older_requests_stay_accepted_and_may_not_carry_the_construction_judgment(tmp_path: Path) -> None:
    from nfl_dfs.cowork import (
        COWORK_REQUEST_VERSION_V1,
        COWORK_REQUEST_VERSION_V2,
        COWORK_REQUEST_VERSION_V3,
        request_version_for,
    )

    judgment = tmp_path / "judgment.json"
    judgment.write_text("{}", encoding="utf-8")
    for version in (COWORK_REQUEST_VERSION_V1, COWORK_REQUEST_VERSION_V2, COWORK_REQUEST_VERSION_V3):
        request = CoworkRunRequest.from_mapping({"schema_version": version, "label": "archived"})
        assert request.schema_version == version and request.construction_judgment_json is None
        with pytest.raises(CoworkInputError, match="introduced in 'nfl_cowork_run_request_v4'"):
            CoworkRunRequest.from_mapping(
                {"schema_version": version, "construction_judgment_json": str(judgment)},
                base_dir=tmp_path, allowed_roots=[tmp_path],
            )
    # a v4 request may still carry every earlier field, and a flag on a reloaded v3 request raises it to v4
    request = CoworkRunRequest.from_mapping(
        {"schema_version": "nfl_cowork_run_request_v4", "delivery_deadline_utc": "2026-09-27T16:55:00Z"})
    assert request.delivery_deadline_utc == "2026-09-27T16:55:00+00:00"
    assert request_version_for("nfl_cowork_run_request_v3", ["construction_judgment_json"]) == (
        "nfl_cowork_run_request_v4")
    assert request_version_for("nfl_cowork_run_request_v3", ["delivery_deadline_utc"]) == (
        "nfl_cowork_run_request_v3")
