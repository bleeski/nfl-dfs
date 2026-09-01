from __future__ import annotations

import argparse
import csv
from pathlib import Path

from nfl_dfs.cli import command_build

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
        "rank_start,rank_end,prize_type,value\n1,1,CASH,10\n2,100,CASH,1\n",
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
        advertised_prize_value=109.0,
        ticket_face_value=None,
        field_size=100,
        objective="SMALL_GPP",
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
    output = tmp_path / "outputs" / "reduced-build"
    report = output / "build_reduced-build.json"
    assert report.exists()
    text = report.read_text(encoding="utf-8")
    assert '"DESIGN": 20' in text
    assert '"SELECT": 25' in text
    assert '"REFEREE": 25' in text
    assert '"report_only": true' in text
    assert (output / "assignments_reduced-build.csv").exists()
