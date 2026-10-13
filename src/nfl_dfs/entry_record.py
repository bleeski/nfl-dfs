"""The per-Entry-ID build record (Session 72): one row per Entry ID of a delivered DraftKings file.

Contract `nfl_entry_build_record_v1` (`docs/DATA_CONTRACTS.md`). The record joins the delivered file, the salary file and the
entries template by exact DraftKings ID only, and reads each row's prior from one named source: a pool-score dump
(`nfl_prior_pool_scores_v1`, summed by exact DK ID in slot order, the engine's own lineup arithmetic) or a portfolio record's
own per-Entry-ID figure, taken as stated. It never recomputes a person's prior and never writes a number a source lacks.

Missing evidence is a named null: no prior source, a person the dump does not score, an entries file with no player table,
and, without a run folder, everything one supplies (run ID, method, policy, thesis, market numbers). Since Session 72b a run's
output folder (`run_dir`) and run-data folder (`run_data`) supply them: the method by bytes, the run's own stage and rung, the
final policy's hash and each Entry ID's thesis when the file comes from the review selection, and the stack game's market
numbers only through the run's source ledger, validated at the run's own clock. Paths the run recorded are absolute paths on
its own machine, so each is found again under the supplied folder, never read as it stands. Bad bytes are refused whole by
name (`EntryRecordRefused`, registry family `entry_record`). The structure counts come from the Session 23 rule
(`portfolio_policy.structure_counts`) and the Classic stack rule (`classic_portfolio.stack_value`). The salary file's
average-points column is never read: `SalaryPlayer` has no field for it.

The record states what was built and what the priors said. It certifies nothing and changes no release truth;
`MODEL_STATUS=PRIOR_ONLY` and `RELEASE_DECISION=DO_NOT_UPLOAD` stand.
"""

from __future__ import annotations

import copy
import csv
import io
import json
import math
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from . import delivery, entry_history
from .classic_portfolio import stack_value
from .contracts import EngineMode, SlateContract
from .dk import DraftKingsParseError, EntryTemplate, embedded_pool_ids, parse_entry_bytes, parse_salaries, reconcile_template
from .evidence import EvidenceError, validate_source_ledger
from .hashing import canonical_json_bytes, sha256_bytes
from .lineups import prefilled_cell_id, roster_canonical_key, validate_lineup
from .portfolio_policy import structure_counts
from .selection import POOL_SCORES_SCHEMA

