#!/usr/bin/env python3
"""Generate an nfl_showdown_portfolio_policy_v1 artifact from DK salary + entries bytes.

Twin of scripts/make_classic_policy.py. Written 2026-09-14 per the
SHOWDOWN_RETROSPECTIVE_2026-09-13 recommendation: the policy schema was guessed
wrong by hand on the prior slate and cost ~3 minutes under a lock clock.

Emits absolute paths, exact-decimal fractions in FRACTION_0_TO_1, the complete
person identity map derived from the salary bytes, and every fillable Entry ID
in template order as read from the entries file. `--entry-id` (repeatable,
Session 11b) binds only those rows instead, in template order; each must be a
fillable blank row. run-slate fills the rows the policy leaves unbound with
sequential Showdown after the policy's joint solve, and every fraction's
denominator is the bound rows.

RUNGS (Session 10). `--rung 0` is the policy the flags describe. Rungs 1 to 3
are `nfl_dfs.relaxation.SHOWDOWN_RUNGS` applied to it, each the loosest of the
policy and the rung, never tighter: 1 widens every capped Captain fraction to
at least 0.25 (zeroed Captains stay zero); 2 lets zeroed Captains captain and
widens Captain caps to at least 0.5; 3 drops every exposure cap and raises the
overlap cap to at least 5. Rung 4 writes nothing: run-slate without
--portfolio-policy-json. `--exclude` and uniqueness are never relaxed (R29).
`run-slate` walks these rungs itself when SD3 fails on a trigger, after trying
a re-sized bank first; this flag writes one by hand.
"""
import argparse, csv, hashlib, json, os, sys
from collections import defaultdict

