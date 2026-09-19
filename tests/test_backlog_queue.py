"""The backlog queue table is the tracker, so it must actually be parseable.

On 2026-09-19 a second status table was added to `backlog.md` with its own
column layout. `scripts/repo_state.py`'s queue parser requires a leading order
column, so it matched none of those rows and silently ignored them: the
session-start hook — the only status a fresh cloud session ever sees — kept
reporting the old queue while five chunks came and went.

Nothing failed. That is the problem these tests exist to make impossible: a
status written where the deriving script cannot read it is decoration, and
`.claude/rules/ledger.md` already says status lives only in the queue table.
"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKLOG = PROJECT_ROOT / "backlog.md"

# Any markdown row carrying a backticked status is a status claim, whatever
# table it happens to sit in.
_STATUS_ROW = re.compile(
    r"^\|.*\|\s*`(?P<status>READY|IN_PROGRESS|BLOCKED|DONE|DEFERRED)`\s*\|"
)


def _repo_state():
    spec = importlib.util.spec_from_file_location(
        "repo_state", PROJECT_ROOT / "scripts" / "repo_state.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# The authoritative program, and the superseded one that follows it. Rows in
# superseded sections are historical record, not the tracker, and the 2026-09-10
# table carries an extra `Track` column that the parser has never read.
_CURRENT_PROGRAM = "## Reprioritized development program — 2026-09-15"
_SUPERSEDED_PROGRAM = "## Reprioritized development program — 2026-09-10"


@pytest.fixture(scope="module")
def backlog_lines() -> list[str]:
    return BACKLOG.read_text(encoding="utf-8").splitlines()


@pytest.fixture(scope="module")
def current_program_lines(backlog_lines) -> list[str]:
    start = next(
        index
        for index, line in enumerate(backlog_lines)
        if line.startswith(_CURRENT_PROGRAM)
    )
    end = next(
        index
        for index, line in enumerate(backlog_lines[start + 1 :], start=start + 1)
        if line.startswith(_SUPERSEDED_PROGRAM)
    )
    return backlog_lines[start:end]


def test_every_status_row_in_the_live_program_is_read_by_the_parser(
    current_program_lines,
):
    """A status the deriving script cannot see is not a status."""

    queue_row = _repo_state()._QUEUE_ROW
    unreadable = [
        line
        for line in current_program_lines
        if _STATUS_ROW.match(line) and not queue_row.match(line)
    ]
    assert not unreadable, (
        "These rows declare a status that scripts/repo_state.py ignores, so the"
        " session-start hook will never show them. Put them in the one Queue"
        " table with its order column, per .claude/rules/ledger.md:\n  "
        + "\n  ".join(unreadable)
    )


def test_the_superseded_program_is_marked_superseded(backlog_lines):
    """Its table is unreadable by design, so it must not look authoritative.

    The 2026-09-10 table uses a `Track` column the parser cannot read. That is
    fine for a historical record and dangerous for a live one, so the section
    has to say which it is.
    """

    start = next(
        index
        for index, line in enumerate(backlog_lines)
        if line.startswith(_SUPERSEDED_PROGRAM)
    )
    body = "\n".join(backlog_lines[start : start + 120]).lower()
    assert "superseded" in body


def test_the_parser_finds_the_whole_queue(backlog_lines):
    queue_row = _repo_state()._QUEUE_ROW
    parsed = [queue_row.match(line) for line in backlog_lines]
    chunks = [match.group("chunk").strip() for match in parsed if match]
    # Guards against a regex that matches nothing and a table that quietly
    # loses its tail.
    assert len(chunks) >= 20, chunks
    assert len(chunks) == len(set(chunks)), "a chunk is listed twice in the queue"


def test_the_cloud_operability_chunks_are_in_the_queue(backlog_lines):
    """The exact rows that were invisible when this file was written."""

    queue_row = _repo_state()._QUEUE_ROW
    statuses = {
        match.group("chunk").strip(): match.group("status")
        for match in (queue_row.match(line) for line in backlog_lines)
        if match
    }
    for chunk in ("X0", "X1", "X2", "X3", "X4", "P1b"):
        assert chunk in statuses, f"{chunk} is not in the queue table"


def test_every_queue_status_is_a_declared_status(backlog_lines):
    module = _repo_state()
    statuses = {
        match.group("status")
        for match in (module._QUEUE_ROW.match(line) for line in backlog_lines)
        if match
    }
    assert statuses <= set(module.VALID_STATUSES), statuses - set(module.VALID_STATUSES)


def test_the_ledger_stays_lf(backlog_lines):
    # `.claude/rules/ledger.md`: these files are LF. A CRLF write rewrites every
    # line and buries the real change.
    assert BACKLOG.read_bytes().count(b"\r\n") == 0


def test_the_guard_catches_the_row_shape_that_slipped_through():
    """The literal row that was invisible on 2026-09-19, as a regression.

    Without this, the guard could be weakened to a tautology and nothing would
    notice. It asserts both halves: the row reads as a status claim, and the
    queue parser does not see it.
    """

    invisible = (
        "| X0 | `DONE` | none | Baseline captured, egress probed, claim "
        "convention established as a GitHub issue |"
    )
    assert _STATUS_ROW.match(invisible), "the guard must recognise this as a status row"
    assert not _repo_state()._QUEUE_ROW.match(invisible), (
        "if the queue parser now reads this shape, the guard is no longer"
        " testing anything and should be rewritten around the new parser"
    )

    # And the shape that replaced it is read.
    readable = (
        "| 14 | X0 | `DONE` | none | Cloud baseline captured | Claims are "
        "invisible to a session that clones fresh |"
    )
    match = _repo_state()._QUEUE_ROW.match(readable)
    assert match and match.group("chunk").strip() == "X0"
    assert match.group("status") == "DONE"


# --- the operator-flag counter ------------------------------------------


def test_open_flags_come_only_from_the_live_ledger():
    """The count must mean "open", not "mentioned".

    `changelog.md` and `IMPLEMENTATION_STATUS.md` quote flags that were raised
    and ruled on, and sentences *about* flags matched as if they were flags. On
    2026-09-19 that reported 10 when 3 were open, with fragments like `'] flags'`
    in the list. A count wrong in the direction of more buries the real ones.
    """

    module = _repo_state()
    sources = {flag["file"] for flag in module.ben_flags()}
    assert "changelog.md" not in sources
    assert "IMPLEMENTATION_STATUS.md" not in sources
    assert sources <= {"backlog.md"} | {
        f"docs/chunks/{path.name}" for path in (PROJECT_ROOT / "docs" / "chunks").glob("*.md")
    }, sources


def test_every_reported_flag_has_real_text():
    """A flag whose text is a stray bracket is a false positive, not a flag."""

    for flag in _repo_state().ben_flags():
        text = flag["text"].strip()
        assert len(text) >= 12, flag
        assert not text.startswith(("]", "`", "*")), flag


def test_the_blockers_ben_actually_owns_are_flagged():
    """The two that gate every remaining chunk must be visible on startup."""

    joined = " ".join(flag["text"] for flag in _repo_state().ben_flags()).lower()
    assert "#19" in joined, "merging #18/#19 unblocks X1 and X3 and repairs the suite"
    assert "standings exports" in joined, "the corpus choice unblocks X2, then P0"
