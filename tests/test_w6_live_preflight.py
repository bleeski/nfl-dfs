"""W6 / R09: historical artifact integrity is not a current upload decision.

`audit` read a stored manifest and fed its stored truth fields straight into the
release policy. It never reparsed evidence expiry at the current clock, never
rebound the assignment, template or salary files it claimed to cover, and never
validated the manifest's own schema. A stored green result therefore stayed
green after its evidence expired, and the exit code described audit problems
rather than whether the release decision permits upload.

Every probe here fails on 6cd710e: `nfl_dfs.preflight` and `command_preflight`
did not exist, and `command_audit` reported `CERTIFIED_UPLOAD_PACKAGE` on
January evidence.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from nfl_dfs import certification as certification_module
from nfl_dfs.certification import certify_upload
from nfl_dfs.cli import command_audit, command_preflight
from nfl_dfs.contracts import EvidenceRecord, EvidenceState
from nfl_dfs.hashing import sha256_file
from nfl_dfs.optimizer import LineupOptimizer
from nfl_dfs.preflight import historical_artifact_integrity, live_pre_upload_check


EXPIRED = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "supplied"
SALARY_CSV = FIXTURE_ROOT / "DKSalaries Salary CSV Classic.csv"
ENTRIES_CSV = FIXTURE_ROOT / "DKEntries CSV.csv"


def _before_fixture_lock(slate, *, minutes: int = 30) -> datetime:
    """A clock inside the supplied fixture slate's own pre-lock window.

    The fixture is the real 2026-09-13 Classic slate, whose players lock at real
    wall-clock times. A live check anchored to `datetime.now()` therefore passed
    only until that slate kicked off and reported
    SELECTED_PLAYER_ALREADY_LOCKED permanently afterwards. This is the same
    defect as the hardcoded AS_OF in `test_priors_adapter.py` (P3-17), one file
    over and worse: that one failed for a day, this one fails forever. A replay
    supplies its own clock, which is what `preflight.py` documents.
    """

    earliest = min(player.lock_at for player in slate.players).astimezone(timezone.utc)
    return earliest - timedelta(minutes=minutes)


def _assignments(slate, entries):
    scores = {player.dk_id: 50_000 / max(player.salary, 1) for player in slate.players}
    optimizer = LineupOptimizer(slate)
    result = {}
    for entry in sorted(entries.authorizations, key=lambda item: item.entry_id):
        solved = optimizer.solve(scores)
        assert solved.roster is not None
        result[entry.entry_id] = solved.roster
        optimizer.add_no_good(solved.roster)
    return result


def _evidence(slate, entries, assignments, *, expires_at):
    now = datetime.now(timezone.utc)
    selected = {dk_id: "ACTIVE" for roster in assignments.values() for dk_id in roster}
    return [
        EvidenceRecord(subject="slate", field="salary_pool", value=True, source_artifact_id=slate.salary_hash, observed_at=now, hard_gate=True, state=EvidenceState.PASS, reason="parsed"),
        EvidenceRecord(subject="entries", field="entry_authorization", value=True, source_artifact_id=entries.raw_hash, observed_at=now, hard_gate=True, state=EvidenceState.PASS, reason="reconciled"),
        EvidenceRecord(subject="contest", field="payout_contract", value=True, source_artifact_id="b" * 64, observed_at=now, hard_gate=True, state=EvidenceState.PASS, reason="reconciled"),
        EvidenceRecord(subject="selected", field="official_inactive_status", value=selected, source_artifact_id="a" * 64, observed_at=now, expires_at=expires_at, hard_gate=True, state=EvidenceState.PASS, reason="official exact IDs"),
        EvidenceRecord(subject="slate", field="weather_if_required", hard_gate=True, state=EvidenceState.NOT_APPLICABLE, reason="manual guardrail"),
        EvidenceRecord(subject="slate", field="market_line", hard_gate=True, state=EvidenceState.NOT_APPLICABLE, reason="manual guardrail"),
    ]


def _certified(tmp_path: Path, slate, entries, *, expires_at, monkeypatch=None, now=None):
    """A genuinely certified package whose official evidence expires at `expires_at`.

    `certify_upload` grades its evidence at the live clock and takes no `now`,
    so a package whose expiry sits inside the fixture slate's own pre-lock
    window cannot be certified today without pinning that clock. Pass
    `monkeypatch` and `now` to do it; the injection point is the one function
    certification uses to grade evidence, not `datetime` itself.
    """

    if now is not None:
        if monkeypatch is None:
            raise AssertionError("pinning the certification clock needs monkeypatch")
        graded = certification_module.aggregate_evidence_state
        monkeypatch.setattr(
            certification_module,
            "aggregate_evidence_state",
            lambda evidence, **kwargs: graded(evidence, **{**kwargs, "now": now}),
        )
    assignments = _assignments(slate, entries)
    output = tmp_path / "upload.csv"
    manifest_path = tmp_path / "upload.manifest.json"
    manifest = certify_upload(
        run_id="w6-live",
        slate=slate,
        template=entries,
        assignments=assignments,
        evidence=_evidence(slate, entries, assignments, expires_at=expires_at),
        output_path=output,
        manifest_path=manifest_path,
    )
    assert manifest.release_decision.value == "CERTIFIED_UPLOAD_PACKAGE"
    return manifest_path, output


def _stale_stored_manifest(tmp_path: Path, slate, entries) -> tuple[Path, Path]:
    """A stored manifest whose evidence has since expired, output hash intact.

    This is the review's independent reproduction. Nothing about the file is
    malformed, and the bytes it points at are exactly the bytes it certified.
    Only the clock moved.
    """
    manifest_path, output = _certified(
        tmp_path, slate, entries, expires_at=datetime.now(timezone.utc) + timedelta(hours=1)
    )
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    for record in data["evidence"]:
        if record.get("expires_at"):
            record["expires_at"] = EXPIRED.isoformat().replace("+00:00", "Z")
    manifest_path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    return manifest_path, output


# --------------------------------------------------------------------------
# R09 reproduction
# --------------------------------------------------------------------------


def test_audit_alone_cannot_report_a_current_upload_ready_result(
    tmp_path: Path, classic_slate, classic_entries, capsys: pytest.CaptureFixture[str]
) -> None:
    """Expired evidence plus a matching output hash must not read as certified.

    The bytes really are intact, so archival integrity passes and `audit` exits
    0 to say exactly that. What it may no longer do is present that as a current
    release decision: `RELEASE_DECISION` is pinned to `DO_NOT_UPLOAD`, the
    manifest's own claim is reported separately and labelled as stored, and the
    scope names the question actually answered. The exit code that follows the
    release decision belongs to `preflight`.
    """
    manifest_path, _ = _stale_stored_manifest(tmp_path, classic_slate, classic_entries)
    code = command_audit(argparse.Namespace(manifest=str(manifest_path)))
    result = json.loads(capsys.readouterr().out)
    assert result["check_scope"] == "HISTORICAL_ARTIFACT_INTEGRITY"
    assert result["RELEASE_DECISION"] == "DO_NOT_UPLOAD"
    assert result["release_decision_basis"] == "HISTORICAL_ONLY"
    assert result["manifest_stored_RELEASE_DECISION"] == "CERTIFIED_UPLOAD_PACKAGE"
    assert result["ARTIFACT_INTEGRITY"] == "PASS"
    assert code == 0

    # The same package, asked the release question, is refused.
    live = live_pre_upload_check(manifest_path, salaries=SALARY_CSV)
    assert live["RELEASE_DECISION"] == "DO_NOT_UPLOAD"
    assert live["EVIDENCE_STATE"] == "STALE"


def test_historical_check_never_renews_certification(
    tmp_path: Path, classic_slate, classic_entries
) -> None:
    """Even a perfectly intact, unexpired package is not re-certified by audit."""
    manifest_path, _ = _certified(
        tmp_path, classic_slate, classic_entries,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=6),
    )
    report = historical_artifact_integrity(manifest_path)
    assert report["ARTIFACT_INTEGRITY"] == "PASS"
    assert report["RELEASE_DECISION"] == "DO_NOT_UPLOAD"
    assert report["release_decision_basis"] == "HISTORICAL_ONLY"
    assert report["manifest_stored_RELEASE_DECISION"] == "CERTIFIED_UPLOAD_PACKAGE"


# --------------------------------------------------------------------------
# The live pre-upload check
# --------------------------------------------------------------------------


def test_live_check_refuses_expired_evidence_at_the_current_clock(
    tmp_path: Path, classic_slate, classic_entries
) -> None:
    manifest_path, _ = _stale_stored_manifest(tmp_path, classic_slate, classic_entries)
    report = live_pre_upload_check(manifest_path, salaries=SALARY_CSV)
    assert report["RELEASE_DECISION"] == "DO_NOT_UPLOAD"
    assert report["EVIDENCE_STATE"] == "STALE"
    assert any("official_inactive_status" in blocker for blocker in report["blockers"])


def test_live_check_recomputes_at_the_clock_it_is_given(
    tmp_path: Path, classic_slate, classic_entries, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same package, two clocks: fresh before the expiry, stale one second after."""
    expires = _before_fixture_lock(classic_slate)
    manifest_path, _ = _certified(
        tmp_path, classic_slate, classic_entries, expires_at=expires,
        monkeypatch=monkeypatch, now=expires - timedelta(minutes=1),
    )
    before = live_pre_upload_check(
        manifest_path, salaries=SALARY_CSV, now=expires - timedelta(seconds=1)
    )
    after = live_pre_upload_check(
        manifest_path, salaries=SALARY_CSV, now=expires + timedelta(seconds=1)
    )
    assert before["RELEASE_DECISION"] == "CERTIFIED_UPLOAD_PACKAGE"
    assert after["RELEASE_DECISION"] == "DO_NOT_UPLOAD"
    assert after["EVIDENCE_STATE"] == "STALE"


