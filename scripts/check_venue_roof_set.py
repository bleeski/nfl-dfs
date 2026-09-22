#!/usr/bin/env python3
"""Check a current schedule for a retractable venue this repository does not list.

`nfl_dfs.venues.RETRACTABLE_ROOF_HOME_TEAMS` is a hand-maintained stadium fact,
and it is the one part of the blank-roof resolution that cannot keep itself
current: the day a sixth retractable roof opens, that venue's unplayed games
carry a blank `roof` that resolves to nothing, and the engine quietly goes back
to demanding an `api.weather.gov` capture for a game played indoors.

No test can catch that. A committed fixture is a snapshot, and a snapshot cannot
contain a stadium that does not exist yet. Only a run against a current schedule
can, which is what this script is for.

Usage:

    python3 scripts/check_venue_roof_set.py --games <games.csv> [--season 2026]

`games.csv` is the nflverse schedule a run already freezes, for example
`data/runs/<run_id>/inputs/games.csv`. Exit 0 means every unplayed blank roof
belongs to a listed venue. Exit 1 names the home teams that do not, each of
which is either a new retractable stadium or a schedule defect. Exit 2 is a
usage or read error, so a broken invocation is never mistaken for a clean run.

This reads bytes that are already on disk. It fetches nothing.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from nfl_dfs.venues import (  # noqa: E402
    RETRACTABLE_ROOF_HOME_TEAMS,
    unlisted_blank_roof_teams,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", required=True, help="path to an nflverse games.csv")
    parser.add_argument(
        "--season",
        action="append",
        default=None,
        help="restrict to this season; repeatable. Omit to read every row.",
    )
    args = parser.parse_args(argv)

    path = Path(args.games)
    try:
        with open(path, encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except OSError as exc:
        print(f"CANNOT_READ_SCHEDULE:{path}:{exc}", file=sys.stderr)
        return 2
    if not rows:
        print(f"SCHEDULE_HAS_NO_ROWS:{path}", file=sys.stderr)
        return 2
    if "roof" not in (rows[0].keys()):
        print(f"SCHEDULE_HAS_NO_ROOF_COLUMN:{path}", file=sys.stderr)
        return 2

    unlisted = unlisted_blank_roof_teams(rows, seasons=args.season)
    listed = ",".join(sorted(RETRACTABLE_ROOF_HOME_TEAMS))
    scope = ",".join(args.season) if args.season else "all seasons"

    if not unlisted:
        print(f"VENUE_ROOF_SET_CURRENT:listed={listed}:scope={scope}:rows={len(rows)}")
        return 0

    print(
        f"UNLISTED_BLANK_ROOF_VENUES:{','.join(unlisted)}"
        f":listed={listed}:scope={scope}",
        file=sys.stderr,
    )
    print(
        "Each named team has an unplayed game with no recorded roof. That is a "
        "new retractable stadium, or a schedule defect. Add a genuinely "
        "retractable venue to RETRACTABLE_ROOF_HOME_TEAMS in "
        "src/nfl_dfs/venues.py; never add one to silence this.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
