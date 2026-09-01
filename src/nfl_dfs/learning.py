from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class PromotionDecision:
    promote: bool
    tier: str
    influence_cap: float
    reasons: tuple[str, ...]


def field_model_tier(comparable_settled_slates: int, prospective_gates_pass: bool) -> tuple[str, float]:
    if comparable_settled_slates < 3 or not prospective_gates_pass:
        return "COLD", 0.0
    if comparable_settled_slates < 10:
        return "PROVISIONAL", 0.25
    if comparable_settled_slates < 20:
        return "GRADED", 0.50
    return "CALIBRATED", 1.0


def evaluate_challenger(
    *,
    comparable_settled_slates: int,
    reproducible: bool,
    integrity_pass: bool,
    rolling_origin_improvement: bool,
    calibration_pass: bool,
    drift_pass: bool,
    no_regression: bool,
    prospective_field_gates: bool,
    realized_roi_observed: float | None = None,
) -> PromotionDecision:
    del realized_roi_observed  # ROI is descriptive and never a promotion input here.
    tier, influence = field_model_tier(comparable_settled_slates, prospective_field_gates)
    checks: Mapping[str, bool] = {
        "reproducibility": reproducible,
        "integrity": integrity_pass,
        "rolling_origin_improvement": rolling_origin_improvement,
        "calibration": calibration_pass,
        "drift": drift_pass,
        "no_regression": no_regression,
    }
    failures = tuple(name for name, passed in checks.items() if not passed)
    return PromotionDecision(not failures, tier, influence, failures)


def should_rollback(
    *,
    integrity_failure: bool,
    consecutive_registered_degradation_windows: int,
    required_windows: int = 2,
) -> tuple[bool, str]:
    if integrity_failure:
        return True, "IMMEDIATE_INTEGRITY_ROLLBACK"
    if consecutive_registered_degradation_windows >= required_windows:
        return True, "MULTI_SLATE_STATISTICAL_ROLLBACK"
    return False, "RETAIN_DEPLOYED_MODEL"
