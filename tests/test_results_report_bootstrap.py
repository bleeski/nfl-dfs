"""Session 71b: the registered slate-cluster bootstrap and each slice's minimum detectable effect.

`config/results_metrics_v1.json`'s `bootstrap` section, read exactly: pairs from 30 slates, the studentized wild cluster
bootstrap with Webb weights below, no interval below 5 slates, 10,000 resamples, a 90% interval, and the MDE at alpha
1/20 and power 4/5 through a pure-Python t quantile. Hand computations pin the arithmetic; every payload test uses 200
resamples so the suite stays fast.
"""

from __future__ import annotations

import dataclasses
import math
import random
from datetime import date, timedelta
from fractions import Fraction

import pytest

from nfl_dfs import contest_facts, entry_history
from nfl_dfs import results_report as rr
from tests.test_entry_history import _history, _row
from tests.test_results_report import TOP_HEAVY, _contest

REGISTERED = rr.load_results_metrics()
FAST = dataclasses.replace(REGISTERED, bootstrap={**REGISTERED.bootstrap, "resamples": 200})
STATISTICS = {"percentile_excess", "top_10_excess", "bottom_10_excess", "percentile_excess_blanks_removed",
              "top_10_excess_blanks_removed", "bottom_10_excess_blanks_removed", "realized_return_on_fees"}


def _slates(count: int, start: date = date(2026, 9, 10), first: int = 0) -> list[list[str]]:
    """One paid entry per slate, one slate a day, places spread over a field of 1,000; `first` keeps keys distinct."""

    return [_contest(first + index, (start + timedelta(days=index)).isoformat(), (37 * (first + index)) % 1000 + 1,
                     TOP_HEAVY) for index in range(count)]


def _payload(*rows: list[str], metrics: rr.ResultsMetrics = FAST, era: str | None = None) -> dict:
    raw = _history(*rows)
    return rr.build_report(entry_history.parse_entry_history(raw), metrics=metrics, source_sha256="0" * 64,
                           source_bytes=len(raw), engine_era_start=era, bootstrap=True)


# ----------------------------------------------------------------------------------------- the t quantile


@pytest.mark.parametrize(("probability", "df", "published"), [
    pytest.param(Fraction(39, 40), 4, "2.776445", id="t4-975"),
    pytest.param(Fraction(4, 5), 4, "0.940965", id="t4-80"),
    pytest.param(Fraction(39, 40), 16, "2.119905", id="t16-975"),
    pytest.param(Fraction(39, 40), 1, "12.706205", id="t1-975"),  # the Cauchy: an empty bracket, 2 theta / pi
    pytest.param(Fraction(39, 40), 2, "4.302653", id="t2-975"),
    pytest.param(Fraction(39, 40), 3, "3.182446", id="t3-975"),
    pytest.param(Fraction(39, 40), 54, "2.004879", id="t54-975"),
    pytest.param(Fraction(39, 40), 500, "1.964720", id="t500-975"),
])
def test_the_t_quantile_matches_published_values(probability, df, published):
    assert f"{rr.t_quantile(probability, df):.6f}" == published


def test_the_t_quantile_refuses_what_it_cannot_answer():
    for probability, df in ((Fraction(1, 2), 4), (Fraction(1), 4), (Fraction(39, 40), 0)):
        with pytest.raises(ValueError):
            rr.t_quantile(probability, df)


# ------------------------------------------------------------------------------- the arithmetic, by hand


def test_the_mde_follows_the_registered_alpha_and_power():
    # Y = 1, 2, 3, 4, 10 over five slates of one entry: theta 4, residuals -3, -2, -1, 0, 6, sum of squares 50.
    standard_error = rr.cr1_standard_error([-3.0, -2.0, -1.0, 0.0, 6.0], [1.0] * 5)
    assert f"{standard_error:.6f}" == "1.581139"  # sqrt(5/4 * 50) / 5
    effect = rr.minimum_detectable_effect(standard_error, 5, Fraction(1, 20), Fraction(4, 5))
    assert f"{effect:.4f}" == "5.8777"  # (t_4(0.975) + t_4(0.80)) * SE = 3.7174097 * 1.5811388 = 5.87774
    halved = rr.minimum_detectable_effect(standard_error, 5, Fraction(1, 10), Fraction(4, 5))
    assert halved < effect  # a looser alpha detects a smaller effect


def test_the_wild_t_statistic_matches_a_hand_computation():
    # e = -3,-2,-1,0,6 and v = 1,-1,1,-1,1: shift 4/5, e* = -3.8,1.2,-1.8,-0.8,5.2, SE* = sqrt(5/4 * 46.8) / 5.
    t_star = rr.wild_t([1.0, -1.0, 1.0, -1.0, 1.0], [-3.0, -2.0, -1.0, 0.0, 6.0], [1.0] * 5)
    assert f"{t_star:.6f}" == "0.522976"


