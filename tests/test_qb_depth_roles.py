"""P1 acceptance: the DEN@KC failure, reproduced and then resolved.

The fixture is the shape the standings recorded on 2026-09-14: a running back
the market prices as the most expensive FLEX on the slate whose history is on
another team, and a backup quarterback taking almost half his team's attempts
from a prior-season split. Every capture here is synthetic and says so; no test
reaches the network.
"""
from __future__ import annotations

import csv
import io
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from nfl_dfs.hashing import sha256_bytes
from nfl_dfs.offensive_roles import (
    OffensiveRoleError,
    material_role_change_blockers,
    resolve_offensive_roles,
)
from nfl_dfs.participation import build_participation_contract
from nfl_dfs.prior_score import (
    SALARY_RANK_DIVERGENCE_FRACTION,
    SALARY_RANK_DIVERGENCE_MIN_PLACES,
    salary_rank_divergence,
    score_pool,
)
from nfl_dfs.qb_depth_roles import (
    ALLOCATION_VERSION,
    DEPTH_CHART_COLUMNS,
    SCHEMA_VERSION,
    TRANSFORMATION_VERSION,
    QbDepthRoleError,
    parse_depth_chart_excerpt,
    resolve_qb_depth_roles,
    verify_qb_depth_resolution,
)
from nfl_dfs.dk import parse_salaries
from nfl_dfs.opportunity import PLAYER_COLUMNS, TEAM_COLUMNS, load_opportunity_model
from nfl_dfs.prior_score import read_team_splits
from nfl_dfs.selection import select_prior_lineups

AS_OF = datetime(2026, 9, 14, 18, tzinfo=timezone.utc)
OBSERVED = AS_OF - timedelta(hours=6)
PRIOR_SEASON = 2025
GAME = "DEN@KC 09/14/2026 04:25PM ET"

# DEN@KC in miniature. "KC Transfer RB" is Kenneth Walker III: the slate's most
# expensive FLEX, with his history on another team. "KC Backup QB" is Justin
# Fields, behind Mahomes on the depth chart and holding 46% of the attempts from
# prior-season history.
_POOL = (
    ("KC", "QB", "KC Starter QB", "", 11000),
    ("KC", "QB", "KC Backup QB", "", 5200),
    ("KC", "RB", "KC Transfer RB", "", 10600),
    ("KC", "RB", "KC Committee RB", "", 4200),
    ("KC", "WR", "KC Alpha WR", "", 9000),
    ("KC", "TE", "KC Starting TE", "", 6000),
    ("KC", "K", "KC Kicker", "", 4000),
    ("KC", "DST", "Chiefs", "", 3200),
    ("DEN", "QB", "DEN Starter QB", "", 9400),
    ("DEN", "RB", "DEN Lead RB", "", 7800),
    ("DEN", "RB", "DEN Backup RB", "", 3600),
    ("DEN", "WR", "DEN Alpha WR", "", 8600),
    ("DEN", "TE", "DEN TE", "", 3000),
    ("DEN", "K", "DEN Kicker", "", 4400),
    ("DEN", "DST", "Broncos", "", 3800),
)

_GSIS = {
    "KC Starter QB": "00-0033873",
    "KC Backup QB": "00-0036945",
    "DEN Starter QB": "00-0034857",
}
# qb, carry, target, catch, ypt, rushing td, receiving td, capacity.
# The two Kansas City quarterbacks carry the 0.5395 / 0.4605 prior-season
# attempt split `docs/RUN_RECORD_20260914_DEN_KC.md` recorded.
_SHARES = {
    "KC Starter QB":   (0.5395, 0.12, 0.0,  0.0,  0.0,  0.10, 0.0,  0.98),
    "KC Backup QB":    (0.4605, 0.08, 0.0,  0.0,  0.0,  0.05, 0.0,  0.40),
    "KC Transfer RB":  (0.0,    0.21, 0.08, 0.75, 5.8,  0.25, 0.08, 0.35),
    "KC Committee RB": (0.0,    0.55, 0.10, 0.78, 6.1,  0.55, 0.10, 0.62),
    "KC Alpha WR":     (0.0,    0.03, 0.52, 0.68, 9.4,  0.03, 0.55, 0.91),
    "KC Starting TE":  (0.0,    0.01, 0.30, 0.72, 7.8,  0.02, 0.27, 0.80),
    "KC Third QB":     (0.0,    0.02, 0.0,  0.0,  0.0,  0.01, 0.0,  0.10),
    "KC Kicker":       (0.0,)  * 7 + (0.0,),
    "Chiefs":          (0.0,)  * 7 + (0.0,),
    "DEN Starter QB":  (1.0,    0.14, 0.0,  0.0,  0.0,  0.12, 0.0,  0.97),
    "DEN Lead RB":     (0.0,    0.58, 0.09, 0.79, 5.6,  0.62, 0.09, 0.59),
    "DEN Backup RB":   (0.0,    0.22, 0.05, 0.74, 5.2,  0.18, 0.05, 0.26),
    "DEN Alpha WR":    (0.0,    0.04, 0.54, 0.70, 10.2, 0.04, 0.57, 0.88),
    "DEN TE":          (0.0,    0.01, 0.22, 0.71, 7.1,  0.02, 0.19, 0.64),
    "DEN Kicker":      (0.0,)  * 7 + (0.0,),
    "Broncos":         (0.0,)  * 7 + (0.0,),
}
_TEAM_ROW = {
    "PLAYS_MEAN": "64", "PASS_RATE": "0.58", "PASS_YARDS_PER_ATTEMPT": "7.4",
    "RUSH_YARDS_PER_ATTEMPT": "4.4", "TOUCHDOWNS_MEAN": "3.0",
    "FIELD_GOALS_MEAN": "1.5", "TURNOVERS_MEAN": "1.1",
    "SACKS_ALLOWED_MEAN": "2.2", "UNCERTAINTY": "0.12",
    "MARKET_TOTAL": "47.5", "MARKET_SPREAD": "3",
    "MARKET_OBSERVED_AT": "2026-09-14T12:00:00+00:00",
    "WEATHER_STATE": "CLEAR", "ERA": "2026_TEST",
}
_SPLIT_COLUMNS = (
    "season", "week", "team", "season_type", "passing_tds", "rushing_tds",
    "passing_interceptions", "fumbles_lost_total", "pat_made", "pat_att",
    "fg_made_0_19", "fg_made_20_29", "fg_made_30_39", "fg_made_40_49",
    "fg_made_50_59", "fg_made_60_",
)


