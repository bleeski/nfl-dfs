import json,csv,sys,re,html,itertools
from collections import Counter
D='data/inbox/slates/wk4-classic-2026-10-04'
src,out,inact,target=sys.argv[1],sys.argv[2],sys.argv[3],int(sys.argv[4])
sal={r['ID']:r for r in csv.DictReader(open(f'{D}/DKSalaries.csv',encoding='utf-8-sig'))}
sc=json.load(open(f'{D}/construction/scores_qbclean.json'))['by_dk_id']
t=open(inact,encoding='utf-8',errors='ignore').read()
t=re.sub(r'<script.*?</script>|<style.*?</style>','',t,flags=re.S)
x=html.unescape(re.sub(r'<[^>]+>','|',t)); x=re.sub(r'\|\s*\|+','|',x); x=re.sub(r'\s+',' ',x)
inactive=set(m.group(1).strip() for m in re.finditer(r'\|([A-Z][A-Za-z\.\'\- ]+?) \((?:QB|RB|WR|TE|K|P|S|CB|LB|DT|DE|OL|OT|OG|G|C|DL|EDGE|OLB|ILB|NT|FB|LS|DB)\)',x))
protect={'Braelon Allen','Zach Ertz','Jauan Jennings','Emanuel Wilson'}
d=json.load(open(src));A=d['assignments_by_entry_id']
gm=lambda i:sal[i]['Game Info'].split(' ')[0]
unlocked=lambda i:'04:25PM' in sal[i]['Game Info']
def qb(l): return [i for i in l if sal[i]['Position']=='QB'][0]
def dst(l): return [i for i in l if sal[i]['Position']=='DST'][0]
def metrics(A):
    c=Counter(i for l in A.values() for i in l); L=list(A.values())
    top3=[k for k,_ in c.most_common(3)]
    union=sum(1 for l in L if any(k in l for k in top3))
    pairs=list(itertools.combinations(L,2)); mo=sum(len(set(a)&set(b)) for a,b in pairs)/len(pairs)
    return dict(maxe=max(c.values()),top3=union,mo=mo,distinct=len(c))
def no_worse(m,b): return m['maxe']<=b['maxe'] and m['top3']<=b['top3'] and m['mo']<=b['mo']+1e-12 and m['distinct']>=b['distinct']
def legal(e,l,cur,k):
    if k in l or sal[k]['Position']!=sal[cur]['Position']: return None
    if sum(int(sal[i]['Salary']) for i in l)-int(sal[cur]['Salary'])+int(sal[k]['Salary'])>50000: return None
    if gm(k)==gm(dst(l)) and sal[k]['TeamAbbrev']!=sal[dst(l)]['TeamAbbrev']: return None
    tr=[k if i==cur else i for i in l]
    if tuple(sorted(tr)) in {tuple(sorted(v)) for kk,v in A.items() if kk!=e}: return None
    if max(len(set(tr)&set(v)) for kk,v in A.items() if kk!=e)>5: return None
    return tr
movable=lambda l,i: unlocked(i) and sal[i]['Position'] not in('QB','DST') and sal[i]['Name'] not in protect and gm(i)!=gm(qb(l))
base=metrics(A); print('base',{k:round(v,3) for k,v in base.items()})
log=[]
wil=[k for k,r in sal.items() if r['Name']=='Emanuel Wilson'][0]
while sum(1 for l in A.values() if wil in l)<target:
    cur_m=metrics(A); best=None
    for e,l in A.items():
        if wil in l: continue
        for cur in l:
            if not movable(l,cur) or sal[cur]['Position']!='RB': continue
            tr=legal(e,l,cur,wil)
            if tr is None: continue
            B=dict(A); B[e]=tr; m=metrics(B)
            if not no_worse(m,cur_m): continue
            key=(-(sc.get(cur,0)-sc[wil]), -m['mo'])   # smallest prior given up, then lowest overlap
            if best is None or key>best[0]: best=(key,e,cur,tr,m)
    if not best: print('no washout-safe row left for Wilson'); break
    _,e,cur,tr,m=best; A[e]=tr; log.append(f"LATE_ADD {e}: {sal[cur]['Name']} ({sal[cur]['Salary']}) -> Emanuel Wilson")
changed=True
while changed:
    changed=False; cur_m=metrics(A); best=None
    for e,l in A.items():
        for cur in l:
            if not movable(l,cur): continue
            for k in sal:
                if k not in sc or sal[k]['Status']!='' or sal[k]['Name'] in inactive or not unlocked(k) or gm(k)==gm(qb(l)): continue
                gain=sc[k]-sc.get(cur,0)
                if gain<=0: continue
                tr=legal(e,l,cur,k)
                if tr is None: continue
                B=dict(A); B[e]=tr; m=metrics(B)
                if no_worse(m,cur_m) and (best is None or gain>best[0]): best=(gain,e,cur,k,tr)
    if best:
        g,e,cur,k,tr=best; A[e]=tr; changed=True
        log.append(f"PARETO {e}: {sal[cur]['Name']} -> {sal[k]['Name']} (+{g:.2f} prior, ${int(sal[k]['Salary'])-int(sal[cur]['Salary']):+d})")
fin=metrics(A); print('final',{k:round(v,3) for k,v in fin.items()})
for n,e in enumerate(A):
    r=A[e]; d['lineups'][n]=dict(d['lineups'][n],roster=r,salary=sum(int(sal[i]['Salary']) for i in r),prior_points=round(sum(sc.get(i,0) for i in r),3))
d['construction'].setdefault('manual_adds',[]).extend(log)
json.dump(d,open(out,'x'),indent=1); print('\n'.join(log) or 'no change')
print('prior sum', round(sum(l['prior_points'] for l in d['lineups']),1))
