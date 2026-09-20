"""Acceptance for `scripts/fetch_weather_captures.py`. No network is touched.

The script's job is to make a blocked build session survivable by letting the
capture happen elsewhere. That only works if it covers every stadium a slate can
name, reuses the gridpoints already checked, and refuses to guess the one value
no forecast carries.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "fetch_weather_captures.py"

# DraftKings team abbreviations. A home team outside this set would be a new
# franchise or a relocation, which is a deliberate edit, not a silent gap.
DK_TEAMS = {
    "ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE", "DAL", "DEN",
    "DET", "GB", "HOU", "IND", "JAX", "KC", "LAC", "LAR", "LV", "MIA",
    "MIN", "NE", "NO", "NYG", "NYJ", "PHI", "PIT", "SEA", "SF", "TB",
    "TEN", "WAS",
}


def _load():
    spec = importlib.util.spec_from_file_location("fetch_weather_captures", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["fetch_weather_captures"] = module
    spec.loader.exec_module(module)
    return module


fetch = _load()


def test_every_draftkings_team_has_stadium_coordinates():
    """A missing home team stops a slate, because the weather package must
    cover the exact complete game set."""

    assert set(fetch.STADIUMS) == DK_TEAMS


def test_retractable_roofs_are_flagged_for_a_human():
    """Whether a retractable roof is open is an observation, not a forecast."""

    assert fetch.RETRACTABLE <= DK_TEAMS
    for team in ("ARI", "ATL", "DAL", "HOU"):
        assert team in fetch.RETRACTABLE


def test_pinned_gridpoints_are_reused_and_well_formed():
    """Reusing a checked gridpoint avoids a /points call that could be wrong."""

    pinned = fetch.known_gridpoints()
    assert pinned, "scripts/nws_gridpoints.json should supply at least one"
    for team, uri in pinned.items():
        assert team in DK_TEAMS
        assert uri.startswith("https://api.weather.gov/gridpoints/")


def _salary(path: Path, cells: list[str]) -> Path:
    header = (
        "Position,Name + ID,Name,ID,Roster Position,Salary,"
        "Game Info,TeamAbbrev,AvgPointsPerGame,Status\n"
    )
    body = "".join(
        f"RB,P{i} ({i}),P{i},{i},RB/FLEX,5000,{cell},AAA,0,\n"
        for i, cell in enumerate(cells)
    )
    path.write_text(header + body, encoding="utf-8")
    return path


def test_home_team_is_taken_from_the_matchup_not_the_whole_cell(tmp_path):
    """`game_id` is `AWAY@HOME` alone; using the whole Game Info cell is the
    documented way to produce WEATHER_EVIDENCE_GAME_COVERAGE_MISMATCH."""

    path = _salary(
        tmp_path / "s.csv",
        [
            "CAR@ATL 09/20/2026 01:00PM ET",
            "CAR@ATL 09/20/2026 01:00PM ET",
            "MIA@SF 09/20/2026 04:25PM ET",
        ],
    )
    assert sorted(fetch.home_teams(path)) == ["ATL", "SF"]


def test_duplicate_games_collapse_to_one_capture_each(tmp_path):
    path = _salary(tmp_path / "s.csv", ["GB@NYJ 09/20/2026 01:00PM ET"] * 40)
    assert fetch.home_teams(path) == ["NYJ"]


def test_a_malformed_matchup_is_skipped_rather_than_guessed(tmp_path):
    path = _salary(
        tmp_path / "s.csv",
        ["NOTAMATCHUP 09/20/2026 01:00PM ET", "CLE@TB 09/20/2026 01:00PM ET"],
    )
    assert fetch.home_teams(path) == ["TB"]


def test_fetch_failure_is_a_named_stop_that_forbids_inventing_a_value(monkeypatch):
    """A 403 at a proxy must end the script, not fall back to a default."""

    def boom(*_args, **_kwargs):
        raise fetch.urllib.error.URLError("Tunnel connection failed: 403 Forbidden")

    monkeypatch.setattr(fetch.urllib.request, "urlopen", boom)
    monkeypatch.setattr(fetch.time, "sleep", lambda _s: None)
    with pytest.raises(SystemExit) as caught:
        fetch.get("https://api.weather.gov/points/1,2")
    message = str(caught.value)
    assert "FETCH_FAILED" in message
    assert "Never invent a value" in message


def test_weather_enum_matches_the_contract():
    """The enum has no UNKNOWN member; that is the whole reason this is a gate."""

    assert set(fetch.ENUM) == {
        "CLEAR", "INDOOR_OR_CLEAR", "MIXED", "RAIN", "SNOW", "WIND",
    }
    assert "UNKNOWN" not in fetch.ENUM


def test_known_gridpoints_survives_a_missing_file(monkeypatch, tmp_path):
    monkeypatch.setattr(fetch, "GRIDPOINTS", tmp_path / "absent.json")
    assert fetch.known_gridpoints() == {}


def test_pinned_file_parses_as_json():
    data = json.loads(fetch.GRIDPOINTS.read_text(encoding="utf-8"))
    assert "teams" in data
