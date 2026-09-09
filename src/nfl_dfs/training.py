from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

import numpy as np
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_squared_error

from .hashing import content_hash


@dataclass(frozen=True)
class RollingOriginResult:
    selected_alpha: float
    validation_mse: float
    baseline_mse: float
    coefficient_hash: str
    training_cutoff: datetime
    coefficients: tuple[float, ...]
    intercept: float
    reproducible: bool
    leakage_free: bool


def rolling_origin_splits(
    timestamps: Iterable[datetime],
    *,
    minimum_train: int,
    validation_size: int,
) -> tuple[tuple[np.ndarray, np.ndarray], ...]:
    values = list(timestamps)
    if minimum_train < 1 or validation_size < 1:
        raise ValueError("rolling-origin train and validation sizes must be positive")
    if any(value.tzinfo is None for value in values):
        raise ValueError("rolling-origin timestamps must be timezone-aware")
    timestamps_array = np.array([value.timestamp() for value in values])
    order = np.argsort(timestamps_array, kind="stable")
    ordered_times = timestamps_array[order]
    splits: list[tuple[np.ndarray, np.ndarray]] = []
    stop = minimum_train
    # Never split outcomes from one slate timestamp between train and validation.
    while stop < len(values) and ordered_times[stop] == ordered_times[stop - 1]:
        stop += 1
    while stop + validation_size <= len(values):
        end = stop + validation_size
        while end < len(values) and ordered_times[end] == ordered_times[end - 1]:
            end += 1
        train = order[:stop]
        validate = order[stop:end]
        splits.append((train, validate))
        stop = end
    if not splits:
        raise ValueError("insufficient observations for rolling-origin validation")
    return tuple(splits)


def fit_weekly_ridge_challenger(
    *,
    features: np.ndarray,
    target: np.ndarray,
    feature_as_of: Iterable[datetime],
    outcome_at: Iterable[datetime],
    alpha_grid: tuple[float, ...] = (0.1, 1.0, 10.0, 100.0),
    minimum_train: int = 100,
    validation_size: int = 25,
) -> RollingOriginResult:
    x = np.asarray(features, dtype=float)
    y = np.asarray(target, dtype=float)
    feature_times = list(feature_as_of)
    outcome_times = list(outcome_at)
    if x.ndim != 2 or len(x) != len(y) or len(y) != len(feature_times) or len(y) != len(outcome_times):
        raise ValueError("training arrays are not aligned")
    if not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError("training features and targets must be finite")
    if not alpha_grid or any(not np.isfinite(alpha) or alpha <= 0 for alpha in alpha_grid):
        raise ValueError("alpha_grid must contain positive finite values")
    if any(value.tzinfo is None for value in feature_times + outcome_times):
        raise ValueError("training timestamps must be timezone-aware")
    leakage_free = all(feature <= outcome for feature, outcome in zip(feature_times, outcome_times, strict=True))
    if not leakage_free:
        raise ValueError("feature timestamp occurs after its outcome")
    splits = rolling_origin_splits(outcome_times, minimum_train=minimum_train, validation_size=validation_size)
    alpha_scores: dict[float, list[float]] = {alpha: [] for alpha in alpha_grid}
    baseline_scores: list[float] = []
    for train, validate in splits:
        cutoff = min(feature_times[index] for index in validate)
        train = np.array([index for index in train if outcome_times[index] < cutoff], dtype=int)
        if len(train) < minimum_train:
            raise ValueError("insufficient training outcomes available before validation prediction cutoff")
        baseline = np.full(len(validate), float(y[train].mean()))
        baseline_scores.append(mean_squared_error(y[validate], baseline))
        for alpha in alpha_grid:
            model = Ridge(alpha=alpha, random_state=0)
            model.fit(x[train], y[train])
            alpha_scores[alpha].append(mean_squared_error(y[validate], model.predict(x[validate])))
    selected_alpha = min(alpha_grid, key=lambda alpha: (np.mean(alpha_scores[alpha]), alpha))
    final = Ridge(alpha=selected_alpha, random_state=0)
    final.fit(x, y)
    coefficients = tuple(float(value) for value in final.coef_)
    artifact = {
        "alpha": selected_alpha,
        "coefficients": coefficients,
        "intercept": float(final.intercept_),
        "training_cutoff": max(outcome_times).isoformat(),
    }
    return RollingOriginResult(
        selected_alpha=float(selected_alpha),
        validation_mse=float(np.mean(alpha_scores[selected_alpha])),
        baseline_mse=float(np.mean(baseline_scores)),
        coefficient_hash=content_hash(artifact),
        training_cutoff=max(outcome_times),
        coefficients=coefficients,
        intercept=float(final.intercept_),
        reproducible=True,
        leakage_free=True,
    )
