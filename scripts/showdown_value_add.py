#!/usr/bin/env python3
"""Work one named person into rows of a filled Showdown review file by one swap each (Session 55).

The validated replacement for `data/inbox/slates/phi-chi-sd-2026-09-28/keenum_swap.py`, which can put a
person into a row that already holds him and exits 0 (2026-10-02 review, F-01). Construction only: no
projection is written. The person has no prior row, adds 0 prior points, and his evidence gate stays unmet,
so the file stays DO_NOT_UPLOAD and the report names that as a limitation.

The person is an exact current-slate DraftKings ID (his CPT or FLEX row; both resolve to him). Each swap
replaces one FLEX cell with his FLEX ID, or with `--captain` the Captain cell with his CPT ID. A row he
already holds, in either slot, is never edited. A swap is taken only if `validate_lineup` accepts the row
(six distinct people, cap, both teams) and its `roster_canonical_key` matches no other row of the file, so
a FLEX permutation is the same lineup (R29), and it does not create the same six people under another Captain
(a legal near-duplicate, which `keenum_swap.py` also refused). Only rows the `--template` left blank are editable; a row
DraftKings prefilled passes through untouched and still counts for distinctness.

Before anything is created, the output bytes are rebuilt, reparsed and audited: every line equals the
template except the swapped cells, every filled row is legal, every key is distinct. One bad row, even one
this tool never touched, refuses the whole publication. The output is created exclusively and last.

Order: rows by their lowest removable score, then Entry ID; within a row the lowest-scored cell first.
`--scores` (`by_dk_id`, the exact ID of the cell) is read only to order; an ID it lacks, or no file, scores 0 and
salary breaks the tie. Inputs are read once and their hashes reported.

Exit codes: 0 every requested row swapped; 3 file written with a shortfall; 2 refused, nothing written.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import math
import os
import re
import sys
from pathlib import Path

from nfl_dfs.byte_lines import csv_field_spans, split_byte_lines, split_line_ending
from nfl_dfs.contracts import UNAVAILABLE_DK_STATUSES, EngineMode
from nfl_dfs.dk import DraftKingsParseError, parse_entry_bytes, parse_salaries, reconcile_template
from nfl_dfs.lineups import roster_canonical_key, validate_lineup

EXIT_OK, EXIT_REFUSED, EXIT_PARTIAL = 0, 2, 3
WIDTH = 6
_TRAILING_ID = re.compile(r"\((\d+)\)\s*$")
LIMITATION = ("{name} adds 0 prior points by construction: no projection was written, and his evidence gate "
              "(official activity, current role) stays unmet. MODEL_STATUS=PRIOR_ONLY, RELEASE_DECISION=DO_NOT_UPLOAD.")


class Refused(Exception):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code, self.detail = code, detail


def cell_id(cell: str) -> str:
    """A roster cell's DraftKings ID, whether it holds `123` or `Name (123)`."""
    match = _TRAILING_ID.search(cell)
    return match.group(1) if match else cell.strip()


def fields(line: bytes) -> list[bytes]:
    body, _ = split_line_ending(line)
    return [body[start:end] for start, end in csv_field_spans(body)]


def changed_cells(a: bytes, b: bytes) -> set[int] | None:
    """Field indexes where two raw lines differ, or None when their ending or field count differs."""
    fa, fb = fields(a), fields(b)
    if split_line_ending(a)[1] != split_line_ending(b)[1] or len(fa) != len(fb):
        return None
    return {i for i, (x, y) in enumerate(zip(fa, fb)) if x != y}


def bytes_defects(template_raw: bytes, other_raw: bytes, lo: int, label: str) -> list[str]:
    """Lines that differ from the template anywhere but the roster cells of a row it left blank."""
    t_lines, o_lines = split_byte_lines(template_raw), split_byte_lines(other_raw)
    if len(t_lines) != len(o_lines):
        return [f"{label}: LINE_COUNT_CHANGED {len(t_lines)} -> {len(o_lines)}"]
    defects = []
    for n, (t, o) in enumerate(zip(t_lines, o_lines), start=1):
        if t == o:
            continue
        diff, tf = changed_cells(t, o), fields(t)
        blank = n > 1 and tf[0].strip().isdigit() and len(tf) >= lo + WIDTH and not any(
            f.strip() for f in tf[lo:lo + WIDTH])
        if diff is None or not diff <= (set(range(lo, lo + WIDTH)) if blank else set()):
            defects.append(f"{label}: LINE_{n}_CHANGED_OUTSIDE_A_BLANK_ROSTER")
    return defects


