"""Versioned Showdown portfolio controls and deterministic normalization.

SD3 owns this contract. SD4 consumes its exact integer maxima and canonical
bytes in a separate bounded selector and independent final-assignment audit.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal, ROUND_FLOOR
from pathlib import Path
from typing import Mapping, Sequence

from .contracts import EngineMode, SlateContract
from .entry_groups import subset_binding_problems
from .hashing import sha256_bytes
from .lineups import validate_lineup


POLICY_SCHEMA_VERSION = "nfl_showdown_portfolio_policy_v1"
NORMALIZED_POLICY_SCHEMA_VERSION = "nfl_showdown_portfolio_policy_normalized_v1"
FRACTION_UNIT = "FRACTION_0_TO_1"


@dataclass(frozen=True, order=True)
class PersonBinding:
    underlying_id: str
    cpt_dk_id: str
    flex_dk_id: str

    def as_mapping(self) -> dict[str, str]:
        return {
            "underlying_id": self.underlying_id,
            "cpt_dk_id": self.cpt_dk_id,
            "flex_dk_id": self.flex_dk_id,
        }


@dataclass(frozen=True)
class ExposureOverride:
    person: PersonBinding
    fraction: Decimal


@dataclass(frozen=True)
class ExposureRule:
    default_fraction: Decimal | None
    overrides: tuple[ExposureOverride, ...]

    def fraction_for(self, person_id: str) -> tuple[Decimal | None, str]:
        by_person = {item.person.underlying_id: item.fraction for item in self.overrides}
        if person_id in by_person:
            return by_person[person_id], "PERSON_OVERRIDE"
        if self.default_fraction is not None:
            return self.default_fraction, "DEFAULT"
        return None, "OMITTED_NO_CAP"


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
class EffectivePersonLimit:
    person: PersonBinding
    combined_fraction: Decimal | None
    combined_source: str
    combined_max_entries: int
    captain_fraction: Decimal | None
    captain_source: str
    declared_captain_max_entries: int
    captain_max_entries: int
    excluded: bool
    exclusion_source: str | None

    def as_mapping(self) -> dict[str, object]:
        return {
            **self.person.as_mapping(),
            "combined_fraction": self.combined_fraction,
            "combined_source": self.combined_source,
            "combined_max_entries": self.combined_max_entries,
            "captain_fraction": self.captain_fraction,
            "captain_source": self.captain_source,
            "declared_captain_max_entries": self.declared_captain_max_entries,
            "captain_max_entries": self.captain_max_entries,
            "excluded": self.excluded,
            "exclusion_source": self.exclusion_source,
        }


@dataclass(frozen=True)
class NormalizedPortfolioPolicy:
    salary_sha256: str
    game_id: str
    entry_ids: tuple[str, ...]
    people: tuple[PersonBinding, ...]
    combined_rule: ExposureRule
    captain_rule: ExposureRule
    excluded_people: tuple[PersonBinding, ...]
    max_pairwise_person_overlap: int | None
    require_unique_lineups: bool
    effective_limits: tuple[EffectivePersonLimit, ...]

    @property
    def entry_count(self) -> int:
        return len(self.entry_ids)

    @property
    def effective_pairwise_person_overlap(self) -> int:
        return 6 if self.max_pairwise_person_overlap is None else self.max_pairwise_person_overlap

    def as_mapping(self) -> dict[str, object]:
        return {
            "schema_version": NORMALIZED_POLICY_SCHEMA_VERSION,
            "bindings": {
                "salary_sha256": self.salary_sha256,
                "game_id": self.game_id,
                "entry_ids": list(self.entry_ids),
                "person_identities": [person.as_mapping() for person in self.people],
            },
            "controls": {
                "fraction_unit": FRACTION_UNIT,
                "max_combined_person_exposure": _rule_mapping(self.combined_rule),
                "max_captain_exposure": _rule_mapping(self.captain_rule),
                "excluded_people": [person.as_mapping() for person in self.excluded_people],
                "max_pairwise_person_overlap": self.max_pairwise_person_overlap,
                "effective_pairwise_person_overlap": self.effective_pairwise_person_overlap,
                "require_unique_lineups": self.require_unique_lineups,
            },
            "effective": {
                "entry_count_denominator": self.entry_count,
                "rounding": "FLOOR_EXACT_DECIMAL",
                "captain_is_subset_of_combined": True,
                "people": [item.as_mapping() for item in self.effective_limits],
            },
        }

    def canonical_bytes(self) -> bytes:
        return canonical_decimal_json_bytes(self.as_mapping())

    @property
    def normalized_sha256(self) -> str:
        return sha256_bytes(self.canonical_bytes())


@dataclass(frozen=True)
class PortfolioPolicyValidation:
    source_sha256: str
    policy: NormalizedPortfolioPolicy | None
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
            "enforcement_blocker": None,
        }


@dataclass(frozen=True)
class PortfolioSemantics:
    entry_ids: tuple[str, ...]
    canonical_lineups: tuple[tuple[str, str], ...]
    combined_person_counts: tuple[tuple[str, int], ...]
    captain_counts: tuple[tuple[str, int], ...]
    duplicate_canonical_lineups: tuple[str, ...]
    pairwise_person_overlap: tuple[tuple[str, str, int], ...]

    def as_report(self) -> dict[str, object]:
        return {
            "entry_ids": list(self.entry_ids),
            "canonical_lineups": dict(self.canonical_lineups),
            "combined_person_counts": dict(self.combined_person_counts),
            "captain_counts": dict(self.captain_counts),
            "duplicate_canonical_lineups": list(self.duplicate_canonical_lineups),
            "pairwise_person_overlap": [
                {"entry_id_a": left, "entry_id_b": right, "people": count}
                for left, right, count in self.pairwise_person_overlap
            ],
        }


class _DuplicateKey(ValueError):
    pass


class _NonFiniteNumber(ValueError):
    pass


def _pairs_without_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise _DuplicateKey(key)
        value[key] = item
    return value


def _reject_nonfinite(value: str) -> object:
    raise _NonFiniteNumber(value)


def _decimal_text(value: Decimal) -> str:
    if not value.is_finite():
        raise ValueError("canonical JSON cannot contain a nonfinite Decimal")
    if value == 0:
        return "0"
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def canonical_decimal_json_bytes(value: object) -> bytes:
    """Serialize normalized policy values with exact JSON decimal numbers."""

    def encode(item: object) -> str:
        if item is None:
            return "null"
        if item is True:
            return "true"
        if item is False:
            return "false"
        if isinstance(item, str):
            return json.dumps(item, ensure_ascii=False)
        if isinstance(item, Decimal):
            return _decimal_text(item)
        if isinstance(item, int):
            return str(item)
        if isinstance(item, (list, tuple)):
            return "[" + ",".join(encode(child) for child in item) + "]"
        if isinstance(item, Mapping):
            pairs = (
                json.dumps(str(key), ensure_ascii=False) + ":" + encode(child)
                for key, child in sorted(item.items(), key=lambda pair: str(pair[0]))
            )
            return "{" + ",".join(pairs) + "}"
        raise TypeError(f"unsupported canonical policy value: {type(item).__name__}")

    return encode(value).encode("utf-8")


def write_normalized_portfolio_policy(
    path: str | Path, policy: NormalizedPortfolioPolicy
) -> Path:
    target = Path(path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_bytes(policy.canonical_bytes())
    temporary.replace(target)
    return target


def write_portfolio_policy_validation(
    path: str | Path, validation: PortfolioPolicyValidation
) -> Path:
    target = Path(path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_bytes(canonical_decimal_json_bytes(validation.as_report()) + b"\n")
    temporary.replace(target)
    return target


def salary_person_bindings(slate: SlateContract) -> tuple[PersonBinding, ...]:
    """Return the complete exact Showdown CPT/FLEX identity map."""

    if slate.mode is not EngineMode.SHOWDOWN:
        raise ValueError("PORTFOLIO_POLICY_MODE_UNSUPPORTED: Showdown salary rows are required")
    grouped: dict[str, dict[str, str]] = {}
    for row in slate.players:
        if row.role not in {"CPT", "FLEX"}:
            raise ValueError(
                f"PORTFOLIO_POLICY_ROLE_IDENTITY_INVALID:{row.underlying_id}:{row.role}"
            )
        roles = grouped.setdefault(row.underlying_id, {})
        if row.role in roles:
            raise ValueError(
                f"PORTFOLIO_POLICY_DUPLICATE_ROLE_IDENTITY:{row.underlying_id}:{row.role}"
            )
        roles[row.role] = row.dk_id
    missing = sorted(person for person, roles in grouped.items() if set(roles) != {"CPT", "FLEX"})
    if missing:
        raise ValueError(f"PORTFOLIO_POLICY_ROLE_IDENTITY_INCOMPLETE:{missing}")
    return tuple(
        PersonBinding(person, roles["CPT"], roles["FLEX"])
        for person, roles in sorted(grouped.items())
    )


def _rule_mapping(rule: ExposureRule) -> dict[str, object]:
    return {
        "default_fraction": rule.default_fraction,
        "overrides": [
            {**item.person.as_mapping(), "fraction": item.fraction}
            for item in rule.overrides
        ],
    }


def portfolio_policy_template(
    slate: SlateContract,
    entry_ids: Sequence[str],
    *,
    controls: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Build exact bindings for an operator-authored controls object."""

    if len(slate.games) != 1:
        raise ValueError("PORTFOLIO_POLICY_GAME_BINDING_INVALID: exactly one game is required")
    return {
        "schema_version": POLICY_SCHEMA_VERSION,
        "bindings": {
            "salary_sha256": slate.salary_hash,
            "game_id": slate.games[0].game_id,
            "entry_ids": list(entry_ids),
            "person_identities": [
                person.as_mapping() for person in salary_person_bindings(slate)
            ],
        },
        "controls": {
            "fraction_unit": FRACTION_UNIT,
            "max_combined_person_exposure": {
                "default_fraction": None,
                "overrides": [],
            },
            "max_captain_exposure": {
                "default_fraction": None,
                "overrides": [],
            },
            "excluded_people": [],
            "max_pairwise_person_overlap": None,
            "require_unique_lineups": True,
            **dict(controls or {}),
        },
    }


