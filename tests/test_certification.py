from __future__ import annotations

import argparse
import csv
import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

import nfl_dfs.certification as certification_module
from nfl_dfs.certification import CertificationError, certify_upload
from nfl_dfs.cli import command_audit
from nfl_dfs.contracts import EvidenceRecord, EvidenceState
from nfl_dfs.dk import parse_entries
from nfl_dfs.hashing import sha256_file
from nfl_dfs.optimizer import LineupOptimizer
from nfl_dfs.payouts import parse_payout_csv
from nfl_dfs.referee import ByteAudit, audit_output_bytes


def _assignments(slate, entries):
    scores = {player.dk_id: 50_000 / max(player.salary, 1) for player in slate.players}
    optimizer = LineupOptimizer(slate)
    result = {}
    for entry in sorted(entries.authorizations, key=lambda item: item.entry_id):
        solved = optimizer.solve(scores)
        assert solved.roster is not None
        result[entry.entry_id] = solved.roster
        optimizer.add_no_good(solved.roster)
    return result


def _evidence(tmp_path: Path, classic_slate, classic_entries, official_state=EvidenceState.PASS):
    now = datetime.now(timezone.utc)
    payout = tmp_path / "payouts.csv"
    payout.write_text(
        "rank_start,rank_end,prize_type,value\n1,1,CASH,10\n2,2,CASH,5\n",
        encoding="utf-8",
    )
    parse_payout_csv(payout)
    records = [
        EvidenceRecord(subject="slate", field="salary_pool", value=True, source_artifact_id=classic_slate.salary_hash, observed_at=now, hard_gate=True, state=EvidenceState.PASS, reason="parsed"),
        EvidenceRecord(subject="entries", field="entry_authorization", value=True, source_artifact_id=classic_entries.raw_hash, observed_at=now, hard_gate=True, state=EvidenceState.PASS, reason="reconciled"),
        EvidenceRecord(subject="contest", field="payout_contract", value=True, source_artifact_id=sha256_file(payout), observed_at=now, hard_gate=True, state=EvidenceState.PASS, reason="reconciled"),
        EvidenceRecord(subject="selected", field="official_inactive_status", value=True, source_artifact_id="a" * 64, observed_at=now, hard_gate=True, state=official_state, reason="official exact IDs"),
        EvidenceRecord(subject="slate", field="weather_if_required", hard_gate=True, state=EvidenceState.NOT_APPLICABLE, reason="manual guardrail"),
        EvidenceRecord(subject="slate", field="market_line", hard_gate=True, state=EvidenceState.NOT_APPLICABLE, reason="manual guardrail"),
    ]
    return payout, records


def test_certification_is_fail_closed_then_exact_byte_certified(
    tmp_path: Path, classic_slate, classic_entries
) -> None:
    assignments = _assignments(classic_slate, classic_entries)
    payout, evidence = _evidence(
        tmp_path, classic_slate, classic_entries, EvidenceState.UNKNOWN
    )
    output = tmp_path / "upload.csv"
    manifest_path = tmp_path / "manifest.json"
    blocked = certify_upload(
        run_id="blocked",
        slate=classic_slate,
        template=classic_entries,
        assignments=assignments,
        evidence=evidence,
        output_path=output,
        manifest_path=manifest_path,
    )
    assert blocked.status == "DO_NOT_UPLOAD"
    assert blocked.file_valid
    assert blocked.evidence_state.value == "UNKNOWN"
    assert blocked.model_status.value == "UNVALIDATED"
    assert blocked.release_decision.value == "DO_NOT_UPLOAD"
    assert blocked.proposed_output_sha256 is not None
    assert not output.exists()
    blocked_json = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert blocked_json["FILE_VALID"] is True
    assert blocked_json["EVIDENCE_STATE"] == "UNKNOWN"
    assert blocked_json["MODEL_STATUS"] == "UNVALIDATED"
    assert blocked_json["RELEASE_DECISION"] == "DO_NOT_UPLOAD"
    with pytest.raises(CertificationError, match="already exist"):
        certify_upload(
            run_id="blocked-retry",
            slate=classic_slate,
            template=classic_entries,
            assignments=assignments,
            evidence=evidence,
            output_path=output,
            manifest_path=manifest_path,
        )
    _, pass_evidence = _evidence(tmp_path, classic_slate, classic_entries)
    certified_output = tmp_path / "certified-upload.csv"
    certified = certify_upload(
        run_id="certified",
        slate=classic_slate,
        template=classic_entries,
        assignments=assignments,
        evidence=pass_evidence,
        output_path=certified_output,
        manifest_path=tmp_path / "certified-manifest.json",
    )
    assert certified.status == "CERTIFIED"
    assert certified.file_valid
    assert certified.evidence_state.value == "PASS"
    assert certified.model_status.value == "UNVALIDATED"
    assert certified.release_decision.value == "CERTIFIED_UPLOAD_PACKAGE"
    assert certified_output.exists()
    assert sha256_file(certified_output) == certified.output_sha256
    assert not certified_output.read_bytes().startswith(b"\xef\xbb\xbf")
    audit = audit_output_bytes(
        classic_entries.path,
        certified_output.read_bytes(),
        classic_entries,
        assignments,
    )
    assert audit.valid
    certified_json = json.loads(
        (tmp_path / "certified-manifest.json").read_text(encoding="utf-8")
    )
    assert certified_json["FILE_VALID"] is True
    assert certified_json["EVIDENCE_STATE"] == "PASS"
    assert certified_json["MODEL_STATUS"] == "UNVALIDATED"
    assert certified_json["RELEASE_DECISION"] == "CERTIFIED_UPLOAD_PACKAGE"


