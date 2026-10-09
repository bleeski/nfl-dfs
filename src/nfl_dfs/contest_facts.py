"""Contest facts and the first-place label (Session 23d, `nfl_contest_facts_v1`).

An operator supplies, from the DraftKings lobby by hand, four numbers per contest: its id, its field size, its
places paid and its entry fee. This module reads that file strictly, divides places paid by field size per
contest, and tags each reserved entry (through its Contest ID) with that paid fraction. An entry whose contest
pays strictly under 5% is labelled `FIRST_PLACE_OBJECTIVE`.

The label is a fact about a contest, computed from supplied numbers only. It is never inferred from a contest
name (this module is never given one), it is not a forecast, and nothing reads it downstream: it moves no
lineup, no assignment and no gate. `does_not_establish`: expected value or ROI, win or cash probability, payout
shape or top prize, overlay or rake, ownership or duplication, that a contest is worth entering, that any
lineup suits a contest, upload clearance.

The file is refused whole, never repaired and never used in part: every bad row is named (`CONTEST_FACTS_*`,
with its row number, the header being row 1). A refused, partial or unreadable file never stops a run: the
caller records the named block and the limitations below, and the run goes on (R28).

`build_block` never raises. `review_block` is the review's recompute: it validates the block's own types and
ranges before any arithmetic, rebuilds it from the entry file's rows and the block's numbers, and answers every
failure it meets with exactly one registered `P` code, `CONTEST_FACTS_REVIEW_MISMATCH:<kind>`.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal
from fractions import Fraction
from pathlib import Path
from typing import Mapping, Sequence

CONTRACT_VERSION = "nfl_contest_facts_v1"
BLOCK_VERSION = "nfl_contest_facts_labels_v1"
LABEL_VERSION = "paid_fraction_under_five_percent_v1"
LABEL = "FIRST_PLACE_OBJECTIVE"
THRESHOLD = Fraction(1, 20)
THRESHOLD_RULE = "PLACES_PAID_TIMES_20_LESS_THAN_FIELD_SIZE"
HEADER = ("contest_id", "field_size", "places_paid", "entry_fee")
MAX_BYTES = 1_000_000
ARTIFACT_NAME = "contest_facts.json"

STATUS_NOT_SUPPLIED = "NOT_SUPPLIED"
STATUS_APPLIED = "APPLIED"
STATUS_PARTIAL = "PARTIAL"
STATUS_REFUSED = "REFUSED"
STATUSES = (STATUS_NOT_SUPPLIED, STATUS_APPLIED, STATUS_PARTIAL, STATUS_REFUSED)
STATE_SUPPLIED = "SUPPLIED"
STATE_NO_ROW = "NO_FACTS_ROW"
STATE_FEE_DISAGREES = "FEE_DISAGREES"

DOES_NOT_ESTABLISH = (
    "EXPECTED_VALUE_OR_ROI",
    "WIN_OR_CASH_PROBABILITY",
    "PAYOUT_SHAPE_OR_TOP_PRIZE",
    "OVERLAY_OR_RAKE",
    "OWNERSHIP_OR_DUPLICATION",
    "THAT_A_CONTEST_IS_WORTH_ENTERING",
    "THAT_ANY_LINEUP_SUITS_A_CONTEST",
    "UPLOAD_CLEARANCE",
)
MEANING = {
    STATUS_NOT_SUPPLIED: (
        "no contest facts file was supplied, so no entry is labelled; this does not say that no contest pays under 5%"
    ),
    STATUS_APPLIED: (
        "every entry's contest has a supplied row; a label is places paid divided by field size from the supplied"
        " numbers, a fact about the contest and never a forecast"
    ),
    STATUS_PARTIAL: (
        "some entries' contests have no usable row and carry no label; the rest are labelled from the supplied numbers"
    ),
    STATUS_REFUSED: "the supplied file was refused whole and no entry is labelled; the run went on without it",
}

# The codes a parser or a step names; each is emitted as a full literal below (the gate registry scan reads them).
PARSE_CODES = (
    "CONTEST_FACTS_FILE_EMPTY",
    "CONTEST_FACTS_FILE_TOO_LARGE",
    "CONTEST_FACTS_NOT_TEXT",
    "CONTEST_FACTS_HEADER_INVALID",
    "CONTEST_FACTS_NO_ROWS",
    "CONTEST_FACTS_ROW_MISSHAPEN",
    "CONTEST_FACTS_CONTEST_ID_INVALID",
    "CONTEST_FACTS_CONTEST_ID_DUPLICATE",
    "CONTEST_FACTS_FIELD_SIZE_INVALID",
    "CONTEST_FACTS_FIELD_SIZE_NOT_POSITIVE",
    "CONTEST_FACTS_PLACES_PAID_INVALID",
    "CONTEST_FACTS_PLACES_PAID_NOT_POSITIVE",
    "CONTEST_FACTS_PLACES_PAID_EXCEEDS_FIELD_SIZE",
    "CONTEST_FACTS_ENTRY_FEE_INVALID",
)
RUN_CODES = (
    "CONTEST_FACTS_UNREADABLE",
    "CONTEST_FACTS_STEP_FAILED",
    "CONTEST_FACTS_REFUSED",
    "CONTEST_FACTS_INCOMPLETE",
    "CONTEST_FACTS_FEE_DISAGREES_WITH_ENTRIES",
)

_CONTEST_ID = re.compile(r"[0-9]{1,18}")
_INTEGER = re.compile(r"-?[0-9]{1,12}")
_FEE = re.compile(r"\$?[0-9]{1,6}(?:\.[0-9]{1,2})?")
_HEX64 = re.compile(r"[0-9a-f]{64}")
_CENT = Decimal("0.01")
_SIX_PLACES = Decimal("0.000001")


class ContestFactsRefused(Exception):
    """The whole file is refused; `problems` names every bad row in file order."""

    def __init__(self, problems: Sequence[str]):
        super().__init__(";".join(problems))
        self.problems = tuple(problems)


@dataclass(frozen=True)
class FactRow:
    contest_id: str
    field_size: int
    places_paid: int
    fee_cents: int


def _problem(code: str, detail: str = "") -> str:
    return f"{code}:{detail}" if detail else code


def _mismatch(kind: str) -> str:
    return _problem("CONTEST_FACTS_REVIEW_MISMATCH", kind)


def sha256_hex(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical_bytes(block: Mapping[str, object]) -> bytes:
    """Sorted keys, compact separators, one trailing LF: what `prior_review` writes and hashes."""

    return (json.dumps(dict(block), sort_keys=True, separators=(",", ":"), default=str) + "\n").encode("utf-8")


# ------------------------------------------------------------------------------- the parser


def _integer(text: str) -> int | None:
    return int(text) if _INTEGER.fullmatch(text) else None


def _fee_cents(text: str) -> int | None:
    if not _FEE.fullmatch(text):
        return None
    return int((Decimal(text.lstrip("$")) * 100).to_integral_value(rounding=ROUND_HALF_EVEN))


def parse_contest_facts(raw: bytes) -> tuple[FactRow, ...]:
    """The rows of one facts file, or `ContestFactsRefused` naming every bad row. Never partial."""

    problems: list[str] = []
    if not raw:
        problems.append(_problem("CONTEST_FACTS_FILE_EMPTY"))
    elif len(raw) > MAX_BYTES:
        problems.append(_problem("CONTEST_FACTS_FILE_TOO_LARGE"))
    elif b"\x00" in raw:
        problems.append(_problem("CONTEST_FACTS_NOT_TEXT"))
    if problems:
        raise ContestFactsRefused(problems)
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ContestFactsRefused([_problem("CONTEST_FACTS_NOT_TEXT")]) from None
    try:
        records = list(csv.reader(io.StringIO(text, newline=""), strict=True))
    except csv.Error:
        raise ContestFactsRefused([_problem("CONTEST_FACTS_ROW_MISSHAPEN", "csv")]) from None
    numbered = [(number, cells) for number, cells in enumerate(records, start=1) if cells]
    if not numbered:
        raise ContestFactsRefused([_problem("CONTEST_FACTS_FILE_EMPTY")])
    if tuple(cell.strip() for cell in numbered[0][1]) != HEADER:
        raise ContestFactsRefused([_problem("CONTEST_FACTS_HEADER_INVALID")])
    body = numbered[1:]
    if not body:
        raise ContestFactsRefused([_problem("CONTEST_FACTS_NO_ROWS")])

    seen: dict[str, int] = {}
    rows: list[FactRow] = []
    for number, cells in body:
        where = f"row={number}"
        if len(cells) != len(HEADER):
            problems.append(_problem("CONTEST_FACTS_ROW_MISSHAPEN", where))
            continue
        contest_id, size_text, paid_text, fee_text = (cell.strip() for cell in cells)
        before = len(problems)
        if not _CONTEST_ID.fullmatch(contest_id):
            problems.append(_problem("CONTEST_FACTS_CONTEST_ID_INVALID", where))
        elif contest_id in seen:
            problems.append(_problem("CONTEST_FACTS_CONTEST_ID_DUPLICATE", f"{where}:first={seen[contest_id]}"))
        else:
            seen[contest_id] = number
        size = _integer(size_text)
        if size is None:
            problems.append(_problem("CONTEST_FACTS_FIELD_SIZE_INVALID", where))
        elif size <= 0:
            problems.append(_problem("CONTEST_FACTS_FIELD_SIZE_NOT_POSITIVE", where))
        paid = _integer(paid_text)
        if paid is None:
            problems.append(_problem("CONTEST_FACTS_PLACES_PAID_INVALID", where))
        elif paid <= 0:
            problems.append(_problem("CONTEST_FACTS_PLACES_PAID_NOT_POSITIVE", where))
        elif size is not None and 0 < size < paid:
            problems.append(_problem("CONTEST_FACTS_PLACES_PAID_EXCEEDS_FIELD_SIZE", where))
        cents = _fee_cents(fee_text)
        if cents is None:
            problems.append(_problem("CONTEST_FACTS_ENTRY_FEE_INVALID", where))
        if len(problems) == before and size is not None and paid is not None and cents is not None:
            rows.append(FactRow(contest_id, size, paid, cents))
    if problems:
        raise ContestFactsRefused(problems)
    return tuple(rows)


# --------------------------------------------------------------------------------- the label


def first_place_label(places_paid: int, field_size: int) -> str | None:
    """`FIRST_PLACE_OBJECTIVE` when places paid are strictly under 1/20 of the field, else None.

    Integer arithmetic on supplied numbers only: exactly 5% is not labelled, and no contest name is read.
    """

    return LABEL if places_paid * THRESHOLD.denominator < field_size * THRESHOLD.numerator else None


def _fraction_text(places_paid: int, field_size: int) -> str:
    fraction = Fraction(places_paid, field_size)
    return f"{fraction.numerator}/{fraction.denominator}"


def _decimal_text(places_paid: int, field_size: int) -> str:
    return str((Decimal(places_paid) / Decimal(field_size)).quantize(_SIX_PLACES, rounding=ROUND_HALF_EVEN))


# --------------------------------------------------------------------------------- the block


def _entry_refs(entries: object) -> list[tuple[str, str, int]] | None:
    """`(entry_id, contest_id, fee in cents)` for every entry, or None when a row cannot be read."""

    if isinstance(entries, (str, bytes)) or not isinstance(entries, Sequence):
        return None
    refs: list[tuple[str, str, int]] = []
    for row in entries:
        if isinstance(row, (str, bytes)) or not isinstance(row, Sequence) or len(row) != 3:
            return None
        entry_id, contest_id, fee = row
        if not isinstance(entry_id, str) or not isinstance(contest_id, str):
            return None
        if isinstance(fee, bool) or not isinstance(fee, (int, float)) or not math.isfinite(fee) or fee < 0:
            return None
        refs.append((entry_id, contest_id, int((Decimal(repr(float(fee))) / _CENT).to_integral_value(
            rounding=ROUND_HALF_EVEN))))
    return refs


def _base(status: str, *, sha: str | None, name: str | None) -> dict[str, object]:
    return {
        "schema_version": BLOCK_VERSION,
        "contract": CONTRACT_VERSION,
        "contest_facts_label_version": LABEL_VERSION,
        "label": LABEL,
        "threshold_paid_fraction": f"{THRESHOLD.numerator}/{THRESHOLD.denominator}",
        "threshold_rule": THRESHOLD_RULE,
        "does_not_establish": list(DOES_NOT_ESTABLISH),
        "status": status,
        "meaning": MEANING[status],
        "facts_file_name": name,
        "facts_sha256": sha,
        "facts_row_count": 0,
        "problems": [],
        "contests": [],
        "entries": [],
        "entries_labelled": 0,
        "contests_without_row": [],
        "contests_fee_disagree": [],
        "unused_contest_ids": [],
    }


def _unusable(status: str, problems: Sequence[str], *, sha: str | None, name: str | None) -> dict[str, object]:
    block = _base(status, sha=sha, name=name)
    block["problems"] = list(problems)
    return block


def _assemble(
    facts: Mapping[str, FactRow],
    unused: Sequence[str],
    refs: Sequence[tuple[str, str, int]],
    *,
    sha: str,
    name: str | None,
) -> dict[str, object]:
    """The labelled block from the entry file's rows and the supplied numbers; the review recomputes with it."""

    fees: dict[str, set[int]] = {}
    count: Counter[str] = Counter()
    for _entry_id, contest_id, cents in refs:
        fees.setdefault(contest_id, set()).add(cents)
        count[contest_id] += 1
    contests: list[dict[str, object]] = []
    state_of: dict[str, str] = {}
    for contest_id in sorted(fees):
        entry_fees = sorted(fees[contest_id])
        row = facts.get(contest_id)
        if row is None:
            state = STATE_NO_ROW
        else:
            state = STATE_SUPPLIED if entry_fees == [row.fee_cents] else STATE_FEE_DISAGREES
        state_of[contest_id] = state
        supplied = state == STATE_SUPPLIED
        contests.append({
            "contest_id": contest_id,
            "entry_count": count[contest_id],
            "facts_state": state,
            "field_size": None if row is None else row.field_size,
            "places_paid": None if row is None else row.places_paid,
            "facts_fee_cents": None if row is None else row.fee_cents,
            "entry_file_fee_cents": entry_fees,
            "paid_fraction": _fraction_text(row.places_paid, row.field_size) if supplied else None,
            "paid_fraction_decimal": _decimal_text(row.places_paid, row.field_size) if supplied else None,
            "label": first_place_label(row.places_paid, row.field_size) if supplied else None,
        })
    by_contest = {row["contest_id"]: row for row in contests}
    entries: list[dict[str, object]] = []
    for entry_id, contest_id, _cents in refs:
        row = by_contest[contest_id]
        entries.append({
            "entry_id": entry_id,
            "contest_id": contest_id,
            "facts_state": row["facts_state"],
            "label": row["label"],
            "paid_fraction": row["paid_fraction"],
            "paid_fraction_decimal": row["paid_fraction_decimal"],
        })
    without = [contest for contest in sorted(state_of) if state_of[contest] == STATE_NO_ROW]
    disagree = [contest for contest in sorted(state_of) if state_of[contest] == STATE_FEE_DISAGREES]
    complete = all(row["facts_state"] == STATE_SUPPLIED for row in entries)
    block = _base(STATUS_APPLIED if complete else STATUS_PARTIAL, sha=sha, name=name)
    block.update({
        "facts_row_count": len(facts) + len(unused),
        "contests": contests,
        "entries": entries,
        "entries_labelled": sum(1 for row in entries if row["label"]),
        "contests_without_row": without,
        "contests_fee_disagree": disagree,
        "unused_contest_ids": sorted(unused),
    })
    return block


