#!/usr/bin/env python3
"""Reassign a filled entry file's lineups so each contest's entries differ.

Written 2026-09-28 on the PHI@CHI slate, where three satellite contests held
seven of the portfolio's 36 lineups each and one held the same Captain three
times out of seven. Since Session 50 the search lives in
`src/nfl_dfs/contest_assignment.py` (`within_contest_diversity_v1`), which
`run-slate` applies on its own; this script is the thin wrapper for a file
built outside `run-slate`. It works on Showdown and, since Session 50, Classic
files (the mode is read from the template's header: a `CPT` column is Showdown).

What it changes. Only which Entry ID holds which lineup, and only among the
rows the untouched DraftKings template left blank. A row already filled in the
template (entered by hand) never moves and never changes, though its lineup
still counts in its contest's score. Every lineup in the input file is in the
output exactly once, so the portfolio, its exposures and its captain counts are
unchanged.

The score, per contest, over every pair of its lineups: shared people squared,
plus a penalty for the same Captain (Classic: the same QB), the same Classic
primary stack team and the same thesis, and a contest's score is its worst pair
plus its mean pair (`contest_assignment.py` states why). Theses come from an
optional JSON map of Entry ID to a label (the sleeve plan); without one that
term is zero. The penalty flags override the registered weights for an offline
experiment and the record says so.

What it checks before writing. The output differs from the template only in
the roster cells of rows the template left blank; the multiset of movable
lineups is unchanged; a line whose cells cannot be split on commas and joined
back to the same bytes (a quoted field) is refused, never guessed. It writes a
new path only. It does not validate lineups against DraftKings rules: run
`qa_showdown_portfolio.py` (or the Classic QA) on the output, as for any file.

It establishes nothing about EV, ownership or probability; the file stays
PRIOR_ONLY / DO_NOT_UPLOAD like its input.

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
import json
import sys
from pathlib import Path

import importlib.util  # noqa: E402


def _load_module():
    """`contest_assignment.py` is standard library only: load it by path, so this script
    still runs under any Python 3 without the project's virtual environment."""

    path = Path(__file__).resolve().parents[1] / "src" / "nfl_dfs" / "contest_assignment.py"
    spec = importlib.util.spec_from_file_location("nfl_dfs_contest_assignment", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ca = _load_module()

SHOWDOWN_ROSTER = slice(4, 10)
CLASSIC_ROSTER = slice(4, 13)


class DiversifyError(ValueError):
    """A named refusal; nothing is written."""


def _people_by_id(salaries: Path) -> dict[str, ca.Person]:
    with salaries.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows or not {"ID", "Name", "TeamAbbrev", "Roster Position"} <= set(rows[0]):
        raise DiversifyError(f"SALARY_SCHEMA_UNRECOGNIZED:{salaries}")
    position_column = "Position" if "Position" in rows[0] else "Roster Position"
    return {
        row["ID"].strip(): ca.Person(
            key=f"{row['TeamAbbrev'].strip()}|{row['Name'].strip()}",
            team=row["TeamAbbrev"].strip(),
            position=row[position_column].strip(),
        )
        for row in rows
    }


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


def _mode(template_lines: list[bytes]) -> tuple[str, slice]:
    header = [cell.strip() for cell in template_lines[0].decode("utf-8-sig").split(",")]
    if "CPT" in header:
        return ca.MODE_SHOWDOWN, SHOWDOWN_ROSTER
    if "QB" in header:
        return ca.MODE_CLASSIC, CLASSIC_ROSTER
    raise DiversifyError("TEMPLATE_MODE_UNRECOGNIZED")


def plan(template: Path, entries: Path, salaries: Path, theses: dict[str, str] | None):
    people = _people_by_id(salaries)
    t_lines, t_end = _lines(template)
    e_lines, e_end = _lines(entries)
    if len(t_lines) != len(e_lines) or t_end != e_end:
        raise DiversifyError("ENTRIES_GEOMETRY_DIFFERS_FROM_TEMPLATE")
    mode, roster_slice = _mode(t_lines)
    width = roster_slice.stop - roster_slice.start
    rows = []
    for index, (t_line, e_line) in enumerate(zip(t_lines, e_lines)):
        if t_line == e_line and not t_line:
            continue
        t_fields, e_fields = _fields(t_line), _fields(e_line)
        if not (len(t_fields) > roster_slice.stop and _entry_id(t_fields).isdigit()):
            if t_line != e_line:
                raise DiversifyError(f"NON_ENTRY_LINE_CHANGED:{index}")
            continue
        if (len(t_fields) != len(e_fields) or t_fields[:4] != e_fields[:4]
                or t_fields[roster_slice.stop:] != e_fields[roster_slice.stop:]):
            raise DiversifyError(f"NON_ROSTER_BYTES_CHANGED:{_entry_id(t_fields)}")
        blank = all(cell == b"" for cell in t_fields[roster_slice])
        if not blank and t_fields[roster_slice] != e_fields[roster_slice]:
            raise DiversifyError(f"PREFILLED_ROW_CHANGED:{_entry_id(t_fields)}")
        cells = e_fields[roster_slice]
        if not all(cells):
            raise DiversifyError(f"ROW_NOT_FILLED:{_entry_id(t_fields)}")
        ids = tuple(cell.decode("utf-8-sig").strip() for cell in cells)
        unknown = [dk_id for dk_id in ids if dk_id not in people]
        if unknown:
            raise DiversifyError(f"UNKNOWN_DK_ID:{_entry_id(t_fields)}:{unknown}")
        entry_id = _entry_id(t_fields)
        rows.append({
            "line": index, "entry_id": entry_id, "contest_id": e_fields[2].decode("utf-8-sig").strip(),
            "movable": blank, "cells": cells, "roster": ids, "thesis": (theses or {}).get(entry_id),
        })
    return rows, e_lines, e_end, mode, roster_slice, people


def _stat_row(mode: str, stats: dict[str, object]) -> dict[str, object]:
    """The record's per-contest reading, under the names the first record used."""

    row = {
        "entries": stats["entries"],
        "max_shared_people": stats["worst_pair_shared_people"],
        "mean_shared_people": stats["mean_shared_people"],
        "distinct_theses": stats["distinct_theses"],
        "in_every_lineup": stats["people_in_every_lineup"],
        "worst_pair_cost": stats["worst_pair_cost"],
        "score": stats["score"],
    }
    if mode == ca.MODE_SHOWDOWN:
        row["distinct_captains"] = stats["distinct_key_people"]
    else:
        row["distinct_qbs"] = stats["distinct_key_people"]
        row["distinct_stack_teams"] = stats["distinct_stack_teams"]
    return row


def diversify(rows, people, mode, *, weights: ca.Weights, restarts: int, seed: int, time_limit: float):
    thesis_by_roster = {row["roster"]: row["thesis"] for row in rows if row["thesis"] is not None}
    entry_rows = [
        ca.EntryRow(row["entry_id"], row["contest_id"], row["roster"], "template" if row["movable"] else None)
        for row in rows
    ]
    try:
        return ca.diversify(
            entry_rows, mode=mode, people=people, thesis_by_roster=thesis_by_roster,
            seed=seed, restarts=restarts, time_limit_seconds=time_limit, weights=weights)
    except ca.ContestAssignmentError as exc:
        raise DiversifyError(str(exc)) from exc


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--salaries", required=True, type=Path)
    parser.add_argument("--template", required=True, type=Path, help="the untouched DKEntries download")
    parser.add_argument("--entries", required=True, type=Path, help="the filled file to reassign")
    parser.add_argument("--out", required=True, type=Path, help="a new path; never an existing file")
    parser.add_argument("--theses", type=Path, help="JSON map of Entry ID to thesis label")
    parser.add_argument("--record", type=Path, help="write the mapping and both reports here (new path)")
    parser.add_argument("--captain-penalty", type=int, default=ca.KEY_PERSON_WEIGHT,
                        help="the same-Captain (Classic: same-QB) weight; the registered value is 12")
    parser.add_argument("--stack-penalty", type=int, default=ca.STACK_TEAM_WEIGHT,
                        help="the same Classic primary stack team weight; the registered value is 6")
    parser.add_argument("--thesis-penalty", type=int, default=ca.THESIS_WEIGHT,
                        help="the same-thesis weight; the registered value is 3")
    parser.add_argument("--restarts", type=int, default=ca.DEFAULT_RESTARTS)
    parser.add_argument("--seed", type=int, default=ca.DEFAULT_SEED)
    parser.add_argument("--time-limit-seconds", type=float, default=60.0)
    args = parser.parse_args(argv)
    try:
        for target in (args.out, args.record):
            if target is not None and target.exists():
                raise DiversifyError(f"OUTPUT_EXISTS:{target}")
        if args.out.resolve() in {args.template.resolve(), args.entries.resolve(), args.salaries.resolve()}:
            raise DiversifyError("OUTPUT_IS_AN_INPUT")
        theses = json.loads(args.theses.read_text(encoding="utf-8")) if args.theses else None
        rows, lines, ending, mode, roster_slice, people = plan(args.template, args.entries, args.salaries, theses)
        weights = ca.Weights(args.captain_penalty, args.stack_penalty, args.thesis_penalty)
        outcome = diversify(rows, people, mode, weights=weights, restarts=args.restarts, seed=args.seed,
                            time_limit=args.time_limit_seconds)
        by_entry = {row["entry_id"]: row for row in rows}
        placed = {entry_id: by_entry_cells(rows, roster) for entry_id, roster in outcome.assignments.items()}
        out_lines = list(lines)
        for row in rows:
            if row["movable"]:
                fields = lines[row["line"]].split(b",")
                fields[roster_slice] = placed[row["entry_id"]]
                out_lines[row["line"]] = b",".join(fields)
        moved = [row["cells"] for row in rows if row["movable"]]
        written = [placed[row["entry_id"]] for row in rows if row["movable"]]
        if sorted(map(tuple, moved)) != sorted(map(tuple, written)):
            raise DiversifyError("LINEUP_MULTISET_CHANGED")
        payload = ending.join(out_lines)
        _check_against_template(args.template, payload, ending, roster_slice)
        _audit_payload(payload, ending, roster_slice, rows, people, mode, theses, outcome)
        source_entry = {}
        for row in rows:
            if row["movable"]:
                source_entry[row["entry_id"]] = next(
                    other["entry_id"] for other in rows if other["movable"]
                    and other["roster"] == outcome.assignments[row["entry_id"]])
            else:
                source_entry[row["entry_id"]] = row["entry_id"]
        report = outcome.report
        record = {
            "schema_version": "nfl_contest_diversification_v2",
            "mode": mode,
            "does_not_establish": list(ca.DOES_NOT_ESTABLISH) + ["LINEUP_LEGALITY"],
            "contest_assignment": {k: v for k, v in report.items()
                                   if k not in ("contests_before", "contests_after")},
            "score": {"captain_penalty": weights.key_person, "stack_penalty": weights.stack_team,
                      "thesis_penalty": weights.thesis, "restarts": args.restarts, "seed": args.seed,
                      "before": float(report["total_score_before"]), "after": float(report["total_score_after"])},
            "mapping_entry_to_source_entry": source_entry,
            "contests_before": {c: _stat_row(mode, s) for c, s in report["contests_before"].items()},
            "contests_after": {c: _stat_row(mode, s) for c, s in report["contests_after"].items()},
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
    print(json.dumps({"status": "WRITTEN", "out": str(args.out), "score_before": record["score"]["before"],
                      "score_after": record["score"]["after"], "moved_rows": report["moved_rows"],
                      "timed_out": report["timed_out"], "contests_after": record["contests_after"]},
                     indent=1, sort_keys=True))
    return 0


def _audit_payload(payload, ending, roster_slice, rows, people, mode, theses, outcome) -> None:
    """The module's independent audit, run on the bytes about to be written."""

    final: dict[str, tuple[str, ...]] = {}
    for line in payload.split(ending):
        fields = _fields(line) if line else []
        if len(fields) > roster_slice.stop and _entry_id(fields).isdigit():
            final[_entry_id(fields)] = tuple(cell.decode("utf-8-sig").strip() for cell in fields[roster_slice])
    entry_rows = [
        ca.EntryRow(row["entry_id"], row["contest_id"], row["roster"], "template" if row["movable"] else None)
        for row in rows
    ]
    problems, _ = ca.audit_contest_assignment(
        final, rows=entry_rows, mode=mode, people=people,
        selected_by_pool={"template": [row["roster"] for row in rows if row["movable"]]},
        thesis_by_roster={row["roster"]: row["thesis"] for row in rows if row["thesis"] is not None},
        reported_after=outcome.report["contests_after"] if outcome.result.weights.registered else None)
    if problems:
        raise DiversifyError("AUDIT_FAILED:" + ",".join(problems))


def by_entry_cells(rows, roster):
    """The original cell bytes of the lineup whose roster this is."""

    for row in rows:
        if row["roster"] == roster:
            return row["cells"]
    raise DiversifyError("LINEUP_NOT_IN_INPUT")


def _check_against_template(template: Path, payload: bytes, ending: bytes, roster_slice: slice) -> None:
    t_lines = template.read_bytes().split(ending)
    o_lines = payload.split(ending)
    if len(t_lines) != len(o_lines):
        raise DiversifyError("OUTPUT_GEOMETRY_DIFFERS_FROM_TEMPLATE")
    for t_line, o_line in zip(t_lines, o_lines):
        if t_line == o_line:
            continue
        t_fields, o_fields = t_line.split(b","), o_line.split(b",")
        if (len(t_fields) != len(o_fields) or t_fields[:4] != o_fields[:4]
                or t_fields[roster_slice.stop:] != o_fields[roster_slice.stop:]
                or not all(cell == b"" for cell in t_fields[roster_slice])):
            raise DiversifyError(f"OUTPUT_CHANGES_MORE_THAN_BLANK_ROSTER_CELLS:{t_line[:40]!r}")


if __name__ == "__main__":
    sys.exit(main())
