#!/usr/bin/env python3
"""Construction-only edits to an already-built Classic portfolio. NOT the
evidence layer: every mode reads the engine's own gated scores and the
current DraftKings salary file, and never invents an observation.

Provenance: promoted from `scripts/staging/slate_2026_09_27/swap_inactives.py`,
a session scratchpad that swapped newly inactive players and worked named
value adds into the Week 3 Classic portfolio by hand. This generalizes it to
four modes and gives every mode the same legality, caps and uniqueness the
portfolio was built under (see `scripts/build_classic_portfolio.py`, which
this deliberately mirrors: the same slot counts, DST/QB anti-correlation, and
bring-back definition, so a lineup this script writes never fails
`scripts/qa_classic_portfolio.py` Tier 1 for a reason this script could have
caught).

Modes (`--mode`):
  inactive    replace a newly OUT/IR/D player. Tries a same-slot single swap
              first (any legal, cap-fitting, exposure/overlap-respecting
              replacement, ranked by score); when none exists (the position
              broke: e.g. no legal single RB/WR/TE swap fits every FLEX
              constraint) falls back to a two-player swap, trading the
              absent player plus one non-core flex-eligible teammate for a
              better-scoring pair.
  value-add   work a named, currently-scored player into up to
              `--target-count` lineups, each time replacing the weakest
              non-core same-position-group player he beats.
  redeploy    one salary-driven upgrade per changed lineup (from
              `--changed-entry-id`, or the prior mode's own
              `construction.changed_entry_ids`): spend unspent cap room on
              the single best-scoring legal non-core replacement, never
              touching the QB stack or the bring-back.
  late-swap   the `inactive` replacement, restricted to cells whose game has
              not locked as of `--now` (from each player's own `Game Info`).
              A locked cell is never touched, whichever player is in it.

"Core" (never touched by value-add or redeploy, so the stack and bring-back
this portfolio was built for survive every edit): the QB, his own-team
WR/TE stackmates, and any opponent skill player supplying the bring-back.

Exit codes: 0 every named absent player (or, in `value-add`/`redeploy`, every
change asked for) was applied; 3 written with a shortfall, each one named on
stderr; 2 refused by name, nothing written.
"""

from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

SALARY_COLUMNS = ("ID", "Name", "Position", "Roster Position", "Salary", "Game Info",
                  "TeamAbbrev", "Status")
UNAVAILABLE_STATUSES = {"O", "OUT", "IR", "D"}
FLEX_POSITIONS = ("RB", "WR", "TE")
EXIT_OK, EXIT_REFUSED, EXIT_PARTIAL = 0, 2, 3
EASTERN = ZoneInfo("America/New_York")


class Refused(Exception):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code, self.detail = code, detail


# --------------------------------------------------------------------------- #
# Loaders, matching build_classic_portfolio.py's own vocabulary and columns.
# --------------------------------------------------------------------------- #


def read_csv_rows(path, what):
    try:
        with open(path, encoding="utf-8-sig", newline="") as handle:
            return list(csv.reader(handle))
    except (UnicodeDecodeError, csv.Error) as exc:
        raise Refused(f"{what}_UNREADABLE", f"{path}: {exc}")


def load_salaries(path):
    rows = read_csv_rows(path, "SALARY")
    header = rows[0] if rows else []
    missing = [c for c in SALARY_COLUMNS if c not in header]
    if missing:
        raise Refused("SALARY_COLUMNS_MISSING", f"{path} lacks {missing}")
    index = {c: header.index(c) for c in SALARY_COLUMNS}
    sal = {}
    for row in rows[1:]:
        if not row or not any(cell.strip() for cell in row):
            continue
        rec = {c: (row[i].strip() if i < len(row) else "") for c, i in index.items()}
        if not rec["ID"]:
            continue
        if rec["ID"] in sal:
            raise Refused("SALARY_DUPLICATE_ID", rec["ID"])
        if "CPT" in rec["Roster Position"].split("/"):
            raise Refused("NOT_A_CLASSIC_SALARY_FILE", f"{path} has Showdown captain rows")
        try:
            rec["Salary"] = int(rec["Salary"])
        except ValueError:
            raise Refused("SALARY_UNREADABLE", f"ID {rec['ID']} salary {rec['Salary']!r}")
        sal[rec["ID"]] = rec
    if not sal:
        raise Refused("SALARY_EMPTY", f"{path} has no readable rows")
    return sal


