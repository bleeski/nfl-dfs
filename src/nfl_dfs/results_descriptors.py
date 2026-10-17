"""The descriptor comparison (Session 73b, `nfl_results_descriptors_v1`): bust attribution, descriptive only.

Each slate's `entry_results.w1.json` (Session 73) is joined to its build record on Entry ID, and the bottom-10% entries
are set against the top-10% entries on what the record says the engine chose (salary left, stack size, the team split,
kickers, Q flags, later-window people, the structure counts), with the finish percentile read against each as a
continuous outcome. A contest's own place and field size decide each entry's group (`results_report.in_top`,
`in_bottom`), so a contest too small to hold a top-10% finish (under ten entries) contributes bottoms only.

The fixed effect is the contest and the cluster is the slate. Ben's entries sit in four to twelve contests a slate, of
one, two, seven or twenty of his entries, and the contest a lineup went to follows its Captain, stack and thesis, so a
slate-level contrast would compare lineups placed in small contests with lineups that topped the large one. Within a
contest `c`, with `n_t` top and `n_b` bottom entries, a contest weighs `n_t n_b / (n_t + n_b)`; a contest missing a
group weighs nothing. Both statistics are exact ratios of slate sums, `sum(Y_g) / sum(X_g)` over `Fraction`s, so
`results_report`'s own CR1 standard error and bootstrap-t (Webb wild under 30 slates, pairs from 30) read them
unchanged.

Only the four registered primary descriptors get an interval. The rest carry an estimate and a standard error, and the
report states how many intervals it shows and that none is adjusted for the others. Captain position (Showdown) is a
table, not a test: the position comes from the salary file whose SHA-256 the record binds, by exact DraftKings ID.

It reads each slate's results file and record, and a salary file for the Captain table; it writes one report under the
gitignored results root and nothing else. It reaches no run, selection, policy or release truth, and the report says
what it does not establish.
"""

from __future__ import annotations

import json
import random
import re
from collections import Counter
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Callable, Mapping, Sequence

from . import entry_history
from . import results_join as rj
from . import results_report as rr
from .contest_facts import canonical_bytes
from .dk import parse_salaries
from .entry_history import _problem
from .hashing import sha256_bytes

CONTRACT_VERSION = "nfl_results_descriptors_v1"
# A fix that changes a written byte takes a new writer version, so a report already on disk is never contradicted.
WRITER = "w1"
POPULATION = "ALL_JOINED"
DEFAULT_SLATES_DIR = rj.DEFAULT_SLATES_DIR
STATISTICS = ("top_minus_bottom", "percentile_slope")
# Why a slate, or a Captain, was left out: data, not gate codes (the registry scan reads code-shaped names it can reach).
GAPS = ("NO_RESULTS_FILE", "RESULTS_DO_NOT_MATCH_RECORD", "SALARY_FILE_NOT_FOUND", "SALARY_FILE_UNREADABLE",
        "CAPTAIN_NOT_IN_SALARY_FILE", "NO_CAPTAIN_IN_RECORD")
SECONDARY = "SECONDARY_DESCRIPTOR"
# The codes this module names; each is emitted as a full literal below (the gate registry scan reads them).
DESCRIPTOR_CODES = (
    "RESULTS_DESCRIPTORS_INPUT_INVALID",
    "RESULTS_DESCRIPTORS_RECORD_INVALID",
    "RESULTS_DESCRIPTORS_RESULTS_INVALID",
    "RESULTS_DESCRIPTORS_ARTIFACT_CONFLICT",
    "RESULTS_DESCRIPTORS_WRITE_FAILED",
)
DOES_NOT_ESTABLISH = (*rj.DOES_NOT_ESTABLISH, "CAUSE_OF_A_BUST")
ARTIFACT_RECOVERY = (
    "Another file holds this report's name, and the name binds every input byte and the metrics file, so the same name"
    " with other bytes is a hand-edited or damaged copy. It is never overwritten: delete it by hand if it is, and rerun."
)
_SHA256 = re.compile(r"[0-9a-f]{64}")
_RESULTS_KEYS = frozenset({"schema_version", "writer", "contract", "source_sha256", "slate", "record_name", "entries",
                           "does_not_establish"})
