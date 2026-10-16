"""Which entry holds which lineup, contest by contest (Session 50).

`prior_review` used to map lineups onto Entry IDs by position: the joint solvers
sort their selection by prior points and the sort was zipped onto template order,
sequential Showdown, C1 and the baseline kept solver order. Contest ID never
reached assignment, so a contest holding seven entries got whatever fell in its
rows. On PHI@CHI (2026-09-28) that was a worst pair of 5 shared people in three
seven-entry contests and one contest with the same Captain three times in seven.

This module changes only which entry holds which lineup. It is pure (standard
library, no I/O, no solver): the lineups that exist, their exposures and their
captain counts are the input's, and R29 (every lineup distinct) is untouched.

`contest_assignment_version = within_contest_diversity_v1`. Per contest, over
every pair of its lineups, a pair costs

    shared_people ** 2
    + 12 if both have the same key person (the Showdown Captain, the Classic QB)
    + 6  if both have the same Classic primary stack team
    + 3  if both carry the same thesis label (when labels exist)

The weights came from PHI@CHI: at 6 a seven-entry contest still repeated a
Captain, at 25 a two-entry contest paired two lineups of one thesis.

Labels (Session 67). Inside `run-slate` a lineup's label is the thesis a v4
portfolio's selection names for it (`theses.by_lineup`, canonical lineup to
thesis), held as `thesis_by_roster` keyed by the exact roster, so it follows the
lineup wherever the step moves it; every site that recomputes the step's figures
uses the same labels. Every other run has none and the term is zero. Against
shared people the label's 3 outweighs a pair going from 0 to 1 shared person
(cost 1), ties one going from 1 to 2 (cost 3, so nothing moves) and loses to
2 to 3 or more (cost 5 and up).

Contest size. A raw sum of pair costs lets a contest of seven entries (21 pairs)
outweigh one of two (1 pair): on PHI@CHI v4 the three seven-entry contests kept
one two-entry pair at three shared people. A contest's score is therefore its
worst pair cost plus its mean pair cost, and every contest counts once. The worst
pair is what an entrant reads in a contest; the mean stops the search ignoring
the other pairs. A contest with fewer than two entries scores 0. Contests are
grouped by Contest ID only: nothing here reads a contest name, an entry fee or a
field size, and a payout is never inferred.

Movement. A row the template already filled (or that a caller marks fixed) never
moves but its lineup counts in its contest's score. Movable rows carry a pool
label and only permute within their own pool: a policy's bound rows and the
fill rows are separate pools because the policy's caps and C3's row sources are
defined over each set.

Search. Deterministic. Cross-contest pairwise swaps in a fixed order from the
solver's order (a swap inside one contest cannot change any score), then seeded
random restarts, until `time_limit_seconds` runs out; a timeout keeps the best
found. The solver's order is always a candidate, so the result is never worse in
total, and with `no_regression` (the default) no contest scores worse than it
did in the solver's order. It never blocks: a caller that sees an exception
keeps the solver's order.

`within_contest_diversity_v2` (Session 76, R38: first place in each contest).
The entries in one contest are one set of shots at its first place, so two
lineups with the same Captain (Classic: QB) there are one shot spent twice. v2
compares placements lexicographically on a sum over contests of two or more
entries, in this order:

    (a) whether the contest holds a repeated key person (0 or 1: every contest counts once)
    (b) lost key people: the entries that repeat a key person the contest already holds
    (b') same-key-person pairs, so a forced repeat is spread evenly
    (c) same-thesis pairs (zero without labels)
    (d) the spread: worst plus mean of shared_people ** 2, plus 6 for the same Classic stack team

So a repeat ranks as the costliest difference, a repeated thesis next, and
shared people last. The search is v1's (seeded swaps and restarts inside a time
allowance): it avoids a repeat wherever it finds an arrangement without one and
does not prove that none exists; on the committed PHI@CHI and MIN@NO files it
reaches the exact floor. The four counts compare exactly (the search folds them
into one integer); EPSILON reaches only (d). Its score costs about 2.5 times
v1's on those files, at the same entry-sized restarts. Two choices differ from
v1 and are why it is a new version: a
one-entry contest's row may move (its own reading never changes, and the lineup
it takes can relieve a forced repeat elsewhere: MIN@NO's 20-entry contest went
from 15 same-Captain pairs to the floor's 14), and no contest is held to its
solver-order score, because that guard forbids exactly the trade v2 exists for
(on PHI@CHI v4 it moved nothing). v2 guarantees only that its total never rises
above the solver's order, which is always a candidate. The per-contest readings
(`contests_before`, `contests_after`) and `total_score_*` keep v1's definition
and weights under both versions, so every audit and reading recomputes them
unchanged; a v2 report carries its own objective beside them. The module default
stays v1 (the baseline's step); `prior_review` passes v2.

`does_not_establish`: this is a within-contest spread of the selected lineups by
shared people, Captain or QB, stack team and thesis. It is not expected value,
win probability, cash probability, ownership, duplication, a payout claim or a
statement about which contest is worth more.
"""

from __future__ import annotations

import functools
import itertools
import random
import time
from collections import Counter
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Callable, Mapping, Sequence

CONTEST_ASSIGNMENT_VERSION_V1 = "within_contest_diversity_v1"
CONTEST_ASSIGNMENT_VERSION_V2 = "within_contest_diversity_v2"
CONTEST_ASSIGNMENT_VERSIONS = (CONTEST_ASSIGNMENT_VERSION_V1, CONTEST_ASSIGNMENT_VERSION_V2)
# The module default, the baseline's step; `prior_review` passes v2 (Session 76).
CONTEST_ASSIGNMENT_VERSION = CONTEST_ASSIGNMENT_VERSION_V1
# The step's own record beside the Classic `assignments.csv` (Session 50c), without `seconds`.
CONTEST_ASSIGNMENT_ARTIFACT_VERSION = "nfl_contest_assignment_step_v1"
CONTEST_ASSIGNMENT_ARTIFACT_VERSION_V2 = "nfl_contest_assignment_step_v2"
ARTIFACT_VERSION_FOR = {
    CONTEST_ASSIGNMENT_VERSION_V1: CONTEST_ASSIGNMENT_ARTIFACT_VERSION,
    CONTEST_ASSIGNMENT_VERSION_V2: CONTEST_ASSIGNMENT_ARTIFACT_VERSION_V2,
}
CONTEST_OBJECTIVE_DEFINITION = "LEXICOGRAPHIC_SUM_OVER_CONTESTS_EVERY_CONTEST_COUNTS_ONCE"
OBJECTIVE_ORDER = (
    "contests_with_a_repeated_key_person",
    "lost_key_people",
    "same_key_person_pairs",
    "same_thesis_pairs",
    "spread",
)
READING_DEFINITION = "CONTESTS_AND_TOTAL_SCORE_ARE_WITHIN_CONTEST_DIVERSITY_V1_READINGS_NOT_THE_V2_OBJECTIVE"
DOES_NOT_ESTABLISH = (
    "EXPECTED_POINTS_OR_VALUE",
    "WIN_OR_CASH_LIKELIHOOD",
    "OWNERSHIP_OR_DUPLICATION",
    "PAYOUT_OR_CONTEST_WORTH",
    "UPLOAD_CLEARANCE",
)
CONTEST_SCORE_DEFINITION = "WORST_PAIR_COST_PLUS_MEAN_PAIR_COST_EVERY_CONTEST_COUNTS_ONCE"
KEY_PERSON_WEIGHT = 12
STACK_TEAM_WEIGHT = 6
THESIS_WEIGHT = 3