def load_scores(path):
    try:
        with open(path, encoding="utf-8") as handle:
            by_id = json.load(handle)["by_dk_id"]
        return {str(k): float(v) for k, v in by_id.items()}
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise Refused("SCORES_UNREADABLE", f"{path}: {type(exc).__name__}: {exc}")


def load_portfolio(path):
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise Refused("PORTFOLIO_UNREADABLE", f"{path}: {exc}")
    assignments = doc.get("assignments_by_entry_id")
    if not isinstance(assignments, dict) or not assignments:
        raise Refused("PORTFOLIO_HAS_NO_ASSIGNMENTS", f"{path} has no assignments_by_entry_id")
    for entry_id, roster in assignments.items():
        if not isinstance(roster, list) or len(roster) != 9:
            raise Refused("PORTFOLIO_ROSTER_MALFORMED", f"entry {entry_id} is not a nine-cell roster")
    return doc


def lock_at(row) -> datetime | None:
    """A salary row's kickoff, from its own `Game Info`, or `None` (TBD/postponed)."""

    parts = (row.get("Game Info") or "").split()
    if len(parts) < 3:
        return None
    try:
        naive = datetime.strptime(" ".join(parts[1:3]), "%m/%d/%Y %I:%M%p")
    except ValueError:
        return None
    return naive.replace(tzinfo=EASTERN)


# --------------------------------------------------------------------------- #
# Shared legality, matching build_classic_portfolio.py's own definitions.
# --------------------------------------------------------------------------- #


class Board:
    """Salary-row accessors and the legality rules every mode shares."""

    def __init__(self, sal, cap, floor):
        self.sal = sal
        self.cap = cap
        self.floor = floor

    def P(self, i):
        return self.sal[i]["Position"]

    def S(self, i):
        return self.sal[i]["Salary"]

    def T(self, i):
        return self.sal[i]["TeamAbbrev"]

    def NM(self, i):
        return self.sal[i]["Name"]

    def G(self, i):
        return self.sal[i]["Game Info"].split()[0] if self.sal[i]["Game Info"] else ""

    def status(self, i):
        return (self.sal[i].get("Status") or "").upper()

    def lock(self, i):
        return lock_at(self.sal[i])

    def opponent(self, i):
        game = self.G(i)
        if "@" not in game:
            return ""
        away, home = game.split("@", 1)
        return home if self.T(i) == away else away

    def qb_of(self, roster):
        qbs = [i for i in roster if i in self.sal and self.P(i) == "QB"]
        return qbs[0] if qbs else None

    def has_bringback(self, roster):
        qb = self.qb_of(roster)
        if qb is None:
            return False
        opp = self.opponent(qb)
        return any(self.T(i) == opp and self.P(i) != "DST" for i in roster if i in self.sal)

    def has_stack(self, roster):
        qb = self.qb_of(roster)
        if qb is None:
            return False
        return any(
            i != qb and i in self.sal and self.T(i) == self.T(qb) and self.P(i) in ("WR", "TE")
            for i in roster
        )

    def preserves_shape(self, original, trial):
        """A stack or bring-back this roster already had must survive the
        edit; this script is never the reason a portfolio's construction
        preferences regress, whatever mode is doing the editing."""

        if self.has_stack(original) and not self.has_stack(trial):
            return False
        if self.has_bringback(original) and not self.has_bringback(trial):
            return False
        return True

    def is_anti_correlated(self, roster):
        dsts = [i for i in roster if i in self.sal and self.P(i) == "DST"]
        if not dsts:
            return False
        dst = dsts[0]
        foe = self.opponent(dst)
        if any(self.T(i) == foe and self.P(i) != "DST" for i in roster if i in self.sal):
            return True  # the DST plays a team you also rostered skill players from
        qb = self.qb_of(roster)
        if qb is not None and self.T(dst) == self.opponent(qb):
            return True  # the DST plays against the QB you rostered
        return False

    def is_legal(self, roster):
        if len(set(roster)) != 9 or any(i not in self.sal for i in roster):
            return False
        need = collections.Counter(self.P(i) for i in roster)
        if need["QB"] != 1 or need["DST"] != 1 or need["RB"] < 2 or need["WR"] < 3 or need["TE"] < 1:
            return False
        total = sum(self.S(i) for i in roster)
        if total > self.cap or total < self.floor:
            return False
        if len({self.G(i) for i in roster}) < 2:
            return False
        return not self.is_anti_correlated(roster)

    def core(self, roster):
        """QB, his stackmates, and his bring-back: never touched by value-add
        or redeploy, so the built stack and bring-back always survive."""

        qb = self.qb_of(roster)
        if qb is None:
            return set()
        opp = self.opponent(qb)
        return {
            i for i in roster
            if i in self.sal and (i == qb or self.T(i) in (self.T(qb), opp))
        }