def _write_csv(path, columns, rows):
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(columns)
    writer.writerows(rows)
    path.write_bytes(buffer.getvalue().encode("utf-8"))
    return path


def _slate(tmp_path, pool=_POOL):
    header = (
        "Position", "Name + ID", "Name", "ID", "Roster Position", "Salary",
        "Game Info", "TeamAbbrev", "AvgPointsPerGame", "Status",
    )
    rows, dk_id = [], 60000000
    for team, position, name, status, flex_salary in pool:
        for role, salary in (("CPT", round(flex_salary * 1.5)), ("FLEX", flex_salary)):
            dk_id += 1
            rows.append(
                (position, f"{name} ({dk_id})", name, str(dk_id), role, str(salary),
                 GAME, team, "0", status)
            )
    return parse_salaries(_write_csv(tmp_path / "DKSalaries.csv", header, rows))


def _model(tmp_path, slate):
    game_id = slate.games[0].game_id
    team_rows = []
    for team in ("KC", "DEN"):
        row = {"TEAM": team, "GAME_ID": game_id, **_TEAM_ROW}
        row["MARKET_SPREAD"] = "-3" if team == "KC" else "3"
        team_rows.append([row[column] for column in TEAM_COLUMNS])
    flex = {p.underlying_id: p for p in slate.players if p.role == "FLEX"}
    player_rows = []
    for player in sorted(flex.values(), key=lambda item: int(item.dk_id)):
        qb, carry, target, catch, ypt, rtd, ctd, cap = _SHARES[player.name]
        player_rows.append(
            [player.dk_id, player.team, player.position,
             qb, carry, target, catch, ypt, rtd, ctd, cap, "PASS"]
        )
    return load_opportunity_model(
        slate,
        _write_csv(tmp_path / "team_projections.csv", TEAM_COLUMNS, team_rows),
        _write_csv(tmp_path / "player_opportunities.csv", PLAYER_COLUMNS, player_rows),
    )


def _splits(tmp_path):
    rows = []
    for team in ("KC", "DEN"):
        for week in range(1, 18):
            rows.append((str(PRIOR_SEASON), str(week), team, "REG",
                         "2", "1", "1", "1", "3", "3", "0", "0", "1", "1", "0", "0"))
    return read_team_splits(
        _write_csv(tmp_path / "stats_team_week.csv", _SPLIT_COLUMNS, rows),
        prior_season=PRIOR_SEASON,
        teams=("KC", "DEN"),
    )


_TRANSFER_HISTORY = {
    "KC|RB|KC Transfer RB": {
        "state": "CURRENT_ROLE_UNKNOWN",
        "incompatible_transfer": True,
        "current_team": "KC",
        "transfer_prior": {
            "basis": "OWN_OLD_TEAM_SHARE",
            "old_teams": ["SEA"],
            "own_old_share": 0.21,
        },
    }
}


def _setup(tmp_path, pool=_POOL, *, transfer=False):
    """The slate. `transfer=True` adds the unresolved role change on the RB.

    It is off by default because the gate is per-person and so is its remedy: a
    quarterback depth chart resolves quarterbacks and says nothing whatever
    about a running back. A test that wants to exercise the depth chart must not
    also leave an unrelated unresolved transfer sitting in the pool, or it is
    really testing the gate.
    """

    slate = _slate(tmp_path, pool=pool)
    model = _model(tmp_path, slate)
    if transfer:
        model = replace(model, offensive_history_by_person=dict(_TRANSFER_HISTORY))
    return slate, model, build_participation_contract(slate), _splits(tmp_path)


def _person(slate, name):
    return next(p.underlying_id for p in slate.players if p.name == name)


def _prior_points(slate, offense, splits):
    """Score the pool without the gate, so the ranking itself can be asserted.

    `score_pool` runs the gate as its last act, which is right for the engine
    and unhelpful for a test whose whole subject is the input that gate reads.
    """

    from nfl_dfs.prior_score import score_pool as _score
    import nfl_dfs.prior_score as module

    original = module.enforce_material_role_change_gate
    module.enforce_material_role_change_gate = lambda *args, **kwargs: None
    try:
        return _score(slate, offense.model, splits, offensive_roles=offense).by_person
    finally:
        module.enforce_material_role_change_gate = original


def _excerpt(team, ordering, observed=OBSERVED):
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(DEPTH_CHART_COLUMNS)
    for rank, name in enumerate(ordering, start=1):
        writer.writerow(
            [
                observed.isoformat().replace("+00:00", "Z"),
                team,
                name,
                "",
                _GSIS[name],
                "16",
                "3WR 1TE",
                "9",
                "Quarterback",
                "QB",
                "9",
                str(rank),
            ]
        )
    return buffer.getvalue()


