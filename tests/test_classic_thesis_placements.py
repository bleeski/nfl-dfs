"""Session 61 (R37): protected placements in the Classic thesis build.

A validated construction judgment names people the thesis build must roster in at least a
minimum number of rows. These tests pin the mechanism on the Session 49 fixture (102 rows,
six teams): the minimum is met by construction, every row stays distinct and stacked (R29), a
failed attempt to place him changes nothing the shared relaxations hold, his person cap is his
own minimum when that is more, and the report is recounted from the delivered rosters.
"""

from __future__ import annotations

import itertools
from collections import Counter

import pytest

from nfl_dfs import classic_theses
from nfl_dfs.classic_theses import (
    DEFAULT_PERSON_SHARE,
    PLACEMENT_MISS_LIMIT,
    PLACEMENT_SOLVES_PER_ROW,
    THESIS_CONSTRUCTION_VERSION,
    THESIS_CONSTRUCTION_VERSION_V2,
    person_cap,
)
from nfl_dfs.optimizer import LineupOptimizer, SolverResult
from nfl_dfs.selection import CLASSIC_MAX_USEFUL_OVERLAP, CLASSIC_PERSON_OVERLAP, SelectionError

from .test_classic_portfolio_c2 import _slate
from .test_classic_theses import _shape, _thesis_run


def _person(slate, name):
    return next(p.underlying_id for p in slate.players if p.name == name)


def _rows_with(slate, run, person):
    by_id = {row.dk_id: row for row in slate.players}
    return [lineup.index for lineup in run.selected if person in {by_id[d].underlying_id for d in lineup.roster}]


def _run(protected, *, count=20, **kwargs):
    slate = _slate()
    named = {_person(slate, name): rows for name, rows in protected.items()}
    slate, run = _thesis_run(count, slate=slate, protected=named, **kwargs)
    return slate, run, named


# ----------------------------------------------------------------------------- the minimum is met


def test_a_protected_person_the_prior_would_never_pick_sits_in_his_minimum_rows():
    slate = _slate()
    _slate_b, plain = _thesis_run(20, slate=slate)
    low = _person(slate, "NYJ RB 4")
    assert len(_rows_with(slate, plain, low)) <= 1  # the objective barely reaches him: one late row at most

    slate, run, named = _run({"NYJ RB 4": 5})
    rows = _rows_with(slate, run, low)
    assert len(rows) >= 5 and len({lineup.canonical_key for lineup in run.selected}) == 20
    block = run.construction["placements"]
    assert block["requested"] == {low: 5} and block["met"] == {low: True} and block["shortfall"] == {}
    assert block["delivered_rows"] == {low: rows}
    assert set(block["forced_rows"]) <= {str(index) for index in rows}
    assert run.construction["version"] == THESIS_CONSTRUCTION_VERSION_V2
    assert "A_CURRENT_ROLE_OR_ANY_NUMBER_FOR_HIM" in run.construction["does_not_establish"]
    # every row is still a stacked, distinct lineup, and nobody else is over the shared cap
    share, stacked = _shape(slate, [lineup.roster for lineup in run.selected])
    assert stacked == 20 and share <= DEFAULT_PERSON_SHARE
    assert run.construction["relaxations"] == [] and run.stopped is None


def test_the_placements_spread_over_the_run_instead_of_clumping_at_the_start():
    slate, run, named = _run({"NYJ RB 4": 5})
    rows = _rows_with(slate, run, _person(slate, "NYJ RB 4"))
    assert rows[0] == 1 and rows[-1] > 20 * 3 // 5  # first row owed, last owed late
    assert max(b - a for a, b in itertools.pairwise(rows)) <= 8


def test_two_protected_people_are_each_placed_and_the_cap_binds_everyone_else():
    slate, run, named = _run({"NYJ RB 4": 4, "BUF WR 6": 6})
    assert all(run.construction["placements"]["met"].values())
    totals = Counter(
        person for lineup in run.selected for person in
        {row.underlying_id for row in slate.players if row.dk_id in lineup.roster})
    free = {person: count for person, count in totals.items() if person not in named}
    assert max(free.values()) <= person_cap(20, DEFAULT_PERSON_SHARE)


