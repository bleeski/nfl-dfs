#!/usr/bin/env python3
"""Construction layer for a Classic GPP portfolio. NOT the evidence layer.

Provenance: this is the code that actually produced the 2026-09-13 Week 1
portfolio, promoted out of a session scratchpad. On that slate the engine's C2
candidate-bank solver failed six times across 43 minutes and never produced a
portfolio; this script produced one in about ten minutes from the engine's own
gated per-player scores. See docs/CLASSIC_C4_RETROSPECTIVE_2026-09-13.md.

The split it assumes: the ENGINE owns evidence (priors, identity, weather,
official activity, participation) and emits a scored player pool. THIS owns
construction (stacking, bring-backs, exposure caps, anti-correlation, leverage),
which CLAUDE.md classes as preferences Claude may set under a lock clock.

Input `scores.json` is currently produced by `selection.write_pool_scores`, via
the `NFL_DFS_DUMP_SCORES` environment variable or the `pool_scores_path` kwarg.
Backlog P1-4 gives it a first-class CLI surface; when it lands, only the loader
below changes.

## 2026-09-20: what changed and why

Three defects surfaced on the Week 2 slate, all recorded in `changelog.md`:

* **The pipeline was broken in the middle.** This script emitted
  `assignments_by_entry_id` as a literal empty dict while
  `scripts/write_dk_entries.py` reads exactly that key, so the mapping from
  lineup to reserved Entry ID had to be produced by hand on every slate. It is
  now built here from the DKEntries template, in template order.
* **Three slate-specific tables were hardcoded.** `ITT`, `OWN` and `BOOST` held
  literal 2026-09-13 values: Week 1 implied totals, Week 1 ownership, and role
  boosts keyed to Week 1 absences (Bowers, Kamara). Carrying those into any
  later slate is wrong data, not a stale preference, and patching them by hand
  each week is where a mistake gets made. They now arrive in `--slate-context`,
  built by `scripts/make_slate_context.py` from the run's own captured
  `games.csv`, and default to empty rather than to last week.
* **Construction limits were constants.** The bring-back quota in particular was
  probabilistic (85%) rather than required, which on 2026-09-20 produced 12 of
  18 lineups with a bring-back against a suggested floor of 70%. They are flags
  now, and `--require-bringback` makes it structural.

## 2026-09-23 (Session 02b): what changed and why

The 2026-09-22 audit (issue #40, D6) found that a shortfall printed a WARNING
and exited 0, so the chain could ship blank reserved rows with nothing naming
them. Now the three fallback stages share one exit vocabulary:

* 0: every blank authorized row has a lineup, and every lineup is distinct.
* 2: refused by name (`REFUSED <CODE>: ...` on stderr), and nothing is written.
* 3: written with a shortfall. `unfilled_entry_ids` lists every blank row that
  has no lineup, and stderr names each one. R29: a lineup is never repeated to
  fill a row, and a lineup already prefilled in the template is never built
  again, whatever `--max-overlap` allows.

And:

* The ratchet has a ceiling and never tightens what the operator asked for:
  exposure stops at `max(--max-exposure, N)` and overlap at
  `max(--max-overlap, 6)`. `min(EXP + 1, max(EXP + 1, 9))` was always
  `EXP + 1`, and `min(OVL + 1, 6)` pulled `--max-overlap 9` down to 6.
* DraftKings `OUT`, `IR` and `D` rows leave the pool, by the engine's one
  vocabulary (`nfl_dfs.contracts.UNAVAILABLE_DK_STATUSES`). `selection.py`
  writes scores.json before its own exclusion set, so they arrived scored.
  `--available-status D` restores doubtful players, as it does in the engine.
* Only blank template rows are reserved, and `--lineups` defaults to their
  count. A prefilled row was assigned and the writer then refused the file. The
  template is read as the writer reads it: a repeated Entry ID is refused, and a
  blank row too narrow for nine roster cells is left blank and named.
* A DraftKings status outside the engine's vocabulary (blank, `Q`, `OUT`, `IR`,
  `D`) also leaves the pool, and is named on stderr.
* `--out` must be a new path that is none of the inputs. The bytes go to a
  temporary file beside it, are re-read, then `os.replace`d.
* The salary file is read by eight named columns; nothing else is parsed. A
  Showdown salary file, a repeated ID, an unreadable salary, a truncated
  scores.json and a status file without its columns are refused by name.

Exit 0 does not clear an upload: the portfolio is `PRIOR_ONLY / DO_NOT_UPLOAD`,
and `scripts/qa_classic_portfolio.py --template --export` runs on the written
file.

Known gaps, all tracked in Appendix A of the retrospective:
  P1-6  dart conditions here still predate the rewrite (top-4 total, lowest
        ownership) rather than "names the prior it is short" + 2-12% with a role
  P1-8  no early-locked vs swap-flexible entry tagging
  P1-9  the prior model's exclusion list is not used as a dart candidate pool
  P1-10 QB leverage is not taken first
"""

