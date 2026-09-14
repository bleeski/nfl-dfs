"""Registered full-fixture C3 scale and copied-package acceptance harness."""

from __future__ import annotations

import csv
import io
import json
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from .byte_lines import split_byte_lines
from .classic_portfolio import (
    assignment_artifact_bytes,
    audit_classic_portfolio,
    build_classic_candidate_bank,
    candidate_bank_bytes,
    exact_classic_assignments,
    solve_classic_portfolio,
)
from .classic_portfolio_policy import (
    classic_portfolio_policy_template,
    validate_classic_portfolio_policy_bytes,
)
from .classic_review import SCORE_SNAPSHOT_VERSION, create_classic_review_package
from .dk import parse_entries, parse_salaries
from .hashing import sha256_bytes, sha256_file
from .lineups import validate_lineup
from .portfolio_policy import canonical_decimal_json_bytes
from .workbook import create_cowork_status_workbook


REPORT_SCHEMA = "nfl_classic_c3_scale_acceptance_result_v1"
SELECTION_SCHEMA = "nfl_classic_prior_review_selection_c2_v1"
COVERAGE_SCHEMA = "nfl_classic_slate_coverage_c2_v1"
AUDIT_AT = datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc)


def _canonical_newline(value: Mapping[str, object]) -> bytes:
    return (
        json.dumps(dict(value), sort_keys=True, separators=(",", ":"), default=str)
        + "\n"
    ).encode("utf-8")


def _write(path: Path, raw: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return sha256_bytes(raw)


def _entry_bytes(source: bytes, entry_count: int) -> bytes:
    lines = split_byte_lines(source)
    if len(lines) < 4:
        raise ValueError("CLASSIC_C3_SCALE_ENTRY_FIXTURE_TOO_SHORT")
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\r\n")
    for index in range(entry_count):
        writer.writerow(
            (
                str(7000000001 + index),
                "C3 Full Fixture Scale Acceptance",
                "193028206",
                "$5",
                "", "", "", "", "", "", "", "", "", "",
                f"registered-scale-entry-{index + 1}",
            )
        )
    return lines[0] + output.getvalue().encode("utf-8") + b"".join(lines[3:])


def _fixture_objective(slate) -> dict[str, float]:
    """Stable test-only score; deliberately does not consume DraftKings APPG."""

    ordered = sorted(slate.players, key=lambda row: int(row.dk_id))
    return {
        row.dk_id: round(20.0 + (len(ordered) - index) / 1000.0, 6)
        for index, row in enumerate(ordered)
    }


def _process_peak_rss_bytes() -> int:
    if os.name != "nt":
        try:
            import resource

            peak = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
            return peak if peak > 10_000_000 else peak * 1024
        except (ImportError, OSError):
            return 0
    try:
        import ctypes
        from ctypes import wintypes

        class ProcessMemoryCountersEx(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
                ("PrivateUsage", ctypes.c_size_t),
            ]

        counters = ProcessMemoryCountersEx()
        counters.cb = ctypes.sizeof(counters)
        get_current_process = ctypes.windll.kernel32.GetCurrentProcess
        get_current_process.restype = wintypes.HANDLE
        handle = get_current_process()
        get_process_memory_info = ctypes.windll.psapi.GetProcessMemoryInfo
        get_process_memory_info.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(ProcessMemoryCountersEx),
            wintypes.DWORD,
        ]
        get_process_memory_info.restype = wintypes.BOOL
        ok = get_process_memory_info(
            handle, ctypes.byref(counters), counters.cb
        )
        return int(counters.PeakWorkingSetSize) if ok else 0
    except (AttributeError, OSError):
        return 0


