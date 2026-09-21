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
from nfl_dfs.opportunity import (
    PLAYER_COLUMNS,
    TEAM_COLUMNS,
    OpportunityError,
    load_opportunity_model,
)
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
    # "SSPD" stands in for a code DraftKings has not shipped here yet. It used
    # to be "D", which stopped being an unknown code when doubtful was handled
    # natively; an exemplar that the vocabulary later absorbs stops testing the
    # thing it was written for.
    pool = list(_POOL)
    pool[3] = ("NE", "WR", "Alpha WR", "SSPD", 9000)
    slate = _slate(tmp_path, tuple(pool))
    with pytest.raises(ParticipationError, match="UNKNOWN_DK_STATUS"):
        build_participation_contract(slate)
    # The operator can classify a new code, either way, and it is honoured.
    unavailable = build_participation_contract(slate, extra_unavailable_statuses=["sspd"])
    assert "NE|WR|Alpha WR" in unavailable.unavailable_people
    available = build_participation_contract(slate, extra_available_statuses=["SSPD"])
    assert "NE|WR|Alpha WR" in available.selectable_people
    with pytest.raises(ParticipationError, match="STATUS_CLASSIFIED_BOTH_WAYS"):
        build_participation_contract(
            slate, extra_unavailable_statuses=["SSPD"], extra_available_statuses=["SSPD"]
        )


def test_doubtful_is_unavailable_without_an_operator_flag(tmp_path):
    """P3-18. On 2026-09-13 a real Classic slate stopped on UNKNOWN_DK_STATUS:D.

    The operator cleared it by remembering `--unavailable-status D` under a lock
    clock, which is a default masquerading as a decision.
    """

    pool = list(_POOL)
    pool[3] = ("NE", "WR", "Alpha WR", "D", 9000)
    slate = _slate(tmp_path, tuple(pool))

    contract = build_participation_contract(slate)
    assert "NE|WR|Alpha WR" in contract.unavailable_people
    assert "NE|WR|Alpha WR" not in contract.selectable_people
    # Every role row of the person moves together, so a Showdown CPT row cannot
    # survive its own FLEX row being excluded.
    assert set(excluded_dk_ids(slate, contract)) >= {
        row.dk_id for row in slate.players if row.underlying_id == "NE|WR|Alpha WR"
    }


def test_the_operator_can_still_put_a_doubtful_person_back_in_the_pool(tmp_path):
    """The default is a judgement, so it has to be reversible in one flag.

    Before this, `--available-status D` collided with the built-in default and
    raised STATUS_CLASSIFIED_BOTH_WAYS, which left the operator no way back.
    """

    pool = list(_POOL)
    pool[3] = ("NE", "WR", "Alpha WR", "D", 9000)
    slate = _slate(tmp_path, tuple(pool))

    restored = build_participation_contract(slate, extra_available_statuses=["D"])
    assert "NE|WR|Alpha WR" in restored.selectable_people
    assert "NE|WR|Alpha WR" not in restored.unavailable_people
    # Two operator flags that contradict each other are still a typo, not a
    # judgement, and still fail closed.
    with pytest.raises(ParticipationError, match="STATUS_CLASSIFIED_BOTH_WAYS"):
        build_participation_contract(
            slate, extra_unavailable_statuses=["D"], extra_available_statuses=["D"]
        )


def test_the_supplied_classic_slate_needs_no_status_flags(classic_slate):
    """The 2026-09-13 fixture carries D rows. It must build unflagged.

    This is the end-to-end form of P3-18: the supplied Classic bytes are the
    exact shape that stopped the live run.
    """

    statuses = {(row.status_raw or "").strip().upper() for row in classic_slate.players}
    assert "D" in statuses, "fixture no longer exercises the doubtful path"

    contract = build_participation_contract(classic_slate)
    doubtful = {
        row.underlying_id
        for row in classic_slate.players
        if (row.status_raw or "").strip().upper() == "D"
    }
    assert doubtful
    assert doubtful <= set(contract.unavailable_people)
    assert not doubtful & set(contract.selectable_people)


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


# --------------------------------------------------------------------------- #
# P0-1: pool completeness, the opportunity side
# --------------------------------------------------------------------------- #


def _model_missing(tmp_path, slate, omit: str):
    """Build the opportunity inputs with one person's row left out."""

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
        if player.name == omit:
            continue
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


def test_a_missing_selectable_person_is_still_a_hard_stop(tmp_path):
    """The tolerance added on 2026-09-13 must not become a blanket one."""

    slate = _slate(tmp_path)
    with pytest.raises(OpportunityError, match="missing 1 selectable people"):
        _model_missing(tmp_path, slate, "Sea Third RB")


