import sys, time, json, csv, collections, hashlib, io, datetime as dt
CON = '/home/user/nfl-dfs/data/inbox/slates/atl-no-sd-2026-10-05/construction'
sys.path.insert(0, CON)
import numpy as np
import scenario_harness as H
OUT = CON + '/qa_iter1'
V3 = CON + '/DK_REVIEW_ENTRY_atl-no-sd_ceiling_v3.csv'
DEADLINE = dt.datetime(2026, 10, 5, 23, 22, 50, tzinfo=dt.timezone.utc)
def now(): return dt.datetime.now(dt.timezone.utc)
def log(*a): print(now().strftime('%H:%M:%S'), *a, flush=True)
# cache pool score matrix (harness recomputes it per field otherwise)
_orig = H.lineup_score_matrix; _MC = {}
def _lsm(s, sims, rosters):
    if len(rosters) == H.FIELD_POOL:
        k = id(sims)
        if k not in _MC: _MC[k] = _orig(s, sims, rosters)
        return _MC[k]
    return _orig(s, sims, rosters)
H.lineup_score_matrix = _lsm
s = H.slate(); byd = {p.dk_id: p for p in s.players}
sc = json.loads(open(CON + '/pool_scores.json').read())['by_dk_id']
excl = set(H.PS_EXCLUDED)
def elig(p): return p.dk_id not in excl and p.dk_id in sc and p.name not in H.BACKUP_QB and (p.status_raw or '').upper() not in ('OUT','IR','D')
role_id = collections.defaultdict(dict)
for p in s.players:
    if elig(p): role_id[p.underlying_id][p.role] = p.dk_id
pname = {p.underlying_id: p.name for p in s.players}
entries0 = H.read_file(V3)
EID = [e[0] for e in entries0]; CID = [e[1] for e in entries0]; N = len(entries0)
contests = sorted(set(CID)); cidx = {c: [j for j in range(N) if CID[j] == c] for c in contests}
log('entries', N, {c: len(v) for c, v in cidx.items()})
PITTS = 'Kyle Pitts Sr.'; OLAVE = 'Chris Olave'
def legal(r):
    if len(r) != 6 or any(d not in byd for d in r): return False
    ps = [byd[d] for d in r]
    if ps[0].role != 'CPT' or any(p.role != 'FLEX' for p in ps[1:]): return False
    if not all(elig(p) for p in ps): return False
    if len({p.underlying_id for p in ps}) != 6: return False
    if len({p.team for p in ps}) < 2: return False
    return sum(p.salary for p in ps) <= 50000
def ident(r): return (byd[r[0]].underlying_id, tuple(sorted(byd[d].underlying_id for d in r[1:])))
def people(r): return frozenset(byd[d].underlying_id for d in r)
def port_check(R):
    bad = []
    for j, r in enumerate(R):
        if not legal(r): bad.append(f'illegal {j}')
    if len({ident(r) for r in R}) != len(R): bad.append('R29 duplicate')
    cc = collections.Counter(byd[r[0]].underlying_id for r in R)
    pc = collections.Counter(u for r in R for u in people(r))
    if max(cc.values()) > 7: bad.append('captain cap')
    if max(pc.values()) > 27: bad.append('person cap')
    P = [people(r) for r in R]
    mo = max(len(P[a] & P[b]) for a in range(len(R)) for b in range(a+1, len(R)))
    if mo > 5: bad.append(f'overlap {mo}')
    nm = collections.Counter(pname[u] for r in R for u in people(r))
    if nm.get(PITTS, 0) > 6: bad.append('pitts')
    if nm.get(OLAVE, 0) < 7: bad.append('olave')
    return bad, dict(distinct_captains=len(cc), captain_counts={pname[u]: n for u, n in cc.most_common()},
                     max_person_count=max(pc.values()), max_person=pname[pc.most_common(1)[0][0]], max_overlap=mo,
                     pitts_rows=nm.get(PITTS, 0), olave_rows=nm.get(OLAVE, 0))
R0 = [e[2] for e in entries0]
b0, st0 = port_check(R0); log('v3 constraint check', b0, st0)
sims = H.bank('SELECT'); log('bank SELECT done')
FQ = {f: H.field_quantiles('SELECT', f) for f in ('sharp', 'uniform')}; log('fields done')
O = sims.outcomes.astype(np.float64); pidx = {p: i for i, p in enumerate(sims.person_ids)}; S = O.shape[0]
def own(rosters):
    M = np.empty((S, len(rosters)))
    for k, r in enumerate(rosters):
        ix = [pidx[byd[d].underlying_id] for d in r]
        v = O[:, ix[0]] * 1.5
        for i in ix[1:]: v = v + O[:, i]
        M[:, k] = v
    return M
