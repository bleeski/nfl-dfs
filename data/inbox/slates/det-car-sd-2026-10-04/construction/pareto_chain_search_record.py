import runpy,sys,csv,json,collections
SRC='/home/user/nfl-dfs/data/inbox/slates/det-car-sd-2026-10-04/construction/DK_REVIEW_ENTRY_det-car-sd_final.csv'
sys.argv=['x',SRC]
import io,contextlib
with contextlib.redirect_stdout(io.StringIO()):
    g=runpy.run_path('/tmp/claude-0/-home-user-nfl-dfs/83ce60f1-d2e1-5278-9529-e58178f0fe2e/scratchpad/det-car-sd/pareto.py')
sal,score,excl,key,people,metrics,salary=g['sal'],g['score'],g['excl'],g['key'],g['people'],g['metrics'],g['salary']
raw=list(csv.reader(open(SRC))); rows=[r for r in raw[1:] if r and r[0].strip().isdigit()]
base=metrics(rows); cnt=collections.Counter(p for r in rows for p in set(people(r)))
flex={key(i):i for i in sal if sal[i]['Roster Position']=='FLEX' and i not in excl}
LOWER=('max_exposure','max_captain','mean_pair_overlap','max_pair_overlap','top3_union'); HIGHER=('distinct_people','distinct_captains','distinct_lineups')
def movable(i): return sal[i]['Position']!='QB' and sal[i]['Name']!='Brycen Tremayne'
res=[]
for a,A in enumerate(rows):
  for xs in range(5,10):
    x=A[xs].strip()
    if not movable(x): continue
    for yk,y in flex.items():
      if sal[y]['Position']=='QB' or score.get(y,0)<=score.get(x,0)+1e-9 or cnt[yk]>cnt[key(x)]-1: continue
      for b,B in enumerate(rows):
        if b==a: continue
        for ps in range(5,10):
          p=B[ps].strip()
          if not movable(p) or key(p) in people(A) or yk in people(B) or key(p)==yk: continue
          if salary(A)-int(sal[x]['Salary'])+int(sal[p]['Salary'])>50000: continue
          if salary(B)-int(sal[p]['Salary'])+int(sal[y]['Salary'])>50000: continue
          nA=list(A); nA[xs]=p; nB=list(B); nB[ps]=y
          trial=[nA if i==a else nB if i==b else r for i,r in enumerate(rows)]
          m=metrics(trial)
          if m['distinct_lineups']<28 or m['max_pair_overlap']>4: continue
          worse=[k for k in LOWER if m[k]>base[k]]+[k for k in HIGHER if m[k]<base[k]]
          if worse: continue
          res.append((round(m['prior_total']-base['prior_total'],2),A[0],sal[x]['Name'],sal[p]['Name'],B[0],sal[p]['Name'],sal[y]['Name'],{k:m[k] for k in ('max_exposure','mean_pair_overlap','top3_union','distinct_people','max_pair_overlap')}))
res.sort(reverse=True)
print('BASE',json.dumps(base)); print('PARETO_CHAINS',len(res))
for r in res[:12]: print(r)
json.dump(res,open('/tmp/claude-0/-home-user-nfl-dfs/83ce60f1-d2e1-5278-9529-e58178f0fe2e/scratchpad/det-car-sd/chains.json','w'))
