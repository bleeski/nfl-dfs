"""The results join (Session 73, `nfl_results_join_v1` and `nfl_entry_results_v1`).

Session 69's entry history (`nfl_dk_entry_history_v1`) joined to Session 72's build records (`nfl_entry_build_record_v1`)
on exact Entry ID. Every Entry ID gets a class: joined, a locked blank with or without a record, entered with no record,
recorded but not in the export, or a row whose contest or game type disagrees with its record. A gap is a named class and
never stops the join; a malformed input is refused whole by name. The realized points are the export's own `Points`.

Each slate's prior points are ranked against those points (`player_grading.spearman`, tied ranks averaged) over every
joined row with a prior and over paid rows alone, and pooled as the unweighted mean of the slate figures. It is
descriptive: a slate's rows share most of their people, so it carries no p-value.

The report is written once under the gitignored results root. Each slate's results are written once beside its record and
are tracked, so they carry place, field size, points and percentile only, never a fee or a winning. A later export that
agrees with a slate's file confirms it; one that disagrees is named for that slate and never overwrites it. Nothing here
reaches a run, a selection or a release truth.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from . import entry_history
from .contest_facts import canonical_bytes
from .entry_history import CONTRACT_VERSION as HISTORY_CONTRACT
from .entry_history import EntryHistory, EntryHistoryRefused, HistoryRow, _problem
from .hashing import sha256_bytes
from .player_grading import spearman
from .results_report import _fixed, _snapshot, finishing_percentile, is_blank, slate_key

CONTRACT_VERSION = "nfl_results_join_v1"
RESULTS_VERSION = "nfl_entry_results_v1"
RECORD_VERSION = "nfl_entry_build_record_v1"
# A fix that changes a written byte takes a new writer version, so a file already on disk is never contradicted.
WRITER = "w1"
REPORT_NAME = f"results_join.{WRITER}.json"
RESULTS_NAME = f"entry_results.{WRITER}.json"
RECORD_NAME = "entry_build_record.jsonl"
DEFAULT_SLATES_DIR = Path(__file__).resolve().parents[2] / "data" / "inbox" / "slates"
CLASSES = ("JOINED", "LOCKED_BLANK_WITH_FILE", "LOCKED_BLANK_NO_RECORD", "ENTERED_NO_RECORD",
           "RECORDED_NOT_IN_HISTORY", "ROW_DISAGREES")
# Why each class was given: data, not gate codes (a holder-shaped name would make the registry scan read them as codes).
CAUSES = ("RECORD_ROW_FILLED", "RECORD_ROW_UNFILLED", "NO_RECORD_ON_SLATE", "SLATE_RECORD_LACKS_ENTRY_ID",
          "NOT_IN_EXPORT", "CONTEST", "GAME_TYPE")
STATES = ("WRITTEN", "ALREADY_PRESENT", "CONFIRMED_BY_EXPORT", "NOT_IN_EXPORT", "REFUSED", "WRITE_FAILED",
          "NOT_ATTEMPTED")
# The codes this module names; each is emitted as a full literal below (the gate registry scan reads them).
JOIN_CODES = (
    "RESULTS_JOIN_INPUT_INVALID",
    "RESULTS_JOIN_SNAPSHOT_INVALID",
    "RESULTS_JOIN_RECORD_INVALID",
    "RESULTS_JOIN_RESULTS_DIFFER",
    "RESULTS_JOIN_ARTIFACT_CONFLICT",
    "RESULTS_JOIN_WRITE_FAILED",
)
DOES_NOT_ESTABLISH = (
    "EXPECTED_VALUE_OR_ROI",
    "WIN_OR_CASH_PROBABILITY",
    "AN_EDGE_OR_ITS_ABSENCE",
    "CALIBRATION",
    "WHICH_ENTRIES_THE_ENGINE_BUILT",
    "UPLOAD_CLEARANCE",
)
ARTIFACT_RECOVERY = (
    "Another file holds this name and is never overwritten: check it, delete it by hand if it is a damaged copy and rerun"
    " the join. A fix that changes a written byte takes a new writer version instead."
)
RESULTS_RECOVERY = (
    "This slate's results file came from an earlier export whose results for these Entry IDs differ, usually one taken"
    " before every contest settled. It is never overwritten: compare the two exports, delete the file by hand in a pull"
    " request if the earlier one was not final, and rerun the join."
)
_GAME_TYPE_PREFIX = {"SHOWDOWN": "Showdown", "CLASSIC": "Classic"}
_SHA256 = re.compile(r"[0-9a-f]{64}")
_DIGITS = re.compile(r"[1-9][0-9]{0,17}")


class ResultsJoinRefused(ValueError):
    """The records were refused whole, by a code in the registry's `results_join` family."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}:{detail}")
        self.code, self.detail = code, detail


