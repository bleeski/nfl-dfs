"""Week 5 afternoon Classic: Pareto search over whole-lineup exchanges between contests (a record, never a tool).

Usage: python contest_pareto_record.py <portfolio in> <portfolio out|-> <DKEntries.csv> <scores.json> <DKSalaries.csv>

The set of lineups never changes (R29 untouched); only which Entry ID holds which lineup. Per contest it
measures prior mean (higher), and for a contest with two or more entries also mean and max pairwise overlap
(lower), distinct people (higher) and the most-used person's count (lower). An exchange between two Entry IDs
in different contests is taken only when no measure of either contest gets worse and at least one gets better.
Greedy to a fixed point, best total prior gain first. With out "-" it reports and writes nothing.
Writes no prior; reads the gated scores only to compare rows.
"""
import csv
import itertools
import json
import sys
from collections import Counter

src, out, ent_path, sc_path, sal_path = sys.argv[1:6]
sc = json.load(open(sc_path))["by_dk_id"]
contest = {r["Entry ID"]: r["Contest ID"] for r in csv.DictReader(open(ent_path, encoding="utf-8-sig")) if r["Entry ID"]}
d = json.load(open(src))
A = d["assignments_by_entry_id"]
groups = {}
for e in A:
    groups.setdefault(contest[e], []).append(e)


def prior(l):
    return sum(sc.get(x, 0) for x in l)


def measures(entries, assign):
    ls = [assign[e] for e in entries]
    m = {"prior_mean": sum(prior(l) for l in ls) / len(ls)}
    if len(ls) >= 2:
        ov = [len(set(a) & set(b)) for a, b in itertools.combinations(ls, 2)]
        c = Counter(x for l in ls for x in l)
        m.update(mean_overlap=sum(ov) / len(ov), max_overlap=max(ov), distinct=len(c), max_count=max(c.values()))
    return m


HIGHER = {"prior_mean", "distinct"}


def no_worse(b, a):
    worse = better = False
    for k in b:
        if k in HIGHER:
            worse |= a[k] < b[k] - 1e-9
            better |= a[k] > b[k] + 1e-9
        else:
            worse |= a[k] > b[k] + 1e-9
            better |= a[k] < b[k] - 1e-9
    return worse, better


log = []
while True:
    best = None
    for x, y in itertools.combinations(list(A), 2):
        cx, cy = contest[x], contest[y]
        if cx == cy:
            continue
        before = {g: measures(groups[g], A) for g in (cx, cy)}
        trial = dict(A)
        trial[x], trial[y] = A[y], A[x]
        after = {g: measures(groups[g], trial) for g in (cx, cy)}
        flags = [no_worse(before[g], after[g]) for g in (cx, cy)]
        if any(w for w, _ in flags) or not any(b for _, b in flags):
            continue
        gain = sum(after[g]["prior_mean"] - before[g]["prior_mean"] for g in (cx, cy))
        key = (gain, x, y)
        if best is None or key > best[0]:
            best = (key, before, after)
    if best is None:
        break
    (_, x, y), before, after = best
    A[x], A[y] = A[y], A[x]
    log.append(f"EXCHANGE {x} ({contest[x]}) <-> {y} ({contest[y]}): before {before} after {after}")

for g, es in groups.items():
    print(g, len(es), {k: round(v, 3) for k, v in measures(es, A).items()})
print("\n".join(log) or "NO_PARETO_EXCHANGE")
if out != "-" and log:
    by_entry = {row["entry_id"]: row for row in d["lineups"]}
    for row in d["lineups"]:
        r = A[row["entry_id"]]
        row.update(roster=r, prior_points=round(prior(r), 3))
    salmap = {r["ID"]: int(r["Salary"]) for r in csv.DictReader(open(sal_path, encoding="utf-8-sig"))}
    for row in d["lineups"]:
        row["salary"] = sum(salmap[x] for x in row["roster"])
    d.setdefault("construction", {}).setdefault("contest_pareto", []).extend(log)
    json.dump(d, open(out, "x"), indent=1)
    print("wrote", out)
