from __future__ import annotations

from nfl_dfs.lineups import validate_lineup
from nfl_dfs.optimizer import LineupOptimizer


def _scores(slate):
    return {player.dk_id: 50_000 / max(player.salary, 1) for player in slate.players}


def test_classic_optimizer_direct_highs_and_no_good(classic_slate) -> None:
    optimizer = LineupOptimizer(classic_slate, time_limit_seconds=5)
    first = optimizer.solve(_scores(classic_slate))
    assert first.status == "OPTIMAL"
    assert first.validation and first.validation.valid
    assert first.roster is not None
    optimizer.add_no_good(first.roster)
    second = optimizer.solve(_scores(classic_slate))
    assert second.roster is not None and second.roster != first.roster
    assert second.validation and second.validation.valid


def test_showdown_optimizer_preserves_underlying_person(showdown_slate) -> None:
    optimizer = LineupOptimizer(showdown_slate, time_limit_seconds=5)
    result = optimizer.solve(_scores(showdown_slate))
    assert result.status == "OPTIMAL"
    assert result.roster is not None
    validation = validate_lineup(showdown_slate, result.roster)
    assert validation.valid
    by_id = {player.dk_id: player for player in showdown_slate.players}
    assert by_id[result.roster[0]].role == "CPT"
    assert len({by_id[dk_id].underlying_id for dk_id in result.roster}) == 6
