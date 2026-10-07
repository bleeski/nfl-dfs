"""Session 23c layer 4: the SD4 audit and the R34 measures for a portfolio of Showdown theses.

The audit reparses the normalized v4 policy, recomputes every roster against every thesis (each thesis's own rules,
bounds and backup-quarterback rule), checks the selector's claim of which thesis each lineup fills against what it
recomputed, and proves a quota-feasible assignment exists without trusting that claim. The claim is keyed by lineup
so it survives the contest step moving lineups between Entry IDs. The measures are the review's numbers (R34).
A thesis is a choice, not a forecast; leverage is unmeasured without an ownership input.
"""

from __future__ import annotations

import json
from collections import Counter
from itertools import combinations

import pytest

from nfl_dfs.hashing import sha256_bytes
from nfl_dfs.portfolio_enforcement import audit_policy_assignments
from nfl_dfs.portfolio_policy import canonical_decimal_json_bytes
from nfl_dfs.showdown_theses import thesis_portfolio_measures

from .test_showdown_theses import _prepared, _thesis
from .test_showdown_thesis_ladder import _select_portfolio
from .test_showdown_thesis_portfolio import _three

SIX = ("1", "2", "3", "4", "5", "6")


def _audit(tmp_path, slate, policy, raw, pairs, summary=None, *, normalized=None):
    artifact = ("Entry ID,CPT,FLEX,FLEX,FLEX,FLEX,FLEX\n"
                + "".join(",".join((entry, *roster)) + "\n" for entry, roster in pairs)).encode("utf-8")
    normalized = policy.canonical_bytes() if normalized is None else normalized
    entry_bytes = b"exact entry bytes"
    return audit_policy_assignments(
        slate=slate, policy=policy, assignments=pairs, salary_bytes=(tmp_path / "DKSalaries.csv").read_bytes(),
        entry_bytes=entry_bytes, expected_entry_sha256=sha256_bytes(entry_bytes), source_policy_bytes=raw,
        expected_source_policy_sha256=sha256_bytes(raw), normalized_policy_bytes=normalized,
        expected_normalized_policy_sha256=sha256_bytes(normalized), assignment_artifact_bytes=artifact,
        expected_assignment_artifact_sha256=sha256_bytes(artifact), selector_summary=summary)


def _pairs(lineups):
    return [(str(index), lineup.roster) for index, lineup in enumerate(lineups, 1)]


def _summary_for(slate, report, pairs):
    """The selector's own summary, relabelled to the entries the lineups now sit in (what `prior_review` does)."""

    by_id = {row.dk_id: row for row in slate.players}
    people = {entry: frozenset(by_id[dk_id].underlying_id for dk_id in roster) for entry, roster in pairs}
    entries = [entry for entry, _roster in pairs]
    return {**report, "pairwise_person_overlap": [
        {"entry_id_a": left, "entry_id_b": right, "people": len(people[left] & people[right])}
        for left, right in combinations(entries, 2)]}


@pytest.fixture
def built(tmp_path):
    slate, policy, raw, lineups, report = _select_portfolio(tmp_path, _three)
    return tmp_path, slate, policy, raw, lineups, report


def test_the_audit_passes_a_portfolio_and_names_each_entry_s_thesis(built):
    tmp_path, slate, policy, raw, lineups, report = built
    audit = _audit(tmp_path, slate, policy, raw, _pairs(lineups), report)
    assert audit.passed, audit.problems
    block = audit.as_report()["theses"]
    assert block["build_version"] == "showdown_thesis_portfolio_sd3_v1"
    assert {entry: item["thesis"] for entry, item in block["entries"].items()} == {
        str(index): lineup.thesis for index, lineup in enumerate(lineups, 1)}
    assert all(item["follows"] and item["broken_rules"] == [] for item in block["entries"].values())
    assert [(item["name"], item["rows"]) for item in block["theses"]] == [
        ("NE_WIN_BIG", 2), ("NE_WIN_CLOSE_LOW", 2), ("SEA_WIN_BIG", 2)]
    assert block["measures"]["by_thesis"]["NE_WIN_BIG"]["rows"] == 2


def test_the_audit_proves_a_quota_feasible_assignment_without_the_selectors_claim(built):
    tmp_path, slate, policy, raw, lineups, _report = built
    audit = _audit(tmp_path, slate, policy, raw, _pairs(lineups), None)
    assert audit.passed, audit.problems
    counts = Counter(item["thesis"] for item in audit.as_report()["theses"]["entries"].values())
    assert counts == {"NE_WIN_BIG": 2, "NE_WIN_CLOSE_LOW": 2, "SEA_WIN_BIG": 2}


