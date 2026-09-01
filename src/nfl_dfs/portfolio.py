from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
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


def _state_metrics(
    economics: CandidateEconomics,
    indices: tuple[int, ...],
    *,
    entry_fee: float,
    elite_rank: int,
    top_one_percent_rank: int,
    objective: ContestObjective,
) -> dict[str, float]:
    gross = economics.gross_payout[:, indices].sum(axis=1)
    net = gross - entry_fee * len(indices)
    if objective in {ContestObjective.CASH, ContestObjective.WTA, ContestObjective.SATELLITE}:
        any_elite = (economics.gross_payout[:, indices] > 0).any(axis=1)
    else:
        any_elite = (economics.ranks[:, indices] <= elite_rank).any(axis=1)
    any_top_one = (economics.ranks[:, indices] <= top_one_percent_rank).any(axis=1)
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
    frontier: list[PortfolioMetrics] = []
    for candidate in metrics:
        dominated = any(
            other.robust_net_payout_lcb >= candidate.robust_net_payout_lcb
            and other.elite_probability >= candidate.elite_probability
            and (
                other.robust_net_payout_lcb > candidate.robust_net_payout_lcb
                or other.elite_probability > candidate.elite_probability
            )
            for other in metrics
        )
        if not dominated:
            frontier.append(candidate)
    return frontier


def select_portfolio(
    state_economics: Mapping[str, CandidateEconomics],
    *,
    entry_count: int,
    entry_fee: float,
    field_size: int,
    objective: ContestObjective,
    shortlist_limit: int = 250,
) -> PortfolioMetrics:
    first = next(iter(state_economics.values()))
    candidate_count = len(first.rosters)
    if any(len(value.rosters) != candidate_count for value in state_economics.values()):
        raise ValueError("field states do not share a candidate bank")
    limited = min(candidate_count, shortlist_limit)
    if not 1 <= entry_count <= min(150, limited):
        raise ValueError("entry count must be between one and 150 and no larger than shortlist")

    def evaluate(indices: tuple[int, ...]) -> PortfolioMetrics:
        return evaluate_portfolio(
            state_economics,
            indices,
            entry_fee=entry_fee,
            field_size=field_size,
            objective=objective,
        )

    if entry_count <= 3:
        evaluated = [evaluate(indices) for indices in itertools.combinations(range(limited), entry_count)]
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
        return incumbent

    return _choose_nash(frontier)


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
