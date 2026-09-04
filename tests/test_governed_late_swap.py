from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import nfl_dfs.late_swap as late_swap_module
from nfl_dfs.cli import main
from nfl_dfs.contracts import EvidenceRecord, EvidenceState
from nfl_dfs.dk import CLASSIC_COLUMNS, parse_entries
from nfl_dfs.evidence import evaluate_hard_gates
from nfl_dfs.hashing import sha256_file
from nfl_dfs.late_swap import derive_late_swap_authorization, govern_late_swap
from nfl_dfs.lineups import (
    LineupValidationError,
    validate_lineup,
    write_late_swap_bytes,
    write_upload_bytes,
)
from nfl_dfs.optimizer import LineupOptimizer
from nfl_dfs.referee import audit_late_swap_output_bytes

from .conftest import FIXTURE_ROOT


AS_OF = datetime.fromisoformat("2026-09-13T15:00:00-04:00")


def _write_assignments(path: Path, assignments: dict[str, tuple[str, ...]]) -> Path:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\r\n")
        writer.writerow(("Entry ID",) + CLASSIC_COLUMNS)
        for entry_id in sorted(assignments):
            writer.writerow((entry_id,) + assignments[entry_id])
    return path


def _lineups(slate, entries) -> dict[str, tuple[str, ...]]:
    scores = {player.dk_id: 50_000 / max(player.salary, 1) for player in slate.players}
    optimizer = LineupOptimizer(slate)
    result: dict[str, tuple[str, ...]] = {}
    for entry in sorted(entries.authorizations, key=lambda value: value.entry_id):
        solved = optimizer.solve(scores)
        assert solved.roster is not None
        result[entry.entry_id] = solved.roster
        optimizer.add_no_good(solved.roster)
    return result


def _valid_proposal(slate, original: dict[str, tuple[str, ...]]):
    by_id = {player.dk_id: player for player in slate.players}
    proposed = dict(original)
    entry_id = sorted(original)[0]
    roster = original[entry_id]
    for slot, old_id in enumerate(roster):
        old = by_id[old_id]
        if old.lock_at <= AS_OF:
            continue
        for candidate in slate.players:
            if candidate.dk_id in roster or candidate.lock_at <= AS_OF:
                continue
            changed = list(roster)
            changed[slot] = candidate.dk_id
            validation = validate_lineup(slate, changed)
            if validation.valid:
                proposed[entry_id] = tuple(changed)
                if len(set(proposed.values())) == len(proposed):
                    return proposed, entry_id, slot, candidate.dk_id
    raise AssertionError("fixture did not provide a valid unlocked replacement")


