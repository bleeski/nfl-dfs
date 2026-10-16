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


# --- Session 76: within_contest_diversity_v2 (R38, first place in each contest) ---------

V1, V2 = ca.CONTEST_ASSIGNMENT_VERSION_V1, ca.CONTEST_ASSIGNMENT_VERSION_V2
V1_REPORT_KEYS = {
    "contest_assignment_version", "does_not_establish", "score_definition", "weights", "status",
    "total_score_before", "total_score_after", "moved_rows", "restarts_run", "timed_out", "seed", "seconds",
}


def _placed(slots, lineups, order):
    by_contest: dict[str, list[ca.LineupFacts]] = {}
    for slot, index in zip(slots, order):
        by_contest.setdefault(slot.contest_id, []).append(lineups[index])
    return by_contest


def _objective(slots, lineups, order):
    """v2's total, recomputed here from the placement: four exact counts, then the spread."""

    readings = [ca.contest_objective(placed) for placed in _placed(slots, lineups, order).values() if len(placed) > 1]
    return (
        sum(1 for r in readings if r["repeated_key_person"]),
        sum(r["lost_key_people"] for r in readings),
        sum(r["same_key_person_pairs"] for r in readings),
        sum(r["same_thesis_pairs"] for r in readings),
        sum(Fraction(r["spread"]) for r in readings),
    )


def _captains(slots, lineups, order):
    return {contest: sorted(f.key_person for f in placed)
            for contest, placed in _placed(slots, lineups, order).items()}


def _overlap_saving_instance():
    """v1 keeps Captain A twice in one contest because every arrangement without the repeat shares more people.

    L1 and L2 (both Captain A) share only A, 1 + 12 = 13. L3 and L4 each hold A at FLEX and three of each A lineup's
    people, so each cross pair shares 3 (cost 9). v1: {L1,L2} and {L3,L4} score 2 x 13 + 2 x 1 = 28 against 36.
    """

    l1 = _facts({"A", "a1", "a2", "a3", "a4", "a5"}, key="A")
    l2 = _facts({"A", "b1", "b2", "b3", "b4", "b5"}, key="A")
    l3 = _facts({"B", "A", "a1", "a2", "b1", "b2"}, key="B")
    l4 = _facts({"C", "A", "a3", "a4", "b3", "b4"}, key="C")
    slots = [ca.Slot("e1", "c1", "p"), ca.Slot("e2", "c1", "p"), ca.Slot("e3", "c2", "p"), ca.Slot("e4", "c2", "p")]
    return slots, [l1, l2, l3, l4]


def test_v2_is_registered_beside_v1_and_the_module_default_stays_v1():
    assert ca.CONTEST_ASSIGNMENT_VERSIONS == (V1, V2) == ("within_contest_diversity_v1", "within_contest_diversity_v2")
    assert ca.CONTEST_ASSIGNMENT_VERSION == V1  # the baseline's step; `prior_review` passes v2
    assert ca.ARTIFACT_VERSION_FOR == {V1: "nfl_contest_assignment_step_v1", V2: "nfl_contest_assignment_step_v2"}
    assert ca.OBJECTIVE_ORDER == ("contests_with_a_repeated_key_person", "lost_key_people", "same_key_person_pairs",
                                  "same_thesis_pairs", "spread")
    with pytest.raises(ca.ContestAssignmentError, match="UNKNOWN_VERSION"):
        ca.assign_contests(*_overlap_saving_instance(), version="within_contest_diversity_v9")


def test_v2_avoids_the_repeated_captain_v1_keeps_for_an_overlap_saving():
    slots, lineups = _overlap_saving_instance()
    v1 = ca.assign_contests(slots, lineups, restarts=20, time_limit_seconds=None)
    assert v1.status == ca.STATUS_UNCHANGED and _captains(slots, lineups, v1.order)["c1"] == ["A", "A"]
    v2 = ca.assign_contests(slots, lineups, restarts=20, time_limit_seconds=None, version=V2)
    assert v2.status == ca.STATUS_IMPROVED
    assert all(len(set(keys)) == len(keys) for keys in _captains(slots, lineups, v2.order).values())
    assert _objective(slots, lineups, v2.order)[:4] == (0, 0, 0, 0)
    # The trade v2 exists for: its own spread, and v1's reading of the placement, both rise.
    assert _objective(slots, lineups, v2.order)[4] > _objective(slots, lineups, v1.order)[4]
    assert float(v2.total_after) > float(v2.total_before)


