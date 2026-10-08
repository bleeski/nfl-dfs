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
uses the same labels. Every other run has none and the term is zero. The label
breaks ties: going from 2 to 3 shared people costs 5, more than its 3.

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

`does_not_establish`: this is a within-contest spread of the selected lineups by
shared people, Captain or QB, stack team and thesis. It is not expected value,
win probability, cash probability, ownership, duplication, a payout claim or a
statement about which contest is worth more.
"""

from __future__ import annotations

import itertools
import random
import time
from collections import Counter
from dataclasses import dataclass
from fractions import Fraction
from typing import Callable, Mapping, Sequence

CONTEST_ASSIGNMENT_VERSION = "within_contest_diversity_v1"
# The step's own record beside the Classic `assignments.csv` (Session 50c), without `seconds`.
CONTEST_ASSIGNMENT_ARTIFACT_VERSION = "nfl_contest_assignment_step_v1"
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

    def as_report(self) -> dict[str, object]:
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
) -> AssignmentResult:
    """Permute the movable lineups over the movable slots to lower every contest's score.

    `lineups[k]` is the lineup at slot `k` in the solver's order (a fixed slot's
    own lineup). Slots and lineups are the same length.
    """

    if len(slots) != len(lineups):
        raise ContestAssignmentError("CONTEST_ASSIGNMENT_SLOT_AND_LINEUP_COUNTS_DIFFER")
    started = clock()
    deadline = None if time_limit_seconds is None else started + max(0.0, time_limit_seconds)
    count = len(slots)
    cost = [[0] * count for _ in range(count)]
    for a, b in itertools.combinations(range(count), 2):
        cost[a][b] = cost[b][a] = pair_cost(lineups[a], lineups[b], weights)
    by_contest = _contest_slots(slots)
    contest_of = [slot.contest_id for slot in slots]

    pair_index = {
        contest: tuple(itertools.combinations(members, 2)) for contest, members in by_contest.items()
    }

    def score(contest: str, placed: Sequence[int]) -> float:
        # Worst pair plus mean pair. Integers in, one float division out: the search
        # compares with EPSILON; the reported scores are recomputed exactly.
        costs = [cost[placed[i]][placed[j]] for i, j in pair_index[contest]]
        return (max(costs) + sum(costs) / len(costs)) if costs else 0.0

    start = list(range(count))
    start_scores = {contest: score(contest, start) for contest in by_contest}
    pools: dict[str, list[int]] = {}
    for index, slot in enumerate(slots):
        # A one-entry contest has no pair to spread: its row stays where the solver put it.
        if slot.pool is not None and len(by_contest[slot.contest_id]) > 1:
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

    def climb(placed: list[int], scores: dict[str, float], *, pareto: bool) -> None:
        improved = True
        while improved and not out_of_time():
            improved = False
            for i, j in swap_pairs:
                if out_of_time():
                    return
                ci, cj = contest_of[i], contest_of[j]
                before = scores[ci] + scores[cj]
                placed[i], placed[j] = placed[j], placed[i]
                new_i, new_j = score(ci, placed), score(cj, placed)
                better = new_i + new_j < before - EPSILON
                if better and pareto and (new_i > scores[ci] + EPSILON or new_j > scores[cj] + EPSILON):
                    better = False
                if better:
                    scores[ci], scores[cj] = new_i, new_j
                    improved = True
                else:
                    placed[i], placed[j] = placed[j], placed[i]

    def total(scores: Mapping[str, float]) -> float:
        return sum(scores[contest] for contest in sorted(scores))

    def admissible(scores: Mapping[str, float]) -> bool:
        if total(scores) > total(start_scores) + EPSILON:
            return False
        return not no_regression or all(scores[c] <= start_scores[c] + EPSILON for c in scores)

    best, best_scores = list(start), dict(start_scores)
    restarts_run = 0
    if swap_pairs:
        # A climb from the solver's order that never worsens either contest of a swap:
        # always admissible, so the result can only improve on the input.
        placed, scores = list(start), dict(start_scores)
        climb(placed, scores, pareto=no_regression)
        if total(scores) < total(best_scores) - EPSILON:
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
            if admissible(scores) and total(scores) < total(best_scores) - EPSILON:
                best, best_scores = placed, scores

    moved = sum(1 for slot, lineup in enumerate(best) if lineup != slot)
    before = {
        contest: contest_statistics([lineups[k] for k in members], weights)
        for contest, members in by_contest.items() if len(members) > 1
    }
    after = {
        contest: contest_statistics([lineups[best[k]] for k in members], weights)
        for contest, members in by_contest.items() if len(members) > 1
    }
    status = (
        STATUS_NOT_APPLICABLE if not swap_pairs
        else STATUS_IMPROVED if total(best_scores) < total(start_scores) - EPSILON
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
) -> Diversification:
    """The permuted assignment of every movable row, with the step's own report."""

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
        clock=clock)
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


