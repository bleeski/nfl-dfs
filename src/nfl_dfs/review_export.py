"""Legality-and-bytes export of a prior-only review lineup.

`certify` is the certified path and it requires the full payout table,
advertised prize value and field size, because it runs the economics and the
release policy. None of that changes the outcome for a prior-only package: the
model is not prospectively validated, so `certify` ends at `DO_NOT_UPLOAD`
regardless, and the operator has spent an afternoon transcribing a payout table
to learn nothing.

This path separates the two questions. Legality and byte fidelity do not need
contest economics, so they run here in full: exact salary-row identity, one
captain, person uniqueness, salary cap, both teams, an independent byte audit
against the source template, a reparse of the proposed bytes, and a SHA-256.
Economics are simply not consulted, and the release decision is therefore
`DO_NOT_UPLOAD` by construction rather than by failure.

The bulk-entry file this writes is legal and byte-audited. It is not certified,
it carries no EV, ROI, ceiling, ownership or edge claim, and uploading it stays
a manual operator decision.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from .contracts import EngineMode, SlateContract
from .dk import EntryTemplate, parse_entry_bytes, reconcile_template, single_contest_problems
from .hashing import sha256_bytes, sha256_file
from .lineups import validate_lineup, write_upload_bytes
from .referee import audit_output_bytes


EXPORT_VERSION = "prior_only_review_export_v1"


class ReviewExportError(ValueError):
    """A named fail-closed export error."""


@dataclass(frozen=True)
class ReviewExport:
    export_version: str
    output_path: str
    output_sha256: str
    entries: int
    file_valid: bool
    problems: tuple[str, ...]

    def as_report(self, extra: Mapping[str, object] | None = None) -> dict[str, object]:
        return {
            "status": "DO_NOT_UPLOAD",
            "export_version": self.export_version,
            "FILE_VALID": self.file_valid,
            "EVIDENCE_STATE": "UNKNOWN",
            "MODEL_STATUS": "PRIOR_ONLY",
            "RELEASE_DECISION": "DO_NOT_UPLOAD",
            "certification_basis": "NOT_CERTIFIED_REVIEW_EXPORT",
            "bulk_entry_csv": self.output_path if self.file_valid else None,
            "bulk_entry_sha256": self.output_sha256 if self.file_valid else None,
            "entries": self.entries,
            "problems": list(self.problems),
            "checks_run": [
                "TEMPLATE_RECONCILED_TO_SALARY_POOL",
                "SINGLE_CONTEST_AND_ENTRY_FEE",
                "EXACT_SALARY_ROW_IDENTITY_PER_SLOT",
                "ONE_CAPTAIN_AND_FIVE_FLEX",
                "UNDERLYING_PERSON_UNIQUENESS",
                "SALARY_CAP",
                "BOTH_TEAMS_REPRESENTED",
                "INDEPENDENT_BYTE_AUDIT_AGAINST_SOURCE_TEMPLATE",
                "REPARSE_OF_PROPOSED_BYTES",
                "SHA256_OF_PROPOSED_BYTES",
            ],
            "checks_not_run": [
                "PAYOUT_AND_FIELD_ECONOMICS",
                "OWNERSHIP_AND_DUPLICATION",
                "PROSPECTIVE_MODEL_VALIDATION",
                "OFFICIAL_ACTIVITY_EVIDENCE_GATE",
            ],
            "warning": (
                "Legal and byte-audited, not certified. This file carries no EV, ROI,"
                " win probability, cash probability, ceiling, ownership or edge claim."
                " Uploading it to DraftKings remains a manual operator decision."
            ),
            **(dict(extra) if extra else {}),
        }


def export_review_entries(
    *,
    slate: SlateContract,
    template: EntryTemplate,
    assignments: Mapping[str, tuple[str, ...]],
    output_path: str | Path,
) -> ReviewExport:
    """Write the bulk-entry CSV only after legality and the byte audit pass."""

    output = Path(output_path).resolve()
    if output.exists():
        raise ReviewExportError(f"OUTPUT_EXISTS:{output}")

    problems: list[str] = list(single_contest_problems(template))
    if slate.mode is not EngineMode.SHOWDOWN:
        problems.append(f"MODE_NOT_SUPPORTED:{slate.mode.value}")
    try:
        reconcile_template(template, slate)
    except ValueError as exc:
        problems.append(f"TEMPLATE_MISMATCH:{exc}")
    if sha256_file(template.path) != template.raw_hash:
        problems.append("ENTRY_TEMPLATE_BYTES_CHANGED_AFTER_PARSE")

    authorized = {entry.entry_id for entry in template.authorizations}
    if set(assignments) != authorized:
        missing = sorted(authorized.difference(assignments))
        extra = sorted(set(assignments).difference(authorized))
        problems.append(f"ENTRY_AUTHORIZATION_MISMATCH:missing={missing}:extra={extra}")

    validated = {}
    for entry_id, roster in sorted(assignments.items()):
        result = validate_lineup(slate, roster)
        if not result.valid:
            problems.extend(f"LINEUP_{entry_id}:{problem}" for problem in result.errors)
        elif result.lineup is not None:
            validated[entry_id] = result.lineup

    output_bytes: bytes | None = None
    digest = ""
    if not problems:
        try:
            output_bytes = write_upload_bytes(template, assignments)
            audit = audit_output_bytes(
                template.path, output_bytes, template, assignments
            )
            if not audit.valid:
                problems.extend(f"BYTE_AUDIT:{problem}" for problem in audit.problems)
            else:
                reparsed = parse_entry_bytes(output_bytes, source_name=str(output))
                reconcile_template(reparsed, slate)
                reparsed_assignments = {
                    entry.entry_id: entry.existing_cells
                    for entry in reparsed.authorizations
                }
                if reparsed_assignments != dict(assignments):
                    problems.append("REPARSE_ASSIGNMENT_MISMATCH")
                else:
                    digest = sha256_bytes(output_bytes)
        except Exception as exc:  # noqa: BLE001 - reported, never swallowed
            problems.append(f"FILE_CONSTRUCTION_FAILED:{type(exc).__name__}:{exc}")

    file_valid = not problems and output_bytes is not None and bool(digest)
    if file_valid and output_bytes is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_name(output.name + ".tmp")
        temporary.write_bytes(output_bytes)
        temporary.replace(output)
        if sha256_file(output) != digest:
            output.unlink(missing_ok=True)
            raise ReviewExportError("WRITTEN_BYTES_DID_NOT_MATCH_THE_AUDITED_BYTES")

    return ReviewExport(
        export_version=EXPORT_VERSION,
        output_path=str(output),
        output_sha256=digest,
        entries=len(authorized),
        file_valid=file_valid,
        problems=tuple(problems),
    )


def write_assignments_csv(
    path: str | Path, assignments: Mapping[str, tuple[str, ...]]
) -> str:
    """Write the Entry ID,CPT,FLEX... assignments file `certify` also accepts."""

    target = Path(path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    header = "Entry ID,CPT,FLEX,FLEX,FLEX,FLEX,FLEX"
    lines = [header]
    for entry_id, roster in sorted(assignments.items()):
        if len(roster) != 6:
            raise ReviewExportError(f"ASSIGNMENT_WIDTH:{entry_id}:{len(roster)}")
        lines.append(",".join((entry_id, *roster)))
    payload = ("\n".join(lines) + "\n").encode("utf-8")
    temporary = target.with_name(target.name + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(target)
    return sha256_file(target)


def write_run_record(path: str | Path, record: Mapping[str, object]) -> str:
    target = Path(path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        json.dumps(
            {"recorded_at": datetime.now(timezone.utc).isoformat(), **dict(record)},
            indent=2,
            sort_keys=True,
            default=str,
        )
        + "\n"
    ).encode("utf-8")
    temporary = target.with_name(target.name + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(target)
    return sha256_file(target)
