"""C1 golden and adversarial coverage for governed Classic prior review."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from nfl_dfs.dk import parse_salaries
from nfl_dfs.hashing import sha256_file
from nfl_dfs.lineups import validate_lineup
from nfl_dfs.prior_review import run_prior_review
from nfl_dfs import priors
from nfl_dfs.priors import resolve_nflverse_games, resolve_team_crosswalk, slate_people
from nfl_dfs.projection import build_projection_package

from .test_prior_selection import _splits_bytes


AS_OF = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)
OBSERVED = AS_OF - timedelta(minutes=20)
CAPTURED = AS_OF - timedelta(minutes=10)
EXPIRES = AS_OF + timedelta(hours=6)
TEAMS = ("NE", "SEA", "DAL", "PHI")
GAMES = {
    "NE": "NE@SEA 09/13/2026 01:00PM ET",
    "SEA": "NE@SEA 09/13/2026 01:00PM ET",
    "DAL": "DAL@PHI 09/13/2026 04:25PM ET",
    "PHI": "DAL@PHI 09/13/2026 04:25PM ET",
}


def _json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _csv(header, rows) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def _salary_bytes(*, draft_groups: tuple[str, ...] | None = None, appg: float = 99.0) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(
        (
            "Position", "Name + ID", "Name", "ID", "Roster Position", "Salary",
            "Game Info", "TeamAbbrev", "AvgPointsPerGame", "Status", "Draft Group ID",
        )
    )
    identifier = 81000000
    for team_index, team in enumerate(TEAMS):
        for position_index, position in enumerate(("QB", "RB", "WR", "TE", "DST")):
            identifier += 1
            name = f"{team} {position} One"
            salary = 4700 + (team_index * 50) + (position_index * 25)
            group = (draft_groups or ("DG-C1",))[team_index % len(draft_groups or ("DG-C1",))]
            writer.writerow(
                (
                    position,
                    f"{name} ({identifier})",
                    name,
                    identifier,
                    position if position in {"QB", "DST"} else f"{position}/FLEX",
                    salary,
                    GAMES[team],
                    team,
                    appg,
                    "",
                    group,
                )
            )
    return output.getvalue().encode("utf-8")


def _entry_bytes(count: int = 2) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(
        (
            "Entry ID", "Contest Name", "Contest ID", "Entry Fee", "QB", "RB", "RB",
            "WR", "WR", "WR", "TE", "FLEX", "DST", "", "Instructions",
        )
    )
    for index in range(count):
        writer.writerow(
            (
                str(910000001 + index), "C1 Classic", "200000001", "$5",
                "", "", "", "", "", "", "", "", "", "", f"{index + 1}. test",
            )
        )
    return output.getvalue().encode("utf-8")


def _metadata(parser: str, artifact: str, coverage: dict[str, object]) -> dict[str, object]:
    return {
        "source_uri": f"https://raw.githubusercontent.com/openai/test/main/{artifact}",
        "captured_at": CAPTURED.isoformat(),
        "observed_at": OBSERVED.isoformat(),
        "expires_at": EXPIRES.isoformat(),
        "license_decision": "PERMITTED_REPOSITORY_LICENSE",
        "parser_version": parser,
        "evidence_state": "PASS",
        "coverage": coverage,
    }


def _weights(position: str) -> dict[str, float]:
    values = {
        "qb_attempt_weight": 0.0,
        "carry_weight": 0.0,
        "target_weight": 0.0,
        "catch_rate": 0.0,
        "yards_per_target": 0.0,
        "rushing_td_weight": 0.0,
        "receiving_td_weight": 0.0,
        "role_capacity": 0.0,
    }
    if position == "QB":
        values.update(qb_attempt_weight=1.0, carry_weight=0.1, rushing_td_weight=0.1, role_capacity=1.0)
    elif position == "RB":
        values.update(carry_weight=0.9, target_weight=0.2, catch_rate=0.7,
                      yards_per_target=6.0, rushing_td_weight=0.9,
                      receiving_td_weight=0.2, role_capacity=1.0)
    elif position == "WR":
        values.update(target_weight=0.5, catch_rate=0.65, yards_per_target=8.0,
                      receiving_td_weight=0.5, role_capacity=1.0)
    elif position == "TE":
        values.update(target_weight=0.3, catch_rate=0.68, yards_per_target=7.0,
                      receiving_td_weight=0.3, role_capacity=1.0)
    return values


def _projection_sources(root: Path, salary: Path):
    slate = parse_salaries(salary)
    team_records = []
    team_mappings = []
    for game in slate.games:
        for team in (game.away_team, game.home_team):
            provider = f"nflverse:{team}:2026"
            team_records.append(
                {
                    "provider_team_id": provider,
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
                    "market_observed_at": OBSERVED.isoformat(),
                    "weather_state": "INDOOR_OR_CLEAR",
                    "era": "2025_PRIOR",
                    "evidence_state": "PASS",
                }
            )
            team_mappings.append(
                {
                    "provider_team_id": provider,
                    "team": team,
                    "game_id": game.game_id,
                    "match_method": "EXACT",
                    "evidence_state": "PASS",
                }
            )
    player_records = []
    player_mappings = []
    history = {}
    for index, player in enumerate(slate.players, start=1):
        provider = f"GSIS-C1-{index:04d}"
        player_records.append(
            {
                "provider_player_id": provider,
                "provider_team_id": f"nflverse:{player.team}:2026",
                "position": player.position,
                **_weights(player.position),
                "evidence_state": "PASS",
            }
        )
        player_mappings.append(
            {
                "provider_player_id": provider,
                "provider_team_id": f"nflverse:{player.team}:2026",
                "dk_id": player.dk_id,
                "underlying_id": player.underlying_id,
                "team": player.team,
                "position": player.position,
                "dk_role": None,
                "match_method": "EXACT",
                "evidence_state": "PASS",
            }
        )
        if player.position in {"QB", "RB", "WR", "TE"}:
            history[player.underlying_id] = {
                "state": "OBSERVED_HISTORY",
                "current_team": player.team,
                "receiving_efficiency_observed": player.position in {"RB", "WR", "TE"},
            }
    team = _json(
        root / "team_prior.json",
        {
            "schema_version": "nfl_team_projection_source_v1",
            "metadata": _metadata(
                "team_projection_source_v1", "team.json",
                {"expiry_basis": "C1_FIXTURE", "teams": len(TEAMS)},
            ),
            "records": team_records,
        },
    )
    player = _json(
        root / "player_prior.json",
        {
            "schema_version": "nfl_player_opportunity_source_v1",
            "metadata": _metadata(
                "player_opportunity_source_v1", "player.json",
                {"expiry_basis": "C1_FIXTURE", "offensive_history_by_person": history},
            ),
            "records": player_records,
        },
    )
    identity = _json(
        root / "identity_map.json",
        {
            "schema_version": "nfl_projection_identity_map_v1",
            "metadata": _metadata(
                "projection_identity_map_v1", "identity.json",
                {"expiry_basis": "C1_FIXTURE", "people": len(slate.players)},
            ),
            "salary_artifact": {
                "artifact_id": sha256_file(salary),
                "source_uri": "https://www.draftkings.com/",
                "captured_at": CAPTURED.isoformat(),
                "observed_at": OBSERVED.isoformat(),
                "expires_at": EXPIRES.isoformat(),
                "license_decision": "OPERATOR_SUPPLIED",
                "parser_version": "dk_csv_v1",
                "evidence_state": "PASS",
                "coverage": {"raw_bytes": True},
            },
            "team_mappings": team_mappings,
            "player_mappings": player_mappings,
        },
    )
    return slate, team, player, identity


def _role_evidence(root: Path, slate, salary_hash: str) -> Path:
    sources_dir = root / "sources"
    sources_dir.mkdir(parents=True)
    sources = []
    declarations = []
    for team in TEAMS:
        players = [p for p in slate.players if p.team == team and p.position != "DST"]
        shares = {
            "QB": (1.0, 0.1, 0.0, 0.1, 0.0),
            "RB": (0.0, 0.9, 0.2, 0.9, 0.2),
            "WR": (0.0, 0.0, 0.5, 0.0, 0.5),
            "TE": (0.0, 0.0, 0.3, 0.0, 0.3),
        }
        recipients = []
        for player in players:
            qb, carry, target, rush_td, receive_td = shares[player.position]
            recipients.append(
                {
                    "underlying_id": player.underlying_id,
                    "dk_id": player.dk_id,
                    "shares": {
                        "qb_attempt_share": qb,
                        "carry_share": carry,
                        "target_share": target,
                        "rushing_td_share": rush_td,
                        "receiving_td_share": receive_td,
                    },
                }
            )
        game_id = players[0].game_id
        declaration = {
            "team": team,
            "game_id": game_id,
            "totals": {
                "qb_attempt_share": 1.0, "carry_share": 1.0, "target_share": 1.0,
                "rushing_td_share": 1.0, "receiving_td_share": 1.0,
            },
            "unallocated": {
                "qb_attempt_share": 0.0, "carry_share": 0.0, "target_share": 0.0,
                "rushing_td_share": 0.0, "receiving_td_share": 0.0,
            },
            "recipients": recipients,
        }
        excerpt = json.dumps(declaration, sort_keys=True, separators=(",", ":"))
        source_path = sources_dir / "pending.json"
        source_path.write_text(excerpt + "\n", encoding="utf-8")
        digest = sha256_file(source_path)
        final_source = sources_dir / f"{digest}.json"
        source_path.replace(final_source)
        sources.append(
            {
                "path": f"sources/{final_source.name}",
                "sha256": digest,
                "source_uri": f"https://raw.githubusercontent.com/openai/test/main/{team}-roles.json",
                "observed_at": OBSERVED.isoformat(),
                "captured_at": CAPTURED.isoformat(),
                "expires_at": EXPIRES.isoformat(),
                "license_decision": "PERMITTED_REPOSITORY_LICENSE",
                "parser_version": "classic_role_fixture_v1",
                "transformation_version": "offensive_explicit_team_shares_v1",
                "support_kind": "NUMERICAL_ALLOCATION",
                "supporting_excerpt": excerpt,
                "synthetic": False,
            }
        )
        declarations.append({**declaration, "source_sha256": digest})
    return _json(
        root / "offensive_roles.json",
        {
            "schema_version": "nfl_classic_offensive_role_evidence_c1_v1",
            "transformation_version": "offensive_explicit_team_shares_v1",
            "salary_sha256": salary_hash,
            "game_ids": [game.game_id for game in slate.games],
            "sources": sources,
            "declarations": declarations,
            "facts": [],
        },
    )


def _fixture(root: Path, *, entries: int = 2, inactive_dst: bool = False):
    root.mkdir(parents=True, exist_ok=True)
    salary = root / "DKSalaries.csv"
    salary.write_bytes(_salary_bytes())
    entry = root / "DKEntries.csv"
    entry.write_bytes(_entry_bytes(entries))
    package = root / "priors"
    package.mkdir()
    slate, team, player, identity = _projection_sources(package, salary)
    stats = root / "stats_team_week.csv"
    stats.write_bytes(_splits_bytes(teams=TEAMS))
    stats_hash = sha256_file(stats)
    raw = package / "raw"
    raw.mkdir()
    (raw / f"{stats_hash}.csv").write_bytes(stats.read_bytes())
    _json(
        package / "prior_package.json",
        {
            "schema_version": "nfl_prior_package_v1",
            "season": 2026,
            "prior_season": 2025,
            "salary_artifact_id": sha256_file(salary),
            "package_dir": str(package),
            "frozen_sources": {"team_stats": stats_hash},
            "artifacts": {
                "team_prior.json": sha256_file(team),
                "player_prior.json": sha256_file(player),
                "identity_map.json": sha256_file(identity),
            },
        },
    )
    role = _role_evidence(root / "roles", slate, sha256_file(salary))
    status = root / "official_status.csv"
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(("TEAM", "PLAYER_OR_GSIS_ID", "STATUS", "SOURCE_URL", "OBSERVED_AT"))
    inactive_id = next(p.dk_id for p in slate.players if p.team == "NE" and p.position == "DST")
    for player_row in slate.players:
        state = "INACTIVE" if inactive_dst and player_row.dk_id == inactive_id else "ACTIVE"
        writer.writerow(
            (
                player_row.team, player_row.dk_id, state,
                "https://raw.githubusercontent.com/openai/test/main/status.csv",
                OBSERVED.isoformat(),
            )
        )
    status.write_text(output.getvalue(), encoding="utf-8", newline="")
    return salary, entry, package, role, status, inactive_id


def _run(root: Path, *, entries: int = 2, inactive_dst: bool = False):
    salary, entry, package, role, status, inactive_id = _fixture(
        root, entries=entries, inactive_dst=inactive_dst
    )
    outcome = run_prior_review(
        salary_csv=salary,
        entry_csv=entry,
        label="classic-c1",
        as_of=AS_OF,
        run_root=root / "run",
        output_root=root / "out",
        prior_package_dir=package,
        build_priors=True,
        official_status_csv=status,
        offensive_role_evidence_json=role,
        project=build_projection_package,
    )
    return outcome, parse_salaries(salary), inactive_id


def test_classic_intake_detects_mode_geometry_draft_group_and_quarantines_appg(tmp_path: Path) -> None:
    salary = tmp_path / "salary.csv"
    salary.write_bytes(_salary_bytes(appg=9876.5))
    slate = parse_salaries(salary)
    assert slate.mode.value == "CLASSIC"
    assert slate.salary_cap == 50_000
    assert slate.draft_group == "DG-C1"
    assert len(slate.games) == 2
    assert len({player.dk_id for player in slate.players}) == len(slate.players)
    assert all(not hasattr(player, "appg") for player in slate.players)
    mixed = tmp_path / "mixed.csv"
    mixed.write_bytes(_salary_bytes(draft_groups=("DG-A", "DG-B")))
    with pytest.raises(ValueError, match="DRAFT_GROUP_MIXED"):
        parse_salaries(mixed)


def test_classic_prior_identity_and_schedule_bind_every_team_person_and_game(tmp_path: Path) -> None:
    salary = tmp_path / "salary.csv"
    salary.write_bytes(_salary_bytes())
    slate = parse_salaries(salary)
    team_rows = [
        {
            "season": "2026",
            "team": team,
            "full": f"City {team}",
            "nickname": next(
                player.name
                for player in slate.players
                if player.team == team and player.position == "DST"
            ),
            "draft_kings": team,
        }
        for team in TEAMS
    ]
    crosswalk = resolve_team_crosswalk(slate, team_rows, season=2026)
    games = [
        {
            "game_id": "2026_01_NE_SEA",
            "season": "2026",
            "gameday": "2026-09-13",
            "away_team": "NE",
            "home_team": "SEA",
        },
        {
            "game_id": "2026_01_DAL_PHI",
            "season": "2026",
            "gameday": "2026-09-13",
            "away_team": "DAL",
            "home_team": "PHI",
        },
    ]
    resolved = resolve_nflverse_games(slate, games, crosswalk, season=2026)
    assert set(resolved) == {game.game_id for game in slate.games}
    assert set(crosswalk) == set(TEAMS)
    assert len(slate_people(slate)) == len(slate.players) == 20


def test_classic_frozen_prior_producer_covers_every_game_team_and_person(tmp_path: Path) -> None:
    salary = tmp_path / "salary.csv"
    salary.write_bytes(_salary_bytes())
    slate = parse_salaries(salary)
    root = tmp_path / "proposal"
    raw = root / priors.RAW_DIRNAME
    raw.mkdir(parents=True)
    rows: dict[str, bytes] = {}
    rows["teams"] = _csv(
        ("season", "team", "full", "nickname", "draft_kings"),
        [
            (
                "2026", team, f"City {team}",
                next(p.name for p in slate.players if p.team == team and p.position == "DST"),
                team,
            )
            for team in TEAMS
        ],
    )
    rows["games"] = _csv(
        (
            "game_id", "season", "game_type", "week", "gameday", "away_team",
            "home_team", "spread_line", "total_line", "roof",
        ),
        [
            ("2026_01_NE_SEA", "2026", "REG", "1", "2026-09-13", "NE", "SEA", "-2", "44", "dome"),
            ("2026_01_DAL_PHI", "2026", "REG", "1", "2026-09-13", "DAL", "PHI", "1", "46", "closed"),
        ],
    )
    team_week_rows = []
    for team in TEAMS:
        for week in (1, 2, 3, 4):
            team_week_rows.append(
                ("2025", week, team, "REG", 32, 26, 2, 240, 110, 2, 1, 1, 1, 2)
            )
    rows["team_stats"] = _csv(
        (
            "season", "week", "team", "season_type", "attempts", "carries",
            "sacks_suffered", "passing_yards", "rushing_yards", "passing_tds",
            "rushing_tds", "passing_interceptions", "fumbles_lost_total", "fg_made",
        ),
        team_week_rows,
    )
    roster_rows = []
    index_rows = []
    player_stat_rows = []
    snap_rows = []
    for index, player in enumerate(
        (p for p in slate.players if p.position != "DST"), start=1
    ):
        gsis = f"00-C1-{index:04d}"
        pfr = f"PFR{index:04d}"
        roster_rows.append(("2026", "1", player.team, player.position, player.name, gsis, pfr, "ACT"))
        index_rows.append((gsis, player.name, player.position, player.team, "ACT", pfr))
        weights = _weights(player.position)
        player_stat_rows.append(
            (
                gsis, player.name, player.position, "2025", "1", "REG", player.team,
                int(weights["qb_attempt_weight"] * 500),
                int(weights["carry_weight"] * 300),
                int(weights["target_weight"] * 200),
                int(weights["target_weight"] * 250),
                int(weights["target_weight"] * 1800),
                int(weights["rushing_td_weight"] * 10),
                int(weights["receiving_td_weight"] * 10),
            )
        )
        snap_rows.append(("2025", "1", "REG", player.name, pfr, player.position, player.team, "50", "0.8"))
    rows["weekly_rosters"] = _csv(
        ("season", "week", "team", "position", "full_name", "gsis_id", "pfr_id", "status"),
        roster_rows,
    )
    rows["players"] = _csv(
        ("gsis_id", "display_name", "position", "latest_team", "status", "pfr_id"),
        index_rows,
    )
    rows["player_stats"] = _csv(
        (
            "player_id", "player_display_name", "position", "season", "week",
            "season_type", "team", "attempts", "carries", "receptions", "targets",
            "receiving_yards", "rushing_tds", "receiving_tds",
        ),
        player_stat_rows,
    )
    rows["snap_counts"] = _csv(
        (
            "season", "week", "game_type", "player", "pfr_player_id", "position",
            "team", "offense_snaps", "offense_pct",
        ),
        snap_rows,
    )
    specs = {
        item.name: item
        for item in priors.source_specifications(season=2026, prior_season=2025)
    }
    artifacts = []
    for name, payload in sorted(rows.items()):
        digest = __import__("hashlib").sha256(payload).hexdigest()
        path = raw / f"{digest}.csv"
        path.write_bytes(payload)
        spec = specs[name]
        artifacts.append(
            {
                "name": name,
                "artifact_id": digest,
                "relative_path": f"{priors.RAW_DIRNAME}/{path.name}",
                "sha256": digest,
                "byte_count": len(payload),
                "source_uri": spec.url,
                "captured_at": CAPTURED.isoformat(),
                "observed_at": CAPTURED.isoformat(),
                "expires_at": (CAPTURED + spec.expires_after).isoformat(),
                "license_decision": spec.license_decision,
                "parser_version": spec.parser_version,
                "staleness_basis": spec.staleness_basis,
                "coverage": {"rows": len(payload.splitlines()) - 1},
            }
        )
    team_rows = priors.read_csv_rows(raw / next(Path(a["relative_path"]).name for a in artifacts if a["name"] == "teams"), ("season", "team", "full", "nickname", "draft_kings"), label="teams")
    crosswalk = resolve_team_crosswalk(slate, team_rows, season=2026)
    manifest = {
        "schema_version": priors.MANIFEST_SCHEMA,
        "adapter_version": priors.ADAPTER_VERSION,
        "as_of": AS_OF.isoformat(),
        "season": 2026,
        "prior_season": 2025,
        "salary_artifact_id": sha256_file(salary),
        "mode": "CLASSIC",
        "dk_game_ids": [game.game_id for game in slate.games],
        "dk_lock_times": {game.game_id: game.lock_at.isoformat() for game in slate.games},
        "nflverse_game_ids": {"NE@SEA": "2026_01_NE_SEA", "DAL@PHI": "2026_01_DAL_PHI"},
        "team_crosswalk": crosswalk,
        "artifacts": artifacts,
    }
    (root / priors.MANIFEST_FILENAME).write_bytes(priors.canonical_json_bytes(manifest))
    roster_source = raw / next(Path(a["relative_path"]).name for a in artifacts if a["name"] == "weekly_rosters")
    player_source = raw / next(Path(a["relative_path"]).name for a in artifacts if a["name"] == "players")
    proposals = priors.propose_identities(
        slate,
        priors.read_csv_rows(roster_source, tuple(rows["weekly_rosters"].decode().splitlines()[0].split(",")), label="weekly_rosters"),
        crosswalk,
        season=2026,
        player_index_rows=priors.read_csv_rows(player_source, tuple(rows["players"].decode().splitlines()[0].split(",")), label="players"),
    )
    (root / priors.PROPOSAL_FILENAME).write_bytes(
        priors.canonical_json_bytes(
            {
                "schema_version": priors.PROPOSAL_SCHEMA,
                "adapter_version": priors.ADAPTER_VERSION,
                "as_of": AS_OF.isoformat(),
                "season": 2026,
                "salary_artifact_id": sha256_file(salary),
                "source_manifest_sha256": sha256_file(root / priors.MANIFEST_FILENAME),
                "authoritative": False,
                "proposals": [item.as_payload() for item in proposals],
            }
        )
    )
    review = root / priors.REVIEW_FILENAME
    review.write_bytes(priors.review_csv_bytes(proposals))
    result = priors.freeze_prior_package(
        package_dir=root,
        reviewed=review,
        reviewed_sha256=sha256_file(review),
        salaries=salary,
        salary_sha256=sha256_file(salary),
        as_of=AS_OF.isoformat(),
        output_dir=tmp_path / "frozen",
        salary_observed_at=OBSERVED.isoformat(),
    )
    assert result["teams"] == 4
    assert result["people"] == 20
    assert set(result["weather_by_game"]) == {game.game_id for game in slate.games}
    package = build_projection_package(
        salaries=salary,
        salary_sha256=sha256_file(salary),
        team_source=Path(result["output_dir"]) / priors.TEAM_PRIOR_FILENAME,
        team_source_sha256=result["hashes"][priors.TEAM_PRIOR_FILENAME],
        player_source=Path(result["output_dir"]) / priors.PLAYER_PRIOR_FILENAME,
        player_source_sha256=result["hashes"][priors.PLAYER_PRIOR_FILENAME],
        identity_map=Path(result["output_dir"]) / priors.IDENTITY_MAP_FILENAME,
        identity_map_sha256=result["hashes"][priors.IDENTITY_MAP_FILENAME],
        as_of=AS_OF.isoformat(),
        output_dir=tmp_path / "projected",
    )
    assert package.hashes["team_projections"]
    assert package.hashes["player_opportunities"]


@pytest.mark.parametrize("entries", [1, 2])
def test_classic_review_is_deterministic_legal_and_emits_no_upload_shape(
    tmp_path: Path, entries: int
) -> None:
    first, slate, _ = _run(tmp_path / "a", entries=entries)
    second, _second_slate, _ = _run(tmp_path / "b", entries=entries)
    assert not first.blocked, first.blockers
    assert first.file_valid
    assert first.export["EVIDENCE_STATE"] == "PASS"
    assert first.export["MODEL_STATUS"] == "PRIOR_ONLY"
    assert first.export["RELEASE_DECISION"] == "DO_NOT_UPLOAD"
    assert first.hashes["selection_report"] == second.hashes["selection_report"]
    assert first.hashes["complete_slate_coverage"] == second.hashes["complete_slate_coverage"]
    assert "bulk_entry_csv" not in first.artifacts
    # Since Q1C, Classic writes `assignments.csv` — `Entry ID,QB,RB,...` holding
    # DraftKings IDs. That is not an upload shape: it carries no Contest ID,
    # Contest Name, Entry Fee or instructions block, so DraftKings would reject
    # it, and Showdown's prior review has always written the same file. It exists
    # because `lineups.read_assignment_csv` is what `settle` reads, and without
    # it a Classic run cannot bind its own selection into a pre-lock manifest.
    # The upload-shape prohibition above is unchanged and still checked.
    assert Path(first.artifacts["assignments"]).name == "assignments.csv"
    assert first.hashes["assignments"] == second.hashes["assignments"]
    assert not list((tmp_path / "a").rglob("*.csv")) == []  # immutable inputs still exist
    assert not [
        path for path in (tmp_path / "a").rglob("*.csv")
        if path.name.startswith(("DK_UPLOAD_", "DK_REVIEW_ENTRY_"))
    ]
    payload = json.loads(Path(first.artifacts["selection_report"]).read_text(encoding="utf-8"))
    assert len(payload["assignments_by_entry_id"]) == entries
    by_id = {player.dk_id: player for player in slate.players}
    for roster in payload["assignments_by_entry_id"].values():
        validated = validate_lineup(slate, roster)
        assert validated.lineup.salary <= 50_000
        assert len({by_id[dk_id].game_id for dk_id in roster}) >= 2


def test_exact_id_inactive_is_excluded_before_classic_selection(tmp_path: Path) -> None:
    outcome, _slate, inactive_id = _run(tmp_path, inactive_dst=True)
    assert not outcome.blocked, outcome.blockers
    selection = json.loads(Path(outcome.artifacts["selection_report"]).read_text(encoding="utf-8"))
    assert all(
        inactive_id not in roster
        for roster in selection["assignments_by_entry_id"].values()
    )


def test_missing_selected_activity_blocks_before_any_selection_artifact(tmp_path: Path) -> None:
    salary, entry, package, role, status, _ = _fixture(tmp_path)
    rows = status.read_text(encoding="utf-8").splitlines()
    status.write_text("\n".join(rows[:2]) + "\n", encoding="utf-8")
    outcome = run_prior_review(
        salary_csv=salary, entry_csv=entry, label="missing-status", as_of=AS_OF,
        run_root=tmp_path / "run", output_root=tmp_path / "out",
        prior_package_dir=package, official_status_csv=status,
        offensive_role_evidence_json=role,
    )
    assert outcome.blocked
    assert outcome.blockers[0].startswith("SELECTED_CURRENT_EVIDENCE_REQUIRED:")
    assert "OFFICIAL_ACTIVITY" in outcome.blockers[0]
    assert "selection_report" not in outcome.artifacts
    assert not list((tmp_path / "out").rglob("*.csv"))


def test_role_source_mutation_fails_closed(tmp_path: Path) -> None:
    salary, entry, package, role, status, _ = _fixture(tmp_path)
    source = next((role.parent / "sources").iterdir())
    source.write_text(source.read_text(encoding="utf-8") + " ", encoding="utf-8")
    mutated = run_prior_review(
        salary_csv=salary, entry_csv=entry, label="mutated", as_of=AS_OF,
        run_root=tmp_path / "run-a", output_root=tmp_path / "out-a",
        prior_package_dir=package, official_status_csv=status,
        offensive_role_evidence_json=role,
    )
    assert mutated.blocked
    assert "OFFENSIVE_ROLE_SOURCE_HASH_MISMATCH" in mutated.blockers[0]


def test_classic_selects_on_history_derived_priors_and_names_them(tmp_path: Path) -> None:
    """R17 extended to Classic on 2026-09-12.

    No approved host publishes a forward-looking numerical allocation, so
    demanding one for every selected offensive person made a live Classic slate
    unpublishable while the identical Showdown pool selected fine. Classic now
    selects on the same history-derived priors, and every such person is named.
    """

    salary, entry, package, role, status, _ = _fixture(tmp_path)
    del role
    outcome = run_prior_review(
        salary_csv=salary, entry_csv=entry, label="no-role", as_of=AS_OF,
        run_root=tmp_path / "run", output_root=tmp_path / "out",
        prior_package_dir=package, official_status_csv=status,
    )
    assert not outcome.blocked, outcome.blockers
    gate = outcome.reports["selected_evidence_gate"]
    assert gate["status"] == "PASS"
    assert gate["gaps"] == []
    assert gate["role_basis"] == "HISTORY_DERIVED_PRIOR_IS_NOT_A_CURRENT_ROLE"
    assert gate["unverified_role_people"]
    observed = {item["person"] for item in gate["selected_role_observations"]}
    assert set(gate["unverified_role_people"]).issubset(observed)
    assert all(
        item["selection_action"] in {"SELECT", "DIAGNOSTIC"}
        for item in gate["selected_role_observations"]
    )
    # The release truths are untouched by the ruling.
    selection = json.loads(
        Path(outcome.artifacts["selection_report"]).read_text(encoding="utf-8")
    )
    assert selection["MODEL_STATUS"] == "PRIOR_ONLY"
    assert selection["RELEASE_DECISION"] == "DO_NOT_UPLOAD"


def test_unselectable_or_missing_role_finding_still_blocks_classic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The R17 ruling widened the accepted states, it did not remove the gate.

    A selected offensive person whose resolver finding is absent, or carries an
    action the resolver would never select on, still stops publication.
    """

    import nfl_dfs.prior_review as module
    import nfl_dfs.selection as selection_module

    real = selection_module.resolve_offensive_roles

    def drop_first_offensive_finding(*args, **kwargs):
        resolution = real(*args, **kwargs)
        findings = list(resolution.report.get("findings", []))
        keep = [
            item for item in findings
            if item.get("selection_action") not in {"SELECT", "DIAGNOSTIC"}
        ]
        dropped = next(
            item for item in findings
            if item.get("selection_action") in {"SELECT", "DIAGNOSTIC"}
        )
        resolution.report["findings"] = keep + [
            {**dropped, "selection_action": "EXCLUDE"}
        ]
        return resolution

    salary, entry, package, role, status, _ = _fixture(tmp_path)
    del role
    monkeypatch.setattr(
        selection_module, "resolve_offensive_roles", drop_first_offensive_finding
    )
    assert module.run_prior_review is run_prior_review
    outcome = run_prior_review(
        salary_csv=salary, entry_csv=entry, label="dropped-finding", as_of=AS_OF,
        run_root=tmp_path / "run", output_root=tmp_path / "out",
        prior_package_dir=package, official_status_csv=status,
    )
    assert outcome.blocked
    assert outcome.blockers[0].startswith("SELECTED_CURRENT_EVIDENCE_REQUIRED:")
    assert "CURRENT_OFFENSIVE_ROLE" in outcome.blockers[0]
    assert "selection_report" not in outcome.artifacts
    assert not list((tmp_path / "out").rglob("*.csv"))


