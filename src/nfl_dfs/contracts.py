from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, Iterable, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)


class EngineMode(StrEnum):
    CLASSIC = "CLASSIC"
    SHOWDOWN = "SHOWDOWN"


class ContestObjective(StrEnum):
    LARGE_GPP = "LARGE_GPP"
    SMALL_GPP = "SMALL_GPP"
    CASH = "CASH"
    WTA = "WTA"
    SATELLITE = "SATELLITE"


class EvidenceState(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"
    STALE = "STALE"
    CONFLICTED = "CONFLICTED"
    NOT_YET_DUE = "NOT_YET_DUE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class ReleaseEvidenceState(StrEnum):
    PASS = "PASS"
    UNKNOWN = "UNKNOWN"
    STALE = "STALE"
    CONFLICTED = "CONFLICTED"


class ModelStatus(StrEnum):
    UNVALIDATED = "UNVALIDATED"
    PRIOR_ONLY = "PRIOR_ONLY"
    PROSPECTIVELY_VALIDATED = "PROSPECTIVELY_VALIDATED"


class ReleaseDecision(StrEnum):
    CERTIFIED_UPLOAD_PACKAGE = "CERTIFIED_UPLOAD_PACKAGE"
    DO_NOT_UPLOAD = "DO_NOT_UPLOAD"


class CertificationBasis(StrEnum):
    MANUAL_GUARDRAIL = "MANUAL_GUARDRAIL"
    MODEL_ASSISTED = "MODEL_ASSISTED"


class WorkflowState(StrEnum):
    NEW = "NEW"
    SNAPSHOTTED = "SNAPSHOTTED"
    RECONCILED = "RECONCILED"
    MODELLED = "MODELLED"
    CANDIDATES_READY = "CANDIDATES_READY"
    SELECTED = "SELECTED"
    QA_REVIEWED = "QA_REVIEWED"
    CERTIFIED = "CERTIFIED"
    DO_NOT_UPLOAD = "DO_NOT_UPLOAD"
    LOCKED = "LOCKED"
    SETTLED = "SETTLED"
    GRADED = "GRADED"


SOURCE_LEDGER_V1 = "nfl_source_ledger_v1"
SOURCE_LEDGER_V2 = "nfl_source_ledger_v2"
# What a producer must emit. `SOURCE_LEDGER_V1` stays readable as the legacy
# shape and carries no per-source expiry, which is the R08 defect itself.
SOURCE_LEDGER_SCHEMA = SOURCE_LEDGER_V2
_LEDGER_V2_REQUIRED_FIELDS = (
    "expires_at",
    "evidence_state",
    "evidence_scope",
    "transformation_version",
)


class EvidenceScope(StrEnum):
    """What a source artifact is evidence *of*.

    R08: a hash binding proves which bytes were consumed, not what they cover.
    A player prior going stale must not be renewed by a fresh market capture,
    so scope travels with the entry and is never inferred from a filename.
    """

    SLATE_GEOMETRY = "SLATE_GEOMETRY"
    TEAM_PRIOR = "TEAM_PRIOR"
    PLAYER_PRIOR = "PLAYER_PRIOR"
    IDENTITY_MAP = "IDENTITY_MAP"


# Worst state first. A conflict outranks staleness, which outranks an unknown,
# because a conflicted source is a stop and an unknown one is a gap.
_FRESHNESS_SEVERITY: dict[EvidenceState, int] = {
    EvidenceState.CONFLICTED: 0,
    EvidenceState.FAIL: 1,
    EvidenceState.STALE: 2,
    EvidenceState.UNKNOWN: 3,
    EvidenceState.NOT_YET_DUE: 4,
    EvidenceState.NOT_APPLICABLE: 5,
    EvidenceState.PASS: 6,
}


class SourceFreshness(FrozenModel):
    """The one freshness rule, shared by every boundary that asks the question.

    R08 found three separate implementations: the projection producer checked
    `expires_at` against its own `as_of`, the ledger validator checked hashes
    and future timestamps and never staleness, and the prior-package resolver
    read `expires_at` straight out of artifact metadata. They all evaluate this
    now. An expiry is a reason to refetch and is never widened.
    """

    label: str = Field(min_length=1)
    expires_at: datetime
    basis: str = "UNRECORDED"
    observed_at: datetime | None = None
    declared_state: EvidenceState = EvidenceState.PASS

    @field_validator("expires_at", "observed_at")
    @classmethod
    def freshness_timezone_required(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("freshness timestamps must be timezone-aware")
        return value

    @model_validator(mode="after")
    def window_is_ordered(self) -> "SourceFreshness":
        if self.observed_at is not None and self.expires_at < self.observed_at:
            raise ValueError(f"{self.label} expires before it was observed")
        return self

    def state_at(self, when: datetime) -> EvidenceState:
        """Re-derive the evidence state at an arbitrary clock.

        The caller decides which clock that is: a replay uses the run's
        recorded `as_of`, a release uses the live clock. Nothing here reads a
        clock of its own.

        The declared state and the expiry verdict are composed, worst wins,
        rather than the declared state short-circuiting the clock. A source
        labelled `NOT_APPLICABLE` or `NOT_YET_DUE` that is also past its expiry
        reports `STALE`; a `CONFLICTED` one stays `CONFLICTED`, which is worse
        than stale. Short-circuiting let a non-PASS label hide staleness and,
        through `earliest_source_freshness`, carry a later expiry than the
        earliest real one.
        """

        expiry_state = (
            EvidenceState.STALE
            if when.astimezone(timezone.utc) > self.expires_at.astimezone(timezone.utc)
            else EvidenceState.PASS
        )
        return min(
            (self.declared_state, expiry_state), key=lambda state: _FRESHNESS_SEVERITY[state]
        )


def earliest_source_freshness(
    records: Iterable[SourceFreshness], *, at: datetime
) -> SourceFreshness:
    """The binding source: worst state at `at`, earliest expiry breaking ties."""

    candidates = list(records)
    if not candidates:
        raise ValueError("at least one source freshness record is required")
    return min(
        candidates,
        key=lambda item: (
            _FRESHNESS_SEVERITY[item.state_at(at)],
            item.expires_at.astimezone(timezone.utc),
            item.label,
        ),
    )


def earliest_expiry(records: Iterable[SourceFreshness]) -> datetime:
    """The earliest expiry across a set of sources. An expiry is never widened."""

    candidates = list(records)
    if not candidates:
        raise ValueError("at least one source freshness record is required")
    return min(item.expires_at.astimezone(timezone.utc) for item in candidates)


def source_freshness_evidence(
    records: Iterable[SourceFreshness],
    *,
    subject: str,
    field: str,
    at: datetime,
    source_artifact_id: str | None = None,
    source_url: str | None = None,
    value: Any = None,
) -> "EvidenceRecord":
    """Bind a freshness verdict into the hard-gate evidence set.

    The returned record carries the binding `expires_at`, so
    `evaluate_hard_gates` re-derives `STALE` at whatever clock it is given
    later. That is how a package that was valid at creation goes stale at its
    real expiry without anyone re-reading the sources.
    """

    collected = list(records)
    binding = earliest_source_freshness(collected, at=at)
    state = binding.state_at(at)
    # The state comes from the worst source; the window comes from the earliest
    # expiry. Taking both from one record could stamp a later expiry than the
    # set actually has, which is a widening.
    return EvidenceRecord(
        subject=subject,
        field=field,
        value=value if value is not None else {"binding_source": binding.label},
        source_artifact_id=source_artifact_id,
        source_url=source_url,
        observed_at=binding.observed_at,
        expires_at=earliest_expiry(collected),
        hard_gate=True,
        state=state,
        reason=(
            f"binding source {binding.label} is {state.value}"
            f" at {at.astimezone(timezone.utc).isoformat()};"
            f" expiry basis {binding.basis}"
        ),
    )


class SourceArtifact(FrozenModel):
    artifact_id: str
    path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    byte_count: int = Field(ge=0)
    source: str
    source_uri: str | None = None
    license_decision: str
    captured_at: datetime
    effective_at: datetime | None = None
    per_record_timestamp_field: str | None = None
    parser_version: str
    coverage: dict[str, Any] = Field(default_factory=dict)

    @field_validator("captured_at", "effective_at")
    @classmethod
    def timezone_required(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("timestamps must be timezone-aware")
        return value


class LedgerEntry(FrozenModel):
    artifact_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    path: str = Field(min_length=1)
    source_uri: str = Field(min_length=1)
    captured_at: datetime
    observed_at: datetime | None = None
    license_decision: Literal[
        "OPERATOR_SUPPLIED",
        "PUBLIC_DOMAIN",
        "PERMITTED_PUBLIC_API",
        "PERMITTED_REPOSITORY_LICENSE",
        "SECONDARY_STATUS_ONLY",
    ]
    parser_version: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
    coverage: dict[str, Any] = Field(default_factory=dict)
    # `nfl_source_ledger_v2`. R08: the producer checked `expires_at` and the
    # evidence state against its supplied `as_of` and then dropped both, so a
    # downstream consumer saw a hash match and called it freshness. A consumed
    # entry now carries its own expiry, scope, state, transformation version
    # and input dependency bindings. A `v1` entry carries none of these and is
    # accepted only as the legacy read shape.
    expires_at: datetime | None = None
    evidence_state: EvidenceState | None = None
    evidence_scope: EvidenceScope | None = None
    transformation_version: str | None = Field(
        default=None, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$"
    )
    depends_on: dict[str, str] = Field(default_factory=dict)

    @field_validator("captured_at", "observed_at", "expires_at")
    @classmethod
    def ledger_timezone_required(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("ledger timestamps must be timezone-aware")
        return value

    @field_validator("depends_on")
    @classmethod
    def dependency_bindings_are_hashes(cls, value: dict[str, str]) -> dict[str, str]:
        for name, digest in value.items():
            if not name or not isinstance(digest, str) or len(digest) != 64:
                raise ValueError(
                    "input dependency bindings must be named lowercase SHA-256 values"
                )
            if any(character not in "0123456789abcdef" for character in digest):
                raise ValueError(
                    "input dependency bindings must be named lowercase SHA-256 values"
                )
        return value

    @model_validator(mode="after")
    def expiry_follows_observation(self) -> "LedgerEntry":
        if self.expires_at is None:
            return self
        expires = self.expires_at.astimezone(timezone.utc)
        observed = (self.observed_at or self.captured_at).astimezone(timezone.utc)
        if expires < observed:
            raise ValueError(f"ledger entry expires before it was observed: {self.path}")
        return self

    def freshness(self) -> SourceFreshness | None:
        """This entry's freshness record, or `None` for a legacy `v1` entry."""

        if self.expires_at is None:
            return None
        scope = self.evidence_scope.value if self.evidence_scope else "UNSCOPED"
        return SourceFreshness(
            label=f"{scope}:{self.artifact_id[:12]}",
            expires_at=self.expires_at,
            basis=str(self.coverage.get("expiry_basis", "") or "UNRECORDED"),
            observed_at=self.observed_at,
            declared_state=self.evidence_state or EvidenceState.PASS,
        )


class SourceLedger(FrozenModel):
    schema_version: Literal["nfl_source_ledger_v1", "nfl_source_ledger_v2"]
    entries: tuple[LedgerEntry, ...] = Field(min_length=1)
    derived: dict[str, str]

    @field_validator("derived")
    @classmethod
    def valid_derived_hashes(cls, value: dict[str, str]) -> dict[str, str]:
        if not value:
            raise ValueError("derived hashes must not be empty")
        for name, digest in value.items():
            if not name or not isinstance(digest, str) or len(digest) != 64:
                raise ValueError("derived hashes must use named lowercase SHA-256 values")
            if any(character not in "0123456789abcdef" for character in digest):
                raise ValueError("derived hashes must use named lowercase SHA-256 values")
        return value

    @model_validator(mode="after")
    def unique_entries(self) -> "SourceLedger":
        artifact_ids = [entry.artifact_id for entry in self.entries]
        if len(set(artifact_ids)) != len(artifact_ids):
            raise ValueError("source ledger artifact IDs must be unique")
        return self

    @model_validator(mode="after")
    def schema_version_matches_entry_shape(self) -> "SourceLedger":
        """The declared version and the entry shape cannot disagree.

        A `v2` ledger is the consumed contract R08 requires, so every entry
        must carry its expiry, scope, state and transformation version, and
        must address its archived bytes inside the package. A `v1` ledger is
        the legacy shape and may not carry those fields at all, so a producer
        cannot half-migrate and leave a consumer guessing which rule applies.
        """

        for entry in self.entries:
            present = tuple(
                name
                for name in _LEDGER_V2_REQUIRED_FIELDS
                if getattr(entry, name) is not None
            )
            if self.schema_version == SOURCE_LEDGER_V2:
                missing = tuple(
                    name
                    for name in _LEDGER_V2_REQUIRED_FIELDS
                    if getattr(entry, name) is None
                )
                if missing:
                    raise ValueError(
                        f"{SOURCE_LEDGER_V2} entry {entry.path} is missing "
                        f"{sorted(missing)}"
                    )
                if (
                    PurePosixPath(entry.path).is_absolute()
                    or PureWindowsPath(entry.path).is_absolute()
                    or "\\" in entry.path
                ):
                    raise ValueError(
                        f"{SOURCE_LEDGER_V2} entry paths must be package-relative"
                        " POSIX paths so a copied package resolves without a path"
                        f" rewrite: {entry.path}"
                    )
                # Both flavours, because `..\..\x` is one opaque segment to
                # PurePosixPath and is not absolute to PureWindowsPath either.
                if ".." in PurePosixPath(entry.path).parts or ".." in PureWindowsPath(
                    entry.path
                ).parts:
                    raise ValueError(
                        f"{SOURCE_LEDGER_V2} entry path escapes the package: {entry.path}"
                    )
            elif present or entry.depends_on:
                raise ValueError(
                    f"{SOURCE_LEDGER_V1} entries cannot carry {SOURCE_LEDGER_V2}"
                    f" fields {sorted(present)}; emit {SOURCE_LEDGER_V2} instead"
                )
        return self

    def freshness(self) -> tuple[SourceFreshness, ...]:
        """Every per-source freshness record this ledger preserves.

        Empty for a legacy `v1` ledger, which is exactly why `v1` cannot clear
        a release gate: it never recorded an expiry to re-evaluate.
        """

        return tuple(
            record
            for record in (entry.freshness() for entry in self.entries)
            if record is not None
        )


class EvidenceRecord(FrozenModel):
    subject: str
    field: str
    value: Any = None
    source_artifact_id: str | None = None
    source_url: str | None = None
    observed_at: datetime | None = None
    expires_at: datetime | None = None
    hard_gate: bool
    state: EvidenceState
    reason: str

    @model_validator(mode="after")
    def validate_state(self) -> "EvidenceRecord":
        if self.state is EvidenceState.PASS and not (
            self.source_artifact_id or self.source_url or self.field == "final_bytes"
        ):
            raise ValueError("PASS evidence must be source-bound")
        if self.observed_at and self.observed_at.tzinfo is None:
            raise ValueError("observed_at must be timezone-aware")
        if self.expires_at and self.expires_at.tzinfo is None:
            raise ValueError("expires_at must be timezone-aware")
        return self

    def state_at(self, now: datetime | None = None) -> EvidenceState:
        when = now or datetime.now(timezone.utc)
        if self.state is EvidenceState.PASS and self.expires_at and when > self.expires_at:
            return EvidenceState.STALE
        return self.state


class GameContract(FrozenModel):
    game_id: str
    away_team: str
    home_team: str
    lock_at: datetime


class SalaryPlayer(FrozenModel):
    dk_id: str
    name: str
    position: str
    roster_positions: tuple[str, ...]
    salary: int = Field(ge=0)
    team: str
    opponent: str
    game_id: str
    lock_at: datetime
    status_raw: str = ""
    underlying_id: str
    role: Literal["CPT", "FLEX"] | None = None


class SlateContract(FrozenModel):
    site: Literal["DRAFTKINGS"] = "DRAFTKINGS"
    sport: Literal["NFL"] = "NFL"
    mode: EngineMode
    draft_group: str
    games: tuple[GameContract, ...]
    scoring_version: str
    salary_hash: str
    players: tuple[SalaryPlayer, ...]
    salary_cap: int = 50_000


class EntryAuthorization(FrozenModel):
    entry_id: str
    contest_id: str
    contest_name: str
    entry_fee: float = Field(ge=0)
    existing_cells: tuple[str, ...]


class PayoutTier(FrozenModel):
    rank_start: int = Field(ge=1)
    rank_end: int = Field(ge=1)
    prize_type: Literal["CASH", "TICKET"]
    value: float = Field(ge=0)

    @model_validator(mode="after")
    def valid_range(self) -> "PayoutTier":
        if self.rank_end < self.rank_start:
            raise ValueError("rank_end must not precede rank_start")
        return self


class ContestContract(FrozenModel):
    contest_id: str
    entries: tuple[EntryAuthorization, ...]
    field_size: int = Field(ge=2)
    max_entries: int = Field(ge=1)
    fee: float = Field(ge=0)
    payout_tiers: tuple[PayoutTier, ...]
    advertised_prize_value: float = Field(ge=0)
    objective: ContestObjective
    mode: EngineMode
    ticket_face_value: float | None = Field(default=None, ge=0)


class RoleVariant(FrozenModel):
    underlying_id: str
    dk_id: str
    role: Literal["CPT", "FLEX"]
    salary: int
    salary_multiplier: float
    scoring_multiplier: float


class PlayerIdentity(FrozenModel):
    dk_id: str
    underlying_id: str
    name: str
    team: str
    position: str
    gsis_id: str | None = None
    identity_evidence: EvidenceRecord


class PredictionSnapshot(FrozenModel):
    snapshot_id: str
    created_at: datetime
    feature_cutoff: datetime
    model_version: str
    player_ids: tuple[str, ...]
    opportunity_parameters: dict[str, dict[str, float]]
    uncertainty: dict[str, dict[str, float]]
    input_hashes: dict[str, str]


class ScenarioBank(FrozenModel):
    bank_id: str
    purpose: Literal["DESIGN", "SELECT", "REFEREE"]
    seed: int
    scenario_count: int = Field(gt=0)
    input_hashes: dict[str, str]
    model_hash: str
    sample_weight_hash: str | None = None
    outcome_path: str


class Lineup(FrozenModel):
    mode: EngineMode
    roster: tuple[str, ...]
    canonical_key: str
    salary: int


class PortfolioAssignment(FrozenModel):
    assignment_id: str
    contest_id: str
    objective: ContestObjective
    entry_to_lineup: dict[str, Lineup]
    exposure: dict[str, float]
    field_state_metrics: dict[str, dict[str, float]]
    late_swap_state: dict[str, Any] = Field(default_factory=dict)


class CertificationManifest(FrozenModel):
    manifest_version: Literal["certification_manifest_v1"] = "certification_manifest_v1"
    run_id: str
    status: Literal["CERTIFIED", "DO_NOT_UPLOAD"]
    file_valid: bool = Field(alias="FILE_VALID")
    evidence_state: ReleaseEvidenceState = Field(alias="EVIDENCE_STATE")
    model_status: ModelStatus = Field(alias="MODEL_STATUS")
    release_decision: ReleaseDecision = Field(alias="RELEASE_DECISION")
    certification_basis: CertificationBasis = CertificationBasis.MANUAL_GUARDRAIL
    created_at: datetime
    input_hashes: dict[str, str]
    config_hashes: dict[str, str]
    model_hashes: dict[str, str]
    output_path: str | None = None
    output_sha256: str | None = None
    proposed_output_sha256: str | None = None
    proposed_output_byte_count: int | None = Field(default=None, ge=0)
    evidence: tuple[EvidenceRecord, ...]
    solver_proof: dict[str, Any] = Field(default_factory=dict)
    runtime: dict[str, float] = Field(default_factory=dict)
    file_blockers: tuple[str, ...] = ()
    evidence_blockers: tuple[str, ...] = ()
    model_blockers: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()

    @model_validator(mode="before")
    @classmethod
    def backfill_release_truths(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        result = dict(value)
        status = result.get("status")
        certified = status == "CERTIFIED"
        if "FILE_VALID" not in result and "file_valid" not in result:
            result["FILE_VALID"] = certified
        if "EVIDENCE_STATE" not in result and "evidence_state" not in result:
            result["EVIDENCE_STATE"] = "PASS" if certified else "UNKNOWN"
        if "MODEL_STATUS" not in result and "model_status" not in result:
            result["MODEL_STATUS"] = "UNVALIDATED"
        if "RELEASE_DECISION" not in result and "release_decision" not in result:
            result["RELEASE_DECISION"] = (
                "CERTIFIED_UPLOAD_PACKAGE" if certified else "DO_NOT_UPLOAD"
            )
        return result

    @model_validator(mode="after")
    def legacy_status_matches_release_decision(self) -> "CertificationManifest":
        expected = (
            "CERTIFIED"
            if self.release_decision is ReleaseDecision.CERTIFIED_UPLOAD_PACKAGE
            else "DO_NOT_UPLOAD"
        )
        if self.status != expected:
            raise ValueError("status must be derived from RELEASE_DECISION")
        if self.release_decision is ReleaseDecision.CERTIFIED_UPLOAD_PACKAGE:
            if not self.file_valid or self.evidence_state is not ReleaseEvidenceState.PASS:
                raise ValueError("certified release requires valid file bytes and PASS evidence")
            if (
                self.certification_basis is CertificationBasis.MODEL_ASSISTED
                and self.model_status is not ModelStatus.PROSPECTIVELY_VALIDATED
            ):
                raise ValueError(
                    "model-assisted release requires prospective model validation"
                )
            if self.blockers:
                raise ValueError("certified release cannot contain blockers")
            if not self.output_path or not self.output_sha256:
                raise ValueError("certified release requires a persisted hashed output")
        elif self.output_path or self.output_sha256:
            raise ValueError("DO_NOT_UPLOAD manifest cannot point to upload bytes")
        return self


class LateSwapEligibility(FrozenModel):
    schema_version: Literal["nfl_late_swap_eligibility_v1"]
    contest_id: str = Field(pattern=r"^[0-9]+$")
    bulk_late_swap_eligible: bool
    evidence_state: EvidenceState
    source_url: str = Field(min_length=1)
    observed_at: datetime
    expires_at: datetime

    @field_validator("observed_at", "expires_at")
    @classmethod
    def eligibility_timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("eligibility timestamps must be timezone-aware")
        return value

    @model_validator(mode="after")
    def eligibility_window_is_ordered(self) -> "LateSwapEligibility":
        if self.evidence_state is EvidenceState.NOT_APPLICABLE:
            raise ValueError("late-swap eligibility cannot be NOT_APPLICABLE")
        if self.expires_at < self.observed_at:
            raise ValueError("eligibility expires_at must not precede observed_at")
        return self


class TeamInactiveReport(FrozenModel):
    team: str = Field(pattern=r"^[A-Z]{2,3}$")
    game_id: str = Field(min_length=3)
    inactive_dk_ids: tuple[str, ...]
    evidence_state: EvidenceState
    source_url: str = Field(min_length=1)
    observed_at: datetime

    @field_validator("observed_at")
    @classmethod
    def report_timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("inactive-report timestamps must be timezone-aware")
        return value

    @model_validator(mode="after")
    def report_ids_are_unique(self) -> "TeamInactiveReport":
        if self.evidence_state is EvidenceState.NOT_APPLICABLE:
            raise ValueError("a supplied team inactive report cannot be NOT_APPLICABLE")
        if len(set(self.inactive_dk_ids)) != len(self.inactive_dk_ids):
            raise ValueError(f"inactive IDs must be unique for team {self.team}")
        if any(not dk_id.isdigit() for dk_id in self.inactive_dk_ids):
            raise ValueError(f"inactive IDs must be exact numeric DK IDs for team {self.team}")
        return self


class TeamInactiveReportBundle(FrozenModel):
    schema_version: Literal["nfl_team_inactive_reports_v1"]
    reports: tuple[TeamInactiveReport, ...] = Field(min_length=1)


class LateSwapManifest(FrozenModel):
    manifest_version: Literal["nfl_late_swap_manifest_v1"] = (
        "nfl_late_swap_manifest_v1"
    )
    run_id: str
    prior_run_id: str | None = None
    status: Literal["CERTIFIED", "DO_NOT_UPLOAD"]
    file_valid: bool = Field(alias="FILE_VALID")
    evidence_state: ReleaseEvidenceState = Field(alias="EVIDENCE_STATE")
    model_status: ModelStatus = Field(alias="MODEL_STATUS")
    release_decision: ReleaseDecision = Field(alias="RELEASE_DECISION")
    certification_basis: CertificationBasis = CertificationBasis.MANUAL_GUARDRAIL
    created_at: datetime
    as_of: datetime
    contest_id: str | None = None
    input_hashes: dict[str, str]
    replaceable_cells: dict[str, tuple[int, ...]] = Field(default_factory=dict)
    output_path: str | None = None
    output_sha256: str | None = None
    proposed_output_sha256: str | None = None
    proposed_output_byte_count: int | None = Field(default=None, ge=0)
    evidence: tuple[EvidenceRecord, ...] = ()
    file_blockers: tuple[str, ...] = ()
    evidence_blockers: tuple[str, ...] = ()
    model_blockers: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    next_action: str
    runtime: dict[str, float] = Field(default_factory=dict)

    @field_validator("created_at", "as_of")
    @classmethod
    def late_swap_timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("late-swap timestamps must be timezone-aware")
        return value

    @model_validator(mode="after")
    def legacy_status_matches_release_decision(self) -> "LateSwapManifest":
        expected = (
            "CERTIFIED"
            if self.release_decision is ReleaseDecision.CERTIFIED_UPLOAD_PACKAGE
            else "DO_NOT_UPLOAD"
        )
        if self.status != expected:
            raise ValueError("status must be derived from RELEASE_DECISION")
        if self.release_decision is ReleaseDecision.CERTIFIED_UPLOAD_PACKAGE:
            if not self.file_valid or self.evidence_state is not ReleaseEvidenceState.PASS:
                raise ValueError("certified late swap requires valid bytes and PASS evidence")
            if (
                self.certification_basis is CertificationBasis.MODEL_ASSISTED
                and self.model_status is not ModelStatus.PROSPECTIVELY_VALIDATED
            ):
                raise ValueError(
                    "model-assisted late swap requires prospective model validation"
                )
            if self.blockers:
                raise ValueError("certified late swap cannot contain blockers")
            if not self.output_path or not self.output_sha256:
                raise ValueError("certified late swap requires a persisted hashed output")
        elif self.output_path or self.output_sha256:
            raise ValueError("DO_NOT_UPLOAD late swap cannot point to upload bytes")
        return self


class SettlementBundle(FrozenModel):
    settlement_id: str
    contest_id: str
    frozen_manifest_hash: str
    standings_hash: str
    scoring_reconciliation: dict[str, Any]
    settled_at: datetime


class ModelRegistryEntry(FrozenModel):
    model_id: str
    model_family: str
    version: str
    training_cutoff: datetime
    artifact_hash: str
    validation: dict[str, float]
    tier: Literal["COLD", "PROVISIONAL", "GRADED", "CALIBRATED"]
    deployed: bool
    rollback_model_id: str | None = None