def _issue(code: str, message: str, next_action: str) -> PolicyIssue:
    return PolicyIssue(code, message, next_action)


def _unknown_fields(
    value: Mapping[str, object], allowed: set[str], location: str, problems: list[PolicyIssue]
) -> None:
    unknown = sorted(set(value).difference(allowed))
    if unknown:
        problems.append(
            _issue(
                "PORTFOLIO_POLICY_UNKNOWN_FIELD",
                f"{location} contains unsupported fields {unknown}",
                "remove the unsupported fields and regenerate the policy",
            )
        )


def _mapping(
    value: object, location: str, problems: list[PolicyIssue]
) -> Mapping[str, object] | None:
    if not isinstance(value, Mapping):
        problems.append(
            _issue(
                "PORTFOLIO_POLICY_OBJECT_REQUIRED",
                f"{location} must be a JSON object",
                f"replace {location} with the documented object shape",
            )
        )
        return None
    return value


def _nonempty_string(
    value: object, location: str, problems: list[PolicyIssue]
) -> str | None:
    if not isinstance(value, str) or not value.strip():
        problems.append(
            _issue(
                "PORTFOLIO_POLICY_STRING_REQUIRED",
                f"{location} must be a non-empty JSON string",
                f"supply the exact documented value for {location}",
            )
        )
        return None
    return value.strip()


