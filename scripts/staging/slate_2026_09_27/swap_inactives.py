"""Swap newly inactive players out of the thesis portfolio; boost named replacements.
Construction only: engine scores and exclusions unchanged. Usage:
  swap_inactives.py <new DKSalaries.csv | inactive_ids.txt> <out_portfolio.json> [--boost NAME=OUTNAME ...]
"""
import csv, json, sys, collections
W = '/tmp/claude-0/wk3aux'
OLD = '/tmp/claude-0/wk3in/DKSalaries.csv'
src, outp = sys.argv[1], sys.argv[2]
boost_pairs = [a.split('=', 1) for a in sys.argv[3:] if '=' in a]
old = {r['ID']: r for r in csv.DictReader(open(OLD, encoding='utf-8-sig'))}
UNAV = {'O', 'OUT', 'IR', 'D'}
if src.endswith('.csv'):
    new = {r['ID']: r for r in csv.DictReader(open(src, encoding='utf-8-sig'))}
    assert set(new) == set(old), 'salary file IDs differ: not the same draft group'
    out_ids = {i for i, r in new.items() if r['Status'].upper() in UNAV and old[i]['Status'].upper() not in UNAV}
    changed = {i: (old[i]['Status'], new[i]['Status']) for i in new if new[i]['Status'] != old[i]['Status']}
else:
    out_ids = {l.strip() for l in open(src) if l.strip()}
    changed = {i: (old[i]['Status'], 'OUT') for i in out_ids}
sal = old; nm = lambda i: sal[i]['Name']; pos = lambda i: sal[i]['Position']; team = lambda i: sal[i]['TeamAbbrev']
game = lambda i: sal[i]['Game Info'].split()[0]
def opp(i):
    a, h = game(i).split('@'); return h if team(i) == a else a
S = {k: v for k, v in json.load(open(W + '/pool_scores_gated.json'))['by_dk_id'].items() if v > 0 and k not in out_ids}
byname = {nm(i): i for i in sal}
for rep, gone in boost_pairs:
    r, g = byname.get(rep), byname.get(gone)
    if r in S and g:
        gone_score = json.load(open(W + '/pool_scores_gated.json'))['by_dk_id'].get(g, 0)
        S[r] = max(S[r], 0.7 * gone_score)   # construction heuristic: replacement inherits 70% of the absent player's prior
        print(f'BOOST {rep}: {S[r]:.2f} (absent {gone})')
    else:
        print(f'BOOST_SKIPPED {rep}: not in the engine-selectable pool' if r not in S else f'BOOST_SKIPPED {gone}: unknown')
p = json.load(open(W + '/thesis24v4_portfolio.json'))
A = {e: list(L) for e, L in p['assignments_by_entry_id'].items()}
EXP, OVL, CAP, FLOOR = 7, 5, 50000, 48500
def exp():
    c = collections.Counter(); [c.update(L) for L in A.values()]; return c
def legal(L):
    need = collections.Counter(pos(i) for i in L)
    if len(set(L)) != 9 or need['QB'] != 1 or need['DST'] != 1 or need['RB'] < 2 or need['WR'] < 3 or need['TE'] < 1: return False
    s = sum(int(sal[i]['Salary']) for i in L)
    if s > CAP or s < FLOOR: return False
    d = [i for i in L if pos(i) == 'DST'][0]; q = [i for i in L if pos(i) == 'QB'][0]
    if any(team(i) == opp(d) and pos(i) != 'DST' for i in L) or team(d) == opp(q): return False
    if not any(team(i) == team(q) and pos(i) in ('WR', 'TE') for i in L): return False
    if not any(team(i) == opp(q) and pos(i) != 'DST' for i in L): return False
    return len({game(i) for i in L}) >= 2
def fits(e, L):
    if frozenset(L) in {frozenset(x) for k, x in A.items() if k != e}: return False
    if any(len(set(L) & set(x)) > OVL for k, x in A.items() if k != e): return False
    c = exp(); [c.subtract([i]) for i in A[e]]; c.update(L)
    return all(c[i] <= EXP for i in L)
log = []
for e, L in A.items():
    for gone in [i for i in L if i in out_ids]:
        best = None
        for r in S:
            if r in L or r in out_ids: continue
            if pos(gone) in ('RB', 'WR', 'TE'):
                if pos(r) not in ('RB', 'WR', 'TE'): continue
            elif pos(r) != pos(gone): continue
            M = [r if i == gone else i for i in L]
            if legal(M) and fits(e, M) and (best is None or S[r] > S[best]): best = r
        if best is None:
            # two-player fallback: replacement r for the absent player, plus one non-core flex-eligible player x -> y
            q = [i for i in L if pos(i) == 'QB'][0]
            core = {q, gone} | {i for i in L if team(i) == team(q)}
            top = sorted([i for i in S if pos(i) in ('RB', 'WR', 'TE') and i not in L and i not in out_ids], key=lambda i: -S[i])[:90]
            pair = None
            for r in top[:45]:
                for x in [i for i in L if i not in core and pos(i) in ('RB', 'WR', 'TE')]:
                    for y in top:
                        if y == r: continue
                        M = [r if i == gone else (y if i == x else i) for i in L]
                        gain = S[r] + S[y] - S.get(x, 0)
                        if (pair is None or gain > pair[0]) and legal(M) and fits(e, M): pair = (gain, r, x, y, M)
            if pair is None: log.append(f'NO_LEGAL_SWAP {e}: {nm(gone)}'); continue
            _, r, x, y, M = pair; A[e] = M; L = A[e]
            log.append(f'SWAP2 {e}: {nm(gone)} -> {nm(r)} ({team(r)} {pos(r)}); {nm(x)} -> {nm(y)} ({team(y)} {pos(y)})')
            continue
        A[e] = [best if i == gone else i for i in L]; L = A[e]
        log.append(f'SWAP {e}: {nm(gone)} ({team(gone)} {pos(gone)}) -> {nm(best)} ({team(best)} {pos(best)} ${sal[best]["Salary"]})')
# side 2: work each boosted replacement into lineups where he beats a same-position non-core player
for rep, gone in boost_pairs:
    r = byname.get(rep)
    if r not in S: continue
    for e, L in sorted(A.items(), key=lambda kv: kv[0]):
        if r in L or exp()[r] >= 3: continue
        q = [i for i in L if pos(i) == 'QB'][0]
        core = {q} | {i for i in L if team(i) == team(q)} | {i for i in L if team(i) == opp(q)}
        for x in sorted([i for i in L if i not in core and pos(i) == pos(r)], key=lambda i: S.get(i, 0)):
            M = [r if i == x else i for i in L]
            if S[r] > S.get(x, 0) * 1.15 and legal(M) and fits(e, M):
                A[e] = M; log.append(f'UPGRADE {e}: {nm(x)} -> {rep}'); break
print('status changes vs morning file:', {nm(i): v for i, v in changed.items()})
print('newly unavailable:', sorted(nm(i) for i in out_ids))
print('\n'.join(log) or 'no rostered player affected')
p['assignments_by_entry_id'] = A
p['lineups'] = [{'index': k + 1, 'roster': L} for k, L in enumerate(A.values())]
p.setdefault('construction', {})['inactive_swaps'] = log
json.dump(p, open(outp, 'w'), indent=1)
