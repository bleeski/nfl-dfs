from __future__ import annotations

import csv
import json
import math
from copy import deepcopy
from pathlib import Path

import pytest

from nfl_dfs import cli
from nfl_dfs.dk import parse_salaries
from nfl_dfs.evidence import validate_source_ledger
from nfl_dfs.hashing import sha256_file
from nfl_dfs.opportunity import PLAYER_COLUMNS, TEAM_COLUMNS, load_opportunity_model
from nfl_dfs.projection import ProjectionBuildError, build_projection_package

from .conftest import FIXTURE_ROOT


AS_OF = "2026-09-04T12:00:00+00:00"
OBSERVED = "2026-09-04T10:00:00+00:00"
CAPTURED = "2026-09-04T10:05:00+00:00"
EXPIRES = "2026-09-05T12:00:00+00:00"
SHOWDOWN_SALARY = FIXTURE_ROOT / "DKSalaries Salary CSV Showdown.csv"
CLASSIC_SALARY = FIXTURE_ROOT / "DKSalaries Salary CSV Classic.csv"


def _metadata(parser_version: str, artifact: str) -> dict[str, object]:
    return {
        "source_uri": f"https://raw.githubusercontent.com/bleeski/nfl-dfs/main/{artifact}",
        "captured_at": CAPTURED,
        "observed_at": OBSERVED,
        "expires_at": EXPIRES,
        "license_decision": "PERMITTED_REPOSITORY_LICENSE",
        "parser_version": parser_version,
        "evidence_state": "PASS",
        "coverage": {"fixture": True},
    }


def _salary_people(slate):
    people = {}
    for player in slate.players:
        if player.underlying_id not in people or player.role == "FLEX":
            people[player.underlying_id] = player
    return people


def _weight_fields(position: str) -> dict[str, float]:
    if position == "QB":
        return {
            "qb_attempt_weight": 1.0,
            "carry_weight": 0.2,
            "target_weight": 0.0,
            "catch_rate": 0.0,
            "yards_per_target": 0.0,
            "rushing_td_weight": 0.2,
            "receiving_td_weight": 0.0,
            "role_capacity": 1.0,
        }
    if position == "RB":
        return {
            "qb_attempt_weight": 0.0,
            "carry_weight": 1.0,
            "target_weight": 0.7,
            "catch_rate": 0.72,
            "yards_per_target": 6.2,
            "rushing_td_weight": 1.0,
            "receiving_td_weight": 0.7,
            "role_capacity": 1.0,
        }
    if position == "WR":
        return {
            "qb_attempt_weight": 0.0,
            "carry_weight": 0.05,
            "target_weight": 1.0,
            "catch_rate": 0.64,
            "yards_per_target": 8.1,
            "rushing_td_weight": 0.05,
            "receiving_td_weight": 1.0,
            "role_capacity": 1.0,
        }
    if position == "TE":
        return {
            "qb_attempt_weight": 0.0,
            "carry_weight": 0.01,
            "target_weight": 0.8,
            "catch_rate": 0.68,
            "yards_per_target": 7.0,
            "rushing_td_weight": 0.01,
            "receiving_td_weight": 0.8,
            "role_capacity": 1.0,
        }
    return {
        "qb_attempt_weight": 0.0,
        "carry_weight": 0.0,
        "target_weight": 0.0,
        "catch_rate": 0.0,
        "yards_per_target": 0.0,
        "rushing_td_weight": 0.0,
        "receiving_td_weight": 0.0,
        "role_capacity": 0.0,
    }


