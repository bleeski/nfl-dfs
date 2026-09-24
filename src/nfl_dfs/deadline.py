"""The deadline controller (Session 07, R31): one time budget for a whole run.

R31 sets the default delivery deadline at 5 minutes before the earliest relevant
lock. Before this module every stage kept its own fixed clock (the baseline's
60 s, the session probe's 45 s, 30 s per fetch, a policy's own search limits),
so no run knew how long it had. `run-slate` now builds one `Budget` right after
intake and every stage takes its allowance from it:

- **the deadline** is the request's `delivery_deadline_utc`, or the earliest
  relevant lock minus 5 minutes. The earliest relevant lock is the earliest
  `lock_at` among the salary file's games: every contest on one draft group locks
  at its first kickoff, and every blank row a pre-lock run fills is on that draft
  group, so a template whose entries span contests takes the same minimum;
- **the improvement stops earlier**, at the deadline less a finishing reserve of
  `stop_discretionary_optimization_minutes_before_lock` (`config/runtime.json`,
  10) minus R31's 5: discretionary optimization stops at lock minus 10 and
  delivery is due at lock minus 5, so the export, audit and review have 5
  minutes. An explicit deadline keeps the same 5-minute reserve;
- **the baseline is never cut below its floor**: it gets `min(60, max(30,
  seconds to the deadline))`, a deadline already passed included, because a late
  file beats no file;
- **the clock**: elapsed time is always the injected monotonic clock. The
  deadline is compared with the run's clock, which is the pinned `--as-of` moment
  advanced by that elapsed time, or the wall clock when nothing is pinned. The
  wall clock is recorded beside a pinned one and never used for arithmetic.

When the window is spent the improvement stops at the next stage boundary and
the baseline stays the deliverable. Every stop or shortened allowance is a
registered limitation (`delivery_deadline`, `S`: a construction budget, never
a gate that withholds a valid file), and every stage's allowance and measured
duration is in the `nfl_deadline_budget_v1` record the run writes.

Evidence fetches (`sources.fetch_public_artifact` and the forecast capture
script) and the Classic policy generator take their allowances from it in
Session 07b.
"""

from __future__ import annotations

import json
import math
import os
import platform
import re
import time
from collections.abc import Callable, Iterable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .contracts import DeliveryLimitation
from .gate_registry import GateRegistry

CONTRACT_VERSION = "nfl_deadline_budget_v1"
RATE_LEDGER_VERSION = "nfl_host_candidate_rate_v1"
HANDOFF_RESERVE = timedelta(minutes=5)  # R31
DEFAULT_STOP_MINUTES = 10.0  # runtime.json `stop_discretionary_optimization_minutes_before_lock`
# The baseline: measured at 1.3 s for the slowest single solve and about 6 s for
# 150 distinct Showdown lineups (Session 04). The floor is five times that; the
# cap is the fixed budget it had before this module.
BASELINE_FLOOR_SECONDS = 30.0
BASELINE_CAP_SECONDS = 60.0
BASELINE_PER_SOLVE_SECONDS = 5.0
PROBE_SHARE, PROBE_MINIMUM_SECONDS = 0.10, 3.0
SOLVE_MINIMUM_SECONDS = 0.5
BANK_SHARE, JOINT_SHARE = 0.70, 0.20
RATE_OBSERVATIONS_KEPT, RATE_OBSERVATIONS_READ = 20, 5

DOES_NOT_ESTABLISH = (
    "UPLOAD_CLEARANCE",
    "CERTIFICATION",
    "LINEUP_QUALITY",
    "THAT_THE_DEADLINE_IS_MET_AFTER_THE_RUN_ENDS",
)


def earliest_lock(games: Iterable[object]) -> datetime:
    """The earliest `lock_at` among a slate's games: the earliest relevant lock.

    Aware moments compare as instants; the result keeps its game's own zone (the
    baseline report prints it that way), and the budget converts it to UTC.
    """

    locks = [getattr(game, "lock_at") for game in games]
    if not locks:
        raise ValueError("a slate with no games has no lock")
    return min(locks)


def default_deadline(games: Iterable[object]) -> datetime:
    """R31: 5 minutes before the earliest relevant lock."""

    return earliest_lock(games).astimezone(timezone.utc) - HANDOFF_RESERVE


def parse_moment(value: str) -> datetime:
    """An aware ISO-8601 moment in UTC; a naive or unparseable one is refused."""

    moment = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    if moment.tzinfo is None:
        raise ValueError(f"{value!r} has no UTC offset")
    return moment.astimezone(timezone.utc)


