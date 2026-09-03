from __future__ import annotations

import json
from pathlib import Path

import pytest

from nfl_dfs.contracts import EngineMode
from nfl_dfs.dk import DraftKingsParseError, parse_salaries, reconcile_template
from nfl_dfs.hashing import sha256_file

from .conftest import FIXTURE_ROOT


def test_fixture_hashes_match_manifest() -> None:
    manifest = json.loads((FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8"))
    for artifact in manifest["artifacts"]:
        path = FIXTURE_ROOT / artifact["file"]
        assert path.stat().st_size == artifact["bytes"]
        assert sha256_file(path) == artifact["sha256"]


def test_supplied_classic_contract(classic_slate, classic_entries) -> None:
    assert classic_slate.mode is EngineMode.CLASSIC
    assert len(classic_slate.players) == 719
    assert len({player.dk_id for player in classic_slate.players}) == 719
    assert len({player.team for player in classic_slate.players}) == 24
    assert len(classic_slate.games) == 12
    assert len(classic_entries.authorizations) == 2
    assert {entry.contest_id for entry in classic_entries.authorizations} == {"193028206"}
    reconcile_template(classic_entries, classic_slate)


def test_supplied_showdown_contract(showdown_slate) -> None:
    assert showdown_slate.mode is EngineMode.SHOWDOWN
    assert len(showdown_slate.players) == 126
    assert len({player.underlying_id for player in showdown_slate.players}) == 63
    by_person = {}
    for player in showdown_slate.players:
        by_person.setdefault(player.underlying_id, {})[player.role] = player
    assert all(set(roles) == {"CPT", "FLEX"} for roles in by_person.values())
    assert all(
        roles["CPT"].salary == round(1.5 * roles["FLEX"].salary)
        and roles["CPT"].dk_id != roles["FLEX"].dk_id
        for roles in by_person.values()
    )


def test_classic_template_rejected_for_showdown(showdown_slate, classic_entries) -> None:
    with pytest.raises(DraftKingsParseError, match="template is CLASSIC"):
        reconcile_template(classic_entries, showdown_slate)


def test_short_salary_row_fails_with_a_contract_error(tmp_path: Path) -> None:
    path = tmp_path / "short.csv"
    path.write_text(
        "Position,Name,ID,Roster Position,Salary,Game Info,TeamAbbrev,AvgPointsPerGame,Status\nQB\n",
        encoding="utf-8",
    )
    with pytest.raises(DraftKingsParseError, match="short salary row 2"):
        parse_salaries(path)
