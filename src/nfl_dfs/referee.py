from __future__ import annotations

import csv
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Mapping

from .dk import EntryTemplate


@dataclass(frozen=True)
class ByteAudit:
    valid: bool
    problems: tuple[str, ...]


def audit_output_bytes(
    source_path: str | Path,
    output_bytes: bytes,
    template: EntryTemplate,
    assignments: Mapping[str, tuple[str, ...]],
) -> ByteAudit:
    source_bytes = Path(source_path).read_bytes()
    source_text = source_bytes.decode(template.encoding)
    output_text = output_bytes.decode(template.encoding)
    source_lines = source_text.splitlines(keepends=True)
    output_lines = output_text.splitlines(keepends=True)
    problems: list[str] = []
    if len(source_lines) != len(output_lines):
        return ByteAudit(False, ("line count changed",))
    roster_start = 4
    roster_end = roster_start + len(template.roster_columns)
    authorized = set(assignments)
    seen: set[str] = set()
    for line_number, (source_line, output_line) in enumerate(
        zip(source_lines, output_lines, strict=True), start=1
    ):
        source_row = next(csv.reader(StringIO(source_line)))
        output_row = next(csv.reader(StringIO(output_line)))
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
        if source_row[:roster_start] != output_row[:roster_start]:
            problems.append(f"line {line_number}: entry metadata changed")
        if source_row[roster_end:] != output_row[roster_end:]:
            problems.append(f"line {line_number}: non-roster cells changed")
        if tuple(cell.strip() for cell in output_row[roster_start:roster_end]) != assignments[source_id]:
            problems.append(f"line {line_number}: roster bytes do not match assignment")
    if seen != authorized:
        problems.append("authorized Entry-ID coverage is incomplete")
    return ByteAudit(not problems, tuple(problems))
