"""Realized player points and player-level grading of the prior (Session 70, `nfl_player_grading_v1`).

A grading input only. Realized points come from the nflverse weekly player file, fetched once through the
priors adapter's own `player_stats_current` source entry into a hash-checked package, and scored with this
engine's `scoring.py`. They never become a prior, a candidate, a selection or a gate input, and nothing here
touches a run, a frozen package or a release truth. People join through the salary's `underlying_id` and the
run's reviewed identity file, by exact DraftKings ID only; a person or a stat the source does not carry is a
named gap, never a zero. The reconciliation checks the delivered lineups against DraftKings' own lineup points
from the entry-history artifact (`nfl_dk_entry_history_entries_v1`).
"""

from __future__ import annotations

import contextlib
import csv
import dataclasses
import io
import json
import math
from collections import Counter
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
from typing import Mapping, Sequence

from . import priors
from .dk import parse_entries, parse_salaries
from .entry_history import ENTRIES_VERSION
from .hashing import sha256_bytes, sha256_file
from .lineups import prefilled_cell_id
from .participation import AVAILABLE_STATUSES, DEGRADED_STATUSES, UNAVAILABLE_STATUSES
from .scoring import KickerStatLine, OffensiveStatLine, score_kicker, score_offense

SCHEMA_VERSION = "nfl_player_grading_v1"
REALIZED_VERSION = "nfl_realized_dk_points_v1"
SALARY_BASELINE_VERSION = "salary_scaled_points_v1"
POOL_SCORES_SCHEMA = "nfl_prior_pool_scores_v1"
REPORT_NAME = "player_grading.w1.json"
STATS_SOURCE = "player_stats_current"
TOLERANCE_HUNDREDTHS = 1
RESIDUAL_AGREEMENT_HUNDREDTHS = 2
CODES = (
    "PLAYER_GRADING_STATS_UNAVAILABLE",
    "PLAYER_GRADING_STATS_INVALID",
    "PLAYER_GRADING_WEEK_ABSENT",
    "PLAYER_GRADING_GAME_UNBOUND",
    "PLAYER_GRADING_INPUT_INVALID",
    "PLAYER_GRADING_OUTPUT_EXISTS",
)
IDENTITY_COLUMNS = ("player_id", "season", "week", "season_type", "game_id")
# Each scoring.py field and the nflverse columns that sum to it (`nfl_realized_dk_points_v1`).
OFFENSE_MAP = {
    "passing_yards": ("passing_yards",),
    "passing_tds": ("passing_tds",),
    "interceptions": ("passing_interceptions",),
    "rushing_yards": ("rushing_yards",),
    "rushing_tds": ("rushing_tds",),
    "receiving_yards": ("receiving_yards",),
    "receiving_tds": ("receiving_tds",),
    "receptions": ("receptions",),
    "return_tds": ("special_teams_tds",),
    "fumbles_lost": ("fumbles_lost_total",),
    "two_point_conversions": ("passing_2pt_conversions", "rushing_2pt_conversions", "receiving_2pt_conversions"),
    "offensive_fumble_recovery_tds": ("fumble_recovery_tds",),
}
KICKER_MAP = {
    "extra_points": ("pat_made",),
    "field_goals_0_39": ("fg_made_0_19", "fg_made_20_29", "fg_made_30_39"),
    "field_goals_40_49": ("fg_made_40_49",),
    "field_goals_50_plus": ("fg_made_50_59", "fg_made_60_"),
}
FUMBLE_PARTS = ("sack_fumbles_lost", "rushing_fumbles_lost", "receiving_fumbles_lost")
YARD_FIELDS = frozenset({"passing_yards", "rushing_yards", "receiving_yards"})
CHECKED_COLUMNS = tuple(sorted({c for cols in (*OFFENSE_MAP.values(), *KICKER_MAP.values()) for c in cols}
                               | set(FUMBLE_PARTS)))
MAE_DEPARTURES = (
    "the prior is an expected-points figure, not the registered pre-lock median",
    "realized points are nflverse stat lines scored by scoring.py, not settled DraftKings points",
    "people with a gap are left out, not scored 0",
    "no slate-cluster bootstrap interval",
)
DOES_NOT_ESTABLISH = (
    "Realized points are nflverse stat lines scored by this engine's scoring.py; the reconciliation is the check "
    "against DraftKings' own lineup points.",
    "player_points_mae here is a variant of the registered Q1 metric (see departures): a player who did not play has "
    "no stat row and is left out of the figure, not counted as an error.",
    "Salary-scaled points are salary scaled to the prior's own total over the same people: a consensus-price "
    "baseline for who gets the points, not a projection.",
    "One slate is one sample. No figure here measures calibration, expected value, return or edge, and nothing here "
    "changes a prior, a selection or a release truth.",
    "The tables by position and by within-slate salary tier are cuts of the same usable people, never crossed; a cell "
    "under 3 people is null, and the salary side keeps the slate's one scale.",
    "Play rate counts a stat row as played: an undercount, and not the registered participation_brier event.",
)
TIER_NAMES = ("low", "mid", "high")
TIER_RULE = ("graded non-DST people by salary ascending; tied salaries share their mid-rank r of n; tier "
             "floor(3 (r - 0.5) / n), at most 2, so a tied salary never splits across tiers")
MIN_CELL_PEOPLE = 3
PLAY_RATE_POPULATION = "every identity-bound non-DST salary person, graded or not"
PLAYED_MEANS = ("a stat row in the nflverse weekly file that week: an undercount (a player on the field with no "
                "counting stat has no row), and not the registered participation_brier event")
