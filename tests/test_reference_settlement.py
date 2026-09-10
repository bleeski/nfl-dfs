from __future__ import annotations

from decimal import Decimal

import numpy as np
import pytest

from nfl_dfs.contracts import PayoutTier
from nfl_dfs.economics import evaluate_candidates_against_field
from nfl_dfs.field import FieldLineup
from nfl_dfs.lineups import validate_lineup
from nfl_dfs.optimizer import LineupOptimizer
from nfl_dfs.reference_settlement import (
    ReferenceBudget,
    ReferenceFieldEntry,
    ReferenceSettlementError,
    ReferenceSettlementRefused,
    canonical_score,
    evaluate_reference_settlement,
)
from nfl_dfs.simulation import SimulationResult


def _entry(
    entry_id: str,
    score: str,
    lineup: str | None = None,
    *,
    owned: bool = False,
) -> ReferenceFieldEntry:
    return ReferenceFieldEntry(entry_id, score, lineup or f"L-{entry_id}", owned)


def _gross_cents(result, entry_id: str):
    row = next(item for item in result.rows if item.entry_id == entry_id)
    return row.gross_prize.cents


def test_exchangeable_field_and_exact_ties_cross_payout_boundary() -> None:
    tiers = (
        PayoutTier(rank_start=1, rank_end=1, prize_type="CASH", value=100),
        PayoutTier(rank_start=2, rank_end=2, prize_type="CASH", value=50),
        PayoutTier(rank_start=3, rank_end=3, prize_type="CASH", value=0),
    )
    entries = (_entry("a", "10"), _entry("b", "10"), _entry("c", "5"))
    first = evaluate_reference_settlement(
        entries, tiers, field_size=3, advertised_prize_value="150.00"
    )
    reversed_result = evaluate_reference_settlement(
        reversed(entries), tiers, field_size=3, advertised_prize_value="150.00"
    )
    assert first.deterministic_dict() == reversed_result.deterministic_dict()
    tied = [row for row in first.rows if row.entry_id in {"a", "b"}]
    assert {(row.rank, row.tie_count) for row in tied} == {(1, 2)}
    assert {_gross_cents(first, entry_id) for entry_id in ("a", "b")} == {7500}
    assert _gross_cents(first, "c") == 0


@pytest.mark.parametrize(
    ("tiers", "ticket_face", "advertised", "expected"),
    [
        (
            (PayoutTier(rank_start=1, rank_end=3, prize_type="CASH", value=10),),
            None,
            "30.00",
            [1000, 1000, 1000],
        ),
        (
            (
                PayoutTier(rank_start=1, rank_end=1, prize_type="CASH", value=100),
                PayoutTier(rank_start=2, rank_end=3, prize_type="CASH", value=0),
            ),
            None,
            "100.00",
            [10000, 0, 0],
        ),
        (
            (
                PayoutTier(rank_start=1, rank_end=1, prize_type="TICKET", value=2),
                PayoutTier(rank_start=2, rank_end=2, prize_type="TICKET", value=1),
                PayoutTier(rank_start=3, rank_end=3, prize_type="CASH", value=0),
            ),
            "25.00",
            "75.00",
            [5000, 2500, 0],
        ),
    ],
)
def test_flat_top_heavy_satellite_and_last_paid_rank_boundaries(
    tiers, ticket_face, advertised, expected
) -> None:
    result = evaluate_reference_settlement(
        (_entry("1", "30"), _entry("2", "20"), _entry("3", "10")),
        tiers,
        field_size=3,
        ticket_face_value=ticket_face,
        advertised_prize_value=advertised,
    )
    assert [_gross_cents(result, str(index)) for index in (1, 2, 3)] == expected


def test_zero_payout_contract_is_explicit_and_complete() -> None:
    result = evaluate_reference_settlement(
        (_entry("1", "2"), _entry("2", "1")),
        (),
        field_size=2,
        advertised_prize_value="0.00",
    )
    assert result.paid_rank_count == 0
    assert all(row.gross_prize.cents == 0 for row in result.rows)


def test_known_duplicates_and_multiple_owned_entries_settle_together() -> None:
    result = evaluate_reference_settlement(
        (
            _entry("owned-a", "10", "SAME", owned=True),
            _entry("owned-b", "10", "SAME", owned=True),
            _entry("field", "5", "OTHER"),
        ),
        (
            PayoutTier(rank_start=1, rank_end=1, prize_type="CASH", value=90),
            PayoutTier(rank_start=2, rank_end=2, prize_type="CASH", value=30),
            PayoutTier(rank_start=3, rank_end=3, prize_type="CASH", value=0),
        ),
        field_size=3,
        advertised_prize_value="120.00",
    )
    owned = [row for row in result.rows if row.operator_owned]
    assert len(owned) == 2
    assert {(row.rank, row.tie_count) for row in owned} == {(1, 2)}
    assert {row.lineup_duplication_total for row in owned} == {2}
    assert {row.lineup_duplicate_opponents for row in owned} == {1}
    assert {row.gross_prize.cents for row in owned} == {6000}


