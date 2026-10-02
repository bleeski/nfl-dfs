"""Session 54 (R36): a depth-declared starter with no usable history is selectable.

Ben, 2026-10-01: "We can't over rely on history." A quarterback the hash-bound depth evidence names
the starter, with no prior-season row, used to be excluded by the role gate whatever the chart said
(Keenum on PHI@CHI, Watson on PIT@CLE). He is now selectable as a DIAGNOSTIC: attempt share from the
depth resolution, carry and target shares zero, a finding that says the share is a depth-chart order and
not a role fact. Participation precedence still wins. Every fixture is synthetic.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from nfl_dfs.offensive_roles import FIELDS, resolve_offensive_roles
from nfl_dfs.participation import build_participation_contract
from nfl_dfs.qb_depth_roles import (
    ALLOCATION_VERSION_V2,
    TRANSFORMATION_VERSION_V2,
    resolve_qb_depth_roles,
)
from nfl_dfs.selection import select_prior_lineups

from . import test_offensive_roles as roles
from . import test_qb_depth_roles as depth

NO_HISTORY = "KC Starter QB"
CODE = "OFFENSIVE_DEPTH_DECLARED_STARTER_NO_HISTORY"


def _world(tmp_path, *, pool=depth._POOL, orders=None, backup_share=1.0, no_history=NO_HISTORY,
           qb_shares=None, **package):
    """A KC quarterback with no history. His row is all zeros and the backup carries the pool.

    `qb_shares` overrides named quarterbacks' attempt shares (for a no-history backup).
    """

    tmp_path.mkdir(parents=True, exist_ok=True)
    slate, model, contract, splits = depth._setup(tmp_path, pool=pool)
    person = depth._person(slate, no_history)
    players = []
    for row in model.players:
        if row.underlying_id == person:
            row = replace(row, **{field: 0.0 for field in FIELDS})
        elif row.underlying_id == depth._person(slate, "KC Backup QB") and no_history == NO_HISTORY:
            row = replace(row, qb_attempt_share=backup_share)
        for name, share in (qb_shares or {}).items():
            if row.underlying_id == depth._person(slate, name):
                row = replace(row, qb_attempt_share=share)
        players.append(row)
    model = replace(
        model, players=tuple(players),
        offensive_history_by_person={person: {"state": "MISSING_HISTORY", "incompatible_transfer": False}},
    )
    package.setdefault("transformation", TRANSFORMATION_VERSION_V2)
    package.setdefault("allocation", ALLOCATION_VERSION_V2)
    evidence = depth._package(tmp_path / "qb", slate, orders or depth._orders(), **package)
    return slate, model, contract, splits, evidence, person


def _select(world, **kwargs):
    slate, model, contract, splits, evidence, _person = world
    return select_prior_lineups(
        slate, model, splits, contract, count=kwargs.pop("count", 4),
        qb_depth_role_evidence_json=evidence, as_of=depth.AS_OF, **kwargs,
    )


def _finding(report, person):
    return next(f for f in report["offensive_roles"]["findings"] if f["person"] == person)


# --------------------------------------------------------------------------- #
# Acceptance 1 and 5: selectable, scored, carry share 0, the finding says what it is
# --------------------------------------------------------------------------- #


def test_a_declared_starter_with_no_history_is_scored_and_selectable_with_carry_share_zero(tmp_path):
    world = _world(tmp_path)
    person = world[-1]
    lineups, scores, report = _select(world)
    finding = _finding(report, person)
    assert finding["selection_action"] == "DIAGNOSTIC" and finding["finding"] == CODE
    assert finding["state"] == "MISSING_HISTORY" and finding["history_state"] == "MISSING_HISTORY"
    # The gate reads the model the depth resolution already moved, so `before` carries the share too.
    assert finding["before"] == {**dict.fromkeys(FIELDS, 0.0), "qb_attempt_share": 1.0}
    assert finding["after"]["qb_attempt_share"] == 1.0
    assert finding["after"]["carry_share"] == 0.0 and finding["after"]["target_share"] == 0.0
    assert person in scores.by_person and scores.by_person[person] > 0
    assert person not in {p for people in report["offensive_roles"]["excluded_by_finding"].values() for p in people}
    assert lineups


def test_the_finding_names_the_depth_evidence_and_says_it_is_not_a_role(tmp_path):
    world = _world(tmp_path)
    _lineups, _scores, report = _select(world)
    text = _finding(report, world[-1])["next_evidence_action"]
    assert "depth evidence" in text and "depth-chart order, not a role fact" in text
    assert "not confirmed activity" in text and "carry share 0, target share 0" in text
    assert report["qb_depth_roles"]["evidence_sha256"] in text and "effective starter for KC" in text
    assert report["offensive_roles"]["evidence_state"] == "UNKNOWN"
    assert "DEPTH_DECLARED_STARTER_WITHOUT_HISTORY_IS_A_DEPTH_CHART_ORDER_NOT_A_ROLE" in (
        report["offensive_roles"]["assumptions"]
    )


def test_he_can_be_rostered_by_the_unbound_selection(tmp_path):
    world = _world(tmp_path)
    slate, person = world[0], world[-1]
    lineups, _scores, _report = _select(world, count=6)
    by_id = {p.dk_id: p for p in slate.players}
    held = [any(by_id[dk].underlying_id == person for dk in lineup.roster) for lineup in lineups]
    assert any(held), "a scored, selectable quarterback should reach at least one of six lineups"


def test_an_empty_quarterback_pool_gives_the_declared_starter_the_unit_share_under_allocation_v2(tmp_path):
    # Both Kansas City quarterbacks have no history: nothing to conserve, so the depth resolution gives
    # the starter the unit share (BASIS_POOL_UNIT_NO_ALLOCATED_POOL) and the gate selects him on it.
    world = _world(tmp_path, backup_share=0.0)
    lineups, scores, report = _select(world)
    finding = _finding(report, world[-1])
    assert finding["selection_action"] == "DIAGNOSTIC" and finding["after"]["qb_attempt_share"] == 1.0
    assert world[-1] in scores.by_person and lineups


# --------------------------------------------------------------------------- #
# Acceptance 2: declared a backup stays excluded
# --------------------------------------------------------------------------- #


def test_the_same_quarterback_declared_a_backup_stays_excluded(tmp_path):
    world = _world(
        tmp_path,
        orders={"KC": ("KC Backup QB", "KC Starter QB"), "DEN": ("DEN Starter QB",)},
    )
    person = world[-1]
    _lineups, scores, report = _select(world)
    finding = _finding(report, person)
    assert finding["selection_action"] == "EXCLUDE" and finding["finding"] == "OFFENSIVE_MISSING_HISTORY"
    assert person not in scores.by_person
    assert report["qb_depth_roles"]["starters_by_team"]["KC"] == depth._person(world[0], "KC Backup QB")


# --------------------------------------------------------------------------- #
# Acceptance 3: a DraftKings-OUT declared starter stays excluded
# --------------------------------------------------------------------------- #


def test_a_declared_starter_draftkings_lists_out_stays_excluded_and_his_backup_is_promoted(tmp_path):
    pool = tuple(
        (team, position, name, "OUT" if name == NO_HISTORY else status, salary)
        for team, position, name, status, salary in depth._POOL
    )
    world = _world(tmp_path, pool=pool)
    person = world[-1]
    _lineups, scores, report = _select(world)
    finding = _finding(report, person)
    assert finding["selection_action"] == "EXCLUDE" and finding["finding"] == "PARTICIPATION_PRECEDENCE"
    assert person not in scores.by_person
    assert report["qb_depth_roles"]["starters_by_team"]["KC"] == depth._person(world[0], "KC Backup QB")


# --------------------------------------------------------------------------- #
# Acceptance 4: a declared starter with history is unchanged
# --------------------------------------------------------------------------- #


def test_a_declared_starter_with_history_is_unchanged(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    slate, model, contract, splits = depth._setup(tmp_path)
    evidence = depth._package(
        tmp_path / "qb", slate, depth._orders(),
        transformation=TRANSFORMATION_VERSION_V2, allocation=ALLOCATION_VERSION_V2,
    )
    _lineups, scores, report = select_prior_lineups(
        slate, model, splits, contract, count=4, qb_depth_role_evidence_json=evidence, as_of=depth.AS_OF
    )
    starter = depth._person(slate, NO_HISTORY)
    finding = _finding(report, starter)
    assert finding["finding"] == "HISTORICAL_ROLE_UNCONFIRMED" and finding["selection_action"] == "DIAGNOSTIC"
    assert starter in scores.by_person


# --------------------------------------------------------------------------- #
# The bounds, called directly
# --------------------------------------------------------------------------- #


def _resolve(world, declared, role_evidence=None, contract=None):
    slate, model, base_contract, _splits, evidence, _person = world
    resolution = resolve_qb_depth_roles(slate, model, base_contract, evidence_path=evidence, as_of=depth.AS_OF)
    return resolve_offensive_roles(
        slate, resolution.model, contract or base_contract, as_of=depth.AS_OF, declared_starters=declared,
        evidence_path=role_evidence, depth_evidence_sha256=resolution.evidence_sha256,
    )


def test_with_no_declared_starters_the_gate_is_exactly_what_it_was(tmp_path):
    world = _world(tmp_path)
    finding = next(f for f in _resolve(world, ()).report["findings"] if f["person"] == world[-1])
    assert finding["selection_action"] == "EXCLUDE" and finding["finding"] == "OFFENSIVE_MISSING_HISTORY"


def test_a_declared_non_quarterback_with_no_history_stays_excluded(tmp_path):
    world = _world(tmp_path)
    slate, model = world[0], world[1]
    rb = depth._person(slate, "KC Committee RB")
    model = replace(model, offensive_history_by_person={rb: {"state": "MISSING_HISTORY"}})
    world = (slate, model, *world[2:])
    finding = next(f for f in _resolve(world, {rb}).report["findings"] if f["person"] == rb)
    assert finding["selection_action"] == "EXCLUDE" and finding["finding"] == "OFFENSIVE_MISSING_HISTORY"


def test_allocation_v1_leaves_an_empty_pool_at_zero_so_the_declared_starter_stays_excluded_by_name(tmp_path):
    world = _world(tmp_path, backup_share=0.0, transformation=depth.TRANSFORMATION_VERSION,
                   allocation=depth.ALLOCATION_VERSION)
    _lineups, scores, report = _select(world)
    finding = _finding(report, world[-1])
    assert finding["selection_action"] == "EXCLUDE" and finding["finding"] == "OFFENSIVE_MISSING_HISTORY"
    assert "allocation version 1 leaves an empty quarterback pool at zero" in finding["next_evidence_action"]
    assert world[-1] not in scores.by_person


def test_a_refused_gap_fill_is_named_in_the_finding_of_a_declared_starter(tmp_path):
    world = _world(tmp_path)
    slate, model = world[0], world[1]
    person = world[-1]
    model = replace(model, offensive_history_by_person={
        person: {"state": "MISSING_HISTORY", "incompatible_transfer": False,
                 "gap_fill_refused": "CURRENT_SEASON_STATS_INCOMPLETE:KC:2"},
    })
    finding = next(
        f for f in _resolve((slate, model, *world[2:]), {person}).report["findings"] if f["person"] == person
    )
    assert finding["selection_action"] == "DIAGNOSTIC"
    assert "CURRENT_SEASON_STATS_INCOMPLETE:KC:2" in finding["next_evidence_action"]


# --------------------------------------------------------------------------- #
# Review findings (2026-10-02): bound facts, a promoted backup, participation, allocation
# --------------------------------------------------------------------------- #


def _roles(world, tmp_path, *facts):
    return roles._package(tmp_path / "roles", world[0], facts=[(world[-1], fact) for fact in facts], as_of=depth.AS_OF)


@pytest.mark.parametrize("fact", ["NAMED_BACKUP", "MATERIAL_ROLE_CHANGE"])
def test_a_bound_fact_that_disagrees_with_the_depth_chart_keeps_the_old_exclusion(tmp_path, fact):
    # Two hash-bound sources disagree about the same quarterback: the engine chooses neither.
    world = _world(tmp_path)
    finding = next(
        f for f in _resolve(world, {world[-1]}, role_evidence=_roles(world, tmp_path, fact)).report["findings"]
        if f["person"] == world[-1]
    )
    assert finding["selection_action"] == "EXCLUDE" and finding["finding"] == "OFFENSIVE_MISSING_HISTORY"
    assert finding["declared_fact"] == fact


def test_a_bound_fact_that_agrees_with_the_depth_chart_changes_nothing(tmp_path):
    world = _world(tmp_path)
    finding = next(
        f for f in _resolve(world, {world[-1]}, role_evidence=_roles(world, tmp_path, "NAMED_STARTER")).report["findings"]
        if f["person"] == world[-1]
    )
    assert finding["selection_action"] == "DIAGNOSTIC" and finding["finding"] == CODE
    assert finding["declared_fact"] == "NAMED_STARTER"


def test_an_explicit_nonparticipation_fact_beats_the_depth_chart(tmp_path):
    world = _world(tmp_path)
    finding = next(
        f for f in _resolve(world, {world[-1]}, role_evidence=_roles(world, tmp_path, "EXPLICIT_NONPARTICIPATION")).report["findings"]
        if f["person"] == world[-1]
    )
    assert finding["selection_action"] == "EXCLUDE" and finding["finding"] == "PARTICIPATION_PRECEDENCE"


def test_an_operator_excluded_declared_starter_is_excluded_by_participation_precedence(tmp_path):
    # Selection never reaches here (the depth resolver refuses to promote past him), so this is the gate alone.
    world = _world(tmp_path)
    slate = world[0]
    excluded = build_participation_contract(
        slate, operator_excluded_dk_ids=[p.dk_id for p in slate.players if p.name == NO_HISTORY]
    )
    base = (world[0], world[1], excluded, *world[3:])
    slate, model, _contract, _splits, _evidence, person = base
    finding = next(
        f for f in resolve_offensive_roles(slate, model, excluded, as_of=depth.AS_OF, declared_starters={person}).report["findings"]
        if f["person"] == person
    )
    assert finding["selection_action"] == "EXCLUDE" and finding["finding"] == "PARTICIPATION_PRECEDENCE"


def test_a_no_history_backup_the_resolver_promotes_over_an_out_starter_is_selectable_and_says_so(tmp_path):
    # R25 (Ben, ruled): a DraftKings-unavailable published starter is stepped over and his backup inherits
    # the job. That backup is the effective starter, so the rule treats him as one, and the finding says
    # "effective starter", not "declared". This pins the choice; the promotion is named in the QB report.
    pool = tuple(
        (team, position, name, "OUT" if name == NO_HISTORY else status, salary)
        for team, position, name, status, salary in depth._POOL
    )
    world = _world(tmp_path, pool=pool, no_history="KC Backup QB", qb_shares={NO_HISTORY: 1.0})
    person = world[-1]
    _lineups, scores, report = _select(world)
    assert report["qb_depth_roles"]["starters_by_team"]["KC"] == person
    assert report["qb_depth_roles"]["effective_starter_promotions"]
    finding = _finding(report, person)
    assert finding["selection_action"] == "DIAGNOSTIC" and finding["finding"] == CODE
    assert "effective starter for KC" in finding["next_evidence_action"]
    assert person in scores.by_person


def test_an_explicit_team_allocation_still_decides_the_declared_starters_team(tmp_path):
    world = _world(tmp_path)
    slate, model = world[0], world[1]
    resolution = resolve_qb_depth_roles(slate, model, world[2], evidence_path=world[4], as_of=depth.AS_OF)
    recipients, sums = [], dict.fromkeys(FIELDS, 0.0)
    for player in resolution.model.players:
        if player.team != "KC" or player.position not in roles.OFFENSE:
            continue
        shares = {field: getattr(player, field) for field in FIELDS}
        for field, value in shares.items():
            sums[field] += value
        recipients.append({**roles._binding(slate, player.underlying_id), "shares": shares, "receiving_efficiency": None})
    declaration = {
        "team": "KC", "game_id": slate.games[0].game_id,
        "totals": dict.fromkeys(FIELDS, 1.0),
        "unallocated": {field: round(1.0 - sums[field], 12) for field in FIELDS},
        "recipients": recipients,
    }
    path = roles._package(tmp_path / "roles", slate, [declaration], as_of=depth.AS_OF)
    finding = next(
        f for f in _resolve(world, {world[-1]}, role_evidence=path).report["findings"] if f["person"] == world[-1]
    )
    assert finding["finding"] == "EXPLICIT_TEAM_ALLOCATION" and finding["selection_action"] == "SELECT"
