"""Availability contract derived from the DraftKings salary Status column.

R03, selection side. `dk.py` has always parsed `status_raw` onto every
`SalaryPlayer` and nothing has ever read it, so a person DraftKings has flagged
`OUT` stays selectable by the solver and scoreable by the simulator. The
retained review probe measured a zero-capacity kicker averaging 7.99 points
across 984 of 1,000 scenarios.

This module owns one question: who may be selected. It answers from the salary
file's own bytes, moves both Showdown roles of a person together, and refuses a
status vocabulary it does not recognize rather than guessing that an unknown
code means available.

`D` (doubtful) is recognized natively and classified unavailable. On
2026-09-13 it was not, so a real Classic slate stopped on `UNKNOWN_DK_STATUS:D`
until the operator remembered `--unavailable-status D` by hand, which is a
default masquerading as a decision. An operator who wants a doubtful person in
the pool says `--available-status D`, and that now overrides the default
instead of colliding with it.

What it deliberately does not do: it does not touch the simulator's scoring
path. The full R03 contract in tranche `W3` still owns the availability mask
inside `simulation.py`. A prior-only selection never simulates, so filtering the
candidate pool is sufficient here and is not a substitute for that work.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from .contracts import (
    UNAVAILABLE_DK_STATUSES,
    EngineMode,
    SalaryPlayer,
    SlateContract,
)
from .opportunity import OpportunityError, OpportunityModel, remove_inactive_and_redistribute


CONTRACT_VERSION = "dk_status_participation_v1"

# DraftKings' own vocabulary in the salary export's Status column, as observed.
# An empty cell is the site's way of saying nothing is flagged.
AVAILABLE_STATUSES = frozenset({""})
# Defined once in `contracts.py`, because `priors.py`, `projection.py` and
# `opportunity.py` each re-derive the same set to decide whether a person
# missing from their inputs is a tolerable absence. See the note there.
UNAVAILABLE_STATUSES = UNAVAILABLE_DK_STATUSES
# Flagged but still permitted to play. Reported, never silently excluded: fading
# a questionable player is an operator judgement, not a legality fact.
DEGRADED_STATUSES = frozenset({"Q"})


class ParticipationError(ValueError):
    """A named fail-closed availability error."""


@dataclass(frozen=True)
class ParticipationContract:
    contract_version: str
    status_by_person: dict[str, str]
    unavailable_people: tuple[str, ...]
    unavailable_dk_ids: tuple[str, ...]
    degraded_people: tuple[str, ...]
    available_people: tuple[str, ...]
    operator_excluded_people: tuple[str, ...]

    @property
    def selectable_people(self) -> tuple[str, ...]:
        blocked = set(self.unavailable_people) | set(self.operator_excluded_people)
        return tuple(person for person in self.available_people if person not in blocked)

    def as_report(self) -> dict[str, object]:
        return {
            "contract_version": self.contract_version,
            "people": len(self.status_by_person),
            "selectable_people": len(self.selectable_people),
            "unavailable_people": len(self.unavailable_people),
            "unavailable_dk_ids": len(self.unavailable_dk_ids),
            "degraded_people": len(self.degraded_people),
            "operator_excluded_people": len(self.operator_excluded_people),
            "unavailable_detail": [
                f"{person}:{self.status_by_person[person]}"
                for person in self.unavailable_people
            ],
            "degraded_detail": [
                f"{person}:{self.status_by_person[person]}"
                for person in self.degraded_people
            ],
            "basis": "DRAFTKINGS_SALARY_STATUS_COLUMN",
            "note": (
                "Availability governs selection only. The simulator's scoring path"
                " still lacks an availability mask; that is R03 and tranche W3 owns it."
            ),
        }


def _people(slate: SlateContract) -> dict[str, list[SalaryPlayer]]:
    grouped: dict[str, list[SalaryPlayer]] = {}
    for player in slate.players:
        grouped.setdefault(player.underlying_id, []).append(player)
    return grouped


def build_participation_contract(
    slate: SlateContract,
    *,
    operator_excluded_dk_ids: Iterable[str] = (),
    extra_unavailable_statuses: Iterable[str] = (),
    extra_available_statuses: Iterable[str] = (),
) -> ParticipationContract:
    """Classify every person in the pool as selectable or not.

    An unrecognized status is an error, not an assumption. DraftKings can
    introduce a code at any time, and defaulting an unknown code to available is
    the failure mode that puts a scratched player in a lineup. The operator can
    classify a new code explicitly through the two extension arguments, which are
    recorded in the report.
    """

    extra_unavailable = {
        value.strip().upper() for value in extra_unavailable_statuses if value.strip()
    }
    extra_available = {
        value.strip().upper() for value in extra_available_statuses if value.strip()
    }
    overlap = extra_unavailable & extra_available
    if overlap:
        raise ParticipationError(f"STATUS_CLASSIFIED_BOTH_WAYS:{sorted(overlap)}")
    # An explicit operator classification overrides the built-in default rather
    # than colliding with it, so `--available-status D` restores a doubtful
    # person to the pool instead of raising STATUS_CLASSIFIED_BOTH_WAYS. Only
    # the two operator sets may contradict each other; that is a typo, not a
    # judgement, and it still fails closed above.
    unavailable_vocabulary = (UNAVAILABLE_STATUSES | extra_unavailable) - extra_available
    available_vocabulary = (AVAILABLE_STATUSES | extra_available) - extra_unavailable

    grouped = _people(slate)
    by_dk_id = {player.dk_id: player for player in slate.players}
    excluded_ids = {str(value).strip() for value in operator_excluded_dk_ids if str(value).strip()}
    unknown_exclusions = sorted(excluded_ids.difference(by_dk_id))
    if unknown_exclusions:
        raise ParticipationError(f"OPERATOR_EXCLUSION_NOT_IN_POOL:{unknown_exclusions}")
    operator_excluded_people = sorted(
        {by_dk_id[dk_id].underlying_id for dk_id in excluded_ids}
    )

    status_by_person: dict[str, str] = {}
    unknown: dict[str, list[str]] = {}
    inconsistent: list[str] = []
    for person, rows in sorted(grouped.items()):
        statuses = {(row.status_raw or "").strip().upper() for row in rows}
        if len(statuses) != 1:
            # Both Showdown roles of a person must agree. A pool that disagrees
            # with itself about whether someone is playing is not a pool this
            # engine will resolve on its own.
            inconsistent.append(f"{person}:{sorted(statuses)}")
            continue
        status = statuses.pop()
        status_by_person[person] = status
        if (
            status not in unavailable_vocabulary
            and status not in available_vocabulary
            and status not in DEGRADED_STATUSES
        ):
            unknown.setdefault(status, []).append(person)

    if inconsistent:
        raise ParticipationError(
            "STATUS_INCONSISTENT_ACROSS_ROLES:" + ";".join(sorted(inconsistent)[:10])
        )
    if unknown:
        detail = ";".join(
            f"{status}={sorted(people)[:3]}" for status, people in sorted(unknown.items())
        )
        raise ParticipationError(
            f"UNKNOWN_DK_STATUS:{detail}"
            ":classify it with --unavailable-status or --available-status;"
            " an unrecognized code is never assumed available"
        )

    unavailable = tuple(
        person
        for person in sorted(status_by_person)
        if status_by_person[person] in unavailable_vocabulary
    )
    degraded = tuple(
        person
        for person in sorted(status_by_person)
        if status_by_person[person] in DEGRADED_STATUSES
    )
    available = tuple(
        person for person in sorted(status_by_person) if person not in set(unavailable)
    )
    # Every role row of an unavailable person, so CPT and FLEX move together.
    unavailable_dk_ids = tuple(
        sorted(
            (row.dk_id for person in unavailable for row in grouped[person]),
            key=int,
        )
    )
    return ParticipationContract(
        contract_version=CONTRACT_VERSION,
        status_by_person=status_by_person,
        unavailable_people=unavailable,
        unavailable_dk_ids=unavailable_dk_ids,
        degraded_people=degraded,
        available_people=available,
        operator_excluded_people=tuple(operator_excluded_people),
    )


def excluded_dk_ids(slate: SlateContract, contract: ParticipationContract) -> tuple[str, ...]:
    """Every DraftKings row the solver may not select, both Showdown roles."""

    grouped = _people(slate)
    blocked = set(contract.unavailable_people) | set(contract.operator_excluded_people)
    return tuple(
        sorted((row.dk_id for person in blocked for row in grouped[person]), key=int)
    )


def selectable_pool_problems(
    slate: SlateContract, contract: ParticipationContract
) -> tuple[str, ...]:
    """Report obvious mode-specific blockers before invoking the solver."""

    problems: list[str] = []
    selectable = set(contract.selectable_people)
    if slate.mode is EngineMode.CLASSIC:
        selectable_rows = [
            player for player in slate.players if player.underlying_id in selectable
        ]
        counts = {
            position: sum(player.position == position for player in selectable_rows)
            for position in ("QB", "RB", "WR", "TE", "DST")
        }
        required = {"QB": 1, "RB": 2, "WR": 3, "TE": 1, "DST": 1}
        for position, minimum in required.items():
            if counts[position] < minimum:
                problems.append(
                    f"SELECTABLE_CLASSIC_POSITION_SHORTAGE:{position}:"
                    f"available={counts[position]}:required={minimum}"
                )
        flex_count = counts["RB"] + counts["WR"] + counts["TE"]
        if flex_count < 7:
            problems.append(
                f"SELECTABLE_CLASSIC_FLEX_SHORTAGE:available={flex_count}:required=7"
            )
        games = {player.game_id for player in selectable_rows}
        if len(games) < 2:
            problems.append(
                f"SELECTABLE_CLASSIC_GAME_SHORTAGE:available={sorted(games)}:required=2"
            )
        return tuple(problems)
    if slate.mode is not EngineMode.SHOWDOWN:
        return ()
    if len(selectable) < 6:
        problems.append(
            f"SELECTABLE_POOL_TOO_SMALL:{len(selectable)}:a Showdown lineup needs six people"
        )
    teams = {
        player.team
        for player in slate.players
        if player.underlying_id in selectable
    }
    if len(teams) < 2:
        problems.append(f"SELECTABLE_POOL_SINGLE_TEAM:{sorted(teams)}")
    cheapest = sorted(
        (
            min(
                player.salary
                for player in slate.players
                if player.underlying_id == person and player.role == "FLEX"
            )
            for person in selectable
        )
    )
    captain = min(
        (
            player.salary
            for player in slate.players
            if player.underlying_id in selectable and player.role == "CPT"
        ),
        default=0,
    )
    if cheapest and captain + sum(cheapest[:5]) > slate.salary_cap:
        problems.append("SELECTABLE_POOL_CANNOT_FIT_CAP")
    return tuple(problems)


# Volume shares, where a snap-share ceiling is meaningful: a person cannot take
# a larger slice of his team's touches than his observed playing time supports.
_CAPPED_SHARE_FIELDS = ("carry_share", "target_share")
# Conversion and takeover shares, deliberately uncapped.
#
# `role_capacity` is a mean offensive snap share, and capping a touchdown share
# with it is a category error. Measured on the real NE@SEA pool, Zach Charbonnet
# holds 70.6% of Seattle's prior rushing touchdowns on a 48.4% snap share, which
# is an ordinary goal-line back rather than a data fault. Quarterback attempts
# are uncapped for a different reason: a backup who takes over really does
# inherit nearly every attempt, and snap share does not bound that either.
_UNCAPPED_SHARE_FIELDS = (
    "qb_attempt_share",
    "rushing_td_share",
    "receiving_td_share",
)

_ELIGIBLE_POSITIONS = {
    "qb_attempt_share": frozenset({"QB"}),
    "carry_share": frozenset({"QB", "RB", "WR", "TE"}),
    "target_share": frozenset({"RB", "WR", "TE"}),
    "rushing_td_share": frozenset({"QB", "RB", "WR", "TE"}),
    "receiving_td_share": frozenset({"RB", "WR", "TE"}),
}

# Who may absorb a vacated share, which is not the same question as who may hold
# one. A quarterback holds carry share from his own scrambles and designed runs;
# that role does not expand because the starting running back is out. Leaving
# quarterbacks in the absorption set produced a measured 0.0854 to 0.2891 carry
# share for Sam Darnold once Zach Charbonnet was removed, purely because a
# quarterback's snap share leaves enormous headroom.
_ABSORPTION_POSITIONS = {
    "qb_attempt_share": frozenset({"QB"}),
    "carry_share": frozenset({"RB", "WR", "TE"}),
    "target_share": frozenset({"RB", "WR", "TE"}),
    "rushing_td_share": frozenset({"QB", "RB", "WR", "TE"}),
    "receiving_td_share": frozenset({"RB", "WR", "TE"}),
}


def capacity_data_quality(model: OpportunityModel) -> dict[str, object]:
    """Report where role_capacity contradicts the shares built beside it.

    Two patterns show up on real pools and both are worth surfacing rather than
    enforcing. A share above capacity is usually real football, most often a
    goal-line back converting more touchdowns than his playing time suggests. A
    capacity of exactly zero beside a nonzero share is a join gap in the snap
    artifact, not a person who never played.
    """

    exceedances: list[str] = []
    false_zeros: list[str] = []
    for player in model.players:
        shares = {
            field: float(getattr(player, field))
            for field in _CAPPED_SHARE_FIELDS + _UNCAPPED_SHARE_FIELDS
        }
        active = {field: value for field, value in shares.items() if value > 0}
        if float(player.role_capacity) == 0 and active:
            false_zeros.append(f"{player.underlying_id}:{sorted(active)}")
            continue
        for field, value in sorted(active.items()):
            if value > float(player.role_capacity) + 1e-9:
                exceedances.append(
                    f"{player.underlying_id}:{field}:{value:.4f}>{player.role_capacity:.4f}"
                )
    return {
        "share_above_capacity": sorted(exceedances),
        "share_above_capacity_count": len(exceedances),
        "capacity_zero_with_nonzero_share": sorted(false_zeros),
        "capacity_zero_with_nonzero_share_count": len(false_zeros),
        "interpretation": (
            "A share above capacity is usually real (goal-line conversion). A zero"
            " capacity beside a nonzero share is a snap-artifact join gap and is"
            " treated as unknown, never as a ceiling."
        ),
    }


def vacated_opportunity(
    model: OpportunityModel, contract: ParticipationContract
) -> dict[str, dict[str, float]]:
    """How much of each team's opportunity is held by people who cannot play."""

    detail = vacated_opportunity_by_position(model, contract)
    return {
        team: {
            field: round(sum(by_position.values()), 6)
            for field, by_position in sorted(fields.items())
        }
        for team, fields in sorted(detail.items())
    }


