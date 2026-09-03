from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Iterable

from .contracts import PayoutTier


class PayoutContractError(ValueError):
    pass


def parse_payout_csv(
    path: str | Path, *, ticket_face_value: float | None = None
) -> tuple[PayoutTier, ...]:
    payout_path = Path(path)
    with payout_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        exact = ("rank_start", "rank_end", "prize_type", "value")
        if tuple(reader.fieldnames or ()) != exact:
            raise PayoutContractError(
                "payout CSV header must be rank_start,rank_end,prize_type,value"
            )
        tiers: list[PayoutTier] = []
        for row_number, row in enumerate(reader, start=2):
            if None in row or any(value is None for value in row.values()):
                raise PayoutContractError(
                    f"payout row {row_number} has missing or extra cells"
                )
            if not any(value.strip() for value in row.values()):
                continue
            try:
                tiers.append(
                    PayoutTier(
                        rank_start=int(row["rank_start"]),
                        rank_end=int(row["rank_end"]),
                        prize_type=row["prize_type"].strip().upper(),
                        value=float(row["value"]),
                    )
                )
            except (TypeError, ValueError) as exc:
                raise PayoutContractError(f"invalid payout row {row_number}") from exc
    return validate_payout_tiers(tiers, ticket_face_value=ticket_face_value)


def validate_payout_tiers(
    tiers: Iterable[PayoutTier],
    *,
    advertised_value: float | None = None,
    ticket_face_value: float | None = None,
    field_size: int | None = None,
    reserved_entry_count: int | None = None,
) -> tuple[PayoutTier, ...]:
    if advertised_value is not None and (
        not math.isfinite(advertised_value) or advertised_value < 0
    ):
        raise PayoutContractError("advertised value must be finite and non-negative")
    if ticket_face_value is not None and (
        not math.isfinite(ticket_face_value) or ticket_face_value < 0
    ):
        raise PayoutContractError("ticket face value must be finite and non-negative")
    if field_size is not None:
        if isinstance(field_size, bool) or not isinstance(field_size, int) or field_size < 2:
            raise PayoutContractError("field size must be an integer of at least two")
        if reserved_entry_count is not None and not 1 <= reserved_entry_count <= field_size:
            raise PayoutContractError(
                "reserved entry count must be positive and no larger than field size"
            )
    ordered = tuple(sorted(tiers, key=lambda tier: tier.rank_start))
    if not ordered:
        raise PayoutContractError("payout table is empty")
    expected_rank = 1
    previous_effective_value = float("inf")
    total = 0.0
    for tier in ordered:
        if not math.isfinite(tier.value):
            raise PayoutContractError("payout values must be finite")
        if tier.rank_start != expected_rank:
            raise PayoutContractError(
                f"payout ranks are not contiguous at rank {expected_rank}"
            )
        if tier.prize_type == "TICKET" and ticket_face_value is None:
            raise PayoutContractError("ticket face value is required for ticket prizes")
        unit_value = (
            tier.value * ticket_face_value
            if tier.prize_type == "TICKET" and ticket_face_value is not None
            else tier.value
        )
        if unit_value > previous_effective_value + 1e-9:
            raise PayoutContractError("effective payout values must be non-increasing")
        total += (tier.rank_end - tier.rank_start + 1) * unit_value
        previous_effective_value = unit_value
        expected_rank = tier.rank_end + 1
    if field_size is not None and ordered[-1].rank_end > field_size:
        raise PayoutContractError(
            f"payout rank {ordered[-1].rank_end} exceeds field size {field_size}"
        )
    if advertised_value is not None and abs(total - advertised_value) > 0.01:
        raise PayoutContractError(
            f"payout value {total:.2f} does not reconcile advertised value {advertised_value:.2f}"
        )
    return ordered


def payout_for_rank(
    rank: int, tiers: Iterable[PayoutTier], ticket_face_value: float | None = None
) -> float:
    for tier in tiers:
        if tier.rank_start <= rank <= tier.rank_end:
            if tier.prize_type == "TICKET":
                if ticket_face_value is None:
                    raise PayoutContractError("ticket face value is required")
                return tier.value * ticket_face_value
            return tier.value
    return 0.0


def divided_payout(
    occupied_rank_start: int,
    tied_count: int,
    tiers: Iterable[PayoutTier],
    ticket_face_value: float | None = None,
) -> float:
    if occupied_rank_start < 1 or tied_count < 1:
        raise PayoutContractError("invalid tie group")
    gross = sum(
        payout_for_rank(rank, tiers, ticket_face_value)
        for rank in range(occupied_rank_start, occupied_rank_start + tied_count)
    )
    return gross / tied_count
