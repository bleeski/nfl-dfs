from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

from .byte_lines import csv_field_spans, split_byte_lines, split_line_ending
from .contracts import EngineMode, Lineup, SalaryPlayer, SlateContract
from .dk import CLASSIC_COLUMNS, SHOWDOWN_COLUMNS, EntryTemplate
from .hashing import content_hash, sha256_bytes


class LineupValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ValidationResult:
    lineup: Lineup | None
    errors: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return not self.errors and self.lineup is not None


@dataclass(frozen=True)
class LateSwapAuthorization:
    current_template_sha256: str
    prior_assignment_sha256: str
    as_of: str
    replaceable_cells: tuple[tuple[str, tuple[int, ...]], ...]

    def by_entry(self) -> dict[str, frozenset[int]]:
        return {
            entry_id: frozenset(indexes)
            for entry_id, indexes in self.replaceable_cells
        }


def _canonical_key(mode: EngineMode, players: list[SalaryPlayer]) -> str:
    if mode is EngineMode.SHOWDOWN:
        captain = players[0].underlying_id
        flex = sorted(player.underlying_id for player in players[1:])
        return f"CPT:{captain}|FLEX:{'|'.join(flex)}"
    return "|".join(sorted(player.dk_id for player in players))


def validate_lineup(
    slate: SlateContract,
    roster_ids: Iterable[str],
    *,
    locked_slots: Mapping[int, str] | None = None,
) -> ValidationResult:
    roster = tuple(str(value).strip() for value in roster_ids)
    expected_slots = CLASSIC_COLUMNS if slate.mode is EngineMode.CLASSIC else SHOWDOWN_COLUMNS
    errors: list[str] = []
    if len(roster) != len(expected_slots):
        return ValidationResult(
            None, (f"LINEUP_ROSTER_WIDTH_INVALID: expected {len(expected_slots)} roster cells",)
        )
    if any(not value for value in roster):
        errors.append("LINEUP_BLANK_CELL: roster contains a blank cell")
    by_id = {player.dk_id: player for player in slate.players}
    players: list[SalaryPlayer] = []
    for slot_number, (slot, dk_id) in enumerate(zip(expected_slots, roster, strict=True)):
        player = by_id.get(dk_id)
        if player is None:
            errors.append(
                f"LINEUP_DK_ID_NOT_IN_POOL: slot {slot_number + 1}: DK ID {dk_id!r} is outside "
                "the salary pool"
            )
            continue
        if slate.mode is EngineMode.CLASSIC:
            eligible = slot in player.roster_positions
        else:
            eligible = player.role == slot
        if not eligible:
            errors.append(
                f"LINEUP_SLOT_INELIGIBLE: slot {slot_number + 1}: {player.name} ({dk_id}) is not "
                f"eligible for {slot}"
            )
        players.append(player)
    if locked_slots:
        for index, locked_id in locked_slots.items():
            if index < 0 or index >= len(roster) or roster[index] != locked_id:
                errors.append(f"LINEUP_LOCKED_SLOT_CHANGED: locked slot {index + 1} changed")
    if len(players) != len(roster):
        return ValidationResult(None, tuple(errors))
    person_ids = [player.underlying_id for player in players]
    if len(set(person_ids)) != len(person_ids):
        errors.append("LINEUP_PERSON_REPEATED: the same underlying player appears more than once")
    salary = sum(player.salary for player in players)
    if salary > slate.salary_cap:
        errors.append(f"LINEUP_SALARY_CAP_EXCEEDED: salary {salary} exceeds cap {slate.salary_cap}")
    if slate.mode is EngineMode.CLASSIC:
        if len({player.game_id for player in players}) < 2:
            errors.append(
                "LINEUP_GAME_COUNT_INVALID: Classic lineup must include players from at least two games"
            )
    else:
        if players and players[0].role != "CPT":
            errors.append("LINEUP_CAPTAIN_SLOT_INVALID: first Showdown slot must use a CPT salary row")
        if len({player.team for player in players}) < 2:
            errors.append("LINEUP_TEAM_COUNT_INVALID: Showdown lineup must include both teams")
    if errors:
        return ValidationResult(None, tuple(errors))
    return ValidationResult(
        Lineup(
            mode=slate.mode,
            roster=roster,
            canonical_key=_canonical_key(slate.mode, players),
            salary=salary,
        ),
        (),
    )


