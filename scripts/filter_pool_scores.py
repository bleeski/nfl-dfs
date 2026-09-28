#!/usr/bin/env python3
"""Remove a run's own role-gated exclusions from an `NFL_DFS_DUMP_SCORES` dump.

`selection.write_pool_scores` writes the whole scored pool, including people
the run's own gates already excluded from selection: their score stays as
scored (a material-role-change exclusion is scored fully on purpose, per the
ruling in `prior_score.py`), which is correct for the engine's own report but
wrong for `scripts/build_classic_portfolio.py`, whose pool filter keeps anyone
scored above zero. On the 2026-09-27 Week 3 slate, 65 role-gated people were
still scored above zero in the dump this way, and had to be removed by hand
against the run's own selection report before the fallback build.

Since 2026-09-27 `write_pool_scores` also names its own exclusion set directly
(`excluded_dk_ids`, the same set `select_prior_lineups` passes to its own
objective). When the dump already carries that field, this script uses it, and
it is authoritative: it covers every exclusion reason (kicker zero-share,
official status, offensive role and material role change, and a portfolio
policy's own zero caps), not only the offensive-role gate. Pass `--report`
alongside it purely as an integrity cross-check against the report's own
`excluded_rows`.

For an older dump with no `excluded_dk_ids` field, `--report` is required and
this falls back to the 2026-09-27 method: read
`offensive_roles.excluded_by_finding` (every reason, which since R28 already
includes material-role-change people under
`OFFENSIVE_UNRESOLVED_MATERIAL_ROLE_CHANGE`) plus, defensively,
`material_role_change_exclusions`' own embedded person ids, map each excluded
person to a dk_id through `--salaries`, and refuse unless the removed person
count equals the report's `excluded_rows`. That equality only holds when the
run has no *other* kind of exclusion (kicker, official status, a portfolio
policy): this script refuses rather than guess when it does not hold, because
removing an incomplete or overlapping set is worse than refusing outright.

`--report` accepts a raw selection report, a `selection_report.json`, or a full
`cowork_run.json`; it is found at whichever nesting holds an `offensive_roles`
key (an unwrapped report, `<file>.selection`, or
`<file>.prior_review_reports.selection.selection`).

Exit codes: 0 written, 2 refused by name (nothing written).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import tempfile
from pathlib import Path

from nfl_dfs.selection import POOL_SCORES_SCHEMA

EXIT_OK, EXIT_REFUSED = 0, 2
MATERIAL_ROLE_CHANGE_CODE = re.compile(r"OFFENSIVE_UNRESOLVED_MATERIAL_ROLE_CHANGE:([^:]+):")


class Refused(Exception):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def load_scores(path: str) -> dict:
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    if doc.get("schema_version") != POOL_SCORES_SCHEMA:
        raise Refused(
            "SCORES_SCHEMA_MISMATCH",
            f"{path} is not a {POOL_SCORES_SCHEMA} document (schema_version="
            f"{doc.get('schema_version')!r})",
        )
    if "by_dk_id" not in doc:
        raise Refused("SCORES_MISSING_BY_DK_ID", f"{path} has no by_dk_id")
    return doc


def load_person_to_dk_ids(path: str) -> dict[str, list[str]]:
    """`{team}|{position}|{name}` -> every dk_id on that salary row.

    The same underlying-id formula `dk.py` uses, so a person here always
    matches the run's own report, never a fuzzy or normalized identity.
    """

    with open(path, encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    by_person: dict[str, list[str]] = {}
    for row in rows:
        team = (row.get("TeamAbbrev") or "").strip()
        position = (row.get("Position") or "").strip()
        name = (row.get("Name") or "").strip()
        dk_id = (row.get("ID") or "").strip()
        if not (team and position and name and dk_id):
            continue
        by_person.setdefault(f"{team}|{position}|{name}", []).append(dk_id)
    if not by_person:
        raise Refused("SALARIES_EMPTY", f"{path} has no readable rows")
    return by_person


def find_selection_report(doc: dict) -> dict:
    """Walk down to the dict carrying `offensive_roles` directly.

    Handles an unwrapped selection report, a `selection_report.json`
    (`.selection`), and a full `cowork_run.json`
    (`.prior_review_reports.selection.selection`), without caring which one
    was actually passed.
    """

    current = doc
    for _ in range(6):
        if isinstance(current, dict) and "offensive_roles" in current:
            return current
        if not isinstance(current, dict):
            break
        if "selection" in current:
            current = current["selection"]
        elif "prior_review_reports" in current:
            current = current["prior_review_reports"]
        else:
            break
    raise Refused(
        "REPORT_SHAPE_UNRECOGNIZED",
        "no offensive_roles report found; expected an unwrapped selection "
        "report, selection_report.json, or cowork_run.json",
    )


def excluded_persons(report: dict) -> set[str]:
    offense = report.get("offensive_roles") or {}
    people: set[str] = set()
    for members in (offense.get("excluded_by_finding") or {}).values():
        people.update(str(member) for member in members or ())
    for code in offense.get("material_role_change_exclusions") or ():
        match = MATERIAL_ROLE_CHANGE_CODE.match(str(code))
        if match:
            people.add(match.group(1))
    return people


def write_new(out: Path, data: bytes) -> None:
    fd, tmp = tempfile.mkstemp(dir=out.parent, prefix=f".{out.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if Path(tmp).read_bytes() != data:
            raise Refused("VERIFICATION_FAILED", "temporary file does not hold the filtered scores")
        if out.exists():
            raise Refused("OUTPUT_EXISTS", f"{out} appeared while writing")
        os.replace(tmp, out)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def filter_scores(a) -> dict:
    out = Path(a.out)
    if out.exists():
        raise Refused("OUTPUT_EXISTS", f"{a.out} already exists; an earlier filtered dump is never overwritten")

    scores = load_scores(a.scores)
    person_to_dk_ids = load_person_to_dk_ids(a.salaries)
    dk_id_to_person = {dk_id: person for person, ids in person_to_dk_ids.items() for dk_id in ids}

    report = None
    if a.report:
        report = find_selection_report(json.loads(Path(a.report).read_text(encoding="utf-8")))

    dump_excluded = scores.get("excluded_dk_ids")
    if dump_excluded:
        excluded_ids = {str(dk_id) for dk_id in dump_excluded}
        source = "the dump's own excluded_dk_ids"
        if report is not None:
            declared = report.get("excluded_rows")
            if declared is not None and declared != len(excluded_ids):
                raise Refused(
                    "EXCLUDED_COUNT_MISMATCH",
                    f"dump names {len(excluded_ids)} excluded_dk_ids; {a.report}'s excluded_rows is {declared}",
                )
    else:
        if report is None:
            raise Refused(
                "REPORT_REQUIRED",
                f"{a.scores} has no excluded_dk_ids field (a dump from before the 2026-09-27 engine "
                "fix); pass --report",
            )
        people = excluded_persons(report)
        excluded_ids = set()
        unresolved = []
        for person in sorted(people):
            ids = person_to_dk_ids.get(person)
            if not ids:
                unresolved.append(person)
                continue
            excluded_ids.update(ids)
        if unresolved:
            raise Refused(
                "PERSON_NOT_IN_SALARIES",
                f"{len(unresolved)} excluded person(s) not on {a.salaries}: {unresolved}",
            )
        declared = report.get("excluded_rows")
        if declared is None:
            raise Refused("EXCLUDED_ROWS_MISSING", f"{a.report} has no excluded_rows to check against")
        if len(people) != declared:
            raise Refused(
                "EXCLUDED_COUNT_MISMATCH",
                f"{len(people)} people named across offensive_roles.excluded_by_finding and "
                f"material_role_change_exclusions; {a.report}'s excluded_rows is {declared}. Refusing "
                "rather than removing an incomplete or overlapping set -- this run may also carry "
                "kicker, official-status or portfolio-policy exclusions this fallback does not derive; "
                "a dump already carrying excluded_dk_ids does not have this gap.",
            )
        source = f"{a.report}: offensive_roles.excluded_by_finding + material_role_change_exclusions"

    removed_persons = sorted({dk_id_to_person[i] for i in excluded_ids if i in dk_id_to_person})
    doc = dict(scores)
    doc["by_dk_id"] = {k: v for k, v in scores["by_dk_id"].items() if k not in excluded_ids}
    doc["by_person"] = {
        k: v for k, v in (scores.get("by_person") or {}).items() if k not in removed_persons
    }
    doc["filter_report"] = {
        "source": source,
        "input_scores": str(a.scores),
        "removed_dk_ids": sorted(set(scores["by_dk_id"]) & excluded_ids),
        "removed_persons": removed_persons,
        "kept_rows": len(doc["by_dk_id"]),
    }
    data = json.dumps(doc, indent=2).encode("utf-8")
    write_new(out, data)
    return doc["filter_report"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--scores", required=True, help="NFL_DFS_DUMP_SCORES json to filter")
    ap.add_argument("--salaries", required=True, help="DKSalaries.csv, to map an excluded person to a dk_id")
    ap.add_argument(
        "--report",
        help="a selection report, selection_report.json, or cowork_run.json naming the exclusions; "
        "required unless --scores already carries excluded_dk_ids",
    )
    ap.add_argument("--out", required=True, help="filtered scores json to write; a new path, never an input")
    a = ap.parse_args(argv)
    try:
        report = filter_scores(a)
    except Refused as exc:
        print(f"REFUSED {exc.code}: {exc.detail}", file=sys.stderr)
        print("nothing was written", file=sys.stderr)
        return EXIT_REFUSED
    print(f"source: {report['source']}")
    print(f"removed {len(report['removed_dk_ids'])} dk_id(s) ({len(report['removed_persons'])} person(s))")
    print(f"kept: {report['kept_rows']} rows")
    print(f"wrote: {a.out}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
