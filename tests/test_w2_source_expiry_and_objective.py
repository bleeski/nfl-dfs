"""W2 regression baseline: the two defects R07 and R08 name, as failing tests.

Both probes reproduce the review's own independent reproductions and both fail
on `f318882`:

* R08 (`docs/PRODUCTION_READINESS_REVIEW_2026-09-08.md`): a package whose source
  metadata expired September 5 was accepted by `validate_source_ledger` at a
  September 8 clock, and the produced package references its inputs by absolute
  original path, so a copied package cannot resolve them.
* R07: two candidates on a fixed 100-scenario payout distribution selected the
  constant-1.5 candidate; replicating those same rows 100 times, leaving the
  empirical distribution unchanged, selected the variable candidate with mean
  2.0.

Nothing here asserts a model claim. `MODEL_STATUS` stays `PRIOR_ONLY` and
`RELEASE_DECISION` stays `DO_NOT_UPLOAD` on every path these probes touch.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

from pydantic import ValidationError

from nfl_dfs.contracts import (
    ContestObjective,
    EvidenceState,
    SourceFreshness,
    SourceLedger,
    earliest_expiry,
    source_freshness_evidence,
)
from nfl_dfs.economics import CandidateEconomics
from nfl_dfs.evidence import (
    EvidenceError,
    source_ledger_evidence,
    validate_source_ledger,
)
from nfl_dfs.hashing import sha256_file
from nfl_dfs.portfolio import select_portfolio
from nfl_dfs.projection import (
    ProjectionBuildError,
    build_projection_package,
    verify_projection_package,
)

from .test_projection_producer import AS_OF, EXPIRES, SHOWDOWN_SALARY, _prepare


# The review's clock. `EXPIRES` is 2026-09-05T12:00Z and `AS_OF` is
# 2026-09-04T12:00Z, so this package is valid at creation and expired here.
RELEASE_CLOCK = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)


def _expected_outputs(package) -> dict[str, str]:
    return {
        "team_projections": sha256_file(package.team_projections),
        "player_opportunities": sha256_file(package.player_opportunities),
    }


# --------------------------------------------------------------------------- #
# R08 - source expiry is lost after production
# --------------------------------------------------------------------------- #


def test_r08_probe_a_package_valid_at_creation_is_stale_at_its_real_expiry(
    tmp_path: Path,
) -> None:
    """The review's exact probe: expired September 5, accepted at September 8."""

    package = build_projection_package(**_prepare(tmp_path))
    expected = _expected_outputs(package)

    # Valid at creation. The producer's own `as_of` precedes every source expiry.
    validate_source_ledger(
        package.source_ledger,
        expected_outputs=expected,
        now=datetime.fromisoformat(AS_OF),
    )

    # The same bytes at a clock past the recorded source expiry are stale. The
    # ledger must carry the expiry itself; a hash match is not freshness.
    assert datetime.fromisoformat(EXPIRES) < RELEASE_CLOCK
    with pytest.raises(EvidenceError, match="stale"):
        validate_source_ledger(
            package.source_ledger,
            expected_outputs=expected,
            now=RELEASE_CLOCK,
        )


def test_r08_probe_a_new_market_timestamp_does_not_renew_old_player_evidence(
    tmp_path: Path,
) -> None:
    """Copying a ledger and re-validating it at a fresh clock renews nothing."""

    package = build_projection_package(**_prepare(tmp_path))
    expected = _expected_outputs(package)
    copied = tmp_path / "copied-package"
    shutil.copytree(package.output_dir, copied)

    with pytest.raises(EvidenceError, match="stale"):
        validate_source_ledger(
            copied / "source_ledger.json",
            expected_outputs=expected,
            now=RELEASE_CLOCK,
        )


def test_r08_probe_a_copied_package_validates_without_the_original_inputs(
    tmp_path: Path,
) -> None:
    """A self-contained package resolves with every original attachment deleted."""

    build_root = tmp_path / "build"
    build_root.mkdir()
    salary_copy = build_root / "DKSalaries.csv"
    salary_copy.write_bytes(SHOWDOWN_SALARY.read_bytes())
    args = _prepare(build_root, salary_copy)
    package = build_projection_package(**args)
    expected = _expected_outputs(package)

    copied = tmp_path / "elsewhere" / "package"
    copied.parent.mkdir(parents=True)
    shutil.copytree(package.output_dir, copied)

    # Every original attachment path is gone, including the salary CSV.
    for key in ("salaries", "team_source", "player_source", "identity_map"):
        Path(args[key]).unlink()
    shutil.rmtree(package.output_dir)

    ledger = validate_source_ledger(
        copied / "source_ledger.json",
        expected_outputs=expected,
        now=datetime.fromisoformat(AS_OF),
    )
    # Resolution is a lookup inside the package, so no entry may point outside
    # it and no Windows-to-Linux path rewrite can be required.
    for entry in ledger.entries:
        assert not Path(entry.path).is_absolute()
        assert (copied / entry.path).is_file()


