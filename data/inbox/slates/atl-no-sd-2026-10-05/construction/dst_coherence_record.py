"""ATL@NO game-script coherence (large-prize rule: every row needs one script where all six hit together).
A DST is never in a row with the opposing starting QB: the Falcons DST beside Shough (often with Olave, Johnson or Kamara, sometimes as
Captain) roots against its own row. Each such DST is replaced by the best-prior legal FLEX that is not a kicker (no second kicker), not
Pitts (the ceiling pass's research cap) and not the row's opposing DST; person cap 27 of 36, overlap 5, distinct lineups (R29).
Prior points only order the choice; nothing is written as a projection."""
import csv, json, sys, itertools, collections, hashlib
SL='/home/user/nfl-dfs/data/inbox/slates/atl-no-sd-2026-10-05'
SRC=SL+'/construction/DK_REVIEW_ENTRY_atl-no-sd_ceiling_v2.csv'; OUT=SL+'/construction/DK_REVIEW_ENTRY_atl-no-sd_ceiling_v3.csv'
sal={r['ID']:r for r in csv.DictReader(open(SL+'/input/DKSalaries_143.csv',encoding='utf-8-sig'))}
sc=json.load(open(SL+'/construction/pool_scores.json')); score=sc['by_dk_id']; excl=set(sc['excluded_dk_ids'])
cannot=set(open(SL+'/construction/cannot_play_dk_ids.txt').read().strip().split(','))
key=lambda i:(sal[i]['Name'],sal[i]['TeamAbbrev'])
BACKUP_QB={'Tua Tagovailoa','Spencer Rattler','Cooper Rush','Jack Strand','Zach Wilson'}
flex={key(i):i for i in sal if sal[i]['Roster Position']=='FLEX' and i not in excl and i not in cannot
      and sal[i]['Name'] not in BACKUP_QB and i in score}
STARTER={'ATL':('Michael Penix Jr.','ATL'),'NO':('Tyler Shough','NO')}
OPP={'ATL':'NO','NO':'ATL'}; PITTS=('Kyle Pitts Sr.','ATL'); CAP=27; MAXOV=5
raw=list(csv.reader(open(SRC,newline=''))); rows=[r for r in raw[1:] if r and r[0].strip().isdigit() and r[4].strip()]
P=lambda r:[key(x) for x in r[4:10]]
pts=lambda r:sum(score.get(x,0) for x in r[4:10])
salary=lambda r:sum(int(sal[x]['Salary']) for x in r[4:10])
sig=lambda r:(P(r)[0],tuple(sorted(P(r)[1:])))
kickers=lambda r:sum(sal[x]['Position']=='K' for x in r[4:10])
def bad_dst_slots(r):
    return [s for s in range(4,10) if sal[r[s]]['Position']=='DST' and STARTER[OPP[sal[r[s]]['TeamAbbrev']]] in P(r)]
def metrics(rows):
    cnt=collections.Counter(p for r in rows for p in set(P(r))); cpt=collections.Counter(P(r)[0] for r in rows)
    ov=[len(set(P(a))&set(P(b))) for a,b in itertools.combinations(rows,2)]
    return dict(prior_total=round(sum(pts(r) for r in rows),2),prior_min=round(min(pts(r) for r in rows),2),max_exposure=max(cnt.values()),
      max_captain=max(cpt.values()),distinct_captains=len(cpt),distinct_people=len(cnt),mean_pair_overlap=round(sum(ov)/len(ov),4),
      max_pair_overlap=max(ov),pairs_overlap_5=sum(o>=5 for o in ov),dst_with_opposing_qb=sum(bool(bad_dst_slots(r)) for r in rows),
      two_kicker_rows=sum(kickers(r)>1 for r in rows),salary_min=min(salary(r) for r in rows),
      exposure={k[0]:v for k,v in cnt.most_common()},captains={k[0]:v for k,v in cpt.most_common()})
def ok(trial,ri):
    nr=trial[ri]
    if salary(nr)>50000 or len(set(P(nr)))!=6 or kickers(nr)>1: return False
    if len({sal[x]['TeamAbbrev'] for x in nr[4:10]})<2: return False
    if any(sig(b)==sig(nr) for j,b in enumerate(trial) if j!=ri): return False
    if max(len(set(P(nr))&set(P(b))) for j,b in enumerate(trial) if j!=ri)>MAXOV: return False
    return max(collections.Counter(p for r in trial for p in set(P(r))).values())<=CAP
before=metrics(rows); log=[]
for ri,r in enumerate(rows):
    for s in bad_dst_slots(r):
        if s==4: log.append(dict(entry_id=r[0],result='DST_IS_CAPTAIN_LEFT_FOR_REVIEW')); continue
        o=r[s]; best=None
        for pk,pid in flex.items():
            if pk==PITTS or pk in P(r) or sal[pid]['Position'] in ('K','DST'): continue
            nr=list(r); nr[s]=pid; t=rows[:ri]+[nr]+rows[ri+1:]
            if ok(t,ri) and (best is None or pts(nr)>best[0]): best=(pts(nr),pid)
        if best:
            log.append(dict(entry_id=r[0],captain=sal[r[4]]['Name'],out=sal[o]['Name'],incoming=sal[best[1]]['Name'],prior_change=round(score.get(best[1],0)-score.get(o,0),2)))
            r[s]=best[1]
        else: log.append(dict(entry_id=r[0],captain=sal[r[4]]['Name'],result='NO_FEASIBLE_SWAP'))
after=metrics(rows)
print('BEFORE',json.dumps(before)); print('AFTER ',json.dumps(after))
for l in log: print(json.dumps(l))
if '--write' in sys.argv:
    byid={r[0]:r for r in rows}
    with open(OUT,'x',newline='') as f: csv.writer(f,lineterminator='\r\n').writerows([byid.get(r[0],r) if r and r[0].strip().isdigit() else r for r in raw])
    json.dump(dict(rules=__doc__,before=before,after=after,moves=log,source_sha256=hashlib.sha256(open(SRC,'rb').read()).hexdigest(),
      out_sha256=hashlib.sha256(open(OUT,'rb').read()).hexdigest()),open(OUT.replace('.csv','_record.json'),'x'),indent=1)
    print('WROTE',OUT)
