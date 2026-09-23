"""The latest deliverable (Session 05, R28): the one validated file a run would hand over.

`LATEST_DELIVERABLE.json` (`nfl_latest_deliverable_v1` in `docs/DATA_CONTRACTS.md`)
sits in a run's output folder and names one entry file inside that folder: its
path, SHA-256, the salary and entries snapshots it was built from, its Entry ID
coverage and its `nfl_release_truths_v2`. Nothing advertises the file until
`revalidate` has passed the bytes on disk, and `read_latest` revalidates again
before it returns, so the pointer never vouches for bytes nobody just checked.

- `publish` writes a run's first pointer.
- `replace` swaps it for a file of the same two inputs whose coverage is equal
  or better (Session 06: the baseline first, then an improvement).
- `read_latest` reads it back and revalidates the file it names.

Every write is atomic: the bytes go to a temporary file in the same folder, are
flushed and synced, and `os.replace` puts them in place, so a reader sees the
old pointer or the new one and never part of either.

Revalidation is independent of whoever built the file. Both snapshots are
parsed afresh, and the checks are the integrity gates `CLAUDE.md` names (exact
DraftKings IDs, hashes, entry mapping, blank-cell authority, Classic/Showdown
mode) plus R29 distinctness. It judges no evidence, model or policy; the truths
the pointer carries do that, and `RELEASE_DECISION` stays what they say.

`discrepancy_limitations` and `blocker_limitations` turn codes into registry
limitations for the paths that publish here. A code the registry does not hold
is `GATE_CODE_UNCLASSIFIED`, a `V` gate: what nobody classified cannot be shown
to spare the file, so it withholds it (fail closed).
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from .contracts import DeliveryLimitation, DeliveryState, GateClass, ReleaseTruthsV2
from .dk import parse_entries, parse_entry_bytes, parse_salaries, reconcile_template
from .gate_registry import GateRegistry
from .hashing import sha256_bytes, sha256_file
from .lineups import validate_lineup
from .referee import audit_output_bytes

POINTER_NAME = "LATEST_DELIVERABLE.json"
POINTER_VERSION = "nfl_latest_deliverable_v1"
UPLOAD_PREFIX = "DK_UPLOAD_"
CHECKS_RUN = (
    "NAME_NOT_UPLOAD_SHAPED_AND_INSIDE_THE_RUN_FOLDER",
    "TRUTHS_DESCRIBE_A_VALID_DELIVERED_FILE",
    "FILE_SHA256",
    "SALARY_AND_ENTRIES_SNAPSHOT_SHA256",
    "FRESH_PARSE_OF_BOTH_SNAPSHOTS",
    "REPARSE_OF_THE_FILE_AND_ITS_MODE",
    "ENTRY_ID_ORDER",
    "FILLED_AND_BLANK_ROWS_EQUAL_THE_TRUTHS",
    "BYTE_AUDIT_AGAINST_THE_TEMPLATE",
    "SHARED_VALIDATOR_ON_EVERY_FILLED_ROW",
    "EXACT_ROSTER_DISTINCTNESS",
)
WARNING = (
    "PRIOR_ONLY / DO_NOT_UPLOAD unless RELEASE_DECISION says otherwise. DELIVERY_STATE "
    "says a valid file exists to hand over; it is not upload clearance."
)
_CODE = re.compile(r"[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+")
_FIELDS = frozenset({
    "schema_version", "published_at", "run_id", "producer", "file", "inputs", "mode",
    "coverage", "release_truths", "revalidation", "supersedes", "warning",
})


class DeliveryPointerError(ValueError):
    """The pointer or the file it names cannot be trusted; `problems` holds each `CODE:detail`."""

    def __init__(self, message: str, *, problems: Iterable[str] = ()) -> None:
        super().__init__(message)
        self.problems = tuple(problems) or (message,)


@dataclass(frozen=True)
class Deliverable:
    """A file offered for delivery, and what its producer says it holds."""

    path: Path
    sha256: str
    file_kind: str
    producer: str
    run_id: str
    salary_path: Path
    salary_sha256: str
    entry_path: Path
    entry_sha256: str
    truths: ReleaseTruthsV2


@dataclass(frozen=True)
class LatestDeliverable:
    """A pointer read back, or just written, whose file revalidated."""

    pointer_path: Path
    pointer_sha256: str
    record: dict[str, object]
    deliverable: Deliverable

    def summary(self) -> dict[str, object]:
        truths = self.deliverable.truths
        return {
            "pointer": str(self.pointer_path),
            "pointer_sha256": self.pointer_sha256,
            "path": str(self.deliverable.path),
            "sha256": self.deliverable.sha256,
            "file_kind": self.deliverable.file_kind,
            "producer": self.deliverable.producer,
            "DELIVERY_STATE": truths.delivery_state.value,
            "delivered_rows": len(truths.delivered_entry_ids),
            "unfilled_entry_ids": list(truths.unfilled_entry_ids),
        }


def revalidate(item: Deliverable, *, root: str | Path) -> tuple[str, ...]:
    """Every reason the file on disk is not what `item` says, checked from scratch."""

    problems: list[str] = []
    try:
        _revalidate(item, Path(root).resolve(), problems)
    except Exception as exc:  # noqa: BLE001 - a check that cannot finish proves nothing
        problems.append(f"DELIVERABLE_REVALIDATION_FAILED:{type(exc).__name__}:{exc}")
    return tuple(problems)


def _revalidate(item: Deliverable, root: Path, problems: list[str]) -> None:
    path = Path(item.path).resolve()
    if path.name.startswith(UPLOAD_PREFIX):
        problems.append(f"DELIVERABLE_UPLOAD_NAME_PROHIBITED:{path.name}")
    if not path.is_relative_to(root) or path == root:
        problems.append(f"DELIVERABLE_OUTSIDE_RUN_FOLDER:{path} is not inside {root}")
    truths = item.truths
    if truths.delivery_state is DeliveryState.NO_DELIVERABLE or not truths.delivered_file_valid:
        problems.append(f"DELIVERABLE_STATE_NOT_DELIVERABLE:{truths.delivery_state.value}")
    if problems:
        return
    if not path.is_file():
        problems.append(f"DELIVERABLE_FILE_MISSING:{path}")
        return
    raw = path.read_bytes()
    if sha256_bytes(raw) != item.sha256:
        problems.append(f"DELIVERABLE_SHA256_MISMATCH:actual={sha256_bytes(raw)}:expected={item.sha256}")
        return
    for label, source, digest in (
        ("salaries", Path(item.salary_path), item.salary_sha256),
        ("entries", Path(item.entry_path), item.entry_sha256),
    ):
        actual = sha256_file(source) if source.is_file() else "MISSING"
        if actual != digest:
            problems.append(f"DELIVERABLE_INPUT_SHA256_MISMATCH:{label}:actual={actual}:expected={digest}")
    if problems:
        return
    try:
        slate = parse_salaries(item.salary_path)
        template = parse_entries(item.entry_path)
        reconcile_template(template, slate)
    except ValueError as exc:
        problems.append(f"DELIVERABLE_INPUT_PARSE_FAILED:{exc}")
        return
    try:
        reparsed = parse_entry_bytes(raw, source_name=path.name)
    except ValueError as exc:
        problems.append(f"DELIVERABLE_REPARSE_FAILED:{exc}")
        return
    try:
        if reparsed.roster_columns != template.roster_columns:
            raise ValueError(f"file columns {list(reparsed.roster_columns)}, "
                             f"template columns {list(template.roster_columns)}")
        reconcile_template(reparsed, slate)
    except ValueError as exc:
        problems.append(f"DELIVERABLE_MODE_MISMATCH:{exc}")
        return
    order = [entry.entry_id for entry in template.authorizations]
    if [entry.entry_id for entry in reparsed.authorizations] != order:
        problems.append("DELIVERABLE_ENTRY_ORDER_MISMATCH:the file's Entry IDs are not the template's, in its order")
        return
    authorized = [entry.entry_id for entry in template.authorizations if not any(entry.existing_cells)]
    rows = {entry.entry_id: entry.existing_cells for entry in reparsed.authorizations}
    filled = {eid: rows[eid] for eid in authorized if any(rows[eid])}
    blank = tuple(eid for eid in authorized if not any(rows[eid]))
    if (
        tuple(truths.delivered_entry_ids) != tuple(filled)
        or tuple(truths.unfilled_entry_ids) != blank
    ):
        problems.append(
            "DELIVERABLE_COVERAGE_MISMATCH:the file fills "
            f"{list(filled)} and leaves {list(blank)} blank, the truths say "
            f"{list(truths.delivered_entry_ids)} and {list(truths.unfilled_entry_ids)}"
        )
    audit = audit_output_bytes(item.entry_path, raw, template, filled)
    problems.extend(f"DELIVERABLE_BYTE_AUDIT_FAILED:{problem}" for problem in audit.problems)
    keys: dict[str, str] = {}
    for entry_id, roster in filled.items():
        result = validate_lineup(slate, roster)
        if result.lineup is None:
            problems.append(f"DELIVERABLE_LINEUP_INVALID:{entry_id}:{' | '.join(result.errors)}")
            continue
        earlier = keys.setdefault(result.lineup.canonical_key, entry_id)
        if earlier != entry_id:
            problems.append(f"DELIVERABLE_LINEUP_DUPLICATE:{entry_id} repeats {earlier}")


def _canonical(record: Mapping[str, object]) -> bytes:
    return (json.dumps(record, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode("utf-8")


def _atomic_write(path: Path, payload: bytes) -> str:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with open(temporary, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return sha256_file(path)


def _record(
    item: Deliverable,
    *,
    root: Path,
    now: datetime,
    supersedes: Mapping[str, object] | None,
) -> dict[str, object]:
    path = Path(item.path).resolve()
    truths = item.truths
    return {
        "schema_version": POINTER_VERSION,
        "published_at": now.astimezone(timezone.utc).isoformat(),
        "run_id": item.run_id,
        "producer": item.producer,
        "file": {
            "path": path.relative_to(root).as_posix(),
            "sha256": item.sha256,
            "bytes": path.stat().st_size,
            "file_kind": item.file_kind,
        },
        "inputs": {
            "salaries": {"path": str(Path(item.salary_path).resolve()), "sha256": item.salary_sha256},
            "entries": {"path": str(Path(item.entry_path).resolve()), "sha256": item.entry_sha256},
        },
        "mode": parse_entries(item.entry_path).mode.value,
        "coverage": {
            "delivered_entry_ids": list(truths.delivered_entry_ids),
            "unfilled_entry_ids": list(truths.unfilled_entry_ids),
        },
        "release_truths": truths.model_dump(mode="json", by_alias=True),
        "revalidation": {"status": "PASS", "checks_run": list(CHECKS_RUN)},
        "supersedes": dict(supersedes) if supersedes is not None else None,
        "warning": WARNING,
    }


def _write(root: Path, item: Deliverable, *, now: datetime | None,
           supersedes: Mapping[str, object] | None) -> LatestDeliverable:
    problems = revalidate(item, root=root)
    if problems:
        raise DeliveryPointerError(";".join(problems), problems=problems)
    record = _record(item, root=root, now=now or datetime.now(timezone.utc), supersedes=supersedes)
    payload = _canonical(record)
    pointer = root / POINTER_NAME
    if _atomic_write(pointer, payload) != sha256_bytes(payload):
        raise DeliveryPointerError(f"DELIVERY_POINTER_WRITE_MISMATCH:{pointer}")
    return LatestDeliverable(pointer, sha256_bytes(payload), record, item)


def publish(root: str | Path, item: Deliverable, *, now: datetime | None = None) -> LatestDeliverable:
    """Name `item` as the run's first deliverable, after it revalidates."""

    base = Path(root).resolve()
    if (base / POINTER_NAME).exists():
        raise DeliveryPointerError(f"DELIVERY_POINTER_EXISTS:{base / POINTER_NAME}, use replace")
    return _write(base, item, now=now, supersedes=None)


