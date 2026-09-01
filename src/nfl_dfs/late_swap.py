from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

from .contracts import SlateContract
from .lineups import validate_lineup


@dataclass(frozen=True)
class LateSwapAudit:
    valid: bool
    problems: tuple[str, ...]


def audit_late_swap(
    *,
    slate: SlateContract,
    original: Mapping[str, tuple[str, ...]],
    proposed: Mapping[str, tuple[str, ...]],
    now: datetime,
) -> LateSwapAudit:
    problems: list[str] = []
    if set(original) != set(proposed):
        problems.append("Entry-ID set changed")
        return LateSwapAudit(False, tuple(problems))
    by_id = {player.dk_id: player for player in slate.players}
    for entry_id in sorted(original):
        before = original[entry_id]
        after = proposed[entry_id]
        if len(before) != len(after):
            problems.append(f"{entry_id}: roster width changed")
            continue
        locked: dict[int, str] = {}
        for slot, dk_id in enumerate(before):
            player = by_id.get(dk_id)
            if player is None:
                problems.append(f"{entry_id}: original ID {dk_id} missing from current pool")
                continue
            if player.lock_at <= now:
                locked[slot] = dk_id
        validation = validate_lineup(slate, after, locked_slots=locked)
        problems.extend(f"{entry_id}: {problem}" for problem in validation.errors)
    return LateSwapAudit(not problems, tuple(problems))
