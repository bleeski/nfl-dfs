"""Session 67: the thesis label is live inside the contest step (`within_contest_diversity_v1`'s same-thesis term).

The registered pair cost already had a term for two lineups of one thesis (weight 3, Session 50); nothing in `run-slate`
fed it a label. Now the selection's `by_lineup` (canonical lineup to thesis) reaches `apply_step` as a map keyed by the
exact roster, so it follows a lineup wherever the step moves it, and every site that recomputes the step's figures from
the delivered bytes uses the same labels: the audit through the step's claim, the readable review from its own reading
of the selection record's lineups (each roster and its thesis). A run with no theses carries no label and places
lineups as it did.

Against shared people the label's 3 outweighs a pair going from 0 to 1 shared person (cost 1), ties one going from 1 to
2 (cost 3: nothing moves) and loses to 2 to 3 or more (cost 5 and up); the tests below pin all three. The weight is not
changed here. A thesis is a choice, not a forecast; none of this is EV or a payout claim.
"""

from __future__ import annotations

import dataclasses
import itertools
from fractions import Fraction
from types import SimpleNamespace

import pytest

from nfl_dfs import contest_assignment as ca
from nfl_dfs import prior_review
from nfl_dfs.lineups import roster_canonical_key
from nfl_dfs.readable_review import ReadableReviewError

from .test_contest_assignment_run_slate import INTERLEAVED_CONTESTS, _assert_truths_unchanged
from .test_readable_review_theses import _controls, _doctored, _finished
from .test_showdown_thesis_acceptance import build_world, r33_theses

# ------------------------------------------------------------------ a pure fixture through `apply_step`


def _players(rosters):
    people = sorted({dk_id for roster in rosters for dk_id in roster})
    return [SimpleNamespace(dk_id=dk_id, underlying_id=f"person:{dk_id}", team="AAA", position="WR") for dk_id in people]


def _plan(contests, prefilled=None):
    groups = {}
    for entry_id, contest_id in contests.items():
        groups.setdefault(contest_id, []).append(entry_id)
    return SimpleNamespace(
        order=list(contests),
        groups=[SimpleNamespace(contest_id=c, entry_ids=tuple(ids)) for c, ids in groups.items()],
        prefilled={e: SimpleNamespace(roster=tuple(r), resolved=True) for e, r in (prefilled or {}).items()})


def _lineup(tag, shared=()):
    """Six people: a Captain of its own, the named shared people, then people no other lineup holds."""

    own = [f"{tag}-cpt", *shared]
    return tuple(own + [f"{tag}-{index}" for index in range(6 - len(own))])


def _step(contests, assignments, labels, *, prefilled=None, bound=()):
    rosters = [*assignments.values(), *(prefilled or {}).values()]
    return ca.apply_step(
        mode=ca.MODE_SHOWDOWN, players=_players(rosters), entry_plan=_plan(contests, prefilled),
        assignments=assignments, bound_ids=bound, thesis_by_roster=labels, time_limit_seconds=None)


def _same_thesis_pairs(assignment, contests, labels, prefilled=None):
    held = {**{e: tuple(r) for e, r in (prefilled or {}).items()}, **{e: tuple(r) for e, r in assignment.items()}}
    by_contest = {}
    for entry_id, roster in held.items():
        by_contest.setdefault(contests[entry_id], []).append(labels.get(roster))
    return sum(1 for theses in by_contest.values() for a, b in itertools.combinations(theses, 2)
               if a is not None and a == b)


def _without_seconds(report):
    return {key: value for key, value in report.items() if key != "seconds"}


FOUR = {"e1": "A", "e2": "A", "e3": "B", "e4": "B"}


def _four():
    lineups = [_lineup(tag) for tag in ("L1", "L2", "L3", "L4")]
    assignments = dict(zip(FOUR, lineups))
    labels = {lineups[0]: "T1", lineups[1]: "T1", lineups[2]: "T2", lineups[3]: "T2"}
    return assignments, labels