def _package(root, slate, orders, *, as_of=AS_OF, observed=OBSERVED,
             expiry_hours=36, unlisted=None):
    root.mkdir(parents=True, exist_ok=True)
    (root / "sources").mkdir(exist_ok=True)
    sources, declarations = [], []
    by_name = {}
    for player in slate.players:
        by_name.setdefault(player.name, {})[player.role or "FLEX"] = player
    for team, ordering in orders.items():
        excerpt = _excerpt(team, ordering, observed)
        digest = sha256_bytes(excerpt.encode("utf-8"))
        (root / "sources" / f"{digest}.csv").write_bytes(excerpt.encode("utf-8"))
        sources.append(
            {
                "path": f"sources/{digest}.csv",
                "sha256": digest,
                "source_uri": (
                    "https://github.com/nflverse/nflverse-data/releases/download"
                    "/depth_charts/depth_charts_2026.csv"
                ),
                "observed_at": observed.isoformat(),
                "captured_at": (observed + timedelta(minutes=5)).isoformat(),
                "expires_at": (observed + timedelta(hours=expiry_hours)).isoformat(),
                "license_decision": "PERMITTED_REPOSITORY_LICENSE",
                "parser_version": "nflverse_depth_charts_csv_v1",
                "transformation_version": TRANSFORMATION_VERSION,
                "support_kind": "DEPTH_CHART_ORDER",
                "supporting_excerpt": excerpt,
                "synthetic": True,
                "upstream_sha256": sha256_bytes(b"upstream-depth-chart-2026"),
            }
        )
        entries = [
            {
                "underlying_id": _person(slate, name),
                "cpt_dk_id": by_name[name]["CPT"].dk_id,
                "flex_dk_id": by_name[name]["FLEX"].dk_id,
                "provider_player_id": _GSIS[name],
                "player_name": name,
                "pos_rank": rank,
            }
            for rank, name in enumerate(ordering, start=1)
        ]
        absent = [
            {
                "underlying_id": _person(slate, name),
                "cpt_dk_id": by_name[name]["CPT"].dk_id,
                "flex_dk_id": by_name[name]["FLEX"].dk_id,
                "player_name": name,
            }
            for name in (unlisted or {}).get(team, ())
        ]
        declarations.append(
            {
                "team": team,
                "game_id": slate.games[0].game_id,
                "declared_observed_at": observed.isoformat(),
                "starter": entries[0],
                "backups": entries[1:],
                "unlisted": absent,
                "source_sha256": digest,
            }
        )
    path = root / "qb_depth_roles.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": SCHEMA_VERSION,
                "allocation_version": ALLOCATION_VERSION,
                "transformation_version": TRANSFORMATION_VERSION,
                "salary_sha256": slate.salary_hash,
                "game_ids": [slate.games[0].game_id],
                "sources": sources,
                "declarations": declarations,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return path


def _orders():
    return {
        "KC": ("KC Starter QB", "KC Backup QB"),
        "DEN": ("DEN Starter QB",),
    }


# --- the diagnostic -------------------------------------------------------


def test_the_transfer_priced_as_the_slates_best_is_named_with_its_evidence_state(tmp_path):
    # The Walker case, measured on the ranking function directly: the market has
    # him second-dearest on the board and the prior has him ninth, and the state
    # that produced the prior travels with the finding.
    slate, model, contract, splits = _setup(tmp_path, transfer=True)
    package = _package(tmp_path / "qb", slate, _orders())
    qb_depth = resolve_qb_depth_roles(
        slate, model, contract, evidence_path=package, as_of=AS_OF
    )
    offense = resolve_offensive_roles(
        slate, qb_depth.model, contract, as_of=AS_OF
    )
    by_person = _prior_points(slate, offense, splits)
    transfer = _person(slate, "KC Transfer RB")
    finding = next(
        row
        for row in salary_rank_divergence(slate, by_person, offense.report)
        if row["person"] == transfer
    )
    assert finding["salary"] == 10600
    assert finding["overall_salary_rank"] == 2  # only the starting QB costs more
    assert finding["divergence_places"] >= SALARY_RANK_DIVERGENCE_MIN_PLACES
    assert finding["divergence_share_of_slate"] >= SALARY_RANK_DIVERGENCE_FRACTION
    assert finding["evidence_state"] == "TRANSFER_PRIOR_UNVERIFIED"


def test_the_zeroed_backup_quarterback_is_named_in_the_selection_report(tmp_path):
    # After the depth chart zeroes him, DraftKings still prices the backup at
    # $5,200 and this scorer puts him last. That disagreement is real and it is
    # reported; it is not a gate, because nothing says his role is unresolved.
    slate, model, contract, splits = _setup(tmp_path)
    package = _package(tmp_path / "qb", slate, _orders())
    lineups, scores, report = select_prior_lineups(
        slate, model, splits, contract, count=1,
        qb_depth_role_evidence_json=package, as_of=AS_OF,
    )
    backup = _person(slate, "KC Backup QB")
    finding = next(
        row for row in scores.salary_rank_divergence if row["person"] == backup
    )
    assert finding["salary"] == 5200
    assert finding["overall_prior_rank"] == finding["scored_people"]
    published = report["salary_rank_divergence"]
    assert published["version"] == "salary_rank_divergence_v1"
    assert "WHICH_SIDE_IS_WRONG" in published["does_not_establish"]
    assert backup in {row["person"] for row in published["findings"]}
    assert lineups


def test_a_person_priced_where_his_prior_puts_him_does_not_trip(tmp_path):
    slate, model, contract, splits = _setup(tmp_path)
    package = _package(tmp_path / "qb", slate, _orders())
    _lineups, scores, _report = select_prior_lineups(
        slate, model, splits, contract, count=1,
        qb_depth_role_evidence_json=package, as_of=AS_OF,
    )
    diverging = {row["person"] for row in scores.salary_rank_divergence}
    assert _person(slate, "KC Alpha WR") not in diverging
    assert _person(slate, "DEN Alpha WR") not in diverging
    assert _person(slate, "DEN Lead RB") not in diverging


def test_the_cheapest_row_is_ranked_never_the_inflated_captain_row(tmp_path):
    slate, model, contract, splits = _setup(tmp_path)
    package = _package(tmp_path / "qb", slate, _orders())
    _lineups, scores, _report = select_prior_lineups(
        slate, model, splits, contract, count=1,
        qb_depth_role_evidence_json=package, as_of=AS_OF,
    )
    assert scores.salary_rank_divergence
    for row in scores.salary_rank_divergence:
        listed = [p.salary for p in slate.players if p.underlying_id == row["person"]]
        assert len(listed) == 2 and row["salary"] == min(listed)


def test_divergence_is_reported_deterministically(tmp_path):
    slate, model, contract, splits = _setup(tmp_path)
    package = _package(tmp_path / "qb", slate, _orders())
    runs = [
        select_prior_lineups(
            slate, model, splits, contract, count=1,
            qb_depth_role_evidence_json=package, as_of=AS_OF,
        )[1].salary_rank_divergence
        for _ in range(2)
    ]
    assert runs[0] == runs[1]


# --- the gate -------------------------------------------------------------


