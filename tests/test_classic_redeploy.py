"""Session 64 (R37): the Pareto salary redeploy as engine code, and its stage at the end of the rung-4 thesis build.

Three layers. (1) The rule on a small synthetic slate (the Session 08 to 23e Classic fixture: six teams in three
games), where a swap's existence, its refusal and the goal it would hurt are worked out by hand. (2) The committed
Week 4 inputs (`DKSalaries.csv`, the operator portfolios, the score dump), where the lifted rule must reproduce
Session 62's recorded numbers exactly and never touch a locked cell. (3) The stage inside `select_thesis_lineups`
(the report, the window states, never fatal, the one backstop) and what reads it (`non_optimal_lineups`, the
limitation, the coverage key). Nothing here touches the network.

Clock discipline: Week 4 kicked off 2026-10-04 and the synthetic fixture is dated 2026-09-13, both earlier than today,
so a test that leaves the lock clock to the wall clock locks every cell and passes at zero swaps while testing
nothing. Every test that expects the redeploy to act pins `now` before the first kickoff (or passes no lock clock) and
asserts `locked_people == 0`; the lock tests pin it deliberately between windows.
"""

from __future__ import annotations

import ast
import collections
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from nfl_dfs import classic_redeploy as cr
from nfl_dfs import classic_theses, cli, selection
from nfl_dfs.classic_theses import select_thesis_lineups
from nfl_dfs.deadline import Budget, activated
from nfl_dfs.dk import parse_salaries
from nfl_dfs.gate_registry import load_gate_registry
from nfl_dfs.lineups import roster_canonical_key, validate_lineup
from nfl_dfs.optimizer import LineupOptimizer
from nfl_dfs.selection import CLASSIC_PERSON_OVERLAP, SelectedLineup

from .test_classic_portfolio_c2 import _objective, _slate

REPO_ROOT = Path(__file__).resolve().parent.parent
WEEK4 = REPO_ROOT / "data" / "inbox" / "slates" / "wk4-classic-2026-10-04"

SLATE = _slate()
BY_ID = {player.dk_id: player for player in SLATE.players}
BY_NAME = {player.name: player.dk_id for player in SLATE.players}
PERSON = {dk_id: player.underlying_id for dk_id, player in BY_ID.items()}
ET = timezone(timedelta(hours=-4))
BEFORE_THE_FIXTURE_LOCKS = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)  # NE@SEA locks at 18:00Z
BETWEEN_THE_FIXTURE_WINDOWS = datetime(2026, 9, 13, 19, 0, tzinfo=timezone.utc)  # after NE@SEA, before the 20:25Z games


def ids(*names):
    return [BY_NAME[name] for name in names]


def row(rb1, rb2, wr3, flex, *, qb="NE QB 1", dst="DAL DST 1", te="NE TE 1"):
    """A legal slot-ordered Classic roster: a NE stack (two NE receivers and a NE tight end), a DAL defense, and the
    four cells a redeploy may move (two running backs, a receiver and the flex). Everything else on the roster is the
    QB's team or the opponent's (the redeployer's `core`) or the DST, so only those four cells are ever outgoing."""

    cells = ids(qb, rb1, rb2, "NE WR 1", "NE WR 2", wr3, te, flex, dst)
    ordered = cr.slot_order(BY_ID, cells)
    assert ordered is not None and validate_lineup(SLATE, ordered).valid
    return ordered


def scores_with(**by_name):
    scores = {player.dk_id: 10.0 for player in SLATE.players}
    for name, value in by_name.items():
        scores[BY_NAME[name.replace("_", " ")]] = value
    return scores


def portfolio(*rows):
    return {str(index): roster for index, roster in enumerate(rows, start=1)}


def four_rows():
    return portfolio(
        row("DAL RB 1", "BUF RB 1", "BUF WR 1", "NYJ WR 1"),
        row("DAL RB 2", "BUF RB 2", "BUF WR 2", "NYJ WR 2"),
        row("DAL RB 3", "BUF RB 3", "BUF WR 3", "NYJ WR 3"),
        row("DAL RB 4", "BUF RB 4", "BUF WR 4", "NYJ WR 4"),
    )


def redeploy(rows, scores=None, **kwargs):
    kwargs.setdefault("exposure_limit", 99)
    kwargs.setdefault("overlap_cap", 9)
    return cr.redeploy(SLATE, scores or scores_with(NYJ_WR_5=25.0), rows, **kwargs)