@dataclass(frozen=True)
class Weights:
    """The registered weights. `run-slate` always uses the defaults; the offline
    wrapper may override them and its record then says so."""

    key_person: int = KEY_PERSON_WEIGHT
    stack_team: int = STACK_TEAM_WEIGHT
    thesis: int = THESIS_WEIGHT

    @property
    def registered(self) -> bool:
        return self == Weights()


REGISTERED_WEIGHTS = Weights()
DEFAULT_SEED = 20260929
DEFAULT_RESTARTS = 300
EPSILON = 1e-9
RESTART_WORK_BUDGET = 25_000_000
DEFAULT_TIME_LIMIT_SECONDS = 20.0
MODE_SHOWDOWN = "SHOWDOWN"
MODE_CLASSIC = "CLASSIC"

POOL_ALL = "all"
POOL_BOUND = "bound"
POOL_FILL = "fill"

STATUS_FAILED = "FAILED"
STATUS_IMPROVED = "IMPROVED"
STATUS_UNCHANGED = "UNCHANGED"
STATUS_NOT_APPLICABLE = "NOT_APPLICABLE"


class ContestAssignmentError(ValueError):
    """A named refusal of the inputs; the caller keeps the solver's order."""


@dataclass(frozen=True)
class Person:
    """What the module needs to know about one DraftKings ID."""

    key: str                      # the person, identical across a Showdown CPT and FLEX ID
    team: str | None = None       # Classic stack team
    position: str | None = None   # Classic: "QB", "RB", "WR", "TE", "DST", ...


@dataclass(frozen=True)
class LineupFacts:
    people: frozenset[str]
    key_person: str | None
    stack_team: str | None
    thesis: str | None


@dataclass(frozen=True)
class Slot:
    """One entry. `pool` is None for a row that never moves."""

    entry_id: str
    contest_id: str
    pool: str | None


def primary_stack_team(roster: Sequence[str], people: Mapping[str, Person]) -> str | None:
    """The Classic team holding the most rostered offensive players.

    Offense is QB, RB, WR and TE (the FLEX is one of the last three, so a DST or
    kicker never counts). Ties go to the QB's team, then to the lower team
    abbreviation. A team with a single player is not a stack, so the result is
    None below two.
    """

    offense = [people[dk_id] for dk_id in roster if people[dk_id].position in {"QB", "RB", "WR", "TE"}]
    counts = Counter(person.team for person in offense if person.team)
    if not counts:
        return None
    qb_team = next((p.team for p in offense if p.position == "QB"), None)
    team, count = min(counts.items(), key=lambda item: (-item[1], item[0] != qb_team, item[0]))
    return team if count >= 2 else None


def lineup_facts(
    roster: Sequence[str],
    *,
    mode: str,
    people: Mapping[str, Person],
    thesis: str | None = None,
) -> LineupFacts:
    """A lineup's scored features. Showdown slot 0 is the Captain (DraftKings order)."""

    missing = [dk_id for dk_id in roster if dk_id not in people]
    if missing:
        raise ContestAssignmentError(f"CONTEST_ASSIGNMENT_UNKNOWN_DK_ID:{missing}")
    keys = frozenset(people[dk_id].key for dk_id in roster)
    if mode == MODE_SHOWDOWN:
        return LineupFacts(keys, people[roster[0]].key, None, thesis)
    if mode == MODE_CLASSIC:
        qb = next((people[dk_id].key for dk_id in roster if people[dk_id].position == "QB"), None)
        return LineupFacts(keys, qb, primary_stack_team(roster, people), thesis)
    raise ContestAssignmentError(f"CONTEST_ASSIGNMENT_UNKNOWN_MODE:{mode}")


def pair_cost(a: LineupFacts, b: LineupFacts, weights: Weights = REGISTERED_WEIGHTS) -> int:
    cost = len(a.people & b.people) ** 2
    if a.key_person is not None and a.key_person == b.key_person:
        cost += weights.key_person
    if a.stack_team is not None and a.stack_team == b.stack_team:
        cost += weights.stack_team
    if a.thesis is not None and a.thesis == b.thesis:
        cost += weights.thesis
    return cost


def contest_score(pair_costs: Sequence[int]) -> Fraction:
    """Worst pair plus mean pair, or 0 below one pair."""

    if not pair_costs:
        return Fraction(0)
    return Fraction(max(pair_costs)) + Fraction(sum(pair_costs), len(pair_costs))


def contest_statistics(placed: Sequence[LineupFacts], weights: Weights = REGISTERED_WEIGHTS) -> dict[str, object]:
    """One contest's readings over the lineups it holds, recomputed from scratch."""

    entries = len(placed)
    pairs = list(itertools.combinations(placed, 2))
    costs = [pair_cost(a, b, weights) for a, b in pairs]
    shared = [len(a.people & b.people) for a, b in pairs]
    score = contest_score(costs)
    return {
        "entries": entries,
        "pairs": len(pairs),
        "worst_pair_shared_people": max(shared) if shared else 0,
        "mean_shared_people": round(sum(shared) / len(shared), 3) if shared else 0.0,
        "distinct_key_people": len({facts.key_person for facts in placed if facts.key_person is not None}),
        "distinct_stack_teams": len({facts.stack_team for facts in placed if facts.stack_team is not None}),
        "distinct_theses": len({facts.thesis for facts in placed if facts.thesis is not None}),
        "people_in_every_lineup": sorted(frozenset.intersection(*(f.people for f in placed))) if placed else [],
        "worst_pair_cost": max(costs) if costs else 0,
        "score": _score_text(score),
    }