def test_a_degenerate_draw_sits_at_infinity_and_is_counted():
    # Y = 2,2,2,2,0 over X = 1,1,1,1,4: theta 1, e = 1,1,1,1,-4, SE 0.625; v = 1,1,1,1,-1 makes every e* zero.
    assert rr.cr1_standard_error([1.0, 1.0, 1.0, 1.0, -4.0], [1.0, 1.0, 1.0, 1.0, 4.0]) == 0.625
    assert rr.wild_t([1.0, 1.0, 1.0, 1.0, -1.0], [1.0, 1.0, 1.0, 1.0, -4.0], [1.0, 1.0, 1.0, 1.0, 4.0]) == math.inf
    settings = rr.bootstrap_settings(FAST)
    few = rr.interval_figures(0.25, 0.5, [math.inf] * 5 + [0.0] * 195, settings)
    assert few["degenerate_resamples"] == 5 and few["interval"] is not None and few["reason"] is None
    many = rr.interval_figures(0.25, 0.5, [-math.inf] * 15 + [0.0] * 185, settings)
    assert (many["degenerate_resamples"], many["interval"], many["reason"]) == (15, None, "DEGENERATE_RESAMPLES")


def test_a_pairs_draw_with_no_shift_and_no_spread_has_no_sign_and_nulls_the_interval():
    # Theta 0 and a draw of only the first slate (Y 0, X 1): shift 0 and SE* 0, a t* of 0/0 that no sign can place.
    method, values, zero = rr.resample([0.0, 1.0, -1.0], [1.0, 1.0, 1.0], 0.0, rr.bootstrap_settings(FAST),
                                       random.Random(3).random, pairs=True)
    undefined = sum(math.isnan(value) for value in values)
    assert method == "PAIRS_CLUSTER_STUDENTIZED" and zero == 0 and 0 < undefined < 200
    figures = rr.interval_figures(0.0, 0.5, [math.nan] + [0.0] * 199, rr.bootstrap_settings(FAST))
    assert (figures["interval"], figures["reason"], figures["degenerate_resamples"]) == (
        None, "DEGENERATE_RESAMPLES", 1)


def test_the_floor_reason_names_the_registered_minimum():
    raised = dataclasses.replace(FAST, bootstrap={**FAST.bootstrap, "interval_min_slates": 6})
    figures = _payload(*_slates(5), metrics=raised)["scopes"]["nfl"]["overall"]["uncertainty"]["percentile_excess"]
    assert (figures["reason"], figures["interval"]) == ("FEWER_THAN_6_SLATES", None)


def test_a_zero_denominator_resample_is_named_never_dropped():
    # Unreachable from a report (every cluster has a positive denominator); the pairs loop still counts it.
    method, values, zero = rr.resample([0.0, 1.0], [0.0, 1.0], 1.0, rr.bootstrap_settings(FAST),
                                       random.Random(7).random, pairs=True)
    assert method == "PAIRS_CLUSTER_STUDENTIZED" and 0 < zero < 200 and len(values) == 200 - zero


def test_the_interval_takes_the_registered_order_statistics():
    assert rr.order_statistics(Fraction(9, 10), 10_000) == (499, 9499)
    assert rr.order_statistics(Fraction(9, 10), 200) == (9, 189)
    settings = rr.bootstrap_settings(FAST)
    values = [index / 100 for index in range(200)]  # t* sorted: q_lo = 0.09, q_hi = 1.89
    figures = rr.interval_figures(0.5, 0.1, values, settings)
    assert figures["interval"] == {"low": "31.1000", "high": "49.1000"}  # theta - q SE, in percent


# --------------------------------------------------------------------------------------- the payload


def test_the_bootstrap_is_seeded_and_wild_below_30():
    methods = {}
    for count in (4, 29, 30):
        overall = _payload(*_slates(count))["scopes"]["nfl"]["overall"]["uncertainty"]
        assert set(overall) == STATISTICS
        methods[count] = overall["percentile_excess"]
    assert methods[4]["slates"] == 4 and methods[4]["estimate"] is not None
    assert (methods[4]["method"], methods[4]["interval"], methods[4]["mde"], methods[4]["reason"]) == (
        None, None, None, "FEWER_THAN_5_SLATES")
    assert methods[29]["method"] == "WILD_WEBB_STUDENTIZED" and methods[29]["interval"] is not None
    assert methods[30]["method"] == "PAIRS_CLUSTER_STUDENTIZED" and methods[30]["interval"] is not None
    for figures in (methods[29], methods[30]):
        low, high = Fraction(figures["interval"]["low"]), Fraction(figures["interval"]["high"])
        assert low < high and figures["reason"] is None and Fraction(figures["mde"]) > 0
    rows = _slates(29)
    first = contest_facts.canonical_bytes(_payload(*rows))
    assert contest_facts.canonical_bytes(_payload(*rows)) == first
    reseeded = dataclasses.replace(FAST, bootstrap={**FAST.bootstrap, "seed": 1})
    assert contest_facts.canonical_bytes(_payload(*rows, metrics=reseeded)) != first


