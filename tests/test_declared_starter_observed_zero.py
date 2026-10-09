"""Session 58 (R36, review F-03): a depth-declared starter whose history is all zero is selectable too.

Session 54 made a quarterback the depth evidence names his team's effective starter selectable when his
history state is `MISSING_HISTORY`. The same starter with an all-zero record (`OBSERVED_HISTORY_ZERO`) was
still excluded with the depth resolution's attempt share erased: two identical starters, opposite decisions
by the shape of the history file. These tests run the Session 54 world under both states and pin each
state's own outcome, cell by cell. Every fixture is synthetic; the helpers come from the Session 54 file.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from nfl_dfs.dk import parse_salaries
from nfl_dfs.hashing import sha256_file
from nfl_dfs.offensive_roles import FIELDS, OffensiveRoleError, resolve_offensive_roles
from nfl_dfs.participation import build_participation_contract
from nfl_dfs.prior_review import run_prior_review
from nfl_dfs.qb_depth_roles import resolve_qb_depth_roles

from . import test_classic_judgment as classic_judgment
from . import test_classic_prior_review as classic
from . import test_declared_starter_selectable as ds
from . import test_offensive_roles as roles
from . import test_qb_depth_roles as depth

MISSING, ZERO = "MISSING_HISTORY", "OBSERVED_HISTORY_ZERO"
STATES = (MISSING, ZERO)
CODE = "OFFENSIVE_DEPTH_DECLARED_STARTER_NO_HISTORY"
EXCLUDE_CODE = {MISSING: "OFFENSIVE_MISSING_HISTORY", ZERO: "OFFENSIVE_OBSERVED_HISTORY_ZERO"}
# The evidence state the prior producer writes on the model row for each history state (priors.py).
PRODUCER_ROW = {MISSING: "UNKNOWN", ZERO: "PASS", "CURRENT_ROLE_UNKNOWN": "UNKNOWN"}
BLOCK = ("BLOCK", "OFFENSIVE_CURRENT_ROLE_UNRESOLVED")
REFUSED = "CURRENT_SEASON_STATS_INCOMPLETE:KC:2"
NO_DEPTH_SHARE = (
    " The depth evidence declares him the starter but gave him no attempt share"
    " (allocation version 1 leaves an empty quarterback pool at zero)."
)


def _history(state, **extra):
    """The producer's key set for a history entry (`priors.py`, `offensive_current_team_history_v1`)."""

    return {
        "state": state, "historical_teams": ["KC"], "current_team": "KC", "provider_current_team": "KC",
        "incompatible_transfer": False, "prior_rows": 17, "current_team_rows": 17, "prior_season": 2025,
        "receiving_efficiency_observed": False, "basis_version": "offensive_current_team_history_v1",
        "denominator_basis": "CURRENT_TEAM_ROWS_ONLY_CURRENT_SALARY_POOL", **extra,
    }


def _world(tmp_path, state, *, row_evidence=None, history_extra=None, **kwargs):
    """The Session 54 world with the starter's history state, and his row's evidence state, swapped."""

    slate, model, contract, splits, evidence, person = ds._world(tmp_path, **kwargs)
    marking = row_evidence or PRODUCER_ROW[state]
    players = tuple(replace(p, evidence_state=marking) if p.underlying_id == person else p for p in model.players)
    model = replace(
        model, players=players, offensive_history_by_person={person: _history(state, **(history_extra or {}))}
    )
    return slate, model, contract, splits, evidence, person


def _outcome(world, declared, role_evidence=None):
    """(selection_action, finding code, finding) from the resolver; ("BLOCK", code, None) when it raises."""

    try:
        resolution = ds._resolve(world, declared, role_evidence=role_evidence)
    except OffensiveRoleError as exc:
        return "BLOCK", str(exc).split(":", 1)[0], None
    found = next(f for f in resolution.report["findings"] if f["person"] == world[-1])
    return found["selection_action"], found["finding"], found


def _selectable_text(state, sha, refused=None):
    source = f" (sha256 {sha})" if sha else ""
    basis = (
        "no history to carry" if state == MISSING
        else "the history record exists and every share in it is zero, so there is nothing to carry"
    )
    return (
        f"Selectable on the quarterback depth evidence{source} alone: the effective starter for KC, attempt share 1,"
        f" carry share 0, target share 0 ({basis}). That share is a depth-chart order, not a role fact, and it is"
        " not confirmed activity. Capture an explicit numerical current-team allocation to replace it."
        + (f" Current-season gap-fill was refused: {refused}." if refused else "")
    )