def _fraction(
    value: object, location: str, problems: list[PolicyIssue]
) -> Decimal | None:
    if isinstance(value, bool) or not isinstance(value, (Decimal, int)):
        problems.append(
            _issue(
                "PORTFOLIO_POLICY_FRACTION_TYPE_INVALID",
                f"{location} must be a JSON number, never a Boolean or numeric string",
                "supply a numeric fraction from 0 through 1 with fraction_unit FRACTION_0_TO_1",
            )
        )
        return None
    decimal = value if isinstance(value, Decimal) else Decimal(value)
    if not decimal.is_finite():
        problems.append(
            _issue(
                "PORTFOLIO_POLICY_FRACTION_NONFINITE",
                f"{location} must be finite",
                "replace the value with a finite fraction from 0 through 1",
            )
        )
        return None
    if decimal < 0 or decimal > 1:
        problems.append(
            _issue(
                "PORTFOLIO_POLICY_FRACTION_OUT_OF_RANGE",
                f"{location}={decimal} is outside [0,1]",
                "convert the intended percentage to an explicit fraction from 0 through 1",
            )
        )
        return None
    return decimal


def _identity_list(
    value: object,
    *,
    location: str,
    required: bool,
    problems: list[PolicyIssue],
) -> tuple[PersonBinding, ...] | None:
    if value is None and not required:
        return ()
    if not isinstance(value, list):
        problems.append(
            _issue(
                "PORTFOLIO_POLICY_IDENTITY_LIST_REQUIRED",
                f"{location} must be a JSON array",
                f"supply the documented exact identity array for {location}",
            )
        )
        return None
    identities: list[PersonBinding] = []
    for index, raw in enumerate(value):
        item = _mapping(raw, f"{location}[{index}]", problems)
        if item is None:
            continue
        _unknown_fields(
            item,
            {"underlying_id", "cpt_dk_id", "flex_dk_id"},
            f"{location}[{index}]",
            problems,
        )
        person = _nonempty_string(item.get("underlying_id"), f"{location}[{index}].underlying_id", problems)
        cpt = _nonempty_string(item.get("cpt_dk_id"), f"{location}[{index}].cpt_dk_id", problems)
        flex = _nonempty_string(item.get("flex_dk_id"), f"{location}[{index}].flex_dk_id", problems)
        if person is not None and cpt is not None and flex is not None:
            identities.append(PersonBinding(person, cpt, flex))
    person_counts = Counter(item.underlying_id for item in identities)
    cpt_counts = Counter(item.cpt_dk_id for item in identities)
    flex_counts = Counter(item.flex_dk_id for item in identities)
    duplicates = sorted(
        [f"person:{key}" for key, count in person_counts.items() if count > 1]
        + [f"cpt:{key}" for key, count in cpt_counts.items() if count > 1]
        + [f"flex:{key}" for key, count in flex_counts.items() if count > 1]
    )
    if duplicates:
        problems.append(
            _issue(
                "PORTFOLIO_POLICY_DUPLICATE_IDENTITY",
                f"{location} repeats identities {duplicates}",
                "retain each underlying person and each role ID exactly once",
            )
        )
    return tuple(sorted(identities))