def fits(board, assignments, entry_id, roster, *, max_exposure, max_overlap):
    """Uniqueness (R29), the overlap cap, and the exposure cap, against every
    OTHER entry's current roster."""

    others = [r for eid, r in assignments.items() if eid != entry_id]
    if frozenset(roster) in {frozenset(r) for r in others}:
        return False
    if any(len(set(roster) & set(other)) > max_overlap for other in others):
        return False
    exposure = collections.Counter()
    for other in others:
        exposure.update(other)
    exposure.update(roster)
    return all(exposure[i] <= max_exposure for i in roster)


def resolve_caps(a, construction):
    cap = a.cap if a.cap is not None else int(construction.get("cap", 50000))
    floor = a.min_salary if a.min_salary is not None else int(construction.get("min_salary", 0))
    max_exposure = (
        a.max_exposure if a.max_exposure is not None
        else construction.get("max_exposure_landed", construction.get("max_exposure"))
    )
    max_overlap = (
        a.max_overlap if a.max_overlap is not None
        else construction.get("max_overlap_landed", construction.get("max_overlap"))
    )
    if max_exposure is None or max_overlap is None:
        raise Refused(
            "CAPS_UNKNOWN",
            "pass --max-exposure and --max-overlap; the portfolio's own construction "
            "block does not carry them",
        )
    return cap, floor, int(max_exposure), int(max_overlap)


# --------------------------------------------------------------------------- #
# Mode: inactive (and late-swap, which is the same search under a lock filter)
# --------------------------------------------------------------------------- #


def newly_out_ids(board, previous_sal):
    return {
        dk_id for dk_id, row in board.sal.items()
        if row["Status"].upper() in UNAVAILABLE_STATUSES
        and dk_id in previous_sal
        and previous_sal[dk_id]["Status"].upper() not in UNAVAILABLE_STATUSES
    }


