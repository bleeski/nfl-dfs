"""ATL@NO scenario harness: scores a filled Showdown file against the engine's own correlated scenario bank and a cold-start field.

Everything here is a DIAGNOSTIC. The scenario bank is `simulation.simulate_factor_bank` on the run's own opportunity model (run r3's
projection inputs, the frozen prior history, the same operator exclusions, and Session 60's workload move, exactly as selection
received it). The field is `field.generate_opponent_field` on `ownership.cold_start_states` (a salary/projection-rank prior, NOT
calibrated ownership). No rate below is a win, cash or top-1% probability, EV or ROI; they are counts over prior-only scenarios.

Measures, per scenario s, with the field's weighted quantiles q99(s) and q75(s), q50(s):
  entry_top1      share of scenarios where the entry's score >= q99(s)                (goal 1 proxy, per entry)
  contest_top1    share of scenarios where ANY entry in that contest >= q99(s)         (goal 1 proxy, per contest)
  washout_q75     share of scenarios where NO entry in the portfolio >= q75(s)         (goal 2 proxy: no min-cash-like finish)
  washout_q50     share of scenarios where NO entry >= q50(s)
Banks: SELECT (seed 20261005, the search bank) and REFEREE (seed 20261006, report-only confirmation). Same bank and field for every
file compared, so differences are paired.
"""
from __future__ import annotations
import csv, json, sys, collections
from functools import lru_cache
from pathlib import Path
import numpy as np
REPO = Path('/home/user/nfl-dfs'); sys.path.insert(0, str(REPO / 'src'))
from nfl_dfs.dk import parse_salaries
from nfl_dfs.opportunity import load_opportunity_model
from nfl_dfs.offensive_roles import attach_history
from nfl_dfs.participation import build_participation_contract, redistribute_vacated_workload
from nfl_dfs.simulation import simulate_factor_bank, lineup_score_matrix
from nfl_dfs.ownership import cold_start_states
from nfl_dfs.field import generate_opponent_field

SL = REPO / 'data/inbox/slates/atl-no-sd-2026-10-05'
RUN = REPO / 'data/runs/20261005T225913Z-atl-no-sd-r3/prior_review/projected'
FROZEN = REPO / 'data/runs/atl-no-sd-1005-frozen'
SALARIES = SL / 'input/DKSalaries_143.csv'
PS_EXCLUDED = [x for x in (SL / 'construction/cannot_play_dk_ids.txt').read_text().strip().split(',')]
SEEDS = {'SELECT': 20261005, 'REFEREE': 20261006}
SCENARIOS = 6000
FIELD_SAMPLE = 4000


@lru_cache(maxsize=None)
def slate():
    return parse_salaries(SALARIES)


@lru_cache(maxsize=None)
def model():
    s = slate()
    m = load_opportunity_model(s, str(RUN / 'team_projections.csv'), str(RUN / 'player_opportunities.csv'), allow_empty_groups=True)
    prior_hash = json.loads((FROZEN / 'prior_package.json').read_text()).get('hashes', {}).get('player_prior.json')
    if not prior_hash:
        import hashlib; prior_hash = hashlib.sha256((FROZEN / 'player_prior.json').read_bytes()).hexdigest()
    m = attach_history(m, FROZEN / 'player_prior.json', prior_hash)
    contract = build_participation_contract(s, operator_excluded_dk_ids=tuple(PS_EXCLUDED))
    m, _ = redistribute_vacated_workload(s, m, contract)
    return m


@lru_cache(maxsize=None)
def bank(purpose: str):
    return simulate_factor_bank(slate(), model(), scenarios=SCENARIOS, seed=SEEDS[purpose], purpose=purpose)


BACKUP_QB = {'Tua Tagovailoa', 'Spencer Rattler', 'Cooper Rush', 'Jack Strand', 'Zach Wilson'}
FIELD_POOL = 20000
BETA = {'uniform': 0.0, 'sharp': 1.5}


@lru_cache(maxsize=None)
def pool_field():
    """20,000 random legal lineups from people who can play (no practice squad, no backup QB, no DK OUT/IR), salary 45,000-50,000,
    both teams. Seeded, so every file is compared against the same field. A construction of the diagnostic, not an ownership model:
    the engine's cold-start field (field_quantiles_cold_start) gave every person, practice-squad players included, about 2.5% of
    Captains, so its 99th percentile measured nothing."""
    s = slate(); excl = set(PS_EXCLUDED)
    sc = json.loads((SL / 'construction/pool_scores.json').read_text())['by_dk_id']
    cpt = [p for p in s.players if p.role == 'CPT' and p.dk_id not in excl and p.dk_id in sc and p.name not in BACKUP_QB
           and (p.status_raw or '').upper() not in ('OUT', 'IR', 'D')]
    flex = {p.underlying_id: p for p in s.players if p.role == 'FLEX' and p.dk_id not in excl and p.dk_id in sc
            and p.name not in BACKUP_QB and (p.status_raw or '').upper() not in ('OUT', 'IR', 'D')}
    rng = np.random.default_rng(424242); seen = set(); out = []
    fl = list(flex.values())
    while len(out) < FIELD_POOL:
        c = cpt[rng.integers(len(cpt))]
        picks = rng.choice(len(fl), size=5, replace=False)
        f = [fl[i] for i in picks]
        if any(x.underlying_id == c.underlying_id for x in f): continue
        sal = c.salary + sum(x.salary for x in f)
        if not 45000 <= sal <= 50000 or len({c.team, *[x.team for x in f]}) < 2: continue
        key = (c.dk_id, tuple(sorted(x.dk_id for x in f)))
        if key in seen: continue
        seen.add(key); out.append((c.dk_id,) + tuple(x.dk_id for x in f))
    return out