def test_an_unresolved_transfer_the_market_disagrees_with_stops_the_run(tmp_path):
    slate, model, contract, splits = _setup(tmp_path, transfer=True)
    # No depth-chart package at all: the transfer is still unresolved, and Ben's
    # 2026-09-19 ruling makes that a stop rather than a diagnostic.
    with pytest.raises(OffensiveRoleError) as error:
        select_prior_lineups(slate, model, splits, contract, count=1, as_of=AS_OF)
    message = str(error.value)
    assert "OFFENSIVE_UNRESOLVED_MATERIAL_ROLE_CHANGE" in message
    assert _person(slate, "KC Transfer RB") in message
    assert "old_teams=SEA" in message
    # The stop names the action that actually clears it. A running back is
    # not resolved by a quarterback depth chart, so it must not say so.
    assert "offensive_role_evidence_json" in message
    assert "qb_depth_role_evidence_json" not in message
    assert "make_offensive_role_evidence.py" not in message
    assert error.value.report["evidence_state"] == "UNKNOWN"


def test_an_unresolved_transfer_the_market_agrees_with_stays_a_diagnostic(tmp_path):
    # The gate is conjunctive on purpose. Same unverified transfer prior, priced
    # where the prior puts him, and the run continues.
    cheap = tuple(
        (team, position, name, status, 3000 if name == "KC Transfer RB" else salary)
        for team, position, name, status, salary in _POOL
    )
    slate, model, contract, splits = _setup(tmp_path, pool=cheap, transfer=True)
    package = _package(tmp_path / "qb", slate, _orders())
    lineups, scores, _report = select_prior_lineups(
        slate, model, splits, contract, count=1,
        qb_depth_role_evidence_json=package, as_of=AS_OF,
    )
    assert lineups
    transfer = _person(slate, "KC Transfer RB")
    assert transfer not in {row["person"] for row in scores.salary_rank_divergence}


def test_the_gate_needs_both_halves(tmp_path):
    report = {
        "findings": [
            {"person": "a", "state": "TRANSFER_PRIOR_UNVERIFIED", "history_basis": {}},
            {"person": "b", "state": "SOURCE_SUPPORTED_ADJUSTMENT", "history_basis": {}},
        ]
    }
    diverging = [{"person": "b", "salary": 9000, "prior_points": 1.0, "divergence_places": 14}]
    assert material_role_change_blockers(report, diverging) == ()
    diverging = [{"person": "a", "salary": 9000, "prior_points": 1.0, "divergence_places": 14}]
    assert len(material_role_change_blockers(report, diverging)) == 1


# --- the remedy -----------------------------------------------------------


def test_the_depth_chart_moves_every_attempt_onto_the_named_starter(tmp_path):
    slate, model, contract, splits = _setup(tmp_path)
    package = _package(tmp_path / "qb", slate, _orders())
    resolution = resolve_qb_depth_roles(
        slate, model, contract, evidence_path=package, as_of=AS_OF
    )
    starter = _person(slate, "KC Starter QB")
    backup = _person(slate, "KC Backup QB")
    shares = {p.underlying_id: p.qb_attempt_share for p in resolution.model.players}
    assert shares[backup] == 0.0
    assert shares[starter] == pytest.approx(0.5395 + 0.4605)
    assert resolution.report["starters_by_team"]["KC"] == starter
    assert resolution.report["allocation_version"] == ALLOCATION_VERSION
    assert "TARGET_SHARE" in resolution.report["does_not_establish"]
    assert "HOW_MANY_ATTEMPTS_THE_TEAM_WILL_THROW" in resolution.report["does_not_establish"]


def test_only_the_attempt_share_moves(tmp_path):
    slate, model, contract, _splits_unused = _setup(tmp_path)
    package = _package(tmp_path / "qb", slate, _orders())
    resolution = resolve_qb_depth_roles(
        slate, model, contract, evidence_path=package, as_of=AS_OF
    )
    before = {p.underlying_id: p for p in model.players}
    for player in resolution.model.players:
        original = before[player.underlying_id]
        assert player.target_share == original.target_share
        assert player.carry_share == original.carry_share
        assert player.rushing_td_share == original.rushing_td_share
        assert player.receiving_td_share == original.receiving_td_share


def test_supplying_the_package_clears_the_stop_and_scores_the_backup_at_zero(tmp_path):
    slate, model, contract, splits = _setup(tmp_path)
    package = _package(tmp_path / "qb", slate, _orders())
    _lineups, scores, report = select_prior_lineups(
        slate, model, splits, contract, count=1,
        qb_depth_role_evidence_json=package, as_of=AS_OF,
    )
    backup = _person(slate, "KC Backup QB")
    starter = _person(slate, "KC Starter QB")
    assert scores.by_person[backup] < scores.by_person[starter]
    assert report["qb_depth_roles"]["starters_by_team"]["KC"] == starter
    changed = {row["person"]: row for row in report["qb_depth_roles"]["changed_people"]}
    assert changed[backup]["qb_attempt_share_after"] == 0.0
    assert changed[backup]["role"] == "BACKUP"


def test_replay_is_byte_identical(tmp_path):
    slate, model, contract, splits = _setup(tmp_path)
    package = _package(tmp_path / "qb", slate, _orders())
    payloads = []
    for _ in range(2):
        _lineups, _scores, report = select_prior_lineups(
            slate, model, splits, contract, count=1,
            qb_depth_role_evidence_json=package, as_of=AS_OF,
        )
        payloads.append(
            json.dumps(report["qb_depth_roles"], sort_keys=True, default=str)
        )
    assert payloads[0] == payloads[1]


# --- adversarial ----------------------------------------------------------


def test_a_package_that_omits_a_listed_quarterback_is_refused(tmp_path):
    slate, model, contract, _unused = _setup(tmp_path)
    package = _package(
        tmp_path / "qb", slate, {"KC": ("KC Starter QB",), "DEN": ("DEN Starter QB",)}
    )
    with pytest.raises(QbDepthRoleError, match="QB_DEPTH_TEAM_COVERAGE_MISMATCH"):
        resolve_qb_depth_roles(slate, model, contract, evidence_path=package, as_of=AS_OF)


