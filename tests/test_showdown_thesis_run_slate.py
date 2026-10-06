"""Session 23c: a portfolio of theses through `run-slate`, with the contest step moving lineups between Entry IDs.

The selector names the thesis each lineup fills; the contest step then reassigns lineups to Entry IDs. The audit and
the readable review must read each Entry ID's thesis through that final assignment, the claim must follow its
lineup, and every release truth must stay `PRIOR_ONLY / DO_NOT_UPLOAD`. A thesis is a choice, not a forecast.
"""

from __future__ import annotations

from pathlib import Path

from nfl_dfs.portfolio_policy import POLICY_SCHEMA_VERSION_V4
from nfl_dfs.lineups import roster_canonical_key

from .test_contest_assignment_run_slate import (
    INTERLEAVED_CONTESTS,
    SIX,
    _assert_truths_unchanged,
    _assignment_rosters,
    _run,
)
from .test_entry_groups import _cells, _readable
from .test_showdown_theses import _people, _thesis


def _portfolio_controls(slate):
    theses = [
        _thesis(slate, ["Starter QB", "Alpha WR"], name="NE_WIN_BIG", teams=["NE"]),
        _thesis(slate, ["NE Kicker", "Patriots"], name="NE_WIN_CLOSE_LOW", teams=["NE"]),
        _thesis(slate, ["Sea QB", "Sea Alpha WR"], name="SEA_WIN_BIG", teams=["SEA"]),
    ]
    assert _people(slate)  # the names above resolve to exact identities on this slate
    return {"max_captain_exposure": {"default_fraction": 0.5, "overrides": []},
            "max_pairwise_person_overlap": 4, "structural_bounds": {}, "theses": theses}


def test_each_entry_id_names_the_thesis_its_lineup_fills_after_the_contest_step_moves_it(tmp_path, monkeypatch):
    code, report, entries, slate = _run(
        tmp_path, monkeypatch, run_id="thesis-run", contests=INTERLEAVED_CONTESTS,
        policy_controls=_portfolio_controls, policy_schema=POLICY_SCHEMA_VERSION_V4)
    assert code == 0, report["blockers"]
    _assert_truths_unchanged(report)
    reports = report["prior_review_reports"]
    assert reports["contest_assignment"]["moved_rows"] > 0  # the lineups really did change Entry IDs

    # The selector's claim, by lineup, read from its own report.
    selection = reports["selection"]
    claim = {tuple(row["roster"]): row["thesis"] for row in selection["lineups"]}
    assert len(claim) == 6 and set(claim.values()) == {"NE_WIN_BIG", "NE_WIN_CLOSE_LOW", "SEA_WIN_BIG"}
    block = selection["selection"]["portfolio_policy"]["theses"]  # the record wraps the selector's own report
    assert block["build_version"] == "showdown_thesis_portfolio_sd3_v1"
    assert [(item["name"], item["rows"]) for item in block["theses"]] == [
        ("NE_WIN_BIG", 2), ("NE_WIN_CLOSE_LOW", 2), ("SEA_WIN_BIG", 2)]

    # The delivered file's rosters, entry by entry, and the thesis each carries through the move.
    delivered = _assignment_rosters(report)
    assert {entry: tuple(roster) for entry, roster in _cells(Path(report["latest_deliverable"]["path"])).items()
            if entry in SIX} == delivered
    expected = {entry: claim[roster] for entry, roster in delivered.items()}
    assert block["entries"] == expected  # relabelled from the final assignment, not left in the solver's order
    assert block["by_lineup"] == {roster_canonical_key(slate, roster): thesis for roster, thesis in claim.items()}

    # The independent audit read the same thing from the exact final bytes, and each lineup follows its thesis.
    audit = reports["portfolio_policy_audit"]
    assert audit["status"] == "PASS", audit["problems"]
    entries_block = audit["theses"]["entries"]
    assert {entry: item["thesis"] for entry, item in entries_block.items()} == expected
    assert all(item["follows"] and item["broken_rules"] == [] for item in entries_block.values())
    assert audit["theses"]["measures"]["by_thesis"]["NE_WIN_BIG"]["rows"] == 2

    # The readable review accepts the v4 policy and reconciles; its own thesis section is Session 23f's.
    readable = _readable(report)
    assert readable["reconciliation"]["status"] == "PASS"
    assert "READABLE_REVIEW_FAILED" not in " ".join(report["blockers"])


def test_a_thesis_no_lineup_can_follow_is_dropped_by_name_and_the_others_deliver(tmp_path, monkeypatch):
    # A thesis whose six people must all be Seattle's cannot make a legal lineup (DraftKings needs both teams), so the
    # probe proves it short before any bank. The ladder drops exactly that thesis, names where its rows went, rebuilds
    # the same policy with the other two byte for byte, and the run delivers: nothing was bent.
    def controls(slate):
        built = _portfolio_controls(slate)
        built["theses"] = [
            built["theses"][0],
            _thesis(slate, ["Sea Kicker"], name="SEA_ALL_IN", teams=["SEA"],
                    team_bounds=[{"team": "SEA", "minimum": 6, "maximum": 6}]),
            built["theses"][2],
        ]
        return built

    code, report, _entries, _slate = _run(
        tmp_path, monkeypatch, run_id="thesis-drop", contests=INTERLEAVED_CONTESTS,
        policy_controls=controls, policy_schema=POLICY_SCHEMA_VERSION_V4)
    assert code == 0, report["blockers"]
    _assert_truths_unchanged(report)
    (dropped,) = [item for item in report["relaxation"]["relaxations"] if item["limitation_code"] == "THESIS_DROPPED"]
    assert dropped["constraint"] == "theses.SEA_ALL_IN"
    assert "its rows went to NE_WIN_BIG, SEA_WIN_BIG" in dropped["limitation_text"]
    assert not any(item["limitation_code"] == "RELAXATION_POLICY_DROPPED" for item in report["relaxation"]["relaxations"])
    reports = report["prior_review_reports"]
    audit = reports["portfolio_policy_audit"]
    assert audit["status"] == "PASS", audit["problems"]
    assert [(item["name"], item["rows"]) for item in audit["theses"]["theses"]] == [
        ("NE_WIN_BIG", 3), ("SEA_WIN_BIG", 3)]
    counts = {}
    for item in audit["theses"]["entries"].values():
        counts[item["thesis"]] = counts.get(item["thesis"], 0) + 1
    assert counts == {"NE_WIN_BIG": 3, "SEA_WIN_BIG": 3}
