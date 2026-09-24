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

from nfl_dfs.hashing import sha256_file

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
        mutate(salary=salary, status=status, package=package)
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

    def keep_two_rows(*, salary, status, package):
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


def test_an_unobserved_game_ships_named_and_moves_no_number(tmp_path, monkeypatch):
    """Missing weather (R28, Session 09). A frozen package whose team prior
    records one game `UNOBSERVED` (team source v2) projects, selects and ships;
    the game is named, `EVIDENCE_STATE` is not `PASS`, and the file is the same
    one the fully observed package builds, because weather moves no number."""

    code, observed, _salary = _run_slate(tmp_path / "observed", monkeypatch, run_id="observed")
    _the_models_file_is_delivered(code, observed)
    unobserved_game: dict[str, str] = {}

    def unobserve_one_game(*, salary, status, package):
        team_path = package / "team_prior.json"
        team = json.loads(team_path.read_text(encoding="utf-8"))
        game = sorted({record["game_id"] for record in team["records"]})[0]
        unobserved_game["id"] = game
        team["schema_version"] = "nfl_team_projection_source_v2"
        for record in team["records"]:
            if record["game_id"] == game:
                record["weather_state"] = "UNOBSERVED"
        team_path.write_text(json.dumps(team, indent=2), encoding="utf-8")
        manifest_path = package / "prior_package.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["artifacts"]["team_prior.json"] = sha256_file(team_path)
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    code, report, _salary = _run_slate(
        tmp_path / "unobserved", monkeypatch, run_id="unobserved", mutate=unobserve_one_game)
    _the_models_file_is_delivered(code, report)
    [item] = _limitations(report)["WEATHER_UNOBSERVED"]
    assert (item["class"], item["stops"]) == ("P", "CERTIFICATION")
    assert item["detail"].startswith(f"WEATHER_UNOBSERVED:{unobserved_game['id']}:")
    assert (observed["EVIDENCE_STATE"], report["EVIDENCE_STATE"]) == ("PASS", "UNKNOWN")
    # R24: the same lineups, entry for entry.
    assert _delivered_rosters(report) == _delivered_rosters(observed)
    team_csv = Path(report["prior_review_artifacts"]["team_projections"]).read_text(encoding="utf-8")
    assert ",UNOBSERVED," in team_csv
    # The team CSV holding it is declared v2; the observed run's is still v1.
    for run, version in ((report, "nfl_team_projections_csv_v2"), (observed, "nfl_team_projections_csv_v1")):
        manifest = Path(run["prior_review_artifacts"]["prelock_manifest"]).read_text(encoding="utf-8")
        assert f'"{version}"' in manifest


def test_a_v1_team_source_can_never_hold_an_unobserved_game(tmp_path):
    """v1 is never mutated: only `nfl_team_projection_source_v2` may say it."""

    from pydantic import ValidationError

    from nfl_dfs.projection import TeamSource

    _salary, _entry, package, _role, _status, _ = classic_fixture(tmp_path / "fixture", entries=1)
    team = json.loads((package / "team_prior.json").read_text(encoding="utf-8"))
    team["records"][0]["weather_state"] = "UNOBSERVED"
    with pytest.raises(ValidationError, match="UNOBSERVED weather needs nfl_team_projection_source_v2"):
        TeamSource.model_validate(team)
    team["schema_version"] = "nfl_team_projection_source_v2"
    assert TeamSource.model_validate(team).records[0].weather_state == "UNOBSERVED"


def test_certification_never_reads_an_unobserved_game_as_weather_evidence():
    from datetime import datetime, timezone
    from types import SimpleNamespace

    from nfl_dfs.cli import _base_evidence

    now = datetime.now(timezone.utc).isoformat()

    def weather_record(state):
        model = SimpleNamespace(teams=[
            SimpleNamespace(team=team, market_total=45, market_spread=0, market_observed_at=now,
                            weather_state=state)
            for team in ("NE", "SEA")])
        records = _base_evidence(
            slate_hash="a" * 64, entries_hash="b" * 64, payout_path="unused", payout_hash="c" * 64,
            manual_guardrail=False, model_input_hash="d" * 64, model=model)
        return next(record for record in records if record.field == "weather_if_required")

    assert weather_record("CLEAR").state == "PASS"
    unobserved = weather_record("UNOBSERVED")
    assert (unobserved.state, unobserved.hard_gate) == ("UNKNOWN", True)
    assert "NE, SEA" in unobserved.reason