def test_with_labels_no_contest_holds_two_of_one_thesis_when_a_mixed_pair_is_available():
    # Every pair shares nobody and every Captain differs, so only the label can tell placements apart. In the solver's
    # order thesis T1 fills contest A and T2 fills B.
    assignments, labels = _four()
    plain = _step(FOUR, assignments, None)
    assert plain.report["status"] == ca.STATUS_UNCHANGED and plain.assignments == assignments
    assert _same_thesis_pairs(plain.assignments, FOUR, labels) == 2

    labelled = _step(FOUR, assignments, labels)
    assert labelled.failure is None
    assert labelled.report["status"] == ca.STATUS_IMPROVED and labelled.report["moved_rows"] == 2
    assert _same_thesis_pairs(labelled.assignments, FOUR, labels) == 0
    assert {c: s["distinct_theses"] for c, s in labelled.report["contests_after"].items()} == {"A": 2, "B": 2}
    # The lineups are the selection's; only which entry holds which moved.
    assert sorted(labelled.assignments.values()) == sorted(assignments.values())
    # The step's own no-regression rule, scored with the labels: no contest worse than in the solver's order.
    before, after = labelled.report["contests_before"], labelled.report["contests_after"]
    assert all(Fraction(after[c]["score"]) <= Fraction(before[c]["score"]) for c in before)
    assert {c: s["worst_pair_shared_people"] for c, s in after.items()} == {"A": 0, "B": 0}


def test_none_and_an_empty_map_place_lineups_exactly_as_no_labels_did():
    assignments, _labels = _four()
    none, empty = _step(FOUR, assignments, None), _step(FOUR, assignments, {})
    assert none.assignments == empty.assignments == assignments
    assert _without_seconds(none.report) == _without_seconds(empty.report)
    assert none.claim.thesis_by_roster is None and empty.claim.thesis_by_roster is None


def test_where_no_spread_exists_the_step_reaches_the_fewest_same_thesis_pairs():
    contests = {f"e{i}": c for i, c in enumerate(("A", "A", "B", "B", "C", "C"), 1)}
    lineups = [_lineup(f"L{i}") for i in range(1, 7)]
    assignments = dict(zip(contests, lineups))
    # Four of T1 and two of T2 in three contests of two: one contest must hold two of T1.
    labels = {lineups[0]: "T1", lineups[1]: "T1", lineups[2]: "T1", lineups[3]: "T1", lineups[4]: "T2", lineups[5]: "T2"}
    assert _same_thesis_pairs(assignments, contests, labels) == 3
    labelled = _step(contests, assignments, labels)
    assert _same_thesis_pairs(labelled.assignments, contests, labels) == 1


def test_a_labelled_filled_row_stays_put_and_counts_in_its_contest():
    contests = {"e1": "A", "e2": "A", "e3": "B", "e4": "B"}
    fixed = _lineup("L0")
    lineups = [_lineup(tag) for tag in ("L1", "L2", "L3")]
    assignments = {"e2": lineups[0], "e3": lineups[1], "e4": lineups[2]}
    labels = {fixed: "T1", lineups[0]: "T1", lineups[1]: "T2", lineups[2]: "T2"}
    prefilled = {"e1": fixed}
    assert _same_thesis_pairs(assignments, contests, labels, prefilled) == 2
    labelled = _step(contests, assignments, labels, prefilled=prefilled)
    assert "e1" not in labelled.assignments and labelled.report["fixed_entry_ids"] == ["e1"]
    assert _same_thesis_pairs(labelled.assignments, contests, labels, prefilled) == 0
    assert labelled.assignments["e2"] in (lineups[1], lineups[2])


def test_a_label_never_moves_a_lineup_out_of_its_pool():
    # The policy's rows (e1, e2) share contest A and the fill rows (e3, e4) contest B: no swap inside a pool changes a
    # contest, and a swap across pools is never allowed, so the same-thesis pairs stay.
    assignments, labels = _four()
    labelled = _step(FOUR, assignments, labels, bound=("e1", "e2"))
    assert labelled.report["status"] == ca.STATUS_NOT_APPLICABLE
    assert labelled.assignments == assignments
    assert labelled.report["pools"] == {"bound": 2, "fill": 2}


def _uniform(same: int, mixed: int):
    """Four lineups: T1 holds L1 and L2, T2 holds L3 and L4; each same-thesis pair shares `same` people and every mixed
    pair `mixed`, each through people only that pair holds, and every Captain is its own."""

    shared = {pair: [f"{pair[0]}{pair[1]}-{k}" for k in range(same if pair in {(1, 2), (3, 4)} else mixed)]
              for pair in itertools.combinations((1, 2, 3, 4), 2)}
    lineups = []
    for index in (1, 2, 3, 4):
        members = [person for pair, people in shared.items() if index in pair for person in people]
        lineups.append(_lineup(f"L{index}", members))
    return lineups