def test_v2_keeps_a_contest_clean_before_it_spreads_a_forced_repeat():
    """(a) before (b'): contests of 2 and 6, Captains A x5, B, C, D. Cleaning the two-entry contest piles four A
    lineups into the six (6 same-Captain pairs); the alternative dirties both (1 + 3 = 4 pairs). Lost shots tie at 3."""

    keys = ["A", "A", "A", "A", "A", "B", "C", "D"]
    lineups = [_facts({f"{key}{i}", f"x{i}"}, key=key) for i, key in enumerate(keys)]
    slots = [ca.Slot(f"e{i}", "small" if i < 2 else "big", "p") for i in range(8)]
    result = ca.assign_contests(slots, lineups, restarts=30, time_limit_seconds=None, version=V2)
    captains = _captains(slots, lineups, result.order)
    assert len(set(captains["small"])) == 2 and captains["big"].count("A") == 4
    assert _objective(slots, lineups, result.order)[:3] == (1, 3, 6)


def test_v2_spreads_a_forced_repeat_evenly_and_moves_one_entry_rows_to_do_it():
    """(b'): one four-entry contest beside two one-entry contests, Captains A x3, B x3. {A,A,B,B} (2 pairs) beats
    {A,A,A,B} (3 pairs) at the same 2 lost. v1 holds one-entry rows, so it has nothing to swap."""

    keys = ["A", "A", "A", "B", "B", "B"]
    lineups = [_facts({f"p{i}"}, key=key) for i, key in enumerate(keys)]
    slots = [ca.Slot(f"e{i}", "big", "p") for i in range(4)] + [ca.Slot("s1", "solo1", "p"), ca.Slot("s2", "solo2", "p")]
    v1 = ca.assign_contests(slots, lineups, restarts=10, time_limit_seconds=None)
    assert v1.status == ca.STATUS_NOT_APPLICABLE and v1.order == tuple(range(6))
    held = ca.assign_contests(slots, lineups, restarts=10, time_limit_seconds=None, version=V2,
                              move_single_entry_rows=False)
    assert held.status == ca.STATUS_NOT_APPLICABLE and held.order == tuple(range(6))
    v2 = ca.assign_contests(slots, lineups, restarts=10, time_limit_seconds=None, version=V2)
    assert _captains(slots, lineups, v2.order)["big"] == ["A", "A", "B", "B"]
    assert _objective(slots, lineups, v2.order)[:3] == (1, 2, 2)
    assert v2.as_report()["single_entry_rows_move"] is True and held.as_report()["single_entry_rows_move"] is False


def test_v2_separates_two_lineups_of_one_thesis_whatever_the_shared_people_cost():
    """(c) before (d). Session 67 pinned v1 keeping same-thesis pairs where a mixed pair shares 3 people against 2;
    under v2 the thesis comes first."""

    # A same-thesis pair shares 2 people (cost 4 + 3 = 7 in v1), every mixed pair 3 (cost 9).
    shared = {pair: {f"{pair}{i}" for i in range(3)} for pair in ("p13", "p14", "p23", "p24")}
    lineups = [
        _facts({"k1", "a", "b"} | shared["p13"] | shared["p14"], key="k1", thesis="t1"),
        _facts({"k2", "a", "b"} | shared["p23"] | shared["p24"], key="k2", thesis="t1"),
        _facts({"k3", "c", "d"} | shared["p13"] | shared["p23"], key="k3", thesis="t2"),
        _facts({"k4", "c", "d"} | shared["p14"] | shared["p24"], key="k4", thesis="t2"),
    ]
    slots = [ca.Slot("e1", "c1", "p"), ca.Slot("e2", "c1", "p"), ca.Slot("e3", "c2", "p"), ca.Slot("e4", "c2", "p")]
    v1 = ca.assign_contests(slots, lineups, restarts=20, time_limit_seconds=None)
    assert _objective(slots, lineups, v1.order)[3] == 2
    v2 = ca.assign_contests(slots, lineups, restarts=20, time_limit_seconds=None, version=V2)
    assert _objective(slots, lineups, v2.order)[3] == 0
    assert _objective(slots, lineups, v2.order)[4] > _objective(slots, lineups, v1.order)[4]


