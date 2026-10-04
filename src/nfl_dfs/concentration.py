"""The registered Showdown concentration defaults (Session 56, R35, review F-02).

`config/showdown_concentration_defaults_v1.json` is one default set: no person in
more than 0.60 of the lineups, no Captain in more than 0.20, two lineups sharing at
most 4 people, plus the order the caps give way in when a run cannot meet them.
It is read by `scripts/make_showdown_policy.py` (its flag defaults), by `run-slate`
(the policy it builds for a Showdown run that supplied none) and by the relaxation
ladder (the steps before any structural rung). v1 is never mutated: a change is a
new file and a new `schema_version`, and `tests/test_concentration_defaults.py`
pins this one's bytes.

A construction preference (class `S`): the ladder relaxes it on its own authority
and names every step. It says nothing about winnings; see `does_not_establish`.
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
from decimal import Decimal, InvalidOperation
from pathlib import Path

SCHEMA_VERSION = "showdown_concentration_defaults_v1"
DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config" / "showdown_concentration_defaults_v1.json"
# What a step may apply to: the policy the engine builds itself, and a policy whose
# default fractions are exactly the requested pair (a generator's default output).
ENGINE_DEFAULT = "ENGINE_DEFAULT"
POLICY = "POLICY"
TARGETS = frozenset({ENGINE_DEFAULT, POLICY})
_TOP = frozenset({"schema_version", "registered_at", "scope", "authority", "defaults", "relaxation_steps",
                  "step_notes", "does_not_establish"})
_NAME = re.compile(r"[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*")


class ConcentrationDefaultsError(ValueError):
    """The defaults file cannot be trusted; nothing falls back to a guess."""


@dataclass(frozen=True)
class ConcentrationStep:
    name: str
    person_fraction: Decimal | None  # None: no cap
    captain_fraction: Decimal | None
    applies_to: frozenset[str]


@dataclass(frozen=True)
class ConcentrationDefaults:
    person_fraction: Decimal
    captain_fraction: Decimal
    pairwise_person_overlap: int
    steps: tuple[ConcentrationStep, ...]
    does_not_establish: tuple[str, ...]
    sha256: str
    version: str = SCHEMA_VERSION

    def steps_for(self, target: str) -> tuple[ConcentrationStep, ...]:
        """The cap steps that apply to `target`, in the order they are taken."""

        return tuple(step for step in self.steps if target in step.applies_to)

    def least_entries(self) -> int:
        """The fewest entries on which the Captain default binds (`floor(f * n) >= 1`)."""

        return math.ceil(Decimal(1) / self.captain_fraction)

    def requested(self) -> dict[str, object]:
        return {"person_fraction": str(self.person_fraction), "captain_fraction": str(self.captain_fraction),
                "pairwise_person_overlap": self.pairwise_person_overlap}

    def matches(self, person_fraction: Decimal | None, captain_fraction: Decimal | None) -> bool:
        """True when a policy's two default fractions are exactly the requested pair."""

        return person_fraction == self.person_fraction and captain_fraction == self.captain_fraction


def _fraction(value: object, where: str, *, nullable: bool = False) -> Decimal | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str):
        raise ConcentrationDefaultsError(f"concentration defaults invalid: {where} must be a decimal string")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ConcentrationDefaultsError(f"concentration defaults invalid: {where} is not a decimal: {value!r}") from exc
    if not parsed.is_finite() or not Decimal(0) < parsed <= Decimal(1):
        raise ConcentrationDefaultsError(f"concentration defaults invalid: {where} must be in (0, 1]: {value!r}")
    return parsed


def parse_concentration_defaults(raw: bytes) -> ConcentrationDefaults:
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ConcentrationDefaultsError(f"concentration defaults unreadable: {exc}") from exc
    if not isinstance(document, dict) or document.get("schema_version") != SCHEMA_VERSION:
        raise ConcentrationDefaultsError(f"concentration defaults invalid: schema_version is not {SCHEMA_VERSION}")
    unknown = sorted(set(document) - _TOP)
    if unknown:
        raise ConcentrationDefaultsError(f"concentration defaults invalid: unknown fields {unknown}")
    defaults = document.get("defaults")
    if not isinstance(defaults, dict):
        raise ConcentrationDefaultsError("concentration defaults invalid: defaults must be an object")
    person = _fraction(defaults.get("person_fraction"), "defaults.person_fraction")
    captain = _fraction(defaults.get("captain_fraction"), "defaults.captain_fraction")
    overlap = defaults.get("pairwise_person_overlap")
    if isinstance(overlap, bool) or not isinstance(overlap, int) or not 0 <= overlap <= 6:
        raise ConcentrationDefaultsError("concentration defaults invalid: defaults.pairwise_person_overlap must be 0 to 6")
    steps: list[ConcentrationStep] = []
    seen: set[str] = set()
    previous = (person, captain)
    for index, item in enumerate(document.get("relaxation_steps") or ()):
        where = f"relaxation_steps[{index}]"
        if not isinstance(item, dict):
            raise ConcentrationDefaultsError(f"concentration defaults invalid: {where} must be an object")
        name = item.get("name")
        if not isinstance(name, str) or not _NAME.fullmatch(name) or name in seen:
            raise ConcentrationDefaultsError(f"concentration defaults invalid: {where}.name is missing, malformed or repeated")
        seen.add(name)
        step_person = _fraction(item.get("person_fraction"), f"{where}.person_fraction", nullable=True)
        step_captain = _fraction(item.get("captain_fraction"), f"{where}.captain_fraction", nullable=True)
        targets = item.get("applies_to")
        if (not isinstance(targets, list) or not targets or not set(targets) <= TARGETS
                or len(set(targets)) != len(targets)):
            raise ConcentrationDefaultsError(f"concentration defaults invalid: {where}.applies_to must name {sorted(TARGETS)}")
        # A step only ever loosens: None is no cap, the loosest value, and the whole list is monotone.
        for label, before, after in (("person", previous[0], step_person), ("captain", previous[1], step_captain)):
            if before is None and after is not None or (before is not None and after is not None and after < before):
                raise ConcentrationDefaultsError(f"concentration defaults invalid: {where} tightens the {label} cap")
        if (step_person, step_captain) == previous:
            raise ConcentrationDefaultsError(f"concentration defaults invalid: {where} changes nothing")
        previous = (step_person, step_captain)
        steps.append(ConcentrationStep(name, step_person, step_captain, frozenset(targets)))
    limits = document.get("does_not_establish")
    if not isinstance(limits, list) or not limits or not all(isinstance(item, str) for item in limits):
        raise ConcentrationDefaultsError("concentration defaults invalid: does_not_establish must name what it does not claim")
    return ConcentrationDefaults(person, captain, overlap, tuple(steps), tuple(limits), hashlib.sha256(raw).hexdigest())