def build_block(path: str | Path | None, entries: Sequence[tuple[str, str, float]]) -> dict[str, object]:
    """The run's block for one facts file over the template's `(entry_id, contest_id, entry_fee)` rows.

    Never raises. No file is `NOT_SUPPLIED`; a file that cannot be read or used is `REFUSED` with every problem
    named and no label written; otherwise the block is `APPLIED` or `PARTIAL`.
    """

    digest: str | None = None
    name: str | None = None
    try:
        if path is None:
            return _base(STATUS_NOT_SUPPLIED, sha=None, name=None)
        name = Path(path).name
        refs = _entry_refs(entries)
        if refs is None:
            raise ValueError("entries")
        try:
            raw = Path(path).read_bytes()
        except OSError:
            return _unusable(STATUS_REFUSED, [_problem("CONTEST_FACTS_UNREADABLE")], sha=None, name=name)
        digest = sha256_hex(raw)
        try:
            rows = parse_contest_facts(raw)
        except ContestFactsRefused as refused:
            return _unusable(STATUS_REFUSED, refused.problems, sha=digest, name=name)
        wanted = {contest_id for _entry_id, contest_id, _cents in refs}
        every = {row.contest_id: row for row in rows}
        return _assemble(
            {contest: row for contest, row in every.items() if contest in wanted},
            [contest for contest in every if contest not in wanted],
            refs,
            sha=digest,
            name=name,
        )
    except Exception as exc:  # noqa: BLE001 - a label step never stops a run (R28); the class name is the detail
        return _unusable(
            STATUS_REFUSED, [_problem("CONTEST_FACTS_STEP_FAILED", type(exc).__name__)], sha=digest, name=name)


