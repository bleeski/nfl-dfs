from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from .hashing import sha256_file


@dataclass(frozen=True)
class StandingRow:
    entry_id: str
    rank: int
    points: float
    prize: float
    lineup_raw: str


@dataclass(frozen=True)
class StandingsSnapshot:
    path: str
    sha256: str
    rows: tuple[StandingRow, ...]


class SettlementError(ValueError):
    pass


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
            entry_id = row["EntryId"].strip()
            if not entry_id:
                continue
            if entry_id in seen:
                raise SettlementError(f"duplicate EntryId at row {row_number}")
            try:
                rank = int(row["Rank"].replace(",", ""))
                points = float(row["Points"])
                prize = float(row["Prize"].replace("$", "").replace(",", "") or 0)
            except ValueError as exc:
                raise SettlementError(f"invalid numeric value at row {row_number}") from exc
            rows.append(StandingRow(entry_id, rank, points, prize, row["Lineup"]))
            seen.add(entry_id)
    if not rows:
        raise SettlementError("standings contain no entry rows")
    return StandingsSnapshot(str(standings_path), sha256_file(standings_path), tuple(rows))


def require_entry_coverage(snapshot: StandingsSnapshot, entry_ids: set[str]) -> None:
    observed = {row.entry_id for row in snapshot.rows}
    missing = entry_ids.difference(observed)
    if missing:
        raise SettlementError(f"standings are incomplete for Entry IDs: {sorted(missing)}")
