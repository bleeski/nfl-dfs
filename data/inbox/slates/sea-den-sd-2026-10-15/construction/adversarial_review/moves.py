import sys, copy
sys.path.insert(0, '/tmp/claude-0/-home-user-nfl-dfs/2bcf0cfe-60b8-5dd0-86f4-7e62c57ce802/scratchpad/review')
from lib import *
lines, rows = load(sys.argv[1])
BOOST = '196781421'
m0, cnt0, cpt0, con0 = measures(rows)
for i, a in enumerate(rows):
    if a['cid'] != BOOST: continue
    for j, b in enumerate(rows):
        if b['cid'] == BOOST: continue
        rr = copy.deepcopy(rows); rr[i]['ids'], rr[j]['ids'] = rr[j]['ids'], rr[i]['ids']
        m, cnt, cpt, con = measures(rr)
        if any(con[c][1] < con0[c][1] or con[c][2] > con0[c][2] for c in con): continue
        d = con[BOOST][3] - con0[BOOST][3]
        if d > 0: print(round(d, 2), a['eid'], b['eid'], b['cid'], 'boost cpts', con[BOOST][1], 'other', con[b['cid']])
