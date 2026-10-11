"""MIN@NO final QA: adversarial checks and a Pareto FLEX scan on the delivered file. A record, not a tool.

Adversarial: no DraftKings OUT/IR person, no excluded practice-squad ID, no backup QB, 33 distinct rows.
Pareto: a FLEX swap is taken only when it raises the row's frozen prior, keeps the Captain, the row's thesis
(team and position bounds), the policy's structural bounds (1-2 QB; 1-2 WR/TE per rostered QB's team),
salary <= 50,000, both teams, distinctness, never removes a protected person (each starting QB, each DST,
Vele, Lance, Jennings, Felton: the research placements), and leaves no washout proxy worse on the whole
portfolio: max exposure, top-3 exposure sum and mean pairwise overlap no higher, distinct people no fewer,
max pairwise overlap <= 5. Scans to a fixed point. Writes a new file only if a swap is taken.

Usage: pareto_scan.py <salaries> <final_csv> <judgment_v6_csv> <theses_by_entry> <theses_dir> <scores> <exclude_args> <out_csv> <record>
"""
import csv
import json
import os
import sys
from collections import Counter

(sal_path, final_csv, v6_csv, theses_by_entry, theses_dir, scores_path, exclude_path,
 out_csv, record_path) = sys.argv[1:10]