_ENTRY_KEYS = frozenset({"entry_id", "class", "place", "contest_entries", "points_hundredths", "percentile"})
_BOUND = ("JOINED", "LOCKED_BLANK_WITH_FILE")


class ResultsDescriptorsRefused(ValueError):
    """An input was refused whole, by a code in the registry's `results_descriptors` family."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}:{detail}")
        self.code, self.detail = code, detail


# ------------------------------------------------------------------------------------------ descriptors


def _count(value: object) -> Fraction | None:
    return Fraction(value) if isinstance(value, int) and not isinstance(value, bool) else None


def _section(row: Mapping, section: str, key: str) -> object:
    found = row.get(section)
    return found.get(key) if isinstance(found, dict) else None


def _structure(key: str) -> Callable[[Mapping], Fraction | None]:
    return lambda row: _count(_section(row, "structure", key))


def _salary_left(row: Mapping) -> Fraction | None:
    left = _count(row.get("salary_left"))
    return left / 100 if left is not None else None


def _stack_size(row: Mapping) -> Fraction | None:
    """The most pass catchers beside any rostered quarterback; null, never 0, when the row has no quarterback."""

    quarterbacks = _section(row, "structure", "qb_count")
    catchers = _section(row, "structure", "pass_catchers_with_rostered_qb")
    if isinstance(quarterbacks, int) and quarterbacks >= 1 and isinstance(catchers, list) and catchers:
        return Fraction(max(catchers))
    return None


def _split(row: Mapping) -> dict | None:
    found = _section(row, "structure", "team_split")
    return found if isinstance(found, dict) and found else None


def _largest_team(row: Mapping) -> Fraction | None:
    found = _split(row)
    return Fraction(max(found.values())) if found else None


def _team_count(row: Mapping) -> Fraction | None:
    """Classic only: a Showdown lineup always holds two teams."""

    found = _split(row)
    return Fraction(len(found)) if found and row.get("mode") == "CLASSIC" else None


@dataclass(frozen=True)
class Descriptor:
    name: str
    unit: str
    primary: bool
    read: Callable[[Mapping], Fraction | None]


# The primary list is registered here and in the contract: it is chosen before any export is read, so no estimate picks it.
DESCRIPTORS = (
    Descriptor("salary_left", "USD_100", True, _salary_left),
    Descriptor("max_pass_catchers_with_qb", "COUNT", True, _stack_size),
    Descriptor("max_team_count", "COUNT", True, _largest_team),
    Descriptor("kicker_count", "COUNT", True, _structure("kicker_count")),
    Descriptor("q_count", "COUNT", False, lambda row: _count(_section(row, "dk_status", "q_count"))),
    Descriptor("later_window_count", "COUNT", False, lambda row: _count(row.get("later_window_count"))),
    Descriptor("qb_count", "COUNT", False, _structure("qb_count")),
    Descriptor("dst_count", "COUNT", False, _structure("dst_count")),
    Descriptor("offense_against_own_dst", "COUNT", False, _structure("offense_against_own_dst")),
    Descriptor("offense_facing_rostered_dst", "COUNT", False, _structure("offense_facing_rostered_dst")),
    Descriptor("bring_backs", "COUNT", False, _structure("bring_backs")),
    Descriptor("rb_with_own_dst", "COUNT", False, _structure("rb_with_own_dst")),
    Descriptor("team_count", "COUNT", False, _team_count),
)


def descriptor_values(row: Mapping) -> dict[str, Fraction | None]:
    """Every descriptor of one record row, exact; null where the record is null (an unfilled row is null throughout)."""

    return {item.name: item.read(row) for item in DESCRIPTORS}


# ------------------------------------------------------------------------------------------ the inputs


@dataclass(frozen=True)
class Row:
    entry_id: str
    contest: str
    place: int
    field: int
    group: str
    finish: Fraction
    values: Mapping[str, Fraction | None]
    captain: str | None


@dataclass(frozen=True)
class SlateData:
    slate: str
    mode: str
    record_sha256: str
    results_sha256: str | None
    gap: str | None
    salary_gap: str | None
    salary_token: str
    excluded: Mapping[str, int]
    rows: tuple[Row, ...]
    captain_gaps: Mapping[str, int]
    captain_positions: Mapping[str, str]


@dataclass(frozen=True)
class Inputs:
    slates: tuple[SlateData, ...]
    digest: str
    run_fields: Mapping[str, tuple[int, int]]


def _invalid_record(slate: str, line: int, field: str) -> ResultsDescriptorsRefused:
    return ResultsDescriptorsRefused("RESULTS_DESCRIPTORS_RECORD_INVALID",
                                     f"{slate}/construction/{rj.RECORD_NAME}:line={line}:{field}")


def _natural(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _check_record_row(slate: str, line: int, row: dict) -> None:
    """The fields this comparison reads, on top of the join's own checks. An unfilled row is null throughout."""

    def need(field: str, ok: bool) -> None:
        if not ok:
            raise _invalid_record(slate, line, field)

    hashes = row.get("hashes")
    need("hashes.salary_sha256", isinstance(hashes, dict) and isinstance(hashes.get("salary_sha256"), str)
         and bool(_SHA256.fullmatch(hashes["salary_sha256"])))
    need("run", isinstance(row.get("run"), dict))
    need("salary_left", row.get("salary_left") is None or _natural(row["salary_left"]))
    need("later_window_count", row.get("later_window_count") is None or _natural(row["later_window_count"]))
    need("captain_dk_id", row.get("captain_dk_id") is None or isinstance(row["captain_dk_id"], str))
    status = row.get("dk_status")
    need("dk_status", status is None or isinstance(status, dict))
    if status is not None:
        need("dk_status.q_count", _natural(status.get("q_count")))
    structure = row.get("structure")
    need("structure", structure is None or isinstance(structure, dict))
    if structure is None:
        return
    for key in ("qb_count", "kicker_count", "dst_count", "offense_against_own_dst", "offense_facing_rostered_dst"):
        need(f"structure.{key}", _natural(structure.get(key)))
    for key in ("bring_backs", "rb_with_own_dst"):
        need(f"structure.{key}", structure.get(key) is None or _natural(structure[key]))
    catchers = structure.get("pass_catchers_with_rostered_qb")
    need("structure.pass_catchers_with_rostered_qb", isinstance(catchers, list) and all(_natural(item) for item in catchers))
    split = structure.get("team_split")
    need("structure.team_split", isinstance(split, dict) and all(
        isinstance(team, str) and _natural(count) and count > 0 for team, count in split.items()))