def _write_prior_manifest(
    path: Path,
    *,
    slate,
    entries,
    assignments_path: Path,
    prior_output: Path,
) -> Path:
    now = datetime.now(timezone.utc).isoformat()
    output_hash = sha256_file(prior_output)
    payload = {
        "manifest_version": "certification_manifest_v1",
        "run_id": "prior-certified",
        "status": "CERTIFIED",
        "created_at": now,
        "input_hashes": {
            "salary": slate.salary_hash,
            "entries": entries.raw_hash,
            "assignments": sha256_file(assignments_path),
        },
        "config_hashes": {},
        "model_hashes": {},
        "output_path": str(prior_output.resolve()),
        "output_sha256": output_hash,
        "evidence": [
            {
                "subject": "slate",
                "field": "salary_pool",
                "value": True,
                "source_artifact_id": slate.salary_hash,
                "hard_gate": True,
                "state": "PASS",
                "reason": "parsed",
            },
            {
                "subject": "entries",
                "field": "entry_authorization",
                "value": True,
                "source_artifact_id": entries.raw_hash,
                "hard_gate": True,
                "state": "PASS",
                "reason": "reconciled",
            },
            {
                "subject": "prior-certified",
                "field": "final_bytes",
                "value": output_hash,
                "hard_gate": True,
                "state": "PASS",
                "reason": "matched",
            },
        ],
        "solver_proof": {},
        "runtime": {},
        "blockers": [],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _write_evidence(
    root: Path,
    *,
    slate,
    proposed: dict[str, tuple[str, ...]],
    eligibility_state: str = "PASS",
    eligible: bool = True,
    eligibility_contest_id: str = "193028206",
    report_mutator=None,
) -> tuple[Path, Path]:
    eligibility = root / "eligibility.json"
    eligibility.write_text(
        json.dumps(
            {
                "schema_version": "nfl_late_swap_eligibility_v1",
                "contest_id": eligibility_contest_id,
                "bulk_late_swap_eligible": eligible,
                "evidence_state": eligibility_state,
                "source_url": "https://example.com/contest-details",
                "observed_at": "2026-09-13T14:58:00-04:00",
                "expires_at": "2026-09-13T18:00:00-04:00",
            }
        ),
        encoding="utf-8",
    )
    by_id = {player.dk_id: player for player in slate.players}
    games_by_team = {
        team: game
        for game in slate.games
        for team in (game.away_team, game.home_team)
    }
    selected_unlocked = {
        dk_id
        for roster in proposed.values()
        for dk_id in roster
        if by_id[dk_id].lock_at > AS_OF
    }
    reports = [
        {
            "team": team,
            "game_id": games_by_team[team].game_id,
            "inactive_dk_ids": [],
            "evidence_state": "PASS",
            "source_url": f"https://example.com/inactives/{team}",
            "observed_at": "2026-09-13T14:56:00-04:00",
        }
        for team in sorted({by_id[dk_id].team for dk_id in selected_unlocked})
    ]
    if report_mutator is not None:
        report_mutator(reports, by_id, selected_unlocked)
    inactive = root / "inactive-reports.json"
    inactive.write_text(
        json.dumps(
            {
                "schema_version": "nfl_team_inactive_reports_v1",
                "reports": reports,
            }
        ),
        encoding="utf-8",
    )
    return eligibility, inactive


def _case(tmp_path: Path, slate, entries):
    tmp_path.mkdir(parents=True, exist_ok=True)
    salaries = tmp_path / "salaries.csv"
    salaries.write_bytes(
        (FIXTURE_ROOT / "DKSalaries Salary CSV Classic.csv").read_bytes()
    )
    original = _lineups(slate, entries)
    proposed, changed_entry, changed_slot, replacement = _valid_proposal(slate, original)
    prior_assignments = _write_assignments(tmp_path / "prior.csv", original)
    proposed_assignments = _write_assignments(tmp_path / "proposed.csv", proposed)
    prior_output = tmp_path / "prior-output.csv"
    prior_output.write_bytes(write_upload_bytes(entries, original))
    current = tmp_path / "current-prefilled.csv"
    current.write_bytes(prior_output.read_bytes())
    prior_manifest = _write_prior_manifest(
        tmp_path / "prior-manifest.json",
        slate=slate,
        entries=entries,
        assignments_path=prior_assignments,
        prior_output=prior_output,
    )
    eligibility, inactive = _write_evidence(
        tmp_path,
        slate=slate,
        proposed=proposed,
    )
    return {
        "original": original,
        "proposed": proposed,
        "changed_entry": changed_entry,
        "changed_slot": changed_slot,
        "replacement": replacement,
        "prior_assignments": prior_assignments,
        "proposed_assignments": proposed_assignments,
        "prior_output": prior_output,
        "current": current,
        "prior_manifest": prior_manifest,
        "eligibility": eligibility,
        "inactive": inactive,
        "salaries": salaries,
        "output_dir": tmp_path / "outputs",
    }


def _govern(case, slate, run_id="late-valid"):
    return govern_late_swap(
        run_id=run_id,
        salaries_path=case["salaries"],
        current_entries_path=case["current"],
        prior_manifest_path=case["prior_manifest"],
        prior_assignments_path=case["prior_assignments"],
        proposed_assignments_path=case["proposed_assignments"],
        eligibility_evidence_path=case["eligibility"],
        inactive_reports_path=case["inactive"],
        output_directory=case["output_dir"],
        as_of=AS_OF,
    )


def _assert_blocked(manifest, manifest_path: Path) -> None:
    assert manifest.status == "DO_NOT_UPLOAD"
    assert manifest_path.exists()
    assert manifest.output_path is None
    assert manifest.output_sha256 is None
    assert manifest.release_decision.value == "DO_NOT_UPLOAD"
    assert not list(manifest_path.parent.glob("DK_UPLOAD_*.csv"))


def test_end_to_end_governed_late_swap_writes_and_audits_exact_bytes(
    tmp_path: Path, classic_slate, classic_entries
) -> None:
    case = _case(tmp_path, classic_slate, classic_entries)
    manifest, manifest_path = _govern(case, classic_slate)
    assert manifest.status == "CERTIFIED", manifest.blockers
    assert manifest.file_valid
    assert manifest.evidence_state.value == "PASS"
    assert manifest.release_decision.value == "CERTIFIED_UPLOAD_PACKAGE"
    assert manifest_path.exists()
    output = Path(manifest.output_path or "")
    assert output.exists()
    assert sha256_file(output) == manifest.output_sha256
    reparsed = parse_entries(output)
    assert {
        entry.entry_id: entry.existing_cells for entry in reparsed.authorizations
    } == case["proposed"]
    assert manifest.input_hashes["prior_manifest"] == sha256_file(case["prior_manifest"])
    assert manifest.input_hashes["prior_assignments"] == sha256_file(
        case["prior_assignments"]
    )
    assert manifest.input_hashes["current_entries"] == sha256_file(case["current"])
    assert manifest.replaceable_cells[case["changed_entry"]] == (
        case["changed_slot"],
    )
    source = case["current"].read_bytes()
    result = output.read_bytes()
    assert source != result
    assert any(record.field == "final_bytes" for record in manifest.evidence)
    serialized = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert serialized["FILE_VALID"] is True
    assert serialized["EVIDENCE_STATE"] == "PASS"
    assert serialized["MODEL_STATUS"] == "UNVALIDATED"
    assert serialized["RELEASE_DECISION"] == "CERTIFIED_UPLOAD_PACKAGE"


def test_locked_player_removal_addition_and_movement_fail(
    tmp_path: Path, classic_slate, classic_entries
) -> None:
    case = _case(tmp_path, classic_slate, classic_entries)
    by_id = {player.dk_id: player for player in classic_slate.players}
    entry_id = sorted(case["original"])[0]
    original = case["original"][entry_id]
    locked_slot = next(
        index for index, dk_id in enumerate(original) if by_id[dk_id].lock_at <= AS_OF
    )
    unlocked_slot = next(
        index for index, dk_id in enumerate(original) if by_id[dk_id].lock_at > AS_OF
    )
    changed = list(original)
    changed[locked_slot], changed[unlocked_slot] = changed[unlocked_slot], changed[locked_slot]
    case["proposed"][entry_id] = tuple(changed)
    _write_assignments(case["proposed_assignments"], case["proposed"])
    manifest, path = _govern(case, classic_slate, "locked-movement")
    _assert_blocked(manifest, path)
    assert any("locked prior player" in blocker for blocker in manifest.blockers)
    assert any("already-locked player" in blocker for blocker in manifest.blockers)


def test_adding_already_locked_player_fails(
    tmp_path: Path, classic_slate, classic_entries
) -> None:
    case = _case(tmp_path, classic_slate, classic_entries)
    by_id = {player.dk_id: player for player in classic_slate.players}
    entry_id = sorted(case["original"])[0]
    roster = list(case["original"][entry_id])
    unlocked_slot = next(
        index for index, dk_id in enumerate(roster) if by_id[dk_id].lock_at > AS_OF
    )
    roster[unlocked_slot] = next(
        player.dk_id
        for player in classic_slate.players
        if player.lock_at <= AS_OF and player.dk_id not in roster
    )
    case["proposed"][entry_id] = tuple(roster)
    _write_assignments(case["proposed_assignments"], case["proposed"])
    manifest, path = _govern(case, classic_slate, "locked-add")
    _assert_blocked(manifest, path)
    assert any("already-locked player" in blocker for blocker in manifest.blockers)


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ("manifest-status", "PRIOR_MANIFEST_NOT_CERTIFIED"),
        ("manifest-salary", "PRIOR_MANIFEST_SALARY_HASH_MISMATCH"),
        ("manifest-template", "PRIOR_TEMPLATE_HASH_EVIDENCE_MISMATCH"),
        ("prior-assignment", "PRIOR_ASSIGNMENT_HASH_MISMATCH"),
        ("prior-output", "PRIOR_CERTIFIED_OUTPUT_HASH_MISMATCH"),
    ],
)
def test_tampered_prior_state_fails_closed(
    tmp_path: Path, classic_slate, classic_entries, mutation: str, expected: str
) -> None:
    case = _case(tmp_path, classic_slate, classic_entries)
    if mutation.startswith("manifest-"):
        payload = json.loads(case["prior_manifest"].read_text(encoding="utf-8"))
        if mutation == "manifest-status":
            payload["status"] = "DO_NOT_UPLOAD"
            payload["output_path"] = None
            payload["output_sha256"] = None
        elif mutation == "manifest-salary":
            payload["input_hashes"]["salary"] = "0" * 64
        else:
            payload["input_hashes"]["entries"] = "0" * 64
        case["prior_manifest"].write_text(json.dumps(payload), encoding="utf-8")
    elif mutation == "prior-assignment":
        case["prior_assignments"].write_bytes(
            case["prior_assignments"].read_bytes() + b"\r\n"
        )
    else:
        case["prior_output"].write_bytes(case["prior_output"].read_bytes() + b"\r\n")
    manifest, path = _govern(case, classic_slate, f"tamper-{mutation}")
    _assert_blocked(manifest, path)
    assert any(expected in blocker for blocker in manifest.blockers)