def _load(root: Path) -> tuple[Path, bytes, dict[str, object], Deliverable] | None:
    pointer = root / POINTER_NAME
    if not pointer.exists():
        return None
    raw = pointer.read_bytes()
    try:
        record = json.loads(raw.decode("utf-8"))
        if not isinstance(record, dict) or set(record) != _FIELDS:
            raise ValueError(f"fields {sorted(record) if isinstance(record, dict) else type(record).__name__}")
        if record["schema_version"] != POINTER_VERSION:
            raise ValueError(f"schema_version {record['schema_version']!r}")
        file, inputs = record["file"], record["inputs"]
        relative = Path(str(file["path"]))
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"file path {relative} is not inside the run folder")
        item = Deliverable(
            path=root / relative,
            sha256=str(file["sha256"]),
            file_kind=str(file["file_kind"]),
            producer=str(record["producer"]),
            run_id=str(record["run_id"]),
            salary_path=Path(str(inputs["salaries"]["path"])),
            salary_sha256=str(inputs["salaries"]["sha256"]),
            entry_path=Path(str(inputs["entries"]["path"])),
            entry_sha256=str(inputs["entries"]["sha256"]),
            truths=ReleaseTruthsV2.model_validate(record["release_truths"]),
        )
    except (UnicodeDecodeError, ValueError, KeyError, TypeError, ValidationError) as exc:
        raise DeliveryPointerError(f"DELIVERY_POINTER_INVALID:{pointer}:{type(exc).__name__}:{exc}") from exc
    return pointer, raw, record, item