def test_v2_lowers_shared_people_once_every_count_ties():
    near = [_facts({"k1", "a", "b", "c"}, key="k1"), _facts({"k2", "a", "b", "c"}, key="k2")]
    far = [_facts({"k3", "x", "y", "z"}, key="k3"), _facts({"k4", "u", "v", "w"}, key="k4")]
    lineups = [near[0], near[1], far[0], far[1]]
    slots = [ca.Slot("e1", "c1", "p"), ca.Slot("e2", "c1", "p"), ca.Slot("e3", "c2", "p"), ca.Slot("e4", "c2", "p")]
    v2 = ca.assign_contests(slots, lineups, restarts=10, time_limit_seconds=None, version=V2)
    assert v2.status == ca.STATUS_IMPROVED
    assert _objective(slots, lineups, v2.order) < _objective(slots, lineups, tuple(range(4)))


def test_v2_compares_four_counts_exactly_and_the_spread_within_epsilon():
    better = ca.objective_improves
    assert better((0, 0, 0, 0, 100.0), (0, 0, 0, 1, 0.0))
    assert better((0, 5, 9, 9, 99.0), (1, 0, 0, 0, 0.0))
    assert not better((0, 0, 0, 0, 1.0 - 1e-12), (0, 0, 0, 0, 1.0))
    assert better((0, 0, 0, 0, 1.0 - 1e-6), (0, 0, 0, 0, 1.0))
    assert not better((0, 0, 0, 0, 1.0), (0, 0, 0, 0, 1.0))


def test_the_contest_objective_reads_one_contest():
    placed = [_facts({"A", "x", "y"}, key="A", thesis="t"), _facts({"A", "x", "z"}, key="A", thesis="t"),
              _facts({"A", "q"}, key="A"), _facts({"B", "x"}, key="B", thesis="t"), _facts({"C"}, key=None)]
    reading = ca.contest_objective(placed)
    assert reading["repeated_key_person"] is True
    assert reading["lost_key_people"] == 2 and reading["same_key_person_pairs"] == 3
    assert reading["same_thesis_pairs"] == 3
    # shared people squared, worst plus mean over the 10 pairs: the worst pair shares A and x (4)
    shared = [len(a.people & b.people) ** 2 for i, a in enumerate(placed) for b in placed[i + 1:]]
    assert reading["spread"] == f"{float(Fraction(max(shared)) + Fraction(sum(shared), len(shared))):.6f}"
    assert ca.contest_objective([placed[0]]) == {"repeated_key_person": False, "lost_key_people": 0,
                                                 "same_key_person_pairs": 0, "same_thesis_pairs": 0,
                                                 "spread": "0.000000"}


def test_the_v2_spread_counts_the_classic_stack_team_and_nothing_ranked_above_it():
    a = _facts({"a", "b"}, key="k", stack="T", thesis="x")
    b = _facts({"a", "c"}, key="k", stack="T", thesis="x")
    assert ca.spread_cost(a, b) == 1 + 6
    assert ca.spread_cost(a, _facts({"z"}, stack="U")) == 0


