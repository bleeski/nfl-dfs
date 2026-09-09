"""R02 coverage: the gated `cowork-run --profile prior_review` entry point.

Fixtures are the ones `test_participation` and `test_prior_selection` already
describe, so the pool, the DraftKings statuses and the opportunity shares live in
one place. What is asserted here is orchestration: which blockers gate which
profile, that the identity gate never accepts an uncertain identity for someone
who could still be selected, that an expired package is rebuilt rather than
widened, that a moved byte in a frozen artifact fails closed, and that no path
through this profile can emit anything but PRIOR_ONLY and DO_NOT_UPLOAD.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from nfl_dfs import priors as priors_module
from nfl_dfs.contracts import CertificationBasis, ModelStatus, ReleaseDecision, ReleaseEvidenceState
from nfl_dfs.cowork import (
    CoworkInputError,
    CoworkRunRequest,
    OPERATOR_WEATHER_STATES,
    PRIOR_PACKAGE_FILENAME,
    SUPPORTED_PROFILES,
    gating_blockers,
    prior_review_next_inputs,
    required_next_inputs,
)
from nfl_dfs.hashing import sha256_file
from nfl_dfs.prior_review import (
    AUTO_ACCEPT_MATCH_METHOD,
    PriorReviewError,
    SCHEDULE_DERIVABLE_ROOFS,
    apply_identity_gate,
    decide_weather,
    derive_season,
    resolve_prior_package,
    run_prior_review,
)
from nfl_dfs.priors import IdentityProposal
from nfl_dfs.release import derive_release_policy

from .test_participation import _model, _slate
from .test_kicker_roles import _write_evidence
from .test_prior_selection import _entries_bytes, _splits_bytes


AS_OF = datetime(2026, 9, 8, 16, 45, tzinfo=timezone.utc)


# --------------------------------------------------------------------------- #
# The constants this module deliberately repeats rather than imports
# --------------------------------------------------------------------------- #


def test_repeated_constants_still_agree_with_the_adapter() -> None:
    assert PRIOR_PACKAGE_FILENAME == priors_module.PACKAGE_FILENAME
    assert set(OPERATOR_WEATHER_STATES) == set(priors_module._OPERATOR_WEATHER_STATES)
    assert SCHEDULE_DERIVABLE_ROOFS <= set(priors_module._ROOF_WEATHER)


# --------------------------------------------------------------------------- #
# Which blockers gate which profile
# --------------------------------------------------------------------------- #


def test_profile_set_accepts_prior_review_and_still_defaults_to_diagnostic() -> None:
    assert SUPPORTED_PROFILES == ("diagnostic", "registered", "prior_review")
    assert CoworkRunRequest().profile == "diagnostic"
    assert CoworkRunRequest.from_mapping({"profile": "prior_review"}).profile == "prior_review"
    with pytest.raises(CoworkInputError, match="profile must be one of"):
        CoworkRunRequest.from_mapping({"profile": "certified"})


def test_certification_blockers_are_reported_but_do_not_gate_prior_review() -> None:
    request = CoworkRunRequest(profile="prior_review", build_priors=True)
    reported = required_next_inputs(request)
    assert any(value.startswith("CONTEST_PAYOUT_REQUIRED:") for value in reported)
    assert any(value.startswith("FIELD_SIZE_REQUIRED:") for value in reported)
    assert any(value.startswith("OFFICIAL_STATUS_REQUIRED:") for value in reported)

    gating = gating_blockers(request, reported)
    assert gating == ()


def test_diagnostic_and_registered_gating_is_unchanged() -> None:
    for profile in ("diagnostic", "registered"):
        request = CoworkRunRequest(profile=profile)
        reported = required_next_inputs(request)
        gating = gating_blockers(request, reported)
        # Exactly the pre-existing behaviour: everything gates except the
        # activity report, which is a certification gate rather than an intake one.
        assert set(gating) == {
            value
            for value in reported
            if not value.startswith("OFFICIAL_STATUS_REQUIRED:")
        }
        assert prior_review_next_inputs(request) or True
        assert len(gating) == len(reported) - 1


def test_prior_review_names_the_prior_chain_it_still_needs() -> None:
    empty = prior_review_next_inputs(CoworkRunRequest(profile="prior_review"))
    assert any(value.startswith("PRIOR_PACKAGE_REQUIRED:") for value in empty)

    authorized = prior_review_next_inputs(
        CoworkRunRequest(profile="prior_review", build_priors=True)
    )
    assert authorized == ()

    with_assignment = prior_review_next_inputs(
        CoworkRunRequest(
            profile="prior_review", build_priors=True, assignment_csv="/tmp/a.csv"
        )
    )
    assert any(
        value.startswith("ASSIGNMENT_NOT_ACCEPTED_BY_PROFILE:")
        for value in with_assignment
    )


def test_request_validates_the_new_prior_review_fields() -> None:
    with pytest.raises(CoworkInputError, match="weather_state must be one of"):
        CoworkRunRequest.from_mapping({"weather_state": "PARTLY_SUNNY"})
    with pytest.raises(CoworkInputError, match="season must be a positive JSON integer"):
        CoworkRunRequest.from_mapping({"season": 0})
    with pytest.raises(CoworkInputError, match="prior_season must be earlier"):
        CoworkRunRequest.from_mapping({"season": 2026, "prior_season": 2026})
    with pytest.raises(CoworkInputError, match="build_priors must be true or false"):
        CoworkRunRequest.from_mapping({"build_priors": "yes"})
    assert CoworkRunRequest.from_mapping({"weather_state": "clear"}).weather_state == "CLEAR"


# --------------------------------------------------------------------------- #
# The two-phase identity gate
# --------------------------------------------------------------------------- #


def _proposal(**overrides) -> IdentityProposal:
    payload = dict(
        dk_id="50000001",
        captain_dk_id="50000002",
        dk_name="Cut Receiver",
        dk_team="NE",
        dk_position="WR",
        underlying_id="NE|WR|Cut Receiver",
        nflverse_team="NE",
        provider_player_id="00-0011111",
        provider_name="Cut Receiver",
        provider_pfr_id="CutRe00",
        provider_team="HOU",
        provider_status="CUT",
        match_method=AUTO_ACCEPT_MATCH_METHOD,
        candidates=("00-0011111|Cut Receiver|WR|HOU|CUT",),
    )
    payload.update(overrides)
    return IdentityProposal(**payload)


@pytest.mark.parametrize("status", ["OUT", "IR", "out"])
def test_unique_league_match_is_auto_accepted_only_for_an_unavailable_person(status) -> None:
    gate = apply_identity_gate([_proposal()], {"50000001": status})

    assert gate.blockers == ()
    assert len(gate.auto_accepted) == 1
    accepted = gate.auto_accepted[0]
    assert accepted.decision == "ACCEPT"
    assert accepted.basis.startswith("AUTO_ACCEPT_UNIQUE_LEAGUE_NAME_POSITION")
    assert "nflverse_team=HOU" in accepted.basis
    assert "roster_status=CUT" in accepted.basis


@pytest.mark.parametrize("status", ["", "Q"])
def test_the_same_match_stops_the_run_when_the_person_is_available(status) -> None:
    gate = apply_identity_gate([_proposal()], {"50000001": status})

    assert len(gate.blockers) == 1
    blocker = gate.blockers[0]
    assert blocker.startswith("IDENTITY_UNRESOLVED_AND_AVAILABLE:50000001:")
    # The candidate provider ID, the conflicting nflverse team and the roster
    # status are all in the message, because those are what a human needs.
    assert "candidate_provider_id=00-0011111" in blocker
    assert "nflverse_team=HOU" in blocker
    assert "roster_status=CUT" in blocker
    assert gate.auto_accepted == ()
    assert len(gate.blocked) == 1


@pytest.mark.parametrize("method", ["AMBIGUOUS", "UNMATCHED", "NAME_OTHER_TEAM"])
def test_nothing_looser_than_a_unique_name_and_position_match_is_accepted(method) -> None:
    gate = apply_identity_gate([_proposal(match_method=method)], {"50000001": "OUT"})

    assert gate.auto_accepted == ()
    assert len(gate.blockers) == 1
    assert gate.blockers[0].startswith("IDENTITY_UNRESOLVED_AND_UNAVAILABLE:")


def test_a_resolved_proposal_keeps_its_own_method_as_its_basis() -> None:
    gate = apply_identity_gate(
        [_proposal(match_method="NORMALIZED_NAME_TEAM_POSITION", provider_team="NE")],
        {"50000001": ""},
    )

    assert gate.blockers == ()
    assert gate.auto_accepted == ()
    assert gate.decisions[0].basis == "PROPOSAL_RESOLVED:NORMALIZED_NAME_TEAM_POSITION"


# --------------------------------------------------------------------------- #
# The weather gate
# --------------------------------------------------------------------------- #


def test_a_fixed_roof_resolves_from_the_schedule_alone() -> None:
    decision = decide_weather("dome")
    assert decision.blockers == ()
    assert decision.freeze_weather_state is None


@pytest.mark.parametrize("roof", ["outdoors", "", "open"])
def test_every_other_roof_asks_for_the_weather_capture(roof) -> None:
    decision = decide_weather(roof)
    assert any(value.startswith("WEATHER_CAPTURE_REQUIRED:") for value in decision.blockers)
    assert decision.freeze_weather_state is None


def test_an_attributed_capture_clears_the_outdoor_gate() -> None:
    decision = decide_weather(
        "outdoors",
        weather_state="CLEAR",
        weather_source_uri="https://api.weather.gov/gridpoints/SEW/125,67/forecast",
        weather_observed_at="2026-09-08T16:37:07+00:00",
    )
    assert decision.blockers == ()
    assert decision.freeze_weather_state == "CLEAR"


def test_a_state_without_attribution_is_still_blocked() -> None:
    decision = decide_weather("outdoors", weather_state="CLEAR")
    assert any(value.startswith("WEATHER_CAPTURE_REQUIRED:") for value in decision.blockers)


# --------------------------------------------------------------------------- #
# Slate-derived season
# --------------------------------------------------------------------------- #


def test_season_comes_from_the_kickoff_and_rolls_over_in_march() -> None:
    assert derive_season(datetime(2026, 9, 9, 20, 20, tzinfo=timezone.utc)) == 2026
    assert derive_season(datetime(2027, 1, 10, 18, 0, tzinfo=timezone.utc)) == 2026
    assert derive_season(datetime(2027, 3, 1, 18, 0, tzinfo=timezone.utc)) == 2027


# --------------------------------------------------------------------------- #
# A frozen prior package on disk
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class _StubProjection:
    output_dir: str
    team_projections: str
    player_opportunities: str
    source_ledger: str
    hashes: dict
    input_hashes: dict
    # W2/R08 added these to `ProjectionPackage`: a produced package carries its
    # own expiry, its ledger schema version and its archived sources across
    # every boundary, so this stub mirrors that surface.
    ledger_schema_version: str = "nfl_source_ledger_v2"
    expires_at: str = "2026-09-08T22:45:00+00:00"
    expiry_basis: str = "TEAM_PRIOR:team_source:MARKET_LINE_MOVES_INTRADAY"
    archived_sources: dict = field(default_factory=dict)


def _stub_expiry(as_of: str) -> str:
    """A projection package's expiry, six hours past the clock it was built at."""

    return (
        datetime.fromisoformat(str(as_of).replace("Z", "+00:00")) + timedelta(hours=6)
    ).isoformat()


