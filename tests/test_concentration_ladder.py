"""Session 56 (R35, review F-02): the relaxation ladder and the concentration defaults.

The engine default (0.60 a person, 0.20 a Captain, overlap 4; `Ladder.begin_with_defaults`)
and a generator policy at the same pair both give their caps way first, 0.80 and 0.40 and
(for a policy) then none, before any structural rung. The engine's own default has no
uncapped joint solve: its off is rung 4. A relaxed cap is carried forward, never reapplied,
and a value the operator set is theirs. Each step is recorded under
`SHOWDOWN_CONCENTRATION_RELAXED` (class `S`); evidence gates are not on this ladder.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from nfl_dfs.concentration import load_concentration_defaults
from nfl_dfs.dk import parse_entries, parse_salaries
from nfl_dfs.gate_registry import load_gate_registry
from nfl_dfs.hashing import sha256_bytes
from nfl_dfs.portfolio_policy import OPEN_STRUCTURAL_BOUNDS, validate_portfolio_policy_bytes
from nfl_dfs.relaxation import (
    Failure,
    Ladder,
    Rung,
    STRUCTURE,
    THROUGHPUT,
    concentration_state,
    showdown_relaxed_controls,
    supplied_rung,
)

from .test_concentration_defaults import SUPPLIED, _generate

NOW = datetime(2026, 10, 4, 15, 0, tzinfo=timezone.utc)
STRUCTURE_FAILURE = Failure("MODELED_BANK_INFEASIBLE_PROVEN", STRUCTURE, "the joint solve is infeasible")


class _Window:
    """A budget stub: a fixed improvement window, for the ladder's window arithmetic."""

    passed_at_start = False

    def __init__(self, seconds: float) -> None:
        self.seconds = seconds

    def improvement_remaining(self) -> float:
        return self.seconds

    def elapsed(self) -> float:
        return 0.0

    def now(self):
        return NOW


def _supplied_world():
    slate = parse_salaries(SUPPLIED / "DKSalaries Salary CSV Showdown.csv")
    entries = parse_entries(SUPPLIED / "DKEntries CSV 20 entries.csv")
    return slate, entries, tuple(item.entry_id for item in entries.authorizations)


def _ladder(tmp_path, *, budget=None, supplied=None, world=None):
    slate, entries, _ids = world or _supplied_world()
    return Ladder(slate=slate, entries=entries, folder=tmp_path / "relaxation", registry=load_gate_registry(),
                  supplied=supplied or Rung(None, None, engine_default=True, concentration=0), budget=budget)


def _fractions(rung):
    return rung.policy.combined_rule.default_fraction, rung.policy.captain_rule.default_fraction


def test_the_engine_default_is_the_registered_pair_with_open_structure_and_every_fillable_row(tmp_path):
    _slate, _entries, entry_ids = _supplied_world()
    ladder = _ladder(tmp_path)
    rung = ladder.begin_with_defaults()
    assert rung.label == "DEFAULT" and rung.engine_default and rung.concentration == 0 and rung.rung is None
    policy = rung.policy
    assert _fractions(rung) == (Decimal("0.6"), Decimal("0.2"))
    assert policy.max_pairwise_person_overlap == 4 and policy.require_unique_lineups
    assert policy.entry_ids == entry_ids
    assert not policy.combined_rule.overrides and not policy.captain_rule.overrides and not policy.excluded_people
    assert policy.structural_bounds == OPEN_STRUCTURAL_BOUNDS
    source = Path(rung.source_path)
    assert sha256_bytes(source.read_bytes()) == rung.source_sha256
    assert source.parent.name == "attempt_0_rung_DEFAULT" and Path(rung.normalized_path).is_file()
    assert ladder.records == [] and ladder.started_from is rung
    assert ladder.as_record()["started_from"]["rung"] == "DEFAULT"
    # The request's own overlap wins over the registered one.
    other = _ladder(tmp_path / "other").begin_with_defaults(overlap=3)
    assert other.policy.max_pairwise_person_overlap == 3


