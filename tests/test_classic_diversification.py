"""Session 39: Classic diversification.

The Classic path used to ship one lineup with 17 perturbations: C1 and the
unbound fill were cut by exact rosters only (review S3), and the C2 witness chain
was N copies of the best lineup with the quarterback swapped (review S4). These
tests run on the Session 08 to 23e Classic fixture (`tests/test_classic_portfolio_c2.py`,
102 rows over six teams) with its 20-entry policy.
"""

from __future__ import annotations

import itertools
from types import SimpleNamespace

import pytest

from nfl_dfs.selection import (
    CLASSIC_PERSON_OVERLAP,
    SelectionError,
    _sequential_lineups,
)

from .test_classic_portfolio_c2 import _objective, _slate


def _contract(slate):
    return SimpleNamespace(selectable_people=tuple(sorted({row.underlying_id for row in slate.players})))


def _people(slate, roster):
    by_id = {row.dk_id: row.underlying_id for row in slate.players}
    return frozenset(by_id[dk_id] for dk_id in roster)


def _max_shared(slate, rosters):
    return max(
        (len(_people(slate, left) & _people(slate, right)) for left, right in itertools.combinations(rosters, 2)),
        default=0,
    )


def _c1(count=20, **kwargs):
    slate = _slate()
    run = _sequential_lineups(
        slate, _objective(slate), (), _contract(slate), count=count, first_index=1,
        forbidden_rosters=kwargs.pop("forbidden_rosters", ()), differentiate_captain=False,
        max_person_overlap=4, time_limit_seconds=20.0, **kwargs,
    )
    return slate, run


def test_the_default_classic_cap_is_six_and_c1_rows_respect_it():
    """Old code: the Classic cap was None, so each row was the last one minus a player (8 shared)."""

    assert CLASSIC_PERSON_OVERLAP == 6
    slate, run = _c1()
    rosters = [lineup.roster for lineup in run.selected]
    assert len(rosters) == 20 and len({lineup.canonical_key for lineup in run.selected}) == 20
    assert _max_shared(slate, rosters) <= 6
    assert run.effective_overlap == 6 and run.overlap_relaxations == []
    differentiation = run.differentiation(slate)
    assert differentiation["max_person_overlap"] == 6
    assert differentiation["requested_person_overlap"] == 6
    assert differentiation["overlap_relaxations"] == []


@pytest.mark.parametrize("cap", (4, 5, 7))
def test_a_tighter_and_a_looser_cap_are_each_respected(cap):
    slate, run = _c1(classic_person_overlap=cap)
    rosters = [lineup.roster for lineup in run.selected]
    assert len(rosters) == 20
    assert _max_shared(slate, rosters) <= cap
    assert run.overlap_relaxations == []


def test_no_cap_keeps_the_old_exact_roster_only_behaviour_for_diagnostics():
    slate, run = _c1(classic_person_overlap=None)
    rosters = [lineup.roster for lineup in run.selected]
    assert _max_shared(slate, rosters) == 8  # each optimum is the previous one minus a person
    assert run.effective_overlap is None
    assert run.differentiation(slate)["max_person_overlap"] is None


# -- S4: the witness chain ---------------------------------------------------

from nfl_dfs.classic_portfolio import build_classic_candidate_bank, candidate_bank_bytes, solve_classic_portfolio

from .test_classic_portfolio_c2 import _policy


def _chain(bank):
    return [c for c in bank.candidates if c.source_stratum == "policy_feasible_chain"]


def _bank(entry_count, overlap):
    controls = {"max_pairwise_person_overlap": overlap}
    slate, policy, *_ = _policy(entry_count, controls=controls)
    return slate, policy, build_classic_candidate_bank(slate, _objective(slate), policy)