def vacated_opportunity_by_position(
    model: OpportunityModel, contract: ParticipationContract
) -> dict[str, dict[str, dict[str, float]]]:
    """Vacated share split by the position that vacated it.

    Redistribution is position-scoped, so the origin position has to be kept:
    a running back's vacated carries are offered to running backs before anyone
    else, which is both closer to how a depth chart actually works and what
    stops a tight end inheriting a fifth of a team's rushing touchdowns.
    """

    blocked = set(contract.unavailable_people) | set(contract.operator_excluded_people)
    vacated: dict[str, dict[str, dict[str, float]]] = {}
    for player in model.players:
        if player.underlying_id not in blocked:
            continue
        team_bucket = vacated.setdefault(player.team, {})
        for field in _CAPPED_SHARE_FIELDS + _UNCAPPED_SHARE_FIELDS:
            amount = float(getattr(player, field))
            if amount <= 0:
                continue
            field_bucket = team_bucket.setdefault(field, {})
            field_bucket[player.position] = field_bucket.get(player.position, 0.0) + amount
    return vacated


def _successor_at(
    depth_ranks: Mapping[tuple[str, str], object],
    pool: Mapping[str, float],
    *,
    position: str,
) -> str | None:
    """The lowest effective rank among the survivors holding this position.

    Returns `None` when the depth chart places none of them, which leaves the
    proportional rule in charge rather than inventing a successor. A rank is
    keyed `(person, position)` so a kick-return line can never nominate one.
    """

    ranked: list[tuple[int, str]] = []
    for person in pool:
        rank = depth_ranks.get((person, position))
        effective = getattr(rank, "effective_rank", None)
        if effective is None:
            continue
        ranked.append((int(effective), person))
    if not ranked:
        return None
    return min(ranked)[1]


