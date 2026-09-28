#!/usr/bin/env python3
"""Reassign a filled Showdown entry file's lineups so each contest's entries differ.

Written 2026-09-28 on the PHI@CHI slate, where three satellite contests held
seven of the portfolio's 36 lineups each: the thesis sleeves spread the
portfolio's game scripts, but not every contest's, and one contest had the same
Captain three times out of seven.

What it changes. Only which Entry ID holds which lineup, and only among the
rows the untouched DraftKings template left blank. A row already filled in the
template (entered by hand) never moves and never changes, though its lineup
still counts in its contest's score. Every lineup in the input file is in the
output exactly once, so the portfolio, its exposures and its captain counts are
unchanged; within-contest overlap, repeated Captains and repeated theses are
what move.

The score, per contest, summed over every pair of its lineups:
shared_people ** 2 + captain_penalty * same_captain + thesis_penalty *
same_thesis. Squaring the shared count makes one five-of-six pair cost more
than several two-of-six pairs. Theses come from an optional JSON map of Entry
ID to a label (the sleeve plan); without one that term is zero. The search is
deterministic: pairwise swaps between rows in different contests from the
input assignment and from `--restarts` seeded shuffles, keeping the lowest.

What it checks before writing. The output differs from the template only in
the six roster cells of rows the template left blank; the multiset of movable
lineups is unchanged; a line whose cells cannot be split on commas and joined
back to the same bytes (a quoted field) is refused, never guessed. It writes a
new path only. It does not validate lineups against DraftKings rules: run
`qa_showdown_portfolio.py` on the output, as for any file.

Standard library only. It establishes nothing about EV, ownership or
probability; the file stays PRIOR_ONLY / DO_NOT_UPLOAD like its input.

Example:

    python3 scripts/diversify_showdown_contests.py \\
        --salaries DKSalaries.csv --template DKEntries.csv \\
        --entries DK_REVIEW_ENTRY_v1.csv --theses sleeve_plan.json \\
        --out DK_REVIEW_ENTRY_v2.csv --record assignment_v2.json
"""

from __future__ import annotations

import argparse
import csv
import io
import itertools
import json
import random
import sys
from pathlib import Path

ROSTER = slice(4, 10)


class DiversifyError(ValueError):
    """A named refusal; nothing is written."""


def _people_by_id(salaries: Path) -> dict[str, str]:
    with salaries.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows or not {"ID", "Name", "TeamAbbrev", "Roster Position"} <= set(rows[0]):
        raise DiversifyError(f"SALARY_SCHEMA_UNRECOGNIZED:{salaries}")
    return {row["ID"].strip(): f"{row['TeamAbbrev'].strip()}|{row['Name'].strip()}" for row in rows}


def _lines(path: Path) -> tuple[list[bytes], bytes]:
    raw = path.read_bytes()
    ending = b"\r\n" if b"\r\n" in raw else b"\n"
    return raw.split(ending), ending


def _fields(line: bytes) -> list[bytes]:
    parts = line.split(b",")
    parsed = next(csv.reader(io.StringIO(line.decode("utf-8-sig"))), [])
    if [part.decode("utf-8-sig") for part in parts] != parsed:
        raise DiversifyError(f"LINE_NOT_BYTE_SPLITTABLE:{line[:40]!r}")
    return parts


def _entry_id(fields: list[bytes]) -> str:
    return fields[0].decode("utf-8-sig").strip()


def _is_entry(fields: list[bytes]) -> bool:
    return len(fields) > 10 and _entry_id(fields).isdigit()


