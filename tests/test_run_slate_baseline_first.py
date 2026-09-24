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
from .test_baseline import CLASSIC_SALARY, NOW, SHOWDOWN_SALARY, classic_template, showdown_template
from .test_classic_prior_review import AS_OF as CLASSIC_AS_OF
from .test_classic_prior_review import _fixture as classic_fixture
from .test_cowork import _attachment_pair
from .test_prior_review_profile import REPLAY_DEADLINE, _attachments, _cowork_args, _prepared_run

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


def test_an_unobserved_game_with_no_network_still_delivers_the_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_network: list[object]
) -> None:
    """Session 06's first run, moved by Session 09 (R28). It was
    `test_blocked_weather_with_no_network_still_delivers_the_baseline`: the
    outdoor game stopped the review at WEATHER with `WEATHER_CAPTURE_REQUIRED`.
    Weather no longer blocks, so the game is named unobserved and the review
    reaches the freeze, which fails here instead; the baseline stays the file."""

    from nfl_dfs import cli
    from nfl_dfs import prior_review as prior_review_module

    salary_path, entry_path, _package, project = _prepared_run(tmp_path, expires_at=NOW)
    attachments = _attachments(tmp_path, salary_path, entry_path)
    root = tmp_path / "outputs" / "prior-review-test"
    seen: dict[str, object] = {}

    def freeze(**kwargs):
        seen["freeze_weather_state"] = kwargs.get("weather_state")
        raise RuntimeError("PRIORS_UNAVAILABLE_OFFLINE")

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
    assert report["stage"] == "PRIOR_REVIEW_PRIORS_BLOCKED"
    assert any(value.startswith("PRIORS_FREEZE_FAILED:") for value in report["blockers"])
    weather = next(item for item in report["prior_review_stages"] if item["stage"] == "WEATHER")
    assert weather["status"] == "UNOBSERVED_GAMES_NAMED"
    [game] = weather["games"].values()
    assert game["limitations"][0].startswith("WEATHER_UNOBSERVED:roof=outdoors:")
    assert seen["freeze_weather_state"] is None  # nothing observed is ever passed on
    assert not any("WEATHER_CAPTURE_REQUIRED:" in value for value in report["blockers"])
    assert report["FILE_VALID"] is False and report["bulk_entry_csv"] is None
    assert report["MODEL_STATUS"] == "PRIOR_ONLY"
    assert seen["pointer_before_review"] == BASELINE  # published before priors and weather
    _assert_baseline_delivered(report, root, "prior-review-test")
    assert report["release_truths"]["FILE_VALID"] is False  # the review's own v1 truth
    assert report["improvement"]["status"] == "NOT_PRODUCED"
    assert report["improvement"]["stage"] == "PRIORS"
    assert "PRIORS_FREEZE_FAILED" in next(
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

        def probe(salaries, **_budgeted):  # Session 07 passes the probe its timeout
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
        delivery_deadline_utc=REPLAY_DEADLINE,  # a replay of a locked slate (Session 07)
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


def test_an_improvement_that_stops_revalidating_gives_the_pointer_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Written, then changed before the read-back: withheld, and the baseline restored."""

    from nfl_dfs import cli

    real = cli.replace_deliverable

    def replace_then_corrupt(root, item, *, now=None):
        written = real(root, item, now=now)
        if item.producer != BASELINE:
            Path(item.path).write_bytes(Path(item.path).read_bytes() + b"\r\n")
        return written

    monkeypatch.setattr(cli, "replace_deliverable", replace_then_corrupt)
    code, report, root = _showdown_run(tmp_path, monkeypatch)
    assert code == 2 and report["FILE_VALID"] is False and report["bulk_entry_csv"] is None
    latest = _assert_baseline_delivered(report, root, "prior-review-test")
    assert latest.record["supersedes"]["revalidation"] == "FAIL"
    assert latest.record["supersedes"]["producer"] == "run-slate:prior_review:SHOWDOWN"
    assert report["improvement"]["status"] == "WITHHELD"
    assert "DELIVERABLE_SHA256_MISMATCH" in report["improvement"]["reasons"]


def test_an_existing_c1_output_is_never_overwritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def patch(cli):
        real = cli.run_prior_review

        def review(**kwargs):
            outcome = real(**kwargs)
            stray = Path(kwargs["output_root"]) / "review" / "DK_REVIEW_ENTRY_C1_classic-s05.csv"
            stray.parent.mkdir(parents=True, exist_ok=True)
            stray.write_bytes(b"an earlier output\r\n")
            return outcome

        monkeypatch.setattr(cli, "run_prior_review", review)

    code, report, root = _classic_run(tmp_path, monkeypatch, policy=False, patch=patch)
    assert code == 2
    assert report["blockers"][0].startswith("CLASSIC_C1_EXPORT_OUTPUT_EXISTS:")
    assert (root / "review" / "DK_REVIEW_ENTRY_C1_classic-s05.csv").read_bytes() == b"an earlier output\r\n"
    _assert_baseline_delivered(report, root, "classic-s05")


def test_the_outer_handler_after_a_replacement_names_the_improvement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def crash(**kwargs):
        raise RuntimeError("workbook crashed after the replacement")

    code, report, root = _showdown_run(tmp_path, monkeypatch, workbook=crash)
    assert code == 2 and report["stage"] == "BUILD_OR_CERTIFY_FAILED"
    latest = delivery.read_latest(root, run_id="prior-review-test")
    assert latest.deliverable.producer == "run-slate:prior_review:SHOWDOWN"
    assert latest.record["supersedes"]["producer"] == BASELINE
    assert report["DELIVERY_STATE"] == "DELIVERABLE"
    assert report["improvement"]["status"] == "DELIVERED"
    assert "IMPROVEMENT_NOT_DELIVERED" not in _codes(report)
    assert not report["next"].startswith("The baseline ")


def test_the_pre_review_exit_names_a_baseline_that_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nfl_dfs import cli

    def broken(**kwargs):
        raise OSError("forced baseline failure")

    attachments = tmp_path / "attachments"
    attachments.mkdir()
    _attachment_pair(attachments)
    monkeypatch.setattr(cli, "DEFAULT_RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(cli, "run_baseline", broken)
    assert cli.command_cowork_run(argparse.Namespace(
        input_dir=str(attachments), request=None, salaries=None, entries=None,
        label="both-failed", run_id="both-failed", output_dir=str(tmp_path / "outputs"),
    )) == 2
    report = _report(tmp_path / "outputs" / "both-failed")
    assert report["DELIVERY_STATE"] == "NO_DELIVERABLE" and report["latest_deliverable"] is None
    assert report["baseline"]["problems"] == ["BASELINE_RUN_FAILED:OSError:forced baseline failure"]
    assert _codes(report)["BASELINE_RUN_FAILED"] == "V"
    assert report["release_truths"]["RELEASE_DECISION"] == "DO_NOT_UPLOAD"


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


def test_a_hand_run_baseline_takes_the_same_exclusions(tmp_path: Path, capsys) -> None:
    from nfl_dfs.cli import main

    template = classic_template(tmp_path, 5)
    slate = parse_salaries(CLASSIC_SALARY)
    top = max(slate.players, key=lambda player: player.salary)
    code = main(["baseline", "--salaries", str(CLASSIC_SALARY), "--entries", str(template),
                 "--out-dir", str(tmp_path / "runs"), "--run-id", "by-hand",
                 "--exclude", top.dk_id, "--unavailable-status", "Q"])
    summary = json.loads(capsys.readouterr().out)
    assert code == 0 and summary["DELIVERY_STATE"] == "DELIVERABLE"
    report = json.loads((tmp_path / "runs" / "by-hand" / "baseline_report.json").read_text(encoding="utf-8"))
    assert report["pool"]["operator_excluded_dk_ids"] == [top.dk_id]
    assert report["pool"]["extra_unavailable_statuses"] == ["Q"]
    rows = {player.dk_id for player in slate.players if player.underlying_id == top.underlying_id}
    assert not any(rows & set(line["roster"]) for line in report["lineups"])


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


# ------------------------------------------ R32: official inactives (Session 06b)

OBSERVED = "2026-09-23T11:00:00-04:00"
SOURCE = "https://www.nfl.com/injuries/league/2026/reg3"


def _status_csv(path: Path, rows: list[tuple[str, str, str, str]]) -> Path:
    """An official status file: (team, DK ID, status, source URL) per row."""

    lines = ["TEAM,PLAYER_OR_GSIS_ID,STATUS,SOURCE_URL,OBSERVED_AT"]
    lines += [f"{team},{dk_id},{status},{url},{OBSERVED}" for team, dk_id, status, url in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _rows_of(slate, person: str) -> set[str]:
    return {player.dk_id for player in slate.players if player.underlying_id == person}


def test_official_inactive_rows_leave_the_baseline_pool(tmp_path: Path) -> None:
    template = classic_template(tmp_path, 20)
    slate = parse_salaries(CLASSIC_SALARY)
    top = max(slate.players, key=lambda player: player.salary)
    other = next(p for p in sorted(slate.players, key=lambda p: -p.salary)
                 if p.underlying_id != top.underlying_id and (p.status_raw or "") == "")
    status = _status_csv(tmp_path / "status.csv", [
        (top.team, top.dk_id, "INACTIVE", SOURCE),
        (other.team, other.dk_id, "ACTIVE", SOURCE),
    ])
    outcome = run_baseline(salaries=CLASSIC_SALARY, entries=template, out_dir=tmp_path / "runs",
                           run_id="inactive", now=NOW, official_status_csv=status)
    assert outcome.truths.delivery_state.value == "DELIVERABLE"
    assert not any(_rows_of(slate, top.underlying_id) & set(r) for r in outcome.assignments.values())
    pool = outcome.report["pool"]
    assert pool["official_inactive_people"] == [top.underlying_id]
    assert pool["official_status_rows_not_applied"] == []
    assert "NO_OFFICIAL_INACTIVE_PERSON" in outcome.report["audit"]["checks_run"]
    bound = outcome.report["inputs"]["official_status"]
    assert bound["sha256"] == sha256_file(status) and Path(bound["snapshot"]).is_file()
    required = next(item for item in outcome.truths.delivery_limitations
                    if item.code == "OFFICIAL_STATUS_REQUIRED")
    assert required.gate_class.value == "P" and "1 person" in required.detail  # still not certified


def test_refused_rows_and_an_unreadable_file_are_named_never_a_stop(tmp_path: Path) -> None:
    template = classic_template(tmp_path, 5)
    slate = parse_salaries(CLASSIC_SALARY)
    top = max(slate.players, key=lambda player: player.salary)
    status = _status_csv(tmp_path / "status.csv", [
        (top.team, top.dk_id, "INACTIVE", SOURCE),
        (top.team, "99999999", "INACTIVE", SOURCE),                  # not a current-slate ID
        (top.team, top.dk_id.replace(top.dk_id[-1], "0"), "INACTIVE", "http://insecure.example/x"),
    ])
    mixed = run_baseline(salaries=CLASSIC_SALARY, entries=template, out_dir=tmp_path / "runs",
                         run_id="mixed", now=NOW, official_status_csv=status)
    assert mixed.truths.delivery_state.value == "DELIVERABLE"
    assert mixed.report["pool"]["official_inactive_people"] == [top.underlying_id]
    codes = {item.code: item for item in mixed.truths.delivery_limitations}
    assert codes["BASELINE_OFFICIAL_STATUS_ROWS_NOT_APPLIED"].gate_class.value == "P"
    assert "99999999" in codes["BASELINE_OFFICIAL_STATUS_ROWS_NOT_APPLIED"].detail

    broken = tmp_path / "broken.csv"
    broken.write_text("NAME,STATUS\nsomeone,INACTIVE\n", encoding="utf-8")
    unread = run_baseline(salaries=CLASSIC_SALARY, entries=template, out_dir=tmp_path / "runs",
                          run_id="unread", now=NOW, official_status_csv=broken)
    assert unread.truths.delivery_state.value == "DELIVERABLE"
    assert unread.report["pool"]["official_inactive_people"] == []
    codes = {item.code: item.gate_class.value for item in unread.truths.delivery_limitations}
    assert codes["BASELINE_OFFICIAL_STATUS_UNREADABLE"] == "P" and "V" not in codes.values()


def test_a_status_snapshot_that_changes_before_the_write_withholds_the_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nfl_dfs import baseline as baseline_module

    template = classic_template(tmp_path, 3)
    slate = parse_salaries(CLASSIC_SALARY)
    top = max(slate.players, key=lambda player: player.salary)
    status = _status_csv(tmp_path / "status.csv", [(top.team, top.dk_id, "INACTIVE", SOURCE)])
    digest = sha256_file(status)
    real = baseline_module.build_distinct_lineups

    def build_then_change(*args, **kwargs):
        built = real(*args, **kwargs)
        for snapshot in (tmp_path / "runs" / "changed" / "inputs").glob(f"{digest}*"):
            snapshot.write_bytes(snapshot.read_bytes() + b"\n")
        return built

    monkeypatch.setattr(baseline_module, "build_distinct_lineups", build_then_change)
    outcome = run_baseline(salaries=CLASSIC_SALARY, entries=template, out_dir=tmp_path / "runs",
                           run_id="changed", now=NOW, official_status_csv=status)
    assert outcome.output_path is None and outcome.truths.delivery_state.value == "NO_DELIVERABLE"
    assert "BASELINE_OFFICIAL_STATUS_CHANGED_DURING_RUN" in {
        item.code for item in outcome.truths.delivery_limitations}
    assert not list((tmp_path / "runs" / "changed").glob("DK_BASELINE_ENTRY_*"))


def test_a_hand_run_baseline_takes_the_official_status_file(tmp_path: Path, capsys) -> None:
    from nfl_dfs.cli import main

    template = classic_template(tmp_path, 3)
    slate = parse_salaries(CLASSIC_SALARY)
    top = max(slate.players, key=lambda player: player.salary)
    status = _status_csv(tmp_path / "status.csv", [(top.team, top.dk_id, "INACTIVE", SOURCE)])
    code = main(["baseline", "--salaries", str(CLASSIC_SALARY), "--entries", str(template),
                 "--out-dir", str(tmp_path / "runs"), "--run-id", "by-hand", "--official-status", str(status)])
    assert code == 0 and json.loads(capsys.readouterr().out)["DELIVERY_STATE"] == "DELIVERABLE"
    report = json.loads((tmp_path / "runs" / "by-hand" / "baseline_report.json").read_text(encoding="utf-8"))
    assert report["pool"]["official_inactive_people"] == [top.underlying_id]


def test_run_slate_delivers_a_baseline_without_the_runs_official_inactives(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The case R32 was ruled on: the review never finishes, the baseline ships."""

    from nfl_dfs import cli

    salary, entry, package, _role, _status, _ = classic_fixture(tmp_path / "fixture", entries=2)
    attachments = _attachments(tmp_path, salary, entry)
    slate = parse_salaries(salary)
    plain = run_baseline(salaries=salary, entries=entry, out_dir=tmp_path / "plain", run_id="plain",
                         now=CLASSIC_AS_OF)
    held = {dk_id for roster in plain.assignments.values() for dk_id in roster}
    target = max((p for p in slate.players if p.dk_id in held), key=lambda p: p.salary)
    status = _status_csv(tmp_path / "evidence" / "status.csv", [(target.team, target.dk_id, "INACTIVE", SOURCE)]) \
        if (tmp_path / "evidence").mkdir() is None else None

    def crash(**kwargs):
        raise RuntimeError("the review never finishes")

    monkeypatch.setattr(cli, "DEFAULT_RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(cli, "run_prior_review", crash)
    cli.command_cowork_run(_cowork_args(
        tmp_path, attachments, label="inactive", run_id="inactive", prior_package_dir=str(package),
        official_status_csv=str(status), as_of=CLASSIC_AS_OF.isoformat()))

    root = tmp_path / "outputs" / "inactive"
    report = _report(root)
    latest = _assert_baseline_delivered(report, root, "inactive")
    written = parse_entries(latest.deliverable.path)
    rows = _rows_of(slate, target.underlying_id)
    assert all(not rows & set(item.existing_cells) for item in written.authorizations)  # the plain one held him
    baseline_report = json.loads(Path(report["baseline"]["report"]).read_text(encoding="utf-8"))
    assert baseline_report["pool"]["official_inactive_people"] == [target.underlying_id]


def test_conflicting_rows_take_the_person_out_and_are_not_counted_as_refused(tmp_path: Path) -> None:
    template = classic_template(tmp_path, 5)
    slate = parse_salaries(CLASSIC_SALARY)
    top = max(slate.players, key=lambda player: player.salary)
    status = _status_csv(tmp_path / "status.csv", [
        (top.team, top.dk_id, "ACTIVE", SOURCE),
        (top.team, top.dk_id, "INACTIVE", SOURCE),  # the parser sets this aside as a conflict
    ])
    outcome = run_baseline(salaries=CLASSIC_SALARY, entries=template, out_dir=tmp_path / "runs",
                           run_id="conflict", now=NOW, official_status_csv=status)
    pool = outcome.report["pool"]
    assert pool["official_inactive_people"] == [top.underlying_id]
    assert len(pool["official_status_conflicts"]) == 1 and pool["official_status_rows_not_applied"] == []
    assert not any(_rows_of(slate, top.underlying_id) & set(r) for r in outcome.assignments.values())
    assert "BASELINE_OFFICIAL_STATUS_ROWS_NOT_APPLIED" not in {
        item.code for item in outcome.truths.delivery_limitations}

    # Showdown: a captain row ACTIVE and a flex row INACTIVE take the person out of both roles.
    sd_slate = parse_salaries(SHOWDOWN_SALARY)
    person = max((p for p in sd_slate.players if p.role == "FLEX"), key=lambda p: p.salary)
    captain = next(p for p in sd_slate.players if p.underlying_id == person.underlying_id and p.role != "FLEX")
    sd_status = _status_csv(tmp_path / "sd_status.csv", [
        (captain.team, captain.dk_id, "ACTIVE", SOURCE),
        (person.team, person.dk_id, "INACTIVE", SOURCE),
    ])
    sd = run_baseline(salaries=SHOWDOWN_SALARY, entries=showdown_template(tmp_path, 5), out_dir=tmp_path / "runs",
                      run_id="roles", now=NOW, official_status_csv=sd_status)
    assert sd.report["pool"]["official_inactive_people"] == [person.underlying_id]
    assert sd.report["pool"]["official_status_rows_not_applied"] == []
    assert not any(_rows_of(sd_slate, person.underlying_id) & set(r) for r in sd.assignments.values())


def test_a_file_the_csv_reader_cannot_read_is_named_not_a_stop(tmp_path: Path) -> None:
    status = tmp_path / "status.csv"
    status.write_text("TEAM,PLAYER_OR_GSIS_ID,STATUS,SOURCE_URL,OBSERVED_AT\n\"" + "x" * 140_000 + "\n",
                      encoding="utf-8")  # a stray quote swallows the file into one oversized field
    outcome = run_baseline(salaries=CLASSIC_SALARY, entries=classic_template(tmp_path, 3),
                           out_dir=tmp_path / "runs", run_id="huge", now=NOW, official_status_csv=status)
    assert outcome.truths.delivery_state.value == "DELIVERABLE"
    codes = {item.code: item for item in outcome.truths.delivery_limitations}
    assert codes["BASELINE_OFFICIAL_STATUS_UNREADABLE"].gate_class.value == "P"
    assert "Error" in codes["BASELINE_OFFICIAL_STATUS_UNREADABLE"].detail


def test_the_audit_refuses_a_roster_holding_an_official_inactive(tmp_path: Path) -> None:
    from nfl_dfs.baseline import audit_baseline_bytes

    template = classic_template(tmp_path, 3)
    slate = parse_salaries(CLASSIC_SALARY)
    plain = run_baseline(salaries=CLASSIC_SALARY, entries=template, out_dir=tmp_path / "runs",
                         run_id="plain", now=NOW)
    first = plain.assignments[next(iter(plain.assignments))][0]
    player = next(p for p in slate.players if p.dk_id == first)
    status = _status_csv(tmp_path / "status.csv", [(player.team, player.dk_id, "INACTIVE", SOURCE)])
    kwargs = dict(salary_path=CLASSIC_SALARY, entries_path=template, assignments=plain.assignments,
                  unfilled=())
    raw = plain.output_path.read_bytes()
    assert audit_baseline_bytes(raw, **kwargs) == []
    problems = audit_baseline_bytes(raw, **kwargs, official_status_csv=status)
    holders = [eid for eid, roster in plain.assignments.items()
               if _rows_of(slate, player.underlying_id) & set(roster)]
    assert problems == [f"BASELINE_AUDIT_OFFICIAL_INACTIVE_PERSON:{eid}" for eid in holders]


def test_the_c1_export_audit_reads_the_runs_status_snapshot_and_its_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[object] = []

    def patch(cli):
        real = cli.audit_baseline_bytes

        def recording(raw, **kwargs):
            seen.append(kwargs.get("official_status_csv"))
            return real(raw, **kwargs)

        monkeypatch.setattr(cli, "audit_baseline_bytes", recording)

    code, report, root = _classic_run(tmp_path / "read", monkeypatch, policy=False, patch=patch)
    assert code == 0 and report["latest_deliverable"]["producer"] == "run-slate:prior_review:CLASSIC_C1"
    snapshot = report["prior_review_artifacts"]["official_status_csv"]
    assert seen == [snapshot] and Path(snapshot).parent.name == "inputs"

    def change(cli):
        real = cli.run_prior_review

        def review(**kwargs):
            outcome = real(**kwargs)
            path = Path(kwargs["official_status_csv"])
            path.write_bytes(path.read_bytes() + b"\n")  # after C1 read it
            return outcome

        monkeypatch.setattr(cli, "run_prior_review", review)

    code, report, root = _classic_run(tmp_path / "changed", monkeypatch, policy=False, patch=change)
    assert code == 2
    assert report["blockers"][0].startswith("CLASSIC_C1_EXPORT_OFFICIAL_STATUS_CHANGED:")
    _assert_baseline_delivered(report, root, "classic-s05")
