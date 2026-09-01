from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

from nfl_dfs.contracts import EvidenceRecord, EvidenceState, WorkflowState
from nfl_dfs.evidence import evaluate_hard_gates, parse_official_inactives
from nfl_dfs.lifecycle import LifecycleError, invalidate_certification, transition
from nfl_dfs.optimizer import LineupOptimizer
from nfl_dfs.qa import decide_repair, referee_blocks, run_three_pass_audit
from nfl_dfs.registry import RunRegistry
from nfl_dfs.scenario_store import load_scenario_bank, save_scenario_bank
from nfl_dfs.settlement import SettlementError, parse_standings, require_entry_coverage
from nfl_dfs.simulation import simulate_factor_bank

from .test_simulation import _model


def test_monotonic_lifecycle_and_sqlite_registry(tmp_path: Path) -> None:
    assert transition(WorkflowState.NEW, WorkflowState.SNAPSHOTTED) is WorkflowState.SNAPSHOTTED
    with pytest.raises(LifecycleError):
        transition(WorkflowState.NEW, WorkflowState.CERTIFIED)
    assert invalidate_certification(WorkflowState.CERTIFIED) is WorkflowState.DO_NOT_UPLOAD
    registry = RunRegistry(tmp_path / "registry.sqlite")
    registry.create_run("r1", {"label": "test"})
    registry.set_state("r1", WorkflowState.SNAPSHOTTED, {"hash": "abc"})
    assert registry.get_run("r1")["state"] == "SNAPSHOTTED"
    with pytest.raises(LifecycleError):
        registry.set_state("r1", WorkflowState.CERTIFIED, {})


def test_evidence_expiry_and_exact_inactive_parser(tmp_path: Path, classic_slate) -> None:
    now = datetime.now(timezone.utc)
    stale = EvidenceRecord(
        subject="p",
        field="official_inactive_status",
        value="ACTIVE",
        source_artifact_id="b" * 64,
        observed_at=now,
        expires_at=now,
        hard_gate=True,
        state=EvidenceState.PASS,
        reason="test",
    )
    passed, blockers = evaluate_hard_gates([stale], now=now)
    assert passed and not blockers
    selected = classic_slate.players[0]
    path = tmp_path / "status.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["TEAM", "PLAYER_OR_GSIS_ID", "STATUS", "SOURCE_URL", "OBSERVED_AT"])
        writer.writerow([selected.team, selected.dk_id, "ACTIVE", "https://official.example/status", now.isoformat()])
    statuses, problems = parse_official_inactives(path, classic_slate.players)
    assert statuses[selected.dk_id] == "ACTIVE"
    assert not problems


def test_qa_repair_and_referee_semantics() -> None:
    accepted = decide_repair(
        net_payout_delta=np.full(100, 2.0),
        elite_probability_delta=0.0,
        elite_standard_error=0.01,
        state_net_deltas={"BASE": 1.0, "CHALK": 0.5},
        weakens_safety=False,
    )
    assert accepted.accepted
    rejected = decide_repair(
        net_payout_delta=np.array([-1.0, 1.0]),
        elite_probability_delta=-0.02,
        elite_standard_error=0.01,
        state_net_deltas={"BASE": -0.1},
        weakens_safety=True,
    )
    assert not rejected.accepted and len(rejected.reasons) == 4
    assert referee_blocks(
        select_net_delta=1,
        referee_net_delta=-1,
        uncertainty=0,
        safety_failure=False,
        hard_constraint_failure=False,
    )[0]
    calls = {"audit": 0, "repair": 0}

    def audit():
        calls["audit"] += 1
        return ()

    def repair(_):
        calls["repair"] += 1
        return True

    history = run_three_pass_audit(audit, repair)
    assert len(history) == 1 and calls["repair"] == 0


def test_scenario_parquet_round_trip(tmp_path: Path, classic_slate) -> None:
    result = simulate_factor_bank(
        classic_slate,
        _model(classic_slate),
        scenarios=5,
        seed=99,
        purpose="REFEREE",
    )
    artifact = save_scenario_bank(result, tmp_path)
    people, outcomes, weights, diagnostics = load_scenario_bank(artifact["path"])
    assert people == result.person_ids
    assert np.array_equal(outcomes, result.outcomes)
    assert np.allclose(weights, result.weights)
    assert diagnostics["share_conservation"] == 1.0


def test_settlement_requires_reserved_entry_coverage(tmp_path: Path, classic_entries) -> None:
    standings = tmp_path / "standings.csv"
    standings.write_text(
        "EntryId,Rank,Points,Prize,Lineup\n"
        f"{classic_entries.authorizations[0].entry_id},1,200.5,$10,lineup\n",
        encoding="utf-8",
    )
    snapshot = parse_standings(standings)
    with pytest.raises(SettlementError, match="incomplete"):
        require_entry_coverage(
            snapshot, {entry.entry_id for entry in classic_entries.authorizations}
        )
