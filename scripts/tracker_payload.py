"""Build Ben's plain-English roadmap tracker from the board and its cards.

The tracker is a published page whose rows live in the page's own database.
Two sources feed it: `docs/ROADMAP.md` (status, dependencies, operator items,
completion dates; read through `scripts/repo_state.py`, so "ready" here is
exactly what the session-start digest calls startable) and
`docs/tracker/plain.json` (the plain-English card for every board row and
operator item, written by whoever adds the row).

    python scripts/tracker_payload.py --check       # exit 1 naming every gap
    python scripts/tracker_payload.py --out <dir>   # one JSON file per database document

`--out` writes `<collection>.<doc_id>.json` files and prints the batch the
`ArtifactData` tool applies (`docs/claude/working.md` § The plain-English
tracker). No network, no writes outside `--out`.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROADMAP = PROJECT_ROOT / "docs" / "ROADMAP.md"
PLAIN = PROJECT_ROOT / "docs" / "tracker" / "plain.json"
PLAIN_REL = "docs/tracker/plain.json"
SCHEMA = "nfl_plain_tracker_v1"

# The page's database: one document per goal plus two board documents, so a
# full sync is one batch (at most 50 writes) and each document stays far
# below the 256 KiB limit.
MAX_DOCUMENTS = 50
MAX_DOCUMENT_BYTES = 256 * 1024

STATE_LABELS = {
    "done": "Done",
    "active": "In progress",
    "ready": "Ready to start",
    "you": "Waiting on you",
    "decision": "Needs your decision",
    "blocked": "Waiting on other work",
    "parked": "Parked",
}
CARD_FIELDS = ("goal", "title", "what", "why", "matters")
TODO_FIELDS = ("title", "what", "why")
# CLAUDE.md: a prior is never EV, ROI or a probability, and nothing is
# described as upload-ready. Plain cards are where that drifts first.
FORBIDDEN = re.compile(
    r"\b(EV|ROI|upload-ready|win probability|cash probability|proven edge|calibrated ownership)\b"
)
_COMPLETED = re.compile(
    r"^\| (?P<date>\d{4}-\d{2}-\d{2})[a-z]? \| Session (?P<id>[0-9]{2}[a-z]?) \| (?P<change>[^|]*?) \|", re.M
)


def _repo_state():
    spec = importlib.util.spec_from_file_location("repo_state_for_tracker", PROJECT_ROOT / "scripts" / "repo_state.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_plain(path: Path = PLAIN) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def completion_dates(text: str) -> dict[str, str]:
    """The last `... to Complete` date per session in the roadmap's ledger."""
    dates = {}
    for match in _COMPLETED.finditer(text):
        if match.group("change").strip().endswith("Complete"):
            dates["S" + match.group("id")] = match.group("date")
    return dates


def _satisfied(token: str, sessions: dict[str, str], operators: dict[str, str]) -> bool:
    if token == "none":
        return True
    if token.startswith("Session "):
        return sessions.get(token) == "Complete"
    if token.startswith("O"):
        return operators.get(token) == "Done"
    return False


def state_of(row: dict, sessions: dict[str, str], operators: dict[str, str]) -> str:
    """One display state per board row.

    `ready` is the digest's own `startable`. A Pending row that is not ready
    waits on other work while any session it depends on is open; once only
    Ben's items remain, it waits on his decision (`BEN ruling`) or on him.
    """
    status = row["status"]
    if status == "Complete":
        return "done"
    if status == "Deferred":
        return "parked"
    if status == "In Progress":
        return "active"
    if row.get("startable"):
        return "ready"
    unmet = [token for token in row["depends_on"] if not _satisfied(token, sessions, operators)]
    if any(token.startswith("Session ") for token in unmet):
        return "blocked"
    if "BEN ruling" in unmet:
        return "decision"
    return "you"


