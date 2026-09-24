"""Session 07: the deadline controller (R31).

One `Budget`, built right after intake, gives every `run-slate` stage its time:
the baseline (never below its floor), the session probe and the review's
solver limits. When the window is spent the improvement stops and the baseline
stays the deliverable, named by a registered limitation, never a silent
timeout. Evidence fetches and the policy generator are Session 07b's.

Every clock here is pinned or injected, a slow stage is a stub that moves the
injected clock, and no test opens a socket.
"""

from __future__ import annotations

import inspect
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from nfl_dfs import deadline
from nfl_dfs.contracts import GateClass
from nfl_dfs.deadline import (
    BASELINE_CAP_SECONDS,
    BASELINE_FLOOR_SECONDS,
    HANDOFF_RESERVE,
    Budget,
    bank_rate_observation,
    default_deadline,
    earliest_lock,
    finish_reserve,
    read_candidate_rate,
    record_candidate_rate,
    runtime_stop_minutes,
)
from nfl_dfs.dk import parse_salaries
from nfl_dfs.gate_registry import load_gate_registry

from .test_classic_prior_review import AS_OF
from .test_classic_prior_review import _fixture as classic_fixture
from .test_prior_review_profile import _attachments, _cowork_args

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "tests" / "fixtures" / "supplied"
CLASSIC_SALARY = FIXTURES / "DKSalaries Salary CSV Classic.csv"
SHOWDOWN_SALARY = FIXTURES / "DKSalaries Salary CSV Showdown.csv"
CLASSIC_LOCK = datetime(2026, 9, 13, 17, 0, tzinfo=timezone.utc)  # ATL@PIT and ten more, 1:00 PM ET
SHOWDOWN_LOCK = datetime(2026, 9, 10, 0, 20, tzinfo=timezone.utc)  # NE@SEA, 8:20 PM ET
DEADLINE_CODES = (
    "DEADLINE_PASSED_AT_START", "DEADLINE_IMPROVEMENT_WINDOW_SPENT",
    "DEADLINE_POLICY_SEARCH_EXCEEDS_WINDOW", "DEADLINE_STAGE_SHORTENED", "DEADLINE_AFTER_EARLIEST_LOCK", "DEADLINE_WALL_CLOCK_PAST_DEADLINE",
)