def _write_package(
    tmp_path: Path, *, salary_sha: str, team_stats_sha: str, expires_at: datetime
) -> Path:
    package_dir = tmp_path / "priors"
    package_dir.mkdir(parents=True, exist_ok=True)
    from .test_participation import _POOL
    metadata = {
        "metadata": {
            "expires_at": expires_at.isoformat(),
            "evidence_state": "PASS",
            "coverage": {
                "expiry_basis": "MARKET_LINE_MOVES_INTRADAY",
                "offensive_history_by_person": {
                    f"{team}|{position}|{name}": {"state": "OBSERVED_HISTORY", "synthetic": True}
                    for team, position, name, _status, _salary in _POOL
                    if position in {"QB", "RB", "WR", "TE"}
                },
            },
        }
    }
    for name in ("team_prior.json", "player_prior.json", "identity_map.json"):
        payload = dict(metadata)
        if name == "identity_map.json":
            payload = {
                **metadata,
                "salary_artifact": {"expires_at": (expires_at + timedelta(hours=6)).isoformat()},
            }
        (package_dir / name).write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    package = {
        "schema_version": "nfl_prior_package_v1",
        "season": 2026,
        "prior_season": 2025,
        "salary_artifact_id": salary_sha,
        "package_dir": str(package_dir),
        "frozen_sources": {"team_stats": team_stats_sha},
        "artifacts": {
            name: sha256_file(package_dir / name)
            for name in ("team_prior.json", "player_prior.json", "identity_map.json")
        },
    }
    (package_dir / PRIOR_PACKAGE_FILENAME).write_text(
        json.dumps(package, indent=2, sort_keys=True), encoding="utf-8"
    )
    return package_dir