SELECTABLE_CASES = [
    pytest.param(MISSING, {}, id="missing-history"),
    pytest.param(ZERO, {}, id="observed-zero"),
    pytest.param(ZERO, {"gap_fill_refused": REFUSED}, id="observed-zero-gap-fill-refused"),
]


# --------------------------------------------------------------------------- #
# Acceptance 1: selectable, scored, carry and target share zero, the state kept
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(("state", "extra"), SELECTABLE_CASES)
def test_a_declared_starter_is_scored_and_selectable_with_carry_and_target_share_zero(tmp_path, state, extra):
    world = _world(tmp_path, state, history_extra=extra)
    slate, person = world[0], world[-1]
    lineups, scores, report = ds._select(world, count=6)
    finding = ds._finding(report, person)
    assert finding["selection_action"] == "DIAGNOSTIC" and finding["finding"] == CODE
    assert finding["state"] == state and finding["history_state"] == state
    assert finding["before"] == {**dict.fromkeys(FIELDS, 0.0), "qb_attempt_share": 1.0}
    assert finding["after"] == {**dict.fromkeys(FIELDS, 0.0), "qb_attempt_share": 1.0}
    assert scores.by_person[person] > 0
    assert person not in {p for people in report["offensive_roles"]["excluded_by_finding"].values() for p in people}
    by_id = {p.dk_id: p for p in slate.players}
    assert lineups and any(by_id[dk].underlying_id == person for lineup in lineups for dk in lineup.roster)
    assert report["offensive_roles"]["evidence_state"] == "UNKNOWN"
    assert "DEPTH_DECLARED_STARTER_WITHOUT_HISTORY_IS_A_DEPTH_CHART_ORDER_NOT_A_ROLE" in (
        report["offensive_roles"]["assumptions"]
    )


@pytest.mark.parametrize(("state", "extra"), SELECTABLE_CASES)
def test_the_finding_text_is_pinned_whole_and_names_the_depth_package(tmp_path, state, extra):
    world = _world(tmp_path, state, history_extra=extra)
    _lineups, _scores, report = ds._select(world)
    sha = report["qb_depth_roles"]["evidence_sha256"]
    assert sha and ds._finding(report, world[-1])["next_evidence_action"] == _selectable_text(
        state, sha, extra.get("gap_fill_refused")
    )


@pytest.mark.parametrize("state", STATES)
def test_a_depth_package_without_a_sha256_leaves_the_hash_out(tmp_path, state):
    slate, model, contract, _splits, evidence, person = _world(tmp_path, state)
    resolution = resolve_qb_depth_roles(slate, model, contract, evidence_path=evidence, as_of=depth.AS_OF)
    result = resolve_offensive_roles(
        slate, resolution.model, contract, as_of=depth.AS_OF, declared_starters={person}, depth_evidence_sha256=None
    )
    found = next(f for f in result.report["findings"] if f["person"] == person)
    assert found["selection_action"] == "DIAGNOSTIC" and found["next_evidence_action"] == _selectable_text(state, None)


# --------------------------------------------------------------------------- #
# Acceptance 2: backups and participation precedence are unchanged in both states
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("state", STATES)
def test_the_same_quarterback_declared_a_backup_stays_excluded_by_his_own_code(tmp_path, state):
    world = _world(tmp_path, state, orders={"KC": ("KC Backup QB", "KC Starter QB"), "DEN": ("DEN Starter QB",)})
    _lineups, scores, report = ds._select(world)
    finding = ds._finding(report, world[-1])
    assert finding["selection_action"] == "EXCLUDE" and finding["finding"] == EXCLUDE_CODE[state]
    assert world[-1] not in scores.by_person
    assert report["qb_depth_roles"]["starters_by_team"]["KC"] == depth._person(world[0], "KC Backup QB")


@pytest.mark.parametrize("state", STATES)
def test_a_declared_starter_draftkings_lists_out_stays_excluded_and_his_backup_is_promoted(tmp_path, state):
    pool = tuple(
        (team, position, name, "OUT" if name == ds.NO_HISTORY else status, salary)
        for team, position, name, status, salary in depth._POOL
    )
    world = _world(tmp_path, state, pool=pool)
    _lineups, scores, report = ds._select(world)
    finding = ds._finding(report, world[-1])
    assert finding["selection_action"] == "EXCLUDE" and finding["finding"] == "PARTICIPATION_PRECEDENCE"
    assert world[-1] not in scores.by_person
    assert report["qb_depth_roles"]["starters_by_team"]["KC"] == depth._person(world[0], "KC Backup QB")