def test_a_slice_with_no_spread_is_named_zero_standard_error():
    # Every slate pays $10 on a $5 fee: the return is exactly 100% everywhere, so no residual is non-zero.
    figures = _payload(*_slates(6))["scopes"]["nfl"]["overall"]["uncertainty"]["realized_return_on_fees"]
    assert figures == {"slates": 6, "estimate": "100.0000", "method": None, "interval": None, "standard_error": None,
                       "mde": None, "reason": "ZERO_STANDARD_ERROR", "degenerate_resamples": 0}


@pytest.mark.parametrize(("count", "statistic", "method", "interval", "standard_error"), [
    pytest.param(29, "percentile_excess", "WILD_WEBB_STUDENTIZED", ("-11.6048", "6.8014"), "5.7756", id="wild"),
    pytest.param(29, "top_10_excess_blanks_removed", "WILD_WEBB_STUDENTIZED", ("-7.3189", "13.8395"), "6.5166",
                 id="wild-top"),
    pytest.param(30, "percentile_excess", "PAIRS_CLUSTER_STUDENTIZED", ("-12.5985", "8.7227"), "5.7451", id="pairs"),
    pytest.param(30, "top_10_excess_blanks_removed", "PAIRS_CLUSTER_STUDENTIZED", ("-1.7608", "21.6070"), "6.9205",
                 id="pairs-top"),
])
def test_the_written_intervals_are_pinned(count, statistic, method, interval, standard_error):
    # Pinned so any change to the draws, the weights, the seeding or the quantiles shows: a change to a written byte
    # takes a new writer version. Only correctly rounded operations reach these figures (the MDE is not pinned here).
    figures = _payload(*_slates(count))["scopes"]["nfl"]["overall"]["uncertainty"][statistic]
    assert (figures["method"], figures["standard_error"]) == (method, standard_error)
    assert (figures["interval"]["low"], figures["interval"]["high"]) == interval


def test_a_new_month_moves_no_earlier_month_row():
    before = _payload(*_slates(40, date(2026, 9, 1)))["scopes"]["nfl"]
    after = _payload(*_slates(40, date(2026, 9, 1)), *_slates(10, date(2026, 11, 1), first=100))["scopes"]["nfl"]
    months = [row["month"] for row in before["by_month"]]
    assert months == ["2026-09", "2026-10"]
    assert after["by_month"][:2] == before["by_month"]
    assert after["by_month"][2]["month"] == "2026-11"
    assert after["overall"]["uncertainty"] != before["overall"]["uncertainty"]  # the parent's data moved


def test_the_estimate_equals_the_exact_slice_figure():
    rows = [_contest(index, f"2026-09-{11 + index:02d}", 100 * (index + 1), TOP_HEAVY) for index in range(5)]
    overall = _payload(*rows)["scopes"]["nfl"]["overall"]
    # Places 100..500 of 1,000: mean percentile 0.3 against random 0.5005.
    assert overall["uncertainty"]["percentile_excess"]["estimate"] == "-20.0500"
    assert overall["uncertainty"]["realized_return_on_fees"]["estimate"] == overall["realized_return_on_fees"]
    standard_error = Fraction(overall["uncertainty"]["percentile_excess"]["standard_error"])
    # Excess per slate -0.4005 .. -0.0005, residuals -0.2, -0.1, 0, 0.1, 0.2: SE = sqrt(5/4 * 0.1) / 5 in points.
    assert abs(standard_error - Fraction(math.sqrt(0.125) / 5 * 100)) < Fraction(1, 10_000)


def test_an_all_blank_slate_is_no_cluster_of_a_blanks_removed_statistic():
    rows = _slates(5) + [_row(Entry_Key="4300000001", Contest_Key="130000001", Contest_Date_EST="2026-10-01 13:00:00",
                              Points="0")]
    overall = _payload(*rows)["scopes"]["nfl"]["overall"]["uncertainty"]
    assert (overall["percentile_excess"]["slates"], overall["percentile_excess_blanks_removed"]["slates"]) == (6, 5)


def test_an_empty_scope_has_null_uncertainty():
    era = _payload(*_slates(6), era="2027-01-01")["scopes"]["engine_era"]["overall"]["uncertainty"]
    for figures in era.values():
        assert figures == {"slates": 0, "estimate": None, "method": None, "interval": None, "standard_error": None,
                           "mde": None, "reason": "FEWER_THAN_5_SLATES", "degenerate_resamples": 0}


def test_by_slate_rows_carry_no_uncertainty_and_every_other_row_does():
    payload = _payload(*_slates(6))
    for scope in ("nfl", "engine_era"):
        block = payload["scopes"][scope]
        assert all("uncertainty" not in row for row in block["by_slate"])
        for name in ("by_format", "by_payout_shape", "by_field_size", "by_entry_fee", "by_month"):
            assert block[name] and all(set(row["uncertainty"]) == STATISTICS for row in block[name]), name
    assert "uncertainty" not in payload["all_sport_check"]["overall"]
    method = payload["bootstrap"]
    assert (method["resamples"], method["seed"], method["statistics"]) == (200, 20261010, sorted(STATISTICS))
    assert "bootstrap" not in rr.build_report(entry_history.parse_entry_history(_history(*_slates(6))), metrics=FAST,
                                              source_sha256="0" * 64, source_bytes=1)
