"""Session 12, review V13: a prefilled `Name (ID)` roster cell is read by its ID, not as a missing player.

DraftKings' bulk-edit template may carry a roster cell as a bare ID or as text ending `(ID)`
(`prefilled_cell_id`, Session 11). Before this fix `govern_late_swap`, `write_late_swap_bytes` and the
byte audit compared the raw cell text to a bare ID, so a `Name (ID)` current template was refused as
"missing from the current salary pool". The name text is never identity: only the ID is read, and
anything that names no exact ID is refused by name. An unchanged slot keeps its bytes.

The shared test world never writes a `Name (ID)` cell (all 18 of its current cells are bare IDs), so
these tests build their own current files, with `write_bytes`, inside the roster spans only.
"""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path

import pytest

from nfl_dfs import entry_groups, lineups
from nfl_dfs.byte_lines import csv_field_spans, split_byte_lines, split_line_ending
from nfl_dfs.dk import parse_entries
from nfl_dfs.lineups import LateSwapAuthorization, LineupValidationError, write_late_swap_bytes
from nfl_dfs.referee import audit_late_swap_output_bytes

from .test_governed_late_swap import AS_OF, _assert_blocked, _case, _govern

UNRESOLVED = "CURRENT_TEMPLATE_CELL_UNRESOLVED"


def _name_id(player) -> str:
    """`Name (ID)` with an ASCII name, so the file's detected encoding never changes."""

    name = re.sub(r"[^A-Za-z0-9 .'-]", "", player.name).strip() or "Player"
    return f"{name} ({player.dk_id})"


def _rewrite_roster(template, new_cell) -> bytes:
    """The template's bytes with chosen roster cells rewritten; every other byte is kept.

    `new_cell(entry_id, slot, cell)` returns the replacement text, or None to keep the cell's bytes.
    A replacement is serialized the way the late-swap writer serializes one.
    """

    raw = template.path.read_bytes()
    authorized = {entry.entry_id: entry for entry in template.authorizations}
    start = template.roster_start_index
    width = len(template.roster_columns)
    output: list[bytes] = []
    for line in split_byte_lines(raw):
        body, ending = split_line_ending(line)
        row = next(csv.reader([body.decode(template.encoding)]))
        entry_id = row[0].strip() if row else ""
        if entry_id not in authorized:
            output.append(line)
            continue
        pieces: list[bytes] = []
        cursor = 0
        for index, (field_start, field_end) in enumerate(csv_field_spans(body)):
            pieces.append(body[cursor:field_start])
            slot = index - start
            text = (
                new_cell(entry_id, slot, authorized[entry_id].existing_cells[slot])
                if 0 <= slot < width
                else None
            )
            if text is None:
                pieces.append(body[field_start:field_end])
            else:
                buffer = io.StringIO(newline="")
                csv.writer(buffer, lineterminator="").writerow([text])
                pieces.append(buffer.getvalue().encode("utf-8"))
            cursor = field_end
        pieces.append(body[cursor:])
        pieces.append(ending)
        output.append(b"".join(pieces))
    return b"".join(output)


def _reshape(raw: bytes, *, bom: bool, line_ending: bytes, final_newline: bool) -> bytes:
    body = raw.replace(b"\r\n", b"\n").rstrip(b"\n").replace(b"\n", line_ending)
    if final_newline:
        body += line_ending
    return (b"\xef\xbb\xbf" if bom else b"") + body


def _wrapped_world(tmp_path: Path, slate, entries):
    """The shared late-swap world with every current roster cell rewritten as `Name (ID)`."""

    case = _case(tmp_path, slate, entries)
    by_id = {player.dk_id: player for player in slate.players}
    template = parse_entries(case["current"])
    case["current"].write_bytes(
        _rewrite_roster(template, lambda _eid, _slot, cell: _name_id(by_id[cell]))
    )
    case["by_id"] = by_id
    return case


def _authorization(template, original, replaceable=None) -> LateSwapAuthorization:
    replaceable = replaceable or {}
    return LateSwapAuthorization(
        current_template_sha256=template.raw_hash,
        prior_assignment_sha256="a" * 64,
        as_of=AS_OF.isoformat(),
        replaceable_cells=tuple((eid, tuple(replaceable.get(eid, ()))) for eid in sorted(original)),
    )


def _expected_replaceable(case) -> dict[str, tuple[int, ...]]:
    return {
        entry_id: ((case["changed_slot"],) if entry_id == case["changed_entry"] else ())
        for entry_id in case["original"]
    }


def _unlocked_slot_other_than_the_change(case) -> int:
    roster = case["original"][case["changed_entry"]]
    return next(
        slot
        for slot, dk_id in enumerate(roster)
        if case["by_id"][dk_id].lock_at > AS_OF and slot != case["changed_slot"]
    )


