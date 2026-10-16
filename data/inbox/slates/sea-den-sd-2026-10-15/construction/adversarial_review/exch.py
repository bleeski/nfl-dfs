import sys, copy
sys.path.insert(0, '/tmp/claude-0/-home-user-nfl-dfs/2bcf0cfe-60b8-5dd0-86f4-7e62c57ce802/scratchpad/review')
from lib import *
lines, rows = load(sys.argv[1])
m0, cnt0, cpt0, con0 = measures(rows)
out = []
for i in range(len(rows)):
    for j in range(i + 1, len(rows)):
        a, b = rows[i], rows[j]
        na, nb = set(ppl(a['ids'])), set(ppl(b['ids']))
        for si in range(1, 6):
            x = a['ids'][si]
            if P[x]['name'] in nb: continue
            for sj in range(1, 6):
                y = b['ids'][sj]
                if P[y]['name'] in na: continue
                A = list(a['ids']); A[si] = y; Bn = list(b['ids']); Bn[sj] = x
                if check_row(A) or check_row(Bn): continue
                rr = copy.deepcopy(rows); rr[i]['ids'] = A; rr[j]['ids'] = Bn
                if full_check(rr): continue
                m, cnt, cpt, con = measures(rr)
                if m['meanov'] > m0['meanov'] + 1e-9 or m['minrow'] < m0['minrow'] - 1e-9: continue
                if any(con[c][1] < con0[c][1] or con[c][2] > con0[c][2] for c in con): continue
                d = m['total'] - m0['total']
                strict = m['meanov'] < m0['meanov'] - 1e-9 or any(con[c][2] < con0[c][2] for c in con)
                if d > 1e-6 or (strict and d >= -1e-6):
                    out.append((round(d, 2), strict, m['meanov'], a['eid'], a['cid'], P[x]['name'], x, '->', P[y]['name'], y, '|', b['eid'], b['cid'], round(rowprior(a['ids']), 1), round(rowprior(A), 1), round(rowprior(b['ids']), 1), round(rowprior(Bn), 1)))
out.sort(key=lambda t: (-t[1], -t[0]))
for t in out[:25]: print(t)
print(len(out))