def test_a_quarterback_the_chart_does_not_name_is_declared_unlisted_and_zeroed(tmp_path):
    # The real shape, measured on DET@BUF 2026-09-17: DraftKings sells three
    # quarterbacks and the published chart names two.
    pool = _POOL + (("KC", "QB", "KC Third QB", "", 4000),)
    slate, model, contract, _unused = _setup(tmp_path, pool=pool)
    package = _package(
        tmp_path / "qb", slate, _orders(), unlisted={"KC": ("KC Third QB",)}
    )
    resolution = resolve_qb_depth_roles(
        slate, model, contract, evidence_path=package, as_of=AS_OF
    )
    third = _person(slate, "KC Third QB")
    assert resolution.report["unlisted_on_depth_chart"] == [third]
    shares = {p.underlying_id: p.qb_attempt_share for p in resolution.model.players}
    assert shares[third] == 0.0
    assert shares[_person(slate, "KC Starter QB")] == pytest.approx(0.5395 + 0.4605)
    changed = {row["person"]: row for row in resolution.report["changed_people"]}
    assert changed[third]["role"] == "UNLISTED_ON_DEPTH_CHART"


def test_unlisted_cannot_hide_a_quarterback_the_capture_names(tmp_path):
    slate, model, contract, _unused = _setup(tmp_path)
    package = _package(tmp_path / "qb", slate, _orders())
    payload = json.loads(package.read_text(encoding="utf-8"))
    for declaration in payload["declarations"]:
        if declaration["team"] != "KC":
            continue
        # Try to demote the charted backup by calling him unlisted.
        backup = declaration["backups"].pop()
        declaration["unlisted"] = [
            {
                "underlying_id": backup["underlying_id"],
                "cpt_dk_id": backup["cpt_dk_id"],
                "flex_dk_id": backup["flex_dk_id"],
                "player_name": backup["player_name"],
            }
        ]
    package.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    with pytest.raises(QbDepthRoleError, match="QB_DEPTH_UNLISTED_IS_ON_THE_CAPTURE"):
        resolve_qb_depth_roles(slate, model, contract, evidence_path=package, as_of=AS_OF)


def test_a_declaration_the_capture_does_not_support_is_refused(tmp_path):
    slate, model, contract, _unused = _setup(tmp_path)
    package = _package(tmp_path / "qb", slate, _orders())
    payload = json.loads(package.read_text(encoding="utf-8"))
    for declaration in payload["declarations"]:
        if declaration["team"] != "KC":
            continue
        # Swap the order in the package while leaving the capture untouched.
        declaration["starter"], declaration["backups"] = (
            {**declaration["backups"][0], "pos_rank": 1},
            [{**declaration["starter"], "pos_rank": 2}],
        )
    package.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    with pytest.raises(QbDepthRoleError, match="QB_DEPTH_ORDER_NOT_SUPPORTED_BY_CAPTURE"):
        resolve_qb_depth_roles(slate, model, contract, evidence_path=package, as_of=AS_OF)


def test_a_mutated_capture_byte_withholds_the_allocation(tmp_path):
    slate, model, contract, _unused = _setup(tmp_path)
    package = _package(tmp_path / "qb", slate, _orders())
    capture = next((package.parent / "sources").glob("*.csv"))
    capture.write_text(
        capture.read_text(encoding="utf-8").replace("Quarterback", "Quarterbacks"),
        encoding="utf-8",
    )
    with pytest.raises(QbDepthRoleError, match="QB_DEPTH_SOURCE_HASH_MISMATCH"):
        resolve_qb_depth_roles(slate, model, contract, evidence_path=package, as_of=AS_OF)


def test_a_capture_mixing_two_snapshots_is_refused(tmp_path):
    slate, model, contract, _unused = _setup(tmp_path)
    package = _package(tmp_path / "qb", slate, _orders())
    payload = json.loads(package.read_text(encoding="utf-8"))
    stale = (OBSERVED - timedelta(days=1)).isoformat().replace("+00:00", "Z")
    current = OBSERVED.isoformat().replace("+00:00", "Z")
    for source in payload["sources"]:
        excerpt = source["supporting_excerpt"]
        if excerpt.count(current) < 2:
            continue
        # Backdate exactly one row, so the capture holds two snapshots.
        head, _, tail = excerpt.partition(current)
        mixed = head + stale + tail
        rows = parse_depth_chart_excerpt(mixed)
        assert len({row["dt"] for row in rows}) == 2, "fixture must actually mix two dt values"
        digest = sha256_bytes(mixed.encode("utf-8"))
        (package.parent / "sources" / f"{digest}.csv").write_bytes(mixed.encode("utf-8"))
        old = source["path"]
        source["path"] = f"sources/{digest}.csv"
        source["sha256"] = digest
        source["supporting_excerpt"] = mixed
        for declaration in payload["declarations"]:
            if declaration["source_sha256"] == old.split("/")[-1].removesuffix(".csv"):
                declaration["source_sha256"] = digest
        break
    package.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    with pytest.raises(QbDepthRoleError, match="QB_DEPTH_EXCERPT_DT_MIXED"):
        resolve_qb_depth_roles(slate, model, contract, evidence_path=package, as_of=AS_OF)


def test_a_declared_quarterback_missing_from_the_prior_package_is_refused(tmp_path):
    slate, model, contract, _unused = _setup(tmp_path)
    package = _package(tmp_path / "qb", slate, _orders())
    backup = _person(slate, "KC Backup QB")
    thinned = replace(
        model,
        players=tuple(p for p in model.players if p.underlying_id != backup),
    )
    with pytest.raises(QbDepthRoleError, match="QB_DEPTH_PRIOR_ROW_MISSING"):
        resolve_qb_depth_roles(
            slate, thinned, contract, evidence_path=package, as_of=AS_OF
        )


def test_a_name_that_is_not_the_draftkings_person_is_refused(tmp_path):
    slate, model, contract, _unused = _setup(tmp_path)
    package = _package(tmp_path / "qb", slate, _orders())
    payload = json.loads(package.read_text(encoding="utf-8"))
    for declaration in payload["declarations"]:
        if declaration["team"] == "KC":
            declaration["starter"]["player_name"] = "Somebody Else"
    package.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    with pytest.raises(QbDepthRoleError) as error:
        resolve_qb_depth_roles(slate, model, contract, evidence_path=package, as_of=AS_OF)
    assert "QB_DEPTH_PROVIDER_NAME_MISMATCH" in str(
        error.value
    ) or "QB_DEPTH_ORDER_NOT_SUPPORTED_BY_CAPTURE" in str(error.value)


