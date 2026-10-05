import sys, json, csv, collections, hashlib, io, datetime as dt
CON = '/home/user/nfl-dfs/data/inbox/slates/atl-no-sd-2026-10-05/construction'
sys.path.insert(0, CON)
import numpy as np
import scenario_harness as H
H.BETA['very_sharp'] = 3.0
OUT = CON + '/qa_iter3'
V3 = CON + '/DK_REVIEW_ENTRY_atl-no-sd_ceiling_v3.csv'; I2 = CON + '/qa_iter2/DK_REVIEW_ENTRY_atl-no-sd_qa_iter2.csv'
REPAIR_DEADLINE = dt.datetime(2026, 10, 5, 23, 36, 30, tzinfo=dt.timezone.utc)
DEADLINE = dt.datetime(2026, 10, 5, 23, 38, 50, tzinfo=dt.timezone.utc)
FS = ('sharp', 'very_sharp')
def now(): return dt.datetime.now(dt.timezone.utc)
def log(*a): print(now().strftime('%H:%M:%S'), *a, flush=True)
_orig = H.lineup_score_matrix; _MC = {}
def _lsm(s, sims, rosters):
    if len(rosters) == H.FIELD_POOL:
        k = id(sims)
        if k not in _MC: _MC[k] = _orig(s, sims, rosters)
        return _MC[k]
    return _orig(s, sims, rosters)
H.lineup_score_matrix = _lsm
s = H.slate(); byd = {p.dk_id: p for p in s.players}
POS = {d: r['Position'] for d, r in H._sal().items()}
sc = json.loads(open(CON + '/pool_scores.json').read())['by_dk_id']
excl = set(H.PS_EXCLUDED)
def elig(p): return p.dk_id not in excl and p.dk_id in sc and p.name not in H.BACKUP_QB and (p.status_raw or '').upper() not in ('OUT','IR','D')
role_id = collections.defaultdict(dict)
for p in s.players:
    if elig(p): role_id[p.underlying_id][p.role] = p.dk_id
pname = {p.underlying_id: p.name for p in s.players}; pteam = {p.underlying_id: p.team for p in s.players}
ppos = {byd[d].underlying_id: POS[d] for d in POS if d in byd}
STARTER = {'ATL': 'Michael Penix Jr.', 'NO': 'Tyler Shough'}
uid = {n: u for u, n in pname.items()}
PEN, SHO = uid['Michael Penix Jr.'], uid['Tyler Shough']
entries0 = H.read_file(V3); entries2 = H.read_file(I2)
EID = [e[0] for e in entries0]; CID = [e[1] for e in entries0]; N = len(entries0)
assert [e[0] for e in entries2] == EID and [e[1] for e in entries2] == CID
contests = sorted(set(CID)); cidx = {c: [j for j in range(N) if CID[j] == c] for c in contests}
PITTS = 'Kyle Pitts Sr.'; OLAVE = 'Chris Olave'
def legal(r):
    if len(r) != 6 or any(d not in byd for d in r): return False
    ps = [byd[d] for d in r]
    if ps[0].role != 'CPT' or any(p.role != 'FLEX' for p in ps[1:]): return False
    if not all(elig(p) for p in ps): return False
    if len({p.underlying_id for p in ps}) != 6: return False
    if len({p.team for p in ps}) < 2: return False
    return sum(p.salary for p in ps) <= 50000
def thesis_row(r):
    ps = [byd[d] for d in r]; pos = [POS[d] for d in r]; names = {p.name for p in ps}; v = []
    if pos[0] in ('WR', 'TE') and STARTER[ps[0].team] not in names: v.append('WRTE_CPT_WITHOUT_OWN_QB')
    dst = [p for p, po in zip(ps, pos) if po == 'DST']
    if len(dst) > 1: v.append('MULTI_DST')
    for d in dst:
        if STARTER['NO' if d.team == 'ATL' else 'ATL'] in names: v.append('DST_WITH_OPPOSING_QB')
    if sum(po == 'K' for po in pos) > 1: v.append('MULTI_K')
    if sum(po == 'QB' for po in pos) == 0 and pos[0] not in ('RB', 'K', 'DST'): v.append('ZERO_QB_WITH_NON_RB_K_DST_CPT')
    return v
