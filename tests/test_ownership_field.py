from __future__ import annotations

import pytest

from nfl_dfs.field import generate_opponent_field, scale_field_multiplicities
from nfl_dfs.ownership import OwnershipBracket, cold_start_states, ownership_roster_total


def test_cold_ownership_normalizes_to_roster_and_field_is_legal(classic_slate) -> None:
    projections = {player.dk_id: 50_000 / max(player.salary, 1) for player in classic_slate.players}
    team_totals = {player.team: 45.0 for player in classic_slate.players}
    states = cold_start_states(classic_slate, projections, team_totals)
    assert {state.name for state in states} == {
        "BASE",
        "CHALK_SURGE",
        "CHALK_FADE",
        "LATE_VALUE_SURGE",
        "SHARP_FIELD",
    }
    assert all(ownership_roster_total(state) == pytest.approx(9.0) for state in states)
    field = generate_opponent_field(classic_slate, states[0], field_size=20, seed=5)
    assert sum(lineup.multiplicity for lineup in field) == 20
    scaled = scale_field_multiplicities(field, 1_000)
    assert sum(lineup.multiplicity for lineup in scaled) == 1_000


@pytest.mark.parametrize(
    "values",
    [(-0.1, 0.1, 0.2), (0.2, 0.1, 0.3), (0.1, 0.2, 1.1)],
)
def test_ownership_brackets_are_ordered_decimal_percentages(values) -> None:
    with pytest.raises(ValueError, match="0 <= LOW"):
        OwnershipBracket(*values)
