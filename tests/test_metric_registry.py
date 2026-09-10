from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest

from nfl_dfs.cli import main
from nfl_dfs.metric_registry import (
    MetricRegistryError,
    REQUIRED_DOMAINS,
    load_metric_registry,
    require_registry_precedes_evaluation,
)


REGISTRY = Path(__file__).parents[1] / "config" / "metric_registry_q1_v1.json"


def test_metric_registration_is_complete_and_precedes_challenger_evaluation() -> None:
    registry = load_metric_registry(REGISTRY)
    assert {metric["domain"] for metric in registry.metrics} == REQUIRED_DOMAINS
    assert all(metric["minimum_sample"] > 0 for metric in registry.metrics)
    assert all(
        set(metric["thresholds"])
        == {
            "promotion_delta",
            "noninferiority_margin",
            "demotion_delta",
            "rollback_delta",
        }
        for metric in registry.metrics
    )
    require_registry_precedes_evaluation(
        registry, registry.registered_at + timedelta(seconds=1)
    )
    with pytest.raises(MetricRegistryError, match="NOT_PREDECLARED"):
        require_registry_precedes_evaluation(registry, registry.registered_at)


def test_learn_is_fail_closed_until_registered_metric_results_exist(capsys) -> None:
    result = main(
        [
            "learn",
            "--comparable-slates",
            "20",
            "--reproducible",
            "--integrity-pass",
            "--rolling-origin-improvement",
            "--calibration-pass",
            "--drift-pass",
            "--no-regression",
            "--prospective-field-gates",
            "--metric-registry",
            str(REGISTRY),
            "--challenger-evaluated-at",
            "2026-09-10T17:37:31Z",
        ]
    )
    assert result == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["promote"] is False
    assert payload["registry_policy_status"] == "REGISTRATION_ONLY_NO_MODEL_PROMOTION"
    assert "REGISTERED_METRIC_RESULTS_REQUIRED_Q6" in payload["promotion_failures"]


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda value: value.update(status="DRAFT"), "PREDECLARED"),
        (
            lambda value: value["metrics"].__setitem__(
                0, {**value["metrics"][0], "thresholds": {}}
            ),
            "promotion_delta",
        ),
        (
            lambda value: value.update(fitted_to_challenger_or_holdout=True),
            "fitted_to_challenger",
        ),
        (
            lambda value: value["temporal_split_policy"].update(
                holdout_policy="VIEWED_DURING_TUNING"
            ),
            "holdout policy",
        ),
    ],
)
def test_metric_registry_rejects_unregistered_or_posthoc_shapes(
    tmp_path: Path, mutation, message: str
) -> None:
    value = json.loads(REGISTRY.read_text(encoding="utf-8"))
    mutation(value)
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(MetricRegistryError, match=message):
        load_metric_registry(path)