def _invalid_results(slate: str, what: str) -> ResultsDescriptorsRefused:
    return ResultsDescriptorsRefused("RESULTS_DESCRIPTORS_RESULTS_INVALID", f"{slate}:{what}")


def _results_entries(slate: str, raw: bytes) -> list[dict]:
    """A results file's entries, or a refusal naming the first fault. Exactly the shape Session 73 writes."""

    try:
        payload = json.loads(raw, parse_constant=rj._no_constant)
    except ValueError:
        raise _invalid_results(slate, "unreadable") from None
    if not isinstance(payload, dict):
        raise _invalid_results(slate, "unreadable")
    if set(payload) != _RESULTS_KEYS:
        raise _invalid_results(slate, "keys")
    expected = (("schema_version", rj.RESULTS_VERSION), ("writer", rj.WRITER), ("contract", rj.CONTRACT_VERSION),
                ("record_name", rj.RECORD_NAME), ("slate", slate))
    for field, value in expected:
        if payload[field] != value:
            raise _invalid_results(slate, field)
    source = payload["source_sha256"]
    if not (isinstance(source, str) and _SHA256.fullmatch(source)):
        raise _invalid_results(slate, "source_sha256")
    named = payload["does_not_establish"]
    if not (isinstance(named, list) and all(isinstance(item, str) for item in named)):
        raise _invalid_results(slate, "does_not_establish")
    if not isinstance(payload["entries"], list):
        raise _invalid_results(slate, "entries")
    seen: set[str] = set()
    for index, entry in enumerate(payload["entries"]):
        if not (isinstance(entry, dict) and set(entry) == _ENTRY_KEYS):
            raise _invalid_results(slate, f"entries[{index}]:keys")
        entry_id = entry["entry_id"]
        if not (isinstance(entry_id, str) and rj._DIGITS.fullmatch(entry_id)):
            raise _invalid_results(slate, f"entries[{index}]:entry_id")
        where = f"entry_id={entry_id}"
        if entry_id in seen:
            raise _invalid_results(slate, f"{where}:entry_id_repeated")
        seen.add(entry_id)
        if entry["class"] not in rj.CLASSES:
            raise _invalid_results(slate, f"{where}:class")
        bound = entry["class"] in _BOUND
        place, field, points = entry["place"], entry["contest_entries"], entry["points_hundredths"]
        for name, value, low in (("place", place, 1), ("contest_entries", field, 1), ("points_hundredths", points, 0)):
            number = isinstance(value, int) and not isinstance(value, bool) and value >= low
            if (not number) if bound else (value is not None):
                raise _invalid_results(slate, f"{where}:{name}")
        if bound and place > field:
            raise _invalid_results(slate, f"{where}:place")
    return payload["entries"]