def _payloads(salary: Path) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    slate = parse_salaries(salary)
    team_records = []
    team_mappings = []
    for game in slate.games:
        for team in (game.away_team, game.home_team):
            provider_team_id = f"TEAM-{team}"
            team_records.append(
                {
                    "provider_team_id": provider_team_id,
                    "game_id": game.game_id,
                    "plays_mean": 64.0,
                    "pass_rate": 0.58,
                    "pass_yards_per_attempt": 6.8,
                    "rush_yards_per_attempt": 4.2,
                    "touchdowns_mean": 2.5,
                    "field_goals_mean": 1.5,
                    "turnovers_mean": 1.2,
                    "sacks_allowed_mean": 2.4,
                    "uncertainty": 0.25,
                    "market_total": 45.0,
                    "market_spread": 0.0,
                    "market_observed_at": OBSERVED,
                    "weather_state": "INDOOR_OR_CLEAR",
                    "era": "2026_PRIOR",
                    "evidence_state": "PASS",
                }
            )
            team_mappings.append(
                {
                    "provider_team_id": provider_team_id,
                    "team": team,
                    "game_id": game.game_id,
                    "match_method": "EXACT",
                    "evidence_state": "PASS",
                }
            )
    player_records = []
    player_mappings = []
    for index, player in enumerate(_salary_people(slate).values(), start=1):
        provider_player_id = f"GSIS-{index:05d}"
        player_records.append(
            {
                "provider_player_id": provider_player_id,
                "provider_team_id": f"TEAM-{player.team}",
                "position": player.position,
                **_weight_fields(player.position),
                "evidence_state": "PASS",
            }
        )
        player_mappings.append(
            {
                "provider_player_id": provider_player_id,
                "provider_team_id": f"TEAM-{player.team}",
                "dk_id": player.dk_id,
                "underlying_id": player.underlying_id,
                "team": player.team,
                "position": player.position,
                "dk_role": player.role,
                "match_method": "EXACT",
                "evidence_state": "PASS",
            }
        )
    team_payload = {
        "schema_version": "nfl_team_projection_source_v1",
        "metadata": _metadata("team_projection_source_v1", "team-source.json"),
        "records": team_records,
    }
    player_payload = {
        "schema_version": "nfl_player_opportunity_source_v1",
        "metadata": _metadata("player_opportunity_source_v1", "player-source.json"),
        "records": player_records,
    }
    identity_payload = {
        "schema_version": "nfl_projection_identity_map_v1",
        "metadata": _metadata("projection_identity_map_v1", "identity-map.json"),
        "salary_artifact": {
            "artifact_id": sha256_file(salary),
            "source_uri": "https://www.draftkings.com/",
            "captured_at": CAPTURED,
            "observed_at": OBSERVED,
            "expires_at": EXPIRES,
            "license_decision": "OPERATOR_SUPPLIED",
            "parser_version": "dk_csv_v1",
            "evidence_state": "PASS",
            "coverage": {"operator_download": True},
        },
        "team_mappings": team_mappings,
        "player_mappings": player_mappings,
    }
    return team_payload, player_payload, identity_payload


def _write_json(path: Path, payload: object) -> Path:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=True) + "\n",
        encoding="utf-8",
    )
    return path


def _prepare(tmp_path: Path, salary: Path = SHOWDOWN_SALARY) -> dict[str, object]:
    team_payload, player_payload, identity_payload = _payloads(salary)
    team_path = _write_json(tmp_path / "team-source.json", team_payload)
    player_path = _write_json(tmp_path / "player-source.json", player_payload)
    identity_path = _write_json(tmp_path / "identity-map.json", identity_payload)
    return {
        "salaries": salary,
        "salary_sha256": sha256_file(salary),
        "team_source": team_path,
        "team_source_sha256": sha256_file(team_path),
        "player_source": player_path,
        "player_source_sha256": sha256_file(player_path),
        "identity_map": identity_path,
        "identity_map_sha256": sha256_file(identity_path),
        "as_of": AS_OF,
        "output_dir": tmp_path / "package",
    }


def _rewrite_input(
    args: dict[str, object],
    key: str,
    payload: dict[str, object],
    *,
    update_hash: bool = True,
) -> Path:
    path = Path(args[key])
    _write_json(path, payload)
    if update_hash:
        args[f"{key}_sha256"] = sha256_file(path)
    return path


