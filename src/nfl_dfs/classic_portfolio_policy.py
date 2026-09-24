"""C2 Classic portfolio preference contract and canonical normalization.

The contract contains only deterministic construction preferences and exact
integer limits.  It deliberately has no ownership, field, duplication, payout,
scenario, risk, or EV fields.  Hard controls are never relaxed; advisory group
and stack rules are candidate-coverage hints and are reported as such.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Mapping, Sequence

from .contracts import EngineMode, SlateContract
from .entry_groups import subset_binding_problems
from .hashing import sha256_bytes
from .portfolio_policy import canonical_decimal_json_bytes


POLICY_SCHEMA_VERSION = "nfl_classic_portfolio_policy_c2_v1"
NORMALIZED_POLICY_SCHEMA_VERSION = "nfl_classic_portfolio_policy_normalized_c2_v1"
OBJECTIVE_VERSION = "classic_prior_points_expected_stat_line_c2_v1"
OBJECTIVE_NAME = "MAXIMIZE_PRIOR_POINTS_OF_THE_EXPECTED_STAT_LINE"
SEED = 0
ROSTER_SLOTS = ("QB", "RB1", "RB2", "WR1", "WR2", "WR3", "TE", "FLEX", "DST")
POSITIONS = ("QB", "RB", "WR", "TE", "DST")
REGISTERED_STACK_RULE_TYPES = (
    "QB_PASS_CATCHER",
    "QB_BRINGBACK",
    "RB_DST_PAIR",
    "SECONDARY_GAME_CORRELATION",
)
RULE_STRENGTHS = frozenset({"HARD", "ADVISORY"})


@dataclass(frozen=True, order=True)
class ClassicPersonBinding:
    underlying_id: str
    dk_id: str
    name: str
    team: str
    opponent: str
    game_id: str
    position: str
    roster_positions: tuple[str, ...]
    salary: int

    def reference(self) -> dict[str, str]:
        return {"underlying_id": self.underlying_id, "dk_id": self.dk_id}

    def as_mapping(self) -> dict[str, object]:
        return {
            "underlying_id": self.underlying_id,
            "dk_id": self.dk_id,
            "name": self.name,
            "team": self.team,
            "opponent": self.opponent,
            "game_id": self.game_id,
            "position": self.position,
            "roster_positions": list(self.roster_positions),
            "salary": self.salary,
        }


@dataclass(frozen=True, order=True)
class EntityExposureBound:
    entity_id: str
    minimum_entries: int
    maximum_entries: int
    exclusion_source: str | None = None

    def as_mapping(self, key: str) -> dict[str, object]:
        return {
            key: self.entity_id,
            "minimum_entries": self.minimum_entries,
            "maximum_entries": self.maximum_entries,
            "hard": True,
            "exclusion_source": self.exclusion_source,
        }


@dataclass(frozen=True, order=True)
class GroupRule:
    group_id: str
    member_ids: tuple[str, ...]
    minimum_players: int
    maximum_players: int
    minimum_entries: int
    maximum_entries: int
    strength: str

    @property
    def hard(self) -> bool:
        return self.strength == "HARD"

    def as_mapping(self, people: Mapping[str, ClassicPersonBinding]) -> dict[str, object]:
        return {
            "group_id": self.group_id,
            "members": [people[person].reference() for person in self.member_ids],
            "minimum_players": self.minimum_players,
            "maximum_players": self.maximum_players,
            "minimum_entries": self.minimum_entries,
            "maximum_entries": self.maximum_entries,
            "strength": self.strength,
        }


@dataclass(frozen=True, order=True)
class StackRule:
    rule_id: str
    rule_type: str
    minimum_value: int
    maximum_value: int
    minimum_entries: int
    maximum_entries: int
    strength: str

    @property
    def hard(self) -> bool:
        return self.strength == "HARD"

    def as_mapping(self) -> dict[str, object]:
        return {
            "rule_id": self.rule_id,
            "rule_type": self.rule_type,
            "minimum_value": self.minimum_value,
            "maximum_value": self.maximum_value,
            "minimum_entries": self.minimum_entries,
            "maximum_entries": self.maximum_entries,
            "strength": self.strength,
        }


@dataclass(frozen=True)
class SearchLimits:
    candidate_limit: int
    candidate_total_milliseconds: int
    candidate_per_solve_milliseconds: int
    selection_milliseconds: int

    def as_mapping(self) -> dict[str, int]:
        return {
            "candidate_limit": self.candidate_limit,
            "candidate_total_milliseconds": self.candidate_total_milliseconds,
            "candidate_per_solve_milliseconds": self.candidate_per_solve_milliseconds,
            "selection_milliseconds": self.selection_milliseconds,
        }


@dataclass(frozen=True)
class NormalizedClassicPortfolioPolicy:
    salary_sha256: str
    entry_sha256: str
    draft_group: str
    games: tuple[tuple[str, str, str, str], ...]
    teams: tuple[tuple[str, str, str], ...]
    entry_ids: tuple[str, ...]
    people: tuple[ClassicPersonBinding, ...]
    player_bounds: tuple[EntityExposureBound, ...]
    team_bounds: tuple[EntityExposureBound, ...]
    game_bounds: tuple[EntityExposureBound, ...]
    exact_exclusions: tuple[str, ...]
    groups: tuple[GroupRule, ...]
    stack_rules: tuple[StackRule, ...]
    max_pairwise_person_overlap: int
    require_unique_lineups: bool
    search_limits: SearchLimits
    objective_version: str = OBJECTIVE_VERSION
    objective_name: str = OBJECTIVE_NAME
    seed: int = SEED

    @property
    def entry_count(self) -> int:
        return len(self.entry_ids)

    @property
    def people_by_id(self) -> dict[str, ClassicPersonBinding]:
        return {person.underlying_id: person for person in self.people}

    def as_mapping(self) -> dict[str, object]:
        people = self.people_by_id
        return {
            "schema_version": NORMALIZED_POLICY_SCHEMA_VERSION,
            "bindings": {
                "salary_sha256": self.salary_sha256,
                "entry_sha256": self.entry_sha256,
                "draft_group": self.draft_group,
                "games": [
                    {
                        "game_id": game_id,
                        "away_team": away,
                        "home_team": home,
                        "lock_at": lock_at,
                    }
                    for game_id, away, home, lock_at in self.games
                ],
                "teams": [
                    {"team": team, "opponent": opponent, "game_id": game_id}
                    for team, opponent, game_id in self.teams
                ],
                "positions": list(POSITIONS),
                "roster_slots": list(ROSTER_SLOTS),
                "registered_stack_rule_types": list(REGISTERED_STACK_RULE_TYPES),
                "entry_ids": list(self.entry_ids),
                "people": [person.as_mapping() for person in self.people],
            },
            "selection": {
                "objective_version": self.objective_version,
                "objective": self.objective_name,
                "direction": "MAXIMIZE",
                "seed": self.seed,
                "limits": self.search_limits.as_mapping(),
            },
            "controls": {
                "player_exposure_bounds": [
                    {
                        **people[bound.entity_id].reference(),
                        "minimum_entries": bound.minimum_entries,
                        "maximum_entries": bound.maximum_entries,
                        "hard": True,
                        "exclusion_source": bound.exclusion_source,
                    }
                    for bound in self.player_bounds
                ],
                "team_exposure_bounds": [
                    bound.as_mapping("team") for bound in self.team_bounds
                ],
                "game_exposure_bounds": [
                    bound.as_mapping("game_id") for bound in self.game_bounds
                ],
                "exact_exclusions": [people[person].reference() for person in self.exact_exclusions],
                "groups": [group.as_mapping(people) for group in self.groups],
                "stack_rules": [rule.as_mapping() for rule in self.stack_rules],
                "max_pairwise_person_overlap": self.max_pairwise_person_overlap,
                "require_unique_lineups": self.require_unique_lineups,
            },
            "effective": {
                "entry_count_denominator": self.entry_count,
                "integer_limit_semantics": "DIRECT_INCLUSIVE_COUNTS_NO_ROUNDING",
                "hard_controls_are_never_relaxed": True,
                "advisory_controls_are_candidate_coverage_only": True,
            },
        }

    def canonical_bytes(self) -> bytes:
        return canonical_decimal_json_bytes(self.as_mapping())

    @property
    def normalized_sha256(self) -> str:
        return sha256_bytes(self.canonical_bytes())


@dataclass(frozen=True)
class PolicyIssue:
    code: str
    message: str
    next_action: str

    def as_mapping(self) -> dict[str, str]:
        return {
            "code": self.code,
            "message": self.message,
            "next_action": self.next_action,
        }

    def as_blocker(self) -> str:
        return f"{self.code}: {self.message}; next action: {self.next_action}"


@dataclass(frozen=True)
class ClassicPortfolioPolicyValidation:
    source_sha256: str
    policy: NormalizedClassicPortfolioPolicy | None
    problems: tuple[PolicyIssue, ...]
    findings: tuple[PolicyIssue, ...]

    @property
    def valid(self) -> bool:
        return self.policy is not None and not self.problems

    @property
    def normalized_sha256(self) -> str | None:
        return self.policy.normalized_sha256 if self.policy is not None else None

    def blockers(self) -> tuple[str, ...]:
        return tuple(issue.as_blocker() for issue in self.problems)

    def as_report(self) -> dict[str, object]:
        return {
            "schema_version": POLICY_SCHEMA_VERSION,
            "valid": self.valid,
            "source_policy_sha256": self.source_sha256,
            "normalized_policy_sha256": self.normalized_sha256,
            "problems": [issue.as_mapping() for issue in self.problems],
            "findings": [issue.as_mapping() for issue in self.findings],
            "normalized_policy": self.policy.as_mapping() if self.policy else None,
            "enforcement_status": "NOT_EVALUATED_BY_CONTRACT_VALIDATION",
        }


class _DuplicateKey(ValueError):
    pass


def _pairs_without_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKey(key)
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> object:
    raise ValueError(f"nonfinite JSON number {value!r}")


def _issue(code: str, message: str, next_action: str) -> PolicyIssue:
    return PolicyIssue(code, message, next_action)


def _mapping(value: object, location: str, problems: list[PolicyIssue]) -> Mapping[str, object] | None:
    if not isinstance(value, Mapping):
        problems.append(_issue("CLASSIC_POLICY_TYPE_INVALID", f"{location} must be an object", "repair the policy shape"))
        return None
    return value


def _unknown_fields(
    value: Mapping[str, object], allowed: set[str], location: str, problems: list[PolicyIssue]
) -> None:
    unknown = sorted(set(value).difference(allowed))
    if unknown:
        problems.append(
            _issue(
                "CLASSIC_POLICY_UNKNOWN_FIELD",
                f"{location} contains unsupported fields {unknown}",
                "remove fields not declared by the C2 schema",
            )
        )


def _integer(
    value: object,
    location: str,
    problems: list[PolicyIssue],
    *,
    minimum: int = 0,
    maximum: int | None = None,
) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        problems.append(_issue("CLASSIC_POLICY_INTEGER_REQUIRED", f"{location} must be a JSON integer", "supply a direct integer count"))
        return None
    if value < minimum or (maximum is not None and value > maximum):
        problems.append(_issue("CLASSIC_POLICY_INTEGER_OUT_OF_RANGE", f"{location}={value} is outside [{minimum},{maximum if maximum is not None else 'unbounded'}]", "supply an integer inside the declared domain"))
        return None
    return value


def _string(value: object, location: str, problems: list[PolicyIssue]) -> str | None:
    if not isinstance(value, str) or not value.strip():
        problems.append(_issue("CLASSIC_POLICY_STRING_REQUIRED", f"{location} must be a non-empty string", "copy the exact bound value"))
        return None
    return value.strip()


def classic_people(slate: SlateContract) -> tuple[ClassicPersonBinding, ...]:
    if slate.mode is not EngineMode.CLASSIC:
        raise ValueError("CLASSIC_POLICY_MODE_UNSUPPORTED:Classic salary rows are required")
    if len({row.underlying_id for row in slate.players}) != len(slate.players):
        raise ValueError("CLASSIC_POLICY_DUPLICATE_UNDERLYING_PERSON")
    return tuple(
        sorted(
            (
                ClassicPersonBinding(
                    underlying_id=row.underlying_id,
                    dk_id=row.dk_id,
                    name=row.name,
                    team=row.team,
                    opponent=row.opponent,
                    game_id=row.game_id,
                    position=row.position,
                    roster_positions=tuple(sorted(row.roster_positions)),
                    salary=row.salary,
                )
                for row in slate.players
            ),
            key=lambda row: (row.underlying_id, row.dk_id),
        )
    )


def _game_bindings(slate: SlateContract) -> tuple[tuple[str, str, str, str], ...]:
    return tuple(
        sorted(
            (
                game.game_id,
                game.away_team,
                game.home_team,
                game.lock_at.isoformat(),
            )
            for game in slate.games
        )
    )


def _team_bindings(slate: SlateContract) -> tuple[tuple[str, str, str], ...]:
    found = {(row.team, row.opponent, row.game_id) for row in slate.players}
    return tuple(sorted(found))


def default_search_limits(entry_count: int) -> SearchLimits:
    return SearchLimits(
        candidate_limit=max(32, entry_count + 24),
        candidate_total_milliseconds=max(30_000, 400 * entry_count),
        candidate_per_solve_milliseconds=1_500,
        selection_milliseconds=max(10_000, 150 * entry_count),
    )


def _default_stack_rules(entry_count: int) -> list[dict[str, object]]:
    return [
        {
            "rule_id": "qb-pass-catcher",
            "rule_type": "QB_PASS_CATCHER",
            "minimum_value": 1,
            "maximum_value": 4,
            "minimum_entries": 0,
            "maximum_entries": entry_count,
            "strength": "ADVISORY",
        },
        {
            "rule_id": "qb-bringback",
            "rule_type": "QB_BRINGBACK",
            "minimum_value": 1,
            "maximum_value": 6,
            "minimum_entries": 0,
            "maximum_entries": entry_count,
            "strength": "ADVISORY",
        },
        {
            "rule_id": "rb-dst-pair",
            "rule_type": "RB_DST_PAIR",
            "minimum_value": 1,
            "maximum_value": 2,
            "minimum_entries": 0,
            "maximum_entries": entry_count,
            "strength": "ADVISORY",
        },
        {
            "rule_id": "secondary-game-correlation",
            "rule_type": "SECONDARY_GAME_CORRELATION",
            "minimum_value": 1,
            "maximum_value": 4,
            "minimum_entries": 0,
            "maximum_entries": entry_count,
            "strength": "ADVISORY",
        },
    ]


def classic_portfolio_policy_template(
    slate: SlateContract,
    entry_ids: Sequence[str],
    *,
    entry_sha256: str,
    controls: Mapping[str, object] | None = None,
    limits: Mapping[str, object] | None = None,
) -> dict[str, object]:
    people = classic_people(slate)
    count = len(entry_ids)
    defaults = default_search_limits(count).as_mapping()
    defaults.update(dict(limits or {}))
    return {
        "schema_version": POLICY_SCHEMA_VERSION,
        "bindings": {
            "salary_sha256": slate.salary_hash,
            "entry_sha256": entry_sha256,
            "draft_group": slate.draft_group,
            "games": [
                {"game_id": game_id, "away_team": away, "home_team": home, "lock_at": lock_at}
                for game_id, away, home, lock_at in _game_bindings(slate)
            ],
            "teams": [
                {"team": team, "opponent": opponent, "game_id": game_id}
                for team, opponent, game_id in _team_bindings(slate)
            ],
            "positions": list(POSITIONS),
            "roster_slots": list(ROSTER_SLOTS),
            "registered_stack_rule_types": list(REGISTERED_STACK_RULE_TYPES),
            "entry_ids": list(entry_ids),
            "people": [person.as_mapping() for person in people],
        },
        "selection": {
            "objective_version": OBJECTIVE_VERSION,
            "objective": OBJECTIVE_NAME,
            "direction": "MAXIMIZE",
            "seed": SEED,
            "limits": defaults,
        },
        "controls": {
            "player_exposure_bounds": [],
            "team_exposure_bounds": [],
            "game_exposure_bounds": [],
            "exact_exclusions": [],
            "groups": [],
            "stack_rules": _default_stack_rules(count),
            "max_pairwise_person_overlap": 8,
            "require_unique_lineups": True,
            **dict(controls or {}),
        },
    }


def _parse_person_reference(
    value: object,
    *,
    location: str,
    expected: Mapping[str, ClassicPersonBinding],
    problems: list[PolicyIssue],
) -> str | None:
    item = _mapping(value, location, problems)
    if item is None:
        return None
    _unknown_fields(item, {"underlying_id", "dk_id"}, location, problems)
    person = _string(item.get("underlying_id"), f"{location}.underlying_id", problems)
    dk_id = _string(item.get("dk_id"), f"{location}.dk_id", problems)
    if person is None or dk_id is None:
        return None
    target = expected.get(person)
    if target is None or target.dk_id != dk_id:
        problems.append(_issue("CLASSIC_POLICY_PERSON_REFERENCE_MISMATCH", f"{location} does not bind one exact current salary person", "copy underlying_id and dk_id from bindings.people"))
        return None
    return person


def _parse_exposure_bounds(
    value: object,
    *,
    kind: str,
    valid_ids: set[str],
    expected_people: Mapping[str, ClassicPersonBinding],
    entry_count: int,
    problems: list[PolicyIssue],
) -> dict[str, tuple[int, int]]:
    if not isinstance(value, list):
        problems.append(_issue("CLASSIC_POLICY_BOUND_LIST_REQUIRED", f"controls.{kind}_exposure_bounds must be an array", "supply zero or more exact integer bounds"))
        return {}
    result: dict[str, tuple[int, int]] = {}
    for index, raw in enumerate(value):
        location = f"controls.{kind}_exposure_bounds[{index}]"
        item = _mapping(raw, location, problems)
        if item is None:
            continue
        key_name = {"player": "person", "team": "team", "game": "game_id"}[kind]
        allowed = {"minimum_entries", "maximum_entries", "hard", key_name}
        if kind == "player":
            allowed = {
                "underlying_id",
                "dk_id",
                "minimum_entries",
                "maximum_entries",
                "hard",
            }
        _unknown_fields(item, allowed, location, problems)
        if item.get("hard") is not True:
            problems.append(_issue("CLASSIC_POLICY_EXPOSURE_MUST_BE_HARD", f"{location}.hard must be true", "use groups or stack_rules for advisory preferences"))
        if kind == "player":
            entity = _parse_person_reference(
                {
                    "underlying_id": item.get("underlying_id"),
                    "dk_id": item.get("dk_id"),
                },
                location=location,
                expected=expected_people,
                problems=problems,
            )
        else:
            entity = _string(item.get(key_name), f"{location}.{key_name}", problems)
            if entity is not None and entity not in valid_ids:
                problems.append(_issue("CLASSIC_POLICY_ENTITY_UNKNOWN", f"{location} references unknown {kind} {entity!r}", "copy an exact identity from bindings"))
                entity = None
        minimum = _integer(item.get("minimum_entries"), f"{location}.minimum_entries", problems, maximum=entry_count)
        maximum = _integer(item.get("maximum_entries"), f"{location}.maximum_entries", problems, maximum=entry_count)
        if minimum is not None and maximum is not None and minimum > maximum:
            problems.append(_issue("CLASSIC_POLICY_BOUND_CONTRADICTORY", f"{location} minimum exceeds maximum", "make the inclusive integer bounds ordered"))
        if entity is not None and minimum is not None and maximum is not None:
            if entity in result:
                problems.append(_issue("CLASSIC_POLICY_DUPLICATE_BOUND", f"{location} repeats {kind} {entity!r}", "retain one bound per exact entity"))
            result[entity] = (minimum, maximum)
    return result


def _parse_groups(
    value: object,
    *,
    people: Mapping[str, ClassicPersonBinding],
    entry_count: int,
    problems: list[PolicyIssue],
) -> tuple[GroupRule, ...]:
    if not isinstance(value, list):
        problems.append(_issue("CLASSIC_POLICY_GROUP_LIST_REQUIRED", "controls.groups must be an array", "supply zero or more versioned groups"))
        return ()
    result: list[GroupRule] = []
    for index, raw in enumerate(value):
        location = f"controls.groups[{index}]"
        item = _mapping(raw, location, problems)
        if item is None:
            continue
        _unknown_fields(item, {"group_id", "members", "minimum_players", "maximum_players", "minimum_entries", "maximum_entries", "strength"}, location, problems)
        group_id = _string(item.get("group_id"), f"{location}.group_id", problems)
        raw_members = item.get("members")
        members: list[str] = []
        if not isinstance(raw_members, list) or not raw_members:
            problems.append(_issue("CLASSIC_POLICY_GROUP_MEMBERS_REQUIRED", f"{location}.members must be a non-empty array", "bind exact group people"))
        else:
            for member_index, member in enumerate(raw_members):
                parsed = _parse_person_reference(member, location=f"{location}.members[{member_index}]", expected=people, problems=problems)
                if parsed is not None:
                    members.append(parsed)
        if len(set(members)) != len(members):
            problems.append(_issue("CLASSIC_POLICY_GROUP_MEMBER_DUPLICATE", f"{location} repeats a person", "retain each exact member once"))
        minimum_players = _integer(item.get("minimum_players"), f"{location}.minimum_players", problems, maximum=9)
        maximum_players = _integer(item.get("maximum_players"), f"{location}.maximum_players", problems, maximum=9)
        minimum_entries = _integer(item.get("minimum_entries"), f"{location}.minimum_entries", problems, maximum=entry_count)
        maximum_entries = _integer(item.get("maximum_entries"), f"{location}.maximum_entries", problems, maximum=entry_count)
        strength = _string(item.get("strength"), f"{location}.strength", problems)
        if strength is not None and strength not in RULE_STRENGTHS:
            problems.append(_issue("CLASSIC_POLICY_RULE_STRENGTH_INVALID", f"{location}.strength must be HARD or ADVISORY", "declare whether the construction preference is binding"))
        if minimum_players is not None and maximum_players is not None and (minimum_players > maximum_players or maximum_players > len(set(members))):
            problems.append(_issue("CLASSIC_POLICY_GROUP_PLAYER_BOUNDS_CONTRADICTORY", f"{location} player bounds cannot be satisfied by its members", "repair the member set or player bounds"))
        if minimum_entries is not None and maximum_entries is not None and minimum_entries > maximum_entries:
            problems.append(_issue("CLASSIC_POLICY_GROUP_ENTRY_BOUNDS_CONTRADICTORY", f"{location} minimum_entries exceeds maximum_entries", "repair the inclusive entry bounds"))
        values = (group_id, minimum_players, maximum_players, minimum_entries, maximum_entries, strength)
        if all(value is not None for value in values) and members:
            result.append(GroupRule(str(group_id), tuple(sorted(members)), int(minimum_players), int(maximum_players), int(minimum_entries), int(maximum_entries), str(strength)))
    if len({rule.group_id for rule in result}) != len(result):
        problems.append(_issue("CLASSIC_POLICY_GROUP_ID_DUPLICATE", "group_id values must be unique", "rename or combine duplicate groups"))
    return tuple(sorted(result))


def _parse_stack_rules(
    value: object, *, entry_count: int, problems: list[PolicyIssue]
) -> tuple[StackRule, ...]:
    if not isinstance(value, list):
        problems.append(_issue("CLASSIC_POLICY_STACK_LIST_REQUIRED", "controls.stack_rules must be an array", "supply registered Classic stack rules"))
        return ()
    result: list[StackRule] = []
    for index, raw in enumerate(value):
        location = f"controls.stack_rules[{index}]"
        item = _mapping(raw, location, problems)
        if item is None:
            continue
        _unknown_fields(item, {"rule_id", "rule_type", "minimum_value", "maximum_value", "minimum_entries", "maximum_entries", "strength"}, location, problems)
        rule_id = _string(item.get("rule_id"), f"{location}.rule_id", problems)
        rule_type = _string(item.get("rule_type"), f"{location}.rule_type", problems)
        if rule_type is not None and rule_type not in REGISTERED_STACK_RULE_TYPES:
            problems.append(_issue("CLASSIC_POLICY_STACK_RULE_UNREGISTERED", f"{location} uses unregistered type {rule_type!r}", "use a C2 registered stack rule type"))
        minimum_value = _integer(item.get("minimum_value"), f"{location}.minimum_value", problems, maximum=9)
        maximum_value = _integer(item.get("maximum_value"), f"{location}.maximum_value", problems, maximum=9)
        minimum_entries = _integer(item.get("minimum_entries"), f"{location}.minimum_entries", problems, maximum=entry_count)
        maximum_entries = _integer(item.get("maximum_entries"), f"{location}.maximum_entries", problems, maximum=entry_count)
        strength = _string(item.get("strength"), f"{location}.strength", problems)
        if strength is not None and strength not in RULE_STRENGTHS:
            problems.append(_issue("CLASSIC_POLICY_RULE_STRENGTH_INVALID", f"{location}.strength must be HARD or ADVISORY", "declare whether the construction preference is binding"))
        if minimum_value is not None and maximum_value is not None and minimum_value > maximum_value:
            problems.append(_issue("CLASSIC_POLICY_STACK_VALUE_BOUNDS_CONTRADICTORY", f"{location} minimum_value exceeds maximum_value", "repair the inclusive stack value bounds"))
        if minimum_entries is not None and maximum_entries is not None and minimum_entries > maximum_entries:
            problems.append(_issue("CLASSIC_POLICY_STACK_ENTRY_BOUNDS_CONTRADICTORY", f"{location} minimum_entries exceeds maximum_entries", "repair the inclusive entry bounds"))
        values = (rule_id, rule_type, minimum_value, maximum_value, minimum_entries, maximum_entries, strength)
        if all(value is not None for value in values):
            result.append(StackRule(str(rule_id), str(rule_type), int(minimum_value), int(maximum_value), int(minimum_entries), int(maximum_entries), str(strength)))
    if len({rule.rule_id for rule in result}) != len(result):
        problems.append(_issue("CLASSIC_POLICY_STACK_RULE_ID_DUPLICATE", "rule_id values must be unique", "rename or combine duplicate stack rules"))
    return tuple(sorted(result))


def _complete_identity_payload(slate: SlateContract) -> dict[str, object]:
    return {
        "games": [
            {"game_id": game_id, "away_team": away, "home_team": home, "lock_at": lock_at}
            for game_id, away, home, lock_at in _game_bindings(slate)
        ],
        "teams": [
            {"team": team, "opponent": opponent, "game_id": game_id}
            for team, opponent, game_id in _team_bindings(slate)
        ],
        "positions": list(POSITIONS),
        "roster_slots": list(ROSTER_SLOTS),
        "registered_stack_rule_types": list(REGISTERED_STACK_RULE_TYPES),
        "people": [person.as_mapping() for person in classic_people(slate)],
    }


def _capacity_issues(policy: NormalizedClassicPortfolioPolicy) -> tuple[PolicyIssue, ...]:
    issues: list[PolicyIssue] = []
    count = policy.entry_count
    player_minima = {
        bound.entity_id: bound.minimum_entries for bound in policy.player_bounds
    }
    player_maxima = {
        bound.entity_id: bound.maximum_entries for bound in policy.player_bounds
    }
    team_minima = {
        bound.entity_id: bound.minimum_entries for bound in policy.team_bounds
    }
    team_maxima = {
        bound.entity_id: bound.maximum_entries for bound in policy.team_bounds
    }
    game_minima = {
        bound.entity_id: bound.minimum_entries for bound in policy.game_bounds
    }
    game_maxima = {
        bound.entity_id: bound.maximum_entries for bound in policy.game_bounds
    }
    maxima = {
        person.underlying_id: min(
            player_maxima[person.underlying_id],
            team_maxima[person.team],
            game_maxima[person.game_id],
        )
        for person in policy.people
    }
    available = [person for person in policy.people if maxima[person.underlying_id] > 0]
    if len(available) < 9:
        issues.append(_issue("CLASSIC_POLICY_PERSON_CAPACITY_INSUFFICIENT", "fewer than nine people have positive effective capacity", "raise a hard player maximum or remove an exact exclusion"))
    if sum(maxima.values()) < 9 * count:
        issues.append(_issue("CLASSIC_POLICY_PLAYER_EXPOSURE_CAPACITY_INSUFFICIENT", "player maximum counts cannot fill every requested roster slot", "raise explicit player maxima without relaxing another hard gate"))
    required_position_slots = {"QB": 1, "RB": 2, "WR": 3, "TE": 1, "DST": 1}
    for position, slots in required_position_slots.items():
        capacity = sum(maxima[person.underlying_id] for person in available if person.position == position)
        if capacity < slots * count:
            issues.append(_issue("CLASSIC_POLICY_POSITION_CAPACITY_INSUFFICIENT", f"{position} maximum capacity {capacity} cannot fill {slots * count} mandatory slots", "raise maxima for exact eligible people at this position"))
    flex_capacity = sum(maxima[person.underlying_id] for person in available if person.position in {"RB", "WR", "TE"})
    if flex_capacity < 7 * count:
        issues.append(_issue("CLASSIC_POLICY_FLEX_CAPACITY_INSUFFICIENT", "RB/WR/TE maximum capacity cannot fill the seven skill slots per lineup", "raise exact skill-player maxima"))
    if sum(player_minima.values()) > 9 * count:
        issues.append(_issue("CLASSIC_POLICY_PLAYER_MINIMUMS_CONTRADICTORY", "player minimum counts require more than the available roster slots", "lower one or more hard player minimums"))
    maximum_slots_by_position = {"QB": 1, "RB": 3, "WR": 4, "TE": 2, "DST": 1}
    for position, maximum_slots in maximum_slots_by_position.items():
        required = sum(
            player_minima[person.underlying_id]
            for person in policy.people
            if person.position == position
        )
        if required > maximum_slots * count:
            issues.append(_issue("CLASSIC_POLICY_POSITION_MINIMUMS_CONTRADICTORY", f"{position} minimum counts require {required} uses but at most {maximum_slots * count} roster slots exist", "lower one or more hard player minimums at this position"))
    skill_minimum = sum(
        player_minima[person.underlying_id]
        for person in policy.people
        if person.position in {"RB", "WR", "TE"}
    )
    if skill_minimum > 7 * count:
        issues.append(_issue("CLASSIC_POLICY_FLEX_MINIMUMS_CONTRADICTORY", "RB/WR/TE minimum counts require more than the seven skill slots per lineup", "lower one or more hard skill-player minimums"))
    if sum(team_maxima.values()) < 2 * count:
        issues.append(_issue("CLASSIC_POLICY_TEAM_EXPOSURE_CAPACITY_INSUFFICIENT", "team maximum counts cannot provide the minimum two distinct teams implied by Classic's two-game rule", "raise one or more hard team maxima"))
    if sum(game_maxima.values()) < 2 * count:
        issues.append(_issue("CLASSIC_POLICY_GAME_EXPOSURE_CAPACITY_INSUFFICIENT", "game maximum counts cannot provide the required two distinct games per lineup", "raise one or more hard game maxima"))
    if sum(team_minima.values()) > min(9, len(team_minima)) * count:
        issues.append(_issue("CLASSIC_POLICY_TEAM_MINIMUMS_CONTRADICTORY", "team minimum counts require more distinct-team appearances than the rosters can contain", "lower one or more hard team minimums"))
    if sum(game_minima.values()) > min(9, len(game_minima)) * count:
        issues.append(_issue("CLASSIC_POLICY_GAME_MINIMUMS_CONTRADICTORY", "game minimum counts require more distinct-game appearances than the rosters can contain", "lower one or more hard game minimums"))
    for person in policy.people:
        minimum = player_minima[person.underlying_id]
        if minimum > team_maxima[person.team] or minimum > game_maxima[person.game_id]:
            issues.append(_issue("CLASSIC_POLICY_ENTITY_BOUNDS_CONTRADICTORY", f"player {person.underlying_id!r} minimum exceeds its team or game maximum", "reconcile the hard player, team, and game bounds"))
    if count > 1:
        minimum_overlap = max(0, 18 - len(available))
        if policy.max_pairwise_person_overlap < minimum_overlap:
            issues.append(_issue("CLASSIC_POLICY_PAIRWISE_OVERLAP_CAPACITY_INSUFFICIENT", f"{len(available)} usable people force overlap of at least {minimum_overlap}", "raise the overlap cap or permit more exact people"))
    if policy.require_unique_lineups and len(available) >= 9 and math.comb(len(available), 9) < count:
        issues.append(_issue("CLASSIC_POLICY_UNIQUE_LINEUP_CAPACITY_INSUFFICIENT", "the loose canonical-lineup upper bound is below the entry count", "permit more people or request fewer entries"))
    for group in policy.groups:
        if not group.hard or group.minimum_entries == 0:
            continue
        usable_members = sum(maxima[person] > 0 for person in group.member_ids)
        if usable_members < group.minimum_players:
            issues.append(_issue("CLASSIC_POLICY_GROUP_CAPACITY_INSUFFICIENT", f"hard group {group.group_id!r} needs {group.minimum_players} usable members but has {usable_members}", "repair the hard group or exact exclusions"))
    for bound in policy.player_bounds:
        if bound.entity_id in policy.exact_exclusions and bound.minimum_entries > 0:
            issues.append(_issue("CLASSIC_POLICY_EXCLUSION_CONTRADICTS_MINIMUM", f"excluded person {bound.entity_id!r} has positive minimum exposure", "set the minimum to zero or remove the exact exclusion"))
        if bound.minimum_entries > bound.maximum_entries:
            issues.append(_issue("CLASSIC_POLICY_EFFECTIVE_BOUND_CONTRADICTORY", f"effective player bound is impossible for {bound.entity_id!r}", "repair the requested minimum or exclusion"))
    return tuple(issues)


def validate_classic_portfolio_policy_bytes(
    raw: bytes,
    *,
    slate: SlateContract,
    entry_ids: Sequence[str],
    entry_sha256: str,
    externally_excluded_people: Sequence[str] = (),
) -> ClassicPortfolioPolicyValidation:
    source_sha256 = sha256_bytes(raw)
    problems: list[PolicyIssue] = []
    findings: list[PolicyIssue] = []
    try:
        payload = json.loads(
            raw.decode("utf-8-sig"),
            parse_float=Decimal,
            parse_int=int,
            parse_constant=_reject_nonfinite,
            object_pairs_hook=_pairs_without_duplicates,
        )
    except _DuplicateKey as exc:
        return ClassicPortfolioPolicyValidation(source_sha256, None, (_issue("CLASSIC_POLICY_DUPLICATE_JSON_KEY", f"duplicate JSON key {str(exc)!r}", "retain each key once"),), ())
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        return ClassicPortfolioPolicyValidation(source_sha256, None, (_issue("CLASSIC_POLICY_JSON_INVALID", f"invalid UTF-8 JSON: {exc}", "repair the policy JSON"),), ())
    root = _mapping(payload, "policy", problems)
    if root is None:
        return ClassicPortfolioPolicyValidation(source_sha256, None, tuple(problems), ())
    _unknown_fields(root, {"schema_version", "bindings", "selection", "controls"}, "policy", problems)
    if root.get("schema_version") != POLICY_SCHEMA_VERSION:
        problems.append(_issue("CLASSIC_POLICY_SCHEMA_UNSUPPORTED", f"schema_version must be {POLICY_SCHEMA_VERSION!r}", "regenerate the C2 policy"))
    if slate.mode is not EngineMode.CLASSIC:
        problems.append(_issue("CLASSIC_POLICY_MODE_UNSUPPORTED", "the C2 policy requires a Classic salary contract", "use an exact Classic salary file"))
        return ClassicPortfolioPolicyValidation(source_sha256, None, tuple(problems), ())
    expected_people_tuple = classic_people(slate)
    expected_people = {person.underlying_id: person for person in expected_people_tuple}
    expected_identity = _complete_identity_payload(slate)
    # `entry_ids` are the rows a policy may bind (the plan's fillable blank rows);
    # the policy binds them all or, since Session 11b, a subset in template
    # order, and its own list sets every integer domain below.
    requested_entries = tuple(str(entry) for entry in entry_ids)
    count = len(requested_entries)
    if count < 1 or len(set(requested_entries)) != count or any(not entry for entry in requested_entries):
        problems.append(_issue("CLASSIC_POLICY_ENTRY_SET_INVALID", "requested Entry IDs must be non-empty, exact, ordered, and unique", "repair the entry template before policy validation"))
    bound_entries = requested_entries

    bindings = _mapping(root.get("bindings"), "bindings", problems)
    if bindings is not None:
        _unknown_fields(bindings, {"salary_sha256", "entry_sha256", "draft_group", "games", "teams", "positions", "roster_slots", "registered_stack_rule_types", "entry_ids", "people"}, "bindings", problems)
        exact_scalars = {
            "salary_sha256": slate.salary_hash,
            "entry_sha256": entry_sha256,
            "draft_group": slate.draft_group,
        }
        for name, expected in exact_scalars.items():
            if bindings.get(name) != expected:
                problems.append(_issue(f"CLASSIC_POLICY_{name.upper()}_MISMATCH", f"bindings.{name} does not match the immutable current input", "regenerate the policy from the current salary and entry bytes"))
        for name in ("games", "teams", "positions", "roster_slots", "registered_stack_rule_types", "people"):
            declared = bindings.get(name)
            expected_value = expected_identity[name]
            if name in {"games", "teams", "people"} and isinstance(declared, list):
                declared = sorted(declared, key=lambda item: json.dumps(item, sort_keys=True) if isinstance(item, Mapping) else str(item))
                expected_value = sorted(expected_value, key=lambda item: json.dumps(item, sort_keys=True))
            if declared != expected_value:
                problems.append(_issue(f"CLASSIC_POLICY_{name.upper()}_IDENTITY_MISMATCH", f"bindings.{name} is not the complete exact current identity set", "regenerate all bindings from the immutable salary contract"))
        declared_entries = bindings.get("entry_ids")
        if declared_entries != list(requested_entries):
            if not isinstance(declared_entries, list) or any(not isinstance(item, str) or not item for item in declared_entries):
                binding = ["entry_ids is not an array of exact Entry ID strings"]
            else:
                binding = subset_binding_problems(tuple(declared_entries), requested_entries)
            if binding:
                problems.append(_issue("CLASSIC_POLICY_ENTRY_ID_BINDING_MISMATCH", "entry_ids are not the template's fillable rows or a subset of them in template order: " + "; ".join(binding), "bind every fillable blank Entry ID, or a subset of them, once each in original order"))
            else:
                bound_entries = tuple(declared_entries)
                count = len(bound_entries)

    selection = _mapping(root.get("selection"), "selection", problems)
    search_limits: SearchLimits | None = None
    if selection is not None:
        _unknown_fields(selection, {"objective_version", "objective", "direction", "seed", "limits"}, "selection", problems)
        expected = {"objective_version": OBJECTIVE_VERSION, "objective": OBJECTIVE_NAME, "direction": "MAXIMIZE", "seed": SEED}
        for name, value in expected.items():
            if selection.get(name) != value:
                problems.append(_issue("CLASSIC_POLICY_SELECTION_CONTRACT_MISMATCH", f"selection.{name} must be {value!r}", "use the registered prior-only C2 selection contract"))
        limits = _mapping(selection.get("limits"), "selection.limits", problems)
        if limits is not None:
            _unknown_fields(limits, {"candidate_limit", "candidate_total_milliseconds", "candidate_per_solve_milliseconds", "selection_milliseconds"}, "selection.limits", problems)
            candidate_limit = _integer(limits.get("candidate_limit"), "selection.limits.candidate_limit", problems, minimum=max(1, count), maximum=5000)
            total_ms = _integer(limits.get("candidate_total_milliseconds"), "selection.limits.candidate_total_milliseconds", problems, minimum=1, maximum=3_600_000)
            per_solve_ms = _integer(limits.get("candidate_per_solve_milliseconds"), "selection.limits.candidate_per_solve_milliseconds", problems, minimum=1, maximum=300_000)
            selection_ms = _integer(limits.get("selection_milliseconds"), "selection.limits.selection_milliseconds", problems, minimum=1, maximum=3_600_000)
            if total_ms is not None and per_solve_ms is not None and per_solve_ms > total_ms:
                problems.append(_issue("CLASSIC_POLICY_SEARCH_LIMIT_CONTRADICTORY", "candidate_per_solve_milliseconds exceeds the total candidate budget", "raise the total budget or lower the per-solve budget"))
            if all(value is not None for value in (candidate_limit, total_ms, per_solve_ms, selection_ms)):
                search_limits = SearchLimits(int(candidate_limit), int(total_ms), int(per_solve_ms), int(selection_ms))

    controls = _mapping(root.get("controls"), "controls", problems)
    raw_player: dict[str, tuple[int, int]] = {}
    raw_team: dict[str, tuple[int, int]] = {}
    raw_game: dict[str, tuple[int, int]] = {}
    exclusions: list[str] = []
    groups: tuple[GroupRule, ...] = ()
    stack_rules: tuple[StackRule, ...] = ()
    overlap = 8
    unique = True
    teams = {team for team, _opponent, _game in _team_bindings(slate)}
    games = {game_id for game_id, _away, _home, _lock in _game_bindings(slate)}
    if controls is not None:
        _unknown_fields(controls, {"player_exposure_bounds", "team_exposure_bounds", "game_exposure_bounds", "exact_exclusions", "groups", "stack_rules", "max_pairwise_person_overlap", "require_unique_lineups"}, "controls", problems)
        raw_player = _parse_exposure_bounds(controls.get("player_exposure_bounds"), kind="player", valid_ids=set(expected_people), expected_people=expected_people, entry_count=count, problems=problems)
        raw_team = _parse_exposure_bounds(controls.get("team_exposure_bounds"), kind="team", valid_ids=teams, expected_people=expected_people, entry_count=count, problems=problems)
        raw_game = _parse_exposure_bounds(controls.get("game_exposure_bounds"), kind="game", valid_ids=games, expected_people=expected_people, entry_count=count, problems=problems)
        raw_exclusions = controls.get("exact_exclusions")
        if not isinstance(raw_exclusions, list):
            problems.append(_issue("CLASSIC_POLICY_EXCLUSION_LIST_REQUIRED", "controls.exact_exclusions must be an array", "supply zero or more exact person references"))
        else:
            for index, item in enumerate(raw_exclusions):
                parsed = _parse_person_reference(item, location=f"controls.exact_exclusions[{index}]", expected=expected_people, problems=problems)
                if parsed is not None:
                    exclusions.append(parsed)
            if len(set(exclusions)) != len(exclusions):
                problems.append(_issue("CLASSIC_POLICY_EXCLUSION_DUPLICATE", "exact_exclusions repeats a person", "retain each exact exclusion once"))
        groups = _parse_groups(controls.get("groups"), people=expected_people, entry_count=count, problems=problems)
        stack_rules = _parse_stack_rules(controls.get("stack_rules"), entry_count=count, problems=problems)
        overlap_value = _integer(controls.get("max_pairwise_person_overlap"), "controls.max_pairwise_person_overlap", problems, maximum=9)
        if overlap_value is not None:
            overlap = overlap_value
        if not isinstance(controls.get("require_unique_lineups"), bool):
            problems.append(_issue("CLASSIC_POLICY_UNIQUENESS_TYPE_INVALID", "require_unique_lineups must be Boolean", "set it to true; C2 requires canonical uniqueness"))
        else:
            unique = bool(controls.get("require_unique_lineups"))
            if not unique:
                problems.append(_issue("CLASSIC_POLICY_UNIQUENESS_REQUIRED", "C2 requires one unique canonical lineup per Entry ID", "set require_unique_lineups to true"))

    external = tuple(sorted({str(person) for person in externally_excluded_people if str(person)}))
    unknown_external = sorted(set(external).difference(expected_people))
    if unknown_external:
        problems.append(_issue("CLASSIC_POLICY_EXTERNAL_EXCLUSION_UNKNOWN", f"external exclusions reference unknown people {unknown_external}", "reconcile exclusions to exact Classic identities"))
    if problems or search_limits is None:
        return ClassicPortfolioPolicyValidation(source_sha256, None, tuple(problems), tuple(findings))

    effective_exclusions = set(exclusions) | set(external)
    player_bounds: list[EntityExposureBound] = []
    for person in expected_people_tuple:
        minimum, maximum = raw_player.get(person.underlying_id, (0, count))
        source = None
        if person.underlying_id in effective_exclusions:
            source = "SOURCE_OR_PARTICIPATION_PRECEDENCE" if person.underlying_id in external else "POLICY_EXCLUSION"
            maximum = 0
        player_bounds.append(EntityExposureBound(person.underlying_id, minimum, maximum, source))
    team_bounds = tuple(EntityExposureBound(team, *raw_team.get(team, (0, count))) for team in sorted(teams))
    game_bounds = tuple(EntityExposureBound(game, *raw_game.get(game, (0, count))) for game in sorted(games))
    policy = NormalizedClassicPortfolioPolicy(
        salary_sha256=slate.salary_hash,
        entry_sha256=entry_sha256,
        draft_group=slate.draft_group,
        games=_game_bindings(slate),
        teams=_team_bindings(slate),
        entry_ids=bound_entries,
        people=expected_people_tuple,
        player_bounds=tuple(player_bounds),
        team_bounds=team_bounds,
        game_bounds=game_bounds,
        exact_exclusions=tuple(sorted(effective_exclusions)),
        groups=groups,
        stack_rules=stack_rules,
        max_pairwise_person_overlap=overlap,
        require_unique_lineups=unique,
        search_limits=search_limits,
    )
    problems.extend(_capacity_issues(policy))
    for rule in (*groups, *stack_rules):
        if not rule.hard:
            findings.append(_issue("CLASSIC_POLICY_ADVISORY_NOT_ENFORCED", f"{getattr(rule, 'group_id', getattr(rule, 'rule_id', 'rule'))!r} is advisory and affects coverage only", "no action is required unless this preference should be HARD"))
    return ClassicPortfolioPolicyValidation(source_sha256, policy, tuple(problems), tuple(findings))


def validate_classic_portfolio_policy_file(
    path: str | Path,
    *,
    slate: SlateContract,
    entry_ids: Sequence[str],
    entry_sha256: str,
    externally_excluded_people: Sequence[str] = (),
    expected_sha256: str | None = None,
) -> ClassicPortfolioPolicyValidation:
    source = Path(path).resolve()
    validation = validate_classic_portfolio_policy_bytes(
        source.read_bytes(),
        slate=slate,
        entry_ids=entry_ids,
        entry_sha256=entry_sha256,
        externally_excluded_people=externally_excluded_people,
    )
    if expected_sha256 is not None and validation.source_sha256 != expected_sha256:
        issue = _issue("CLASSIC_POLICY_INPUT_MUTATED", "the source policy changed after immutable intake", "start a new run from stable source-policy bytes")
        return ClassicPortfolioPolicyValidation(validation.source_sha256, None, (issue, *validation.problems), validation.findings)
    return validation


def write_normalized_classic_portfolio_policy(
    path: str | Path, policy: NormalizedClassicPortfolioPolicy
) -> Path:
    target = Path(path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_bytes(policy.canonical_bytes())
    temporary.replace(target)
    return target


def write_classic_portfolio_policy_validation(
    path: str | Path, validation: ClassicPortfolioPolicyValidation
) -> Path:
    target = Path(path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_bytes(canonical_decimal_json_bytes(validation.as_report()) + b"\n")
    temporary.replace(target)
    return target


def parse_normalized_classic_policy_bytes(raw: bytes) -> NormalizedClassicPortfolioPolicy:
    """Strictly reconstruct the normalized policy for the independent audit."""

    payload = json.loads(
        raw.decode("utf-8"),
        parse_float=Decimal,
        parse_int=int,
        parse_constant=_reject_nonfinite,
        object_pairs_hook=_pairs_without_duplicates,
    )
    if canonical_decimal_json_bytes(payload) != raw:
        raise ValueError("CLASSIC_POLICY_NORMALIZED_BYTES_NOT_CANONICAL")
    if not isinstance(payload, Mapping) or payload.get("schema_version") != NORMALIZED_POLICY_SCHEMA_VERSION:
        raise ValueError("CLASSIC_POLICY_NORMALIZED_SCHEMA_UNSUPPORTED")
    bindings = payload.get("bindings")
    selection = payload.get("selection")
    controls = payload.get("controls")
    if not all(isinstance(value, Mapping) for value in (bindings, selection, controls)):
        raise ValueError("CLASSIC_POLICY_NORMALIZED_SECTION_INVALID")
    assert isinstance(bindings, Mapping) and isinstance(selection, Mapping) and isinstance(controls, Mapping)
    people = tuple(
        ClassicPersonBinding(
            underlying_id=str(item["underlying_id"]),
            dk_id=str(item["dk_id"]),
            name=str(item["name"]),
            team=str(item["team"]),
            opponent=str(item["opponent"]),
            game_id=str(item["game_id"]),
            position=str(item["position"]),
            roster_positions=tuple(str(value) for value in item["roster_positions"]),
            salary=int(item["salary"]),
        )
        for item in bindings["people"]
    )
    people_by_id = {person.underlying_id: person for person in people}
    player_bounds = tuple(
        EntityExposureBound(str(item["underlying_id"]), int(item["minimum_entries"]), int(item["maximum_entries"]), item.get("exclusion_source"))
        for item in controls["player_exposure_bounds"]
    )
    team_bounds = tuple(EntityExposureBound(str(item["team"]), int(item["minimum_entries"]), int(item["maximum_entries"]), item.get("exclusion_source")) for item in controls["team_exposure_bounds"])
    game_bounds = tuple(EntityExposureBound(str(item["game_id"]), int(item["minimum_entries"]), int(item["maximum_entries"]), item.get("exclusion_source")) for item in controls["game_exposure_bounds"])
    groups = tuple(
        GroupRule(
            str(item["group_id"]),
            tuple(sorted(str(member["underlying_id"]) for member in item["members"])),
            int(item["minimum_players"]),
            int(item["maximum_players"]),
            int(item["minimum_entries"]),
            int(item["maximum_entries"]),
            str(item["strength"]),
        )
        for item in controls["groups"]
    )
    stack_rules = tuple(StackRule(str(item["rule_id"]), str(item["rule_type"]), int(item["minimum_value"]), int(item["maximum_value"]), int(item["minimum_entries"]), int(item["maximum_entries"]), str(item["strength"])) for item in controls["stack_rules"])
    limits = selection["limits"]
    assert isinstance(limits, Mapping)
    policy = NormalizedClassicPortfolioPolicy(
        salary_sha256=str(bindings["salary_sha256"]),
        entry_sha256=str(bindings["entry_sha256"]),
        draft_group=str(bindings["draft_group"]),
        games=tuple((str(item["game_id"]), str(item["away_team"]), str(item["home_team"]), str(item["lock_at"])) for item in bindings["games"]),
        teams=tuple((str(item["team"]), str(item["opponent"]), str(item["game_id"])) for item in bindings["teams"]),
        entry_ids=tuple(str(item) for item in bindings["entry_ids"]),
        people=people,
        player_bounds=player_bounds,
        team_bounds=team_bounds,
        game_bounds=game_bounds,
        exact_exclusions=tuple(str(item["underlying_id"]) for item in controls["exact_exclusions"]),
        groups=groups,
        stack_rules=stack_rules,
        max_pairwise_person_overlap=int(controls["max_pairwise_person_overlap"]),
        require_unique_lineups=bool(controls["require_unique_lineups"]),
        search_limits=SearchLimits(int(limits["candidate_limit"]), int(limits["candidate_total_milliseconds"]), int(limits["candidate_per_solve_milliseconds"]), int(limits["selection_milliseconds"])),
        objective_version=str(selection["objective_version"]),
        objective_name=str(selection["objective"]),
        seed=int(selection["seed"]),
    )
    if policy.canonical_bytes() != raw or len(people_by_id) != len(people):
        raise ValueError("CLASSIC_POLICY_NORMALIZED_SEMANTICS_INVALID")
    return policy