def nqb(r): return sum(POS[d] == 'QB' for d in r)
def ident(r): return (byd[r[0]].underlying_id, tuple(sorted(byd[d].underlying_id for d in r[1:])))
def people(r): return frozenset(byd[d].underlying_id for d in r)
NEWT = ('NONQB_GT24', 'PENIX_LT10', 'BOTHQB_LT4')
def port_check(R):
    bad = []
    for j, r in enumerate(R):
        if not legal(r): bad.append('ILLEGAL')
        bad += thesis_row(r)
    if len({ident(r) for r in R}) != len(R): bad.append('R29_DUPLICATE')
    cc = collections.Counter(byd[r[0]].underlying_id for r in R)
    pc = collections.Counter(u for r in R for u in people(r))
    if max(cc.values()) > 7: bad.append('CAPTAIN_CAP')
    if max(pc.values()) > 27: bad.append('PERSON_CAP')
    bad += ['NONQB_GT24'] * sum(max(0, n - 24) for u, n in pc.items() if ppos[u] != 'QB')
    Pp = [people(r) for r in R]
    mo = max(len(Pp[a] & Pp[b]) for a in range(len(R)) for b in range(a+1, len(R)))
    if mo > 5: bad.append('OVERLAP')
    nm = collections.Counter(pname[u] for r in R for u in people(r))
    if nm.get(PITTS, 0) > 6: bad.append('PITTS')
    if nm.get(OLAVE, 0) < 7: bad.append('OLAVE')
    bad += ['PENIX_LT10'] * max(0, 10 - pc.get(PEN, 0))
    both = sum(PEN in people(r) and SHO in people(r) for r in R)
    bad += ['BOTHQB_LT4'] * max(0, 4 - both)
    z = sum(nqb(r) == 0 for r in R)
    if z > 3: bad.append('ZERO_QB_ROWS_GT3')
    if len(cc) < 10: bad.append('DISTINCT_CAPTAINS_LT10')
    return bad, dict(distinct_captains=len(cc), captain_counts={pname[u]: n for u, n in cc.most_common()},
                     person_counts_ge18={pname[u]: n for u, n in pc.most_common() if n >= 18}, max_overlap=mo, pitts_rows=nm.get(PITTS, 0), olave_rows=nm.get(OLAVE, 0),
                     penix_rows=pc.get(PEN, 0), both_qb_rows=both, zero_qb_rows=z, qb_per_row_hist=dict(sorted(collections.Counter(nqb(r) for r in R).items())))
def no_worse(bnew, bold, ignore=()):
    cn = collections.Counter(x for x in bnew if x not in ignore); co = collections.Counter(x for x in bold if x not in ignore)
    return all(cn[k] <= co[k] for k in cn)
R0 = [e[2] for e in entries0]; R2 = [e[2] for e in entries2]
b2, st2 = port_check(R2); log('iter2 check', b2, st2)
sims = H.bank('SELECT')
FQ = {f: H.field_quantiles('SELECT', f) for f in FS}; log('fields done')
O = sims.outcomes.astype(np.float64); pidx = {p: i for i, p in enumerate(sims.person_ids)}; S = O.shape[0]
def own(rosters):
    M = np.empty((S, len(rosters)))
    if not rosters: return M
    IX = np.array([[pidx[byd[d].underlying_id] for d in r] for r in rosters])
    for a in range(0, len(rosters), 3000):
        ix = IX[a:a+3000]; v = O[:, ix[:, 0]] * 1.5
        for t in range(1, 6): v = v + O[:, ix[:, t]]
        M[:, a:a+3000] = v
    return M
Q = {f: (FQ[f]['q99'], FQ[f]['q75'], FQ[f]['q50']) for f in FS}
elig_cpt = {u: d['CPT'] for u, d in role_id.items() if 'CPT' in d}
elig_flex = {u: d['FLEX'] for u, d in role_id.items() if 'FLEX' in d}
PL = sorted(set(elig_flex) | set(elig_cpt)); PI = {u: i for i, u in enumerate(PL)}; NP = len(PL)
nonqb = np.array([ppos[u] != 'QB' for u in PL]); iP, iS = PI[PEN], PI[SHO]
def gen(n, cap_names, must, weights_fn, maxtries, seed, max_atl=6, no_dst=False):
    rng = np.random.default_rng(seed); out = set(); tries = 0
    caps = [u for u in elig_cpt if pname[u] in cap_names] if cap_names else list(elig_cpt)
    fl = [u for u in elig_flex if not (no_dst and ppos[u] == 'DST')]
    w = np.array([weights_fn(u) for u in fl], float); cw = np.cumsum(w) / w.sum()
    while len(out) < n and tries < maxtries:
        tries += 1
        cu = caps[rng.integers(len(caps))]
        picks = [m for m in must if m != cu and m in elig_flex]
        if ppos[cu] in ('WR', 'TE'):
            q = uid[STARTER[pteam[cu]]]
            if q not in picks and q != cu: picks.append(q)
        draws = np.searchsorted(cw, rng.random(20))
        for d_ in draws:
            if len(picks) >= 5: break
            u = fl[min(d_, len(fl) - 1)]
            if u != cu and u not in picks: picks.append(u)
        if len(picks) != 5: continue
        r = (elig_cpt[cu],) + tuple(elig_flex[u] for u in picks)
        if not legal(r) or thesis_row(r): continue
        if sum(byd[d].salary for d in r) < 44000: continue
        if sum(pteam[byd[d].underlying_id] == 'ATL' for d in r) > max_atl: continue
        out.add((r[0],) + tuple(sorted(r[1:])))
    return list(out), tries
