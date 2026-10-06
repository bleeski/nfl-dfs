"""The Pareto salary redeploy as engine code (Session 64, R37): one rule for `run-slate`'s rung-4 build and the operator scripts.

Ben (R37, 2026-10-04): unused salary is never a defect, and a redeploy is not a way to spend it. A swap is taken
only when it raises the row's prior AND leaves every washout proxy no worse, and where no such swap exists the
portfolio stays as it is and the report says so. Both goals are R34's: the prior is the large-prize proxy (a prior,
never an expected value) and the four proxies below are the washout proxies QA's Tier 2 prints. A swap that helps one
goal and hurts the other is a trade, which this never takes and always counts.

Session 62 built the rule in `scripts/swap_inactives.py`, where `src/` could not reach it; this module is that rule,
lifted, and the script imports it back (one rule, not two). What changed in the lift, each on purpose:

- **Legality is the engine's.** Every trial roster goes through `lineups.validate_lineup` (slot eligibility, cap, two
  games, no repeated person), after being put in DraftKings slot order, because a roster is a set here and a slot
  assignment is how the engine tells a legal one. The Board mirror in the script stays for the script's other modes.
- **Caps are per person and per pair**, as callables: the thesis build's own backstop checks each person against
  `limit_for(person)` (a protected person's own minimum may exceed the shared cap) and each pair against the cap of the
  later row's own build, so a scalar cap would pass a swap the backstop then rejects.
- **Lock awareness.** `locked` DraftKings IDs (a game that kicked off at or before the clock) are never outgoing and
  never incoming.
- **Bounded by counts, never seconds.** The report stores at most `stored_limit` swaps of each kind and the exact totals
  beside them, names its state (`COMPLETED`, `PASS_BOUND_REACHED`, `DEADLINE_STOP`, ...), and carries no clock value, so
  a replay of a pinned run is byte-identical. A `stop` callable ends the work at the caller's window; what was taken
  before it is still a complete, valid, no-worse portfolio because every accepted swap is a whole Pareto step.

`pareto_redeploy_v2` (v1 was the script's report; a changed schema is a new version) does not establish that a prior gain
is an expected value or a win probability, that the four proxies measure leverage or field duplication, that a blank
DraftKings status is official activity evidence, that a redeployed person is playing or has the role his prior assumes,
or that a game the clock says is open is open on DraftKings.
"""

from __future__ import annotations

import collections
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Iterable, Mapping, Sequence

from .contracts import SalaryPlayer, SlateContract
from .lineups import roster_canonical_key, validate_lineup

REDEPLOY_RULE = "pareto_redeploy_v2"
MAX_PASSES = 25
POLL_EVERY = 64  # evaluations between looks at the caller's `stop`, so a test's fake clock sees a fixed cadence
# The engine's stage (`classic_theses`): a construction preference gives way before the clock does, so it asks the run's
# deadline controller for at most this much, never more than this share of the improvement window, and never starts
# under the minimum. A report stores at most `STORED_LIMIT` swaps of each kind (the totals stay exact).
STAGE_NAME = "pareto_redeploy"
STAGE_SECONDS = 20.0
STAGE_WINDOW_SHARE = 0.10
STAGE_MINIMUM_SECONDS = 1.0
STORED_LIMIT = 100
WASHOUT_GOALS = ("max_exposure", "top3_union", "mean_overlap", "distinct_people")
ROW_REJECTION_REASONS = ("ILLEGAL", "SHAPE", "CAPS_OR_DISTINCT")
STATES = ("COMPLETED", "PASS_BOUND_REACHED", "DEADLINE_STOP", "NOT_RUN_WINDOW_SPENT", "NOT_APPLICABLE", "FAILED")
INCOMPLETE_STATES = ("DEADLINE_STOP", "NOT_RUN_WINDOW_SPENT", "FAILED")
DOES_NOT_ESTABLISH = (
    "THAT_A_PRIOR_GAIN_IS_EXPECTED_VALUE_OR_A_WIN_PROBABILITY",
    "THAT_THE_FOUR_WASHOUT_PROXIES_MEASURE_LEVERAGE_OR_FIELD_DUPLICATION",
    "THAT_A_BLANK_DRAFTKINGS_STATUS_IS_OFFICIAL_ACTIVITY_EVIDENCE",
    "THAT_ANY_REDEPLOYED_PERSON_IS_PLAYING_OR_HAS_THE_ROLE_HIS_PRIOR_ASSUMES",
    "THAT_A_GAME_THE_CLOCK_SAYS_IS_OPEN_IS_OPEN_ON_DRAFTKINGS",
)
FLEX_POSITIONS = ("RB", "WR", "TE")
_GAIN_EPSILON = 1e-9


