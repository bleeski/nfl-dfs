"""Adversarial Pareto pass over a filled Showdown file. Prior points only order and gate swaps; nothing is written as a projection."""
import csv, json, sys, itertools, collections
SAL='/home/user/nfl-dfs/data/inbox/slates/det-car-sd-2026-10-04/input/DKSalaries.csv'
SC='/tmp/claude-0/-home-user-nfl-dfs/83ce60f1-d2e1-5278-9529-e58178f0fe2e/scratchpad/det-car-sd/pool_scores.json'
src=sys.argv[1]; out=sys.argv[2] if len(sys.argv)>2 else None
sal={r['ID']:r for r in csv.DictReader(open(SAL,encoding='utf-8-sig'))}
sc=json.load(open(SC)); score=sc['by_dk_id']; excl=set(sc['excluded_dk_ids'])
key=lambda i:(sal[i]['Name'],sal[i]['TeamAbbrev'])
flex_id={key(i):i for i in sal if sal[i]['Roster Position']=='FLEX'}
HAND={'Brycen Tremayne'}
raw=list(csv.reader(open(src))); hdr=raw[0]
rows=[r for r in raw[1:] if r and r[0].strip().isdigit()]
def people(r): return [key(x.strip()) for x in r[4:10]]
def pts(r): return sum(score.get(x.strip(),0.0) for x in r[4:10])
def salary(r): return sum(int(sal[x.strip()]['Salary']) for x in r[4:10])
def metrics(rows):
    cnt=collections.Counter(p for r in rows for p in set(people(r)))
    cpt=collections.Counter(people(r)[0] for r in rows)
    ov=[len(set(people(a))&set(people(b))) for a,b in itertools.combinations(rows,2)]
    top3=[p for p,_ in cnt.most_common(3)]
    return dict(rows=len(rows),distinct_lineups=len({tuple([people(r)[0]]+sorted(people(r)[1:])) for r in rows}),
        prior_total=round(sum(pts(r) for r in rows),2),prior_min=round(min(pts(r) for r in rows),2),
        max_exposure=max(cnt.values()),max_captain=max(cpt.values()),distinct_captains=len(cpt),
        distinct_people=len(cnt),mean_pair_overlap=round(sum(ov)/len(ov),4),max_pair_overlap=max(ov),
        top3_union=sum(1 for r in rows if set(people(r))&set(top3)),unused_salary=sum(50000-salary(r) for r in rows))
before=metrics(rows); print('BEFORE',json.dumps(before))
swaps=[]
while True:
    cnt=collections.Counter(p for r in rows for p in set(people(r)))
    best=None
    for ri,r in enumerate(rows):
        pr=people(r)
        for slot in range(5,10):
            o=r[slot].strip(); ok=key(o)
            if sal[o]['Position']=='QB' or ok[0] in HAND: continue
            for pk,pid in flex_id.items():
                if pid in excl or pk in pr: continue
                if sal[pid]['Position']=='QB': continue
                gain=score.get(pid,0)-score.get(o,0)
                if gain<=1e-9: continue
                if salary(r)-int(sal[o]['Salary'])+int(sal[pid]['Salary'])>50000: continue
                if cnt[pk]>cnt[ok]-2: continue  # incoming used at least 2 fewer times: overlap down, max and distinct no worse
                nr=list(r); nr[slot]=pid
                trial=rows[:ri]+[nr]+rows[ri+1:]
                if max(len(set(people(nr))&set(people(b))) for j,b in enumerate(trial) if j!=ri)>4: continue
                sig=tuple([people(nr)[0]]+sorted(people(nr)[1:]))
                if any(tuple([people(b)[0]]+sorted(people(b)[1:]))==sig for j,b in enumerate(trial) if j!=ri): continue
                if best is None or gain>best[0]: best=(gain,ri,slot,o,pid)
    if not best: break
    g,ri,slot,o,pid=best; rows[ri][slot]=pid
    swaps.append(dict(entry_id=rows[ri][0],slot=hdr[slot],out=sal[o]['Name'],out_score=round(score.get(o,0),3),incoming=sal[pid]['Name'],in_score=round(score.get(pid,0),3),gain=round(g,3),salary_after=salary(rows[ri])))
after=metrics(rows); print('AFTER ',json.dumps(after))
for s in swaps: print('SWAP',json.dumps(s))
worse=[k for k in ('max_exposure','max_captain','mean_pair_overlap','max_pair_overlap','top3_union') if after[k]>before[k]]+[k for k in ('distinct_people','distinct_captains','distinct_lineups','prior_total') if after[k]<before[k]]
print('WORSE_MEASURES',worse)
if out and swaps:
    with open(out,'x',newline='') as f:
        w=csv.writer(f,lineterminator='\n'); byid={r[0]:r for r in rows}
        for r in raw:
            w.writerow(byid.get(r[0],r) if r and r[0].strip().isdigit() else r)
    json.dump(dict(tool='adversarial_pareto_pass',rule='FLEX swap; incoming count <= outgoing count - 2; prior up; CPT, QBs, Tremayne untouched; overlap<=4; distinct',before=before,after=after,swaps=swaps),open(out.replace('.csv','.json'),'x'),indent=1)