def _group(place: int, field: int) -> str:
    return "top" if rr.in_top(place, field) else "bottom" if rr.in_bottom(place, field) else "neither"


def _positions(folder: Path, salary_sha: str) -> tuple[dict[str, str] | None, str | None]:
    """Position by exact DraftKings ID from the salary file whose bytes hash to `salary_sha`, found under the folder."""

    for path in sorted(folder.rglob("*.csv")):
        try:
            if path.is_symlink() or not path.is_file() or sha256_bytes(path.read_bytes()) != salary_sha:
                continue
        except OSError:
            continue
        try:
            slate = parse_salaries(path)
        except (OSError, ValueError):
            return None, "SALARY_FILE_UNREADABLE"
        return {player.dk_id: player.position for player in slate.players}, None
    return None, "SALARY_FILE_NOT_FOUND"


def _slate_data(folder: Path, record: rj.SlateRecord) -> SlateData:
    rows = record.rows
    for line, row in enumerate(rows, start=1):
        _check_record_row(record.slate, line, row)
    modes = sorted({row["mode"] for row in rows})
    head = {"slate": record.slate, "mode": modes[0] if len(modes) == 1 else "MIXED", "record_sha256": record.sha256}
    empty: dict = {"results_sha256": None, "gap": None, "salary_gap": None, "salary_token": "-", "excluded": {},
                   "rows": (), "captain_gaps": {}, "captain_positions": {}}
    path = folder / "construction" / rj.RESULTS_NAME
    if path.is_symlink():
        raise _invalid_results(record.slate, "symlink")
    if not path.is_file():
        return SlateData(**head, **{**empty, "gap": "NO_RESULTS_FILE"})
    raw = path.read_bytes()
    entries = _results_entries(record.slate, raw)
    empty["results_sha256"] = sha256_bytes(raw)
    if [entry["entry_id"] for entry in entries] != [row["entry_id"] for row in rows]:
        return SlateData(**head, **{**empty, "gap": "RESULTS_DO_NOT_MATCH_RECORD"})
    kept: list[Row] = []
    excluded: Counter[str] = Counter()
    for row, entry in zip(rows, entries):
        if entry["class"] != "JOINED":
            excluded[entry["class"]] += 1
            continue
        place, field = entry["place"], entry["contest_entries"]
        captain = row.get("captain_dk_id") if row["mode"] == "SHOWDOWN" else None
        kept.append(Row(row["entry_id"], row["contest_id"], place, field, _group(place, field),
                        Fraction(100 * place, field), descriptor_values(row), captain))
    showdown = {row["entry_id"]: row["hashes"]["salary_sha256"] for row in rows if row["mode"] == "SHOWDOWN"}
    return SlateData(**head, **{**empty, "excluded": dict(sorted(excluded.items())), "rows": tuple(kept),
                                **_captains(folder, showdown, kept)})