def test_a_structural_failure_walks_the_default_to_080_040_then_to_rung_4_and_names_each_step(tmp_path):
    ladder = _ladder(tmp_path)
    ladder.begin_with_defaults()
    step = ladder.next(STRUCTURE_FAILURE)
    assert step.label == "CAPS_0_80_0_40" and step.rung is None and step.concentration == 1 and step.engine_default
    assert _fractions(step) == (Decimal("0.8"), Decimal("0.4"))
    assert step.policy.max_pairwise_person_overlap == 4 and step.policy.structural_bounds == OPEN_STRUCTURAL_BOUNDS
    # The two fractions are one preference: one record, one limitation.
    (record,) = ladder.records
    assert record["constraint"] == "concentration_defaults"
    assert record["original"] == {"person_fraction": "0.6", "captain_fraction": "0.2"}
    assert record["final"] == {"person_fraction": "0.8", "captain_fraction": "0.4"}
    assert record["step"] == "CONCENTRATION" and record["class"] == "S"
    assert record["limitation_code"] == "SHOWDOWN_CONCENTRATION_RELAXED"
    assert (record["rung_from"], record["rung_to"]) == ("DEFAULT", "CAPS_0_80_0_40")
    floor = ladder.next(STRUCTURE_FAILURE)
    assert floor.rung == 4 and floor.policy is None
    ended = ladder.records[1:]
    assert [r["constraint"] for r in ended] == ["concentration_defaults", "portfolio_policy"]
    assert [r["limitation_code"] for r in ended] == ["SHOWDOWN_CONCENTRATION_RELAXED", "RELAXATION_POLICY_DROPPED"]
    assert ended[0]["original"] == {"person_fraction": "0.8", "captain_fraction": "0.4"}
    # No structural rung and no uncapped joint solve is ever taken for the engine default.
    assert {r["rung_to"] for r in ladder.records} == {"CAPS_0_80_0_40", "4"}
    assert ladder.next(STRUCTURE_FAILURE) is None  # rung 4 is the floor
    assert sum("SHOWDOWN_CONCENTRATION_RELAXED" in text for text in ladder.texts()) == 2


def test_a_bank_step_carries_the_relaxed_caps_forward_instead_of_reapplying_the_defaults(tmp_path):
    ladder = _ladder(tmp_path)
    ladder.begin_with_defaults()
    step = ladder.next(STRUCTURE_FAILURE)
    assert _fractions(step) == (Decimal("0.8"), Decimal("0.4"))
    bank = ladder.next(Failure("CANDIDATE_BANK_TIME_LIMIT", THROUGHPUT, "bank limit", {"candidates": 40}))
    assert bank.label == "CAPS_0_80_0_40" and bank.concentration == 1 and bank.bank_steps == 1
    assert bank.showdown_candidate_limit == 40 // 2 and bank.policy is step.policy
    assert _fractions(bank) == (Decimal("0.8"), Decimal("0.4"))


def _default_cap_policy(tmp_path, capsys, *extra):
    document, out = _generate(tmp_path, capsys, *extra)
    slate, _entries, entry_ids = _supplied_world()
    validation = validate_portfolio_policy_bytes(out.read_bytes(), slate=slate, entry_ids=entry_ids)
    assert validation.valid, validation.blockers()
    return validation.policy, out


def _supply(policy, out):
    return supplied_rung(policy, source_path=out, source_sha256=sha256_bytes(out.read_bytes()), normalized_path=None,
                         normalized_sha256=policy.normalized_sha256, defaults=load_concentration_defaults())


