"""Availability contract coverage: R03 on the selection side.

Every number in these fixtures is a test input. The assertions are about who may
be selected, that both Showdown roles of a person move together, that an
unrecognized DraftKings status is refused rather than assumed available, and
that vacated opportunity reallocates within the depth chart rather than onto
whoever happens to have snap-share headroom.
"""

from __future__ import annotations

import csv
import io

import pytest

from nfl_dfs.dk import parse_salaries
from nfl_dfs.opportunity import PLAYER_COLUMNS, TEAM_COLUMNS, load_opportunity_model
from nfl_dfs.participation import (
    CONTRACT_VERSION,
    ParticipationError,
    build_participation_contract,
    capacity_data_quality,
    excluded_dk_ids,
    redistribute_opportunity,
    selectable_pool_problems,
    status_by_dk_id,
    vacated_opportunity_by_position,
)


GAME = "NE@SEA 09/09/2026 08:20PM ET"

# (team, position, name, status, flex_salary)
_POOL = (
    ("NE", "QB", "Starter QB", "", 10000),
    ("NE", "RB", "Lead RB", "", 8000),
    ("NE", "RB", "Backup RB", "", 3000),
    ("NE", "WR", "Alpha WR", "", 9000),
    ("NE", "TE", "Starting TE", "", 4000),
    ("NE", "K", "NE Kicker", "", 4600),
    ("NE", "DST", "Patriots", "", 3400),
    ("SEA", "QB", "Sea QB", "", 9400),
    ("SEA", "RB", "Sea Lead RB", "OUT", 8200),
    ("SEA", "RB", "Sea Backup RB", "", 4000),
    ("SEA", "RB", "Sea Third RB", "", 2000),
    ("SEA", "WR", "Sea Alpha WR", "", 10600),
    ("SEA", "WR", "Sea Hurt WR", "IR", 1200),
    ("SEA", "TE", "Sea TE", "Q", 4600),
    ("SEA", "K", "Sea Kicker", "", 5400),
    ("SEA", "DST", "Seahawks", "", 4400),
)


def _salary_bytes(pool=_POOL) -> bytes:
    header = (
        "Position", "Name + ID", "Name", "ID", "Roster Position", "Salary",
        "Game Info", "TeamAbbrev", "AvgPointsPerGame", "Status",
    )
    rows = []
    dk_id = 50000000
    for team, position, name, status, flex_salary in pool:
        for role, salary in (("CPT", round(flex_salary * 1.5)), ("FLEX", flex_salary)):
            dk_id += 1
            rows.append(
                (position, f"{name} ({dk_id})", name, str(dk_id), role, str(salary),
                 GAME, team, "0", status)
            )
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _slate(tmp_path, pool=_POOL):
    path = tmp_path / "DKSalaries.csv"
    path.write_bytes(_salary_bytes(pool))
    return parse_salaries(path)


_TEAM_ROW = {
    "PLAYS_MEAN": "62", "PASS_RATE": "0.55", "PASS_YARDS_PER_ATTEMPT": "7.2",
    "RUSH_YARDS_PER_ATTEMPT": "4.3", "TOUCHDOWNS_MEAN": "2.8", "FIELD_GOALS_MEAN": "1.6",
    "TURNOVERS_MEAN": "1.2", "SACKS_ALLOWED_MEAN": "2.4", "UNCERTAINTY": "0.12",
    "MARKET_TOTAL": "44.5", "MARKET_SPREAD": "3",
    "MARKET_OBSERVED_AT": "2026-09-08T12:00:00+00:00",
    "WEATHER_STATE": "CLEAR", "ERA": "2026_TEST",
}