def recount(rosters):
    """The four washout proxies counted again from scratch, independently of `washout_proxies`."""

    people = [[PERSON[i] for i in roster] for roster in rosters.values()]
    exposure = collections.Counter(p for roster in people for p in roster)
    top3 = [p for p, _n in exposure.most_common(3)]
    return {
        "max_exposure": max(exposure.values()),
        "top3_union": sum(1 for roster in people if any(p in roster for p in top3)),
        "pair_overlap_sum": sum(n * (n - 1) // 2 for n in exposure.values()),
        "distinct_people": len(exposure),
    }


def no_proxy_worse(before, after):
    return (after["max_exposure"] <= before["max_exposure"] and after["top3_union"] <= before["top3_union"]
            and after["pair_overlap_sum"] <= before["pair_overlap_sum"]
            and after["distinct_people"] >= before["distinct_people"])


def names_of(roster):
    return [BY_ID[i].name for i in roster]


# ----------------------------------------------------------------------------------------- the proxies


def test_the_proxies_are_counted_as_tier_two_counts_them_and_compared_exactly():
    rows = four_rows()
    got = cr.washout_proxies(rows.values())
    assert {k: got[k] for k in ("max_exposure", "top3_union", "pair_overlap_sum", "distinct_people")} == recount_ids(rows)
    assert got["mean_overlap"] == got["pair_overlap_sum"] / 6
    assert cr.washout_proxies([["a"]])["mean_overlap"] == 0.0  # no pair, nothing to average
    assert cr.washout_proxies([])["distinct_people"] == 0


def recount_ids(rosters):
    exposure = collections.Counter(i for roster in rosters.values() for i in roster)
    top3 = [i for i, _n in exposure.most_common(3)]
    return {
        "max_exposure": max(exposure.values()),
        "top3_union": sum(1 for roster in rosters.values() if any(i in roster for i in top3)),
        "pair_overlap_sum": sum(n * (n - 1) // 2 for n in exposure.values()),
        "distinct_people": len(exposure),
    }


@pytest.mark.parametrize("field,value,goal", [
    ("max_exposure", 6, "max_exposure"), ("top3_union", 5, "top3_union"), ("pair_overlap_sum", 11, "mean_overlap"),
    ("distinct_people", 8, "distinct_people"),
])
def test_each_proxy_that_is_worse_is_named_and_a_tie_is_not_worse(field, value, goal):
    base = {"max_exposure": 5, "top3_union": 4, "pair_overlap_sum": 10, "distinct_people": 9}
    assert cr.proxies_hurt(base, dict(base)) == []
    assert cr.proxies_hurt(base, {**base, field: value}) == [goal]
    better = {**base, "max_exposure": 4, "top3_union": 3, "pair_overlap_sum": 9, "distinct_people": 10}
    assert cr.proxies_hurt(base, better) == []


# ------------------------------------------------------------------------------------- slot order, clock


def test_slot_order_is_what_the_optimizer_emits_and_any_shuffle_comes_back_to_it():
    result = LineupOptimizer(SLATE, time_limit_seconds=20.0).solve(_objective(SLATE))
    assert result.roster is not None
    for shuffle in (list(reversed(result.roster)), list(result.roster[3:] + result.roster[:3])):
        assert cr.slot_order(BY_ID, shuffle) == tuple(result.roster)
    assert validate_lineup(SLATE, result.roster).valid


def test_slot_order_refuses_what_cannot_fill_the_slots():
    cells = list(row("DAL RB 1", "BUF RB 1", "BUF WR 1", "NYJ WR 1"))
    assert cr.slot_order(BY_ID, cells[:8]) is None  # eight cells
    two_qbs = [BY_NAME["SEA QB 1"] if i == BY_NAME["NYJ WR 1"] else i for i in cells]
    assert cr.slot_order(BY_ID, two_qbs) is None
    one_rb = [BY_NAME["NYJ WR 2"] if i == BY_NAME["BUF RB 1"] else i for i in cells]  # one running back, five receivers
    assert cr.slot_order(BY_ID, one_rb) is None
    assert cr.slot_order(BY_ID, cells[:-1] + ["not-a-dk-id"]) is None


def test_locked_ids_are_the_games_that_kicked_off_and_a_naive_clock_is_refused():
    assert cr.locked_dk_ids(SLATE, BEFORE_THE_FIXTURE_LOCKS) == frozenset()
    locked = cr.locked_dk_ids(SLATE, BETWEEN_THE_FIXTURE_WINDOWS)
    assert locked == {i for i, p in BY_ID.items() if p.team in {"NE", "SEA"}}
    assert cr.locked_dk_ids(SLATE, datetime(2026, 9, 13, 18, 0, tzinfo=timezone.utc)) == locked  # at the kickoff: locked
    with pytest.raises(ValueError, match="REDEPLOY_NOW_NOT_TIMEZONE_AWARE"):
        cr.locked_dk_ids(SLATE, datetime(2026, 9, 13, 19, 0))


# -------------------------------------------------------------------------------------- the rule itself


def test_a_pareto_swap_is_taken_and_both_goals_are_reported():
    before_rows = four_rows()
    result = redeploy(before_rows)
    report = result.report
    assert report["rule"] == "pareto_redeploy_v2" and report["state"] == "COMPLETED"
    assert report["fixed_point"] is True and report["locked_people"] == 0
    assert report["accepted_total"] == 1 and result.changed == ["1"] == report["changed_entry_ids"]
    (swap,) = report["accepted"]
    # The two running-back cells would leave one running back (illegal); the first receiver cell is the first legal one.
    assert (swap["entry_id"], swap["out_name"], swap["in_name"], swap["prior_gain"]) == ("1", "BUF WR 1", "NYJ WR 5", 15.0)
    assert report["after"]["prior_sum"] == report["before"]["prior_sum"] + 15.0
    after_rows = result.rosters
    assert after_rows["2"] == before_rows["2"] and after_rows["1"] != before_rows["1"]
    assert no_proxy_worse(recount(before_rows), recount(after_rows))
    assert validate_lineup(SLATE, after_rows["1"]).valid
    assert [report["after"][k] for k in ("max_exposure", "top3_union", "distinct_people")] == [
        recount(after_rows)[k] for k in ("max_exposure", "top3_union", "distinct_people")]
    assert report["before"]["distinct_people"] == 5 + 4 * 4  # the five shared people and each row's four own


def test_a_prior_raising_swap_that_would_hurt_a_goal_is_refused_with_the_goal_named():
    report = redeploy(four_rows()).report
    # Once the target is in row 1, moving him into another row raises a prior but adds a use of a person already used
    # (mean overlap) and drops the outgoing person from the portfolio (distinct people).
    assert report["rejected_total"] == 6 and report["refusal_scan"] == "COMPLETE"
    assert report["rejected_by_goal"] == {"max_exposure": 0, "top3_union": 0, "mean_overlap": 6, "distinct_people": 6}
    assert all(record["hurts"] == ["mean_overlap", "distinct_people"] for record in report["rejected"])
    assert {record["entry_id"] for record in report["rejected"]} == {"2", "3", "4"}
    # Into a running-back cell the same swap leaves one running back: a row-level refusal, not a goal trade.
    assert report["row_rejections"] == {"ILLEGAL": 6, "SHAPE": 0, "CAPS_OR_DISTINCT": 0}
    assert report["available_at_stop"] == 0


def test_with_no_prior_gain_the_portfolio_stays_and_the_report_says_so():
    result = redeploy(four_rows(), scores_with())
    assert result.changed == [] and result.report["accepted_total"] == 0 and result.report["state"] == "COMPLETED"
    assert result.rosters == four_rows()
    assert any(line.startswith("NO_PARETO_GAIN") for line in cr.render_report(result.report))


def test_a_protected_person_never_moves_in_or_out_and_the_next_swap_is_taken_instead():
    rows = four_rows()
    target = BY_NAME["NYJ WR 5"]
    plain = redeploy(rows)
    assert plain.report["accepted"][0]["out_name"] == "BUF WR 1"
    protected_out = redeploy(rows, protect=[BY_NAME["BUF WR 1"]])
    assert protected_out.report["accepted"][0]["out_name"] == "NYJ WR 1"
    assert BY_NAME["BUF WR 1"] in protected_out.rosters["1"]
    both = redeploy(rows, protect=[BY_NAME["BUF WR 1"], BY_NAME["NYJ WR 1"]])
    assert [(s["entry_id"], s["out_name"]) for s in both.report["accepted"]] == [("2", "BUF WR 2")]
    for result in (protected_out, both):
        for person in result.report["protected"]:
            assert person["rows_before"] == person["rows_after"] == 1
    never_in = redeploy(rows, protect=[target])
    assert never_in.report["accepted_total"] == 0 and never_in.rosters == rows
    assert never_in.report["protected"][0]["rows_after"] == 0


def test_a_gated_person_or_one_with_a_status_never_comes_in():
    rows = four_rows()
    assert redeploy(rows, gated=[BY_NAME["NYJ WR 5"]]).report["accepted_total"] == 0
    statused = SLATE.model_copy(update={"players": tuple(
        p.model_copy(update={"status_raw": "Q"}) if p.name == "NYJ WR 5" else p for p in SLATE.players)})
    assert cr.redeploy(statused, scores_with(NYJ_WR_5=25.0), rows, exposure_limit=99, overlap_cap=9).report["accepted_total"] == 0


def test_the_qb_the_dst_and_the_stack_and_bring_back_are_never_touched():
    rows = portfolio(
        row("DAL RB 1", "BUF RB 1", "BUF WR 1", "SEA WR 1"),  # SEA WR 1 is the bring-back
        row("DAL RB 2", "BUF RB 2", "BUF WR 2", "NYJ WR 2"),
        row("DAL RB 3", "BUF RB 3", "BUF WR 3", "NYJ WR 3"),
    )
    scores = scores_with(NYJ_WR_5=25.0, NE_WR_1=1.0, SEA_WR_1=1.0, NE_QB_1=1.0, DAL_DST_1=1.0, NE_TE_1=1.0)
    result = redeploy(rows, scores)
    core = set(ids("NE QB 1", "NE WR 1", "NE WR 2", "NE TE 1", "SEA WR 1", "DAL DST 1"))
    for entry, roster in result.rosters.items():
        assert core & set(rows[entry]) <= set(roster), "a core cell moved"
    assert result.report["accepted_total"] >= 1


def test_a_repeated_roster_is_refused_and_the_next_swap_is_taken():
    first = row("DAL RB 1", "BUF RB 1", "BUF WR 1", "NYJ WR 1")
    clone = row("DAL RB 1", "BUF RB 1", "NYJ WR 5", "NYJ WR 1")  # the first row with the target already in
    # BUF WR 1 -> NYJ WR 5 would make row 1 exactly row 2 (R29): refused; NYJ WR 1 -> NYJ WR 5 is distinct and taken.
    result = redeploy(portfolio(first, clone))
    assert [(s["out_name"], s["in_name"]) for s in result.report["accepted"]] == [("NYJ WR 1", "NYJ WR 5")]
    assert len({roster_canonical_key(SLATE, r) for r in result.rosters.values()}) == 2
    # With the other receiver protected the duplicate is the only swap on offer: nothing is taken, and the scan counts it.
    only = redeploy(portfolio(first, clone), protect=[BY_NAME["NYJ WR 1"]], row_ids=["1"])
    assert only.report["accepted_total"] == 0 and only.rosters == portfolio(first, clone)
    assert only.report["row_rejections"] == {"ILLEGAL": 2, "SHAPE": 0, "CAPS_OR_DISTINCT": 1}


def test_a_row_that_converges_on_an_earlier_rows_new_roster_is_refused():
    # Row 1 takes the target in place of BUF WR 1 and becomes {core, DAL RB 1, BUF RB 1, NYJ WR 5, NYJ WR 1}. Row 2 is row 1
    # with BUF WR 2 where BUF WR 1 was, and BUF WR 2 is also in row 3, so moving the target into row 2 in place of BUF WR 2
    # passes the proxies and would make row 2 exactly row 1's NEW roster (R29). The rule must know row 1 changed.
    rows = portfolio(
        row("DAL RB 1", "BUF RB 1", "BUF WR 1", "NYJ WR 1"),
        row("DAL RB 1", "BUF RB 1", "BUF WR 2", "NYJ WR 1"),
        row("DAL RB 3", "BUF RB 3", "NYJ WR 3", "BUF WR 2"),
    )
    result = redeploy(rows)
    keys = [roster_canonical_key(SLATE, roster) for roster in result.rosters.values()]
    assert len(set(keys)) == 3
    first = next(s for s in result.report["accepted"] if s["entry_id"] == "1")
    assert (first["out_name"], first["in_name"]) == ("BUF WR 1", "NYJ WR 5")
    assert BY_NAME["BUF WR 2"] in result.rosters["2"]  # the converging swap was the one refused; row 2 took another


def test_a_locked_person_never_changes_slot_when_a_changed_row_is_put_in_slot_order():
    rows = portfolio(row("DAL RB 4", "BUF RB 1", "BUF WR 1", "NYJ RB 1"), row("DAL RB 3", "BUF RB 2", "BUF WR 2", "NYJ RB 2"))
    unlocked = redeploy(rows).rosters["1"]
    moved = [p for p in rows["1"] if p in unlocked and rows["1"].index(p) != unlocked.index(p)]
    assert moved, "the unlocked swap re-orders the row: the case is real"
    for person in moved:
        held = redeploy(rows, locked={person}).rosters["1"]
        assert person in held and held.index(person) == rows["1"].index(person)
    nobody_moves = redeploy(rows, locked=set(moved)).rosters["1"]
    assert all(nobody_moves.index(p) == rows["1"].index(p) for p in moved if p in nobody_moves)


def test_a_roster_the_entry_template_already_holds_is_refused():
    rows = four_rows()
    plain_swap = tuple(BY_NAME["NYJ WR 5"] if i == BY_NAME["BUF WR 1"] else i for i in rows["1"])
    other_swap = tuple(BY_NAME["NYJ WR 5"] if i == BY_NAME["NYJ WR 1"] else i for i in rows["1"])
    forbidden = {roster_canonical_key(SLATE, plain_swap)}
    result = redeploy(rows, forbidden_keys=forbidden)
    assert [(s["out_name"], s["in_name"]) for s in result.report["accepted"]] == [("NYJ WR 1", "NYJ WR 5")]
    assert roster_canonical_key(SLATE, result.rosters["1"]) not in forbidden
    both = {roster_canonical_key(SLATE, plain_swap), roster_canonical_key(SLATE, other_swap)}
    shut = redeploy(rows, forbidden_keys=both, row_ids=["1"])
    assert shut.report["accepted_total"] == 0 and shut.rosters == rows
    assert shut.report["row_rejections"]["CAPS_OR_DISTINCT"] == 2


def test_a_lock_clock_keeps_a_locked_person_out_of_both_directions():
    rows = four_rows()
    target_row = portfolio(row("DAL RB 1", "BUF RB 1", "BUF WR 1", "NYJ WR 1"),
                           row("DAL RB 2", "BUF RB 2", "BUF WR 2", "NYJ WR 2"))
    # The target is a SEA person here, so his game (NE@SEA, 18:00Z) is the one that locks.
    scores = scores_with(SEA_WR_5=25.0)
    early = cr.redeploy(SLATE, scores, target_row, exposure_limit=99, overlap_cap=9,
                        locked=cr.locked_dk_ids(SLATE, BEFORE_THE_FIXTURE_LOCKS))
    assert early.report["locked_people"] == 0 and early.report["accepted"][0]["in_name"] == "SEA WR 5"
    late_locks = cr.locked_dk_ids(SLATE, BETWEEN_THE_FIXTURE_WINDOWS)
    late = cr.redeploy(SLATE, scores, target_row, exposure_limit=99, overlap_cap=9, locked=late_locks)
    assert late.report["accepted_total"] == 0 and late.rosters == target_row  # a locked person is never incoming
    assert late.report["locked_people"] == len({PERSON[i] for i in late_locks}) > 0
    # And never outgoing: lock the outgoing receiver's game (BUF@NYJ is open; lock BUF WR 1 itself).
    out_locked = redeploy(rows, locked={BY_NAME["BUF WR 1"]})
    assert out_locked.report["accepted"][0]["out_name"] == "NYJ WR 1" and BY_NAME["BUF WR 1"] in out_locked.rosters["1"]


def test_changed_rows_come_out_in_slot_order_and_script_rows_keep_their_cells():
    # Three running backs, the first-by-ID of them (DAL RB 4) in a running-back slot: replacing him by a receiver leaves two
    # running backs and four receivers, legal only once the cells are re-ordered (the receiver cannot sit in his old slot).
    rows = portfolio(row("DAL RB 4", "BUF RB 1", "BUF WR 1", "NYJ RB 1"), row("DAL RB 3", "BUF RB 2", "BUF WR 2", "NYJ RB 2"))
    assert rows["1"].index(BY_NAME["DAL RB 4"]) < 7  # it sits in a RB slot, not the flex
    in_slot_order = redeploy(rows, slot_ordered=True)
    (swap,) = in_slot_order.report["accepted"]
    assert swap["out_name"] == "DAL RB 4" and swap["in_name"] == "NYJ WR 5"
    ordered = in_slot_order.rosters["1"]
    assert validate_lineup(SLATE, ordered).valid and ordered == cr.slot_order(BY_ID, ordered)
    in_place = redeploy(rows, slot_ordered=False)
    cells = in_place.rosters["1"]
    assert cells == tuple(BY_NAME["NYJ WR 5"] if i == BY_NAME["DAL RB 4"] else i for i in rows["1"])
    assert not validate_lineup(SLATE, cells).valid  # in place, the receiver sits in a running-back slot: the engine would refuse it as written
    assert set(cells) == set(ordered)  # the same people either way
    assert in_place.rosters["2"] == rows["2"]


def test_a_clash_the_row_did_not_have_is_never_added_and_one_it_had_is_never_worse():
    # DAL's defense plays PHI: a PHI skill player beside it is a DST-against-own-skill clash.
    rows = portfolio(row("DAL RB 1", "BUF RB 1", "BUF WR 1", "NYJ WR 1"), row("DAL RB 2", "BUF RB 2", "BUF WR 2", "NYJ WR 2"))
    result = redeploy(rows, scores_with(PHI_WR_5=25.0))
    assert result.report["accepted_total"] == 0 and result.report["row_rejections"]["ILLEGAL"] >= 1
    clashing = portfolio(row("DAL RB 1", "BUF RB 1", "BUF WR 1", "PHI WR 1"), row("DAL RB 2", "BUF RB 2", "BUF WR 2", "NYJ WR 2"))
    again = redeploy(clashing, scores_with(NYJ_WR_5=25.0))  # a row that already clashes is still redeployable
    assert again.report["accepted_total"] >= 1


def test_per_person_limits_are_honoured_where_one_scalar_cap_would_pass_the_swap():
    rows = four_rows()
    assert redeploy(rows, exposure_limit=99).report["accepted_total"] == 1
    target_person = PERSON[BY_NAME["NYJ WR 5"]]
    held = redeploy(rows, exposure_limit=lambda person: 0 if person == target_person else 99)
    assert held.report["accepted_total"] == 0 and held.rosters == rows
    assert held.report["row_rejections"]["CAPS_OR_DISTINCT"] > 0


def test_per_pair_caps_are_honoured_where_one_scalar_cap_would_pass_the_swap():
    # O (BUF WR 1) is in rows 1 and 3, the target in row 2 only: moving him into row 1 keeps every proxy but raises the
    # overlap of rows 1 and 2 from the five core people to six. A cap between that pair stops it; one loose scalar does not.
    rows = portfolio(
        row("DAL RB 1", "BUF RB 1", "BUF WR 1", "NYJ WR 1"),
        row("DAL RB 2", "BUF RB 2", "BUF WR 2", "NYJ WR 5"),
        row("DAL RB 3", "BUF RB 3", "NYJ WR 3", "BUF WR 1"),
    )
    assert redeploy(rows, overlap_cap=9).report["accepted_total"] == 1
    capped = redeploy(rows, overlap_cap=lambda first, second: 5 if "2" in (first, second) else 9)
    assert capped.report["accepted_total"] == 0 and capped.rosters == rows
    assert capped.report["row_rejections"]["CAPS_OR_DISTINCT"] > 0


def test_a_salary_floor_the_operator_passed_binds_the_swap():
    rows = four_rows()
    swapped = sum(BY_ID[i].salary for i in rows["1"]) - BY_ID[BY_NAME["BUF WR 1"]].salary + BY_ID[BY_NAME["NYJ WR 5"]].salary
    assert redeploy(rows, min_salary=swapped).report["accepted"][0]["entry_id"] == "1"  # a floor the new row meets
    assert redeploy(rows, min_salary=49_000).report["accepted_total"] == 0  # one no swapped row reaches: refused
    assert redeploy(rows, min_salary=0).report["accepted_total"] == 1  # and no floor is inherited from anywhere


def test_a_row_the_caller_does_not_let_change_still_counts_in_the_proxies():
    rows = four_rows()
    only_row_two = redeploy(rows, row_ids=["2"])
    assert only_row_two.changed == ["2"] and only_row_two.report["rows_considered"] == 1
    assert only_row_two.report["before"]["rows"] == 4  # the proxies read every row
    with pytest.raises(ValueError, match="REDEPLOY_ROW_UNKNOWN"):
        redeploy(rows, row_ids=["9"])
    with pytest.raises(ValueError, match="REDEPLOY_DK_ID_NOT_IN_POOL"):
        redeploy({"1": rows["1"][:8] + ("nobody",)})
    assert redeploy({}).report["state"] == "NOT_APPLICABLE"


# ---------------------------------------------------------------------------------- the report's bounds


def many_swaps():
    """Three unused targets and four rows: three accepted swaps and a pile of refusals."""

    return four_rows(), scores_with(NYJ_WR_5=25.0, NYJ_WR_6=24.0, DAL_WR_5=23.0)


def test_the_report_carries_no_time_and_replays_byte_identically():
    rows, scores = many_swaps()
    first = json.dumps(redeploy(rows, scores).report, sort_keys=True)
    assert first == json.dumps(redeploy(rows, scores).report, sort_keys=True)

    def keys(value):
        if isinstance(value, dict):
            for key, item in value.items():
                yield key
                yield from keys(item)
        elif isinstance(value, list):
            for item in value:
                yield from keys(item)
    assert not [k for k in keys(json.loads(first)) if any(word in k for word in ("second", "elapsed", "time", "clock"))]


def test_stored_lists_are_bounded_by_count_and_the_totals_stay_exact():
    rows, scores = many_swaps()
    full = redeploy(rows, scores).report
    assert full["accepted_total"] == 3 and len(full["accepted"]) == 3 and full["stored_limit"] is None
    small = redeploy(rows, scores, stored_limit=2).report
    assert small["accepted_total"] == 3 and len(small["accepted"]) == 2 and small["accepted"] == full["accepted"][:2]
    assert small["rejected_total"] == full["rejected_total"] > 2 and len(small["rejected"]) == 2
    assert small["rejected_by_goal"] == full["rejected_by_goal"] and small["row_rejections"] == full["row_rejections"]
    largest = sorted((r["prior_gain"] for r in full["rejected"]), reverse=True)[:2]
    assert [r["prior_gain"] for r in small["rejected"]] == largest  # the largest gains, not the first found
    assert small["stored_limit"] == 2
    assert redeploy(rows, scores, stored_limit=0).report["accepted"] == []


# ------------------------------------------------------------------------- the window, as states not seconds


def test_a_stop_before_any_work_is_a_deadline_state_and_the_portfolio_is_as_it_was(monkeypatch):
    monkeypatch.setattr(cr, "POLL_EVERY", 1)
    rows, scores = many_swaps()
    result = redeploy(rows, scores, stop=lambda: True)
    report = result.report
    assert report["state"] == "DEADLINE_STOP" and report["fixed_point"] is False and result.rosters == rows
    assert report["accepted_total"] == 0 and report["refusal_scan"] == "NOT_RUN"
    assert report["rejected_total"] is None and report["rejected_by_goal"] is None and report["rejected"] == []
    lines = cr.render_report(report)
    assert any("DEADLINE_STOP" in line for line in lines)
    assert not any(line.startswith("NO_PARETO_GAIN") for line in lines)  # a scan that never finished claims nothing


def test_a_stop_after_a_swap_keeps_a_valid_no_worse_partial(monkeypatch):
    monkeypatch.setattr(cr, "POLL_EVERY", 1)
    rows, scores = many_swaps()
    calls = []

    def stop_at_the_fourth_look():
        calls.append(1)
        return len(calls) > 3

    partial = redeploy(rows, scores, stop=stop_at_the_fourth_look)
    report = partial.report
    assert report["state"] == "DEADLINE_STOP" and report["accepted_total"] == 1 and report["fixed_point"] is False
    assert no_proxy_worse(recount(rows), recount(partial.rosters))
    assert all(validate_lineup(SLATE, roster).valid for roster in partial.rosters.values())
    assert report["after"]["prior_sum"] > report["before"]["prior_sum"]


def test_a_stop_during_the_refusal_scan_leaves_the_fixed_point_and_names_the_partial_counts(monkeypatch):
    monkeypatch.setattr(cr, "POLL_EVERY", 1)
    rows, scores = many_swaps()
    ticks = []

    def counting():
        ticks.append(1)
        return False

    redeploy(rows, scores, stop=counting)
    last = len(ticks)
    cut = []

    def stop_on_the_last_look():
        cut.append(1)
        return len(cut) >= last

    result = redeploy(rows, scores, stop=stop_on_the_last_look)
    report = result.report
    # The portfolio is at its fixed point: the state is what the swaps made it, and only the refusal counts are partial.
    assert report["state"] == "COMPLETED" and report["fixed_point"] is True
    assert report["refusal_scan"] == "PARTIAL" and report["rejected_total"] is not None
    assert report["accepted_total"] == 3 and no_proxy_worse(recount(rows), recount(result.rosters))
    assert any("refusal scan PARTIAL" in line for line in cr.render_report(report))
    full = redeploy(rows, scores)
    assert report["rejected_total"] < full.report["rejected_total"] and result.rosters == full.rosters


def test_the_pass_bound_is_reported_and_a_rerun_continues():
    rows, scores = many_swaps()
    one = redeploy(rows, scores, max_passes=1)
    assert one.report["state"] == "PASS_BOUND_REACHED" and one.report["fixed_point"] is False and one.report["passes"] == 1
    rerun = redeploy(one.rosters, scores, max_passes=1)
    assert rerun.report["accepted_total"] + one.report["accepted_total"] <= 3
    assert redeploy(rows, scores).report["state"] == "COMPLETED"


def test_the_incomplete_report_keeps_the_identity_and_the_does_not_establish_text():
    block = cr.incomplete_report("NOT_RUN_WINDOW_SPENT", "NO_TIME")
    assert block["rule"] == "pareto_redeploy_v2" and block["state"] == "NOT_RUN_WINDOW_SPENT"
    assert "THAT_A_PRIOR_GAIN_IS_EXPECTED_VALUE_OR_A_WIN_PROBABILITY" in block["does_not_establish"]
    with pytest.raises(ValueError):
        cr.incomplete_report("COMPLETED", "x")
    assert cr.render_report(block)[0].startswith("PARETO_REDEPLOY state=NOT_RUN_WINDOW_SPENT")


# -------------------------------------------------------------------------- Week 4, the committed inputs


@pytest.fixture(scope="module")
def week4():
    slate = parse_salaries(WEEK4 / "DKSalaries.csv")
    construction = WEEK4 / "construction"
    dump = json.loads((construction / "scores_qbclean.json").read_text(encoding="utf-8"))
    scores = {k: float(v) for k, v in dump["by_dk_id"].items()}
    gated = {str(i) for i in dump.get("excluded_dk_ids") or ()}
    by_name = {p.name: p.dk_id for p in slate.players}
    protect = {by_name[n] for n in ("Braelon Allen", "Zach Ertz", "Jauan Jennings", "Emanuel Wilson")}
    return SimpleNamespace(slate=slate, scores=scores, gated=gated, protect=protect, construction=construction,
                           person={p.dk_id: p.underlying_id for p in slate.players})


def week4_rows(week4, name="portfolio_final_v4.json"):
    doc = json.loads((week4.construction / name).read_text(encoding="utf-8"))
    return {entry: tuple(roster) for entry, roster in doc["assignments_by_entry_id"].items()}


def week4_run(week4, rows, **kwargs):
    kwargs.setdefault("protect", week4.protect)
    kwargs.setdefault("exposure_limit", 13)
    kwargs.setdefault("overlap_cap", 5)
    kwargs.setdefault("slot_ordered", False)
    return cr.redeploy(week4.slate, week4.scores, rows, gated=week4.gated, **kwargs)


def test_week4_the_lifted_rule_reproduces_session_62s_numbers_exactly(week4):
    rows = week4_rows(week4)
    result = week4_run(week4, rows)
    report = result.report
    assert report["state"] == "COMPLETED" and report["fixed_point"] is True and report["locked_people"] == 0
    assert (report["accepted_total"], report["passes"]) == (49, 3)
    before, after = report["before"], report["after"]
    assert (before["prior_sum"], after["prior_sum"]) == (4148.518, 4231.611)
    assert (before["max_exposure"], after["max_exposure"]) == (13, 13)
    assert (before["top3_union"], after["top3_union"]) == (29, 27)
    assert (before["distinct_people"], after["distinct_people"]) == (115, 119)
    assert (round(before["mean_overlap"], 4), round(after["mean_overlap"], 4)) == (1.1323, 1.0580)
    assert report["rejected_total"] == 215 and report["rejected_by_goal"] == {
        "max_exposure": 0, "top3_union": 19, "mean_overlap": 215, "distinct_people": 95}
    assert report["row_rejections"] == {"ILLEGAL": 164, "SHAPE": 0, "CAPS_OR_DISTINCT": 23}


def test_week4_every_proxy_is_no_worse_by_an_independent_recount_and_the_rows_are_sound(week4):
    rows = week4_rows(week4)
    result = week4_run(week4, rows, slot_ordered=True)
    person_rows = lambda rs: {e: [week4.person[i] for i in r] for e, r in rs.items()}  # noqa: E731
    persons_before, persons_after = person_rows(rows), person_rows(result.rosters)
    assert no_proxy_worse(recount_ids(persons_before), recount_ids(persons_after))
    assert result.report["accepted_total"] >= 1  # the non-vacuous case: operator rows left slack
    assert len({roster_canonical_key(week4.slate, r) for r in result.rosters.values()}) == len(rows)  # R29
    by_id = {p.dk_id: p for p in week4.slate.players}
    for entry, roster in result.rosters.items():
        if entry in result.changed:
            assert validate_lineup(week4.slate, roster).valid and roster == cr.slot_order(by_id, roster)
        else:
            assert roster == rows[entry]
    for dk_id in week4.protect:  # nobody a judgment placed moves
        assert [e for e, r in rows.items() if dk_id in r] == [e for e, r in result.rosters.items() if dk_id in r]
    for accepted in result.report["accepted"]:
        assert accepted["prior_gain"] > 0 and accepted["in"] not in week4.protect | week4.gated
    again = week4_run(week4, {e: r for e, r in result.rosters.items()})
    assert again.report["accepted_total"] == 0 and again.report["fixed_point"] is True  # a fixed point


def test_week4_a_lock_clock_between_the_windows_never_touches_a_locked_cell(week4):
    rows = week4_rows(week4)
    between = datetime(2026, 10, 4, 14, 30, tzinfo=ET)  # after the 1:00 games, before the 4:05 and 4:25 kickoffs
    locked = cr.locked_dk_ids(week4.slate, between)
    assert 0 < len(locked) < len(week4.slate.players)
    unfiltered = week4_run(week4, rows)
    result = week4_run(week4, rows, locked=locked)
    assert result.report["locked_people"] > 0 and result.report["accepted_total"] >= 1
    for accepted in result.report["accepted"]:
        assert accepted["out"] not in locked and accepted["in"] not in locked
    for entry, roster in result.rosters.items():
        assert {i for i in roster if i in locked} == {i for i in rows[entry] if i in locked}
    before_everything = datetime(2026, 10, 4, 12, 0, tzinfo=ET)
    nothing_locked = week4_run(week4, rows, locked=cr.locked_dk_ids(week4.slate, before_everything))
    assert nothing_locked.report["locked_people"] == 0 and nothing_locked.rosters == unfiltered.rosters


def test_week4_the_pass_bound_stops_a_run_and_says_what_is_left(week4):
    rows = week4_rows(week4)
    one = week4_run(week4, rows, max_passes=1)
    assert one.report["state"] == "PASS_BOUND_REACHED" and one.report["fixed_point"] is False
    assert one.report["available_at_stop"] > 0
    assert any("PASS_BOUND_REACHED" in line for line in cr.render_report(one.report))
    finished = week4_run(week4, one.rosters)
    assert finished.report["state"] == "COMPLETED" and finished.report["accepted_total"] > 0


def random_legal_roster(week4, rng, pools):
    by_id = {p.dk_id: p for p in week4.slate.players}
    for _attempt in range(2000):
        qb = rng.choice(pools["QB"])
        rbs, wrs, te = rng.sample(pools["RB"], 2), rng.sample(pools["WR"], 3), rng.choice(pools["TE"])
        flex = rng.choice([i for pos in ("RB", "WR", "TE") for i in pools[pos] if i not in [*rbs, *wrs, te]])
        dst = rng.choice(pools["DST"])
        cells = [qb, *rbs, *wrs, te, flex, dst]
        if len({week4.person[i] for i in cells}) != 9 or sum(by_id[i].salary for i in cells) > 50_000:
            continue
        ordered = cr.slot_order(by_id, cells)
        if ordered is not None and validate_lineup(week4.slate, ordered).valid:
            return ordered
    raise AssertionError("no legal roster")


@pytest.mark.parametrize("seed", range(24))
def test_week4_random_portfolios_keep_every_invariant_on_the_delivered_cells(week4, seed):
    """Random legal slot-ordered portfolios on the committed pool, random protected people, a random lock clock, random
    limits. Every invariant is recounted from the DELIVERED cells: no proxy worse (the top-3 tie breaks by first appearance, so
    the cell order matters: seed 0 was a top-3 union of 9 to 11 that the rule called 9 to 9 before it counted the delivered
    order), every row legal and distinct, the protected and locked people exactly where they were, every person and pair
    within its limit."""

    import random

    pools = {pos: [p.dk_id for p in week4.slate.players if p.position == pos and week4.scores.get(p.dk_id, 0) > 0
                   and not p.status_raw.strip() and p.dk_id not in week4.gated] for pos in ("QB", "RB", "WR", "TE", "DST")}
    rng = random.Random(seed)
    count = rng.choice([10, 25, 40])
    rows, keys = {}, set()
    while len(rows) < count:
        roster = random_legal_roster(week4, rng, pools)
        key = roster_canonical_key(week4.slate, roster)
        if key not in keys:
            keys.add(key)
            rows[str(len(rows) + 1)] = roster
    protect = set(rng.sample(sorted({i for r in rows.values() for i in r}), 4))
    kickoffs = sorted({p.lock_at for p in week4.slate.players})
    moment = rng.choice([None, *kickoffs])
    locked = cr.locked_dk_ids(week4.slate, moment) if moment is not None else frozenset()
    limit, cap = rng.choice([count, max(2, count // 2), max(3, int(count * 0.4))]), rng.choice([None, 5, 6, 9])
    result = cr.redeploy(week4.slate, week4.scores, rows, protect=protect, gated=week4.gated, exposure_limit=limit,
                         overlap_cap=cap, locked=locked, slot_ordered=True, stored_limit=100)
    after = result.rosters
    persons = lambda rs: {e: [week4.person[i] for i in r] for e, r in rs.items()}  # noqa: E731
    assert no_proxy_worse(recount_ids(persons(rows)), recount_ids(persons(after)))
    assert len({roster_canonical_key(week4.slate, r) for r in after.values()}) == count
    exposure_before = collections.Counter(p for r in persons(rows).values() for p in r)
    for entry, roster in after.items():
        assert validate_lineup(week4.slate, roster).valid
        assert set(roster) & protect == set(rows[entry]) & protect
        for person in set(rows[entry]) & locked:
            assert roster.index(person) == rows[entry].index(person)  # the cell, not only the person
    exposure_after = collections.Counter(p for r in persons(after).values() for p in r)
    assert all(n <= max(limit, exposure_before[p]) for p, n in exposure_after.items())
    if cap is not None:
        later_rows, earlier_rows = list(persons(after).values()), list(persons(rows).values())
        for later in range(len(later_rows)):
            for earlier in range(later):
                shared = len(set(later_rows[earlier]) & set(later_rows[later]))
                assert shared <= max(cap, len(set(earlier_rows[earlier]) & set(earlier_rows[later])))


def test_week4_a_bounded_report_is_a_small_artifact_with_exact_totals(week4):
    rows = week4_rows(week4)
    full = week4_run(week4, rows).report
    bounded = week4_run(week4, rows, stored_limit=cr.STORED_LIMIT).report
    assert bounded["accepted_total"] == full["accepted_total"] and bounded["rejected_total"] == full["rejected_total"]
    assert len(bounded["rejected"]) == cr.STORED_LIMIT < len(full["rejected"])
    assert len(json.dumps(bounded)) < len(json.dumps(full))


# ----------------------------------------------------- the stage inside the thesis build (engine rows)


def contract_for(slate):
    return SimpleNamespace(selectable_people=tuple(sorted({row.underlying_id for row in slate.players})))


def thesis(count=12, *, slate=SLATE, objective=None, **kwargs):
    kwargs.setdefault("classic_person_overlap", CLASSIC_PERSON_OVERLAP)
    kwargs.setdefault("time_limit_seconds", 20.0)
    return select_thesis_lineups(
        slate, objective or _objective(slate), kwargs.pop("excluded", ()), contract_for(slate), count=count, **kwargs)


def test_the_stage_is_off_by_default_so_the_construction_stands_alone():
    run = thesis(8)
    assert "pareto_redeploy" not in run.construction
    assert {lineup.solver_status for lineup in run.selected} == {"OPTIMAL"}


def test_the_stage_reports_in_the_construction_block_and_leaves_every_row_valid_distinct_and_no_worse():
    plain = thesis(12)
    run = thesis(12, pareto_redeploy=True, now=BEFORE_THE_FIXTURE_LOCKS)
    block = run.construction["pareto_redeploy"]
    assert block["rule"] == "pareto_redeploy_v2" and block["state"] == "COMPLETED" and block["locked_people"] == 0
    assert block["stored_limit"] == cr.STORED_LIMIT and block["refusal_scan"] == "COMPLETE"
    rosters = [lineup.roster for lineup in run.selected]
    assert len({lineup.canonical_key for lineup in run.selected}) == len(run.selected) == 12  # R29
    assert all(validate_lineup(SLATE, roster).valid for roster in rosters)
    changed = set(block["changed_entry_ids"])
    assert changed and block["accepted_total"] >= 1, "this fixture has natural Pareto swaps: the stage is exercised, not vacuous"
    for before, after in zip(plain.selected, run.selected):
        if str(after.index) in changed:
            assert after.solver_status == "PARETO_REDEPLOY_OF_OPTIMAL" and after.roster != before.roster
            assert after.prior_points > before.prior_points
        else:
            assert (after.roster, after.canonical_key, after.prior_points, after.solver_status) == (
                before.roster, before.canonical_key, before.prior_points, before.solver_status)
    assert no_proxy_worse(recount({str(i): r for i, r in enumerate((p.roster for p in plain.selected), 1)}),
                          recount({str(i): r for i, r in enumerate(rosters, 1)}))
    assert block["after"]["rows"] == 12 and run.construction["effective"]["lineups"] == 12
    assert {line.index for line in run.selected} == {line.index for line in plain.selected}


def test_the_stage_with_an_unpinned_clock_is_off_the_lock_filter_and_with_a_late_one_locks_cells():
    open_run = thesis(8, pareto_redeploy=True, now=None)
    assert open_run.construction["pareto_redeploy"]["locked_people"] == 0
    # The fixture is dated 2026-09-13: under the wall clock every cell is locked, which is why no test leaves it to it.
    wall = thesis(8, pareto_redeploy=True, now=datetime.now(timezone.utc))
    block = wall.construction["pareto_redeploy"]
    assert block["locked_people"] == len({row.underlying_id for row in SLATE.players}) and block["accepted_total"] == 0
    assert [line.roster for line in wall.selected] == [line.roster for line in thesis(8).selected]


def test_a_window_of_nothing_is_named_and_the_rows_are_as_built():
    run = thesis(8, pareto_redeploy=True, redeploy_seconds=0)
    block = run.construction["pareto_redeploy"]
    assert block["state"] == "NOT_RUN_WINDOW_SPENT" and "before" not in block
    assert [l.roster for l in run.selected] == [l.roster for l in thesis(8).selected]


def test_a_stage_that_raises_is_named_failed_and_the_rows_stay_as_built(monkeypatch):
    def boom(*_args, **_kwargs):
        raise RuntimeError("the rule broke")

    monkeypatch.setattr(cr, "redeploy", boom)
    run = thesis(8, pareto_redeploy=True)
    block = run.construction["pareto_redeploy"]
    assert block["state"] == "FAILED" and block["reason"] == "RuntimeError: the rule broke"
    assert [l.roster for l in run.selected] == [l.roster for l in thesis(8).selected]
    assert all(l.solver_status == "OPTIMAL" for l in run.selected)


def test_a_trial_the_one_backstop_rejects_is_never_adopted(monkeypatch):
    real = cr.redeploy

    def duplicates_a_row(slate, scores, rosters, **kwargs):
        result = real(slate, scores, rosters, **kwargs)
        broken = dict(rosters)
        broken["2"] = rosters["1"]  # R29 broken on purpose: row 2 becomes row 1, row 1 stays as built
        return cr.RedeployResult(broken, result.log, {**result.report, "changed_entry_ids": ["2"]})

    monkeypatch.setattr(cr, "redeploy", duplicates_a_row)
    run = thesis(8, pareto_redeploy=True)
    block = run.construction["pareto_redeploy"]
    assert block["state"] == "FAILED" and "DUPLICATE_LINEUP_SELECTED" in block["reason"]
    assert [l.roster for l in run.selected] == [l.roster for l in thesis(8).selected]


def test_a_real_swap_through_the_stage_replaces_the_row_and_names_its_solve(monkeypatch):
    """Make the prior suddenly like a person no built row holds (a boost passed only to the rule, as a placement or an
    operator's slack would leave a row), and follow the real swap through the stage: the row is replaced, its status
    names the solve it came from, its salary, key and prior are recounted, and the one backstop passes on the final rows."""

    real = cr.redeploy
    plain = thesis(8)
    held = {i for lineup in plain.selected for i in lineup.roster}
    target = next(i for i, p in sorted(BY_ID.items()) if i not in held and p.position in ("RB", "WR", "TE") and not p.status_raw)

    def boosted(slate, scores, rosters, **kwargs):
        return real(slate, {**scores, target: scores[target] + 100.0}, rosters, **kwargs)

    monkeypatch.setattr(cr, "redeploy", boosted)
    run = thesis(8, pareto_redeploy=True, now=BEFORE_THE_FIXTURE_LOCKS)
    block = run.construction["pareto_redeploy"]
    assert block["state"] == "COMPLETED" and block["accepted_total"] >= 1 and block["locked_people"] == 0
    changed = [lineup for lineup in run.selected if str(lineup.index) in block["changed_entry_ids"]]
    assert changed and any(target in lineup.roster for lineup in changed)  # natural swaps are there too
    objective = _objective(SLATE)
    for lineup in changed:
        validation = validate_lineup(SLATE, lineup.roster)
        assert lineup.solver_status == "PARETO_REDEPLOY_OF_OPTIMAL" and validation.valid
        assert (lineup.salary, lineup.canonical_key) == (validation.lineup.salary, validation.lineup.canonical_key)
        assert lineup.prior_points == pytest.approx(sum(objective[i] for i in lineup.roster))
        assert lineup.roster == cr.slot_order(BY_ID, lineup.roster)
    unchanged = [(a, b) for a, b in zip(plain.selected, run.selected) if str(b.index) not in block["changed_entry_ids"]]
    assert all(a.roster == b.roster and a.solver_status == b.solver_status for a, b in unchanged)
    assert len({lineup.canonical_key for lineup in run.selected}) == 8
    assert run.construction["effective"]["lineups"] == 8


def test_the_pair_cap_the_stage_hands_over_is_the_later_rows():
    binds = lambda cap: cap is not None and cap < 9  # noqa: E731
    caps = [3, 4, None, 6, 9]
    assert classic_theses._later_row_cap(caps, "1", "2", binds) == 4 == classic_theses._later_row_cap(caps, "2", "1", binds)
    assert classic_theses._later_row_cap(caps, "1", "4", binds) == 6  # min would say 3
    assert classic_theses._later_row_cap(caps, "3", "1", binds) is None  # the later row was uncapped
    assert classic_theses._later_row_cap(caps, "2", "5", binds) is None  # a cap that does not bind is no cap


def test_a_trial_that_holds_an_excluded_person_is_never_adopted(monkeypatch):
    real = cr.redeploy
    excluded = tuple(sorted(i for i, p in BY_ID.items() if p.position == "WR" and int(p.name.split()[-1]) >= 5))

    def smuggles_one_in(slate, scores, rosters, **kwargs):
        result = real(slate, scores, rosters, **kwargs)
        broken = dict(rosters)
        cells = list(rosters["1"])
        for cell in cells:
            if BY_ID[cell].position != "WR":
                continue
            for banned in excluded:
                trial = tuple(banned if i == cell else i for i in cells)
                ordered = cr.slot_order(BY_ID, trial)
                if banned not in cells and ordered is not None and validate_lineup(slate, ordered).valid:
                    broken["1"] = ordered
                    return cr.RedeployResult(broken, result.log, {**result.report, "changed_entry_ids": ["1"]})
        raise AssertionError("no cell to smuggle into")

    monkeypatch.setattr(cr, "redeploy", smuggles_one_in)
    run = thesis(8, excluded=excluded, pareto_redeploy=True)
    block = run.construction["pareto_redeploy"]
    assert block["state"] == "FAILED" and "SOLVER_SELECTED_AN_EXCLUDED_ROW" in block["reason"]
    assert [l.roster for l in run.selected] == [l.roster for l in thesis(8, excluded=excluded).selected]


def test_a_trial_whose_delivered_proxies_are_worse_is_never_adopted(monkeypatch):
    """The rule decides each swap on its own count; the stage counts the delivered rows again before adopting them. Make the
    stage's own look (the first comparison after the rule returns) see a worse proxy: the rows stay as built."""

    real, real_hurt, armed = cr.redeploy, cr.proxies_hurt, []

    def rule_then_arm(*args, **kwargs):
        result = real(*args, **kwargs)
        armed.append(1)
        return result

    monkeypatch.setattr(cr, "redeploy", rule_then_arm)
    monkeypatch.setattr(cr, "proxies_hurt", lambda before, after: ["top3_union"] if armed else real_hurt(before, after))
    run = thesis(8, pareto_redeploy=True)
    block = run.construction["pareto_redeploy"]
    assert block["state"] == "FAILED" and "THESIS_CONSTRUCTION_BREACHED:washout_proxy:top3_union" in block["reason"]
    assert [l.roster for l in run.selected] == [l.roster for l in thesis(8).selected]


def test_a_trial_the_checks_reject_marks_the_deadline_record_as_well_as_the_block(monkeypatch):
    real = cr.redeploy

    def duplicates_a_row(slate, scores, rosters, **kwargs):
        result = real(slate, scores, rosters, **kwargs)
        broken = dict(rosters)
        broken["2"] = rosters["1"]
        return cr.RedeployResult(broken, result.log, {**result.report, "changed_entry_ids": ["2"]})

    monkeypatch.setattr(cr, "redeploy", duplicates_a_row)
    budget, _clock = fake_clock_budget(SLATE, as_of=BEFORE_THE_FIXTURE_LOCKS - timedelta(hours=2))
    with activated(budget):
        run = thesis(8, pareto_redeploy=True, now=budget.now())
    assert run.construction["pareto_redeploy"]["state"] == "FAILED"
    (record,) = [stage for stage in budget.stages if stage.name == "pareto_redeploy"]
    assert record.outcome == "RAISED"  # the record and the block say the same thing


def test_the_stage_honours_protected_people_exactly_as_the_build_placed_them():
    slate, objective = SLATE, _objective(SLATE)
    placed = "NYJ|WR|3"  # a person a construction judgment would name
    run = thesis(12, protected={placed: 3}, pareto_redeploy=True, now=BEFORE_THE_FIXTURE_LOCKS)
    placements = run.construction["placements"]
    held = [l.index for l in run.selected if any(PERSON[i] == placed for i in l.roster)]
    assert held == placements["delivered_rows"][placed] and len(held) >= 3
    protected = run.construction["pareto_redeploy"]["protected"]
    assert protected and all(p["rows_before"] == p["rows_after"] for p in protected)
    assert run.construction["pareto_redeploy"]["state"] == "COMPLETED"


def test_the_stage_hands_the_rule_exactly_what_the_build_knows(monkeypatch):
    """Every limit and every set the stage passes is the build's own: its exclusions, the prefilled rosters, the placed people,
    each person's limit (a placed person's own minimum may exceed the shared cap), each pair's cap and the lock clock."""

    seen = {}
    real = cr.redeploy

    def spy(slate, scores, rosters, **kwargs):
        seen.update(kwargs)
        return real(slate, scores, rosters, **kwargs)

    monkeypatch.setattr(cr, "redeploy", spy)
    placed = "NYJ|WR|3"
    prefilled = thesis(12).selected[0].roster  # a roster the entry template already holds; the build cuts it
    excluded = tuple(sorted(ids("SEA WR 6", "BUF TE 3")))
    run = thesis(12, protected={placed: 7}, forbidden_rosters=[prefilled], excluded=excluded, pareto_redeploy=True,
                 now=BETWEEN_THE_FIXTURE_WINDOWS)
    assert seen["gated"] == set(excluded)
    assert seen["forbidden_keys"] == {roster_canonical_key(SLATE, prefilled)}
    assert seen["protect"] == {i for i, p in BY_ID.items() if p.underlying_id == placed}
    assert seen["exposure_limit"](placed) == 7 > seen["exposure_limit"]("NE|QB|1") == classic_theses.person_cap(12, 0.4)
    assert seen["overlap_cap"]("1", "2") in (None, *range(10)) and seen["overlap_cap"]("2", "1") == seen["overlap_cap"]("1", "2")
    assert seen["locked"] == cr.locked_dk_ids(SLATE, BETWEEN_THE_FIXTURE_WINDOWS) and seen["slot_ordered"] is True
    assert seen["stored_limit"] == cr.STORED_LIMIT
    assert run.construction["pareto_redeploy"]["locked_people"] == len(
        {PERSON[i] for i in cr.locked_dk_ids(SLATE, BETWEEN_THE_FIXTURE_WINDOWS)})
    assert all(roster_canonical_key(SLATE, lineup.roster) != roster_canonical_key(SLATE, prefilled) for lineup in run.selected)


def test_a_build_that_spent_its_own_window_leaves_the_redeploy_no_time():
    """A clock that stands still while the build runs and then jumps: whatever the allowance says, a window already spent
    by the build is not a window to redeploy in."""

    calls = []

    def counting():
        calls.append(1)
        return 0.0

    thesis(6, clock=counting)
    build_calls = len(calls)
    seen = []

    def jumps_after_the_build():
        seen.append(1)
        return 0.0 if len(seen) <= build_calls else 1e9

    run = thesis(6, pareto_redeploy=True, clock=jumps_after_the_build)
    block = run.construction["pareto_redeploy"]
    assert block["state"] == "NOT_RUN_WINDOW_SPENT" and run.stopped is None
    assert [l.roster for l in run.selected] == [l.roster for l in thesis(6).selected]


class StillClock:
    """A monotonic clock that moves only when a test says so."""

    now = 1000.0

    def __call__(self):
        return self.now


def fake_clock_budget(slate, *, as_of):
    clock = StillClock()
    return Budget.build(slate.games, as_of=as_of, clock=clock, wall=lambda: as_of), clock


def test_inside_run_slate_the_stage_asks_the_deadline_controller_and_is_recorded():
    budget, _clock = fake_clock_budget(SLATE, as_of=BEFORE_THE_FIXTURE_LOCKS - timedelta(hours=2))
    with activated(budget):
        run = thesis(8, pareto_redeploy=True, now=budget.now())
    assert run.construction["pareto_redeploy"]["state"] == "COMPLETED"
    (record,) = [stage for stage in budget.stages if stage.name == "pareto_redeploy"]
    assert record.outcome == "COMPLETED" and record.allowance_seconds == cr.STAGE_SECONDS
    assert record.default_seconds == cr.STAGE_SECONDS and record.elapsed_seconds is not None


def test_inside_run_slate_a_spent_window_skips_the_stage_and_names_it_once():
    # The delivery deadline (lock minus five minutes) is already past: no improvement window is left.
    budget, _clock = fake_clock_budget(SLATE, as_of=BEFORE_THE_FIXTURE_LOCKS + timedelta(hours=5, minutes=57))
    with activated(budget):
        run = thesis(8, pareto_redeploy=True, now=None)
    block = run.construction["pareto_redeploy"]
    assert block["state"] == "NOT_RUN_WINDOW_SPENT"
    (record,) = [stage for stage in budget.stages if stage.name == "pareto_redeploy"]
    assert record.outcome == "SKIPPED"
    assert not [code for code, _detail in budget.events if code == "DEADLINE_STAGE_SHORTENED" and "pareto_redeploy" in _detail]
    assert [l.roster for l in run.selected] == [l.roster for l in thesis(8).selected]


def test_week4_engine_rows_with_the_four_placed_people_are_reported_no_worse_and_untouched(week4):
    """The acceptance on the committed Week 4 pool: the engine's own rung-4 build (the committed score dump as the prior),
    the four people Session 61's judgment placed, the lock clock pinned before the first kickoff. On these rows the rule
    takes nothing (the solver already spends the cap and the rows it leaves are prior-optimal under the caps), so this
    is the guarantee and the report; the operator portfolios above are where the rule takes swaps."""

    slate = week4.slate
    persons = {dk: week4.person[dk] for dk in week4.protect}
    excluded = tuple(sorted(week4.gated))
    objective = {p.dk_id: float(week4.scores.get(p.dk_id, 0.0)) for p in slate.players}
    before_everything = datetime(2026, 10, 4, 12, 0, tzinfo=ET)
    run = select_thesis_lineups(
        slate, objective, excluded, contract_for(slate), count=20, classic_person_overlap=CLASSIC_PERSON_OVERLAP,
        time_limit_seconds=10.0, protected={person: 3 for person in persons.values()}, pareto_redeploy=True,
        now=before_everything)
    block = run.construction["pareto_redeploy"]
    assert block["state"] == "COMPLETED" and block["locked_people"] == 0 and block["rule"] == "pareto_redeploy_v2"
    assert no_proxy_worse(
        {k: block["before"][k] for k in ("max_exposure", "top3_union", "pair_overlap_sum", "distinct_people")},
        {k: block["after"][k] for k in ("max_exposure", "top3_union", "pair_overlap_sum", "distinct_people")})
    placements = run.construction["placements"]
    assert all(placements["met"].values())
    for dk_id, person in persons.items():  # the placed people sit where the build put them
        held = [lineup.index for lineup in run.selected if dk_id in lineup.roster]
        assert held == placements["delivered_rows"][person] and len(held) >= 3
    assert {p["dk_id"] for p in block["protected"]} == set(persons)
    assert all(p["rows_before"] == p["rows_after"] for p in block["protected"])
    assert len({lineup.canonical_key for lineup in run.selected}) == len(run.selected) == 20  # R29
    assert all(validate_lineup(slate, lineup.roster).valid for lineup in run.selected)


def test_a_run_slate_rung_four_run_reports_the_redeploy_and_stays_prior_only_do_not_upload(tmp_path, monkeypatch):
    from .test_relaxation_controller import _classic

    wide = {"QB": 2, "RB": 3, "WR": 4, "TE": 2, "DST": 1}
    code, report, _root = _classic(tmp_path, monkeypatch, run_id="redeploy-run", entries=10, policy=None, depth=wide)
    assert code == 0, report["blockers"]
    block = report["prior_review_reports"]["selection"]["selection"]["construction"]["pareto_redeploy"]
    assert block["rule"] == "pareto_redeploy_v2" and block["state"] == "COMPLETED" and block["locked_people"] == 0
    assert block["after"]["rows"] == 10
    (record,) = [stage for stage in report["deadline"]["stages"] if stage["name"] == "pareto_redeploy"]
    assert record["outcome"] == "COMPLETED"
    assert report["RELEASE_DECISION"] == "DO_NOT_UPLOAD" and report["MODEL_STATUS"] == "PRIOR_ONLY"
    assert not [c for c in (item["code"] for item in report["release_truths"]["delivery_limitations"])
                if c == "CLASSIC_PARETO_REDEPLOY_INCOMPLETE"]


def test_the_coverage_artifact_carries_the_block_and_a_pinned_run_replays_it_byte_for_byte(tmp_path, monkeypatch):
    from .test_classic_judgment import _classic_run

    first = _classic_run(tmp_path / "a", monkeypatch, classic_construction="THESES")
    second = _classic_run(tmp_path / "b", monkeypatch, classic_construction="THESES")
    outcome, coverage, _slate = first
    block = coverage["pareto_redeploy"]
    assert block["rule"] == "pareto_redeploy_v2" and block["state"] == "COMPLETED" and block["locked_people"] == 0
    assert outcome.reports["selection"]["selection"]["construction"]["pareto_redeploy"] == block
    assert json.dumps(block, sort_keys=True) == json.dumps(second[1]["pareto_redeploy"], sort_keys=True)
    assert coverage["MODEL_STATUS"] == "PRIOR_ONLY" and coverage["RELEASE_DECISION"] == "DO_NOT_UPLOAD"


def test_the_engines_operating_path_turns_the_stage_on_with_the_runs_clock(tmp_path, monkeypatch):
    """`select_prior_lineups` is the engine's operating path: it must ask the thesis build for the redeploy and hand it the
    clock the run reads (the pinned `as_of` when no deadline budget is active)."""

    from .test_classic_judgment import _classic_run
    from .test_classic_prior_review import AS_OF as PINNED

    seen = {}
    real = selection.select_thesis_lineups

    def spy(*args, **kwargs):
        seen.update(kwargs)
        return real(*args, **kwargs)

    monkeypatch.setattr(selection, "select_thesis_lineups", spy)
    _classic_run(tmp_path, monkeypatch, classic_construction="THESES")
    assert seen["pareto_redeploy"] is True and seen["now"] == PINNED


def test_the_handoff_script_prints_the_redeploy_block_beside_the_judgment_pass(tmp_path, monkeypatch, capsys):
    import importlib.util

    from .test_classic_judgment import _classic_run

    spec = importlib.util.spec_from_file_location("judgment_pass_report", REPO_ROOT / "scripts" / "judgment_pass_report.py")
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    outcome, coverage, _slate = _classic_run(tmp_path, monkeypatch, classic_construction="THESES")
    path = Path(outcome.artifacts["complete_slate_coverage"])
    assert script.main([str(path)]) == 0
    text = capsys.readouterr().out
    assert "## Salary redeploy (a Pareto swap only; not a selection)" in text and "PARETO_REDEPLOY state=COMPLETED" in text
    assert text.index("## Injury rooms") < text.index("## Salary redeploy")
    assert script.main([str(path), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["pareto_redeploy"] == coverage["pareto_redeploy"]


# -------------------------------------------------------- what reads the block: the list, the limitation


def lineups_with(*statuses):
    return [SelectedLineup(index=i, roster=(), captain_dk_id="", salary=0, prior_points=0.0, canonical_key=str(i),
                           solver_status=status, solver_seconds=0.0) for i, status in enumerate(statuses, start=1)]


def test_a_redeployed_row_of_an_optimal_solve_adds_no_time_limit_text_and_a_limited_one_stays_listed():
    assert selection._non_optimal_indexes(lineups_with("OPTIMAL", "PARETO_REDEPLOY_OF_OPTIMAL")) == []
    kept = selection._non_optimal_indexes(lineups_with(
        "OPTIMAL", "PARETO_REDEPLOY_OF_OPTIMAL", "PARETO_REDEPLOY_OF_FEASIBLE", "FEASIBLE"))
    assert kept == [3, 4]


@pytest.mark.parametrize("state", ["DEADLINE_STOP", "NOT_RUN_WINDOW_SPENT", "FAILED"])
def test_an_incomplete_redeploy_travels_with_the_file_by_name(state):
    reports = {"selection": {"selection": {"construction": {"pareto_redeploy": {"state": state, "reason": "WHY"}}}}}
    (limitation,) = [x for x in cli._classic_judgment_limitations(reports) if x.startswith("CLASSIC_PARETO_REDEPLOY_INCOMPLETE")]
    assert state in limitation and "WHY" in limitation and "the file is not affected" in limitation
    family = load_gate_registry().limitation("CLASSIC_PARETO_REDEPLOY_INCOMPLETE", detail=limitation)
    assert family.gate_class.value == "P"


@pytest.mark.parametrize("state", ["COMPLETED", "PASS_BOUND_REACHED", "NOT_APPLICABLE"])
def test_a_redeploy_that_ran_to_its_end_or_had_nothing_to_do_adds_no_limitation(state):
    reports = {"selection": {"selection": {"construction": {"pareto_redeploy": {"state": state}}}}}
    assert not [x for x in cli._classic_judgment_limitations(reports) if "PARETO_REDEPLOY" in x]
    assert not [x for x in cli._classic_judgment_limitations({}) if "PARETO_REDEPLOY" in x]


def test_the_module_imports_only_the_contract_and_the_legality_and_never_a_field_or_economics_module():
    source = (REPO_ROOT / "src" / "nfl_dfs" / "classic_redeploy.py").read_text(encoding="utf-8")
    imported = {node.module for node in ast.walk(ast.parse(source)) if isinstance(node, ast.ImportFrom) and node.level == 1}
    assert imported == {"contracts", "lineups"}
    assert "AvgPointsPerGame" not in source