@pytest.mark.parametrize("overlap", (5, 6, 7))
def test_the_witness_chain_respects_the_policy_overlap(overlap):
    """Old code: the chain was single swaps of one seed (7 to 8 shared), so a policy
    overlap below 8 left the bank with no feasible witness at all."""

    slate, policy, bank = _bank(20, overlap)
    chain = _chain(bank)
    assert chain, bank.as_report()
    assert max(len(a.people & b.people) for a, b in itertools.combinations(chain, 2)) <= overlap
    assert bank.feasible_chain_status == "POLICY_FEASIBLE"
    selection = solve_classic_portfolio(policy, bank)
    assert selection.passed
    chosen = [bank.candidates[i] for i in bank.feasible_chain_indexes]
    assert len(chosen) == 20 and len({c.canonical_key for c in chosen}) == 20
    assert max(len(a.people & b.people) for a, b in itertools.combinations(chosen, 2)) <= overlap


def test_the_chain_is_not_one_lineup_with_the_quarterback_swapped():
    """Round-robin over seeds and slots: with no overlap constraint the neighbours still
    come from several seeds and change several slots."""

    slate, policy, bank = _bank(20, 9)
    seeds = [c for c in bank.candidates if c.source_stratum != "policy_feasible_chain"]
    origins, slots = set(), set()
    for member in _chain(bank):
        near = [s for s in seeds if sum(a != b for a, b in zip(s.roster, member.roster)) == 1]
        assert near, "every chain member is one swap from a MILP seed when nothing caps overlap"
        origins.add(near[0].roster)
        slots.add(next(i for i, (a, b) in enumerate(zip(near[0].roster, member.roster)) if a != b))
    assert len(origins) >= 3 and len(slots) >= 3


def test_the_chain_is_deterministic_at_a_tight_overlap():
    _slate_a, policy, first = _bank(20, 6)
    _slate_b, _policy_b, second = _bank(20, 6)
    assert candidate_bank_bytes(policy, first) == candidate_bank_bytes(policy, second)


# -- S6: the unbound fill applies the policy's own exclusions ----------------

def test_the_fill_exclusions_are_the_runs_and_the_policys_exact_ones():
    """Old code: the fill used the run's exclusions only, so a person the policy
    excludes (or caps at zero, or whose team or game it caps at zero) could fill a row."""

    from nfl_dfs.selection import _fill_exclusions

    slate = _slate()
    people = {row.underlying_id: row for row in slate.players}
    out, zero = people["NE|WR|1"], people["DAL|RB|1"]
    controls = {
        "exact_exclusions": [{"underlying_id": out.underlying_id, "dk_id": out.dk_id}],
        "player_exposure_bounds": [{"underlying_id": zero.underlying_id, "dk_id": zero.dk_id,
                                    "minimum_entries": 0, "maximum_entries": 0, "hard": True}],
        "team_exposure_bounds": [{"team": "BUF", "minimum_entries": 0, "maximum_entries": 0, "hard": True}],
    }
    _slate_again, policy, *_ = _policy(4, controls=controls)
    buf = {row.dk_id for row in slate.players if row.team == "BUF"}
    run_out = "82000099"
    fill = set(_fill_exclusions((run_out,), policy))
    assert {run_out, out.dk_id, zero.dk_id} | buf <= fill
    bare = set(_fill_exclusions((run_out,), None))
    assert bare == {run_out}  # no policy, nothing added


# -- the run-level reports ---------------------------------------------------

def test_a_run_with_no_policy_still_names_a_cap_step_its_c1_took(tmp_path, monkeypatch):
    """No ladder, so no `relaxation` record: the step is still a named limitation."""

    from functools import partial

    from nfl_dfs import prior_review

    from .test_entry_groups import _run_slate

    monkeypatch.setattr(prior_review, "select_prior_lineups",
                        partial(prior_review.select_prior_lineups, classic_person_overlap=2))
    code, report, _entries, _root = _run_slate(tmp_path, monkeypatch, run_id="c1-no-policy-cap", entries=3)
    assert code == 0, report["blockers"]
    assert "relaxation" not in report
    texts = [text for text in report["blockers"] if text.startswith("RELAXATION_STRUCTURE_RELAXED:")]
    assert texts and "classic_person_overlap 2 to" in texts[0] and all("C1 row" in text for text in texts)
    from .test_deadline_controller import _truth_codes

    assert _truth_codes(report)["RELAXATION_STRUCTURE_RELAXED"] == "S"


