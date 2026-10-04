import json,csv,sys
from collections import Counter
src,out=sys.argv[1],sys.argv[2]
protect={'Braelon Allen','Zach Ertz','Jauan Jennings','Emanuel Wilson'}
sal={r['ID']:r for r in csv.DictReader(open('data/inbox/slates/wk4-classic-2026-10-04/DKSalaries.csv',encoding='utf-8-sig'))}
sc=json.load(open('data/inbox/slates/wk4-classic-2026-10-04/construction/scores_qbclean.json'))['by_dk_id']
d=json.load(open(src));A=d['assignments_by_entry_id']
gm=lambda x:sal[x]['Game Info'].split(' ')[0]
log=[]
for e,l in A.items():
    while True:
        used=sum(int(sal[x]['Salary']) for x in l)
        if used>=49500: break
        q=[x for x in l if sal[x]['Position']=='QB'][0]
        expo=Counter(x for v in A.values() for x in v)
        best=None
        for cur in l:
            r=sal[cur]
            if r['Position'] in('QB','DST') or r['Name'] in protect or gm(cur)==gm(q): continue
            for k,c in sal.items():
                if k in l or k not in sc or c['Status'] in('OUT','IR') or c['Position']!=r['Position']: continue
                if gm(k)==gm(q): continue
                dst=[x for x in l if sal[x]['Position']=='DST'][0]
                if gm(k)==gm(dst) and c['TeamAbbrev']!=sal[dst]['TeamAbbrev']: continue
                if used-int(r['Salary'])+int(c['Salary'])>50000 or expo[k]>expo[cur]-2 or (c["Status"] not in ("",)) : continue
                trial=[k if x==cur else x for x in l]
                if tuple(sorted(trial)) in {tuple(sorted(v)) for kk,v in A.items() if kk!=e}: continue
                if max(len(set(trial)&set(v)) for kk,v in A.items() if kk!=e)>5: continue
                gain=sc[k]-sc.get(cur,0)
                if gain>0 and (best is None or gain>best[0]): best=(gain,cur,k,trial)
        if not best: break
        A[e]=l=best[3]; log.append(f"UPGRADE {e}: {sal[best[1]]['Name']} -> {sal[best[2]]['Name']} (+${int(sal[best[2]]['Salary'])-int(sal[best[1]]['Salary'])})")
for n,(e) in enumerate(A):
    r=A[e]; d['lineups'][n]=dict(d['lineups'][n],roster=r,salary=sum(int(sal[x]['Salary']) for x in r),prior_points=round(sum(sc.get(x,0) for x in r),3))
d['construction'].setdefault('manual_adds',[]).extend(log)
json.dump(d,open(out,'x'),indent=1); print('\n'.join(log) or 'no upgrade')
