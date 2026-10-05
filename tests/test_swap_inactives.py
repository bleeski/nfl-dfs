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

import collections
import importlib.util
import json
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "swap_inactives.py"
QA_SCRIPT = REPO_ROOT / "scripts" / "qa_classic_portfolio.py"
WEEK4 = REPO_ROOT / "data" / "inbox" / "slates" / "wk4-classic-2026-10-04"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


swap = _load("swap_inactives", SCRIPT)
qa = _load("qa_classic_portfolio_for_swap_parity", QA_SCRIPT)

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


def make_scores(tmp_path: Path, scores: dict, excluded=(), operator=()) -> Path:
    path = tmp_path / "scores.json"
    doc = {
        "schema_version": "nfl_prior_pool_scores_v1",
        "score_version": "v1",
        "by_dk_id": scores,
        "by_person": {},
        "excluded_dk_ids": sorted(excluded),
        "operator_construction_exclusions": list(operator),
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


# --------------------------------------------------------------------------- #
# Session 62 (R37, P9 part 3): redeploy is a Pareto gain or it does not happen.
# --------------------------------------------------------------------------- #
#
# The fixtures below are hand-built so every proxy is countable by eye. X is the one upgrade candidate (score
# 20 against 10 for everyone else), and the portfolio's exposure decides whether taking it is a Pareto gain.
# E1's non-core pass catchers are CCCWR0 and CCCWR1 (its RBs and TE cannot become a WR and stay legal; the DST
# and the QB are never outgoing; AAA and BBB are the QB's game, so core).

X = "CCCWR3"
E1 = ["AAAQB0", "AAAWR0", "BBBWR0", "CCCRB0", "CCCRB1", "CCCWR0", "CCCWR1", "CCCTE0", "CCCDST0"]
E2_WITH_X = ["AAAQB0", "AAAWR0", "BBBWR0", "CCCRB2", "AAARB0", "CCCWR3", "CCCWR2", "CCCTE1", "CCCDST0"]
E2_WITHOUT_X = ["AAAQB0", "AAAWR0", "BBBWR0", "CCCRB2", "AAARB0", "CCCWR2", "AAAWR1", "CCCTE1", "CCCDST0"]
E3 = ["AAAQB0", "AAAWR0", "BBBWR0", "CCCRB0", "AAARB0", "CCCWR2", "AAAWR2", "CCCTE0", "CCCDST0"]
# Every skill player is AAA or BBB (core), the DST is CCC's: a legal DST swap to DDDDST0 exists, a bigger prior
# exists at QB and DST, and still nothing may move.
ALL_CORE = ["AAAQB0", "AAAWR0", "BBBWR0", "AAARB0", "BBBRB0", "AAAWR1", "BBBWR1", "AAATE0", "CCCDST0"]


def _pareto_fixture(tmp_path, *, other=E2_WITHOUT_X, first=E1, x_score=20.0, statuses=None, salaries=None,
                    excluded=(), operator=(), min_salary=0, scores_patch=None, extra_rows=None, max_overlap=9):
    sal_path, scores = make_salaries(tmp_path, "sal.csv", statuses=statuses, salaries=salaries)
    scores = {dk_id: 10.0 for dk_id in scores}
    scores[X] = x_score
    scores.update(scores_patch or {})
    scores_path = make_scores(tmp_path, scores, excluded=excluded, operator=operator)
    rosters = {"E1": list(first)}
    if other is not None:
        rosters["E2"] = list(other)
    rosters.update(extra_rows or {})
    portfolio = make_portfolio(tmp_path, rosters, max_exposure=9, max_overlap=max_overlap, min_salary=min_salary)
    return sal_path, scores_path, portfolio


def _redeploy(tmp_path, fixture, extra=(), out_name="out.json", portfolio=None):
    sal_path, scores_path, original = fixture
    return _invoke(tmp_path, [
        "--portfolio", str(portfolio or original), "--scores", str(scores_path), "--salaries", str(sal_path),
        "--mode", "redeploy", *extra,
    ], out_name)


def _proxies_by_hand(rosters):
    """The QA gate's own arithmetic, written out again so a test never checks the function against itself."""

    exposure = collections.Counter(i for r in rosters for i in r)
    top3 = [i for i, _n in exposure.most_common(3)]
    pairs = [len(set(a) & set(b)) for n, a in enumerate(rosters) for b in rosters[n + 1:]]
    return {
        "max_exposure": max(exposure.values()),
        "top3_union": sum(1 for r in rosters if any(i in r for i in top3)),
        "mean_overlap": statistics.mean(pairs) if pairs else 0.0,
        "distinct_people": len(exposure),
    }


# ---- the proxies ----------------------------------------------------------- #

BASE_PROXIES = dict(max_exposure=3, top3_union=5, pair_overlap_sum=10, distinct_people=20)


def test_washout_proxies_count_what_the_qa_gate_counts():
    rows = [["a", "b", "c"], ["a", "b", "d"], ["a", "e", "f"]]
    got = swap.washout_proxies(rows)
    assert got["rows"] == 3 and got["distinct_people"] == 6
    assert got["max_exposure"] == 3 and got["max_exposure_person"] == "a"
    assert got["pair_overlap_sum"] == 4 and got["mean_overlap"] == pytest.approx(4 / 3)
    assert got["top3_union"] == 3  # a, b and the first one-timer encountered (c) cover every row
    assert swap.washout_proxies([["a"]])["mean_overlap"] == 0.0  # no pair, nothing to average


@pytest.mark.parametrize("field,value,goal", [
    ("max_exposure", 4, "max_exposure"),
    ("top3_union", 6, "top3_union"),
    ("pair_overlap_sum", 11, "mean_overlap"),
    ("distinct_people", 19, "distinct_people"),
])
def test_proxies_hurt_names_the_one_goal_that_got_worse(field, value, goal):
    assert swap.proxies_hurt(BASE_PROXIES, {**BASE_PROXIES, field: value}) == [goal]


def test_equal_or_better_proxies_hurt_nothing():
    better = dict(max_exposure=2, top3_union=4, pair_overlap_sum=10, distinct_people=21)
    assert swap.proxies_hurt(BASE_PROXIES, better) == []
    assert swap.proxies_hurt(BASE_PROXIES, dict(BASE_PROXIES)) == []


def test_the_two_fewer_rule_is_a_filter_not_the_proof():
    """I (never used) replaces O (used four times): the incoming person is used at least two fewer times, the card's
    fast filter. But O's departure promotes X into the top three, and X's rows are disjoint from A and B's, so the
    top-3 union grows from four rows to seven. Only the portfolio-level check sees it."""

    rows = [["X", "f1"], ["X", "f2"], ["X", "f3"], ["A", "B", "O"], ["A", "B", "O"], ["A", "B", "O"], ["A", "B", "O"]]
    after = [list(r) for r in rows]
    after[6] = ["A", "B", "I"]
    counts = collections.Counter(i for r in rows for i in r)
    assert counts["I"] <= counts["O"] - 2
    before_p, after_p = swap.washout_proxies(rows), swap.washout_proxies(after)
    assert (before_p["top3_union"], after_p["top3_union"]) == (4, 7)
    assert swap.proxies_hurt(before_p, after_p) == ["top3_union"]


def test_washout_proxies_match_what_the_qa_gate_prints(tmp_path, capsys):
    rosters = {"E1": E1, "E2": E2_WITH_X, "E3": E3}
    out = tmp_path / "qa.json"
    code = qa.main([
        "--portfolio", str(make_portfolio(tmp_path, rosters)), "--salaries",
        str(make_salaries(tmp_path, "sal.csv")[0]), "--json", str(out),
    ])
    assert code == 0
    printed = capsys.readouterr().out
    got = swap.washout_proxies(list(rosters.values()))
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["max_exposure"] == got["max_exposure"] / got["rows"]
    assert doc["top3_union"] == got["top3_union"] / got["rows"]
    assert doc["distinct_players"] == got["distinct_people"]
    assert f"/ {got['mean_overlap']:.2f}" in printed


# ---- the rule -------------------------------------------------------------- #


def test_pareto_accepts_a_swap_that_raises_the_prior_and_hurts_no_proxy(tmp_path, capsys):
    """X is in no row, CCCWR0 is in one: the incoming person is used ONE fewer time, which the Week 4 hand rule
    (two fewer) skipped. Mean overlap is exactly equal, so it is a Pareto gain."""

    fixture = _pareto_fixture(tmp_path, other=E2_WITHOUT_X)
    code, doc = _redeploy(tmp_path, fixture)
    assert code == swap.EXIT_OK
    report = doc["construction"]["pareto_redeploy"]
    assert [(s["entry_id"], s["out"], s["in"]) for s in report["accepted"]] == [("E1", "CCCWR0", X)]
    assert doc["assignments_by_entry_id"]["E1"] == [X if i == "CCCWR0" else i for i in E1]
    assert doc["assignments_by_entry_id"]["E2"] == E2_WITHOUT_X
    before = swap.washout_proxies([E1, E2_WITHOUT_X])
    after = swap.washout_proxies(list(doc["assignments_by_entry_id"].values()))
    assert swap.proxies_hurt(before, after) == []
    assert report["before"]["prior_sum"] == pytest.approx(180.0)
    assert report["after"]["prior_sum"] == pytest.approx(190.0)
    assert report["fixed_point"] is True
    assert doc["construction"]["swap_log"][0].startswith("REDEPLOY E1: CCC WR0 -> CCC WR3")
    printed = capsys.readouterr().out
    assert "PARETO_REDEPLOY" in printed and "before:" in printed and "after :" in printed
    assert "NO_PARETO_GAIN" not in printed


def test_pareto_leaves_a_portfolio_alone_when_its_only_gain_concentrates_exposure(tmp_path, capsys):
    """X already sits in E2. Either swap in E1 (CCCWR0 or CCCWR1 for X) lifts the prior by ten, and either one
    raises the mean pairwise overlap and drops a distinct person. Nothing is written but the report."""

    fixture = _pareto_fixture(tmp_path, other=E2_WITH_X)
    code, doc = _redeploy(tmp_path, fixture)
    assert code == swap.EXIT_OK
    assert doc["assignments_by_entry_id"] == {"E1": E1, "E2": E2_WITH_X}
    report = doc["construction"]["pareto_redeploy"]
    assert report["accepted"] == []
    rejected = {(r["entry_id"], r["out"], r["in"]): r for r in report["rejected"]}
    assert set(rejected) == {("E1", "CCCWR0", X), ("E1", "CCCWR1", X)}
    for record in rejected.values():
        assert record["hurts"] == ["mean_overlap", "distinct_people"]
        assert record["prior_gain"] == pytest.approx(10.0)
    assert report["rejected_by_goal"] == {"max_exposure": 0, "top3_union": 0, "mean_overlap": 2, "distinct_people": 2}
    assert report["row_rejections"]["ILLEGAL"] >= 3  # RBs and the TE cannot turn into a WR
    assert "NO_PARETO_GAIN" in capsys.readouterr().out
    assert report["before"] == report["after"]


def test_rerunning_on_its_own_output_changes_nothing(tmp_path):
    fixture = _pareto_fixture(tmp_path, other=E2_WITHOUT_X)
    code, first = _redeploy(tmp_path, fixture)
    assert code == swap.EXIT_OK and first["construction"]["pareto_redeploy"]["accepted"]
    out = tmp_path / "out.json"
    for flags, name in (((), "again.json"), (("--changed-entry-id", "E1"), "again_e1.json")):
        code, again = _redeploy(tmp_path, fixture, flags, out_name=name, portfolio=out)
        assert code == swap.EXIT_OK
        assert again["assignments_by_entry_id"] == first["assignments_by_entry_id"]
        assert again["construction"]["pareto_redeploy"]["accepted"] == []


def test_a_no_change_run_can_be_rerun_with_no_flags(tmp_path):
    """It writes `changed_entry_ids: []`; the old default refused to run on that."""

    fixture = _pareto_fixture(tmp_path, other=E2_WITH_X)
    code, first = _redeploy(tmp_path, fixture)
    assert code == swap.EXIT_OK and first["construction"]["changed_entry_ids"] == []
    code, again = _redeploy(tmp_path, fixture, out_name="again.json", portfolio=tmp_path / "out.json")
    assert code == swap.EXIT_OK
    assert again["assignments_by_entry_id"] == first["assignments_by_entry_id"]


def test_redeploy_is_deterministic(tmp_path):
    fixture = _pareto_fixture(tmp_path, other=E2_WITHOUT_X)
    _redeploy(tmp_path, fixture, out_name="a.json")
    _redeploy(tmp_path, fixture, out_name="b.json")
    assert (tmp_path / "a.json").read_bytes() == (tmp_path / "b.json").read_bytes()


def test_changed_entry_id_restricts_the_rows_and_an_unknown_one_is_refused(tmp_path, capsys):
    fixture = _pareto_fixture(tmp_path, other=E2_WITHOUT_X)
    code, doc = _redeploy(tmp_path, fixture, ["--changed-entry-id", "E2"])
    assert code == swap.EXIT_OK
    assert doc["assignments_by_entry_id"]["E1"] == E1  # E1 holds a gain too, but E2 alone was the scope
    assert X in doc["assignments_by_entry_id"]["E2"]
    assert doc["construction"]["pareto_redeploy"]["rows_considered"] == 1
    code, doc = _redeploy(tmp_path, fixture, ["--changed-entry-id", "E9"], out_name="nope.json")
    assert code == swap.EXIT_REFUSED and doc is None
    assert "CHANGED_ENTRY_UNKNOWN" in capsys.readouterr().err


def test_the_qb_and_the_dst_never_move_for_a_bigger_prior(tmp_path):
    """DDDDST0 is a legal DST swap worth 89 prior points and CCCQB0 a bigger QB; AAAWR3 and BBBWR3 are bigger pass
    catchers on the QB's own game. Every skill player here is core, the QB and the DST are never outgoing."""

    fixture = _pareto_fixture(
        tmp_path, first=ALL_CORE, other=None,
        scores_patch={"DDDDST0": 99.0, "CCCQB0": 99.0, "AAAWR3": 99.0, "BBBWR3": 99.0},
    )
    code, doc = _redeploy(tmp_path, fixture)
    assert code == swap.EXIT_OK
    assert doc["assignments_by_entry_id"]["E1"] == ALL_CORE
    assert doc["construction"]["pareto_redeploy"]["accepted"] == []


def test_the_stack_and_bringback_never_move_for_a_bigger_prior(tmp_path):
    """AAAWR3 (99) beats every pass catcher in E1, the stackmate AAAWR0 and the bring-back BBBWR0 included, but
    only the CCC pass catchers are outgoing."""

    fixture = _pareto_fixture(tmp_path, other=E2_WITHOUT_X, scores_patch={"AAAWR3": 99.0})
    code, doc = _redeploy(tmp_path, fixture)
    assert code == swap.EXIT_OK
    outs = {s["out"] for s in doc["construction"]["pareto_redeploy"]["accepted"]}
    assert outs and outs <= {"CCCWR0", "CCCWR1"}
    assert {"AAAQB0", "AAAWR0", "BBBWR0", "CCCDST0"} <= set(doc["assignments_by_entry_id"]["E1"])


# CCCWR0 is in E1 and in LINEUP_2's row E3 (two rows), X in one other row: moving E1's CCCWR0 to X leaves the mean
# overlap exactly equal and every other proxy no worse, so only the row-level rules can refuse it.
def test_a_swap_that_would_repeat_another_row_is_refused_by_r29_not_by_the_proxies(tmp_path):
    e1_plus_x = [X if i == "CCCWR0" else i for i in E1]
    fixture = _pareto_fixture(tmp_path, other=e1_plus_x, extra_rows={"E3": LINEUP_2}, scores_patch={"CCCWR1": 20.0})
    code, doc = _redeploy(tmp_path, fixture)
    assert code == swap.EXIT_OK
    rows = list(doc["assignments_by_entry_id"].values())
    assert len({frozenset(r) for r in rows}) == len(rows)
    assert doc["assignments_by_entry_id"]["E1"] == E1
    report = doc["construction"]["pareto_redeploy"]
    assert report["accepted"] == [] and report["row_rejections"]["CAPS_OR_DISTINCT"] >= 1


def test_a_swap_that_would_break_the_overlap_cap_is_refused_by_the_cap_not_the_proxies(tmp_path):
    fixture = _pareto_fixture(tmp_path, other=E2_WITH_X, extra_rows={"E3": LINEUP_2}, max_overlap=4)
    code, doc = _redeploy(tmp_path, fixture)
    assert code == swap.EXIT_OK
    rows = list(doc["assignments_by_entry_id"].values())
    assert max(len(set(a) & set(b)) for n, a in enumerate(rows) for b in rows[n + 1:]) <= 4
    assert doc["assignments_by_entry_id"]["E1"] == E1  # E3 may take X; E1 may not, it would sit on E2 for 5 people
    report = doc["construction"]["pareto_redeploy"]
    assert all(taken["entry_id"] != "E1" for taken in report["accepted"])
    assert report["row_rejections"]["CAPS_OR_DISTINCT"] >= 1


@pytest.mark.parametrize("label,kwargs", [
    ("a questionable incoming player", dict(statuses={X: "Q"})),
    ("an out incoming player", dict(statuses={X: "OUT"})),
    ("a salary over the cap", dict(salaries={X: 20000})),
    ("a person the scores file excludes by id", dict(excluded=(X,))),
    ("a person the scores file excludes by name", dict(operator=("CCC WR3",))),
    ("a person the scores file excludes by id in the operator list", dict(operator=(X,))),
])
def test_an_ineligible_incoming_person_is_never_added(tmp_path, label, kwargs):
    fixture = _pareto_fixture(tmp_path, other=E2_WITHOUT_X, **kwargs)
    code, doc = _redeploy(tmp_path, fixture)
    assert code == swap.EXIT_OK, label
    assert doc["assignments_by_entry_id"] == {"E1": E1, "E2": E2_WITHOUT_X}, label
    assert doc["construction"]["pareto_redeploy"]["rejected"] == [], label


STATUS_HEADER = "TEAM,PLAYER_OR_GSIS_ID,STATUS,SOURCE_URL,OBSERVED_AT\n"


def _status_file(tmp_path, *rows, name="status.csv"):
    path = tmp_path / name
    path.write_text(STATUS_HEADER + "".join(f"{team},{dk_id},{status},https://example.org/x,2026-09-28T15:00:00+00:00\n"
                                            for team, dk_id, status in rows), encoding="utf-8")
    return path


def test_an_officially_inactive_person_is_never_added_even_if_the_scores_file_scores_him(tmp_path, capsys):
    fixture = _pareto_fixture(tmp_path, other=E2_WITHOUT_X)
    inactive = _status_file(tmp_path, ("CCC", X, "INACTIVE"))
    code, doc = _redeploy(tmp_path, fixture, ["--status", str(inactive)])
    assert code == swap.EXIT_OK
    assert doc["assignments_by_entry_id"] == {"E1": E1, "E2": E2_WITHOUT_X}
    active = _status_file(tmp_path, ("CCC", X, "ACTIVE"), name="active.csv")  # only INACTIVE rows keep a person out
    code, doc = _redeploy(tmp_path, fixture, ["--status", str(active)], out_name="active_out.json")
    assert code == swap.EXIT_OK and X in doc["assignments_by_entry_id"]["E1"]
    header_only = _status_file(tmp_path, name="header_only.csv")  # no official observation names nobody
    code, doc = _redeploy(tmp_path, fixture, ["--status", str(header_only)], out_name="header_out.json")
    assert code == swap.EXIT_OK and X in doc["assignments_by_entry_id"]["E1"]
    bad = tmp_path / "bad.csv"
    bad.write_text("TEAM,PLAYER,STATE\n", encoding="utf-8")
    code, doc = _redeploy(tmp_path, fixture, ["--status", str(bad)], out_name="bad_out.json")
    assert code == swap.EXIT_REFUSED and doc is None
    assert "STATUS_COLUMNS_MISSING" in capsys.readouterr().err


def test_status_rows_match_by_id_case_and_whitespace_like_a_careful_reader(tmp_path):
    fixture = _pareto_fixture(tmp_path, other=E2_WITHOUT_X)
    padded = _status_file(tmp_path, ("CCC", f" {X} ", "inactive"), name="padded.csv")
    code, doc = _redeploy(tmp_path, fixture, ["--status", str(padded)])
    assert code == swap.EXIT_OK and doc["assignments_by_entry_id"] == {"E1": E1, "E2": E2_WITHOUT_X}


def test_a_scores_file_that_declares_no_exclusions_is_named_on_stderr(tmp_path, capsys):
    fixture = _pareto_fixture(tmp_path, other=E2_WITHOUT_X)
    scores_path = fixture[1]
    doc = json.loads(scores_path.read_text(encoding="utf-8"))
    del doc["excluded_dk_ids"]
    scores_path.write_text(json.dumps(doc), encoding="utf-8")
    code, written = _redeploy(tmp_path, fixture)
    assert code == swap.EXIT_OK and written["construction"]["pareto_redeploy"]["gated_people"] == 0
    assert "SCORES_FILE_HAS_NO_EXCLUDED_DK_IDS" in capsys.readouterr().err
    declared = tmp_path / "declared"
    declared.mkdir()
    _redeploy(declared, _pareto_fixture(declared, other=E2_WITHOUT_X))
    assert "SCORES_FILE_HAS_NO_EXCLUDED_DK_IDS" not in capsys.readouterr().err


def test_redeploy_only_flags_are_refused_in_every_other_mode(tmp_path, capsys):
    fixture = _pareto_fixture(tmp_path, other=E2_WITHOUT_X)
    sal_path, scores_path, portfolio = fixture
    status = _status_file(tmp_path, ("CCC", X, "INACTIVE"))
    for n, (mode, flags) in enumerate([
        ("value-add", ["--add", "CCC WR3", "--protect", "Nobody Atall"]),
        ("inactive", ["--inactive-id", "CCCWR0", "--protect-from", str(tmp_path / "missing.json")]),
        ("value-add", ["--add", "CCC WR3", "--status", str(status)]),
    ]):
        out = tmp_path / f"other_{n}.json"
        code = swap.main(["--portfolio", str(portfolio), "--scores", str(scores_path), "--salaries", str(sal_path),
                          "--mode", mode, *flags, "--out", str(out)])
        assert code == swap.EXIT_REFUSED and not out.exists()
        assert "REDEPLOY_ONLY_FLAG" in capsys.readouterr().err


def test_a_later_mode_does_not_carry_an_earlier_redeploy_report(tmp_path):
    fixture = _pareto_fixture(tmp_path, other=E2_WITHOUT_X)
    code, first = _redeploy(tmp_path, fixture)
    assert code == swap.EXIT_OK and "pareto_redeploy" in first["construction"]
    code, second = _invoke(tmp_path, [
        "--portfolio", str(tmp_path / "out.json"), "--scores", str(fixture[1]), "--salaries", str(fixture[0]),
        "--mode", "value-add", "--add", "CCC WR2", "--target-count", "1",
    ], out_name="value_add.json")
    assert code == swap.EXIT_OK and "pareto_redeploy" not in second["construction"]


# ---- --protect ------------------------------------------------------------- #


def _run_json(tmp_path, ids, *, shape):
    people = [{"person": f"p{n}", "dk_id": dk_id, "name": f"name {n}", "min_rows": 1,
               "delivered_rows": [], "met": True} for n, dk_id in enumerate(ids)]
    block = {"version": "classic_judgment_pass_v1", "protected_people": people}
    doc = {"prior_review_reports": {"selection": {"judgment_pass": block}}} if shape == "run" else {"judgment_pass": block}
    path = tmp_path / f"{shape}.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


@pytest.mark.parametrize("flags,e1_takes_x", [
    (("--protect", "CCC WR0", "--protect", "CCCWR1"), False),  # a name and an id: E1 has nobody left to swap
    (("--protect", X), False),                                  # an incoming person is a move too
    (("--protect", "CCC WR0"), True),                           # the other one is still fair game
])
def test_a_protected_person_never_moves(tmp_path, capsys, flags, e1_takes_x):
    fixture = _pareto_fixture(tmp_path, other=E2_WITHOUT_X)
    code, doc = _redeploy(tmp_path, fixture, flags)
    assert code == swap.EXIT_OK
    assert "protected (rows before -> after):" in capsys.readouterr().out
    after = doc["assignments_by_entry_id"]["E1"]
    report = doc["construction"]["pareto_redeploy"]
    if e1_takes_x:
        assert X in after and "CCCWR1" not in after and "CCCWR0" in after
    else:
        assert after == E1 and all(s["entry_id"] != "E1" for s in report["accepted"])
    if X in flags:
        assert report["accepted"] == []
    assert report["protected"]
    for row in report["protected"]:
        assert row["rows_before"] == row["rows_after"], row["dk_id"]


@pytest.mark.parametrize("shape", ["run", "coverage"])
def test_protect_is_read_from_a_runs_judgment_pass(tmp_path, shape):
    fixture = _pareto_fixture(tmp_path, other=E2_WITHOUT_X)
    run_json = _run_json(tmp_path, ["CCCWR0", "CCCWR1"], shape=shape)
    code, doc = _redeploy(tmp_path, fixture, ["--protect-from", str(run_json)])
    assert code == swap.EXIT_OK
    assert doc["assignments_by_entry_id"]["E1"] == E1
    assert {row["dk_id"] for row in doc["construction"]["pareto_redeploy"]["protected"]} == {"CCCWR0", "CCCWR1"}


def test_an_empty_protected_list_is_accepted_and_changes_nothing_else(tmp_path):
    fixture = _pareto_fixture(tmp_path, other=E2_WITHOUT_X)
    run_json = _run_json(tmp_path, [], shape="run")
    code, doc = _redeploy(tmp_path, fixture, ["--protect-from", str(run_json)])
    assert code == swap.EXIT_OK
    assert doc["construction"]["pareto_redeploy"]["protected"] == []
    assert X in doc["assignments_by_entry_id"]["E1"]


def test_protect_refusals_name_the_problem_and_write_nothing(tmp_path, capsys):
    fixture = _pareto_fixture(tmp_path, other=E2_WITHOUT_X)
    sal_path = fixture[0]
    sal_path.write_text(sal_path.read_text(encoding="utf-8")
                        + "WR,CCC WR0 (ZZZ1),CCC WR0,ZZZ1,WR/FLEX,4000,CCC@DDD 09/28/2026 01:00PM ET,CCC,0,\n",
                        encoding="utf-8")
    no_pass = tmp_path / "no_pass.json"
    no_pass.write_text(json.dumps({"prior_review_reports": {}}), encoding="utf-8")
    cases = [
        (["--protect", "Nobody Atall"], "PROTECT_UNKNOWN"),
        (["--protect", "CCC WR0"], "PROTECT_AMBIGUOUS"),
        (["--protect-from", str(no_pass)], "PROTECT_FROM_HAS_NO_JUDGMENT_PASS"),
        (["--protect-from", str(_run_json(tmp_path, ["NOT_IN_THE_FILE"], shape="run"))], "PROTECT_ID_NOT_IN_SALARY_FILE"),
        (["--protect-from", str(tmp_path / "missing.json")], "PROTECT_FROM_UNREADABLE"),
    ]
    for n, (flags, code_name) in enumerate(cases):
        code, doc = _redeploy(tmp_path, fixture, flags, out_name=f"refused_{n}.json")
        assert code == swap.EXIT_REFUSED and doc is None, code_name
        assert code_name in capsys.readouterr().err
        assert not (tmp_path / f"refused_{n}.json").exists()


# ---- salary: unused salary is never a defect ------------------------------------ #


def test_an_inherited_salary_floor_never_blocks_a_redeploy_but_an_explicit_one_does(tmp_path):
    fixture = _pareto_fixture(tmp_path, other=E2_WITHOUT_X, min_salary=48500)  # rows sit near 36,000
    code, doc = _redeploy(tmp_path, fixture)
    assert code == swap.EXIT_OK
    assert X in doc["assignments_by_entry_id"]["E1"]  # the swap was taken under a floor it would have failed
    assert doc["construction"]["min_salary"] == 0
    code, doc = _redeploy(tmp_path, fixture, ["--min-salary", "48500"], out_name="explicit.json")
    assert code == swap.EXIT_OK
    assert doc["assignments_by_entry_id"] == {"E1": E1, "E2": E2_WITHOUT_X}  # the operator's own floor is honored
    assert doc["construction"]["pareto_redeploy"]["row_rejections"]["ILLEGAL"] > 0


def test_a_cheaper_player_with_a_bigger_prior_is_a_gain_and_leaves_salary_unused(tmp_path):
    fixture = _pareto_fixture(tmp_path, other=E2_WITHOUT_X, salaries={X: 1000})
    code, doc = _redeploy(tmp_path, fixture)
    assert code == swap.EXIT_OK
    rows = doc["lineups"]
    assert rows[0]["salary"] < 36200 and X in rows[0]["roster"]


# ---- Week 4, the committed inputs ------------------------------------------------- #


def test_week4_v4_redeploy_is_a_pareto_gain_that_moves_no_protected_person(tmp_path):
    construction = WEEK4 / "construction"
    protect = ("Braelon Allen", "Zach Ertz", "Jauan Jennings", "Emanuel Wilson")
    flags = [part for name in protect for part in ("--protect", name)]

    def argv(portfolio, out_path):
        return ["--portfolio", str(portfolio), "--scores", str(construction / "scores_qbclean.json"),
                "--salaries", str(WEEK4 / "DKSalaries.csv"), "--mode", "redeploy", *flags, "--out", str(out_path)]

    out = tmp_path / "v4_pareto.json"
    assert swap.main(argv(construction / "portfolio_final_v4.json", out)) == swap.EXIT_OK

    before_doc = json.loads((construction / "portfolio_final_v4.json").read_text(encoding="utf-8"))
    after_doc = json.loads(out.read_text(encoding="utf-8"))
    before, after = before_doc["assignments_by_entry_id"], after_doc["assignments_by_entry_id"]
    sal, scores = swap.load_salaries(WEEK4 / "DKSalaries.csv"), swap.load_scores(construction / "scores_qbclean.json")
    report = after_doc["construction"]["pareto_redeploy"]

    assert report["accepted"] and report["fixed_point"] is True
    assert [row["dk_id"] for row in report["protected"]] == sorted(
        i for i, row in sal.items() if row["Name"] in protect)
    assert all(row["rows_before"] == row["rows_after"] > 0 for row in report["protected"])
    for row in report["protected"]:  # and the report's own counts agree with the written file
        assert row["rows_after"] == sum(1 for roster in after.values() if row["dk_id"] in roster)
    for taken in report["accepted"]:  # every accepted swap raises its own row's prior
        assert scores[taken["in"]] > scores.get(taken["out"], 0.0)
        assert taken["prior_gain"] > 0
    b, a = _proxies_by_hand(list(before.values())), _proxies_by_hand(list(after.values()))
    assert a["max_exposure"] <= b["max_exposure"] and a["top3_union"] <= b["top3_union"]
    assert a["mean_overlap"] <= b["mean_overlap"] and a["distinct_people"] >= b["distinct_people"]
    assert sum(scores.get(i, 0.0) for r in after.values() for i in r) > sum(scores.get(i, 0.0) for r in before.values() for i in r)

    protected = {i for i, row in sal.items() if row["Name"] in protect}
    assert len(protected) == 4
    for dk_id in protected:  # no protected person moves
        assert [e for e, r in before.items() if dk_id in r] == [e for e, r in after.items() if dk_id in r]

    board = swap.Board(sal, 50000, 0)
    assert len({frozenset(r) for r in after.values()}) == len(after)  # R29
    assert all(board.is_legal(r) for r in after.values())
    for entry_id, roster in before.items():  # the QB, his stack, the bring-back and the DST stay
        assert set(board.core(roster)) <= set(after[entry_id])
        assert [i for i in roster if board.P(i) in ("QB", "DST")] == [i for i in after[entry_id] if board.P(i) in ("QB", "DST")]

    again = tmp_path / "v4_again.json"  # a rerun on its own output changes nothing
    assert swap.main(argv(out, again)) == swap.EXIT_OK
    rerun = json.loads(again.read_text(encoding="utf-8"))
    assert rerun["assignments_by_entry_id"] == after
    assert rerun["construction"]["pareto_redeploy"]["accepted"] == []
    assert qa.main(["--portfolio", str(out), "--salaries", str(WEEK4 / "DKSalaries.csv"),
                    "--max-exposure", "13", "--max-overlap", "5"]) == 0


def test_hitting_the_pass_bound_is_reported_and_a_rerun_continues(tmp_path, monkeypatch, capsys):
    """A rerun changes nothing only at a fixed point. One pass is not enough on Week 4 (the second takes a swap the
    first made available), so with the bound at one pass the report must say it stopped early, not that it finished."""

    construction = WEEK4 / "construction"

    def argv(portfolio, out_path):
        return ["--portfolio", str(portfolio), "--scores", str(construction / "scores_qbclean.json"),
                "--salaries", str(WEEK4 / "DKSalaries.csv"), "--mode", "redeploy", "--out", str(out_path)]

    monkeypatch.setattr(swap, "PARETO_MAX_PASSES", 1)
    first = tmp_path / "bounded.json"
    assert swap.main(argv(construction / "portfolio_final_v4.json", first)) == swap.EXIT_OK
    report = json.loads(first.read_text(encoding="utf-8"))["construction"]["pareto_redeploy"]
    assert report["fixed_point"] is False and report["passes"] == 1 and report["available_at_stop"] >= 1
    assert "PASS_BOUND_REACHED" in capsys.readouterr().out
    monkeypatch.undo()
    second = tmp_path / "continued.json"
    assert swap.main(argv(first, second)) == swap.EXIT_OK
    again = json.loads(second.read_text(encoding="utf-8"))["construction"]["pareto_redeploy"]
    assert again["fixed_point"] is True and again["accepted"]  # the rerun had work left, and finished it
