from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import time
import traceback
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Mapping

import numpy as np

from .baseline import DEFAULT_BUDGET_SECONDS, DEFAULT_PER_SOLVE_SECONDS, run_baseline
from .baseline import OBJECTIVE_VERSION as BASELINE_OBJECTIVE_VERSION
from .baseline import OUTPUT_CONTRACT as BASELINE_OUTPUT_CONTRACT
from .baseline import BaselineOutcome, audit_baseline_bytes
from .baseline import summary as baseline_summary
from .certification import certify_upload
from .classic_review import ClassicReviewError
from .classic_portfolio_policy import (
    validate_classic_portfolio_policy_file,
    write_classic_portfolio_policy_validation,
    write_normalized_classic_portfolio_policy,
)
from .preflight import historical_artifact_integrity, live_pre_upload_check
from .candidate_families import coverage_report
from .contracts import (
    CertificationBasis,
    ContestObjective,
    DeliveryLimitation,
    DeliveryState,
    EngineMode,
    GateClass,
    EvidenceRecord,
    EvidenceState,
    Lineup,
    ModelStatus,
    ReleaseDecision,
    ReleaseEvidenceState,
    ReleaseTruthsV2,
)
from .deadline import (
    PROBE_MINIMUM_SECONDS,
    PROBE_SHARE,
    Budget,
    activated,
    bank_rate_observation,
    record_candidate_rate,
    runtime_stop_minutes,
)
from .cowork import (
    CoworkRunRequest,
    LIST_MERGE_REQUEST_FIELDS,
    OPERATOR_WEATHER_STATES,
    PATH_FIELDS,
    SUPPORTED_PROFILES,
    confine_request_path,
    request_version_for,
    gating_blockers,
    prior_review_next_inputs,
    required_next_inputs,
    resolve_request_inputs,
)
from .dk import (
    EntryTemplate,
    parse_entries,
    parse_salaries,
    reconcile_template,
    require_single_contest,
    single_contest_problems,
)
from .delivery import (
    POINTER_NAME,
    Deliverable,
    DeliveryPointerError,
    LatestDeliverable,
    blocker_limitations,
    discrepancy_limitations,
    publish as publish_deliverable,
    read_latest as read_latest_deliverable,
    replace as replace_deliverable,
    withholds,
)
from .economics import evaluate_candidates_against_field
from .evidence import EvidenceError, parse_official_inactive_snapshot, source_ledger_evidence
from .field import generate_opponent_field, scale_field_multiplicities
from .hashing import content_hash, sha256_bytes, sha256_file
from .late_swap import LateSwapRunError, govern_late_swap
from .learning import evaluate_challenger, should_rollback
from .lineups import read_assignment_csv, validate_lineup, write_upload_bytes
from .metric_registry import (
    load_metric_registry,
    require_registry_precedes_evaluation,
)
from .opportunity import load_opportunity_model
from .optimizer import LIMIT_INCUMBENT_STATUS, generate_candidates
from .ownership import OwnershipBracket, cold_start_states
from .payouts import parse_payout_csv, validate_payout_tiers
from .portfolio import (
    evaluate_portfolio,
    select_portfolio,
    unpaired_difference_standard_error,
)
from .portfolio_policy import (
    validate_portfolio_policy_file,
    write_normalized_portfolio_policy,
    write_portfolio_policy_validation,
)
from .projection import SOURCES_DIRNAME as PROJECTION_SOURCES_DIRNAME
from .projection import build_projection_package
from .prior_review import PROFILE_VERSION as PRIOR_REVIEW_PROFILE_VERSION
from .prior_review import run_prior_review, team_projections_csv_version
from .readable_review import (
    ReadableReviewArtifacts,
    ReadableReviewError,
    create_readable_review,
    verify_readable_review_artifacts,
)
from .priors import freeze_prior_package, propose_prior_package
from .participation import (
    ParticipationError,
    build_participation_contract,
    redistribute_opportunity,
)
from .prior_score import read_team_splits
from .review_export import export_review_entries, write_assignments_csv, write_run_record
from .selection import assignments_for_entries, select_prior_lineups
from .qa import QAFinding, audit_selected_portfolio, referee_blocks, run_three_pass_audit
from .gate_registry import GateRegistry, load_gate_registry
from .release import derive_delivery_state, derive_release_policy, release_truths_v2
from .scenario_store import save_scenario_bank
from .settlement import (
    capture_settlement_bundle,
    parse_standings,
    replay_settlement_package,
    require_entry_coverage,
)
from .simulation import lineup_score_matrix, simulate_factor_bank
from .system import doctor, live_memory_limit, workbook_is_closed
from .workbook import (
    WorkbookLockedError,
    create_cowork_status_workbook,
    create_operator_input_workbook,
    create_review_workbook,
    populate_operator_run_control,
    read_operator_input,
    timestamped_review_path,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STAGED_WORKBOOK = PROJECT_ROOT / "operator_input.xlsx"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs"
DEFAULT_RUNS_DIR = PROJECT_ROOT / "data" / "runs"
RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")


def _print_json(value: object) -> None:
    print(json.dumps(value, indent=2, sort_keys=True, default=str))


SESSION_PROBE_SCRIPT = PROJECT_ROOT / "scripts" / "session_probe.py"
SESSION_PROBE_SKIP_ENV = "NFL_DFS_SKIP_SESSION_PROBE"
SESSION_PROBE_TIMEOUT_SECONDS = 45


def _session_probe(
    salaries: str | Path | None, *, timeout: float = SESSION_PROBE_TIMEOUT_SECONDS
) -> dict[str, object] | None:
    """Report which evidence gates this session can reach, before the run works.

    `scripts/session_probe.py` has existed since 2026-09-20 and answered the
    question in three seconds. It only ever ran when somebody remembered it, and
    on 2026-09-20 two slates were lost walking into a refused `api.weather.gov`
    instead. This runs it at the head of every `run-slate`, writes the report
    into the run folder, and says the verdict out loud.

    It never blocks and never raises. A blocked host is a routing decision for
    the operator, and the Classic fallback path exists precisely so that a
    session which cannot certify can still build. A probe that cannot run at all
    is reported as such rather than being read as good news.
    """

    if os.environ.get(SESSION_PROBE_SKIP_ENV) == "1":
        return None
    if not SESSION_PROBE_SCRIPT.is_file():
        return {"verdict": "PROBE_UNAVAILABLE", "detail": "script missing"}
    command = [sys.executable, str(SESSION_PROBE_SCRIPT), "--json"]
    if salaries:
        command += ["--salaries", str(salaries)]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        report = json.loads(completed.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        return {"verdict": "PROBE_UNAVAILABLE", "detail": f"{type(exc).__name__}:{exc}"}
    if not isinstance(report, dict):
        return {"verdict": "PROBE_UNAVAILABLE", "detail": "report was not an object"}
    return report


def _announce_session_probe(report: Mapping[str, object] | None) -> None:
    """Put the verdict where an operator reading a terminal will see it."""

    if not report:
        return
    verdict = str(report.get("verdict") or "UNKNOWN")
    if verdict == "CAN_COMPLETE_A_RUN":
        return
    blocking = report.get("blocking_hosts")
    names = (
        ", ".join(
            f"{item.get('host')} ({item.get('gate')})"
            for item in blocking
            if isinstance(item, Mapping)
        )
        if isinstance(blocking, list)
        else ""
    )
    print(
        f"session probe: {verdict}" + (f" -- blocked: {names}" if names else ""),
        file=sys.stderr,
    )


def _blocked_truth_values(
    *,
    file_valid: bool = False,
    evidence_state: ReleaseEvidenceState = ReleaseEvidenceState.UNKNOWN,
    model_status: ModelStatus = ModelStatus.UNVALIDATED,
    certification_basis: CertificationBasis = CertificationBasis.MANUAL_GUARDRAIL,
) -> dict[str, bool | str]:
    values = derive_release_policy(
        file_valid=file_valid,
        evidence_state=evidence_state,
        model_status=model_status,
        certification_basis=certification_basis,
    ).truth_values()
    values["certification_basis"] = certification_basis.value
    return values


def _load_config(name: str) -> dict[str, object]:
    path = PROJECT_ROOT / "config" / name
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{name} must contain a JSON object")
    return value


def _validate_scoring_config(slate) -> None:
    config = _load_config("scoring.json")
    expected = {
        "schema_version": slate.scoring_version,
        "salary_cap": slate.salary_cap,
        "captain_salary_multiplier": 1.5,
        "captain_scoring_multiplier": 1.5,
    }
    for key, value in expected.items():
        if config.get(key) != value:
            raise ValueError(
                f"scoring.json {key}={config.get(key)!r} conflicts with runtime {value!r}"
            )


def _certification_policy(slate, manual_guardrail: bool) -> tuple[tuple[str, ...], float]:
    evidence = _load_config("evidence_policy.json")
    hard_fields = evidence.get("hard_fields")
    model_fields = evidence.get("model_assisted_hard_fields", [])
    if not isinstance(hard_fields, list) or not all(
        isinstance(value, str) for value in hard_fields
    ):
        raise ValueError("evidence_policy.json hard_fields must be a string list")
    if not isinstance(model_fields, list) or not all(
        isinstance(value, str) for value in model_fields
    ):
        raise ValueError(
            "evidence_policy.json model_assisted_hard_fields must be a string list"
        )
    baseline_minimum = {
        "salary_pool",
        "entry_authorization",
        "payout_contract",
        "official_inactive_status",
        "weather_if_required",
        "market_line",
        "final_bytes",
    }
    model_minimum = {
        "player_opportunity_evidence",
        "quantitative_qa",
        "referee_review",
    }
    if not baseline_minimum.issubset(hard_fields):
        raise ValueError("evidence policy cannot remove baseline hard fields")
    if not model_minimum.issubset(model_fields):
        raise ValueError("evidence policy cannot remove model-assisted hard fields")
    required = [value for value in hard_fields if value != "final_bytes"]
    if not manual_guardrail:
        required.extend(model_fields)
    if len(set(required)) != len(required):
        raise ValueError("evidence policy contains duplicate hard fields")
    runtime = _load_config("runtime.json")
    runtime_key = "showdown" if slate.mode is EngineMode.SHOWDOWN else "classic"
    profile = runtime.get(runtime_key)
    if not isinstance(profile, dict):
        raise ValueError(f"runtime.json {runtime_key} profile is missing")
    deadline = profile.get("certification_seconds")
    if (
        isinstance(deadline, bool)
        or not isinstance(deadline, (int, float))
        or not np.isfinite(deadline)
        or not 0 < deadline <= 120
    ):
        raise ValueError("runtime.json certification_seconds must be in (0,120]")
    return tuple(required), float(deadline)


def _runtime_scenario_defaults(slate) -> tuple[int, int, int]:
    runtime = _load_config("runtime.json")
    key = "showdown" if slate.mode is EngineMode.SHOWDOWN else "classic"
    profile = runtime.get(key)
    if not isinstance(profile, dict):
        raise ValueError(f"runtime.json {key} profile is missing")
    values = tuple(
        profile.get(name)
        for name in ("design_scenarios", "select_scenarios", "referee_scenarios")
    )
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 1 for value in values):
        raise ValueError(f"runtime.json {key} scenario counts must be positive integers")
    return values


def _run_id(label: str = "run") -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    cleaned = "".join(character if character.isalnum() or character in "-_" else "-" for character in label)
    return f"{stamp}-{cleaned[:40] or 'run'}"


def _resolved_run_id(value: str | None, label: str) -> str:
    run_id = value or _run_id(label)
    if not RUN_ID_PATTERN.fullmatch(run_id):
        raise ValueError(
            "run_id must be 1-80 ASCII letters, digits, hyphens, or underscores "
            "and must begin with a letter or digit"
        )
    return run_id


def _snapshot_filename(path: str | Path, digest: str) -> str:
    """Keep full content identity without inheriting unsafe attachment-name length."""
    suffix = Path(path).suffix.lower()
    if len(suffix) > 10 or any(not (character.isalnum() or character == ".") for character in suffix):
        suffix = ""
    return f"{digest}{suffix}"


def _snapshot_inputs(
    run_id: str,
    paths: Iterable[str | Path],
    *,
    allowed_roots: Iterable[str | Path] | None = None,
    allowed_files: Iterable[str | Path] = (),
) -> dict[str, str]:
    input_dir = DEFAULT_RUNS_DIR / run_id / "inputs"
    if input_dir.exists():
        raise ValueError(
            f"run_id already exists and immutable snapshots will not be overwritten: {run_id}"
        )
    input_dir.mkdir(parents=True, exist_ok=False)
    hashes: dict[str, str] = {}
    for path_value in dict.fromkeys(str(Path(path).resolve()) for path in paths):
        source = (
            confine_request_path(
                path_value,
                allowed_roots=allowed_roots,
                allowed_files=allowed_files,
                field_name="snapshot input",
            )
            if allowed_roots is not None
            else Path(path_value).resolve()
        )
        if not source.is_file():
            raise FileNotFoundError(source)
        digest = sha256_file(source)
        target = input_dir / _snapshot_filename(source, digest)
        shutil.copyfile(source, target)
        if sha256_file(target) != digest:
            raise RuntimeError(f"snapshot hash mismatch for {source}")
        hashes[str(source)] = digest
        _snapshot_archived_sources(source, input_dir)
    return hashes


def _snapshot_archived_sources(source: Path, input_dir: Path) -> None:
    """Bring a projection package's archived sources along with its ledger.

    R08: a snapshot used to copy the ledger file on its own, which worked only
    because the entries pointed at absolute originals. A versioned ledger
    addresses its archived sources by package-relative path, so the snapshot
    has to carry that subtree or the copy resolves to nothing. Hashes are
    re-verified on arrival, and an archive that is already present is left
    alone rather than overwritten, because snapshots are immutable.
    """

    archive = source.parent / PROJECTION_SOURCES_DIRNAME
    if source.suffix.lower() != ".json" or not archive.is_dir():
        return
    destination = input_dir / PROJECTION_SOURCES_DIRNAME
    destination.mkdir(parents=True, exist_ok=True)
    for archived in sorted(archive.iterdir()):
        if not archived.is_file():
            continue
        copy = destination / archived.name
        if copy.exists():
            continue
        digest = sha256_file(archived)
        shutil.copyfile(archived, copy)
        if sha256_file(copy) != digest:
            raise RuntimeError(f"snapshot hash mismatch for {archived}")


def _snapshot_path(run_id: str, source: str | Path, digest: str) -> Path:
    return DEFAULT_RUNS_DIR / run_id / "inputs" / _snapshot_filename(source, digest)


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    temporary.replace(path)


def _write_staged_csv(path: Path, header: tuple[str, ...], rows: Iterable[tuple[object, ...]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\r\n")
        writer.writerow(header)
        writer.writerows(rows)
    return path


def _base_evidence(
    *,
    slate_hash: str,
    entries_hash: str,
    payout_path: str | Path,
    payout_hash: str | None = None,
    manual_guardrail: bool,
    model_input_hash: str | None,
    model=None,
    source_ledger_validated: bool = False,
    market_freshness_window: timedelta = timedelta(hours=6),
) -> list[EvidenceRecord]:
    now = datetime.now(timezone.utc)
    market_observed_at: datetime | None = None
    market_expires_at: datetime | None = None
    model_state = EvidenceState.NOT_APPLICABLE if manual_guardrail else EvidenceState.UNKNOWN
    weather_record_state = model_state
    market_reason = "manual legality guardrail makes no projection or market claim"
    weather_reason = "manual legality guardrail makes no model or weather claim"
    market_value = None
    weather_value = None
    if not manual_guardrail and model is not None and model_input_hash:
        observations = [
            datetime.fromisoformat(team.market_observed_at.replace("Z", "+00:00"))
            for team in model.teams
        ]
        market_observed_at = min(observations)
        market_expires_at = market_observed_at + market_freshness_window
        if any(observed > now + timedelta(minutes=5) for observed in observations):
            model_state = EvidenceState.CONFLICTED
            reason_prefix = "market/weather observations include a future timestamp"
        elif now > market_expires_at:
            model_state = EvidenceState.STALE
            reason_prefix = "market/weather observations exceed the registered freshness window"
        else:
            model_state = EvidenceState.PASS
            reason_prefix = "bounded timestamped model inputs passed deterministic validation"
        market_value = {
            team.team: {
                "total": team.market_total,
                "spread": team.market_spread,
                "observed_at": team.market_observed_at,
            }
            for team in model.teams
        }
        weather_value = {team.team: team.weather_state for team in model.teams}
        ledger_reason = (
            "strict source ledger contract and derived hashes validated"
            if source_ledger_validated
            else "source ledger is missing or invalid"
        )
        market_reason = f"{reason_prefix}; {ledger_reason}"
        weather_reason = f"{reason_prefix}; weather states use model inputs whose {ledger_reason}"
        # A game nobody observed (Session 09) is never weather evidence.
        weather_record_state = model_state
        unobserved = sorted(team for team, state in weather_value.items() if state == "UNOBSERVED")
        if unobserved and weather_record_state is EvidenceState.PASS:
            weather_record_state = EvidenceState.UNKNOWN
            weather_reason = f"weather was not observed for {', '.join(unobserved)} (UNOBSERVED)"
    return [
        EvidenceRecord(
            subject="slate",
            field="salary_pool",
            value=slate_hash,
            source_artifact_id=slate_hash,
            observed_at=now,
            hard_gate=True,
            state=EvidenceState.PASS,
            reason="strict salary parser and roster-contract validation passed",
        ),
        EvidenceRecord(
            subject="entries",
            field="entry_authorization",
            value=entries_hash,
            source_artifact_id=entries_hash,
            observed_at=now,
            hard_gate=True,
            state=EvidenceState.PASS,
            reason="exact Entry IDs and template geometry reconciled",
        ),
        EvidenceRecord(
            subject="contest",
            field="payout_contract",
            value=payout_hash or sha256_file(payout_path),
            source_artifact_id=payout_hash or sha256_file(payout_path),
            observed_at=now,
            hard_gate=True,
            state=EvidenceState.PASS,
            reason="payout ranks, monotonicity, and advertised value reconciled",
        ),
        EvidenceRecord(
            subject="slate",
            field="weather_if_required",
            value=weather_value,
            source_artifact_id=model_input_hash if not manual_guardrail else None,
            observed_at=market_observed_at,
            expires_at=market_expires_at,
            hard_gate=True,
            state=weather_record_state,
            reason=weather_reason,
        ),
        EvidenceRecord(
            subject="slate",
            field="market_line",
            value=market_value,
            source_artifact_id=model_input_hash if not manual_guardrail else None,
            observed_at=market_observed_at,
            expires_at=market_expires_at,
            hard_gate=True,
            state=model_state,
            reason=market_reason,
        ),
    ]


def _official_status_evidence(
    *,
    status_path: str | Path | None,
    slate,
    assignments: Mapping[str, tuple[str, ...]],
    now: datetime | None = None,
    freshness_window: timedelta = timedelta(hours=3),
) -> EvidenceRecord:
    when = now or datetime.now(timezone.utc)
    selected = {dk_id for roster in assignments.values() for dk_id in roster}
    if not status_path:
        return EvidenceRecord(
            subject="selected_portfolio",
            field="official_inactive_status",
            hard_gate=True,
            state=EvidenceState.UNKNOWN,
            reason="official exact-ID activity evidence was not supplied",
        )
    digest = sha256_file(status_path)
    snapshot = parse_official_inactive_snapshot(status_path, slate.players)
    statuses = snapshot.statuses
    problems = list(snapshot.problems)
    if sha256_file(status_path) != digest:
        problems.append("official status CSV changed while it was being validated")
    missing = sorted(selected.difference(statuses))
    selected_inactive = sorted(dk_id for dk_id in selected if statuses.get(dk_id) == "INACTIVE")
    observations = [snapshot.observed_at_by_id[dk_id] for dk_id in selected if dk_id in snapshot.observed_at_by_id]
    oldest_observation = min(observations) if observations else None
    expires_at = oldest_observation + freshness_window if oldest_observation else None
    future_ids = sorted(
        dk_id
        for dk_id in selected
        if dk_id in snapshot.observed_at_by_id
        and snapshot.observed_at_by_id[dk_id] > when + timedelta(minutes=5)
    )
    by_id = {player.dk_id: player for player in slate.players}
    earliest_selected_lock = min(
        (by_id[dk_id].lock_at for dk_id in selected if dk_id in by_id),
        default=None,
    )
    locked_ids = sorted(
        dk_id for dk_id in selected if dk_id in by_id and by_id[dk_id].lock_at <= when
    )
    post_lock_observations = sorted(
        dk_id
        for dk_id in selected
        if dk_id in by_id
        and dk_id in snapshot.observed_at_by_id
        and snapshot.observed_at_by_id[dk_id] > by_id[dk_id].lock_at
    )
    lock_window_start = (
        earliest_selected_lock - freshness_window if earliest_selected_lock else None
    )
    stale = bool(
        oldest_observation
        and (
            when > oldest_observation + freshness_window
            or (lock_window_start is not None and oldest_observation < lock_window_start)
        )
    )
    if problems:
        state = EvidenceState.CONFLICTED
        reason = "; ".join(problems)
    elif future_ids:
        state = EvidenceState.CONFLICTED
        reason = f"official status observations are in the future: {future_ids}"
    elif selected_inactive:
        state = EvidenceState.FAIL
        reason = f"selected players are officially inactive: {selected_inactive}"
    elif missing:
        state = EvidenceState.UNKNOWN
        reason = f"selected exact IDs lack current activity evidence: {missing}"
    elif locked_ids:
        state = EvidenceState.FAIL
        reason = f"selected players have already locked: {locked_ids}"
    elif post_lock_observations:
        state = EvidenceState.CONFLICTED
        reason = (
            "official status observations occur after player lock: "
            f"{post_lock_observations}"
        )
    elif stale:
        state = EvidenceState.STALE
        reason = (
            "official exact-ID activity evidence falls outside the registered "
            f"{freshness_window.total_seconds() / 3600:g}-hour lock window"
        )
    else:
        state = EvidenceState.PASS
        reason = "every selected exact DK ID has current operator-attested ACTIVE provenance"
    asserted_sources = sorted({
        snapshot.source_url_by_id[dk_id] for dk_id in selected
        if dk_id in snapshot.source_url_by_id
    })
    if len(asserted_sources) > 1:
        reason += "; asserted source URLs: " + ", ".join(asserted_sources)
    return EvidenceRecord(
        subject="selected_portfolio",
        field="official_inactive_status",
        value={dk_id: statuses.get(dk_id) for dk_id in sorted(selected)},
        source_artifact_id=digest,
        source_url=asserted_sources[0] if len(asserted_sources) == 1 else None,
        observed_at=oldest_observation,
        expires_at=expires_at,
        hard_gate=True,
        state=state,
        reason=reason,
    )


def _selected_opportunity_evidence(
    *,
    model,
    slate,
    assignments: Mapping[str, tuple[str, ...]],
    source_artifact_id: str,
) -> EvidenceRecord:
    by_dk_id = {player.dk_id: player for player in slate.players}
    by_person = {player.underlying_id: player for player in model.players}
    selected_ids = {
        dk_id for roster in assignments.values() for dk_id in roster if dk_id in by_dk_id
    }
    selected_people = {by_dk_id[dk_id].underlying_id for dk_id in selected_ids}
    required_people = {player.underlying_id for player in slate.players}
    states = {
        person: by_person[person].evidence_state
        for person in sorted(required_people)
        if person in by_person
    }
    missing_selected = sorted(selected_people.difference(states))
    non_pass_selected = {
        person: states[person]
        for person in sorted(selected_people.intersection(states))
        if states[person] != "PASS"
    }
    unselected_people = required_people.difference(selected_people)
    prior_only_pool = sorted(
        person for person in unselected_people if states.get(person) != "PASS"
    )
    if missing_selected:
        state = EvidenceState.UNKNOWN
        reason = (
            "selected players are absent from the opportunity evidence: "
            f"{missing_selected}"
        )
    elif any(value == "CONFLICTED" for value in non_pass_selected.values()):
        state = EvidenceState.CONFLICTED
        reason = f"selected opportunity evidence is conflicted: {non_pass_selected}"
    elif any(value == "STALE" for value in non_pass_selected.values()):
        state = EvidenceState.STALE
        reason = f"selected opportunity evidence is stale: {non_pass_selected}"
    elif non_pass_selected:
        state = EvidenceState.UNKNOWN
        reason = f"selected opportunity evidence is unknown: {non_pass_selected}"
    else:
        state = EvidenceState.PASS
        reason = (
            "every selected player has PASS opportunity evidence; "
            f"{len(prior_only_pool)} unselected salary-pool players remain prior-only"
        )
    return EvidenceRecord(
        subject="selected_portfolio",
        field="player_opportunity_evidence",
        value={
            "selected_dk_ids": sorted(selected_ids),
            "selected_people": sorted(selected_people),
            "selected_states_by_person": {
                person: states.get(person, "MISSING") for person in sorted(selected_people)
            },
            "prior_only_unselected_pool_count": len(prior_only_pool),
            "prior_only_unselected_people": prior_only_pool,
            "salary_pool_people_count": len(required_people),
        },
        source_artifact_id=source_artifact_id,
        observed_at=datetime.now(timezone.utc),
        hard_gate=True,
        state=state,
        reason=reason,
    )


def _validated_lineups(slate, assignments: Mapping[str, tuple[str, ...]]) -> dict[str, Lineup]:
    lineups: dict[str, Lineup] = {}
    for entry_id, roster in assignments.items():
        result = validate_lineup(slate, roster)
        if result.valid and result.lineup:
            lineups[entry_id] = result.lineup
    return lineups


def command_doctor(args: argparse.Namespace) -> int:
    report = doctor(args.workspace)
    _print_json(json.loads(report.to_json()))
    return 0 if report.pass_status else 2


def command_setup(args: argparse.Namespace) -> int:
    report = doctor(PROJECT_ROOT)
    if not report.pass_status:
        _print_json(
            {
                "status": "DO_NOT_UPLOAD",
                **_blocked_truth_values(),
                "message": (
                    "Environment doctor failed. Use the pinned Python 3.13.7 runtime, "
                    "ensure memory and SQLite checks pass, and close operator_input.xlsx."
                ),
                "doctor": json.loads(report.to_json()),
            }
        )
        return 2
    workbook = create_operator_input_workbook(args.workbook)
    bootstrap = DEFAULT_OUTPUT_DIR / "bootstrap" / "operator_input.xlsx"
    bootstrap.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(workbook, bootstrap)
    _print_json(
        {
            "status": "SETUP_COMPLETE",
            "operator_workbook": str(workbook),
            "bootstrap_copy": str(bootstrap),
            "doctor": json.loads(report.to_json()),
            "next": (
                ".\\nfl.ps1 run"
                if os.name == "nt"
                else "sh ./nfl.sh cowork-run --input-dir '<attachment-directory>'"
            ),
        }
    )
    return 0


def command_workbook(args: argparse.Namespace) -> int:
    try:
        path = create_operator_input_workbook(args.output)
    except WorkbookLockedError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(f"Created staged operator workbook: {path}")
    return 0


def _intake(
    *,
    salaries: str | Path,
    entries_path: str | Path,
    run_id: str,
    snapshot_paths: Iterable[str | Path] | None = None,
    snapshot_allowed_roots: Iterable[str | Path] | None = None,
    snapshot_allowed_files: Iterable[str | Path] = (),
) -> tuple[dict[str, object], object, EntryTemplate]:
    slate = parse_salaries(salaries)
    entries = parse_entries(entries_path)
    reconcile_template(entries, slate)
    contest_problems = single_contest_problems(entries)
    hashes = _snapshot_inputs(
        run_id,
        snapshot_paths or [salaries, entries_path],
        allowed_roots=snapshot_allowed_roots,
        allowed_files=snapshot_allowed_files,
    )
    summary = {
        "run_id": run_id,
        "state": "DO_NOT_UPLOAD" if contest_problems else "RECONCILED",
        **_blocked_truth_values(),
        "mode": slate.mode.value,
        "salary_players": len(slate.players),
        "underlying_people": len({player.underlying_id for player in slate.players}),
        "teams": len({player.team for player in slate.players}),
        "games": len(slate.games),
        "authorized_entries": len(entries.authorizations),
        "contest_consistency": "PASS" if not contest_problems else "FAIL",
        "contest_problems": contest_problems,
        "hashes": hashes,
        "next": "Supply payouts, exact-ID official statuses, and assignments or model inputs.",
    }
    _write_json(DEFAULT_RUNS_DIR / run_id / "intake.json", summary)
    return summary, slate, entries


def command_intake(args: argparse.Namespace) -> int:
    run_id = _resolved_run_id(args.run_id, args.label)
    summary, _, _ = _intake(
        salaries=args.salaries,
        entries_path=args.entries,
        run_id=run_id,
    )
    _print_json(summary)
    return 0 if not summary["contest_problems"] else 2


def command_validate(args: argparse.Namespace) -> int:
    slate = parse_salaries(args.salaries)
    template = parse_entries(args.entries)
    reconcile_template(template, slate)
    assignment_digest = sha256_file(args.assignments)
    assignments = read_assignment_csv(args.assignments, slate.mode)
    if sha256_file(args.assignments) != assignment_digest:
        raise RuntimeError("assignment CSV changed while it was being validated")
    authorized = {entry.entry_id for entry in template.authorizations}
    problems: list[str] = list(single_contest_problems(template))
    if set(assignments) != authorized:
        problems.append("assignment Entry IDs do not exactly match reserved entries")
    for entry_id, roster in assignments.items():
        result = validate_lineup(slate, roster)
        problems.extend(f"{entry_id}: {problem}" for problem in result.errors)
    _print_json(
        {
            "status": "PASS" if not problems else "FAIL",
            **_blocked_truth_values(file_valid=False),
            "mode": slate.mode.value,
            "authorized_entries": len(authorized),
            "problems": problems,
        }
    )
    return 0 if not problems else 2


def _certify(args: argparse.Namespace) -> tuple[int, object]:
    run_id = _resolved_run_id(args.run_id, args.label)
    slate = parse_salaries(args.salaries)
    _validate_scoring_config(slate)
    required_hard_fields, certification_deadline = _certification_policy(
        slate, args.manual_guardrail
    )
    template = parse_entries(args.entries)
    reconcile_template(template, slate)
    assignment_digest = sha256_file(args.assignments)
    assignments = read_assignment_csv(args.assignments, slate.mode)
    if sha256_file(args.assignments) != assignment_digest:
        raise RuntimeError("assignment CSV changed while it was being validated")
    field_size = getattr(args, "field_size", None)
    if field_size is None:
        raise ValueError("field size is required for certification")
    objective = ContestObjective(getattr(args, "objective", ContestObjective.LARGE_GPP.value))
    payout_digest = sha256_file(args.payouts)
    tiers = parse_payout_csv(
        args.payouts, ticket_face_value=getattr(args, "ticket_face_value", None)
    )
    validate_payout_tiers(
        tiers,
        advertised_value=args.advertised_prize_value,
        ticket_face_value=args.ticket_face_value,
        field_size=field_size,
        reserved_entry_count=len(template.authorizations),
    )
    if sha256_file(args.payouts) != payout_digest:
        raise RuntimeError("payout CSV changed while it was being validated")
    model_paths = {
        "team_projection_input": getattr(args, "team_projections", None),
        "player_opportunity_input": getattr(args, "player_opportunities", None),
        "source_ledger": getattr(args, "source_ledger", None),
    }
    model_hashes = {
        name: sha256_file(path)
        for name, path in model_paths.items()
        if path
    }
    model_hash = content_hash(model_hashes) if model_hashes else None
    precertification_evidence: list[EvidenceRecord] = []
    precertification_findings: tuple[QAFinding, ...] = ()
    certification_blockers: list[str] = []
    certification_file_blockers: list[str] = []
    solver_proof: Mapping[str, object] = {}
    portfolio_metrics: Mapping[str, float | str] | None = None
    build_report_value = getattr(args, "build_report", None)
    certification_model = None
    source_ledger_validated = False
    certification_basis = (
        CertificationBasis.MANUAL_GUARDRAIL
        if args.manual_guardrail
        else CertificationBasis.MODEL_ASSISTED
    )
    model_status = ModelStatus.UNVALIDATED
    if not args.manual_guardrail:
        if not getattr(args, "team_projections", None) or not getattr(
            args, "player_opportunities", None
        ):
            certification_blockers.append("MODEL_INPUTS_REQUIRED_FOR_CERTIFICATION")
        else:
            certification_model = load_opportunity_model(
                slate,
                args.team_projections,
                args.player_opportunities,
            )
            model_status = ModelStatus.PRIOR_ONLY
            for name in ("team_projection_input", "player_opportunity_input"):
                path = model_paths[name]
                if path and sha256_file(path) != model_hashes[name]:
                    certification_blockers.append(
                        f"{name.upper()}_CHANGED_DURING_VALIDATION"
                    )
        if not getattr(args, "source_ledger", None):
            certification_blockers.append("SOURCE_LEDGER_REQUIRED_FOR_CERTIFICATION")
        elif model_hashes.get("team_projection_input") and model_hashes.get(
            "player_opportunity_input"
        ):
            # Certification runs at the live release clock, which is what makes
            # this the boundary where a package's real expiry bites. R08: the
            # record carries the earliest source expiry, so `evaluate_hard_gates`
            # re-derives STALE at final release without reopening a source, and
            # a legacy ledger shape that cannot express an expiry cannot clear
            # the gate at all.
            expected_model_outputs = {
                "team_projections": model_hashes["team_projection_input"],
                "player_opportunities": model_hashes["player_opportunity_input"],
            }
            ledger_record = source_ledger_evidence(
                args.source_ledger, expected_outputs=expected_model_outputs
            )
            precertification_evidence.append(ledger_record)
            if ledger_record.state is EvidenceState.PASS:
                source_ledger_validated = True
            else:
                certification_blockers.append(
                    f"SOURCE_LEDGER_INVALID:{ledger_record.state.value}:{ledger_record.reason}"
                )
    if not args.manual_guardrail:
        if not build_report_value:
            certification_blockers.append("MISSING_BUILD_QA_REPORT")
        else:
            build_report_path = Path(build_report_value).resolve()
            build_digest = sha256_file(build_report_path)
            build_report = json.loads(build_report_path.read_text(encoding="utf-8"))
            if build_report.get("run_id") != run_id:
                certification_blockers.append("BUILD_REPORT_RUN_ID_MISMATCH")
            if build_report.get("assignment_sha256") != assignment_digest:
                certification_blockers.append("BUILD_ASSIGNMENT_HASH_MISMATCH")
            expected_build_hashes = {
                "salary": slate.salary_hash,
                "entries": template.raw_hash,
                "payouts": payout_digest,
                "team_projections": model_hashes.get("team_projection_input"),
                "player_opportunities": model_hashes.get("player_opportunity_input"),
            }
            if build_report.get("input_hashes") != expected_build_hashes:
                certification_blockers.append("BUILD_INPUT_HASH_MISMATCH")
            expected_contest = {
                "field_size": field_size,
                "objective": objective.value,
                "advertised_prize_value": args.advertised_prize_value,
                "ticket_face_value": args.ticket_face_value,
            }
            if build_report.get("contest_parameters") != expected_contest:
                certification_blockers.append("BUILD_CONTEST_PARAMETER_MISMATCH")
            raw_findings = build_report.get("precertification_findings", [])
            if not isinstance(raw_findings, list):
                certification_blockers.append("BUILD_QA_FINDINGS_INVALID")
                raw_findings = []
            try:
                precertification_findings = tuple(
                    QAFinding(
                        code=str(item["code"]),
                        severity=str(item["severity"]),
                        trigger_value=item["trigger_value"],
                        threshold=item["threshold"],
                        message=str(item["message"]),
                        blocking=bool(item["blocking"]),
                    )
                    for item in raw_findings
                )
            except (KeyError, TypeError, ValueError):
                certification_blockers.append("BUILD_QA_FINDINGS_INVALID")
                precertification_findings = ()
            created_raw = build_report.get("created_at")
            try:
                build_observed_at = datetime.fromisoformat(
                    str(created_raw).replace("Z", "+00:00")
                )
                if build_observed_at.tzinfo is None:
                    raise ValueError
            except ValueError:
                build_observed_at = datetime.now(timezone.utc)
                certification_blockers.append("BUILD_REPORT_TIMESTAMP_INVALID")
            quantitative = build_report.get("quantitative_qa", {})
            qa_blocked = bool(quantitative.get("blocked", True))
            parsed_qa_blocked = any(
                finding.blocking and not finding.code.startswith("REFEREE_")
                for finding in precertification_findings
            )
            if qa_blocked != parsed_qa_blocked:
                certification_blockers.append("BUILD_QA_SUMMARY_MISMATCH")
                qa_blocked = True
            referee = build_report.get("referee", {})
            referee_blocked = bool(referee.get("blocked", True))
            parsed_referee_blocked = any(
                finding.blocking and finding.code.startswith("REFEREE_")
                for finding in precertification_findings
            )
            if (
                referee.get("binding") is not True
                or referee_blocked != parsed_referee_blocked
            ):
                certification_blockers.append("BUILD_REFEREE_SUMMARY_MISMATCH")
                referee_blocked = True
            precertification_evidence.extend(
                (
                    EvidenceRecord(
                        subject=run_id,
                        field="quantitative_qa",
                        value=quantitative,
                        source_artifact_id=build_digest,
                        observed_at=build_observed_at,
                        hard_gate=True,
                        state=EvidenceState.FAIL if qa_blocked else EvidenceState.PASS,
                        reason=(
                            "registered quantitative QA has blocking findings"
                            if qa_blocked
                            else "registered quantitative QA completed without blocking findings"
                        ),
                    ),
                    EvidenceRecord(
                        subject=run_id,
                        field="referee_review",
                        value=referee,
                        source_artifact_id=build_digest,
                        observed_at=build_observed_at,
                        hard_gate=True,
                        state=EvidenceState.FAIL if referee_blocked else EvidenceState.PASS,
                        reason=str(referee.get("reason", "REFEREE_REPORT_MISSING")),
                    ),
                )
            )
            solver_value = build_report.get("solver_proof", {})
            if isinstance(solver_value, dict):
                solver_proof = solver_value
            else:
                certification_blockers.append("BUILD_SOLVER_PROOF_INVALID")
            portfolio_value = build_report.get("portfolio")
            if isinstance(portfolio_value, dict):
                portfolio_metrics = portfolio_value
    evidence = _base_evidence(
        slate_hash=slate.salary_hash,
        entries_hash=template.raw_hash,
        payout_path=args.payouts,
        payout_hash=payout_digest,
        manual_guardrail=args.manual_guardrail,
        model_input_hash=model_hash,
        model=certification_model,
        source_ledger_validated=source_ledger_validated,
    )
    evidence.append(
        _official_status_evidence(
            status_path=args.official_statuses,
            slate=slate,
            assignments=assignments,
        )
    )
    if certification_model is not None and model_hashes.get("player_opportunity_input"):
        evidence.append(
            _selected_opportunity_evidence(
                model=certification_model,
                slate=slate,
                assignments=assignments,
                source_artifact_id=model_hashes["player_opportunity_input"],
            )
        )
    evidence.extend(precertification_evidence)
    if sha256_file(args.salaries) != slate.salary_hash:
        certification_file_blockers.append("SALARY_INPUT_CHANGED_DURING_CERTIFICATION")
    if sha256_file(args.entries) != template.raw_hash:
        certification_file_blockers.append("ENTRY_INPUT_CHANGED_DURING_CERTIFICATION")
    if sha256_file(args.assignments) != assignment_digest:
        certification_file_blockers.append("ASSIGNMENT_INPUT_CHANGED_DURING_CERTIFICATION")
    for name, path in model_paths.items():
        if path and sha256_file(path) != model_hashes[name]:
            certification_blockers.append(f"{name.upper()}_CHANGED_DURING_CERTIFICATION")
    output_dir = Path(args.output_dir).resolve() / run_id
    output_csv = output_dir / f"DK_UPLOAD_{run_id}.csv"
    manifest_path = output_dir / f"DK_UPLOAD_{run_id}.manifest.json"
    manifest = certify_upload(
        run_id=run_id,
        slate=slate,
        template=template,
        assignments=assignments,
        evidence=evidence,
        output_path=output_csv,
        manifest_path=manifest_path,
        config_hashes={
            path.name: sha256_file(path)
            for path in (PROJECT_ROOT / "config").glob("*.json")
        },
        model_hashes=model_hashes,
        additional_input_hashes={"assignments": assignment_digest},
        solver_proof=solver_proof,
        model_status=model_status,
        certification_basis=certification_basis,
        additional_file_blockers=certification_file_blockers,
        additional_blockers=certification_blockers,
        deadline_seconds=certification_deadline,
        required_hard_fields=required_hard_fields,
    )
    lineups = _validated_lineups(slate, assignments)
    findings = precertification_findings + tuple(
        QAFinding(
            code=blocker.split(":", 1)[0],
            severity="CRITICAL",
            trigger_value=blocker,
            threshold="PASS",
            message=blocker,
            blocking=True,
        )
        for blocker in manifest.blockers
    )
    staged = Path(args.staged_workbook).resolve()
    if not staged.exists():
        create_operator_input_workbook(staged)
    review = timestamped_review_path(output_dir, run_id)
    create_review_workbook(
        staged_input=staged,
        output_path=review,
        lineups=lineups,
        qa_findings=findings,
        manifest=manifest,
        manifest_path=manifest_path,
        portfolio_metrics=portfolio_metrics,
    )
    result = {
        "run_id": run_id,
        "status": manifest.status,
        "FILE_VALID": manifest.file_valid,
        "EVIDENCE_STATE": manifest.evidence_state.value,
        "MODEL_STATUS": manifest.model_status.value,
        "RELEASE_DECISION": manifest.release_decision.value,
        "certification_basis": manifest.certification_basis.value,
        "upload_csv": manifest.output_path,
        "sha256": manifest.output_sha256,
        "proposed_sha256": manifest.proposed_output_sha256,
        "manifest": str(manifest_path),
        "review_workbook": str(review),
        "blockers": list(manifest.blockers),
        "qa_findings": [_finding_dict(finding) for finding in findings],
        "meaning": (
            "FILE_VALID covers authorized legal bytes only. RELEASE_DECISION is derived "
            "separately from hard evidence, model status, and safety gates; manual guardrail "
            "certification is not a model-performance claim."
        ),
    }
    return (
        0 if manifest.release_decision.value == "CERTIFIED_UPLOAD_PACKAGE" else 2,
        result,
    )


def command_certify(args: argparse.Namespace) -> int:
    try:
        code, result = _certify(args)
    except Exception as exc:
        run_id = _resolved_run_id(args.run_id, args.label)
        output_root = Path(args.output_dir).resolve() / run_id
        upload_path = output_root / f"DK_UPLOAD_{run_id}.csv"
        upload_path.unlink(missing_ok=True)
        diagnostic_path = output_root / "certification_diagnostic.json"
        try:
            _write_json(
                diagnostic_path,
                {
                    "run_id": run_id,
                    "status": "DO_NOT_UPLOAD",
                    **_blocked_truth_values(
                        certification_basis=(
                            CertificationBasis.MANUAL_GUARDRAIL
                            if getattr(args, "manual_guardrail", True)
                            else CertificationBasis.MODEL_ASSISTED
                        )
                    ),
                    "stage": "CERTIFICATION_FAILED",
                    "error": type(exc).__name__,
                    "message": str(exc),
                    "traceback": traceback.format_exc(),
                    "upload_csv": None,
                },
            )
        except OSError:
            pass
        raise
    _print_json(result)
    return code


def _projection_scores(slate, simulations) -> tuple[dict[str, float], dict[str, float]]:
    means = simulations.outcomes.mean(axis=0)
    p90 = np.quantile(simulations.outcomes, 0.90, axis=0)
    person_index = {person: index for index, person in enumerate(simulations.person_ids)}
    mean_by_id: dict[str, float] = {}
    p90_by_id: dict[str, float] = {}
    for player in slate.players:
        multiplier = 1.5 if player.role == "CPT" else 1.0
        index = person_index[player.underlying_id]
        mean_by_id[player.dk_id] = float(means[index] * multiplier)
        p90_by_id[player.dk_id] = float(p90[index] * multiplier)
    return mean_by_id, p90_by_id


def _read_brackets(
    path: str | Path | None,
    *,
    valid_ids: Iterable[str] | None = None,
) -> dict[str, OwnershipBracket]:
    if not path:
        return {}
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != ("DK_ID", "LOW", "BASE", "HIGH"):
            raise ValueError("ownership bracket CSV must be DK_ID,LOW,BASE,HIGH")
        allowed = set(valid_ids) if valid_ids is not None else None
        brackets: dict[str, OwnershipBracket] = {}
        for row_number, row in enumerate(reader, start=2):
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f"ownership bracket row {row_number} has missing or extra cells")
            dk_id = row["DK_ID"].strip()
            if not dk_id:
                continue
            if dk_id in brackets:
                raise ValueError(f"duplicate ownership bracket DK_ID: {dk_id}")
            if allowed is not None and dk_id not in allowed:
                raise ValueError(f"ownership bracket DK_ID is not in the salary pool: {dk_id}")
            try:
                brackets[dk_id] = OwnershipBracket(
                    float(row["LOW"]), float(row["BASE"]), float(row["HIGH"])
                )
            except ValueError as exc:
                raise ValueError(f"ownership bracket row {row_number}: {exc}") from exc
        return brackets


def _finding_dict(finding: QAFinding) -> dict[str, object]:
    return {
        "code": finding.code,
        "severity": finding.severity,
        "trigger_value": finding.trigger_value,
        "threshold": finding.threshold,
        "message": finding.message,
        "blocking": finding.blocking,
    }


def _weighted_salary_left_range(slate, fields_by_state) -> tuple[float, float] | None:
    values: list[int] = []
    weights: list[int] = []
    for field in fields_by_state.values():
        for field_lineup in field:
            validation = validate_lineup(slate, field_lineup.roster)
            if validation.valid and validation.lineup is not None:
                values.append(slate.salary_cap - validation.lineup.salary)
                weights.append(field_lineup.multiplicity)
    if not values:
        return None
    expanded = np.repeat(np.asarray(values, dtype=np.int32), np.asarray(weights, dtype=np.int32))
    return float(np.quantile(expanded, 0.05)), float(np.quantile(expanded, 0.95))


def _referee_uncertainty(
    *,
    select_economics,
    select_indices: tuple[int, ...],
    referee_economics,
    referee_indices: tuple[int, ...],
    entry_fee: float,
) -> float:
    # SELECT and REFEREE are separate banks with separate seeds, so there is no
    # scenario to pair on and the two variances add. R07: each side's variance
    # is now divided by its effective sample size rather than its row count, so
    # a bank with repeated scenarios cannot narrow the REFEREE tolerance and
    # wave a disagreement through.
    standard_error = unpaired_difference_standard_error(
        select_economics,
        select_indices,
        referee_economics,
        referee_indices,
        entry_fee=entry_fee,
    )
    return float(1.96 * standard_error)


def command_build(args: argparse.Namespace) -> int:
    started = time.perf_counter()
    run_id = _resolved_run_id(args.run_id, args.label)
    output_dir = Path(args.output_dir).resolve() / run_id
    immutable_targets = (
        output_dir / f"assignments_{run_id}.csv",
        output_dir / f"build_{run_id}.json",
        output_dir / "scenarios",
    )
    if any(path.exists() for path in immutable_targets):
        raise RuntimeError(
            f"build outputs already exist for immutable run_id {run_id}; use a new run_id"
        )
    slate = parse_salaries(args.salaries)
    _validate_scoring_config(slate)
    entries = parse_entries(args.entries)
    reconcile_template(entries, slate)
    require_single_contest(entries)
    if args.field_size <= len(entries.authorizations):
        raise ValueError(
            "field size must exceed the reserved entry count for opponent-field modeling"
        )
    for name in (
        "design_objectives",
        "candidates",
        "milp_seed_candidates",
        "field_sample_size",
        "field_chunk_size",
        "shortlist_limit",
    ):
        if getattr(args, name) < 1:
            raise ValueError(f"{name} must be positive")
    for name in ("design_scenarios", "select_scenarios", "referee_scenarios"):
        value = getattr(args, name)
        if value is not None and value < 1:
            raise ValueError(f"{name} must be positive when supplied")
    if not np.isfinite(args.per_solve_seconds) or args.per_solve_seconds <= 0:
        raise ValueError("per_solve_seconds must be positive")
    input_hashes = {
        "salary": slate.salary_hash,
        "entries": entries.raw_hash,
        "payouts": sha256_file(args.payouts),
        "team_projections": sha256_file(args.team_projections),
        "player_opportunities": sha256_file(args.player_opportunities),
    }
    model = load_opportunity_model(slate, args.team_projections, args.player_opportunities)
    for name, path in (
        ("salary", args.salaries),
        ("entries", args.entries),
        ("team_projections", args.team_projections),
        ("player_opportunities", args.player_opportunities),
    ):
        if sha256_file(path) != input_hashes[name]:
            raise RuntimeError(f"{name} input changed while it was being validated")
    tiers = parse_payout_csv(
        args.payouts, ticket_face_value=getattr(args, "ticket_face_value", None)
    )
    validate_payout_tiers(
        tiers,
        advertised_value=args.advertised_prize_value,
        ticket_face_value=args.ticket_face_value,
        field_size=args.field_size,
        reserved_entry_count=len(entries.authorizations),
    )
    if sha256_file(args.payouts) != input_hashes["payouts"]:
        raise RuntimeError("payout input changed while it was being validated")
    default_design, default_select, default_referee = _runtime_scenario_defaults(slate)
    design_count = args.design_scenarios if args.design_scenarios is not None else default_design
    select_count = args.select_scenarios if args.select_scenarios is not None else default_select
    referee_count = (
        args.referee_scenarios if args.referee_scenarios is not None else default_referee
    )
    design_simulations = simulate_factor_bank(
        slate,
        model,
        scenarios=design_count,
        seed=args.seed,
        purpose="DESIGN",
        tail_oversample=True,
    )
    select_simulations = simulate_factor_bank(
        slate,
        model,
        scenarios=select_count,
        seed=args.seed + 1,
        purpose="SELECT",
    )
    referee_simulations = simulate_factor_bank(
        slate,
        model,
        scenarios=referee_count,
        seed=args.seed + 2,
        purpose="REFEREE",
    )
    mean_scores, p90_scores = _projection_scores(slate, design_simulations)
    select_mean_scores, select_p90_scores = _projection_scores(slate, select_simulations)
    objectives: list[Mapping[str, float]] = [mean_scores, p90_scores]
    person_index = {person: index for index, person in enumerate(design_simulations.person_ids)}
    scenario_indices = np.linspace(
        0,
        design_count - 1,
        min(args.design_objectives, design_count),
    ).astype(int)
    for scenario_index in scenario_indices:
        objective: dict[str, float] = {}
        for player in slate.players:
            multiplier = 1.5 if player.role == "CPT" else 1.0
            objective[player.dk_id] = float(
                design_simulations.outcomes[
                    scenario_index, person_index[player.underlying_id]
                ]
                * multiplier
            )
        objectives.append(objective)
    milp_seed_count = min(args.candidates, args.milp_seed_candidates)
    solved = generate_candidates(
        slate,
        objectives,
        maximum=milp_seed_count,
        per_solve_seconds=args.per_solve_seconds,
    )
    candidate_rosters = [result.roster for result in solved if result.roster is not None]
    if len(candidate_rosters) < len(entries.authorizations):
        raise RuntimeError("candidate bank is too small for the reserved entries")
    brackets = _read_brackets(
        args.ownership_brackets,
        valid_ids=(player.dk_id for player in slate.players),
    )
    team_total = {team.team: team.market_total for team in model.teams}
    states = cold_start_states(slate, select_mean_scores, team_total, brackets)
    seen_rosters = set(candidate_rosters)
    fill_round = 0
    while len(candidate_rosters) < args.candidates and fill_round < 8:
        remaining = args.candidates - len(candidate_rosters)
        sample_count = min(max(int(remaining * 1.15), 1_000), 100_000)
        sampled_candidates = generate_opponent_field(
            slate,
            states[0],
            field_size=sample_count,
            seed=args.seed + 50_000 + fill_round,
            maximum_attempt_factor=300,
        )
        before = len(candidate_rosters)
        for sampled in sampled_candidates:
            if sampled.roster not in seen_rosters:
                candidate_rosters.append(sampled.roster)
                seen_rosters.add(sampled.roster)
                if len(candidate_rosters) == args.candidates:
                    break
        if len(candidate_rosters) == before:
            break
        fill_round += 1
    if len(candidate_rosters) < args.candidates:
        raise RuntimeError(
            f"candidate bank target not reached: {len(candidate_rosters)}/{args.candidates}"
        )
    coverage = coverage_report(slate, candidate_rosters)

    def shortlist_score(roster: tuple[str, ...]) -> tuple[float, float, tuple[str, ...]]:
        mean_score = sum(select_mean_scores[dk_id] for dk_id in roster)
        p90_score = sum(select_p90_scores[dk_id] for dk_id in roster)
        return mean_score, p90_score, tuple(reversed(roster))

    economics_limit = min(args.shortlist_limit, len(candidate_rosters), 5_000)
    economics_rosters = sorted(candidate_rosters, key=shortlist_score, reverse=True)[
        :economics_limit
    ]
    actual_field_size = args.field_size
    opponent_count = max(1, actual_field_size - len(entries.authorizations))
    sample_size = min(opponent_count, args.field_sample_size)
    state_economics = {}
    fields_by_state = {}
    for state_number, state in enumerate(states):
        sampled = generate_opponent_field(
            slate,
            state,
            field_size=sample_size,
            seed=args.seed + 1000 + state_number,
        )
        field = scale_field_multiplicities(sampled, opponent_count)
        fields_by_state[state.name] = field
        state_economics[state.name] = evaluate_candidates_against_field(
            slate=slate,
            simulations=select_simulations,
            candidates=economics_rosters,
            field=field,
            payout_tiers=tiers,
            ticket_face_value=args.ticket_face_value,
            field_chunk_size=args.field_chunk_size,
        )
    metrics = select_portfolio(
        state_economics,
        entry_count=len(entries.authorizations),
        entry_fee=entries.authorizations[0].entry_fee,
        field_size=actual_field_size,
        objective=ContestObjective(args.objective),
        shortlist_limit=args.shortlist_limit,
    )
    assignments = {
        entry.entry_id: tuple(economics_rosters[candidate_index])
        for entry, candidate_index in zip(
            sorted(entries.authorizations, key=lambda entry: entry.entry_id),
            metrics.candidate_indices,
            strict=True,
        )
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    scenario_artifacts = {
        result.purpose: save_scenario_bank(result, output_dir / "scenarios")
        for result in (design_simulations, select_simulations, referee_simulations)
    }
    selected_rosters = [economics_rosters[index] for index in metrics.candidate_indices]
    referee_economics = {
        state_name: evaluate_candidates_against_field(
            slate=slate,
            simulations=referee_simulations,
            candidates=selected_rosters,
            field=field,
            payout_tiers=tiers,
            ticket_face_value=args.ticket_face_value,
            field_chunk_size=args.field_chunk_size,
        )
        for state_name, field in fields_by_state.items()
    }
    referee_metrics = evaluate_portfolio(
        referee_economics,
        tuple(range(len(selected_rosters))),
        entry_fee=entries.authorizations[0].entry_fee,
        field_size=actual_field_size,
        objective=ContestObjective(args.objective),
    )
    referee_uncertainty = _referee_uncertainty(
        select_economics=state_economics[metrics.worst_state],
        select_indices=metrics.candidate_indices,
        referee_economics=referee_economics[referee_metrics.worst_state],
        referee_indices=tuple(range(len(selected_rosters))),
        entry_fee=entries.authorizations[0].entry_fee,
    )

    selected_lineups_by_entry = _validated_lineups(slate, assignments)
    selected_lineups = tuple(selected_lineups_by_entry.values())
    duplicate_p95: dict[str, float] = {}
    divided_payout_p95: dict[str, float] = {}
    for lineup, candidate_index in zip(
        selected_lineups,
        metrics.candidate_indices,
        strict=True,
    ):
        duplicate_p95[lineup.canonical_key] = float(
            np.quantile(
                [
                    float(economics.duplicate_counts[candidate_index])
                    for economics in state_economics.values()
                ],
                0.95,
            )
        )
        divided_payout_p95[lineup.canonical_key] = min(
            float(np.quantile(economics.gross_payout[:, candidate_index], 0.95))
            for economics in state_economics.values()
        )

    solved_by_roster = {
        result.roster: result for result in solved if result.roster is not None
    }
    selected_solver_results = [
        solved_by_roster[roster] for roster in selected_rosters if roster in solved_by_roster
    ]
    selected_solver_gap = (
        max(
            (result.mip_gap for result in selected_solver_results if result.mip_gap is not None),
            default=None,
        )
        if selected_solver_results
        else None
    )
    selected_solver_gap_complete = all(
        result.mip_gap is not None for result in selected_solver_results
    )
    if selected_solver_results and not selected_solver_gap_complete:
        selected_solver_gap = None

    def run_registered_audit() -> tuple[QAFinding, ...]:
        return audit_selected_portfolio(
            slate=slate,
            lineups=selected_lineups,
            evidence=(),
            duplicate_p95=duplicate_p95,
            divided_payout_p95=divided_payout_p95,
            entry_fee=entries.authorizations[0].entry_fee,
            salary_left_field_range=_weighted_salary_left_range(slate, fields_by_state),
            solver_gap=selected_solver_gap,
            solver_gap_required=bool(selected_solver_results),
            final_byte_match=None,
        )

    qa_history = run_three_pass_audit(run_registered_audit, lambda _findings: False)
    generated_findings: list[QAFinding] = []
    if not coverage.pass_status:
        generated_findings.append(
            QAFinding(
                code="CANDIDATE_FAMILY_COVERAGE_INCOMPLETE",
                severity="MEDIUM",
                trigger_value=", ".join(coverage.missing_registered_families),
                threshold="all registered candidate families represented",
                message=(
                    "candidate generation omitted one or more registered construction "
                    "families; coverage is informative and is not an upload-safety rule"
                ),
                blocking=False,
            )
        )
    for simulations in (design_simulations, select_simulations, referee_simulations):
        for diagnostic in ("passing_receiving_accounting", "share_conservation"):
            value = simulations.diagnostics.get(diagnostic)
            if value != 1.0:
                generated_findings.append(
                    QAFinding(
                        code=f"{simulations.purpose}_{diagnostic.upper()}_FAILED",
                        severity="CRITICAL",
                        trigger_value="MISSING" if value is None else value,
                        threshold=1.0,
                        message="scenario-bank accounting diagnostics did not pass",
                        blocking=True,
                    )
                )
    qa_findings = tuple(qa_history[-1] if qa_history else ()) + tuple(generated_findings)
    qa_blocked = any(finding.blocking for finding in qa_findings)
    referee_blocked, referee_reason = referee_blocks(
        select_net_delta=metrics.expected_net_payout,
        referee_net_delta=referee_metrics.expected_net_payout,
        uncertainty=referee_uncertainty,
        safety_failure=qa_blocked,
        hard_constraint_failure=False,
    )
    referee_finding = (
        QAFinding(
            code=referee_reason,
            severity="CRITICAL",
            trigger_value=referee_metrics.expected_net_payout,
            threshold=f"same sign as SELECT outside +/-{referee_uncertainty:.6f}",
            message="independent REFEREE bank blocks promotion",
            blocking=True,
        ),
    ) if referee_blocked else ()
    precertification_findings = tuple(qa_findings) + referee_finding
    assignment_path = output_dir / f"assignments_{run_id}.csv"
    headers = ("Entry ID",) + (
        ("QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX", "DST")
        if slate.mode is EngineMode.CLASSIC
        else ("CPT", "FLEX", "FLEX", "FLEX", "FLEX", "FLEX")
    )
    with assignment_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\r\n")
        writer.writerow(headers)
        for entry_id in sorted(assignments):
            writer.writerow((entry_id, *assignments[entry_id]))
    solver_proof = {
        "milp_candidate_count": len(solved),
        "milp_statuses": {
            status: sum(result.status == status for result in solved)
            for status in sorted({result.status for result in solved})
        },
        "maximum_mip_gap": max(
            (result.mip_gap for result in solved if result.mip_gap is not None),
            default=None,
        ),
        "maximum_node_count": max(
            (result.node_count for result in solved if result.node_count is not None),
            default=None,
        ),
        "selected_candidate_sources": [
            "MILP" if roster in solved_by_roster else "LEGAL_FIELD_SAMPLER"
            for roster in selected_rosters
        ],
        "selected_mip_gaps": [
            solved_by_roster[roster].mip_gap if roster in solved_by_roster else None
            for roster in selected_rosters
        ],
    }
    bracket_normalization_deltas = {
        dk_id: {
            state.name: state.ownership[dk_id]
            - {
                "CHALK_FADE": bracket.low,
                "BASE": bracket.base,
                "CHALK_SURGE": bracket.high,
                "LATE_VALUE_SURGE": bracket.high,
                "SHARP_FIELD": bracket.base,
            }[state.name]
            for state in states
        }
        for dk_id, bracket in brackets.items()
    }
    elapsed = time.perf_counter() - started
    slate_by_id = {player.dk_id: player for player in slate.players}
    selected_people = {
        slate_by_id[dk_id].underlying_id
        for roster in selected_rosters
        for dk_id in roster
    }
    prior_only_pool_count = sum(
        player.underlying_id not in selected_people and player.evidence_state != "PASS"
        for player in model.players
    )
    report = {
        "schema_version": "nfl_prelock_run_manifest_v1",
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "DIAGNOSTIC_ASSIGNMENTS_READY_DO_NOT_UPLOAD",
        **_blocked_truth_values(
            file_valid=False,
            evidence_state=ReleaseEvidenceState.UNKNOWN,
            model_status=ModelStatus.PRIOR_ONLY,
            certification_basis=CertificationBasis.MODEL_ASSISTED,
        ),
        "label": "COLD_START_FIELD_MODEL",
        "assignments": str(assignment_path),
        "assignment_sha256": sha256_file(assignment_path),
        "input_hashes": input_hashes,
        "contest_parameters": {
            "contest_id": entries.authorizations[0].contest_id,
            "draft_group": slate.draft_group,
            "mode": slate.mode.value,
            "entry_fee": entries.authorizations[0].entry_fee,
            "field_size": args.field_size,
            "objective": ContestObjective(args.objective).value,
            "advertised_prize_value": args.advertised_prize_value,
            "ticket_face_value": args.ticket_face_value,
        },
        "candidate_count": len(candidate_rosters),
        "milp_seed_candidate_count": len(solved),
        "economics_shortlist_count": len(economics_rosters),
        "candidate_family_coverage": coverage.counts,
        "missing_candidate_families": coverage.missing_registered_families,
        "model_status_limitations": {
            "prior_only_unselected_pool_count": prior_only_pool_count,
            "prospective_validation": "ABSENT",
        },
        "scenario_counts": {
            "DESIGN": design_count,
            "SELECT": select_count,
            "REFEREE": referee_count,
        },
        "artifact_versions": {
            "salary": "dk_salary_csv_v1",
            "entries": "dk_entry_csv_v1",
            "payouts": "nfl_payout_contract_v1",
            "assignments": "nfl_assignment_csv_v1",
            "team_projections": team_projections_csv_version(
                team.weather_state for team in model.teams
            ),
            "player_opportunities": "nfl_player_opportunities_csv_v1",
            "DESIGN": "nfl_scenario_bank_v1",
            "SELECT": "nfl_scenario_bank_v1",
            "REFEREE": "nfl_scenario_bank_v1",
        },
        "scenario_artifacts": scenario_artifacts,
        "field_sample_size": sample_size,
        "field_size": actual_field_size,
        "simulated_opponents": opponent_count,
        "portfolio": {
            key: value
            for key, value in metrics.__dict__.items()
            if key != "candidate_indices"
        },
        "quantitative_qa": {
            "pass_count": len(qa_history),
            "repair_attempted": False,
            "blocked": qa_blocked,
            "findings": [_finding_dict(finding) for finding in qa_findings],
        },
        "referee": {
            "blocked": referee_blocked,
            "reason": referee_reason,
            "robust_net_payout_lcb": referee_metrics.robust_net_payout_lcb,
            "expected_net_payout": referee_metrics.expected_net_payout,
            "elite_probability": referee_metrics.elite_probability,
            "uncertainty_95": referee_uncertainty,
            "binding": True,
        },
        "precertification_findings": [
            _finding_dict(finding) for finding in precertification_findings
        ],
        "solver_proof": solver_proof,
        "ownership_bracket_normalization_deltas": bracket_normalization_deltas,
        "candidate_indices": list(metrics.candidate_indices),
        "elapsed_seconds": elapsed,
        "memory_limit_bytes": live_memory_limit(),
        "next": "Review assignments, supply official exact-ID ACTIVE evidence for every selected player, then run certify.",
        "warning": "Cold-start field outputs are diagnostic priors, not EV, ROI, win probability, or calibrated ownership.",
    }
    _write_json(output_dir / f"build_{run_id}.json", report)
    _print_json(report)
    return 0


def command_select(args: argparse.Namespace) -> int:
    """Prior-only Showdown selection. Never consults field or payout economics."""

    slate = parse_salaries(args.salaries)
    if args.salary_sha256 and sha256_file(args.salaries) != args.salary_sha256.strip().lower():
        raise ValueError("SALARY_ARTIFACT_HASH_MISMATCH")
    template = parse_entries(args.entries)
    reconcile_template(template, slate)
    entry_ids = [entry.entry_id for entry in template.authorizations]

    model = load_opportunity_model(
        slate, args.team_projections, args.player_opportunities
    )
    contract = build_participation_contract(
        slate,
        operator_excluded_dk_ids=args.exclude or (),
        extra_unavailable_statuses=args.unavailable_status or (),
        extra_available_statuses=args.available_status or (),
    )
    _reduced, redistribution = redistribute_opportunity(model, contract, redistribute=False)
    splits = read_team_splits(
        args.team_splits,
        prior_season=args.prior_season,
        teams=sorted({player.team for player in slate.players}),
    )
    count = args.count if args.count else len(entry_ids)
    selection_as_of = None
    if getattr(args, "as_of", None):
        selection_as_of = datetime.fromisoformat(str(args.as_of).replace("Z", "+00:00"))
        if selection_as_of.tzinfo is None:
            raise ValueError("as_of must be timezone aware")
        selection_as_of = selection_as_of.astimezone(timezone.utc)
    lineups, scores, selection = select_prior_lineups(
        slate,
        model,
        splits,
        contract,
        count=count,
        differentiate_captain=not args.allow_repeat_captain,
        max_person_overlap=args.max_person_overlap,
        role_evidence_json=getattr(args, "role_evidence_json", None),
        offensive_role_evidence_json=getattr(args, "offensive_role_evidence_json", None),
        qb_depth_role_evidence_json=getattr(args, "qb_depth_role_evidence_json", None),
        as_of=selection_as_of,
    )
    assignments = assignments_for_entries(entry_ids, lineups)

    output_dir = Path(args.output_dir).resolve()
    assignments_path = output_dir / "assignments.csv"
    if assignments_path.exists():
        raise ValueError(f"OUTPUT_PACKAGE_EXISTS:{assignments_path}")
    assignments_hash = write_assignments_csv(assignments_path, assignments)
    names = {
        player.dk_id: f"{player.name} ({player.position}, {player.team})"
        for player in slate.players
    }
    result = {
        "status": "DO_NOT_UPLOAD",
        "package_status": "PRIOR_ONLY_ASSIGNMENTS_READY",
        **_blocked_truth_values(
            file_valid=False,
            evidence_state=ReleaseEvidenceState.UNKNOWN,
            model_status=ModelStatus.PRIOR_ONLY,
            certification_basis=CertificationBasis.MODEL_ASSISTED,
        ),
        "assignments": str(assignments_path),
        "assignments_sha256": assignments_hash,
        "reserved_entries": entry_ids,
        "lineups": [lineup.as_payload(names) for lineup in lineups],
        "participation": contract.as_report(),
        "redistribution": redistribution,
        "selection": selection,
        "prior_scores": scores.as_report(),
        "next": (
            "Run review-export with these assignments to write the byte-audited"
            " bulk-entry CSV."
        ),
        "warning": (
            "Prior-only selection maximizing a central estimate. Not a ceiling, not"
            " ownership aware, and not EV, ROI, win probability or edge."
        ),
    }
    write_run_record(output_dir / "selection_report.json", result)
    _print_json(result)
    return 0


def command_review_export(args: argparse.Namespace) -> int:
    """Legality plus byte audit, with no payout table and no economics."""

    slate = parse_salaries(args.salaries)
    template = parse_entries(args.entries)
    assignments = read_assignment_csv(args.assignments, slate.mode)
    output_dir = Path(args.output_dir).resolve()
    export = export_review_entries(
        slate=slate,
        template=template,
        assignments=assignments,
        output_path=output_dir / f"DK_REVIEW_ENTRY_{args.label or 'showdown'}.csv",
    )
    report = export.as_report(
        {
            "salaries_sha256": sha256_file(args.salaries),
            "entries_sha256": template.raw_hash,
            "assignments_sha256": sha256_file(args.assignments),
            "contest_ids": sorted({e.contest_id for e in template.authorizations}),
            "entry_fees": sorted({e.entry_fee for e in template.authorizations}),
        }
    )
    write_run_record(output_dir / "review_export_report.json", report)
    _print_json(report)
    return 0 if export.file_valid else 2


def command_baseline(args: argparse.Namespace) -> int:
    """R28's baseline: distinct legal lineups from the DraftKings bytes alone (Session 04).

    Exit 0 fills every blank authorized row, 3 fills some and names the rest, 2
    fills none. None of them clears an upload: the run ends `PRIOR_ONLY` and
    `DO_NOT_UPLOAD`.
    """

    outcome = run_baseline(
        salaries=args.salaries,
        entries=args.entries,
        out_dir=args.out_dir,
        run_id=args.run_id,
        per_solve_seconds=args.per_solve_seconds,
        budget_seconds=args.budget_seconds,
        operator_excluded_dk_ids=getattr(args, "exclude", None) or (),
        extra_unavailable_statuses=getattr(args, "unavailable_status", None) or (),
        official_status_csv=getattr(args, "official_status", None),
    )
    _print_json(baseline_summary(outcome))
    return outcome.exit_code


def command_priors_propose(args: argparse.Namespace) -> int:
    result = propose_prior_package(
        salaries=args.salaries,
        salary_sha256=args.salary_sha256,
        season=args.season,
        prior_season=args.prior_season,
        as_of=args.as_of,
        output_dir=args.output_dir,
    )
    _print_json(result)
    return 0


def command_priors_freeze(args: argparse.Namespace) -> int:
    result = freeze_prior_package(
        package_dir=args.package_dir,
        reviewed=args.reviewed,
        reviewed_sha256=args.reviewed_sha256,
        salaries=args.salaries,
        salary_sha256=args.salary_sha256,
        as_of=args.as_of,
        output_dir=args.output_dir,
        weather_state=args.weather_state,
        salary_observed_at=args.salary_observed_at,
        weather_source_uri=args.weather_source_uri,
        weather_observed_at=args.weather_observed_at,
    )
    _print_json(result)
    return 0


def command_project(args: argparse.Namespace) -> int:
    package = build_projection_package(
        salaries=args.salaries,
        salary_sha256=args.salary_sha256,
        team_source=args.team_source,
        team_source_sha256=args.team_source_sha256,
        player_source=args.player_source,
        player_source_sha256=args.player_source_sha256,
        identity_map=args.identity_map,
        identity_map_sha256=args.identity_map_sha256,
        as_of=args.as_of,
        output_dir=args.output_dir,
    )
    result = {
        "status": "DO_NOT_UPLOAD",
        "package_status": "PROJECTION_INPUTS_READY",
        **_blocked_truth_values(
            file_valid=False,
            evidence_state=ReleaseEvidenceState.PASS,
            model_status=ModelStatus.PRIOR_ONLY,
            certification_basis=CertificationBasis.MODEL_ASSISTED,
        ),
        "output_dir": package.output_dir,
        "team_projections": package.team_projections,
        "player_opportunities": package.player_opportunities,
        "source_ledger": package.source_ledger,
        "hashes": package.hashes,
        "input_hashes": package.input_hashes,
        "next": (
            "Use the three files as prior-only model inputs for build/certify; "
            "they do not authorize upload."
        ),
        "warning": (
            "This deterministic package is PRIOR_ONLY. It does not establish EV, ROI, "
            "profitability, calibration, win probability, cash probability, or upload readiness."
        ),
    }
    _print_json(result)
    return 0


def command_late_swap(args: argparse.Namespace) -> int:
    run_id = _resolved_run_id(args.run_id, "late-swap")
    now = datetime.fromisoformat(args.as_of.replace("Z", "+00:00"))
    if now.tzinfo is None:
        raise ValueError("--as-of must include a timezone")
    try:
        manifest, manifest_path = govern_late_swap(
            run_id=run_id,
            salaries_path=args.salaries,
            current_entries_path=args.current_entries,
            prior_manifest_path=args.prior_manifest,
            prior_assignments_path=args.prior_assignments,
            proposed_assignments_path=args.proposed_assignments,
            eligibility_evidence_path=args.eligibility_evidence,
            inactive_reports_path=args.inactive_reports,
            output_directory=args.output_dir,
            as_of=now,
        )
    except LateSwapRunError as exc:
        _print_json(
            {
                "run_id": run_id,
                "status": "DO_NOT_UPLOAD",
                **_blocked_truth_values(),
                "blockers": [str(exc)],
                "manifest": None,
                "output_path": None,
                "output_sha256": None,
                "next_action": "Use a new unique run ID after reviewing the existing run directory.",
            }
        )
        return 2
    _print_json(
        {
            "run_id": run_id,
            "status": manifest.status,
            "FILE_VALID": manifest.file_valid,
            "EVIDENCE_STATE": manifest.evidence_state.value,
            "MODEL_STATUS": manifest.model_status.value,
            "RELEASE_DECISION": manifest.release_decision.value,
            "certification_basis": manifest.certification_basis.value,
            "blockers": list(manifest.blockers),
            "input_hashes": manifest.input_hashes,
            "manifest": str(manifest_path),
            "output_path": manifest.output_path,
            "output_sha256": manifest.output_sha256,
            "proposed_output_sha256": manifest.proposed_output_sha256,
            "next_action": manifest.next_action,
        }
    )
    return (
        0 if manifest.release_decision.value == "CERTIFIED_UPLOAD_PACKAGE" else 2
    )


def command_settle(args: argparse.Namespace) -> int:
    if args.request and args.replay:
        raise ValueError("settle accepts only one of --request or --replay")
    if (args.request or args.replay) and (args.entries or args.standings):
        raise ValueError(
            "legacy --entries/--standings cannot be mixed with --request or --replay"
        )
    if args.replay:
        _print_json(replay_settlement_package(args.replay))
        return 0
    if args.request:
        outcome = capture_settlement_bundle(args.request, args.output_dir)
        bundle = outcome.bundle
        _print_json(
            {
                "status": "Q1_SETTLEMENT_COMPLETE",
                "capture_status": bundle.capture_status,
                "settlement_id": bundle.settlement_id,
                "run_id": bundle.run_id,
                "package_path": outcome.package_path,
                "reference_result_hash": bundle.reference_result_hash,
                "assignment_semantic_hash": bundle.assignment_semantic_hash,
                "artifact_count": len(bundle.artifacts),
                "elapsed_seconds": outcome.elapsed_seconds,
                "peak_python_memory_bytes": outcome.peak_python_memory_bytes,
                **bundle.release_truths.model_dump(mode="json", by_alias=True),
                "note": (
                    "Settlement capture completion does not change the frozen pre-lock "
                    "release truths or make a lineup upload-ready."
                ),
            }
        )
        return 0
    if not args.entries or not args.standings:
        raise ValueError(
            "settle requires --request for a Q1-complete bundle, --replay for copied-package "
            "verification, or both --entries and --standings for a legacy partial check"
        )
    entries = parse_entries(args.entries)
    snapshot = parse_standings(args.standings)
    require_entry_coverage(snapshot, {entry.entry_id for entry in entries.authorizations})
    result = {
        "status": "LEGACY_PARTIAL_SETTLEMENT_CAPTURE",
        "q1_complete": False,
        **_blocked_truth_values(),
        "standings_sha256": snapshot.sha256,
        "rows": len(snapshot.rows),
        "reserved_entry_coverage": len(entries.authorizations),
        "blockers": [
            "Q1_COMPLETE_REQUEST_REQUIRED: legacy coverage does not bind salaries, payouts, "
            "assignments, predictions, scenarios, versions, or the metric registry"
        ],
        "note": "This compatibility check is intentionally not a Q1 settlement bundle.",
    }
    _print_json(result)
    return 2


def command_learn(args: argparse.Namespace) -> int:
    registry = load_metric_registry(args.metric_registry)
    evaluated_at = (
        datetime.fromisoformat(args.challenger_evaluated_at.replace("Z", "+00:00"))
        if args.challenger_evaluated_at
        else datetime.now(timezone.utc)
    )
    require_registry_precedes_evaluation(registry, evaluated_at)
    decision = evaluate_challenger(
        comparable_settled_slates=args.comparable_slates,
        reproducible=args.reproducible,
        integrity_pass=args.integrity_pass,
        rolling_origin_improvement=args.rolling_origin_improvement,
        calibration_pass=args.calibration_pass,
        drift_pass=args.drift_pass,
        no_regression=args.no_regression,
        prospective_field_gates=args.prospective_field_gates,
        realized_roi_observed=args.realized_roi,
    )
    rollback, rollback_reason = should_rollback(
        integrity_failure=args.integrity_failure,
        consecutive_registered_degradation_windows=args.degradation_windows,
    )
    promotion_failures = tuple(
        dict.fromkeys((*decision.reasons, "REGISTERED_METRIC_RESULTS_REQUIRED_Q6"))
    )
    _print_json(
        {
            "promote": False,
            "tier": "COLD",
            "influence_cap": 0.0,
            "promotion_failures": promotion_failures,
            "legacy_boolean_checks_passed": decision.promote,
            "rollback": rollback,
            "rollback_reason": rollback_reason,
            "metric_registry_id": registry.registry_id,
            "metric_registry_sha256": registry.sha256,
            "metric_registry_registered_at": registry.registered_at.isoformat(),
            "challenger_evaluated_at": evaluated_at.isoformat(),
            "registry_policy_status": "REGISTRATION_ONLY_NO_MODEL_PROMOTION",
            "roi_policy": "realized ROI is descriptive and was not used in this decision",
        }
    )
    return 2


def command_status(args: argparse.Namespace) -> int:
    data = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    release_decision = data.get(
        "RELEASE_DECISION",
        "CERTIFIED_UPLOAD_PACKAGE" if data.get("status") == "CERTIFIED" else "DO_NOT_UPLOAD",
    )
    _print_json(
        {
            "run_id": data.get("run_id"),
            "status": data.get("status"),
            "FILE_VALID": data.get("FILE_VALID", data.get("status") == "CERTIFIED"),
            "EVIDENCE_STATE": data.get(
                "EVIDENCE_STATE", "PASS" if data.get("status") == "CERTIFIED" else "UNKNOWN"
            ),
            "MODEL_STATUS": data.get("MODEL_STATUS", "UNVALIDATED"),
            "RELEASE_DECISION": release_decision,
            "certification_basis": data.get(
                "certification_basis", "MANUAL_GUARDRAIL"
            ),
            "output_path": data.get("output_path"),
            "output_sha256": data.get("output_sha256"),
            "blockers": data.get("blockers", []),
        }
    )
    return 0 if release_decision == "CERTIFIED_UPLOAD_PACKAGE" else 2


def command_audit(args: argparse.Namespace) -> int:
    """Historical artifact integrity. R09: this is never a current release decision.

    It used to feed the manifest's stored truth fields into the release policy,
    so a package whose evidence had expired still reported
    `CERTIFIED_UPLOAD_PACKAGE`. It now reports what the manifest *stored*,
    labelled as stored, and its own release decision is fixed at
    `DO_NOT_UPLOAD`. Use `preflight` for a current pre-upload decision.
    """

    report = historical_artifact_integrity(args.manifest)
    _print_json(report)
    return 0 if report["ARTIFACT_INTEGRITY"] == "PASS" else 2


def command_preflight(args: argparse.Namespace) -> int:
    """Live pre-upload check. Re-derives every hard gate at the current clock."""

    report = live_pre_upload_check(
        args.manifest,
        salaries=getattr(args, "salaries", None),
        entries=getattr(args, "entries", None),
        assignments=getattr(args, "assignments", None),
    )
    _print_json(report)
    return 0 if report["RELEASE_DECISION"] == "CERTIFIED_UPLOAD_PACKAGE" else 2


def _cowork_run_control_values(request: CoworkRunRequest) -> dict[str, object]:
    return {
        "RUN_LABEL": request.label,
        "SALARY_CSV": request.salary_csv or "",
        "ENTRY_CSV": request.entry_csv or "",
        "PAYOUT_CSV": request.payout_csv or "",
        "ASSIGNMENT_CSV": request.assignment_csv or "",
        "TEAM_PROJECTION_CSV": request.team_projection_csv or "",
        "PLAYER_OPPORTUNITY_CSV": request.player_opportunity_csv or "",
        "OFFICIAL_STATUS_CSV": request.official_status_csv or "",
        "ROLE_EVIDENCE_JSON": request.role_evidence_json or "",
        "OFFENSIVE_ROLE_EVIDENCE_JSON": request.offensive_role_evidence_json or "",
        "QB_DEPTH_ROLE_EVIDENCE_JSON": request.qb_depth_role_evidence_json or "",
        "PORTFOLIO_POLICY_JSON": request.portfolio_policy_json or "",
        "FIELD_SIZE": request.field_size,
        "MAX_ENTRIES": None,
        "ADVERTISED_PRIZE_VALUE": request.advertised_prize_value,
        "TICKET_FACE_VALUE": request.ticket_face_value,
        "CONTEST_OBJECTIVE": request.objective,
        "MANUAL_GUARDRAIL_MODE": "YES" if request.manual_guardrail else "NO",
    }


def _snapshot_cowork_request(
    request: CoworkRunRequest, run_id: str, hashes: Mapping[str, str]
) -> CoworkRunRequest:
    updates: dict[str, object] = {"input_dir": None}
    for name in PATH_FIELDS:
        raw = getattr(request, name)
        if raw is None:
            continue
        source = str(Path(raw).resolve())
        updates[name] = str(_snapshot_path(run_id, source, hashes[source]).resolve())
    return replace(request, **updates)


def _cowork_reported_blockers(request: CoworkRunRequest) -> tuple[str, ...]:
    """Every named input this request still lacks, whatever the profile gates on."""

    blockers = list(required_next_inputs(request))
    if request.profile == "prior_review":
        blockers.extend(prior_review_next_inputs(request))
    return tuple(blockers)


def _cowork_core_blockers(request: CoworkRunRequest) -> tuple[str, ...]:
    """The subset the requested profile actually gates on."""

    return gating_blockers(request, _cowork_reported_blockers(request))


# R28 (Session 05): a review CSV that passed independent validation survives a
# later presentation failure. A readable-review discrepancy is classified code by
# code through the gate registry; a `V`, unregistered or unparseable one withholds
# the CSV, anything else keeps it listed with a presentation limitation, and the
# kept CSV is revalidated by `delivery.publish` before anything advertises it.
_C3_OUTPUT_KEYS = ("classic_export_audit", "bulk_entry_csv", "readable_review_json", "readable_review_html")
_READABLE_KEYS = ("readable_review_json", "readable_review_html")
_PRESENTATION_NEXT = (
    "The review CSV passed independent validation and stays listed; only its readable "
    "review failed. Review the CSV by exact Entry ID and roster ID, or rerun to rebuild "
    "the display. It remains PRIOR_ONLY / DO_NOT_UPLOAD."
)


def _discrepancy_text(exc: BaseException) -> str:
    """The codes a readable-review failure carries; any other exception has none."""

    if isinstance(exc, (ReadableReviewError, ClassicReviewError)):
        return str(exc)
    return f"{type(exc).__name__}:{exc}"


def _without(mapping: Mapping[str, object], keys: Iterable[str]) -> dict:
    drop = set(keys)
    return {key: value for key, value in mapping.items() if key not in drop}


def _unlink_outputs(outcome, keys: Iterable[str]) -> None:
    for key in keys:
        candidate = outcome.artifacts.get(key)
        if candidate:
            try:
                Path(candidate).unlink(missing_ok=True)
            except OSError:
                pass


def _keep_classic_review_csv(outcome, blocker: str):
    """C3's export and audit stay listed; the readable JSON and HTML that failed go."""

    _unlink_outputs(outcome, _READABLE_KEYS)
    export = {
        **dict(outcome.export or {}),
        "readable_review_json": None,
        "readable_review_json_sha256": None,
        "readable_review_html": None,
        "readable_review_html_sha256": None,
        "readable_review_failure": blocker,
    }
    return replace(
        outcome,
        stage="READABLE_REVIEW",
        artifacts=_without(outcome.artifacts, _READABLE_KEYS),
        hashes=_without(outcome.hashes, _READABLE_KEYS),
        reports=_without(outcome.reports, ("readable_review",)),
        export=export,
        error=blocker,
    )


def _withhold_classic_review_csv(outcome, blocker: str):
    """C3's four outputs are removed and nothing advertises them (a `V` display code)."""

    _unlink_outputs(outcome, _C3_OUTPUT_KEYS)
    export = {
        **dict(outcome.export or {}),
        "FILE_VALID": False,
        "bulk_entry_csv": None,
        "bulk_entry_sha256": None,
        "downstream_audit": None,
        "downstream_audit_sha256": None,
        "readable_review_json": None,
        "readable_review_json_sha256": None,
        "readable_review_html": None,
        "readable_review_html_sha256": None,
        "problems": [blocker],
    }
    return replace(
        outcome,
        stage="READABLE_REVIEW",
        blocked=True,
        artifacts=_without(outcome.artifacts, _C3_OUTPUT_KEYS),
        hashes=_without(outcome.hashes, _C3_OUTPUT_KEYS),
        reports=_without(outcome.reports, ("classic_export_audit", "readable_review")),
        export=export,
        error=blocker,
    )


def _showdown_review_csv_record(
    outcome,
    blocker: str,
    *,
    withheld: bool,
    limitations: Iterable[DeliveryLimitation],
) -> object:
    """The Showdown CSV kept listed, or withheld from both indexes, after a display failure."""

    path = outcome.artifacts.get("bulk_entry_csv")
    digest = outcome.hashes.get("bulk_entry_csv")
    record = {
        "stage": "READABLE_REVIEW",
        "FILE_VALID": not withheld,
        "RELEASE_DECISION": ReleaseDecision.DO_NOT_UPLOAD.value,
        "blocker": blocker,
        "limitations": [item.code for item in limitations],
        ("withheld_artifacts" if withheld else "kept_artifacts"): {
            "bulk_entry_csv": {"path": path, "sha256": digest}
        },
        "meaning": _WITHHELD_MEANING if withheld else (
            "The readable review failed after the review CSV passed independent "
            "validation. The CSV stays listed with this presentation limitation (R28). "
            "It is not certified and not an upload authorization."
        ),
    }
    problems = [*list((outcome.export or {}).get("problems", [])), blocker]
    if withheld:
        drop = ("bulk_entry_csv", *_READABLE_KEYS)
        export = {**dict(outcome.export or {}), "FILE_VALID": False, "bulk_entry_csv": None,
                  "bulk_entry_sha256": None, "problems": problems}
        artifacts, hashes = _without(outcome.artifacts, drop), _without(outcome.hashes, drop)
    else:
        export = {**dict(outcome.export or {}), "problems": problems}
        artifacts, hashes = dict(outcome.artifacts), dict(outcome.hashes)
    return replace(
        outcome,
        stage="READABLE_REVIEW",
        blocked=withheld,
        artifacts=artifacts,
        hashes=hashes,
        reports={**outcome.reports, "readable_review_failure": record},
        export=export,
        error=blocker,
    )


_WITHHELD_MEANING = (
    "A roster, Entry ID, byte or unclassified discrepancy was found after export. The "
    "review CSV named here is preserved as an earlier output and is not advertised; do "
    "not review or upload it."
)


def _withhold_at_delivery(outcome, refusal: str, limitations: Iterable[DeliveryLimitation]):
    """A CSV `publish` refused, or one a `V` blocker stops: unlisted, kept on disk, never deleted.

    Either mode. A display-failure record that said the CSV was kept is rewritten
    to say it was withheld, so nothing in the run describes it as listed.
    """

    path = outcome.artifacts.get("bulk_entry_csv")
    digest = outcome.hashes.get("bulk_entry_csv")
    drop = ("bulk_entry_csv", "classic_export_audit", *_READABLE_KEYS)
    record = {
        "stage": "DELIVERY",
        "FILE_VALID": False,
        "RELEASE_DECISION": ReleaseDecision.DO_NOT_UPLOAD.value,
        "blocker": refusal,
        "limitations": [item.code for item in limitations],
        "withheld_artifacts": {"bulk_entry_csv": {"path": path, "sha256": digest}},
        "meaning": _WITHHELD_MEANING,
    }
    export = {**dict(outcome.export or {}), "FILE_VALID": False,
              "problems": [*list((outcome.export or {}).get("problems", [])), refusal]}
    for key in ("bulk_entry_csv", "bulk_entry_sha256", "downstream_audit", "downstream_audit_sha256",
                "readable_review_json", "readable_review_json_sha256", "readable_review_html",
                "readable_review_html_sha256"):
        if key in export:
            export[key] = None
    reports = {**_without(outcome.reports, ("readable_review", "classic_export_audit")),
               "delivery_withheld": record}
    earlier = reports.get("readable_review_failure")
    if isinstance(earlier, Mapping) and "kept_artifacts" in earlier:
        reports["readable_review_failure"] = {
            **_without(earlier, ("kept_artifacts",)),
            "FILE_VALID": False,
            "withheld_artifacts": earlier["kept_artifacts"],
            "withheld_at": "DELIVERY",
            "withheld_by": refusal,
            "meaning": _WITHHELD_MEANING,
        }
    return replace(
        outcome,
        stage="DELIVERY",
        blocked=True,
        artifacts=_without(outcome.artifacts, drop),
        hashes=_without(outcome.hashes, drop),
        reports=reports,
        export=export,
        error=refusal,
    )


def _review_release_truths(
    *,
    outcome,
    truths: Mapping[str, object],
    authorized: tuple[str, ...],
    blockers: Iterable[str],
    extra: Iterable[DeliveryLimitation],
    registry: GateRegistry,
) -> ReleaseTruthsV2:
    """`nfl_release_truths_v2` for a prior_review exit: the four v1 truths, and delivery."""

    policy = derive_release_policy(
        file_valid=bool(truths["FILE_VALID"]),
        evidence_state=ReleaseEvidenceState(str(truths["EVIDENCE_STATE"])),
        model_status=ModelStatus.PRIOR_ONLY,
        certification_basis=CertificationBasis.MODEL_ASSISTED,
    )
    if {key: truths[key] for key in policy.truth_values()} != policy.truth_values():
        raise RuntimeError("the v2 truths would disagree with the v1 truths this run reports")
    has_csv = outcome.file_valid and bool(outcome.artifacts.get("bulk_entry_csv"))
    limitations = [*blocker_limitations(blockers, registry), *extra]
    if outcome.file_valid and not has_csv:
        limitations.append(registry.limitation(
            "PROFILE_WRITES_NO_ENTRY_FILE",
            detail="the run's own review wrote no entry file to hand over; the baseline, when "
                   "it was published, stays the deliverable"))
    delivery = derive_delivery_state(
        file_valid=has_csv,
        authorized_entry_ids=authorized,
        delivered_entry_ids=authorized if has_csv else (),
        limitations=limitations,
    )
    return release_truths_v2(policy, delivery)


# R28 (Session 06): the baseline goes first. `run-slate` builds `nfl baseline`'s
# file straight after intake, inside its own output folder, and publishes it as
# the latest deliverable before the session probe, policy validation, priors,
# weather, roles or any solve. The run's own review is the improvement: it
# replaces the pointer only through `delivery.replace`, and whatever fails after
# the baseline leaves it named. Every result's `DELIVERY_STATE` and
# `release_truths` delivery half describe the file the pointer names.
BASELINE_DIRNAME = "baseline"
BASELINE_PRODUCER = "run-slate:baseline"
C1_PRODUCER = "run-slate:prior_review:CLASSIC_C1"
_V1_KEYS = ("FILE_VALID", "EVIDENCE_STATE", "MODEL_STATUS", "RELEASE_DECISION")


@dataclass(frozen=True)
class _SlateBaseline:
    """What the baseline step did: the build, the pointer it published, and why not."""

    outcome: BaselineOutcome | None
    latest: LatestDeliverable | None
    problems: tuple[str, ...]

    def summary(self) -> dict[str, object]:
        outcome = self.outcome
        truths = outcome.truths if outcome is not None else None
        return {
            "published": self.latest is not None,
            "producer": BASELINE_PRODUCER,
            "objective": BASELINE_OBJECTIVE_VERSION,
            "path": str(outcome.output_path) if outcome is not None and outcome.output_path else None,
            "sha256": outcome.output_sha256 if outcome is not None else None,
            "DELIVERY_STATE": (
                truths.delivery_state.value if truths is not None else DeliveryState.NO_DELIVERABLE.value
            ),
            "delivered_rows": len(truths.delivered_entry_ids) if truths is not None else 0,
            "unfilled_entry_ids": list(truths.unfilled_entry_ids) if truths is not None else [],
            "limitations": [item.code for item in truths.delivery_limitations] if truths is not None else [],
            "report": str(outcome.report_path) if outcome is not None and outcome.report_path else None,
            "wall_seconds": (
                (outcome.report.get("timing") or {}).get("wall_seconds") if outcome is not None else None
            ),
            "problems": list(self.problems),
        }


def _pinned_as_of(args: argparse.Namespace) -> datetime | None:
    """`--as-of` as an aware UTC moment, or None for the live clock."""

    raw = getattr(args, "as_of", None)
    if not raw:
        return None
    moment = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    if moment.tzinfo is None:
        raise ValueError("as_of must be timezone aware")
    return moment.astimezone(timezone.utc)


def _build_run_slate_baseline(
    request: CoworkRunRequest, *, run_id: str, output_root: Path, args: argparse.Namespace,
    budget: Budget | None = None,
) -> _SlateBaseline:
    """The baseline for this run, published as its first deliverable. Never raises.

    Built from the run's immutable snapshots into `<output_root>/baseline/`, with
    the operator's exact exclusions and extra unavailable statuses and the run's
    official `INACTIVE` rows (R32), and published
    under this run's id so the outer handler reads it back. A build that raises,
    delivers nothing or is refused by `publish` is reported; the run goes on.
    Its solve limits come from `budget` (Session 07), never below the floor.
    """

    problems: list[str] = []
    outcome: BaselineOutcome | None = None
    latest: LatestDeliverable | None = None
    per_solve, total = (
        budget.baseline_limits() if budget is not None
        else (DEFAULT_PER_SOLVE_SECONDS, DEFAULT_BUDGET_SECONDS)
    )
    try:
        as_of = _pinned_as_of(args)
        outcome = run_baseline(
            salaries=request.salary_csv or "",
            entries=request.entry_csv or "",
            out_dir=output_root,
            run_id=BASELINE_DIRNAME,
            per_solve_seconds=per_solve,
            budget_seconds=total,
            now=as_of,
            operator_excluded_dk_ids=request.exclude_dk_ids,
            extra_unavailable_statuses=request.unavailable_statuses,
            official_status_csv=request.official_status_csv,  # R32
        )
        if outcome.output_path is not None and outcome.output_sha256 is not None:
            inputs = outcome.report["inputs"]
            latest = publish_deliverable(
                output_root,
                Deliverable(
                    path=outcome.output_path,
                    sha256=outcome.output_sha256,
                    file_kind=BASELINE_OUTPUT_CONTRACT,
                    producer=BASELINE_PRODUCER,
                    run_id=run_id,
                    salary_path=Path(str(inputs["salaries"]["snapshot"])),
                    salary_sha256=str(inputs["salaries"]["sha256"]),
                    entry_path=Path(str(inputs["entries"]["snapshot"])),
                    entry_sha256=str(inputs["entries"]["sha256"]),
                    truths=outcome.truths,
                ),
                now=as_of,
            )
    except DeliveryPointerError as exc:
        problems.extend(exc.problems)
    except Exception as exc:  # noqa: BLE001 - the baseline never stops the run it backs
        problems.append(f"BASELINE_RUN_FAILED:{type(exc).__name__}:{exc}")
    return _SlateBaseline(outcome, latest, tuple(problems))


def _run_release_truths(
    v1: Mapping[str, object],
    *,
    latest: LatestDeliverable | None,
    not_delivered: str | None,
    authorized: tuple[str, ...],
    blockers: Iterable[str],
    registry: GateRegistry,
    extra: Iterable[DeliveryLimitation] = (),
) -> ReleaseTruthsV2:
    """The run's own v1 truths beside the delivery half of the file its pointer names.

    With a pointer, `DELIVERY_STATE`, `delivered_file_valid`, coverage and the
    file's limitations are the pointer's; `not_delivered` adds
    `IMPROVEMENT_NOT_DELIVERED` when that file is the baseline, and `extra` (the
    deadline's limitations, Session 07) follows. Without one, nothing is
    delivered and the run's blockers, which carry the same texts, are the
    limitations.
    """

    head = {key: v1[key] for key in _V1_KEYS}
    if latest is not None:
        record = latest.deliverable.truths.model_dump(mode="json", by_alias=True)
        limitations = list(record["delivery_limitations"])
        if not_delivered is not None and latest.deliverable.producer == BASELINE_PRODUCER:
            limitations.append(
                registry.limitation("IMPROVEMENT_NOT_DELIVERED", detail=not_delivered)
                .model_dump(mode="json", by_alias=True)
            )
        seen = {(item["code"], item["detail"]) for item in limitations}
        limitations.extend(
            item.model_dump(mode="json", by_alias=True) for item in extra
            if (item.code, item.detail) not in seen
        )
        return ReleaseTruthsV2.model_validate({**record, **head, "delivery_limitations": limitations})
    delivery = derive_delivery_state(
        file_valid=False,
        authorized_entry_ids=authorized,
        delivered_entry_ids=(),
        limitations=blocker_limitations(blockers, registry),
    )
    return ReleaseTruthsV2.model_validate({
        **head,
        "DELIVERY_STATE": delivery.delivery_state.value,
        "delivered_file_valid": delivery.delivered_file_valid,
        "delivery_limitations": [item.model_dump(mode="json", by_alias=True)
                                 for item in delivery.delivery_limitations],
        "delivered_entry_ids": list(delivery.delivered_entry_ids),
        "unfilled_entry_ids": list(delivery.unfilled_entry_ids),
    })


def _baseline_next(latest: LatestDeliverable | None, next_action: str) -> str:
    """The handoff names the baseline first whenever it is the file to hand over."""

    if latest is None or latest.deliverable.producer != BASELINE_PRODUCER:
        return next_action
    truths = latest.deliverable.truths
    return (
        f"The baseline {latest.deliverable.path} is this run's deliverable "
        f"(DELIVERY_STATE={truths.delivery_state.value}, {len(truths.delivered_entry_ids)} rows, "
        "salary-ranked from the DraftKings bytes less every excluded or officially inactive "
        "person, PRIOR_ONLY / DO_NOT_UPLOAD); the run's "
        "own review did not replace it. " + next_action
    )


def _improvement_record(
    outcome, *, delivered: LatestDeliverable | None, withheld_by: str | None, reasons: Iterable[str]
) -> dict[str, object]:
    """What became of the run's own review file: `DELIVERED`, `WITHHELD` or `NOT_PRODUCED`."""

    if delivered is not None:
        return {
            "status": "DELIVERED",
            "stage": outcome.stage,
            "path": str(delivered.deliverable.path),
            "sha256": delivered.deliverable.sha256,
            "producer": delivered.deliverable.producer,
            "replaced": delivered.record.get("supersedes"),
            "reasons": [],
        }
    record: dict[str, object] = {
        "status": "WITHHELD" if withheld_by is not None else "NOT_PRODUCED",
        "stage": outcome.stage,
        "path": None,
        "sha256": None,
        "producer": None,
        "replaced": None,
        "reasons": list(dict.fromkeys(str(item) for item in reasons)),
    }
    if withheld_by is not None:
        record["withheld_by"] = withheld_by
    return record


def _not_delivered_detail(improvement: Mapping[str, object]) -> str:
    reasons = [str(item) for item in improvement.get("reasons") or ()]
    return (
        f"the run's own review is {improvement['status']} at stage {improvement['stage']}"
        + (f" ({'; '.join(reasons[:5])})" if reasons else "")
        + "; the delivered file is the salary-ranked baseline built from the DraftKings bytes,"
          " less every excluded or officially inactive person"
    )


def _export_classic_c1_csv(
    outcome, *, request: CoworkRunRequest, output_root: Path, run_id: str
) -> tuple[object, tuple[str, ...]]:
    """C1's own lineups as a review CSV, through the baseline's writer and audit (rung 4).

    C1 writes review JSON and `assignments.csv`. The exact-byte writer the
    baseline uses fills the entries snapshot from that assignment, the
    baseline's independent audit passes the bytes on disk (fresh parses, byte
    audit, shared validator, R29, no DraftKings-unavailable or operator-excluded
    person), and only then is the CSV listed, so `delivery.replace` can put it
    in place of the baseline. Any refusal lists nothing and leaves the baseline.
    """

    source = Path(str(outcome.artifacts.get("assignments") or ""))
    target = output_root / "review" / f"DK_REVIEW_ENTRY_C1_{run_id}.csv"
    if target.exists():
        return outcome, (f"CLASSIC_C1_EXPORT_OUTPUT_EXISTS:{target}",)
    try:
        if not source.is_file() or sha256_file(source) != outcome.hashes.get("assignments"):
            return outcome, (f"CLASSIC_C1_EXPORT_ASSIGNMENT_SHA256_MISMATCH:{source}",)
        status = request.official_status_csv
        if status is not None and sha256_file(status) != outcome.hashes.get("official_status_csv"):
            return outcome, (f"CLASSIC_C1_EXPORT_OFFICIAL_STATUS_CHANGED:{status}",)
        assignments = read_assignment_csv(source, EngineMode.CLASSIC)
        template = parse_entries(request.entry_csv or "")
        raw = write_upload_bytes(template, assignments)
    except (OSError, ValueError) as exc:
        return outcome, (f"CLASSIC_C1_EXPORT_FAILED:{type(exc).__name__}:{exc}",)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    try:
        temporary.write_bytes(raw)
        on_disk = temporary.read_bytes()
        audit_problems = audit_baseline_bytes(
            on_disk,
            salary_path=Path(request.salary_csv or ""),
            entries_path=Path(request.entry_csv or ""),
            assignments=assignments,
            unfilled=(),
            operator_excluded_dk_ids=request.exclude_dk_ids,
            extra_unavailable_statuses=request.unavailable_statuses,
            official_status_csv=request.official_status_csv,
        )
        if audit_problems:
            return outcome, (f"CLASSIC_C1_EXPORT_AUDIT_FAILED:{' | '.join(audit_problems)}",)
        digest = sha256_bytes(on_disk)
        temporary.replace(target)
    except Exception as exc:  # noqa: BLE001 - an export that cannot finish lists nothing
        return outcome, (f"CLASSIC_C1_EXPORT_FAILED:{type(exc).__name__}:{exc}",)
    finally:
        temporary.unlink(missing_ok=True)  # an unaudited copy never outlives the step
    if sha256_file(target) != digest:
        target.unlink(missing_ok=True)
        return outcome, (f"CLASSIC_C1_EXPORT_POST_WRITE_HASH_MISMATCH:{target}",)
    export = {
        **dict(outcome.export or {}),
        "bulk_entry_csv": str(target),
        "bulk_entry_sha256": digest,
        "c1_export": {
            "writer": "lineups.write_upload_bytes",
            "audit": "baseline.audit_baseline_bytes",
            "assignments": str(source),
            "assignments_sha256": outcome.hashes.get("assignments"),
            "status": "PASS",
        },
    }
    return replace(
        outcome,
        artifacts={**outcome.artifacts, "bulk_entry_csv": str(target)},
        hashes={**outcome.hashes, "bulk_entry_csv": digest},
        export=export,
    ), ()


def _run_prior_review_profile(
    *,
    args: argparse.Namespace,
    request: CoworkRunRequest,
    run_id: str,
    slate,
    entries,
    output_root: Path,
    report_path: Path,
    request_path: Path,
    doctor_report,
    unclassified,
    intake: Mapping[str, object],
    reported_blockers: list[str],
    portfolio_policy=None,
    portfolio_policy_source_path: str | None = None,
    portfolio_policy_source_sha256: str | None = None,
    portfolio_policy_normalized_path: str | None = None,
    portfolio_policy_normalized_sha256: str | None = None,
    policy_summary: Mapping[str, object] | None = None,
    baseline: _SlateBaseline | None = None,
    budget: Budget | None = None,
) -> int:
    """Drive the prior-only review chain from one gated Cowork command.

    This path certifies nothing. `MODEL_STATUS` is pinned to `PRIOR_ONLY` and
    `RELEASE_DECISION` to `DO_NOT_UPLOAD` here, not derived from an argument, and
    the derived policy is re-asserted before anything is written. There is no
    flag or profile value that can make this profile emit a certified package,
    and a generated assignment is never routed into the manual-guardrail path.

    The run's review is the improvement on `baseline` (Session 06): a CSV it
    lists replaces the pointer only through `delivery.replace`, and a review
    that blocks, is withheld or writes no file leaves the baseline delivered.
    """

    as_of = _pinned_as_of(args)  # None: the live profile advances the clock itself

    # The review runs inside the run's budget (Session 07): its solves take their
    # limits from the window, and it stops before selection when none is left.
    # Every evidence fetch it reaches reads the same budget (Session 07b); the
    # session probe is a subprocess with its own allowance, so only this is wrapped.
    review_started = budget.elapsed() if budget is not None else 0.0
    with activated(budget):
        outcome = run_prior_review(
            salary_csv=request.salary_csv or "",
            entry_csv=request.entry_csv or "",
            label=request.label,
            as_of=as_of,
            run_root=DEFAULT_RUNS_DIR / run_id / "prior_review",
            output_root=output_root,
            season=request.season,
            prior_season=request.prior_season,
            prior_package_dir=request.prior_package_dir,
            build_priors=request.build_priors,
            weather_state=request.weather_state,
            weather_source_uri=request.weather_source_uri,
            weather_observed_at=request.weather_observed_at,
            weather_evidence_json=request.weather_evidence_json,
            lineup_count=request.lineup_count,
            max_person_overlap=request.max_person_overlap,
            operator_excluded_dk_ids=request.exclude_dk_ids,
            extra_unavailable_statuses=request.unavailable_statuses,
            extra_available_statuses=request.available_statuses,
            official_status_csv=request.official_status_csv,
            role_evidence_json=request.role_evidence_json,
            offensive_role_evidence_json=request.offensive_role_evidence_json,
            qb_depth_role_evidence_json=request.qb_depth_role_evidence_json,
            portfolio_policy=portfolio_policy,
            portfolio_policy_source_path=portfolio_policy_source_path,
            portfolio_policy_source_sha256=portfolio_policy_source_sha256,
            portfolio_policy_normalized_path=portfolio_policy_normalized_path,
            portfolio_policy_normalized_sha256=portfolio_policy_normalized_sha256,
            budget=budget,
        )
    if budget is not None:
        budget.record("review", started_after=review_started, elapsed=budget.elapsed() - review_started)
        budget.finished_late("review")
        _record_bank_rate(budget, outcome, portfolio_policy, run_id=run_id, slate=slate, entries=entries)
    finish_started = budget.elapsed() if budget is not None else 0.0

    blockers = list(reported_blockers)
    blockers[0:0] = list(outcome.blockers)
    if budget is not None:
        blockers.extend(
            deadline_text for deadline_text in budget.blocker_texts() if deadline_text not in blockers
        )
    next_action = (
        "Review every exact Entry ID and named limitation, refresh missing or stale "
        "evidence, and rerun before any separately certified manual workflow."
        if outcome.file_valid
        else "Resolve every named blocker above, then rerun the same command."
    )
    truths = _blocked_truth_values(
        file_valid=outcome.file_valid,
        evidence_state=(
            ReleaseEvidenceState(
                str((outcome.export or {}).get("EVIDENCE_STATE", "UNKNOWN"))
            )
            if slate.mode is EngineMode.CLASSIC
            else ReleaseEvidenceState.UNKNOWN
        ),
        model_status=ModelStatus.PRIOR_ONLY,
        certification_basis=CertificationBasis.MODEL_ASSISTED,
    )
    if (
        truths["MODEL_STATUS"] != ModelStatus.PRIOR_ONLY.value
        or truths["RELEASE_DECISION"] != ReleaseDecision.DO_NOT_UPLOAD.value
    ):
        raise RuntimeError(
            "prior_review derived a release decision other than DO_NOT_UPLOAD; "
            "refusing to write anything"
        )

    registry = load_gate_registry()
    authorized_ids = tuple(item.entry_id for item in entries.authorizations)
    readable_review = None
    readable_failed = False
    withheld_by: str | None = None  # why a CSV this review produced is not listed
    review_limitations: list[DeliveryLimitation] = []
    if (
        outcome.file_valid
        and slate.mode is EngineMode.CLASSIC
        and "classic_export_audit" in outcome.artifacts
    ):
        # C3 either recorded a readable failure itself (its export and audit kept,
        # the blocker already in `outcome.blockers`), or its readable files are
        # re-hashed here.
        discrepancy = (outcome.export or {}).get("readable_review_failure")
        display_blocker = f"CLASSIC_C3_READABLE_REVIEW_FAILED:{discrepancy}"
        if not discrepancy:
            try:
                readable_review = ReadableReviewArtifacts(
                    data=dict(outcome.reports["readable_review"]),
                    json_path=outcome.artifacts["readable_review_json"],
                    json_sha256=outcome.hashes["readable_review_json"],
                    html_path=outcome.artifacts["readable_review_html"],
                    html_sha256=outcome.hashes["readable_review_html"],
                )
                readable_problems = verify_readable_review_artifacts(
                    json_path=readable_review.json_path,
                    json_sha256=readable_review.json_sha256,
                    html_path=readable_review.html_path,
                    html_sha256=readable_review.html_sha256,
                )
                if readable_problems:
                    raise ReadableReviewError(";".join(readable_problems))
            except (KeyError, OSError, TypeError, ValueError) as exc:
                readable_review = None
                discrepancy = _discrepancy_text(exc)
                display_blocker = f"CLASSIC_C3_READABLE_REVIEW_FAILED:{type(exc).__name__}:{exc}"
                blockers.insert(0, display_blocker)
                outcome = replace(outcome, blockers=(display_blocker, *outcome.blockers))
        if discrepancy:
            readable_failed = True
            review_limitations = list(discrepancy_limitations(str(discrepancy), registry))
            if withholds(review_limitations):
                withheld_by = display_blocker
                outcome = _withhold_classic_review_csv(outcome, display_blocker)
                truths = _blocked_truth_values(
                    file_valid=False,
                    evidence_state=ReleaseEvidenceState.UNKNOWN,
                    model_status=ModelStatus.PRIOR_ONLY,
                    certification_basis=CertificationBasis.MODEL_ASSISTED,
                )
                next_action = "Resolve the named Classic C3 readable-review discrepancy and rerun."
            else:
                outcome = _keep_classic_review_csv(outcome, display_blocker)
                next_action = _PRESENTATION_NEXT
    if outcome.file_valid and slate.mode is EngineMode.SHOWDOWN:
        try:
            readable_review = create_readable_review(
                slate=slate,
                template=entries,
                salary_path=request.salary_csv or "",
                entry_path=request.entry_csv or "",
                assignment_path=outcome.artifacts["assignments"],
                exported_path=outcome.artifacts["bulk_entry_csv"],
                artifacts=outcome.artifacts,
                expected_hashes=outcome.hashes,
                reports=outcome.reports,
                truth_values=truths,
                blockers=tuple(blockers),
                next_action=next_action,
                output_dir=output_root / "review",
                package_root=PROJECT_ROOT,
            )
            readable_problems = verify_readable_review_artifacts(
                json_path=readable_review.json_path,
                json_sha256=readable_review.json_sha256,
                html_path=readable_review.html_path,
                html_sha256=readable_review.html_sha256,
            )
            if readable_problems:
                raise ReadableReviewError(";".join(readable_problems))
            outcome = replace(
                outcome,
                artifacts={
                    **outcome.artifacts,
                    "readable_review_json": readable_review.json_path,
                    "readable_review_html": readable_review.html_path,
                },
                hashes={
                    **outcome.hashes,
                    "readable_review_json": readable_review.json_sha256,
                    "readable_review_html": readable_review.html_sha256,
                },
                reports={
                    **outcome.reports,
                    "readable_review": readable_review.data,
                },
            )
        except (KeyError, OSError, ValueError) as exc:
            readable_review = None
            readable_failed = True
            display_blocker = f"READABLE_REVIEW_FAILED:{type(exc).__name__}:{exc}"
            blockers.insert(0, display_blocker)
            review_limitations = list(discrepancy_limitations(_discrepancy_text(exc), registry))
            withheld = withholds(review_limitations)
            # Withheld, the CSV stays on disk as a preserved earlier output that
            # neither index names; kept, it stays in both (R28, Session 05).
            outcome = _showdown_review_csv_record(
                replace(outcome, blockers=(display_blocker, *outcome.blockers)),
                display_blocker,
                withheld=withheld,
                limitations=review_limitations,
            )
            if withheld:
                withheld_by = display_blocker
                truths = _blocked_truth_values(
                    file_valid=False,
                    evidence_state=ReleaseEvidenceState.UNKNOWN,
                    model_status=ModelStatus.PRIOR_ONLY,
                    certification_basis=CertificationBasis.MODEL_ASSISTED,
                )
                next_action = "Resolve the named readable-review discrepancy and rerun from stable exact artifacts."
            else:
                next_action = _PRESENTATION_NEXT

    # Rung 4 (R28, Session 06): C1 exports its own lineups through the
    # baseline's writer and audit, so it ends with a CSV; a refusal leaves the
    # baseline as the deliverable. C2/C3 keep their own audited export.
    c1_export_problems: tuple[str, ...] = ()
    if (
        outcome.file_valid
        and slate.mode is EngineMode.CLASSIC
        and portfolio_policy is None
        and "classic_export_audit" not in outcome.artifacts
        and not outcome.artifacts.get("bulk_entry_csv")
    ):
        outcome, c1_export_problems = _export_classic_c1_csv(
            outcome, request=request, output_root=output_root, run_id=run_id
        )
        blockers[0:0] = list(c1_export_problems)

    # R28 (Session 09): each game the model ran without a weather observation
    # travels with the file it shaped, by name.
    if outcome.file_valid:
        for weather_code in reversed(list(outcome.reports.get("weather_unobserved") or ())):
            blockers.insert(0, str(weather_code))
    selection_report = outcome.reports.get("selection")
    if isinstance(selection_report, Mapping):
        coverage = selection_report.get("official_status_coverage")
        if isinstance(coverage, Mapping) and coverage.get("selected_without_row"):
            missing = list(coverage["selected_without_row"])
            blockers.insert(
                0,
                "OFFICIAL_STATUS_INCOMPLETE_FOR_SELECTED: "
                f"{len(missing)} selected people have no current exact-ID row in the "
                f"supplied official status file: {missing}; a supplied file never implies "
                "ACTIVE for anyone it omits",
            )
        selector = selection_report.get("selection")
        # R28 absorbs the P1 stop (Session 09): each unresolved role change the
        # market disagrees with left the pool, and travels with the file by name.
        offensive = selector.get("offensive_roles") if isinstance(selector, Mapping) else None
        if isinstance(offensive, Mapping):
            for code in reversed(list(offensive.get("material_role_change_exclusions") or ())):
                blockers.insert(0, str(code))
        if isinstance(selector, Mapping) and selector.get("non_optimal_lineups"):
            blockers.insert(
                0,
                "SOLVER_TIME_LIMIT_ACCEPTED_LINEUPS: lineups "
                f"{list(selector['non_optimal_lineups'])} were accepted from a time-limited "
                "solve and are feasible but not proven optimal for the prior objective",
            )
        # C2 and SD3 (Session 08): a bank stopped at a limit that kept enough to
        # select from, and a joint selection a limit stopped with a validated
        # incumbent, each travel with the file. Neither is a claim of optimality.
        policy_record = selector.get("portfolio_policy") if isinstance(selector, Mapping) else None
        if isinstance(policy_record, Mapping):
            bank_record = policy_record.get("candidate_bank")
            solve_record = policy_record.get("solve")
            if isinstance(bank_record, Mapping) and bank_record.get("status") in {
                "BOUNDED_TIME_LIMIT_STOP", "BOUNDED_SEARCH_LIMIT_STOP",
            }:
                blockers.insert(
                    0,
                    "CANDIDATE_BANK_STOPPED_AT_LIMIT: the candidate bank stopped at its "
                    f"{bank_record.get('status')} after "
                    f"{bank_record.get('produced_candidates')} of "
                    f"{bank_record.get('requested_candidates')} candidates; it held the entry "
                    "count and a policy-feasible witness, and the portfolio was chosen from it",
                )
            if isinstance(solve_record, Mapping) and solve_record.get("status") == LIMIT_INCUMBENT_STATUS:
                blockers.insert(
                    0,
                    "PORTFOLIO_SELECTION_LIMIT_INCUMBENT: the joint selection stopped at "
                    f"{solve_record.get('model_status')} with a validated incumbent "
                    f"(from {solve_record.get('incumbent_source') or 'JOINT_SOLVE'}, "
                    f"gap {solve_record.get('mip_gap')}, {solve_record.get('node_count')} nodes); "
                    "its lineups were accepted and are feasible under every policy bound but "
                    "not proven optimal for the prior objective over the bank",
                )

    # The delivery truth, then the pointer. A kept CSV is published only after
    # `delivery.publish` revalidates it, or put in place of the baseline only
    # through `delivery.replace` (same inputs, equal or better coverage, the
    # same revalidation); a refusal, or a `V` gate among the blockers, withholds
    # it exactly as a `V` display discrepancy would, and the baseline stays.
    release_truths = _review_release_truths(
        outcome=outcome, truths=truths, authorized=authorized_ids, blockers=blockers,
        extra=review_limitations, registry=registry,
    )
    latest: LatestDeliverable | None = None
    if outcome.file_valid and outcome.artifacts.get("bulk_entry_csv"):
        if release_truths.delivery_state is not DeliveryState.NO_DELIVERABLE:
            write = (
                replace_deliverable if (output_root / POINTER_NAME).exists() else publish_deliverable
            )
            try:
                latest = write(
                    output_root,
                    Deliverable(
                        path=Path(outcome.artifacts["bulk_entry_csv"]),
                        sha256=outcome.hashes["bulk_entry_csv"],
                        file_kind="DK_REVIEW_ENTRY_CSV",
                        producer=(
                            C1_PRODUCER
                            if "c1_export" in (outcome.export or {})
                            else f"run-slate:prior_review:{slate.mode.value}"
                        ),
                        run_id=run_id,
                        salary_path=Path(request.salary_csv or ""),
                        salary_sha256=outcome.hashes["salary_csv"],
                        entry_path=Path(request.entry_csv or ""),
                        entry_sha256=outcome.hashes["entry_csv"],
                        truths=release_truths,
                    ),
                    now=as_of,
                )
            except DeliveryPointerError as exc:
                blockers[0:0] = list(exc.problems)
        if latest is None:
            refusal = next(
                (item.detail for item in (
                    *blocker_limitations(blockers, registry), *review_limitations
                ) if item.gate_class is GateClass.V),
                "FILE_VALIDATION_INCOMPLETE",
            )
            withheld_by = refusal
            outcome = _withhold_at_delivery(outcome, refusal, blocker_limitations(blockers, registry))
            readable_review = None
            truths = _blocked_truth_values(
                file_valid=False,
                evidence_state=ReleaseEvidenceState.UNKNOWN,
                model_status=ModelStatus.PRIOR_ONLY,
                certification_basis=CertificationBasis.MODEL_ASSISTED,
            )
            next_action = "Resolve every named integrity blocker above, then rerun the same command."
            release_truths = _review_release_truths(
                outcome=outcome, truths=truths, authorized=authorized_ids, blockers=blockers,
                extra=review_limitations, registry=registry,
            )
        else:
            outcome = replace(
                outcome,
                artifacts={**outcome.artifacts, "latest_deliverable": str(latest.pointer_path)},
                hashes={**outcome.hashes, "latest_deliverable": latest.pointer_sha256},
            )
    improvement_latest = latest
    # What the pointer names now: the improvement just written, the baseline it
    # did not replace, or nothing. The result describes that file.
    latest, latest_problems = _read_run_pointer(output_root, run_id)
    if improvement_latest is not None and latest is None:
        # Written, then no longer revalidating: withheld like any other refusal.
        withheld_by = latest_problems[0] if latest_problems else "DELIVERABLE_REVALIDATION_FAILED"
        blockers[0:0] = list(latest_problems)
        outcome = _withhold_at_delivery(outcome, withheld_by, blocker_limitations(blockers, registry))
        readable_review = None
        truths = _blocked_truth_values(
            file_valid=False,
            evidence_state=ReleaseEvidenceState.UNKNOWN,
            model_status=ModelStatus.PRIOR_ONLY,
            certification_basis=CertificationBasis.MODEL_ASSISTED,
        )
        next_action = "Resolve every named integrity blocker above, then rerun the same command."
        improvement_latest = None
        if baseline is not None and baseline.latest is not None:
            # The baseline still on disk takes the pointer back: `replace` lets a
            # file that revalidates displace one that no longer does.
            try:
                replace_deliverable(output_root, baseline.latest.deliverable, now=as_of)
            except DeliveryPointerError as exc:
                latest_problems = (*latest_problems, *exc.problems)
            restored, restore_problems = _read_run_pointer(output_root, run_id)
            latest, latest_problems = restored, (*latest_problems, *restore_problems)
    improvement = _improvement_record(
        outcome,
        delivered=improvement_latest,
        withheld_by=withheld_by,
        reasons=(
            [item.code for item in (*blocker_limitations(blockers, registry), *review_limitations)
             if item.gate_class is GateClass.V]
            if withheld_by is not None
            else list(c1_export_problems or outcome.blockers)
        ),
    )
    if latest is not None and improvement_latest is None:
        release_truths = _run_release_truths(
            truths, latest=latest, not_delivered=_not_delivered_detail(improvement),
            authorized=authorized_ids, blockers=blockers, registry=registry,
            extra=budget.limitations(registry) if budget is not None else (),
        )
    elif latest is None:
        # Nothing to hand over: the review's own record, plus why no baseline backs it.
        release_truths = _review_release_truths(
            outcome=outcome, truths=truths, authorized=authorized_ids,
            blockers=[*blockers, *latest_problems, *(baseline.problems if baseline is not None else ())],
            extra=review_limitations, registry=registry,
        )
    next_action = _baseline_next(latest, next_action)
    failure_record = outcome.reports.get("readable_review_failure")
    if slate.mode is EngineMode.SHOWDOWN and isinstance(failure_record, Mapping):
        # Written once the delivery decision is final, so the marker never says
        # "kept" about a CSV that revalidation then withheld.
        try:
            _write_json(
                DEFAULT_RUNS_DIR / run_id / "prior_review" / "READABLE_REVIEW_FAILED.json",
                failure_record,
            )
            _write_json(output_root / "review" / "READABLE_REVIEW_FAILED.json", failure_record)
        except OSError:
            pass
    review_path = output_root / f"NFL_DFS_Cowork_Review_{run_id}.xlsx"
    create_cowork_status_workbook(
        output_path=review_path,
        run_values=_cowork_run_control_values(request),
        blockers=blockers,
        report_path=report_path,
        truth_values=truths,
        readable_review=readable_review.data if readable_review is not None else None,
        review_csv_path=latest.deliverable.path if latest is not None else None,
        review_csv_sha256=latest.deliverable.sha256 if latest is not None else None,
    )
    review_workbook_sha256 = sha256_file(review_path)
    if budget is not None:
        budget.record("finish", started_after=finish_started, elapsed=budget.elapsed() - finish_started)
    result = {
        "run_id": run_id,
        "status": "DO_NOT_UPLOAD",
        **truths,
        "stage": (
            (
                (
                    "PRIOR_ONLY_CLASSIC_C3_REVIEW_EXPORT"
                    if "classic_export_audit" in outcome.artifacts
                    else "PRIOR_ONLY_CLASSIC_REVIEW_ARTIFACTS"
                )
                if slate.mode is EngineMode.CLASSIC
                else "PRIOR_ONLY_REVIEW_EXPORT"
            )
            + ("_READABLE_REVIEW_FAILED" if readable_failed else "")
            if outcome.file_valid
            else f"PRIOR_REVIEW_{outcome.stage}_BLOCKED"
        ),
        "mode": slate.mode.value,
        "authorized_entries": len(entries.authorizations),
        "contest_ids": sorted({entry.contest_id for entry in entries.authorizations}),
        "entry_fees": sorted({entry.entry_fee for entry in entries.authorizations}),
        "request": str(request_path),
        "review_workbook": str(review_path),
        "review_workbook_sha256": review_workbook_sha256,
        "blockers": blockers,
        "unclassified_csvs": [str(path) for path in unclassified],
        "input_hashes": intake["hashes"],
        "superseded_request_inputs": getattr(args, "_cowork_superseded_inputs", {}),
        "doctor": json.loads(doctor_report.to_json()),
        **outcome.as_report(),
        "DELIVERY_STATE": release_truths.delivery_state.value,
        "release_truths": release_truths.model_dump(mode="json", by_alias=True),
        "latest_deliverable": latest.summary() if latest is not None else None,
        "latest_deliverable_problems": list(latest_problems),
        "baseline": baseline.summary() if baseline is not None else None,
        "improvement": improvement,
        "deadline": budget.as_record() if budget is not None else None,
        "next": next_action,
        "meaning": (
            "Legal and byte-audited, never certified. This profile reads no payout "
            "table or field size; supplied activity reports constrain selection. It makes no EV, ROI, "
            "win probability, cash probability, ownership or edge claim. "
            + (
                "Classic C3 may emit an independently audited exact-template "
                "DK_REVIEW_ENTRY CSV, but never a DK_UPLOAD package."
                if "classic_export_audit" in outcome.artifacts
                else "Classic C1 writes review JSON and exports its own lineups through the "
                "baseline's writer and audit as an exact-template DK_REVIEW_ENTRY CSV, "
                "never a DK_UPLOAD package."
                if slate.mode is EngineMode.CLASSIC
                else "Showdown may emit a byte-audited exact-template DK_REVIEW_ENTRY CSV, "
                "never a DK_UPLOAD package."
            )
        ),
    }
    if policy_summary is not None:
        selector_policy = (
            dict(outcome.reports.get("selection", {}))
            .get("selection", {})
            .get("portfolio_policy")
        )
        audit_report = outcome.reports.get(
            "classic_portfolio_audit"
            if slate.mode is EngineMode.CLASSIC
            else "portfolio_policy_audit"
        )
        enforced_and_audited = bool(
            outcome.file_valid
            and isinstance(selector_policy, Mapping)
            and selector_policy.get("enforcement_status") == "PASS"
            and isinstance(audit_report, Mapping)
            and audit_report.get("status") == "PASS"
        )
        result["portfolio_policy"] = {
            **dict(policy_summary),
            "enforcement_status": (
                "ENFORCED_AND_INDEPENDENTLY_AUDITED"
                if enforced_and_audited
                else "NOT_ENFORCED_AND_AUDITED"
            ),
            "selector": selector_policy,
            "independent_audit": audit_report,
        }
    _write_json(report_path, result)
    _print_json(result)
    # Exit codes keep their meaning (Session 06): 0 when the run's own review
    # completed, 2 when it did not. A baseline in place never turns one into the
    # other; `DELIVERY_STATE` and `latest_deliverable` say whether a file ships.
    return 0 if outcome.file_valid and not readable_failed and not c1_export_problems and (
        slate.mode is EngineMode.CLASSIC or readable_review is not None
    ) else 2


HOST_RATES_FILENAME = "host_candidate_rates.json"


def _record_bank_rate(budget: Budget, outcome, portfolio_policy, *, run_id: str, slate, entries) -> None:
    """This host's candidate rate from a Classic C2 bank, into the run's runs folder.

    `data/runs/` is per machine and never committed, which is what a per-host
    measurement needs; Session 07b's policy generator reads it. Never raises:
    a ledger it cannot read or write is reported and left as it is.
    """

    limits = getattr(portfolio_policy, "search_limits", None)
    if slate.mode is not EngineMode.CLASSIC or limits is None:
        return
    try:
        observed = bank_rate_observation(
            outcome.reports, outcome.blockers,
            declared_bank_seconds=limits.candidate_total_milliseconds / 1000.0,
        )
        if observed is None:
            return
        candidates, seconds, basis = observed
        budget.candidate_rate = record_candidate_rate(
            DEFAULT_RUNS_DIR / HOST_RATES_FILENAME, mode=slate.mode.value, candidates=candidates,
            seconds=seconds, basis=basis, run_id=run_id, measured_at=datetime.now(timezone.utc),
            pool_people=len({player.underlying_id for player in slate.players}),
            entries=len(entries.authorizations),
        )
    except Exception as exc:  # noqa: BLE001 - a rate never costs the review it measured
        budget.candidate_rate = {"recorded": False, "detail": f"{type(exc).__name__}:{exc}"}


def _command_cowork_run(args: argparse.Namespace) -> int:
    command_started = time.monotonic()
    request_roots: list[Path] = [(PROJECT_ROOT / "data").resolve()]
    if args.input_dir:
        request_roots.append(Path(args.input_dir).resolve())
    # An operator who names a frozen prior package directory on the command line
    # has authorized that exact path, the same way --salaries and --entries work.
    if getattr(args, "prior_package_dir", None):
        request_roots.append(Path(args.prior_package_dir).resolve())
    # A role manifest is a small package: its own immutable JSON plus the
    # adjacent content-addressed `sources/` captures it binds. Authorize only
    # that explicitly named package directory.
    if getattr(args, "role_evidence_json", None):
        request_roots.append(Path(args.role_evidence_json).resolve().parent)
    if getattr(args, "offensive_role_evidence_json", None):
        request_roots.append(Path(args.offensive_role_evidence_json).resolve().parent)
    if getattr(args, "qb_depth_role_evidence_json", None):
        request_roots.append(Path(args.qb_depth_role_evidence_json).resolve().parent)
    if getattr(args, "portfolio_policy_json", None):
        request_roots.append(Path(args.portfolio_policy_json).resolve().parent)
    if getattr(args, "official_status_csv", None):
        request_roots.append(Path(args.official_status_csv).resolve().parent)
    if getattr(args, "weather_evidence_json", None):
        request_roots.append(Path(args.weather_evidence_json).resolve().parent)
    if args.request:
        request_source = Path(args.request).resolve()
        possible_run_root = request_source.parent
        if (
            possible_run_root.parent == DEFAULT_RUNS_DIR.resolve()
            and RUN_ID_PATTERN.fullmatch(possible_run_root.name)
        ):
            request_roots.append(possible_run_root)
        confine_request_path(
            request_source,
            allowed_roots=request_roots,
            field_name="request",
        )
    requested = (
        CoworkRunRequest.from_json(args.request, allowed_roots=request_roots)
        if args.request
        else CoworkRunRequest(label=args.label or "slate")
    )
    if args.label:
        requested = replace(requested, label=args.label)
    overrides: dict[str, object] = {}
    for flag, field_name in (
        ("profile", "profile"),
        ("prior_package_dir", "prior_package_dir"),
        ("season", "season"),
        ("prior_season", "prior_season"),
        ("weather_state", "weather_state"),
        ("weather_source_uri", "weather_source_uri"),
        ("weather_observed_at", "weather_observed_at"),
        ("weather_evidence_json", "weather_evidence_json"),
        ("role_evidence_json", "role_evidence_json"),
        ("offensive_role_evidence_json", "offensive_role_evidence_json"),
        ("qb_depth_role_evidence_json", "qb_depth_role_evidence_json"),
        ("portfolio_policy_json", "portfolio_policy_json"),
        ("official_status_csv", "official_status_csv"),
        ("lineup_count", "lineup_count"),
        ("max_person_overlap", "max_person_overlap"),
        ("exclude", "exclude_dk_ids"),
        ("unavailable_status", "unavailable_statuses"),
        ("available_status", "available_statuses"),
        ("delivery_deadline_utc", "delivery_deadline_utc"),
    ):
        value = getattr(args, flag, None)
        if value not in (None, ""):
            if flag == "prior_package_dir":
                value = str(confine_request_path(
                    value, base_dir=Path.cwd(), allowed_roots=request_roots,
                    field_name=flag,
                ))
            if field_name in LIST_MERGE_REQUEST_FIELDS:
                # A follow-up `--exclude` on a reloaded request adds to the
                # exclusions the request already carries; it does not replace
                # them. Replacing silently re-admitted every earlier fade on the
                # rerun that was meant to add one more.
                existing = list(getattr(requested, field_name) or ())
                value = list(dict.fromkeys([*existing, *[str(item) for item in value]]))
            overrides[field_name] = value
    if getattr(args, "build_priors", False):
        overrides["build_priors"] = True
    if overrides:
        requested = CoworkRunRequest.from_mapping(
            {
                **requested.to_dict(),
                **overrides,
                # A flag for a field a later version added makes this run's
                # request that version; the file it was loaded from is untouched.
                "schema_version": request_version_for(requested.schema_version, overrides),
            },
            allowed_roots=request_roots,
            allowed_files=tuple(
                Path(path).resolve()
                for path in (args.salaries, args.entries)
                if path
            ),
        )
    run_id = _resolved_run_id(args.run_id, requested.label)
    if (DEFAULT_RUNS_DIR / run_id).exists():
        # Refuse before anything is written. The failure handler below only
        # writes into a run folder this invocation created, so an earlier run's
        # record is never rewritten by a later command that reused its id.
        raise ValueError(
            "RUN_ID_COLLISION: run_id already exists and immutable run records are "
            f"never overwritten: {run_id}; choose a new --run-id or omit it"
        )
    args._resolved_cowork_run_id = run_id
    request_roots.append((DEFAULT_RUNS_DIR / run_id).resolve())
    if requested.input_dir:
        request_roots.append(Path(requested.input_dir).resolve())
    request, unclassified = resolve_request_inputs(
        requested,
        input_dir=args.input_dir,
        salary_csv=args.salaries,
        entry_csv=args.entries,
        allowed_roots=request_roots,
    )
    superseded_inputs = {
        name: {"request": previous, "attached": current}
        for name in PATH_FIELDS
        if (previous := getattr(requested, name)) not in (None, "")
        and (current := getattr(request, name)) not in (None, "")
        and str(Path(str(previous)).resolve()) != str(Path(str(current)).resolve())
    }
    args._cowork_superseded_inputs = superseded_inputs
    ContestObjective(request.objective)
    source_paths = [
        value
        for name in PATH_FIELDS
        if (value := getattr(request, name)) is not None
    ]
    intake, slate, entries = _intake(
        salaries=request.salary_csv or "",
        entries_path=request.entry_csv or "",
        run_id=run_id,
        snapshot_paths=source_paths,
        snapshot_allowed_roots=request_roots,
        snapshot_allowed_files=tuple(
            Path(path).resolve()
            for path in (args.salaries, args.entries)
            if path
        ),
    )
    snapshotted = _snapshot_cowork_request(request, run_id, intake["hashes"])
    request_path = DEFAULT_RUNS_DIR / run_id / "run_request.json"
    _write_json(request_path, snapshotted.to_dict())
    output_root = Path(args.output_dir).resolve() / run_id
    output_root.mkdir(parents=True, exist_ok=True)
    report_path = output_root / "cowork_run.json"
    # R31 (Session 07): one budget for the whole run, from the request's deadline
    # or the earliest lock minus 5 minutes; every stage below takes its allowance.
    try:
        budget = Budget.build(
            slate.games,
            requested_deadline=snapshotted.delivery_deadline_utc,
            as_of=_pinned_as_of(args),
            stop_minutes=runtime_stop_minutes(_load_config("runtime.json")),
        )
    except Exception:  # noqa: BLE001 - re-raised below, after the baseline
        # A clock or runtime setting the budget cannot read (malformed, missing,
        # unreadable) never costs the baseline: it is built on its fixed
        # defaults, then the run fails by name.
        args._run_slate_baseline = _build_run_slate_baseline(
            snapshotted, run_id=run_id, output_root=output_root, args=args
        )
        raise
    budget.record("intake", started_after=command_started - budget.clock_started,
                  elapsed=budget.clock_started - command_started)
    args._run_slate_budget = budget
    # R28 (Session 06): the baseline first, from the DraftKings bytes alone and
    # before anything that needs the network, a policy or a model.
    with budget.stage("baseline"):
        baseline = _build_run_slate_baseline(
            snapshotted, run_id=run_id, output_root=output_root, args=args, budget=budget
        )
    args._run_slate_baseline = baseline
    # Session capability, before the run spends its window discovering it, for
    # as long as the window allows.
    if not getattr(args, "no_session_probe", False):
        # A probe the environment switched off takes no allowance, so none is named.
        switched_off = os.environ.get(SESSION_PROBE_SKIP_ENV) == "1"
        probe_seconds = None if switched_off else budget.allowance(
            "session_probe", default=SESSION_PROBE_TIMEOUT_SECONDS,
            share=PROBE_SHARE, minimum=PROBE_MINIMUM_SECONDS,
        )
        if switched_off or probe_seconds is not None:
            with budget.stage("session_probe") as probe_stage:
                probe_report = _session_probe(
                    request.salary_csv, timeout=probe_seconds or SESSION_PROBE_TIMEOUT_SECONDS
                )
                if probe_report is None:
                    probe_stage.outcome = "SKIPPED"
            if probe_report is not None:
                _write_json(DEFAULT_RUNS_DIR / run_id / "session_probe.json", probe_report)
                _announce_session_probe(probe_report)
    policy_started = budget.elapsed()
    policy_summary: dict[str, object] | None = None
    policy_blockers: list[str] = []
    validated_policy = None
    normalized_path: Path | None = None
    expected_policy_sha256: str | None = None
    if snapshotted.portfolio_policy_json is not None:
        by_dk_id = {player.dk_id: player for player in slate.players}
        official_exclusions: tuple[str, ...] = ()
        if snapshotted.official_status_csv is not None:
            try:
                official_snapshot = parse_official_inactive_snapshot(
                    snapshotted.official_status_csv, slate.players
                )
            except EvidenceError as exc:
                policy_blockers.append(
                    "PORTFOLIO_POLICY_OFFICIAL_STATUS_INVALID: "
                    f"{exc}; next action: repair the exact-ID official activity snapshot"
                )
            else:
                if official_snapshot.problems:
                    policy_blockers.append(
                        "PORTFOLIO_POLICY_OFFICIAL_STATUS_INVALID: "
                        f"{';'.join(official_snapshot.problems)}; next action: repair the exact-ID "
                        "official activity snapshot"
                    )
                official_exclusions = tuple(
                    dk_id
                    for dk_id, status in official_snapshot.statuses.items()
                    if status == "INACTIVE"
                )
        all_request_exclusions = tuple(snapshotted.exclude_dk_ids) + official_exclusions
        unknown_exclusions = sorted(
            set(all_request_exclusions).difference(by_dk_id)
        )
        if unknown_exclusions:
            policy_blockers.append(
                "PORTFOLIO_POLICY_EXTERNAL_EXCLUSION_DK_ID_UNKNOWN: "
                f"request exclusions are outside the salary pool {unknown_exclusions}; "
                "next action: use exact current salary CPT/FLEX IDs"
            )
        external_people: tuple[str, ...] = ()
        try:
            participation = build_participation_contract(
                slate,
                operator_excluded_dk_ids=all_request_exclusions,
                extra_unavailable_statuses=snapshotted.unavailable_statuses,
                extra_available_statuses=snapshotted.available_statuses,
            )
        except ParticipationError as exc:
            policy_blockers.append(
                "PORTFOLIO_POLICY_PARTICIPATION_INVALID: "
                f"{exc}; next action: reconcile status and exclusion inputs to the current salary file"
            )
        else:
            external_people = tuple(
                sorted(
                    set(participation.unavailable_people)
                    | set(participation.operator_excluded_people)
                )
            )
        original_policy = str(Path(request.portfolio_policy_json or "").resolve())
        expected_policy_sha256 = str(intake["hashes"][original_policy])
        if slate.mode is EngineMode.CLASSIC:
            validation = validate_classic_portfolio_policy_file(
                snapshotted.portfolio_policy_json,
                slate=slate,
                entry_ids=tuple(entry.entry_id for entry in entries.authorizations),
                entry_sha256=entries.raw_hash,
                externally_excluded_people=external_people,
                expected_sha256=expected_policy_sha256,
            )
        else:
            validation = validate_portfolio_policy_file(
                snapshotted.portfolio_policy_json,
                slate=slate,
                entry_ids=tuple(entry.entry_id for entry in entries.authorizations),
                externally_excluded_people=external_people,
                expected_sha256=expected_policy_sha256,
            )
        policy_report_path = (
            DEFAULT_RUNS_DIR / run_id / "portfolio_policy_validation.json"
        )
        if slate.mode is EngineMode.CLASSIC:
            write_classic_portfolio_policy_validation(policy_report_path, validation)
        else:
            write_portfolio_policy_validation(policy_report_path, validation)
        if validation.policy is not None:
            normalized_path = (
                DEFAULT_RUNS_DIR / run_id / "portfolio_policy.normalized.json"
            )
            if slate.mode is EngineMode.CLASSIC:
                write_normalized_classic_portfolio_policy(
                    normalized_path, validation.policy
                )
            else:
                write_normalized_portfolio_policy(normalized_path, validation.policy)
        if validation.valid:
            validated_policy = validation.policy
        policy_blockers.extend(validation.blockers())
        if snapshotted.profile != "prior_review":
            policy_profile_code = (
                "PORTFOLIO_POLICY_PROFILE_UNSUPPORTED_SD4"
                if slate.mode is EngineMode.SHOWDOWN
                else "PORTFOLIO_POLICY_PROFILE_UNSUPPORTED_C2"
            )
            policy_blockers.append(
                f"{policy_profile_code}: policy enforcement and "
                "independent audit are available only in the prior_review "
                "profile; next action: use profile=prior_review or omit the policy"
            )
        if (
            snapshotted.lineup_count is not None
            and snapshotted.lineup_count != len(entries.authorizations)
        ):
            policy_blockers.append(
                "PORTFOLIO_POLICY_LINEUP_COUNT_MUST_MATCH_ENTRIES: "
                f"lineup_count={snapshotted.lineup_count} but requested entries="
                f"{len(entries.authorizations)}; next action: omit lineup_count or set it "
                "to the full requested Entry-ID count"
            )
        policy_summary = {
            "valid": validation.valid,
            "source_policy_sha256": validation.source_sha256,
            "normalized_policy_sha256": validation.normalized_sha256,
            "validation_report": str(policy_report_path),
            "normalized_policy": str(normalized_path) if normalized_path else None,
            "entry_count_denominator": len(entries.authorizations),
            "enforcement_status": (
                "PENDING_RUNTIME_ENFORCEMENT_AND_AUDIT"
                if validation.valid
                else "VALIDATION_FAILED"
            ),
        }
    if policy_summary is not None:
        budget.record("policy_validation", started_after=policy_started,
                      elapsed=budget.elapsed() - policy_started)
    staged_workbook = DEFAULT_RUNS_DIR / run_id / "staged" / "cowork_input.xlsx"
    create_operator_input_workbook(staged_workbook)
    populate_operator_run_control(
        staged_workbook,
        _cowork_run_control_values(snapshotted),
    )
    doctor_report = doctor(PROJECT_ROOT)
    blockers = list(_cowork_reported_blockers(snapshotted))
    blockers[0:0] = policy_blockers
    contest_scope_spread = list(single_contest_problems(entries))
    if snapshotted.profile == "prior_review":
        contest_problems: list[str] = []
    else:
        contest_problems = list(contest_scope_spread)
        blockers[0:0] = contest_problems
    if not doctor_report.pass_status:
        blockers.insert(
            0,
            "ENVIRONMENT_DOCTOR_FAILED: the pinned runtime or workspace checks did not pass",
        )

    # The deadline's gate on the improvement: a deadline already passed, or a
    # window already spent, leaves the baseline as the file (named, never silent).
    # Certifying a supplied manual-guardrail assignment optimizes nothing, so it
    # is not discretionary optimization and the gate does not stop it.
    manual_certification = snapshotted.profile != "prior_review" and snapshotted.assignment_csv is not None
    deadline_stop = None if manual_certification else budget.review_gate()
    if (
        not doctor_report.pass_status
        or contest_problems
        or policy_blockers
        or _cowork_core_blockers(snapshotted)
        or deadline_stop is not None
    ):
        blocked_truths = _blocked_truth_values(
            model_status=(
                ModelStatus.PRIOR_ONLY
                if snapshotted.profile == "prior_review"
                else ModelStatus.UNVALIDATED
            ),
            certification_basis=(
                CertificationBasis.MANUAL_GUARDRAIL
                if snapshotted.manual_guardrail and snapshotted.assignment_csv is not None
                else CertificationBasis.MODEL_ASSISTED
            )
        )
        # The run stops before its review; the baseline, when published, is
        # still the file to hand over, and the result says so.
        registry = load_gate_registry()
        if deadline_stop is not None:
            blockers.insert(0, deadline_stop)
        blockers.extend(
            deadline_text for deadline_text in budget.blocker_texts() if deadline_text not in blockers
        )
        stage = (
            "DEADLINE_IMPROVEMENT_SKIPPED" if deadline_stop is not None
            else "PORTFOLIO_POLICY_ENFORCEMENT_BLOCKED" if policy_summary is not None
            else "RECONCILED"
        )
        latest, latest_problems = _read_run_pointer(output_root, run_id)
        improvement = {
            "status": "NOT_PRODUCED", "stage": stage, "path": None, "sha256": None,
            "producer": None, "replaced": None, "reasons": list(blockers[:5]),
        }
        release_truths = _run_release_truths(
            blocked_truths, latest=latest, not_delivered=_not_delivered_detail(improvement),
            authorized=tuple(item.entry_id for item in entries.authorizations),
            blockers=[*blockers, *latest_problems, *baseline.problems], registry=registry,
            extra=budget.limitations(registry),
        )
        review_path = output_root / f"NFL_DFS_Cowork_Review_{run_id}.xlsx"
        create_cowork_status_workbook(
            output_path=review_path,
            run_values=_cowork_run_control_values(snapshotted),
            blockers=blockers,
            report_path=report_path,
            truth_values=blocked_truths,
            review_csv_path=latest.deliverable.path if latest is not None else None,
            review_csv_sha256=latest.deliverable.sha256 if latest is not None else None,
        )
        result = {
            "run_id": run_id,
            "status": "DO_NOT_UPLOAD",
            **blocked_truths,
            "stage": stage,
            "mode": slate.mode.value,
            "authorized_entries": len(entries.authorizations),
            "contest_ids": sorted({entry.contest_id for entry in entries.authorizations}),
            "contest_names": sorted({entry.contest_name for entry in entries.authorizations}),
            "entry_fees": sorted({entry.entry_fee for entry in entries.authorizations}),
            "contest_scope_observations": contest_scope_spread,
            "request": str(request_path),
            "review_workbook": str(review_path),
            "blockers": blockers,
            "unclassified_csvs": [str(path) for path in unclassified],
            "input_hashes": intake["hashes"],
            "superseded_request_inputs": getattr(args, "_cowork_superseded_inputs", {}),
            "doctor": json.loads(doctor_report.to_json()),
            "next": (
                "Claude should gather and freeze approved public evidence, populate the request, "
                "and ask the operator only for unavailable contest payout or field facts."
            ),
            "DELIVERY_STATE": release_truths.delivery_state.value,
            "release_truths": release_truths.model_dump(mode="json", by_alias=True),
            "latest_deliverable": latest.summary() if latest is not None else None,
            "latest_deliverable_problems": list(latest_problems),
            "baseline": baseline.summary(),
            "improvement": improvement,
            "deadline": budget.as_record(),
        }
        if policy_summary is not None:
            result["portfolio_policy"] = policy_summary
            result["bulk_entry_csv"] = None
            result["next"] = (
                "Resolve every named policy or input blocker, then rerun from the immutable "
                "salary, entry, source-policy and normalized-policy artifacts."
            )
        if deadline_stop is not None:
            result["next"] = (
                f"The delivery deadline {budget.deadline.isoformat()} left the run's own review no"
                " time; hand over the file named above with every limitation it carries."
            )
        result["next"] = _baseline_next(latest, str(result["next"]))
        _write_json(report_path, result)
        _print_json(result)
        return 2

    if snapshotted.profile == "prior_review":
        return _run_prior_review_profile(
            args=args,
            request=snapshotted,
            run_id=run_id,
            slate=slate,
            entries=entries,
            output_root=output_root,
            report_path=report_path,
            request_path=request_path,
            doctor_report=doctor_report,
            unclassified=unclassified,
            intake=intake,
            reported_blockers=blockers,
            portfolio_policy=validated_policy,
            portfolio_policy_source_path=(
                snapshotted.portfolio_policy_json if validated_policy is not None else None
            ),
            portfolio_policy_source_sha256=(
                expected_policy_sha256 if validated_policy is not None else None
            ),
            portfolio_policy_normalized_path=(
                str(normalized_path) if validated_policy is not None and normalized_path else None
            ),
            portfolio_policy_normalized_sha256=(
                validated_policy.normalized_sha256 if validated_policy is not None else None
            ),
            policy_summary=policy_summary,
            baseline=baseline,
            budget=budget,
        )

    review_started = budget.elapsed()
    assignment_path = snapshotted.assignment_csv
    build_report_path: Path | None = None
    model_assisted = assignment_path is None
    if model_assisted:
        diagnostic = snapshotted.profile == "diagnostic"
        build_args = argparse.Namespace(
            salaries=snapshotted.salary_csv,
            entries=snapshotted.entry_csv,
            run_id=run_id,
            label=snapshotted.label,
            team_projections=snapshotted.team_projection_csv,
            player_opportunities=snapshotted.player_opportunity_csv,
            payouts=snapshotted.payout_csv,
            advertised_prize_value=snapshotted.advertised_prize_value,
            ticket_face_value=snapshotted.ticket_face_value,
            field_size=snapshotted.field_size,
            objective=snapshotted.objective,
            ownership_brackets=snapshotted.ownership_brackets_csv,
            design_scenarios=1000 if diagnostic else None,
            select_scenarios=2000 if diagnostic else None,
            referee_scenarios=2000 if diagnostic else None,
            seed=20260913,
            design_objectives=64,
            candidates=250 if diagnostic else 20000,
            milp_seed_candidates=64,
            per_solve_seconds=3.0,
            field_sample_size=1000,
            field_chunk_size=128,
            shortlist_limit=250,
            output_dir=str(Path(args.output_dir).resolve()),
        )
        build_code = command_build(build_args)
        if build_code != 0:
            raise RuntimeError(f"Cowork diagnostic build failed with exit code {build_code}")
        assignment_path = str(output_root / f"assignments_{run_id}.csv")
        build_report_path = output_root / f"build_{run_id}.json"

    certify_args = argparse.Namespace(
        salaries=snapshotted.salary_csv,
        entries=snapshotted.entry_csv,
        run_id=run_id,
        label=snapshotted.label,
        assignments=assignment_path,
        payouts=snapshotted.payout_csv,
        advertised_prize_value=snapshotted.advertised_prize_value,
        ticket_face_value=snapshotted.ticket_face_value,
        field_size=snapshotted.field_size,
        objective=snapshotted.objective,
        official_statuses=snapshotted.official_status_csv,
        team_projections=snapshotted.team_projection_csv,
        player_opportunities=snapshotted.player_opportunity_csv,
        source_ledger=snapshotted.source_ledger_json,
        build_report=str(build_report_path) if build_report_path else None,
        manual_guardrail=False if model_assisted else snapshotted.manual_guardrail,
        output_dir=str(Path(args.output_dir).resolve()),
        staged_workbook=str(staged_workbook),
    )
    code, certification = _certify(certify_args)
    budget.record("review", started_after=review_started, elapsed=budget.elapsed() - review_started)
    budget.finished_late("review")
    latest, latest_problems = _read_run_pointer(output_root, run_id)
    result = {
        "run_id": run_id,
        "status": certification["status"],
        "FILE_VALID": certification["FILE_VALID"],
        "EVIDENCE_STATE": certification["EVIDENCE_STATE"],
        "MODEL_STATUS": certification["MODEL_STATUS"],
        "RELEASE_DECISION": certification["RELEASE_DECISION"],
        "stage": (
            "CERTIFIED"
            if certification["RELEASE_DECISION"] == "CERTIFIED_UPLOAD_PACKAGE"
            else "DO_NOT_UPLOAD"
        ),
        "mode": slate.mode.value,
        "authorized_entries": len(entries.authorizations),
        "request": str(request_path),
        "build_report": str(build_report_path) if build_report_path else None,
        "assignments": assignment_path,
        "certification": certification,
        "unclassified_csvs": [str(path) for path in unclassified],
        "input_hashes": intake["hashes"],
        "doctor": json.loads(doctor_report.to_json()),
        "meaning": (
            "CERTIFIED covers exact inputs, legality, evidence, authorization, and final bytes; "
            "it is not an EV, ROI, win-rate, or profitability claim."
        ),
        # The certify path writes its own package; the baseline is named beside
        # it as the prior-only fallback, never mixed into its release decision.
        "baseline": baseline.summary(),
        "latest_deliverable": latest.summary() if latest is not None else None,
        "latest_deliverable_problems": list(latest_problems),
        "latest_deliverable_meaning": (
            "The PRIOR_ONLY / DO_NOT_UPLOAD baseline this run published first. A certified "
            "package, when RELEASE_DECISION says so, is certification's own file, not this one."
        ),
        "deadline": budget.as_record(),
    }
    _write_json(report_path, result)
    _print_json(result)
    return code


def _read_run_pointer(
    output_root: Path, run_id: str
) -> tuple[LatestDeliverable | None, tuple[str, ...]]:
    """This run's validated deliverable, if its pointer still revalidates. Never raises.

    Every `run-slate` exit reads the pointer back through here, so its result
    describes the file on disk now; the outer handler must finish whatever it finds.
    """

    try:
        return read_latest_deliverable(output_root, run_id=run_id), ()
    except DeliveryPointerError as exc:
        return None, exc.problems
    except Exception as exc:  # noqa: BLE001 - reported, never allowed to break the handler
        return None, (f"DELIVERABLE_REVALIDATION_FAILED:{type(exc).__name__}:{exc}",)


def _handler_release_truths(
    latest: LatestDeliverable | None, failure: str, budget: Budget | None = None
) -> dict[str, object] | None:
    """v2 for a failed run: its own blocked v1 truths beside the pointer's delivery half.

    When the pointer still names the baseline, `IMPROVEMENT_NOT_DELIVERED` says
    the run failed before anything replaced it.
    """

    if latest is None:
        return None
    registry = load_gate_registry()
    return _run_release_truths(
        _blocked_truth_values(),
        latest=latest,
        not_delivered=_not_delivered_detail(
            {"status": "NOT_PRODUCED", "stage": "BUILD_OR_CERTIFY_FAILED", "reasons": [failure]}
        ),
        authorized=(),
        blockers=(),
        registry=registry,
        extra=budget.limitations(registry) if budget is not None else (),
    ).model_dump(mode="json", by_alias=True)


def command_cowork_run(args: argparse.Namespace) -> int:
    try:
        return _command_cowork_run(args)
    except Exception as exc:
        label = args.label or "slate"
        if args.request:
            try:
                raw_request = json.loads(Path(args.request).read_text(encoding="utf-8"))
                if isinstance(raw_request, dict) and isinstance(raw_request.get("label"), str):
                    label = raw_request["label"]
            except (OSError, json.JSONDecodeError):
                pass
        run_id = getattr(args, "_resolved_cowork_run_id", None)
        if run_id is None:
            # Nothing was created by this invocation (the failure came before
            # the run id was claimed, e.g. RUN_ID_COLLISION), so there is no
            # folder of ours to write a record into. An earlier run's folder is
            # never touched from here.
            raise
        intake_path = DEFAULT_RUNS_DIR / run_id / "intake.json"
        if not intake_path.is_file():
            raise
        try:
            intake = json.loads(intake_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            intake = {"run_id": run_id, "hashes": {}}

        output_base = Path(args.output_dir).resolve()
        output_root = (output_base / run_id).resolve()
        if not output_root.is_relative_to(output_base):
            raise RuntimeError("Cowork output run path escaped the supplied output directory") from exc
        # A file passed independent validation earlier in this run exactly when
        # this run's LATEST_DELIVERABLE.json names it and it revalidates now
        # (Session 05). The handler names that file and never deletes it.
        # The pointer never names a `DK_UPLOAD_*` file (`delivery.revalidate`
        # refuses the name), so the sweep below cannot reach it.
        latest, latest_problems = _read_run_pointer(output_root, run_id)
        failure = f"{type(exc).__name__}:{exc}"
        budget = getattr(args, "_run_slate_budget", None)
        budget = budget if isinstance(budget, Budget) else None
        try:
            handler_truths = _handler_release_truths(latest, failure, budget)
        except Exception as truths_exc:  # noqa: BLE001 - the handler must finish
            latest_problems = (*latest_problems, f"DELIVERABLE_REVALIDATION_FAILED:{truths_exc}")
            latest, handler_truths = None, None
        baseline = getattr(args, "_run_slate_baseline", None)
        removed_uploads: list[str] = []
        if output_root.is_dir():
            for upload_path in output_root.glob("DK_UPLOAD_*.csv"):
                upload_path.unlink(missing_ok=True)
                removed_uploads.append(str(upload_path))
        delivery_fields = {
            "DELIVERY_STATE": (
                latest.deliverable.truths.delivery_state.value
                if latest is not None
                else DeliveryState.NO_DELIVERABLE.value
            ),
            "release_truths": handler_truths,
            "latest_deliverable": latest.summary() if latest is not None else None,
            "latest_deliverable_problems": list(latest_problems),
            "baseline": baseline.summary() if isinstance(baseline, _SlateBaseline) else None,
            "improvement": {
                "status": (
                    "DELIVERED"
                    if latest is not None and latest.deliverable.producer != BASELINE_PRODUCER
                    else "NOT_PRODUCED"
                ),
                "stage": "BUILD_OR_CERTIFY_FAILED",
                "reasons": [failure],
            },
            "deadline": budget.as_record() if budget is not None else None,
        }

        diagnostic = {
            "run_id": run_id,
            "status": "DO_NOT_UPLOAD",
            **_blocked_truth_values(),
            "stage": "BUILD_OR_CERTIFY_FAILED",
            "error": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
            "input_hashes": intake.get("hashes", {}),
            "removed_uploads": removed_uploads,
            **delivery_fields,
        }
        diagnostic_path = output_root / "cowork_diagnostic.json"
        report_path = output_root / "cowork_run.json"
        result = {
            "run_id": run_id,
            "status": "DO_NOT_UPLOAD",
            **_blocked_truth_values(),
            "stage": "BUILD_OR_CERTIFY_FAILED",
            "error": type(exc).__name__,
            "message": str(exc),
            "diagnostic": str(diagnostic_path),
            "request": str(DEFAULT_RUNS_DIR / run_id / "run_request.json"),
            "input_hashes": intake.get("hashes", {}),
            "upload_csv": None,
            **delivery_fields,
            "next": _baseline_next(
                latest,
                "Read the diagnostic, fix the named failure and rerun under a new run id.",
            ),
        }
        try:
            _write_json(diagnostic_path, diagnostic)
            _write_json(report_path, result)
        except OSError:
            fallback = DEFAULT_RUNS_DIR / run_id / "cowork_diagnostic.json"
            try:
                _write_json(fallback, diagnostic)
                result["diagnostic"] = str(fallback)
            except OSError:
                result["diagnostic"] = None
        _print_json(result)
        return 2


def command_run(args: argparse.Namespace) -> int:
    print("NFL DFS guided workflow")
    print("1. Intake and reconcile immutable DraftKings inputs.")
    print("2. Close Excel and provide staged evidence.")
    print("3. Build or validate assignments.")
    print("4. Run quantitative QA.")
    print("5. Certify exact output bytes.")
    print("6. Review the versioned workbook and upload manually only if CERTIFIED.")
    if args.salaries:
        return command_intake(args)
    if not DEFAULT_STAGED_WORKBOOK.exists():
        create_operator_input_workbook(DEFAULT_STAGED_WORKBOOK)
    operator = read_operator_input(DEFAULT_STAGED_WORKBOOK)
    values = operator.values
    salaries = str(values.get("SALARY_CSV") or "").strip()
    entries = str(values.get("ENTRY_CSV") or "").strip()
    if not salaries or not entries:
        print(f"\nStaged workbook: {DEFAULT_STAGED_WORKBOOK}")
        print("Fill SALARY_CSV and ENTRY_CSV on Run Control, close Excel, then run this same command again:")
        print(r".\nfl.ps1 run")
        return 0
    label = str(values.get("RUN_LABEL") or "slate")
    run_id = _run_id(label)
    staged_dir = DEFAULT_RUNS_DIR / run_id / "staged"
    payout_path = str(values.get("PAYOUT_CSV") or "").strip()
    if not payout_path and operator.payout_rows:
        payout_path = str(
            _write_staged_csv(
                staged_dir / "payouts.csv",
                ("rank_start", "rank_end", "prize_type", "value"),
                operator.payout_rows,
            )
        )
    status_path = str(values.get("OFFICIAL_STATUS_CSV") or "").strip()
    if not status_path and operator.official_status_rows:
        status_path = str(
            _write_staged_csv(
                staged_dir / "official_statuses.csv",
                ("TEAM", "PLAYER_OR_GSIS_ID", "STATUS", "SOURCE_URL", "OBSERVED_AT"),
                operator.official_status_rows,
            )
        )
    bracket_path = ""
    if operator.ownership_rows:
        bracket_path = str(
            _write_staged_csv(
                staged_dir / "ownership_brackets.csv",
                ("DK_ID", "LOW", "BASE", "HIGH"),
                operator.ownership_rows,
            )
        )
    assignment_path = str(values.get("ASSIGNMENT_CSV") or "").strip()
    team_path = str(values.get("TEAM_PROJECTION_CSV") or "").strip()
    player_path = str(values.get("PLAYER_OPPORTUNITY_CSV") or "").strip()
    advertised = values.get("ADVERTISED_PRIZE_VALUE")
    ticket_face = values.get("TICKET_FACE_VALUE")
    field_size = values.get("FIELD_SIZE")
    objective = str(values.get("CONTEST_OBJECTIVE") or "LARGE_GPP")
    manual = str(values.get("MANUAL_GUARDRAIL_MODE") or "YES").upper() == "YES"
    if (
        assignment_path
        and payout_path
        and advertised not in (None, "")
        and field_size not in (None, "")
    ):
        inferred_build_report = Path(assignment_path).resolve().parent / f"build_{run_id}.json"
        certify_args = argparse.Namespace(
            salaries=salaries,
            entries=entries,
            run_id=run_id,
            label=label,
            assignments=assignment_path,
            payouts=payout_path,
            advertised_prize_value=float(advertised),
            ticket_face_value=float(ticket_face) if ticket_face not in (None, "") else None,
            field_size=int(field_size),
            objective=objective,
            official_statuses=status_path or None,
            team_projections=team_path or None,
            player_opportunities=player_path or None,
            source_ledger=None,
            build_report=str(inferred_build_report) if inferred_build_report.exists() else None,
            manual_guardrail=manual,
            output_dir=str(DEFAULT_OUTPUT_DIR),
            staged_workbook=str(DEFAULT_STAGED_WORKBOOK),
        )
        return command_certify(certify_args)
    if team_path and player_path and payout_path and advertised not in (None, "") and field_size not in (None, ""):
        build_args = argparse.Namespace(
            salaries=salaries,
            entries=entries,
            run_id=run_id,
            label=label,
            team_projections=team_path,
            player_opportunities=player_path,
            payouts=payout_path,
            advertised_prize_value=float(advertised),
            ticket_face_value=float(ticket_face) if ticket_face not in (None, "") else None,
            field_size=int(field_size),
            objective=objective,
            ownership_brackets=bracket_path or None,
            design_scenarios=1000,
            select_scenarios=2000,
            referee_scenarios=2000,
            seed=20260913,
            design_objectives=64,
            candidates=250,
            milp_seed_candidates=64,
            per_solve_seconds=3.0,
            field_sample_size=1000,
            field_chunk_size=128,
            shortlist_limit=250,
            output_dir=str(DEFAULT_OUTPUT_DIR),
        )
        return command_build(build_args)
    intake_args = argparse.Namespace(salaries=salaries, entries=entries, run_id=run_id, label=label)
    code = command_intake(intake_args)
    if code == 0:
        print(
            "\nIntake passed. Add either ASSIGNMENT_CSV plus payout and field-size "
            "evidence, or both model-input CSVs plus payout and field-size evidence, "
            "then rerun .\\nfl.ps1 run."
        )
    return code


def _add_intake_args(parser: argparse.ArgumentParser, optional: bool = False) -> None:
    parser.add_argument("--salaries", required=not optional)
    parser.add_argument("--entries", required=not optional)
    parser.add_argument("--run-id")
    parser.add_argument("--label", default="slate")


def _add_certify_args(parser: argparse.ArgumentParser) -> None:
    _add_intake_args(parser)
    parser.add_argument("--assignments", required=True)
    parser.add_argument("--payouts", required=True)
    parser.add_argument("--advertised-prize-value", type=float, required=True)
    parser.add_argument("--ticket-face-value", type=float)
    parser.add_argument("--field-size", type=int, required=True)
    parser.add_argument(
        "--objective",
        choices=[value.value for value in ContestObjective],
        default=ContestObjective.LARGE_GPP.value,
    )
    parser.add_argument("--official-statuses")
    parser.add_argument("--team-projections")
    parser.add_argument("--player-opportunities")
    parser.add_argument("--source-ledger")
    parser.add_argument("--build-report")
    parser.add_argument("--manual-guardrail", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--staged-workbook", default=str(DEFAULT_STAGED_WORKBOOK))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nfl-dfs", description="Evidence-first NFL DFS engine")
    subparsers = parser.add_subparsers(dest="command", required=True)
    setup = subparsers.add_parser("setup")
    setup.add_argument("--workbook", default=str(DEFAULT_STAGED_WORKBOOK))
    setup.set_defaults(func=command_setup)
    run = subparsers.add_parser("run")
    _add_intake_args(run, optional=True)
    run.set_defaults(func=command_run)
    # `run-slate` is the documented name. `cowork-run` stays as an alias because
    # renaming it alone would not help: the wire format is
    # `nfl_cowork_run_request_v1` and `cowork.py` hard-rejects a mismatched
    # schema_version, so every run_request.json already on disk depends on the
    # old string. Changing that is a contract version bump, not a rename.
    cowork = subparsers.add_parser(
        "run-slate",
        aliases=["cowork-run"],
        help="discover the DraftKings CSVs by schema and drive the fail-closed slate workflow",
    )
    cowork.add_argument("--input-dir")
    cowork.add_argument("--request")
    cowork.add_argument("--salaries")
    cowork.add_argument("--entries")
    cowork.add_argument("--label")
    cowork.add_argument("--run-id")
    cowork.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    cowork.add_argument(
        "--profile",
        choices=list(SUPPORTED_PROFILES),
        help=(
            "diagnostic (default) and registered run the existing build and certify"
            " path; prior_review drives the prior-only chain and can never certify"
        ),
    )
    cowork.add_argument(
        "--no-session-probe",
        action="store_true",
        default=False,
        help=(
            "skip the pre-run host reachability probe; it otherwise runs at the"
            " head of every slate and is written to the run folder"
        ),
    )
    cowork.add_argument("--prior-package-dir")
    cowork.add_argument("--build-priors", action="store_true", default=False)
    cowork.add_argument("--season", type=int)
    cowork.add_argument("--prior-season", type=int)
    cowork.add_argument("--weather-state", choices=list(OPERATOR_WEATHER_STATES))
    cowork.add_argument("--weather-source-uri")
    cowork.add_argument("--weather-observed-at")
    cowork.add_argument(
        "--weather-evidence-json",
        help=(
            "hash-bound per-game Classic weather evidence manifest; required when "
            "more than one game needs an operator weather observation"
        ),
    )
    cowork.add_argument("--role-evidence-json")
    cowork.add_argument("--offensive-role-evidence-json")
    cowork.add_argument("--qb-depth-role-evidence-json")
    cowork.add_argument("--portfolio-policy-json")
    cowork.add_argument("--official-status-csv")
    cowork.add_argument("--lineup-count", type=int)
    cowork.add_argument("--max-person-overlap", type=int)
    cowork.add_argument("--as-of")
    cowork.add_argument(
        "--delivery-deadline-utc",
        help=(
            "when the file is due, an ISO-8601 moment with a UTC offset (request v3);"
            " default: the earliest lock minus 5 minutes (R31)"
        ),
    )
    cowork.add_argument("--exclude", action="append")
    cowork.add_argument("--unavailable-status", action="append")
    cowork.add_argument("--available-status", action="append")
    cowork.set_defaults(func=command_cowork_run)
    select = subparsers.add_parser(
        "select",
        help="prior-only Showdown selection; never calls field or payout economics",
    )
    select.add_argument("--salaries", required=True)
    select.add_argument("--salary-sha256")
    select.add_argument("--entries", required=True)
    select.add_argument("--team-projections", required=True)
    select.add_argument("--player-opportunities", required=True)
    select.add_argument("--team-splits", required=True)
    select.add_argument("--prior-season", type=int, required=True)
    select.add_argument("--role-evidence-json")
    select.add_argument("--offensive-role-evidence-json")
    select.add_argument("--qb-depth-role-evidence-json")
    select.add_argument("--as-of")
    select.add_argument("--count", type=int)
    select.add_argument("--max-person-overlap", type=int, default=4)
    select.add_argument(
        "--allow-repeat-captain", action="store_true", default=False
    )
    select.add_argument(
        "--no-redistribute", action="store_true", default=False
    )
    select.add_argument("--exclude", action="append")
    select.add_argument("--unavailable-status", action="append")
    select.add_argument("--available-status", action="append")
    select.add_argument("--output-dir", required=True)
    select.set_defaults(func=command_select)
    review_export = subparsers.add_parser(
        "review-export",
        help="write a legality-checked, byte-audited bulk-entry CSV; never certified",
    )
    review_export.add_argument("--salaries", required=True)
    review_export.add_argument("--entries", required=True)
    review_export.add_argument("--assignments", required=True)
    review_export.add_argument("--label")
    review_export.add_argument("--output-dir", required=True)
    review_export.set_defaults(func=command_review_export)
    baseline_parser = subparsers.add_parser(
        "baseline",
        help=(
            "distinct legal lineups from the DraftKings salary and entries bytes, less any"
            " excluded or officially inactive person, into a new byte-audited DK_BASELINE_ENTRY"
            " file; no network, priors, weather or roles"
        ),
    )
    baseline_parser.add_argument("--salaries", required=True)
    baseline_parser.add_argument("--entries", required=True)
    baseline_parser.add_argument("--out-dir", "--output-dir", dest="out_dir", default=str(DEFAULT_RUNS_DIR))
    baseline_parser.add_argument("--run-id")
    baseline_parser.add_argument("--per-solve-seconds", type=float, default=DEFAULT_PER_SOLVE_SECONDS)
    baseline_parser.add_argument("--budget-seconds", type=float, default=DEFAULT_BUDGET_SECONDS)
    baseline_parser.add_argument(
        "--exclude", action="append", default=[],
        help="an exact DraftKings ID whose person leaves the pool (repeatable)")
    baseline_parser.add_argument(
        "--unavailable-status", action="append", default=[],
        help="an extra DraftKings status whose people leave the pool (repeatable)")
    baseline_parser.add_argument(
        "--official-status",
        help="an official status CSV; people its accepted rows mark INACTIVE leave the pool (R32)")
    baseline_parser.set_defaults(func=command_baseline)
    priors_propose = subparsers.add_parser(
        "priors-propose",
        help="freeze approved nflverse artifacts and propose the DK identity crosswalk",
    )
    priors_propose.add_argument("--salaries", required=True)
    priors_propose.add_argument("--salary-sha256", required=True)
    priors_propose.add_argument("--season", type=int, required=True)
    priors_propose.add_argument("--prior-season", type=int, required=True)
    priors_propose.add_argument("--as-of", required=True)
    priors_propose.add_argument("--output-dir", required=True)
    priors_propose.set_defaults(func=command_priors_propose)
    priors_freeze = subparsers.add_parser(
        "priors-freeze",
        help="publish prior-only team, player and identity artifacts from a reviewed crosswalk",
    )
    priors_freeze.add_argument("--package-dir", required=True)
    priors_freeze.add_argument("--reviewed", required=True)
    priors_freeze.add_argument("--reviewed-sha256", required=True)
    priors_freeze.add_argument("--salaries", required=True)
    priors_freeze.add_argument("--salary-sha256", required=True)
    priors_freeze.add_argument("--as-of", required=True)
    priors_freeze.add_argument("--output-dir", required=True)
    priors_freeze.add_argument("--weather-state")
    priors_freeze.add_argument("--salary-observed-at")
    priors_freeze.add_argument("--weather-source-uri")
    priors_freeze.add_argument("--weather-observed-at")
    priors_freeze.set_defaults(func=command_priors_freeze)
    project = subparsers.add_parser(
        "project",
        help="build deterministic prior-only model inputs from frozen approved artifacts",
    )
    project.add_argument("--salaries", required=True)
    project.add_argument("--salary-sha256", required=True)
    project.add_argument("--team-source", required=True)
    project.add_argument("--team-source-sha256", required=True)
    project.add_argument("--player-source", required=True)
    project.add_argument("--player-source-sha256", required=True)
    project.add_argument("--identity-map", required=True)
    project.add_argument("--identity-map-sha256", required=True)
    project.add_argument("--as-of", required=True)
    project.add_argument("--output-dir", required=True)
    project.set_defaults(func=command_project)
    doctor_parser = subparsers.add_parser("doctor")
    doctor_parser.add_argument("--workspace", default=str(PROJECT_ROOT))
    doctor_parser.set_defaults(func=command_doctor)
    workbook = subparsers.add_parser("workbook")
    workbook.add_argument("--output", default=str(DEFAULT_STAGED_WORKBOOK))
    workbook.set_defaults(func=command_workbook)
    intake = subparsers.add_parser("intake")
    _add_intake_args(intake)
    intake.set_defaults(func=command_intake)
    validate = subparsers.add_parser("validate")
    validate.add_argument("--salaries", required=True)
    validate.add_argument("--entries", required=True)
    validate.add_argument("--assignments", required=True)
    validate.set_defaults(func=command_validate)
    certify = subparsers.add_parser("certify")
    _add_certify_args(certify)
    certify.set_defaults(func=command_certify)
    build = subparsers.add_parser("build")
    _add_intake_args(build)
    build.add_argument("--team-projections", required=True)
    build.add_argument("--player-opportunities", required=True)
    build.add_argument("--payouts", required=True)
    build.add_argument("--advertised-prize-value", type=float, required=True)
    build.add_argument("--ticket-face-value", type=float)
    build.add_argument("--field-size", type=int, required=True)
    build.add_argument(
        "--objective",
        choices=[value.value for value in ContestObjective],
        default=ContestObjective.LARGE_GPP.value,
    )
    build.add_argument("--ownership-brackets")
    build.add_argument("--design-scenarios", type=int)
    build.add_argument("--select-scenarios", type=int)
    build.add_argument("--referee-scenarios", type=int)
    build.add_argument("--seed", type=int, default=20260913)
    build.add_argument("--design-objectives", type=int, default=64)
    build.add_argument("--candidates", type=int, default=20000)
    build.add_argument("--milp-seed-candidates", type=int, default=64)
    build.add_argument("--per-solve-seconds", type=float, default=3.0)
    build.add_argument("--field-sample-size", type=int, default=1000)
    build.add_argument("--field-chunk-size", type=int, default=128)
    build.add_argument("--shortlist-limit", type=int, default=250)
    build.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    build.set_defaults(func=command_build)
    late = subparsers.add_parser("late-swap")
    late.add_argument("--run-id", required=True)
    late.add_argument("--salaries", required=True)
    late.add_argument("--current-entries", "--entries", dest="current_entries", required=True)
    late.add_argument("--prior-manifest", required=True)
    late.add_argument("--prior-assignments", required=True)
    late.add_argument("--proposed-assignments", required=True)
    late.add_argument("--eligibility-evidence", required=True)
    late.add_argument("--inactive-reports", required=True)
    late.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    late.add_argument("--as-of", required=True)
    late.set_defaults(func=command_late_swap)
    settle = subparsers.add_parser("settle")
    settle.add_argument("--request")
    settle.add_argument("--replay")
    settle.add_argument("--entries")
    settle.add_argument("--standings")
    settle.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR / "settlements"))
    settle.set_defaults(func=command_settle)
    learn = subparsers.add_parser("learn")
    learn.add_argument("--comparable-slates", type=int, required=True)
    for flag in (
        "reproducible",
        "integrity-pass",
        "rolling-origin-improvement",
        "calibration-pass",
        "drift-pass",
        "no-regression",
        "prospective-field-gates",
        "integrity-failure",
    ):
        learn.add_argument(f"--{flag}", action=argparse.BooleanOptionalAction, default=False)
    learn.add_argument("--realized-roi", type=float)
    learn.add_argument("--degradation-windows", type=int, default=0)
    learn.add_argument(
        "--metric-registry",
        default=str(PROJECT_ROOT / "config" / "metric_registry_q1_v1.json"),
    )
    learn.add_argument("--challenger-evaluated-at")
    learn.set_defaults(func=command_learn)
    status = subparsers.add_parser("status")
    status.add_argument("--manifest", required=True)
    status.set_defaults(func=command_status)
    audit = subparsers.add_parser("audit")
    audit.add_argument("--manifest", required=True)
    audit.set_defaults(func=command_audit)
    preflight = subparsers.add_parser(
        "preflight",
        help="live pre-upload check: re-derive every hard gate at the current clock",
    )
    preflight.add_argument("--manifest", required=True)
    preflight.add_argument("--salaries")
    preflight.add_argument("--entries")
    preflight.add_argument("--assignments")
    preflight.set_defaults(func=command_preflight)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except Exception as exc:
        _print_json(
            {
                "status": "DO_NOT_UPLOAD",
                **_blocked_truth_values(),
                "stage": "CLI_FAILED",
                "error": type(exc).__name__,
                "message": str(exc),
            }
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