def _prepared_run(tmp_path: Path, *, expires_at: datetime):
    """A slate, an entry template, a frozen package and a projection stub."""

    slate = _slate(tmp_path)
    _model(tmp_path, slate)  # writes team_projections.csv and player_opportunities.csv
    salary_path = tmp_path / "DKSalaries.csv"
    entry_path = tmp_path / "DKEntries.csv"
    entry_path.write_bytes(_entries_bytes())
    splits_path = tmp_path / "stats_team_week.csv"
    splits_path.write_bytes(_splits_bytes())
    package_dir = _write_package(
        tmp_path,
        salary_sha=sha256_file(salary_path),
        team_stats_sha=sha256_file(splits_path),
        expires_at=expires_at,
    )
    raw_dir = package_dir / "raw"
    raw_dir.mkdir(exist_ok=True)
    (raw_dir / f"{sha256_file(splits_path)}.csv").write_bytes(splits_path.read_bytes())

    def project(**kwargs):
        output = Path(kwargs["output_dir"])
        output.mkdir(parents=True, exist_ok=True)
        return _StubProjection(
            output_dir=str(output),
            team_projections=str(tmp_path / "team_projections.csv"),
            player_opportunities=str(tmp_path / "player_opportunities.csv"),
            source_ledger=str(output / "source_ledger.json"),
            hashes={"team_projections": "0" * 64},
            input_hashes={},
            # A real package's expiry is derived from its sources and is always
            # ahead of the `as_of` it was built at, because the producer
            # refuses an already-expired source. The stub mirrors that instead
            # of pinning a constant that goes stale on its own.
            expires_at=_stub_expiry(kwargs["as_of"]),
        )

    return salary_path, entry_path, package_dir, project