def _validate_identity_reference(
    reference: PersonBinding,
    *,
    expected: Mapping[str, PersonBinding],
    dk_roles: Mapping[str, tuple[str, str]],
    location: str,
    problems: list[PolicyIssue],
) -> bool:
    unknown_ids = sorted(
        dk_id
        for dk_id in (reference.cpt_dk_id, reference.flex_dk_id)
        if dk_id not in dk_roles
    )
    if unknown_ids:
        problems.append(
            _issue(
                "PORTFOLIO_POLICY_UNKNOWN_DK_ID",
                f"{location} contains role IDs outside the salary file {unknown_ids}",
                "regenerate the policy bindings from the exact current salary CSV",
            )
        )
        return False
    expected_person = expected.get(reference.underlying_id)
    if expected_person is None:
        problems.append(
            _issue(
                "PORTFOLIO_POLICY_UNKNOWN_PERSON_ID",
                f"{location} references unknown underlying person {reference.underlying_id!r}",
                "choose an exact underlying person from the current salary identity bindings",
            )
        )
        return False
    cpt_person, cpt_role = dk_roles[reference.cpt_dk_id]
    flex_person, flex_role = dk_roles[reference.flex_dk_id]
    if (
        cpt_role != "CPT"
        or flex_role != "FLEX"
        or cpt_person != flex_person
        or cpt_person != reference.underlying_id
        or reference != expected_person
    ):
        problems.append(
            _issue(
                "PORTFOLIO_POLICY_CONFLICTING_ROLE_IDENTITY",
                f"{location} does not bind one person's exact CPT and FLEX IDs",
                "replace the reference with the exact current salary identity binding",
            )
        )
        return False
    return True


def _exposure_rule(
    value: object,
    *,
    location: str,
    expected: Mapping[str, PersonBinding],
    dk_roles: Mapping[str, tuple[str, str]],
    problems: list[PolicyIssue],
) -> ExposureRule | None:
    if value is None:
        return ExposureRule(None, ())
    item = _mapping(value, location, problems)
    if item is None:
        return None
    _unknown_fields(item, {"default_fraction", "overrides"}, location, problems)
    default_raw = item.get("default_fraction")
    default = None if default_raw is None else _fraction(default_raw, f"{location}.default_fraction", problems)
    overrides_raw = item.get("overrides", [])
    if not isinstance(overrides_raw, list):
        problems.append(
            _issue(
                "PORTFOLIO_POLICY_OVERRIDE_LIST_REQUIRED",
                f"{location}.overrides must be a JSON array",
                "supply an array with at most one exact binding per person",
            )
        )
        return None
    overrides: list[ExposureOverride] = []
    for index, raw in enumerate(overrides_raw):
        override_location = f"{location}.overrides[{index}]"
        override = _mapping(raw, override_location, problems)
        if override is None:
            continue
        _unknown_fields(
            override,
            {"underlying_id", "cpt_dk_id", "flex_dk_id", "fraction"},
            override_location,
            problems,
        )
        identities = _identity_list(
            [{key: override.get(key) for key in ("underlying_id", "cpt_dk_id", "flex_dk_id")}],
            location=override_location,
            required=True,
            problems=problems,
        )
        fraction = _fraction(override.get("fraction"), f"{override_location}.fraction", problems)
        if identities and fraction is not None:
            reference = identities[0]
            if _validate_identity_reference(
                reference,
                expected=expected,
                dk_roles=dk_roles,
                location=override_location,
                problems=problems,
            ):
                overrides.append(ExposureOverride(reference, fraction))
    counts = Counter(item.person.underlying_id for item in overrides)
    duplicates = sorted(person for person, count in counts.items() if count > 1)
    if duplicates:
        problems.append(
            _issue(
                "PORTFOLIO_POLICY_DUPLICATE_OVERRIDE",
                f"{location} repeats per-person overrides {duplicates}",
                "retain one override per underlying person in this control",
            )
        )
    return ExposureRule(default, tuple(sorted(overrides, key=lambda row: row.person)))


def _integer_max(fraction: Decimal | None, entry_count: int) -> int:
    if fraction is None:
        return entry_count
    return int((fraction * Decimal(entry_count)).to_integral_value(rounding=ROUND_FLOOR))


