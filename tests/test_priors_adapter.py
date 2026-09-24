"""W1 / R01 coverage for the deterministic nflverse prior adapter.

Every fixture here is a test input, not a model value: the CSV rows are tiny
hand-built stand-ins for the frozen nflverse artifacts, and the assertions are
about the transformation, the identity gate and the fail-closed behaviour. No
test touches the network.
"""

from __future__ import annotations

import csv
import io
import json
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from nfl_dfs import priors
from nfl_dfs.dk import parse_salaries
from nfl_dfs.hashing import sha256_file
from nfl_dfs.priors import (
    PriorsBuildError,
    canonical_json_bytes,
    freeze_prior_package,
    normalize_person_name,
    propose_identities,
    resolve_team_crosswalk,
    resolve_weather_state,
)
from nfl_dfs.projection import build_projection_package
from nfl_dfs.sources import (
    SourcePolicyError,
    is_github_release_download,
    resolve_github_release_redirect,
)


# AS_OF is slate time, not wall-clock time: it is a fixed point inside this
# module's own synthetic LAR@SEA slate, and it has to stay before that slate's
# lock for the expiry assertions below to mean anything.
AS_OF = "2026-09-13T14:00:00+00:00"
CAPTURED = datetime(2026, 9, 13, 13, 0, tzinfo=timezone.utc)
GAME_INFO = "LAR@SEA 09/13/2026 04:25PM ET"

# P3-17. A salary file written into `tmp_path` carries an mtime of "now", and
# `_salary_timestamp` reads that mtime as the operator's observation whenever no
# download time was stated. Comparing a wall-clock observation against a frozen
# AS_OF is a clock that expires: at 10:00am ET on 2026-09-13 real time crossed
# AS_OF and eighteen tests in this module began failing
# SALARY_OBSERVATION_IN_FUTURE with no engine defect behind any of them, costing
# five minutes to prove innocent on slate day.
#
# The fix is to stamp the observation rather than inherit the wall clock, so
# these tests read the same on any date. AS_OF itself stays a constant because
# the slate it describes is one: rebasing it onto "today" would drift the season
# the adapter resolves and silently change which fixture rows are in scope.
SALARY_OBSERVED_AT = datetime.fromisoformat(AS_OF) - timedelta(hours=2)


def _write_salary(path: Path, payload: bytes | None = None) -> Path:
    """Write salary bytes with a deterministic observation time."""

    path.write_bytes(_salary_bytes() if payload is None else payload)
    stamp = SALARY_OBSERVED_AT.timestamp()
    os.utime(path, (stamp, stamp))
    return path

# DraftKings writes LAR where nflverse writes LA. Using that pair on purpose:
# it is the case a naive abbreviation match gets wrong.
_ROSTER = (
    ("LA", "QB", "Matthew Stafford", "00-0026498", "StafMa00"),
    ("LA", "RB", "Kyren Williams", "00-0037746", "WillKy00"),
    ("LA", "WR", "Puka Nacua", "00-0039337", "NacuPu00"),
    ("LA", "TE", "Tyler Higbee", "00-0032398", "HigbTy00"),
    ("LA", "K", "Joshua Karty", "00-0039687", "KartJo00"),
    ("SEA", "QB", "Sam Darnold", "00-0034869", "DarnSa00"),
    ("SEA", "RB", "Kenneth Walker III", "00-0037746a", "WalkKe00"),
    ("SEA", "WR", "Jaxon Smith-Njigba", "00-0038543", "SmitJa06"),
    ("SEA", "TE", "AJ Barner", "00-0039912", "BarnAJ00"),
    ("SEA", "K", "Jason Myers", "00-0031258", "MyerJa00"),
)
_DK_TEAM = {"LA": "LAR", "SEA": "SEA"}
_NICKNAME = {"LA": "Rams", "SEA": "Seahawks"}

# Deliberately unequal so every normalized share is distinguishable and a
# uniform fill would be visible in the output.
_USAGE = {
    "00-0026498": {"attempts": 500, "carries": 20, "targets": 0, "receptions": 0,
                   "receiving_yards": 0, "rushing_tds": 2, "receiving_tds": 0},
    "00-0037746": {"attempts": 0, "carries": 300, "targets": 60, "receptions": 45,
                   "receiving_yards": 380, "rushing_tds": 14, "receiving_tds": 2},
    "00-0039337": {"attempts": 0, "carries": 10, "targets": 150, "receptions": 100,
                   "receiving_yards": 1300, "rushing_tds": 1, "receiving_tds": 8},
    "00-0032398": {"attempts": 0, "carries": 0, "targets": 70, "receptions": 50,
                   "receiving_yards": 500, "rushing_tds": 0, "receiving_tds": 3},
    "00-0039687": {"attempts": 0, "carries": 0, "targets": 0, "receptions": 0,
                   "receiving_yards": 0, "rushing_tds": 0, "receiving_tds": 0},
    "00-0034869": {"attempts": 450, "carries": 35, "targets": 0, "receptions": 0,
                   "receiving_yards": 0, "rushing_tds": 3, "receiving_tds": 0},
    "00-0037746a": {"attempts": 0, "carries": 250, "targets": 55, "receptions": 40,
                    "receiving_yards": 300, "rushing_tds": 9, "receiving_tds": 1},
    "00-0038543": {"attempts": 0, "carries": 5, "targets": 140, "receptions": 95,
                   "receiving_yards": 1100, "rushing_tds": 0, "receiving_tds": 6},
    "00-0039912": {"attempts": 0, "carries": 0, "targets": 60, "receptions": 40,
                   "receiving_yards": 400, "rushing_tds": 0, "receiving_tds": 2},
    "00-0031258": {"attempts": 0, "carries": 0, "targets": 0, "receptions": 0,
                   "receiving_yards": 0, "rushing_tds": 0, "receiving_tds": 0},
}
_SNAP_PCT = {
    "StafMa00": "1", "WillKy00": "0.72", "NacuPu00": "0.86", "HigbTy00": "0.61",
    "KartJo00": "0", "DarnSa00": "1", "WalkKe00": "0.68", "SmitJa06": "0.9",
    "BarnAJ00": "0.55", "MyerJa00": "0",
}


def _csv_bytes(header: tuple[str, ...], rows) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _salary_bytes(status_by_name: dict[str, str] | None = None) -> bytes:
    header = (
        "Position", "Name + ID", "Name", "ID", "Roster Position", "Salary",
        "Game Info", "TeamAbbrev", "AvgPointsPerGame", "Status",
    )
    people = [(_DK_TEAM[team], position, name) for team, position, name, _gsis, _pfr in _ROSTER]
    people += [("LAR", "DST", "Rams"), ("SEA", "DST", "Seahawks")]
    rows = []
    dk_id = 40000000
    for index, (team, position, name) in enumerate(people):
        flex_salary = 10000 - index * 400
        for role, salary in (("CPT", round(flex_salary * 1.5)), ("FLEX", flex_salary)):
            dk_id += 1
            rows.append(
                (
                    position, f"{name} ({dk_id})", name, str(dk_id), role, str(salary),
                    GAME_INFO, team,
                    # A deliberately absurd APPG: if it ever reached a numerical
                    # path the derived output would move, and it must not.
                    "999.9", (status_by_name or {}).get(name, ""),
                )
            )
    return _csv_bytes(header, rows)


def _games_bytes(
    *,
    roof: str = "dome",
    spread: str = "-3.5",
    total: str = "44.5",
    home_roof_history: tuple[str, ...] = (),
) -> bytes:
    header = (
        "game_id", "season", "game_type", "week", "gameday", "away_team", "home_team",
        "spread_line", "total_line", "roof", "home_score",
    )
    rows = [
        ("2026_02_LA_SEA", "2026", "REG", "2", "2026-09-13", "LA", "SEA", spread, total, roof, ""),
        # A same-day decoy that must not be selected.
        ("2026_02_DAL_NYG", "2026", "REG", "2", "2026-09-13", "DAL", "NYG", "3", "48.5", "outdoors", ""),
    ]
    # Completed SEA home games, for the venue-roof-history resolution. Each
    # carries a home score, because an unplayed row is the one being resolved and
    # must never vouch for itself.
    rows += [
        (
            f"2025_{index:02d}_LA_SEA", "2025", "REG", str(index), f"2025-09-{index:02d}",
            "LA", "SEA", "-3.5", "44.5", recorded, "24",
        )
        for index, recorded in enumerate(home_roof_history, start=1)
    ]
    return _csv_bytes(header, rows)


