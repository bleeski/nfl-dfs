from __future__ import annotations

import csv
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Mapping

from .byte_lines import csv_field_spans, split_byte_lines, split_line_ending
from .dk import EntryTemplate
from .lineups import LateSwapAuthorization, prefilled_cell_id


@dataclass(frozen=True)
class ByteAudit:
    valid: bool
    problems: tuple[str, ...]


def _first_record(line: bytes, encoding: str) -> list[str] | None:
    """The one CSV record on a physical line, or None when the line holds none.

    Review E12 (Session 37): `next()` on a line that decodes to nothing (a lone
    byte-order mark) raised `StopIteration` instead of naming the line.
    """
    return next(csv.reader(StringIO(line.decode(encoding))), None)


def audit_output_bytes(
    source_path: str | Path,
    output_bytes: bytes,
    template: EntryTemplate,
    assignments: Mapping[str, tuple[str, ...]],
) -> ByteAudit:
    source_bytes = Path(source_path).read_bytes()
    source_lines = split_byte_lines(source_bytes)
    output_lines = split_byte_lines(output_bytes)
    problems: list[str] = []
    if len(source_lines) != len(output_lines):
        return ByteAudit(False, ("line count changed",))
    roster_start = template.roster_start_index
    roster_end = roster_start + len(template.roster_columns)
    authorized = set(assignments)
    seen: set[str] = set()
    for line_number, (source_line, output_line) in enumerate(
        zip(source_lines, output_lines, strict=True), start=1
    ):
        source_body, source_ending = split_line_ending(source_line)
        output_body, output_ending = split_line_ending(output_line)
        if source_ending != output_ending:
            problems.append(f"line {line_number}: line ending changed")
        try:
            source_row = _first_record(source_line, template.encoding)
            output_row = _first_record(output_line, template.encoding)
        except (UnicodeDecodeError, csv.Error) as exc:
            problems.append(f"line {line_number}: CSV reparse failed: {exc}")
            continue
        if source_row is None or output_row is None:
            if source_line != output_line:
                problems.append(f"line {line_number}: empty physical line holds no CSV record")
            continue
        source_id = source_row[0].strip() if source_row else ""
        output_id = output_row[0].strip() if output_row else ""
        if source_id != output_id:
            problems.append(f"line {line_number}: Entry ID changed")
            continue
        if source_id not in authorized:
            if source_line != output_line:
                problems.append(f"line {line_number}: unauthorized bytes changed")
            continue
        seen.add(source_id)
        if any(cell.strip() for cell in source_row[roster_start:roster_end]):
            # Blank-cell authority (Session 11): only an all-blank row is ever written.
            problems.append(f"line {line_number}: a prefilled roster cell was written")
        try:
            source_spans = csv_field_spans(source_body)
            output_spans = csv_field_spans(output_body)
        except ValueError as exc:
            problems.append(f"line {line_number}: invalid physical CSV bytes: {exc}")
            continue
        if len(source_spans) != len(output_spans):
            problems.append(f"line {line_number}: CSV field count changed")
            continue
        for index, ((source_start, source_end), (output_start, output_end)) in enumerate(
            zip(source_spans, output_spans, strict=True)
        ):
            if roster_start <= index < roster_end:
                continue
            if source_body[source_start:source_end] != output_body[output_start:output_end]:
                problems.append(f"line {line_number}: untouched field bytes changed")
                break
        if source_row[:roster_start] != output_row[:roster_start]:
            problems.append(f"line {line_number}: entry metadata changed")
        if source_row[roster_end:] != output_row[roster_end:]:
            problems.append(f"line {line_number}: non-roster cells changed")
        if tuple(cell.strip() for cell in output_row[roster_start:roster_end]) != assignments[source_id]:
            problems.append(f"line {line_number}: roster bytes do not match assignment")
    if seen != authorized:
        problems.append("authorized Entry-ID coverage is incomplete")
    return ByteAudit(not problems, tuple(problems))


