"""Session 51 (R35): the v3 current-season gap-fill.

Every row is a synthetic test input. The assertions are about the transformation:
v3 rates only the people v2 cannot rate (no prior-season row, a historically zero
person, a transfer with rows on his new team) from this season's current-team rows
played before the slate's week, and leaves everyone else exactly as v2 wrote them.
A row at or after the slate's week is never read, a team with a completed game
missing from the file falls back to v2 by name, a number that cannot be taken from
the bound rows is refused and named, and nothing is clamped. Nothing here is a model
value, and nothing here establishes a role.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from nfl_dfs import priors
from nfl_dfs.hashing import sha256_file
from nfl_dfs.offensive_roles import FIELDS
from nfl_dfs.participation import build_participation_contract
from nfl_dfs.selection import select_prior_lineups
from nfl_dfs.sources import SourceDeadlineError, SourcePolicyError

from . import test_priors_adapter as adapter
from .test_offensive_roles import _setup
from .test_prior_rate_transformation import (
    BARNER,
    HIGBEE,
    JSN,
    KYREN,
    PUKA,
    WALKER,
    _base_rows,
    _build,
    _history,
    _quantized,
    _record,
    _stat,
)
from .test_priors_adapter import (  # noqa: F401  (pytest fixture)
    AS_OF,
    _PLAYER_STAT_COLUMNS,
    _csv_bytes,
    _freeze,
    package,
)

V2 = priors.PLAYER_TRANSFORMATION_V2
V3 = priors.PLAYER_TRANSFORMATION_V3
STAFFORD = "00-0026498"  # LAR QB
DARNOLD = "00-0034869"  # SEA QB
SLATE_WEEK = 4
BEFORE = (1, 2, 3)
WEEKS = {"LA": BEFORE, "SEA": BEFORE}


def _current(player_id, position, week, team, **columns):
    return _stat(player_id, position, week, team, season="2026", **columns)


def _team_fillers(teams=("LA", "SEA"), weeks=BEFORE):
    """One quarterback row per team-week, so each team's completed games are present.

    Both quarterbacks have prior-season rows, so v3 never gap-fills them.
    """

    anchor = {"LA": (STAFFORD, "QB"), "SEA": (DARNOLD, "QB")}
    return [
        _current(anchor[team][0], anchor[team][1], week, team, attempts=30)
        for team in teams
        for week in weeks
    ]


def _without_prior(tmp_path, *player_ids):
    return [r for r in _base_rows(tmp_path) if r["player_id"] not in set(player_ids)]


def _v3(package, prior_rows, current_rows, **kwargs):
    return _build(
        package,
        prior_rows,
        player_transformation=V3,
        current_season_rows=current_rows,
        slate_week=kwargs.pop("slate_week", SLATE_WEEK),
        team_weeks_before_slate_by_team=kwargs.pop("weeks", WEEKS),
        **kwargs,
    )


def _puka_rows(*weeks, targets=(8, 9, 10), receptions=(5, 6, 7), yards=(70, 80, 90)):
    return [
        _current(PUKA, "WR", week, "LA", targets=t, receptions=r, receiving_yards=y)
        for week, t, r, y in zip(weeks, targets, receptions, yards)
    ]


# --------------------------------------------------------------------------- #
# Acceptance 1: nothing changes for anyone v2 can rate
# --------------------------------------------------------------------------- #


def test_current_rows_at_or_after_the_slate_week_change_no_record(package, tmp_path):
    prior = _base_rows(tmp_path)
    v2 = _build(package, prior, player_transformation=V2)
    leak = [_current(PUKA, "WR", SLATE_WEEK, "LA", targets=40, receptions=30, receiving_yards=400)]
    v3 = _v3(package, prior, _team_fillers() + leak)
    assert v3[0] == v2[0] and v3[1] == v2[1]
    assert v3[2]["current_season_gap_fill"]["people"] == []


def test_a_person_v2_can_rate_keeps_his_prior_season_rate_even_with_current_rows(package, tmp_path):
    # Puka has a prior-season row. Three huge current-season games must not move
    # him: v3 is a gap-fill, so no recency weight exists for a veteran.
    prior = _base_rows(tmp_path)
    v2 = _build(package, prior, player_transformation=V2)
    hot = _puka_rows(1, 2, 3, targets=(30, 30, 30), receptions=(20, 20, 20), yards=(300, 300, 300))
    v3 = _v3(package, prior, _team_fillers() + hot)
    assert v3[0] == v2[0] and v3[1] == v2[1]
    assert _history(v3[1], v3[2], PUKA)["basis_version"] == "offensive_current_team_history_v2"


# --------------------------------------------------------------------------- #
# Acceptance 2: a person with no prior-season row, rated from three current games
# --------------------------------------------------------------------------- #


def test_a_rookie_receiver_with_three_current_games_is_rated_and_named_thin(package, tmp_path):
    prior = _without_prior(tmp_path, PUKA)
    v2_records, v2_mappings, v2_report = _build(package, prior, player_transformation=V2)
    assert _history(v2_mappings, v2_report, PUKA)["state"] == "MISSING_HISTORY"
    assert _record(v2_records, PUKA)["target_weight"] == 0

    records, mappings, report = _v3(package, prior, _team_fillers() + _puka_rows(*BEFORE))
    history = _history(mappings, report, PUKA)
    assert history["state"] == "OBSERVED_HISTORY"
    assert history["history_source"] == "CURRENT_SEASON_GAP_FILL"
    assert history["gap_fill_from_state"] == "MISSING_HISTORY"
    assert (history["games"], history["games_floor"], history["effective_denominator"]) == (3, 3, 3)
    assert history["thin_sample"] is True  # three games is under v2's four
    assert (history["slate_week"], history["through_week"]) == (SLATE_WEEK, 3)
    # 27 targets over three games is nine a game, beside Kyren's 7.5 and Higbee's 8.75.
    puka = _record(records, PUKA)
    assert puka["target_weight"] == _quantized(Decimal(9) / Decimal("25.25"))
    assert puka["catch_rate"] == _quantized(Decimal(18) / Decimal(27))
    assert puka["evidence_state"] == "PASS"
    assert report["current_season_gap_fill"]["people"] and report["current_season_gap_fill"]["applied"]
    # Teammates' shares now share the pool with him; the other team is untouched.
    for player in (JSN, WALKER, BARNER):
        assert _record(records, player) == _record(v2_records, player)


def test_a_quarterback_with_no_prior_row_is_rated_from_current_attempts(package, tmp_path):
    prior = _without_prior(tmp_path, STAFFORD)
    v2_records, v2_mappings, v2_report = _build(package, prior, player_transformation=V2)
    assert _history(v2_mappings, v2_report, STAFFORD)["state"] == "MISSING_HISTORY"
    assert _record(v2_records, STAFFORD)["qb_attempt_weight"] == 0
    current = [
        _current(STAFFORD, "QB", week, "LA", attempts=attempts, carries=3)
        for week, attempts in zip(BEFORE, (22, 30, 30))
    ]
    current += _team_fillers(teams=("SEA",))
    records, mappings, report = _v3(package, prior, current)
    history = _history(mappings, report, STAFFORD)
    assert history["state"] == "OBSERVED_HISTORY" and history["games"] == 3
    # He is the only quarterback the team lists, so the pool is his.
    assert _record(records, STAFFORD)["qb_attempt_weight"] == Decimal("1.000000")


def test_a_transfer_with_rows_on_his_new_team_is_no_longer_a_transfer(package, tmp_path):
    prior = [{**r, "team": "DEN"} if r["player_id"] == PUKA else r for r in _base_rows(tmp_path)]
    prior = [r for r in prior if not (r["player_id"] == PUKA and r["team"] == "LA")]
    _r, mappings, report = _build(package, prior, player_transformation=V2)
    assert _history(mappings, report, PUKA)["state"] == "CURRENT_ROLE_UNKNOWN"
    records, mappings, report = _v3(package, prior, _team_fillers() + _puka_rows(*BEFORE))
    history = _history(mappings, report, PUKA)
    assert history["state"] == "OBSERVED_HISTORY"
    assert history["gap_fill_from_state"] == "CURRENT_ROLE_UNKNOWN"
    assert history["incompatible_transfer"] is False
    assert "transfer_prior" not in history  # his old-team share is never used beside real rows
    assert _record(records, PUKA)["target_weight"] > 0


# --------------------------------------------------------------------------- #
# Acceptance 3: no look-ahead
# --------------------------------------------------------------------------- #


def test_a_person_whose_only_row_is_the_slate_week_stays_excluded_and_says_why(package, tmp_path):
    prior = _without_prior(tmp_path, PUKA)
    own_game = _puka_rows(SLATE_WEEK, targets=(34,), receptions=(20,), yards=(250,))
    records, mappings, report = _v3(package, prior, _team_fillers() + own_game)
    history = _history(mappings, report, PUKA)
    assert history["state"] == "MISSING_HISTORY"
    assert history["gap_fill_refused"] == priors.GAP_FILL_REFUSED_LOOK_AHEAD
    assert _record(records, PUKA)["target_weight"] == 0
    assert report["current_season_gap_fill"]["refused"][next(iter(report["current_season_gap_fill"]["refused"]))] == (
        "CURRENT_SEASON_ROW_AT_OR_AFTER_SLATE_WEEK"
    )


def test_rows_at_or_after_the_slate_week_are_ignored_beside_earlier_ones(package, tmp_path):
    prior = _without_prior(tmp_path, PUKA)
    earlier = _puka_rows(1, 2, 3)
    later = _puka_rows(SLATE_WEEK, 5, targets=(40, 40), receptions=(30, 30), yards=(400, 400))
    with_later = _v3(package, prior, _team_fillers() + earlier + later)
    without = _v3(package, prior, _team_fillers() + earlier)
    assert with_later[0] == without[0]
    assert _history(with_later[1], with_later[2], PUKA)["ignored_rows_at_or_after_slate_week"] == 2


# --------------------------------------------------------------------------- #
# Acceptance 4: the season is part of every key
# --------------------------------------------------------------------------- #


def test_a_prior_season_week_does_not_stand_in_for_a_current_season_week(package, tmp_path):
    prior = _without_prior(tmp_path, PUKA)
    # LA's file carries week 1 and 3 as 2026 rows and a *2025* week 2 row: week 2
    # of this season is missing, whatever the other season holds.
    rows = [
        _current(STAFFORD, "QB", 1, "LA", attempts=30),
        _stat(STAFFORD, "QB", 2, "LA", season="2025", attempts=30),
        _current(STAFFORD, "QB", 3, "LA", attempts=30),
    ] + _team_fillers(teams=("SEA",)) + _puka_rows(
        1, 3, targets=(8, 10), receptions=(5, 7), yards=(70, 90)
    )
    present = priors.current_season_weeks_present(rows, season=2026, slate_week=SLATE_WEEK)
    assert present["LA"] == {1, 3}
    _r, mappings, report = _v3(package, prior, rows)
    history = _history(mappings, report, PUKA)
    assert history["gap_fill_refused"] == "CURRENT_SEASON_STATS_INCOMPLETE:LA:2"
    assert history["state"] == "MISSING_HISTORY"


def test_a_player_with_a_2025_and_a_2026_week_three_counts_each_once(package, tmp_path):
    # Puka's only prior row is a 2025 week 3 on DEN; his 2026 week 3 is on LA.
    prior = [r for r in _base_rows(tmp_path) if r["player_id"] != PUKA]
    prior.append(_stat(PUKA, "WR", 3, "DEN", targets=12, receptions=8, receiving_yards=100))
    current = _team_fillers() + _puka_rows(1, 2, 3)
    _r, mappings, report = _v3(package, prior, current)
    history = _history(mappings, report, PUKA)
    assert history["gap_fill_from_state"] == "CURRENT_ROLE_UNKNOWN"
    assert history["weeks"] == [1, 2, 3] and history["games"] == 3


# --------------------------------------------------------------------------- #
# Acceptance 5: a thin sample never fails the build
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("targets", "receptions", "yards"),
    [(1, 1, 77), (1, 0, -2), (1, 2, 10)],
    ids=["yards-per-target-over-30", "negative-yards", "catch-rate-over-1"],
)
def test_an_out_of_range_efficiency_is_a_named_finding_not_a_build_failure(
    package, tmp_path, targets, receptions, yards
):
    prior = _without_prior(tmp_path, PUKA)
    current = _team_fillers() + [
        _current(PUKA, "WR", 1, "LA", targets=targets, receptions=receptions, receiving_yards=yards)
    ]
    records, mappings, report = _v3(package, prior, current)
    history = _history(mappings, report, PUKA)
    assert history["state"] == "MISSING_HISTORY"
    assert history["gap_fill_refused"] == priors.GAP_FILL_REFUSED_EFFICIENCY
    assert _record(records, PUKA)["yards_per_target"] == 0  # nothing was clamped into his record


def test_missing_cells_and_all_zero_rows_are_refused_by_name(package, tmp_path):
    prior = _without_prior(tmp_path, PUKA, HIGBEE)
    current = _team_fillers() + [
        _current(PUKA, "WR", 1, "LA", targets=5, receptions="NA", receiving_yards=40),
        _current(HIGBEE, "TE", 1, "LA"),
    ]
    _records, mappings, report = _v3(package, prior, current)
    assert _history(mappings, report, PUKA)["gap_fill_refused"] == priors.GAP_FILL_REFUSED_INCOMPLETE_ROW
    assert _history(mappings, report, HIGBEE)["gap_fill_refused"] == priors.GAP_FILL_REFUSED_ALL_ZERO


# --------------------------------------------------------------------------- #
# Acceptance 6: a team with a missing game falls back to v2 by name
# --------------------------------------------------------------------------- #


def test_a_team_missing_a_completed_game_falls_back_to_v2_and_the_other_team_still_fills(
    package, tmp_path
):
    prior = _without_prior(tmp_path, PUKA, JSN)
    la_without_week_two = [
        _current(STAFFORD, "QB", week, "LA", attempts=30) for week in (1, 3)
    ]
    current = (
        la_without_week_two
        + _team_fillers(teams=("SEA",))
        + _puka_rows(1, 3, targets=(8, 10), receptions=(5, 7), yards=(70, 90))
        + [
            _current(JSN, "WR", week, "SEA", targets=8, receptions=6, receiving_yards=70)
            for week in BEFORE
        ]
    )
    records, mappings, report = _v3(package, prior, current)
    assert _history(mappings, report, PUKA)["gap_fill_refused"] == "CURRENT_SEASON_STATS_INCOMPLETE:LA:2"
    assert _record(records, PUKA)["target_weight"] == 0
    assert _history(mappings, report, JSN)["state"] == "OBSERVED_HISTORY"
    assert _record(records, JSN)["target_weight"] > 0


# --------------------------------------------------------------------------- #
# The floor
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("team_games", "played", "floor", "effective"),
    [(3, (1, 2, 3), 3, 3), (3, (2,), 3, 3), (8, (1, 2, 3), 4, 4), (1, (1,), 1, 1)],
)
def test_the_floor_is_the_smaller_of_four_and_the_teams_completed_games(
    package, tmp_path, team_games, played, floor, effective
):
    weeks = tuple(range(1, team_games + 1))
    prior = _without_prior(tmp_path, PUKA)
    current = _team_fillers(weeks=weeks) + _puka_rows(
        *played, targets=(8,) * len(played), receptions=(5,) * len(played), yards=(70,) * len(played)
    )
    _r, mappings, report = _v3(
        package, prior, current, slate_week=team_games + 1, weeks={"LA": weeks, "SEA": weeks}
    )
    history = _history(mappings, report, PUKA)
    assert (history["games_floor"], history["effective_denominator"]) == (floor, effective)
    assert history["team_games_before_slate"] == team_games


# --------------------------------------------------------------------------- #
# The helpers
# --------------------------------------------------------------------------- #


def test_team_weeks_before_the_slate_come_from_regular_season_games_only():
    header = ("game_id", "season", "game_type", "week", "away_team", "home_team")
    rows = [
        dict(zip(header, ("g1", "2026", "REG", "1", "LA", "DEN"))),
        dict(zip(header, ("g2", "2026", "REG", "3", "SEA", "LA"))),
        dict(zip(header, ("g3", "2026", "REG", "4", "LA", "SEA"))),  # the slate's own week
        dict(zip(header, ("g4", "2025", "REG", "2", "LA", "SEA"))),  # another season
        dict(zip(header, ("g5", "2026", "POST", "2", "LA", "SEA"))),  # not regular season
    ]
    weeks = priors.team_weeks_before_slate(rows, season=2026, slate_week=4)
    assert weeks == {"DEN": (1,), "LA": (1, 3), "SEA": (3,)}


# --------------------------------------------------------------------------- #
# The optional source
# --------------------------------------------------------------------------- #


def _spec(name, *, optional):
    return priors.NflverseSource(
        name=name,
        url=f"https://github.com/nflverse/nflverse-data/releases/download/x/{name}.csv",
        parser_version="test_v1",
        expires_after=priors.timedelta(hours=1),
        staleness_basis="TEST",
        required_columns=("a",),
        optional=optional,
    )


def test_an_optional_source_that_cannot_be_fetched_is_named_absent(tmp_path, monkeypatch):
    def refuse(url, *args, **kwargs):
        raise RuntimeError("HTTP 404 Not Found")

    monkeypatch.setattr(priors, "fetch_public_artifact", refuse)
    absent: list[dict[str, str]] = []
    frozen = priors.freeze_sources(
        [_spec("player_stats_current", optional=True)],
        package_root=tmp_path / "pkg",
        as_of=priors._parse_timestamp(AS_OF, label="AS_OF"),
        absent=absent,
    )
    assert frozen == {}
    assert absent == [{"name": "player_stats_current", "reason": "RuntimeError:HTTP 404 Not Found"}]


def test_a_required_source_that_cannot_be_fetched_still_fails_the_build(tmp_path, monkeypatch):
    def refuse(url, *args, **kwargs):
        raise RuntimeError("HTTP 404 Not Found")

    monkeypatch.setattr(priors, "fetch_public_artifact", refuse)
    with pytest.raises(RuntimeError):
        priors.freeze_sources(
            [_spec("player_stats", optional=False)],
            package_root=tmp_path / "pkg",
            as_of=priors._parse_timestamp(AS_OF, label="AS_OF"),
            absent=[],
        )


@pytest.mark.parametrize("error", [SourcePolicyError("prohibited"), SourceDeadlineError("spent")])
def test_a_policy_refusal_or_spent_deadline_is_never_an_absence(tmp_path, monkeypatch, error):
    def refuse(url, *args, **kwargs):
        raise error

    monkeypatch.setattr(priors, "fetch_public_artifact", refuse)
    with pytest.raises(type(error)):
        priors.freeze_sources(
            [_spec("player_stats_current", optional=True)],
            package_root=tmp_path / "pkg",
            as_of=priors._parse_timestamp(AS_OF, label="AS_OF"),
            absent=[],
        )


# --------------------------------------------------------------------------- #
# The freeze carries what the in-season file contributed
# --------------------------------------------------------------------------- #


def _games_with_week_one() -> bytes:
    header = (
        "game_id", "season", "game_type", "week", "gameday", "away_team", "home_team",
        "spread_line", "total_line", "roof", "home_score",
    )
    rows = [
        ("2026_01_DEN_LA", "2026", "REG", "1", "2026-09-06", "DEN", "LA", "-3.5", "44.5", "dome", "21"),
        ("2026_01_SEA_ARI", "2026", "REG", "1", "2026-09-06", "SEA", "ARI", "-3.5", "44.5", "dome", "17"),
        ("2026_02_LA_SEA", "2026", "REG", "2", "2026-09-13", "LA", "SEA", "-3.5", "44.5", "dome", ""),
        ("2026_02_DAL_NYG", "2026", "REG", "2", "2026-09-13", "DAL", "NYG", "3", "48.5", "outdoors", ""),
    ]
    return _csv_bytes(header, rows)


def _prior_without_puka() -> bytes:
    kept = [
        row
        for row in priors.csv.DictReader(adapter._player_stats_bytes().decode("utf-8").splitlines())
        if row["player_id"] != PUKA
    ]
    return _csv_bytes(_PLAYER_STAT_COLUMNS, [tuple(row[c] for c in _PLAYER_STAT_COLUMNS) for row in kept])


def _current_file(*, include_sea_week_one: bool = True) -> bytes:
    rows = [
        (STAFFORD, "Matthew Stafford", "QB", "2026", "1", "REG", "LA", "30", "0", "0", "0", "0", "0", "0"),
        (PUKA, "Puka Nacua", "WR", "2026", "1", "REG", "LA", "0", "0", "6", "9", "80", "0", "1"),
    ]
    if include_sea_week_one:
        rows.append(
            (DARNOLD, "Sam Darnold", "QB", "2026", "1", "REG", "SEA", "28", "0", "0", "0", "0", "0", "0")
        )
    return _csv_bytes(_PLAYER_STAT_COLUMNS, rows)


@pytest.fixture
def current_source(monkeypatch):
    """Put a games file with a week 1 and an in-season file into the fixture's sources."""

    monkeypatch.setitem(adapter._SOURCE_BYTES, "games", _games_with_week_one)
    monkeypatch.setitem(adapter._SOURCE_BYTES, "player_stats", _prior_without_puka)
    monkeypatch.setitem(adapter._SOURCE_BYTES, "player_stats_current", _current_file)