# -- the unbound fill --------------------------------------------------------

def test_the_fill_rows_are_capped_against_the_policy_lineups_and_each_other():
    """Old code: a fill row was a near copy of a bound one (8 shared), cut by exact rosters only."""

    from nfl_dfs.selection import _fill_unbound

    slate, near_copies = _c1(3, classic_person_overlap=None)  # three bound rows that share 8 with each other
    policy_lineups = list(near_copies.selected)
    lineups, report = _fill_unbound(
        slate, _objective(slate), (), _contract(slate), policy_lineups=policy_lineups,
        forbidden_rosters=(), count=5, differentiate_captain=False, max_person_overlap=4,
        time_limit_seconds=20.0)
    fill = [lineup.roster for lineup in lineups[3:]]
    assert len(fill) == 5 and [lineup.index for lineup in lineups[3:]] == [4, 5, 6, 7, 8]
    for roster in fill:
        for bound in policy_lineups:
            assert len(_people(slate, roster) & _people(slate, bound.roster)) <= 6
    assert _max_shared(slate, fill) <= 6
    assert len({lineup.canonical_key for lineup in lineups}) == 8
    differentiation = report["differentiation"]
    assert differentiation["max_person_overlap"] == 6 and differentiation["overlap_relaxations"] == []
    assert report["exclusions"] == "THE_RUN_S_OWN_AND_THE_POLICY_S_EXACT_EXCLUSIONS"


def test_a_cap_no_lineup_fits_under_is_stepped_up_reported_and_never_repeats_a_lineup():
    """Twenty rows sharing no person need 180 of the pool's 102 rows, so the cap has to give."""

    slate, run = _c1(20, classic_person_overlap=0)
    rosters = [lineup.roster for lineup in run.selected]
    assert len({lineup.canonical_key for lineup in run.selected}) == 20  # R29
    steps = run.overlap_relaxations
    assert steps and all(step["requested"] == 0 and step["from"] < step["used"] <= 8 for step in steps)
    assert all(step["reason"] == "NO_DISTINCT_LINEUP_UNDER_THE_REQUESTED_OVERLAP_CAP" for step in steps)
    assert all(step["trigger_status"] == "INFEASIBLE" for step in steps)
    # A ratchet: each step starts where the last ended, and there are at most 8 of them,
    # however many rows there are, which is what the deadline's per-solve sizing can afford.
    assert steps[0]["from"] == 0 and len(steps) <= 8
    assert all(later["from"] == earlier["used"] for earlier, later in zip(steps, steps[1:]))
    assert [step["index"] for step in steps] == sorted({step["index"] for step in steps})
    assert run.effective_overlap == steps[-1]["used"]
    assert _max_shared(slate, rosters) <= run.effective_overlap
    differentiation = run.differentiation(slate)
    assert differentiation["requested_person_overlap"] == 0
    assert differentiation["max_person_overlap"] == run.effective_overlap
    # Every row shares at most the cap in force when it was built with every earlier row.
    cap = 0
    for lineup in run.selected:
        cap = next((step["used"] for step in steps if step["index"] == lineup.index), cap)
        for earlier in run.selected[: lineup.index - 1]:
            assert len(_people(slate, lineup.roster) & _people(slate, earlier.roster)) <= cap


def test_a_solve_that_ends_on_a_time_limit_is_not_read_as_an_infeasible_cap(monkeypatch):
    """Only a proven infeasible model steps the cap: a timeout falls to the R29 refusal, as before."""

    from dataclasses import replace

    from nfl_dfs import selection

    class TimesOut(selection.LineupOptimizer):
        calls = 0

        def solve(self, objective):
            result = super().solve(objective)
            TimesOut.calls += 1
            return replace(result, roster=None, status="NO_SOLUTION") if TimesOut.calls == 2 else result

    monkeypatch.setattr(selection, "LineupOptimizer", TimesOut)
    with pytest.raises(SelectionError) as caught:
        _c1(3, classic_person_overlap=6)
    assert caught.value.status == "SOLVER_RETURNED_NO_LINEUP" and "status=NO_SOLUTION" in str(caught.value)
    assert TimesOut.calls == 2  # no loosened model was built and solved


