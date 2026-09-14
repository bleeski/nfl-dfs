from __future__ import annotations

import csv
import json
import os
import re
import shutil
import tempfile
import time
import tracemalloc
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from pathlib import Path
from typing import Any, Mapping

from pydantic import ValidationError

from .contracts import (
    SettlementArtifactRequest,
    SettlementBundle,
    SettlementCaptureRequest,
    SettledArtifact,
)
from .dk import parse_entries, parse_salaries, reconcile_template, require_single_contest
from .hashing import canonical_json_bytes, sha256_bytes, sha256_file
from .lineups import assignment_hash, read_assignment_csv, validate_lineup
from .metric_registry import (
    METRIC_REGISTRY_VERSION,
    load_metric_registry,
    require_registry_precedes_evaluation,
)
from .payouts import parse_payout_csv
from .reference_settlement import (
    ReferenceBudget,
    ReferenceFieldEntry,
    ReferenceSettlementResult,
    evaluate_reference_settlement,
)
from .scenario_store import SCENARIO_BANK_VERSION, inspect_scenario_bank


STANDINGS_PARSER_VERSION = "nfl_standings_csv_v2"
SETTLEMENT_REQUEST_VERSION = "nfl_settlement_request_v1"
PRELOCK_MANIFEST_VERSION = "nfl_prelock_run_manifest_v1"
BRIEF_VERSION = "nfl_run_settlement_brief_v1"
BUNDLE_VERSION = "nfl_settlement_bundle_v1"

_FIXED_ARTIFACT_NAMES = {
    "salary": "salary",
    "entries": "entries",
    "payouts": "payouts",
    "assignments": "assignments",
    "prelock_manifest": "prelock_manifest",
    "standings": "standings",
    "metric_registry": "metric_registry",
}
_FIXED_ARTIFACT_VERSIONS = {
    "salary": "dk_salary_csv_v1",
    "entries": "dk_entry_csv_v1",
    "payouts": "nfl_payout_contract_v1",
    "assignments": "nfl_assignment_csv_v1",
    "prelock_manifest": PRELOCK_MANIFEST_VERSION,
    "standings": STANDINGS_PARSER_VERSION,
    "metric_registry": METRIC_REGISTRY_VERSION,
}


@dataclass(frozen=True)
class StandingRow:
    entry_id: str
    rank: int
    points: float
    points_decimal: Decimal
    prize: float
    prize_cents: int
    lineup_raw: str


@dataclass(frozen=True)
class StandingsSnapshot:
    path: str
    sha256: str
    rows: tuple[StandingRow, ...]


@dataclass(frozen=True)
class CapturedArtifact:
    role: str
    request: SettlementArtifactRequest
    source_path: Path
    raw: bytes


@dataclass(frozen=True)
class PreparedSettlement:
    request: SettlementCaptureRequest
    artifacts: tuple[CapturedArtifact, ...]
    assignment_semantic_hash: str
    reference: ReferenceSettlementResult
    brief: Mapping[str, Any]


@dataclass(frozen=True)
class SettlementCaptureOutcome:
    package_path: str
    bundle: SettlementBundle
    elapsed_seconds: float
    peak_python_memory_bytes: int


class SettlementError(ValueError):
    pass


def _parse_decimal(raw: str, label: str, row_number: int) -> Decimal:
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise SettlementError(f"invalid {label} at row {row_number}") from exc
    if not value.is_finite():
        raise SettlementError(f"non-finite {label} at row {row_number}")
    return value


