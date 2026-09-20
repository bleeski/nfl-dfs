"""Acceptance for `scripts/build_classic_portfolio.py`.

This is the construction layer that shipped the 2026-09-13 Week 1 portfolio when
the engine's C2 solver could not. It had no test until 2026-09-20, the day it
emitted an empty `assignments_by_entry_id` for the second slate running and the
mapping was filled by hand again.

Nothing here touches the network or the engine.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "build_classic_portfolio.py"


def _load():
    spec = importlib.util.spec_from_file_location("build_classic_portfolio", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["build_classic_portfolio"] = module
    spec.loader.exec_module(module)
    return module


build = _load()

SALARY_HEADER = (
    "Position,Name + ID,Name,ID,Roster Position,Salary,"
    "Game Info,TeamAbbrev,AvgPointsPerGame,Status\n"
)
ENTRY_HEADER = "Entry ID,Contest Name,Contest ID,Entry Fee,QB,RB,RB,WR,WR,WR,TE,FLEX,DST,,Instructions\n"

# Four teams across two games, deep enough at every slot to fill nine-man
# lineups many different ways.
TEAMS = {"AAA": "AAA@BBB", "BBB": "AAA@BBB", "CCC": "CCC@DDD", "DDD": "CCC@DDD"}
COUNTS = {"QB": 1, "RB": 4, "WR": 6, "TE": 2, "DST": 1}


def make_pool(tmp_path: Path):
    rows, scores, dk = [], {}, 1000
    for team, game in TEAMS.items():
        for pos, n in COUNTS.items():
            for k in range(n):
                dk += 1
                ident = str(dk)
                name = f"{team}{pos}{k}"
                salary = 3000 + (k * 400) + (500 if pos == "QB" else 0)
                rows.append(
                    f"{pos},{name} ({ident}),{name},{ident},"
                    f"{pos}/FLEX,{salary},{game} 09/20/2026 01:00PM ET,{team},0,\n"
                )
                scores[ident] = 10.0 + k
    sal = tmp_path / "sal.csv"
    sal.write_text(SALARY_HEADER + "".join(rows), encoding="utf-8")
    sc = tmp_path / "scores.json"
    sc.write_text(json.dumps({"by_dk_id": scores}), encoding="utf-8")
    st = tmp_path / "status.csv"
    st.write_text("TEAM,PLAYER_OR_GSIS_ID,STATUS,SOURCE_URL,OBSERVED_AT\n", encoding="utf-8")
    return sal, sc, st


def make_entries(tmp_path: Path, n: int) -> Path:
    p = tmp_path / "entries.csv"
    body = "".join(f"52632{i:05d},Contest,1234,$1,,,,,,,,,,,\n" for i in range(n))
    p.write_text(ENTRY_HEADER + body, encoding="utf-8")
    return p


def run(tmp_path, extra=(), lineups=4):
    sal, sc, st = make_pool(tmp_path)
    out = tmp_path / "portfolio.json"
    args = ["--scores", str(sc), "--salaries", str(sal), "--status", str(st),
            "--out", str(out), "--lineups", str(lineups), *extra]
    build.main(args)
    return json.loads(out.read_text(encoding="utf-8"))


def test_entry_ids_are_assigned_in_template_order(tmp_path):
    """The 2026-09-20 defect: this key was emitted empty and filled by hand."""

    entries = make_entries(tmp_path, 4)
    got = run(tmp_path, ["--entries", str(entries)])
    assigned = got["assignments_by_entry_id"]
    assert len(assigned) == len(got["lineups"]) == 4
    assert list(assigned) == ["5263200000", "5263200001", "5263200002", "5263200003"]
    for eid, roster in assigned.items():
        assert len(roster) == 9


def test_without_entries_the_mapping_is_empty_and_that_is_explicit(tmp_path):
    got = run(tmp_path)
    assert got["assignments_by_entry_id"] == {}
    assert len(got["lineups"]) == 4


def test_too_few_reserved_entry_ids_is_a_named_stop(tmp_path):
    entries = make_entries(tmp_path, 2)
    with pytest.raises(SystemExit) as caught:
        run(tmp_path, ["--entries", str(entries)], lineups=4)
    assert "ENTRY_ID_SHORTFALL" in str(caught.value)


def test_same_seed_same_bytes(tmp_path):
    """Determinism: the builder draws randomly, so the seed is the contract."""

    a = run(tmp_path, ["--seed", "913"])
    b = run(tmp_path, ["--seed", "913"])
    assert a["lineups"] == b["lineups"]


def test_a_different_seed_moves_the_portfolio(tmp_path):
    a = run(tmp_path, ["--seed", "1"])
    b = run(tmp_path, ["--seed", "2"])
    assert a["lineups"] != b["lineups"]


def test_require_bringback_holds_on_every_lineup(tmp_path):
    """12 of 18 on 2026-09-20 because this was an 85% coin flip, not a rule."""

    got = run(tmp_path, ["--require-bringback"])
    assert got["lineups"]
    assert all(l["bringback"] for l in got["lineups"])


def test_min_salary_floor_is_respected(tmp_path):
    got = run(tmp_path, ["--min-salary", "30000"])
    assert got["lineups"]
    assert all(l["salary"] >= 30000 for l in got["lineups"])


def test_every_lineup_is_legal_and_anti_correlation_holds(tmp_path):
    got = run(tmp_path, ["--entries", str(make_entries(tmp_path, 4))])
    sal = {r.split(",")[3]: r.split(",") for r in
           (tmp_path / "sal.csv").read_text(encoding="utf-8").splitlines()[1:]}
    for lineup in got["lineups"]:
        roster = lineup["roster"]
        assert len(set(roster)) == 9
        positions = [sal[i][0] for i in roster]
        assert positions.count("QB") == 1
        assert positions.count("DST") == 1
        assert lineup["salary"] <= 50000
        games = {sal[i][6].split()[0] for i in roster}
        assert len(games) >= 2
        dst = [i for i in roster if sal[i][0] == "DST"][0]
        dst_game = sal[dst][6].split()[0]
        away, home = dst_game.split("@")
        foe = home if sal[dst][7] == away else away
        assert not [i for i in roster if sal[i][7] == foe and sal[i][0] != "DST"]


def test_slate_context_is_read_and_recorded(tmp_path):
    ctx = tmp_path / "ctx.json"
    ctx.write_text(json.dumps({
        "implied_team_totals": {"AAA": 28.0, "BBB": 18.0},
        "projected_ownership": {}, "role_boosts": {},
    }), encoding="utf-8")
    got = run(tmp_path, ["--slate-context", str(ctx)])
    assert got["construction"]["slate_context"] == str(ctx)


def test_no_slate_context_means_no_stale_week_one_tables(tmp_path):
    """Regression on the real defect: the builder used to carry literal
    2026-09-13 implied totals, ownership and role boosts as module constants."""

    source = SCRIPT.read_text(encoding="utf-8")
    for stale in ("Jahmyr Gibbs", "Brock Bowers", "Michael Mayer", "Kendre Miller"):
        assert stale not in source, f"{stale} is a hardcoded Week 1 value"
    got = run(tmp_path)
    assert got["construction"]["slate_context"] is None


def test_empty_pool_is_a_named_stop(tmp_path):
    sal, sc, st = make_pool(tmp_path)
    sc.write_text(json.dumps({"by_dk_id": {}}), encoding="utf-8")
    with pytest.raises(SystemExit) as caught:
        build.main(["--scores", str(sc), "--salaries", str(sal), "--status", str(st),
                    "--out", str(tmp_path / "o.json"), "--lineups", "2"])
    assert "EMPTY_POOL" in str(caught.value)


def test_inactive_players_never_enter_the_pool(tmp_path):
    sal, sc, st = make_pool(tmp_path)
    scores = json.loads(sc.read_text(encoding="utf-8"))["by_dk_id"]
    benched = sorted(scores)[0]
    st.write_text(
        "TEAM,PLAYER_OR_GSIS_ID,STATUS,SOURCE_URL,OBSERVED_AT\n"
        f"AAA,{benched},INACTIVE,,\n",
        encoding="utf-8",
    )
    out = tmp_path / "p.json"
    build.main(["--scores", str(sc), "--salaries", str(sal), "--status", str(st),
                "--out", str(out), "--lineups", "4"])
    got = json.loads(out.read_text(encoding="utf-8"))
    assert all(benched not in l["roster"] for l in got["lineups"])