def test_live_check_rebinds_the_files_the_manifest_claims_to_cover(
    tmp_path: Path, classic_slate, classic_entries
) -> None:
    """A changed assignment CSV on disk cannot pass a live check."""
    expires = datetime.now(timezone.utc) + timedelta(hours=2)
    manifest_path, _ = _certified(tmp_path, classic_slate, classic_entries, expires_at=expires)
    forged = tmp_path / "assignments.csv"
    forged.write_text("Entry ID,QB\n1,2\n", encoding="utf-8")
    report = live_pre_upload_check(manifest_path, salaries=SALARY_CSV, assignments=forged)
    assert report["FILE_VALID"] is False
    assert report["RELEASE_DECISION"] == "DO_NOT_UPLOAD"
    assert any("assignments" in blocker for blocker in report["blockers"])


def test_live_check_binds_a_matching_file_as_pass(
    tmp_path: Path, classic_slate, classic_entries, monkeypatch: pytest.MonkeyPatch
) -> None:
    expires = _before_fixture_lock(classic_slate)
    manifest_path, output = _certified(
        tmp_path, classic_slate, classic_entries, expires_at=expires,
        monkeypatch=monkeypatch, now=expires - timedelta(minutes=1),
    )
    report = live_pre_upload_check(
        manifest_path, salaries=SALARY_CSV, entries=ENTRIES_CSV,
        now=expires - timedelta(minutes=1),
    )
    assert report["RELEASE_DECISION"] == "CERTIFIED_UPLOAD_PACKAGE"
    bound = {check["name"]: check for check in report["checks"]}
    assert bound["output_bytes"]["state"] == "PASS"
    assert bound["output_bytes"]["detail"].endswith(sha256_file(output))
    assert bound["input_salary"]["state"] == "PASS"
    assert bound["input_entries"]["state"] == "PASS"