pc_w = lambda u: 3.0 if ppos[u] in ('WR', 'TE') else (1.5 if ppos[u] == 'RB' else 0.7)
A, ta = gen(15000, ['Drake London', 'Chris Olave', 'Juwan Johnson', 'Bijan Robinson', 'Kyle Pitts Sr.', 'Michael Penix Jr.', 'Tyler Shough', 'Kevin Austin Jr.', 'Alvin Kamara', 'Devaughn Vele'], [PEN, SHO], pc_w, 150000, 11, no_dst=True)
B, tb = gen(12000, ['Drake London', 'Bijan Robinson', 'Kyle Pitts Sr.', 'Michael Penix Jr.', 'Falcons', 'Brian Robinson Jr.', 'Chris Olave', 'Daniel Carlson', 'Nick Folk', 'Saints'], [PEN], lambda u: 3.0 if pteam[u] == 'ATL' else 1.0, 150000, 12)
C, tc_ = gen(12000, ['Alvin Kamara', 'Chris Olave', 'Saints', 'Daniel Carlson', 'Juwan Johnson', 'Tyler Shough', 'Kendre Miller', 'Brian Robinson Jr.', 'Kevin Austin Jr.', 'Kyle Pitts Sr.', 'Falcons', 'Nick Folk'], [], lambda u: 3.0 if pteam[u] == 'NO' else 1.0, 150000, 13, max_atl=2)
pool = H.pool_field(); Mpool = _MC[id(sims)]
psub = [i for i, r in enumerate(pool) if not thesis_row(r)]
tgt = list(dict.fromkeys(A + B + C + [pool[i] for i in psub]))
log('candidates shootout', len(A), 'penix', len(B), 'NO-lean', len(C), 'total', len(tgt))
Mt = own(tgt); tgt_h = {f: (Mt >= Q[f][0][:, None], Mt >= Q[f][1][:, None]) for f in FS}; del Mt
def incid(rosters):
    X = np.zeros((len(rosters), NP), np.int32)
    for k, r in enumerate(rosters):
        for d in r: X[k, PI[byd[d].underlying_id]] = 1
    return X
INC_t = incid(tgt)
def neighbours(R):
    out = set()
    for r in R:
        cu = byd[r[0]].underlying_id; fu = [byd[d].underlying_id for d in r[1:]]; inl = set([cu] + fu)
        for i in range(5):
            for u, d in elig_flex.items():
                if u in inl: continue
                n = list(r); n[1 + i] = d; out.add(tuple(n))
        for u, d in elig_cpt.items():
            if u in inl: continue
            out.add((d,) + tuple(r[1:]))
        for i, f in enumerate(fu):
            if f in elig_cpt and cu in elig_flex:
                n = list(r); n[0] = elig_cpt[f]; n[1 + i] = elig_flex[cu]; out.add(tuple(n))
    return [n for n in out if legal(n) and not thesis_row(n)]
def state(R, f):
    E = own(R); q99, q75, _ = Q[f]
    h99 = E >= q99[:, None]; h75 = E >= q75[:, None]
    cnt = {c: h99[:, js].sum(1) for c, js in cidx.items()}; c75 = h75.sum(1)
    mask = np.empty((N, S), np.float32); W = np.empty((N, S), np.float32)
    for j in range(N):
        mask[j] = ~((cnt[CID[j]] - h99[:, j]) > 0); W[j] = ~((c75 - h75[:, j]) > 0)
    return h99, h75, cnt, c75, mask, W