import argparse
import collections
import csv
import hashlib
import json
import os
import random
import re
import sys
import tempfile
from pathlib import Path

from nfl_dfs.contracts import UNAVAILABLE_DK_STATUSES
from nfl_dfs.participation import AVAILABLE_STATUSES, DEGRADED_STATUSES

SLOTS = ("QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX", "DST")
# Only these salary columns are ever read; nothing else in the file is parsed.
SALARY_COLUMNS = ("ID", "Name", "Position", "Roster Position", "Salary", "Game Info",
                  "TeamAbbrev", "Status")
EXIT_FILLED, EXIT_REFUSED, EXIT_PARTIAL = 0, 2, 3
# Attempts between ratchet steps. A module constant so tests can drive it.
RATCHET_EVERY = 150000
OVERLAP_CEILING = 6
_TRAILING_ID = re.compile(r"\((\d+)\)\s*$")


class Refused(Exception):
    """One or more named refusals; nothing is written."""

    def __init__(self, problems):
        super().__init__("; ".join(f"{code}: {detail}" for code, detail in problems))
        self.problems = problems


def load_slate_context(path):
    """Implied team totals, projected ownership and role boosts for THIS slate.

    Every one of these is slate-specific. An empty context is the honest default:
    the builder then ranks on the engine's scores alone, which is weaker but not
    wrong. A stale context is wrong, which is why there is no baked-in fallback.
    """
    if not path:
        return {}, {}, {}
    d = json.load(open(path, encoding="utf-8"))
    itt = {str(k): float(v) for k, v in (d.get("implied_team_totals") or {}).items()}
    own = {str(k): float(v) for k, v in (d.get("projected_ownership") or {}).items()}
    boost = {str(k): float(v) for k, v in (d.get("role_boosts") or {}).items()}
    return itt, own, boost


def cell_id(cell):
    """A roster cell's DraftKings ID, whether it holds `123` or `Name (123)`."""

    match = _TRAILING_ID.search(cell)
    return match.group(1) if match else cell.strip()


def read_template(path):
    """(assignable Entry IDs, rosters already filled, every blank Entry ID), in template order.

    Read the way `write_dk_entries.parse_template` reads it, so the two agree on
    what is authorized. A row is blank when every roster cell it has is empty. It
    is assignable when it is blank and wide enough to hold nine roster cells; a
    narrower blank row is never assigned, because the writer refuses to fill it,
    and is reported unfilled instead. A filled row is never assigned either.
    """

    try:
        with open(path, encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.reader(fh))
    except (UnicodeDecodeError, csv.Error) as exc:
        raise Refused([("TEMPLATE_UNREADABLE", f"{path}: {exc}")])
    header = rows[0] if rows else []
    fee = header.index("Entry Fee") if "Entry Fee" in header else -1
    end = fee + 1 + len(SLOTS)
    after = header[end] if len(header) > end else ""
    if fee < 0 or tuple(header[fee + 1:end]) != SLOTS or after not in ("", "Instructions"):
        raise Refused([("NOT_A_CLASSIC_TEMPLATE",
                        f"{path} has no Entry Fee column followed by {list(SLOTS)}")])
    assignable, prefilled, blank, seen = [], [], [], set()
    for row in rows[1:]:
        eid = row[0].strip() if row else ""
        if not eid.isdigit():
            continue
        if eid in seen:
            raise Refused([("DUPLICATE_TEMPLATE_ENTRY_ID", eid)])
        seen.add(eid)
        cells = [c.strip() for c in row[fee + 1:end]]
        if not any(cells):
            blank.append(eid)
            if len(row) >= end:
                assignable.append(eid)
        elif len(cells) == len(SLOTS) and all(cells):
            prefilled.append(frozenset(cell_id(c) for c in cells))
    return assignable, prefilled, blank


