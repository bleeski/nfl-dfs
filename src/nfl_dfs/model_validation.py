from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np


@dataclass(frozen=True)
class SimulationGateReport:
    status: str
    proper_score_improvement: float
    interval_coverage_error: dict[str, float]
    tail_relative_error: dict[str, float]
    dependency_failures: tuple[str, ...]
    sample_warnings: tuple[str, ...]
    blockers: tuple[str, ...]


def quantile_pinball_score(actual: np.ndarray, draws: np.ndarray) -> float:
    actual_values = np.asarray(actual, dtype=float)
    scenarios = np.asarray(draws, dtype=float)
    if scenarios.ndim != 2 or scenarios.shape[1] != len(actual_values):
        raise ValueError("draws must be scenarios by observations")
    losses: list[float] = []
    for quantile in (0.1, 0.25, 0.5, 0.75, 0.9):
        prediction = np.quantile(scenarios, quantile, axis=0)
        error = actual_values - prediction
        losses.append(float(np.mean(np.maximum(quantile * error, (quantile - 1) * error))))
    return float(np.mean(losses))


def validate_simulation_draws(
    *,
    actual: np.ndarray,
    model_draws: np.ndarray,
    baseline_draws: np.ndarray,
    positions: np.ndarray,
    model_dependencies: Mapping[str, float],
    dependency_bands: Mapping[str, tuple[float, float]],
    minimum_position_sample: int = 20,
    minimum_tail_sample: int = 100,
) -> SimulationGateReport:
    actual_values = np.asarray(actual, dtype=float)
    positions_array = np.asarray(positions)
    if len(actual_values) != len(positions_array):
        raise ValueError("position labels must align with actual outcomes")
    model_score = quantile_pinball_score(actual_values, model_draws)
    baseline_score = quantile_pinball_score(actual_values, baseline_draws)
    proper_improvement = baseline_score - model_score
    blockers: list[str] = []
    warnings: list[str] = []
    if proper_improvement <= 0:
        blockers.append("PROPER_SCORE_NOT_BETTER_THAN_BASELINE")

    coverage_error: dict[str, float] = {}
    for position in sorted(set(positions_array.tolist())):
        mask = positions_array == position
        count = int(mask.sum())
        if count < minimum_position_sample:
            warnings.append(f"{position}:INTERVAL_SAMPLE_{count}_BELOW_{minimum_position_sample}")
            continue
        errors = []
        for level in (0.50, 0.80, 0.90, 0.95):
            lower_q = (1.0 - level) / 2.0
            upper_q = 1.0 - lower_q
            lower = np.quantile(model_draws[:, mask], lower_q, axis=0)
            upper = np.quantile(model_draws[:, mask], upper_q, axis=0)
            observed = float(((actual_values[mask] >= lower) & (actual_values[mask] <= upper)).mean())
            errors.append(abs(observed - level))
        maximum_error = max(errors)
        coverage_error[position] = maximum_error
        if maximum_error > 0.05:
            blockers.append(f"INTERVAL_COVERAGE:{position}:{maximum_error:.4f}")

    tail_error: dict[str, float] = {}
    if len(actual_values) < minimum_tail_sample:
        warnings.append(f"TAIL_SAMPLE_{len(actual_values)}_BELOW_{minimum_tail_sample}")
    else:
        for quantile, expected in ((0.95, 0.05), (0.99, 0.01)):
            threshold = np.quantile(model_draws, quantile, axis=0)
            exceedance = float((actual_values > threshold).mean())
            relative_error = abs(exceedance - expected) / expected
            tail_error[f"q{int(quantile * 100)}"] = relative_error
            if relative_error > 0.20:
                blockers.append(
                    f"TAIL_EXCEEDANCE:q{int(quantile * 100)}:{relative_error:.4f}"
                )

    dependency_failures: list[str] = []
    for name, (lower, upper) in dependency_bands.items():
        value = model_dependencies.get(name)
        if value is None or not lower <= value <= upper:
            dependency_failures.append(
                f"{name}:{'UNKNOWN' if value is None else value}:expected[{lower},{upper}]"
            )
    blockers.extend(f"DEPENDENCY:{failure}" for failure in dependency_failures)
    return SimulationGateReport(
        status="PASS" if not blockers else "SIMULATION_DIAGNOSTIC_ONLY",
        proper_score_improvement=proper_improvement,
        interval_coverage_error=coverage_error,
        tail_relative_error=tail_error,
        dependency_failures=tuple(dependency_failures),
        sample_warnings=tuple(warnings),
        blockers=tuple(blockers),
    )
