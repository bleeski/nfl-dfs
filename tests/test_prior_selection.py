"""Prior-only scoring, selection and review-export coverage.

Fixtures are shared with `test_participation` so the pool, the statuses and the
shares are described in one place. Assertions here are about arithmetic that
must reconcile, about the solver never reaching an unavailable person, and about
the export refusing to write anything it has not audited.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import replace
from pathlib import Path

import pytest

from nfl_dfs.dk import parse_entries, parse_salaries
from nfl_dfs.kicker_roles import (
    KICKER_ROLE_ALLOCATION_VERSION,
    KickerRoleResolution,
)
from nfl_dfs.participation import build_participation_contract, redistribute_opportunity
from nfl_dfs.prior_score import (
    PriorScoreError,
    read_team_splits,
    score_pool,
    team_volumes,
)
from nfl_dfs.review_export import (
    ReviewExportError,
    export_review_entries,
    write_assignments_csv,
)
from nfl_dfs.selection import (
    SelectionError,
    assignments_for_entries,
    select_prior_lineups,
)

from .test_participation import _POOL, _model, _salary_bytes, _slate


PRIOR_SEASON = 2025

_SPLIT_COLUMNS = (
    "season", "week", "team", "season_type", "passing_tds", "rushing_tds",
    "passing_interceptions", "fumbles_lost_total", "pat_made", "pat_att",
    "fg_made_0_19", "fg_made_20_29", "fg_made_30_39", "fg_made_40_49",
    "fg_made_50_59", "fg_made_60_",
)


def _splits_bytes(*, weeks: int = 17, teams=("NE", "SEA")) -> bytes:
    rows = []
    for team in teams:
        for week in range(1, weeks + 1):
            rows.append(
                (
                    str(PRIOR_SEASON), str(week), team, "REG",
                    "2", "1", "1", "1", "3", "3",
                    "0", "0", "1", "1", "0", "0",
                )
            )
        # Postseason must not be counted.
        rows.append((str(PRIOR_SEASON), "1", team, "POST", "9", "9", "9", "9", "9", "9",
                     "9", "9", "9", "9", "9", "9"))
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(_SPLIT_COLUMNS)
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _splits(tmp_path, **kwargs):
    path = tmp_path / "stats_team_week.csv"
    path.write_bytes(_splits_bytes(**kwargs))
    return read_team_splits(path, prior_season=PRIOR_SEASON, teams=("NE", "SEA"))


def _entries_bytes(entry_ids=("900000001", "900000002")) -> bytes:
    header = (
        "Entry ID", "Contest Name", "Contest ID", "Entry Fee",
        "CPT", "FLEX", "FLEX", "FLEX", "FLEX", "FLEX", "", "Instructions",
    )
    rows = [header]
    for index, entry_id in enumerate(entry_ids):
        rows.append(
            (entry_id, "Test Showdown (NE @ SEA)", "193391013", "$20",
             "", "", "", "", "", "", "", f"{index + 1}. instruction text")
        )
    rows.append(("", "", "", "", "", "", "", "", "", "", "", "trailing note"))
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _template(tmp_path, entry_ids=("900000001", "900000002")):
    path = tmp_path / "DKEntries.csv"
    path.write_bytes(_entries_bytes(entry_ids))
    return parse_entries(path)


def _prepared(tmp_path):
    slate = _slate(tmp_path)
    model = _model(tmp_path, slate)
    contract = build_participation_contract(slate)
    reduced, _ = redistribute_opportunity(model, contract)
    return slate, reduced, contract, _splits(tmp_path)


# --------------------------------------------------------------------------- #
# Splits and volumes must reconcile with the artifacts they came from
# --------------------------------------------------------------------------- #


def test_team_splits_exclude_postseason_and_derive_three_ratios(tmp_path):
    splits = _splits(tmp_path)
    for team, split in splits.items():
        assert split.games == 17, team
        # 2 passing to 1 rushing touchdown per week.
        assert split.pass_touchdown_fraction == pytest.approx(2 / 3)
        assert split.interception_fraction == pytest.approx(0.5)
        assert split.pat_success_rate == pytest.approx(1.0)
        assert sum(split.field_goal_mix.values()) == pytest.approx(1.0)
        assert split.field_goal_mix["field_goals_0_39"] == pytest.approx(0.5)
        assert split.field_goal_mix["field_goals_40_49"] == pytest.approx(0.5)


def test_missing_split_columns_and_coverage_fail_closed(tmp_path):
    thin = tmp_path / "thin.csv"
    thin.write_bytes(b"season,week,team\n2025,1,NE\n")
    with pytest.raises(PriorScoreError, match="TEAM_SPLIT_COLUMNS_MISSING"):
        read_team_splits(thin, prior_season=PRIOR_SEASON, teams=("NE",))
    path = tmp_path / "stats.csv"
    path.write_bytes(_splits_bytes(teams=("NE",)))
    with pytest.raises(PriorScoreError, match="TEAM_SPLIT_COVERAGE_MISSING"):
        read_team_splits(path, prior_season=PRIOR_SEASON, teams=("NE", "SEA"))
    with pytest.raises(PriorScoreError, match="TEAM_SPLIT_COVERAGE_MISSING"):
        read_team_splits(path, prior_season=2024, teams=("NE",))


def test_team_volumes_reconcile_with_the_team_projection(tmp_path):
    slate, model, _contract, splits = _prepared(tmp_path)
    projections = {team.team: team for team in model.teams}
    volumes = team_volumes(model, splits)
    for team, volume in volumes.items():
        projection = projections[team]
        # Plays are dropbacks plus carries, and dropbacks are attempts plus sacks.
        assert volume.attempts + volume.sacks_allowed + volume.carries == pytest.approx(
            projection.plays_mean
        )
        assert volume.passing_touchdowns + volume.rushing_touchdowns == pytest.approx(
            projection.touchdowns_mean
        )
        assert volume.interceptions + volume.lost_fumbles == pytest.approx(
            projection.turnovers_mean
        )
        assert volume.field_goals == pytest.approx(projection.field_goals_mean)
    # The two implied totals are the game total.
    assert sum(v.implied_points for v in volumes.values()) == pytest.approx(
        projections["NE"].market_total
    )


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #


def test_captain_rows_are_exactly_one_and_a_half_times_flex(tmp_path):
    slate, model, _contract, splits = _prepared(tmp_path)
    scores = score_pool(slate, model, splits)
    by_person_role = {}
    for player in slate.players:
        if player.dk_id in scores.by_dk_id:
            by_person_role[(player.underlying_id, player.role)] = scores.by_dk_id[player.dk_id]
    people = {person for person, _role in by_person_role}
    assert people
    for person in people:
        flex = by_person_role[(person, "FLEX")]
        captain = by_person_role[(person, "CPT")]
        assert captain == pytest.approx(1.5 * flex), person


def test_kickers_and_defences_are_scored_from_real_artifact_fields(tmp_path):
    slate, model, _contract, splits = _prepared(tmp_path)
    scores = score_pool(slate, model, splits)
    # A kicker has no opportunity share at all, so a nonzero score can only
    # have come from the team's field-goal and touchdown volumes.
    kicker = scores.by_person["SEA|K|Sea Kicker"]
    assert kicker > 0
    defence = scores.by_person["SEA|DST|Seahawks"]
    assert defence > 0
    assert "DEFENSIVE_RETURN_TOUCHDOWNS_SAFETIES_AND_BLOCKED_KICKS_NOT_MODELLED" in (
        scores.omissions
    )


def test_two_eligible_kickers_do_not_duplicate_team_kicking_points(tmp_path):
    slate, model, _contract, splits = _prepared(tmp_path)
    ne_kicker = next(
        player for player in model.players if player.team == "NE" and player.position == "K"
    )
    backup_person = "NE|K|Backup Kicker"
    backup = replace(
        ne_kicker,
        underlying_id=backup_person,
        source_dk_id="99000002",
    )
    flex = next(
        player
        for player in slate.players
        if player.underlying_id == ne_kicker.underlying_id and player.role == "FLEX"
    )
    captain = next(
        player
        for player in slate.players
        if player.underlying_id == ne_kicker.underlying_id and player.role == "CPT"
    )
    two_kicker_slate = slate.model_copy(
        update={
            "players": (
                *slate.players,
                flex.model_copy(
                    update={
                        "dk_id": "99000002",
                        "name": "Backup Kicker",
                        "underlying_id": backup_person,
                    }
                ),
                captain.model_copy(
                    update={
                        "dk_id": "99000001",
                        "name": "Backup Kicker",
                        "underlying_id": backup_person,
                    }
                ),
            )
        }
    )
    two_kicker_model = replace(model, players=(*model.players, backup))

    roles = KickerRoleResolution(
        allocation_version=KICKER_ROLE_ALLOCATION_VERSION,
        shares_by_person={
            ne_kicker.underlying_id: 0.625,
            backup_person: 0.375,
            "SEA|K|Sea Kicker": 1.0,
        },
        zero_share_people=(),
        assumptions=(),
        coverage_gaps=(),
        team_allocations={
            "NE": {ne_kicker.underlying_id: 0.625, backup_person: 0.375},
            "SEA": {"SEA|K|Sea Kicker": 1.0},
        },
    )
    scores = score_pool(
        two_kicker_slate, two_kicker_model, splits, kicker_roles=roles
    )
    original = scores.by_person[ne_kicker.underlying_id]
    duplicated = scores.by_person[backup_person]

    assert original + duplicated == pytest.approx(8.4)
    assert original == pytest.approx(8.4 * 0.625)
    assert duplicated == pytest.approx(8.4 * 0.375)
    by_person_role = {
        (player.underlying_id, player.role): scores.by_dk_id[player.dk_id]
        for player in two_kicker_slate.players
        if player.dk_id in scores.by_dk_id
    }
    for person in (ne_kicker.underlying_id, backup_person):
        assert by_person_role[(person, "CPT")] == pytest.approx(
            1.5 * by_person_role[(person, "FLEX")]
        )


def test_the_metric_names_itself_honestly(tmp_path):
    slate, model, _contract, splits = _prepared(tmp_path)
    report = score_pool(slate, model, splits).as_report()
    assert report["metric"] == "DRAFTKINGS_POINTS_OF_THE_EXPECTED_STAT_LINE"
    assert report["not_a_claim_of"] == "EV_ROI_CEILING_OWNERSHIP_LEVERAGE_OR_EDGE"
    assert "threshold_note" in report


def test_scoring_is_deterministic(tmp_path):
    slate, model, _contract, splits = _prepared(tmp_path)
    first = score_pool(slate, model, splits).by_dk_id
    second = score_pool(slate, model, splits).by_dk_id
    assert first == second


def test_unavailable_people_are_absent_from_the_scored_pool(tmp_path):
    slate, model, contract, splits = _prepared(tmp_path)
    scores = score_pool(slate, model, splits)
    for person in contract.unavailable_people:
        assert person not in scores.by_person


# --------------------------------------------------------------------------- #
# Selection
# --------------------------------------------------------------------------- #


def test_selection_never_reaches_an_unavailable_person(tmp_path):
    slate, model, contract, splits = _prepared(tmp_path)
    lineups, _scores, report = select_prior_lineups(
        slate, model, splits, contract, count=2
    )
    by_id = {player.dk_id: player for player in slate.players}
    blocked = set(contract.unavailable_people)
    assert blocked
    for lineup in lineups:
        people = {by_id[dk_id].underlying_id for dk_id in lineup.roster}
        assert not people & blocked
        assert len(lineup.roster) == 6
        assert lineup.salary <= slate.salary_cap
        assert by_id[lineup.roster[0]].role == "CPT"
        assert all(by_id[dk].role == "FLEX" for dk in lineup.roster[1:])
        assert len({by_id[dk].team for dk in lineup.roster}) == 2
    assert report["never_calls"] == ["field.py", "economics.py", "portfolio economics"]


def test_entries_get_distinct_captains_and_limited_overlap(tmp_path):
    slate, model, contract, splits = _prepared(tmp_path)
    lineups, _scores, report = select_prior_lineups(
        slate, model, splits, contract, count=2, max_person_overlap=3
    )
    by_id = {player.dk_id: player for player in slate.players}
    assert len({lineup.captain_dk_id for lineup in lineups}) == 2
    first = {by_id[dk].underlying_id for dk in lineups[0].roster}
    second = {by_id[dk].underlying_id for dk in lineups[1].roster}
    assert len(first & second) <= 3
    assert report["differentiation"]["max_person_overlap"] == 3


def test_the_overlap_cap_actually_reduces_shared_personnel(tmp_path):
    slate, model, contract, splits = _prepared(tmp_path)
    by_id = {player.dk_id: player for player in slate.players}

    def shared(cap):
        lineups, _scores, _report = select_prior_lineups(
            slate, model, splits, contract, count=2, max_person_overlap=cap
        )
        first = {by_id[dk].underlying_id for dk in lineups[0].roster}
        second = {by_id[dk].underlying_id for dk in lineups[1].roster}
        return len(first & second), sum(l.prior_points for l in lineups)

    uncapped, uncapped_points = shared(None)
    capped, capped_points = shared(2)
    # The cap is the default because forbidding the exact roster alone leaves
    # nearly the same personnel available with a rotated captain. On the real
    # NE@SEA pool that measured six shared people out of six.
    assert capped <= 2
    assert capped < uncapped
    # Diversification is paid for in projection, and that trade is the point.
    assert capped_points <= uncapped_points


def test_selection_is_deterministic(tmp_path):
    slate, model, contract, splits = _prepared(tmp_path)
    first, _s, _r = select_prior_lineups(slate, model, splits, contract, count=2)
    second, _s, _r = select_prior_lineups(slate, model, splits, contract, count=2)
    assert [lineup.roster for lineup in first] == [lineup.roster for lineup in second]


def test_an_infeasible_pool_fails_closed_with_a_named_error(tmp_path):
    slate = _slate(tmp_path)
    model = _model(tmp_path, slate)
    splits = _splits(tmp_path)
    sea = [p.dk_id for p in slate.players if p.team == "SEA" and p.role == "FLEX"]
    contract = build_participation_contract(slate, operator_excluded_dk_ids=sea)
    with pytest.raises(SelectionError, match="SELECTABLE_POOL_INFEASIBLE"):
        select_prior_lineups(slate, model, splits, contract, count=1)


def test_a_bad_lineup_count_is_refused(tmp_path):
    slate, model, contract, splits = _prepared(tmp_path)
    with pytest.raises(SelectionError, match="LINEUP_COUNT_INVALID"):
        select_prior_lineups(slate, model, splits, contract, count=0)


def test_assignments_cycle_explicitly_when_entries_outnumber_lineups(tmp_path):
    slate, model, contract, splits = _prepared(tmp_path)
    lineups, _s, _r = select_prior_lineups(slate, model, splits, contract, count=2)
    assignments = assignments_for_entries(["a", "b", "c"], lineups)
    assert assignments["a"] == lineups[0].roster
    assert assignments["c"] == lineups[0].roster
    with pytest.raises(SelectionError, match="NO_RESERVED_ENTRIES"):
        assignments_for_entries([], lineups)


# --------------------------------------------------------------------------- #
# Review export
# --------------------------------------------------------------------------- #


def test_export_writes_a_byte_audited_file_and_changes_only_reserved_rows(tmp_path):
    slate, model, contract, splits = _prepared(tmp_path)
    template = _template(tmp_path)
    lineups, _s, _r = select_prior_lineups(slate, model, splits, contract, count=2)
    entry_ids = [entry.entry_id for entry in template.authorizations]
    assignments = assignments_for_entries(entry_ids, lineups)
    export = export_review_entries(
        slate=slate,
        template=template,
        assignments=assignments,
        output_path=tmp_path / "out" / "DK_REVIEW.csv",
    )
    assert export.file_valid
    assert export.problems == ()
    report = export.as_report()
    assert report["RELEASE_DECISION"] == "DO_NOT_UPLOAD"
    assert report["MODEL_STATUS"] == "PRIOR_ONLY"
    assert report["certification_basis"] == "NOT_CERTIFIED_REVIEW_EXPORT"
    assert "PAYOUT_AND_FIELD_ECONOMICS" in report["checks_not_run"]

    source = template.path.read_bytes().decode("utf-8").splitlines()
    written = Path(export.output_path).read_bytes().decode("utf-8").splitlines()
    assert len(source) == len(written)
    changed = [i for i, (a, b) in enumerate(zip(source, written)) if a != b]
    assert len(changed) == len(entry_ids)
    for index in changed:
        assert written[index].split(",")[0] in entry_ids


def test_export_refuses_an_illegal_lineup_and_writes_nothing(tmp_path):
    slate, _model, _contract, _splits = _prepared(tmp_path)
    template = _template(tmp_path)
    entry_ids = [entry.entry_id for entry in template.authorizations]
    # Six FLEX rows: no captain, so the lineup is illegal.
    flex = [p.dk_id for p in slate.players if p.role == "FLEX"][:6]
    target = tmp_path / "out" / "DK_REVIEW.csv"
    export = export_review_entries(
        slate=slate,
        template=template,
        assignments={entry_id: tuple(flex) for entry_id in entry_ids},
        output_path=target,
    )
    assert not export.file_valid
    assert any("LINEUP_" in problem for problem in export.problems)
    assert not target.exists()


def test_export_refuses_an_entry_set_that_does_not_match_the_template(tmp_path):
    slate, model, contract, splits = _prepared(tmp_path)
    template = _template(tmp_path)
    lineups, _s, _r = select_prior_lineups(slate, model, splits, contract, count=1)
    target = tmp_path / "out" / "DK_REVIEW.csv"
    export = export_review_entries(
        slate=slate,
        template=template,
        assignments={"999999999": lineups[0].roster},
        output_path=target,
    )
    assert not export.file_valid
    assert any("ENTRY_AUTHORIZATION_MISMATCH" in problem for problem in export.problems)
    assert not target.exists()


def test_export_will_not_overwrite(tmp_path):
    slate, model, contract, splits = _prepared(tmp_path)
    template = _template(tmp_path)
    lineups, _s, _r = select_prior_lineups(slate, model, splits, contract, count=2)
    entry_ids = [entry.entry_id for entry in template.authorizations]
    assignments = assignments_for_entries(entry_ids, lineups)
    target = tmp_path / "out" / "DK_REVIEW.csv"
    export_review_entries(
        slate=slate, template=template, assignments=assignments, output_path=target
    )
    with pytest.raises(ReviewExportError, match="OUTPUT_EXISTS"):
        export_review_entries(
            slate=slate, template=template, assignments=assignments, output_path=target
        )


def test_assignments_csv_round_trips_through_the_certify_format(tmp_path):
    slate, model, contract, splits = _prepared(tmp_path)
    lineups, _s, _r = select_prior_lineups(slate, model, splits, contract, count=2)
    assignments = assignments_for_entries(["900000001", "900000002"], lineups)
    path = tmp_path / "assignments.csv"
    digest = write_assignments_csv(path, assignments)
    assert len(digest) == 64
    from nfl_dfs.lineups import read_assignment_csv

    parsed = read_assignment_csv(path, slate.mode)
    assert parsed == assignments
