"""Session 61 (R37, P9 part 2): the Classic judgment pass inside the run.

Every number here is a test input. The assertions are about what the pass names and why:
the starters check, the injury rooms with their before and after, the candidate list and its
order, the late-swap watch list, the Classic backup-quarterback default, and that none of it
writes a number, clears a gate or moves a release truth. The Week 4 frozen priors are not on
this host, so the Week 4 cases (Allen, Wilson, Ertz, Jennings) are reproduced by shape on the
Classic fixture, not by name.
"""

from __future__ import annotations

import copy
import csv
import io
import json
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from nfl_dfs import classic_judgment as cj
from nfl_dfs.dk import parse_salaries
from nfl_dfs.hashing import sha256_bytes
from nfl_dfs.prior_review import run_prior_review
from nfl_dfs.qb_depth_roles import ALLOCATION_VERSION, SCHEMA_VERSION, TRANSFORMATION_VERSION

from . import test_classic_prior_review as classic
from . import test_qb_depth_roles as qb_depth

NE_ONE, NE_TWO = "NE|RB|NE RB One", "NE|RB|NE RB Two"
SEA_WR_ONE, SEA_WR_THREE = "SEA|WR|SEA WR One", "SEA|WR|SEA WR Three"
DEPTH = {"QB": 2, "RB": 2, "WR": 3, "TE": 1, "DST": 1}


# ----------------------------------------------------------------------------- fixtures


def _slate(tmp_path, depth=DEPTH):
    path = Path(tmp_path) / "salary.csv"
    path.write_bytes(classic._salary_bytes(depth=depth))
    return parse_salaries(path)


def _coverage(slate, **reasons):
    """Pool coverage rows: SELECTABLE unless a person is named in `reasons` ({person: (reason, status)})."""

    rows = []
    for player in slate.players:
        reason, status = reasons.get(player.underlying_id, ("SELECTABLE", ""))
        rows.append({
            "person": player.underlying_id, "name": player.name, "team": player.team,
            "position": player.position, "game_id": player.game_id, "lock_at": player.lock_at.isoformat(),
            "dk_ids": [player.dk_id], "dk_status": status, "official_activity": "UNKNOWN", "reason": reason,
            "smallest_evidence_action": "", "salary": player.salary,
        })
    return {"people": rows}


def _person(slate, name):
    return next(p.underlying_id for p in slate.players if p.name == name)


def _move(team, position, field, vacated, absorbed, total, *, unallocated=0.0):
    return {
        "team": team, "position": position, "field": field, "vacated_total": total, "unallocated": unallocated,
        "vacated": [{"person": p, "name": p.split("|")[-1], "share": s, "triggered_by": ["DK_STATUS_UNAVAILABLE"]}
                    for p, s in vacated],
        "absorbed": [{"person": p, "name": p.split("|")[-1], "before": b, "after": a, "gained": round(a - b, 6)}
                     for p, b, a in absorbed],
    }


def _redistribution(moves, unresolved=()):
    return {
        "applied": True, "rule": "PROPORTIONAL_TO_PRIOR_WITHIN_VACATING_POSITION_NO_SPILL_V1",
        "transformation_version": "injury_room_workload_redistribution_v1", "moves": moves,
        "not_absorbing_unresolved_current_role": list(unresolved),
        "quarterbacks_left_to_the_depth_evidence": [],
    }


def _findings(**states):
    """Offensive-role findings: {person: (state, history_state, action)}."""

    return {"findings": [
        {"person": person, "state": state, "history_state": history, "selection_action": action, "finding": "X"}
        for person, (state, history, action) in states.items()
    ]}


# ----------------------------------------------------------------------------- the starters check


def test_the_starters_check_names_every_team_and_why_a_starter_is_not_scored(tmp_path):
    slate = _slate(tmp_path)
    starters = {team: f"{team}|QB|{team} QB One" for team in ("NE", "SEA", "DAL")}  # PHI is not declared
    coverage = _coverage(slate, **{starters["DAL"]: ("DK_STATUS_UNAVAILABLE:OUT", "OUT")})
    prior = {person: 15.0 for person in starters.values() if person != starters["DAL"]}
    check = cj.starters_check(
        slate, qb_depth_report={"schema_version": "x", "starters_by_team": starters},
        pool_coverage=coverage, prior_points=prior)

    by_team = {row["team"]: row for row in check["starters"]}
    assert set(by_team) == {"NE", "SEA", "DAL"} and check["unevaluated_teams"] == ["PHI"]
    assert by_team["NE"]["scored"] and by_team["NE"]["selectable"] and by_team["NE"]["prior_points"] == 15.0
    assert by_team["DAL"]["scored"] is False and by_team["DAL"]["selectable"] is False
    assert by_team["DAL"]["reason"] == "DK_STATUS_UNAVAILABLE:OUT" and by_team["DAL"]["dk_status"] == "OUT"
    assert [row["team"] for row in check["missing_from_scored_pool"]] == ["DAL"]
    assert check["evidence"] == "SUPPLIED" and "OFFICIAL_ACTIVE_STATUS" in check["does_not_establish"]


def test_a_promoted_backup_is_the_starter_and_the_out_starter_is_not_named(tmp_path):
    slate = _slate(tmp_path)
    backup, hurt = "NE|QB|NE QB Two", "NE|QB|NE QB One"
    check = cj.starters_check(
        slate,
        qb_depth_report={
            "schema_version": "x", "starters_by_team": {"NE": backup},
            "effective_starter_promotions": [{"team": "NE", "published_starter": hurt, "effective_starter": backup,
                                              "promoted_over": [hurt]}]},
        pool_coverage=_coverage(slate, **{hurt: ("DK_STATUS_UNAVAILABLE:OUT", "OUT")}),
        prior_points={backup: 12.0})
    row = check["starters"][0]
    assert row["person"] == backup and row["selectable"] and row["promoted_over"] == [hurt]
    assert hurt not in {item["person"] for item in check["starters"]}
    assert check["missing_from_scored_pool"] == []


def test_without_depth_evidence_every_quarterback_team_is_unevaluated_and_nobody_is_guessed(tmp_path):
    slate = _slate(tmp_path)
    check = cj.starters_check(
        slate, qb_depth_report={"schema_version": None, "starters_by_team": {}},
        pool_coverage=_coverage(slate), prior_points={})
    assert check["evidence"] == "NOT_SUPPLIED" and check["starters"] == []
    assert check["unevaluated_teams"] == ["DAL", "NE", "PHI", "SEA"]


def test_a_starter_the_role_gate_left_out_is_named_missing_with_his_reason(tmp_path):
    """A starter the pool could not score is named with why, never rostered around and left unsaid."""

    slate = _slate(tmp_path)
    check = cj.starters_check(
        slate, qb_depth_report={"schema_version": "x", "starters_by_team": {"NE": "NE|QB|NE QB One"}},
        pool_coverage=_coverage(slate, **{"NE|QB|NE QB One": (
            "OFFENSIVE_ROLE_GATE_EXCLUDED:OFFENSIVE_UNRESOLVED_MATERIAL_ROLE_CHANGE", "")}),
        prior_points={})
    (missing,) = check["missing_from_scored_pool"]
    assert missing["reason"].endswith("OFFENSIVE_UNRESOLVED_MATERIAL_ROLE_CHANGE") and missing["prior_points"] is None


# ----------------------------------------------------------------------------- the injury rooms


def _ne_room():
    """NE's running back room: One is out and Two inherits."""

    return [
        _move("NE", "RB", "carry_share", [(NE_ONE, 0.60)], [(NE_TWO, 0.20, 0.80)], 0.60),
        _move("NE", "RB", "target_share", [(NE_ONE, 0.10)], [(NE_TWO, 0.05, 0.15)], 0.10),
    ]


