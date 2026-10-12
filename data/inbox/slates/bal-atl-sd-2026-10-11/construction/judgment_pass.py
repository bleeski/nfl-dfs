"""BAL@ATL Showdown judgment pass (2026-10-11 SNF). A record of the swaps, not a tool.

Reads the engine's review file and writes a new file; never edits the input.
Every swap keeps: the Captain, the row's thesis (team and position bounds from the
thesis files), the policy's structural bounds (1 to 2 QBs; 1 to 2 WR/TE of each
rostered QB's team), salary <= 50,000, both teams present, distinct rows (R29), and
no person above 24 of 32 rows (75%). No number is written for anyone; research
(nflverse 2026 weekly stats captured by the run, official inactives) chose who goes
in, and the frozen prior only orders ties.

Steps, in order:
  A. Kyle Pitts down to about 8 rows: prior 10.3 FLEX points on last season's role,
     2026 usage 2.2 targets and 2.9 PPR a game over 4 games.
  B. DST coherence: no DST beside the opposing starting quarterback.
  C. Ceiling: a WR/TE Captain gets his own starting quarterback where one swap fits.
  D. Mark Andrews (6.0 targets, 9.7 PPR a game in 2026) for a FLEX kicker in BAL-script rows.

Usage: judgment_pass.py <salaries> <review_in> <scores> <qa_json> <theses_dir> <out_csv> <record_json>
"""
import csv
import json
import os
import sys
from collections import Counter

sal_path, review_in, scores_path, qa_path, theses_dir, out_csv, record_path = sys.argv[1:8]

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
DST_OF = {"BAL": "Ravens", "ATL": "Falcons"}
CAP = 50000
PERSON_MAX = 24
PITTS_TARGET = 8

def fid(name):
    return FLEX_OF[name]

with open(review_in, newline="", encoding="utf-8-sig") as f:
    raw = list(csv.reader(f))
header = raw[0]
rows = {}
order = []
for i, r in enumerate(raw[1:], start=1):
    if r and r[0].strip().isdigit() and all(c.strip() for c in r[4:10]):
        rows[r[0].strip()] = [c.strip() for c in r[4:10]]
        order.append((i, r[0].strip()))

def name(d):
    return SAL[d]["name"]

def salary(ids):
    return sum(SAL[d]["salary"] for d in ids)

def counts():
    c = Counter()
    for ids in rows.values():
        for d in ids:
            c[name(d)] += 1
    return c

def thesis_ok(eid, ids):
    t = THESES[THESIS_OF[eid]]
    tc = Counter(SAL[d]["team"] for d in ids)
    pc = Counter(SAL[d]["pos"] for d in ids)
    for b in t.get("team_bounds", []):
        if not b["minimum"] <= tc[b["team"]] <= b["maximum"]:
            return False
    for b in t.get("position_bounds", []):
        if not b["minimum"] <= pc[b["position"]] <= b["maximum"]:
            return False
    return True

def legal(eid, ids):
    if salary(ids) > CAP:
        return False
    if len({name(d) for d in ids}) != 6:
        return False
    if len({SAL[d]["team"] for d in ids}) < 2:
        return False
    if not thesis_ok(eid, ids):
        return False
    qbs = [d for d in ids if SAL[d]["pos"] == "QB"]
    if not 1 <= len(qbs) <= 2:
        return False
    for q in qbs:
        pc = sum(1 for d in ids if SAL[d]["pos"] in ("WR", "TE") and SAL[d]["team"] == SAL[q]["team"])
        if not 1 <= pc <= 2:
            return False
    if sum(1 for d in ids if SAL[d]["pos"] == "K") > 1 or sum(1 for d in ids if SAL[d]["pos"] == "DST") > 1:
        return False
    key = (ids[0], frozenset(ids[1:]))
    for other, oids in rows.items():
        if other != eid and (oids[0], frozenset(oids[1:])) == key:
            return False
    return True

log = []

def try_swap(eid, out_id, in_name, step, why):
    ids = rows[eid]
    if out_id not in ids[1:] or in_name not in FLEX_OF:
        return False
    in_id = fid(in_name)
    if in_name in {name(d) for d in ids}:
        return False
    if counts()[in_name] >= PERSON_MAX:
        return False
    new = [in_id if d == out_id else d for d in ids]
    if not legal(eid, new):
        return False
    log.append(dict(step=step, entry_id=eid, thesis=THESIS_OF[eid], out=name(out_id), out_id=out_id,
                    **{"in": in_name}, in_id=in_id, salary_before=salary(ids), salary_after=salary(new), why=why))
    rows[eid] = new
    return True

def snapshot():
    c = counts()
    cap = Counter(name(ids[0]) for ids in rows.values())
    def rp(ids):
        return 1.5 * (SCORES.get(ids[0], 0.0) or 0.0) / 1.5 + sum(SCORES.get(d, 0.0) or 0.0 for d in ids[1:])
    prior = sum(rp(ids) for ids in rows.values())
    lows = min(rp(ids) for ids in rows.values())
    sets = [set(name(d) for d in ids) for ids in rows.values()]
    ov = [len(a & b) for i, a in enumerate(sets) for b in sets[i + 1:]]
    top3 = sum(v for _, v in c.most_common(3))
    return dict(total_prior=round(prior, 2), lowest_row_prior=round(lows, 2),
                max_person=c.most_common(1)[0], top3=top3, people=dict(c.most_common()), distinct_people=len(c),
                captains=dict(cap.most_common()), mean_pair_overlap=round(sum(ov) / len(ov), 4),
                max_pair_overlap=max(ov), pairs_sharing_5=sum(1 for x in ov if x >= 5),
                min_salary=min(salary(i) for i in rows.values()), max_salary=max(salary(i) for i in rows.values()),
                distinct_lineups=len({(i[0], frozenset(i[1:])) for i in rows.values()}))