@dataclass(frozen=True)
class SlateRecord:
    slate: str
    sha256: str
    rows: tuple[dict, ...]


@dataclass(frozen=True)
class Records:
    slates: tuple[SlateRecord, ...]
    alternates: tuple[str, ...]


# ------------------------------------------------------------------------------------------ the records


def _no_constant(text: str) -> None:
    raise ValueError(text)  # json's NaN and Infinity


def _record_rows(raw: bytes, label: str) -> tuple[dict, ...]:
    """One record's rows, or a refusal naming the line. Only the fields the join reads are checked."""

    if not raw.endswith(b"\n"):
        raise ResultsJoinRefused("RESULTS_JOIN_RECORD_INVALID", f"{label}:{'empty' if not raw else 'unterminated'}")
    rows: list[dict] = []
    seen: set[str] = set()
    for number, line in enumerate(raw[:-1].split(b"\n"), start=1):
        where = f"{label}:line={number}"
        try:
            row = json.loads(line, parse_constant=_no_constant)
            values = (row["schema_version"], row["entry_id"], row["contest_id"], row["mode"], row["roster"],
                      row["prior"]["points"], row["prior"]["reason"])
        except (ValueError, KeyError, TypeError):
            raise ResultsJoinRefused("RESULTS_JOIN_RECORD_INVALID", f"{where}:unreadable") from None
        version, entry_id, contest_id, mode, roster, points, why = values
        number_ok = points is None or (isinstance(points, (int, float)) and not isinstance(points, bool)
                                       and math.isfinite(points))
        checks = (("schema_version", version == RECORD_VERSION),
                  ("entry_id", isinstance(entry_id, str) and bool(_DIGITS.fullmatch(entry_id))),
                  ("contest_id", isinstance(contest_id, str) and bool(_DIGITS.fullmatch(contest_id))),
                  ("mode", mode in _GAME_TYPE_PREFIX), ("roster", roster is None or isinstance(roster, list)),
                  ("prior", number_ok and (why is None or isinstance(why, str))),
                  ("entry_id_repeated", entry_id not in seen))
        for field, ok in checks:
            if not ok:
                raise ResultsJoinRefused("RESULTS_JOIN_RECORD_INVALID", f"{where}:{field}")
        seen.add(entry_id)
        rows.append(row)
    return tuple(rows)


def load_records(slates_root: str | Path) -> Records:
    """Each slate folder's graded record (`construction/entry_build_record.jsonl`), in folder order.

    An earlier delivered file's record (`entry_build_record.<stem>.jsonl`) is listed, never joined. An Entry ID in two
    folders' records is refused: the join could not say which slate it belongs to.
    """

    slates: list[SlateRecord] = []
    alternates: list[str] = []
    owner: dict[str, str] = {}
    for folder in sorted(path for path in Path(slates_root).iterdir() if path.is_dir()):
        construction = folder / "construction"
        alternates += [f"{folder.name}/construction/{path.name}"
                       for path in sorted(construction.glob("entry_build_record*.jsonl")) if path.name != RECORD_NAME]
        path = construction / RECORD_NAME
        if not path.is_file():
            continue
        raw = path.read_bytes()
        rows = _record_rows(raw, f"{folder.name}/construction/{RECORD_NAME}")
        for row in rows:
            first = owner.setdefault(row["entry_id"], folder.name)
            if first != folder.name:
                raise ResultsJoinRefused("RESULTS_JOIN_RECORD_INVALID",
                                         f"entry_id={row['entry_id']}:slates={first},{folder.name}")
        slates.append(SlateRecord(folder.name, sha256_bytes(raw), rows))
    return Records(tuple(slates), tuple(alternates))