class FakeClock:
    """A monotonic clock that moves only when a test says so."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _budget(clock: FakeClock, *, as_of: datetime, requested: str | None = None, games=None) -> Budget:
    return Budget.build(
        games if games is not None else parse_salaries(CLASSIC_SALARY).games,
        requested_deadline=requested, as_of=as_of, clock=clock,
        wall=lambda: as_of,  # the wall clock agrees with the pinned one unless a test says not
    )


# ----------------------------------------------------------------- the deadline


def test_the_default_deadline_is_the_earliest_lock_minus_five_minutes():
    classic = parse_salaries(CLASSIC_SALARY)
    assert len(classic.games) == 12
    assert earliest_lock(classic.games) == CLASSIC_LOCK  # the earliest kickoff, not the latest
    assert default_deadline(classic.games) == CLASSIC_LOCK - timedelta(minutes=5)
    showdown = parse_salaries(SHOWDOWN_SALARY)
    assert default_deadline(showdown.games) == SHOWDOWN_LOCK - HANDOFF_RESERVE
    assert HANDOFF_RESERVE == timedelta(minutes=5)  # R31

    budget = _budget(FakeClock(), as_of=CLASSIC_LOCK - timedelta(hours=2))
    assert budget.deadline == CLASSIC_LOCK - timedelta(minutes=5)
    assert budget.deadline_source == "DEFAULT_EARLIEST_LOCK_MINUS_R31"
    # Discretionary optimization stops at lock minus 10; delivery is due at lock minus 5.
    assert budget.improvement_stop == CLASSIC_LOCK - timedelta(minutes=10)
    assert budget.remaining() == pytest.approx(115 * 60)
    assert budget.improvement_remaining() == pytest.approx(110 * 60)
    assert budget.events == []


def test_the_runtime_key_is_consumed_and_the_dead_one_removed():
    runtime = json.loads((REPO / "config" / "runtime.json").read_text(encoding="utf-8"))
    assert runtime_stop_minutes(runtime) == 10.0
    assert finish_reserve(10) == timedelta(minutes=5)
    for mode in ("classic", "showdown"):
        assert "full_refresh_seconds" not in runtime[mode]
    with pytest.raises(ValueError, match="at least R31's 5 minutes"):
        finish_reserve(4)  # a stop inside the handoff reserve would deliver late
    with pytest.raises(ValueError):
        runtime_stop_minutes({"stop_discretionary_optimization_minutes_before_lock": "10"})


def test_an_explicit_deadline_wins_and_one_after_lock_is_named():
    as_of = CLASSIC_LOCK - timedelta(hours=1)
    early = _budget(FakeClock(), as_of=as_of, requested="2026-09-13T12:30:00-04:00")
    assert early.deadline == datetime(2026, 9, 13, 16, 30, tzinfo=timezone.utc)
    assert early.deadline_source == "REQUEST" and early.events == []

    late = _budget(FakeClock(), as_of=as_of, requested="2026-09-13T17:30:00Z")
    assert late.deadline == CLASSIC_LOCK + timedelta(minutes=30)  # authoritative, not clamped
    assert [code for code, _ in late.events] == ["DEADLINE_AFTER_EARLIEST_LOCK"]
    with pytest.raises(ValueError, match="no UTC offset"):
        _budget(FakeClock(), as_of=as_of, requested="2026-09-13T12:30:00")


def test_elapsed_time_is_monotonic_and_a_pinned_clock_is_the_deadline_clock():
    clock = FakeClock()
    pinned = CLASSIC_LOCK - timedelta(minutes=30)
    wall = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)
    budget = Budget.build(parse_salaries(CLASSIC_SALARY).games, as_of=pinned, clock=clock,
                          wall=lambda: wall)
    assert budget.remaining() == pytest.approx(25 * 60)  # against the pinned moment, not the wall
    clock.advance(90)
    assert budget.now() == pinned + timedelta(seconds=90)
    assert budget.remaining() == pytest.approx(25 * 60 - 90)
    record = budget.as_record()
    assert record["clock"] == {
        "deadline_against": "PINNED_AS_OF", "started_utc": pinned.isoformat(),
        "wall_started_utc": wall.isoformat(), "elapsed": "MONOTONIC",
    }
    # The wall clock is only recorded, and named when it says this is a replay.
    assert [code for code, _ in budget.events] == ["DEADLINE_WALL_CLOCK_PAST_DEADLINE"]


# ----------------------------------------------------------------- the stages


def test_the_baseline_never_goes_below_its_floor():
    plenty = _budget(FakeClock(), as_of=CLASSIC_LOCK - timedelta(hours=3))
    assert plenty.baseline_limits() == (5.0, BASELINE_CAP_SECONDS)
    assert plenty.events == []

    close = _budget(FakeClock(), as_of=CLASSIC_LOCK - timedelta(minutes=5, seconds=45))
    assert close.baseline_limits() == (5.0, 45.0)

    passed = _budget(FakeClock(), as_of=CLASSIC_LOCK + timedelta(hours=1))
    assert passed.passed_at_start
    assert passed.baseline_limits() == (5.0, BASELINE_FLOOR_SECONDS)  # a late file beats none
    codes = [code for code, _ in passed.events]
    assert codes == ["DEADLINE_PASSED_AT_START", "DEADLINE_STAGE_SHORTENED"]
    assert passed.review_gate().startswith("DEADLINE_PASSED_AT_START:")


def test_allowances_shorten_then_skip_and_each_is_named_once():
    clock = FakeClock()
    budget = _budget(clock, as_of=CLASSIC_LOCK - timedelta(minutes=10, seconds=100))  # 100 s window
    assert budget.allowance("session_probe", default=45, share=0.10, minimum=3) == pytest.approx(10.0)
    assert budget.allowance("a_stage", default=30) == 30.0
    clock.advance(80)
    assert budget.allowance("a_stage", default=30) == pytest.approx(20.0)
    assert budget.allowance("a_stage", default=30) == pytest.approx(20.0)
    clock.advance(20)
    assert budget.allowance("a_stage", default=30, minimum=1) is None
    shortened = [detail for code, detail in budget.events if code == "DEADLINE_STAGE_SHORTENED"]
    assert [detail.split(":")[0] for detail in shortened] == ["session_probe", "a_stage"]
    assert budget.review_gate().startswith("DEADLINE_IMPROVEMENT_WINDOW_SPENT:review:")
    stages = [(item["name"], item["outcome"]) for item in budget.as_record()["stages"]]
    assert ("a_stage", "SKIPPED") in stages and ("review", "SKIPPED") in stages


def test_selection_limits_come_from_the_window():
    clock = FakeClock()
    budget = _budget(clock, as_of=CLASSIC_LOCK - timedelta(minutes=10, seconds=30))  # 30 s window
    per_solve, stopped = budget.sequential_solve_seconds(count=2, default=10.0)
    assert (per_solve, stopped) == (pytest.approx(10.0), None)
    per_solve, _ = budget.sequential_solve_seconds(count=5, default=10.0)
    assert per_solve == pytest.approx(5.0)  # six solves' worth in 30 s
    seconds, stopped = budget.policy_search_seconds(bank_default=40, joint_default=10, per_solve_default=2)
    assert stopped is None and seconds == (pytest.approx(21.0), 2, pytest.approx(6.0))
    assert budget.fits_declared_search(declared_seconds=25) is None
    assert budget.fits_declared_search(declared_seconds=40).startswith("DEADLINE_POLICY_SEARCH_EXCEEDS_WINDOW:")
    clock.advance(29.9)
    per_solve, stopped = budget.sequential_solve_seconds(count=1, default=10.0)
    assert per_solve is None and stopped.startswith("DEADLINE_IMPROVEMENT_WINDOW_SPENT:selection:")


def test_the_c1_default_matches_select_prior_lineups():
    from nfl_dfs.prior_review import SEQUENTIAL_PER_SOLVE_SECONDS
    from nfl_dfs.selection import select_prior_lineups

    default = inspect.signature(select_prior_lineups).parameters["time_limit_seconds"].default
    assert SEQUENTIAL_PER_SOLVE_SECONDS == default


def test_no_deadline_code_can_withhold_a_file():
    registry = load_gate_registry()
    classes = {code: registry.family_of(code).gate_class for code in DEADLINE_CODES}
    assert GateClass.V not in classes.values()
    assert {code for code, value in classes.items() if value is GateClass.P} == {
        "DEADLINE_AFTER_EARLIEST_LOCK", "DEADLINE_WALL_CLOCK_PAST_DEADLINE"}
    family = registry.family_of("DEADLINE_STAGE_SHORTENED")
    assert (family.name, family.provenance.ref) == ("delivery_deadline", "R31")
    budget = _budget(FakeClock(), as_of=CLASSIC_LOCK + timedelta(hours=1))
    budget.baseline_limits()
    assert all(item.gate_class is not GateClass.V for item in budget.limitations(registry))


# ----------------------------------------------------------------- the host rate


def test_the_host_candidate_rate_is_recorded_and_read_back_conservatively(tmp_path):
    ledger = tmp_path / "runs" / "host_candidate_rates.json"
    assert read_candidate_rate(ledger, mode="CLASSIC") is None
    moment = datetime(2026, 9, 24, 12, tzinfo=timezone.utc)
    for index, (candidates, seconds) in enumerate(((100, 30.0), (82, 480.0), (1000, 280.0))):
        written = record_candidate_rate(
            ledger, mode="CLASSIC", candidates=candidates, seconds=seconds, basis="BANK_REPORT",
            run_id=f"run-{index}", measured_at=moment, pool_people=719, entries=20)
    assert written["seconds_per_candidate"] == 0.28
    rate = read_candidate_rate(ledger, mode="CLASSIC")
    assert rate["seconds_per_candidate"] == pytest.approx(480.0 / 82)  # the slowest of the last five
    assert rate["observations"] == 3 and rate["run_id"] == "run-1"
    assert read_candidate_rate(ledger, mode="SHOWDOWN") is None
    stored = json.loads(ledger.read_text(encoding="utf-8"))
    assert stored["schema_version"] == "nfl_host_candidate_rate_v1"
    assert list(stored["hosts"]) == [f"{deadline.host_key()}|CLASSIC"]


def test_a_bank_rate_is_read_from_its_report_or_from_a_bank_time_limit():
    report = {"selection": {"selection": {"portfolio_policy": {
        "candidate_bank": {"produced_candidates": 50, "elapsed_seconds": 14.0}}}}}
    assert bank_rate_observation(report, (), declared_bank_seconds=60.0) == (50, 14.0, "BANK_REPORT")
    timed_out = ("SELECTION_FAILED:SelectionError:CANDIDATE_BANK_TIMEOUT:model_status=kTimeLimit:"
                 "candidates=82:requested=642",)
    assert bank_rate_observation({}, timed_out, declared_bank_seconds=480.0) == (
        82, 480.0, "BANK_TIME_LIMIT")
    assert bank_rate_observation({}, ("SELECTION_FAILED:other",), declared_bank_seconds=480.0) is None


# ----------------------------------------------------------------- run-slate


def _clocked(monkeypatch, clock: FakeClock):
    """`run-slate`'s budget on the fake monotonic clock."""

    from nfl_dfs import cli

    build = Budget.build.__func__

    class Clocked(Budget):
        @classmethod
        def build(cls, games, **kwargs):
            return build(cls, games, clock=clock, **kwargs)

    monkeypatch.setattr(cli, "Budget", Clocked)


