"""Work Case Keenum (FLEX 44282409) into N lineups of a filled Showdown file by one FLEX swap each.

Operator-directed (Ben, 2026-09-28: assume Keenum starts; he wants Keenum rostered).
Keenum has no prior, so he adds 0 prior points; the removed player is the lowest-scored
FLEX (never the Captain, never a CHI WR/TE, never Hurts outside the CHI-upset thesis) whose
removal keeps salary <= 50000. Deterministic. Writes a new path; byte-exact cell edits.
"""
import csv, json, sys, itertools
sal_path, entries, theses_path, scores_path, n_target, out = sys.argv[1:7]
KEENUM = '44282409'
sal = {}
for r in csv.DictReader(open(sal_path, encoding='utf-8-sig')):
    sal[r['ID']] = dict(name=r['Name'], team=r['TeamAbbrev'], pos=r['Position'], salary=int(r['Salary']))
th = json.load(open(theses_path)); sc = json.load(open(scores_path))['by_dk_id']
L = open(entries, 'rb').read().split(b'\r\n')
rows = {}
for i, l in enumerate(L):
    f = l.split(b',')
    if f[0].decode().isdigit() and all(f[4:10]):
        rows[f[0].decode()] = dict(line=i, ids=[x.decode() for x in f[4:10]])
def people(ids): return frozenset(sal[i]['name'] for i in ids)
def options(eid):
    ids = rows[eid]['ids']; t = th[eid]
    if t not in ('S2', 'S3', 'S4'): return []
    if not any(sal[i]['team'] == 'CHI' and sal[i]['pos'] in ('WR', 'TE') for i in ids): return []
    total = sum(sal[i]['salary'] for i in ids); out = []
    for k in range(1, 6):
        x = sal[ids[k]]
        if x['team'] == 'CHI' and x['pos'] in ('WR', 'TE'): continue
        if x['name'] == 'Jalen Hurts' and t != 'S4': continue
        if total - x['salary'] + sal[KEENUM]['salary'] > 50000: continue
        new = ids[:k] + [KEENUM] + ids[k + 1:]
        if len({sal[i]['team'] for i in new}) < 2: continue  # DraftKings: both teams
        out.append((sc.get(ids[k], 0.0), k, x['name'], new))
    return sorted(out)
order = {'S4': 0, 'S3': 1, 'S2': 2}
cands = []
for eid in rows:
    o = options(eid)
    if o: cands.append((order[th[eid]], o[0][0], eid, o))
cands.sort()
chosen = {}
current = {e: list(r['ids']) for e, r in rows.items()}
for _, _, eid, opts in cands:
    if len(chosen) >= int(n_target): break
    for loss, k, name, new in opts:
        others = [people(v) for e, v in current.items() if e != eid]
        keys = {tuple(v) for e, v in current.items() if e != eid}
        if tuple(new) in keys: continue
        if any(len(people(new) & p) > 5 for p in others): continue
        chosen[eid] = dict(thesis=th[eid], removed=name, lost_prior_points=round(loss, 3)); current[eid] = new; break
for eid, c in chosen.items():
    f = L[rows[eid]['line']].split(b','); f[4:10] = [x.encode() for x in current[eid]]; L[rows[eid]['line']] = b','.join(f)
open(out, 'xb').write(b'\r\n'.join(L))
print(json.dumps({'feasible_candidates': len(cands), 'chosen': chosen}, indent=1))
