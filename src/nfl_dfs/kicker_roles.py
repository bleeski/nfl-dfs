"""Versioned, source-bound current kicker-role allocation.

The team projection owns one kicking event line.  This module decides which
current-slate people may receive that line; it never creates team volume and it
never treats historical offensive snap share as current role evidence.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Sequence

from pydantic import Field, field_validator, model_validator

from .contracts import FrozenModel, SlateContract
from .hashing import sha256_file
from .participation import ParticipationContract
from .sources import SourcePolicyError, validate_source_reference_policy


KICKER_ROLE_EVIDENCE_VERSION = "nfl_kicker_role_evidence_v1"
KICKER_ROLE_ALLOCATION_VERSION = "kicker_team_scoring_event_allocation_v1"
KICKER_ROLE_SHARE_TOLERANCE = 1e-6

_SOLE_CUES = (
    "sole kicker",
    "only kicker",
    "starting kicker",
    "placekicker",
)


class KickerRoleError(ValueError):
    """A named fail-closed current-role error."""


class KickerRoleSource(FrozenModel):
    """One immutable supporting capture referenced by the role declaration."""

    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_uri: str = Field(min_length=1)
    observed_at: datetime
    captured_at: datetime
    expires_at: datetime
    license_decision: Literal[
        "PUBLIC_DOMAIN",
        "PERMITTED_PUBLIC_API",
        "PERMITTED_REPOSITORY_LICENSE",
    ]
    parser_version: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
    transformation_version: str = Field(
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$"
    )
    support_kind: Literal["QUALITATIVE_SOLE", "NUMERICAL_SPLIT"]
    supporting_excerpt: str = Field(min_length=1, max_length=4000)
    synthetic: bool = False

    @field_validator("synthetic", mode="before")
    @classmethod
    def strict_synthetic_label(cls, value: object) -> bool:
        if not isinstance(value, bool):
            raise ValueError("synthetic must be a JSON Boolean")
        return value

    @field_validator("observed_at", "captured_at", "expires_at")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("kicker-role source timestamps must be timezone-aware")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def ordered_window(self) -> "KickerRoleSource":
        if self.captured_at < self.observed_at:
            raise ValueError("kicker-role source was captured before it was observed")
        if self.expires_at < self.captured_at:
            raise ValueError("kicker-role source expires before capture")
        return self


class KickerRoleRecipient(FrozenModel):
    underlying_id: str = Field(min_length=1)
    cpt_dk_id: str = Field(min_length=1)
    flex_dk_id: str = Field(min_length=1)
    share: float

    @field_validator("share", mode="before")
    @classmethod
    def finite_nonnegative_share(cls, value: object) -> float:
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value < 0
        ):
            raise ValueError("kicker share must be finite and nonnegative")
        return float(value)


class KickerTeamDeclaration(FrozenModel):
    game_id: str = Field(min_length=1)
    team: str = Field(min_length=1)
    allocation_kind: Literal["SOLE", "SPLIT"]
    recipients: tuple[KickerRoleRecipient, ...] = Field(min_length=1)
    source_sha256s: tuple[str, ...] = Field(min_length=1)

    @field_validator("source_sha256s")
    @classmethod
    def source_hashes_are_sha256(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(re.fullmatch(r"[0-9a-f]{64}", value) is None for value in values):
            raise ValueError("source_sha256s must contain lowercase SHA-256 values")
        return values


class KickerRoleEvidence(FrozenModel):
    schema_version: Literal["nfl_kicker_role_evidence_v1"]
    allocation_version: Literal["kicker_team_scoring_event_allocation_v1"]
    salary_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    game_id: str = Field(min_length=1)
    share_tolerance: float
    sources: tuple[KickerRoleSource, ...] = Field(min_length=1)
    declarations: tuple[KickerTeamDeclaration, ...]

    @field_validator("share_tolerance", mode="before")
    @classmethod
    def registered_tolerance(cls, value: object) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("kicker role share_tolerance must be a JSON number")
        if value != KICKER_ROLE_SHARE_TOLERANCE:
            raise ValueError(
                "kicker role share_tolerance must equal the registered 0.000001"
            )
        return float(value)


@dataclass(frozen=True)
class KickerRoleResolution:
    allocation_version: str
    shares_by_person: dict[str, float]
    zero_share_people: tuple[str, ...]
    assumptions: tuple[str, ...]
    coverage_gaps: tuple[str, ...]
    team_allocations: dict[str, dict[str, float]]
    evidence_path: str | None = None
    evidence_sha256: str | None = None
    source_paths: tuple[str, ...] = ()
    source_hashes: dict[str, str] | None = None
    observed_at: str | None = None
    expires_at: str | None = None
    synthetic_sources: tuple[str, ...] = ()

    def as_report(self) -> dict[str, object]:
        supplied = self.evidence_path is not None
        return {
            "schema_version": KICKER_ROLE_EVIDENCE_VERSION if supplied else None,
            "allocation_version": self.allocation_version,
            "allocation_basis": (
                "SOURCE_BOUND_CURRENT_ROLE_EVIDENCE"
                if supplied
                else "PRIOR_ONLY_SOLE_LISTED_ASSUMPTION"
            ),
            "evidence_state": "PASS" if supplied else "UNKNOWN",
            "does_not_establish": [
                "OFFICIAL_ACTIVE_STATUS",
                "MODEL_VALIDATION",
            ],
            "team_allocations": {
                team: dict(sorted(values.items()))
                for team, values in sorted(self.team_allocations.items())
            },
            "zero_share_people": list(self.zero_share_people),
            "assumptions": list(self.assumptions),
            "coverage_gaps": list(self.coverage_gaps),
            "evidence_path": self.evidence_path,
            "evidence_sha256": self.evidence_sha256,
            "source_hashes": dict(sorted((self.source_hashes or {}).items())),
            "observed_at": self.observed_at,
            "expires_at": self.expires_at,
            "synthetic_sources": list(self.synthetic_sources),
            "synthetic_note": (
                "TEST_ONLY_SYNTHETIC_EVIDENCE"
                if self.synthetic_sources
                else None
            ),
        }


def _salary_kickers(slate: SlateContract) -> dict[str, dict[str, object]]:
    grouped: dict[str, dict[str, object]] = {}
    for player in slate.players:
        if player.position != "K":
            continue
        bucket = grouped.setdefault(
            player.underlying_id,
            {
                "team": player.team,
                "game_id": player.game_id,
                "name": player.name,
                "roles": {},
            },
        )
        if bucket["team"] != player.team or bucket["game_id"] != player.game_id:
            raise KickerRoleError(
                f"KICKER_IDENTITY_CONFLICT:{player.underlying_id}:team_or_game"
            )
        roles = bucket["roles"]
        assert isinstance(roles, dict)
        if player.role in roles:
            raise KickerRoleError(
                f"KICKER_ROLE_ID_DUPLICATE:{player.underlying_id}:{player.role}"
            )
        roles[player.role] = player.dk_id
    for person, detail in grouped.items():
        roles = detail["roles"]
        if not isinstance(roles, dict) or set(roles) != {"CPT", "FLEX"}:
            raise KickerRoleError(
                f"KICKER_CPT_FLEX_IDENTITY_INCOMPLETE:{person}:{sorted(roles)}"
            )
    return grouped


def _relative_source_path(manifest_path: Path, value: str) -> Path:
    raw = Path(value)
    if raw.is_absolute() or ".." in raw.parts:
        raise KickerRoleError(f"KICKER_ROLE_SOURCE_PATH_ESCAPE:{value}")
    root = manifest_path.parent.resolve()
    resolved = (root / raw).resolve()
    if not resolved.is_relative_to(root):
        raise KickerRoleError(f"KICKER_ROLE_SOURCE_PATH_ESCAPE:{value}")
    if resolved.is_symlink() or not resolved.is_file():
        raise KickerRoleError(f"KICKER_ROLE_SOURCE_UNREADABLE:{value}")
    return resolved


def _validate_source(
    source: KickerRoleSource,
    *,
    manifest_path: Path,
    as_of: datetime,
) -> tuple[Path, str]:
    try:
        validate_source_reference_policy(
            source.source_uri,
            license_decision=source.license_decision,
            parser_version=source.parser_version,
        )
    except SourcePolicyError as exc:
        raise KickerRoleError(f"KICKER_ROLE_SOURCE_POLICY:{exc}") from exc
    if source.observed_at > as_of:
        raise KickerRoleError(
            f"KICKER_ROLE_SOURCE_FUTURE:observed_at={source.observed_at.isoformat()}"
        )
    if source.captured_at > as_of:
        raise KickerRoleError(
            f"KICKER_ROLE_CAPTURE_FUTURE:captured_at={source.captured_at.isoformat()}"
        )
    if as_of > source.expires_at:
        raise KickerRoleError(
            f"KICKER_ROLE_SOURCE_STALE:expires_at={source.expires_at.isoformat()}"
        )
    path = _relative_source_path(manifest_path, source.path)
    digest = sha256_file(path)
    if digest != source.sha256:
        raise KickerRoleError(
            f"KICKER_ROLE_SOURCE_HASH_MISMATCH:path={source.path}"
        )
    if not path.name.startswith(digest):
        raise KickerRoleError(
            f"KICKER_ROLE_SOURCE_NOT_CONTENT_ADDRESSED:path={source.path}"
        )
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise KickerRoleError(
            f"KICKER_ROLE_SOURCE_NOT_UTF8:path={source.path}"
        ) from exc
    if source.supporting_excerpt not in text:
        raise KickerRoleError(
            f"KICKER_ROLE_SUPPORT_NOT_IN_CAPTURE:path={source.path}"
        )
    if sha256_file(path) != digest:
        raise KickerRoleError(
            f"KICKER_ROLE_SOURCE_CHANGED_DURING_READ:path={source.path}"
        )
    return path, digest


def _validate_numerical_support(
    excerpt: str,
    *,
    declaration: KickerTeamDeclaration,
) -> None:
    try:
        payload = json.loads(excerpt)
    except (TypeError, json.JSONDecodeError) as exc:
        raise KickerRoleError("KICKER_ROLE_NUMERICAL_SUPPORT_NOT_JSON") from exc
    if not isinstance(payload, dict) or set(payload) != {
        "allocations",
        "game_id",
        "team",
    }:
        raise KickerRoleError("KICKER_ROLE_NUMERICAL_SUPPORT_SCHEMA_INVALID")
    if payload["game_id"] != declaration.game_id or payload["team"] != declaration.team:
        raise KickerRoleError("KICKER_ROLE_NUMERICAL_SUPPORT_SCOPE_MISMATCH")
    expected = sorted(
        (
            recipient.underlying_id,
            recipient.cpt_dk_id,
            recipient.flex_dk_id,
            recipient.share,
        )
        for recipient in declaration.recipients
    )
    allocations = payload["allocations"]
    if not isinstance(allocations, list):
        raise KickerRoleError("KICKER_ROLE_NUMERICAL_SUPPORT_SCHEMA_INVALID")
    observed: list[tuple[str, str, str, float]] = []
    for allocation in allocations:
        if not isinstance(allocation, dict) or set(allocation) != {
            "cpt_dk_id",
            "flex_dk_id",
            "share",
            "underlying_id",
        }:
            raise KickerRoleError("KICKER_ROLE_NUMERICAL_SUPPORT_SCHEMA_INVALID")
        share = allocation["share"]
        if isinstance(share, bool) or not isinstance(share, (int, float)):
            raise KickerRoleError("KICKER_ROLE_NUMERICAL_SUPPORT_SCHEMA_INVALID")
        observed.append(
            (
                str(allocation["underlying_id"]),
                str(allocation["cpt_dk_id"]),
                str(allocation["flex_dk_id"]),
                float(share),
            )
        )
    if len(observed) != len(expected):
        raise KickerRoleError("KICKER_ROLE_NUMERICAL_SUPPORT_ALLOCATION_MISMATCH")
    for actual, wanted in zip(sorted(observed), expected):
        if actual[:3] != wanted[:3] or not math.isclose(
            actual[3], wanted[3], rel_tol=0, abs_tol=KICKER_ROLE_SHARE_TOLERANCE
        ):
            raise KickerRoleError("KICKER_ROLE_NUMERICAL_SUPPORT_ALLOCATION_MISMATCH")


def _implicit_resolution(
    slate: SlateContract,
    contract: ParticipationContract,
) -> KickerRoleResolution:
    kickers = _salary_kickers(slate)
    selectable = set(contract.selectable_people)
    by_team: dict[str, list[str]] = {}
    for person, detail in kickers.items():
        if person in selectable:
            by_team.setdefault(str(detail["team"]), []).append(person)

    shares: dict[str, float] = {person: 0.0 for person in kickers}
    assumptions: list[str] = []
    gaps: list[str] = []
    allocations: dict[str, dict[str, float]] = {}
    teams = sorted({player.team for player in slate.players})
    for team in teams:
        eligible = sorted(by_team.get(team, ()))
        if len(eligible) > 1:
            raise KickerRoleError(
                f"KICKER_ROLE_UNRESOLVED:team={team}:eligible={eligible}"
                ":capture approved current-role evidence and add role_evidence_json"
                " to the generated request; do not choose by salary or snap share"
            )
        if not eligible:
            gaps.append(
                f"NO_ELIGIBLE_KICKER:team={team}:no team kicking production allocated;"
                " K-free lineups may proceed diagnostically"
            )
            allocations[team] = {}
            continue
        person = eligible[0]
        shares[person] = 1.0
        allocations[team] = {person: 1.0}
        assumptions.append(
            f"SOLE_LISTED_KICKER_ASSUMPTION:team={team}:person={person}:"
            "not confirmed current role or official ACTIVE status"
        )
    return KickerRoleResolution(
        allocation_version=KICKER_ROLE_ALLOCATION_VERSION,
        shares_by_person=shares,
        zero_share_people=tuple(sorted(person for person, share in shares.items() if share == 0)),
        assumptions=tuple(assumptions),
        coverage_gaps=tuple(gaps),
        team_allocations=allocations,
    )


def resolve_kicker_roles(
    slate: SlateContract,
    contract: ParticipationContract,
    *,
    evidence_path: str | Path | None = None,
    as_of: datetime | None = None,
) -> KickerRoleResolution:
    """Resolve one conserved team allocation after all selection exclusions."""

    when = (as_of or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if evidence_path in (None, ""):
        return _implicit_resolution(slate, contract)

    manifest_path = Path(evidence_path).resolve()
    manifest_digest = sha256_file(manifest_path)
    try:
        evidence = KickerRoleEvidence.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, ValueError) as exc:
        raise KickerRoleError(f"KICKER_ROLE_EVIDENCE_INVALID:{exc}") from exc
    if sha256_file(manifest_path) != manifest_digest:
        raise KickerRoleError("KICKER_ROLE_EVIDENCE_CHANGED_DURING_READ")
    if evidence.salary_sha256 != slate.salary_hash:
        raise KickerRoleError("KICKER_ROLE_SALARY_HASH_MISMATCH")
    game_ids = {game.game_id for game in slate.games}
    if game_ids != {evidence.game_id}:
        raise KickerRoleError("KICKER_ROLE_GAME_MISMATCH")

    sources: dict[str, tuple[KickerRoleSource, Path]] = {}
    source_paths: list[str] = []
    source_hashes: dict[str, str] = {}
    for source in evidence.sources:
        if source.sha256 in sources:
            raise KickerRoleError(f"KICKER_ROLE_SOURCE_DUPLICATE:{source.sha256}")
        path, digest = _validate_source(source, manifest_path=manifest_path, as_of=when)
        sources[source.sha256] = (source, path)
        source_paths.append(str(path))
        source_hashes[str(path)] = digest

    kickers = _salary_kickers(slate)
    selectable = set(contract.selectable_people)
    eligible_by_team: dict[str, set[str]] = {}
    for person, detail in kickers.items():
        if person in selectable:
            eligible_by_team.setdefault(str(detail["team"]), set()).add(person)

    declarations: dict[str, KickerTeamDeclaration] = {}
    bound_people: set[str] = set()
    for declaration in evidence.declarations:
        team = declaration.team.strip().upper()
        if team in declarations:
            raise KickerRoleError(f"KICKER_ROLE_TEAM_DECLARATION_DUPLICATE:{team}")
        if declaration.game_id != evidence.game_id:
            raise KickerRoleError(f"KICKER_ROLE_DECLARATION_GAME_MISMATCH:{team}")
        if team not in {player.team for player in slate.players}:
            raise KickerRoleError(f"KICKER_ROLE_UNKNOWN_TEAM:{team}")
        declarations[team] = declaration
        referenced = set(declaration.source_sha256s)
        if len(referenced) != len(declaration.source_sha256s):
            raise KickerRoleError(f"KICKER_ROLE_SOURCE_REFERENCE_DUPLICATE:{team}")
        if not referenced or not referenced.issubset(sources):
            raise KickerRoleError(f"KICKER_ROLE_SOURCE_REFERENCE_UNKNOWN:{team}")

        people: set[str] = set()
        for recipient in declaration.recipients:
            if recipient.underlying_id in people or recipient.underlying_id in bound_people:
                raise KickerRoleError(
                    f"KICKER_ROLE_PERSON_DECLARATION_DUPLICATE:{recipient.underlying_id}"
                )
            detail = kickers.get(recipient.underlying_id)
            if detail is None:
                raise KickerRoleError(
                    f"KICKER_ROLE_UNKNOWN_PERSON:{recipient.underlying_id}"
                )
            roles = detail["roles"]
            assert isinstance(roles, dict)
            if (
                detail["team"] != team
                or detail["game_id"] != declaration.game_id
                or roles["CPT"] != recipient.cpt_dk_id
                or roles["FLEX"] != recipient.flex_dk_id
            ):
                raise KickerRoleError(
                    f"KICKER_ROLE_IDENTITY_MISMATCH:{recipient.underlying_id}"
                )
            if recipient.share > 0 and recipient.underlying_id not in selectable:
                raise KickerRoleError(
                    f"KICKER_ROLE_POSITIVE_SHARE_NOT_ELIGIBLE:{recipient.underlying_id}:"
                    "refresh role evidence after the inactive or exclusion change"
                )
            people.add(recipient.underlying_id)
            bound_people.add(recipient.underlying_id)

        total = sum(recipient.share for recipient in declaration.recipients)
        if not math.isclose(
            total, 1.0, rel_tol=0, abs_tol=evidence.share_tolerance
        ):
            raise KickerRoleError(
                f"KICKER_ROLE_SHARE_TOTAL_INVALID:team={team}:total={total:.12g}:expected=1"
            )
        if declaration.allocation_kind == "SOLE":
            if len(declaration.recipients) != 1 or not math.isclose(
                declaration.recipients[0].share,
                1.0,
                rel_tol=0,
                abs_tol=evidence.share_tolerance,
            ):
                raise KickerRoleError(f"KICKER_ROLE_SOLE_DECLARATION_INVALID:{team}")
            recipient = declaration.recipients[0]
            salary_name = str(kickers[recipient.underlying_id]["name"]).casefold()
            qualitative = [
                sources[digest][0]
                for digest in referenced
                if sources[digest][0].support_kind == "QUALITATIVE_SOLE"
            ]
            numerical = [
                sources[digest][0]
                for digest in referenced
                if sources[digest][0].support_kind == "NUMERICAL_SPLIT"
            ]
            if qualitative:
                if not all(
                    salary_name in source.supporting_excerpt.casefold()
                    and any(cue in source.supporting_excerpt.casefold() for cue in _SOLE_CUES)
                    for source in qualitative
                ):
                    raise KickerRoleError(
                        f"KICKER_ROLE_QUALITATIVE_SUPPORT_INSUFFICIENT:{team}"
                    )
            if numerical:
                for source in numerical:
                    _validate_numerical_support(
                        source.supporting_excerpt, declaration=declaration
                    )
            if not qualitative and not numerical:
                raise KickerRoleError(f"KICKER_ROLE_SOLE_SUPPORT_MISSING:{team}")
        else:
            if len(declaration.recipients) < 2:
                raise KickerRoleError(f"KICKER_ROLE_SPLIT_REQUIRES_TWO_RECIPIENTS:{team}")
            if people != eligible_by_team.get(team, set()):
                raise KickerRoleError(
                    f"KICKER_ROLE_SPLIT_COVERAGE_MISMATCH:team={team}:"
                    f"declared={sorted(people)}:eligible={sorted(eligible_by_team.get(team, set()))}"
                )
            numerical = [
                sources[digest][0]
                for digest in referenced
                if sources[digest][0].support_kind == "NUMERICAL_SPLIT"
            ]
            if any(
                sources[digest][0].support_kind == "QUALITATIVE_SOLE"
                for digest in referenced
            ):
                raise KickerRoleError(
                    f"KICKER_ROLE_SPLIT_QUALITATIVE_SOURCE_NOT_ALLOWED:{team}:"
                    "qualitative prose cannot invent fractional shares"
                )
            if not numerical:
                raise KickerRoleError(
                    f"KICKER_ROLE_SPLIT_REQUIRES_NUMERICAL_SOURCE:{team}:"
                    "qualitative prose cannot invent fractional shares"
                )
            for source in numerical:
                _validate_numerical_support(source.supporting_excerpt, declaration=declaration)

    shares = {person: 0.0 for person in kickers}
    allocations: dict[str, dict[str, float]] = {}
    gaps: list[str] = []
    for team in sorted({player.team for player in slate.players}):
        eligible = eligible_by_team.get(team, set())
        declaration = declarations.get(team)
        if not eligible:
            if declaration is not None:
                raise KickerRoleError(
                    f"KICKER_ROLE_DECLARED_WITH_NO_ELIGIBLE_KICKER:{team}:refresh evidence"
                )
            allocations[team] = {}
            gaps.append(
                f"NO_ELIGIBLE_KICKER:team={team}:no team kicking production allocated;"
                " K-free lineups may proceed diagnostically"
            )
            continue
        if declaration is None:
            raise KickerRoleError(
                f"KICKER_ROLE_EVIDENCE_COVERAGE_MISSING:team={team}:"
                "a supplied artifact must resolve every team with an eligible kicker"
            )
        values = {
            recipient.underlying_id: recipient.share
            for recipient in declaration.recipients
        }
        if declaration.allocation_kind == "SOLE":
            for person in eligible:
                values.setdefault(person, 0.0)
        for person, share in values.items():
            shares[person] = share
        allocations[team] = values

    used_sources = {
        digest
        for declaration in evidence.declarations
        for digest in declaration.source_sha256s
    }
    if used_sources != set(sources):
        raise KickerRoleError(
            f"KICKER_ROLE_UNUSED_SOURCE:{sorted(set(sources).difference(used_sources))}"
        )
    return KickerRoleResolution(
        allocation_version=evidence.allocation_version,
        shares_by_person=shares,
        zero_share_people=tuple(sorted(person for person, share in shares.items() if share == 0)),
        assumptions=(),
        coverage_gaps=tuple(gaps),
        team_allocations=allocations,
        evidence_path=str(manifest_path),
        evidence_sha256=manifest_digest,
        source_paths=tuple(sorted(source_paths)),
        source_hashes=source_hashes,
        observed_at=min(source.observed_at for source, _path in sources.values()).isoformat(),
        expires_at=min(source.expires_at for source, _path in sources.values()).isoformat(),
        synthetic_sources=tuple(
            sorted(source.sha256 for source, _path in sources.values() if source.synthetic)
        ),
    )


def verify_kicker_role_resolution(
    resolution: KickerRoleResolution,
    *,
    at: datetime,
) -> None:
    """Recheck immutable bytes and expiry immediately before review export."""

    if resolution.evidence_path is None:
        return
    when = at.astimezone(timezone.utc)
    if sha256_file(resolution.evidence_path) != resolution.evidence_sha256:
        raise KickerRoleError("KICKER_ROLE_EVIDENCE_CHANGED_DURING_SELECTION")
    for path, digest in (resolution.source_hashes or {}).items():
        if sha256_file(path) != digest:
            raise KickerRoleError(
                f"KICKER_ROLE_SOURCE_CHANGED_DURING_SELECTION:path={path}"
            )
    if resolution.expires_at is not None:
        expires = datetime.fromisoformat(resolution.expires_at.replace("Z", "+00:00"))
        if when > expires:
            raise KickerRoleError(
                "KICKER_ROLE_SOURCE_EXPIRED_DURING_SELECTION:refresh role evidence and rerun"
            )


def validate_kicker_scoring_allocation(
    slate: SlateContract,
    resolution: KickerRoleResolution,
) -> None:
    """Defend the scorer from an unvalidated in-process allocation object."""

    kickers = _salary_kickers(slate)
    teams = {player.team for player in slate.players}
    if set(resolution.shares_by_person) != set(kickers):
        raise KickerRoleError("KICKER_ROLE_SCORING_PERSON_COVERAGE_MISMATCH")
    if set(resolution.team_allocations) != teams:
        raise KickerRoleError("KICKER_ROLE_SCORING_TEAM_COVERAGE_MISMATCH")
    for person, share in resolution.shares_by_person.items():
        if not math.isfinite(share) or share < 0:
            raise KickerRoleError(f"KICKER_ROLE_SCORING_SHARE_INVALID:{person}")
    expected_zero = {
        person for person, share in resolution.shares_by_person.items() if share == 0
    }
    if set(resolution.zero_share_people) != expected_zero:
        raise KickerRoleError("KICKER_ROLE_ZERO_SHARE_REPORT_MISMATCH")
    for team, allocation in resolution.team_allocations.items():
        expected_people = {
            person
            for person, detail in kickers.items()
            if detail["team"] == team and resolution.shares_by_person[person] > 0
        }
        if set(allocation) != expected_people | {
            person for person, share in allocation.items() if share == 0
        }:
            raise KickerRoleError(f"KICKER_ROLE_SCORING_TEAM_BINDING_INVALID:{team}")
        for person, share in allocation.items():
            if person not in kickers or kickers[person]["team"] != team:
                raise KickerRoleError(f"KICKER_ROLE_SCORING_TEAM_BINDING_INVALID:{team}")
            if not math.isclose(
                share,
                resolution.shares_by_person[person],
                rel_tol=0,
                abs_tol=KICKER_ROLE_SHARE_TOLERANCE,
            ):
                raise KickerRoleError(f"KICKER_ROLE_SCORING_SHARE_MISMATCH:{person}")
        total = sum(allocation.values())
        if allocation and not math.isclose(
            total, 1.0, rel_tol=0, abs_tol=KICKER_ROLE_SHARE_TOLERANCE
        ):
            raise KickerRoleError(
                f"KICKER_ROLE_SCORING_TEAM_TOTAL_INVALID:{team}:{total:.12g}"
            )
        if not allocation and any(
            resolution.shares_by_person[person] > 0
            for person, detail in kickers.items()
            if detail["team"] == team
        ):
            raise KickerRoleError(f"KICKER_ROLE_SCORING_TEAM_TOTAL_INVALID:{team}:0")


def allocation_from_model_people(
    slate: SlateContract,
    people: Sequence[str],
) -> KickerRoleResolution:
    """Compatibility helper for direct scorer calls with no participation object."""

    selectable = set(people)
    status = {
        player.underlying_id: "" for player in slate.players
    }
    contract = ParticipationContract(
        contract_version="score_pool_people_v1",
        status_by_person=status,
        unavailable_people=tuple(sorted(set(status).difference(selectable))),
        unavailable_dk_ids=(),
        degraded_people=(),
        available_people=tuple(sorted(status)),
        operator_excluded_people=(),
    )
    return _implicit_resolution(slate, contract)
