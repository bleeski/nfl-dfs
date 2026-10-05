"""ATL@NO large-prize pass (Ben 2026-10-04: err toward large prizes when they conflict with washouts).
Phase 0 (research judgment, no number written): Kyle Pitts Sr. to at most 6 rows. His prior (10.32) is the prior season's per-game
rate; PFF has him at 2 catches in 3 games under the new staff's 13 personnel (Woerner 43 snaps, Pitts 42 in Week 3). His one Captain
row stays (a low-owned ceiling bet); FLEX rows lose him where the best legal replacement costs the least prior. He is never incoming.
Phase 1: every WR/TE Captain row holds its own team's starting QB (Penix ATL, Shough NO; depth package + official depth charts).
Phase 2: greedy FLEX swaps that raise the row prior by >= 1.0; person <= 27/36 (0.75), pair overlap <= 5, Captains untouched,
phase-1 QBs kept, distinct lineups (R29). Prior points order swaps only.
Phase 3: retry phase 1 after phase 2.
Kickers: no swap may raise a row's kicker count above one; phase 4 replaces the lower-prior FLEX kicker in every two-kicker row with
the best legal non-kicker (any prior change), because a second kicker adds little ceiling. Olave: never outgoing in phases 2 and 4
(research: 27 catches, 375 yards in four games; his prior of 11.66 is the prior season's rate and understates the current role)."""
import csv, json, sys, itertools, collections, hashlib
SL='/home/user/nfl-dfs/data/inbox/slates/atl-no-sd-2026-10-05'
SRC='/home/user/nfl-dfs/outputs/20261005T225913Z-atl-no-sd-r3/review/DK_REVIEW_ENTRY_atl-no-sd-r3.csv'
OUT=SL+'/construction/DK_REVIEW_ENTRY_atl-no-sd_ceiling_v1.csv'
sal={r['ID']:r for r in csv.DictReader(open(SL+'/input/DKSalaries_143.csv',encoding='utf-8-sig'))}
sc=json.load(open(SL+'/construction/pool_scores.json')); score=sc['by_dk_id']; excl=set(sc['excluded_dk_ids'])
cannot=set(open(SL+'/construction/cannot_play_dk_ids.txt').read().strip().split(','))
key=lambda i:(sal[i]['Name'],sal[i]['TeamAbbrev'])
BACKUP_QB={'Tua Tagovailoa','Spencer Rattler','Cooper Rush','Jack Strand','Zach Wilson'}
flex={key(i):i for i in sal if sal[i]['Roster Position']=='FLEX' and i not in excl and i not in cannot
      and sal[i]['Name'] not in BACKUP_QB and i in score}
STARTER={'ATL':flex[('Michael Penix Jr.','ATL')],'NO':flex[('Tyler Shough','NO')]}
PITTS=('Kyle Pitts Sr.','ATL'); PITTS_MAX=6
N=36; CAP=27; MAXOV=5
raw=list(csv.reader(open(SRC,newline=''))); hdr=raw[0]
rows=[r for r in raw[1:] if r and r[0].strip().isdigit() and r[4].strip()]
assert len(rows)==N
P=lambda r:[key(x) for x in r[4:10]]
pts=lambda r:sum(score.get(x,0) for x in r[4:10])
salary=lambda r:sum(int(sal[x]['Salary']) for x in r[4:10])
sig=lambda r:(P(r)[0],tuple(sorted(P(r)[1:])))
needs_qb=lambda r: sal[r[4]]['Position'] in ('WR','TE')
own_qb=lambda r: STARTER[sal[r[4]]['TeamAbbrev']]
def metrics(rows):
    cnt=collections.Counter(p for r in rows for p in set(P(r))); cpt=collections.Counter(P(r)[0] for r in rows)
    ov=[len(set(P(a))&set(P(b))) for a,b in itertools.combinations(rows,2)]
    top3=[p for p,_ in cnt.most_common(3)]
    return dict(prior_total=round(sum(pts(r) for r in rows),2),prior_min=round(min(pts(r) for r in rows),2),
      max_exposure=max(cnt.values()),max_captain=max(cpt.values()),distinct_captains=len(cpt),distinct_people=len(cnt),
      mean_pair_overlap=round(sum(ov)/len(ov),4),max_pair_overlap=max(ov),pairs_overlap_5=sum(o>=5 for o in ov),
      top3_union=sum(1 for r in rows if set(P(r))&set(top3)),
      passcatcher_cpt_without_own_qb=sum(1 for r in rows if needs_qb(r) and own_qb(r) not in r[4:10]),
      zero_qb_rows=sum(1 for r in rows if not any(sal[x]['Position']=='QB' for x in r[4:10])),
      two_kicker_rows=sum(1 for r in rows if sum(sal[x]['Position']=='K' for x in r[4:10])==2),
      salary_min=min(salary(r) for r in rows),pitts_rows=cnt.get(PITTS,0),
      exposure={k[0]:v for k,v in cnt.most_common()},captains={k[0]:v for k,v in cpt.most_common()})