@pytest.mark.parametrize("seed", range(6))
def test_v2_is_a_permutation_inside_each_pool_and_never_moves_a_fixed_row(seed):
    slots, lineups = _random_instance(seed)
    result = ca.assign_contests(slots, lineups, restarts=20, time_limit_seconds=None, version=V2)
    assert sorted(result.order) == list(range(len(slots)))
    assert all(result.order[i] == i for i, slot in enumerate(slots) if slot.pool is None)
    movable = [i for i, s in enumerate(slots) if s.pool == "p"]
    assert Counter(result.order[i] for i in movable) == Counter(movable)
    pooled = [ca.Slot("a", "c1", "bound"), ca.Slot("b", "c2", "bound"), ca.Slot("c", "c1", "fill"),
              ca.Slot("d", "c2", "fill"), ca.Slot("e", "solo", "fill")]
    facts = [_facts({"1", "2"}, key="k"), _facts({"1", "3"}, key="k"), _facts({"9"}, key="k"),
             _facts({"8"}, key="j"), _facts({"7"}, key="i")]
    out = ca.assign_contests(pooled, facts, restarts=10, time_limit_seconds=None, version=V2)
    assert {out.order[0], out.order[1]} == {0, 1} and {out.order[2], out.order[3], out.order[4]} == {2, 3, 4}


@pytest.mark.parametrize("seed", range(8))
def test_v2_s_total_never_rises_above_the_solver_order(seed):
    slots, lineups = _random_instance(seed, contests=6, per=3, fixed=1)
    result = ca.assign_contests(slots, lineups, restarts=25, time_limit_seconds=None, version=V2)
    start, end = _objective(slots, lineups, tuple(range(len(slots)))), _objective(slots, lineups, result.order)
    assert end[:4] < start[:4] or (end[:4] == start[:4] and end[4] <= start[4])
    assert (result.status == ca.STATUS_IMPROVED) == (end != start)


def test_v2_s_timeout_keeps_the_best_order_found():
    slots, lineups = _random_instance(4, contests=6, per=4, fixed=0)
    ticks = iter(range(10_000))
    expired = ca.assign_contests(slots, lineups, restarts=500, time_limit_seconds=0.0, version=V2,
                                 clock=lambda: float(next(ticks)))
    assert expired.timed_out and expired.order == tuple(range(len(slots)))
    ticks = iter(range(10_000))
    partial = ca.assign_contests(slots, lineups, restarts=500, time_limit_seconds=40.0, version=V2,
                                 clock=lambda: float(next(ticks)))
    start, end = _objective(slots, lineups, tuple(range(len(slots)))), _objective(slots, lineups, partial.order)
    assert partial.timed_out and not ca.objective_improves(start, end)


def test_v2_gives_the_same_order_and_report_for_the_same_inputs():
    slots, lineups = _random_instance(3)
    first = ca.assign_contests(slots, lineups, restarts=15, time_limit_seconds=None, version=V2)
    second = ca.assign_contests(slots, lineups, restarts=15, time_limit_seconds=None, version=V2)
    assert first.order == second.order
    assert {k: v for k, v in first.as_report().items() if k != "seconds"} == {
        k: v for k, v in second.as_report().items() if k != "seconds"}


def test_the_v2_report_names_its_objective_and_keeps_v1_s_readings():
    slots, lineups = _random_instance(5)
    result = ca.assign_contests(slots, lineups, restarts=10, time_limit_seconds=None, version=V2)
    report = result.as_report()
    assert set(report) == V1_REPORT_KEYS | {"objective_order", "reading_definition", "objective_before",
                                            "objective_after", "single_entry_rows_move"}
    assert report["contest_assignment_version"] == V2
    assert report["score_definition"] == ca.CONTEST_OBJECTIVE_DEFINITION
    assert report["reading_definition"] == ca.READING_DEFINITION
    assert report["objective_order"] == list(ca.OBJECTIVE_ORDER)
    assert report["weights"] == {"shared_people_exponent": 2, "same_stack_team": 6, "registered": True}
    assert "PAYOUT_OR_CONTEST_WORTH" in report["does_not_establish"]
    placed = _placed(slots, lineups, result.order)
    # The readings are v1's, with v1's registered weights, whatever the version.
    assert dict(result.after) == {c: ca.contest_statistics(p) for c, p in placed.items() if len(p) > 1}
    assert dict(result.objective_after) == {c: ca.contest_objective(p) for c, p in placed.items() if len(p) > 1}
    end = _objective(slots, lineups, result.order)
    assert report["objective_after"] == {
        "contests_with_a_repeated_key_person": end[0], "lost_key_people": end[1], "same_key_person_pairs": end[2],
        "same_thesis_pairs": end[3],
        "spread": f"{sum(float(r['spread']) for r in result.objective_after.values()):.6f}"}


