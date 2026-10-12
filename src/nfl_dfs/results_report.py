"""The NFL results report (Session 71, `nfl_results_metrics_v1`, `nfl_results_report_v1`).

Realized results of past entries, read from the hash-named entry-history snapshot (`nfl_dk_entry_history_v1`). This
module owns the entry-level definitions every later grader imports (Session 18's `standings_metrics.py` among them):
the finishing percentile `Place / Contest_Entries` and its random expectation `(n+1)/2n`, the top-10% and bottom-10%
finishes and theirs, and blanks (`Points` exactly zero). DraftKings gives a tie group its best place, so the percentile
flatters where ties are common; the random expectation assumes no ties, and `Place` is read as given.

The registered metrics file (`config/results_metrics_v1.json`) names the populations, the rules, the bands, the slate
and the within-slate test; the loader refuses any file whose declared rules are not the ones this module implements.
Its bootstrap section is registered ahead of the intervals and the minimum detectable effect (Session 71b); nothing
here reads it yet. Every figure is exact rational arithmetic rounded once, so the same rows give the same text.
Payout shape and field size come from the numeric columns only, never from a contest name, and nothing here reaches a
run, a frozen package, a selection or a release truth.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date
from fractions import Fraction
from pathlib import Path
from typing import Callable, Mapping, Sequence

from .contest_facts import LABEL, THRESHOLD, first_place_label
from .entry_history import CONTRACT_VERSION as HISTORY_CONTRACT
from .entry_history import EntryHistory, HistoryRow
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
# The values a row must hold to be counted; an NFL row always holds them (the parser refuses the file otherwise).
REQUIRED = ("contest_start", "place", "points_hundredths", "winnings_non_ticket_cents", "winnings_ticket_cents",
            "contest_entries", "entry_fee_cents", "prize_pool_cents", "places_paid")

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


def parse_results_metrics(raw: bytes) -> ResultsMetrics:
    """The registered metrics, or `ResultsMetricsError` naming the first fault."""

    try:
        document = json.loads(raw.decode("utf-8"))
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
            describe: Callable[[tuple, list[HistoryRow]], dict]) -> list[dict]:
    groups: dict[tuple, list[HistoryRow]] = {}
    for row in rows:
        groups.setdefault(key(row), []).append(row)
    return [{**describe(found, groups[found]), **_slice(groups[found])} for found in sorted(groups)]


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


def _scope(rows: Sequence[HistoryRow], metrics: ResultsMetrics) -> dict[str, object]:
    shapes = _shape_labels(metrics.paid_fraction_edges)
    sizes = _labels(metrics.field_size_upper, str)
    fees = _labels(metrics.entry_fee_upper_cents, _cents_text)
    return {
        "slates": len({slate_key(row) for row in rows}),
        "fine_slates": len({fine_slate_key(row) for row in rows}),
        "overall": _slice(rows),
        "by_format": _rollup(rows, lambda row: (row.game_type,), lambda key, _: {"game_type": key[0]}),
        "by_payout_shape": _rollup(
            rows, lambda row: (_shape_band(row, metrics.paid_fraction_edges),),
            lambda key, _: {"band": shapes[key[0]], "first_place_label": LABEL if key[0] == 0 else None}),
        "by_field_size": _rollup(rows, lambda row: (_band(row.contest_entries, metrics.field_size_upper),),
                                 lambda key, _: {"band": sizes[key[0]]}),
        "by_entry_fee": _rollup(rows, lambda row: (_band(row.entry_fee_cents, metrics.entry_fee_upper_cents),),
                                lambda key, _: {"band": fees[key[0]]}),
        "by_month": _rollup(rows, lambda row: (str(row.contest_start)[:7],), lambda key, _: {"month": key[0]}),
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
        "slates_after_registration": sum(key[1] > registered_on for key, *_ in slates),
        "slates": [
            {"sport": key[0], "date": key[1], "game_type": key[2], "top_heavy_entries": top,
             "flatter_entries": flat, "difference_points": _mean_percent([difference])}
            for key, top, flat, difference in slates
        ],
    }


def _trigger(test: Mapping[str, object], metrics: ResultsMetrics) -> dict[str, object]:
    one_sided, _ = sign_test(int(test["worse"]), int(test["better"]))
    slates = int(test["worse"]) + int(test["better"])
    return {
        "scope": metrics.trigger_scope,
        "registered_on": metrics.registered_on,
        "alpha": str(metrics.trigger_alpha),
        "min_slates": metrics.trigger_min_slates,
        "slates": slates,
        "p_one_sided": test["p_one_sided"],
        "met": one_sided < metrics.trigger_alpha and slates >= metrics.trigger_min_slates,
        "when_met": ("open a roadmap row for the per-contest term inside Session 50's placement objective; this "
                     "report states the trigger and acts on nothing"),
    }


def _complete(row: HistoryRow) -> bool:
    return all(getattr(row, name) is not None for name in REQUIRED)


def _all_sport(history: EntryHistory, metrics: ResultsMetrics) -> tuple[list[HistoryRow], Counter[str]]:
    """Every sport's paid entries outside the excluded game types; a row with an unparsed value is left out."""

    counted: list[HistoryRow] = []
    left_out: Counter[str] = Counter()
    for row in history.rows:
        if row.game_type in metrics.excluded_game_types or row.entry_fee_cents == 0:
            continue
        if _complete(row):
            counted.append(row)
        else:
            left_out[row.sport] += 1
    return counted, left_out


def build_report(history: EntryHistory, *, metrics: ResultsMetrics, source_sha256: str, source_bytes: int,
                 engine_era_start: str | None = None) -> dict[str, object]:
    """The report payload (`nfl_results_report_v1`); `engine_era_start` overrides the registered default."""

    if engine_era_start is not None and not is_calendar_date(engine_era_start):
        raise ValueError("engine_era_start must be a calendar date YYYY-MM-DD")
    era = metrics.engine_era_start if engine_era_start is None else engine_era_start
    counted, left_out = _all_sport(history, metrics)
    nfl = [row for row in counted if row.is_nfl]
    engine_era = [row for row in nfl
                  if row.game_type in metrics.engine_game_types and str(row.contest_start)[:10] >= era]
    scopes = {"nfl": _scope(nfl, metrics), "engine_era": _scope(engine_era, metrics)}
    return {
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
        "within_slate_trigger": _trigger(scopes[metrics.trigger_scope]["within_slate_test"], metrics),
        "all_sport_check": {"entries": len(counted), "left_out_unreadable": dict(sorted(left_out.items())),
                            "overall": _slice(counted)},
        "notes": [
            {"kind": "PLACES_PAID_ABOVE_CONTEST_ENTRIES_CAPPED", "row": row.row, "entry_key": row.entry_key,
             "contest_key": row.contest_key}
            for row in nfl if row.places_paid_above_entries
        ],
        "parser_note_counts": dict(sorted(Counter(note["kind"] for note in history.notes).items())),
        "does_not_establish": list(metrics.does_not_establish),
    }


__all__ = [
    "BOTTOM_STRICT",
    "DEFAULT_METRICS_PATH",
    "METRICS_VERSION",
    "REPORT_VERSION",
    "ResultsMetrics",
    "ResultsMetricsError",
    "build_report",
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
