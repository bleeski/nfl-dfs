from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping

import numpy as np

from .certification import certify_upload
from .candidate_families import coverage_report
from .contracts import (
    ContestObjective,
    EngineMode,
    EvidenceRecord,
    EvidenceState,
    Lineup,
)
from .cowork import (
    CoworkRunRequest,
    PATH_FIELDS,
    required_next_inputs,
    resolve_request_inputs,
)
from .dk import EntryTemplate, parse_entries, parse_salaries, reconcile_template
from .economics import evaluate_candidates_against_field
from .evidence import parse_official_inactives
from .field import generate_opponent_field, scale_field_multiplicities
from .hashing import content_hash, sha256_file
from .late_swap import audit_late_swap
from .learning import evaluate_challenger, should_rollback
from .lineups import read_assignment_csv, validate_lineup
from .opportunity import load_opportunity_model
from .optimizer import generate_candidates
from .ownership import OwnershipBracket, cold_start_states
from .payouts import parse_payout_csv, validate_payout_tiers
from .portfolio import select_portfolio
from .portfolio import evaluate_portfolio
from .qa import QAFinding, referee_blocks
from .scenario_store import save_scenario_bank
from .settlement import parse_standings, require_entry_coverage
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


def _print_json(value: object) -> None:
    print(json.dumps(value, indent=2, sort_keys=True, default=str))


def _run_id(label: str = "run") -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    cleaned = "".join(character if character.isalnum() or character in "-_" else "-" for character in label)
    return f"{stamp}-{cleaned[:40] or 'run'}"


def _snapshot_basename(path: str | Path) -> str:
    name = Path(path).name
    prefix, separator, remainder = name.partition("_")
    if separator and len(prefix) == 64 and all(character in "0123456789abcdef" for character in prefix):
        return remainder
    return name


def _snapshot_inputs(run_id: str, paths: Iterable[str | Path]) -> dict[str, str]:
    input_dir = DEFAULT_RUNS_DIR / run_id / "inputs"
    input_dir.mkdir(parents=True, exist_ok=False)
    hashes: dict[str, str] = {}
    for path_value in dict.fromkeys(str(Path(path).resolve()) for path in paths):
        source = Path(path_value).resolve()
        if not source.is_file():
            raise FileNotFoundError(source)
        digest = sha256_file(source)
        target = input_dir / f"{digest}_{_snapshot_basename(source)}"
        shutil.copyfile(source, target)
        if sha256_file(target) != digest:
            raise RuntimeError(f"snapshot hash mismatch for {source}")
        hashes[str(source)] = digest
    return hashes


def _snapshot_path(run_id: str, source: str | Path, digest: str) -> Path:
    return DEFAULT_RUNS_DIR / run_id / "inputs" / f"{digest}_{_snapshot_basename(source)}"


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
    manual_guardrail: bool,
    model_input_hash: str | None,
) -> list[EvidenceRecord]:
    now = datetime.now(timezone.utc)
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
            value=sha256_file(payout_path),
            source_artifact_id=sha256_file(payout_path),
            observed_at=now,
            hard_gate=True,
            state=EvidenceState.PASS,
            reason="payout ranks, monotonicity, and advertised value reconciled",
        ),
        EvidenceRecord(
            subject="slate",
            field="weather_if_required",
            value=None if manual_guardrail else model_input_hash,
            source_artifact_id=model_input_hash if not manual_guardrail else None,
            observed_at=now,
            hard_gate=True,
            state=EvidenceState.NOT_APPLICABLE if manual_guardrail else EvidenceState.PASS,
            reason=(
                "manual legality guardrail makes no model or weather claim"
                if manual_guardrail
                else "model input contains explicit weather state"
            ),
        ),
        EvidenceRecord(
            subject="slate",
            field="market_line",
            value=None if manual_guardrail else model_input_hash,
            source_artifact_id=model_input_hash if not manual_guardrail else None,
            observed_at=now,
            hard_gate=True,
            state=EvidenceState.NOT_APPLICABLE if manual_guardrail else EvidenceState.PASS,
            reason=(
                "manual legality guardrail makes no projection or market claim"
                if manual_guardrail
                else "team model input contains timestamped manual market lines"
            ),
        ),
    ]