def _create_current_evidence(root: Path, slate) -> tuple[Path, Path, dict[str, Path]]:
    observed = "2026-09-11T11:00:00+00:00"
    expires = "2026-09-13T16:00:00+00:00"
    status_buffer = io.StringIO(newline="")
    writer = csv.writer(status_buffer, lineterminator="\n")
    writer.writerow(("TEAM", "PLAYER_OR_GSIS_ID", "STATUS", "SOURCE_URL", "OBSERVED_AT"))
    for player in slate.players:
        writer.writerow(
            (
                player.team,
                player.dk_id,
                "ACTIVE",
                "https://raw.githubusercontent.com/openai/test/main/c3-scale-status.csv",
                observed,
            )
        )
    status_path = root / "evidence" / "official_status.csv"
    _write(status_path, status_buffer.getvalue().encode("utf-8"))

    role_root = root / "evidence" / "roles"
    source_paths: dict[str, Path] = {}
    sources: list[dict[str, object]] = []
    declarations: list[dict[str, object]] = []
    for team in sorted({player.team for player in slate.players}):
        players = [
            player
            for player in slate.players
            if player.team == team and player.position in {"QB", "RB", "WR", "TE"}
        ]
        recipients = [
            {
                "underlying_id": player.underlying_id,
                "dk_id": player.dk_id,
                "shares": {"fixture_role_share": round(1 / len(players), 12)},
            }
            for player in players
        ]
        declaration = {
            "team": team,
            "game_id": players[0].game_id,
            "recipients": recipients,
            "totals": {"fixture_role_share": 1.0},
            "unallocated": {"fixture_role_share": 0.0},
        }
        source_raw = _canonical_newline(declaration)
        digest = sha256_bytes(source_raw)
        source_path = role_root / "sources" / f"{digest}.json"
        _write(source_path, source_raw)
        artifact_key = f"offensive_role_source:{digest}"
        source_paths[artifact_key] = source_path
        sources.append(
            {
                "path": f"sources/{source_path.name}",
                "sha256": digest,
                "source_uri": f"https://example.invalid/c3-scale/{team}/role",
                "observed_at": observed,
                "captured_at": observed,
                "expires_at": expires,
                "license_decision": "TEST_FIXTURE_ONLY",
                "parser_version": "classic_c3_scale_role_v1",
                "transformation_version": "classic_c3_scale_fixture_v1",
                "support_kind": "NUMERICAL_ALLOCATION",
                "supporting_excerpt": source_raw.decode("utf-8").strip(),
                "synthetic": False,
            }
        )
        declarations.append({**declaration, "source_sha256": digest})
    role_path = role_root / "offensive_role_evidence.json"
    _write(
        role_path,
        _canonical_newline(
            {
                "schema_version": "nfl_classic_offensive_role_evidence_c1_v1",
                "transformation_version": "classic_c3_scale_fixture_v1",
                "salary_sha256": slate.salary_hash,
                "game_ids": [game.game_id for game in slate.games],
                "sources": sources,
                "declarations": declarations,
                "facts": [],
            }
        ),
    )
    return status_path, role_path, source_paths