POOL_SCHEMA_VERSION = "nfl_player_grading_pool_v1"
MEASURES = ("player_points_mae", "spearman")
SIDES = ("prior", "salary")
REGISTERED_MINIMUM_SAMPLE = 500  # player_points_mae's minimum_sample in config/metric_registry_q1_v1.json
POOL_DOES_NOT_ESTABLISH = (
    "Each figure is the unweighted mean over the slates that have it: the slate is the unit, whatever its people, so "
    "Kish ESS at equal weights is the slate count.",
    "Slates that share an nflverse game count its player-weeks twice; independent_slates counts each group of slates "
    "linked by shared games once.",
    "Across prior versions the pool grades the priors as delivered, not one model version.",
    "No bootstrap interval is computed, and below the registered minimum sample no figure here is a promotion, demotion "
    "or rollback measure. No figure measures calibration, expected value, return or edge.",
)
NOT_COMPUTED = {
    "participation_brier": "NOT_COMPUTABLE: the engine states no pre-lock playing probability (participation.py).",
    "bootstrap_interval": "NOT_COMPUTED: the registered interval resamples slates and needs 500 player-weeks; one "
                          "slate is one cluster.",
}
POOL_NOT_COMPUTED = {
    "bootstrap_interval": "NOT_COMPUTED: the registered 95% slate-cluster bootstrap interval with 10000 deterministic "
                          "resamples (player_points_mae, config/metric_registry_q1_v1.json)",
    "participation_brier": NOT_COMPUTED["participation_brier"],
}


class PlayerGradingRefused(Exception):
    """A named refusal: the grading report is not written."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}:{detail}")
        self.code = code
        self.detail = detail


# ----------------------------------------------------------------- the stats package


def _stats_spec(season: int) -> priors.NflverseSource:
    spec = next(s for s in priors.source_specifications(season=season, prior_season=season - 1)
                if s.name == STATS_SOURCE)
    # Optional for the priors build (week 1 has no file); here a missing file is a refusal, never an empty grade.
    return dataclasses.replace(spec, optional=False)


def load_or_fetch_stats(package: Path, season: int) -> tuple[bytes, dict]:
    """The season's weekly file from `package`, fetched into it once through `priors.freeze_sources`."""

    package = Path(package).resolve()
    spec = _stats_spec(season)
    manifest = package / priors.MANIFEST_FILENAME
    if not manifest.exists():
        try:
            frozen = priors.freeze_sources([spec], package_root=package, as_of=datetime.now(timezone.utc))
        except priors.PriorsBuildError as exc:
            raise PlayerGradingRefused("PLAYER_GRADING_STATS_INVALID", f"{spec.url}:{exc}") from exc
        except Exception as exc:  # transport, policy or deadline: the file was not obtained
            raise PlayerGradingRefused("PLAYER_GRADING_STATS_UNAVAILABLE", f"{spec.url}:{type(exc).__name__}:{exc}") from exc
        entry = frozen[spec.name].manifest_entry(package_root=package)
        manifest.write_bytes(priors.canonical_json_bytes(
            {"schema_version": priors.MANIFEST_SCHEMA, "artifacts": [entry]}))
    try:
        artifact = priors.load_frozen_manifest(package).get(spec.name)
    except priors.PriorsBuildError as exc:
        raise PlayerGradingRefused("PLAYER_GRADING_STATS_INVALID", f"{package}:{exc}") from exc
    if artifact is None or artifact.source_uri != spec.url:
        raise PlayerGradingRefused("PLAYER_GRADING_STATS_INVALID", f"{package}:holds no {spec.url}")
    try:
        raw = artifact.path.read_bytes()
    except OSError as exc:
        raise PlayerGradingRefused("PLAYER_GRADING_STATS_INVALID", f"{artifact.path}:{type(exc).__name__}") from exc
    if sha256_bytes(raw) != artifact.sha256:
        raise PlayerGradingRefused("PLAYER_GRADING_STATS_INVALID", f"{artifact.path}:changed after the check")
    return raw, artifact.manifest_entry(package_root=package)


# ----------------------------------------------------------------- stat rows and realized points


def _number(text: str | None, column: str) -> float | None:
    """A cell's value; None for blank or `NA`. Anything else that is not a finite number raises ValueError."""

    value = (text or "").strip()
    if value in ("", "NA"):
        return None
    number = float(value)
    if not math.isfinite(number) or (column not in YARD_FIELDS and not number.is_integer()):
        raise ValueError(value)
    return number


def parse_week(raw: bytes, season: int, week: int) -> tuple[frozenset[str], dict[str, dict[str, str]], int]:
    """The file's columns, its regular-season rows for one week by nflverse `player_id`, and the unattributed count.

    nflverse writes one row a week with a blank `player_id` (plays credited to no player). Nothing can join to it, so
    it is counted and skipped; a repeated `player_id` still refuses.
    """

    try:
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""))
        header = tuple(reader.fieldnames or ())
        records = list(reader)
    except (UnicodeDecodeError, csv.Error) as exc:
        raise PlayerGradingRefused("PLAYER_GRADING_STATS_INVALID", f"UNREADABLE:{exc}") from exc
    missing = [column for column in IDENTITY_COLUMNS if column not in header]
    if missing:
        raise PlayerGradingRefused("PLAYER_GRADING_STATS_INVALID", f"COLUMNS_MISSING:{missing}")
    checked = [column for column in CHECKED_COLUMNS if column in header]
    rows: dict[str, dict[str, str]] = {}
    unattributed = 0
    for number, row in enumerate(records, start=2):
        if None in row or None in row.values():
            raise PlayerGradingRefused("PLAYER_GRADING_STATS_INVALID", f"ROW_MISSHAPEN:row={number}")
        if (row["season"].strip(), row["week"].strip(), row["season_type"].strip()) != (str(season), str(week), "REG"):
            continue
        for column in checked:
            try:
                _number(row[column], column)
            except ValueError:
                raise PlayerGradingRefused(
                    "PLAYER_GRADING_STATS_INVALID", f"CELL_INVALID:row={number}:{column}={row[column]!r}") from None
        player_id = row["player_id"].strip()
        if not player_id:
            unattributed += 1
            continue
        if player_id in rows:
            raise PlayerGradingRefused("PLAYER_GRADING_STATS_INVALID", f"DUPLICATE_PLAYER_WEEK:row={number}:{player_id}")
        rows[player_id] = row
    if not rows:
        raise PlayerGradingRefused("PLAYER_GRADING_WEEK_ABSENT", f"season={season}:week={week}:no REG rows")
    return frozenset(header), rows, unattributed


