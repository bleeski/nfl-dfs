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

Usage:

    python3 scripts/fetch_weather_captures.py \\
        --salaries <run>/inputs/DKSalaries.csv \\
        --out-dir  <run>/weather

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
import ssl
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GRIDPOINTS = REPO_ROOT / "scripts" / "nws_gridpoints.json"

UA = "nfl-dfs-weather-capture/1.0"
ENUM = ("CLEAR", "INDOOR_OR_CLEAR", "MIXED", "RAIN", "SNOW", "WIND")

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


def get(url: str, retries: int = 3) -> dict:
    last: Exception | None = None
    for attempt in range(retries):
        try:
            request = urllib.request.Request(
                url, headers={"User-Agent": UA, "Accept": "application/geo+json"}
            )
            with urllib.request.urlopen(
                request, timeout=30, context=ssl.create_default_context()
            ) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last = exc
            if attempt + 1 < retries:
                time.sleep(2**attempt)
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--salaries", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    out = Path(args.out_dir)
    captures = out / "captures"
    captures.mkdir(parents=True, exist_ok=True)

    teams = home_teams(Path(args.salaries))
    if not teams:
        raise SystemExit("no games parsed from the salary CSV Game Info column")

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
            points = get(f"https://api.weather.gov/points/{lat},{lon}")
            properties = points["properties"]
            relative = properties.get("relativeLocation", {}).get("properties", {})
            city = f"{relative.get('city', '?')}, {relative.get('state', '?')}"
            forecast_uri, origin = properties["forecast"], "resolved"
        else:
            unknown.append(team)
            continue

        forecast = get(forecast_uri)
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
