from __future__ import annotations

import json
import math
import os
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping

from pydantic import ValidationError

from .contracts import (
    CertificationManifest,
    EvidenceRecord,
    EvidenceState,
    LateSwapManifest,
    Lineup,
    SlateContract,
)
from .dk import EntryTemplate, parse_entries, parse_entry_bytes, parse_salaries, reconcile_template
from .evidence import (
    evaluate_hard_gates,
    late_swap_eligibility_evidence,
    team_inactive_report_evidence,
)
from .hashing import sha256_bytes, sha256_file
from .lineups import (
    LateSwapAuthorization,
    assignment_hash,
    read_assignment_csv,
    validate_lineup,
    write_late_swap_bytes,
)
from .referee import audit_late_swap_output_bytes


@dataclass(frozen=True)
class LateSwapAudit:
    valid: bool
    problems: tuple[str, ...]


@dataclass(frozen=True)
class DerivedLateSwapAuthorization:
    authorization: LateSwapAuthorization | None
    problems: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return self.authorization is not None and not self.problems


class LateSwapRunError(RuntimeError):
    pass


def _unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _portfolio_problems(
    label: str,
    slate: SlateContract,
    assignments: Mapping[str, tuple[str, ...]],
    *,
    locked_slots_by_entry: Mapping[str, Mapping[int, str]] | None = None,
) -> tuple[list[str], dict[str, Lineup]]:
    problems: list[str] = []
    validated: dict[str, Lineup] = {}
    for entry_id, roster in assignments.items():
        result = validate_lineup(
            slate,
            roster,
            locked_slots=(locked_slots_by_entry or {}).get(entry_id),
        )
        if not result.valid:
            problems.extend(
                f"{label}_{entry_id}:{problem}" for problem in result.errors
            )
        elif result.lineup is not None:
            validated[entry_id] = result.lineup
    canonical = [lineup.canonical_key for lineup in validated.values()]
    if len(set(canonical)) != len(canonical):
        problems.append(f"{label}:duplicate lineups are not permitted")
    return problems, validated


def derive_late_swap_authorization(
    *,
    slate: SlateContract,
    original: Mapping[str, tuple[str, ...]],
    current: Mapping[str, tuple[str, ...]],
    proposed: Mapping[str, tuple[str, ...]],
    as_of: datetime,
    current_template_sha256: str,
    prior_assignment_sha256: str,
) -> DerivedLateSwapAuthorization:
    if as_of.tzinfo is None:
        return DerivedLateSwapAuthorization(None, ("as_of must be timezone-aware",))
    problems: list[str] = []
    if set(original) != set(current) or set(original) != set(proposed):
        problems.append("Entry-ID set changed")
        return DerivedLateSwapAuthorization(None, tuple(problems))
    by_id = {player.dk_id: player for player in slate.players}
    replaceable: list[tuple[str, tuple[int, ...]]] = []
    locked_by_entry: dict[str, dict[int, str]] = {}
    for entry_id in sorted(original):
        before = original[entry_id]
        present = current[entry_id]
        after = proposed[entry_id]
        if len({len(before), len(present), len(after)}) != 1:
            problems.append(f"{entry_id}: roster width changed")
            continue
        locked: dict[int, str] = {}
        changed: list[int] = []
        for slot, (before_id, current_id, after_id) in enumerate(
            zip(before, present, after, strict=True)
        ):
            values = {
                "prior": (before_id, by_id.get(before_id)),
                "current": (current_id, by_id.get(current_id)),
                "proposed": (after_id, by_id.get(after_id)),
            }
            for state, (dk_id, player) in values.items():
                if player is None:
                    problems.append(
                        f"{entry_id}: {state} ID {dk_id} is missing from the current salary pool"
                    )
            prior_player = values["prior"][1]
            current_player = values["current"][1]
            proposed_player = values["proposed"][1]
            prior_locked = prior_player is not None and prior_player.lock_at <= as_of
            current_locked = current_player is not None and current_player.lock_at <= as_of
            proposed_locked = proposed_player is not None and proposed_player.lock_at <= as_of
            if prior_locked:
                locked[slot] = before_id
                if current_id != before_id:
                    problems.append(
                        f"{entry_id}: locked prior player {before_id} was removed or moved from slot {slot + 1}"
                    )
                if after_id != before_id:
                    problems.append(
                        f"{entry_id}: locked prior player {before_id} cannot change in slot {slot + 1}"
                    )
            if current_locked and current_id != before_id:
                problems.append(
                    f"{entry_id}: locked player {current_id} was added or moved into slot {slot + 1}"
                )
            if proposed_locked and after_id != before_id:
                problems.append(
                    f"{entry_id}: slot {slot + 1} cannot add already-locked player {after_id}"
                )
            if current_id != after_id:
                if prior_locked or current_locked or proposed_locked:
                    continue
                changed.append(slot)
        locked_by_entry[entry_id] = locked
        replaceable.append((entry_id, tuple(changed)))

    for label, values in (("PRIOR", original), ("CURRENT", current)):
        portfolio_problems, _ = _portfolio_problems(
            label,
            slate,
            values,
            locked_slots_by_entry=locked_by_entry,
        )
        problems.extend(portfolio_problems)
    proposed_problems, _ = _portfolio_problems(
        "PROPOSED",
        slate,
        proposed,
        locked_slots_by_entry=locked_by_entry,
    )
    problems.extend(proposed_problems)
    if problems:
        return DerivedLateSwapAuthorization(None, tuple(_unique(problems)))
    return DerivedLateSwapAuthorization(
        LateSwapAuthorization(
            current_template_sha256=current_template_sha256,
            prior_assignment_sha256=prior_assignment_sha256,
            as_of=as_of.isoformat(),
            replaceable_cells=tuple(replaceable),
        ),
        (),
    )