def test_build_priors_authority_persists_through_a_request_rerun(tmp_path, monkeypatch):
    """The card's `build_priors` item (audit D8). A request that authorizes the
    rebuild never stops to ask for that authority again: not on its own run,
    and not on a plain `--request` rerun of the request it saved, which carries
    `build_priors: true`. The rebuild is stubbed at `propose` so no network is
    touched; reaching it is the proof that nothing asked first."""

    from nfl_dfs import cli
    from nfl_dfs import prior_review as prior_review_module

    salary, entry, _package, _role, _status, _ = classic_fixture(tmp_path / "fixture", entries=1)
    attachments = _attachments(tmp_path, salary, entry)
    monkeypatch.setattr(cli, "DEFAULT_RUNS_DIR", tmp_path / "runs")
    rebuilds: list[str] = []

    def propose(**kwargs):
        rebuilds.append(str(kwargs["output_dir"]))
        raise RuntimeError("REBUILD_REACHED_WITHOUT_ASKING")

    real = prior_review_module.run_prior_review
    monkeypatch.setattr(cli, "run_prior_review", lambda **kwargs: real(**kwargs, propose=propose))

    def asked(report) -> list[str]:
        return [value for value in report["blockers"]
                if value.startswith(("PRIOR_PACKAGE_REQUIRED", "PRIOR_PACKAGE_EXPIRED"))]

    code = cli.command_cowork_run(_cowork_args(
        tmp_path, attachments, run_id="first", build_priors=True, as_of=AS_OF.isoformat()))
    first = json.loads((tmp_path / "outputs" / "first" / "cowork_run.json").read_text(encoding="utf-8"))
    saved = json.loads(Path(first["request"]).read_text(encoding="utf-8"))
    assert saved["build_priors"] is True and saved["prior_package_dir"] is None

    code = cli.command_cowork_run(_cowork_args(
        tmp_path, attachments, run_id="rerun", request=first["request"], input_dir=None,
        build_priors=False, as_of=AS_OF.isoformat()))
    rerun = json.loads((tmp_path / "outputs" / "rerun" / "cowork_run.json").read_text(encoding="utf-8"))
    assert code == 2  # the stubbed rebuild fails; the baseline is the file
    for report in (first, rerun):
        assert asked(report) == []
        assert any(value.startswith("PRIORS_PROPOSE_FAILED:RuntimeError:REBUILD_REACHED_WITHOUT_ASKING")
                   for value in report["blockers"])
        assert report["DELIVERY_STATE"] == "DELIVERABLE"
        assert report["latest_deliverable"]["producer"] == "run-slate:baseline"
    assert len(rebuilds) == 2


def test_an_unsourced_state_never_reaches_a_multi_game_classic_freeze(tmp_path):
    """Session 09 review, the blocking case. A Classic request with a typed
    `weather_state` and no source, whose first-locking game is under a dome,
    used to hand that state to the legacy freeze as the scalar capture, and two
    outdoor games then stopped it (CLASSIC_WEATHER_SCOPE_AMBIGUOUS). Nothing
    unattributed reaches the freeze now, whatever the game order."""

    from nfl_dfs.prior_review import run_prior_review

    salary, entry, _package, _role, _status, _ = classic_fixture(tmp_path / "fixture", entries=1)
    slate = parse_salaries(salary)
    first, *rest = [game.game_id for game in slate.games]
    seen: dict[str, object] = {}

    def propose(**kwargs):
        root = Path(kwargs["output_dir"])
        (root / "raw").mkdir(parents=True)
        proposals = [
            {"dk_id": player.dk_id, "captain_dk_id": player.dk_id, "dk_name": player.name,
             "dk_team": player.team, "dk_position": player.position,
             "underlying_id": player.underlying_id, "nflverse_team": player.team,
             "provider_player_id": f"00-{int(player.dk_id) % 10_000_000:07d}",
             "provider_name": player.name, "provider_pfr_id": "", "provider_team": player.team,
             "provider_status": "ACT", "match_method": "NORMALIZED_NAME_TEAM_POSITION",
             "candidates": []}
            for player in slate.players
        ]
        (root / "identity_proposals.json").write_text(json.dumps({"proposals": proposals}), encoding="utf-8")
        return {"package_dir": str(root), "identity_proposals": str(root / "identity_proposals.json"),
                "source_manifest": str(root / "source_manifest.json"), "hashes": {},
                "markets": {first: {"roof": "dome"}, **{game: {"roof": "outdoors"} for game in rest}}}

    def freeze(**kwargs):
        seen.update(kwargs)
        raise RuntimeError("FREEZE_REACHED")

    outcome = run_prior_review(
        salary_csv=salary, entry_csv=entry, label="unsourced", as_of=AS_OF,
        run_root=tmp_path / "run", output_root=tmp_path / "out", build_priors=True,
        weather_state="CLEAR", propose=propose, freeze=freeze)
    assert outcome.blockers == ("PRIORS_FREEZE_FAILED:RuntimeError:FREEZE_REACHED",)
    assert (seen["weather_state"], seen["weather_source_uri"], seen["weather_observed_at"]) == (None, None, None)
    games = outcome.reports["weather"]["games"]
    assert games[first]["limitations"] == []
    for game in rest:
        [limitation] = games[game]["limitations"]
        assert "the unattributed state CLEAR was not used" in limitation


def test_a_reused_package_with_an_unsourced_state_is_named(tmp_path):
    """A package frozen outside run-slate may carry a typed state with no
    source (Showdown's standalone freeze still writes one). Reusing it names
    the game rather than reading the state as an observation."""

    from nfl_dfs.prior_review import _unobserved_weather

    team = tmp_path / "team_prior.json"
    team.write_text(json.dumps({
        "metadata": {"coverage": {"weather_basis_by_game": {
            "NE@SEA": "OPERATOR_SUPPLIED:roof=outdoors|OPERATOR_SUPPLIED_UNATTRIBUTED",
            "DAL@PHI": "DERIVED_FROM_SCHEDULE_ROOF:dome"}}},
        "records": [{"game_id": "NE@SEA", "weather_state": "RAIN"}]}), encoding="utf-8")
    [named] = _unobserved_weather(team)
    assert named.startswith("WEATHER_UNOBSERVED:NE@SEA:OPERATOR_SUPPLIED:roof=outdoors|")
    assert "typed without a captured source" in named