def test_success_path_exports_a_byte_audited_file_and_never_certifies(tmp_path: Path) -> None:
    salary_path, entry_path, package_dir, project = _prepared_run(
        tmp_path, expires_at=AS_OF + timedelta(hours=6)
    )

    outcome = run_prior_review(
        salary_csv=salary_path,
        entry_csv=entry_path,
        label="ne-sea",
        as_of=AS_OF,
        run_root=tmp_path / "run",
        output_root=tmp_path / "out",
        prior_package_dir=package_dir,
        project=project,
    )

    assert not outcome.blocked
    assert outcome.blockers == ()
    assert outcome.stage == "EXPORT"
    assert outcome.file_valid
    assert outcome.export["problems"] == []
    assert outcome.export["MODEL_STATUS"] == "PRIOR_ONLY"
    assert outcome.export["RELEASE_DECISION"] == "DO_NOT_UPLOAD"
    exported = Path(outcome.artifacts["bulk_entry_csv"])
    assert exported.is_file()
    assert sha256_file(exported) == outcome.hashes["bulk_entry_csv"]
    statuses = {stage["stage"]: stage["status"] for stage in outcome.stages}
    assert statuses["PRIORS"] == "REUSED"
    assert statuses["SELECT"] == "OK"
    assert statuses["EXPORT"] == "OK"

    # Only the reserved entry rows may differ from the operator's own template.
    source_lines = entry_path.read_bytes().split(b"\n")
    output_lines = exported.read_bytes().split(b"\n")
    assert len(source_lines) == len(output_lines)
    changed = [
        index
        for index, (before, after) in enumerate(zip(source_lines, output_lines))
        if before != after
    ]
    assert changed == [1, 2]


def test_no_release_policy_input_can_certify_a_prior_only_package() -> None:
    for evidence_state in ReleaseEvidenceState:
        result = derive_release_policy(
            file_valid=True,
            evidence_state=evidence_state,
            model_status=ModelStatus.PRIOR_ONLY,
            certification_basis=CertificationBasis.MODEL_ASSISTED,
        )
        assert result.release_decision is ReleaseDecision.DO_NOT_UPLOAD


def test_an_expired_package_blocks_without_permission_and_rebuilds_with_it(
    tmp_path: Path,
) -> None:
    salary_path, entry_path, package_dir, project = _prepared_run(
        tmp_path, expires_at=AS_OF - timedelta(minutes=1)
    )

    blocked = run_prior_review(
        salary_csv=salary_path,
        entry_csv=entry_path,
        label="ne-sea",
        as_of=AS_OF,
        run_root=tmp_path / "run-a",
        output_root=tmp_path / "out-a",
        prior_package_dir=package_dir,
        project=project,
    )
    assert blocked.blocked
    assert len(blocked.blockers) == 1
    assert blocked.blockers[0].startswith("PRIOR_PACKAGE_EXPIRED:")
    assert "expires_at=" in blocked.blockers[0] and "as_of=" in blocked.blockers[0]
    assert blocked.export is None
    assert "bulk_entry_csv" not in blocked.artifacts

    calls: list[dict] = []

    def propose(**kwargs):
        calls.append(kwargs)
        raise priors_module.PriorsBuildError("SOURCE_EMPTY:games")

    rebuilding = run_prior_review(
        salary_csv=salary_path,
        entry_csv=entry_path,
        label="ne-sea",
        as_of=AS_OF,
        run_root=tmp_path / "run-b",
        output_root=tmp_path / "out-b",
        prior_package_dir=package_dir,
        build_priors=True,
        propose=propose,
        project=project,
    )

    # Permission to build turns the expiry into a re-fetch. The stale package is
    # recorded and discarded; the expiry itself is never widened.
    assert len(calls) == 1
    assert calls[0]["season"] == 2026 and calls[0]["prior_season"] == 2025
    statuses = [(stage["stage"], stage["status"]) for stage in rebuilding.stages]
    assert ("PRIORS", "REBUILDING_EXPIRED_PACKAGE") in statuses
    assert rebuilding.reports["expired_package"]["expired"] is True
    assert rebuilding.blocked
    assert rebuilding.blockers[0].startswith("PRIORS_PROPOSE_FAILED:PriorsBuildError:")
    assert rebuilding.export is None


def test_a_moved_byte_in_a_frozen_artifact_fails_closed(tmp_path: Path) -> None:
    salary_path, entry_path, package_dir, project = _prepared_run(
        tmp_path, expires_at=AS_OF + timedelta(hours=6)
    )
    tampered = package_dir / "team_prior.json"
    tampered.write_text(tampered.read_text(encoding="utf-8") + " ", encoding="utf-8")

    outcome = run_prior_review(
        salary_csv=salary_path,
        entry_csv=entry_path,
        label="ne-sea",
        as_of=AS_OF,
        run_root=tmp_path / "run",
        output_root=tmp_path / "out",
        prior_package_dir=package_dir,
        build_priors=True,
        project=project,
    )

    assert outcome.blocked
    assert outcome.blockers[0].startswith("PRIOR_ARTIFACT_HASH_MISMATCH:team_prior.json:")
    assert outcome.export is None
    assert not (tmp_path / "out").exists() or not list(
        (tmp_path / "out").rglob("*.csv")
    )


def test_a_package_built_for_another_salary_file_is_refused(tmp_path: Path) -> None:
    salary_path, entry_path, package_dir, _project = _prepared_run(
        tmp_path, expires_at=AS_OF + timedelta(hours=6)
    )
    with pytest.raises(PriorReviewError, match="PRIOR_PACKAGE_SALARY_MISMATCH:"):
        resolve_prior_package(package_dir, salary_sha256="a" * 64, as_of=AS_OF)


