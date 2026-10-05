"""Whole-lineup swaps between Entry IDs (Showdown judgment pass, last step). The 36 lineups never change; only which Entry ID carries
which lineup. A swap is taken only when no contest measure worsens and at least one improves, then repeated to a fixed point.
Per contest with 2+ entries: distinct Captains (higher), same-Captain pairs, max people shared, mean people shared, pairs sharing 4+,
pairs sharing 3+ (all lower). Single-entry contests have no internal measure."""
import csv, json, sys, itertools, collections, hashlib
SL='/home/user/nfl-dfs/data/inbox/slates/atl-no-sd-2026-10-05'
SRC=SL+'/construction/DK_REVIEW_ENTRY_atl-no-sd_ceiling_v1.csv'; OUT=SL+'/construction/DK_REVIEW_ENTRY_atl-no-sd_ceiling_v2.csv'
if '--from' in sys.argv: SRC=SL+'/construction/'+sys.argv[sys.argv.index('--from')+1]  # v1 to v2 (first pass); v3 to v4
if '--to' in sys.argv: OUT=SL+'/construction/'+sys.argv[sys.argv.index('--to')+1]
sal={r['ID']:r for r in csv.DictReader(open(SL+'/input/DKSalaries_143.csv',encoding='utf-8-sig'))}
key=lambda i:(sal[i]['Name'],sal[i]['TeamAbbrev'])
raw=list(csv.reader(open(SRC,newline=''))); rows=[r for r in raw[1:] if r and r[0].strip().isdigit() and r[4].strip()]
contest={r[0]:r[2] for r in rows}; lineup={r[0]:r[4:10] for r in rows}
def cmeasure(eids):
    L=[lineup[e] for e in eids]; P=[set(map(key,l)) for l in L]; C=[key(l[0]) for l in L]
    pairs=list(itertools.combinations(range(len(L)),2)); sh=[len(P[a]&P[b]) for a,b in pairs]
    return dict(distinct_captains=len(set(C)),same_captain_pairs=sum(C[a]==C[b] for a,b in pairs),max_shared=max(sh),
                mean_shared=round(sum(sh)/len(sh),4),pairs_shared_4=sum(s>=4 for s in sh),pairs_shared_3=sum(s>=3 for s in sh))
groups=collections.defaultdict(list)
for e,c in contest.items(): groups[c].append(e)
multi={c:es for c,es in groups.items() if len(es)>1}
def all_measures(): return {c:cmeasure(es) for c,es in multi.items()}
def no_worse_some_better(b,a):
    better=False
    for c in b:
        for k in b[c]:
            if k=='distinct_captains':
                if a[c][k]<b[c][k]: return False
                better|=a[c][k]>b[c][k]
            else:
                if a[c][k]>b[c][k]: return False
                better|=a[c][k]<b[c][k]
    return better
before=all_measures(); log=[]
while True:
    cur=all_measures(); done=False
    for e1,e2 in itertools.combinations(sorted(contest),2):
        if contest[e1]==contest[e2] or (contest[e1] not in multi and contest[e2] not in multi): continue
        lineup[e1],lineup[e2]=lineup[e2],lineup[e1]
        new=all_measures()
        if no_worse_some_better(cur,new):
            log.append(dict(swap=[e1,e2],contests=[contest[e1],contest[e2]])); done=True; break
        lineup[e1],lineup[e2]=lineup[e2],lineup[e1]
    if not done: break
after=all_measures()
for c in multi: print(c,len(multi[c]),'BEFORE',before[c],'\n   ','AFTER ',after[c])
print('SWAPS',json.dumps(log))
assert sorted(map(tuple,lineup.values()))==sorted(tuple(r[4:10]) for r in rows)
if '--write' in sys.argv and log:
    with open(OUT,'x',newline='') as f:
        csv.writer(f,lineterminator='\r\n').writerows([r[:4]+list(lineup[r[0]])+r[10:] if r and r[0].strip() in lineup else r for r in raw])
    json.dump(dict(rules=__doc__,before=before,after=after,swaps=log,source_sha256=hashlib.sha256(open(SRC,'rb').read()).hexdigest(),
      out_sha256=hashlib.sha256(open(OUT,'rb').read()).hexdigest()),open(OUT.replace('.csv','_record.json'),'x'),indent=1)
    print('WROTE',OUT)
