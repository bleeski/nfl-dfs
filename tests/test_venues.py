"""Acceptance for the venue roof resolution.

The statement under test: a blank `roof` at a retractable-roof venue whose
completed history in the same frozen artifact is unanimously `closed` resolves
without an `api.weather.gov` capture, and every other blank still blocks.
"""

from __future__ import annotations

import pytest

from nfl_dfs.venues import (
    MIN_COMPLETED_HOME_GAMES,
    RETRACTABLE_ROOF_HOME_TEAMS,
    home_team_of,
    resolve_blank_roof,
    roof_history,
)


def _rows(
    team: str,
    roof: str,
    count: int,
    *,
    played: bool = True,
    season: int = 2025,
) -> list[dict[str, str]]:
    return [
        {
            "home_team": team,
            "home_score": "24" if played else "",
            "roof": roof,
            "season": str(season),
            "game_id": f"{season}_{index:02d}_AWAY_{team}",
        }
        for index in range(1, count + 1)
    ]


def test_home_team_of_reads_the_away_at_home_matchup() -> None:
    assert home_team_of("SEA@ARI") == "ARI"
    assert home_team_of("was@dal") == "DAL"
    # Anything that is not exactly one '@' names no side rather than guessing.
    assert home_team_of("") == ""
    assert home_team_of("ARI") == ""
    assert home_team_of("A@B@C") == ""


def test_roof_history_counts_only_completed_rows() -> None:
    rows = _rows("DAL", "closed", 9) + _rows("DAL", "", 5, played=False)
    assert roof_history(rows) == {"DAL": {"closed": 9}}


def test_roof_history_ignores_a_completed_row_with_no_roof_recorded() -> None:
    rows = _rows("ATL", "closed", 8) + _rows("ATL", "", 3)
    assert roof_history(rows) == {"ATL": {"closed": 8}}


def test_unanimous_retractable_history_resolves_with_its_counts_in_the_basis() -> None:
    history = roof_history(_rows("ARI", "closed", 17), seasons=(2025, 2026))
    resolved = resolve_blank_roof("ARI", history, seasons=(2025, 2026))
    assert resolved is not None
    roof, basis = resolved
    assert roof == "closed"
    # The window is part of the claim: unanimity holds over these seasons, and
    # the same venue has recorded an open roof in earlier ones.
    assert basis == (
        "DERIVED_FROM_VENUE_ROOF_HISTORY:retractable:closed=17/17:seasons=2025,2026"
    )


def test_a_mixed_history_does_not_resolve() -> None:
    # One recorded open roof is a venue that plays in the weather sometimes, so
    # the capture is still the only thing that can answer this game.
    history = roof_history(_rows("HOU", "closed", 16) + _rows("HOU", "open", 1))
    assert resolve_blank_roof("HOU", history) is None


def test_a_thin_history_does_not_resolve() -> None:
    history = roof_history(_rows("IND", "closed", MIN_COMPLETED_HOME_GAMES - 1))
    assert resolve_blank_roof("IND", history) is None


def test_the_boundary_count_resolves() -> None:
    history = roof_history(_rows("IND", "closed", MIN_COMPLETED_HOME_GAMES))
    assert resolve_blank_roof("IND", history) is not None


def test_an_outdoor_venue_never_resolves_from_history() -> None:
    # GB has a unanimous history too. It is unanimously outdoors, and a venue
    # with no roof is not a venue this module may speak for.
    history = roof_history(_rows("GB", "outdoors", 17))
    assert resolve_blank_roof("GB", history) is None


def test_no_history_at_all_does_not_resolve() -> None:
    assert resolve_blank_roof("DAL", None) is None
    assert resolve_blank_roof("DAL", {}) is None


@pytest.mark.parametrize("team", sorted(RETRACTABLE_ROOF_HOME_TEAMS))
def test_every_declared_retractable_venue_can_resolve(team: str) -> None:
    history = roof_history(_rows(team, "closed", 17))
    assert resolve_blank_roof(team, history) is not None


def test_the_season_window_excludes_older_rows() -> None:
    """The window is load-bearing, not decoration.

    ARI reads 144 closed, 21 open and 58 outdoors over the whole artifact and
    unanimous closed over the prior and current seasons. A resolution that
    counted every season would never fire, and one that counted the wrong
    seasons would fire on stale practice.
    """

    rows = _rows("ARI", "closed", 17, season=2025) + _rows("ARI", "open", 2, season=2022)
    assert roof_history(rows) == {"ARI": {"closed": 17, "open": 2}}
    assert resolve_blank_roof("ARI", roof_history(rows)) is None

    scoped = roof_history(rows, seasons=(2025, 2026))
    assert scoped == {"ARI": {"closed": 17}}
    assert resolve_blank_roof("ARI", scoped, seasons=(2025, 2026)) is not None


def test_season_window_is_the_prior_and_current_pair() -> None:
    from nfl_dfs.venues import season_window

    assert season_window(2026, 2025) == (2025, 2026)
    assert season_window(2026, 2026) == (2026,)
