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
        [--template <DKEntries.csv> --export <written entries csv>]  # after the writer \\
        [--backup-pairs 'Brock Purdy>Mac Jones;Lamar Jackson>Tyler Huntley'] \\
        [--min-salary 47500] [--max-overlap 4] [--max-exposure 6] \\
        [--implied-totals team_totals.csv]   # TEAM,IMPLIED_TOTAL
        [--ownership ownership.csv]          # NAME,OWNERSHIP_PCT
        [--json out.json]

## 2026-09-23 (Session 02): the final CSV is what gets checked

The 2026-09-22 audit (issue #40, D6) found that this gate validated the JSON
rosters and never the file. With `--template` and `--export` it compared cell
values outside the roster, counted non-empty rosters only `if rosters`, and never
compared an exported roster to the lineup assigned to that Entry ID. A file whose
reserved rows were blank, swapped or placed in the wrong slots printed PASS.
Now, with `--template` and `--export`:

* **Export audit, on bytes.** The template and export are split into raw lines
  with `nfl_dfs.byte_lines`. Every line must be byte-identical except a blank
  authorized row, which may differ only inside its nine roster cells, with the
  same field count and line ending. The old cell comparison is gone; its name,
  "byte fidelity", claimed more than it checked.
* **Each exported roster against its assignment**, by Entry ID, and each cell
  against the salary file's slot eligibility, so the rosters that upload go
  through Tier 1, not only the JSON.
* **Coverage is unconditional.** Every blank authorized row is filled or listed
  as unfilled. An assigned row left blank, an assignment Entry ID the template
  does not hold, and an export byte-identical to the template are failures.

Exit codes separate validity from strategy: 1 a validity failure (roster
legality, slot eligibility, export bytes, export against assignment, a repeated
lineup under R29, an officially inactive player); 3 valid, but authorized rows
are unfilled and each Entry ID is named; 2 only an operator-requested limit
(`--min-salary`, `--max-overlap`, `--max-exposure`, `--backup-pairs`); else 0.
A backup pair moved from 1 to 2: it is the operator's assertion about who
starts, with no evidence bound to it. Tier 2 never changes the exit code; it
prints a scorecard and names what a human has to accept. Without `--export` the
verdict covers the portfolio JSON only, and says so.
"""
from __future__ import annotations
import argparse, csv, itertools, json, re, statistics, sys
from collections import Counter

from nfl_dfs.byte_lines import csv_field_spans, split_byte_lines, split_line_ending

SLOTS = ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX", "DST"]
NEED = {"QB": 1, "RB": 2, "WR": 3, "TE": 1, "DST": 1}
FLEX_OK = {"RB", "WR", "TE"}
EXIT_PASS, EXIT_FAIL, EXIT_DEFECT, EXIT_PARTIAL = 0, 1, 2, 3
_TRAILING_ID = re.compile(r"\((\d+)\)\s*$")


def cell_id(cell):
    """A roster cell's DraftKings ID, whether it holds `123` or `Name (123)`."""
    match = _TRAILING_ID.search(cell)
    return match.group(1) if match else cell.strip()


def load_rows(path, key):
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return {r[key]: r for r in csv.DictReader(fh)}


def read_portfolio(path):
    """Return (rosters to check, the Entry ID map or None)."""
    d = json.load(open(path, encoding="utf-8"))
    assigned = d.get("assignments_by_entry_id") or None
    if assigned:
        assigned = {str(k).strip(): [str(x).strip() for x in (v["roster"] if isinstance(v, dict) else v)]
                    for k, v in assigned.items()}
        return list(assigned.values()), assigned
    if "lineups" in d:
        return [l["roster"] for l in d["lineups"]], None
    raise SystemExit("portfolio json has neither 'lineups' nor a populated 'assignments_by_entry_id'")


def cells_of(line):
    body, _ = split_line_ending(line)
    return next(csv.reader([body.decode("utf-8-sig", errors="replace")]), [])


def roster_region_changed_only(t_line, e_line, lo):
    """True when two raw lines differ at most inside fields lo..lo+8."""
    (tb, te), (eb, ee) = split_line_ending(t_line), split_line_ending(e_line)
    try:
        ts, es = csv_field_spans(tb), csv_field_spans(eb)
    except ValueError:
        return False
    if te != ee or len(ts) != len(es) or len(ts) < lo + 9:
        return False
    hi = lo + 8
    return tb[:ts[lo][0]] == eb[:es[lo][0]] and tb[ts[hi][1]:] == eb[es[hi][1]:]


def export_audit(template, export, assigned):
    """Compare the export to the untouched template on raw bytes.

    Only a blank authorized row may change, and only inside its nine roster
    cells. Returns (failures, exported rosters by Entry ID in slot order,
    unfilled authorized Entry IDs).
    """
    fail, exported, unfilled, prefilled = [], {}, [], {}
    t_raw, e_raw = open(template, "rb").read(), open(export, "rb").read()
    t_lines, e_lines = split_byte_lines(t_raw), split_byte_lines(e_raw)
    if len(t_lines) != len(e_lines):
        return [f"LINE_COUNT_CHANGED template={len(t_lines)} export={len(e_lines)}"], {}, []
    hdr = cells_of(t_lines[0]) if t_lines else []
    if "Entry Fee" not in hdr or hdr[hdr.index("Entry Fee") + 1:hdr.index("Entry Fee") + 10] != SLOTS:
        return ["NOT_A_CLASSIC_TEMPLATE: the template header has no Classic roster after Entry Fee"], {}, []
    lo = hdr.index("Entry Fee") + 1
    template_ids = []
    for n, (t, e) in enumerate(zip(t_lines, e_lines)):
        tc = cells_of(t)
        eid = tc[0].strip() if n and tc else ""
        entry = eid.isdigit()
        blank = entry and not any(c.strip() for c in tc[lo:lo + 9])
        if entry:
            template_ids.append(eid)
        if entry and not blank and t == e:
            prefilled[eid] = [cell_id(c) for c in tc[lo:lo + 9]]
        if t == e:
            if blank:
                if assigned is not None and eid in assigned:
                    fail.append(f"ASSIGNED_ROW_NOT_FILLED: entry {eid} is assigned and blank in the export")
                else:
                    unfilled.append(eid)
            continue
        if not blank:
            fail.append(f"LINE_{n + 1}_BYTES_CHANGED on a line that is not a blank authorized row")
            continue
        if not roster_region_changed_only(t, e, lo):
            fail.append(f"LINE_{n + 1}_BYTES_CHANGED_OUTSIDE_ROSTER entry {eid}")
            continue
        cells = [c.strip() for c in cells_of(e)[lo:lo + 9]]
        if not all(cells):
            fail.append(f"PARTIALLY_FILLED_ROW: entry {eid} has {sum(map(bool, cells))} of 9 cells")
            continue
        exported[eid] = cells
    export_ids = [c[0].strip() for c in map(cells_of, e_lines[1:]) if c and c[0].strip().isdigit()]
    if template_ids != export_ids:
        fail.append("ENTRY_ID_ORDER_OR_COVERAGE_MISMATCH")
    if t_raw == e_raw and (unfilled or assigned):
        fail.append("EXPORT_IDENTICAL_TO_TEMPLATE: nothing was filled")
    if assigned is None:
        fail.append("EXPORT_HAS_NO_ASSIGNMENT_MAP: the portfolio has no assignments_by_entry_id, "
                    "so no exported roster can be checked against its lineup")
    else:
        for eid in sorted(set(assigned) - set(template_ids)):
            fail.append(f"ASSIGNMENT_ENTRY_ID_NOT_IN_TEMPLATE: {eid}")
        for eid in sorted(set(assigned) & set(prefilled)):
            fail.append(f"ASSIGNED_ROW_WAS_PREFILLED: entry {eid} was not blank in the template, "
                        "so its assignment is not what the file holds")
        for eid, cells in exported.items():
            if eid not in assigned:
                fail.append(f"EXPORT_ROW_NOT_IN_ASSIGNMENT: entry {eid}")
            elif sorted(cells) != sorted(assigned[eid]):
                fail.append(f"EXPORT_ROSTER_DIFFERS_FROM_ASSIGNMENT: entry {eid}")
    # R29 covers the whole file, including rows filled before this run.
    rows = [tuple(sorted(c)) for c in [*exported.values(), *prefilled.values()] if all(c)]
    if len(set(rows)) != len(rows):
        fail.append("DUPLICATE_LINEUPS_IN_EXPORT: a lineup appears in more than one row")
    return fail, exported, unfilled


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--portfolio", required=True)
    ap.add_argument("--salaries", required=True)
    ap.add_argument("--status")
    ap.add_argument("--template", help="the untouched DKEntries export")
    ap.add_argument("--export", help="the written entries CSV, audited on bytes against --template")
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

    L, assigned = read_portfolio(a.portfolio)
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
    fail = []        # validity: exit 1
    defects = []     # operator-requested limits: exit 2
    unfilled = []    # coverage: exit 3

    def check_lineup(label, r, enforce=True):
        """Validity always; the operator's limits only on the portfolio, so none prints twice."""
        if len(r) != 9:
            fail.append(f"{label}: {len(r)} players"); return
        if len(set(r)) != 9:
            fail.append(f"{label}: duplicate player")
        unknown = [x for x in r if x not in sal]
        if unknown:
            fail.append(f"{label}: id not in salary pool {unknown}"); return
        c = Counter(P(i) for i in r)
        for pos, n_req in NEED.items():
            if c[pos] < n_req:
                fail.append(f"{label}: {c[pos]} {pos}, need {n_req}")
        if c["QB"] != 1:
            fail.append(f"{label}: {c['QB']} QB")
        if c["DST"] != 1:
            fail.append(f"{label}: {c['DST']} DST")
        if c["RB"] + c["WR"] + c["TE"] != 7:
            fail.append(f"{label}: flex shape {dict(c)}")
        tot = sum(S(i) for i in r)
        if tot > a.cap:
            fail.append(f"{label}: salary {tot} over {a.cap}")
        if enforce and a.min_salary and tot < a.min_salary:
            defects.append(f"{label}: salary {tot} under the {a.min_salary} floor")
        if len({G(i) for i in r}) < 2:
            fail.append(f"{label}: violates the two-game rule")
        ina = [NM(i) for i in r if status.get(i) == "INACTIVE"]
        if ina:
            fail.append(f"{label}: INACTIVE rostered {ina}")
        names = {NM(i) for i in r}
        for starter, backup in (pairs if enforce else ()):
            if backup in names and starter not in names:
                defects.append(f"{label}: starts {backup}, the backup to {starter}")
            if backup in names and starter in names:
                defects.append(f"{label}: {starter} alongside own backup {backup}")

    for n, r in enumerate(L, 1):
        check_lineup(f"L{n}", r)

    # duplicate lineups, on the canonical player set; R29 makes this validity
    canon = [tuple(sorted(r)) for r in L]
    if len(set(canon)) != len(canon):
        dupes = [k for k, v in Counter(canon).items() if v > 1]
        fail.append(f"DUPLICATE_LINEUPS: {len(dupes)} roster(s) appear more than once")

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

    export_checked = bool(a.template and a.export)
    if export_checked:
        audit, exported, unfilled = export_audit(a.template, a.export, assigned)
        fail.extend(audit)
        for eid, cells in exported.items():
            for slot, i in zip(SLOTS, cells):
                if i not in sal:
                    continue
                eligible = {t.strip() for t in sal[i]["Roster Position"].split("/")}
                fixed_ok = slot != "FLEX" and P(i) == slot
                flex_ok = slot == "FLEX" and P(i) in FLEX_OK
                if slot not in eligible or not (fixed_ok or flex_ok):
                    fail.append(f"SLOT_INELIGIBLE: entry {eid}: {NM(i)} ({P(i)}, "
                                f"{sal[i]['Roster Position']}) in {slot}")
            check_lineup(f"entry {eid}", cells, enforce=False)
    elif a.template or a.export:
        fail.append("EXPORT_CHECK_INCOMPLETE: --template and --export must be given together")

    print("=" * 62)
    print("TIER 1  VALIDITY, COVERAGE AND ENFORCEMENT  (blocking)")
    print("=" * 62)
    print(f"  lineups: {len(L)}")
    if export_checked:
        print(f"  export checked: {a.export}")
    else:
        print("  export not checked: this verdict covers the portfolio JSON, not a DraftKings file")
    print(f"  validity failures: {len(fail)}")
    for f in fail:
        print(f"    ! {f}")
    if not fail:
        print("    all lineups legal")
    if export_checked:
        print(f"  unfilled authorized Entry IDs: {len(unfilled)} {unfilled}")
        if unfilled:
            print("    name them in the handoff; never repeat a lineup to fill them (R29)")
    print(f"  enforcement defects (operator-requested limits): {len(defects)}")
    for d in defects:
        print(f"    ! {d}")
    if not defects:
        print("    no enforced limit exceeded")

    if not L:
        # A builder shortfall can emit zero lineups; there is nothing to score.
        print("    ! NO_LINEUPS: the portfolio holds no lineup")
        print()
        print("  VERDICT: FAIL")
        if a.json:
            json.dump({"verdict": "FAIL", "export_checked": export_checked,
                       "validity_failures": fail + ["NO_LINEUPS"],
                       "unfilled_entry_ids": unfilled, "enforcement_defects": defects},
                      open(a.json, "w"), indent=1)
        return EXIT_FAIL

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

    verdict = ("FAIL" if fail else "PARTIAL" if unfilled
               else "DEFECT" if defects else "PASS")
    print()
    print(f"  VERDICT: {verdict}")

    if a.json:
        json.dump({"verdict": verdict,
                   "export_checked": export_checked,
                   "validity_failures": fail,
                   "unfilled_entry_ids": unfilled,
                   "enforcement_defects": defects,
                   "max_exposure": mx[1] / n_l,
                   "top3_union": top3_union / n_l,
                   "distinct_players": len(exp),
                   "max_overlap": max(overlaps) if overlaps else 0,
                   "stacked": stacked, "bringback": bringback,
                   "anti_correlation": anti},
                  open(a.json, "w"), indent=1)
    if fail:
        return EXIT_FAIL
    if unfilled:
        return EXIT_PARTIAL
    return EXIT_DEFECT if defects else EXIT_PASS


if __name__ == "__main__":
    sys.exit(main())
