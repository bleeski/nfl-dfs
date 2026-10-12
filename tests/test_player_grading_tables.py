"""Session 70b: the tables by position and by salary tier, play rate by status, and the pooled report.

Synthetic bytes only, written with `write_bytes` so every platform hashes the same file. Session 70's fixture
(`tests/test_player_grading.py`) is reused for the report-level checks.
"""

from __future__ import annotations

import pytest

from nfl_dfs import player_grading as pg
from tests.test_player_grading import INFO, PRIORS, REALIZED, grade, person

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