def test_a_minimum_above_the_shared_cap_holds_him_to_his_own_minimum_and_names_the_override():
    slate, run, named = _run({"NYJ RB 4": 12})
    (person,) = named
    rows = _rows_with(slate, run, person)
    cap = person_cap(20, DEFAULT_PERSON_SHARE)
    block = run.construction["placements"]
    assert len(rows) == 12 > cap and block["met"] == {person: True}
    assert block["person_cap_override"] == {person: 12}
    free = Counter(
        p for lineup in run.selected for p in {r.underlying_id for r in slate.players if r.dk_id in lineup.roster}
        if p != person)
    assert max(free.values()) <= cap


def test_a_protected_quarterback_gets_his_teams_thesis_even_when_the_ranking_left_it_out():
    slate = _slate()
    _s, plain = _thesis_run(20, slate=slate)
    teams = {item["team"] for item in plain.construction["theses"] if item["team"]}
    assert "NYJ" not in teams  # the ranking does not reach it
    slate, run, named = _run({"NYJ QB 2": 3})
    (person,) = named
    rows = _rows_with(slate, run, person)
    assert len(rows) >= 3
    tags = run.construction["lineup_theses"]
    assert all(tags[str(index)] == "STACK_NYJ" for index in rows)


def test_two_protected_quarterbacks_of_different_teams_never_share_a_row():
    slate, run, named = _run({"NYJ QB 2": 4, "BUF QB 2": 4})
    first, second = named
    assert not set(_rows_with(slate, run, first)) & set(_rows_with(slate, run, second))
    assert all(run.construction["placements"]["met"].values())


def test_a_protected_dst_and_a_protected_receiver_may_share_a_row():
    slate, run, named = _run({"NYJ DST 2": 5, "BUF WR 6": 5})
    assert all(run.construction["placements"]["met"].values())


# ----------------------------------------------------------------------------- distinct and deterministic


def test_the_rows_stay_distinct_against_prefilled_rosters_r29():
    slate = _slate()
    _s, first = _thesis_run(20, slate=slate)
    prefilled = tuple(lineup.roster for lineup in first.selected[:6])
    named = {_person(slate, "NYJ RB 4"): 5}
    slate, run = _thesis_run(20, slate=slate, protected=named, forbidden_rosters=prefilled)
    from nfl_dfs import selection
    keys = {lineup.canonical_key for lineup in run.selected}
    forbidden = {selection.roster_canonical_key(slate, roster) for roster in prefilled}
    assert len(keys) == 20 and not keys & forbidden
    assert run.construction["placements"]["met"] == {_person(slate, "NYJ RB 4"): True}


def test_the_same_inputs_give_the_same_rows_in_the_same_order():
    _s, _r, _n = _run({"NYJ RB 4": 5})
    _s2, first, _ = _run({"NYJ RB 4": 5})
    _s3, second, _ = _run({"NYJ RB 4": 5})
    assert [lineup.roster for lineup in first.selected] == [lineup.roster for lineup in second.selected]
    assert first.construction["placements"] == second.construction["placements"]


def test_with_nobody_protected_the_run_is_exactly_what_it_was():
    slate = _slate()
    _s, none = _thesis_run(20, slate=slate)
    _s, empty = _thesis_run(20, slate=slate, protected={})
    assert [lineup.roster for lineup in none.selected] == [lineup.roster for lineup in empty.selected]
    assert "placements" not in none.construction and none.construction["version"] == THESIS_CONSTRUCTION_VERSION
    assert empty.construction == none.construction


