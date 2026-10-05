"""Classic rung 4 as several constructions under one exposure cap (Session 49).

Rung 4 of the relaxation ladder is "no policy", which used to mean C1: one
construction (`_sequential_lineups`), repeated, each row the best legal lineup
the previous rows left. On the 2026-09-27 Week 3 slate that file held three
people in 25 of 25 lineups and no stack. `scripts/build_thesis_portfolio.py`
solves this at the operator layer with several named theses selected together
under one global cap; it needs an operator-written config and slate-context
totals and shells out to another builder, so the engine does not call it. This
module ports its shape onto the engine's own pieces:

- **Theses.** One per primary stack team: the QB comes from that team, with a
  teammate WR/TE and a bring-back from the opponent. The teams are ranked by a
  stack value read from the run's own prior objective (best QB, two best WR/TE,
  best opponent skill player), the best team of each game first. The thesis
  axis is the run's own prior, never a number written by hand.
- **One global cap.** No person is in more than `max_person_share` of the rows
  (40% by default), enforced as a zero bound on a person the moment they reach
  the cap, in every thesis model.
- **Round robin.** Row k goes to the next live thesis. Every row is one solve of
  that thesis's model with every earlier row cut as an exact roster and capped
  by `CLASSIC_PERSON_OVERLAP` shared people (Session 39), and every prefilled
  roster cut exactly (R29).

Construction preferences relax on this module's authority, each step reported
and never silent: a thesis proved infeasible drops its bring-back, then the one
overlap cap (shared by every thesis) steps up a person at a time, then the
thesis is dropped; when every thesis is gone the person share cap steps up ten
points at a time; past `STACK_HOLD_SHARE` the stack requirement goes (a free
thesis takes the rest), and the share keeps stepping to 100%.
Distinct lineups (R29) are never relaxed: a run that cannot build row k returns
the k rows it has, `stopped` names why, and nothing is repeated. With no row at
all it raises `SOLVER_RETURNED_NO_LINEUP`, as C1 does.

`classic_thesis_sequential_v1` does not establish that any thesis is a better
bet than another, that a stacked lineup is worth more, or that the cap improves
any payout: the ranking is the prior's central estimate and the structure is a
construction preference.

Protected placements (Session 61, R37; `classic_thesis_sequential_v2`, used only when a
validated construction judgment names someone). A named person must sit in at least
`minimum` of the rows. The schedule owes him a row whenever his count falls behind
`ceil(index * minimum / count)` or the rows left equal what he still needs; a row that owes
someone is solved on a throwaway model of the chosen thesis with his DraftKings row required,
trying the theses that share his game first. A forced attempt that fails changes nothing shared:
the thesis keeps its bring-back, no thesis is dropped and the one overlap cap stays where it was
(an urgent debt may try a looser cap for that one row alone, and says so); the row is then built
as it always was and the debt carries to the next row. His person cap is `max(cap, minimum)`.
A minimum the rows could not hold is reported as a shortfall by name and never closed by
repeating a lineup (R29). The delivered rosters are recounted, not trusted. The attempts are
budgeted (`PLACEMENT_SOLVES_PER_ROW`, `PLACEMENT_MISS_LIMIT`, `PLACEMENT_TIME_SHARE`): a person no
thesis could hold is abandoned by name, so a preference that cannot be met never costs the file its rows.
"""

from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable, Mapping, Sequence

from .contracts import SlateContract
from .lineups import validate_lineup
from .optimizer import LineupOptimizer, SolverResult

