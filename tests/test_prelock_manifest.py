"""A run must freeze what it predicted, before the games decide anything.

Q1 built the settlement plane; Q1B proved nothing could reach it, because no
`data/runs/` snapshot held an `nfl_prelock_run_manifest_v1` — only the legacy
`build` command ever wrote one, and every contest Ben has actually entered came
through `prior_review`. This is the coverage for the emitter that closes that.

The property that matters is ordering. A manifest written after the outcome is
known proves nothing at all, so the emitter runs inside the run that builds the
portfolio, it never backfills, and it records only what that run genuinely
observed. Everything below is either a refusal that protects that property, or
the end-to-end proof that what the emitter writes is what settlement accepts.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from nfl_dfs.contracts import EngineMode
from nfl_dfs.hashing import sha256_file
from nfl_dfs.lineups import validate_lineup
from nfl_dfs.prelock_manifest import (
    PRELOCK_MANIFEST_VERSION,
    PredictionArtifact,
    PrelockManifestError,
    build_prelock_manifest,
    write_prelock_manifest,
)
from nfl_dfs.settlement import capture_settlement_bundle, replay_settlement_package

from .test_classic_prior_review import _run

CREATED_AT = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)

TRUTHS = {
    "FILE_VALID": True,
    "EVIDENCE_STATE": "PASS",
    "MODEL_STATUS": "PRIOR_ONLY",
    "RELEASE_DECISION": "DO_NOT_UPLOAD",
}

PREDICTION = PredictionArtifact(
    name="team_projections",
    path="projected/team_projections.csv",
    sha256="a" * 64,
    artifact_version="nfl_team_projections_csv_v1",
)


def _manifest(**overrides):
    kwargs = {
        "run_id": "fixture-run",
        "created_at": CREATED_AT,
        "mode": EngineMode.CLASSIC,
        "contest_id": "200000001",
        "draft_group": "DG-C1",
        "entry_fee": Decimal("5.00"),
        "salary_sha256": "b" * 64,
        "entries_sha256": "c" * 64,
        "assignments_path": "selection/assignments.csv",
        "assignments_sha256": "d" * 64,
        "predictions": [PREDICTION],
        "release_truths": TRUTHS,
        "selected_entry_ids": ["910000001"],
    }
    kwargs.update(overrides)
    return build_prelock_manifest(**kwargs)


# ---------------------------------------------------------------------------
# What the manifest says, and what it refuses to say
# ---------------------------------------------------------------------------


def test_the_manifest_records_identity_prediction_and_selection():
    manifest = _manifest()
    assert manifest["schema_version"] == PRELOCK_MANIFEST_VERSION
    assert manifest["contest_parameters"]["contest_id"] == "200000001"
    assert manifest["contest_parameters"]["mode"] == "CLASSIC"
    assert manifest["input_hashes"]["team_projections"] == "a" * 64
    assert manifest["artifact_versions"]["assignments"] == "nfl_assignment_csv_v1"
    assert manifest["assignment_sha256"] == "d" * 64
    assert manifest["selected_entry_ids"] == ["910000001"]
    assert manifest["RELEASE_DECISION"] == "DO_NOT_UPLOAD"


def test_a_prior_only_run_declares_what_it_does_not_have():
    """Absence is stated, never left to be inferred from a missing key.

    A prior-only run simulates nothing and reads no contest economics. Recording
    that explicitly is what separates "did not know" from "forgot", and it is the
    difference between a manifest settlement can trust and one it cannot.
    """
    manifest = _manifest()
    assert manifest["scenario_artifacts"] == {}
    assert manifest["contest_parameters"]["field_size"] is None
    assert (
        manifest["contest_parameters"]["field_size_basis"]
        == "UNKNOWN_PRIOR_ONLY_RUN_READS_NO_CONTEST_ECONOMICS"
    )
    limits = manifest["model_status_limitations"]
    assert limits["prospective_validation"] == "ABSENT"
    assert limits["scenarios"].startswith("ABSENT_PRIOR_ONLY")
    assert limits["contest_economics"].startswith("ABSENT_PRIOR_ONLY")
    assert "payouts" not in manifest["input_hashes"]
    assert manifest["credentials_or_account_state_stored"] is False


def test_a_recorded_field_size_is_labelled_an_assumption_not_an_observation():
    """The distinction settlement now depends on.

    A producer that assumed a field size records it as the assumption the
    portfolio was built against. Settlement reports it beside the settled count
    rather than demanding they match, because they are different quantities:
    193391013 was advertised at 133,000 and settled 126,020.
    """
    manifest = _manifest(assumed_field_size=133_000)
    assert manifest["contest_parameters"]["field_size"] == 133_000
    assert manifest["contest_parameters"]["field_size_basis"] == "PRE_LOCK_ASSUMPTION"


def test_a_naive_clock_is_refused():
    """A pre-lock record whose clock is ambiguous cannot prove it preceded lock."""
    with pytest.raises(PrelockManifestError, match="PRELOCK_CREATED_AT_NOT_TIMEZONE_AWARE"):
        _manifest(created_at=datetime(2026, 9, 10, 12, 0))


def test_a_manifest_with_no_prediction_is_refused():
    with pytest.raises(PrelockManifestError, match="PRELOCK_PREDICTION_REQUIRED"):
        _manifest(predictions=[])


def test_a_manifest_with_no_selected_entry_is_refused():
    with pytest.raises(PrelockManifestError, match="PRELOCK_ASSIGNMENT_REQUIRED"):
        _manifest(selected_entry_ids=[])


def test_a_prediction_named_like_a_fixed_artifact_role_is_refused():
    """`settlement` derives the prediction set by subtracting the fixed roles.

    A prediction called `salary` would be subtracted away and silently vanish
    from the coverage check, so the collision is named here instead.
    """
    clash = PredictionArtifact("salary", "x.csv", "e" * 64, "dk_salary_csv_v1")
    with pytest.raises(PrelockManifestError, match="PRELOCK_PREDICTION_NAME_RESERVED"):
        _manifest(predictions=[clash])


def test_duplicate_prediction_names_are_refused():
    with pytest.raises(PrelockManifestError, match="PRELOCK_PREDICTION_NAME_DUPLICATE"):
        _manifest(predictions=[PREDICTION, PREDICTION])


def test_missing_release_truths_are_refused():
    with pytest.raises(PrelockManifestError, match="PRELOCK_RELEASE_TRUTH_MISSING"):
        _manifest(release_truths={"FILE_VALID": True})


def test_an_unresolved_identity_field_is_refused():
    with pytest.raises(PrelockManifestError, match="PRELOCK_FIELD_UNRESOLVED"):
        _manifest(contest_id="")


def test_the_same_inputs_write_byte_identical_bytes(tmp_path):
    first = write_prelock_manifest(tmp_path / "a.json", _manifest())
    second = write_prelock_manifest(tmp_path / "b.json", _manifest())
    assert first == second
    assert (tmp_path / "a.json").read_bytes() == (tmp_path / "b.json").read_bytes()


# ---------------------------------------------------------------------------
# The emitter inside a real run
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def classic_run(tmp_path_factory):
    root = tmp_path_factory.mktemp("prelock-classic")
    outcome, slate, _ = _run(root / "a", entries=2)
    assert not outcome.blocked, outcome.blockers
    return outcome, slate, root


def test_a_real_classic_run_freezes_a_manifest(classic_run):
    outcome, _slate, _root = classic_run
    stage = next(s for s in outcome.stages if s["stage"] == "PRELOCK_MANIFEST")
    assert stage["status"] == "OK"
    manifest = json.loads(
        Path(outcome.artifacts["prelock_manifest"]).read_text(encoding="utf-8")
    )
    assert manifest["schema_version"] == PRELOCK_MANIFEST_VERSION
    # Bound to the bytes the run actually read and wrote, not recomputed here.
    assert manifest["input_hashes"]["salary"] == outcome.hashes["salary_csv"]
    assert manifest["input_hashes"]["entries"] == outcome.hashes["entry_csv"]
    assert manifest["input_hashes"]["assignments"] == outcome.hashes["assignments"]
    assert sorted(manifest["artifact_versions"]) == [
        "assignments", "entries", "player_opportunities", "salary",
        "source_ledger", "team_projections",
    ]


def test_the_manifest_is_emitted_for_a_do_not_upload_run(classic_run):
    """Which is the whole point.

    Every prior-only run ends `DO_NOT_UPLOAD`, and those are the review lineups
    Ben actually enters by hand. A manifest emitted only for an uploadable
    package would never be emitted at all. It changes no release truth.
    """
    outcome, _slate, _root = classic_run
    manifest = json.loads(
        Path(outcome.artifacts["prelock_manifest"]).read_text(encoding="utf-8")
    )
    assert manifest["RELEASE_DECISION"] == "DO_NOT_UPLOAD"
    assert manifest["MODEL_STATUS"] == "PRIOR_ONLY"
    assert outcome.export["RELEASE_DECISION"] == "DO_NOT_UPLOAD"


def test_the_manifest_matches_the_runs_own_release_truths(classic_run):
    """Settlement requires equality, so a drift here would block every capture."""
    outcome, _slate, _root = classic_run
    manifest = json.loads(
        Path(outcome.artifacts["prelock_manifest"]).read_text(encoding="utf-8")
    )
    for key in ("FILE_VALID", "EVIDENCE_STATE", "MODEL_STATUS", "RELEASE_DECISION"):
        assert manifest[key] == outcome.export[key]


def test_the_classic_assignment_csv_is_the_selection_settlement_will_read(classic_run):
    """Nine-slot geometry that `lineups.read_assignment_csv` accepts, and the
    same rosters the canonical selection report already published."""
    from nfl_dfs.lineups import read_assignment_csv

    outcome, slate, _root = classic_run
    assignments = read_assignment_csv(outcome.artifacts["assignments"], EngineMode.CLASSIC)
    selection = json.loads(
        Path(outcome.artifacts["selection_report"]).read_text(encoding="utf-8")
    )
    assert assignments == {
        entry_id: tuple(roster)
        for entry_id, roster in selection["assignments_by_entry_id"].items()
    }
    for roster in assignments.values():
        assert validate_lineup(slate, roster).valid


def test_a_replayed_run_freezes_byte_identical_bytes(tmp_path_factory):
    """A pinned `as_of` must reproduce the manifest exactly.

    The emitter stamps the run's own clock rather than `now()` for this reason:
    a wall-clock stamp would be the single field that could never replay.
    """
    root = tmp_path_factory.mktemp("prelock-replay")
    first, _slate, _ = _run(root / "a", entries=2)
    second, _slate2, _ = _run(root / "b", entries=2)
    assert first.hashes["prelock_manifest"] == second.hashes["prelock_manifest"]


# ---------------------------------------------------------------------------
# End to end: what the emitter writes is what settlement accepts
# ---------------------------------------------------------------------------


def _standings(path: Path, slate, assignments) -> Path:
    """A complete two-entry field: the operator owns it, so it settles exactly."""
    rows = ["EntryId,Rank,Points,Prize,Lineup"]
    for rank, (entry_id, roster) in enumerate(sorted(assignments.items()), start=1):
        lineup = validate_lineup(slate, roster).lineup
        assert lineup is not None
        points = "200.00" if rank == 1 else "150.00"
        prize = "20.00" if rank == 1 else "0.00"
        rows.append(f"{entry_id},{rank},{points},{prize},{lineup.canonical_key}")
    path.write_text("\r\n".join(rows) + "\r\n", encoding="utf-8", newline="")
    return path


def test_a_frozen_manifest_captures_and_replays_through_settle(classic_run, tmp_path):
    """The proof Q1B could not produce on any real run.

    prior_review freezes the manifest; a settlement request binds it together
    with the run's own projections and assignment; `settle` captures the
    package; `settle --replay` reproduces it. No scenario bank, no payout hash in
    the manifest, and a field size the run never claimed to know.
    """
    from nfl_dfs.lineups import read_assignment_csv

    outcome, slate, _root = classic_run
    source = tmp_path / "source"
    source.mkdir()

    assignments = read_assignment_csv(outcome.artifacts["assignments"], EngineMode.CLASSIC)
    payouts = source / "payouts.csv"
    payouts.write_text(
        "rank_start,rank_end,prize_type,value\n1,1,CASH,20\n", encoding="utf-8"
    )
    standings = _standings(source / "standings.csv", slate, assignments)
    registry = Path(__file__).resolve().parents[1] / "config" / "metric_registry_q1_v1.json"

    def binding(name, path, version):
        return {
            "name": name,
            "path": str(Path(path).resolve()),
            "sha256": sha256_file(path),
            "artifact_version": version,
        }

    manifest_path = outcome.artifacts["prelock_manifest"]
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    request = {
        "schema_version": "nfl_settlement_request_v1",
        "settlement_id": "q1c-prelock-emitter",
        "run_id": manifest["run_id"],
        "captured_at": "2026-09-13T16:00:00+00:00",
        "settled_at": "2026-09-14T00:30:00+00:00",
        "contest": {
            "contest_id": manifest["contest_parameters"]["contest_id"],
            "draft_group": manifest["contest_parameters"]["draft_group"],
            "mode": "CLASSIC",
            "entry_fee": "5.00",
            # The settled count, which the manifest never claimed to know.
            "field_size": len(assignments),
            "objective": "SMALL_GPP",
            "advertised_prize_value": "20.00",
            "ticket_face_value": None,
        },
        "versions": {
            "salary_parser": "dk_csv_v1",
            "entry_parser": "dk_csv_v1",
            "payout_parser": "nfl_payout_csv_v2",
            "standings_parser": "nfl_standings_csv_v2",
            "assignment_parser": "nfl_assignment_csv_v1",
            "scoring": slate.scoring_version,
            "settlement": "nfl_reference_settlement_v1",
            "bundle_schema": "nfl_settlement_bundle_v1",
            "brief_schema": "nfl_run_settlement_brief_v1",
            "metric_registry_schema": "nfl_metric_promotion_registry_v1",
        },
        "artifacts": {
            "salary": binding("salary", outcome.artifacts["salary_csv"], "dk_salary_csv_v1"),
            "entries": binding("entries", outcome.artifacts["entry_csv"], "dk_entry_csv_v1"),
            "payouts": binding("payouts", payouts, "nfl_payout_contract_v1"),
            "assignments": binding(
                "assignments", outcome.artifacts["assignments"], "nfl_assignment_csv_v1"
            ),
            "prelock_manifest": binding(
                "prelock_manifest", manifest_path, "nfl_prelock_run_manifest_v1"
            ),
            "standings": binding("standings", standings, "nfl_standings_csv_v2"),
            "metric_registry": binding(
                "metric_registry", registry, "nfl_metric_promotion_registry_v1"
            ),
            "predictions": [
                binding(name, outcome.artifacts[name], version)
                for name, version in (
                    ("team_projections", "nfl_team_projections_csv_v1"),
                    ("player_opportunities", "nfl_player_opportunities_csv_v1"),
                    ("source_ledger", "nfl_source_ledger_v2"),
                )
            ],
            # A prior-only run simulates nothing, so it binds no bank at all.
            "scenarios": [],
        },
        "release_truths": {
            key: manifest[key]
            for key in ("FILE_VALID", "EVIDENCE_STATE", "MODEL_STATUS", "RELEASE_DECISION")
        },
        "evidence_issues": [
            {
                "state": "MISSING",
                "code": "PROSPECTIVE_VALIDATION_ABSENT",
                "detail": "No prospective validation corpus yet; Q6 is unstarted.",
            }
        ],
        "reference_budget": {
            "max_entries": 100,
            "max_work_units": 1000,
            "max_runtime_seconds": 10.0,
        },
    }
    request_path = source / "request.json"
    request_path.write_text(json.dumps(request, indent=2), encoding="utf-8")

    captured = capture_settlement_bundle(request_path, tmp_path / "settlements")
    assert captured.bundle.capture_status == "Q1_COMPLETE"
    assert captured.bundle.release_truths.release_decision.value == "DO_NOT_UPLOAD"

    replay = replay_settlement_package(captured.package_path)
    assert replay["status"] == "DETERMINISTIC_REPLAY_PASS"

    brief = json.loads(
        (Path(captured.package_path) / "run_settlement_brief.json").read_text(
            encoding="utf-8"
        )
    )
    # The assumed/settled pair settlement now reports instead of enforcing.
    assert brief["prediction"]["assumed_field_size"] is None
    assert brief["prediction"]["settled_field_size"] == len(assignments)
    assert brief["prediction"]["scenario_artifact_names"] == []


def test_a_prediction_whose_declared_version_moved_on_is_skipped_not_asserted(
    tmp_path_factory, monkeypatch
):
    """A stale expectation must surface at the run, not days later at capture.

    Settlement re-reads every JSON prediction and compares the version the
    request declares against the one the file carries. If the emitter's expected
    version ever drifts from what the projection actually writes, the manifest
    would assert something false and fail at capture with a confusing message.
    It stops here instead, naming both versions.
    """
    from nfl_dfs import prior_review as module

    monkeypatch.setitem(
        module._PRELOCK_PREDICTION_VERSIONS, "source_ledger", "nfl_source_ledger_v99"
    )
    root = tmp_path_factory.mktemp("prelock-version-drift")
    outcome, _slate, _ = _run(root / "a", entries=1)
    stage = next(s for s in outcome.stages if s["stage"] == "PRELOCK_MANIFEST")
    assert stage["status"] == "SKIPPED"
    assert stage["reason"] == "PREDICTION_VERSION_UNEXPECTED"
    assert stage["artifact"] == "source_ledger"
    assert stage["expected"] == "nfl_source_ledger_v99"
    assert stage["declared"] == "nfl_source_ledger_v2"
    # A run that produced a portfolio is still a good run.
    assert not outcome.blocked, outcome.blockers
    assert "prelock_manifest" not in outcome.artifacts


def test_the_showdown_path_freezes_a_manifest_too(tmp_path):
    """Every success exit, not just the one that happened to be wired first.

    `prior_review` returns from three places — Showdown, Classic C1/C2 and
    Classic C3. A manifest emitted from only one of them would leave the other
    two unsettleable, which is precisely the failure Q1B found in the repo.
    """
    from nfl_dfs.contracts import EngineMode as _Mode
    from nfl_dfs.lineups import read_assignment_csv
    from nfl_dfs.prior_review import run_prior_review

    from .test_prior_review_profile import AS_OF, _prepared_run

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
    assert not outcome.blocked, outcome.blockers
    stage = next(s for s in outcome.stages if s["stage"] == "PRELOCK_MANIFEST")
    assert stage["status"] == "OK"
    manifest = json.loads(
        Path(outcome.artifacts["prelock_manifest"]).read_text(encoding="utf-8")
    )
    assert manifest["contest_parameters"]["mode"] == "SHOWDOWN"
    assert manifest["input_hashes"]["assignments"] == outcome.hashes["assignments"]
    rosters = read_assignment_csv(outcome.artifacts["assignments"], _Mode.SHOWDOWN)
    assert sorted(rosters) == manifest["selected_entry_ids"]
