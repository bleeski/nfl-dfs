import sys, time, json, csv, collections, hashlib, io, datetime as dt
CON = '/home/user/nfl-dfs/data/inbox/slates/atl-no-sd-2026-10-05/construction'
sys.path.insert(0, CON)
import numpy as np
import scenario_harness as H
H.BETA['very_sharp'] = 3.0
OUT = CON + '/qa_iter2'
V3 = CON + '/DK_REVIEW_ENTRY_atl-no-sd_ceiling_v3.csv'
DEADLINE = dt.datetime(2026, 10, 5, 23, 28, 40, tzinfo=dt.timezone.utc)
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
entries0 = H.read_file(V3)
EID = [e[0] for e in entries0]; CID = [e[1] for e in entries0]; N = len(entries0)
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
    Pp = [people(r) for r in R]
    mo = max(len(Pp[a] & Pp[b]) for a in range(len(R)) for b in range(a+1, len(R)))
    if mo > 5: bad.append('OVERLAP')
    nm = collections.Counter(pname[u] for r in R for u in people(r))
    if nm.get(PITTS, 0) > 6: bad.append('PITTS')
    if nm.get(OLAVE, 0) < 7: bad.append('OLAVE')
    z = sum(nqb(r) == 0 for r in R)
    if z > 3: bad.append('ZERO_QB_ROWS_GT3')
    if len(cc) < 10: bad.append('DISTINCT_CAPTAINS_LT10')
    mp = pc.most_common(1)[0]
    return bad, dict(distinct_captains=len(cc), captain_counts={pname[u]: n for u, n in cc.most_common()}, max_person_count=mp[1],
                     max_persons=[pname[u] for u, n in pc.items() if n == mp[1]], max_overlap=mo, pitts_rows=nm.get(PITTS, 0), olave_rows=nm.get(OLAVE, 0),
                     zero_qb_rows=z, qb_per_row_hist=dict(sorted(collections.Counter(nqb(r) for r in R).items())))
def no_worse(bnew, bold):
    cn, co = collections.Counter(bnew), collections.Counter(bold)
    return all(cn[k] <= co[k] for k in cn)
R0 = [e[2] for e in entries0]
b0, st0 = port_check(R0); log('v3 check', b0, st0)
sims = H.bank('SELECT')
FQ = {f: H.field_quantiles('SELECT', f) for f in FS}; log('fields done', FQ['very_sharp']['field_captain_share'])
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
chk = H.lineup_score_matrix(s, sims, R0); log('own vs harness maxdiff', float(np.abs(own(R0) - chk).max()))
Q = {f: (FQ[f]['q99'], FQ[f]['q75'], FQ[f]['q50']) for f in FS}
pool = H.pool_field(); Mpool = _MC[id(sims)]
psub = [i for i, r in enumerate(pool) if not thesis_row(r)]
poolc = [pool[i] for i in psub]; Mp = Mpool[:, psub]
pool_h = {f: (Mp >= Q[f][0][:, None], Mp >= Q[f][1][:, None]) for f in FS}
log('pool thesis-legal', len(poolc))
# targeted candidates: NO-leaning, low ATL exposure
elig_cpt = {u: d['CPT'] for u, d in role_id.items() if 'CPT' in d}
elig_flex = {u: d['FLEX'] for u, d in role_id.items() if 'FLEX' in d}
TCAP = ['Alvin Kamara', 'Chris Olave', 'Saints', 'Daniel Carlson', 'Juwan Johnson', 'Tyler Shough', 'Kendre Miller', 'Brian Robinson Jr.', 'Kevin Austin Jr.', 'Kyle Pitts Sr.', 'Falcons', 'Nick Folk']
tcap = [u for u in elig_cpt if pname[u] in TCAP]
log('target captains', [pname[u] for u in tcap], 'missing', [n for n in TCAP if n not in {pname[u] for u in tcap}])
fl = list(elig_flex); wfl = np.array([3.0 if pteam[u] == 'NO' else 1.0 for u in fl]); wfl /= wfl.sum()
qb_of = {t: next((u for u in elig_flex if pname[u] == n), None) for t, n in STARTER.items()}
rng = np.random.default_rng(1005); tgt = set(); tries = 0
while len(tgt) < 30000 and tries < 600000:
    tries += 1
    cu = tcap[rng.integers(len(tcap))]; picks = []
    if ppos[cu] in ('WR', 'TE') and qb_of[pteam[cu]]: picks.append(qb_of[pteam[cu]])
    while len(picks) < 5:
        u = fl[rng.choice(len(fl), p=wfl)]
        if u != cu and u not in picks: picks.append(u)
    r = (elig_cpt[cu],) + tuple(elig_flex[u] for u in picks)
    if not legal(r) or thesis_row(r): continue
    if sum(byd[d].salary for d in r) < 44000: continue
    if sum(pteam[byd[d].underlying_id] == 'ATL' for d in r) > 2: continue
    tgt.add((r[0],) + tuple(sorted(r[1:])))
