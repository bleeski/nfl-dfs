from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

import numpy as np

from .contracts import EvidenceRecord, EvidenceState, Lineup, SlateContract
from .portfolio import objective_standard_error


@dataclass(frozen=True)
class QAFinding:
    code: str
    severity: str
    trigger_value: float | str
    threshold: float | str
    message: str
    blocking: bool


@dataclass(frozen=True)
class RepairDecision:
    accepted: bool
    reasons: tuple[str, ...]


def audit_selected_portfolio(
    *,
    slate: SlateContract,
    lineups: Iterable[Lineup],
    evidence: Iterable[EvidenceRecord],
    exposure_envelopes: Mapping[str, tuple[float, float]] | None = None,
    pair_dependence: Mapping[tuple[str, str], float] | None = None,
    negative_dependence_floor: float = -0.20,
    duplicate_p95: Mapping[str, float] | None = None,
    divided_payout_p95: Mapping[str, float] | None = None,
    entry_fee: float = 0.0,
    salary_left_field_range: tuple[float, float] | None = None,
    robust_supported_keys: Iterable[str] = (),
    sensitivity_changed: bool = False,
    solver_gap: float | None = None,
    solver_gap_required: bool = True,
    maximum_solver_gap: float = 0.01,
    final_byte_match: bool | None = None,
) -> tuple[QAFinding, ...]:
    selected = tuple(lineups)
    findings: list[QAFinding] = []
    by_id = {player.dk_id: player for player in slate.players}
    for lineup in selected:
        players = [by_id[dk_id] for dk_id in lineup.roster]
        defenses = [player for player in players if player.position == "DST"]
        for defense in defenses:
            conflicts = [
                player.dk_id
                for player in players
                if player.team == defense.opponent and player.position in {"QB", "WR", "TE"}
            ]
            if conflicts:
                findings.append(
                    QAFinding(
                        "DST_OPPOSING_PASS_STACK",
                        "MEDIUM",
                        ",".join(conflicts),
                        "advisory unless enforced by a registered solver policy",
                        f"{defense.dk_id} conflicts with opposing passing pieces",
                        False,
                    )
                )
    for record in evidence:
        current_state = record.state_at()
        if record.hard_gate and current_state not in {
            EvidenceState.PASS,
            EvidenceState.NOT_APPLICABLE,
            EvidenceState.NOT_YET_DUE,
        }:
            findings.append(
                QAFinding(
                    "HARD_EVIDENCE_NOT_PASS",
                    "CRITICAL",
                    current_state.value,
                    EvidenceState.PASS.value,
                    f"{record.subject}.{record.field}: {record.reason}",
                    True,
                )
            )
    exposure_counts: dict[str, int] = {}
    for lineup in selected:
        for dk_id in lineup.roster:
            exposure_counts[dk_id] = exposure_counts.get(dk_id, 0) + 1
    envelope = exposure_envelopes or {}
    for dk_id, count in exposure_counts.items():
        exposure = count / max(len(selected), 1)
        low, high = envelope.get(dk_id, (0.0, 1.0))
        if not low - 1e-9 <= exposure <= high + 1e-9:
            findings.append(
                QAFinding(
                    "EXPOSURE_OUTSIDE_ENVELOPE",
                    "HIGH",
                    exposure,
                    f"[{low},{high}]",
                    f"{dk_id} exposure is outside the registered robust envelope",
                    True,
                )
            )
    dependence = pair_dependence or {}
    for lineup in selected:
        ids = lineup.roster
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                value = dependence.get(tuple(sorted((ids[i], ids[j]))))
                if value is not None and value < negative_dependence_floor:
                    findings.append(
                        QAFinding(
                            "NEGATIVE_DEPENDENCE",
                            "HIGH",
                            value,
                            negative_dependence_floor,
                            f"pair {ids[i]}/{ids[j]} breaches the registered dependence band",
                            True,
                        )
                    )
    duplicate = duplicate_p95 or {}
    divided = divided_payout_p95 or {}
    for lineup in selected:
        if duplicate.get(lineup.canonical_key, 0) > 0 and divided.get(
            lineup.canonical_key, float("inf")
        ) < entry_fee:
            findings.append(
                QAFinding(
                    "DUPLICATION_CHOPS_BELOW_FEE",
                    "HIGH",
                    divided[lineup.canonical_key],
                    entry_fee,
                    "simulated p95 duplicate count chops the payout below entry fee",
                    True,
                )
            )
    if salary_left_field_range:
        minimum, maximum = salary_left_field_range
        supported = set(robust_supported_keys)
        for lineup in selected:
            salary_left = slate.salary_cap - lineup.salary
            if not minimum <= salary_left <= maximum and lineup.canonical_key not in supported:
                findings.append(
                    QAFinding(
                        "SALARY_LEFT_OUTSIDE_FIELD_RANGE",
                        "MEDIUM",
                        salary_left,
                        f"[{minimum},{maximum}]",
                        "salary left lacks robust scenario support",
                        False,
                    )
                )
    if sensitivity_changed:
        findings.append(
            QAFinding(
                "MATERIAL_SENSITIVITY",
                "HIGH",
                "changed",
                "stable",
                "registered ownership or market perturbation materially changed selection",
                True,
            )
        )
    if solver_gap_required and (solver_gap is None or solver_gap > maximum_solver_gap):
        findings.append(
            QAFinding(
                "SOLVER_PROOF_OUTSIDE_LIMIT",
                "HIGH",
                "UNKNOWN" if solver_gap is None else solver_gap,
                maximum_solver_gap,
                "solver proof does not meet the registered gap limit",
                True,
            )
        )
    if final_byte_match is False:
        findings.append(
            QAFinding(
                "FINAL_BYTE_MISMATCH",
                "CRITICAL",
                "mismatch",
                "exact match",
                "final output bytes do not match the certified assignment",
                True,
            )
        )
    return tuple(findings)


