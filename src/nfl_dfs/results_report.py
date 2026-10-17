"""The NFL results report (Session 71, `nfl_results_metrics_v1`, `nfl_results_report_v1`).

Realized results of past entries, read from the hash-named entry-history snapshot (`nfl_dk_entry_history_v1`). This
module owns the entry-level definitions every later grader imports (Session 18's `standings_metrics.py` among them):
the finishing percentile `Place / Contest_Entries` and its random expectation `(n+1)/2n`, the top-10% and bottom-10%
finishes and theirs, and blanks (`Points` exactly zero). DraftKings gives a tie group its best place, so the percentile
flatters where ties are common; the random expectation assumes no ties, and `Place` is read as given.

The registered metrics file (`config/results_metrics_v1.json`) names the populations, the rules, the bands, the slate
and the within-slate test; the loader refuses any file whose declared rules are not the ones this module implements.
Every point figure is exact rational arithmetic rounded once, so the same rows give the same text. Session 71b reads the
file's bootstrap section for each slice's interval and minimum detectable effect (resampled in IEEE doubles, in a fixed
order, rounded once) and writes the report once through `nfl results-report`.
Payout shape and field size come from the numeric columns only, never from a contest name, and nothing here reaches a
run, a frozen package, a selection or a release truth.

Session 77 registers `nfl_results_metrics_v2` (`config/results_metrics_v2.json`) and its report, `nfl_results_report_v2`:
every v1 block unchanged, plus R38's two realized readings. Goal 1, per contest: our best entry's place and percentile
beside the best of that many random places, and first-place and top-1% finishes beside each entry's random share. Goal
2, per portfolio (the paid entries sharing a contest start time and game type): whether every entry won nothing, beside a
random draw's washout. A v1 metrics file still gives the v1 payload, file and table, byte for byte.
"""

from __future__ import annotations

import json
import math
import os
import random
import re
import stat
from collections import Counter
from dataclasses import dataclass
from datetime import date
from fractions import Fraction
from functools import partial
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence

from . import entry_history
from .contest_facts import LABEL, THRESHOLD, canonical_bytes, first_place_label
from .entry_history import CONTRACT_VERSION as HISTORY_CONTRACT
from .entry_history import EntryHistory, EntryHistoryRefused, HistoryRow, _problem
from .hashing import sha256_bytes

METRICS_VERSION = "nfl_results_metrics_v1"
REPORT_VERSION = "nfl_results_report_v1"
WRITER = "w1"
DEFAULT_METRICS_PATH = Path(__file__).resolve().parents[2] / "config" / "results_metrics_v1.json"
METRICS_V2 = "nfl_results_metrics_v2"
REPORT_V2 = "nfl_results_report_v2"
METRICS_V2_PATH = DEFAULT_METRICS_PATH.parent / "results_metrics_v2.json"
METRICS_VERSIONS = (METRICS_VERSION, METRICS_V2)
# What `nfl results-report` reads unless told otherwise; `DEFAULT_METRICS_PATH` stays v1's file, as its tests pin.
CURRENT_METRICS_VERSION = METRICS_V2

TOP_FRACTION = Fraction(1, 10)
BOTTOM_FRACTION = Fraction(9, 10)
# A bottom-10% finish is a place above 9n/10 (strict). The review's "20% at five entries" fits either boundary; the
# real export's all-sport bottom rate (13.6%) decides it, and flipping this constant is a new metrics version.
BOTTOM_STRICT = True
TIE_RULE = "TIE_GROUP_TAKES_BEST_PLACE"
SCOPES = ("nfl", "engine_era")
# The rules the metrics file declares and this module implements; any other text is refused.
DECLARED = {
    "populations": {"paid": "ENTRY_FEE_ABOVE_ZERO", "winnings": "NON_TICKET_PLUS_TICKET_AT_FACE_VALUE"},
    "rates": {
        "percentile": "PLACE_OVER_CONTEST_ENTRIES",
        "random_percentile": "N_PLUS_1_OVER_2N",
        "top_10": "PLACE_TIMES_10_AT_MOST_N",
        "bottom_10": "PLACE_TIMES_10_ABOVE_9N",
        "blank": "POINTS_EXACTLY_ZERO",
        "tie_rule": TIE_RULE,
    },
    "slates": {"slate": "SPORT_EASTERN_DATE_GAME_TYPE", "fine_slate": "SPORT_CONTEST_START_GAME_TYPE"},
    "within_slate_test": {
        "split": "FIRST_PLACE_OBJECTIVE_AGAINST_UNLABELLED",
        "statistic": "MEAN_PERCENTILE_DIFFERENCE_WITH_BLANKS",
        "test": "EXACT_SIGN_TEST_ONE_SIDED_TOP_HEAVY_WORSE_TIES_DROPPED",
    },
    "bootstrap": {"cluster": "SLATE", "wild": "WEBB_SIX_POINT_STUDENTIZED_CR1"},
}
# The two sections only a v2 file carries (Session 77, R38), checked the same way.
DECLARED_V2 = {
    "first_place": {
        "first_place": "PLACE_EQUALS_ONE",
        "random_first_place": "ONE_OVER_N",
        "top_1": "PLACE_TIMES_100_AT_MOST_N",
        "random_top_1": "FLOOR_N_OVER_100_OVER_N",
        "best_entry": "MIN_PLACE_PER_CONTEST_KEY",
        "random_best_percentile": "N_PLUS_1_OVER_K_PLUS_1_TIMES_N",
        "points_behind_first": "NOT_IN_EXPORT_SESSION_18_THRESHOLDS",
    },
    "washout": {
        "washout": "EVERY_PAID_ENTRY_NON_TICKET_AND_TICKET_ZERO",
        "portfolio": "SPORT_CONTEST_START_GAME_TYPE",
        "random_washout": "HYPERGEOMETRIC_NO_ENTRY_IN_PLACES_PAID",
    },
}
_RULES = {**DECLARED, **DECLARED_V2}
_V1_KEYS = frozenset({"schema_version", "registered_at", "authority", "populations", "rates", "slates", "bands",
                      "fee_concentration_top", "within_slate_test", "bootstrap", "does_not_establish"})

_FRACTION = re.compile(r"[1-9][0-9]{0,5}/[1-9][0-9]{0,5}")
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


class ResultsMetricsError(ValueError):
    """The metrics file cannot be trusted; nothing falls back to a guess."""


@dataclass(frozen=True)
class ResultsMetrics:
    excluded_game_types: tuple[str, ...]
    engine_game_types: tuple[str, ...]
    engine_era_start: str
    paid_fraction_edges: tuple[Fraction, ...]
    field_size_upper: tuple[int, ...]
    entry_fee_upper_cents: tuple[int, ...]
    fee_concentration_top: int
    registered_on: str
    trigger_scope: str
    trigger_alpha: Fraction
    trigger_min_slates: int
    bootstrap: Mapping[str, object]
    does_not_establish: tuple[str, ...]
    sha256: str
    version: str = METRICS_VERSION


# ------------------------------------------------------------------------------------- the metrics file


def _invalid(where: str, why: str) -> ResultsMetricsError:
    return ResultsMetricsError(f"results metrics invalid: {where} {why}")


def _object(value: object, keys: frozenset[str], where: str) -> dict:
    if not isinstance(value, dict) or set(value) != keys:
        raise _invalid(where, f"must be an object with exactly the keys {sorted(keys)}")
    return value


