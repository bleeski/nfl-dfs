from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from nfl_dfs.model_validation import validate_simulation_draws
from nfl_dfs.training import fit_weekly_ridge_challenger, rolling_origin_splits


def test_simulation_validation_fails_closed_on_bad_model() -> None:
    rng = np.random.default_rng(1)
    actual = rng.normal(10, 2, size=120)
    bad = rng.normal(50, 1, size=(200, 120))
    baseline = rng.normal(10, 3, size=(200, 120))
    positions = np.array(["WR"] * 120)
    report = validate_simulation_draws(
        actual=actual,
        model_draws=bad,
        baseline_draws=baseline,
        positions=positions,
        model_dependencies={"qb_receiver": -0.2},
        dependency_bands={"qb_receiver": (0.2, 0.8)},
    )
    assert report.status == "SIMULATION_DIAGNOSTIC_ONLY"
    assert "PROPER_SCORE_NOT_BETTER_THAN_BASELINE" in report.blockers
    assert report.dependency_failures


def test_weekly_ridge_uses_rolling_origin_and_rejects_leakage() -> None:
    rng = np.random.default_rng(4)
    observations = 160
    x = rng.normal(size=(observations, 3))
    y = 2 * x[:, 0] - x[:, 1] + rng.normal(scale=0.1, size=observations)
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    outcomes = [start + timedelta(days=index) for index in range(observations)]
    features = [value - timedelta(hours=1) for value in outcomes]
    assert rolling_origin_splits(outcomes, minimum_train=100, validation_size=20)
    result = fit_weekly_ridge_challenger(
        features=x,
        target=y,
        feature_as_of=features,
        outcome_at=outcomes,
        minimum_train=100,
        validation_size=20,
    )
    assert result.validation_mse < result.baseline_mse
    assert result.reproducible and result.leakage_free
    with pytest.raises(ValueError, match="after its outcome"):
        fit_weekly_ridge_challenger(
            features=x,
            target=y,
            feature_as_of=[value + timedelta(hours=1) for value in outcomes],
            outcome_at=outcomes,
            minimum_train=100,
            validation_size=20,
        )


def test_validation_and_training_reject_nonfinite_numbers() -> None:
    with pytest.raises(ValueError, match="positive"):
        rolling_origin_splits(
            [datetime(2025, 1, 1, tzinfo=timezone.utc)],
            minimum_train=1,
            validation_size=0,
        )
    with pytest.raises(ValueError, match="finite"):
        validate_simulation_draws(
            actual=np.array([float("nan")]),
            model_draws=np.zeros((2, 1)),
            baseline_draws=np.zeros((2, 1)),
            positions=np.array(["WR"]),
            model_dependencies={"pair": 0.0},
            dependency_bands={"pair": (-1.0, 1.0)},
        )
    now = datetime(2025, 1, 1, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="finite"):
        fit_weekly_ridge_challenger(
            features=np.array([[float("inf")], [1.0]]),
            target=np.array([1.0, 2.0]),
            feature_as_of=[now, now + timedelta(days=1)],
            outcome_at=[now, now + timedelta(days=1)],
            minimum_train=1,
            validation_size=1,
        )
