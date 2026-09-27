"""Thesis portfolio: construction only. Engine scores and exclusions unchanged."""
import csv, json, subprocess, sys, collections, itertools
W = '/tmp/claude-0/wk3aux'; T = W + '/theses/v4'
import os; os.makedirs(T, exist_ok=False)
PY = '/home/user/nfl-dfs/.venv-linux/bin/python'; B = '/home/user/nfl-dfs/scripts/build_classic_portfolio.py'
SAL = '/tmp/claude-0/wk3in/DKSalaries.csv'; ENT = '/tmp/claude-0/wk3in/DKEntries.csv'
FREE = "5272123785"; EXP_CAP, OVL_CAP = 7, 5
sal = {r['ID']: r for r in csv.DictReader(open(SAL, encoding='utf-8-sig'))}
base = json.load(open(W + '/pool_scores_gated.json'))
S = {k: v for k, v in base['by_dk_id'].items() if v > 0}
team = lambda i: sal[i]['TeamAbbrev']; pos = lambda i: sal[i]['Position']; nm = lambda i: sal[i]['Name']
# market totals from Ben's ESPN/DraftKings odds PDF (sha 6b7ad115...), current columns
MKT = {'CAR':22.0,'CLE':19.5,'CIN':23.0,'PIT':19.5,'HOU':22.0,'IND':20.5,'KC':27.75,'MIA':17.75,
       'BUF':28.75,'LAC':21.75,'DET':27.5,'NYJ':21.0,'SEA':24.5,'WAS':16.0,'NYG':20.0,'TEN':17.5,
       'JAX':24.75,'NE':21.75,'SF':28.0,'ARI':20.5,'MIN':22.0,'TB':20.5,'BAL':28.25,'DAL':25.25,'NO':23.5,'LV':20.0}
STORM = {'TEN','NYG','SEA','WAS'}; STORM2 = {'CIN','PIT'}
INDOOR = {'DET','NYJ','LV','NO','BAL','DAL','HOU','IND'}
def boosts(fn):
    return {nm(i): m for i in S for m in [fn(i)] if m != 1.0}
def storm_tilt(i):
    t, p = team(i), pos(i)
    if t in STORM: return {'QB':.80,'WR':.80,'TE':.80,'RB':1.05,'DST':1.15}[p]
    if t in STORM2 and p in ('QB','WR','TE'): return .92
    return 1.0
def storm_proof(i):
    t, p = team(i), pos(i)
    if t in STORM: return {'QB':.6,'WR':.6,'TE':.6,'RB':1.3,'DST':1.5}[p]
    return 1.0
def qbs_only(teams, scores):
    return {k: v for k, v in scores.items() if pos(k) != 'QB' or team(k) in teams}
