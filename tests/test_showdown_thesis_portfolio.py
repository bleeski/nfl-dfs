"""Session 23c (chunk P8, R33 and R34): a portfolio of Showdown game theses.

Layers, each proved here before the code that makes it true:

1. The contract: `nfl_showdown_portfolio_policy_v4` carries several theses, each with a `row_weight`; the entries are
   allotted across the active theses by largest remainder (ties by declared order); each thesis has its own effective
   structural bounds; v3 is untouched.
2. The bank and the joint solve: every candidate names the theses it follows, one solve picks every row under the
   per-thesis quotas, every lineup is distinct across theses and against prefilled rosters, and the portfolio-wide share
   limit holds.
3. The ladder: a thesis no lineup can follow is dropped by name and its rows go to the others; none is ever relaxed.
4. The audit and the measures: every roster is recomputed against its thesis; the review numbers (R34) are recomputed.
5. The NE@SEA acceptance on the real salary bytes.

A thesis is a choice, not a forecast; nothing here calls one likely, calibrated or +EV.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from nfl_dfs.portfolio_policy import (
    POLICY_SCHEMA_VERSION_V3,
    POLICY_SCHEMA_VERSION_V4,
    canonical_decimal_json_bytes,
    portfolio_policy_template,
    validate_portfolio_policy_bytes,
)
from nfl_dfs.showdown_theses import allot_rows

from .test_showdown_theses import _people, _prepared, _thesis


# ------------------------------------------------------------------ helpers


def _three(slate):
    """Three structurally different theses on the synthetic NE@SEA slate, in declared (priority) order."""

    return [
        _thesis(slate, ["Starter QB", "Alpha WR"], name="NE_WIN_BIG", teams=["NE"]),
        _thesis(slate, ["NE Kicker", "Patriots"], name="NE_WIN_CLOSE_LOW", teams=["NE"]),
        _thesis(slate, ["Sea QB", "Sea Alpha WR"], name="SEA_WIN_BIG", teams=["SEA"]),
    ]


def _validate_v4(slate, theses, entry_ids, *, external=(), schema=POLICY_SCHEMA_VERSION_V4, **controls):
    document = portfolio_policy_template(
        slate, entry_ids, schema_version=schema,
        controls={"structural_bounds": {}, **controls, "theses": theses})
    raw = canonical_decimal_json_bytes(document)
    return validate_portfolio_policy_bytes(
        raw, slate=slate, entry_ids=entry_ids, externally_excluded_people=external), raw


def _policy_v4(slate, theses, entry_ids, **controls):
    validation, raw = _validate_v4(slate, theses, entry_ids, **controls)
    assert validation.valid, validation.blockers()
    return validation.policy, raw


SIX = ("1", "2", "3", "4", "5", "6")


# ------------------------------------------------------------------ allotment


def test_allot_rows_is_largest_remainder_with_ties_by_declared_order():
    # 6 rows over weights 1, 1, 2: shares 1.5, 1.5, 3.0. One row is left and the tie goes to the earlier thesis.
    assert allot_rows([("A", 1), ("B", 1), ("C", 2)], 6) == {"A": 2, "B": 1, "C": 3}
    # 20 rows over eight equal weights: 2.5 each, so the first four in declared order take the extra row.
    names = [f"T{index}" for index in range(8)]
    rows = allot_rows([(name, 1) for name in names], 20)
    assert [rows[name] for name in names] == [3, 3, 3, 3, 2, 2, 2, 2] and sum(rows.values()) == 20
    # Weights are a preference for rows and nothing else: doubling every weight changes nothing.
    assert allot_rows([("A", 2), ("B", 2), ("C", 4)], 6) == {"A": 2, "B": 1, "C": 3}


def test_allot_rows_gives_every_row_to_someone_and_fewer_rows_than_theses_favour_the_earliest():
    rows = allot_rows([("A", 1), ("B", 1), ("C", 1), ("D", 1)], 3)
    assert rows == {"A": 1, "B": 1, "C": 1, "D": 0}
    assert allot_rows([("ONLY", 5)], 7) == {"ONLY": 7}
    assert sum(allot_rows([("A", 3), ("B", 7), ("C", 11)], 20).values()) == 20


# ------------------------------------------------------------------ the v4 contract


def test_v4_accepts_several_theses_and_writes_rows_weights_and_effective_bounds(tmp_path):
    slate, *_rest = _prepared(tmp_path)
    theses = _three(slate)
    theses[2]["row_weight"] = 2
    policy, _raw = _policy_v4(slate, theses, SIX)
    assert [(item.name, item.row_weight, item.rows) for item in policy.theses] == [
        ("NE_WIN_BIG", 1, 2), ("NE_WIN_CLOSE_LOW", 1, 1), ("SEA_WIN_BIG", 2, 3)]
    assert all(item.active for item in policy.theses)
    assert policy.thesis_schema == "v4" and [item.name for item in policy.active_theses] == [
        "NE_WIN_BIG", "NE_WIN_CLOSE_LOW", "SEA_WIN_BIG"]
    mapping = policy.as_mapping()
    assert mapping["schema_version"] == "nfl_showdown_portfolio_policy_normalized_v4"
    written = mapping["controls"]["theses"]
    assert [item["rows"] for item in written] == [2, 1, 3] and [item["row_weight"] for item in written] == [1, 1, 2]
    assert all(item["effective_bounds"] == policy.structural_bounds.as_mapping() for item in written)


def test_a_policy_without_a_weight_gives_every_thesis_the_same_weight(tmp_path):
    slate, *_rest = _prepared(tmp_path)
    policy, _raw = _policy_v4(slate, _three(slate), SIX)
    assert [item.row_weight for item in policy.theses] == [1, 1, 1] and [item.rows for item in policy.theses] == [2, 2, 2]


def test_v3_stays_one_thesis_and_its_bytes_carry_no_weight_or_rows(tmp_path):
    slate, *_rest = _prepared(tmp_path)
    one = _thesis(slate, ["NE Kicker"])
    validation, _raw = _validate_v4(slate, [one], ("1", "2"), schema=POLICY_SCHEMA_VERSION_V3)
    assert validation.valid, validation.blockers()
    thesis = validation.policy.theses[0]
    assert thesis.row_weight is None and "row_weight" not in thesis.source_mapping()
    assert validation.policy.thesis_schema == "v3"
    written = validation.policy.as_mapping()
    assert written["schema_version"] == "nfl_showdown_portfolio_policy_normalized_v3"
    assert set(written["controls"]["theses"][0]).isdisjoint({"row_weight", "rows", "effective_bounds"})


def test_v3_refuses_two_theses_and_points_at_v4(tmp_path):
    slate, *_rest = _prepared(tmp_path)
    thesis = _thesis(slate, ["NE Kicker"])
    validation, _raw = _validate_v4(slate, [thesis, {**thesis, "name": "OTHER"}], ("1",), schema=POLICY_SCHEMA_VERSION_V3)
    assert [issue.code for issue in validation.problems] == ["PORTFOLIO_POLICY_THESIS_INVALID"]
    assert "v4" in validation.problems[0].message


def test_row_weight_is_a_v4_field_only(tmp_path):
    slate, *_rest = _prepared(tmp_path)
    validation, _raw = _validate_v4(slate, [{**_thesis(slate, ["NE Kicker"]), "row_weight": 2}], ("1",),
                                    schema=POLICY_SCHEMA_VERSION_V3)
    assert [issue.code for issue in validation.problems] == ["PORTFOLIO_POLICY_UNKNOWN_FIELD"]


def test_a_v4_policy_with_one_thesis_gives_it_every_row(tmp_path):
    slate, *_rest = _prepared(tmp_path)
    policy, _raw = _policy_v4(slate, [_thesis(slate, ["NE Kicker"], name="ONLY")], SIX)
    assert [item.rows for item in policy.theses] == [6]


def test_a_thesis_the_entries_cannot_give_a_row_is_dropped_and_named(tmp_path):
    slate, *_rest = _prepared(tmp_path)
    validation, _raw = _validate_v4(slate, _three(slate), ("1", "2"))
    assert validation.valid, validation.blockers()
    by_name = {item.name: item for item in validation.policy.theses}
    assert [by_name[name].rows for name in ("NE_WIN_BIG", "NE_WIN_CLOSE_LOW", "SEA_WIN_BIG")] == [1, 1, 0]
    dropped = by_name["SEA_WIN_BIG"]
    assert not dropped.active and "row" in dropped.dropped_reason
    assert any(issue.code == "THESIS_DROPPED" and "SEA_WIN_BIG" in issue.message for issue in validation.findings)


def test_a_thesis_dropped_at_validation_gives_its_rows_to_the_others(tmp_path):
    slate, *_rest = _prepared(tmp_path)
    # Its only Captain is unavailable, so it is dropped; the other two share every one of the six rows.
    theses = _three(slate)
    theses[1] = _thesis(slate, ["NE Kicker"], name="NE_WIN_CLOSE_LOW", teams=["NE"])
    validation, _raw = _validate_v4(slate, theses, SIX, external=(_people(slate)["NE Kicker"]["underlying_id"],))
    assert validation.valid, validation.blockers()
    by_name = {item.name: item for item in validation.policy.theses}
    assert not by_name["NE_WIN_CLOSE_LOW"].active
    assert by_name["NE_WIN_BIG"].rows + by_name["SEA_WIN_BIG"].rows == 6
    assert by_name["NE_WIN_CLOSE_LOW"].rows == 0


@pytest.mark.parametrize("mutate, code", [
    (lambda theses: [theses[0], {**theses[1], "name": theses[0]["name"]}], "PORTFOLIO_POLICY_THESIS_INVALID"),
    (lambda theses: [{**theses[0], "row_weight": 0}, theses[1]], "PORTFOLIO_POLICY_THESIS_INVALID"),
    (lambda theses: [{**theses[0], "row_weight": -3}, theses[1]], "PORTFOLIO_POLICY_THESIS_INVALID"),
    (lambda theses: [{**theses[0], "row_weight": True}, theses[1]], "PORTFOLIO_POLICY_THESIS_INVALID"),
    (lambda theses: [{**theses[0], "row_weight": Decimal("1.5")}, theses[1]], "PORTFOLIO_POLICY_THESIS_INVALID"),
    (lambda theses: [{**theses[0], "row_weight": "2"}, theses[1]], "PORTFOLIO_POLICY_THESIS_INVALID"),
    (lambda theses: [{**theses[0], "row_weight": 1000}, theses[1]], "PORTFOLIO_POLICY_THESIS_INVALID"),
    (lambda theses: [{**theses[0], "odds": "likely"}, theses[1]], "PORTFOLIO_POLICY_UNKNOWN_FIELD"),
    (lambda theses: [], "PORTFOLIO_POLICY_THESIS_INVALID"),
    (lambda theses: [theses[0], "NE_WIN_BIG"], "PORTFOLIO_POLICY_OBJECT_REQUIRED"),
])
def test_a_malformed_v4_thesis_list_is_refused_by_name(tmp_path, mutate, code):
    slate, *_rest = _prepared(tmp_path)
    validation, _raw = _validate_v4(slate, mutate(_three(slate)[:2]), ("1", "2", "3", "4"))
    assert code in [issue.code for issue in validation.problems]
    assert validation.policy is None or not validation.valid


def test_each_thesis_widens_the_bounds_for_its_own_rows_only(tmp_path):
    slate, *_rest = _prepared(tmp_path)
    theses = [
        _thesis(slate, ["NE Kicker"], name="DEFENSIVE_BATTLE", teams=["NE", "SEA"],
                position_bounds=[{"position": "K", "minimum": 2, "maximum": 2}]),
        _thesis(slate, ["Starter QB"], name="NE_WIN_BIG", teams=["NE"]),
    ]
    validation, _raw = _validate_v4(slate, theses, ("1", "2", "3", "4"), structural_bounds={"kicker_count": 1})
    assert validation.valid, validation.blockers()
    policy = validation.policy
    bounds = {item.name: item.effective_bounds for item in policy.theses}
    # The second kicker is the defensive battle's own; nothing else on the slate asked for it.
    assert bounds["DEFENSIVE_BATTLE"].kicker_count_maximum == 2
    assert bounds["NE_WIN_BIG"].kicker_count_maximum == 1
    assert policy.structural_bounds.kicker_count_maximum == 1  # the policy's declared bound is never rewritten
    assert any(issue.code == "PORTFOLIO_POLICY_THESIS_OVERRIDES_BOUND" and "DEFENSIVE_BATTLE" in issue.message
               for issue in validation.findings)


def test_a_thesis_whose_captains_the_caps_starve_is_a_capacity_issue_for_its_own_rows(tmp_path):
    slate, *_rest = _prepared(tmp_path)
    # Five entries over weights 3 and 2; a Captain cap of 0.4 lets each Captain open two rows. The first thesis has
    # one Captain and three rows, so its rows cannot be filled whatever the other thesis does.
    theses = [{**_thesis(slate, ["NE Kicker"], name="A"), "row_weight": 3},
              {**_thesis(slate, ["Starter QB", "Sea QB"], name="B"), "row_weight": 2}]
    validation, _raw = _validate_v4(
        slate, theses, ("1", "2", "3", "4", "5"),
        max_captain_exposure={"default_fraction": Decimal("0.4"), "overrides": []})
    assert [issue.code for issue in validation.problems] == ["PORTFOLIO_POLICY_THESIS_CAPACITY_INSUFFICIENT"]
    assert "'A'" in validation.problems[0].message
