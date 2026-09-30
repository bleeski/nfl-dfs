"""Session 49: Classic rung 4 as several stack theses under one person share cap.

Rung 4 (no policy) used to be C1: one construction repeated. The 2026-09-27 Week 3
file held three people in 25 of 25 lineups and no stack. These tests pin the
construction on the Session 08 to 23e Classic fixture (102 rows, six teams) and, for
the acceptance, through `run-slate` on a pool wide enough to hold the cap.
"""

from __future__ import annotations

import itertools
from collections import Counter
from functools import partial
from types import SimpleNamespace

import pytest

from nfl_dfs import classic_theses, selection
from nfl_dfs.classic_theses import DEFAULT_PERSON_SHARE, person_cap, rank_stack_teams, select_thesis_lineups
from nfl_dfs.dk import parse_salaries
from nfl_dfs.selection import CLASSIC_PERSON_OVERLAP, SelectionError, _sequential_lineups

from .test_classic_portfolio_c2 import _objective, _slate

WIDE = {"QB": 1, "RB": 3, "WR": 4, "TE": 2, "DST": 1}


def _contract(slate):
    return SimpleNamespace(selectable_people=tuple(sorted({row.underlying_id for row in slate.players})))


def _thesis_run(count=20, slate=None, excluded=(), **kwargs):
    slate = slate or _slate()
    kwargs.setdefault("classic_person_overlap", CLASSIC_PERSON_OVERLAP)
    kwargs.setdefault("time_limit_seconds", 20.0)
    run = select_thesis_lineups(slate, _objective(slate), excluded, _contract(slate), count=count, **kwargs)
    return slate, run


def _plain_c1(count=20):
    slate = _slate()
    return slate, _sequential_lineups(
        slate, _objective(slate), (), _contract(slate), count=count, first_index=1, forbidden_rosters=(),
        differentiate_captain=False, max_person_overlap=4, time_limit_seconds=20.0)


def _shape(slate, rosters):
    """(largest share of rows one person is in, lineups with a QB and a teammate WR/TE)."""

    by_id = {row.dk_id: row for row in slate.players}
    exposure = Counter(by_id[dk_id].underlying_id for roster in rosters for dk_id in roster)
    stacked = 0
    for roster in rosters:
        qb = next(by_id[dk_id] for dk_id in roster if by_id[dk_id].position == "QB")
        stacked += any(by_id[dk_id].team == qb.team and by_id[dk_id].position in {"WR", "TE"} for dk_id in roster)
    return max(exposure.values()) / len(rosters), stacked


# ---------------------------------------------------------------- the construction


def test_plain_c1_on_this_fixture_is_the_concentration_the_card_describes():
    """Old rung 4: the same people again and again, and a stack only where the optimum had one."""

    slate, run = _plain_c1()
    share, _stacked = _shape(slate, [lineup.roster for lineup in run.selected])
    assert share > DEFAULT_PERSON_SHARE


def test_theses_keep_every_person_at_forty_percent_and_stack_every_lineup():
    slate, run = _thesis_run(20)
    rosters = [lineup.roster for lineup in run.selected]
    share, stacked = _shape(slate, rosters)
    assert len(rosters) == 20 and len({lineup.canonical_key for lineup in run.selected}) == 20
    assert share <= DEFAULT_PERSON_SHARE and stacked == 20
    construction = run.construction
    assert construction["version"] == "classic_thesis_sequential_v1"
    assert construction["relaxations"] == [] and run.overlap_relaxations == [] and run.stopped is None
    assert construction["effective"]["person_cap"] == person_cap(20, DEFAULT_PERSON_SHARE) == 8
    assert construction["effective"]["stacked_lineups"] == 20
    assert "ANY_EXPECTED_VALUE_PAYOUT_OR_WIN_PROBABILITY" in construction["does_not_establish"]