# Shares chosen so the lead running back holds most of the carries and the
# touchdowns, which is what makes the redistribution assertions meaningful.
_SHARES = {
    "Starter QB":     dict(qb=1.0, carry=0.20, target=0.0,  catch=0.0,  ypt=0.0,  rtd=0.15, ctd=0.0,  cap=0.98),
    "Lead RB":        dict(qb=0.0, carry=0.60, target=0.10, catch=0.75, ypt=6.0,  rtd=0.65, ctd=0.10, cap=0.60),
    "Backup RB":      dict(qb=0.0, carry=0.15, target=0.05, catch=0.70, ypt=5.0,  rtd=0.15, ctd=0.05, cap=0.20),
    "Alpha WR":       dict(qb=0.0, carry=0.03, target=0.50, catch=0.65, ypt=9.0,  rtd=0.03, ctd=0.55, cap=0.90),
    "Starting TE":    dict(qb=0.0, carry=0.02, target=0.35, catch=0.70, ypt=7.5,  rtd=0.02, ctd=0.30, cap=0.75),
    "NE Kicker":      dict(qb=0.0, carry=0.0,  target=0.0,  catch=0.0,  ypt=0.0,  rtd=0.0,  ctd=0.0,  cap=0.0),
    "Patriots":       dict(qb=0.0, carry=0.0,  target=0.0,  catch=0.0,  ypt=0.0,  rtd=0.0,  ctd=0.0,  cap=0.0),
    "Sea QB":         dict(qb=1.0, carry=0.10, target=0.0,  catch=0.0,  ypt=0.0,  rtd=0.10, ctd=0.0,  cap=0.96),
    "Sea Lead RB":    dict(qb=0.0, carry=0.55, target=0.08, catch=0.80, ypt=5.5,  rtd=0.70, ctd=0.08, cap=0.48),
    "Sea Backup RB":  dict(qb=0.0, carry=0.25, target=0.06, catch=0.85, ypt=5.8,  rtd=0.15, ctd=0.06, cap=0.31),
    "Sea Third RB":   dict(qb=0.0, carry=0.05, target=0.01, catch=1.0,  ypt=7.5,  rtd=0.05, ctd=0.01, cap=0.05),
    "Sea Alpha WR":   dict(qb=0.0, carry=0.04, target=0.55, catch=0.73, ypt=11.0, rtd=0.03, ctd=0.60, cap=0.77),
    "Sea Hurt WR":    dict(qb=0.0, carry=0.0,  target=0.05, catch=0.60, ypt=6.0,  rtd=0.0,  ctd=0.05, cap=0.17),
    "Sea TE":         dict(qb=0.0, carry=0.01, target=0.25, catch=0.76, ypt=7.6,  rtd=0.02, ctd=0.20, cap=0.77),
    "Sea Kicker":     dict(qb=0.0, carry=0.0,  target=0.0,  catch=0.0,  ypt=0.0,  rtd=0.0,  ctd=0.0,  cap=0.0),
    "Seahawks":       dict(qb=0.0, carry=0.0,  target=0.0,  catch=0.0,  ypt=0.0,  rtd=0.0,  ctd=0.0,  cap=0.0),
}


def _model(tmp_path, slate):
    team_path = tmp_path / "team_projections.csv"
    player_path = tmp_path / "player_opportunities.csv"
    game_id = slate.games[0].game_id
    team_rows = []
    for team in ("NE", "SEA"):
        row = {"TEAM": team, "GAME_ID": game_id, **_TEAM_ROW}
        row["MARKET_SPREAD"] = "3" if team == "NE" else "-3"
        team_rows.append([row[column] for column in TEAM_COLUMNS])
    flex = {p.underlying_id: p for p in slate.players if p.role == "FLEX"}
    player_rows = []
    for player in sorted(flex.values(), key=lambda item: int(item.dk_id)):
        s = _SHARES[player.name]
        player_rows.append(
            [
                player.dk_id, player.team, player.position,
                s["qb"], s["carry"], s["target"], s["catch"], s["ypt"],
                s["rtd"], s["ctd"], s["cap"], "PASS",
            ]
        )
    for path, columns, rows in (
        (team_path, TEAM_COLUMNS, team_rows),
        (player_path, PLAYER_COLUMNS, player_rows),
    ):
        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(columns)
        writer.writerows(rows)
        path.write_bytes(buffer.getvalue().encode("utf-8"))
    return load_opportunity_model(slate, team_path, player_path)


