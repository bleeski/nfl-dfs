"""Acceptance for `scripts/swap_inactives.py`.

Promoted from a 2026-09-27 slate-day scratchpad that swapped newly inactive
players and worked named value adds into the Week 3 Classic portfolio by
hand. Four teams across two games, deep enough at every slot for a single
swap, a two-player fallback, a value add and a salary redeploy, each with
just enough bench depth and no more, so a wrong legality or cap check shows
up as a real failure rather than being masked by an oversized pool.

Nothing here touches the network or the engine.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "swap_inactives.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


swap = _load("swap_inactives", SCRIPT)

SALARY_HEADER = (
    "Position,Name + ID,Name,ID,Roster Position,Salary,"
    "Game Info,TeamAbbrev,AvgPointsPerGame,Status\n"
)
GAME_A = "AAA@BBB 09/28/2026 01:00PM ET"
GAME_B = "CCC@DDD 09/28/2026 01:00PM ET"
GAME_LATE = "CCC@DDD 09/28/2026 08:20PM ET"
TEAM_GAME = {"AAA": GAME_A, "BBB": GAME_A, "CCC": GAME_B, "DDD": GAME_B}
COUNTS = {"QB": 1, "RB": 3, "WR": 4, "TE": 2, "DST": 1}


def roster_position(pos: str) -> str:
    return pos if pos in ("QB", "DST") else f"{pos}/FLEX"


def _rows(team_game=None, statuses=None, salaries=None, scores_override=None):
    team_game = team_game or TEAM_GAME
    statuses = statuses or {}
    salaries = salaries or {}
    rows, scores, sal_by_id = [], {}, {}
    for team, game in team_game.items():
        for pos, n in COUNTS.items():
            for k in range(n):
                dk_id = f"{team}{pos}{k}"
                name = f"{team} {pos}{k}"
                default_salary = 4000 + k * 100
                salary = salaries.get(dk_id, default_salary)
                status = statuses.get(dk_id, "")
                rows.append(
                    f"{pos},{name} ({dk_id}),{name},{dk_id},{roster_position(pos)},{salary},"
                    f"{game},{team},0,{status}\n"
                )
                scores[dk_id] = scores_override.get(dk_id, 10.0 + k) if scores_override else 10.0 + k
                sal_by_id[dk_id] = salary
    return rows, scores, sal_by_id


def make_salaries(tmp_path: Path, name: str, **kwargs) -> tuple[Path, dict]:
    rows, scores, _sal = _rows(**kwargs)
    path = tmp_path / name
    path.write_text(SALARY_HEADER + "".join(rows), encoding="utf-8")
    return path, scores


def make_scores(tmp_path: Path, scores: dict, excluded=()) -> Path:
    path = tmp_path / "scores.json"
    doc = {
        "schema_version": "nfl_prior_pool_scores_v1",
        "score_version": "v1",
        "by_dk_id": scores,
        "by_person": {},
        "excluded_dk_ids": sorted(excluded),
    }
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


# A DST's own opponent must have zero rostered skill players (the engine's own
# anti-correlation rule, `build_classic_portfolio.py`'s `anti()`), so the DST
# always comes from the game the QB is NOT in, and everything else in that
# game comes from the DST's own side only.
#
# LINEUP_1: AAA QB + AAA WR (stack) + BBB WR (bring-back, BBB is AAA's
# opponent); DST is CCC (game CCC@DDD), so DDD contributes nothing, and the
# rest of the roster is CCC's own offense.
LINEUP_1 = ["AAAQB0", "AAAWR0", "BBBWR0", "CCCRB0", "CCCRB1", "CCCRB2", "CCCWR0", "CCCTE0", "CCCDST0"]
# LINEUP_2: mirrored -- CCC QB stacked with a CCC WR, bring-back from DDD;
# DST is AAA (game AAA@BBB), so BBB contributes nothing.
LINEUP_2 = ["CCCQB0", "CCCWR0", "DDDWR0", "AAARB0", "AAARB1", "AAARB2", "AAAWR1", "AAATE0", "AAADST0"]


def make_portfolio(tmp_path: Path, assignments: dict, *, max_exposure=6, max_overlap=6,
                    cap=50000, min_salary=0) -> Path:
    doc = {
        "lineups": [],
        "assignments_by_entry_id": assignments,
        "unfilled_entry_ids": [],
        "operator_excluded_entry_ids": {},
        "construction": {
            "max_exposure": max_exposure, "max_overlap": max_overlap,
            "cap": cap, "min_salary": min_salary,
        },
    }
    path = tmp_path / "portfolio.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def _invoke(tmp_path, extra, out_name="out.json"):
    out = tmp_path / out_name
    code = swap.main([*extra, "--out", str(out)])
    written = code != swap.EXIT_REFUSED and out.exists()
    return code, (json.loads(out.read_text(encoding="utf-8")) if written else None)


def test_lineups_are_legal_and_distinct_before_any_edit():
    """Sanity on the fixture itself, not the tool: both hand-built lineups obey
    the same legality this tool enforces."""

    from io import StringIO
    import csv as _csv

    rows, _scores, _sal = _rows()
    sal = {}
    reader = _csv.DictReader(StringIO(SALARY_HEADER + "".join(rows)))
    for row in reader:
        sal[row["ID"]] = {**row, "Salary": int(row["Salary"])}
    board = swap.Board(sal, 50000, 0)
    assert board.is_legal(LINEUP_1)
    assert board.is_legal(LINEUP_2)
    assert frozenset(LINEUP_1) != frozenset(LINEUP_2)


def test_inactive_mode_single_swaps_a_newly_out_player(tmp_path):
    salaries, scores = make_salaries(tmp_path, "sal.csv", statuses={"AAAWR0": "OUT"})
    scores_path = make_scores(tmp_path, scores)
    portfolio = make_portfolio(tmp_path, {"E1": list(LINEUP_1), "E2": list(LINEUP_2)})
    code, doc = _invoke(tmp_path, [
        "--portfolio", str(portfolio), "--scores", str(scores_path), "--salaries", str(salaries),
        "--mode", "inactive", "--inactive-id", "AAAWR0",
    ])
    assert code == swap.EXIT_OK
    roster = doc["assignments_by_entry_id"]["E1"]
    assert "AAAWR0" not in roster
    assert len(set(roster)) == 9
    assert "SWAP E1: AAA WR0" in doc["construction"]["swap_log"][0]
    assert doc["construction"]["mode"] == "inactive"
    assert doc["construction"]["changed_entry_ids"] == ["E1"]


def test_inactive_mode_never_repeats_or_exceeds_caps(tmp_path):
    """The replacement must keep every lineup unique and within the caps this
    portfolio was built under, exactly as `build_classic_portfolio.py` would
    enforce on a fresh build."""

    salaries, scores = make_salaries(tmp_path, "sal.csv", statuses={"CCCRB0": "OUT"})
    scores_path = make_scores(tmp_path, scores)
    portfolio = make_portfolio(
        tmp_path, {"E1": list(LINEUP_1), "E2": list(LINEUP_2)}, max_exposure=1, max_overlap=8,
    )
    code, doc = _invoke(tmp_path, [
        "--portfolio", str(portfolio), "--scores", str(scores_path), "--salaries", str(salaries),
        "--mode", "inactive", "--inactive-id", "CCCRB0",
    ])
    assert code == swap.EXIT_OK
    e1, e2 = doc["assignments_by_entry_id"]["E1"], doc["assignments_by_entry_id"]["E2"]
    assert frozenset(e1) != frozenset(e2)
    exposure = {}
    for roster in (e1, e2):
        for dk_id in roster:
            exposure[dk_id] = exposure.get(dk_id, 0) + 1
    assert max(exposure.values()) <= 1


def test_inactive_mode_falls_back_to_a_two_player_swap_when_the_position_breaks(tmp_path):
    """Every same-slot single swap is illegal for its own reason -- the one
    scored RB candidate busts the cap alone, and any WR/TE candidate would
    leave the roster with only one RB (below the minimum) -- so the tool must
    trade the absent RB for that RB candidate AND, in the same move, trade a
    bench WR for a cheaper one, funding the first leg's cost from the
    second's saving."""

    # Exactly two RBs (one below the usual fixture), so losing the second
    # one to anything but another RB drops the count under the minimum.
    lineup = ["AAAQB0", "AAAWR0", "BBBWR0", "CCCRB0", "CCCRB1", "CCCWR0", "CCCWR1", "CCCTE0", "CCCDST0"]
    flat = {dk_id: 4000 for dk_id in lineup}
    salaries, scores = make_salaries(
        tmp_path, "sal.csv",
        salaries={**flat, "AAARB0": 6000, "AAAWR1": 1000},
        scores_override={"AAARB0": 10.0, "AAAWR1": 5.0},
    )
    # Zero every other flex candidate: the only ones left scored are the RB
    # (too expensive alone) and the cheap WR (this test's second leg).
    for dk_id in list(scores):
        if dk_id not in lineup and dk_id not in ("AAARB0", "AAAWR1"):
            scores[dk_id] = 0.0
    scores_path = make_scores(tmp_path, scores)
    portfolio = make_portfolio(tmp_path, {"E1": lineup}, max_exposure=9, max_overlap=9, cap=36000)
    code, doc = _invoke(tmp_path, [
        "--portfolio", str(portfolio), "--scores", str(scores_path), "--salaries", str(salaries),
        "--mode", "inactive", "--inactive-id", "CCCRB1",
    ])
    assert code == swap.EXIT_OK
    roster = doc["assignments_by_entry_id"]["E1"]
    assert "CCCRB1" not in roster
    assert "AAARB0" in roster and "AAAWR1" in roster
    # Both CCCWR0 and CCCWR1 are legal to drop; the higher-gain pairing (the
    # lower-scored bench player leaves) wins.
    assert "CCCWR0" not in roster
    assert len(set(roster)) == 9
    log = "\n".join(doc["construction"]["swap_log"])
    assert log.startswith("SWAP2 E1: CCC RB1")