def test_an_injury_room_reports_who_vacated_who_inherits_before_and_after_and_salary(tmp_path):
    slate = _slate(tmp_path)
    rooms = cj.injury_rooms(
        slate, redistribution=_redistribution(_ne_room()), prior_before={NE_TWO: 3.5}, prior_after={NE_TWO: 9.25},
        offensive_report=_findings(**{NE_TWO: ("CURRENT_ROLE_UNKNOWN", "OBSERVED_HISTORY", "DIAGNOSTIC")}),
        pool_coverage=_coverage(slate, **{NE_ONE: ("DK_STATUS_UNAVAILABLE:OUT", "OUT")}))

    (room,) = rooms["rooms"]
    assert (room["team"], room["position"]) == ("NE", "RB")
    (vacated,) = room["vacated"]
    assert vacated["person"] == NE_ONE and vacated["dk_status"] == "OUT"
    assert vacated["triggered_by"] == ["DK_STATUS_UNAVAILABLE"]
    assert vacated["share_by_field"] == {"carry_share": 0.6, "target_share": 0.1}
    assert room["vacated_total_by_field"] == {"carry_share": 0.6, "target_share": 0.1}
    (heir,) = room["inheritors"]
    assert heir["person"] == NE_TWO and heir["salary"] == next(p.salary for p in slate.players if p.underlying_id == NE_TWO)
    assert heir["share_gained_by_field"] == {"carry_share": 0.6, "target_share": 0.1}
    assert (heir["prior_points_before"], heir["prior_points_after"]) == (3.5, 9.25)
    assert heir["repriced_by_redistribution"] is True and heir["history_state"] == "OBSERVED_HISTORY"
    assert rooms["prior_points_before_basis"].startswith("SAME_SCORING_PIPELINE")


def test_a_before_the_run_could_not_compute_is_never_invented(tmp_path):
    slate = _slate(tmp_path)
    rooms = cj.injury_rooms(
        slate, redistribution=_redistribution(_ne_room()), prior_before=None, prior_after={NE_TWO: 9.25},
        offensive_report=_findings(), pool_coverage=_coverage(slate))
    (heir,) = rooms["rooms"][0]["inheritors"]
    assert heir["prior_points_before"] is None and heir["repriced_by_redistribution"] is False
    assert rooms["prior_points_before_basis"].startswith("NOT_COMPUTED")


def test_an_unresolved_role_person_is_named_as_not_inheriting_with_his_history_state(tmp_path):
    """Session 60's planning note: a transfer (Jennings, Ertz) never absorbs, and his prior is the old role's."""

    slate = _slate(tmp_path)
    transfer = NE_TWO  # the room's other survivor is the unresolved one
    rooms = cj.injury_rooms(
        slate,
        redistribution=_redistribution(
            [_move("NE", "RB", "carry_share", [(NE_ONE, 0.6)], [], 0.6, unallocated=0.6)], unresolved=[transfer]),
        prior_before=None, prior_after={transfer: 0.3},
        offensive_report=_findings(**{transfer: ("TRANSFER_PRIOR_UNVERIFIED", "CURRENT_ROLE_UNKNOWN", "DIAGNOSTIC")}),
        pool_coverage=_coverage(slate))
    (room,) = rooms["rooms"]
    assert room["inheritors"] == []
    (entry,) = room["not_inheriting_unresolved_role"]
    assert entry["person"] == transfer and entry["history_state"] == "CURRENT_ROLE_UNKNOWN"
    assert entry["prior_points"] == 0.3 and "OLD_ROLE" in entry["why"]
    assert room["unallocated_by_field"] == {"carry_share": 0.6}


# ----------------------------------------------------------------------------- the candidates


def _candidate_inputs(slate):
    """NE: One out, Two inherits (repriced). SEA: a receiver out, Three (a transfer) does not inherit."""

    moves = [
        _move("NE", "RB", "carry_share", [(NE_ONE, 0.6)], [(NE_TWO, 0.2, 0.8)], 0.6),
        _move("SEA", "WR", "target_share", [(SEA_WR_ONE, 0.25)], [], 0.25, unallocated=0.25),
    ]
    redistribution = _redistribution(moves, unresolved=[SEA_WR_THREE])
    findings = _findings(**{
        NE_TWO: ("CURRENT_ROLE_UNKNOWN", "OBSERVED_HISTORY", "DIAGNOSTIC"),
        SEA_WR_THREE: ("TRANSFER_PRIOR_UNVERIFIED", "CURRENT_ROLE_UNKNOWN", "DIAGNOSTIC"),
    })
    coverage = _coverage(
        slate, **{NE_ONE: ("DK_STATUS_UNAVAILABLE:OUT", "OUT"), SEA_WR_ONE: ("DK_STATUS_UNAVAILABLE:IR", "IR")})
    return redistribution, findings, coverage


def _candidates(slate, redistribution, findings, coverage, *, divergence=(), before=None,
                after=None):
    after = {NE_TWO: 9.0, SEA_WR_THREE: 0.3} if after is None else after
    rooms = cj.injury_rooms(
        slate, redistribution=redistribution, prior_before=before, prior_after=after,
        offensive_report=findings, pool_coverage=coverage)
    return cj.candidates(
        slate, rooms=rooms, offensive_report=findings, divergence=divergence, prior_before=before,
        prior_after=after, pool_coverage=coverage)


def test_the_candidates_rank_the_unresolved_room_person_first_and_carry_no_number_of_their_own(tmp_path):
    slate = _slate(tmp_path)
    redistribution, findings, coverage = _candidate_inputs(slate)
    result = _candidates(slate, redistribution, findings, coverage, before={NE_TWO: 3.0})

    ranked = result["candidates"]
    assert [row["person"] for row in ranked] == [SEA_WR_THREE, NE_TWO]
    assert [row["rank"] for row in ranked] == [1, 2]
    first, second = ranked
    assert first["sources"] == [cj.SOURCE_UNRESOLVED_IN_VACATED_ROOM, cj.SOURCE_UNRESOLVED_TRANSFER]
    assert first["history_state"] == "CURRENT_ROLE_UNKNOWN" and first["repriced_by_redistribution"] is False
    assert first["prior_points_after"] == 0.3 and first["room_vacated_names"] == ["SEA WR One"]
    assert second["sources"] == [cj.SOURCE_ABSORBER] and second["repriced_by_redistribution"] is True
    assert (second["prior_points_before"], second["prior_points_after"]) == (3.0, 9.0)
    assert second["room_vacated_touch_share"] == 0.6 and first["room_vacated_touch_share"] == 0.25
    assert "unresolved" in first["research"] and "SEA WR One" in first["research"]
    # It is a list for research: it says so, writes no projection, and the only points in it are the pool's own.
    assert result["kind"] == "FOR_THE_AGENTS_RESEARCH_NOT_A_SELECTION"
    assert "ANY_PROJECTION_EXPECTED_VALUE_OR_WIN_PROBABILITY" in result["does_not_establish"]
    assert "DEPTH_RANK_ONE_AT_POSITION" in result["sources_unevaluated"]
    assert all(row["placeable"] and row["placement"] == "IN_THE_SCORED_POOL" for row in ranked)


def test_a_person_nothing_can_place_is_not_listed_and_a_role_gate_exclusion_is_not_placeable(tmp_path):
    slate = _slate(tmp_path)
    redistribution, findings, _coverage_unused = _candidate_inputs(slate)
    # NE RB Two inherits the vacated share on the run's bytes and is on an official INACTIVE row:
    # nothing can place him, so he is not a candidate, and the report says why he is missing.
    coverage = _coverage(slate, **{
        NE_ONE: ("DK_STATUS_UNAVAILABLE:OUT", "OUT"), SEA_WR_ONE: ("DK_STATUS_UNAVAILABLE:IR", "IR"),
        SEA_WR_THREE: ("OFFENSIVE_ROLE_GATE_EXCLUDED:OFFENSIVE_MISSING_HISTORY", ""),
        NE_TWO: ("OFFICIAL_INACTIVE", ""), "DAL|WR|DAL WR One": ("DK_STATUS_UNAVAILABLE:OUT", "OUT")})
    result = _candidates(
        slate, redistribution, findings, coverage,
        divergence=[{"person": "DAL|WR|DAL WR One", "position": "WR", "divergence_places": 20, "name": "DAL WR One"}])
    by_person = {row["person"]: row for row in result["candidates"]}
    assert NE_TWO not in by_person and NE_ONE not in by_person
    assert result["not_listed_because_nothing_can_place_them"][NE_TWO] == "OFFICIAL_INACTIVE"
    assert "DAL|WR|DAL WR One" not in {row["person"] for row in result["priced_above_prior_only"]}
    gated = by_person[SEA_WR_THREE]
    assert gated["placeable"] is False
    assert gated["placement"] == "OFFENSIVE_ROLE_GATE_EXCLUDED:OFFENSIVE_MISSING_HISTORY"


