from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, replace
from typing import Mapping

import numpy as np

from .contracts import ContestObjective
from .economics import CandidateEconomics


# The declared, scenario-count-independent risk preference.
#
# R07: the ranking axis was `mean - 1.96 * standard_error`, whose penalty
# shrinks with the square root of the scenario count, so the computation budget
# was part of the economic preference. Two candidates on a fixed 100-scenario
# payout distribution chose the constant-1.5 candidate; replicating those same
# rows 100 times, with the empirical distribution unchanged, chose the variable
# candidate with mean 2.0.
#
# The objective is now a convex combination of the expectation and a fixed
# tail measure, with a weight declared here rather than emerging from `S`.
# `RISK_AVERSION = 0.0` selects on the expectation, which is what the objective
# was always trying to maximize; raising it is a deliberate, recorded decision.
# Monte Carlo uncertainty is reported separately and never enters the
# objective. This adds no field, ownership, leverage, correlation or
# duplication economics: R05, R06 and S7 own those, and the objective still
# maximizes a central estimate, which in a large-field GPP is chalk.
RISK_MEASURE = "MEAN_CVAR_05_CONVEX_V1"
RISK_AVERSION = 0.0
CVAR_TAIL_FRACTION = 0.05


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
    # The ranking axis, its reported Monte Carlo uncertainty, and the effective
    # sample size that uncertainty was computed against. The objective is
    # invariant to scenario count; only the uncertainty moves with precision.
    selection_objective: float = 0.0
    objective_standard_error: float = 0.0
    effective_scenario_count: float = 0.0
    risk_measure: str = RISK_MEASURE
    risk_aversion: float = RISK_AVERSION


def effective_sample_size(multiplicity: np.ndarray) -> float:
    """Kish effective sample size for a bank with repeated scenarios.

    `multiplicity[j]` is how many rows of the bank carry scenario `j`'s draw. A
    bank of `m` distinct draws each repeated `c` times has the effective size
    of the `m` draws, not of `m * c`. Every row carries unit weight, so the
    Kish size collapses to `S**2 / sum(c_g**2)` over distinct draws `g`, and
    `sum(c_g**2)` is the sum of this per-row vector. All-ones gives back `S`
    exactly, so an honest bank reports exactly the uncertainty it used to.

    Multiplicity is declared by the caller, never inferred from outcomes.
    Independent scenarios routinely settle a portfolio at the same value, so
    collapsing equal outcomes into one draw would understate real precision,
    and an overstated standard error *widens* the REFEREE tolerance in
    `qa.referee_blocks`. `economics.evaluate_candidates_against_field` refuses
    any non-uniform scenario bank, so today every production bank is
    all-distinct and this returns the row count.
    """

    total = int(np.shape(multiplicity)[0])
    if total == 0:
        return 0.0
    squared = float(np.sum(multiplicity, dtype=np.float64))
    if squared <= 0:
        return 0.0
    return float(total * total) / squared


def resolve_effective_sample_size(
    scenarios: int, multiplicity: np.ndarray | None = None
) -> float:
    """Effective sample size for a bank, from declared multiplicity or none."""

    if multiplicity is None:
        return float(scenarios)
    if int(np.shape(multiplicity)[0]) != scenarios:
        raise ValueError("scenario multiplicity must have one entry per scenario row")
    if np.any(np.asarray(multiplicity) < 1):
        raise ValueError("scenario multiplicity entries must be at least one")
    return effective_sample_size(multiplicity)


def _declared_effective(
    economics: CandidateEconomics,
    state: str,
    declared: Mapping[str, np.ndarray] | None,
) -> float:
    scenarios = int(economics.gross_payout.shape[0])
    return resolve_effective_sample_size(
        scenarios, None if declared is None else declared.get(state)
    )


def _tail_count(size: int, fraction: float = CVAR_TAIL_FRACTION) -> int:
    return max(1, int(math.ceil(fraction * size)))


def portfolio_objective(
    net: np.ndarray,
    *,
    risk_aversion: float = RISK_AVERSION,
    tail_fraction: float = CVAR_TAIL_FRACTION,
) -> float:
    """The declared economic objective for one portfolio on one bank.

    Scenario count enters only through the empirical distribution, so
    duplicating rows cannot move it.
    """

    mean = float(np.mean(net))
    if risk_aversion <= 0:
        return mean
    tail = float(np.mean(np.sort(net)[: _tail_count(net.size, tail_fraction)]))
    return (1.0 - risk_aversion) * mean + risk_aversion * tail


def _batched_objective(
    net: np.ndarray,
    *,
    risk_aversion: float = RISK_AVERSION,
    tail_fraction: float = CVAR_TAIL_FRACTION,
) -> np.ndarray:
    """`portfolio_objective` over a scenarios-by-portfolio array."""

    mean = net.mean(axis=0)
    if risk_aversion <= 0:
        return mean
    count = _tail_count(len(net), tail_fraction)
    tail = np.partition(net, count - 1, axis=0)[:count].mean(axis=0)
    return (1.0 - risk_aversion) * mean + risk_aversion * tail


def objective_standard_error(net: np.ndarray, effective: float) -> float:
    """Monte Carlo uncertainty of the estimate, against effective sample size.

    Reported, never selected on. Uses the population second moment scaled to
    the effective size, so an all-distinct bank returns exactly the classical
    `sd(ddof=1) / sqrt(S)` and a bank of replicated rows returns the
    uncertainty of the distinct rows it actually contains.
    """

    if effective <= 1.0 or np.size(net) < 2:
        return 0.0
    centered = np.asarray(net, dtype=np.float64) - float(np.mean(net))
    population = float(np.dot(centered, centered)) / float(np.size(net))
    variance = population * effective / (effective - 1.0)
    return math.sqrt(variance / effective)