# --------------------------------------------------------------------------- #
# Classification
# --------------------------------------------------------------------------- #


def test_out_and_ir_are_unavailable_and_both_roles_are_excluded(tmp_path):
    slate = _slate(tmp_path)
    contract = build_participation_contract(slate)
    assert contract.contract_version == CONTRACT_VERSION
    assert set(contract.unavailable_people) == {"SEA|RB|Sea Lead RB", "SEA|WR|Sea Hurt WR"}
    assert len(contract.unavailable_dk_ids) == 4
    excluded = set(excluded_dk_ids(slate, contract))
    for person in contract.unavailable_people:
        rows = {p.dk_id for p in slate.players if p.underlying_id == person}
        assert rows <= excluded, person
        assert len(rows) == 2
    assert len(contract.selectable_people) == 14


def test_questionable_is_reported_but_stays_selectable(tmp_path):
    slate = _slate(tmp_path)
    contract = build_participation_contract(slate)
    assert contract.degraded_people == ("SEA|TE|Sea TE",)
    assert "SEA|TE|Sea TE" in contract.selectable_people
    assert "SEA|TE|Sea TE:Q" in contract.as_report()["degraded_detail"]


def test_unknown_status_is_refused_not_assumed_available(tmp_path):
    pool = list(_POOL)
    pool[3] = ("NE", "WR", "Alpha WR", "D", 9000)
    slate = _slate(tmp_path, tuple(pool))
    with pytest.raises(ParticipationError, match="UNKNOWN_DK_STATUS"):
        build_participation_contract(slate)
    # The operator can classify a new code, either way, and it is honoured.
    unavailable = build_participation_contract(slate, extra_unavailable_statuses=["d"])
    assert "NE|WR|Alpha WR" in unavailable.unavailable_people
    available = build_participation_contract(slate, extra_available_statuses=["D"])
    assert "NE|WR|Alpha WR" in available.selectable_people
    with pytest.raises(ParticipationError, match="STATUS_CLASSIFIED_BOTH_WAYS"):
        build_participation_contract(
            slate, extra_unavailable_statuses=["D"], extra_available_statuses=["D"]
        )


def test_roles_disagreeing_about_a_person_fails_closed(tmp_path):
    raw = _salary_bytes().decode("utf-8").splitlines()
    for index, line in enumerate(raw):
        if "Sea Alpha WR" in line and ",CPT," in line:
            raw[index] = line[: line.rindex(",")] + ",OUT"
    path = tmp_path / "conflict.csv"
    path.write_bytes(("\n".join(raw) + "\n").encode("utf-8"))
    slate = parse_salaries(path)
    with pytest.raises(ParticipationError, match="STATUS_INCONSISTENT_ACROSS_ROLES"):
        build_participation_contract(slate)


def test_operator_exclusions_are_honoured_and_validated(tmp_path):
    slate = _slate(tmp_path)
    target = next(p for p in slate.players if p.name == "Alpha WR" and p.role == "FLEX")
    contract = build_participation_contract(slate, operator_excluded_dk_ids=[target.dk_id])
    assert contract.operator_excluded_people == ("NE|WR|Alpha WR",)
    assert "NE|WR|Alpha WR" not in contract.selectable_people
    # Both roles still leave the solver's reach, alongside the two unavailable.
    assert len(excluded_dk_ids(slate, contract)) == 6
    with pytest.raises(ParticipationError, match="OPERATOR_EXCLUSION_NOT_IN_POOL"):
        build_participation_contract(slate, operator_excluded_dk_ids=["999999999"])


def test_status_is_reported_per_dk_row(tmp_path):
    slate = _slate(tmp_path)
    contract = build_participation_contract(slate)
    mapping = status_by_dk_id(slate, contract)
    assert len(mapping) == len(slate.players)
    for player in slate.players:
        if player.name == "Sea Lead RB":
            assert mapping[player.dk_id] == "OUT"