def test_r08_probe_a_forged_ledger_expiry_is_refused_by_its_archived_source(
    tmp_path: Path,
) -> None:
    """Writing a newer expiry into a copied ledger renews nothing.

    The ledger is a plain JSON file, so preserving the expiry inside it is only
    half the repair: the archived source it describes has to agree.
    """

    package = build_projection_package(**_prepare(tmp_path))
    expected = _expected_outputs(package)
    copied = tmp_path / "forged"
    shutil.copytree(package.output_dir, copied)

    ledger_path = copied / "source_ledger.json"
    payload = json.loads(ledger_path.read_text(encoding="utf-8"))
    renewed = (RELEASE_CLOCK + timedelta(hours=12)).isoformat()
    for entry in payload["entries"]:
        entry["expires_at"] = renewed
    ledger_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    # The forged ledger now passes the freshness check in isolation, which is
    # why the check cannot end at the ledger.
    validate_source_ledger(
        ledger_path, expected_outputs=expected, now=RELEASE_CLOCK
    )
    with pytest.raises(
        ProjectionBuildError, match="LEDGER_EXPIRY_DISAGREES_WITH_ARCHIVED_SOURCE"
    ):
        verify_projection_package(copied, at=RELEASE_CLOCK, expected_outputs=expected)


def test_r08_probe_the_package_verifier_re_evaluates_at_the_clock_it_is_given(
    tmp_path: Path,
) -> None:
    """One package, two clocks, two verdicts, no source byte re-read."""

    package = build_projection_package(**_prepare(tmp_path))

    verify_projection_package(package.output_dir, at=datetime.fromisoformat(AS_OF))
    with pytest.raises(ProjectionBuildError, match="stale"):
        verify_projection_package(package.output_dir, at=RELEASE_CLOCK)