def test_a_salary_far_above_the_prior_is_a_tag_on_a_candidate_and_a_short_list_of_its_own(tmp_path):
    slate = _slate(tmp_path)
    redistribution, findings, coverage = _candidate_inputs(slate)
    others = [p for p in slate.players
              if p.position in {"WR", "TE", "RB"} and p.underlying_id not in {NE_TWO, NE_ONE, SEA_WR_ONE, SEA_WR_THREE}][:14]
    divergence = [
        {"person": NE_TWO, "position": "RB", "divergence_places": 3, "name": "NE RB Two", "salary": 1},
        {"person": "PHI|DST|PHI DST One", "position": "DST", "divergence_places": 99, "name": "PHI DST One"},
        *({"person": p.underlying_id, "position": p.position, "divergence_places": 40 - i, "name": p.name,
           "salary": p.salary, "dk_id": p.dk_id, "team": p.team, "prior_points": 1.0, "history_state": "OBSERVED_HISTORY"}
          for i, p in enumerate(others)),
    ]
    result = _candidates(slate, redistribution, findings, coverage, divergence=divergence)
    absorber = next(row for row in result["candidates"] if row["person"] == NE_TWO)
    assert absorber["sources"] == [cj.SOURCE_ABSORBER, cj.SOURCE_SALARY_ABOVE_PRIOR]
    assert absorber["salary_rank_divergence_places"] == 3
    short = result["priced_above_prior_only"]
    assert len(short) == cj.PRICED_ABOVE_PRIOR_LIMIT
    assert all(row["position"] != "DST" for row in short)
    assert [row["divergence_places"] for row in short] == sorted((r["divergence_places"] for r in short), reverse=True)
    assert not ({row["person"] for row in short} & {row["person"] for row in result["candidates"]})


def test_the_candidate_order_is_deterministic_under_any_input_order(tmp_path):
    slate = _slate(tmp_path)
    redistribution, findings, coverage = _candidate_inputs(slate)
    reordered = {**redistribution, "moves": list(reversed(redistribution["moves"]))}
    forward = _candidates(slate, redistribution, findings, coverage)
    backward = _candidates(slate, reordered, findings, coverage)
    assert json.dumps(forward, sort_keys=True) == json.dumps(backward, sort_keys=True)


# ----------------------------------------------------------------------------- the late-swap watch list


def _roster(slate, *names):
    by_name = {p.name: p.dk_id for p in slate.players}
    return SimpleNamespace(roster=tuple(by_name[name] for name in names))


def test_the_watch_list_is_the_later_window_without_a_row_and_leaves_the_early_gap_named(tmp_path):
    slate = _slate(tmp_path)
    early = {p.lock_at for p in slate.players if p.team == "NE"}
    later = {p.lock_at for p in slate.players if p.team == "DAL"}
    assert max(early) < min(later)  # NE@SEA kicks off at 1:00 and DAL@PHI at 4:25
    lineups = [
        _roster(slate, "NE QB One", "NE RB One", "DAL QB One", "DAL WR One", "PHI TE One"),
        _roster(slate, "NE QB One", "SEA WR One", "DAL QB One", "PHI TE One"),
    ]
    status = {p.dk_id: "ACTIVE" for p in slate.players if p.name == "NE QB One"}
    coverage = _coverage(slate, **{_person(slate, "DAL WR One"): ("SELECTABLE", "Q")})
    watch = cj.late_swap_watch(slate, lineups=lineups, pool_coverage=coverage, official_statuses=status)

    rows = watch["later_window_without_official_row"]
    assert [row["name"] for row in rows] == ["DAL QB One", "PHI TE One", "DAL WR One"]  # lock, rows held, name
    assert rows[0]["rows"] == 2 and rows[0]["dk_status"] == ""
    assert next(row for row in rows if row["name"] == "DAL WR One")["dk_status"] == "Q"
    assert [row["name"] for row in watch["early_window_without_official_row"]] == ["NE RB One", "SEA WR One"]
    assert watch["kind"] == "LATE_SWAP_WATCH_LIST_NOT_A_BLOCKER" and "OFFICIAL_STATUS_*" in watch["note"]
    assert "NE QB One" not in {row["name"] for row in rows}  # he has an official row


def test_a_slate_with_one_window_has_an_empty_watch_list(tmp_path):
    slate = _slate(tmp_path)
    one_window = [_roster(slate, "NE QB One", "SEA WR One")]
    watch = cj.late_swap_watch(slate, lineups=one_window, pool_coverage=_coverage(slate), official_statuses={})
    assert watch["later_window_without_official_row"] == []
    assert {row["name"] for row in watch["early_window_without_official_row"]} == {"NE QB One", "SEA WR One"}


# ----------------------------------------------------------------------------- the pass is pure


def test_the_pass_is_deterministic_and_never_mutates_what_it_reads(tmp_path):
    slate = _slate(tmp_path)
    redistribution, findings, coverage = _candidate_inputs(slate)
    selection = {
        "offensive_roles": findings,
        "qb_depth_roles": {"schema_version": None, "starters_by_team": {}},
        "prior_points_before_redistribution": {NE_TWO: 3.0},
        "salary_rank_divergence": {"findings": []},
    }
    prior = {NE_TWO: 9.0, SEA_WR_THREE: 0.3}
    snapshot = copy.deepcopy((redistribution, coverage, selection, prior))
    kwargs = dict(lineups=[_roster(slate, "NE QB One", "DAL QB One")], selection=selection, prior_points=prior,
                  redistribution=redistribution, pool_coverage=coverage, official_statuses={})
    first, second = cj.build_judgment_pass(slate, **kwargs), cj.build_judgment_pass(slate, **kwargs)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert (redistribution, coverage, selection, prior) == snapshot
    assert first["version"] == cj.JUDGMENT_PASS_VERSION
    assert set(first) == {"version", "protected_people", "starters_check", "injury_rooms", "candidates",
                          "late_swap_watch", "does_not_establish"}
    assert first["protected_people"] == []


# ----------------------------------------------------------------------------- end to end


def _salary_with(depth, out_statuses):
    original = classic._salary_bytes

    def with_status(**kwargs):
        rows = list(csv.reader(io.StringIO(original(**{**kwargs, "depth": depth}).decode("utf-8"))))
        name_at, status_at = rows[0].index("Name"), rows[0].index("Status")
        for row in rows[1:]:
            if row[name_at] in out_statuses:
                row[status_at] = out_statuses[row[name_at]]
        buffer = io.StringIO(newline="")
        csv.writer(buffer, lineterminator="\n").writerows(rows)
        return buffer.getvalue().encode("utf-8")

    return with_status


def _classic_run(tmp_path, monkeypatch, *, out=None, depth=DEPTH, depth_package=None, official=False, **kwargs):
    monkeypatch.setattr(classic, "_salary_bytes", _salary_with(depth, dict(out or {})))
    salary, entry, package, _role, status, _inactive = classic._fixture(tmp_path, depth=depth)
    if depth_package is not None:
        depth_package = depth_package(tmp_path, parse_salaries(salary))
    outcome = run_prior_review(
        salary_csv=salary, entry_csv=entry, label="classic-judgment", as_of=classic.AS_OF,
        run_root=tmp_path / "run", output_root=tmp_path / "out", prior_package_dir=package,
        qb_depth_role_evidence_json=depth_package, official_status_csv=status if official else None, **kwargs)
    assert not outcome.blocked, outcome.blockers
    coverage = json.loads(Path(outcome.artifacts["complete_slate_coverage"]).read_text(encoding="utf-8"))
    return outcome, coverage, parse_salaries(salary)