def redistribute_opportunity(
    model: OpportunityModel,
    contract: ParticipationContract,
    *,
    redistribute: bool = True,
    depth_ranks: Mapping[tuple[str, str], object] | None = None,
) -> tuple[OpportunityModel, dict[str, object]]:
    """Drop unavailable people and, by default, reallocate what they vacate.

    The rule is proportional to prior share, scoped to the position that vacated
    it, and uncapped. Each of those three choices was forced by a measurement on
    the real NE@SEA pool:

    - `opportunity.remove_inactive_and_redistribute` renormalizes over all
      survivors and then rejects the result if anyone exceeds `role_capacity`.
      It refuses this pool outright, because Zach Charbonnet is `OUT` holding
      44.88% of Seattle's carries and plain renormalization pushes George Holani
      past a 0.055 capacity built from a 5.5% snap share.
    - Scoping to the vacating position keeps those carries in the running back
      room. Without it, quarterbacks absorbed carries on the strength of their
      snap share alone (Sam Darnold measured 0.0854 to 0.2891) and a tight end
      inherited a fifth of the team's rushing touchdowns.
    - The cap is gone because `role_capacity` is a mean prior-season snap share.
      It describes the role a person held while someone was ahead of him, so it
      is invalid in the one situation redistribution addresses. Emanuel Wilson's
      0.3112 capacity is his share as Charbonnet's backup; with Charbonnet out he
      plays well beyond it. Capacity is reported against, never enforced.

    Pass `redistribute=False` for the strictly conservative reading: survivors
    keep unmodified prior shares and nothing is reallocated. That understates a
    promoted survivor, and unevenly between the two teams, so it is not the
    default.

    `depth_ranks` is P7's inheritance route: the effective depth ranks from
    `depth_roles.effective_depth_ranks`, keyed `(person, position)`. When it is
    supplied, a vacated share goes to the person who actually inherits the role
    (effective rank 1 among the survivors at the vacating position) instead of
    proportionally to everyone at that position. A depth chart names a
    successor; proportional-to-prior does not know there is one, which is how a
    third-string back drew a share of a vacated workload he will not see.

    It is off by default, deliberately. The proportional rule above was forced
    by measurements on the real NE@SEA pool, and nothing has yet measured
    inheritance against it: that needs the standings grading harness, which is
    chunk `P0` and is blocked on the corpus transport. Switching the default is
    a modelling change that should follow a number, not precede one. Supplying
    the ranks is an explicit caller decision until then.
    """

    from dataclasses import replace

    blocked = set(contract.unavailable_people) | set(contract.operator_excluded_people)
    survivors = [p for p in model.players if p.underlying_id not in blocked]
    if not survivors:
        raise ParticipationError("PARTICIPATION_REMOVES_EVERY_PERSON")
    for team in {p.team for p in model.players}:
        if not any(p.team == team for p in survivors):
            raise ParticipationError(f"PARTICIPATION_REMOVES_EVERY_PERSON_FOR_TEAM:{team}")

    vacated = vacated_opportunity(model, contract)
    report: dict[str, object] = {
        "rule": (
            "PROPORTIONAL_TO_PRIOR_WITHIN_VACATING_POSITION_UNCAPPED_V1"
            if redistribute
            else "NO_REDISTRIBUTION_SURVIVORS_KEEP_PRIOR_SHARES"
        ),
        "removed_people": sorted(blocked),
        "removed_count": len(blocked),
        "surviving_people": len(survivors),
        "vacated_by_team": vacated,
        "capacity_data_quality": capacity_data_quality(model),
        "vacancy_rule": (
            "DEPTH_CHART_SUCCESSOR_INHERITS_V1"
            if depth_ranks
            else "PROPORTIONAL_TO_PRIOR_NO_SUCCESSOR_KNOWN"
        ),
        "capacity_treatment": (
            "DIAGNOSTIC_ONLY:role_capacity is a mean prior-season snap share and is"
            " not a forward ceiling; a promoted survivor is expected to exceed it"
        ),
    }
    if not redistribute:
        report["unallocated_by_team"] = vacated
        report["share_above_prior_capacity_after_redistribution"] = []
        return replace(model, players=tuple(survivors)), report

    detail = vacated_opportunity_by_position(model, contract)
    updated: dict[str, dict[str, float]] = {p.underlying_id: {} for p in survivors}
    unallocated: dict[str, dict[str, float]] = {}
    gains: list[dict[str, object]] = []
    for team in sorted({p.team for p in survivors}):
        team_survivors = [p for p in survivors if p.team == team]
        for field in _CAPPED_SHARE_FIELDS + _UNCAPPED_SHARE_FIELDS:
            eligible = [
                p for p in team_survivors if p.position in _ELIGIBLE_POSITIONS[field]
            ]
            if not eligible:
                continue
            prior = {p.underlying_id: float(getattr(p, field)) for p in eligible}
            position_of = {p.underlying_id: p.position for p in eligible}
            shares = dict(prior)
            absorbers = _ABSORPTION_POSITIONS[field]
            residual = 0.0
            for source_position, amount in sorted(
                detail.get(team, {}).get(field, {}).items()
            ):
                remaining = amount
                # The depth chart absorbs its own vacancy first. Only a position
                # group with no prior share at all spills to the wider absorption
                # set, which is what keeps vacated carries in the running back
                # room instead of handing a sixth of them to a tight end.
                for tier in (frozenset({source_position}), absorbers):
                    if remaining <= 1e-12:
                        break
                    pool = {
                        person: prior[person]
                        for person in prior
                        if position_of[person] in tier
                        and position_of[person] in absorbers
                    }
                    # P7. The depth chart names who inherits the role, so when
                    # the caller supplied effective ranks the vacated share goes
                    # to that person rather than being split across the room.
                    # Scoped to the vacating position only: a successor at RB
                    # inherits vacated carries, and nothing about him says he
                    # absorbs a spill from another position group.
                    if depth_ranks and tier == frozenset({source_position}):
                        successor = _successor_at(
                            depth_ranks, pool, position=source_position
                        )
                        if successor is not None:
                            pool = {successor: 1.0}
                    weight = sum(pool.values())
                    if not pool or weight <= 0:
                        continue
                    for person, value in pool.items():
                        shares[person] += remaining * (value / weight)
                    remaining = 0.0
                residual += remaining
            for person, value in shares.items():
                updated[person][field] = value
                if value - prior[person] > 1e-6:
                    gains.append(
                        {
                            "person": person,
                            "field": field,
                            "before": round(prior[person], 6),
                            "after": round(value, 6),
                        }
                    )
            if residual > 1e-9:
                unallocated.setdefault(team, {})[field] = round(residual, 6)

    rebuilt = tuple(
        replace(player, **updated[player.underlying_id]) for player in survivors
    )
    exceeded = [
        f"{player.underlying_id}:{field}:{getattr(player, field):.4f}"
        f">{player.role_capacity:.4f}"
        for player in rebuilt
        for field in _CAPPED_SHARE_FIELDS
        if float(player.role_capacity) > 0
        and getattr(player, field) > float(player.role_capacity) + 1e-6
    ]
    report["unallocated_by_team"] = {
        team: fields for team, fields in sorted(unallocated.items())
    }
    report["share_above_prior_capacity_after_redistribution"] = sorted(exceeded)
    report["shares_changed"] = len(gains)
    report["largest_gains"] = sorted(
        gains, key=lambda item: item["before"] - item["after"]
    )[:10]
    return replace(model, players=rebuilt), report


def person_status(contract: ParticipationContract, person: str) -> str:
    return contract.status_by_person.get(person, "")


def status_by_dk_id(
    slate: SlateContract, contract: ParticipationContract
) -> Mapping[str, str]:
    return {
        player.dk_id: contract.status_by_person.get(player.underlying_id, "")
        for player in slate.players
    }