def read_assignment_csv(
    path: str | Path, mode: EngineMode
) -> dict[str, tuple[str, ...]]:
    columns = CLASSIC_COLUMNS if mode is EngineMode.CLASSIC else SHOWDOWN_COLUMNS
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise LineupValidationError("ASSIGNMENT_CSV_EMPTY: assignment CSV is empty") from exc
        expected = ("Entry ID",) + columns
        if tuple(header) != expected:
            raise LineupValidationError(f"ASSIGNMENT_HEADER_INVALID: assignment header must be {expected}")
        assignments: dict[str, tuple[str, ...]] = {}
        for row_number, row in enumerate(reader, start=2):
            if not row or not any(cell.strip() for cell in row):
                continue
            if len(row) != len(expected):
                raise LineupValidationError(
                    f"ASSIGNMENT_ROW_WIDTH_INVALID: assignment row {row_number} has wrong width"
                )
            entry_id = row[0].strip()
            if entry_id in assignments:
                raise LineupValidationError(
                    f"ASSIGNMENT_ENTRY_ID_DUPLICATE: duplicate assignment Entry ID {entry_id}"
                )
            assignments[entry_id] = tuple(cell.strip() for cell in row[1:])
    return assignments


def write_upload_bytes(
    template: EntryTemplate,
    assignments: Mapping[str, tuple[str, ...]],
    *,
    unfilled: Iterable[str] = (),
) -> bytes:
    """The template's bytes with each assigned row's roster cells written in place.

    Every authorized Entry ID is either assigned or named in `unfilled`, never
    both, so a row can be left blank only on purpose (R28's partial delivery);
    an unfilled row's bytes pass through untouched. A prefilled row refuses the
    write whichever list it is in, exactly as before `unfilled` existed.
    """

    authorized = {entry.entry_id: entry for entry in template.authorizations}
    left_blank = set(unfilled)
    if set(assignments) | left_blank != set(authorized) or left_blank & set(assignments):
        missing = sorted(set(authorized).difference(assignments).difference(left_blank))
        extra = sorted(set(assignments).union(left_blank).difference(authorized))
        both = sorted(left_blank.intersection(assignments))
        raise LineupValidationError(
            "ENTRY_AUTHORIZATION_MISMATCH: assignment authorization mismatch: "
            f"missing={missing}, extra={extra}, assigned_and_unfilled={both}"
        )
    prefilled = sorted(entry_id for entry_id in left_blank if any(authorized[entry_id].existing_cells))
    if prefilled:
        raise LineupValidationError(
            f"ENTRY_BLANK_CELL_AUTHORITY_REQUIRED: Entry {prefilled[0]} has prefilled cells; "
            "automatic replacement is not authorized"
        )
    raw = template.path.read_bytes()
    lines = split_byte_lines(raw)
    output: list[bytes] = []
    found: set[str] = set()
    for line_number, line in enumerate(lines, start=1):
        body_bytes, ending_bytes = split_line_ending(line)
        body = body_bytes.decode(template.encoding)
        row = next(csv.reader([body]))
        entry_id = row[0].strip() if row else ""
        if entry_id not in assignments:
            output.append(line)
            continue
        if entry_id in found:
            raise LineupValidationError(
                f"ENTRY_SOURCE_ID_DUPLICATE: duplicate source Entry ID at line {line_number}"
            )
        auth = authorized[entry_id]
        if any(auth.existing_cells):
            raise LineupValidationError(
                f"ENTRY_BLANK_CELL_AUTHORITY_REQUIRED: Entry {entry_id} has prefilled cells; "
                "automatic replacement is not authorized"
            )
        roster_start = template.roster_start_index
        needed = roster_start + len(template.roster_columns)
        spans = csv_field_spans(body_bytes)
        if len(row) < needed or len(spans) < needed:
            raise LineupValidationError(
                f"ENTRY_ROW_NARROWER_THAN_ROSTER: Entry {entry_id} source row is narrower than "
                "the roster geometry"
            )
        output_encoding = "utf-8" if template.encoding == "utf-8-sig" else template.encoding
        replacements: dict[int, bytes] = {}
        for index, value in enumerate(assignments[entry_id], start=roster_start):
            buffer = io.StringIO(newline="")
            csv.writer(buffer, lineterminator="").writerow([value])
            replacements[index] = buffer.getvalue().encode(output_encoding)
        rewritten: list[bytes] = []
        cursor = 0
        for index, (start, end) in enumerate(spans):
            rewritten.append(body_bytes[cursor:start])
            rewritten.append(replacements.get(index, body_bytes[start:end]))
            cursor = end
        rewritten.append(body_bytes[cursor:])
        rewritten.append(ending_bytes)
        output.append(b"".join(rewritten))
        found.add(entry_id)
    if found != set(assignments):
        raise LineupValidationError(
            "ENTRY_SOURCE_COVERAGE_INCOMPLETE: not all authorized Entry IDs were found in source bytes"
        )
    return b"".join(output)


