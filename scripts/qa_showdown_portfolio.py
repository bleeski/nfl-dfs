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
2026-09-26 (Session 37): the 2026-09-25 code review (V2, V11) found the byte
loop exempted the roster cells of every numbered row, so an export that
overwrote a prefilled row printed PASS, and that it compared parsed cells, not
bytes. It now mirrors `qa_classic_portfolio.py`:

* **Export audit, on bytes.** Template and export are split into raw lines with
  `nfl_dfs.byte_lines`. Every line must be byte-identical except a row whose
  six roster cells are blank in the template, which may differ only inside
  those six cells, with the same field count and line ending.
* **Only blank rows are checked as this run's lineups.** A prefilled row must
  come through untouched; it still counts toward R29 distinctness.
* **Identity by DraftKings ID.** A person is the salary row's
  `team|position|name` for the ID in the cell (the engine's `underlying_id`),
  never a bare `Name`; a lineup is its Captain ID and its sorted FLEX IDs.
  `--backup-pairs` accepts a DraftKings ID or a name on either side.
* **Exit codes as Classic's:** 1 a validity failure (bytes, roster rules,
  Entry ID coverage, a repeated lineup under R29, an officially inactive
  player); 3 valid, but blank authorized rows are unfilled (a sanctioned R29
  shortfall), each named; 2 only an operator limit (`--max-overlap`,
  `--backup-pairs`); else 0. Exit 0 still does not clear an upload.
"""
from __future__ import annotations
import argparse, csv, collections, json, re, sys

from nfl_dfs.byte_lines import csv_field_spans, split_byte_lines, split_line_ending

SLOTS = ["CPT", "FLEX", "FLEX", "FLEX", "FLEX", "FLEX"]
WIDTH = len(SLOTS)
EXIT_PASS, EXIT_FAIL, EXIT_DEFECT, EXIT_PARTIAL = 0, 1, 2, 3
_TRAILING_ID = re.compile(r"\((\d+)\)\s*$")


def cell_id(cell):
    """A roster cell's DraftKings ID, whether it holds `123` or `Name (123)`."""
    match = _TRAILING_ID.search(cell)
    return match.group(1) if match else cell.strip()


def load_salary(p):
    d = {}
    with open(p, newline='', encoding='utf-8-sig') as fh:
        for r in csv.DictReader(fh):
            name, team, pos = r['Name'].strip(), r['TeamAbbrev'].strip(), r['Position'].strip()
            d[r['ID'].strip()] = dict(name=name, team=team, pos=pos, salary=int(r['Salary']),
                                      role=r['Roster Position'].strip(),
                                      person=f"{team}|{pos}|{name}",
                                      status=(r.get('Status') or '').strip())
    return d


def cells_of(line):
    body, _ = split_line_ending(line)
    return next(csv.reader([body.decode("utf-8-sig", errors="replace")]), [])


def roster_region_changed_only(t_line, e_line, lo):
    """True when two raw lines differ at most inside fields lo..lo+5."""
    (tb, te), (eb, ee) = split_line_ending(t_line), split_line_ending(e_line)
    try:
        ts, es = csv_field_spans(tb), csv_field_spans(eb)
    except ValueError:
        return False
    if te != ee or len(ts) != len(es) or len(ts) < lo + WIDTH:
        return False
    hi = lo + WIDTH - 1
    return tb[:ts[lo][0]] == eb[:es[lo][0]] and tb[ts[hi][1]:] == eb[es[hi][1]:]