def test_r08_probe_a_cowork_snapshot_carries_the_archived_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The snapshot boundary is the one Cowork actually crosses every run.

    A snapshot copies each supplied path as a single flat file. That worked
    only because the ledger entries pointed at absolute originals, so the
    versioned ledger's archived sources have to travel with it.
    """

    from nfl_dfs import cli

    package = build_projection_package(**_prepare(tmp_path))
    expected = _expected_outputs(package)
    monkeypatch.setattr(cli, "DEFAULT_RUNS_DIR", tmp_path / "runs")

    hashes = cli._snapshot_inputs("snapshot-test", [package.source_ledger])

    snapshotted = cli._snapshot_path(
        "snapshot-test", package.source_ledger, hashes[str(Path(package.source_ledger))]
    )
    assert snapshotted.is_file()
    assert (snapshotted.parent / "sources").is_dir()
    # The copy resolves on its own, with the produced package untouched.
    validate_source_ledger(
        snapshotted,
        expected_outputs=expected,
        now=datetime.fromisoformat(AS_OF),
    )


def test_r08_probe_deleting_an_entry_does_not_evade_the_expiry_check(
    tmp_path: Path,
) -> None:
    """An incomplete entry set is refused, not quietly accepted.

    Checking only the entries that are present would make deleting the expired
    entry exactly as effective as forging its expiry.
    """

    package = build_projection_package(**_prepare(tmp_path))
    expected = _expected_outputs(package)
    copied = tmp_path / "pruned"
    shutil.copytree(package.output_dir, copied)

    ledger_path = copied / "source_ledger.json"
    payload = json.loads(ledger_path.read_text(encoding="utf-8"))
    payload["entries"] = [
        entry for entry in payload["entries"] if entry["evidence_scope"] != "TEAM_PRIOR"
    ]
    assert len(payload["entries"]) == 3
    ledger_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    with pytest.raises(
        ProjectionBuildError, match="PACKAGE_SCOPE_COVERAGE_MISMATCH"
    ):
        verify_projection_package(
            copied, at=datetime.fromisoformat(AS_OF), expected_outputs=expected
        )


def test_r08_probe_a_legacy_ledger_cannot_clear_the_release_gate(
    tmp_path: Path,
) -> None:
    """A shape that cannot express an expiry cannot be called fresh.

    Downgrading the schema and dropping the four consumed fields would
    otherwise pass every remaining check: the hashes still match and the paths
    still resolve.
    """

    package = build_projection_package(**_prepare(tmp_path))
    expected = _expected_outputs(package)
    payload = json.loads(Path(package.source_ledger).read_text(encoding="utf-8"))

    fresh = source_ledger_evidence(
        package.source_ledger,
        expected_outputs=expected,
        as_of=datetime.fromisoformat(AS_OF),
    )
    assert fresh.state is EvidenceState.PASS
    assert fresh.expires_at == datetime.fromisoformat(EXPIRES)

    stale = source_ledger_evidence(
        package.source_ledger, expected_outputs=expected, as_of=RELEASE_CLOCK
    )
    assert stale.state is EvidenceState.STALE

    downgraded = tmp_path / "legacy" / "source_ledger.json"
    downgraded.parent.mkdir(parents=True)
    for entry in payload["entries"]:
        for field_name in (
            "expires_at",
            "evidence_state",
            "evidence_scope",
            "transformation_version",
            "depends_on",
        ):
            entry.pop(field_name, None)
        # The archived bytes travel with the downgrade, so nothing else fails.
        source = Path(package.output_dir) / entry["path"]
        target = downgraded.parent / entry["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    payload["schema_version"] = "nfl_source_ledger_v1"
    downgraded.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    # The legacy shape still validates for integrity, which is the whole
    # problem: hashes are not freshness.
    validate_source_ledger(
        downgraded, expected_outputs=expected, now=RELEASE_CLOCK
    )
    legacy = source_ledger_evidence(
        downgraded, expected_outputs=expected, as_of=datetime.fromisoformat(AS_OF)
    )
    assert legacy.state is EvidenceState.UNKNOWN
    assert legacy.expires_at is None
    assert "no per-source expiry" in legacy.reason


def test_r08_probe_a_non_pass_label_cannot_hide_or_widen_an_expiry() -> None:
    """The declared state and the clock compose; the window stays the earliest."""

    now = datetime(2026, 9, 8, tzinfo=timezone.utc)
    expired = datetime(2020, 1, 1, tzinfo=timezone.utc)

    # A label that release aggregation drops must not suppress staleness.
    for label in (EvidenceState.NOT_APPLICABLE, EvidenceState.NOT_YET_DUE):
        record = SourceFreshness(
            label="odd", expires_at=expired, declared_state=label
        )
        assert record.state_at(now) is EvidenceState.STALE
    # A conflict is worse than stale and survives.
    conflicted = SourceFreshness(
        label="bad", expires_at=expired, declared_state=EvidenceState.CONFLICTED
    )
    assert conflicted.state_at(now) is EvidenceState.CONFLICTED

    soon = SourceFreshness(
        label="soon", expires_at=datetime(2026, 9, 9, tzinfo=timezone.utc)
    )
    later = SourceFreshness(
        label="later",
        expires_at=datetime(2027, 1, 1, tzinfo=timezone.utc),
        declared_state=EvidenceState.NOT_APPLICABLE,
    )
    record = source_freshness_evidence(
        (soon, later), subject="s", field="f", at=now
    )
    assert record.expires_at == soon.expires_at
    assert earliest_expiry((soon, later)) == soon.expires_at


def test_r08_probe_a_versioned_entry_path_cannot_escape_the_package() -> None:
    """Both path flavours, because a Windows escape is opaque to PurePosixPath."""

    now = datetime(2026, 9, 8, tzinfo=timezone.utc)

    def ledger(entry_path: str) -> dict[str, object]:
        return {
            "schema_version": "nfl_source_ledger_v2",
            "entries": [
                {
                    "artifact_id": "a" * 64,
                    "path": entry_path,
                    "source_uri": "https://raw.githubusercontent.com/x/y/main/z.json",
                    "captured_at": now.isoformat(),
                    "observed_at": now.isoformat(),
                    "expires_at": (now + timedelta(hours=1)).isoformat(),
                    "license_decision": "PERMITTED_REPOSITORY_LICENSE",
                    "parser_version": "p_v1",
                    "evidence_state": "PASS",
                    "evidence_scope": "TEAM_PRIOR",
                    "transformation_version": "T_V1",
                    "depends_on": {},
                }
            ],
            "derived": {"team_projections": "1" * 64},
        }

    SourceLedger.model_validate(ledger("sources/a.json"))
    for escape in (
        "/etc/passwd",
        "C:\\Windows\\x",
        "../../etc/passwd",
        "..\\..\\etc\\passwd",
        "\\Windows\\x",
    ):
        with pytest.raises(ValidationError):
            SourceLedger.model_validate(ledger(escape))


# --------------------------------------------------------------------------- #
# R07 - selection changes with simulation count for the same empirical outcomes
# --------------------------------------------------------------------------- #


def _two_candidate_economics(gross: np.ndarray) -> CandidateEconomics:
    """Two candidates on a fixed payout distribution, identical rank geometry.

    Ranks are held equal and outside every elite band so the payout
    distribution is the only thing that differs between the two candidates.
    """

    scenarios = gross.shape[0]
    return CandidateEconomics(
        rosters=(("A",), ("B",)),
        gross_payout=gross.astype(np.float32),
        ranks=np.full((scenarios, 2), 50, dtype=np.int32),
        tie_counts=np.ones((scenarios, 2), dtype=np.int32),
        duplicate_counts=np.zeros(2, dtype=np.int32),
    )


def _fixed_distribution() -> np.ndarray:
    """Candidate A pays a constant 1.5. Candidate B has mean 2.0, sd 4.0."""

    gross = np.zeros((100, 2), dtype=np.float64)
    gross[:, 0] = 1.5
    gross[:20, 1] = 10.0
    assert gross[:, 0].mean() == pytest.approx(1.5)
    assert gross[:, 1].mean() == pytest.approx(2.0)
    return gross


def _select(gross: np.ndarray, *, repeats: int = 1):
    """Select on one bank, declaring how many rows carry each distinct draw.

    Multiplicity is declared rather than inferred from outcomes: independent
    scenarios often settle a portfolio at the same value, and collapsing those
    would understate precision and, through `qa.referee_blocks`, widen the
    REFEREE tolerance.
    """

    declared = (
        None
        if repeats == 1
        else {"BASE": np.full(gross.shape[0], repeats, dtype=np.int64)}
    )
    return select_portfolio(
        {"BASE": _two_candidate_economics(gross)},
        entry_count=1,
        entry_fee=0.0,
        field_size=1000,
        objective=ContestObjective.LARGE_GPP,
        shortlist_limit=2,
        scenario_multiplicity=declared,
    )


def test_r07_probe_replicated_scenario_rows_do_not_change_the_selection() -> None:
    """The review's exact probe, as an invariance assertion."""

    gross = _fixed_distribution()
    replicated = np.repeat(gross, 100, axis=0)
    assert replicated.shape == (10_000, 2)
    # Replication leaves the empirical distribution untouched.
    assert replicated[:, 1].mean() == pytest.approx(gross[:, 1].mean())

    hundred = _select(gross)
    ten_thousand = _select(replicated)

    assert hundred.candidate_indices == ten_thousand.candidate_indices
    # The economic preference is the higher expectation, at either count.
    assert hundred.candidate_indices == (1,)


