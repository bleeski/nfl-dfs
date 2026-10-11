"""Session 70: realized player points, the join, the reconciliation and the per-slate grade.

Synthetic bytes only, written with `write_bytes` so every platform hashes the same file.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from nfl_dfs import cli
from nfl_dfs import player_grading as pg
from nfl_dfs import priors
from nfl_dfs.contracts import SourceArtifact
from nfl_dfs.entry_history import ENTRIES_VERSION
from nfl_dfs.gate_registry import load_gate_registry
from nfl_dfs.scoring import KickerStatLine, OffensiveStatLine, score_kicker, score_offense

GAME = "DEN@KC 09/20/2026 08:20PM ET"
GAME_ID = "2026_02_DEN_KC"
SEASON, WEEK = 2026, 2
PEOPLE = [  # key, name, position, team, FLEX salary
    ("kc_qb", "KC QB", "QB", "KC", 11000), ("kc_rb", "KC RB", "RB", "KC", 5000),
    ("kc_wr1", "KC WR1", "WR", "KC", 10000), ("kc_wr2", "KC WR2", "WR", "KC", 6000),
    ("kc_te", "KC TE", "TE", "KC", 4000), ("kc_k", "KC K", "K", "KC", 3000),
    ("kc_dst", "Chiefs", "DST", "KC", 3000),
    ("den_qb", "DEN QB", "QB", "DEN", 11000), ("den_rb", "DEN RB", "RB", "DEN", 5000),
    ("den_wr1", "DEN WR1", "WR", "DEN", 10000), ("den_wr2", "DEN WR2", "WR", "DEN", 6000),
    ("den_te", "DEN TE", "TE", "DEN", 4000), ("den_k", "DEN K", "K", "DEN", 3000),
    ("den_dst", "Broncos", "DST", "DEN", 3000),
]
INFO = {key: (name, pos, team, salary) for key, name, pos, team, salary in PEOPLE}
FLEX = {key: str(3000 + n) for n, (key, *_rest) in enumerate(PEOPLE)}
CPT = {key: str(4000 + n) for n, (key, *_rest) in enumerate(PEOPLE)}
GSIS = {key: f"00-00000{n:02d}" for n, (key, *_rest) in enumerate(PEOPLE)}
PRIORS = {"kc_qb": 20.0, "kc_rb": 12.0, "kc_wr1": 15.5, "kc_wr2": 8.0, "kc_te": 6.0, "kc_k": 7.0, "kc_dst": 6.5,
          "den_qb": 18.0, "den_rb": 14.0, "den_wr1": 11.0, "den_wr2": 7.5, "den_te": 5.0, "den_k": 6.0,
          "den_dst": 6.0}
# Realized hundredths by hand from DraftKings' rules (the tests also check them against scoring.py).
REALIZED = {"kc_qb": 2460, "kc_rb": 1390, "kc_wr1": 3340, "kc_te": 770, "kc_k": 1800, "den_qb": 2200,
            "den_rb": 3010, "den_wr1": 1160, "den_te": 190, "den_k": 500}
STATS = {
    "kc_qb": dict(passing_yards=310, passing_tds=2, passing_interceptions=1, rushing_yards=12,
                  fumbles_lost_total=1, sack_fumbles_lost=1, passing_2pt_conversions=1),
    "kc_rb": dict(rushing_yards=48, rushing_tds=1, receptions=2, receiving_yards=11),
    "kc_wr1": dict(receptions=7, receiving_yards=104, receiving_tds=1, special_teams_tds=1,
                   receiving_2pt_conversions=1, fumbles_lost_total=1),
    "kc_te": dict(receptions=4, receiving_yards=37),
    "kc_k": dict(pat_made=3, fg_made_20_29=1, fg_made_30_39=1, fg_made_40_49=1, fg_made_50_59=1),
    "den_qb": dict(passing_yards=250, passing_tds=1, rushing_yards=20, rushing_tds=1),
    "den_rb": dict(rushing_yards=101, rushing_tds=1, receptions=3, receiving_yards=20, fumble_recovery_tds=1),
    "den_wr1": dict(receptions=5, receiving_yards=66),
    "den_te": dict(receptions=1, receiving_yards=9),
    "den_k": dict(pat_made=2, fg_made_0_19=1),
}
ID_COLUMNS = ["player_id", "player_display_name", "position", "season", "week", "season_type", "game_id", "team",
              "attempts", "carries", "targets"]
OFFENSE = ["passing_yards", "passing_tds", "passing_interceptions", "rushing_yards", "rushing_tds",
           "receiving_yards", "receiving_tds", "receptions", "special_teams_tds", "fumbles_lost_total",
           "sack_fumbles_lost", "rushing_fumbles_lost", "receiving_fumbles_lost", "passing_2pt_conversions",
           "rushing_2pt_conversions", "receiving_2pt_conversions", "fumble_recovery_tds"]
KICKER = ["pat_made", "fg_made_0_19", "fg_made_20_29", "fg_made_30_39", "fg_made_40_49", "fg_made_50_59",
          "fg_made_60_"]


def stats_bytes(*, drop=(), cells=None, extra_rows=(), week_rows=True, game_for=None, teams=("KC", "DEN")) -> bytes:
    """The nflverse weekly file: one week-2 row per STATS person, a week-1 row, and a decoy named DEN WR2."""

    header = [c for c in ID_COLUMNS + OFFENSE + KICKER if c not in drop]
    rows = []
    if week_rows:
        for key, values in STATS.items():
            name, pos, team, _ = INFO[key]
            if team not in teams:
                continue
            base = dict(player_id=GSIS[key], player_display_name=name, position=pos, season=SEASON, week=WEEK,
                        season_type="REG", game_id=(game_for or {}).get(team, GAME_ID), team=team)
            rows.append({**base, **values, **(cells or {}).get(key, {})})
        rows.append(dict(player_id="00-0000099", player_display_name="DEN WR2", position="WR", season=SEASON,
                         week=WEEK, season_type="REG", game_id=GAME_ID, team="DEN", receptions=9,
                         receiving_yards=150))
    rows.append(dict(player_id=GSIS["kc_qb"], player_display_name="KC QB", position="QB", season=SEASON, week=1,
                     season_type="REG", game_id="2026_01_KC_LV", team="KC", passing_yards=999))
    rows.extend(extra_rows)
    lines = [",".join(header)] + [",".join(str(row.get(c, 0)) for c in header) for row in rows]
    return ("\n".join(lines) + "\n").encode("utf-8")


def salary_bytes(appg: str = "0") -> bytes:
    lines = ["Position,Name + ID,Name,ID,Roster Position,Salary,Game Info,TeamAbbrev,AvgPointsPerGame,Status"]
    for key, name, pos, team, salary in PEOPLE:
        for role, table, price in (("CPT", CPT, salary * 3 // 2), ("FLEX", FLEX, salary)):
            status = "Q" if key == "den_te" else ""
            lines.append(f"{pos},{name} ({table[key]}),{name},{table[key]},{role},{price},{GAME},{team},{appg},{status}")
    return ("\n".join(lines) + "\n").encode("utf-8")


def uid(key: str) -> str:
    name, pos, team, _ = INFO[key]
    return f"{team}|{pos}|{name}"


def pool_scores_bytes(**changes) -> bytes:
    payload = {
        "schema_version": "nfl_prior_pool_scores_v1", "score_version": "prior_points_of_expected_statline_v3",
        "status": "DIAGNOSTIC_NOT_AN_UPLOAD_AUTHORIZATION",
        "by_dk_id": {**{FLEX[k]: v for k, v in PRIORS.items()}, **{CPT[k]: v * 1.5 for k, v in PRIORS.items()}},
        "by_person": {uid(k): v for k, v in PRIORS.items()},
        "excluded_dk_ids": [FLEX["den_k"], CPT["den_k"]], "omissions": [], "threshold_sensitive": [],
    }
    payload.update(changes)
    return json.dumps(payload, indent=2).encode("utf-8")


def identity_bytes(*, alter=None) -> bytes:
    lines = [",".join(priors.REVIEW_COLUMNS)]
    for key, name, pos, team, _salary in PEOPLE:
        provider, method = (team, "TEAM_DEFENSE_NICKNAME") if pos == "DST" else (GSIS[key], "NORMALIZED_NAME_TEAM_POSITION")
        if key == "den_wr2":
            provider, method = "", "UNMATCHED"
        row = dict(DK_ID=FLEX[key], DK_NAME=name, DK_TEAM=team, DK_POSITION=pos, PROPOSED_PROVIDER_PLAYER_ID=provider,
                   PROPOSED_PROVIDER_NAME=name if provider else "", PROPOSED_PROVIDER_TEAM=team if provider else "",
                   PROPOSED_PROVIDER_STATUS="ACT" if provider else "", MATCH_METHOD=method, DECISION="ACCEPT",
                   REVIEWED_PROVIDER_PLAYER_ID="")
        row.update((alter or {}).get(key, {}))
        lines.append(",".join(row[c] for c in priors.REVIEW_COLUMNS))
    return ("\n".join(lines) + "\n").encode("utf-8")


def entry_id(n: int) -> str:
    return f"48800{n:05d}"


# Captain first. Hundredths DraftKings would show for each: L0 all covered and equal; L1 a 2-hundredth gap; L2, L3
# and L4 hold one uncovered DST (FLEX, CPT, FLEX), each implying the Chiefs scored 7.00.
LINEUPS = [
    (["kc_qb", "kc_rb", "kc_wr1", "kc_te", "den_rb", "den_wr1"], 13360),
    (["den_rb", "den_qb", "kc_qb", "kc_k", "den_te", "kc_te"], 11937),
    (["kc_wr1", "kc_dst", "kc_qb", "den_rb", "den_te", "den_k"], 11870),
    (["kc_dst", "kc_qb", "kc_rb", "den_rb", "den_wr1", "kc_te"], 9840),
    (["kc_qb", "kc_dst", "den_qb", "den_rb", "kc_rb", "den_k"], 11490),
]


def lineup_bytes(lineups=LINEUPS) -> bytes:
    lines = ["Entry ID,Contest Name,Contest ID,Entry Fee,CPT,FLEX,FLEX,FLEX,FLEX,FLEX,,Instructions"]
    for n, (keys, _points) in enumerate(lineups):
        cells = [CPT[keys[0]], *(FLEX[k] for k in keys[1:])]
        lines.append(f"{entry_id(n)},Showdown,9001,$5,{','.join(cells)},,")
    return ("\n".join(lines) + "\n").encode("utf-8")


def entries_bytes(points=None, *, contest="9001", drop=(), schema=ENTRIES_VERSION) -> bytes:
    entries = [{"entry_key": entry_id(n), "contest_key": contest, "points_hundredths": (points or {}).get(n, p)}
               for n, (_keys, p) in enumerate(LINEUPS) if n not in drop]
    return json.dumps({"schema_version": schema, "entries": entries}).encode("utf-8")


STATS_ENTRY_URL = "https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_2026.csv"


def stats_entry(raw: bytes) -> dict:
    digest = hashlib.sha256(raw).hexdigest()
    return {"name": "player_stats_current", "sha256": digest, "relative_path": f"raw/{digest}.csv",
            "source_uri": STATS_ENTRY_URL, "observed_at": "2026-09-22T12:00:00+00:00",
            "parser_version": "nflverse_stats_player_week_csv_v1"}


def write_inputs(tmp_path: Path, **override) -> dict:
    files = {"salaries": salary_bytes(), "pool_scores": pool_scores_bytes(), "identity_review": identity_bytes(),
             "lineups": lineup_bytes(), "entries": entries_bytes()}
    files.update(override)
    paths = {}
    for name, data in files.items():
        if data is None:
            paths[name] = None
            continue
        path = tmp_path / f"{name}.bin"
        path.write_bytes(data)
        paths[name] = path
    return paths


def grade(tmp_path: Path, stats: bytes | None = None, **override) -> dict:
    raw = stats if stats is not None else stats_bytes()
    return pg.grade_slate(stats_raw=raw, stats_entry=stats_entry(raw), season=SEASON, week=WEEK,
                          **write_inputs(tmp_path, **override))


def person(report: dict, key: str) -> dict:
    return next(p for p in report["people"] if p["underlying_id"] == uid(key))


def kinds(entry: dict) -> set[str]:
    return {gap["kind"] for gap in entry["gaps"]}


def refused(tmp_path: Path, code: str, **kwargs) -> str:
    with pytest.raises(pg.PlayerGradingRefused) as caught:
        grade(tmp_path, **kwargs)
    assert caught.value.code == code, caught.value
    return caught.value.detail


# ----------------------------------------------------------------- realized points


@pytest.mark.parametrize("key", ["kc_qb", "kc_rb", "kc_wr1", "kc_te", "den_qb", "den_rb", "den_wr1", "den_te"])
def test_offense_points_are_scoring_py_on_the_mapped_line(tmp_path, key):
    entry = person(grade(tmp_path), key)
    values = {c: STATS[key].get(c, 0) for c in OFFENSE}
    expected = score_offense(OffensiveStatLine(
        passing_yards=values["passing_yards"], passing_tds=values["passing_tds"],
        interceptions=values["passing_interceptions"], rushing_yards=values["rushing_yards"],
        rushing_tds=values["rushing_tds"], receiving_yards=values["receiving_yards"],
        receiving_tds=values["receiving_tds"], receptions=values["receptions"],
        return_tds=values["special_teams_tds"], fumbles_lost=values["fumbles_lost_total"],
        two_point_conversions=values["passing_2pt_conversions"] + values["rushing_2pt_conversions"]
        + values["receiving_2pt_conversions"],
        offensive_fumble_recovery_tds=values["fumble_recovery_tds"]))
    assert entry["realized_hundredths"] == round(expected * 100) == REALIZED[key]
    assert entry["gaps"] == []


@pytest.mark.parametrize("key", ["kc_k", "den_k"])
def test_kicker_points_are_score_kicker_on_the_binned_line(tmp_path, key):
    v = {c: STATS[key].get(c, 0) for c in KICKER}
    expected = score_kicker(KickerStatLine(
        extra_points=v["pat_made"], field_goals_0_39=v["fg_made_0_19"] + v["fg_made_20_29"] + v["fg_made_30_39"],
        field_goals_40_49=v["fg_made_40_49"], field_goals_50_plus=v["fg_made_50_59"] + v["fg_made_60_"]))
    assert person(grade(tmp_path), key)["realized_hundredths"] == round(expected * 100) == REALIZED[key]


def test_each_column_feeds_its_own_field():
    offense = {c: str(n + 1) for n, c in enumerate(OFFENSE)}
    line, gaps = pg.stat_line(offense, frozenset(offense), "WR")
    assert gaps == []
    assert line == OffensiveStatLine(
        passing_yards=1, passing_tds=2, interceptions=3, rushing_yards=4, rushing_tds=5, receiving_yards=6,
        receiving_tds=7, receptions=8, return_tds=9, fumbles_lost=10, two_point_conversions=14 + 15 + 16,
        offensive_fumble_recovery_tds=17)
    kicker = {c: str(n + 1) for n, c in enumerate(KICKER)}
    line, gaps = pg.stat_line(kicker, frozenset(kicker), "K")
    assert gaps == []
    assert line == KickerStatLine(extra_points=1, field_goals_0_39=2 + 3 + 4, field_goals_40_49=5,
                                  field_goals_50_plus=6 + 7)


def test_a_fumble_count_that_disagrees_with_its_parts_is_noted_for_tracing(tmp_path):
    report = grade(tmp_path)
    assert person(report, "kc_wr1")["notes"] == ["FUMBLES_LOST_SOURCES_DIFFER:total=1:parts=0"]
    assert person(report, "kc_qb")["notes"] == []


# ----------------------------------------------------------------- gaps are named, never zero


def test_missing_people_and_stats_are_named_never_zero(tmp_path):
    report = grade(tmp_path, stats_bytes(cells={"kc_rb": {"rushing_yards": ""}, "kc_te": {"receptions": "NA"}}))
    assert kinds(person(report, "kc_wr2")) == {"NO_STAT_ROW"}
    assert kinds(person(report, "den_wr2")) == {"IDENTITY_UNBOUND"}
    assert kinds(person(report, "kc_dst")) == {"DST_NOT_IN_PLAYER_FILE"}
    assert kinds(person(report, "kc_rb")) == {"STAT_CELL_BLANK:rushing_yards"}
    assert kinds(person(report, "kc_te")) == {"STAT_CELL_BLANK:receptions"}
    for key in ("kc_wr2", "den_wr2", "kc_dst", "kc_rb", "kc_te"):
        assert person(report, key)["realized_hundredths"] is None
    grade_ = report["grade"]
    assert grade_["graded_people"] == 14 and grade_["usable_people"] == 8
    assert grade_["gaps_by_kind"] == {"DST_NOT_IN_PLAYER_FILE": 2, "IDENTITY_UNBOUND": 1, "NO_STAT_ROW": 1,
                                      "STAT_CELL_BLANK:receptions": 1, "STAT_CELL_BLANK:rushing_yards": 1}


def test_a_column_the_file_does_not_carry_is_named_per_person(tmp_path):
    report = grade(tmp_path, stats_bytes(drop=("special_teams_tds",)))
    assert kinds(person(report, "kc_qb")) == {"STAT_NOT_CARRIED:special_teams_tds"}
    assert person(report, "kc_k")["realized_hundredths"] == REALIZED["kc_k"]
    report = grade(tmp_path, stats_bytes(drop=tuple(KICKER)))
    assert kinds(person(report, "den_k")) == {f"STAT_NOT_CARRIED:{c}" for c in KICKER}
    assert person(report, "den_k")["realized_hundredths"] is None
    assert person(report, "den_qb")["realized_hundredths"] == REALIZED["den_qb"]


def test_an_unbound_person_is_never_matched_by_name(tmp_path):
    entry = person(grade(tmp_path), "den_wr2")
    assert entry["provider_player_id"] is None and entry["stat_line"] is None
    report = grade(tmp_path, identity_review=identity_bytes(alter={"kc_rb": {"DECISION": "REJECT"}}))
    assert kinds(person(report, "kc_rb")) == {"IDENTITY_UNBOUND"}


def test_a_reviewed_id_wins_over_the_proposal(tmp_path):
    alter = {"kc_te": {"PROPOSED_PROVIDER_PLAYER_ID": GSIS["den_te"], "REVIEWED_PROVIDER_PLAYER_ID": GSIS["kc_te"]}}
    assert person(grade(tmp_path, identity_review=identity_bytes(alter=alter)), "kc_te")["realized_hundredths"] == 770


# ----------------------------------------------------------------- the reconciliation


def lineup(report: dict, n: int) -> dict:
    return next(item for item in report["reconciliation"]["lineups"] if item["entry_id"] == entry_id(n))


def test_a_covered_lineup_reconciles_and_a_two_hundredth_gap_is_named(tmp_path):
    report = grade(tmp_path)
    first = lineup(report, 0)
    assert (first["status"], first["realized_hundredths"], first["dk_hundredths"]) == ("RECONCILED", "13360", 13360)
    second = lineup(report, 1)
    assert second["status"] == "MISMATCH" and second["gap_hundredths"] == "2"
    named = {player["dk_id"]: player for player in second["players"]}
    assert named[CPT["den_rb"]]["captain"] and named[CPT["den_rb"]]["points_hundredths"] == "4515"
    assert named[FLEX["kc_qb"]]["stat_line"]["passing_yards"] == 310


def test_one_hundredth_is_inside_the_tolerance(tmp_path):
    assert lineup(grade(tmp_path, entries=entries_bytes({0: 13361})), 0)["status"] == "RECONCILED"
    assert lineup(grade(tmp_path, entries=entries_bytes({0: 13362})), 0)["status"] == "MISMATCH"


def test_a_captain_counts_exactly_one_and_a_half(tmp_path):
    lineups = [(["kc_te", "kc_qb", "kc_rb", "den_rb", "den_wr1", "kc_wr1"], 0)]
    report = grade(tmp_path, lineups=lineup_bytes(lineups), entries=entries_bytes({0: 1155 + 2460 + 1390 + 3010
                                                                                       + 1160 + 3340}))
    assert lineup(report, 0)["status"] == "RECONCILED"
    assert lineup(report, 0)["players"][0]["points_hundredths"] == "1155"


def test_single_uncovered_lineups_form_residual_groups(tmp_path):
    report = grade(tmp_path)
    for n in (2, 3, 4):
        assert lineup(report, n)["status"] == "NOT_FULLY_COVERED"
        assert lineup(report, n)["uncovered"] == [uid("kc_dst")]
    group = report["reconciliation"]["residual_groups"][uid("kc_dst")]
    assert group == {"lineups": 3, "implied_hundredths": ["700", "700", "700"], "spread_hundredths": "0",
                     "status": "AGREE"}
    for points, status in ((11492, "AGREE"), (11493, "DISAGREE")):
        report = grade(tmp_path, entries=entries_bytes({4: points}))
        assert report["reconciliation"]["residual_groups"][uid("kc_dst")]["status"] == status


def test_an_entry_missing_from_history_or_another_contest_is_named(tmp_path):
    assert lineup(grade(tmp_path, entries=entries_bytes(drop=(0,))), 0)["status"] == "ENTRY_NOT_IN_HISTORY"
    assert lineup(grade(tmp_path, entries=entries_bytes(contest="9002")), 0)["status"] == "CONTEST_DISAGREES"


def test_no_lineups_means_no_reconciliation(tmp_path):
    assert grade(tmp_path, lineups=None, entries=None)["reconciliation"] is None


# ----------------------------------------------------------------- the grade


def test_the_grade_uses_usable_people_only(tmp_path):
    report = grade(tmp_path)
    usable = [k for k in REALIZED]
    expected = sum(abs(PRIORS[k] - REALIZED[k] / 100) for k in usable) / len(usable)
    mae = report["grade"]["prior"]["player_points_mae"]
    assert mae["n"] == 10 and mae["value"] == pytest.approx(expected, abs=1e-4) == pytest.approx(6.19)
    assert mae["registered_metric"] == "player_points_mae" and mae["departures"]
    scale = sum(PRIORS[k] for k in usable) / sum(INFO[k][3] for k in usable)
    salary_mae = sum(abs(INFO[k][3] * scale - REALIZED[k] / 100) for k in usable) / len(usable)
    assert report["grade"]["salary"]["player_points_mae"]["value"] == pytest.approx(salary_mae, abs=1e-4)
    assert person(report, "den_k")["out_of_selection"] is True
    assert person(report, "den_k")["realized_hundredths"] == 500
    assert report["grade"]["out_of_selection"] == 1


def test_spearman_averages_tied_ranks_and_refuses_too_few():
    assert pg.spearman([10, 8, 6, 4], [20, 5, 5, 1]) == (pytest.approx(0.948683, abs=1e-6), None)
    assert pg.spearman([1, 2], [2, 1]) == (None, "FEWER_THAN_3")
    assert pg.spearman([1, 1, 1], [1, 2, 3]) == (None, "ZERO_VARIANCE")


def test_avg_points_per_game_is_never_read(tmp_path):
    first = grade(tmp_path, salaries=salary_bytes("0"))
    second = grade(tmp_path, salaries=salary_bytes("31.7"))
    first["inputs"].pop("salaries"), second["inputs"].pop("salaries")
    assert first == second
    assert "AvgPointsPerGame" not in Path(pg.__file__).read_text(encoding="utf-8")


def test_the_report_states_what_it_does_not_establish(tmp_path):
    report = grade(tmp_path)
    assert report["model_status"] == "PRIOR_ONLY"
    assert report["does_not_establish"] and report["not_computed"]["participation_brier"]
    text = pg.render(report).decode("utf-8").lower()
    for word in ("calibrated", "win_probability", "\"ev\"", "roi"):
        assert word not in text


# ----------------------------------------------------------------- determinism and mutation


def test_the_same_bytes_give_byte_identical_reports(tmp_path):
    assert pg.render(grade(tmp_path)) == pg.render(grade(tmp_path))
    assert pg.render(grade(tmp_path)).endswith(b"}\n") and b"\r" not in pg.render(grade(tmp_path))


def test_one_changed_stat_byte_changes_the_report(tmp_path):
    raw = stats_bytes()
    changed = raw.replace(b",104,", b",105,", 1)
    assert len(changed) == len(raw) and changed != raw
    assert pg.render(grade(tmp_path, raw)) != pg.render(grade(tmp_path, changed))
    assert person(grade(tmp_path, changed), "kc_wr1")["realized_hundredths"] == 3350


def test_a_same_length_damaged_identity_byte_refuses(tmp_path):
    raw = identity_bytes()
    damaged = raw.replace(FLEX["kc_rb"].encode() + b",KC RB", b"3999,KC RB", 1)
    assert len(damaged) == len(raw) and damaged != raw
    assert "identity" in refused(tmp_path, "PLAYER_GRADING_INPUT_INVALID", identity_review=damaged)


# ----------------------------------------------------------------- refusals


def test_stats_refusals(tmp_path):
    assert "game_id" in refused(tmp_path, "PLAYER_GRADING_STATS_INVALID", stats=stats_bytes(drop=("game_id",)))
    assert "passing_yards" in refused(tmp_path, "PLAYER_GRADING_STATS_INVALID",
                                      stats=stats_bytes(cells={"kc_qb": {"passing_yards": "abc"}}))
    assert "passing_tds" in refused(tmp_path, "PLAYER_GRADING_STATS_INVALID",
                                    stats=stats_bytes(cells={"kc_qb": {"passing_tds": "1.5"}}))
    duplicate = dict(player_id=GSIS["kc_te"], season=SEASON, week=WEEK, season_type="REG", game_id=GAME_ID)
    assert "DUPLICATE" in refused(tmp_path, "PLAYER_GRADING_STATS_INVALID", stats=stats_bytes(extra_rows=[duplicate]))
    refused(tmp_path, "PLAYER_GRADING_WEEK_ABSENT", stats=stats_bytes(week_rows=False))
    huge = stats_bytes(cells={"kc_qb": {"player_display_name": "x" * 200_000}})
    assert "UNREADABLE" in refused(tmp_path, "PLAYER_GRADING_STATS_INVALID", stats=huge)


def test_a_row_credited_to_no_player_is_counted_not_refused(tmp_path):
    blank = dict(player_id="", season=SEASON, week=WEEK, season_type="REG", game_id=GAME_ID, team="KC")
    report = grade(tmp_path, stats_bytes(extra_rows=[blank]))
    assert (report["slate"]["week_stat_rows"], report["slate"]["unattributed_stat_rows"]) == (11, 1)
    assert person(report, "kc_qb")["realized_hundredths"] == REALIZED["kc_qb"]


def test_stats_bytes_that_do_not_match_their_entry_refuse(tmp_path):
    raw = stats_bytes()
    with pytest.raises(pg.PlayerGradingRefused) as caught:
        pg.grade_slate(stats_raw=raw + b"\n", stats_entry=stats_entry(raw), season=SEASON, week=WEEK,
                       **write_inputs(tmp_path))
    assert caught.value.code == "PLAYER_GRADING_STATS_INVALID"


def test_a_game_whose_rows_name_two_games_is_unbound(tmp_path):
    detail = refused(tmp_path, "PLAYER_GRADING_GAME_UNBOUND", stats=stats_bytes(game_for={"DEN": "2026_02_DEN_LV"}))
    assert "2026_02_DEN_LV" in detail


GAMES = [("A@B", ("A", "B")), ("C@D", ("C", "D"))]


@pytest.mark.parametrize("found, detail", [
    ({"A@B": [("A", "g1", "a"), ("B", "g1", "b")], "C@D": [("C", "g1", "c"), ("D", "g1", "d")]},
     "C@D:g1:ALSO_ANOTHER_GAME"),
    ({"A@B": [("A", "g1", "a"), ("B", "g1", "b")]}, "C@D:NO_STAT_ROWS"),
    ({"A@B": [("A", "g1", "a")], "C@D": [("C", "g2", "c"), ("D", "g2", "d")]}, "A@B:g1:NO_STAT_ROW_FOR:['B']"),
    ({"A@B": [("A", "g1", "a"), ("B", "g9", "b")]}, "A@B:ROWS_NAME_SEVERAL_GAMES:{'g1': ['a'], 'g9': ['b']}"),
])
def test_each_slate_game_binds_one_nflverse_game_holding_both_teams(found, detail):
    with pytest.raises(pg.PlayerGradingRefused) as caught:
        pg.bind_games(GAMES, found)
    assert (caught.value.code, caught.value.detail) == ("PLAYER_GRADING_GAME_UNBOUND", detail)
    both = {"A@B": [("A", "g1", "a"), ("B", "g1", "b")], "C@D": [("C", "g2", "c"), ("D", "g2", "d")]}
    assert pg.bind_games(GAMES, both) == {"A@B": "g1", "C@D": "g2"}


def test_a_wrong_week_with_one_team_on_bye_refuses(tmp_path):
    assert "NO_STAT_ROW_FOR:['DEN']" in refused(tmp_path, "PLAYER_GRADING_GAME_UNBOUND", stats=stats_bytes(teams=("KC",)))


def test_a_postseason_row_in_the_same_week_is_not_read(tmp_path):
    post = dict(player_id=GSIS["kc_te"], season=SEASON, week=WEEK, season_type="POST", game_id=GAME_ID, team="KC",
                receptions=9, receiving_yards=150)
    assert person(grade(tmp_path, stats_bytes(extra_rows=[post])), "kc_te")["realized_hundredths"] == 770


def test_a_classic_lineup_file_on_a_showdown_slate_refuses(tmp_path):
    keys = ["kc_qb", "kc_rb", "den_rb", "kc_wr1", "kc_wr2", "den_wr1", "kc_te", "den_te", "kc_dst"]
    data = ("Entry ID,Contest Name,Contest ID,Entry Fee,QB,RB,RB,WR,WR,WR,TE,FLEX,DST,,Instructions\n"
            f"{entry_id(0)},Classic,9001,$5,{','.join(FLEX[k] for k in keys)},,\n").encode("utf-8")
    assert "MODE" in refused(tmp_path, "PLAYER_GRADING_INPUT_INVALID", lineups=data)


@pytest.mark.parametrize("name, data", [
    ("salaries", b"Position,Name + ID\n"),
    ("pool_scores", pool_scores_bytes(schema_version="nfl_prior_pool_scores_v9")),
    ("pool_scores", pool_scores_bytes(by_person={"KC|QB|Nobody": 1.0})),
    ("pool_scores", pool_scores_bytes(by_dk_id={"9999": 1.0})),
    ("pool_scores", pool_scores_bytes(by_person={uid("kc_qb"): float("nan")})),
    ("identity_review", b"DK_ID,DK_NAME\n3000,KC QB\n"),
    ("identity_review", identity_bytes(alter={"kc_qb": {"DK_NAME": "Other QB"}})),
    ("identity_review", identity_bytes(alter={"kc_qb": {"DK_TEAM": "DEN"}})),
    ("identity_review", identity_bytes(alter={"kc_qb": {"DK_POSITION": "RB"}})),
    ("identity_review", identity_bytes().replace(b"KC TE,KC", b"KC T\xc9,KC", 1)),
    ("identity_review", identity_bytes().replace(b",ACCEPT,", b",ACCEPT,,", 1)),
    ("entries", json.dumps({"schema_version": ENTRIES_VERSION, "entries": [1]}).encode("utf-8")),
    ("identity_review", identity_bytes(alter={"kc_te": {"REVIEWED_PROVIDER_PLAYER_ID": GSIS["kc_qb"]}})),
    ("lineups", lineup_bytes().replace(CPT["kc_qb"].encode() + b",", b"Some Name,", 1)),
    ("entries", entries_bytes(schema="nfl_dk_entry_history_entries_v0")),
])
def test_each_input_refuses_by_name(tmp_path, name, data):
    assert name.split("_")[0] in refused(tmp_path, "PLAYER_GRADING_INPUT_INVALID", **{name: data})


def test_lineups_without_entries_refuse(tmp_path):
    assert "entries" in refused(tmp_path, "PLAYER_GRADING_INPUT_INVALID", entries=None)


def test_every_code_is_registered_in_its_family():
    registry = load_gate_registry()
    family = registry.families["player_grading"]
    assert (family.gate_class.value, family.stops.value) == ("P", "CERTIFICATION")
    for code in pg.CODES:
        assert registry.codes[code] == "player_grading", code


# ----------------------------------------------------------------- the stats package


def fake_fetch(raw: bytes, calls: list):
    def fetch(url, destination_dir, *, source, license_decision, parser_version, **_kwargs):
        calls.append((url, parser_version))
        digest = hashlib.sha256(raw).hexdigest()
        target = Path(destination_dir) / f"{digest}.csv"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        return SourceArtifact(artifact_id=digest, path=str(target), sha256=digest, byte_count=len(raw),
                              source=source, source_uri=url, license_decision=license_decision,
                              captured_at=datetime.now(timezone.utc), parser_version=parser_version)
    return fetch


def test_the_stats_package_reuses_the_priors_source_entry(tmp_path, monkeypatch):
    calls: list = []
    raw = stats_bytes()
    monkeypatch.setattr(priors, "fetch_public_artifact", fake_fetch(raw, calls))
    first_raw, first_entry = pg.load_or_fetch_stats(tmp_path / "pkg", SEASON)
    assert calls == [(STATS_ENTRY_URL, "nflverse_stats_player_week_csv_v1")]
    assert first_raw == raw and first_entry["sha256"] == hashlib.sha256(raw).hexdigest()
    monkeypatch.setattr(priors, "fetch_public_artifact", lambda *a, **k: pytest.fail("fetched twice"))
    assert pg.load_or_fetch_stats(tmp_path / "pkg", SEASON) == (first_raw, first_entry)


def test_a_failed_fetch_refuses_rather_than_returning_nothing(tmp_path, monkeypatch):
    def broken(*_args, **_kwargs):
        raise OSError("network down")
    monkeypatch.setattr(priors, "fetch_public_artifact", broken)
    with pytest.raises(pg.PlayerGradingRefused) as caught:
        pg.load_or_fetch_stats(tmp_path / "pkg", SEASON)
    assert caught.value.code == "PLAYER_GRADING_STATS_UNAVAILABLE"
    assert not (tmp_path / "pkg" / priors.MANIFEST_FILENAME).exists()


def test_a_damaged_package_or_another_season_refuses(tmp_path, monkeypatch):
    raw = stats_bytes()
    monkeypatch.setattr(priors, "fetch_public_artifact", fake_fetch(raw, []))
    _raw, entry = pg.load_or_fetch_stats(tmp_path / "pkg", SEASON)
    with pytest.raises(pg.PlayerGradingRefused) as caught:
        pg.load_or_fetch_stats(tmp_path / "pkg", SEASON + 1)
    assert caught.value.code == "PLAYER_GRADING_STATS_INVALID"
    stored = tmp_path / "pkg" / entry["relative_path"]
    data = stored.read_bytes()
    stored.write_bytes(data.replace(b",104,", b",105,", 1))
    with pytest.raises(pg.PlayerGradingRefused) as caught:
        pg.load_or_fetch_stats(tmp_path / "pkg", SEASON)
    assert caught.value.code == "PLAYER_GRADING_STATS_INVALID"


def test_a_package_file_that_cannot_be_read_is_a_stats_refusal(tmp_path, monkeypatch):
    monkeypatch.setattr(priors, "fetch_public_artifact", fake_fetch(stats_bytes(), []))
    pg.load_or_fetch_stats(tmp_path / "pkg", SEASON)
    loaded = priors.load_frozen_manifest((tmp_path / "pkg").resolve())
    gone = {name: dataclasses.replace(item, path=tmp_path / "gone.csv") for name, item in loaded.items()}
    monkeypatch.setattr(priors, "load_frozen_manifest", lambda _root: gone)
    with pytest.raises(pg.PlayerGradingRefused) as caught:
        pg.load_or_fetch_stats(tmp_path / "pkg", SEASON)
    assert (caught.value.code, caught.value.detail.endswith(":FileNotFoundError")) == ("PLAYER_GRADING_STATS_INVALID", True)


# ----------------------------------------------------------------- the command


def run_cli(tmp_path: Path, capsys, out: Path, monkeypatch, **override) -> tuple[int, dict]:
    raw = stats_bytes()
    monkeypatch.setattr(priors, "fetch_public_artifact", fake_fetch(raw, []))
    paths = write_inputs(tmp_path, **override)
    argv = ["grade-players", "--salaries", str(paths["salaries"]), "--pool-scores", str(paths["pool_scores"]),
            "--identity-review", str(paths["identity_review"]), "--stats-package", str(tmp_path / "pkg"),
            "--season", str(SEASON), "--week", str(WEEK), "--out", str(out)]
    if paths["lineups"] is not None:
        argv += ["--lineups", str(paths["lineups"])]
    if paths["entries"] is not None:
        argv += ["--entries", str(paths["entries"])]
    code = cli.main(argv)
    return code, json.loads(capsys.readouterr().out)


def test_the_command_writes_one_report_and_reruns_identically(tmp_path, capsys, monkeypatch):
    code, summary = run_cli(tmp_path, capsys, tmp_path / "out1", monkeypatch)
    assert code == 0 and summary["status"] == "COMPLETE" and summary["model_status"] == "PRIOR_ONLY"
    assert summary["reconciliation"] == {"MISMATCH": 1, "NOT_FULLY_COVERED": 3, "RECONCILED": 1}
    assert sorted(p.name for p in (tmp_path / "out1").iterdir()) == ["player_grading.w1.json"]
    code, _summary = run_cli(tmp_path, capsys, tmp_path / "out2", monkeypatch)
    assert code == 0
    first = (tmp_path / "out1" / "player_grading.w1.json").read_bytes()
    assert first == (tmp_path / "out2" / "player_grading.w1.json").read_bytes()
    assert hashlib.sha256(first).hexdigest() == summary["report_sha256"]


def test_the_command_refuses_by_code_and_never_prints_release_truths(tmp_path, capsys, monkeypatch):
    (tmp_path / "taken").mkdir()
    code, summary = run_cli(tmp_path, capsys, tmp_path / "taken", monkeypatch)
    assert (code, summary["status"], summary["code"]) == (2, "REFUSED", "PLAYER_GRADING_OUTPUT_EXISTS")
    assert not (tmp_path / "pkg").exists(), "the folder check runs before any fetch"
    for name, data in (("pool_scores", pool_scores_bytes(schema_version="x")),
                       ("identity_review", identity_bytes().replace(b"KC TE,KC", b"KC T\xc9,KC", 1)),
                       ("entries", b'{"schema_version": "nfl_dk_entry_history_entries_v1", "entries": [1]}')):
        code, summary = run_cli(tmp_path, capsys, tmp_path / "fresh", monkeypatch, **{name: data})
        assert (code, summary["code"]) == (2, "PLAYER_GRADING_INPUT_INVALID"), name
        assert not (tmp_path / "fresh").exists()
        assert "RELEASE_DECISION" not in json.dumps(summary)


def test_an_unexpected_failure_is_still_never_a_release_truth(tmp_path, capsys, monkeypatch):
    def broken(**_kwargs):
        raise RuntimeError("boom")
    monkeypatch.setattr(pg, "grade_slate", broken)
    code, summary = run_cli(tmp_path, capsys, tmp_path / "out", monkeypatch)
    assert (code, summary["status"], summary["detail"]) == (2, "FAILED", "RuntimeError:boom")
    assert "RELEASE_DECISION" not in json.dumps(summary)


def test_a_failed_write_leaves_no_folder_behind(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(pg, "sha256_file", lambda _path: "0" * 64)
    code, summary = run_cli(tmp_path, capsys, tmp_path / "out", monkeypatch)
    assert (code, summary["status"]) == (2, "WRITE_FAILED")
    assert not (tmp_path / "out").exists()