def file_defects(slate, rows: dict[str, list[str]]) -> list[str]:
    """Every row legal and every canonical key distinct across the whole file."""
    defects, seen = [], collections.defaultdict(list)
    for entry_id, ids in rows.items():
        result = validate_lineup(slate, ids)
        if result.valid:
            seen[result.lineup.canonical_key].append(entry_id)
        else:
            defects.append(f"entry {entry_id}: {'; '.join(result.errors)}")
    return defects + [f"DUPLICATE_LINEUP: entries {es} hold one roster" for es in seen.values() if len(es) > 1]


def finite(value) -> float:
    if isinstance(value, bool) or not math.isfinite(number := float(value)):
        raise ValueError(f"not a finite number: {value!r}")
    return number


def load_json_map(path: str | None, what: str, key: str | None = None, cast=str):
    """A `{string: value}` JSON file as read bytes and a map, or ({}, None) when no path was given."""
    if not path:
        return {}, None
    try:
        raw = Path(path).read_bytes()
        doc = json.loads(raw.decode("utf-8"))
        return {str(k): cast(v) for k, v in (doc[key] if key else doc).items()}, hashlib.sha256(raw).hexdigest()
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise Refused(f"{what}_UNREADABLE", f"{path}: {type(exc).__name__}: {exc}")


