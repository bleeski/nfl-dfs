"""Week 5 afternoon Classic: exchange two whole lineups between Entry IDs (a record, never a tool).

Usage: python contest_swap_record.py <portfolio in> <portfolio out> <entry id A> <entry id B>

The $1 single-entry Daily Dollar Entry ID held the lowest-prior lineup (95.5); the first $0.10 Dime Entry ID
held a 135.7 Goff stack. Exchanging them leaves the set of 25 lineups unchanged (R29 untouched) and puts the
stronger lineup on the higher-fee single entry. Writes no prior.
"""
import json
import sys

src, out, a, b = sys.argv[1:5]
d = json.load(open(src))
A = d["assignments_by_entry_id"]
before = sorted(tuple(sorted(v)) for v in A.values())
A[a], A[b] = A[b], A[a]
assert sorted(tuple(sorted(v)) for v in A.values()) == before
by_entry = {row["entry_id"]: row for row in d["lineups"]}
ra, rb = by_entry[a], by_entry[b]
for k in ("roster", "salary", "prior_points", "bringback"):
    ra[k], rb[k] = rb[k], ra[k]
assert all(sorted(row["roster"]) == sorted(A[row["entry_id"]]) for row in d["lineups"])
d.setdefault("construction", {}).setdefault("contest_swaps", []).append(
    f"EXCHANGE {a} <-> {b}: whole lineups, set unchanged")
json.dump(d, open(out, "x"), indent=1)
print(f"EXCHANGE {a} <-> {b}: lineup set unchanged")