@pytest.mark.parametrize(("same", "mixed", "separates"), [(0, 1, True), (1, 2, False)])
def test_the_registered_weight_against_one_more_shared_person(same, mixed, separates):
    # Separating two theses here turns two same-thesis pairs into two mixed pairs. From 0 to 1 shared person costs 1 a
    # pair against the label's 3, so the theses are separated and the worst pair rises from 0 to 1 (the registered
    # trade, not a regression against the solver's order, which scores the labels too). From 1 to 2 costs 3, a tie,
    # and the step moves only on a strict gain.
    l1, l2, l3, l4 = _uniform(same, mixed)
    assignments = {"e1": l1, "e2": l2, "e3": l3, "e4": l4}
    labels = {l1: "T1", l2: "T1", l3: "T2", l4: "T2"}
    plain = _step(FOUR, assignments, None)
    assert plain.report["status"] == ca.STATUS_UNCHANGED
    labelled = _step(FOUR, assignments, labels)
    worst = {c: s["worst_pair_shared_people"] for c, s in labelled.report["contests_after"].items()}
    if separates:
        assert labelled.report["status"] == ca.STATUS_IMPROVED
        assert _same_thesis_pairs(labelled.assignments, FOUR, labels) == 0
        assert worst == {"A": mixed, "B": mixed}
    else:
        assert labelled.report["status"] == ca.STATUS_UNCHANGED and labelled.assignments == assignments
        assert worst == {"A": same, "B": same}


def test_the_registered_weight_loses_to_a_step_from_two_to_three_shared_people():
    # Same-thesis pairs share 2 people; every mixed pair would share 3. Separating the theses costs 3**2 - 2**2 = 5 per
    # pair, more than the label's 3, so with the registered weights the same-thesis pairs stay. A heavier weight (an
    # offline override, not the registered rule) would separate them, which shows it is the weight that decides.
    l1 = ("c1", "a", "b", "p", "q", "r")
    l2 = ("c2", "a", "b", "s", "t", "u")
    l3 = ("c3", "a", "p", "q", "s", "t")
    l4 = ("c4", "b", "r", "u", "q", "s")
    shared = {(x, y): len(set(x) & set(y)) for x, y in itertools.combinations((l1, l2, l3, l4), 2)}
    assert shared[(l1, l2)] == shared[(l3, l4)] == 2
    assert all(count == 3 for pair, count in shared.items() if pair not in {(l1, l2), (l3, l4)})
    assignments = {"e1": l1, "e2": l2, "e3": l3, "e4": l4}
    labels = {l1: "T1", l2: "T1", l3: "T2", l4: "T2"}
    labelled = _step(FOUR, assignments, labels)
    assert labelled.report["status"] == ca.STATUS_UNCHANGED and labelled.assignments == assignments
    assert _same_thesis_pairs(labelled.assignments, FOUR, labels) == 2

    rows = [ca.EntryRow(e, FOUR[e], r, ca.POOL_ALL) for e, r in assignments.items()]
    heavy = ca.diversify(rows, mode=ca.MODE_SHOWDOWN, people=ca.people_from_slate(_players(assignments.values())),
                         thesis_by_roster=labels, weights=ca.Weights(thesis=10), time_limit_seconds=None)
    assert _same_thesis_pairs(heavy.assignments, FOUR, labels) == 0


def test_the_claim_recomputes_with_the_labels_the_step_scored_with():
    assignments, labels = _four()
    labelled = _step(FOUR, assignments, labels)
    final = dict(labelled.assignments)
    findings, recomputed = labelled.claim.audit(final)
    assert findings == [] and recomputed == labelled.report["contests_after"]
    # The same claim without its labels no longer bears the reported figures out.
    unlabelled = dataclasses.replace(labelled.claim, thesis_by_roster=None)
    assert unlabelled.audit(final)[0] == ["CONTEST_ASSIGNMENT_STATS_MISMATCH"]


@pytest.mark.parametrize("with_labels", [True, False])
def test_the_review_block_reconciles_only_with_the_same_labels(with_labels):
    assignments, labels = _four()
    labelled = _step(FOUR, assignments, labels)
    rows = [(e, FOUR[e], tuple(r), ca.POOL_ALL) for e, r in labelled.assignments.items()]
    block, problems = ca.review_block(
        mode=ca.MODE_SHOWDOWN, people=ca.people_from_slate(_players(assignments.values())), rows=rows,
        selected_in_solver_order=list(assignments.values()), reported=labelled.report,
        thesis_by_roster=labels if with_labels else None)
    if with_labels:
        assert problems == [] and block["reported_statistics_match"] is True
        assert [row["distinct_theses"] for row in block["contests"]] == [2, 2]
    else:
        assert problems == ["CONTEST_ASSIGNMENT_STATS_MISMATCH"]


