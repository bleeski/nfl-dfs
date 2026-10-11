"""Week 5 Classic late swap (a record, never a tool).

Usage: python late_swap_record.py <portfolio in> <portfolio out> <DKSalaries.csv> <scores.json> <now ISO+offset> \
           "ENTRY_ID:OUT_DK_ID:IN_DK_ID:REASON" ...

Applies each named swap and refuses the whole run (writes nothing) when any swap touches a player whose game
has kicked off at <now> (outgoing or incoming), leaves an illegal DraftKings shape or a salary over 50,000,
puts a skill player against his own row's DST, repeats a roster (R29), or names a player not in the row.
Prints the portfolio washout measures and each multi-entry contest's measures before and after.
Writes no prior.
"""
import csv
import itertools
import json
import sys
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo

src, out, sal_path, sc_path, now_s = sys.argv[1:6]
swaps = [a.split(":", 3) for a in sys.argv[6:]]
now = datetime.fromisoformat(now_s)
S = {r["ID"]: r for r in csv.DictReader(open(sal_path, encoding="utf-8-sig"))}
sc = json.load(open(sc_path))["by_dk_id"]
d = json.load(open(src))
A = d["assignments_by_entry_id"]
before_rows = {k: list(v) for k, v in A.items()}
ET = ZoneInfo("America/New_York")


def kickoff(k):
    parts = S[k]["Game Info"].split(" ")
    return datetime.strptime(parts[1] + " " + parts[2], "%m/%d/%Y %I:%M%p").replace(tzinfo=ET)


def g(k): return S[k]["Game Info"].split(" ")[0]
def p(k): return S[k]["Position"]
def t(k): return S[k]["TeamAbbrev"]


def legal(l):
    c = Counter(p(x) for x in l)
    return (len(set(l)) == 9 and c["QB"] == 1 and c["DST"] == 1 and c["RB"] >= 2 and c["WR"] >= 3 and c["TE"] >= 1
            and c["RB"] + c["WR"] + c["TE"] == 7 and sum(int(S[x]["Salary"]) for x in l) <= 50000)


def measures(rows):
    rows = list(rows)
    use = Counter(x for l in rows for x in l)
    top3 = [x for x, _ in use.most_common(3)]
    pairs = list(itertools.combinations(rows, 2))
    return {"max_exposure": max(use.values()), "top3_union": sum(1 for l in rows if set(l) & set(top3)),
            "mean_overlap": round(sum(len(set(a) & set(b)) for a, b in pairs) / len(pairs), 4) if pairs else 0.0,
            "distinct": len(use)}


log = []
for e, out_id, in_id, reason in swaps:
    l = A[e]
    if out_id not in l:
        sys.exit(f"REFUSED {e}: {out_id} is not in the row")
    for k in (out_id, in_id):
        if kickoff(k) <= now:
            sys.exit(f"REFUSED {e}: {S[k]['Name']} ({k}) kicked off at {kickoff(k).isoformat()}, now {now.isoformat()}")
    tr = [in_id if x == out_id else x for x in l]
    if not legal(tr):
        sys.exit(f"REFUSED {e}: illegal shape or salary after {S[out_id]['Name']} -> {S[in_id]['Name']}")
    dst = [x for x in tr if p(x) == "DST"][0]
    if any(x != dst and g(x) == g(dst) and t(x) != t(dst) for x in tr):
        sys.exit(f"REFUSED {e}: {S[in_id]['Name']} faces the row's DST {S[dst]['Name']}")
    if tuple(sorted(tr)) in {tuple(sorted(v)) for k, v in A.items() if k != e}:
        sys.exit(f"REFUSED {e}: duplicate roster")
    A[e] = tr
    log.append(f"LATE_SWAP {e}: {S[out_id]['Name']} ({out_id}, prior {sc.get(out_id, 0):.2f}) -> {S[in_id]['Name']} "
               f"({in_id}, prior {sc.get(in_id, 0):.2f}); {reason}")

d["lineups"] = [dict(old, roster=A[k], salary=sum(int(S[x]["Salary"]) for x in A[k]),
                     prior_points=round(sum(sc.get(x, 0) for x in A[k]), 3)) for old, k in zip(d["lineups"], A)]
d.setdefault("construction", {}).setdefault("late_swap", []).extend(log)
json.dump(d, open(out, "x"), indent=1)
print("\n".join(log))
print("portfolio", measures(before_rows.values()), "->", measures(A.values()))