# --------------------------------------------------------------------------- #
# Feasibility of what is left
# --------------------------------------------------------------------------- #


def test_a_healthy_pool_reports_no_feasibility_problems(tmp_path):
    slate = _slate(tmp_path)
    assert selectable_pool_problems(slate, build_participation_contract(slate)) == ()


def test_excluding_a_whole_team_is_reported(tmp_path):
    slate = _slate(tmp_path)
    sea = [p.dk_id for p in slate.players if p.team == "SEA" and p.role == "FLEX"]
    contract = build_participation_contract(slate, operator_excluded_dk_ids=sea)
    problems = selectable_pool_problems(slate, contract)
    assert any(problem.startswith("SELECTABLE_POOL_SINGLE_TEAM") for problem in problems)


def test_too_few_selectable_people_is_reported(tmp_path):
    slate = _slate(tmp_path)
    keep = {"NE|QB|Starter QB", "SEA|QB|Sea QB"}
    drop = [
        p.dk_id
        for p in slate.players
        if p.role == "FLEX" and p.underlying_id not in keep
    ]
    contract = build_participation_contract(slate, operator_excluded_dk_ids=drop)
    problems = selectable_pool_problems(slate, contract)
    assert any(problem.startswith("SELECTABLE_POOL_TOO_SMALL") for problem in problems)


# --------------------------------------------------------------------------- #
# Redistribution
# --------------------------------------------------------------------------- #


def test_vacated_share_is_tracked_by_the_position_that_vacated_it(tmp_path):
    slate = _slate(tmp_path)
    model = _model(tmp_path, slate)
    detail = vacated_opportunity_by_position(model, build_participation_contract(slate))
    assert set(detail) == {"SEA"}
    assert "RB" in detail["SEA"]["carry_share"]
    assert "WR" in detail["SEA"]["target_share"]
    assert detail["SEA"]["carry_share"]["RB"] > 0.5


def test_vacated_carries_stay_in_the_running_back_room(tmp_path):
    slate = _slate(tmp_path)
    model = _model(tmp_path, slate)
    contract = build_participation_contract(slate)
    before = {p.underlying_id: p.carry_share for p in model.players}
    reduced, report = redistribute_opportunity(model, contract)
    after = {p.underlying_id: p.carry_share for p in reduced.players}

    # The surviving backup inherits the lead role.
    assert after["SEA|RB|Sea Backup RB"] > before["SEA|RB|Sea Backup RB"] * 2
    # The quarterback's own rushing role does not expand.
    assert after["SEA|QB|Sea QB"] == pytest.approx(before["SEA|QB|Sea QB"])
    # Neither does a receiver's or a tight end's.
    assert after["SEA|TE|Sea TE"] == pytest.approx(before["SEA|TE|Sea TE"])
    assert after["SEA|WR|Sea Alpha WR"] == pytest.approx(before["SEA|WR|Sea Alpha WR"])
    # Nothing was quietly dropped, and the other team is untouched.
    assert report["unallocated_by_team"] == {}
    assert after["NE|RB|Lead RB"] == pytest.approx(before["NE|RB|Lead RB"])
    assert report["rule"].startswith("PROPORTIONAL_TO_PRIOR_WITHIN_VACATING_POSITION")


def test_vacated_targets_go_to_the_same_position_first(tmp_path):
    slate = _slate(tmp_path)
    model = _model(tmp_path, slate)
    contract = build_participation_contract(slate)
    before = {p.underlying_id: p.target_share for p in model.players}
    reduced, _ = redistribute_opportunity(model, contract)
    after = {p.underlying_id: p.target_share for p in reduced.players}
    # The only unavailable Seattle receiver is a wide receiver, so his targets
    # go to the other wide receiver and the tight end is left alone. Spreading
    # them across the whole receiving corps would be a different, looser rule.
    assert after["SEA|WR|Sea Alpha WR"] > before["SEA|WR|Sea Alpha WR"]
    assert after["SEA|TE|Sea TE"] == pytest.approx(before["SEA|TE|Sea TE"])
    assert after["SEA|QB|Sea QB"] == 0