@pytest.mark.parametrize("state", STATES)
def test_an_operator_or_official_exclusion_wins_by_participation_precedence(tmp_path, state):
    # Official inactives reach the role gate folded into the operator-excluded ids (`prior_review.py`), so this is
    # the gate's whole participation path. Selection never gets here (the depth resolver refuses to promote past him).
    slate, model, _contract, _splits, _evidence, person = _world(tmp_path, state)
    excluded = build_participation_contract(
        slate, operator_excluded_dk_ids=[p.dk_id for p in slate.players if p.name == ds.NO_HISTORY]
    )
    result = resolve_offensive_roles(slate, model, excluded, as_of=depth.AS_OF, declared_starters={person})
    found = next(f for f in result.report["findings"] if f["person"] == person)
    assert found["selection_action"] == "EXCLUDE" and found["finding"] == "PARTICIPATION_PRECEDENCE"


# --------------------------------------------------------------------------- #
# Acceptance 3: conflicting facts keep each state's own pre-change outcome
# --------------------------------------------------------------------------- #

SELECT = ("DIAGNOSTIC", CODE)
FACT_OUTCOMES = {
    (MISSING, None): SELECT,
    (MISSING, "NAMED_STARTER"): SELECT,
    (MISSING, "NAMED_BACKUP"): ("EXCLUDE", "OFFENSIVE_MISSING_HISTORY"),
    (MISSING, "MATERIAL_ROLE_CHANGE"): ("EXCLUDE", "OFFENSIVE_MISSING_HISTORY"),
    (MISSING, "EXPLICIT_NONPARTICIPATION"): ("EXCLUDE", "PARTICIPATION_PRECEDENCE"),
    (ZERO, None): SELECT,
    (ZERO, "NAMED_STARTER"): SELECT,
    (ZERO, "NAMED_BACKUP"): BLOCK,
    (ZERO, "MATERIAL_ROLE_CHANGE"): BLOCK,
    (ZERO, "EXPLICIT_NONPARTICIPATION"): ("EXCLUDE", "PARTICIPATION_PRECEDENCE"),
}


@pytest.mark.parametrize(("state", "fact"), list(FACT_OUTCOMES))
def test_a_bound_fact_keeps_each_states_own_outcome(tmp_path, state, fact):
    world = _world(tmp_path, state)
    evidence = ds._roles(world, tmp_path, fact) if fact else None
    action, code, found = _outcome(world, {world[-1]}, role_evidence=evidence)
    assert (action, code) == FACT_OUTCOMES[(state, fact)]
    if found is not None:
        assert found["declared_fact"] == fact


# --------------------------------------------------------------------------- #
# Acceptance 4: an unresolved role change and a non-quarterback stay exactly as before
# --------------------------------------------------------------------------- #

TRANSFER_PRIOR = {"basis": "OWN_OLD_TEAM_SHARE", "old_teams": ["SEA"], "own_old_share": 0.21}


@pytest.mark.parametrize(
    ("extra", "expected"),
    [
        pytest.param({"incompatible_transfer": True, "transfer_prior": TRANSFER_PRIOR},
                     ("DIAGNOSTIC", "OFFENSIVE_TRANSFER_PRIOR_UNVERIFIED"), id="transfer-with-a-prior"),
        pytest.param({"incompatible_transfer": True},
                     ("BLOCK", "OFFENSIVE_TRANSFER_REQUIRES_CURRENT_TEAM_ROLE"), id="transfer-without-a-prior"),
        pytest.param({}, BLOCK, id="role-unknown-without-a-transfer"),
    ],
)
def test_a_declared_quarterback_with_an_unresolved_role_change_is_not_widened_to(tmp_path, extra, expected):
    # A declared quarterback with positive share, so only the history state keeps him out of the new branch.
    world = _world(tmp_path, "CURRENT_ROLE_UNKNOWN", history_extra=extra)
    action, code, _found = _outcome(world, {world[-1]})
    assert (action, code) == expected