before = snapshot()

ATL_SCRIPTS = ("ATL_WINS_BIG", "ATL_WINS_CLOSE_HIGH", "ATL_WINS_CLOSE_LOW")
BAL_SCRIPTS = ("BAL_WINS_BIG", "BAL_WINS_CLOSE_HIGH", "BAL_WINS_CLOSE_LOW")

# A. Pitts down. ATL-script rows keep an ATL pass catcher first; BAL-script rows take a BAL one.
PITTS = fid("Kyle Pitts Sr.")
for _, eid in order:
    if counts()["Kyle Pitts Sr."] <= PITTS_TARGET:
        break
    if PITTS not in rows[eid][1:]:
        continue
    th = THESIS_OF[eid]
    if th in BAL_SCRIPTS:
        cands = ["Mark Andrews", "Rashod Bateman", "Jahan Dotson", "Austin Hooper", "Matt Hibner"]
    else:
        cands = ["Jahan Dotson", "Mark Andrews", "Rashod Bateman", "Austin Hooper", "Matt Hibner"]
    why = "Pitts 2.2 targets, 2.9 PPR a game in 2026 (prior prices last season); in 19 of 32 rows"
    if not any(try_swap(eid, PITTS, c, "A", why) for c in cands):
        log.append(dict(step="A", entry_id=eid, kept="Kyle Pitts Sr.", why="no single swap keeps the row legal"))

# B. DST coherence.
for _, eid in order:
    for dst in [d for d in rows[eid] if SAL[d]["pos"] == "DST"]:
        team = SAL[dst]["team"]
        opp_qb_name = STARTING_QB[OPP[team]]
        opp_qb = [d for d in rows[eid][1:] if name(d) == opp_qb_name]
        if not opp_qb:
            if rows[eid][0] != dst and any(name(d) == opp_qb_name for d in rows[eid][:1]):
                log.append(dict(step="B", entry_id=eid, unresolved=f"{name(dst)} DST with {opp_qb_name} Captain"))
            continue
        why = f"{name(dst)} DST beside opposing QB {opp_qb_name}"
        if rows[eid][0] != dst:
            if try_swap(eid, dst, DST_OF[OPP[team]], "B", why + "; the other DST matches the row"):
                continue
        if try_swap(eid, opp_qb[0], STARTING_QB[team], "B", why + "; the DST's own QB in"):
            continue
        log.append(dict(step="B", entry_id=eid, unresolved=why))

# C. WR/TE Captain gets his own QB.
for _, eid in order:
    ids = rows[eid]
    c = SAL[ids[0]]
    if c["pos"] not in ("WR", "TE"):
        continue
    qb = STARTING_QB[c["team"]]
    if qb in {name(d) for d in ids}:
        continue
    outs = sorted(ids[1:], key=lambda d: SCORES.get(d, 0.0) or 0.0)
    if not any(try_swap(eid, o, qb, "C", f"{c['name']} Captain without {qb}") for o in outs):
        log.append(dict(step="C", entry_id=eid, unresolved=f"{c['name']} Captain without {qb}: no single swap fits"))

# D. Andrews for a FLEX kicker in BAL-script and shootout rows (Andrews 6.0 targets a game in 2026).
ANDREWS_TARGET = 8
for _, eid in order:
    if counts()["Mark Andrews"] >= ANDREWS_TARGET:
        break
    if THESIS_OF[eid] in ("BAL_WINS_BIG", "BAL_WINS_CLOSE_HIGH", "OFFENSIVE_SHOOTOUT"):
        for k in ("Tyler Loop", "Nick Folk"):
            if fid(k) in rows[eid][1:]:
                if try_swap(eid, fid(k), "Mark Andrews", "D", "Andrews 6.0 targets, 9.7 PPR a game in 2026; FLEX kicker out"):
                    break

after = snapshot()

with open(out_csv, "x", newline="", encoding="utf-8") as f:
    w = csv.writer(f, lineterminator="\r\n")
    for i, r in enumerate(raw):
        eid = r[0].strip() if r else ""
        if i > 0 and eid in rows:
            r = list(r)
            r[4:10] = rows[eid]
        w.writerow(r)

with open(record_path, "x", encoding="utf-8") as f:
    json.dump(dict(input=review_in, output=out_csv, swaps=log, before=before, after=after,
                   does_not_establish=["EV", "ROI", "WIN_PROBABILITY", "UPLOAD_CLEARANCE"]), f, indent=2)

for s in log:
    print(s.get("step"), s.get("entry_id"), s.get("thesis", ""), s.get("out", ""), "->", s.get("in", s.get("unresolved", s.get("kept", ""))))
for k in ("total_prior", "lowest_row_prior", "max_person", "top3", "distinct_people", "mean_pair_overlap", "max_pair_overlap",
          "pairs_sharing_5", "min_salary", "max_salary", "distinct_lineups", "captains"):
    print(k, before[k], "->", after[k])
print("people after", after["people"])
