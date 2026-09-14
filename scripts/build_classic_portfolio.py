#!/usr/bin/env python3
"""Construction layer for a Classic GPP portfolio. NOT the evidence layer.

Provenance: this is the code that actually produced the 2026-09-13 Week 1
portfolio, promoted out of a session scratchpad. On that slate the engine's C2
candidate-bank solver failed six times across 43 minutes and never produced a
portfolio; this script produced one in about ten minutes from the engine's own
gated per-player scores. See docs/CLASSIC_C4_RETROSPECTIVE_2026-09-13.md.

The split it assumes: the ENGINE owns evidence (priors, identity, weather,
official activity, participation) and emits a scored player pool. THIS owns
construction (stacking, bring-backs, exposure caps, anti-correlation, leverage),
which CLAUDE.md classes as preferences Claude may set under a lock clock.

Input `scores.json` is currently produced by a debug hook in selection.py.
Backlog P1-4 replaces that with a first-class artifact; when it lands, only the
loader below changes.

Known gaps, all tracked in Appendix A of the retrospective:
  P1-6  dart conditions here still predate the rewrite (top-4 total, lowest
        ownership) rather than "names the prior it is short" + 2-12% with a role
  P1-7  no salary reserve: this spends toward the cap
  P1-8  no early-locked vs swap-flexible entry tagging
  P1-9  the prior model's exclusion list is not used as a dart candidate pool
  P1-10 QB leverage is not taken first
"""

import csv, json, random, sys, collections

SCORES, SAL, STATUS, OUT = sys.argv[1:5]
N, CAP = 20, 50000
random.seed(913)

scores = json.load(open(SCORES))["by_dk_id"]
sal = {r["ID"]: r for r in csv.DictReader(open(SAL, encoding="utf-8-sig"))}
status = {r["PLAYER_OR_GSIS_ID"]: r["STATUS"]
          for r in csv.DictReader(open(STATUS, encoding="utf-8-sig"))}

ITT = {"LAC":28.50,"DET":28.25,"CIN":27.00,"BAL":25.50,"CHI":25.25,"PHI":25.00,
       "JAX":24.25,"MIN":24.25,"PIT":23.75,"TB":23.50,"BUF":23.00,"CAR":22.25,
       "GB":22.25,"IND":22.00,"LV":21.75,"HOU":21.50,"NO":21.25,"TEN":20.00,
       "WAS":19.50,"ARI":19.00,"MIA":18.75,"NYJ":18.50,"ATL":17.25,"CLE":15.75}
OWN = {"Jahmyr Gibbs":47.2,"Ja'Marr Chase":32.4,"Michael Mayer":25.1,"Chris Olave":26.2,
       "Amon-Ra St. Brown":21.2,"Bijan Robinson":24.2,"Ashton Jeanty":17,"Jonathan Taylor":16,
       "De'Von Achane":15,"Derrick Henry":13,"Zay Flowers":13,"Saquon Barkley":13,
       "Omarion Hampton":13,"Chase Brown":8.8,"Jameson Williams":8.3,"Tee Higgins":10,
       "Emeka Egbuka":5,"Sam LaPorta":9,"Josh Allen":3,"Khalil Shakir":2,
       "Lamar Jackson":5.5,"Baker Mayfield":2,"Bucky Irving":1.5,"Bhayshul Tuten":1.1,
       "Trey McBride":5.5,"Travis Etienne Jr.":6,"Tyler Warren":9.4,"DeVonta Smith":9,
       "Jalen Coker":3,"Drake London":8,"Jalen Hurts":9}
# Construction adjustment, NOT evidence: confirmed Week 1 role vacancies the
# prior-season model cannot see. Each is tied to a specific reported absence.
BOOST = {"Michael Mayer":1.95,     # Brock Bowers out (meniscus)
         "Travis Etienne Jr.":1.55, # Alvin Kamara out
         "Tre Tucker":1.30,         # Bowers' vacated targets
         "Bucky Irving":1.25,       # Sean Tucker out
         "Dallas Goedert":1.20,     # A.J. Brown departed
         "DeVonta Smith":1.15,      # A.J. Brown departed
         "Kendre Miller":1.20}      # Kamara out