def _locked_slot(case, entry_id: str) -> int:
    roster = case["original"][entry_id]
    return next(slot for slot, dk_id in enumerate(roster) if case["by_id"][dk_id].lock_at <= AS_OF)


def test_a_bare_id_cell_resolves_and_the_swap_ships(tmp_path: Path, classic_slate, classic_entries) -> None:
    case = _case(tmp_path, classic_slate, classic_entries)
    manifest, _ = _govern(case, classic_slate, "bare-id")
    assert manifest.status == "CERTIFIED", manifest.blockers
    assert manifest.replaceable_cells == _expected_replaceable(case)


@pytest.mark.parametrize(
    ("bom", "line_ending", "final_newline"),
    [(False, b"\r\n", True), (True, b"\n", False)],
    ids=["crlf-final-newline", "bom-lf-no-final-newline"],
)
def test_a_name_id_cell_resolves_and_the_unchanged_slots_keep_their_bytes(
    tmp_path: Path, classic_slate, classic_entries, bom: bool, line_ending: bytes, final_newline: bool
) -> None:
    case = _wrapped_world(tmp_path, classic_slate, classic_entries)
    case["current"].write_bytes(
        _reshape(case["current"].read_bytes(), bom=bom, line_ending=line_ending, final_newline=final_newline)
    )
    manifest, _ = _govern(case, classic_slate, "name-id")
    assert manifest.status == "CERTIFIED", manifest.blockers
    assert manifest.replaceable_cells == _expected_replaceable(case)
    output_path = Path(manifest.output_path or "")
    output = output_path.read_bytes()
    template = parse_entries(case["current"])
    changed = (case["changed_entry"], case["changed_slot"])
    expected = _rewrite_roster(
        template,
        lambda eid, slot, _cell: case["replacement"] if (eid, slot) == changed else None,
    )
    assert output == expected  # the one authorized cell is a bare ID; every other byte is the source's
    assert output != case["current"].read_bytes()
    assert output.startswith(b"\xef\xbb\xbf") is bom
    assert output.endswith(line_ending) is final_newline
    cells = [cell for entry in parse_entries(output_path).authorizations for cell in entry.existing_cells]
    assert sum("(" in cell for cell in cells) == len(cells) - 1


def test_text_ending_in_an_id_outside_the_pool_is_refused(
    tmp_path: Path, classic_slate, classic_entries
) -> None:
    case = _wrapped_world(tmp_path, classic_slate, classic_entries)
    assert "99999999" not in case["by_id"]
    target = (case["changed_entry"], _unlocked_slot_other_than_the_change(case))
    template = parse_entries(case["current"])
    case["current"].write_bytes(
        _rewrite_roster(template, lambda eid, slot, _c: "Not A Player (99999999)" if (eid, slot) == target else None)
    )
    manifest, path = _govern(case, classic_slate, "wrong-id")
    _assert_blocked(manifest, path)
    assert any(
        "current ID 99999999 is missing from the current salary pool" in blocker
        for blocker in manifest.blockers
    )
    assert not any(blocker.startswith(UNRESOLVED) for blocker in manifest.blockers)


def test_text_with_no_id_is_refused_by_the_named_code(tmp_path: Path, classic_slate, classic_entries) -> None:
    case = _wrapped_world(tmp_path, classic_slate, classic_entries)
    target = (case["changed_entry"], _unlocked_slot_other_than_the_change(case))
    template = parse_entries(case["current"])
    case["current"].write_bytes(
        _rewrite_roster(template, lambda eid, slot, _c: "Not A Player" if (eid, slot) == target else None)
    )
    manifest, path = _govern(case, classic_slate, "no-id")
    _assert_blocked(manifest, path)
    named = [blocker for blocker in manifest.blockers if blocker.startswith(f"{UNRESOLVED}:")]
    assert len(named) == 1 and case["changed_entry"] in named[0]


def test_a_blank_cell_is_named_only_by_the_fully_prefilled_code(
    tmp_path: Path, classic_slate, classic_entries
) -> None:
    """A blank cell holds no text to resolve; `CURRENT_TEMPLATE_MUST_BE_FULLY_PREFILLED` already names it."""

    case = _wrapped_world(tmp_path, classic_slate, classic_entries)
    target = (case["changed_entry"], 1)
    template = parse_entries(case["current"])
    case["current"].write_bytes(
        _rewrite_roster(template, lambda eid, slot, _c: "" if (eid, slot) == target else None)
    )
    manifest, path = _govern(case, classic_slate, "blank-cell")
    _assert_blocked(manifest, path)
    assert "CURRENT_TEMPLATE_MUST_BE_FULLY_PREFILLED" in manifest.blockers
    assert not any(blocker.startswith(UNRESOLVED) for blocker in manifest.blockers)


