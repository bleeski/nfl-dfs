import csv, json, itertools, sys
from collections import Counter, defaultdict
B = '/home/user/nfl-dfs/data/inbox/slates/sea-den-sd-2026-10-15/'
SAL = B + 'input/DKSalaries.csv'
CUR = B + 'construction/DK_REVIEW_ENTRY_sea-den-sd_final_v2.csv'
J = json.load(open(B + 'construction/pool_scores_sea-den-sd-1015-r2.json'))
PR = {k: float(v) for k, v in J['by_dk_id'].items()}
EXC = set(J['excluded_dk_ids'])
P = {}
for r in csv.DictReader(open(SAL, newline='', encoding='utf-8-sig')):
    P[r['ID']] = dict(pos=r['Position'], name=r['Name'], slot=r['Roster Position'], sal=int(r['Salary']), team=r['TeamAbbrev'], status=r['Status'])
QB = {'SEA': 'Sam Darnold', 'DEN': 'Bo Nix'}
BANNED = {'Drew Lock', 'Jarrett Stidham'}
def load(path):
    raw = open(path, 'rb').read()
    lines = raw.split(b'\r\n')
    rows = []
    for i, ln in enumerate(lines):
        if i == 0 or not ln: continue
        c = ln.decode('utf-8').split(',')
        if c[0] and c[0].isdigit() and len(c) > 9 and c[4]:
            rows.append(dict(i=i, eid=c[0], cid=c[2], ids=c[4:10]))
    return lines, rows
def ppl(ids): return [P[x]['name'] for x in ids]
def rowprior(ids): return sum(PR.get(x, 0) for x in ids)
def check_row(ids):
    errs = []
    if ids[0] not in P or P[ids[0]]['slot'] != 'CPT': errs.append('cpt slot')
    for x in ids[1:]:
        if x not in P or P[x]['slot'] != 'FLEX': errs.append('flex slot ' + x)
    for x in ids:
        if x not in PR: errs.append('noprior ' + x)
        if x in EXC: errs.append('excluded ' + x)
        if P[x]['status'] not in ('', 'Q'): errs.append('status ' + x)
        if P[x]['name'] in BANNED: errs.append('backup qb')
    if sum(P[x]['sal'] for x in ids) > 50000: errs.append('salary')
    n = ppl(ids)
    if len(set(n)) != 6: errs.append('dup person')
    teams = set(P[x]['team'] for x in ids)
    if len(teams) != 2: errs.append('one team')
    c = P[ids[0]]
    if c['pos'] in ('WR', 'TE') and QB[c['team']] not in n: errs.append('WR/TE cpt without QB')
    for x in ids:
        if P[x]['pos'] == 'DST':
            opp = [t for t in QB if t != P[x]['team']][0]
            if QB[opp] in n: errs.append('DST vs opp QB')
    if c['pos'] == 'DST':
        opp = [x for x in ids if P[x]['team'] != c['team']]
        if len(opp) > 1 or any(P[x]['pos'] not in ('RB', 'K') for x in opp): errs.append('DST cpt opp')
    return errs
def measures(rows):
    cnt = Counter(); cpt = Counter()
    for r in rows:
        for n in ppl(r['ids']): cnt[n] += 1
        cpt[P[r['ids'][0]]['name']] += 1
    pairs = list(itertools.combinations(rows, 2))
    ov = [len(set(ppl(a['ids'])) & set(ppl(b['ids']))) for a, b in pairs]
    pri = [rowprior(r['ids']) for r in rows]
    nonqb = [v for k, v in cnt.items() if k not in QB.values()]
    m = dict(total=round(sum(pri), 3), minrow=round(min(pri), 3), maxp=max(cnt.values()), maxnonqb=max(nonqb),
             top3=sum(sorted(cnt.values(), reverse=True)[:3]), meanov=round(sum(ov) / len(ov), 4), maxov=max(ov),
             distinct=len(cnt))
    bycon = defaultdict(list)
    for r in rows: bycon[r['cid']].append(r)
    con = {}
    for c, rs in bycon.items():
        cp = len(set(P[r['ids'][0]]['name'] for r in rs))
        wp = max([len(set(ppl(a['ids'])) & set(ppl(b['ids']))) for a, b in itertools.combinations(rs, 2)] or [0])
        con[c] = (len(rs), cp, wp, round(sum(rowprior(r['ids']) for r in rs), 2))
    return m, cnt, cpt, con
def full_check(rows):
    errs = []
    for r in rows:
        e = check_row(r['ids'])
        if e: errs.append((r['eid'], e))
    keys = [(r['ids'][0], frozenset(r['ids'][1:])) for r in rows]
    if len(set(keys)) != len(keys): errs.append('duplicate lineup')
    m, cnt, cpt, con = measures(rows)
    if m['maxov'] > 5: errs.append('overlap>5')
    if max(cpt.values()) > 5: errs.append('cpt>5')
    for k, v in cnt.items():
        if k in QB.values() and v > 21: errs.append('qb>21 ' + k)
        if k not in QB.values() and v > 17: errs.append('>17 ' + k)
    return errs
