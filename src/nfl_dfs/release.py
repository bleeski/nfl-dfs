from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from .contracts import (
    CertificationBasis,
    EvidenceRecord,
    EvidenceState,
    ModelStatus,
    ReleaseDecision,
    ReleaseEvidenceState,
)


@dataclass(frozen=True)
class ReleasePolicyResult:
    file_valid: bool
    evidence_state: ReleaseEvidenceState
    model_status: ModelStatus
    release_decision: ReleaseDecision
    certification_basis: CertificationBasis
    file_blockers: tuple[str, ...]
    evidence_blockers: tuple[str, ...]
    model_blockers: tuple[str, ...]
    blockers: tuple[str, ...]

    @property
    def status(self) -> str:
        return legacy_status(self.release_decision)

    def truth_values(self) -> dict[str, bool | str]:
        return {
            "FILE_VALID": self.file_valid,
            "EVIDENCE_STATE": self.evidence_state.value,
            "MODEL_STATUS": self.model_status.value,
            "RELEASE_DECISION": self.release_decision.value,
        }


def _unique(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for value in values if value))


def legacy_status(decision: ReleaseDecision) -> str:
    return (
        "CERTIFIED"
        if decision is ReleaseDecision.CERTIFIED_UPLOAD_PACKAGE
        else "DO_NOT_UPLOAD"
    )


def aggregate_evidence_state(
    evidence: Iterable[EvidenceRecord],
    *,
    required_hard_fields: Iterable[str] = (),
    now: datetime | None = None,
    final_release: bool = True,
) -> tuple[ReleaseEvidenceState, tuple[str, ...]]:
    """Summarize hard evidence without conflating it with file validity."""
    records = tuple(evidence)
    when = now or datetime.now(timezone.utc)
    blockers: list[str] = []
    states: list[EvidenceState] = []
    hard_fields = {record.field for record in records if record.hard_gate}
    for required_field in required_hard_fields:
        if required_field not in hard_fields:
            blockers.append(f"MISSING_HARD_EVIDENCE:{required_field}")
            states.append(EvidenceState.UNKNOWN)
    for record in records:
        if not record.hard_gate:
            continue
        state = record.state_at(when)
        if state is EvidenceState.NOT_APPLICABLE:
            continue
        if state is EvidenceState.NOT_YET_DUE and not final_release:
            continue
        if state is not EvidenceState.PASS:
            blockers.append(
                f"{record.subject}.{record.field}:{state.value}:{record.reason}"
            )
            states.append(state)
    if any(state in {EvidenceState.CONFLICTED, EvidenceState.FAIL} for state in states):
        aggregate = ReleaseEvidenceState.CONFLICTED
    elif EvidenceState.STALE in states:
        aggregate = ReleaseEvidenceState.STALE
    elif states:
        aggregate = ReleaseEvidenceState.UNKNOWN
    else:
        aggregate = ReleaseEvidenceState.PASS
    return aggregate, _unique(blockers)


def derive_release_policy(
    *,
    file_valid: bool,
    evidence_state: ReleaseEvidenceState,
    model_status: ModelStatus,
    certification_basis: CertificationBasis,
    file_blockers: Iterable[str] = (),
    evidence_blockers: Iterable[str] = (),
    model_blockers: Iterable[str] = (),
    safety_blockers: Iterable[str] = (),
) -> ReleasePolicyResult:
    """Derive the only authoritative release decision from independent truths."""
    file_reasons = list(_unique(file_blockers))
    evidence_reasons = list(_unique(evidence_blockers))
    model_reasons = list(_unique(model_blockers))
    safety_reasons = list(_unique(safety_blockers))
    if not file_valid and not file_reasons:
        file_reasons.append("FILE_VALIDATION_INCOMPLETE")
    if evidence_state is not ReleaseEvidenceState.PASS and not evidence_reasons:
        evidence_reasons.append(f"HARD_EVIDENCE_STATE:{evidence_state.value}")
    if (
        certification_basis is CertificationBasis.MODEL_ASSISTED
        and model_status is not ModelStatus.PROSPECTIVELY_VALIDATED
    ):
        model_reasons.append(
            f"MODEL_NOT_PROSPECTIVELY_VALIDATED:{model_status.value}"
        )
    all_blockers = _unique(
        (*file_reasons, *evidence_reasons, *model_reasons, *safety_reasons)
    )
    decision = (
        ReleaseDecision.CERTIFIED_UPLOAD_PACKAGE
        if file_valid
        and evidence_state is ReleaseEvidenceState.PASS
        and not all_blockers
        and (
            certification_basis is CertificationBasis.MANUAL_GUARDRAIL
            or model_status is ModelStatus.PROSPECTIVELY_VALIDATED
        )
        else ReleaseDecision.DO_NOT_UPLOAD
    )
    return ReleasePolicyResult(
        file_valid=file_valid,
        evidence_state=evidence_state,
        model_status=model_status,
        release_decision=decision,
        certification_basis=certification_basis,
        file_blockers=tuple(file_reasons),
        evidence_blockers=tuple(evidence_reasons),
        model_blockers=tuple(model_reasons),
        blockers=all_blockers,
    )
