import csv, json, sys, itertools
from collections import defaultdict, Counter
sal_p, sc_p = sys.argv[1:3]; files = sys.argv[3:]
SAL = {r['ID']: r for r in csv.DictReader(open(sal_p, encoding='utf-8-sig'))}
SC = json.load(open(sc_p))['by_dk_id']
nm = lambda d: SAL[d]['Name']
def load(f):
    rows, con = {}, {}
    for r in list(csv.reader(open(f, encoding='utf-8-sig')))[1:]:
        if r and r[0].strip().isdigit() and all(c.strip() for c in r[4:10]):
            rows[r[0]] = r[4:10]; con[r[0]] = r[2]
    return rows, con
def cm(L):
    sets = [frozenset(nm(d) for d in ids) for ids in L]
    ov = [len(a & b) for a, b in itertools.combinations(sets, 2)] or [0]
    caps = Counter(nm(i[0]) for i in L); ppl = Counter(n for s in sets for n in s)
    return dict(n=len(L), maxov=max(ov), pairs5=sum(1 for o in ov if o >= 5), meanov=round(sum(ov)/len(ov), 3), maxcap=max(caps.values()),
                distinct_caps=len(caps), maxperson=ppl.most_common(1)[0], prior=round(sum(sum(SC.get(d,0) or 0 for d in i) for i in L), 2))
for f in files:
    rows, con = load(f); by = defaultdict(list)
    for e, c in con.items(): by[c].append(rows[e])
    print(f.split('/')[-1])
    for c in sorted(by): print(' ', c, cm(by[c]))