def test_a_stale_snapshot_is_refused_at_the_clock_it_is_given(tmp_path):
    slate, model, contract, _unused = _setup(tmp_path)
    package = _package(tmp_path / "qb", slate, _orders(), expiry_hours=1)
    with pytest.raises(QbDepthRoleError, match="QB_DEPTH_SOURCE_STALE"):
        resolve_qb_depth_roles(slate, model, contract, evidence_path=package, as_of=AS_OF)


def test_expiry_during_selection_is_caught_before_export(tmp_path):
    slate, model, contract, _unused = _setup(tmp_path)
    package = _package(tmp_path / "qb", slate, _orders())
    resolution = resolve_qb_depth_roles(
        slate, model, contract, evidence_path=package, as_of=AS_OF
    )
    verify_qb_depth_resolution(resolution, at=AS_OF)
    with pytest.raises(QbDepthRoleError, match="QB_DEPTH_SOURCE_EXPIRED_DURING_SELECTION"):
        verify_qb_depth_resolution(resolution, at=OBSERVED + timedelta(hours=48))


def test_a_salary_file_the_package_was_not_built_for_is_refused(tmp_path):
    slate, model, contract, _unused = _setup(tmp_path)
    package = _package(tmp_path / "qb", slate, _orders())
    payload = json.loads(package.read_text(encoding="utf-8"))
    payload["salary_sha256"] = "0" * 64
    package.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    with pytest.raises(QbDepthRoleError, match="QB_DEPTH_SALARY_HASH_MISMATCH"):
        resolve_qb_depth_roles(slate, model, contract, evidence_path=package, as_of=AS_OF)


def test_no_package_leaves_the_model_untouched(tmp_path):
    slate, model, contract, _unused = _setup(tmp_path)
    resolution = resolve_qb_depth_roles(slate, model, contract, as_of=AS_OF)
    assert resolution.model is model
    assert resolution.report["evidence_state"] == "UNKNOWN"
    assert resolution.report["allocation_basis"] == "PRIOR_ONLY_HISTORICAL_ATTEMPT_SPLIT"
    assert resolution.report["schema_version"] is None


def test_an_excerpt_with_an_unexpected_header_is_refused():
    with pytest.raises(QbDepthRoleError, match="QB_DEPTH_EXCERPT_COLUMNS_UNEXPECTED"):
        parse_depth_chart_excerpt("dt,team,player_name\n2026-09-14T12:00:00Z,KC,X\n")


def test_divergence_on_an_empty_pool_is_empty(tmp_path):
    slate, _model_unused, _contract, _unused = _setup(tmp_path)
    assert salary_rank_divergence(slate, {}, None) == ()


# --- the producer ---------------------------------------------------------


def _depth_chart_file(tmp_path, rows, *, observed=OBSERVED):
    """A synthetic published-shape depth chart, including non-quarterbacks."""

    body = [
        [
            observed.isoformat().replace("+00:00", "Z"), team, name, "", gsis,
            "16", "3WR 1TE", "9", pos_name, pos_abb, "9", str(rank),
        ]
        for team, name, gsis, pos_abb, pos_name, rank in rows
    ]
    # A stale snapshot of the same teams, to prove only one `dt` is ever used.
    stale = observed - timedelta(days=2)
    body += [
        [stale.isoformat().replace("+00:00", "Z"), team, name, "", gsis,
         "16", "3WR 1TE", "9", pos_name, pos_abb, "9", str(3 - rank)]
        for team, name, gsis, pos_abb, pos_name, rank in rows
        if pos_abb == "QB"
    ]
    return _write_csv(tmp_path / "depth_charts_2026.csv", DEPTH_CHART_COLUMNS, body)


_CHART_ROWS = (
    ("KC", "KC Starter QB", "00-0033873", "QB", "Quarterback", 1),
    ("KC", "KC Backup QB", "00-0036945", "QB", "Quarterback", 2),
    ("KC", "KC Alpha WR", "00-0031111", "WR", "Wide Receiver", 1),
    ("DEN", "DEN Starter QB", "00-0034857", "QB", "Quarterback", 1),
)


def _run_producer(argv):
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "make_offensive_role_evidence",
        "scripts/make_offensive_role_evidence.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.main(argv)


def test_the_producer_builds_a_package_the_engine_accepts(tmp_path):
    slate, model, contract, _unused = _setup(tmp_path)
    chart = _depth_chart_file(tmp_path, _CHART_ROWS)
    out = tmp_path / "produced"
    assert _run_producer([
        "--salaries", str(tmp_path / "DKSalaries.csv"),
        "--capture", str(chart),
        "--source-uri", "https://github.com/nflverse/nflverse-data/releases/download"
                        "/depth_charts/depth_charts_2026.csv",
        "--as-of", AS_OF.isoformat(),
        "--out-dir", str(out),
    ]) == 0
    resolution = resolve_qb_depth_roles(
        slate, model, contract,
        evidence_path=out / "qb_depth_roles.json", as_of=AS_OF,
    )
    starter = _person(slate, "KC Starter QB")
    assert resolution.report["starters_by_team"]["KC"] == starter
    shares = {p.underlying_id: p.qb_attempt_share for p in resolution.model.players}
    assert shares[_person(slate, "KC Backup QB")] == 0.0
    assert shares[starter] == pytest.approx(1.0)


def test_the_producer_pins_one_snapshot_and_ignores_the_stale_one(tmp_path):
    _setup(tmp_path)
    chart = _depth_chart_file(tmp_path, _CHART_ROWS)
    out = tmp_path / "produced"
    assert _run_producer([
        "--salaries", str(tmp_path / "DKSalaries.csv"),
        "--capture", str(chart), "--source-uri", "https://github.com/x/y",
        "--as-of", AS_OF.isoformat(), "--out-dir", str(out),
    ]) == 0
    payload = json.loads((out / "qb_depth_roles.json").read_text(encoding="utf-8"))
    assert {d["declared_observed_at"] for d in payload["declarations"]} == {
        OBSERVED.isoformat()
    }
    for source in payload["sources"]:
        rows = parse_depth_chart_excerpt(source["supporting_excerpt"])
        assert len({row["dt"] for row in rows}) == 1


