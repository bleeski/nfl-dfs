"""Adversarial Pareto search on a BAL@ATL Showdown v3-style file. Scratch tool, writes only to out paths given.

Usage: pareto_search.py <repo> <in_csv> <out_csv|-> <record_json|-> [mode]
mode: pareto (default) | report
"""
import csv, json, os, sys, itertools
from collections import Counter

repo, in_csv, out_csv, rec_path = sys.argv[1:5]
mode = sys.argv[5] if len(sys.argv) > 5 else "pareto"
I = os.path.join(repo, "data/inbox/slates/bal-atl-sd-2026-10-11/input")
C = os.path.join(repo, "data/inbox/slates/bal-atl-sd-2026-10-11/construction")

SAL, ID_OF = {}, {}
with open(os.path.join(I, "DKSalaries_176.csv"), newline="", encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        SAL[r["ID"]] = dict(name=r["Name"], team=r["TeamAbbrev"], pos=r["Position"], salary=int(r["Salary"]),
                            rp=r["Roster Position"], status=r.get("Status", ""))
        ID_OF[(r["Name"], r["Roster Position"])] = r["ID"]
SC = json.load(open(os.path.join(C, "pool_scores_r3.json")))["by_dk_id"]
THESIS_OF = json.load(open(os.path.join(C, "theses_by_entry.json")))
TH = {}
for fn in os.listdir(os.path.join(C, "theses")):
    d = json.load(open(os.path.join(C, "theses", fn)))
    TH[d["name"]] = d
excl = open(os.path.join(C, "exclude_args.txt")).read().split()
BANNED = {x for x in excl if x.isdigit()}
BAN_NAMES = {"Lamar Jackson", "Cooper Rush", "Jack Strand", "Elijah Sarratt", "Skylar Thompson", "Trey Sermon",
             "Adam Randall", "Ja'Kobi Lane", "Beaux Collins", "Durham Smythe", "Tua Tagovailoa", "Joe Fagnano"}
# judgment: Pitts's prior prices last season's role (2.2 tgt/g in 2026); never brought in by this search
NO_IN_NAMES = {"Kyle Pitts Sr."}
for d, s in SAL.items():
    if s["name"] in BAN_NAMES or s["status"] in ("O", "OUT", "IR"):
        BANNED.add(d)
STARTING_QB = {"BAL": "Tyler Huntley", "ATL": "Michael Penix Jr."}
OPP = {"BAL": "ATL", "ATL": "BAL"}
CAP, PMAX, CPTMAX, OVMAX = 50000, 24, 6, 5

with open(in_csv, newline="", encoding="utf-8-sig") as f:
    raw = list(csv.reader(f))
rows, order = {}, []
for r in raw[1:]:
    if r and r[0].strip().isdigit() and all(c.strip() for c in r[4:10]):
        rows[r[0].strip()] = [c.strip() for c in r[4:10]]
        order.append(r[0].strip())

nm = lambda d: SAL[d]["name"]
sc = lambda ids: sum(SC.get(d, 0.0) or 0.0 for d in ids)
sal = lambda ids: sum(SAL[d]["salary"] for d in ids)

def measures(rs):
    c = Counter(nm(d) for ids in rs.values() for d in ids)
    cap = Counter(nm(ids[0]) for ids in rs.values())
    sets = [frozenset(nm(d) for d in ids) for ids in rs.values()]
    ov = [len(a & b) for a, b in itertools.combinations(sets, 2)]
    tot = [sc(ids) for ids in rs.values()]
    return dict(total=round(sum(tot), 3), low=round(min(tot), 3), maxp=max(c.values()),
                maxp_name=[n for n, v in c.items() if v == max(c.values())], top3=sum(v for _, v in c.most_common(3)),
                meanov=round(sum(ov) / len(ov), 4), maxov=max(ov), distinct=len(c), cap=dict(cap.most_common()),
                ov_sum=sum(ov), exposure=dict(c.most_common()))

def conflict(ids):
    names = {nm(d) for d in ids}
    return any(SAL[d]["pos"] == "DST" and STARTING_QB[OPP[SAL[d]["team"]]] in names for d in ids)

def legal(eid, ids, rs):
    if SAL[ids[0]]["rp"] != "CPT" or any(SAL[d]["rp"] != "FLEX" for d in ids[1:]):
        return "slot"
    if any(d in BANNED for d in ids):
        return "banned"
    if sal(ids) > CAP: return "cap"
    if len({nm(d) for d in ids}) != 6: return "dup_person"
    if len({SAL[d]["team"] for d in ids}) < 2: return "one_team"
    t = TH[THESIS_OF[eid]]
    if "|".join([SAL[ids[0]]["team"], SAL[ids[0]]["pos"], nm(ids[0])]) not in t["captain_set"]:
        return "captain_set"
    tc = Counter(SAL[d]["team"] for d in ids); pc = Counter(SAL[d]["pos"] for d in ids)
    for b in t.get("team_bounds") or []:
        if not b["minimum"] <= tc[b["team"]] <= b["maximum"]: return "team_bounds"
    pb = {b["position"]: b for b in (t.get("position_bounds") or [])}
    for b in pb.values():
        if not b["minimum"] <= pc[b["position"]] <= b["maximum"]: return "pos_bounds"
    qbs = [d for d in ids if SAL[d]["pos"] == "QB"]
    if not 1 <= len(qbs) <= 2: return "qb_count"
    for q in qbs:
        n = sum(1 for d in ids if SAL[d]["pos"] in ("WR", "TE") and SAL[d]["team"] == SAL[q]["team"])
        if not 1 <= n <= 2: return "qb_stack"
    if "K" not in pb and pc["K"] > 1: return "k"
    if "DST" not in pb and pc["DST"] > 1: return "dst"
    if conflict(ids): return "dst_vs_qb"
    key = (ids[0], frozenset(ids[1:]))
    for o, oids in rs.items():
        if o != eid and (oids[0], frozenset(oids[1:])) == key: return "R29"
    return None

def worse(m0, m1):
    out = []
    if m1["maxp"] > m0["maxp"]: out.append("maxp")
    if m1["top3"] > m0["top3"]: out.append("top3")
    if m1["ov_sum"] > m0["ov_sum"]: out.append("meanov")
    if m1["maxov"] > m0["maxov"]: out.append("maxov")
    if m1["distinct"] < m0["distinct"]: out.append("distinct")
    if max(m1["cap"].values()) > CPTMAX: out.append("cptcap")
    if m1["maxp"] > PMAX: out.append("pmax")
    return out

m0 = measures(rows)
if mode == "report":
    print(json.dumps({k: v for k, v in m0.items() if k != "exposure"}))
    print("exposure", m0["exposure"])
    for e in order:
        ids = rows[e]
        print(e, THESIS_OF[e], round(sc(ids), 2), sal(ids), "CPT", nm(ids[0]), "|", ", ".join(nm(d) for d in ids[1:]),
              "CONFLICT" if conflict(ids) else "", legal(e, ids, rows) or "")
    sys.exit(0)

FLEXPOOL = [d for d, s in SAL.items() if s["rp"] == "FLEX" and d not in BANNED and s["name"] not in NO_IN_NAMES]
CPT_OF = {nm(d): d for d, s in SAL.items() if s["rp"] == "CPT"}
FLEX_OF = {nm(d): d for d, s in SAL.items() if s["rp"] == "FLEX"}
log, rejected = [], Counter()
BAN_SWAPS = set(x for x in os.environ.get("BAN_SWAPS", "").split(";") if x)
ALLFLEX = [d for d, s_ in SAL.items() if s_["rp"] == "FLEX" and d not in BANNED and s_["name"] not in NO_IN_NAMES]
if os.environ.get("FIX_CONFLICTS"):
    for e in order:
        ids = rows[e]
        if not conflict(ids): continue
        if os.environ.get("FIX_ONLY") and e not in os.environ["FIX_ONLY"].split(","): continue
        best = None
        for k in (1, 2):
            for outs in itertools.combinations(range(1, 6), k):
                for ins in itertools.combinations(ALLFLEX, k):
                    if any(d in ids for d in ins): continue
                    for perm in itertools.permutations(ins):
                        n = list(ids)
                        for o, d in zip(outs, perm): n[o] = d
                        if legal(e, n, rows): continue
                        trial = dict(rows); trial[e] = n
                        m1 = measures(trial); w = worse(m0, m1)
                        if m1["maxov"] > OVMAX: w.append("ovmax")
                        if w: continue
                        if best is None or sc(n) > best[0]: best = (sc(n), n, m1)
                        break
            if best: break
        if best:
            log.append(dict(entry_id=e, thesis=THESIS_OF[e], kind="conflict_fix",
                            out=[nm(d) for d in rows[e] if d not in best[1]], **{"in": [nm(d) for d in best[1] if d not in rows[e]]},
                            prior_before=round(sc(rows[e]), 3), prior_after=round(best[0], 3), salary_after=sal(best[1])))
            rows[e] = best[1]; m0 = best[2]
        else:
            log.append(dict(entry_id=e, thesis=THESIS_OF[e], kind="conflict_fix", unresolved="no legal 1-2 FLEX change with no washout measure worse"))
changed = True
passes = 0
while changed and passes < 20:
    changed = False; passes += 1
    best = None
    for e in order:
        ids = rows[e]; base = sc(ids)
        cands = []
        # single FLEX swaps
        for i in range(1, 6):
            for d in FLEXPOOL:
                if d in ids: continue
                if SAL[d]["pos"] in ("K", "DST") or SAL[ids[i]]["pos"] in ("K", "DST"):
                    continue  # keep K/DST structure fixed
                n = list(ids); n[i] = d; cands.append(("flex", n))
        # CPT<->FLEX flip
        for i in range(1, 6):
            cp = CPT_OF.get(nm(ids[i])); fl = FLEX_OF.get(nm(ids[0]))
            if cp and fl:
                n = list(ids); n[0] = cp; n[i] = fl; cands.append(("flip", n))
        for kind, n in cands:
            s = sc(n)
            if s <= base + 1e-9: continue
            o_n = [nm(d) for d in ids if d not in n]; i_n = [nm(d) for d in n if d not in ids]
            if any(f"{e}:{a}:{b}" in BAN_SWAPS for a in o_n for b in i_n): rejected["judgment_ban"] += 1; continue
            why = legal(e, n, rows)
            if why: rejected[why] += 1; continue
            trial = dict(rows); trial[e] = n
            m1 = measures(trial)
            w = worse(m0, m1)
            if m1["maxov"] > OVMAX: w.append("ovmax")
            if w: rejected["washout:" + ",".join(w)] += 1; continue
            gain = s - base
            if best is None or gain > best[0]:
                best = (gain, e, kind, n, m1)
    if best:
        gain, e, kind, n, m1 = best
        log.append(dict(entry_id=e, thesis=THESIS_OF[e], kind=kind,
                        out=[nm(d) + ("(CPT)" if j == 0 else "") for j, d in enumerate(rows[e]) if d not in n],
                        **{"in": [nm(d) + ("(CPT)" if j == 0 else "") for j, d in enumerate(n) if d not in rows[e]]},
                        prior_before=round(sc(rows[e]), 3), prior_after=round(sc(n), 3),
                        salary_after=sal(n)))
        rows[e] = n; m0 = m1; changed = True
print("ACCEPTED", json.dumps(log, indent=1))
print("REJECTED_COUNTS", dict(rejected.most_common(12)))
mF = measures(rows)
print("FINAL", json.dumps({k: v for k, v in mF.items() if k != "exposure"}))
if out_csv != "-" and log:
    with open(out_csv, "x", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\r\n")
        for i, r in enumerate(raw):
            eid = r[0].strip() if r else ""
            if i > 0 and eid in rows:
                r = list(r); r[4:10] = rows[eid]
            w.writerow(r)
    with open(rec_path, "x", encoding="utf-8") as f:
        json.dump(dict(input=in_csv, output=out_csv, swaps=log, final=mF,
                       does_not_establish=["EV", "ROI", "WIN_PROBABILITY", "UPLOAD_CLEARANCE"]), f, indent=2)
