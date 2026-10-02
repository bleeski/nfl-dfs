"""Session 53 (R36): the run-level wiring of the depth capture, the per-team fallback and the limitations.

`tests/test_qb_depth_capture.py` covers the capture itself and `tests/test_showdown_backup_qb_default.py`
the selection default. This file covers what joins them in `run-slate`: which package a run uses,
what it does when selection refuses a package the run built, and which limitations reach the file.
Every chart and pool is synthetic.
"""

from __future__ import annotations

import hashlib

import pytest

from nfl_dfs import cli, prior_review, qb_depth_capture as capture
from nfl_dfs.participation import build_participation_contract
from nfl_dfs.qb_depth_roles import QbDepthRoleError
from nfl_dfs.selection import select_prior_lineups

from . import test_qb_depth_roles as depth
from .test_qb_depth_capture import URI

_DEN_BACKUP = ("DEN", "QB", "DEN Backup QB", "", 5000)
_CHART = depth._CHART_ROWS + (("DEN", "DEN Backup QB", "00-0098888", "QB", "Quarterback", 2),)


@pytest.fixture
def den_backup(monkeypatch):
    """The synthetic pool plus a second Denver quarterback, so both teams have a backup."""

    monkeypatch.setitem(depth._SHARES, "DEN Backup QB", (0.0, 0.02, 0.0, 0.0, 0.0, 0.01, 0.0, 0.05))
    return depth._POOL + (_DEN_BACKUP,)


def _world(tmp_path, pool, *, operator_excluded=()):
    tmp_path.mkdir(parents=True, exist_ok=True)
    slate, model, contract, splits = depth._setup(tmp_path, pool=pool)
    if operator_excluded:
        contract = build_participation_contract(
            slate,
            operator_excluded_dk_ids=[p.dk_id for p in slate.players if p.name in operator_excluded],
        )
    chart = depth._depth_chart_file(tmp_path, _CHART)
    digest = hashlib.sha256(chart.read_bytes()).hexdigest()

    def capture_depth(teams, directory):
        return capture.capture_for_run(
            salaries=tmp_path / "DKSalaries.csv", depth_chart=(chart, digest, URI),
            as_of=depth.AS_OF, out_dir=tmp_path / directory, teams=teams,
        )

    def select(depth_path):
        return select_prior_lineups(
            slate, model, splits, contract, count=4, qb_depth_role_evidence_json=depth_path, as_of=depth.AS_OF
        )

    return slate, capture_depth, select


def _holds(slate, lineup, name):
    person = depth._person(slate, name)
    by_id = {p.dk_id: p for p in slate.players}
    return any(by_id[dk_id].underlying_id == person for dk_id in lineup.roster)


# --------------------------------------------------------------------------- #
# Which package a run uses
# --------------------------------------------------------------------------- #


def test_a_supplied_package_wins_and_nothing_is_captured():
    def forbidden(*_args, **_kwargs):
        raise AssertionError("a supplied package must not trigger a capture")

    reports: dict = {}
    assert prior_review._auto_capture_depth(
        supplied="/operator/qb.json", showdown=True, capture_depth=forbidden, reports=reports
    ) == ("/operator/qb.json", False)
    assert reports == {}


def test_classic_captures_nothing():
    def forbidden(*_args, **_kwargs):
        raise AssertionError("Classic builds no depth package")

    reports: dict = {}
    assert prior_review._auto_capture_depth(
        supplied=None, showdown=False, capture_depth=forbidden, reports=reports
    ) == (None, False)
    assert reports == {}


def test_a_showdown_run_with_no_package_builds_one_and_reports_it(tmp_path, den_backup):
    _slate, capture_depth, _select = _world(tmp_path, den_backup)
    reports: dict = {}
    path, auto = prior_review._auto_capture_depth(
        supplied=None, showdown=True, capture_depth=capture_depth, reports=reports
    )
    assert auto is True and path == reports["qb_depth_capture"]["package"]
    assert reports["qb_depth_capture"]["status"] == "CAPTURED"


@pytest.mark.parametrize("status", [capture.QB_DEPTH_CAPTURE_STALE, capture.QB_DEPTH_CAPTURE_UNAVAILABLE,
                                    capture.QB_DEPTH_CAPTURE_REFUSED])
