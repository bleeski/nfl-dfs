from __future__ import annotations

from datetime import timedelta

from nfl_dfs.late_swap import audit_late_swap
from nfl_dfs.learning import evaluate_challenger, field_model_tier, should_rollback
from nfl_dfs.optimizer import LineupOptimizer


def test_locked_cells_are_immutable(classic_slate, classic_entries) -> None:
    scores = {player.dk_id: 50_000 / max(player.salary, 1) for player in classic_slate.players}
    result = LineupOptimizer(classic_slate).solve(scores)
    assert result.roster is not None
    original = {classic_entries.authorizations[0].entry_id: result.roster}
    proposed = {classic_entries.authorizations[0].entry_id: result.roster}
    after_all_locks = max(player.lock_at for player in classic_slate.players) + timedelta(minutes=1)
    assert audit_late_swap(
        slate=classic_slate, original=original, proposed=proposed, now=after_all_locks
    ).valid
    changed = list(result.roster)
    changed[0] = next(player.dk_id for player in classic_slate.players if player.dk_id not in changed)
    audit = audit_late_swap(
        slate=classic_slate,
        original=original,
        proposed={classic_entries.authorizations[0].entry_id: tuple(changed)},
        now=after_all_locks,
    )
    assert not audit.valid
    assert any("locked slot" in problem for problem in audit.problems)


def test_late_swap_cannot_add_a_player_whose_game_started(
    classic_slate, classic_entries
) -> None:
    scores = {player.dk_id: 50_000 / max(player.salary, 1) for player in classic_slate.players}
    solved = LineupOptimizer(classic_slate).solve(scores)
    assert solved.roster is not None
    locks = sorted({player.lock_at for player in classic_slate.players})
    assert len(locks) > 1
    now = locks[0] + timedelta(minutes=1)
    by_id = {player.dk_id: player for player in classic_slate.players}
    unlocked_slot = next(
        index for index, dk_id in enumerate(solved.roster) if by_id[dk_id].lock_at > now
    )
    already_locked = next(
        player.dk_id
        for player in classic_slate.players
        if player.lock_at <= now and player.dk_id not in solved.roster
    )
    proposed = list(solved.roster)
    proposed[unlocked_slot] = already_locked
    entry_id = classic_entries.authorizations[0].entry_id
    audit = audit_late_swap(
        slate=classic_slate,
        original={entry_id: solved.roster},
        proposed={entry_id: tuple(proposed)},
        now=now,
    )
    assert not audit.valid
    assert any("cannot add already-locked player" in problem for problem in audit.problems)


def test_learning_tiers_and_guarded_promotion_ignore_roi() -> None:
    assert field_model_tier(2, True) == ("COLD", 0.0)
    assert field_model_tier(3, True) == ("PROVISIONAL", 0.25)
    assert field_model_tier(10, True) == ("GRADED", 0.5)
    assert field_model_tier(20, True) == ("CALIBRATED", 1.0)
    decision = evaluate_challenger(
        comparable_settled_slates=20,
        reproducible=True,
        integrity_pass=True,
        rolling_origin_improvement=True,
        calibration_pass=True,
        drift_pass=True,
        no_regression=True,
        prospective_field_gates=True,
        realized_roi_observed=-0.99,
    )
    assert decision.promote
    assert should_rollback(integrity_failure=True, consecutive_registered_degradation_windows=0)[0]
    assert not should_rollback(
        integrity_failure=False, consecutive_registered_degradation_windows=1
    )[0]