# --------------------------------------------------------------------------------------------- the join


def _record_class(row: dict, found: HistoryRow | None) -> tuple[str, str | None]:
    if found is None:
        return "RECORDED_NOT_IN_HISTORY", "NOT_IN_EXPORT"
    if found.contest_key != row["contest_id"]:
        return "ROW_DISAGREES", "CONTEST"
    if not found.game_type.startswith(_GAME_TYPE_PREFIX[row["mode"]]):
        return "ROW_DISAGREES", "GAME_TYPE"
    if is_blank(found.points_hundredths):
        return "LOCKED_BLANK_WITH_FILE", "RECORD_ROW_FILLED" if row["roster"] is not None else "RECORD_ROW_UNFILLED"
    return "JOINED", None


def _item(entry_id: str, contest_id: str, slate: str | None, kind: str, why: str | None,
          found: HistoryRow | None) -> dict:
    _sport, date, game_type = slate_key(found) if found is not None else (None, None, None)
    return {"entry_id": entry_id, "contest_id": contest_id, "slate": slate, "class": kind, "reason": why,
            "date": date, "game_type": game_type}


def _rho(pairs: list[tuple[float, int]]) -> dict:
    rho, note = spearman([prior for prior, _ in pairs], [points for _, points in pairs])
    return {"n": len(pairs), "rho": rho, "note": note}


def _pooled(checks: list[dict], population: str) -> dict:
    defined = [check[population] for check in checks if check[population]["rho"] is not None]
    mean = round(sum(item["rho"] for item in defined) / len(defined), 6) if defined else None
    return {"slates": len(defined), "rows": sum(item["n"] for item in defined), "mean_rho": mean}


def build_join(history: EntryHistory, records: Records, *, source_sha256: str) -> tuple[dict, dict[str, dict]]:
    """The report and each slate's results payload (only slates with an Entry ID in the export). No I/O."""

    nfl = {row.entry_key: row for row in history.nfl_rows}
    recorded = {row["entry_id"] for slate in records.slates for row in slate.rows}
    entries: list[dict] = []
    checks: list[dict] = []
    results: dict[str, dict] = {}
    covered: set[tuple[str, str, str]] = set()  # the history slates a record row joined
    for slate in records.slates:
        pairs: dict[str, list[tuple[float, int]]] = {"all": [], "paid": []}
        excluded: Counter[str] = Counter()
        lines: list[dict] = []
        for row in slate.rows:
            found = nfl.get(row["entry_id"])
            kind, why = _record_class(row, found)
            entries.append(_item(row["entry_id"], row["contest_id"], slate.slate, kind, why, found))
            bound = found if kind in ("JOINED", "LOCKED_BLANK_WITH_FILE") else None
            lines.append({
                "entry_id": row["entry_id"], "class": kind,
                "place": bound.place if bound else None,
                "contest_entries": bound.contest_entries if bound else None,
                "points_hundredths": bound.points_hundredths if bound else None,
                "percentile": _fixed(finishing_percentile(bound.place, bound.contest_entries) * 100) if bound else None,
            })
            if found is not None:
                covered.add(slate_key(found))
            points = row["prior"]["points"]
            if kind != "JOINED":
                excluded[kind] += 1
            elif points is None:
                excluded[row["prior"]["reason"] or "PRIOR_NULL"] += 1
            else:
                pairs["all"].append((points, found.points_hundredths))
                if found.entry_fee_cents > 0:
                    pairs["paid"].append((points, found.points_hundredths))
        if all(line["class"] == "RECORDED_NOT_IN_HISTORY" for line in lines):
            continue
        checks.append({"slate": slate.slate, "record_sha256": slate.sha256, "all": _rho(pairs["all"]),
                       "paid": _rho(pairs["paid"]), "excluded": dict(sorted(excluded.items()))})
        results[slate.slate] = {
            "schema_version": RESULTS_VERSION, "writer": WRITER, "contract": CONTRACT_VERSION,
            "source_sha256": source_sha256, "slate": slate.slate, "record_name": RECORD_NAME, "entries": lines,
            "does_not_establish": list(DOES_NOT_ESTABLISH),
        }
    for row in history.nfl_rows:
        if row.entry_key not in recorded:
            kind = "LOCKED_BLANK_NO_RECORD" if is_blank(row.points_hundredths) else "ENTERED_NO_RECORD"
            why = "SLATE_RECORD_LACKS_ENTRY_ID" if slate_key(row) in covered else "NO_RECORD_ON_SLATE"
            entries.append(_item(row.entry_key, row.contest_key, None, kind, why, row))
    counts = Counter(item["class"] for item in entries)
    report = {
        "schema_version": CONTRACT_VERSION, "writer": WRITER, "history_contract": HISTORY_CONTRACT,
        "source_sha256": source_sha256,
        "records": [{"slate": slate.slate, "record_name": RECORD_NAME, "record_sha256": slate.sha256,
                     "rows": len(slate.rows)} for slate in records.slates],
        "alternate_records": list(records.alternates),
        "not_in_export": [slate.slate for slate in records.slates if slate.slate not in results],
        "non_nfl_rows_ignored": len(history.rows) - len(history.nfl_rows),
        "entries": entries,
        "class_counts": {kind: counts[kind] for kind in CLASSES},
        "rank_check": {"method": "SPEARMAN_TIED_RANKS_AVERAGED", "unit": "SLATE", "slates": checks,
                       "pooled": {"all": _pooled(checks, "all"), "paid": _pooled(checks, "paid")}},
        "does_not_establish": list(DOES_NOT_ESTABLISH),
    }
    return report, results