def test_the_v1_report_keeps_exactly_its_keys():
    slots, lineups = _random_instance(5)
    assert set(ca.assign_contests(slots, lineups, restarts=3).as_report()) == V1_REPORT_KEYS
    rows, people = _rows()
    report = ca.diversify(rows, mode="SHOWDOWN", people=people, restarts=3, time_limit_seconds=None).report
    assert not {"contest_objective_before", "contest_objective_after", "single_entry_contests_moved",
                "objective_order"} & set(report)


def _v2_rows():
    people = {f"c{i}": ca.Person(f"person{i}") for i in range(30)}
    people.update({f"s{i}": ca.Person(f"person{i}") for i in range(30)})

    def roster(captain: int, *flex: int) -> tuple[str, ...]:
        return (f"c{captain}",) + tuple(f"s{i}" for i in flex)

    rows = [
        ca.EntryRow("1", "A", roster(1, 2, 3, 4, 5, 6), "p"),
        ca.EntryRow("2", "A", roster(1, 7, 8, 9, 10, 11), "p"),
        ca.EntryRow("3", "B", roster(12, 13, 14, 15, 16, 17), "p"),
        ca.EntryRow("4", "B", roster(18, 19, 20, 21, 22, 23), "p"),
        ca.EntryRow("5", "S", roster(24, 25, 26, 27, 28, 29), "p"),
    ]
    return rows, people


def test_diversify_v2_reports_each_contest_s_objective_and_the_one_entry_contests_it_changed():
    rows, people = _v2_rows()
    out = ca.diversify(rows, mode="SHOWDOWN", people=people, restarts=10, time_limit_seconds=None, version=V2)
    report = out.report
    assert report["contest_assignment_version"] == V2
    assert report["contest_objective_before"]["A"]["repeated_key_person"] is True
    assert all(not reading["repeated_key_person"] for reading in report["contest_objective_after"].values())
    assert set(report["contest_objective_after"]) == {"A", "B"}
    moved_solo = out.assignments["5"] != rows[4].roster
    assert report["single_entry_contests_moved"] == (["S"] if moved_solo else [])


def test_apply_step_v2_carries_its_version_into_the_claim_and_the_audit_recomputes_the_objective():
    from types import SimpleNamespace

    rows, people = _v2_rows()
    players = [SimpleNamespace(dk_id=dk_id, underlying_id=person.key, team=None, position=None)
               for dk_id, person in people.items()]
    plan = SimpleNamespace(
        order=[row.entry_id for row in rows], prefilled={},
        groups=[SimpleNamespace(contest_id=c, entry_ids=[r.entry_id for r in rows if r.contest_id == c])
                for c in ("A", "B", "S")])
    assignments = {row.entry_id: row.roster for row in rows}
    step = ca.apply_step(mode=ca.MODE_SHOWDOWN, players=players, entry_plan=plan, assignments=assignments,
                         restarts=10, time_limit_seconds=None, version=V2)
    assert step.failure is None and step.claim.version == V2
    assert step.report["contest_assignment_version"] == V2
    problems, recomputed = step.claim.audit(step.assignments)
    assert problems == [] and recomputed == dict(step.report["contests_after"])
    lie = {c: dict(v, same_key_person_pairs=7) for c, v in step.report["contest_objective_after"].items()}
    lying = ca.Claim(step.claim.rows, step.claim.selected_by_pool, step.claim.mode, step.claim.people,
                     reported_after=step.claim.reported_after, version=V2, reported_objective_after=lie)
    assert "CONTEST_ASSIGNMENT_STATS_MISMATCH" in lying.audit(step.assignments)[0]
    v1 = ca.apply_step(mode=ca.MODE_SHOWDOWN, players=players, entry_plan=plan, assignments=assignments,
                       restarts=10, time_limit_seconds=None)
    assert v1.claim.version == V1 and v1.report["contest_assignment_version"] == V1
    failed = ca.apply_step(mode=ca.MODE_SHOWDOWN, players=players, entry_plan=plan, assignments=assignments,
                           version="within_contest_diversity_v9")
    assert failed.failure and "UNKNOWN_VERSION" in failed.failure
    assert failed.report["contest_assignment_version"] == "within_contest_diversity_v9"


