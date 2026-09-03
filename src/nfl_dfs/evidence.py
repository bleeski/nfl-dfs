from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Mapping
from urllib.parse import urlparse

from pydantic import ValidationError

from .contracts import EvidenceRecord, EvidenceState, SalaryPlayer, SourceLedger
from .hashing import sha256_file
from .sources import SourcePolicyError, validate_url_policy


class EvidenceError(ValueError):
    pass


@dataclass(frozen=True)
class InactiveStatusSnapshot:
    statuses: dict[str, str]
    observed_at_by_id: dict[str, datetime]
    source_url_by_id: dict[str, str]
    problems: tuple[str, ...]


def evaluate_hard_gates(
    evidence: Iterable[EvidenceRecord], now: datetime | None = None
) -> tuple[bool, tuple[str, ...]]:
    when = now or datetime.now(timezone.utc)
    blockers: list[str] = []
    for record in evidence:
        if not record.hard_gate:
            continue
        state = record.state_at(when)
        if state in {EvidenceState.NOT_APPLICABLE, EvidenceState.NOT_YET_DUE}:
            continue
        if state is not EvidenceState.PASS:
            blockers.append(f"{record.subject}.{record.field}:{state.value}:{record.reason}")
    return not blockers, tuple(blockers)


def validate_source_ledger(
    path: str | Path,
    *,
    expected_outputs: Mapping[str, str],
    now: datetime | None = None,
) -> SourceLedger:
    ledger_path = Path(path).resolve()
    try:
        payload = json.loads(ledger_path.read_text(encoding="utf-8"))
        ledger = SourceLedger.model_validate(payload)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise EvidenceError(f"invalid source ledger contract: {exc}") from exc

    expected = dict(expected_outputs)
    if set(ledger.derived) != set(expected):
        raise EvidenceError(
            "source ledger derived outputs must be exactly "
            f"{sorted(expected)}; received {sorted(ledger.derived)}"
        )
    for name, digest in expected.items():
        if ledger.derived[name] != digest:
            raise EvidenceError(
                f"source ledger derived hash mismatch for {name}: expected {digest}"
            )

    checked_at = now or datetime.now(timezone.utc)
    future_limit = checked_at + timedelta(minutes=5)
    for entry in ledger.entries:
        try:
            validate_url_policy(entry.source_uri)
        except SourcePolicyError as exc:
            raise EvidenceError(
                f"source ledger URI is not approved: {entry.source_uri}: {exc}"
            ) from exc
        captured_at = entry.captured_at.astimezone(timezone.utc)
        if captured_at > future_limit:
            raise EvidenceError(f"source ledger captured_at is in the future: {entry.path}")
        if entry.observed_at is not None:
            observed_at = entry.observed_at.astimezone(timezone.utc)
            if observed_at > future_limit:
                raise EvidenceError(
                    f"source ledger observed_at is in the future: {entry.path}"
                )
            if observed_at > captured_at + timedelta(minutes=5):
                raise EvidenceError(
                    f"source ledger observed_at follows captured_at: {entry.path}"
                )
        artifact = Path(entry.path)
        if not artifact.is_absolute():
            artifact = ledger_path.parent / artifact
        try:
            artifact = artifact.resolve(strict=True)
        except OSError as exc:
            raise EvidenceError(f"source ledger artifact is missing: {entry.path}") from exc
        if not artifact.is_file():
            raise EvidenceError(f"source ledger artifact is missing: {entry.path}")
        if sha256_file(artifact) != entry.artifact_id:
            raise EvidenceError(
                f"source ledger artifact hash mismatch: {entry.path}"
            )
    return ledger


def parse_official_inactive_snapshot(
    path: str | Path,
    players: Iterable[SalaryPlayer],
) -> InactiveStatusSnapshot:
    active_pool = list(players)
    by_id = {player.dk_id: player for player in active_pool}
    teams = {player.team for player in active_pool}
    statuses: dict[str, str] = {}
    observations: dict[str, datetime] = {}
    source_urls: dict[str, str] = {}
    problems: list[str] = []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        exact = ("TEAM", "PLAYER_OR_GSIS_ID", "STATUS", "SOURCE_URL", "OBSERVED_AT")
        if tuple(reader.fieldnames or ()) != exact:
            raise EvidenceError(
                "inactive CSV header must be TEAM,PLAYER_OR_GSIS_ID,STATUS,SOURCE_URL,OBSERVED_AT"
            )
        for row_number, row in enumerate(reader, start=2):
            if None in row or any(value is None for value in row.values()):
                raise EvidenceError(
                    f"inactive row {row_number} has missing or extra cells"
                )
            team = row["TEAM"].strip().upper()
            player_id = row["PLAYER_OR_GSIS_ID"].strip()
            status = row["STATUS"].strip().upper()
            source_url = row["SOURCE_URL"].strip()
            observed_raw = row["OBSERVED_AT"].strip()
            if team not in teams:
                problems.append(f"row {row_number}: unknown team {team}")
                continue
            player = by_id.get(player_id)
            if player is None:
                problems.append(f"row {row_number}: exact player ID not found: {player_id}")
                continue
            if player.team != team:
                problems.append(f"row {row_number}: player/team conflict")
                continue
            if status not in {"INACTIVE", "ACTIVE"}:
                problems.append(f"row {row_number}: status must be ACTIVE or INACTIVE")
                continue
            parsed_url = urlparse(source_url)
            if parsed_url.scheme.lower() != "https" or not parsed_url.hostname:
                problems.append(f"row {row_number}: HTTPS source URL required")
                continue
            try:
                observed = datetime.fromisoformat(observed_raw.replace("Z", "+00:00"))
                if observed.tzinfo is None:
                    raise ValueError
            except ValueError:
                problems.append(f"row {row_number}: timezone-aware OBSERVED_AT required")
                continue
            if player_id in statuses and statuses[player_id] != status:
                problems.append(f"row {row_number}: conflicting status for {player_id}")
                continue
            previous = observations.get(player_id)
            if previous is None or observed > previous:
                statuses[player_id] = status
                observations[player_id] = observed.astimezone(timezone.utc)
                source_urls[player_id] = source_url
    return InactiveStatusSnapshot(statuses, observations, source_urls, tuple(problems))


def parse_official_inactives(
    path: str | Path,
    players: Iterable[SalaryPlayer],
) -> tuple[dict[str, str], tuple[str, ...]]:
    """Compatibility wrapper for callers that need only statuses and problems."""
    snapshot = parse_official_inactive_snapshot(path, players)
    return snapshot.statuses, snapshot.problems