def test_the_producer_is_deterministic(tmp_path):
    _setup(tmp_path)
    chart = _depth_chart_file(tmp_path, _CHART_ROWS)
    written = []
    for index in range(2):
        out = tmp_path / f"produced{index}"
        assert _run_producer([
            "--salaries", str(tmp_path / "DKSalaries.csv"),
            "--capture", str(chart), "--source-uri", "https://github.com/x/y",
            "--as-of", AS_OF.isoformat(), "--out-dir", str(out),
        ]) == 0
        written.append((out / "qb_depth_roles.json").read_bytes())
    assert written[0] == written[1]


def test_the_producer_refuses_a_chart_whose_columns_changed(tmp_path):
    _setup(tmp_path)
    chart = _write_csv(
        tmp_path / "depth_charts_2026.csv",
        ("dt", "team", "player_name"),
        [[OBSERVED.isoformat(), "KC", "KC Starter QB"]],
    )
    assert _run_producer([
        "--salaries", str(tmp_path / "DKSalaries.csv"),
        "--capture", str(chart), "--source-uri", "https://github.com/x/y",
        "--as-of", AS_OF.isoformat(), "--out-dir", str(tmp_path / "produced"),
    ]) == 2


def test_the_producer_refuses_a_quarterback_draftkings_does_not_list(tmp_path):
    _setup(tmp_path)
    chart = _depth_chart_file(
        tmp_path,
        _CHART_ROWS + (("KC", "Somebody Else", "00-0099999", "QB", "Quarterback", 3),),
    )
    assert _run_producer([
        "--salaries", str(tmp_path / "DKSalaries.csv"),
        "--capture", str(chart), "--source-uri", "https://github.com/x/y",
        "--as-of", AS_OF.isoformat(), "--out-dir", str(tmp_path / "produced"),
    ]) == 2


def test_the_producer_refuses_a_capture_from_the_future(tmp_path):
    _setup(tmp_path)
    chart = _depth_chart_file(
        tmp_path, _CHART_ROWS, observed=AS_OF + timedelta(days=1)
    )
    assert _run_producer([
        "--salaries", str(tmp_path / "DKSalaries.csv"),
        "--capture", str(chart), "--source-uri", "https://github.com/x/y",
        "--as-of", AS_OF.isoformat(), "--out-dir", str(tmp_path / "produced"),
    ]) == 2


def test_the_stop_names_the_depth_chart_only_for_a_quarterback():
    report = {
        "findings": [
            {"person": "qb", "state": "TRANSFER_PRIOR_UNVERIFIED", "history_basis": {}},
            {"person": "rb", "state": "TRANSFER_PRIOR_UNVERIFIED", "history_basis": {}},
        ]
    }
    diverging = [
        {"person": "qb", "position": "QB", "salary": 9000, "prior_points": 1.0,
         "divergence_places": 14},
        {"person": "rb", "position": "RB", "salary": 9000, "prior_points": 1.0,
         "divergence_places": 14},
    ]
    blockers = {b.split(":")[1]: b for b in material_role_change_blockers(report, diverging)}
    assert "qb_depth_role_evidence_json" in blockers["qb"]
    assert "make_offensive_role_evidence.py" in blockers["qb"]
    assert "offensive_role_evidence_json" in blockers["rb"]
    assert "qb_depth_role_evidence_json" not in blockers["rb"]


# --- P1b: the request contract ------------------------------------------


def test_a_v1_request_still_loads_unchanged():
    from nfl_dfs.cowork import (
        COWORK_REQUEST_VERSION,
        COWORK_REQUEST_VERSION_V1,
        COWORK_REQUEST_VERSION_V2,
        SUPPORTED_REQUEST_VERSIONS,
        CoworkRunRequest,
    )

    # Session 07 emits v3 (`delivery_deadline_utc`); v1 and v2 stay accepted.
    assert COWORK_REQUEST_VERSION == "nfl_cowork_run_request_v3"
    assert COWORK_REQUEST_VERSION_V2 == "nfl_cowork_run_request_v2"
    assert COWORK_REQUEST_VERSION_V1 == "nfl_cowork_run_request_v1"
    assert SUPPORTED_REQUEST_VERSIONS == (
        COWORK_REQUEST_VERSION_V1,
        COWORK_REQUEST_VERSION_V2,
        COWORK_REQUEST_VERSION,
    )
    request = CoworkRunRequest.from_mapping(
        {"schema_version": COWORK_REQUEST_VERSION_V1, "label": "archived"}
    )
    assert request.schema_version == COWORK_REQUEST_VERSION_V1
    assert request.qb_depth_role_evidence_json is None


def test_a_v1_request_may_not_carry_the_v2_field(tmp_path):
    from nfl_dfs.cowork import COWORK_REQUEST_VERSION_V1, CoworkInputError, CoworkRunRequest

    package = tmp_path / "qb_depth_roles.json"
    package.write_text("{}", encoding="utf-8")
    with pytest.raises(CoworkInputError) as error:
        CoworkRunRequest.from_mapping(
            {
                "schema_version": COWORK_REQUEST_VERSION_V1,
                "qb_depth_role_evidence_json": str(package),
            },
            base_dir=tmp_path,
            allowed_roots=[tmp_path],
        )
    assert "introduced in 'nfl_cowork_run_request_v2'" in str(error.value)


def test_a_v2_request_carries_and_confines_the_package(tmp_path):
    from nfl_dfs.cowork import COWORK_REQUEST_VERSION_V2 as COWORK_REQUEST_VERSION
    from nfl_dfs.cowork import CoworkInputError, CoworkRunRequest

    package = tmp_path / "qb_depth_roles.json"
    package.write_text("{}", encoding="utf-8")
    request = CoworkRunRequest.from_mapping(
        {
            "schema_version": COWORK_REQUEST_VERSION,
            "qb_depth_role_evidence_json": str(package),
        },
        base_dir=tmp_path,
        allowed_roots=[tmp_path],
    )
    assert request.qb_depth_role_evidence_json == str(package.resolve())
    # The same confinement every other request path gets.
    outside = tmp_path.parent / "elsewhere.json"
    outside.write_text("{}", encoding="utf-8")
    with pytest.raises(CoworkInputError, match="outside the supplied"):
        CoworkRunRequest.from_mapping(
            {
                "schema_version": COWORK_REQUEST_VERSION,
                "qb_depth_role_evidence_json": str(outside),
            },
            base_dir=tmp_path,
            allowed_roots=[tmp_path],
        )