def reserved_entry_ids(path):
    """Blank Entry IDs from a DKEntries template, in template order.

    Order is the contract: `write_dk_entries.py` fills the nine blank roster
    cells of each row it is given, and the operator reads the result top to
    bottom against the same file DraftKings exported.
    """
    return read_template(path)[0]


def read_csv_rows(path, what):
    try:
        with open(path, encoding="utf-8-sig", newline="") as fh:
            return list(csv.reader(fh))
    except (UnicodeDecodeError, csv.Error) as exc:
        raise Refused([(f"{what}_UNREADABLE", f"{path}: {exc}")])


def load_salaries(path):
    rows = read_csv_rows(path, "SALARY")
    header = rows[0] if rows else []
    missing = [c for c in SALARY_COLUMNS if c not in header]
    if missing:
        raise Refused([("SALARY_COLUMNS_MISSING", f"{path} lacks {missing}")])
    index = {c: header.index(c) for c in SALARY_COLUMNS}
    sal = {}
    for row in rows[1:]:
        if not row or not any(cell.strip() for cell in row):
            continue
        rec = {c: (row[i].strip() if i < len(row) else "") for c, i in index.items()}
        if rec["ID"] in sal:
            raise Refused([("SALARY_DUPLICATE_ID", rec["ID"])])
        if "CPT" in rec["Roster Position"].split("/"):
            raise Refused([("NOT_A_CLASSIC_SALARY_FILE",
                            f"{path} has Showdown captain rows; this builder is Classic only")])
        try:
            rec["Salary"] = int(rec["Salary"])
        except ValueError:
            raise Refused([("SALARY_UNREADABLE", f"ID {rec['ID']} salary {rec['Salary']!r}")])
        sal[rec["ID"]] = rec
    return sal


def load_scores(path):
    try:
        with open(path, encoding="utf-8") as fh:
            by_id = json.load(fh)["by_dk_id"]
        return {str(k): float(v) for k, v in by_id.items()}
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise Refused([("SCORES_UNREADABLE", f"{path}: {type(exc).__name__}: {exc}")])


def load_status(path):
    rows = read_csv_rows(path, "STATUS")
    header = rows[0] if rows else []
    missing = [c for c in ("PLAYER_OR_GSIS_ID", "STATUS") if c not in header]
    if missing:
        raise Refused([("STATUS_COLUMNS_MISSING", f"{path} lacks {missing}")])
    ident, state = header.index("PLAYER_OR_GSIS_ID"), header.index("STATUS")
    return {r[ident]: r[state] for r in rows[1:] if len(r) > max(ident, state)}


def next_rung(exp, ovl, need_bb, asked_exp, asked_ovl, n):
    """One ratchet step: loosen toward a ceiling, never below what was asked.

    Exposure stops at N lineups (or the operator's own higher cap), overlap at
    OVERLAP_CEILING (or higher, if asked), and the bring-back target falls by
    three to a floor of 6 without ever rising.
    """

    return (min(exp + 1, max(asked_exp, n)),
            min(ovl + 1, max(asked_ovl, OVERLAP_CEILING)),
            max(need_bb - 3, min(need_bb, 6)))


def check_output_path(out, inputs):
    def same(x, y):
        if x.resolve() == y.resolve():
            return True
        try:
            return x.exists() and y.exists() and os.path.samefile(x, y)
        except OSError:
            return False

    if any(same(out, p) for p in inputs):
        return [("OUTPUT_IS_AN_INPUT", f"{out} is one of the inputs")]
    if out.exists():
        return [("OUTPUT_EXISTS", f"{out} already exists; an earlier portfolio is never overwritten")]
    if not out.parent.is_dir():
        return [("OUTPUT_DIRECTORY_MISSING", str(out.parent))]
    return []