def _necessary_capacity_issues(
    policy: NormalizedPortfolioPolicy, slate: SlateContract
) -> tuple[PolicyIssue, ...]:
    issues: list[PolicyIssue] = []
    count = policy.entry_count
    available = [item for item in policy.effective_limits if item.combined_max_entries > 0]
    available_people = {item.person.underlying_id for item in available}
    if len(available) < 6:
        issues.append(
            _issue(
                "PORTFOLIO_POLICY_PERSON_CAPACITY_INSUFFICIENT",
                f"only {len(available)} people can appear, but every Showdown lineup needs six",
                "raise or remove combined-person caps, or remove exclusions for enough exact people",
            )
        )
    if sum(item.combined_max_entries for item in policy.effective_limits) < 6 * count:
        issues.append(
            _issue(
                "PORTFOLIO_POLICY_COMBINED_EXPOSURE_CAPACITY_INSUFFICIENT",
                "the sum of combined-person integer maxima cannot fill all requested roster slots",
                "raise explicit combined-person fractions while preserving the intended strict caps",
            )
        )
    if sum(item.captain_max_entries for item in policy.effective_limits) < count:
        issues.append(
            _issue(
                "PORTFOLIO_POLICY_CAPTAIN_CAPACITY_INSUFFICIENT",
                "the sum of effective Captain integer maxima cannot fill all requested Captain slots",
                "raise explicit Captain or combined-person fractions for eligible exact people",
            )
        )
    teams = {
        row.team for row in slate.players if row.underlying_id in available_people
    }
    if len(teams) < 2:
        issues.append(
            _issue(
                "PORTFOLIO_POLICY_TEAM_CAPACITY_INSUFFICIENT",
                "the effective person pool cannot satisfy the two-team Showdown rule",
                "permit at least one exact person from each team",
            )
        )
    if count > 1 and policy.max_pairwise_person_overlap is not None:
        minimum_overlap = max(0, 12 - len(available))
        if policy.max_pairwise_person_overlap < minimum_overlap:
            issues.append(
                _issue(
                    "PORTFOLIO_POLICY_PAIRWISE_OVERLAP_CAPACITY_INSUFFICIENT",
                    f"{len(available)} usable people force pairwise overlap of at least {minimum_overlap}",
                    "raise the overlap limit or permit more exact people",
                )
            )
    if policy.require_unique_lineups:
        available_count = len(available)
        unique_upper_bound = sum(
            math.comb(available_count - 1, 5)
            for item in available
            if item.captain_max_entries > 0 and available_count >= 6
        )
        if unique_upper_bound < count:
            issues.append(
                _issue(
                    "PORTFOLIO_POLICY_UNIQUE_LINEUP_CAPACITY_INSUFFICIENT",
                    f"at most {unique_upper_bound} canonical lineups remain for {count} requested entries",
                    "raise caps, permit more people, or explicitly disable canonical uniqueness",
                )
            )
    by_id = {row.dk_id: row for row in slate.players}
    cheapest_legal = None
    for item in available:
        if item.captain_max_entries < 1:
            continue
        captain = by_id[item.person.cpt_dk_id]
        flex = sorted(
            (
                by_id[other.person.flex_dk_id]
                for other in available
                if other.person.underlying_id != item.person.underlying_id
            ),
            key=lambda row: (row.salary, row.dk_id),
        )
        if len(flex) < 5:
            continue
        selected = flex[:5]
        if len({captain.team, *(row.team for row in selected)}) < 2:
            opponent_flex = [row for row in flex if row.team != captain.team]
            if not opponent_flex:
                continue
            selected = flex[:4] + [opponent_flex[0]]
        salary = captain.salary + sum(row.salary for row in selected)
        cheapest_legal = salary if cheapest_legal is None else min(cheapest_legal, salary)
    if cheapest_legal is None or cheapest_legal > slate.salary_cap:
        issues.append(
            _issue(
                "PORTFOLIO_POLICY_SALARY_CAPACITY_INSUFFICIENT",
                "the effective pool cannot form even one two-team lineup under the salary cap",
                "permit a lower-salary exact Captain/FLEX combination without weakening other gates",
            )
        )
    return tuple(issues)