def _official_status_evidence(
    *,
    status_path: str | Path | None,
    slate,
    assignments: Mapping[str, tuple[str, ...]],
) -> EvidenceRecord:
    now = datetime.now(timezone.utc)
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
    statuses, problems = parse_official_inactives(status_path, slate.players)
    missing = sorted(selected.difference(statuses))
    selected_inactive = sorted(dk_id for dk_id in selected if statuses.get(dk_id) == "INACTIVE")
    if problems:
        state = EvidenceState.CONFLICTED
        reason = "; ".join(problems)
    elif selected_inactive:
        state = EvidenceState.FAIL
        reason = f"selected players are officially inactive: {selected_inactive}"
    elif missing:
        state = EvidenceState.UNKNOWN
        reason = f"selected exact IDs lack current activity evidence: {missing}"
    else:
        state = EvidenceState.PASS
        reason = "every selected exact DK ID is source-bound and ACTIVE"
    return EvidenceRecord(
        subject="selected_portfolio",
        field="official_inactive_status",
        value={dk_id: statuses.get(dk_id) for dk_id in sorted(selected)},
        source_artifact_id=digest,
        observed_at=now,
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
    if report.excel_lock_probe == "LOCKED_BY_EXCEL":
        print("Close operator_input.xlsx in Excel, then run setup again.", file=sys.stderr)
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
) -> tuple[dict[str, object], object, EntryTemplate]:
    slate = parse_salaries(salaries)
    entries = parse_entries(entries_path)
    reconcile_template(entries, slate)
    hashes = _snapshot_inputs(run_id, snapshot_paths or [salaries, entries_path])
    summary = {
        "run_id": run_id,
        "state": "RECONCILED",
        "mode": slate.mode.value,
        "salary_players": len(slate.players),
        "underlying_people": len({player.underlying_id for player in slate.players}),
        "teams": len({player.team for player in slate.players}),
        "games": len(slate.games),
        "authorized_entries": len(entries.authorizations),
        "hashes": hashes,
        "next": "Supply payouts, exact-ID official statuses, and assignments or model inputs.",
    }
    _write_json(DEFAULT_RUNS_DIR / run_id / "intake.json", summary)
    return summary, slate, entries


def command_intake(args: argparse.Namespace) -> int:
    run_id = args.run_id or _run_id(args.label)
    summary, _, _ = _intake(
        salaries=args.salaries,
        entries_path=args.entries,
        run_id=run_id,
    )
    _print_json(summary)
    return 0


def command_validate(args: argparse.Namespace) -> int:
    slate = parse_salaries(args.salaries)
    template = parse_entries(args.entries)
    reconcile_template(template, slate)
    assignments = read_assignment_csv(args.assignments, slate.mode)
    authorized = {entry.entry_id for entry in template.authorizations}
    problems: list[str] = []
    if set(assignments) != authorized:
        problems.append("assignment Entry IDs do not exactly match reserved entries")
    for entry_id, roster in assignments.items():
        result = validate_lineup(slate, roster)
        problems.extend(f"{entry_id}: {problem}" for problem in result.errors)
    _print_json(
        {
            "status": "PASS" if not problems else "FAIL",
            "mode": slate.mode.value,
            "authorized_entries": len(authorized),
            "problems": problems,
        }
    )
    return 0 if not problems else 2


def _certify(args: argparse.Namespace) -> tuple[int, object]:
    run_id = args.run_id or _run_id(args.label)
    slate = parse_salaries(args.salaries)
    template = parse_entries(args.entries)
    reconcile_template(template, slate)
    assignments = read_assignment_csv(args.assignments, slate.mode)
    tiers = parse_payout_csv(args.payouts)
    validate_payout_tiers(
        tiers,
        advertised_value=args.advertised_prize_value,
        ticket_face_value=args.ticket_face_value,
    )
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
    evidence = _base_evidence(
        slate_hash=slate.salary_hash,
        entries_hash=template.raw_hash,
        payout_path=args.payouts,
        manual_guardrail=args.manual_guardrail,
        model_input_hash=model_hash,
    )
    evidence.append(
        _official_status_evidence(
            status_path=args.official_statuses,
            slate=slate,
            assignments=assignments,
        )
    )
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
    )
    lineups = _validated_lineups(slate, assignments)
    findings = tuple(
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
    )
    result = {
        "run_id": run_id,
        "status": manifest.status,
        "upload_csv": manifest.output_path,
        "sha256": manifest.output_sha256,
        "manifest": str(manifest_path),
        "review_workbook": str(review),
        "blockers": list(manifest.blockers),
        "meaning": "Certification covers legality, current evidence, authorization, and exact bytes; it is not an EV claim.",
    }
    return (0 if manifest.status == "CERTIFIED" else 2), result