def swap_inactive(board, scores, assignments, out_ids, *, max_exposure, max_overlap, lock_floor=None):
    """Single-swap first, then a two-player fallback. Returns (log, changed,
    unresolved): `changed` is every entry id whose roster this touched."""

    pool = [i for i in scores if i in board.sal and scores[i] > 0 and i not in out_ids]
    if lock_floor is not None:
        pool = [i for i in pool if (board.lock(i) or lock_floor) > lock_floor]
    log, changed, unresolved = [], set(), []

    def locked(entry_roster, dk_id):
        if lock_floor is None:
            return False
        row_lock = board.lock(dk_id)
        return row_lock is not None and row_lock <= lock_floor

    for entry_id, roster in list(assignments.items()):
        gone_here = [i for i in roster if i in out_ids]
        for gone in gone_here:
            if locked(roster, gone):
                unresolved.append((entry_id, gone, "LOCKED_CELL"))
                continue
            same_group = FLEX_POSITIONS if board.P(gone) in FLEX_POSITIONS else (board.P(gone),)
            candidates = sorted(
                (i for i in pool if board.P(i) in same_group and i not in roster
                 and not locked(roster, i)),
                key=lambda i: -scores[i],
            )
            best = None
            for candidate in candidates:
                trial = [candidate if i == gone else i for i in roster]
                if board.is_legal(trial) and board.preserves_shape(roster, trial) and fits(
                    board, assignments, entry_id, trial,
                    max_exposure=max_exposure, max_overlap=max_overlap,
                ):
                    best = candidate
                    break
            if best is not None:
                assignments[entry_id] = [best if i == gone else i for i in roster]
                changed.add(entry_id)
                log.append(
                    f"SWAP {entry_id}: {board.NM(gone)} ({board.T(gone)} {board.P(gone)}) -> "
                    f"{board.NM(best)} ({board.T(best)} {board.P(best)} ${board.S(best)})"
                )
                roster = assignments[entry_id]
                continue

            pair = _two_player_fallback(
                board, scores, pool, assignments, entry_id, roster, gone, locked,
                max_exposure=max_exposure, max_overlap=max_overlap,
            )
            if pair is None:
                unresolved.append((entry_id, gone, "NO_LEGAL_SWAP"))
                continue
            replacement, dropped, added = pair
            assignments[entry_id] = [
                replacement if i == gone else (added if i == dropped else i) for i in roster
            ]
            changed.add(entry_id)
            log.append(
                f"SWAP2 {entry_id}: {board.NM(gone)} -> {board.NM(replacement)}; "
                f"{board.NM(dropped)} -> {board.NM(added)}"
            )
            roster = assignments[entry_id]
    return log, changed, unresolved


def _two_player_fallback(
    board, scores, pool, assignments, entry_id, roster, gone, locked, *, max_exposure, max_overlap
):
    """No legal single swap exists (the position broke): trade the absent
    player plus one non-core flex-eligible teammate for a better-scoring
    pair. `pool` is already restricted to available, positive-scored,
    unlocked players."""

    core = board.core(roster)
    bench = [
        i for i in roster
        if i not in core and i != gone and board.P(i) in FLEX_POSITIONS and not locked(roster, i)
    ]
    top = sorted(
        (i for i in pool if board.P(i) in FLEX_POSITIONS and i not in roster),
        key=lambda i: -scores[i],
    )[:60]
    best = None
    for replacement in top:
        for dropped in bench:
            for added in top:
                if added in (replacement, dropped) or added in roster:
                    continue
                trial = [
                    replacement if i == gone else (added if i == dropped else i) for i in roster
                ]
                if not board.is_legal(trial) or not board.preserves_shape(roster, trial):
                    continue
                if not fits(board, assignments, entry_id, trial,
                            max_exposure=max_exposure, max_overlap=max_overlap):
                    continue
                gain = scores[replacement] + scores[added] - scores.get(dropped, 0.0)
                if best is None or gain > best[0]:
                    best = (gain, replacement, dropped, added)
    if best is None:
        return None
    _gain, replacement, dropped, added = best
    return replacement, dropped, added


# --------------------------------------------------------------------------- #
# Mode: value-add
# --------------------------------------------------------------------------- #


def value_add(board, scores, assignments, names, target_count, *, max_exposure, max_overlap):
    log = []
    by_name = {board.NM(i): i for i in board.sal}
    for name in names:
        dk_id = by_name.get(name)
        if dk_id is None or dk_id not in scores or scores[dk_id] <= 0:
            log.append(f"VALUE_ADD_SKIPPED {name}: not in the current scored pool")
            continue
        current_exposure = sum(1 for roster in assignments.values() if dk_id in roster)
        for entry_id, roster in sorted(assignments.items()):
            if current_exposure >= target_count:
                break
            if dk_id in roster:
                continue
            core = board.core(roster)
            candidates = sorted(
                (i for i in roster if i not in core and board.P(i) == board.P(dk_id)),
                key=lambda i: scores.get(i, 0.0),
            )
            for weakest in candidates:
                if scores[dk_id] <= scores.get(weakest, 0.0):
                    continue
                trial = [dk_id if i == weakest else i for i in roster]
                if board.is_legal(trial) and fits(
                    board, assignments, entry_id, trial,
                    max_exposure=max_exposure, max_overlap=max_overlap,
                ):
                    assignments[entry_id] = trial
                    current_exposure += 1
                    log.append(f"VALUE_ADD {entry_id}: {board.NM(weakest)} -> {name}")
                    break
    return log


