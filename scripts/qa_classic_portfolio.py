#!/usr/bin/env python3
"""Two-tier QA gate for a Classic portfolio.

Tier 1 is legality and enforcement, and is BLOCKING. Tier 2 is portfolio
coherence and is SCORED: it does not block, but the run may not be handed off
without showing it.

The reason Tier 2 exists: on 2026-09-13 the Week 1 main-slate portfolio passed
every legality check with zero failures and was still a bad portfolio. Three
players covered 17 of 20 lineups, four lineups paired a DST against skill players
in its own game, and only 9 of 20 carried a bring-back. A legality checker cannot
see any of that, because nothing was illegal. An adversarial reviewer found all
of it in eight minutes. This script encodes what that reviewer checked so the
next slate does not depend on remembering to ask.

## 2026-09-20: what changed and why

The Week 2 session shipped a portfolio with 12 of 18 bring-backs against the
suggested floor of 70%, and four lineups starting a backup quarterback. Tier 2
already measured the first and this script was simply never run; the second it
could not measure at all. Recorded in `changelog.md`. Changes:

* **The backup-QB check was dead code.** It looked for a second
  `Position == "QB"` on the same team, which legal DK Classic cannot produce
  because FLEX is RB/WR/TE only, and the `exactly one QB` check already fails
  first. It is replaced by `--backup-pairs STARTER>BACKUP`, ported from
  `scripts/qa_showdown_portfolio.py`, which is the check that actually catches
  a lineup starting somebody's backup.
* **`qb_vs_opposing_dst` was declared and never appended to**, so it always
  printed zero. In a nine-man lineup with one QB and one DST it is the same
  relation as `dst_vs_own_qb`. Removed rather than faked: a duplicate metric
  that always reads zero is worse than no metric.
* **Overlap and exposure were reported but not enforced.** Its Showdown twin
  has enforced overlap as a defect with exit 2 since 2026-09-14. Both are now
  enforceable here, opt-in via `--max-overlap` / `--max-exposure`.
* **Byte fidelity, duplicate lineups and entry-ID coverage were absent**, all
  three present in the twin. Ported.
* **No salary floor.** Added as `--min-salary`: unspent salary is late-swap
  option value (P1-7), and a lineup far under the cap is usually an accident.

Usage:
    python scripts/qa_classic_portfolio.py \\
        --portfolio <selection or portfolio json> \\
        --salaries  <run>/inputs/DKSalaries.csv \\
        --status    <run>/status/official_status.csv \\
        [--template <DKEntries.csv> --export <written entries csv>] \\
        [--backup-pairs 'Brock Purdy>Mac Jones;Lamar Jackson>Tyler Huntley'] \\
        [--min-salary 47500] [--max-overlap 4] [--max-exposure 6] \\
        [--implied-totals team_totals.csv]   # TEAM,IMPLIED_TOTAL
        [--ownership ownership.csv]          # NAME,OWNERSHIP_PCT
        [--json out.json]

Exit 1 if any Tier 1 legality check fails, 2 if only an enforcement defect
fires, else 0. Tier 2 never changes the exit code; it prints a scorecard and
names what a human has to accept.
"""
from __future__ import annotations
import argparse, csv, itertools, json, statistics, sys
from collections import Counter

SLOTS = ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX", "DST"]
NEED = {"QB": 1, "RB": 2, "WR": 3, "TE": 1, "DST": 1}
FLEX_OK = {"RB", "WR", "TE"}


def load_rows(path, key):
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return {r[key]: r for r in csv.DictReader(fh)}


def read_portfolio(path):
    d = json.load(open(path, encoding="utf-8"))
    if d.get("assignments_by_entry_id"):
        return list(d["assignments_by_entry_id"].values())
    if "lineups" in d:
        return [l["roster"] for l in d["lineups"]]
    raise SystemExit("portfolio json has neither 'lineups' nor a populated 'assignments_by_entry_id'")


def rows_of(path):
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.reader(fh))