THESIS_CONSTRUCTION_VERSION = "classic_thesis_sequential_v1"
THESIS_CONSTRUCTION_VERSION_V2 = "classic_thesis_sequential_v2"
DEFAULT_PERSON_SHARE = 0.40
SHARE_STEP = 0.10
# Past this share the stack requirement goes before the cap moves further: a stacked file at
# 60% is still several constructions, a file at 100% with stacks is the 2026-09-27 file.
STACK_HOLD_SHARE = 0.60
MIN_THESES = 4
ROWS_PER_EXTRA_THESIS = 15
# A forced placement is a construction preference, so it gives way before the clock does: at most this many
# throwaway solves a row, a person is given up on after this many rows no thesis could hold him, and all
# forced solves together may spend this share of the build's window. Each forced solve also runs under a
# quarter of the per-row solve limit. The shortfall is named; nothing is repeated to close it (R29).
PLACEMENT_SOLVES_PER_ROW = 8
PLACEMENT_MISS_LIMIT = 3
PLACEMENT_TIME_SHARE = 0.25
FREE_THESIS = "FREE_NO_STACK"
DOES_NOT_ESTABLISH = (
    "THAT_ANY_THESIS_IS_A_BETTER_BET_THAN_ANOTHER",
    "THAT_A_STACKED_LINEUP_IS_WORTH_MORE",
    "ANY_EXPECTED_VALUE_PAYOUT_OR_WIN_PROBABILITY",
    "THAT_THE_EXPOSURE_CAP_IMPROVES_ANY_OUTCOME",
)
PLACEMENT_DOES_NOT_ESTABLISH = (
    "THAT_A_PROTECTED_PERSON_IS_PLAYING_OR_HAS_THE_ROLE_THE_JUDGMENT_NAMES",
    "A_CURRENT_ROLE_OR_ANY_NUMBER_FOR_HIM",
    "THAT_PLACING_HIM_RAISES_ANY_PAYOUT",
)


class _OutOfTime(Exception):
    """The run's window (`time_limit x (rows + 1)`) is spent; the rows built so far are the result."""


@dataclass
class _Thesis:
    name: str
    team: str | None  # the primary stack team; None is the free thesis
    rank: int
    value: float
    share: float = DEFAULT_PERSON_SHARE  # the person share the thesis was built under
    stack: bool = True
    bringback: bool = True
    qb_people: frozenset[str] = frozenset()  # the people whose QB rows the thesis may use
    optimizer: LineupOptimizer | None = None
    synced_rows: int = 0
    synced_capped: frozenset[str] = frozenset()
    rows: list[int] = field(default_factory=list)
    drops: list[dict[str, object]] = field(default_factory=list)

    def report(self) -> dict[str, object]:
        return {"name": self.name, "team": self.team, "rank": self.rank,
                "stack_value": round(self.value, 6), "person_share": round(self.share, 4),
                "rows": list(self.rows), "bringback_required": self.bringback,
                "drops": [dict(item) for item in self.drops]}


def person_cap(count: int, share: float) -> int:
    """Rows one person may be in: `share` of `count`, rounded down, never under one."""

    return max(1, int(count * share + 1e-9))