def limitations(block: Mapping[str, object]) -> list[str]:
    """The named `P` limitations a run carries for one block; an applied block and an absent file carry none."""

    limitation_lines: list[str] = []
    if block.get("status") == STATUS_REFUSED:
        problems = [str(item) for item in (block.get("problems") or ())]
        first = problems[0].split(":", 1)[0] if problems else "CONTEST_FACTS_STEP_FAILED"
        limitation_lines.append(
            f"CONTEST_FACTS_REFUSED:{first}:{len(problems)} problem(s), the file was refused whole and no entry is labelled")
    missing = [str(item) for item in (block.get("contests_without_row") or ())]
    if missing:
        limitation_lines.append(
            f"CONTEST_FACTS_INCOMPLETE:{len(missing)} entry contest(s) have no facts row, so their entries carry no"
            f" label: {', '.join(missing)}")
    disagree = [str(item) for item in (block.get("contests_fee_disagree") or ())]
    if disagree:
        limitation_lines.append(
            f"CONTEST_FACTS_FEE_DISAGREES_WITH_ENTRIES:{len(disagree)} contest(s) whose facts row names another entry"
            f" fee than the entry file, so they carry no label: {', '.join(disagree)}")
    return limitation_lines


# ------------------------------------------------------------------------- the review's recompute