def test_changed_entry_ids_and_partially_prefilled_rows_fail(
    tmp_path: Path, classic_slate, classic_entries
) -> None:
    case = _case(tmp_path, classic_slate, classic_entries)
    missing = dict(case["proposed"])
    missing.pop(sorted(missing)[0])
    _write_assignments(case["proposed_assignments"], missing)
    manifest, path = _govern(case, classic_slate, "missing-entry")
    _assert_blocked(manifest, path)
    assert any("Entry-ID set changed" in blocker for blocker in manifest.blockers)

    second = _case(tmp_path / "partial", classic_slate, classic_entries)
    raw = second["current"].read_bytes()
    roster_id = second["original"][sorted(second["original"])[0]][0].encode("ascii")
    second["current"].write_bytes(raw.replace(roster_id, b"", 1))
    manifest, path = _govern(second, classic_slate, "partial-prefill")
    _assert_blocked(manifest, path)
    assert "CURRENT_TEMPLATE_MUST_BE_FULLY_PREFILLED" in manifest.blockers


@pytest.mark.parametrize("state", ["UNKNOWN", "STALE", "CONFLICTED", "NOT_YET_DUE"])
def test_nonpass_and_not_yet_due_evidence_prevent_final_output(
    tmp_path: Path, classic_slate, classic_entries, state: str
) -> None:
    case = _case(tmp_path, classic_slate, classic_entries)
    payload = json.loads(case["eligibility"].read_text(encoding="utf-8"))
    payload["evidence_state"] = state
    case["eligibility"].write_text(json.dumps(payload), encoding="utf-8")
    manifest, path = _govern(case, classic_slate, f"evidence-{state.lower()}")
    _assert_blocked(manifest, path)
    assert manifest.file_valid
    assert manifest.proposed_output_sha256 is not None
    assert any(f":{state}:" in blocker for blocker in manifest.blockers)