def test_a_capture_that_fails_is_named_and_the_run_goes_on_without_a_package(status):
    reports: dict = {}
    result = prior_review._auto_capture_depth(
        supplied=None, showdown=True, reports=reports,
        capture_depth=lambda teams, directory: capture.CaptureOutcome(status, detail="why"),
    )
    assert result == (None, False)
    assert reports["qb_depth_capture"]["status"] == status
    assert cli._qb_depth_limitations({"qb_depth_capture": reports["qb_depth_capture"]}) == [f"{status}:why"]


# --------------------------------------------------------------------------- #
# What a run does when selection refuses a package it built
# --------------------------------------------------------------------------- #


def test_a_supplied_package_selection_refuses_still_raises(tmp_path, den_backup):
    _slate, capture_depth, select = _world(tmp_path, den_backup, operator_excluded=("KC Starter QB",))
    reports: dict = {}
    path, _auto = prior_review._auto_capture_depth(
        supplied=None, showdown=True, capture_depth=capture_depth, reports=reports
    )
    with pytest.raises(QbDepthRoleError, match="PROMOTION_OVER_AVAILABLE_PERSON"):
        prior_review._select_under_depth_package(
            select=select, capture_depth=capture_depth, qb_teams=("DEN", "KC"),
            depth_path=path, auto_captured=False, reports=reports,
        )


def test_one_teams_refusal_drops_that_team_and_keeps_the_default_for_the_other(tmp_path, den_backup):
    # R25 never promotes past a starter DraftKings still lists as available, even when the operator
    # excluded him. That refusal is about Kansas City alone, so Denver's backup stays out.
    slate, capture_depth, select = _world(tmp_path, den_backup, operator_excluded=("KC Starter QB",))
    reports: dict = {}
    path, auto = prior_review._auto_capture_depth(
        supplied=None, showdown=True, capture_depth=capture_depth, reports=reports
    )
    lineups, _scores, selection, used = prior_review._select_under_depth_package(
        select=select, capture_depth=capture_depth, qb_teams=("DEN", "KC"),
        depth_path=path, auto_captured=auto, reports=reports,
    )
    report = reports["qb_depth_capture"]
    assert report["status"] == capture.QB_DEPTH_CAPTURE_REFUSED
    assert list(report["refused_teams"]) == ["KC"] and "PROMOTION_OVER_AVAILABLE_PERSON" in report["refused_teams"]["KC"]
    assert report["package"] == used
    assert capture.Path(used).parts[-2:] == ("qb_depth_without_KC", "qb_depth_roles.json")
    default = selection["showdown_backup_qb_default"]
    assert default["excluded_people"] == [depth._person(slate, "DEN Backup QB")]
    assert default["unevaluated_teams"] == ["KC"]
    assert lineups and not any(_holds(slate, lineup, "DEN Backup QB") for lineup in lineups)
    # The refusal and the undeclared team both travel with the file by name.
    limitations = cli._qb_depth_limitations({"qb_depth_capture": report, "selection": {"selection": selection}})
    assert limitations[0].startswith("QB_DEPTH_CAPTURE_REFUSED:refused at selection")
    assert limitations[1].startswith("SHOWDOWN_BACKUP_QB_UNEVALUATED:") and "KC" in limitations[1]


def test_a_refusal_that_names_no_team_drops_the_whole_package():
    calls = []

    def select(depth_path):
        calls.append(depth_path)
        if depth_path is not None:
            raise QbDepthRoleError("QB_DEPTH_SALARY_HASH_MISMATCH")
        return ["lineup"], {}, {"selection": "ran"}

    reports = {"qb_depth_capture": {"status": "CAPTURED", "package": "p.json", "detail": ""}}
    lineups, _scores, _selection, used = prior_review._select_under_depth_package(
        select=select, capture_depth=lambda *_: pytest.fail("no team to drop, so no rebuild"),
        qb_teams=("DEN", "KC"), depth_path="p.json", auto_captured=True, reports=reports,
    )
    assert lineups == ["lineup"] and used is None and calls == ["p.json", None]
    assert reports["qb_depth_capture"]["status"] == capture.QB_DEPTH_CAPTURE_REFUSED
    assert reports["qb_depth_capture"]["package"] is None