def read_latest(root: str | Path) -> LatestDeliverable | None:
    """The run's pointer, after the file it names revalidates; `None` when there is none."""

    base = Path(root).resolve()
    loaded = _load(base)
    if loaded is None:
        return None
    pointer, raw, record, item = loaded
    problems = revalidate(item, root=base)
    if problems:
        raise DeliveryPointerError(";".join(problems), problems=problems)
    return LatestDeliverable(pointer, sha256_bytes(raw), record, item)


def replace(root: str | Path, item: Deliverable, *, now: datetime | None = None) -> LatestDeliverable:
    """Point at `item` instead: same inputs, and at least as many delivered rows.

    A current file that no longer revalidates is replaced by any file that does,
    whatever its coverage; a current file that does is replaced only by one that
    delivers as many rows or more.
    """

    base = Path(root).resolve()
    loaded = _load(base)
    if loaded is None:
        raise DeliveryPointerError(f"DELIVERY_POINTER_MISSING:{base / POINTER_NAME}, use publish")
    _, raw, _, current = loaded
    if (current.salary_sha256, current.entry_sha256) != (item.salary_sha256, item.entry_sha256):
        raise DeliveryPointerError("DELIVERY_POINTER_INPUTS_DIFFER:the replacement was built from other "
                                   "salary or entries bytes than the file it would replace")
    current_problems = revalidate(current, root=base)
    have = len(current.truths.delivered_entry_ids)
    offered = len(item.truths.delivered_entry_ids)
    if not current_problems and offered < have:
        raise DeliveryPointerError(f"DELIVERY_POINTER_COVERAGE_REGRESSION:the replacement delivers "
                                   f"{offered} rows, the current file {have}")
    supersedes = {
        "pointer_sha256": sha256_bytes(raw),
        "file_sha256": current.sha256,
        "producer": current.producer,
        "delivered_rows": have,
        "revalidation": "FAIL" if current_problems else "PASS",
        "problems": list(current_problems),
    }
    return _write(base, item, now=now, supersedes=supersedes)


def discrepancy_limitations(text: str, registry: GateRegistry) -> tuple[DeliveryLimitation, ...]:
    """Each `;`-joined `CODE:detail` fragment of one discrepancy, as a registry limitation."""

    fragments = [fragment.strip() for fragment in str(text).split(";") if fragment.strip()]
    return tuple(_limitation(fragment, registry) for fragment in fragments or [str(text)])


def blocker_limitations(blockers: Iterable[str], registry: GateRegistry) -> tuple[DeliveryLimitation, ...]:
    """One registry limitation per blocker, by its leading code; the text is the detail."""

    return tuple(_limitation(str(text), registry) for text in blockers)


def _limitation(text: str, registry: GateRegistry) -> DeliveryLimitation:
    head = text.split(":", 1)[0].strip()
    if _CODE.fullmatch(head) and head in registry.codes:
        return registry.limitation(head, detail=text)
    return registry.limitation("GATE_CODE_UNCLASSIFIED", detail=text)


def withholds(limitations: Iterable[DeliveryLimitation]) -> bool:
    """Whether any limitation is an integrity (`V`) gate, which stops the file (R28)."""

    return any(item.gate_class is GateClass.V for item in limitations)