def _qb_package(tmp_path_, slate, *, starters=None):
    """A Classic QB depth package: each team's rank 1 is its alphabetically first QB unless `starters` says otherwise."""

    root = Path(tmp_path_) / "qb_depth"
    (root / "sources").mkdir(parents=True, exist_ok=True)
    observed = classic.AS_OF - timedelta(hours=6)
    quarterbacks: dict[str, list] = {}
    for player in slate.players:
        if player.position == "QB":
            quarterbacks.setdefault(player.team, []).append(player)
    sources, declarations = [], []
    for index, (team, rows) in enumerate(sorted(quarterbacks.items())):
        rows = sorted(rows, key=lambda p: p.name)
        first = (starters or {}).get(team)
        if first:
            rows.sort(key=lambda p: p.name != first)
        ids = {p.name: f"00-{9000000 + 10 * index + n}" for n, p in enumerate(rows)}
        qb_depth._GSIS.update(ids)
        excerpt = qb_depth._excerpt(team, [p.name for p in rows], observed)
        digest = sha256_bytes(excerpt.encode("utf-8"))
        (root / "sources" / f"{digest}.csv").write_bytes(excerpt.encode("utf-8"))
        sources.append({
            "path": f"sources/{digest}.csv", "sha256": digest,
            "source_uri": "https://github.com/nflverse/nflverse-data/releases/download/depth_charts/depth_charts_2026.csv",
            "observed_at": observed.isoformat(), "captured_at": (observed + timedelta(minutes=5)).isoformat(),
            "expires_at": (observed + timedelta(hours=36)).isoformat(),
            "license_decision": "PERMITTED_REPOSITORY_LICENSE", "parser_version": "nflverse_depth_charts_csv_v1",
            "transformation_version": TRANSFORMATION_VERSION, "support_kind": "DEPTH_CHART_ORDER",
            "supporting_excerpt": excerpt, "synthetic": True,
            "upstream_sha256": sha256_bytes(b"upstream-depth-chart-2026"),
        })
        entries = [{"underlying_id": p.underlying_id, "dk_id": p.dk_id, "provider_player_id": ids[p.name],
                    "player_name": p.name, "pos_rank": rank} for rank, p in enumerate(rows, start=1)]
        declarations.append({
            "team": team, "game_id": rows[0].game_id, "declared_observed_at": observed.isoformat(),
            "starter": entries[0], "backups": entries[1:], "unlisted": [], "source_sha256": digest})
    path = root / "qb_depth_roles.json"
    path.write_text(json.dumps({
        "schema_version": SCHEMA_VERSION, "allocation_version": ALLOCATION_VERSION,
        "transformation_version": TRANSFORMATION_VERSION, "salary_sha256": slate.salary_hash,
        "game_ids": sorted({game.game_id for game in slate.games}), "sources": sources,
        "declarations": declarations}, sort_keys=True), encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def _restore_gsis(monkeypatch):
    monkeypatch.setattr(qb_depth, "_GSIS", dict(qb_depth._GSIS))


def test_a_classic_run_carries_the_pass_in_the_coverage_artifact_and_moves_no_release_truth(tmp_path, monkeypatch):
    outcome, coverage, slate = _classic_run(tmp_path, monkeypatch, out={"NE RB One": "OUT"})
    block = coverage["judgment_pass"]
    assert block["version"] == cj.JUDGMENT_PASS_VERSION
    assert coverage["MODEL_STATUS"] == "PRIOR_ONLY" and coverage["RELEASE_DECISION"] == "DO_NOT_UPLOAD"
    (room,) = block["injury_rooms"]["rooms"]
    assert (room["team"], room["position"]) == ("NE", "RB")
    assert [row["name"] for row in room["vacated"]] == ["NE RB One"] and room["vacated"][0]["dk_status"] == "OUT"
    heirs = {row["person"]: row for row in room["inheritors"]}
    assert NE_TWO in heirs
    heir = heirs[NE_TWO]
    assert heir["prior_points_before"] is not None and heir["prior_points_after"] > heir["prior_points_before"]
    assert heir["repriced_by_redistribution"] is True
    assert heir["salary"] == next(p.salary for p in slate.players if p.underlying_id == NE_TWO)
    assert block["candidates"]["candidates"][0]["person"] == NE_TWO
    assert block["starters_check"]["evidence"] == "NOT_SUPPLIED"
    # the same object is the in-memory report
    assert outcome.reports["selection"]["judgment_pass"] == block
    selection = outcome.reports["selection"]["selection"]
    assert selection["prior_points_before_redistribution_note"] == "SCORED"
    # Only a scored person has a before: the vacating back is out of the pool, so Two is the one it names.
    assert set(selection["prior_points_before_redistribution"]) == {NE_TWO}


def test_a_run_with_nobody_out_reports_no_rooms_and_no_counterfactual(tmp_path, monkeypatch):
    outcome, coverage, _slate_unused = _classic_run(tmp_path, monkeypatch)
    block = coverage["judgment_pass"]
    assert block["injury_rooms"]["rooms"] == [] and block["injury_rooms"]["applied"] is False
    selection = outcome.reports["selection"]["selection"]
    assert selection["prior_points_before_redistribution"] is None
    assert selection["prior_points_before_redistribution_note"] == "NOTHING_MOVED"


def test_the_watch_list_rides_the_run_and_the_official_status_codes_are_untouched(tmp_path, monkeypatch):
    """No official file at all: the later window is the watch list, the early window the open gap, and nothing moved."""

    outcome, coverage, slate = _classic_run(tmp_path, monkeypatch)
    watch = coverage["judgment_pass"]["late_swap_watch"]
    assert watch["earliest_lock_at"] == min(p.lock_at for p in slate.players).isoformat()
    by_id = {p.dk_id: p for p in slate.players}
    rostered = {by_id[d].underlying_id for lineup in outcome.reports["selection"]["lineups"] for d in lineup["roster"]}
    later = {row["person"] for row in watch["later_window_without_official_row"]}
    early = {row["person"] for row in watch["early_window_without_official_row"]}
    assert later == {p.underlying_id for p in slate.players if p.underlying_id in rostered and p.team in {"DAL", "PHI"}}
    assert early == {p.underlying_id for p in slate.players if p.underlying_id in rostered and p.team in {"NE", "SEA"}}
    assert later and early and not later & early
    assert coverage["official_status_coverage"] is None  # no official file: the existing coverage block is as before


def test_with_an_official_row_for_everyone_both_lists_are_empty_and_the_coverage_says_the_same(tmp_path, monkeypatch):
    outcome, coverage, _slate_unused = _classic_run(tmp_path, monkeypatch, official=True)
    watch = coverage["judgment_pass"]["late_swap_watch"]
    assert watch["later_window_without_official_row"] == [] and watch["early_window_without_official_row"] == []
    assert coverage["official_status_coverage"]["selected_without_row"] == []


def test_a_supplied_depth_package_makes_the_starters_check_name_every_team_scored(tmp_path, monkeypatch):
    outcome, coverage, slate = _classic_run(tmp_path, monkeypatch, depth_package=_qb_package)
    check = coverage["judgment_pass"]["starters_check"]
    assert check["evidence"] == "SUPPLIED" and check["unevaluated_teams"] == []
    assert {row["team"] for row in check["starters"]} == {"DAL", "NE", "PHI", "SEA"}
    assert all(row["scored"] and row["selectable"] and row["name"].endswith("QB One") for row in check["starters"])
    assert check["missing_from_scored_pool"] == []


def test_a_backup_quarterback_leaves_every_classic_row_and_the_default_is_reported(tmp_path, monkeypatch):
    outcome, coverage, slate = _classic_run(tmp_path, monkeypatch, depth_package=_qb_package)
    default = outcome.reports["selection"]["selection"]["classic_backup_qb_default"]
    backups = {p.underlying_id for p in slate.players if p.position == "QB" and p.name.endswith("QB Two")}
    assert default["applies"] is True and set(default["excluded_people"]) == backups
    assert default["unevaluated_teams"] == [] and default["readmitted_by_a_named_choice"] == []
    assert outcome.reports["selection"]["selection"]["showdown_backup_qb_default"]["applies"] is False
    rostered = {d for lineup in outcome.reports["selection"]["lineups"] for d in lineup["roster"]}
    assert not rostered & {p.dk_id for p in slate.players if p.underlying_id in backups}


def test_a_run_with_no_depth_package_names_every_team_unevaluated_and_excludes_nobody(tmp_path, monkeypatch):
    outcome, _coverage_unused, _slate_unused = _classic_run(tmp_path, monkeypatch)
    default = outcome.reports["selection"]["selection"]["classic_backup_qb_default"]
    assert default["applies"] is True and default["excluded_people"] == []
    assert default["unevaluated_teams"] == ["DAL", "NE", "PHI", "SEA"]


def test_a_promoted_backup_is_not_excluded_and_the_out_starter_is(tmp_path, monkeypatch):
    outcome, coverage, slate = _classic_run(
        tmp_path, monkeypatch, out={"NE QB One": "OUT"}, depth_package=_qb_package)
    default = outcome.reports["selection"]["selection"]["classic_backup_qb_default"]
    ne = next(row for row in coverage["judgment_pass"]["starters_check"]["starters"] if row["team"] == "NE")
    assert ne["name"] == "NE QB Two" and ne["selectable"] and ne["promoted_over"] == ["NE|QB|NE QB One"]
    assert "NE|QB|NE QB Two" not in default["excluded_people"]
    assert coverage["judgment_pass"]["starters_check"]["missing_from_scored_pool"] == []


# ============================================================================= the construction judgment (Part B)

import hashlib  # noqa: E402

from nfl_dfs import cli  # noqa: E402
from nfl_dfs.classic_judgment import (  # noqa: E402
    CONSTRUCTION_JUDGMENT_VERSION,
    ConstructionJudgmentError,
    judge_placements,
    load_construction_judgment,
)
from nfl_dfs.gate_registry import load_gate_registry  # noqa: E402

JUDGMENT_AS_OF = classic.AS_OF
SOURCE = {"uri": "https://www.example.org/reports/ne-backfield", "observed_at": "2026-09-10T11:00:00+00:00"}


def _judgment_doc(slate, *names_and_rows, **overrides):
    by_name = {p.name: p for p in slate.players}
    placements = [
        {"dk_id": by_name[name].dk_id, "name": name, "min_rows": rows,
         "reason": "Reported the starter after the injury; the prior still prices his old role.",
         "sources": [dict(SOURCE)]}
        for name, rows in names_and_rows
    ]
    document = {
        "schema_version": CONSTRUCTION_JUDGMENT_VERSION, "salary_sha256": slate.salary_hash,
        "author": "agent:S61-test", "authored_at": "2026-09-10T11:30:00+00:00", "placements": placements,
    }
    document.update(overrides)
    return document


def _write_judgment(tmp_path, document, name="judgment.json"):
    path = Path(tmp_path) / name
    path.write_text(json.dumps(document, indent=1), encoding="utf-8")
    return path


def _load(tmp_path, slate, document, **kwargs):
    return load_construction_judgment(
        _write_judgment(tmp_path, document), slate, as_of=kwargs.pop("as_of", JUDGMENT_AS_OF))


def test_the_schema_constant_is_the_registered_literal():
    from nfl_dfs.classic_judgment import ConstructionJudgmentFile

    assert CONSTRUCTION_JUDGMENT_VERSION == "nfl_classic_construction_judgment_v1"
    assert ConstructionJudgmentFile.model_fields["schema_version"].annotation.__args__ == (CONSTRUCTION_JUDGMENT_VERSION,)


def test_a_valid_judgment_loads_bound_to_the_salary_bytes_and_its_own(tmp_path):
    slate = _slate(tmp_path)
    path = _write_judgment(tmp_path, _judgment_doc(slate, ("NE RB Two", 4)))
    judgment = load_construction_judgment(path, slate, as_of=JUDGMENT_AS_OF)
    assert judgment.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert judgment.document.salary_sha256 == slate.salary_hash
    assert judgment.person_by_dk_id == {next(p.dk_id for p in slate.players if p.name == "NE RB Two"): NE_TWO}
    report = judgment.as_report()
    assert report["author"] == "agent:S61-test" and report["placements_named"] == 1
    # the report names the file, never where this run snapshotted it (it lands in run-ID independent artifacts)
    assert report["file_name"] == "judgment.json" and "path" not in report and str(tmp_path) not in json.dumps(report)


@pytest.mark.parametrize(
    "mutation, code",
    [
        (lambda d, s: d.update(salary_sha256="0" * 64), "CONSTRUCTION_JUDGMENT_SALARY_HASH_MISMATCH"),
        (lambda d, s: d["placements"][0].update(dk_id="999999999"), "CONSTRUCTION_JUDGMENT_ID_NOT_IN_THE_SALARY_FILE"),
        (lambda d, s: d["placements"][0].update(name="NE RB One"), "CONSTRUCTION_JUDGMENT_NAME_IS_NOT_THE_ROW"),
        (lambda d, s: d.update(authored_at="2026-09-10T13:00:00+00:00"), "CONSTRUCTION_JUDGMENT_FROM_THE_FUTURE"),
        (lambda d, s: d["placements"][0]["sources"][0].update(observed_at="2026-09-10T12:30:00+00:00"),
         "CONSTRUCTION_JUDGMENT_SOURCE_FROM_THE_FUTURE"),
        (lambda d, s: d.update(schema_version="nfl_classic_construction_judgment_v2"), "CONSTRUCTION_JUDGMENT_INVALID"),
        (lambda d, s: d.update(extra_field=1), "CONSTRUCTION_JUDGMENT_INVALID"),
        (lambda d, s: d.update(author=""), "CONSTRUCTION_JUDGMENT_INVALID"),
        (lambda d, s: d.update(authored_at="2026-09-10T11:30:00"), "CONSTRUCTION_JUDGMENT_INVALID"),
        (lambda d, s: d["placements"][0].update(min_rows=0), "CONSTRUCTION_JUDGMENT_INVALID"),
        (lambda d, s: d["placements"][0].update(reason="starter"), "CONSTRUCTION_JUDGMENT_INVALID"),
        (lambda d, s: d["placements"][0].update(sources=[]), "CONSTRUCTION_JUDGMENT_INVALID"),
        (lambda d, s: d["placements"][0]["sources"][0].update(uri="http://www.example.org/x"),
         "CONSTRUCTION_JUDGMENT_INVALID"),
        (lambda d, s: d["placements"][0]["sources"][0].update(uri="https://www.draftkings.com/lineup"),
         "CONSTRUCTION_JUDGMENT_INVALID"),
        (lambda d, s: d["placements"][0]["sources"][0].update(uri="https://www.nfl.com/news/x"),
         "CONSTRUCTION_JUDGMENT_INVALID"),
        (lambda d, s: d["placements"][0]["sources"][0].update(uri="https://api.draftkings.com/lineups"),
         "CONSTRUCTION_JUDGMENT_INVALID"),
        (lambda d, s: d["placements"][0]["sources"][0].update(uri="https://static.nfl.com/news/x"),
         "CONSTRUCTION_JUDGMENT_INVALID"),
        (lambda d, s: d["placements"][0]["sources"][0].update(uri="https://example.org/" + "x" * 600),
         "CONSTRUCTION_JUDGMENT_INVALID"),
        (lambda d, s: d.update(author="a" * 81), "CONSTRUCTION_JUDGMENT_INVALID"),
        (lambda d, s: d.update(author="agent\u0007bell"), "CONSTRUCTION_JUDGMENT_INVALID"),
        (lambda d, s: d["placements"][0].update(reason="x" * 601), "CONSTRUCTION_JUDGMENT_INVALID"),
        (lambda d, s: d["placements"][0].update(reason="a plain reason with a\u0000 control character"),
         "CONSTRUCTION_JUDGMENT_INVALID"),
        (lambda d, s: d["placements"][0]["sources"][0].update(uri="https://user:pw@www.example.org/x"),
         "CONSTRUCTION_JUDGMENT_INVALID"),
        (lambda d, s: d["placements"].append(dict(d["placements"][0])), "CONSTRUCTION_JUDGMENT_INVALID"),
        (lambda d, s: d.update(placements=[]), "CONSTRUCTION_JUDGMENT_INVALID"),
    ],
)
def test_a_judgment_the_file_cannot_use_is_refused_by_a_named_code(tmp_path, mutation, code):
    slate = _slate(tmp_path)
    document = _judgment_doc(slate, ("NE RB Two", 4))
    mutation(document, slate)
    with pytest.raises(ConstructionJudgmentError) as raised:
        _load(tmp_path, slate, document)
    assert raised.value.code == code


def test_a_judgment_is_refused_at_lock_and_for_unreadable_or_changed_bytes(tmp_path):
    slate = _slate(tmp_path)
    document = _judgment_doc(slate, ("NE RB Two", 4))
    path = _write_judgment(tmp_path, document)
    earliest = min(p.lock_at for p in slate.players)
    with pytest.raises(ConstructionJudgmentError) as raised:
        load_construction_judgment(path, slate, as_of=earliest)
    assert raised.value.code == "CONSTRUCTION_JUDGMENT_EXPIRED_AT_LOCK"
    with pytest.raises(ConstructionJudgmentError) as raised:
        load_construction_judgment(Path(tmp_path) / "absent.json", slate, as_of=JUDGMENT_AS_OF)
    assert raised.value.code == "CONSTRUCTION_JUDGMENT_UNREADABLE"
    with pytest.raises(ConstructionJudgmentError) as raised:
        load_construction_judgment(path, slate, as_of=JUDGMENT_AS_OF.replace(tzinfo=None))
    assert raised.value.code == "CONSTRUCTION_JUDGMENT_CLOCK_REQUIRES_TIMEZONE"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ConstructionJudgmentError) as raised:
        load_construction_judgment(path, slate, as_of=JUDGMENT_AS_OF)
    assert raised.value.code == "CONSTRUCTION_JUDGMENT_INVALID"


