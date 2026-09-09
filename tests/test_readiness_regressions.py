"""Independent regressions found while rehearsing the September Showdown flow."""
from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import numpy as np

from nfl_dfs import cli, preflight
from nfl_dfs import prior_review as prior_review_module
from nfl_dfs.cowork import CoworkRunRequest, resolve_request_inputs
from nfl_dfs.dk import parse_salaries
from nfl_dfs.evidence import parse_official_inactive_snapshot
from nfl_dfs.hashing import sha256_file
from nfl_dfs.prior_review import run_prior_review
from nfl_dfs.learning import evaluate_challenger
from nfl_dfs.model_validation import validate_simulation_draws
from nfl_dfs.training import rolling_origin_splits, fit_weekly_ridge_challenger
from nfl_dfs.priors import _weather_evidence_basis, PriorsBuildError

from .test_cowork import _attachment_pair
from .test_kicker_roles import _write_evidence
from .test_prior_review_profile import AS_OF, _prepared_run
from .test_w6_live_preflight import SALARY_CSV, _certified


def _statuses(path, slate, ids, *, url="https://www.nfl.com/injuries/", inactive=(), observed=None):
    when = observed or slate.games[0].lock_at - timedelta(hours=1)
    by_id = {p.dk_id: p for p in slate.players}
    path.write_text(
        "TEAM,PLAYER_OR_GSIS_ID,STATUS,SOURCE_URL,OBSERVED_AT\n"
        + "".join(
            f"{by_id[dk].team},{dk},{'INACTIVE' if dk in inactive else 'ACTIVE'},{url},{when.isoformat()}\n"
            for dk in ids
        ), encoding="utf-8",
    )
    return path


@pytest.mark.parametrize("url", [
    "https://rehearsal.invalid/status", "https://localhost/status",
    "https://127.0.0.1/status", "https://user:password@www.nfl.com/status",
])
def test_official_status_rejects_unusable_provenance(tmp_path, showdown_slate, url):
    path = _statuses(tmp_path / "status.csv", showdown_slate,
                     [showdown_slate.players[0].dk_id], url=url)
    assert parse_official_inactive_snapshot(path, showdown_slate.players).problems


def test_official_status_detects_conflict_between_captain_and_flex(tmp_path, showdown_slate):
    person = showdown_slate.players[0].underlying_id
    ids = [p.dk_id for p in showdown_slate.players if p.underlying_id == person]
    path = _statuses(tmp_path / "status.csv", showdown_slate, ids, inactive=[ids[-1]])
    assert parse_official_inactive_snapshot(path, showdown_slate.players).problems


def test_certification_retains_asserted_official_source(tmp_path, showdown_slate):
    dk = showdown_slate.players[0].dk_id
    observed = showdown_slate.players[0].lock_at - timedelta(hours=1)
    path = _statuses(tmp_path / "status.csv", showdown_slate, [dk], observed=observed)
    evidence = cli._official_status_evidence(
        status_path=path, slate=showdown_slate, assignments={"test": (dk,)}, now=observed,
    )
    assert evidence.source_url == "https://www.nfl.com/injuries/"


def test_relative_cli_attachment_paths_resolve_from_working_directory(tmp_path, monkeypatch):
    _attachment_pair(tmp_path)
    monkeypatch.chdir(tmp_path)
    resolved, _ = resolve_request_inputs(
        CoworkRunRequest(), input_dir=".", allowed_roots=[tmp_path],
    )
    assert Path(resolved.salary_csv).is_absolute()


@pytest.mark.parametrize("mutation", ["missing_basis", "string_boolean", "stored_blocker"])
def test_preflight_cannot_repair_malformed_certification(tmp_path, classic_slate, classic_entries, mutation):
    path, _ = _certified(tmp_path, classic_slate, classic_entries,
                          expires_at=datetime.now(timezone.utc) + timedelta(hours=2))
    data = json.loads(path.read_text())
    if mutation == "missing_basis":
        data.pop("certification_basis")
    elif mutation == "string_boolean":
        data["FILE_VALID"] = "false"
    else:
        data["blockers"] = ["PENDING_INDEPENDENT_REVIEW"]
    path.write_text(json.dumps(data), encoding="utf-8")
    report = preflight.live_pre_upload_check(path, salaries=SALARY_CSV)
    assert report["RELEASE_DECISION"] == "DO_NOT_UPLOAD"