def test_the_rows_come_from_several_theses_each_with_its_own_quarterback_team():
    slate, run = _thesis_run(20)
    construction = run.construction
    live = [item for item in construction["theses"] if item["rows"]]
    assert len(live) >= 4 and construction["effective"]["distinct_qb_teams"] >= 4
    by_id = {row.dk_id: row for row in slate.players}
    for item in live:
        for index in item["rows"]:
            roster = run.selected[index - 1].roster
            qb = next(by_id[d] for d in roster if by_id[d].position == "QB")
            assert qb.team == item["team"]
    # round robin over the live theses: quotas differ by at most one row
    sizes = [len(item["rows"]) for item in live]
    assert max(sizes) - min(sizes) <= 1
    # one thesis per game before any game gets a second team
    games = {by_id[next(d for d in run.selected[item["rows"][0] - 1].roster if by_id[d].position == "QB")].game_id
             for item in live}
    assert len(games) == 3 and len(live) == 4


def test_every_lineup_keeps_the_bringback_and_the_overlap_cap_when_nothing_is_relaxed():
    slate, run = _thesis_run(20)
    by_id = {row.dk_id: row for row in slate.players}
    assert run.construction["effective"]["bringback_lineups"] == 20
    people = [frozenset(by_id[d].underlying_id for d in lineup.roster) for lineup in run.selected]
    assert max(len(a & b) for a, b in itertools.combinations(people, 2)) <= CLASSIC_PERSON_OVERLAP
    assert run.differentiation(slate)["basis"].startswith("THESIS_SEQUENTIAL")


def test_a_larger_portfolio_holds_the_same_bounds():
    slate, run = _thesis_run(60)
    share, stacked = _shape(slate, [lineup.roster for lineup in run.selected])
    assert len(run.selected) == 60 and share <= DEFAULT_PERSON_SHARE and stacked == 60


def test_the_same_inputs_give_the_same_rows_in_the_same_order():
    _slate_a, first = _thesis_run(20)
    _slate_b, second = _thesis_run(20)
    assert [lineup.roster for lineup in first.selected] == [lineup.roster for lineup in second.selected]
    assert first.construction["theses"] == second.construction["theses"]
    assert first.construction["lineup_theses"] == second.construction["lineup_theses"]


def test_a_prefilled_roster_is_never_repeated_across_theses_r29():
    _slate_a, first = _thesis_run(20)
    prefilled = tuple(lineup.roster for lineup in first.selected[:6])
    slate, run = _thesis_run(20, forbidden_rosters=prefilled)
    keys = {lineup.canonical_key for lineup in run.selected}
    forbidden = {selection.roster_canonical_key(slate, roster) for roster in prefilled}
    assert len(keys) == 20 and not (keys & forbidden)


def test_an_excluded_row_never_enters_any_thesis():
    slate = _slate()
    banned = tuple(row.dk_id for row in slate.players if row.team == "NE" and row.position in {"QB", "WR"})
    _slate_b, run = _thesis_run(12, slate=slate, excluded=banned)
    assert not (set(banned) & {dk_id for lineup in run.selected for dk_id in lineup.roster})
    assert all(item["team"] != "NE" for item in run.construction["theses"])
    ranked = [team for team, _value, _game in rank_stack_teams(slate, _objective(slate), banned)]
    assert "NE" not in ranked


# ---------------------------------------------------------------- relaxation and named gaps


def test_a_cap_the_pool_cannot_hold_steps_up_ten_points_at_a_time_and_each_step_is_reported():
    slate, run = _thesis_run(20, max_person_share=0.05)
    steps = [item for item in run.construction["relaxations"] if item["constraint"] == "classic_person_share"]
    assert steps and steps[0]["from"] == 0.05 and steps[0]["used"] == 0.15
    assert len(run.selected) == 20 and len({lineup.canonical_key for lineup in run.selected}) == 20
    effective = run.construction["effective"]
    assert effective["person_share"] > 0.05 and effective["max_person_rows"] <= effective["person_cap"]
    for step in steps:
        assert step["trigger_status"] in {"INFEASIBLE", "PERSON_CAP_REACHED"} and step["thesis"] == "ALL"


