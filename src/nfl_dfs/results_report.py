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
"""

from __future__ import annotations

import json
import math
import random
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date
from fractions import Fraction
from functools import partial
from pathlib import Path
from typing import Callable, Mapping, Sequence

from . import entry_history
from .contest_facts import LABEL, THRESHOLD, canonical_bytes, first_place_label
from .entry_history import CONTRACT_VERSION as HISTORY_CONTRACT
from .entry_history import EntryHistory, EntryHistoryRefused, HistoryRow, _problem
from .hashing import sha256_bytes

METRICS_VERSION = "nfl_results_metrics_v1"
REPORT_VERSION = "nfl_results_report_v1"
WRITER = "w1"
DEFAULT_METRICS_PATH = Path(__file__).resolve().parents[2] / "config" / "results_metrics_v1.json"

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
    block = _object(document[section], frozenset(DECLARED.get(section, {})) | extra, section)
    for key, text in DECLARED.get(section, {}).items():
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
    _object(document, frozenset({"schema_version", "registered_at", "authority", "populations", "rates", "slates",
                                 "bands", "fee_concentration_top", "within_slate_test", "bootstrap",
                                 "does_not_establish"}), "file")
    if document["schema_version"] != METRICS_VERSION:
        raise _invalid("schema_version", f"must be {METRICS_VERSION}")
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
    )


def load_results_metrics(path: str | Path = DEFAULT_METRICS_PATH) -> ResultsMetrics:
    try:
        raw = Path(path).read_bytes()
    except OSError as exc:
        raise ResultsMetricsError(f"results metrics unreadable: {type(exc).__name__}") from None
    return parse_results_metrics(raw)


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
FEWER_SLATES = "FEWER_THAN_5_SLATES"


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
    """A resample with no spread left is never dropped: it sits at +-inf by the sign of its shift."""

    return shift / standard_error if standard_error else math.copysign(math.inf, shift)


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


def _percent(value: float) -> str:
    return _fixed(Fraction(value) * 100)


def interval_figures(theta: float, standard_error: float, t_values: Sequence[float],
                     settings: BootstrapSettings) -> dict[str, object]:
    """The bootstrap-t interval `[theta - q_hi SE, theta - q_lo SE]`, null when an infinite t* is an endpoint."""

    ordered = sorted(t_values)
    low, high = order_statistics(settings.level, settings.resamples)
    degenerate = sum(math.isinf(value) for value in ordered)
    if math.isinf(ordered[low]) or math.isinf(ordered[high]):
        return {"interval": None, "reason": "DEGENERATE_RESAMPLES", "degenerate_resamples": degenerate}
    return {"interval": {"low": _percent(theta - ordered[high] * standard_error),
                         "high": _percent(theta - ordered[low] * standard_error)},
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
               draw: Callable[[], float]) -> dict[str, object]:
    count = len(clusters)
    figures: dict[str, object] = {"slates": count, "estimate": None, "method": None, "interval": None,
                                  "standard_error": None, "mde": None, "reason": None, "degenerate_resamples": 0}
    if count:
        exact = sum(y for y, _ in clusters) / sum(x for _, x in clusters)
        figures["estimate"] = _fixed(exact * 100)
    if count < settings.interval_min_slates:
        return {**figures, "reason": FEWER_SLATES}
    residuals = [y - exact * x for y, x in clusters]  # exact, so a slice with no spread is caught exactly
    if not any(residuals):
        return {**figures, "reason": "ZERO_STANDARD_ERROR"}
    x = [float(size) for _, size in clusters]
    standard_error = cr1_standard_error([float(value) for value in residuals], x)
    method, t_values, zero = resample([float(value) for value, _ in clusters], x, float(exact), settings, draw,
                                      pairs=count >= settings.pairs_min_slates)
    figures.update(method=method, standard_error=_percent(standard_error), mde=_percent(minimum_detectable_effect(
        standard_error, count, settings.alpha, settings.power)))
    if zero:
        return {**figures, "reason": "ZERO_DENOMINATOR_RESAMPLES", "degenerate_resamples": zero}
    return {**figures, **interval_figures(float(exact), standard_error, t_values, settings)}


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
    """The report payload (`nfl_results_report_v1`); `engine_era_start` overrides the registered default.

    `bootstrap=True` (what the writer passes) adds the `bootstrap` method block and every scope slice's `uncertainty`.
    """

    if engine_era_start is not None and not is_calendar_date(engine_era_start):
        raise ValueError("engine_era_start must be a calendar date YYYY-MM-DD")
    era = metrics.engine_era_start if engine_era_start is None else engine_era_start
    counted, left_out = _all_sport(history, metrics)
    nfl = [row for row in counted if row.is_nfl]
    settings = bootstrap_settings(metrics) if bootstrap else None

    def measure(scope: str) -> Callable[[str, dict, Sequence[HistoryRow]], dict] | None:
        return None if settings is None else partial(_uncertainty, settings, scope)

    scopes = {"nfl": _scope(nfl, metrics, measure("nfl")),
              "engine_era": _scope(_era_rows(nfl, metrics, era), metrics, measure("engine_era"))}
    registered = nfl if metrics.trigger_scope == "nfl" else _era_rows(nfl, metrics, metrics.engine_era_start)
    extra = {} if settings is None else {"bootstrap": _method_block(metrics)}
    return {
        **extra,
        "schema_version": REPORT_VERSION,
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


def report_name(era: str) -> str:
    """The era names the file, so a report for another era is another file and never a conflict."""

    return f"results_report.era-{era}.{WRITER}.json"


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

    @property
    def exit_code(self) -> int:
        return 0 if self.status in ("COMPLETE", "ALREADY_PRESENT") else 2

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "exit_code": self.exit_code,
            "problems": list(self.problems),
            "contract": REPORT_VERSION,
            "source_sha256": self.source_sha256,
            "engine_era_start": self.engine_era_start,
            "files": self.files,
            "headline": self.headline,
            "does_not_establish": list(self.does_not_establish),
        }


def headline(payload: Mapping[str, object]) -> dict[str, object]:
    """What stdout carries: counts, place-based rates, the within-slate test and the trigger; no fee or winnings."""

    def scope(block: Mapping[str, object]) -> dict[str, object]:
        blanks: Counter[str] = Counter()
        for row in block["by_slate"]:
            blanks[row["date"]] += row["blanks"]
        test = block["within_slate_test"]
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
    """The snapshot's bytes, or why they are not the bytes its name promises: never followed through a symlink."""

    if path.is_symlink():
        return None, "symlink"
    if not path.exists():
        return None, "absent"
    try:
        with path.open("rb") as handle:
            raw = handle.read(entry_history.MAX_BYTES + 1)
    except OSError:  # a directory at the name, a lock, a permission
        return None, "unreadable"
    # No intake writes a file past the cap, and its first MAX_BYTES + 1 bytes cannot hash to the name.
    if len(raw) > entry_history.MAX_BYTES or sha256_bytes(raw) != sha256:
        return None, "hash"
    return raw, None