def stat_line(row: Mapping[str, str], columns: frozenset[str], position: str):
    """The scoring.py line a row maps to, or None and each column it lacks."""

    mapping = KICKER_MAP if position == "K" else OFFENSE_MAP
    gaps: list[dict[str, str]] = []
    values: dict[str, float] = {}
    for field, sources in mapping.items():
        total = 0.0
        for column in sources:
            if column not in columns:
                gaps.append({"kind": f"STAT_NOT_CARRIED:{column}"})
                continue
            value = _number(row.get(column), column)
            if value is None:
                gaps.append({"kind": f"STAT_CELL_BLANK:{column}"})
                continue
            total += value
        values[field] = total
    if gaps:
        return None, gaps
    if position == "K":
        return KickerStatLine(**{field: int(value) for field, value in values.items()}), []
    return OffensiveStatLine(**{field: value if field in YARD_FIELDS else int(value)
                                for field, value in values.items()}), []


def _realized(position: str, provider: str | None, rows: Mapping[str, Mapping[str, str]],
              columns: frozenset[str]) -> dict[str, object]:
    found: dict[str, object] = {"realized_hundredths": None, "stat_line": None, "gaps": [], "notes": [],
                                "game_id": None}
    if position == "DST":
        found["gaps"] = [{"kind": "DST_NOT_IN_PLAYER_FILE"}]
        return found
    row = rows.get(provider) if provider else None
    if provider is None:
        found["gaps"] = [{"kind": "IDENTITY_UNBOUND"}]
    elif row is None:
        found["gaps"] = [{"kind": "NO_STAT_ROW"}]
    if row is None:
        return found
    found["game_id"] = row["game_id"].strip()
    line, gaps = stat_line(row, columns, position)
    if line is None:
        found["gaps"] = gaps
        return found
    points = score_kicker(line) if position == "K" else score_offense(line)
    found.update(realized_hundredths=round(points * 100), stat_line=dataclasses.asdict(line))
    if all(column in columns for column in ("fumbles_lost_total", *FUMBLE_PARTS)):
        total = _number(row["fumbles_lost_total"], "fumbles_lost_total")
        parts = [_number(row[column], column) for column in FUMBLE_PARTS]
        if total is not None and None not in parts and total != sum(parts):
            found["notes"] = [f"FUMBLES_LOST_SOURCES_DIFFER:total={total:g}:parts={sum(parts):g}"]
    return found


# ----------------------------------------------------------------- inputs


def _input(name: str, why: object) -> PlayerGradingRefused:
    return PlayerGradingRefused("PLAYER_GRADING_INPUT_INVALID", f"{name}:{why}"[:400])


