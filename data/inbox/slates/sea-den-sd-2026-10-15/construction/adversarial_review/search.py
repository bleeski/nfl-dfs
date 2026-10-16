import sys, copy
sys.path.insert(0, '/tmp/claude-0/-home-user-nfl-dfs/2bcf0cfe-60b8-5dd0-86f4-7e62c57ce802/scratchpad/review')
from lib import *
path = sys.argv[1]
lines, rows = load(path)
m0, cnt0, cpt0, con0 = measures(rows)
flex = [x for x in P if P[x]['slot'] == 'FLEX' and x in PR and x not in EXC and P[x]['status'] in ('', 'Q') and P[x]['name'] not in BANNED]
res = []
for ri, r in enumerate(rows):
    for si in range(1, 6):
        for x in flex:
            if P[x]['name'] in ppl(r['ids']): continue
            new = list(r['ids']); new[si] = x
            if check_row(new): continue
            rr = copy.deepcopy(rows); rr[ri]['ids'] = new
            if full_check(rr): continue
            m, cnt, cpt, con = measures(rr)
            if m['maxp'] > m0['maxp'] or m['maxnonqb'] > m0['maxnonqb'] or m['top3'] > m0['top3'] or m['meanov'] > m0['meanov'] + 1e-9 or m['distinct'] < m0['distinct']: continue
            if any(con[c][1] < con0[c][1] or con[c][2] > con0[c][2] for c in con): continue
            d = rowprior(new) - rowprior(r['ids'])
            strict = (m['top3'] < m0['top3'] or m['meanov'] < m0['meanov'] - 1e-9 or m['distinct'] > m0['distinct'] or m['maxp'] < m0['maxp'] or any(con[c][2] < con0[c][2] for c in con))
            if d < -1e-9 and not strict: continue
            if d <= 1e-9 and not strict: continue
            res.append((round(d, 2), strict, r['eid'], r['cid'], P[r['ids'][si]]['name'], r['ids'][si], P[x]['name'], x, m['top3'], m['meanov'], m['distinct'], round(rowprior(new), 1)))
res.sort(key=lambda t: -t[0])
for t in res[:60]: print(t)
print(len(res))