def test_preflight_missing_policy_fails_closed(tmp_path, classic_slate, classic_entries, monkeypatch):
    path, _ = _certified(tmp_path, classic_slate, classic_entries,
                          expires_at=datetime.now(timezone.utc) + timedelta(hours=2))
    monkeypatch.setattr(preflight, "PROJECT_ROOT", tmp_path / "missing")
    report = preflight.live_pre_upload_check(path, salaries=SALARY_CSV)
    assert report["RELEASE_DECISION"] == "DO_NOT_UPLOAD"
    assert any("POLICY" in b for b in report["blockers"])


def test_model_preflight_requires_model_specific_evidence(tmp_path, classic_slate, classic_entries):
    path, _ = _certified(tmp_path, classic_slate, classic_entries,
                          expires_at=datetime.now(timezone.utc) + timedelta(hours=2))
    data = json.loads(path.read_text())
    data.update(certification_basis="MODEL_ASSISTED", MODEL_STATUS="PROSPECTIVELY_VALIDATED")
    path.write_text(json.dumps(data), encoding="utf-8")
    report = preflight.live_pre_upload_check(path, salaries=SALARY_CSV)
    assert report["RELEASE_DECISION"] == "DO_NOT_UPLOAD"
    assert any("player_opportunity_evidence" in b for b in report["blockers"])


@pytest.mark.parametrize("mutation", ["omitted_player", "inactive_value"])
def test_preflight_reconciles_activity_with_actual_export_rosters(tmp_path, classic_slate, classic_entries, mutation):
    path, _ = _certified(tmp_path, classic_slate, classic_entries,
                         expires_at=datetime.now(timezone.utc) + timedelta(hours=2))
    data = json.loads(path.read_text())
    status = next(e for e in data["evidence"] if e["field"] == "official_inactive_status")
    dk = next(iter(status["value"]))
    if mutation == "omitted_player":
        status["value"].pop(dk)
    else:
        status["value"][dk] = "INACTIVE"
    path.write_text(json.dumps(data), encoding="utf-8")
    report = preflight.live_pre_upload_check(path, salaries=SALARY_CSV)
    assert report["RELEASE_DECISION"] == "DO_NOT_UPLOAD"


def test_prior_review_applies_supplied_inactive_status_to_both_roles(tmp_path):
    salary, entries, package, project = _prepared_run(tmp_path, expires_at=AS_OF + timedelta(hours=6))
    slate = parse_salaries(salary)
    scratched = next(p for p in slate.players if p.name == "NE Kicker" and p.role == "FLEX")
    path = _statuses(tmp_path / "official.csv", slate, [scratched.dk_id],
                     inactive=[scratched.dk_id], observed=AS_OF)
    outcome = run_prior_review(
        salary_csv=salary, entry_csv=entries, label="inactive-test", as_of=AS_OF,
        run_root=tmp_path / "run", output_root=tmp_path / "out",
        prior_package_dir=package, project=project, official_status_csv=path,
    )
    assert outcome.file_valid, outcome.blockers
    excluded = {p.dk_id for p in slate.players if p.underlying_id == scratched.underlying_id}
    assert outcome.hashes["official_status_csv"] == sha256_file(path)
    for lineup in outcome.reports["selection"]["lineups"]:
        assert not (set(lineup["roster"]) & excluded)
    assert outcome.reports["selection"]["participation"]["operator_excluded_people"] == 1


def test_late_inactive_change_invalidates_a_supported_kicker_allocation(tmp_path):
    salary, entries, package, project = _prepared_run(
        tmp_path, expires_at=AS_OF + timedelta(hours=6)
    )
    slate = parse_salaries(salary)
    scratched = next(
        player for player in slate.players if player.name == "NE Kicker" and player.role == "FLEX"
    )
    roles = _write_evidence(
        tmp_path / "roles",
        slate,
        {
            "NE": [("NE|K|NE Kicker", 1.0)],
            "SEA": [("SEA|K|Sea Kicker", 1.0)],
        },
        as_of=AS_OF,
    )
    status = _statuses(
        tmp_path / "official.csv",
        slate,
        [scratched.dk_id],
        inactive=[scratched.dk_id],
        observed=AS_OF,
    )
    outcome = run_prior_review(
        salary_csv=salary,
        entry_csv=entries,
        label="inactive-role-test",
        as_of=AS_OF,
        run_root=tmp_path / "run",
        output_root=tmp_path / "out",
        prior_package_dir=package,
        project=project,
        official_status_csv=status,
        role_evidence_json=roles,
    )
    assert outcome.blocked
    assert any("KICKER_ROLE_POSITIVE_SHARE_NOT_ELIGIBLE" in value for value in outcome.blockers)
    assert not list((tmp_path / "out").rglob("DK_REVIEW_ENTRY_*.csv"))


