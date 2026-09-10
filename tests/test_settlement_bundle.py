from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

import numpy as np
import pytest

import nfl_dfs.settlement as settlement_module
from nfl_dfs.cli import main
from nfl_dfs.dk import parse_entries, parse_salaries
from nfl_dfs.hashing import sha256_file
from nfl_dfs.optimizer import LineupOptimizer
from nfl_dfs.scenario_store import save_scenario_bank
from nfl_dfs.settlement import (
    SettlementError,
    capture_settlement_bundle,
    replay_settlement_package,
)
from nfl_dfs.simulation import SimulationResult


REGISTRY = Path(__file__).parents[1] / "config" / "metric_registry_q1_v1.json"


def _json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def _write_csv(path: Path, header: tuple[str, ...], rows: list[tuple[object, ...]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def _settlement_fixture(
    tmp_path: Path, classic_slate, classic_entries
) -> tuple[Path, dict, dict[str, Path]]:
    source = tmp_path / "source"
    source.mkdir()
    paths = {
        "salary": source / "salary.csv",
        "entries": source / "entries.csv",
        "payouts": source / "payouts.csv",
        "assignments": source / "assignments.csv",
        "standings": source / "standings.csv",
        "prediction": source / "prediction.json",
        "registry": source / "metric_registry.json",
        "manifest": source / "prelock_manifest.json",
    }
    salary_source = Path(__file__).parent / "fixtures" / "supplied" / "DKSalaries Salary CSV Classic.csv"
    paths["salary"].write_bytes(salary_source.read_bytes())
    paths["entries"].write_bytes(classic_entries.path.read_bytes())
    paths["payouts"].write_text(
        "rank_start,rank_end,prize_type,value\n1,1,CASH,20\n",
        encoding="utf-8",
    )
    slate = parse_salaries(paths["salary"], draft_group=classic_slate.draft_group)
    entries = parse_entries(paths["entries"])
    optimizer = LineupOptimizer(slate)
    scores = {player.dk_id: 50_000 / max(player.salary, 1) for player in slate.players}
    first = optimizer.solve(scores)
    assert first.roster is not None
    optimizer.add_no_good(first.roster)
    second = optimizer.solve(scores)
    assert second.roster is not None
    assignments = {
        entries.authorizations[0].entry_id: first.roster,
        entries.authorizations[1].entry_id: second.roster,
    }
    _write_csv(
        paths["assignments"],
        ("Entry ID", "QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX", "DST"),
        [(entry_id, *roster) for entry_id, roster in assignments.items()],
    )
    from nfl_dfs.lineups import validate_lineup

    first_lineup = validate_lineup(slate, first.roster).lineup
    second_lineup = validate_lineup(slate, second.roster).lineup
    assert first_lineup is not None and second_lineup is not None
    _write_csv(
        paths["standings"],
        ("EntryId", "Rank", "Points", "Prize", "Lineup"),
        [
            (entries.authorizations[0].entry_id, 1, "200.000000", "$20.00", first_lineup.canonical_key),
            (entries.authorizations[1].entry_id, 2, "150.000000", "$0.00", second_lineup.canonical_key),
        ],
    )
    _json(
        paths["prediction"],
        {
            "schema_version": "nfl_prediction_artifact_v1",
            "created_at": "2026-09-10T17:00:00Z",
            "note": "synthetic contract fixture; no model claim",
        },
    )
    paths["registry"].write_bytes(REGISTRY.read_bytes())
    people = tuple(dict.fromkeys(player.underlying_id for player in slate.players))
    scenario = save_scenario_bank(
        SimulationResult(
            purpose="SELECT",
            seed=101,
            person_ids=people,
            outcomes=np.zeros((2, len(people)), dtype=np.float32),
            weights=np.full(2, 0.5),
            diagnostics={"fixture": True},
        ),
        source / "scenarios",
    )
    paths["scenario"] = Path(scenario["path"])

    truths = {
        "FILE_VALID": True,
        "EVIDENCE_STATE": "UNKNOWN",
        "MODEL_STATUS": "PRIOR_ONLY",
        "RELEASE_DECISION": "DO_NOT_UPLOAD",
    }
    artifact_versions = {
        "salary": "dk_salary_csv_v1",
        "entries": "dk_entry_csv_v1",
        "payouts": "nfl_payout_contract_v1",
        "assignments": "nfl_assignment_csv_v1",
        "prediction": "nfl_prediction_artifact_v1",
        "SELECT": "nfl_scenario_bank_v1",
    }
    manifest = {
        "schema_version": "nfl_prelock_run_manifest_v1",
        "run_id": "q1-fixture-run",
        "status": "DIAGNOSTIC_ASSIGNMENTS_READY_DO_NOT_UPLOAD",
        **truths,
        "input_hashes": {
            "salary": sha256_file(paths["salary"]),
            "entries": sha256_file(paths["entries"]),
            "payouts": sha256_file(paths["payouts"]),
            "prediction": sha256_file(paths["prediction"]),
        },
        "assignment_sha256": sha256_file(paths["assignments"]),
        "scenario_artifacts": {"SELECT": scenario},
        "artifact_versions": artifact_versions,
        "contest_parameters": {
            "contest_id": entries.authorizations[0].contest_id,
            "draft_group": classic_slate.draft_group,
            "mode": "CLASSIC",
            "entry_fee": 5.0,
            "field_size": 2,
            "objective": "SMALL_GPP",
            "advertised_prize_value": 20.0,
            "ticket_face_value": None,
        },
    }
    _json(paths["manifest"], manifest)

    def binding(name: str, key: str, version: str) -> dict[str, str]:
        return {
            "name": name,
            "path": str(paths[key].relative_to(source)),
            "sha256": sha256_file(paths[key]),
            "artifact_version": version,
        }

    request = {
        "schema_version": "nfl_settlement_request_v1",
        "settlement_id": "q1-fixture-settlement",
        "run_id": "q1-fixture-run",
        "captured_at": "2026-09-10T17:00:00Z",
        "settled_at": "2026-09-10T18:00:00Z",
        "contest": {
            "contest_id": entries.authorizations[0].contest_id,
            "draft_group": classic_slate.draft_group,
            "mode": "CLASSIC",
            "entry_fee": "5.00",
            "field_size": 2,
            "objective": "SMALL_GPP",
            "advertised_prize_value": "20.00",
            "ticket_face_value": None,
        },
        "versions": {
            "salary_parser": "dk_csv_v1",
            "entry_parser": "dk_csv_v1",
            "payout_parser": "nfl_payout_csv_v2",
            "standings_parser": "nfl_standings_csv_v2",
            "assignment_parser": "nfl_assignment_csv_v1",
            "scoring": classic_slate.scoring_version,
            "settlement": "nfl_reference_settlement_v1",
            "bundle_schema": "nfl_settlement_bundle_v1",
            "brief_schema": "nfl_run_settlement_brief_v1",
            "metric_registry_schema": "nfl_metric_promotion_registry_v1",
        },
        "artifacts": {
            "salary": binding("salary", "salary", "dk_salary_csv_v1"),
            "entries": binding("entries", "entries", "dk_entry_csv_v1"),
            "payouts": binding("payouts", "payouts", "nfl_payout_contract_v1"),
            "assignments": binding(
                "assignments", "assignments", "nfl_assignment_csv_v1"
            ),
            "prelock_manifest": binding(
                "prelock_manifest", "manifest", "nfl_prelock_run_manifest_v1"
            ),
            "standings": binding(
                "standings", "standings", "nfl_standings_csv_v2"
            ),
            "metric_registry": binding(
                "metric_registry", "registry", "nfl_metric_promotion_registry_v1"
            ),
            "predictions": [
                binding("prediction", "prediction", "nfl_prediction_artifact_v1")
            ],
            "scenarios": [binding("SELECT", "scenario", "nfl_scenario_bank_v1")],
        },
        "release_truths": truths,
        "evidence_issues": [
            {
                "state": "MISSING",
                "code": "PROSPECTIVE_VALIDATION_ABSENT",
                "detail": "Synthetic fixture remains PRIOR_ONLY and is not upload-ready.",
            }
        ],
        "reference_budget": {
            "max_entries": 100,
            "max_work_units": 1000,
            "max_runtime_seconds": 5.0,
        },
    }
    request_path = source / "request.json"
    _json(request_path, request)
    return request_path, request, paths


def _rewrite_request(request_path: Path, request: dict) -> None:
    _json(request_path, request)


def test_complete_immutable_bundle_and_deterministic_copied_replay(
    tmp_path: Path, classic_slate, classic_entries
) -> None:
    request_path, _, _ = _settlement_fixture(tmp_path, classic_slate, classic_entries)
    outcome = capture_settlement_bundle(request_path, tmp_path / "settlements")
    package = Path(outcome.package_path)
    assert outcome.bundle.capture_status == "Q1_COMPLETE"
    assert outcome.bundle.release_truths.release_decision.value == "DO_NOT_UPLOAD"
    assert (package / "settlement_bundle.json").is_file()
    assert (package / "run_settlement_brief.json").is_file()
    assert (package / "reference_settlement.json").is_file()
    brief = json.loads((package / "run_settlement_brief.json").read_text(encoding="utf-8"))
    assert brief["credentials_or_account_state_stored"] is False
    assert brief["selection_and_entry"]["selected_entry_ids"] == [
        entry.entry_id for entry in classic_entries.authorizations
    ]
    replay = replay_settlement_package(package)
    assert replay["status"] == "DETERMINISTIC_REPLAY_PASS"
    copied = tmp_path / "copied-package"
    shutil.copytree(package, copied)
    assert replay_settlement_package(copied)["reference_result_hash"] == replay[
        "reference_result_hash"
    ]
    with pytest.raises(SettlementError, match="already exists and is immutable"):
        capture_settlement_bundle(request_path, tmp_path / "settlements")


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda request: request["artifacts"]["salary"].update(sha256="0" * 64),
            "ARTIFACT_HASH_MISMATCH",
        ),
        (
            lambda request: request["artifacts"]["salary"].update(
                artifact_version="dk_salary_csv_v0"
            ),
            "ARTIFACT_VERSION_MISMATCH",
        ),
        (
            lambda request: request["contest"].update(contest_id="999"),
            "PRELOCK_CONTEST_MISMATCH:contest_id",
        ),
        (
            lambda request: request["contest"].update(draft_group="wrong-draft-group"),
            "PRELOCK_CONTEST_MISMATCH:draft_group",
        ),
        (
            lambda request: request["contest"].update(mode="SHOWDOWN"),
            "PRELOCK_CONTEST_MISMATCH:mode",
        ),
    ],
)
def test_bundle_rejects_hash_version_contest_draft_group_and_mode_mismatches(
    tmp_path: Path, classic_slate, classic_entries, mutate, message: str
) -> None:
    request_path, request, _ = _settlement_fixture(tmp_path, classic_slate, classic_entries)
    mutate(request)
    _rewrite_request(request_path, request)
    with pytest.raises(SettlementError, match=message):
        capture_settlement_bundle(request_path, tmp_path / "settlements")


