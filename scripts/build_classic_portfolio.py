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
import json
import random
import sys


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


def reserved_entry_ids(path):
    """Entry IDs from a DKEntries template, in template order.

    Order is the contract: `write_dk_entries.py` fills the nine blank roster
    cells of each row it is given, and the operator reads the result top to
    bottom against the same file DraftKings exported.
    """
    ids = []
    with open(path, encoding="utf-8-sig", newline="") as fh:
        for row in csv.reader(fh):
            if row and row[0].strip().isdigit():
                ids.append(row[0].strip())
    return ids


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--scores", required=True, help="pool scores json, read as ['by_dk_id']")
    ap.add_argument("--salaries", required=True, help="DKSalaries.csv")
    ap.add_argument("--status", required=True, help="official_status.csv")
    ap.add_argument("--out", required=True, help="portfolio json to write")
    ap.add_argument("--entries", help="DKEntries template; supplies the reserved Entry IDs")
    ap.add_argument("--slate-context", help="json: implied_team_totals, projected_ownership, role_boosts")
    ap.add_argument("--lineups", type=int, default=20)
    ap.add_argument("--cap", type=int, default=50000)
    ap.add_argument("--min-salary", type=int, default=0,
                    help="reject a lineup below this; unspent salary is late-swap option value (P1-7)")
    ap.add_argument("--max-exposure", type=int, default=6, help="max lineups one person may appear in")
    ap.add_argument("--max-overlap", type=int, default=4, help="max shared players between any two lineups")
    ap.add_argument("--require-bringback", action="store_true",
                    help="every lineup must pair the QB stack with an opposing skill player")
    ap.add_argument("--seed", type=int, default=913)
    ap.add_argument("--attempts", type=int, default=900000)
    a = ap.parse_args(argv)

    random.seed(a.seed)
    N, CAP, FLOOR = a.lineups, a.cap, a.min_salary

    scores = json.load(open(a.scores, encoding="utf-8"))["by_dk_id"]
    sal = {r["ID"]: r for r in csv.DictReader(open(a.salaries, encoding="utf-8-sig"))}
    status = {r["PLAYER_OR_GSIS_ID"]: r["STATUS"]
              for r in csv.DictReader(open(a.status, encoding="utf-8-sig"))}
    ITT, OWN, BOOST = load_slate_context(a.slate_context)

    P = lambda i: sal[i]["Position"]
    S = lambda i: int(sal[i]["Salary"])
    T = lambda i: sal[i]["TeamAbbrev"]
    NM = lambda i: sal[i]["Name"]
    G = lambda i: sal[i]["Game Info"].split()[0]

    def OPP(i):
        away, home = G(i).split("@")
        return home if T(i) == away else away

    pool = [i for i in scores if i in sal and status.get(i) != "INACTIVE" and scores[i] > 0]
    if not pool:
        raise SystemExit("EMPTY_POOL: no scored, available player survived the filter")

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
    for att in range(a.attempts):
        if len(lineups) == N:
            break
        if att and att % 150000 == 0:
            # Ratchet. Reported at the end, never silent: a relaxed cap is a
            # construction preference Claude may drop under a lock clock, but the
            # handoff has to say which rung it landed on.
            EXP = min(EXP + 1, max(EXP + 1, 9))
            OVL = min(OVL + 1, 6)
            need_bb = max(need_bb - 3, 6)
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
        if any(len(set(r) & set(x)) > OVL for x in lineups):
            continue
        lineups.append(r)
        for i in r:
            exp[i] += 1

    print(f"built {len(lineups)} | exposure cap {EXP}/{N}, overlap cap {OVL}"
          f"{', bring-back required' if a.require_bringback else ''}")
    if len(lineups) < N:
        print(f"  WARNING: asked for {N}, produced {len(lineups)}. Relax a cap or widen the pool.")

    # The mapping write_dk_entries.py consumes. Empty until 2026-09-20, which
    # meant every slate filled it by hand.
    assignments = {}
    if a.entries:
        ids = reserved_entry_ids(a.entries)
        if len(ids) < len(lineups):
            raise SystemExit(
                f"ENTRY_ID_SHORTFALL: {len(ids)} reserved Entry IDs for {len(lineups)} lineups"
            )
        assignments = {eid: r for eid, r in zip(ids, lineups)}

    json.dump({"lineups": [{"index": n + 1, "roster": r, "salary": sum(S(i) for i in r),
                            "prior_points": round(sum(scores[i] for i in r), 3),
                            "bringback": has_bringback(r)}
                           for n, r in enumerate(lineups)],
               "assignments_by_entry_id": assignments,
               "construction": {"seed": a.seed, "lineups": N, "cap": CAP,
                                "min_salary": FLOOR, "max_exposure_landed": EXP,
                                "max_overlap_landed": OVL,
                                "require_bringback": a.require_bringback,
                                "slate_context": a.slate_context or None}},
              open(a.out, "w"), indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
