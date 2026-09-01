from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

from .contracts import PayoutTier


class PayoutContractError(ValueError):
    pass


def parse_payout_csv(path: str | Path) -> tuple[PayoutTier, ...]:
    payout_path = Path(path)
    with payout_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        expected = {"rank_start", "rank_end", "prize_type", "value"}
        if not reader.fieldnames or set(reader.fieldnames) != expected:
            raise PayoutContractError(
                "payout CSV header must be rank_start,rank_end,prize_type,value"
            )
        tiers: list[PayoutTier] = []
        for row_number, row in enumerate(reader, start=2):
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
    return validate_payout_tiers(tiers)


def validate_payout_tiers(
    tiers: Iterable[PayoutTier],
    *,
    advertised_value: float | None = None,
    ticket_face_value: float | None = None,
) -> tuple[PayoutTier, ...]:
    ordered = tuple(sorted(tiers, key=lambda tier: tier.rank_start))
    if not ordered:
        raise PayoutContractError("payout table is empty")
    expected_rank = 1
    previous_value = float("inf")
    total = 0.0
    for tier in ordered:
        if tier.rank_start != expected_rank:
            raise PayoutContractError(
                f"payout ranks are not contiguous at rank {expected_rank}"
            )
        if tier.value > previous_value + 1e-9:
            raise PayoutContractError("payout values must be non-increasing")
        if tier.prize_type == "TICKET" and ticket_face_value is None:
            raise PayoutContractError("ticket face value is required for ticket prizes")
        unit_value = ticket_face_value if tier.prize_type == "TICKET" else tier.value
        assert unit_value is not None
        total += (tier.rank_end - tier.rank_start + 1) * unit_value
        previous_value = tier.value
        expected_rank = tier.rank_end + 1
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
                return ticket_face_value
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