def _teams_bytes() -> bytes:
    header = ("season", "team", "full", "nickname", "draft_kings")
    rows = [
        ("2026", code, f"City {_NICKNAME[code]}", _NICKNAME[code], f"{code} {_NICKNAME[code]}")
        for code in sorted(_NICKNAME)
    ]
    rows.append(("2025", "LA", "City Rams", "Rams", "LA Rams"))
    return _csv_bytes(header, rows)


_TEAM_STAT_COLUMNS = (
    "season", "week", "team", "season_type", "attempts", "carries", "sacks_suffered",
    "passing_yards", "rushing_yards", "passing_tds", "rushing_tds",
    "passing_interceptions", "fumbles_lost_total", "fg_made",
)


def _team_stats_bytes(*, weeks: int = 17) -> bytes:
    rows = []
    for team_index, team in enumerate(("LA", "SEA")):
        for week in range(1, weeks + 1):
            # A small week-to-week wobble so the dispersion measure is non-zero
            # and the coefficient of variation is actually exercised.
            wobble = (week % 3) - 1
            rows.append(
                (
                    "2025", str(week), team, "REG",
                    str(32 + wobble + team_index), str(26 - wobble), "2",
                    str(240 + 5 * wobble), str(110 - 3 * wobble), "2", "1", "1", "1", "2",
                )
            )
        rows.append(("2025", "1", team, "POST", "40", "20", "3", "300", "90", "3", "1", "0", "0", "1"))
    return _csv_bytes(_TEAM_STAT_COLUMNS, rows)


_PLAYER_STAT_COLUMNS = (
    "player_id", "player_display_name", "position", "season", "week", "season_type",
    "team", "attempts", "carries", "receptions", "targets", "receiving_yards",
    "rushing_tds", "receiving_tds",
)


