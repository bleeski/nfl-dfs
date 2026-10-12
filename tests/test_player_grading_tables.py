"""Session 70b: the tables by position and by salary tier, play rate by status, and the pooled report.

Synthetic bytes only, written with `write_bytes` so every platform hashes the same file. Session 70's fixture
(`tests/test_player_grading.py`) is reused for the report-level checks.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from nfl_dfs import cli
from nfl_dfs import player_grading as pg
from nfl_dfs.metric_registry import load_metric_registry
from tests.test_player_grading import INFO, PRIORS, REALIZED, grade, person, pool_scores_bytes, uid

# ----------------------------------------------------------------- the tables, by hand


def row(position, tier, prior, salary_points, realized):
    return {"position": position, "salary_tier": tier, "prior": prior, "salary_points": salary_points,
            "realized": realized}


# a, b, c are WRs (b and c tie on realized points); d and e RBs; f a lone QB; g a WR with no stat row; h a TE with none.
ROWS = [
    row("WR", "mid", 10.0, 6.0, 14.0),   # a
    row("WR", "low", 8.0, 12.0, 4.0),    # b
    row("WR", "low", 6.0, 9.0, 4.0),     # c
    row("RB", "mid", 12.0, 10.0, 20.0),  # d
    row("RB", "mid", 9.0, 11.0, 5.0),    # e
    row("QB", "high", 20.0, 18.0, 25.0),  # f
    row("WR", "low", 7.0, None, None),   # g
    row("TE", "high", 5.0, None, None),  # h
]


def test_tables_by_position_match_a_hand_computed_fixture():
    tables = pg.grade_tables(ROWS)
    wr = tables["by_position"]["WR"]
    # Prior: |10-14| + |8-4| + |6-4| = 10 over 3. Ranks: prior (3, 2, 1); realized (3, 1.5, 1.5), the tie averaged.
    # Deviations (1, 0, -1) and (1, -0.5, -0.5): sxy 1.5, sxx 2, syy 1.5, rho 1.5 / sqrt(3).
    assert wr["n"] == 3
    assert wr["prior"] == {"player_points_mae": pytest.approx(3.333333, abs=1e-6),
                           "spearman": pytest.approx(0.866025, abs=1e-6), "note": None}
    # Salary: |6-14| + |12-4| + |9-4| = 21 over 3. Ranks (1, 3, 2): deviations (-1, 1, 0), sxy -1.5, rho -1.5 / sqrt(3).
    assert wr["salary"] == {"player_points_mae": 7.0, "spearman": pytest.approx(-0.866025, abs=1e-6), "note": None}
    for position, n in (("RB", 2), ("QB", 1), ("TE", 0)):
        cell = tables["by_position"][position]
        assert cell["n"] == n
        for side in ("prior", "salary"):
            assert cell[side] == {"player_points_mae": None, "spearman": None, "note": "FEWER_THAN_3"}
    assert sorted(tables["by_position"]) == ["QB", "RB", "TE", "WR"]


def test_tables_by_tier_match_a_hand_computed_fixture():
    tables = pg.grade_tables(ROWS)
    mid = tables["by_tier"]["mid"]
    # a, d, e. Prior: |10-14| + |12-20| + |9-5| = 16 over 3; ranks (2, 3, 1) against (2, 3, 1): rho 1.
    # Salary: |6-14| + |10-20| + |11-5| = 24 over 3; ranks (1, 2, 3) against (2, 3, 1): sxy -1, sxx 2, syy 2, rho -0.5.
    assert mid["n"] == 3
    assert mid["prior"] == {"player_points_mae": pytest.approx(5.333333, abs=1e-6), "spearman": 1.0, "note": None}
    assert mid["salary"] == {"player_points_mae": 8.0, "spearman": -0.5, "note": None}
    assert tables["by_tier"]["low"]["n"] == 2 and tables["by_tier"]["high"]["n"] == 1
    assert tables["by_tier"]["low"]["prior"]["note"] == "FEWER_THAN_3"
    assert list(tables["by_tier"]) == ["low", "mid", "high"]
    usable = sum(1 for item in ROWS if item["realized"] is not None)
    assert sum(cell["n"] for cell in tables["by_position"].values()) == usable == 6
    assert sum(cell["n"] for cell in tables["by_tier"].values()) == usable


def test_a_zero_variance_cell_keeps_its_own_note():
    rows = [row("WR", "low", 5.0, 5.0, 3.0), row("WR", "low", 6.0, 5.0, 4.0), row("WR", "low", 7.0, 5.0, 8.0)]
    cell = pg.grade_tables(rows)["by_position"]["WR"]
    assert cell["prior"]["spearman"] == 1.0 and cell["prior"]["note"] is None
    # Salary: |5-3| + |5-4| + |5-8| = 6 over 3; every salary point equal, so no rank correlation.
    assert cell["salary"] == {"player_points_mae": 2.0, "spearman": None, "note": "ZERO_VARIANCE"}


# ----------------------------------------------------------------- the tier rule


def test_salary_tiers_split_evenly_without_ties():
    # n = 10, rank r takes floor(3 (r - 0.5) / 10): ranks 1-3 low, 4-7 mid, 8-10 high.
    salaries = [8000, 3000, 7000, 3200, 6000, 3500, 5000, 3700, 4500, 4000]
    assert pg.salary_tiers(salaries) == ["high", "low", "high", "low", "high", "low", "mid", "mid", "mid", "mid"]


def test_a_tied_block_straddling_a_boundary_keeps_one_tier():
    # Ranks 3 and 4 tie at 3500: both take 3.5, and 3 * 3 / 10 = 0.9 is low, so the low tier holds four.
    salaries = [3000, 3200, 3500, 3500, 4000, 4500, 5000, 6000, 7000, 8000]
    tiers = pg.salary_tiers(salaries)
    assert tiers == ["low"] * 4 + ["mid"] * 3 + ["high"] * 3


def test_a_large_tied_block_can_leave_a_tier_empty():
    # Seven tie at the bottom with mid-rank 4: 3 * 3.5 / 10 = 1.05, so all seven are mid and low is empty.
    salaries = [2500] * 7 + [3000, 4000, 5000]
    assert pg.salary_tiers(salaries) == ["mid"] * 7 + ["high"] * 3
    assert pg.salary_tiers([5000]) == ["mid"] and pg.salary_tiers([4000, 5000]) == ["low", "high"]
    assert pg.salary_tiers([]) == []
    block = pg.tier_bounds(salaries, pg.salary_tiers(salaries))
    assert block["low"] == {"people": 0, "salary_min": None, "salary_max": None}
    assert block["mid"] == {"people": 7, "salary_min": 2500, "salary_max": 2500}
    assert block["high"] == {"people": 3, "salary_min": 3000, "salary_max": 5000}
    empty = pg.grade_tables([row("WR", "mid", 5.0, 5.0, 3.0)])["by_tier"]["low"]
    assert empty["n"] == 0 and empty["prior"]["note"] == "FEWER_THAN_3"


# ----------------------------------------------------------------- play rate


def entry(status, *, position="WR", bound=True, played=False):
    return {"position": position, "dk_status": status, "provider_player_id": "00-1" if bound else None,
            "game_id": "2026_04_ATL_NO" if played else None}


def test_play_rate_by_status():
    people = [
        entry("", played=True), entry(""), entry("", bound=False),
        entry("Q", played=True), entry("Q"),
        entry("OUT"), entry("out"),
        entry("GTD", played=True),
        entry("", position="DST", played=True), entry("Q", position="DST"),
        entry("IR", bound=False),
    ]
    rate = pg.play_rate(people)
    assert rate["by_status"] == {
        "(blank)": {"class": "AVAILABLE", "people": 2, "played": 1, "rate": 0.5, "unbound": 1},
        "GTD": {"class": "UNRECOGNIZED", "people": 1, "played": 1, "rate": 1.0, "unbound": 0},
        "IR": {"class": "UNAVAILABLE", "people": 0, "played": 0, "rate": None, "unbound": 1},
        "OUT": {"class": "UNAVAILABLE", "people": 1, "played": 0, "rate": 0.0, "unbound": 0},
        "Q": {"class": "DEGRADED", "people": 2, "played": 1, "rate": 0.5, "unbound": 0},
        "out": {"class": "UNAVAILABLE", "people": 1, "played": 0, "rate": 0.0, "unbound": 0},
    }
    assert "undercount" in rate["played_means"] and "participation_brier" in rate["played_means"]
    assert "non-DST" in rate["population"]


# ----------------------------------------------------------------- the report


def test_the_report_carries_the_tables_and_play_rate(tmp_path):
    report = grade(tmp_path)
    assert report["schema_version"] == "nfl_player_grading_v1" and pg.REPORT_NAME == "player_grading.w1.json"
    found = report["grade"]
    # Twelve graded non-DST people in six tied salary pairs: mid-ranks 1.5 to 11.5 over n = 12 give 4 / 4 / 4.
    assert found["tiers"]["low"] == {"people": 4, "salary_min": 3000, "salary_max": 4000}
    assert found["tiers"]["mid"] == {"people": 4, "salary_min": 5000, "salary_max": 6000}
    assert found["tiers"]["high"] == {"people": 4, "salary_min": 10000, "salary_max": 11000}
    assert person(report, "kc_k")["salary_tier"] == "low" and person(report, "den_wr2")["salary_tier"] == "mid"
    assert person(report, "kc_qb")["salary_tier"] == "high" and person(report, "kc_dst")["salary_tier"] is None
    usable = found["usable_people"]
    assert usable == 10
    assert sum(cell["n"] for cell in found["by_position"].values()) == usable
    assert sum(cell["n"] for cell in found["by_tier"].values()) == usable
    assert {key: cell["n"] for key, cell in found["by_position"].items()} == {"K": 2, "QB": 2, "RB": 2, "TE": 2, "WR": 2}
    # The high tier holds both QBs and both WR1s; the salary side uses the slate's one scale.
    high = ["kc_qb", "kc_wr1", "den_qb", "den_wr1"]
    scale = sum(PRIORS[k] for k in REALIZED) / sum(INFO[k][3] for k in REALIZED)
    prior_mae = sum(abs(PRIORS[k] - REALIZED[k] / 100) for k in high) / 4
    salary_mae = sum(abs(INFO[k][3] * scale - REALIZED[k] / 100) for k in high) / 4
    cell = found["by_tier"]["high"]
    assert cell["n"] == 4 and cell["prior"]["player_points_mae"] == pytest.approx(prior_mae, abs=1e-6) == 6.775
    assert cell["salary"]["player_points_mae"] == pytest.approx(salary_mae, abs=1e-6)
    assert found["by_tier"]["mid"]["n"] == 2 and found["by_tier"]["mid"]["prior"]["note"] == "FEWER_THAN_3"
    # den_wr2 is unbound; kc_wr2 has no stat row; den_te is Q and played.
    assert found["play_rate"]["by_status"] == {
        "(blank)": {"class": "AVAILABLE", "people": 10, "played": 9, "rate": 0.9, "unbound": 1},
        "Q": {"class": "DEGRADED", "people": 1, "played": 1, "rate": 1.0, "unbound": 0},
    }


def test_play_rate_counts_people_the_prior_did_not_grade(tmp_path):
    # kc_wr2 leaves the prior's people: ungraded, so out of every table, but still a bound blank-status person.
    by_person = {uid(k): v for k, v in PRIORS.items() if k != "kc_wr2"}
    report = grade(tmp_path, pool_scores=pool_scores_bytes(by_person=by_person))
    assert report["grade"]["graded_people"] == 13 and person(report, "kc_wr2")["salary_tier"] is None
    assert report["grade"]["play_rate"]["by_status"]["(blank)"]["people"] == 10


# ----------------------------------------------------------------- the pool


def second_slate(report: dict, *, week=3, salary="b" * 64, games=None, mode=None) -> dict:
    """Another slate: its own salary bytes, week and nflverse games."""

    other = copy.deepcopy(report)
    other["inputs"]["salaries"]["sha256"] = salary
    other["slate"]["week"] = week
    other["slate"]["games"] = games if games is not None else {"DEN@KC 09/27/2026 08:20PM ET": f"2026_{week:02d}_DEN_KC"}
    if mode is not None:
        other["slate"]["mode"] = mode
    return other


def write_reports(tmp_path: Path, *reports) -> list[Path]:
    paths = []
    for n, report in enumerate(reports, start=1):
        path = tmp_path / f"report{n}.json"
        path.write_bytes(report if isinstance(report, bytes) else pg.render(report))
        paths.append(path)
    return paths


def pool_refused(paths) -> str:
    with pytest.raises(pg.PlayerGradingRefused) as caught:
        pg.pool_reports(paths)
    assert caught.value.code == "PLAYER_GRADING_INPUT_INVALID", caught.value
    return caught.value.detail


def test_the_pool_macro_averages_with_the_slate_as_the_unit(tmp_path):
    first = grade(tmp_path)
    second = second_slate(first)
    first["grade"]["prior"]["player_points_mae"]["value"] = 4.0
    second["grade"]["prior"]["player_points_mae"].update(value=6.0, n=200)
    second["grade"]["usable_people"] = 200
    second["grade"]["by_tier"]["high"]["prior"]["player_points_mae"] = 7.775
    pool = pg.pool_reports(write_reports(tmp_path, second, first))
    # Unweighted: (4 + 6) / 2 = 5, though the second slate has 20 times the people (people-weighted: 5.9).
    assert pool["overall"]["prior"]["player_points_mae"] == {"value": 5.0, "slates": 2, "people": 210,
                                                             "values": [4.0, 6.0]}
    assert pool["by_tier"]["high"]["prior"]["player_points_mae"] == {"value": 7.275, "slates": 2, "people": 8,
                                                                     "values": [6.775, 7.775]}
    sample = pool["sample"]
    assert sample["slates"] == 2 and sample["kish_ess"] == 2.0 and sample["independent_slates"] == 2
    assert sample["usable_people_by_slate"] == [10, 200] and sample["usable_people"] == 210
    assert (sample["registered_minimum_sample"], sample["meets_minimum_sample"]) == (500, False)
    for report in (first, second):  # exactly the registered 500
        report["grade"]["usable_people"] = report["grade"]["prior"]["player_points_mae"]["n"] = 250
    assert pg.pool_reports(write_reports(tmp_path, first, second))["sample"]["meets_minimum_sample"] is True
    assert [slate["week"] for slate in pool["slates"]] == [2, 3]
    assert pool["schema_version"] == "nfl_player_grading_pool_v1" and pool["model_status"] == "PRIOR_ONLY"
    assert pool["play_rate"]["Q"] == {"class": "DEGRADED", "rate": {"value": 1.0, "slates": 2, "people": 2,
                                                                     "values": [1.0, 1.0]},
                                      "people": 2, "played": 2, "unbound": 0}


def test_a_cell_missing_from_one_slate_averages_over_the_others(tmp_path):
    first = grade(tmp_path)
    second = second_slate(first)
    first["grade"]["by_position"]["WR"].update(n=3, prior={"player_points_mae": 2.0, "spearman": 0.5, "note": None})
    del second["grade"]["by_position"]["WR"]
    second["grade"]["by_tier"]["high"]["prior"].update(spearman=None, note="ZERO_VARIANCE")
    pool = pg.pool_reports(write_reports(tmp_path, first, second))
    assert pool["by_position"]["WR"]["prior"]["player_points_mae"] == {"value": 2.0, "slates": 1, "people": 3,
                                                                       "values": [2.0, None]}
    assert pool["by_position"]["K"]["prior"]["spearman"] == {"value": None, "slates": 0, "people": 0,
                                                             "values": [None, None]}
    high = pool["by_tier"]["high"]["prior"]
    assert (high["player_points_mae"]["slates"], high["spearman"]["slates"]) == (2, 1)


def test_shared_games_are_declared_not_refused(tmp_path):
    first = grade(tmp_path)
    game = next(iter(first["slate"]["games"].values()))
    classic = second_slate(first, week=2, mode="CLASSIC", games={"A": game, "B": "2026_02_X_Y"})
    later = second_slate(first, salary="c" * 64)
    pool = pg.pool_reports(write_reports(tmp_path, first, classic, later))
    assert pool["independence"]["shared_games"] == {game: [1, 2]}
    assert pool["sample"]["independent_slates"] == 2 and pool["sample"]["slates"] == 3
    # Two slates sharing two games are one independent slate, not none.
    one = second_slate(first, week=6, salary="d" * 64, games={"A": "g1", "B": "g2"})
    other = second_slate(first, week=6, mode="CLASSIC", salary="e" * 64, games={"A": "g1", "B": "g2", "C": "g3"})
    pool = pg.pool_reports(write_reports(tmp_path, one, other))
    assert pool["independence"]["shared_games"] == {"g1": [1, 2], "g2": [1, 2]}
    assert pool["sample"]["independent_slates"] == 1


def damaged(report: dict, change) -> dict:
    other = second_slate(report)
    change(other)
    return other


@pytest.mark.parametrize("name, build, detail", [
    ("graded before the tables", lambda r: damaged(r, lambda o: o["grade"].pop("by_tier")),
     "pool_report:2:SHAPE:grade.by_tier"),
    ("another schema", lambda r: damaged(r, lambda o: o.update(schema_version="nfl_player_grading_v9")),
     "pool_report:2:SCHEMA:'nfl_player_grading_v9'"),
    ("not JSON", lambda r: b"{not json", "pool_report:2:UNREADABLE"),
    ("not an object", lambda r: b"[1]", "pool_report:2:NOT_AN_OBJECT"),
    ("a bool value", lambda r: damaged(r, lambda o: o["grade"]["prior"]["player_points_mae"].update(value=True)),
     "pool_report:2:SHAPE:grade.prior.player_points_mae.value"),
    ("a text count", lambda r: damaged(r, lambda o: o["grade"]["by_tier"]["low"].update(n="4")),
     "pool_report:2:SHAPE:grade.by_tier.low.n"),
    ("an infinite value", lambda r: damaged(r, lambda o: o["grade"]["by_tier"]["low"]["prior"].update(
        player_points_mae=float("inf"))), "pool_report:2:SHAPE:grade.by_tier.low.prior.player_points_mae"),
    ("a play rate count", lambda r: damaged(r, lambda o: o["grade"]["play_rate"]["by_status"]["Q"].update(
        played=-1)), "pool_report:2:SHAPE:grade.play_rate.by_status.Q.played"),
    ("games not an object", lambda r: damaged(r, lambda o: o["slate"].update(games=["2026_03_DEN_KC"])),
     "pool_report:2:SHAPE:slate.games"),
    ("a status class not text", lambda r: damaged(r, lambda o: o["grade"]["play_rate"]["by_status"]["Q"].update(
        **{"class": 1})), "pool_report:2:SHAPE:grade.play_rate.by_status.Q.class"),
    ("another status's class", lambda r: damaged(r, lambda o: o["grade"]["play_rate"]["by_status"]["Q"].update(
        **{"class": "AVAILABLE"})), "pool_report:2:SHAPE:grade.play_rate.by_status.Q.class"),
    ("more played than people", lambda r: damaged(r, lambda o: o["grade"]["play_rate"]["by_status"]["Q"].update(
        played=2)), "pool_report:2:SHAPE:grade.play_rate.by_status.Q.played"),
    ("a rate past 1", lambda r: damaged(r, lambda o: o["grade"]["play_rate"]["by_status"]["Q"].update(rate=3.0)),
     "pool_report:2:SHAPE:grade.play_rate.by_status.Q.rate"),
    ("a negative error", lambda r: damaged(r, lambda o: o["grade"]["by_tier"]["low"]["salary"].update(
        player_points_mae=-0.5)), "pool_report:2:SHAPE:grade.by_tier.low.salary.player_points_mae"),
    ("a correlation past 1", lambda r: damaged(r, lambda o: o["grade"]["by_tier"]["low"]["prior"].update(
        spearman=5.0)), "pool_report:2:SHAPE:grade.by_tier.low.prior.spearman"),
    ("a value past the float range", lambda r: damaged(
        r, lambda o: o["grade"]["prior"]["player_points_mae"].update(value=10 ** 400)),
     "pool_report:2:SHAPE:grade.prior.player_points_mae.value"),
    ("a usable count its cells disagree with", lambda r: damaged(r, lambda o: o["grade"].update(
        usable_people=10 ** 6)), "pool_report:2:SHAPE:grade.usable_people"),
    ("a game id not text", lambda r: damaged(r, lambda o: o["slate"].update(games={"A": 7})),
     "pool_report:2:SHAPE:slate.games"),
    ("one game twice", lambda r: damaged(r, lambda o: o["slate"].update(games={"A": "g1", "B": "g1"})),
     "pool_report:2:SHAPE:slate.games"),
    ("nested too deep", lambda r: b"[" * 100000 + b"]" * 100000, "pool_report:2:UNREADABLE:RecursionError"),
    ("a number too long to read", lambda r: b'{"a": ' + b"9" * 5000 + b"}", "pool_report:2:UNREADABLE:ValueError"),
    ("the same salary bytes", lambda r: second_slate(r, salary=r["inputs"]["salaries"]["sha256"]),
     "pool_report:2:REPEATED_SLATE:1"),
    ("a re-export of the same games", lambda r: second_slate(r, week=r["slate"]["week"], games=r["slate"]["games"]),
     "pool_report:2:REPEATED_SLATE:1"),
])
def test_each_pool_refusal(tmp_path, name, build, detail):
    first = grade(tmp_path)
    assert pool_refused(write_reports(tmp_path, first, build(first))).startswith(detail), name


def test_a_re_export_with_its_games_in_another_order_is_the_same_slate(tmp_path):
    first = grade(tmp_path)
    one = second_slate(first, week=6, salary="d" * 64, games={"A": "g1", "B": "g2"})
    other = second_slate(first, week=6, salary="e" * 64, games={"B": "g2", "A": "g1"})
    # Written without sorted keys, so its games really are in the other order.
    reordered = json.dumps(other).encode("utf-8")
    assert pool_refused(write_reports(tmp_path, one, reordered)) == "pool_report:2:REPEATED_SLATE:1"


def test_too_few_or_unreadable_reports_refuse(tmp_path):
    first = grade(tmp_path)
    assert pool_refused(write_reports(tmp_path, first)) == "pool:FEWER_THAN_2_REPORTS"
    missing = pool_refused([write_reports(tmp_path, first)[0], tmp_path / "absent.json"])
    assert missing.startswith("pool_report:2:UNREADABLE")


def test_the_pool_is_byte_identical_and_order_free(tmp_path):
    first = grade(tmp_path)
    # A third slate in the same week as the first: only the salary SHA-256 orders the two.
    same_week = second_slate(first, week=2, salary="0" * 64, games={"X": "2026_02_X_Y"})
    paths = write_reports(tmp_path, first, second_slate(first), same_week)
    data = pg.render(pg.pool_reports(paths))
    assert data == pg.render(pg.pool_reports(list(reversed(paths)))) == pg.render(pg.pool_reports(paths))
    assert data.endswith(b"}\n") and b"\r" not in data
    text = data.decode("utf-8").lower()
    for word in ("calibrated", "win_probability", "\"ev\"", "roi"):
        assert word not in text


def test_one_changed_report_byte_changes_the_pool_or_refuses(tmp_path):
    first = grade(tmp_path)
    paths = write_reports(tmp_path, first, second_slate(first))
    before = pg.render(pg.pool_reports(paths))
    raw = paths[0].read_bytes()
    paths[0].write_bytes(raw[:-1] + b" \n")  # still the same JSON, but other bytes
    assert pg.render(pg.pool_reports(paths)) != before
    paths[0].write_bytes(raw.replace(b"6.775", b"6.776", 1))
    assert pg.pool_reports(paths)["by_tier"]["high"]["prior"]["player_points_mae"]["values"][0] == 6.776
    paths[0].write_bytes(b"[" + raw[1:])
    assert pool_refused(paths).startswith("pool_report:1:UNREADABLE")


def test_the_registered_constants_agree_with_the_registry():
    registry = load_metric_registry(Path(__file__).resolve().parents[1] / "config" / "metric_registry_q1_v1.json")
    metric = next(m for m in registry.metrics if m["metric_id"] == "player_points_mae")
    assert pg.REGISTERED_MINIMUM_SAMPLE == metric["minimum_sample"]
    assert metric["uncertainty_interval"] in pg.POOL_NOT_COMPUTED["bootstrap_interval"]


# ----------------------------------------------------------------- the command


def pool_cli(capsys, argv) -> tuple[int, dict]:
    code = cli.main(argv)
    return code, json.loads(capsys.readouterr().out)


def test_the_pool_command_writes_one_file(tmp_path, capsys):
    first = grade(tmp_path)
    paths = [str(p) for p in write_reports(tmp_path, first, second_slate(first))]
    code, summary = pool_cli(capsys, ["grade-players", "--pool", *paths, "--out", str(tmp_path / "pools" / "p.json")])
    assert (code, summary["status"], summary["model_status"]) == (0, "COMPLETE", "PRIOR_ONLY")
    written = (tmp_path / "pools" / "p.json").read_bytes()
    assert hashlib.sha256(written).hexdigest() == summary["pool_sha256"]
    assert written == pg.render(pg.pool_reports([Path(p) for p in paths]))
    assert (summary["slates"], summary["usable_people"]) == (2, 20)
    code, summary = pool_cli(capsys, ["grade-players", "--pool", *paths, "--out", str(tmp_path / "pools" / "p.json")])
    assert (code, summary["code"]) == (2, "PLAYER_GRADING_OUTPUT_EXISTS")
    assert (tmp_path / "pools" / "p.json").read_bytes() == written
    # --pool given twice keeps every report.
    code, summary = pool_cli(capsys, ["grade-players", "--pool", paths[0], "--pool", paths[1], "--out",
                                      str(tmp_path / "pools" / "q.json")])
    assert (code, summary["slates"]) == (0, 2) and (tmp_path / "pools" / "q.json").read_bytes() == written


def test_a_pool_refusal_never_prints_release_truths(tmp_path, capsys):
    first = grade(tmp_path)
    paths = [str(p) for p in write_reports(tmp_path, first)]
    code, summary = pool_cli(capsys, ["grade-players", "--pool", *paths, "--out", str(tmp_path / "p.json")])
    assert (code, summary["status"], summary["code"]) == (2, "REFUSED", "PLAYER_GRADING_INPUT_INVALID")
    assert "RELEASE_DECISION" not in json.dumps(summary) and not (tmp_path / "p.json").exists()


@pytest.mark.parametrize("argv, message", [
    (["--pool", "a.json", "b.json", "--salaries", "s.csv", "--out", "p.json"], "--pool takes only --out"),
    (["--pool", "a.json", "b.json"], "the following arguments are required: --out"),
    (["--pool-scores", "p.json", "--identity-review", "i.csv", "--stats-package", "pkg", "--season", "2026",
      "--week", "2", "--out", "o"], "the following arguments are required: --salaries"),
    ([], "the following arguments are required: --salaries, --pool-scores, --identity-review, --stats-package, "
         "--season, --week, --out"),
])
def test_usage_errors_stay_argparse_errors(capsys, argv, message):
    with pytest.raises(SystemExit) as caught:
        cli.main(["grade-players", *argv])
    captured = capsys.readouterr()
    assert caught.value.code == 2 and message in captured.err
    assert "RELEASE_DECISION" not in captured.out + captured.err