def validate_portfolio_policy_bytes(
    raw: bytes,
    *,
    slate: SlateContract,
    entry_ids: Sequence[str],
    externally_excluded_people: Sequence[str] = (),
) -> PortfolioPolicyValidation:
    """Validate exact input bindings and derive integer limits without solving.

    `entry_ids` are the rows a policy may bind: the plan's fillable blank rows in
    template order. The policy binds all of them or, since Session 11b, a
    non-empty subset in the same order, and its own list is the denominator.
    """

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
        problems.append(
            _issue(
                "PORTFOLIO_POLICY_DUPLICATE_JSON_KEY",
                f"the JSON object repeats key {str(exc)!r}",
                "retain each JSON object key exactly once",
            )
        )
        return PortfolioPolicyValidation(source_sha256, None, tuple(problems), ())
    except _NonFiniteNumber as exc:
        problems.append(
            _issue(
                "PORTFOLIO_POLICY_FRACTION_NONFINITE",
                f"the policy contains nonfinite JSON number {str(exc)!r}",
                "replace it with a finite fraction from 0 through 1",
            )
        )
        return PortfolioPolicyValidation(source_sha256, None, tuple(problems), ())
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        problems.append(
            _issue(
                "PORTFOLIO_POLICY_JSON_INVALID",
                f"the policy is not valid UTF-8 JSON: {exc}",
                "repair the JSON syntax without changing the intended exact bindings",
            )
        )
        return PortfolioPolicyValidation(source_sha256, None, tuple(problems), ())

    root = _mapping(payload, "policy", problems)
    if root is None:
        return PortfolioPolicyValidation(source_sha256, None, tuple(problems), ())
    _unknown_fields(root, {"schema_version", "bindings", "controls"}, "policy", problems)
    if root.get("schema_version") != POLICY_SCHEMA_VERSION:
        problems.append(
            _issue(
                "PORTFOLIO_POLICY_SCHEMA_UNSUPPORTED",
                f"schema_version must be {POLICY_SCHEMA_VERSION!r}",
                "regenerate the policy with the current versioned contract",
            )
        )
    if slate.mode is not EngineMode.SHOWDOWN or len(slate.games) != 1:
        problems.append(
            _issue(
                "PORTFOLIO_POLICY_MODE_UNSUPPORTED",
                "the v1 policy requires one Showdown game",
                "use an exact single-game Showdown salary CSV",
            )
        )
        return PortfolioPolicyValidation(source_sha256, None, tuple(problems), ())
    try:
        expected_people_tuple = salary_person_bindings(slate)
    except ValueError as exc:
        problems.append(
            _issue(
                "PORTFOLIO_POLICY_SALARY_IDENTITY_INVALID",
                str(exc),
                "repair the salary identity contract before authoring portfolio controls",
            )
        )
        return PortfolioPolicyValidation(source_sha256, None, tuple(problems), ())
    expected_people = {item.underlying_id: item for item in expected_people_tuple}
    dk_roles = {
        row.dk_id: (row.underlying_id, row.role or "") for row in slate.players
    }

    bindings = _mapping(root.get("bindings"), "bindings", problems)
    declared_people: tuple[PersonBinding, ...] | None = None
    requested_entry_ids: tuple[str, ...] = ()
    if bindings is not None:
        _unknown_fields(
            bindings,
            {"salary_sha256", "game_id", "entry_ids", "person_identities"},
            "bindings",
            problems,
        )
        salary_sha = _nonempty_string(bindings.get("salary_sha256"), "bindings.salary_sha256", problems)
        if salary_sha is not None and salary_sha != slate.salary_hash:
            problems.append(
                _issue(
                    "PORTFOLIO_POLICY_SALARY_HASH_MISMATCH",
                    "the policy salary SHA-256 does not match the exact current salary bytes",
                    "regenerate the policy from the current immutable salary snapshot",
                )
            )
        game_id = _nonempty_string(bindings.get("game_id"), "bindings.game_id", problems)
        if game_id is not None and game_id != slate.games[0].game_id:
            problems.append(
                _issue(
                    "PORTFOLIO_POLICY_GAME_ID_MISMATCH",
                    f"policy game {game_id!r} does not match {slate.games[0].game_id!r}",
                    "regenerate the policy for the current single game",
                )
            )
        raw_entries = bindings.get("entry_ids")
        if not isinstance(raw_entries, list) or any(
            not isinstance(item, str) or not item.strip() for item in raw_entries
        ):
            problems.append(
                _issue(
                    "PORTFOLIO_POLICY_ENTRY_IDS_INVALID",
                    "bindings.entry_ids must be an array of non-empty exact strings",
                    "copy every requested Entry ID from the immutable entry template in order",
                )
            )
        else:
            requested_entry_ids = tuple(item.strip() for item in raw_entries)
            duplicates = sorted(
                entry for entry, count in Counter(requested_entry_ids).items() if count > 1
            )
            if duplicates:
                problems.append(
                    _issue(
                        "PORTFOLIO_POLICY_DUPLICATE_ENTRY_ID",
                        f"the policy repeats Entry IDs {duplicates}",
                        "retain every requested Entry ID exactly once in template order",
                    )
                )
            # Session 11b: a policy binds the fillable rows (`entry_ids`) or a
            # non-empty subset of them in template order; its own list is the
            # denominator. A template with no fillable row keeps the exact rule.
            binding = (
                subset_binding_problems(requested_entry_ids, tuple(entry_ids))
                if entry_ids else (["it binds Entry IDs the template does not offer"]
                                   if requested_entry_ids else [])
            )
            if binding:
                problems.append(
                    _issue(
                        "PORTFOLIO_POLICY_ENTRY_ID_BINDING_MISMATCH",
                        "the policy Entry IDs are not the template's fillable rows or a subset of them"
                        " in template order: " + "; ".join(binding),
                        "bind every fillable blank Entry ID, or a subset of them, once each in template order",
                    )
                )
        declared_people = _identity_list(
            bindings.get("person_identities"),
            location="bindings.person_identities",
            required=True,
            problems=problems,
        )
        if declared_people is not None:
            for index, reference in enumerate(declared_people):
                _validate_identity_reference(
                    reference,
                    expected=expected_people,
                    dk_roles=dk_roles,
                    location=f"bindings.person_identities[{index}]",
                    problems=problems,
                )
            if declared_people != expected_people_tuple:
                problems.append(
                    _issue(
                        "PORTFOLIO_POLICY_PERSON_IDENTITY_COVERAGE_MISMATCH",
                        "the policy does not contain the complete exact salary person identity map",
                        "regenerate all person bindings from the current immutable salary snapshot",
                    )
                )

    controls = _mapping(root.get("controls"), "controls", problems)
    combined_rule: ExposureRule | None = None
    captain_rule: ExposureRule | None = None
    excluded_people: tuple[PersonBinding, ...] | None = ()
    overlap_limit: int | None = None
    unique = True
    if controls is not None:
        _unknown_fields(
            controls,
            {
                "fraction_unit",
                "max_combined_person_exposure",
                "max_captain_exposure",
                "excluded_people",
                "max_pairwise_person_overlap",
                "require_unique_lineups",
            },
            "controls",
            problems,
        )
        if controls.get("fraction_unit") != FRACTION_UNIT:
            problems.append(
                _issue(
                    "PORTFOLIO_POLICY_FRACTION_UNIT_INVALID",
                    f"controls.fraction_unit must be exactly {FRACTION_UNIT!r}",
                    "declare fractions in [0,1]; do not supply bare percentage units",
                )
            )
        combined_rule = _exposure_rule(
            controls.get("max_combined_person_exposure"),
            location="controls.max_combined_person_exposure",
            expected=expected_people,
            dk_roles=dk_roles,
            problems=problems,
        )
        captain_rule = _exposure_rule(
            controls.get("max_captain_exposure"),
            location="controls.max_captain_exposure",
            expected=expected_people,
            dk_roles=dk_roles,
            problems=problems,
        )
        excluded_people = _identity_list(
            controls.get("excluded_people", []),
            location="controls.excluded_people",
            required=False,
            problems=problems,
        )
        if excluded_people is not None:
            for index, reference in enumerate(excluded_people):
                _validate_identity_reference(
                    reference,
                    expected=expected_people,
                    dk_roles=dk_roles,
                    location=f"controls.excluded_people[{index}]",
                    problems=problems,
                )
        overlap_raw = controls.get("max_pairwise_person_overlap")
        if overlap_raw is not None:
            if isinstance(overlap_raw, bool) or not isinstance(overlap_raw, int):
                problems.append(
                    _issue(
                        "PORTFOLIO_POLICY_OVERLAP_TYPE_INVALID",
                        "max_pairwise_person_overlap must be a JSON integer or null",
                        "supply an underlying-person count from 0 through 6",
                    )
                )
            elif overlap_raw < 0 or overlap_raw > 6:
                problems.append(
                    _issue(
                        "PORTFOLIO_POLICY_OVERLAP_OUT_OF_RANGE",
                        "max_pairwise_person_overlap must be from 0 through 6",
                        "supply the intended maximum number of shared underlying people",
                    )
                )
            else:
                overlap_limit = overlap_raw
        unique_raw = controls.get("require_unique_lineups", True)
        if not isinstance(unique_raw, bool):
            problems.append(
                _issue(
                    "PORTFOLIO_POLICY_UNIQUENESS_TYPE_INVALID",
                    "require_unique_lineups must be true or false",
                    "choose an explicit Boolean canonical-lineup uniqueness setting",
                )
            )
        else:
            unique = unique_raw

    external = tuple(sorted(set(str(person).strip() for person in externally_excluded_people if str(person).strip())))
    unknown_external = sorted(set(external).difference(expected_people))
    if unknown_external:
        problems.append(
            _issue(
                "PORTFOLIO_POLICY_EXTERNAL_EXCLUSION_UNKNOWN",
                f"source/participation exclusions reference unknown people {unknown_external}",
                "reconcile exclusions to the exact current salary identity map",
            )
        )
    if problems or combined_rule is None or captain_rule is None or excluded_people is None:
        return PortfolioPolicyValidation(source_sha256, None, tuple(problems), tuple(findings))

    count = len(requested_entry_ids)
    if count < 1:
        problems.append(
            _issue(
                "PORTFOLIO_POLICY_ENTRY_SET_EMPTY",
                "the denominator cannot be empty",
                "supply a reserved-entry template with at least one exact Entry ID",
            )
        )
        return PortfolioPolicyValidation(source_sha256, None, tuple(problems), tuple(findings))
    policy_excluded = {person.underlying_id for person in excluded_people}
    external_excluded = set(external)
    effective_limits: list[EffectivePersonLimit] = []
    for person in expected_people_tuple:
        combined_fraction, combined_source = combined_rule.fraction_for(person.underlying_id)
        captain_fraction, captain_source = captain_rule.fraction_for(person.underlying_id)
        declared_combined = _integer_max(combined_fraction, count)
        declared_captain = _integer_max(captain_fraction, count)
        exclusion_source = None
        if person.underlying_id in external_excluded:
            exclusion_source = "SOURCE_OR_PARTICIPATION_PRECEDENCE"
        elif person.underlying_id in policy_excluded:
            exclusion_source = "POLICY_EXCLUSION"
        excluded = exclusion_source is not None
        combined_max = 0 if excluded else declared_combined
        captain_max = 0 if excluded else min(declared_captain, combined_max)
        if not excluded and declared_captain > combined_max:
            findings.append(
                _issue(
                    "PORTFOLIO_POLICY_CAPTAIN_TIGHTENED_BY_COMBINED",
                    f"{person.underlying_id} Captain maximum {declared_captain} was tightened to combined maximum {combined_max}",
                    "no action is required unless the declared Captain control should be equally strict",
                )
            )
        if excluded and (declared_combined > 0 or declared_captain > 0):
            findings.append(
                _issue(
                    "PORTFOLIO_POLICY_EXCLUSION_TAKES_PRECEDENCE",
                    f"{person.underlying_id} effective combined and Captain maxima are zero because {exclusion_source} is stricter",
                    "remove only the explicit/source exclusion if this exact person should be eligible",
                )
            )
        effective_limits.append(
            EffectivePersonLimit(
                person=person,
                combined_fraction=combined_fraction,
                combined_source=combined_source,
                combined_max_entries=combined_max,
                captain_fraction=captain_fraction,
                captain_source=captain_source,
                declared_captain_max_entries=declared_captain,
                captain_max_entries=captain_max,
                excluded=excluded,
                exclusion_source=exclusion_source,
            )
        )
    policy = NormalizedPortfolioPolicy(
        salary_sha256=slate.salary_hash,
        game_id=slate.games[0].game_id,
        entry_ids=requested_entry_ids,
        people=expected_people_tuple,
        combined_rule=combined_rule,
        captain_rule=captain_rule,
        excluded_people=tuple(sorted(excluded_people)),
        max_pairwise_person_overlap=overlap_limit,
        require_unique_lineups=unique,
        effective_limits=tuple(effective_limits),
    )
    capacity = _necessary_capacity_issues(policy, slate)
    if capacity:
        problems.extend(capacity)
        return PortfolioPolicyValidation(
            source_sha256, policy, tuple(problems), tuple(findings)
        )
    return PortfolioPolicyValidation(source_sha256, policy, (), tuple(findings))


