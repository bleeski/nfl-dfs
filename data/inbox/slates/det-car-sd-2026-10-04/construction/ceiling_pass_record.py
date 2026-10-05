"""Large-prize pass (Ben 2026-10-04: err toward large prizes when they conflict with washouts).
Phase 1: every WR/TE Captain row holds its own team's starting QB (min prior loss swap).
Phase 2: greedy FLEX swaps that raise the row prior by >= 1.0, washout allowed to worsen within: person <= 21/28 (0.75),
pair overlap <= 4, Captains untouched, phase-1 QBs kept, Tremayne kept, distinct lineups (R29). Prior points order swaps only."""
import csv, json, sys, itertools, collections, hashlib
SL='/home/user/nfl-dfs/data/inbox/slates/det-car-sd-2026-10-04'
SRC=SL+'/construction/DK_REVIEW_ENTRY_det-car-sd_final_v3.csv'; OUT=SL+'/construction/DK_REVIEW_ENTRY_det-car-sd_final_v4.csv'
sal={r['ID']:r for r in csv.DictReader(open(SL+'/input/DKSalaries.csv',encoding='utf-8-sig'))}
sc=json.load(open(SL+'/construction/pool_scores.json')); score=sc['by_dk_id']; excl=set(sc['excluded_dk_ids'])
key=lambda i:(sal[i]['Name'],sal[i]['TeamAbbrev'])
flex={key(i):i for i in sal if sal[i]['Roster Position']=='FLEX' and i not in excl}
STARTER={'DET':flex[('Jared Goff','DET')],'CAR':flex[('Bryce Young','CAR')]}
CAP=21; HAND='Brycen Tremayne'
raw=list(csv.reader(open(SRC,newline=''))); hdr=raw[0]
rows=[r for r in raw[1:] if r and r[0].strip().isdigit()]
P=lambda r:[key(x) for x in r[4:10]]
pts=lambda r:sum(score.get(x,0) for x in r[4:10])
salary=lambda r:sum(int(sal[x]['Salary']) for x in r[4:10])
sig=lambda r:(P(r)[0],tuple(sorted(P(r)[1:])))
def needs_qb(r):
    c=r[4]; return sal[c]['Position'] in ('WR','TE')
def own_qb(r): return STARTER[sal[r[4]]['TeamAbbrev']]
def metrics(rows):
    cnt=collections.Counter(p for r in rows for p in set(P(r))); cpt=collections.Counter(P(r)[0] for r in rows)
    ov=[len(set(P(a))&set(P(b))) for a,b in itertools.combinations(rows,2)]
    top3=[p for p,_ in cnt.most_common(3)]
    return dict(prior_total=round(sum(pts(r) for r in rows),2),prior_min=round(min(pts(r) for r in rows),2),max_exposure=max(cnt.values()),
      max_captain=max(cpt.values()),distinct_captains=len(cpt),distinct_people=len(cnt),mean_pair_overlap=round(sum(ov)/len(ov),4),
      max_pair_overlap=max(ov),top3_union=sum(1 for r in rows if set(P(r))&set(top3)),
      passcatcher_cpt_without_own_qb=sum(1 for r in rows if needs_qb(r) and own_qb(r) not in r[4:10]),
      zero_qb_rows=sum(1 for r in rows if not any(sal[x]['Position']=='QB' for x in r[4:10])),
      two_kicker_rows=sum(1 for r in rows if sum(sal[x]['Position']=='K' for x in r[4:10])==2),
      exposure={k[0]:v for k,v in cnt.most_common(10)})
def ok(trial,ri,cap,maxov=4):
    nr=trial[ri]
    if salary(nr)>50000: return False
    if any(sig(b)==sig(nr) for j,b in enumerate(trial) if j!=ri): return False
    if max(len(set(P(nr))&set(P(b))) for j,b in enumerate(trial) if j!=ri)>maxov: return False
    cnt=collections.Counter(p for r in trial for p in set(P(r)))
    return max(cnt.values())<=cap