def test_every_code_the_loader_can_raise_is_registered_with_the_gate_registry():
    registry = load_gate_registry()
    for code in (
        "CONSTRUCTION_JUDGMENT_SALARY_HASH_MISMATCH", "CONSTRUCTION_JUDGMENT_ID_NOT_IN_THE_SALARY_FILE",
        "CONSTRUCTION_JUDGMENT_NAME_IS_NOT_THE_ROW", "CONSTRUCTION_JUDGMENT_FROM_THE_FUTURE",
        "CONSTRUCTION_JUDGMENT_SOURCE_FROM_THE_FUTURE", "CONSTRUCTION_JUDGMENT_INVALID",
        "CONSTRUCTION_JUDGMENT_EXPIRED_AT_LOCK", "CONSTRUCTION_JUDGMENT_UNREADABLE",
        "CONSTRUCTION_JUDGMENT_CHANGED_DURING_READ", "CONSTRUCTION_JUDGMENT_CLOCK_REQUIRES_TIMEZONE",
        "CONSTRUCTION_JUDGMENT_IS_CLASSIC_ONLY", "CLASSIC_JUDGMENT_FILE_DROPPED", "CLASSIC_JUDGMENT_NOT_APPLIED",
        "CLASSIC_JUDGMENT_PLACEMENT_APPLIED", "CLASSIC_JUDGMENT_PLACEMENT_REFUSED",
        "CLASSIC_JUDGMENT_PLACEMENT_SHORTFALL", "CLASSIC_JUDGMENT_PASS_FAILED", "CLASSIC_BACKUP_QB_UNEVALUATED",
    ):
        limitation = registry.limitation(code, detail="x")
        assert limitation.code == code


