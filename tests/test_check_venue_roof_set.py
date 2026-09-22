"""Acceptance for the unlisted-retractable-venue diagnostic.

The statement under test: a home team carrying an unplayed game with no
recorded roof, and absent from `RETRACTABLE_ROOF_HOME_TEAMS`, is named; every
other shape is silent.

The thing this guards cannot be tested directly. A committed fixture cannot
contain a stadium that does not exist yet, so these tests pin the detection and
`scripts/check_venue_roof_set.py` is what runs it against a current schedule.
"""

from __future__ import annotations

import csv
import importlib.util
import sys
from pathlib import Path

import pytest

from nfl_dfs.venues import RETRACTABLE_ROOF_HOME_TEAMS, unlisted_blank_roof_teams

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check_venue_roof_set.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("check_venue_roof_set", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_venue_roof_set"] = module
    spec.loader.exec_module(module)
    return module


def _row(team: str, roof: str, *, played: bool, season: int = 2026) -> dict[str, str]:
    return {
        "home_team": team,
        "home_score": "24" if played else "",
        "roof": roof,
        "season": str(season),
        "game_id": f"{season}_01_AWAY_{team}",
    }


def test_a_listed_venue_with_a_blank_unplayed_roof_is_not_named() -> None:
    rows = [_row(team, "", played=False) for team in sorted(RETRACTABLE_ROOF_HOME_TEAMS)]
    assert unlisted_blank_roof_teams(rows) == ()


def test_an_unlisted_venue_with_a_blank_unplayed_roof_is_named() -> None:
    # The failure this exists for: a sixth retractable roof opens.
    rows = [_row("BUF", "", played=False)]
    assert unlisted_blank_roof_teams(rows) == ("BUF",)


def test_a_played_game_with_a_blank_roof_is_missing_data_not_a_signal() -> None:
    assert unlisted_blank_roof_teams([_row("BUF", "", played=True)]) == ()


def test_a_recorded_roof_is_never_a_signal() -> None:
    rows = [
        _row("BUF", "outdoors", played=False),
        _row("LV", "dome", played=False),
        _row("ARI", "closed", played=False),
    ]
    assert unlisted_blank_roof_teams(rows) == ()


def test_a_blank_home_team_is_skipped_rather_than_named() -> None:
    assert unlisted_blank_roof_teams([_row("", "", played=False)]) == ()


def test_teams_are_reported_once_sorted_and_upper_cased() -> None:
    rows = [
        _row("buf", "", played=False),
        _row("BUF", "", played=False),
        _row("car", "", played=False),
    ]
    assert unlisted_blank_roof_teams(rows) == ("BUF", "CAR")


def test_the_season_window_excludes_other_seasons() -> None:
    rows = [_row("BUF", "", played=False, season=2024)]
    assert unlisted_blank_roof_teams(rows, seasons=[2026]) == ()
    assert unlisted_blank_roof_teams(rows, seasons=[2024]) == ("BUF",)


def test_no_rows_at_all_names_nobody() -> None:
    assert unlisted_blank_roof_teams([]) == ()


def _write(path: Path, rows: list[dict[str, str]]) -> Path:
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["home_team", "home_score", "roof", "season", "game_id"]
        )
        writer.writeheader()
        writer.writerows(rows)
    return path


def test_script_exits_zero_when_every_blank_belongs_to_a_listed_venue(
    tmp_path: Path,
) -> None:
    module = _load_script()
    games = _write(
        tmp_path / "games.csv",
        [_row(team, "", played=False) for team in sorted(RETRACTABLE_ROOF_HOME_TEAMS)],
    )
    assert module.main(["--games", str(games)]) == 0


def test_script_exits_one_and_names_the_venue(tmp_path: Path, capsys) -> None:
    module = _load_script()
    games = _write(tmp_path / "games.csv", [_row("BUF", "", played=False)])
    assert module.main(["--games", str(games)]) == 1
    assert "UNLISTED_BLANK_ROOF_VENUES:BUF" in capsys.readouterr().err


def test_script_exits_two_on_a_missing_file(tmp_path: Path) -> None:
    module = _load_script()
    assert module.main(["--games", str(tmp_path / "absent.csv")]) == 2


def test_script_exits_two_on_a_schedule_with_no_roof_column(tmp_path: Path) -> None:
    # A truncated or wrong-schema file must never read as a clean run.
    module = _load_script()
    path = tmp_path / "games.csv"
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["home_team", "season"])
        writer.writeheader()
        writer.writerow({"home_team": "BUF", "season": "2026"})
    assert module.main(["--games", str(path)]) == 2


def test_script_exits_two_on_an_empty_schedule(tmp_path: Path) -> None:
    module = _load_script()
    path = tmp_path / "games.csv"
    path.write_text("", encoding="utf-8")
    assert module.main(["--games", str(path)]) == 2


@pytest.mark.parametrize("team", sorted(RETRACTABLE_ROOF_HOME_TEAMS))
def test_every_listed_venue_is_silent_on_its_own_blank(team: str) -> None:
    assert unlisted_blank_roof_teams([_row(team, "", played=False)]) == ()
