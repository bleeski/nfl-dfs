"""Week 5 Classic final adversarial pass (a record, never a tool).

Usage: python final_qa_record.py <portfolio in> <portfolio out> <DKSalaries.csv> <scores.json> <DKEntries.csv>

1. Same-team RB pair: row 5290502374 (Daniel Jones) rostered TreVeyon Henderson with Rhamondre Stevenson. Try
   every RB swap for either one; take the highest-prior one that leaves the row legal (shape, cap, distinct,
   overlap 5, exposure 10, no DST conflict) and leaves no portfolio washout measure worse (max exposure, top-3
   union, mean pairwise overlap, distinct people) and the row's prior no lower.
2. Contest assignment: the two $1 single-entry Daily Dollar contests held the two lowest-prior lineups. Exchange
   whole lineups between Entry IDs (the set of 32 lineups is unchanged, so no portfolio measure moves): each $1
   single-entry Entry ID takes the highest-prior lineup from the 20-entry Dime contest, provided the Dime
   contest's own max exposure and mean overlap get no worse.
Writes no prior.
"""
import csv
import itertools
import json
import sys
from collections import Counter

src, out, sal_path, sc_path, ent_path = sys.argv[1:6]
S = {r["ID"]: r for r in csv.DictReader(open(sal_path, encoding="utf-8-sig"))}
sc = json.load(open(sc_path))["by_dk_id"]
contest = {r[0]: r[1].strip() for r in csv.reader(open(ent_path, encoding="utf-8-sig")) if r and r[0].isdigit()}
fee = {r[0]: r[3] for r in csv.reader(open(ent_path, encoding="utf-8-sig")) if r and r[0].isdigit()}
d = json.load(open(src))
A = d["assignments_by_entry_id"]
log = []


def g(x): return S[x]["Game Info"].split(" ")[0]
def t(x): return S[x]["TeamAbbrev"]
def p(x): return S[x]["Position"]
def prior(l): return sum(sc.get(x, 0) for x in l)


def measures(rows):
    rows = list(rows)
    use = Counter(x for l in rows for x in l)
    top3 = [x for x, _ in use.most_common(3)]
    pairs = list(itertools.combinations(rows, 2))
    return {
        "max_exposure": max(use.values()),
        "top3_union": sum(1 for l in rows if set(l) & set(top3)),
        "mean_overlap": round(sum(len(set(a) & set(b)) for a, b in pairs) / len(pairs), 6),
        "distinct": len(use),
    }


def no_worse(a, b):
    return (b["max_exposure"] <= a["max_exposure"] and b["top3_union"] <= a["top3_union"]
            and b["mean_overlap"] <= a["mean_overlap"] and b["distinct"] >= a["distinct"])


def legal(l, e):
    c = Counter(p(x) for x in l)
    if not (len(set(l)) == 9 and c["QB"] == 1 and c["DST"] == 1 and c["RB"] >= 2 and c["WR"] >= 3 and c["TE"] >= 1
            and c["RB"] + c["WR"] + c["TE"] == 7):
        return False
    if sum(int(S[x]["Salary"]) for x in l) > 50000:
        return False
    dst = [x for x in l if p(x) == "DST"][0]
    if any(x != dst and g(x) == g(dst) and t(x) != t(dst) for x in l):
        return False
    others = [v for k, v in A.items() if k != e]
    if tuple(sorted(l)) in {tuple(sorted(v)) for v in others}:
        return False
    if max(len(set(l) & set(v)) for v in others) > 5:
        return False
    use = Counter(x for v in others for x in v) + Counter(l)
    return max(use.values()) <= 10


# 1. same-team RB pair
e = "5290502374"
l = A[e]
before = measures(A.values())
best = None
for out_id in [x for x in l if p(x) == "RB" and sum(1 for y in l if p(y) == "RB" and t(y) == t(x)) > 1]:
    for cand in [k for k in sc if p(k) == "RB" and k not in l and t(k) != t(out_id)]:
        trial = [cand if x == out_id else x for x in l]
        if not legal(trial, e) or prior(trial) < prior(l):
            continue
        after = measures([trial if k == e else v for k, v in A.items()])
        if not no_worse(before, after):
            continue
        if best is None or prior(trial) > best[0]:
            best = (prior(trial), out_id, cand, trial, after)
if best:
    A[e] = best[3]
    log.append(f"RB_PAIR {e}: {S[best[1]]['Name']} -> {S[best[2]]['Name']}, row prior {prior(l):.2f} -> {best[0]:.2f}, "
               f"measures {before} -> {best[4]}")
else:
    log.append(f"RB_PAIR {e}: no swap keeps the row's prior and every washout measure; left as is")

# 2. contest assignment
dime = [k for k in A if contest[k].startswith("NFL $7.5K Dime Package")]
targets = sorted([k for k in A if fee[k] == "$1"], key=lambda k: prior(A[k]))
for tgt in targets:
    dm_before = measures(A[k] for k in dime)
    for src_e in sorted(dime, key=lambda k: -prior(A[k])):
        if prior(A[src_e]) <= prior(A[tgt]):
            break
        trial = dict(A)
        trial[tgt], trial[src_e] = A[src_e], A[tgt]
        dm_after = measures(trial[k] for k in dime)
        if no_worse(dm_before, dm_after):
            log.append(f"CONTEST_SWAP {tgt} ({contest[tgt]}) <-> {src_e} (Dime): prior {prior(A[tgt]):.1f} -> "
                       f"{prior(A[src_e]):.1f}; Dime measures {dm_before} -> {dm_after}")
            A[tgt], A[src_e] = A[src_e], A[tgt]
            break
    else:
        log.append(f"CONTEST_SWAP {tgt}: no Dime lineup moves without worsening the Dime contest's measures")

eids = list(A.keys())
d["lineups"] = [dict(old, roster=A[k], salary=sum(int(S[x]["Salary"]) for x in A[k]), prior_points=round(prior(A[k]), 3))
                for old, k in zip(d["lineups"], eids)]
d.setdefault("construction", {}).setdefault("final_qa", []).extend(log)
json.dump(d, open(out, "x"), indent=1)
print("\n".join(log))
print("portfolio", measures(A.values()), "prior_sum", round(sum(prior(v) for v in A.values()), 3))