def test_a_vacated_tight_end_feeds_the_tight_ends(tmp_path):
    pool = list(_POOL)
    # Make the Seattle tight end unavailable and add a second one to inherit.
    pool[13] = ("SEA", "TE", "Sea TE", "OUT", 4600)
    pool.append(("SEA", "TE", "Sea Backup TE", "", 1400))
    _SHARES["Sea Backup TE"] = dict(
        qb=0.0, carry=0.0, target=0.04, catch=0.6, ypt=6.5, rtd=0.0, ctd=0.04, cap=0.22
    )
    slate = _slate(tmp_path, tuple(pool))
    model = _model(tmp_path, slate)
    contract = build_participation_contract(slate)
    before = {p.underlying_id: p.target_share for p in model.players}
    reduced, report = redistribute_opportunity(model, contract)
    after = {p.underlying_id: p.target_share for p in reduced.players}
    assert after["SEA|TE|Sea Backup TE"] > before["SEA|TE|Sea Backup TE"] * 3
    assert report["unallocated_by_team"] == {}


def test_unavailable_people_are_gone_from_the_model(tmp_path):
    slate = _slate(tmp_path)
    model = _model(tmp_path, slate)
    contract = build_participation_contract(slate)
    reduced, _ = redistribute_opportunity(model, contract)
    remaining = {p.underlying_id for p in reduced.players}
    assert not remaining & set(contract.unavailable_people)
    assert len(remaining) == len(model.players) - 2


def test_redistribution_can_be_switched_off(tmp_path):
    slate = _slate(tmp_path)
    model = _model(tmp_path, slate)
    contract = build_participation_contract(slate)
    before = {p.underlying_id: p.carry_share for p in model.players}
    reduced, report = redistribute_opportunity(model, contract, redistribute=False)
    after = {p.underlying_id: p.carry_share for p in reduced.players}
    for person, value in after.items():
        assert value == pytest.approx(before[person]), person
    assert report["rule"] == "NO_REDISTRIBUTION_SURVIVORS_KEEP_PRIOR_SHARES"
    assert report["unallocated_by_team"]["SEA"]["carry_share"] > 0.5


def test_role_capacity_is_a_diagnostic_and_never_a_ceiling(tmp_path):
    slate = _slate(tmp_path)
    model = _model(tmp_path, slate)
    contract = build_participation_contract(slate)
    reduced, report = redistribute_opportunity(model, contract)
    promoted = next(
        p for p in reduced.players if p.underlying_id == "SEA|RB|Sea Backup RB"
    )
    # The promoted back exceeds the snap share he held while behind the starter,
    # which is the point: that number describes the role he was promoted out of.
    assert promoted.carry_share > promoted.role_capacity
    assert any(
        entry.startswith("SEA|RB|Sea Backup RB:carry_share")
        for entry in report["share_above_prior_capacity_after_redistribution"]
    )
    assert report["capacity_treatment"].startswith("DIAGNOSTIC_ONLY")


def test_removing_every_person_for_a_team_fails_closed(tmp_path):
    slate = _slate(tmp_path)
    model = _model(tmp_path, slate)
    sea = [p.dk_id for p in slate.players if p.team == "SEA" and p.role == "FLEX"]
    contract = build_participation_contract(slate, operator_excluded_dk_ids=sea)
    with pytest.raises(
        ParticipationError, match="PARTICIPATION_REMOVES_EVERY_PERSON_FOR_TEAM"
    ):
        redistribute_opportunity(model, contract)


def test_capacity_data_quality_separates_conversion_from_join_gaps(tmp_path):
    slate = _slate(tmp_path)
    model = _model(tmp_path, slate)
    quality = capacity_data_quality(model)
    # The lead backs convert more touchdowns than their snap share, which is
    # ordinary football and must be reported rather than enforced.
    assert quality["share_above_capacity_count"] >= 1
    assert "interpretation" in quality