def _prepare_artifacts(root: Path, salary_source: Path, entry_source: Path, scale: int, limits):
    root.mkdir(parents=True, exist_ok=False)
    salary = root / "inputs" / "DKSalaries.csv"
    entry = root / "inputs" / "DKEntries.csv"
    _write(salary, salary_source.read_bytes())
    _write(entry, _entry_bytes(entry_source.read_bytes(), scale))
    slate = parse_salaries(salary)
    template = parse_entries(entry)
    entry_ids = tuple(item.entry_id for item in template.authorizations)
    policy_document = classic_portfolio_policy_template(
        slate,
        entry_ids,
        entry_sha256=template.raw_hash,
        limits={
            key: limits[key]
            for key in (
                "candidate_limit",
                "candidate_total_milliseconds",
                "candidate_per_solve_milliseconds",
                "selection_milliseconds",
            )
        },
    )
    policy_source = root / "policy" / "classic_policy.json"
    source_raw = (json.dumps(policy_document, indent=2) + "\n").encode("utf-8")
    _write(policy_source, source_raw)
    validated = validate_classic_portfolio_policy_bytes(
        source_raw,
        slate=slate,
        entry_ids=entry_ids,
        entry_sha256=template.raw_hash,
    )
    if not validated.valid or validated.policy is None:
        raise ValueError(f"CLASSIC_C3_SCALE_POLICY_INVALID:{validated.blockers()}")
    policy = validated.policy
    policy_normalized = root / "policy" / "classic_policy.normalized.json"
    _write(policy_normalized, policy.canonical_bytes())

    objective = _fixture_objective(slate)
    candidate_started = time.perf_counter()
    bank = build_classic_candidate_bank(slate, objective, policy)
    candidate_elapsed = time.perf_counter() - candidate_started
    selection_started = time.perf_counter()
    selected = solve_classic_portfolio(policy, bank)
    selection_elapsed = time.perf_counter() - selection_started
    if not selected.passed:
        raise ValueError(f"CLASSIC_C3_SCALE_SELECTION_FAILED:{selected.status}")
    rosters = [bank.candidates[index].roster for index in selected.selected_candidate_indexes]
    assignments = exact_classic_assignments(entry_ids, rosters)

    candidate_path = root / "selection" / "classic_candidate_bank.json"
    candidate_raw = candidate_bank_bytes(policy, bank)
    candidate_sha = _write(candidate_path, candidate_raw)
    assignment_path = root / "selection" / "classic_assignment.json"
    assignment_raw = assignment_artifact_bytes(
        policy, assignments, candidate_bank_sha256=candidate_sha
    )
    assignment_sha = _write(assignment_path, assignment_raw)

    evidence_paths: dict[str, Path] = {}
    for name in (
        "team_source",
        "player_source",
        "identity_map",
        "team_projections",
        "player_opportunities",
        "source_ledger",
    ):
        path = root / "immutable" / f"{name}.json"
        _write(path, _canonical_newline({"schema_version": f"classic_c3_scale_{name}_v1"}))
        evidence_paths[name] = path
    team_splits = root / "immutable" / "team_splits.csv"
    _write(team_splits, b"TEAM,TEST_FIXTURE_VALUE\nALL,0\n")
    evidence_paths["team_splits"] = team_splits
    official_status, role_evidence, role_sources = _create_current_evidence(root, slate)
    evidence_paths["official_status_csv"] = official_status
    evidence_paths["offensive_role_evidence_json"] = role_evidence
    evidence_paths.update(role_sources)

    bound_names = {
        "team_source": "team_prior_sha256",
        "player_source": "player_prior_sha256",
        "identity_map": "identity_map_sha256",
        "team_projections": "team_projections_sha256",
        "player_opportunities": "player_opportunities_sha256",
        "source_ledger": "source_ledger_sha256",
        "team_splits": "team_splits_sha256",
        "official_status_csv": "official_status_csv_sha256",
        "offensive_role_evidence_json": "offensive_role_evidence_json_sha256",
    }
    bound_artifacts = {
        bound_names[name]: (path.read_bytes(), sha256_file(path))
        for name, path in evidence_paths.items()
        if name in bound_names
    }
    for name, path in role_sources.items():
        bound_artifacts[f"{name}_sha256"] = (path.read_bytes(), sha256_file(path))
    c2_audit = audit_classic_portfolio(
        slate=slate,
        normalized_policy_bytes=policy.canonical_bytes(),
        expected_normalized_policy_sha256=policy.normalized_sha256,
        source_policy_bytes=source_raw,
        expected_source_policy_sha256=sha256_bytes(source_raw),
        salary_bytes=salary.read_bytes(),
        expected_salary_sha256=slate.salary_hash,
        entry_bytes=entry.read_bytes(),
        expected_entry_sha256=template.raw_hash,
        bound_artifacts=bound_artifacts,
        candidate_bytes=candidate_raw,
        expected_candidate_sha256=candidate_sha,
        assignment_bytes=assignment_raw,
        expected_assignment_sha256=assignment_sha,
    )
    if not c2_audit.passed:
        raise ValueError(f"CLASSIC_C3_SCALE_C2_AUDIT_FAILED:{c2_audit.problems}")
    c2_audit_path = root / "selection" / "classic_portfolio_audit.json"
    c2_audit_raw = _canonical_newline(c2_audit.as_report())
    c2_audit_sha = _write(c2_audit_path, c2_audit_raw)

    artifacts = {
        **{name: str(path) for name, path in evidence_paths.items()},
        "portfolio_policy_source": str(policy_source),
        "portfolio_policy_normalized": str(policy_normalized),
        "classic_candidate_bank": str(candidate_path),
        "classic_assignment": str(assignment_path),
        "classic_portfolio_audit": str(c2_audit_path),
    }
    hashes = {name: sha256_file(path) for name, path in evidence_paths.items()}
    hashes.update(
        {
            "salary_csv": slate.salary_hash,
            "entry_csv": template.raw_hash,
            "portfolio_policy_source": sha256_bytes(source_raw),
            "portfolio_policy_normalized": policy.normalized_sha256,
            "classic_candidate_bank": candidate_sha,
            "classic_assignment": assignment_sha,
            "classic_portfolio_audit": c2_audit_sha,
        }
    )
    immutable_bindings = {
        "salary_sha256": slate.salary_hash,
        "entry_sha256": template.raw_hash,
        "team_prior_sha256": hashes["team_source"],
        "player_prior_sha256": hashes["player_source"],
        "identity_map_sha256": hashes["identity_map"],
        "team_projections_sha256": hashes["team_projections"],
        "player_opportunities_sha256": hashes["player_opportunities"],
        "source_ledger_sha256": hashes["source_ledger"],
        "official_status_sha256": hashes["official_status_csv"],
        "offensive_role_evidence_sha256": hashes["offensive_role_evidence_json"],
        "weather_evidence_sha256": None,
        "weather_source_sha256_by_game": {},
        "source_policy_sha256": hashes["portfolio_policy_source"],
        "normalized_policy_sha256": hashes["portfolio_policy_normalized"],
        "candidate_bank_sha256": candidate_sha,
        "assignment_sha256": assignment_sha,
        "classic_portfolio_audit_sha256": c2_audit_sha,
    }
    by_roster = {candidate.roster: candidate for candidate in bank.candidates}
    lineups = []
    for index, (_entry_id, roster) in enumerate(assignments, start=1):
        valid = validate_lineup(slate, roster)
        assert valid.lineup is not None
        candidate = by_roster[roster]
        lineups.append(
            {
                "index": index,
                "roster": list(roster),
                "salary": valid.lineup.salary,
                "prior_points": round(candidate.prior_points, 6),
                "canonical_key": valid.lineup.canonical_key,
                "solver_status": selected.model_status,
            }
        )
    enforcement = {
        "status": "ENFORCED_AND_INDEPENDENTLY_AUDITED",
        "candidate_bank_status": bank.status,
        "joint_selection_status": selected.status,
        "optimality_scope": "ACTUAL_CANDIDATE_BANK",
    }
    selection_record = {
        "schema_version": SELECTION_SCHEMA,
        "artifact_class": "REVIEW_ONLY_NOT_DRAFTKINGS_UPLOAD",
        "FILE_VALID": True,
        "EVIDENCE_STATE": "PASS",
        "MODEL_STATUS": "PRIOR_ONLY",
        "RELEASE_DECISION": "DO_NOT_UPLOAD",
        "mode": "CLASSIC",
        "draft_group": slate.draft_group,
        "scoring_version": slate.scoring_version,
        "immutable_bindings": immutable_bindings,
        "assignments_by_entry_id": {entry_id: list(roster) for entry_id, roster in assignments},
        "entry_assignments": [
            {"entry_id": entry_id, "roster": list(roster)} for entry_id, roster in assignments
        ],
        "lineups": lineups,
        "objective": "TEST_ONLY_DETERMINISTIC_FIXTURE_RANK_NOT_APPG",
        "limitations": [
            "TEST_ONLY_SCALE_OBJECTIVE_NOT_MODEL_PERFORMANCE",
            "NOT_CALIBRATED_EV_ROI_WIN_OR_CASH_PROBABILITY",
            "NO_OWNERSHIP_FIELD_DUPLICATION_PAYOUT_OR_ECONOMICS",
            "NOT_UPLOAD_READY",
        ],
        "portfolio_policy": {
            "source_policy_sha256": hashes["portfolio_policy_source"],
            "normalized_policy_sha256": hashes["portfolio_policy_normalized"],
            "candidate_bank_sha256": candidate_sha,
            "assignment_sha256": assignment_sha,
            "audit_sha256": c2_audit_sha,
            "enforcement": enforcement,
            "independent_audit": c2_audit.as_report(),
        },
    }
    selection_path = root / "selection" / "classic_selection.json"
    selection_sha = _write(selection_path, _canonical_newline(selection_record))
    artifacts["selection_report"] = str(selection_path)
    hashes["selection_report"] = selection_sha

    coverage_record = {
        "schema_version": COVERAGE_SCHEMA,
        "artifact_class": "COMPLETE_SLATE_REVIEW_COVERAGE",
        "FILE_VALID": True,
        "EVIDENCE_STATE": "PASS",
        "MODEL_STATUS": "PRIOR_ONLY",
        "RELEASE_DECISION": "DO_NOT_UPLOAD",
        "mode": "CLASSIC",
        "immutable_bindings": immutable_bindings,
        "games": [game.game_id for game in slate.games],
        "official_status_coverage": {"selected_without_row": []},
        "selected_evidence_gate": {"status": "PASS", "gaps": []},
        "pool_coverage": {
            "salary_people": len(slate.players),
            "selectable_people": len(slate.players),
            "excluded_people": 0,
            "unallocated": {"test_fixture": 0},
        },
        "conservation": {
            "declared_totals_by_team": {},
            "declared_unallocated_by_team": {},
            "basis": "TEST_ONLY_SCALE_EVIDENCE",
        },
        "policy_coverage": {
            "candidate_bank": {
                "status": bank.status,
                "completion_scope": (
                    "EXHAUSTIVE_MODELED_LINEUP_SPACE"
                    if bank.exhaustive
                    else "BOUNDED_ACTUAL_CANDIDATE_BANK"
                ),
                "requested_candidates": bank.requested_candidates,
                "produced_candidates": len(bank.candidates),
                "coverage": bank.coverage(),
            },
            "independent_audit": c2_audit.as_report(),
        },
    }
    coverage_path = root / "selection" / "classic_complete_slate_coverage.json"
    coverage_sha = _write(coverage_path, _canonical_newline(coverage_record))
    artifacts["complete_slate_coverage"] = str(coverage_path)
    hashes["complete_slate_coverage"] = coverage_sha

    selected_ids = sorted({dk_id for _entry, roster in assignments for dk_id in roster}, key=int)
    score_record = {
        "schema_version": SCORE_SNAPSHOT_VERSION,
        "salary_sha256": slate.salary_hash,
        "assignment_sha256": assignment_sha,
        "scores_by_dk_id": {dk_id: objective[dk_id] for dk_id in selected_ids},
        "metric": "TEST_ONLY_DETERMINISTIC_FIXTURE_RANK_NOT_APPG",
        "not_a_claim_of": "MODEL_PERFORMANCE_CEILING_LEVERAGE_EV_ROI_WIN_OR_CASH_PROBABILITY",
    }
    score_path = root / "selection" / "classic_selected_scores.json"
    score_sha = _write(score_path, _canonical_newline(score_record))
    artifacts["classic_selected_scores"] = str(score_path)
    hashes["classic_selected_scores"] = score_sha
    return {
        "salary": salary,
        "entry": entry,
        "slate": slate,
        "template": template,
        "policy": policy,
        "bank": bank,
        "selection": selected,
        "candidate_elapsed": candidate_elapsed,
        "selection_elapsed": selection_elapsed,
        "artifacts": artifacts,
        "hashes": hashes,
    }