def test_the_stack_holds_until_the_share_reaches_sixty_percent_then_goes_by_name():
    slate, run = _thesis_run(20, max_person_share=0.05)
    names = [item["constraint"] for item in run.construction["relaxations"]]
    dropped = names.index("classic_qb_stack") if "classic_qb_stack" in names else len(names)
    shares = [item["used"] for item in run.construction["relaxations"][:dropped]
              if item["constraint"] == "classic_person_share"]
    assert all(value <= classic_theses.STACK_HOLD_SHARE + 1e-9 for value in shares)
    if "classic_qb_stack" in names:
        assert run.construction["effective"]["stack_required"] is False


def test_a_thesis_whose_quarterbacks_reach_the_cap_is_dropped_by_name_not_by_a_wrong_relaxation():
    """Two stack teams at 20 rows: each quarterback is capped at 8, so the wall is the person cap.

    The bring-back and the overlap cap are not touched for it; the drops are reported as
    `classic_thesis` records and the share steps once, 40% to 50% (a cap of 10), which finishes.
    """

    slate = _slate()
    banned = tuple(row.dk_id for row in slate.players
                   if row.position == "QB" and not (row.team in {"NE", "SEA"} and row.underlying_id.endswith("|1")))
    _slate_b, run = _thesis_run(20, slate=slate, excluded=banned)
    relaxations = run.construction["relaxations"]
    names = [item["constraint"] for item in relaxations]
    assert len(run.selected) == 20 and run.stopped is None
    assert "classic_bringback" not in names and run.overlap_relaxations == []
    assert names.count("classic_thesis") == 2 and names.count("classic_person_share") == 1
    (step,) = [item for item in relaxations if item["constraint"] == "classic_person_share"]
    assert (step["from"], step["used"], step["trigger_status"]) == (0.4, 0.5, "PERSON_CAP_REACHED")
    assert all(item["used"] == "DROPPED" and item["trigger_status"] == "PERSON_CAP_REACHED"
               for item in relaxations if item["constraint"] == "classic_thesis")
    effective = run.construction["effective"]
    assert effective["person_cap"] == 10 and effective["max_person_rows"] <= 10
    assert effective["max_person_share_of_delivered_rows"] == effective["max_person_rows"] / 20


def test_the_selectors_own_backstop_refuses_a_model_that_breaks_the_cap_or_the_stack(monkeypatch):
    """Mutation check: a model that ignores a bound is caught by the recomputation, not delivered."""

    from nfl_dfs.optimizer import LineupOptimizer

    real_count = LineupOptimizer.add_selected_count_bounds
    monkeypatch.setattr(
        LineupOptimizer, "add_selected_count_bounds",
        lambda self, dk_ids, **kwargs: None if kwargs.get("maximum") == 0 else real_count(self, dk_ids, **kwargs))
    with pytest.raises(SelectionError, match="THESIS_CONSTRUCTION_BREACHED:person_share"):
        _thesis_run(20)
    monkeypatch.undo()

    real_corr = LineupOptimizer.add_classic_qb_correlation_bounds
    monkeypatch.setattr(
        LineupOptimizer, "add_classic_qb_correlation_bounds",
        lambda self, *, kind, **kwargs: None if kind == "PASS_CATCHER" else real_corr(self, kind=kind, **kwargs))
    with pytest.raises(SelectionError, match="THESIS_CONSTRUCTION_BREACHED:stack"):
        _thesis_run(20)


def _one_team_slate_and_ban(slate):
    """Every row but one legal lineup's: NE's QB, three RBs, three WRs and a TE, and DAL's DST.

    Three RBs put the third in FLEX, so exactly one set of nine exists; the DST from another game
    meets the two-game rule, and with no SEA row the bring-back cannot be met.
    """

    limits = {"QB": 1, "RB": 3, "WR": 3, "TE": 1}
    taken: Counter = Counter()
    keep = set()
    for row in slate.players:
        if row.team == "NE" and taken[row.position] < limits.get(row.position, 0):
            taken[row.position] += 1
            keep.add(row.dk_id)
        if row.team == "DAL" and row.position == "DST" and "DST" not in taken:
            taken["DST"] += 1
            keep.add(row.dk_id)
    return tuple(row.dk_id for row in slate.players if row.dk_id not in keep)


