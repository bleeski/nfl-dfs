"""Session 50: `within_contest_diversity_v1`, the pure assignment step.

The module changes only which entry holds which lineup. These tests pin that it
is a permutation, that a filled row never moves, that a one-entry contest is
left alone, that the same bytes in give the same order out, that a timeout keeps
the best order found, and that no contest scores worse than it did in the
solver's order.
"""
from __future__ import annotations

import random
from collections import Counter
from fractions import Fraction

import pytest

from nfl_dfs import contest_assignment as ca

PEOPLE = {
    f"d{i}": ca.Person(key=f"p{i}", team=team, position=position)
    for i, (team, position) in enumerate(
        [("AAA", "QB"), ("AAA", "RB"), ("AAA", "WR"), ("AAA", "WR"), ("AAA", "TE"), ("AAA", "DST"),
         ("BBB", "QB"), ("BBB", "RB"), ("BBB", "WR"), ("BBB", "WR"), ("BBB", "TE"), ("BBB", "DST"),
         ("CCC", "QB"), ("CCC", "RB"), ("CCC", "WR"), ("CCC", "TE")]
    )
}


def _facts(people: set[str], key: str | None = None, stack: str | None = None, thesis: str | None = None):
    return ca.LineupFacts(frozenset(people), key, stack, thesis)


def _random_instance(seed: int, contests: int = 5, per: int = 4, fixed: int = 2):
    rng = random.Random(seed)
    pool = [f"x{i}" for i in range(24)]
    slots, lineups = [], []
    for c in range(contests):
        for k in range(per):
            people = set(rng.sample(pool, 6))
            lineups.append(_facts(people, key=rng.choice(pool[:8]), thesis=rng.choice(["t1", "t2", None])))
            slots.append(ca.Slot(f"e{c}-{k}", f"c{c}", None if (c * per + k) < fixed else "p"))
    return slots, lineups


def _scores(slots, lineups, order):
    by_contest: dict[str, list[ca.LineupFacts]] = {}
    for slot, index in zip(slots, order):
        by_contest.setdefault(slot.contest_id, []).append(lineups[index])
    out = {}
    for contest, placed in by_contest.items():
        costs = [ca.pair_cost(a, b) for i, a in enumerate(placed) for b in placed[i + 1:]]
        out[contest] = ca.contest_score(costs)
    return out


# --- the objective ------------------------------------------------------------


def test_the_pair_cost_weights_are_the_registered_ones():
    a = _facts({"a", "b", "c"}, key="k", stack="T", thesis="x")
    b = _facts({"a", "b", "d"}, key="k", stack="T", thesis="x")
    assert ca.pair_cost(a, b) == 2 ** 2 + 12 + 6 + 3
    assert ca.pair_cost(a, _facts({"z"})) == 0
    assert ca.pair_cost(_facts({"a"}, thesis=None), _facts({"a"}, thesis=None)) == 1
    assert (ca.KEY_PERSON_WEIGHT, ca.STACK_TEAM_WEIGHT, ca.THESIS_WEIGHT) == (12, 6, 3)
    assert ca.CONTEST_ASSIGNMENT_VERSION == "within_contest_diversity_v1"


def test_a_contest_scores_its_worst_pair_plus_its_mean_pair_and_a_lone_entry_scores_zero():
    assert ca.contest_score([]) == 0
    assert ca.contest_score([9]) == 18
    assert ca.contest_score([4, 4, 16]) == 16 + Fraction(24, 3)


def test_a_two_entry_pair_is_not_crowded_out_by_a_seven_entry_contest():
    """The reason for worst-plus-mean: one bad pair in a small contest still counts fully."""

    small_bad = ca.contest_score([16])
    big_one_bad_pair = ca.contest_score([16] + [0] * 20)
    assert small_bad == 32
    assert big_one_bad_pair < small_bad
    raw_sum_small, raw_sum_big = 16, 16 + 20 * 9
    assert raw_sum_big > raw_sum_small  # the raw sum would have ranked the big contest worse


def test_the_report_states_what_it_does_not_establish():
    slots, lineups = _random_instance(1)
    report = ca.assign_contests(slots, lineups, restarts=2).as_report()
    assert report["contest_assignment_version"] == "within_contest_diversity_v1"
    for word in ("EXPECTED_POINTS_OR_VALUE", "WIN_OR_CASH_LIKELIHOOD", "PAYOUT_OR_CONTEST_WORTH"):
        assert word in report["does_not_establish"]


# --- lineup facts -------------------------------------------------------------