def test_salary_mutation_during_selection_blocks_artifact_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import nfl_dfs.prior_review as module

    salary, entry, package, role, status, _ = _fixture(tmp_path)
    real = module.select_prior_lineups

    def mutate_after_selection(*args, **kwargs):
        result = real(*args, **kwargs)
        salary.write_bytes(salary.read_bytes() + b"\n")
        return result

    monkeypatch.setattr(module, "select_prior_lineups", mutate_after_selection)
    outcome = run_prior_review(
        salary_csv=salary, entry_csv=entry, label="mutating", as_of=AS_OF,
        run_root=tmp_path / "run", output_root=tmp_path / "out",
        prior_package_dir=package, official_status_csv=status,
        offensive_role_evidence_json=role,
    )
    assert outcome.blocked
    assert outcome.blockers == ("SALARY_CHANGED_BEFORE_ARTIFACT_PUBLISH",)
    assert "selection_report" not in outcome.artifacts


def test_classic_path_never_reaches_field_ownership_or_economics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import nfl_dfs.economics as economics
    import nfl_dfs.field as field
    import nfl_dfs.ownership as ownership
    import nfl_dfs.portfolio as portfolio

    def forbidden(*_args, **_kwargs):
        raise AssertionError("C1 reached a prohibited production-economics path")

    monkeypatch.setattr(economics, "evaluate_candidates_against_field", forbidden)
    monkeypatch.setattr(field, "generate_opponent_field", forbidden)
    monkeypatch.setattr(ownership, "cold_start_states", forbidden)
    monkeypatch.setattr(portfolio, "select_portfolio", forbidden)
    outcome, _slate, _ = _run(tmp_path)
    assert outcome.file_valid


