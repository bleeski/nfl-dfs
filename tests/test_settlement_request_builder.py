"""The settlement request must be assembled from bytes, or refused by name.

`scripts/make_settlement_request.py` is the missing front door to Q1. Everything
`settle --request` needs is bound by SHA-256, so the only two honest outcomes for
a builder are a complete request whose every binding is real, or a refusal that
names what is missing. A builder that defaulted a field would produce a request
that fails at capture with a hash mismatch instead of here, with a reason.

`PRELOCK_MANIFEST_ABSENT` is not hypothetical. When Q1B wrote these tests, no
`data/runs/` snapshot in the repo held a pre-lock manifest at all: only the
legacy `build` command wrote one, and every contest Ben had actually entered came
through `prior_review`/C1-C3. Q1C fixed that going forward by emitting one on the
path he uses. It recovers none of the eighteen contests already played, because a
pre-lock manifest records what was predicted *before* lock and can never be
written afterwards — so the refusal below stays, and stays exercised.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from nfl_dfs.hashing import sha256_file
from nfl_dfs.settlement import capture_settlement_bundle, replay_settlement_package

from .test_settlement_bundle import _settlement_fixture


def _builder():
    path = Path(__file__).resolve().parents[1] / "scripts" / "make_settlement_request.py"
    spec = importlib.util.spec_from_file_location("make_settlement_request", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def builder():
    return _builder()


CAPTURED_AT = datetime(2026, 9, 14, 17, 0, tzinfo=timezone.utc)
SETTLED_AT = datetime(2026, 9, 14, 18, 0, tzinfo=timezone.utc)


@pytest.fixture()
def run_snapshot(tmp_path, classic_slate, classic_entries, builder, monkeypatch):
    """A complete synthetic `data/runs/` snapshot, laid out as the builder expects.

    Synthetic on purpose. No real contest in this repo can reach this state: none
    has a pre-lock manifest or a scenario bank, which is the finding the refusal
    tests below pin. Proving the round trip needs a slate that *does*, so this
    builds one rather than pretending a real one qualifies.
    """
    _, request, paths = _settlement_fixture(tmp_path, classic_slate, classic_entries)
    run_id = "q1-fixture-run"
    runs = tmp_path / "runs"
    run_dir = runs / run_id
    (run_dir / "inputs").mkdir(parents=True)
    (run_dir / "projected").mkdir(parents=True)
    (run_dir / "scenarios").mkdir(parents=True)

    # Content-addressed names, as the real intake writes them: the builder must
    # classify these by schema, never by filename.
    (run_dir / "inputs" / f"{sha256_file(paths['salary'])}.csv").write_bytes(
        paths["salary"].read_bytes()
    )
    (run_dir / "inputs" / f"{sha256_file(paths['entries'])}.csv").write_bytes(
        paths["entries"].read_bytes()
    )
    (run_dir / "assignments.csv").write_bytes(paths["assignments"].read_bytes())
    (run_dir / "payouts_operator_supplied.csv").write_bytes(paths["payouts"].read_bytes())
    (run_dir / "prelock_manifest.json").write_bytes(paths["manifest"].read_bytes())
    (run_dir / "projected" / "team_projections.csv").write_bytes(
        paths["prediction"].read_bytes()
    )
    (run_dir / "scenarios" / paths["scenario"].name).write_bytes(
        paths["scenario"].read_bytes()
    )
    (run_dir / "cowork_run.json").write_text(
        json.dumps(request["release_truths"]), encoding="utf-8"
    )

    normalized = tmp_path / "normalized"
    contest_id = request["contest"]["contest_id"]
    (normalized / contest_id).mkdir(parents=True)
    (normalized / contest_id / "standings.csv").write_bytes(paths["standings"].read_bytes())

    monkeypatch.setattr(builder, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(builder, "RUNS_DIR", runs)
    monkeypatch.setattr(builder, "NORMALIZED_DIR", normalized)
    return run_dir, contest_id, request


def _resolve(builder, run_snapshot, **kwargs):
    run_dir, contest_id, _ = run_snapshot
    kwargs.setdefault("assignments", run_dir / "assignments.csv")
    kwargs.setdefault("payouts", run_dir / "payouts_operator_supplied.csv")
    return builder.resolve_contest(contest_id, run_dir, **kwargs)


def _build(builder, resolution, **kwargs):
    kwargs.setdefault("settlement_id", "q1b-builder-fixture")
    kwargs.setdefault("captured_at", CAPTURED_AT)
    kwargs.setdefault("settled_at", SETTLED_AT)
    kwargs.setdefault("objective", "SMALL_GPP")
    kwargs.setdefault("advertised_prize_value", Decimal("20.00"))
    kwargs.setdefault(
        "reference_budget",
        {"max_entries": 100, "max_work_units": 1000, "max_runtime_seconds": 5.0},
    )
    return builder.build_request(resolution, **kwargs)


# ---------------------------------------------------------------------------
# The round trip
# ---------------------------------------------------------------------------


def test_a_built_request_captures_and_replays(builder, run_snapshot, tmp_path):
    """Build, capture, replay. The acceptance this tranche is for.

    Proven on the synthetic complete slate above, not on one of Ben's eighteen
    contests: every one of those refuses at `PRELOCK_MANIFEST_ABSENT` before it
    reaches capture.
    """
    resolution = _resolve(builder, run_snapshot)
    assert resolution.blockers == []
    request = _build(builder, resolution)
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(request, indent=2), encoding="utf-8")

    outcome = capture_settlement_bundle(request_path, tmp_path / "settlements")
    assert outcome.bundle.capture_status == "Q1_COMPLETE"

    replay = replay_settlement_package(outcome.package_path)
    assert replay["status"] == "DETERMINISTIC_REPLAY_PASS"
    assert replay["settlement_id"] == "q1b-builder-fixture"


def test_the_same_snapshot_builds_a_byte_identical_request(builder, run_snapshot):
    first = json.dumps(_build(builder, _resolve(builder, run_snapshot)), sort_keys=True)
    second = json.dumps(_build(builder, _resolve(builder, run_snapshot)), sort_keys=True)
    assert first == second


def test_inputs_are_classified_by_schema_not_by_filename(builder, run_snapshot):
    """`data/runs/*/inputs/` holds content-addressed names as often as readable ones."""
    run_dir, _, _ = run_snapshot
    salary, entries = builder.classify_run_inputs(run_dir)
    assert salary is not None and entries is not None
    assert salary != entries
    # Neither filename says what it is; only the parser does.
    assert "salary" not in salary.name.lower()
    assert "entr" not in entries.name.lower()


def test_release_truths_are_copied_from_the_frozen_run_not_recomputed(builder, run_snapshot):
    """Settlement must never be able to improve the decision a slate shipped with."""
    run_dir, _, request = run_snapshot
    resolution = _resolve(builder, run_snapshot)
    assert resolution.resolved["release_truths"] == request["release_truths"]
    assert resolution.resolved["release_truths"]["RELEASE_DECISION"] == "DO_NOT_UPLOAD"
    built = _build(builder, resolution)
    assert built["release_truths"] == request["release_truths"]
    assert resolution.resolved["release_truths_source"].endswith("cowork_run.json")


def test_the_field_size_comes_from_the_standings_bytes(builder, run_snapshot):
    """The observed row count is the contest's true settled field, and nothing else has it."""
    resolution = _resolve(builder, run_snapshot)
    assert resolution.resolved["observed_field_size"] == 2
    assert _build(builder, resolution)["contest"]["field_size"] == 2