def test_r07_probe_replication_does_not_shrink_the_reported_uncertainty() -> None:
    """Duplicated rows carry no new information, so precision cannot improve."""

    gross = _fixed_distribution()
    hundred = _select(gross)
    replicated = _select(np.repeat(gross, 100, axis=0), repeats=100)

    # 100 distinct draws either way, and the same reported uncertainty.
    assert hundred.effective_scenario_count == pytest.approx(100.0)
    assert replicated.effective_scenario_count == pytest.approx(100.0)
    assert replicated.objective_standard_error == pytest.approx(
        hundred.objective_standard_error
    )
    # The reported figure is the honest one for 100 draws of this distribution,
    # not an artifact of collapsing equal outcomes: sd 4.0 over 100 draws.
    assert hundred.objective_standard_error == pytest.approx(0.4020, abs=1e-4)


def test_r07_probe_an_undeclared_bank_is_treated_as_independent_draws() -> None:
    """No declaration means one draw per row, which is what production has.

    `economics.evaluate_candidates_against_field` refuses a non-uniform
    scenario bank, so every bank the engine builds today is all-distinct. An
    overstated standard error would widen the REFEREE tolerance rather than
    narrow it, so silence has to mean independent, not dependent.
    """

    from nfl_dfs.portfolio import resolve_effective_sample_size

    assert resolve_effective_sample_size(4000) == pytest.approx(4000.0)
    assert resolve_effective_sample_size(
        4000, np.ones(4000, dtype=np.int64)
    ) == pytest.approx(4000.0)
    assert resolve_effective_sample_size(
        4000, np.full(4000, 40, dtype=np.int64)
    ) == pytest.approx(100.0)
    with pytest.raises(ValueError, match="one entry per scenario row"):
        resolve_effective_sample_size(4000, np.ones(3, dtype=np.int64))


def test_r07_probe_independent_precision_moves_uncertainty_not_selection() -> None:
    """More genuinely independent scenarios sharpen the estimate, not the choice."""

    generator = np.random.default_rng(20260908)

    def independent(scenarios: int) -> np.ndarray:
        gross = np.zeros((scenarios, 2), dtype=np.float64)
        gross[:, 0] = 1.5
        gross[:, 1] = generator.gamma(shape=2.0, scale=1.0, size=scenarios)
        return gross

    small = _select(independent(500))
    large = _select(independent(50_000))

    assert small.candidate_indices == large.candidate_indices
    assert large.effective_scenario_count > 10 * small.effective_scenario_count
    assert large.objective_standard_error < 0.5 * small.objective_standard_error
