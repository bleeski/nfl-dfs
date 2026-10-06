#!/usr/bin/env python3
"""List the DraftKings players a slate's nflverse roster file says are not on the active roster.

Written 2026-10-05 from the ATL@NO Showdown, where 13 of 56 people in the salary file were on a practice squad (nflverse status
`DEV`) with a blank DraftKings status. A non-elevated practice-squad player cannot play and appears on no inactive list, so his
blank status and any old-team prior keep him selectable at $200 (DET@CAR, 2026-10-04: Casey Washington in 7 of 28 rows). The
check was a judgment step done by hand; this makes it one command.

The roster file is the one every `--build-priors` run already captures through `sources.py` (nflverse weekly rosters, the
`season,team,position,depth_chart_position,jersey_number,status,full_name,...` header). Pass it with `--rosters`, or pass the run
directory with `--run-dir` and the script finds it by header under `prior_review/priors/proposal/raw/`.

For each person in the salary file it takes the latest week's row on his DraftKings team, matched by exact name, then by name with
the suffix (Jr., Sr., II, III, IV, V) removed, then by either half of a hyphenated surname. Every match carries its method; a
non-exact match is a proposal. People with no row are listed as `NO_ROSTER_ROW`.

It decides nothing. `not_active` lists people whose status is not `ACT` and whom DraftKings does not already mark unavailable,
with both role IDs and the `--exclude` arguments for a `--request` rerun. A club can elevate a practice-squad player after the
roster snapshot: check the team's elevation post for the game before excluding (docs/claude/working.md, Showdown judgment pass).
It never reads the salary file's points column, writes no number, and clears no gate.

    python scripts/practice_squad_check.py --salaries DKSalaries.csv --run-dir data/runs/<run_id>
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

ROSTER_HEADER_PREFIX = "season,team,position,depth_chart_position,jersey_number,status,full_name"
DK_UNAVAILABLE = {"OUT", "IR", "D"}
SUFFIX = re.compile(r"\s+(jr\.?|sr\.?|ii|iii|iv|v)$", re.IGNORECASE)
DOES_NOT_ESTABLISH = [
    "OFFICIAL_ACTIVE_STATUS",
    "GAME_DAY_ELEVATION",
    "A_CURRENT_ROLE",
    "UPLOAD_CLEARANCE",
]


def _norm(name: str) -> str:
    return " ".join(name.strip().lower().split())


def _strip_suffix(name: str) -> str:
    return SUFFIX.sub("", _norm(name))


def find_roster_file(run_dir: Path) -> Path:
    raw = run_dir / "prior_review" / "priors" / "proposal" / "raw"
    for path in sorted(raw.glob("*.csv")):
        with path.open("r", encoding="utf-8", newline="") as handle:
            if handle.readline().startswith(ROSTER_HEADER_PREFIX):
                return path
    raise SystemExit(f"no nflverse roster file under {raw}")


def latest_rows(rosters: Path, teams: set[str]) -> dict[str, dict[str, dict[str, str]]]:
    """Team -> normalized full name -> that person's row from the team's latest week."""
    by_team: dict[str, list[dict[str, str]]] = {team: [] for team in teams}
    with rosters.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("team") in by_team:
                by_team[row["team"]].append(row)
    out: dict[str, dict[str, dict[str, str]]] = {}
    for team, rows in by_team.items():
        def order(row: dict[str, str]) -> tuple[int, int]:
            return (int(row.get("season") or 0), int(row.get("week") or 0))
        if not rows:
            out[team] = {}
            continue
        latest = max(order(row) for row in rows)
        out[team] = {_norm(row["full_name"]): row for row in rows if order(row) == latest}
    return out


def match(name: str, people: dict[str, dict[str, str]]) -> tuple[dict[str, str] | None, str]:
    exact = people.get(_norm(name))
    if exact is not None:
        return exact, "EXACT_NAME_TEAM"
    bare = _strip_suffix(name)
    hits = [row for key, row in people.items() if _strip_suffix(key) == bare]
    if len(hits) == 1:
        return hits[0], "NAME_WITHOUT_SUFFIX_TEAM"
    first, _, last = bare.rpartition(" ")
    if "-" in last:
        halves = {f"{first} {part}" for part in last.split("-")}
        hits = [row for key, row in people.items() if _strip_suffix(key) in halves]
        if len(hits) == 1:
            return hits[0], "HYPHENATED_SURNAME_HALF_TEAM"
    return None, "NO_ROSTER_ROW"


def check(salaries: Path, rosters: Path) -> dict[str, object]:
    with salaries.open("r", encoding="utf-8-sig", newline="") as handle:
        salary_rows = list(csv.DictReader(handle))
    people: dict[tuple[str, str], dict[str, object]] = {}
    for row in salary_rows:
        if row["Position"] == "DST":
            continue
        key = (row["Name"], row["TeamAbbrev"])
        entry = people.setdefault(
            key,
            {
                "name": row["Name"],
                "team": row["TeamAbbrev"],
                "position": row["Position"],
                "dk_status": (row.get("Status") or "").strip().upper(),
                "dk_ids": [],
                "max_salary": 0,
            },
        )
        entry["dk_ids"].append(row["ID"])
        entry["max_salary"] = max(int(entry["max_salary"]), int(row["Salary"]))
    roster = latest_rows(rosters, {team for _, team in people})
    report: list[dict[str, object]] = []
    for (name, team), entry in sorted(people.items(), key=lambda item: (item[0][1], item[0][0])):
        row, method = match(name, roster.get(team, {}))
        entry["nflverse_status"] = row.get("status") if row else None
        entry["nflverse_name"] = row.get("full_name") if row else None
        entry["nflverse_week"] = int(row["week"]) if row and row.get("week") else None
        entry["match_method"] = method
        report.append(entry)
    not_active = [
        entry
        for entry in report
        if entry["nflverse_status"] not in (None, "ACT") and entry["dk_status"] not in DK_UNAVAILABLE
    ]
    no_row = [entry for entry in report if entry["nflverse_status"] is None]
    return {
        "schema_version": "nfl_practice_squad_check_v1",
        "salaries": str(salaries),
        "rosters": str(rosters),
        "people": len(report),
        "not_active": not_active,
        "no_roster_row": no_row,
        "exclude_args": " ".join(f"--exclude {dk_id}" for entry in not_active for dk_id in entry["dk_ids"]),
        "does_not_establish": DOES_NOT_ESTABLISH,
        "next": "Check each team's elevation post for this game; exclude only the people it does not name.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--salaries", required=True, type=Path)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--rosters", type=Path, help="nflverse weekly roster CSV")
    source.add_argument("--run-dir", type=Path, help="a --build-priors run directory")
    args = parser.parse_args(argv)
    rosters = args.rosters if args.rosters else find_roster_file(args.run_dir)
    json.dump(check(args.salaries, rosters), sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