def test_a_missing_person_the_site_flags_out_is_tolerated(tmp_path):
    """A person DraftKings flags OUT cannot be selected, so his absence from the
    model inputs cannot change any lineup. Blocking on it was an evidence gate
    no source could clear on a full Classic pool.
    """

    pool = list(_POOL)
    index = next(i for i, row in enumerate(pool) if row[2] == "Sea Third RB")
    pool[index] = (pool[index][0], pool[index][1], pool[index][2], "OUT", pool[index][4])
    slate = _slate(tmp_path, tuple(pool))

    model = _model_missing(tmp_path, slate, "Sea Third RB")
    assert model is not None
    assert "SEA|RB|Sea Third RB" not in {
        player.underlying_id for player in model.players
    }


# --- P7: the depth chart names a successor -------------------------------


def _seattle_back_ranks():
    """Effective ranks after the OUT lead back is removed from above.

    Shaped exactly as `depth_roles.effective_depth_ranks` returns them, keyed
    `(person, position)`, so the wiring under test is the real one.
    """

    from nfl_dfs.depth_roles import DepthRow, effective_depth_ranks

    rows = [
        DepthRow(person="SEA|RB|Sea Lead RB", team="SEA", position="RB",
                 published_rank=1, player_name="Sea Lead RB"),
        DepthRow(person="SEA|RB|Sea Backup RB", team="SEA", position="RB",
                 published_rank=2, player_name="Sea Backup RB"),
        DepthRow(person="SEA|RB|Sea Third RB", team="SEA", position="RB",
                 published_rank=3, player_name="Sea Third RB"),
    ]
    return effective_depth_ranks(rows, unavailable_people={"SEA|RB|Sea Lead RB"})


def test_the_named_successor_inherits_the_whole_vacated_share(tmp_path):
    slate = _slate(tmp_path)
    model = _model(tmp_path, slate)
    contract = build_participation_contract(slate)
    before = {p.underlying_id: p.carry_share for p in model.players}
    reduced, report = redistribute_opportunity(
        model, contract, depth_ranks=_seattle_back_ranks()
    )
    after = {p.underlying_id: p.carry_share for p in reduced.players}

    vacated = before["SEA|RB|Sea Lead RB"]
    assert after["SEA|RB|Sea Backup RB"] == pytest.approx(
        before["SEA|RB|Sea Backup RB"] + vacated
    )
    # The third back is behind him on the chart and inherits nothing.
    assert after["SEA|RB|Sea Third RB"] == pytest.approx(before["SEA|RB|Sea Third RB"])
    assert report["vacancy_rule"] == "DEPTH_CHART_SUCCESSOR_INHERITS_V1"
    assert report["unallocated_by_team"] == {}


def test_without_depth_ranks_the_measured_proportional_rule_is_unchanged(tmp_path):
    """The default is not touched by P7. Supplying ranks is an explicit choice."""

    slate = _slate(tmp_path)
    model = _model(tmp_path, slate)
    contract = build_participation_contract(slate)
    before = {p.underlying_id: p.carry_share for p in model.players}
    reduced, report = redistribute_opportunity(model, contract)
    after = {p.underlying_id: p.carry_share for p in reduced.players}

    assert report["vacancy_rule"] == "PROPORTIONAL_TO_PRIOR_NO_SUCCESSOR_KNOWN"
    # Both survivors gain, which is the behaviour the NE@SEA measurement forced.
    assert after["SEA|RB|Sea Third RB"] > before["SEA|RB|Sea Third RB"]
    assert after["SEA|RB|Sea Backup RB"] > before["SEA|RB|Sea Backup RB"]


def test_a_position_the_chart_does_not_place_keeps_the_proportional_rule(tmp_path):
    """No successor is invented when the depth chart places nobody who survived."""

    slate = _slate(tmp_path)
    model = _model(tmp_path, slate)
    contract = build_participation_contract(slate)
    before = {p.underlying_id: p.carry_share for p in model.players}
    # Ranks that name only the person who is already OUT.
    from nfl_dfs.depth_roles import DepthRow, effective_depth_ranks

    ranks = effective_depth_ranks(
        [
            DepthRow(person="SEA|RB|Sea Lead RB", team="SEA", position="RB",
                     published_rank=1, player_name="Sea Lead RB")
        ],
        unavailable_people=set(),
    )
    reduced, _report = redistribute_opportunity(model, contract, depth_ranks=ranks)
    after = {p.underlying_id: p.carry_share for p in reduced.players}
    assert after["SEA|RB|Sea Third RB"] > before["SEA|RB|Sea Third RB"]