def cov_counts(R, f):
    st_ = state(R, f); return {c: int((v > 0).sum()) for c, v in st_[2].items()}, int((st_[3] == 0).sum())
def GW(ST, HH, a, b):
    G = {}; WN = {}
    for f in FS:
        h99, h75, cnt, c75, mask, W = ST[f]
        A99 = HH[f][0][:, a:b].astype(np.float32); A75 = HH[f][1][:, a:b].astype(np.float32)
        base = np.einsum('js,sj->j', mask, h99.astype(np.float32))
        G[f] = mask @ A99 - base[:, None]; WN[f] = W.sum(1)[:, None] - W @ A75 - float((c75 == 0).sum())
    return G, WN
def Vparts(cnt, both):
    return np.maximum(0, cnt[..., nonqb] - 24).sum(-1) + np.maximum(0, 10 - cnt[..., iP]) + np.maximum(0, 4 - both)
def record_move(R, j, cand, kind, extra):
    before = {f: cov_counts(R, f) for f in FS}; out = R[j]; R[j] = cand
    after = {f: cov_counts(R, f) for f in FS}
    d = dict(type=kind, entry=EID[j], contest=CID[j], out=[byd[x].name for x in out], into=[byd[x].name for x in cand], out_ids=list(out), in_ids=list(cand), touched=[CID[j]],
             measures={f: dict(changed={c: [before[f][0][c] / S, after[f][0][c] / S] for c in contests if before[f][0][c] != after[f][0][c]}, washout_q75=[before[f][1] / S, after[f][1] / S]) for f in FS}, **extra)
    return d
# ---------------- (1) repair
R = list(R2); repairs = []
while now() < REPAIR_DEADLINE:
    bR, _ = port_check(R)
    nv = sum(x in NEWT for x in bR)
    if nv == 0: break
    ST = {f: state(R, f) for f in FS}
    INC_R = incid(R); cnt = INC_R.sum(0); both = int((INC_R[:, iP] & INC_R[:, iS]).sum())
    nb = neighbours(R); nbM = own(nb); nb_h = {f: (nbM >= Q[f][0][:, None], nbM >= Q[f][1][:, None]) for f in FS}; INC_nb = incid(nb)
    V0 = Vparts(cnt, both)
    best = None
    for src, cands, HH, INC in (('cand', tgt, tgt_h, INC_t), ('nb', nb, nb_h, INC_nb)):
        K = len(cands)
        for a in range(0, K, 6000):
            b = min(K, a + 6000); G, WN = GW(ST, HH, a, b)
            cost = -G['very_sharp'] + 10 * WN['very_sharp']
            Ik = INC[a:b]; bk = Ik[:, iP] & Ik[:, iS]
            for j in range(N):
                base = cnt - INC_R[j]; bb = both - int(INC_R[j, iP] & INC_R[j, iS])
                Vn = Vparts(base[None, :] + Ik, bb + bk); dV = V0 - Vn
                good = np.nonzero(dV > 0)[0]
                if not len(good): continue
                cj = cost[j, good]; dv = dV[good]
                score = np.where(cj > 0, cj / dv, cj * dv)
                for o in np.argsort(score)[:40]:
                    k = int(good[o]); sv = float(score[o])
                    if best is not None and sv >= best[0]: break
                    cand = tuple(cands[a + k]); Rn = list(R); Rn[j] = cand
                    bn, _ = port_check(Rn)
                    if not no_worse(bn, bR, ignore=NEWT): continue
                    best = (sv, j, cand, float(cost[j, k]), int(dV[k]), {f: (float(G[f][j, k]), float(WN[f][j, k])) for f in FS}, src)
                    break
    if best is None: log('REPAIR stuck', bR); break
    d = record_move(R, best[1], best[2], 'repair', dict(cost_scenarios=best[3], violation_reduction=best[4], source=best[6]))
    repairs.append(d); log('REPAIR', len(repairs), json.dumps({k: v for k, v in d.items() if k not in ('out_ids', 'in_ids')}), 'remaining', [x for x in port_check(R)[0] if x in NEWT])
