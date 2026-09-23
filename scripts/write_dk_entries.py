#!/usr/bin/env python3
"""Fill the blank roster cells of a DraftKings Classic DKEntries file, and verify.

Provenance: promoted from the 2026-09-13 session scratchpad. It is the writer at
the end of the Classic fallback path (`docs/RUNBOOK.md`, "The Classic fallback
path"): it takes the portfolio's `assignments_by_entry_id`, the operator's
untouched DKEntries download and the salary file, and writes a new file that
differs from the download only inside the nine roster cells of the rows it
filled.

## 2026-09-23 (Session 02): what changed and why

The 2026-09-22 audit (issue #40, D6) found that this script could exit 0 while
reserved rows went out blank. It silently skipped an assignment whose Entry ID
the template does not hold, never said which rows it left empty, checked a
roster only with `assert`, rewrote every line through `csv.writer` as CRLF, and
opened the output with `"w"`, so an earlier file at that path was destroyed.
Now:

* Every refusal is named (`REFUSED <CODE>: ...` on stderr) and nothing is written.
* Every blank authorized row is filled, or the file is written with those rows
  left blank and the script exits 3 naming each unfilled Entry ID. R29: never
  repeat a lineup to fill a row.
* Each roster is validated against the salary file: nine DraftKings IDs in the
  pool, nine different people, slot and FLEX eligibility, the 50,000 cap, and
  players from at least two games.
* Untouched lines keep their raw bytes, line endings included; a filled line
  changes only inside its nine roster cells (`nfl_dfs.byte_lines`, the helpers
  `lineups.write_upload_bytes` uses).
* The output must be a new path that is none of the inputs. The bytes go to a
  temporary file beside it, are re-read and verified, then `os.replace`d.

Exit codes: 0 every blank authorized row filled and verified; 2 refused, nothing
written; 3 written with unfilled authorized rows, each named. Exit 0 means the
file is structurally what the assignment asked for. It does not clear an upload:
the portfolio is still `PRIOR_ONLY / DO_NOT_UPLOAD`, and
`scripts/qa_classic_portfolio.py --template --export` runs on the result.

Usage:
    python scripts/write_dk_entries.py <portfolio.json> <DKEntries.csv> <DKSalaries.csv> <new-output.csv>
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path

from nfl_dfs.byte_lines import csv_field_spans, split_byte_lines, split_line_ending

SLOTS = ("QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX", "DST")
NEED = {"QB": 1, "RB": 2, "WR": 3, "TE": 1, "DST": 1}
FLEX_POSITIONS = frozenset({"RB", "WR", "TE"})
SALARY_CAP = 50000
# Only these salary columns are ever read; nothing else in the file is parsed.
SALARY_COLUMNS = ("ID", "Name", "Position", "Roster Position", "Salary", "Game Info", "TeamAbbrev")

EXIT_FILLED, EXIT_REFUSED, EXIT_PARTIAL = 0, 2, 3


class Refused(Exception):
    """One or more named refusals; nothing is written."""

    def __init__(self, problems: list[tuple[str, str]]):
        super().__init__("; ".join(f"{code}: {detail}" for code, detail in problems))
        self.problems = problems


def load_assignments(path: Path) -> dict[str, list[str]]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    by_entry = doc.get("assignments_by_entry_id") if isinstance(doc, dict) else None
    if not by_entry:
        raise Refused([("NO_ASSIGNMENTS", f"{path} has no populated assignments_by_entry_id")])
    out = {}
    for eid, value in by_entry.items():
        roster = value["roster"] if isinstance(value, dict) else value
        out[str(eid).strip()] = [str(x).strip() for x in roster]
    return out


def load_salaries(path: Path) -> dict[str, dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader, [])
        missing = [c for c in SALARY_COLUMNS if c not in header]
        if missing:
            raise Refused([("SALARY_COLUMNS_MISSING", f"{path} lacks {missing}")])
        index = {c: header.index(c) for c in SALARY_COLUMNS}
        pool: dict[str, dict] = {}
        for row in reader:
            if not row or not any(cell.strip() for cell in row):
                continue
            rec = {c: (row[i].strip() if i < len(row) else "") for c, i in index.items()}
            if rec["ID"] in pool:
                raise Refused([("SALARY_DUPLICATE_ID", rec["ID"])])
            try:
                rec["Salary"] = int(rec["Salary"])
            except ValueError:
                raise Refused([("SALARY_UNREADABLE", f"ID {rec['ID']} salary {rec['Salary']!r}")])
            pool[rec["ID"]] = rec
    return pool


def decode(line: bytes) -> list[str]:
    body, _ending = split_line_ending(line)
    try:
        text = body.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise Refused([("TEMPLATE_NOT_UTF8", str(exc))])
    return next(csv.reader([text]), [])


def parse_template(lines: tuple[bytes, ...]):
    """Return (fee index, entry rows in template order).

    An entry row is any line whose first cell is a numeric Entry ID. It is blank,
    and so authorized for filling, when every roster cell it has is empty.
    """

    if not lines:
        raise Refused([("TEMPLATE_EMPTY", "no header line")])
    header = decode(lines[0])
    if "Entry Fee" not in header:
        raise Refused([("NOT_A_CLASSIC_TEMPLATE", "header has no Entry Fee column")])
    fee = header.index("Entry Fee")
    roster = tuple(header[fee + 1:fee + 1 + len(SLOTS)])
    after = header[fee + 1 + len(SLOTS)] if len(header) > fee + 1 + len(SLOTS) else ""
    if roster != SLOTS or after not in ("", "Instructions"):
        raise Refused([("NOT_A_CLASSIC_TEMPLATE",
                        f"roster header is {list(header[fee + 1:fee + 2 + len(SLOTS)])}, "
                        f"expected {list(SLOTS)}")])
    rows, seen = [], set()
    for number, line in enumerate(lines[1:], start=1):
        cells = decode(line)
        eid = cells[0].strip() if cells else ""
        if not eid.isdigit():
            continue
        if eid in seen:
            raise Refused([("DUPLICATE_TEMPLATE_ENTRY_ID", eid)])
        seen.add(eid)
        present = cells[fee + 1:fee + 1 + len(SLOTS)]
        rows.append({
            "line": number,
            "entry_id": eid,
            "blank": not any(c.strip() for c in present),
            "narrow": len(cells) < fee + 1 + len(SLOTS),
        })
    return fee, rows


def validate_roster(eid: str, ids: list[str], pool: dict[str, dict]) -> tuple[list[str], list[tuple[str, str]]]:
    """Place nine DraftKings IDs into DK slot order, or say why they cannot go."""

    problems: list[tuple[str, str]] = []
    if len(ids) != len(SLOTS):
        return [], [("ROSTER_SIZE", f"entry {eid}: {len(ids)} players, need {len(SLOTS)}")]
    unknown = [i for i in ids if i not in pool]
    if unknown:
        return [], [("DK_ID_NOT_IN_POOL", f"entry {eid}: {unknown} not in the salary file")]
    repeated = sorted({i for i in ids if ids.count(i) > 1})
    if repeated:
        return [], [("DUPLICATE_PLAYER", f"entry {eid}: {repeated} rostered more than once")]

    fixed = {pos: [] for pos in NEED}
    flex = []
    for i in ids:
        pos = pool[i]["Position"]
        if pos in fixed and len(fixed[pos]) < NEED[pos]:
            fixed[pos].append(i)
        else:
            flex.append(i)
    short = {pos: NEED[pos] - len(got) for pos, got in fixed.items() if len(got) < NEED[pos]}
    if short or len(flex) != 1 or pool[flex[0]]["Position"] not in FLEX_POSITIONS:
        spare = [f"{pool[i]['Position']} {pool[i]['Name']}" for i in flex]
        return [], [("ROSTER_SHAPE",
                     f"entry {eid}: short {short or 'nothing'}; left for FLEX {spare}; "
                     f"FLEX takes exactly one of {sorted(FLEX_POSITIONS)}, so a QB or DST cannot fill it")]
    cells = [fixed["QB"][0], *fixed["RB"], *fixed["WR"], fixed["TE"][0], flex[0], fixed["DST"][0]]

    for slot, i in zip(SLOTS, cells):
        eligible = {t.strip() for t in pool[i]["Roster Position"].split("/")}
        if slot not in eligible:
            problems.append(("SLOT_INELIGIBLE",
                             f"entry {eid}: {pool[i]['Name']} ({i}) is {pool[i]['Roster Position']}, not {slot}"))
    total = sum(pool[i]["Salary"] for i in cells)
    if total > SALARY_CAP:
        problems.append(("OVER_SALARY_CAP", f"entry {eid}: salary {total} over {SALARY_CAP}"))
    games = {pool[i]["Game Info"].split()[0] if pool[i]["Game Info"] else "" for i in cells}
    if len(games) < 2:
        problems.append(("TWO_GAME_RULE", f"entry {eid}: every player is from {sorted(games)}"))
    return cells, problems


def roster_bytes(value: str) -> bytes:
    buffer = io.StringIO(newline="")
    csv.writer(buffer, lineterminator="").writerow([value])
    return buffer.getvalue().encode("utf-8")


def splice(line: bytes, start: int, cells: list[str], eid: str) -> bytes:
    body, ending = split_line_ending(line)
    try:
        spans = csv_field_spans(body)
    except ValueError as exc:
        raise Refused([("UNREADABLE_TEMPLATE_ROW", f"entry {eid}: {exc}")])
    if len(spans) < start + len(SLOTS):
        raise Refused([("ROW_NARROWER_THAN_ROSTER", f"entry {eid}: {len(spans)} fields")])
    replacements = {start + k: roster_bytes(v) for k, v in enumerate(cells)}
    out, cursor = [], 0
    for index, (lo, hi) in enumerate(spans):
        out.append(body[cursor:lo])
        out.append(replacements.get(index, body[lo:hi]))
        cursor = hi
    out.append(body[cursor:])
    out.append(ending)
    return b"".join(out)


def outside_roster_changed(before: bytes, after: bytes, start: int) -> bool:
    """True when anything but the nine roster cells differs between two lines."""

    (b_body, b_end), (a_body, a_end) = split_line_ending(before), split_line_ending(after)
    b_spans, a_spans = csv_field_spans(b_body), csv_field_spans(a_body)
    if b_end != a_end or len(b_spans) != len(a_spans):
        return True
    lo, hi = start, start + len(SLOTS) - 1
    return (b_body[:b_spans[lo][0]] != a_body[:a_spans[lo][0]]
            or b_body[b_spans[hi][1]:] != a_body[a_spans[hi][1]:])


def check_output_path(out: Path, template: Path, others: list[Path]) -> list[tuple[str, str]]:
    def same(a: Path, b: Path) -> bool:
        if a.resolve() == b.resolve():
            return True
        try:
            return a.exists() and b.exists() and os.path.samefile(a, b)
        except OSError:
            return False

    if same(out, template):
        return [("OUTPUT_IS_TEMPLATE", f"{out} is the DKEntries download; write a new file")]
    if any(same(out, p) for p in others):
        return [("OUTPUT_IS_AN_INPUT", f"{out} is one of the inputs")]
    if out.exists():
        return [("OUTPUT_EXISTS", f"{out} already exists; an earlier output is never overwritten")]
    if not out.parent.is_dir():
        return [("OUTPUT_DIRECTORY_MISSING", str(out.parent))]
    return []


def write_new(out: Path, data: bytes) -> None:
    fd, tmp = tempfile.mkstemp(dir=out.parent, prefix=f".{out.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        if Path(tmp).read_bytes() != data:
            raise Refused([("VERIFICATION_FAILED", "temporary file does not hold the verified bytes")])
        if out.exists():
            raise Refused([("OUTPUT_EXISTS", f"{out} appeared while writing")])
        os.replace(tmp, out)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def fill(sel: Path, tpl: Path, sal: Path, out: Path):
    problems = check_output_path(out, tpl, [sel, sal])
    if problems:
        raise Refused(problems)
    assignments = load_assignments(sel)
    pool = load_salaries(sal)
    raw = tpl.read_bytes()
    lines = split_byte_lines(raw)
    fee, rows = parse_template(lines)
    start = fee + 1
    by_id = {r["entry_id"]: r for r in rows}

    unknown = sorted(set(assignments) - set(by_id))
    if unknown:
        problems.append(("UNKNOWN_ENTRY_ID",
                         f"{len(unknown)} assignment Entry IDs are not in {tpl.name}: {unknown}"))
    for eid in assignments:
        row = by_id.get(eid)
        if row and not row["blank"]:
            problems.append(("PREFILLED_ROW_ASSIGNED",
                             f"entry {eid}: a roster cell was not blank; filled cells are never replaced"))
        elif row and row["narrow"]:
            problems.append(("ROW_NARROWER_THAN_ROSTER", f"entry {eid} has no nine roster cells to fill"))

    slotted: dict[str, list[str]] = {}
    for eid, ids in assignments.items():
        cells, found = validate_roster(eid, ids, pool)
        problems.extend(found)
        if cells and not found:
            slotted[eid] = cells
    seen: dict[frozenset, str] = {}
    for eid, cells in slotted.items():
        key = frozenset(cells)
        if key in seen:
            problems.append(("DUPLICATE_LINEUP",
                             f"entries {seen[key]} and {eid} carry the same roster; R29 keeps every lineup distinct"))
        seen.setdefault(key, eid)
    if problems:
        raise Refused(problems)

    fill_at = {by_id[eid]["line"]: (eid, cells) for eid, cells in slotted.items()}
    written = []
    for n, line in enumerate(lines):
        if n in fill_at:
            eid, cells = fill_at[n]
            line = splice(line, start, cells, eid)
        written.append(line)
    data = b"".join(written)

    # Independent re-read of the bytes about to be promoted.
    again = split_byte_lines(data)
    moved = []
    if len(again) != len(lines):
        moved.append(f"line count {len(lines)} -> {len(again)}")
    for n, (before, after) in enumerate(zip(lines, again)):
        if n not in fill_at:
            if before != after:
                moved.append(f"line {n + 1} changed")
            continue
        eid, cells = fill_at[n]
        if outside_roster_changed(before, after, start):
            moved.append(f"line {n + 1} (entry {eid}) changed outside its roster cells")
        if [c.strip() for c in decode(after)[start:start + len(SLOTS)]] != cells:
            moved.append(f"line {n + 1} (entry {eid}) does not reparse to its assignment")
    if moved:
        raise Refused([("VERIFICATION_FAILED", "; ".join(moved[:5]))])

    write_new(out, data)
    unfilled = [r["entry_id"] for r in rows if r["blank"] and r["entry_id"] not in assignments]
    prefilled = sum(1 for r in rows if not r["blank"])
    return {"filled": len(fill_at), "prefilled": prefilled, "unfilled": unfilled,
            "moved": len(moved), "sha256": hashlib.sha256(out.read_bytes()).hexdigest()}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("portfolio", type=Path, help="json with assignments_by_entry_id")
    ap.add_argument("template", type=Path, help="the untouched DKEntries download")
    ap.add_argument("salaries", type=Path, help="the DKSalaries file for the same slate")
    ap.add_argument("output", type=Path, help="a new path; never an existing file or an input")
    a = ap.parse_args(argv)
    try:
        report = fill(a.portfolio, a.template, a.salaries, a.output)
    except Refused as exc:
        for code, detail in exc.problems:
            print(f"REFUSED {code}: {detail}", file=sys.stderr)
        print("nothing was written", file=sys.stderr)
        return EXIT_REFUSED

    print(f"entries filled: {report['filled']}")
    print(f"prefilled rows preserved: {report['prefilled']}")
    print(f"unfilled authorized Entry IDs: {len(report['unfilled'])} {report['unfilled']}")
    print(f"bytes changed outside the nine roster cells: {report['moved']}")
    print(f"sha256: {report['sha256']}")
    print(f"wrote: {a.output}")
    if report["unfilled"]:
        print(f"UNFILLED_AUTHORIZED_ROWS: {len(report['unfilled'])} blank authorized rows have no "
              f"assignment and were left blank: {report['unfilled']}. Name them in the handoff; "
              "never repeat a lineup to fill them (R29).", file=sys.stderr)
        return EXIT_PARTIAL
    return EXIT_FILLED


if __name__ == "__main__":
    sys.exit(main())