def test_one_cowork_command_emits_classic_review_json_and_no_upload_csv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nfl_dfs import cli
    from .test_prior_review_profile import _cowork_args

    salary, entry, package, role, status, _ = _fixture(tmp_path / "fixture")
    attachments = tmp_path / "attachments"
    attachments.mkdir()
    (attachments / "salary.csv").write_bytes(salary.read_bytes())
    (attachments / "entries.csv").write_bytes(entry.read_bytes())
    monkeypatch.setattr(cli, "DEFAULT_RUNS_DIR", tmp_path / "runs")
    args = _cowork_args(
        tmp_path,
        attachments,
        label="classic-c1",
        prior_package_dir=str(package),
        build_priors=True,
        official_status_csv=str(status),
        offensive_role_evidence_json=str(role),
        as_of=AS_OF.isoformat(),
    )
    code = cli.command_cowork_run(args)
    assert code == 0
    report = json.loads(
        (tmp_path / "outputs" / "prior-review-test" / "cowork_run.json").read_text(
            encoding="utf-8"
        )
    )
    assert report["stage"] == "PRIOR_ONLY_CLASSIC_REVIEW_ARTIFACTS"
    assert report["FILE_VALID"] is True
    assert report["EVIDENCE_STATE"] == "PASS"
    assert report["MODEL_STATUS"] == "PRIOR_ONLY"
    assert report["RELEASE_DECISION"] == "DO_NOT_UPLOAD"
    assert report["bulk_entry_csv"] is None
    assert Path(report["prior_review_artifacts"]["selection_report"]).is_file()
    assert Path(report["prior_review_artifacts"]["complete_slate_coverage"]).is_file()
    assert not [
        path for path in tmp_path.rglob("*.csv")
        if path.name.startswith(("DK_UPLOAD_", "DK_REVIEW_ENTRY_"))
    ]