def test_the_claim_follows_its_lineup_when_the_contest_step_moves_it_to_another_entry(built):
    tmp_path, slate, policy, raw, lineups, report = built
    moved = [(str(index), lineup.roster) for index, lineup in enumerate(reversed(lineups), 1)]
    audit = _audit(tmp_path, slate, policy, raw, moved, _summary_for(slate, report, moved))
    assert audit.passed, audit.problems
    entries = audit.as_report()["theses"]["entries"]
    assert {entry: item["thesis"] for entry, item in entries.items()} == {
        str(index): lineup.thesis for index, lineup in enumerate(reversed(lineups), 1)}


def test_the_audit_catches_a_lineup_claimed_for_a_thesis_it_does_not_follow(built):
    tmp_path, slate, policy, raw, lineups, report = built
    block = report["portfolio_policy"]["theses"]
    liar = next(lineup for lineup in lineups if lineup.thesis == "NE_WIN_BIG")
    forged = {**report, "portfolio_policy": {**report["portfolio_policy"], "theses": {
        **block, "by_lineup": {**block["by_lineup"], liar.canonical_key: "SEA_WIN_BIG"}}}}
    audit = _audit(tmp_path, slate, policy, raw, _pairs(lineups), forged)
    assert not audit.passed
    assert any(problem.startswith("PORTFOLIO_AUDIT_THESIS_VIOLATED:") and "thesis=SEA_WIN_BIG" in problem
               and problem.endswith("rule=captain_set") for problem in audit.problems)
    assert any(problem.startswith("PORTFOLIO_AUDIT_THESIS_ROWS_MISMATCH:") for problem in audit.problems)


def test_the_audit_refuses_a_claim_that_names_no_active_thesis(built):
    tmp_path, slate, policy, raw, lineups, report = built
    block = report["portfolio_policy"]["theses"]
    forged = {**report, "portfolio_policy": {**report["portfolio_policy"], "theses": {
        **block, "by_lineup": {**block["by_lineup"], lineups[0].canonical_key: "NO_SUCH_THESIS"}}}}
    audit = _audit(tmp_path, slate, policy, raw, _pairs(lineups), forged)
    assert any(problem.startswith("PORTFOLIO_AUDIT_THESIS_CLAIM_INVALID:") and "NO_SUCH_THESIS" in problem
               for problem in audit.problems)
    missing = {key: value for key, value in block["by_lineup"].items() if key != lineups[0].canonical_key}
    gone = {**report, "portfolio_policy": {**report["portfolio_policy"], "theses": {**block, "by_lineup": missing}}}
    assert any(problem.startswith("PORTFOLIO_AUDIT_THESIS_CLAIM_INVALID:")
               for problem in _audit(tmp_path, slate, policy, raw, _pairs(lineups), gone).problems)


def test_the_audit_refuses_a_thesis_that_got_more_or_fewer_rows_than_its_allotment(tmp_path):
    def twins(slate):
        first = _thesis(slate, ["Starter QB", "Alpha WR"], name="A", teams=["NE"])
        return [first, {**first, "name": "B"}]

    slate, policy, raw, lineups, report = _select_portfolio(tmp_path, twins)
    assert Counter(lineup.thesis for lineup in lineups) == {"A": 3, "B": 3}
    block = report["portfolio_policy"]["theses"]
    # Both theses follow every lineup, so a claim of four for A and two for B is followed but is not the allotment.
    skewed = dict(block["by_lineup"])
    for lineup in lineups:
        skewed[lineup.canonical_key] = "A"
    skewed[lineups[0].canonical_key] = "B"
    skewed[lineups[1].canonical_key] = "B"
    claim = {**report, "portfolio_policy": {**report["portfolio_policy"], "theses": {**block, "by_lineup": skewed}}}
    audit = _audit(tmp_path, slate, policy, raw, _pairs(lineups), claim)
    assert any(problem.startswith("PORTFOLIO_AUDIT_THESIS_ROWS_MISMATCH:") and "thesis=A" in problem
               and "actual=4" in problem and "rows=3" in problem for problem in audit.problems)


def _tampered(policy, mutate):
    payload = json.loads(policy.canonical_bytes().decode("utf-8"))
    mutate(payload)
    return canonical_decimal_json_bytes(payload)


