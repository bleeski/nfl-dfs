from __future__ import annotations

import argparse
import json
import shutil
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
    assert report["stage"] == "RECONCILED"
    assert report["authorized_entries"] == 2
    assert Path(request["salary_csv"]).parent == runs / "cowork-fixture" / "inputs"
    assert Path(request["entry_csv"]).parent == runs / "cowork-fixture" / "inputs"
    assert not list(outputs.rglob("DK_UPLOAD_*.csv"))
    workbook = load_workbook(report["review_workbook"], data_only=False)
    assert workbook["Upload"]["B4"].value == "DO_NOT_UPLOAD"
    assert workbook["Run Control"]["B6"].value == request["salary_csv"]
    assert workbook["Run Control"]["B7"].value == request["entry_csv"]
