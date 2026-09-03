from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


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

    @field_validator("captured_at", "observed_at")
    @classmethod
    def ledger_timezone_required(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("ledger timestamps must be timezone-aware")
        return value


class SourceLedger(FrozenModel):
    schema_version: Literal["nfl_source_ledger_v1"]
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
    created_at: datetime
    input_hashes: dict[str, str]
    config_hashes: dict[str, str]
    model_hashes: dict[str, str]
    output_path: str | None = None
    output_sha256: str | None = None
    evidence: tuple[EvidenceRecord, ...]
    solver_proof: dict[str, Any] = Field(default_factory=dict)
    runtime: dict[str, float] = Field(default_factory=dict)
    blockers: tuple[str, ...] = ()


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
