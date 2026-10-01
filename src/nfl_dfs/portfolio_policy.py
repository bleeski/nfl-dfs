"""Versioned Showdown portfolio controls and deterministic normalization.

SD3 owns this contract. SD4 consumes its exact integer maxima and canonical
bytes in a separate bounded selector and independent final-assignment audit.

v3 (Session 23b, chunk P8) adds `controls.theses`: one named game thesis every
bound lineup follows (`showdown_theses.py`). Without a thesis the normalized
bytes are exactly v2's; with one they are `normalized_v3`.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from dataclasses import dataclass, replace
from decimal import Decimal, ROUND_FLOOR
from pathlib import Path
from typing import Mapping, Sequence

from .contracts import EngineMode, SlateContract
from .entry_groups import subset_binding_problems
from .hashing import sha256_bytes
from .lineups import validate_lineup
from .showdown_theses import (
    DROPPED,
    POSITIONS,
    ROSTER_PEOPLE,
    THESIS_FIELDS,
    CountBound,
    ShowdownThesis,
)


POLICY_SCHEMA_VERSION = "nfl_showdown_portfolio_policy_v1"
POLICY_SCHEMA_VERSION_V2 = "nfl_showdown_portfolio_policy_v2"
POLICY_SCHEMA_VERSION_V3 = "nfl_showdown_portfolio_policy_v3"
SUPPORTED_POLICY_SCHEMA_VERSIONS = (POLICY_SCHEMA_VERSION, POLICY_SCHEMA_VERSION_V2, POLICY_SCHEMA_VERSION_V3)
NORMALIZED_POLICY_SCHEMA_VERSION = "nfl_showdown_portfolio_policy_normalized_v2"
NORMALIZED_POLICY_SCHEMA_VERSION_V3 = "nfl_showdown_portfolio_policy_normalized_v3"
NORMALIZED_POLICY_SCHEMA_VERSIONS = (NORMALIZED_POLICY_SCHEMA_VERSION, NORMALIZED_POLICY_SCHEMA_VERSION_V3)
FRACTION_UNIT = "FRACTION_0_TO_1"
# Session 23 (P2): per-lineup structural hygiene bounds, v2-only. Absent on a
# v1 policy, which normalizes with every bound fully open (identical to v1
# behaviour). `qb_count`/`pass_catchers_with_rostered_qb`/`salary_left` are
# inclusive [minimum, maximum] integer ranges; `kicker_count`/`dst_count` are
# maxima only; `offense_against_own_dst` is a hard Boolean. None means no
# bound on that side. Recomputed independently by the audit from roster IDs,
# never trusted from the generator's own claims.
STRUCTURAL_BOUND_FIELDS = (
    "qb_count",
    "pass_catchers_with_rostered_qb",
    "salary_left",
    "kicker_count",
    "dst_count",
    "offense_against_own_dst",
)


@dataclass(frozen=True)
class StructuralBoundRange:
    minimum: int | None
    maximum: int | None

    def as_mapping(self) -> dict[str, object]:
        return {"minimum": self.minimum, "maximum": self.maximum}

    def satisfied_by(self, value: int) -> bool:
        if self.minimum is not None and value < self.minimum:
            return False
        if self.maximum is not None and value > self.maximum:
            return False
        return True


OPEN_RANGE = StructuralBoundRange(None, None)


@dataclass(frozen=True)
class StructuralBounds:
    qb_count: StructuralBoundRange = OPEN_RANGE
    pass_catchers_with_rostered_qb: StructuralBoundRange = OPEN_RANGE
    salary_left: StructuralBoundRange = OPEN_RANGE
    kicker_count_maximum: int | None = None
    dst_count_maximum: int | None = None
    offense_against_own_dst: bool = False

    def as_mapping(self) -> dict[str, object]:
        return {
            "qb_count": self.qb_count.as_mapping(),
            "pass_catchers_with_rostered_qb": self.pass_catchers_with_rostered_qb.as_mapping(),
            "salary_left": self.salary_left.as_mapping(),
            "kicker_count": self.kicker_count_maximum,
            "dst_count": self.dst_count_maximum,
            "offense_against_own_dst": self.offense_against_own_dst,
        }


OPEN_STRUCTURAL_BOUNDS = StructuralBounds()


def structural_bound_violations(
    slate: SlateContract, roster_ids: Sequence[str], bounds: StructuralBounds
) -> tuple[str, ...]:
    """Which of `bounds` a legal Showdown roster violates, recomputed from `slate.players`.

    `pass_catchers_with_rostered_qb` is per rostered QB: the count of WR/TE on
    his team. With zero QBs rostered it is vacuously satisfied.
    `offense_against_own_dst` forbids any non-DST person, any position, sharing
    a rostered DST's team (so it also covers a DST on the rostered QB's team).
    """

    by_id = {row.dk_id: row for row in slate.players}
    rows = [by_id[str(dk_id).strip()] for dk_id in roster_ids]
    violations: list[str] = []
    qb_rows = [row for row in rows if row.position == "QB"]
    if not bounds.qb_count.satisfied_by(len(qb_rows)):
        violations.append("qb_count")
    if qb_rows:
        counts = [
            sum(1 for row in rows if row.team == qb.team and row.position in {"WR", "TE"})
            for qb in qb_rows
        ]
        if any(not bounds.pass_catchers_with_rostered_qb.satisfied_by(count) for count in counts):
            violations.append("pass_catchers_with_rostered_qb")
    salary_left = slate.salary_cap - sum(row.salary for row in rows)
    if not bounds.salary_left.satisfied_by(salary_left):
        violations.append("salary_left")
    kicker_count = sum(1 for row in rows if row.position == "K")
    if bounds.kicker_count_maximum is not None and kicker_count > bounds.kicker_count_maximum:
        violations.append("kicker_count")
    dst_count = sum(1 for row in rows if row.position == "DST")
    if bounds.dst_count_maximum is not None and dst_count > bounds.dst_count_maximum:
        violations.append("dst_count")
    if bounds.offense_against_own_dst:
        dst_teams = {row.team for row in rows if row.position == "DST"}
        if any(row.team in dst_teams and row.position != "DST" for row in rows):
            violations.append("offense_against_own_dst")
    return tuple(violations)


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
    structural_bounds: StructuralBounds = OPEN_STRUCTURAL_BOUNDS
    # Session 23b: the declared theses, each ACTIVE or DROPPED (v3 only; empty otherwise).
    theses: tuple[ShowdownThesis, ...] = ()

    @property
    def entry_count(self) -> int:
        return len(self.entry_ids)

    @property
    def active_thesis(self) -> ShowdownThesis | None:
        return next((thesis for thesis in self.theses if thesis.active), None)

    @property
    def effective_pairwise_person_overlap(self) -> int:
        return 6 if self.max_pairwise_person_overlap is None else self.max_pairwise_person_overlap

    def as_mapping(self) -> dict[str, object]:
        return {
            "schema_version": (NORMALIZED_POLICY_SCHEMA_VERSION_V3 if self.theses
                               else NORMALIZED_POLICY_SCHEMA_VERSION),
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
                "structural_bounds": self.structural_bounds.as_mapping(),
                **({"theses": [thesis.as_mapping() for thesis in self.theses]} if self.theses else {}),
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
            # Accepted source schema versions: SUPPORTED_POLICY_SCHEMA_VERSIONS.
            # This field names the contract family, not the exact supplied
            # version; the normalized policy and its own schema_version carry
            # the authoritative post-validation shape.
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
    schema_version: str = POLICY_SCHEMA_VERSION,
) -> dict[str, object]:
    """Build exact bindings for an operator-authored controls object.

    `schema_version=POLICY_SCHEMA_VERSION_V2` and a `structural_bounds` key in
    `controls` together author a v2 policy (Session 23); v1 stays the default
    and never carries `structural_bounds`.
    """

    if len(slate.games) != 1:
        raise ValueError("PORTFOLIO_POLICY_GAME_BINDING_INVALID: exactly one game is required")
    return {
        "schema_version": schema_version,
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


def _structural_bound_integer(
    value: object, location: str, problems: list[PolicyIssue], *, maximum: int
) -> int | None:
    """A nullable non-negative integer bound; `None` (omitted or null) is no bound."""

    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        problems.append(
            _issue(
                "PORTFOLIO_POLICY_STRUCTURAL_BOUND_INTEGER_REQUIRED",
                f"{location} must be a JSON integer or null",
                "supply a non-negative integer, or omit/null for no bound on this side",
            )
        )
        return None
    if value < 0 or value > maximum:
        problems.append(
            _issue(
                "PORTFOLIO_POLICY_STRUCTURAL_BOUND_OUT_OF_RANGE",
                f"{location}={value} is outside [0,{maximum}]",
                "supply an integer inside the declared domain",
            )
        )
        return None
    return value


def _structural_bound_range(
    value: object, location: str, problems: list[PolicyIssue], *, maximum: int
) -> StructuralBoundRange | None:
    if value is None:
        return OPEN_RANGE
    item = _mapping(value, location, problems)
    if item is None:
        return None
    _unknown_fields(item, {"minimum", "maximum"}, location, problems)
    minimum_bound = _structural_bound_integer(item.get("minimum"), f"{location}.minimum", problems, maximum=maximum)
    maximum_bound = _structural_bound_integer(item.get("maximum"), f"{location}.maximum", problems, maximum=maximum)
    if minimum_bound is not None and maximum_bound is not None and minimum_bound > maximum_bound:
        problems.append(
            _issue(
                "PORTFOLIO_POLICY_STRUCTURAL_BOUND_CONTRADICTORY",
                f"{location} minimum exceeds maximum",
                "make the inclusive integer bounds ordered",
            )
        )
    return StructuralBoundRange(minimum_bound, maximum_bound)


def _structural_bounds(
    value: object, *, location: str, problems: list[PolicyIssue]
) -> StructuralBounds | None:
    """Parse `controls.structural_bounds` (Session 23, v2-only); omitted is fully open."""

    if value is None:
        return OPEN_STRUCTURAL_BOUNDS
    item = _mapping(value, location, problems)
    if item is None:
        return None
    _unknown_fields(item, set(STRUCTURAL_BOUND_FIELDS), location, problems)
    qb_count = _structural_bound_range(item.get("qb_count"), f"{location}.qb_count", problems, maximum=6)
    pass_catchers = _structural_bound_range(
        item.get("pass_catchers_with_rostered_qb"),
        f"{location}.pass_catchers_with_rostered_qb",
        problems,
        maximum=5,
    )
    salary_left = _structural_bound_range(
        item.get("salary_left"), f"{location}.salary_left", problems, maximum=50_000
    )
    kicker_count = _structural_bound_integer(
        item.get("kicker_count"), f"{location}.kicker_count", problems, maximum=6
    )
    dst_count = _structural_bound_integer(
        item.get("dst_count"), f"{location}.dst_count", problems, maximum=6
    )
    offense_raw = item.get("offense_against_own_dst", False)
    if not isinstance(offense_raw, bool):
        problems.append(
            _issue(
                "PORTFOLIO_POLICY_STRUCTURAL_BOUND_TYPE_INVALID",
                f"{location}.offense_against_own_dst must be Boolean",
                "set true or false",
            )
        )
        offense_against_own_dst = False
    else:
        offense_against_own_dst = offense_raw
    if qb_count is None or pass_catchers is None or salary_left is None:
        return None
    return StructuralBounds(
        qb_count, pass_catchers, salary_left, kicker_count, dst_count, offense_against_own_dst
    )


def _thesis_issue(location: str, message: str) -> PolicyIssue:
    return _issue(
        "PORTFOLIO_POLICY_THESIS_INVALID",
        f"{location} {message}",
        "repair the thesis to the documented nfl_showdown_portfolio_policy_v3 shape; a thesis is never loosened",
    )


def _thesis_count_bounds(
    value: object, *, location: str, label: str, allowed: Sequence[str], problems: list[PolicyIssue]
) -> tuple[CountBound, ...] | None:
    if value is None:
        return ()
    if not isinstance(value, list):
        problems.append(_thesis_issue(location, "must be a JSON array"))
        return None
    bounds: list[CountBound] = []
    for index, raw in enumerate(value):
        where = f"{location}[{index}]"
        item = _mapping(raw, where, problems)
        if item is None:
            return None
        _unknown_fields(item, {label, "minimum", "maximum"}, where, problems)
        key = item.get(label)
        if not isinstance(key, str) or key not in allowed:
            problems.append(_thesis_issue(f"{where}.{label}", f"must be one of {list(allowed)}"))
            return None
        numbers = []
        for side, default in (("minimum", 0), ("maximum", ROSTER_PEOPLE)):
            number = item.get(side, default)
            if isinstance(number, bool) or not isinstance(number, int) or not 0 <= number <= ROSTER_PEOPLE:
                problems.append(_thesis_issue(f"{where}.{side}", f"must be an integer from 0 through {ROSTER_PEOPLE}"))
                return None
            numbers.append(number)
        if numbers[0] > numbers[1]:
            problems.append(_thesis_issue(where, "minimum exceeds maximum"))
            return None
        bounds.append(CountBound(key, numbers[0], numbers[1]))
    keys = [bound.key for bound in bounds]
    if len(set(keys)) != len(keys):
        problems.append(_thesis_issue(location, f"repeats a {label}"))
        return None
    if sum(bound.minimum for bound in bounds) > ROSTER_PEOPLE:
        problems.append(_thesis_issue(location, f"minima total more than the {ROSTER_PEOPLE} people of a lineup"))
        return None
    return tuple(sorted(bounds, key=lambda bound: bound.key))


def _theses(
    value: object,
    *,
    slate: SlateContract,
    expected: Mapping[str, PersonBinding],
    dk_roles: Mapping[str, tuple[str, str]],
    problems: list[PolicyIssue],
) -> tuple[ShowdownThesis, ...] | None:
    """Parse `controls.theses` (v3, Session 23b): exactly one thesis until Session 23c."""

    location = "controls.theses"
    if not isinstance(value, list) or len(value) != 1:
        problems.append(_thesis_issue(
            location, "must be a JSON array holding exactly one thesis (a portfolio of theses is Session 23c)"))
        return None
    teams_on_slate = sorted({row.team for row in slate.players})
    positions = {row.underlying_id: row.position for row in slate.players}
    theses: list[ShowdownThesis] = []
    for index, raw in enumerate(value):
        where = f"{location}[{index}]"
        item = _mapping(raw, where, problems)
        if item is None:
            return None
        _unknown_fields(item, set(THESIS_FIELDS), where, problems)
        name = item.get("name")
        if not isinstance(name, str) or not name.strip() or len(name) > 80 or not name.isprintable():
            problems.append(_thesis_issue(f"{where}.name", "must be a printable label of 1 to 80 characters"))
            return None
        teams = item.get("teams")
        if (not isinstance(teams, list) or not teams or any(team not in teams_on_slate for team in teams)
                or len(set(teams)) != len(teams)):
            problems.append(_thesis_issue(f"{where}.teams", f"must name one or both of {teams_on_slate}, once each"))
            return None
        people: dict[str, tuple[PersonBinding, ...]] = {}
        for field_name, required in (("captain_set", True), ("excluded_people", False),
                                     ("named_backup_quarterbacks", False)):
            found = _identity_list(item.get(field_name), location=f"{where}.{field_name}", required=required,
                                   problems=problems)
            if found is None:
                return None
            for position, reference in enumerate(found):
                if not _validate_identity_reference(reference, expected=expected, dk_roles=dk_roles,
                                                    location=f"{where}.{field_name}[{position}]", problems=problems):
                    return None
            people[field_name] = found
        if not people["captain_set"]:
            problems.append(_thesis_issue(f"{where}.captain_set", "must name at least one Captain"))
            return None
        excluded = {person.underlying_id for person in people["excluded_people"]}
        clash = sorted(excluded & {person.underlying_id for person in
                                   (*people["captain_set"], *people["named_backup_quarterbacks"])})
        if clash:
            problems.append(_thesis_issue(where, f"both requires and excludes {clash}"))
            return None
        not_quarterbacks = sorted(person.underlying_id for person in people["named_backup_quarterbacks"]
                                  if positions.get(person.underlying_id) != "QB")
        if not_quarterbacks:
            problems.append(_thesis_issue(f"{where}.named_backup_quarterbacks", f"names non-quarterbacks {not_quarterbacks}"))
            return None
        team_bounds = _thesis_count_bounds(item.get("team_bounds"), location=f"{where}.team_bounds", label="team",
                                           allowed=teams_on_slate, problems=problems)
        position_bounds = _thesis_count_bounds(item.get("position_bounds"), location=f"{where}.position_bounds",
                                               label="position", allowed=POSITIONS, problems=problems)
        if team_bounds is None or position_bounds is None:
            return None
        theses.append(ShowdownThesis(
            name=name, teams=tuple(teams), captain_set=people["captain_set"], team_bounds=team_bounds,
            position_bounds=position_bounds, excluded_people=people["excluded_people"],
            named_backup_quarterbacks=people["named_backup_quarterbacks"]))
    return tuple(theses)


def _resolved_thesis(
    thesis: ShowdownThesis, slate: SlateContract, limits: Sequence[EffectivePersonLimit]
) -> ShowdownThesis:
    """`thesis`, or the same thesis DROPPED when no lineup could follow it.

    Dropped when every Captain it requires is unavailable (an exclusion from the
    run, the policy's own, or a combined cap of zero), or when fewer people are
    available than a team or position minimum asks for. Never loosened: the
    exclusions decide, and the thesis is named rather than bent.
    """

    by_person = {limit.person.underlying_id: limit for limit in limits}
    available = {person for person, limit in by_person.items()
                 if limit.combined_max_entries > 0 and person not in thesis.excluded_ids}
    unavailable = tuple(sorted(
        (person, by_person[person].exclusion_source or "COMBINED_CAP_ZERO")
        for person in thesis.captain_people if person not in available))
    reasons: list[str] = []
    if len(unavailable) == len(thesis.captain_set):
        reasons.append("every required Captain is unavailable: "
                       + ", ".join(f"{person} ({source})" for person, source in unavailable))
    rows = {row.underlying_id: row for row in slate.players}
    for label, bounds, attribute in (("team", thesis.team_bounds, "team"),
                                     ("position", thesis.position_bounds, "position")):
        for bound in bounds:
            count = sum(1 for person in available if getattr(rows[person], attribute) == bound.key)
            if count < bound.minimum:
                reasons.append(f"{label} {bound.key} needs {bound.minimum} and {count} are available")
    if not reasons:
        return thesis
    return replace(thesis, status=DROPPED, dropped_reason="; ".join(reasons), unavailable_captains=unavailable)


def _thesis_widened_bounds(
    bounds: StructuralBounds, thesis: ShowdownThesis
) -> tuple[StructuralBounds, list[str]]:
    """`bounds` widened just enough for the thesis's QB, K and DST counts, and what moved.

    The thesis is Ben's more specific statement for its own rows, so a policy count
    bound that forbids what it asks for gives way, by the least step, rather than
    sending the run down rungs that loosen unrelated bounds first.
    """

    needs = {bound.key: bound for bound in thesis.position_bounds}
    moved: list[str] = []
    qb_count = bounds.qb_count
    if "QB" in needs:
        low, high = qb_count.minimum, qb_count.maximum
        new_low = low if low is None or needs["QB"].maximum >= low else needs["QB"].maximum
        new_high = high if high is None or needs["QB"].minimum <= high else needs["QB"].minimum
        if (new_low, new_high) != (low, high):
            moved.append(f"qb_count {low}..{high} to {new_low}..{new_high}")
            qb_count = StructuralBoundRange(new_low, new_high)
    maxima = {"K": bounds.kicker_count_maximum, "DST": bounds.dst_count_maximum}
    for position, maximum in list(maxima.items()):
        if position in needs and maximum is not None and needs[position].minimum > maximum:
            maxima[position] = needs[position].minimum
            moved.append(f"{'kicker' if position == 'K' else 'dst'}_count {maximum} to {maxima[position]}")
    return replace(bounds, qb_count=qb_count, kicker_count_maximum=maxima["K"],
                   dst_count_maximum=maxima["DST"]), moved


def _thesis_capacity_issues(policy: NormalizedPortfolioPolicy) -> list[PolicyIssue]:
    """Captain caps that leave an active thesis's Captains too few rows: an `S` issue.

    The ladder loosens the caps (rungs 1 to 3), never the thesis.
    """

    thesis = policy.active_thesis
    if thesis is None:
        return []
    room = sum(limit.captain_max_entries for limit in policy.effective_limits
               if limit.person.underlying_id in thesis.captain_people)
    if room >= policy.entry_count:
        return []
    return [_issue(
        "PORTFOLIO_POLICY_THESIS_CAPACITY_INSUFFICIENT",
        f"thesis {thesis.name!r}: its Captains may captain {room} of {policy.entry_count} entries under the Captain caps",
        "raise the Captain caps on the thesis's Captains; the thesis itself is never loosened",
    )]


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
                    "raise caps or permit more people; distinct lineups are never relaxed (R29)",
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
    declared_schema_version = root.get("schema_version")
    is_v3 = declared_schema_version == POLICY_SCHEMA_VERSION_V3
    # v3 carries every v2 control; "v2" below reads "v2 or later".
    is_v2 = declared_schema_version == POLICY_SCHEMA_VERSION_V2 or is_v3
    if declared_schema_version not in SUPPORTED_POLICY_SCHEMA_VERSIONS:
        problems.append(
            _issue(
                "PORTFOLIO_POLICY_SCHEMA_UNSUPPORTED",
                f"schema_version must be one of {list(SUPPORTED_POLICY_SCHEMA_VERSIONS)!r}",
                "regenerate the policy with a current versioned contract",
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
    structural_bounds: StructuralBounds | None = OPEN_STRUCTURAL_BOUNDS
    theses: tuple[ShowdownThesis, ...] | None = ()
    allowed_control_fields = {
        "fraction_unit",
        "max_combined_person_exposure",
        "max_captain_exposure",
        "excluded_people",
        "max_pairwise_person_overlap",
        "require_unique_lineups",
    }
    if is_v2:
        allowed_control_fields = allowed_control_fields | {"structural_bounds"}
    if is_v3:
        allowed_control_fields = allowed_control_fields | {"theses"}
    if controls is not None:
        _unknown_fields(controls, allowed_control_fields, "controls", problems)
        if is_v3:
            theses = _theses(controls.get("theses"), slate=slate, expected=expected_people,
                             dk_roles=dk_roles, problems=problems)
        elif "theses" in controls:
            problems.append(_thesis_issue(
                "controls.theses", f"requires schema_version {POLICY_SCHEMA_VERSION_V3!r}"))
        if is_v2:
            structural_bounds = _structural_bounds(
                controls.get("structural_bounds"),
                location="controls.structural_bounds",
                problems=problems,
            )
        elif "structural_bounds" in controls:
            problems.append(
                _issue(
                    "PORTFOLIO_POLICY_STRUCTURAL_BOUND_TYPE_INVALID",
                    f"controls.structural_bounds requires schema_version {POLICY_SCHEMA_VERSION_V2!r}",
                    "regenerate the policy as v2, or drop structural_bounds",
                )
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
            if not unique:
                # R29: every lineup in a portfolio is distinct. Classic refuses
                # the same flag (`CLASSIC_POLICY_UNIQUENESS_REQUIRED`).
                problems.append(
                    _issue(
                        "PORTFOLIO_POLICY_UNIQUENESS_REQUIRED",
                        "require_unique_lineups must be true: every lineup in a portfolio is distinct (R29)",
                        "set require_unique_lineups to true or omit it",
                    )
                )

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
    if (
        problems
        or combined_rule is None
        or captain_rule is None
        or excluded_people is None
        or structural_bounds is None
        or theses is None
    ):
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
    # Session 23b: a thesis no lineup could follow is dropped and named, never loosened;
    # a policy count bound that contradicts an active thesis gives way to the thesis.
    theses = tuple(_resolved_thesis(thesis, slate, effective_limits) for thesis in theses)
    for thesis in theses:
        if thesis.status == DROPPED:
            findings.append(_issue(
                "THESIS_DROPPED",
                f"thesis {thesis.name!r} cannot be built and is dropped, not loosened: {thesis.dropped_reason}",
                "the bound rows are built without it and name no thesis; restore a required person or revise the thesis",
            ))
        else:
            structural_bounds, widened = _thesis_widened_bounds(structural_bounds, thesis)
            if widened:
                findings.append(_issue(
                    "PORTFOLIO_POLICY_THESIS_OVERRIDES_BOUND",
                    f"thesis {thesis.name!r} asks for counts the policy's bounds forbid: " + "; ".join(widened),
                    "no action is required unless the policy bound should win, in which case revise the thesis",
                ))
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
        structural_bounds=structural_bounds,
        theses=theses,
    )
    capacity = (*_necessary_capacity_issues(policy, slate), *_thesis_capacity_issues(policy))
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