chk = H.lineup_score_matrix(s, sims, R0); log('own vs harness maxdiff', float(np.abs(own(R0) - chk).max()))
Q = {f: (FQ[f]['q99'], FQ[f]['q75'], FQ[f]['q50']) for f in FQ}
pool = H.pool_field(); Mpool = _MC[id(sims)]
def meas(R, f):
    E = own(R); q99, q75, q50 = Q[f]
    h = E >= q99[:, None]
    return dict(contest_top1={c: float(h[:, js].any(1).mean()) for c, js in cidx.items()},
                washout_q75=float((~(E >= q75[:, None]).any(1)).mean()), washout_q50=float((~(E >= q50[:, None]).any(1)).mean()),
                entry_top1=h.mean(0), portfolio_any_top1=float(h.any(1).mean()))
# ---------- (a) diagnosis
diag = {}
E0 = own(R0); q99s, q75s, q50s = Q['sharp']; h0 = E0 >= q99s[:, None]; w0 = ~(E0 >= q75s[:, None]).any(1)
diag['per_entry_top1_sharp_select'] = {EID[j]: dict(contest=CID[j], captain=byd[R0[j][0]].name, rate=round(float(h0[:, j].mean()), 4)) for j in range(N)}
marg = {}
for c, js in cidx.items():
    full = h0[:, js].any(1).mean()
    for j in js:
        oth = [k for k in js if k != j]
        wo = h0[:, oth].any(1).mean() if oth else 0.0
        marg[EID[j]] = dict(contest=c, marginal=round(float(full - wo), 4), solo=round(float(h0[:, j].mean()), 4))
diag['marginal_contest_top1'] = marg
diag['zero_marginal_entries'] = [e for e, v in marg.items() if v['marginal'] == 0 and v['solo'] > 0]
log('per-contest marginals (lowest 10):', sorted(((v['marginal'], e, v['contest']) for e, v in marg.items()))[:10])
names = ['Tyler Shough', 'Michael Penix Jr.', 'Bijan Robinson', 'Drake London', 'Chris Olave', 'Juwan Johnson', 'Alvin Kamara']
wash = {}
for nm in names:
    us = [u for u, n in pname.items() if n == nm]
    if not us or us[0] not in pidx: wash[nm] = 'not found'; continue
    x = O[:, pidx[us[0]]]; pct = x.argsort().argsort() / (S - 1)
    wash[nm] = dict(mean_pctile_in_washout=round(float(pct[w0].mean()), 3), mean_pts_washout=round(float(x[w0].mean()), 2), mean_pts_all=round(float(x.mean()), 2),
                    share_washout_below_p25=round(float((pct[w0] < 0.25).mean()), 3))
diag['washout_q75_sharp_select'] = dict(rate=round(float(w0.mean()), 4), n_scenarios=int(w0.sum()), players=wash)
# team totals in washout
team_pts = collections.defaultdict(lambda: np.zeros(S))
for u, i in pidx.items():
    tm = next((p.team for p in s.players if p.underlying_id == u), None)
    if tm: team_pts[tm] += O[:, i]
diag['washout_team_points'] = {t: dict(washout=round(float(v[w0].mean()), 1), all=round(float(v.mean()), 1)) for t, v in team_pts.items()}
ourc = collections.Counter(byd[r[0]].name for r in R0)
diag['captains_field_sharp_vs_ours'] = dict(field_sharp=FQ['sharp']['field_captain_share'], field_uniform=FQ['uniform']['field_captain_share'],
                                           ours={k: round(v / N, 4) for k, v in ourc.most_common()})
log('DIAG', json.dumps(diag['washout_q75_sharp_select']), json.dumps(diag['washout_team_points']), json.dumps(diag['captains_field_sharp_vs_ours']))
# ---------- (b) search
elig_cpt = {u: d['CPT'] for u, d in role_id.items() if 'CPT' in d}
elig_flex = {u: d['FLEX'] for u, d in role_id.items() if 'FLEX' in d}
def neighbours(R):
    out = set()
    for r in R:
        cu = byd[r[0]].underlying_id; fu = [byd[d].underlying_id for d in r[1:]]
        inl = set([cu] + fu)
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
    return [n for n in out if legal(n)]
def hits_of(M, f):
    q99, q75, _ = Q[f]
    return (M >= q99[:, None]).astype(np.float32), (M >= q75[:, None]).astype(np.float32)
pool_h = {}
for f in Q:
    q99, q75, _ = Q[f]
    pool_h[f] = ((Mpool >= q99[:, None]), (Mpool >= q75[:, None]))
