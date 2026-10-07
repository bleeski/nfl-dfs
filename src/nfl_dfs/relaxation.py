"""The relaxation controller (Session 10): the rung ladder, walked by the engine.

Under a lock clock a construction preference may be relaxed on Claude's own
authority whenever it stands between the run and a legal portfolio (the
2026-09-12 lock-clock ruling, amended by R28, R29 and R31). Until this module
the ladder was printed advice: `scripts/make_classic_policy.py --rung N` said
"regenerate at --rung N+1", and a person did. `run-slate` now walks it inside
one run, inside the run's deadline budget (Session 07), and records each step.

THE LADDER. Classic rungs 0 to 3 are the generator's table below and Showdown
rungs 1 to 3 its own (`SHOWDOWN_RUNGS`); rung 4 in both is no policy: C1, or
sequential Showdown selection, the floor. Since Session 49 Classic rung 4 is not C1's
one repeated construction: it builds several stack theses under one person share cap
(`classic_theses.py`, `classic_thesis_sequential_v1`), and the preferences that build
relaxes (bring-back, overlap, the share cap, the stack) travel in the same `relaxation`
record as a rung's; Showdown rung 4 is unchanged. A rung's policy is the loosest of the
policy it replaces and the rung's table, dimension by dimension, so a
relaxation never tightens anything: a generator's rung-k policy becomes rung
k+1 exactly, and a hand-written one keeps whatever the rung leaves looser. A
supplied policy starts at the first rung that changes it.

Session 23e (P2) folds Classic's structural bounds into the same table: rung 1 drops
the `salary_left` band, rung 2 `offense_against_own_dst`, and `max_person_share` (0.80)
stays through rung 3, dropped only by rung 4. See `classic_structural_bounds` and
`docs/DATA_CONTRACTS.md` § C2 v2.

Session 57 (2026-10-02 review F-06, F-07) re-cut what a NEW policy is written with, not what the tables do. The
generators leave `offense_against_own_dst` open (Classic: `classic_rung_controls`, which writes it only when asked and
then follows `classic_structural_bounds`, on through rung 1 and off from rung 2; Showdown: `make_showdown_policy.py`) and
the Showdown generator admits one to two quarterbacks. `classic_structural_bounds` and `SHOWDOWN_RUNGS` stay exactly the
relaxation tables, so an explicit or a frozen policy relaxes where it always did (rung 2 drops its `offense_against_own_dst`,
rung 3 its QB-count band) and the Boolean is never read as the DST's opponent; for a policy written with the new defaults
those drops are no-ops. A construction preference: relaxed or restored on Claude's authority, Ben's to overturn.

WHAT A FAILURE ASKS FOR. The selection's failure status, carried structured on
`SelectionError` into `reports["selection_failure"]` (never parsed from text),
picks the step:

- `STRUCTURE`: the bank or joint solve is infeasible under the policy, or the
  policy's only validation problems are `S` codes. The next structural rung.
- `THROUGHPUT`: a bank or joint solve hit its time or search limit without
  what it needed, or a hash-bound search the window cannot hold. The same
  structure with the bank re-sized from this run's measured rate to the window
  left, once per rung (C4 retro #3: a time signal shrinks the bank or raises
  its budget, it does not relax structure); a second one takes rung 4, since
  structure does not fix throughput.
- `SOLVER_ERROR`: a claim failure (`selection_claims`, `P`), not a preference.
  One retry on a smaller bank, then rung 4; never a structural rung.
- `BANK_DEPTH`: SD3's joint solve infeasible over an incomplete bank. The bank
  deepened once to 6 x entries (DAL@NYG retro §6, §7e), or by half where that
  is no deeper than `max(32, 4 x entries)`, then structure.

Never a trigger: a bank or joint solve a limit stopped with what it needed
(Session 08 delivers and names it), and running out of distinct lineups: rung 4
is the floor and R29 keeps every lineup distinct. Classic rung 4 (Session 49)
that builds k of n rows delivers the k and names the rest; with no row built, and
on Showdown, the baseline stays the file.

A SHOWDOWN THESIS (Session 23b, `showdown_theses.py`) is never on the ladder. Every
rung copies the policy's `theses` byte for byte (`_changes` refuses a rung that
would change one), so only caps loosen. A thesis no lineup can follow
(`THESIS_UNBUILDABLE`, proved before any bank) is dropped by name and the same
policy is built without it, with no rung taken; rung 4 drops a thesis with the
policy, by name. Each drop is a `THESIS_DROPPED` record.

THE CONCENTRATION STEPS (Session 56, R35). Before any structural rung a Showdown policy whose two default fractions are exactly the
registered pair (`config/showdown_concentration_defaults_v1.json`: 0.60 a person, 0.20 a Captain) gives its caps way: 0.80 and 0.40,
then none (`CAPS_OFF`; its overrides, exclusions and structural bounds stay), and a structural rung taken after them carries the caps
off, so a relaxed cap is never reapplied (`showdown_relaxed_controls(..., concentration=)`). A Showdown run that supplied no policy
starts on the engine's own default of that pair (`Ladder.begin_with_defaults`: three controls, structure open, every fillable row,
written and validated like a rung); its off is rung 4 because sequential selection keeps a distinct Captain per row where an
uncapped joint solve would not, and it starts at rung 4 when the window cannot hold the declared bank and joint solve and leave rung 4
its own. Any other value an operator wrote is theirs and these steps never touch it. Each step is one record, code
`SHOWDOWN_CONCENTRATION_RELAXED`; a default that could not apply at all is `concentration_not_applied_text`.

NEVER ON EITHER LADDER. `require_unique_lineups` (R29) and every exact exclusion
(a Classic policy's `exact_exclusions`, a Showdown policy's `excluded_people`),
which rung 4 carries as operator exclusions. A person a policy caps at zero
entries (a Classic `maximum_entries` of 0, a Showdown combined fraction of 0)
is excluded too: the selector already treats a zero maximum as an exclusion, so
the ladder keeps it as one. A zeroed Showdown Captain is a Captain cap, not an
exclusion, and rung 2 relaxes it. Nothing here touches an evidence gate; the
ladder only replaces the policy.

THE WINDOW. Before each attempt the next rung's declared search must fit the
improvement window less the last attempt's measured pre-selection time: a C2
rung's bank and joint budget from `classic_limits` at this host's slowest
measured rate, an SD3 rung the least window its budget allowances take, rung 4
one C1 solve per lineup at the least time a solve is given. A C2 or SD3 rung
that does not fit takes rung 4; rung 4 not fitting stops the ladder, named
`RELAXATION_LADDER_STOPPED`, and the baseline stays the file. A rung the
validator refuses on a code no rung loosens is a defect, named
`RELAXATION_RUNG_UNBUILDABLE`, and rung 4, which needs no generated policy, is
still tried.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from .classic_theses import THESIS_CONSTRUCTION_VERSION
from .classic_portfolio_policy import (
    ClassicStructuralBounds,
    NormalizedClassicPortfolioPolicy,
    StackRule,
    classic_portfolio_policy_template,
    person_share_maximum,
    validate_classic_portfolio_policy_file,
    write_classic_portfolio_policy_validation,
    write_normalized_classic_portfolio_policy,
)
from .concentration import (
    ENGINE_DEFAULT,
    POLICY,
    ConcentrationDefaults,
    ConcentrationStep,
    ConcentrationDefaultsError,
    load_concentration_defaults,
)
from .contracts import EngineMode, GateClass
from .deadline import JOINT_SHARE as SD3_JOINT_SHARE
from .deadline import SOLVE_MINIMUM_SECONDS, Budget
from .entry_groups import plan_entries
from .gate_registry import GateRegistry, GateRegistryError
from .hashing import sha256_bytes
from .portfolio_enforcement import scaled_candidate_limit, scaled_candidate_seconds, scaled_selection_seconds
from .portfolio_policy import (
    FRACTION_UNIT,
    OPEN_RANGE,
    OPEN_STRUCTURAL_BOUNDS,
    POLICY_SCHEMA_VERSION_V2,
    POLICY_SCHEMA_VERSION_V3,
    POLICY_SCHEMA_VERSION_V4,
    ExposureRule,
    NormalizedPortfolioPolicy,
    StructuralBoundRange,
    StructuralBounds,
    canonical_decimal_json_bytes,
    portfolio_policy_template,
    validate_portfolio_policy_file,
    write_normalized_portfolio_policy,
    write_portfolio_policy_validation,
)

CONTRACT_VERSION = "nfl_relaxation_record_v1"
NO_POLICY_RUNG = 4
_CONTINUE = object()  # `_concentration_step`: no cap step is left; the structural rungs follow

# -- the Classic rung table (moved from scripts/make_classic_policy.py) -------

ROSTER_SIZE = 9
# The 2026-09-12 cloud measurement (`classic_limits`), with the room kept for
# it: a declared bank budget is twice the expected generation time, and the
# bank plus joint solve may declare 75% of the improvement window, the joint
# solve at most 20%.
DEFAULT_SECONDS_PER_CANDIDATE = 0.28
GENERATION_HEADROOM = 2.0
WINDOW_SHARE, JOINT_SHARE = 0.75, 0.20
DEFAULT_MINUTES = 4.0


class BankDoesNotFit(ValueError):
    """Even the floor bank and its joint solve exceed the window's share."""


def classic_stack_rules(count: int, rung: int) -> list[dict[str, object]]:
    """QB correlation is the only edge this objective can express structurally.

    The objective is a sum of independent per-player central estimates: there is
    no covariance term and no ceiling, so a stack is worth nothing to the solver
    on its own. The only way correlation enters a Classic portfolio today is as
    a hard constraint on which candidates may be built.
    """
    if rung <= 0:
        pass_catcher_entries, bringback_entries, bringback_strength = count, math.ceil(0.70 * count), "HARD"
    elif rung == 1:
        pass_catcher_entries, bringback_entries, bringback_strength = count, math.ceil(0.34 * count), "HARD"
    elif rung == 2:
        pass_catcher_entries, bringback_entries, bringback_strength = count, 0, "ADVISORY"
    else:
        pass_catcher_entries, bringback_entries, bringback_strength = math.ceil(0.50 * count), 0, "ADVISORY"

    return [
        {
            "rule_id": "qb-pass-catcher",
            "rule_type": "QB_PASS_CATCHER",
            "minimum_value": 1,
            "maximum_value": 4,
            "minimum_entries": min(pass_catcher_entries, count),
            "maximum_entries": count,
            "strength": "HARD",
        },
        {
            "rule_id": "qb-bringback",
            "rule_type": "QB_BRINGBACK",
            "minimum_value": 1,
            "maximum_value": 6,
            "minimum_entries": min(bringback_entries, count),
            "maximum_entries": count,
            "strength": bringback_strength,
        },
        {
            "rule_id": "secondary-game-correlation",
            "rule_type": "SECONDARY_GAME_CORRELATION",
            "minimum_value": 1,
            "maximum_value": 4,
            "minimum_entries": 0,
            "maximum_entries": count,
            "strength": "ADVISORY",
        },
        {
            "rule_id": "rb-dst-pair",
            "rule_type": "RB_DST_PAIR",
            "minimum_value": 1,
            "maximum_value": 2,
            "minimum_entries": 0,
            "maximum_entries": count,
            "strength": "ADVISORY",
        },
    ]