def command_certify(args: argparse.Namespace) -> int:
    code, result = _certify(args)
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


def _read_brackets(path: str | Path | None) -> dict[str, OwnershipBracket]:
    if not path:
        return {}
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != ("DK_ID", "LOW", "BASE", "HIGH"):
            raise ValueError("ownership bracket CSV must be DK_ID,LOW,BASE,HIGH")
        return {
            row["DK_ID"].strip(): OwnershipBracket(
                float(row["LOW"]), float(row["BASE"]), float(row["HIGH"])
            )
            for row in reader
            if row["DK_ID"].strip()
        }


def command_build(args: argparse.Namespace) -> int:
    started = time.perf_counter()
    run_id = args.run_id or _run_id(args.label)
    slate = parse_salaries(args.salaries)
    entries = parse_entries(args.entries)
    reconcile_template(entries, slate)
    model = load_opportunity_model(slate, args.team_projections, args.player_opportunities)
    tiers = parse_payout_csv(args.payouts)
    validate_payout_tiers(
        tiers,
        advertised_value=args.advertised_prize_value,
        ticket_face_value=args.ticket_face_value,
    )
    design_count = args.design_scenarios or (20_000 if slate.mode is EngineMode.SHOWDOWN else 10_000)
    select_count = args.select_scenarios or (50_000 if slate.mode is EngineMode.SHOWDOWN else 20_000)
    referee_count = args.referee_scenarios or (50_000 if slate.mode is EngineMode.SHOWDOWN else 20_000)
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
    brackets = _read_brackets(args.ownership_brackets)
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
    output_dir = Path(args.output_dir).resolve() / run_id
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
    referee_blocked, referee_reason = referee_blocks(
        select_net_delta=metrics.robust_net_payout_lcb,
        referee_net_delta=referee_metrics.robust_net_payout_lcb,
        uncertainty=0.0,
        safety_failure=False,
        hard_constraint_failure=False,
    )
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
    elapsed = time.perf_counter() - started
    report = {
        "run_id": run_id,
        "status": "DIAGNOSTIC_ASSIGNMENTS_READY_DO_NOT_UPLOAD",
        "label": "COLD_START_FIELD_MODEL",
        "assignments": str(assignment_path),
        "candidate_count": len(candidate_rosters),
        "milp_seed_candidate_count": len(solved),
        "economics_shortlist_count": len(economics_rosters),
        "candidate_family_coverage": coverage.counts,
        "missing_candidate_families": coverage.missing_registered_families,
        "scenario_counts": {
            "DESIGN": design_count,
            "SELECT": select_count,
            "REFEREE": referee_count,
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
        "referee": {
            "blocked": referee_blocked,
            "reason": referee_reason,
            "robust_net_payout_lcb": referee_metrics.robust_net_payout_lcb,
            "elite_probability": referee_metrics.elite_probability,
            "report_only": True,
        },
        "candidate_indices": list(metrics.candidate_indices),
        "elapsed_seconds": elapsed,
        "memory_limit_bytes": live_memory_limit(),
        "next": "Review assignments, supply official exact-ID ACTIVE evidence for every selected player, then run certify.",
        "warning": "Cold-start field outputs are diagnostic priors, not EV, ROI, win probability, or calibrated ownership.",
    }
    _write_json(output_dir / f"build_{run_id}.json", report)
    _print_json(report)
    return 0


def command_late_swap(args: argparse.Namespace) -> int:
    slate = parse_salaries(args.salaries)
    original = read_assignment_csv(args.original, slate.mode)
    proposed = read_assignment_csv(args.proposed, slate.mode)
    now = datetime.fromisoformat(args.as_of.replace("Z", "+00:00"))
    if now.tzinfo is None:
        raise ValueError("--as-of must include a timezone")
    audit = audit_late_swap(slate=slate, original=original, proposed=proposed, now=now)
    _print_json({"status": "PASS" if audit.valid else "FAIL", "problems": audit.problems})
    return 0 if audit.valid else 2


def command_settle(args: argparse.Namespace) -> int:
    entries = parse_entries(args.entries)
    snapshot = parse_standings(args.standings)
    require_entry_coverage(snapshot, {entry.entry_id for entry in entries.authorizations})
    result = {
        "status": "SETTLEMENT_CAPTURED",
        "standings_sha256": snapshot.sha256,
        "rows": len(snapshot.rows),
        "reserved_entry_coverage": len(entries.authorizations),
        "note": "Projection, ownership, and payout grading remains version-bound to the frozen pre-lock manifest.",
    }
    _print_json(result)
    return 0


def command_learn(args: argparse.Namespace) -> int:
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
    _print_json(
        {
            "promote": decision.promote,
            "tier": decision.tier,
            "influence_cap": decision.influence_cap,
            "promotion_failures": decision.reasons,
            "rollback": rollback,
            "rollback_reason": rollback_reason,
            "roi_policy": "realized ROI is descriptive and was not used in this decision",
        }
    )
    return 0 if decision.promote else 2


def command_status(args: argparse.Namespace) -> int:
    data = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    _print_json(
        {
            "run_id": data.get("run_id"),
            "status": data.get("status"),
            "output_path": data.get("output_path"),
            "output_sha256": data.get("output_sha256"),
            "blockers": data.get("blockers", []),
        }
    )
    return 0 if data.get("status") == "CERTIFIED" else 2


def command_audit(args: argparse.Namespace) -> int:
    data = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    problems: list[str] = []
    output_path = data.get("output_path")
    if data.get("status") == "CERTIFIED":
        if not output_path or not Path(output_path).exists():
            problems.append("certified output is missing")
        elif sha256_file(output_path) != data.get("output_sha256"):
            problems.append("certified output hash changed")
    elif output_path:
        problems.append("DO_NOT_UPLOAD manifest must not point to an upload CSV")
    _print_json({"status": "PASS" if not problems else "FAIL", "problems": problems})
    return 0 if not problems else 2


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


def _cowork_core_blockers(request: CoworkRunRequest) -> tuple[str, ...]:
    blockers = list(required_next_inputs(request))
    return tuple(
        blocker
        for blocker in blockers
        if not blocker.startswith("OFFICIAL_STATUS_REQUIRED:")
    )


def command_cowork_run(args: argparse.Namespace) -> int:
    requested = (
        CoworkRunRequest.from_json(args.request)
        if args.request
        else CoworkRunRequest(label=args.label or "slate")
    )
    if args.label:
        requested = replace(requested, label=args.label)
    request, unclassified = resolve_request_inputs(
        requested,
        input_dir=args.input_dir,
        salary_csv=args.salaries,
        entry_csv=args.entries,
    )
    ContestObjective(request.objective)
    run_id = args.run_id or _run_id(request.label)
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
    )
    snapshotted = _snapshot_cowork_request(request, run_id, intake["hashes"])
    request_path = DEFAULT_RUNS_DIR / run_id / "run_request.json"
    _write_json(request_path, snapshotted.to_dict())
    staged_workbook = DEFAULT_RUNS_DIR / run_id / "staged" / "cowork_input.xlsx"
    create_operator_input_workbook(staged_workbook)
    populate_operator_run_control(
        staged_workbook,
        _cowork_run_control_values(snapshotted),
    )
    doctor_report = doctor(PROJECT_ROOT)
    blockers = list(required_next_inputs(snapshotted))
    if not doctor_report.pass_status:
        blockers.insert(
            0,
            "ENVIRONMENT_DOCTOR_FAILED: the pinned runtime or workspace checks did not pass",
        )
    output_root = Path(args.output_dir).resolve() / run_id
    output_root.mkdir(parents=True, exist_ok=True)
    report_path = output_root / "cowork_run.json"

    if not doctor_report.pass_status or _cowork_core_blockers(snapshotted):
        review_path = output_root / f"NFL_DFS_Cowork_Review_{run_id}.xlsx"
        create_cowork_status_workbook(
            output_path=review_path,
            run_values=_cowork_run_control_values(snapshotted),
            blockers=blockers,
            report_path=report_path,
        )
        result = {
            "run_id": run_id,
            "status": "DO_NOT_UPLOAD",
            "stage": "RECONCILED",
            "mode": slate.mode.value,
            "authorized_entries": len(entries.authorizations),
            "contest_ids": sorted({entry.contest_id for entry in entries.authorizations}),
            "contest_names": sorted({entry.contest_name for entry in entries.authorizations}),
            "entry_fees": sorted({entry.entry_fee for entry in entries.authorizations}),
            "request": str(request_path),
            "review_workbook": str(review_path),
            "blockers": blockers,
            "unclassified_csvs": [str(path) for path in unclassified],
            "input_hashes": intake["hashes"],
            "doctor": json.loads(doctor_report.to_json()),
            "next": (
                "Claude should gather and freeze approved public evidence, populate the request, "
                "and ask the operator only for unavailable contest payout or field facts."
            ),
        }
        _write_json(report_path, result)
        _print_json(result)
        return 2

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
        official_statuses=snapshotted.official_status_csv,
        team_projections=snapshotted.team_projection_csv,
        player_opportunities=snapshotted.player_opportunity_csv,
        source_ledger=snapshotted.source_ledger_json,
        manual_guardrail=False if model_assisted else snapshotted.manual_guardrail,
        output_dir=str(Path(args.output_dir).resolve()),
        staged_workbook=str(staged_workbook),
    )
    code, certification = _certify(certify_args)
    result = {
        "run_id": run_id,
        "status": certification["status"],
        "stage": "CERTIFIED" if certification["status"] == "CERTIFIED" else "DO_NOT_UPLOAD",
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
    }
    _write_json(report_path, result)
    _print_json(result)
    return code


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
    if assignment_path and payout_path and advertised not in (None, ""):
        certify_args = argparse.Namespace(
            salaries=salaries,
            entries=entries,
            run_id=run_id,
            label=label,
            assignments=assignment_path,
            payouts=payout_path,
            advertised_prize_value=float(advertised),
            ticket_face_value=float(ticket_face) if ticket_face not in (None, "") else None,
            official_statuses=status_path or None,
            team_projections=team_path or None,
            player_opportunities=player_path or None,
            source_ledger=None,
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
    print("\nIntake passed. Add either ASSIGNMENT_CSV plus payout evidence, or both model-input CSVs plus payout and field-size evidence, then rerun .\\nfl.ps1 run.")
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
    parser.add_argument("--official-statuses")
    parser.add_argument("--team-projections")
    parser.add_argument("--player-opportunities")
    parser.add_argument("--source-ledger")
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
    cowork = subparsers.add_parser(
        "cowork-run",
        help="discover attached CSVs by schema and drive the fail-closed Cowork workflow",
    )
    cowork.add_argument("--input-dir")
    cowork.add_argument("--request")
    cowork.add_argument("--salaries")
    cowork.add_argument("--entries")
    cowork.add_argument("--label")
    cowork.add_argument("--run-id")
    cowork.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    cowork.set_defaults(func=command_cowork_run)
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
    late.add_argument("--salaries", required=True)
    late.add_argument("--original", required=True)
    late.add_argument("--proposed", required=True)
    late.add_argument("--as-of", required=True)
    late.set_defaults(func=command_late_swap)
    settle = subparsers.add_parser("settle")
    settle.add_argument("--entries", required=True)
    settle.add_argument("--standings", required=True)
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
    learn.set_defaults(func=command_learn)
    status = subparsers.add_parser("status")
    status.add_argument("--manifest", required=True)
    status.set_defaults(func=command_status)
    audit = subparsers.add_parser("audit")
    audit.add_argument("--manifest", required=True)
    audit.set_defaults(func=command_audit)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (ValueError, RuntimeError, FileNotFoundError, WorkbookLockedError) as exc:
        _print_json(
            {
                "status": "DO_NOT_UPLOAD",
                "error": type(exc).__name__,
                "message": str(exc),
            }
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