def load_record(path: str | Path, expected_sha256: str | None) -> tuple[object | None, list[str]]:
    """The artifact's JSON when it is there and bears its bound hash; otherwise one named mismatch."""

    try:
        target = Path(path)
        if not target.is_file():
            return None, [_mismatch("missing")]
        raw = target.read_bytes()
    except (OSError, TypeError, ValueError):
        return None, [_mismatch("missing")]
    if not isinstance(expected_sha256, str) or sha256_hex(raw) != expected_sha256:
        return None, [_mismatch("sha256")]
    try:
        record = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None, [_mismatch("invalid")]
    # A hash-correct artifact whose JSON is `null` (or any non-object) is a supplied file the review cannot read,
    # never "no file": `review_block(None, ...)` means no record, so it must not be reachable from a file's bytes.
    return (record, []) if isinstance(record, dict) else (None, [_mismatch("invalid")])


def _strict_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("not an integer")
    return value


def _facts_from(record: Mapping[str, object]) -> tuple[dict[str, FactRow], list[str]]:
    """The supplied numbers a recorded block carries, validated before any arithmetic touches them."""

    contests = record["contests"]
    unused = record["unused_contest_ids"]
    if not isinstance(contests, list) or not isinstance(unused, list):
        raise ValueError("shape")
    if any(not isinstance(item, str) for item in unused):
        raise ValueError("unused")
    facts: dict[str, FactRow] = {}
    for row in contests:
        if not isinstance(row, Mapping) or not isinstance(row["contest_id"], str):
            raise ValueError("contest row")
        if row["facts_state"] == STATE_NO_ROW:
            continue
        size = _strict_int(row["field_size"])
        paid = _strict_int(row["places_paid"])
        cents = _strict_int(row["facts_fee_cents"])
        if size < 1 or paid < 1 or paid > size or cents < 0:
            raise ValueError("range")
        facts[row["contest_id"]] = FactRow(row["contest_id"], size, paid, cents)
    return facts, list(unused)


