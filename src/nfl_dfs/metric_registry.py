from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from .hashing import sha256_file


METRIC_REGISTRY_VERSION = "nfl_metric_promotion_registry_v1"
REQUIRED_DOMAINS = frozenset(
    {
        "PLAYER_OUTCOME",
        "PARTICIPATION",
        "OWNERSHIP",
        "DUPLICATION",
        "RANK_PAYOUT_TAIL",
        "PORTFOLIO",
        "OPERATIONS",
    }
)


class MetricRegistryError(ValueError):
    pass


@dataclass(frozen=True)
class MetricRegistryRecord:
    path: str
    sha256: str
    registry_id: str
    registered_at: datetime
    metrics: tuple[Mapping[str, Any], ...]
    data: Mapping[str, Any]


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise MetricRegistryError(f"{label} must be an object")
    return value


def _positive_number(value: object, label: str, *, allow_zero: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MetricRegistryError(f"{label} must be numeric")
    numeric = float(value)
    if not math.isfinite(numeric) or numeric < 0 or (numeric == 0 and not allow_zero):
        qualifier = "non-negative" if allow_zero else "positive"
        raise MetricRegistryError(f"{label} must be finite and {qualifier}")
    return numeric


def _nonempty_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MetricRegistryError(f"{label} must be nonempty text")
    return value.strip()


def load_metric_registry(path: str | Path) -> MetricRegistryRecord:
    registry_path = Path(path).resolve()
    try:
        decoded = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise MetricRegistryError(f"invalid metric registry: {exc}") from exc
    data = _mapping(decoded, "metric registry")
    if data.get("schema_version") != METRIC_REGISTRY_VERSION:
        raise MetricRegistryError(
            f"metric registry schema_version must be {METRIC_REGISTRY_VERSION}"
        )
    registry_id = _nonempty_text(data.get("registry_id"), "registry_id")
    if data.get("status") != "PREDECLARED":
        raise MetricRegistryError("metric registry status must be PREDECLARED")
    try:
        registered_at = datetime.fromisoformat(
            _nonempty_text(data.get("registered_at"), "registered_at").replace(
                "Z", "+00:00"
            )
        )
    except ValueError as exc:
        raise MetricRegistryError("registered_at must be ISO 8601") from exc
    if registered_at.tzinfo is None:
        raise MetricRegistryError("registered_at must be timezone-aware")
    _nonempty_text(data.get("threshold_basis"), "threshold_basis")
    if data.get("fitted_to_challenger_or_holdout") is not False:
        raise MetricRegistryError(
            "registry must state fitted_to_challenger_or_holdout=false"
        )

    raw_metrics = data.get("metrics")
    if not isinstance(raw_metrics, list) or not raw_metrics:
        raise MetricRegistryError("metrics must be a nonempty array")
    metrics: list[Mapping[str, Any]] = []
    ids: set[str] = set()
    domains: set[str] = set()
    for index, raw_metric in enumerate(raw_metrics):
        metric = _mapping(raw_metric, f"metrics[{index}]")
        metric_id = _nonempty_text(metric.get("metric_id"), f"metrics[{index}].metric_id")
        if metric_id in ids:
            raise MetricRegistryError(f"duplicate metric_id: {metric_id}")
        ids.add(metric_id)
        domain = _nonempty_text(metric.get("domain"), f"metrics[{index}].domain")
        if domain not in REQUIRED_DOMAINS:
            raise MetricRegistryError(f"unsupported metric domain: {domain}")
        domains.add(domain)
        if metric.get("direction") not in {"MINIMIZE", "MAXIMIZE"}:
            raise MetricRegistryError(
                f"metrics[{index}].direction must be MINIMIZE or MAXIMIZE"
            )
        for field in (
            "definition",
            "unit",
            "uncertainty_interval",
            "effective_sample_size",
            "rationale",
        ):
            _nonempty_text(metric.get(field), f"metrics[{index}].{field}")
        minimum = metric.get("minimum_sample")
        if isinstance(minimum, bool) or not isinstance(minimum, int) or minimum < 1:
            raise MetricRegistryError(
                f"metrics[{index}].minimum_sample must be a positive integer"
            )
        thresholds = _mapping(metric.get("thresholds"), f"metrics[{index}].thresholds")
        for threshold in (
            "promotion_delta",
            "noninferiority_margin",
            "demotion_delta",
            "rollback_delta",
        ):
            _positive_number(
                thresholds.get(threshold),
                f"metrics[{index}].thresholds.{threshold}",
                allow_zero=True,
            )
        metrics.append(metric)
    missing_domains = sorted(REQUIRED_DOMAINS.difference(domains))
    if missing_domains:
        raise MetricRegistryError(f"metric domains are incomplete: {missing_domains}")

    split = _mapping(data.get("temporal_split_policy"), "temporal_split_policy")
    if split.get("group_unit") != "SLATE":
        raise MetricRegistryError("temporal split group_unit must be SLATE")
    if split.get("order_by") != "LOCK_TIME_UTC":
        raise MetricRegistryError("temporal split order_by must be LOCK_TIME_UTC")
    if split.get("challenger_selection_data") != "TRAIN_AND_VALIDATION_ONLY":
        raise MetricRegistryError(
            "challenger selection must be limited to TRAIN_AND_VALIDATION_ONLY"
        )
    if split.get("holdout_policy") != "UNTOUCHED_UNTIL_FINAL_PROMOTION_DECISION":
        raise MetricRegistryError("holdout policy must remain untouched until promotion")
    for name in ("minimum_train_slates", "minimum_validation_slates", "minimum_holdout_slates"):
        value = split.get(name)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise MetricRegistryError(f"temporal_split_policy.{name} must be positive")

    runtime = _mapping(data.get("runtime_limits"), "runtime_limits")
    for name in (
        "maximum_evaluation_seconds",
        "maximum_peak_memory_bytes",
        "maximum_reference_field_entries",
        "maximum_reference_work_units",
    ):
        _positive_number(runtime.get(name), f"runtime_limits.{name}")

    policy = _mapping(data.get("promotion_policy"), "promotion_policy")
    if policy.get("all_registered_metrics_required") is not True:
        raise MetricRegistryError("promotion requires all registered metrics")
    if policy.get("missing_metric_action") != "DO_NOT_PROMOTE":
        raise MetricRegistryError("missing metrics must result in DO_NOT_PROMOTE")
    if policy.get("rollback_on_integrity_failure") != "IMMEDIATE":
        raise MetricRegistryError("integrity failures must trigger immediate rollback")
    windows = policy.get("demotion_windows")
    if isinstance(windows, bool) or not isinstance(windows, int) or windows < 1:
        raise MetricRegistryError("promotion_policy.demotion_windows must be positive")
    _nonempty_text(policy.get("multiple_testing_control"), "multiple_testing_control")
    _nonempty_text(policy.get("uncertainty_rule"), "uncertainty_rule")

    return MetricRegistryRecord(
        path=str(registry_path),
        sha256=sha256_file(registry_path),
        registry_id=registry_id,
        registered_at=registered_at,
        metrics=tuple(metrics),
        data=data,
    )


def require_registry_precedes_evaluation(
    registry: MetricRegistryRecord, evaluated_at: datetime
) -> None:
    if evaluated_at.tzinfo is None:
        raise MetricRegistryError("challenger evaluation time must be timezone-aware")
    if registry.registered_at >= evaluated_at:
        raise MetricRegistryError(
            "METRIC_REGISTRY_NOT_PREDECLARED: registered_at must precede challenger evaluation"
        )