def audit_contest_assignment(
    final: Mapping[str, tuple[str, ...]],
    *,
    rows: Sequence[EntryRow],
    selected_by_pool: Mapping[str, Sequence[tuple[str, ...]]],
    mode: str,
    people: Mapping[str, Person],
    thesis_by_roster: Mapping[tuple[str, ...], str] | None = None,
    reported_after: Mapping[str, Mapping[str, object]] | None = None,
) -> tuple[list[str], dict[str, dict[str, object]]]:
    """Recompute the step's claims from the final assignment bytes.

    `final` maps each Entry ID the file holds a roster for (every movable row, and
    optionally the fixed rows) to that roster, read from the file's bytes.
    `rows` gives every entry's contest and pool, and each fixed row's roster as the
    template holds it. `selected_by_pool` is what selection produced. Returns the
    problems and the recomputed per-contest readings; the optimizer's own numbers
    are compared, never trusted.

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
    except ContestAssignmentError as exc:
        return problems + [str(exc)], {}
    if reported_after is not None and {k: dict(v) for k, v in reported_after.items()} != recomputed:
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

    def audit(self, final: Mapping[str, tuple[str, ...]]) -> tuple[list[str], dict[str, dict[str, object]]]:
        return audit_contest_assignment(
            final, rows=self.rows, selected_by_pool=self.selected_by_pool, mode=self.mode,
            people=self.people, thesis_by_roster=self.thesis_by_roster, reported_after=self.reported_after)


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
) -> StepOutcome:
    """Diversify `assignments` (fillable entry -> roster, solver order), never raising.

    `restarts` None sizes the restarts from the entries (`restarts_for`); the
    baseline passes 0, the single climb from its own order. `thesis_by_roster`
    (Session 67) labels each roster with its thesis; the claim carries the same
    labels so the audit recomputes with them. None (or empty) is no label.

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
                            time_limit_seconds=time_limit_seconds, seed=seed, restarts=restarts, clock=clock)
        # Key order is the template's, exactly as it came in: only the values move.
        permuted = {entry_id: outcome.assignments[entry_id] for entry_id in original}
        claim = Claim(
            rows=tuple(rows),
            selected_by_pool={pool: tuple(rosters) for pool, rosters in selected.items()},
            mode=mode, people=people, thesis_by_roster=labels, reported_after=outcome.report["contests_after"])
        return StepOutcome(permuted, dict(outcome.report), claim, None)
    except Exception as exc:  # noqa: BLE001 - named, never swallowed: the solver's order stands
        problems: list[str] = []
        problems.append(f"CONTEST_ASSIGNMENT_STEP_FAILED:{type(exc).__name__}:{exc}")
        return StepOutcome(dict(original), {
            "contest_assignment_version": CONTEST_ASSIGNMENT_VERSION,
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
    `(None, [])` for a record from before Session 50.
    """

    if not isinstance(reported, Mapping):
        return None, []
    problems: list[str] = []
    movable = [row for row in rows if row[3] is not None]
    ordered = [row for pool in (POOL_BOUND, POOL_FILL, POOL_ALL) for row in movable if row[3] == pool]
    after = statistics_from_rosters(
        [(e, c, r) for e, c, r, _pool in rows], mode=mode, people=people, thesis_by_roster=thesis_by_roster)
    before = after
    # Sequential Showdown may select more lineups than there are entries; the
    # entries take the first N, exactly as the assignment does.
    selected = list(selected_in_solver_order)[: len(ordered)]
    if len(ordered) != len(selected):
        problems.append("CONTEST_ASSIGNMENT_MULTISET_CHANGED:selection_count")
    else:
        if Counter(row[2] for row in movable) != Counter(tuple(r) for r in selected):
            problems.append("CONTEST_ASSIGNMENT_MULTISET_CHANGED:delivered_rosters")
        solver_order = {row[0]: tuple(roster) for row, roster in zip(ordered, selected)}
        before = statistics_from_rosters(
            [(e, c, solver_order.get(e, r)) for e, c, r, _pool in rows], mode=mode, people=people,
            thesis_by_roster=thesis_by_roster)
    failed = reported.get("status") == STATUS_FAILED
    if not failed and (
        {k: dict(v) for k, v in (reported.get("contests_after") or {}).items()} != after
        or {k: dict(v) for k, v in (reported.get("contests_before") or {}).items()} != before
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
    contest_ids = {row[1] for row in rows}
    return {
        "contest_assignment_version": CONTEST_ASSIGNMENT_VERSION,
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
    }, problems
