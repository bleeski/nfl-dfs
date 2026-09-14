#!/usr/bin/env python3
"""Two-tier QA gate for a Classic portfolio.

Tier 1 is legality and is BLOCKING. Tier 2 is portfolio coherence and is
SCORED: it does not block, but the run may not be handed off without showing it.

The reason Tier 2 exists: on 2026-09-13 the Week 1 main-slate portfolio passed
every legality check with zero failures and was still a bad portfolio. Three
players covered 17 of 20 lineups, four lineups paired a DST against skill players
in its own game, and only 9 of 20 carried a bring-back. A legality checker cannot
see any of that, because nothing was illegal. An adversarial reviewer found all
of it in eight minutes. This script encodes what that reviewer checked so the
next slate does not depend on remembering to ask.

Usage:
    python scripts/qa_classic_portfolio.py \
        --portfolio <selection or portfolio json> \
        --salaries  <run>/inputs/DKSalaries.csv \
        --status    <run>/status/official_status.csv \
        [--implied-totals team_totals.csv]   # TEAM,IMPLIED_TOTAL
        [--ownership ownership.csv]          # NAME,OWNERSHIP_PCT
        [--json out.json]

Exit code is 1 if any Tier 1 check fails, else 0. Tier 2 never changes the exit
code; it prints a scorecard and names what a human has to accept.
"""
from __future__ import annotations
import argparse, csv, itertools, json, statistics, sys
from collections import Counter, defaultdict

SLOTS = ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX", "DST"]
NEED = {"QB": 1, "RB": 2, "WR": 3, "TE": 1, "DST": 1}
FLEX_OK = {"RB", "WR", "TE"}


def load_rows(path, key):
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return {r[key]: r for r in csv.DictReader(fh)}