def test_classic_weather_manifest_requires_exact_complete_game_scope(tmp_path: Path) -> None:
    salary = tmp_path / "salary.csv"
    salary.write_bytes(_salary_bytes())
    entry = tmp_path / "entries.csv"
    entry.write_bytes(_entry_bytes(1))
    slate = parse_salaries(salary)
    weather = _json(
        tmp_path / "weather.json",
        {
            "schema_version": "nfl_classic_weather_evidence_c1_v1",
            "salary_sha256": sha256_file(salary),
            "games": {
                slate.games[0].game_id: {
                    "weather_state": "CLEAR",
                    "source_uri": "https://api.weather.gov/gridpoints/BOX/70,76/forecast",
                    "observed_at": OBSERVED.isoformat(),
                }
            },
        },
    )
    outcome = run_prior_review(
        salary_csv=salary, entry_csv=entry, label="weather-gap", as_of=AS_OF,
        run_root=tmp_path / "run", output_root=tmp_path / "out",
        build_priors=False, weather_evidence_json=weather,
    )
    assert outcome.blocked
    assert outcome.blockers[0].startswith("WEATHER_EVIDENCE_GAME_COVERAGE_MISMATCH")


def _weather_package(root: Path, salary: Path, slate, *, captured=CAPTURED):
    """A complete multi-game weather package, shaped like the real thing.

    The capture bodies are SYNTHETIC: they carry the `properties.generatedAt`
    field the package reads and nothing was fetched to produce them. This
    exercises the binding, hashing, host-policy and freshness checks, not the
    truth of any forecast.
    """

    out = root / "weather"
    sources = out / "sources"
    sources.mkdir(parents=True, exist_ok=True)
    games = {}
    for index, game in enumerate(slate.games):
        body = json.dumps(
            {
                "properties": {
                    "generatedAt": OBSERVED.isoformat(),
                    "gridId": f"SYNTHETIC{index}",
                    "periods": [{"name": "This Afternoon", "shortForecast": "Sunny"}],
                }
            },
            indent=2,
            sort_keys=True,
        ).encode("utf-8") + b"\n"
        digest = hashlib.sha256(body).hexdigest()
        (sources / f"{digest}.json").write_bytes(body)
        games[game.game_id] = {
            "path": f"sources/{digest}.json",
            "sha256": digest,
            "source_uri": f"https://api.weather.gov/gridpoints/SYN/{index},{index}/forecast",
            "license_decision": "PUBLIC_DOMAIN",
            "parser_version": "nws_gridpoint_forecast_v1",
            "observed_at": OBSERVED.isoformat(),
            "captured_at": captured.isoformat(),
            "expires_at": EXPIRES.isoformat(),
        }
    return _json(
        out / "weather_evidence.json",
        {
            "schema_version": "nfl_classic_weather_evidence_c1_v1",
            "salary_sha256": sha256_file(salary),
            "games": games,
        },
    )


