import json,csv,sys,copy
from collections import Counter
src,out,add_name,target=sys.argv[1],sys.argv[2],sys.argv[3],int(sys.argv[4])
sal={r['ID']:r for r in csv.DictReader(open('data/inbox/slates/wk4-classic-2026-10-04/DKSalaries.csv',encoding='utf-8-sig'))}
sc=json.load(open('outputs/wk4-classic-2026-10-04-thesis/scores_r3_qbclean.json'))['by_dk_id']
d=json.load(open(src)); A=d['assignments_by_entry_id']
add=[k for k,r in sal.items() if r['Name']==add_name][0]; pos=sal[add]['Position']; team=sal[add]['TeamAbbrev']
game=sal[add]['Game Info'].split(' ')[0]
def qb(l): return [x for x in l if sal[x]['Position']=='QB'][0]
def gm(x): return sal[x]['Game Info'].split(' ')[0]
log=[]
# prefer rows whose QB is in the added player's game (natural bring-back), then the rest by lowest-scored replaceable
order=sorted(A, key=lambda e:(gm(qb(A[e]))!=game, e))
expo=Counter(x for l in A.values() for x in l)
for e in order:
    if sum(1 for l in A.values() if add in l)>=target: break
    l=A[e]
    if add in l: continue
    q=qb(l); qt=sal[q]['TeamAbbrev']; qg=gm(q)
    if team!=qt and any(sal[x]['TeamAbbrev']==team and sal[x]['Position']=='DST' for x in l): pass
    # never add against own DST
    opp_dst=[x for x in l if sal[x]['Position']=='DST']
    if opp_dst and gm(opp_dst[0])==game and sal[opp_dst[0]]['TeamAbbrev']!=team: continue
    cands=[x for x in l if sal[x]['Position']==pos and sal[x]['TeamAbbrev']!=qt and not (gm(x)==qg and sum(1 for y in l if gm(y)==qg and sal[y]['TeamAbbrev']!=qt and sal[y]['Position']!='DST')==1)]
    cands.sort(key=lambda x:sc.get(x,0))
    used=sum(int(sal[x]['Salary']) for x in l)
    for c in cands:
        if used-int(sal[c]['Salary'])+int(sal[add]['Salary'])>50000: continue
        trial=[add if x==c else x for x in l]
        keys={tuple(sorted(v)) for k,v in A.items() if k!=e}
        if tuple(sorted(trial)) in keys: continue
        if max(len(set(trial)&set(v)) for k,v in A.items() if k!=e)>5: continue
        A[e]=trial; log.append(f"MANUAL_ADD {e}: {sal[c]['Name']} ({sal[c]['Salary']}) -> {add_name} ({sal[add]['Salary']}), QB {sal[q]['Name']}"); break
for i,lu in enumerate(d['lineups']):
    pass
# rebuild lineups list from assignments in the same order
eids=list(A.keys())
new=[]
for n,(e) in enumerate(eids):
    old=d['lineups'][n]
    r=A[e]; new.append(dict(old, roster=r, salary=sum(int(sal[x]['Salary']) for x in r), prior_points=round(sum(sc.get(x,0) for x in r),3)))
d['lineups']=new
d.setdefault('construction',{}).setdefault('manual_adds',[]).extend(log)
json.dump(d,open(out,'x'),indent=1)
print('\n'.join(log)); print('exposure now',sum(1 for l in A.values() if add in l))