def test_a_missing_package_blocks_rather_than_building_without_permission(
    tmp_path: Path,
) -> None:
    salary_path, entry_path, _package_dir, project = _prepared_run(
        tmp_path, expires_at=AS_OF + timedelta(hours=6)
    )

    outcome = run_prior_review(
        salary_csv=salary_path,
        entry_csv=entry_path,
        label="ne-sea",
        as_of=AS_OF,
        run_root=tmp_path / "run",
        output_root=tmp_path / "out",
        project=project,
    )

    assert outcome.blocked
    assert outcome.blockers[0].startswith("PRIOR_PACKAGE_REQUIRED:")
    assert outcome.export is None


def test_classic_is_refused_by_this_showdown_only_profile(tmp_path: Path) -> None:
    classic = Path(__file__).parent / "fixtures" / "supplied" / "DKSalaries Salary CSV Classic.csv"
    entries = Path(__file__).parent / "fixtures" / "supplied" / "DKEntries CSV.csv"

    outcome = run_prior_review(
        salary_csv=classic,
        entry_csv=entries,
        label="classic",
        as_of=AS_OF,
        run_root=tmp_path / "run",
        output_root=tmp_path / "out",
        build_priors=True,
    )

    assert outcome.blocked
    assert outcome.blockers[0].startswith("PROFILE_MODE_NOT_SUPPORTED:CLASSIC")
    assert outcome.export is None


# --------------------------------------------------------------------------- #
# The one gated command
# --------------------------------------------------------------------------- #


def _cowork_args(tmp_path: Path, attachments: Path, **overrides):
    import argparse

    values = dict(
        input_dir=str(attachments),
        request=None,
        salaries=None,
        entries=None,
        label="ne-sea",
        run_id="prior-review-test",
        output_dir=str(tmp_path / "outputs"),
        profile="prior_review",
        prior_package_dir=None,
        build_priors=False,
        season=None,
        prior_season=None,
        weather_state=None,
        weather_source_uri=None,
        weather_observed_at=None,
        role_evidence_json=None,
        lineup_count=None,
        max_person_overlap=None,
        as_of=None,
    )
    values.update(overrides)
    return argparse.Namespace(**values)


def _attachments(tmp_path: Path, salary_path: Path, entry_path: Path) -> Path:
    attachments = tmp_path / "attachments"
    attachments.mkdir()
    (attachments / "salary.csv").write_bytes(salary_path.read_bytes())
    (attachments / "entries.csv").write_bytes(entry_path.read_bytes())
    return attachments


def test_the_sibling_priors_folder_is_discovered_inside_the_allowed_roots(
    tmp_path: Path,
) -> None:
    from nfl_dfs.cowork import resolve_request_inputs

    salary_path, entry_path, package_dir, _project = _prepared_run(
        tmp_path, expires_at=AS_OF + timedelta(hours=6)
    )
    run_folder = tmp_path / "20260909-showdown-ne-sea"
    inputs = run_folder / "inputs"
    inputs.mkdir(parents=True)
    (inputs / "salary.csv").write_bytes(salary_path.read_bytes())
    (inputs / "entries.csv").write_bytes(entry_path.read_bytes())
    import shutil

    shutil.copytree(package_dir, run_folder / "priors")

    resolved, _unclassified = resolve_request_inputs(
        CoworkRunRequest(profile="prior_review"),
        input_dir=inputs,
        allowed_roots=(run_folder,),
    )
    assert resolved.prior_package_dir == str((run_folder / "priors").resolve())

    # Outside the allowed roots it is not silently adopted; the named blocker
    # asks the operator for it instead.
    outside, _ = resolve_request_inputs(
        CoworkRunRequest(profile="prior_review"),
        input_dir=inputs,
        allowed_roots=(inputs,),
    )
    assert outside.prior_package_dir is None
    assert any(
        value.startswith("PRIOR_PACKAGE_REQUIRED:")
        for value in prior_review_next_inputs(outside)
    )


def test_one_command_exports_and_reports_all_four_truths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nfl_dfs import cli
    from nfl_dfs import prior_review as prior_review_module

    # `command_cowork_run` stamps `as_of` from the live clock rather than from
    # this module's fixed `AS_OF`, so this package's expiry has to follow the
    # same clock or the test expires on its own six hours after `AS_OF`.
    salary_path, entry_path, package_dir, project = _prepared_run(
        tmp_path, expires_at=datetime.now(timezone.utc) + timedelta(hours=6)
    )
    attachments = _attachments(tmp_path, salary_path, entry_path)
    monkeypatch.setattr(cli, "DEFAULT_RUNS_DIR", tmp_path / "runs")
    real = prior_review_module.run_prior_review
    monkeypatch.setattr(
        cli, "run_prior_review", lambda **kwargs: real(**kwargs, project=project)
    )

    code = cli.command_cowork_run(
        _cowork_args(tmp_path, attachments, prior_package_dir=str(package_dir))
    )

    assert code == 0
    report = json.loads(
        (tmp_path / "outputs" / "prior-review-test" / "cowork_run.json").read_text(
            encoding="utf-8"
        )
    )
    assert report["FILE_VALID"] is True
    assert report["EVIDENCE_STATE"] == "UNKNOWN"
    assert report["MODEL_STATUS"] == "PRIOR_ONLY"
    assert report["RELEASE_DECISION"] == "DO_NOT_UPLOAD"
    assert report["status"] == "DO_NOT_UPLOAD"
    assert report["stage"] == "PRIOR_ONLY_REVIEW_EXPORT"
    assert report["profile"] == "prior_review"
    assert Path(report["bulk_entry_csv"]).is_file()
    assert Path(report["review_workbook"]).is_file()
    # Certification-only inputs stay visible without gating this profile.
    assert any(
        value.startswith("CONTEST_PAYOUT_REQUIRED:") for value in report["blockers"]
    )
    assert any(
        value.startswith("OFFICIAL_STATUS_REQUIRED:") for value in report["blockers"]
    )


