from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

from nfl_dfs.certification import certify_upload
from nfl_dfs.contracts import EvidenceRecord, EvidenceState
from nfl_dfs.hashing import sha256_file
from nfl_dfs.optimizer import LineupOptimizer
from nfl_dfs.payouts import parse_payout_csv
from nfl_dfs.referee import audit_output_bytes


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
    assert not output.exists()
    _, pass_evidence = _evidence(tmp_path, classic_slate, classic_entries)
    certified = certify_upload(
        run_id="certified",
        slate=classic_slate,
        template=classic_entries,
        assignments=assignments,
        evidence=pass_evidence,
        output_path=output,
        manifest_path=manifest_path,
    )
    assert certified.status == "CERTIFIED"
    assert output.exists()
    assert sha256_file(output) == certified.output_sha256
    assert not output.read_bytes().startswith(b"\xef\xbb\xbf")
    audit = audit_output_bytes(classic_entries.path, output.read_bytes(), classic_entries, assignments)
    assert audit.valid