@lru_cache(maxsize=None)
def field_quantiles(purpose: str, sharpness: str = 'sharp'):
    s, sims = slate(), bank(purpose)
    rosters = pool_field()
    M = lineup_score_matrix(s, sims, rosters)
    mu = M.mean(axis=0); z = (mu - mu.mean()) / mu.std()
    w = np.exp(BETA[sharpness] * z)
    order = np.argsort(M, axis=1); Ms = np.take_along_axis(M, order, axis=1); Ws = w[order]
    cw = np.cumsum(Ws, axis=1) / w.sum()
    def q(p):
        idx = np.minimum((cw < p).sum(axis=1), M.shape[1] - 1)
        return Ms[np.arange(M.shape[0]), idx]
    cap = collections.Counter()
    for r, wi in zip(rosters, w): cap[s_name(r[0])] += wi
    tot = sum(cap.values())
    return dict(q99=q(0.99), q75=q(0.75), q50=q(0.50), field_lineups=len(rosters), state=f'POOL_{sharpness.upper()}',
                field_captain_share={k: round(v / tot, 4) for k, v in cap.most_common(8)})


@lru_cache(maxsize=None)
def field_quantiles_cold_start(purpose: str):
    s, sims = slate(), bank(purpose)
    pidx = {p: i for i, p in enumerate(sims.person_ids)}
    mean = {}
    for pl in s.players:
        mean[pl.dk_id] = float(sims.outcomes[:, pidx[pl.underlying_id]].mean()) * (1.5 if pl.role == 'CPT' else 1.0)
    team_total = {t.team: t.market_total for t in model().teams}
    states = cold_start_states(s, mean, team_total)
    state = next((st for st in states if 'BASE' in st.name.upper()), states[0])
    field = generate_opponent_field(s, state, field_size=FIELD_SAMPLE, seed=SEEDS[purpose] + 7)
    rosters = [f.roster for f in field]; w = np.array([f.multiplicity for f in field], dtype=float)
    M = lineup_score_matrix(s, sims, rosters)  # scenarios x field lineups
    order = np.argsort(M, axis=1); Ms = np.take_along_axis(M, order, axis=1); Ws = w[order]
    cw = np.cumsum(Ws, axis=1) / w.sum()
    def q(p):
        idx = (cw < p).sum(axis=1); idx = np.minimum(idx, M.shape[1] - 1)
        return Ms[np.arange(M.shape[0]), idx]
    captain_own = collections.Counter()
    for f in field: captain_own[s_name(f.roster[0])] += f.multiplicity
    tot = sum(captain_own.values())
    return dict(q99=q(0.99), q75=q(0.75), q50=q(0.50), field_lineups=len(field), state=state.name,
                field_captain_share={k: round(v / tot, 4) for k, v in captain_own.most_common(15)})


@lru_cache(maxsize=None)
def _sal():
    return {r['ID']: r for r in csv.DictReader(open(SALARIES, encoding='utf-8-sig'))}


def s_name(dk_id):
    return _sal()[dk_id]['Name']


def read_file(path):
    raw = list(csv.reader(open(path, newline='')))
    rows = [r for r in raw[1:] if r and r[0].strip().isdigit() and r[4].strip()]
    return [(r[0], r[2], tuple(x.strip() for x in r[4:10])) for r in rows]


def evaluate(entries, purpose='SELECT', sharpness='sharp'):
    """entries: list of (entry_id, contest_id, roster tuple CPT-first). Returns the diagnostic measures."""
    sims = bank(purpose); fq = field_quantiles(purpose, sharpness)
    M = lineup_score_matrix(slate(), sims, [e[2] for e in entries])
    top1 = M >= fq['q99'][:, None]
    by_contest = collections.defaultdict(list)
    for j, e in enumerate(entries): by_contest[e[1]].append(j)
    return dict(
        purpose=purpose,
        entry_top1={e[0]: round(float(top1[:, j].mean()), 4) for j, e in enumerate(entries)},
        contest_top1={c: round(float(top1[:, js].any(axis=1).mean()), 4) for c, js in sorted(by_contest.items())},
        contest_entries={c: len(js) for c, js in sorted(by_contest.items())},
        mean_entry_top1=round(float(top1.mean()), 4),
        portfolio_any_top1=round(float(top1.any(axis=1).mean()), 4),
        washout_q75=round(float((~(M >= fq['q75'][:, None]).any(axis=1)).mean()), 4),
        washout_q50=round(float((~(M >= fq['q50'][:, None]).any(axis=1)).mean()), 4),
        mean_score=round(float(M.mean()), 2),
    )


if __name__ == '__main__':
    path = sys.argv[1]; purposes = sys.argv[2:] or ['SELECT']
    for p in purposes:
        for sh in BETA:
            fq = field_quantiles(p, sh)
            ev = evaluate(read_file(path), p, sh)
            print(json.dumps(dict(bank=p, field=fq['state'], q99_mean=round(float(fq['q99'].mean()), 2), q75_mean=round(float(fq['q75'].mean()), 2),
                                  field_captain_share=fq['field_captain_share'])))
            print(json.dumps({k: v for k, v in ev.items() if k != 'entry_top1'}))