def test_a_rebuild_that_fails_or_leaves_no_team_drops_the_whole_package():
    def select(depth_path):
        if depth_path is not None:
            raise QbDepthRoleError("QB_DEPTH_PROMOTION_OVER_AVAILABLE_PERSON:team=KC", team="KC")
        return ["lineup"], {}, {}

    for qb_teams, rebuild in (
        (("DEN", "KC"), lambda teams, directory: capture.CaptureOutcome(capture.QB_DEPTH_CAPTURE_REFUSED)),
        (("KC",), lambda *_: pytest.fail("no team remains to declare")),
    ):
        reports = {"qb_depth_capture": {"status": "CAPTURED", "package": "p.json", "detail": ""}}
        *_head, used = prior_review._select_under_depth_package(
            select=select, capture_depth=rebuild, qb_teams=qb_teams,
            depth_path="p.json", auto_captured=True, reports=reports,
        )
        assert used is None and reports["qb_depth_capture"]["package"] is None


def test_each_teams_refusal_is_dropped_in_turn_and_the_loop_ends():
    seen = []

    def select(depth_path):
        seen.append(depth_path)
        team = {"all.json": "DEN", "qb_depth_without_DEN.json": "KC"}.get(depth_path)
        if team:
            raise QbDepthRoleError(f"QB_DEPTH_PROMOTION_OVER_AVAILABLE_PERSON:team={team}", team=team)
        return ["lineup"], {}, {}

    rebuilt = []

    def rebuild(teams, directory):
        rebuilt.append((teams, directory))
        return capture.CaptureOutcome("CAPTURED", package=capture.Path(f"{directory}.json"))

    reports = {"qb_depth_capture": {"status": "CAPTURED", "package": "all.json", "detail": ""}}
    *_head, used = prior_review._select_under_depth_package(
        select=select, capture_depth=rebuild, qb_teams=("DEN", "KC", "NYG"),
        depth_path="all.json", auto_captured=True, reports=reports,
    )
    assert rebuilt == [(("KC", "NYG"), "qb_depth_without_DEN"), (("NYG",), "qb_depth_without_DEN_KC")]
    assert seen == ["all.json", "qb_depth_without_DEN.json", "qb_depth_without_DEN_KC.json"]
    assert used == "qb_depth_without_DEN_KC.json"
    assert list(reports["qb_depth_capture"]["refused_teams"]) == ["DEN", "KC"]


# --------------------------------------------------------------------------- #
# The limitations that reach the file
# --------------------------------------------------------------------------- #


def test_a_clean_capture_and_a_fully_evaluated_slate_name_nothing():
    reports = {
        "qb_depth_capture": {"status": "CAPTURED", "detail": ""},
        "selection": {"selection": {"showdown_backup_qb_default": {"applies": True, "unevaluated_teams": []}}},
    }
    assert cli._qb_depth_limitations(reports) == []
    assert cli._qb_depth_limitations({}) == []


def test_classic_names_no_depth_limitation_and_reports_the_default_as_not_applying(tmp_path):
    from . import test_classic_prior_review as classic

    outcome, _slate, _inactive = classic._run(tmp_path)
    assert "qb_depth_capture" not in outcome.reports
    block = outcome.reports["selection"]["selection"]["showdown_backup_qb_default"]
    assert block["applies"] is False and block["excluded_people"] == [] and block["unevaluated_teams"] == []
    assert cli._qb_depth_limitations(outcome.reports) == []


def test_a_package_damaged_after_capture_is_dropped_named_and_the_run_selects_without_it(tmp_path, den_backup):
    slate, capture_depth, select = _world(tmp_path, den_backup)
    reports: dict = {}
    path, auto = prior_review._auto_capture_depth(
        supplied=None, showdown=True, capture_depth=capture_depth, reports=reports
    )
    package = capture.Path(path)
    package.write_bytes(package.read_bytes()[:-9])
    lineups, _scores, selection, used = prior_review._select_under_depth_package(
        select=select, capture_depth=capture_depth, qb_teams=("DEN", "KC"),
        depth_path=path, auto_captured=auto, reports=reports,
    )
    assert used is None and lineups
    assert reports["qb_depth_capture"]["status"] == capture.QB_DEPTH_CAPTURE_REFUSED
    assert reports["qb_depth_capture"]["package"] is None
    default = selection["showdown_backup_qb_default"]
    assert default["excluded_people"] == [] and default["unevaluated_teams"] == ["DEN", "KC"]