def test_a_generator_policy_at_the_default_pair_gives_its_caps_way_before_any_structural_rung(tmp_path, capsys):
    policy, out = _default_cap_policy(tmp_path, capsys)
    supplied = _supply(policy, out)
    assert supplied.concentration == 0 and supplied.label == "SUPPLIED" and not supplied.engine_default
    ladder = _ladder(tmp_path / "walk", supplied=supplied)
    captain_zeroed = {o.person.underlying_id for o in policy.captain_rule.overrides if o.fraction == 0}
    assert captain_zeroed  # the generator zeroes K and DST Captains; cap steps leave that preference alone

    first = ladder.next(STRUCTURE_FAILURE)
    assert first.label == "CAPS_0_80_0_40" and first.rung is None
    assert _fractions(first) == (Decimal("0.8"), Decimal("0.4"))
    assert first.policy.structural_bounds == policy.structural_bounds  # structure is untouched by a cap step
    off = ladder.next(STRUCTURE_FAILURE)
    assert off.label == "CAPS_OFF" and _fractions(off) == (None, None)
    for rung in (first, off):
        assert {o.person.underlying_id for o in rung.policy.captain_rule.overrides if o.fraction == 0} == captain_zeroed
        assert rung.policy.excluded_people == policy.excluded_people and rung.policy.require_unique_lineups
    one = ladder.next(STRUCTURE_FAILURE)
    assert one.rung == 1 and _fractions(one) == (None, None)  # carried forward, never reapplied
    assert one.policy.structural_bounds.salary_left.minimum is None  # rung 1's own drop
    two = ladder.next(STRUCTURE_FAILURE)
    assert two.rung == 2 and _fractions(two) == (None, None)
    assert {r["step"] for r in ladder.records} == {"CONCENTRATION", "STRUCTURE"}
    order = [r["rung_to"] for r in ladder.records]
    assert order.index("1") > max(order.index("CAPS_0_80_0_40"), order.index("CAPS_OFF"))
    # A policy never tightens: each step's fraction is at least the one before (None is no cap).
    seen = [_fractions(rung) for rung in (supplied, first, off, one, two)]
    rank = lambda fraction: float("inf") if fraction is None else float(fraction)  # noqa: E731
    assert all(rank(b[i]) >= rank(a[i]) for a, b in zip(seen, seen[1:]) for i in (0, 1))


def test_a_generator_rung_n_is_the_policy_the_ladder_holds_at_rung_n(tmp_path, capsys):
    policy, _out = _default_cap_policy(tmp_path, capsys)
    slate, _entries, entry_ids = _supplied_world()
    for rung in (1, 2, 3):
        _document, written = _generate(tmp_path / f"r{rung}", capsys, "--rung", str(rung))
        generated = validate_portfolio_policy_bytes(written.read_bytes(), slate=slate, entry_ids=entry_ids).policy
        held = showdown_relaxed_controls(policy, rung, concentration=0)
        assert generated.combined_rule.default_fraction is None and generated.captain_rule.default_fraction is None
        assert held["max_combined_person_exposure"]["default_fraction"] is None
        assert held["max_captain_exposure"]["default_fraction"] is None
        assert generated.structural_bounds.as_mapping() == held["structural_bounds"]


def test_an_explicit_value_that_is_not_the_default_pair_keeps_the_old_ladder(tmp_path, capsys):
    policy, out = _default_cap_policy(tmp_path / "explicit", capsys, "--combined-default", "0.5",
                                      "--captain-default", "0.1")
    supplied = _supply(policy, out)
    assert supplied.concentration is None
    ladder = _ladder(tmp_path / "walk", supplied=supplied)
    rung = ladder.next(STRUCTURE_FAILURE)
    assert rung.rung == 1 and rung.step_name is None  # rung 1 as before: Captain floor 0.25, combined cap untouched
    assert _fractions(rung) == (Decimal("0.5"), Decimal("0.25"))
    # One value off the pair is explicit too.
    mixed, mixed_out = _default_cap_policy(tmp_path / "mixed", capsys, "--captain-default", "0.25")
    assert _supply(mixed, mixed_out).concentration is None
    assert concentration_state(policy, None) is None