R_rep = list(R); brep, strep = port_check(R_rep); log('repaired check', brep, strep)
# ---------------- (2) pareto
moves = []; it = 0; dd_report = []
jdd = cidx['196285178'][0]
while now() < DEADLINE:
    it += 1
    ST = {f: state(R, f) for f in FS}
    nb = neighbours(R); nbM = own(nb); nb_h = {f: (nbM >= Q[f][0][:, None], nbM >= Q[f][1][:, None]) for f in FS}
    base_b, _ = port_check(R); curcap = collections.Counter(byd[r[0]].underlying_id for r in R); best = None
    for src, cands, HH in (('cand', tgt, tgt_h), ('nb', nb, nb_h)):
        K = len(cands)
        for a in range(0, K, 6000):
            b = min(K, a + 6000); G, WN = GW(ST, HH, a, b)
            ok = (G['sharp'] >= 0) & (G['very_sharp'] >= 0) & (WN['sharp'] <= 0) & (WN['very_sharp'] <= 0) & ((G['very_sharp'] > 0) | (WN['very_sharp'] < 0))
            key = G['very_sharp'] - WN['very_sharp']
            jj, kk = np.nonzero(ok)
            if not len(jj): continue
            for o in np.argsort(-key[jj, kk])[:400]:
                j, k = int(jj[o]), int(kk[o]); cand = tuple(cands[a + k]); cu = byd[cand[0]].underlying_id
                kv = float(key[j, k]) + (3.0 if (curcap.get(cu, 0) - (1 if byd[R[j][0]].underlying_id == cu else 0)) == 0 else 0)
                if best is not None and kv + 3.0 <= best[0]: break
                if best is not None and kv <= best[0]: continue
                Rn = list(R); Rn[j] = cand
                if not no_worse(port_check(Rn)[0], base_b): continue
                best = (kv, 'replace', j, cand, src); 
    Pm = {f: ST[f][4] @ ST[f][0].astype(np.float32) for f in FS}
    for j1 in range(N):
        for j2 in range(j1 + 1, N):
            if CID[j1] == CID[j2]: continue
            g = {f: (Pm[f][j1, j2] - Pm[f][j1, j1], Pm[f][j2, j1] - Pm[f][j2, j2]) for f in FS}
            if it == 1 and jdd in (j1, j2):
                o_ = j2 if j1 == jdd else j1; gi = 0 if j1 == jdd else 1
                dd_report.append(dict(partner=EID[o_], partner_contest=CID[o_], dd_gain={f: float(g[f][gi]) / S for f in FS}, partner_change={f: float(g[f][1 - gi]) / S for f in FS}))
            if min(g['sharp']) >= 0 and min(g['very_sharp']) >= 0 and max(g['very_sharp']) > 0:
                kv = float(sum(g['very_sharp']))
                if best is None or kv > best[0]: best = (kv, 'swap', j1, j2)
    if best is None: log('no passing move at iteration', it); break
    if best[1] == 'replace':
        d = record_move(R, best[2], best[3], 'replace', dict(source=best[4]))
    else:
        j1, j2 = best[2], best[3]; before = {f: cov_counts(R, f) for f in FS}; R[j1], R[j2] = R[j2], R[j1]; after = {f: cov_counts(R, f) for f in FS}
        d = dict(type='swap', entries=[EID[j1], EID[j2]], contests=[CID[j1], CID[j2]], touched=[CID[j1], CID[j2]], j=[j1, j2],
                 measures={f: dict(changed={c: [before[f][0][c] / S, after[f][0][c] / S] for c in contests if before[f][0][c] != after[f][0][c]}, washout_q75=[before[f][1] / S, after[f][1] / S]) for f in FS})
    moves.append(d); log('MOVE', it, json.dumps({k: v for k, v in d.items() if k not in ('out_ids', 'in_ids')}))
dd_report.sort(key=lambda x: -x['dd_gain']['very_sharp'])
log('search ended; moves', len(moves), 'DD best swaps', json.dumps(dd_report[:3]))
def ev(R_, p, f):
    ent = [(EID[j], CID[j], R_[j]) for j in range(N)]; e = H.evaluate(ent, p, f); e.pop('entry_top1'); return e
def compare(R_):
    out = {}
    for p in ('SELECT', 'REFEREE'):
        for f in FS: out[f'{p}_{f}'] = dict(v3=ev(R0, p, f), iter2=ev(R2, p, f), iter3=ev(R_, p, f))
    return out
cmp = compare(R)
def ref_worse(cmp, base='iter2'):
    return sorted({c for f in FS for c in contests if cmp[f'REFEREE_{f}']['iter3']['contest_top1'][c] < cmp[f'REFEREE_{f}'][base]['contest_top1'][c]})