def classic_overlap(rung: int) -> int:
    return {0: 5, 1: 5, 2: 6}.get(rung, 7)


def classic_exposure_fraction(rung: int) -> float | None:
    return {0: 0.50, 1: 0.50, 2: 0.65}.get(rung)


def classic_exposure_cap(count: int, rung: int) -> int:
    """The rung's per-person maximum: its fraction of the entries, or no cap."""

    fraction = classic_exposure_fraction(rung)
    if fraction is None or count <= 2:
        return count
    return max(1, math.ceil(fraction * count))


# Session 23e (P2): Classic structural hygiene and the share cap, folded into the
# rung table in the brief's relaxable order (salary band, pass-catcher band, K/DST
# caps, QB count, `max_person_share` last). The pass-catcher band is the existing
# `QB_PASS_CATCHER` rule above, already on the table, and Classic has no kicker or
# QB-count row, so what is new is the salary band (rung 1), `offense_against_own_dst`
# (rung 2, grouped with the K/DST caps it sits beside in Showdown's ladder, the same
# judgment call Session 23 recorded) and the share cap. The share cap stays through
# rung 3, the last policy rung and the first where it is the only exposure cap left
# (rungs 0 to 2 carry tighter explicit fractions); rung 4, no policy, drops it.
CLASSIC_SALARY_LEFT_MAXIMUM = 1000
CLASSIC_SHARE_CEILING = Decimal("0.80")


def _json_number(fraction: Decimal | None) -> float | None:
    """A share as the plain JSON number a policy document carries (`json.dumps` reads it;
    `_materialize` turns it back into the exact decimal the validator parses)."""

    return None if fraction is None else float(fraction)


