#!/usr/bin/env python3
"""Generate an nfl_showdown_portfolio_policy_v2 artifact from DK salary + entries bytes.

Twin of scripts/make_classic_policy.py. Written 2026-09-14 per the
SHOWDOWN_RETROSPECTIVE_2026-09-13 recommendation: the policy schema was guessed
wrong by hand on the prior slate and cost ~3 minutes under a lock clock. v2
(Session 23, P2): per-lineup structural hygiene bounds from the four-game-stable
set in `docs/STANDINGS_DUAL_OPTIMIZATION_FINDINGS_2026-09-15.md` §5.4, §7,
§8.1 C and §8.2 H/I, plus a real default Captain cap (code review S7). v1 is
never mutated; a hand-authored v1 policy still validates.

Emits absolute paths, exact-decimal fractions in FRACTION_0_TO_1, the complete
person identity map derived from the salary bytes, and every fillable Entry ID
in template order as read from the entries file. `--entry-id` (repeatable,
Session 11b) binds only those rows instead, in template order; each must be a
fillable blank row. run-slate fills the rows the policy leaves unbound with
sequential Showdown after the policy's joint solve, and every fraction's
denominator is the bound rows.

DEFAULTS (Session 23, two re-cut by Session 57). One to two quarterbacks, one to
two pass catchers with each, $1 to $500 left, at most one kicker and one DST,
and no bar on a person sharing a rostered DST's team. Session 57 (2026-10-02
review F-06 and F-07) re-cut the two Session 23 defaults the graded fields
contradict: `offense_against_own_dst` is off (it forbade any non-DST person on a
rostered DST's team, and every rank-1 entry in NE@SEA, DEN@KC and PHI@CHI holds
one) and `--qb-count-max` is 2, minimum 1 (it was 1; two-quarterback rows were
24.7% of PHI@CHI entries and 73.5% of its top 1%, so a feasible one-quarterback
bank never reached the rung that admitted them). Nothing forces a second
quarterback or adds a bonus; the depth exclusions and the per-quarterback
pass-catcher bound are as they were. `--offense-against-own-dst` and
`--qb-count-max 1` write the old policy, and the policy field, the auditors, the
MILP rows and the relaxation table keep their meaning for an explicit or a frozen
policy (the Boolean is never read as the DST's opponent). Both are construction
preferences: Claude's defaults, Ben's to overturn. Kickers and DSTs stay in the
combined pool (`--captain-zero-pos` only zeroes their Captain fraction, never
excludes them): kickers were in 45%/68% and defenses 68%/82% of the top 1% in
the graded games. `--combined-default` (this session's name for
`max_person_share`), `--captain-default` and `--max-overlap` default to the
registered concentration defaults, `config/showdown_concentration_defaults_v1.json`
(Session 56, R35: 0.60 a person, 0.20 a Captain, overlap 4; they were 0.80, 0.4
and 4 before, 0.80 being the field median). An explicit flag wins. A Captain
default exists at all because of review S7: an unbounded default let the captain
strata and the summed-points objective put every entry under one Captain.

RUNGS (Session 10, extended Session 23). `--rung 0` is the policy the flags
describe. Rungs 1 to 3 are `nfl_dfs.relaxation.SHOWDOWN_RUNGS` applied to it,
each the loosest of the policy and the rung, never tighter: 1 widens every
capped Captain fraction to at least 0.25 (zeroed Captains stay zero) and drops
the salary band; 2 lets zeroed Captains captain, widens Captain caps to at
least 0.5, and additionally drops the pass-catcher band, the kicker/DST caps
and `offense_against_own_dst` (already open in a default policy, so it moves
only a policy that asked for it); 3 drops every exposure cap (which drops
`max_person_share` too), raises the overlap cap to at least 5, and
additionally drops the QB-count band. Rung 4 writes nothing: run-slate without
--portfolio-policy-json. `--exclude` and uniqueness are never relaxed (R29).
`run-slate` walks these rungs itself when SD3 fails on a trigger, after trying
a re-sized bank first; this flag writes one by hand. Session 56: a policy whose
two default fractions are exactly the registered pair (0.60 and 0.20, which is
what the flags give unless you set them) gives its caps way first on the
ladder, 0.80 and 0.40 and then none, before any structural rung, so rungs 1 to
3 written for it carry the caps already off (zeroed Captain overrides and the
structural bounds stay the rung's own). Any other value you set is yours and
the rungs treat it exactly as before.

THESIS (Session 23b). `--thesis PATH` reads one game thesis Ben chose (a JSON
object: `name`, `teams`, `captain_set`, optional `team_bounds`, `position_bounds`,
`excluded_people` and `named_backup_quarterbacks`, people as underlying IDs) and
writes v3 with it as `controls.theses`. Its Captains are exempt from
`--captain-zero-pos`, so a kicker or DST Captain the thesis requires stays
possible. Every rung carries the thesis unchanged; a policy count bound that
contradicts it gives way at validation, named (`docs/DATA_CONTRACTS.md` § SD3 v3).

A PORTFOLIO OF THESES (Session 23c). `--thesis` is repeatable: the order of the
flags is the order Ben declared, which is the priority (it breaks allotment ties
and decides which of two colliding theses is kept). Each file may carry
`row_weight`, a positive integer share of the entries (default 1; a higher
weight is more rows and nothing more: it is not a probability). More than one
thesis, or any `row_weight`, writes `nfl_showdown_portfolio_policy_v4`; exactly
one thesis without a weight still writes v3, byte for byte as before. The
entries are allotted across the theses by largest remainder, one joint solve
assembles every row (distinct across theses and against prefilled rows, R29),
and every Captain any thesis requires is exempt from `--captain-zero-pos`
(`docs/DATA_CONTRACTS.md` § SD3 v4).

THESES AND THE SALARY BAND (Session 23c). The default $1 to $500 band cannot hold a
thesis built from a kicker, a defense and backs, and `run-slate`'s ladder gives the
caps way before a band (Session 56), so with a band on, a portfolio of such theses
loses its 0.60 person cap and 0.20 Captain cap before the band is dropped. A
portfolio (more than one thesis, or any `row_weight`) is therefore written with the
band open ($0 to $50,000 left) unless `--salary-left-min` or `--salary-left-max` is
passed, and then it is yours. A policy with no thesis, and one thesis without a
weight (the Session 23b output), keep $1 to $500, so v3 is written exactly as
before. Claude's default under the lock-clock ruling, Ben's to overturn.
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
    from nfl_dfs.concentration import load_concentration_defaults

    defaults = load_concentration_defaults()  # Session 56: one registered default set (R35)
    ap = argparse.ArgumentParser()
    ap.add_argument('--salaries', required=True)
    ap.add_argument('--entries', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--combined-default', type=float, default=float(defaults.person_fraction),
                    help='max_person_share default, from config/showdown_concentration_defaults_v1.json'
                         ' (R35, Session 56; it was 0.80, the field median, until then)')
    ap.add_argument('--captain-default', type=float, default=float(defaults.captain_fraction),
                    help='default Captain fraction cap (review S7), from the same registered defaults;'
                         ' it was 0.4 until Session 56')
    ap.add_argument('--max-overlap', type=int, default=defaults.pairwise_person_overlap,
                    help='most people two lineups may share, from the same registered defaults')
    ap.add_argument('--captain-zero-pos', default='K,DST',
                    help='comma-separated positions forced to captain fraction 0 (they stay in the'
                         ' combined pool: never excluded, only barred from captaining by default)')
    ap.add_argument('--captain-zero-below-flex-salary', type=int, default=0,
                    help='force captain fraction 0 for anyone whose FLEX salary is <= this')
    ap.add_argument('--combined-override', action='append', default=[],
                    help='UNDERLYING_ID=FRACTION (repeatable)')
    ap.add_argument('--captain-override', action='append', default=[],
                    help='UNDERLYING_ID=FRACTION (repeatable)')
    ap.add_argument('--exclude', action='append', default=[],
                    help='UNDERLYING_ID to exclude entirely (repeatable)')
    ap.add_argument('--qb-count-min', type=int, default=1)
    ap.add_argument('--qb-count-max', type=int, default=2,
                    help='most quarterbacks a lineup may hold (default 2, minimum 1: Session 57, review F-07;'
                         ' it was 1). Nothing forces a second one; --qb-count-max 1 asks for the old band')
    ap.add_argument('--pass-catchers-min', type=int, default=1,
                    help='minimum WR/TE on the rostered QB\'s team (0 QBs rostered is unaffected)')
    ap.add_argument('--pass-catchers-max', type=int, default=2)
    ap.add_argument('--salary-left-min', type=int, default=None,
                    help='fewest dollars a lineup leaves (default 1; 0 for a portfolio of theses: see the docstring)')
    ap.add_argument('--salary-left-max', type=int, default=None,
                    help='most dollars a lineup leaves (default 500; 50000 for a portfolio of theses)')
    ap.add_argument('--kicker-count-max', type=int, default=1)
    ap.add_argument('--dst-count-max', type=int, default=1)
    ap.add_argument('--offense-against-own-dst', dest='offense_against_own_dst',
                    action='store_true', default=False,
                    help='forbid any position sharing a rostered DST\'s team (default off since Session 57,'
                         ' review F-06: the field holds a DST beside a teammate; it was on)')
    ap.add_argument('--no-offense-against-own-dst', dest='offense_against_own_dst', action='store_false',
                    default=False, help='the default, spelled out')
    ap.add_argument('--rung', type=int, default=0, choices=(0, 1, 2, 3, 4),
                    help='relax the policy the flags describe to this rung (nfl_dfs.relaxation)')
    ap.add_argument('--entry-id', action='append', default=[],
                    help='bind only this fillable Entry ID (repeatable); the rest are filled sequentially')
    ap.add_argument('--thesis', action='append', default=[],
                    help='JSON file holding one game thesis (Session 23b), repeatable (Session 23c: the flag order is'
                         ' the declared priority; a file may carry row_weight); one thesis writes v3, more write v4')
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

    theses = [read_thesis(path, people) for path in a.thesis]
    # One thesis without a weight is the Session 23b contract (v3) exactly; anything more is a portfolio (v4).
    portfolio = len(theses) > 1 or any('row_weight' in item for item in theses)
    # The $1 to $500 band is Session 23's hygiene default, and a thesis that opens only a kicker, a defense and backs cannot
    # spend $49,500 (measured on NE@SEA: the bank held no candidate for those theses). The ladder gives the caps way before
    # a band (Session 56), so leaving the band on would cost a portfolio its 0.60 and 0.20 caps first and the theses nothing
    # but time. A portfolio's band therefore defaults open; either flag, given, is the operator's and wins. A single thesis
    # without a weight is the Session 23b output and keeps the band it always had, so v3 is byte for byte as before.
    if a.salary_left_min is None:
        a.salary_left_min = 0 if portfolio else 1
    if a.salary_left_max is None:
        a.salary_left_max = 50000 if portfolio else 500
    thesis_captains = {person['underlying_id'] for item in theses for person in item['captain_set']}
    zero_pos = {p.strip() for p in a.captain_zero_pos.split(',') if p.strip()}
    for uid, e in people.items():
        if uid in capt_ovr or uid in thesis_captains:
            continue
        if e['pos'] in zero_pos or e['flex_salary'] <= a.captain_zero_below_flex_salary:
            capt_ovr[uid] = 0.0

    excl = []
    for uid in a.exclude:
        if uid not in people:
            sys.exit(f"UNKNOWN_UNDERLYING_ID (exclude): {uid!r}")
        excl.append(ident(people[uid]))

    pol = {
        'schema_version': ('nfl_showdown_portfolio_policy_v4' if portfolio
                           else 'nfl_showdown_portfolio_policy_v3' if theses
                           else 'nfl_showdown_portfolio_policy_v2'),
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
            'structural_bounds': {
                'qb_count': {'minimum': a.qb_count_min, 'maximum': a.qb_count_max},
                'pass_catchers_with_rostered_qb': {
                    'minimum': a.pass_catchers_min, 'maximum': a.pass_catchers_max,
                },
                'salary_left': {'minimum': a.salary_left_min, 'maximum': a.salary_left_max},
                'kicker_count': a.kicker_count_max,
                'dst_count': a.dst_count_max,
                'offense_against_own_dst': a.offense_against_own_dst,
            },
            **({'theses': theses} if theses else {}),
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
        'structural_bounds': pol['controls']['structural_bounds'] if not a.rung else None,
        'rung': a.rung,
        **({'note': 'the integer caps above are the flags (rung 0); written_controls is the relaxed policy'}
           if a.rung else {}),
        **({'written_controls': _written_controls(out)} if a.rung else {}),
    }, indent=2))
    return 0


def read_thesis(path, people):
    """One thesis from `path`, its people resolved to exact identities; the validator checks the rest."""

    with open(path, encoding='utf-8') as f:
        raw = json.load(f)
    if not isinstance(raw, dict):
        sys.exit(f"THESIS_NOT_AN_OBJECT: {path}")
    thesis = dict(raw)
    for field in ('captain_set', 'excluded_people', 'named_backup_quarterbacks'):
        resolved = []
        for uid in raw.get(field) or []:
            if uid not in people:
                sys.exit(f"UNKNOWN_UNDERLYING_ID (thesis {field}): {uid!r}")
            resolved.append(ident(people[uid]))
        thesis[field] = resolved
    return thesis


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
        'structural_bounds': controls.get('structural_bounds'),
    }


def relaxed_document(document, salary_path, entry_path, rung):
    """The rung-0 `document` relaxed to `rung` by the engine's table, as canonical bytes."""

    from nfl_dfs.dk import parse_salaries
    from nfl_dfs.portfolio_policy import (
        canonical_decimal_json_bytes, portfolio_policy_template, validate_portfolio_policy_bytes)
    from nfl_dfs.concentration import load_concentration_defaults
    from nfl_dfs.relaxation import concentration_state, showdown_relaxed_controls, showdown_schema_version

    slate = parse_salaries(salary_path)
    entry_ids = read_entries(entry_path, salary_path)
    raw = json.dumps(document).encode('utf-8')
    validation = validate_portfolio_policy_bytes(raw, slate=slate, entry_ids=entry_ids)
    if validation.policy is None:
        sys.exit("RUNG_0_POLICY_INVALID: " + "; ".join(validation.blockers()))
    # A policy at the registered default pair has taken the cap steps before any structural rung
    # (Session 56), so rung N writes what the ladder holds at rung N, caps already off.
    state = concentration_state(validation.policy, load_concentration_defaults())
    controls = showdown_relaxed_controls(validation.policy, rung, concentration=state)
    relaxed = portfolio_policy_template(
        slate, validation.policy.entry_ids, controls=controls,
        schema_version=showdown_schema_version(validation.policy))
    return canonical_decimal_json_bytes(relaxed) + b"\n"


if __name__ == '__main__':
    raise SystemExit(main())
