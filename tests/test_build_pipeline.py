from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from openpyxl import load_workbook

from nfl_dfs.cli import _certify, command_build
from nfl_dfs.hashing import sha256_file
from nfl_dfs.lineups import read_assignment_csv
from nfl_dfs.workbook import create_operator_input_workbook

from .conftest import FIXTURE_ROOT


def _write_model_inputs(tmp_path: Path, slate) -> tuple[Path, Path]:
    team_path = tmp_path / "teams.csv"
    player_path = tmp_path / "players.csv"
    with team_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\r\n")
        writer.writerow(
            [
                "TEAM",
                "GAME_ID",
                "PLAYS_MEAN",
                "PASS_RATE",
                "PASS_YARDS_PER_ATTEMPT",
                "RUSH_YARDS_PER_ATTEMPT",
                "TOUCHDOWNS_MEAN",
                "FIELD_GOALS_MEAN",
                "TURNOVERS_MEAN",
                "SACKS_ALLOWED_MEAN",
                "UNCERTAINTY",
                "MARKET_TOTAL",
                "MARKET_SPREAD",
                "MARKET_OBSERVED_AT",
                "WEATHER_STATE",
                "ERA",
            ]
        )
        for game in slate.games:
            for team in (game.away_team, game.home_team):
                writer.writerow(
                    [team, game.game_id, 64, 0.58, 6.8, 4.2, 2.5, 1.5, 1.2, 2.4, 0.25, 45, 0, "2026-09-13T10:00:00-04:00", "CLEAR", "2026"]
                )
    people = {}
    for player in slate.players:
        people.setdefault(player.underlying_id, player)
    with player_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\r\n")
        writer.writerow(
            [
                "DK_ID",
                "TEAM",
                "POSITION",
                "QB_ATTEMPT_SHARE",
                "CARRY_SHARE",
                "TARGET_SHARE",
                "CATCH_RATE",
                "YARDS_PER_TARGET",
                "RUSHING_TD_SHARE",
                "RECEIVING_TD_SHARE",
                "ROLE_CAPACITY",
                "EVIDENCE_STATE",
            ]
        )
        for player in people.values():
            skill = player.position in {"QB", "RB", "WR", "TE"}
            receiver = player.position in {"RB", "WR", "TE"}
            writer.writerow(
                [
                    player.dk_id,
                    player.team,
                    player.position,
                    1 if player.position == "QB" else 0,
                    1 if skill else 0,
                    1 if receiver else 0,
                    0.68 if receiver else 0,
                    7.2 if receiver else 0,
                    1 if skill else 0,
                    1 if receiver else 0,
                    1,
                    "PASS",
                ]
            )
    return team_path, player_path