def test_thesis_labels_keys_by_roster_and_never_returns_an_empty_map():
    r1, r2 = ("a", "b"), ("c", "d")
    assert ca.thesis_labels(None, [(r1, "k1")]) is None
    assert ca.thesis_labels({}, [(r1, "k1")]) is None
    assert ca.thesis_labels({"k1": 5, "k2": None}, [(r1, "k1"), (r2, "k2")]) is None
    assert ca.thesis_labels({"k1": "T1"}, [(list(r1), "k1"), (r2, "k2")]) == {r1: "T1"}


# ------------------------------------------------------------------ the bridge in `prior_review`


@pytest.fixture(scope="module")
def policies(tmp_path_factory):
    root = tmp_path_factory.mktemp("s67-policies")
    slate, v4, *_rest = build_world(root / "v4", variants=False)
    _slate, v2, *_rest = build_world(root / "v2", variants=False, with_theses=False)
    one = r33_theses(slate, variants=False)[:1]
    _slate, v3, *_rest = build_world(root / "v3", variants=False, theses=one)
    assert (v4.thesis_schema, v3.thesis_schema) == ("v4", "v3") and v2.theses == ()
    return slate, {"v2": v2, "v3": v3, "v4": v4}


def _rosters(slate, count):
    flex = [p for p in slate.players if p.role == "FLEX"]
    captains = [p for p in slate.players if p.role == "CPT"]
    return [tuple([captains[index].dk_id, *(p.dk_id for p in flex[index * 5 + 1:index * 5 + 6])]) for index in range(count)]


def test_the_bridge_labels_exactly_the_rosters_a_v4_selection_names(policies):
    slate, by_schema = policies
    bound_a, bound_b, fill = _rosters(slate, 3)
    selection = {"portfolio_policy": {"theses": {"by_lineup": {
        roster_canonical_key(slate, bound_a): "NE_WINS_BIG", roster_canonical_key(slate, bound_b): "SEA_WINS_BIG"}}}}
    assignments = {"1": list(bound_a), "2": list(bound_b), "3": list(fill)}
    labels = prior_review._thesis_by_roster(selection, slate, by_schema["v4"], assignments)
    assert labels == {bound_a: "NE_WINS_BIG", bound_b: "SEA_WINS_BIG"}  # a fill row follows no thesis
    for schema in ("v2", "v3"):
        assert prior_review._thesis_by_roster(selection, slate, by_schema[schema], assignments) is None
    assert prior_review._thesis_by_roster(selection, slate, None, assignments) is None
    assert prior_review._thesis_by_roster(selection, slate, SimpleNamespace(thesis_schema="v4"), assignments) is None
    assert prior_review._thesis_by_roster({}, slate, by_schema["v4"], assignments) is None


# ------------------------------------------------------------------ end to end: the Session 23c run-slate fixture


@pytest.fixture(scope="module")
def labelled_run(tmp_path_factory):
    """One run of the 23c fixture (three theses, six rows, two interleaved contests), with every contest step also
    replayed over the same inputs without labels, so the two placements compare on identical inputs."""

    calls = []
    real = ca.apply_step

    def spy(**kwargs):
        unlabelled = real(**{**kwargs, "thesis_by_roster": None})
        outcome = real(**kwargs)
        calls.append((kwargs, outcome, unlabelled))
        return outcome

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(ca, "apply_step", spy)
        run = _finished(tmp_path_factory, "s67-th", policy_controls=_controls(4))
    policy_calls = [call for call in calls if call[0].get("bound_ids")]
    assert len(policy_calls) == 1, [sorted(call[0]) for call in calls]
    return run, policy_calls[0]


def test_the_engine_feeds_the_step_the_selection_s_labels_by_roster(labelled_run):
    run, (kwargs, _outcome, _unlabelled) = labelled_run
    labels = kwargs["thesis_by_roster"]
    claim = run.claim_by_roster()
    assert labels == claim and len(labels) == 6 and None not in labels.values()
    by_lineup = run.reports["selection"]["selection"]["portfolio_policy"]["theses"]["by_lineup"]
    assert {roster_canonical_key(run.slate, roster): thesis for roster, thesis in labels.items()} == by_lineup