def parse_standings(path: str | Path) -> StandingsSnapshot:
    standings_path = Path(path).resolve()
    with standings_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"EntryId", "Rank", "Points", "Prize", "Lineup"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise SettlementError(f"standings CSV must include {sorted(required)}")
        rows: list[StandingRow] = []
        seen: set[str] = set()
        for row_number, row in enumerate(reader, start=2):
            if None in row or any(value is None for value in row.values()):
                raise SettlementError(
                    f"standings row {row_number} has missing or extra cells"
                )
            entry_id = row["EntryId"].strip()
            if not entry_id:
                continue
            if not entry_id.isdigit():
                raise SettlementError(f"non-numeric EntryId at row {row_number}")
            if entry_id in seen:
                raise SettlementError(f"duplicate EntryId at row {row_number}")
            lineup = row["Lineup"].strip()
            if not lineup:
                raise SettlementError(f"standings row {row_number} has no complete lineup")
            try:
                rank = int(row["Rank"].replace(",", ""))
            except ValueError as exc:
                raise SettlementError(f"invalid rank at row {row_number}") from exc
            points_decimal = _parse_decimal(row["Points"].strip(), "points", row_number)
            prize_text = row["Prize"].replace("$", "").replace(",", "").strip() or "0"
            prize_decimal = _parse_decimal(prize_text, "prize", row_number)
            prize_cents_decimal = prize_decimal * 100
            if prize_decimal < 0 or prize_cents_decimal != prize_cents_decimal.to_integral_value():
                raise SettlementError(
                    f"standings prize must be exact non-negative cents at row {row_number}"
                )
            if rank < 1:
                raise SettlementError(f"out-of-range rank at row {row_number}")
            rows.append(
                StandingRow(
                    entry_id=entry_id,
                    rank=rank,
                    points=float(points_decimal),
                    points_decimal=points_decimal,
                    prize=float(prize_decimal),
                    prize_cents=int(prize_cents_decimal),
                    lineup_raw=lineup,
                )
            )
            seen.add(entry_id)
    if not rows:
        raise SettlementError("standings contain no entry rows")
    return StandingsSnapshot(
        str(standings_path), sha256_file(standings_path), tuple(rows)
    )


def require_entry_coverage(snapshot: StandingsSnapshot, entry_ids: set[str]) -> None:
    observed = {row.entry_id for row in snapshot.rows}
    missing = entry_ids.difference(observed)
    if missing:
        raise SettlementError(f"standings are incomplete for Entry IDs: {sorted(missing)}")


def load_settlement_request(path: str | Path) -> SettlementCaptureRequest:
    request_path = Path(path).resolve()
    try:
        raw = json.loads(request_path.read_text(encoding="utf-8"))
        return SettlementCaptureRequest.model_validate(raw)
    except (OSError, UnicodeError, json.JSONDecodeError, ValidationError) as exc:
        raise SettlementError(f"invalid settlement request: {exc}") from exc


def _all_artifact_requests(
    request: SettlementCaptureRequest,
) -> tuple[tuple[str, SettlementArtifactRequest], ...]:
    fixed = tuple(
        (role.upper(), getattr(request.artifacts, field))
        for field, role in _FIXED_ARTIFACT_NAMES.items()
    )
    predictions = tuple(("PREDICTION", item) for item in request.artifacts.predictions)
    scenarios = tuple(("SCENARIO", item) for item in request.artifacts.scenarios)
    return fixed + predictions + scenarios


def _resolve_artifact_path(
    binding: SettlementArtifactRequest, base_directory: Path, *, confined: bool
) -> Path:
    path = Path(binding.path)
    resolved = (base_directory / path).resolve() if not path.is_absolute() else path.resolve()
    if confined:
        try:
            resolved.relative_to(base_directory.resolve())
        except ValueError as exc:
            raise SettlementError(
                f"replay artifact escapes copied package: {binding.name}"
            ) from exc
    if not resolved.is_file():
        raise SettlementError(f"settlement artifact is missing: {binding.name}: {resolved}")
    return resolved


def _capture_artifacts(
    request: SettlementCaptureRequest, base_directory: Path, *, confined: bool
) -> tuple[CapturedArtifact, ...]:
    captured: list[CapturedArtifact] = []
    for role, binding in _all_artifact_requests(request):
        source = _resolve_artifact_path(binding, base_directory, confined=confined)
        raw = source.read_bytes()
        actual = sha256_bytes(raw)
        if actual != binding.sha256:
            raise SettlementError(
                f"ARTIFACT_HASH_MISMATCH:{binding.name}:expected={binding.sha256}:actual={actual}"
            )
        captured.append(CapturedArtifact(role, binding, source, raw))
    return tuple(captured)


def _captured_by_name(
    artifacts: tuple[CapturedArtifact, ...],
) -> dict[str, CapturedArtifact]:
    return {artifact.request.name: artifact for artifact in artifacts}