tgt = list(tgt); Mt = own(tgt); tgt_h = {f: (Mt >= Q[f][0][:, None], Mt >= Q[f][1][:, None]) for f in FS}
log('targeted candidates', len(tgt), 'tries', tries)
def meas(R, f):
    E = own(R); q99, q75, q50 = Q[f]; h = E >= q99[:, None]
    return dict(contest_top1={c: float(h[:, js].any(1).mean()) for c, js in cidx.items()}, washout_q75=float((~(E >= q75[:, None]).any(1)).mean()))
# diagnosis of v3 under very_sharp
diag = {}
for f in FS:
    E0 = own(R0); h0 = E0 >= Q[f][0][:, None]
    marg = {}
    for c, js in cidx.items():
        full = h0[:, js].any(1).mean()
        for j in js:
            oth = [k for k in js if k != j]; wo = h0[:, oth].any(1).mean() if oth else 0.0
            marg[EID[j]] = round(float(full - wo), 4)
    diag[f'marginal_{f}'] = marg
log('very_sharp lowest marginals', sorted((v, e) for e, v in diag['marginal_very_sharp'].items())[:8])
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
REDUNDANT = ['5284789377', '5284789385', '5284828440'] + [e for v, e in sorted((v, e) for e, v in diag['marginal_sharp'].items() if e in [EID[j] for j in cidx['196285161']])][:5]
R = list(R0); moves = []; it = 0; near = []; targeted_report = {}
while now() < DEADLINE:
    it += 1
    ST = {f: state(R, f) for f in FS}
    nb = neighbours(R); nbM = own(nb)
    nb_h = {f: (nbM >= Q[f][0][:, None], nbM >= Q[f][1][:, None]) for f in FS}
    base_b, _ = port_check(R)
    curcap = collections.Counter(byd[r[0]].underlying_id for r in R)
    best = None
    for src, cands, HH in (('targeted', tgt, tgt_h), ('pool', poolc, pool_h), ('nb', nb, nb_h)):
        K = len(cands)
        for a in range(0, K, 5000):
            b = min(K, a + 5000); G = {}; WN = {}
            for f in FS:
                h99, h75, cnt, c75, mask, W = ST[f]
                A99 = HH[f][0][:, a:b].astype(np.float32); A75 = HH[f][1][:, a:b].astype(np.float32)
                base = np.einsum('js,sj->j', mask, h99.astype(np.float32))
                G[f] = mask @ A99 - base[:, None]
                WN[f] = W.sum(1)[:, None] - W @ A75 - float((c75 == 0).sum())
            ok = (G['sharp'] >= 0) & (G['very_sharp'] >= 0) & (WN['sharp'] <= 0) & (WN['very_sharp'] <= 0) & ((G['very_sharp'] > 0) | (WN['very_sharp'] < 0))
            key = G['very_sharp'] - WN['very_sharp']
            if it == 1:
                for e in REDUNDANT:
                    j = EID.index(e); kk = int(np.argmax(key[j])); okj = np.nonzero(ok[j])[0]
                    tr = targeted_report.setdefault(e, {})
                    if src == 'targeted':
                        cand = cands[a + kk]
                        if key[j, kk] > tr.get('best_any_key', -1e9):
                            tr.update(best_any_key=float(key[j, kk]), best_any=[byd[d].name for d in cand], best_any_passes=bool(ok[j, kk]),
                                      gain_sharp=float(G['sharp'][j, kk]), gain_very_sharp=float(G['very_sharp'][j, kk]), wash_delta_sharp=float(WN['sharp'][j, kk]), wash_delta_very_sharp=float(WN['very_sharp'][j, kk]))
                        tr['targeted_passing_count'] = tr.get('targeted_passing_count', 0) + int(len(okj))
                nm_ = (~ok) & (key > 0); j2, k2 = np.nonzero(nm_)
                if len(j2):
                    for o in np.argsort(-key[j2, k2])[:30]:
                        j, k = int(j2[o]), int(k2[o])
                        near.append((float(key[j, k]), EID[j], CID[j], src, [byd[d].name for d in cands[a + k]], float(G['sharp'][j, k]), float(WN['sharp'][j, k]), float(G['very_sharp'][j, k]), float(WN['very_sharp'][j, k])))
            jj, kk = np.nonzero(ok)
            if not len(jj): continue
            for o in np.argsort(-key[jj, kk])[:400]:
                j, k = int(jj[o]), int(kk[o]); cand = tuple(cands[a + k])
                cu = byd[cand[0]].underlying_id
                newc = curcap.get(cu, 0) == 0 or (curcap.get(cu, 0) == 1 and byd[R[j][0]].underlying_id == cu and False)
                kv = float(key[j, k]) + (3.0 if (curcap.get(cu, 0) - (1 if byd[R[j][0]].underlying_id == cu else 0)) == 0 else 0)
                if best is not None and kv + 3.0 <= best[0]: break
                if best is not None and kv <= best[0]: continue
                Rn = list(R); Rn[j] = cand
                bn, _ = port_check(Rn)
                if not no_worse(bn, base_b): continue
                best = (kv, 'replace', j, cand, {f: (float(G[f][j, k]), float(WN[f][j, k])) for f in FS}, src)
    Pm = {f: ST[f][4] @ ST[f][0].astype(np.float32) for f in FS}
    for j1 in range(N):
        for j2 in range(j1 + 1, N):
            if CID[j1] == CID[j2]: continue
            g = {f: (Pm[f][j1, j2] - Pm[f][j1, j1], Pm[f][j2, j1] - Pm[f][j2, j2]) for f in FS}
            if min(g['sharp']) >= 0 and min(g['very_sharp']) >= 0 and max(g['very_sharp']) > 0:
                kv = float(sum(g['very_sharp']))
                if best is None or kv > best[0]: best = (kv, 'swap', j1, j2)
    if best is None: log('no passing move at iteration', it); break
    before = {f: cov_counts(R, f) for f in FS}
    if best[1] == 'replace':
        j, cand = best[2], best[3]; out = R[j]; R[j] = cand
        desc = dict(type='replace', entry=EID[j], contest=CID[j], source=best[5], out=[byd[d].name for d in out], out_ids=list(out), into=[byd[d].name for d in cand], in_ids=list(cand), touched=[CID[j]])
    else:
        j1, j2 = best[2], best[3]; R[j1], R[j2] = R[j2], R[j1]
        desc = dict(type='swap', entries=[EID[j1], EID[j2]], contests=[CID[j1], CID[j2]], touched=[CID[j1], CID[j2]])
    after = {f: cov_counts(R, f) for f in FS}
    for f in FS:
        assert all(after[f][0][c] >= before[f][0][c] for c in contests), ('pareto fail', f); assert after[f][1] <= before[f][1]
    desc['measures'] = {f: dict(changed={c: [before[f][0][c] / S, after[f][0][c] / S] for c in contests if before[f][0][c] != after[f][0][c]},
                                washout_q75=[before[f][1] / S, after[f][1] / S]) for f in FS}
    desc['R_after'] = None
    moves.append(desc); log('MOVE', it, json.dumps({k: v for k, v in desc.items() if k not in ('out_ids', 'in_ids', 'R_after')}))