@pytest.mark.parametrize("state", STATES)
def test_a_declared_non_quarterback_with_an_all_zero_or_missing_record_stays_excluded(tmp_path, state):
    slate, model, *rest = _world(tmp_path, state)
    rb = depth._person(slate, "KC Committee RB")
    # Keep the starter's own entry: his row is `UNKNOWN` under missing history, and without an entry the gate blocks him.
    # Give the back a quarterback share too, so only the position guard (not the positive-share guard) keeps him out.
    players = tuple(replace(p, qb_attempt_share=1.0) if p.underlying_id == rb else p for p in model.players)
    model = replace(
        model, players=players, offensive_history_by_person={**model.offensive_history_by_person, rb: _history(state)}
    )
    world = (slate, model, *rest[:-1], rb)
    action, code, _found = _outcome(world, {rb})
    assert (action, code) == ("EXCLUDE", EXCLUDE_CODE[state])


# --------------------------------------------------------------------------- #
# Acceptance 5: no declared starters, and an empty quarterback pool under allocation v1
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("state", STATES)
def test_with_no_declared_starters_the_gate_is_exactly_what_it_was(tmp_path, state):
    world = _world(tmp_path, state)
    action, code, _found = _outcome(world, ())
    assert (action, code) == ("EXCLUDE", EXCLUDE_CODE[state])


EXCLUDED_TEXT = {
    MISSING: "Excluded with zero share: no prior-season rows. Capture a numerical current-team allocation,"
             " or a registered rookie prior, to select this person.",
    ZERO: "Capture current opportunity evidence before selecting this historically zero person.",
}


@pytest.mark.parametrize("refused", [None, REFUSED])
@pytest.mark.parametrize("state", STATES)
def test_allocation_v1_leaves_an_empty_pool_at_zero_so_the_starter_stays_excluded_by_name(tmp_path, state, refused):
    extra = {"gap_fill_refused": refused} if refused else {}
    world = _world(
        tmp_path, state, history_extra=extra, backup_share=0.0,
        transformation=depth.TRANSFORMATION_VERSION, allocation=depth.ALLOCATION_VERSION,
    )
    _lineups, scores, report = ds._select(world)
    finding = ds._finding(report, world[-1])
    assert finding["selection_action"] == "EXCLUDE" and finding["finding"] == EXCLUDE_CODE[state]
    assert finding["next_evidence_action"] == (
        EXCLUDED_TEXT[state] + NO_DEPTH_SHARE + (f" Current-season gap-fill refused: {refused}." if refused else "")
    )
    assert world[-1] not in scores.by_person


@pytest.mark.parametrize("state", STATES)
def test_an_empty_quarterback_pool_gives_the_declared_starter_the_unit_share_under_allocation_v2(tmp_path, state):
    # Both Kansas City quarterbacks have nothing to conserve: the depth resolution gives the starter the unit share.
    world = _world(tmp_path, state, backup_share=0.0)
    lineups, scores, report = ds._select(world)
    finding = ds._finding(report, world[-1])
    assert finding["selection_action"] == "DIAGNOSTIC" and finding["state"] == state
    assert finding["after"]["qb_attempt_share"] == 1.0
    assert world[-1] in scores.by_person and lineups


@pytest.mark.parametrize("state", STATES)
def test_a_backup_the_resolver_promotes_over_an_out_starter_is_selectable_and_says_so(tmp_path, state):
    # R25: a DraftKings-unavailable published starter is stepped over and his backup is the effective starter.
    pool = tuple(
        (team, position, name, "OUT" if name == ds.NO_HISTORY else status, salary)
        for team, position, name, status, salary in depth._POOL
    )
    world = _world(tmp_path, state, pool=pool, no_history="KC Backup QB", qb_shares={ds.NO_HISTORY: 1.0})
    person = world[-1]
    _lineups, scores, report = ds._select(world)
    assert report["qb_depth_roles"]["starters_by_team"]["KC"] == person
    assert report["qb_depth_roles"]["effective_starter_promotions"]
    finding = ds._finding(report, person)
    assert finding["selection_action"] == "DIAGNOSTIC" and finding["finding"] == CODE and finding["state"] == state
    assert "effective starter for KC" in finding["next_evidence_action"]
    assert person in scores.by_person