def test_a_pool_that_runs_out_of_distinct_lineups_returns_the_rows_it_built_and_says_so():
    slate = _slate()
    banned = _one_team_slate_and_ban(slate)
    _slate_b, run = _thesis_run(3, slate=slate, excluded=banned)
    assert len(run.selected) == 1
    assert run.stopped is not None and run.stopped["proved_exhausted"] is True and run.stopped["index"] == 2
    assert run.construction["unfilled_rows"] == 2 and run.construction["stopped"] == run.stopped
    names = [item["constraint"] for item in run.construction["relaxations"]]
    assert "classic_bringback" in names  # a one-team pool has no bring-back


def test_a_run_that_builds_no_row_raises_as_c1_does():
    slate = _slate()
    everyone = tuple(row.dk_id for row in slate.players)
    with pytest.raises(SelectionError) as raised:
        _thesis_run(3, slate=slate, excluded=everyone)
    assert raised.value.status == "SOLVER_RETURNED_NO_LINEUP"


def test_the_time_budget_stops_the_run_with_the_rows_it_has_and_names_it():
    ticks = itertools.count()
    clock = lambda: next(ticks) * 1.0  # noqa: E731 - each call advances one second
    slate, run = _thesis_run(20, time_limit_seconds=0.5, clock=clock)  # 0.5 s x 21 = 10.5 s window
    assert 0 < len(run.selected) < 20
    assert run.stopped["status"] == "TIME_BUDGET" and run.stopped["proved_exhausted"] is False
    assert len({lineup.canonical_key for lineup in run.selected}) == len(run.selected)


# ---------------------------------------------------------------- the selector's switch


def test_showdown_and_a_policy_refuse_the_classic_construction():
    from nfl_dfs.contracts import EngineMode

    slate = _slate()
    assert slate.mode is EngineMode.CLASSIC
    with pytest.raises(SelectionError, match="MODE_NOT_SUPPORTED"):
        selection.select_prior_lineups(slate, None, {}, _contract(slate), count=1, classic_construction="FREEHAND")


def test_the_default_selector_is_still_plain_c1():
    """`run_prior_review` called directly keeps plain C1; `cli` asks for the theses on Classic with no policy."""

    assert "classic_construction" in selection.select_prior_lineups.__kwdefaults__
    assert selection.select_prior_lineups.__kwdefaults__["classic_construction"] is None


# ---------------------------------------------------------------- run-slate: the acceptance


def _run_shape(tmp_path, report):
    from .test_relaxation_controller import _exported_rosters

    slate = parse_salaries(tmp_path / "attachments" / "salary.csv")
    rosters = [tuple(roster) for roster in _exported_rosters(report)]
    return slate, rosters, _shape(slate, rosters)


def _infeasible_joint_solve(monkeypatch):
    from dataclasses import replace

    real = selection.solve_classic_portfolio

    def infeasible(policy, bank, **kwargs):
        return replace(real(policy, bank, **kwargs), status="MODELED_BANK_INFEASIBILITY",
                       selected_candidate_indexes=())

    monkeypatch.setattr(selection, "solve_classic_portfolio", infeasible)


def test_a_rung_4_run_has_no_player_over_forty_percent_and_every_lineup_stacked(tmp_path, monkeypatch):
    """The card's acceptance: fails on the tree before Session 49 (one construction, repeated)."""

    from .test_relaxation_controller import _classic, _policy_file, _truth_codes

    _infeasible_joint_solve(monkeypatch)
    code, report, _root = _classic(tmp_path, monkeypatch, run_id="rung4-theses", entries=10, depth=WIDE,
                                   policy=lambda attachments: _policy_file(attachments))
    assert code == 0 and report["improvement"]["status"] == "DELIVERED", report["blockers"]
    relaxation = report["relaxation"]
    assert relaxation["final_rung"] == "4" and relaxation["final_policy"] is None
    (drop,) = [item for item in relaxation["relaxations"] if item["constraint"] == "portfolio_policy"]
    assert drop["final"]["construction"] == "classic_thesis_sequential_v1"
    _slate_c, rosters, (share, stacked) = _run_shape(tmp_path, report)
    assert len(rosters) == 10 and len(set(rosters)) == 10
    assert share <= DEFAULT_PERSON_SHARE and stacked == 10
    assert report["RELEASE_DECISION"] == "DO_NOT_UPLOAD" and report["MODEL_STATUS"] == "PRIOR_ONLY"
    assert "V" not in _truth_codes(report).values()
    assert report["release_truths"]["unfilled_entry_ids"] == []


