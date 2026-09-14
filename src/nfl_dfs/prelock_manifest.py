"""Freeze what a run predicted, before lock, as ``nfl_prelock_run_manifest_v1``.

Q1 built the settlement plane and Q1B proved nothing could reach it: no
``data/runs/`` snapshot held a pre-lock manifest, because only the legacy
``build`` command ever wrote one and every contest Ben has actually entered came
through ``prior_review``. This is the emitter that closes that gap.

What a pre-lock manifest is for
-------------------------------

It is the record, written *before* the games start, of what the engine predicted
and which lineups it selected — bound by SHA-256 so that a settlement written
days later cannot quietly disagree with it. That ordering is the whole point.
A manifest written after the outcome is known proves nothing, so this module
never backfills one: it is called on the path that builds a portfolio, at the
moment the portfolio exists, or it is not called at all.

Deliberately not a release decision. A manifest is emitted for a run whose
release decision is ``DO_NOT_UPLOAD`` — which is every prior-only run, and which
is exactly the case that matters, because those are the review lineups Ben
actually enters by hand. Emitting one changes no truth, unlocks no upload, and
says nothing about model quality.

What a prior-only run can and cannot attest
-------------------------------------------

The manifest records only what the run genuinely observed:

- the exact salary and reserved-entry bytes it read;
- the frozen projection artifacts it produced, which *are* the prediction;
- the assignment it selected;
- contest identity — id, draft group, mode and entry fee — all four read
  straight out of those CSVs;
- the four release truths, unchanged.

It does not record a payout table, a contest objective, an advertised prize
value, or a settled field size, because a prior-only run has none of them and
inventing any of them would be the exact failure this module exists to prevent.
``settlement._validate_prelock_manifest`` treats all of those as optional, and
compares them only when a producer that genuinely had them recorded them; Ben's
ruling, 2026-09-14.

``field_size`` is the subtle one. The manifest's copy is the *assumption a
portfolio was built against*; settlement's is the *settled entry count*. Those
are different quantities and they routinely differ — contest 193391013 was
advertised at 133,000 and settled 126,020 — so settlement reports the gap as a
Q6 diagnostic instead of demanding they match. A prior-only run assumed nothing,
so it records ``null`` and says why, rather than omitting the key and leaving
"did not know" indistinguishable from "forgot".
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Mapping, Sequence

from .contracts import EngineMode
from .hashing import sha256_file

PRELOCK_MANIFEST_VERSION = "nfl_prelock_run_manifest_v1"
PRIOR_ONLY_STATUS = "PRIOR_ONLY_REVIEW_DO_NOT_UPLOAD"

#: Artifact roles settlement resolves itself. Anything else this manifest lists
#: in ``artifact_versions`` becomes a prediction the request must bind, because
#: ``settlement._validate_prelock_manifest`` derives the expected prediction set
#: by subtracting exactly these names and the scenario names from that mapping.
_FIXED_ARTIFACT_NAMES = ("salary", "entries", "payouts", "assignments")


class PrelockManifestError(ValueError):
    """A named refusal. Every message starts with a stable upper-case code."""


@dataclass(frozen=True)
class PredictionArtifact:
    """One frozen model artifact, bound by the hash the run already computed."""

    name: str
    path: str
    sha256: str
    artifact_version: str


def build_prelock_manifest(
    *,
    run_id: str,
    created_at: datetime,
    mode: EngineMode,
    contest_id: str,
    draft_group: str,
    entry_fee: Decimal | float | str,
    salary_sha256: str,
    entries_sha256: str,
    assignments_path: str,
    assignments_sha256: str,
    predictions: Sequence[PredictionArtifact],
    release_truths: Mapping[str, object],
    selected_entry_ids: Sequence[str],
    evidence: Mapping[str, object] | None = None,
    status: str = PRIOR_ONLY_STATUS,
    assumed_field_size: int | None = None,
) -> dict:
    """Assemble the manifest. Refuses rather than filling in a blank.

    Every hash here is one the run already computed while doing the work; none is
    recomputed from a path, because a path can be swapped between the run and
    this call and a recomputed hash would silently bless the swap.
    """
    if created_at.tzinfo is None:
        raise PrelockManifestError(
            "PRELOCK_CREATED_AT_NOT_TIMEZONE_AWARE: a pre-lock record without an "
            "unambiguous clock cannot prove it preceded lock"
        )
    if not predictions:
        raise PrelockManifestError(
            "PRELOCK_PREDICTION_REQUIRED: a manifest with no frozen prediction "
            "artifact records nothing worth settling against"
        )
    if not selected_entry_ids:
        raise PrelockManifestError(
            "PRELOCK_ASSIGNMENT_REQUIRED: no Entry ID was assigned, so there is no "
            "pre-lock selection to freeze"
        )
    missing = [
        label
        for label, value in (
            ("run_id", run_id),
            ("contest_id", contest_id),
            ("draft_group", draft_group),
            ("salary_sha256", salary_sha256),
            ("entries_sha256", entries_sha256),
            ("assignments_sha256", assignments_sha256),
        )
        if not value
    ]
    if missing:
        raise PrelockManifestError(f"PRELOCK_FIELD_UNRESOLVED: {sorted(missing)}")

    required_truths = ("FILE_VALID", "EVIDENCE_STATE", "MODEL_STATUS", "RELEASE_DECISION")
    absent = [key for key in required_truths if key not in release_truths]
    if absent:
        raise PrelockManifestError(f"PRELOCK_RELEASE_TRUTH_MISSING: {absent}")

    duplicate = {
        item.name for item in predictions if item.name in _FIXED_ARTIFACT_NAMES
    }
    if duplicate:
        raise PrelockManifestError(
            f"PRELOCK_PREDICTION_NAME_RESERVED: {sorted(duplicate)} collide with the "
            "artifact roles settlement resolves itself"
        )
    seen = [item.name for item in predictions]
    if len(set(seen)) != len(seen):
        raise PrelockManifestError(f"PRELOCK_PREDICTION_NAME_DUPLICATE: {sorted(seen)}")

    input_hashes = {
        "salary": salary_sha256,
        "entries": entries_sha256,
        "assignments": assignments_sha256,
    }
    artifact_versions = {
        "salary": "dk_salary_csv_v1",
        "entries": "dk_entry_csv_v1",
        "assignments": "nfl_assignment_csv_v1",
    }
    for item in predictions:
        input_hashes[item.name] = item.sha256
        artifact_versions[item.name] = item.artifact_version

    return {
        "schema_version": PRELOCK_MANIFEST_VERSION,
        "run_id": run_id,
        "created_at": created_at.isoformat(),
        "status": status,
        "FILE_VALID": release_truths["FILE_VALID"],
        "EVIDENCE_STATE": release_truths["EVIDENCE_STATE"],
        "MODEL_STATUS": release_truths["MODEL_STATUS"],
        "RELEASE_DECISION": release_truths["RELEASE_DECISION"],
        # Run-relative, never absolute: two runs of the same slate from different
        # roots must produce byte-identical manifests, and an absolute path is
        # the one field that could not. Settlement binds the assignment by
        # `assignment_sha256`, so this is a label, not a lookup.
        "assignments": assignments_path,
        "assignment_sha256": assignments_sha256,
        "selected_entry_ids": sorted(selected_entry_ids),
        "input_hashes": input_hashes,
        "artifact_versions": artifact_versions,
        # A prior-only run simulates nothing, so it declares the absence rather
        # than emitting a one-scenario bank that would read as a distribution it
        # does not have. `SettlementCaptureRequest` refuses an empty set for any
        # model status other than PRIOR_ONLY.
        "scenario_artifacts": {},
        "contest_parameters": {
            "contest_id": contest_id,
            "draft_group": draft_group,
            "mode": mode.value,
            "entry_fee": float(Decimal(str(entry_fee))),
            # The assumption the portfolio was built against, not the settled
            # count, which no pre-lock producer can know. Null where nothing was
            # assumed; the basis says which.
            "field_size": assumed_field_size,
            "field_size_basis": (
                "PRE_LOCK_ASSUMPTION" if assumed_field_size is not None
                else "UNKNOWN_PRIOR_ONLY_RUN_READS_NO_CONTEST_ECONOMICS"
            ),
        },
        "model_status_limitations": {
            "prospective_validation": "ABSENT",
            "scenarios": "ABSENT_PRIOR_ONLY_RUN_SIMULATES_NOTHING",
            "contest_economics": "ABSENT_PRIOR_ONLY_RUN_READS_NO_PAYOUTS_OR_FIELD_SIZE",
        },
        "evidence": dict(evidence or {}),
        "credentials_or_account_state_stored": False,
    }


def write_prelock_manifest(path: str | Path, manifest: Mapping[str, object]) -> str:
    """Write the manifest as stable bytes and return its SHA-256.

    Canonical JSON with sorted keys, written through a temporary file so a
    half-written manifest never appears at the destination. Byte-stable for the
    same inputs, which is what lets a deterministic replay compare it.
    """
    target = Path(path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        json.dumps(dict(manifest), sort_keys=True, separators=(",", ":"), default=str)
        + "\n"
    ).encode("utf-8")
    temporary = target.with_name(target.name + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(target)
    return sha256_file(target)