log('pool hits cached')
R = list(R0); moves = []; it = 0
def state(R, f):
    E = own(R); q99, q75, _ = Q[f]
    h99 = E >= q99[:, None]; h75 = E >= q75[:, None]
    cnt = {c: h99[:, js].sum(1) for c, js in cidx.items()}; c75 = h75.sum(1)
    mask = np.empty((N, S), np.float32); W = np.empty((N, S), np.float32)
    for j in range(N):
        mask[j] = ~((cnt[CID[j]] - h99[:, j]) > 0)
        W[j] = ~((c75 - h75[:, j]) > 0)
    return h99, h75, cnt, c75, mask, W
def cov_counts(R, f):
    st_ = state(R, f); return {c: int((v > 0).sum()) for c, v in st_[2].items()}, int((st_[3] == 0).sum())
near = []
while now() < DEADLINE:
    it += 1
    ST = {f: state(R, f) for f in Q}
    nb = neighbours(R); nbM = own(nb)
    cand_sets = [('pool', pool, None), ('nb', nb, nbM)]
    best = None; best_near = []
    for f in Q: pass
    for src, cands, Mc in cand_sets:
        K = len(cands); step = 4000
        for a in range(0, K, step):
            b = min(K, a + step)
            G = {}; WN = {}
            for f in Q:
                h99, h75, cnt, c75, mask, W = ST[f]
                if Mc is None: A99 = pool_h[f][0][:, a:b].astype(np.float32); A75 = pool_h[f][1][:, a:b].astype(np.float32)
                else: A99, A75 = hits_of(Mc[:, a:b], f)
                base = np.array([mask[j] @ h99[:, j].astype(np.float32) for j in range(N)])
                G[f] = mask @ A99 - base[:, None]
                wo = float((c75 == 0).sum())
                WN[f] = W.sum(1)[:, None] - W @ A75 - wo  # new - old washout count (<=0 good)
            ok = (G['sharp'] >= 0) & (G['uniform'] >= 0) & (WN['sharp'] <= 0) & (WN['uniform'] <= 0) & ((G['sharp'] > 0) | (WN['sharp'] < 0))
            key = G['sharp'] - WN['sharp']
            jj, kk = np.nonzero(ok)
            if len(jj):
                order = np.argsort(-key[jj, kk])[:300]
                for o in order:
                    j, k = int(jj[o]), int(kk[o]); cand = tuple(cands[a + k])
                    newc = byd[cand[0]].underlying_id not in {byd[r[0]].underlying_id for i2, r in enumerate(R) if i2 != j}
                    kv = float(key[j, k]) + (0.5 if newc else 0)
                    if best is not None and kv <= best[0]: break
                    Rn = list(R); Rn[j] = cand
                    if port_check(Rn)[0]: continue
                    best = (kv, 'replace', j, cand, float(G['sharp'][j, k]), float(WN['sharp'][j, k]), float(G['uniform'][j, k]), float(WN['uniform'][j, k]), src)
                    break
            # near misses: high key but failing pareto (only first iteration)
            if it == 1:
                nm_ = (~ok) & (key > 0)
                j2, k2 = np.nonzero(nm_)
                if len(j2):
                    oo = np.argsort(-key[j2, k2])[:50]
                    for o in oo:
                        j, k = int(j2[o]), int(k2[o])
                        near.append((float(key[j, k]), EID[j], src, tuple(cands[a + k]), float(G['sharp'][j, k]), float(WN['sharp'][j, k]), float(G['uniform'][j, k]), float(WN['uniform'][j, k])))
    # (iv) swaps between entries in different contests
    P = {f: ST[f][4] @ ST[f][0].astype(np.float32) for f in Q}  # P[j1,j2] = mask_j1 . h_j2
    for j1 in range(N):
        for j2 in range(j1 + 1, N):
            if CID[j1] == CID[j2]: continue
            g = {f: (P[f][j1, j2] - P[f][j1, j1], P[f][j2, j1] - P[f][j2, j2]) for f in Q}
            if min(g['sharp']) >= 0 and min(g['uniform']) >= 0 and max(g['sharp']) > 0:
                kv = float(sum(g['sharp']))
                if best is None or kv > best[0]:
                    best = (kv, 'swap', j1, j2, g['sharp'], g['uniform'])
    if best is None: log('no passing move at iteration', it); break
    before = {f: cov_counts(R, f) for f in Q}
    if best[1] == 'replace':
        j, cand = best[2], best[3]; out = R[j]; R[j] = cand
        desc = dict(type='replace', entry=EID[j], contest=CID[j], source=best[8], out=[byd[d].name for d in out], out_ids=list(out), into=[byd[d].name for d in cand], in_ids=list(cand))
    else:
        j1, j2 = best[2], best[3]; R[j1], R[j2] = R[j2], R[j1]
        desc = dict(type='swap', entries=[EID[j1], EID[j2]], contests=[CID[j1], CID[j2]], lineups=[[byd[d].name for d in R[j1]], [byd[d].name for d in R[j2]]])
    after = {f: cov_counts(R, f) for f in Q}
    # verify pareto exactly
    for f in Q:
        assert all(after[f][0][c] >= before[f][0][c] for c in contests), ('pareto fail', f)
        assert after[f][1] <= before[f][1]
    desc['measures'] = {f: dict(contest_top1_before={c: before[f][0][c] / S for c in contests if before[f][0][c] != after[f][0][c]},
                                contest_top1_after={c: after[f][0][c] / S for c in contests if before[f][0][c] != after[f][0][c]},
                                washout_q75_before=before[f][1] / S, washout_q75_after=after[f][1] / S) for f in Q}
    moves.append(desc); log('MOVE', it, json.dumps(desc))