def write_new(out, data):
    fd, tmp = tempfile.mkstemp(dir=out.parent, prefix=f".{out.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        if Path(tmp).read_bytes() != data:
            raise Refused([("VERIFICATION_FAILED", "temporary file does not hold the portfolio bytes")])
        if out.exists():
            raise Refused([("OUTPUT_EXISTS", f"{out} appeared while building")])
        os.replace(tmp, out)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--scores", required=True, help="pool scores json, read as ['by_dk_id']")
    ap.add_argument("--salaries", required=True, help="DKSalaries.csv")
    ap.add_argument("--status", required=True, help="official_status.csv")
    ap.add_argument("--out", required=True, help="portfolio json to write; a new path, never an input")
    ap.add_argument("--entries", help="DKEntries template; its blank rows are the reserved Entry IDs")
    ap.add_argument("--slate-context", help="json: implied_team_totals, projected_ownership, role_boosts")
    ap.add_argument("--lineups", type=int,
                    help="default: the template's blank rows with --entries, else 20")
    ap.add_argument("--cap", type=int, default=50000)
    ap.add_argument("--min-salary", type=int, default=0,
                    help="reject a lineup below this; unspent salary is late-swap option value (P1-7)")
    ap.add_argument("--max-exposure", type=int, default=6, help="max lineups one person may appear in")
    ap.add_argument("--max-overlap", type=int, default=4, help="max shared players between any two lineups")
    ap.add_argument("--require-bringback", action="store_true",
                    help="every lineup must pair the QB stack with an opposing skill player")
    ap.add_argument("--available-status", action="append", default=[],
                    help="a DraftKings Status to keep in the pool (e.g. D), as in the engine")
    ap.add_argument("--seed", type=int, default=913)
    ap.add_argument("--attempts", type=int, default=900000)
    a = ap.parse_args(argv)
    try:
        report = build(a)
    except Refused as exc:
        for code, detail in exc.problems:
            print(f"REFUSED {code}: {detail}", file=sys.stderr)
        print("nothing was written", file=sys.stderr)
        return EXIT_REFUSED

    unfilled, short = report["unfilled"], report["shortfall"]
    if report["unknown"]:
        print(f"UNKNOWN_DK_STATUS: rows flagged {report['unknown']} are outside the engine's "
              "vocabulary and left the pool. Keep one with --available-status CODE.",
              file=sys.stderr)
    print(f"unfilled authorized Entry IDs: {len(unfilled)} {unfilled}")
    print(f"sha256: {report['sha256']}")
    print(f"wrote: {a.out}")
    if short:
        print(f"SHORTFALL: asked for {report['asked']} distinct lineups, built {report['built']}. "
              "Never repeat a lineup to close the gap (R29); relax a construction cap or name "
              "the gap in the handoff.", file=sys.stderr)
    if unfilled:
        print(f"UNFILLED_AUTHORIZED_ROWS: {len(unfilled)} blank authorized rows have no lineup: "
              f"{unfilled}. The writer leaves them blank and exits 3.", file=sys.stderr)
    return EXIT_PARTIAL if short or unfilled else EXIT_FILLED


def build(a):
    out = Path(a.out)
    inputs = [Path(x) for x in (a.scores, a.salaries, a.status, a.entries, a.slate_context) if x]
    problems = check_output_path(out, inputs)
    if problems:
        raise Refused(problems)
    blank, prefilled, open_rows = read_template(a.entries) if a.entries else ([], [], [])
    if a.entries and not blank:
        raise Refused([("NO_BLANK_ENTRY_ROWS",
                        f"{a.entries} has no blank authorized row wide enough to fill")])
    N = a.lineups if a.lineups is not None else (len(blank) if a.entries else 20)
    if N < 1:
        raise Refused([("LINEUPS_NOT_POSITIVE", f"--lineups {N}")])
    if a.entries and len(blank) < N:
        raise Refused([("ENTRY_ID_SHORTFALL",
                        f"{len(blank)} blank reserved Entry IDs for {N} lineups")])

    random.seed(a.seed)
    CAP, FLOOR = a.cap, a.min_salary

    scores = load_scores(a.scores)
    sal = load_salaries(a.salaries)
    status = load_status(a.status)
    ITT, OWN, BOOST = load_slate_context(a.slate_context)
    kept = {s.strip().upper() for s in a.available_status if s.strip()}
    unavailable = UNAVAILABLE_DK_STATUSES - kept
    # A code outside the engine's vocabulary is never taken as available: it
    # leaves the pool and is named (R28 keeps the file; the gap is reported).
    known = AVAILABLE_STATUSES | DEGRADED_STATUSES | UNAVAILABLE_DK_STATUSES | kept
    unknown = set()

    P = lambda i: sal[i]["Position"]
    S = lambda i: sal[i]["Salary"]
    T = lambda i: sal[i]["TeamAbbrev"]
    NM = lambda i: sal[i]["Name"]
    G = lambda i: sal[i]["Game Info"].split()[0]

    def OPP(i):
        away, home = G(i).split("@")
        return home if T(i) == away else away

    dropped = collections.Counter()
    pool = []
    for i in scores:
        if i not in sal or status.get(i) == "INACTIVE" or scores[i] <= 0:
            continue
        flag = sal[i]["Status"].upper()
        if flag not in known:
            unknown.add(flag)
        if flag in unavailable or flag not in known:
            dropped[flag] += 1
            continue
        pool.append(i)
    if not pool:
        raise Refused([("EMPTY_POOL", "no scored, available player survived the filter")])

    def wt(i):
        w = 1.0 + (ITT.get(T(i), 21.0) - 21.0) * 0.090      # steeper than v1
        o = OWN.get(NM(i))
        if o is not None:
            w *= 1.0 + (12.0 - min(o, 50.0)) * 0.010
        return w * BOOST.get(NM(i), 1.0)

    val = {i: scores[i] * wt(i) for i in pool}

    QBS = [i for i in pool if P(i) == "QB"]
    CCH = lambda t: [i for i in pool if T(i) == t and P(i) in ("WR", "TE")]
    SKL = lambda t: [i for i in pool if T(i) == t and P(i) in ("WR", "TE", "RB")]

    def anti(r):
        """Reject self-cancelling construction."""
        d = [i for i in r if P(i) == "DST"]
        if not d:
            return True
        dst = d[0]
        foe = OPP(dst)
        if any(T(i) == foe and P(i) != "DST" for i in r):
            return True                                      # DST vs own skill
        q = [i for i in r if P(i) == "QB"]
        if q and T(dst) == OPP(q[0]):
            return True                                      # DST vs own QB
        return False

    def has_bringback(r):
        q = [i for i in r if P(i) == "QB"]
        if not q:
            return False
        return any(T(i) == OPP(q[0]) and P(i) != "DST" for i in r)

    def pick(c, exp, cap, k=1, ex=()):
        c = [i for i in c if i not in ex and exp[i] < cap]
        if len(c) < k:
            return []
        w = [max(val.get(i, .01), .01) ** 2.2 for i in c]
        out, seen = [], set()
        for _ in range(k * 8):
            if len(out) == k:
                break
            x = random.choices(c, weights=w, k=1)[0]
            if x not in seen:
                seen.add(x)
                out.append(x)
        return out if len(out) == k else []

    def complete(seed, exp, cap):
        r = list(seed)
        need = {"QB": 1, "RB": 2, "WR": 3, "TE": 1, "DST": 1}
        for i in r:
            need[P(i)] = need.get(P(i), 0) - 1
        if any(v < 0 for v in need.values()):
            return None
        for p in [p for p, n in need.items() for _ in range(max(0, n))]:
            g = pick([i for i in pool if P(i) == p], exp, cap, 1, ex=r)
            if not g:
                return None
            r.append(g[0])
        if len(r) < 9:
            g = pick([i for i in pool if P(i) in ("RB", "WR", "TE")], exp, cap, 1, ex=r)
            if not g:
                return None
            r.append(g[0])
        if len(r) != 9 or len(set(r)) != 9:
            return None
        tot = sum(S(i) for i in r)
        if tot > CAP or tot < FLOOR:
            return None
        if len({G(i) for i in r}) < 2:
            return None
        if anti(r):
            return None
        return r

    lineups = []
    exp = collections.Counter()
    EXP, OVL = a.max_exposure, a.max_overlap
    need_bb = int(N * 0.7)
    steps = 0
    # R29 covers the whole file: a roster already in the template counts too.
    taken = set(prefilled)
    for att in range(a.attempts):
        if len(lineups) == N:
            break
        if att and att % RATCHET_EVERY == 0:
            # Ratchet. Reported at the end, never silent: a relaxed cap is a
            # construction preference Claude may drop under a lock clock, but the
            # handoff has to say which rung it landed on.
            rung = next_rung(EXP, OVL, need_bb, a.max_exposure, a.max_overlap, N)
            steps += rung != (EXP, OVL, need_bb)
            EXP, OVL, need_bb = rung
        q = pick(QBS, exp, EXP, 1)
        if not q:
            continue
        q = q[0]
        mates = CCH(T(q))
        if not mates:
            continue
        seed = [q] + pick(mates, exp, EXP, 1, ex=[q])
        if len(seed) < 2:
            continue
        if random.random() < 0.60:
            seed += pick(mates, exp, EXP, 1, ex=seed)
        bb = len([1 for L in lineups if has_bringback(L)])
        if a.require_bringback or random.random() < 0.85 or bb < need_bb * len(lineups) // max(N, 1):
            seed += pick(SKL(OPP(q)), exp, EXP, 1, ex=seed)
            if a.require_bringback and not any(T(i) == OPP(q) and P(i) != "DST" for i in seed):
                continue
        r = complete(seed, exp, EXP)
        if not r:
            continue
        if a.require_bringback and not has_bringback(r):
            continue
        if frozenset(r) in taken:
            continue                                         # R29: never a repeat
        if any(len(set(r) & set(x)) > OVL for x in lineups):
            continue
        lineups.append(r)
        taken.add(frozenset(r))
        for i in r:
            exp[i] += 1

    print(f"built {len(lineups)} of {N} | exposure cap {EXP}/{N} (asked {a.max_exposure}), "
          f"overlap cap {OVL} (asked {a.max_overlap}), {steps} ratchet steps"
          f"{', bring-back required' if a.require_bringback else ''}")
    print(f"pool: {len(pool)} players; DraftKings status dropped: {dict(sorted(dropped.items()))}")

    # The mapping write_dk_entries.py consumes, in template order over blank rows.
    assignments = {eid: r for eid, r in zip(blank, lineups)}
    unfilled = [eid for eid in open_rows if eid not in assignments]
    doc = {"lineups": [{"index": n + 1, "roster": r, "salary": sum(S(i) for i in r),
                        "prior_points": round(sum(scores[i] for i in r), 3),
                        "bringback": has_bringback(r)}
                       for n, r in enumerate(lineups)],
           "assignments_by_entry_id": assignments,
           "unfilled_entry_ids": unfilled,
           "shortfall": N - len(lineups),
           "construction": {"seed": a.seed, "lineups": N, "lineups_built": len(lineups),
                            "cap": CAP, "min_salary": FLOOR,
                            "max_exposure_requested": a.max_exposure,
                            "max_exposure_landed": EXP,
                            "max_overlap_requested": a.max_overlap,
                            "max_overlap_landed": OVL, "ratchet_steps": steps,
                            "require_bringback": a.require_bringback,
                            "dk_unavailable_statuses": sorted(unavailable),
                            "dk_status_dropped": dict(sorted(dropped.items())),
                            "dk_status_unknown": sorted(unknown),
                            "prefilled_rows": len(prefilled),
                            "slate_context": a.slate_context or None}}
    data = json.dumps(doc, indent=1).encode("utf-8")
    write_new(out, data)
    return {"unfilled": unfilled, "shortfall": N - len(lineups), "asked": N,
            "built": len(lineups), "unknown": sorted(unknown),
            "sha256": hashlib.sha256(data).hexdigest()}


if __name__ == "__main__":
    sys.exit(main())