def test_live_check_refuses_a_manifest_with_an_unknown_schema(
    tmp_path: Path, classic_slate, classic_entries
) -> None:
    manifest_path, _ = _certified(
        tmp_path, classic_slate, classic_entries,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
    )
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    data["manifest_version"] = "certification_manifest_v99"
    manifest_path.write_text(json.dumps(data), encoding="utf-8")
    report = live_pre_upload_check(manifest_path, salaries=SALARY_CSV)
    assert report["RELEASE_DECISION"] == "DO_NOT_UPLOAD"
    assert any("MANIFEST_SCHEMA" in blocker for blocker in report["blockers"])


def test_live_check_refuses_a_malformed_manifest(tmp_path: Path) -> None:
    broken = tmp_path / "broken.manifest.json"
    broken.write_text("{not json", encoding="utf-8")
    report = live_pre_upload_check(broken)
    assert report["RELEASE_DECISION"] == "DO_NOT_UPLOAD"
    assert any("MANIFEST_UNREADABLE" in blocker for blocker in report["blockers"])


def test_live_check_refuses_a_manifest_whose_evidence_is_missing(
    tmp_path: Path, classic_slate, classic_entries
) -> None:
    """Deleting the inconvenient record is as effective as forging its expiry."""
    manifest_path, _ = _certified(
        tmp_path, classic_slate, classic_entries,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
    )
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    data["evidence"] = [
        record for record in data["evidence"]
        if record.get("field") != "official_inactive_status"
    ]
    manifest_path.write_text(json.dumps(data), encoding="utf-8")
    report = live_pre_upload_check(manifest_path, salaries=SALARY_CSV)
    assert report["RELEASE_DECISION"] == "DO_NOT_UPLOAD"
    assert any("MANIFEST_EVIDENCE_SCOPE" in blocker for blocker in report["blockers"])


def test_live_check_refuses_when_the_certified_output_is_gone(
    tmp_path: Path, classic_slate, classic_entries
) -> None:
    manifest_path, output = _certified(
        tmp_path, classic_slate, classic_entries,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
    )
    output.unlink()
    report = live_pre_upload_check(manifest_path, salaries=SALARY_CSV)
    assert report["FILE_VALID"] is False
    assert report["RELEASE_DECISION"] == "DO_NOT_UPLOAD"