def test_an_evidence_issue_is_always_present(builder, run_snapshot):
    """The contract requires one whenever evidence is not PASS, which is every slate so far."""
    built = _build(builder, _resolve(builder, run_snapshot))
    assert built["evidence_issues"]
    assert built["evidence_issues"][0]["code"] == "PROSPECTIVE_VALIDATION_ABSENT"


# ---------------------------------------------------------------------------
# Refusals — the state every real contest is actually in
# ---------------------------------------------------------------------------


def test_a_missing_prelock_manifest_is_named_not_reconstructed(builder, run_snapshot):
    """The finding. Reconstructing a pre-lock prediction after the fact is forbidden."""
    run_dir, _, _ = run_snapshot
    (run_dir / "prelock_manifest.json").unlink()
    resolution = _resolve(builder, run_snapshot)
    assert any(b.startswith("PRELOCK_MANIFEST_ABSENT") for b in resolution.blockers)
    with pytest.raises(builder.SettlementRequestError, match="SETTLEMENT_REQUEST_INCOMPLETE"):
        _build(builder, resolution)


def test_a_scenario_bank_the_manifest_declares_but_the_run_lost_is_named(builder, run_snapshot):
    """Declared-but-absent is a different failure from never-declared, and says so."""
    run_dir, _, _ = run_snapshot
    for bank in (run_dir / "scenarios").iterdir():
        bank.unlink()
    resolution = _resolve(builder, run_snapshot)
    assert any(b.startswith("SCENARIO_BANK_BYTES_ABSENT") for b in resolution.blockers)


def _without_scenarios(run_dir, model_status="PRIOR_ONLY"):
    manifest = run_dir / "prelock_manifest.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["scenario_artifacts"] = {}
    payload["MODEL_STATUS"] = model_status
    manifest.write_text(json.dumps(payload), encoding="utf-8")


def test_a_prior_only_run_may_declare_no_scenario_bank(builder, run_snapshot):
    """The state every run on the path Ben actually uses is in.

    `prior_review` simulates nothing, so binding zero banks is the truthful
    outcome rather than a gap. Since Q1C the request contract permits it for a
    PRIOR_ONLY model and refuses it for every other.
    """
    run_dir, _, _ = run_snapshot
    _without_scenarios(run_dir)
    resolution = _resolve(builder, run_snapshot)
    assert not any(b.startswith("SCENARIO_BANK") for b in resolution.blockers)
    assert resolution.resolved["scenarios"] == []