def test_showdown_facts_take_the_captain_from_slot_zero_and_the_person_from_the_key():
    people = {
        "cpt1": ca.Person("hurts"), "flex1": ca.Person("hurts"),
        "flex2": ca.Person("smith"), "flex3": ca.Person("swift"),
    }
    facts = ca.lineup_facts(("flex2", "cpt1", "flex3"), mode="SHOWDOWN", people=people)
    assert facts.key_person == "smith" and facts.stack_team is None
    # the CPT and FLEX ID of one person collapse to one person
    assert ca.lineup_facts(("cpt1", "flex1"), mode="SHOWDOWN", people=people).people == {"hurts"}


def test_classic_facts_take_the_qb_and_the_primary_stack_team():
    roster = ("d0", "d1", "d2", "d3", "d6", "d7", "d10", "d5", "d15")
    facts = ca.lineup_facts(roster, mode="CLASSIC", people=PEOPLE)
    assert facts.key_person == "p0"
    assert facts.stack_team == "AAA"  # four offensive AAA players against three BBB and one CCC


def test_primary_stack_team_ties_go_to_the_qbs_team_then_the_lower_abbreviation():
    assert ca.primary_stack_team(("d0", "d1", "d6", "d7"), PEOPLE) == "AAA"   # 2-2, QB's team
    assert ca.primary_stack_team(("d1", "d2", "d7", "d8"), PEOPLE) == "AAA"   # 2-2, no QB, lower name
    assert ca.primary_stack_team(("d0", "d7", "d13", "d5"), PEOPLE) is None    # no team has two
    assert ca.primary_stack_team(("d5", "d11"), PEOPLE) is None                # defenses never stack


def test_unknown_ids_and_modes_are_named_refusals():
    with pytest.raises(ca.ContestAssignmentError, match="UNKNOWN_DK_ID"):
        ca.lineup_facts(("nope",), mode="SHOWDOWN", people=PEOPLE)
    with pytest.raises(ca.ContestAssignmentError, match="UNKNOWN_MODE"):
        ca.lineup_facts(("d0",), mode="FANTASY", people=PEOPLE)


# --- the properties the card names ---------------------------------------------


@pytest.mark.parametrize("seed", range(6))
def test_the_result_is_a_permutation_that_keeps_every_pool_and_every_fixed_row(seed):
    slots, lineups = _random_instance(seed)
    result = ca.assign_contests(slots, lineups, restarts=20, time_limit_seconds=None)
    assert sorted(result.order) == list(range(len(slots)))
    for index, slot in enumerate(slots):
        if slot.pool is None:
            assert result.order[index] == index, "a filled row moved"
    movable = [i for i, s in enumerate(slots) if s.pool == "p"]
    assert Counter(result.order[i] for i in movable) == Counter(movable)


def test_a_fixed_row_counts_in_its_contests_score_but_never_moves():
    same = _facts({"a", "b", "c", "d", "e", "f"}, key="k")
    other = _facts({"a", "b", "c", "d", "e", "g"}, key="k")
    far = _facts({"u", "v", "w", "x", "y", "z"}, key="j")
    far2 = _facts({"m", "n", "o", "p", "q", "r"}, key="i")
    slots = [ca.Slot("fixed", "c1", None), ca.Slot("m1", "c1", "p"),
             ca.Slot("m2", "c2", "p"), ca.Slot("m3", "c2", "p")]
    lineups = [same, other, far, far2]
    result = ca.assign_contests(slots, lineups, restarts=10, time_limit_seconds=None)
    assert result.order[0] == 0
    # the movable row next to the fixed one is now a far-away lineup, not the near copy
    assert result.order[1] in (2, 3)
    assert result.after["c1"]["worst_pair_shared_people"] == 0


def test_a_one_entry_contest_is_left_alone():
    slots = [ca.Slot("s", "solo", "p"), ca.Slot("a", "c1", "p"), ca.Slot("b", "c1", "p"),
             ca.Slot("c", "c2", "p"), ca.Slot("d", "c2", "p")]
    lineups = [_facts({"1", "2", "3", "4", "5", "6"}), _facts({"a", "b", "c", "d", "e", "f"}),
               _facts({"a", "b", "c", "d", "e", "g"}), _facts({"a", "b", "c", "d", "e", "h"}),
               _facts({"u", "v", "w", "x", "y", "z"})]
    result = ca.assign_contests(slots, lineups, restarts=20, time_limit_seconds=None)
    assert result.order[0] == 0
    assert "solo" not in result.after and len(result.after) == 2


def test_nothing_to_permute_is_reported_not_applicable():
    slots = [ca.Slot("a", "c1", "p"), ca.Slot("b", "c1", "p")]
    lineups = [_facts({"a"}), _facts({"a"})]
    result = ca.assign_contests(slots, lineups)
    assert result.order == (0, 1) and result.status == ca.STATUS_NOT_APPLICABLE