def test_a_person_the_builder_cannot_place_is_named_not_dropped_silently():
    slate = _slate()
    banned = _person(slate, "NYJ RB 4")
    excluded = tuple(row.dk_id for row in slate.players if row.underlying_id == banned)
    _s, run = _thesis_run(12, slate=slate, excluded=excluded, protected={banned: 3, "NOT|A|PERSON": 2})
    block = run.construction["placements"]
    assert block["ignored"] == {banned: "EXCLUDED_ROW", "NOT|A|PERSON": "NOT_IN_THE_SLATE"}
    assert block["requested"] == {} and not _rows_with(slate, run, banned)


# ----------------------------------------------------------------------------- a failed attempt changes nothing shared


class _CannotHold(LineupOptimizer):
    """A model that proves any row pinned with `add_required_row` infeasible, under any overlap cap."""

    pinned = False
    solves_pinned = 0

    def add_required_row(self, dk_id):
        type(self).pinned = True
        self._pin = True
        super().add_required_row(dk_id)

    def solve(self, scores):
        if getattr(self, "_pin", False):
            type(self).solves_pinned += 1
            return SolverResult(status="INFEASIBLE", roster=None, objective=None, elapsed_seconds=0.0,
                                mip_gap=None, node_count=None, validation=None, model_status="kInfeasible")
        return super().solve(scores)


def test_a_failed_attempt_to_place_him_touches_no_shared_relaxation_and_the_debt_is_named(monkeypatch):
    _CannotHold.solves_pinned = 0
    monkeypatch.setattr(classic_theses, "LineupOptimizer", _CannotHold)
    slate = _slate()
    low = _person(slate, "NYJ RB 4")
    _s, run = _thesis_run(20, slate=slate, protected={low: 5})
    construction = run.construction
    # Every row is built, distinct and stacked, as if nobody had been protected...
    assert len(run.selected) == 20 and len({lineup.canonical_key for lineup in run.selected}) == 20
    assert run.stopped is None
    # ...and no shared preference moved: no bring-back dropped, no thesis dropped, no overlap step.
    assert construction["relaxations"] == [] and run.overlap_relaxations == []
    assert construction["effective"]["person_overlap"] == CLASSIC_PERSON_OVERLAP
    assert construction["effective"]["bringback_lineups"] == 20 and construction["effective"]["stacked_lineups"] == 20
    assert all(not item["drops"] for item in construction["theses"])
    # The shortfall is named, with the rows that owed him and why they could not hold him.
    block = construction["placements"]
    organic = len(_rows_with(slate, run, low))  # whatever the prior itself rostered; no row was forced
    assert organic < 5 and block["met"] == {low: False} and block["shortfall"] == {low: 5 - organic}
    assert block["forced_rows"] == {} and block["misses"] and block["misses"][0]["people"] == [low]
    assert block["misses"][0]["reason"] == "NO_THESIS_HAD_A_DISTINCT_ROW_HOLDING_THEM"
    # ...and the attempts were budgeted: he is given up on by name after PLACEMENT_MISS_LIMIT rows, not retried on all 20
    assert len(block["misses"]) == PLACEMENT_MISS_LIMIT
    assert block["abandoned"] == {low: f"NO_THESIS_COULD_HOLD_HIM_IN_{PLACEMENT_MISS_LIMIT}_ROWS_IN_A_ROW"}
    assert _CannotHold.solves_pinned <= PLACEMENT_MISS_LIMIT * PLACEMENT_SOLVES_PER_ROW