def validate_portfolio_policy_file(
    path: str | Path,
    *,
    slate: SlateContract,
    entry_ids: Sequence[str],
    externally_excluded_people: Sequence[str] = (),
    expected_sha256: str | None = None,
) -> PortfolioPolicyValidation:
    source = Path(path).resolve()
    raw = source.read_bytes()
    validation = validate_portfolio_policy_bytes(
        raw,
        slate=slate,
        entry_ids=entry_ids,
        externally_excluded_people=externally_excluded_people,
    )
    if expected_sha256 is not None and validation.source_sha256 != expected_sha256:
        issue = _issue(
            "PORTFOLIO_POLICY_INPUT_MUTATED",
            "the policy bytes changed after the immutable intake hash was recorded",
            "start a new run from one stable policy file and preserve the changed file separately",
        )
        return PortfolioPolicyValidation(
            validation.source_sha256,
            None,
            (issue, *validation.problems),
            validation.findings,
        )
    return validation


def canonical_showdown_lineup_identity(
    slate: SlateContract, roster_ids: Sequence[str]
) -> tuple[str, frozenset[str], str]:
    """Return (canonical key, person set, Captain person) for one legal lineup."""

    if slate.mode is not EngineMode.SHOWDOWN:
        raise ValueError("PORTFOLIO_LINEUP_MODE_UNSUPPORTED:SHOWDOWN_REQUIRED")
    validation = validate_lineup(slate, roster_ids)
    if not validation.valid:
        raise ValueError("PORTFOLIO_LINEUP_INVALID:" + ";".join(validation.errors))
    by_id = {row.dk_id: row for row in slate.players}
    captain = by_id[str(roster_ids[0]).strip()].underlying_id
    flex = sorted(by_id[str(dk_id).strip()].underlying_id for dk_id in roster_ids[1:])
    key = canonical_decimal_json_bytes({"captain": captain, "flex": flex}).decode("utf-8")
    return key, frozenset((captain, *flex)), captain