def test_canonical_score_rounding_boundaries_are_declared() -> None:
    assert canonical_score("10.0000004") == Decimal("10.000000")
    assert canonical_score("10.0000005") == Decimal("10.000000")
    assert canonical_score("10.0000006") == Decimal("10.000001")
    result = evaluate_reference_settlement(
        (
            _entry("a", "10.0000004"),
            _entry("b", "10.0000005"),
            _entry("c", "10.0000006"),
        ),
        (PayoutTier(rank_start=1, rank_end=3, prize_type="CASH", value=1),),
        field_size=3,
        advertised_prize_value="3.00",
    )
    assert next(row for row in result.rows if row.entry_id == "c").rank == 1
    assert {
        (row.rank, row.tie_count)
        for row in result.rows
        if row.entry_id in {"a", "b"}
    } == {(2, 2)}


def test_fractional_cent_tie_uses_exact_rational_money() -> None:
    result = evaluate_reference_settlement(
        (_entry("a", "1"), _entry("b", "1"), _entry("c", "1")),
        (PayoutTier(rank_start=1, rank_end=1, prize_type="CASH", value=1),),
        field_size=3,
        advertised_prize_value="1.00",
    )
    assert {
        (row.gross_prize.cents_numerator, row.gross_prize.cents_denominator)
        for row in result.rows
    } == {(100, 3)}


def test_reference_rejects_incomplete_malformed_nonfinite_and_budgeted_fields() -> None:
    with pytest.raises(ReferenceSettlementError, match="complete field"):
        evaluate_reference_settlement((_entry("a", "1"),), (), field_size=2)
    with pytest.raises(ReferenceSettlementError, match="finite"):
        evaluate_reference_settlement((_entry("a", "NaN"),), (), field_size=1)
    with pytest.raises(ReferenceSettlementError, match="contiguous"):
        evaluate_reference_settlement(
            (_entry("a", "1"), _entry("b", "0")),
            (PayoutTier(rank_start=2, rank_end=2, prize_type="CASH", value=1),),
            field_size=2,
        )
    with pytest.raises(ReferenceSettlementError, match="whole ticket"):
        evaluate_reference_settlement(
            (_entry("a", "1"),),
            (PayoutTier(rank_start=1, rank_end=1, prize_type="TICKET", value=1.5),),
            field_size=1,
            ticket_face_value=10,
        )
    with pytest.raises(ReferenceSettlementRefused, match="SIZE_BUDGET"):
        evaluate_reference_settlement(
            (_entry("a", "1"), _entry("b", "0")),
            (),
            field_size=2,
            budget=ReferenceBudget(max_entries=1),
        )
    with pytest.raises(ReferenceSettlementRefused, match="WORK_BUDGET"):
        evaluate_reference_settlement(
            (_entry("a", "1"), _entry("b", "0")),
            (),
            field_size=2,
            budget=ReferenceBudget(max_work_units=2),
        )
    with pytest.raises(ReferenceSettlementRefused, match="RUNTIME_BUDGET"):
        evaluate_reference_settlement(
            (_entry("a", "1"), _entry("b", "0")),
            (),
            field_size=2,
            budget=ReferenceBudget(max_runtime_seconds=1e-12),
        )


def test_reference_matches_production_on_bounded_duplicate_golden_case(
    classic_slate,
) -> None:
    solved = LineupOptimizer(classic_slate).solve(
        {player.dk_id: 50_000 / max(player.salary, 1) for player in classic_slate.players}
    )
    assert solved.roster is not None
    validation = validate_lineup(classic_slate, solved.roster)
    assert validation.lineup is not None
    people = tuple(dict.fromkeys(player.underlying_id for player in classic_slate.players))
    simulations = SimulationResult(
        purpose="SELECT",
        seed=7,
        person_ids=people,
        outcomes=np.arange(len(people), dtype=np.float32).reshape(1, -1),
        weights=np.ones(1),
        diagnostics={},
    )
    tiers = (
        PayoutTier(rank_start=1, rank_end=1, prize_type="CASH", value=100),
        PayoutTier(rank_start=2, rank_end=2, prize_type="CASH", value=50),
        PayoutTier(rank_start=3, rank_end=3, prize_type="CASH", value=10),
    )
    production = evaluate_candidates_against_field(
        slate=classic_slate,
        simulations=simulations,
        candidates=[solved.roster],
        field=[FieldLineup(solved.roster, validation.lineup.canonical_key, 2)],
        payout_tiers=tiers,
    )
    score = str(production.rounded_scores[0, 0])
    reference = evaluate_reference_settlement(
        (
            _entry("owned", score, validation.lineup.canonical_key, owned=True),
            _entry("field-a", score, validation.lineup.canonical_key),
            _entry("field-b", score, validation.lineup.canonical_key),
        ),
        tiers,
        field_size=3,
        advertised_prize_value="160.00",
    )
    owned = next(row for row in reference.rows if row.entry_id == "owned")
    assert owned.rank == int(production.ranks[0, 0])
    assert owned.tie_count == int(production.tie_counts[0, 0])
    assert owned.lineup_duplicate_opponents == int(production.duplicate_counts[0])
    assert float(owned.gross_prize.cents / 100) == pytest.approx(
        production.gross_payout[0, 0]
    )