# --------------------------------------------------------------------------- #
# Mode: redeploy
# --------------------------------------------------------------------------- #


def redeploy(board, scores, assignments, changed_entry_ids, *, max_exposure, max_overlap):
    log = []
    pool = [i for i in scores if i in board.sal and scores[i] > 0]
    for entry_id in changed_entry_ids:
        roster = assignments.get(entry_id)
        if roster is None:
            continue
        core = board.core(roster)
        headroom = board.cap - sum(board.S(i) for i in roster)
        best = None
        for current in [i for i in roster if i not in core]:
            for candidate in pool:
                if candidate in roster:
                    continue
                if board.P(candidate) not in (
                    FLEX_POSITIONS if board.P(current) in FLEX_POSITIONS else (board.P(current),)
                ):
                    continue
                if board.S(candidate) - board.S(current) > headroom:
                    continue
                if scores[candidate] <= scores[current]:
                    continue
                trial = [candidate if i == current else i for i in roster]
                if not board.is_legal(trial):
                    continue
                if not fits(board, assignments, entry_id, trial,
                            max_exposure=max_exposure, max_overlap=max_overlap):
                    continue
                gain = scores[candidate] - scores[current]
                if best is None or gain > best[0]:
                    best = (gain, current, candidate)
        if best is not None:
            _gain, current, candidate = best
            assignments[entry_id] = [candidate if i == current else i for i in roster]
            log.append(f"REDEPLOY {entry_id}: {board.NM(current)} -> {board.NM(candidate)}")
    return log


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #


def write_new(out: Path, data: bytes) -> None:
    fd, tmp = tempfile.mkstemp(dir=out.parent, prefix=f".{out.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if Path(tmp).read_bytes() != data:
            raise Refused("VERIFICATION_FAILED", "temporary file does not hold the portfolio bytes")
        if out.exists():
            raise Refused("OUTPUT_EXISTS", f"{out} appeared while writing")
        os.replace(tmp, out)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def run(a) -> dict:
    out = Path(a.out)
    if out.exists():
        raise Refused("OUTPUT_EXISTS", f"{a.out} already exists; an earlier portfolio is never overwritten")

    portfolio = load_portfolio(a.portfolio)
    scores = load_scores(a.scores)
    sal = load_salaries(a.salaries)
    construction = dict(portfolio.get("construction") or {})
    cap, floor, max_exposure, max_overlap = resolve_caps(a, construction)
    board = Board(sal, cap, floor)
    assignments = {eid: list(roster) for eid, roster in portfolio["assignments_by_entry_id"].items()}

    unresolved = []
    if a.mode in ("inactive", "late-swap"):
        if a.previous_salaries and a.inactive_id:
            raise Refused("CONFLICTING_INACTIVE_SOURCE", "pass --previous-salaries or --inactive-id, not both")
        if a.previous_salaries:
            previous = load_salaries(a.previous_salaries)
            out_ids = newly_out_ids(board, previous)
        elif a.inactive_id:
            out_ids = set(a.inactive_id)
        else:
            raise Refused("NO_INACTIVE_SOURCE", "pass --previous-salaries or --inactive-id")
        lock_floor = None
        if a.mode == "late-swap":
            if a.now is None:
                raise Refused("NOW_REQUIRED", "--mode late-swap requires --now")
            lock_floor = a.now
        log, changed, unresolved = swap_inactive(
            board, scores, assignments, out_ids,
            max_exposure=max_exposure, max_overlap=max_overlap, lock_floor=lock_floor,
        )
    elif a.mode == "value-add":
        if not a.add:
            raise Refused("NO_NAMES", "--mode value-add requires at least one --add NAME")
        log = value_add(
            board, scores, assignments, a.add, a.target_count,
            max_exposure=max_exposure, max_overlap=max_overlap,
        )
        changed = {eid for eid, roster in assignments.items()
                   if roster != portfolio["assignments_by_entry_id"][eid]}
    elif a.mode == "redeploy":
        changed_entry_ids = a.changed_entry_id or construction.get("changed_entry_ids") or []
        if not changed_entry_ids:
            raise Refused(
                "NO_CHANGED_ENTRIES",
                "--mode redeploy needs --changed-entry-id, or a portfolio whose "
                "construction.changed_entry_ids names them",
            )
        log = redeploy(
            board, scores, assignments, changed_entry_ids,
            max_exposure=max_exposure, max_overlap=max_overlap,
        )
        changed = {eid for eid, roster in assignments.items()
                   if roster != portfolio["assignments_by_entry_id"][eid]}
    else:
        raise Refused("MODE_UNKNOWN", a.mode)

    doc = dict(portfolio)
    doc["assignments_by_entry_id"] = assignments
    doc["lineups"] = [
        {
            "index": n + 1,
            "entry_id": eid,
            "roster": roster,
            "salary": sum(board.S(i) for i in roster),
            "prior_points": round(sum(scores.get(i, 0.0) for i in roster), 3),
            "bringback": board.has_bringback(roster),
        }
        for n, (eid, roster) in enumerate(assignments.items())
    ]
    doc["construction"] = {
        **construction,
        "mode": a.mode,
        "cap": cap,
        "min_salary": floor,
        "max_exposure": max_exposure,
        "max_overlap": max_overlap,
        "changed_entry_ids": sorted(changed),
        "swap_log": construction.get("swap_log", []) + log,
    }
    data = json.dumps(doc, indent=1).encode("utf-8")
    write_new(out, data)
    return {
        "log": log,
        "changed": sorted(changed),
        "unresolved": unresolved,
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--portfolio", required=True, help="portfolio json to edit")
    ap.add_argument("--scores", required=True, help="current gated pool scores json, read as ['by_dk_id']")
    ap.add_argument("--salaries", required=True, help="current DKSalaries.csv")
    ap.add_argument("--out", required=True, help="portfolio json to write; a new path, never an input")
    ap.add_argument("--mode", required=True, choices=("inactive", "value-add", "redeploy", "late-swap"))
    ap.add_argument("--cap", type=int, default=None)
    ap.add_argument("--min-salary", type=int, default=None)
    ap.add_argument("--max-exposure", type=int, default=None)
    ap.add_argument("--max-overlap", type=int, default=None)
    ap.add_argument("--previous-salaries", help="mode inactive/late-swap: the salary file this portfolio was built from")
    ap.add_argument("--inactive-id", action="append", default=[], help="mode inactive/late-swap: an explicit dk_id")
    ap.add_argument("--add", action="append", default=[], help="mode value-add: a Name from --salaries")
    ap.add_argument("--target-count", type=int, default=3, help="mode value-add: lineups to work each --add into")
    ap.add_argument("--changed-entry-id", action="append", default=[], help="mode redeploy: an entry id to consider")
    ap.add_argument(
        "--now", type=lambda s: datetime.fromisoformat(s).astimezone(timezone.utc) if s else None,
        default=None, help="mode late-swap: ISO 8601; a cell whose game locked at or before this is never touched",
    )
    a = ap.parse_args(argv)
    try:
        result = run(a)
    except Refused as exc:
        print(f"REFUSED {exc.code}: {exc.detail}", file=sys.stderr)
        print("nothing was written", file=sys.stderr)
        return EXIT_REFUSED

    print("\n".join(result["log"]) or "no rostered player changed")
    print(f"changed entries: {result['changed']}")
    print(f"sha256: {result['sha256']}")
    print(f"wrote: {a.out}")
    if result["unresolved"]:
        for entry_id, dk_id, reason in result["unresolved"]:
            print(f"UNRESOLVED {entry_id}: {dk_id} ({reason})", file=sys.stderr)
        return EXIT_PARTIAL
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