def test_the_writer_keeps_the_name_id_cells_it_is_not_asked_to_change(
    tmp_path: Path, classic_slate, classic_entries
) -> None:
    case = _wrapped_world(tmp_path, classic_slate, classic_entries)
    template = parse_entries(case["current"])
    output = write_late_swap_bytes(template, case["original"], _authorization(template, case["original"]))
    assert output == case["current"].read_bytes()


def test_the_writer_refuses_an_unresolvable_existing_cell_by_name(
    tmp_path: Path, classic_slate, classic_entries
) -> None:
    case = _wrapped_world(tmp_path, classic_slate, classic_entries)
    target = (case["changed_entry"], 1)
    template = parse_entries(case["current"])
    case["current"].write_bytes(
        _rewrite_roster(template, lambda eid, slot, _c: "Not A Player" if (eid, slot) == target else None)
    )
    template = parse_entries(case["current"])
    with pytest.raises(LineupValidationError, match=UNRESOLVED):
        write_late_swap_bytes(template, case["original"], _authorization(template, case["original"]))


def test_the_byte_audit_reads_a_retained_name_id_cell_by_its_id(
    tmp_path: Path, classic_slate, classic_entries
) -> None:
    case = _wrapped_world(tmp_path, classic_slate, classic_entries)
    template = parse_entries(case["current"])
    source = case["current"].read_bytes()
    audit = audit_late_swap_output_bytes(
        case["current"], source, template, case["original"], _authorization(template, case["original"])
    )
    assert audit.valid, audit.problems


def test_the_byte_audit_accepts_an_authorized_slot_written_in_the_name_id_form(
    tmp_path: Path, classic_slate, classic_entries
) -> None:
    """Only the roster comparison is in play here: the slot is replaceable, so no byte guard applies."""

    case = _wrapped_world(tmp_path, classic_slate, classic_entries)
    template = parse_entries(case["current"])
    changed = (case["changed_entry"], case["changed_slot"])
    output = _rewrite_roster(
        template,
        lambda eid, slot, _c: f"Alias Name ({case['replacement']})" if (eid, slot) == changed else None,
    )
    audit = audit_late_swap_output_bytes(
        case["current"],
        output,
        template,
        case["proposed"],
        _authorization(template, case["original"], {case["changed_entry"]: (case["changed_slot"],)}),
    )
    assert audit.valid, audit.problems


def test_the_byte_audit_rejects_a_locked_name_id_cell_whose_text_changed_but_not_its_id(
    tmp_path: Path, classic_slate, classic_entries
) -> None:
    """The one input only the byte guard rejects: the ID is unchanged, so the roster comparison passes."""

    case = _wrapped_world(tmp_path, classic_slate, classic_entries)
    template = parse_entries(case["current"])
    locked = (case["changed_entry"], _locked_slot(case, case["changed_entry"]))
    locked_id = case["original"][locked[0]][locked[1]]
    output = _rewrite_roster(
        template,
        lambda eid, slot, _c: f"Renamed Player ({locked_id})" if (eid, slot) == locked else None,
    )
    audit = audit_late_swap_output_bytes(
        case["current"],
        output,
        template,
        case["original"],
        _authorization(template, case["original"]),
    )
    assert not audit.valid
    assert any("locked or unauthorized roster cell bytes changed" in problem for problem in audit.problems)
    assert not any("roster bytes do not match assignment" in problem for problem in audit.problems)


def test_the_same_bytes_in_give_byte_identical_upload_files(
    tmp_path: Path, classic_slate, classic_entries
) -> None:
    case = _wrapped_world(tmp_path, classic_slate, classic_entries)
    first, _ = _govern(case, classic_slate, "determinism-a")
    second, _ = _govern(case, classic_slate, "determinism-b")
    assert first.status == second.status == "CERTIFIED", (first.blockers, second.blockers)
    assert Path(first.output_path or "").read_bytes() == Path(second.output_path or "").read_bytes()
    assert first.output_sha256 == second.output_sha256


def test_one_changed_current_cell_in_a_locked_slot_withholds_the_upload(
    tmp_path: Path, classic_slate, classic_entries
) -> None:
    case = _wrapped_world(tmp_path, classic_slate, classic_entries)
    entry_id = case["changed_entry"]
    slot = _locked_slot(case, entry_id)
    roster = case["original"][entry_id]
    other = next(
        player for player in classic_slate.players
        if player.dk_id not in roster and "(" not in player.name and "," not in player.name
    )
    template = parse_entries(case["current"])
    case["current"].write_bytes(
        _rewrite_roster(template, lambda eid, s, _c: _name_id(other) if (eid, s) == (entry_id, slot) else None)
    )
    manifest, path = _govern(case, classic_slate, "mutated-locked-cell")
    _assert_blocked(manifest, path)
    assert any("locked prior player" in blocker for blocker in manifest.blockers)


def test_prefilled_cell_id_is_one_function_in_both_modules() -> None:
    assert entry_groups.prefilled_cell_id is lineups.prefilled_cell_id