def audit_late_swap_output_bytes(
    source_path: str | Path,
    output_bytes: bytes,
    template: EntryTemplate,
    assignments: Mapping[str, tuple[str, ...]],
    authorization: LateSwapAuthorization,
) -> ByteAudit:
    source_bytes = Path(source_path).read_bytes()
    source_lines = split_byte_lines(source_bytes)
    output_lines = split_byte_lines(output_bytes)
    problems: list[str] = []
    if len(source_lines) != len(output_lines):
        return ByteAudit(False, ("line count changed",))
    roster_start = template.roster_start_index
    roster_width = len(template.roster_columns)
    roster_end = roster_start + roster_width
    allowed_by_entry = authorization.by_entry()
    authorized = set(assignments)
    if set(allowed_by_entry) != authorized:
        problems.append("derived authorization Entry-ID coverage is incomplete")
    seen: set[str] = set()
    for line_number, (source_line, output_line) in enumerate(
        zip(source_lines, output_lines, strict=True), start=1
    ):
        source_body, source_ending = split_line_ending(source_line)
        output_body, output_ending = split_line_ending(output_line)
        if source_ending != output_ending:
            problems.append(f"line {line_number}: line ending changed")
        try:
            source_row = _first_record(source_line, template.encoding)
            output_row = _first_record(output_line, template.encoding)
        except (UnicodeDecodeError, csv.Error) as exc:
            problems.append(f"line {line_number}: CSV reparse failed: {exc}")
            continue
        if source_row is None or output_row is None:
            if source_line != output_line:
                problems.append(f"line {line_number}: empty physical line holds no CSV record")
            continue
        source_id = source_row[0].strip() if source_row else ""
        output_id = output_row[0].strip() if output_row else ""
        if source_id != output_id:
            problems.append(f"line {line_number}: Entry ID changed")
            continue
        if source_id not in authorized:
            if source_line != output_line:
                problems.append(f"line {line_number}: unauthorized bytes changed")
            continue
        seen.add(source_id)
        try:
            source_spans = csv_field_spans(source_body)
            output_spans = csv_field_spans(output_body)
        except ValueError as exc:
            problems.append(f"line {line_number}: invalid physical CSV bytes: {exc}")
            continue
        if len(source_spans) != len(output_spans):
            problems.append(f"line {line_number}: CSV field count changed")
            continue
        allowed = allowed_by_entry.get(source_id, frozenset())
        for index, ((source_start, source_end), (output_start, output_end)) in enumerate(
            zip(source_spans, output_spans, strict=True)
        ):
            is_replaceable = roster_start <= index < roster_end and (
                index - roster_start in allowed
            )
            if is_replaceable:
                continue
            if source_body[source_start:source_end] != output_body[output_start:output_end]:
                if roster_start <= index < roster_end:
                    problems.append(
                        f"line {line_number}: locked or unauthorized roster cell bytes changed"
                    )
                else:
                    problems.append(f"line {line_number}: unauthorized field bytes changed")
                break
        if source_row[:roster_start] != output_row[:roster_start]:
            problems.append(f"line {line_number}: entry metadata changed")
        if source_row[roster_end:] != output_row[roster_end:]:
            problems.append(f"line {line_number}: non-roster cells changed")
        output_cells = tuple(cell.strip() for cell in output_row[roster_start:roster_end])
        # The roster matches the assignment by the ID each cell names (`Name (ID)` or a bare ID,
        # Session 12, V13); a cell that names none stays text, so it can never equal an assignment.
        output_roster = tuple(prefilled_cell_id(cell) or cell for cell in output_cells)
        if output_roster != assignments[source_id]:
            problems.append(f"line {line_number}: roster bytes do not match assignment")
        source_roster = tuple(
            cell.strip() for cell in source_row[roster_start:roster_end]
        )
        for slot in range(roster_width):
            # A cell no one authorized stays the same text, not only the same ID.
            if slot not in allowed and output_cells[slot] != source_roster[slot]:
                problems.append(
                    f"line {line_number}: unauthorized roster slot {slot + 1} changed"
                )
    if seen != authorized:
        problems.append("authorized Entry-ID coverage is incomplete")
    return ByteAudit(not problems, tuple(problems))
