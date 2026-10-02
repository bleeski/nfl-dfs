"""Session 21: per-game rate shares, the transfer pool, and the version selector.

Every row is a synthetic test input. The assertions are about the
transformation: v1 still reproduces the season-count shares it always did, v2
turns a person's prior season into a per-game rate before the pool is
normalized, and the two are told apart by the version strings the package
carries. Nothing here is a model value.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path

import pytest

from nfl_dfs import priors
from nfl_dfs.hashing import sha256_file

from .test_priors_adapter import (
    AS_OF,
    _PLAYER_STAT_COLUMNS,
    _freeze,
    _player_stats_bytes,
    package,  # noqa: F401  (pytest fixture)
)

V1 = priors.PLAYER_TRANSFORMATION_V1
V2 = priors.PLAYER_TRANSFORMATION_V2

# Pinned on the pre-Session-21 code, on the base fixture and on the fixture with
# one receiver moved to another team. A v1 build must keep producing these bytes.
V1_GOLDEN_BASE = "0f05ee0d8e17975e09d3bbbc28eb61807c235e178b453936bd0f4f2b0a26d77e"
V1_GOLDEN_TRANSFER = "6ce291b8bb7885bf22ab8304dd8d911c788a1c501f7a9b811ce16e7fc85561b6"

PUKA = "00-0039337"  # LAR WR
HIGBEE = "00-0032398"  # LAR TE
KYREN = "00-0037746"  # LAR RB
JSN = "00-0038543"  # SEA WR
WALKER = "00-0037746a"  # SEA RB
BARNER = "00-0039912"  # SEA TE


def _quantized(value: Decimal) -> Decimal:
    return value.quantize(priors.QUANTUM)


def _stat(player_id, position, week, team, *, name="Synthetic", **columns):
    row = {
        "player_id": player_id,
        "player_display_name": name,
        "position": position,
        "season": "2025",
        "week": str(week),
        "season_type": "REG",
        "team": team,
        "attempts": "0",
        "carries": "0",
        "receptions": "0",
        "targets": "0",
        "receiving_yards": "0",
        "rushing_tds": "0",
        "receiving_tds": "0",
    }
    row.update({key: str(value) for key, value in columns.items()})
    return row


def _base_rows(tmp_path):
    source = tmp_path / "synthetic-player-history.csv"
    source.write_bytes(_player_stats_bytes())
    return priors.read_csv_rows(source, _PLAYER_STAT_COLUMNS, label="synthetic")


def _build(package, rows, **kwargs):
    resolved = {p.underlying_id: (p, p.provider_player_id) for p in package["proposals"]}
    return priors.build_player_records(
        package["slate"],
        resolved,
        crosswalk=package["crosswalk"],
        player_stat_rows=rows,
        snap_rows=[],
        prior_season=2025,
        season=2026,
        **kwargs,
    )


def _record(records, player_id):
    return next(r for r in records if r["provider_player_id"] == player_id)


def _history(mappings, report, player_id):
    person = next(m["underlying_id"] for m in mappings if m["provider_player_id"] == player_id)
    return report["offensive_history_by_person"][person]


def _missed_games_rows(tmp_path):
    """Puka plays 8 of 16 games and Higbee all 16, both at ten targets a game."""

    rows = [r for r in _base_rows(tmp_path) if r["player_id"] not in {PUKA, HIGBEE}]
    for week in range(1, 9):
        rows.append(_stat(PUKA, "WR", week, "LA", targets=10, receptions=6, receiving_yards=80))
    for week in range(1, 17):
        rows.append(_stat(HIGBEE, "TE", week, "LA", targets=10, receptions=6, receiving_yards=80))
    return rows


def _digest(outputs) -> str:
    return hashlib.sha256(priors.canonical_json_bytes(list(outputs))).hexdigest()


# --------------------------------------------------------------------------- #
# The selector and the frozen v1 bytes
# --------------------------------------------------------------------------- #


def test_v1_reproduces_the_pre_session_21_bytes(package, tmp_path):
    base = _base_rows(tmp_path)
    assert _digest(_build(package, base, player_transformation=V1)) == V1_GOLDEN_BASE
    transfer = [{**r, "team": "DEN"} if r["player_id"] == PUKA else r for r in base]
    assert _digest(_build(package, transfer, player_transformation=V1)) == V1_GOLDEN_TRANSFER


def test_new_packages_default_to_v3_and_without_current_rows_equal_v2(package, tmp_path):
    # Session 51 moved the default from v2 to v3. v3 is v2 for everyone v2 can
    # rate and, with no current-season rows, for everyone: the records and the
    # identity mappings are byte-identical, and the report differs only by the
    # `current_season_gap_fill` block v3 adds.
    assert priors.DEFAULT_PLAYER_TRANSFORMATION == priors.PLAYER_TRANSFORMATION_V3 != V2 != V1
    base = _base_rows(tmp_path)
    default = _build(package, base)
    v2 = _build(package, base, player_transformation=V2)
    assert _digest(default[:2]) == _digest(v2[:2])
    assert {k: v for k, v in default[2].items() if k != "current_season_gap_fill"} == v2[2]
    assert default[2]["current_season_gap_fill"]["applied"] is False
    assert _digest(default) != _digest(_build(package, base, player_transformation=V1))
    _records, mappings, report = _build(package, base, player_transformation=V2)
    history = _history(mappings, report, PUKA)
    assert history["basis_version"] == "offensive_current_team_history_v2"
    assert history["rate_basis"] == "PER_GAME_RATE_OVER_WEEKS_WITH_A_CURRENT_TEAM_ROW"
    _v1_records, v1_mappings, v1_report = _build(package, base, player_transformation=V1)
    v1_history = _history(v1_mappings, v1_report, PUKA)
    assert v1_history["basis_version"] == "offensive_current_team_history_v1"
    assert "rate_basis" not in v1_history


def test_an_unregistered_transformation_is_refused(package, tmp_path):
    with pytest.raises(priors.PriorsBuildError, match="PLAYER_TRANSFORMATION_UNKNOWN"):
        _build(package, _base_rows(tmp_path), player_transformation="FREEHAND_V3")


# --------------------------------------------------------------------------- #
# Acceptance: a player who missed games
# --------------------------------------------------------------------------- #


def test_v1_charges_the_missed_games_to_the_player_and_gives_them_to_teammates(package, tmp_path):
    records, _mappings, _report = _build(
        package, _missed_games_rows(tmp_path), player_transformation=V1
    )
    puka, higbee = _record(records, PUKA), _record(records, HIGBEE)
    # Season counts: Kyren 30, Puka 80, Higbee 160. Half the games, half the share.
    assert puka["target_weight"] == _quantized(Decimal(80) / Decimal(270))
    assert higbee["target_weight"] == _quantized(Decimal(160) / Decimal(270))
    assert puka["target_weight"] * 2 == pytest.approx(higbee["target_weight"], abs=Decimal("0.000002"))


def test_v2_projects_a_player_who_missed_games_at_his_per_game_rate(package, tmp_path):
    records, mappings, report = _build(
        package, _missed_games_rows(tmp_path), player_transformation=V2
    )
    v1_records, _m, _r = _build(package, _missed_games_rows(tmp_path), player_transformation=V1)
    puka, higbee, kyren = (_record(records, key) for key in (PUKA, HIGBEE, KYREN))
    # Rates: Kyren 30 over the four-game floor, Puka 80/8, Higbee 160/16.
    total = Decimal("7.5") + Decimal(10) + Decimal(10)
    assert puka["target_weight"] == higbee["target_weight"] == _quantized(Decimal(10) / total)
    assert kyren["target_weight"] == _quantized(Decimal("7.5") / total)
    # The teammates' shares no longer absorb the games he missed.
    assert higbee["target_weight"] < _record(v1_records, HIGBEE)["target_weight"]
    assert puka["target_weight"] > _record(v1_records, PUKA)["target_weight"]
    total_weight = sum(_record(records, key)["target_weight"] for key in (PUKA, HIGBEE, KYREN))
    assert abs(total_weight - Decimal("1")) < Decimal("0.00001")
    # Efficiency is his own ratio in either version: the rate scales both terms.
    assert puka["catch_rate"] == _record(v1_records, PUKA)["catch_rate"] == Decimal("0.6")
    history = _history(mappings, report, PUKA)
    assert (history["games"], history["effective_denominator"], history["thin_sample"]) == (8, 8, False)


def test_v2_floors_a_thin_sample_at_the_minimum_prior_games_and_says_so(package, tmp_path):
    rows = [r for r in _base_rows(tmp_path) if r["player_id"] != PUKA]
    rows += [_stat(PUKA, "WR", week, "LA", targets=10) for week in (1, 2)]
    records, mappings, report = _build(package, rows, player_transformation=V2)
    history = _history(mappings, report, PUKA)
    assert (history["games"], history["effective_denominator"]) == (2, priors.MINIMUM_PRIOR_GAMES)
    assert history["thin_sample"] is True
    # Twenty targets over four, not two: one hot game cannot outrun a starter.
    # Kyren 30 and Higbee 35 are one-row players in the base fixture, so 7.5 and 8.75.
    puka = _record(records, PUKA)["target_weight"]
    assert puka == _quantized(Decimal(5) / (Decimal(5) + Decimal("7.5") + Decimal("8.75")))


def test_v2_share_follows_the_rate_not_the_games_and_a_changed_count_is_visible(package, tmp_path):
    rows = _missed_games_rows(tmp_path)
    v2 = lambda data: _record(_build(package, data, player_transformation=V2)[0], PUKA)["target_weight"]
    v1 = lambda data: _record(_build(package, data, player_transformation=V1)[0], PUKA)["target_weight"]
    fewer = [r for r in rows if not (r["player_id"] == PUKA and r["week"] in {"7", "8"})]
    # Dropping two of his eight games takes their targets with them: the rate is
    # untouched in v2 and the season count shrinks in v1.
    assert v2(fewer) == v2(rows)
    assert v1(fewer) < v1(rows)
    # A changed input value moves the artifact (mutation).
    bumped = [
        {**r, "targets": "20"} if (r["player_id"] == PUKA and r["week"] == "1") else r for r in rows
    ]
    assert v2(bumped) > v2(rows)


def test_v2_build_is_deterministic(package, tmp_path):
    rows = _missed_games_rows(tmp_path)
    first = priors.canonical_json_bytes(list(_build(package, rows)))
    second = priors.canonical_json_bytes(list(_build(package, list(rows))))
    assert first == second


# --------------------------------------------------------------------------- #
# Acceptance: a thin-room transfer starter
# --------------------------------------------------------------------------- #


def _thin_room_rows(tmp_path, *, incumbent_targets=1, departed_targets=30):
    """SEA's receiving volume left with a departed player; JSN arrives from DEN."""

    # The base fixture parks each person's second week on DEN; drop those rows so
    # DEN's volume is exactly what this test writes.
    rows = [
        r for r in _base_rows(tmp_path)
        if r["player_id"] not in {JSN, WALKER, BARNER} and r["team"] != "DEN"
    ]
    for week in range(1, 9):
        rows.append(_stat(JSN, "WR", week, "DEN", targets=12, receptions=8, receiving_yards=100))
        rows.append(_stat("00-DENX", "WR", week, "DEN", targets=12))
        if departed_targets:
            rows.append(_stat("00-GONE", "WR", week, "SEA", targets=departed_targets))
        if incumbent_targets:
            rows.append(_stat(WALKER, "RB", week, "SEA", carries=10, targets=incumbent_targets))
            rows.append(_stat(BARNER, "TE", week, "SEA", targets=incumbent_targets))
    return rows