SAL = {}
FLEX_OF = {}
with open(sal_path, newline="", encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        SAL[r["ID"]] = dict(name=r["Name"], team=r["TeamAbbrev"], pos=r["Position"], salary=int(r["Salary"]),
                            rp=r["Roster Position"], status=r["Status"])
        if r["Roster Position"] == "FLEX":
            FLEX_OF[r["Name"]] = r["ID"]
SC = json.load(open(scores_path))["by_dk_id"]
EXCL = set(open(exclude_path).read().split()) - {"--exclude"}
THESES = {}
for fn in os.listdir(theses_dir):
    d = json.load(open(os.path.join(theses_dir, fn)))
    THESES[d["name"]] = d
BACKUPS = {"Carson Wentz", "Max Brosmer", "Spencer Rattler", "Zach Wilson"}
PROTECT = {"Kyler Murray", "Tyler Shough", "Vikings", "Saints", "Devaughn Vele", "Bryce Lance", "Jauan Jennings", "Tai Felton"}


def read(p):
    raw = list(csv.reader(open(p, newline="", encoding="utf-8-sig")))
    rows = {}
    for r in raw[1:]:
        if r and r[0].strip().isdigit() and all(c.strip() for c in r[4:10]):
            rows[r[0].strip()] = [c.strip() for c in r[4:10]]
    return raw, rows


key = lambda ids: (ids[0], frozenset(ids[1:]))
_, v6 = read(v6_csv)
tbe = json.load(open(theses_by_entry))
thesis_of_lineup = {key(ids): tbe[e] for e, ids in v6.items()}
raw, rows = read(final_csv)
THESIS = {e: thesis_of_lineup[key(ids)] for e, ids in rows.items()}
nm = lambda d: SAL[d]["name"]

problems = []
for e, ids in rows.items():
    for d in ids:
        if SAL[d]["status"] in ("OUT", "IR"):
            problems.append(f"{e} {nm(d)} DK {SAL[d]['status']}")
        if d in EXCL:
            problems.append(f"{e} {nm(d)} excluded practice-squad ID")
        if nm(d) in BACKUPS:
            problems.append(f"{e} {nm(d)} backup QB")
if len({key(i) for i in rows.values()}) != len(rows):
    problems.append("duplicate lineups")


def ok(eid, ids):
    if sum(SAL[d]["salary"] for d in ids) > 50000 or len({nm(d) for d in ids}) != 6:
        return False
    if len({SAL[d]["team"] for d in ids}) < 2:
        return False
    t = THESES[THESIS[eid]]
    tc = Counter(SAL[d]["team"] for d in ids)
    pc = Counter(SAL[d]["pos"] for d in ids)
    if any(not b["minimum"] <= tc[b["team"]] <= b["maximum"] for b in t.get("team_bounds", [])):
        return False
    if any(not b["minimum"] <= pc[b["position"]] <= b["maximum"] for b in t.get("position_bounds", [])):
        return False
    qbs = [d for d in ids if SAL[d]["pos"] == "QB"]
    if not 1 <= len(qbs) <= 2:
        return False
    for q in qbs:
        if not 1 <= sum(1 for d in ids if SAL[d]["pos"] in ("WR", "TE") and SAL[d]["team"] == SAL[q]["team"]) <= 2:
            return False
    if pc["DST"] > 1:
        return False
    for d in ids:
        if SAL[d]["pos"] == "DST":
            opp_qb = {"MIN": "Tyler Shough", "NO": "Kyler Murray"}[SAL[d]["team"]]
            if opp_qb in {nm(x) for x in ids} and not any(nm(x) == opp_qb for x in rows[eid]):
                return False  # never create a DST beside the opposing QB
    return True


def measures(rs):
    c = Counter(nm(d) for ids in rs.values() for d in ids)
    top = c.most_common(3)
    sets = [set(nm(d) for d in ids) for ids in rs.values()]
    ov = [len(a & b) for i, a in enumerate(sets) for b in sets[i + 1:]]
    return dict(max_exposure=top[0][1], top3=sum(n for _, n in top), mean_overlap=sum(ov) / len(ov),
                distinct=len(c), max_overlap=max(ov),
                prior=sum(SC.get(d, 0) or 0 for ids in rs.values() for d in ids))


def no_worse(a, b):
    return (b["max_exposure"] <= a["max_exposure"] and b["top3"] <= a["top3"]
            and b["mean_overlap"] <= a["mean_overlap"] + 1e-12 and b["distinct"] >= a["distinct"]
            and b["max_overlap"] <= 5)


pool = [d for d, s in SAL.items() if s["rp"] == "FLEX" and s["status"] == "" and d not in EXCL
        and s["name"] not in BACKUPS]
before = measures(rows)
taken, rejected = [], Counter()
for _ in range(10):
    changed = False
    for eid in list(rows):
        ids = rows[eid]
        best = None
        for out in ids[1:]:
            if nm(out) in PROTECT:
                continue
            for inc in pool:
                if inc in ids or nm(inc) in {nm(x) for x in ids}:
                    continue
                gain = (SC.get(inc, 0) or 0) - (SC.get(out, 0) or 0)
                if gain <= 0.0:
                    continue
                new = [inc if d == out else d for d in ids]
                if not ok(eid, new) or any(key(new) == key(o) for e2, o in rows.items() if e2 != eid):
                    continue
                trial = dict(rows)
                trial[eid] = new
                m = measures(trial)
                if not no_worse(measures(rows), m):
                    rejected[f"{nm(out)}->{nm(inc)}"] += 1
                    continue
                if best is None or gain > best[0]:
                    best = (gain, out, inc, new)
        if best:
            gain, out, inc, new = best
            taken.append(dict(entry_id=eid, thesis=THESIS[eid], out=nm(out), **{"in": nm(inc)}, prior_gain=round(gain, 3)))
            rows[eid] = new
            changed = True
    if not changed:
        break
after = measures(rows)
if taken:
    with open(out_csv, "x", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\r\n")
        w.writerow(raw[0])
        for r in raw[1:]:
            e = r[0].strip() if r else ""
            if e in rows:
                r = list(r)
                r[4:10] = rows[e]
            w.writerow(r)
json.dump(dict(problems=problems, taken=taken, before=before, after=after,
               rejected_top=rejected.most_common(15), wrote=bool(taken)), open(record_path, "x"), indent=2)
print(json.dumps(dict(problems=problems, taken=taken, before=before, after=after, rejected_top=rejected.most_common(8)), indent=1))