def test_the_audit_refuses_a_normalized_policy_whose_rows_are_not_the_allotment(built):
    tmp_path, slate, policy, raw, lineups, report = built
    forged = _tampered(policy, lambda payload: payload["controls"]["theses"][0].update(rows=3))
    audit = _audit(tmp_path, slate, policy, raw, _pairs(lineups), report, normalized=forged)
    assert any(problem.startswith("PORTFOLIO_AUDIT_NORMALIZED_POLICY_INVALID:") and "allotment" in problem
               for problem in audit.problems)


def test_the_audit_refuses_a_normalized_policy_whose_effective_bounds_are_not_the_recomputed_widening(built):
    tmp_path, slate, policy, raw, lineups, report = built

    def widen(payload):
        payload["controls"]["theses"][0]["effective_bounds"]["kicker_count"] = 2

    audit = _audit(tmp_path, slate, policy, raw, _pairs(lineups), report, normalized=_tampered(policy, widen))
    assert any(problem.startswith("PORTFOLIO_AUDIT_NORMALIZED_POLICY_INVALID:") and "effective bounds" in problem
               for problem in audit.problems)


def test_a_lineup_is_checked_against_its_own_theses_bounds_not_another_s(tmp_path):
    def two_kickers(slate):
        both = [{"position": "K", "minimum": 2, "maximum": 2}]
        return [_thesis(slate, ["NE Kicker"], name="DEFENSIVE_BATTLE", teams=["NE", "SEA"], position_bounds=both),
                _thesis(slate, ["NE Kicker", "Starter QB"], name="NE_WIN_BIG", teams=["NE"])]

    slate, policy, raw, lineups, report = _select_portfolio(
        tmp_path, two_kickers, count=4, controls={"structural_bounds": {"kicker_count": 1}})
    assert {item.name: item.effective_bounds.kicker_count_maximum for item in policy.theses} == {
        "DEFENSIVE_BATTLE": 2, "NE_WIN_BIG": 1}
    by_id = {row.dk_id: row for row in slate.players}
    battle = [lineup for lineup in lineups if lineup.thesis == "DEFENSIVE_BATTLE"]
    assert battle and all(sum(by_id[dk_id].position == "K" for dk_id in lineup.roster) == 2 for lineup in battle)
    assert _audit(tmp_path, slate, policy, raw, _pairs(lineups), report).passed
    # Claim a two-kicker lineup for the other thesis: it opens with a kicker Captain that thesis allows, but its
    # own bounds still cap kickers at the policy's declared one.
    block = report["portfolio_policy"]["theses"]
    forged = {**report, "portfolio_policy": {**report["portfolio_policy"], "theses": {
        **block, "by_lineup": {**block["by_lineup"], battle[0].canonical_key: "NE_WIN_BIG"}}}}
    audit = _audit(tmp_path, slate, policy, raw, _pairs(lineups), forged)
    assert any("thesis=NE_WIN_BIG" in problem and problem.endswith("rule=structural_bounds.kicker_count")
               for problem in audit.problems)


def test_a_lineup_repeated_across_theses_fails_the_audit(built):
    tmp_path, slate, policy, raw, lineups, report = built
    repeated = [(str(index), lineups[0].roster if index == 2 else lineup.roster)
                for index, lineup in enumerate(lineups, 1)]
    audit = _audit(tmp_path, slate, policy, raw, repeated, None)
    assert any(problem.startswith("PORTFOLIO_AUDIT_CANONICAL_DUPLICATE:") for problem in audit.problems)


# ------------------------------------------------------------------ the R34 measures


def _ids(slate):
    return {(row.name, row.role): row.dk_id for row in slate.players}