def test_end_to_end_classic_package_has_exact_schema_coverage_bounds_and_ledger(
    tmp_path: Path,
) -> None:
    args = _prepare(tmp_path, CLASSIC_SALARY)
    package = build_projection_package(**args)
    output = Path(package.output_dir)
    assert {path.name for path in output.iterdir()} == {
        "team_projections.csv",
        "player_opportunities.csv",
        "source_ledger.json",
    }
    slate = parse_salaries(CLASSIC_SALARY)
    with Path(package.team_projections).open(encoding="utf-8", newline="") as handle:
        team_rows = list(csv.DictReader(handle))
    with Path(package.player_opportunities).open(encoding="utf-8", newline="") as handle:
        player_rows = list(csv.DictReader(handle))
    assert tuple(team_rows[0]) == TEAM_COLUMNS
    assert tuple(player_rows[0]) == PLAYER_COLUMNS
    assert len(team_rows) == len({player.team for player in slate.players}) == 24
    assert len(player_rows) == len({player.underlying_id for player in slate.players}) == 719
    expected_team_order = [
        team
        for game in slate.games
        for team in (game.away_team, game.home_team)
    ]
    assert [row["TEAM"] for row in team_rows] == expected_team_order
    assert [int(row["DK_ID"]) for row in player_rows] == sorted(
        int(row["DK_ID"]) for row in player_rows
    )
    for row in team_rows:
        assert 35 <= float(row["PLAYS_MEAN"]) <= 95
        assert 0.2 <= float(row["PASS_RATE"]) <= 0.85
        assert 0 <= float(row["UNCERTAINTY"]) <= 1
    for row in player_rows:
        for field in (
            "QB_ATTEMPT_SHARE",
            "CARRY_SHARE",
            "TARGET_SHARE",
            "CATCH_RATE",
            "RUSHING_TD_SHARE",
            "RECEIVING_TD_SHARE",
            "ROLE_CAPACITY",
        ):
            assert math.isfinite(float(row[field]))
            assert 0 <= float(row[field]) <= 1
        assert float(row["YARDS_PER_TARGET"]) >= 0
        assert row["EVIDENCE_STATE"] == "PASS"
    model = load_opportunity_model(
        slate, package.team_projections, package.player_opportunities
    )
    assert len(model.teams) == 24
    assert len(model.players) == 719
    ledger_payload = json.loads(Path(package.source_ledger).read_text(encoding="utf-8"))
    expected_derived = {
        "team_projections": sha256_file(package.team_projections),
        "player_opportunities": sha256_file(package.player_opportunities),
    }
    assert ledger_payload["derived"] == expected_derived
    assert {entry["artifact_id"] for entry in ledger_payload["entries"]} == set(
        package.input_hashes.values()
    )
    assert all(entry["coverage"] for entry in ledger_payload["entries"])
    validate_source_ledger(
        package.source_ledger,
        expected_outputs=expected_derived,
        now=parse_salaries(CLASSIC_SALARY).games[0].lock_at,
    )


def test_identical_runs_have_identical_csv_and_ledger_bytes(tmp_path: Path) -> None:
    args = _prepare(tmp_path)
    first = build_projection_package(**args)
    second_args = {**args, "output_dir": tmp_path / "second-package"}
    second = build_projection_package(**second_args)
    for name in ("team_projections", "player_opportunities", "source_ledger"):
        assert Path(getattr(first, name)).read_bytes() == Path(getattr(second, name)).read_bytes()
        assert first.hashes[name] == second.hashes[name]


def test_showdown_outputs_one_flex_id_per_underlying_person(tmp_path: Path) -> None:
    args = _prepare(tmp_path)
    package = build_projection_package(**args)
    slate = parse_salaries(SHOWDOWN_SALARY)
    by_id = {player.dk_id: player for player in slate.players}
    with Path(package.player_opportunities).open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 63
    assert len({by_id[row["DK_ID"]].underlying_id for row in rows}) == 63
    assert all(by_id[row["DK_ID"]].role == "FLEX" for row in rows)


