from __future__ import annotations

from datetime import datetime, timezone

import pytest

from nfl_dfs.contracts import (
    CertificationBasis,
    EvidenceRecord,
    EvidenceState,
    ModelStatus,
    ReleaseDecision,
    ReleaseEvidenceState,
)
from nfl_dfs.release import aggregate_evidence_state, derive_release_policy


@pytest.mark.parametrize(
    ("basis", "model_status", "expected"),
    [
        (
            CertificationBasis.MANUAL_GUARDRAIL,
            ModelStatus.UNVALIDATED,
            ReleaseDecision.CERTIFIED_UPLOAD_PACKAGE,
        ),
        (
            CertificationBasis.MODEL_ASSISTED,
            ModelStatus.UNVALIDATED,
            ReleaseDecision.DO_NOT_UPLOAD,
        ),
        (
            CertificationBasis.MODEL_ASSISTED,
            ModelStatus.PRIOR_ONLY,
            ReleaseDecision.DO_NOT_UPLOAD,
        ),
        (
            CertificationBasis.MODEL_ASSISTED,
            ModelStatus.PROSPECTIVELY_VALIDATED,
            ReleaseDecision.CERTIFIED_UPLOAD_PACKAGE,
        ),
    ],
)
def test_release_truth_table_keeps_model_and_manual_claims_separate(
    basis: CertificationBasis,
    model_status: ModelStatus,
    expected: ReleaseDecision,
) -> None:
    result = derive_release_policy(
        file_valid=True,
        evidence_state=ReleaseEvidenceState.PASS,
        model_status=model_status,
        certification_basis=basis,
    )
    assert result.release_decision is expected
    assert result.status == (
        "CERTIFIED" if expected is ReleaseDecision.CERTIFIED_UPLOAD_PACKAGE else "DO_NOT_UPLOAD"
    )
    if basis is CertificationBasis.MODEL_ASSISTED and model_status is not ModelStatus.PROSPECTIVELY_VALIDATED:
        assert result.model_blockers == (
            f"MODEL_NOT_PROSPECTIVELY_VALIDATED:{model_status.value}",
        )


@pytest.mark.parametrize(
    "evidence_state",
    [
        ReleaseEvidenceState.UNKNOWN,
        ReleaseEvidenceState.STALE,
        ReleaseEvidenceState.CONFLICTED,
    ],
)
def test_file_valid_alone_never_clears_nonpass_evidence(
    evidence_state: ReleaseEvidenceState,
) -> None:
    result = derive_release_policy(
        file_valid=True,
        evidence_state=evidence_state,
        model_status=ModelStatus.PROSPECTIVELY_VALIDATED,
        certification_basis=CertificationBasis.MODEL_ASSISTED,
    )
    assert result.file_valid
    assert result.release_decision is ReleaseDecision.DO_NOT_UPLOAD


@pytest.mark.parametrize(
    "blocker",
    [
        "LINEUP_illegal:salary cap exceeded",
        "ENTRY_AUTHORIZATION_MISMATCH",
        "FINAL_BYTE_AUDIT:unauthorized bytes changed",
    ],
)
def test_file_failures_remain_blocking(blocker: str) -> None:
    invalid = derive_release_policy(
        file_valid=False,
        evidence_state=ReleaseEvidenceState.PASS,
        model_status=ModelStatus.PROSPECTIVELY_VALIDATED,
        certification_basis=CertificationBasis.MODEL_ASSISTED,
        file_blockers=(blocker,),
    )
    assert invalid.release_decision is ReleaseDecision.DO_NOT_UPLOAD
    assert invalid.file_blockers == (blocker,)


@pytest.mark.parametrize(
    "blocker",
    [
        "SOLVER_PROOF_OUTSIDE_LIMIT",
        "DESIGN_PASSING_RECEIVING_ACCOUNTING_FAILED",
        "REFEREE_SIGN_DISAGREEMENT",
        "BUILD_ASSIGNMENT_HASH_MISMATCH",
    ],
)
def test_genuine_safety_failures_remain_blocking(blocker: str) -> None:
    unsafe = derive_release_policy(
        file_valid=True,
        evidence_state=ReleaseEvidenceState.PASS,
        model_status=ModelStatus.PROSPECTIVELY_VALIDATED,
        certification_basis=CertificationBasis.MODEL_ASSISTED,
        safety_blockers=(blocker,),
    )
    assert unsafe.release_decision is ReleaseDecision.DO_NOT_UPLOAD
    assert blocker in unsafe.blockers


def test_evidence_aggregate_has_registered_release_states_and_named_blockers() -> None:
    record = EvidenceRecord(
        subject="selected",
        field="official_inactive_status",
        source_artifact_id="a" * 64,
        observed_at=datetime.now(timezone.utc),
        hard_gate=True,
        state=EvidenceState.FAIL,
        reason="selected player is inactive",
    )
    state, blockers = aggregate_evidence_state(
        (record,), required_hard_fields=("official_inactive_status", "final_bytes")
    )
    assert state is ReleaseEvidenceState.CONFLICTED
    assert "MISSING_HARD_EVIDENCE:final_bytes" in blockers
    assert any("selected player is inactive" in blocker for blocker in blockers)
