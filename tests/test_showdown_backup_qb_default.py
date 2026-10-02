"""Session 53 (R36): the backup-quarterback default for every Showdown run.

Ben, 2026-10-01: apply R33's backup-quarterback rule to every Showdown run, not only under
a thesis. PIT@CLE's engine baseline had captained a backup ($9k) and rostered another in three
lineups, because the rule ran only under a thesis and only when a depth package was supplied.

Each test is a fixture, never a model value. The depth package is synthetic and says so.
"""

from __future__ import annotations

import pytest

from nfl_dfs.portfolio_policy import POLICY_SCHEMA_VERSION_V2
from nfl_dfs.selection import select_prior_lineups

from . import test_qb_depth_roles as depth
from .test_showdown_theses import _both_quarterbacks, _policy, _row, _validate


def _plain_policy(slate, entry_ids):
    """A v2 policy: caps and structure, no thesis."""

    validation, _raw = _validate(slate, None, entry_ids, schema=POLICY_SCHEMA_VERSION_V2)
    assert validation.valid, validation.blockers()
    return validation.policy


def _backup(slate):
    return depth._person(slate, "KC Backup QB")


def _holds(slate, lineup, person):
    return person in {_row(slate, dk_id).underlying_id for dk_id in lineup.roster}


def _run(tmp_path, *, package=True, pool=None, count=6, policy=None, **kwargs):
    tmp_path.mkdir(parents=True, exist_ok=True)
    slate, model, contract, splits = (
        depth._setup(tmp_path, pool=pool) if pool is not None else depth._setup(tmp_path)
    )
    evidence = depth._package(tmp_path / "qb", slate, depth._orders()) if package else None
    chosen_policy = policy(slate) if policy is not None else None
    lineups, _scores, report = select_prior_lineups(
        slate, model, splits, contract,
        count=count, portfolio_policy=chosen_policy,
        qb_depth_role_evidence_json=evidence, as_of=depth.AS_OF, **kwargs,
    )
    return slate, lineups, report


# --------------------------------------------------------------------------- #
# Acceptance 1: no thesis, no policy
# --------------------------------------------------------------------------- #


def test_a_depth_chart_keeps_every_backup_out_of_a_run_with_no_policy_and_no_thesis(tmp_path):
    slate, lineups, report = _run(tmp_path)
    block = report["showdown_backup_qb_default"]
    assert block["applies"] is True
    assert block["excluded_people"] == [_backup(slate)]
    assert block["unevaluated_teams"] == []
    assert lineups and not any(_holds(slate, lineup, _backup(slate)) for lineup in lineups)


def test_the_default_removes_the_backups_rows_from_the_pool(tmp_path):
    # Beside the same run with no depth evidence: exactly the backup's CPT and FLEX rows more.
    _slate, _lineups, with_chart = _run(tmp_path / "with")
    _slate, _lineups, without = _run(tmp_path / "without", package=False)
    assert with_chart["excluded_rows"] == without["excluded_rows"] + 2


# --------------------------------------------------------------------------- #
# Acceptance 4: no evidence, nobody guessed out, the gap named
# --------------------------------------------------------------------------- #


def test_with_no_depth_chart_nothing_is_excluded_and_the_gap_is_named(tmp_path):
    _slate, lineups, report = _run(tmp_path, package=False)
    block = report["showdown_backup_qb_default"]
    assert block["excluded_people"] == []
    assert block["unevaluated_teams"] == ["DEN", "KC"]
    assert lineups


# --------------------------------------------------------------------------- #
# Acceptance 2: a plain policy, and a thesis that names a backup
# --------------------------------------------------------------------------- #


def test_a_plain_policy_gets_the_same_default(tmp_path):
    slate, lineups, report = _run(
        tmp_path, count=3, policy=lambda s: _plain_policy(s, ("1", "2", "3"))
    )
    assert report["showdown_backup_qb_default"]["excluded_people"] == [_backup(slate)]
    assert lineups and not any(_holds(slate, lineup, _backup(slate)) for lineup in lineups)


def test_a_thesis_that_names_a_backup_readmits_him_for_its_own_rows_only(tmp_path):
    slate, lineups, report = _run(
        tmp_path,
        count=2,
        policy=lambda s: _policy(
            s,
            _both_quarterbacks(
                s, excluded_people=["DEN Starter QB"], named_backup_quarterbacks=["KC Backup QB"]
            ),
            ("1", "2"),
        )[0],
    )
    backup = _backup(slate)
    block = report["showdown_backup_qb_default"]
    assert block["thesis_named_backups_readmitted_for_bound_rows"] == [backup]
    assert all(_holds(slate, lineup, backup) for lineup in lineups)


def test_a_thesis_backup_is_not_rostered_by_the_unbound_fill(tmp_path):
    # Bound rows first, then the fill: only the thesis's own rows may hold the backup it names.
    slate, lineups, _report = _run(
        tmp_path,
        count=2,
        fill_count=3,
        policy=lambda s: _policy(
            s,
            _both_quarterbacks(
                s, excluded_people=["DEN Starter QB"], named_backup_quarterbacks=["KC Backup QB"]
            ),
            ("1", "2"),
        )[0],
    )
    assert [_holds(slate, lineup, _backup(slate)) for lineup in lineups] == [True, True, False, False, False]


# --------------------------------------------------------------------------- #
# Acceptance 3: a team whose declared starter cannot be selected keeps its room
# --------------------------------------------------------------------------- #


def test_a_dk_out_starter_is_promoted_over_by_the_resolver_so_his_backup_is_the_starter(tmp_path):
    # R25: the resolver names the effective starter (the backup), so the default removes nobody on KC.
    pool = tuple(
        (team, position, name, "OUT" if name == "KC Starter QB" else status, salary)
        for team, position, name, status, salary in depth._POOL
    )
    slate, _lineups, report = _run(tmp_path, pool=pool)
    block = report["showdown_backup_qb_default"]
    assert report["qb_depth_roles"]["starters_by_team"]["KC"] == _backup(slate)
    # The OUT starter is the one now "behind" him; DraftKings had already excluded him. The backup stays.
    assert _backup(slate) not in block["excluded_people"]
    assert block["excluded_people"] == [depth._person(slate, "KC Starter QB")]


# --------------------------------------------------------------------------- #
# The report
# --------------------------------------------------------------------------- #


def test_the_report_says_the_default_applies_to_a_showdown_slate(tmp_path):
    # Classic's side (`applies` false, nobody excluded, no capture) is pinned through a real
    # Classic run in tests/test_prior_review_depth_capture.py.
    slate, _lineups, report = _run(tmp_path)
    assert report["showdown_backup_qb_default"]["applies"] is True
    assert slate.mode.value == "SHOWDOWN"