before=metrics(rows); log=[]
# Phase 1
for ri,r in enumerate(rows):
    if not needs_qb(r) or own_qb(r) in r[4:10]: continue
    q=own_qb(r); best=None
    for s in range(5,10):
        o=r[s]
        if sal[o]['Name']==HAND: continue
        nr=list(r); nr[s]=q; t=rows[:ri]+[nr]+rows[ri+1:]
        if ok(t,ri,CAP) and (best is None or pts(nr)>best[0]): best=(pts(nr),s,o)
    if best:
        _,s,o=best; log.append(dict(phase=1,entry_id=r[0],captain=sal[r[4]]['Name'],out=sal[o]['Name'],incoming=sal[q]['Name'],prior_change=round(score.get(q,0)-score.get(o,0),2)))
        r[s]=q
    else: log.append(dict(phase=1,entry_id=r[0],captain=sal[r[4]]['Name'],result='NO_FEASIBLE_SWAP'))
# Phase 2
protected=lambda r,s: sal[r[s]]['Name']==HAND or (needs_qb(r) and r[s]==own_qb(r))
while True:
    best=None
    for ri,r in enumerate(rows):
        for s in range(5,10):
            o=r[s]
            if protected(r,s): continue
            for pk,pid in flex.items():
                if pk in P(r): continue
                g=score.get(pid,0)-score.get(o,0)
                if g<1.0: continue
                nr=list(r); nr[s]=pid; t=rows[:ri]+[nr]+rows[ri+1:]
                if not ok(t,ri,CAP): continue
                if best is None or g>best[0]: best=(g,ri,s,o,pid)
    if not best: break
    g,ri,s,o,pid=best; log.append(dict(phase=2,entry_id=rows[ri][0],captain=sal[rows[ri][4]]['Name'],out=sal[o]['Name'],incoming=sal[pid]['Name'],prior_change=round(g,2))); rows[ri][s]=pid
# Phase 3: retry phase 1 after phase 2, allowing pair overlap 5 (still distinct) for the stack
for ri,r in enumerate(rows):
    if not needs_qb(r) or own_qb(r) in r[4:10]: continue
    q=own_qb(r); best=None
    for mo in (4,5):
        for s_ in range(5,10):
            o=r[s_]
            if sal[o]['Name']==HAND: continue
            nr=list(r); nr[s_]=q; t=rows[:ri]+[nr]+rows[ri+1:]
            if ok(t,ri,CAP,mo) and (best is None or pts(nr)>best[0]): best=(pts(nr),s_,o,mo)
        if best: break
    if best:
        _,s_,o,mo=best; log.append(dict(phase=3,entry_id=r[0],captain=sal[r[4]]['Name'],out=sal[o]['Name'],incoming=sal[q]['Name'],prior_change=round(score.get(q,0)-score.get(o,0),2),max_overlap_used=mo)); r[s_]=q
    else: log.append(dict(phase=3,entry_id=r[0],captain=sal[r[4]]['Name'],result='NO_FEASIBLE_SWAP_EVEN_AT_OVERLAP_5'))
after=metrics(rows)
print('BEFORE',json.dumps(before)); print('AFTER ',json.dumps(after))
for l in log: print(json.dumps(l))
if '--write' in sys.argv:
    byid={r[0]:r for r in rows}
    with open(OUT,'x',newline='') as f: csv.writer(f,lineterminator='\r\n').writerows([byid.get(r[0],r) if r and r[0].strip().isdigit() else r for r in raw])
    json.dump(dict(ruling='Ben 2026-10-04: err on the side of large prizes when at odds with minimizing washouts',rules=__doc__,before=before,after=after,moves=log,
      source_sha256=hashlib.sha256(open(SRC,'rb').read()).hexdigest(),out_sha256=hashlib.sha256(open(OUT,'rb').read()).hexdigest()),open(OUT.replace('.csv','_record.json'),'x'),indent=1)
    print('WROTE',OUT)