def test_a_bound_in_season_file_rates_a_person_with_no_prior_row_and_is_recorded(
    current_source, package, tmp_path
):
    frozen = _freeze(package, tmp_path, name="v3")
    coverage = priors_player_coverage(frozen)
    stats = coverage["current_season_stats"]
    assert stats["status"] == "BOUND"
    assert (stats["slate_week"], stats["through_week"]) == (2, 1)
    assert stats["read_rule"] == "ROWS_WITH_WEEK_BEFORE_THE_SLATE_WEEK_ONLY"
    assert stats["team_games_before_slate"] == {"LA": 1, "SEA": 1}
    assert stats["incomplete_teams"] == {}
    assert "RECENCY_WEIGHT" in coverage["transformation_does_not_establish"]
    history = coverage["offensive_history_by_person"]
    puka = next(v for k, v in history.items() if k.endswith("Puka Nacua"))
    assert puka["state"] == "OBSERVED_HISTORY" and puka["history_source"] == "CURRENT_SEASON_GAP_FILL"
    assert (puka["games"], puka["games_floor"], puka["thin_sample"]) == (1, 1, True)
    assert coverage["current_season_gap_fill"]["people"]
    # The in-season file is one of the sources the artifact's expiry rests on.
    assert "player_stats_current" in coverage["contributing_artifacts"]


