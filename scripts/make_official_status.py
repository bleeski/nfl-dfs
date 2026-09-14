#!/usr/bin/env python3
"""Emit the exact official-status CSV that `certify --official-statuses` requires.

Standard library only, so it runs under any Python 3.9+ without the project
environment. It writes the header
`TEAM,PLAYER_OR_GSIS_ID,STATUS,SOURCE_URL,OBSERVED_AT` with one row per distinct
DraftKings ID appearing in the assignment CSV, resolving TEAM from the salary
CSV so a player/team conflict cannot be typed by hand.

This script only formats what the operator observed. It does not fetch, verify,
or vouch for any source. `--source-url` and `--observed-at` are the operator's
attestation of where the status came from and when it was read, and the
certification gate checks their shape and freshness, not their truth.

Example:

    python scripts/make_official_status.py \\
        --salaries DKSalaries.csv \\
        --assignments assignments.csv \\
        --source-url https://www.nfl.com/injuries/ \\
        --observed-at now \\
        --out official_status.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HEADER = ("TEAM", "PLAYER_OR_GSIS_ID", "STATUS", "SOURCE_URL", "OBSERVED_AT")
FRESHNESS_WINDOW = timedelta(hours=3)


def _read_salaries(path: Path) -> "tuple[dict[str, dict[str, str]], datetime | None]":
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise SystemExit(f"salary CSV has no rows: {path}")
    by_id = {}
    for row in rows:
        dk_id = (row.get("ID") or "").strip()
        if dk_id:
            by_id[dk_id] = row
    return by_id, _lock_from_game_info(rows)


def _lock_from_game_info(rows) -> "datetime | None":
    """Read the slate lock out of `Game Info` so the window warning is data-driven.

    A Showdown file carries one kickoff. A Classic file carries one per game, and
    the slate locks at the earliest of them, so the earliest kickoff is the
    deadline every selected player's observation has to beat. Returning None for
    a multi-game file, as this did before 2026-09-12, silently dropped the
    freshness warning exactly where the operator most needs it.
    """
    values = {(row.get("Game Info") or "").strip() for row in rows}
    values.discard("")
    if not values:
        return None
    from zoneinfo import ZoneInfo

    eastern = ZoneInfo("America/New_York")
    kickoffs = []
    for text in values:
        parts = text.split()
        if len(parts) < 3:
            continue
        # "AWAY@HOME MM/DD/YYYY HH:MMPM ET"
        for fmt in ("%m/%d/%Y %I:%M%p",):
            try:
                naive = datetime.strptime(" ".join(parts[1:3]), fmt)
            except ValueError:
                continue
            # DraftKings prints Eastern. Attach the zone so the offset in force
            # on that date is used (a fixed -4 was wrong from November to March).
            kickoffs.append(naive.replace(tzinfo=eastern))
            break
    if not kickoffs:
        return None
    return min(kickoffs)


def _read_selection_ids(path: Path) -> "list[str]":
    """Read roster IDs out of a Classic prior-review selection report.

    Classic C1/C2 publish JSON, not an assignment CSV, so there is nothing for
    `--assignments` to read on that path. The selection report's
    `assignments_by_entry_id` carries the same exact DraftKings IDs.
    """
    import json

    payload = json.loads(path.read_text(encoding="utf-8"))
    assignments = payload.get("assignments_by_entry_id")
    if not isinstance(assignments, dict) or not assignments:
        raise SystemExit(
            f"selection report has no assignments_by_entry_id: {path}"
        )
    seen: list[str] = []
    for roster in assignments.values():
        for dk_id in roster or ():
            text = str(dk_id).strip()
            if text and text not in seen:
                seen.append(text)
    if not seen:
        raise SystemExit("selection report contains no roster IDs")
    return seen


def _read_pool_ids(by_id: "dict[str, dict[str, str]]") -> "list[str]":
    """Every DraftKings ID in the salary pool.

    Classic selection happens inside the run, so before a first pass there is no
    selected set to cover. Writing the whole pool lets one observation clear the
    gate whoever gets selected; it is a bigger attestation, so only claim it when
    the source you read really did cover the slate.
    """
    return list(by_id)


def _read_assignment_ids(path: Path) -> "list[str]":
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration:
            raise SystemExit(f"assignment CSV is empty: {path}")
        if not header or header[0].strip() != "Entry ID":
            raise SystemExit("assignment CSV must start with an 'Entry ID' column")
        seen = []
        for row in reader:
            if not row or not any(cell.strip() for cell in row):
                continue
            for cell in row[1:]:
                dk_id = cell.strip()
                if dk_id and dk_id not in seen:
                    seen.append(dk_id)
    if not seen:
        raise SystemExit("assignment CSV contains no roster IDs")
    return seen


def _parse_observed(value: str) -> datetime:
    if value.strip().lower() == "now":
        return datetime.now(timezone.utc).replace(microsecond=0)
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise SystemExit(
            "--observed-at must carry a timezone offset, for example "
            "2026-09-09T18:00:00-05:00"
        )
    return parsed


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--salaries", required=True)
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument(
        "--assignments", help="assignment CSV (Showdown, or any path that writes one)"
    )
    source_group.add_argument(
        "--selection",
        help="Classic prior-review selection JSON (classic_selection.json)",
    )
    source_group.add_argument(
        "--whole-pool",
        action="store_true",
        help="one row per salary-pool ID, for a Classic first pass with no selection yet",
    )
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--observed-at", required=True, help="ISO 8601 with offset, or 'now'")
    parser.add_argument("--out", required=True)
    parser.add_argument(
        "--inactive",
        default="",
        help="comma-separated DraftKings IDs to mark INACTIVE instead of ACTIVE",
    )
    args = parser.parse_args(argv)

    if not args.source_url.lower().startswith("https://"):
        raise SystemExit("--source-url must be an https:// URL")

    salary_path = Path(args.salaries)
    by_id, lock_at = _read_salaries(salary_path)
    if args.assignments:
        selected = _read_assignment_ids(Path(args.assignments))
    elif args.selection:
        selected = _read_selection_ids(Path(args.selection))
    else:
        selected = _read_pool_ids(by_id)
    observed = _parse_observed(args.observed_at)

    inactive = {value.strip() for value in args.inactive.split(",") if value.strip()}
    unknown = [dk_id for dk_id in selected if dk_id not in by_id]
    if unknown:
        raise SystemExit(f"roster IDs are not in the salary pool: {unknown}")
    stray = sorted(inactive.difference(selected))
    if stray:
        raise SystemExit(f"--inactive names IDs that are not covered: {stray}")

    out_path = Path(args.out)
    with out_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(HEADER)
        for dk_id in selected:
            row = by_id[dk_id]
            writer.writerow(
                [
                    (row.get("TeamAbbrev") or "").strip(),
                    dk_id,
                    "INACTIVE" if dk_id in inactive else "ACTIVE",
                    args.source_url,
                    observed.isoformat(),
                ]
            )

    print(f"wrote {out_path} with {len(selected)} rows, observed {observed.isoformat()}")
    if inactive:
        print(
            f"marked INACTIVE: {sorted(inactive)}. Certification will FAIL while an "
            "inactive player is selected. Replace him and rerun."
        )
    if lock_at is not None:
        window_start = lock_at - FRESHNESS_WINDOW
        print(f"kickoff from Game Info: {lock_at.isoformat()}")
        print(f"observation window:     {window_start.isoformat()} .. {lock_at.isoformat()}")
        if observed < window_start:
            print(
                "WARNING: this observation is older than kickoff minus three hours. "
                "certify will report official_inactive_status:STALE. Re-read the "
                "source and regenerate.",
                file=sys.stderr,
            )
        if observed > lock_at:
            print(
                "WARNING: this observation is after kickoff. certify will report "
                "CONFLICTED.",
                file=sys.stderr,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
