from __future__ import annotations

import math
import time
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
from fractions import Fraction
from typing import Iterable

from .contracts import PayoutTier
from .hashing import content_hash


REFERENCE_SETTLEMENT_VERSION = "nfl_reference_settlement_v1"
SCORE_QUANTUM = Decimal("0.000001")


class ReferenceSettlementError(ValueError):
    pass


class ReferenceSettlementRefused(ReferenceSettlementError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class ReferenceBudget:
    max_entries: int = 200_000
    max_work_units: int = 1_000_000
    max_runtime_seconds: float = 10.0

    def __post_init__(self) -> None:
        if isinstance(self.max_entries, bool) or self.max_entries < 1:
            raise ReferenceSettlementError("reference max_entries must be positive")
        if isinstance(self.max_work_units, bool) or self.max_work_units < 1:
            raise ReferenceSettlementError("reference max_work_units must be positive")
        if not math.isfinite(self.max_runtime_seconds) or self.max_runtime_seconds <= 0:
            raise ReferenceSettlementError(
                "reference max_runtime_seconds must be positive and finite"
            )

    def to_dict(self) -> dict[str, int | float]:
        return {
            "max_entries": self.max_entries,
            "max_work_units": self.max_work_units,
            "max_runtime_seconds": self.max_runtime_seconds,
        }


@dataclass(frozen=True)
class ReferenceFieldEntry:
    entry_id: str
    score: Decimal | str | int | float
    lineup_key: str
    operator_owned: bool = False


@dataclass(frozen=True)
class ExactShare:
    cents_numerator: int
    cents_denominator: int

    @classmethod
    def from_fraction(cls, value: Fraction) -> "ExactShare":
        return cls(value.numerator, value.denominator)

    @property
    def cents(self) -> Fraction:
        return Fraction(self.cents_numerator, self.cents_denominator)

    def to_dict(self) -> dict[str, int | str]:
        dollars = Decimal(self.cents_numerator) / Decimal(self.cents_denominator * 100)
        return {
            "cents_numerator": self.cents_numerator,
            "cents_denominator": self.cents_denominator,
            "dollars_decimal": format(dollars, "f"),
        }


@dataclass(frozen=True)
class ReferenceSettlementRow:
    entry_id: str
    operator_owned: bool
    canonical_score: str
    rank: int
    tie_count: int
    lineup_key: str
    lineup_duplication_total: int
    lineup_duplicate_opponents: int
    cash_prize: ExactShare
    ticket_count_numerator: int
    ticket_count_denominator: int
    ticket_face_value_cents: int | None
    ticket_value: ExactShare
    gross_prize: ExactShare

    def to_dict(self) -> dict[str, object]:
        return {
            "entry_id": self.entry_id,
            "operator_owned": self.operator_owned,
            "canonical_score": self.canonical_score,
            "rank": self.rank,
            "tie_count": self.tie_count,
            "lineup_key": self.lineup_key,
            "lineup_duplication_total": self.lineup_duplication_total,
            "lineup_duplicate_opponents": self.lineup_duplicate_opponents,
            "cash_prize": self.cash_prize.to_dict(),
            "ticket_count": {
                "numerator": self.ticket_count_numerator,
                "denominator": self.ticket_count_denominator,
            },
            "ticket_face_value_cents": self.ticket_face_value_cents,
            "ticket_value": self.ticket_value.to_dict(),
            "gross_prize": self.gross_prize.to_dict(),
        }


@dataclass(frozen=True)
class ReferenceSettlementResult:
    status: str
    evaluator_version: str
    score_rounding: str
    money_representation: str
    field_size: int
    paid_rank_count: int
    rows: tuple[ReferenceSettlementRow, ...]
    budget: ReferenceBudget
    work_units: int

    def deterministic_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "evaluator_version": self.evaluator_version,
            "score_rounding": self.score_rounding,
            "money_representation": self.money_representation,
            "field_size": self.field_size,
            "paid_rank_count": self.paid_rank_count,
            "rows": [row.to_dict() for row in self.rows],
            "budget": self.budget.to_dict(),
            "work_units": self.work_units,
        }

    @property
    def result_hash(self) -> str:
        return content_hash(self.deterministic_dict())


def canonical_score(value: Decimal | str | int | float) -> Decimal:
    if isinstance(value, bool):
        raise ReferenceSettlementError("scores must be finite numeric values")
    try:
        decimal_value = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ReferenceSettlementError("scores must be finite numeric values") from exc
    if not decimal_value.is_finite():
        raise ReferenceSettlementError("scores must be finite numeric values")
    return decimal_value.quantize(SCORE_QUANTUM, rounding=ROUND_HALF_EVEN)


