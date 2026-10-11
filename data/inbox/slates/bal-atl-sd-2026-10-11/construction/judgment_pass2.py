"""BAL@ATL judgment pass, part 2 (2026-10-11 SNF). A record of the swaps, not a tool.

Fixes the rows part 1 left with a DST beside the opposing starting QB, using the best
legal one- or two-FLEX change (Captain untouched, thesis and structural bounds held,
R29, no person above 24 of 32, max overlap 5). Ranked by the row's prior; Kyle Pitts
and kickers are never brought in here (Pitts's prior prices last season's role).

Usage: judgment_pass2.py <judgment_pass.py dir> <salaries> <review_in> <scores> <qa_json> <theses_dir> <out_csv> <record_json>
"""
import csv
import itertools
import json
import os
import sys
from collections import Counter

here, sal_path, review_in, scores_path, qa_path, theses_dir, out_csv, record_path = sys.argv[1:9]

SAL = {}
FLEX_OF = {}
with open(sal_path, newline="", encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        SAL[r["ID"]] = dict(name=r["Name"], team=r["TeamAbbrev"], pos=r["Position"],
                            salary=int(r["Salary"]), rp=r["Roster Position"], status=r["Status"])
        if r["Roster Position"] == "FLEX":
            FLEX_OF[r["Name"]] = r["ID"]
SCORES = json.load(open(scores_path))["by_dk_id"]
QA = json.load(open(qa_path))
THESIS_OF = {e: v["thesis"] for e, v in QA["theses"]["entries"].items()}
THESES = {}
for fn in os.listdir(theses_dir):
    d = json.load(open(os.path.join(theses_dir, fn)))
    THESES[d["name"]] = d
STARTING_QB = {"BAL": "Tyler Huntley", "ATL": "Michael Penix Jr."}
OPP = {"BAL": "ATL", "ATL": "BAL"}
CAP, PERSON_MAX, MAX_OVERLAP = 50000, 24, 5

with open(review_in, newline="", encoding="utf-8-sig") as f:
    raw = list(csv.reader(f))
rows, order = {}, []
for i, r in enumerate(raw[1:], start=1):
    if r and r[0].strip().isdigit() and all(c.strip() for c in r[4:10]):
        rows[r[0].strip()] = [c.strip() for c in r[4:10]]
        order.append(r[0].strip())

name = lambda d: SAL[d]["name"]
salary = lambda ids: sum(SAL[d]["salary"] for d in ids)
score = lambda ids: sum(SCORES.get(d, 0.0) or 0.0 for d in ids)

def counts(excl=None):
    c = Counter()
    for e, ids in rows.items():
        if e == excl:
            continue
        for d in ids:
            c[name(d)] += 1
    return c

def conflict(ids):
    names = {name(d) for d in ids}
    for d in ids:
        if SAL[d]["pos"] == "DST" and STARTING_QB[OPP[SAL[d]["team"]]] in names:
            return True
    return False

def legal(eid, ids):
    if salary(ids) > CAP or len({name(d) for d in ids}) != 6 or len({SAL[d]["team"] for d in ids}) < 2:
        return False
    t = THESES[THESIS_OF[eid]]
    tc = Counter(SAL[d]["team"] for d in ids)
    pc = Counter(SAL[d]["pos"] for d in ids)
    for b in t.get("team_bounds", []):
        if not b["minimum"] <= tc[b["team"]] <= b["maximum"]:
            return False
    for b in t.get("position_bounds", []):
        if not b["minimum"] <= pc[b["position"]] <= b["maximum"]:
            return False
    qbs = [d for d in ids if SAL[d]["pos"] == "QB"]
    if not 1 <= len(qbs) <= 2:
        return False
    for q in qbs:
        n = sum(1 for d in ids if SAL[d]["pos"] in ("WR", "TE") and SAL[d]["team"] == SAL[q]["team"])
        if not 1 <= n <= 2:
            return False
    if pc["K"] > 1 or pc["DST"] > 1:
        return False
    if conflict(ids):
        return False
    me = {name(d) for d in ids}
    for other, oids in rows.items():
        if other == eid:
            continue
        if (oids[0], frozenset(oids[1:])) == (ids[0], frozenset(ids[1:])):
            return False
        if len(me & {name(d) for d in oids}) > MAX_OVERLAP:
            return False
    c = counts(excl=eid)
    if any(c[n] + 1 > PERSON_MAX for n in me):
        return False
    return True

POOL = sorted({d for ids in rows.values() for d in ids[1:]} |
              {FLEX_OF[n] for n in ("Mark Andrews", "Rashod Bateman", "Jahan Dotson", "Austin Hooper", "Matt Hibner",
                                    "Chris Moore", "Devontez Walker", "Justice Hill", "Brian Robinson Jr.", "Ravens", "Falcons",
                                    "Tyler Huntley", "Michael Penix Jr.")})
BANNED_IN = {FLEX_OF["Kyle Pitts Sr."], FLEX_OF["Tyler Loop"], FLEX_OF["Nick Folk"]}

log = []
for eid in order:
    ids = rows[eid]
    if not conflict(ids):
        continue
    best = None
    flex = ids[1:]
    for k in (1, 2):
        for outs in itertools.combinations(range(5), k):
            for ins in itertools.product(POOL, repeat=k):
                if any(d in BANNED_IN for d in ins) or len(set(ins)) < k:
                    continue
                new_flex = list(flex)
                for o, d in zip(outs, ins):
                    new_flex[o] = d
                new = [ids[0]] + new_flex
                if legal(eid, new):
                    s = score(new)
                    if best is None or s > best[0]:
                        best = (s, new)
        if best:
            break
    if best:
        out_n = [name(d) for d in ids[1:] if d not in best[1]]
        in_n = [name(d) for d in best[1][1:] if d not in ids]
        log.append(dict(entry_id=eid, thesis=THESIS_OF[eid], out=out_n, **{"in": in_n},
                        prior_before=round(score(ids), 2), prior_after=round(best[0], 2),
                        salary_before=salary(ids), salary_after=salary(best[1]),
                        why="DST beside the opposing starting QB; best legal one- or two-FLEX change"))
        rows[eid] = best[1]
    else:
        log.append(dict(entry_id=eid, thesis=THESIS_OF[eid], unresolved="no legal one- or two-FLEX change"))

with open(out_csv, "x", newline="", encoding="utf-8") as f:
    w = csv.writer(f, lineterminator="\r\n")
    for i, r in enumerate(raw):
        eid = r[0].strip() if r else ""
        if i > 0 and eid in rows:
            r = list(r)
            r[4:10] = rows[eid]
        w.writerow(r)
with open(record_path, "x", encoding="utf-8") as f:
    json.dump(dict(input=review_in, output=out_csv, swaps=log,
                   does_not_establish=["EV", "ROI", "WIN_PROBABILITY", "UPLOAD_CLEARANCE"]), f, indent=2)
for s in log:
    print(json.dumps(s))