def thesis_count(eligible: int, count: int) -> int:
    return min(eligible, max(MIN_THESES, count // ROWS_PER_EXTRA_THESIS + 3))


def rank_stack_teams(slate: SlateContract, objective: Mapping[str, float],
                     excluded: Sequence[str]) -> list[tuple[str, float, str]]:
    """`(team, value, game_id)` best first: QB, two best WR/TE and best opponent skill player.

    Read only from the prior objective over the rows the run has not excluded, so
    an unavailable person never moves a rank. A team with no QB or no WR/TE left
    cannot carry a stack thesis and is left out. Ties break on the team code.
    """

    blocked = set(map(str, excluded))
    live = [row for row in slate.players if row.dk_id not in blocked]

    def best(rows, n):
        return sorted((float(objective.get(row.dk_id, 0.0)) for row in rows), reverse=True)[:n]

    ranked = []
    for team in sorted({row.team for row in live}):
        qbs = [row for row in live if row.team == team and row.position == "QB"]
        catchers = [row for row in live if row.team == team and row.position in {"WR", "TE"}]
        if not qbs or not catchers:
            continue
        opponent = qbs[0].opponent
        skill = [row for row in live if row.team == opponent and row.position in {"RB", "WR", "TE"}]
        value = sum(best(qbs, 1)) + sum(best(catchers, 2)) + sum(best(skill, 1))
        ranked.append((team, value, qbs[0].game_id))
    return sorted(ranked, key=lambda item: (-item[1], item[0]))


def _choose_teams(ranked: Sequence[tuple[str, float, str]], wanted: int) -> list[tuple[str, float, str]]:
    """The best team of each game first, then the second team of a game, best first."""

    firsts: list[tuple[str, float, str]] = []
    seconds: list[tuple[str, float, str]] = []
    games: set[str] = set()
    for item in ranked:
        (seconds if item[2] in games else firsts).append(item)
        games.add(item[2])
    return sorted([*firsts, *seconds][:wanted], key=lambda item: (-item[1], item[0]))


def _stacked(slate_rows: Mapping[str, object], roster: Sequence[str]) -> bool:
    qb = next((slate_rows[dk_id] for dk_id in roster if slate_rows[dk_id].position == "QB"), None)
    return qb is not None and any(
        slate_rows[dk_id].team == qb.team and slate_rows[dk_id].position in {"WR", "TE"} for dk_id in roster)


def _bringback(slate_rows: Mapping[str, object], roster: Sequence[str]) -> bool:
    qb = next((slate_rows[dk_id] for dk_id in roster if slate_rows[dk_id].position == "QB"), None)
    return qb is not None and any(
        slate_rows[dk_id].team == qb.opponent and slate_rows[dk_id].position in {"RB", "WR", "TE"}
        for dk_id in roster)


def select_thesis_lineups(
    slate: SlateContract,
    objective: Mapping[str, float],
    excluded: Sequence[str],
    contract,
    *,
    count: int,
    forbidden_rosters: Sequence[tuple[str, ...]] = (),
    time_limit_seconds: float = 10.0,
    classic_person_overlap: int | None,
    max_person_share: float = DEFAULT_PERSON_SHARE,
    protected: Mapping[str, int] | None = None,
    clock: Callable[[], float] = time.monotonic,
):
    """`count` distinct Classic lineups from several stack theses under one person cap.

    `classic_person_overlap` is the most people a row may share with an earlier one
    (`None`: exact rosters only), required so the caller's default is the only one.

    `protected` (Session 61) is `{person: minimum rows}` for the people a validated construction
    judgment names; the module docstring says how they are placed. Empty or `None`: v1, as before.

    Returns the `_Sequential` run the C1 path returns, with `.construction` (the
    report block). Fewer than `count` rows come back with `.stopped` set; none at
    all raises `SOLVER_RETURNED_NO_LINEUP`.
    """

    from .selection import (  # the selector imports this module, so these come late
        CLASSIC_MAX_USEFUL_OVERLAP,
        SelectedLineup,
        SelectionError,
        _Sequential,
    )

    excluded = tuple(sorted(set(map(str, excluded))))
    blocked = set(excluded)
    rows = {player.dk_id: player for player in slate.players}
    by_person: dict[str, list[str]] = {}
    for player in slate.players:
        by_person.setdefault(player.underlying_id, []).append(player.dk_id)
    forbidden = tuple(tuple(map(str, roster)) for roster in forbidden_rosters)
    started = clock()
    window = time_limit_seconds * (count + 1)

    def binds(cap: int | None) -> bool:
        return cap is not None and cap < CLASSIC_MAX_USEFUL_OVERLAP

    asked = {person: int(minimum) for person, minimum in sorted(dict(protected or {}).items()) if int(minimum) > 0}
    # A person the builder cannot place at all is named, never dropped silently: the caller refuses
    # these before it gets here, so this is the backstop.
    ignored = {person: "NOT_IN_THE_SLATE" if person not in by_person else "EXCLUDED_ROW"
               for person in asked if person not in by_person or set(by_person[person]) & blocked}
    protected_min = {person: min(minimum, count) for person, minimum in asked.items() if person not in ignored}
    ranked = rank_stack_teams(slate, objective, excluded)
    chosen = _choose_teams(ranked, thesis_count(len(ranked), count))
    # A protected quarterback needs his own team's thesis: every row of a thesis has that team's QB.
    protected_qb_teams = {rows[by_person[person][0]].team for person in protected_min
                          if rows[by_person[person][0]].position == "QB"}
    have = {team for team, _value, _game in chosen}
    chosen = sorted([*chosen, *(item for item in ranked if item[0] in protected_qb_teams and item[0] not in have)],
                    key=lambda item: (-item[1], item[0]))
    share = float(max_person_share)
    theses = [
        _Thesis(f"STACK_{team}", team, rank, value, share=share, qb_people=frozenset(
            row.underlying_id for row in slate.players
            if row.team == team and row.position == "QB" and row.dk_id not in blocked))
        for rank, (team, value, _game) in enumerate(chosen, start=1)
    ]
    history: list[_Thesis] = list(theses)
    stack_required = True
    overlap = classic_person_overlap  # one cap for every thesis: a step rebuilds them all
    selected: list[SelectedLineup] = []
    tags: list[str] = []
    row_caps: list[int | None] = []
    exposure: Counter[str] = Counter()
    capped: set[str] = set()
    steps: list[dict[str, object]] = []  # overlap steps, in the shape C1 reports them
    relaxations: list[dict[str, object]] = []
    stopped: dict[str, object] | None = None
    last_status = "NO_SOLUTION"
    cursor = 0

    def free_thesis() -> _Thesis:
        item = _Thesis(FREE_THESIS, None, 0, 0.0, share=share, stack=False, bringback=False)
        history.append(item)
        return item

    if not theses:
        stack_required = False
        relaxations.append({"constraint": "classic_qb_stack", "from": True, "used": False, "index": 1,
                            "thesis": "ALL", "trigger_status": "NO_STACK_TEAM",
                            "reason": "NO_TEAM_HAS_A_LIVE_QB_AND_A_LIVE_WR_OR_TE"})
        theses = [free_thesis()]
    active = list(theses)

    def cap_now() -> int:
        return person_cap(count, share)

    def limit_for(person: str) -> int:
        """Rows `person` may be in: the shared cap, or his own minimum when that is more (Session 61)."""

        return max(cap_now(), protected_min.get(person, 0))

    def relax(constraint: str, original: object, final: object, *, index: int, thesis: str, status: str,
              cause: str) -> None:
        relaxations.append({"constraint": constraint, "from": original, "used": final, "index": index,
                            "thesis": thesis, "trigger_status": status, "reason": cause})

    def new_model(thesis: _Thesis, *, cap: int | None, require: Sequence[str] = (),
                  limit: float | None = None) -> LineupOptimizer:
        """A model of `thesis` under every row built so far, with `cap` as the overlap cap and `require` pinned."""

        model = LineupOptimizer(slate, excluded_ids=excluded,
                                time_limit_seconds=time_limit_seconds if limit is None else limit)
        for roster in forbidden:
            model.add_no_good(roster)
        if thesis.team is not None:
            qb_rows = [p.dk_id for p in slate.players
                       if p.team == thesis.team and p.position == "QB" and p.dk_id not in blocked]
            model.add_selected_count_bounds(qb_rows, minimum=1, maximum=1)
            if thesis.stack:
                model.add_classic_qb_correlation_bounds(kind="PASS_CATCHER", minimum=1, maximum=7)
            if thesis.bringback:
                model.add_classic_qb_correlation_bounds(kind="BRINGBACK", minimum=1, maximum=7)
        for earlier in selected:
            model.add_no_good(earlier.roster)
            if binds(cap):
                model.add_person_overlap_limit(earlier.roster, cap)
        held = sorted(dk_id for person in capped for dk_id in by_person[person])
        if held:
            model.add_selected_count_bounds(held, maximum=0)
        for dk_id in require:
            model.add_required_row(dk_id)
        return model

    def build(thesis: _Thesis) -> None:
        thesis.optimizer = new_model(thesis, cap=overlap)
        thesis.synced_rows = len(selected)
        thesis.synced_capped = frozenset(capped)

    def sync(thesis: _Thesis) -> None:
        if thesis.optimizer is None:
            build(thesis)
            return
        for earlier in selected[thesis.synced_rows:]:
            thesis.optimizer.add_no_good(earlier.roster)
            if binds(overlap):
                thesis.optimizer.add_person_overlap_limit(earlier.roster, overlap)
        thesis.synced_rows = len(selected)
        fresh = sorted(dk_id for person in capped - set(thesis.synced_capped) for dk_id in by_person[person])
        if fresh:
            thesis.optimizer.add_selected_count_bounds(fresh, maximum=0)
        thesis.synced_capped = frozenset(capped)

    def solve_row(thesis: _Thesis, index: int) -> SolverResult | None:
        """One row from `thesis`, relaxing its own preferences first; None drops the thesis."""

        nonlocal last_status, overlap
        while True:
            if clock() - started > window:
                raise _OutOfTime
            if thesis.team is not None and thesis.qb_people <= capped:
                # Every QB the thesis may use is at the person cap: the wall is the cap, not a
                # bring-back or the overlap, so none of them is relaxed for it.
                last_status = "PERSON_CAP_REACHED"
                thesis.drops.append({"index": index, "status": last_status, "proved": True, "share": share})
                return None
            sync(thesis)
            result = thesis.optimizer.solve(objective)
            last_status = result.status
            if result.roster is not None:
                return result
            if result.status != "INFEASIBLE":
                thesis.drops.append({"index": index, "status": result.status, "proved": False, "share": share})
                return None
            if thesis.bringback and thesis.team is not None:
                thesis.bringback = False
                relax("classic_bringback", True, False, index=index, thesis=thesis.name,
                      status=result.status, cause="NO_DISTINCT_STACKED_LINEUP_WITH_A_BRINGBACK")
                thesis.optimizer = None
                continue
            if binds(overlap) and selected:
                before, overlap = overlap, overlap + 1
                steps.append({"index": index, "requested": classic_person_overlap, "from": before,
                              "used": overlap, "trigger_status": result.status, "thesis": thesis.name,
                              "scope": "THESES",
                              "reason": "NO_DISTINCT_LINEUP_UNDER_THE_REQUESTED_OVERLAP_CAP"})
                for other in (*active, thesis):
                    other.optimizer = None  # every model holds the cap it was built under
                continue
            thesis.drops.append({"index": index, "status": result.status, "proved": True, "share": share})
            return None

    def next_level(index: int) -> bool:
        """Relax one more construction preference once every thesis is gone; False ends the run."""

        nonlocal share, stack_required, theses, active, cursor
        if stack_required and share + 1e-9 < STACK_HOLD_SHARE:
            before, share = share, min(1.0, share + SHARE_STEP)
            relax("classic_person_share", round(before, 4), round(share, 4), index=index, thesis="ALL",
                  status=last_status, cause="NO_THESIS_HAS_A_DISTINCT_LINEUP_LEFT_UNDER_THE_PERSON_SHARE_CAP")
        elif stack_required:
            stack_required = False
            relax("classic_qb_stack", True, False, index=index, thesis="ALL", status=last_status,
                  cause="NO_STACK_THESIS_HAS_A_DISTINCT_LINEUP_LEFT_AT_THE_HELD_PERSON_SHARE_CAP")
            theses = [free_thesis()]
        elif share + 1e-9 < 1.0:
            before, share = share, min(1.0, share + SHARE_STEP)
            relax("classic_person_share", round(before, 4), round(share, 4), index=index, thesis="ALL",
                  status=last_status, cause="THE_FREE_THESIS_HAS_NO_DISTINCT_LINEUP_LEFT_UNDER_THE_PERSON_SHARE_CAP")
        else:
            return False
        # The cap moved, so who is at it moves too; the models restart from these.
        capped.clear()
        capped.update(person for person, rows_held in exposure.items() if rows_held >= limit_for(person))
        for item in theses:
            item.optimizer, item.share = None, share
        active, cursor = list(theses), 0
        return True

    forced_rows: dict[int, list[str]] = {}  # row index -> the protected people its row was solved to hold
    misses: list[dict[str, object]] = []  # a row that owed someone and could not hold him, for the report
    miss_count: Counter[str] = Counter()  # rows in a row that no thesis could hold him
    abandoned: dict[str, str] = {}  # given up on, by name, so the preference never costs the file its rows
    forced_seconds = 0.0  # what every forced solve together has spent of the window

    def due_people(index: int) -> list[str]:
        """The protected people the schedule owes this row, most urgent first.

        Owed when his count is behind `ceil(index * minimum / count)` or the rows left are no more
        than he still needs. Urgency is need over rows left; ties break on the person ID.
        """

        rows_left = count - index + 1
        owed: list[tuple[float, str]] = []
        for person, minimum in protected_min.items():
            need = minimum - exposure[person]
            if person not in abandoned and need > 0 and (exposure[person] < -(-index * minimum // count) or need >= rows_left):
                owed.append((-(need / rows_left), person))
        return [person for _urgency, person in sorted(owed)]

    def place(index: int, owed: Sequence[str]):
        """`(thesis, position, result, people, cap, trigger_status)` for a row that holds what the schedule owes, or None.

        Every attempt is a throwaway model: nothing here sets `overlap`, a thesis's bring-back or
        `active`, so a failed attempt leaves the shared relaxations exactly where they were. An urgent
        debt (the rows left equal what he still needs) may try a looser overlap cap for this row only.
        """

        nonlocal forced_seconds
        rows_left = count - index + 1
        solves = 0
        failed = "INFEASIBLE"
        for size in range(len(owed), 0, -1):
            targets = list(owed[:size])
            target_rows = [by_person[person][0] for person in targets]
            qb_teams = {rows[dk_id].team for dk_id in target_rows if rows[dk_id].position == "QB"}
            if len(qb_teams) > 1:
                continue
            lead = rows[target_rows[0]]
            urgent = any(protected_min[person] - exposure[person] >= rows_left for person in targets)
            loosest = CLASSIC_MAX_USEFUL_OVERLAP
            caps = [overlap, *(range(overlap + 1, loosest + 1) if urgent and binds(overlap) else ())]

            def affinity(thesis: _Thesis) -> int:
                if thesis.team is None:
                    return 2
                return 0 if thesis.team == lead.team else 1 if thesis.team == lead.opponent else 2

            order = sorted(range(len(active)),
                           key=lambda at: (affinity(active[at]), (at - cursor) % len(active)))
            for at in order:
                thesis = active[at]
                if qb_teams and thesis.team is not None and thesis.team not in qb_teams:
                    continue
                if thesis.team is not None and thesis.qb_people <= capped:
                    continue
                for cap in caps:
                    if clock() - started > window:
                        raise _OutOfTime
                    if solves >= PLACEMENT_SOLVES_PER_ROW:
                        return None
                    if forced_seconds > PLACEMENT_TIME_SHARE * window:
                        for person in protected_min:
                            if person not in abandoned and exposure[person] < protected_min[person]:
                                abandoned[person] = "THE_PLACEMENT_TIME_SHARE_OF_THE_WINDOW_IS_SPENT"
                        return None
                    solves += 1
                    before = clock()
                    result = new_model(thesis, cap=cap, require=target_rows,
                                       limit=max(0.5, time_limit_seconds / 4)).solve(objective)
                    forced_seconds += max(0.0, clock() - before)
                    if result.roster is not None:
                        return thesis, at, result, targets, cap, failed
                    failed = result.status
        return None

    def commit(thesis: _Thesis, index: int, result: SolverResult, cap: int | None) -> None:
        roster = tuple(result.roster)
        validation = validate_lineup(slate, roster)
        if validation.lineup is None:
            raise SelectionError(f"SOLVER_PRODUCED_ILLEGAL_LINEUP:index={index}:{validation.errors}")
        if set(roster) & blocked:
            raise SelectionError(f"SOLVER_SELECTED_AN_EXCLUDED_ROW:index={index}:{sorted(set(roster) & blocked)}")
        selected.append(SelectedLineup(
            index=index, roster=roster, captain_dk_id="", salary=validation.lineup.salary,
            prior_points=sum(objective[dk_id] for dk_id in roster), canonical_key=validation.lineup.canonical_key,
            solver_status=result.status, solver_seconds=result.elapsed_seconds))
        tags.append(thesis.name)
        row_caps.append(cap)
        thesis.rows.append(index)
        people = {rows[dk_id].underlying_id for dk_id in roster}
        exposure.update(people)
        capped.update(person for person in people if exposure[person] >= limit_for(person))

    while len(selected) < count:
        index = len(selected) + 1
        if clock() - started > window:
            stopped = {"index": index, "status": "TIME_BUDGET", "proved_exhausted": False}
            break
        if not active:
            if not next_level(index):
                stopped = {"index": index, "status": last_status, "proved_exhausted": last_status == "INFEASIBLE"}
                break
            continue
        owed = due_people(index) if protected_min else []
        if owed:
            try:
                placed = place(index, owed)
            except _OutOfTime:
                stopped = {"index": index, "status": "TIME_BUDGET", "proved_exhausted": False}
                break
            if placed is not None:
                thesis, at, result, targets, cap, tripped = placed
                if cap != overlap:
                    relax("classic_placement_overlap", overlap, cap, index=index, thesis=thesis.name,
                          status=tripped, cause="THE_PROTECTED_PLACEMENT_HAD_NO_DISTINCT_ROW_UNDER_THE_OVERLAP_CAP")
                commit(thesis, index, result, cap)
                forced_rows[index] = list(targets)
                for person in targets:
                    miss_count[person] = 0
                cursor = at + 1
                continue
            misses.append({"index": index, "people": list(owed), "reason": "NO_THESIS_HAD_A_DISTINCT_ROW_HOLDING_THEM"})
            for person in owed:
                miss_count[person] += 1
                if miss_count[person] >= PLACEMENT_MISS_LIMIT and person not in abandoned:
                    abandoned[person] = f"NO_THESIS_COULD_HOLD_HIM_IN_{PLACEMENT_MISS_LIMIT}_ROWS_IN_A_ROW"
        thesis = active[cursor % len(active)]
        try:
            result = solve_row(thesis, index)
        except _OutOfTime:
            stopped = {"index": index, "status": "TIME_BUDGET", "proved_exhausted": False}
            break
        if result is None:
            dropped = thesis.drops[-1]
            if len(thesis.drops) == 1:  # later drops of the same thesis stay in `drops`, not the record
                relax("classic_thesis", thesis.name, "DROPPED", index=index, thesis=thesis.name,
                      status=str(dropped["status"]),
                      cause="NO_DISTINCT_LINEUP_LEFT_FOR_THE_THESIS" if dropped["proved"]
                      else "THE_THESIS_SOLVE_ENDED_WITHOUT_A_LINEUP_AND_WITHOUT_A_PROOF")
            position = active.index(thesis)
            active.remove(thesis)
            cursor = position  # the next live thesis now sits at this position
            continue
        commit(thesis, index, result, overlap)
        cursor += 1

    if not selected:
        raise SelectionError(
            f"SOLVER_RETURNED_NO_LINEUP:index=1:status={last_status}"
            f":selectable_people={len(contract.selectable_people)}",
            status="SOLVER_RETURNED_NO_LINEUP",
            facts={"stage": "THESIS_SEQUENTIAL", "index": 1, "selected": 0, "requested": count,
                   "selectable_people": len(contract.selectable_people)},
        )

    # The backstop, recomputed from the rosters alone: distinct (R29), no excluded row, every row
    # under the overlap cap it was solved under, nobody above the held person share, every
    # lineup stacked while the stack requirement held.
    keys = [lineup.canonical_key for lineup in selected]
    if len(set(keys)) != len(keys):
        raise SelectionError("DUPLICATE_LINEUP_SELECTED")
    people_by_row = [{rows[dk_id].underlying_id for dk_id in lineup.roster} for lineup in selected]
    for later, cap in enumerate(row_caps):
        if not binds(cap):
            continue
        for earlier in range(later):
            shared = len(people_by_row[earlier] & people_by_row[later])
            if shared > cap:
                raise SelectionError(f"OVERLAP_LIMIT_BREACHED:{earlier + 1}v{later + 1}:{shared}>{cap}")
    final_cap = cap_now()
    totals = Counter(person for people in people_by_row for person in people)
    top_person, top_count = max(totals.items(), key=lambda item: (item[1], item[0]))
    over = [(rows_held, person) for person, rows_held in totals.items() if rows_held > limit_for(person)]
    if over:
        rows_held, person = max(over)
        raise SelectionError(f"THESIS_CONSTRUCTION_BREACHED:person_share:{person}:{rows_held}>{limit_for(person)}")
    for forced_index, held in sorted(forced_rows.items()):
        for person in held:
            if person not in people_by_row[forced_index - 1]:
                raise SelectionError(f"THESIS_CONSTRUCTION_BREACHED:placement:{person}:row={forced_index}")
    stacked = sum(1 for lineup in selected if _stacked(rows, lineup.roster))
    if stack_required and stacked != len(selected):
        raise SelectionError(f"THESIS_CONSTRUCTION_BREACHED:stack:{stacked}/{len(selected)}")
    bringbacks = sum(1 for lineup in selected if _bringback(rows, lineup.roster))

    used = [cap for cap in row_caps if cap is not None]
    construction = {
        "version": THESIS_CONSTRUCTION_VERSION,
        "does_not_establish": list(DOES_NOT_ESTABLISH),
        "basis": "STACK_TEAM_THESES_RANKED_BY_THE_PRIOR_OBJECTIVE_UNDER_ONE_PERSON_SHARE_CAP_NOT_A_PORTFOLIO_POLICY",
        "requested": {"max_person_share": float(max_person_share),
                      "person_cap": person_cap(count, float(max_person_share)),
                      "classic_person_overlap": classic_person_overlap, "rows": count,
                      "theses": len(chosen)},
        "effective": {"person_share": round(share, 4), "person_cap": final_cap, "person_overlap": overlap,
                      "stack_required": stack_required, "max_person_rows": top_count,
                      "max_person_share_of_delivered_rows": round(top_count / len(selected), 4),
                      "max_person": top_person, "stacked_lineups": stacked, "bringback_lineups": bringbacks,
                      "lineups": len(selected), "distinct_qb_teams": len(
                          {rows[next(d for d in lineup.roster if rows[d].position == "QB")].team
                           for lineup in selected})},
        "theses": [item.report() for item in history],
        "lineup_theses": {str(lineup.index): tag for lineup, tag in zip(selected, tags)},
        "relaxations": [*relaxations],
        "unfilled_rows": count - len(selected),
        "stopped": stopped,
    }
    if protected_min or ignored:
        # Recounted from the delivered rosters, so the report cannot say what the rows do not.
        delivered = {person: [at + 1 for at, people in enumerate(people_by_row) if person in people]
                     for person in protected_min}
        construction["version"] = THESIS_CONSTRUCTION_VERSION_V2
        construction["does_not_establish"] = [*DOES_NOT_ESTABLISH, *PLACEMENT_DOES_NOT_ESTABLISH]
        construction["placements"] = {
            "requested": dict(protected_min),
            "delivered_rows": delivered,
            "met": {person: len(held) >= protected_min[person] for person, held in delivered.items()},
            "shortfall": {person: protected_min[person] - len(held) for person, held in delivered.items()
                          if len(held) < protected_min[person]},
            "forced_rows": {str(at): list(held) for at, held in sorted(forced_rows.items())},
            "misses": misses,
            "ignored": ignored,
            "abandoned": dict(sorted(abandoned.items())),
            "person_cap_override": {person: limit_for(person) for person in protected_min
                                    if limit_for(person) > final_cap},
            "rows_delivered": len(selected),
        }
    return _Sequential(
        selected=selected,
        forbidden_captains=[],
        captain_repeats_from_index=None,
        differentiate_captain=False,
        effective_overlap=max(used) if used else None,
        requested_overlap=classic_person_overlap,
        overlap_relaxations=steps,
        stopped=stopped,
        construction=construction,
    )