# ----------------------------------------------------------------------------- the eligibility decisions


def _contract(*, unavailable=(), operator=(), statuses=None):
    return SimpleNamespace(
        status_by_person=dict(statuses or {}), unavailable_people=tuple(unavailable),
        operator_excluded_people=tuple(operator))


def _decide(tmp_path, slate, names_and_rows, *, contract=None, findings=None, gate_excluded=(), kicker=(),
            scored=None, count=20, applies=True, reason=""):
    judgment = _load(tmp_path, slate, _judgment_doc(slate, *names_and_rows))
    pool = {p.underlying_id for p in slate.players} if scored is None else set(scored)
    return judge_placements(
        judgment, slate, contract=contract or _contract(), offensive_report=findings or {"findings": []},
        offense_excluded_people=gate_excluded, kicker_zero_share_people=kicker, scored_people=pool,
        count=count, applies=applies, why_not_applied=reason)


def test_a_person_in_the_scored_pool_is_accepted_with_his_minimum_and_no_number_is_written(tmp_path):
    slate = _slate(tmp_path)
    decision = _decide(tmp_path, slate, [("NE RB Two", 4)])
    assert decision.status == "APPLIED" and dict(decision.accepted) == {NE_TWO: 4}
    report = decision.report
    assert report["number_written"] == "NONE" and report["refused"] == []
    (row,) = report["placements"]
    assert row["decision"] == "ACCEPTED" and row["sources"][0]["uri"] == SOURCE["uri"]
    assert "A_CURRENT_ROLE_OR_ANY_MODEL_VALUE_FOR_A_NAMED_PERSON" in report["does_not_establish"]
    assert not any(key in row for key in ("prior_points", "projection", "score"))


def test_a_judgment_naming_a_draftkings_out_person_is_refused_by_name(tmp_path):
    slate = _slate(tmp_path)
    decision = _decide(
        tmp_path, slate, [("NE RB One", 4), ("NE RB Two", 3)],
        contract=_contract(unavailable=[NE_ONE], statuses={NE_ONE: "OUT"}))
    assert dict(decision.accepted) == {NE_TWO: 3}
    (refused,) = decision.report["refused"]
    assert refused["name"] == "NE RB One" and refused["refusal"] == "NEVER_OVERRIDDEN:DK_STATUS_UNAVAILABLE:OUT"


@pytest.mark.parametrize(
    "setup, refusal",
    [
        (dict(contract=_contract(operator=[NE_ONE])), "NEVER_OVERRIDDEN:OPERATOR_OR_OFFICIAL_INACTIVE_EXCLUSION"),
        (dict(findings={"findings": [{"person": NE_ONE, "selection_action": "BLOCK", "finding": "X"}]}),
         "NEVER_OVERRIDDEN:X"),
        (dict(gate_excluded=[NE_ONE], findings={"findings": [{
            "person": NE_ONE, "selection_action": "EXCLUDE", "finding": "OFFENSIVE_UNRESOLVED_MATERIAL_ROLE_CHANGE",
            "material_role_change": "OFFENSIVE_UNRESOLVED_MATERIAL_ROLE_CHANGE"}]}),
         "NEVER_OVERRIDDEN:OFFENSIVE_UNRESOLVED_MATERIAL_ROLE_CHANGE"),
        (dict(gate_excluded=[NE_ONE], findings={"findings": [{
            "person": NE_ONE, "selection_action": "EXCLUDE", "finding": "OFFENSIVE_MISSING_HISTORY"}]}),
         "NOT_IN_THE_SCORED_POOL:OFFENSIVE_MISSING_HISTORY"),
        (dict(kicker=[NE_ONE]), "NOT_IN_THE_SCORED_POOL:KICKER_ROLE_ZERO_SHARE"),
        (dict(scored=[]), "NOT_IN_THE_SCORED_POOL:NO_PRIOR_ROW"),
        (dict(count=3), "MIN_ROWS_EXCEEDS_THE_ENTRIES:4>3"),
    ],
)
def test_each_thing_the_judgment_never_overrides_is_refused_by_a_named_reason(tmp_path, setup, refusal):
    slate = _slate(tmp_path)
    decision = _decide(tmp_path, slate, [("NE RB One", 4)], **setup)
    assert dict(decision.accepted) == {} and decision.status == "NO_PLACEMENT_ACCEPTED"
    assert decision.report["refused"][0]["refusal"] == refusal


def test_with_a_policy_in_force_every_placement_is_not_applied_and_says_why(tmp_path):
    slate = _slate(tmp_path)
    decision = _decide(tmp_path, slate, [("NE RB Two", 4)], applies=False, reason="A_PORTFOLIO_POLICY_IS_IN_FORCE")
    assert decision.status == "NOT_APPLIED" and dict(decision.accepted) == {}
    assert decision.report["placements"][0]["decision"] == "NOT_APPLIED"
    assert decision.report["not_applied_reason"] == "A_PORTFOLIO_POLICY_IS_IN_FORCE" and decision.report["refused"] == []


# ----------------------------------------------------------------------------- through the run


def _run_with_judgment(tmp_path, monkeypatch, names_and_rows, *, out=None, document=None, depth_package=None,
                       **kwargs):
    """A Classic run of the wide fixture with 12 entries and a judgment bound to its salary bytes."""

    wide = {"QB": 2, "RB": 3, "WR": 4, "TE": 2, "DST": 1}
    monkeypatch.setattr(classic, "_salary_bytes", _salary_with(wide, dict(out or {})))
    salary, entry, package, _role, status, _inactive = classic._fixture(tmp_path, entries=12, depth=wide)
    slate = parse_salaries(salary)
    document = document if document is not None else _judgment_doc(slate, *names_and_rows)
    (Path(tmp_path) / "judgment").mkdir(parents=True, exist_ok=True)
    path = _write_judgment(Path(tmp_path) / "judgment", document)
    outcome = run_prior_review(
        salary_csv=salary, entry_csv=entry, label="classic-judgment", as_of=classic.AS_OF,
        run_root=tmp_path / "run", output_root=tmp_path / "out", prior_package_dir=package,
        official_status_csv=status, classic_construction="THESES", construction_judgment_json=path,
        qb_depth_role_evidence_json=depth_package(tmp_path, slate) if depth_package is not None else None, **kwargs)
    assert not outcome.blocked, outcome.blockers
    coverage = json.loads(Path(outcome.artifacts["complete_slate_coverage"]).read_text(encoding="utf-8"))
    return outcome, coverage, slate


def _rows_holding(slate, outcome, person):
    by_id = {p.dk_id: p.underlying_id for p in slate.players}
    return [index for index, lineup in enumerate(outcome.reports["selection"]["lineups"], start=1)
            if person in {by_id[d] for d in lineup["roster"]}]


