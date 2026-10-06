"""Session 53 (R36): the run-level wiring of the depth capture, the per-team fallback and the limitations.

`tests/test_qb_depth_capture.py` covers the capture itself and `tests/test_showdown_backup_qb_default.py`
the selection default. This file covers what joins them in `run-slate`: which package a run uses,
what it does when selection refuses a package the run built, and which limitations reach the file.
Every chart and pool is synthetic. Since Session 63 the capture runs for Classic as well and a team the
chart cannot declare is named and left out, so the second half drives a Classic slate through `run_prior_review`
and `run-slate` (once per Classic exit) with a frozen chart that lacks one team.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

from nfl_dfs import cli, prior_review, qb_depth_capture as capture
from nfl_dfs.dk import parse_salaries
from nfl_dfs.participation import build_participation_contract
from nfl_dfs.prior_review import run_prior_review
from nfl_dfs.qb_depth_roles import DEPTH_CHART_COLUMNS, QbDepthRoleError
from nfl_dfs.selection import select_prior_lineups

from . import test_classic_judgment as judgment
from . import test_classic_prior_review as classic
from . import test_qb_depth_roles as depth
from . import test_relaxation_controller as relaxation
from .test_qb_depth_capture import URI

_DEN_BACKUP = ("DEN", "QB", "DEN Backup QB", "", 5000)
_CHART = depth._CHART_ROWS + (("DEN", "DEN Backup QB", "00-0098888", "QB", "Quarterback", 2),)


@pytest.fixture
def den_backup(monkeypatch):
    """The synthetic pool plus a second Denver quarterback, so both teams have a backup."""

    monkeypatch.setitem(depth._SHARES, "DEN Backup QB", (0.0, 0.02, 0.0, 0.0, 0.0, 0.01, 0.0, 0.05))
    return depth._POOL + (_DEN_BACKUP,)


def _world(tmp_path, pool, *, operator_excluded=(), edit_model=None):
    tmp_path.mkdir(parents=True, exist_ok=True)
    slate, model, contract, splits = depth._setup(tmp_path, pool=pool)
    if edit_model is not None:
        model = edit_model(model)
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
        supplied="/operator/qb.json", capture_depth=forbidden, reports=reports
    ) == ("/operator/qb.json", False)
    assert reports == {}


def test_a_showdown_run_with_no_package_builds_one_and_reports_it(tmp_path, den_backup):
    _slate, capture_depth, _select = _world(tmp_path, den_backup)
    reports: dict = {}
    path, auto = prior_review._auto_capture_depth(
        supplied=None, capture_depth=capture_depth, reports=reports
    )
    assert auto is True and path == reports["qb_depth_capture"]["package"]
    assert reports["qb_depth_capture"]["status"] == "CAPTURED"


@pytest.mark.parametrize("status", [capture.QB_DEPTH_CAPTURE_STALE, capture.QB_DEPTH_CAPTURE_UNAVAILABLE,
                                    capture.QB_DEPTH_CAPTURE_REFUSED])
def test_a_capture_that_fails_is_named_and_the_run_goes_on_without_a_package(status):
    reports: dict = {}
    result = prior_review._auto_capture_depth(
        supplied=None, reports=reports,
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
        supplied=None, capture_depth=capture_depth, reports=reports
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
        supplied=None, capture_depth=capture_depth, reports=reports
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
    assert reports["qb_depth_capture"]["declared_teams"] == []  # no package is in use, so no team is declared


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


def test_classic_without_a_frozen_chart_names_the_capture_gap_and_the_default_gap_by_team(tmp_path):
    """Edited by Session 63 (R36 for Classic), named in the changelog. Edited by Session 61 before it.

    Session 61 made this assert that Classic builds no package of its own (`"qb_depth_capture" not in
    reports`, no Showdown-helper line). Classic now tries to capture, so a run whose prior package froze
    no depth chart reports `QB_DEPTH_CAPTURE_UNAVAILABLE` (`P`, appended to the file's blockers) and still
    names every quarterback team as unevaluated, nobody guessed out. The Showdown block is unchanged: it
    still reports that it does not apply.
    """

    outcome, _slate, _inactive = classic._run(tmp_path)
    report = outcome.reports["qb_depth_capture"]
    assert report["status"] == capture.QB_DEPTH_CAPTURE_UNAVAILABLE and report["package"] is None
    # With no depth evidence there is nothing to measure, and no second scoring pass was run to say so.
    effect = outcome.reports["selection"]["selection"]["depth_order_effect"]
    assert effect["status"] == "NO_DEPTH_EVIDENCE" and "scores_moved" not in effect
    block = outcome.reports["selection"]["selection"]["showdown_backup_qb_default"]
    assert block["applies"] is False and block["excluded_people"] == [] and block["unevaluated_teams"] == []
    default = outcome.reports["selection"]["selection"]["classic_backup_qb_default"]
    assert default["applies"] is True and default["excluded_people"] == []
    assert default["unevaluated_teams"] == ["DAL", "NE", "PHI", "SEA"]
    assert cli._qb_depth_capture_limitations(outcome.reports) == [
        "QB_DEPTH_CAPTURE_UNAVAILABLE:no depth chart was frozen with the prior package"
    ]
    (limitation,) = cli._classic_judgment_limitations(outcome.reports)
    assert limitation.startswith("CLASSIC_BACKUP_QB_UNEVALUATED:no quarterback depth evidence orders DAL, NE, PHI, SEA")


def test_a_package_damaged_after_capture_is_dropped_named_and_the_run_selects_without_it(tmp_path, den_backup):
    slate, capture_depth, select = _world(tmp_path, den_backup)
    reports: dict = {}
    path, auto = prior_review._auto_capture_depth(
        supplied=None, capture_depth=capture_depth, reports=reports
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


# --------------------------------------------------------------------------- #
# Session 63: the capture on a team the chart cannot declare, named per team
# --------------------------------------------------------------------------- #


def test_a_package_that_leaves_a_team_out_names_it_before_the_showdown_default_gap():
    reports = {
        "qb_depth_capture": {
            "status": "CAPTURED", "package": "p.json", "detail": "", "undeclared_teams": {"KC": "chart lists no quarterback"},
        },
        "selection": {"selection": {"showdown_backup_qb_default": {"applies": True, "unevaluated_teams": ["KC"]}}},
    }
    limitations = cli._qb_depth_limitations(reports)
    assert limitations[0] == "QB_DEPTH_CAPTURE_TEAM_UNDECLARED:KC:chart lists no quarterback"
    assert limitations[1].startswith("SHOWDOWN_BACKUP_QB_UNEVALUATED:") and len(limitations) == 2
    assert cli._qb_depth_capture_limitations(reports) == limitations[:1]


def test_with_no_package_the_whole_capture_line_stands_alone_and_32_teams_never_bury_the_file():
    reports = {
        "qb_depth_capture": {
            "status": capture.QB_DEPTH_CAPTURE_REFUSED, "package": None, "detail": "the chart declares none of its 32 teams: ...",
            "undeclared_teams": {f"T{index:02d}": "chart lists no quarterback" for index in range(32)},
        }
    }
    assert cli._qb_depth_capture_limitations(reports) == [
        "QB_DEPTH_CAPTURE_REFUSED:the chart declares none of its 32 teams: ..."
    ]


def test_a_model_side_refusal_names_its_team_so_one_team_never_costs_the_others(tmp_path, den_backup):
    """D3: the resolver's per-team model refusals carry their team, so an auto-built package drops just that team.

    The model loader conserves a team's quarterback pool at the unit, so the pool is set to 0.5 on the loaded
    model (neither empty nor the unit), which the resolver refuses as `POOL_NOT_UNIT`. Before the tag that refusal
    named no team and the whole package, Kansas City's declaration included, was dropped; a package the operator
    supplied still raises, now with its team on the error.
    """

    def halve_denver(model):
        return replace(model, players=tuple(
            replace(player, qb_attempt_share=0.5) if player.underlying_id.endswith("DEN Starter QB") else player
            for player in model.players))

    slate, capture_depth, select = _world(tmp_path, den_backup, edit_model=halve_denver)
    reports: dict = {}
    path, auto = prior_review._auto_capture_depth(supplied=None, capture_depth=capture_depth, reports=reports)
    lineups, _scores, selection, used = prior_review._select_under_depth_package(
        select=select, capture_depth=capture_depth, qb_teams=("DEN", "KC"),
        depth_path=path, auto_captured=auto, reports=reports,
    )
    report = reports["qb_depth_capture"]
    assert list(report["refused_teams"]) == ["DEN"] and "POOL_NOT_UNIT" in report["refused_teams"]["DEN"]
    assert report["declared_teams"] == ["KC"] and report["package"] == used
    default = selection["showdown_backup_qb_default"]
    assert default["unevaluated_teams"] == ["DEN"]
    assert default["excluded_people"] == [depth._person(slate, "KC Backup QB")]
    assert lineups and not any(_holds(slate, lineup, "KC Backup QB") for lineup in lineups)
    with pytest.raises(QbDepthRoleError, match="POOL_NOT_UNIT") as raised:
        prior_review._select_under_depth_package(
            select=select, capture_depth=capture_depth, qb_teams=("DEN", "KC"),
            depth_path=path, auto_captured=False, reports={},
        )
    assert raised.value.team == "DEN"


# ---- a Classic slate with a frozen chart, through `run_prior_review` and through `run-slate`

CHART_TEAMS = ("NE", "PHI", "SEA")  # the fixture's fourth team, DAL, is the one the chart lacks
STARTER_AND_BACKUP = {team: (f"{team}|QB|{team} QB One", f"{team}|QB|{team} QB Two") for team in ("DAL", "NE", "PHI", "SEA")}


def _chart_bytes(slate, teams) -> bytes:
    """The published shape, quarterback rows only: each listed team's quarterbacks in name order, One at rank 1."""

    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(DEPTH_CHART_COLUMNS)
    stamp = (classic.AS_OF - timedelta(hours=6)).isoformat().replace("+00:00", "Z")
    for index, team in enumerate(sorted(teams)):
        names = sorted(p.name for p in slate.players if p.team == team and p.position == "QB")
        for rank, name in enumerate(names, start=1):
            writer.writerow([stamp, team, name, "", f"00-{9100000 + 10 * index + rank}", "16", "3WR 1TE", "9",
                             "Quarterback", "QB", "9", str(rank)])
    return buffer.getvalue().encode("utf-8")


def _freeze_chart(package: Path, slate, teams) -> str:
    """Put the chart where a frozen prior package keeps it, exactly as `priors` would have."""

    chart = _chart_bytes(slate, teams)
    digest = hashlib.sha256(chart).hexdigest()
    (package / "raw" / f"{digest}.csv").write_bytes(chart)
    manifest_path = package / "prior_package.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["frozen_sources"]["depth_charts"] = digest
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return digest


def _classic_with_chart(tmp_path, teams=CHART_TEAMS, **kwargs):
    salary, entry, package, _role, status, _inactive = classic._fixture(tmp_path, depth=judgment.DEPTH)
    slate = parse_salaries(salary)
    _freeze_chart(package, slate, teams)
    outcome = run_prior_review(
        salary_csv=salary, entry_csv=entry, label="classic-depth", as_of=classic.AS_OF, run_root=tmp_path / "run",
        output_root=tmp_path / "out", prior_package_dir=package, official_status_csv=status, **kwargs)
    return outcome, slate


def _held(slate, outcome) -> set[str]:
    by_id = {player.dk_id: player.underlying_id for player in slate.players}
    return {by_id[dk_id] for lineup in outcome.reports["selection"]["lineups"] for dk_id in lineup["roster"]}


def test_a_classic_run_declares_the_teams_its_chart_can_names_the_one_it_cannot_and_keeps_the_backups_out(tmp_path):
    outcome, slate = _classic_with_chart(tmp_path)
    assert not outcome.blocked, outcome.blockers
    report = outcome.reports["qb_depth_capture"]
    assert report["status"] == "CAPTURED" and report["declared_teams"] == list(CHART_TEAMS)
    assert list(report["undeclared_teams"]) == ["DAL"]
    assert "lists no quarterback for DAL" in report["undeclared_teams"]["DAL"]
    selector = outcome.reports["selection"]["selection"]
    assert selector["qb_depth_roles"]["starters_by_team"] == {team: STARTER_AND_BACKUP[team][0] for team in CHART_TEAMS}
    default = selector["classic_backup_qb_default"]
    assert default["unevaluated_teams"] == ["DAL"]
    assert default["excluded_people"] == sorted(STARTER_AND_BACKUP[team][1] for team in CHART_TEAMS)
    held = _held(slate, outcome)
    assert held and not held & set(default["excluded_people"])
    assert "qb_depth_role_evidence_json" in outcome.hashes  # the package that was used is hash-bound
    (line,) = cli._qb_depth_capture_limitations(outcome.reports)
    assert line.startswith("QB_DEPTH_CAPTURE_TEAM_UNDECLARED:DAL:")
    assert outcome.reports["selection"]["MODEL_STATUS"] == "PRIOR_ONLY"
    assert outcome.reports["selection"]["RELEASE_DECISION"] == "DO_NOT_UPLOAD"
    # How many scores the depth order moved (D5): the declared starters' attempt shares, nothing else. Each of the
    # three declared teams has two quarterbacks of equal weight, so the unit pool splits half and half before the
    # chart and goes whole to One after it: six shares and six scores move, One up and Two down; DAL, undeclared, none.
    effect = selector["depth_order_effect"]
    assert effect["version"] == "classic_depth_order_effect_v1" and effect["status"] == "SCORED"
    assert effect["declared_teams"] == list(CHART_TEAMS)
    assert effect["attempt_shares_moved"] == 6 and effect["scores_moved"] == 6
    assert (effect["scored_only_with_depth"], effect["scored_only_without_depth"]) == ([], [])
    moves = {row["person"]: row for row in effect["largest_moves"]}
    assert set(moves) == {person for team in CHART_TEAMS for person in STARTER_AND_BACKUP[team]}
    assert all(moves[STARTER_AND_BACKUP[team][0]]["delta"] > 0 > moves[STARTER_AND_BACKUP[team][1]]["delta"] for team in CHART_TEAMS)
    assert "DAL" not in json.dumps(effect["largest_moves"])
    assert json.loads(json.dumps(effect)) == effect and "seconds" not in json.dumps(effect)  # hash-bound: no wall time


def test_a_classic_run_on_the_same_bytes_gives_the_same_package_and_the_same_effect(tmp_path):
    first, _slate_one = _classic_with_chart(tmp_path / "a")
    second, _slate_two = _classic_with_chart(tmp_path / "b")
    package = lambda outcome: Path(outcome.reports["qb_depth_capture"]["package"]).read_bytes()  # noqa: E731
    assert package(first) == package(second)
    effect = lambda outcome: json.dumps(outcome.reports["selection"]["selection"]["depth_order_effect"], sort_keys=True)  # noqa: E731
    assert effect(first) == effect(second)
    assert first.reports["qb_depth_capture"]["undeclared_teams"] == second.reports["qb_depth_capture"]["undeclared_teams"]
    assert first.hashes["qb_depth_role_evidence_json"] == second.hashes["qb_depth_role_evidence_json"]


def test_a_classic_run_with_every_team_on_the_chart_names_nothing_and_still_keeps_the_backups_out(tmp_path):
    outcome, slate = _classic_with_chart(tmp_path, teams=("DAL", "NE", "PHI", "SEA"))
    assert outcome.reports["qb_depth_capture"]["undeclared_teams"] == {}
    assert cli._qb_depth_capture_limitations(outcome.reports) == []
    assert cli._classic_judgment_limitations(outcome.reports) == []
    default = outcome.reports["selection"]["selection"]["classic_backup_qb_default"]
    assert default["unevaluated_teams"] == [] and len(default["excluded_people"]) == 4
    assert not _held(slate, outcome) & set(default["excluded_people"])


def test_an_operator_excluded_starter_drops_that_team_from_an_auto_built_classic_package_and_keeps_the_rest(tmp_path):
    salary = tmp_path / "probe"
    probe = classic._fixture(salary, depth=judgment.DEPTH)
    dk_id = next(p.dk_id for p in parse_salaries(probe[0]).players if p.name == "NE QB One")
    outcome, slate = _classic_with_chart(tmp_path / "run", teams=("DAL", "NE", "PHI", "SEA"), operator_excluded_dk_ids=[dk_id])
    assert not outcome.blocked, outcome.blockers
    report = outcome.reports["qb_depth_capture"]
    assert report["status"] == capture.QB_DEPTH_CAPTURE_REFUSED
    assert list(report["refused_teams"]) == ["NE"] and "PROMOTION_OVER_AVAILABLE_PERSON" in report["refused_teams"]["NE"]
    assert report["declared_teams"] == ["DAL", "PHI", "SEA"] and report["package"]
    default = outcome.reports["selection"]["selection"]["classic_backup_qb_default"]
    assert default["unevaluated_teams"] == ["NE"]
    assert default["excluded_people"] == sorted(STARTER_AND_BACKUP[team][1] for team in ("DAL", "PHI", "SEA"))
    assert not _held(slate, outcome) & set(default["excluded_people"])
    assert cli._qb_depth_capture_limitations(outcome.reports)[0].startswith("QB_DEPTH_CAPTURE_REFUSED:refused at selection")


def test_a_supplied_classic_package_the_resolver_refuses_still_stops_the_review(tmp_path, monkeypatch):
    monkeypatch.setattr(judgment.qb_depth, "_GSIS", dict(judgment.qb_depth._GSIS))
    probe = classic._fixture(tmp_path / "probe", depth=judgment.DEPTH)
    probe_slate = parse_salaries(probe[0])
    dk_id = next(p.dk_id for p in probe_slate.players if p.name == "NE QB One")
    salary, entry, package, _role, status, _inactive = classic._fixture(tmp_path / "run", depth=judgment.DEPTH)
    supplied = judgment._qb_package(tmp_path / "run", parse_salaries(salary))
    outcome = run_prior_review(
        salary_csv=salary, entry_csv=entry, label="classic-supplied", as_of=classic.AS_OF, run_root=tmp_path / "run" / "r",
        output_root=tmp_path / "run" / "o", prior_package_dir=package, official_status_csv=status,
        qb_depth_role_evidence_json=supplied, operator_excluded_dk_ids=[dk_id])
    assert outcome.blocked and "PROMOTION_OVER_AVAILABLE_PERSON" in outcome.error
    assert "qb_depth_capture" not in outcome.reports  # a supplied package is never replaced by a capture


def _with_chart(monkeypatch, teams):
    """`run-slate`'s Classic harness, with the fixture's prior package carrying a frozen depth chart."""

    original = relaxation.classic_fixture

    def fixture(root, **kwargs):
        built = original(root, **kwargs)
        _freeze_chart(built[2], parse_salaries(built[0]), teams)
        return built

    monkeypatch.setattr(relaxation, "classic_fixture", fixture)


def _run_slate(tmp_path, monkeypatch, *, run_id, policy, entries):
    holder: dict = {}

    def extra(attachments):
        holder["slate"] = parse_salaries(attachments / "salary.csv")
        return {}

    _with_chart(monkeypatch, CHART_TEAMS)
    code, report, root = relaxation._classic(
        tmp_path, monkeypatch, run_id=run_id, policy=policy, entries=entries, depth=judgment.DEPTH, extra=extra)
    return code, report, holder["slate"]


def _assert_capture_travels(report, slate):
    blockers = report["blockers"]
    assert report["RELEASE_DECISION"] == "DO_NOT_UPLOAD" and report["MODEL_STATUS"] == "PRIOR_ONLY"
    assert report["DELIVERY_STATE"] == "DELIVERABLE" and not list(Path(report["latest_deliverable"]["path"]).parent.glob("DK_UPLOAD_*.csv"))
    (team_line,) = [item for item in blockers if item.startswith("QB_DEPTH_CAPTURE_TEAM_UNDECLARED:")]
    assert team_line.startswith("QB_DEPTH_CAPTURE_TEAM_UNDECLARED:DAL:")
    (default_line,) = [item for item in blockers if item.startswith("CLASSIC_BACKUP_QB_UNEVALUATED:")]
    assert "orders DAL, so no backup quarterback of those teams was excluded" in default_line
    # Appended, never first: a blocker that withholds a file keeps index 0 (the six tests that read it there).
    assert not blockers[0].startswith(("QB_DEPTH_CAPTURE", "CLASSIC_BACKUP_QB"))
    assert blockers.index(team_line) < blockers.index(default_line)
    by_id = {p.dk_id: p.underlying_id for p in slate.players}
    held = {by_id[dk_id] for roster in relaxation._exported_rosters(report) for dk_id in roster}
    backups = {STARTER_AND_BACKUP[team][1] for team in CHART_TEAMS}
    assert held and not held & backups


def test_run_slate_delivers_a_classic_file_declaring_three_teams_and_naming_the_fourth(tmp_path, monkeypatch):
    code, report, slate = _run_slate(tmp_path, monkeypatch, run_id="depth-c1", policy=None, entries=4)
    assert code == 0, report["blockers"]
    assert report["latest_deliverable"]["producer"] == "run-slate:prior_review:CLASSIC_C1"
    _assert_capture_travels(report, slate)


def test_a_showdown_run_slate_still_puts_its_depth_limitations_first(tmp_path, monkeypatch):
    """Only Classic's capture limitations are appended; Showdown's stay at the front of the file's blockers.

    A mutation pass found the Showdown ordering unguarded at the run-slate level (Session 53 never pinned it):
    this prior package froze no chart, so the capture is `UNAVAILABLE` and every team is unevaluated.
    """

    code, report = relaxation._showdown_subset_run(
        tmp_path, monkeypatch, run_id="sd-depth-order", rows=("900000001", "900000002", "900000003", "900000004"),
        bound=("900000002",),
        controls={"max_captain_exposure": {"default_fraction": 1, "overrides": []}, "max_pairwise_person_overlap": 4})
    assert code == 0, report["blockers"]
    assert report["blockers"][0].startswith("QB_DEPTH_CAPTURE_UNAVAILABLE:")
    assert report["blockers"][1].startswith("SHOWDOWN_BACKUP_QB_UNEVALUATED:")


def test_run_slate_delivers_a_classic_c3_file_declaring_three_teams_and_naming_the_fourth(tmp_path, monkeypatch):
    code, report, slate = _run_slate(
        tmp_path, monkeypatch, run_id="depth-c3", policy=lambda attachments: relaxation._policy_file(attachments), entries=3)
    assert code == 0 and report["stage"] == "PRIOR_ONLY_CLASSIC_C3_REVIEW_EXPORT", report["blockers"]
    _assert_capture_travels(report, slate)