def _verify_fixed_artifact_contracts(request: SettlementCaptureRequest) -> None:
    for field, expected_name in _FIXED_ARTIFACT_NAMES.items():
        binding = getattr(request.artifacts, field)
        if binding.name != expected_name:
            raise SettlementError(
                f"ARTIFACT_NAME_MISMATCH:{field}:expected={expected_name}:actual={binding.name}"
            )
        expected_version = _FIXED_ARTIFACT_VERSIONS[field]
        if binding.artifact_version != expected_version:
            raise SettlementError(
                f"ARTIFACT_VERSION_MISMATCH:{binding.name}:"
                f"expected={expected_version}:actual={binding.artifact_version}"
            )
    for binding in request.artifacts.scenarios:
        if binding.artifact_version != SCENARIO_BANK_VERSION:
            raise SettlementError(
                f"ARTIFACT_VERSION_MISMATCH:{binding.name}:"
                f"expected={SCENARIO_BANK_VERSION}:actual={binding.artifact_version}"
            )


def _load_json_artifact(artifact: CapturedArtifact, label: str) -> Mapping[str, Any]:
    try:
        value = json.loads(artifact.raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise SettlementError(f"invalid {label} JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise SettlementError(f"{label} must be a JSON object")
    return value


def _manifest_hash(
    mapping: Mapping[str, Any], key: str, *, aliases: tuple[str, ...] = ()
) -> str | None:
    hashes = mapping.get("input_hashes")
    if not isinstance(hashes, dict):
        return None
    for candidate in (key, *aliases):
        value = hashes.get(candidate)
        if isinstance(value, str):
            return value
    return None


def _manifest_field_size(mapping: Mapping[str, Any]) -> int | None:
    """The pre-lock field-size assumption, if the manifest recorded one."""
    contest = mapping.get("contest_parameters")
    if not isinstance(contest, dict):
        return None
    value = contest.get("field_size")
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _compare_manifest_value(
    actual: object, expected: object, code: str, *, optional: bool = False
) -> None:
    if actual is None and optional:
        return
    if str(actual) != str(expected):
        raise SettlementError(f"{code}:expected={expected}:actual={actual}")


def _validate_prelock_manifest(
    request: SettlementCaptureRequest,
    artifacts: Mapping[str, CapturedArtifact],
) -> Mapping[str, Any]:
    manifest = _load_json_artifact(artifacts["prelock_manifest"], "pre-lock manifest")
    _compare_manifest_value(
        manifest.get("schema_version"), PRELOCK_MANIFEST_VERSION, "PRELOCK_VERSION_MISMATCH"
    )
    _compare_manifest_value(manifest.get("run_id"), request.run_id, "RUN_ID_MISMATCH")
    for name in ("salary", "entries"):
        recorded = _manifest_hash(manifest, name, aliases=(f"{name}s",))
        _compare_manifest_value(
            recorded,
            artifacts[name].request.sha256,
            f"PRELOCK_{name.upper()}_HASH_MISMATCH",
        )
    # Payouts are optional in the manifest, and only in the manifest. A
    # prior-only run never reads a payout table — CLAUDE.md keeps contest
    # economics out of that path deliberately — so it has no hash to record,
    # while the legacy `build` path does and is still checked exactly as before.
    # The request binds the payout bytes by SHA-256 either way, so nothing is
    # unbound by this; only the manifest's second copy of that binding is
    # allowed to be absent. Ben's ruling, 2026-09-14.
    _compare_manifest_value(
        _manifest_hash(manifest, "payouts", aliases=("payout",)),
        artifacts["payouts"].request.sha256,
        "PRELOCK_PAYOUTS_HASH_MISMATCH",
        optional=True,
    )
    assignment_recorded = _manifest_hash(manifest, "assignments") or manifest.get(
        "assignment_sha256"
    )
    _compare_manifest_value(
        assignment_recorded,
        artifacts["assignments"].request.sha256,
        "PRELOCK_ASSIGNMENT_HASH_MISMATCH",
    )
    for binding in request.artifacts.predictions:
        _compare_manifest_value(
            _manifest_hash(manifest, binding.name),
            binding.sha256,
            f"PRELOCK_PREDICTION_HASH_MISMATCH:{binding.name}",
        )
    scenario_records = manifest.get("scenario_artifacts")
    if not isinstance(scenario_records, dict):
        raise SettlementError("PRELOCK_SCENARIO_ARTIFACTS_MISSING")
    # A prior-only run simulates nothing, so it declares `{}` here and the
    # request binds no bank. The coverage check below still holds both sides to
    # each other; `SettlementCaptureRequest` is what refuses an empty set for any
    # model status other than PRIOR_ONLY.
    requested_scenarios = {binding.name for binding in request.artifacts.scenarios}
    if requested_scenarios != set(scenario_records):
        raise SettlementError(
            "PRELOCK_SCENARIO_COVERAGE_MISMATCH:"
            f"request={sorted(requested_scenarios)}:"
            f"manifest={sorted(scenario_records)}"
        )
    for binding in request.artifacts.scenarios:
        record = scenario_records.get(binding.name)
        if not isinstance(record, dict):
            raise SettlementError(f"PRELOCK_SCENARIO_MISSING:{binding.name}")
        _compare_manifest_value(
            record.get("sha256"),
            binding.sha256,
            f"PRELOCK_SCENARIO_HASH_MISMATCH:{binding.name}",
        )
        _compare_manifest_value(
            record.get("schema_version"),
            binding.artifact_version,
            f"PRELOCK_SCENARIO_VERSION_MISMATCH:{binding.name}",
        )

    versions = manifest.get("artifact_versions")
    if not isinstance(versions, dict):
        raise SettlementError("PRELOCK_ARTIFACT_VERSIONS_MISSING")
    fixed_prelock_names = {"salary", "entries", "payouts", "assignments"}
    expected_prediction_names = set(versions).difference(
        fixed_prelock_names, requested_scenarios
    )
    requested_prediction_names = {
        binding.name for binding in request.artifacts.predictions
    }
    if requested_prediction_names != expected_prediction_names:
        raise SettlementError(
            "PRELOCK_PREDICTION_COVERAGE_MISMATCH:"
            f"request={sorted(requested_prediction_names)}:"
            f"manifest={sorted(expected_prediction_names)}"
        )
    versioned_bindings = (
        request.artifacts.salary,
        request.artifacts.entries,
        request.artifacts.assignments,
        *request.artifacts.predictions,
        *request.artifacts.scenarios,
    )
    for binding in versioned_bindings:
        _compare_manifest_value(
            versions.get(binding.name),
            binding.artifact_version,
            f"PRELOCK_ARTIFACT_VERSION_MISMATCH:{binding.name}",
        )
    # Payouts again: a producer that never read a payout table cannot declare its
    # version any more than it can declare its hash. Checked when recorded.
    _compare_manifest_value(
        versions.get(request.artifacts.payouts.name),
        request.artifacts.payouts.artifact_version,
        "PRELOCK_ARTIFACT_VERSION_MISMATCH:payouts",
        optional=True,
    )

    contest = manifest.get("contest_parameters")
    if not isinstance(contest, dict):
        raise SettlementError("PRELOCK_CONTEST_PARAMETERS_MISSING")
    facts = request.contest
    # Contest identity. A pre-lock run reads all four of these straight out of
    # the salary and reserved-entry bytes, so they stay hard checks: they are
    # what proves the manifest describes this contest and not another.
    for key, expected in {
        "contest_id": facts.contest_id,
        "draft_group": facts.draft_group,
        "mode": facts.mode.value,
        "entry_fee": float(facts.entry_fee),
    }.items():
        _compare_manifest_value(
            contest.get(key), expected, f"PRELOCK_CONTEST_MISMATCH:{key}"
        )
    # Contest economics. Stable facts, but an operator supplies them and a
    # prior-only run never sees them, so they are checked when the manifest
    # records them and not required when it does not.
    for key, expected in {
        "objective": facts.objective.value,
        "advertised_prize_value": float(facts.advertised_prize_value),
        "ticket_face_value": (
            float(facts.ticket_face_value) if facts.ticket_face_value is not None else None
        ),
    }.items():
        _compare_manifest_value(
            contest.get(key),
            expected,
            f"PRELOCK_CONTEST_MISMATCH:{key}",
            optional=True,
        )
    # `field_size` is deliberately NOT compared. The manifest's copy is the
    # pre-lock *assumption* the portfolio was built against; the request's is the
    # *settled* count, which must equal the standings row count. Those are two
    # different quantities and they routinely differ — contest 193391013 was
    # advertised at 133,000 and settled 126,020 — so requiring equality made this
    # gate unclearable by any honest producer, `build` included. The difference is
    # reported in the run brief as a Q6 diagnostic instead. Ben's ruling,
    # 2026-09-14.
    truths = request.release_truths.model_dump(mode="json", by_alias=True)
    for key, expected in truths.items():
        _compare_manifest_value(
            manifest.get(key), expected, f"PRELOCK_RELEASE_TRUTH_MISMATCH:{key}"
        )
    return manifest


def _reference_budget(request: SettlementCaptureRequest) -> ReferenceBudget:
    exact_keys = {"max_entries", "max_work_units", "max_runtime_seconds"}
    supplied = request.reference_budget
    if set(supplied) != exact_keys:
        raise SettlementError(
            f"reference_budget keys must be exactly {sorted(exact_keys)}"
        )
    try:
        return ReferenceBudget(
            max_entries=int(supplied["max_entries"]),
            max_work_units=int(supplied["max_work_units"]),
            max_runtime_seconds=float(supplied["max_runtime_seconds"]),
        )
    except (TypeError, ValueError) as exc:
        raise SettlementError(f"invalid reference budget: {exc}") from exc


def _verify_sources_unchanged(artifacts: tuple[CapturedArtifact, ...]) -> None:
    for artifact in artifacts:
        actual = sha256_file(artifact.source_path)
        if actual != artifact.request.sha256:
            raise SettlementError(
                f"SOURCE_MUTATED_DURING_CAPTURE:{artifact.request.name}:"
                f"expected={artifact.request.sha256}:actual={actual}"
            )


def _prepare_settlement(
    request: SettlementCaptureRequest,
    base_directory: Path,
    *,
    confined: bool,
) -> PreparedSettlement:
    _verify_fixed_artifact_contracts(request)
    artifacts = _capture_artifacts(request, base_directory, confined=confined)
    by_name = _captured_by_name(artifacts)
    manifest = _validate_prelock_manifest(request, by_name)

    slate = parse_salaries(
        by_name["salary"].source_path, draft_group=request.contest.draft_group
    )
    template = parse_entries(by_name["entries"].source_path)
    reconcile_template(template, slate)
    require_single_contest(template)
    facts = request.contest
    if slate.mode is not facts.mode or template.mode is not facts.mode:
        raise SettlementError(
            f"MODE_MISMATCH:request={facts.mode.value}:salary={slate.mode.value}:"
            f"entries={template.mode.value}"
        )
    if slate.draft_group != facts.draft_group:
        raise SettlementError("DRAFT_GROUP_MISMATCH")
    if slate.scoring_version != request.versions.scoring:
        raise SettlementError(
            f"SCORING_VERSION_MISMATCH:expected={request.versions.scoring}:"
            f"actual={slate.scoring_version}"
        )
    contest_ids = {entry.contest_id for entry in template.authorizations}
    entry_fees = {Decimal(str(entry.entry_fee)) for entry in template.authorizations}
    if contest_ids != {facts.contest_id}:
        raise SettlementError(
            f"CONTEST_ID_MISMATCH:request={facts.contest_id}:entries={sorted(contest_ids)}"
        )
    if entry_fees != {facts.entry_fee}:
        raise SettlementError(
            f"ENTRY_FEE_MISMATCH:request={facts.entry_fee}:entries={sorted(entry_fees)}"
        )

    tiers = parse_payout_csv(
        by_name["payouts"].source_path,
        ticket_face_value=(
            float(facts.ticket_face_value) if facts.ticket_face_value is not None else None
        ),
        advertised_value=float(facts.advertised_prize_value),
        field_size=facts.field_size,
        reserved_entry_count=len(template.authorizations),
        allow_zero_payout=True,
    )
    assignments = read_assignment_csv(by_name["assignments"].source_path, facts.mode)
    authorized_ids = {entry.entry_id for entry in template.authorizations}
    if set(assignments) != authorized_ids:
        raise SettlementError(
            "ENTRY_ID_ASSIGNMENT_MISMATCH: selected assignments must exactly cover reserved entries"
        )
    validated_lineups = {}
    for entry_id, roster in assignments.items():
        validated = validate_lineup(slate, roster)
        if not validated.valid or validated.lineup is None:
            raise SettlementError(
                f"INVALID_SELECTED_ASSIGNMENT:{entry_id}:{'; '.join(validated.errors)}"
            )
        validated_lineups[entry_id] = validated.lineup

    standings = parse_standings(by_name["standings"].source_path)
    require_entry_coverage(standings, authorized_ids)
    if len(standings.rows) != facts.field_size:
        raise SettlementError(
            f"INCOMPLETE_STANDINGS_FIELD:expected={facts.field_size}:"
            f"observed={len(standings.rows)}"
        )
    for row in standings.rows:
        if row.entry_id in validated_lineups and (
            row.lineup_raw != validated_lineups[row.entry_id].canonical_key
        ):
            raise SettlementError(
                f"OWNED_LINEUP_MISMATCH:{row.entry_id}: standings lineup does not match selected assignment"
            )

    registry = load_metric_registry(by_name["metric_registry"].source_path)
    if registry.sha256 != request.artifacts.metric_registry.sha256:
        raise SettlementError("METRIC_REGISTRY_HASH_MISMATCH")
    require_registry_precedes_evaluation(registry, request.settled_at)
    for prediction in request.artifacts.predictions:
        artifact = by_name[prediction.name]
        if artifact.source_path.suffix.lower() == ".json":
            decoded = _load_json_artifact(artifact, f"prediction {prediction.name}")
            embedded = decoded.get("schema_version") or decoded.get("artifact_version")
            _compare_manifest_value(
                embedded,
                prediction.artifact_version,
                f"PREDICTION_VERSION_MISMATCH:{prediction.name}",
            )
    scenario_purposes: set[str] = set()
    for scenario in request.artifacts.scenarios:
        metadata = inspect_scenario_bank(by_name[scenario.name].source_path)
        if metadata["purpose"] != scenario.name:
            raise SettlementError(
                f"SCENARIO_PURPOSE_MISMATCH:{scenario.name}:actual={metadata['purpose']}"
            )
        if metadata["purpose"] in scenario_purposes:
            raise SettlementError(f"DUPLICATE_SCENARIO_PURPOSE:{metadata['purpose']}")
        scenario_purposes.add(metadata["purpose"])

    reference_entries = tuple(
        ReferenceFieldEntry(
            entry_id=row.entry_id,
            score=row.points_decimal,
            lineup_key=row.lineup_raw,
            operator_owned=row.entry_id in authorized_ids,
        )
        for row in standings.rows
    )
    reference = evaluate_reference_settlement(
        reference_entries,
        tiers,
        field_size=facts.field_size,
        ticket_face_value=facts.ticket_face_value,
        advertised_prize_value=facts.advertised_prize_value,
        budget=_reference_budget(request),
    )
    standings_by_id = {row.entry_id: row for row in standings.rows}
    for result in reference.rows:
        observed = standings_by_id[result.entry_id]
        if result.rank != observed.rank:
            raise SettlementError(
                f"STANDINGS_RANK_MISMATCH:{result.entry_id}:"
                f"expected={result.rank}:actual={observed.rank}"
            )
        if result.gross_prize.cents != Fraction(observed.prize_cents, 1):
            raise SettlementError(
                f"STANDINGS_PRIZE_MISMATCH:{result.entry_id}:"
                f"expected_cents={result.gross_prize.cents}:"
                f"actual_cents={observed.prize_cents}"
            )

    semantic_hash = assignment_hash(assignments)
    artifact_inventory = [
        {
            "name": artifact.request.name,
            "role": artifact.role,
            "sha256": artifact.request.sha256,
            "artifact_version": artifact.request.artifact_version,
            "byte_count": len(artifact.raw),
        }
        for artifact in sorted(artifacts, key=lambda item: (item.role, item.request.name))
    ]
    brief: dict[str, Any] = {
        "schema_version": BRIEF_VERSION,
        "settlement_id": request.settlement_id,
        "run_id": request.run_id,
        "purpose": (
            "Reconstruct the frozen prediction, selection, entry authorization, "
            "complete-field settlement, and release truth without conversation history."
        ),
        "contest": request.contest.model_dump(mode="json"),
        "versions": request.versions.model_dump(mode="json"),
        "timeline": {
            "captured_at": request.captured_at.isoformat(),
            "settled_at": request.settled_at.isoformat(),
        },
        "prediction": {
            "prelock_manifest_sha256": request.artifacts.prelock_manifest.sha256,
            "prediction_artifact_names": [item.name for item in request.artifacts.predictions],
            "scenario_artifact_names": [item.name for item in request.artifacts.scenarios],
            "manifest_status": manifest.get("status"),
            # What the portfolio was built against, beside what actually turned
            # up. These are two different quantities, so this is reported rather
            # than enforced: for Q6 the gap between an assumed and a settled field
            # is signal about the build, not a fault in the capture.
            "assumed_field_size": _manifest_field_size(manifest),
            "settled_field_size": request.contest.field_size,
        },
        "selection_and_entry": {
            "assignment_sha256": request.artifacts.assignments.sha256,
            "assignment_semantic_hash": semantic_hash,
            "selected_entry_ids": sorted(assignments),
            "reserved_entry_template_sha256": request.artifacts.entries.sha256,
        },
        "settlement": {
            "standings_sha256": standings.sha256,
            "reference_result_hash": reference.result_hash,
            "complete_field_entries": len(standings.rows),
            "operator_entry_count": len(authorized_ids),
            "reference_budget": reference.budget.to_dict(),
            "reference_work_units": reference.work_units,
        },
        "metric_registration": {
            "registry_id": registry.registry_id,
            "registered_at": registry.registered_at.isoformat(),
            "sha256": registry.sha256,
        },
        "release_truths": request.release_truths.model_dump(mode="json", by_alias=True),
        "evidence_issues": [
            issue.model_dump(mode="json") for issue in request.evidence_issues
        ],
        "artifacts": artifact_inventory,
        "credentials_or_account_state_stored": False,
    }
    _verify_sources_unchanged(artifacts)
    return PreparedSettlement(request, artifacts, semantic_hash, reference, brief)


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-.") or "artifact"


def _artifact_destination(artifact: CapturedArtifact) -> Path:
    suffix = "".join(artifact.source_path.suffixes[-2:])
    if len(suffix) > 20:
        suffix = artifact.source_path.suffix
    filename = (
        f"{artifact.role.lower()}_{_safe_name(artifact.request.name)}_"
        f"{artifact.request.sha256[:16]}{suffix}"
    )
    return Path("artifacts") / filename


def _published_artifacts(
    prepared: PreparedSettlement, staging: Path
) -> tuple[tuple[SettledArtifact, ...], SettlementCaptureRequest]:
    destinations: dict[str, Path] = {}
    settled: list[SettledArtifact] = []
    artifact_dir = staging / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=False)
    for artifact in prepared.artifacts:
        relative = _artifact_destination(artifact)
        if relative in destinations.values():
            raise SettlementError(f"artifact destination collision: {relative}")
        target = staging / relative
        target.write_bytes(artifact.raw)
        if sha256_file(target) != artifact.request.sha256:
            raise SettlementError(f"copied artifact hash mismatch: {artifact.request.name}")
        destinations[artifact.request.name] = relative
        settled.append(
            SettledArtifact(
                name=artifact.request.name,
                role=artifact.role,
                relative_path=relative.as_posix(),
                sha256=artifact.request.sha256,
                artifact_version=artifact.request.artifact_version,
                byte_count=len(artifact.raw),
            )
        )

    request_data = prepared.request.model_dump(mode="json", by_alias=True)
    artifact_data = request_data["artifacts"]
    for field in _FIXED_ARTIFACT_NAMES:
        binding = artifact_data[field]
        binding["path"] = destinations[binding["name"]].as_posix()
    for group in ("predictions", "scenarios"):
        for binding in artifact_data[group]:
            binding["path"] = destinations[binding["name"]].as_posix()
    replay_request = SettlementCaptureRequest.model_validate(request_data)
    return tuple(sorted(settled, key=lambda item: (item.role, item.name))), replay_request


def capture_settlement_bundle(
    request_path: str | Path, output_directory: str | Path
) -> SettlementCaptureOutcome:
    started = time.perf_counter()
    tracemalloc.start()
    try:
        request_file = Path(request_path).resolve()
        request = load_settlement_request(request_file)
        output_root = Path(output_directory).resolve()
        output_root.mkdir(parents=True, exist_ok=True)
        final = output_root / request.settlement_id
        if final.exists():
            raise SettlementError(
                f"settlement bundle already exists and is immutable: {final}"
            )
        prepared = _prepare_settlement(request, request_file.parent, confined=False)
        staging = Path(
            tempfile.mkdtemp(prefix=f".{request.settlement_id}.tmp-", dir=output_root)
        )
        published = False
        try:
            settled_artifacts, replay_request = _published_artifacts(prepared, staging)
            reference_path = Path("reference_settlement.json")
            brief_path = Path("run_settlement_brief.json")
            replay_path = Path("replay_request.json")
            (staging / reference_path).write_bytes(
                canonical_json_bytes(prepared.reference.deterministic_dict()) + b"\n"
            )
            (staging / brief_path).write_bytes(
                canonical_json_bytes(prepared.brief) + b"\n"
            )
            (staging / replay_path).write_bytes(
                canonical_json_bytes(
                    replay_request.model_dump(mode="json", by_alias=True)
                )
                + b"\n"
            )
            bundle = SettlementBundle(
                settlement_id=request.settlement_id,
                run_id=request.run_id,
                contest=request.contest,
                versions=request.versions,
                artifacts=settled_artifacts,
                assignment_semantic_hash=prepared.assignment_semantic_hash,
                reference_result_hash=prepared.reference.result_hash,
                reference_result_path=reference_path.as_posix(),
                brief_path=brief_path.as_posix(),
                metric_registry_hash=request.artifacts.metric_registry.sha256,
                captured_at=request.captured_at,
                settled_at=request.settled_at,
                release_truths=request.release_truths,
                evidence_issues=request.evidence_issues,
            )
            (staging / "settlement_bundle.json").write_bytes(
                canonical_json_bytes(bundle.model_dump(mode="json", by_alias=True))
                + b"\n"
            )
            _verify_sources_unchanged(prepared.artifacts)
            os.replace(staging, final)
            published = True
        finally:
            if not published and staging.exists():
                shutil.rmtree(staging)
        _, peak = tracemalloc.get_traced_memory()
        return SettlementCaptureOutcome(
            package_path=str(final),
            bundle=bundle,
            elapsed_seconds=time.perf_counter() - started,
            peak_python_memory_bytes=peak,
        )
    finally:
        if tracemalloc.is_tracing():
            tracemalloc.stop()


def _load_bundle(path: Path) -> SettlementBundle:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return SettlementBundle.model_validate(raw)
    except (OSError, UnicodeError, json.JSONDecodeError, ValidationError) as exc:
        raise SettlementError(f"invalid settlement bundle: {exc}") from exc


def replay_settlement_package(package_directory: str | Path) -> dict[str, object]:
    package = Path(package_directory).resolve()
    if not package.is_dir():
        raise SettlementError(f"settlement package is missing: {package}")
    bundle = _load_bundle(package / "settlement_bundle.json")
    request = load_settlement_request(package / "replay_request.json")
    if request.settlement_id != bundle.settlement_id or request.run_id != bundle.run_id:
        raise SettlementError("REPLAY_REQUEST_BUNDLE_ID_MISMATCH")
    prepared = _prepare_settlement(request, package, confined=True)
    if prepared.reference.result_hash != bundle.reference_result_hash:
        raise SettlementError("REFERENCE_REPLAY_HASH_MISMATCH")
    if prepared.assignment_semantic_hash != bundle.assignment_semantic_hash:
        raise SettlementError("ASSIGNMENT_REPLAY_HASH_MISMATCH")
    inventory = {artifact.name: artifact for artifact in bundle.artifacts}
    if set(inventory) != {artifact.request.name for artifact in prepared.artifacts}:
        raise SettlementError("BUNDLE_ARTIFACT_INVENTORY_MISMATCH")
    for artifact in prepared.artifacts:
        recorded = inventory[artifact.request.name]
        if (
            recorded.sha256 != artifact.request.sha256
            or recorded.artifact_version != artifact.request.artifact_version
            or recorded.byte_count != len(artifact.raw)
        ):
            raise SettlementError(f"BUNDLE_ARTIFACT_RECORD_MISMATCH:{recorded.name}")
        if Path(recorded.relative_path) != Path(artifact.request.path):
            raise SettlementError(f"BUNDLE_ARTIFACT_PATH_MISMATCH:{recorded.name}")
    reference_file = (package / bundle.reference_result_path).resolve()
    brief_file = (package / bundle.brief_path).resolve()
    for label, target in (("reference", reference_file), ("brief", brief_file)):
        try:
            target.relative_to(package)
        except ValueError as exc:
            raise SettlementError(f"{label} path escapes settlement package") from exc
        if not target.is_file():
            raise SettlementError(f"settlement {label} artifact is missing")
    stored_reference = json.loads(reference_file.read_text(encoding="utf-8"))
    if stored_reference != prepared.reference.deterministic_dict():
        raise SettlementError("REFERENCE_REPLAY_BYTES_DISAGREE")
    stored_brief = json.loads(brief_file.read_text(encoding="utf-8"))
    if stored_brief != prepared.brief:
        raise SettlementError("BRIEF_REPLAY_DISAGREES")
    return {
        "status": "DETERMINISTIC_REPLAY_PASS",
        "settlement_id": bundle.settlement_id,
        "run_id": bundle.run_id,
        "reference_result_hash": bundle.reference_result_hash,
        "assignment_semantic_hash": bundle.assignment_semantic_hash,
        "artifact_count": len(bundle.artifacts),
        "package_path": str(package),
    }