def _captains(folder: Path, salary_sha: Mapping[str, str], kept: Sequence[Row]) -> dict:
    """Each kept Showdown row's Captain as a position, and a count of those the salary file cannot name."""

    wanted = [item for item in kept if item.entry_id in salary_sha]
    out: dict = {"salary_gap": None, "salary_token": "-", "captain_gaps": {}, "captain_positions": {}}
    if not wanted:
        return out
    found: dict[str, tuple[dict[str, str] | None, str | None]] = {}
    gaps: Counter[str] = Counter()
    for item in wanted:
        sha = salary_sha[item.entry_id]
        if sha not in found:
            found[sha] = _positions(folder, sha)
        positions, file_gap = found[sha]
        if item.captain is None:
            gaps["NO_CAPTAIN_IN_RECORD"] += 1
        elif positions is None:
            out["salary_gap"] = file_gap
            gaps[file_gap] += 1
        elif item.captain not in positions:
            gaps["CAPTAIN_NOT_IN_SALARY_FILE"] += 1
        else:
            out["captain_positions"][item.entry_id] = positions[item.captain]
    out["salary_token"] = ",".join(sorted(sha if positions is not None else file_gap
                                          for sha, (positions, file_gap) in found.items()))
    out["captain_gaps"] = dict(sorted(gaps.items()))
    return out


def load_inputs(slates_root: str | Path) -> Inputs:
    """Each slate's record and results file, joined on Entry ID. A malformed input is refused whole, by name."""

    root = Path(slates_root)
    try:
        records = rj.load_records(root)
    except rj.ResultsJoinRefused as refusal:  # the join's own loader checks the join fields, once
        raise ResultsDescriptorsRefused("RESULTS_DESCRIPTORS_RECORD_INVALID", refusal.detail) from None
    slates = tuple(_slate_data(root / record.slate, record) for record in records.slates)
    lines = "".join(f"{slate.slate}|record:{slate.record_sha256}|results:{slate.results_sha256 or '-'}"
                    f"|salary:{slate.salary_token}\n" for slate in slates)
    run_fields = {"thesis": [0, 0], "method": [0, 0], "final_rung": [0, 0]}
    for record in records.slates:
        for row in record.rows:
            run = row["run"]
            method = run.get("method")
            for name, present in (("thesis", run.get("thesis") is not None), ("method", method is not None),
                                  ("final_rung", isinstance(method, dict) and method.get("final_rung") is not None)):
                run_fields[name][0] += 1
                run_fields[name][1] += int(present)
    return Inputs(slates, sha256_bytes(lines.encode("utf-8")), {name: tuple(pair) for name, pair in run_fields.items()})


# --------------------------------------------------------------------------------------------- the statistics


def _contests(slate: SlateData) -> list[list[Row]]:
    found: dict[str, list[Row]] = {}
    for row in slate.rows:
        found.setdefault(row.contest, []).append(row)
    return [found[key] for key in sorted(found)]