def decimal_to_exact_cents(value: Decimal | str | int | float, label: str) -> int:
    if isinstance(value, bool):
        raise ReferenceSettlementError(f"{label} must be exact non-negative cents")
    try:
        decimal_value = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ReferenceSettlementError(
            f"{label} must be exact non-negative cents"
        ) from exc
    if not decimal_value.is_finite() or decimal_value < 0:
        raise ReferenceSettlementError(f"{label} must be exact non-negative cents")
    cents = decimal_value * 100
    if cents != cents.to_integral_value():
        raise ReferenceSettlementError(f"{label} must be exact non-negative cents")
    return int(cents)


def _effective_rank_values(
    tiers: Iterable[PayoutTier],
    *,
    field_size: int,
    ticket_face_value: Decimal | str | int | float | None,
    advertised_prize_value: Decimal | str | int | float | None,
) -> tuple[tuple[int, ...], tuple[int, ...], int | None]:
    ordered = tuple(sorted(tiers, key=lambda tier: tier.rank_start))
    ticket_face_cents = (
        decimal_to_exact_cents(ticket_face_value, "ticket face value")
        if ticket_face_value is not None
        else None
    )
    cash_by_rank = [0] * (field_size + 1)
    tickets_by_rank = [0] * (field_size + 1)
    expected_rank = 1
    previous_effective_cents: int | None = None
    for tier in ordered:
        if tier.rank_start != expected_rank:
            raise ReferenceSettlementError(
                f"payout ranks are not contiguous at rank {expected_rank}"
            )
        if tier.rank_end > field_size:
            raise ReferenceSettlementError(
                f"payout rank {tier.rank_end} exceeds field size {field_size}"
            )
        if tier.prize_type == "CASH":
            cash_cents = decimal_to_exact_cents(tier.value, "cash payout value")
            ticket_count = 0
            effective_cents = cash_cents
        elif tier.prize_type == "TICKET":
            ticket_decimal = Decimal(str(tier.value))
            if (
                not ticket_decimal.is_finite()
                or ticket_decimal < 0
                or ticket_decimal != ticket_decimal.to_integral_value()
            ):
                raise ReferenceSettlementError(
                    "ticket payout value must be a non-negative whole ticket count"
                )
            if ticket_face_cents is None:
                raise ReferenceSettlementError(
                    "ticket face value is required for ticket prizes"
                )
            cash_cents = 0
            ticket_count = int(ticket_decimal)
            effective_cents = ticket_count * ticket_face_cents
        else:  # pragma: no cover - Pydantic prevents this for normal callers.
            raise ReferenceSettlementError(f"unsupported prize type: {tier.prize_type}")
        if (
            previous_effective_cents is not None
            and effective_cents > previous_effective_cents
        ):
            raise ReferenceSettlementError(
                "effective payout values must be non-increasing"
            )
        for rank in range(tier.rank_start, tier.rank_end + 1):
            cash_by_rank[rank] = cash_cents
            tickets_by_rank[rank] = ticket_count
        previous_effective_cents = effective_cents
        expected_rank = tier.rank_end + 1

    total_value_cents = sum(cash_by_rank)
    if ticket_face_cents is not None:
        total_value_cents += sum(tickets_by_rank) * ticket_face_cents
    if advertised_prize_value is not None:
        advertised_cents = decimal_to_exact_cents(
            advertised_prize_value, "advertised prize value"
        )
        if total_value_cents != advertised_cents:
            raise ReferenceSettlementError(
                "payout value does not exactly reconcile advertised prize value"
            )
    return tuple(cash_by_rank), tuple(tickets_by_rank), ticket_face_cents


