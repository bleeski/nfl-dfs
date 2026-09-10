from __future__ import annotations

import numpy as np
import pytest

from nfl_dfs.contracts import ContestObjective, PayoutTier
from nfl_dfs.economics import evaluate_candidates_against_field, exact_toy_field_settlement
from nfl_dfs.field import FieldLineup
from nfl_dfs.lineups import validate_lineup
from nfl_dfs.optimizer import LineupOptimizer
from nfl_dfs.payouts import (
    PayoutContractError,
    divided_payout,
    parse_payout_csv,
    validate_payout_tiers,
)
from nfl_dfs.portfolio import evaluate_portfolio, portfolio_net_samples, select_portfolio
from nfl_dfs.simulation import SimulationResult


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


def test_candidate_identical_to_field_uses_exact_structural_tie(classic_slate) -> None:
    solved = LineupOptimizer(classic_slate).solve(
        {player.dk_id: 50_000 / max(player.salary, 1) for player in classic_slate.players}
    )
    assert solved.roster is not None
    validation = validate_lineup(classic_slate, solved.roster)
    assert validation.lineup is not None
    people = tuple(dict.fromkeys(player.underlying_id for player in classic_slate.players))
    outcomes = np.arange(2 * len(people), dtype=np.float32).reshape(2, len(people)) / 10
    simulations = SimulationResult(
        purpose="SELECT",
        seed=1,
        person_ids=people,
        outcomes=outcomes,
        weights=np.full(2, 0.5),
        diagnostics={},
    )
    tiers = (
        PayoutTier(rank_start=1, rank_end=1, prize_type="CASH", value=100),
        PayoutTier(rank_start=2, rank_end=2, prize_type="CASH", value=50),
        PayoutTier(rank_start=3, rank_end=3, prize_type="CASH", value=10),
    )
    economics = evaluate_candidates_against_field(
        slate=classic_slate,
        simulations=simulations,
        candidates=[solved.roster],
        field=[FieldLineup(solved.roster, validation.lineup.canonical_key, 2)],
        payout_tiers=tiers,
    )
    assert np.array_equal(economics.ranks, np.ones((2, 1), dtype=np.int32))
    assert np.array_equal(economics.tie_counts, np.full((2, 1), 3, dtype=np.int32))
    assert economics.gross_payout.dtype == np.float64
    assert np.allclose(economics.gross_payout, (100 + 50 + 10) / 3)

    nonuniform = SimulationResult(
        purpose="SELECT",
        seed=1,
        person_ids=people,
        outcomes=outcomes,
        weights=np.array([0.75, 0.25]),
        diagnostics={},
    )
    with pytest.raises(ValueError, match="uniformly weighted"):
        evaluate_candidates_against_field(
            slate=classic_slate,
            simulations=nonuniform,
            candidates=[solved.roster],
            field=[],
            payout_tiers=tiers,
        )


def test_reserved_entries_compete_with_each_other_in_portfolio_settlement(
    classic_slate,
) -> None:
    optimizer = LineupOptimizer(classic_slate)
    scores = {player.dk_id: 50_000 / max(player.salary, 1) for player in classic_slate.players}
    first = optimizer.solve(scores)
    assert first.roster is not None
    optimizer.add_no_good(first.roster)
    second = optimizer.solve(scores)
    assert second.roster is not None
    people = tuple(dict.fromkeys(player.underlying_id for player in classic_slate.players))
    outcomes = np.arange(2 * len(people), dtype=np.float32).reshape(2, len(people)) / 10
    simulations = SimulationResult(
        purpose="SELECT",
        seed=1,
        person_ids=people,
        outcomes=outcomes,
        weights=np.full(2, 0.5),
        diagnostics={},
    )
    tiers = (
        PayoutTier(rank_start=1, rank_end=1, prize_type="CASH", value=100),
        PayoutTier(rank_start=2, rank_end=2, prize_type="CASH", value=50),
    )
    economics = evaluate_candidates_against_field(
        slate=classic_slate,
        simulations=simulations,
        candidates=[first.roster, second.roster],
        field=[],
        payout_tiers=tiers,
    )
    assert np.allclose(economics.gross_payout, 100)
    assert np.allclose(
        portfolio_net_samples(economics, (0, 1), entry_fee=0),
        150,
    )
    selected = select_portfolio(
        {"BASE": economics},
        entry_count=2,
        entry_fee=0,
        field_size=2,
        objective=ContestObjective.SMALL_GPP,
        shortlist_limit=2,
    )
    scalar = evaluate_portfolio(
        {"BASE": economics},
        (0, 1),
        entry_fee=0,
        field_size=2,
        objective=ContestObjective.SMALL_GPP,
    )
    assert selected.expected_net_payout == pytest.approx(150)
    assert selected.expected_net_payout == pytest.approx(scalar.expected_net_payout)


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


def test_ticket_value_is_ticket_count() -> None:
    tiers = validate_payout_tiers(
        (
            PayoutTier(rank_start=1, rank_end=1, prize_type="TICKET", value=2),
            PayoutTier(rank_start=2, rank_end=2, prize_type="TICKET", value=1),
        ),
        ticket_face_value=25,
        advertised_value=75,
    )
    assert divided_payout(1, 1, tiers, ticket_face_value=25) == 50


def test_parse_payout_csv_accepts_ticket_face_value_and_fails_without_it(
    tmp_path,
) -> None:
    payout = tmp_path / "satellite.csv"
    payout.write_text(
        "rank_start,rank_end,prize_type,value\n"
        "1,1,TICKET,2\n"
        "2,3,CASH,10\n",
        encoding="utf-8",
    )
    tiers = parse_payout_csv(payout, ticket_face_value=25)
    assert len(tiers) == 2
    assert divided_payout(1, 1, tiers, ticket_face_value=25) == 50
    with pytest.raises(PayoutContractError, match="ticket face"):
        parse_payout_csv(payout)


def test_contest_economics_reject_nonfinite_values_and_impossible_ranks() -> None:
    tiers = (PayoutTier(rank_start=1, rank_end=3, prize_type="CASH", value=10),)
    with pytest.raises(PayoutContractError, match="finite"):
        validate_payout_tiers(tiers, advertised_value=float("nan"))
    with pytest.raises(PayoutContractError, match="exceeds field size"):
        validate_payout_tiers(tiers, field_size=2, reserved_entry_count=1)
    with pytest.raises(PayoutContractError, match="reserved entry count"):
        validate_payout_tiers(tiers, field_size=3, reserved_entry_count=4)


def test_payout_contract_uses_exact_cents_whole_tickets_and_explicit_zero() -> None:
    with pytest.raises(PayoutContractError, match="exact cents"):
        validate_payout_tiers(
            (PayoutTier(rank_start=1, rank_end=1, prize_type="CASH", value=1.005),)
        )
    with pytest.raises(PayoutContractError, match="whole ticket"):
        validate_payout_tiers(
            (PayoutTier(rank_start=1, rank_end=1, prize_type="TICKET", value=1.5),),
            ticket_face_value=10,
        )
    assert validate_payout_tiers(
        (), advertised_value=0, field_size=2, reserved_entry_count=1, allow_zero_payout=True
    ) == ()
    with pytest.raises(PayoutContractError, match="empty"):
        validate_payout_tiers((), advertised_value=0)