def _clusters(slates: Sequence[SlateData], name: str, statistic: str) -> list[tuple[Fraction, Fraction]]:
    """`(Y_g, X_g)` per slate in name order, only where `X_g > 0`: the contest fixed effect, summed to the slate."""

    clusters = []
    for slate in slates:
        y = x = Fraction(0)
        for rows in _contests(slate):
            held = [(row, row.values[name]) for row in rows if row.values[name] is not None]
            if statistic == "top_minus_bottom":
                top = [value for row, value in held if row.group == "top"]
                bottom = [value for row, value in held if row.group == "bottom"]
                if top and bottom:
                    weight = Fraction(len(top) * len(bottom), len(top) + len(bottom))
                    y += weight * (sum(top) / len(top) - sum(bottom) / len(bottom))
                    x += weight
            elif len(held) >= 2:
                mean_d = sum(value for _, value in held) / len(held)
                mean_p = sum(row.finish for row, _ in held) / len(held)
                y += sum((value - mean_d) * (row.finish - mean_p) for row, value in held)
                x += sum((value - mean_d) ** 2 for _, value in held)
        if x > 0:
            clusters.append((y, x))
    return clusters


def _secondary(clusters: Sequence[tuple[Fraction, Fraction]]) -> dict[str, object]:
    """An estimate and a CR1 standard error from the shared function, with no resampling and no interval."""

    count = len(clusters)
    figures: dict[str, object] = {"slates": count, "estimate": None, "method": None, "interval": None,
                                  "standard_error": None, "mde": None, "reason": SECONDARY,
                                  "degenerate_resamples": 0}
    if count:
        exact = sum(y for y, _ in clusters) / sum(x for _, x in clusters)
        figures["estimate"] = rr._fixed(exact)
        residuals = [float(y - exact * x) for y, x in clusters]
        if count >= 2 and any(residuals):
            figures["standard_error"] = rr._percent(
                rr.cr1_standard_error(residuals, [float(x) for _, x in clusters]), 1)
    return figures


def _figures(slates: Sequence[SlateData], item: Descriptor, statistic: str,
             settings: rr.BootstrapSettings) -> dict[str, object]:
    clusters = _clusters(slates, item.name, statistic)
    if not item.primary:
        return _secondary(clusters)
    # Each figure draws from its own generator, seeded from its own name: no figure moves another's draws.
    key = json.dumps([settings.seed, "RESULTS_DESCRIPTORS", POPULATION, item.name, statistic], sort_keys=True)
    draw = random.Random(int(sha256_bytes(key.encode("utf-8")), 16)).random
    return rr._statistic(clusters, settings, draw, scale=1)


def _mean_text(values: Sequence[Fraction]) -> str:
    return rr._fixed(sum(values) / len(values))


def _positions_table(rows: Sequence[tuple[str, Row]]) -> dict[str, dict[str, object]]:
    by_position: dict[str, list[Row]] = {}
    for position, row in rows:
        by_position.setdefault(position, []).append(row)
    return {position: {"entries": len(found), "top": sum(row.group == "top" for row in found),
                       "bottom": sum(row.group == "bottom" for row in found),
                       "neither": sum(row.group == "neither" for row in found),
                       "mean_percentile": _mean_text([row.finish for row in found])}
            for position, found in sorted(by_position.items())}


def _captain_table(slates: Sequence[SlateData]) -> dict[str, object]:
    per_slate: dict[str, dict[str, object]] = {}
    pooled: list[tuple[str, Row]] = []
    unresolved: Counter[str] = Counter()
    for slate in slates:
        if slate.mode == "CLASSIC" or slate.gap is not None:
            continue
        found = [(slate.captain_positions[row.entry_id], row) for row in slate.rows
                 if row.entry_id in slate.captain_positions]
        if not found and not slate.captain_gaps:
            continue
        per_slate[slate.slate] = {"gap": slate.salary_gap, "positions": _positions_table(found)}
        pooled += found
        unresolved.update(slate.captain_gaps)
    return {"slates": per_slate, "pooled": {"positions": _positions_table(pooled)},
            "unresolved": dict(sorted(unresolved.items()))}