def test_two_freezes_with_the_in_season_file_are_byte_identical_and_a_changed_byte_moves_the_hash(
    current_source, package, tmp_path, monkeypatch
):
    first = _freeze(package, tmp_path, name="det_one")
    second = _freeze(package, tmp_path, name="det_two")
    assert sha256_file(first["player_source"]) == sha256_file(second["player_source"])
    # Change one byte of the in-season file and rebuild the package on it: the
    # player artifact must change, because the rate rests on those bytes.
    def mutated() -> bytes:
        return _current_file().replace(b",9,80,", b",9,81,")

    monkeypatch.setitem(adapter._SOURCE_BYTES, "player_stats_current", mutated)
    rebuilt = _rebuild_package(package, tmp_path)
    third = _freeze(rebuilt, tmp_path, name="det_mutated")
    assert sha256_file(third["player_source"]) != sha256_file(first["player_source"])


def test_an_incomplete_in_season_file_is_named_per_team(monkeypatch, package, tmp_path):
    monkeypatch.setitem(adapter._SOURCE_BYTES, "games", _games_with_week_one)
    monkeypatch.setitem(adapter._SOURCE_BYTES, "player_stats", _prior_without_puka)
    monkeypatch.setitem(adapter._SOURCE_BYTES, "player_stats_current", lambda: _current_file(include_sea_week_one=False))
    # `package` was built before the monkeypatch took effect in this test, so
    # rebuild it through the same helper the fixture uses.
    rebuilt = _rebuild_package(package, tmp_path)
    frozen = _freeze(rebuilt, tmp_path, name="v3_incomplete")
    stats = priors_player_coverage(frozen)["current_season_stats"]
    assert stats["status"] == "BOUND"
    assert stats["incomplete_teams"] == {"SEA": "CURRENT_SEASON_STATS_INCOMPLETE:SEA:1"}