def run(a) -> dict:
    out = Path(a.out)
    if out.exists():
        raise Refused("OUTPUT_EXISTS", f"{out} already exists; an earlier file is never overwritten")
    if a.entry_id and (a.count is not None or a.thesis):
        raise Refused("ENTRY_ID_CONFLICT", "--entry-id names the rows; --count and --thesis choose them, so not together")
    if bool(a.thesis) != bool(a.theses):
        raise Refused("THESIS_FILTER_INCOMPLETE", "--thesis and --theses go together")
    limit_count = 3 if a.count is None else a.count
    if limit_count < 1:
        raise Refused("COUNT_INVALID", f"--count must be at least 1, got {limit_count}")
    scores, scores_sha = load_json_map(a.scores, "SCORES", "by_dk_id", finite)
    theses, theses_sha = load_json_map(a.theses, "THESES")
    try:  # each input is read once, so the bytes that are parsed are the bytes that are audited and hashed
        t_raw, r_raw = Path(a.template).read_bytes(), Path(a.review).read_bytes()
        slate = parse_salaries(a.salaries)
        template, review = parse_entry_bytes(t_raw, source_name=a.template), parse_entry_bytes(r_raw, source_name=a.review)
        for parsed in (template, review):
            reconcile_template(parsed, slate)
    except (DraftKingsParseError, OSError) as exc:
        raise Refused("INPUT_REFUSED", str(exc))
    if slate.mode is not EngineMode.SHOWDOWN:
        raise Refused("DK_MODE_NOT_SHOWDOWN", "this tool edits Showdown files only")
    lo = template.roster_start_index
    if template.header != review.header or [e.entry_id for e in template.authorizations] != [
            e.entry_id for e in review.authorizations]:
        raise Refused("REVIEW_NOT_DERIVED_FROM_TEMPLATE", "the header, Entry IDs or their order differ")
    try:
        problems = bytes_defects(t_raw, r_raw, lo, "review")
    except ValueError as exc:
        raise Refused("CSV_LINE_UNREADABLE", str(exc))
    if problems:
        raise Refused("REVIEW_NOT_DERIVED_FROM_TEMPLATE", "; ".join(problems[:5]))

    by_id = {p.dk_id: p for p in slate.players}
    person = by_id.get(str(a.dk_id).strip())
    if person is None:
        raise Refused("DK_ID_NOT_IN_POOL", f"{a.dk_id!r} is not a current-slate DraftKings ID")
    if (person.status_raw or "").strip().upper() in UNAVAILABLE_DK_STATUSES:
        raise Refused("PERSON_UNAVAILABLE_PER_DK_STATUS", f"{person.name} is {person.status_raw} on DraftKings")
    peers = collections.defaultdict(list)
    for p in slate.players:
        peers[p.underlying_id].append(p.dk_id)
    role_id = {by_id[i].role: i for i in peers[person.underlying_id]}
    new_id = role_id["CPT" if a.captain else "FLEX"]
    slots = (0,) if a.captain else range(1, WIDTH)

    kinds, rows = {}, {}
    for t, r in zip(template.authorizations, review.authorizations):
        if not any(r.existing_cells):
            kinds[r.entry_id] = "blank"
            continue
        if not all(r.existing_cells):
            raise Refused("PARTIAL_ROW", f"entry {r.entry_id} has {sum(map(bool, r.existing_cells))} of {WIDTH} cells")
        kinds[r.entry_id] = "prefilled" if any(t.existing_cells) else "filled"
        rows[r.entry_id] = [cell_id(c) for c in r.existing_cells]
    bad = file_defects(slate, rows)
    if bad:
        raise Refused("INPUT_FILE_NOT_VALID", "; ".join(bad[:5]) + " (nothing is swapped into a file that is not valid)")

    def holds(ids):
        return next((("CPT" if i == 0 else "FLEX") for i, c in enumerate(ids)
                     if by_id[c].underlying_id == person.underlying_id), None)

    def score(dk_id):
        return scores.get(dk_id, 0.0)  # the exact ID: a Captain row and a FLEX row are priced and scored apart

    cur = {e: list(v) for e, v in rows.items()}
    keys = {e: roster_canonical_key(slate, v) for e, v in cur.items()}
    people = {e: frozenset(by_id[c].underlying_id for c in v) for e, v in cur.items()}

    def options(entry_id):
        """Swaps legal on the file as it stands now, lowest removed score first."""
        taken = {k for e, k in keys.items() if e != entry_id}
        taken_people = {s for e, s in people.items() if e != entry_id}
        found = []
        for i in slots:
            trial = cur[entry_id][:i] + [new_id] + cur[entry_id][i + 1:]
            result = validate_lineup(slate, trial)
            # R29 allows the same six people under another Captain; like keenum_swap.py, this tool does not create one.
            if (result.valid and result.lineup.canonical_key not in taken
                    and frozenset(by_id[c].underlying_id for c in trial) not in taken_people):
                found.append((score(cur[entry_id][i]), by_id[cur[entry_id][i]].salary, i, trial,
                              result.lineup.canonical_key))
        return sorted(found, key=lambda o: o[:3])

    explicit = list(dict.fromkeys(a.entry_id))
    for e in explicit:
        if kinds.get(e) != "filled":
            raise Refused("ENTRY_NOT_SWAPPABLE", f"{e} is {kinds.get(e, 'not in the file')}; only a row the "
                          "template left blank and the review filled may change")
        if holds(cur[e]):
            raise Refused("PERSON_ALREADY_ROSTERED", f"entry {e} already holds {person.name} in {holds(cur[e])}")
    already = sorted(e for e, v in cur.items() if holds(v))
    pool = explicit or [e for e in cur if kinds[e] == "filled" and e not in already
                        and (not a.thesis or theses.get(e) in a.thesis)]
    first = {e: options(e) for e in pool}
    limit = len(explicit) or limit_count
    swaps, skipped = [], {}
    for e in sorted(pool, key=lambda e: (first[e][0][:2] if first[e] else (float("inf"), 0), int(e))):
        if len(swaps) >= limit:
            break
        found = options(e)
        if not found:
            skipped[e] = "NO_VALID_SWAP"
            continue
        loss, _, slot, trial, key = found[0]
        swaps.append({"entry_id": e, "slot": "CPT" if slot == 0 else f"FLEX {slot}", "slot_index": slot,
                      "removed_dk_id": cur[e][slot], "removed": by_id[cur[e][slot]].name, "removed_score": loss})
        cur[e], keys[e] = trial, key
        people[e] = frozenset(by_id[c].underlying_id for c in trial)
    if explicit and skipped:
        raise Refused("NO_VALID_SWAP", f"no legal, distinct swap for {sorted(skipped)}; nothing is written")
    if not swaps:
        raise Refused("NO_ROW_CHANGED", f"no row could take {person.name}: {len(already)} already hold him, "
                      f"{len(skipped)} have no legal distinct swap, {len(pool)} were eligible")

    lines = list(split_byte_lines(r_raw))
    by_entry = {s["entry_id"]: s for s in swaps}
    try:
        for n, line in enumerate(lines):
            body, ending = split_line_ending(line)
            spans = csv_field_spans(body)
            swap = by_entry.get(body[spans[0][0]:spans[0][1]].decode("ascii", "ignore").strip())
            if swap:
                start, end = spans[lo + swap["slot_index"]]
                lines[n] = body[:start] + new_id.encode("ascii") + body[end:] + ending
        out_raw = b"".join(lines)
        defects = bytes_defects(t_raw, out_raw, lo, "output")
        for n, (r, o) in enumerate(zip(split_byte_lines(r_raw), split_byte_lines(out_raw)), start=1):
            swap = by_entry.get(fields(r)[0].decode("ascii", "ignore").strip())
            if changed_cells(r, o) != ({lo + swap["slot_index"]} if swap else set()):
                defects.append(f"output: LINE_{n}_DIFFERS_FROM_THE_REVIEW_BEYOND_THE_SWAP")
        reparsed = parse_entry_bytes(out_raw, source_name=str(out))
    except (ValueError, IndexError, DraftKingsParseError) as exc:
        raise Refused("OUTPUT_FAILED_VALIDATION", f"{type(exc).__name__}: {exc}")
    out_rows = {e.entry_id: [cell_id(c) for c in e.existing_cells] for e in reparsed.authorizations
                if any(e.existing_cells)}
    defects += file_defects(slate, out_rows)
    defects += [f"entry {e}: row changed outside the swap" for e in out_rows if (out_rows[e] != rows.get(e)) != (e in by_entry)]
    defects += [f"entry {e}: {person.name} is not in the swapped cell" for e, s in by_entry.items()
                if out_rows.get(e, [""] * WIDTH)[s["slot_index"]] != new_id]
    if set(out_rows) != set(rows):
        defects.append("output: the set of filled rows changed")
    if defects:
        raise Refused("OUTPUT_FAILED_VALIDATION", "; ".join(defects[:10]))

    try:
        handle = open(out, "xb")
    except FileExistsError:
        raise Refused("OUTPUT_EXISTS", f"{out} appeared while writing; it was not touched")
    except OSError as exc:
        raise Refused("OUTPUT_UNWRITABLE", str(exc))
    try:
        with handle:
            handle.write(out_raw)
            handle.flush()
            os.fsync(handle.fileno())
        if out.read_bytes() != out_raw:
            raise Refused("OUTPUT_READBACK_MISMATCH", f"{out} does not hold the bytes that were validated")
    except BaseException as exc:  # only this call created `out`, so only this call removes it
        try:
            out.unlink(missing_ok=True)
        except OSError as unlink_exc:
            raise Refused("OUTPUT_LEFT_BEHIND", f"{out} could not be removed ({unlink_exc}) after {exc!r}; "
                          "its bytes are unconfirmed: delete it and do not use it")
        if isinstance(exc, OSError):
            raise Refused("OUTPUT_UNWRITABLE", f"{out}: {exc}")
        raise

    name_of = {p.underlying_id: p.name for p in slate.players}
    people = collections.Counter(by_id[c].underlying_id for ids in out_rows.values() for c in ids)
    captains = collections.Counter(by_id[ids[0]].underlying_id for ids in out_rows.values())
    top, cap = people.most_common(1)[0], captains.most_common(1)[0]
    return {
        "tool": "showdown_value_add_v1",
        "person": {"dk_id": person.dk_id, "name": person.name, "team": person.team, "position": person.position,
                   "slot_rows_used": "CPT" if a.captain else "FLEX"},
        "requested": limit, "swapped": len(swaps), "shortfall": limit - len(swaps),
        "swaps": [{k: v for k, v in s.items() if k != "slot_index"} for s in sorted(swaps, key=lambda s: int(s["entry_id"]))],
        "already_holds": already, "skipped": skipped,
        "order": "scores" if scores else "UNSCORED_BY_SALARY_THEN_DK_ID",
        "after": {"filled_rows": len(out_rows), "rows_holding_person": sum(1 for v in out_rows.values() if holds(v)),
                  "most_shared_person": [name_of[top[0]], top[1]], "most_frequent_captain": [name_of[cap[0]], cap[1]]},
        "salary_sha256": slate.salary_hash, "template_sha256": hashlib.sha256(t_raw).hexdigest(),
        "review_sha256": hashlib.sha256(r_raw).hexdigest(), "scores_sha256": scores_sha, "theses_sha256": theses_sha,
        "out": str(out), "out_sha256": hashlib.sha256(out_raw).hexdigest(),
        "LIMITATION": LIMITATION.format(name=person.name),
        "MODEL_STATUS": "PRIOR_ONLY", "RELEASE_DECISION": "DO_NOT_UPLOAD",
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--salaries", required=True, help="the slate's DKSalaries.csv")
    ap.add_argument("--template", required=True, help="the original DKEntries download the review was filled from")
    ap.add_argument("--review", required=True, help="the filled Showdown review file to edit; never overwritten")
    ap.add_argument("--out", required=True, help="a new path, created exclusively")
    ap.add_argument("--dk-id", required=True, help="the person's exact DraftKings ID, CPT or FLEX row")
    ap.add_argument("--count", type=int, default=None, help="up to N rows (default 3); not with --entry-id")
    ap.add_argument("--entry-id", action="append", default=[], help="swap exactly this row; any refusal refuses the run")
    ap.add_argument("--captain", action="store_true", help="replace the Captain, not a FLEX (default FLEX only)")
    ap.add_argument("--scores", help="JSON with by_dk_id; read only to order the swaps")
    ap.add_argument("--theses", help="JSON {entry_id: thesis}; with --thesis restricts automatic selection")
    ap.add_argument("--thesis", action="append", default=[], help="an allowed thesis label; repeatable")
    try:
        report = run(ap.parse_args(argv))
    except Refused as exc:
        print(f"REFUSED {exc.code}: {exc.detail}\nnothing was written", file=sys.stderr)
        return EXIT_REFUSED
    print(json.dumps(report, indent=2))
    return EXIT_PARTIAL if report["shortfall"] else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