log('search ended; moves', len(moves))
def ev(R_, p, f):
    ent = [(EID[j], CID[j], R_[j]) for j in range(N)]; e = H.evaluate(ent, p, f); e.pop('entry_top1'); return e
cmp = {}
for f in FS: cmp[f'SELECT_{f}'] = dict(v3=ev(R0, 'SELECT', f), iter2=ev(R, 'SELECT', f))
reverts = []
for f in FS:
    cmp[f'REFEREE_{f}'] = dict(v3=ev(R0, 'REFEREE', f), iter2=ev(R, 'REFEREE', f)); log('REF', f, 'done')
worse = sorted({c for f in FS for c in contests if cmp[f'REFEREE_{f}']['iter2']['contest_top1'][c] < cmp[f'REFEREE_{f}']['v3']['contest_top1'][c]})
wash_worse = [f for f in FS if cmp[f'REFEREE_{f}']['iter2']['washout_q75'] > cmp[f'REFEREE_{f}']['v3']['washout_q75']]
log('REFEREE worse contests', worse, 'washout worse', wash_worse)
R_pre_revert = list(R)
if worse:
    tc = set(worse)
    for m in moves:
        if tc & set(m['touched']): tc |= set(m['touched'])
    for j in range(N):
        if CID[j] in tc and R[j] != R0[j]: R[j] = R0[j]; reverts.append(EID[j])
    log('reverted entries', reverts, 'contests', sorted(tc), 'check', port_check(R)[0])
    for f in FS:
        cmp[f'SELECT_{f}']['iter2'] = ev(R, 'SELECT', f); cmp[f'REFEREE_{f}']['iter2'] = ev(R, 'REFEREE', f)
