"""Week 5 afternoon Classic, adversarial pass iteration 2: named swaps (a record, never a tool).

Usage: python split_backfield_record.py <portfolio in> <portfolio out> <DKSalaries.csv> <scores.json>

Writes no prior. Each swap is (entry, outgoing name, incoming name, reason). Every swap must keep a legal
DraftKings shape, salary at or under 50,000, the row distinct from every other (R29), overlap at most 5 with
every other row, no person above 10 of 25, and no DST facing the incoming player's team; any failure raises
and nothing is written. Sources: LAC backfield three-way split in Week 4 (RotoBaller), four LAC offensive
line starters out (Yahoo DEN@LAC live blog, 2:10 PM ET), ARI backfield split Love/Allgeier (Arizona Sports),
three LAC defensive backs inactive (Chargers.com, 11:43 AM).
"""
import csv
import json
import sys
from collections import Counter

src, out, sal_path, sc_path = sys.argv[1:5]
sal = {r["ID"]: r for r in csv.DictReader(open(sal_path, encoding="utf-8-sig"))}
byname = {r["Name"].strip(): k for k, r in sal.items()}
sc = json.load(open(sc_path))["by_dk_id"]
d = json.load(open(src))
A = d["assignments_by_entry_id"]

SWAPS = [
    ("5292356750", "Omarion Hampton", "RJ Harvey", "two LAC backs in a split behind a gutted line"),
    ("5292356750", "Bam Knight", "Jeremiyah Love", "bring-back stays ARI; Knight has no sourced role"),
    ("5292379456", "Omarion Hampton", "Jaylen Waddle", "two LAC backs; DEN WR against three missing LAC DBs"),
    ("5292379451", "Bam Knight", "RJ Harvey", "Love plus Knight share one backfield"),
    ("5292379448", "Tyler Allgeier", "J.K. Dobbins", "Love plus Allgeier share one backfield"),
    ("5292379457", "Tyler Allgeier", "RJ Harvey", "Love plus Allgeier share one backfield"),
]


def pos(x):
    return sal[x]["Position"]


def game(x):
    return sal[x]["Game Info"].split(" ")[0]


def legal(l):
    c = Counter(pos(x) for x in l)
    return (len(set(l)) == 9 and c["QB"] == 1 and c["DST"] == 1 and c["RB"] >= 2 and c["WR"] >= 3
            and c["TE"] >= 1 and c["RB"] + c["WR"] + c["TE"] == 7)


log = []
for e, o, i, why in SWAPS:
    oid, iid = byname[o], byname[i]
    l = A[e]
    assert oid in l and iid not in l, (e, o, i)
    trial = [iid if x == oid else x for x in l]
    assert legal(trial), (e, "shape")
    s = sum(int(sal[x]["Salary"]) for x in trial)
    assert s <= 50000, (e, s)
    dst = [x for x in trial if pos(x) == "DST"][0]
    assert not (game(dst) == game(iid) and sal[dst]["TeamAbbrev"] != sal[iid]["TeamAbbrev"]), (e, "dst faces")
    others = [v for k, v in A.items() if k != e]
    assert tuple(sorted(trial)) not in {tuple(sorted(v)) for v in others}, (e, "duplicate")
    assert max(len(set(trial) & set(v)) for v in others) <= 5, (e, "overlap")
    A[e] = trial
    expo = Counter(x for v in A.values() for x in v)
    assert expo[iid] <= 10, (i, expo[iid])
    log.append(f"SWAP {e}: {o} (prior {sc.get(oid, 0):.2f}) -> {i} (prior {sc.get(iid, 0):.2f}), salary {s}; {why}")

for row in d["lineups"]:
    r = A[row["entry_id"]]
    row.update(roster=r, salary=sum(int(sal[x]["Salary"]) for x in r), prior_points=round(sum(sc.get(x, 0) for x in r), 3))
d.setdefault("construction", {}).setdefault("adversarial_swaps", []).extend(log)
json.dump(d, open(out, "x"), indent=1)
print("\n".join(log))
expo = Counter(sal[x]["Name"] for v in A.values() for x in v)
print({n: expo[n] for n in ("RJ Harvey", "J.K. Dobbins", "Jeremiyah Love", "Tyler Allgeier", "Omarion Hampton",
                           "Bam Knight", "Jaylen Waddle", "Keaton Mitchell")})
