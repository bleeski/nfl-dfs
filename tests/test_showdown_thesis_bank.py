"""Session 23c layer 2: the candidate bank, the quota solve and the joint probe for a portfolio of Showdown theses.

Every candidate names the theses it follows (recomputed, never inherited), one solve fills exactly each thesis's
allotment, a lineup is used once whichever theses it serves, and a thesis that collides with an earlier one is named
before any bank is built. A thesis is a choice, not a forecast.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import replace
from decimal import Decimal

from nfl_dfs.portfolio_enforcement import (
    build_policy_candidate_bank,
    plan_captain_strata,
    probe_thesis_rows,
    run_lockstep,
    solve_policy_portfolio,
    thesis_contexts,
)
from nfl_dfs.portfolio_policy import thesis_roster_violations

from .test_showdown_theses import _prepared, _thesis
from .test_showdown_thesis_portfolio import SIX, _policy_v4, _three


def _world(tmp_path, *, entries=SIX, theses=_three, **controls):
    """The synthetic NE@SEA slate, a v4 policy over `entries`, a salary-shaped objective, the unavailable rows."""

    tmp_path.mkdir(parents=True, exist_ok=True)
    slate, *_rest = _prepared(tmp_path)
    policy, _raw = _policy_v4(slate, theses(slate), entries, **controls)
    objective = {row.dk_id: row.salary / 1000.0 for row in slate.players}
    unavailable = tuple(row.dk_id for row in slate.players if row.status_raw in {"OUT", "IR"})
    return slate, policy, objective, unavailable


def _bank(slate, policy, objective, unavailable, *, limit=80, seconds=30, forbidden=()):
    return build_policy_candidate_bank(
        slate, objective, excluded_ids=unavailable, candidate_limit=limit, total_time_limit_seconds=seconds,
        per_solve_time_limit_seconds=2, policy=policy, forbidden_rosters=forbidden)


def _selected(bank, selection):
    return [(bank.candidates[index], name)
            for index, name in zip(selection.selected_candidate_indexes, selection.selected_theses)]


def test_every_candidate_names_exactly_the_theses_it_follows(tmp_path):
    slate, policy, objective, unavailable = _world(tmp_path)
    bank = _bank(slate, policy, objective, unavailable)
    assert bank.candidates
    for candidate in bank.candidates:
        expected = tuple(thesis.name for thesis in policy.active_theses
                         if not thesis_roster_violations(slate, candidate.roster, thesis))
        assert candidate.serves == expected and candidate.serves
    report = bank.as_report()["theses"]
    assert {name: row["rows"] for name, row in report.items()} == {
        "NE_WIN_BIG": 2, "NE_WIN_CLOSE_LOW": 2, "SEA_WIN_BIG": 2}
    assert all(row["serving"] >= row["rows"] for row in report.values())


def test_captain_strata_are_sized_to_the_theses_rows_not_the_whole_portfolio(tmp_path):
    slate, policy, objective, unavailable = _world(tmp_path, entries=tuple(str(n) for n in range(1, 13)))
    context = thesis_contexts(slate, policy)[0]
    assert context.rows == 4
    gone = (*unavailable, *context.excluded_dk_ids)
    seeded, depth = plan_captain_strata(policy, objective, excluded_ids=gone, entries=context.rows)
    _all_seeded, depth_all = plan_captain_strata(policy, objective, excluded_ids=gone)
    assert depth == math.ceil(context.rows / len(seeded)) + 1
    assert depth < depth_all  # a four-row thesis is not seeded as if it held all twelve entries


def test_the_joint_solve_fills_exactly_the_allotment_of_each_thesis(tmp_path):
    slate, policy, objective, unavailable = _world(tmp_path)
    bank = _bank(slate, policy, objective, unavailable)
    selection = solve_policy_portfolio(policy, bank, time_limit_seconds=20)
    assert selection.passed, selection.status
    picks = _selected(bank, selection)
    assert len(picks) == 6
    assert Counter(name for _c, name in picks) == {"NE_WIN_BIG": 2, "NE_WIN_CLOSE_LOW": 2, "SEA_WIN_BIG": 2}
    theses = {thesis.name: thesis for thesis in policy.active_theses}
    for candidate, name in picks:
        assert name in candidate.serves
        assert not thesis_roster_violations(slate, candidate.roster, theses[name])
    assert len({candidate.canonical_key for candidate, _name in picks}) == 6  # distinct across theses (R29)


def test_a_roster_that_serves_two_theses_is_used_once(tmp_path):
    def twins(slate):
        first = _thesis(slate, ["Starter QB", "Alpha WR"], name="A", teams=["NE"])
        return [first, {**first, "name": "B"}]

    slate, policy, objective, unavailable = _world(tmp_path, theses=twins)
    bank = _bank(slate, policy, objective, unavailable)
    assert all(candidate.serves == ("A", "B") for candidate in bank.candidates)
    selection = solve_policy_portfolio(policy, bank, time_limit_seconds=20)
    assert selection.passed, selection.status
    picks = _selected(bank, selection)
    assert len({candidate.canonical_key for candidate, _name in picks}) == 6
    assert Counter(name for _c, name in picks) == {"A": 3, "B": 3}


def test_a_thesis_with_too_few_candidates_makes_the_joint_solve_infeasible(tmp_path):
    slate, policy, objective, unavailable = _world(tmp_path)
    bank = _bank(slate, policy, objective, unavailable)
    starved = [replace(candidate, serves=tuple(name for name in candidate.serves if name != "SEA_WIN_BIG"))
               for candidate in bank.candidates]
    only_one = next(index for index, candidate in enumerate(bank.candidates) if "SEA_WIN_BIG" in candidate.serves)
    starved[only_one] = bank.candidates[only_one]
    complete = replace(bank, candidates=tuple(starved), complete=True, status="COMPLETE_MODELED_BANK")
    selection = solve_policy_portfolio(policy, complete, time_limit_seconds=20)
    assert not selection.passed and selection.status == "MODELED_BANK_INFEASIBLE_PROVEN"


def test_a_prefilled_roster_is_never_in_the_bank_or_the_selection(tmp_path):
    slate, policy, objective, unavailable = _world(tmp_path)
    free = _bank(slate, policy, objective, unavailable)
    first = solve_policy_portfolio(policy, free, time_limit_seconds=20)
    prefilled = tuple(candidate.roster for candidate, _name in _selected(free, first))
    bank = _bank(slate, policy, objective, unavailable, forbidden=prefilled)
    assert not {candidate.roster for candidate in bank.candidates} & set(prefilled)
    selection = solve_policy_portfolio(policy, bank, time_limit_seconds=20)
    assert selection.passed, selection.status
    assert not {candidate.roster for candidate, _name in _selected(bank, selection)} & set(prefilled)


def test_the_share_limit_holds_when_every_thesis_wants_the_same_star(tmp_path):
    def stars(slate):
        return [_thesis(slate, [captain], name=name, teams=["NE", "SEA"])
                for name, captain in (("Q1", "Starter QB"), ("W1", "Alpha WR"), ("Q2", "Sea QB"), ("W2", "Sea Alpha WR"))]

    entries = tuple(str(n) for n in range(1, 11))
    slate, policy, objective, unavailable = _world(
        tmp_path, entries=entries, theses=stars,
        max_combined_person_exposure={"default_fraction": Decimal("0.6"), "overrides": []})
    bank = _bank(slate, policy, objective, unavailable, limit=120)
    selection = solve_policy_portfolio(policy, bank, time_limit_seconds=30)
    assert selection.passed, selection.status
    counts = Counter(person for candidate, _name in _selected(bank, selection) for person in candidate.people)
    assert max(counts.values()) <= 6  # floor(0.6 * 10): one limit across every thesis


def test_kicker_and_dst_captains_appear_where_a_thesis_requires_them(tmp_path):
    def scripts(slate):
        return [_thesis(slate, ["NE Kicker"], name="K_CAPTAIN", teams=["NE"]),
                _thesis(slate, ["Patriots"], name="DST_CAPTAIN", teams=["NE"]),
                _thesis(slate, ["Starter QB", "Sea QB"], name="QB_CAPTAIN", teams=["NE", "SEA"])]

    slate, policy, objective, unavailable = _world(tmp_path, theses=scripts)
    bank = _bank(slate, policy, objective, unavailable)
    selection = solve_policy_portfolio(policy, bank, time_limit_seconds=20)
    assert selection.passed, selection.status
    by_id = {row.dk_id: row for row in slate.players}
    captains = {name: sorted({by_id[candidate.roster[0]].name for candidate, picked in _selected(bank, selection)
                              if picked == name}) for name in ("K_CAPTAIN", "DST_CAPTAIN", "QB_CAPTAIN")}
    assert captains["K_CAPTAIN"] == ["NE Kicker"] and captains["DST_CAPTAIN"] == ["Patriots"]
    assert set(captains["QB_CAPTAIN"]) <= {"Starter QB", "Sea QB"}


def test_the_lockstep_chain_is_a_cap_legal_portfolio(tmp_path):
    slate, policy, objective, unavailable = _world(
        tmp_path,
        max_combined_person_exposure={"default_fraction": Decimal("0.67"), "overrides": []},
        max_captain_exposure={"default_fraction": Decimal("0.34"), "overrides": []},
        max_pairwise_person_overlap=4)
    contexts = thesis_contexts(slate, policy)
    result = run_lockstep(
        slate, objective, contexts, excluded_ids=unavailable, forbidden_rosters=(), chain_policy=policy,
        targets={context.thesis.name: context.rows for context in contexts}, per_solve_seconds=2, total_seconds=30)
    assert dict(result.found) == {context.thesis.name: context.rows for context in contexts}
    limits = {item.person.underlying_id: item for item in policy.effective_limits}
    by_id = {row.dk_id: row for row in slate.players}
    people = [frozenset(by_id[dk_id].underlying_id for dk_id in roster) for _name, roster in result.rosters]
    assert len({roster for _name, roster in result.rosters}) == len(result.rosters)
    for person, count in Counter(person for group in people for person in group).items():
        assert count <= limits[person].combined_max_entries
    for person, count in Counter(by_id[roster[0]].underlying_id for _name, roster in result.rosters).items():
        assert count <= limits[person].captain_max_entries
    assert all(len(left & right) <= 4 for index, left in enumerate(people) for right in people[index + 1:])
    theses = {context.thesis.name: context.thesis for context in contexts}
    assert all(not thesis_roster_violations(slate, roster, theses[name]) for name, roster in result.rosters)


# ------------------------------------------------------------------ the joint probe


_SEVEN = ("NE Kicker", "Starter QB", "Lead RB", "Alpha WR", "Patriots", "Sea QB", "Sea Alpha WR")


def _only_these_people(slate, names):
    keep = set(names)
    return tuple(row.dk_id for row in slate.players if row.name not in keep)


def _two_kicker_theses(slate):
    first = _thesis(slate, ["NE Kicker"], name="A", teams=["NE"])
    return [first, {**first, "name": "B"}]


def test_the_probe_names_a_thesis_that_collides_with_an_earlier_one(tmp_path):
    entries = tuple(str(n) for n in range(1, 9))
    slate, policy, objective, _unavailable = _world(tmp_path, entries=entries, theses=_two_kicker_theses)
    gone = _only_these_people(slate, _SEVEN)
    # Seven people leave five legal lineups under a kicker Captain (the sixth breaks the cap). A takes four of them
    # (declared order is the priority); B asked for four and finds the one that is left.
    probe = probe_thesis_rows(slate, objective, policy, excluded_ids=gone, per_solve_seconds=2, total_seconds=30)
    assert [(item.name, item.wanted) for item in probe.short] == [("B", 4)]
    assert probe.short[0].found == 1 and dict(probe.found) == {"A": 4, "B": 1}
    # Each thesis alone has room for its four rows, which is why an independent per-thesis probe passes both.
    for only in ("A", "B"):
        alone = [item for item in _two_kicker_theses(slate) if item["name"] == only]
        policy_alone, _raw = _policy_v4(slate, alone, tuple(str(n) for n in range(1, 5)))
        assert not probe_thesis_rows(slate, objective, policy_alone, excluded_ids=gone, per_solve_seconds=2,
                                     total_seconds=30).short


def test_the_probe_passes_theses_that_have_room_for_every_row(tmp_path):
    slate, policy, objective, unavailable = _world(tmp_path)
    probe = probe_thesis_rows(slate, objective, policy, excluded_ids=unavailable, per_solve_seconds=2, total_seconds=30)
    assert not probe.short and not probe.unproven
    assert dict(probe.found) == {"NE_WIN_BIG": 2, "NE_WIN_CLOSE_LOW": 2, "SEA_WIN_BIG": 2}


def test_a_probe_solve_a_limit_stopped_proves_nothing(tmp_path, monkeypatch):
    from nfl_dfs import portfolio_enforcement
    from nfl_dfs.optimizer import SolverResult

    slate, policy, objective, unavailable = _world(tmp_path)
    stopped = SolverResult("NO_SOLUTION", None, None, 0.0, None, None, None, "kTimeLimit")
    monkeypatch.setattr(portfolio_enforcement.LineupOptimizer, "solve", lambda self, scores: stopped)
    probe = probe_thesis_rows(slate, objective, policy, excluded_ids=unavailable, per_solve_seconds=2, total_seconds=30)
    assert not probe.short and set(probe.unproven) == {"NE_WIN_BIG", "NE_WIN_CLOSE_LOW", "SEA_WIN_BIG"}


def test_the_bank_and_the_selection_are_deterministic(tmp_path):
    first = _world(tmp_path / "a")
    second = _world(tmp_path / "b")
    banks = [_bank(*world) for world in (first, second)]
    assert [(c.roster, c.serves) for c in banks[0].candidates] == [(c.roster, c.serves) for c in banks[1].candidates]
    picks = [solve_policy_portfolio(world[1], bank, time_limit_seconds=20) for world, bank in zip((first, second), banks)]
    assert (picks[0].selected_candidate_indexes, picks[0].selected_theses) == (
        picks[1].selected_candidate_indexes, picks[1].selected_theses)