bF, stF = port_check(R)
log('final check', bF, stF)
raw = open(V3, newline='').read(); rows = list(csv.reader(io.StringIO(raw, newline='')))
buf = io.StringIO(); csv.writer(buf, lineterminator='\r\n').writerows(rows); rt = buf.getvalue() == raw
emap = dict(zip(EID, R)); nrows = []
for r in rows:
    if r and r[0] in emap and len(r) >= 10: r = list(r); r[4:10] = list(emap[r[0]])
    nrows.append(r)
buf = io.StringIO(); csv.writer(buf, lineterminator='\r\n').writerows(nrows)
outcsv = OUT + '/DK_REVIEW_ENTRY_atl-no-sd_qa_iter2.csv'
with open(outcsv, 'x', newline='') as fh: fh.write(buf.getvalue())
sha = hashlib.sha256(open(outcsv, 'rb').read()).hexdigest(); log('wrote', outcsv, sha, 'roundtrip', rt)
for k, d in cmp.items(): log('CMP', k, json.dumps({x: {kk: d[x][kk] for kk in ('contest_top1', 'mean_entry_top1', 'portfolio_any_top1', 'washout_q75', 'washout_q50')} for x in ('v3', 'iter2')}))
# remaining washout scenarios
remw = {}
names = ['Tyler Shough', 'Michael Penix Jr.', 'Bijan Robinson', 'Drake London', 'Chris Olave', 'Juwan Johnson', 'Alvin Kamara']
team_pts = collections.defaultdict(lambda: np.zeros(S))
for u, i in pidx.items():
    if u in pteam: team_pts[pteam[u]] += O[:, i]
for f in FS:
    E = own(R); w = ~(E >= Q[f][1][:, None]).any(1)
    d = dict(rate=float(w.mean()), n=int(w.sum()))
    if w.sum():
        d['team_points'] = {t: [round(float(v[w].mean()), 1), round(float(v.mean()), 1)] for t, v in team_pts.items()}
        for nm in names:
            u = next(u for u in pname if pname[u] == nm and u in pidx); x = O[:, pidx[u]]; pct = x.argsort().argsort() / (S - 1)
            d[nm] = round(float(pct[w].mean()), 3)
    remw[f] = d
log('remaining washout', json.dumps(remw))
near.sort(reverse=True)
rec = dict(status='DIAGNOSTIC_PRIOR_ONLY_NOT_AN_UPLOAD_AUTHORIZATION', RELEASE_DECISION='DO_NOT_UPLOAD',
           rule='Pareto on SELECT bank, sharp (1.5) and very_sharp (3.0): no contest_top1 down, washout_q75 not up on both, strict gain on very_sharp; REFEREE report-only with revert of moves touching worse contests',
           input=dict(v3=V3, v3_sha256=hashlib.sha256(open(V3, 'rb').read()).hexdigest()), output=dict(path=outcsv, sha256=sha, v3_csv_roundtrip_identical=rt),
           v3_checks=dict(defects=b0, **st0), final_checks=dict(defects=bF, **stF), diagnosis=diag, targeted_candidates=len(tgt), pool_thesis_legal=len(poolc),
           redundant_entry_targeted_test=targeted_report, moves=moves, referee_worse_contests=worse, referee_washout_worse=wash_worse, reverted_entries=reverts,
           comparison=cmp, remaining_washout=remw, near_misses=[dict(key=n[0], entry=n[1], contest=n[2], source=n[3], lineup=n[4], gain_sharp=n[5], wash_delta_sharp=n[6], gain_very_sharp=n[7], wash_delta_very_sharp=n[8]) for n in near[:10]],
           search=dict(iterations=it, deadline=DEADLINE.isoformat()))
with open(OUT + '/record.json', 'x') as fh: json.dump(rec, fh, indent=1, default=lambda o: o.tolist() if hasattr(o, 'tolist') else str(o))
log('record written')