def test_late_swap_never_touches_a_locked_cell(tmp_path):
    """A game already underway is untouchable, whatever else changed."""

    team_game = dict(TEAM_GAME)
    team_game["CCC"] = GAME_LATE
    team_game["DDD"] = GAME_LATE
    salaries, scores = make_salaries(
        tmp_path, "sal.csv", team_game=team_game,
        statuses={"AAAWR0": "OUT", "CCCTE0": "OUT"},
    )
    scores_path = make_scores(tmp_path, scores)
    portfolio = make_portfolio(tmp_path, {"E1": list(LINEUP_1)}, max_exposure=9, max_overlap=9)
    # GAME_A (AAA@BBB) kicks 1:00pm ET = 17:00 UTC; GAME_LATE (CCC@DDD) kicks
    # 8:20pm ET the same day = 00:20 UTC the next. `now` sits between them.
    now = datetime(2026, 9, 28, 18, 0, tzinfo=timezone.utc)
    code, doc = _invoke(tmp_path, [
        "--portfolio", str(portfolio), "--scores", str(scores_path), "--salaries", str(salaries),
        "--mode", "late-swap", "--now", now.isoformat(),
        "--inactive-id", "AAAWR0", "--inactive-id", "CCCTE0",
    ])
    roster = doc["assignments_by_entry_id"]["E1"]
    assert "AAAWR0" in roster  # AAA@BBB already locked before `now`: untouched
    assert "CCCTE0" not in roster  # CCC@DDD not yet locked: swappable
    assert code == swap.EXIT_PARTIAL