P  = lambda i: sal[i]["Position"]; S = lambda i: int(sal[i]["Salary"])
T  = lambda i: sal[i]["TeamAbbrev"]; NM = lambda i: sal[i]["Name"]
G  = lambda i: sal[i]["Game Info"].split()[0]
def OPP(i):
    a, h = G(i).split("@"); return h if T(i) == a else a

pool = [i for i in scores if i in sal and status.get(i) != "INACTIVE" and scores[i] > 0]
def wt(i):
    w = 1.0 + (ITT.get(T(i), 21.0) - 21.0) * 0.090      # steeper than v1
    o = OWN.get(NM(i))
    if o is not None: w *= 1.0 + (12.0 - min(o, 50.0)) * 0.010
    return w * BOOST.get(NM(i), 1.0)
val = {i: scores[i] * wt(i) for i in pool}

QBS = [i for i in pool if P(i) == "QB"]
CCH = lambda t: [i for i in pool if T(i) == t and P(i) in ("WR","TE")]
SKL = lambda t: [i for i in pool if T(i) == t and P(i) in ("WR","TE","RB")]

def anti(r):
    """Reject self-cancelling construction."""
    d = [i for i in r if P(i) == "DST"]
    if not d: return True
    dst = d[0]; foe = OPP(dst)
    if any(T(i) == foe and P(i) != "DST" for i in r): return True   # DST vs own skill
    q = [i for i in r if P(i) == "QB"]
    if q and T(dst) == OPP(q[0]): return True                        # DST vs own QB
    return False

def pick(c, exp, cap, k=1, ex=()):
    c = [i for i in c if i not in ex and exp[i] < cap]
    if len(c) < k: return []
    w = [max(val.get(i, .01), .01) ** 2.2 for i in c]
    out, seen = [], set()
    for _ in range(k*8):
        if len(out) == k: break
        x = random.choices(c, weights=w, k=1)[0]
        if x not in seen: seen.add(x); out.append(x)
    return out if len(out) == k else []

def complete(seed, exp, cap):
    r = list(seed); need = {"QB":1,"RB":2,"WR":3,"TE":1,"DST":1}
    for i in r: need[P(i)] = need.get(P(i),0) - 1
    if any(v < 0 for v in need.values()): return None
    for p in [p for p,n in need.items() for _ in range(max(0,n))]:
        g = pick([i for i in pool if P(i)==p], exp, cap, 1, ex=r)
        if not g: return None
        r.append(g[0])
    if len(r) < 9:
        g = pick([i for i in pool if P(i) in ("RB","WR","TE")], exp, cap, 1, ex=r)
        if not g: return None
        r.append(g[0])
    if len(r)!=9 or len(set(r))!=9: return None
    if sum(S(i) for i in r) > CAP: return None
    if len({G(i) for i in r}) < 2: return None
    if anti(r): return None
    return r

lineups, exp, EXP, OVL = [], collections.Counter(), 6, 4
need_bb = 14
for att in range(900000):
    if len(lineups) == N: break
    if att and att % 150000 == 0:
        EXP = min(EXP+1, 9); OVL = min(OVL+1, 6); need_bb = max(need_bb-3, 6)
    q = pick(QBS, exp, EXP, 1)
    if not q: continue
    q = q[0]; mates = CCH(T(q))
    if not mates: continue
    seed = [q] + pick(mates, exp, EXP, 1, ex=[q])
    if len(seed) < 2: continue
    if random.random() < 0.60: seed += pick(mates, exp, EXP, 1, ex=seed)
    bb = len([1 for L in lineups if any(T(i)==OPP([x for x in L if P(x)=="QB"][0]) and P(i)!="DST" for i in L)])
    if random.random() < 0.85 or bb < need_bb*len(lineups)//max(N,1):
        seed += pick(SKL(OPP(q)), exp, EXP, 1, ex=seed)
    r = complete(seed, exp, EXP)
    if not r: continue
    if any(len(set(r)&set(x)) > OVL for x in lineups): continue
    lineups.append(r)
    for i in r: exp[i] += 1

print(f"built {len(lineups)} | exposure cap {EXP}/20, overlap cap {OVL}")
json.dump({"lineups":[{"index":n+1,"roster":r,"salary":sum(S(i) for i in r),
                       "prior_points":round(sum(scores[i] for i in r),3)}
                      for n,r in enumerate(lineups)],
           "assignments_by_entry_id":{}}, open(OUT,"w"), indent=1)