def _sample(slates: Sequence[SlateData]) -> dict[str, object]:
    used = [slate for slate in slates if slate.rows]
    rows = [row for slate in used for row in slate.rows]
    contests = {(slate.slate, row.contest): [] for slate in used for row in slate.rows}
    for slate in used:
        for row in slate.rows:
            contests[(slate.slate, row.contest)].append(row.group)
    by_mode: dict[str, dict[str, int]] = {}
    for slate in used:
        found = by_mode.setdefault(slate.mode, {"slates": 0, "joined_entries": 0})
        found["slates"] += 1
        found["joined_entries"] += len(slate.rows)
    excluded: Counter[str] = Counter()
    for slate in slates:
        excluded.update(slate.excluded)
    groups = Counter(row.group for row in rows)
    return {"slates": len(used), "joined_entries": len(rows), "contests": len(contests),
            "contests_with_both_groups": sum({"top", "bottom"} <= set(found) for found in contests.values()),
            "top": groups["top"], "bottom": groups["bottom"], "neither": groups["neither"],
            "excluded": dict(sorted(excluded.items())), "by_mode": dict(sorted(by_mode.items())),
            "slates_not_compared": [slate.slate for slate in slates if slate.gap is not None]}


def build_report(inputs: Inputs, metrics: rr.ResultsMetrics, *,
                 settings: rr.BootstrapSettings | None = None) -> dict[str, object]:
    """The report payload. `settings` overrides the registered bootstrap (a test shortens the resamples)."""

    settings = settings or rr.bootstrap_settings(metrics)
    slates = inputs.slates
    primary = [item for item in DESCRIPTORS if item.primary]
    return {
        "schema_version": CONTRACT_VERSION, "writer": WRITER, "population": POPULATION,
        "metrics_version": metrics.version, "metrics_sha256": metrics.sha256, "inputs_digest": inputs.digest,
        "bootstrap": {"seed": settings.seed, "resamples": settings.resamples, "level": str(settings.level),
                      "pairs_min_slates": settings.pairs_min_slates,
                      "interval_min_slates": settings.interval_min_slates},
        "reading": {
            "rows": "JOINED_ONLY_BLANKS_REMOVED_BY_CONSTRUCTION", "fixed_effect": "CONTEST", "cluster": "SLATE",
            "top": "PLACE_TIMES_10_AT_MOST_N", "bottom": "PLACE_TIMES_10_ABOVE_9N",
            "top_minus_bottom": "POSITIVE_MEANS_TOP_ENTRIES_CARRY_MORE",
            "percentile_slope": "NEGATIVE_MEANS_MORE_GOES_WITH_A_BETTER_FINISH"},
        "limits": {
            "resamples": settings.resamples, "interval_min_slates": settings.interval_min_slates,
            "webb_distinct_weight_vectors_at_the_minimum": 6 ** settings.interval_min_slates,
            "few_clusters": ("WEBB_DRAWS_FEWER_THAN_RESAMPLES_AT_THE_MINIMUM"
                             if 6 ** settings.interval_min_slates < settings.resamples else None)},
        "family": {"descriptors": len(DESCRIPTORS), "intervals": 2 * len(primary), "adjustment": "NONE"},
        "slates": [{"slate": slate.slate, "mode": slate.mode, "record_sha256": slate.record_sha256,
                    "results_sha256": slate.results_sha256, "gap": slate.gap, "joined": len(slate.rows),
                    "excluded": dict(slate.excluded)} for slate in slates],
        "sample": _sample(slates),
        "run_fields": {name: {"rows": rows, "rows_with_value": with_value}
                       for name, (rows, with_value) in sorted(inputs.run_fields.items())},
        "descriptors": [{"name": item.name, "unit": item.unit, "primary": item.primary,
                         **{statistic: _figures(slates, item, statistic, settings) for statistic in STATISTICS}}
                        for item in DESCRIPTORS],
        "captain_table": _captain_table(slates),
        "does_not_establish": list(DOES_NOT_ESTABLISH),
    }


def report_name(inputs: Inputs, metrics: rr.ResultsMetrics) -> str:
    """One name binds every input byte, the metrics file and the writer, so a changed byte is a new report."""

    key = f"{inputs.digest}:{metrics.sha256}:{CONTRACT_VERSION}:{WRITER}"
    return f"results_descriptors.{sha256_bytes(key.encode('utf-8'))[:16]}.{WRITER}.json"