def test_an_urgent_debt_may_loosen_the_overlap_for_that_row_alone_and_says_so(monkeypatch):
    """He is owed every row, so each is urgent. Only a looser cap than the shared one can hold him here."""

    class NeedsLooseCap(_CannotHold):
        def add_person_overlap_limit(self, roster, max_overlap):
            self._tight = True
            super().add_person_overlap_limit(roster, max_overlap)

        def solve(self, scores):
            if getattr(self, "_pin", False) and getattr(self, "_tight", False):
                return super().solve(scores)  # the stub answers INFEASIBLE under any limit
            return LineupOptimizer.solve(self, scores)

    monkeypatch.setattr(classic_theses, "LineupOptimizer", NeedsLooseCap)
    slate = _slate()
    low = _person(slate, "NYJ RB 4")
    _s, run = _thesis_run(6, slate=slate, protected={low: 6})
    construction = run.construction
    steps = [step for step in construction["relaxations"] if step["constraint"] == "classic_placement_overlap"]
    assert steps and all(step["used"] == CLASSIC_MAX_USEFUL_OVERLAP and step["from"] == CLASSIC_PERSON_OVERLAP
                         for step in steps)
    # the shared cap never moved, so later rows were still solved under it
    assert construction["effective"]["person_overlap"] == CLASSIC_PERSON_OVERLAP and run.overlap_relaxations == []
    assert construction["placements"]["met"] == {low: True}
    assert len({lineup.canonical_key for lineup in run.selected}) == 6


def test_the_report_is_recounted_from_the_delivered_rosters():
    slate, run, named = _run({"NYJ RB 4": 5})
    (person,) = named
    recount = _rows_with(slate, run, person)
    assert run.construction["placements"]["delivered_rows"][person] == recount
    assert run.construction["placements"]["rows_delivered"] == len(run.selected) == 20


def test_the_recount_refuses_a_forced_row_that_does_not_hold_the_person_it_was_solved_for(monkeypatch):
    """Mutation check: a model that ignores the pinned row is caught by the recount, not delivered."""

    class IgnoresThePin(LineupOptimizer):
        def add_required_row(self, dk_id):
            return None

    monkeypatch.setattr(classic_theses, "LineupOptimizer", IgnoresThePin)
    with pytest.raises(SelectionError, match="THESIS_CONSTRUCTION_BREACHED:placement"):
        _run({"NYJ RB 4": 5})


def test_the_forced_solves_stop_when_their_share_of_the_window_is_spent(monkeypatch):
    """A person who cannot be held must not eat the window: past a quarter of it he is abandoned, by name."""

    state = {"now": 0.0}

    class SlowToRefuse(_CannotHold):
        def solve(self, scores):
            if getattr(self, "_pin", False):
                state["now"] += 2.0  # each forced solve spends two seconds of the build's clock
            return super().solve(scores)

    monkeypatch.setattr(classic_theses, "LineupOptimizer", SlowToRefuse)
    slate = _slate()
    low = _person(slate, "NYJ RB 4")
    # window = 4 s x (20 + 1) = 84 s, so the share is 21 s: ten forced solves, fewer than the miss limit would allow
    _s, run = _thesis_run(20, slate=slate, protected={low: 5}, time_limit_seconds=4.0, clock=lambda: state["now"])
    block = run.construction["placements"]
    assert len(run.selected) == 20 and run.stopped is None  # every row still built
    assert block["abandoned"] == {low: "THE_PLACEMENT_TIME_SHARE_OF_THE_WINDOW_IS_SPENT"}
    assert block["met"] == {low: False} and "forced_solve_seconds" not in block  # no wall time in a hash-bound report
    assert len({lineup.canonical_key for lineup in run.selected}) == 20


def test_a_budget_spent_on_one_person_does_not_stop_the_others_from_being_tried_first(monkeypatch):
    """The per-row cap bounds a row's forced solves even with several people owed at once."""

    _CannotHold.solves_pinned = 0
    monkeypatch.setattr(classic_theses, "LineupOptimizer", _CannotHold)
    slate = _slate()
    named = {_person(slate, "NYJ RB 4"): 5, _person(slate, "BUF WR 6"): 5, _person(slate, "SEA TE 3"): 5}
    _s, run = _thesis_run(20, slate=slate, protected=named)
    assert len(run.selected) == 20
    assert _CannotHold.solves_pinned <= PLACEMENT_MISS_LIMIT * PLACEMENT_SOLVES_PER_ROW * len(named)