def test_a_judgment_named_person_sits_in_at_least_his_minimum_rows_and_the_file_stays_do_not_upload(
        tmp_path, monkeypatch):
    outcome, coverage, slate = _run_with_judgment(tmp_path, monkeypatch, [("PHI RB Three", 5)])
    person = "PHI|RB|PHI RB Three"
    rows = _rows_holding(slate, outcome, person)
    assert len(rows) >= 5
    block = outcome.reports["construction_judgment"]
    assert block["status"] == "APPLIED" and block["accepted"] == {person: 5}
    assert block["delivery"]["met"] == {person: True} and block["delivery"]["delivered_rows"][person] == rows
    assert coverage["MODEL_STATUS"] == "PRIOR_ONLY" and coverage["RELEASE_DECISION"] == "DO_NOT_UPLOAD"
    assert coverage["judgment_pass"]["protected_people"] == [{
        "person": person, "dk_id": next(p.dk_id for p in slate.players if p.underlying_id == person),
        "name": "PHI RB Three", "min_rows": 5, "delivered_rows": rows, "met": True}]
    # the hash of the file the run read is bound beside the other immutable inputs
    assert coverage["immutable_bindings"]["construction_judgment_sha256"] == outcome.hashes["construction_judgment_json"]
    assert outcome.hashes["construction_judgment_json"] == hashlib.sha256(
        Path(outcome.artifacts["construction_judgment_json"]).read_bytes()).hexdigest()
    # R29 and the stack hold whatever was placed
    keys = {tuple(sorted(lineup["roster"])) for lineup in outcome.reports["selection"]["lineups"]}
    assert len(keys) == len(outcome.reports["selection"]["lineups"]) == 12
    assert outcome.reports["selection"]["selection"]["construction"]["version"] == "classic_thesis_sequential_v2"


def test_a_candidate_the_pass_lists_can_be_placed_by_the_judgment_the_next_run(tmp_path, monkeypatch):
    """The loop the card describes: the pass names a candidate, the agent researches him, the judgment places him."""

    out = {"NE RB One": "OUT"}
    _first, coverage, _slate_one = _run_with_judgment(tmp_path / "a", monkeypatch, [("PHI RB Three", 3)], out=out)
    candidates = coverage["judgment_pass"]["candidates"]["candidates"]
    assert candidates and all(item["placeable"] for item in candidates)
    named = next(item for item in candidates if item["person"] != "PHI|RB|PHI RB Three")
    second, _coverage_two, slate_two = _run_with_judgment(tmp_path / "b", monkeypatch, [(named["name"], 4)], out=out)
    assert second.reports["construction_judgment"]["accepted"] == {named["person"]: 4}
    assert len(_rows_holding(slate_two, second, named["person"])) >= 4


def test_a_judgment_naming_a_draftkings_out_person_still_delivers_and_names_the_refusal(tmp_path, monkeypatch):
    outcome, coverage, slate = _run_with_judgment(
        tmp_path, monkeypatch, [("NE RB One", 4), ("PHI RB Three", 3)], out={"NE RB One": "OUT"})
    block = outcome.reports["construction_judgment"]
    assert block["refused"] == [{
        "dk_id": next(p.dk_id for p in slate.players if p.name == "NE RB One"), "name": "NE RB One",
        "refusal": "NEVER_OVERRIDDEN:DK_STATUS_UNAVAILABLE:OUT"}]
    assert block["accepted"] == {"PHI|RB|PHI RB Three": 3}
    assert len(_rows_holding(slate, outcome, "PHI|RB|PHI RB Three")) >= 3
    assert not _rows_holding(slate, outcome, "NE|RB|NE RB One")
    limitations = cli._classic_judgment_limitations(outcome.reports)
    assert any(item.startswith("CLASSIC_JUDGMENT_PLACEMENT_REFUSED:NE RB One") and "DK_STATUS_UNAVAILABLE:OUT" in item
               for item in limitations)
    assert any(item.startswith("CLASSIC_JUDGMENT_PLACEMENT_APPLIED:PHI RB Three (at least 3 rows)") for item in limitations)


def test_a_judgment_for_other_salary_bytes_is_dropped_by_name_and_the_run_goes_on(tmp_path, monkeypatch):
    wide = {"QB": 2, "RB": 3, "WR": 4, "TE": 2, "DST": 1}
    monkeypatch.setattr(classic, "_salary_bytes", _salary_with(wide, {}))
    document = {"schema_version": CONSTRUCTION_JUDGMENT_VERSION, "salary_sha256": "1" * 64, "author": "x",
                "authored_at": "2026-09-10T11:30:00+00:00",
                "placements": [{"dk_id": "81000001", "name": "NE QB One", "min_rows": 2,
                                "reason": "A reason of plain words.", "sources": [dict(SOURCE)]}]}
    outcome, coverage, slate = _run_with_judgment(tmp_path, monkeypatch, [], document=document)
    block = outcome.reports["construction_judgment"]
    assert block["status"] == "DROPPED" and block["code"] == "CONSTRUCTION_JUDGMENT_SALARY_HASH_MISMATCH"
    assert "construction_judgment_json" not in outcome.hashes and coverage["immutable_bindings"][
        "construction_judgment_sha256"] is None
    assert len(outcome.reports["selection"]["lineups"]) == 12
    (limitation,) = [item for item in cli._classic_judgment_limitations(outcome.reports)
                     if item.startswith("CLASSIC_JUDGMENT")]
    assert limitation.startswith("CLASSIC_JUDGMENT_FILE_DROPPED:CONSTRUCTION_JUDGMENT_SALARY_HASH_MISMATCH")


def test_a_changed_judgment_file_after_the_read_blocks_publication(tmp_path, monkeypatch):
    from nfl_dfs import prior_review

    real = prior_review.select_prior_lineups

    def mutate_then_select(*args, **kwargs):
        result = real(*args, **kwargs)
        path = Path(kwargs["construction_judgment"].path)
        path.write_text(path.read_text(encoding="utf-8") + " ", encoding="utf-8")
        return result

    monkeypatch.setattr(prior_review, "select_prior_lineups", mutate_then_select)
    wide = {"QB": 2, "RB": 3, "WR": 4, "TE": 2, "DST": 1}
    monkeypatch.setattr(classic, "_salary_bytes", _salary_with(wide, {}))
    salary, entry, package, _role, status, _inactive = classic._fixture(tmp_path, entries=12, depth=wide)
    slate = parse_salaries(salary)
    (tmp_path / "judgment").mkdir()
    path = _write_judgment(tmp_path / "judgment", _judgment_doc(slate, ("PHI RB Three", 3)))
    outcome = run_prior_review(
        salary_csv=salary, entry_csv=entry, label="classic-judgment", as_of=classic.AS_OF,
        run_root=tmp_path / "run", output_root=tmp_path / "out", prior_package_dir=package,
        official_status_csv=status, classic_construction="THESES", construction_judgment_json=path)
    assert outcome.blocked and outcome.blockers == ("CONSTRUCTION_JUDGMENT_CHANGED_BEFORE_ARTIFACT_PUBLISH",)


def test_a_showdown_run_drops_a_classic_judgment_by_name(tmp_path):
    from .test_prior_review_profile import AS_OF as SD_AS_OF, _prepared_run

    salary, entry, package, project = _prepared_run(tmp_path, expires_at=SD_AS_OF + timedelta(hours=6))
    document = {"schema_version": CONSTRUCTION_JUDGMENT_VERSION, "salary_sha256": "1" * 64, "author": "x",
                "authored_at": "2026-09-09T11:30:00+00:00",
                "placements": [{"dk_id": "1", "name": "x", "min_rows": 1, "reason": "A reason of plain words.",
                                "sources": [dict(SOURCE)]}]}
    path = _write_judgment(tmp_path, document)
    outcome = run_prior_review(
        salary_csv=salary, entry_csv=entry, label="sd", as_of=SD_AS_OF, run_root=tmp_path / "run",
        output_root=tmp_path / "out", prior_package_dir=package, project=project, construction_judgment_json=path)
    assert outcome.reports["construction_judgment"]["code"] == "CONSTRUCTION_JUDGMENT_IS_CLASSIC_ONLY"
    assert not outcome.blocked, outcome.blockers