def test_bundle_rejects_entry_id_and_incomplete_standings(
    tmp_path: Path, classic_slate, classic_entries
) -> None:
    request_path, request, paths = _settlement_fixture(
        tmp_path, classic_slate, classic_entries
    )
    rows = list(csv.reader(paths["assignments"].read_text(encoding="utf-8").splitlines()))
    rows[1][0] = "999"
    _write_csv(paths["assignments"], tuple(rows[0]), [tuple(row) for row in rows[1:]])
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    manifest["assignment_sha256"] = sha256_file(paths["assignments"])
    _json(paths["manifest"], manifest)
    request["artifacts"]["assignments"]["sha256"] = sha256_file(paths["assignments"])
    request["artifacts"]["prelock_manifest"]["sha256"] = sha256_file(paths["manifest"])
    _rewrite_request(request_path, request)
    with pytest.raises(SettlementError, match="ENTRY_ID_ASSIGNMENT_MISMATCH"):
        capture_settlement_bundle(request_path, tmp_path / "settlements")

    second_root = tmp_path / "incomplete"
    second_root.mkdir()
    second_request, second, second_paths = _settlement_fixture(
        second_root, classic_slate, classic_entries
    )
    standings_rows = list(
        csv.reader(second_paths["standings"].read_text(encoding="utf-8").splitlines())
    )
    _write_csv(
        second_paths["standings"],
        tuple(standings_rows[0]),
        [tuple(standings_rows[1])],
    )
    second["artifacts"]["standings"]["sha256"] = sha256_file(
        second_paths["standings"]
    )
    _rewrite_request(second_request, second)
    with pytest.raises(SettlementError, match="standings are incomplete"):
        capture_settlement_bundle(second_request, second_root / "settlements")


