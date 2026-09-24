"""R28 on the model path (Session 09): each exit that used to stop, driven through `run-slate`.

`.claude/rules/operating-path.md` asks for a run-slate test per changed exit.
Each run here is Classic C1 on the replay fixture, pinned before its lock, and
each delivers the model's own file with the gap named and
`RELEASE_DECISION=DO_NOT_UPLOAD`: a selected person with no activity row, a
run with no activity file at all, and an unresolved role change the market
disagrees with (the P1 stop Ben absorbed on 2026-09-23).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nfl_dfs.dk import parse_entries, parse_salaries

from .test_classic_prior_review import AS_OF
from .test_classic_prior_review import _fixture as classic_fixture
from .test_prior_review_profile import _attachments, _cowork_args

C1_PRODUCER = "run-slate:prior_review:CLASSIC_C1"


def _run_slate(tmp_path, monkeypatch, *, run_id, mutate=None, **extra):
    from nfl_dfs import cli

    salary, entry, package, role, status, _ = classic_fixture(tmp_path / "fixture", entries=2)
    if mutate is not None:
        mutate(salary=salary, status=status)
    attachments = _attachments(tmp_path, salary, entry)
    monkeypatch.setattr(cli, "DEFAULT_RUNS_DIR", tmp_path / "runs")
    values = dict(
        label=run_id, run_id=run_id, prior_package_dir=str(package),
        official_status_csv=str(status), offensive_role_evidence_json=str(role),
        as_of=AS_OF.isoformat())
    values.update(extra)
    code = cli.command_cowork_run(_cowork_args(tmp_path, attachments, **values))
    root = tmp_path / "outputs" / run_id
    report = json.loads((root / "cowork_run.json").read_text(encoding="utf-8"))
    return code, report, salary


def _limitations(report) -> dict[str, list[dict]]:
    found: dict[str, list[dict]] = {}
    for item in report["release_truths"]["delivery_limitations"]:
        found.setdefault(item["code"], []).append(item)
    return found


def _delivered_rosters(report) -> list[tuple[str, ...]]:
    template = parse_entries(report["bulk_entry_csv"])
    return [tuple(entry.existing_cells) for entry in template.authorizations]


def _the_models_file_is_delivered(code, report):
    assert code == 0, report["blockers"]
    assert report["FILE_VALID"] is True
    assert report["DELIVERY_STATE"] == "DELIVERABLE"
    assert report["latest_deliverable"]["producer"] == C1_PRODUCER
    assert report["improvement"]["status"] == "DELIVERED"
    assert (report["MODEL_STATUS"], report["RELEASE_DECISION"]) == ("PRIOR_ONLY", "DO_NOT_UPLOAD")
    assert report["release_truths"]["RELEASE_DECISION"] == "DO_NOT_UPLOAD"
    assert "V" not in {item["class"] for item in report["release_truths"]["delivery_limitations"]}
    rosters = _delivered_rosters(report)
    assert rosters and all(all(rosters_cell for rosters_cell in roster) for roster in rosters)
    assert len(set(rosters)) == len(rosters)  # R29


@pytest.mark.parametrize("supplied", [True, False], ids=["rows-missing", "no-file"])
def test_a_selected_person_without_an_activity_row_ships_named(tmp_path, monkeypatch, supplied):
    """Until Session 09 this stopped at SELECTED_CURRENT_EVIDENCE_REQUIRED and the
    baseline stayed the deliverable. Now C1's file goes out with the gap named,
    exactly as Showdown's already did."""

    def keep_two_rows(*, salary, status):
        rows = status.read_text(encoding="utf-8").splitlines()
        status.write_text("\n".join(rows[:3]) + "\n", encoding="utf-8")

    extra = {} if supplied else {"official_status_csv": None}
    code, report, _salary = _run_slate(
        tmp_path, monkeypatch, run_id="activity", mutate=keep_two_rows if supplied else None, **extra)
    _the_models_file_is_delivered(code, report)
    found = _limitations(report)
    if supplied:
        [item] = found["OFFICIAL_STATUS_INCOMPLETE_FOR_SELECTED"]
        assert "OFFICIAL_STATUS_REQUIRED" not in found
        coverage = report["prior_review_reports"]["selection"]["official_status_coverage"]
        assert coverage["selected_without_row"] and all(
            person in item["detail"] for person in coverage["selected_without_row"])
    else:
        assert "OFFICIAL_STATUS_REQUIRED" in found
        assert "OFFICIAL_STATUS_INCOMPLETE_FOR_SELECTED" not in found
    for code_name in ("OFFICIAL_STATUS_INCOMPLETE_FOR_SELECTED", "OFFICIAL_STATUS_REQUIRED"):
        for item in found.get(code_name, ()):
            assert (item["class"], item["stops"]) == ("P", "CERTIFICATION")
    gate = report["prior_review_reports"]["selected_evidence_gate"]
    assert (gate["status"], gate["gaps"]) == ("PASS_WITH_NAMED_LIMITATIONS", [])
    assert report["EVIDENCE_STATE"] == "UNKNOWN"


def test_an_unresolved_role_change_leaves_the_pool_and_the_file_ships(tmp_path, monkeypatch):
    """The P1 stop, absorbed (R28, Ben 2026-09-23). The person the gate names is
    left out and named; he appears in no delivered roster."""

    from nfl_dfs import offensive_roles

    code, before, salary = _run_slate(tmp_path / "before", monkeypatch, run_id="before")
    _the_models_file_is_delivered(code, before)
    slate = parse_salaries(salary)
    by_id = {player.dk_id: player for player in slate.players}
    chosen = next(
        by_id[dk_id]
        for roster in _delivered_rosters(before)
        for dk_id in roster
        if by_id[dk_id].position in {"RB", "WR", "TE"}
    )
    code_text = (
        f"OFFENSIVE_UNRESOLVED_MATERIAL_ROLE_CHANGE:{chosen.underlying_id}:salary={chosen.salary}"
        ":prior_points=1.0:places=14:old_teams=SEA:the market prices this person far above a prior"
        " carried from his previous team, so he was left out of the selectable pool and is never"
        " selected on the old-team share."
    )
    monkeypatch.setattr(
        offensive_roles, "_material_role_changes",
        lambda report, divergence: [(chosen.underlying_id, code_text)])

    code, report, _salary = _run_slate(tmp_path / "after", monkeypatch, run_id="after")
    _the_models_file_is_delivered(code, report)
    [item] = _limitations(report)["OFFENSIVE_UNRESOLVED_MATERIAL_ROLE_CHANGE"]
    assert (item["class"], item["stops"]) == ("P", "CERTIFICATION")
    assert before["EVIDENCE_STATE"] == "PASS"  # the fixture's evidence is complete
    assert report["EVIDENCE_STATE"] == "UNKNOWN"  # an excluded role change is not
    assert chosen.underlying_id in item["detail"]
    assert all(chosen.dk_id not in roster for roster in _delivered_rosters(report))
    selector = report["prior_review_reports"]["selection"]["selection"]
    assert selector["offensive_roles"]["material_role_change_exclusions"] == [code_text]
    pool = report["prior_review_reports"]["selection"]["pool_coverage"]
    row = next(item for item in pool["people"] if item["person"] == chosen.underlying_id)
    assert row["reason"] == "OFFENSIVE_ROLE_GATE_EXCLUDED:OFFENSIVE_UNRESOLVED_MATERIAL_ROLE_CHANGE"
    assert not any(value.startswith("SELECTION_FAILED:") for value in report["blockers"])