def write_late_swap_bytes(
    template: EntryTemplate,
    assignments: Mapping[str, tuple[str, ...]],
    authorization: LateSwapAuthorization,
) -> bytes:
    """Rewrite only roster cells proven replaceable by the late-swap governor."""
    authorized = {entry.entry_id: entry for entry in template.authorizations}
    if set(assignments) != set(authorized):
        missing = sorted(set(authorized).difference(assignments))
        extra = sorted(set(assignments).difference(authorized))
        raise LineupValidationError(
            f"ENTRY_AUTHORIZATION_MISMATCH: assignment authorization mismatch: missing={missing}, extra={extra}"
        )
    raw = template.path.read_bytes()
    if sha256_bytes(raw) != template.raw_hash:
        raise LineupValidationError(
            "LATE_SWAP_TEMPLATE_CHANGED: current entry template changed after authorization"
        )
    if template.raw_hash != authorization.current_template_sha256:
        raise LineupValidationError(
            "LATE_SWAP_AUTHORIZATION_TEMPLATE_MISMATCH: late-swap authorization targets a different template"
        )
    allowed_by_entry = authorization.by_entry()
    if set(allowed_by_entry) != set(assignments):
        raise LineupValidationError(
            "LATE_SWAP_AUTHORIZATION_COVERAGE_INCOMPLETE: late-swap authorization Entry-ID coverage is incomplete"
        )

    lines = split_byte_lines(raw)
    output: list[bytes] = []
    found: set[str] = set()
    for line_number, line in enumerate(lines, start=1):
        body_bytes, ending_bytes = split_line_ending(line)
        body = body_bytes.decode(template.encoding)
        row = next(csv.reader([body]))
        entry_id = row[0].strip() if row else ""
        if entry_id not in assignments:
            output.append(line)
            continue
        if entry_id in found:
            raise LineupValidationError(
                f"ENTRY_SOURCE_ID_DUPLICATE: duplicate source Entry ID at line {line_number}"
            )
        roster_start = template.roster_start_index
        roster_width = len(template.roster_columns)
        needed = roster_start + roster_width
        spans = csv_field_spans(body_bytes)
        if len(row) < needed or len(spans) < needed:
            raise LineupValidationError(
                f"ENTRY_ROW_NARROWER_THAN_ROSTER: Entry {entry_id} source row is narrower than "
                "the roster geometry"
            )
        auth = authorized[entry_id]
        if len(auth.existing_cells) != roster_width or any(
            not value for value in auth.existing_cells
        ):
            raise LineupValidationError(
                f"LATE_SWAP_ENTRY_NOT_FULLY_PREFILLED: Entry {entry_id} must be fully prefilled "
                "for governed late swap"
            )
        proposed = assignments[entry_id]
        if len(proposed) != roster_width:
            raise LineupValidationError(f"LATE_SWAP_ROSTER_WIDTH_CHANGED: Entry {entry_id} roster width changed")
        allowed = allowed_by_entry[entry_id]
        if any(index < 0 or index >= roster_width for index in allowed):
            raise LineupValidationError(
                f"LATE_SWAP_AUTHORIZATION_INDEX_INVALID: Entry {entry_id} authorization contains "
                "an invalid roster index"
            )
        changed = {
            index
            for index, (existing, replacement) in enumerate(
                zip(auth.existing_cells, proposed, strict=True)
            )
            if existing != replacement
        }
        if changed != allowed:
            raise LineupValidationError(
                f"LATE_SWAP_CHANGED_CELLS_UNAUTHORIZED: Entry {entry_id} changed cells {sorted(changed)} do not exactly match "
                f"derived authorization {sorted(allowed)}"
            )
        output_encoding = (
            "utf-8" if template.encoding == "utf-8-sig" else template.encoding
        )
        replacements: dict[int, bytes] = {}
        for slot in sorted(changed):
            buffer = io.StringIO(newline="")
            csv.writer(buffer, lineterminator="").writerow([proposed[slot]])
            replacements[roster_start + slot] = buffer.getvalue().encode(output_encoding)
        rewritten: list[bytes] = []
        cursor = 0
        for index, (start, end) in enumerate(spans):
            rewritten.append(body_bytes[cursor:start])
            rewritten.append(replacements.get(index, body_bytes[start:end]))
            cursor = end
        rewritten.append(body_bytes[cursor:])
        rewritten.append(ending_bytes)
        output.append(b"".join(rewritten))
        found.add(entry_id)
    if found != set(assignments):
        raise LineupValidationError(
            "ENTRY_SOURCE_COVERAGE_INCOMPLETE: not all authorized Entry IDs were found in source bytes"
        )
    return b"".join(output)


def assignment_hash(assignments: Mapping[str, tuple[str, ...]]) -> str:
    return content_hash({key: list(assignments[key]) for key in sorted(assignments)})