def load_concentration_defaults(
    path: str | Path = DEFAULT_PATH, *, expected_sha256: str | None = None
) -> ConcentrationDefaults:
    """Read, hash and validate the defaults; refuse bytes other than `expected_sha256`."""

    try:
        raw = Path(path).read_bytes()
    except OSError as exc:
        raise ConcentrationDefaultsError(f"concentration defaults unreadable: {path}:{exc}") from exc
    digest = hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256:
        raise ConcentrationDefaultsError(
            f"concentration defaults sha256 mismatch: actual={digest}:expected={expected_sha256}")
    return parse_concentration_defaults(raw)


_SLOTS = ["CPT", "FLEX", "FLEX", "FLEX", "FLEX", "FLEX"]
_TRAILING_ID = re.compile(r"\((\d+)\)\s*$")


def measure_delivered_concentration(slate, csv_path: str | Path) -> dict[str, object]:
    """How concentrated the file at `csv_path` is, recomputed from its own bytes (Session 56).

    Reads the filled roster cells of every entry row, the template's prefilled rows
    included, and counts each person (Captain and FLEX together, a person once per
    lineup) and each Captain through `slate`'s exact DraftKings IDs. It reads no report
    of the engine's: a file the baseline delivered is measured the same way as one the
    joint solve built. A problem reading the file is named in the result, never raised.
    """

    try:
        text = Path(csv_path).read_bytes().decode("utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        return {"problem": f"the delivered file could not be read: {exc}"}
    try:
        rows = list(csv.reader(io.StringIO(text, newline="")))
    except csv.Error as exc:
        return {"problem": f"the delivered file is not readable as CSV: {exc}"}
    header = rows[0] if rows else []
    if "Entry Fee" not in header:
        return {"problem": "the delivered file has no Entry Fee column to anchor the roster cells"}
    start = header.index("Entry Fee") + 1
    if header[start:start + len(_SLOTS)] != _SLOTS:
        return {"problem": "the delivered file is not a Showdown entry file (CPT and five FLEX after Entry Fee)"}
    people = {row.dk_id: row.underlying_id for row in slate.players}
    person_counts: Counter[str] = Counter()
    captain_counts: Counter[str] = Counter()
    lineups: set[tuple[str, tuple[str, ...]]] = set()
    unknown = 0
    measured = 0
    for row in rows[1:]:
        if not row or not row[0].strip().isdigit():
            continue
        ids = []
        for cell in row[start:start + len(_SLOTS)]:
            match = _TRAILING_ID.search(cell)
            ids.append(match.group(1) if match else cell.strip())
        if len(ids) != len(_SLOTS) or not all(ids):
            continue  # a blank or partly filled row is not a lineup
        if not all(item in people for item in ids):
            unknown += 1
            continue
        measured += 1
        underlying = [people[item] for item in ids]
        person_counts.update(set(underlying))
        captain_counts[underlying[0]] += 1
        lineups.add((underlying[0], tuple(sorted(underlying[1:]))))
    # Every filled row counts, the template's prefilled rows included: the caps bind the fillable rows only.
    report: dict[str, object] = {"scope": "ALL_FILLED_ROWS_INCLUDING_PREFILLED", "rows": measured,
                                 "distinct_lineups": len(lineups), "unknown_id_rows": unknown}
    if measured:
        person, person_entries = person_counts.most_common(1)[0]
        captain, captain_entries = captain_counts.most_common(1)[0]
        report.update({
            "max_person": person, "max_person_entries": person_entries,
            "max_person_share": str(Decimal(person_entries) / Decimal(measured)),
            "max_captain": captain, "max_captain_entries": captain_entries,
            "max_captain_share": str(Decimal(captain_entries) / Decimal(measured)),
        })
    return report
