"""Session 06: `run-slate` builds and publishes the baseline first (R28, R29).

The card's acceptance is three runs, each producing a `DELIVERABLE` baseline,
with `RELEASE_DECISION=DO_NOT_UPLOAD` wherever evidence is missing:

- blocked weather with no network: the run's own review stops at `WEATHER`,
  and the baseline, built before it with every socket refused, is delivered;
- a forced improvement crash: the outer handler names the baseline;
- an improvement success, which replaces the pointer through `delivery.replace`.

Beside them: the baseline is on the pointer before the session probe, policy
validation or the review starts; a withheld improvement, the pre-review blocked
exit and a refused C1 export all leave it named; C1 (rung 4) ends with a CSV of
its own lineups; the operator's exclusions bind the baseline; and a baseline
that cannot be built never stops the run.
"""

from __future__ import annotations

import argparse
import json
import socket
from pathlib import Path

import pytest
from openpyxl import load_workbook

from nfl_dfs import delivery
from nfl_dfs.baseline import run_baseline
from nfl_dfs.dk import parse_entries, parse_entry_bytes, parse_salaries
from nfl_dfs.hashing import sha256_file
from nfl_dfs.readable_review import ReadableReviewError

from .test_artifact_preservation import _classic_run, _showdown_run
from .test_baseline import CLASSIC_SALARY, NOW, classic_template
from .test_classic_prior_review import AS_OF as CLASSIC_AS_OF
from .test_classic_prior_review import _fixture as classic_fixture
from .test_cowork import _attachment_pair
from .test_prior_review_profile import _attachments, _cowork_args, _prepared_run

BASELINE = "run-slate:baseline"
EVIDENCE_GAPS = {"OFFICIAL_STATUS_REQUIRED", "OFFENSIVE_CURRENT_ROLE_UNRESOLVED",
                 "WEATHER_CAPTURE_REQUIRED", "MODEL_NOT_PROSPECTIVELY_VALIDATED"}


# ---------------------------------------------------------------- helpers


def _report(root: Path) -> dict:
    return json.loads((root / "cowork_run.json").read_text(encoding="utf-8"))


def _codes(report: dict) -> dict[str, str]:
    return {item["code"]: item["class"] for item in report["release_truths"]["delivery_limitations"]}


def _upload_sheet_names(report: dict, path: str | Path) -> bool:
    cell = load_workbook(report["review_workbook"], data_only=False)["Upload"]["B10"].value
    return str(Path(path).resolve()) in str(cell)


def _assert_baseline_delivered(report: dict, root: Path, run_id: str):
    """The pointer names the baseline, it revalidates now, and the result says so."""

    latest = delivery.read_latest(root, run_id=run_id)  # revalidates the bytes on disk
    assert latest is not None and latest.deliverable.producer == BASELINE
    assert latest.deliverable.path.parent == root.resolve() / "baseline"
    assert report["DELIVERY_STATE"] == "DELIVERABLE"
    assert report["latest_deliverable"]["producer"] == BASELINE
    assert report["latest_deliverable"]["path"] == str(latest.deliverable.path)
    assert sha256_file(latest.deliverable.path) == report["latest_deliverable"]["sha256"]
    assert report["baseline"]["published"] is True
    assert report["baseline"]["DELIVERY_STATE"] == "DELIVERABLE"
    assert report["baseline"]["path"] == str(latest.deliverable.path)
    truths = report["release_truths"]
    assert truths["schema_version"] == "nfl_release_truths_v2"
    assert report["RELEASE_DECISION"] == truths["RELEASE_DECISION"] == "DO_NOT_UPLOAD"
    assert truths["DELIVERY_STATE"] == "DELIVERABLE" and truths["delivered_file_valid"] is True
    assert truths["unfilled_entry_ids"] == []
    codes = _codes(report)
    assert codes["IMPROVEMENT_NOT_DELIVERED"] == "P"
    assert "V" not in codes.values()
    assert EVIDENCE_GAPS <= set(codes)  # every missing piece of evidence is named
    assert report["next"].startswith(f"The baseline {latest.deliverable.path} is this run's deliverable")
    assert not list(root.rglob("DK_UPLOAD_*.csv"))
    return latest


