"""C2 golden, adversarial, replay, and boundary coverage."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import highspy
import pytest

from nfl_dfs.classic_portfolio import (
    ClassicCandidateBank,
    assignment_artifact_bytes,
    audit_classic_portfolio,
    build_classic_candidate_bank,
    candidate_bank_bytes,
    exact_classic_assignments,
    solve_classic_portfolio,
)
from nfl_dfs.classic_portfolio_policy import (
    classic_portfolio_policy_template,
    parse_normalized_classic_policy_bytes,
    validate_classic_portfolio_policy_bytes,
    write_normalized_classic_portfolio_policy,
)
from nfl_dfs.contracts import EngineMode, GameContract, SalaryPlayer, SlateContract
from nfl_dfs.hashing import sha256_bytes, sha256_file
from nfl_dfs.lineups import validate_lineup
from nfl_dfs.prior_review import run_prior_review
from nfl_dfs.projection import build_projection_package

from .test_classic_prior_review import AS_OF, _fixture


def _slate() -> SlateContract:
    games = (
        GameContract(
            game_id="NE@SEA",
            away_team="NE",
            home_team="SEA",
            lock_at=datetime(2026, 9, 13, 18, 0, tzinfo=timezone.utc),
        ),
        GameContract(
            game_id="DAL@PHI",
            away_team="DAL",
            home_team="PHI",
            lock_at=datetime(2026, 9, 13, 20, 25, tzinfo=timezone.utc),
        ),
        GameContract(
            game_id="BUF@NYJ",
            away_team="BUF",
            home_team="NYJ",
            lock_at=datetime(2026, 9, 13, 20, 25, tzinfo=timezone.utc),
        ),
    )
    game_by_team = {
        team: game
        for game in games
        for team in (game.away_team, game.home_team)
    }
    depths = {"QB": 2, "RB": 4, "WR": 6, "TE": 3, "DST": 2}
    rows: list[SalaryPlayer] = []
    identifier = 82000000
    for team_index, team in enumerate(game_by_team):
        game = game_by_team[team]
        opponent = game.home_team if team == game.away_team else game.away_team
        for position, depth in depths.items():
            for ordinal in range(1, depth + 1):
                identifier += 1
                rows.append(
                    SalaryPlayer(
                        dk_id=str(identifier),
                        name=f"{team} {position} {ordinal}",
                        position=position,
                        roster_positions=(
                            (position, "FLEX")
                            if position in {"RB", "WR", "TE"}
                            else (position,)
                        ),
                        salary=3500 + 75 * ordinal + 20 * team_index,
                        team=team,
                        opponent=opponent,
                        game_id=game.game_id,
                        lock_at=game.lock_at,
                        underlying_id=f"{team}|{position}|{ordinal}",
                    )
                )
    return SlateContract(
        mode=EngineMode.CLASSIC,
        draft_group="DG-C2",
        games=games,
        scoring_version="draftkings_nfl_scoring_2026_fixture_v1",
        salary_hash=sha256_bytes(b"salary"),
        players=tuple(rows),
    )


def _policy(
    count: int,
    *,
    controls: dict[str, object] | None = None,
    limits: dict[str, object] | None = None,
):
    slate = _slate()
    entry_ids = tuple(f"E{index:03d}" for index in range(1, count + 1))
    entry_bytes = b"entry"
    document = classic_portfolio_policy_template(
        slate,
        entry_ids,
        entry_sha256=sha256_bytes(entry_bytes),
        controls=controls,
        limits=limits,
    )
    raw = json.dumps(document, ensure_ascii=False, indent=2).encode("utf-8")
    validation = validate_classic_portfolio_policy_bytes(
        raw,
        slate=slate,
        entry_ids=entry_ids,
        entry_sha256=sha256_bytes(entry_bytes),
    )
    assert validation.valid, validation.blockers()
    assert validation.policy is not None
    return slate, validation.policy, raw, entry_bytes


def _objective(slate: SlateContract) -> dict[str, float]:
    return {
        row.dk_id: 40.0 - index / 1000.0
        for index, row in enumerate(slate.players)
    }


def _audit(slate, policy, source, original_entry_bytes, bank, selection, **mutations):
    candidate = candidate_bank_bytes(policy, bank)
    pairs = exact_classic_assignments(
        policy.entry_ids,
        [bank.candidates[index].roster for index in selection.selected_candidate_indexes],
    )
    assignment = assignment_artifact_bytes(
        policy,
        pairs,
        candidate_bank_sha256=sha256_bytes(candidate),
    )
    values = {
        "normalized_policy_bytes": policy.canonical_bytes(),
        "expected_normalized_policy_sha256": policy.normalized_sha256,
        "source_policy_bytes": source,
        "expected_source_policy_sha256": sha256_bytes(source),
        "salary_bytes": b"salary",
        "expected_salary_sha256": slate.salary_hash,
        "entry_bytes": original_entry_bytes,
        "expected_entry_sha256": sha256_bytes(original_entry_bytes),
        "bound_artifacts": {"team_prior_sha256": (b"team-prior", sha256_bytes(b"team-prior"))},
        "candidate_bytes": candidate,
        "expected_candidate_sha256": sha256_bytes(candidate),
        "assignment_bytes": assignment,
        "expected_assignment_sha256": sha256_bytes(assignment),
    }
    values.update(mutations)
    return audit_classic_portfolio(slate=slate, **values), candidate, assignment


def test_policy_binds_complete_identity_integer_limits_and_canonicalizes_order() -> None:
    slate, policy, raw, entry_bytes = _policy(3)
    payload = json.loads(raw)
    payload["bindings"]["people"].reverse()
    payload["bindings"]["games"].reverse()
    payload["bindings"]["teams"].reverse()
    reordered = validate_classic_portfolio_policy_bytes(
        json.dumps(payload, separators=(",", ":")).encode(),
        slate=slate,
        entry_ids=policy.entry_ids,
        entry_sha256=sha256_bytes(entry_bytes),
    )
    assert reordered.valid
    assert reordered.policy is not None
    assert reordered.normalized_sha256 == policy.normalized_sha256
    assert parse_normalized_classic_policy_bytes(policy.canonical_bytes()) == policy
    normalized = policy.as_mapping()
    assert normalized["bindings"]["salary_sha256"] == slate.salary_hash
    assert normalized["bindings"]["entry_sha256"] == sha256_bytes(entry_bytes)
    assert normalized["bindings"]["entry_ids"] == list(policy.entry_ids)
    assert normalized["effective"]["hard_controls_are_never_relaxed"] is True


def test_all_supported_bound_types_stack_groups_exclusion_and_audit() -> None:
    slate = _slate()
    people = {row.underlying_id: row for row in slate.players}
    excluded = people["NYJ|WR|6"]
    target = people["NE|QB|1"]
    group_people = [people["DAL|RB|1"], people["DAL|WR|1"]]
    controls = {
        "player_exposure_bounds": [
            {"underlying_id": target.underlying_id, "dk_id": target.dk_id, "minimum_entries": 1, "maximum_entries": 2, "hard": True}
        ],
        "team_exposure_bounds": [
            {"team": "NE", "minimum_entries": 1, "maximum_entries": 3, "hard": True}
        ],
        "game_exposure_bounds": [
            {"game_id": "NE@SEA", "minimum_entries": 1, "maximum_entries": 3, "hard": True}
        ],
        "exact_exclusions": [
            {"underlying_id": excluded.underlying_id, "dk_id": excluded.dk_id}
        ],
        "groups": [
            {
                "group_id": "dal-skill",
                "members": [
                    {"underlying_id": row.underlying_id, "dk_id": row.dk_id}
                    for row in group_people
                ],
                "minimum_players": 1,
                "maximum_players": 2,
                "minimum_entries": 1,
                "maximum_entries": 3,
                "strength": "HARD",
            }
        ],
        "stack_rules": [
            {
                "rule_id": "hard-qb-stack",
                "rule_type": "QB_PASS_CATCHER",
                "minimum_value": 1,
                "maximum_value": 4,
                "minimum_entries": 2,
                "maximum_entries": 3,
                "strength": "HARD",
            },
            {
                "rule_id": "advisory-bringback",
                "rule_type": "QB_BRINGBACK",
                "minimum_value": 1,
                "maximum_value": 6,
                "minimum_entries": 0,
                "maximum_entries": 3,
                "strength": "ADVISORY",
            },
        ],
        "max_pairwise_person_overlap": 8,
        "require_unique_lineups": True,
    }
    slate, policy, source, entry_bytes = _policy(3, controls=controls)
    bank = build_classic_candidate_bank(slate, _objective(slate), policy)
    selection = solve_classic_portfolio(policy, bank)
    assert selection.passed, (bank.as_report(), selection.as_report())
    audit, _candidate, _assignment = _audit(
        slate, policy, source, entry_bytes, bank, selection
    )
    assert audit.passed, audit.problems
    assert dict(audit.player_counts)[target.underlying_id] >= 1
    assert dict(audit.player_counts)[target.underlying_id] <= 2
    assert dict(audit.group_counts)["dal-skill"] >= 1
    assert dict(audit.stack_counts)["hard-qb-stack"] >= 2
    assert dict(audit.player_counts).get(excluded.underlying_id, 0) == 0
    assert all(value <= 8 for *_entries, value in audit.pairwise_overlap)
    assert any(
        stratum.kind == "player_cap_exclusion"
        and stratum.subject == target.underlying_id
        for stratum in bank.strata
    )


@pytest.mark.parametrize("entry_count", (1, 3, 20, 150))
def test_golden_portfolios_cover_every_entry_without_cycles(entry_count: int) -> None:
    slate, policy, _source, _entry = _policy(entry_count)
    bank = build_classic_candidate_bank(slate, _objective(slate), policy)
    selected = solve_classic_portfolio(policy, bank)
    assert selected.passed, (entry_count, bank.as_report(), selected.as_report())
    rosters = [bank.candidates[index].roster for index in selected.selected_candidate_indexes]
    assignments = exact_classic_assignments(policy.entry_ids, rosters)
    assert tuple(entry for entry, _roster in assignments) == policy.entry_ids
    assert len({tuple(roster) for _entry, roster in assignments}) == entry_count
    assert all(validate_lineup(slate, roster).valid for _entry, roster in assignments)
    assert bank.feasible_chain_status == "POLICY_FEASIBLE"
    assert bank.peak_traced_python_bytes > 0
    assert {
        "QB_SINGLE",
        "QB_DOUBLE",
        "NAKED_QB",
        "ZERO_BRINGBACK",
        "ONE_BRINGBACK",
        "TWO_PLUS_BRINGBACK",
    }.issubset(bank.coverage()["families"])


def test_candidate_bank_and_assignment_replay_are_byte_deterministic() -> None:
    slate, policy, _source, _entry = _policy(20)
    first = build_classic_candidate_bank(slate, _objective(slate), policy)
    second = build_classic_candidate_bank(slate, _objective(slate), policy)
    assert candidate_bank_bytes(policy, first) == candidate_bank_bytes(policy, second)
    first_selection = solve_classic_portfolio(policy, first)
    second_selection = solve_classic_portfolio(policy, second)
    assert first_selection.selected_candidate_indexes == second_selection.selected_candidate_indexes
    first_pairs = exact_classic_assignments(policy.entry_ids, [first.candidates[index].roster for index in first_selection.selected_candidate_indexes])
    second_pairs = exact_classic_assignments(policy.entry_ids, [second.candidates[index].roster for index in second_selection.selected_candidate_indexes])
    candidate_hash = sha256_bytes(candidate_bank_bytes(policy, first))
    assert assignment_artifact_bytes(policy, first_pairs, candidate_bank_sha256=candidate_hash) == assignment_artifact_bytes(policy, second_pairs, candidate_bank_sha256=candidate_hash)


@pytest.mark.parametrize(
    ("mutator", "expected"),
    [
        (lambda values: {"source_policy_bytes": values["source_policy_bytes"] + b" "}, "SOURCE_POLICY_SHA256_MISMATCH"),
        (lambda values: {"normalized_policy_bytes": values["normalized_policy_bytes"] + b" "}, "NORMALIZED_POLICY"),
        (lambda values: {"salary_bytes": values["salary_bytes"] + b" "}, "SALARY_SHA256_MISMATCH"),
        (lambda values: {"entry_bytes": values["entry_bytes"] + b" "}, "ENTRY_SHA256_MISMATCH"),
        (lambda values: {"bound_artifacts": {"team_prior_sha256": (b"changed", sha256_bytes(b"team-prior"))}}, "TEAM_PRIOR_SHA256_MISMATCH"),
        (lambda values: {"candidate_bytes": values["candidate_bytes"] + b" "}, "CANDIDATE_BANK"),
        (lambda values: {"assignment_bytes": values["assignment_bytes"] + b" "}, "ASSIGNMENT"),
    ],
)
def test_every_artifact_mutation_fails_independent_audit(mutator, expected) -> None:
    slate, policy, source, entry_bytes = _policy(3)
    bank = build_classic_candidate_bank(slate, _objective(slate), policy)
    selection = solve_classic_portfolio(policy, bank)
    passed, candidate, assignment = _audit(slate, policy, source, entry_bytes, bank, selection)
    assert passed.passed
    values = {
        "source_policy_bytes": source,
        "normalized_policy_bytes": policy.canonical_bytes(),
        "salary_bytes": b"salary",
        "entry_bytes": entry_bytes,
        "candidate_bytes": candidate,
        "assignment_bytes": assignment,
    }
    changes = mutator(values)
    audit, _candidate, _assignment = _audit(
        slate, policy, source, entry_bytes, bank, selection, **changes
    )
    assert not audit.passed
    assert any(expected in problem for problem in audit.problems)


def test_conflicting_policy_and_structural_capacity_fail_before_solver() -> None:
    slate = _slate()
    entries = ("E1", "E2", "E3")
    entry_sha = sha256_bytes(b"entry")
    document = classic_portfolio_policy_template(slate, entries, entry_sha256=entry_sha)
    document["controls"]["player_exposure_bounds"] = [
        {
            "underlying_id": row.underlying_id,
            "dk_id": row.dk_id,
            "minimum_entries": 0,
            "maximum_entries": 0,
            "hard": True,
        }
        for row in slate.players
    ]
    validation = validate_classic_portfolio_policy_bytes(
        json.dumps(document).encode(),
        slate=slate,
        entry_ids=entries,
        entry_sha256=entry_sha,
    )
    assert not validation.valid
    assert any("CAPACITY_INSUFFICIENT" in blocker for blocker in validation.blockers())


def test_candidate_bank_reports_structural_lineup_infeasibility() -> None:
    slate, policy, _source, _entry = _policy(1)
    all_qbs = tuple(row.dk_id for row in slate.players if row.position == "QB")
    bank = build_classic_candidate_bank(
        slate,
        _objective(slate),
        policy,
        excluded_ids=all_qbs,
    )
    assert bank.status == "STRUCTURAL_INFEASIBILITY"
    assert bank.blocking


def test_exhaustive_modeled_infeasibility_and_incomplete_bank_exhaustion_are_distinct() -> None:
    slate, policy, _source, _entry = _policy(3)
    real = build_classic_candidate_bank(slate, _objective(slate), policy)
    one = real.candidates[:2]
    exhaustive = ClassicCandidateBank(
        one, "EXHAUSTIVE_COMPLETION", True, 2, 3, 0.0, 1, 2, 0, 0.0, "kInfeasible", (), (), "MODELED_BANK_INFEASIBILITY"
    )
    incomplete = ClassicCandidateBank(
        one, "BOUNDED_COMPLETION", False, 2, 3, 0.0, 1, 2, 0, 0.0, "kOptimal", (), (), "INCOMPLETE_BANK_EXHAUSTION"
    )
    assert solve_classic_portfolio(policy, exhaustive).status == "MODELED_BANK_INFEASIBILITY"
    assert solve_classic_portfolio(policy, incomplete).status == "INCOMPLETE_BANK_EXHAUSTION"


@pytest.mark.parametrize(
    ("model_status", "expected"),
    [
        ("kTimeLimit", "CANDIDATE_BANK_TIMEOUT"),
        ("kIterationLimit", "CANDIDATE_BANK_SEARCH_LIMIT"),
        ("kSolveError", "CANDIDATE_BANK_SOLVER_ERROR"),
    ],
)
def test_candidate_timeout_search_limit_and_solver_error_are_distinct(
    monkeypatch, model_status, expected
) -> None:
    from nfl_dfs import classic_portfolio as module

    class StubOptimizer:
        def __init__(self, *_args, **_kwargs):
            pass

        def add_required_row(self, *_args):
            pass

        def add_selected_count_bounds(self, *_args, **_kwargs):
            pass

        def add_classic_qb_correlation_bounds(self, *_args, **_kwargs):
            pass

        def add_no_good(self, *_args):
            pass

        def set_time_limit(self, *_args):
            pass

        def solve(self, *_args):
            return SimpleNamespace(
                status="NO_SOLUTION",
                roster=None,
                model_status=model_status,
                node_count=None,
                mip_gap=None,
            )

    monkeypatch.setattr(module, "LineupOptimizer", StubOptimizer)
    slate, policy, _source, _entry = _policy(1)
    bank = build_classic_candidate_bank(slate, _objective(slate), policy)
    assert bank.status == expected
    assert bank.blocking


@pytest.mark.parametrize(
    ("model_status", "expected"),
    [
        (highspy.HighsModelStatus.kTimeLimit, "PORTFOLIO_SELECTION_TIMEOUT"),
        (highspy.HighsModelStatus.kIterationLimit, "PORTFOLIO_SELECTION_SEARCH_LIMIT"),
        (highspy.HighsModelStatus.kSolveError, "PORTFOLIO_SELECTION_SOLVER_ERROR"),
    ],
)
def test_nonoptimal_and_solver_error_selection_states_fail_closed(model_status, expected) -> None:
    slate, policy, _source, _entry = _policy(1)
    bank = build_classic_candidate_bank(slate, _objective(slate), policy)

    class StubHighs:
        def setOptionValue(self, *_args):
            pass

        def addVars(self, *_args):
            pass

        def changeColsIntegrality(self, *_args):
            pass

        def changeObjectiveSense(self, *_args):
            pass

        def changeColsCost(self, *_args):
            pass

        def addRow(self, *_args):
            pass

        def run(self):
            pass

        def getModelStatus(self):
            return model_status

        def getInfo(self):
            return SimpleNamespace(mip_gap=float("inf"), mip_node_count=0)

        def getSolution(self):
            return SimpleNamespace(value_valid=False, col_value=[])

    result = solve_classic_portfolio(policy, bank, solver_factory=StubHighs)
    assert result.status == expected
    assert not result.passed


def test_c3_full_prior_review_writes_bound_review_package_and_replays(tmp_path: Path) -> None:
    salary, entry, package, role, status, _inactive = _fixture(
        tmp_path / "fixture", entries=3
    )
    from nfl_dfs.dk import parse_entries, parse_salaries

    slate = parse_salaries(salary)
    entries = parse_entries(entry)
    document = classic_portfolio_policy_template(
        slate,
        tuple(item.entry_id for item in entries.authorizations),
        entry_sha256=entries.raw_hash,
    )
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(json.dumps(document, indent=2), encoding="utf-8")
    validation = validate_classic_portfolio_policy_bytes(
        policy_path.read_bytes(),
        slate=slate,
        entry_ids=tuple(item.entry_id for item in entries.authorizations),
        entry_sha256=entries.raw_hash,
    )
    assert validation.policy is not None and validation.valid
    normalized = write_normalized_classic_portfolio_policy(
        tmp_path / "policy.normalized.json", validation.policy
    )

    def run(name: str):
        return run_prior_review(
            salary_csv=salary,
            entry_csv=entry,
            label="classic-c2",
            as_of=AS_OF,
            run_root=tmp_path / name / "run",
            output_root=tmp_path / name / "out",
            prior_package_dir=package,
            build_priors=True,
            official_status_csv=status,
            offensive_role_evidence_json=role,
            portfolio_policy=validation.policy,
            portfolio_policy_source_path=policy_path,
            portfolio_policy_source_sha256=sha256_file(policy_path),
            portfolio_policy_normalized_path=normalized,
            portfolio_policy_normalized_sha256=sha256_file(normalized),
            project=build_projection_package,
        )

    first = run("first")
    second = run("second")
    assert not first.blocked, first.blockers
    assert first.profile_version == "cowork_classic_prior_review_c3_v1"
    assert first.reports["classic_portfolio_audit"]["status"] == "PASS"
    for key in (
        "classic_candidate_bank",
        "classic_assignment",
        "classic_portfolio_audit",
        "selection_report",
        "complete_slate_coverage",
        "classic_selected_scores",
        "classic_export_audit",
        "bulk_entry_csv",
        "readable_review_json",
        "readable_review_html",
    ):
        assert Path(first.artifacts[key]).is_file()
        assert first.hashes[key] == second.hashes[key]
    assert json.loads(Path(first.artifacts["selection_report"]).read_text())["schema_version"] == "nfl_classic_prior_review_selection_c2_v1"
    # Since Q1C each run also writes `assignments.csv`, the nine-slot
    # `nfl_assignment_csv_v1` record `settle` reads. It is deterministic like
    # every other bound artifact, and it is not an upload shape: no Contest ID,
    # Contest Name, Entry Fee or instructions block, so DraftKings would reject
    # it. The upload-shape prohibitions below are unchanged.
    assert len(list(tmp_path.rglob("assignments.csv"))) == 2
    assert first.hashes["assignments"] == second.hashes["assignments"]
    assert len(list(tmp_path.rglob("DK_REVIEW_ENTRY_*.csv"))) == 2
    assert not list(tmp_path.rglob("DK_UPLOAD_*.csv"))


def test_c2_required_player_without_current_activity_stops_before_publish(
    tmp_path: Path,
) -> None:
    salary, entry, package, role, status, _inactive = _fixture(
        tmp_path / "fixture", entries=1
    )
    from nfl_dfs.dk import parse_entries, parse_salaries

    slate = parse_salaries(salary)
    entries = parse_entries(entry)
    required = next(row for row in slate.players if row.position == "QB")
    status_lines = status.read_text(encoding="utf-8").splitlines()
    status.write_text(
        "\n".join(
            line for line in status_lines if f",{required.dk_id}," not in line
        )
        + "\n",
        encoding="utf-8",
        newline="",
    )
    document = classic_portfolio_policy_template(
        slate,
        tuple(item.entry_id for item in entries.authorizations),
        entry_sha256=entries.raw_hash,
        controls={
            "player_exposure_bounds": [
                {
                    "underlying_id": required.underlying_id,
                    "dk_id": required.dk_id,
                    "minimum_entries": 1,
                    "maximum_entries": 1,
                    "hard": True,
                }
            ]
        },
    )
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(json.dumps(document, indent=2), encoding="utf-8")
    validation = validate_classic_portfolio_policy_bytes(
        policy_path.read_bytes(),
        slate=slate,
        entry_ids=tuple(item.entry_id for item in entries.authorizations),
        entry_sha256=entries.raw_hash,
    )
    assert validation.policy is not None and validation.valid
    normalized = write_normalized_classic_portfolio_policy(
        tmp_path / "policy.normalized.json", validation.policy
    )
    outcome = run_prior_review(
        salary_csv=salary,
        entry_csv=entry,
        label="classic-c2-missing-activity",
        as_of=AS_OF,
        run_root=tmp_path / "run",
        output_root=tmp_path / "out",
        prior_package_dir=package,
        build_priors=True,
        official_status_csv=status,
        offensive_role_evidence_json=role,
        portfolio_policy=validation.policy,
        portfolio_policy_source_path=policy_path,
        portfolio_policy_source_sha256=sha256_file(policy_path),
        portfolio_policy_normalized_path=normalized,
        portfolio_policy_normalized_sha256=sha256_file(normalized),
        project=build_projection_package,
    )
    assert outcome.blocked
    assert outcome.blockers[0].startswith("SELECTED_CURRENT_EVIDENCE_REQUIRED:")
    assert required.underlying_id in outcome.blockers[0]
    assert "classic_candidate_bank" not in outcome.artifacts
    assert "classic_assignment" not in outcome.artifacts
    assert "selection_report" not in outcome.artifacts


def test_one_cowork_command_dispatches_classic_c3_review_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nfl_dfs import cli
    from nfl_dfs.dk import parse_entries, parse_salaries
    from .test_prior_review_profile import _cowork_args

    salary, entry, package, role, status, _inactive = _fixture(
        tmp_path / "fixture", entries=3
    )
    attachments = tmp_path / "attachments"
    attachments.mkdir()
    attached_salary = attachments / "salary.csv"
    attached_entry = attachments / "entries.csv"
    attached_salary.write_bytes(salary.read_bytes())
    attached_entry.write_bytes(entry.read_bytes())
    slate = parse_salaries(attached_salary)
    entries = parse_entries(attached_entry)
    policy_path = tmp_path / "classic_policy.json"
    policy_path.write_text(
        json.dumps(
            classic_portfolio_policy_template(
                slate,
                tuple(item.entry_id for item in entries.authorizations),
                entry_sha256=entries.raw_hash,
            ),
            indent=2,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(cli, "DEFAULT_RUNS_DIR", tmp_path / "runs")
    code = cli.command_cowork_run(
        _cowork_args(
            tmp_path,
            attachments,
            label="classic-c2-cli",
            run_id="classic-c2-cli",
            prior_package_dir=str(package),
            build_priors=True,
            official_status_csv=str(status),
            offensive_role_evidence_json=str(role),
            portfolio_policy_json=str(policy_path),
            as_of=AS_OF.isoformat(),
        )
    )
    assert code == 0
    report = json.loads(
        (tmp_path / "outputs" / "classic-c2-cli" / "cowork_run.json").read_text(
            encoding="utf-8"
        )
    )
    assert report["stage"] == "PRIOR_ONLY_CLASSIC_C3_REVIEW_EXPORT"
    assert report["FILE_VALID"] is True
    assert report["MODEL_STATUS"] == "PRIOR_ONLY"
    assert report["RELEASE_DECISION"] == "DO_NOT_UPLOAD"
    assert report["portfolio_policy"]["enforcement_status"] == (
        "ENFORCED_AND_INDEPENDENTLY_AUDITED"
    )
    for key in (
        "classic_candidate_bank",
        "classic_assignment",
        "classic_portfolio_audit",
        "selection_report",
        "complete_slate_coverage",
        "classic_selected_scores",
        "classic_export_audit",
        "bulk_entry_csv",
        "readable_review_json",
        "readable_review_html",
    ):
        assert Path(report["prior_review_artifacts"][key]).is_file()
    assert Path(report["review_workbook"]).is_file()
    assert len(list(tmp_path.rglob("DK_REVIEW_ENTRY_*.csv"))) == 1
    assert not list(tmp_path.rglob("DK_UPLOAD_*.csv"))


def test_c3_enforcement_never_calls_quantitative_or_later_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nfl_dfs import (
        cli,
        economics,
        field,
        ownership,
        portfolio,
        prior_review as prior_module,
    )
    from nfl_dfs.dk import parse_entries, parse_salaries
    from .test_prior_review_profile import _cowork_args

    def forbidden(*_args, **_kwargs):
        raise AssertionError("prohibited C3-or-later path called")

    monkeypatch.setattr(economics, "evaluate_candidates_against_field", forbidden)
    monkeypatch.setattr(field, "generate_opponent_field", forbidden)
    monkeypatch.setattr(ownership, "cold_start_states", forbidden)
    monkeypatch.setattr(portfolio, "select_portfolio", forbidden)
    for name in (
        "evaluate_candidates_against_field",
        "generate_opponent_field",
        "cold_start_states",
        "select_portfolio",
        "write_assignments_csv",
    ):
        monkeypatch.setattr(cli, name, forbidden)

    # Since Q1C the Classic prior-review path does write `assignments.csv`, so
    # that a Classic run can bind its own selection into a pre-lock manifest and
    # become settleable. The real hazard the old blanket ban guarded against is
    # narrower and is still checked here: writing a Showdown-shaped six-column
    # CPT/FLEX file for a nine-slot Classic roster. A spy that asserts the mode
    # is a stronger check than refusing the call, because it also proves the
    # geometry is right rather than only that nothing happened.
    real_writer = prior_module.write_assignments_csv
    observed_modes: list[EngineMode] = []

    def spy(path, assignments, *, entry_order=None, mode=EngineMode.SHOWDOWN):
        observed_modes.append(mode)
        return real_writer(path, assignments, entry_order=entry_order, mode=mode)

    monkeypatch.setattr(prior_module, "write_assignments_csv", spy)

    salary, entry, package, role, status, _inactive = _fixture(
        tmp_path / "fixture", entries=1
    )
    attachments = tmp_path / "attachments"
    attachments.mkdir()
    attached_salary = attachments / "salary.csv"
    attached_entry = attachments / "entries.csv"
    attached_salary.write_bytes(salary.read_bytes())
    attached_entry.write_bytes(entry.read_bytes())
    slate = parse_salaries(attached_salary)
    entries = parse_entries(attached_entry)
    policy_path = tmp_path / "classic_policy.json"
    policy_path.write_text(
        json.dumps(
            classic_portfolio_policy_template(
                slate,
                tuple(item.entry_id for item in entries.authorizations),
                entry_sha256=entries.raw_hash,
            )
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(cli, "DEFAULT_RUNS_DIR", tmp_path / "runs")
    code = cli.command_cowork_run(
        _cowork_args(
            tmp_path,
            attachments,
            label="classic-c2-boundary",
            run_id="classic-c2-boundary",
            prior_package_dir=str(package),
            build_priors=True,
            official_status_csv=str(status),
            offensive_role_evidence_json=str(role),
            portfolio_policy_json=str(policy_path),
            as_of=AS_OF.isoformat(),
        )
    )
    assert code == 0
    # Nine-slot Classic geometry, never the six-column Showdown shape.
    assert observed_modes == [EngineMode.CLASSIC], observed_modes
    assert len(list(tmp_path.rglob("prior_only_readable_review.html"))) == 1
    assert len(list(tmp_path.rglob("DK_REVIEW_ENTRY_*.csv"))) == 1
    assert not list(tmp_path.rglob("DK_UPLOAD_*.csv"))


def test_c3_readable_reconciliation_failure_removes_new_review_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nfl_dfs import cli
    from nfl_dfs.dk import parse_entries, parse_salaries
    from .test_prior_review_profile import _cowork_args

    salary, entry, package, role, status, _inactive = _fixture(
        tmp_path / "fixture", entries=1
    )
    attachments = tmp_path / "attachments"
    attachments.mkdir()
    attached_salary = attachments / "salary.csv"
    attached_entry = attachments / "entries.csv"
    attached_salary.write_bytes(salary.read_bytes())
    attached_entry.write_bytes(entry.read_bytes())
    slate = parse_salaries(attached_salary)
    entries = parse_entries(attached_entry)
    policy_path = tmp_path / "classic_policy.json"
    policy_path.write_text(
        json.dumps(
            classic_portfolio_policy_template(
                slate,
                tuple(item.entry_id for item in entries.authorizations),
                entry_sha256=entries.raw_hash,
            )
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(cli, "DEFAULT_RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(
        cli,
        "verify_readable_review_artifacts",
        lambda **_kwargs: ("FORCED_POST_PUBLICATION_DISPLAY_MUTATION",),
    )
    code = cli.command_cowork_run(
        _cowork_args(
            tmp_path,
            attachments,
            label="classic-c3-display-failure",
            run_id="classic-c3-display-failure",
            prior_package_dir=str(package),
            build_priors=True,
            official_status_csv=str(status),
            offensive_role_evidence_json=str(role),
            portfolio_policy_json=str(policy_path),
            as_of=AS_OF.isoformat(),
        )
    )
    assert code == 2
    report = json.loads(
        (
            tmp_path
            / "outputs"
            / "classic-c3-display-failure"
            / "cowork_run.json"
        ).read_text(encoding="utf-8")
    )
    assert report["stage"] == "PRIOR_REVIEW_READABLE_REVIEW_BLOCKED"
    assert report["FILE_VALID"] is False
    assert report["RELEASE_DECISION"] == "DO_NOT_UPLOAD"
    assert report["export"]["bulk_entry_csv"] is None
    assert report["export"]["downstream_audit"] is None
    for key in (
        "classic_export_audit",
        "bulk_entry_csv",
        "readable_review_json",
        "readable_review_html",
    ):
        assert key not in report["prior_review_artifacts"]
    assert not list(tmp_path.rglob("DK_REVIEW_ENTRY_*.csv"))
    assert not list(tmp_path.rglob("classic_review_export_audit.json"))
    assert not list(tmp_path.rglob("prior_only_readable_review.json"))
    assert not list(tmp_path.rglob("prior_only_readable_review.html"))
    assert not list(tmp_path.rglob("DK_UPLOAD_*.csv"))