kickers=lambda r: sum(sal[x]['Position']=='K' for x in r[4:10])
OLAVE=('Chris Olave','NO')
def ok(trial,ri,cap=CAP,maxov=MAXOV):
    nr=trial[ri]
    if salary(nr)>50000 or len(set(P(nr)))!=6: return False
    if kickers(nr)>1 and kickers(nr)>kickers(rows[ri]): return False
    if len({sal[x]['TeamAbbrev'] for x in nr[4:10]})<2: return False
    if any(sig(b)==sig(nr) for j,b in enumerate(trial) if j!=ri): return False
    if max(len(set(P(nr))&set(P(b))) for j,b in enumerate(trial) if j!=ri)>maxov: return False
    cnt=collections.Counter(p for r in trial for p in set(P(r)))
    return max(cnt.values())<=cap
before=metrics(rows); log=[]
# Phase 0: Pitts down to PITTS_MAX rows, FLEX only, least prior loss first
while collections.Counter(p for r in rows for p in set(P(r)))[PITTS]>PITTS_MAX:
    best=None
    for ri,r in enumerate(rows):
        for s in range(5,10):
            if key(r[s])!=PITTS: continue
            for pk,pid in flex.items():
                if pk==PITTS or pk in P(r): continue
                nr=list(r); nr[s]=pid; t=rows[:ri]+[nr]+rows[ri+1:]
                if not ok(t,ri): continue
                loss=score.get(r[s],0)-score.get(pid,0)
                if best is None or loss<best[0]: best=(loss,ri,s,pid)
    if not best: log.append(dict(phase=0,result='NO_FEASIBLE_PITTS_REMOVAL')); break
    loss,ri,s,pid=best
    log.append(dict(phase=0,entry_id=rows[ri][0],captain=sal[rows[ri][4]]['Name'],out='Kyle Pitts Sr.',incoming=sal[pid]['Name'],prior_change=round(-loss,2)))
    rows[ri][s]=pid
def qb_fix(phase,maxovs):
    for ri,r in enumerate(rows):
        if not needs_qb(r) or own_qb(r) in r[4:10]: continue
        q=own_qb(r); best=None
        for mo in maxovs:
            for s in range(5,10):
                if key(r[s])==OLAVE: continue
                nr=list(r); nr[s]=q; t=rows[:ri]+[nr]+rows[ri+1:]
                if ok(t,ri,CAP,mo) and (best is None or pts(nr)>best[0]): best=(pts(nr),s,r[s])
            if best: break
        if best:
            _,s,o=best; log.append(dict(phase=phase,entry_id=r[0],captain=sal[r[4]]['Name'],out=sal[o]['Name'],incoming=sal[q]['Name'],prior_change=round(score.get(q,0)-score.get(o,0),2)))
            r[s]=q
        else: log.append(dict(phase=phase,entry_id=r[0],captain=sal[r[4]]['Name'],result='NO_FEASIBLE_SWAP'))
qb_fix(1,(4,5))
protected=lambda r,s: (needs_qb(r) and r[s]==own_qb(r)) or key(r[s])==OLAVE
while True:
    best=None
    for ri,r in enumerate(rows):
        for s in range(5,10):
            o=r[s]
            if protected(r,s): continue
            for pk,pid in flex.items():
                if pk==PITTS or pk in P(r): continue
                g=score.get(pid,0)-score.get(o,0)
                if g<1.0: continue
                nr=list(r); nr[s]=pid; t=rows[:ri]+[nr]+rows[ri+1:]
                if not ok(t,ri): continue
                if best is None or g>best[0]: best=(g,ri,s,o,pid)
    if not best: break
    g,ri,s,o,pid=best; log.append(dict(phase=2,entry_id=rows[ri][0],captain=sal[rows[ri][4]]['Name'],out=sal[o]['Name'],incoming=sal[pid]['Name'],prior_change=round(g,2))); rows[ri][s]=pid