def read_portfolio(path):
    d = json.load(open(path, encoding="utf-8"))
    if "lineups" in d:
        return [l["roster"] for l in d["lineups"]]
    if "assignments_by_entry_id" in d:
        return list(d["assignments_by_entry_id"].values())
    raise SystemExit("portfolio json has neither 'lineups' nor 'assignments_by_entry_id'")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--portfolio", required=True)
    ap.add_argument("--salaries", required=True)
    ap.add_argument("--status")
    ap.add_argument("--implied-totals")
    ap.add_argument("--ownership")
    ap.add_argument("--json")
    ap.add_argument("--cap", type=int, default=50000)
    a = ap.parse_args(argv)

    sal = load_rows(a.salaries, "ID")
    status = {}
    if a.status:
        status = {r["PLAYER_OR_GSIS_ID"]: r["STATUS"]
                  for r in csv.DictReader(open(a.status, encoding="utf-8-sig"))}
    itt = {}
    if a.implied_totals:
        for r in csv.DictReader(open(a.implied_totals, encoding="utf-8-sig")):
            itt[r["TEAM"].strip()] = float(r["IMPLIED_TOTAL"])
    own = {}
    if a.ownership:
        for r in csv.DictReader(open(a.ownership, encoding="utf-8-sig")):
            own[r["NAME"].strip()] = float(r["OWNERSHIP_PCT"])

    L = read_portfolio(a.portfolio)
    P = lambda i: sal[i]["Position"]
    S = lambda i: int(sal[i]["Salary"])
    T = lambda i: sal[i]["TeamAbbrev"]
    NM = lambda i: sal[i]["Name"]
    G = lambda i: sal[i]["Game Info"].split()[0]

    def opp(i):
        away, home = G(i).split("@")
        return home if T(i) == away else away

    # ---------------------------------------------------------- TIER 1
    fail = []
    for n, r in enumerate(L, 1):
        if len(r) != 9:
            fail.append(f"L{n}: {len(r)} players"); continue
        if len(set(r)) != 9:
            fail.append(f"L{n}: duplicate player")
        unknown = [x for x in r if x not in sal]
        if unknown:
            fail.append(f"L{n}: id not in salary pool {unknown}"); continue
        c = Counter(P(i) for i in r)
        for pos, n_req in NEED.items():
            if c[pos] < n_req:
                fail.append(f"L{n}: {c[pos]} {pos}, need {n_req}")
        if c["QB"] != 1:
            fail.append(f"L{n}: {c['QB']} QB")
        if c["DST"] != 1:
            fail.append(f"L{n}: {c['DST']} DST")
        if c["RB"] + c["WR"] + c["TE"] != 7:
            fail.append(f"L{n}: flex shape {dict(c)}")
        tot = sum(S(i) for i in r)
        if tot > a.cap:
            fail.append(f"L{n}: salary {tot} over {a.cap}")
        if len({G(i) for i in r}) < 2:
            fail.append(f"L{n}: violates the two-game rule")
        ina = [NM(i) for i in r if status.get(i) == "INACTIVE"]
        if ina:
            fail.append(f"L{n}: INACTIVE rostered {ina}")
        q = [i for i in r if P(i) == "QB"]
        for x in q:
            mates = [NM(i) for i in r if i != x and P(i) == "QB" and T(i) == T(x)]
            if mates:
                fail.append(f"L{n}: QB {NM(x)} alongside own backup {mates}")

    print("=" * 62)
    print("TIER 1  LEGALITY  (blocking)")
    print("=" * 62)
    print(f"  lineups: {len(L)}")
    print(f"  failures: {len(fail)}")
    for f in fail:
        print(f"    ! {f}")
    if not fail:
        print("    all lineups legal")

    # ---------------------------------------------------------- TIER 2
    exp = Counter(i for r in L for i in r)
    n_l = len(L)
    overlaps = [len(set(x) & set(y)) for x, y in itertools.combinations(L, 2)]
    top3 = [i for i, _ in exp.most_common(3)]
    top3_union = sum(1 for r in L if any(i in r for i in top3))

    anti = {"dst_vs_own_skill": [], "dst_vs_own_qb": [], "qb_vs_opposing_dst": []}
    stacked = bringback = 0
    env = []
    for n, r in enumerate(L, 1):
        qs = [i for i in r if P(i) == "QB"]
        ds = [i for i in r if P(i) == "DST"]
        if qs:
            q = qs[0]
            if any(P(i) in ("WR", "TE") and T(i) == T(q) for i in r):
                stacked += 1
            if any(T(i) == opp(q) and P(i) != "DST" for i in r):
                bringback += 1
        if ds:
            d = ds[0]
            clash = [NM(i) for i in r if P(i) != "DST" and T(i) == opp(d)]
            if clash:
                anti["dst_vs_own_skill"].append(f"L{n}: {NM(d)} DST vs {clash}")
            if qs and T(d) == opp(qs[0]):
                anti["dst_vs_own_qb"].append(f"L{n}: {NM(d)} DST vs own QB {NM(qs[0])}")
        if itt:
            skill = [i for i in r if P(i) != "DST"]
            env.append((n, sum(itt.get(T(i), 0) for i in skill) / max(len(skill), 1)))

    print()
    print("=" * 62)
    print("TIER 2  PORTFOLIO COHERENCE  (scored, must be shown at handoff)")
    print("=" * 62)
    print("  CONCENTRATION")
    mx = exp.most_common(1)[0]
    print(f"    max single-player exposure : {mx[1]}/{n_l} ({mx[1]*100//n_l}%)  {NM(mx[0])}")
    print(f"    top-3 union coverage       : {top3_union}/{n_l} ({top3_union*100//n_l}%)"
          f"   <- 85% on 2026-09-13 meant a 4-lineup portfolio")
    print(f"    distinct players           : {len(exp)}")
    print(f"    pairwise overlap max/mean  : {max(overlaps) if overlaps else 0} / "
          f"{statistics.mean(overlaps):.2f}" if overlaps else "    n/a")
    print("  ANTI-CORRELATION  (all should be zero)")
    for k, v in anti.items():
        print(f"    {k:<20s}: {len(v)}")
        for x in v[:6]:
            print(f"        ! {x}")
    print("  STACK INTEGRITY")
    print(f"    QB + own pass catcher      : {stacked}/{n_l}")
    print(f"    bring-back                 : {bringback}/{n_l}")
    if env:
        env.sort(key=lambda t: t[1])
        print("  GAME ENVIRONMENT  (avg implied total of skill slots)")
        print(f"    portfolio mean             : {statistics.mean(v for _, v in env):.2f}")
        print("    weakest lineups            : " +
              ", ".join(f"L{n}={v:.1f}" for n, v in env[:4]))
    if own:
        per = []
        for r in L:
            per.append(sum(own.get(NM(i), 0.0) for i in r))
        print("  LEVERAGE")
        print(f"    mean summed ownership/lineup: {statistics.mean(per):.1f} pts")
        print("    chalkiest lineups           : " +
              ", ".join(f"L{n+1}={v:.0f}" for n, v in
                        sorted(enumerate(per), key=lambda t: -t[1])[:4]))
        print("    leanest lineups             : " +
              ", ".join(f"L{n+1}={v:.0f}" for n, v in
                        sorted(enumerate(per), key=lambda t: t[1])[:4]))

    print()
    print("  TOP EXPOSURES")
    for i, c in exp.most_common(12):
        o = own.get(NM(i))
        tag = f"  field {o:.0f}%" if o is not None else ""
        print(f"    {c:2d}/{n_l} {c*100//n_l:3d}%  {NM(i):<22s} {P(i):4s} {T(i):4s} "
              f"${S(i)}{tag}")

    if a.json:
        json.dump({"tier1_failures": fail,
                   "max_exposure": mx[1] / n_l,
                   "top3_union": top3_union / n_l,
                   "distinct_players": len(exp),
                   "max_overlap": max(overlaps) if overlaps else 0,
                   "stacked": stacked, "bringback": bringback,
                   "anti_correlation": anti},
                  open(a.json, "w"), indent=1)
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