def test_v1_gives_a_transfer_starter_a_third_however_thin_the_room(package, tmp_path):
    records, mappings, report = _build(
        package, _thin_room_rows(tmp_path), player_transformation=V1
    )
    jsn = _record(records, JSN)
    # Half of DEN's volume, times the incumbents' eight-plus-eight targets, is 8:
    # 8 / (16 + 8), whatever the departed player left behind.
    assert jsn["target_weight"] == _quantized(Decimal(8) / Decimal(24))
    prior = _history(mappings, report, JSN)["transfer_prior"]
    assert prior["basis_version"] == "transfer_prior_own_old_team_share_v1"


def test_v2_thin_room_transfer_starter_takes_the_volume_the_room_lost(package, tmp_path):
    records, mappings, report = _build(
        package, _thin_room_rows(tmp_path), player_transformation=V2
    )
    jsn = _record(records, JSN)
    # Pseudo-rate: half of DEN's targets times SEA's 32 targets a game, so 16
    # against two incumbents at one target a game each.
    assert jsn["target_weight"] == _quantized(Decimal(16) / Decimal(18))
    prior = _history(mappings, report, JSN)["transfer_prior"]
    assert prior["basis_version"] == "transfer_prior_own_old_team_share_v2"
    assert prior["injection"] == "PSEUDO_RATE_EQUALS_OWN_OLD_SHARE_TIMES_CURRENT_TEAM_PER_GAME_TOTAL"
    assert prior["current_team_per_game_total"]["targets"] == "32"
    assert prior["own_old_share"]["targets"] == "0.5"
    assert jsn["evidence_state"] == "UNKNOWN"


