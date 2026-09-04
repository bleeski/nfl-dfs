from __future__ import annotations

import json
import math
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping

from .contracts import (
    CertificationBasis,
    CertificationManifest,
    EvidenceRecord,
    EvidenceState,
    Lineup,
    ModelStatus,
    SlateContract,
)
from .dk import EntryTemplate, parse_entry_bytes, reconcile_template
from .hashing import sha256_bytes, sha256_file
from .lineups import validate_lineup, write_upload_bytes
from .referee import audit_output_bytes
from .release import aggregate_evidence_state, derive_release_policy


class CertificationError(RuntimeError):
    pass


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def certify_upload(
    *,
    run_id: str,
    slate: SlateContract,
    template: EntryTemplate,
    assignments: Mapping[str, tuple[str, ...]],
    evidence: Iterable[EvidenceRecord],
    output_path: str | Path,
    manifest_path: str | Path,
    config_hashes: Mapping[str, str] | None = None,
    model_hashes: Mapping[str, str] | None = None,
    additional_input_hashes: Mapping[str, str] | None = None,
    solver_proof: Mapping[str, object] | None = None,
    model_status: ModelStatus = ModelStatus.UNVALIDATED,
    certification_basis: CertificationBasis = CertificationBasis.MANUAL_GUARDRAIL,
    additional_file_blockers: Iterable[str] = (),
    additional_blockers: Iterable[str] = (),
    deadline_seconds: float = 120.0,
    required_hard_fields: tuple[str, ...] = (
        "salary_pool",
        "entry_authorization",
        "payout_contract",
        "official_inactive_status",
        "weather_if_required",
        "market_line",
    ),
) -> CertificationManifest:
    started = time.perf_counter()
    output = Path(output_path).resolve()
    manifest_file = Path(manifest_path).resolve()
    if output == manifest_file:
        raise CertificationError("output CSV and manifest paths must be different")
    if not math.isfinite(deadline_seconds) or deadline_seconds <= 0:
        raise CertificationError("certification deadline must be positive and finite")
    if output.exists() or manifest_file.exists():
        raise CertificationError(
            "certification artifacts already exist; use a new immutable run_id"
        )
    evidence_tuple = tuple(evidence)
    file_blockers: list[str] = list(additional_file_blockers)
    safety_blockers: list[str] = list(additional_blockers)
    validated: dict[str, Lineup] = {}
    try:
        reconcile_template(template, slate)
    except ValueError as exc:
        file_blockers.append(f"TEMPLATE_MISMATCH:{exc}")
    if sha256_file(template.path) != template.raw_hash:
        file_blockers.append("ENTRY_TEMPLATE_BYTES_CHANGED_AFTER_PARSE")
    authorized = {entry.entry_id for entry in template.authorizations}
    contest_ids = {entry.contest_id for entry in template.authorizations}
    entry_fees = {entry.entry_fee for entry in template.authorizations}
    if len(contest_ids) != 1:
        file_blockers.append(
            "MULTI_CONTEST_ENTRY_FILE_UNSUPPORTED:reserved entries must share one Contest ID"
        )
    if len(entry_fees) != 1:
        file_blockers.append(
            "MIXED_ENTRY_FEES_UNSUPPORTED:reserved entries must share one entry fee"
        )
    if set(assignments) != authorized:
        file_blockers.append("ENTRY_AUTHORIZATION_MISMATCH")
    for entry_id, roster in assignments.items():
        result = validate_lineup(slate, roster)
        if not result.valid:
            file_blockers.extend(
                f"LINEUP_{entry_id}:{problem}" for problem in result.errors
            )
        elif result.lineup is not None:
            validated[entry_id] = result.lineup
    if len({lineup.canonical_key for lineup in validated.values()}) != len(validated):
        file_blockers.append("DUPLICATE_SELECTED_LINEUPS")

    output_bytes: bytes | None = None
    proposed_hash: str | None = None
    if not file_blockers:
        try:
            output_bytes = write_upload_bytes(template, assignments)
            byte_audit = audit_output_bytes(
                template.path, output_bytes, template, assignments
            )
            if not byte_audit.valid:
                file_blockers.extend(
                    f"FINAL_BYTE_AUDIT:{problem}" for problem in byte_audit.problems
                )
            else:
                reparsed = parse_entry_bytes(
                    output_bytes, source_name=str(output)
                )
                reconcile_template(reparsed, slate)
                reparsed_assignments = {
                    entry.entry_id: entry.existing_cells
                    for entry in reparsed.authorizations
                }
                if reparsed_assignments != dict(assignments):
                    file_blockers.append("FINAL_REPARSE_ASSIGNMENT_MISMATCH")
                else:
                    proposed_hash = sha256_bytes(output_bytes)
        except Exception as exc:
            file_blockers.append(
                f"FILE_CONSTRUCTION_FAILED:{type(exc).__name__}:{exc}"
            )
    file_valid = not file_blockers and output_bytes is not None and proposed_hash is not None
    if file_valid:
        evidence_tuple = evidence_tuple + (
            EvidenceRecord(
                subject=run_id,
                field="final_bytes",
                value=proposed_hash,
                source_artifact_id=proposed_hash,
                hard_gate=True,
                state=EvidenceState.PASS,
                reason="in-memory byte audit, reparse, and SHA-256 matched the authorized assignments",
            ),
        )
    elapsed = time.perf_counter() - started
    if elapsed > deadline_seconds:
        safety_blockers.append(f"CERTIFICATION_DEADLINE_EXCEEDED:{elapsed:.3f}s")
    evidence_state, evidence_blockers = aggregate_evidence_state(
        evidence_tuple,
        required_hard_fields=required_hard_fields,
        final_release=True,
    )
    policy = derive_release_policy(
        file_valid=file_valid,
        evidence_state=evidence_state,
        model_status=model_status,
        certification_basis=certification_basis,
        file_blockers=file_blockers,
        evidence_blockers=evidence_blockers,
        safety_blockers=safety_blockers,
    )
    output_path_value: str | None = None
    output_hash: str | None = None
    if policy.release_decision.value == "CERTIFIED_UPLOAD_PACKAGE":
        assert output_bytes is not None and proposed_hash is not None
        try:
            _atomic_write(output, output_bytes)
            if sha256_file(output) != proposed_hash:
                raise CertificationError("post-write SHA-256 does not match proposed bytes")
            output_path_value = str(output)
            output_hash = proposed_hash
        except Exception as exc:
            output.unlink(missing_ok=True)
            file_blockers.append(f"POST_WRITE_HASH_OR_IO_FAILURE:{type(exc).__name__}:{exc}")
            file_valid = False
            policy = derive_release_policy(
                file_valid=False,
                evidence_state=evidence_state,
                model_status=model_status,
                certification_basis=certification_basis,
                file_blockers=file_blockers,
                evidence_blockers=evidence_blockers,
                safety_blockers=safety_blockers,
            )
    evidence_hashes: dict[str, str] = {}
    for index, record in enumerate(evidence_tuple, start=1):
        if record.source_artifact_id:
            evidence_hashes[
                f"evidence:{record.subject}:{record.field}:{index}"
            ] = record.source_artifact_id
    manifest = CertificationManifest(
        run_id=run_id,
        status=policy.status,
        file_valid=policy.file_valid,
        evidence_state=policy.evidence_state,
        model_status=policy.model_status,
        release_decision=policy.release_decision,
        certification_basis=policy.certification_basis,
        created_at=datetime.now(timezone.utc),
        input_hashes={
            "salary": slate.salary_hash,
            "entries": template.raw_hash,
            **dict(additional_input_hashes or {}),
            **evidence_hashes,
        },
        config_hashes=dict(config_hashes or {}),
        model_hashes=dict(model_hashes or {}),
        output_path=output_path_value,
        output_sha256=output_hash,
        proposed_output_sha256=proposed_hash,
        proposed_output_byte_count=(len(output_bytes) if output_bytes is not None else None),
        evidence=evidence_tuple,
        solver_proof=dict(solver_proof or {}),
        runtime={"certification_seconds": elapsed},
        file_blockers=policy.file_blockers,
        evidence_blockers=policy.evidence_blockers,
        model_blockers=policy.model_blockers,
        blockers=policy.blockers,
    )
    manifest_bytes = json.dumps(
        manifest.model_dump(mode="json", by_alias=True), indent=2, sort_keys=True
    ).encode("utf-8") + b"\n"
    try:
        _atomic_write(manifest_file, manifest_bytes)
    except Exception:
        if output_path_value is not None:
            output.unlink(missing_ok=True)
        raise
    return manifest