def test_certification_rejects_mixed_contests(
    tmp_path: Path, classic_slate, classic_entries
) -> None:
    assignments = _assignments(classic_slate, classic_entries)
    _, evidence = _evidence(tmp_path, classic_slate, classic_entries)
    mixed = replace(
        classic_entries,
        authorizations=(
            classic_entries.authorizations[0],
            classic_entries.authorizations[1].model_copy(
                update={"contest_id": "999999999"}
            ),
        ),
    )
    output = tmp_path / "mixed-upload.csv"
    manifest = certify_upload(
        run_id="mixed",
        slate=classic_slate,
        template=mixed,
        assignments=assignments,
        evidence=evidence,
        output_path=output,
        manifest_path=tmp_path / "mixed-manifest.json",
    )
    assert manifest.status == "DO_NOT_UPLOAD"
    assert not manifest.file_valid
    assert manifest.release_decision.value == "DO_NOT_UPLOAD"
    assert any("MULTI_CONTEST_ENTRY_FILE_UNSUPPORTED" in item for item in manifest.blockers)
    assert not output.exists()


def test_certification_rejects_entry_bytes_changed_after_parse(
    tmp_path: Path, classic_slate, classic_entries
) -> None:
    copied = tmp_path / "entries.csv"
    copied.write_bytes(classic_entries.path.read_bytes())
    parsed = parse_entries(copied)
    copied.write_bytes(copied.read_bytes() + b"\r\n")
    assignments = _assignments(classic_slate, parsed)
    _, evidence = _evidence(tmp_path, classic_slate, parsed)
    manifest = certify_upload(
        run_id="mutated-template",
        slate=classic_slate,
        template=parsed,
        assignments=assignments,
        evidence=evidence,
        output_path=tmp_path / "mutated-upload.csv",
        manifest_path=tmp_path / "mutated-manifest.json",
    )
    assert manifest.status == "DO_NOT_UPLOAD"
    assert not manifest.file_valid
    assert "ENTRY_TEMPLATE_BYTES_CHANGED_AFTER_PARSE" in manifest.blockers


def test_illegal_lineup_reports_file_failure_and_no_upload(
    tmp_path: Path, classic_slate, classic_entries
) -> None:
    assignments = _assignments(classic_slate, classic_entries)
    entry_id = sorted(assignments)[0]
    illegal = dict(assignments)
    illegal[entry_id] = (assignments[entry_id][0],) * len(assignments[entry_id])
    _, evidence = _evidence(tmp_path, classic_slate, classic_entries)
    output = tmp_path / "illegal-upload.csv"
    manifest = certify_upload(
        run_id="illegal",
        slate=classic_slate,
        template=classic_entries,
        assignments=illegal,
        evidence=evidence,
        output_path=output,
        manifest_path=tmp_path / "illegal-manifest.json",
    )
    assert not manifest.file_valid
    assert manifest.release_decision.value == "DO_NOT_UPLOAD"
    assert any(blocker.startswith(f"LINEUP_{entry_id}:") for blocker in manifest.blockers)
    assert not output.exists()


def test_independent_byte_audit_failure_reports_file_failure(
    tmp_path: Path, classic_slate, classic_entries, monkeypatch: pytest.MonkeyPatch
) -> None:
    assignments = _assignments(classic_slate, classic_entries)
    _, evidence = _evidence(tmp_path, classic_slate, classic_entries)
    monkeypatch.setattr(
        certification_module,
        "audit_output_bytes",
        lambda *_args, **_kwargs: ByteAudit(False, ("simulated byte mismatch",)),
    )
    output = tmp_path / "byte-failure-upload.csv"
    manifest = certify_upload(
        run_id="byte-failure",
        slate=classic_slate,
        template=classic_entries,
        assignments=assignments,
        evidence=evidence,
        output_path=output,
        manifest_path=tmp_path / "byte-failure-manifest.json",
    )
    assert not manifest.file_valid
    assert manifest.release_decision.value == "DO_NOT_UPLOAD"
    assert "FINAL_BYTE_AUDIT:simulated byte mismatch" in manifest.blockers
    assert not output.exists()


def test_manifest_audit_rederives_do_not_upload_after_output_tamper(
    tmp_path: Path, classic_slate, classic_entries, capsys: pytest.CaptureFixture[str]
) -> None:
    assignments = _assignments(classic_slate, classic_entries)
    _, evidence = _evidence(tmp_path, classic_slate, classic_entries)
    output = tmp_path / "audit-upload.csv"
    manifest_path = tmp_path / "audit-manifest.json"
    manifest = certify_upload(
        run_id="audit-tamper",
        slate=classic_slate,
        template=classic_entries,
        assignments=assignments,
        evidence=evidence,
        output_path=output,
        manifest_path=manifest_path,
    )
    assert manifest.release_decision.value == "CERTIFIED_UPLOAD_PACKAGE"
    output.write_bytes(output.read_bytes() + b"\r\n")
    assert command_audit(argparse.Namespace(manifest=str(manifest_path))) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "FAIL"
    assert result["FILE_VALID"] is False
    assert result["RELEASE_DECISION"] == "DO_NOT_UPLOAD"