def _batched_standard_error(net: np.ndarray, effective: float) -> np.ndarray:
    if effective <= 1.0 or len(net) < 2:
        return np.zeros(net.shape[1])
    population = net.var(axis=0, ddof=0)
    variance = population * effective / (effective - 1.0)
    return np.sqrt(variance / effective)


def unpaired_difference_standard_error(
    first_economics: CandidateEconomics,
    first_indices: tuple[int, ...],
    second_economics: CandidateEconomics,
    second_indices: tuple[int, ...],
    *,
    entry_fee: float,
    first_multiplicity: np.ndarray | None = None,
    second_multiplicity: np.ndarray | None = None,
) -> float:
    """Two independent banks cannot be paired, so their variances add.

    This is the SELECT-versus-REFEREE comparison: separate seeds, separate
    draws, no scenario in common to pair on. With no declared multiplicity
    this reproduces the row-count divisor exactly. The paired case, where two
    portfolios are compared on one bank, lives in `qa.decide_repair`, which
    takes the per-scenario difference and keeps the pairing.
    """

    first = portfolio_net_samples(first_economics, first_indices, entry_fee=entry_fee)
    second = portfolio_net_samples(second_economics, second_indices, entry_fee=entry_fee)
    first_error = objective_standard_error(
        first, resolve_effective_sample_size(len(first), first_multiplicity)
    )
    second_error = objective_standard_error(
        second, resolve_effective_sample_size(len(second), second_multiplicity)
    )
    return math.sqrt(first_error**2 + second_error**2)


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
    effective: float | None = None,
) -> dict[str, float]:
    gross, adjusted_ranks, entry_gross = _portfolio_settlement(economics, indices)
    net = gross - entry_fee * len(indices)
    if objective in {ContestObjective.CASH, ContestObjective.WTA, ContestObjective.SATELLITE}:
        any_elite = (entry_gross > 0).any(axis=1)
    else:
        any_elite = (adjusted_ranks <= elite_rank).any(axis=1)
    any_top_one = (adjusted_ranks <= top_one_percent_rank).any(axis=1)
    mean = float(net.mean())
    if effective is None:
        effective = float(len(net))
    standard_error = objective_standard_error(net, effective)
    sorted_net = np.sort(net)
    tail_count = _tail_count(len(net))
    total_fees = entry_fee * len(indices)
    return {
        "selection_objective": portfolio_objective(net),
        "objective_standard_error": standard_error,
        "effective_sample_size": effective,
        # Reported, not selected on. A confidence bound is an honest statement
        # about the estimate and a dishonest ranking axis.
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
    scenario_multiplicity: Mapping[str, np.ndarray] | None = None,
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
            effective=_declared_effective(economics, state, scenario_multiplicity),
        )
        for state, economics in state_economics.items()
    }
    # The worst field state on the declared objective, not on a confidence
    # bound whose width depends on how many scenarios were run.
    worst_state = min(results, key=lambda state: results[state]["selection_objective"])
    worst = results[worst_state]
    return PortfolioMetrics(
        candidate_indices=indices,
        selection_objective=min(
            value["selection_objective"] for value in results.values()
        ),
        # The most uncertain state, so reported precision is never flattered by
        # averaging a sharp state against a vague one.
        objective_standard_error=max(
            value["objective_standard_error"] for value in results.values()
        ),
        effective_scenario_count=min(
            value["effective_sample_size"] for value in results.values()
        ),
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
            -item[1].selection_objective,
            -item[1].elite_probability,
            item[0],
        ),
    )
    survivor_indices: set[int] = set()
    best_elite_at_higher_net = float("-inf")
    cursor = 0
    while cursor < len(ordered):
        net_value = ordered[cursor][1].selection_objective
        group: list[tuple[int, PortfolioMetrics]] = []
        while (
            cursor < len(ordered)
            and ordered[cursor][1].selection_objective == net_value
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
    scenario_multiplicity: Mapping[str, np.ndarray] | None = None,
) -> list[PortfolioMetrics]:
    effective_by_state = {
        state: _declared_effective(economics, state, scenario_multiplicity)
        for state, economics in state_economics.items()
    }
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
        selection_objective = np.full(count, np.inf)
        objective_error = np.full(count, -np.inf)
        effective_count = np.full(count, np.inf)
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
            effective = effective_by_state[state_name]
            standard_error = _batched_standard_error(net, effective)
            state_objective = _batched_objective(net)
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

            newly_worst = state_objective < selection_objective
            worst_state[newly_worst] = state_name
            selection_objective = np.minimum(selection_objective, state_objective)
            objective_error = np.maximum(objective_error, standard_error)
            effective_count = np.minimum(effective_count, np.full(count, effective))
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
                selection_objective=float(selection_objective[index]),
                objective_standard_error=float(objective_error[index]),
                effective_scenario_count=float(effective_count[index]),
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
    scenario_multiplicity: Mapping[str, np.ndarray] | None = None,
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
            scenario_multiplicity=scenario_multiplicity,
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
            scenario_multiplicity=scenario_multiplicity,
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
    net_values = np.array([item.selection_objective for item in frontier])
    elite_values = np.array([item.elite_probability for item in frontier])

    def normalize(value: float, values: np.ndarray) -> float:
        spread = float(values.max() - values.min())
        return 1.0 if spread <= 1e-12 else (value - float(values.min())) / spread

    def key(item: PortfolioMetrics) -> tuple[float, float, float, tuple[int, ...]]:
        nash = normalize(item.selection_objective, net_values) * normalize(
            item.elite_probability, elite_values
        )
        return (
            nash,
            -item.net_loss_probability,
            -item.severe_loss_probability,
            tuple(-index for index in item.candidate_indices),
        )

    return max(frontier, key=key)