# revert pareto moves touching REFEREE-worse contests (relative to the repaired file)
rep_cmp = {f: ev(R_rep, 'REFEREE', f) for f in FS}
worse = sorted({c for f in FS for c in contests if cmp[f'REFEREE_{f}']['iter3']['contest_top1'][c] < rep_cmp[f]['contest_top1'][c]})
reverts = []
if worse:
    tc = set(worse)
    for m in moves:
        if tc & set(m['touched']): tc |= set(m['touched'])
    Rt = list(R)
    for j in range(N):
        if CID[j] in tc and Rt[j] != R_rep[j]: Rt[j] = R_rep[j]; reverts.append(EID[j])
    if no_worse(port_check(Rt)[0], port_check(R)[0]): R = Rt; cmp = compare(R)
    else: log('revert would break constraints', port_check(Rt)[0]); reverts = ['NOT_APPLIED'] + reverts
log('REFEREE worse vs repaired', worse, 'reverted', reverts)
gate = {}
for k, d in cmp.items():
    fails = [c for c in contests if d['iter3']['contest_top1'][c] < d['v3']['contest_top1'][c]]
    for w in ('washout_q75', 'washout_q50'):
        if d['iter3'][w] > d['v3'][w]: fails.append(w)
    gate[k] = fails
log('FINAL GATE vs v3', gate)
bF, stF = port_check(R); log('final check', bF, stF)
raw = open(V3, newline='').read(); rows = list(csv.reader(io.StringIO(raw, newline='')))
buf = io.StringIO(); csv.writer(buf, lineterminator='\r\n').writerows(rows); rt = buf.getvalue() == raw
emap = dict(zip(EID, R)); nrows = []
for r in rows:
    if r and r[0] in emap and len(r) >= 10: r = list(r); r[4:10] = list(emap[r[0]])
    nrows.append(r)
buf = io.StringIO(); csv.writer(buf, lineterminator='\r\n').writerows(nrows)
outcsv = OUT + '/DK_REVIEW_ENTRY_atl-no-sd_qa_iter3.csv'
with open(outcsv, 'x', newline='') as fh: fh.write(buf.getvalue())
sha = hashlib.sha256(open(outcsv, 'rb').read()).hexdigest(); log('wrote', outcsv, sha, 'roundtrip', rt)
remw = {}
names = ['Tyler Shough', 'Michael Penix Jr.', 'Bijan Robinson', 'Drake London', 'Chris Olave', 'Juwan Johnson', 'Alvin Kamara']
team_pts = collections.defaultdict(lambda: np.zeros(S))
for u, i in pidx.items():
    if u in pteam: team_pts[pteam[u]] += O[:, i]
for f in FS:
    E = own(R); w = ~(E >= Q[f][1][:, None]).any(1); d = dict(rate=float(w.mean()), n=int(w.sum()))
    if w.sum():
        d['team_points_washout_vs_all'] = {t: [round(float(v[w].mean()), 1), round(float(v.mean()), 1)] for t, v in team_pts.items()}
        for nm in names:
            x = O[:, pidx[uid[nm]]]; pct = x.argsort().argsort() / (S - 1); d[nm + ' mean pctile'] = round(float(pct[w].mean()), 3)
    remw[f] = d
log('remaining washout', json.dumps(remw))
rec = dict(status='DIAGNOSTIC_PRIOR_ONLY_NOT_AN_UPLOAD_AUTHORIZATION', RELEASE_DECISION='DO_NOT_UPLOAD',
           rule='repair to new constraints at least cost on SELECT very_sharp (contest_top1 loss + 10x washout_q75 increase); then Pareto on SELECT sharp+very_sharp; REFEREE report-only, revert Pareto moves touching REFEREE-worse contests; final gate no worse than v3 on 4 bank/field combos',
           input=dict(v3=V3, iter2=I2, iter2_sha256=hashlib.sha256(open(I2, 'rb').read()).hexdigest()), output=dict(path=outcsv, sha256=sha, v3_csv_roundtrip_identical=rt),
           iter2_checks=dict(defects=b2, **st2), repaired_checks=dict(defects=brep, **strep), final_checks=dict(defects=bF, **stF),
           candidates=dict(shootout=len(A), penix=len(B), no_lean=len(C), total=len(tgt)), repairs=repairs, moves=moves, daily_dollar_best_swaps=dd_report[:5],
           referee_worse_vs_repaired=worse, reverted_entries=reverts, final_gate_failures=gate, comparison=cmp, remaining_washout=remw, search=dict(iterations=it))
with open(OUT + '/record.json', 'x') as fh: json.dump(rec, fh, indent=1, default=lambda o: o.tolist() if hasattr(o, 'tolist') else str(o))
log('record written')
