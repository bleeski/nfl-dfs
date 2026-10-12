"""Session 71: the NFL results report (`nfl_results_metrics_v1`, `nfl_results_report_v1`).

Realized results of past entries, read from the hash-named entry-history snapshot: the finishing percentile and the
tail rates beside each entry's random expectation, blanks, rollups by format, payout shape, field size, fee, month and
slate, the engine era, fee concentration and the all-sport check. Fixtures are synthetic bytes built with Session 69's
builders and written with `write_bytes` (Ben's real export carries account winnings and never enters the repository).
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from fractions import Fraction
from pathlib import Path

import pytest

from nfl_dfs import contest_facts, entry_history
from nfl_dfs import results_report as rr
from tests.test_entry_history import _history, _row

REPO = Path(__file__).resolve().parents[1]
METRICS_SHA256 = "56c471710421f5f4fca579a82409610f9c2b73d3dd7d8e0d80170538fa1f736c"
ZERO_SHA = "0" * 64

# Two paid Classic entries in one contest, a paid Showdown entry, and rows every NFL scope leaves out.
CLASSIC_A = _row()
CLASSIC_B = _row(Entry_Key="4000000002", Entry="NFL $5 Synthetic Classic (2/2)", Place="640", Points="88",
                 Winnings_Non_Ticket="$0.00")
SHOWDOWN = _row(Game_Type="Showdown Captain Mode", Entry_Key="4000000003", Contest_Key="100000002",
                Contest_Date_EST="2026-09-14 20:15:00", Place="1", Points="150", Winnings_Non_Ticket="$5.00",
                Winnings_Ticket="$3.00", Contest_Entries="10", Entry_Fee="$1.00", Prize_Pool="$9.00", Places_Paid="2")
BEST_BALL = _row(Game_Type="Best Ball", Entry_Key="4000000004", Contest_Key="100000003")
FREE = _row(Entry_Key="4000000005", Contest_Key="100000004", Entry_Fee="$0.00", Prize_Pool="$0.00")
MLB = _row(Sport="MLB", Entry_Key="4000000006", Contest_Key="100000005", Contest_Date_EST="2026-07-04 19:05:00",
           Place="3", Points="12", Winnings_Non_Ticket="$0.00", Contest_Entries="50", Entry_Fee="$1.00",
           Prize_Pool="$45.00", Places_Paid="10")
STANDARD = (CLASSIC_A, CLASSIC_B, SHOWDOWN, BEST_BALL, FREE, MLB)


def _report(*rows: list[str], era: str | None = None, metrics: rr.ResultsMetrics | None = None,
            source_bytes: int | None = None) -> dict:
    raw = _history(*rows)
    history = entry_history.parse_entry_history(raw)
    return rr.build_report(history, metrics=metrics or rr.load_results_metrics(), source_sha256=ZERO_SHA,
                           source_bytes=len(raw) if source_bytes is None else source_bytes, engine_era_start=era)


def _bytes(*rows: list[str], era: str | None = None, source_bytes: int | None = None) -> bytes:
    return contest_facts.canonical_bytes(_report(*rows, era=era, source_bytes=source_bytes))


def _by(rows: list[dict], key: str, value: object) -> dict:
    [found] = [row for row in rows if row[key] == value]
    return found


# ------------------------------------------------------------------------------- per-entry definitions


def test_each_rate_sits_beside_its_random_expectation():
    assert rr.finishing_percentile(12, 1000) == Fraction(12, 1000)
    assert rr.random_percentile(5) == Fraction(6, 10)
    assert rr.random_percentile(1000) == Fraction(1001, 2000)
    # A top-10% finish is impossible below 10 entries.
    assert [rr.random_top(n) for n in (5, 9, 10, 20)] == [0, 0, Fraction(1, 10), Fraction(1, 10)]
    assert not rr.in_top(1, 9) and rr.in_top(1, 10) and rr.in_top(2, 20) and not rr.in_top(3, 20)
    # A bottom-10% finish is 20% likely at five entries; n=10 separates a strict boundary from an inclusive one.
    assert [rr.random_bottom(n) for n in (5, 9, 10, 20)] == [Fraction(1, 5), Fraction(1, 9), Fraction(1, 10),
                                                            Fraction(1, 10)]
    assert rr.in_bottom(5, 5) and not rr.in_bottom(4, 5)
    assert rr.in_bottom(10, 10) and not rr.in_bottom(9, 10)
    assert rr.in_bottom(19, 20) and not rr.in_bottom(18, 20)
    assert rr.BOTTOM_STRICT is True
    # Every rates block carries its random expectation and the tie rule.
    rates = _report(*STANDARD)["scopes"]["nfl"]["overall"]["with_blanks"]
    assert set(rates) == {"entries", "tie_rule", "percentile", "top_10", "bottom_10"}
    for name in ("percentile", "top_10", "bottom_10"):
        assert set(rates[name]) == {"realized", "random"}


def test_a_blank_is_points_exactly_zero():
    assert rr.is_blank(0)
    assert not rr.is_blank(1) and not rr.is_blank(-50)
    rows = (
        _row(Points="0"),
        _row(Entry_Key="4000000002", Points="0.00", Place="900"),
        _row(Entry_Key="4000000003", Points="0.01", Place="899"),
        _row(Entry_Key="4000000004", Points="-0.5", Place="898"),
    )
    overall = _report(*rows)["scopes"]["nfl"]["overall"]
    assert overall["blanks"] == 2
    assert overall["with_blanks"]["entries"] == 4
    assert overall["blanks_removed"]["entries"] == 2
    # Blanks removed: places 899 and 898 of 1000.
    assert overall["blanks_removed"]["percentile"]["realized"] == "89.8500"


def test_ties_take_the_best_place_and_say_so():
    tied = (_row(Place="3", Points="150"), _row(Entry_Key="4000000002", Place="3", Points="150"))
    report = _report(*tied)
    rates = report["scopes"]["nfl"]["overall"]["with_blanks"]
    assert rates["percentile"]["realized"] == "0.3000"  # 3 / 1000 for both, read as given and never re-ranked
    assert rates["tie_rule"] == "TIE_GROUP_TAKES_BEST_PLACE"
    assert report["definitions"]["tie_rule"] == "TIE_GROUP_TAKES_BEST_PLACE"
    assert any("tie group its best place" in text for text in report["does_not_establish"])


# --------------------------------------------------------------------------------------- the rollups


def test_the_nfl_rollup_matches_a_hand_computed_fixture():
    report = _report(*STANDARD)
    nfl = report["scopes"]["nfl"]
    overall = nfl["overall"]
    # Best Ball, the free entry and MLB are left out: 3 entries in 2 contests on 2 slates.
    assert (overall["entries"], overall["contests"], overall["slates"], overall["blanks"]) == (3, 2, 2, 0)
    assert (nfl["slates"], nfl["fine_slates"]) == (2, 2)
    assert overall["fees_cents"] == 1100
    assert (overall["winnings_cash_cents"], overall["winnings_ticket_cents"]) == (1500, 300)
    assert overall["net_cents"] == 700
    assert overall["realized_return_on_fees"] == "63.6364"  # 700 / 1100
    assert overall["rake_implied_return"] == "-10.0000"  # (450 + 450 + 90) / 1100 - 1
    rates = overall["with_blanks"]
    assert rates["percentile"] == {"realized": "25.0667", "random": "51.7000"}  # (.012+.64+.1)/3; (.5005*2+.55)/3
    assert rates["top_10"] == {"realized": "66.6667", "random": "10.0000"}
    assert rates["bottom_10"] == {"realized": "0.0000", "random": "10.0000"}
    assert [row["game_type"] for row in nfl["by_format"]] == ["Classic", "Showdown Captain Mode"]
    assert _by(nfl["by_format"], "game_type", "Classic")["entries"] == 2
    assert [row["month"] for row in nfl["by_month"]] == ["2026-09"]
    assert [(row["date"], row["game_type"], row["entries"], row["fine_slates"]) for row in nfl["by_slate"]] == [
        ("2026-09-13", "Classic", 2, 1), ("2026-09-14", "Showdown Captain Mode", 1, 1)]
    # Payout shape from the numeric columns: 200 of 1000 is 1/5, 2 of 10 is 1/5.
    assert [(row["band"], row["first_place_label"], row["entries"]) for row in nfl["by_payout_shape"]] == [
        ("[1/5, 1/2)", None, 3)]
    assert [(row["band"], row["entries"]) for row in nfl["by_field_size"]] == [("1-20", 1), ("501-2000", 2)]
    assert [(row["band"], row["entries"]) for row in nfl["by_entry_fee"]] == [("$0.01-$1.00", 1),
                                                                               ("$1.01-$5.00", 2)]
    concentration = nfl["fee_concentration"]
    assert concentration["contests"] == 2
    assert [(row["contest_key"], row["fees_cents"], row["share"]) for row in concentration["top_contests"]] == [
        ("100000001", 1000, "90.9091"), ("100000002", 100, "9.0909")]
    assert report["schema_version"] == "nfl_results_report_v1"
    assert report["source"] == {"sha256": ZERO_SHA, "bytes": len(_history(*STANDARD)),
                                "contract": entry_history.CONTRACT_VERSION}


def test_a_top_heavy_contest_takes_the_first_place_label():
    top_heavy = _row(Places_Paid="49")  # 49 * 20 < 1000
    exactly_five_percent = _row(Entry_Key="4000000002", Contest_Key="100000002", Places_Paid="50")
    shapes = _report(top_heavy, exactly_five_percent)["scopes"]["nfl"]["by_payout_shape"]
    assert [(row["band"], row["first_place_label"]) for row in shapes] == [
        ("[0, 1/20)", "FIRST_PLACE_OBJECTIVE"), ("[1/20, 1/5)", None)]


def test_the_paid_fraction_caps_at_one_and_names_the_row():
    assert rr.paid_fraction(1200, 1000) == 1
    assert rr.paid_fraction(200, 1000) == Fraction(1, 5)
    report = _report(_row(Places_Paid="1200"))
    assert [row["band"] for row in report["scopes"]["nfl"]["by_payout_shape"]] == ["[1/2, 1]"]
    assert report["notes"] == [{"kind": "PLACES_PAID_ABOVE_CONTEST_ENTRIES_CAPPED", "row": 2,
                                "entry_key": "4000000001", "contest_key": "100000001"}]


def test_the_engine_era_parameter_splits_by_date():
    early = _row(Entry_Key="4000000007", Contest_Key="100000007", Contest_Date_EST="2026-09-08 20:20:00")
    default = _report(*STANDARD, early)
    assert default["engine_era_start"] == {"date": "2026-09-09", "is_default": True}
    assert default["scopes"]["nfl"]["overall"]["entries"] == 4
    assert default["scopes"]["engine_era"]["overall"]["entries"] == 3
    moved = _report(*STANDARD, early, era="2026-09-14")
    assert moved["engine_era_start"] == {"date": "2026-09-14", "is_default": False}
    assert [row["date"] for row in moved["scopes"]["engine_era"]["by_slate"]] == ["2026-09-14"]


def test_the_engine_era_keeps_only_the_game_types_the_engine_builds():
    tiers = _row(Game_Type="Tiers", Entry_Key="4000000008", Contest_Key="100000008")
    report = _report(*STANDARD, tiers)
    assert report["scopes"]["nfl"]["overall"]["entries"] == 4
    assert report["scopes"]["engine_era"]["overall"]["entries"] == 3


def test_a_late_evening_start_keeps_its_eastern_date():
    late = _row(Contest_Date_EST="2026-09-14 23:59:59")
    assert [row["date"] for row in _report(late)["scopes"]["nfl"]["by_slate"]] == ["2026-09-14"]


def test_fine_slates_split_same_day_contests_by_start_time():
    first = _row(Game_Type="Showdown Captain Mode", Contest_Date_EST="2026-09-14 13:00:00")
    second = _row(Game_Type="Showdown Captain Mode", Entry_Key="4000000002", Contest_Key="100000002",
                  Contest_Date_EST="2026-09-14 16:25:00")
    nfl = _report(first, second)["scopes"]["nfl"]
    assert (nfl["slates"], nfl["fine_slates"]) == (1, 2)
    assert nfl["by_slate"][0]["fine_slates"] == 2


def test_the_all_sport_check_leaves_out_unreadable_rows_and_counts_them():
    unreadable = _row(Sport="NBA", Entry_Key="4000000009", Contest_Key="100000009", Place="first")
    zero_field = _row(Sport="NBA", Entry_Key="4000000010", Contest_Key="100000010", Contest_Entries="0",
                      Place="1")
    history = entry_history.parse_entry_history(_history(*STANDARD, unreadable, zero_field))
    assert [note["kind"] for note in history.notes].count("NON_NFL_RULE_NOT_MET") >= 2
    check = _report(*STANDARD, unreadable, zero_field)["all_sport_check"]
    assert check["entries"] == 4  # 3 NFL and 1 MLB; Best Ball and the free row are out
    assert check["left_out_unreadable"] == {"NBA": 2}
    assert check["overall"]["fees_cents"] == 1200


def test_the_contest_name_is_never_read():
    renamed = [list(row) for row in STANDARD]
    for row in renamed:
        row[3] = "Renamed: Millionaire Single Entry Satellite 50/50"
    # The file's length is the only thing a longer name moves, so both sides name the same source.
    assert _bytes(*renamed, source_bytes=1) == _bytes(*STANDARD, source_bytes=1)
    assert b"Synthetic" not in _bytes(*STANDARD)


def test_an_empty_scope_reports_nulls_not_zeros():
    report = _report(*STANDARD, era="2027-01-01")
    era = report["scopes"]["engine_era"]
    assert era["overall"]["entries"] == 0
    assert era["overall"]["with_blanks"]["percentile"] == {"realized": None, "random": None}
    assert era["overall"]["realized_return_on_fees"] is None
    assert era["by_slate"] == [] and era["fee_concentration"]["top_contests"] == []


# --------------------------------------------------------------------------------------- the metrics file


def test_the_metrics_file_is_the_pinned_bytes():
    raw = rr.DEFAULT_METRICS_PATH.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == METRICS_SHA256, (
        "config/results_metrics_v1.json changed; v1 is never mutated: register v2 instead")
    metrics = rr.load_results_metrics()
    assert metrics.sha256 == METRICS_SHA256
    assert metrics.version == "nfl_results_metrics_v1"
    assert metrics.excluded_game_types == ("Best Ball",)
    assert metrics.engine_game_types == ("Classic", "Showdown Captain Mode")
    assert metrics.engine_era_start == "2026-09-09"
    assert metrics.paid_fraction_edges == (Fraction(1, 20), Fraction(1, 5), Fraction(1, 2))
    assert metrics.paid_fraction_edges[0] == contest_facts.THRESHOLD
    assert metrics.field_size_upper == (20, 100, 500, 2000)
    assert metrics.entry_fee_upper_cents == (100, 500, 2000)
    assert metrics.fee_concentration_top == 10
    assert (metrics.trigger_scope, metrics.trigger_alpha, metrics.trigger_min_slates) == (
        "engine_era", Fraction(1, 20), 20)
    assert metrics.registered_on == "2026-10-10"
    assert metrics.does_not_establish[0] == ("Realized results of past entries; not EV, an ROI forecast, a win "
                                             "probability, a calibration or a proven edge.")
    assert rr.DEFAULT_METRICS_PATH == REPO / "config" / "results_metrics_v1.json"


def _metrics_with(**changes: object) -> bytes:
    document = json.loads(rr.DEFAULT_METRICS_PATH.read_bytes())
    for dotted, value in changes.items():
        *parents, leaf = dotted.split("__")
        target = document
        for parent in parents:
            target = target[parent]
        if value is _DELETE:
            del target[leaf]
        else:
            target[leaf] = value
    return json.dumps(document).encode("utf-8")


_DELETE = object()


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"\xff\xfe",
        b"{not json",
        b"[" * 100_000 + b"]" * 100_000,
        b"[]",
        _metrics_with(schema_version="nfl_results_metrics_v2"),
        _metrics_with(surprise=1),
        _metrics_with(populations__surprise=1),
        _metrics_with(populations__excluded_game_types=_DELETE),
        _metrics_with(populations__excluded_game_types=[""]),
        _metrics_with(populations__excluded_game_types=["Best Ball", "Best Ball"]),
        _metrics_with(fee_concentration_top=True),
        _metrics_with(bootstrap__mde_power="1/1"),
        _metrics_with(populations__engine_game_types="Classic"),
        _metrics_with(populations__engine_era_start="2026-02-30"),
        _metrics_with(populations__paid="ENTRY_FEE_AT_LEAST_ZERO"),
        _metrics_with(rates__bottom_10="PLACE_TIMES_10_AT_LEAST_9N"),
        _metrics_with(slates__slate="SPORT_EASTERN_DATE"),
        _metrics_with(bands__paid_fraction_edges=["1/10", "1/5", "1/2"]),
        _metrics_with(bands__paid_fraction_edges=["1/20", "1/2", "1/5"]),
        _metrics_with(bands__paid_fraction_edges=["1/20", "1/5", "x"]),
        _metrics_with(bands__field_size_upper=[20, 20, 500]),
        _metrics_with(bands__entry_fee_upper_cents=[100, True]),
        _metrics_with(bands__entry_fee_upper_cents=[10 ** 400]),
        _metrics_with(fee_concentration_top=0),
        _metrics_with(within_slate_test__trigger_scope="all_sport"),
        _metrics_with(within_slate_test__trigger_alpha="0"),
        _metrics_with(within_slate_test__trigger_min_slates=-1),
        _metrics_with(bootstrap__resamples=10 ** 9),
        _metrics_with(bootstrap__level="1"),
        _metrics_with(does_not_establish=[]),
    ],
)
def test_a_malformed_metrics_file_is_refused_by_name(raw):
    with pytest.raises(rr.ResultsMetricsError, match="^results metrics "):
        rr.parse_results_metrics(raw)


# --------------------------------------------------------------------------------- the within-slate test


def _contest(number: int, day: str, place: int, paid: str, game_type: str = "Classic") -> list[str]:
    return _row(Game_Type=game_type, Entry_Key=str(4100000000 + number), Contest_Key=str(110000000 + number),
                Contest_Date_EST=f"{day} 13:00:00", Place=str(place), Places_Paid=paid, Points="100")


TOP_HEAVY, FLATTER = "10", "200"  # 10 of 1000 is under 1/20; 200 of 1000 is not


def test_the_sign_test_is_exact_and_one_sided():
    assert rr.sign_test(11, 1) == (Fraction(13, 4096), Fraction(26, 4096))
    assert rr.sign_test(10, 3)[0] == Fraction(378, 8192)
    assert rr.sign_test(1, 1) == (Fraction(3, 4), Fraction(1))
    assert rr.sign_test(0, 0) == (Fraction(1), Fraction(1))
    assert rr.sign_test(0, 3) == (Fraction(1), Fraction(1, 4))


def test_the_paired_test_counts_slates_by_hand():
    rows = (
        _contest(1, "2026-09-13", 800, TOP_HEAVY), _contest(2, "2026-09-13", 200, FLATTER),  # +0.6: worse
        _contest(3, "2026-09-14", 100, TOP_HEAVY, "Showdown Captain Mode"),
        _contest(4, "2026-09-14", 500, FLATTER, "Showdown Captain Mode"),  # -0.4: better
        _contest(5, "2026-09-21", 300, TOP_HEAVY), _contest(6, "2026-09-21", 300, FLATTER),  # tied: dropped
        _contest(7, "2026-09-28", 900, TOP_HEAVY),  # one kind only: not in the test
        _contest(8, "2026-10-10", 500, TOP_HEAVY), _contest(9, "2026-10-10", 500, FLATTER),  # registration day: tied
    )
    report = _report(*rows)
    test = report["scopes"]["nfl"]["within_slate_test"]
    assert (test["slates_with_both"], test["worse"], test["better"], test["tied"]) == (4, 1, 1, 2)
    assert (test["p_one_sided"], test["p_two_sided"]) == ("0.750000", "1.000000")
    assert test["mean_difference_points"] == "5.0000"  # (60 - 40 + 0 + 0) / 4
    assert [(row["date"], row["difference_points"]) for row in test["slates"]] == [
        ("2026-09-13", "60.0000"), ("2026-09-14", "-40.0000"), ("2026-09-21", "0.0000"), ("2026-10-10", "0.0000")]
    assert test["slates"][0]["top_heavy_entries"] == 1 and test["slates"][0]["flatter_entries"] == 1
    assert test["slates_after_registration"] == 0
    trigger = report["within_slate_trigger"]
    assert trigger["scope"] == "engine_era" and trigger["met"] is False
    assert (trigger["slates"], trigger["p_one_sided"]) == (2, "0.750000")


def _worse_slates(count: int, better: int = 0) -> list[list[str]]:
    rows = []
    for index in range(count):
        day = f"2026-10-{11 + index:02d}"
        top, flat = (100, 900) if index < better else (900, 100)
        rows += [_contest(2 * index, day, top, TOP_HEAVY), _contest(2 * index + 1, day, flat, FLATTER)]
    return rows


@pytest.mark.parametrize(("count", "better", "met"), [(19, 0, False), (20, 0, True), (20, 6, False),
                                                       (20, 5, True)])
def test_the_trigger_needs_twenty_slates_and_p_under_one_twentieth(count, better, met):
    report = _report(*_worse_slates(count, better))
    trigger = report["within_slate_trigger"]
    assert (trigger["slates"], trigger["met"]) == (count, met)
    assert trigger["registered_on"] == "2026-10-10"
    assert report["scopes"]["engine_era"]["within_slate_test"]["slates_after_registration"] == count


def test_a_capped_contest_is_flatter_not_top_heavy():
    rows = (_contest(1, "2026-09-13", 800, "1200"), _contest(2, "2026-09-13", 200, TOP_HEAVY))
    test = _report(*rows)["scopes"]["nfl"]["within_slate_test"]
    assert (test["worse"], test["better"]) == (0, 1)  # the capped contest is the flatter side


def test_an_era_start_that_is_not_a_calendar_date_is_refused():
    history = entry_history.parse_entry_history(_history(*STANDARD))
    for bad in ("2026-9-9", "2026-02-30", "20260909", ""):
        assert not rr.is_calendar_date(bad)
        with pytest.raises(ValueError, match="engine_era_start"):
            rr.build_report(history, metrics=rr.load_results_metrics(), source_sha256=ZERO_SHA, source_bytes=1,
                            engine_era_start=bad)
    assert rr.is_calendar_date("2026-09-09")


def test_every_figure_is_exact_and_rounds_half_to_even():
    # 123465 / 10,000,000 is exactly 1.23465 points: half to even keeps 1.2346, where half-up would give 1.2347.
    rates = _report(_row(Place="123465", Contest_Entries="10000000"))["scopes"]["nfl"]["overall"]["with_blanks"]
    assert rates["percentile"]["realized"] == "1.2346"
    rates = _report(_row(Place="123475", Contest_Entries="10000000"))["scopes"]["nfl"]["overall"]["with_blanks"]
    assert rates["percentile"]["realized"] == "1.2348"


def test_the_contracts_doc_names_the_metrics_hash():
    assert METRICS_SHA256 in (REPO / "docs" / "DATA_CONTRACTS.md").read_text(encoding="utf-8")


def test_fee_concentration_lists_the_registered_top_ten():
    rows = [_row(Entry_Key=str(4200000000 + number), Contest_Key=str(120000000 + number),
                 Entry_Fee=f"${number}.00", Prize_Pool="$900.00") for number in range(1, 13)]
    concentration = _report(*rows)["scopes"]["nfl"]["fee_concentration"]
    assert concentration["contests"] == 12 and concentration["fees_cents"] == 7800
    assert [row["contest_key"] for row in concentration["top_contests"]] == [
        str(120000000 + number) for number in range(12, 2, -1)]


def test_the_trigger_needs_p_strictly_below_alpha():
    # A sign-test p is k / 2^n and never equals the registered 1/20; a dyadic alpha pins the strict rule.
    metrics = dataclasses.replace(rr.load_results_metrics(), trigger_alpha=Fraction(1, 4), trigger_min_slates=2)
    trigger = _report(*_worse_slates(2), metrics=metrics)["within_slate_trigger"]
    assert (trigger["p_one_sided"], trigger["met"]) == ("0.250000", False)