def export_audit(template, export):
    """Compare the export to the untouched template on raw bytes.

    Only a row blank in the template may change, and only inside its six roster
    cells. Returns (failures, filled rosters by Entry ID in slot order,
    unfilled blank Entry IDs, prefilled rosters by Entry ID).
    """
    fail, filled, unfilled, prefilled = [], {}, [], {}
    with open(template, "rb") as fh:
        t_raw = fh.read()
    with open(export, "rb") as fh:
        e_raw = fh.read()
    t_lines, e_lines = split_byte_lines(t_raw), split_byte_lines(e_raw)
    if len(t_lines) != len(e_lines):
        return [f"LINE_COUNT_CHANGED template={len(t_lines)} export={len(e_lines)}"], {}, [], {}
    hdr = cells_of(t_lines[0]) if t_lines else []
    if "Entry Fee" not in hdr or hdr[hdr.index("Entry Fee") + 1:hdr.index("Entry Fee") + 1 + WIDTH] != SLOTS:
        return ["NOT_A_SHOWDOWN_TEMPLATE: the template header has no CPT and five FLEX after Entry Fee"], {}, [], {}
    lo = hdr.index("Entry Fee") + 1
    template_ids = []
    for n, (t, e) in enumerate(zip(t_lines, e_lines)):
        tc = cells_of(t)
        eid = tc[0].strip() if n and tc else ""
        entry = eid.isdigit()
        blank = entry and not any(c.strip() for c in tc[lo:lo + WIDTH])
        if entry:
            template_ids.append(eid)
        if entry and not blank:
            prefilled[eid] = [cell_id(c) for c in tc[lo:lo + WIDTH]]
        if t == e:
            if blank:
                unfilled.append(eid)
            continue
        if not blank:
            what = f"prefilled entry {eid}" if entry else "a line that is not an entry row"
            fail.append(f"LINE_{n + 1}_BYTES_CHANGED on {what}; only a blank authorized row may change")
            continue
        if not roster_region_changed_only(t, e, lo):
            fail.append(f"LINE_{n + 1}_BYTES_CHANGED_OUTSIDE_ROSTER entry {eid}")
            continue
        cells = [cell_id(c) for c in cells_of(e)[lo:lo + WIDTH]]
        if not all(cells):
            fail.append(f"PARTIALLY_FILLED_ROW: entry {eid} has {sum(map(bool, cells))} of {WIDTH} cells")
            continue
        filled[eid] = cells
    export_ids = [c[0].strip() for c in map(cells_of, e_lines[1:]) if c and c[0].strip().isdigit()]
    if template_ids != export_ids:
        fail.append("ENTRY_ID_ORDER_OR_COVERAGE_MISMATCH")
    if t_raw == e_raw and unfilled:
        fail.append("EXPORT_IDENTICAL_TO_TEMPLATE: nothing was filled")
    return fail, filled, unfilled, prefilled


def lineup_key(ids):
    """R29 identity: the exact roster, so a different Captain is a different lineup."""
    return (ids[0], tuple(sorted(ids[1:])))