def _integer(value: object, where: str, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise _invalid(where, f"must be an integer from {low} to {high}")
    return value


def _fraction(value: object, where: str) -> Fraction:
    if not isinstance(value, str) or not _FRACTION.fullmatch(value) or not 0 < Fraction(value) < 1:
        raise _invalid(where, "must be a fraction a/b strictly between 0 and 1")
    return Fraction(value)


def is_calendar_date(value: object) -> bool:
    """A YYYY-MM-DD string naming a real day; dates compare as text only in this exact form."""

    try:
        return isinstance(value, str) and bool(_DATE.fullmatch(value)) and bool(date.fromisoformat(value))
    except ValueError:
        return False


def _date(value: object, where: str) -> str:
    if not is_calendar_date(value):
        raise _invalid(where, "must be a calendar date YYYY-MM-DD")
    return value


def _texts(value: object, where: str) -> tuple[str, ...]:
    if (not isinstance(value, list) or not value
            or not all(isinstance(text, str) and text and text == text.strip() for text in value)
            or len(set(value)) != len(value)):
        raise _invalid(where, "must be a non-empty list of distinct, trimmed, non-empty strings")
    return tuple(value)


def _increasing(values: tuple, where: str) -> tuple:
    if any(later <= earlier for earlier, later in zip(values, values[1:])):
        raise _invalid(where, "must increase strictly")
    return values


def _uppers(value: object, where: str, high: int) -> tuple[int, ...]:
    if not isinstance(value, list) or not value:
        raise _invalid(where, "must be a non-empty list")
    return _increasing(tuple(_integer(upper, where, 1, high) for upper in value), where)


def _declared(document: Mapping[str, object], section: str, extra: frozenset[str]) -> dict:
    block = _object(document[section], frozenset(_RULES.get(section, {})) | extra, section)
    for key, text in _RULES.get(section, {}).items():
        if block[key] != text:
            raise _invalid(f"{section}.{key}", f"must be {text!r}, the rule this module implements")
    return block


def _unique_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    if len({key for key, _ in pairs}) != len(pairs):
        raise _invalid("an object", "repeats a key")
    return dict(pairs)


def parse_results_metrics(raw: bytes) -> ResultsMetrics:
    """The registered metrics, or `ResultsMetricsError` naming the first fault."""

    try:
        document = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_keys)
    except ResultsMetricsError:
        raise
    except (ValueError, RecursionError) as exc:  # UnicodeDecodeError and JSONDecodeError are ValueErrors
        raise ResultsMetricsError(f"results metrics unreadable: {type(exc).__name__}") from None
    # The version picks the key set first: a v2 file adds exactly the `DECLARED_V2` sections, and a v1 or v2 name on
    # the other's sections is refused here.
    version = document.get("schema_version") if isinstance(document, dict) else None
    _object(document, _V1_KEYS | (frozenset(DECLARED_V2) if version == METRICS_V2 else frozenset()), "file")
    if version not in METRICS_VERSIONS:
        raise _invalid("schema_version", f"must be one of {list(METRICS_VERSIONS)}")
    _date(document["registered_at"], "registered_at")
    _texts(document["authority"], "authority")
    populations = _declared(document, "populations",
                            frozenset({"excluded_game_types", "engine_game_types", "engine_era_start"}))
    _declared(document, "rates", frozenset())
    _declared(document, "slates", frozenset())
    bands = _object(document["bands"], frozenset({"paid_fraction_edges", "field_size_upper",
                                                  "entry_fee_upper_cents"}), "bands")
    edges = _increasing(tuple(_fraction(cut, "bands.paid_fraction_edges")
                              for cut in _texts(bands["paid_fraction_edges"], "bands.paid_fraction_edges")),
                        "bands.paid_fraction_edges")
    if edges[0] != THRESHOLD:
        raise _invalid("bands.paid_fraction_edges", "must start at contest_facts.THRESHOLD, the first-place label")
    sizes = _uppers(bands["field_size_upper"], "bands.field_size_upper", 10 ** 7)
    fees = _uppers(bands["entry_fee_upper_cents"], "bands.entry_fee_upper_cents", 10 ** 9)
    test = _declared(document, "within_slate_test",
                     frozenset({"registered_on", "trigger_scope", "trigger_alpha", "trigger_min_slates"}))
    if test["trigger_scope"] not in SCOPES:
        raise _invalid("within_slate_test.trigger_scope", f"must be one of {list(SCOPES)}")
    bootstrap = _declared(document, "bootstrap", frozenset({"seed", "resamples", "level", "pairs_min_slates",
                                                            "interval_min_slates", "mde_alpha_two_sided",
                                                            "mde_power"}))
    _integer(bootstrap["seed"], "bootstrap.seed", 0, 2 ** 63 - 1)
    _integer(bootstrap["resamples"], "bootstrap.resamples", 1, 100_000)
    _integer(bootstrap["pairs_min_slates"], "bootstrap.pairs_min_slates", 2, 10_000)
    _integer(bootstrap["interval_min_slates"], "bootstrap.interval_min_slates", 2, 10_000)
    for name in ("level", "mde_alpha_two_sided", "mde_power"):
        _fraction(bootstrap[name], f"bootstrap.{name}")
    if version == METRICS_V2:
        for section in DECLARED_V2:
            _declared(document, section, frozenset())
    return ResultsMetrics(
        excluded_game_types=_texts(populations["excluded_game_types"], "populations.excluded_game_types"),
        engine_game_types=_texts(populations["engine_game_types"], "populations.engine_game_types"),
        engine_era_start=_date(populations["engine_era_start"], "populations.engine_era_start"),
        paid_fraction_edges=edges,
        field_size_upper=sizes,
        entry_fee_upper_cents=fees,
        fee_concentration_top=_integer(document["fee_concentration_top"], "fee_concentration_top", 1, 1_000),
        registered_on=_date(test["registered_on"], "within_slate_test.registered_on"),
        trigger_scope=test["trigger_scope"],
        trigger_alpha=_fraction(test["trigger_alpha"], "within_slate_test.trigger_alpha"),
        trigger_min_slates=_integer(test["trigger_min_slates"], "within_slate_test.trigger_min_slates", 1, 10_000),
        bootstrap=dict(bootstrap),
        does_not_establish=_texts(document["does_not_establish"], "does_not_establish"),
        sha256=sha256_bytes(raw),
        version=version,
    )


def load_results_metrics(path: str | Path = DEFAULT_METRICS_PATH) -> ResultsMetrics:
    try:
        raw = Path(path).read_bytes()
    except OSError as exc:
        raise ResultsMetricsError(f"results metrics unreadable: {type(exc).__name__}") from None
    return parse_results_metrics(raw)


def registered_metrics_path(version: str) -> Path:
    """Each registered version's file, looked up at call time so a test that moves one moves what the command reads."""

    if version == METRICS_VERSION:
        return DEFAULT_METRICS_PATH
    if version == METRICS_V2:
        return METRICS_V2_PATH
    raise ValueError(f"unknown results metrics version {version!r}")


def report_contract(metrics: ResultsMetrics) -> str:
    return REPORT_V2 if metrics.version == METRICS_V2 else REPORT_VERSION


# ------------------------------------------------------------------------------ per-entry definitions


def finishing_percentile(place: int, entries: int) -> Fraction:
    """`Place / Contest_Entries`: lower is better, and DraftKings' best-place tie rule makes it flatter."""

    return Fraction(place, entries)


def random_percentile(entries: int) -> Fraction:
    """The mean of `place / n` over a uniformly random place in 1..n: `(n+1)/2n`, above 1/2 in small fields."""

    return Fraction(entries + 1, 2 * entries)


def in_top(place: int, entries: int) -> bool:
    return place * TOP_FRACTION.denominator <= TOP_FRACTION.numerator * entries