def _classic(tmp_path, monkeypatch, *, run_id, deadline=None, as_of=AS_OF, policy=None, review=None):
    from nfl_dfs import cli

    salary, entry, package, role, status, _ = classic_fixture(tmp_path / "fixture", entries=1)
    attachments = _attachments(tmp_path, salary, entry)
    monkeypatch.setattr(cli, "DEFAULT_RUNS_DIR", tmp_path / "runs")
    if review is not None:
        monkeypatch.setattr(cli, "run_prior_review", review)
    overrides = {"portfolio_policy_json": str(policy(attachments))} if policy else {}
    code = cli.command_cowork_run(_cowork_args(
        tmp_path, attachments, label=run_id, run_id=run_id, prior_package_dir=str(package),
        official_status_csv=str(status), offensive_role_evidence_json=str(role),
        as_of=as_of.isoformat(), delivery_deadline_utc=deadline, **overrides))
    root = tmp_path / "outputs" / run_id
    return code, json.loads((root / "cowork_run.json").read_text(encoding="utf-8")), root


def _truth_codes(report) -> dict[str, str]:
    return {item["code"]: item["class"] for item in report["release_truths"]["delivery_limitations"]}


def _baseline_is_the_file(report, root):
    from nfl_dfs import delivery

    latest = delivery.read_latest(root)
    assert latest is not None and latest.deliverable.producer == "run-slate:baseline"
    assert report["DELIVERY_STATE"] == "DELIVERABLE"
    assert report["latest_deliverable"]["producer"] == "run-slate:baseline"
    assert report["RELEASE_DECISION"] == "DO_NOT_UPLOAD"
    assert "V" not in _truth_codes(report).values()


