from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

from nfl_dfs.contracts import EvidenceRecord, EvidenceState, WorkflowState
from nfl_dfs.cli import _official_status_evidence, _selected_opportunity_evidence
from nfl_dfs.contracts import ContestObjective
from nfl_dfs.economics import CandidateEconomics
from nfl_dfs.evidence import evaluate_hard_gates, parse_official_inactives
from nfl_dfs.lifecycle import LifecycleError, invalidate_certification, transition
from nfl_dfs.optimizer import LineupOptimizer
from nfl_dfs.opportunity import OpportunityModel, PlayerOpportunity
from nfl_dfs.portfolio import evaluate_portfolio, select_portfolio
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


def test_official_status_evidence_uses_row_time_and_rejects_stale_snapshot(
    tmp_path: Path, classic_slate, classic_entries
) -> None:
    solved = LineupOptimizer(classic_slate).solve(
        {player.dk_id: 50_000 / max(player.salary, 1) for player in classic_slate.players}
    )
    assert solved.roster is not None
    by_id = {player.dk_id: player for player in classic_slate.players}
    earliest_lock = min(by_id[dk_id].lock_at for dk_id in solved.roster)
    observed_at = earliest_lock - timedelta(hours=4)
    path = tmp_path / "stale-status.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["TEAM", "PLAYER_OR_GSIS_ID", "STATUS", "SOURCE_URL", "OBSERVED_AT"])
        for dk_id in solved.roster:
            writer.writerow(
                [
                    by_id[dk_id].team,
                    dk_id,
                    "ACTIVE",
                    "https://official.example/status",
                    observed_at.isoformat(),
                ]
            )
    evidence = _official_status_evidence(
        status_path=path,
        slate=classic_slate,
        assignments={classic_entries.authorizations[0].entry_id: solved.roster},
        now=earliest_lock - timedelta(hours=1),
    )
    assert evidence.state is EvidenceState.STALE
    assert evidence.observed_at == observed_at
    assert evidence.expires_at == observed_at + timedelta(hours=3)


def test_selected_unknown_opportunity_evidence_is_a_hard_blocker(
    classic_slate, classic_entries
) -> None:
    solved = LineupOptimizer(classic_slate).solve(
        {player.dk_id: 50_000 / max(player.salary, 1) for player in classic_slate.players}
    )
    assert solved.roster is not None
    people = {}
    for salary_player in classic_slate.players:
        people.setdefault(
            salary_player.underlying_id,
            PlayerOpportunity(
                underlying_id=salary_player.underlying_id,
                source_dk_id=salary_player.dk_id,
                team=salary_player.team,
                position=salary_player.position,
                qb_attempt_share=0,
                carry_share=0,
                target_share=0,
                catch_rate=0,
                yards_per_target=0,
                rushing_td_share=0,
                receiving_td_share=0,
                role_capacity=1,
                evidence_state="UNKNOWN",
            ),
        )
    record = _selected_opportunity_evidence(
        model=OpportunityModel((), tuple(people.values())),
        slate=classic_slate,
        assignments={classic_entries.authorizations[0].entry_id: solved.roster},
        source_artifact_id="a" * 64,
    )
    assert record.hard_gate
    assert record.state is EvidenceState.UNKNOWN
    assert not evaluate_hard_gates((record,))[0]


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


def test_batched_exact_portfolio_search_matches_scalar_metrics_and_is_bounded() -> None:
    rng = np.random.default_rng(42)
    scenarios = 30
    candidates = 8
    economics = CandidateEconomics(
        rosters=tuple((str(index),) for index in range(candidates)),
        gross_payout=rng.integers(0, 50, size=(scenarios, candidates)).astype(np.float32),
        ranks=rng.integers(1, 100, size=(scenarios, candidates), dtype=np.int32),
        tie_counts=np.ones((scenarios, candidates), dtype=np.int32),
        duplicate_counts=np.zeros(candidates, dtype=np.int32),
    )
    states = {"BASE": economics, "STRESS": economics}
    selected = select_portfolio(
        states,
        entry_count=2,
        entry_fee=5,
        field_size=100,
        objective=ContestObjective.SMALL_GPP,
        shortlist_limit=candidates,
    )
    scalar = evaluate_portfolio(
        states,
        selected.candidate_indices,
        entry_fee=5,
        field_size=100,
        objective=ContestObjective.SMALL_GPP,
    )
    assert selected.robust_net_payout_lcb == pytest.approx(scalar.robust_net_payout_lcb)
    assert selected.elite_probability == pytest.approx(scalar.elite_probability)
    assert selected.payout_p95 == pytest.approx(scalar.payout_p95)
    assert selected.selection_candidate_count == candidates
    assert selected.evaluated_portfolio_count == 28

    bounded = select_portfolio(
        states,
        entry_count=3,
        entry_fee=5,
        field_size=100,
        objective=ContestObjective.SMALL_GPP,
        shortlist_limit=candidates,
        maximum_exact_combinations=10,
    )
    assert bounded.selection_candidate_count == 5
    assert bounded.evaluated_portfolio_count == 10


def test_scenario_parquet_round_trip(tmp_path: Path, classic_slate) -> None:
    result = simulate_factor_bank(
        classic_slate,
        _model(classic_slate),
        scenarios=5,
        seed=99,
        purpose="REFEREE",
    )
    artifact = save_scenario_bank(result, tmp_path)
    with pytest.raises(FileExistsError, match="immutable"):
        save_scenario_bank(result, tmp_path)
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