def test_reduced_end_to_end_design_select_referee_build(
    tmp_path: Path, classic_slate, classic_entries
) -> None:
    team_path, player_path = _write_model_inputs(tmp_path, classic_slate)
    payout = tmp_path / "payouts.csv"
    payout.write_text(
        "rank_start,rank_end,prize_type,value\n1,1,TICKET,2\n2,100,CASH,1\n",
        encoding="utf-8",
    )
    args = argparse.Namespace(
        run_id="reduced-build",
        label="test",
        salaries=str(FIXTURE_ROOT / "DKSalaries Salary CSV Classic.csv"),
        entries=str(classic_entries.path),
        team_projections=str(team_path),
        player_opportunities=str(player_path),
        payouts=str(payout),
        advertised_prize_value=199.0,
        ticket_face_value=50.0,
        field_size=100,
        objective="SATELLITE",
        ownership_brackets=None,
        design_scenarios=20,
        select_scenarios=25,
        referee_scenarios=25,
        seed=1234,
        design_objectives=5,
        candidates=8,
        milp_seed_candidates=8,
        per_solve_seconds=2.0,
        field_sample_size=20,
        field_chunk_size=8,
        shortlist_limit=8,
        output_dir=str(tmp_path / "outputs"),
    )
    assert command_build(args) == 0
    with pytest.raises(RuntimeError, match="immutable run_id"):
        command_build(args)
    output = tmp_path / "outputs" / "reduced-build"
    report = output / "build_reduced-build.json"
    assert report.exists()
    text = report.read_text(encoding="utf-8")
    assert '"DESIGN": 20' in text
    assert '"SELECT": 25' in text
    assert '"REFEREE": 25' in text
    assert '"binding": true' in text
    assert '"quantitative_qa"' in text
    assert '"solver_proof"' in text
    build_payload = json.loads(text)
    assert build_payload["FILE_VALID"] is False
    assert build_payload["EVIDENCE_STATE"] == "UNKNOWN"
    assert build_payload["MODEL_STATUS"] == "PRIOR_ONLY"
    assert build_payload["RELEASE_DECISION"] == "DO_NOT_UPLOAD"
    coverage_findings = [
        finding
        for finding in build_payload["precertification_findings"]
        if finding["code"] == "CANDIDATE_FAMILY_COVERAGE_INCOMPLETE"
    ]
    assert all(not finding["blocking"] for finding in coverage_findings)
    assert (output / "assignments_reduced-build.csv").exists()

    assignments_path = output / "assignments_reduced-build.csv"
    assignments = read_assignment_csv(assignments_path, classic_slate.mode)
    by_id = {player.dk_id: player for player in classic_slate.players}
    statuses = tmp_path / "official.csv"
    with statuses.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["TEAM", "PLAYER_OR_GSIS_ID", "STATUS", "SOURCE_URL", "OBSERVED_AT"])
        for dk_id in sorted({dk_id for roster in assignments.values() for dk_id in roster}):
            writer.writerow(
                [
                    by_id[dk_id].team,
                    dk_id,
                    "ACTIVE",
                    "https://official.example/status",
                    datetime.now(timezone.utc).isoformat(),
                ]
            )
    source_ledger = tmp_path / "source-ledger.json"
    source_ledger.write_text('{"schema":"test"}\n', encoding="utf-8")
    staged = create_operator_input_workbook(tmp_path / "staged.xlsx")
    certify_args = argparse.Namespace(
        salaries=str(FIXTURE_ROOT / "DKSalaries Salary CSV Classic.csv"),
        entries=str(classic_entries.path),
        run_id="reduced-build",
        label="test",
        assignments=str(assignments_path),
        payouts=str(payout),
        advertised_prize_value=199.0,
        ticket_face_value=50.0,
        field_size=100,
        objective="SATELLITE",
        official_statuses=str(statuses),
        team_projections=str(team_path),
        player_opportunities=str(player_path),
        source_ledger=str(source_ledger),
        build_report=str(report),
        manual_guardrail=False,
        output_dir=str(tmp_path / "outputs"),
        staged_workbook=str(staged),
    )
    code, certification = _certify(certify_args)
    assert code == 2 and certification["status"] == "DO_NOT_UPLOAD"
    assert any(
        blocker.startswith("SOURCE_LEDGER_INVALID:")
        for blocker in certification["blockers"]
    )
    manifest = json.loads(Path(certification["manifest"]).read_text(encoding="utf-8"))
    assert manifest["solver_proof"]["milp_candidate_count"] == 8
    assert manifest["input_hashes"]["assignments"] == json.loads(text)["assignment_sha256"]
    assert {item["field"] for item in manifest["evidence"]} >= {
        "player_opportunity_evidence",
        "quantitative_qa",
        "referee_review",
    }

    source_artifact = tmp_path / "frozen-source.json"
    source_artifact.write_text('{"players": []}\n', encoding="utf-8")
    valid_ledger = tmp_path / "valid-source-ledger.json"
    valid_ledger.write_text(
        json.dumps(
            {
                "schema_version": "nfl_source_ledger_v1",
                "entries": [
                    {
                        "artifact_id": sha256_file(source_artifact),
                        "path": source_artifact.name,
                        "source_uri": "https://api.sleeper.app/v1/players/nfl",
                        "captured_at": datetime.now(timezone.utc).isoformat(),
                        "observed_at": datetime.now(timezone.utc).isoformat(),
                        "license_decision": "SECONDARY_STATUS_ONLY",
                        "parser_version": "sleeper_players_v1",
                    }
                ],
                "derived": {
                    "team_projections": sha256_file(team_path),
                    "player_opportunities": sha256_file(player_path),
                },
            }
        ),
        encoding="utf-8",
    )
    valid_report = json.loads(report.read_text(encoding="utf-8"))
    valid_report["run_id"] = "valid-ledger"
    valid_report_path = tmp_path / "valid-ledger-build.json"
    valid_report_path.write_text(json.dumps(valid_report), encoding="utf-8")
    valid_args = argparse.Namespace(
        **{
            **vars(certify_args),
            "run_id": "valid-ledger",
            "source_ledger": str(valid_ledger),
            "build_report": str(valid_report_path),
        }
    )
    _, valid_certification = _certify(valid_args)
    assert not any(
        blocker.startswith("SOURCE_LEDGER_")
        for blocker in valid_certification["blockers"]
    )
    assert valid_certification["FILE_VALID"] is True
    assert valid_certification["MODEL_STATUS"] == "PRIOR_ONLY"
    assert valid_certification["RELEASE_DECISION"] == "DO_NOT_UPLOAD"
    assert any(
        blocker == "MODEL_NOT_PROSPECTIVELY_VALIDATED:PRIOR_ONLY"
        for blocker in valid_certification["blockers"]
    )
    review_workbook = load_workbook(
        valid_certification["review_workbook"], data_only=False
    )
    assert review_workbook["Upload"]["B5"].value is True
    assert review_workbook["Upload"]["B6"].value in {
        "PASS",
        "UNKNOWN",
        "STALE",
        "CONFLICTED",
    }
    assert review_workbook["Upload"]["B7"].value == "PRIOR_ONLY"
    assert review_workbook["Upload"]["B8"].value == "DO_NOT_UPLOAD"

    tampered_report = json.loads(report.read_text(encoding="utf-8"))
    tampered_report["run_id"] = "tampered-build"
    tampered_report["input_hashes"]["salary"] = "0" * 64
    tampered_path = tmp_path / "tampered-build.json"
    tampered_path.write_text(json.dumps(tampered_report), encoding="utf-8")
    tampered_args = argparse.Namespace(
        **{
            **vars(certify_args),
            "run_id": "tampered-build",
            "build_report": str(tampered_path),
        }
    )
    tampered_code, tampered = _certify(tampered_args)
    assert tampered_code == 2
    assert "BUILD_INPUT_HASH_MISMATCH" in tampered["blockers"]
