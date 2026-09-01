from __future__ import annotations

import json
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping

from .contracts import (
    CertificationManifest,
    EvidenceRecord,
    EvidenceState,
    Lineup,
    SlateContract,
)
from .dk import EntryTemplate, reconcile_template
from .evidence import evaluate_hard_gates
from .hashing import sha256_bytes, sha256_file
from .lineups import validate_lineup, write_upload_bytes
from .referee import audit_output_bytes


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
    evidence_tuple = tuple(evidence)
    blockers: list[str] = []
    evidence_fields = {record.field for record in evidence_tuple if record.hard_gate}
    for required_field in required_hard_fields:
        if required_field not in evidence_fields:
            blockers.append(f"MISSING_HARD_EVIDENCE:{required_field}")
    validated: dict[str, Lineup] = {}
    try:
        reconcile_template(template, slate)
    except ValueError as exc:
        blockers.append(f"TEMPLATE_MISMATCH:{exc}")
    authorized = {entry.entry_id for entry in template.authorizations}
    if set(assignments) != authorized:
        blockers.append("ENTRY_AUTHORIZATION_MISMATCH")
    for entry_id, roster in assignments.items():
        result = validate_lineup(slate, roster)
        if not result.valid:
            blockers.extend(f"LINEUP_{entry_id}:{problem}" for problem in result.errors)
        elif result.lineup is not None:
            validated[entry_id] = result.lineup
    if len({lineup.canonical_key for lineup in validated.values()}) != len(validated):
        blockers.append("DUPLICATE_SELECTED_LINEUPS")
    gates_pass, gate_blockers = evaluate_hard_gates(evidence_tuple)
    if not gates_pass:
        blockers.extend(gate_blockers)

    output_bytes: bytes | None = None
    output_hash: str | None = None
    if not blockers:
        output_bytes = write_upload_bytes(template, assignments)
        byte_audit = audit_output_bytes(template.path, output_bytes, template, assignments)
        if not byte_audit.valid:
            blockers.extend(f"FINAL_BYTE_AUDIT:{problem}" for problem in byte_audit.problems)
        else:
            output_hash = sha256_bytes(output_bytes)
    elapsed = time.perf_counter() - started
    if elapsed > deadline_seconds:
        blockers.append(f"CERTIFICATION_DEADLINE_EXCEEDED:{elapsed:.3f}s")

    if blockers:
        if output.exists():
            output.unlink()
        status = "DO_NOT_UPLOAD"
        output_path_value = None
        output_hash = None
    else:
        assert output_bytes is not None and output_hash is not None
        _atomic_write(output, output_bytes)
        if sha256_file(output) != output_hash:
            output.unlink(missing_ok=True)
            blockers.append("POST_WRITE_HASH_MISMATCH")
            status = "DO_NOT_UPLOAD"
            output_path_value = None
            output_hash = None
        else:
            status = "CERTIFIED"
            output_path_value = str(output)
            evidence_tuple = evidence_tuple + (
                EvidenceRecord(
                    subject=run_id,
                    field="final_bytes",
                    value=output_hash,
                    hard_gate=True,
                    state=EvidenceState.PASS,
                    reason="independent reparse and post-write SHA-256 matched",
                ),
            )
    evidence_hashes = {
        f"evidence:{record.field}": record.source_artifact_id
        for record in evidence_tuple
        if record.source_artifact_id
    }
    manifest = CertificationManifest(
        run_id=run_id,
        status=status,
        created_at=datetime.now(timezone.utc),
        input_hashes={
            "salary": slate.salary_hash,
            "entries": template.raw_hash,
            **evidence_hashes,
        },
        config_hashes=dict(config_hashes or {}),
        model_hashes=dict(model_hashes or {}),
        output_path=output_path_value,
        output_sha256=output_hash,
        evidence=evidence_tuple,
        solver_proof={},
        runtime={"certification_seconds": elapsed},
        blockers=tuple(blockers),
    )
    manifest_bytes = json.dumps(
        manifest.model_dump(mode="json"), indent=2, sort_keys=True
    ).encode("utf-8") + b"\n"
    _atomic_write(manifest_file, manifest_bytes)
    return manifest