def coverage_gaps(plain: dict, queue: dict) -> list[str]:
    """Every reason the tracker would be wrong or incomplete, one line each."""
    if queue.get("error"):
        return [f"docs/ROADMAP.md is unreadable ({queue['error']}); fix the board first"]
    gaps = []
    if plain.get("schema_version") != SCHEMA:
        gaps.append(f"{PLAIN_REL}: schema_version must be {SCHEMA}")
    goals = {goal.get("key") for goal in plain.get("goals", [])}
    cards = plain.get("chunks", {})
    todos = plain.get("todos", {})
    board = {row["short"]: row for row in queue["rows"]}
    for short in board:
        if short not in cards:
            gaps.append(
                f"{short} is on the roadmap board but has no card: add \"{short}\" under \"chunks\" in "
                f"{PLAIN_REL} with {', '.join(CARD_FIELDS)} (plain English, written for Ben)"
            )
    for short, card in cards.items():
        if short not in board:
            gaps.append(f"{short} has a card in {PLAIN_REL} but no row on the roadmap board: remove the card")
            continue
        for field in CARD_FIELDS:
            if not str(card.get(field, "")).strip():
                gaps.append(f"{short}: card field \"{field}\" is empty in {PLAIN_REL}")
        if card.get("goal") and card["goal"] not in goals:
            gaps.append(f"{short}: goal \"{card['goal']}\" is not one of the goals in {PLAIN_REL}")
        if board[short]["status"] == "Deferred" and not str(card.get("return_when", "")).strip():
            gaps.append(f"{short} is Deferred: add \"return_when\" (what brings it back) to its card in {PLAIN_REL}")
    for item in queue["operators"]:
        if item["id"] not in todos:
            gaps.append(
                f"{item['id']} is an operator item but has no card: add \"{item['id']}\" under \"todos\" in "
                f"{PLAIN_REL} with {', '.join(TODO_FIELDS)}"
            )
    operator_ids = {item["id"] for item in queue["operators"]}
    for item_id, todo in todos.items():
        if item_id not in operator_ids:
            gaps.append(f"{item_id} has a to-do card in {PLAIN_REL} but no operator row in docs/ROADMAP.md: remove it")
        for field in TODO_FIELDS:
            if not str(todo.get(field, "")).strip():
                gaps.append(f"{item_id}: to-do field \"{field}\" is empty in {PLAIN_REL}")
    for decision in plain.get("decisions", []):
        for short in decision.get("holds_up", []):
            if short not in board:
                gaps.append(f"decision \"{decision.get('key')}\" holds up {short}, which is not on the board")
    # The words Ben reads; `about` is the note to authors and names the rule itself.
    text = json.dumps({key: value for key, value in plain.items() if key != "about"}, ensure_ascii=False)
    for match in sorted(set(FORBIDDEN.findall(text))):
        gaps.append(f"{PLAIN_REL} uses \"{match}\", which CLAUDE.md never allows to describe this engine")
    return gaps


def _waiting_on(row, sessions, operators, cards, todos) -> list[dict]:
    waits = []
    for token in row["depends_on"]:
        if _satisfied(token, sessions, operators):
            continue
        if token.startswith("Session "):
            short = token.replace("Session ", "S")
            waits.append({"kind": "work", "id": short, "label": cards.get(short, {}).get("title", short)})
        elif token.startswith("O"):
            waits.append({"kind": "todo", "id": token, "label": todos.get(token, {}).get("title", token)})
        else:
            waits.append({"kind": "decision", "id": "", "label": "Your decision"})
    return waits