def test_missing_unverified_and_ineligible_contest_evidence_fail(
    tmp_path: Path, classic_slate, classic_entries
) -> None:
    for suffix, change in (
        ("missing", "missing"),
        ("wrong-contest", "contest"),
        ("ineligible", "eligible"),
    ):
        root = tmp_path / suffix
        case = _case(root, classic_slate, classic_entries)
        if change == "missing":
            case["eligibility"].unlink()
        else:
            payload = json.loads(case["eligibility"].read_text(encoding="utf-8"))
            if change == "contest":
                payload["contest_id"] = "999999999"
            else:
                payload["bulk_late_swap_eligible"] = False
            case["eligibility"].write_text(json.dumps(payload), encoding="utf-8")
        manifest, path = _govern(case, classic_slate, f"eligibility-{suffix}")
        _assert_blocked(manifest, path)
        assert manifest.file_valid
        assert manifest.proposed_output_sha256 is not None


@pytest.mark.parametrize("kind", ["expired", "invalid-url", "not-applicable"])
def test_invalid_or_expired_eligibility_contract_fails(
    tmp_path: Path, classic_slate, classic_entries, kind: str
) -> None:
    case = _case(tmp_path, classic_slate, classic_entries)
    payload = json.loads(case["eligibility"].read_text(encoding="utf-8"))
    if kind == "expired":
        payload["expires_at"] = "2026-09-13T14:59:00-04:00"
    elif kind == "invalid-url":
        payload["source_url"] = "http://example.com/contest-details"
    else:
        payload["evidence_state"] = "NOT_APPLICABLE"
    case["eligibility"].write_text(json.dumps(payload), encoding="utf-8")
    manifest, path = _govern(case, classic_slate, f"eligibility-{kind}")
    _assert_blocked(manifest, path)