def test_the_same_inputs_give_the_same_order_and_report_bytes():
    slots, lineups = _random_instance(3)
    first = ca.assign_contests(slots, lineups, restarts=15, time_limit_seconds=None)
    second = ca.assign_contests(slots, lineups, restarts=15, time_limit_seconds=None)
    assert first.order == second.order
    assert first.before == second.before and first.after == second.after
    assert {k: v for k, v in first.as_report().items() if k != "seconds"} == {
        k: v for k, v in second.as_report().items() if k != "seconds"}


@pytest.mark.parametrize("seed", range(8))
@pytest.mark.parametrize("no_regression", [True, False])
def test_the_cost_never_increases_in_total_and_by_default_in_no_contest(seed, no_regression):
    slots, lineups = _random_instance(seed, contests=6, per=3, fixed=1)
    start = _scores(slots, lineups, list(range(len(slots))))
    result = ca.assign_contests(
        slots, lineups, restarts=25, time_limit_seconds=None, no_regression=no_regression)
    end = _scores(slots, lineups, result.order)
    assert sum(end.values()) <= sum(start.values())
    if no_regression:
        assert all(end[c] <= start[c] for c in start), (start, end)


def test_the_reported_statistics_are_recomputed_from_the_final_placement():
    slots, lineups = _random_instance(2)
    result = ca.assign_contests(slots, lineups, restarts=10, time_limit_seconds=None)
    by_contest: dict[str, list[ca.LineupFacts]] = {}
    for slot, index in zip(slots, result.order):
        by_contest.setdefault(slot.contest_id, []).append(lineups[index])
    assert dict(result.after) == {c: ca.contest_statistics(p) for c, p in by_contest.items()}


def test_a_timeout_returns_the_best_order_found_so_far():
    slots, lineups = _random_instance(4, contests=6, per=4, fixed=0)
    ticks = iter(range(10_000))
    expired = ca.assign_contests(slots, lineups, restarts=500, time_limit_seconds=0.0,
                                 clock=lambda: float(next(ticks)))
    assert expired.timed_out and expired.order == tuple(range(len(slots)))
    assert expired.status in (ca.STATUS_UNCHANGED, ca.STATUS_NOT_APPLICABLE)

    ticks = iter(range(10_000))
    partial = ca.assign_contests(slots, lineups, restarts=500, time_limit_seconds=40.0,
                                 clock=lambda: float(next(ticks)))
    assert partial.timed_out
    start = _scores(slots, lineups, list(range(len(slots))))
    end = _scores(slots, lineups, partial.order)
    assert sum(end.values()) <= sum(start.values())
    assert sorted(partial.order) == list(range(len(slots)))


def test_lineups_never_cross_pools():
    slots = [ca.Slot("a", "c1", "bound"), ca.Slot("b", "c2", "bound"),
             ca.Slot("c", "c1", "fill"), ca.Slot("d", "c2", "fill")]
    lineups = [_facts({"1", "2", "3", "4", "5", "6"}), _facts({"1", "2", "3", "4", "5", "7"}),
               _facts({"1", "2", "3", "4", "5", "8"}), _facts({"9", "10", "11", "12", "13", "14"})]
    for restarts in (0, 30):
        result = ca.assign_contests(slots, lineups, restarts=restarts, time_limit_seconds=None)
        assert {result.order[0], result.order[1]} == {0, 1}
        assert {result.order[2], result.order[3]} == {2, 3}


def test_a_classic_pair_with_the_same_qb_is_split_across_two_entry_contests():
    """Week 3's shape: four lineups, two QBs, two two-entry contests."""

    def lineup(qb, rb):
        roster = (qb, rb, "d2", "d3", "d4", "d7", "d8", "d9", "d5")
        return ca.lineup_facts(roster, mode="CLASSIC", people=PEOPLE)

    lineups = [lineup("d0", "d1"), lineup("d0", "d13"), lineup("d6", "d7"), lineup("d6", "d13")]
    slots = [ca.Slot("a", "c1", "p"), ca.Slot("b", "c1", "p"), ca.Slot("c", "c2", "p"), ca.Slot("d", "c2", "p")]
    result = ca.assign_contests(slots, lineups, restarts=20, time_limit_seconds=None)
    for contest in ("c1", "c2"):
        assert result.after[contest]["distinct_key_people"] == 2


def test_mismatched_slots_and_lineups_are_refused():
    with pytest.raises(ca.ContestAssignmentError, match="COUNTS_DIFFER"):
        ca.assign_contests([ca.Slot("a", "c", "p")], [])


# --- the entry-level API and the independent audit -----------------------------