flip = dict(MKT);
for a, b in [('LAC','BUF'),('ARI','SF'),('NE','JAX'),('PIT','CIN')]: flip[a], flip[b] = MKT[b], MKT[a]
bust = dict(MKT); bust.update({'SEA':27.0,'WAS':23.0,'NYG':24.0,'TEN':23.0})
flat = {k: 22.5 for k in MKT}
THESES = [
  ('CORE_MARKET_STORM_TILT', 8, S, MKT, boosts(storm_tilt)),
  ('STORM_PROOF_INDOOR_STACKS', 4, {k: v for k, v in qbs_only(INDOOR, S).items() if pos(k) != 'DST' or team(k) in STORM}, MKT, boosts(storm_proof)),
  ('STORM_BUST_SHOOTOUT', 4, qbs_only(STORM, S), bust, {}),
  ('UNDERDOG_FLIP', 4, qbs_only({'LAC','ARI','NE','PIT'}, S), flip, {}),
]
def run(name, n, scores, itt, bst, seed, k):
    sp, cp, op = f'{T}/{name}_{seed}_scores.json', f'{T}/{name}_{seed}_ctx.json', f'{T}/{name}_{seed}_out.json'
    json.dump({'by_dk_id': scores}, open(sp, 'w'))
    json.dump({'implied_team_totals': itt, 'projected_ownership': {}, 'role_boosts': bst}, open(cp, 'w'))
    r = subprocess.run([PY, B, '--scores', sp, '--salaries', SAL, '--status', W + '/official_status_empty.csv',
        '--slate-context', cp, '--lineups', str(k), '--out', op, '--max-exposure', str(max(3, k * 2 // 5)),
        '--max-overlap', '5', '--require-bringback', '--min-salary', '48500', '--seed', str(seed)],
        capture_output=True, text=True)
    if r.returncode not in (0, 3): print('BUILDER', name, seed, r.returncode, r.stderr[-400:]); return []
    try: return [l['roster'] for l in json.load(open(op))['lineups']]
    except Exception: print(name, seed, r.stdout[-300:], r.stderr[-300:]); return []
cands = collections.defaultdict(list)
for name, n, scores, itt, bst in THESES:
    for seed in (11, 23, 37):
        for L in run(name, n, scores, itt, bst, seed, n * 3):
            cands[name].append(L)
# thesis 5: priors wrong -> DraftKings salary as the value, flat totals, fade the heaviest names so far
heavy = collections.Counter(i for Ls in cands.values() for L in Ls for i in L)
fade = {i for i, _ in heavy.most_common(12) if pos(i) != 'DST'}
S5 = {i: float(sal[i]['Salary']) / 1000.0 for i in S if i not in fade}
THESES.append(('PRIORS_WRONG_SALARY_FLAT', 4, S5, flat, {}))
for seed in (11, 23, 37):
    cands['PRIORS_WRONG_SALARY_FLAT'] += run('PRIORS_WRONG_SALARY_FLAT', 4, S5, flat, {}, seed, 12)
# global greedy: round robin by thesis, best base-model prior first, caps across the whole file
val = lambda L: sum(S.get(i, 0) for i in L)
quota = {t[0]: t[1] for t in THESES}
pools = {t: sorted({frozenset(L): L for L in Ls}.values(), key=val, reverse=True) for t, Ls in cands.items()}
chosen, tags, exp = [], [], collections.Counter()
qbof = lambda L: [i for i in L if pos(i) == 'QB'][0]
def ok(L, t=None):
    if t and sum(1 for x, g in zip(chosen, tags) if g == t and qbof(x) == qbof(L)) >= 2: return False
    if frozenset(L) in {frozenset(x) for x in chosen}: return False
    if any(exp[i] + 1 > EXP_CAP for i in L): return False
    return all(len(set(L) & set(x)) <= OVL_CAP for x in chosen)
progress = True
while progress and len(chosen) < 24:
    progress = False
    for t in quota:
        if sum(1 for g in tags if g == t) >= quota[t]: continue
        for L in pools.get(t, []):
            if ok(L, t):
                chosen.append(L); tags.append(t); exp.update(L); progress = True; break
print('candidates', {t: len(v) for t, v in pools.items()})
print('chosen', collections.Counter(tags), len(chosen))
rows = list(csv.reader(open(ENT, encoding='utf-8-sig')))
order = [r[0] for r in rows[1:] if r and r[0].strip().isdigit() and r[0] != FREE]
out = {'lineups': [{'index': k + 1, 'roster': L, 'thesis': g, 'salary': sum(int(sal[i]['Salary']) for i in L),
                    'prior_points': round(val(L), 3)} for k, (L, g) in enumerate(zip(chosen, tags))],
       'assignments_by_entry_id': dict(zip(order, chosen)), 'unfilled_entry_ids': [FREE],
       'operator_excluded_entry_ids': {FREE: 'NFL FREE 200-Player (196114372): Ben, 2026-09-27'},
       'construction': {'theses': {t[0]: t[1] for t in THESES}, 'faded_in_priors_wrong': sorted(nm(i) for i in fade),
                        'max_exposure': EXP_CAP, 'max_overlap': OVL_CAP, 'odds_source_pdf_sha256': '6b7ad1150bce5893bf25e7379a76f5a794e8c548259eca6e1daf020f989ee692'}}
json.dump(out, open(W + '/thesis24v4_portfolio.json', 'w'), indent=1)
print('faded', out['construction']['faded_in_priors_wrong'])