def _incumbent_rows(rows, *, targets):
    for week in range(1, 9):
        rows.append(_stat(WALKER, "RB", week, "SEA", carries=10, targets=targets))
        rows.append(_stat(BARNER, "TE", week, "SEA", targets=targets))
    return rows


def test_v2_transfer_matches_v1_when_the_incumbents_carry_the_teams_volume(package, tmp_path):
    rows = _incumbent_rows(
        _thin_room_rows(tmp_path, incumbent_targets=0, departed_targets=0), targets=15
    )
    v1 = _record(_build(package, rows, player_transformation=V1)[0], JSN)["target_weight"]
    v2 = _record(_build(package, rows, player_transformation=V2)[0], JSN)["target_weight"]
    assert v1 == v2 == _quantized(Decimal(1) / Decimal(3))


def test_v2_transfer_takes_the_departed_players_volume_that_v1_ignores(package, tmp_path):
    rows = _incumbent_rows(
        _thin_room_rows(tmp_path, incumbent_targets=0, departed_targets=30), targets=15
    )
    v1 = _record(_build(package, rows, player_transformation=V1)[0], JSN)["target_weight"]
    v2 = _record(_build(package, rows, player_transformation=V2)[0], JSN)["target_weight"]
    # Team total 60 a game against 30 of incumbent rate: half of 60 is 30.
    assert v1 == _quantized(Decimal(1) / Decimal(3))
    assert v2 == _quantized(Decimal(30) / Decimal(60))