def headline(report: dict) -> dict:
    """What stdout carries: counts, correlations, classes and the blanks. No money."""

    return {
        "rank_check": [{"slate": check["slate"], "all_n": check["all"]["n"], "all_rho": check["all"]["rho"],
                        "paid_n": check["paid"]["n"], "paid_rho": check["paid"]["rho"]}
                       for check in report["rank_check"]["slates"]],
        "pooled": report["rank_check"]["pooled"],
        "class_counts": report["class_counts"],
        "blanks": [{key: item[key] for key in ("entry_id", "class", "reason", "date")}
                   for item in report["entries"] if item["class"].startswith("LOCKED_BLANK")],
        "not_in_export": report["not_in_export"],
        "alternate_records": report["alternate_records"],
    }


# ----------------------------------------------------------------------------------------------- writing


@dataclass(frozen=True)
class JoinOutcome:
    """`COMPLETE` and `ALREADY_PRESENT` exit 0; `REFUSED` and `WRITE_FAILED` exit 2. Every file reports a state."""

    status: str
    problems: tuple[str, ...]
    files: dict
    source_sha256: str | None = None
    headline: dict | None = None

    @property
    def exit_code(self) -> int:
        return 0 if self.status in ("COMPLETE", "ALREADY_PRESENT") else 2

    def as_dict(self) -> dict[str, object]:
        return {"status": self.status, "exit_code": self.exit_code, "problems": list(self.problems),
                "contract": CONTRACT_VERSION, "source_sha256": self.source_sha256, "files": self.files,
                "headline": self.headline, "does_not_establish": list(DOES_NOT_ESTABLISH)}


def _earlier(path: Path) -> tuple[bytes | None, object]:
    if path.is_symlink() or not path.is_file():
        return None, None
    try:
        raw = path.read_bytes()
        return raw, json.loads(raw)
    except (OSError, ValueError):
        return None, None