def finish_reserve(stop_minutes: float) -> timedelta:
    """How long before the delivery deadline discretionary optimization stops."""

    if (isinstance(stop_minutes, bool) or not isinstance(stop_minutes, (int, float))
            or not math.isfinite(stop_minutes)):
        raise ValueError("stop_discretionary_optimization_minutes_before_lock must be a finite number")
    reserve = timedelta(minutes=float(stop_minutes)) - HANDOFF_RESERVE
    if not timedelta(0) <= reserve <= timedelta(hours=2):
        raise ValueError(
            "stop_discretionary_optimization_minutes_before_lock must be at least R31's 5 minutes"
            " and at most 125"
        )
    return reserve


def runtime_stop_minutes(runtime: Mapping[str, object]) -> float:
    """The registered stop from `config/runtime.json`, validated by `finish_reserve`."""

    value = runtime.get("stop_discretionary_optimization_minutes_before_lock", DEFAULT_STOP_MINUTES)
    finish_reserve(value)  # type: ignore[arg-type]
    return float(value)  # type: ignore[arg-type]


@dataclass
class StageRecord:
    name: str
    started_after_seconds: float | None = None
    elapsed_seconds: float | None = None
    default_seconds: float | None = None
    allowance_seconds: float | None = None
    outcome: str | None = None

    def as_record(self) -> dict[str, object]:
        return {
            "name": self.name,
            "started_after_seconds": _round(self.started_after_seconds),
            "elapsed_seconds": _round(self.elapsed_seconds),
            "default_seconds": _round(self.default_seconds),
            "allowance_seconds": _round(self.allowance_seconds),
            "outcome": self.outcome,
        }


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 3)