@pytest.fixture
def no_network(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    """Every outbound connection refused, and recorded, for the whole run."""

    attempts: list[object] = []

    def refuse(*args, **kwargs):
        attempts.append(args[1:] or args)
        raise OSError("the test refuses every network connection")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    return attempts


def _outdoor_proposer(slate):
    """A prior proposal that resolves every identity, for a game played outdoors."""

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
                "provider_player_id": f"00-{int(player.dk_id) % 10_000_000:07d}",
                "provider_name": player.name,
                "provider_pfr_id": "",
                "provider_team": player.team,
                "provider_status": "ACT",
                "match_method": "NORMALIZED_NAME_TEAM_POSITION",  # resolved by the proposal
                "candidates": [],
            }
            for player in slate.players
            if player.role == "FLEX"
        ]
        (package_root / "identity_proposals.json").write_text(
            json.dumps({"proposals": proposals}), encoding="utf-8")
        return {
            "package_dir": str(package_root),
            "identity_proposals": str(package_root / "identity_proposals.json"),
            "source_manifest": str(package_root / "source_manifest.json"),
            "hashes": {},
            "market": {"roof": "outdoors"},
        }

    return propose


# ------------------------------------------------ the card's three runs


def test_blocked_weather_with_no_network_still_delivers_the_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_network: list[object]
) -> None:
    from nfl_dfs import cli
    from nfl_dfs import prior_review as prior_review_module

    salary_path, entry_path, _package, project = _prepared_run(tmp_path, expires_at=NOW)
    attachments = _attachments(tmp_path, salary_path, entry_path)
    root = tmp_path / "outputs" / "prior-review-test"
    seen: dict[str, object] = {}

    def freeze(**kwargs):  # pragma: no cover - reaching this is the failure
        raise AssertionError("freeze must not run while the weather gate is open")

    real = prior_review_module.run_prior_review

    def review(**kwargs):
        seen["pointer_before_review"] = delivery.read_latest(root).deliverable.producer
        return real(**kwargs, propose=_outdoor_proposer(parse_salaries(salary_path)),
                    freeze=freeze, project=project)

    monkeypatch.setattr(cli, "DEFAULT_RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(cli, "run_prior_review", review)
    code = cli.command_cowork_run(_cowork_args(tmp_path, attachments, build_priors=True))

    report = _report(root)
    assert code == 2
    assert report["stage"] == "PRIOR_REVIEW_WEATHER_BLOCKED"
    assert any("WEATHER_CAPTURE_REQUIRED:" in value for value in report["blockers"])
    assert report["FILE_VALID"] is False and report["bulk_entry_csv"] is None
    assert report["MODEL_STATUS"] == "PRIOR_ONLY"
    assert seen["pointer_before_review"] == BASELINE  # published before priors and weather
    _assert_baseline_delivered(report, root, "prior-review-test")
    assert report["release_truths"]["FILE_VALID"] is False  # the review's own v1 truth
    assert report["improvement"]["status"] == "NOT_PRODUCED"
    assert report["improvement"]["stage"] == "WEATHER"
    assert "WEATHER_CAPTURE_REQUIRED" in next(
        item["detail"] for item in report["release_truths"]["delivery_limitations"]
        if item["code"] == "IMPROVEMENT_NOT_DELIVERED")
    assert _upload_sheet_names(report, report["latest_deliverable"]["path"])
    assert no_network == []  # nothing even tried


def test_a_forced_improvement_crash_leaves_the_baseline_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nfl_dfs import cli

    salary, entry, package, _role, _status, _ = classic_fixture(tmp_path / "fixture", entries=2)
    attachments = _attachments(tmp_path, salary, entry)

    def crash(**kwargs):
        raise RuntimeError("forced improvement crash")

    monkeypatch.setattr(cli, "DEFAULT_RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(cli, "run_prior_review", crash)
    code = cli.command_cowork_run(_cowork_args(
        tmp_path, attachments, label="crash", run_id="crash", prior_package_dir=str(package),
        as_of=CLASSIC_AS_OF.isoformat()))

    root = tmp_path / "outputs" / "crash"
    report = _report(root)
    assert code == 2
    assert report["stage"] == "BUILD_OR_CERTIFY_FAILED"
    assert report["message"] == "forced improvement crash"
    assert report["FILE_VALID"] is False
    latest = _assert_baseline_delivered(report, root, "crash")
    assert latest.record["published_at"] == CLASSIC_AS_OF.isoformat()  # the pinned clock
    assert report["release_truths"]["FILE_VALID"] is False
    assert report["improvement"] == {
        "status": "NOT_PRODUCED", "stage": "BUILD_OR_CERTIFY_FAILED",
        "reasons": ["RuntimeError:forced improvement crash"],
    }
    diagnostic = json.loads((root / "cowork_diagnostic.json").read_text(encoding="utf-8"))
    assert diagnostic["latest_deliverable"]["path"] == str(latest.deliverable.path)
    assert diagnostic["baseline"]["published"] is True


def test_an_improvement_success_replaces_the_pointer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    code, report, root = _showdown_run(tmp_path, monkeypatch)
    assert code == 0 and report["stage"] == "PRIOR_ONLY_REVIEW_EXPORT"
    assert report["baseline"]["published"] is True
    assert report["baseline"]["DELIVERY_STATE"] == "DELIVERABLE"
    latest = delivery.read_latest(root, run_id="prior-review-test")
    assert latest.deliverable.producer == "run-slate:prior_review:SHOWDOWN"
    assert str(latest.deliverable.path) == report["bulk_entry_csv"]
    supersedes = latest.record["supersedes"]
    assert supersedes["producer"] == BASELINE and supersedes["revalidation"] == "PASS"
    assert supersedes["file_sha256"] == report["baseline"]["sha256"]
    # The baseline is superseded, never deleted or rewritten.
    assert sha256_file(report["baseline"]["path"]) == report["baseline"]["sha256"]
    assert report["improvement"]["status"] == "DELIVERED"
    assert report["improvement"]["replaced"]["producer"] == BASELINE
    assert report["DELIVERY_STATE"] == "DELIVERABLE"
    assert report["RELEASE_DECISION"] == report["release_truths"]["RELEASE_DECISION"] == "DO_NOT_UPLOAD"
    assert report["release_truths"]["FILE_VALID"] is True
    assert "IMPROVEMENT_NOT_DELIVERED" not in _codes(report)
    assert report["latest_deliverable"]["producer"] == "run-slate:prior_review:SHOWDOWN"
    assert _upload_sheet_names(report, report["bulk_entry_csv"])
    assert not report["next"].startswith("The baseline ")


# -------------------------------------------------- ordering and Classic


def test_the_baseline_is_published_before_the_probe_the_policy_and_the_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, object] = {}

    def patch(cli):
        root = tmp_path / "outputs" / "classic-s05"

        def producer() -> str | None:
            latest = delivery.read_latest(root)
            return latest.deliverable.producer if latest is not None else None

        def probe(salaries):
            seen["probe"] = producer()
            return None

        real_validate = cli.validate_classic_portfolio_policy_file

        def validate(*args, **kwargs):
            seen["policy"] = producer()
            return real_validate(*args, **kwargs)

        real_review = cli.run_prior_review

        def review(**kwargs):
            seen["review"] = producer()
            return real_review(**kwargs)

        monkeypatch.setattr(cli, "_session_probe", probe)
        monkeypatch.setattr(cli, "validate_classic_portfolio_policy_file", validate)
        monkeypatch.setattr(cli, "run_prior_review", review)

    code, report, root = _classic_run(tmp_path, monkeypatch, patch=patch)
    assert seen == {"probe": BASELINE, "policy": BASELINE, "review": BASELINE}
    # C3 then replaces it through `delivery.replace`.
    assert code == 0 and report["stage"] == "PRIOR_ONLY_CLASSIC_C3_REVIEW_EXPORT"
    latest = delivery.read_latest(root, run_id="classic-s05")
    assert latest.deliverable.producer == "run-slate:prior_review:CLASSIC"
    assert latest.record["supersedes"]["producer"] == BASELINE
    assert report["improvement"]["status"] == "DELIVERED"


def test_c1_rung_4_ends_with_its_own_csv_through_the_baseline_writer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    code, report, root = _classic_run(tmp_path, monkeypatch, policy=False)
    assert code == 0 and report["stage"] == "PRIOR_ONLY_CLASSIC_REVIEW_ARTIFACTS"
    csv_path = Path(report["bulk_entry_csv"])
    assert csv_path == root.resolve() / "review" / "DK_REVIEW_ENTRY_C1_classic-s05.csv"
    assert report["export"]["c1_export"]["status"] == "PASS"
    latest = delivery.read_latest(root, run_id="classic-s05")
    assert latest.deliverable.producer == "run-slate:prior_review:CLASSIC_C1"
    assert latest.deliverable.path == csv_path
    assert latest.record["supersedes"]["producer"] == BASELINE
    assert report["DELIVERY_STATE"] == "DELIVERABLE" and report["FILE_VALID"] is True
    assert report["RELEASE_DECISION"] == "DO_NOT_UPLOAD"
    assert "PROFILE_WRITES_NO_ENTRY_FILE" not in _codes(report)
    # The CSV is the template with C1's own assignment written in, row for row.
    reparsed = parse_entry_bytes(csv_path.read_bytes(), source_name=csv_path.name)
    assigned = {
        line.split(",")[0]: tuple(line.split(",")[1:])
        for line in Path(report["prior_review_artifacts"]["assignments"]).read_text(
            encoding="utf-8").splitlines()[1:]
    }
    assert {entry.entry_id: entry.existing_cells for entry in reparsed.authorizations} == assigned
    assert not list(root.rglob("*.tmp"))


def test_the_same_bytes_give_the_same_baseline_and_c1_csv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = _classic_run(tmp_path / "a", monkeypatch, policy=False)[1]
    second = _classic_run(tmp_path / "b", monkeypatch, policy=False)[1]
    for report in (first, second):
        assert report["DELIVERY_STATE"] == "DELIVERABLE"
    assert first["baseline"]["sha256"] == second["baseline"]["sha256"]
    assert first["bulk_entry_sha256"] == second["bulk_entry_sha256"]
    assert Path(first["bulk_entry_csv"]).read_bytes() == Path(second["bulk_entry_csv"]).read_bytes()


def test_a_changed_c1_assignment_withholds_the_export(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def patch(cli):
        real = cli.run_prior_review

        def review(**kwargs):
            outcome = real(**kwargs)
            path = Path(outcome.artifacts["assignments"])
            path.write_bytes(path.read_bytes() + b"\n")  # one byte after C1 hashed it
            return outcome

        monkeypatch.setattr(cli, "run_prior_review", review)

    code, report, root = _classic_run(tmp_path, monkeypatch, policy=False, patch=patch)
    assert code == 2
    assert report["blockers"][0].startswith("CLASSIC_C1_EXPORT_ASSIGNMENT_SHA256_MISMATCH:")
    assert report["bulk_entry_csv"] is None
    _assert_baseline_delivered(report, root, "classic-s05")
    assert not list(root.rglob("DK_REVIEW_ENTRY_C1_*"))


def test_a_refused_c1_export_falls_back_to_the_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def patch(cli):
        monkeypatch.setattr(cli, "audit_baseline_bytes", lambda raw, **kwargs: ["BYTE_AUDIT:forced"])

    code, report, root = _classic_run(tmp_path, monkeypatch, policy=False, patch=patch)
    assert code == 2
    assert report["blockers"][0] == "CLASSIC_C1_EXPORT_AUDIT_FAILED:BYTE_AUDIT:forced"
    assert report["bulk_entry_csv"] is None and report["FILE_VALID"] is True  # the C1 JSON stands
    _assert_baseline_delivered(report, root, "classic-s05")
    assert report["improvement"]["status"] == "NOT_PRODUCED"
    assert report["improvement"]["reasons"] == ["CLASSIC_C1_EXPORT_AUDIT_FAILED:BYTE_AUDIT:forced"]
    assert not list(root.rglob("DK_REVIEW_ENTRY_C1_*"))  # nothing unaudited is kept


# ------------------------------------------------- every other exit


def test_a_withheld_improvement_leaves_the_baseline_delivered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def failing(**kwargs):
        raise ReadableReviewError("READABLE_REVIEW_SELECTION_SALARY_MISMATCH:test")

    code, report, root = _showdown_run(tmp_path, monkeypatch, failing=failing)
    assert code == 2
    assert report["FILE_VALID"] is False and report["bulk_entry_csv"] is None
    _assert_baseline_delivered(report, root, "prior-review-test")
    assert report["improvement"]["status"] == "WITHHELD"
    assert "READABLE_REVIEW_SELECTION_SALARY_MISMATCH" in report["improvement"]["reasons"]
    assert _upload_sheet_names(report, report["latest_deliverable"]["path"])


def test_the_pre_review_blocked_exit_reports_the_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nfl_dfs import cli

    attachments = tmp_path / "attachments"
    attachments.mkdir()
    _attachment_pair(attachments)
    monkeypatch.setattr(cli, "DEFAULT_RUNS_DIR", tmp_path / "runs")
    args = argparse.Namespace(
        input_dir=str(attachments), request=None, salaries=None, entries=None,
        label="blocked", run_id="blocked", output_dir=str(tmp_path / "outputs"),
    )
    assert cli.command_cowork_run(args) == 2

    root = tmp_path / "outputs" / "blocked"
    report = _report(root)
    assert report["stage"] == "RECONCILED"
    assert report["MODEL_STATUS"] == report["release_truths"]["MODEL_STATUS"] == "UNVALIDATED"
    _assert_baseline_delivered(report, root, "blocked")
    assert report["improvement"]["status"] == "NOT_PRODUCED"
    assert any(value.startswith("CONTEST_PAYOUT_REQUIRED:") for value in report["improvement"]["reasons"])
    assert _upload_sheet_names(report, report["latest_deliverable"]["path"])


def test_a_baseline_that_cannot_be_built_never_stops_the_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The review then publishes the run's first pointer itself."""

    from nfl_dfs import cli

    def broken(**kwargs):
        raise OSError("forced baseline failure")

    monkeypatch.setattr(cli, "run_baseline", broken)
    code, report, root = _showdown_run(tmp_path, monkeypatch)
    assert code == 0
    assert report["baseline"]["published"] is False and report["baseline"]["path"] is None
    assert report["baseline"]["problems"] == ["BASELINE_RUN_FAILED:OSError:forced baseline failure"]
    latest = delivery.read_latest(root, run_id="prior-review-test")
    assert latest.deliverable.producer == "run-slate:prior_review:SHOWDOWN"
    assert latest.record["supersedes"] is None  # published, not a replacement
    assert report["improvement"]["status"] == "DELIVERED" and report["improvement"]["replaced"] is None
    assert report["DELIVERY_STATE"] == "DELIVERABLE"


# ------------------------------------------------- exclusions


def test_the_operators_exclusions_bind_the_baseline(tmp_path: Path) -> None:
    template = classic_template(tmp_path, 20)
    slate = parse_salaries(CLASSIC_SALARY)
    top = max(slate.players, key=lambda player: player.salary)
    free = run_baseline(salaries=CLASSIC_SALARY, entries=template, out_dir=tmp_path / "runs",
                        run_id="free", now=NOW)
    assert any(top.dk_id in roster for roster in free.assignments.values())

    faded = run_baseline(salaries=CLASSIC_SALARY, entries=template, out_dir=tmp_path / "runs",
                         run_id="faded", now=NOW, operator_excluded_dk_ids=[top.dk_id])
    assert faded.truths.delivery_state.value == "DELIVERABLE"
    rows = {player.dk_id for player in slate.players if player.underlying_id == top.underlying_id}
    assert not any(rows & set(roster) for roster in faded.assignments.values())
    assert faded.report["pool"]["operator_excluded_people"] == [top.underlying_id]
    assert "NO_OPERATOR_EXCLUDED_PERSON" in faded.report["audit"]["checks_run"]

    status = next(p.status_raw for p in slate.players if (p.status_raw or "").strip() not in ("", "OUT", "IR", "D"))
    by_status = run_baseline(salaries=CLASSIC_SALARY, entries=template, out_dir=tmp_path / "runs",
                             run_id="by-status", now=NOW, extra_unavailable_statuses=[status.lower()])
    flagged = {p.dk_id for p in slate.players if (p.status_raw or "").strip().upper() == status.upper()}
    assert flagged and not any(flagged & set(roster) for roster in by_status.assignments.values())

    unknown = run_baseline(salaries=CLASSIC_SALARY, entries=template, out_dir=tmp_path / "runs",
                           run_id="unknown", now=NOW, operator_excluded_dk_ids=["99999999"])
    assert unknown.truths.delivery_state.value == "NO_DELIVERABLE" and unknown.output_path is None
    assert "OPERATOR_EXCLUSION_NOT_IN_POOL" in {item.code for item in unknown.truths.delivery_limitations}


def test_run_slate_passes_the_request_exclusions_to_the_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nfl_dfs import cli

    salary, entry, package, _role, _status, _ = classic_fixture(tmp_path / "fixture", entries=2)
    attachments = _attachments(tmp_path, salary, entry)
    slate = parse_salaries(salary)
    top = max(slate.players, key=lambda player: player.salary)

    def crash(**kwargs):
        raise RuntimeError("the review is not under test")

    monkeypatch.setattr(cli, "DEFAULT_RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(cli, "run_prior_review", crash)
    cli.command_cowork_run(_cowork_args(
        tmp_path, attachments, label="faded", run_id="faded", prior_package_dir=str(package),
        as_of=CLASSIC_AS_OF.isoformat(), exclude=[top.dk_id]))

    root = tmp_path / "outputs" / "faded"
    report = _report(root)
    latest = _assert_baseline_delivered(report, root, "faded")
    rows = {player.dk_id for player in slate.players if player.underlying_id == top.underlying_id}
    written = parse_entries(latest.deliverable.path)
    assert all(not rows & set(item.existing_cells) for item in written.authorizations)
    baseline_report = json.loads(Path(report["baseline"]["report"]).read_text(encoding="utf-8"))
    assert baseline_report["pool"]["operator_excluded_dk_ids"] == [top.dk_id]