def test_a_pool_that_runs_out_of_distinct_lineups_still_raises_and_never_repeats():
    """R29 is not on the cap's walk: with one distinct lineup available the second row is refused."""

    slate = _slate()
    objective = _objective(slate)
    (only,) = _sequential_lineups(
        slate, objective, (), _contract(slate), count=1, first_index=1, forbidden_rosters=(),
        differentiate_captain=False, max_person_overlap=4, time_limit_seconds=20.0).selected[:1]
    keep = set(only.roster)
    excluded = tuple(row.dk_id for row in slate.players if row.dk_id not in keep)
    with pytest.raises(SelectionError) as caught:
        _sequential_lineups(
            slate, objective, excluded, _contract(slate), count=2, first_index=1, forbidden_rosters=(),
            differentiate_captain=False, max_person_overlap=4, time_limit_seconds=20.0)
    assert caught.value.status == "SOLVER_RETURNED_NO_LINEUP" and caught.value.facts["selected"] == 1


def test_a_classic_fill_that_runs_out_of_distinct_lineups_returns_its_rows_and_never_repeats():
    """Session 39b (R29): a pool holding one distinct lineup gives one fill row, and the rest are named.

    The sequential run (C1 with no policy) still raises on the same pool
    (`test_a_pool_that_runs_out_of_distinct_lineups_still_raises_and_never_repeats`).
    """

    from nfl_dfs.selection import _fill_unbound

    slate = _slate()
    objective = _objective(slate)
    (only,) = _sequential_lineups(
        slate, objective, (), _contract(slate), count=1, first_index=1, forbidden_rosters=(),
        differentiate_captain=False, max_person_overlap=4, time_limit_seconds=20.0).selected[:1]
    excluded = tuple(row.dk_id for row in slate.players if row.dk_id not in set(only.roster))

    rows, report = _fill_unbound(
        slate, objective, excluded, _contract(slate), policy_lineups=[], forbidden_rosters=(), count=3,
        differentiate_captain=False, max_person_overlap=4, time_limit_seconds=20.0)
    assert [row.roster for row in rows] == [only.roster]
    assert (report["requested"], report["lineups"], report["unfilled_rows"]) == (3, 1, 2)
    assert report["stopped"] == {"index": 2, "status": "INFEASIBLE", "proved_exhausted": True}

    # The one lineup the pool holds is already a bound row: the fill builds none, and says so.
    rows, report = _fill_unbound(
        slate, objective, excluded, _contract(slate), policy_lineups=[only], forbidden_rosters=(), count=2,
        differentiate_captain=False, max_person_overlap=4, time_limit_seconds=20.0)
    assert [row.roster for row in rows] == [only.roster]  # the bound row, once, never cycled
    assert (report["lineups"], report["unfilled_rows"]) == (0, 2)
    assert report["stopped"]["index"] == 2 and report["stopped"]["proved_exhausted"] is True


def test_a_fill_row_cap_step_reaches_the_ladder_record_with_its_scope(tmp_path, monkeypatch):
    """The subset policy's C1 fill takes the same walk, and its steps say `UNBOUND_FILL`."""

    from functools import partial

    from nfl_dfs import prior_review

    from .test_entry_groups import _classic_subset_run

    monkeypatch.setattr(prior_review, "select_prior_lineups",
                        partial(prior_review.select_prior_lineups, classic_person_overlap=0))
    code, report, _entries, _root, _slate_used, _prefilled = _classic_subset_run(
        tmp_path, monkeypatch, run_id="fill-cap-step")
    assert code == 0, report["blockers"]
    steps = [item for item in report["relaxation"]["relaxations"] if item["step"] == "OVERLAP_CAP"]
    assert steps and all(item["trigger_detail"].startswith("UNBOUND_FILL row ") for item in steps)
    assert steps[0]["original"] == 0 and steps[0]["limitation_code"] == "RELAXATION_STRUCTURE_RELAXED"
    assert any("UNBOUND_FILL row" in text for text in report["blockers"])