def test_v2_transfer_into_a_room_with_no_incumbent_volume_is_no_longer_zero(package, tmp_path):
    rows = _thin_room_rows(tmp_path, incumbent_targets=0)
    rows = [r for r in rows if r["player_id"] not in {WALKER, BARNER}]
    v1 = _record(_build(package, rows, player_transformation=V1)[0], JSN)
    v2 = _record(_build(package, rows, player_transformation=V2)[0], JSN)
    assert v1["target_weight"] == 0
    assert v2["target_weight"] == Decimal("1")
    assert v2["evidence_state"] == "UNKNOWN"


def test_v2_transfer_share_is_floored_like_an_incumbent_rate(package, tmp_path):
    rows = [r for r in _thin_room_rows(tmp_path) if not (r["player_id"] in {JSN, "00-DENX"} and int(r["week"]) > 2)]
    _records, mappings, report = _build(package, rows, player_transformation=V2)
    prior = _history(mappings, report, JSN)["transfer_prior"]
    # Two old-team weeks over a four-game floor halves the share: 0.5 x 2/4.
    assert prior["old_team_weeks"] == 2
    assert prior["effective_old_team_weeks"] == priors.MINIMUM_PRIOR_GAMES
    assert prior["own_old_share"]["targets"] == "0.25"
    assert prior["thin_sample"] is True


# --------------------------------------------------------------------------- #
# The freeze carries the version it used
# --------------------------------------------------------------------------- #


def _player_metadata(result):
    payload = json.loads(open(result["player_source"], encoding="utf-8").read())
    return payload["metadata"]["coverage"]


def test_freeze_records_the_transformation_it_used(package, tmp_path):
    default = _freeze(package, tmp_path, name="default")
    explicit_v2 = _freeze(package, tmp_path, name="v2", player_transformation=V2)
    explicit_v1 = _freeze(package, tmp_path, name="v1", player_transformation=V1)
    assert _player_metadata(default)["transformation"] == priors.PLAYER_TRANSFORMATION_V3
    assert _player_metadata(explicit_v2)["transformation"] == V2
    assert _player_metadata(explicit_v1)["transformation"] == V1
    assert _player_metadata(default)["transformation_does_not_establish"]
    assert "RECENCY_WEIGHT" in _player_metadata(default)["transformation_does_not_establish"]
    assert _player_metadata(explicit_v2)["transformation_does_not_establish"]
    assert "transformation_does_not_establish" not in _player_metadata(explicit_v1)
    # This fixture's package has no in-season file, so v3 says so and rates as v2.
    assert _player_metadata(default)["current_season_stats"]["status"] == "ABSENT"
    for result in (default, explicit_v2, explicit_v1):
        assert result["MODEL_STATUS"] == "PRIOR_ONLY"
        assert result["status"] == "DO_NOT_UPLOAD"


def test_freeze_is_deterministic_and_the_v1_read_path_still_projects(package, tmp_path):
    first = _freeze(package, tmp_path, name="one")
    second = _freeze(package, tmp_path, name="two")
    assert sha256_file(first["player_source"]) == sha256_file(second["player_source"])
    # A v1 package is read as written by the same projection path as v2.
    from nfl_dfs.projection import build_projection_package

    for name in ("v1", "v2"):
        frozen = _freeze(
            package, tmp_path, name=f"proj_{name}", player_transformation=V1 if name == "v1" else V2
        )
        projected = build_projection_package(
            salaries=package["salary"],
            salary_sha256=package["salary_digest"],
            team_source=frozen["team_source"],
            team_source_sha256=sha256_file(frozen["team_source"]),
            player_source=frozen["player_source"],
            player_source_sha256=sha256_file(frozen["player_source"]),
            identity_map=frozen["identity_map"],
            identity_map_sha256=sha256_file(frozen["identity_map"]),
            as_of=AS_OF,
            output_dir=tmp_path / f"projected_{name}",
        )
        rows = Path(projected.player_opportunities).read_text(encoding="utf-8").splitlines()
        assert len(rows) > 1
        assert sha256_file(frozen["player_source"]) in projected.input_hashes.values()