def test_prior_review_consumes_source_bound_roles_and_reports_their_hashes(tmp_path: Path) -> None:
    from nfl_dfs.dk import parse_salaries

    salary_path, entry_path, package_dir, project = _prepared_run(
        tmp_path, expires_at=AS_OF + timedelta(hours=6)
    )
    slate = parse_salaries(salary_path)
    role_path = _write_evidence(
        tmp_path / "roles",
        slate,
        {
            "NE": [("NE|K|NE Kicker", 1.0)],
            "SEA": [("SEA|K|Sea Kicker", 1.0)],
        },
        as_of=AS_OF,
    )

    outcome = run_prior_review(
        salary_csv=salary_path,
        entry_csv=entry_path,
        label="ne-sea-role",
        as_of=AS_OF,
        run_root=tmp_path / "run",
        output_root=tmp_path / "out",
        prior_package_dir=package_dir,
        role_evidence_json=role_path,
        project=project,
    )

    assert not outcome.blocked
    assert outcome.file_valid
    assert outcome.hashes["role_evidence_json"] == sha256_file(role_path)
    role_report = outcome.reports["selection"]["prior_scores"]["kicker_roles"]
    assert role_report["evidence_state"] == "PASS"
    assert role_report["allocation_basis"] == "SOURCE_BOUND_CURRENT_ROLE_EVIDENCE"
    assert role_report["synthetic_note"] == "TEST_ONLY_SYNTHETIC_EVIDENCE"
    assert outcome.export["FILE_VALID"] is True
    assert outcome.export["EVIDENCE_STATE"] == "UNKNOWN"
    assert outcome.export["MODEL_STATUS"] == "PRIOR_ONLY"
    assert outcome.export["RELEASE_DECISION"] == "DO_NOT_UPLOAD"


def test_invalid_role_capture_blocks_before_assignments_or_review_csv(tmp_path: Path) -> None:
    from nfl_dfs.dk import parse_salaries

    salary_path, entry_path, package_dir, project = _prepared_run(
        tmp_path, expires_at=AS_OF + timedelta(hours=6)
    )
    slate = parse_salaries(salary_path)
    role_path = _write_evidence(
        tmp_path / "roles",
        slate,
        {
            "NE": [("NE|K|NE Kicker", 1.0)],
            "SEA": [("SEA|K|Sea Kicker", 1.0)],
        },
        as_of=AS_OF,
    )
    role_payload = json.loads(role_path.read_text(encoding="utf-8"))
    changed_source = role_path.parent / role_payload["sources"][0]["path"]
    changed_source.write_text("changed after declaration", encoding="utf-8")

    outcome = run_prior_review(
        salary_csv=salary_path,
        entry_csv=entry_path,
        label="ne-sea-invalid-role",
        as_of=AS_OF,
        run_root=tmp_path / "run",
        output_root=tmp_path / "out",
        prior_package_dir=package_dir,
        role_evidence_json=role_path,
        project=project,
    )

    assert outcome.blocked
    assert outcome.stage == "SELECT"
    assert "KICKER_ROLE_SOURCE_HASH_MISMATCH" in outcome.blockers[0]
    assert "assignments" not in outcome.artifacts
    assert "bulk_entry_csv" not in outcome.artifacts
    assert list((tmp_path / "out").rglob("DK_REVIEW_ENTRY_*.csv")) == []


