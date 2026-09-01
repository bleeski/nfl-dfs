from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .contracts import EvidenceRecord, EvidenceState, SalaryPlayer


class EvidenceError(ValueError):
    pass


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


def parse_official_inactives(
    path: str | Path,
    players: Iterable[SalaryPlayer],
) -> tuple[dict[str, str], tuple[str, ...]]:
    active_pool = list(players)
    by_id = {player.dk_id: player for player in active_pool}
    by_gsis: dict[str, SalaryPlayer] = {}
    del by_gsis
    teams = {player.team for player in active_pool}
    statuses: dict[str, str] = {}
    problems: list[str] = []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        expected = {"TEAM", "PLAYER_OR_GSIS_ID", "STATUS", "SOURCE_URL", "OBSERVED_AT"}
        if not reader.fieldnames or set(reader.fieldnames) != expected:
            raise EvidenceError(
                "inactive CSV header must be TEAM,PLAYER_OR_GSIS_ID,STATUS,SOURCE_URL,OBSERVED_AT"
            )
        for row_number, row in enumerate(reader, start=2):
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
            if not source_url.startswith("https://"):
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
            statuses[player_id] = status
    return statuses, tuple(problems)