def test_with_a_policy_in_force_the_judgment_is_read_named_and_not_applied(tmp_path, monkeypatch):
    from .test_relaxation_controller import _classic, _policy_file

    def extra(attachments):
        slate = parse_salaries(attachments / "salary.csv")
        return {"construction_judgment_json": str(_write_judgment(
            attachments.parent, _judgment_doc(slate, ("NE RB One", 3))))}

    code, report, root = _classic(
        tmp_path, monkeypatch, run_id="judgment-policy", entries=3, policy=lambda attachments: _policy_file(attachments),
        extra=extra)
    assert code == 0 and report["stage"] == "PRIOR_ONLY_CLASSIC_C3_REVIEW_EXPORT", report["blockers"]
    limitations = {item["code"]: item["detail"] for item in report["release_truths"]["delivery_limitations"]}
    assert limitations["CLASSIC_JUDGMENT_NOT_APPLIED"].startswith(
        "CLASSIC_JUDGMENT_NOT_APPLIED:A_PORTFOLIO_POLICY_IS_IN_FORCE")
    assert "CLASSIC_JUDGMENT_PLACEMENT_APPLIED" not in limitations
    assert report["RELEASE_DECISION"] == "DO_NOT_UPLOAD" and report["MODEL_STATUS"] == "PRIOR_ONLY"


def test_a_run_slate_run_places_the_person_and_carries_the_limitations_in_the_result(tmp_path, monkeypatch):
    from .test_relaxation_controller import _classic

    wide = {"QB": 2, "RB": 3, "WR": 4, "TE": 2, "DST": 1}
    holder = {}

    def extra(attachments):
        slate = parse_salaries(attachments / "salary.csv")
        holder["slate"] = slate
        return {"construction_judgment_json": str(_write_judgment(
            attachments.parent, _judgment_doc(slate, ("PHI RB Three", 4), ("NE RB One", 2))))}

    code, report, root = _classic(
        tmp_path, monkeypatch, run_id="judgment-run", entries=10, policy=None, depth=wide, extra=extra)
    assert code == 0, report["blockers"]
    codes = {item["code"] for item in report["release_truths"]["delivery_limitations"]}
    assert "CLASSIC_JUDGMENT_PLACEMENT_APPLIED" in codes
    from .test_relaxation_controller import _exported_rosters

    by_id = {p.dk_id: p.underlying_id for p in holder["slate"].players}
    rosters = _exported_rosters(report)
    held = [roster for roster in rosters if "PHI|RB|PHI RB Three" in {by_id[d] for d in roster}]
    assert len(held) >= 4 and report["RELEASE_DECISION"] == "DO_NOT_UPLOAD"


# ----------------------------------------------------------------------------- the handoff text


def _script():
    import importlib.util

    path = Path(__file__).resolve().parents[1] / "scripts" / "judgment_pass_report.py"
    spec = importlib.util.spec_from_file_location("judgment_pass_report", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_handoff_text_names_every_block_and_adds_nothing(tmp_path, monkeypatch):
    outcome, coverage, slate = _classic_run(
        tmp_path, monkeypatch, out={"NE RB One": "OUT"}, depth_package=_qb_package)
    text = cj.render_judgment_pass_text(coverage["judgment_pass"], coverage["construction_judgment"])
    for heading in ("## Starting quarterbacks", "## Injury rooms", "## Candidates to research (not a selection)",
                    "## Late-swap watch list (not a blocker)"):
        assert heading in text
    assert "NE RB One (OUT" in text and "NE RB Two" in text and "repriced" in text
    assert "writes no model value" in text
    # no figure appears that the report does not carry: every number in a candidate line is the report's
    for row in coverage["judgment_pass"]["candidates"]["candidates"]:
        assert f"${row['salary']}" in text and f"prior {row['prior_points_before']} to {row['prior_points_after']}" in text
    assert cj.render_judgment_pass_text({"status": "FAILED", "error": "boom"}).startswith("Classic judgment pass did not run")


def test_the_script_prints_the_pass_from_a_coverage_artifact_and_a_run_result(tmp_path, monkeypatch, capsys):
    outcome, coverage, slate = _classic_run(tmp_path, monkeypatch, out={"NE RB One": "OUT"})
    script = _script()
    coverage_path = Path(outcome.artifacts["complete_slate_coverage"])
    assert script.main([str(coverage_path)]) == 0
    from_coverage = capsys.readouterr().out
    assert "## Injury rooms" in from_coverage and "NE RB Two" in from_coverage
    result = Path(tmp_path) / "cowork_run.json"
    result.write_text(json.dumps({"prior_review_reports": json.loads(json.dumps(
        outcome.reports, default=str))}), encoding="utf-8")
    assert script.main([str(result)]) == 0
    assert capsys.readouterr().out == from_coverage
    assert script.main([str(coverage_path), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["judgment_pass"]["version"] == cj.JUDGMENT_PASS_VERSION
    other = Path(tmp_path) / "other.json"
    other.write_text("{}", encoding="utf-8")
    assert script.main([str(other)]) == 2


def test_a_judgment_may_keep_a_depth_listed_backup_in_the_pool_and_place_him_the_same_day_case(tmp_path, monkeypatch):
    """Keenum's shape: the depth chart lists him behind a starter, the agent's research says he starts.

    A named choice readmits him past the backup default (and the report says so); every other backup stays out.
    Nothing is overridden that says he is not playing: he is in the scored pool, and a person the gate left out is refused.
    """

    outcome, coverage, slate = _run_with_judgment(
        tmp_path, monkeypatch, [("NE QB Two", 3)], depth_package=_qb_package)
    person = "NE|QB|NE QB Two"
    default = outcome.reports["selection"]["selection"]["classic_backup_qb_default"]
    assert default["readmitted_by_a_named_choice"] == [person]
    assert set(default["excluded_people"]) == {"DAL|QB|DAL QB Two", "PHI|QB|PHI QB Two", "SEA|QB|SEA QB Two"}
    block = outcome.reports["construction_judgment"]
    assert block["status"] == "APPLIED" and block["accepted"] == {person: 3}
    rows = _rows_holding(slate, outcome, person)
    assert len(rows) >= 3 and block["delivery"]["met"] == {person: True}
    # every row he sits in has him as the lineup's only quarterback, on his own team's thesis
    tags = outcome.reports["selection"]["selection"]["construction"]["lineup_theses"]
    assert all(tags[str(index)] == "STACK_NE" for index in rows)
    assert coverage["RELEASE_DECISION"] == "DO_NOT_UPLOAD"


def test_a_host_that_only_looks_like_a_prohibited_one_is_not_refused(tmp_path):
    slate = _slate(tmp_path)
    document = _judgment_doc(slate, ("NE RB Two", 4))
    document["placements"][0]["sources"][0]["uri"] = "https://notdraftkings.com.example.org/x"
    assert _load(tmp_path, slate, document).sha256


def test_a_reason_of_several_lines_is_kept_as_one_plain_line(tmp_path):
    slate = _slate(tmp_path)
    document = _judgment_doc(slate, ("NE RB Two", 4))
    document["placements"][0]["reason"] = "Reported the starter after the injury\n  and the prior still prices\this old role."
    (placement,) = _load(tmp_path, slate, document).document.placements
    assert placement.reason == "Reported the starter after the injury and the prior still prices his old role."


def test_the_coverage_artifact_is_run_id_independent_with_a_judgment_and_with_a_dropped_one(tmp_path, monkeypatch):
    """`_write_canonical_json` promises run-ID independent bytes: the snapshot path must not reach them."""

    def coverage_bytes(root, dropped):
        if dropped:
            document = {"schema_version": CONSTRUCTION_JUDGMENT_VERSION, "salary_sha256": "1" * 64, "author": "x",
                        "authored_at": "2026-09-10T11:30:00+00:00",
                        "placements": [{"dk_id": "81000001", "name": "NE QB One", "min_rows": 2,
                                        "reason": "A reason of plain words.", "sources": [dict(SOURCE)]}]}
            outcome, _coverage_unused, _slate_unused = _run_with_judgment(root, monkeypatch, [], document=document)
        else:
            outcome, _coverage_unused, _slate_unused = _run_with_judgment(root, monkeypatch, [("PHI RB Three", 3)])
        return Path(outcome.artifacts["complete_slate_coverage"]).read_bytes()

    for dropped in (False, True):
        first = coverage_bytes(tmp_path / f"a{dropped}" / "deeper" / "root", dropped)
        second = coverage_bytes(tmp_path / f"b{dropped}", dropped)
        assert first == second
        assert str(tmp_path).encode() not in first