def test_appg_mutation_cannot_change_either_derived_csv_byte(tmp_path: Path) -> None:
    baseline_dir = tmp_path / "baseline-inputs"
    baseline_dir.mkdir()
    baseline_args = _prepare(baseline_dir)
    baseline = build_projection_package(**baseline_args)

    rows = list(csv.reader(SHOWDOWN_SALARY.open("r", encoding="utf-8-sig", newline="")))
    appg_index = rows[0].index("AvgPointsPerGame")
    for index, row in enumerate(rows[1:], start=1):
        row[appg_index] = str(900000 + index)
    mutated_salary = tmp_path / "mutated-salary.csv"
    with mutated_salary.open("w", encoding="utf-8-sig", newline="") as handle:
        csv.writer(handle, lineterminator="\r\n").writerows(rows)

    mutated_dir = tmp_path / "mutated-inputs"
    mutated_dir.mkdir()
    mutated_args = _prepare(mutated_dir, mutated_salary)
    mutated = build_projection_package(**mutated_args)
    assert Path(baseline.team_projections).read_bytes() == Path(mutated.team_projections).read_bytes()
    assert Path(baseline.player_opportunities).read_bytes() == Path(mutated.player_opportunities).read_bytes()


@pytest.mark.parametrize("case", ["missing", "tampered"])
def test_missing_or_tampered_artifact_fails_without_partial_package(
    tmp_path: Path, case: str
) -> None:
    args = _prepare(tmp_path)
    source = Path(args["player_source"])
    if case == "missing":
        source.unlink()
    else:
        source.write_text(source.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(ProjectionBuildError, match="INPUT_ARTIFACT_(MISSING|HASH_MISMATCH)"):
        build_projection_package(**args)
    assert not Path(args["output_dir"]).exists()


@pytest.mark.parametrize(
    "mutation,match",
    [
        (lambda meta: meta.update(source_uri="https://example.com/source.json"), "SOURCE_LICENSE_UNAPPROVED"),
        (lambda meta: meta.update(license_decision="SECONDARY_STATUS_ONLY"), "SOURCE_LICENSE_UNAPPROVED"),
        (lambda meta: meta.update(parser_version="unknown_parser_v1"), "PARSER_VERSION_UNAPPROVED"),
        (lambda meta: meta.update(expires_at="2026-09-04T11:00:00+00:00"), "STALE_EVIDENCE"),
        (
            lambda meta: meta.update(
                captured_at="2026-09-04T13:00:00+00:00",
                observed_at="2026-09-04T12:59:00+00:00",
                expires_at="2026-09-05T13:00:00+00:00",
            ),
            "FUTURE_EVIDENCE",
        ),
        (lambda meta: meta.update(evidence_state="CONFLICTED"), "CONFLICTED_EVIDENCE"),
        (lambda meta: meta.update(evidence_state="UNKNOWN"), "UNKNOWN_EVIDENCE"),
    ],
)
def test_unapproved_stale_future_conflicted_or_unknown_metadata_fails_closed(
    tmp_path: Path, mutation, match: str
) -> None:
    args = _prepare(tmp_path)
    payload = json.loads(Path(args["team_source"]).read_text(encoding="utf-8"))
    mutation(payload["metadata"])
    _rewrite_input(args, "team_source", payload)
    with pytest.raises(ProjectionBuildError, match=match):
        build_projection_package(**args)
    assert not Path(args["output_dir"]).exists()


def test_ambiguous_source_identity_fails_closed(tmp_path: Path) -> None:
    args = _prepare(tmp_path)
    payload = json.loads(Path(args["player_source"]).read_text(encoding="utf-8"))
    payload["records"].append(deepcopy(payload["records"][0]))
    _rewrite_input(args, "player_source", payload)
    with pytest.raises(ProjectionBuildError, match="AMBIGUOUS_PLAYER_SOURCE_ID"):
        build_projection_package(**args)
    assert not Path(args["output_dir"]).exists()


@pytest.mark.parametrize(
    "case,match",
    [
        ("missing", "PLAYER_IDENTITY_COVERAGE_MISMATCH"),
        ("duplicate", "DUPLICATE_PLAYER_IDENTITY"),
        ("fuzzy", "FUZZY_IDENTITY_FORBIDDEN"),
        ("team", "PLAYER_TEAM_IDENTITY_CONFLICT"),
        ("position", "PLAYER_POSITION_IDENTITY_CONFLICT"),
        ("showdown_role", "SHOWDOWN_ROLE_IDENTITY_CONFLICT"),
    ],
)
def test_missing_duplicate_fuzzy_conflicted_and_showdown_role_identities_fail_closed(
    tmp_path: Path, case: str, match: str
) -> None:
    args = _prepare(tmp_path)
    payload = json.loads(Path(args["identity_map"]).read_text(encoding="utf-8"))
    mappings = payload["player_mappings"]
    if case == "missing":
        mappings.pop()
    elif case == "duplicate":
        mappings.append(deepcopy(mappings[0]))
    elif case == "fuzzy":
        mappings[0]["match_method"] = "NORMALIZED"
    elif case == "team":
        original = mappings[0]["team"]
        mappings[0]["team"] = next(
            mapping["team"] for mapping in payload["team_mappings"] if mapping["team"] != original
        )
    elif case == "position":
        mappings[0]["position"] = "WR" if mappings[0]["position"] != "WR" else "QB"
    elif case == "showdown_role":
        slate = parse_salaries(SHOWDOWN_SALARY)
        player = next(
            player
            for player in slate.players
            if player.underlying_id == mappings[0]["underlying_id"] and player.role == "CPT"
        )
        mappings[0]["dk_id"] = player.dk_id
        mappings[0]["dk_role"] = "CPT"
    _rewrite_input(args, "identity_map", payload)
    with pytest.raises(ProjectionBuildError, match=match):
        build_projection_package(**args)
    assert not Path(args["output_dir"]).exists()


@pytest.mark.parametrize(
    "case,match",
    [
        ("nan", "SOURCE_JSON_INVALID"),
        ("infinity", "SOURCE_JSON_INVALID"),
        ("negative", "PLAYER_SOURCE_INVALID"),
        ("out_of_bounds", "PLAYER_SOURCE_INVALID"),
        ("zero_group", "ZERO_OR_MISSING_SHARE_GROUP"),
    ],
)
def test_invalid_numeric_source_never_clips_invents_or_publishes(
    tmp_path: Path, case: str, match: str
) -> None:
    args = _prepare(tmp_path)
    payload = json.loads(Path(args["player_source"]).read_text(encoding="utf-8"))
    if case == "nan":
        payload["records"][0]["catch_rate"] = float("nan")
    elif case == "infinity":
        payload["records"][0]["yards_per_target"] = float("inf")
    elif case == "negative":
        payload["records"][0]["yards_per_target"] = -1
    elif case == "out_of_bounds":
        payload["records"][0]["carry_weight"] = 1.1
    else:
        team_id = payload["records"][0]["provider_team_id"]
        for record in payload["records"]:
            if record["provider_team_id"] == team_id and record["position"] == "QB":
                record["qb_attempt_weight"] = 0
    _rewrite_input(args, "player_source", payload)
    with pytest.raises(ProjectionBuildError, match=match):
        build_projection_package(**args)
    assert not Path(args["output_dir"]).exists()


def test_salary_identity_hash_conflict_fails_closed(tmp_path: Path) -> None:
    args = _prepare(tmp_path)
    payload = json.loads(Path(args["identity_map"]).read_text(encoding="utf-8"))
    payload["salary_artifact"]["artifact_id"] = "0" * 64
    _rewrite_input(args, "identity_map", payload)
    with pytest.raises(ProjectionBuildError, match="SALARY_HASH_IDENTITY_CONFLICT"):
        build_projection_package(**args)
    assert not Path(args["output_dir"]).exists()


def test_project_cli_reports_prior_only_do_not_upload_truths(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = _prepare(tmp_path)
    argv = ["project"]
    for key in (
        "salaries",
        "salary_sha256",
        "team_source",
        "team_source_sha256",
        "player_source",
        "player_source_sha256",
        "identity_map",
        "identity_map_sha256",
        "as_of",
        "output_dir",
    ):
        argv.extend((f"--{key.replace('_', '-')}", str(args[key])))

    assert cli.main(argv) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["package_status"] == "PROJECTION_INPUTS_READY"
    assert result["FILE_VALID"] is False
    assert result["EVIDENCE_STATE"] == "PASS"
    assert result["MODEL_STATUS"] == "PRIOR_ONLY"
    assert result["RELEASE_DECISION"] == "DO_NOT_UPLOAD"
    assert result["status"] == "DO_NOT_UPLOAD"
