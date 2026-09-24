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


# ----------------------------------------------------------------- the lock clock (Session 07b)

FIXTURES = REPO_ROOT / "tests" / "fixtures" / "supplied"
CLASSIC_SALARY = FIXTURES / "DKSalaries Salary CSV Classic.csv"
SHOWDOWN_SALARY = FIXTURES / "DKSalaries Salary CSV Showdown.csv"


class _Clock:
    """The script's wall clock, moved only by the stubs below."""

    def __init__(self, moment):
        self.moment = moment

    def __call__(self):
        return self.moment

    def advance(self, seconds: float) -> None:
        from datetime import timedelta

        self.moment += timedelta(seconds=seconds)


def _clocked(monkeypatch, moment):
    clock = _Clock(moment)
    pauses: list[float] = []

    def sleep(seconds: float) -> None:
        pauses.append(seconds)
        clock.advance(seconds)

    monkeypatch.setattr(fetch, "utc_now", clock)
    monkeypatch.setattr(fetch.time, "sleep", sleep)
    return clock, pauses


def test_the_reserves_are_deadline_pys():
    """The script cannot import `nfl_dfs`; these are the numbers it repeats."""

    from nfl_dfs import deadline

    runtime = json.loads((REPO_ROOT / "config" / "runtime.json").read_text(encoding="utf-8"))
    assert fetch.HANDOFF_RESERVE == deadline.HANDOFF_RESERVE
    assert fetch.FINISH_RESERVE == deadline.finish_reserve(deadline.runtime_stop_minutes(runtime))
    assert fetch.REQUEST_TIMEOUT_SECONDS == deadline.FETCH_DEFAULT_SECONDS
    assert fetch.REQUEST_MINIMUM_SECONDS == deadline.FETCH_MINIMUM_SECONDS


@pytest.mark.parametrize("salary", (CLASSIC_SALARY, SHOWDOWN_SALARY), ids=("classic", "showdown"))
def test_the_default_deadline_is_the_engines(salary):
    from nfl_dfs.deadline import default_deadline, earliest_lock
    from nfl_dfs.dk import parse_salaries

    games = parse_salaries(salary).games
    lock, why = fetch.earliest_lock(salary)
    assert why is None and lock == earliest_lock(games)
    stop, line = fetch.request_stop(None, salary)
    assert stop == default_deadline(games) - fetch.FINISH_RESERVE
    assert line.startswith(f"delivery deadline {default_deadline(games).isoformat()}")


def test_a_slow_host_gets_the_time_left_and_nothing_past_it(monkeypatch):
    """The card's case: requests stop 45 s from now; every attempt times out."""

    from datetime import datetime, timedelta, timezone

    start = datetime(2026, 9, 27, 16, 0, tzinfo=timezone.utc)
    clock, pauses = _clocked(monkeypatch, start)
    timeouts: list[float] = []

    def slow(_request, *, timeout, context):
        timeouts.append(timeout)
        clock.advance(timeout)
        raise TimeoutError("timed out")

    monkeypatch.setattr(fetch.urllib.request, "urlopen", slow)
    with pytest.raises(SystemExit) as caught:
        fetch.get("https://api.weather.gov/gridpoints/X/1,2/forecast", stop=start + timedelta(seconds=45))
    assert timeouts == [30.0, pytest.approx(14.0)]
    assert pauses == [1.0, pytest.approx(0.0)]
    message = str(caught.value)
    assert message.startswith("FETCH_DEADLINE_REACHED")
    assert "No request was started" in message and "Never invent a value" in message
    assert "timed out" in message  # the attempt that did fail is named


def test_without_a_stop_the_fixed_clocks_are_unchanged(monkeypatch):
    timeouts: list[float] = []

    def failing(_request, *, timeout, context):
        timeouts.append(timeout)
        raise fetch.urllib.error.URLError("refused")

    pauses: list[float] = []
    monkeypatch.setattr(fetch.urllib.request, "urlopen", failing)
    monkeypatch.setattr(fetch.time, "sleep", pauses.append)
    with pytest.raises(SystemExit, match="^FETCH_FAILED after 3 tries"):
        fetch.get("https://api.weather.gov/points/1,2")
    assert timeouts == [30.0, 30.0, 30.0] and pauses == [1.0, 2.0]