log('search ended; moves', len(moves))
# ---------- (c) write csv
raw = open(V3, newline='').read()
rows = list(csv.reader(io.StringIO(raw, newline='')))
buf = io.StringIO(); csv.writer(buf, lineterminator='\r\n').writerows(rows)
roundtrip_identical = buf.getvalue() == raw
emap = dict(zip(EID, R))
nrows = []
for r in rows:
    if r and r[0] in emap and len(r) >= 10:
        r = list(r); r[4:10] = list(emap[r[0]])
    nrows.append(r)
buf = io.StringIO(); csv.writer(buf, lineterminator='\r\n').writerows(nrows)
outcsv = OUT + '/DK_REVIEW_ENTRY_atl-no-sd_qa_iter1.csv'
with open(outcsv, 'x', newline='') as fh: fh.write(buf.getvalue())
sha = hashlib.sha256(open(outcsv, 'rb').read()).hexdigest()
log('wrote', outcsv, sha, 'v3 roundtrip identical', roundtrip_identical)
fin = H.read_file(outcsv); assert [e[0] for e in fin] == EID
bF, stF = port_check([e[2] for e in fin]); log('final constraint check', bF, stF)
def ev(entries, p, f):
    e = H.evaluate(entries, p, f); e.pop('entry_top1'); return e
cmp = {}
for p in ('SELECT', 'REFEREE'):
    for f in ('sharp', 'uniform'):
        try:
            cmp[f'{p}_{f}'] = dict(v3=ev(entries0, p, f), iter1=ev(fin, p, f)); log('EVAL', p, f, json.dumps(cmp[f'{p}_{f}']))
        except Exception as ex:
            cmp[f'{p}_{f}'] = repr(ex); log('EVAL fail', p, f, ex)
ref_worse = {}
for f in ('sharp', 'uniform'):
    d = cmp.get(f'REFEREE_{f}')
    if isinstance(d, dict):
        ref_worse[f] = {c: [d['v3']['contest_top1'][c], d['iter1']['contest_top1'][c]] for c in d['v3']['contest_top1'] if d['iter1']['contest_top1'][c] < d['v3']['contest_top1'][c]}
        ref_worse[f]['washout_q75'] = [d['v3']['washout_q75'], d['iter1']['washout_q75']]
near.sort(reverse=True)
rec = dict(status='DIAGNOSTIC_PRIOR_ONLY_NOT_AN_UPLOAD_AUTHORIZATION', RELEASE_DECISION='DO_NOT_UPLOAD', measure_names=dict(contest_top1='scenario top-1% rate per contest', washout_q75='scenario washout rate (q75)'),
           input=dict(v3=V3, v3_sha256=hashlib.sha256(open(V3, 'rb').read()).hexdigest()), output=dict(path=outcsv, sha256=sha, v3_csv_roundtrip_identical=roundtrip_identical),
           diagnosis=diag, moves=moves, search=dict(iterations=it, deadline=DEADLINE.isoformat(), rule='Pareto on SELECT sharp+uniform; REFEREE report only'),
           near_misses_iter1=[dict(key=n[0], entry=n[1], source=n[2], lineup=[byd[d].name for d in n[3]], gain_sharp=n[4], wash_delta_sharp=n[5], gain_uniform=n[6], wash_delta_uniform=n[7]) for n in near[:10]],
           comparison=cmp, referee_contests_worse=ref_worse, constraints=dict(v3=dict(defects=b0, **st0), iter1=dict(defects=bF, **stF)))
with open(OUT + '/record.json', 'x') as fh: json.dump(rec, fh, indent=1, default=lambda o: o.tolist() if hasattr(o, 'tolist') else str(o))
log('record written')
