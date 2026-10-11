"""Week 5 Classic: place research-backed role-change players by construction (a record, never a tool).

Usage: python manual_add_record.py <portfolio in> <portfolio out> <DKSalaries.csv> <scores.json> "Name:target" ...

Writes no prior. For each named player, in order, swaps him into rows until he reaches the target. It
ranks every (row, outgoing player) pair across the whole portfolio by the outgoing player's prior, lowest
first, one swap per row, so it never pulls a row's best player when a weaker one elsewhere can go. The
outgoing player is an RB, WR or TE whose removal leaves a legal DraftKings shape, and is never the row's
QB, a QB-team player, the row's only bring-back, the DST, or a player placed earlier in this run. Refuses
a row whose DST faces the added player's team, a swap over the cap, a duplicate roster (R29), and any
overlap above 5 with another row. Ties go to rows whose QB is in the added player's game.

Two earlier versions were wrong and are recorded in changelog.md (2026-10-11, Week 5 Classic): a
row-by-row pass pulled D'Andre Swift and Ja'Marr Chase out of rows, and a pass without the placed set let
each later placement displace the one before it.
"""
import csv
import json
import sys
from collections import Counter

src, out, sal_path, sc_path = sys.argv[1:5]
targets = [(a.rsplit(":", 1)[0], int(a.rsplit(":", 1)[1])) for a in sys.argv[5:]]
sal = {r["ID"]: r for r in csv.DictReader(open(sal_path, encoding="utf-8-sig"))}
sc = json.load(open(sc_path))["by_dk_id"]
d = json.load(open(src))
A = d["assignments_by_entry_id"]


def gm(x):
    return sal[x]["Game Info"].split(" ")[0]


def team(x):
    return sal[x]["TeamAbbrev"]


def pos(x):
    return sal[x]["Position"]


def legal_shape(l):
    """The JSON's roster order is arbitrary (the writer assigns slots), so check the DraftKings shape."""
    c = Counter(pos(x) for x in l)
    return (len(l) == 9 and c["QB"] == 1 and c["DST"] == 1 and c["RB"] >= 2 and c["WR"] >= 3
            and c["TE"] >= 1 and c["RB"] + c["WR"] + c["TE"] == 7 and len(set(l)) == 9)


log = []
placed = set()
for add_name, target in targets:
    add = [k for k, r in sal.items() if r["Name"] == add_name]
    assert len(add) == 1, add_name
    add = add[0]
    game = gm(add)
    expo = Counter(x for l in A.values() for x in l)

    def qb(l):
        return [x for x in l if pos(x) == "QB"][0]

    # Whole-portfolio greedy: every legal (row, outgoing) pair, lowest outgoing prior first, one per row.
    # The FLEX slot (roster index 7) may give up any RB, WR or TE.
    pairs = []
    for e, l in A.items():
        if add in l:
            continue
        q = qb(l)
        qt, qg = team(q), gm(q)
        dst = [x for x in l if pos(x) == "DST"][0]
        if gm(dst) == game and team(dst) != team(add):
            continue
        bring = [y for y in l if gm(y) == qg and team(y) != qt and pos(y) != "DST"]
        for i, x in enumerate(l):
            slot_ok = pos(x) in ("RB", "WR", "TE") and legal_shape(l[:i] + [add] + l[i + 1:])
            if not slot_ok or x in placed or team(x) == qt or (x in bring and len(bring) == 1):
                continue
            pairs.append((sc.get(x, 0), gm(q) != game, e, i))
    pairs.sort()
    for _, _, e, i in pairs:
        if sum(1 for l in A.values() if add in l) >= target:
            break
        l = A[e]
        if add in l:
            continue
        c = l[i]
        q = qb(l)
        used = sum(int(sal[x]["Salary"]) for x in l)
        if used - int(sal[c]["Salary"]) + int(sal[add]["Salary"]) > 50000:
            continue
        trial = l[:i] + [add] + l[i + 1:]
        others = [v for k, v in A.items() if k != e]
        if tuple(sorted(trial)) in {tuple(sorted(v)) for v in others}:
            continue
        if max(len(set(trial) & set(v)) for v in others) > 5:
            continue
        A[e] = trial
        log.append(
            f"MANUAL_ADD {e}: {sal[c]['Name']} ({sal[c]['Salary']}, prior {sc.get(c, 0):.2f}) -> "
            f"{add_name} ({sal[add]['Salary']}, prior {sc.get(add, 0):.2f}), QB {sal[q]['Name']}"
        )
    placed.add(add)
    log.append(f"EXPOSURE {add_name}: {sum(1 for l in A.values() if add in l)} of target {target}")

eids = list(A.keys())
new = []
for n, e in enumerate(eids):
    old = d["lineups"][n]
    r = A[e]
    new.append(dict(old, roster=r, salary=sum(int(sal[x]["Salary"]) for x in r),
                    prior_points=round(sum(sc.get(x, 0) for x in r), 3)))
d["lineups"] = new
d.setdefault("construction", {}).setdefault("manual_adds", []).extend(log)
json.dump(d, open(out, "x"), indent=1)
print("\n".join(log))