def byte_fidelity(template, export):
    """Only the nine roster cells of a reserved row may differ from the template.

    Ported from qa_showdown_portfolio.py, which has had this since 2026-09-14.
    The Classic export is the operator's own DKEntries file with blanks filled;
    anything else that moved is a defect, not a formatting difference.
    """
    defects = []
    tpl, exp = rows_of(template), rows_of(export)
    if len(tpl) != len(exp):
        defects.append(f"ROW_COUNT_CHANGED template={len(tpl)} export={len(exp)}")
        return defects, [], []
    hdr = exp[0]
    try:
        fee = hdr.index("Entry Fee")
    except ValueError:
        defects.append("EXPORT_HEADER_HAS_NO_ENTRY_FEE_COLUMN")
        return defects, [], []
    lo, hi = fee + 1, fee + 10
    for i, (t, e) in enumerate(zip(tpl, exp)):
        width = max(len(t), len(e))
        t = t + [""] * (width - len(t))
        e = e + [""] * (width - len(e))
        reserved = i > 0 and t and t[0].strip().isdigit()
        for j, (tv, ev) in enumerate(zip(t, e)):
            if tv != ev and not (reserved and lo <= j < hi):
                defects.append(f"ROW_{i}_COL_{j}_MUTATED {tv!r}->{ev!r}")
    tpl_ids = [r[0].strip() for r in tpl if r and r[0].strip().isdigit()]
    exp_ids = [r[0].strip() for r in exp if r and r[0].strip().isdigit()]
    if tpl_ids != exp_ids:
        defects.append("ENTRY_ID_ORDER_OR_COVERAGE_MISMATCH")
    rosters = [[c.strip() for c in r[lo:hi]] for r in exp
               if r and r[0].strip().isdigit() and any(c.strip() for c in r[lo:hi])]
    return defects, exp_ids, rosters


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--portfolio", required=True)
    ap.add_argument("--salaries", required=True)
    ap.add_argument("--status")
    ap.add_argument("--template", help="the untouched DKEntries export")
    ap.add_argument("--export", help="the written entries CSV, checked byte-for-byte against --template")
    ap.add_argument("--backup-pairs", default="",
                    help="semicolon list of STARTER>BACKUP names; flags a lineup starting the backup")
    ap.add_argument("--implied-totals")
    ap.add_argument("--ownership")
    ap.add_argument("--json")
    ap.add_argument("--cap", type=int, default=50000)
    ap.add_argument("--min-salary", type=int, default=0)
    ap.add_argument("--max-overlap", type=int, help="enforced when given")
    ap.add_argument("--max-exposure", type=int, help="enforced when given")
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

    pairs = []
    for item in a.backup_pairs.split(";"):
        if ">" in item:
            starter, backup = item.split(">", 1)
            pairs.append((starter.strip(), backup.strip()))

    # ---------------------------------------------------------- TIER 1
    fail = []
    defects = []
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
        if a.min_salary and tot < a.min_salary:
            defects.append(f"L{n}: salary {tot} under the {a.min_salary} floor")
        if len({G(i) for i in r}) < 2:
            fail.append(f"L{n}: violates the two-game rule")
        ina = [NM(i) for i in r if status.get(i) == "INACTIVE"]
        if ina:
            fail.append(f"L{n}: INACTIVE rostered {ina}")
        names = {NM(i) for i in r}
        for starter, backup in pairs:
            if backup in names and starter not in names:
                fail.append(f"L{n}: starts {backup}, the backup to {starter}")
            if backup in names and starter in names:
                fail.append(f"L{n}: {starter} alongside own backup {backup}")

    # duplicate lineups, on the canonical player set
    canon = [tuple(sorted(r)) for r in L]
    if len(set(canon)) != len(canon):
        dupes = [k for k, v in Counter(canon).items() if v > 1]
        defects.append(f"DUPLICATE_LINEUPS: {len(dupes)} roster(s) appear more than once")

    overlaps_pairs = []
    for (x, rx), (y, ry) in itertools.combinations(list(enumerate(L, 1)), 2):
        o = len(set(rx) & set(ry))
        overlaps_pairs.append(o)
        if a.max_overlap is not None and o > a.max_overlap:
            defects.append(f"OVERLAP_{o}_EXCEEDS_{a.max_overlap}: L{x}/L{y}")

    exp = Counter(i for r in L for i in r)
    if a.max_exposure is not None:
        for i, ct in exp.items():
            if ct > a.max_exposure:
                defects.append(f"EXPOSURE_{ct}_EXCEEDS_{a.max_exposure}: {NM(i)}")

    if a.template and a.export:
        bf, exp_ids, rosters = byte_fidelity(a.template, a.export)
        defects.extend(bf)
        if rosters and len(rosters) != len(L):
            defects.append(f"EXPORT_LINEUP_COUNT {len(rosters)} != portfolio {len(L)}")
    elif a.template or a.export:
        defects.append("BYTE_FIDELITY_SKIPPED: --template and --export must be given together")

    print("=" * 62)
    print("TIER 1  LEGALITY AND ENFORCEMENT  (blocking)")
    print("=" * 62)
    print(f"  lineups: {len(L)}")
    print(f"  legality failures: {len(fail)}")
    for f in fail:
        print(f"    ! {f}")
    if not fail:
        print("    all lineups legal")
    print(f"  enforcement defects: {len(defects)}")
    for d in defects:
        print(f"    ! {d}")
    if not defects:
        print("    no enforced limit exceeded")

    # ---------------------------------------------------------- TIER 2
    n_l = len(L)
    overlaps = overlaps_pairs
    top3 = [i for i, _ in exp.most_common(3)]
    top3_union = sum(1 for r in L if any(i in r for i in top3))

    anti = {"dst_vs_own_skill": [], "dst_vs_own_qb": []}
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
    if overlaps:
        print(f"    pairwise overlap max/mean  : {max(overlaps)} / {statistics.mean(overlaps):.2f}")
    print("  ANTI-CORRELATION  (all should be zero)")
    for k, v in anti.items():
        print(f"    {k:<20s}: {len(v)}")
        for x in v[:6]:
            print(f"        ! {x}")
    print("  STACK INTEGRITY")
    print(f"    QB + own pass catcher      : {stacked}/{n_l}")
    print(f"    bring-back                 : {bringback}/{n_l}"
          f"   <- suggested floor 70%, was 12/18 on 2026-09-20")
    if env:
        env.sort(key=lambda t: t[1])
        print("  GAME ENVIRONMENT  (avg implied total of skill slots)")
        print(f"    portfolio mean             : {statistics.mean(v for _, v in env):.2f}")
        print("    weakest lineups            : " +
              ", ".join(f"L{n}={v:.1f}" for n, v in env[:4]))
    if own:
        per = [sum(own.get(NM(i), 0.0) for i in r) for r in L]
        print("  LEVERAGE")
        print(f"    mean summed ownership/lineup: {statistics.mean(per):.1f} pts")
        print("    chalkiest lineups           : " +
              ", ".join(f"L{n+1}={v:.0f}" for n, v in
                        sorted(enumerate(per), key=lambda t: -t[1])[:4]))
        print("    leanest lineups             : " +
              ", ".join(f"L{n+1}={v:.0f}" for n, v in
                        sorted(enumerate(per), key=lambda t: t[1])[:4]))
    else:
        print("  LEVERAGE")
        print("    no ownership supplied: this portfolio carries NO leverage model.")
        print("    Say so at handoff. Mean-max in a large field is chalk.")

    print()
    print("  TOP EXPOSURES")
    for i, c in exp.most_common(12):
        o = own.get(NM(i))
        tag = f"  field {o:.0f}%" if o is not None else ""
        print(f"    {c:2d}/{n_l} {c*100//n_l:3d}%  {NM(i):<22s} {P(i):4s} {T(i):4s} "
              f"${S(i)}{tag}")

    verdict = "FAIL" if fail else ("DEFECT" if defects else "PASS")
    print()
    print(f"  VERDICT: {verdict}")

    if a.json:
        json.dump({"verdict": verdict,
                   "tier1_failures": fail,
                   "enforcement_defects": defects,
                   "max_exposure": mx[1] / n_l,
                   "top3_union": top3_union / n_l,
                   "distinct_players": len(exp),
                   "max_overlap": max(overlaps) if overlaps else 0,
                   "stacked": stacked, "bringback": bringback,
                   "anti_correlation": anti},
                  open(a.json, "w"), indent=1)
    if fail:
        return 1
    return 2 if defects else 0


if __name__ == "__main__":
    sys.exit(main())