def _json(path: Path, name: str) -> dict:
    try:
        payload = json.loads(Path(path).read_bytes().decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _input(name, f"UNREADABLE:{exc}") from exc
    if not isinstance(payload, dict):
        raise _input(name, "NOT_AN_OBJECT")
    return payload


def _pool_scores(path: Path, people: Mapping[str, object], dk_ids: set[str]) -> tuple[dict[str, float], set[str], str]:
    payload = _json(path, "pool_scores")
    if payload.get("schema_version") != POOL_SCORES_SCHEMA:
        raise _input("pool_scores", f"SCHEMA:{payload.get('schema_version')!r}")
    by_person, by_dk_id = payload.get("by_person"), payload.get("by_dk_id")
    excluded = payload.get("excluded_dk_ids", [])
    if not isinstance(by_person, dict) or not isinstance(by_dk_id, dict) or not isinstance(excluded, list):
        raise _input("pool_scores", "SHAPE")
    for key, value in by_person.items():
        if key not in people:
            raise _input("pool_scores", f"PERSON_NOT_ON_SLATE:{key}")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise _input("pool_scores", f"PRIOR_NOT_A_NUMBER:{key}")
    off_slate = sorted(set(by_dk_id) - dk_ids)
    if off_slate:
        raise _input("pool_scores", f"DK_ID_NOT_ON_SLATE:{off_slate[:5]}")
    selectable = set(by_dk_id) - {str(item) for item in excluded}
    return {key: float(value) for key, value in by_person.items()}, selectable, str(payload.get("score_version"))


def _identity(path: Path, anchors: Mapping[str, object]) -> dict[str, str]:
    """Each anchor DK ID's accepted nflverse ID; anyone else is unbound.

    `_resolve_reviewed`'s rule on the file's own columns: `ACCEPT`, then the reviewed ID, else the file's proposed ID.
    The engine takes the proposed ID from its own fresh proposal instead; the two agree on any file the engine wrote.
    """

    try:
        decisions = priors.read_reviewed_decisions(Path(path))
    except (priors.PriorsBuildError, ValueError, csv.Error, AttributeError) as exc:  # bad encoding or a misshapen row
        raise _input("identity", f"{type(exc).__name__}:{exc}") from exc
    bound: dict[str, str] = {}
    for dk_id, row in decisions.items():
        player = anchors.get(dk_id)
        if player is None:
            raise _input("identity", f"DK_ID_NOT_ON_SLATE:{dk_id}")
        for column, expected in (("DK_NAME", player.name), ("DK_TEAM", player.team), ("DK_POSITION", player.position)):
            if row.get(column, "") != expected:
                raise _input("identity", f"ROW_ALTERED:{dk_id}:{column}")
        provider = row.get("REVIEWED_PROVIDER_PLAYER_ID", "") or row.get("PROPOSED_PROVIDER_PLAYER_ID", "")
        if row.get("DECISION", "").upper() == priors.ACCEPTED_DECISION and provider:
            bound[dk_id] = provider
    repeated = sorted(provider for provider, count in Counter(bound.values()).items() if count > 1)
    if repeated:
        raise _input("identity", f"PROVIDER_ID_NOT_UNIQUE:{repeated[:5]}")
    return bound


def _entries(path: Path) -> dict[str, dict]:
    payload = _json(path, "entries")
    if payload.get("schema_version") != ENTRIES_VERSION or not isinstance(payload.get("entries"), list):
        raise _input("entries", f"SCHEMA:{payload.get('schema_version')!r}")
    found: dict[str, dict] = {}
    for item in payload["entries"]:
        if not isinstance(item, dict):
            raise _input("entries", "ENTRY_NOT_AN_OBJECT")
        key, points = item.get("entry_key"), item.get("points_hundredths")
        if (not isinstance(key, str) or key in found or not isinstance(item.get("contest_key"), str)
                or isinstance(points, bool) or not isinstance(points, int)):
            raise _input("entries", f"ENTRY_INVALID:{key!r}")
        found[key] = item
    return found


# ----------------------------------------------------------------- statistics


def _ranks(values: Sequence[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start
        while end + 1 < len(order) and values[order[end + 1]] == values[order[start]]:
            end += 1
        for position in range(start, end + 1):
            ranks[order[position]] = (start + end) / 2 + 1
        start = end + 1
    return ranks


def spearman(xs: Sequence[float], ys: Sequence[float]) -> tuple[float | None, str | None]:
    """Spearman's rho with tied ranks averaged; None and why below 3 people or at zero variance."""

    if len(xs) < 3:
        return None, "FEWER_THAN_3"
    rx, ry = _ranks(xs), _ranks(ys)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    sxy = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    sxx, syy = sum((a - mx) ** 2 for a in rx), sum((b - my) ** 2 for b in ry)
    if sxx == 0 or syy == 0:
        return None, "ZERO_VARIANCE"
    return round(sxy / math.sqrt(sxx * syy), 6), None


def _measures(predicted: Sequence[float], realized: Sequence[float]) -> dict[str, object]:
    mae = round(sum(abs(p - r) for p, r in zip(predicted, realized)) / len(realized), 6) if realized else None
    rho, note = spearman(predicted, realized)
    return {"player_points_mae": {"value": mae, "n": len(realized), "registered_metric": "player_points_mae",
                                  "departures": list(MAE_DEPARTURES)},
            "spearman": {"value": rho, "n": len(realized), "note": note}}


def _text(value: Fraction) -> str:
    if value.denominator == 1:
        return str(value.numerator)
    return f"{float(value):.2f}"


# ----------------------------------------------------------------- the tables and play rate (Session 70b)


def salary_tiers(salaries: Sequence[float]) -> list[str]:
    """Each salary's tertile, in input order (`TIER_RULE`). A tied block takes its mid-rank's tier, which can empty one."""

    # 3 (r - 0.5) / n is (6r - 3) / 2n; r is a whole or half rank, so 6r - 3 is a whole number and the floor is exact.
    return [TIER_NAMES[min(2, int(6 * rank - 3) // (2 * len(salaries)))] for rank in _ranks(salaries)]


def tier_bounds(salaries: Sequence[float], tiers: Sequence[str]) -> dict[str, dict]:
    found = {}
    for name in TIER_NAMES:
        members = [salary for salary, tier in zip(salaries, tiers) if tier == name]
        found[name] = {"people": len(members), "salary_min": min(members, default=None),
                       "salary_max": max(members, default=None)}
    return found


def _cell(rows: Sequence[Mapping]) -> dict:
    usable = [row for row in rows if row["realized"] is not None]
    cell: dict[str, object] = {"n": len(usable)}
    for side, key in (("prior", "prior"), ("salary", "salary_points")):
        if len(usable) < MIN_CELL_PEOPLE:
            cell[side] = {"player_points_mae": None, "spearman": None, "note": "FEWER_THAN_3"}
            continue
        measures = _measures([row[key] for row in usable], [row["realized"] for row in usable])
        cell[side] = {"player_points_mae": measures["player_points_mae"]["value"],
                      "spearman": measures["spearman"]["value"], "note": measures["spearman"]["note"]}
    return cell


def grade_tables(rows: Sequence[Mapping]) -> dict:
    """`player_points_mae` and Spearman by position and by salary tier, reported separately and never crossed.

    `rows` are the graded non-DST people (`position`, `salary_tier`, `prior`, `salary_points`, `realized`; the last two
    None without realized points). Each cell is measured over its rows with realized points and is null below 3.
    """

    positions = sorted({row["position"] for row in rows})
    return {"by_position": {position: _cell([row for row in rows if row["position"] == position])
                            for position in positions},
            "by_tier": {tier: _cell([row for row in rows if row["salary_tier"] == tier]) for tier in TIER_NAMES}}


def _status_class(status: str) -> str:
    value = status.strip().upper()  # `dk.py` only strips; the engine's unavailability test upper-cases
    for name, vocabulary in (("AVAILABLE", AVAILABLE_STATUSES), ("DEGRADED", DEGRADED_STATUSES),
                             ("UNAVAILABLE", UNAVAILABLE_STATUSES)):
        if value in vocabulary:
            return name
    return "UNRECOGNIZED"


def play_rate(people: Sequence[Mapping]) -> dict:
    """Realized play rate by DraftKings status over every identity-bound non-DST person (`PLAYED_MEANS`)."""

    by_status: dict[str, dict] = {}
    for person in people:
        if person["position"] == "DST":
            continue
        status = person["dk_status"] or ""
        row = by_status.setdefault(status or "(blank)", {"class": _status_class(status), "people": 0, "played": 0,
                                                         "unbound": 0})
        if person["provider_player_id"] is None:
            row["unbound"] += 1
        else:
            row["people"] += 1
            row["played"] += int(person["game_id"] is not None)
    for row in by_status.values():
        row["rate"] = round(row["played"] / row["people"], 6) if row["people"] else None
    return {"population": PLAY_RATE_POPULATION, "played_means": PLAYED_MEANS,
            "by_status": dict(sorted(by_status.items()))}


# ----------------------------------------------------------------- the grade


def _reconcile(lineups: Path, entries: Path, contract, by_dk_id: Mapping, people: Mapping[str, dict]) -> dict:
    try:
        template = parse_entries(Path(lineups))
        mode = template.mode
    except Exception as exc:  # any parse failure of the delivered file is that input's refusal
        raise _input("lineups", f"{type(exc).__name__}:{exc}") from exc
    if mode is not contract.mode:
        raise _input("lineups", f"MODE:{mode.value}!={contract.mode.value}")
    history = _entries(entries)
    results, residuals = [], {}
    for auth in template.authorizations:
        if not any(cell.strip() for cell in auth.existing_cells):
            results.append({"entry_id": auth.entry_id, "status": "BLANK_LINEUP"})
            continue
        cell_ids = [prefilled_cell_id(cell) for cell in auth.existing_cells]
        if None in cell_ids or any(dk_id not in by_dk_id for dk_id in cell_ids):
            raise _input("lineups", f"CELL_NOT_AN_EXACT_SLATE_ID:{auth.entry_id}")
        total, players, uncovered = Fraction(0), [], []
        for dk_id in cell_ids:
            player = by_dk_id[dk_id]
            captain = player.role == "CPT"
            person = people[player.underlying_id]
            points = None
            if person["realized_hundredths"] is None:
                uncovered.append((player.underlying_id, captain))
            else:
                points = Fraction(person["realized_hundredths"]) * (Fraction(3, 2) if captain else 1)
                total += points
            players.append({"dk_id": dk_id, "underlying_id": player.underlying_id, "captain": captain,
                            "points_hundredths": None if points is None else _text(points),
                            "stat_line": person["stat_line"], "gaps": person["gaps"]})
        entry = history.get(auth.entry_id)
        gap = None if entry is None else Fraction(entry["points_hundredths"]) - total
        if entry is None:
            status = "ENTRY_NOT_IN_HISTORY"
        elif entry["contest_key"] != auth.contest_id:
            status = "CONTEST_DISAGREES"
        elif uncovered:
            status = "NOT_FULLY_COVERED"
            if len(uncovered) == 1:
                person_id, captain = uncovered[0]
                residuals.setdefault(person_id, []).append(gap / (Fraction(3, 2) if captain else 1))
        else:
            status = "RECONCILED" if abs(gap) <= TOLERANCE_HUNDREDTHS else "MISMATCH"
        results.append({"entry_id": auth.entry_id, "contest_id": auth.contest_id, "status": status,
                        "realized_hundredths": _text(total),
                        "dk_hundredths": None if entry is None else entry["points_hundredths"],
                        "gap_hundredths": None if gap is None else _text(gap),
                        "uncovered": [person_id for person_id, _captain in uncovered], "players": players})
    groups = {}
    for person_id, implied in sorted(residuals.items()):
        spread = max(implied) - min(implied)
        groups[person_id] = {
            "lineups": len(implied), "implied_hundredths": [_text(value) for value in sorted(implied)],
            "spread_hundredths": _text(spread),
            "status": "SINGLE" if len(implied) == 1 else
            ("AGREE" if spread <= RESIDUAL_AGREEMENT_HUNDREDTHS else "DISAGREE")}
    return {
        "statuses": dict(sorted(Counter(item["status"] for item in results).items())),
        "tolerance_hundredths": TOLERANCE_HUNDREDTHS,
        "lineups": results,
        "residual_groups": groups,
        "residual_coverage": {
            "lineups_with_one_uncovered_person": sum(group["lineups"] for group in groups.values()),
            "groups_checked": sum(1 for group in groups.values() if group["lineups"] > 1),
            "single_lineup_groups": sum(1 for group in groups.values() if group["lineups"] == 1),
            "agreement_tolerance_hundredths": RESIDUAL_AGREEMENT_HUNDREDTHS,
            "blind_spot": "agreement cannot see an error in a person every lineup of the group holds",
        },
    }


def bind_games(games: Sequence[tuple[str, Sequence[str]]],
               found: Mapping[str, Sequence[tuple[str, str, str]]]) -> dict[str, str]:
    """Each DraftKings game's one nflverse `game_id`.

    `games` is each game with its two teams; `found` is, per game, `(team, game_id, person)` for every bound person with
    a stat row. Both teams must have a row (a wrong week with one team on bye would otherwise bind), every row must name
    the same `game_id`, and no two games may share one.
    """

    bound: dict[str, str] = {}
    for game, teams in games:
        rows = found.get(game, ())
        ids = sorted({game_id for _team, game_id, _person in rows})
        if not ids:
            raise PlayerGradingRefused("PLAYER_GRADING_GAME_UNBOUND", f"{game}:NO_STAT_ROWS")
        if len(ids) > 1:
            people = {game_id: sorted(p for _t, g, p in rows if g == game_id)[:3] for game_id in ids}
            raise PlayerGradingRefused("PLAYER_GRADING_GAME_UNBOUND", f"{game}:ROWS_NAME_SEVERAL_GAMES:{people}")
        absent = sorted(set(teams) - {team for team, _game_id, _person in rows})
        if absent:
            raise PlayerGradingRefused("PLAYER_GRADING_GAME_UNBOUND", f"{game}:{ids[0]}:NO_STAT_ROW_FOR:{absent}")
        if ids[0] in bound.values():
            raise PlayerGradingRefused("PLAYER_GRADING_GAME_UNBOUND", f"{game}:{ids[0]}:ALSO_ANOTHER_GAME")
        bound[game] = ids[0]
    return bound


def grade_slate(*, stats_raw: bytes, stats_entry: Mapping[str, object], season: int, week: int, salaries: Path,
                pool_scores: Path, identity_review: Path, lineups: Path | None = None,
                entries: Path | None = None) -> dict:
    """The per-slate report (`nfl_player_grading_v1`). Raises `PlayerGradingRefused` and writes nothing."""

    if sha256_bytes(stats_raw) != stats_entry.get("sha256"):
        raise PlayerGradingRefused("PLAYER_GRADING_STATS_INVALID", "BYTES_DO_NOT_MATCH_THE_PACKAGE_SHA256")
    if (lineups is None) != (entries is None):
        raise _input("lineups" if entries is not None else "entries", "LINEUPS_AND_ENTRIES_GO_TOGETHER")
    try:
        contract = parse_salaries(Path(salaries))
    except Exception as exc:  # any parse failure of the salary file is that input's refusal
        raise _input("salaries", f"{type(exc).__name__}:{exc}") from exc
    by_dk_id = {player.dk_id: player for player in contract.players}
    anchors = {player.underlying_id: player for player in contract.players if player.role != "CPT"}
    prior, selectable, score_version = _pool_scores(Path(pool_scores), anchors, set(by_dk_id))
    provider_by_dk = _identity(Path(identity_review), {player.dk_id: player for player in anchors.values()})
    columns, rows, unattributed = parse_week(stats_raw, season, week)

    people: dict[str, dict] = {}
    for person_id, player in sorted(anchors.items()):
        provider = provider_by_dk.get(player.dk_id)
        people[person_id] = {
            "underlying_id": person_id, "dk_id": player.dk_id, "position": player.position, "team": player.team,
            "salary": player.salary, "dk_status": player.status_raw, "prior_points": prior.get(person_id),
            "out_of_selection": None if person_id not in prior else player.dk_id not in selectable,
            "provider_player_id": provider, "salary_tier": None,
            **_realized(player.position, provider, rows, columns)}
    found_games: dict[str, list[tuple[str, str, str]]] = {}
    for person_id, entry in people.items():
        if entry["game_id"]:
            anchor = anchors[person_id]
            found_games.setdefault(anchor.game_id, []).append((anchor.team, entry["game_id"], person_id))
    bound_games = bind_games([(game.game_id, (game.away_team, game.home_team)) for game in contract.games],
                             found_games)

    graded = [entry for person_id, entry in people.items() if person_id in prior]
    usable = [entry for entry in graded if entry["realized_hundredths"] is not None]
    realized = [entry["realized_hundredths"] / 100 for entry in usable]
    priors_ = [entry["prior_points"] for entry in usable]
    salary_total = sum(entry["salary"] for entry in usable)
    scale = sum(priors_) / salary_total if salary_total else 0.0
    salary_points = [entry["salary"] * scale for entry in usable]
    tiered = [entry for entry in graded if entry["position"] != "DST"]
    tier_salaries = [entry["salary"] for entry in tiered]
    for entry, tier in zip(tiered, salary_tiers(tier_salaries)):
        entry["salary_tier"] = tier
    salary_by_person = {entry["underlying_id"]: points for entry, points in zip(usable, salary_points)}
    tables = grade_tables([
        {"position": entry["position"], "salary_tier": entry["salary_tier"], "prior": entry["prior_points"],
         "salary_points": salary_by_person.get(entry["underlying_id"]),
         "realized": None if entry["realized_hundredths"] is None else entry["realized_hundredths"] / 100}
        for entry in tiered])
    report = {
        "schema_version": SCHEMA_VERSION,
        "realized_points_version": REALIZED_VERSION,
        "model_status": "PRIOR_ONLY",
        "status": "DIAGNOSTIC_NOT_AN_UPLOAD_AUTHORIZATION",
        "slate": {"mode": contract.mode.value, "season": season, "week": week, "games": bound_games,
                  "week_stat_rows": len(rows), "unattributed_stat_rows": unattributed},
        "inputs": {
            "salaries": {"sha256": sha256_file(Path(salaries))},
            "pool_scores": {"sha256": sha256_file(Path(pool_scores)), "score_version": score_version,
                            "binding": "KEY_MEMBERSHIP_ONLY: the file carries no salary hash"},
            "identity_review": {"sha256": sha256_file(Path(identity_review)), "bound_people": len(provider_by_dk)},
            "lineups": None if lineups is None else {"sha256": sha256_file(Path(lineups))},
            "entries": None if entries is None else {"sha256": sha256_file(Path(entries))},
        },
        "stats_source": dict(stats_entry),
        "people": [people[person_id] for person_id in sorted(people)],
        "grade": {
            "graded_people": len(graded), "usable_people": len(usable),
            "out_of_selection": sum(1 for entry in graded if entry["out_of_selection"]),
            "gaps_by_kind": dict(sorted(Counter(gap["kind"] for entry in graded for gap in entry["gaps"]).items())),
            "prior": _measures(priors_, realized),
            "salary": {**_measures(salary_points, realized), "baseline_version": SALARY_BASELINE_VERSION},
            "sample": {"people": len(usable), "slates": 1},
            "by_position": tables["by_position"],
            "by_tier": tables["by_tier"],
            "tiers": {"rule": TIER_RULE, **tier_bounds(tier_salaries, [entry["salary_tier"] for entry in tiered])},
            "play_rate": play_rate([people[person_id] for person_id in sorted(people)]),
        },
        "reconciliation": None if lineups is None else _reconcile(lineups, entries, contract, by_dk_id, people),
        "not_computed": dict(NOT_COMPUTED),
        "does_not_establish": list(DOES_NOT_ESTABLISH),
    }
    return report


def render(report: Mapping[str, object]) -> bytes:
    return (json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def write_report(report: Mapping[str, object], out: Path) -> tuple[Path, str]:
    data = render(report)
    try:
        Path(out).mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise PlayerGradingRefused("PLAYER_GRADING_OUTPUT_EXISTS", str(out)) from exc
    target = Path(out) / REPORT_NAME
    try:
        target.write_bytes(data)
        digest = sha256_file(target)
        if digest != sha256_bytes(data):
            raise OSError(f"{target}: written bytes differ")
    except OSError:
        # This run made the folder: leave nothing behind, so a rerun is not refused as OUTPUT_EXISTS.
        with contextlib.suppress(OSError):
            target.unlink(missing_ok=True)
            Path(out).rmdir()
        raise
    return target, digest


def run(*, salaries, pool_scores, identity_review, stats_package, season, week, out, lineups=None,
        entries=None) -> tuple[int, dict]:
    """`nfl grade-players`: exit 0 and the summary, or exit 2 and the refusal. Never a release truth."""

    try:
        if Path(out).exists():
            raise PlayerGradingRefused("PLAYER_GRADING_OUTPUT_EXISTS", str(out))
        raw, entry = load_or_fetch_stats(Path(stats_package), season)
        report = grade_slate(stats_raw=raw, stats_entry=entry, season=season, week=week, salaries=salaries,
                             pool_scores=pool_scores, identity_review=identity_review, lineups=lineups,
                             entries=entries)
        target, digest = write_report(report, Path(out))
    except PlayerGradingRefused as exc:
        return 2, {"status": "REFUSED", "code": exc.code, "detail": exc.detail, "model_status": "PRIOR_ONLY"}
    except OSError as exc:
        return 2, {"status": "WRITE_FAILED", "detail": f"{type(exc).__name__}:{exc}", "model_status": "PRIOR_ONLY"}
    except Exception as exc:  # never fall through to cli.main's handler, which prints lineup release truths
        return 2, {"status": "FAILED", "detail": f"{type(exc).__name__}:{exc}", "model_status": "PRIOR_ONLY"}
    grade = report["grade"]
    reconciliation = report["reconciliation"]
    return 0, {
        "status": "COMPLETE", "model_status": "PRIOR_ONLY", "report": str(target), "report_sha256": digest,
        "graded_people": grade["graded_people"], "usable_people": grade["usable_people"],
        "player_points_mae": {side: grade[side]["player_points_mae"]["value"] for side in ("prior", "salary")},
        "spearman": {side: grade[side]["spearman"]["value"] for side in ("prior", "salary")},
        "reconciliation": None if reconciliation is None else reconciliation["statuses"],
        "residual_groups": None if reconciliation is None else dict(sorted(Counter(
            group["status"] for group in reconciliation["residual_groups"].values()).items())),
    }


# ----------------------------------------------------------------- the pool (Session 70b, `nfl_player_grading_pool_v1`)


class _Shape(ValueError):
    """A report key that is absent or of the wrong type; the message names it."""


def _at(payload: Mapping, *keys: str) -> object:
    value: object = payload
    for key in keys:
        if not isinstance(value, dict) or key not in value:
            raise _Shape(".".join(keys))
        value = value[key]
    return value


def _value_at(payload: Mapping, *keys: str) -> float | None:
    value = _at(payload, *keys)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise _Shape(".".join(keys))
    return float(value)


def _whole_at(payload: Mapping, *keys: str) -> int:
    value = _at(payload, *keys)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise _Shape(".".join(keys))
    return value


def _typed_at(payload: Mapping, kind: type, *keys: str):
    value = _at(payload, *keys)
    if not isinstance(value, kind):
        raise _Shape(".".join(keys))
    return value


def _pool_entry(payload: Mapping) -> dict:
    games = _typed_at(payload, dict, "slate", "games")
    if not all(isinstance(game_id, str) for game_id in games.values()):
        raise _Shape("slate.games")
    slate = {
        "salaries_sha256": _typed_at(payload, str, "inputs", "salaries", "sha256"),
        "mode": _typed_at(payload, str, "slate", "mode"),
        "season": _whole_at(payload, "slate", "season"),
        "week": _whole_at(payload, "slate", "week"),
        "games": sorted(games.values()),
        "stats_source_sha256": _typed_at(payload, str, "stats_source", "sha256"),
        "stats_observed_at": _typed_at(payload, str, "stats_source", "observed_at"),
        "score_version": _typed_at(payload, str, "inputs", "pool_scores", "score_version"),
        "graded_people": _whole_at(payload, "grade", "graded_people"),
        "usable_people": _whole_at(payload, "grade", "usable_people"),
    }
    cells = {("overall", "", side): {measure: (_value_at(payload, "grade", side, measure, "value"),
                                               _whole_at(payload, "grade", side, measure, "n"))
                                     for measure in MEASURES} for side in SIDES}
    for section in ("by_position", "by_tier"):
        for group in sorted(_typed_at(payload, dict, "grade", section)):
            n = _whole_at(payload, "grade", section, group, "n")
            for side in SIDES:
                cells[(section, group, side)] = {
                    measure: (_value_at(payload, "grade", section, group, side, measure), n) for measure in MEASURES}
    play = {}
    for status in sorted(_typed_at(payload, dict, "grade", "play_rate", "by_status")):
        keys = ("grade", "play_rate", "by_status", status)
        play[status] = {"class": _typed_at(payload, str, *keys, "class"), "rate": _value_at(payload, *keys, "rate"),
                        **{count: _whole_at(payload, *keys, count) for count in ("people", "played", "unbound")}}
    return {"slate": slate, "cells": cells, "play": play}


def read_pool_report(path: Path, index: int) -> dict:
    """One per-slate report for the pool, its SHA-256 taken from the bytes it was parsed from."""

    name = f"pool_report:{index}"
    try:
        raw = Path(path).read_bytes()
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _input(name, f"UNREADABLE:{type(exc).__name__}") from exc
    if not isinstance(payload, dict):
        raise _input(name, "NOT_AN_OBJECT")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise _input(name, f"SCHEMA:{payload.get('schema_version')!r}")
    try:
        found = _pool_entry(payload)
    except _Shape as exc:
        raise _input(name, f"SHAPE:{exc}") from None
    found["slate"]["report_sha256"] = sha256_bytes(raw)
    found["argument"] = index
    return found


def _pooled(items: Sequence[tuple[float | None, int] | None]) -> dict:
    """The unweighted mean over the slates with a value, each slate's value aligned (null where it has none)."""

    present = [item for item in items if item is not None and item[0] is not None]
    return {"value": round(sum(value for value, _n in present) / len(present), 6) if present else None,
            "slates": len(present), "people": sum(n for _value, n in present),
            "values": [None if item is None else item[0] for item in items]}


def _pooled_cells(found: Sequence[dict], section: str, group: str) -> dict:
    return {side: {measure: _pooled([entry["cells"].get((section, group, side), {}).get(measure) for entry in found])
                   for measure in MEASURES} for side in SIDES}


def _independent_slates(found: Sequence[dict]) -> tuple[dict[str, list[int]], int]:
    """Each nflverse game two or more slates share (1-based positions), and the groups shared games link."""

    at: dict[str, list[int]] = {}
    for position, entry in enumerate(found, start=1):
        for game_id in entry["slate"]["games"]:
            at.setdefault(game_id, []).append(position)
    shared = {game_id: positions for game_id, positions in sorted(at.items()) if len(positions) > 1}
    parent = list(range(len(found) + 1))

    def root(position: int) -> int:
        while parent[position] != position:
            position = parent[position]
        return position

    for positions in shared.values():
        for position in positions[1:]:
            parent[root(position)] = root(positions[0])
    return shared, len({root(position) for position in range(1, len(found) + 1)})


def pool_reports(paths: Sequence[Path]) -> dict:
    """`nfl_player_grading_pool_v1`: each cell macro-averaged over the slates that have it. Raises, writes nothing."""

    if len(paths) < 2:
        raise _input("pool", "FEWER_THAN_2_REPORTS")
    found = [read_pool_report(Path(path), index) for index, path in enumerate(paths, start=1)]
    seen_salary: dict[str, int] = {}
    seen_games: dict[tuple, int] = {}
    for entry in found:
        slate = entry["slate"]
        for seen, key in ((seen_salary, slate["salaries_sha256"]),
                          (seen_games, (slate["mode"], slate["season"], slate["week"], tuple(slate["games"])))):
            if key in seen:
                raise _input(f"pool_report:{entry['argument']}", f"REPEATED_SLATE:{seen[key]}")
            seen[key] = entry["argument"]
    found.sort(key=lambda entry: (entry["slate"]["season"], entry["slate"]["week"], entry["slate"]["salaries_sha256"]))
    shared, independent = _independent_slates(found)
    usable = [entry["slate"]["usable_people"] for entry in found]
    weights = [1.0] * len(found)
    groups = {section: sorted({group for entry in found for kind, group, _side in entry["cells"] if kind == section})
              for section in ("by_position", "by_tier")}
    play_rate = {}
    for status in sorted({status for entry in found for status in entry["play"]}):
        rows = [entry["play"].get(status) for entry in found]
        present = [row for row in rows if row is not None]
        play_rate[status] = {"class": present[0]["class"],
                             "rate": _pooled([None if row is None else (row["rate"], row["people"]) for row in rows]),
                             **{count: sum(row[count] for row in present) for count in ("people", "played", "unbound")}}
    return {
        "schema_version": POOL_SCHEMA_VERSION,
        "report_schema_version": SCHEMA_VERSION,
        "model_status": "PRIOR_ONLY",
        "status": "DIAGNOSTIC_NOT_AN_UPLOAD_AUTHORIZATION",
        "unit": "slate",
        "slates": [entry["slate"] for entry in found],
        "sample": {
            "slates": len(found), "weights": "EQUAL_PER_SLATE",
            "kish_ess": sum(weights) ** 2 / sum(weight * weight for weight in weights),
            "independent_slates": independent, "usable_people_by_slate": usable, "usable_people": sum(usable),
            "registered_minimum_sample": REGISTERED_MINIMUM_SAMPLE,
            "meets_minimum_sample": sum(usable) >= REGISTERED_MINIMUM_SAMPLE,
        },
        "independence": {"shared_games": shared},
        "sources": {"stats_packages": len({entry["slate"]["stats_source_sha256"] for entry in found}),
                    "score_versions": sorted({entry["slate"]["score_version"] for entry in found})},
        "overall": _pooled_cells(found, "overall", ""),
        "by_position": {group: _pooled_cells(found, "by_position", group) for group in groups["by_position"]},
        "by_tier": {group: _pooled_cells(found, "by_tier", group) for group in groups["by_tier"]},
        "play_rate": play_rate,
        "not_computed": dict(POOL_NOT_COMPUTED),
        "does_not_establish": list(POOL_DOES_NOT_ESTABLISH),
    }


def write_pool(pool: Mapping[str, object], out: Path) -> tuple[Path, str]:
    data = render(pool)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        handle = out.open("xb")
    except FileExistsError as exc:
        raise PlayerGradingRefused("PLAYER_GRADING_OUTPUT_EXISTS", str(out)) from exc
    try:
        with handle:
            handle.write(data)
        digest = sha256_file(out)
        if digest != sha256_bytes(data):
            raise OSError(f"{out}: written bytes differ")
    except OSError:
        with contextlib.suppress(OSError):
            out.unlink(missing_ok=True)  # this run made the file: leave nothing a rerun would be refused over
        raise
    return out, digest


def run_pool(*, reports, out) -> tuple[int, dict]:
    """`nfl grade-players --pool`: exit 0 and the summary, or exit 2 and the refusal. Never a release truth."""

    try:
        if Path(out).exists():
            raise PlayerGradingRefused("PLAYER_GRADING_OUTPUT_EXISTS", str(out))
        pool = pool_reports([Path(report) for report in reports])
        target, digest = write_pool(pool, Path(out))
    except PlayerGradingRefused as exc:
        return 2, {"status": "REFUSED", "code": exc.code, "detail": exc.detail, "model_status": "PRIOR_ONLY"}
    except OSError as exc:
        return 2, {"status": "WRITE_FAILED", "detail": f"{type(exc).__name__}:{exc}", "model_status": "PRIOR_ONLY"}
    except Exception as exc:  # never fall through to cli.main's handler, which prints lineup release truths
        return 2, {"status": "FAILED", "detail": f"{type(exc).__name__}:{exc}", "model_status": "PRIOR_ONLY"}
    sample = pool["sample"]
    return 0, {
        "status": "COMPLETE", "model_status": "PRIOR_ONLY", "pool": str(target), "pool_sha256": digest,
        "slates": sample["slates"], "independent_slates": sample["independent_slates"],
        "usable_people": sample["usable_people"], "meets_minimum_sample": sample["meets_minimum_sample"],
        "player_points_mae": {side: pool["overall"][side]["player_points_mae"]["value"] for side in SIDES},
        "spearman": {side: pool["overall"][side]["spearman"]["value"] for side in SIDES},
    }