@dataclass
class Budget:
    """The run's one clock and time budget. Build it with `Budget.build`."""

    deadline: datetime
    deadline_source: str
    lock: datetime
    started: datetime
    wall_started: datetime
    pinned: bool
    reserve: timedelta
    stop_minutes: float
    clock: Callable[[], float] = time.monotonic
    clock_started: float = 0.0
    stages: list[StageRecord] = field(default_factory=list)
    events: list[tuple[str, str]] = field(default_factory=list)
    candidate_rate: dict[str, object] | None = None

    @classmethod
    def build(
        cls,
        games: Iterable[object],
        *,
        requested_deadline: str | datetime | None = None,
        as_of: datetime | None = None,
        stop_minutes: float = DEFAULT_STOP_MINUTES,
        clock: Callable[[], float] = time.monotonic,
        wall: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> "Budget":
        lock = earliest_lock(games).astimezone(timezone.utc)
        if isinstance(requested_deadline, str):
            requested = parse_moment(requested_deadline)
        elif isinstance(requested_deadline, datetime):
            requested = parse_moment(requested_deadline.isoformat())
        else:
            requested = None
        wall_started = wall().astimezone(timezone.utc)
        budget = cls(
            deadline=requested or lock - HANDOFF_RESERVE,
            deadline_source="REQUEST" if requested else "DEFAULT_EARLIEST_LOCK_MINUS_R31",
            lock=lock,
            started=(as_of.astimezone(timezone.utc) if as_of is not None else wall_started),
            wall_started=wall_started,
            pinned=as_of is not None,
            reserve=finish_reserve(stop_minutes),
            stop_minutes=float(stop_minutes),
            clock=clock,
            clock_started=clock(),
        )
        if budget.deadline <= budget.started:
            budget._limitation_event(
                "DEADLINE_PASSED_AT_START",
                f"the delivery deadline {budget.deadline.isoformat()} had passed when the run's"
                f" clock read {budget.started.isoformat()}; the baseline is built at its"
                f" {BASELINE_FLOOR_SECONDS:.0f} s floor and is the deliverable, and no discretionary"
                " optimization is attempted")
        if requested is not None and requested > lock:
            budget._limitation_event(
                "DEADLINE_AFTER_EARLIEST_LOCK",
                f"the request's delivery deadline {requested.isoformat()} is after the earliest"
                f" lock {lock.isoformat()}; DraftKings takes no lineup for a blank row after"
                " its contest locks, so a file delivered then cannot be entered")
        if budget.pinned and budget.started < budget.deadline <= wall_started:
            budget._limitation_event(
                "DEADLINE_WALL_CLOCK_PAST_DEADLINE",
                f"the run's clock is pinned to {budget.started.isoformat()}, and the wall clock"
                f" {wall_started.isoformat()} is past the delivery deadline"
                f" {budget.deadline.isoformat()}: a replay, not a live delivery")
        return budget

    # -- the clock ----------------------------------------------------------

    def elapsed(self) -> float:
        return max(0.0, self.clock() - self.clock_started)

    def now(self) -> datetime:
        return self.started + timedelta(seconds=self.elapsed())

    @property
    def improvement_stop(self) -> datetime:
        return self.deadline - self.reserve

    @property
    def passed_at_start(self) -> bool:
        return self.deadline <= self.started

    def remaining(self) -> float:
        """Seconds from the run's clock to the delivery deadline; negative once past."""

        return (self.deadline - self.now()).total_seconds()

    def improvement_remaining(self) -> float:
        """Seconds until discretionary optimization must stop."""

        return (self.improvement_stop - self.now()).total_seconds()

    # -- stages -------------------------------------------------------------

    def _open(self, name: str) -> StageRecord:
        for record in reversed(self.stages):
            if record.name == name and record.elapsed_seconds is None and record.outcome != "SKIPPED":
                return record
        record = StageRecord(name)
        self.stages.append(record)
        return record

    @contextmanager
    def stage(self, name: str) -> Iterator[StageRecord]:
        """Measure one stage; its allowance, if any, was set by `allowance` first."""

        record = self._open(name)
        record.started_after_seconds = self.elapsed()
        try:
            yield record
        except BaseException:
            record.outcome = record.outcome or "RAISED"
            raise
        else:
            record.outcome = record.outcome or "COMPLETED"
        finally:
            record.elapsed_seconds = self.elapsed() - record.started_after_seconds

    def record(self, name: str, *, started_after: float, elapsed: float) -> None:
        """A stage the caller timed itself (intake ran before the budget existed)."""

        record = self._open(name)
        record.started_after_seconds, record.elapsed_seconds = started_after, max(0.0, elapsed)
        record.outcome = record.outcome or "COMPLETED"

    def allowance(self, name: str, *, default: float, share: float = 1.0,
                  minimum: float = 0.0, name_skip: bool = True) -> float | None:
        """`min(default, share x the improvement window)`, or None when under `minimum`.

        A value below `default` is a shortened construction budget and is named
        once per stage; None means the stage is skipped, named the same way
        unless the caller names the stop itself (`name_skip=False`).
        """

        window = 0.0 if self.passed_at_start else self.improvement_remaining()
        value = min(float(default), share * window)
        record = self._open(name)
        record.default_seconds = float(default)
        if value < minimum or value <= 0:
            record.outcome = "SKIPPED"
            if name_skip:
                self._shortened(name, f"{name}: {max(0.0, window):.1f} s left in the improvement"
                                      f" window, under its {minimum:g} s minimum; skipped")
            return None
        record.allowance_seconds = value
        if value < default:
            self._shortened(name, f"{name}: {value:.1f} s instead of its {default:g} s default")
        return value

    def _shortened(self, name: str, detail: str) -> None:
        if not any(text.startswith(f"{name}:") for code, text in self.events
                   if code == "DEADLINE_STAGE_SHORTENED"):
            self._limitation_event("DEADLINE_STAGE_SHORTENED", detail)

    def _limitation_event(self, code: str, detail: str) -> str:
        self.events.append((code, detail))
        return f"{code}:{detail}"

    # -- what each stage asks -----------------------------------------------

    def baseline_limits(self) -> tuple[float, float]:
        """(per-solve, total) seconds for the baseline: never below the floor."""

        total = min(BASELINE_CAP_SECONDS, max(BASELINE_FLOOR_SECONDS, self.remaining()))
        record = self._open("baseline")
        record.default_seconds, record.allowance_seconds = BASELINE_CAP_SECONDS, total
        if total < BASELINE_CAP_SECONDS:
            self._shortened("baseline", f"baseline: {total:.1f} s instead of its"
                                        f" {BASELINE_CAP_SECONDS:g} s default")
        return min(BASELINE_PER_SOLVE_SECONDS, total), total

    def review_gate(self) -> str | None:
        """The text that stops the run's own review before it starts, or None."""

        if self.passed_at_start:
            self._open("review").outcome = "SKIPPED"
            return next(f"{code}:{detail}" for code, detail in self.events
                        if code == "DEADLINE_PASSED_AT_START")
        if self.improvement_remaining() <= 0:
            self._open("review").outcome = "SKIPPED"
            return self._limitation_event(
                "DEADLINE_IMPROVEMENT_WINDOW_SPENT",
                f"review: the improvement window closed at {self.improvement_stop.isoformat()}"
                " before the run's own review could start; the baseline is the deliverable")
        return None

    def sequential_solve_seconds(self, *, count: int, default: float) -> tuple[float | None, str | None]:
        """C1's per-solve limit: `count` solves in the window, never above `default`."""

        per_solve = self.allowance("selection", default=default, share=1.0 / max(1, count + 1),
                                   minimum=SOLVE_MINIMUM_SECONDS, name_skip=False)
        if per_solve is None:
            return None, self._selection_spent(f"{count} sequential solves")
        return per_solve, None

    def policy_search_seconds(
        self, *, bank_default: float, joint_default: float, per_solve_default: float
    ) -> tuple[tuple[float, float, float] | None, str | None]:
        """(bank, per-solve, joint) seconds for a candidate bank and its joint solve."""

        bank = self.allowance("selection", default=bank_default, share=BANK_SHARE,
                              minimum=SOLVE_MINIMUM_SECONDS, name_skip=False)
        if bank is None:
            return None, self._selection_spent("a candidate bank")
        joint = min(joint_default, JOINT_SHARE * max(0.0, self.improvement_remaining()))
        if joint < SOLVE_MINIMUM_SECONDS:
            return None, self._selection_spent("a joint solve")
        if joint < joint_default:
            self._shortened("joint_selection", f"joint_selection: {joint:.1f} s instead of its"
                                               f" {joint_default:g} s default")
        return (bank, min(per_solve_default, bank), joint), None

    def fits_declared_search(self, *, declared_seconds: float) -> str | None:
        """A hash-bound policy's own search limits either fit the window or stop the review."""

        window = max(0.0, self.improvement_remaining())
        record = self._open("selection")
        record.default_seconds = record.allowance_seconds = float(declared_seconds)
        if declared_seconds <= window:
            return None
        record.outcome = "SKIPPED"
        return self._limitation_event(
            "DEADLINE_POLICY_SEARCH_EXCEEDS_WINDOW",
            f"the policy's bank and joint-solve limits total {declared_seconds:.1f} s and"
            f" {window:.1f} s are left before {self.improvement_stop.isoformat()}; its limits are"
            " hash-bound, so regenerate it with a smaller make_classic_policy.py --minutes, or"
            " take rung 4 (no --portfolio-policy-json); the baseline is the deliverable")

    def finished_late(self, stage: str) -> None:
        """Name a stage that ended after the delivery deadline (it ran; it was late)."""

        late = -self.remaining()
        if late > 0:
            self._limitation_event(
                "DEADLINE_PASSED_DURING_REVIEW",
                f"{stage}: ended {late:.1f} s after the delivery deadline {self.deadline.isoformat()};"
                " whatever file it delivered is late, and the baseline was on the pointer before it")

    def _selection_spent(self, what: str) -> str:
        return self._limitation_event(
            "DEADLINE_IMPROVEMENT_WINDOW_SPENT",
            f"selection: {max(0.0, self.improvement_remaining()):.1f} s left before"
            f" {self.improvement_stop.isoformat()} is too little for {what}; the review stopped"
            " before selection and the baseline is the deliverable")

    # -- reporting ----------------------------------------------------------

    def blocker_texts(self) -> list[str]:
        return [f"{code}:{detail}" for code, detail in self.events]

    def limitations(self, registry: GateRegistry) -> tuple[DeliveryLimitation, ...]:
        # The detail is the whole `CODE:detail` text, as `delivery.blocker_limitations`
        # builds it from the same text in the run's blockers.
        return tuple(registry.limitation(code, detail=f"{code}:{detail}") for code, detail in self.events)

    def as_record(self) -> dict[str, object]:
        return {
            "schema_version": CONTRACT_VERSION,
            "deadline_utc": self.deadline.isoformat(),
            "deadline_source": self.deadline_source,
            "earliest_lock_utc": self.lock.isoformat(),
            "handoff_reserve_seconds": HANDOFF_RESERVE.total_seconds(),
            "stop_discretionary_optimization_minutes_before_lock": self.stop_minutes,
            "finish_reserve_seconds": self.reserve.total_seconds(),
            "improvement_stop_utc": self.improvement_stop.isoformat(),
            "clock": {
                "deadline_against": "PINNED_AS_OF" if self.pinned else "WALL_CLOCK",
                "started_utc": self.started.isoformat(),
                "wall_started_utc": self.wall_started.isoformat(),
                "elapsed": "MONOTONIC",
            },
            "passed_at_start": self.passed_at_start,
            "seconds_to_deadline_at_start": round((self.deadline - self.started).total_seconds(), 3),
            "elapsed_seconds": round(self.elapsed(), 3),
            "stages": [record.as_record() for record in self.stages],
            "limitations": [code for code, _detail in self.events],
            "candidate_rate": self.candidate_rate,
            "does_not_establish": list(DOES_NOT_ESTABLISH),
        }


# -- the per-host candidate rate ---------------------------------------------

def host_key() -> str:
    """This machine, as far as a candidate rate depends on it."""

    return "|".join((platform.node() or "unknown", platform.system(), platform.machine(),
                     f"cpus={os.cpu_count()}"))


def bank_rate_observation(
    reports: Mapping[str, object], blockers: Iterable[str], *, declared_bank_seconds: float | None
) -> tuple[int, float, str] | None:
    """(candidates, seconds, basis) from a Classic C2 bank, or None.

    A finished bank reports its own count and elapsed time. A bank stopped by its
    time limit reports only its count; it ran for its declared budget.
    """

    selection = reports.get("selection") if isinstance(reports, Mapping) else None
    selector = selection.get("selection") if isinstance(selection, Mapping) else None
    policy = selector.get("portfolio_policy") if isinstance(selector, Mapping) else None
    bank = policy.get("candidate_bank") if isinstance(policy, Mapping) else None
    if isinstance(bank, Mapping):
        produced, elapsed = bank.get("produced_candidates"), bank.get("elapsed_seconds")
        if isinstance(produced, int) and produced > 0 and isinstance(elapsed, (int, float)):
            return produced, float(elapsed), "BANK_REPORT"
    for text in blockers:
        if "CANDIDATE_BANK_TIMEOUT" in str(text) and declared_bank_seconds:
            found = re.search(r"candidates=(\d+)", str(text))
            if found and int(found.group(1)) > 0:
                return int(found.group(1)), float(declared_bank_seconds), "BANK_TIME_LIMIT"
    return None


def record_candidate_rate(
    path: str | Path, *, mode: str, candidates: int, seconds: float, basis: str,
    run_id: str, measured_at: datetime, pool_people: int, entries: int,
) -> dict[str, object]:
    """Append one observation for this host and mode; return what was written."""

    target = Path(path)
    ledger = _read_ledger(target)
    observation = {
        "seconds_per_candidate": round(seconds / candidates, 6),
        "candidates": candidates,
        "elapsed_seconds": round(seconds, 3),
        "basis": basis,
        "pool_people": pool_people,
        "entries": entries,
        "run_id": run_id,
        "measured_at": measured_at.astimezone(timezone.utc).isoformat(),
    }
    key = f"{host_key()}|{mode}"
    kept = [*ledger["hosts"].get(key, []), observation][-RATE_OBSERVATIONS_KEPT:]
    ledger["hosts"][key] = kept
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    temporary.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(target)
    return {"ledger": str(target), "host": key, **observation}


def read_candidate_rate(path: str | Path, *, mode: str) -> dict[str, object] | None:
    """The slowest of this host's last few rates for `mode`, or None when it has none."""

    try:
        kept = _read_ledger(Path(path))["hosts"].get(f"{host_key()}|{mode}", [])
    except ValueError:
        return None
    recent = [item for item in kept[-RATE_OBSERVATIONS_READ:]
              if isinstance(item, dict) and isinstance(item.get("seconds_per_candidate"), (int, float))]
    if not recent:
        return None
    slowest = max(recent, key=lambda item: item["seconds_per_candidate"])
    return {"seconds_per_candidate": float(slowest["seconds_per_candidate"]),
            "observations": len(recent), "measured_at": slowest.get("measured_at"),
            "run_id": slowest.get("run_id")}


def _read_ledger(path: Path) -> dict[str, object]:
    """The ledger, or a new one when none exists; anything else there is refused, never overwritten."""

    if not path.exists():
        return {"schema_version": RATE_LEDGER_VERSION, "hosts": {}}
    try:
        ledger = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"{path} is not a readable {RATE_LEDGER_VERSION} ledger: {exc}") from exc
    hosts = ledger.get("hosts") if isinstance(ledger, dict) else None
    if (not isinstance(ledger, dict) or ledger.get("schema_version") != RATE_LEDGER_VERSION
            or not isinstance(hosts, dict) or not all(isinstance(kept, list) for kept in hosts.values())):
        raise ValueError(f"{path} is not a {RATE_LEDGER_VERSION} ledger; it is left as it is")
    return ledger
