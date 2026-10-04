"""Session 56 acceptance 5 (review F-02): the counterexample, bounded.

The 2026-10-02 review built 20 distinct, legal rows on the Session 54 fixture with no policy: two receivers in 20 of 20 and
a Captain in 7 of 20. The same pool under the existing policy mechanism at 0.60 and 0.20 gave 12 and 4 in 14.0 s on its
host. This is that world, with the policy the engine builds itself (`Ladder.begin_with_defaults`, the one `run-slate`
starts a no-policy Showdown run on) and the bank and joint-solve budgets the review used, so the test stays bounded at
30 s rather than running the unbounded scaled bank. It proves feasibility under the declared budgets, not a speed
promise for a real slate.
"""

from __future__ import annotations

import time
from collections import Counter

from nfl_dfs.gate_registry import load_gate_registry
from nfl_dfs.lineups import validate_lineup
from nfl_dfs.relaxation import Ladder, Rung

from . import test_declared_starter_selectable as world_module
from .test_prior_selection import _template

BOUND_SECONDS = 30.0
ENTRIES = tuple(str(index) for index in range(20))


def _counts(slate, lineups):
    person = {row.dk_id: row.underlying_id for row in slate.players}
    people = Counter(person[dk_id] for lineup in lineups for dk_id in lineup.roster)
    captains = Counter(person[lineup.roster[0]] for lineup in lineups)
    return people, captains


def test_the_reviews_counterexample_holds_the_default_caps_within_the_bound(tmp_path):
    world = world_module._world(tmp_path / "world")
    slate = world[0]

    # The control: the engine's no-policy selector on this world, as the review ran it.
    loose, _scores, _report = world_module._select(world, count=20)
    loose_people, loose_captains = _counts(slate, loose)
    assert len({lineup.canonical_key for lineup in loose}) == 20
    assert max(loose_people.values()) > 12 and max(loose_captains.values()) > 4

    # The engine's own default policy for the same twenty rows, built and validated the way `run-slate` builds it.
    (tmp_path / "entries").mkdir()
    entries = _template(tmp_path / "entries", ENTRIES)
    tmp = tmp_path / "relaxation"
    ladder = Ladder(slate=slate, entries=entries, folder=tmp, registry=load_gate_registry(),
                    supplied=Rung(None, None, engine_default=True, concentration=0))
    rung = ladder.begin_with_defaults()
    assert rung.label == "DEFAULT" and rung.policy is not None and rung.policy.entry_ids == ENTRIES

    started = time.perf_counter()
    lineups, _scores, report = world_module._select(
        world, count=20, portfolio_policy=rung.policy, policy_candidate_limit=120, policy_candidate_seconds=30,
        policy_selection_seconds=15)
    elapsed = time.perf_counter() - started

    assert len(lineups) == 20 and len({lineup.canonical_key for lineup in lineups}) == 20  # R29
    for lineup in lineups:
        assert validate_lineup(slate, lineup.roster).valid
    people, captains = _counts(slate, lineups)
    assert max(people.values()) <= 12 and max(captains.values()) <= 4
    assert report["portfolio_policy"]["enforcement_status"] == "PASS"
    assert report["differentiation"]["max_person_overlap"] == 4
    assert elapsed < BOUND_SECONDS, f"{elapsed:.1f} s against a {BOUND_SECONDS:g} s bound on this host"