def test_live_check_reports_the_clock_and_scope_of_every_check(
    tmp_path: Path, classic_slate, classic_entries
) -> None:
    expires = datetime.now(timezone.utc) + timedelta(hours=2)
    manifest_path, _ = _certified(tmp_path, classic_slate, classic_entries, expires_at=expires)
    report = live_pre_upload_check(
        manifest_path, salaries=SALARY_CSV, now=expires - timedelta(minutes=1)
    )
    assert report["check_scope"] == "LIVE_PRE_UPLOAD"
    assert report["checked_at"]
    assert report["checks"]
    for check in report["checks"]:
        assert check["scope"] in {"LIVE_RECOMPUTE", "FILE_BINDING", "MANIFEST_SCHEMA"}
        assert check["state"] in {"PASS", "FAIL"}
        assert check["checked_at"]


def test_live_check_refuses_once_a_selected_player_has_locked(
    tmp_path: Path, classic_slate, classic_entries, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A package certified before lock is not uploadable after it.

    Every clock here is derived from the fixture's own lock times. The earlier
    version hardcoded `expires_at=2026-09-14`, so from 2026-09-14 onward the
    package could no longer be certified at the live clock and the test failed
    every day thereafter, for a reason that had nothing to do with what it
    tests. This is the defect `_before_fixture_lock` documents.

    The evidence deliberately stays valid past the check clock, so the only
    reason this package is refused is that a selected player has locked.
    """
    earliest_lock = min(
        player.lock_at for player in classic_slate.players
    ).astimezone(timezone.utc)
    certified_at = _before_fixture_lock(classic_slate)
    manifest_path, _ = _certified(
        tmp_path, classic_slate, classic_entries,
        expires_at=earliest_lock + timedelta(hours=6),
        monkeypatch=monkeypatch, now=certified_at,
    )

    after_lock = earliest_lock + timedelta(hours=1)
    report = live_pre_upload_check(manifest_path, salaries=SALARY_CSV, now=after_lock)
    assert report["RELEASE_DECISION"] == "DO_NOT_UPLOAD"
    assert any("SELECTED_PLAYER_ALREADY_LOCKED" in b for b in report["blockers"])
    # Not merely expired: the package's own evidence is still live at this clock.
    assert not any("EXPIRED" in blocker for blocker in report["blockers"])


def test_live_check_without_a_salary_csv_cannot_certify(
    tmp_path: Path, classic_slate, classic_entries
) -> None:
    """Locks cannot be re-derived without the current pool, so the check fails closed."""
    expires = datetime.now(timezone.utc) + timedelta(hours=2)
    manifest_path, _ = _certified(tmp_path, classic_slate, classic_entries, expires_at=expires)
    report = live_pre_upload_check(manifest_path, now=expires - timedelta(minutes=1))
    assert report["RELEASE_DECISION"] == "DO_NOT_UPLOAD"
    assert any("LIVE_BINDING_INCOMPLETE" in b for b in report["blockers"])


# --------------------------------------------------------------------------
# Exit codes
# --------------------------------------------------------------------------


def test_preflight_exit_code_follows_the_release_decision(
    tmp_path: Path, classic_slate, classic_entries, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest_path, _ = _stale_stored_manifest(tmp_path, classic_slate, classic_entries)
    code = command_preflight(
        argparse.Namespace(
            manifest=str(manifest_path), salaries=str(SALARY_CSV),
            entries=None, assignments=None,
        )
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["RELEASE_DECISION"] == "DO_NOT_UPLOAD"
    assert code == 2


def test_preflight_exit_zero_only_on_a_current_certified_decision(
    tmp_path: Path,
    classic_slate,
    classic_entries,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # `command_preflight` takes no clock: a release asks about right now. The
    # fixture slate's "right now" is 2026-09-13 before lock, so the test pins
    # that rather than borrowing today's. See `_before_fixture_lock`.
    expires = _before_fixture_lock(classic_slate)
    monkeypatch.setattr(
        "nfl_dfs.preflight.release_clock", lambda: expires - timedelta(minutes=1)
    )
    manifest_path, _ = _certified(
        tmp_path, classic_slate, classic_entries, expires_at=expires,
        monkeypatch=monkeypatch, now=expires - timedelta(minutes=1),
    )
    code = command_preflight(
        argparse.Namespace(
            manifest=str(manifest_path), salaries=str(SALARY_CSV),
            entries=str(ENTRIES_CSV), assignments=None,
        )
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["RELEASE_DECISION"] == "CERTIFIED_UPLOAD_PACKAGE"
    assert code == 0
