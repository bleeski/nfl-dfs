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


# ------------------------------------------------------- Session 23: structural-bound MILP rows


def test_add_salary_band_bounds_total_salary(classic_slate) -> None:
    optimizer = LineupOptimizer(classic_slate, time_limit_seconds=5)
    optimizer.add_salary_band(minimum=45_000, maximum=48_000)
    result = optimizer.solve(_scores(classic_slate))
    assert result.status == "OPTIMAL"
    by_id = {player.dk_id: player for player in classic_slate.players}
    salary = sum(by_id[dk_id].salary for dk_id in result.roster)
    assert 45_000 <= salary <= 48_000


def test_add_no_offense_with_dst_forbids_same_team_pairing(showdown_slate) -> None:
    optimizer = LineupOptimizer(showdown_slate, time_limit_seconds=5)
    optimizer.add_no_offense_with_dst()
    dst_row = next(player for player in showdown_slate.players if player.position == "DST")
    optimizer.add_required_row(dst_row.dk_id)
    result = optimizer.solve(_scores(showdown_slate))
    assert result.status == "OPTIMAL"
    by_id = {player.dk_id: player for player in showdown_slate.players}
    rostered = [by_id[dk_id] for dk_id in result.roster]
    dst_teams = {player.team for player in rostered if player.position == "DST"}
    assert all(player.position == "DST" or player.team not in dst_teams for player in rostered)


def test_add_classic_qb_correlation_bounds_pass_catcher_works_for_showdown(showdown_slate) -> None:
    """Generalized off Classic in Session 23: the same rows now serve SD3's

    `pass_catchers_with_rostered_qb` structural bound."""

    optimizer = LineupOptimizer(showdown_slate, time_limit_seconds=5)
    optimizer.add_classic_qb_correlation_bounds(kind="PASS_CATCHER", minimum=0, maximum=0)
    result = optimizer.solve(_scores(showdown_slate))
    assert result.status == "OPTIMAL"
    by_id = {player.dk_id: player for player in showdown_slate.players}
    rostered = [by_id[dk_id] for dk_id in result.roster]
    for qb in (player for player in rostered if player.position == "QB"):
        catchers = sum(
            1 for player in rostered if player.team == qb.team and player.position in {"WR", "TE"}
        )
        assert catchers == 0