# --------------------------------------------------------------------------- #
# The model row's own evidence state, and an explicit team allocation, still come first
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("row", ["PASS", "UNKNOWN", "STALE", "CONFLICTED"])
@pytest.mark.parametrize("state", STATES)
def test_the_rows_own_evidence_state_still_gates_an_observed_zero_person(tmp_path, state, row):
    # Session 54's branch never consulted the row (a missing-history row is `UNKNOWN` by construction). An all-zero
    # record's row is `PASS` by construction, so a stale, conflicted or unknown one keeps today's block.
    world = _world(tmp_path, state, row_evidence=row)
    expected = BLOCK if (state == ZERO and row != "PASS") else SELECT
    action, code, _found = _outcome(world, {world[-1]})
    assert (action, code) == expected


@pytest.mark.parametrize("state", STATES)
def test_an_explicit_team_allocation_still_decides_the_declared_starters_team(tmp_path, state):
    world = _world(tmp_path, state)
    slate = world[0]
    resolution = resolve_qb_depth_roles(slate, world[1], world[2], evidence_path=world[4], as_of=depth.AS_OF)
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
    action, code, _found = _outcome(world, {world[-1]}, role_evidence=path)
    assert (action, code) == ("SELECT", "EXPLICIT_TEAM_ALLOCATION")


# --------------------------------------------------------------------------- #
# The Classic exit: the gate sits below every `prior_review` exit, and no test reached it through one
# --------------------------------------------------------------------------- #


def _write_json(path, payload):
    path.write_bytes((json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8"))


def test_a_classic_run_selects_an_observed_zero_declared_starter_and_moves_no_release_truth(tmp_path, monkeypatch):
    # The Classic depth-package helper writes its provider ids into the Session 54 module's table; restore it.
    monkeypatch.setattr(depth, "_GSIS", dict(depth._GSIS))
    monkeypatch.setattr(classic, "_salary_bytes", classic_judgment._salary_with(classic_judgment.DEPTH, {}))
    salary, entry, package, _role, _status, _inactive = classic._fixture(tmp_path, depth=classic_judgment.DEPTH)
    slate = parse_salaries(salary)
    person = "NE|QB|NE QB One"  # his team's rank 1 in the depth package below
    provider = next(f"GSIS-C1-{i:04d}" for i, p in enumerate(slate.players, start=1) if p.underlying_id == person)
    # Rewrite his record to an all-zero one (his backup still holds the pool) and re-hash the package.
    player_path = package / "player_prior.json"
    payload = json.loads(player_path.read_text(encoding="utf-8"))
    record = next(r for r in payload["records"] if r["provider_player_id"] == provider)
    for key in ("qb_attempt_weight", "carry_weight", "target_weight", "rushing_td_weight", "receiving_td_weight",
                "role_capacity"):
        record[key] = 0.0
    payload["metadata"]["coverage"]["offensive_history_by_person"][person] = {
        "state": ZERO, "current_team": "NE", "receiving_efficiency_observed": False,
    }
    _write_json(player_path, payload)
    manifest_path = package / "prior_package.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"]["player_prior.json"] = sha256_file(player_path)
    _write_json(manifest_path, manifest)

    outcome = run_prior_review(
        salary_csv=salary, entry_csv=entry, label="s58-classic", as_of=classic.AS_OF,
        run_root=tmp_path / "run", output_root=tmp_path / "out", prior_package_dir=package,
        qb_depth_role_evidence_json=classic_judgment._qb_package(tmp_path, slate),
    )
    assert not outcome.blocked, outcome.blockers
    selection = outcome.reports["selection"]
    inner = selection["selection"]
    finding = next(f for f in inner["offensive_roles"]["findings"] if f["person"] == person)
    assert (finding["selection_action"], finding["finding"]) == ("DIAGNOSTIC", CODE)
    assert finding["state"] == ZERO and finding["history_state"] == ZERO
    coverage = json.loads(Path(outcome.artifacts["complete_slate_coverage"]).read_text(encoding="utf-8"))
    check = coverage["judgment_pass"]["starters_check"]
    (starter,) = [s for s in check["starters"] if s["team"] == "NE"]
    assert starter["person"] == person and starter["scored"] is True and starter["selectable"] is True
    assert starter["smallest_evidence_action"] == finding["next_evidence_action"]
    assert inner["qb_depth_roles"]["evidence_sha256"] in finding["next_evidence_action"]
    assert "every share in it is zero" in finding["next_evidence_action"]
    assert check["missing_from_scored_pool"] == []
    assert [r["reason"] for r in coverage["pool_coverage"]["people"] if r["person"] == person] == ["SELECTABLE"]
    assert (selection["MODEL_STATUS"], selection["RELEASE_DECISION"]) == ("PRIOR_ONLY", "DO_NOT_UPLOAD")