def run_results_report(source_sha256: str, results_root: str | Path, engine_era_start: str | None = None, *,
                       metrics: ResultsMetrics | None = None) -> ReportOutcome:
    """Read one snapshot, build the report and write it once: `<root>/reports/<sha256>/results_report.era-<date>.w1.json`.

    The registered metrics load first, from the module's path at call time: a defect there is `ResultsMetricsError`, a
    fault in a tracked file and never a refusal. A refused input writes nothing. The trigger reads the registered era
    whatever `engine_era_start` names.
    """

    metrics = load_results_metrics(DEFAULT_METRICS_PATH) if metrics is None else metrics
    files: dict[str, dict[str, str | None]] = {"report": {"path": None, "state": "NOT_ATTEMPTED", "sha256": None}}
    refused = partial(ReportOutcome, "REFUSED", files=files, does_not_establish=metrics.does_not_establish)
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
                   source_sha256=source_sha256, engine_era_start=era, headline=headline(payload))
    writes = (("report", root / "reports" / source_sha256 / report_name(era["date"]), canonical_bytes(payload)),)
    for name, path, data in writes:
        files[name]["path"] = str(path)
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
    "DEFAULT_METRICS_PATH",
    "METRICS_VERSION",
    "REPORT_CODES",
    "REPORT_VERSION",
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
    "report_name",
    "resample",
    "run_results_report",
    "t_quantile",
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