def test_a_validated_model_may_not_declare_no_scenario_bank(builder, run_snapshot):
    """The relaxation must not reach the path where the banks do real work."""
    run_dir, _, _ = run_snapshot
    _without_scenarios(run_dir, model_status="PROSPECTIVELY_VALIDATED")
    resolution = _resolve(builder, run_snapshot)
    blocker = next(b for b in resolution.blockers if b.startswith("SCENARIO_BANK_ABSENT"))
    assert "PROSPECTIVELY_VALIDATED" in blocker


def test_a_missing_prediction_artifact_is_named(builder, run_snapshot):
    run_dir, _, _ = run_snapshot
    (run_dir / "projected" / "team_projections.csv").unlink()
    resolution = _resolve(builder, run_snapshot)
    assert any(b.startswith("PREDICTION_ARTIFACT_ABSENT") for b in resolution.blockers)


def test_a_missing_payout_table_is_named_never_inferred(builder, run_snapshot):
    """Payout tiers are never inferred from a contest name."""
    run_dir, contest_id, _ = run_snapshot
    (run_dir / "payouts_operator_supplied.csv").unlink()
    resolution = builder.resolve_contest(
        contest_id, run_dir, assignments=run_dir / "assignments.csv"
    )
    assert any(b.startswith("PAYOUT_TABLE_ABSENT") for b in resolution.blockers)


def test_a_missing_normalized_standings_points_at_the_normalizer(builder, run_snapshot):
    run_dir, contest_id, _ = run_snapshot
    for path in (builder.NORMALIZED_DIR / contest_id).iterdir():
        path.unlink()
    resolution = _resolve(builder, run_snapshot)
    blocker = next(b for b in resolution.blockers if b.startswith("NORMALIZED_STANDINGS_ABSENT"))
    assert "file_standings.py" in blocker


def test_an_ambiguous_assignment_is_never_chosen_for_the_operator(builder, run_snapshot):
    """A run can hold an early review and the export that actually reached DK.

    Picking between them is exactly the judgement a builder must not make
    silently: the wrong one settles a lineup Ben never entered.
    """
    run_dir, contest_id, _ = run_snapshot
    (run_dir / "assignments_v2.csv").write_bytes((run_dir / "assignments.csv").read_bytes())
    resolution = builder.resolve_contest(
        contest_id, run_dir, payouts=run_dir / "payouts_operator_supplied.csv"
    )
    assert any(b.startswith("ASSIGNMENT_AMBIGUOUS") for b in resolution.blockers)


def test_a_field_above_the_registered_budget_is_excluded_not_approximated(builder, run_snapshot):
    """Contest 193028206 settled 832,342 entries against a 200,000 ceiling.

    The complete-field rule allows no partial settlement, so the honest outcome
    is a named exclusion rather than a sampled estimate.
    """
    run_dir, contest_id, _ = run_snapshot
    monkey = builder.DEFAULT_REFERENCE_BUDGET["max_entries"]
    builder.DEFAULT_REFERENCE_BUDGET["max_entries"] = 1
    try:
        resolution = _resolve(builder, run_snapshot)
    finally:
        builder.DEFAULT_REFERENCE_BUDGET["max_entries"] = monkey
    blocker = next(
        b for b in resolution.blockers if b.startswith("REFERENCE_SIZE_BUDGET_EXCEEDED")
    )
    assert "complete-field rule" in blocker


def test_a_contest_absent_from_the_entry_template_is_refused(builder, run_snapshot):
    run_dir, _, _ = run_snapshot
    resolution = builder.resolve_contest(
        "999999999",
        run_dir,
        assignments=run_dir / "assignments.csv",
        payouts=run_dir / "payouts_operator_supplied.csv",
    )
    assert any(b.startswith("CONTEST_NOT_IN_ENTRY_TEMPLATE") for b in resolution.blockers)


def test_an_absent_run_snapshot_is_refused(builder, tmp_path):
    resolution = builder.resolve_contest("195379585", tmp_path / "nope")
    assert any(b.startswith("RUN_SNAPSHOT_ABSENT") for b in resolution.blockers)


def test_an_existing_request_is_never_overwritten(builder, run_snapshot, tmp_path, monkeypatch):
    run_dir, contest_id, _ = run_snapshot
    destination = tmp_path / "request.json"
    destination.write_text("{}", encoding="utf-8")
    code = builder.main([
        "--contest", contest_id,
        "--run", run_dir.name,
        "--assignments", str(run_dir / "assignments.csv"),
        "--payouts", str(run_dir / "payouts_operator_supplied.csv"),
        "--advertised-prize-value", "20.00",
        "--out", str(destination),
    ])
    assert code == 2
    assert destination.read_text(encoding="utf-8") == "{}"


def test_report_mode_exits_nonzero_while_anything_is_unresolved(builder, run_snapshot, capsys):
    run_dir, contest_id, _ = run_snapshot
    (run_dir / "prelock_manifest.json").unlink()
    code = builder.main(["--contest", contest_id, "--run", run_dir.name, "--report"])
    assert code == 2
    assert "PRELOCK_MANIFEST_ABSENT" in capsys.readouterr().out