def _write(path: Path, payload: dict, name: str, problems: list[str], *, confirm: bool) -> dict:
    """Write once. With `confirm`, a file another export wrote with the same entries is that export's, kept as it is."""

    data = canonical_bytes(payload)
    out: dict[str, str | None] = {"path": str(path), "state": None, "sha256": None}
    try:
        out["state"] = entry_history._write_once(
            path, data, code="RESULTS_JOIN_ARTIFACT_CONFLICT", recovery=ARTIFACT_RECOVERY)
        out["sha256"] = sha256_bytes(data)
        return out
    except entry_history._Stop:
        pass
    except OSError as exc:
        out["state"] = "WRITE_FAILED"
        problems.append(_problem("RESULTS_JOIN_WRITE_FAILED", f"file={name}:exception={type(exc).__name__}"))
        return out
    raw, earlier = _earlier(path)
    same_kind = confirm and isinstance(earlier, dict) and all(
        earlier.get(key) == payload[key] for key in ("schema_version", "writer", "slate", "record_name"))
    if same_kind and earlier.get("entries") == payload["entries"]:
        out.update(state="CONFIRMED_BY_EXPORT", sha256=sha256_bytes(raw))
    elif same_kind:
        out.update(state="REFUSED", recovery=RESULTS_RECOVERY)
        problems.append(_problem("RESULTS_JOIN_RESULTS_DIFFER", f"file={name}"))
    else:
        out.update(state="REFUSED", recovery=ARTIFACT_RECOVERY)
        problems.append(_problem("RESULTS_JOIN_ARTIFACT_CONFLICT", f"file={name}"))
    return out


def run_results_join(source_sha256: str, results_root: str | Path,
                     slates_root: str | Path = DEFAULT_SLATES_DIR) -> JoinOutcome:
    """Read one kept snapshot and every slate's record, join them, and write the report, then each slate's results.

    A refused input writes nothing. Every file is attempted and reports its own state, so one conflict never stops the
    folders after it.
    """

    files: dict = {"report": {"path": None, "state": "NOT_ATTEMPTED", "sha256": None}, "slates": {}}
    if not isinstance(source_sha256, str) or not _SHA256.fullmatch(source_sha256):
        return JoinOutcome("REFUSED", (_problem("RESULTS_JOIN_INPUT_INVALID", "field=source_sha256"),), files)
    slates = Path(slates_root)
    if not slates.is_dir():
        return JoinOutcome("REFUSED", (_problem("RESULTS_JOIN_INPUT_INVALID", "field=slates_root"),), files,
                           source_sha256)
    root = Path(results_root)
    raw, why = _snapshot(root / "inbox" / f"{source_sha256}.csv", source_sha256)
    if why is not None:
        return JoinOutcome("REFUSED", (_problem("RESULTS_JOIN_SNAPSHOT_INVALID", f"reason={why}"),), files,
                           source_sha256)
    try:
        history = entry_history.parse_entry_history(raw)
        records = load_records(slates)
    except EntryHistoryRefused as refusal:  # a snapshot the parser no longer takes: its own codes, unchanged
        return JoinOutcome("REFUSED", refusal.problems, files, source_sha256)
    except ResultsJoinRefused as refusal:
        return JoinOutcome("REFUSED", (str(refusal),), files, source_sha256)
    report, results = build_join(history, records, source_sha256=source_sha256)
    problems: list[str] = []
    files["report"] = _write(root / "reports" / source_sha256 / REPORT_NAME, report, "report", problems,
                             confirm=False)
    for slate in records.slates:
        if slate.slate in results:
            files["slates"][slate.slate] = _write(slates / slate.slate / "construction" / RESULTS_NAME,
                                                  results[slate.slate], slate.slate, problems, confirm=True)
        else:
            files["slates"][slate.slate] = {"path": None, "state": "NOT_IN_EXPORT", "sha256": None}
    states = [files["report"]["state"], *(entry["state"] for entry in files["slates"].values())]
    status = ("REFUSED" if "REFUSED" in states else "WRITE_FAILED" if "WRITE_FAILED" in states
              else "COMPLETE" if "WRITTEN" in states else "ALREADY_PRESENT")
    return JoinOutcome(status, tuple(problems), files, source_sha256, headline(report))


__all__ = [
    "CLASSES",
    "CONTRACT_VERSION",
    "DEFAULT_SLATES_DIR",
    "JOIN_CODES",
    "JoinOutcome",
    "CAUSES",
    "RECORD_NAME",
    "RESULTS_NAME",
    "RESULTS_VERSION",
    "Records",
    "ResultsJoinRefused",
    "STATES",
    "SlateRecord",
    "build_join",
    "headline",
    "load_records",
    "run_results_join",
]