def spread_cost(a: LineupFacts, b: LineupFacts, weights: Weights = REGISTERED_WEIGHTS) -> int:
    """v2's pair cost for (d): v1's without the key-person and thesis terms, which v2 ranks above it."""

    cost = len(a.people & b.people) ** 2
    if a.stack_team is not None and a.stack_team == b.stack_team:
        cost += weights.stack_team
    return cost


def contest_objective(placed: Sequence[LineupFacts], weights: Weights = REGISTERED_WEIGHTS) -> dict[str, object]:
    """One contest's v2 objective over the lineups it holds, recomputed from scratch."""

    pairs = list(itertools.combinations(placed, 2))
    same_key = sum(1 for a, b in pairs if a.key_person is not None and a.key_person == b.key_person)
    keys = Counter(facts.key_person for facts in placed if facts.key_person is not None)
    return {
        "repeated_key_person": same_key > 0,
        "lost_key_people": sum(count - 1 for count in keys.values()),
        "same_key_person_pairs": same_key,
        "same_thesis_pairs": sum(1 for a, b in pairs if a.thesis is not None and a.thesis == b.thesis),
        "spread": _score_text(contest_score([spread_cost(a, b, weights) for a, b in pairs])),
    }


def objective_total(readings: Mapping[str, Mapping[str, object]]) -> dict[str, object]:
    """v2's total over the contests' recomputed objectives, the spread summed from their texts as v1's total is."""

    return {
        "contests_with_a_repeated_key_person": sum(1 for r in readings.values() if r["repeated_key_person"]),
        "lost_key_people": sum(int(r["lost_key_people"]) for r in readings.values()),
        "same_key_person_pairs": sum(int(r["same_key_person_pairs"]) for r in readings.values()),
        "same_thesis_pairs": sum(int(r["same_thesis_pairs"]) for r in readings.values()),
        "spread": f"{sum(float(r['spread']) for r in readings.values()):.6f}",
    }


def objective_improves(new: Sequence[float], old: Sequence[float]) -> bool:
    """v2's comparison on `OBJECTIVE_ORDER` tuples: the four counts exactly, in order, then the spread lower by more
    than EPSILON. The search compares the same order with the counts folded into one integer."""

    for level in range(4):
        if new[level] != old[level]:
            return new[level] < old[level]
    return new[4] < old[4] - EPSILON


def _exact_total_text(readings: Mapping[str, Mapping[str, object]]) -> str:
    """The total of the contests' exact scores, from the recomputed readings."""

    return f"{sum(float(reading['score']) for reading in readings.values()):.6f}"


def _score_text(score: Fraction) -> str:
    """A byte-stable rendering, rounded to six places."""

    return f"{float(score):.6f}"