def _review(version):
    rows, people = _v2_rows()
    out = ca.diversify(rows, mode="SHOWDOWN", people=people, restarts=10, time_limit_seconds=None, version=version)
    delivered = [(r.entry_id, r.contest_id, tuple(out.assignments[r.entry_id]), "all") for r in rows]
    return ca.review_block(mode=ca.MODE_SHOWDOWN, people=people, rows=delivered,
                           selected_in_solver_order=[r.roster for r in rows], reported=out.report), out


def test_the_v2_review_block_recomputes_and_reconciles_the_objective():
    (block, problems), out = _review(V2)
    assert problems == [] and block["reported_statistics_match"] is True
    assert block["contest_assignment_version"] == V2 and block["objective_order"] == list(ca.OBJECTIVE_ORDER)
    assert block["score_definition"] == ca.CONTEST_OBJECTIVE_DEFINITION
    assert block["objective_after"] == out.report["objective_after"]
    assert block["objective_before"] == out.report["objective_before"]
    row = next(r for r in block["contests"] if r["contest_id"] == "A")
    assert (row["same_key_person_pairs_before"], row["same_key_person_pairs"]) == (1, 0)
    assert {"lost_key_people", "lost_key_people_before", "same_thesis_pairs", "same_thesis_pairs_before",
            "spread", "spread_before"} <= set(row)
    lie = dict(out.report, contest_objective_after={
        c: dict(v, lost_key_people=5) for c, v in out.report["contest_objective_after"].items()})
    rows, people = _v2_rows()
    delivered = [(r.entry_id, r.contest_id, tuple(out.assignments[r.entry_id]), "all") for r in rows]
    _block, found = ca.review_block(mode=ca.MODE_SHOWDOWN, people=people, rows=delivered,
                                    selected_in_solver_order=[r.roster for r in rows], reported=lie)
    assert found == ["CONTEST_ASSIGNMENT_STATS_MISMATCH"]
    # The one-entry contests that changed are recomputed from the rosters, never copied from the record.
    moved = out.report["single_entry_contests_moved"]
    assert block["single_entry_contests_moved"] == moved
    lie = dict(out.report, single_entry_contests_moved=[] if moved else ["S"])
    lied, found = ca.review_block(mode=ca.MODE_SHOWDOWN, people=people, rows=delivered,
                                  selected_in_solver_order=[r.roster for r in rows], reported=lie)
    assert found == ["CONTEST_ASSIGNMENT_STATS_MISMATCH"] and lied["single_entry_contests_moved"] == moved


def test_a_v1_review_block_keeps_exactly_its_keys():
    (block, problems), _out = _review(V1)
    assert problems == []
    assert set(block) == {
        "contest_assignment_version", "does_not_establish", "score_definition", "basis", "status", "key_person",
        "moved_rows", "timed_out", "restarts_run", "seed", "error", "total_score_before", "total_score_after",
        "single_entry_contest_count", "reported_statistics_match", "contests"}
    assert block["contest_assignment_version"] == V1
    assert set(block["contests"][0]) == {
        "contest_id", "entries", "worst_pair_shared_people", "worst_pair_shared_people_before", "mean_shared_people",
        "mean_shared_people_before", "distinct_key_people", "distinct_key_people_before", "distinct_stack_teams",
        "distinct_theses", "people_in_every_lineup", "score_before", "score_after"}


# --- Session 76b: the combinations only the offline wrapper reaches -------------------


def _solo_instance():
    keys = ["A", "A", "A", "B", "B", "B"]
    lineups = [_facts({f"p{i}"}, key=key) for i, key in enumerate(keys)]
    slots = [ca.Slot(f"e{i}", "big", "p") for i in range(4)] + [ca.Slot("s1", "solo1", "p"), ca.Slot("s2", "solo2", "p")]
    return slots, lineups