# --------------------------------------------------------------------------- #
# Intake: a step the validator refuses is passed over, and the window guard
# --------------------------------------------------------------------------- #


def _small_world(tmp_path, count):
    """The shared NE@SEA pool and a template of `count` rows: small enough for 0.20 to floor to no Captain slot."""

    from .test_participation import _slate
    from .test_prior_selection import _template

    tmp_path.mkdir(parents=True, exist_ok=True)
    slate = _slate(tmp_path)
    entries = _template(tmp_path, tuple(str(index) for index in range(1, count + 1)))
    return slate, entries, tuple(item.entry_id for item in entries.authorizations)


def test_a_default_the_validator_refuses_is_passed_over_for_the_registered_step_and_both_are_recorded(tmp_path):
    world = _small_world(tmp_path, 4)  # floor(0.2 * 4) = 0 Captain slots; floor(0.4 * 4) = 1
    ladder = _ladder(tmp_path / "ladder", world=world)
    rung = ladder.begin_with_defaults()
    assert rung.label == "CAPS_0_80_0_40" and rung.concentration == 1 and rung.engine_default
    assert ladder.started_from.label == "DEFAULT"  # the run began on the requested pair, which could not be held
    (refused,) = [a for a in ladder.attempts if a["outcome"] == "REFUSED_AT_VALIDATION"]
    assert refused["rung"] == "DEFAULT" and "PORTFOLIO_POLICY_CAPTAIN_CAPACITY_INSUFFICIENT" in refused["codes"]
    (record,) = ladder.records
    assert record["constraint"] == "concentration_defaults" and record["limitation_code"] == "SHOWDOWN_CONCENTRATION_RELAXED"
    assert record["trigger"] in refused["codes"] and record["trigger_origin"] == "INTAKE"
    assert (record["rung_from"], record["rung_to"]) == ("DEFAULT", "CAPS_0_80_0_40")
    assert _fractions(rung) == (Decimal("0.8"), Decimal("0.4"))
    assert Path(rung.source_path).parent.name == "attempt_0_rung_CAPS_0_80_0_40"


def test_when_no_step_passes_validation_the_run_starts_at_rung_4_with_every_refusal_recorded(tmp_path):
    world = _small_world(tmp_path, 2)  # floor(0.4 * 2) = 0: neither the requested pair nor 0.80 and 0.40 can hold
    ladder = _ladder(tmp_path / "ladder", world=world)
    rung = ladder.begin_with_defaults()
    assert rung.rung == 4 and rung.policy is None
    refused = [a for a in ladder.attempts if a["outcome"] == "REFUSED_AT_VALIDATION"]
    assert [a["rung"] for a in refused] == ["DEFAULT", "CAPS_0_80_0_40"]
    assert [r["constraint"] for r in ladder.records] == ["concentration_defaults", "portfolio_policy"]
    assert [r["limitation_code"] for r in ladder.records] == ["SHOWDOWN_CONCENTRATION_RELAXED", "RELAXATION_POLICY_DROPPED"]
    assert ladder.stop is None and not ladder.defects


def test_the_window_guard_starts_at_the_floor_when_the_capped_search_would_leave_rung_4_nothing(tmp_path):
    from nfl_dfs.portfolio_enforcement import scaled_candidate_seconds, scaled_selection_seconds

    declared = scaled_candidate_seconds(20) + scaled_selection_seconds(20)  # 60 s declared for twenty rows
    reserve = (20 + 1) * 0.5  # rung 4's 21 half-second solves
    assert (declared, reserve) == (60.0, 10.5)
    held = _ladder(tmp_path / "held", budget=_Window(declared + reserve + 0.1)).begin_with_defaults()
    assert held.label == "DEFAULT" and held.policy is not None
    floor_ladder = _ladder(tmp_path / "floor", budget=_Window(declared + reserve - 0.1))
    floor = floor_ladder.begin_with_defaults()
    assert floor.rung == 4 and floor.policy is None and floor_ladder.stop is None
    assert [r["constraint"] for r in floor_ladder.records] == ["concentration_defaults", "portfolio_policy"]
    for record in floor_ladder.records:
        assert record["trigger"] == "DEADLINE_POLICY_SEARCH_EXCEEDS_WINDOW" and record["trigger_origin"] == "DEADLINE"
        assert record["trigger_kind"] == "THROUGHPUT"
    # No policy file was written for a search the window could not hold.
    assert not (tmp_path / "floor" / "relaxation").exists()