def main(argv=None):
    a = argparse.ArgumentParser()
    a.add_argument('--salaries', required=True)
    a.add_argument('--template', required=True)
    a.add_argument('--export', required=True)
    a.add_argument('--max-overlap', type=int, default=4)
    a.add_argument('--inactive-dk-ids', default='')
    a.add_argument('--backup-pairs', default='',
                   help='semicolon list of STARTER>BACKUP pairs, each side a DraftKings ID or a name, '
                        'to flag if co-rostered')
    a = a.parse_args(argv)

    sal = load_salary(a.salaries)
    D = []   # validity: exit 1
    L = []   # operator-requested limits: exit 2
    O = []   # strategy observations: reported, never counted toward the exit code

    fail, filled, unfilled, prefilled = export_audit(a.template, a.export)
    D.extend(fail)

    inact = {x.strip() for x in a.inactive_dk_ids.split(',') if x.strip()}

    def people_for(token):
        """A backup-pair side: the person of a DraftKings ID, or every person with that name."""
        if token in sal:
            return {sal[token]['person']}
        return {m['person'] for m in sal.values() if m['name'] == token}

    pairs = []
    for it in a.backup_pairs.split(';'):
        if '>' in it:
            s_, b_ = (x.strip() for x in it.split('>', 1))
            pairs.append((s_, b_, people_for(s_), people_for(b_)))

    lus = []
    for eid, ids in filled.items():
        meta = [sal.get(i) for i in ids]
        if any(m is None for m in meta):
            D.append(f"{eid} UNKNOWN_DK_ID"); continue
        if meta[0]['role'] != 'CPT':
            D.append(f"{eid} SLOT1_NOT_CPT_ROW {ids[0]}")
        for i, m in zip(ids[1:], meta[1:]):
            if m['role'] != 'FLEX':
                D.append(f"{eid} FLEX_SLOT_HAS_CPT_ROW {i}")
        people = [m['person'] for m in meta]
        if len(set(people)) != WIDTH:
            D.append(f"{eid} DUPLICATE_PERSON {people}")
        sc = sum(m['salary'] for m in meta)
        if sc > 50000:
            D.append(f"{eid} SALARY_CAP_EXCEEDED {sc}")
        if len({m['team'] for m in meta}) < 2:
            D.append(f"{eid} SINGLE_TEAM_LINEUP")
        nq = sum(1 for m in meta if m['pos'] == 'QB')
        if nq == 0:
            O.append(f"{eid} ZERO_QB")
        nk = sum(1 for m in meta if m['pos'] == 'K')
        if nk > 1:
            O.append(f"{eid} MULTIPLE_KICKERS {nk}")
        nd = sum(1 for m in meta if m['pos'] == 'DST')
        if nd > 1:
            O.append(f"{eid} MULTIPLE_DST {nd}")
        for m in meta:
            if m['pos'] == 'DST':
                off = [x for x in meta if x['team'] == m['team'] and x['pos'] != 'DST']
                if off:
                    O.append(f"{eid} DST_WITH_OWN_OFFENSE {m['team']}:{[x['person'] for x in off]}")
        for s_, b_, starters, backups in pairs:
            if starters & set(people) and backups & set(people):
                L.append(f"{eid} STARTER_WITH_OWN_BACKUP {s_}+{b_}")
        bad = [i for i in ids if i in inact]
        if bad:
            D.append(f"{eid} OFFICIALLY_INACTIVE_ROSTERED {bad}")
        lus.append((eid, people[0], set(people), sc, nq, lineup_key(ids)))

    # R29 covers the whole file, including rows filled before this run.
    keys = [l[5] for l in lus] + [lineup_key(r) for r in prefilled.values() if all(r)]
    if len(set(keys)) != len(keys):
        D.append("DUPLICATE_LINEUPS")
    mx = 0
    for i in range(len(lus)):
        for j in range(i + 1, len(lus)):
            o = len(lus[i][2] & lus[j][2]); mx = max(mx, o)
            if o > a.max_overlap:
                L.append(f"OVERLAP_{o}_EXCEEDS_{a.max_overlap} {lus[i][0]}/{lus[j][0]}")

    verdict = "FAIL" if D else "PARTIAL" if unfilled else "DEFECT" if L else "PASS"
    print(json.dumps({
        'lineups': len(lus), 'defects': len(D), 'DEFECTS': D,
        'limit_breaches': len(L), 'LIMIT_BREACHES': L,
        'unfilled_entry_ids': unfilled,
        'prefilled_entry_ids': sorted(prefilled),
        'observations': len(O), 'OBSERVATIONS': O,
        'observation_note': 'strategy observations never change the exit code; '
                            'DraftKings accepts each of them',
        'exit_codes': '1 validity failure; 3 blank authorized rows unfilled; '
                      '2 an operator limit only; 0 none of these, which does not clear an upload',
        'max_pairwise_overlap': mx,
        'salary_min': min((l[3] for l in lus), default=0),
        'salary_max': max((l[3] for l in lus), default=0),
        'distinct_captains': len({l[1] for l in lus}),
        'qb_count_histogram': dict(collections.Counter(l[4] for l in lus)),
        'VERDICT': verdict,
    }, indent=2))
    if D:
        return EXIT_FAIL
    if unfilled:
        return EXIT_PARTIAL
    return EXIT_DEFECT if L else EXIT_PASS

if __name__ == '__main__':
    sys.exit(main())