def _exact_decimals(value: object) -> object:
    """`value` with every float replaced by its shortest-repr `Decimal`, for canonical bytes."""

    if isinstance(value, float):
        return Decimal(repr(value))
    if isinstance(value, Mapping):
        return {key: _exact_decimals(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_exact_decimals(item) for item in value]
    return value


def classic_structural_bounds(rung: int) -> ClassicStructuralBounds:
    """The relaxation table's structural bounds at `rung`: salary left to $1,000 through rung 0, no
    offense against an own DST through rung 1.

    This is the table `classic_relaxed_controls` loosens a policy by, so an explicit or a frozen
    policy that declares the veto loses it at rung 2 as it always did. It is not what a generated
    policy is written with: `classic_rung_controls` leaves the veto open unless asked (Session 57).
    """

    return ClassicStructuralBounds(
        StructuralBoundRange(0, CLASSIC_SALARY_LEFT_MAXIMUM) if rung <= 0 else OPEN_RANGE,
        rung <= 1,
    )


def classic_table_share(rung: int) -> Decimal:
    """The largest share of the entries one person holds at `rung`: its explicit exposure
    fraction where the rung has one, else the 0.80 ceiling."""

    fraction = classic_exposure_fraction(rung)
    return CLASSIC_SHARE_CEILING if fraction is None else Decimal(str(fraction))


def classic_generated_share(count: int) -> Decimal | None:
    """The `max_person_share` a generated policy declares: the ceiling, on any portfolio
    big enough to cap (the rung fractions skip two entries or fewer the same way)."""

    return CLASSIC_SHARE_CEILING if count > 2 else None


def classic_limits(
    count: int,
    pool_people: int,
    rung: int,
    *,
    minutes: float,
    seconds_per_candidate: float = DEFAULT_SECONDS_PER_CANDIDATE,
    window_seconds: float | None = None,
    candidate_cap: int | None = None,
    minimum_selection_seconds: float | None = None,
) -> dict[str, int]:
    """Size the bank to the pool, not to the entry count, and to the window.

    Measured on the 719-person supplied fixture in the cloud container at 20
    entries, two processors: a 1000-candidate bank with the rung-0 HARD stack
    rules generated in 273.6s and the joint MILP then solved it in 0.39s,
    selecting all 20 entries. Generation is the whole cost, the joint solve is
    free, and hard stack rules make generation slower per candidate than the
    unconstrained default. The declared budget is twice the expected time at
    `seconds_per_candidate`, so a bank that fits the requested minutes does not
    then trip CANDIDATE_BANK_TIMEOUT and cost a rung for nothing.

    Session 07b. `seconds_per_candidate` is this host's measured rate when it
    has one (the C4 retrospective measured 4 to 6 s). With `window_seconds`,
    the seconds left before the improvement stops, the declared bank budget
    plus the joint solve stay within `WINDOW_SHARE` of it and the joint solve
    within `JOINT_SHARE`; the rest is the run's own before selection. Raises
    `BankDoesNotFit` when even the floor bank, `max(32, entries + 24)`, does not.
    Session 10: `candidate_cap` holds the bank at or under a size (never under
    the floor), for a joint solve that could not finish over the last one, and
    `minimum_selection_seconds` keeps that retry's joint budget from falling
    below the one that ran out (within the window's joint share).
    """
    per_candidate_seconds = float(seconds_per_candidate)
    if not (math.isfinite(per_candidate_seconds) and per_candidate_seconds > 0):
        raise ValueError(f"seconds_per_candidate must be a finite number above zero, not {seconds_per_candidate!r}")
    floor = max(32, count + 24)
    affordable = int((minutes * 60.0) / per_candidate_seconds)
    selection_seconds = min(3_600.0, max(10.0, 1.0 * count, float(minimum_selection_seconds or 0.0)))
    if window_seconds is not None:
        selection_seconds = min(selection_seconds, JOINT_SHARE * window_seconds)
        generation_seconds = WINDOW_SHARE * window_seconds - selection_seconds
        affordable = min(affordable, max(0, int(
            generation_seconds / (per_candidate_seconds * GENERATION_HEADROOM))))
    target = max(floor, min(2000, affordable))
    if rung >= 3:
        target = max(floor, target // 2)
    if candidate_cap is not None:
        target = max(floor, min(target, int(candidate_cap)))

    def declared_ms(candidates: int) -> int:
        return int(min(3_600_000, max(
            30_000, candidates * per_candidate_seconds * 1000 * GENERATION_HEADROOM)))

    total_ms = declared_ms(target)
    selection_ms = int(1_000 * selection_seconds)
    # A bank above the floor was sized to fit, so only the floor bank (or the
    # 30 s least budget any bank declares) can fail this.
    if window_seconds is not None and (
            selection_seconds < SOLVE_MINIMUM_SECONDS
            or (total_ms + selection_ms) / 1000.0 > WINDOW_SHARE * window_seconds):
        floor_ms = declared_ms(floor)
        raise BankDoesNotFit(
            f"even the floor bank of {floor} candidates at {per_candidate_seconds:g} s each"
            f" declares {floor_ms / 1000:.0f} s and its joint solve {selection_ms / 1000:.1f} s,"
            f" {(floor_ms + selection_ms) / 1000:.1f} s together, over {WINDOW_SHARE:.0%} of the"
            f" {window_seconds:.1f} s window ({WINDOW_SHARE * window_seconds:.1f} s)"
        )
    return {
        "candidate_limit": target,
        "candidate_total_milliseconds": total_ms,
        "candidate_per_solve_milliseconds": 5_000,
        "selection_milliseconds": selection_ms,
    }


def classic_rung_controls(
    slate, count: int, rung: int, *, offense_against_own_dst: bool = False
) -> dict[str, object]:
    """The generator's controls at `rung`: the table, a bound on every person.

    `offense_against_own_dst` (Session 57, review F-06) asks for the veto on a person sharing a
    rostered DST's team. It is off unless asked: the field contradicts it, so a generated policy
    leaves it open on every rung. A policy that asks for it follows the table
    (`classic_structural_bounds`: on through rung 1, off from rung 2), so a rung never tightens it.
    """

    table = classic_structural_bounds(rung)
    structural = ClassicStructuralBounds(
        table.salary_left, offense_against_own_dst and table.offense_against_own_dst)
    controls: dict[str, object] = {
        "stack_rules": classic_stack_rules(count, rung),
        "max_pairwise_person_overlap": min(classic_overlap(rung), ROSTER_SIZE - 1),
        "require_unique_lineups": True,
        "structural_bounds": structural.as_mapping(),
        "max_person_share": _json_number(classic_generated_share(count)),
    }
    if classic_exposure_fraction(rung) is not None and count > 2:
        cap = classic_exposure_cap(count, rung)
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
    return controls


def classic_relaxed_controls(policy: NormalizedClassicPortfolioPolicy, rung: int | None) -> dict[str, object]:
    """The loosest of `policy` and the rung's table; `rung=None` is `policy` itself.

    Loosest per dimension: a stack rule keeps the lower minimum and the wider
    value range, and stays HARD only if the rung's rule is; a person's maximum is
    the higher of the two and a minimum drops to the table's zero; a team, game
    or HARD group bound the table does not carry is dropped (a group becomes
    ADVISORY); the overlap cap is the higher. Session 23e: `salary_left` is the
    wider range and `offense_against_own_dst` holds only while the rung's does;
    `max_person_share` is the higher of the two fractions, and a policy without
    one keeps none. A policy's own exact exclusions,
    and any person it caps at zero, are carried unchanged, and uniqueness is
    always required (R29). An exclusion
    from outside the policy (official inactives, operator exclusions) is not
    written: the validator re-derives it from the same run.
    """

    count = policy.entry_count
    people = policy.people_by_id
    table_rules: dict[str, dict[str, object]] = {}
    cap = overlap = None
    share = policy.max_person_share
    structural = policy.structural_bounds
    if rung is not None:
        table_rules = {str(item["rule_type"]): item for item in classic_stack_rules(count, rung)}
        # The most one person may hold at this rung, for a person the table bounds:
        # its explicit fraction where it has one; else, on a policy that declares a
        # share cap, the share ceiling (its own default loosens to it); else no cap.
        cap = (classic_exposure_cap(count, rung) if classic_exposure_fraction(rung) is not None
               else count if count <= 2 or share is None else person_share_maximum(CLASSIC_SHARE_CEILING, count))
        overlap = min(classic_overlap(rung), ROSTER_SIZE - 1)
        share = None if share is None else max(share, classic_table_share(rung))
        structural = _classic_relaxed_structural(structural, classic_structural_bounds(rung))
    share_maximum = person_share_maximum(share, count)
    default_maximum = count if share_maximum is None else share_maximum
    bounds = []
    for bound in policy.player_bounds:
        if bound.exclusion_source is not None:
            continue
        low, high = bound.minimum_entries, bound.maximum_entries
        if cap is not None:
            low, high = 0, (0 if high == 0 else max(high, cap))  # a zero cap is an exclusion
        # A person at the share's default maximum carries no explicit row: the
        # relaxed policy derives the same bound from `max_person_share`.
        if (low, high) != (0, default_maximum):
            bounds.append({**people[bound.entity_id].reference(), "minimum_entries": low,
                           "maximum_entries": high, "hard": True})

    def entity_bounds(items, key: str) -> list[dict[str, object]]:
        # The table carries no team or game bound, so a rung drops them, except a
        # zero cap, which takes the team or game out and stays an exclusion.
        return [{key: item.entity_id, "minimum_entries": 0 if rung is not None else item.minimum_entries,
                 "maximum_entries": item.maximum_entries, "hard": True}
                for item in items if (item.minimum_entries, item.maximum_entries) != (0, count)
                and (rung is None or item.maximum_entries == 0)]

    groups = []
    for group in policy.groups:
        mapping = group.as_mapping(people)
        if rung is not None and group.hard:
            mapping = {**mapping, "strength": "ADVISORY", "minimum_entries": 0}
        groups.append(mapping)
    return {
        "player_exposure_bounds": bounds,
        "team_exposure_bounds": entity_bounds(policy.team_bounds, "team"),
        "game_exposure_bounds": entity_bounds(policy.game_bounds, "game_id"),
        "exact_exclusions": [people[person].reference() for person in sorted(
            bound.entity_id for bound in policy.player_bounds if bound.exclusion_source == "POLICY_EXCLUSION")],
        "groups": groups,
        "stack_rules": [_merged_rule(rule, table_rules.get(rule.rule_type), rung is not None)
                        for rule in policy.stack_rules],
        "max_pairwise_person_overlap": (
            policy.max_pairwise_person_overlap if overlap is None
            else max(policy.max_pairwise_person_overlap, overlap)),
        "require_unique_lineups": True,
        "structural_bounds": structural.as_mapping(),
        "max_person_share": _json_number(share),
    }


def _classic_relaxed_structural(
    bounds: ClassicStructuralBounds, table: ClassicStructuralBounds
) -> ClassicStructuralBounds:
    """The loosest of `bounds` and the rung's: a side either leaves open is open."""

    def wider(left: int | None, right: int | None, pick) -> int | None:
        return None if left is None or right is None else pick(left, right)

    return ClassicStructuralBounds(
        StructuralBoundRange(
            wider(bounds.salary_left.minimum, table.salary_left.minimum, min),
            wider(bounds.salary_left.maximum, table.salary_left.maximum, max),
        ),
        bounds.offense_against_own_dst and table.offense_against_own_dst,
    )


def _merged_rule(rule: StackRule, table: Mapping[str, object] | None, relaxing: bool) -> dict[str, object]:
    mapping = rule.as_mapping()
    if not relaxing:
        return mapping
    if table is None:  # the rung carries no rule of this type: coverage only
        return {**mapping, "minimum_entries": 0, "strength": "ADVISORY"}
    return {
        **mapping,
        "minimum_value": min(rule.minimum_value, int(table["minimum_value"])),
        "maximum_value": max(rule.maximum_value, int(table["maximum_value"])),
        "minimum_entries": min(rule.minimum_entries, int(table["minimum_entries"])),
        "maximum_entries": max(rule.maximum_entries, int(table["maximum_entries"])),
        "strength": "HARD" if rule.hard and table["strength"] == "HARD" else "ADVISORY",
    }


# -- the Showdown rung table --------------------------------------------------

@dataclass(frozen=True)
class ShowdownRung:
    captain_floor: Decimal | None  # every capped Captain fraction at least this
    lift_zero_captains: bool       # zeroed Captains (K, DST by default) take the floor
    uncapped: bool                 # no combined or Captain cap at all (drops max_person_share too)
    overlap_floor: int | None      # the pairwise overlap cap at least this
    # Session 23 (P2): the brief's relaxable order for the new structural
    # bounds (salary band, pass-catcher band, K/DST caps, QB count), folded
    # into this same 3-rung ladder. `offense_against_own_dst` isn't named in
    # the brief's 5-item order, so it drops alongside the K/DST caps it's
    # adjacent to (recorded in the changelog as a judgment call).
    drop_salary_band: bool = False
    drop_pass_catcher_band: bool = False
    drop_kicker_dst_caps: bool = False
    drop_qb_count_band: bool = False
    drop_offense_against_own_dst: bool = False


# DAL@NYG retro §6: the bank and the Captain strata bind first (at Captain cap 2
# of 20, only 11 people could ever captain), so after the bank step the Captain
# caps widen first, then zeroed Captains become eligible, then every exposure
# cap and the tight overlap go. Rung 4 is no policy.
SHOWDOWN_RUNGS: Mapping[int, ShowdownRung] = {
    1: ShowdownRung(Decimal("0.25"), False, False, None, drop_salary_band=True),
    2: ShowdownRung(
        Decimal("0.5"), True, False, None,
        drop_salary_band=True, drop_pass_catcher_band=True, drop_kicker_dst_caps=True,
        drop_offense_against_own_dst=True,
    ),
    3: ShowdownRung(
        None, True, True, 5,
        drop_salary_band=True, drop_pass_catcher_band=True, drop_kicker_dst_caps=True,
        drop_offense_against_own_dst=True, drop_qb_count_band=True,
    ),
}
SHOWDOWN_DEEP_BANK_PER_ENTRY = 6
# The least window an SD3 bank and joint solve are given anything in
# (`Budget.policy_search_seconds`: the joint solve takes 20% and needs 0.5 s).
SD3_MINIMUM_WINDOW_SECONDS = SOLVE_MINIMUM_SECONDS / SD3_JOINT_SHARE


def showdown_relaxed_controls(
    policy: NormalizedPortfolioPolicy, rung: int | None, *, concentration: int | None = None
) -> dict[str, object]:
    """The loosest of `policy` and a Showdown rung; `rung=None` is `policy` itself.

    `concentration` (Session 56) is the cap steps a defaults-keyed policy has taken (0 for one
    whose default fractions are exactly the registered pair, `None` for any other). The cap
    steps come before every structural rung, so a rung taken from such a policy carries the
    default fractions off (its overrides and structural bounds are the rung's own business):
    the generator's `--rung N` and the ladder's rung N then agree, and a relaxed cap is never
    reapplied by a later rung.
    """

    spec = None if rung is None else SHOWDOWN_RUNGS[rung]
    caps_off = spec is not None and concentration is not None

    def rule(item: ExposureRule, *, captain: bool) -> dict[str, object]:
        if spec is not None and spec.uncapped:
            if captain:
                return {"default_fraction": None, "overrides": []}
            # A combined fraction of 0 is an exclusion and stays; under a zero
            # default every positive override opens fully instead of vanishing.
            zero_default = item.default_fraction == 0
            return {
                "default_fraction": item.default_fraction if zero_default else None,
                "overrides": [{**override.person.as_mapping(),
                               "fraction": override.fraction if override.fraction == 0 else Decimal(1)}
                              for override in item.overrides if override.fraction == 0 or zero_default],
            }
        floor = spec.captain_floor if spec is not None and captain else None
        lift = bool(spec is not None and spec.lift_zero_captains and captain)

        def loosen(fraction: Decimal | None) -> Decimal | None:
            if floor is None or fraction is None or (fraction == 0 and not lift):
                return fraction
            return max(fraction, floor)

        return {
            "default_fraction": None if caps_off else loosen(item.default_fraction),
            "overrides": [{**override.person.as_mapping(), "fraction": loosen(override.fraction)}
                          for override in item.overrides],
        }

    overlap = policy.max_pairwise_person_overlap
    if spec is not None and spec.overlap_floor is not None and overlap is not None:
        overlap = max(overlap, spec.overlap_floor)
    return {
        "fraction_unit": FRACTION_UNIT,
        "max_combined_person_exposure": rule(policy.combined_rule, captain=False),
        "max_captain_exposure": rule(policy.captain_rule, captain=True),
        "excluded_people": [person.as_mapping() for person in policy.excluded_people],
        "max_pairwise_person_overlap": overlap,
        "require_unique_lineups": True,
        # Session 23b: from the bounds as declared, so a bound a thesis widened is re-derived
        # by each rung's validation (and restored when the thesis is dropped), never carried as
        # if Ben had declared it.
        "structural_bounds": _showdown_relaxed_structural_bounds(
            policy.declared_structural_bounds or policy.structural_bounds, spec),
        # Session 23b: a thesis is never relaxed; every rung carries it exactly as declared.
        **({"theses": [thesis.source_mapping() for thesis in policy.theses]} if policy.theses else {}),
    }


def showdown_schema_version(policy: NormalizedPortfolioPolicy) -> str:
    """The schema a rung's policy is written in: v4 for a portfolio of theses (Session 23c), v3 while it
    carries one thesis, else v2."""

    if policy.thesis_schema == "v4":
        return POLICY_SCHEMA_VERSION_V4
    return POLICY_SCHEMA_VERSION_V3 if policy.theses else POLICY_SCHEMA_VERSION_V2


def _showdown_relaxed_structural_bounds(
    bounds: StructuralBounds, spec: ShowdownRung | None
) -> dict[str, object]:
    """`bounds` itself when `spec` is `None`; each side the rung drops opened fully."""

    def open_range(range_: StructuralBoundRange, drop: bool) -> dict[str, object]:
        return {"minimum": None, "maximum": None} if drop else range_.as_mapping()

    drop_salary = spec is not None and spec.drop_salary_band
    drop_catchers = spec is not None and spec.drop_pass_catcher_band
    drop_kicker_dst = spec is not None and spec.drop_kicker_dst_caps
    drop_qb = spec is not None and spec.drop_qb_count_band
    drop_offense = spec is not None and spec.drop_offense_against_own_dst
    return {
        "qb_count": open_range(bounds.qb_count, drop_qb),
        "pass_catchers_with_rostered_qb": open_range(bounds.pass_catchers_with_rostered_qb, drop_catchers),
        "salary_left": open_range(bounds.salary_left, drop_salary),
        "kicker_count": None if drop_kicker_dst else bounds.kicker_count_maximum,
        "dst_count": None if drop_kicker_dst else bounds.dst_count_maximum,
        "offense_against_own_dst": False if drop_offense else bounds.offense_against_own_dst,
    }


# -- triggers -----------------------------------------------------------------

# The step a trigger asks for (the module docstring).
STRUCTURE = "STRUCTURE"
THROUGHPUT = "THROUGHPUT"
SOLVER_ERROR = "SOLVER_ERROR"
BANK_DEPTH = "BANK_DEPTH"
# A thesis no lineup can follow (Session 23b) is dropped, not walked down the rungs.
THESIS_UNBUILDABLE = "THESIS_UNBUILDABLE"
STRUCTURE_TRIGGERS = frozenset({
    "MODELED_BANK_INFEASIBILITY", "INCOMPLETE_BANK_EXHAUSTION", "STRUCTURAL_INFEASIBILITY",
    "MODELED_BANK_INFEASIBLE_PROVEN", THESIS_UNBUILDABLE,
})
THROUGHPUT_TRIGGERS = frozenset({
    "CANDIDATE_BANK_TIMEOUT", "CANDIDATE_BANK_SEARCH_LIMIT", "CANDIDATE_BANK_TIME_LIMIT",
    "PORTFOLIO_SELECTION_TIMEOUT", "PORTFOLIO_SELECTION_SEARCH_LIMIT", "PORTFOLIO_SELECTION_TIME_LIMIT",
    "DEADLINE_POLICY_SEARCH_EXCEEDS_WINDOW",
})
SOLVER_ERROR_TRIGGERS = frozenset({"CANDIDATE_BANK_SOLVER_ERROR", "PORTFOLIO_SELECTION_SOLVER_ERROR"})
BANK_DEPTH_TRIGGERS = frozenset({"CANDIDATE_BANK_EXHAUSTED_INCOMPLETE"})
TRIGGERS = STRUCTURE_TRIGGERS | THROUGHPUT_TRIGGERS | SOLVER_ERROR_TRIGGERS | BANK_DEPTH_TRIGGERS
# What Session 08 delivers and names, and the floor's own end: never a rung.
NEVER_TRIGGERS = frozenset({
    "BOUNDED_TIME_LIMIT_STOP", "BOUNDED_SEARCH_LIMIT_STOP", "FEASIBLE_LIMIT_ACTUAL_CANDIDATE_BANK",
    "CANDIDATE_BANK_STOPPED_AT_LIMIT", "PORTFOLIO_SELECTION_LIMIT_INCUMBENT", "SOLVER_RETURNED_NO_LINEUP",
})
# A joint solve that could not finish over its bank: the retry halves the bank.
_JOINT_LIMITS = frozenset({
    "PORTFOLIO_SELECTION_TIMEOUT", "PORTFOLIO_SELECTION_SEARCH_LIMIT", "PORTFOLIO_SELECTION_TIME_LIMIT",
})
# An SD3 bank stopped by its own limit before it held what the joint solve needs.
_SD3_BANK_LIMITS = frozenset({"CANDIDATE_BANK_TIME_LIMIT", "CANDIDATE_BANK_SEARCH_LIMIT"})
NEVER_RELAXED = (
    "require_unique_lineups (R29: every lineup in a portfolio distinct)",
    "a Showdown thesis's structure (dropped and named when it cannot be built, never loosened)",
    "exact exclusions: a Classic policy's exact_exclusions and a Showdown policy's excluded_people",
    "every evidence gate: official activity, current role, weather, identity, expiry, hash bindings",
)
DOES_NOT_ESTABLISH = (
    "UPLOAD_CLEARANCE",
    "CERTIFICATION",
    "LINEUP_QUALITY",
    "THAT_A_TIGHTER_POLICY_WAS_INFEASIBLE_OUTSIDE_THE_REPORTED_BANK",
)


def classify(status: str) -> str | None:
    """The step a failure status asks for, or None when it is not a trigger."""

    if status in STRUCTURE_TRIGGERS:
        return STRUCTURE
    if status in THROUGHPUT_TRIGGERS:
        return THROUGHPUT
    if status in SOLVER_ERROR_TRIGGERS:
        return SOLVER_ERROR
    if status in BANK_DEPTH_TRIGGERS:
        return BANK_DEPTH
    return None


@dataclass(frozen=True)
class Failure:
    """Why the current rung did not deliver: a status, its step, its facts."""

    status: str
    kind: str
    detail: str
    facts: Mapping[str, object] = field(default_factory=dict)
    origin: str = "SELECTION"  # SELECTION, DEADLINE or INTAKE


def failure_of(outcome) -> Failure | None:
    """The trigger in a review outcome, from its structured `selection_failure`."""

    report = outcome.reports.get("selection_failure") if isinstance(outcome.reports, Mapping) else None
    if not (outcome.blocked and outcome.stage == "SELECT" and isinstance(report, Mapping)):
        return None
    status = str(report.get("status") or "")
    kind = classify(status)
    if kind is None:
        return None
    facts = report.get("facts")
    return Failure(status, kind, str(report.get("error") or status),
                   dict(facts) if isinstance(facts, Mapping) else {}, str(report.get("origin") or "SELECTION"))


def intake_failure(codes: Sequence[str], registry: GateRegistry) -> Failure | None:
    """A supplied policy whose only validation problems are construction preferences.

    Search-budget codes ask for the bank step; any bound code asks for
    structure, whose rung re-sizes the limits too. Any code that is not `S`, or
    not registered, keeps the policy a stop.
    """

    families = []
    for code in codes:
        try:
            family = registry.family_of(code)
        except GateRegistryError:
            return None
        if family.gate_class is not GateClass.S:
            return None
        families.append(family.name)
    if not codes:
        return None
    kind = THROUGHPUT if set(families) == {"search_budget"} else STRUCTURE
    return Failure(str(codes[0]), kind, "; ".join(codes), {"codes": list(codes)}, "INTAKE")


# -- the ladder ---------------------------------------------------------------

@dataclass(frozen=True)
class Rung:
    """A policy on the ladder and the artifacts that bind it; `policy=None` is rung 4."""

    rung: int | None  # None: the supplied policy
    policy: NormalizedClassicPortfolioPolicy | NormalizedPortfolioPolicy | None
    source_path: str | None = None
    source_sha256: str | None = None
    normalized_path: str | None = None
    normalized_sha256: str | None = None
    showdown_candidate_limit: int | None = None
    bank_steps: int = 0
    excluded_dk_ids: tuple[str, ...] = ()  # the policy's own exclusions, which rung 4 carries
    # Session 56: the concentration cap steps taken so far (0: the requested pair), or None for a
    # policy whose default fractions are not the registered ones (its caps are the operator's).
    concentration: int | None = None
    step_name: str | None = None  # the cap step that made this rung, for its label
    engine_default: bool = False  # `run-slate` built this policy itself; there was no supplied one

    @property
    def label(self) -> str:
        if self.rung is not None:
            return str(self.rung)
        if self.step_name:
            return self.step_name
        return "DEFAULT" if self.engine_default else "SUPPLIED"

    def binding(self) -> dict[str, object] | None:
        if self.policy is None:
            return None
        return {"source_path": self.source_path, "source_sha256": self.source_sha256,
                "normalized_path": self.normalized_path, "normalized_sha256": self.normalized_sha256}


def own_exclusion_dk_ids(policy) -> tuple[str, ...]:
    """The exact DraftKings IDs a policy's own exclusions remove, both roles in Showdown."""

    if isinstance(policy, NormalizedClassicPortfolioPolicy):
        people = policy.people_by_id
        teams = {bound.entity_id for bound in policy.team_bounds if bound.maximum_entries == 0}
        games = {bound.entity_id for bound in policy.game_bounds if bound.maximum_entries == 0}
        return tuple(sorted(people[bound.entity_id].dk_id for bound in policy.player_bounds
                            if bound.exclusion_source == "POLICY_EXCLUSION"
                            or (bound.exclusion_source is None and bound.maximum_entries == 0)
                            or (bound.exclusion_source is None
                                and (people[bound.entity_id].team in teams
                                     or people[bound.entity_id].game_id in games))))
    if isinstance(policy, NormalizedPortfolioPolicy):
        zeroed = {item.person for item in policy.effective_limits
                  if item.exclusion_source is None and item.combined_fraction == 0}
        return tuple(sorted({dk_id for person in (*policy.excluded_people, *zeroed)
                             for dk_id in (person.cpt_dk_id, person.flex_dk_id)}))
    return ()


def concentration_state(policy, defaults: ConcentrationDefaults | None) -> int | None:
    """0 for a Showdown policy whose default fractions are exactly the registered pair, else None.

    The generator writes no provenance field, so the caps themselves are the key: a policy at
    the requested pair takes the cap steps before any structural rung, and any other value the
    operator wrote stays exactly theirs (Session 56).
    """

    if defaults is None or not isinstance(policy, NormalizedPortfolioPolicy):
        return None
    return 0 if defaults.matches(policy.combined_rule.default_fraction, policy.captain_rule.default_fraction) else None


def supplied_rung(policy, *, source_path, source_sha256, normalized_path, normalized_sha256,
                  defaults: ConcentrationDefaults | None = None) -> Rung:
    return Rung(None, policy, str(source_path) if source_path else None, source_sha256,
                str(normalized_path) if normalized_path else None, normalized_sha256,
                excluded_dk_ids=own_exclusion_dk_ids(policy), concentration=concentration_state(policy, defaults))


@dataclass(frozen=True)
class _Refused:
    codes: tuple[str, ...]
    relaxable: bool
    folder: str
    policy: NormalizedPortfolioPolicy | NormalizedClassicPortfolioPolicy | None = None  # what the validator built


def _limitation_text(code: str, detail: str) -> str:
    return f"{code}:{detail}"


def selection_overlap_steps(reports: Mapping[str, object] | None) -> list[dict[str, object]]:
    """Every Classic overlap-cap step a review's selection report names (Session 39).

    C1's own rows and the rows a subset policy leaves unbound each report the
    rows whose cap `_sequential_lineups` stepped up. The cap is a construction
    preference, so a step is a relaxation like a rung's; it is read from the
    structured report, never from text.
    """

    payload = (reports or {}).get("selection")
    payload = payload.get("selection") if isinstance(payload, Mapping) else None
    if not isinstance(payload, Mapping):
        return []
    fill = payload.get("unbound_fill")
    found: list[dict[str, object]] = []
    for scope, block in (("C1", payload), ("UNBOUND_FILL", fill if isinstance(fill, Mapping) else None)):
        differentiation = block.get("differentiation") if isinstance(block, Mapping) else None
        steps = differentiation.get("overlap_relaxations") if isinstance(differentiation, Mapping) else None
        for step in steps or ():
            if isinstance(step, Mapping):
                found.append({"scope": scope, **step})
    # Session 49: the preferences the thesis construction relaxed (bring-back, the person share
    # cap, the stack requirement), which the overlap steps above do not include.
    construction = payload.get("construction")
    for step in (construction.get("relaxations") if isinstance(construction, Mapping) else None) or ():
        if isinstance(step, Mapping):
            found.append({**step, "scope": "THESES"})
    # Session 23b: the teams whose backup quarterbacks no depth evidence orders, from the
    # SD3 report's `theses` block.
    policy = payload.get("portfolio_policy")
    theses = policy.get("theses") if isinstance(policy, Mapping) else None
    # A thesis dropped at validation, and a bound it widened, are named by the ladder from the
    # policy itself (`Ladder._policy_notes`), so they are named even when no selection reports.
    if isinstance(theses, Mapping):
        active = [item.get("name") for item in theses.get("theses") or ()
                  if isinstance(item, Mapping) and item.get("status") == "ACTIVE"]
        if active and theses.get("backup_quarterbacks_unevaluated_teams"):
            found.append({"scope": "THESIS", "constraint": "thesis_backup_quarterbacks", "thesis": active[0],
                          "teams": list(theses["backup_quarterbacks_unevaluated_teams"])})
    return found


THESIS_STEPS = {"thesis": "THESIS_DROP", "thesis_bound_override": "THESIS_BOUND_OVERRIDE",
                "thesis_backup_quarterbacks": "THESIS_EVIDENCE_GAP"}


def _thesis_step_text(step: Mapping[str, object]) -> str:
    if step["constraint"] == "thesis_bound_override":
        return _limitation_text(
            "PORTFOLIO_POLICY_THESIS_OVERRIDES_BOUND",
            f"thesis {step.get('thesis')} asks for counts the policy's bounds forbid, so they gave way for its rows:"
            f" {'; '.join(map(str, step.get('moved') or ()))}")
    if step["constraint"] == "thesis":
        others = step.get("others")
        return _limitation_text(
            "THESIS_DROPPED",
            f"thesis {step.get('thesis')} cannot be built and was dropped, not loosened: {step.get('reason')};"
            + (f" its rows went to the other theses ({', '.join(map(str, others))})" if others
               else " the bound rows were built without it and name no thesis"))
    return _limitation_text(
        "THESIS_BACKUP_QB_UNEVALUATED",
        f"thesis {step.get('thesis')}: no quarterback depth evidence orders {', '.join(map(str, step.get('teams') or ()))},"
        " so no backup quarterback of that team was excluded (R33's default needs the evidence; none was guessed)")


def concentration_not_applied_text(defaults: ConcentrationDefaults | None, reason: str) -> str:
    """The `S` limitation naming that a run's file was built without the registered concentration defaults (Session 56)."""

    held = ("the registered Showdown concentration defaults" if defaults is None else
            f"the registered Showdown concentration defaults ({defaults.person_fraction} a person,"
            f" {defaults.captain_fraction} a Captain, overlap {defaults.pairwise_person_overlap})")
    return _limitation_text("SHOWDOWN_CONCENTRATION_NOT_APPLIED",
                            f"{held} were not applied: {reason}; the delivered file was built without them")


def overlap_step_text(step: Mapping[str, object]) -> str:
    constraint = step.get("constraint", "classic_person_overlap")
    if constraint in THESIS_STEPS:
        return _thesis_step_text(step)
    return _limitation_text(
        "RELAXATION_STRUCTURE_RELAXED",
        f"{constraint} {step['from']} to {step['used']} for {step['scope']} row"
        f" {step['index']} after solver status {step['trigger_status']}: "
        + ("no distinct lineup fit under the cap" if constraint == "classic_person_overlap"
           else f"{str(step.get('reason', '')).lower().replace('_', ' ')} ({step.get('thesis', 'ALL')})")
        + "; lineups stay distinct (R29)")


def _plain(value: object) -> object:
    """JSON-safe: exact decimals as text."""

    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


class Ladder:
    """One run's walk down the rung ladder: the current rung, its attempts and records."""

    def __init__(
        self,
        *,
        slate,
        entries,
        folder: str | Path,
        supplied: Rung,
        registry: GateRegistry,
        externally_excluded_people: Sequence[str] = (),
        budget: Budget | None = None,
        rate: Callable[[], tuple[float, str]] = lambda: (DEFAULT_SECONDS_PER_CANDIDATE, "the default"),
        defaults: ConcentrationDefaults | None = None,
    ) -> None:
        self.slate = slate
        self.mode = slate.mode
        self.entries = entries
        # The rows a policy may bind: the template's fillable blank rows (Session 11).
        self.fillable = plan_entries(entries, slate).fillable
        # The rows the supplied policy binds, which every rung's policy binds too:
        # the fillable rows, or since Session 11b a subset of them. Rung 4 has no
        # policy and fills every fillable row.
        self.entry_ids = supplied.policy.entry_ids if supplied.policy is not None else self.fillable
        self.folder = Path(folder)
        self.registry = registry
        self.external = tuple(externally_excluded_people)
        self.budget = budget
        self.rate = rate
        self.current = supplied
        self.started_from = supplied
        self.records: list[dict[str, object]] = []
        self.attempts: list[dict[str, object]] = []
        self.stop: str | None = None
        self.defects: list[str] = []  # rungs the validator refused on a code no rung loosens
        self._attempt = -1  # the last attempt run; an intake relaxation feeds attempt 0
        self._bank_why = ""  # why the last bank step could not be taken
        self._defaults = defaults  # Session 56: read on first use, so a ladder that never needs it never opens the file
        self._policy_notes(supplied)

    @property
    def defaults(self) -> ConcentrationDefaults:
        if self._defaults is None:
            self._defaults = load_concentration_defaults()
        return self._defaults

    # -- what happened ------------------------------------------------------

    def observe(self, *, attempt: int, run_root: str | Path, outcome, failure: Failure | None,
                elapsed_seconds: float, pre_selection_seconds: float) -> None:
        self._attempt = attempt
        self.attempts.append({
            "attempt": attempt,
            "rung": self.current.label,
            "run_root": str(run_root),
            "policy": self.current.binding(),
            "showdown_candidate_limit": self.current.showdown_candidate_limit,
            "outcome": ("DELIVERED_TO_EXPORT" if outcome.file_valid
                        else f"{outcome.stage}_BLOCKED" if outcome.blocked else outcome.stage),
            "failure": failure.status if failure is not None else None,
            "elapsed_seconds": round(elapsed_seconds, 3),
            "pre_selection_seconds": round(pre_selection_seconds, 3),
        })
        # Session 39b: steps are read from every attempt's selection report, including one
        # whose selection succeeded and was then abandoned (a later stage failed and the ladder
        # went on). That over-reports a cap step that the delivered file did not use; it can
        # never under-report one, which is the side a relaxation record must err on.
        for step in selection_overlap_steps(getattr(outcome, "reports", None)):
            self._record_overlap_step(attempt, step)

    # -- the next rung ------------------------------------------------------

    def next(self, failure: Failure, *, overhead_seconds: float = 0.0) -> Rung | None:
        """The rung to try after `failure`, recorded; None when the ladder ends.

        An end the window forces is recorded as `stop`; a failure that is not a
        trigger, or a failure at rung 4, ends it with nothing to record.
        """

        current = self.current
        if current.policy is None or current.rung == NO_POLICY_RUNG or failure.kind not in {
                STRUCTURE, THROUGHPUT, SOLVER_ERROR, BANK_DEPTH}:
            return None
        if failure.status == THESIS_UNBUILDABLE and isinstance(current.policy, NormalizedPortfolioPolicy) \
                and current.policy.active_thesis is not None:
            return self._drop_thesis(current, failure, overhead_seconds)
        if failure.kind != STRUCTURE and current.bank_steps == 0:
            candidate = self._bank_step(current, failure, overhead_seconds)
            if candidate is not None:
                return self._take(candidate, failure, step="BANK")
        if failure.kind in {THROUGHPUT, SOLVER_ERROR}:
            return self._no_policy(current, failure, overhead_seconds,
                                   why="the bank was already re-sized at this rung, and structure does not fix"
                                       " throughput" if current.bank_steps else self._bank_why)
        return self._structural(current, failure, overhead_seconds)

    def _window(self, overhead_seconds: float) -> float | None:
        if self.budget is None:
            return None
        left = 0.0 if self.budget.passed_at_start else self.budget.improvement_remaining()
        return left - max(0.0, overhead_seconds)

    def _classic_rate(self, failure: Failure, policy: NormalizedClassicPortfolioPolicy) -> tuple[float, str]:
        seconds, basis = self.rate()
        produced = failure.facts.get("candidates")
        if failure.status in {"CANDIDATE_BANK_TIMEOUT", "CANDIDATE_BANK_SEARCH_LIMIT"} and isinstance(produced, int):
            declared = policy.search_limits.candidate_total_milliseconds / 1000.0
            observed = declared / max(1, produced)
            if observed > seconds:
                return observed, (f"{observed:g} s per candidate (this run: {produced} candidates in its"
                                  f" {declared:g} s bank budget)")
        return seconds, basis

    def _bank_step(self, current: Rung, failure: Failure, overhead_seconds: float) -> Rung | None:
        """The same structure on a re-sized bank; None when no re-sized bank changes or fits."""

        window = self._window(overhead_seconds)
        count = len(self.entry_ids)
        if isinstance(current.policy, NormalizedClassicPortfolioPolicy):
            policy = current.policy
            seconds, basis = self._classic_rate(failure, policy)
            cap = joint = None
            if failure.status in _JOINT_LIMITS or failure.kind == SOLVER_ERROR:
                cap = int(failure.facts.get("candidates") or policy.search_limits.candidate_limit) // 2
                joint = policy.search_limits.selection_milliseconds / 1000.0
            try:
                limits = classic_limits(count, len(policy.people), current.rung or 0, minutes=DEFAULT_MINUTES,
                                        seconds_per_candidate=seconds, window_seconds=window, candidate_cap=cap,
                                        minimum_selection_seconds=joint)
            except BankDoesNotFit as exc:
                self._bank_why = f"no re-sized bank fits the window at {basis}: {exc}"
                return None
            if limits == policy.search_limits.as_mapping():
                self._bank_why = f"a bank re-sized at {basis} is the bank that failed"
                return None
            document = classic_portfolio_policy_template(
                self.slate, self.entry_ids, entry_sha256=self.entries.raw_hash,
                controls=classic_relaxed_controls(policy, None), limits=limits)
            made = self._materialize(document, current.rung, bank=True)
            if isinstance(made, Rung):
                return replace(made, bank_steps=1)
            if not made.relaxable:
                self._unbuildable(failure, f"the re-sized bank's policy was refused by the validator"
                                           f" ({', '.join(made.codes)}, {made.folder})")
            self._bank_why = f"the re-sized bank's policy was refused ({', '.join(made.codes)})"
            return None
        # SD3's bank budget is the deadline's (`Budget.policy_search_seconds`); its size is the lever.
        default = current.showdown_candidate_limit or scaled_candidate_limit(count)
        produced = failure.facts.get("candidates")
        produced = produced if isinstance(produced, int) and produced > 0 else None
        if failure.kind == BANK_DEPTH:
            limit = max(SHOWDOWN_DEEP_BANK_PER_ENTRY * count, (3 * default) // 2)
        elif failure.status in _SD3_BANK_LIMITS and (produced or 0) < count:
            self._bank_why = (f"the bank built {produced or 0} of the {count} candidates the entries need in"
                              " its budget, so a smaller target is no help")
            return None
        else:
            limit = max(count, (produced or default) // 2)
            if limit >= default:
                self._bank_why = f"the bank is already at its least useful size ({default})"
                return None
        if window is not None and window < SD3_MINIMUM_WINDOW_SECONDS:
            self._bank_why = f"the window cannot hold a bank and joint solve ({max(0.0, window):.1f} s left)"
            return None
        if current.engine_default and not self._capped_search_fits(window):
            self._bank_why = (f"the window ({max(0.0, window):.1f} s) cannot hold another capped bank and joint solve"
                              " and still keep rung 4 its own time")
            return None
        return replace(current, showdown_candidate_limit=limit, bank_steps=1)

    def _structural(self, current: Rung, failure: Failure, overhead_seconds: float) -> Rung | None:
        # Session 56: a defaults-keyed Showdown policy gives its caps way before any structural rung.
        if self.mode is EngineMode.SHOWDOWN and current.rung is None and current.concentration is not None:
            moved = self._concentration_step(current, failure, overhead_seconds)
            if moved is not _CONTINUE:
                return moved
        start = 0 if current.rung is None else current.rung + 1
        if self.mode is EngineMode.SHOWDOWN:
            start = max(start, 1)
        window = self._window(overhead_seconds)
        count = len(self.entry_ids)
        for rung in range(start, NO_POLICY_RUNG):
            if isinstance(current.policy, NormalizedClassicPortfolioPolicy):
                policy = current.policy
                controls = classic_relaxed_controls(policy, rung)
                if controls == classic_relaxed_controls(policy, None):
                    continue
                seconds, _basis = self._classic_rate(failure, policy)
                try:
                    limits = classic_limits(count, len(policy.people), rung, minutes=DEFAULT_MINUTES,
                                            seconds_per_candidate=seconds, window_seconds=window)
                except BankDoesNotFit as exc:
                    return self._no_policy(current, failure, overhead_seconds,
                                           why=f"the window cannot hold rung {rung}'s declared search: {exc}")
                document = classic_portfolio_policy_template(
                    self.slate, self.entry_ids, entry_sha256=self.entries.raw_hash, controls=controls,
                    limits=limits)
            else:
                # `concentration` only for a defaults-keyed policy, so every other policy takes the exact call it always did.
                keyed = {} if current.concentration is None else {"concentration": current.concentration}
                controls = showdown_relaxed_controls(current.policy, rung, **keyed)
                if controls == showdown_relaxed_controls(current.policy, None):
                    continue
                if window is not None and window < SD3_MINIMUM_WINDOW_SECONDS:
                    return self._no_policy(current, failure, overhead_seconds,
                                           why=f"the window cannot hold rung {rung}'s bank and joint solve"
                                               f" ({max(0.0, window):.1f} s left, {SD3_MINIMUM_WINDOW_SECONDS:g} s"
                                               " the least)")
                document = portfolio_policy_template(
                    self.slate, self.entry_ids, controls=controls,
                    schema_version=showdown_schema_version(current.policy),
                )
            made = self._materialize(document, rung, bank=False)
            if isinstance(made, _Refused):
                if made.relaxable:
                    continue  # a looser rung may still pass; the refusal is in `attempts`
                # Not a preference the next rung could loosen: a defect, named; the
                # floor needs no generated policy, so it is still tried.
                self._unbuildable(failure, f"rung {rung}'s policy was refused by the validator"
                                           f" ({', '.join(made.codes)}, {made.folder})")
                return self._no_policy(current, failure, overhead_seconds,
                                       why=f"rung {rung}'s policy could not be built")
            return self._take(replace(made, showdown_candidate_limit=current.showdown_candidate_limit),
                              failure, step="STRUCTURE")
        return self._no_policy(current, failure, overhead_seconds, why="no structural rung is left")

    def _capped_search_fits(self, window: float | None) -> bool:
        """Another capped bank and joint solve fits `window` and still leaves rung 4 its own time.

        The engine default's rule (Session 56), applied before each of its SD3 attempts: a capped search that
        used the window up would leave the baseline as the file where the sequential floor would have delivered.
        A supplied policy keeps the ladder's older rule (SD3's least window only).
        """

        if window is None:
            return True
        count = len(self.fillable)
        return window >= (scaled_candidate_seconds(count) + scaled_selection_seconds(count)
                          + (count + 1) * SOLVE_MINIMUM_SECONDS)

    def _concentration_step(self, current: Rung, failure: Failure, overhead_seconds: float):
        """The next concentration cap step as a Rung; None when the ladder ended; `_CONTINUE` when none is left.

        The same policy with its two default fractions loosened to the registered step's
        (loosest of the two, so nothing tightens); its overrides, exclusions and structural
        bounds are untouched. A step the validator refuses on `S` codes is passed over for the
        next, looser one. The engine's own default has no uncapped step: after the last capped
        one its off is rung 4, which keeps a distinct Captain per row, where an uncapped joint
        solve would not (the registered `step_notes`).
        """

        steps = self.defaults.steps_for(ENGINE_DEFAULT if current.engine_default else POLICY)
        window = self._window(overhead_seconds)
        for index in range(current.concentration, len(steps)):
            step = steps[index]
            if current.engine_default and not self._capped_search_fits(window):
                return self._no_policy(current, failure, overhead_seconds,
                                       why=f"the window ({max(0.0, window):.1f} s) cannot hold another capped bank and"
                                           f" joint solve and still keep rung 4 its own time")
            if window is not None and window < SD3_MINIMUM_WINDOW_SECONDS:
                return self._no_policy(current, failure, overhead_seconds,
                                       why=f"the window cannot hold cap step {step.name}'s bank and joint solve"
                                           f" ({max(0.0, window):.1f} s left, {SD3_MINIMUM_WINDOW_SECONDS:g} s the least)")
            document = portfolio_policy_template(
                self.slate, self.entry_ids, controls=self._capped_controls(current.policy, step),
                schema_version=showdown_schema_version(current.policy))
            made = self._materialize(document, None, bank=False, label=step.name)
            if isinstance(made, _Refused):
                if made.relaxable:
                    continue  # a looser step may still pass; the refusal is in `attempts`
                self._unbuildable(failure, f"cap step {step.name}'s policy was refused by the validator"
                                           f" ({', '.join(made.codes)}, {made.folder})")
                return self._no_policy(current, failure, overhead_seconds,
                                       why=f"cap step {step.name}'s policy could not be built")
            return self._take(
                replace(made, concentration=index + 1, step_name=step.name, engine_default=current.engine_default,
                        showdown_candidate_limit=current.showdown_candidate_limit),
                failure, step="CONCENTRATION")
        if current.engine_default:
            return self._no_policy(
                current, failure, overhead_seconds,
                why="every capped step is spent; rung 4, sequential selection with a distinct Captain per row, is the"
                    " engine default's off")
        return _CONTINUE

    @staticmethod
    def _capped_controls(policy: NormalizedPortfolioPolicy, step: ConcentrationStep) -> dict[str, object]:
        controls = showdown_relaxed_controls(policy, None)
        for key, fraction in (("max_combined_person_exposure", step.person_fraction),
                              ("max_captain_exposure", step.captain_fraction)):
            rule = dict(controls[key])
            held = rule["default_fraction"]
            rule["default_fraction"] = None if held is None or fraction is None else max(held, fraction)
            controls[key] = rule
        return controls

    def begin_with_defaults(self, *, overlap: int | None = None) -> Rung:
        """Start a Showdown run that supplied no policy on the registered concentration defaults (Session 56).

        The requested pair (0.60 a person, 0.20 a Captain, overlap 4 unless the request named
        another), written and validated through `_materialize` exactly as a rung is, with every
        structural bound open and nothing excluded. A pair the validator refuses on `S` codes (a
        pool or entry count it cannot hold) is passed over for the registered looser step, each
        recorded; when none is accepted, or the window cannot hold the declared bank and joint
        solve and still leave rung 4 its own, the run starts at rung 4, the floor a no-policy
        Showdown run always had. Nothing here reads or relaxes an evidence gate.
        """

        defaults = self.defaults
        count = len(self.fillable)
        overlap = defaults.pairwise_person_overlap if overlap is None else overlap
        steps: list[ConcentrationStep | None] = [None, *defaults.steps_for(ENGINE_DEFAULT)]
        placeholder = Rung(None, None, engine_default=True, concentration=0)
        self.current = self.started_from = placeholder
        window = self._window(0.0)
        failure: Failure | None = None
        if not self._capped_search_fits(window):
            declared = scaled_candidate_seconds(count) + scaled_selection_seconds(count)
            failure = Failure(
                "DEADLINE_POLICY_SEARCH_EXCEEDS_WINDOW", THROUGHPUT,
                f"{max(0.0, window):.1f} s are left; the capped bank and joint solve declare {declared:g} s and rung 4's"
                f" {count} sequential solves need {(count + 1) * SOLVE_MINIMUM_SECONDS:g} s", {}, "DEADLINE")
            floor = self._no_policy(
                placeholder, failure, 0.0,
                why="the window cannot hold the capped bank and joint solve and still keep rung 4 its own time,"
                    " so the run starts at the floor")
            return floor if floor is not None else placeholder
        for index, step in enumerate(steps):
            label = "DEFAULT" if step is None else step.name
            person = defaults.person_fraction if step is None else step.person_fraction
            captain = defaults.captain_fraction if step is None else step.captain_fraction
            made = self._materialize(self._default_document(person, captain, overlap), None, bank=False, label=label)
            if isinstance(made, Rung):
                rung = replace(made, engine_default=True, concentration=index,
                               step_name=None if step is None else step.name)
                if index == 0:
                    self.current = self.started_from = rung
                    self._policy_notes(rung)
                    return rung
                return self._take(rung, failure, step="CONCENTRATION")
            failure = Failure((made.codes or ("RELAXATION_RUNG_UNBUILDABLE",))[0], STRUCTURE,
                              "; ".join(made.codes), {"codes": list(made.codes)}, "INTAKE")
            if not made.relaxable or made.policy is None:
                self._unbuildable(failure, f"the {label} policy was refused by the validator"
                                           f" ({', '.join(made.codes)}, {made.folder})")
                break
            self.current = Rung(None, made.policy, engine_default=True, concentration=index,
                                step_name=None if step is None else step.name)
            if index == 0:
                self.started_from = self.current
        floor = self._no_policy(self.current, failure, 0.0,
                                why="no capped step of the defaults passed validation for this pool and entry count")
        return floor if floor is not None else self.current

    def _default_document(self, person, captain, overlap: int) -> dict[str, object]:
        return portfolio_policy_template(
            self.slate, self.fillable,
            controls={
                "fraction_unit": FRACTION_UNIT,
                "max_combined_person_exposure": {"default_fraction": person, "overrides": []},
                "max_captain_exposure": {"default_fraction": captain, "overrides": []},
                "excluded_people": [],
                "max_pairwise_person_overlap": overlap,
                "require_unique_lineups": True,
                "structural_bounds": _showdown_relaxed_structural_bounds(OPEN_STRUCTURAL_BOUNDS, None),
            },
            schema_version=POLICY_SCHEMA_VERSION_V2)

    def _drop_thesis(self, current: Rung, failure: Failure, overhead_seconds: float) -> Rung | None:
        """The same policy without the theses no lineup can follow (Session 23b, per thesis since 23c).

        Not a rung: every cap and bound is as declared (a bound a thesis widened is restored). The drop is
        recorded by name, one record per thesis. A portfolio (v4) loses exactly the theses the failure names
        and is rebuilt with the rest, byte for byte as declared, their weights unchanged so the dropped
        theses' rows flow to them; when none is left the policy is built without theses (v2). A rebuilt policy
        the validator refuses, or a window too short for another SD3 attempt, leaves rung 4, which needs none.
        """

        window = self._window(overhead_seconds)
        if window is not None and window < SD3_MINIMUM_WINDOW_SECONDS:
            return self._no_policy(current, failure, overhead_seconds,
                                   why=f"the window cannot hold the policy without its thesis"
                                       f" ({max(0.0, window):.1f} s left)")
        policy = current.policy
        active = {thesis.name for thesis in policy.active_theses}
        named = {str(name) for name in (failure.facts.get("theses") or [failure.facts.get("thesis")]) if name}
        gone = (named & active) or active
        controls = {key: value for key, value in showdown_relaxed_controls(policy, None).items()
                    if key != "theses"}
        kept = [thesis for thesis in policy.theses if thesis.name not in gone]
        schema = POLICY_SCHEMA_VERSION_V2
        if policy.thesis_schema == "v4" and any(thesis.active for thesis in kept):
            controls["theses"] = [thesis.source_mapping() for thesis in kept]
            schema = POLICY_SCHEMA_VERSION_V4
        document = portfolio_policy_template(self.slate, self.entry_ids, controls=controls, schema_version=schema)
        made = self._materialize(document, current.rung, bank=False, suffix="_thesis_dropped")
        if isinstance(made, _Refused):
            return self._no_policy(current, failure, overhead_seconds,
                                   why=f"the policy without its thesis was refused ({', '.join(made.codes)})")
        reasons = failure.facts.get("reasons") if isinstance(failure.facts.get("reasons"), Mapping) else {}
        fallback = str(failure.facts.get("reason") or failure.detail)
        survivors = [thesis.name for thesis in made.policy.active_theses]
        why = {
            f"theses.{name}": (f"no lineup can follow it: {reasons.get(name, fallback)}"
                               + (f"; its rows went to {', '.join(survivors)}" if survivors else ""))
            for name in sorted(gone)}
        # The caps are exactly the current rung's, so its concentration state (Session 56) carries across the drop.
        return self._take(replace(made, showdown_candidate_limit=current.showdown_candidate_limit,
                                  concentration=current.concentration, step_name=current.step_name,
                                  engine_default=current.engine_default),
                          failure, step="THESIS_DROP", why=why)

    def _no_policy(self, current: Rung, failure: Failure, overhead_seconds: float, *, why: str) -> Rung | None:
        window = self._window(overhead_seconds)
        needed = (len(self.fillable) + 1) * SOLVE_MINIMUM_SECONDS
        if window is not None and window < needed:
            self._stop(failure, f"rung 4 needs {needed:g} s for {len(self.fillable)} sequential solves and"
                                f" {max(0.0, window):.1f} s are left after the last attempt's"
                                f" {max(0.0, overhead_seconds):.1f} s before selection ({why}); the ladder"
                                " stopped and the baseline is the file")
            return None
        floor = Rung(NO_POLICY_RUNG, None, excluded_dk_ids=current.excluded_dk_ids)
        return self._take(floor, failure, step="NO_POLICY", why=why)

    # -- artifacts and records ----------------------------------------------

    def _materialize(self, document: Mapping[str, object], rung: int | None, *, bank: bool,
                     suffix: str = "", label: str | None = None) -> Rung | _Refused:
        """Write, hash, validate and normalize a rung's policy the way a supplied one is.

        `label` (Session 56) names a concentration cap step's folder and attempt record;
        without one a rung is its number, or `SUPPLIED` for the policy the run began with.
        """

        shown = label or ("SUPPLIED" if rung is None else str(rung))
        name = f"attempt_{self._attempt + 1}_rung_{shown}"
        folder = self.folder / (name + ("_bank" if bank else "") + suffix)
        folder.mkdir(parents=True, exist_ok=False)  # never over an earlier output
        raw = canonical_decimal_json_bytes(_exact_decimals(document)) + b"\n"
        source = folder / "portfolio_policy.json"
        source.write_bytes(raw)
        digest = sha256_bytes(raw)
        if self.mode is EngineMode.CLASSIC:
            validation = validate_classic_portfolio_policy_file(
                source, slate=self.slate, entry_ids=self.fillable, entry_sha256=self.entries.raw_hash,
                externally_excluded_people=self.external, expected_sha256=digest)
            write_classic_portfolio_policy_validation(folder / "portfolio_policy_validation.json", validation)
        else:
            validation = validate_portfolio_policy_file(
                source, slate=self.slate, entry_ids=self.fillable,
                externally_excluded_people=self.external, expected_sha256=digest)
            write_portfolio_policy_validation(folder / "portfolio_policy_validation.json", validation)
        normalized = folder / "portfolio_policy.normalized.json"
        if validation.policy is not None:
            if self.mode is EngineMode.CLASSIC:
                write_normalized_classic_portfolio_policy(normalized, validation.policy)
            else:
                write_normalized_portfolio_policy(normalized, validation.policy)
        if not validation.valid:
            codes = tuple(issue.code for issue in validation.problems)
            refused = _Refused(codes, intake_failure(codes, self.registry) is not None, str(folder), validation.policy)
            self.attempts.append({"attempt": None, "rung": shown,
                                  "outcome": "REFUSED_AT_VALIDATION", "codes": list(codes),
                                  "policy": {"source_path": str(source), "source_sha256": digest}})
            return refused
        return Rung(rung, validation.policy, str(source), digest, str(normalized),
                    validation.policy.normalized_sha256, excluded_dk_ids=own_exclusion_dk_ids(validation.policy))

    def _take(self, new: Rung, failure: Failure, *, step: str, why: str | Mapping[str, str] = "") -> Rung:
        """Record each change and make `new` the current rung.

        `why` is one reason for every record, or (Session 23c, a thesis drop) a mapping from a record's
        constraint to its own reason, because each dropped thesis has one.
        """

        old = self.current
        changes = self._changes(old, new, thesis_drop=step == "THESIS_DROP")
        if step == "CONCENTRATION" and isinstance(old.policy, NormalizedPortfolioPolicy) \
                and isinstance(new.policy, NormalizedPortfolioPolicy):
            # Session 56: the two default fractions are one preference, so one record (and one limitation) names the
            # step, in place of one for each fraction `_changes` compared.
            caps = {"max_combined_person_exposure", "max_captain_exposure"}
            pair = lambda policy: {"person_fraction": policy.combined_rule.default_fraction,  # noqa: E731
                                   "captain_fraction": policy.captain_rule.default_fraction}
            changes = [("concentration_defaults", _plain(pair(old.policy)), _plain(pair(new.policy)), "CONCENTRATION"),
                       *(change for change in changes if change[0] not in caps)]
        for constraint, original, final, kind in changes:
            self._record(old, new, failure, step=step, constraint=constraint, original=original,
                         final=final, kind=kind,
                         why=(why.get(constraint, "") if isinstance(why, Mapping) else why))
        self.current = new
        self._policy_notes(new)
        return new

    def _policy_notes(self, rung: Rung) -> None:
        """Name what a rung's own validation did to its thesis (Session 23b), once each.

        A thesis it dropped and a count bound it widened for one are read from the
        policy, not from a selection report, so they are named even when no attempt
        reaches selection.
        """

        policy = rung.policy
        if not isinstance(policy, NormalizedPortfolioPolicy):
            return
        others = [thesis.name for thesis in policy.active_theses] if policy.thesis_schema == "v4" else []
        for thesis in policy.theses:
            if not thesis.active:
                self._record_overlap_step(self._attempt + 1, {
                    "scope": "THESIS", "constraint": "thesis", "thesis": thesis.name, "reason": thesis.dropped_reason,
                    **({"others": others} if others else {})})
        if policy.thesis_schema == "v4":
            # Each thesis widened the declared bounds for its own rows alone, so each is named with its scope.
            for thesis in policy.active_theses:
                if thesis.widened:
                    self._record_overlap_step(self._attempt + 1, {
                        "scope": "THESIS", "constraint": "thesis_bound_override", "thesis": thesis.name,
                        "moved": list(thesis.widened)})
        elif policy.thesis_bound_overrides and policy.active_thesis is not None:
            self._record_overlap_step(self._attempt + 1, {
                "scope": "THESIS", "constraint": "thesis_bound_override", "thesis": policy.active_thesis.name,
                "moved": list(policy.thesis_bound_overrides)})

    def _concentration_ended(self, old: Rung) -> list[tuple[str, object, object, str]]:
        """The record that rung 4 ends a policy's concentration caps (Session 56): the sequential floor has none."""

        if old.concentration is None:
            return []
        policy = old.policy
        held = ({"person_fraction": policy.combined_rule.default_fraction,
                 "captain_fraction": policy.captain_rule.default_fraction}
                if isinstance(policy, NormalizedPortfolioPolicy) else
                {"person_fraction": self.defaults.person_fraction, "captain_fraction": self.defaults.captain_fraction})
        return [("concentration_defaults", _plain(held),
                 {"person_fraction": None, "captain_fraction": None,
                  "selection": "SEQUENTIAL_DISTINCT_CAPTAINS_UNTIL_THE_POOL_RUNS_OUT"}, "CONCENTRATION")]

    def _changes(self, old: Rung, new: Rung, *, thesis_drop: bool = False) -> list[tuple[str, object, object, str]]:
        # Session 23b: each active thesis the step drops, by name, before what else changed. Since 23c a drop may
        # keep some of a portfolio's theses, so a thesis is dropped only when the new policy no longer holds it.
        kept = {thesis.name for thesis in getattr(new.policy, "theses", ())} if new.policy is not None else set()
        dropped = [(f"theses.{thesis.name}", thesis.source_mapping(), None, "THESIS_DROP")
                   for thesis in getattr(old.policy, "theses", ()) if thesis.active
                   and (new.policy is None or (thesis_drop and thesis.name not in kept))]
        if new.policy is None:
            return [*dropped, *self._concentration_ended(old), ("portfolio_policy",
                     {"rung": old.label, "normalized_sha256": old.normalized_sha256},
                     {"rung": new.label, "policy": None,
                      "carried_exclusion_dk_ids": list(new.excluded_dk_ids),
                      **({"construction": THESIS_CONSTRUCTION_VERSION}
                         if self.mode is EngineMode.CLASSIC else {})}, "DROP")]
        if isinstance(new.policy, NormalizedPortfolioPolicy):
            before_theses = {item.name: item.source_mapping() for item in getattr(old.policy, "theses", ())}
            after_theses = {item.name: item.source_mapping() for item in new.policy.theses}
            # A thesis is never relaxed: a rung that changed one (or, outside a thesis drop, lost one) is a
            # defect, never taken. A thesis drop may remove theses, and every thesis it keeps is byte for byte.
            if (any(before_theses.get(name) != mapping for name, mapping in after_theses.items())
                    or (not thesis_drop and set(before_theses) != set(after_theses))
                    or [item.name for item in getattr(old.policy, "theses", ()) if item.name in after_theses]
                    != [item.name for item in new.policy.theses]):
                raise ValueError(
                    "RELAXATION_RUNG_UNBUILDABLE: a rung's policy changed a Showdown thesis, which no rung may relax")
        changes: list[tuple[str, object, object, str]] = list(dropped)

        def compare(constraint: str, before: object, after: object, kind: str = "STRUCTURE") -> None:
            if before != after:
                changes.append((constraint, _plain(before), _plain(after), kind))

        if isinstance(new.policy, NormalizedClassicPortfolioPolicy):
            before, after = old.policy, new.policy
            rules = {rule.rule_id: rule.as_mapping() for rule in before.stack_rules}
            for rule in after.stack_rules:
                compare(f"stack_rules.{rule.rule_id}", rules.get(rule.rule_id), rule.as_mapping())
            for name in ("player_bounds", "team_bounds", "game_bounds"):
                compare(name.replace("bounds", "exposure_bounds"),
                        _bound_summary(getattr(before, name), before.entry_count),
                        _bound_summary(getattr(after, name), after.entry_count))
            compare("groups", [(group.group_id, group.strength, group.minimum_entries) for group in before.groups],
                    [(group.group_id, group.strength, group.minimum_entries) for group in after.groups])
            compare("max_pairwise_person_overlap", before.max_pairwise_person_overlap,
                    after.max_pairwise_person_overlap)
            compare("structural_bounds", before.structural_bounds.as_mapping(),
                    after.structural_bounds.as_mapping())
            compare("max_person_share", before.max_person_share, after.max_person_share)
            compare("search_limits", before.search_limits.as_mapping(), after.search_limits.as_mapping(), "BANK")
            return changes
        before, after = old.policy, new.policy
        if before is not after:
            compare("max_combined_person_exposure", _rule_summary(before.combined_rule),
                    _rule_summary(after.combined_rule))
            compare("max_captain_exposure", _rule_summary(before.captain_rule), _rule_summary(after.captain_rule))
            compare("max_pairwise_person_overlap", before.max_pairwise_person_overlap,
                    after.max_pairwise_person_overlap)
            # A thesis drop restores the bounds as declared; that is not a relaxation (Session 23b).
            declared = (before.declared_structural_bounds or before.structural_bounds) if thesis_drop \
                else before.structural_bounds
            compare("structural_bounds", declared.as_mapping(), after.structural_bounds.as_mapping())
        count = len(self.entry_ids)
        compare("candidate_bank.candidate_limit", old.showdown_candidate_limit or scaled_candidate_limit(count),
                new.showdown_candidate_limit or scaled_candidate_limit(count), "BANK")
        return changes

    def _record(self, old: Rung, new: Rung, failure: Failure, *, step: str, constraint: str,
                original: object, final: object, kind: str, why: str) -> None:
        detail = (f"attempt {self._attempt + 1}, {step} step, rung {old.label} to {new.label} on"
                  f" {failure.status}: {constraint} {original} to {final}"
                  + (f"; {why}" if why else "")
                  + (f"; policy {new.normalized_sha256}" if new.policy is not None else "; no policy"))
        if kind == "BANK":
            text = _limitation_text("RELAXATION_BANK_RESIZED", detail)
        elif kind == "DROP":
            text = _limitation_text("RELAXATION_POLICY_DROPPED", detail)
        elif kind == "THESIS_DROP":
            text = _limitation_text("THESIS_DROPPED", detail)
        elif kind == "CONCENTRATION":
            text = _limitation_text("SHOWDOWN_CONCENTRATION_RELAXED", detail)
        else:
            text = _limitation_text("RELAXATION_STRUCTURE_RELAXED", detail)
        code = text.split(":", 1)[0]
        family = self.registry.family_of(code)
        self.records.append({
            "schema_version": CONTRACT_VERSION,
            "sequence": len(self.records) + 1,
            "attempt": self._attempt + 1,
            "step": step,
            "constraint": constraint,
            "class": family.gate_class.value,
            "family": family.name,
            "provenance": family.provenance.model_dump(mode="json"),
            "original": original,
            "final": final,
            "trigger": failure.status,
            "trigger_kind": failure.kind,
            "trigger_origin": failure.origin,
            "trigger_detail": failure.detail[:600],
            "rung_from": old.label,
            "rung_to": new.label,
            "why": why or None,
            "at_utc": self._now(),
            "elapsed_seconds": round(self.budget.elapsed(), 3) if self.budget is not None else None,
            "entry_ids": list(self.entry_ids),
            "policy": new.binding(),
            "limitation_code": code,
            "limitation_text": text,
        })

    def _record_overlap_step(self, attempt: int, step: Mapping[str, object]) -> None:
        """A Classic overlap-cap step the selection took inside one attempt (Session 39).

        Not a rung move: `rung_from` and `rung_to` are the rung the attempt ran, and
        `attempt` is that attempt's own number (as in `attempts`), because the step
        happened inside it rather than feeding the next.
        """

        text = overlap_step_text(step)
        thesis_step = step.get("constraint") in THESIS_STEPS
        if thesis_step and any(record["limitation_text"] == text for record in self.records):
            return  # a thesis event every rung or attempt reports again is recorded once (Session 23b)
        code = text.split(":", 1)[0]
        family = self.registry.family_of(code)
        binding = self.current.binding()
        self.records.append({
            "schema_version": CONTRACT_VERSION,
            "sequence": len(self.records) + 1,
            "attempt": attempt,
            "step": (THESIS_STEPS[step["constraint"]] if thesis_step
                     else "OVERLAP_CAP" if step.get("constraint", "classic_person_overlap") == "classic_person_overlap"
                     else "THESIS_PREFERENCE"),
            "constraint": step.get("constraint", "classic_person_overlap"),
            "class": family.gate_class.value,
            "family": family.name,
            "provenance": family.provenance.model_dump(mode="json"),
            "original": step.get("thesis") if thesis_step else step["from"],
            "final": None if thesis_step else step["used"],
            "trigger": code if thesis_step else step["trigger_status"],
            "trigger_kind": STRUCTURE,
            "trigger_origin": ("SELECTION" if not thesis_step or step["constraint"] == "thesis_backup_quarterbacks"
                               else "POLICY_VALIDATION"),
            "trigger_detail": (text if thesis_step else f"{step['scope']} row {step['index']}: {step['reason']}")[:600],
            "rung_from": self.current.label,
            "rung_to": self.current.label,
            "why": ("a thesis is dropped and named, never loosened" if step.get("constraint") == "thesis"
                    else "a policy bound gave way to the thesis Ben chose for its rows"
                    if step.get("constraint") == "thesis_bound_override"
                    else "missing evidence is never permission to guess" if thesis_step
                    else "a construction preference; distinct lineups (R29) are never relaxed"),
            "at_utc": self._now(),
            "elapsed_seconds": round(self.budget.elapsed(), 3) if self.budget is not None else None,
            "entry_ids": list(self.entry_ids),
            "policy": binding,
            "limitation_code": code,
            "limitation_text": text,
        })

    def halt(self, failure: Failure, exc: BaseException) -> None:
        """End the ladder by name when the next rung could not be built at all."""

        self.stop = _limitation_text(
            "RELAXATION_RUNG_UNBUILDABLE",
            f"after {failure.status} at rung {self.current.label}: the next rung could not be built"
            f" ({type(exc).__name__}: {exc}); the ladder stopped and the baseline stays the file")

    def _unbuildable(self, failure: Failure, detail: str) -> None:
        self.defects.append(_limitation_text(
            "RELAXATION_RUNG_UNBUILDABLE", f"after {failure.status} at rung {self.current.label}: {detail}"))

    def _stop(self, failure: Failure, detail: str) -> None:
        self.stop = _limitation_text("RELAXATION_LADDER_STOPPED",
                                     f"after {failure.status} at rung {self.current.label}: {detail}")

    def _now(self) -> str:
        moment = self.budget.now() if self.budget is not None else datetime.now(timezone.utc)
        return moment.astimezone(timezone.utc).isoformat()

    # -- reporting ----------------------------------------------------------

    def texts(self) -> list[str]:
        """Each relaxation and the stop as `CODE:detail`, the form a run's blockers take."""

        return ([str(record["limitation_text"]) for record in self.records] + list(self.defects)
                + ([self.stop] if self.stop else []))

    def as_record(self) -> dict[str, object]:
        return {
            "schema_version": CONTRACT_VERSION,
            "mode": self.mode.value,
            "started_from": {"rung": self.started_from.label, "policy": self.started_from.binding()},
            "final_rung": self.current.label,
            "final_policy": self.current.binding(),
            "attempts": list(self.attempts),
            "relaxations": list(self.records),
            "stop": self.stop,
            "defects": list(self.defects),
            # R29: every rung requires distinct lineups, whatever the supplied policy said.
            "supplied_require_unique_lineups": (
                self.started_from.policy.require_unique_lineups
                if self.started_from.policy is not None else None),
            "never_relaxed": list(NEVER_RELAXED),
            "does_not_establish": list(DOES_NOT_ESTABLISH),
        }


def _bound_summary(bounds, count: int) -> dict[str, object]:
    bounded = [bound for bound in bounds if bound.exclusion_source is None
               and (bound.minimum_entries, bound.maximum_entries) != (0, count)]
    return {
        "bounded": len(bounded),
        "maximum_entries": sorted({bound.maximum_entries for bound in bounded}),
        "minimum_entries_total": sum(bound.minimum_entries for bound in bounded),
        "excluded": sum(1 for bound in bounds if bound.exclusion_source is not None),
    }


def _rule_summary(rule: ExposureRule) -> dict[str, object]:
    return {
        "default_fraction": rule.default_fraction,
        "overrides": len(rule.overrides),
        "zeroed": sum(1 for item in rule.overrides if item.fraction == 0),
        "override_fractions": sorted({item.fraction for item in rule.overrides}),
    }