def test_a_passed_deadline_starts_no_request(monkeypatch, tmp_path, capsys):
    from datetime import datetime, timezone

    _clocked(monkeypatch, datetime(2026, 9, 13, 16, 51, tzinfo=timezone.utc))  # 1 minute after the stop

    def never(*_args, **_kwargs):  # pragma: no cover - reaching this is the failure
        raise AssertionError("a request was started after the stop")

    monkeypatch.setattr(fetch.urllib.request, "urlopen", never)
    out = tmp_path / "weather"
    with pytest.raises(SystemExit) as caught:
        fetch.main(["--salaries", str(CLASSIC_SALARY), "--out-dir", str(out)])
    assert str(caught.value).startswith("FETCH_DEADLINE_REACHED before the first request")
    assert not out.exists()  # nothing written, nothing invented
    assert "requests stop at 2026-09-13T16:50:00+00:00" in capsys.readouterr().out


def test_an_explicit_deadline_wins_and_a_naive_one_is_refused(monkeypatch, capsys):
    from datetime import datetime, timezone

    stop, line = fetch.request_stop("2026-09-13T12:30:00-04:00", CLASSIC_SALARY)
    assert stop == datetime(2026, 9, 13, 16, 25, tzinfo=timezone.utc)
    assert "(--delivery-deadline-utc)" in line
    with pytest.raises(SystemExit) as caught:
        fetch.main(["--salaries", str(CLASSIC_SALARY), "--out-dir", "unused",
                    "--delivery-deadline-utc", "2026-09-13T12:30:00"])
    assert caught.value.code == 2
    assert "has no UTC offset" in capsys.readouterr().err


def test_without_iana_data_it_says_so_and_keeps_the_fixed_clocks(monkeypatch, tmp_path, capsys):
    """A bare Windows Python has no tzdata. The script never guesses the lock."""

    def no_zone(_key):
        raise fetch.ZoneInfoNotFoundError("No time zone found with key America/New_York")

    monkeypatch.setattr(fetch, "ZoneInfo", no_zone)
    lock, why = fetch.earliest_lock(CLASSIC_SALARY)
    assert lock is None and "no IANA time zone data" in why and "tzdata" in why
    seen: list[tuple[str, object]] = []

    def get(url, retries=3, *, stop=None):
        seen.append((url, stop))
        return {"properties": {"generatedAt": "2026-09-27T12:00:00+00:00"}}

    monkeypatch.setattr(fetch, "get", get)
    salary = _salary(tmp_path / "s.csv", ["CAR@KC 09/27/2026 01:00PM ET"])  # KC is pinned
    assert fetch.main(["--salaries", str(salary), "--out-dir", str(tmp_path / "out")]) == 0
    assert seen and all(stop is None for _url, stop in seen)
    printed = capsys.readouterr().out
    assert printed.startswith("NO DELIVERY DEADLINE: this Python has no IANA time zone data")
    assert "Pass --delivery-deadline-utc" in printed and "will not guess the lock" in printed


def test_an_unreadable_game_time_is_not_guessed_around(tmp_path):
    salary = _salary(tmp_path / "s.csv", ["CAR@ATL 09/20/2026 01:00PM ET", "MIA@SF 09/20/2026 TBD"])
    lock, why = fetch.earliest_lock(salary)
    assert lock is None and "MIA@SF 09/20/2026 TBD" in why
    stop, line = fetch.request_stop(None, salary)
    assert stop is None and line.startswith("NO DELIVERY DEADLINE:")


def test_the_script_imports_only_the_standard_library():
    """It must run on a machine with no project environment, a bare Windows Python included."""

    import ast

    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    imported = {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import)
                for alias in node.names}
    imported |= {node.module.split(".")[0] for node in ast.walk(tree)
                 if isinstance(node, ast.ImportFrom) and node.module and node.level == 0}
    assert imported and imported <= set(sys.stdlib_module_names), imported - set(sys.stdlib_module_names)
