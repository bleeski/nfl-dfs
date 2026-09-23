#!/usr/bin/env python3
"""Deterministic QA of an exported DK Showdown review CSV. Twin of qa_classic_portfolio.py.

Written 2026-09-14 per SHOWDOWN_RETROSPECTIVE_2026-09-13 section 7a: this was
hand-written four times in one session. Operates on the EXPORTED BYTES and the
source template, never on the engine's own report.

2026-09-23 (Session 02b): the audit (issue #40, section 4 standalone-QA rows)
found four construction choices DraftKings allows failing the exit code:
ZERO_QB, MULTIPLE_KICKERS, MULTIPLE_DST and DST_WITH_OWN_OFFENSE. They are now
OBSERVATIONS, printed and never counted. Exit 2 is kept for what DraftKings would
reject or what breaks the file (slots, identity, cap, one team, repeated
lineups, bytes, Entry ID coverage, officially inactive players) and, for now,
for the operator's --max-overlap and --backup-pairs limits. Exit 0 does not
clear an upload.
"""
import argparse, csv, collections, json, sys

def load_salary(p):
    d = {}
    for r in csv.DictReader(open(p, newline='', encoding='utf-8-sig')):
        d[r['ID'].strip()] = dict(name=r['Name'].strip(), team=r['TeamAbbrev'].strip(),
                                  pos=r['Position'].strip(), salary=int(r['Salary']),
                                  role=r['Roster Position'].strip(),
                                  status=(r.get('Status') or '').strip())
    return d

def rows_of(p):
    return list(csv.reader(open(p, newline='', encoding='utf-8-sig')))

def main(argv=None):
    a = argparse.ArgumentParser()
    a.add_argument('--salaries', required=True)
    a.add_argument('--template', required=True)
    a.add_argument('--export', required=True)
    a.add_argument('--max-overlap', type=int, default=4)
    a.add_argument('--inactive-dk-ids', default='')
    a.add_argument('--backup-pairs', default='',
                   help='semicolon list of STARTER_NAME>BACKUP_NAME pairs to flag if co-rostered')
    a = a.parse_args(argv)

    sal = load_salary(a.salaries)
    tpl, exp = rows_of(a.template), rows_of(a.export)
    D = []
    O = []  # strategy observations: reported, never counted toward the exit code

    # 1. byte fidelity: only the six roster cells on reserved rows may differ
    if len(tpl) != len(exp):
        D.append(f"ROW_COUNT_CHANGED template={len(tpl)} export={len(exp)}")
    for i, (t, e) in enumerate(zip(tpl, exp)):
        if len(t) != len(e):
            D.append(f"ROW_{i}_WIDTH_CHANGED {len(t)}->{len(e)}"); continue
        for j, (tv, ev) in enumerate(zip(t, e)):
            if tv != ev and not (4 <= j <= 9 and i > 0 and t[0].strip().isdigit()):
                D.append(f"ROW_{i}_COL_{j}_MUTATED {tv!r}->{ev!r}")

    inact = {x.strip() for x in a.inactive_dk_ids.split(',') if x.strip()}
    pairs = []
    for it in a.backup_pairs.split(';'):
        if '>' in it:
            s, b = it.split('>', 1); pairs.append((s.strip(), b.strip()))

    lus, entry_ids = [], []
    for r in exp:
        if not r or not r[0].strip().isdigit():
            continue
        entry_ids.append(r[0].strip())
        ids = [c.strip() for c in r[4:10]]
        if any(not i for i in ids):
            D.append(f"{r[0]} INCOMPLETE_ROSTER"); continue
        meta = [sal.get(i) for i in ids]
        if any(m is None for m in meta):
            D.append(f"{r[0]} UNKNOWN_DK_ID"); continue
        if meta[0]['role'] != 'CPT':
            D.append(f"{r[0]} SLOT1_NOT_CPT_ROW {meta[0]['name']}")
        for m in meta[1:]:
            if m['role'] != 'FLEX':
                D.append(f"{r[0]} FLEX_SLOT_HAS_CPT_ROW {m['name']}")
        names = [m['name'] for m in meta]
        if len(set(names)) != 6:
            D.append(f"{r[0]} DUPLICATE_PERSON {names}")
        sc = sum(m['salary'] for m in meta)
        if sc > 50000:
            D.append(f"{r[0]} SALARY_CAP_EXCEEDED {sc}")
        if len({m['team'] for m in meta}) < 2:
            D.append(f"{r[0]} SINGLE_TEAM_LINEUP")
        nq = sum(1 for m in meta if m['pos'] == 'QB')
        if nq == 0:
            O.append(f"{r[0]} ZERO_QB")
        nk = sum(1 for m in meta if m['pos'] == 'K')
        if nk > 1:
            O.append(f"{r[0]} MULTIPLE_KICKERS {nk}")
        nd = sum(1 for m in meta if m['pos'] == 'DST')
        if nd > 1:
            O.append(f"{r[0]} MULTIPLE_DST {nd}")
        for m in meta:
            if m['pos'] == 'DST':
                off = [x for x in meta if x['team'] == m['team'] and x['pos'] != 'DST']
                if off:
                    O.append(f"{r[0]} DST_WITH_OWN_OFFENSE {m['team']}:{[x['name'] for x in off]}")
        for s, b in pairs:
            if s in names and b in names:
                D.append(f"{r[0]} STARTER_WITH_OWN_BACKUP {s}+{b}")
        bad = [i for i in ids if i in inact]
        if bad:
            D.append(f"{r[0]} OFFICIALLY_INACTIVE_ROSTERED {bad}")
        lus.append((r[0].strip(), names[0], set(names), sc, nq))

    tpl_ids = [r[0].strip() for r in tpl if r and r[0].strip().isdigit()]
    if entry_ids != tpl_ids:
        D.append(f"ENTRY_ID_ORDER_OR_COVERAGE_MISMATCH")
    canon = [(c, tuple(sorted(s - {c}))) for _, c, s, _, _ in lus]
    if len(set(canon)) != len(canon):
        D.append("DUPLICATE_LINEUPS")
    mx = 0
    for i in range(len(lus)):
        for j in range(i + 1, len(lus)):
            o = len(lus[i][2] & lus[j][2]); mx = max(mx, o)
            if o > a.max_overlap:
                D.append(f"OVERLAP_{o}_EXCEEDS_{a.max_overlap} {lus[i][0]}/{lus[j][0]}")

    print(json.dumps({
        'lineups': len(lus), 'defects': len(D), 'DEFECTS': D,
        'observations': len(O), 'OBSERVATIONS': O,
        'observation_note': 'strategy observations never change the exit code; '
                            'DraftKings accepts each of them',
        'max_pairwise_overlap': mx,
        'salary_min': min((l[3] for l in lus), default=0),
        'salary_max': max((l[3] for l in lus), default=0),
        'distinct_captains': len({l[1] for l in lus}),
        'qb_count_histogram': dict(collections.Counter(l[4] for l in lus)),
        'VERDICT': 'PASS' if not D else 'DEFECT',
    }, indent=2))
    return 0 if not D else 2

if __name__ == '__main__':
    sys.exit(main())