def plan(template: Path, entries: Path, salaries: Path, theses: dict[str, str] | None):
    people = _people_by_id(salaries)
    t_lines, t_end = _lines(template)
    e_lines, e_end = _lines(entries)
    if len(t_lines) != len(e_lines) or t_end != e_end:
        raise DiversifyError("ENTRIES_GEOMETRY_DIFFERS_FROM_TEMPLATE")
    rows = []
    for index, (t_line, e_line) in enumerate(zip(t_lines, e_lines)):
        if t_line == e_line and not t_line:
            continue
        t_fields, e_fields = _fields(t_line), _fields(e_line)
        if not _is_entry(t_fields):
            if t_line != e_line:
                raise DiversifyError(f"NON_ENTRY_LINE_CHANGED:{index}")
            continue
        if len(t_fields) != len(e_fields) or t_fields[:4] != e_fields[:4] or t_fields[10:] != e_fields[10:]:
            raise DiversifyError(f"NON_ROSTER_BYTES_CHANGED:{_entry_id(t_fields)}")
        blank = all(cell == b"" for cell in t_fields[ROSTER])
        if not blank and t_fields[ROSTER] != e_fields[ROSTER]:
            raise DiversifyError(f"PREFILLED_ROW_CHANGED:{_entry_id(t_fields)}")
        cells = e_fields[ROSTER]
        if not all(cells):
            raise DiversifyError(f"ROW_NOT_FILLED:{_entry_id(t_fields)}")
        ids = [cell.decode("utf-8-sig").strip() for cell in cells]
        unknown = [dk_id for dk_id in ids if dk_id not in people]
        if unknown:
            raise DiversifyError(f"UNKNOWN_DK_ID:{_entry_id(t_fields)}:{unknown}")
        entry_id = _entry_id(t_fields)
        rows.append({
            "line": index, "entry_id": entry_id, "contest_id": e_fields[2].decode("utf-8-sig").strip(),
            "movable": blank, "cells": cells, "people": frozenset(people[dk_id] for dk_id in ids),
            "captain": people[ids[0]], "thesis": (theses or {}).get(entry_id),
        })
    return rows, e_lines, e_end


def optimize(rows, *, captain_penalty: float, thesis_penalty: float, restarts: int, seed: int):
    lineups = rows  # lineup k starts in row k
    slots_by_contest: dict[str, list[int]] = {}
    for slot, row in enumerate(rows):
        slots_by_contest.setdefault(row["contest_id"], []).append(slot)
    movable = [slot for slot, row in enumerate(rows) if row["movable"]]

    def pair(a: int, b: int) -> float:
        x, y = lineups[a], lineups[b]
        same_thesis = x["thesis"] is not None and x["thesis"] == y["thesis"]
        return (len(x["people"] & y["people"]) ** 2 + captain_penalty * (x["captain"] == y["captain"])
                + thesis_penalty * same_thesis)

    cost = [[pair(a, b) for b in range(len(rows))] for a in range(len(rows))]

    def contest_cost(assign, contest):
        return sum(cost[assign[i]][assign[j]] for i, j in itertools.combinations(slots_by_contest[contest], 2))

    def total(assign):
        return sum(contest_cost(assign, contest) for contest in slots_by_contest)

    def search(assign):
        assign = list(assign)
        improved = True
        while improved:
            improved = False
            for i, j in itertools.combinations(movable, 2):
                ci, cj = rows[i]["contest_id"], rows[j]["contest_id"]
                if ci == cj:
                    continue
                before = contest_cost(assign, ci) + contest_cost(assign, cj)
                assign[i], assign[j] = assign[j], assign[i]
                if contest_cost(assign, ci) + contest_cost(assign, cj) < before:
                    improved = True
                else:
                    assign[i], assign[j] = assign[j], assign[i]
        return assign

    start = list(range(len(rows)))
    best = search(start)
    rng = random.Random(seed)
    for _ in range(restarts):
        shuffled = list(start)
        order = list(movable)
        rng.shuffle(order)
        for slot, lineup in zip(movable, order):
            shuffled[slot] = lineup
        candidate = search(shuffled)
        if total(candidate) < total(best):
            best = candidate
    return best, total(start), total(best), slots_by_contest