def build(plain: dict, queue: dict, dates: dict[str, str], *, now: datetime, commit: str) -> dict[tuple[str, str], dict]:
    """The database documents, keyed by (collection, doc_id)."""
    gaps = coverage_gaps(plain, queue)
    if gaps:
        raise ValueError("\n".join(gaps))
    cards, todos = plain["chunks"], plain["todos"]
    sessions = {row["session"]: row["status"] for row in queue["rows"]}
    operators = {item["id"]: item["status"] for item in queue["operators"]}

    chunks = []
    for order, row in enumerate(queue["rows"], start=1):
        card = cards[row["short"]]
        state = state_of(row, sessions, operators)
        chunk = {
            "id": row["short"],
            "order": order,
            "goal": card["goal"],
            "title": card["title"],
            "what": card["what"],
            "why": card["why"],
            "matters": card["matters"],
            "state": state,
            "state_label": STATE_LABELS[state],
            "done_date": dates.get(row["short"]) if state == "done" else None,
            "waiting_on": [] if state in ("done", "ready", "active") else _waiting_on(row, sessions, operators, cards, todos),
        }
        for optional in ("note", "return_when"):
            if card.get(optional):
                chunk[optional] = card[optional]
        chunks.append(chunk)

    def counts(items):
        tally = {state: 0 for state in STATE_LABELS}
        for item in items:
            tally[item["state"]] += 1
        return tally

    documents = {}
    for order, goal in enumerate(plain["goals"], start=1):
        mine = [chunk for chunk in chunks if chunk["goal"] == goal["key"]]
        documents[("goals", goal["key"])] = {
            "key": goal["key"],
            "order": order,
            "title": goal["title"],
            "tagline": goal["tagline"],
            "why": goal["why"],
            "total": len(mine),
            "counts": counts(mine),
            "chunks": {chunk["id"]: chunk for chunk in mine},
        }

    by_id = {chunk["id"]: chunk for chunk in chunks}
    finished = sorted(
        (chunk for chunk in chunks if chunk["state"] == "done" and chunk["done_date"]),
        key=lambda chunk: (chunk["done_date"], chunk["order"]),
        reverse=True,
    )
    documents[("board", "meta")] = {
        "schema_version": SCHEMA,
        "updated_at": now.astimezone(timezone.utc).isoformat(timespec="seconds"),
        "source_commit": commit,
        "total": len(chunks),
        "counts": counts(chunks),
        "next_up": [
            {"id": chunk["id"], "title": chunk["title"], "goal": chunk["goal"]}
            for chunk in chunks
            if chunk["state"] in ("active", "ready")
        ][:3],
        "recent": [
            {"id": chunk["id"], "title": chunk["title"], "goal": chunk["goal"], "done_date": chunk["done_date"]}
            for chunk in finished[:6]
        ],
    }

    unblocks = {}
    for row in queue["rows"]:
        for token in row["depends_on"]:
            if token.startswith("O") and row["status"] != "Complete":
                unblocks.setdefault(token, []).append({"id": row["short"], "title": by_id[row["short"]]["title"]})
    todo_docs = []
    for item in queue["operators"]:
        todo = todos[item["id"]]
        opens = unblocks.get(item["id"], [])
        entry = {
            "id": item["id"],
            "title": todo["title"],
            "what": todo["what"],
            "why": todo["why"],
            "done": item["status"] == "Done",
            "unblocks": opens,
            # "now": the only thing between a built chunk and its finish (the
            # chunk waits on Ben alone), or the card says so (`"now": true`).
            "now": item["status"] != "Done"
            and (bool(todo.get("now")) or any(by_id[opened["id"]]["state"] == "you" for opened in opens)),
        }
        if todo.get("note"):
            entry["note"] = todo["note"]
        todo_docs.append(entry)
    documents[("board", "you")] = {
        "todos": todo_docs,
        "decisions": [
            {
                "key": decision["key"],
                "title": decision["title"],
                "question": decision["question"],
                "recommendation": decision["recommendation"],
                "holds_up": [{"id": short, "title": by_id[short]["title"]} for short in decision.get("holds_up", [])],
            }
            for decision in plain.get("decisions", [])
        ],
    }

    if len(documents) > MAX_DOCUMENTS:
        raise ValueError(f"{len(documents)} documents exceed one batch ({MAX_DOCUMENTS})")
    for (collection, doc_id), body in documents.items():
        size = len(json.dumps(body, ensure_ascii=False).encode("utf-8"))
        if size > MAX_DOCUMENT_BYTES:
            raise ValueError(f"{collection}/{doc_id} is {size} bytes, over {MAX_DOCUMENT_BYTES}")
    return documents


def _commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=10
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    return result.stdout.strip() or "unknown"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="report coverage gaps and exit 1 if any")
    mode.add_argument("--out", type=Path, help="directory for one JSON file per database document")
    args = parser.parse_args(argv)

    repo_state = _repo_state()
    queue = repo_state.session_queue()
    plain = load_plain()
    gaps = coverage_gaps(plain, queue)
    if gaps:
        print(f"{len(gaps)} tracker gap(s):", file=sys.stderr)
        for gap in gaps:
            print(f"  - {gap}", file=sys.stderr)
        return 1
    if args.check:
        print(f"tracker OK: {len(queue['rows'])} cards, {len(queue['operators'])} to-dos")
        return 0

    dates = completion_dates(ROADMAP.read_text(encoding="utf-8"))
    documents = build(plain, queue, dates, now=datetime.now(timezone.utc), commit=_commit())
    args.out.mkdir(parents=True, exist_ok=True)
    writes = []
    for (collection, doc_id), body in documents.items():
        path = args.out / f"{collection}.{doc_id}.json"
        path.write_bytes((json.dumps(body, indent=1, ensure_ascii=False) + "\n").encode("utf-8"))
        writes.append({"collection": collection, "doc_id": doc_id, "file_path": str(path.resolve())})
    meta = documents[("board", "meta")]
    print(json.dumps({"counts": meta["counts"], "next_up": [item["id"] for item in meta["next_up"]], "writes": writes}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