def test_a_deadline_passed_at_start_ships_the_baseline_and_skips_the_review(tmp_path, monkeypatch):
    def review(**_kwargs):  # pragma: no cover - reaching this is the failure
        raise AssertionError("the review must not start after the deadline")

    after_lock = CLASSIC_LOCK + timedelta(hours=1)
    code, report, root = _classic(tmp_path, monkeypatch, run_id="late", as_of=after_lock,
                                  review=review)
    assert code == 2  # the review did not complete (Session 06's meaning)
    assert report["stage"] == "DEADLINE_IMPROVEMENT_SKIPPED"
    _baseline_is_the_file(report, root)
    codes = _truth_codes(report)
    assert codes["DEADLINE_PASSED_AT_START"] == "S"
    assert codes["BASELINE_EARLIEST_LOCK_PASSED"] == "P"  # the lock is named too
    assert codes["IMPROVEMENT_NOT_DELIVERED"] == "P"
    assert report["improvement"]["reasons"][0].startswith("DEADLINE_PASSED_AT_START:")
    record = report["deadline"]
    assert record["schema_version"] == "nfl_deadline_budget_v1" and record["passed_at_start"]
    baseline_stage = next(item for item in record["stages"] if item["name"] == "baseline")
    assert baseline_stage["allowance_seconds"] == BASELINE_FLOOR_SECONDS
    assert report["baseline"]["DELIVERY_STATE"] == "DELIVERABLE"