def test_negative_list_supports_explicit_empty_and_nonempty_reports(
    tmp_path: Path, classic_slate, classic_entries
) -> None:
    case = _case(tmp_path, classic_slate, classic_entries)
    payload = json.loads(case["inactive"].read_text(encoding="utf-8"))
    assert any(report["inactive_dk_ids"] == [] for report in payload["reports"])
    by_id = {player.dk_id: player for player in classic_slate.players}
    selected = {dk_id for roster in case["proposed"].values() for dk_id in roster}
    report = payload["reports"][0]
    report["inactive_dk_ids"] = [
        player.dk_id
        for player in classic_slate.players
        if player.team == report["team"] and player.dk_id not in selected
    ][:1]
    assert report["inactive_dk_ids"]
    case["inactive"].write_text(json.dumps(payload), encoding="utf-8")
    manifest, _ = _govern(case, classic_slate, "nonempty-negative-list")
    assert manifest.status == "CERTIFIED", manifest.blockers
    assert all(by_id[dk_id].team == report["team"] for dk_id in report["inactive_dk_ids"])


@pytest.mark.parametrize(
    ("kind", "needle"),
    [
        ("missing-team", "UNKNOWN"),
        ("selected-inactive", "officially inactive"),
        ("unknown-id", "unknown inactive exact DK ID"),
        ("team-mismatch", "inactive player/team conflict"),
        ("duplicate-team", "duplicate or conflicting report"),
        ("future", "future inactive-report observation"),
        ("stale", "STALE"),
        ("invalid-url", "invalid HTTPS source URL"),
    ],
)
def test_team_report_fail_closed_cases(
    tmp_path: Path, classic_slate, classic_entries, kind: str, needle: str
) -> None:
    case = _case(tmp_path, classic_slate, classic_entries)
    payload = json.loads(case["inactive"].read_text(encoding="utf-8"))
    reports = payload["reports"]
    by_id = {player.dk_id: player for player in classic_slate.players}
    if kind == "missing-team":
        reports.pop()
    elif kind == "selected-inactive":
        target = next(
            dk_id
            for roster in case["proposed"].values()
            for dk_id in roster
            if by_id[dk_id].team == reports[0]["team"] and by_id[dk_id].lock_at > AS_OF
        )
        reports[0]["inactive_dk_ids"] = [target]
    elif kind == "unknown-id":
        reports[0]["inactive_dk_ids"] = ["999999999"]
    elif kind == "team-mismatch":
        reports[0]["inactive_dk_ids"] = [
            player.dk_id for player in classic_slate.players if player.team != reports[0]["team"]
        ][:1]
    elif kind == "duplicate-team":
        reports.append(dict(reports[0]))
    elif kind == "future":
        reports[0]["observed_at"] = "2026-09-13T15:01:00-04:00"
    elif kind == "stale":
        reports[0]["observed_at"] = "2026-09-13T13:00:00-04:00"
    else:
        reports[0]["source_url"] = "http://example.com/inactives"
    case["inactive"].write_text(json.dumps(payload), encoding="utf-8")
    manifest, path = _govern(case, classic_slate, f"report-{kind}")
    _assert_blocked(manifest, path)
    assert any(needle in blocker for blocker in manifest.blockers)