def summarize_showdown_portfolio(
    slate: SlateContract, assignments: Mapping[str, Sequence[str]]
) -> PortfolioSemantics:
    """Compute SD3 semantics only; this does not assert or enforce a policy."""

    if not assignments:
        raise ValueError("PORTFOLIO_ASSIGNMENTS_EMPTY")
    entries = tuple(sorted((str(entry).strip() for entry in assignments), key=str))
    if any(not entry for entry in entries):
        raise ValueError("PORTFOLIO_ENTRY_ID_BLANK")
    canonical: list[tuple[str, str]] = []
    people_by_entry: dict[str, frozenset[str]] = {}
    combined: Counter[str] = Counter()
    captains: Counter[str] = Counter()
    for entry in entries:
        key, people, captain = canonical_showdown_lineup_identity(slate, assignments[entry])
        canonical.append((entry, key))
        people_by_entry[entry] = people
        combined.update(people)
        captains[captain] += 1
    key_counts = Counter(key for _entry, key in canonical)
    duplicates = tuple(sorted(key for key, count in key_counts.items() if count > 1))
    overlaps: list[tuple[str, str, int]] = []
    for left_index, left in enumerate(entries):
        for right in entries[left_index + 1 :]:
            overlaps.append((left, right, len(people_by_entry[left] & people_by_entry[right])))
    return PortfolioSemantics(
        entry_ids=entries,
        canonical_lineups=tuple(canonical),
        combined_person_counts=tuple(sorted(combined.items())),
        captain_counts=tuple(sorted(captains.items())),
        duplicate_canonical_lineups=duplicates,
        pairwise_person_overlap=tuple(overlaps),
    )