def restarts_for(slots: Sequence[Slot]) -> int:
    """A deterministic restart count that shrinks as the work per restart grows.

    A restart costs about rows**2 * largest_contest**2, so 36 rows in contests of
    at most 7 get 300 restarts, 150 rows in contests of at most 5 get 44, and 150
    rows in contests of 50 get none (the single climb from the solver's order
    still runs). Sized from the entries, never from the clock, so a run that
    finishes inside its allowance replays byte for byte.
    """

    if not slots:
        return 0
    sizes = Counter(slot.contest_id for slot in slots)
    work = len(slots) ** 2 * max(2, max(sizes.values())) ** 2
    return max(0, min(DEFAULT_RESTARTS, RESTART_WORK_BUDGET // work))


def _contest_slots(slots: Sequence[Slot]) -> dict[str, list[int]]:
    by_contest: dict[str, list[int]] = {}
    for index, slot in enumerate(slots):
        by_contest.setdefault(slot.contest_id, []).append(index)
    return by_contest


@dataclass(frozen=True)
class AssignmentResult:
    """`order[k]` is the input lineup index placed at slot `k`."""

    order: tuple[int, ...]
    status: str
    before: Mapping[str, Mapping[str, object]]
    after: Mapping[str, Mapping[str, object]]
    total_before: str
    total_after: str
    restarts_run: int
    timed_out: bool
    seconds: float
    seed: int
    moved_slots: int
    weights: Weights = REGISTERED_WEIGHTS
    version: str = CONTEST_ASSIGNMENT_VERSION_V1
    # v2 only: each contest's objective (contests of two or more entries), and whether one-entry rows could move.
    objective_before: Mapping[str, Mapping[str, object]] = field(default_factory=dict)
    objective_after: Mapping[str, Mapping[str, object]] = field(default_factory=dict)
    single_entry_rows_move: bool = False

    def as_report(self) -> dict[str, object]:
        if self.version == CONTEST_ASSIGNMENT_VERSION_V2:
            return {
                "contest_assignment_version": self.version,
                "does_not_establish": list(DOES_NOT_ESTABLISH),
                "score_definition": CONTEST_OBJECTIVE_DEFINITION,
                "objective_order": list(OBJECTIVE_ORDER),
                "reading_definition": READING_DEFINITION,
                "weights": {
                    "shared_people_exponent": 2,
                    "same_stack_team": self.weights.stack_team,
                    "registered": self.weights.stack_team == STACK_TEAM_WEIGHT,
                },
                "status": self.status,
                "objective_before": objective_total(self.objective_before),
                "objective_after": objective_total(self.objective_after),
                "total_score_before": self.total_before,
                "total_score_after": self.total_after,
                "moved_rows": self.moved_slots,
                "single_entry_rows_move": self.single_entry_rows_move,
                "restarts_run": self.restarts_run,
                "timed_out": self.timed_out,
                "seed": self.seed,
                "seconds": round(self.seconds, 3),
            }
        return {
            "contest_assignment_version": CONTEST_ASSIGNMENT_VERSION,
            "does_not_establish": list(DOES_NOT_ESTABLISH),
            "score_definition": CONTEST_SCORE_DEFINITION,
            "weights": {
                "shared_people_exponent": 2,
                "same_key_person": self.weights.key_person,
                "same_stack_team": self.weights.stack_team,
                "same_thesis": self.weights.thesis,
                "registered": self.weights.registered,
            },
            "status": self.status,
            "total_score_before": self.total_before,
            "total_score_after": self.total_after,
            "moved_rows": self.moved_slots,
            "restarts_run": self.restarts_run,
            "timed_out": self.timed_out,
            "seed": self.seed,
            "seconds": round(self.seconds, 3),
        }


def assign_contests(
    slots: Sequence[Slot],
    lineups: Sequence[LineupFacts],
    *,
    seed: int = DEFAULT_SEED,
    restarts: int = DEFAULT_RESTARTS,
    time_limit_seconds: float | None = DEFAULT_TIME_LIMIT_SECONDS,
    no_regression: bool = True,
    weights: Weights = REGISTERED_WEIGHTS,
    clock: Callable[[], float] = time.monotonic,
    version: str = CONTEST_ASSIGNMENT_VERSION,
    move_single_entry_rows: bool | None = None,
) -> AssignmentResult:
    """Permute the movable lineups over the movable slots to lower every contest's score.

    `lineups[k]` is the lineup at slot `k` in the solver's order (a fixed slot's
    own lineup). Slots and lineups are the same length. `no_regression` is v1's
    per-contest guard; v2 has none. `move_single_entry_rows` None takes the
    version's own rule (v1 holds a one-entry contest's row, v2 moves it).
    """

    if version not in CONTEST_ASSIGNMENT_VERSIONS:
        raise ContestAssignmentError(f"CONTEST_ASSIGNMENT_UNKNOWN_VERSION:{version}")
    if len(slots) != len(lineups):
        raise ContestAssignmentError("CONTEST_ASSIGNMENT_SLOT_AND_LINEUP_COUNTS_DIFFER")
    v2 = version == CONTEST_ASSIGNMENT_VERSION_V2
    move_single = v2 if move_single_entry_rows is None else bool(move_single_entry_rows)
    started = clock()
    deadline = None if time_limit_seconds is None else started + max(0.0, time_limit_seconds)
    count = len(slots)
    # v2's counts, folded into one exact integer in their order: no count, summed over every contest, reaches `base`,
    # so the fold of a sum is the sum of the folds and one integer compare is the lexicographic compare.
    base = count * count + 1
    cost = [[0] * count for _ in range(count)]
    same = [[0] * count for _ in range(count)]   # v2: a same key person counts `base`, a same thesis 1
    for a, b in itertools.combinations(range(count), 2):
        cost[a][b] = cost[b][a] = (spread_cost if v2 else pair_cost)(lineups[a], lineups[b], weights)
        if v2:
            key_a, thesis_a = lineups[a].key_person, lineups[a].thesis
            same[a][b] = same[b][a] = (base * (key_a is not None and key_a == lineups[b].key_person)
                                       + (thesis_a is not None and thesis_a == lineups[b].thesis))
    # A lineup with no key person repeats no one: it gets its own placeholder, so a set of keys counts it once.
    key_of = [facts.key_person if facts.key_person is not None else ("NO_KEY", index)
              for index, facts in enumerate(lineups)]
    by_contest = _contest_slots(slots)
    contest_of = [slot.contest_id for slot in slots]

    pair_index = {
        contest: tuple(itertools.combinations(members, 2)) for contest, members in by_contest.items()
    }

    def score_v1(contest: str, placed: Sequence[int]) -> float:
        # Worst pair plus mean pair. Integers in, one float division out: the search
        # compares with EPSILON; the reported scores are recomputed exactly.
        costs = [cost[placed[i]][placed[j]] for i, j in pair_index[contest]]
        return (max(costs) + sum(costs) / len(costs)) if costs else 0.0

    zero_v2 = (0, 0.0)

    def score_v2(contest: str, placed: Sequence[int]) -> tuple:
        # (the folded counts, the spread). Only the spread is a float, compared with EPSILON.
        pairs = pair_index[contest]
        if not pairs:
            return zero_v2
        members = by_contest[contest]
        key_pairs, thesis_pairs = divmod(sum([same[placed[i]][placed[j]] for i, j in pairs]), base)
        lost = len(members) - len({key_of[placed[i]] for i in members})
        costs = [cost[placed[i]][placed[j]] for i, j in pairs]
        counts = ((((1 if key_pairs else 0) * base + lost) * base + key_pairs) * base) + thesis_pairs
        return (counts, max(costs) + sum(costs) / len(costs))

    if v2:
        score, zero = score_v2, zero_v2

        def improves(new, old):
            return new[0] < old[0] or (new[0] == old[0] and new[1] < old[1] - EPSILON)

        def worsens(new, old):
            return new[0] > old[0] or (new[0] == old[0] and new[1] > old[1] + EPSILON)

        def plus(left, right):
            return (left[0] + right[0], left[1] + right[1])
    else:
        score, zero = score_v1, 0

        def improves(new, old):
            return new < old - EPSILON

        def worsens(new, old):
            return new > old + EPSILON

        def plus(left, right):
            return left + right

    start = list(range(count))
    start_scores = {contest: score(contest, start) for contest in by_contest}
    pools: dict[str, list[int]] = {}
    for index, slot in enumerate(slots):
        # v1: a one-entry contest has no pair to spread, so its row stays where the solver put it.
        # v2: it moves, because the lineup it holds can relieve a repeat elsewhere.
        if slot.pool is not None and (move_single or len(by_contest[slot.contest_id]) > 1):
            pools.setdefault(slot.pool, []).append(index)
    swap_pairs = [
        (i, j)
        for members in pools.values()
        for i, j in itertools.combinations(members, 2)
        if contest_of[i] != contest_of[j]
    ]
    swap_pairs.sort()

    state = {"timed_out": False}

    def out_of_time() -> bool:
        if deadline is not None and clock() >= deadline:
            state["timed_out"] = True
        return state["timed_out"]

    # v1's per-contest guard; v2 has none (its total is still never worse than the solver's order).
    guard = no_regression and not v2

    def climb(placed: list[int], scores: dict, *, pareto: bool) -> None:
        improved = True
        while improved and not out_of_time():
            improved = False
            for i, j in swap_pairs:
                if out_of_time():
                    return
                ci, cj = contest_of[i], contest_of[j]
                before = plus(scores[ci], scores[cj])
                placed[i], placed[j] = placed[j], placed[i]
                new_i, new_j = score(ci, placed), score(cj, placed)
                better = improves(plus(new_i, new_j), before)
                if better and pareto and (worsens(new_i, scores[ci]) or worsens(new_j, scores[cj])):
                    better = False
                if better:
                    scores[ci], scores[cj] = new_i, new_j
                    improved = True
                else:
                    placed[i], placed[j] = placed[j], placed[i]

    def total(scores: Mapping[str, object]):
        return functools.reduce(plus, (scores[contest] for contest in sorted(scores)), zero)

    def admissible(scores: Mapping[str, object]) -> bool:
        if worsens(total(scores), total(start_scores)):
            return False
        return not guard or not any(worsens(scores[c], start_scores[c]) for c in scores)

    best, best_scores = list(start), dict(start_scores)
    restarts_run = 0
    if swap_pairs:
        # v1: a climb from the solver's order that never worsens either contest of a swap,
        # always admissible, so the result can only improve on the input. v2: a plain climb.
        placed, scores = list(start), dict(start_scores)
        climb(placed, scores, pareto=guard)
        if improves(total(scores), total(best_scores)):
            best, best_scores = placed, scores
        rng = random.Random(seed)
        movable_pools = list(pools.values())
        for _ in range(max(0, restarts)):
            if out_of_time():
                break
            placed = list(start)
            for members in movable_pools:
                order = list(members)
                rng.shuffle(order)
                for slot, lineup in zip(members, order):
                    placed[slot] = lineup
            scores = {contest: score(contest, placed) for contest in by_contest}
            climb(placed, scores, pareto=False)
            restarts_run += 1
            if admissible(scores) and improves(total(scores), total(best_scores)):
                best, best_scores = placed, scores

    moved = sum(1 for slot, lineup in enumerate(best) if lineup != slot)
    # The readings are v1's under both versions: v2 keeps v1's registered weights for them.
    reading_weights = REGISTERED_WEIGHTS if v2 else weights
    before = {
        contest: contest_statistics([lineups[k] for k in members], reading_weights)
        for contest, members in by_contest.items() if len(members) > 1
    }
    after = {
        contest: contest_statistics([lineups[best[k]] for k in members], reading_weights)
        for contest, members in by_contest.items() if len(members) > 1
    }
    def objectives(order: Sequence[int]) -> dict[str, dict[str, object]]:
        return {
            contest: contest_objective([lineups[order[k]] for k in members], weights)
            for contest, members in by_contest.items() if len(members) > 1
        }

    objective_before, objective_after = (objectives(start), objectives(best)) if v2 else ({}, {})
    status = (
        STATUS_NOT_APPLICABLE if not swap_pairs
        else STATUS_IMPROVED if improves(total(best_scores), total(start_scores))
        else STATUS_UNCHANGED
    )
    return AssignmentResult(
        order=tuple(best),
        status=status,
        before=before,
        after=after,
        total_before=_exact_total_text(before),
        total_after=_exact_total_text(after),
        restarts_run=restarts_run,
        timed_out=state["timed_out"],
        seconds=clock() - started,
        seed=seed,
        moved_slots=moved,
        weights=weights,
        version=version,
        objective_before=objective_before,
        objective_after=objective_after,
        single_entry_rows_move=move_single,
    )


# --- entry-level API: the call sites, the wrapper script and the audits ------------


@dataclass(frozen=True)
class EntryRow:
    """One entry as the call sites hold it.

    `roster` is the solver's lineup for a movable row and the filled roster of a
    fixed row; None for a fixed row that does not resolve to a roster (it is not
    scored). `pool` is None for a row that never moves.
    """

    entry_id: str
    contest_id: str
    roster: tuple[str, ...] | None
    pool: str | None


@dataclass(frozen=True)
class Diversification:
    assignments: Mapping[str, tuple[str, ...]]   # movable entry_id -> roster, in row order
    result: AssignmentResult
    report: Mapping[str, object]


def _thesis(thesis_by_roster: Mapping[tuple[str, ...], str] | None, roster: tuple[str, ...]) -> str | None:
    return None if not thesis_by_roster else thesis_by_roster.get(tuple(roster))


def thesis_labels(
    by_lineup: object,
    keyed_rosters: Sequence[tuple[Sequence[str], str]],
) -> dict[tuple[str, ...], str] | None:
    """Each roster's thesis label from a selection's `by_lineup` (canonical lineup to thesis), keyed by the roster.

    `keyed_rosters` pairs each roster with its canonical key, computed by the caller (`prior_review`, from the exact
    salary IDs). A roster whose key names no thesis carries none, and a map with no label at all is None, never `{}`,
    so a run without theses reaches the step exactly as before.
    """

    if not isinstance(by_lineup, Mapping):
        return None
    labels = {
        tuple(roster): by_lineup[key] for roster, key in keyed_rosters if isinstance(by_lineup.get(key), str)
    }
    return labels or None


def diversify(
    rows: Sequence[EntryRow],
    *,
    mode: str,
    people: Mapping[str, Person],
    thesis_by_roster: Mapping[tuple[str, ...], str] | None = None,
    seed: int = DEFAULT_SEED,
    restarts: int | None = None,
    time_limit_seconds: float | None = DEFAULT_TIME_LIMIT_SECONDS,
    no_regression: bool = True,
    weights: Weights = REGISTERED_WEIGHTS,
    clock: Callable[[], float] = time.monotonic,
    version: str = CONTEST_ASSIGNMENT_VERSION,
    move_single_entry_rows: bool | None = None,
) -> Diversification:
    """The permuted assignment of every movable row, with the step's own report.

    A v2 report adds each contest's objective before and after and the one-entry contests whose lineup changed.
    """

    entry_ids = [row.entry_id for row in rows]
    if len(set(entry_ids)) != len(entry_ids):
        raise ContestAssignmentError("CONTEST_ASSIGNMENT_DUPLICATE_ENTRY_ID")
    scored = [row for row in rows if row.roster is not None]
    if any(row.roster is None and row.pool is not None for row in rows):
        raise ContestAssignmentError("CONTEST_ASSIGNMENT_MOVABLE_ROW_HAS_NO_ROSTER")
    slots = [Slot(row.entry_id, row.contest_id, row.pool) for row in scored]
    facts = [
        lineup_facts(row.roster, mode=mode, people=people, thesis=_thesis(thesis_by_roster, row.roster))
        for row in scored
    ]
    result = assign_contests(
        slots, facts, seed=seed, restarts=restarts_for(slots) if restarts is None else restarts,
        time_limit_seconds=time_limit_seconds, no_regression=no_regression, weights=weights,
        clock=clock, version=version, move_single_entry_rows=move_single_entry_rows)
    assignments = {
        row.entry_id: scored[result.order[index]].roster
        for index, row in enumerate(scored) if row.pool is not None
    }
    contests = {row.contest_id for row in rows}
    report = dict(result.as_report())
    report.update({
        "fixed_entry_ids": [row.entry_id for row in rows if row.pool is None],
        "unscored_entry_ids": [row.entry_id for row in rows if row.roster is None],
        "pools": {pool: sum(1 for r in rows if r.pool == pool) for pool in sorted({r.pool for r in rows if r.pool})},
        "contest_count": len(contests),
        "single_entry_contest_count": len(contests) - len(result.after),
        "contests_before": dict(sorted(result.before.items())),
        "contests_after": dict(sorted(result.after.items())),
    })
    if version == CONTEST_ASSIGNMENT_VERSION_V2:
        sizes = Counter(slot.contest_id for slot in slots)
        report.update({
            "contest_objective_before": dict(sorted(result.objective_before.items())),
            "contest_objective_after": dict(sorted(result.objective_after.items())),
            "single_entry_contests_moved": sorted(
                slot.contest_id for index, slot in enumerate(slots)
                if sizes[slot.contest_id] == 1 and result.order[index] != index),
        })
    return Diversification(assignments, result, report)


def statistics_from_rosters(
    entries: Sequence[tuple[str, str, tuple[str, ...]]],
    *,
    mode: str,
    people: Mapping[str, Person],
    thesis_by_roster: Mapping[tuple[str, ...], str] | None = None,
) -> dict[str, dict[str, object]]:
    """Per-contest readings from `(entry_id, contest_id, roster)` triples, for contests of 2+."""

    by_contest: dict[str, list[LineupFacts]] = {}
    for _entry_id, contest_id, roster in entries:
        by_contest.setdefault(contest_id, []).append(
            lineup_facts(roster, mode=mode, people=people, thesis=_thesis(thesis_by_roster, roster)))
    return {
        contest: contest_statistics(placed)
        for contest, placed in sorted(by_contest.items()) if len(placed) > 1
    }


def objectives_from_rosters(
    entries: Sequence[tuple[str, str, tuple[str, ...]]],
    *,
    mode: str,
    people: Mapping[str, Person],
    thesis_by_roster: Mapping[tuple[str, ...], str] | None = None,
) -> dict[str, dict[str, object]]:
    """Per-contest v2 objectives from `(entry_id, contest_id, roster)` triples, for contests of 2+."""

    by_contest: dict[str, list[LineupFacts]] = {}
    for _entry_id, contest_id, roster in entries:
        by_contest.setdefault(contest_id, []).append(
            lineup_facts(roster, mode=mode, people=people, thesis=_thesis(thesis_by_roster, roster)))
    return {
        contest: contest_objective(placed)
        for contest, placed in sorted(by_contest.items()) if len(placed) > 1
    }


def audit_contest_assignment(
    final: Mapping[str, tuple[str, ...]],
    *,
    rows: Sequence[EntryRow],
    selected_by_pool: Mapping[str, Sequence[tuple[str, ...]]],
    mode: str,
    people: Mapping[str, Person],
    thesis_by_roster: Mapping[tuple[str, ...], str] | None = None,
    reported_after: Mapping[str, Mapping[str, object]] | None = None,
    version: str = CONTEST_ASSIGNMENT_VERSION,
    reported_objective_after: Mapping[str, Mapping[str, object]] | None = None,
) -> tuple[list[str], dict[str, dict[str, object]]]:
    """Recompute the step's claims from the final assignment bytes.

    `final` maps each Entry ID the file holds a roster for (every movable row, and
    optionally the fixed rows) to that roster, read from the file's bytes.
    `rows` gives every entry's contest and pool, and each fixed row's roster as the
    template holds it. `selected_by_pool` is what selection produced. Returns the
    problems and the recomputed per-contest readings; the optimizer's own numbers
    are compared, never trusted. A v2 step's per-contest objective is recomputed
    and compared too.

    Problem codes: CONTEST_ASSIGNMENT_MULTISET_CHANGED (V),
    CONTEST_ASSIGNMENT_FIXED_ROW_MOVED (V), CONTEST_ASSIGNMENT_STATS_MISMATCH (P).
    """

    problems: list[str] = []
    movable = {row.entry_id: row for row in rows if row.pool is not None}
    known = {row.entry_id for row in rows}
    if not set(movable) <= set(final) or not set(final) <= known:
        problems.append("CONTEST_ASSIGNMENT_MULTISET_CHANGED:entry_ids")
    for pool in sorted({row.pool for row in movable.values()}):
        held = Counter(tuple(final[row.entry_id]) for row in movable.values()
                       if row.pool == pool and row.entry_id in final)
        wanted = Counter(tuple(roster) for roster in selected_by_pool.get(pool, ()))
        if held != wanted:
            problems.append(f"CONTEST_ASSIGNMENT_MULTISET_CHANGED:{pool}")
    for row in rows:
        if row.pool is None and row.roster is not None:
            if row.entry_id in final and tuple(final[row.entry_id]) != tuple(row.roster):
                problems.append(f"CONTEST_ASSIGNMENT_FIXED_ROW_MOVED:{row.entry_id}")
    placed: list[tuple[str, str, tuple[str, ...]]] = []
    for row in rows:
        roster = final.get(row.entry_id) if row.pool is not None else row.roster
        if roster is not None:
            placed.append((row.entry_id, row.contest_id, tuple(roster)))
    try:
        recomputed = statistics_from_rosters(
            placed, mode=mode, people=people, thesis_by_roster=thesis_by_roster)
        objectives = objectives_from_rosters(
            placed, mode=mode, people=people, thesis_by_roster=thesis_by_roster
        ) if version == CONTEST_ASSIGNMENT_VERSION_V2 and reported_objective_after is not None else None
    except ContestAssignmentError as exc:
        return problems + [str(exc)], {}
    if (
        (reported_after is not None and {k: dict(v) for k, v in reported_after.items()} != recomputed)
        or (objectives is not None and {k: dict(v) for k, v in reported_objective_after.items()} != objectives)
    ):
        problems.append("CONTEST_ASSIGNMENT_STATS_MISMATCH")
    return problems, recomputed


# --- the run-slate glue: one step, fail-safe, and the claim an audit rechecks --------


def people_from_slate(players) -> dict[str, Person]:
    """`Person` for every DraftKings ID on the slate (duck-typed on `SalaryPlayer`)."""

    return {p.dk_id: Person(key=p.underlying_id, team=p.team, position=p.position) for p in players}


def pool_by_entry(entry_ids: Sequence[str], bound_ids: Sequence[str]) -> dict[str, str]:
    """`bound` for a policy's rows, `fill` for the rest; `all` when no policy binds any."""

    if not bound_ids:
        return {entry_id: POOL_ALL for entry_id in entry_ids}
    bound = set(bound_ids)
    return {entry_id: POOL_BOUND if entry_id in bound else POOL_FILL for entry_id in entry_ids}


def plan_rows(entry_plan, assignments: Mapping[str, Sequence[str]], pool_of: Mapping[str, str]) -> list[EntryRow]:
    """Every template row in order: movable where `assignments` fills it, else fixed.

    A row the template filled resolves to its roster when `entry_plan.prefilled`
    reads it against the slate; a row it cannot resolve, or one left blank that
    no producer may fill, has no roster and is not scored.
    """

    contest_of = {entry_id: group.contest_id for group in entry_plan.groups for entry_id in group.entry_ids}
    rows: list[EntryRow] = []
    for entry_id in entry_plan.order:
        contest = contest_of.get(entry_id, "")
        if entry_id in assignments:
            rows.append(EntryRow(entry_id, contest, tuple(assignments[entry_id]), pool_of[entry_id]))
            continue
        prefilled = entry_plan.prefilled.get(entry_id)
        roster = tuple(prefilled.roster) if prefilled is not None and prefilled.resolved else None
        rows.append(EntryRow(entry_id, contest, roster, None))
    return rows


@dataclass(frozen=True)
class Claim:
    """What an audit needs to recompute the step's claims from the assignment bytes."""

    rows: tuple[EntryRow, ...]
    selected_by_pool: Mapping[str, tuple[tuple[str, ...], ...]]
    mode: str
    people: Mapping[str, Person]
    thesis_by_roster: Mapping[tuple[str, ...], str] | None = None
    reported_after: Mapping[str, Mapping[str, object]] | None = None
    version: str = CONTEST_ASSIGNMENT_VERSION
    reported_objective_after: Mapping[str, Mapping[str, object]] | None = None

    def audit(self, final: Mapping[str, tuple[str, ...]]) -> tuple[list[str], dict[str, dict[str, object]]]:
        return audit_contest_assignment(
            final, rows=self.rows, selected_by_pool=self.selected_by_pool, mode=self.mode,
            people=self.people, thesis_by_roster=self.thesis_by_roster, reported_after=self.reported_after,
            version=self.version, reported_objective_after=self.reported_objective_after)


@dataclass(frozen=True)
class StepOutcome:
    assignments: dict[str, tuple[str, ...]]
    report: dict[str, object]
    claim: Claim | None
    failure: str | None      # a named reason the solver's order stands (a P-class limitation)


def apply_step(
    *,
    mode: str,
    players,
    entry_plan,
    assignments: Mapping[str, Sequence[str]],
    bound_ids: Sequence[str] = (),
    thesis_by_roster: Mapping[tuple[str, ...], str] | None = None,
    time_limit_seconds: float | None = DEFAULT_TIME_LIMIT_SECONDS,
    seed: int = DEFAULT_SEED,
    restarts: int | None = None,
    clock: Callable[[], float] = time.monotonic,
    version: str = CONTEST_ASSIGNMENT_VERSION,
) -> StepOutcome:
    """Diversify `assignments` (fillable entry -> roster, solver order), never raising.

    `restarts` None sizes the restarts from the entries (`restarts_for`); the
    baseline passes 0, the single climb from its own order. `thesis_by_roster`
    (Session 67) labels each roster with its thesis; the claim carries the same
    labels so the audit recomputes with them. None (or empty) is no label.
    `version` (Session 76) is v1 by default, the baseline's; `prior_review`
    passes v2, and the claim carries it so the audit recomputes v2's objective.

    Any failure leaves the solver's order standing and names it, so the file still
    ships (R28): the caller carries `failure` as a P-class limitation.
    """

    original = {entry_id: tuple(roster) for entry_id, roster in assignments.items()}
    try:
        people = people_from_slate(players)
        pool_of = pool_by_entry(list(original), bound_ids)
        rows = plan_rows(entry_plan, original, pool_of)
        selected: dict[str, list[tuple[str, ...]]] = {}
        for entry_id, roster in original.items():
            selected.setdefault(pool_of[entry_id], []).append(roster)
        labels = {tuple(roster): thesis for roster, thesis in thesis_by_roster.items()} if thesis_by_roster else None
        outcome = diversify(rows, mode=mode, people=people, thesis_by_roster=labels,
                            time_limit_seconds=time_limit_seconds, seed=seed, restarts=restarts, clock=clock,
                            version=version)
        # Key order is the template's, exactly as it came in: only the values move.
        permuted = {entry_id: outcome.assignments[entry_id] for entry_id in original}
        claim = Claim(
            rows=tuple(rows),
            selected_by_pool={pool: tuple(rosters) for pool, rosters in selected.items()},
            mode=mode, people=people, thesis_by_roster=labels, reported_after=outcome.report["contests_after"],
            version=version, reported_objective_after=outcome.report.get("contest_objective_after"))
        return StepOutcome(permuted, dict(outcome.report), claim, None)
    except Exception as exc:  # noqa: BLE001 - named, never swallowed: the solver's order stands
        problems: list[str] = []
        problems.append(f"CONTEST_ASSIGNMENT_STEP_FAILED:{type(exc).__name__}:{exc}")
        return StepOutcome(dict(original), {
            "contest_assignment_version": version,
            "does_not_establish": list(DOES_NOT_ESTABLISH),
            "status": STATUS_FAILED,
            "error": problems[0],
        }, None, problems[0])


def relabel_overlaps(entry_ids: Sequence[str], assignments: Mapping[str, Sequence[str]],
                     people: Mapping[str, Person]) -> list[dict[str, object]]:
    """The selector's pairwise-overlap list, relabelled to the entries that now hold the lineups."""

    held = {entry_id: frozenset(people[dk_id].key for dk_id in assignments[entry_id]) for entry_id in entry_ids}
    return [
        {"entry_id_a": left, "entry_id_b": right, "people": len(held[left] & held[right])}
        for index, left in enumerate(entry_ids) for right in entry_ids[index + 1:]
    ]


# --- the review block: recomputed from the exported bytes, then reconciled -----------

REVIEW_BASIS = "RECOMPUTED_FROM_THE_EXPORTED_ROSTERS_AND_THE_SELECTION_ORDER"


def _total(readings: Mapping[str, Mapping[str, object]]) -> str:
    return _exact_total_text(readings)


def review_block(
    *,
    mode: str,
    people: Mapping[str, Person],
    rows: Sequence[tuple[str, str, tuple[str, ...], str | None]],
    selected_in_solver_order: Sequence[tuple[str, ...]],
    reported: Mapping[str, object] | None,
    thesis_by_roster: Mapping[tuple[str, ...], str] | None = None,
) -> tuple[dict[str, object] | None, list[str]]:
    """The per-contest review block, and the problems reconciling it found.

    `rows` are `(entry_id, contest_id, roster, pool)` for every template row that
    resolves to a roster, read from the delivered file's bytes (`pool` None for a
    row the template filled). `selected_in_solver_order` is the selection's own
    lineup order (bound pool first, then fill). Both the after and the before
    readings are recomputed here; `reported` (the step's own report) is only
    compared to them. `thesis_by_roster` is the caller's own reading of the
    labels (Session 67), keyed by roster, so both readings carry them. Returns
    `(None, [])` for a record from before Session 50. A v2 record (Session 76)
    also has its objective recomputed before and after, and reconciled.
    """

    if not isinstance(reported, Mapping):
        return None, []
    version = reported.get("contest_assignment_version")
    v2 = version == CONTEST_ASSIGNMENT_VERSION_V2
    problems: list[str] = []
    movable = [row for row in rows if row[3] is not None]
    ordered = [row for pool in (POOL_BOUND, POOL_FILL, POOL_ALL) for row in movable if row[3] == pool]
    delivered = [(e, c, r) for e, c, r, _pool in rows]
    after = statistics_from_rosters(delivered, mode=mode, people=people, thesis_by_roster=thesis_by_roster)
    before = after
    in_solver_order = delivered
    # Sequential Showdown may select more lineups than there are entries; the
    # entries take the first N, exactly as the assignment does.
    selected = list(selected_in_solver_order)[: len(ordered)]
    if len(ordered) != len(selected):
        problems.append("CONTEST_ASSIGNMENT_MULTISET_CHANGED:selection_count")
    else:
        if Counter(row[2] for row in movable) != Counter(tuple(r) for r in selected):
            problems.append("CONTEST_ASSIGNMENT_MULTISET_CHANGED:delivered_rosters")
        solver_order = {row[0]: tuple(roster) for row, roster in zip(ordered, selected)}
        in_solver_order = [(e, c, solver_order.get(e, r)) for e, c, r, _pool in rows]
        before = statistics_from_rosters(in_solver_order, mode=mode, people=people, thesis_by_roster=thesis_by_roster)
    objective_after = objective_before = {}
    single_moved: list[str] = []
    if v2:
        objective_after = objectives_from_rosters(
            delivered, mode=mode, people=people, thesis_by_roster=thesis_by_roster)
        objective_before = objectives_from_rosters(
            in_solver_order, mode=mode, people=people, thesis_by_roster=thesis_by_roster)
        sizes = Counter(contest for _e, contest, _r in delivered)
        solver_roster = {entry_id: tuple(roster) for entry_id, _c, roster in in_solver_order}
        single_moved = sorted(contest for entry_id, contest, roster in delivered
                              if sizes[contest] == 1 and tuple(roster) != solver_roster[entry_id])
    failed = reported.get("status") == STATUS_FAILED
    if not failed and (
        {k: dict(v) for k, v in (reported.get("contests_after") or {}).items()} != after
        or {k: dict(v) for k, v in (reported.get("contests_before") or {}).items()} != before
        or (v2 and (
            {k: dict(v) for k, v in (reported.get("contest_objective_after") or {}).items()} != objective_after
            or {k: dict(v) for k, v in (reported.get("contest_objective_before") or {}).items()} != objective_before
            or list(reported.get("single_entry_contests_moved") or []) != single_moved))
    ):
        problems.append("CONTEST_ASSIGNMENT_STATS_MISMATCH")
    contests = []
    for contest in sorted(after):
        now, was = after[contest], before.get(contest, after[contest])
        contests.append({
            "contest_id": contest,
            "entries": now["entries"],
            "worst_pair_shared_people": now["worst_pair_shared_people"],
            "worst_pair_shared_people_before": was["worst_pair_shared_people"],
            "mean_shared_people": now["mean_shared_people"],
            "mean_shared_people_before": was["mean_shared_people"],
            "distinct_key_people": now["distinct_key_people"],
            "distinct_key_people_before": was["distinct_key_people"],
            "distinct_stack_teams": now["distinct_stack_teams"],
            "distinct_theses": now["distinct_theses"],
            "people_in_every_lineup": now["people_in_every_lineup"],
            "score_before": was["score"],
            "score_after": now["score"],
        })
        if v2:
            goal, held = objective_after[contest], objective_before.get(contest, objective_after[contest])
            contests[-1].update({
                f"{name}{suffix}": reading[name]
                for name in ("lost_key_people", "same_key_person_pairs", "same_thesis_pairs", "spread")
                for suffix, reading in (("", goal), ("_before", held))
            })
    contest_ids = {row[1] for row in rows}
    block = {
        "contest_assignment_version": CONTEST_ASSIGNMENT_VERSION if not v2 else version,
        "does_not_establish": list(DOES_NOT_ESTABLISH),
        "score_definition": CONTEST_SCORE_DEFINITION,
        "basis": REVIEW_BASIS,
        "status": reported.get("status"),
        "key_person": "CAPTAIN" if mode == MODE_SHOWDOWN else "QUARTERBACK",
        "moved_rows": reported.get("moved_rows"),
        "timed_out": reported.get("timed_out"),
        "restarts_run": reported.get("restarts_run"),
        "seed": reported.get("seed"),
        "error": reported.get("error"),
        "total_score_before": _total(before),
        "total_score_after": _total(after),
        "single_entry_contest_count": len(contest_ids) - len(after),
        "reported_statistics_match": "CONTEST_ASSIGNMENT_STATS_MISMATCH" not in problems,
        "contests": contests,
    }
    if v2:
        block.update({
            "score_definition": CONTEST_OBJECTIVE_DEFINITION,
            "objective_order": list(OBJECTIVE_ORDER),
            "reading_definition": READING_DEFINITION,
            "objective_before": objective_total(objective_before),
            "objective_after": objective_total(objective_after),
            "single_entry_rows_move": reported.get("single_entry_rows_move"),
            "single_entry_contests_moved": single_moved,
        })
    return block, problems