def headline(report: Mapping[str, object]) -> dict[str, object]:
    """What stdout carries: counts, the primary figures and the named gaps. No money is in any input."""

    keep = ("slates", "estimate", "standard_error", "interval", "reason")
    return {
        "sample": report["sample"],
        "slates": [{key: item[key] for key in ("slate", "gap", "joined")} for item in report["slates"]],
        "primary": {item["name"]: {statistic: {key: item[statistic][key] for key in keep} for statistic in STATISTICS}
                    for item in report["descriptors"] if item["primary"]},
        "family": report["family"],
        "captain_unresolved": report["captain_table"]["unresolved"],
    }


# ----------------------------------------------------------------------------------------------- writing


@dataclass(frozen=True)
class DescriptorOutcome:
    """`COMPLETE` and `ALREADY_PRESENT` exit 0; `REFUSED` and `WRITE_FAILED` exit 2."""

    status: str
    problems: tuple[str, ...]
    file: dict
    headline: dict | None = None

    @property
    def exit_code(self) -> int:
        return 0 if self.status in ("COMPLETE", "ALREADY_PRESENT") else 2

    def as_dict(self) -> dict[str, object]:
        return {"status": self.status, "exit_code": self.exit_code, "problems": list(self.problems),
                "contract": CONTRACT_VERSION, "file": self.file, "headline": self.headline,
                "does_not_establish": list(DOES_NOT_ESTABLISH)}


def run_results_descriptors(results_root: str | Path,
                            slates_root: str | Path = DEFAULT_SLATES_DIR) -> DescriptorOutcome:
    """Read every slate's record and results file, compare, and write the report once. A refused input writes nothing."""

    file: dict = {"path": None, "state": "NOT_ATTEMPTED", "sha256": None}
    slates = Path(slates_root)
    if not slates.is_dir():
        return DescriptorOutcome("REFUSED", (_problem("RESULTS_DESCRIPTORS_INPUT_INVALID", "field=slates_root"),), file)
    try:
        inputs = load_inputs(slates)
    except ResultsDescriptorsRefused as refusal:
        return DescriptorOutcome("REFUSED", (str(refusal),), file)
    metrics = rr.load_results_metrics(rr.registered_metrics_path(rr.CURRENT_METRICS_VERSION))
    report = build_report(inputs, metrics)
    data = canonical_bytes(report)
    path = Path(results_root) / "reports" / "descriptors" / report_name(inputs, metrics)
    file["path"] = str(path)
    problems: list[str] = []
    try:
        file["state"] = entry_history._write_once(
            path, data, code="RESULTS_DESCRIPTORS_ARTIFACT_CONFLICT", recovery=ARTIFACT_RECOVERY)
        file["sha256"] = sha256_bytes(data)
    except entry_history._Stop:
        file.update(state="REFUSED", recovery=ARTIFACT_RECOVERY)
        problems.append(_problem("RESULTS_DESCRIPTORS_ARTIFACT_CONFLICT", "file=report"))
    except OSError as exc:
        file["state"] = "WRITE_FAILED"
        problems.append(_problem("RESULTS_DESCRIPTORS_WRITE_FAILED", f"file=report:exception={type(exc).__name__}"))
    status = {"WRITTEN": "COMPLETE", "ALREADY_PRESENT": "ALREADY_PRESENT"}.get(file["state"], file["state"])
    return DescriptorOutcome(status, tuple(problems), file, headline(report))


__all__ = [
    "ARTIFACT_RECOVERY",
    "CONTRACT_VERSION",
    "DESCRIPTORS",
    "DESCRIPTOR_CODES",
    "DOES_NOT_ESTABLISH",
    "DescriptorOutcome",
    "GAPS",
    "POPULATION",
    "ResultsDescriptorsRefused",
    "STATISTICS",
    "WRITER",
    "build_report",
    "descriptor_values",
    "headline",
    "load_inputs",
    "report_name",
    "run_results_descriptors",
]