def test_hand_entered_active_csv_cannot_masquerade_as_negative_list(
    tmp_path: Path, classic_slate, classic_entries
) -> None:
    case = _case(tmp_path, classic_slate, classic_entries)
    case["inactive"].write_text(
        "TEAM,PLAYER_OR_GSIS_ID,STATUS,SOURCE_URL,OBSERVED_AT\n"
        "ARI,123,ACTIVE,https://example.com/status,2026-09-13T14:56:00-04:00\n",
        encoding="utf-8",
    )
    manifest, path = _govern(case, classic_slate, "legacy-active")
    _assert_blocked(manifest, path)
    assert any("invalid team inactive-report contract" in blocker for blocker in manifest.blockers)


def test_final_release_blocks_not_yet_due_without_changing_provisional_semantics() -> None:
    record = EvidenceRecord(
        subject="team",
        field="official_inactive_status",
        hard_gate=True,
        state=EvidenceState.NOT_YET_DUE,
        reason="T-90 has not arrived",
    )
    assert evaluate_hard_gates([record])[0]
    passed, blockers = evaluate_hard_gates([record], final_release=True)
    assert not passed
    assert any(":NOT_YET_DUE:" in blocker for blocker in blockers)


def test_standard_writer_still_rejects_prefilled_rows(
    tmp_path: Path, classic_slate, classic_entries
) -> None:
    original = _lineups(classic_slate, classic_entries)
    prefilled = tmp_path / "prefilled.csv"
    prefilled.write_bytes(write_upload_bytes(classic_entries, original))
    with pytest.raises(LineupValidationError, match="prefilled cells"):
        write_upload_bytes(parse_entries(prefilled), original)


@pytest.mark.parametrize(
    ("bom", "line_ending", "final_newline"),
    [(False, b"\r\n", True), (True, b"\n", False)],
)
def test_late_swap_writer_preserves_bom_endings_unicode_quotes_and_final_newline(
    tmp_path: Path,
    classic_slate,
    classic_entries,
    bom: bool,
    line_ending: bytes,
    final_newline: bool,
) -> None:
    original = _lineups(classic_slate, classic_entries)
    proposed, _, _, _ = _valid_proposal(classic_slate, original)
    raw = write_upload_bytes(classic_entries, original)
    text = raw.decode("cp1252").replace(
        "NFL $3.5M Fantasy Football Millionaire [$1M to 1st]",
        '"NFL\u2028 $3.5M Fantasy Football Millionaire [$1M to 1st]"',
    )
    text = text.replace("\r\n", "\n").replace("\n", line_ending.decode("ascii"))
    text = text.rstrip("\r\n") + (line_ending.decode("ascii") if final_newline else "")
    encoded = text.encode("utf-8")
    if bom:
        encoded = b"\xef\xbb\xbf" + encoded
    current_path = tmp_path / "current.csv"
    current_path.write_bytes(encoded)
    template = parse_entries(current_path)
    current = {entry.entry_id: entry.existing_cells for entry in template.authorizations}
    derived = derive_late_swap_authorization(
        slate=classic_slate,
        original=original,
        current=current,
        proposed=proposed,
        as_of=AS_OF,
        current_template_sha256=template.raw_hash,
        prior_assignment_sha256="a" * 64,
    )
    assert derived.authorization is not None, derived.problems
    output = write_late_swap_bytes(template, proposed, derived.authorization)
    audit = audit_late_swap_output_bytes(
        current_path, output, template, proposed, derived.authorization
    )
    assert audit.valid, audit.problems
    assert output.startswith(b"\xef\xbb\xbf") is bom
    assert output.endswith(line_ending) is final_newline
    assert "\u2028".encode("utf-8") in output
    assert output.count(b"\r\n") == encoded.count(b"\r\n")