qb_fix(3,(5,))
# Phase 3b: a pass-catcher Captain still without his QB because the QB is at the person cap. Free one copy from a donor row whose
# Captain does not need him (min prior loss, never Pitts, never a second kicker), then place him; both rows checked as usual.
for ri,r in enumerate(rows):
    if not needs_qb(r) or own_qb(r) in r[4:10]: continue
    q=own_qb(r); best=None
    for di,d in enumerate(rows):
        if di==ri or q not in d[5:10] or (needs_qb(d) and own_qb(d)==q): continue
        ds=d.index(q,5)
        for pk,pid in flex.items():
            if pk==PITTS or pk in P(d): continue
            nd=list(d); nd[ds]=pid; t=rows[:di]+[nd]+rows[di+1:]
            if not ok(t,di): continue
            for s in range(5,10):
                if key(r[s])==OLAVE: continue
                nr=list(r); nr[s]=q; t2=list(t); t2[ri]=nr
                if not ok(t2,ri): continue
                loss=(pts(d)-pts(nd))+(pts(r)-pts(nr))
                if best is None or loss<best[0]: best=(loss,di,ds,pid,s)
    if best:
        loss,di,ds,pid,s=best; d=rows[di]
        log.append(dict(phase='3b',entry_id=d[0],captain=sal[d[4]]['Name'],out=sal[q]['Name'],incoming=sal[pid]['Name'],prior_change=round(score.get(pid,0)-score.get(q,0),2)))
        log.append(dict(phase='3b',entry_id=r[0],captain=sal[r[4]]['Name'],out=sal[r[s]]['Name'],incoming=sal[q]['Name'],prior_change=round(score.get(q,0)-score.get(r[s],0),2)))
        d[ds]=pid; r[s]=q
    else: log.append(dict(phase='3b',entry_id=r[0],captain=sal[r[4]]['Name'],result='NO_FEASIBLE_DONOR'))
for ri,r in enumerate(rows):
    if kickers(r)<2: continue
    ks=sorted((score.get(r[s],0),s) for s in range(5,10) if sal[r[s]]['Position']=='K')
    s=ks[0][1]; o=r[s]; best=None
    for pk,pid in flex.items():
        if pk==PITTS or pk in P(r) or sal[pid]['Position']=='K': continue
        nr=list(r); nr[s]=pid; t=rows[:ri]+[nr]+rows[ri+1:]
        if ok(t,ri) and (best is None or pts(nr)>best[0]): best=(pts(nr),pid)
    if best:
        log.append(dict(phase=4,entry_id=r[0],captain=sal[r[4]]['Name'],out=sal[o]['Name'],incoming=sal[best[1]]['Name'],prior_change=round(score.get(best[1],0)-score.get(o,0),2))); r[s]=best[1]
    else: log.append(dict(phase=4,entry_id=r[0],captain=sal[r[4]]['Name'],result='NO_FEASIBLE_SWAP'))
after=metrics(rows)
print('BEFORE',json.dumps(before)); print('AFTER ',json.dumps(after))
for l in log: print(json.dumps(l))
if '--write' in sys.argv:
    byid={r[0]:r for r in rows}
    with open(OUT,'x',newline='') as f: csv.writer(f,lineterminator='\r\n').writerows([byid.get(r[0],r) if r and r[0].strip().isdigit() else r for r in raw])
    json.dump(dict(ruling='Ben 2026-10-04: err on the side of large prizes when at odds with minimizing washouts',rules=__doc__,before=before,after=after,moves=log,
      source_sha256=hashlib.sha256(open(SRC,'rb').read()).hexdigest(),out_sha256=hashlib.sha256(open(OUT,'rb').read()).hexdigest()),open(OUT.replace('.csv','_record.json'),'x'),indent=1)
    print('WROTE',OUT)