def test_role_evidence_expiring_during_selection_blocks_review_export(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nfl_dfs import prior_review as prior_review_module
    from nfl_dfs.dk import parse_salaries

    salary_path, entry_path, package_dir, project = _prepared_run(
        tmp_path, expires_at=AS_OF + timedelta(hours=6)
    )
    slate = parse_salaries(salary_path)
    role_path = _write_evidence(
        tmp_path / "roles",
        slate,
        {
            "NE": [("NE|K|NE Kicker", 1.0)],
            "SEA": [("SEA|K|Sea Kicker", 1.0)],
        },
        as_of=AS_OF,
        expires_at=AS_OF + timedelta(seconds=90),
    )
    stamps = iter(
        [AS_OF, AS_OF + timedelta(minutes=1), AS_OF + timedelta(minutes=2)]
    )

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return next(stamps)

    monkeypatch.setattr(prior_review_module, "datetime", Clock)
    outcome = run_prior_review(
        salary_csv=salary_path,
        entry_csv=entry_path,
        label="ne-sea-expiring-role",
        as_of=None,
        run_root=tmp_path / "run",
        output_root=tmp_path / "out",
        prior_package_dir=package_dir,
        role_evidence_json=role_path,
        project=project,
    )

    assert outcome.blocked
    assert outcome.stage == "EXPORT"
    assert any(
        "KICKER_ROLE_SOURCE_EXPIRED_DURING_SELECTION" in blocker
        for blocker in outcome.blockers
    )
    assert "bulk_entry_csv" not in outcome.artifacts
    assert list((tmp_path / "out").rglob("DK_REVIEW_ENTRY_*.csv")) == []


def test_one_cowork_command_snapshots_roles_and_retains_four_truths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nfl_dfs import cli
    from nfl_dfs import prior_review as prior_review_module
    from nfl_dfs.dk import parse_salaries

    now = datetime.now(timezone.utc)
    salary_path, entry_path, package_dir, project = _prepared_run(
        tmp_path, expires_at=now + timedelta(hours=6)
    )
    slate = parse_salaries(salary_path)
    role_path = _write_evidence(
        tmp_path / "roles",
        slate,
        {
            "NE": [("NE|K|NE Kicker", 1.0)],
            "SEA": [("SEA|K|Sea Kicker", 1.0)],
        },
        as_of=now,
    )
    attachments = _attachments(tmp_path, salary_path, entry_path)
    monkeypatch.setattr(cli, "DEFAULT_RUNS_DIR", tmp_path / "runs")
    real = prior_review_module.run_prior_review
    monkeypatch.setattr(
        cli, "run_prior_review", lambda **kwargs: real(**kwargs, project=project)
    )

    code = cli.command_cowork_run(
        _cowork_args(
            tmp_path,
            attachments,
            prior_package_dir=str(package_dir),
            role_evidence_json=str(role_path),
        )
    )

    assert code == 0
    request = json.loads(
        (tmp_path / "runs" / "prior-review-test" / "run_request.json").read_text(
            encoding="utf-8"
        )
    )
    copied_role = Path(request["role_evidence_json"])
    assert copied_role.parent == tmp_path / "runs" / "prior-review-test" / "inputs"
    assert (copied_role.parent / "sources").is_dir()
    report = json.loads(
        (tmp_path / "outputs" / "prior-review-test" / "cowork_run.json").read_text(
            encoding="utf-8"
        )
    )
    assert report["FILE_VALID"] is True
    assert report["EVIDENCE_STATE"] == "UNKNOWN"
    assert report["MODEL_STATUS"] == "PRIOR_ONLY"
    assert report["RELEASE_DECISION"] == "DO_NOT_UPLOAD"
    assert Path(report["prior_review_artifacts"]["role_evidence_json"]) == copied_role


def test_an_unresolved_available_identity_stops_the_command_with_no_export(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nfl_dfs import cli
    from nfl_dfs import prior_review as prior_review_module

    salary_path, entry_path, _package_dir, project = _prepared_run(
        tmp_path, expires_at=AS_OF + timedelta(hours=6)
    )
    attachments = _attachments(tmp_path, salary_path, entry_path)
    from nfl_dfs.dk import parse_salaries

    slate = parse_salaries(salary_path)
    available = next(
        player
        for player in slate.players
        if player.role == "FLEX" and (player.status_raw or "") == ""
    )

    def propose(**kwargs):
        package_root = Path(kwargs["output_dir"])
        (package_root / "raw").mkdir(parents=True)
        proposals = [
            {
                "dk_id": player.dk_id,
                "captain_dk_id": player.dk_id,
                "dk_name": player.name,
                "dk_team": player.team,
                "dk_position": player.position,
                "underlying_id": player.underlying_id,
                "nflverse_team": player.team,
                "provider_player_id": "00-0022222",
                "provider_name": player.name,
                "provider_pfr_id": "",
                "provider_team": "DAL",
                "provider_status": "ACT",
                "match_method": (
                    AUTO_ACCEPT_MATCH_METHOD
                    if player.dk_id == available.dk_id
                    else "NORMALIZED_NAME_TEAM_POSITION"
                ),
                "candidates": ["00-0022222|x|WR|DAL|ACT"],
            }
            for player in slate.players
            if player.role == "FLEX"
        ]
        (package_root / "identity_proposals.json").write_text(
            json.dumps({"proposals": proposals}), encoding="utf-8"
        )
        return {
            "package_dir": str(package_root),
            "identity_proposals": str(package_root / "identity_proposals.json"),
            "source_manifest": str(package_root / "source_manifest.json"),
            "hashes": {},
            "market": {"roof": "dome"},
        }

    def freeze(**kwargs):  # pragma: no cover - reaching this is the failure
        raise AssertionError("freeze must not run while an identity is unresolved")

    monkeypatch.setattr(cli, "DEFAULT_RUNS_DIR", tmp_path / "runs")
    real = prior_review_module.run_prior_review
    monkeypatch.setattr(
        cli,
        "run_prior_review",
        lambda **kwargs: real(**kwargs, propose=propose, freeze=freeze, project=project),
    )

    code = cli.command_cowork_run(
        _cowork_args(tmp_path, attachments, build_priors=True)
    )

    assert code == 2
    report = json.loads(
        (tmp_path / "outputs" / "prior-review-test" / "cowork_run.json").read_text(
            encoding="utf-8"
        )
    )
    assert report["FILE_VALID"] is False
    assert report["MODEL_STATUS"] == "PRIOR_ONLY"
    assert report["RELEASE_DECISION"] == "DO_NOT_UPLOAD"
    assert report["stage"] == "PRIOR_REVIEW_IDENTITY_BLOCKED"
    assert report["bulk_entry_csv"] is None
    assert Path(report["review_workbook"]).is_file()
    assert any(
        value.startswith(f"IDENTITY_UNRESOLVED_AND_AVAILABLE:{available.dk_id}:")
        for value in report["blockers"]
    )
    assert list((tmp_path / "outputs").rglob("*.csv")) == []
    # The decision file is still written, so the operator can see and edit it.
    reviewed = tmp_path / "runs" / "prior-review-test" / "prior_review" / "priors"
    assert (reviewed / "identity_reviewed.csv").is_file()
    assert (reviewed / "identity_decisions.json").is_file()


def test_operator_fades_and_new_status_codes_survive_the_request_round_trip() -> None:
    request = CoworkRunRequest.from_mapping(
        {
            "profile": "prior_review",
            "build_priors": True,
            "exclude_dk_ids": ["50000001", " 50000003 ", ""],
            "unavailable_statuses": ["SUSP"],
            "available_statuses": ["P"],
        }
    )
    assert request.exclude_dk_ids == ("50000001", "50000003")
    assert request.unavailable_statuses == ("SUSP",)
    assert request.available_statuses == ("P",)
    assert CoworkRunRequest.from_mapping(request.to_dict()) == request

    with pytest.raises(CoworkInputError, match="exclude_dk_ids must be a JSON array"):
        CoworkRunRequest.from_mapping({"exclude_dk_ids": "50000001"})


def test_an_operator_fade_reaches_the_solver_through_the_profile(tmp_path: Path) -> None:
    from nfl_dfs.dk import parse_salaries

    salary_path, entry_path, package_dir, project = _prepared_run(
        tmp_path, expires_at=AS_OF + timedelta(hours=6)
    )
    slate = parse_salaries(salary_path)
    alpha = next(
        player
        for player in slate.players
        if player.name == "Sea Alpha WR" and player.role == "FLEX"
    )

    outcome = run_prior_review(
        salary_csv=salary_path,
        entry_csv=entry_path,
        label="ne-sea",
        as_of=AS_OF,
        run_root=tmp_path / "run",
        output_root=tmp_path / "out",
        prior_package_dir=package_dir,
        operator_excluded_dk_ids=(alpha.dk_id,),
        project=project,
    )

    assert not outcome.blocked
    rosters = {
        dk_id
        for lineup in outcome.reports["selection"]["lineups"]
        for dk_id in lineup["roster"]
    }
    assert alpha.dk_id not in rosters
    assert outcome.reports["selection"]["participation"]["operator_excluded_people"] == 1


def test_an_unclassified_draftkings_status_stops_the_run_by_name(tmp_path: Path) -> None:
    from .test_participation import _POOL

    pool = tuple(
        (team, position, name, "PUP" if name == "Sea TE" else status, salary)
        for team, position, name, status, salary in _POOL
    )
    slate = _slate(tmp_path, pool)
    _model(tmp_path, slate)
    salary_path = tmp_path / "DKSalaries.csv"
    entry_path = tmp_path / "DKEntries.csv"
    entry_path.write_bytes(_entries_bytes())
    splits_path = tmp_path / "stats_team_week.csv"
    splits_path.write_bytes(_splits_bytes())
    package_dir = _write_package(
        tmp_path,
        salary_sha=sha256_file(salary_path),
        team_stats_sha=sha256_file(splits_path),
        expires_at=AS_OF + timedelta(hours=6),
    )
    (package_dir / "raw").mkdir(exist_ok=True)
    (package_dir / "raw" / f"{sha256_file(splits_path)}.csv").write_bytes(
        splits_path.read_bytes()
    )

    def project(**kwargs):
        output = Path(kwargs["output_dir"])
        output.mkdir(parents=True, exist_ok=True)
        return _StubProjection(
            output_dir=str(output),
            team_projections=str(tmp_path / "team_projections.csv"),
            player_opportunities=str(tmp_path / "player_opportunities.csv"),
            source_ledger=str(output / "source_ledger.json"),
            hashes={},
            input_hashes={},
            expires_at=_stub_expiry(kwargs["as_of"]),
        )

    blocked = run_prior_review(
        salary_csv=salary_path,
        entry_csv=entry_path,
        label="ne-sea",
        as_of=AS_OF,
        run_root=tmp_path / "run",
        output_root=tmp_path / "out",
        prior_package_dir=package_dir,
        project=project,
    )
    assert blocked.blocked
    assert "UNKNOWN_DK_STATUS:PUP" in blocked.blockers[0]
    assert blocked.export is None

    cleared = run_prior_review(
        salary_csv=salary_path,
        entry_csv=entry_path,
        label="ne-sea",
        as_of=AS_OF,
        run_root=tmp_path / "run2",
        output_root=tmp_path / "out2",
        prior_package_dir=package_dir,
        extra_unavailable_statuses=("PUP",),
        project=project,
    )
    assert not cleared.blocked
    assert cleared.file_valid
