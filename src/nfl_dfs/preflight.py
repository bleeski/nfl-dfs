"""W6 / R09: historical artifact integrity, and a separate live pre-upload check.

`audit` answered one question ("do the stored bytes still match the stored
hash?") while reporting an answer to a different one ("may this be uploaded
now?"). It fed the manifest's stored `EVIDENCE_STATE` and `MODEL_STATUS`
straight into the release policy, so a package certified in January still read
`CERTIFIED_UPLOAD_PACKAGE` in September, and its exit code described audit
problems rather than the release decision.

Two checks live here, and they answer different questions at different clocks:

`historical_artifact_integrity` is the archival question. It verifies the
manifest parses, its schema is one this code understands, and the bytes it
points at still hash to what it recorded. It reports the decision the manifest
*stored*, clearly labelled as stored, and its own `RELEASE_DECISION` is always
`DO_NOT_UPLOAD`. A historical check can never renew a certification, because
nothing it inspects is evaluated at the present moment.

`live_pre_upload_check` is the release question. It re-derives every hard
evidence state at the clock it is given (`evidence.release_clock()` by default),
re-checks that the manifest still covers every required hard field, rebinds the
files the manifest claims to cover, and re-derives player locks from the current
salary pool. It reports the clock and the scope of every check it ran.

Nothing here can widen an expiry or clear a gate. Both functions only ever add
blockers.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field as dataclass_field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from pydantic import ValidationError

from .contracts import (
    CertificationBasis,
    CertificationManifest,
    EvidenceRecord,
    EvidenceState,
    ModelStatus,
    ReleaseEvidenceState,
)
from .evidence import release_clock
from .hashing import sha256_file
from .release import aggregate_evidence_state, derive_release_policy


PROJECT_ROOT = Path(__file__).resolve().parents[2]

SUPPORTED_MANIFEST_VERSIONS = frozenset({"certification_manifest_v1"})

HISTORICAL_SCOPE = "HISTORICAL_ARTIFACT_INTEGRITY"
LIVE_SCOPE = "LIVE_PRE_UPLOAD"

#: The files a manifest records by plain SHA-256 and a live check can rebind.
BINDABLE_INPUTS = ("salary", "entries", "assignments")


class PreflightError(RuntimeError):
    """A manifest could not be read at all."""


@dataclass(frozen=True)
class PreflightCheck:
    name: str
    scope: str
    state: str
    detail: str
    checked_at: str

    def as_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "scope": self.scope,
            "state": self.state,
            "detail": self.detail,
            "checked_at": self.checked_at,
        }


@dataclass
class _Loaded:
    data: Mapping[str, Any] = dataclass_field(default_factory=dict)
    checks: list[PreflightCheck] = dataclass_field(default_factory=list)
    blockers: list[str] = dataclass_field(default_factory=list)
    readable: bool = False


def _stamp(when: datetime) -> str:
    return when.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _required_hard_fields(basis: CertificationBasis) -> tuple[str, ...]:
    """The hard fields a certification manifest must still account for.

    Read from the same `config/evidence_policy.json` certification reads, so a
    live check cannot drift below the policy the package was certified against.
    """
    path = PROJECT_ROOT / "config" / "evidence_policy.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PreflightError(f"EVIDENCE_POLICY_UNREADABLE:{exc}") from exc
    fields = value.get("hard_fields") if isinstance(value, dict) else None
    model_fields = value.get("model_assisted_hard_fields") if isinstance(value, dict) else None
    if (not isinstance(fields, list) or not fields
            or not isinstance(model_fields, list) or not model_fields
            or any(not isinstance(name, str) or not name.strip()
                   for name in [*fields, *model_fields])):
        raise PreflightError("EVIDENCE_POLICY_INVALID:hard field lists must be nonempty strings")
    return tuple(dict.fromkeys([
        *fields, *(model_fields if basis is CertificationBasis.MODEL_ASSISTED else []),
    ]))


def _load_manifest(manifest_path: str | Path, when: datetime) -> _Loaded:
    loaded = _Loaded()
    stamp = _stamp(when)
    path = Path(manifest_path)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        loaded.blockers.append(f"MANIFEST_UNREADABLE:{exc}")
        loaded.checks.append(
            PreflightCheck("manifest_readable", "MANIFEST_SCHEMA", "FAIL", str(exc), stamp)
        )
        return loaded
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        loaded.blockers.append(f"MANIFEST_UNREADABLE:{exc}")
        loaded.checks.append(
            PreflightCheck("manifest_readable", "MANIFEST_SCHEMA", "FAIL", str(exc), stamp)
        )
        return loaded
    if not isinstance(data, dict):
        loaded.blockers.append("MANIFEST_UNREADABLE:manifest must be a JSON object")
        loaded.checks.append(
            PreflightCheck(
                "manifest_readable", "MANIFEST_SCHEMA", "FAIL", "not a JSON object", stamp
            )
        )
        return loaded
    loaded.data = data
    loaded.readable = True
    # Live checks cannot reconstruct absent release truths from legacy defaults,
    # coerce a string such as "false" to True, or erase recorded blockers.
    required = {"FILE_VALID", "EVIDENCE_STATE", "MODEL_STATUS", "RELEASE_DECISION", "certification_basis"}
    missing = required.difference(data)
    if missing or type(data.get("FILE_VALID")) is not bool:
        loaded.blockers.append(f"MANIFEST_TRUTHS_INVALID:missing={sorted(missing)}")
    try:
        CertificationManifest.model_validate(data)
    except (ValidationError, ValueError, TypeError) as exc:
        loaded.blockers.append(f"MANIFEST_CONTRACT_INVALID:{exc}")
    loaded.checks.append(
        PreflightCheck("manifest_readable", "MANIFEST_SCHEMA", "PASS", str(path), stamp)
    )
    version = data.get("manifest_version")
    if version in SUPPORTED_MANIFEST_VERSIONS:
        loaded.checks.append(
            PreflightCheck("manifest_schema", "MANIFEST_SCHEMA", "PASS", str(version), stamp)
        )
    else:
        loaded.blockers.append(f"MANIFEST_SCHEMA_UNSUPPORTED:{version!r}")
        loaded.checks.append(
            PreflightCheck(
                "manifest_schema", "MANIFEST_SCHEMA", "FAIL", f"unsupported {version!r}", stamp
            )
        )
    return loaded


def _stored_enum(data: Mapping[str, Any], key: str, enum, default):
    try:
        return enum(data.get(key, default.value)), None
    except ValueError:
        return default, f"MANIFEST_FIELD_INVALID:{key}={data.get(key)!r}"


def _output_binding(
    data: Mapping[str, Any], when: datetime
) -> tuple[list[PreflightCheck], list[str], bool]:
    """Rebind the certified bytes. Absent output is only a problem if it was certified."""
    stamp = _stamp(when)
    checks: list[PreflightCheck] = []
    blockers: list[str] = []
    output_path = data.get("output_path")
    stored_decision = data.get("RELEASE_DECISION") or (
        "CERTIFIED_UPLOAD_PACKAGE" if data.get("status") == "CERTIFIED" else "DO_NOT_UPLOAD"
    )
    if stored_decision != "CERTIFIED_UPLOAD_PACKAGE":
        if output_path:
            blockers.append(
                "OUTPUT_BINDING:DO_NOT_UPLOAD manifest must not point to an upload CSV"
            )
            checks.append(
                PreflightCheck(
                    "output_bytes", "FILE_BINDING", "FAIL",
                    "blocked manifest names an output", stamp,
                )
            )
        else:
            checks.append(
                PreflightCheck(
                    "output_bytes", "FILE_BINDING", "FAIL",
                    "manifest carries no certified output", stamp,
                )
            )
            blockers.append("OUTPUT_BINDING:manifest certified no upload bytes")
        return checks, blockers, False
    if not output_path or not Path(output_path).exists():
        blockers.append("OUTPUT_BINDING:certified output is missing")
        checks.append(
            PreflightCheck("output_bytes", "FILE_BINDING", "FAIL", "missing", stamp)
        )
        return checks, blockers, False
    try:
        actual = sha256_file(output_path)
    except OSError as exc:
        blockers.append(f"OUTPUT_BINDING:certified output could not be read: {exc}")
        checks.append(PreflightCheck("output_bytes", "FILE_BINDING", "FAIL", str(exc), stamp))
        return checks, blockers, False
    if actual != data.get("output_sha256"):
        blockers.append("OUTPUT_BINDING:certified output hash changed")
        checks.append(
            PreflightCheck("output_bytes", "FILE_BINDING", "FAIL", f"sha256={actual}", stamp)
        )
        return checks, blockers, False
    checks.append(
        PreflightCheck("output_bytes", "FILE_BINDING", "PASS", f"sha256={actual}", stamp)
    )
    return checks, blockers, True


def _input_binding(
    data: Mapping[str, Any],
    supplied: Mapping[str, str | Path | None],
    when: datetime,
) -> tuple[list[PreflightCheck], list[str]]:
    stamp = _stamp(when)
    checks: list[PreflightCheck] = []
    blockers: list[str] = []
    recorded = data.get("input_hashes")
    recorded = recorded if isinstance(recorded, Mapping) else {}
    for name in BINDABLE_INPUTS:
        path = supplied.get(name)
        if not path:
            continue
        expected = recorded.get(name)
        if not expected:
            blockers.append(f"INPUT_BINDING:{name} is not recorded in this manifest")
            checks.append(
                PreflightCheck(f"input_{name}", "FILE_BINDING", "FAIL", "not recorded", stamp)
            )
            continue
        try:
            actual = sha256_file(path)
        except OSError as exc:
            blockers.append(f"INPUT_BINDING:{name} could not be read: {exc}")
            checks.append(
                PreflightCheck(f"input_{name}", "FILE_BINDING", "FAIL", str(exc), stamp)
            )
            continue
        if actual != expected:
            blockers.append(
                f"INPUT_BINDING:{name} on disk does not match the certified hash"
            )
            checks.append(
                PreflightCheck(
                    f"input_{name}", "FILE_BINDING", "FAIL", f"sha256={actual}", stamp
                )
            )
        else:
            checks.append(
                PreflightCheck(
                    f"input_{name}", "FILE_BINDING", "PASS", f"sha256={actual}", stamp
                )
            )
    return checks, blockers


def _lock_binding(
    data: Mapping[str, Any], salaries: str | Path | None, when: datetime
) -> tuple[list[PreflightCheck], list[str]]:
    """Re-derive player locks from the current salary pool at `when`.

    A package certified before lock is not uploadable after it. The manifest
    records the selected exact IDs inside the official-status evidence record;
    the lock times come from the salary CSV, which is why the live check asks
    for it.
    """
    stamp = _stamp(when)
    if not salaries:
        return (
            [
                PreflightCheck(
                    "selected_player_locks", "LIVE_RECOMPUTE", "FAIL",
                    "salary CSV not supplied, locks were not re-derived", stamp,
                )
            ],
            ["LIVE_BINDING_INCOMPLETE:selected player locks need the current salary CSV"],
        )
    from .dk import parse_salaries, parse_entries  # local import keeps module import cheap

    try:
        slate = parse_salaries(salaries)
    except Exception as exc:  # noqa: BLE001 - any parse failure is a live blocker
        return (
            [
                PreflightCheck(
                    "selected_player_locks", "LIVE_RECOMPUTE", "FAIL", str(exc), stamp
                )
            ],
            [f"LIVE_BINDING_INCOMPLETE:salary CSV could not be parsed: {exc}"],
        )
    selected: set[str] = set()
    inactive_values: set[str] = set()
    for record in data.get("evidence", ()) or ():
        if not isinstance(record, Mapping):
            continue
        if record.get("field") != "official_inactive_status":
            continue
        value = record.get("value")
        if isinstance(value, Mapping):
            selected.update(str(key) for key in value)
            inactive_values.update(str(key) for key, status in value.items() if status != "ACTIVE")
    if not selected:
        return (
            [
                PreflightCheck(
                    "selected_player_locks", "LIVE_RECOMPUTE", "FAIL",
                    "manifest records no selected exact IDs", stamp,
                )
            ],
            ["LIVE_BINDING_INCOMPLETE:manifest records no selected exact IDs to re-lock"],
        )
    try:
        exported = parse_entries(data["output_path"])
        actual_ids = {cell for entry in exported.authorizations for cell in entry.existing_cells}
        if actual_ids != selected or inactive_values:
            raise ValueError(
                f"activity IDs do not cover the exported ACTIVE roster: "
                f"missing={sorted(actual_ids - selected)}, extra={sorted(selected - actual_ids)}, "
                f"nonactive={sorted(inactive_values)}"
            )
    except (OSError, ValueError, TypeError, KeyError) as exc:
        return (
            [PreflightCheck("selected_player_locks", "LIVE_RECOMPUTE", "FAIL", str(exc), stamp)],
            [f"LIVE_BINDING_INCOMPLETE:{exc}"],
        )
    by_id = {player.dk_id: player for player in slate.players}
    unknown = sorted(dk_id for dk_id in selected if dk_id not in by_id)
    if unknown:
        return (
            [
                PreflightCheck(
                    "selected_player_locks", "LIVE_RECOMPUTE", "FAIL",
                    f"IDs absent from the current pool: {unknown}", stamp,
                )
            ],
            [f"SELECTED_ID_NOT_IN_CURRENT_POOL:{unknown}"],
        )
    locked = sorted(
        dk_id for dk_id in selected if by_id[dk_id].lock_at.astimezone(timezone.utc) <= when
    )
    if locked:
        return (
            [
                PreflightCheck(
                    "selected_player_locks", "LIVE_RECOMPUTE", "FAIL",
                    f"already locked: {locked}", stamp,
                )
            ],
            [f"SELECTED_PLAYER_ALREADY_LOCKED:{locked}"],
        )
    earliest = min(by_id[dk_id].lock_at for dk_id in selected).astimezone(timezone.utc)
    return (
        [
            PreflightCheck(
                "selected_player_locks", "LIVE_RECOMPUTE", "PASS",
                f"{len(selected)} selected IDs, earliest lock {_stamp(earliest)}", stamp,
            )
        ],
        [],
    )


def _rebuild_evidence(
    data: Mapping[str, Any], when: datetime
) -> tuple[tuple[EvidenceRecord, ...], list[PreflightCheck], list[str]]:
    stamp = _stamp(when)
    raw = data.get("evidence")
    if not isinstance(raw, list):
        return (
            (),
            [
                PreflightCheck(
                    "evidence_schema", "MANIFEST_SCHEMA", "FAIL", "missing evidence", stamp
                )
            ],
            ["MANIFEST_EVIDENCE_INVALID:manifest carries no evidence list"],
        )
    records: list[EvidenceRecord] = []
    blockers: list[str] = []
    for index, item in enumerate(raw):
        try:
            records.append(EvidenceRecord.model_validate(item))
        except ValidationError as exc:
            blockers.append(
                f"MANIFEST_EVIDENCE_INVALID:record {index}: {exc.error_count()} errors"
            )
    checks = [
        PreflightCheck(
            "evidence_schema",
            "MANIFEST_SCHEMA",
            "FAIL" if blockers else "PASS",
            f"{len(records)} of {len(raw)} records rebuilt",
            stamp,
        )
    ]
    return tuple(records), checks, blockers


def historical_artifact_integrity(
    manifest_path: str | Path, *, checked_at: datetime | None = None
) -> dict[str, Any]:
    """Archival integrity only. Never a current release decision."""
    when = (checked_at or release_clock()).astimezone(timezone.utc)
    stamp = _stamp(when)
    loaded = _load_manifest(manifest_path, when)
    problems = list(loaded.blockers)
    checks = list(loaded.checks)
    stored_decision = None
    stored_evidence_state = None
    if loaded.readable:
        stored_decision = loaded.data.get("RELEASE_DECISION") or (
            "CERTIFIED_UPLOAD_PACKAGE"
            if loaded.data.get("status") == "CERTIFIED"
            else "DO_NOT_UPLOAD"
        )
        stored_evidence_state = loaded.data.get("EVIDENCE_STATE")
        output_checks, output_blockers, _ = _output_binding(loaded.data, when)
        # Archival integrity does not require that a blocked package certified
        # bytes; it only requires that whatever it recorded still matches.
        checks.extend(output_checks)
        problems.extend(
            blocker
            for blocker in output_blockers
            if blocker != "OUTPUT_BINDING:manifest certified no upload bytes"
        )
    integrity = "PASS" if not problems else "FAIL"
    return {
        "check_scope": HISTORICAL_SCOPE,
        "checked_at": stamp,
        "ARTIFACT_INTEGRITY": integrity,
        "status": integrity,
        "manifest_stored_RELEASE_DECISION": stored_decision,
        "manifest_stored_EVIDENCE_STATE": stored_evidence_state,
        "RELEASE_DECISION": "DO_NOT_UPLOAD",
        "release_decision_basis": "HISTORICAL_ONLY",
        "FILE_VALID": integrity == "PASS",
        "checks": [check.as_dict() for check in checks],
        "problems": problems,
        "meaning": (
            "Historical artifact integrity answers whether the recorded bytes still"
            " match the recorded hashes. It re-derives nothing at the current clock"
            " and never renews a certification. Run preflight for a current"
            " pre-upload decision."
        ),
        "next": "sh ./nfl.sh preflight --manifest <manifest> --salaries <current salary CSV>",
    }


def live_pre_upload_check(
    manifest_path: str | Path,
    *,
    salaries: str | Path | None = None,
    entries: str | Path | None = None,
    assignments: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Re-derive the release decision at the current clock. Fail closed."""
    when = (now or release_clock()).astimezone(timezone.utc)
    stamp = _stamp(when)
    loaded = _load_manifest(manifest_path, when)
    checks = list(loaded.checks)
    file_blockers: list[str] = []
    evidence_blockers: list[str] = []
    safety_blockers: list[str] = list(loaded.blockers)

    if not loaded.readable:
        policy = derive_release_policy(
            file_valid=False,
            evidence_state=ReleaseEvidenceState.CONFLICTED,
            model_status=ModelStatus.UNVALIDATED,
            certification_basis=CertificationBasis.MANUAL_GUARDRAIL,
            safety_blockers=safety_blockers,
        )
        return _live_payload(policy, stamp, checks, safety_blockers)

    data = loaded.data
    stored_model_status, model_problem = _stored_enum(
        data, "MODEL_STATUS", ModelStatus, ModelStatus.UNVALIDATED
    )
    stored_basis, basis_problem = _stored_enum(
        data, "certification_basis", CertificationBasis, CertificationBasis.MANUAL_GUARDRAIL
    )
    for problem in (model_problem, basis_problem):
        if problem:
            safety_blockers.append(problem)

    records, evidence_checks, evidence_schema_blockers = _rebuild_evidence(data, when)
    checks.extend(evidence_checks)
    safety_blockers.extend(evidence_schema_blockers)

    try:
        required = _required_hard_fields(stored_basis)
    except PreflightError as exc:
        safety_blockers.append(str(exc))
        required = ()
    present = {record.field for record in records if record.hard_gate}
    missing = [name for name in required if name not in present]
    if missing:
        safety_blockers.append(f"MANIFEST_EVIDENCE_SCOPE:missing {sorted(missing)}")
    checks.append(
        PreflightCheck(
            "evidence_scope",
            "LIVE_RECOMPUTE",
            "FAIL" if missing or not required else "PASS",
            f"required {len(required)}, present {len(present)}",
            stamp,
        )
    )

    evidence_state, live_blockers = aggregate_evidence_state(
        records, required_hard_fields=required, now=when, final_release=True
    )
    evidence_blockers.extend(live_blockers)
    non_passing = sorted(
        {
            record.field
            for record in records
            if record.hard_gate
            and record.state_at(when)
            not in {EvidenceState.PASS, EvidenceState.NOT_APPLICABLE}
        }
    )
    checks.append(
        PreflightCheck(
            "evidence_states_at_current_clock",
            "LIVE_RECOMPUTE",
            "FAIL" if non_passing else "PASS",
            f"{evidence_state.value}; non-passing fields {non_passing}",
            stamp,
        )
    )

    output_checks, output_blockers, output_bound = _output_binding(data, when)
    checks.extend(output_checks)
    file_blockers.extend(output_blockers)

    input_checks, input_blockers = _input_binding(
        data, {"salary": salaries, "entries": entries, "assignments": assignments}, when
    )
    checks.extend(input_checks)
    file_blockers.extend(input_blockers)

    lock_checks, lock_blockers = _lock_binding(data, salaries, when)
    checks.extend(lock_checks)
    safety_blockers.extend(lock_blockers)

    stored_file_valid = bool(data.get("FILE_VALID"))
    file_valid = stored_file_valid and output_bound and not file_blockers

    policy = derive_release_policy(
        file_valid=file_valid,
        evidence_state=evidence_state,
        model_status=stored_model_status,
        certification_basis=stored_basis,
        file_blockers=file_blockers,
        evidence_blockers=evidence_blockers,
        model_blockers=list(data.get("model_blockers", ()) or ()),
        safety_blockers=safety_blockers,
    )
    return _live_payload(policy, stamp, checks, [])


def _live_payload(
    policy, stamp: str, checks: Iterable[PreflightCheck], extra_blockers: Iterable[str]
) -> dict[str, Any]:
    values = policy.truth_values()
    blockers = list(policy.blockers) + [
        blocker for blocker in extra_blockers if blocker not in policy.blockers
    ]
    return {
        "check_scope": LIVE_SCOPE,
        "checked_at": stamp,
        **values,
        "certification_basis": policy.certification_basis.value,
        "status": policy.status,
        "blockers": blockers,
        "checks": [check.as_dict() for check in checks],
        "meaning": (
            "Every state above was re-derived at checked_at. A"
            " CERTIFIED_UPLOAD_PACKAGE here means the exact bytes passed every"
            " current hard gate at that instant, and nothing about lineup"
            " quality. Evidence expires; recheck immediately before upload."
        ),
    }