def test_source_mutation_during_capture_fails_before_publication(
    tmp_path: Path, classic_slate, classic_entries, monkeypatch
) -> None:
    request_path, _, paths = _settlement_fixture(tmp_path, classic_slate, classic_entries)
    original = settlement_module._verify_sources_unchanged
    mutated = False

    def mutate_then_verify(artifacts):
        nonlocal mutated
        if not mutated:
            paths["prediction"].write_text("mutated", encoding="utf-8")
            mutated = True
        original(artifacts)

    monkeypatch.setattr(settlement_module, "_verify_sources_unchanged", mutate_then_verify)
    with pytest.raises(SettlementError, match="SOURCE_MUTATED_DURING_CAPTURE"):
        capture_settlement_bundle(request_path, tmp_path / "settlements")
    assert not (tmp_path / "settlements" / "q1-fixture-settlement").exists()


def test_settle_cli_complete_replay_and_legacy_partial_truth(
    tmp_path: Path, classic_slate, classic_entries, capsys
) -> None:
    request_path, _, paths = _settlement_fixture(tmp_path, classic_slate, classic_entries)
    output = tmp_path / "cli-settlements"
    assert main(["settle", "--request", str(request_path), "--output-dir", str(output)]) == 0
    created = json.loads(capsys.readouterr().out)
    assert created["status"] == "Q1_SETTLEMENT_COMPLETE"
    assert created["RELEASE_DECISION"] == "DO_NOT_UPLOAD"
    assert main(["settle", "--replay", created["package_path"]]) == 0
    replay = json.loads(capsys.readouterr().out)
    assert replay["status"] == "DETERMINISTIC_REPLAY_PASS"
    assert (
        main(
            [
                "settle",
                "--entries",
                str(paths["entries"]),
                "--standings",
                str(paths["standings"]),
            ]
        )
        == 2
    )
    legacy = json.loads(capsys.readouterr().out)
    assert legacy["status"] == "LEGACY_PARTIAL_SETTLEMENT_CAPTURE"
    assert legacy["q1_complete"] is False
    assert legacy["RELEASE_DECISION"] == "DO_NOT_UPLOAD"