def test_a_package_without_the_in_season_file_says_so_and_rates_as_v2(package, tmp_path):
    coverage = priors_player_coverage(_freeze(package, tmp_path, name="absent"))
    assert coverage["current_season_stats"]["status"] == "ABSENT"
    assert coverage["current_season_stats"]["limitation"] == "CURRENT_SEASON_STATS_ABSENT"
    assert coverage["current_season_gap_fill"] == {
        "basis_version": "current_season_gap_fill_v1",
        "slate_week": 2,
        "applied": False,
        "people": [],
        "refused": {},
    }


def priors_player_coverage(frozen):
    import json

    payload = json.loads(Path(frozen["player_source"]).read_text(encoding="utf-8"))
    coverage = payload["metadata"]["coverage"]
    return coverage


def _rebuild_package(package, tmp_path):
    """The `package` fixture's work again, now that the sources have been patched."""

    root = adapter._write_package(tmp_path / "proposal_rebuilt", salary_digest=package["salary_digest"])
    from nfl_dfs.contracts import EngineMode  # noqa: F401
    from nfl_dfs.priors import propose_identities, resolve_team_crosswalk

    slate = package["slate"]
    teams_rows = priors.read_csv_rows(
        (root / priors.RAW_DIRNAME) / adapter._named(root, "teams"),
        ("season", "team", "full", "nickname", "draft_kings"),
        label="teams",
    )
    crosswalk = resolve_team_crosswalk(slate, teams_rows, season=2026)
    roster_rows = priors.read_csv_rows(
        (root / priors.RAW_DIRNAME) / adapter._named(root, "weekly_rosters"),
        adapter._ROSTER_COLUMNS,
        label="weekly_rosters",
    )
    index_rows = priors.read_csv_rows(
        (root / priors.RAW_DIRNAME) / adapter._named(root, "players"),
        adapter._PLAYERS_COLUMNS,
        label="players",
    )
    proposals = propose_identities(slate, roster_rows, crosswalk, season=2026, player_index_rows=index_rows)
    manifest_hash = sha256_file(root / priors.MANIFEST_FILENAME)
    payload = {
        "schema_version": priors.PROPOSAL_SCHEMA,
        "adapter_version": priors.ADAPTER_VERSION,
        "as_of": AS_OF,
        "season": 2026,
        "salary_artifact_id": package["salary_digest"],
        "source_manifest_sha256": manifest_hash,
        "authoritative": False,
        "note": "test proposal",
        "proposals": [item.as_payload() for item in proposals],
    }
    (root / priors.PROPOSAL_FILENAME).write_bytes(priors.canonical_json_bytes(payload))
    review = root / priors.REVIEW_FILENAME
    review.write_bytes(priors.review_csv_bytes(proposals))
    return {**package, "root": root, "review": review, "proposals": proposals, "crosswalk": crosswalk}