def test_showdown_geometry_is_derived_without_inventing_an_upload_fixture(
    showdown_slate,
) -> None:
    scores = {
        player.dk_id: 50_000 / max(player.salary, 1) for player in showdown_slate.players
    }
    solved = LineupOptimizer(showdown_slate).solve(scores)
    assert solved.roster is not None and len(solved.roster) == 6
    entry = {"1": solved.roster}
    before_lock = min(player.lock_at for player in showdown_slate.players) - timedelta(minutes=1)
    derived = derive_late_swap_authorization(
        slate=showdown_slate,
        original=entry,
        current=entry,
        proposed=entry,
        as_of=before_lock,
        current_template_sha256="a" * 64,
        prior_assignment_sha256="b" * 64,
    )
    assert derived.valid
    assert derived.authorization is not None
    assert derived.authorization.replaceable_cells == (("1", ()),)


@pytest.mark.parametrize("target", ["eligibility", "current", "salaries"])
def test_midrun_input_mutation_and_existing_run_id_fail_safely(
    tmp_path: Path, classic_slate, classic_entries, monkeypatch, target: str
) -> None:
    case = _case(tmp_path, classic_slate, classic_entries)
    original_writer = late_swap_module.write_late_swap_bytes

    def mutate_then_write(*args, **kwargs):
        result = original_writer(*args, **kwargs)
        case[target].write_bytes(case[target].read_bytes() + b"\n")
        return result

    monkeypatch.setattr(late_swap_module, "write_late_swap_bytes", mutate_then_write)
    manifest, path = _govern(case, classic_slate, "midrun-mutation")
    _assert_blocked(manifest, path)
    input_name = {
        "eligibility": "eligibility_evidence",
        "current": "current_entries",
        "salaries": "salary",
    }[target]
    assert any(
        f"INPUT_CHANGED_DURING_LATE_SWAP:{input_name}" in blocker
        for blocker in manifest.blockers
    )
    with pytest.raises(late_swap_module.LateSwapRunError, match="already exists"):
        _govern(case, classic_slate, "midrun-mutation")


def test_cli_blocked_case_returns_nonzero_and_writes_no_upload(
    tmp_path: Path, classic_slate, classic_entries
) -> None:
    case = _case(tmp_path, classic_slate, classic_entries)
    eligibility = json.loads(case["eligibility"].read_text(encoding="utf-8"))
    eligibility["bulk_late_swap_eligible"] = False
    case["eligibility"].write_text(json.dumps(eligibility), encoding="utf-8")
    code = main(
        [
            "late-swap",
            "--run-id",
            "cli-blocked",
            "--salaries",
            str(FIXTURE_ROOT / "DKSalaries Salary CSV Classic.csv"),
            "--current-entries",
            str(case["current"]),
            "--prior-manifest",
            str(case["prior_manifest"]),
            "--prior-assignments",
            str(case["prior_assignments"]),
            "--proposed-assignments",
            str(case["proposed_assignments"]),
            "--eligibility-evidence",
            str(case["eligibility"]),
            "--inactive-reports",
            str(case["inactive"]),
            "--output-dir",
            str(case["output_dir"]),
            "--as-of",
            AS_OF.isoformat(),
        ]
    )
    assert code == 2
    run = case["output_dir"] / "cli-blocked"
    assert list(run.glob("late_swap_*.manifest.json"))
    assert not list(run.glob("DK_UPLOAD_*.csv"))
