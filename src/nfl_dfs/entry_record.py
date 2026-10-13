"""The per-Entry-ID build record (Session 72): one row per Entry ID of a delivered DraftKings file.

Contract `nfl_entry_build_record_v1` (`docs/DATA_CONTRACTS.md`). The record joins the delivered file, the salary file and the
entries template by exact DraftKings ID only, and reads each row's prior from one named source: a pool-score dump
(`nfl_prior_pool_scores_v1`, summed by exact DK ID in slot order, the engine's own lineup arithmetic) or a portfolio record's
own per-Entry-ID figure, taken as stated. It never recomputes a person's prior and never writes a number a source lacks.

Missing evidence is a named null: no prior source, a person the dump does not score, an entries file with no player table,
and, in this version, everything a run folder would supply (run ID, method, policy, thesis, market numbers; Session 72b).
Bad bytes are refused whole by name (`EntryRecordRefused`, registry family `entry_record`). The structure counts come from the
Session 23 rule (`portfolio_policy.structure_counts`) and the Classic stack rule (`classic_portfolio.stack_value`). The salary
file's average-points column is never read: `SalaryPlayer` has no field for it.

The record states what was built and what the priors said. It certifies nothing and changes no release truth;
`MODEL_STATUS=PRIOR_ONLY` and `RELEASE_DECISION=DO_NOT_UPLOAD` stand.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from . import entry_history
from .classic_portfolio import stack_value
from .contracts import EngineMode, SlateContract
from .dk import DraftKingsParseError, EntryTemplate, embedded_pool_ids, parse_entry_bytes, parse_salaries, reconcile_template
from .hashing import canonical_json_bytes, sha256_bytes
from .lineups import prefilled_cell_id, validate_lineup
from .portfolio_policy import structure_counts
from .selection import POOL_SCORES_SCHEMA

SCHEMA_VERSION = "nfl_entry_build_record_v1"
NO_RUN_FOLDER = "RUN_FOLDER_NOT_SUPPLIED"
DOES_NOT_ESTABLISH = (
    "EXPECTED_VALUE_OR_ROI",
    "WIN_OR_CASH_PROBABILITY",
    "AN_EDGE_OR_ITS_ABSENCE",
    "CALIBRATION",
    "WHICH_RUN_BUILT_THE_FILE",
    "UPLOAD_CLEARANCE",
)


class EntryRecordRefused(ValueError):
    """A build record refused whole, by a code in the registry's `entry_record` family."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code, self.detail = code, detail


def _read(path: str | Path, label: str) -> bytes:
    try:
        return Path(path).read_bytes()
    except OSError as exc:
        raise EntryRecordRefused("ENTRY_RECORD_INPUT_UNREADABLE", f"{label}: {type(exc).__name__}: {exc}") from None


def _entry_file(raw: bytes, label: str) -> EntryTemplate:
    try:
        return parse_entry_bytes(raw, source_name=label)
    except DraftKingsParseError as exc:
        raise EntryRecordRefused("ENTRY_RECORD_INPUT_UNREADABLE", f"{label}: {exc}") from None