def test_the_measures_name_the_captains_the_majority_people_and_the_rows_one_bad_night_sinks(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    slate, *_rest = _prepared(tmp_path)
    ids = _ids(slate)

    def roster(captain, *flex):
        return (ids[(captain, "CPT")], *(ids[(name, "FLEX")] for name in flex))

    # Legality is not this function's business: it counts the rosters it is given.
    entries = [
        ("1", roster("Starter QB", "Lead RB", "Alpha WR", "Patriots", "Sea QB", "Sea Alpha WR"), "NE_WIN_BIG"),
        ("2", roster("Alpha WR", "Starter QB", "Lead RB", "Patriots", "Sea QB", "Sea TE"), "NE_WIN_BIG"),
        ("3", roster("NE Kicker", "Starter QB", "Backup RB", "Starting TE", "Sea Kicker", "Seahawks"), "NE_WIN_CLOSE_LOW"),
        ("4", roster("Sea QB", "Sea Alpha WR", "Seahawks", "Sea Kicker", "Sea Backup RB", "Sea Third RB"), "SEA_WIN_BIG"),
    ]
    followed = {"1": ["NE_WIN_BIG"], "2": ["NE_WIN_BIG"], "3": ["NE_WIN_CLOSE_LOW"], "4": ["SEA_WIN_BIG"]}
    measures = thesis_portfolio_measures(
        slate, entries, allotment={"NE_WIN_BIG": 2, "NE_WIN_CLOSE_LOW": 1, "SEA_WIN_BIG": 1},
        followed=followed, broken={"3": ["position_bounds.K"]})
    assert measures["entries"]["1"] == {"thesis": "NE_WIN_BIG", "follows": True, "followed_by": ["NE_WIN_BIG"],
                                        "broken_rules": []}
    assert measures["entries"]["3"]["follows"] is False and measures["entries"]["3"]["broken_rules"] == ["position_bounds.K"]
    assert measures["by_thesis"]["NE_WIN_BIG"] == {
        "rows": 2, "entries": ["1", "2"], "captains": {"NE|QB|Starter QB": 1, "NE|WR|Alpha WR": 1}}
    # Four rows, four different Captains: no Captain over a quarter.
    assert measures["distinct_captains"] == 4 and measures["max_captain_share_percentage"] == 25.0
    assert measures["captains"]["NE|K|NE Kicker"] == {
        "count": 1, "share_percentage": 25.0, "theses": {"NE_WIN_CLOSE_LOW": 1}}
    # Starter QB is in rows 1, 2 and 3: more than half. Sea QB is in 1, 2 and 4: also more than half. Lead RB, in
    # two of four, is exactly half and not "more than half".
    assert measures["people_in_more_than_half"] == [
        {"person": "NE|QB|Starter QB", "rows": 3, "share_percentage": 75.0},
        {"person": "SEA|QB|Sea QB", "rows": 3, "share_percentage": 75.0}]
    assert measures["most_rows_one_player_sinks"] == {
        "rows": 3, "share_percentage": 75.0, "people": ["NE|QB|Starter QB", "SEA|QB|Sea QB"]}
    assert measures["most_rows_one_thesis_sinks"] == {"rows": 2, "theses": ["NE_WIN_BIG"]}
    assert "LEVERAGE_NO_OWNERSHIP_INPUT_SO_LEVERAGE_IS_UNMEASURED" in measures["does_not_establish"]


def test_the_measures_name_the_pairs_that_share_a_core_and_a_rotating_captain(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    slate, *_rest = _prepared(tmp_path)
    ids = _ids(slate)
    core = ("Lead RB", "Alpha WR", "Patriots", "Sea QB", "Sea Alpha WR")

    def roster(captain, *flex):
        return (ids[(captain, "CPT")], *(ids[(name, "FLEX")] for name in flex))

    entries = [
        ("1", roster("Starter QB", *core), "A"),
        ("2", roster("Lead RB", "Starter QB", *core[1:]), "A"),      # the same six people, Captain rotated
        ("3", roster("Starter QB", *core[:4], "Sea TE"), "A"),       # five of the same six people
        ("4", roster("NE Kicker", "Backup RB", "Starting TE", "Sea Kicker", "Seahawks", "Sea Third RB"), "B"),
    ]
    measures = thesis_portfolio_measures(
        slate, entries, allotment={"A": 3, "B": 1}, followed={}, broken={})
    pairs = {(item["entry_id_a"], item["entry_id_b"]): item for item in measures["same_core_pairs"]}
    assert set(pairs) == {("1", "2"), ("1", "3"), ("2", "3")}
    assert pairs[("1", "2")]["shared_people"] == 6 and pairs[("1", "2")]["captain_rotation"] is True
    assert pairs[("1", "3")]["shared_people"] == 5 and pairs[("1", "3")]["captain_rotation"] is False
    assert measures["people_in_more_than_half"] and measures["most_rows_one_thesis_sinks"]["theses"] == ["A"]


def test_the_measures_call_an_unassigned_lineup_what_it_is(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    slate, *_rest = _prepared(tmp_path)
    ids = _ids(slate)
    entries = [("1", (ids[("Starter QB", "CPT")], *(ids[(n, "FLEX")] for n in (
        "Lead RB", "Alpha WR", "Patriots", "Sea QB", "Sea Alpha WR"))), None)]
    measures = thesis_portfolio_measures(slate, entries, allotment={"A": 1}, followed={}, broken={})
    assert measures["entries"]["1"]["thesis"] is None and measures["entries"]["1"]["follows"] is False
