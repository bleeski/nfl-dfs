import csv, json, sys, itertools
from collections import defaultdict, Counter
sal_p, sc_p, f = sys.argv[1:4]
SAL = {r['ID']: r for r in csv.DictReader(open(sal_p, encoding='utf-8-sig'))}
SC = json.load(open(sc_p))['by_dk_id']
raw = list(csv.reader(open(f, encoding='utf-8-sig')))
rows = {}; con = {}
for r in raw[1:]:
    if r and r[0].strip().isdigit() and all(c.strip() for c in r[4:10]):
        rows[r[0]] = r[4:10]; con[r[0]] = r[2]
nm = lambda d: SAL[d]['Name']
def cm(ids_list):
    sets = [frozenset(nm(d) for d in ids) for ids in ids_list]
    ov = [len(a & b) for a, b in itertools.combinations(sets, 2)] or [0]
    caps = Counter(nm(i[0]) for i in ids_list)
    return (max(ov), round(sum(ov)/len(ov), 4), max(caps.values()))
by = defaultdict(list)
for e, c in con.items(): by[c].append(e)
single = [e for e in rows if con[e] == '196537744'][0]
s0 = sum(SC.get(d, 0) or 0 for d in rows[single])
print('single', single, round(s0, 2), nm(rows[single][0]))
for e in rows:
    if e == single: continue
    c = con[e]
    L = rows[e]
    if SAL[L[0]]['Position'] in ('K', 'DST'): continue
    s1 = sum(SC.get(d, 0) or 0 for d in L)
    if s1 <= s0: continue
    before = cm([rows[x] for x in by[c]])
    after = cm([rows[single] if x == e else rows[x] for x in by[c]])
    ok = all(a <= b for a, b in zip(after, before))
    print(e, c, round(s1, 2), 'CPT', nm(L[0]), [nm(d) for d in L[1:]], 'contest(maxov,meanov,maxcap) before', before, 'after', after, 'OK' if ok else 'worse')