def test_a_window_spent_before_selection_stops_the_review_and_keeps_the_baseline(tmp_path, monkeypatch):
    from nfl_dfs import prior_review as prior_review_module

    clock = FakeClock()
    _clocked(monkeypatch, clock)
    real = prior_review_module.run_prior_review

    def slow_review(**kwargs):
        clock.advance(6 * 60)  # priors and evidence take six minutes of a five-minute window
        return real(**kwargs)

    code, report, root = _classic(
        tmp_path, monkeypatch, run_id="spent", review=slow_review,
        deadline=(AS_OF + timedelta(minutes=10)).isoformat())
    assert code == 2
    assert report["stage"] == "PRIOR_REVIEW_SELECT_BLOCKED"
    _baseline_is_the_file(report, root)
    assert _truth_codes(report)["DEADLINE_IMPROVEMENT_WINDOW_SPENT"] == "S"
    assert report["blockers"][0].startswith("DEADLINE_IMPROVEMENT_WINDOW_SPENT:selection:")
    assert report["improvement"]["status"] == "NOT_PRODUCED"
    review_stage = next(item for item in report["deadline"]["stages"] if item["name"] == "review")
    assert review_stage["elapsed_seconds"] == 360.0


def test_a_short_window_shortens_c1_solves_and_the_review_still_delivers(tmp_path, monkeypatch):
    from nfl_dfs import prior_review as prior_review_module

    clock = FakeClock()
    _clocked(monkeypatch, clock)
    seen: dict[str, object] = {}
    real_select = prior_review_module.select_prior_lineups

    def select(*args, **kwargs):
        seen.update(kwargs)
        return real_select(*args, **kwargs)

    monkeypatch.setattr(prior_review_module, "select_prior_lineups", select)
    code, report, root = _classic(
        tmp_path, monkeypatch, run_id="short",
        deadline=(AS_OF + timedelta(minutes=5, seconds=12)).isoformat())  # a 12 s window
    assert seen["time_limit_seconds"] == pytest.approx(6.0)  # one lineup: two solves' worth
    assert code == 0 and report["improvement"]["status"] == "DELIVERED"
    codes = _truth_codes(report)
    assert codes["DEADLINE_STAGE_SHORTENED"] == "S"  # a shortened search budget is reported
    assert "IMPROVEMENT_NOT_DELIVERED" not in codes
    selection = next(item for item in report["deadline"]["stages"] if item["name"] == "selection")
    assert (selection["default_seconds"], selection["allowance_seconds"]) == (10.0, 6.0)


def _template_policy(attachments: Path) -> Path:
    from nfl_dfs.classic_portfolio_policy import classic_portfolio_policy_template
    from nfl_dfs.dk import parse_entries

    slate = parse_salaries(attachments / "salary.csv")
    entries = parse_entries(attachments / "entries.csv")
    path = attachments.parent / "classic_policy.json"
    path.write_text(json.dumps(classic_portfolio_policy_template(
        slate, tuple(item.entry_id for item in entries.authorizations), entry_sha256=entries.raw_hash,
    )), encoding="utf-8")
    return path


