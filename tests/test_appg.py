from __future__ import annotations

import csv
from pathlib import Path

from nfl_dfs.dk import parse_salaries
from nfl_dfs.opportunity import appg_is_absent_from_model_contract
from nfl_dfs.optimizer import LineupOptimizer

from .conftest import FIXTURE_ROOT


def test_appg_mutation_does_not_change_normalized_players_or_optimizer(tmp_path: Path) -> None:
    source = FIXTURE_ROOT / "DKSalaries Salary CSV Classic.csv"
    rows = list(csv.reader(source.open("r", encoding="utf-8-sig", newline="")))
    appg_index = rows[0].index("AvgPointsPerGame")
    for row in rows[1:]:
        row[appg_index] = "999999"
    mutated = tmp_path / "mutated.csv"
    with mutated.open("w", encoding="utf-8-sig", newline="") as handle:
        csv.writer(handle, lineterminator="\r\n").writerows(rows)
    baseline = parse_salaries(source)
    changed = parse_salaries(mutated)
    assert [player.model_dump() for player in baseline.players] == [
        player.model_dump() for player in changed.players
    ]
    scores = {player.dk_id: 50_000 / max(player.salary, 1) for player in baseline.players}
    assert LineupOptimizer(baseline).solve(scores).roster == LineupOptimizer(changed).solve(scores).roster
    assert appg_is_absent_from_model_contract()