def audit_late_swap(
    *,
    slate: SlateContract,
    original: Mapping[str, tuple[str, ...]],
    proposed: Mapping[str, tuple[str, ...]],
    now: datetime,
) -> LateSwapAudit:
    derived = derive_late_swap_authorization(
        slate=slate,
        original=original,
        current=original,
        proposed=proposed,
        as_of=now,
        current_template_sha256=slate.salary_hash,
        prior_assignment_sha256=assignment_hash(original),
    )
    return LateSwapAudit(derived.valid, derived.problems)


def _atomic_write_new(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(path)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _evidence_matches_hash(
    manifest: CertificationManifest,
    *,
    field: str,
    digest: str,
) -> bool:
    return any(
        record.field == field
        and record.state is EvidenceState.PASS
        and record.source_artifact_id == digest
        for record in manifest.evidence
    )


def _validate_prior_manifest(
    manifest: CertificationManifest,
    *,
    slate: SlateContract,
    prior_assignment_file_sha256: str,
    as_of: datetime,
) -> tuple[list[str], Path | None]:
    problems: list[str] = []
    if manifest.status != "CERTIFIED":
        problems.append("PRIOR_MANIFEST_NOT_CERTIFIED")
    if manifest.created_at.tzinfo is None:
        problems.append("PRIOR_MANIFEST_CREATED_AT_NOT_TIMEZONE_AWARE")
    elif manifest.created_at > as_of:
        problems.append("PRIOR_MANIFEST_CREATED_AFTER_LATE_SWAP_AS_OF")
    if manifest.blockers:
        problems.append("PRIOR_CERTIFIED_MANIFEST_HAS_BLOCKERS")
    nonfinal_hard_evidence = sorted(
        {
            record.field
            for record in manifest.evidence
            if record.hard_gate
            and record.state not in {EvidenceState.PASS, EvidenceState.NOT_APPLICABLE}
        }
    )
    if nonfinal_hard_evidence:
        problems.append(
            f"PRIOR_MANIFEST_HARD_EVIDENCE_NOT_FINAL:{nonfinal_hard_evidence}"
        )
    required = {"salary", "entries", "assignments"}
    missing = sorted(required.difference(manifest.input_hashes))
    if missing:
        problems.append(f"PRIOR_MANIFEST_HASHES_MISSING:{missing}")
    for key in sorted(required.intersection(manifest.input_hashes)):
        digest = manifest.input_hashes[key]
        if len(digest) != 64 or any(
            character not in "0123456789abcdef" for character in digest
        ):
            problems.append(f"PRIOR_MANIFEST_HASH_INVALID:{key}")
    if manifest.input_hashes.get("salary") != slate.salary_hash:
        problems.append("PRIOR_MANIFEST_SALARY_HASH_MISMATCH")
    if manifest.input_hashes.get("assignments") != prior_assignment_file_sha256:
        problems.append("PRIOR_ASSIGNMENT_HASH_MISMATCH")
    prior_template_hash = manifest.input_hashes.get("entries")
    if prior_template_hash and not _evidence_matches_hash(
        manifest,
        field="entry_authorization",
        digest=prior_template_hash,
    ):
        problems.append("PRIOR_TEMPLATE_HASH_EVIDENCE_MISMATCH")
    if not _evidence_matches_hash(
        manifest,
        field="salary_pool",
        digest=slate.salary_hash,
    ):
        problems.append("PRIOR_SALARY_HASH_EVIDENCE_MISMATCH")
    output_path: Path | None = None
    if not manifest.output_path or not manifest.output_sha256:
        problems.append("PRIOR_CERTIFIED_OUTPUT_BINDING_MISSING")
    else:
        if len(manifest.output_sha256) != 64 or any(
            character not in "0123456789abcdef"
            for character in manifest.output_sha256
        ):
            problems.append("PRIOR_CERTIFIED_OUTPUT_HASH_INVALID")
        candidate = Path(manifest.output_path)
        if not candidate.is_absolute():
            problems.append("PRIOR_CERTIFIED_OUTPUT_PATH_NOT_ABSOLUTE")
        else:
            output_path = candidate.resolve()
            if not output_path.is_file():
                problems.append("PRIOR_CERTIFIED_OUTPUT_MISSING")
            elif sha256_file(output_path) != manifest.output_sha256:
                problems.append("PRIOR_CERTIFIED_OUTPUT_HASH_MISMATCH")
        if not any(
            record.field == "final_bytes"
            and record.state is EvidenceState.PASS
            and record.value == manifest.output_sha256
            for record in manifest.evidence
        ):
            problems.append("PRIOR_FINAL_BYTE_EVIDENCE_MISMATCH")
    return problems, output_path


def govern_late_swap(
    *,
    run_id: str,
    salaries_path: str | Path,
    current_entries_path: str | Path,
    prior_manifest_path: str | Path,
    prior_assignments_path: str | Path,
    proposed_assignments_path: str | Path,
    eligibility_evidence_path: str | Path,
    inactive_reports_path: str | Path,
    output_directory: str | Path,
    as_of: datetime,
    deadline_seconds: float = 120.0,
) -> tuple[LateSwapManifest, Path]:
    if as_of.tzinfo is None:
        raise LateSwapRunError("--as-of must include a timezone")
    if not math.isfinite(deadline_seconds) or deadline_seconds <= 0:
        raise LateSwapRunError("late-swap deadline must be positive and finite")
    started = time.perf_counter()
    run_directory = Path(output_directory).resolve() / run_id
    try:
        run_directory.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise LateSwapRunError(
            "run_id already exists and immutable late-swap artifacts will not be "
            f"overwritten: {run_id}"
        ) from exc
    output_path = run_directory / f"DK_UPLOAD_{run_id}.csv"
    manifest_path = run_directory / f"late_swap_{run_id}.manifest.json"
    diagnostic_path = run_directory / "late_swap_diagnostic.json"
    paths = {
        "salary": Path(salaries_path).resolve(),
        "current_entries": Path(current_entries_path).resolve(),
        "prior_manifest": Path(prior_manifest_path).resolve(),
        "prior_assignments": Path(prior_assignments_path).resolve(),
        "proposed_assignments": Path(proposed_assignments_path).resolve(),
        "eligibility_evidence": Path(eligibility_evidence_path).resolve(),
        "inactive_reports": Path(inactive_reports_path).resolve(),
    }
    input_hashes: dict[str, str] = {}
    blockers: list[str] = []
    for name, path in paths.items():
        try:
            input_hashes[name] = sha256_file(path)
        except OSError as exc:
            blockers.append(f"MISSING_OR_UNREADABLE_INPUT:{name}:{exc}")

    slate: SlateContract | None = None
    current_template: EntryTemplate | None = None
    prior_manifest: CertificationManifest | None = None
    prior_assignments: dict[str, tuple[str, ...]] | None = None
    proposed_assignments: dict[str, tuple[str, ...]] | None = None
    current_assignments: dict[str, tuple[str, ...]] | None = None
    prior_output_path: Path | None = None
    authorization: LateSwapAuthorization | None = None
    evidence: list[EvidenceRecord] = []
    contest_id: str | None = None
    try:
        if "salary" in input_hashes:
            try:
                slate = parse_salaries(paths["salary"])
            except Exception as exc:
                blockers.append(f"SALARY_CONTRACT_INVALID:{exc}")
        if "current_entries" in input_hashes:
            try:
                current_template = parse_entries(paths["current_entries"])
                current_assignments = {
                    entry.entry_id: entry.existing_cells
                    for entry in current_template.authorizations
                }
                if any(
                    not cell
                    for entry in current_template.authorizations
                    for cell in entry.existing_cells
                ):
                    blockers.append("CURRENT_TEMPLATE_MUST_BE_FULLY_PREFILLED")
                contest_ids = {
                    entry.contest_id for entry in current_template.authorizations
                }
                if len(contest_ids) != 1:
                    blockers.append("CURRENT_TEMPLATE_MUST_CONTAIN_ONE_CONTEST_ID")
                else:
                    contest_id = next(iter(contest_ids))
            except Exception as exc:
                blockers.append(f"CURRENT_TEMPLATE_INVALID:{exc}")
        if "prior_manifest" in input_hashes:
            try:
                prior_manifest = CertificationManifest.model_validate_json(
                    paths["prior_manifest"].read_text(encoding="utf-8")
                )
            except (OSError, ValidationError, ValueError) as exc:
                blockers.append(f"PRIOR_MANIFEST_INVALID:{exc}")
        if slate is not None and "prior_assignments" in input_hashes:
            try:
                prior_assignments = read_assignment_csv(
                    paths["prior_assignments"], slate.mode
                )
            except Exception as exc:
                blockers.append(f"PRIOR_ASSIGNMENT_CONTRACT_INVALID:{exc}")
        if slate is not None and "proposed_assignments" in input_hashes:
            try:
                proposed_assignments = read_assignment_csv(
                    paths["proposed_assignments"], slate.mode
                )
            except Exception as exc:
                blockers.append(f"PROPOSED_ASSIGNMENT_CONTRACT_INVALID:{exc}")
        if slate is not None and current_template is not None:
            try:
                reconcile_template(current_template, slate)
            except ValueError as exc:
                blockers.append(f"CURRENT_TEMPLATE_MODE_MISMATCH:{exc}")

        if (
            prior_manifest is not None
            and slate is not None
            and "prior_assignments" in input_hashes
        ):
            prior_problems, prior_output_path = _validate_prior_manifest(
                prior_manifest,
                slate=slate,
                prior_assignment_file_sha256=input_hashes["prior_assignments"],
                as_of=as_of,
            )
            blockers.extend(prior_problems)
        if (
            prior_output_path is not None
            and slate is not None
            and prior_assignments is not None
        ):
            try:
                prior_output = parse_entries(prior_output_path)
                reconcile_template(prior_output, slate)
                prior_output_assignments = {
                    entry.entry_id: entry.existing_cells
                    for entry in prior_output.authorizations
                }
                if prior_output_assignments != prior_assignments:
                    blockers.append("PRIOR_CERTIFIED_OUTPUT_ASSIGNMENT_MISMATCH")
                prior_contests = {
                    entry.contest_id for entry in prior_output.authorizations
                }
                if contest_id is not None and prior_contests != {contest_id}:
                    blockers.append("CURRENT_CONTEST_ID_DIFFERS_FROM_CERTIFIED_PRIOR")
            except Exception as exc:
                blockers.append(f"PRIOR_CERTIFIED_OUTPUT_INVALID:{exc}")

        if (
            slate is not None
            and current_template is not None
            and current_assignments is not None
            and prior_assignments is not None
            and proposed_assignments is not None
            and "prior_assignments" in input_hashes
        ):
            derived = derive_late_swap_authorization(
                slate=slate,
                original=prior_assignments,
                current=current_assignments,
                proposed=proposed_assignments,
                as_of=as_of,
                current_template_sha256=current_template.raw_hash,
                prior_assignment_sha256=input_hashes["prior_assignments"],
            )
            blockers.extend(derived.problems)
            authorization = derived.authorization

        prior_state_ok = (
            prior_manifest is not None
            and prior_assignments is not None
            and prior_output_path is not None
            and "prior_manifest" in input_hashes
            and "prior_assignments" in input_hashes
            and not any(blocker.startswith("PRIOR_") for blocker in blockers)
        )
        evidence.append(
            EvidenceRecord(
                subject=prior_manifest.run_id if prior_manifest else "prior_run",
                field="prior_state_binding",
                value={
                    "prior_assignment_contract_sha256": (
                        assignment_hash(prior_assignments)
                        if prior_assignments is not None
                        else None
                    ),
                    "prior_template_sha256": (
                        prior_manifest.input_hashes.get("entries")
                        if prior_manifest is not None
                        else None
                    ),
                },
                source_artifact_id=input_hashes.get("prior_manifest"),
                hard_gate=True,
                state=EvidenceState.PASS if prior_state_ok else EvidenceState.FAIL,
                reason=(
                    "prior certified manifest, assignment, template hash, salary, and output agree"
                    if prior_state_ok
                    else "prior certified state is missing, invalid, or inconsistent"
                ),
            )
        )
        evidence.append(
            EvidenceRecord(
                subject="selected_portfolio",
                field="locked_cells_match_prior",
                value=(
                    {
                        entry_id: list(indexes)
                        for entry_id, indexes in authorization.replaceable_cells
                    }
                    if authorization is not None
                    else None
                ),
                source_artifact_id=input_hashes.get("prior_assignments"),
                hard_gate=True,
                state=(
                    EvidenceState.PASS
                    if authorization is not None
                    else EvidenceState.FAIL
                ),
                reason=(
                    "replaceable cells were derived from exact IDs and lock times; locked cells match the certified prior"
                    if authorization is not None
                    else "locked-cell agreement or lock-derived replacement authorization failed"
                ),
            )
        )

        if contest_id is None:
            eligibility = EvidenceRecord(
                subject="contest",
                field="contest_late_swap_eligibility",
                hard_gate=True,
                state=EvidenceState.UNKNOWN,
                reason="the exact Contest ID could not be established",
            )
        else:
            eligibility = late_swap_eligibility_evidence(
                paths["eligibility_evidence"]
                if "eligibility_evidence" in input_hashes
                else None,
                contest_id=contest_id,
                as_of=as_of,
            )
        evidence.append(eligibility)

        unlocked_selected: set[str] = set()
        if slate is not None and proposed_assignments is not None:
            by_id = {player.dk_id: player for player in slate.players}
            unlocked_selected = {
                dk_id
                for roster in proposed_assignments.values()
                for dk_id in roster
                if dk_id in by_id and by_id[dk_id].lock_at > as_of
            }
            inactive = team_inactive_report_evidence(
                paths["inactive_reports"]
                if "inactive_reports" in input_hashes
                else None,
                slate=slate,
                selected_dk_ids=unlocked_selected,
                as_of=as_of,
            )
        else:
            inactive = EvidenceRecord(
                subject="selected_unlocked_portfolio",
                field="official_inactive_status",
                hard_gate=True,
                state=EvidenceState.UNKNOWN,
                reason="the selected unlocked portfolio could not be established",
            )
        evidence.append(inactive)
        gates_pass, gate_blockers = evaluate_hard_gates(
            evidence,
            now=as_of,
            final_release=True,
        )
        if not gates_pass:
            blockers.extend(gate_blockers)

        output_bytes: bytes | None = None
        output_hash: str | None = None
        if (
            not blockers
            and slate is not None
            and current_template is not None
            and proposed_assignments is not None
            and authorization is not None
        ):
            output_bytes = write_late_swap_bytes(
                current_template,
                proposed_assignments,
                authorization,
            )
            byte_audit = audit_late_swap_output_bytes(
                current_template.path,
                output_bytes,
                current_template,
                proposed_assignments,
                authorization,
            )
            if not byte_audit.valid:
                blockers.extend(
                    f"FINAL_BYTE_AUDIT:{problem}" for problem in byte_audit.problems
                )
            else:
                reparsed = parse_entry_bytes(
                    output_bytes,
                    source_name=str(output_path),
                )
                reconcile_template(reparsed, slate)
                reparsed_assignments = {
                    entry.entry_id: entry.existing_cells
                    for entry in reparsed.authorizations
                }
                if reparsed_assignments != proposed_assignments:
                    blockers.append("FINAL_REPARSE_ASSIGNMENT_MISMATCH")
                output_hash = sha256_bytes(output_bytes)

        for name, path in paths.items():
            if name not in input_hashes:
                continue
            try:
                if sha256_file(path) != input_hashes[name]:
                    blockers.append(f"INPUT_CHANGED_DURING_LATE_SWAP:{name}")
            except OSError as exc:
                blockers.append(f"INPUT_CHANGED_DURING_LATE_SWAP:{name}:{exc}")
        if (
            prior_output_path is not None
            and prior_manifest is not None
            and prior_manifest.output_sha256 is not None
        ):
            try:
                if sha256_file(prior_output_path) != prior_manifest.output_sha256:
                    blockers.append("PRIOR_OUTPUT_CHANGED_DURING_LATE_SWAP")
            except OSError as exc:
                blockers.append(f"PRIOR_OUTPUT_CHANGED_DURING_LATE_SWAP:{exc}")
        elapsed = time.perf_counter() - started
        if elapsed > deadline_seconds:
            blockers.append(f"LATE_SWAP_DEADLINE_EXCEEDED:{elapsed:.3f}s")
        blockers = _unique(blockers)

        created_output = False
        if not blockers and output_bytes is not None and output_hash is not None:
            try:
                _atomic_write_new(output_path, output_bytes)
                created_output = True
                if sha256_file(output_path) != output_hash:
                    output_path.unlink(missing_ok=True)
                    created_output = False
                    blockers.append("POST_WRITE_HASH_MISMATCH")
            except Exception as exc:
                blockers.append(f"OUTPUT_WRITE_FAILED:{exc}")
        status = "CERTIFIED" if created_output and not blockers else "DO_NOT_UPLOAD"
        if status == "CERTIFIED":
            evidence.append(
                EvidenceRecord(
                    subject=run_id,
                    field="final_bytes",
                    value=output_hash,
                    source_artifact_id=output_hash,
                    hard_gate=True,
                    state=EvidenceState.PASS,
                    reason="independent late-swap byte audit, reparse, and post-write SHA-256 matched",
                )
            )
        elif created_output:
            output_path.unlink(missing_ok=True)
            created_output = False
        next_action = (
            "Review the manifest and exact Entry IDs, then manually upload in DraftKings only if you choose."
            if status == "CERTIFIED"
            else f"Resolve {blockers[0] if blockers else 'the reported blocker'} and rerun with a new run ID."
        )
        manifest = LateSwapManifest(
            run_id=run_id,
            prior_run_id=prior_manifest.run_id if prior_manifest else None,
            status=status,
            created_at=datetime.now(timezone.utc),
            as_of=as_of,
            contest_id=contest_id,
            input_hashes=input_hashes,
            replaceable_cells=(
                {
                    entry_id: indexes
                    for entry_id, indexes in authorization.replaceable_cells
                }
                if authorization is not None
                else {}
            ),
            output_path=str(output_path) if status == "CERTIFIED" else None,
            output_sha256=output_hash if status == "CERTIFIED" else None,
            evidence=tuple(evidence),
            blockers=tuple(blockers),
            next_action=next_action,
            runtime={"late_swap_seconds": time.perf_counter() - started},
        )
        manifest_bytes = json.dumps(
            manifest.model_dump(mode="json"), indent=2, sort_keys=True
        ).encode("utf-8") + b"\n"
        try:
            _atomic_write_new(manifest_path, manifest_bytes)
        except Exception:
            if created_output:
                output_path.unlink(missing_ok=True)
            raise
        return manifest, manifest_path
    except Exception as exc:
        if manifest_path.exists():
            raise
        blockers = _unique(
            [*blockers, f"LATE_SWAP_VALIDATION_FAILED:{type(exc).__name__}:{exc}"]
        )
        diagnostic = {
            "run_id": run_id,
            "status": "DO_NOT_UPLOAD",
            "error": type(exc).__name__,
            "message": str(exc),
        }
        try:
            _atomic_write_new(
                diagnostic_path,
                json.dumps(diagnostic, indent=2, sort_keys=True).encode("utf-8") + b"\n",
            )
        except Exception:
            pass
        manifest = LateSwapManifest(
            run_id=run_id,
            prior_run_id=prior_manifest.run_id if prior_manifest else None,
            status="DO_NOT_UPLOAD",
            created_at=datetime.now(timezone.utc),
            as_of=as_of,
            contest_id=contest_id,
            input_hashes=input_hashes,
            evidence=tuple(evidence),
            blockers=tuple(blockers),
            next_action=f"Resolve {blockers[0]} and rerun with a new run ID.",
            runtime={"late_swap_seconds": time.perf_counter() - started},
        )
        manifest_bytes = json.dumps(
            manifest.model_dump(mode="json"), indent=2, sort_keys=True
        ).encode("utf-8") + b"\n"
        _atomic_write_new(manifest_path, manifest_bytes)
        return manifest, manifest_path