def review_block(
    record: object, entries: Sequence[tuple[str, str, float]]
) -> tuple[dict[str, object] | None, list[str]]:
    """The block rebuilt from the entry file's rows and the block's own numbers, or one registered code.

    `(None, [])` when there is no record (no facts file was supplied). A record that does not rebuild to
    itself is `(None, [CONTEST_FACTS_REVIEW_MISMATCH:<kind>])`; this never raises.
    """

    if record is None:
        return None, []
    try:
        refs = _entry_refs(entries)
        if refs is None:
            return None, [_mismatch("template")]
        if not isinstance(record, Mapping) or record.get("status") not in STATUSES:
            return None, [_mismatch("block")]
        status = record["status"]
        if status in (STATUS_NOT_SUPPLIED, STATUS_REFUSED):
            sha, name, problems = record["facts_sha256"], record["facts_file_name"], record["problems"]
            if status == STATUS_REFUSED and (
                not isinstance(problems, list) or not problems
                or any(not isinstance(item, str) or not item.startswith("CONTEST_FACTS_") for item in problems)
            ):
                return None, [_mismatch("block")]
            if (sha is not None and not (isinstance(sha, str) and _HEX64.fullmatch(sha))) or not (
                name is None or isinstance(name, str)
            ):
                return None, [_mismatch("block")]
            rebuilt = _unusable(status, problems if status == STATUS_REFUSED else [], sha=sha, name=name)
            return (rebuilt, []) if rebuilt == record else (None, [_mismatch("block")])
        try:
            facts, unused = _facts_from(record)
            sha, name = record["facts_sha256"], record["facts_file_name"]
            if not (isinstance(sha, str) and _HEX64.fullmatch(sha)) or not (name is None or isinstance(name, str)):
                raise ValueError("binding")
        except (KeyError, TypeError, ValueError):
            return None, [_mismatch("contests")]
        rebuilt = _assemble(facts, unused, refs, sha=sha, name=name)
        if rebuilt == record:
            return rebuilt, []
        if rebuilt["entries"] != record.get("entries"):
            return None, [_mismatch("entries")]
        if rebuilt["contests"] != record.get("contests"):
            return None, [_mismatch("contests")]
        return None, [_mismatch("block")]
    except Exception:  # noqa: BLE001 - the review never raises on a label; one registered code is the answer
        return None, [_mismatch("block")]
