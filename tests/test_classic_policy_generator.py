"""The generated C2 policy must validate, and its rungs must actually relax.

`scripts/make_classic_policy.py` exists because the registered template's
defaults are the worst configuration the engine supports: every stack rule ships
`ADVISORY` with `minimum_entries: 0`, which the solver does not enforce, and the
candidate bank defaults to `max(32, entries + 24)` out of a several-hundred-person
pool. These tests pin the two things that would silently undo that: a policy the
validator rejects, and a ladder whose rungs do not monotonically loosen.
"""

from __future__ import annotations

import importlib.util
import math
from pathlib import Path

import pytest

from nfl_dfs.classic_portfolio_policy import (
    classic_portfolio_policy_template,
    validate_classic_portfolio_policy_bytes,
)
from nfl_dfs.dk import parse_entries, parse_salaries

import json


def _generator():
    path = Path(__file__).resolve().parents[1] / "scripts" / "make_classic_policy.py"
    spec = importlib.util.spec_from_file_location("make_classic_policy", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "supplied"
SALARY = FIXTURES / "DKSalaries Salary CSV Classic.csv"
ENTRIES = FIXTURES / "DKEntries CSV.csv"


def _document(module, rung: int, entry_ids, slate, entry_sha256: str):
    count = len(entry_ids)
    controls: dict[str, object] = {
        "stack_rules": module._stack_rules(count, rung),
        "max_pairwise_person_overlap": min(module._overlap(rung), 8),
        "require_unique_lineups": True,
    }
    fraction = module._exposure_fraction(rung)
    if fraction is not None and count > 2:
        cap = max(1, math.ceil(fraction * count))
        controls["player_exposure_bounds"] = [
            {
                "underlying_id": row.underlying_id,
                "dk_id": row.dk_id,
                "minimum_entries": 0,
                "maximum_entries": cap,
                "hard": True,
            }
            for row in sorted(
                {row.underlying_id: row for row in slate.players}.values(),
                key=lambda row: row.underlying_id,
            )
        ]
    limits = module._limits(count, len(slate.players), rung, minutes=1.0)
    return classic_portfolio_policy_template(
        slate, entry_ids, entry_sha256=entry_sha256, controls=controls, limits=limits
    )


@pytest.mark.parametrize("rung", (0, 1, 2, 3))
def test_every_rung_produces_a_policy_the_validator_accepts(rung: int) -> None:
    module = _generator()
    slate = parse_salaries(SALARY)
    entries = parse_entries(ENTRIES)
    entry_ids = tuple(item.entry_id for item in entries.authorizations)
    document = _document(module, rung, entry_ids, slate, entries.raw_hash)
    raw = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")
    validation = validate_classic_portfolio_policy_bytes(
        raw, slate=slate, entry_ids=entry_ids, entry_sha256=entries.raw_hash
    )
    assert validation.valid and validation.policy is not None, validation.blockers()


def test_player_exposure_bounds_use_the_schema_key() -> None:
    """`person` reads naturally and the validator rejects it; `underlying_id` is the key."""

    module = _generator()
    slate = parse_salaries(SALARY)
    entries = parse_entries(ENTRIES)
    entry_ids = tuple(item.entry_id for item in entries.authorizations) * 8
    document = _document(module, 0, entry_ids, slate, entries.raw_hash)
    bounds = document["controls"].get("player_exposure_bounds")
    assert bounds, "a portfolio with more than two entries must cap player exposure"
    assert set(bounds[0]) == {
        "underlying_id",
        "dk_id",
        "minimum_entries",
        "maximum_entries",
        "hard",
    }


def test_the_ladder_only_ever_loosens() -> None:
    module = _generator()
    count = 20
    previous_overlap = 0
    previous_pass_catcher = count + 1
    for rung in (0, 1, 2, 3):
        rules = {rule["rule_id"]: rule for rule in module._stack_rules(count, rung)}
        overlap = module._overlap(rung)
        assert overlap >= previous_overlap, f"rung {rung} tightened overlap"
        pass_catcher = rules["qb-pass-catcher"]["minimum_entries"]
        assert pass_catcher <= previous_pass_catcher, f"rung {rung} tightened the stack"
        previous_overlap, previous_pass_catcher = overlap, pass_catcher
    # Rung 0 is the only rung that demands a bring-back on most entries.
    by_id = lambda rung: {rule["rule_id"]: rule for rule in module._stack_rules(count, rung)}
    assert by_id(0)["qb-bringback"]["minimum_entries"] == math.ceil(0.70 * count)
    assert by_id(0)["qb-bringback"]["strength"] == "HARD"
    assert by_id(2)["qb-bringback"]["strength"] == "ADVISORY"


def test_rung_zero_enforces_a_stack_on_every_entry() -> None:
    module = _generator()
    rules = {rule["rule_id"]: rule for rule in module._stack_rules(20, 0)}
    assert rules["qb-pass-catcher"]["strength"] == "HARD"
    assert rules["qb-pass-catcher"]["minimum_entries"] == 20


# ----------------------------------------------------------------- the lock clock (Session 07b)

from datetime import datetime, timedelta, timezone  # noqa: E402

from nfl_dfs.deadline import record_candidate_rate  # noqa: E402

CLASSIC_DEADLINE = datetime(2026, 9, 13, 16, 55, tzinfo=timezone.utc)  # the fixture's lock minus 5
IMPROVEMENT_STOP = CLASSIC_DEADLINE - timedelta(minutes=5)  # runtime.json's 10 before lock


def _declared(limits: dict[str, int]) -> float:
    return (limits["candidate_total_milliseconds"] + limits["selection_milliseconds"]) / 1000.0


def test_the_bank_fits_the_window_at_the_hosts_rate() -> None:
    """The card's case: 5 s per candidate fits 48 candidates in 700 s and none in 600 s."""

    module = _generator()
    limits = module._limits(24, 719, 0, minutes=4.0, seconds_per_candidate=5.0, window_seconds=700.0)
    assert limits["candidate_limit"] == 48  # the floor, max(32, 24 + 24), and --minutes 4 agree
    assert limits["candidate_total_milliseconds"] == 480_000  # 2x headroom at the host's rate
    assert limits["selection_milliseconds"] == 24_000
    assert _declared(limits) <= 0.75 * 700.0
    with pytest.raises(module.BankDoesNotFit, match="floor bank of 48 candidates at 5 s each"):
        module._limits(24, 719, 0, minutes=4.0, seconds_per_candidate=5.0, window_seconds=600.0)


def test_the_joint_solve_takes_at_most_a_fifth_of_the_window_and_the_bank_the_rest() -> None:
    module = _generator()
    limits = module._limits(150, 719, 0, minutes=60.0, seconds_per_candidate=1.0, window_seconds=700.0)
    assert limits["selection_milliseconds"] == 140_000  # 20% of 700 s, under its 150 s default
    assert limits["candidate_limit"] == (525 - 140) // 2 == 192  # the rest of 75%, at 2x headroom
    assert _declared(limits) <= 525.0
    # Rung 3 halves the bank; it never goes under the floor, max(32, 150 + 24).
    halved = module._limits(150, 719, 3, minutes=60.0, seconds_per_candidate=1.0, window_seconds=700.0)
    assert halved["candidate_limit"] == 174


def test_without_a_window_or_a_measured_rate_the_bank_is_what_it_was() -> None:
    module = _generator()
    before = {"candidate_limit": 857, "candidate_total_milliseconds": 479_920,
              "candidate_per_solve_milliseconds": 5_000, "selection_milliseconds": 20_000}
    assert module._limits(20, 719, 0, minutes=4.0) == before  # 0.28 s, --minutes 4
    assert module._limits(20, 719, 0, minutes=4.0, window_seconds=86_400.0) == before
    assert module.DEFAULT_SECONDS_PER_CANDIDATE == 0.28


def _ledger(tmp_path: Path, seconds_per_candidate: float) -> Path:
    ledger = tmp_path / "host_candidate_rates.json"
    record_candidate_rate(ledger, mode="CLASSIC", candidates=100, seconds=100 * seconds_per_candidate,
                          basis="BANK_REPORT", run_id="measured", measured_at=CLASSIC_DEADLINE,
                          pool_people=719, entries=2)
    return ledger


def _run(module, tmp_path: Path, *, window: float, extra: tuple[str, ...] = (), host_rates=None):
    out = tmp_path / "policy.json"
    argv = ["--salaries", str(SALARY), "--entries", str(ENTRIES), "--out", str(out),
            "--host-rates", str(host_rates or tmp_path / "absent.json"), *extra]
    code = module.main(argv, wall=lambda: IMPROVEMENT_STOP - timedelta(seconds=window))
    return code, out


def test_the_generator_reads_this_hosts_rate_and_writes_a_policy_that_fits(tmp_path, capsys) -> None:
    module = _generator()
    code, out = _run(module, tmp_path, window=700.0, host_rates=_ledger(tmp_path, 5.0))
    assert code == 0
    printed = capsys.readouterr().out
    assert "rate:              5 s per candidate (this host's slowest of its last 1 Classic banks" in printed
    assert "window:            700s before the improvement stops" in printed
    document = json.loads(out.read_text(encoding="utf-8"))
    limits = document["selection"]["limits"]
    assert limits["candidate_limit"] == 48 and _declared(limits) <= 0.75 * 700.0
    slate, entries = parse_salaries(SALARY), parse_entries(ENTRIES)
    validation = validate_classic_portfolio_policy_bytes(
        out.read_bytes(), slate=slate, entry_ids=tuple(item.entry_id for item in entries.authorizations),
        entry_sha256=entries.raw_hash)
    assert validation.valid, validation.blockers()


def test_no_rate_on_record_is_the_default_and_a_foreign_ledger_is_left_alone(tmp_path, capsys) -> None:
    module = _generator()
    foreign = tmp_path / "foreign.json"
    foreign.write_bytes(b"not a ledger")
    code, out = _run(module, tmp_path, window=86_400.0, host_rates=foreign)
    assert code == 0 and foreign.read_bytes() == b"not a ledger"
    assert "rate:              0.28 s per candidate (the default" in capsys.readouterr().out
    assert json.loads(out.read_text(encoding="utf-8"))["selection"]["limits"]["candidate_limit"] == 857


def test_when_even_the_floor_bank_does_not_fit_it_writes_nothing_and_names_rung_4(tmp_path, capsys) -> None:
    module = _generator()
    code, out = _run(module, tmp_path, window=400.0, host_rates=_ledger(tmp_path, 5.0))
    assert code == 2 and not out.exists()
    printed = capsys.readouterr().out
    assert "No policy written: even the floor bank of 32 candidates at 5 s each" in printed
    assert "Take rung 4: run-slate without --portfolio-policy-json" in printed


def test_a_closed_window_writes_nothing_and_says_the_baseline_is_the_file(tmp_path, capsys) -> None:
    module = _generator()
    code, out = _run(module, tmp_path, window=-60.0)  # a minute after the improvement stopped
    assert code == 2 and not out.exists()
    printed = capsys.readouterr().out
    assert f"the improvement window closed at {IMPROVEMENT_STOP.isoformat()}" in printed
    assert "hand over the baseline" in printed and "pass a later --delivery-deadline-utc" in printed
    # Past the deadline itself, too; a replay passes a later one and gets its bank.
    code, _ = _run(module, tmp_path, window=-3_600.0)
    assert code == 2
    code, out = _run(module, tmp_path, window=-3_600.0, extra=("--delivery-deadline-utc", "2099-01-01T00:00:00Z"))
    assert code == 0 and out.exists()


def test_the_stop_is_runtime_jsons_and_a_naive_deadline_is_refused(tmp_path, capsys, monkeypatch) -> None:
    module = _generator()
    runtime = json.loads((Path(__file__).resolve().parents[1] / "config" / "runtime.json").read_text(encoding="utf-8"))
    later = tmp_path / "runtime.json"
    later.write_text(json.dumps({**runtime, "stop_discretionary_optimization_minutes_before_lock": 15}),
                     encoding="utf-8")
    monkeypatch.setattr(module, "RUNTIME_JSON", later)
    code, _ = _run(module, tmp_path, window=700.0)  # 700 s before lock minus 10 is 400 s before lock minus 15
    assert code == 0
    printed = capsys.readouterr().out
    assert f"the improvement stops at {(CLASSIC_DEADLINE - timedelta(minutes=10)).isoformat()}" in printed
    assert "window:            400s" in printed
    with pytest.raises(SystemExit) as caught:
        _run(module, tmp_path, window=700.0, extra=("--delivery-deadline-utc", "2026-09-13T12:55:00"))
    assert caught.value.code == 2 and "has no UTC offset" in capsys.readouterr().err


def test_a_rate_no_bank_can_be_sized_from_is_refused() -> None:
    module = _generator()
    for bad in (0.0, -1.0, float("nan"), float("inf")):
        with pytest.raises(ValueError, match="finite number above zero"):
            module._limits(20, 719, 0, minutes=4.0, seconds_per_candidate=bad, window_seconds=700.0)


def test_a_deadline_after_lock_is_warned_and_a_bad_runtime_json_is_not_blamed_on_the_flag(
        tmp_path, capsys, monkeypatch) -> None:
    module = _generator()
    code, _ = _run(module, tmp_path, window=700.0, extra=("--delivery-deadline-utc", "2026-09-13T17:30:00Z"))
    assert code == 0
    assert "WARNING DEADLINE_AFTER_EARLIEST_LOCK: the request's delivery deadline" in capsys.readouterr().out
    broken = tmp_path / "runtime.json"
    broken.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(module, "RUNTIME_JSON", broken)
    with pytest.raises(json.JSONDecodeError):  # its own traceback, not an exit 2 naming the flag
        _run(module, tmp_path, window=700.0)


def test_a_generated_policy_leaves_run_slate_a_quarter_of_the_window_before_selection() -> None:
    """The 75% share against `run-slate`'s own check: 25% of the window covers intake to selection."""

    from nfl_dfs.deadline import Budget

    module = _generator()
    limits = module._limits(24, 719, 0, minutes=4.0, seconds_per_candidate=5.0, window_seconds=700.0)
    declared = _declared(limits)  # 504 s of a 700 s window
    generated_at = IMPROVEMENT_STOP - timedelta(seconds=700)
    games = parse_salaries(SALARY).games
    for later, fits in ((0, True), (196, True), (197, False)):
        budget = Budget.build(games, as_of=generated_at + timedelta(seconds=later), clock=lambda: 0.0,
                              wall=lambda: generated_at)
        stopped = budget.fits_declared_search(declared_seconds=declared)
        assert (stopped is None) is fits, (later, stopped)