def test_an_unknown_schema_version_is_still_refused():
    from nfl_dfs.cowork import CoworkInputError, CoworkRunRequest

    with pytest.raises(CoworkInputError, match="unsupported Cowork request schema"):
        CoworkRunRequest.from_mapping({"schema_version": "nfl_cowork_run_request_v9"})


def test_the_package_is_bound_wherever_the_offensive_package_is():
    """Every exit that binds the sibling package must bind this one too."""

    import inspect

    from nfl_dfs import classic_review, cli, prior_review

    review_source = inspect.getsource(prior_review)
    # Artifact and hash binding, both re-verification sets, and the manifest.
    assert review_source.count('"qb_depth_role_evidence_json",') == 2
    assert review_source.count('"qb_depth_source:",') == 2
    assert '"qb_depth_role_evidence_sha256"' in review_source
    # The C3 exit binds it as an optional immutable artifact, like weather.
    assert (
        classic_review._IMMUTABLE_BINDING_ARTIFACTS["qb_depth_role_evidence_sha256"]
        == "qb_depth_role_evidence_json"
    )
    assert "qb_depth_role_evidence_json" not in classic_review._REQUIRED_ARTIFACTS
    cli_source = inspect.getsource(cli)
    assert '"--qb-depth-role-evidence-json"' in cli_source
    assert "qb_depth_role_evidence_json=request.qb_depth_role_evidence_json," in cli_source


# --- P7 / R25: the published starter is OUT and the backup inherits -------


_STARTER_OUT_POOL = tuple(
    (team, position, name, "OUT" if name == "KC Starter QB" else status, salary)
    for team, position, name, status, salary in _POOL
)


def test_a_published_starter_flagged_out_promotes_the_backup_instead_of_stopping(tmp_path):
    """R25, ruled 2026-09-20. This used to raise QB_DEPTH_STARTER_NOT_SELECTABLE.

    The refusal told the operator to refresh the depth chart after the inactive
    change. Measured on the real published artifact, the last chart before a
    13:00 ET Sunday lock is 08:14 ET and inactives publish about 11:30 ET, so
    that remedy does not exist inside the window where it is needed. Ben ruled
    it a defect; the backup inherits the job instead.
    """

    slate, model, contract, _splits_ = _setup(tmp_path, pool=_STARTER_OUT_POOL)
    package = _package(tmp_path / "qb", slate, _orders())
    resolution = resolve_qb_depth_roles(
        slate, model, contract, evidence_path=package, as_of=AS_OF
    )
    backup = _person(slate, "KC Backup QB")
    starter = _person(slate, "KC Starter QB")
    assert resolution.report["starters_by_team"]["KC"] == backup
    # Conservation is unchanged: the pool moves whole onto whoever holds the
    # job, and the person the salary bytes flag OUT keeps nothing.
    assert resolution.shares_by_person[backup] == pytest.approx(1.0)
    assert resolution.shares_by_person[starter] == 0.0


def test_every_promotion_is_named_in_the_run_record(tmp_path):
    slate, model, contract, _splits_ = _setup(tmp_path, pool=_STARTER_OUT_POOL)
    package = _package(tmp_path / "qb", slate, _orders())
    resolution = resolve_qb_depth_roles(
        slate, model, contract, evidence_path=package, as_of=AS_OF
    )
    promotions = resolution.report["effective_starter_promotions"]
    assert len(promotions) == 1
    row = promotions[0]
    assert row["team"] == "KC"
    assert row["published_starter"] == _person(slate, "KC Starter QB")
    assert row["effective_starter"] == _person(slate, "KC Backup QB")
    assert row["promoted_over"] == [_person(slate, "KC Starter QB")]
    assert row["basis"] == "SALARY_STATUS_UNAVAILABLE_ABOVE"


def test_an_ordinary_slate_reports_no_promotion(tmp_path):
    slate, model, contract, _splits_ = _setup(tmp_path)
    package = _package(tmp_path / "qb", slate, _orders())
    resolution = resolve_qb_depth_roles(
        slate, model, contract, evidence_path=package, as_of=AS_OF
    )
    assert resolution.report["effective_starter_promotions"] == []
    assert resolution.report["starters_by_team"]["KC"] == _person(slate, "KC Starter QB")


def test_an_operator_exclusion_does_not_promote_and_still_refuses(tmp_path):
    """The salary bytes still show the starter available, so nobody inherits.

    R25's bound: availability is re-derived from the bound salary bytes. An
    operator exclusion is a preference, and a preference must never be able to
    hand the job to somebody else.
    """

    slate, model, _contract, _splits_ = _setup(tmp_path)
    excluded = build_participation_contract(
        slate,
        operator_excluded_dk_ids=[
            p.dk_id for p in slate.players if p.name == "KC Starter QB"
        ],
    )
    package = _package(tmp_path / "qb", slate, _orders())
    with pytest.raises(QbDepthRoleError, match="QB_DEPTH_PROMOTION_OVER_AVAILABLE_PERSON"):
        resolve_qb_depth_roles(
            slate, model, excluded, evidence_path=package, as_of=AS_OF
        )


def test_a_team_with_no_selectable_quarterback_is_still_refused(tmp_path):
    pool = tuple(
        (team, position, name, "OUT" if team == "KC" and position == "QB" else status, salary)
        for team, position, name, status, salary in _POOL
    )
    slate, model, contract, _splits_ = _setup(tmp_path, pool=pool)
    package = _package(tmp_path / "qb", slate, _orders())
    with pytest.raises(QbDepthRoleError, match="QB_DEPTH_NO_SELECTABLE_PERSON_AT_POSITION"):
        resolve_qb_depth_roles(
            slate, model, contract, evidence_path=package, as_of=AS_OF
        )