def sha256(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()

def read_salary(path):
    """Return people: underlying_id -> {cpt,flex,team,pos,name,cpt_salary,flex_salary,status}"""
    people = {}
    with open(path, newline='', encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            name = r['Name'].strip()
            team = r['TeamAbbrev'].strip()
            pos = r['Position'].strip()
            uid = f"{team}|{pos}|{name}"
            role = r['Roster Position'].strip()
            e = people.setdefault(uid, {'underlying_id': uid, 'team': team, 'pos': pos,
                                        'name': name, 'cpt_dk_id': None, 'flex_dk_id': None,
                                        'cpt_salary': None, 'flex_salary': None,
                                        'status': (r.get('Status') or '').strip()})
            if role == 'CPT':
                e['cpt_dk_id'] = r['ID'].strip(); e['cpt_salary'] = int(r['Salary'])
            elif role == 'FLEX':
                e['flex_dk_id'] = r['ID'].strip(); e['flex_salary'] = int(r['Salary'])
            if (r.get('Status') or '').strip():
                e['status'] = r['Status'].strip()
    bad = [u for u, e in people.items() if not e['cpt_dk_id'] or not e['flex_dk_id']]
    if bad:
        sys.exit(f"PERSON_MISSING_ROLE_ROW: {bad}")
    return people

def read_entries(path, salary_path):
    """The Entry IDs a policy binds: the template's fillable blank rows (Session 11).

    A prefilled, partly filled or unresolved row is never bound; `run-slate`
    validates the policy against the same list, and its intake checks the mode.
    """
    from nfl_dfs.dk import parse_entries, parse_salaries
    from nfl_dfs.entry_groups import plan_entries

    return list(plan_entries(parse_entries(path), parse_salaries(salary_path)).fillable)

def bound_entries(fillable, requested):
    """The rows `--entry-id` names, in template order (Session 11b); every fillable row without it."""
    if not requested:
        return list(fillable)
    wanted = [str(item).strip() for item in requested]
    repeated = sorted({item for item in wanted if wanted.count(item) > 1})
    if repeated:
        sys.exit(f"ENTRY_ID_REPEATED: {repeated}")
    outside = [item for item in wanted if item not in set(fillable)]
    if outside:
        sys.exit(f"ENTRY_ID_NOT_FILLABLE: {outside} are not fillable blank rows of the template"
                 f" (a prefilled, partly filled, unresolved or unknown row is never bound);"
                 f" fillable: {list(fillable)}")
    return [item for item in fillable if item in set(wanted)]

def game_id(path):
    with open(path, newline='', encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            return r['Game Info'].split(' ')[0].strip()

def ident(e):
    return {'underlying_id': e['underlying_id'], 'cpt_dk_id': e['cpt_dk_id'], 'flex_dk_id': e['flex_dk_id']}

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--salaries', required=True)
    ap.add_argument('--entries', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--combined-default', type=float, required=True)
    ap.add_argument('--captain-default', type=float, required=True)
    ap.add_argument('--max-overlap', type=int, default=4)
    ap.add_argument('--captain-zero-pos', default='K,DST',
                    help='comma-separated positions forced to captain fraction 0')
    ap.add_argument('--captain-zero-below-flex-salary', type=int, default=0,
                    help='force captain fraction 0 for anyone whose FLEX salary is <= this')
    ap.add_argument('--combined-override', action='append', default=[],
                    help='UNDERLYING_ID=FRACTION (repeatable)')
    ap.add_argument('--captain-override', action='append', default=[],
                    help='UNDERLYING_ID=FRACTION (repeatable)')
    ap.add_argument('--exclude', action='append', default=[],
                    help='UNDERLYING_ID to exclude entirely (repeatable)')
    ap.add_argument('--rung', type=int, default=0, choices=(0, 1, 2, 3, 4),
                    help='relax the policy the flags describe to this rung (nfl_dfs.relaxation)')
    ap.add_argument('--entry-id', action='append', default=[],
                    help='bind only this fillable Entry ID (repeatable); the rest are filled sequentially')
    a = ap.parse_args(argv)
    if a.rung == 4:
        print("rung 4 emits no policy by design: run run-slate without --portfolio-policy-json, so"
              " sequential Showdown selection builds the portfolio; exclusions go in the request.")
        return 0

    sal = os.path.abspath(a.salaries); ent = os.path.abspath(a.entries)
    people = read_salary(sal)
    entry_ids = bound_entries(read_entries(ent, sal), a.entry_id)
    n = len(entry_ids)

    def parse_ovr(items):
        out = {}
        for it in items:
            k, _, v = it.rpartition('=')
            if k not in people:
                sys.exit(f"UNKNOWN_UNDERLYING_ID: {k!r}\nknown sample: {list(people)[:5]}")
            out[k] = float(v)
        return out

    comb_ovr = parse_ovr(a.combined_override)
    capt_ovr = parse_ovr(a.captain_override)

    zero_pos = {p.strip() for p in a.captain_zero_pos.split(',') if p.strip()}
    for uid, e in people.items():
        if uid in capt_ovr:
            continue
        if e['pos'] in zero_pos or e['flex_salary'] <= a.captain_zero_below_flex_salary:
            capt_ovr[uid] = 0.0

    excl = []
    for uid in a.exclude:
        if uid not in people:
            sys.exit(f"UNKNOWN_UNDERLYING_ID (exclude): {uid!r}")
        excl.append(ident(people[uid]))

    pol = {
        'schema_version': 'nfl_showdown_portfolio_policy_v1',
        'bindings': {
            'salary_sha256': sha256(sal),
            'game_id': game_id(sal),
            'entry_ids': entry_ids,
            'person_identities': [ident(people[u]) for u in sorted(people)],
        },
        'controls': {
            'fraction_unit': 'FRACTION_0_TO_1',
            'max_combined_person_exposure': {
                'default_fraction': a.combined_default,
                'overrides': [dict(ident(people[u]), fraction=f) for u, f in sorted(comb_ovr.items())],
            },
            'max_captain_exposure': {
                'default_fraction': a.captain_default,
                'overrides': [dict(ident(people[u]), fraction=f) for u, f in sorted(capt_ovr.items())],
            },
            'excluded_people': excl,
            'max_pairwise_person_overlap': a.max_overlap,
            'require_unique_lineups': True,
        },
    }
    out = os.path.abspath(a.out)
    if a.rung:
        pol = relaxed_document(pol, sal, ent, a.rung)
        with open(out, 'wb') as f:
            f.write(pol)
    else:
        with open(out, 'w', encoding='utf-8') as f:
            json.dump(pol, f, indent=2)
            f.write('\n')

    import math
    def imax(fr): return math.floor(fr * n)
    print(json.dumps({
        'policy': out,
        'policy_sha256': sha256(out),
        'entries': n,
        'entry_ids': entry_ids,
        'people': len(people),
        'combined_default_integer_max': imax(a.combined_default),
        'captain_default_integer_max': imax(a.captain_default),
        'captain_zeroed': sorted(u for u, f in capt_ovr.items() if f == 0.0),
        'combined_overrides_integer': {u: imax(f) for u, f in sorted(comb_ovr.items())},
        'captain_overrides_nonzero_integer': {u: imax(f) for u, f in sorted(capt_ovr.items()) if f > 0},
        'max_pairwise_person_overlap': a.max_overlap,
        'rung': a.rung,
        **({'note': 'the integer caps above are the flags (rung 0); written_controls is the relaxed policy'}
           if a.rung else {}),
        **({'written_controls': _written_controls(out)} if a.rung else {}),
    }, indent=2))
    return 0


def _written_controls(path):
    from decimal import Decimal

    with open(path, encoding='utf-8') as f:
        controls = json.load(f, parse_float=Decimal)['controls']
    text = lambda value: None if value is None else str(value)
    captain = controls['max_captain_exposure']
    return {
        'combined_default_fraction': text(controls['max_combined_person_exposure']['default_fraction']),
        'captain_default_fraction': text(captain['default_fraction']),
        'captain_zeroed': sorted(o['underlying_id'] for o in captain['overrides'] if o['fraction'] == 0),
        'max_pairwise_person_overlap': controls['max_pairwise_person_overlap'],
    }


def relaxed_document(document, salary_path, entry_path, rung):
    """The rung-0 `document` relaxed to `rung` by the engine's table, as canonical bytes."""

    from nfl_dfs.dk import parse_salaries
    from nfl_dfs.portfolio_policy import (
        canonical_decimal_json_bytes, portfolio_policy_template, validate_portfolio_policy_bytes)
    from nfl_dfs.relaxation import showdown_relaxed_controls

    slate = parse_salaries(salary_path)
    entry_ids = read_entries(entry_path, salary_path)
    raw = json.dumps(document).encode('utf-8')
    validation = validate_portfolio_policy_bytes(raw, slate=slate, entry_ids=entry_ids)
    if validation.policy is None:
        sys.exit("RUNG_0_POLICY_INVALID: " + "; ".join(validation.blockers()))
    controls = showdown_relaxed_controls(validation.policy, rung)
    relaxed = portfolio_policy_template(slate, validation.policy.entry_ids, controls=controls)
    return canonical_decimal_json_bytes(relaxed) + b"\n"


if __name__ == '__main__':
    raise SystemExit(main())