# --------------------------------------------------------------------------- #
# The role gate
# --------------------------------------------------------------------------- #


def test_a_gap_filled_person_is_scored_and_the_finding_says_it_is_not_a_role(tmp_path):
    slate, model, contract, splits = _setup(tmp_path)
    person = "NE|RB|Backup RB"
    history = {
        "state": "OBSERVED_HISTORY",
        "incompatible_transfer": False,
        "history_source": "CURRENT_SEASON_GAP_FILL",
        "gap_fill_from_state": "MISSING_HISTORY",
        "games": 3,
        "games_floor": 3,
        "through_week": 3,
        "thin_sample": True,
    }
    model = replace(model, offensive_history_by_person={person: history})
    _lineups, scores, report = select_prior_lineups(slate, model, splits, contract, count=1)
    assert person in scores.by_person
    finding = next(f for f in report["offensive_roles"]["findings"] if f["person"] == person)
    assert finding["selection_action"] == "DIAGNOSTIC"
    assert finding["history_basis"]["history_source"] == "CURRENT_SEASON_GAP_FILL"
    assert "3 current-season game(s) through week 3" in finding["next_evidence_action"]
    assert "not a current role" in finding["next_evidence_action"]
    assert any("CURRENT_SEASON_GAP_FILL" in a for a in report["offensive_roles"]["assumptions"])
    assert report["offensive_roles"]["evidence_state"] == "UNKNOWN"


def test_a_refused_gap_fill_names_its_refusal_on_the_exclusion(tmp_path):
    slate, model, contract, splits = _setup(tmp_path)
    person = "NE|RB|Backup RB"
    model = replace(
        model,
        offensive_history_by_person={
            person: {
                "state": "MISSING_HISTORY",
                "incompatible_transfer": False,
                "gap_fill_refused": "CURRENT_SEASON_ROW_AT_OR_AFTER_SLATE_WEEK",
            }
        },
    )
    _lineups, scores, report = select_prior_lineups(slate, model, splits, contract, count=1)
    assert person not in scores.by_person
    finding = next(f for f in report["offensive_roles"]["findings"] if f["person"] == person)
    assert finding["finding"] == "OFFENSIVE_MISSING_HISTORY"
    assert finding["selection_action"] == "EXCLUDE"
    assert "CURRENT_SEASON_ROW_AT_OR_AFTER_SLATE_WEEK" in finding["next_evidence_action"]