def test_a_v1_report_names_a_rule_it_was_asked_to_break_and_only_then():
    """v1 holds one-entry rows and keeps its per-contest guard. Session 76's reviewer found a caller could move those rows
    and still get a plain v1 report; dropping the guard was the same hole. Each departure is now named in the report, and
    the registered v1 report keeps exactly its keys."""

    slots, lineups = _solo_instance()
    run = lambda **kw: ca.assign_contests(slots, lineups, restarts=10, time_limit_seconds=None, **kw).as_report()  # noqa: E731
    assert set(run()) == V1_REPORT_KEYS
    assert set(run(move_single_entry_rows=False)) == set(run(no_regression=True)) == V1_REPORT_KEYS
    moved = run(move_single_entry_rows=True)
    assert set(moved) == V1_REPORT_KEYS | {"single_entry_rows_move"} and moved["single_entry_rows_move"] is True
    assert moved["contest_assignment_version"] == V1
    unguarded = run(no_regression=False)
    assert set(unguarded) == V1_REPORT_KEYS | {"no_regression"} and unguarded["no_regression"] is False
    both = run(move_single_entry_rows=True, no_regression=False)
    assert both["single_entry_rows_move"] is True and both["no_regression"] is False
    # v2 has no per-contest guard, so the argument changes nothing there and its report is unchanged.
    v2 = ca.assign_contests(slots, lineups, restarts=10, time_limit_seconds=None, version=V2, no_regression=False)
    assert "no_regression" not in v2.as_report()
    rows = [ca.EntryRow(s.entry_id, s.contest_id, (f"d{i}",), "p") for i, s in enumerate(slots)]
    people = {f"d{i}": ca.Person(key=f"k{i // 3}") for i in range(6)}
    out = ca.diversify(rows, mode=ca.MODE_SHOWDOWN, people=people, restarts=5, time_limit_seconds=None,
                       move_single_entry_rows=True)
    assert out.report["single_entry_rows_move"] is True


def test_the_audit_recomputes_v2_s_objective_with_the_stack_weight_the_step_used():
    """The offline wrapper's `--stack-penalty` under v2 changes the spread's stack term. Three of four Classic lineups stack
    team AAA in two two-entry contests, so one contest must pair two of them and the weight reaches the spread."""

    rows = [
        ca.EntryRow("1", "K1", ("d0", "d1", "d2"), "p"),    # QB AAA, stack AAA
        ca.EntryRow("2", "K1", ("d2", "d3", "d4"), "p"),    # no QB, stack AAA
        ca.EntryRow("3", "K2", ("d1", "d3", "d4"), "p"),    # no QB, stack AAA
        ca.EntryRow("4", "K2", ("d6", "d7", "d8"), "p"),    # QB BBB, stack BBB
    ]
    override = ca.Weights(stack_team=50)
    out = ca.diversify(rows, mode=ca.MODE_CLASSIC, people=PEOPLE, restarts=5, time_limit_seconds=None,
                       version=V2, weights=override)
    assert out.report["weights"] == {"shared_people_exponent": 2, "same_stack_team": 50, "registered": False}
    triples = [(r.entry_id, r.contest_id, out.assignments[r.entry_id]) for r in rows]
    recomputed = ca.objectives_from_rosters(triples, mode=ca.MODE_CLASSIC, people=PEOPLE, weights=override)
    assert recomputed == dict(out.report["contest_objective_after"])
    assert recomputed != ca.objectives_from_rosters(triples, mode=ca.MODE_CLASSIC, people=PEOPLE)
    audit = dict(rows=rows, selected_by_pool={"p": [r.roster for r in rows]}, mode=ca.MODE_CLASSIC, people=PEOPLE,
                 reported_after=out.report["contests_after"], version=V2,
                 reported_objective_after=out.report["contest_objective_after"])
    assert ca.audit_contest_assignment(dict(out.assignments), objective_weights=override, **audit)[0] == []
    # Recomputed with the registered weight, the override's own numbers do not bear out.
    assert ca.audit_contest_assignment(dict(out.assignments), **audit)[0] == ["CONTEST_ASSIGNMENT_STATS_MISMATCH"]