def test_the_audit_and_the_review_recompute_the_labelled_figures_and_reconcile(labelled_run):
    run, (kwargs, outcome, unlabelled) = labelled_run
    _assert_truths_unchanged(run.report)
    labels = kwargs["thesis_by_roster"]
    step = run.reports["contest_assignment"]
    assert _without_seconds(step) == _without_seconds(outcome.report)
    assert step["status"] == ca.STATUS_IMPROVED and step["moved_rows"] > 0

    # The audit recomputed every figure from the delivered bytes with the step's labels, and they agree.
    reading = run.reports["portfolio_policy_audit"]["contest_assignment"]
    assert reading["status"] == "PASS" and reading["findings"] == []
    delivered = run.delivered()
    recomputed = ca.statistics_from_rosters(
        [(e, INTERLEAVED_CONTESTS[e], r) for e, r in delivered.items()], mode=ca.MODE_SHOWDOWN,
        people=ca.people_from_slate(run.slate.players), thesis_by_roster=labels)
    assert reading["contests"] == recomputed == step["contests_after"]

    # The readable review read the labels itself and reconciled with the step.
    readable = run.readable()
    block = readable["contest_assignment"]
    assert block["reported_statistics_match"] is True
    assert [row["distinct_theses"] for row in block["contests"]] == [3, 3]
    assert readable["reconciliation"]["status"] == "PASS"
    assert not any("READABLE_REVIEW" in item for item in run.report["blockers"])
    # No contest worse than the solver's order, scored with the labels (the step's own rule).
    assert all(Fraction(row["score_after"]) <= Fraction(row["score_before"]) for row in block["contests"])


def test_on_this_fixture_the_overlap_term_already_separates_the_theses(labelled_run, capsys):
    # Measured before any code (Session 67): on the 23c fixture the unlabelled step already puts one lineup of each
    # thesis in each contest, so the label changes no placement here; it changes the figures (the solver's order held
    # two same-thesis pairs, which now cost 3 each) and `distinct_theses`. The tie-built fixture above is where the
    # label alone decides. Vacuous here: no pair can share five people under overlap 4, and a contest of three holds at
    # most three theses.
    run, (kwargs, outcome, unlabelled) = labelled_run
    labels = kwargs["thesis_by_roster"]
    solver = {e: tuple(r) for e, r in kwargs["assignments"].items()}
    counts = {name: _same_thesis_pairs(assignment, INTERLEAVED_CONTESTS, labels)
              for name, assignment in (("solver", solver), ("unlabelled", unlabelled.assignments),
                                       ("labelled", outcome.assignments))}
    with capsys.disabled():
        print(f"\n[S67 23c fixture] same-thesis pairs {counts}; moved labelled {outcome.report['moved_rows']}, "
              f"unlabelled {unlabelled.report['moved_rows']}; total before labelled {outcome.report['total_score_before']},"
              f" unlabelled {unlabelled.report['total_score_before']}")
    assert counts == {"solver": 2, "unlabelled": 0, "labelled": 0}
    assert outcome.assignments == unlabelled.assignments
    assert outcome.report["moved_rows"] == unlabelled.report["moved_rows"] == 2
    assert float(outcome.report["total_score_before"]) > float(unlabelled.report["total_score_before"])
    assert outcome.report["total_score_after"] == unlabelled.report["total_score_after"]


def _doctored_review(run, label, mutate) -> str:
    with _doctored(run.artifacts["selection_report"], mutate) as digest:
        with pytest.raises(ReadableReviewError) as caught:
            run.review(label, hashes={**run.hashes, "selection_report": digest})
    return str(caught.value)


def test_a_doctored_lineup_label_is_named_by_the_contest_block_and_hides_the_thesis_section(labelled_run):
    # The review reads the contest labels from the hash-bound selection record's own lineups (roster and thesis).
    # Relabel every lineup to one thesis and rebind the hash: the contest block no longer reconciles with the step (a
    # `P` finding, the CSV kept). The Game theses section runs only when nothing else is wrong, so this review names
    # the contest mismatch alone.
    run, _call = labelled_run

    def one_thesis(record):
        for row in record["lineups"]:
            row["thesis"] = "NE_WIN_BIG"

    message = _doctored_review(run, "s67-doctored-lineups", one_thesis)
    assert "CONTEST_ASSIGNMENT_STATS_MISMATCH" in message
    assert "READABLE_REVIEW_THESIS_MISMATCH" not in message


def test_a_doctored_by_lineup_claim_stays_the_thesis_section_s_finding_alone(labelled_run):
    # The Game theses section (Session 23f) reads `theses.by_lineup`; the contest block does not, so a doctored
    # `by_lineup` is named once, by the section that reads it, and the contest block still reconciles.
    run, _call = labelled_run

    def swap(record):
        claim = record["selection"]["portfolio_policy"]["theses"]["by_lineup"]
        first = next(iter(claim))
        other = next(key for key, name in claim.items() if name != claim[first])
        claim[first], claim[other] = claim[other], claim[first]

    message = _doctored_review(run, "s67-doctored-by-lineup", swap)
    assert "READABLE_REVIEW_THESIS_MISMATCH" in message
    assert "CONTEST_ASSIGNMENT_STATS_MISMATCH" not in message