SCHEMA_VERSION = "nfl_entry_build_record_v1"
NO_RUN_FOLDER = "RUN_FOLDER_NOT_SUPPLIED"
RUN_REPORT_NAME = "cowork_run.json"
WHICH_RUN = "WHICH_RUN_BUILT_THE_FILE"
_RUN_FIELDS = ("run_id", "method", "policy_sha256", "thesis")
_ATTEMPT_FOLDER = re.compile(r"prior_review(?:_attempt_[0-9]+)?")
_LOCKED = "(LOCKED)"
_MARKET_COLUMNS = (("total", "MARKET_TOTAL"), ("spread", "MARKET_SPREAD"))
DOES_NOT_ESTABLISH = (
    "EXPECTED_VALUE_OR_ROI",
    "WIN_OR_CASH_PROBABILITY",
    "AN_EDGE_OR_ITS_ABSENCE",
    "CALIBRATION",
    WHICH_RUN,
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


def _cell_id(cell: str) -> str | None:
    """A roster cell's exact DK ID: `prefilled_cell_id`'s forms, and DraftKings' late-swap `Name (ID) (LOCKED)` (Session 72b).

    One trailing `(LOCKED)` is stripped here only. The governed late swap and the byte audit read `prefilled_cell_id` (V13)
    and keep refusing the suffix.
    """

    value = cell.strip()
    if value.endswith(_LOCKED):
        value = value[: -len(_LOCKED)]
    return prefilled_cell_id(value)


def _folder_json(raw: bytes, label: str) -> dict[str, object]:
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise EntryRecordRefused("ENTRY_RECORD_RUN_FOLDER_INVALID", f"{label}: {type(exc).__name__}: {exc}") from None
    if not isinstance(document, dict):
        raise EntryRecordRefused("ENTRY_RECORD_RUN_FOLDER_INVALID", f"{label} is not a JSON object")
    return document


def _block(document: dict[str, object], key: str) -> dict[str, object]:
    value = document.get(key)
    return value if isinstance(value, dict) else {}


def _rebase(recorded: object, run_id: str, root: Path) -> tuple[Path | None, str | None]:
    """A path the run recorded on its own machine, found again under `root`, or None and why.

    The tail after the last pair of segments (run ID, `prior_review` or `prior_review_attempt_<N>`) is joined to `root`:
    the absolute path is never read as it stands, and no attempt folder is guessed (the run's report names its last one).
    """

    if not isinstance(recorded, str):
        return None, "ARTIFACT_NOT_FOUND"
    parts = [part for part in recorded.replace("\\", "/").split("/") if part]
    anchors = [index for index in range(len(parts) - 1)
               if parts[index] == run_id and _ATTEMPT_FOLDER.fullmatch(parts[index + 1])]
    if not anchors or any(part == ".." or ":" in part for part in parts[anchors[-1] + 1:]):
        return None, "ARTIFACT_OUTSIDE_RUN_FOLDER"
    path = Path(root).joinpath(*parts[anchors[-1] + 1:])
    return (path, None) if path.is_file() else (None, "ARTIFACT_NOT_FOUND")


def _market_number(text: str | None, label: str) -> float | None:
    value = (text or "").strip()
    if not value:
        return None
    try:
        number = float(Decimal(value))
    except (InvalidOperation, ValueError):
        number = math.nan
    if not math.isfinite(number):
        raise EntryRecordRefused("ENTRY_RECORD_SOURCE_LEDGER_INVALID", f"team_projections.csv {label} is {value!r}, not a number")
    return number


def _claim(from_review: bool, artifacts, hashes, run_id: str, data: Path, policy: str | None):
    """The run's own claim: (thesis by Entry ID, thesis by lineup key), or None and why."""

    if not from_review:
        return None, "FILE_NOT_FROM_THE_REVIEW_SELECTION"
    path, why = _rebase(artifacts.get("selection_report"), run_id, data)
    if path is None:
        return None, "SELECTION_REPORT_NOT_FOUND" if why == "ARTIFACT_NOT_FOUND" else why
    raw = path.read_bytes()
    if sha256_bytes(raw) != hashes.get("selection_report"):
        raise EntryRecordRefused(
            "ENTRY_RECORD_RUN_FOLDER_INVALID", f"selection_report.json's bytes are not the ones run {run_id} recorded")
    block = _block(_block(_folder_json(raw, "selection_report.json"), "selection"), "portfolio_policy")
    named = block.get("normalized_policy_sha256")
    if isinstance(named, str) and isinstance(policy, str) and named != policy:
        raise EntryRecordRefused(
            "ENTRY_RECORD_RUN_FOLDER_INVALID", f"the claim names policy {named}; run {run_id}'s final policy is {policy}")
    theses = _block(block, "theses")
    entries, by_lineup = theses.get("entries"), _block(theses, "by_lineup")
    if not isinstance(entries, dict):
        return None, "NO_THESIS_CLAIM"
    if not all(name is None or isinstance(name, str) for name in [*entries.values(), *by_lineup.values()]):
        raise EntryRecordRefused("ENTRY_RECORD_RUN_FOLDER_INVALID", "the claim's theses are not names")
    return (entries, by_lineup), None


def _theses(claim, rosters: dict[str, tuple[str, ...] | None], slate: SlateContract) -> dict[str, tuple[str | None, str | None]]:
    """Each Entry ID's (thesis, reason), read from the run's claim and never inferred from what a roster holds.

    The claim of record is `by_lineup`, keyed by the exact roster (Sessions 23c and 67): a lineup exactly as the run built
    it carries that thesis wherever the contest pass moved it. `entries` is its readable form by Entry ID, which an edited
    row keeps (the hand passes keep each row's thesis, Session 66), unless a lineup the run built sits under another Entry
    ID than `entries` gives it: then Entry IDs were reassigned and an edited row's thesis is unknown. Session 66's check
    refuses such a file outright; the record names each row instead.
    """

    entries, by_lineup = claim
    keys = {entry: roster_canonical_key(slate, roster) for entry, roster in rosters.items() if roster is not None}
    moved = any(key in by_lineup and by_lineup[key] != entries.get(entry) for entry, key in keys.items())
    result: dict[str, tuple[str | None, str | None]] = {}
    for entry in rosters:
        key = keys.get(entry)
        if key is not None and key in by_lineup:
            name = by_lineup[key]
        elif key is not None and moved:
            result[entry] = (None, "LINEUPS_MOVED_BETWEEN_ENTRY_IDS")
            continue
        else:
            name = entries.get(entry)
        result[entry] = (name, None) if name is not None else (None, "ENTRY_ID_HAS_NO_THESIS")
    return result


def _markets(artifacts, hashes, reports, run_id: str, data: Path, slate: SlateContract):
    """Each game's market numbers from the run's ledger-bound `team_projections.csv`, or None and why."""

    ledger, why = _rebase(artifacts.get("source_ledger"), run_id, data)
    if ledger is None:
        return None, "SOURCE_LEDGER_NOT_FOUND" if why == "ARTIFACT_NOT_FOUND" else why
    derived: dict[str, bytes] = {}
    for name in ("team_projections", "player_opportunities"):
        path, why = _rebase(artifacts.get(name), run_id, data)
        if path is None:
            return None, why
        derived[name] = path.read_bytes()
    try:
        clock = datetime.fromisoformat(str(_block(reports, "projection").get("replay_clock")))
    except ValueError:
        clock = None
    if clock is None or clock.tzinfo is None:
        return None, "RUN_CLOCK_NOT_RECORDED"
    if sha256_bytes(ledger.read_bytes()) != hashes.get("projected:source_ledger"):
        raise EntryRecordRefused(
            "ENTRY_RECORD_SOURCE_LEDGER_INVALID", f"source_ledger.json's bytes are not the ones run {run_id} recorded")
    try:
        validate_source_ledger(ledger, expected_outputs={name: sha256_bytes(raw) for name, raw in derived.items()},
                               now=clock)
    except EvidenceError as exc:
        raise EntryRecordRefused("ENTRY_RECORD_SOURCE_LEDGER_INVALID", f"at the run's clock {clock.isoformat()}: {exc}") from None
    reader = csv.DictReader(io.StringIO(derived["team_projections"].decode("utf-8-sig"), newline=""))
    if not {"TEAM", "GAME_ID", "MARKET_TOTAL", "MARKET_SPREAD"} <= set(reader.fieldnames or ()):
        raise EntryRecordRefused("ENTRY_RECORD_SOURCE_LEDGER_INVALID", "team_projections.csv has no TEAM, GAME_ID and market columns")
    rows: dict[tuple[str, str], dict[str, str]] = {}
    for row in reader:
        key = (row["TEAM"], row["GAME_ID"])
        if key in rows:
            raise EntryRecordRefused("ENTRY_RECORD_SOURCE_LEDGER_INVALID", f"team_projections.csv repeats {key[0]} in {key[1]}")
        rows[key] = row
    markets: dict[str, dict[str, object]] = {}
    for game in slate.games:
        market: dict[str, object] = {}
        for team in (game.away_team, game.home_team):
            row = rows.get((team, game.game_id))
            if row is None:
                market[team] = {"total": None, "spread": None,
                                "reasons": dict.fromkeys(("total", "spread"), "TEAM_NOT_IN_TEAM_PROJECTIONS")}
                continue
            numbers = {field: _market_number(row[column], f"{team} {column}") for field, column in _MARKET_COLUMNS}
            market[team] = {**numbers, "reasons": {field: "MARKET_VALUE_BLANK" for field, value in numbers.items() if value is None}}
        markets[game.game_id] = market
    return markets, None


def _run_folder(run_dir, run_data, *, salary_sha256: str, entries_sha256: str, file_sha256: str,
                slate: SlateContract, rosters: dict[str, tuple[str, ...] | None]) -> dict[str, object] | None:
    """What the supplied run folders say about the delivered file, read once per record; None without a run folder."""

    if run_dir is None:
        if run_data is not None:
            raise EntryRecordRefused("ENTRY_RECORD_RUN_FOLDER_INVALID", "a run-data folder needs its output folder (run_dir)")
        return None
    for label, folder in (("run_dir", run_dir), ("run_data", run_data)):
        if folder is not None and not Path(folder).is_dir():
            raise EntryRecordRefused("ENTRY_RECORD_RUN_FOLDER_INVALID", f"{label} {folder} is not a folder")
    out = Path(run_dir)
    if not (out / RUN_REPORT_NAME).is_file():
        return {"missing": "RUN_REPORT_NOT_FOUND"}
    report = _folder_json((out / RUN_REPORT_NAME).read_bytes(), RUN_REPORT_NAME)
    run_id = report.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise EntryRecordRefused("ENTRY_RECORD_RUN_FOLDER_INVALID", f"{RUN_REPORT_NAME} names no run ID")
    read = {digest for digest in _block(report, "input_hashes").values() if isinstance(digest, str)}
    for label, digest in (("salaries", salary_sha256), ("entries", entries_sha256)):
        if digest not in read:
            raise EntryRecordRefused("ENTRY_RECORD_RUN_INPUTS_DIFFER", f"run {run_id}'s intake never read these {label} ({digest})")
    try:
        loaded = delivery.read_pointer(out)
    except (delivery.DeliveryPointerError, OSError) as exc:
        raise EntryRecordRefused("ENTRY_RECORD_RUN_FOLDER_INVALID", f"{delivery.POINTER_NAME}: {exc}") from None
    pointer, pointer_file = None, None
    if loaded is not None:
        record, pointer = loaded
        if pointer.run_id != run_id:
            raise EntryRecordRefused(
                "ENTRY_RECORD_RUN_FOLDER_INVALID", f"the pointer names run {pointer.run_id}, the report run {run_id}")
        for label, digest, named in (("salaries", salary_sha256, pointer.salary_sha256),
                                     ("entries", entries_sha256, pointer.entry_sha256)):
            if named != digest:
                raise EntryRecordRefused(
                    "ENTRY_RECORD_RUN_INPUTS_DIFFER", f"the pointer's {label} SHA-256 is {named}, the supplied file's {digest}")
        pointer_file = str(_block(record, "file").get("path"))

    # The method, by bytes: a CSV in the output folder counts only when its bytes are an output the run recorded writing,
    # so an in-place edit of the run's own file reads as the operator's.
    review = report.get("bulk_entry_sha256") if isinstance(report.get("bulk_entry_sha256"), str) else None
    written = {digest for digest in (pointer.sha256 if pointer is not None else None, review,
                                     _block(report, "baseline").get("sha256")) if isinstance(digest, str)}
    matches: list[str] = []
    if file_sha256 in written:
        matches = sorted(path.relative_to(out).as_posix() for path in out.rglob("*.csv")
                         if path.is_file() and sha256_bytes(path.read_bytes()) == file_sha256)
        if not matches:
            raise EntryRecordRefused(
                "ENTRY_RECORD_RUN_FOLDER_INVALID", f"run {run_id} recorded writing this file and its folder no longer holds it")
    # The rung, the policy and the theses describe the review's selection: they fill for its own file, or for an
    # operator's file after a run whose pointer names it (the hand passes start from it), never for the baseline.
    from_review = review is not None and (file_sha256 == review if matches else pointer is not None and pointer.sha256 == review)
    relaxation = report.get("relaxation") if isinstance(report.get("relaxation"), dict) else None
    stage = report.get("stage") if isinstance(report.get("stage"), str) else None
    rung = relaxation.get("final_rung") if relaxation is not None and isinstance(relaxation.get("final_rung"), str) else None
    reasons: dict[str, str] = {}
    if stage is None:
        reasons["method.stage"] = "STAGE_NOT_RECORDED"
    if not from_review:
        rung = None
        reasons["method.final_rung"] = "FILE_NOT_FROM_THE_REVIEW_SELECTION"
    elif rung is None:
        reasons["method.final_rung"] = "RELAXATION_NOT_RECORDED"
    if matches:
        run_file = pointer_file if pointer_file in matches else matches[0]
        producer = pointer.producer if pointer is not None and run_file == pointer_file else None
        if producer is None:
            reasons["method.producer"] = "DELIVERY_POINTER_NOT_FOUND" if pointer is None else "FILE_IS_NOT_THE_POINTER_FILE"
        method = {"kind": "ENGINE_FILE", "stage": stage, "final_rung": rung, "producer": producer, "run_file": run_file}
    else:
        method = {"kind": "OPERATOR_FILE", "stage": stage, "final_rung": rung, "producer": None, "run_file": None}
        reasons["method.producer"] = reasons["method.run_file"] = "NO_RUN_FILE_MATCHES"

    final = relaxation.get("final_policy") if relaxation is not None else None
    policy, why = None, None
    if not from_review:
        why = "FILE_NOT_FROM_THE_REVIEW_SELECTION"
    elif relaxation is None:
        why = "RELAXATION_NOT_RECORDED"
    elif final is None:
        why = "NO_POLICY_AT_FINAL_RUNG"
    elif not isinstance(final, dict) or not isinstance(final.get("normalized_sha256"), str):
        why = "POLICY_HASH_NOT_RECORDED"
    else:
        policy = final["normalized_sha256"]
    if why is not None:
        reasons["policy_sha256"] = why
    state: dict[str, object] = {"run_id": run_id, "method": method, "policy_sha256": policy, "reasons": reasons}
    if run_data is None:
        return {**state, "theses": None, "thesis_reason": "RUN_DATA_NOT_SUPPLIED", "markets": None,
                "market_reason": "RUN_DATA_NOT_SUPPLIED"}
    data = Path(run_data)
    artifacts, hashes = _block(report, "prior_review_artifacts"), _block(report, "prior_review_hashes")
    claim, thesis_reason = _claim(from_review, artifacts, hashes, run_id, data, policy)
    theses = _theses(claim, rosters, slate) if claim is not None else None
    markets, market_reason = _markets(artifacts, hashes, _block(report, "prior_review_reports"), run_id, data, slate)
    return {**state, "theses": theses, "thesis_reason": thesis_reason, "markets": markets, "market_reason": market_reason}


def _run_row(state: dict[str, object] | None, entry_id: str) -> dict[str, object]:
    if state is None or "missing" in state:
        reason = NO_RUN_FOLDER if state is None else state["missing"]
        return {"run_id": None, "method": None, "policy_sha256": None, "thesis": None,
                "reasons": dict.fromkeys(_RUN_FIELDS, reason)}
    reasons = dict(state["reasons"])
    thesis, why = state["theses"][entry_id] if state["theses"] is not None else (None, state["thesis_reason"])
    if thesis is None:
        reasons["thesis"] = why
    return {"run_id": state["run_id"], "method": dict(state["method"]), "policy_sha256": state["policy_sha256"],
            "thesis": thesis, "reasons": reasons}


def _stack_game(state: dict[str, object] | None, game_id: str | None) -> dict[str, object]:
    if state is None or "missing" in state:
        return {"game_id": game_id, "market": None, "market_reason": NO_RUN_FOLDER if state is None else state["missing"]}
    if state["markets"] is None:
        return {"game_id": game_id, "market": None, "market_reason": state["market_reason"]}
    if game_id is None:
        return {"game_id": None, "market": None, "market_reason": "UNFILLED"}
    return {"game_id": game_id, "market": copy.deepcopy(state["markets"][game_id]), "market_reason": None}


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
            dk_id = _cell_id(cell)
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
    run_dir: str | Path | None = None,
    run_data: str | Path | None = None,
) -> list[dict[str, object]]:
    """One `nfl_entry_build_record_v1` row per Entry ID of the template, in template order, or a refusal by name.

    `run_dir` is a run's output folder (`outputs/<id>`) and `run_data` its run-data folder (`data/runs/<id>`); without
    them every run field and market number is null, `RUN_FOLDER_NOT_SUPPLIED`.
    """

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
    state = _run_folder(run_dir, run_data, salary_sha256=hashes["salary_sha256"], entries_sha256=hashes["entries_sha256"],
                        file_sha256=hashes["file_sha256"], slate=slate, rosters=rosters)
    # Only the run's own file establishes which run built it; an operator's file binds to the supplied run by hashes alone.
    named = state is not None and "missing" not in state and state["method"]["kind"] == "ENGINE_FILE"

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
            "run": _run_row(state, entry.entry_id),
            "rank": None,
            "does_not_establish": [item for item in DOES_NOT_ESTABLISH if not (named and item == WHICH_RUN)],
        }
        prior = {"points": None, "score_version": version, "source": kind, "unscored_dk_ids": [],
                 "excluded_dk_ids_rostered": [], "reason": None}
        if roster is None:
            prior["reason"] = "UNFILLED"
            rows.append({**row, "roster": None, "captain_dk_id": None, "prior": prior, "salary_left": None,
                         "structure": None, "dk_status": None, "later_window_count": None,
                         "stack_game": _stack_game(state, None)})
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
            "stack_game": _stack_game(state, game),
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