def test_value_add_works_a_named_player_into_the_target_count_of_lineups(tmp_path):
    salaries, scores = make_salaries(tmp_path, "sal.csv")
    scores["AAAWR3"] = 99.0  # a clear upgrade over anyone at WR/FLEX not in the core
    scores_path = make_scores(tmp_path, scores)
    portfolio = make_portfolio(tmp_path, {"E1": list(LINEUP_1), "E2": list(LINEUP_2)}, max_exposure=9, max_overlap=9)
    code, doc = _invoke(tmp_path, [
        "--portfolio", str(portfolio), "--scores", str(scores_path), "--salaries", str(salaries),
        "--mode", "value-add", "--add", "AAA WR3", "--target-count", "2",
    ])
    assert code == swap.EXIT_OK
    exposure = sum(1 for roster in doc["assignments_by_entry_id"].values() if "AAAWR3" in roster)
    assert exposure == 2


def test_value_add_never_touches_the_qb_stack_or_bringback(tmp_path):
    salaries, scores = make_salaries(tmp_path, "sal.csv")
    scores["DDDWR3"] = 99.0
    scores_path = make_scores(tmp_path, scores)
    portfolio = make_portfolio(tmp_path, {"E1": list(LINEUP_1)}, max_exposure=9, max_overlap=9)
    _code, doc = _invoke(tmp_path, [
        "--portfolio", str(portfolio), "--scores", str(scores_path), "--salaries", str(salaries),
        "--mode", "value-add", "--add", "DDD WR3", "--target-count", "5",
    ])
    roster = doc["assignments_by_entry_id"]["E1"]
    # LINEUP_1's QB is AAAQB0, stack is AAAWR0, bring-back is BBBWR0: none may
    # be displaced even though the new player scores far higher.
    assert {"AAAQB0", "AAAWR0", "BBBWR0"} <= set(roster)