def random_top(entries: int) -> Fraction:
    """`floor(n/10)/n`: a top-10% finish is impossible below 10 entries."""

    return Fraction(entries * TOP_FRACTION.numerator // TOP_FRACTION.denominator, entries)


def in_bottom(place: int, entries: int) -> bool:
    scaled, cut = place * BOTTOM_FRACTION.denominator, BOTTOM_FRACTION.numerator * entries
    return scaled > cut if BOTTOM_STRICT else scaled >= cut


def random_bottom(entries: int) -> Fraction:
    """The share of places 1..n that are bottom-10% finishes: 1/5 at five entries."""

    cut = Fraction(BOTTOM_FRACTION.numerator * entries, BOTTOM_FRACTION.denominator)
    first = math.floor(cut) + 1 if BOTTOM_STRICT else math.ceil(cut)
    return Fraction(entries - first + 1, entries)


def is_blank(points_hundredths: int) -> bool:
    """A blank is `Points` exactly zero: a lineup that scored nothing, never a low score or a negative one."""

    return points_hundredths == 0


def paid_fraction(places_paid: int, entries: int) -> Fraction:
    """`Places_Paid / Contest_Entries`, capped at 1 (a contest that ran under its guarantee can pay more places)."""

    return min(Fraction(1), Fraction(places_paid, entries))


# ------------------------------------------------------------- first place and washouts (Session 77, R38)

TOP_1_FRACTION = Fraction(1, 100)


def in_first(place: int) -> bool:
    """First place as DraftKings gives it: every entry in a tie for first is first, read as given."""

    return place == 1


def random_first(entries: int) -> Fraction:
    return Fraction(1, entries)


def in_top_1(place: int, entries: int) -> bool:
    return place * TOP_1_FRACTION.denominator <= TOP_1_FRACTION.numerator * entries


def random_top_1(entries: int) -> Fraction:
    """`floor(n/100)/n`, v1's top-10% rule at 1%: a top-1% finish is impossible below 100 entries."""

    return Fraction(entries * TOP_1_FRACTION.numerator // TOP_1_FRACTION.denominator, entries)


def random_best_percentile(entries: int, ours: int) -> Fraction:
    """The mean of the best of `ours` distinct uniform places in 1..n, over n: `(n+1)/((k+1)n)`; v1's at k = 1. k is
    capped at n: a real export never holds more of our entries than the field, and a file that does still reports."""

    return Fraction(entries + 1, (min(ours, entries) + 1) * entries)


def random_no_paid_place(entries: int, places_paid: int, ours: int) -> Fraction:
    """`C(n-p, k)/C(n, k)`: none of `ours` distinct uniform places is paid, `Places_Paid` capped at n as v1 caps it,
    and k at n as `random_best_percentile` caps it."""

    paid, ours = min(places_paid, entries), min(ours, entries)
    return Fraction(math.comb(entries - paid, ours), math.comb(entries, ours))


def random_washout(contests: Iterable[tuple[int, int, int]]) -> Fraction:
    """A portfolio's random washout: each contest, `(entries, places paid, ours)`, drawn independently."""

    return math.prod((random_no_paid_place(*contest) for contest in contests), start=Fraction(1))


# ------------------------------------------------------------------------------------- aggregation


def _fixed(value: Fraction, places: int = 4) -> str:
    """Exact rational arithmetic rounded once, half to even (Python's `round` on a Fraction), never through a float."""

    units = round(value * 10 ** places)
    whole, part = divmod(abs(units), 10 ** places)
    return f"{'-' if units < 0 else ''}{whole}.{part:0{places}d}"


def _mean_percent(values: Sequence[Fraction]) -> str | None:
    return _fixed(sum(values, Fraction(0)) * 100 / len(values)) if values else None


def _ratio_percent(numerator: Fraction | int, denominator: int) -> str | None:
    return _fixed(Fraction(numerator) * 100 / denominator) if denominator else None


def _pair(rows: Sequence[HistoryRow], realized: Callable[[int, int], object],
          random: Callable[[int], Fraction]) -> dict[str, str | None]:
    return {
        "realized": _mean_percent([Fraction(realized(row.place, row.contest_entries)) for row in rows]),
        "random": _mean_percent([random(row.contest_entries) for row in rows]),
    }


def _rates(rows: Sequence[HistoryRow]) -> dict[str, object]:
    return {
        "entries": len(rows),
        "tie_rule": TIE_RULE,
        "percentile": _pair(rows, finishing_percentile, random_percentile),
        "top_10": _pair(rows, in_top, random_top),
        "bottom_10": _pair(rows, in_bottom, random_bottom),
    }


def slate_key(row: HistoryRow) -> tuple[str, str, str]:
    """The review's cluster: sport, Eastern date (from the parsed time) and game type; same-day Showdowns merge."""

    return row.sport, str(row.contest_start)[:10], row.game_type


def fine_slate_key(row: HistoryRow) -> tuple[str, str, str]:
    return row.sport, str(row.contest_start), row.game_type


def _slice(rows: Sequence[HistoryRow]) -> dict[str, object]:
    fees = sum(row.entry_fee_cents for row in rows)
    cash = sum(row.winnings_non_ticket_cents for row in rows)
    ticket = sum(row.winnings_ticket_cents for row in rows)
    pool_share = sum((Fraction(row.prize_pool_cents, row.contest_entries) for row in rows), Fraction(0))
    return {
        "entries": len(rows),
        "slates": len({slate_key(row) for row in rows}),
        "contests": len({row.contest_key for row in rows}),
        "blanks": sum(is_blank(row.points_hundredths) for row in rows),
        "fees_cents": fees,
        "winnings_cash_cents": cash,
        "winnings_ticket_cents": ticket,
        "net_cents": cash + ticket - fees,
        "realized_return_on_fees": _ratio_percent(cash + ticket - fees, fees),
        "rake_implied_return": _ratio_percent(pool_share - fees, fees),
        "with_blanks": _rates(rows),
        "blanks_removed": _rates([row for row in rows if not is_blank(row.points_hundredths)]),
    }


def _rollup(rows: Sequence[HistoryRow], key: Callable[[HistoryRow], tuple],
            describe: Callable[[tuple, list[HistoryRow]], dict],
            measure: Callable[[dict, list[HistoryRow]], dict] | None = None) -> list[dict]:
    groups: dict[tuple, list[HistoryRow]] = {}
    for row in rows:
        groups.setdefault(key(row), []).append(row)
    out = []
    for found in sorted(groups):
        described = describe(found, groups[found])
        out.append({**described, **_slice(groups[found])})
        if measure is not None:
            out[-1]["uncertainty"] = measure(described, groups[found])
    return out


def _band(value: object, uppers: Sequence) -> int:
    return sum(value > upper for upper in uppers)


def _cents_text(cents: int) -> str:
    return f"${cents // 100}.{cents % 100:02d}"


def _labels(uppers: Sequence[int], text: Callable[[int], str]) -> list[str]:
    lowers = (1, *(upper + 1 for upper in uppers))
    return [f"{text(low)}-{text(high)}" for low, high in zip(lowers, uppers)] + [f"{text(lowers[-1])}+"]


def _shape_labels(edges: Sequence[Fraction]) -> list[str]:
    bounds = ("0", *map(str, edges), "1")
    return [f"[{low}, {high})" for low, high in zip(bounds, bounds[1:-1])] + [f"[{bounds[-2]}, 1]"]


def _shape_band(row: HistoryRow, edges: Sequence[Fraction]) -> int:
    return sum(paid_fraction(row.places_paid, row.contest_entries) >= cut for cut in edges)


def _fee_concentration(rows: Sequence[HistoryRow], top: int) -> dict[str, object]:
    contests: dict[str, list[HistoryRow]] = {}
    for row in rows:
        contests.setdefault(row.contest_key, []).append(row)
    fees = {key: sum(row.entry_fee_cents for row in group) for key, group in contests.items()}
    total = sum(fees.values())
    ranked = sorted(contests.items(), key=lambda item: (-fees[item[0]], item[0]))
    return {
        "contests": len(contests),
        "fees_cents": total,
        "top_contests": [
            {
                "contest_key": key,
                "game_type": group[0].game_type,
                "date": str(group[0].contest_start)[:10],
                "contest_entries": group[0].contest_entries,
                "entries": len(group),
                "fees_cents": fees[key],
                "share": _ratio_percent(fees[key], total),
            }
            for key, group in ranked[:top]
        ],
    }


def _scope(rows: Sequence[HistoryRow], metrics: ResultsMetrics,
           measure: Callable[[str, dict, Sequence[HistoryRow]], dict] | None = None) -> dict[str, object]:
    """One scope's rollups; with `measure` every slice but a one-slate `by_slate` row gains `uncertainty`."""

    shapes = _shape_labels(metrics.paid_fraction_edges)
    sizes = _labels(metrics.field_size_upper, str)
    fees = _labels(metrics.entry_fee_upper_cents, _cents_text)

    def measured(rollup: str) -> Callable[[dict, list[HistoryRow]], dict] | None:
        return None if measure is None else partial(measure, rollup)

    overall = _slice(rows)
    if measure is not None:
        overall["uncertainty"] = measure("overall", {}, rows)
    return {
        "slates": len({slate_key(row) for row in rows}),
        "fine_slates": len({fine_slate_key(row) for row in rows}),
        "overall": overall,
        "by_format": _rollup(rows, lambda row: (row.game_type,), lambda key, _: {"game_type": key[0]},
                             measured("by_format")),
        "by_payout_shape": _rollup(
            rows, lambda row: (_shape_band(row, metrics.paid_fraction_edges),),
            lambda key, _: {"band": shapes[key[0]], "first_place_label": LABEL if key[0] == 0 else None},
            measured("by_payout_shape")),
        "by_field_size": _rollup(rows, lambda row: (_band(row.contest_entries, metrics.field_size_upper),),
                                 lambda key, _: {"band": sizes[key[0]]}, measured("by_field_size")),
        "by_entry_fee": _rollup(rows, lambda row: (_band(row.entry_fee_cents, metrics.entry_fee_upper_cents),),
                                lambda key, _: {"band": fees[key[0]]}, measured("by_entry_fee")),
        "by_month": _rollup(rows, lambda row: (str(row.contest_start)[:7],), lambda key, _: {"month": key[0]},
                            measured("by_month")),
        "by_slate": _rollup(
            rows, lambda row: slate_key(row)[1:] + slate_key(row)[:1],
            lambda key, group: {"sport": key[2], "date": key[0], "game_type": key[1],
                                "fine_slates": len({fine_slate_key(row) for row in group})}),
        "fee_concentration": _fee_concentration(rows, metrics.fee_concentration_top),
        "within_slate_test": _within_slate(rows, metrics.registered_on),
    }


def sign_test(worse: int, better: int) -> tuple[Fraction, Fraction]:
    """The exact sign test with ties already dropped: `P(X >= worse)` one-sided and the two-sided p, X ~ Bin(n, 1/2)."""

    count = worse + better

    def at_least(k: int) -> Fraction:
        return Fraction(sum(math.comb(count, j) for j in range(k, count + 1)), 2 ** count)

    upper, lower = at_least(worse), 1 - at_least(worse + 1)
    return upper, min(Fraction(1), 2 * min(upper, lower))


def _within_slate(rows: Sequence[HistoryRow], registered_on: str) -> dict[str, object]:
    """Per slate holding both kinds: mean percentile of top-heavy entries (`first_place_label` set) minus flatter."""

    groups: dict[tuple[str, str, str], list[HistoryRow]] = {}
    for row in rows:
        groups.setdefault(slate_key(row), []).append(row)
    slates = []
    for key in sorted(groups, key=lambda found: (found[1], found[2], found[0])):
        sides: dict[bool, list[Fraction]] = {True: [], False: []}
        for row in groups[key]:
            top_heavy = first_place_label(row.places_paid, row.contest_entries) is not None
            sides[top_heavy].append(finishing_percentile(row.place, row.contest_entries))
        if sides[True] and sides[False]:
            difference = sum(sides[True]) / len(sides[True]) - sum(sides[False]) / len(sides[False])
            slates.append((key, len(sides[True]), len(sides[False]), difference))
    worse = sum(difference > 0 for *_, difference in slates)
    better = sum(difference < 0 for *_, difference in slates)
    one_sided, two_sided = sign_test(worse, better)
    return {
        "slates_with_both": len(slates),
        "worse": worse,
        "better": better,
        "tied": len(slates) - worse - better,
        "p_one_sided": _fixed(one_sided, 6),
        "p_two_sided": _fixed(two_sided, 6),
        "mean_difference_points": _mean_percent([difference for *_, difference in slates]),
        "after_registration": _fresh([difference for key, *_, difference in slates if key[1] > registered_on]),
        "slates": [
            {"sport": key[0], "date": key[1], "game_type": key[2], "top_heavy_entries": top,
             "flatter_entries": flat, "difference_points": _mean_percent([difference])}
            for key, top, flat, difference in slates
        ],
    }


def _fresh(differences: Sequence[Fraction]) -> dict[str, object]:
    """The same test on the slates after registration alone: the ones that did not choose its direction."""

    worse, better = sum(value > 0 for value in differences), sum(value < 0 for value in differences)
    return {"slates_with_both": len(differences), "worse": worse, "better": better,
            "p_one_sided": _fixed(sign_test(worse, better)[0], 6)}


def _trigger(test: Mapping[str, object], metrics: ResultsMetrics) -> dict[str, object]:
    """Always on the registered population: an era a caller names moves the scopes, never the trigger."""

    one_sided, _ = sign_test(int(test["worse"]), int(test["better"]))
    slates = int(test["worse"]) + int(test["better"])  # tied slates drop out of the test and the count
    return {
        "scope": metrics.trigger_scope,
        "engine_era_start": metrics.engine_era_start,
        "registered_on": metrics.registered_on,
        "alpha": str(metrics.trigger_alpha),
        "min_slates": metrics.trigger_min_slates,
        "slates": slates,
        "p_one_sided": test["p_one_sided"],
        "met": one_sided < metrics.trigger_alpha and slates >= metrics.trigger_min_slates,
        "when_met": ("open a roadmap row for the per-contest term inside Session 50's placement objective; this "
                     "report states the trigger and acts on nothing"),
    }


def _all_sport(history: EntryHistory, metrics: ResultsMetrics) -> tuple[list[HistoryRow], Counter[str]]:
    """Every sport's paid entries outside the excluded game types. A non-NFL row the parser named for a value rule
    (an unreadable cell, a place outside its field, a contest that disagrees) is left out and counted; an NFL row never
    has one, because the parser refuses the file instead."""

    named = {note["row"] for note in history.notes if note["kind"] == "NON_NFL_RULE_NOT_MET"}
    counted: list[HistoryRow] = []
    left_out: Counter[str] = Counter()
    for row in history.rows:
        if row.game_type in metrics.excluded_game_types or row.entry_fee_cents == 0:
            continue
        if row.row in named:
            left_out[row.sport] += 1
        else:
            counted.append(row)
    return counted, left_out


def _era_rows(nfl: Sequence[HistoryRow], metrics: ResultsMetrics, start: str) -> list[HistoryRow]:
    return [row for row in nfl if row.game_type in metrics.engine_game_types and str(row.contest_start)[:10] >= start]


# --------------------------------------------------------------------- the v2 readings (Session 77, R38)

FIRST_PLACE_READING = (
    "First-place and top-1% finishes are rare at this volume, so each count sits beside the sum of its entries' random "
    "shares; each contest's best percentile, beside the best of that many random places, is the reading with data.")
POINTS_BEHIND_FIRST = {"state": "NOT_IN_EXPORT", "named_source": "SESSION_18_PER_CONTEST_THRESHOLDS"}


def _by_contest(rows: Sequence[HistoryRow]) -> list[list[HistoryRow]]:
    """Each Contest ID's entries, by start time, game type and key. The parser makes a contest's numeric cells agree."""

    groups: dict[str, list[HistoryRow]] = {}
    for row in rows:
        groups.setdefault(row.contest_key, []).append(row)
    return sorted(groups.values(), key=lambda group: (str(group[0].contest_start), group[0].game_type,
                                                      group[0].contest_key))


def _counted(entries: Sequence[HistoryRow], realized: Callable[[HistoryRow], bool],
             random: Callable[[int], Fraction]) -> dict[str, object]:
    expected = sum((random(row.contest_entries) for row in entries), Fraction(0))
    return {"entries": sum(realized(row) for row in entries), "random": _fixed(expected, 6) if entries else None}


def _first_place_slice(contests: Sequence[list[HistoryRow]]) -> dict[str, object]:
    entries = [row for group in contests for row in group]
    best = [finishing_percentile(min(row.place for row in group), group[0].contest_entries) for group in contests]
    return {
        "contests": len(contests),
        "entries": len(entries),
        "best_percentile": {
            "realized": _mean_percent(best),
            "random": _mean_percent([random_best_percentile(group[0].contest_entries, len(group))
                                     for group in contests]),
        },
        "first_place": _counted(entries, lambda row: in_first(row.place), random_first),
        "top_1": _counted(entries, lambda row: in_top_1(row.place, row.contest_entries), random_top_1),
    }


def _contest_row(group: Sequence[HistoryRow], band: str) -> dict[str, object]:
    first, ours = group[0], len(group)
    entries, best = first.contest_entries, min(row.place for row in group)
    return {
        "contest_key": first.contest_key,
        "date": str(first.contest_start)[:10],
        "game_type": first.game_type,
        "contest_entries": entries,
        "entries": ours,
        "band": band,
        "best_place": best,
        "best_percentile": _fixed(finishing_percentile(best, entries) * 100),
        "random_best_percentile": _fixed(random_best_percentile(entries, ours) * 100),
        "first_place_entries": sum(in_first(row.place) for row in group),
        "first_place_random": str(ours * random_first(entries)),
        "top_1_entries": sum(in_top_1(row.place, entries) for row in group),
        "top_1_random": str(ours * random_top_1(entries)),
    }


def _first_place(rows: Sequence[HistoryRow], metrics: ResultsMetrics) -> dict[str, object]:
    """Goal 1, per contest: the scope's overall reading, v1's payout bands, and every contest's own row."""

    edges = metrics.paid_fraction_edges
    shapes = _shape_labels(edges)
    contests = _by_contest(rows)
    bands: dict[int, list[list[HistoryRow]]] = {}
    for group in contests:
        bands.setdefault(_shape_band(group[0], edges), []).append(group)
    return {
        "overall": _first_place_slice(contests),
        "by_payout_shape": [{"band": shapes[band], "first_place_label": LABEL if band == 0 else None,
                             **_first_place_slice(bands[band])} for band in sorted(bands)],
        "contests": [_contest_row(group, shapes[_shape_band(group[0], edges)]) for group in contests],
    }


def _won_nothing(row: HistoryRow) -> bool:
    return row.winnings_non_ticket_cents == 0 and row.winnings_ticket_cents == 0


def _washouts(rows: Sequence[HistoryRow]) -> dict[str, object]:
    """Goal 2, per portfolio (v1's fine slate): a washout is every paid entry winning nothing, tickets included."""

    portfolios: dict[tuple[str, str, str], list[HistoryRow]] = {}
    for row in rows:
        portfolios.setdefault(fine_slate_key(row), []).append(row)
    listed, shares = [], []
    for key in sorted(portfolios, key=lambda found: (found[1], found[2], found[0])):
        group = portfolios[key]
        contests = _by_contest(group)
        share = random_washout((contest[0].contest_entries, contest[0].places_paid, len(contest))
                               for contest in contests)
        shares.append(share)
        listed.append({"sport": key[0], "contest_start": key[1], "game_type": key[2], "entries": len(group),
                       "contests": len(contests), "washout": all(_won_nothing(row) for row in group),
                       "random": _fixed(share * 100), "random_exact": str(share)})
    washouts = sum(item["washout"] for item in listed)
    return {
        "portfolios": len(listed),
        "washouts": washouts,
        "rate": {"realized": _ratio_percent(washouts, len(listed)), "random": _mean_percent(shares)},
        "by_portfolio": listed,
    }


# ------------------------------------------------------------------------------ the bootstrap (Session 71b)
#
# Each statistic is a ratio of slate sums, sum(Y_g) / sum(X_g), over the slice's slates holding at least one of its
# entries. Both methods are bootstrap-t with CR1 standard errors; only the resampling changes at `pairs_min_slates`.
# The wild draw holds X_g fixed and moves the unrestricted residual e_g = Y_g - theta X_g by a Webb weight. The
# resampled figures are IEEE doubles (`math.fsum`, `/`, `sqrt`) in a fixed order; estimates stay exact.

PAIRS = "PAIRS_CLUSTER_STUDENTIZED"
WILD = "WILD_WEBB_STUDENTIZED"
WEBB_WEIGHTS = (-math.sqrt(1.5), -1.0, -math.sqrt(0.5), math.sqrt(0.5), 1.0, math.sqrt(1.5))
BLANKS_REMOVED = "_blanks_removed"
RETURN = "realized_return_on_fees"
_EXCESS = {
    "percentile_excess": (finishing_percentile, random_percentile),
    "top_10_excess": (in_top, random_top),
    "bottom_10_excess": (in_bottom, random_bottom),
}
STATISTICS = tuple(sorted([*_EXCESS, *(name + BLANKS_REMOVED for name in _EXCESS), RETURN]))


@dataclass(frozen=True)
class BootstrapSettings:
    seed: int
    resamples: int
    level: Fraction
    pairs_min_slates: int
    interval_min_slates: int
    alpha: Fraction
    power: Fraction


def bootstrap_settings(metrics: ResultsMetrics) -> BootstrapSettings:
    """The registered section, already validated by the loader, as numbers."""

    section = metrics.bootstrap
    return BootstrapSettings(section["seed"], section["resamples"], Fraction(section["level"]),
                             section["pairs_min_slates"], section["interval_min_slates"],
                             Fraction(section["mde_alpha_two_sided"]), Fraction(section["mde_power"]))


def _method_block(metrics: ResultsMetrics) -> dict[str, object]:
    return {**metrics.bootstrap, "pairs_method": PAIRS, "wild_method": WILD, "statistics": list(STATISTICS),
            "degrees_of_freedom": "SLATES_MINUS_ONE", "quantile": "ORDER_STATISTIC_CEIL",
            "seeding": "SHA256_OF_SEED_SCOPE_ROLLUP_LABEL_STATISTIC"}


def _t_two_sided(t: float, df: int) -> float:
    """`P(|T| < t)` for integer df: the exact finite series (Abramowitz and Stegun 26.7.3 odd, 26.7.4 even)."""

    theta = math.atan(t / math.sqrt(df))
    sine, cosine = math.sin(theta), math.cos(theta)
    if df % 2 == 0:
        term = total = 1.0
        for k in range(1, df // 2):
            term *= (2 * k - 1) / (2 * k) * cosine * cosine
            total += term
        return sine * total
    total = 0.0  # df 1, the Cauchy, has no bracket term
    if df > 1:
        term = total = cosine
        for k in range(1, (df - 1) // 2):
            term *= (2 * k) / (2 * k + 1) * cosine * cosine
            total += term
    return 2 / math.pi * (theta + sine * total)


def t_quantile(probability: Fraction, df: int) -> float:
    """Student's t quantile above the median, by bisection on the exact series; no scipy."""

    if df < 1 or not Fraction(1, 2) < probability < 1:
        raise ValueError("t_quantile needs df >= 1 and a probability strictly between 1/2 and 1")
    target = float(2 * Fraction(probability) - 1)
    low, high = 0.0, 1.0
    while _t_two_sided(high, df) < target:
        low, high = high, 2 * high
    while True:
        middle = (low + high) / 2
        if middle in (low, high):
            return high
        if _t_two_sided(middle, df) < target:
            low = middle
        else:
            high = middle


def cr1_standard_error(residuals: Sequence[float], x: Sequence[float]) -> float:
    """`sqrt(G/(G-1) * sum(e_g^2)) / sum(X_g)`, the cluster-robust (CR1) standard error of `sum(Y) / sum(X)`."""

    count = len(x)
    return math.sqrt(count / (count - 1) * math.fsum(value * value for value in residuals)) / math.fsum(x)


def minimum_detectable_effect(standard_error: float, slates: int, alpha: Fraction, power: Fraction) -> float:
    """`(t_{1 - alpha/2, G-1} + t_{power, G-1}) * SE`: the smallest true effect a two-sided test finds at that power."""

    return (t_quantile(1 - alpha / 2, slates - 1) + t_quantile(power, slates - 1)) * standard_error


def _studentized(shift: float, standard_error: float) -> float:
    """A resample with no spread left is never dropped: it sits at +-inf by the sign of its shift. A pairs draw with no
    shift either (every drawn slate exactly at theta) has no sign: NaN, which nulls the interval."""

    if standard_error:
        return shift / standard_error
    return math.copysign(math.inf, shift) if shift else math.nan


def wild_t(weights: Sequence[float], residuals: Sequence[float], x: Sequence[float]) -> float:
    """One wild draw: Y*_g = theta X_g + v_g e_g with X_g fixed, so theta* - theta = sum(v e) / sum(X)."""

    moved = [weight * residual for weight, residual in zip(weights, residuals)]
    shift = math.fsum(moved) / math.fsum(x)
    return _studentized(shift, cr1_standard_error([value - shift * size for value, size in zip(moved, x)], x))


def _pairs_t(indices: Sequence[int], y: Sequence[float], x: Sequence[float], theta: float) -> float | None:
    sizes = [x[index] for index in indices]
    total = math.fsum(sizes)
    if total == 0:  # unreachable while every cluster's denominator is positive; counted, never dropped
        return None
    values = [y[index] for index in indices]
    star = math.fsum(values) / total
    return _studentized(star - theta, cr1_standard_error([v - star * s for v, s in zip(values, sizes)], sizes))


def resample(y: Sequence[float], x: Sequence[float], theta: float, settings: BootstrapSettings,
             draw: Callable[[], float], *, pairs: bool) -> tuple[str, list[float], int]:
    """The method, each resample's t* and the count of pairs resamples whose denominator was zero.

    Draws use `random()` alone, the one stream Python keeps across versions: `int(u * G)` picks a slate, `int(u * 6)`
    a Webb weight.
    """

    count, values, zero = len(x), [], 0
    if pairs:
        for _ in range(settings.resamples):
            t_star = _pairs_t([int(draw() * count) for _ in range(count)], y, x, theta)
            if t_star is None:
                zero += 1
            else:
                values.append(t_star)
        return PAIRS, values, zero
    residuals = [value - theta * size for value, size in zip(y, x)]
    for _ in range(settings.resamples):
        values.append(wild_t([WEBB_WEIGHTS[int(draw() * 6)] for _ in range(count)], residuals, x))
    return WILD, values, zero


def order_statistics(level: Fraction, resamples: int) -> tuple[int, int]:
    """The 0-based indices of the lower and upper order statistics: `ceil(B a) - 1` and `ceil(B (1 - a)) - 1`."""

    tail = (1 - level) / 2
    return math.ceil(resamples * tail) - 1, math.ceil(resamples * (1 - tail)) - 1


def _percent(value: float, scale: int = 100) -> str:
    return _fixed(Fraction(value) * scale)


def interval_figures(theta: float, standard_error: float, t_values: Sequence[float],
                     settings: BootstrapSettings, scale: int = 100) -> dict[str, object]:
    """The bootstrap-t interval `[theta - q_hi SE, theta - q_lo SE]`, null when an infinite t* is an endpoint or a t*
    has no sign at all. `scale` is the unit of the printed figures: 100 for percent, 1 for a count or a rate (Session
    73b's descriptors)."""

    undefined = sum(math.isnan(value) for value in t_values)
    degenerate = undefined + sum(math.isinf(value) for value in t_values)
    if undefined:
        return {"interval": None, "reason": "DEGENERATE_RESAMPLES", "degenerate_resamples": degenerate}
    ordered = sorted(t_values)
    low, high = order_statistics(settings.level, settings.resamples)
    if math.isinf(ordered[low]) or math.isinf(ordered[high]):
        return {"interval": None, "reason": "DEGENERATE_RESAMPLES", "degenerate_resamples": degenerate}
    return {"interval": {"low": _percent(theta - ordered[high] * standard_error, scale),
                         "high": _percent(theta - ordered[low] * standard_error, scale)},
            "reason": None, "degenerate_resamples": degenerate}


def _clusters(rows: Sequence[HistoryRow], statistic: str) -> list[tuple[Fraction, Fraction]]:
    """`(Y_g, X_g)` per slate in slate-key order, only where `X_g > 0`: a slate holding none of the statistic's entries
    (an all-blank slate, for a blanks-removed statistic) is not one of its clusters."""

    groups: dict[tuple[str, str, str], list[HistoryRow]] = {}
    for row in rows:
        groups.setdefault(slate_key(row), []).append(row)
    clusters = []
    for key in sorted(groups):
        group = groups[key]
        if statistic == RETURN:
            pair = (Fraction(sum(row.winnings_non_ticket_cents + row.winnings_ticket_cents - row.entry_fee_cents
                                 for row in group)), Fraction(sum(row.entry_fee_cents for row in group)))
        else:
            if statistic.endswith(BLANKS_REMOVED):
                group = [row for row in group if not is_blank(row.points_hundredths)]
            realized, expected = _EXCESS[statistic.removesuffix(BLANKS_REMOVED)]
            pair = (sum((Fraction(realized(row.place, row.contest_entries)) - expected(row.contest_entries)
                         for row in group), Fraction(0)), Fraction(len(group)))
        if pair[1] > 0:
            clusters.append(pair)
    return clusters


def _statistic(clusters: Sequence[tuple[Fraction, Fraction]], settings: BootstrapSettings,
               draw: Callable[[], float], scale: int = 100) -> dict[str, object]:
    count = len(clusters)
    figures: dict[str, object] = {"slates": count, "estimate": None, "method": None, "interval": None,
                                  "standard_error": None, "mde": None, "reason": None, "degenerate_resamples": 0}
    if count:
        exact = sum(y for y, _ in clusters) / sum(x for _, x in clusters)
        figures["estimate"] = _fixed(exact * scale)
    if count < settings.interval_min_slates:
        return {**figures, "reason": f"FEWER_THAN_{settings.interval_min_slates}_SLATES"}
    residuals = [y - exact * x for y, x in clusters]  # exact, so a slice with no spread is caught exactly
    if not any(residuals):
        return {**figures, "reason": "ZERO_STANDARD_ERROR"}
    x = [float(size) for _, size in clusters]
    standard_error = cr1_standard_error([float(value) for value in residuals], x)
    method, t_values, zero = resample([float(value) for value, _ in clusters], x, float(exact), settings, draw,
                                      pairs=count >= settings.pairs_min_slates)
    figures.update(method=method, standard_error=_percent(standard_error, scale), mde=_percent(
        minimum_detectable_effect(standard_error, count, settings.alpha, settings.power), scale))
    if zero:
        return {**figures, "reason": "ZERO_DENOMINATOR_RESAMPLES", "degenerate_resamples": zero}
    return {**figures, **interval_figures(float(exact), standard_error, t_values, settings, scale)}


def _uncertainty(settings: BootstrapSettings, scope: str, rollup: str, described: Mapping[str, object],
                 rows: Sequence[HistoryRow]) -> dict[str, dict[str, object]]:
    """Each statistic draws from its own generator, seeded from the slice's own name: no row moves another's draws."""

    figures = {}
    for statistic in STATISTICS:
        key = json.dumps([settings.seed, scope, rollup, described, statistic], sort_keys=True).encode("utf-8")
        draw = random.Random(int(sha256_bytes(key), 16)).random
        figures[statistic] = _statistic(_clusters(rows, statistic), settings, draw)
    return figures


def build_report(history: EntryHistory, *, metrics: ResultsMetrics, source_sha256: str, source_bytes: int,
                 engine_era_start: str | None = None, bootstrap: bool = False) -> dict[str, object]:
    """The report payload (`nfl_results_report_v1`, or `_v2` from a v2 metrics file); `engine_era_start` overrides the
    registered default.

    `bootstrap=True` (what the writer passes) adds the `bootstrap` method block and every scope slice's `uncertainty`.
    A v2 payload is the v1 payload with its version and metrics named, plus `first_place` and `washouts` in each scope,
    the v2 definitions, `points_behind_first` and `first_place_reading`.
    """

    if engine_era_start is not None and not is_calendar_date(engine_era_start):
        raise ValueError("engine_era_start must be a calendar date YYYY-MM-DD")
    era = metrics.engine_era_start if engine_era_start is None else engine_era_start
    counted, left_out = _all_sport(history, metrics)
    nfl = [row for row in counted if row.is_nfl]
    settings = bootstrap_settings(metrics) if bootstrap else None

    def measure(scope: str) -> Callable[[str, dict, Sequence[HistoryRow]], dict] | None:
        return None if settings is None else partial(_uncertainty, settings, scope)

    scope_rows = {"nfl": nfl, "engine_era": _era_rows(nfl, metrics, era)}
    scopes = {name: _scope(rows, metrics, measure(name)) for name, rows in scope_rows.items()}
    registered = nfl if metrics.trigger_scope == "nfl" else _era_rows(nfl, metrics, metrics.engine_era_start)
    extra = {} if settings is None else {"bootstrap": _method_block(metrics)}
    payload = {
        **extra,
        "schema_version": report_contract(metrics),
        "writer": WRITER,
        "metrics": {"version": metrics.version, "sha256": metrics.sha256},
        "source": {"sha256": source_sha256, "bytes": source_bytes, "contract": HISTORY_CONTRACT},
        "engine_era_start": {"date": era, "is_default": era == metrics.engine_era_start},
        "definitions": dict(DECLARED["rates"]),
        "populations": {
            **DECLARED["populations"],
            "excluded_game_types": list(metrics.excluded_game_types),
            "engine_game_types": list(metrics.engine_game_types),
        },
        "scopes": scopes,
        "within_slate_trigger": _trigger(_within_slate(registered, metrics.registered_on), metrics),
        "all_sport_check": {"entries": len(counted), "left_out_rule_not_met": dict(sorted(left_out.items())),
                            "overall": _slice(counted)},
        "notes": [
            {"kind": "PLACES_PAID_ABOVE_CONTEST_ENTRIES_CAPPED", "row": row.row, "entry_key": row.entry_key,
             "contest_key": row.contest_key}
            for row in nfl if row.places_paid_above_entries
        ],
        "parser_note_counts": dict(sorted(Counter(note["kind"] for note in history.notes).items())),
        "does_not_establish": list(metrics.does_not_establish),
    }
    if payload["schema_version"] == REPORT_V2:
        payload["definitions"].update({**DECLARED_V2["first_place"], **DECLARED_V2["washout"]})
        for name, rows in scope_rows.items():
            scopes[name]["first_place"] = _first_place(rows, metrics)
            scopes[name]["washouts"] = _washouts(rows)
        payload["points_behind_first"] = dict(POINTS_BEHIND_FIRST)
        payload["first_place_reading"] = FIRST_PLACE_READING
    return payload


# ------------------------------------------------------------------------------------ the command (Session 71b)

REPORT_CODES = (
    "RESULTS_REPORT_INPUT_INVALID",
    "RESULTS_REPORT_SNAPSHOT_INVALID",
    "RESULTS_REPORT_ARTIFACT_CONFLICT",
    "RESULTS_REPORT_WRITE_FAILED",
)
REPORT_RECOVERY = (
    "This file is derived from the snapshot and the registered metrics. Delete it, or the whole reports/<sha256>/"
    " folder, and rerun results-report to rebuild it; a fix that changes a written byte takes a new writer version"
    " instead."
)
_SHA256 = re.compile(r"[0-9a-f]{64}")


_CONTRACT_INFIX = {REPORT_VERSION: "", REPORT_V2: ".v2"}


def report_name(era: str, contract: str = REPORT_VERSION) -> str:
    """The era and the contract name the file, so another era's or version's report is another file, never a
    conflict; v1 keeps its Session 71b name."""

    return f"results_report.era-{era}{_CONTRACT_INFIX[contract]}.{WRITER}.json"


# ------------------------------------------------------------------------------------- the table (Session 71c)
#
# Markdown beside the JSON, every figure the payload's own string. Money is the one conversion, exact cents to signed
# dollars. Nothing printed comes from a CSV cell, so nothing needs escaping. It reads only the written payload, so
# `render_table(json.loads(file))` is the table, and it raises nothing of its own, so no message carries a figure.

PAYOUT_SHAPE_HEADING = "Payout shape"
MISSING = "n/a"
_RATE_TITLES = (("percentile", "Percentile"), ("top_10", "Top 10%"), ("bottom_10", "Bottom 10%"))
_SHAPE_HEADER = ("Band", "Label", "Entries", "Slates", "Rate", "Realized % (random)", "Excess, points", "Interval",
                 "MDE")


def table_name(era: str, contract: str = REPORT_VERSION) -> str:
    return f"results_report.era-{era}{_CONTRACT_INFIX[contract]}.{WRITER}.md"


def _dollars(cents: int) -> str:
    """`-14596` is `-$145.96`; `_cents_text`, which names the JSON's fee bands, would print `$-146.04`."""

    whole, part = divmod(abs(cents), 100)
    return f"{'-' if cents < 0 else ''}${whole:,}.{part:02d}"


def _shown(value: object) -> str:
    return MISSING if value is None else str(value)


def _beside(rates: Mapping[str, object], name: str) -> str:
    pair = rates[name]
    return MISSING if pair["realized"] is None else f"{pair['realized']} ({pair['random']})"


def _grid(header: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    return [f"| {' | '.join(row)} |" for row in (header, ["---"] * len(header), *rows)]


_OVERALL_ROWS: tuple[tuple[str, Callable[[Mapping[str, object]], str]], ...] = (
    ("Entries", lambda block: str(block["entries"])),
    ("Slates", lambda block: str(block["slates"])),
    ("Blanks", lambda block: str(block["blanks"])),
    ("Fees", lambda block: _dollars(block["fees_cents"])),
    ("Net, tickets at face value", lambda block: _dollars(block["net_cents"])),
    ("Realized return on fees, %", lambda block: _shown(block["realized_return_on_fees"])),
    ("Rake-implied return, %", lambda block: _shown(block["rake_implied_return"])),
    ("Percentile % (random), lower is better", lambda block: _beside(block["with_blanks"], "percentile")),
    ("Top 10% (random), higher is better", lambda block: _beside(block["with_blanks"], "top_10")),
    ("Bottom 10% (random), lower is better", lambda block: _beside(block["with_blanks"], "bottom_10")),
)


def _shape_rows(band: str, label: str, block: Mapping[str, object]) -> list[list[str]]:
    """Three lines, one per rate; the band, label, entries and slates on the first line only."""

    rows = []
    for name, title in _RATE_TITLES:
        figures = block["uncertainty"][f"{name}_excess"]
        interval = figures["interval"]
        span = f"[{interval['low']}, {interval['high']}]" if interval else f"{MISSING} ({figures['reason']})"
        lead = [band, label, str(block["entries"]), str(block["slates"])] if not rows else [""] * 4
        rows.append([*lead, title, _beside(block["with_blanks"], name), _shown(figures["estimate"]), span,
                     _shown(figures["mde"])])
    return rows


def _shape_section(title: str, scope: Mapping[str, object], method: Mapping[str, object]) -> list[str]:
    lines = [f"## {PAYOUT_SHAPE_HEADING}, {title}", ""]
    if not scope["overall"]["entries"]:
        return [*lines, "No entries in this scope.", ""]
    note = ("Places paid over entries, banded. Excess is realized minus random in percentage points: above 0 is worse "
            "for percentile and bottom 10%, better for top 10%. It is rounded once from the exact figure, so it can "
            "differ in the last place from the difference of the two printed rates. Intervals are slate-cluster "
            f"bootstrap-t at level {method['level']}; the MDE is the smallest true excess a two-sided test at alpha "
            f"{method['mde_alpha_two_sided']} finds with power {method['mde_power']}.")
    rows = _shape_rows("All shapes", "", scope["overall"])
    for band in scope["by_payout_shape"]:
        rows += _shape_rows(band["band"], _shown(band["first_place_label"]), band)
    return [*lines, note, "", *_grid(_SHAPE_HEADER, rows), ""]


def _within_section(payload: Mapping[str, object]) -> list[str]:
    tests = [payload["scopes"][scope]["within_slate_test"] for scope in SCOPES]
    fresh = [test["after_registration"] for test in tests]
    rows = [
        ["Slates with both", *(str(test["slates_with_both"]) for test in tests)],
        ["Top-heavy worse / better / tied", *(f"{test['worse']} / {test['better']} / {test['tied']}" for test in tests)],
        ["Mean difference, points", *(_shown(test["mean_difference_points"]) for test in tests)],
        ["p, one-sided", *(test["p_one_sided"] for test in tests)],
        ["p, two-sided", *(test["p_two_sided"] for test in tests)],
        ["After registration: slates with both", *(str(block["slates_with_both"]) for block in fresh)],
        ["After registration: worse / better", *(f"{block['worse']} / {block['better']}" for block in fresh)],
        ["After registration: p, one-sided", *(block["p_one_sided"] for block in fresh)],
    ]
    trigger = payload["within_slate_trigger"]
    return [
        "## Within-slate test: top-heavy against flatter", "",
        (f"Per slate holding both, the mean percentile of {LABEL} entries minus the flatter ones' (above 0: top-heavy "
         "finished worse); the exact sign test, ties dropped."), "",
        *_grid(("", "NFL", "Engine era"), rows), "",
        (f"Trigger, on {trigger['scope']} from {trigger['engine_era_start']} (registered {trigger['registered_on']}): "
         f"{trigger['slates']} slates against a minimum of {trigger['min_slates']}, p one-sided "
         f"{trigger['p_one_sided']} against alpha {trigger['alpha']}; met: {json.dumps(trigger['met'])}. When met: "
         f"{trigger['when_met']}."), "",
    ]


FIRST_PLACE_HEADING = "First place by contest"
WASHOUT_HEADING = "Washouts"
_FIRST_PLACE_HEADER = ("Band", "Label", "Contests", "Entries", "Best percentile % (random), lower is better",
                       "First place (random)", "Top 1% (random)")


def _first_place_cells(block: Mapping[str, object]) -> list[str]:
    return [str(block["contests"]), str(block["entries"]), _beside(block, "best_percentile"),
            *(f"{block[name]['entries']} ({_shown(block[name]['random'])})" for name in ("first_place", "top_1"))]


def _first_place_section(title: str, scope: Mapping[str, object]) -> list[str]:
    lines = [f"## {FIRST_PLACE_HEADING}, {title}", ""]
    block = scope["first_place"]
    if not block["overall"]["contests"]:
        return [*lines, "No entries in this scope.", ""]
    note = ("Each contest's best entry: its finishing percentile beside the mean best of that many random places, "
            "averaged over contests. First place and top 1% count entries, each beside the sum of its entries' random "
            "shares (1/n, and floor(n/100)/n). Bands are places paid over entries, as above.")
    rows = [["All shapes", "", *_first_place_cells(block["overall"])]]
    rows += [[band["band"], _shown(band["first_place_label"]), *_first_place_cells(band)]
             for band in block["by_payout_shape"]]
    return [*lines, note, "", *_grid(_FIRST_PLACE_HEADER, rows), ""]


def _goal_sections(payload: Mapping[str, object]) -> list[str]:
    """v2 only: first place by contest in each scope, the reading and points behind first, then washouts."""

    scopes, behind = payload["scopes"], payload["points_behind_first"]
    blocks = [scopes[scope]["washouts"] for scope in SCOPES]
    rows = [
        ["Portfolios", *(str(block["portfolios"]) for block in blocks)],
        ["Washouts", *(str(block["washouts"]) for block in blocks)],
        ["Washout rate % (random), lower is better", *(_beside(block, "rate") for block in blocks)],
    ]
    return [
        *_first_place_section("NFL", scopes["nfl"]),
        *_first_place_section("engine era", scopes["engine_era"]),
        f"{payload['first_place_reading']} Points behind first: {behind['state']} ({behind['named_source']}).", "",
        f"## {WASHOUT_HEADING}", "",
        ("A portfolio is the paid entries sharing a contest start time and game type; a washout is one where every "
         "entry won nothing, cash and tickets. Random: each contest's places drawn independently and uniformly, "
         "Places_Paid as given."), "",
        *_grid(("", "NFL", "Engine era"), rows), "",
    ]


def render_table(payload: Mapping[str, object]) -> bytes:
    """The short readable table of one report payload (`results_report.era-<date>.w1.md`, or `.v2.w1.md`): Overall
    first (NFL, engine era, all sports), then each scope's payout-shape rows with each rate's excess, interval and MDE,
    then the within-slate test and its trigger; a v2 payload adds first place by contest and washouts after it. A null
    prints `n/a`, never a zero. ASCII, LF, one trailing LF."""

    era, source, scopes = payload["engine_era_start"], payload["source"], payload["scopes"]
    v2 = payload["schema_version"] == REPORT_V2
    columns = (scopes["nfl"]["overall"], scopes["engine_era"]["overall"], payload["all_sport_check"]["overall"])
    only = (f"Only in `{report_name(era['date'], REPORT_V2)}` beside this file: the format, field-size, fee, month "
            "and slate rollups, fee concentration, the blanks-removed rates, the return's interval, each contest's "
            "best entry and each portfolio's washout." if v2 else
            f"Only in `{report_name(era['date'])}` beside this file: the format, field-size, fee, month and slate "
            "rollups, fee concentration, the blanks-removed rates and the return's interval.")
    lines = [
        "# NFL results report", "",
        (f"`{payload['schema_version']}`, writer `{payload['writer']}`, metrics `{payload['metrics']['version']}`; "
         f"source `{source['sha256']}` ({source['bytes']} bytes); engine era from {era['date']} "
         f"({'registered default' if era['is_default'] else 'given'}). Realized results only."), "",
        "## Overall", "",
        *_grid(("", "NFL", "Engine era", "All sports"),
               [[label, *(cell(block) for block in columns)] for label, cell in _OVERALL_ROWS]), "",
        *_shape_section("NFL", scopes["nfl"], payload["bootstrap"]),
        *_shape_section("engine era", scopes["engine_era"], payload["bootstrap"]),
        *_within_section(payload),
        *(_goal_sections(payload) if v2 else ()),
        "## Not established", "",
        *(f"- {line}" for line in payload["does_not_establish"]), "",
        only,
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")


@dataclass(frozen=True)
class ReportOutcome:
    """`COMPLETE` and `ALREADY_PRESENT` exit 0; `REFUSED` and `WRITE_FAILED` exit 2. Nothing here carries money."""

    status: str
    problems: tuple[str, ...]
    files: dict[str, dict[str, str | None]]
    does_not_establish: tuple[str, ...]
    source_sha256: str | None = None
    engine_era_start: Mapping[str, object] | None = None
    headline: Mapping[str, object] | None = None
    contract: str = REPORT_VERSION

    @property
    def exit_code(self) -> int:
        return 0 if self.status in ("COMPLETE", "ALREADY_PRESENT") else 2

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "exit_code": self.exit_code,
            "problems": list(self.problems),
            "contract": self.contract,
            "source_sha256": self.source_sha256,
            "engine_era_start": self.engine_era_start,
            "files": self.files,
            "headline": self.headline,
            "does_not_establish": list(self.does_not_establish),
        }


def headline(payload: Mapping[str, object]) -> dict[str, object]:
    """What stdout carries: counts, place-based rates, the within-slate test and the trigger; no fee or winnings. A v2
    payload adds each scope's overall first-place reading and its washout counts (a yes or no per portfolio, never an
    amount); neither the per-contest nor the per-portfolio list."""

    v2 = payload["schema_version"] == REPORT_V2

    def scope(block: Mapping[str, object]) -> dict[str, object]:
        blanks: Counter[str] = Counter()
        for row in block["by_slate"]:
            blanks[row["date"]] += row["blanks"]
        test = block["within_slate_test"]
        goals = {} if not v2 else {
            "first_place": block["first_place"]["overall"],
            "washouts": {key: block["washouts"][key] for key in ("portfolios", "washouts", "rate")},
        }
        return {
            "entries": block["overall"]["entries"],
            "slates": block["slates"],
            "fine_slates": block["fine_slates"],
            "contests": block["overall"]["contests"],
            "blanks": block["overall"]["blanks"],
            "blanks_by_date": {day: count for day, count in sorted(blanks.items()) if count},
            "rates": block["overall"]["with_blanks"],
            "within_slate_test": {key: test[key] for key in ("slates_with_both", "worse", "better", "tied",
                                                             "p_one_sided")},
            **goals,
        }

    check = payload["all_sport_check"]
    return {
        "nfl": scope(payload["scopes"]["nfl"]),
        "engine_era": scope(payload["scopes"]["engine_era"]),
        "all_sport_check": {"entries": check["entries"], "left_out_rule_not_met": check["left_out_rule_not_met"],
                            "blanks": check["overall"]["blanks"], "rates": check["overall"]["with_blanks"]},
        "within_slate_trigger": dict(payload["within_slate_trigger"]),
    }


def _snapshot(path: Path, sha256: str) -> tuple[bytes | None, str | None]:
    """The snapshot's bytes, or why they are not the bytes its name promises.

    One `lstat` decides: nothing there is `absent`; a symlink is `symlink` (never followed); anything but a plain file
    (a directory, a FIFO that would block `open` forever, a device) or a stat that fails is `unreadable`. The open
    refuses a symlink that took the name since, where the platform can.
    """

    try:
        mode = os.lstat(path).st_mode
    except (FileNotFoundError, NotADirectoryError):
        return None, "absent"
    except OSError:
        return None, "unreadable"
    if stat.S_ISLNK(mode):
        return None, "symlink"
    if not stat.S_ISREG(mode):
        return None, "unreadable"
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
        with os.fdopen(os.open(path, flags), "rb") as handle:
            raw = handle.read(entry_history.MAX_BYTES + 1)
    except OSError:  # a lock, a permission, a symlink swapped in
        return None, "unreadable"
    # No intake writes a file past the cap, and its first MAX_BYTES + 1 bytes cannot hash to the name.
    if len(raw) > entry_history.MAX_BYTES or sha256_bytes(raw) != sha256:
        return None, "hash"
    return raw, None


def run_results_report(source_sha256: str, results_root: str | Path, engine_era_start: str | None = None, *,
                       metrics: ResultsMetrics | None = None,
                       metrics_version: str = CURRENT_METRICS_VERSION) -> ReportOutcome:
    """Read one snapshot, build the report and write it once: `<root>/reports/<sha256>/results_report.era-<date>.w1.json`
    (v1) or `.v2.w1.json` (v2), then the table beside it (`.w1.md`, `.v2.w1.md`).

    The registered metrics for `metrics_version` (v2 unless named) load first, from the module's path at call time: a
    defect there is `ResultsMetricsError`, a fault in a tracked file and never a refusal. A refused input writes
    nothing. The table is rendered before either write and written after the JSON, so a table that conflicts or fails
    leaves the JSON, and a rerun writes the table alone. The trigger reads the registered era whatever
    `engine_era_start` names.
    """

    metrics = load_results_metrics(registered_metrics_path(metrics_version)) if metrics is None else metrics
    contract = report_contract(metrics)
    files: dict[str, dict[str, str | None]] = {
        name: {"path": None, "state": "NOT_ATTEMPTED", "sha256": None} for name in ("report", "table")}
    refused = partial(ReportOutcome, "REFUSED", files=files, does_not_establish=metrics.does_not_establish,
                      contract=contract)
    if not isinstance(source_sha256, str) or not _SHA256.fullmatch(source_sha256):
        return refused((_problem("RESULTS_REPORT_INPUT_INVALID", "field=source_sha256"),))
    if engine_era_start is not None and not is_calendar_date(engine_era_start):
        return refused((_problem("RESULTS_REPORT_INPUT_INVALID", "field=engine_era_start"),), source_sha256=source_sha256)
    root = Path(results_root)
    raw, reason = _snapshot(root / "inbox" / f"{source_sha256}.csv", source_sha256)
    if reason is not None:
        return refused((_problem("RESULTS_REPORT_SNAPSHOT_INVALID", f"reason={reason}"),), source_sha256=source_sha256)
    try:
        history = entry_history.parse_entry_history(raw)
    except EntryHistoryRefused as refusal:  # a snapshot the parser no longer takes: its own codes, unchanged
        return refused(tuple(refusal.problems), source_sha256=source_sha256)
    payload = build_report(history, metrics=metrics, source_sha256=source_sha256, source_bytes=len(raw),
                           engine_era_start=engine_era_start, bootstrap=True)
    era = payload["engine_era_start"]
    done = partial(ReportOutcome, files=files, does_not_establish=metrics.does_not_establish,
                   source_sha256=source_sha256, engine_era_start=era, headline=headline(payload), contract=contract)
    folder = root / "reports" / source_sha256
    writes = (("report", folder / report_name(era["date"], contract), canonical_bytes(payload)),
              ("table", folder / table_name(era["date"], contract), render_table(payload)))
    for name, path, _ in writes:
        files[name]["path"] = str(path)
    for name, path, data in writes:
        try:
            files[name]["state"] = entry_history._write_once(
                path, data, code="RESULTS_REPORT_ARTIFACT_CONFLICT", recovery=REPORT_RECOVERY)
        except entry_history._Stop as stop:
            files[name].update(state="REFUSED", recovery=stop.recovery)
            return done("REFUSED", (_problem(stop.code, f"file={name}"),))
        except OSError as exc:
            files[name]["state"] = "WRITE_FAILED"
            written = _problem("RESULTS_REPORT_WRITE_FAILED", f"file={name}:exception={type(exc).__name__}")
            return done("WRITE_FAILED", (written,))
        files[name]["sha256"] = sha256_bytes(data)
    status = "ALREADY_PRESENT" if all(entry["state"] == "ALREADY_PRESENT" for entry in files.values()) else "COMPLETE"
    return done(status, ())


__all__ = [
    "BOTTOM_STRICT",
    "CURRENT_METRICS_VERSION",
    "DECLARED_V2",
    "DEFAULT_METRICS_PATH",
    "FIRST_PLACE_HEADING",
    "FIRST_PLACE_READING",
    "METRICS_V2",
    "METRICS_V2_PATH",
    "METRICS_VERSION",
    "METRICS_VERSIONS",
    "PAYOUT_SHAPE_HEADING",
    "REPORT_CODES",
    "REPORT_V2",
    "REPORT_VERSION",
    "WASHOUT_HEADING",
    "in_first",
    "in_top_1",
    "random_best_percentile",
    "random_first",
    "random_no_paid_place",
    "random_top_1",
    "random_washout",
    "registered_metrics_path",
    "report_contract",
    "ReportOutcome",
    "ResultsMetrics",
    "ResultsMetricsError",
    "BootstrapSettings",
    "STATISTICS",
    "bootstrap_settings",
    "build_report",
    "canonical_bytes",
    "cr1_standard_error",
    "headline",
    "interval_figures",
    "minimum_detectable_effect",
    "order_statistics",
    "render_table",
    "report_name",
    "resample",
    "run_results_report",
    "t_quantile",
    "table_name",
    "wild_t",
    "finishing_percentile",
    "fine_slate_key",
    "in_bottom",
    "in_top",
    "is_calendar_date",
    "is_blank",
    "load_results_metrics",
    "paid_fraction",
    "parse_results_metrics",
    "random_bottom",
    "random_percentile",
    "random_top",
    "sign_test",
    "slate_key",
]