def test_a_c2_policy_whose_declared_search_does_not_fit_stops_the_review(tmp_path, monkeypatch):
    clock = FakeClock()
    _clocked(monkeypatch, clock)
    code, report, root = _classic(
        tmp_path, monkeypatch, run_id="c2-late", policy=_template_policy,
        deadline=(AS_OF + timedelta(minutes=5, seconds=20)).isoformat())  # 20 s; it declares 40
    assert code == 2
    _baseline_is_the_file(report, root)
    assert _truth_codes(report)["DEADLINE_POLICY_SEARCH_EXCEEDS_WINDOW"] == "S"
    assert report["blockers"][0].startswith("DEADLINE_POLICY_SEARCH_EXCEEDS_WINDOW:")


def test_a_replay_records_its_stages_its_request_v3_and_the_hosts_candidate_rate(tmp_path, monkeypatch):
    code, report, root = _classic(tmp_path, monkeypatch, run_id="measured", policy=_template_policy,
                                  deadline="2099-01-01T00:00:00+00:00")
    assert code == 0 and report["stage"] == "PRIOR_ONLY_CLASSIC_C3_REVIEW_EXPORT"
    record = report["deadline"]
    assert record["deadline_utc"] == "2099-01-01T00:00:00+00:00" and record["deadline_source"] == "REQUEST"
    names = [item["name"] for item in record["stages"]]
    assert names[:2] == ["intake", "baseline"] and names[-2:] == ["review", "finish"]
    assert "policy_validation" in names and "selection" in names
    assert all(item["elapsed_seconds"] is not None and item["elapsed_seconds"] >= 0
               for item in record["stages"] if item["outcome"] != "SKIPPED")
    assert _truth_codes(report)["DEADLINE_AFTER_EARLIEST_LOCK"] == "P"  # the replay says so
    request = json.loads((tmp_path / "runs" / "measured" / "run_request.json").read_text(encoding="utf-8"))
    assert request["schema_version"] == "nfl_cowork_run_request_v3"
    assert request["delivery_deadline_utc"] == "2099-01-01T00:00:00+00:00"
    # The C2 bank's measured rate, for this host, where make_classic_policy reads it.
    rate = record["candidate_rate"]
    assert rate["basis"] == "BANK_REPORT" and rate["seconds_per_candidate"] > 0
    ledger = tmp_path / "runs" / "host_candidate_rates.json"
    assert rate["ledger"] == str(ledger)
    assert read_candidate_rate(ledger, mode="CLASSIC")["seconds_per_candidate"] == rate["seconds_per_candidate"]


def test_the_outer_handler_carries_the_budget(tmp_path, monkeypatch):
    def crash(**_kwargs):
        raise RuntimeError("forced crash")

    code, report, root = _classic(tmp_path, monkeypatch, run_id="crashed", review=crash)
    assert code == 2 and report["stage"] == "BUILD_OR_CERTIFY_FAILED"
    assert report["deadline"]["schema_version"] == "nfl_deadline_budget_v1"
    # Pinned before lock, run after it: a replay, and the handler's truths say so.
    assert _truth_codes(report)["DEADLINE_WALL_CLOCK_PAST_DEADLINE"] == "P"
    _baseline_is_the_file(report, root)


def test_a_budget_that_cannot_be_built_still_ships_the_baseline_first(tmp_path, monkeypatch):
    from nfl_dfs import cli

    real_load = cli._load_config

    def load(name):
        value = real_load(name)
        if name == "runtime.json":
            value = {**value, "stop_discretionary_optimization_minutes_before_lock": 2}
        return value

    monkeypatch.setattr(cli, "_load_config", load)
    code, report, root = _classic(tmp_path, monkeypatch, run_id="bad-runtime")
    assert code == 2 and report["stage"] == "BUILD_OR_CERTIFY_FAILED"
    assert "at least R31's 5 minutes" in report["message"]
    assert report["deadline"] is None
    _baseline_is_the_file(report, root)