def test_prior_review_refuses_stale_supplied_activity(tmp_path):
    salary, entries, package, project = _prepared_run(tmp_path, expires_at=AS_OF + timedelta(hours=6))
    slate = parse_salaries(salary)
    path = _statuses(tmp_path / "official.csv", slate, [slate.players[0].dk_id],
                     observed=AS_OF - timedelta(hours=4))
    outcome = run_prior_review(
        salary_csv=salary, entry_csv=entries, label="stale-test", as_of=AS_OF,
        run_root=tmp_path / "run", output_root=tmp_path / "out",
        prior_package_dir=package, project=project, official_status_csv=path,
    )
    assert not outcome.file_valid
    assert any("OFFICIAL_STATUS_STALE" in b for b in outcome.blockers)
    assert not list((tmp_path / "out").rglob("*.csv"))


def test_insufficient_validation_samples_cannot_pass():
    result = validate_simulation_draws(
        actual=np.array([1.0]), model_draws=np.ones((100, 1)),
        baseline_draws=np.zeros((100, 1)), positions=np.array(["WR"]),
        model_dependencies={"pair": 0.5}, dependency_bands={"pair": (0.0, 1.0)},
    )
    assert result.sample_warnings
    assert result.status != "PASS"
    assert result.blockers


def test_weather_capture_does_not_gain_freshness_from_a_new_run():
    with pytest.raises(PriorsBuildError, match="WEATHER_CAPTURE_STALE"):
        _weather_evidence_basis(
            "https://api.weather.gov/gridpoints/SEW/125,67/forecast",
            AS_OF - timedelta(hours=7), as_of=AS_OF,
        )


@pytest.mark.parametrize("expire_during_selection", [False, True])
def test_live_review_advances_clock_and_rechecks_export_expiry(tmp_path, monkeypatch, expire_during_selection):
    salary, entries, package, original_project = _prepared_run(tmp_path, expires_at=AS_OF + timedelta(hours=6))
    stamps = iter([AS_OF, AS_OF + timedelta(minutes=1), AS_OF + timedelta(minutes=2)])
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return next(stamps)
    monkeypatch.setattr(prior_review_module, "datetime", Clock)
    def project(**kwargs):
        assert datetime.fromisoformat(kwargs["as_of"]) > AS_OF
        result = original_project(**kwargs)
        if expire_during_selection:
            result = replace(result, expires_at=(AS_OF + timedelta(seconds=90)).isoformat())
        return result
    outcome = run_prior_review(
        salary_csv=salary, entry_csv=entries, label="live-clock", as_of=None,
        run_root=tmp_path / "run", output_root=tmp_path / "out",
        prior_package_dir=package, project=project,
    )
    assert outcome.file_valid is not expire_during_selection, outcome.blockers
    if expire_during_selection:
        assert any("PROJECTION_EXPIRED_DURING_SELECTION" in b for b in outcome.blockers)


@pytest.mark.parametrize("slates,gates", [(0, True), (20, False)])
def test_promotion_requires_history_and_prospective_field_gates(slates, gates):
    result = evaluate_challenger(
        comparable_settled_slates=slates, prospective_field_gates=gates,
        reproducible=True, integrity_pass=True, rolling_origin_improvement=True,
        calibration_pass=True, drift_pass=True, no_regression=True,
    )
    assert not result.promote


def test_rolling_origin_keeps_each_outcome_time_in_one_partition():
    stamps = [AS_OF + timedelta(days=i // 3) for i in range(18)]
    for train, validation in rolling_origin_splits(stamps, minimum_train=4, validation_size=4):
        assert max(stamps[i] for i in train) < min(stamps[i] for i in validation)


def test_training_outcomes_must_precede_validation_feature_cutoff():
    outcomes = [AS_OF + timedelta(days=i) for i in range(8)]
    with pytest.raises(ValueError, match="prediction cutoff"):
        fit_weekly_ridge_challenger(
            features=np.ones((8, 1)), target=np.arange(8),
            feature_as_of=[AS_OF - timedelta(days=1)] * 8, outcome_at=outcomes,
            minimum_train=4, validation_size=2,
        )
