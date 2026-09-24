#!/usr/bin/env python3
"""Capture the `api.weather.gov` gridpoint forecasts a Classic slate needs.

Standard library only, so it runs on any machine that can reach the host,
including one with no project environment. It is the companion to
`make_classic_weather_evidence.py`, which formats captures but deliberately
never fetches: this fetches, and equally deliberately never judges.

Why it exists. On 2026-09-20 a live 13-game Classic slate was lost because the
build session's egress proxy refused `api.weather.gov`, and the weather enum is
required for every non-dome game before a prior package can freeze. The capture
does not have to happen in the session that builds. It has to be real bytes
with the forecast's own `generatedAt`, hashed and bound. This script lets the
capture run wherever the host is reachable, so a blocked build session is no
longer a lost slate.

Freshness is the constraint that shapes how you schedule it: a weather package
expires six hours after capture, capped at game lock. Run it inside that window,
not the night before.

The lock clock (R31, Session 07b). The delivery deadline is
`--delivery-deadline-utc`, or by default the earliest `Game Info` lock minus 5
minutes. Requests stop 5 minutes before it, as `run-slate`'s improvement does;
each request's timeout is `min(30 s, the time left)` and each retry pause
`min(2**n s, the time left)`, and with under 1 s left the script exits
`FETCH_DEADLINE_REACHED` without starting a request. Where this Python has no
IANA time zone data (a bare Windows install has none) or a `Game Info` time
cannot be read, it says so, names `--delivery-deadline-utc`, and keeps the
fixed 30 s timeouts and 1 s and 2 s pauses. It never guesses a lock.

Usage:

    python3 scripts/fetch_weather_captures.py \\
        --salaries <run>/inputs/DKSalaries.csv \\
        --out-dir  <run>/weather \\
        [--delivery-deadline-utc 2026-09-27T16:55:00Z]

It writes `<out-dir>/captures/<team>.json` per game and `<out-dir>/plan.json`,
then tells you which entries still need a `weather_state` decided by a human.
Feed the result to:

    python3 scripts/make_classic_weather_evidence.py \\
        --salaries <salary> --plan <out-dir>/plan.json --out-dir <out-dir>

Two things this script will not do, because neither is its call to make:

* it never invents a `weather_state`. A retractable roof is an observation of
  whether the roof is open, and no forecast carries that. Those entries are
  written as `REPLACE_ME` and the script says so loudly.
* it never trusts a gridpoint it did not check. Every resolved point is
  reported with the city `api.weather.gov` returned for it, which is how
  `scripts/nws_gridpoints.json` was built and checked in the first place.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

REPO_ROOT = Path(__file__).resolve().parent.parent
GRIDPOINTS = REPO_ROOT / "scripts" / "nws_gridpoints.json"

UA = "nfl-dfs-weather-capture/1.0"
ENUM = ("CLEAR", "INDOOR_OR_CLEAR", "MIXED", "RAIN", "SNOW", "WIND")

# The lock clock. This script cannot import `nfl_dfs`, so it repeats
# `deadline.py`'s two reserves, and a test holds them equal: delivery is due
# `HANDOFF_RESERVE` before the earliest lock (R31), and requests stop
# `FINISH_RESERVE` before delivery, where `run-slate`'s improvement stops
# (`config/runtime.json`'s 10 minutes before lock, less R31's 5).
HANDOFF_RESERVE = timedelta(minutes=5)
FINISH_RESERVE = timedelta(minutes=5)
REQUEST_TIMEOUT_SECONDS = 30.0
REQUEST_MINIMUM_SECONDS = 1.0
# `Game Info` as DraftKings writes it and `nfl_dfs.dk` parses it.
GAME_INFO = re.compile(
    r"^(?P<away>[A-Z]{2,3})@(?P<home>[A-Z]{2,3})\s+"
    r"(?P<date>\d{2}/\d{2}/\d{4})\s+(?P<time>\d{2}:\d{2}[AP]M)\s+ET$"
)
LOCK_ZONE = "America/New_York"

# Operator-supplied stadium coordinates, keyed by the DraftKings home-team
# abbreviation. These are inputs to a live `/points` lookup, never a substitute
# for one: the script resolves each to a gridpoint and prints the city NWS
# returned so it can be checked. Verified gridpoints already in
# `scripts/nws_gridpoints.json` are preferred over resolving again.
STADIUMS: dict[str, tuple[str, float, float, str]] = {
    "ARI": ("State Farm Stadium", 33.5276, -112.2626, "Glendale"),
    "ATL": ("Mercedes-Benz Stadium", 33.7554, -84.4008, "Atlanta"),
    "BAL": ("M&T Bank Stadium", 39.2780, -76.6227, "Baltimore"),
    "BUF": ("Highmark Stadium", 42.7738, -78.7870, "Orchard Park"),
    "CAR": ("Bank of America Stadium", 35.2258, -80.8528, "Charlotte"),
    "CHI": ("Soldier Field", 41.8623, -87.6167, "Chicago"),
    "CIN": ("Paycor Stadium", 39.0955, -84.5161, "Cincinnati"),
    "CLE": ("Huntington Bank Field", 41.5061, -81.6995, "Cleveland"),
    "DAL": ("AT&T Stadium", 32.7473, -97.0945, "Arlington"),
    "DEN": ("Empower Field at Mile High", 39.7439, -105.0201, "Denver"),
    "DET": ("Ford Field", 42.3400, -83.0456, "Detroit"),
    "GB": ("Lambeau Field", 44.5013, -88.0622, "Green Bay"),
    "HOU": ("NRG Stadium", 29.6847, -95.4107, "Houston"),
    "IND": ("Lucas Oil Stadium", 39.7601, -86.1639, "Indianapolis"),
    "JAX": ("EverBank Stadium", 30.3239, -81.6373, "Jacksonville"),
    "KC": ("GEHA Field at Arrowhead", 39.0489, -94.4839, "Kansas City"),
    "LAC": ("SoFi Stadium", 33.9535, -118.3392, "Inglewood"),
    "LAR": ("SoFi Stadium", 33.9535, -118.3392, "Inglewood"),
    "LV": ("Allegiant Stadium", 36.0909, -115.1833, "Las Vegas"),
    "MIA": ("Hard Rock Stadium", 25.9580, -80.2389, "Miami Gardens"),
    "MIN": ("U.S. Bank Stadium", 44.9736, -93.2575, "Minneapolis"),
    "NE": ("Gillette Stadium", 42.0909, -71.2643, "Foxborough"),
    "NO": ("Caesars Superdome", 29.9511, -90.0812, "New Orleans"),
    "NYG": ("MetLife Stadium", 40.8136, -74.0745, "East Rutherford"),
    "NYJ": ("MetLife Stadium", 40.8136, -74.0745, "East Rutherford"),
    "PHI": ("Lincoln Financial Field", 39.9008, -75.1675, "Philadelphia"),
    "PIT": ("Acrisure Stadium", 40.4468, -80.0158, "Pittsburgh"),
    "SEA": ("Lumen Field", 47.5952, -122.3316, "Seattle"),
    "SF": ("Levi's Stadium", 37.4030, -121.9700, "Santa Clara"),
    "TB": ("Raymond James Stadium", 27.9759, -82.5033, "Tampa"),
    "TEN": ("Nissan Stadium", 36.1665, -86.7713, "Nashville"),
    "WAS": ("Northwest Stadium", 38.9077, -76.8645, "Landover"),
}

# Fixed-roof and retractable venues. A fixed roof is resolved by the frozen
# schedule and needs no enum here. A retractable one cannot be: whether the roof
# is open on the day is an observation, so these are flagged for a human.
RETRACTABLE = {"ARI", "ATL", "DAL", "HOU", "IND", "LV"}


def utc_now() -> datetime:
    """The wall clock; tests replace it."""

    return datetime.now(timezone.utc)


def seconds_left(stop: datetime) -> float:
    return (stop - utc_now()).total_seconds()


def deadline_reached(url: str, stop: datetime, last: Exception | None = None) -> SystemExit:
    tried = f"\n  The last attempt failed: {last}" if last is not None else ""
    return SystemExit(
        f"FETCH_DEADLINE_REACHED before {url}\n"
        f"  Requests stop at {stop.isoformat()}, {FINISH_RESERVE.total_seconds() / 60:g} minutes"
        f" before the delivery deadline, and {max(0.0, seconds_left(stop)):.1f} s are left,"
        f" under {REQUEST_MINIMUM_SECONDS:g} s. No request was started.{tried}\n"
        "  Captures already written stay on disk; plan.json is not written. Never invent a value."
    )


def get(url: str, retries: int = 3, *, stop: datetime | None = None) -> dict:
    """One JSON document, retried; with `stop`, never past it.

    Each request's timeout is `min(30, seconds left)` and each pause
    `min(2**attempt, seconds left)`; under 1 s left no request starts.
    """

    last: Exception | None = None
    for attempt in range(retries):
        timeout = REQUEST_TIMEOUT_SECONDS
        if stop is not None:
            left = seconds_left(stop)
            if left < REQUEST_MINIMUM_SECONDS:
                raise deadline_reached(url, stop, last)
            timeout = min(REQUEST_TIMEOUT_SECONDS, left)
        try:
            request = urllib.request.Request(
                url, headers={"User-Agent": UA, "Accept": "application/geo+json"}
            )
            with urllib.request.urlopen(
                request, timeout=timeout, context=ssl.create_default_context()
            ) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last = exc
            if attempt + 1 < retries:
                pause = float(2**attempt)
                if stop is not None:
                    pause = max(0.0, min(pause, seconds_left(stop)))
                time.sleep(pause)
    raise SystemExit(
        f"FETCH_FAILED after {retries} tries: {url}\n  {last}\n"
        "  If this is a 403 at a proxy, the host is blocked for this session.\n"
        "  Run this script somewhere that can reach it. Never invent a value."
    )


def known_gridpoints() -> dict[str, str]:
    try:
        data = json.loads(GRIDPOINTS.read_text(encoding="utf-8"))
    except OSError:
        return {}
    return {
        team: entry["forecast"]
        for team, entry in data.get("teams", {}).items()
        if entry.get("forecast")
    }


def home_teams(salary_csv: Path) -> list[str]:
    """Home team per distinct game, from `Game Info` cells of the form
    `AWAY@HOME MM/DD/YYYY HH:MMPM ET`."""

    with salary_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    matchups = {
        (row.get("Game Info") or "").strip().split()[0]
        for row in rows
        if (row.get("Game Info") or "").strip()
    }
    teams = []
    for matchup in sorted(matchups):
        if "@" not in matchup:
            continue
        teams.append(matchup.split("@")[1])
    return teams


def earliest_lock(salary_csv: Path) -> tuple[datetime | None, str | None]:
    """(the earliest `Game Info` lock in UTC, None), or (None, why it cannot be read).

    Every matchup cell must carry a readable time: the earliest lock of the
    cells that parse could be later than the one that did not.
    """

    try:
        zone = ZoneInfo(LOCK_ZONE)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        return None, (
            f"this Python has no IANA time zone data ({LOCK_ZONE}: {exc}); on Windows it comes"
            " from the tzdata package, which only the project environment installs"
        )
    with salary_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        cells = {(row.get("Game Info") or "").strip() for row in csv.DictReader(handle)}
    locks = []
    for cell in sorted(cells):
        if "@" not in cell.split(" ", 1)[0]:
            continue
        match = GAME_INFO.match(cell)
        if match is None:
            return None, f"the Game Info cell {cell!r} has no lock time this script can read"
        local = datetime.strptime(f"{match.group('date')} {match.group('time')}", "%m/%d/%Y %I:%M%p")
        locks.append(local.replace(tzinfo=zone).astimezone(timezone.utc))
    if not locks:
        return None, "no Game Info cell names a game and a lock time"
    return min(locks), None


def parse_deadline(value: str) -> datetime:
    """An aware ISO-8601 moment in UTC; a naive one is refused, as `run-slate` refuses it."""

    moment = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if moment.tzinfo is None:
        raise ValueError(f"{value!r} has no UTC offset")
    return moment.astimezone(timezone.utc)


def request_stop(requested: str | None, salary_csv: Path) -> tuple[datetime | None, str]:
    """(when requests stop, what the operator is told); None keeps the fixed clocks."""

    if requested is not None:
        deadline, source = parse_deadline(requested), "--delivery-deadline-utc"
    else:
        lock, why = earliest_lock(salary_csv)
        if lock is None:
            return None, (
                f"NO DELIVERY DEADLINE: {why}. Requests keep their fixed"
                f" {REQUEST_TIMEOUT_SECONDS:g} s timeouts and 1 s and 2 s retry pauses, with nothing"
                " stopping them at the lock. Pass --delivery-deadline-utc (the earliest lock minus"
                " 5 minutes, in UTC) to bound them; this script will not guess the lock."
            )
        deadline = lock - HANDOFF_RESERVE
        source = f"the earliest Game Info lock {lock.isoformat()} minus 5 minutes"
    stop = deadline - FINISH_RESERVE
    return stop, (
        f"delivery deadline {deadline.isoformat()} ({source}); requests stop at {stop.isoformat()}"
    )


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--salaries", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument(
        "--delivery-deadline-utc",
        default=None,
        help="aware ISO-8601 delivery deadline (default: the earliest Game Info lock minus"
             " 5 minutes); requests stop 5 minutes before it",
    )
    args = parser.parse_args(argv)

    try:
        stop, clock_line = request_stop(args.delivery_deadline_utc, Path(args.salaries))
    except ValueError as exc:
        parser.error(f"--delivery-deadline-utc: {exc}")
    print(clock_line)
    if stop is not None and seconds_left(stop) < REQUEST_MINIMUM_SECONDS:
        raise deadline_reached("the first request", stop)

    teams = home_teams(Path(args.salaries))
    if not teams:
        raise SystemExit("no games parsed from the salary CSV Game Info column")

    out = Path(args.out_dir)
    captures = out / "captures"
    captures.mkdir(parents=True, exist_ok=True)

    verified = known_gridpoints()
    plan: dict[str, dict[str, str]] = {}
    needs_human: list[str] = []
    unknown: list[str] = []

    print(f"{'TEAM':5} {'SOURCE':9} {'NWS CITY':22} {'EXPECTED':18} CHECK")
    print("-" * 76)
    for team in teams:
        if team in verified:
            forecast_uri, origin, city, expect = verified[team], "pinned", "-", "-"
        elif team in STADIUMS:
            _stadium, lat, lon, expect = STADIUMS[team]
            points = get(f"https://api.weather.gov/points/{lat},{lon}", stop=stop)
            properties = points["properties"]
            relative = properties.get("relativeLocation", {}).get("properties", {})
            city = f"{relative.get('city', '?')}, {relative.get('state', '?')}"
            forecast_uri, origin = properties["forecast"], "resolved"
        else:
            unknown.append(team)
            continue

        forecast = get(forecast_uri, stop=stop)
        path = captures / f"{team.lower()}.json"
        path.write_text(json.dumps(forecast, indent=1), encoding="utf-8")

        entry = {"source_uri": forecast_uri, "path": f"captures/{team.lower()}.json"}
        if team in RETRACTABLE:
            entry["weather_state"] = "REPLACE_ME"
            needs_human.append(team)
        plan[team] = entry

        ok = "-" if origin == "pinned" else ("ok" if city.split(",")[0] == expect else "*** CHECK ***")
        print(f"{team:5} {origin:9} {city:22} {expect:18} {ok}")
        print(f"      generatedAt={forecast['properties']['generatedAt']}")

    (out / "plan.json").write_text(json.dumps(plan, indent=1), encoding="utf-8")
    print(f"\nwrote {out / 'plan.json'} and {len(plan)} captures under {captures}")

    if unknown:
        print(
            f"\nNO STADIUM COORDINATES for {unknown}. Add them to STADIUMS, or resolve"
            "\nthe gridpoint by hand and add it to scripts/nws_gridpoints.json."
            "\nThe package must cover the exact complete game set, so this is a stop."
        )
    if needs_human:
        print(
            f"\nEDIT plan.json BEFORE BUILDING: {sorted(needs_human)} are retractable"
            f"\nroofs. Replace each \"REPLACE_ME\" with one of {', '.join(ENUM)}."
            "\nThat value is your observation of whether the roof is open. No forecast"
            "\ncarries it, and this script will not guess it."
        )
    print(
        "\nCaptures expire six hours after generatedAt, capped at lock."
        "\nBuild from them inside that window."
    )
    return 1 if unknown else 0


if __name__ == "__main__":
    sys.exit(main())