def test_a_window_that_cannot_hold_rung_4_stops_the_ladder_by_name_with_no_policy_in_force(tmp_path):
    ladder = _ladder(tmp_path, budget=_Window(5.0))  # rung 4 needs 10.5 s
    rung = ladder.begin_with_defaults()
    assert rung.policy is None and rung.engine_default and rung.rung is None  # the placeholder: the review runs sequentially
    assert ladder.stop is not None and ladder.stop.startswith("RELAXATION_LADDER_STOPPED:")
    assert "rung 4 needs 10.5 s for 20 sequential solves" in ladder.stop
    assert ladder.records == [] and ladder.texts() == [ladder.stop]
    assert ladder.next(STRUCTURE_FAILURE) is None  # nothing is left to try


def test_a_cap_step_the_window_cannot_hold_stops_the_ladder_by_name(tmp_path):
    ladder = _ladder(tmp_path, budget=_Window(600.0))
    ladder.begin_with_defaults()
    ladder.budget = _Window(2.0)  # under SD3's 2.5 s least, and under rung 4's 10.5 s
    assert ladder.next(STRUCTURE_FAILURE) is None
    assert ladder.stop.startswith("RELAXATION_LADDER_STOPPED:") and "20 sequential solves" in ladder.stop
    assert ladder.current.label == "DEFAULT" and ladder.records == []


def test_a_later_capped_attempt_must_leave_rung_4_its_own_time_too(tmp_path):
    """The first attempt's rule holds for each: a failed capped search must not leave the window to a second one that
    would use it up, so the engine default takes rung 4 while rung 4 still fits (60 s: 21 half-second solves, not 70.5 s)."""

    ladder = _ladder(tmp_path / "step", budget=_Window(600.0))
    ladder.begin_with_defaults()
    ladder.budget = _Window(60.0)
    floor = ladder.next(STRUCTURE_FAILURE)
    assert floor.rung == 4 and floor.policy is None and ladder.stop is None
    assert any("cannot hold another capped bank and joint solve" in str(r["why"]) for r in ladder.records)
    assert [r["constraint"] for r in ladder.records] == ["concentration_defaults", "portfolio_policy"]

    bank = _ladder(tmp_path / "bank", budget=_Window(600.0))
    bank.begin_with_defaults()
    bank.budget = _Window(60.0)
    floor = bank.next(Failure("CANDIDATE_BANK_TIME_LIMIT", THROUGHPUT, "bank limit", {"candidates": 40}))
    assert floor.rung == 4 and floor.policy is None  # no bank step the window cannot afford

    # The same window with room for a capped search (and rung 4 after it) takes the step.
    roomy = _ladder(tmp_path / "roomy", budget=_Window(600.0))
    roomy.begin_with_defaults()
    roomy.budget = _Window(71.0)
    assert roomy.next(STRUCTURE_FAILURE).label == "CAPS_0_80_0_40"


def test_a_supplied_policy_keeps_the_older_window_rule(tmp_path, capsys):
    policy, out = _default_cap_policy(tmp_path, capsys)
    ladder = _ladder(tmp_path / "walk", supplied=_supply(policy, out), budget=_Window(60.0))
    assert ladder.next(STRUCTURE_FAILURE).label == "CAPS_0_80_0_40"  # SD3's 2.5 s least, exactly as before this session