def test_redeploy_spends_headroom_on_one_upgrade_per_changed_lineup(tmp_path):
    """After a plain inactive swap, ample cap room (50000 against a ~36000
    roster) funds one non-core upgrade. BBB is safe (neither the QB's own
    game's other side is off-limits here, nor CCC/DDD's DST relationship)."""

    salaries, scores = make_salaries(tmp_path, "sal.csv", statuses={"CCCRB1": "OUT"})
    scores["BBBRB1"] = 50.0  # a clear non-core upgrade
    scores_path = make_scores(tmp_path, scores)
    portfolio = make_portfolio(tmp_path, {"E1": list(LINEUP_1)}, max_exposure=9, max_overlap=9, cap=50000)

    inactive_out = tmp_path / "after_inactive.json"
    code = swap.main([
        "--portfolio", str(portfolio), "--scores", str(scores_path), "--salaries", str(salaries),
        "--mode", "inactive", "--inactive-id", "CCCRB1", "--out", str(inactive_out),
    ])
    assert code == swap.EXIT_OK

    redeploy_out = tmp_path / "after_redeploy.json"
    code = swap.main([
        "--portfolio", str(inactive_out), "--scores", str(scores_path), "--salaries", str(salaries),
        "--mode", "redeploy", "--out", str(redeploy_out),
    ])
    assert code == swap.EXIT_OK
    doc = json.loads(redeploy_out.read_text(encoding="utf-8"))
    roster = doc["assignments_by_entry_id"]["E1"]
    assert "BBBRB1" in roster
    log = "\n".join(doc["construction"]["swap_log"])
    assert "REDEPLOY E1:" in log


def test_refuses_to_overwrite_an_existing_out_path(tmp_path):
    salaries, scores = make_salaries(tmp_path, "sal.csv", statuses={"AAAWR0": "OUT"})
    scores_path = make_scores(tmp_path, scores)
    portfolio = make_portfolio(tmp_path, {"E1": list(LINEUP_1)})
    out = tmp_path / "out.json"
    out.write_text("stale", encoding="utf-8")
    code = swap.main([
        "--portfolio", str(portfolio), "--scores", str(scores_path), "--salaries", str(salaries),
        "--mode", "inactive", "--inactive-id", "AAAWR0", "--out", str(out),
    ])
    assert code == swap.EXIT_REFUSED
    assert out.read_text(encoding="utf-8") == "stale"


def test_refuses_a_mode_missing_its_required_arguments(tmp_path):
    salaries, scores = make_salaries(tmp_path, "sal.csv")
    scores_path = make_scores(tmp_path, scores)
    portfolio = make_portfolio(tmp_path, {"E1": list(LINEUP_1)})
    code, _doc = _invoke(tmp_path, [
        "--portfolio", str(portfolio), "--scores", str(scores_path), "--salaries", str(salaries),
        "--mode", "value-add",
    ])
    assert code == swap.EXIT_REFUSED
