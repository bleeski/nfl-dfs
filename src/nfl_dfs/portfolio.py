from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, replace
from typing import Mapping

import numpy as np

from .contracts import ContestObjective
from .economics import CandidateEconomics


@dataclass(frozen=True)
class PortfolioMetrics:
    candidate_indices: tuple[int, ...]
    robust_net_payout_lcb: float
    elite_probability: float
    top_one_percent_probability: float
    net_loss_probability: float
    severe_loss_probability: float
    zero_return_probability: float
    expected_net_payout: float
    payout_p05: float
    payout_p50: float
    payout_p95: float
    cvar_05: float
    worst_state: str
    selection_candidate_count: int = 0
    evaluated_portfolio_count: int = 0


def _portfolio_settlement(
    economics: CandidateEconomics,
    indices: tuple[int, ...],
    *,
    scenario_chunk_size: int = 1024,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Settle selected entries against the field and against one another."""
    base_ranks = economics.ranks[:, indices]
    base_gross = economics.gross_payout[:, indices].astype(np.float64)
    if (
        len(indices) <= 1
        or economics.rounded_scores is None
        or economics.cumulative_payout is None
    ):
        return base_gross.sum(axis=1), base_ranks, base_gross
    adjusted_ranks = np.empty_like(base_ranks)
    entry_gross = np.empty_like(base_gross)
    cumulative = economics.cumulative_payout
    for start in range(0, len(base_ranks), scenario_chunk_size):
        stop = min(start + scenario_chunk_size, len(base_ranks))
        scores = economics.rounded_scores[start:stop, indices]
        comparison = scores[:, :, None] > scores[:, None, :]
        equal = scores[:, :, None] == scores[:, None, :]
        own_greater = comparison.sum(axis=1, dtype=np.int32)
        own_equal = equal.sum(axis=1, dtype=np.int32) - 1
        ranks = base_ranks[start:stop] + own_greater
        ties = economics.tie_counts[start:stop, indices] + own_equal
        occupied_end = ranks + ties - 1
        if int(occupied_end.max()) >= len(cumulative):
            raise ValueError("payout lookup does not cover the selected portfolio ranks")
        adjusted_ranks[start:stop] = ranks
        entry_gross[start:stop] = (
            cumulative[occupied_end] - cumulative[ranks - 1]
        ) / ties
    return entry_gross.sum(axis=1), adjusted_ranks, entry_gross


def _portfolio_settlement_batched(
    economics: CandidateEconomics,
    indices: np.ndarray,
    *,
    scenario_chunk_size: int = 512,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    base_ranks = economics.ranks[:, indices]
    base_gross = economics.gross_payout[:, indices].astype(np.float64)
    if (
        indices.shape[1] <= 1
        or economics.rounded_scores is None
        or economics.cumulative_payout is None
    ):
        return base_gross.sum(axis=2), base_ranks, base_gross
    adjusted_ranks = np.empty_like(base_ranks)
    entry_gross = np.empty_like(base_gross)
    cumulative = economics.cumulative_payout
    for start in range(0, len(base_ranks), scenario_chunk_size):
        stop = min(start + scenario_chunk_size, len(base_ranks))
        scores = economics.rounded_scores[start:stop, indices]
        comparison = scores[:, :, :, None] > scores[:, :, None, :]
        equal = scores[:, :, :, None] == scores[:, :, None, :]
        own_greater = comparison.sum(axis=2, dtype=np.int32)
        own_equal = equal.sum(axis=2, dtype=np.int32) - 1
        ranks = base_ranks[start:stop] + own_greater
        ties = economics.tie_counts[start:stop, indices] + own_equal
        occupied_end = ranks + ties - 1
        if int(occupied_end.max()) >= len(cumulative):
            raise ValueError("payout lookup does not cover the selected portfolio ranks")
        adjusted_ranks[start:stop] = ranks
        entry_gross[start:stop] = (
            cumulative[occupied_end] - cumulative[ranks - 1]
        ) / ties
    return entry_gross.sum(axis=2), adjusted_ranks, entry_gross


def _state_metrics(
    economics: CandidateEconomics,
    indices: tuple[int, ...],
    *,
    entry_fee: float,
    elite_rank: int,
    top_one_percent_rank: int,
    objective: ContestObjective,
) -> dict[str, float]:
    gross, adjusted_ranks, entry_gross = _portfolio_settlement(economics, indices)
    net = gross - entry_fee * len(indices)
    if objective in {ContestObjective.CASH, ContestObjective.WTA, ContestObjective.SATELLITE}:
        any_elite = (entry_gross > 0).any(axis=1)
    else:
        any_elite = (adjusted_ranks <= elite_rank).any(axis=1)
    any_top_one = (adjusted_ranks <= top_one_percent_rank).any(axis=1)
    mean = float(net.mean())
    standard_error = float(net.std(ddof=1) / math.sqrt(len(net))) if len(net) > 1 else 0.0
    sorted_net = np.sort(net)
    tail_count = max(1, int(math.ceil(0.05 * len(net))))
    total_fees = entry_fee * len(indices)
    return {
        "robust_net_lcb": mean - 1.96 * standard_error,
        "elite_probability": float(any_elite.mean()),
        "top_one_probability": float(any_top_one.mean()),
        "net_loss_probability": float((net < 0).mean()),
        "severe_loss_probability": float((net < -0.8 * total_fees).mean()),
        "zero_return_probability": float((gross == 0).mean()),
        "expected_net": mean,
        "p05": float(np.quantile(net, 0.05)),
        "p50": float(np.quantile(net, 0.50)),
        "p95": float(np.quantile(net, 0.95)),
        "cvar_05": float(sorted_net[:tail_count].mean()),
    }


def portfolio_net_samples(
    economics: CandidateEconomics,
    indices: tuple[int, ...],
    *,
    entry_fee: float,
) -> np.ndarray:
    gross, _, _ = _portfolio_settlement(economics, indices)
    return gross - entry_fee * len(indices)


def evaluate_portfolio(
    state_economics: Mapping[str, CandidateEconomics],
    indices: tuple[int, ...],
    *,
    entry_fee: float,
    field_size: int,
    objective: ContestObjective,
) -> PortfolioMetrics:
    if not state_economics:
        raise ValueError("at least one field state is required")
    if not indices or len(set(indices)) != len(indices):
        raise ValueError("portfolio indices must be non-empty and unique")
    if not np.isfinite(entry_fee) or entry_fee < 0:
        raise ValueError("entry fee must be finite and non-negative")
    if field_size < 2:
        raise ValueError("field size must be at least two")
    for economics in state_economics.values():
        if any(index < 0 or index >= len(economics.rosters) for index in indices):
            raise ValueError("portfolio index is outside the candidate bank")
    if objective is ContestObjective.LARGE_GPP:
        elite_rank = max(1, math.ceil(0.001 * field_size))
    elif objective is ContestObjective.SMALL_GPP:
        elite_rank = max(1, math.ceil(0.01 * field_size))
    else:
        elite_rank = 1
    top_one_rank = max(1, math.ceil(0.01 * field_size))
    results = {
        state: _state_metrics(
            economics,
            indices,
            entry_fee=entry_fee,
            elite_rank=elite_rank,
            top_one_percent_rank=top_one_rank,
            objective=objective,
        )
        for state, economics in state_economics.items()
    }
    worst_state = min(results, key=lambda state: results[state]["robust_net_lcb"])
    worst = results[worst_state]
    return PortfolioMetrics(
        candidate_indices=indices,
        robust_net_payout_lcb=min(value["robust_net_lcb"] for value in results.values()),
        elite_probability=min(value["elite_probability"] for value in results.values()),
        top_one_percent_probability=min(value["top_one_probability"] for value in results.values()),
        net_loss_probability=max(value["net_loss_probability"] for value in results.values()),
        severe_loss_probability=max(value["severe_loss_probability"] for value in results.values()),
        zero_return_probability=max(value["zero_return_probability"] for value in results.values()),
        expected_net_payout=min(value["expected_net"] for value in results.values()),
        payout_p05=min(value["p05"] for value in results.values()),
        payout_p50=min(value["p50"] for value in results.values()),
        payout_p95=min(value["p95"] for value in results.values()),
        cvar_05=min(value["cvar_05"] for value in results.values()),
        worst_state=worst_state,
    )


def _nondominated(metrics: list[PortfolioMetrics]) -> list[PortfolioMetrics]:
    if not metrics:
        return []
    ordered = sorted(
        enumerate(metrics),
        key=lambda item: (
            -item[1].robust_net_payout_lcb,
            -item[1].elite_probability,
            item[0],
        ),
    )
    survivor_indices: set[int] = set()
    best_elite_at_higher_net = float("-inf")
    cursor = 0
    while cursor < len(ordered):
        net_value = ordered[cursor][1].robust_net_payout_lcb
        group: list[tuple[int, PortfolioMetrics]] = []
        while (
            cursor < len(ordered)
            and ordered[cursor][1].robust_net_payout_lcb == net_value
        ):
            group.append(ordered[cursor])
            cursor += 1
        group_best_elite = max(item.elite_probability for _, item in group)
        if group_best_elite > best_elite_at_higher_net:
            survivor_indices.update(
                index
                for index, item in group
                if item.elite_probability == group_best_elite
            )
        best_elite_at_higher_net = max(best_elite_at_higher_net, group_best_elite)
    return [item for index, item in enumerate(metrics) if index in survivor_indices]


def _evaluate_combinations_batched(
    state_economics: Mapping[str, CandidateEconomics],
    combinations: list[tuple[int, ...]],
    *,
    entry_fee: float,
    field_size: int,
    objective: ContestObjective,
    batch_size: int = 256,
) -> list[PortfolioMetrics]:
    if objective is ContestObjective.LARGE_GPP:
        elite_rank = max(1, math.ceil(0.001 * field_size))
    elif objective is ContestObjective.SMALL_GPP:
        elite_rank = max(1, math.ceil(0.01 * field_size))
    else:
        elite_rank = 1
    top_one_rank = max(1, math.ceil(0.01 * field_size))
    results: list[PortfolioMetrics] = []
    for start in range(0, len(combinations), batch_size):
        batch = combinations[start : start + batch_size]
        indices = np.asarray(batch, dtype=np.int32)
        count = len(batch)
        robust_lcb = np.full(count, np.inf)
        elite_probability = np.full(count, np.inf)
        top_one_probability = np.full(count, np.inf)
        net_loss_probability = np.full(count, -np.inf)
        severe_loss_probability = np.full(count, -np.inf)
        zero_return_probability = np.full(count, -np.inf)
        expected_net = np.full(count, np.inf)
        payout_p05 = np.full(count, np.inf)
        payout_p50 = np.full(count, np.inf)
        payout_p95 = np.full(count, np.inf)
        cvar_05 = np.full(count, np.inf)
        worst_state = np.full(count, "", dtype=object)
        for state_name, economics in state_economics.items():
            gross, adjusted_ranks, entry_gross = _portfolio_settlement_batched(
                economics, indices
            )
            net = gross - entry_fee * indices.shape[1]
            mean = net.mean(axis=0)
            standard_error = (
                net.std(axis=0, ddof=1) / math.sqrt(len(net))
                if len(net) > 1
                else np.zeros(count)
            )
            state_lcb = mean - 1.96 * standard_error
            if objective in {
                ContestObjective.CASH,
                ContestObjective.WTA,
                ContestObjective.SATELLITE,
            }:
                any_elite = (entry_gross > 0).any(axis=2)
            else:
                any_elite = (adjusted_ranks <= elite_rank).any(axis=2)
            any_top_one = (adjusted_ranks <= top_one_rank).any(axis=2)
            total_fees = entry_fee * indices.shape[1]
            quantiles = np.quantile(net, (0.05, 0.50, 0.95), axis=0)
            tail_count = max(1, int(math.ceil(0.05 * len(net))))
            tail = np.partition(net, tail_count - 1, axis=0)[:tail_count].mean(axis=0)

            newly_worst = state_lcb < robust_lcb
            worst_state[newly_worst] = state_name
            robust_lcb = np.minimum(robust_lcb, state_lcb)
            elite_probability = np.minimum(elite_probability, any_elite.mean(axis=0))
            top_one_probability = np.minimum(
                top_one_probability, any_top_one.mean(axis=0)
            )
            net_loss_probability = np.maximum(
                net_loss_probability, (net < 0).mean(axis=0)
            )
            severe_loss_probability = np.maximum(
                severe_loss_probability, (net < -0.8 * total_fees).mean(axis=0)
            )
            zero_return_probability = np.maximum(
                zero_return_probability, (gross == 0).mean(axis=0)
            )
            expected_net = np.minimum(expected_net, mean)
            payout_p05 = np.minimum(payout_p05, quantiles[0])
            payout_p50 = np.minimum(payout_p50, quantiles[1])
            payout_p95 = np.minimum(payout_p95, quantiles[2])
            cvar_05 = np.minimum(cvar_05, tail)
        results.extend(
            PortfolioMetrics(
                candidate_indices=tuple(batch[index]),
                robust_net_payout_lcb=float(robust_lcb[index]),
                elite_probability=float(elite_probability[index]),
                top_one_percent_probability=float(top_one_probability[index]),
                net_loss_probability=float(net_loss_probability[index]),
                severe_loss_probability=float(severe_loss_probability[index]),
                zero_return_probability=float(zero_return_probability[index]),
                expected_net_payout=float(expected_net[index]),
                payout_p05=float(payout_p05[index]),
                payout_p50=float(payout_p50[index]),
                payout_p95=float(payout_p95[index]),
                cvar_05=float(cvar_05[index]),
                worst_state=str(worst_state[index]),
            )
            for index in range(count)
        )
    return results


def select_portfolio(
    state_economics: Mapping[str, CandidateEconomics],
    *,
    entry_count: int,
    entry_fee: float,
    field_size: int,
    objective: ContestObjective,
    shortlist_limit: int = 250,
    maximum_exact_combinations: int = 50_000,
) -> PortfolioMetrics:
    if not state_economics:
        raise ValueError("at least one field state is required")
    first = next(iter(state_economics.values()))
    candidate_count = len(first.rosters)
    if any(value.rosters != first.rosters for value in state_economics.values()):
        raise ValueError("field states do not share a candidate bank")
    if maximum_exact_combinations < 1:
        raise ValueError("maximum_exact_combinations must be positive")
    if shortlist_limit < 1:
        raise ValueError("shortlist_limit must be positive")
    if not np.isfinite(entry_fee) or entry_fee < 0:
        raise ValueError("entry fee must be finite and non-negative")
    if field_size < 2:
        raise ValueError("field size must be at least two")
    limited = min(candidate_count, shortlist_limit)
    if not 1 <= entry_count <= min(150, limited):
        raise ValueError("entry count must be between one and 150 and no larger than shortlist")

    evaluation_count = 0

    def evaluate(indices: tuple[int, ...]) -> PortfolioMetrics:
        nonlocal evaluation_count
        evaluation_count += 1
        return evaluate_portfolio(
            state_economics,
            indices,
            entry_fee=entry_fee,
            field_size=field_size,
            objective=objective,
        )

    if entry_count <= 3:
        while (
            limited > entry_count
            and math.comb(limited, entry_count) > maximum_exact_combinations
        ):
            limited -= 1
        combinations = list(itertools.combinations(range(limited), entry_count))
        evaluated = _evaluate_combinations_batched(
            state_economics,
            combinations,
            entry_fee=entry_fee,
            field_size=field_size,
            objective=objective,
        )
        frontier = _nondominated(evaluated)
    else:
        selected: tuple[int, ...] = ()
        remaining = set(range(limited))
        while len(selected) < entry_count:
            additions = [evaluate(tuple(sorted((*selected, candidate)))) for candidate in remaining]
            choice = _choose_nash(_nondominated(additions))
            added = next(index for index in choice.candidate_indices if index not in selected)
            selected = choice.candidate_indices
            remaining.remove(added)
        # Two bounded one-entry exchange passes preserve the registered live deadline.
        incumbent = evaluate(selected)
        for _ in range(2):
            exchanges: list[PortfolioMetrics] = [incumbent]
            outside = sorted(set(range(limited)).difference(incumbent.candidate_indices))
            for remove_index in incumbent.candidate_indices:
                base = tuple(index for index in incumbent.candidate_indices if index != remove_index)
                for add_index in outside:
                    exchanges.append(evaluate(tuple(sorted((*base, add_index)))))
            improved = _choose_nash(_nondominated(exchanges))
            if improved.candidate_indices == incumbent.candidate_indices:
                break
            incumbent = improved
        return replace(
            incumbent,
            selection_candidate_count=limited,
            evaluated_portfolio_count=evaluation_count,
        )

    return replace(
        _choose_nash(frontier),
        selection_candidate_count=limited,
        evaluated_portfolio_count=len(evaluated),
    )


def _choose_nash(frontier: list[PortfolioMetrics]) -> PortfolioMetrics:
    if not frontier:
        raise ValueError("portfolio frontier is empty")
    net_values = np.array([item.robust_net_payout_lcb for item in frontier])
    elite_values = np.array([item.elite_probability for item in frontier])

    def normalize(value: float, values: np.ndarray) -> float:
        spread = float(values.max() - values.min())
        return 1.0 if spread <= 1e-12 else (value - float(values.min())) / spread

    def key(item: PortfolioMetrics) -> tuple[float, float, float, tuple[int, ...]]:
        nash = normalize(item.robust_net_payout_lcb, net_values) * normalize(
            item.elite_probability, elite_values
        )
        return (
            nash,
            -item.net_loss_probability,
            -item.severe_loss_probability,
            tuple(-index for index in item.candidate_indices),
        )

    return max(frontier, key=key)
