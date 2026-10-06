"""Independent check of a candidate ATL@NO file (main session, not the QA agent): harness measures on SELECT and REFEREE with the
sharp (beta 1.5) and very_sharp (beta 3.0) fields, plus every hard construction rule of the QA pass. Diagnostics only."""
import sys, json, csv, collections, itertools
sys.path.insert(0, '/home/user/nfl-dfs/data/inbox/slates/atl-no-sd-2026-10-05/construction')
import scenario_harness as H
H.BETA['very_sharp'] = 3.0
sal = {r['ID']: r for r in csv.DictReader(open(H.SALARIES, encoding='utf-8-sig'))}
cannot = set(H.PS_EXCLUDED)
STARTER = {'ATL': 'Michael Penix Jr.', 'NO': 'Tyler Shough'}; OPP = {'ATL': 'NO', 'NO': 'ATL'}

def rules(entries):
    probs = []; cnt = collections.Counter(); cpt = collections.Counter(); sigs = set(); zero_qb = 0; qb_hist = collections.Counter()
    people = []
    for eid, cid, r in entries:
        n = [sal[x]['Name'] for x in r]; pos = [sal[x]['Position'] for x in r]; team = [sal[x]['TeamAbbrev'] for x in r]
        people.append(set(n))
        if sal[r[0]]['Roster Position'] != 'CPT' or any(sal[x]['Roster Position'] != 'FLEX' for x in r[1:]): probs.append(f'{eid} slot')
        if len(set(n)) != 6 or len(set(team)) < 2 or sum(int(sal[x]['Salary']) for x in r) > 50000: probs.append(f'{eid} illegal')
        if any(x in cannot for x in r) or any(sal[x]['Status'] in ('OUT', 'IR', 'D') for x in r) or set(n) & H.BACKUP_QB: probs.append(f'{eid} banned')
        sig = (n[0], tuple(sorted(n[1:])))
        if sig in sigs: probs.append(f'{eid} R29 duplicate')
        sigs.add(sig)
        q = sum(p == 'QB' for p in pos); qb_hist[q] += 1
        if pos[0] in ('WR', 'TE') and STARTER[team[0]] not in n: probs.append(f'{eid} WR/TE captain without own QB')
        if sum(p == 'DST' for p in pos) > 1: probs.append(f'{eid} two DST')
        for i, p in enumerate(pos):
            if p == 'DST' and STARTER[OPP[team[i]]] in n: probs.append(f'{eid} DST beside opposing QB')
        if sum(p == 'K' for p in pos) > 1: probs.append(f'{eid} two kickers')
        if q == 0:
            zero_qb += 1
            if pos[0] not in ('RB', 'K', 'DST'): probs.append(f'{eid} zero-QB under {pos[0]} captain')
        cpt[n[0]] += 1; cnt.update(set(n))
    ov = max(len(a & b) for a, b in itertools.combinations(people, 2))
    if zero_qb > 3: probs.append(f'zero-QB rows {zero_qb} > 3')
    if len(cpt) < 10: probs.append(f'distinct captains {len(cpt)} < 10')
    if max(cpt.values()) > 7: probs.append('captain cap')
    if max(cnt.values()) > 27: probs.append('person cap')
    if ov > 5: probs.append(f'overlap {ov}')
    if cnt['Kyle Pitts Sr.'] > 6: probs.append('Pitts > 6')
    if cnt['Chris Olave'] < 7: probs.append('Olave < 7')
    return dict(problems=probs, captains=dict(cpt.most_common()), distinct_captains=len(cpt), qb_hist=dict(qb_hist),
                max_person=cnt.most_common(4), max_overlap=ov)

if __name__ == '__main__':
    files = sys.argv[1:]
    for f in files:
        e = H.read_file(f); print('FILE', f.split('/')[-1]); print('RULES', json.dumps(rules(e)))
        for p in ('SELECT', 'REFEREE'):
            for sh in ('sharp', 'very_sharp'):
                ev = H.evaluate(e, p, sh)
                print(p, sh, json.dumps(dict(contest_top1=ev['contest_top1'], mean_entry_top1=ev['mean_entry_top1'],
                      any_top1=ev['portfolio_any_top1'], washout_q75=ev['washout_q75'], washout_q50=ev['washout_q50'])))