def evaluate_reference_settlement(
    entries: Iterable[ReferenceFieldEntry],
    payout_tiers: Iterable[PayoutTier],
    *,
    field_size: int,
    ticket_face_value: Decimal | str | int | float | None = None,
    advertised_prize_value: Decimal | str | int | float | None = None,
    budget: ReferenceBudget | None = None,
) -> ReferenceSettlementResult:
    """Settle one complete contest without using production economics code.

    This intentionally uses Decimal score quantization, explicit Python
    counters, integer rank tables, and Fraction money shares. It neither calls
    nor imports the vectorized production evaluator or its payout helpers.
    """

    started = time.perf_counter()
    active_budget = budget or ReferenceBudget()
    field_entries = tuple(entries)
    tiers = tuple(payout_tiers)
    if isinstance(field_size, bool) or not isinstance(field_size, int) or field_size < 1:
        raise ReferenceSettlementError("field size must be a positive integer")
    if len(field_entries) != field_size:
        raise ReferenceSettlementError(
            f"complete field required: expected {field_size}, observed {len(field_entries)}"
        )
    if field_size > active_budget.max_entries:
        raise ReferenceSettlementRefused(
            "REFERENCE_SIZE_BUDGET_EXCEEDED",
            f"field size {field_size} exceeds max_entries {active_budget.max_entries}",
        )

    ids = [entry.entry_id.strip() for entry in field_entries]
    if any(not entry_id for entry_id in ids) or len(set(ids)) != len(ids):
        raise ReferenceSettlementError("field Entry IDs must be nonempty and unique")
    lineup_keys = [entry.lineup_key.strip() for entry in field_entries]
    if any(not key for key in lineup_keys):
        raise ReferenceSettlementError("every field entry requires a complete lineup key")
    scores = [canonical_score(entry.score) for entry in field_entries]
    score_counts = Counter(scores)
    lineup_counts = Counter(lineup_keys)
    paid_rank_count = max((tier.rank_end for tier in tiers), default=0)
    work_units = field_size + len(score_counts) + paid_rank_count
    if work_units > active_budget.max_work_units:
        raise ReferenceSettlementRefused(
            "REFERENCE_WORK_BUDGET_EXCEEDED",
            f"estimated work {work_units} exceeds max_work_units {active_budget.max_work_units}",
        )

    cash_by_rank, tickets_by_rank, ticket_face_cents = _effective_rank_values(
        tiers,
        field_size=field_size,
        ticket_face_value=ticket_face_value,
        advertised_prize_value=advertised_prize_value,
    )
    rank_by_score: dict[Decimal, int] = {}
    occupied = 0
    for score in sorted(score_counts, reverse=True):
        rank_by_score[score] = occupied + 1
        occupied += score_counts[score]
        if time.perf_counter() - started > active_budget.max_runtime_seconds:
            raise ReferenceSettlementRefused(
                "REFERENCE_RUNTIME_BUDGET_EXCEEDED",
                "runtime budget expired while constructing exact tie groups",
            )

    rows: list[ReferenceSettlementRow] = []
    for entry, entry_id, score, lineup_key in zip(
        field_entries, ids, scores, lineup_keys, strict=True
    ):
        rank = rank_by_score[score]
        tie_count = score_counts[score]
        occupied_ranks = range(rank, rank + tie_count)
        cash_total = sum(cash_by_rank[position] for position in occupied_ranks)
        ticket_total = sum(tickets_by_rank[position] for position in occupied_ranks)
        cash_share = Fraction(cash_total, tie_count)
        ticket_share = Fraction(ticket_total, tie_count)
        ticket_value_share = (
            ticket_share * ticket_face_cents
            if ticket_face_cents is not None
            else Fraction(0, 1)
        )
        gross_share = cash_share + ticket_value_share
        rows.append(
            ReferenceSettlementRow(
                entry_id=entry_id,
                operator_owned=bool(entry.operator_owned),
                canonical_score=format(score, "f"),
                rank=rank,
                tie_count=tie_count,
                lineup_key=lineup_key,
                lineup_duplication_total=lineup_counts[lineup_key],
                lineup_duplicate_opponents=lineup_counts[lineup_key] - 1,
                cash_prize=ExactShare.from_fraction(cash_share),
                ticket_count_numerator=ticket_share.numerator,
                ticket_count_denominator=ticket_share.denominator,
                ticket_face_value_cents=ticket_face_cents,
                ticket_value=ExactShare.from_fraction(ticket_value_share),
                gross_prize=ExactShare.from_fraction(gross_share),
            )
        )
        if time.perf_counter() - started > active_budget.max_runtime_seconds:
            raise ReferenceSettlementRefused(
                "REFERENCE_RUNTIME_BUDGET_EXCEEDED",
                "runtime budget expired while settling exact entry results",
            )
    rows.sort(key=lambda row: row.entry_id)
    return ReferenceSettlementResult(
        status="COMPLETE",
        evaluator_version=REFERENCE_SETTLEMENT_VERSION,
        score_rounding="Decimal ROUND_HALF_EVEN to 0.000001 points",
        money_representation="exact rational cents",
        field_size=field_size,
        paid_rank_count=paid_rank_count,
        rows=tuple(rows),
        budget=active_budget,
        work_units=work_units,
    )
