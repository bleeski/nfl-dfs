"""Acceptance for `scripts/make_slate_context.py`.

The script exists because `build_classic_portfolio.py` carried three hardcoded
2026-09-13 tables that had to be retyped every week. Its value depends on the
derivation being right and on it refusing to invent the two things no approved
source carries. Nothing here touches the network.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "make_slate_context.py"


def _load():
    spec = importlib.util.spec_from_file_location("make_slate_context", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["make_slate_context"] = module
    spec.loader.exec_module(module)
    return module


ctx = _load()

SALARY_HEADER = (
    "Position,Name + ID,Name,ID,Roster Position,Salary,"
    "Game Info,TeamAbbrev,AvgPointsPerGame,Status\n"
)
GAMES_HEADER = "gameday,away_team,home_team,total_line,spread_line,roof\n"


def salary(tmp_path: Path, cells: list[tuple[str, str]]) -> Path:
    p = tmp_path / "sal.csv"
    body = "".join(
        f"RB,P{i} ({i}),P{i},{i},RB/FLEX,5000,{m} {d},{m.split('@')[1]},0,\n"
        for i, (m, d) in enumerate(cells)
    )
    p.write_text(SALARY_HEADER + body, encoding="utf-8")
    return p


def games(tmp_path: Path, rows: list[tuple[str, str, str, str, str]]) -> Path:
    p = tmp_path / "games.csv"
    body = "".join(f"{d},{a},{h},{t},{s},outdoors\n" for d, a, h, t, s in rows)
    p.write_text(GAMES_HEADER + body, encoding="utf-8")
    return p


def test_implied_totals_follow_the_market_identity(tmp_path):
    """home = total/2 + spread/2, away = total/2 - spread/2."""

    s = salary(tmp_path, [("CAR@ATL", "09/20/2026 01:00PM ET")])
    g = games(tmp_path, [("2026-09-20", "CAR", "ATL", "43.5", "-2.5")])
    out = tmp_path / "ctx.json"
    ctx.main(["--salaries", str(s), "--games", str(g), "--out", str(out)])
    got = json.loads(out.read_text(encoding="utf-8"))["implied_team_totals"]
    assert got["ATL"] == pytest.approx(20.5)
    assert got["CAR"] == pytest.approx(23.0)
    assert got["ATL"] + got["CAR"] == pytest.approx(43.5)


def test_only_this_slates_games_are_used(tmp_path):
    """A games.csv spans the season; a row for another week must not leak in."""

    s = salary(tmp_path, [("CAR@ATL", "09/20/2026 01:00PM ET")])
    g = games(
        tmp_path,
        [
            ("2026-09-20", "CAR", "ATL", "43.5", "-2.5"),
            ("2026-09-27", "CAR", "ATL", "51.0", "+7.0"),
            ("2026-09-20", "GB", "NYJ", "44.5", "-3.5"),
        ],
    )
    out = tmp_path / "ctx.json"
    ctx.main(["--salaries", str(s), "--games", str(g), "--out", str(out)])
    got = json.loads(out.read_text(encoding="utf-8"))
    assert set(got["implied_team_totals"]) == {"CAR", "ATL"}
    assert got["implied_team_totals"]["ATL"] == pytest.approx(20.5)
    assert got["games"] == ["CAR@ATL"]


def test_ownership_and_boosts_are_empty_unless_supplied(tmp_path):
    """No approved source carries ownership, so it is never invented."""

    s = salary(tmp_path, [("CAR@ATL", "09/20/2026 01:00PM ET")])
    g = games(tmp_path, [("2026-09-20", "CAR", "ATL", "43.5", "-2.5")])
    out = tmp_path / "ctx.json"
    ctx.main(["--salaries", str(s), "--games", str(g), "--out", str(out)])
    got = json.loads(out.read_text(encoding="utf-8"))
    assert got["projected_ownership"] == {}
    assert got["role_boosts"] == {}


def test_a_team_with_no_market_line_is_named_not_defaulted(tmp_path):
    """Silence about a missing line is how a 21.0 baseline becomes invisible."""

    s = salary(
        tmp_path,
        [("CAR@ATL", "09/20/2026 01:00PM ET"), ("GB@NYJ", "09/20/2026 01:00PM ET")],
    )
    g = games(tmp_path, [("2026-09-20", "CAR", "ATL", "43.5", "-2.5")])
    out = tmp_path / "ctx.json"
    ctx.main(["--salaries", str(s), "--games", str(g), "--out", str(out)])
    got = json.loads(out.read_text(encoding="utf-8"))
    assert sorted(got["teams_without_a_market_line"]) == ["GB", "NYJ"]


def test_matchup_comes_from_the_first_token_not_the_whole_cell(tmp_path):
    """Real 2026-09-20 row: MIA@SF, total 44.5, spread +13.5 (home favoured)."""

    s = salary(tmp_path, [("MIA@SF", "09/20/2026 04:25PM ET")])
    g = games(tmp_path, [("2026-09-20", "MIA", "SF", "44.5", "13.5")])
    out = tmp_path / "ctx.json"
    ctx.main(["--salaries", str(s), "--games", str(g), "--out", str(out)])
    got = json.loads(out.read_text(encoding="utf-8"))
    assert got["games"] == ["MIA@SF"]
    assert got["implied_team_totals"]["SF"] == pytest.approx(29.0)
    assert got["implied_team_totals"]["MIA"] == pytest.approx(15.5)


def test_spread_sign_convention_is_home_favoured(tmp_path):
    """Guards the sign directly: a negative spread means the home side is the
    underdog. Getting this backwards silently inverts every team on the slate."""

    s = salary(tmp_path, [("CAR@ATL", "09/20/2026 01:00PM ET")])
    g = games(tmp_path, [("2026-09-20", "CAR", "ATL", "40.0", "-6.0")])
    out = tmp_path / "ctx.json"
    ctx.main(["--salaries", str(s), "--games", str(g), "--out", str(out)])
    got = json.loads(out.read_text(encoding="utf-8"))["implied_team_totals"]
    assert got["ATL"] == pytest.approx(17.0)
    assert got["CAR"] == pytest.approx(23.0)


def test_empty_salary_file_is_a_named_stop(tmp_path):
    p = tmp_path / "empty.csv"
    p.write_text(SALARY_HEADER, encoding="utf-8")
    g = games(tmp_path, [("2026-09-20", "CAR", "ATL", "43.5", "-2.5")])
    with pytest.raises(SystemExit):
        ctx.main(["--salaries", str(p), "--games", str(g), "--out", str(tmp_path / "o.json")])


def test_a_malformed_market_line_is_skipped_not_guessed(tmp_path):
    s = salary(tmp_path, [("CAR@ATL", "09/20/2026 01:00PM ET")])
    g = tmp_path / "games.csv"
    g.write_text(GAMES_HEADER + "2026-09-20,CAR,ATL,,,outdoors\n", encoding="utf-8")
    out = tmp_path / "ctx.json"
    ctx.main(["--salaries", str(s), "--games", str(g), "--out", str(out)])
    got = json.loads(out.read_text(encoding="utf-8"))
    assert got["implied_team_totals"] == {}
    assert sorted(got["teams_without_a_market_line"]) == ["ATL", "CAR"]
