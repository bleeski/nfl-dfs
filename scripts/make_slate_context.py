#!/usr/bin/env python3
"""Derive a Classic slate context from artifacts the run already captured.

Standard library only, and it never touches the network: it reads the frozen
`nfldata` `games.csv` the prior build already fetched from an allowlisted host,
and the DraftKings salary CSV, and emits the JSON
`scripts/build_classic_portfolio.py` reads through `--slate-context`.

Why it exists. Until 2026-09-20 the builder carried three hardcoded tables —
`ITT` (24 teams), `OWN` (31 names) and `BOOST` (7 names) — holding literal
2026-09-13 Week 1 values, including role boosts keyed to Week 1 absences. Using
them on any later slate is wrong data rather than a stale preference, and
re-typing them weekly is where the mistake gets made. Implied team totals are
derivable from bytes the run already binds, so they are derived.

    implied_home = total_line / 2 + spread_line / 2
    implied_away = total_line / 2 - spread_line / 2

What it will not do:

* It never invents ownership. No projected-ownership source is on the approved
  allowlist, so `projected_ownership` is emitted empty unless the operator
  supplies a CSV they actually read. An absent leverage model is a named gap;
  a guessed one is a fabricated number.
* It never invents a role boost. `role_boosts` is empty unless supplied, and
  each supplied entry should name the absence it is tied to.

Example:

    python3 scripts/make_slate_context.py \\
        --salaries <run>/inputs/DKSalaries.csv \\
        --games    <run>/prior_review/priors/proposal/raw/<sha>.csv \\
        --out      <run>/slate_context.json
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path


def slate_matchups(salary_csv: Path) -> tuple[set[str], set[str], str | None]:
    """Return the `AWAY@HOME` matchups, the team set, and the slate date.

    The matchup is the first token of `Game Info`, never the whole cell; using
    the whole cell is the documented way to produce a game-coverage mismatch.
    """
    with salary_csv.open("r", encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        raise SystemExit(f"salary CSV has no rows: {salary_csv}")
    matchups, teams, dates = set(), set(), set()
    for row in rows:
        cell = (row.get("Game Info") or "").strip()
        parts = cell.split()
        if len(parts) < 2 or "@" not in parts[0]:
            continue
        matchups.add(parts[0])
        away, home = parts[0].split("@")
        teams.update((away, home))
        try:
            month, day, year = parts[1].split("/")
            dates.add(f"{year}-{month}-{day}")
        except ValueError:
            continue
    if not matchups:
        raise SystemExit("no AWAY@HOME matchups parsed from the Game Info column")
    return matchups, teams, (sorted(dates)[0] if dates else None)


def implied_totals(games_csv: Path, matchups: set[str], gameday: str | None) -> dict[str, float]:
    """Implied team totals from the market lines on the frozen schedule rows."""
    out: dict[str, float] = {}
    skipped: list[str] = []
    with games_csv.open("r", encoding="utf-8", newline="", errors="replace") as fh:
        for row in csv.DictReader(fh):
            matchup = f'{row.get("away_team", "")}@{row.get("home_team", "")}'
            if matchup not in matchups:
                continue
            if gameday and (row.get("gameday") or "") != gameday:
                continue
            try:
                total = float(row["total_line"])
                spread = float(row["spread_line"])
            except (KeyError, ValueError):
                skipped.append(matchup)
                continue
            out[row["home_team"]] = round(total / 2 + spread / 2, 2)
            out[row["away_team"]] = round(total / 2 - spread / 2, 2)
    if skipped:
        print(f"  no market line on the frozen schedule for: {sorted(set(skipped))}", file=sys.stderr)
    return out


def read_pairs(path: Path | None, key: str, value: str) -> dict[str, float]:
    if not path:
        return {}
    out = {}
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            try:
                out[row[key].strip()] = float(row[value])
            except (KeyError, ValueError):
                raise SystemExit(f"{path}: expected columns {key},{value}")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--salaries", required=True)
    ap.add_argument("--games", required=True,
                    help="the frozen nfldata games.csv from this run's prior package")
    ap.add_argument("--out", required=True)
    ap.add_argument("--ownership", help="optional CSV NAME,OWNERSHIP_PCT that the operator actually read")
    ap.add_argument("--role-boosts", help="optional CSV NAME,MULTIPLIER, each tied to a named absence")
    a = ap.parse_args(argv)

    matchups, teams, gameday = slate_matchups(Path(a.salaries))
    itt = implied_totals(Path(a.games), matchups, gameday)
    own = read_pairs(Path(a.ownership) if a.ownership else None, "NAME", "OWNERSHIP_PCT")
    boosts = read_pairs(Path(a.role_boosts) if a.role_boosts else None, "NAME", "MULTIPLIER")

    missing = sorted(t for t in teams if t not in itt)
    context = {
        "schema": "nfl_classic_slate_context_v1",
        "gameday": gameday,
        "games": sorted(matchups),
        "implied_team_totals": itt,
        "projected_ownership": own,
        "role_boosts": boosts,
        "teams_without_a_market_line": missing,
    }
    Path(a.out).write_text(json.dumps(context, indent=1), encoding="utf-8")

    print(f"slate {gameday}: {len(matchups)} games, {len(teams)} teams")
    print(f"implied team totals derived: {len(itt)}")
    if missing:
        print(f"  WARNING: no market line for {missing} — they fall back to the 21.0 baseline")
    print(f"projected ownership supplied: {len(own)}"
          + ("" if own else "  (none; the build carries no leverage model and must say so)"))
    print(f"role boosts supplied: {len(boosts)}")
    print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
