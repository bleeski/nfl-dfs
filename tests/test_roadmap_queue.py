"""The roadmap's status board is the tracker, so it must actually be parseable.

History this file carries forward. On 2026-09-19 a second status table was
added to `backlog.md` with its own column layout. `scripts/repo_state.py`'s
parser required a leading order column, so it matched none of those rows and
silently ignored them: the session-start hook, the only status a fresh cloud
session ever sees, kept reporting the old queue while five chunks came and
went. Nothing failed.

On 2026-09-22 the queue moved to `docs/ROADMAP.md` (Session 00) and this file
replaced `tests/test_backlog_queue.py`. The invariants are the same and
stricter: every status row is read by the parser, every status is declared, an
unreadable board is reported loudly rather than as an empty queue, and the
Quick-Start block names the session the table says is next.
"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROADMAP = PROJECT_ROOT / "docs" / "ROADMAP.md"
BACKLOG_STUB = PROJECT_ROOT / "backlog.md"

# Any markdown row that starts with a session ID is a status claim, whichever
# table it happens to sit in.
_SESSION_ROW = re.compile(r"^\|\s*Session [0-9]{2}[a-z]?\s*\|")
_CARD_HEADING = re.compile(
    r"^####\s+Sessions?\s+(?P<first>[0-9]{2})[a-z]?(?:\s+to\s+(?P<last>[0-9]{2}))?\b"
)


def _repo_state():
    spec = importlib.util.spec_from_file_location(
        "repo_state_for_roadmap", PROJECT_ROOT / "scripts" / "repo_state.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def repo_state():
    return _repo_state()


@pytest.fixture(scope="module")
def roadmap_lines() -> list[str]:
    return ROADMAP.read_text(encoding="utf-8").splitlines()


@pytest.fixture(scope="module")
def board(repo_state):
    sessions, operators = repo_state.read_roadmap()
    return sessions, operators


# --- the board parses, completely ----------------------------------------


def test_the_real_board_parses_without_error(repo_state):
    queue = repo_state.session_queue()
    assert queue["error"] is None, queue["error"]
    assert len(queue["rows"]) >= 30, "the board lost rows"


def test_every_session_row_sits_inside_the_markers(repo_state, roadmap_lines):
    """A status row the parser cannot see is not a status."""

    start = roadmap_lines.index(repo_state.TABLE_START)
    end = roadmap_lines.index(repo_state.TABLE_END)
    outside = [
        line
        for index, line in enumerate(roadmap_lines)
        if _SESSION_ROW.match(line) and not start < index < end
    ]
    assert not outside, (
        "These rows look like session status but sit outside the marked status"
        " board, so scripts/repo_state.py never reads them:\n  " + "\n  ".join(outside)
    )


def test_session_ids_are_unique_and_session_00_leads(board, repo_state):
    """Row order is priority; a session's number is its stable name.

    Until 2026-09-25 this test also required the numbers to ascend, which made
    the number the rank. The consolidation of that date re-ranked the board by
    expected winnings and kept every number (the rulings, the changelog and the
    chunk briefs cite them), so a new session takes the next free number
    wherever its row sits. `docs/ROADMAP.md` §2.1 and `.claude/rules/ledger.md`
    state the rule; the dependency test below still forbids a row that depends
    on a later row, which is the invariant the ordering actually protects.
    """

    sessions, _ = board
    ids = [row["session"] for row in sessions]
    assert len(ids) == len(set(ids)), "a session is listed twice"
    assert all(repo_state._SESSION_ID.match(value) for value in ids)
    assert ids[0] == "Session 00"


def test_every_status_is_declared(board, repo_state):
    sessions, operators = board
    assert {row["status"] for row in sessions} <= set(repo_state.VALID_STATUSES)
    assert {item["status"] for item in operators} <= set(repo_state.OPERATOR_STATUSES)


def test_every_dependency_resolves_and_points_backwards(board):
    """A dependency on a later row is a cycle waiting to happen."""

    sessions, operators = board
    position = {row["session"]: index for index, row in enumerate(sessions)}
    operator_ids = {item["id"] for item in operators}
    for index, row in enumerate(sessions):
        for token in row["depends_on"]:
            if token.startswith("Session "):
                assert token in position, f"{row['session']} depends on missing {token}"
                assert position[token] < index, f"{row['session']} depends on later {token}"
            elif token.startswith("O"):
                assert token in operator_ids, f"{row['session']} depends on missing {token}"


def test_every_open_session_names_a_verification_command(board):
    for row in board[0]:
        if row["status"] in ("Pending", "In Progress"):
            assert re.search(r"nfl\.sh|nfl\.ps1|python3|grep", row["verification"]), row["session"]


def test_every_session_has_a_card(board, roadmap_lines):
    covered: set[int] = set()
    for line in roadmap_lines:
        match = _CARD_HEADING.match(line)
        if match:
            first = int(match.group("first"))
            last = int(match.group("last") or first)
            covered.update(range(first, last + 1))
    missing = [row["session"] for row in board[0] if int(row["session"][8:10]) not in covered]
    assert not missing, f"no card in §2.3 for {missing}"


# --- the parser refuses what it cannot read ------------------------------


_HEADER = (
    "| Session ID | Type | Work Unit & Scope | Source Origin | Target Files |"
    " Classification | Depends on | Verification Command / Breakpoint | Status |"
)
_RULE = "|---|---|---|---|---|---|---|---|---|"
_OPERATORS = (
    "<!-- operator-table:start -->\n| ID | Item | Unblocks | Status |\n|---|---|---|---|\n"
    "| O1 | Copy files | Session 02 | Open |\n<!-- operator-table:end -->\n"
)


def _write(tmp_path: Path, rows: list[str], operators: str = _OPERATORS) -> Path:
    path = tmp_path / "ROADMAP.md"
    body = "\n".join(["<!-- roadmap-table:start -->", _HEADER, _RULE, *rows, "<!-- roadmap-table:end -->"])
    path.write_text(body + "\n\n" + operators, encoding="utf-8")
    return path


def _row(session: str, depends: str, status: str) -> str:
    return f"| {session} | Batched | scope | source | files | P | {depends} | `sh ./nfl.sh test` | {status} |"


def test_missing_markers_are_an_error_not_an_empty_queue(repo_state, tmp_path):
    path = tmp_path / "ROADMAP.md"
    path.write_text(_HEADER + "\n" + _RULE + "\n" + _row("Session 00", "none", "Pending") + "\n", encoding="utf-8")
    queue = repo_state.session_queue(path)
    assert queue["rows"] == []
    assert queue["error"] and "MARKERS_MISSING" in queue["error"]


def test_the_digest_says_so_when_the_board_is_unreadable(repo_state, tmp_path):
    state = {
        "git": {
            "branch": "b", "head": "h", "dirty_paths": 0, "untracked_paths": 0,
            "behind_origin_main": "0", "origin_main_fetch": {"ok": True}, "recent_commits": [],
        },
        "queue_error": "MARKERS_MISSING:x",
        "ready_chunks": [],
        "in_progress_chunks": [],
        "claims": {"active": [], "stale": []},
        "verification": {"known": False},
        "calibration": {"slates_graded": 0, "slates_recorded": 0, "model_status": "PRIOR_ONLY", "release_decision": "DO_NOT_UPLOAD"},
        "ben_flags": [],
    }
    assert "ROADMAP UNREADABLE" in repo_state.digest(state)


@pytest.mark.parametrize(
    "row, reason",
    [
        (_row("Session 00", "none", "READY"), "STATUS_UNDECLARED"),
        (_row("Session 00", "the P0 brief", "Pending"), "DEPENDENCY_UNREADABLE"),
        (_row("S00", "none", "Pending"), "SESSION_ID_UNREADABLE"),
        ("| Session 00 | Batched | scope | Pending |", "ROW_WIDTH"),
    ],
)
def test_a_malformed_row_is_refused_by_name(repo_state, tmp_path, row, reason):
    queue = repo_state.session_queue(_write(tmp_path, [row]))
    assert queue["error"] and reason in queue["error"], queue["error"]


def test_startability_is_derived_from_dependencies(repo_state, tmp_path):
    path = _write(
        tmp_path,
        [
            _row("Session 00", "none", "Complete"),
            _row("Session 01", "Session 00", "Pending"),
            _row("Session 02", "Session 01", "Pending"),
            _row("Session 03", "Session 00, O1", "Pending"),
            _row("Session 04", "BEN ruling", "Pending"),
            _row("Session 05", "none", "Deferred"),
        ],
    )
    rows = {row["session"]: row for row in repo_state.session_queue(path)["rows"]}
    assert rows["Session 01"]["startable"]
    assert not rows["Session 02"]["startable"], "its dependency is only Pending"
    assert not rows["Session 03"]["startable"], "O1 is still Open"
    assert not rows["Session 04"]["startable"], "a ruling is never satisfied by the table"
    assert not rows["Session 05"]["startable"], "Deferred is never startable"


def test_a_done_operator_item_satisfies_its_dependency(repo_state, tmp_path):
    operators = _OPERATORS.replace("| Open |", "| Done |")
    path = _write(tmp_path, [_row("Session 00", "O1", "Pending")], operators)
    (row,) = repo_state.session_queue(path)["rows"]
    assert row["startable"]


# --- the board and the prose agree ---------------------------------------


def test_the_quick_start_names_the_first_startable_session(repo_state, roadmap_lines):
    """Close-out rewrites §1; this catches the close-out that forgot to."""

    text = "\n".join(roadmap_lines)
    quick_start = text.split("## 1. Next Session Quick-Start", 1)[1].split("## 2.", 1)[0]
    named = re.search(r"execute (Session [0-9]{2}[a-z]?)", quick_start)
    assert named, "the Quick-Start prompt names no session"
    startable = [row["session"] for row in repo_state.session_queue()["rows"] if row.get("startable")]
    assert startable, "nothing is startable, so the Quick-Start cannot be right"
    assert named.group(1) == startable[0], (named.group(1), startable[:3])


def test_a_session_waiting_on_ben_carries_its_question(repo_state, roadmap_lines):
    """If the board says a session waits on Ben, its card must show him the question.

    The old version of this test pinned a pull-request number, then a phrase,
    and failed both times the moment Ben ruled. The invariant underneath does
    not expire: a ruling closes the flag and the dependency together.
    """

    text = "\n".join(roadmap_lines)
    for row in repo_state.session_queue()["rows"]:
        if "BEN ruling" not in row["depends_on"]:
            continue
        number = row["session"][8:10]
        card = text.split(f"#### Session {number}", 1)
        assert len(card) == 2, f"{row['session']} waits on Ben and has no card"
        body = card[1].split("\n#### ", 1)[0]
        assert "[BEN:" in body, f"{row['session']} waits on a ruling and its card asks nothing"


def test_the_retired_backlog_is_a_pointer_not_a_queue():
    text = BACKLOG_STUB.read_text(encoding="utf-8")
    assert "docs/ROADMAP.md" in text
    assert len(text.splitlines()) <= 20
    assert not re.search(r"`(READY|IN_PROGRESS|BLOCKED|DONE|DEFERRED)`", text)
    assert "[BEN:" not in text


# --- the operator-flag counter ------------------------------------------


def test_open_flags_come_only_from_the_live_ledger(repo_state):
    """The count must mean "open", not "mentioned".

    `changelog.md` and `IMPLEMENTATION_STATUS.md` quote flags that were raised
    and ruled on, and sentences about flags matched as if they were flags. On
    2026-09-19 that reported 10 when 3 were open. A count wrong in the direction
    of more buries the real ones.
    """

    sources = {flag["file"] for flag in repo_state.ben_flags()}
    assert sources <= {"docs/ROADMAP.md"} | {
        f"docs/chunks/{path.name}" for path in (PROJECT_ROOT / "docs" / "chunks").glob("*.md")
    }, sources


def test_every_reported_flag_has_real_text(repo_state):
    """A flag whose text is a stray bracket is a false positive, not a flag."""

    for flag in repo_state.ben_flags():
        text = flag["text"].strip()
        assert len(text) >= 12, flag
        assert not text.startswith(("]", "`", "*")), flag


# --- line endings --------------------------------------------------------


@pytest.mark.parametrize(
    "relative", ["docs/ROADMAP.md", "backlog.md", "changelog.md", "IMPLEMENTATION_STATUS.md"]
)
def test_the_ledgers_stay_lf(relative):
    # `.claude/rules/ledger.md`: these files are LF. A CRLF write rewrites every
    # line and buries the real change.
    assert (PROJECT_ROOT / relative).read_bytes().count(b"\r\n") == 0