def decide_repair(
    *,
    net_payout_delta: np.ndarray,
    elite_probability_delta: float,
    elite_standard_error: float,
    state_net_deltas: Mapping[str, float],
    weakens_safety: bool,
    effective_sample_size: float | None = None,
) -> RepairDecision:
    """Accept a repair only on a paired, per-scenario improvement.

    R07: the pairing here is correct and stays. What changes is the divisor.
    `effective_sample_size` lets a caller that knows its bank contains repeated
    or dependent scenarios say so, instead of dividing by a row count and
    narrowing this interval with duplicates. Omitting it keeps the row count,
    which is the right answer for a bank of distinct scenarios.
    """

    reasons: list[str] = []
    delta = np.asarray(net_payout_delta, dtype=float)
    effective = (
        float(len(delta)) if effective_sample_size is None else effective_sample_size
    )
    if len(delta) < 2 or effective < 2:
        # `objective_standard_error` returns 0.0 at or below one effective
        # observation, which would make any positive mean look certain. One
        # effective observation is not a sample.
        reasons.append("paired sample is too small")
    else:
        lower = float(delta.mean() - 1.96 * objective_standard_error(delta, effective))
        if lower <= 0:
            reasons.append("paired 95% confidence interval is not above zero")
    if elite_probability_delta < -elite_standard_error:
        reasons.append("elite-finish probability deteriorates by more than one standard error")
    if any(value <= 0 for value in state_net_deltas.values()):
        reasons.append("repair is not directionally positive in every field state")
    if weakens_safety:
        reasons.append("repair weakens evidence, legality, or deadline safety")
    return RepairDecision(not reasons, tuple(reasons))


def referee_blocks(
    *,
    select_net_delta: float,
    referee_net_delta: float,
    uncertainty: float,
    safety_failure: bool,
    hard_constraint_failure: bool,
) -> tuple[bool, str]:
    if safety_failure or hard_constraint_failure:
        return True, "REFEREE_SAFETY_OR_HARD_CONSTRAINT_FAILURE"
    if abs(referee_net_delta) > uncertainty and np.sign(select_net_delta) != np.sign(
        referee_net_delta
    ):
        return True, "REFEREE_SIGN_DISAGREEMENT"
    return False, "REFEREE_WITHIN_REGISTERED_UNCERTAINTY"


def run_three_pass_audit(initial_findings, repair_once):
    """Run at most three registered QA passes; repeated findings stop the loop."""
    history: list[tuple[QAFinding, ...]] = []
    findings = tuple(initial_findings())
    seen_codes: set[tuple[str, ...]] = set()
    for pass_number in range(1, 4):
        history.append(findings)
        material = tuple(finding for finding in findings if finding.blocking)
        if not material:
            break
        signature = tuple(sorted(finding.code for finding in material))
        if signature in seen_codes:
            break
        seen_codes.add(signature)
        if pass_number == 3 or not repair_once(material):
            break
        findings = tuple(initial_findings())
    return tuple(history)