def run_classic_c3_scale_acceptance(
    *,
    repo_root: str | Path,
    work_root: str | Path,
    entry_count: int,
    limits_path: str | Path | None = None,
) -> dict[str, object]:
    repo = Path(repo_root).resolve()
    work = Path(work_root).resolve()
    config_path = Path(limits_path).resolve() if limits_path else repo / "config" / "classic_c3_scale_acceptance_v1.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config.get("schema_version") != "nfl_classic_c3_scale_acceptance_limits_v1":
        raise ValueError("CLASSIC_C3_SCALE_LIMITS_SCHEMA_MISMATCH")
    raw_limits = config.get("scales", {}).get(str(entry_count))
    if not isinstance(raw_limits, dict):
        raise ValueError(f"CLASSIC_C3_SCALE_NOT_REGISTERED:{entry_count}")
    limits = dict(raw_limits)
    fixture = config["fixture"]
    salary_source = repo / fixture["salary_path"]
    entry_source = repo / "tests" / "fixtures" / "supplied" / "DKEntries CSV.csv"
    if sha256_file(salary_source) != fixture["salary_sha256"]:
        raise ValueError("CLASSIC_C3_SCALE_SALARY_FIXTURE_HASH_MISMATCH")
    if work.exists():
        raise ValueError(f"CLASSIC_C3_SCALE_WORK_ROOT_EXISTS:{work}")

    started = time.perf_counter()
    source_root = work / "s"
    prepared = _prepare_artifacts(source_root, salary_source, entry_source, entry_count, limits)
    slate = prepared["slate"]
    if (
        len(slate.players) != fixture["expected_people"]
        or len({player.team for player in slate.players}) != fixture["expected_teams"]
        or len(slate.games) != fixture["expected_games"]
    ):
        raise ValueError("CLASSIC_C3_SCALE_FULL_FIXTURE_IDENTITY_MISMATCH")
    review_dir = source_root / "output" / "review"
    first = create_classic_review_package(
        salary_path=prepared["salary"],
        entry_path=prepared["entry"],
        artifacts=prepared["artifacts"],
        expected_hashes=prepared["hashes"],
        audit_at=AUDIT_AT,
        output_path=review_dir / f"DK_REVIEW_ENTRY_scale-{entry_count}.csv",
        output_dir=review_dir,
        package_root=source_root,
    )
    workbook_path = source_root / "output" / f"NFL_DFS_C3_Scale_{entry_count}.xlsx"
    create_cowork_status_workbook(
        output_path=workbook_path,
        run_values={"RUN_LABEL": f"c3-scale-{entry_count}"},
        blockers=(),
        report_path=source_root / "output" / "classic_c3_scale_acceptance.json",
        truth_values={
            "FILE_VALID": True,
            "EVIDENCE_STATE": "PASS",
            "MODEL_STATUS": "PRIOR_ONLY",
            "RELEASE_DECISION": "DO_NOT_UPLOAD",
        },
        readable_review=first.data,
        review_csv_path=first.export_path,
    )

    copy_root = work / "c"
    shutil.copytree(source_root, copy_root)
    copied_review = copy_root / "output" / "review"
    for name in (
        f"DK_REVIEW_ENTRY_scale-{entry_count}.csv",
        "classic_review_export_audit.json",
        "prior_only_readable_review.json",
        "prior_only_readable_review.html",
    ):
        (copied_review / name).unlink()
    copied_artifacts = {
        name: str(copy_root / Path(path).resolve().relative_to(source_root))
        for name, path in prepared["artifacts"].items()
    }
    second = create_classic_review_package(
        salary_path=copy_root / Path(prepared["salary"]).relative_to(source_root),
        entry_path=copy_root / Path(prepared["entry"]).relative_to(source_root),
        artifacts=copied_artifacts,
        expected_hashes=prepared["hashes"],
        audit_at=AUDIT_AT,
        output_path=copied_review / f"DK_REVIEW_ENTRY_scale-{entry_count}.csv",
        output_dir=copied_review,
        package_root=copy_root,
    )
    canonical_pairs = {
        "policy_source": (
            source_root / Path(prepared["artifacts"]["portfolio_policy_source"]).relative_to(source_root),
            copy_root / Path(prepared["artifacts"]["portfolio_policy_source"]).relative_to(source_root),
        ),
        "policy_normalized": (
            Path(prepared["artifacts"]["portfolio_policy_normalized"]),
            Path(copied_artifacts["portfolio_policy_normalized"]),
        ),
        "candidate_bank": (Path(prepared["artifacts"]["classic_candidate_bank"]), Path(copied_artifacts["classic_candidate_bank"])),
        "assignment": (Path(prepared["artifacts"]["classic_assignment"]), Path(copied_artifacts["classic_assignment"])),
        "c2_audit": (Path(prepared["artifacts"]["classic_portfolio_audit"]), Path(copied_artifacts["classic_portfolio_audit"])),
        "selection": (Path(prepared["artifacts"]["selection_report"]), Path(copied_artifacts["selection_report"])),
        "coverage": (Path(prepared["artifacts"]["complete_slate_coverage"]), Path(copied_artifacts["complete_slate_coverage"])),
        "score_snapshot": (Path(prepared["artifacts"]["classic_selected_scores"]), Path(copied_artifacts["classic_selected_scores"])),
        "c3_audit": (Path(first.audit_path), Path(second.audit_path)),
        "readable_json": (Path(first.json_path), Path(second.json_path)),
        "readable_html": (Path(first.html_path), Path(second.html_path)),
        "review_csv": (Path(first.export_path), Path(second.export_path)),
    }
    replay_hashes = {
        name: {"source": sha256_file(left), "copy": sha256_file(right)}
        for name, (left, right) in canonical_pairs.items()
    }
    replay_identical = all(value["source"] == value["copy"] for value in replay_hashes.values())
    elapsed = time.perf_counter() - started
    peak_rss = _process_peak_rss_bytes()
    bank = prepared["bank"]
    selected = prepared["selection"]
    within_limits = elapsed <= float(limits["wall_seconds_limit"]) and (
        peak_rss == 0 or peak_rss <= int(limits["peak_rss_bytes_limit"])
    )
    status = "PASS" if replay_identical and within_limits else (
        "CLASSIC_C3_SCALE_REPLAY_MISMATCH" if not replay_identical else "FEASIBLE_LIMIT"
    )
    report = {
        "schema_version": REPORT_SCHEMA,
        "status": status,
        "entry_count": entry_count,
        "fixture": {
            "salary_sha256": slate.salary_hash,
            "people": len(slate.players),
            "teams": len({player.team for player in slate.players}),
            "games": len(slate.games),
        },
        "registered_limits": limits,
        "objective": config["objective"],
        "candidate_bank": {
            "requested": bank.requested_candidates,
            "produced": len(bank.candidates),
            "status": bank.status,
            "completeness": "EXHAUSTIVE" if bank.exhaustive else "CANDIDATE_BANK_INCOMPLETE",
            "policy_feasible_chain_status": bank.feasible_chain_status,
            "family_policy_coverage": bank.coverage(),
            "elapsed_seconds": round(float(prepared["candidate_elapsed"]), 6),
            "solver_nodes": bank.solver_node_count,
            "solver_max_gap": bank.solver_max_gap,
            "traced_python_peak_bytes": bank.peak_traced_python_bytes,
        },
        "joint_selection": {
            "status": selected.status,
            "optimality_scope": "ACTUAL_CANDIDATE_BANK",
            "elapsed_seconds": round(float(prepared["selection_elapsed"]), 6),
            "nodes": selected.node_count,
            "gap": selected.mip_gap,
            "selected_entries": len(selected.selected_candidate_indexes),
        },
        "c3": {
            "downstream_audit": first.audit["status"],
            "exact_entry_order": first.audit["entry_ids"],
            "review_csv_sha256": first.export_sha256,
            "workbook_path": str(workbook_path.relative_to(work)),
            "workbook_sha256": sha256_file(workbook_path),
            "no_dk_upload": not list(work.rglob("DK_UPLOAD_*.csv")),
        },
        "copied_package_replay": {
            "status": "PASS" if replay_identical else "FAIL",
            "hashes": replay_hashes,
        },
        "resources": {
            "wall_seconds": round(elapsed, 6),
            "process_peak_rss_bytes": peak_rss,
            "traced_python_peak_bytes": bank.peak_traced_python_bytes,
            "within_registered_limits": within_limits,
        },
        "truths": {
            "FILE_VALID": status == "PASS",
            "EVIDENCE_STATE": "PASS",
            "MODEL_STATUS": "PRIOR_ONLY",
            "RELEASE_DECISION": "DO_NOT_UPLOAD",
        },
        "limitations": [
            "BOUNDED_CANDIDATE_BANK_NOT_FULL_SLATE_OPTIMALITY",
            "TEST_ONLY_DETERMINISTIC_FIXTURE_OBJECTIVE_NOT_MODEL_PERFORMANCE",
            "NO_OWNERSHIP_FIELD_DUPLICATION_PAYOUT_ECONOMICS_OR_EV",
            "REVIEW_ONLY_NOT_UPLOAD_AUTHORIZATION",
        ],
    }
    report_path = source_root / "output" / "classic_c3_scale_acceptance.json"
    _write(report_path, _canonical_newline(report))
    report["report_path"] = str(report_path)
    return report