def test_classic_weather_package_binds_every_game_and_clears_intake(tmp_path: Path) -> None:
    """The complete multi-game weather path had only negative coverage."""

    salary, entry, package, role, status, _ = _fixture(tmp_path)
    slate = parse_salaries(salary)
    weather = _weather_package(tmp_path, salary, slate)
    outcome = run_prior_review(
        salary_csv=salary, entry_csv=entry, label="weather-ok", as_of=AS_OF,
        run_root=tmp_path / "run", output_root=tmp_path / "out",
        prior_package_dir=package, official_status_csv=status,
        offensive_role_evidence_json=role, weather_evidence_json=weather,
        project=build_projection_package, build_priors=True,
    )
    assert not any(
        blocker.startswith("WEATHER") or ":WEATHER" in blocker
        for blocker in outcome.blockers
    ), outcome.blockers
    assert outcome.hashes["weather_evidence_json"] == sha256_file(weather)
    for game in slate.games:
        assert outcome.hashes[f"weather_source:{game.game_id}"]
    assert not outcome.blocked, outcome.blockers


def test_classic_weather_package_rejects_a_mutated_capture(tmp_path: Path) -> None:
    salary, entry, package, role, status, _ = _fixture(tmp_path)
    slate = parse_salaries(salary)
    weather = _weather_package(tmp_path, salary, slate)
    stored = next((weather.parent / "sources").iterdir())
    stored.write_bytes(stored.read_bytes() + b" ")
    outcome = run_prior_review(
        salary_csv=salary, entry_csv=entry, label="weather-mutated", as_of=AS_OF,
        run_root=tmp_path / "run", output_root=tmp_path / "out",
        prior_package_dir=package, official_status_csv=status,
        offensive_role_evidence_json=role, weather_evidence_json=weather,
        project=build_projection_package, build_priors=True,
    )
    assert outcome.blocked
    assert outcome.blockers[0].startswith("WEATHER_EVIDENCE_SOURCE_HASH_MISMATCH")


def test_classic_weather_package_rejects_a_stale_capture(tmp_path: Path) -> None:
    salary, entry, package, role, status, _ = _fixture(tmp_path)
    slate = parse_salaries(salary)
    weather = _weather_package(tmp_path, salary, slate)
    payload = json.loads(weather.read_text(encoding="utf-8"))
    first = sorted(payload["games"])[0]
    payload["games"][first]["expires_at"] = (AS_OF - timedelta(minutes=1)).isoformat()
    _json(weather, payload)
    outcome = run_prior_review(
        salary_csv=salary, entry_csv=entry, label="weather-stale", as_of=AS_OF,
        run_root=tmp_path / "run", output_root=tmp_path / "out",
        prior_package_dir=package, official_status_csv=status,
        offensive_role_evidence_json=role, weather_evidence_json=weather,
        project=build_projection_package, build_priors=True,
    )
    assert outcome.blocked
    assert outcome.blockers[0].startswith("WEATHER_EVIDENCE_TIME_INVALID_OR_STALE")