def _rows():
    people = {f"s{i}": ca.Person(f"person{i}") for i in range(30)}
    people.update({f"c{i}": ca.Person(f"person{i}") for i in range(30)})

    def roster(captain: int, *flex: int) -> tuple[str, ...]:
        return (f"c{captain}",) + tuple(f"s{i}" for i in flex)

    rows = [
        ca.EntryRow("1", "A", roster(1, 2, 3, 4, 5, 6), "p"),
        ca.EntryRow("2", "A", roster(1, 2, 3, 4, 5, 7), "p"),
        ca.EntryRow("3", "B", roster(8, 9, 10, 11, 12, 13), "p"),
        ca.EntryRow("4", "B", roster(14, 15, 16, 17, 18, 19), "p"),
        ca.EntryRow("5", "B", roster(1, 2, 3, 4, 5, 20), None),
        ca.EntryRow("6", "C", None, None),
    ]
    return rows, people


def test_diversify_keeps_the_fixed_row_and_the_unresolved_row_and_reports_them():
    rows, people = _rows()
    out = ca.diversify(rows, mode="SHOWDOWN", people=people, restarts=10, time_limit_seconds=None)
    assert set(out.assignments) == {"1", "2", "3", "4"}
    assert Counter(out.assignments.values()) == Counter(r.roster for r in rows if r.pool == "p")
    assert out.report["fixed_entry_ids"] == ["5", "6"]
    assert out.report["unscored_entry_ids"] == ["6"]
    assert out.report["single_entry_contest_count"] == 1
    assert out.report["contests_after"]["A"]["distinct_key_people"] >= 1


def test_audit_passes_the_assignment_diversify_made_and_recomputes_the_same_numbers():
    rows, people = _rows()
    out = ca.diversify(rows, mode="SHOWDOWN", people=people, restarts=10, time_limit_seconds=None)
    selected = {"p": [r.roster for r in rows if r.pool == "p"]}
    fixed = {r.entry_id: r.roster for r in rows if r.pool is None and r.roster is not None}
    problems, recomputed = ca.audit_contest_assignment(
        {**out.assignments, **fixed}, rows=rows, selected_by_pool=selected, mode="SHOWDOWN",
        people=people, reported_after=out.report["contests_after"])
    assert problems == []
    assert recomputed == dict(out.report["contests_after"])


def test_audit_refuses_a_lineup_from_outside_the_selection():
    rows, people = _rows()
    out = ca.diversify(rows, mode="SHOWDOWN", people=people, restarts=5, time_limit_seconds=None)
    selected = {"p": [r.roster for r in rows if r.pool == "p"]}
    tampered = dict(out.assignments)
    tampered["3"] = ("c25", "s26", "s27", "s28", "s29", "s22")
    problems, _ = ca.audit_contest_assignment(
        tampered, rows=rows, selected_by_pool=selected, mode="SHOWDOWN", people=people)
    assert "CONTEST_ASSIGNMENT_MULTISET_CHANGED:p" in problems


def test_audit_refuses_a_moved_fixed_row():
    rows, people = _rows()
    out = ca.diversify(rows, mode="SHOWDOWN", people=people, restarts=5, time_limit_seconds=None)
    selected = {"p": [r.roster for r in rows if r.pool == "p"]}
    moved = {**out.assignments, "5": rows[0].roster}
    problems, _ = ca.audit_contest_assignment(
        moved, rows=rows, selected_by_pool=selected, mode="SHOWDOWN", people=people)
    assert "CONTEST_ASSIGNMENT_FIXED_ROW_MOVED:5" in problems


def test_audit_refuses_statistics_the_step_reported_but_the_bytes_do_not_bear_out():
    rows, people = _rows()
    out = ca.diversify(rows, mode="SHOWDOWN", people=people, restarts=5, time_limit_seconds=None)
    selected = {"p": [r.roster for r in rows if r.pool == "p"]}
    lie = {c: dict(v, worst_pair_shared_people=0) for c, v in out.report["contests_after"].items()}
    lie["A"]["worst_pair_shared_people"] = 99
    problems, _ = ca.audit_contest_assignment(
        out.assignments, rows=rows, selected_by_pool=selected, mode="SHOWDOWN", people=people,
        reported_after=lie)
    assert "CONTEST_ASSIGNMENT_STATS_MISMATCH" in problems


def test_audit_refuses_an_entry_id_the_template_never_held():
    rows, people = _rows()
    selected = {"p": [r.roster for r in rows if r.pool == "p"]}
    problems, _ = ca.audit_contest_assignment(
        {**{r.entry_id: r.roster for r in rows if r.pool == "p"}, "999": rows[0].roster},
        rows=rows, selected_by_pool=selected, mode="SHOWDOWN", people=people)
    assert "CONTEST_ASSIGNMENT_MULTISET_CHANGED:entry_ids" in problems
