"""MIN@NO Showdown judgment pass (2026-10-11). A record of the swaps, not a tool.

Reads the engine's review file and writes a new file; never edits the input.
Every swap keeps: the Captain, the row's thesis (team and position bounds from the
thesis files), salary <= 50,000, both teams present, distinct rows (R29), and no
person above 25 of 33 rows. No number is written for anyone; research (official
inactives, nflverse 2026 snap and target data) chose who goes in, and the frozen
prior only orders ties.

Steps, in order:
  A. Cedric Tillman (elevated for special teams) -> Bryce Lance (NO WR3, 85% snaps).
  B. DST coherence: no DST beside the opposing starting quarterback.
  C. Ceiling: a WR/TE Captain gets his own starting quarterback where one swap fits.
  D. Value adds from the inactive list: Vele for Kamara in NO-script rows; Jennings
     for the FLEX kicker in MIN-script rows.

Usage: judgment_pass.py <salaries> <review_in> <scores> <audit> <theses_dir> <out_csv> <record_json>
"""
import csv
import json
import os
import sys
from collections import Counter

sal_path, review_in, scores_path, audit_path, theses_dir, out_csv, record_path = sys.argv[1:8]

SAL = {}
FLEX_OF = {}
with open(sal_path, newline="", encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        SAL[r["ID"]] = dict(name=r["Name"], team=r["TeamAbbrev"], pos=r["Position"],
                            salary=int(r["Salary"]), rp=r["Roster Position"], status=r["Status"])
        if r["Roster Position"] == "FLEX":
            FLEX_OF[r["Name"]] = r["ID"]

SCORES = json.load(open(scores_path))["by_dk_id"]
AUDIT = json.load(open(audit_path))
THESIS_OF = {e: v["thesis"] for e, v in AUDIT["theses"]["entries"].items()}
THESES = {}
for fn in os.listdir(theses_dir):
    d = json.load(open(os.path.join(theses_dir, fn)))
    THESES[d["name"]] = d

STARTING_QB = {"MIN": "Kyler Murray", "NO": "Tyler Shough"}
OPP = {"MIN": "NO", "NO": "MIN"}
CAP = 50000
PERSON_MAX = 25

def fid(name):
    return FLEX_OF[name]

# Who may come in, by team, in preference order (research judgment, not a number).
INCOMING = {
    "NO": ["Devaughn Vele", "Juwan Johnson", "Bryce Lance", "Noah Fant", "Chris Olave"],
    "MIN": ["Jauan Jennings", "Tai Felton", "T.J. Hockenson", "Aaron Jones Sr.", "Justin Jefferson"],
}

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
    # The policy's structural bounds (portfolio_policy.normalized.json): 1 to 2 quarterbacks, and
    # 1 to 2 WR/TE of each rostered quarterback's team.
    qbs = [d for d in ids if SAL[d]["pos"] == "QB"]
    if not 1 <= len(qbs) <= 2:
        return False
    for q in qbs:
        pc = sum(1 for d in ids if SAL[d]["pos"] in ("WR", "TE") and SAL[d]["team"] == SAL[q]["team"])
        if not 1 <= pc <= 2:
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
    prior = sum(SCORES.get(d, 0.0) or 0.0 for ids in rows.values() for d in ids)
    lows = min(sum(SCORES.get(d, 0.0) or 0.0 for d in ids) for ids in rows.values())
    sets = [set(name(d) for d in ids) for ids in rows.values()]
    ov = [len(a & b) for i, a in enumerate(sets) for b in sets[i + 1:]]
    return dict(total_prior=round(prior, 2), lowest_row_prior=round(lows, 2),
                max_person=c.most_common(1)[0], people=dict(c.most_common()), distinct_people=len(c),
                captains=dict(cap.most_common()), mean_pair_overlap=round(sum(ov) / len(ov), 4),
                max_pair_overlap=max(ov), pairs_sharing_5=sum(1 for x in ov if x >= 5),
                min_salary=min(salary(i) for i in rows.values()), max_salary=max(salary(i) for i in rows.values()))

before = snapshot()

# A. Tillman -> Lance.
for _, eid in order:
    if fid("Cedric Tillman") in rows[eid]:
        why = "Tillman elevated for special teams; Lance is the NO WR3 (85% snaps week 4)"
        if try_swap(eid, fid("Cedric Tillman"), "Bryce Lance", "A", why):
            continue
        # Pair it with a cheaper same-team swap that frees the salary (FLEX kicker or TE first).
        done = False
        saved = list(rows[eid])
        for out_name, in_name in (("Will Reichard", "Tai Felton"), ("Daniel Carlson", "Noah Fant"),
                                  ("T.J. Hockenson", "Tai Felton"), ("Juwan Johnson", "Noah Fant"),
                                  ("Will Reichard", "Jauan Jennings"), ("Aaron Jones Sr.", "Jauan Jennings")):
            if out_name not in FLEX_OF or fid(out_name) not in rows[eid][1:] or in_name in {name(d) for d in rows[eid]}:
                continue
            n_log = len(log)
            in_id = fid(in_name)
            trial = [in_id if d == fid(out_name) else d for d in rows[eid]]
            trial = [fid("Bryce Lance") if d == fid("Cedric Tillman") else d for d in trial]
            if counts()[in_name] < PERSON_MAX and counts()["Bryce Lance"] < PERSON_MAX and legal(eid, trial):
                log.append(dict(step="A", entry_id=eid, thesis=THESIS_OF[eid], out=f"Cedric Tillman + {out_name}",
                                **{"in": f"Bryce Lance + {in_name}"}, salary_before=salary(rows[eid]), salary_after=salary(trial),
                                why=why + f"; {in_name} for {out_name} frees the salary"))
                rows[eid] = trial
                done = True
                break
        if not done:
            log.append(dict(step="A", entry_id=eid, kept="Cedric Tillman", why="Lance does not fit this row"))

# B. DST coherence.
for _, eid in order:
    ids = rows[eid]
    dsts = [d for d in ids if SAL[d]["pos"] == "DST"]
    for dst in dsts:
        team = SAL[dst]["team"]
        opp_qb = STARTING_QB[OPP[team]]
        qb_ids = [d for d in ids[1:] if name(d) == opp_qb]
        if opp_qb not in {name(d) for d in rows[eid]}:
            continue
        done = False
        dst_is_cpt = rows[eid][0] == dst
        other_dst = fid("Vikings") if team == "NO" else fid("Saints")
        if not dst_is_cpt and other_dst not in rows[eid]:
            new = [other_dst if d == dst else d for d in rows[eid]]
            if legal(eid, new) and counts()[name(other_dst)] < PERSON_MAX:
                log.append(dict(step="B", entry_id=eid, thesis=THESIS_OF[eid], out=name(dst), **{"in": name(other_dst)},
                                salary_before=salary(rows[eid]), salary_after=salary(new),
                                why=f"{name(dst)} DST beside opposing QB {opp_qb}; the other DST matches the row"))
                rows[eid] = new
                continue
        # Prefer removing a FLEX DST; if the DST is Captain or the thesis needs it, remove the opposing QB.
        if not dst_is_cpt:
            for side in (team, OPP[team]):
                for cand in INCOMING[side]:
                    if try_swap(eid, dst, cand, "B", f"{name(dst)} DST beside opposing QB {opp_qb}; DST out"):
                        done = True
                        break
                if done:
                    break
        if not done and qb_ids:
            # The DST's own starting quarterback first, so the row keeps a quarterback.
            if try_swap(eid, qb_ids[0], STARTING_QB[team], "B", f"{name(dst)} DST beside opposing QB {opp_qb}; own QB in"):
                done = True
        if not done and qb_ids:
            for cand in INCOMING[team]:
                if try_swap(eid, qb_ids[0], cand, "B", f"{name(dst)} DST beside opposing QB {opp_qb}; QB out"):
                    done = True
                    break
        if not done:
            log.append(dict(step="B", entry_id=eid, unresolved=f"{name(dst)} DST with {opp_qb}"))

# C. WR/TE Captain gets his own QB (one swap, lowest-prior FLEX of the other side first).
for _, eid in order:
    ids = rows[eid]
    c = SAL[ids[0]]
    if c["pos"] not in ("WR", "TE"):
        continue
    qb = STARTING_QB[c["team"]]
    if qb in {name(d) for d in ids}:
        continue
    outs = sorted(ids[1:], key=lambda d: SCORES.get(d, 0.0) or 0.0)
    if not any(try_swap(eid, o, qb, "C", f"{c['name']} Captain without {qb}") for o in outs
               if SAL[o]["pos"] not in ("QB",) and name(o) not in ("Chris Olave", "Devaughn Vele", "Justin Jefferson")):
        log.append(dict(step="C", entry_id=eid, unresolved=f"{c['name']} Captain without {qb}: no single swap fits"))

# D. Value adds. Vele for Kamara in NO-script rows; Jennings for the FLEX kicker in MIN-script rows.
NO_SCRIPTS = ("NO_WINS_BIG", "NO_WINS_CLOSE_HIGH", "OFFENSIVE_SHOOTOUT", "MIN_WINS_CLOSE_HIGH")
MIN_SCRIPTS = ("MIN_WINS_BIG", "MIN_WINS_CLOSE_HIGH", "OFFENSIVE_SHOOTOUT", "NO_WINS_CLOSE_HIGH")
VELE_TARGET, JENNINGS_TARGET = 10, 7
for _, eid in order:
    if counts()["Devaughn Vele"] >= VELE_TARGET:
        break
    if THESIS_OF[eid] in NO_SCRIPTS and fid("Alvin Kamara") in rows[eid]:
        try_swap(eid, fid("Alvin Kamara"), "Devaughn Vele", "D", "Vele 7.8 targets/g, 89-96% snaps; Kamara in 16 rows")
for _, eid in order:
    if counts()["Devaughn Vele"] >= VELE_TARGET:
        break
    if THESIS_OF[eid] in NO_SCRIPTS:
        for out_name in ("Kendre Miller", "Noah Fant", "Bryce Lance"):
            if out_name in FLEX_OF and fid(out_name) in rows[eid]:
                if try_swap(eid, fid(out_name), "Devaughn Vele", "D", "Vele into a NO-script row"):
                    break
for _, eid in order:
    if counts()["Jauan Jennings"] >= JENNINGS_TARGET:
        break
    if THESIS_OF[eid] in MIN_SCRIPTS:
        for out_name in ("Will Reichard", "Daniel Carlson"):
            if fid(out_name) in rows[eid]:
                if try_swap(eid, fid(out_name), "Jauan Jennings", "D", "Addison OUT: Jennings is MIN WR2 (95% snaps week 4); FLEX kicker out"):
                    break

# E. After the value adds: a WR/TE Captain still without his QB may swap the other QB for him;
#    then two NO_WINS_BIG rows flip Shough Captain / Olave FLEX to Olave Captain / Shough FLEX
#    (Olave leads the NFL in targets per game and captained 1 row).
for _, eid in order:
    ids = rows[eid]
    c = SAL[ids[0]]
    if c["pos"] in ("WR", "TE") and STARTING_QB[c["team"]] not in {name(d) for d in ids}:
        other_qb = [d for d in ids[1:] if name(d) == STARTING_QB[OPP[c["team"]]]]
        if not (other_qb and try_swap(eid, other_qb[0], STARTING_QB[c["team"]], "E", f"{c['name']} Captain without his QB; other QB out")):
            log.append(dict(step="E", entry_id=eid, unresolved=f"{c['name']} Captain without {STARTING_QB[c['team']]}"))
CPT_ID = {}
with open(sal_path, newline="", encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        if r["Roster Position"] == "CPT":
            CPT_ID[r["Name"]] = r["ID"]
flips = 0
for _, eid in order:
    if flips >= 2:
        break
    ids = rows[eid]
    if THESIS_OF[eid] == "NO_WINS_BIG" and ids[0] == CPT_ID["Tyler Shough"] and fid("Chris Olave") in ids:
        new = [CPT_ID["Chris Olave"]] + [fid("Tyler Shough") if d == fid("Chris Olave") else d for d in ids[1:]]
        cap_counts = Counter(name(r[0]) for r in rows.values())
        if legal(eid, new) and cap_counts["Chris Olave"] < 6:
            log.append(dict(step="E", entry_id=eid, thesis=THESIS_OF[eid], out="Tyler Shough CPT + Chris Olave FLEX",
                            **{"in": "Chris Olave CPT + Tyler Shough FLEX"}, salary_before=salary(ids), salary_after=salary(new),
                            why="Olave 12 targets/g (NFL lead), 1 Captain row before"))
            rows[eid] = new
            flips += 1

# F. Coherence again, after the value adds freed salary: a DST still beside the opposing QB
#    takes its own team's starting quarterback instead.
for _, eid in order:
    for dst in [d for d in rows[eid] if SAL[d]["pos"] == "DST"]:
        team = SAL[dst]["team"]
        opp_qb = [d for d in rows[eid][1:] if name(d) == STARTING_QB[OPP[team]]]
        if opp_qb and not try_swap(eid, opp_qb[0], STARTING_QB[team], "F", f"{name(dst)} DST beside opposing QB; own QB in"):
            log.append(dict(step="F", entry_id=eid, unresolved=f"{name(dst)} DST with {name(opp_qb[0])}"))

after = snapshot()

with open(out_csv, "x", newline="", encoding="utf-8") as f:
    w = csv.writer(f, lineterminator="\r\n")
    w.writerow(header)
    for i, r in enumerate(raw[1:], start=1):
        eid = r[0].strip() if r else ""
        if eid in rows:
            r = list(r)
            r[4:10] = rows[eid]
        w.writerow(r)

with open(record_path, "x", encoding="utf-8") as f:
    json.dump(dict(input=review_in, output=out_csv, swaps=log, before=before, after=after,
                   does_not_establish=["EV", "ROI", "WIN_PROBABILITY", "UPLOAD_CLEARANCE"]), f, indent=2)

print(json.dumps(dict(swaps=[s for s in log if "in" in s and s["step"]], unresolved=[s for s in log if "in" not in s]), indent=0)[:6000])
for k in ("total_prior", "lowest_row_prior", "max_person", "distinct_people", "mean_pair_overlap", "max_pair_overlap", "pairs_sharing_5", "min_salary", "max_salary", "captains"):
    print(k, before[k], "->", after[k])
print("people after", after["people"])