def _player_stats_bytes() -> bytes:
    rows = []
    for team, position, name, gsis, _pfr in _ROSTER:
        usage = _USAGE[gsis]
        # Split across two weeks to prove the adapter aggregates rather than
        # reading a single row, and put one week on a different team to prove
        # the join is on person, not on current team.
        for week, share, played_for in ((1, 2, team), (2, 2, "DEN")):
            rows.append(
                (
                    gsis, name, position, "2025", str(week), "REG", played_for,
                    str(usage["attempts"] // share), str(usage["carries"] // share),
                    str(usage["receptions"] // share), str(usage["targets"] // share),
                    str(usage["receiving_yards"] // share),
                    str(usage["rushing_tds"] // share), str(usage["receiving_tds"] // share),
                )
            )
        # Postseason must be excluded.
        rows.append((gsis, name, position, "2025", "1", "POST", team,
                     "99", "99", "99", "99", "999", "9", "9"))
    return _csv_bytes(_PLAYER_STAT_COLUMNS, rows)


_SNAP_COLUMNS = (
    "season", "week", "game_type", "player", "pfr_player_id", "position", "team",
    "offense_snaps", "offense_pct",
)


def _snap_counts_bytes() -> bytes:
    rows = []
    for team, position, name, _gsis, pfr in _ROSTER:
        for week in (1, 2):
            rows.append(("2025", str(week), "REG", name, pfr, position, team, "50", _SNAP_PCT[pfr]))
        rows.append(("2025", "1", "WC", name, pfr, position, team, "50", "1"))
    return _csv_bytes(_SNAP_COLUMNS, rows)


_ROSTER_COLUMNS = (
    "season", "week", "team", "position", "full_name", "gsis_id", "pfr_id", "status",
)


def _roster_bytes() -> bytes:
    rows = []
    for team, position, name, gsis, pfr in _ROSTER:
        rows.append(("2026", "1", team, position, name, gsis, pfr, "ACT"))
        rows.append(("2026", "2", team, position, name, gsis, pfr, "ACT"))
    return _csv_bytes(_ROSTER_COLUMNS, rows)


_PLAYERS_COLUMNS = (
    "gsis_id", "display_name", "position", "latest_team", "status", "pfr_id",
)


def _players_bytes(*, extra=()) -> bytes:
    rows = [
        (gsis, name, position, team, "ACT", pfr)
        for team, position, name, gsis, pfr in _ROSTER
    ]
    rows.extend(extra)
    return _csv_bytes(_PLAYERS_COLUMNS, rows)


_SOURCE_BYTES = {
    "players": _players_bytes,
    "games": _games_bytes,
    "teams": _teams_bytes,
    "team_stats": _team_stats_bytes,
    "player_stats": _player_stats_bytes,
    "snap_counts": _snap_counts_bytes,
    "weekly_rosters": _roster_bytes,
}


def _write_package(root: Path, *, salary_digest: str, overrides=None) -> Path:
    """Assemble a propose-stage package offline, exactly as freeze_sources would."""

    overrides = overrides or {}
    root.mkdir(parents=True)
    raw = root / priors.RAW_DIRNAME
    raw.mkdir()
    specifications = {
        item.name: item for item in priors.source_specifications(season=2026, prior_season=2025)
    }
    artifacts = []
    for name in sorted(_SOURCE_BYTES):
        payload = overrides.get(name) or _SOURCE_BYTES[name]()
        specification = specifications[name]
        digest = __import__("hashlib").sha256(payload).hexdigest()
        path = raw / f"{digest}.csv"
        path.write_bytes(payload)
        artifacts.append(
            {
                "name": name,
                "artifact_id": digest,
                "relative_path": f"{priors.RAW_DIRNAME}/{path.name}",
                "sha256": digest,
                "byte_count": len(payload),
                "source_uri": specification.url,
                "captured_at": CAPTURED.isoformat(),
                "observed_at": CAPTURED.isoformat(),
                "expires_at": (CAPTURED + specification.expires_after).isoformat(),
                "license_decision": specification.license_decision,
                "parser_version": specification.parser_version,
                "staleness_basis": specification.staleness_basis,
                "coverage": {"http_status": 200, "rows": 1},
            }
        )
    manifest = {
        "schema_version": priors.MANIFEST_SCHEMA,
        "adapter_version": priors.ADAPTER_VERSION,
        "as_of": AS_OF,
        "season": 2026,
        "prior_season": 2025,
        "salary_artifact_id": salary_digest,
        "dk_game_id": "LAR@SEA",
        "dk_lock_at": "2026-09-13T16:25:00-04:00",
        "nflverse_game_id": "2026_02_LA_SEA",
        "team_crosswalk": {"LAR": "LA", "SEA": "SEA"},
        "artifacts": artifacts,
    }
    (root / priors.MANIFEST_FILENAME).write_bytes(canonical_json_bytes(manifest))
    return root


@pytest.fixture
def package(tmp_path: Path, request: pytest.FixtureRequest):
    """A reviewed propose-stage package plus everything freeze needs.

    Parametrize indirectly with a `{name: status}` map to build the package on
    salary bytes that already carry a DraftKings Status. The proposal manifest
    binds the salary digest, so a status cannot be introduced after the fact.
    """

    salary = tmp_path / "DKSalaries.csv"
    _write_salary(salary, _salary_bytes(getattr(request, "param", None)))
    salary_digest = sha256_file(salary)
    root = _write_package(tmp_path / "proposal", salary_digest=salary_digest)

    slate = parse_salaries(salary)
    teams_rows = priors.read_csv_rows(
        next((root / priors.RAW_DIRNAME).glob("*.csv")).parent
        / _named(root, "teams"),
        ("season", "team", "full", "nickname", "draft_kings"),
        label="teams",
    )
    crosswalk = resolve_team_crosswalk(slate, teams_rows, season=2026)
    roster_rows = priors.read_csv_rows(
        (root / priors.RAW_DIRNAME) / _named(root, "weekly_rosters"),
        _ROSTER_COLUMNS,
        label="weekly_rosters",
    )
    index_rows = priors.read_csv_rows(
        (root / priors.RAW_DIRNAME) / _named(root, "players"),
        _PLAYERS_COLUMNS,
        label="players",
    )
    proposals = propose_identities(
        slate, roster_rows, crosswalk, season=2026, player_index_rows=index_rows
    )
    manifest_hash = sha256_file(root / priors.MANIFEST_FILENAME)
    proposal_payload = {
        "schema_version": priors.PROPOSAL_SCHEMA,
        "adapter_version": priors.ADAPTER_VERSION,
        "as_of": AS_OF,
        "season": 2026,
        "salary_artifact_id": salary_digest,
        "source_manifest_sha256": manifest_hash,
        "authoritative": False,
        "note": "test proposal",
        "proposals": [item.as_payload() for item in proposals],
    }
    (root / priors.PROPOSAL_FILENAME).write_bytes(canonical_json_bytes(proposal_payload))
    review = root / priors.REVIEW_FILENAME
    review.write_bytes(priors.review_csv_bytes(proposals))
    return {
        "root": root,
        "salary": salary,
        "salary_digest": salary_digest,
        "review": review,
        "proposals": proposals,
        "slate": slate,
        "crosswalk": crosswalk,
    }


def _named(root: Path, name: str) -> str:
    manifest = json.loads((root / priors.MANIFEST_FILENAME).read_text(encoding="utf-8"))
    for entry in manifest["artifacts"]:
        if entry["name"] == name:
            return Path(entry["relative_path"]).name
    raise AssertionError(f"no artifact named {name}")


def _freeze(package, tmp_path: Path, *, name: str = "out", **overrides):
    arguments = {
        "package_dir": package["root"],
        "reviewed": package["review"],
        "reviewed_sha256": sha256_file(package["review"]),
        "salaries": package["salary"],
        "salary_sha256": package["salary_digest"],
        "as_of": AS_OF,
        "output_dir": tmp_path / name,
    }
    arguments.update(overrides)
    return freeze_prior_package(**arguments)


# --------------------------------------------------------------------------- #
# Acceptance 1: reproducibility
# --------------------------------------------------------------------------- #


def test_frozen_package_contains_its_raw_scoring_inputs(package, tmp_path):
    from nfl_dfs.prior_review import resolve_frozen_artifact
    result = _freeze(package, tmp_path, name="portable")
    root = Path(result["output_dir"])
    metadata = json.loads((root / priors.PACKAGE_FILENAME).read_text(encoding="utf-8"))
    for name, digest in metadata["frozen_sources"].items():
        resolved = resolve_frozen_artifact(digest, package_dir=root, label=name)
        assert resolved.resolution == "IN_PACKAGE"
        assert sha256_file(resolved.path) == digest


def test_two_freezes_from_the_same_frozen_artifacts_are_byte_identical(package, tmp_path):
    first = _freeze(package, tmp_path, name="first")
    second = _freeze(package, tmp_path, name="second")
    for filename in (
        priors.TEAM_PRIOR_FILENAME,
        priors.PLAYER_PRIOR_FILENAME,
        priors.IDENTITY_MAP_FILENAME,
    ):
        assert first["hashes"][filename] == second["hashes"][filename], filename
        assert (
            Path(first["output_dir"], filename).read_bytes()
            == Path(second["output_dir"], filename).read_bytes()
        )


def test_canonical_json_emits_decimals_as_numbers_and_refuses_floats():
    payload = {"b": Decimal("0.5"), "a": Decimal("1.000000"), "c": [Decimal("0")]}
    rendered = canonical_json_bytes(payload).decode("utf-8")
    assert rendered == '{"a":1,"b":0.5,"c":[0]}\n'
    assert json.loads(rendered)["b"] == 0.5
    with pytest.raises(PriorsBuildError, match="FLOAT_IN_DERIVED_OUTPUT"):
        canonical_json_bytes({"a": 0.5})


def test_appg_never_reaches_a_derived_number(package, tmp_path):
    baseline = _freeze(package, tmp_path, name="baseline")
    mutated = Path(package["salary"]).read_bytes().replace(b"999.9", b"111.1")
    salary = tmp_path / "mutated.csv"
    _write_salary(salary, mutated)
    root = _write_package(tmp_path / "proposal2", salary_digest=sha256_file(salary))
    # Rebuild the proposal against the mutated salary file, then freeze again.
    slate = parse_salaries(salary)
    roster_rows = priors.read_csv_rows(
        (root / priors.RAW_DIRNAME) / _named(root, "weekly_rosters"),
        _ROSTER_COLUMNS,
        label="weekly_rosters",
    )
    proposals = propose_identities(slate, roster_rows, package["crosswalk"], season=2026)
    (root / priors.PROPOSAL_FILENAME).write_bytes(
        canonical_json_bytes(
            {
                "schema_version": priors.PROPOSAL_SCHEMA,
                "adapter_version": priors.ADAPTER_VERSION,
                "as_of": AS_OF,
                "season": 2026,
                "salary_artifact_id": sha256_file(salary),
                "source_manifest_sha256": sha256_file(root / priors.MANIFEST_FILENAME),
                "authoritative": False,
                "note": "test proposal",
                "proposals": [item.as_payload() for item in proposals],
            }
        )
    )
    review = root / priors.REVIEW_FILENAME
    review.write_bytes(priors.review_csv_bytes(proposals))
    mutated_result = freeze_prior_package(
        package_dir=root,
        reviewed=review,
        reviewed_sha256=sha256_file(review),
        salaries=salary,
        salary_sha256=sha256_file(salary),
        as_of=AS_OF,
        output_dir=tmp_path / "mutated_out",
    )
    assert (
        mutated_result["hashes"][priors.PLAYER_PRIOR_FILENAME]
        == baseline["hashes"][priors.PLAYER_PRIOR_FILENAME]
    )
    assert (
        mutated_result["hashes"][priors.TEAM_PRIOR_FILENAME]
        == baseline["hashes"][priors.TEAM_PRIOR_FILENAME]
    )


# --------------------------------------------------------------------------- #
# Acceptance 2: one mapping and one record per person, both roles reconciled
# --------------------------------------------------------------------------- #


def test_every_person_including_kickers_and_dst_gets_exactly_one_record(package, tmp_path):
    result = _freeze(package, tmp_path)
    slate = package["slate"]
    people = priors.showdown_people(slate)
    assert len(slate.players) == 2 * len(people) == 24

    identity = json.loads(Path(result["identity_map"]).read_text(encoding="utf-8"))
    player_prior = json.loads(Path(result["player_source"]).read_text(encoding="utf-8"))
    assert len(identity["player_mappings"]) == len(people)
    assert len(player_prior["records"]) == len(people)

    flex_ids = {player.dk_id for player in slate.players if player.role == "FLEX"}
    captain_ids = {player.dk_id for player in slate.players if player.role == "CPT"}
    mapped = {row["dk_id"] for row in identity["player_mappings"]}
    assert mapped == flex_ids
    assert not mapped & captain_ids
    assert {row["dk_role"] for row in identity["player_mappings"]} == {"FLEX"}
    assert len({row["underlying_id"] for row in identity["player_mappings"]}) == len(people)

    positions = {row["position"] for row in player_prior["records"]}
    assert {"K", "DST"} <= positions
    reconciliation = identity["metadata"]["coverage"]["showdown_role_reconciliation"]
    assert reconciliation["people"] == len(people)
    assert reconciliation["salary_rows"] == len(slate.players)
    assert reconciliation["captain_rows_reconciled"] == len(people)


def test_team_crosswalk_binds_dk_lar_to_nflverse_la(package):
    assert package["crosswalk"] == {"LAR": "LA", "SEA": "SEA"}


def test_shares_are_normalized_over_the_pool_and_not_uniform(package, tmp_path):
    result = _freeze(package, tmp_path)
    records = json.loads(Path(result["player_source"]).read_text(encoding="utf-8"))["records"]
    identity = json.loads(Path(result["identity_map"]).read_text(encoding="utf-8"))
    team_of = {row["provider_player_id"]: row["team"] for row in identity["player_mappings"]}
    for field, positions in (
        ("target_weight", {"RB", "WR", "TE"}),
        ("qb_attempt_weight", {"QB"}),
    ):
        for team in ("LAR", "SEA"):
            eligible = [
                Decimal(str(row[field]))
                for row in records
                if team_of[row["provider_player_id"]] == team and row["position"] in positions
            ]
            # Shares are quantized to six places, so the group sums to one
            # within one quantum per member rather than exactly. projection.py
            # renormalizes over the same eligible set, so that residue never
            # reaches a model input; forcing an exact sum here would mean
            # distorting an individual share to absorb the rounding.
            residue = abs(sum(eligible) - Decimal("1"))
            assert residue <= priors.QUANTUM * len(eligible), (field, team, residue)
            if len(eligible) > 1:
                assert len(set(eligible)) == len(eligible), f"{field} looks uniform"
    kickers = [row for row in records if row["position"] == "K"]
    assert kickers and all(
        Decimal(str(row["target_weight"])) == 0 and Decimal(str(row["catch_rate"])) == 0
        for row in kickers
    )


def test_postseason_and_other_seasons_are_excluded(package, tmp_path):
    result = _freeze(package, tmp_path)
    records = json.loads(Path(result["player_source"]).read_text(encoding="utf-8"))["records"]
    # The POST rows give every person identical usage. If they leaked in, the
    # WR and TE target shares on a team would converge.
    identity = json.loads(Path(result["identity_map"]).read_text(encoding="utf-8"))
    team_of = {row["provider_player_id"]: row["team"] for row in identity["player_mappings"]}
    receivers = {
        row["position"]: Decimal(str(row["target_weight"]))
        for row in records
        if team_of[row["provider_player_id"]] == "SEA" and row["position"] in {"WR", "TE"}
    }
    assert receivers["WR"] > receivers["TE"]


# --------------------------------------------------------------------------- #
# Acceptance 3: named actionable failures that publish nothing
# --------------------------------------------------------------------------- #


def test_salary_hash_mismatch_fails_closed(package, tmp_path):
    with pytest.raises(PriorsBuildError, match="SALARY_ARTIFACT_HASH_MISMATCH"):
        _freeze(package, tmp_path, salary_sha256="0" * 64)
    assert not (tmp_path / "out").exists()


def test_reviewed_file_hash_mismatch_fails_closed(package, tmp_path):
    with pytest.raises(PriorsBuildError, match="REVIEW_FILE_HASH_MISMATCH"):
        _freeze(package, tmp_path, reviewed_sha256="0" * 64)
    assert not (tmp_path / "out").exists()


def test_tampered_frozen_artifact_fails_closed(package, tmp_path):
    target = (package["root"] / priors.RAW_DIRNAME) / _named(package["root"], "team_stats")
    target.write_bytes(target.read_bytes() + b"\n")
    with pytest.raises(PriorsBuildError, match="FROZEN_ARTIFACT_HASH_MISMATCH"):
        _freeze(package, tmp_path)
    assert not (tmp_path / "out").exists()


def test_insufficient_team_coverage_fails_closed(tmp_path):
    salary = tmp_path / "DKSalaries.csv"
    _write_salary(salary)
    digest = sha256_file(salary)
    root = _write_package(
        tmp_path / "thin",
        salary_digest=digest,
        overrides={"team_stats": _team_stats_bytes(weeks=2)},
    )
    slate = parse_salaries(salary)
    roster_rows = priors.read_csv_rows(
        (root / priors.RAW_DIRNAME) / _named(root, "weekly_rosters"),
        _ROSTER_COLUMNS,
        label="weekly_rosters",
    )
    proposals = propose_identities(slate, roster_rows, {"LAR": "LA", "SEA": "SEA"}, season=2026)
    (root / priors.PROPOSAL_FILENAME).write_bytes(
        canonical_json_bytes(
            {
                "schema_version": priors.PROPOSAL_SCHEMA,
                "adapter_version": priors.ADAPTER_VERSION,
                "as_of": AS_OF,
                "season": 2026,
                "salary_artifact_id": digest,
                "source_manifest_sha256": sha256_file(root / priors.MANIFEST_FILENAME),
                "authoritative": False,
                "note": "test",
                "proposals": [item.as_payload() for item in proposals],
            }
        )
    )
    review = root / priors.REVIEW_FILENAME
    review.write_bytes(priors.review_csv_bytes(proposals))
    with pytest.raises(PriorsBuildError, match="TEAM_PRIOR_COVERAGE_INSUFFICIENT"):
        freeze_prior_package(
            package_dir=root,
            reviewed=review,
            reviewed_sha256=sha256_file(review),
            salaries=salary,
            salary_sha256=digest,
            as_of=AS_OF,
            output_dir=tmp_path / "thin_out",
        )
    assert not (tmp_path / "thin_out").exists()


def test_unaccepted_identity_publishes_nothing(package, tmp_path):
    rows = list(csv.reader(io.StringIO(package["review"].read_text(encoding="utf-8"))))
    rows[1][priors.REVIEW_COLUMNS.index("DECISION")] = ""
    buffer = io.StringIO(newline="")
    csv.writer(buffer, lineterminator="\n").writerows(rows)
    package["review"].write_bytes(buffer.getvalue().encode("utf-8"))
    with pytest.raises(PriorsBuildError, match="IDENTITY_NOT_ACCEPTED"):
        _freeze(package, tmp_path)
    assert not (tmp_path / "out").exists()


def test_review_row_cannot_be_silently_altered(package, tmp_path):
    rows = list(csv.reader(io.StringIO(package["review"].read_text(encoding="utf-8"))))
    rows[1][priors.REVIEW_COLUMNS.index("DK_TEAM")] = "XXX"
    buffer = io.StringIO(newline="")
    csv.writer(buffer, lineterminator="\n").writerows(rows)
    package["review"].write_bytes(buffer.getvalue().encode("utf-8"))
    with pytest.raises(PriorsBuildError, match="REVIEW_ROW_ALTERED"):
        _freeze(package, tmp_path)


def test_duplicate_reviewed_provider_id_fails_closed(package, tmp_path):
    rows = list(csv.reader(io.StringIO(package["review"].read_text(encoding="utf-8"))))
    column = priors.REVIEW_COLUMNS.index("REVIEWED_PROVIDER_PLAYER_ID")
    rows[1][column] = "00-0026498"
    rows[2][column] = "00-0026498"
    buffer = io.StringIO(newline="")
    csv.writer(buffer, lineterminator="\n").writerows(rows)
    package["review"].write_bytes(buffer.getvalue().encode("utf-8"))
    with pytest.raises(PriorsBuildError, match="REVIEWED_PROVIDER_ID_NOT_UNIQUE"):
        _freeze(package, tmp_path)


def test_output_directory_is_never_reused(package, tmp_path):
    _freeze(package, tmp_path, name="once")
    with pytest.raises(PriorsBuildError, match="OUTPUT_PACKAGE_EXISTS"):
        _freeze(package, tmp_path, name="once")


def test_uniform_filling_is_refused_when_a_group_has_no_support(tmp_path):
    salary = tmp_path / "DKSalaries.csv"
    _write_salary(salary)
    digest = sha256_file(salary)
    stripped = _player_stats_bytes().replace(b",500,", b",0,").replace(b",250,", b",0,")
    rows = [
        row
        for row in stripped.split(b"\n")
        if not row.startswith(b"00-0026498,")
    ]
    root = _write_package(
        tmp_path / "nosupport",
        salary_digest=digest,
        overrides={"player_stats": b"\n".join(rows)},
    )
    slate = parse_salaries(salary)
    roster_rows = priors.read_csv_rows(
        (root / priors.RAW_DIRNAME) / _named(root, "weekly_rosters"),
        _ROSTER_COLUMNS,
        label="weekly_rosters",
    )
    proposals = propose_identities(slate, roster_rows, {"LAR": "LA", "SEA": "SEA"}, season=2026)
    (root / priors.PROPOSAL_FILENAME).write_bytes(
        canonical_json_bytes(
            {
                "schema_version": priors.PROPOSAL_SCHEMA,
                "adapter_version": priors.ADAPTER_VERSION,
                "as_of": AS_OF,
                "season": 2026,
                "salary_artifact_id": digest,
                "source_manifest_sha256": sha256_file(root / priors.MANIFEST_FILENAME),
                "authoritative": False,
                "note": "test",
                "proposals": [item.as_payload() for item in proposals],
            }
        )
    )
    review = root / priors.REVIEW_FILENAME
    review.write_bytes(priors.review_csv_bytes(proposals))
    result = freeze_prior_package(
        package_dir=root, reviewed=review, reviewed_sha256=sha256_file(review),
        salaries=salary, salary_sha256=digest, as_of=AS_OF,
        output_dir=tmp_path / "nosupport_out",
    )
    # SD2 preserves a missing basis so a captured current allocation can resolve
    # it later. No uniform share is manufactured while freezing history.
    payload = json.loads(Path(result["player_source"]).read_text(encoding="utf-8"))
    quarterback = next(r for r in payload["records"] if r["provider_player_id"] == "00-0026498")
    assert quarterback["qb_attempt_weight"] == 0
    basis = payload["metadata"]["coverage"]["offensive_history_by_person"]
    assert basis["LAR|QB|Matthew Stafford"]["state"] == "MISSING_HISTORY"
    projected = build_projection_package(
        salaries=salary, salary_sha256=digest,
        team_source=result["team_source"], team_source_sha256=result["hashes"][priors.TEAM_PRIOR_FILENAME],
        player_source=result["player_source"], player_source_sha256=result["hashes"][priors.PLAYER_PRIOR_FILENAME],
        identity_map=result["identity_map"], identity_map_sha256=result["hashes"][priors.IDENTITY_MAP_FILENAME],
        as_of=AS_OF, output_dir=tmp_path / "unknown_projection",
    )
    with Path(projected.player_opportunities).open(newline="") as handle:
        row = next(r for r in csv.DictReader(handle) if r["DK_ID"] == "40000002")
    assert float(row["QB_ATTEMPT_SHARE"]) == 0 and row["EVIDENCE_STATE"] == "UNKNOWN"


# --------------------------------------------------------------------------- #
# Acceptance 4: project consumes the three artifacts
# --------------------------------------------------------------------------- #


def test_project_publishes_model_inputs_from_the_frozen_prior_package(package, tmp_path):
    result = _freeze(package, tmp_path)
    produced = build_projection_package(
        salaries=package["salary"],
        salary_sha256=package["salary_digest"],
        team_source=result["team_source"],
        team_source_sha256=result["hashes"][priors.TEAM_PRIOR_FILENAME],
        player_source=result["player_source"],
        player_source_sha256=result["hashes"][priors.PLAYER_PRIOR_FILENAME],
        identity_map=result["identity_map"],
        identity_map_sha256=result["hashes"][priors.IDENTITY_MAP_FILENAME],
        as_of=AS_OF,
        output_dir=tmp_path / "projected",
    )
    team_csv = Path(produced.team_projections).read_text(encoding="utf-8").splitlines()
    player_csv = Path(produced.player_opportunities).read_text(encoding="utf-8").splitlines()
    assert len(team_csv) == 3
    assert len(player_csv) == 1 + len(priors.showdown_people(package["slate"]))
    ledger = json.loads(Path(produced.source_ledger).read_text(encoding="utf-8"))
    # W2/R08 bumped the consumed contract: the entries now carry their own
    # expiry, scope, state, transformation version and dependency bindings.
    assert ledger["schema_version"] == "nfl_source_ledger_v2"
    assert set(ledger["derived"]) == {"team_projections", "player_opportunities"}


# --------------------------------------------------------------------------- #
# Reported, not repaired: R03 and the market/weather gaps
# --------------------------------------------------------------------------- #


def test_zero_capacity_people_are_reported_not_papered_over(package, tmp_path):
    result = _freeze(package, tmp_path)
    diagnostics = result["diagnostics"]
    reported = {entry.split(":")[2] for entry in diagnostics["zero_role_capacity_people"]}
    assert {"K", "DST"} <= reported
    assert diagnostics["zero_role_capacity_count"] >= 4
    assert "R03" in diagnostics["zero_role_capacity_note"]
    records = json.loads(Path(result["player_source"]).read_text(encoding="utf-8"))["records"]
    assert all(
        Decimal(str(row["role_capacity"])) == 0
        for row in records
        if row["position"] in {"K", "DST"}
    )


def test_market_attribution_records_the_missing_book_and_timestamp(package, tmp_path):
    result = _freeze(package, tmp_path)
    coverage = json.loads(Path(result["team_source"]).read_text(encoding="utf-8"))[
        "metadata"
    ]["coverage"]
    assert coverage["market_attribution"] == (
        "NFLVERSE_SCHEDULE_NO_BOOK_NO_PUBLISHER_TIMESTAMP"
    )
    assert coverage["model_status"] == "PRIOR_ONLY"


def test_spread_is_signed_per_team_from_the_home_perspective(package, tmp_path):
    result = _freeze(package, tmp_path)
    records = json.loads(Path(result["team_source"]).read_text(encoding="utf-8"))["records"]
    by_provider = {row["provider_team_id"]: row for row in records}
    # games.csv spread_line -3.5 means the away team was favoured by 3.5.
    assert Decimal(str(by_provider["nflverse:LA:2026"]["market_spread"])) == Decimal("-3.5")
    assert Decimal(str(by_provider["nflverse:SEA:2026"]["market_spread"])) == Decimal("3.5")


def test_weather_state_is_derived_for_a_roof_and_unobserved_outdoors():
    """Session 09 (R28): an outdoor or blank roof with no state used to raise
    `WEATHER_STATE_REQUIRED`; it is now recorded as unobserved, never observed."""

    assert resolve_weather_state({"roof": "dome"}, None)[0] == "INDOOR"
    assert resolve_weather_state({"roof": "closed"}, None)[0] == "ROOF_CLOSED"
    assert resolve_weather_state({"roof": "open"}, None)[0] == "ROOF_OPEN"
    assert resolve_weather_state({"roof": "outdoors"}, None) == (
        "UNOBSERVED", "WEATHER_UNOBSERVED:roof=outdoors")
    assert resolve_weather_state({"roof": ""}, None) == ("UNOBSERVED", "WEATHER_UNOBSERVED:roof=blank")
    assert resolve_weather_state({"roof": "outdoors"}, "rain")[0] == "RAIN"
    with pytest.raises(PriorsBuildError, match="WEATHER_STATE_UNSUPPORTED"):
        resolve_weather_state({"roof": "outdoors"}, "INDOOR")
    with pytest.raises(PriorsBuildError, match="WEATHER_STATE_CONFLICT"):
        resolve_weather_state({"roof": "dome"}, "RAIN")


def test_an_unobserved_outdoor_game_freezes_as_v2_and_a_supplied_state_as_v1(tmp_path):
    salary = tmp_path / "DKSalaries.csv"
    _write_salary(salary)
    digest = sha256_file(salary)
    root = _write_package(
        tmp_path / "outdoor",
        salary_digest=digest,
        overrides={"games": _games_bytes(roof="outdoors")},
    )
    slate = parse_salaries(salary)
    roster_rows = priors.read_csv_rows(
        (root / priors.RAW_DIRNAME) / _named(root, "weekly_rosters"),
        _ROSTER_COLUMNS,
        label="weekly_rosters",
    )
    proposals = propose_identities(slate, roster_rows, {"LAR": "LA", "SEA": "SEA"}, season=2026)
    (root / priors.PROPOSAL_FILENAME).write_bytes(
        canonical_json_bytes(
            {
                "schema_version": priors.PROPOSAL_SCHEMA,
                "adapter_version": priors.ADAPTER_VERSION,
                "as_of": AS_OF,
                "season": 2026,
                "salary_artifact_id": digest,
                "source_manifest_sha256": sha256_file(root / priors.MANIFEST_FILENAME),
                "authoritative": False,
                "note": "test",
                "proposals": [item.as_payload() for item in proposals],
            }
        )
    )
    review = root / priors.REVIEW_FILENAME
    review.write_bytes(priors.review_csv_bytes(proposals))
    arguments = {
        "package_dir": root,
        "reviewed": review,
        "reviewed_sha256": sha256_file(review),
        "salaries": salary,
        "salary_sha256": digest,
        "as_of": AS_OF,
        "output_dir": tmp_path / "outdoor_out",
    }
    # Until Session 09 this freeze raised WEATHER_STATE_REQUIRED and wrote nothing.
    unobserved = freeze_prior_package(**arguments)
    assert unobserved["weather_state"] == "UNOBSERVED"
    assert unobserved["weather_basis"] == "WEATHER_UNOBSERVED:roof=outdoors"
    team = json.loads(Path(unobserved["team_source"]).read_text(encoding="utf-8"))
    assert team["schema_version"] == "nfl_team_projection_source_v2"
    assert {record["weather_state"] for record in team["records"]} == {"UNOBSERVED"}
    supplied = freeze_prior_package(
        **{**arguments, "weather_state": "WIND", "output_dir": tmp_path / "outdoor_wind"})
    assert supplied["weather_state"] == "WIND"
    assert supplied["weather_basis"].startswith("OPERATOR_SUPPLIED")
    wind = json.loads(Path(supplied["team_source"]).read_text(encoding="utf-8"))
    assert wind["schema_version"] == "nfl_team_projection_source_v1"


# --------------------------------------------------------------------------- #
# Identity proposals are never EXACT
# --------------------------------------------------------------------------- #


def test_weather_evidence_uri_is_held_to_source_policy(tmp_path, package):
    from nfl_dfs.priors import _weather_evidence_basis

    when = datetime(2026, 9, 13, 14, tzinfo=timezone.utc)
    observed = "2026-09-13T13:00:00+00:00"
    assert _weather_evidence_basis(None, None, as_of=when) == (
        "OPERATOR_SUPPLIED_UNATTRIBUTED"
    )
    basis = _weather_evidence_basis(
        "https://api.weather.gov/gridpoints/SEW/125,67/forecast", observed, as_of=when
    )
    assert basis.startswith("OPERATOR_CAPTURE:https://api.weather.gov/")
    assert "observed_at=2026-09-13T13:00:00+00:00" in basis
    # An unapproved host is refused even though the operator typed it in.
    with pytest.raises(PriorsBuildError, match="WEATHER_SOURCE_UNAPPROVED"):
        _weather_evidence_basis("https://www.actionnetwork.com/weather", observed, as_of=when)
    with pytest.raises(PriorsBuildError, match="WEATHER_OBSERVED_AT_REQUIRED"):
        _weather_evidence_basis(
            "https://api.weather.gov/gridpoints/SEW/125,67/forecast", None, as_of=when
        )
    with pytest.raises(PriorsBuildError, match="WEATHER_OBSERVATION_IN_FUTURE"):
        _weather_evidence_basis(
            "https://api.weather.gov/gridpoints/SEW/125,67/forecast",
            "2026-09-14T00:00:00+00:00",
            as_of=when,
        )


def test_outdoor_freeze_records_the_weather_source(tmp_path):
    salary = tmp_path / "DKSalaries.csv"
    _write_salary(salary)
    digest = sha256_file(salary)
    root = _write_package(
        tmp_path / "attributed",
        salary_digest=digest,
        overrides={"games": _games_bytes(roof="outdoors")},
    )
    slate = parse_salaries(salary)
    roster_rows = priors.read_csv_rows(
        (root / priors.RAW_DIRNAME) / _named(root, "weekly_rosters"),
        _ROSTER_COLUMNS,
        label="weekly_rosters",
    )
    proposals = propose_identities(slate, roster_rows, {"LAR": "LA", "SEA": "SEA"}, season=2026)
    (root / priors.PROPOSAL_FILENAME).write_bytes(
        canonical_json_bytes(
            {
                "schema_version": priors.PROPOSAL_SCHEMA,
                "adapter_version": priors.ADAPTER_VERSION,
                "as_of": AS_OF,
                "season": 2026,
                "salary_artifact_id": digest,
                "source_manifest_sha256": sha256_file(root / priors.MANIFEST_FILENAME),
                "authoritative": False,
                "note": "test",
                "proposals": [item.as_payload() for item in proposals],
            }
        )
    )
    review = root / priors.REVIEW_FILENAME
    review.write_bytes(priors.review_csv_bytes(proposals))
    result = freeze_prior_package(
        package_dir=root,
        reviewed=review,
        reviewed_sha256=sha256_file(review),
        salaries=salary,
        salary_sha256=digest,
        as_of=AS_OF,
        output_dir=tmp_path / "attributed_out",
        weather_state="CLEAR",
        weather_source_uri="https://api.weather.gov/gridpoints/SEW/125,67/forecast",
        weather_observed_at="2026-09-13T13:00:00+00:00",
    )
    coverage = json.loads(Path(result["team_source"]).read_text(encoding="utf-8"))[
        "metadata"
    ]["coverage"]
    assert "OPERATOR_CAPTURE:https://api.weather.gov/" in coverage["weather_basis"]
    metadata = json.loads(Path(result["team_source"]).read_text(encoding="utf-8"))["metadata"]
    assert datetime.fromisoformat(metadata["expires_at"]) <= datetime.fromisoformat("2026-09-13T19:00:00+00:00")


def test_proposals_never_claim_exact(package):
    methods = {item.match_method for item in package["proposals"]}
    assert "EXACT" not in methods
    assert methods <= {
        "NORMALIZED_NAME_TEAM_POSITION",
        "NORMALIZED_NAME_TEAM",
        "PLAYERS_INDEX_NAME_TEAM_POSITION",
        "PLAYERS_INDEX_OTHER_TEAM",
        "TEAM_DEFENSE_NICKNAME",
        "NAME_POSITION_OTHER_TEAM",
        "NAME_OTHER_TEAM",
        "AMBIGUOUS",
        "UNMATCHED",
    }


def test_a_person_on_another_nflverse_team_is_reported_with_its_candidate(package, tmp_path):
    salary = tmp_path / "moved.csv"
    _write_salary(salary)
    slate = parse_salaries(salary)
    roster = _roster_bytes().replace(b",LA,WR,Puka Nacua,", b",DEN,WR,Puka Nacua,")
    path = tmp_path / "roster.csv"
    path.write_bytes(roster)
    rows = priors.read_csv_rows(path, _ROSTER_COLUMNS, label="weekly_rosters")
    proposals = propose_identities(slate, rows, {"LAR": "LA", "SEA": "SEA"}, season=2026)
    moved = next(item for item in proposals if item.dk_name == "Puka Nacua")
    assert moved.match_method == "NAME_POSITION_OTHER_TEAM"
    assert moved.provider_player_id == "00-0039337"
    assert moved.provider_team == "DEN"
    assert not moved.resolved
    assert any("DEN" in candidate for candidate in moved.candidates)


def test_person_missing_from_the_weekly_roster_resolves_through_the_player_index(tmp_path):
    salary = tmp_path / "reserve.csv"
    _write_salary(salary)
    slate = parse_salaries(salary)
    # Drop the Rams tight end from the dated weekly roster entirely, the way a
    # reserve-list person is absent from it, and leave him in the index on the
    # same team.
    roster = b"\n".join(
        row for row in _roster_bytes().split(b"\n") if b"Tyler Higbee" not in row
    )
    roster_path = tmp_path / "roster.csv"
    roster_path.write_bytes(roster)
    index_path = tmp_path / "players.csv"
    index_path.write_bytes(_players_bytes())
    proposals = propose_identities(
        slate,
        priors.read_csv_rows(roster_path, _ROSTER_COLUMNS, label="weekly_rosters"),
        {"LAR": "LA", "SEA": "SEA"},
        season=2026,
        player_index_rows=priors.read_csv_rows(
            index_path, _PLAYERS_COLUMNS, label="players"
        ),
    )
    recovered = next(item for item in proposals if item.dk_name == "Tyler Higbee")
    assert recovered.match_method == "PLAYERS_INDEX_NAME_TEAM_POSITION"
    assert recovered.provider_player_id == "00-0032398"
    assert recovered.provider_team == "LA"
    assert recovered.resolved


def test_ambiguous_candidates_are_not_resolved(package, tmp_path):
    salary = tmp_path / "ambiguous.csv"
    _write_salary(salary)
    slate = parse_salaries(salary)
    extra = _roster_bytes() + b"2026,2,LA,WR,Puka Nacua,00-0099999,NacuPu99,ACT\n"
    path = tmp_path / "roster.csv"
    path.write_bytes(extra)
    rows = priors.read_csv_rows(path, _ROSTER_COLUMNS, label="weekly_rosters")
    proposals = propose_identities(slate, rows, {"LAR": "LA", "SEA": "SEA"}, season=2026)
    duplicated = next(item for item in proposals if item.dk_name == "Puka Nacua")
    assert duplicated.match_method == "AMBIGUOUS"
    assert duplicated.provider_player_id == ""
    assert not duplicated.resolved


def test_name_normalization_is_conservative():
    assert normalize_person_name("Jaxon Smith-Njigba") == "JAXON SMITH NJIGBA"
    assert normalize_person_name("A.J. Brown") == "AJ BROWN"
    assert normalize_person_name("Kenneth Walker III") == "KENNETH WALKER"
    assert normalize_person_name("Odell Beckham Jr.") == "ODELL BECKHAM"
    # A two-token name is never shortened, so a person actually surnamed a
    # suffix token is not mangled into a single token.
    assert normalize_person_name("Jeff Sr") == "JEFF SR"


# --------------------------------------------------------------------------- #
# The sources.py release-asset hop
# --------------------------------------------------------------------------- #


def test_only_a_github_release_download_may_redirect():
    assert is_github_release_download(
        "https://github.com/nflverse/nflverse-data/releases/download/players/players.csv"
    )
    assert not is_github_release_download("https://github.com/nflverse/nflverse-data")
    assert not is_github_release_download(
        "https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv"
    )
    assert not is_github_release_download(
        "https://evil.example.com/nflverse/x/releases/download/a/b.csv"
    )


def test_release_redirect_target_must_be_a_github_asset_host():
    url = "https://github.com/nflverse/nflverse-data/releases/download/players/players.csv"
    assert resolve_github_release_redirect(
        url, "https://release-assets.githubusercontent.com/x/y?sig=1"
    ).startswith("https://release-assets.githubusercontent.com/")
    for bad in (
        "",
        "http://release-assets.githubusercontent.com/x",
        "https://evil.example.com/x",
        "https://user:pass@release-assets.githubusercontent.com/x",
    ):
        with pytest.raises(SourcePolicyError):
            resolve_github_release_redirect(url, bad)


# --------------------------------------------------------------------------- #
# Expiry composition
# --------------------------------------------------------------------------- #


def test_emitted_expiry_is_the_earliest_contributing_source_capped_at_lock(package, tmp_path):
    result = _freeze(package, tmp_path)
    lock = package["slate"].games[0].lock_at.astimezone(timezone.utc)
    specifications = {
        item.name: item for item in priors.source_specifications(season=2026, prior_season=2025)
    }
    for filename, contributors in (
        (priors.TEAM_PRIOR_FILENAME, ("games", "teams", "team_stats")),
        (priors.PLAYER_PRIOR_FILENAME, ("player_stats", "snap_counts", "weekly_rosters")),
        (priors.IDENTITY_MAP_FILENAME, ("weekly_rosters", "teams", "players")),
    ):
        metadata = json.loads(
            Path(result["output_dir"], filename).read_text(encoding="utf-8")
        )["metadata"]
        expires = datetime.fromisoformat(metadata["expires_at"])
        expected = min(
            [CAPTURED + specifications[name].expires_after for name in contributors] + [lock]
        )
        assert expires == expected, filename
        assert expires <= lock


def test_salary_artifact_expires_at_lock(package, tmp_path):
    result = _freeze(package, tmp_path)
    identity = json.loads(Path(result["identity_map"]).read_text(encoding="utf-8"))
    lock = package["slate"].games[0].lock_at.astimezone(timezone.utc)
    assert datetime.fromisoformat(identity["salary_artifact"]["expires_at"]) == lock
    assert identity["salary_artifact"]["license_decision"] == "OPERATOR_SUPPLIED"
    assert identity["salary_artifact"]["coverage"]["appg_policy"] == (
        "HASHED_RAW_ONLY_NOT_USED_NUMERICALLY"
    )


def test_stale_source_is_refused_by_project(package, tmp_path):
    result = _freeze(package, tmp_path)
    late = (CAPTURED + timedelta(days=90)).isoformat()
    with pytest.raises(Exception, match="STALE_EVIDENCE"):
        build_projection_package(
            salaries=package["salary"],
            salary_sha256=package["salary_digest"],
            team_source=result["team_source"],
            team_source_sha256=result["hashes"][priors.TEAM_PRIOR_FILENAME],
            player_source=result["player_source"],
            player_source_sha256=result["hashes"][priors.PLAYER_PRIOR_FILENAME],
            identity_map=result["identity_map"],
            identity_map_sha256=result["hashes"][priors.IDENTITY_MAP_FILENAME],
            as_of=late,
            output_dir=tmp_path / "stale",
        )


# --------------------------------------------------------------------------- #
# P0-1: the identity / pool-completeness alignment of 2026-09-13
# --------------------------------------------------------------------------- #

_DROPPABLE = "Joshua Karty"


def _decide_by_name(package, name: str, decision: str) -> str:
    """Rewrite one reviewed person's DECISION in place. Returns his DK ID."""

    rows = list(csv.reader(io.StringIO(package["review"].read_text(encoding="utf-8"))))
    name_column = priors.REVIEW_COLUMNS.index("DK_NAME")
    target = next(row for row in rows[1:] if row[name_column] == name)
    target[priors.REVIEW_COLUMNS.index("DECISION")] = decision
    buffer = io.StringIO(newline="")
    csv.writer(buffer, lineterminator="\n").writerows(rows)
    package["review"].write_bytes(buffer.getvalue().encode("utf-8"))
    return target[priors.REVIEW_COLUMNS.index("DK_ID")]


@pytest.mark.parametrize("package", [{_DROPPABLE: "OUT"}], indirect=True)
def test_an_unresolved_person_the_site_flags_out_may_be_dropped(package, tmp_path):
    """Ben's ruling, 2026-09-13.

    A full Classic pool lists deep practice-squad and UDFA people DraftKings
    itself flags OUT or IR and nflverse has no record of under any spelling.
    Demanding a complete identity map made the Classic path unpublishable on
    every real main slate, which CLAUDE.md classes as a defect, not a
    constraint.
    """

    _decide_by_name(package, _DROPPABLE, priors.EXCLUDED_UNRESOLVED_DECISION)
    result = _freeze(package, tmp_path)
    assert result["package_status"] == "PRIOR_ARTIFACTS_READY"
    # The drop is named, not merely tolerated: a silent drop is the failure the
    # token exists to avoid.
    assert any(_DROPPABLE in entry for entry in result["excluded_unresolved_people"])


def test_dropping_a_still_selectable_person_fails_closed(package, tmp_path):
    """The guard that makes the tolerance safe.

    The permission is re-derived from the bound salary bytes, so the reviewed
    file alone can never widen it. Here nothing flags the person, so the drop is
    refused and no package is published.
    """

    _decide_by_name(package, _DROPPABLE, priors.EXCLUDED_UNRESOLVED_DECISION)
    with pytest.raises(PriorsBuildError, match="IDENTITY_EXCLUDED_BUT_SELECTABLE"):
        _freeze(package, tmp_path)
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("package", [{_DROPPABLE: "D"}], indirect=True)
def test_a_doubtful_person_may_also_be_dropped(package, tmp_path):
    """One vocabulary, four readers, so P3-18's `D` reaches this gate too.

    Before it, `priors`, `projection` and `opportunity` each carried a private
    `{"OUT", "IR"}` literal and a code added to the participation contract would
    have reached none of them.
    """

    _decide_by_name(package, _DROPPABLE, priors.EXCLUDED_UNRESOLVED_DECISION)
    assert _freeze(package, tmp_path)["package_status"] == "PRIOR_ARTIFACTS_READY"


@pytest.mark.parametrize("package", [{_DROPPABLE: "Q"}], indirect=True)
def test_a_questionable_person_may_not_be_dropped(package, tmp_path):
    """Questionable is playable, so his identity is still required."""

    _decide_by_name(package, _DROPPABLE, priors.EXCLUDED_UNRESOLVED_DECISION)
    with pytest.raises(PriorsBuildError, match="IDENTITY_EXCLUDED_BUT_SELECTABLE"):
        _freeze(package, tmp_path)


@pytest.mark.parametrize("package", [{_DROPPABLE: "OUT"}], indirect=True)
def test_an_unknown_decision_token_is_still_a_rejection(package, tmp_path):
    """Only the exact token drops a person; a typo is not a quiet exclusion."""

    _decide_by_name(package, _DROPPABLE, "EXCLUDE_UNRESOLVED")
    with pytest.raises(PriorsBuildError, match="IDENTITY_NOT_ACCEPTED"):
        _freeze(package, tmp_path)


def test_a_blank_roof_at_a_retractable_venue_resolves_from_its_own_history():
    """R26: nflverse records a retractable roof only after the game is played.

    Reading the blank as an unknown outdoor game demanded an api.weather.gov
    capture for a game played under a roof, which cost two of five games on the
    2026-09-20 afternoon slate. The history comes out of the same frozen
    schedule artifact the run already bound.
    """

    history = {"DAL": {"closed": 17}}
    state, basis = resolve_weather_state(
        {"roof": "", "home_team": "DAL"},
        None,
        venue_roof_history=history,
        venue_roof_seasons=(2025, 2026),
    )
    assert state == "ROOF_CLOSED"
    assert basis == (
        "DERIVED_FROM_VENUE_ROOF_HISTORY:retractable:closed=17/17:seasons=2025,2026"
    )


# Session 09 (R28): these three derive no roof, exactly as before R28, and a
# game nobody has observed is now recorded UNOBSERVED where it used to raise
# WEATHER_STATE_REQUIRED.
def test_a_blank_roof_is_unobserved_without_venue_history():
    # The default is the behaviour that shipped before R26: a blank roof and no
    # history is a game nobody has observed.
    assert resolve_weather_state({"roof": "", "home_team": "DAL"}, None) == (
        "UNOBSERVED", "WEATHER_UNOBSERVED:roof=blank")


def test_a_blank_roof_at_an_outdoor_venue_is_unobserved_with_history_supplied():
    assert resolve_weather_state(
        {"roof": "", "home_team": "GB"},
        None,
        venue_roof_history={"GB": {"outdoors": 17}},
    )[0] == "UNOBSERVED"


def test_a_mixed_retractable_history_is_unobserved():
    assert resolve_weather_state(
        {"roof": "", "home_team": "HOU"},
        None,
        venue_roof_history={"HOU": {"closed": 16, "open": 1}},
    )[0] == "UNOBSERVED"


def test_an_operator_observation_outranks_the_venue_history():
    # A human who watched the roof open beats a count of what it usually does.
    state, basis = resolve_weather_state(
        {"roof": "", "home_team": "ARI"},
        "RAIN",
        venue_roof_history={"ARI": {"closed": 17}},
    )
    assert state == "RAIN"
    assert basis.startswith("OPERATOR_SUPPLIED")


def test_an_outdoors_roof_is_never_resolved_by_venue_history():
    # 'outdoors' is a recorded observation, not a blank. History never overrides
    # what the artifact actually says.
    assert resolve_weather_state(
        {"roof": "outdoors", "home_team": "DAL"},
        None,
        venue_roof_history={"DAL": {"closed": 17}},
    ) == ("UNOBSERVED", "WEATHER_UNOBSERVED:roof=outdoors")


def test_the_proposal_carries_venue_history_only_for_a_retractable_venue():
    """`markets` is where the weather stage reads the counts from."""

    from nfl_dfs.priors import _venue_roof_history_for

    history = {"DAL": {"closed": 17}, "GB": {"outdoors": 17}}
    assert _venue_roof_history_for({"home_team": "DAL"}, history) == {"closed": 17}
    # An outdoor venue's unanimous history is not something the stage may act
    # on, so the proposal does not carry it at all.
    assert _venue_roof_history_for({"home_team": "GB"}, history) == {}
    assert _venue_roof_history_for({"home_team": "DAL"}, None) == {}


def test_a_retractable_venue_blank_roof_freezes_without_a_capture(tmp_path, monkeypatch):
    """R26 at the freeze boundary, not just in the resolver.

    `freeze_prior_package` keeps its own `outdoor_games` list, the
    CLASSIC_WEATHER_SCOPE_AMBIGUOUS check and the capture-expiry accounting. This
    is the test that the venue resolution reaches all of them rather than only
    the function that decides the enum.

    SEA is patched into the retractable set so the mechanism is tested through
    the existing fixture. Which venues actually have a moving roof is a stadium
    fact, tested directly in tests/test_venues.py.
    """

    monkeypatch.setattr(priors, "RETRACTABLE_ROOF_HOME_TEAMS", frozenset({"SEA"}))
    monkeypatch.setattr(
        "nfl_dfs.venues.RETRACTABLE_ROOF_HOME_TEAMS", frozenset({"SEA"})
    )
    salary = tmp_path / "DKSalaries.csv"
    _write_salary(salary)
    digest = sha256_file(salary)
    root = _write_package(
        tmp_path / "retractable",
        salary_digest=digest,
        overrides={"games": _games_bytes(roof="", home_roof_history=("closed",) * 9)},
    )
    slate = parse_salaries(salary)
    roster_rows = priors.read_csv_rows(
        (root / priors.RAW_DIRNAME) / _named(root, "weekly_rosters"),
        _ROSTER_COLUMNS,
        label="weekly_rosters",
    )
    proposals = propose_identities(slate, roster_rows, {"LAR": "LA", "SEA": "SEA"}, season=2026)
    (root / priors.PROPOSAL_FILENAME).write_bytes(
        canonical_json_bytes(
            {
                "schema_version": priors.PROPOSAL_SCHEMA,
                "adapter_version": priors.ADAPTER_VERSION,
                "as_of": AS_OF,
                "season": 2026,
                "salary_artifact_id": digest,
                "source_manifest_sha256": sha256_file(root / priors.MANIFEST_FILENAME),
                "authoritative": False,
                "note": "test",
                "proposals": [item.as_payload() for item in proposals],
            }
        )
    )
    review = root / priors.REVIEW_FILENAME
    review.write_bytes(priors.review_csv_bytes(proposals))
    frozen = freeze_prior_package(
        package_dir=root,
        reviewed=review,
        reviewed_sha256=sha256_file(review),
        salaries=salary,
        salary_sha256=digest,
        as_of=AS_OF,
        output_dir=tmp_path / "retractable_out",
    )
    assert frozen["weather_state"] == "ROOF_CLOSED"
    assert frozen["weather_basis"] == (
        "DERIVED_FROM_VENUE_ROOF_HISTORY:retractable:closed=9/9:seasons=2025,2026"
    )


def test_a_retractable_venue_with_one_open_game_still_derives_no_roof(tmp_path, monkeypatch):
    """The same fixture, one recorded open roof. R26's bound holds: no roof is
    derived. Until Session 09 the freeze raised WEATHER_STATE_REQUIRED; now the
    game is frozen UNOBSERVED (R28), never as the roof its history suggests."""

    monkeypatch.setattr(priors, "RETRACTABLE_ROOF_HOME_TEAMS", frozenset({"SEA"}))
    monkeypatch.setattr(
        "nfl_dfs.venues.RETRACTABLE_ROOF_HOME_TEAMS", frozenset({"SEA"})
    )
    salary = tmp_path / "DKSalaries.csv"
    _write_salary(salary)
    digest = sha256_file(salary)
    root = _write_package(
        tmp_path / "mixed",
        salary_digest=digest,
        overrides={
            "games": _games_bytes(
                roof="", home_roof_history=("closed",) * 8 + ("open",)
            )
        },
    )
    slate = parse_salaries(salary)
    roster_rows = priors.read_csv_rows(
        (root / priors.RAW_DIRNAME) / _named(root, "weekly_rosters"),
        _ROSTER_COLUMNS,
        label="weekly_rosters",
    )
    proposals = propose_identities(slate, roster_rows, {"LAR": "LA", "SEA": "SEA"}, season=2026)
    (root / priors.PROPOSAL_FILENAME).write_bytes(
        canonical_json_bytes(
            {
                "schema_version": priors.PROPOSAL_SCHEMA,
                "adapter_version": priors.ADAPTER_VERSION,
                "as_of": AS_OF,
                "season": 2026,
                "salary_artifact_id": digest,
                "source_manifest_sha256": sha256_file(root / priors.MANIFEST_FILENAME),
                "authoritative": False,
                "note": "test",
                "proposals": [item.as_payload() for item in proposals],
            }
        )
    )
    review = root / priors.REVIEW_FILENAME
    review.write_bytes(priors.review_csv_bytes(proposals))
    frozen = freeze_prior_package(
        package_dir=root,
        reviewed=review,
        reviewed_sha256=sha256_file(review),
        salaries=salary,
        salary_sha256=digest,
        as_of=AS_OF,
        output_dir=tmp_path / "mixed_out",
    )
    assert frozen["weather_state"] == "UNOBSERVED"
    assert frozen["weather_basis"] == "WEATHER_UNOBSERVED:roof=blank"


# --- P7: a provenance-only source must not cost the lock path ------------


def _depth_chart_csv(tmp_path, rows=2):
    columns = priors.source_specifications(
        season=2026, prior_season=2025
    )
    spec = {item.name: item for item in columns}["depth_charts"]
    path = tmp_path / "depth_charts.csv"
    body = [",".join(spec.required_columns)]
    for index in range(rows):
        body.append(
            ",".join(
                [
                    "2026-09-20T12:14:30Z", "SEA", f"Player {index}", str(index),
                    f"00-00{index:05d}", "1", "OFF", "1", "Quarterback", "QB",
                    "1", str(index + 1),
                ]
            )
        )
    path.write_text("\n".join(body) + "\n", encoding="utf-8")
    return path, spec


def test_counting_a_provenance_source_agrees_with_reading_it(tmp_path):
    """The cheap path and the retaining path must not disagree about a file."""

    path, spec = _depth_chart_csv(tmp_path, rows=5)
    counted = priors.count_csv_rows(path, spec.required_columns, label="depth_charts")
    read = priors.read_csv_rows(path, spec.required_columns, label="depth_charts")
    assert counted == len(read) == 5


def test_counting_still_refuses_a_missing_column(tmp_path):
    path, spec = _depth_chart_csv(tmp_path)
    with pytest.raises(priors.PriorsBuildError, match="SOURCE_COLUMNS_MISSING:depth_charts"):
        priors.count_csv_rows(path, (*spec.required_columns, "not_a_column"), label="depth_charts")


def test_counting_skips_blank_rows_exactly_as_reading_does(tmp_path):
    path, spec = _depth_chart_csv(tmp_path, rows=3)
    path.write_text(
        path.read_text(encoding="utf-8") + "," * (len(spec.required_columns) - 1) + "\n",
        encoding="utf-8",
    )
    counted = priors.count_csv_rows(path, spec.required_columns, label="depth_charts")
    read = priors.read_csv_rows(path, spec.required_columns, label="depth_charts")
    assert counted == len(read) == 3


def test_only_the_depth_chart_is_provenance_only():
    """Every source the adapter actually joins on still materializes its rows.

    `depth_charts` is 51,864,767 bytes and 545,184 rows; materializing it cost
    14.91s and a 519MB peak on the path that has to finish before a lock, for a
    file nothing reads. Counting instead costs 6.68s and no retained memory.
    If a later chunk makes the adapter join on it, this test is the one that
    should fail first.
    """

    specs = {
        item.name: item
        for item in priors.source_specifications(season=2026, prior_season=2025)
    }
    provenance_only = {
        name for name, item in specs.items() if not item.rows_are_joined_on
    }
    assert provenance_only == {"depth_charts"}
    assert len(specs) == 8