def test_a_run_that_supplies_no_policy_builds_the_same_way(tmp_path, monkeypatch):
    from .test_relaxation_controller import _classic

    code, report, _root = _classic(tmp_path, monkeypatch, run_id="no-policy-theses", entries=10, depth=WIDE,
                                   policy=None)
    assert code == 0 and report["improvement"]["status"] == "DELIVERED", report["blockers"]
    _slate_c, rosters, (share, stacked) = _run_shape(tmp_path, report)
    assert len(rosters) == 10 and len(set(rosters)) == 10
    assert share <= DEFAULT_PERSON_SHARE and stacked == 10


def test_a_thesis_run_that_stops_short_delivers_its_rows_and_names_the_rest(tmp_path, monkeypatch):
    """Session 39b's named gap, on rung 4: k rows are written, the tail Entry IDs stay blank and are named."""

    from nfl_dfs.contracts import EngineMode
    from nfl_dfs.lineups import read_assignment_csv
    from nfl_dfs.prior_review import run_prior_review
    from nfl_dfs.projection import build_projection_package

    from .test_classic_prior_review import AS_OF, _fixture

    real = classic_theses.select_thesis_lineups
    ticks = itertools.count()
    # 10 s x 11 rows is the window; a clock that moves 40 s a look runs it out after a few rows
    monkeypatch.setattr(selection, "select_thesis_lineups", partial(real, clock=lambda: next(ticks) * 40.0))
    salary, entry, package, role, status, _ = _fixture(tmp_path / "fx", entries=10, depth=WIDE)
    outcome = run_prior_review(
        salary_csv=salary, entry_csv=entry, label="thesis-partial", as_of=AS_OF, run_root=tmp_path / "run",
        output_root=tmp_path / "out", prior_package_dir=package, build_priors=True, official_status_csv=status,
        offensive_role_evidence_json=role, project=build_projection_package, classic_construction="THESES")
    assert outcome.file_valid, outcome.blockers
    built = len(outcome.reports["selection"]["lineups"])
    assert 0 < built < 10
    assert outcome.unfilled_entry_ids == tuple(f"{910000001 + index}" for index in range(built, 10))
    chosen = outcome.reports["selection"]["selection"]
    assert chosen["stopped"]["status"] == "TIME_BUDGET" and chosen["unfilled_rows"] == 10 - built
    written = read_assignment_csv(outcome.artifacts["assignments"], EngineMode.CLASSIC)
    assert list(written) == [f"{910000001 + index}" for index in range(built)]
    assert len({tuple(roster) for roster in written.values()}) == built


def test_the_delivery_pointer_keeps_a_fuller_baseline_over_a_partial_thesis_file(tmp_path, monkeypatch):
    """Observed 2026-09-30: the coverage rule (Session 05) refuses a replacement with fewer rows, so a
    rung 4 that stops short leaves the baseline as the file; the gap is named, not hidden."""

    from .test_relaxation_controller import _classic

    real = classic_theses.select_thesis_lineups
    ticks = itertools.count()
    monkeypatch.setattr(selection, "select_thesis_lineups", partial(real, clock=lambda: next(ticks) * 1.0))
    code, report, root = _classic(tmp_path, monkeypatch, run_id="thesis-partial-run", entries=10, depth=WIDE,
                                  policy=None, window=6.0)
    assert code == 2 and "DELIVERY_POINTER_COVERAGE_REGRESSION" in report["improvement"]["reasons"]
    assert report["DELIVERY_STATE"] == "DELIVERABLE" and report["latest_deliverable"]["producer"] == "run-slate:baseline"