# --------------------------------------------------------------------------- #
# The washout proxies: QA Tier 2's own arithmetic
# --------------------------------------------------------------------------- #


def washout_proxies(rosters) -> dict:
    """The portfolio's washout proxies, counted exactly as `qa_classic_portfolio.py` Tier 2 prints them: max
    single-person exposure, the rows the three most-used people cover between them (`most_common(3)`, ties
    broken by first appearance, which is why the rosters must arrive in assignment order), mean pairwise
    overlap and distinct people. Mean pairwise overlap is the sum over people of C(rows held, 2) divided by the
    pairs, which is the same number as averaging the pairs and is an integer until the last step, so two
    portfolios compare exactly."""

    rosters = [list(roster) for roster in rosters]
    exposure = collections.Counter(i for roster in rosters for i in roster)
    rows = len(rosters)
    if not exposure:
        return {"rows": rows, "max_exposure": 0, "max_exposure_person": None, "top3_union": 0,
                "pair_overlap_sum": 0, "mean_overlap": 0.0, "distinct_people": 0}
    top3 = [i for i, _n in exposure.most_common(3)]
    most_used, most_rows = exposure.most_common(1)[0]
    pair_overlap_sum = sum(n * (n - 1) // 2 for n in exposure.values())
    pairs = rows * (rows - 1) // 2
    return {
        "rows": rows,
        "max_exposure": most_rows,
        "max_exposure_person": most_used,
        "top3_union": sum(1 for roster in rosters if any(i in roster for i in top3)),
        "pair_overlap_sum": pair_overlap_sum,
        "mean_overlap": pair_overlap_sum / pairs if pairs else 0.0,
        "distinct_people": len(exposure),
    }


def proxies_hurt(before: dict, after: dict) -> list[str]:
    """Every washout goal `after` is worse on than `before`, in `WASHOUT_GOALS` order. Empty means no proxy is
    worse: max exposure, top-3 union and mean overlap no higher, distinct people no fewer."""

    hurt = []
    if after["max_exposure"] > before["max_exposure"]:
        hurt.append("max_exposure")
    if after["top3_union"] > before["top3_union"]:
        hurt.append("top3_union")
    if after["pair_overlap_sum"] > before["pair_overlap_sum"]:
        hurt.append("mean_overlap")
    if after["distinct_people"] < before["distinct_people"]:
        hurt.append("distinct_people")
    return hurt


# --------------------------------------------------------------------------- #
# Slot order and the clock
# --------------------------------------------------------------------------- #


def slot_order(by_id: Mapping[str, SalaryPlayer], roster: Iterable[str]) -> tuple[str, ...] | None:
    """The Classic roster in DraftKings slot order (QB, RB, RB, WR, WR, WR, TE, FLEX, DST), or None when its
    positions cannot fill the slots. Within a position the order is the optimizer's (`LineupOptimizer._slot_roster`:
    salary high to low, then name, then ID) and the FLEX is the one RB, WR or TE left over, so a roster that
    came out of the solver comes back unchanged. `validate_lineup` is the legality; this only arranges."""

    ids = [str(i) for i in roster]
    if len(ids) != 9 or any(i not in by_id for i in ids):
        return None
    positions: dict[str, list[SalaryPlayer]] = {
        position: sorted((by_id[i] for i in ids if by_id[i].position == position),
                         key=lambda p: (-p.salary, p.name, p.dk_id))
        for position in ("QB", "RB", "WR", "TE", "DST")
    }
    if (len(positions["QB"]) != 1 or len(positions["DST"]) != 1 or len(positions["RB"]) < 2
            or len(positions["WR"]) < 3 or len(positions["TE"]) < 1
            or sum(len(rows) for rows in positions.values()) != 9):
        return None
    ordered = [positions["QB"].pop(0).dk_id]
    ordered.extend(positions["RB"].pop(0).dk_id for _ in range(2))
    ordered.extend(positions["WR"].pop(0).dk_id for _ in range(3))
    ordered.append(positions["TE"].pop(0).dk_id)
    flex = [p for position in FLEX_POSITIONS for p in positions[position]]
    if len(flex) != 1:
        return None
    ordered.append(flex[0].dk_id)
    ordered.append(positions["DST"].pop(0).dk_id)
    return tuple(ordered)


def locked_dk_ids(slate: SlateContract, now: datetime) -> frozenset[str]:
    """Every DraftKings ID whose game kicked off at or before `now`. A cell holding one is locked on DraftKings."""

    if now.tzinfo is None:
        raise ValueError("REDEPLOY_NOW_NOT_TIMEZONE_AWARE: the lock clock needs an aware moment")
    return frozenset(player.dk_id for player in slate.players if player.lock_at <= now)


# --------------------------------------------------------------------------- #
# The rule
# --------------------------------------------------------------------------- #


@dataclass
class RedeployResult:
    rosters: dict[str, tuple[str, ...]]  # every row, in the order it arrived; a changed row is a new tuple
    log: list[str]
    report: dict[str, object]

    @property
    def changed(self) -> list[str]:
        return list(self.report.get("changed_entry_ids") or ())


class _Stop(Exception):
    """The caller's window is spent."""


def _constant(value) -> Callable:
    return value if callable(value) else (lambda *_args: value)


def incomplete_report(state: str, reason: str, **extra: object) -> dict[str, object]:
    """The block for a redeploy that did not run to its own end (`NOT_RUN_WINDOW_SPENT`, `NOT_APPLICABLE`,
    `FAILED`): the same identity and `does_not_establish` as a full report, no number it did not compute."""

    if state not in STATES or state in ("COMPLETED", "PASS_BOUND_REACHED"):
        raise ValueError(f"not an incomplete state: {state}")
    return {"rule": REDEPLOY_RULE, "state": state, "reason": reason, "does_not_establish": list(DOES_NOT_ESTABLISH),
            "accepted_total": 0, "changed_entry_ids": [], **extra}


class _Redeploy:
    def __init__(self, slate, scores, rosters, *, row_ids, protect, gated, forbidden_keys, exposure_limit,
                 overlap_cap, min_salary, locked, slot_ordered, stored_limit, stop, max_passes):
        self.slate = slate
        self.by_id: dict[str, SalaryPlayer] = {player.dk_id: player for player in slate.players}
        unknown = sorted({i for roster in rosters.values() for i in roster if str(i) not in self.by_id})
        if unknown:
            raise ValueError(f"REDEPLOY_DK_ID_NOT_IN_POOL: {unknown[:5]}")
        self.scores = scores
        self.rows: dict[str, tuple[str, ...]] = {str(e): tuple(str(i) for i in r) for e, r in rosters.items()}
        short = sorted(e for e, r in self.rows.items() if len(r) != 9)
        if short:
            raise ValueError(f"REDEPLOY_ROSTERS_NOT_NINE_CELLS: {short[:5]}")
        wanted = set(self.rows) if row_ids is None else {str(e) for e in row_ids}
        absent = sorted(wanted - set(self.rows))
        if absent:
            raise ValueError(f"REDEPLOY_ROW_UNKNOWN: {absent[:5]}")
        self.order = [e for e in self.rows if e in wanted]
        self.protect = frozenset(str(i) for i in protect)
        self.gated = frozenset(str(i) for i in gated)
        self.forbidden = frozenset(forbidden_keys)
        self.locked = frozenset(str(i) for i in locked)
        self.exposure_limit = _constant(exposure_limit)
        self.overlap_cap = _constant(overlap_cap)
        self.min_salary = int(min_salary)
        self.slot_ordered = slot_ordered
        self.stored_limit = stored_limit
        self.stop = stop
        self.max_passes = int(max_passes)
        self.cap = int(slate.salary_cap)
        self.person = {dk_id: player.underlying_id for dk_id, player in self.by_id.items()}
        self.name_of_person: dict[str, str] = {}
        for player in slate.players:
            self.name_of_person.setdefault(player.underlying_id, player.name)
        self.persons = {e: tuple(self.person[i] for i in r) for e, r in self.rows.items()}
        self.person_sets = {e: frozenset(p) for e, p in self.persons.items()}
        self.exposure = collections.Counter(p for persons in self.persons.values() for p in persons)
        self.keys = {e: roster_canonical_key(slate, r) for e, r in self.rows.items()}
        self.key_counts = collections.Counter(self.keys.values())
        self.log: list[str] = []
        self.pool = sorted(
            i for i, player in self.by_id.items()
            if float(scores.get(i, 0.0)) > 0 and i not in self.protect and i not in self.gated
            and i not in self.locked and not (player.status_raw or "").strip()
        )
        self.original = dict(self.rows)
        self.ticks = 0
        self.current = self._proxies()

    # -- small views ---------------------------------------------------------

    def _tick(self) -> None:
        self.ticks += 1
        if self.stop is not None and self.ticks % POLL_EVERY == 0 and self.stop():
            raise _Stop

    def _proxies(self, entry: str | None = None, persons: Sequence[str] | None = None) -> dict:
        return washout_proxies(
            [persons if e == entry else p for e, p in self.persons.items()] if entry is not None
            else list(self.persons.values()))

    def _qb(self, roster) -> SalaryPlayer | None:
        return next((self.by_id[i] for i in roster if self.by_id[i].position == "QB"), None)

    def _core(self, roster) -> set[str]:
        """The QB, and everyone on his team or his opponent's: the stack and the bring-back this row was built for."""

        qb = self._qb(roster)
        if qb is None:
            return set()
        return {i for i in roster if i == qb.dk_id or self.by_id[i].team in (qb.team, qb.opponent)}

    def _has_stack(self, roster) -> bool:
        qb = self._qb(roster)
        return qb is not None and any(
            i != qb.dk_id and self.by_id[i].team == qb.team and self.by_id[i].position in ("WR", "TE") for i in roster)

    def _has_bringback(self, roster) -> bool:
        qb = self._qb(roster)
        return qb is not None and any(
            self.by_id[i].team == qb.opponent and self.by_id[i].position != "DST" for i in roster)

    def _preserves_shape(self, original, trial) -> bool:
        if self._has_stack(original) and not self._has_stack(trial):
            return False
        return not (self._has_bringback(original) and not self._has_bringback(trial))

    def _clashes(self, roster) -> int:
        """DST-against-own-skill and DST-against-own-QB clashes: QA Tier 2's anti-correlation, which the engine's
        thesis build does not enforce, so a row may already have one; a swap may never add one."""

        dsts = [self.by_id[i] for i in roster if self.by_id[i].position == "DST"]
        if not dsts:
            return 0
        dst = dsts[0]
        count = sum(1 for i in roster if self.by_id[i].position != "DST" and self.by_id[i].team == dst.opponent)
        qb = self._qb(roster)
        return count + (1 if qb is not None and dst.team == qb.opponent else 0)

    # -- one trial -----------------------------------------------------------

    def _trial(self, entry: str, outgoing: str, incoming: str):
        """`(roster to emit, persons, canonical key)` for a legal, fitting, shape-keeping swap, else `(None, reason)`."""

        roster = self.rows[entry]
        trial = tuple(incoming if i == outgoing else i for i in roster)
        ordered = slot_order(self.by_id, trial)
        validation = validate_lineup(self.slate, ordered) if ordered is not None else None
        if (validation is None or not validation.valid or validation.lineup.salary < self.min_salary
                or self._clashes(trial) > self._clashes(roster)):
            return None, "ILLEGAL"
        if not self._preserves_shape(roster, trial):
            return None, "SHAPE"
        emitted = ordered if self.slot_ordered else trial
        # A locked cell stays where it is: re-ordering a changed row into slot order must not move a locked person to
        # another slot (the script path replaces the cell in place, so it never does).
        if self.locked and any(emitted[k] != cell for k, cell in enumerate(roster) if cell in self.locked):
            return None, "SHAPE"
        key = validation.lineup.canonical_key
        # The people are counted in the order the row is DELIVERED in: `washout_proxies` breaks the top-3 tie by first
        # appearance, and QA Tier 2 counts the delivered cells, so the rule must decide on the same order.
        persons = tuple(self.person[i] for i in emitted)
        if not self._fits(entry, key, persons):
            return None, "CAPS_OR_DISTINCT"
        return (emitted, persons, key), None

    def _fits(self, entry: str, key: str, persons: tuple[str, ...]) -> bool:
        """R29 (distinct from every other row and every prefilled roster), the pair overlap caps and the per-person
        limits, each against every OTHER row's current people."""

        if key in self.key_counts or key in self.forbidden:
            return False
        trial_set = frozenset(persons)
        for other, other_set in self.person_sets.items():
            if other == entry:
                continue
            cap = self.overlap_cap(entry, other)
            if cap is not None and len(trial_set & other_set) > cap:
                return False
        own = self.person_sets[entry]
        return all(self.exposure[p] - (1 if p in own else 0) + 1 <= self.exposure_limit(p) for p in trial_set)

    def _candidates(self, entry: str) -> list[tuple[float, int, str, str]]:
        """Prior-raising single swaps that fit the cap, best first: (-gain, incoming's exposure, incoming, outgoing)."""

        roster = self.rows[entry]
        in_roster = set(roster)
        core = self._core(roster)
        headroom = self.cap - sum(self.by_id[i].salary for i in roster)
        found = []
        for outgoing in roster:
            player = self.by_id[outgoing]
            if (outgoing in core or outgoing in self.protect or outgoing in self.locked
                    or player.position in ("QB", "DST")):
                continue
            group = FLEX_POSITIONS if player.position in FLEX_POSITIONS else (player.position,)
            for incoming in self.pool:
                if incoming in in_roster or self.by_id[incoming].position not in group:
                    continue
                if self.by_id[incoming].salary - player.salary > headroom:
                    continue
                gain = float(self.scores[incoming]) - float(self.scores.get(outgoing, 0.0))
                if gain > _GAIN_EPSILON:
                    found.append((round(-gain, 9), self.exposure[self.person[incoming]], incoming, outgoing))
        found.sort()
        return found

    def _apply(self, entry: str, emitted, persons, key) -> None:
        old_key = self.keys[entry]
        self.key_counts[old_key] -= 1
        if not self.key_counts[old_key]:
            del self.key_counts[old_key]
        self.keys[entry] = key
        self.key_counts[key] += 1
        self.exposure.subtract(self.persons[entry])
        self.exposure.update(persons)
        self.rows[entry] = tuple(emitted)
        self.persons[entry] = persons
        self.person_sets[entry] = frozenset(persons)

    # -- the pass loop and the refusal scan ----------------------------------

    def run(self) -> dict[str, object]:
        accepted: list[dict[str, object]] = []
        log: list[str] = []
        passes, fixed_point, stopped = 0, False, False
        try:
            while passes < self.max_passes:
                passes += 1
                taken = 0
                for entry in self.order:
                    # Every swap raises the total prior, so a row ends; the bound (one swap per cell a pass) only makes a
                    # regression in that rule stop at the pass bound instead of looping.
                    for _swap in range(len(self.rows[entry])):
                        take = None
                        for neg_gain, _used, incoming, outgoing in self._candidates(entry):
                            self._tick()
                            # Necessary for "mean overlap no higher": one swap changes the pair-overlap sum by
                            # incoming's rows minus outgoing's rows plus one, so incoming must be used at least one
                            # fewer time. A candidate that fails it would be refused by `proxies_hurt` anyway.
                            if (self.exposure[self.person[incoming]] > self.exposure[self.person[outgoing]] - 1):
                                continue
                            built, refused = self._trial(entry, outgoing, incoming)
                            if refused:
                                continue
                            emitted, persons, key = built
                            after = self._proxies(entry, persons)
                            if proxies_hurt(self.current, after):
                                continue
                            take = (-neg_gain, incoming, outgoing, emitted, persons, key, after)
                            break
                        if take is None:
                            break
                        gain, incoming, outgoing, emitted, persons, key, after = take
                        self._apply(entry, emitted, persons, key)
                        self.current = after
                        taken += 1
                        accepted.append({
                            "entry_id": entry, "out": outgoing, "out_name": self.by_id[outgoing].name,
                            "in": incoming, "in_name": self.by_id[incoming].name, "prior_gain": round(gain, 3),
                            "salary_delta": self.by_id[incoming].salary - self.by_id[outgoing].salary, "pass": passes,
                        })
                        log.append(f"REDEPLOY {entry}: {self.by_id[outgoing].name} -> {self.by_id[incoming].name} (+{gain:.2f})")
                if not taken:
                    fixed_point = True
                    break
        except _Stop:
            stopped = True
        # The window ending in the pass loop leaves the portfolio short of its fixed point: `DEADLINE_STOP`. The window
        # ending only in the refusal scan leaves it AT its fixed point with partial refusal counts: the state stays what the
        # swaps made it and `refusal_scan` says `PARTIAL`.
        scan = self._refusal_scan() if not stopped else {"state": "NOT_RUN"}
        state = "DEADLINE_STOP" if stopped else "COMPLETED" if fixed_point else "PASS_BOUND_REACHED"
        self.log = log
        return self._report(state, accepted, passes, fixed_point, scan)

    def _refusal_scan(self) -> dict[str, object]:
        """At the point the loop ended, count every prior-raising swap that was refused, with the goals it would
        hurt (a legal swap) or the row-level reason (an illegal one). Exact over everything it reaches."""

        rejected: list[dict[str, object]] = []
        by_goal = {goal: 0 for goal in WASHOUT_GOALS}
        row_rejections = {reason: 0 for reason in ROW_REJECTION_REASONS}
        available = 0
        try:
            for entry in self.order:
                for neg_gain, _used, incoming, outgoing in self._candidates(entry):
                    self._tick()
                    built, refused = self._trial(entry, outgoing, incoming)
                    if refused:
                        row_rejections[refused] += 1
                        continue
                    hurts = proxies_hurt(self.current, self._proxies(entry, built[1]))
                    if not hurts:
                        available += 1  # only when the pass bound was reached before a fixed point
                        continue
                    for goal in hurts:
                        by_goal[goal] += 1
                    rejected.append({
                        "entry_id": entry, "out": outgoing, "out_name": self.by_id[outgoing].name,
                        "in": incoming, "in_name": self.by_id[incoming].name, "prior_gain": round(-neg_gain, 3),
                        "hurts": hurts,
                    })
        except _Stop:
            return {"state": "PARTIAL", "rejected": rejected, "by_goal": by_goal, "row": row_rejections,
                    "available": available}
        return {"state": "COMPLETE", "rejected": rejected, "by_goal": by_goal, "row": row_rejections,
                "available": available}

    # -- the report ----------------------------------------------------------

    def _snapshot(self, rosters: Mapping[str, Sequence[str]], persons: Mapping[str, Sequence[str]]) -> dict:
        proxies = washout_proxies(list(persons.values()))
        person = proxies["max_exposure_person"]
        return {
            "rows": proxies["rows"],
            "prior_sum": round(sum(float(self.scores.get(i, 0.0)) for roster in rosters.values() for i in roster), 3),
            "max_exposure": proxies["max_exposure"],
            "max_exposure_person": self.name_of_person.get(person, person) if person else None,
            "top3_union": proxies["top3_union"],
            "mean_overlap": round(proxies["mean_overlap"], 6),
            "pair_overlap_sum": proxies["pair_overlap_sum"],
            "distinct_people": proxies["distinct_people"],
        }

    def _report(self, state, accepted, passes, fixed_point, scan) -> dict[str, object]:
        limit = self.stored_limit
        counted = scan["state"] in ("COMPLETE", "PARTIAL")
        rejected = sorted(scan.get("rejected") or [], key=lambda record: -record["prior_gain"])  # stable: row order
        original_persons = {e: tuple(self.person[i] for i in r) for e, r in self.original.items()}
        report: dict[str, object] = {
            "rule": REDEPLOY_RULE,
            "state": state,
            "does_not_establish": list(DOES_NOT_ESTABLISH),
            "rows_considered": len(self.order),
            "gated_people": len(self.gated),
            "locked_people": len({self.person[i] for i in self.locked if i in self.person}),
            "passes": passes,
            "fixed_point": fixed_point,
            "protected": [
                {"dk_id": i, "name": self.by_id[i].name,
                 "rows_before": sum(1 for r in self.original.values() if i in r),
                 "rows_after": sum(1 for r in self.rows.values() if i in r)}
                for i in sorted(self.protect) if i in self.by_id
            ],
            "before": self._snapshot(self.original, original_persons),
            "after": self._snapshot(self.rows, self.persons),
            "accepted_total": len(accepted),
            "accepted": accepted if limit is None else accepted[:limit],
            "changed_entry_ids": [e for e in self.order if self.rows[e] != self.original[e]],
            "refusal_scan": scan["state"],
            "rejected_total": len(rejected) if counted else None,
            "rejected_by_goal": scan["by_goal"] if counted else None,
            "rejected": (rejected if limit is None else rejected[:limit]) if counted else [],
            "row_rejections": scan["row"] if counted else None,
            "available_at_stop": scan["available"] if counted else None,
            "stored_limit": limit,
        }
        return report


def redeploy(
    slate: SlateContract,
    scores: Mapping[str, float],
    rosters: Mapping[str, Sequence[str]],
    *,
    row_ids: Iterable[str] | None = None,
    protect: Iterable[str] = (),
    gated: Iterable[str] = (),
    forbidden_keys: Iterable[str] = (),
    exposure_limit: int | Callable[[str], int],
    overlap_cap: int | None | Callable[[str, str], int | None],
    min_salary: int = 0,
    locked: Iterable[str] = (),
    slot_ordered: bool = True,
    stored_limit: int | None = None,
    stop: Callable[[], bool] | None = None,
    max_passes: int = MAX_PASSES,
) -> RedeployResult:
    """Take salary-driven upgrades only as Pareto gains, to a fixed point. Nothing passed in is mutated.

    A swap (row, outgoing, incoming) is taken only when ALL hold:
      1. the incoming person's prior is higher than the outgoing person's (the row's prior rises);
      2. the row, put in slot order, is a legal Classic lineup (`validate_lineup`: slots, cap, two games, no
         repeated person) at or above `min_salary` (the operator's floor, never inherited), and the swap adds no
         DST-against-own-skill or DST-against-own-QB clash;
      3. the row keeps a stack or bring-back it had, stays distinct from every other row and every
         `forbidden_keys` roster (R29), inside the per-pair `overlap_cap(entry_a, entry_b)` (None: uncapped) and the
         per-person `exposure_limit(person)`;
      4. the QB, the DST, his team and his opponent (the stack and the bring-back), every `protect` ID and every
         `locked` ID are never outgoing; a protected, locked or `gated` ID is never incoming, and an incoming
         person has a blank DraftKings status and a positive prior;
      5. recomputed on the whole portfolio, no washout proxy is worse (`proxies_hurt`).
    The local rule "the incoming person is used at least two fewer times" is a sufficient condition, not the
    proof: rule 5 is the proof, and it also takes a swap whose incoming person is used one fewer time.

    `rosters` maps entry ID to nine DraftKings IDs in the order the rows are counted (the proxies break ties by
    first appearance); `row_ids` restricts which rows may change (every row still counts in the proxies). Rows are
    visited in that order, each takes its best swap (prior gain, then the less-used incoming person, then IDs) until it
    has none, and whole passes repeat until one takes nothing: every swap raises the total prior, so it ends, and at that
    fixed point a rerun on the output changes nothing (`fixed_point`; if `max_passes` (default `MAX_PASSES`) stops it first the state is
    `PASS_BOUND_REACHED` and a rerun continues). With `slot_ordered` a changed row comes back in DraftKings slot order
    (the engine's rows); without it the cell is replaced in place (the operator scripts' rows, which are not slot-ordered).

    `stop`, polled every `POLL_EVERY` evaluations, ends the work at the caller's window. A stop in the pass loop is
    `DEADLINE_STOP`: what was taken stays (each swap is a whole Pareto step), the portfolio is no worse, and it may be
    short of its fixed point. A stop only in the refusal scan leaves the portfolio at its fixed point and the state as the
    swaps made it, with `refusal_scan` `PARTIAL` (the counts cover what the scan reached) or `NOT_RUN`.
    `stored_limit` bounds the lists of swaps the report stores (`accepted`, `rejected`); the totals beside them stay
    exact. A locked cell never moves: with `slot_ordered`, a swap that would re-order a row so that a locked person
    changes slot is refused (`SHAPE`). Returns the new rosters, the log and the report."""

    if not rosters:
        return RedeployResult({}, [], incomplete_report("NOT_APPLICABLE", "NO_ROWS"))
    run = _Redeploy(
        slate, scores, rosters, row_ids=row_ids, protect=protect, gated=gated, forbidden_keys=forbidden_keys,
        exposure_limit=exposure_limit, overlap_cap=overlap_cap, min_salary=min_salary, locked=locked,
        slot_ordered=slot_ordered, stored_limit=stored_limit, stop=stop, max_passes=max_passes)
    if not run.order:
        return RedeployResult(dict(run.rows), [], incomplete_report("NOT_APPLICABLE", "NO_ROW_MAY_CHANGE"))
    report = run.run()
    return RedeployResult(dict(run.rows), run.log, report)


# --------------------------------------------------------------------------- #
# The report as handoff text
# --------------------------------------------------------------------------- #


def render_report(report: Mapping[str, object], limit: int = 10) -> list[str]:
    """The block as handoff text: both goals before and after, and the refused swaps by the goal they would hurt."""

    state = report.get("state")
    if "before" not in report:
        return [f"PARETO_REDEPLOY state={state}: {report.get('reason')}; the portfolio is as it was built"]
    lines = [
        f"PARETO_REDEPLOY state={state} rows_considered={report['rows_considered']} passes={report['passes']} "
        f"fixed_point={report['fixed_point']} accepted={report['accepted_total']} locked_people={report['locked_people']}"
    ]
    for label, snap in (("before:", report["before"]), ("after :", report["after"])):
        lines.append(
            f"  {label} prior_sum={snap['prior_sum']} max_exposure={snap['max_exposure']}/{snap['rows']} "
            f"({snap['max_exposure_person']}) top3_union={snap['top3_union']}/{snap['rows']} "
            f"mean_overlap={snap['mean_overlap']:.4f} distinct_people={snap['distinct_people']}"
        )
    if state == "PASS_BOUND_REACHED":
        lines.append(
            f"  PASS_BOUND_REACHED: stopped after {report['passes']} passes with {report['available_at_stop']} further "
            "Pareto swaps available; rerun on this output to continue (a rerun changes nothing only at a fixed point)"
        )
    if state == "DEADLINE_STOP":
        lines.append(
            "  DEADLINE_STOP: the window ended in the pass loop; every swap taken is a whole Pareto step and the portfolio "
            f"is no worse, but it is not at its fixed point (fixed_point={report['fixed_point']}); refusal scan: "
            f"{report['refusal_scan']}"
        )
    elif report["refusal_scan"] != "COMPLETE":
        lines.append(
            f"  refusal scan {report['refusal_scan']}: the window ended while the refused swaps were being counted, so the "
            "counts below cover what it reached; the portfolio itself is as the swaps left it"
        )
    if report["protected"]:
        lines.append("  protected (rows before -> after): " + ", ".join(
            f"{person['name']} ({person['rows_before']} -> {person['rows_after']})" for person in report["protected"]))
    if report["rejected_total"] is not None:
        goals = report["rejected_by_goal"]
        lines.append(
            f"  rejected (prior-raising, legal, would hurt a goal): {report['rejected_total']} swaps "
            f"({len(report['rejected'])} stored); by goal: " + " ".join(f"{goal}={goals[goal]}" for goal in WASHOUT_GOALS)
        )
        for record in report["rejected"][:limit]:
            lines.append(
                f"  REJECTED {record['entry_id']}: {record['out_name']} -> {record['in_name']} "
                f"(+{record['prior_gain']:.2f}) would hurt: {', '.join(record['hurts'])}"
            )
        lines.append(
            "  row-level rejections (not goal trades): "
            + " ".join(f"{reason}={report['row_rejections'][reason]}" for reason in ROW_REJECTION_REASONS)
        )
    if not report["accepted_total"] and state == "COMPLETED":  # the fixed point itself says no swap is left to take
        lines.append(
            "NO_PARETO_GAIN: no swap raises a row's prior without hurting a washout proxy; the portfolio is unchanged"
        )
    return lines