def contest_report(rows, assign, slots_by_contest):
    report = {}
    for contest, slots in sorted(slots_by_contest.items()):
        if len(slots) < 2:
            continue
        chosen = [rows[assign[slot]] for slot in slots]
        shared = [len(a["people"] & b["people"]) for a, b in itertools.combinations(chosen, 2)]
        report[contest] = {
            "entries": len(slots),
            "max_shared_people": max(shared),
            "mean_shared_people": round(sum(shared) / len(shared), 3),
            "distinct_captains": len({row["captain"] for row in chosen}),
            "distinct_theses": len({row["thesis"] for row in chosen if row["thesis"] is not None}),
            "in_every_lineup": sorted(set.intersection(*(set(row["people"]) for row in chosen))),
        }
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--salaries", required=True, type=Path)
    parser.add_argument("--template", required=True, type=Path, help="the untouched DKEntries download")
    parser.add_argument("--entries", required=True, type=Path, help="the filled file to reassign")
    parser.add_argument("--out", required=True, type=Path, help="a new path; never an existing file")
    parser.add_argument("--theses", type=Path, help="JSON map of Entry ID to thesis label")
    parser.add_argument("--record", type=Path, help="write the mapping and both reports here (new path)")
    parser.add_argument("--captain-penalty", type=float, default=12.0)
    parser.add_argument("--thesis-penalty", type=float, default=3.0)
    parser.add_argument("--restarts", type=int, default=300)
    parser.add_argument("--seed", type=int, default=20260928)
    args = parser.parse_args(argv)
    try:
        for target in (args.out, args.record):
            if target is not None and target.exists():
                raise DiversifyError(f"OUTPUT_EXISTS:{target}")
        if args.out.resolve() in {args.template.resolve(), args.entries.resolve(), args.salaries.resolve()}:
            raise DiversifyError("OUTPUT_IS_AN_INPUT")
        theses = json.loads(args.theses.read_text(encoding="utf-8")) if args.theses else None
        rows, lines, ending = plan(args.template, args.entries, args.salaries, theses)
        assign, before, after, slots = optimize(
            rows, captain_penalty=args.captain_penalty, thesis_penalty=args.thesis_penalty,
            restarts=args.restarts, seed=args.seed)
        out_lines = list(lines)
        for slot, row in enumerate(rows):
            fields = lines[row["line"]].split(b",")
            fields[ROSTER] = rows[assign[slot]]["cells"]
            out_lines[row["line"]] = b",".join(fields)
        moved = [row["cells"] for row in rows if row["movable"]]
        placed = [rows[assign[slot]]["cells"] for slot, row in enumerate(rows) if row["movable"]]
        if sorted(map(tuple, moved)) != sorted(map(tuple, placed)):
            raise DiversifyError("LINEUP_MULTISET_CHANGED")
        if any(assign[slot] != slot for slot, row in enumerate(rows) if not row["movable"]):
            raise DiversifyError("PREFILLED_ROW_MOVED")
        payload = ending.join(out_lines)
        _check_against_template(args.template, payload, ending)
        record = {
            "schema_version": "nfl_showdown_contest_diversification_v1",
            "does_not_establish": ["UPLOAD_CLEARANCE", "EV", "WIN_PROBABILITY", "LINEUP_LEGALITY"],
            "score": {"captain_penalty": args.captain_penalty, "thesis_penalty": args.thesis_penalty,
                      "restarts": args.restarts, "seed": args.seed, "before": before, "after": after},
            "mapping_entry_to_source_entry": {row["entry_id"]: rows[assign[slot]]["entry_id"]
                                              for slot, row in enumerate(rows)},
            "contests_before": contest_report(rows, list(range(len(rows))), slots),
            "contests_after": contest_report(rows, assign, slots),
        }
        with args.out.open("xb") as handle:
            handle.write(payload)
        if args.record is not None:
            with args.record.open("x", encoding="utf-8") as handle:
                json.dump(record, handle, indent=1, sort_keys=True)
                handle.write("\n")
    except DiversifyError as exc:
        print(json.dumps({"status": "REFUSED", "error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps({"status": "WRITTEN", "out": str(args.out), "score_before": before, "score_after": after,
                      "moved_rows": sum(1 for slot in range(len(rows)) if assign[slot] != slot),
                      "contests_after": record["contests_after"]}, indent=1, sort_keys=True))
    return 0


def _check_against_template(template: Path, payload: bytes, ending: bytes) -> None:
    t_lines = template.read_bytes().split(ending)
    o_lines = payload.split(ending)
    if len(t_lines) != len(o_lines):
        raise DiversifyError("OUTPUT_GEOMETRY_DIFFERS_FROM_TEMPLATE")
    for t_line, o_line in zip(t_lines, o_lines):
        if t_line == o_line:
            continue
        t_fields, o_fields = t_line.split(b","), o_line.split(b",")
        if (len(t_fields) != len(o_fields) or t_fields[:4] != o_fields[:4] or t_fields[10:] != o_fields[10:]
                or not all(cell == b"" for cell in t_fields[ROSTER])):
            raise DiversifyError(f"OUTPUT_CHANGES_MORE_THAN_BLANK_ROSTER_CELLS:{t_line[:40]!r}")


if __name__ == "__main__":
    sys.exit(main())
