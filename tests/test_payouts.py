from __future__ import annotations

import pytest

from nfl_dfs.contracts import PayoutTier
from nfl_dfs.economics import exact_toy_field_settlement
from nfl_dfs.payouts import PayoutContractError, divided_payout, validate_payout_tiers


def test_complete_monotonic_payout_and_exact_tie_split() -> None:
    tiers = validate_payout_tiers(
        (
            PayoutTier(rank_start=1, rank_end=1, prize_type="CASH", value=100),
            PayoutTier(rank_start=2, rank_end=3, prize_type="CASH", value=40),
        ),
        advertised_value=180,
    )
    assert divided_payout(1, 2, tiers) == 70
    assert exact_toy_field_settlement([10, 10, 5], tiers) == [70, 70, 40]


def test_payout_gap_rejected() -> None:
    with pytest.raises(PayoutContractError, match="contiguous"):
        validate_payout_tiers(
            (
                PayoutTier(rank_start=1, rank_end=1, prize_type="CASH", value=10),
                PayoutTier(rank_start=3, rank_end=3, prize_type="CASH", value=5),
            )
        )


def test_ticket_requires_face_value() -> None:
    with pytest.raises(PayoutContractError, match="ticket face"):
        validate_payout_tiers(
            (PayoutTier(rank_start=1, rank_end=1, prize_type="TICKET", value=1),)
        )