def _finite(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _json(raw: bytes) -> object:
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise EntryRecordRefused("ENTRY_RECORD_PRIOR_SOURCE_INVALID", f"the prior source is not JSON: {exc}") from None


def _scores(raw: bytes, salary_ids: set[str]) -> tuple[dict[str, float], set[str], str]:
    """(score by DK ID, the dump's own excluded DK IDs, its score version) from an `nfl_prior_pool_scores_v1` dump."""

    document = _json(raw)
    if not isinstance(document, dict) or document.get("schema_version") != POOL_SCORES_SCHEMA:
        raise EntryRecordRefused(
            "ENTRY_RECORD_PRIOR_SOURCE_INVALID", f"the scores file does not declare schema_version {POOL_SCORES_SCHEMA}")
    by_dk_id, excluded = document.get("by_dk_id"), document.get("excluded_dk_ids", [])
    version = document.get("score_version")
    if (not isinstance(by_dk_id, dict) or not all(_finite(value) for value in by_dk_id.values())
            or not isinstance(excluded, list) or not isinstance(version, str)):
        raise EntryRecordRefused(
            "ENTRY_RECORD_PRIOR_SOURCE_INVALID", "the scores file needs by_dk_id (finite numbers), excluded_dk_ids and score_version")
    outside = sorted((set(map(str, by_dk_id)) | set(map(str, excluded))) - salary_ids)
    if outside:
        raise EntryRecordRefused(
            "ENTRY_RECORD_SALARY_MISMATCH", f"{len(outside)} DK IDs the dump names are not in the salary file, first {outside[0]}")
    return {str(key): float(value) for key, value in by_dk_id.items()}, {str(value) for value in excluded}, version


def _portfolio(raw: bytes, salary_ids: set[str], filled: dict[str, tuple[str, ...]]) -> dict[str, float]:
    """Each filled Entry ID's own `prior_points` from a portfolio record whose rosters are the file's, as sets.

    The record declares no schema or score version, so only the construction scripts' own shape is read
    (`scripts/build_thesis_portfolio.py`, `scripts/swap_inactives.py`): `lineups` with `entry_id`, `roster` and
    `prior_points`, beside `assignments_by_entry_id`, the two views agreeing Entry ID by Entry ID.
    """

    document = _json(raw)
    lineups = document.get("lineups") if isinstance(document, dict) else None
    assignments = document.get("assignments_by_entry_id") if isinstance(document, dict) else None
    if not isinstance(lineups, list) or not isinstance(assignments, dict):
        raise EntryRecordRefused(
            "ENTRY_RECORD_PRIOR_SOURCE_INVALID", "the portfolio record needs lineups and assignments_by_entry_id")
    figures: dict[str, tuple[frozenset[str], float]] = {}
    for item in lineups:
        entry = item.get("entry_id") if isinstance(item, dict) else None
        roster = item.get("roster") if isinstance(item, dict) else None
        points = item.get("prior_points") if isinstance(item, dict) else None
        if (not isinstance(entry, str) or entry in figures or not isinstance(roster, list)
                or not all(isinstance(dk_id, str) for dk_id in roster) or len(set(roster)) != len(roster)
                or not _finite(points)):
            raise EntryRecordRefused(
                "ENTRY_RECORD_PRIOR_SOURCE_INVALID", f"a portfolio lineup is malformed or repeated: {entry!r}")
        outside = sorted(set(roster) - salary_ids)
        if outside:
            raise EntryRecordRefused(
                "ENTRY_RECORD_SALARY_MISMATCH", f"Entry ID {entry} in the portfolio record holds {outside[0]}, not in the salary file")
        if not isinstance(assignments.get(entry), list) or set(assignments[entry]) != set(roster):
            raise EntryRecordRefused(
                "ENTRY_RECORD_PRIOR_SOURCE_INVALID", f"Entry ID {entry}'s lineup and assignment disagree in the portfolio record")
        figures[entry] = (frozenset(roster), float(points))
    if set(figures) != set(filled) or set(assignments) != set(figures):
        raise EntryRecordRefused(
            "ENTRY_RECORD_PRIOR_SOURCE_INVALID", "the portfolio record's Entry IDs are not the file's filled Entry IDs")
    differs = sorted(entry for entry, roster in filled.items() if figures[entry][0] != frozenset(roster))
    if differs:
        raise EntryRecordRefused(
            "ENTRY_RECORD_PRIOR_SOURCE_INVALID", f"the portfolio record's roster differs from the file's for {', '.join(differs)}")
    return {entry: figure for entry, (_roster, figure) in figures.items()}


def _rosters(slate: SlateContract, template: EntryTemplate, filled_file: EntryTemplate) -> dict[str, tuple[str, ...] | None]:
    """Each template Entry ID's roster as exact DK IDs in slot order, None when every cell is blank; anything else refuses."""

    by_file = {entry.entry_id: entry for entry in filled_file.authorizations}
    salary_ids = {player.dk_id for player in slate.players}
    rosters: dict[str, tuple[str, ...] | None] = {}
    for entry in template.authorizations:
        cells = by_file[entry.entry_id].existing_cells
        if not any(cell.strip() for cell in cells):
            rosters[entry.entry_id] = None
            continue
        roster: list[str] = []
        for slot, cell in enumerate(cells, start=1):
            dk_id = prefilled_cell_id(cell)
            if dk_id is None:
                raise EntryRecordRefused(
                    "ENTRY_RECORD_CELL_NOT_AN_EXACT_DK_ID",
                    f"Entry ID {entry.entry_id}, slot {slot}: {cell!r} names no exact DraftKings ID")
            if dk_id not in salary_ids:
                raise EntryRecordRefused(
                    "ENTRY_RECORD_DK_ID_NOT_IN_SALARY", f"Entry ID {entry.entry_id}, slot {slot}: {dk_id} is not in the salary file")
            roster.append(dk_id)
        checked = validate_lineup(slate, roster)
        if not checked.valid:
            raise EntryRecordRefused("ENTRY_RECORD_LINEUP_INVALID", f"Entry ID {entry.entry_id}: {'; '.join(checked.errors)}")
        rosters[entry.entry_id] = tuple(roster)
    return rosters


def _structure(slate: SlateContract, roster: tuple[str, ...], players: list, counts: dict[str, object]) -> dict[str, object]:
    one_qb = counts["qb_count"] == 1  # `stack_value` reads the roster's first QB, so a 0- or 2-QB row has no single one
    dst_opponents = {player.opponent for player in players if player.position == "DST"}
    team_split: dict[str, int] = {}
    for player in players:
        team_split[player.team] = team_split.get(player.team, 0) + 1
    return {
        "qb_count": counts["qb_count"],
        "pass_catchers_with_rostered_qb": counts["pass_catchers_with_rostered_qb"],
        "kicker_count": counts["kicker_count"],
        "dst_count": counts["dst_count"],
        "offense_against_own_dst": counts["offense_against_own_dst"],
        "offense_facing_rostered_dst": sum(
            1 for player in players if player.position != "DST" and player.team in dst_opponents),
        "team_split": team_split,
        "bring_backs": stack_value(slate, roster, "QB_BRINGBACK") if one_qb else None,
        "rb_with_own_dst": stack_value(slate, roster, "RB_DST_PAIR") if one_qb else None,
        "stack_rule_reason": None if one_qb else "STACK_RULE_NEEDS_ONE_QB",
    }


def build_records(
    salaries: str | Path,
    entries: str | Path,
    delivered: str | Path,
    *,
    scores: str | Path | None = None,
    portfolio: str | Path | None = None,
) -> list[dict[str, object]]:
    """One `nfl_entry_build_record_v1` row per Entry ID of the template, in template order, or a refusal by name."""

    if scores is not None and portfolio is not None:
        raise EntryRecordRefused("ENTRY_RECORD_PRIOR_SOURCE_INVALID", "one prior source, scores or a portfolio record, not both")
    salary_raw, entries_raw, file_raw = _read(salaries, "salaries"), _read(entries, "entries"), _read(delivered, "file")
    source = scores if scores is not None else portfolio
    source_raw = _read(source, "prior source") if source is not None else None
    try:
        slate = parse_salaries(salaries)
    except (OSError, ValueError) as exc:
        raise EntryRecordRefused("ENTRY_RECORD_INPUT_UNREADABLE", f"salaries: {exc}") from None
    if slate.salary_hash != sha256_bytes(salary_raw):
        raise EntryRecordRefused("ENTRY_RECORD_INPUT_UNREADABLE", "salaries: the file changed while it was read")
    template = _entry_file(entries_raw, "entries")
    try:
        reconcile_template(template, slate)
    except DraftKingsParseError as exc:
        raise EntryRecordRefused("ENTRY_RECORD_MODE_MISMATCH", f"entries against salaries: {exc}") from None
    salary_ids = {player.dk_id for player in slate.players}
    try:
        pool = embedded_pool_ids(entries_raw)
    except DraftKingsParseError as exc:
        raise EntryRecordRefused("ENTRY_RECORD_INPUT_UNREADABLE", f"entries: {exc}") from None
    if pool is not None and set(pool) != salary_ids:
        raise EntryRecordRefused(
            "ENTRY_RECORD_SALARY_MISMATCH",
            f"{len(salary_ids - set(pool))} salary IDs are not in the entries file's player table and "
            f"{len(set(pool) - salary_ids)} of its IDs are not in the salary file")

    filled_file = _entry_file(file_raw, "file")
    if filled_file.roster_columns != template.roster_columns:
        raise EntryRecordRefused(
            "ENTRY_RECORD_MODE_MISMATCH", f"the file's roster columns {filled_file.roster_columns} are not the template's")
    if filled_file.header != template.header:
        raise EntryRecordRefused("ENTRY_RECORD_FILE_GEOMETRY_DIFFERS", "the file's header is not the template's")
    by_template = {entry.entry_id: entry for entry in template.authorizations}
    outside = [entry.entry_id for entry in filled_file.authorizations if entry.entry_id not in by_template]
    if outside:
        raise EntryRecordRefused("ENTRY_RECORD_ENTRY_ID_NOT_IN_TEMPLATE", ", ".join(outside))
    by_file = {entry.entry_id: entry for entry in filled_file.authorizations}
    missing = [entry_id for entry_id in by_template if entry_id not in by_file]
    if missing:
        raise EntryRecordRefused(
            "ENTRY_RECORD_FILE_GEOMETRY_DIFFERS", f"template Entry IDs missing from the file: {', '.join(missing)}")
    moved = [entry_id for entry_id, entry in by_file.items() if entry.contest_id != by_template[entry_id].contest_id]
    if moved:
        raise EntryRecordRefused(
            "ENTRY_RECORD_FILE_GEOMETRY_DIFFERS", f"Contest ID differs from the template for {', '.join(moved)}")
    rosters = _rosters(slate, template, filled_file)

    score_by_id: dict[str, float] = {}
    excluded: set[str] = set()
    version = None
    figures: dict[str, float] = {}
    if scores is not None:
        score_by_id, excluded, version = _scores(source_raw, salary_ids)
    elif portfolio is not None:
        figures = _portfolio(source_raw, salary_ids, {key: value for key, value in rosters.items() if value is not None})
    kind = "POOL_SCORES_SUM" if scores is not None else "PORTFOLIO_RECORD" if portfolio is not None else None
    hashes = {
        "salary_sha256": sha256_bytes(salary_raw),
        "entries_sha256": sha256_bytes(entries_raw),
        "file_sha256": sha256_bytes(file_raw),
        "prior_source_sha256": sha256_bytes(source_raw) if source_raw is not None else None,
    }
    by_id = {player.dk_id: player for player in slate.players}
    earliest = min(player.lock_at for player in slate.players)

    rows: list[dict[str, object]] = []
    for entry in template.authorizations:
        roster = rosters[entry.entry_id]
        row: dict[str, object] = {
            "schema_version": SCHEMA_VERSION,
            "entry_id": entry.entry_id,
            "contest_id": entry.contest_id,
            "mode": slate.mode.value,
            "hashes": dict(hashes),
            "salary_binding": "ENTRIES_POOL_MATCH" if pool is not None else "ENTRIES_POOL_ABSENT",
            # Each run field null with its own reason; Session 72b fills the shapes the contract declares.
            "run": {"run_id": None, "method": None, "policy_sha256": None, "thesis": None,
                    "reasons": {field: NO_RUN_FOLDER for field in ("run_id", "method", "policy_sha256", "thesis")}},
            "rank": None,
            "does_not_establish": list(DOES_NOT_ESTABLISH),
        }
        prior = {"points": None, "score_version": version, "source": kind, "unscored_dk_ids": [],
                 "excluded_dk_ids_rostered": [], "reason": None}
        if roster is None:
            prior["reason"] = "UNFILLED"
            rows.append({**row, "roster": None, "captain_dk_id": None, "prior": prior, "salary_left": None,
                         "structure": None, "dk_status": None, "later_window_count": None,
                         "stack_game": {"game_id": None, "market": None, "market_reason": NO_RUN_FOLDER}})
            continue
        players = [by_id[dk_id] for dk_id in roster]
        if kind == "POOL_SCORES_SUM":
            # No number for a person the dump does not score; one the run's gates excluded keeps the dump's own number,
            # named, because the sum is still the dump's arithmetic and the exclusion is a gate decision.
            unscored = [dk_id for dk_id in roster if dk_id not in score_by_id]
            prior["excluded_dk_ids_rostered"] = [dk_id for dk_id in roster if dk_id in excluded]
            if unscored:
                prior["unscored_dk_ids"] = unscored
                prior["reason"] = "UNSCORED_DK_ID"
            else:
                prior["points"] = sum(score_by_id[dk_id] for dk_id in roster)
        elif kind == "PORTFOLIO_RECORD":
            prior["points"] = figures[entry.entry_id]
        else:
            prior["reason"] = "NO_PRIOR_SOURCE"
        quarterbacks = [player for player in players if player.position == "QB"]
        game = quarterbacks[0].game_id if slate.mode is EngineMode.CLASSIC else players[0].game_id
        flags = {player.dk_id: player.status_raw.strip() for player in players if player.status_raw.strip()}
        counts = structure_counts(slate, roster)
        rows.append({
            **row,
            "roster": list(roster),
            "captain_dk_id": roster[0] if slate.mode is EngineMode.SHOWDOWN else None,
            "prior": prior,
            "salary_left": counts["salary_left"],
            "structure": _structure(slate, roster, players, counts),
            "dk_status": {"flags": flags, "q_count": sum(1 for value in flags.values() if value.upper() == "Q")},
            "later_window_count": sum(1 for player in players if player.lock_at > earliest),
            "stack_game": {"game_id": game, "market": None, "market_reason": NO_RUN_FOLDER},
        })
    ranked = [row["prior"]["points"] for row in rows if row["prior"]["points"] is not None]
    for row in rows:
        value = row["prior"]["points"]
        row["rank"] = None if value is None else 1 + sum(1 for other in ranked if other > value)
    return rows


def record_bytes(rows: list[dict[str, object]]) -> bytes:
    """The record's bytes: one canonical JSON object per line (sorted keys, no spaces), LF, in template order."""

    return b"".join(canonical_json_bytes(row) + b"\n" for row in rows)


def write_record(path: str | Path, data: bytes) -> str:
    """Write the record once: `WRITTEN`, or `ALREADY_PRESENT` for the same bytes; anything else at the name refuses."""

    target = Path(path)
    try:
        return entry_history._write_once(
            target, data, code="ENTRY_RECORD_ARTIFACT_CONFLICT",
            recovery="a build record is written once; record another file under another name")
    except entry_history._Stop as stop:
        raise EntryRecordRefused(
            "ENTRY_RECORD_ARTIFACT_CONFLICT", f"{target.name}: another file holds the record's name ({stop.recovery})") from None
    except OSError as exc:
        raise EntryRecordRefused("ENTRY_RECORD_WRITE_FAILED", f"{target.name}: {type(exc).__name__}: {exc}") from None
