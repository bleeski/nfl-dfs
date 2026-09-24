from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from .contracts import (
    CertificationBasis,
    DeliveryLimitation,
    DeliveryState,
    DeliveryTruth,
    EvidenceRecord,
    EvidenceState,
    GateClass,
    GateProvenance,
    GateStops,
    ModelStatus,
    ProvenanceKind,
    ReleaseDecision,
    ReleaseEvidenceState,
    ReleaseTruthsV2,
    ReleaseTruthsV3,
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


# ---------------------------------------------------------------------------
# DELIVERY_STATE (R28, Session 03). Beside the four truths above, never in them:
# nothing here reads model status or evidence, and `derive_release_policy` is
# unchanged. Sessions 04 to 09 wire it into the operating paths.
# ---------------------------------------------------------------------------

_INTEGRITY_BOUNDARY = GateProvenance(
    kind=ProvenanceKind.CLAUDE_MD_BOUNDARY,
    ref="Integrity gates (exact DraftKings IDs, hashes, entry mapping, blank-cell "
        "authority, locked cells, Classic/Showdown mode) still stop the file they protect.",
)
_AUTHORITY_BOUNDARY = GateProvenance(
    kind=ProvenanceKind.CLAUDE_MD_BOUNDARY,
    ref="Before lock, fill only blank roster cells belonging to the exact Entry IDs "
        "the supplied template authorizes.",
)
_R28 = GateProvenance(kind=ProvenanceKind.RULING, ref="R28")


class DeliveryStateError(ValueError):
    """The inputs contradict themselves; no delivery record can describe them."""


def _ordered_unique(values: Iterable[str], label: str) -> tuple[str, ...]:
    items = tuple(str(value) for value in values)
    if any(not value.strip() for value in items):
        raise DeliveryStateError(f"DELIVERY_ENTRY_ID_BLANK:{label}")
    repeated = sorted({value for value in items if items.count(value) > 1})
    if repeated:
        raise DeliveryStateError(f"DELIVERY_ENTRY_ID_REPEATED:{label}:{repeated}")
    return items


def _integrity(code: str, provenance: GateProvenance, entry_ids: tuple[str, ...] = (),
               detail: str = "") -> DeliveryLimitation:
    return DeliveryLimitation(code=code, gate_class=GateClass.V, stops=GateStops.FILE,
                              provenance=provenance, entry_ids=entry_ids, detail=detail)


def derive_delivery_state(
    *,
    file_valid: bool,
    authorized_entry_ids: Iterable[str],
    delivered_entry_ids: Iterable[str],
    limitations: Iterable[DeliveryLimitation] = (),
    preserved_entry_ids: Iterable[str] = (),
    unresolved_entry_ids: Iterable[str] = (),
) -> DeliveryTruth:
    """`DELIVERY_STATE` from file validity, coverage and integrity blockers only.

    - `file_valid`: the bytes to be handed over passed their own validation.
    - `authorized_entry_ids`: the blank rows the template authorizes filling, in
      its order.
    - `delivered_entry_ids`: the rows those bytes fill.
    - `preserved_entry_ids`, `unresolved_entry_ids` (Session 11): the template's
      other rows. A preserved row is prefilled and kept byte for byte; an
      unresolved row is left as it was and a limitation names it. Neither is
      delivered or unfilled.
    - `limitations`: every gate that fired. A `V` one with no Entry IDs, or with
      one that is not an authorized or unresolved row, stops the whole file;
      with Entry IDs it stops those rows. `S` and `P` ones never change the
      state and travel with it.

    An invalid file or a file-wide integrity gate delivers nothing. Otherwise
    every authorized row is delivered and no row is unresolved
    (`DELIVERABLE`), some rows are delivered (`DELIVERABLE_PARTIAL`), or none
    are (`NO_DELIVERABLE`). A row left unfilled that no limitation names gets
    `UNFILLED_AUTHORIZED_ROWS`, so a gap is never silent. A delivered row that
    is unauthorized, or that an integrity gate blocks, raises: the file would
    hold bytes its own record disowns. So does an unresolved row nothing names.
    """

    authorized = _ordered_unique(authorized_entry_ids, "authorized")
    delivered_in = _ordered_unique(delivered_entry_ids, "delivered")
    preserved = _ordered_unique(preserved_entry_ids, "preserved")
    unresolved = _ordered_unique(unresolved_entry_ids, "unresolved")
    overlap = sorted((set(authorized) & set(preserved)) | (set(authorized) & set(unresolved))
                     | (set(preserved) & set(unresolved)))
    if overlap:
        raise DeliveryStateError(f"DELIVERY_ROW_KIND_OVERLAP:{overlap}")
    stray = [eid for eid in delivered_in if eid not in authorized]
    if stray:
        raise DeliveryStateError(f"DELIVERY_ENTRY_NOT_AUTHORIZED:{stray}")
    items = list(limitations)
    named_any = {eid for item in items for eid in item.entry_ids}
    unnamed = [eid for eid in unresolved if eid not in named_any]
    if unnamed:
        raise DeliveryStateError(f"DELIVERY_UNRESOLVED_ROW_UNNAMED:{unnamed}")
    scoped = set(authorized) | set(unresolved)
    integrity = [item for item in items if item.gate_class is GateClass.V]
    file_wide = [item for item in integrity
                 if not item.entry_ids or not set(item.entry_ids) <= scoped]
    if not authorized and not file_wide:
        items.append(_integrity("NO_AUTHORIZED_ROWS", _AUTHORITY_BOUNDARY,
                                detail="the template authorizes no blank row"))
    if not file_valid and not file_wide:
        items.append(_integrity("FILE_VALIDATION_INCOMPLETE", _INTEGRITY_BOUNDARY,
                                detail="the file to hand over did not pass its own validation"))

    withheld = not file_valid or bool(file_wide) or not authorized
    if withheld:
        delivered: tuple[str, ...] = ()
    else:
        blocked = {eid for item in integrity for eid in item.entry_ids}
        clash = [eid for eid in delivered_in if eid in blocked]
        if clash:
            raise DeliveryStateError(f"DELIVERY_ROW_BLOCKED_BY_INTEGRITY_GATE:{clash}")
        chosen = set(delivered_in)
        delivered = tuple(eid for eid in authorized if eid in chosen)
    unfilled = tuple(eid for eid in authorized if eid not in set(delivered))

    named = {eid for item in items if item.gate_class is GateClass.V for eid in item.entry_ids}
    unexplained = tuple(eid for eid in unfilled if eid not in named)
    if unexplained and not withheld:
        items.append(_integrity("UNFILLED_AUTHORIZED_ROWS", _R28, unexplained,
                                detail="authorized blank rows with no delivered lineup"))

    if not delivered:
        state = DeliveryState.NO_DELIVERABLE
    elif unfilled or unresolved:
        state = DeliveryState.DELIVERABLE_PARTIAL
    else:
        state = DeliveryState.DELIVERABLE
    return DeliveryTruth(DELIVERY_STATE=state, delivered_file_valid=file_valid,
                         delivery_limitations=tuple(items),
                         delivered_entry_ids=delivered, unfilled_entry_ids=unfilled,
                         preserved_entry_ids=preserved, unresolved_entry_ids=unresolved)


def release_truths_v2(policy: ReleasePolicyResult, delivery: DeliveryTruth) -> ReleaseTruthsV2:
    """The five truths side by side (`nfl_release_truths_v2`). Neither half moves the other.

    v2 cannot hold a preserved or unresolved row; a template with one needs v3.
    """

    if delivery.preserved_entry_ids or delivery.unresolved_entry_ids:
        raise DeliveryStateError("nfl_release_truths_v2 cannot hold a preserved or unresolved row; use v3")
    return ReleaseTruthsV2(
        FILE_VALID=policy.file_valid,
        EVIDENCE_STATE=policy.evidence_state,
        MODEL_STATUS=policy.model_status,
        RELEASE_DECISION=policy.release_decision,
        DELIVERY_STATE=delivery.delivery_state,
        delivered_file_valid=delivery.delivered_file_valid,
        delivery_limitations=delivery.delivery_limitations,
        delivered_entry_ids=delivery.delivered_entry_ids,
        unfilled_entry_ids=delivery.unfilled_entry_ids,
    )


def release_truths_v3(policy: ReleasePolicyResult, delivery: DeliveryTruth) -> ReleaseTruthsV3:
    """The five truths with every row's outcome (`nfl_release_truths_v3`, Session 11)."""

    return ReleaseTruthsV3(
        FILE_VALID=policy.file_valid,
        EVIDENCE_STATE=policy.evidence_state,
        MODEL_STATUS=policy.model_status,
        RELEASE_DECISION=policy.release_decision,
        DELIVERY_STATE=delivery.delivery_state,
        delivered_file_valid=delivery.delivered_file_valid,
        delivery_limitations=delivery.delivery_limitations,
        delivered_entry_ids=delivery.delivered_entry_ids,
        unfilled_entry_ids=delivery.unfilled_entry_ids,
        preserved_entry_ids=delivery.preserved_entry_ids,
        unresolved_entry_ids=delivery.unresolved_entry_ids,
    )
