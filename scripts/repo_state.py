#!/usr/bin/env python3
"""Derive the repository's current state, so no session has to be told it.

Several Claude Code instances work this repository without knowing about each
other. Hand-maintained status rots the moment two of them disagree; this script
reads the state back out of the files that are already authoritative and writes
one small machine-readable summary at ``state/repo-state.json``.

It is a reader. It never edits a ledger, never touches ``data/``, and never
reaches the network.

    python3 scripts/repo_state.py            # write state/repo-state.json
    python3 scripts/repo_state.py --print    # write it and print the digest
    python3 scripts/repo_state.py --stdout   # digest only, write nothing

The digest is what ``.claude/hooks/session_start.py`` injects at session start.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = PROJECT_ROOT / "state"
STATE_FILE = STATE_DIR / "repo-state.json"
CLAIMS_FILE = STATE_DIR / "claims.json"
LAST_VERIFY_FILE = STATE_DIR / "last-verify.json"
BACKLOG = PROJECT_ROOT / "backlog.md"
CHUNKS_DIR = PROJECT_ROOT / "docs" / "chunks"
RECORDS_DIR = PROJECT_ROOT / "records" / "slates"

SCHEMA_VERSION = "nfl_repo_state_v1"
VALID_STATUSES = ("READY", "IN_PROGRESS", "BLOCKED", "DONE", "DEFERRED")
STALE_CLAIM_HOURS = 6

# `| 0 | P0 | `READY` | none (operator item 2 first) | ... |`
_QUEUE_ROW = re.compile(
    r"^\|\s*(?P<order>[0-9]+[a-z]?)\s*\|\s*(?P<chunk>[A-Za-z0-9 ,to]+?)\s*\|\s*"
    r"`(?P<status>[A-Z_]+)`\s*\|\s*(?P<depends>[^|]*?)\s*\|"
)
# A flag can wrap across lines, so match from the marker to the end of the line
# and strip a closing bracket if one is there. The bare `[BEN: ...]` placeholder
# that appears in changelog prose is not a flag.
_BEN_FLAG = re.compile(r"\[BEN:\s*(?P<text>.*)")
_BEN_PLACEHOLDER = "..."


def _git(*args: str, default: str = "") -> str:
    try:
        result = subprocess.run(
            ("git", *args),
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return default
    return result.stdout.strip() if result.returncode == 0 else default


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def git_state() -> dict:
    dirty = [line for line in _git("status", "--porcelain").splitlines() if line.strip()]
    branch = _git("rev-parse", "--abbrev-ref", "HEAD", default="unknown")
    ahead_behind = _git("rev-list", "--left-right", "--count", "origin/main...HEAD")
    behind = ahead = None
    if ahead_behind and "\t" in ahead_behind:
        left, _, right = ahead_behind.partition("\t")
        behind, ahead = left.strip(), right.strip()
    return {
        "branch": branch,
        "head": _git("rev-parse", "--short", "HEAD"),
        "dirty_paths": len(dirty),
        "untracked_paths": sum(1 for line in dirty if line.startswith("??")),
        "behind_origin_main": behind,
        "ahead_of_origin_main": ahead,
        "recent_commits": _git("log", "--oneline", "-5").splitlines(),
    }


def chunk_queue() -> list[dict]:
    """Chunk IDs and statuses, read out of the backlog Queue table."""
    if not BACKLOG.is_file():
        return []
    rows: list[dict] = []
    for line in BACKLOG.read_text(encoding="utf-8").splitlines():
        match = _QUEUE_ROW.match(line)
        if not match:
            continue
        status = match.group("status")
        if status not in VALID_STATUSES:
            continue
        chunk = match.group("chunk").strip()
        brief = next(iter(sorted(CHUNKS_DIR.glob(f"{chunk}-*.md"))), None)
        rows.append(
            {
                "order": match.group("order"),
                "chunk": chunk,
                "status": status,
                "depends_on": match.group("depends").strip(),
                "brief": str(brief.relative_to(PROJECT_ROOT)) if brief else None,
            }
        )
    return rows


def claims(now: datetime) -> dict:
    payload = _read_json(CLAIMS_FILE) or {}
    entries = payload.get("claims", []) if isinstance(payload, dict) else []
    active, stale = [], []
    for entry in entries:
        claimed_at = entry.get("claimed_at", "")
        try:
            when = datetime.fromisoformat(claimed_at.replace("Z", "+00:00"))
        except (AttributeError, ValueError):
            stale.append({**entry, "age_hours": None})
            continue
        age_hours = (now - when).total_seconds() / 3600.0
        record = {**entry, "age_hours": round(age_hours, 1)}
        (stale if age_hours > STALE_CLAIM_HOURS else active).append(record)
    return {"active": active, "stale": stale, "stale_after_hours": STALE_CLAIM_HOURS}


def ben_flags() -> list[dict]:
    """Open `[BEN: ...]` questions, the facts only Ben can supply.

    `changelog.md` and `IMPLEMENTATION_STATUS.md` are deliberately not scanned.
    They are the historical record: they quote flags that were raised, ruled on
    and closed, and every sentence *about* a flag ("the `[BEN: ...]` flags went
    7 to 9") matched as if it were one. On 2026-09-19 that inflated the count
    to 10 when three were actually open, with fragments like `'] flags'` and
    `']` question'` sitting in the list. A count that is wrong in the direction
    of more is worse than no count: it buries the real blockers.

    `.claude/rules/ledger.md` says a flag lives in `backlog.md` and is listed
    again in the handoff, so `backlog.md` and the live chunk briefs are the
    only places an *open* flag can be.
    """

    found: list[dict] = []
    roots = [BACKLOG]
    roots.extend(sorted(CHUNKS_DIR.glob("*.md")))
    for path in roots:
        if not path.is_file():
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            match = _BEN_FLAG.search(line)
            if not match:
                continue
            text = match.group("text").strip().rstrip("]").strip().strip("*").strip()
            if not text or text.startswith(_BEN_PLACEHOLDER):
                continue
            found.append(
                {
                    "file": str(path.relative_to(PROJECT_ROOT)),
                    "line": number,
                    "text": text[:160],
                }
            )
    return found


def verification() -> dict:
    """The last recorded suite result. Local runs and CI both land here."""
    recorded = _read_json(LAST_VERIFY_FILE) or _read_json(STATE_DIR / "last-ci.json")
    if not isinstance(recorded, dict):
        return {"known": False}
    return {
        "known": True,
        "result_line": recorded.get("result_line"),
        "commit": recorded.get("commit"),
        "observed_at": recorded.get("observed_at"),
        "source": recorded.get("source", "ci"),
    }


def calibration() -> dict:
    """How much graded evidence exists. Zero is the honest answer until P0 lands."""
    slates = sorted(p.name for p in RECORDS_DIR.glob("*") if p.is_dir()) if RECORDS_DIR.is_dir() else []
    graded = [name for name in slates if (RECORDS_DIR / name / "outcome.jsonl").is_file()]
    return {
        "records_dir": str(RECORDS_DIR.relative_to(PROJECT_ROOT)),
        "slates_recorded": len(slates),
        "slates_graded": len(graded),
        "model_status": "PRIOR_ONLY",
        "release_decision": "DO_NOT_UPLOAD",
        "note": (
            "Player-week grading needs P0. Portfolio and ROI promotion additionally "
            "need settled contests, of which there are none."
        ),
    }


def build_state(now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    queue = chunk_queue()
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git": git_state(),
        "queue": queue,
        "ready_chunks": [row["chunk"] for row in queue if row["status"] == "READY"],
        "in_progress_chunks": [row["chunk"] for row in queue if row["status"] == "IN_PROGRESS"],
        "claims": claims(now),
        "ben_flags": ben_flags(),
        "verification": verification(),
        "calibration": calibration(),
    }


def digest(state: dict) -> str:
    git = state["git"]
    lines = [
        f"branch {git['branch']} @ {git['head']}"
        f"  dirty {git['dirty_paths']} ({git['untracked_paths']} untracked)"
        + (f"  behind origin/main by {git['behind_origin_main']}" if git.get("behind_origin_main") not in (None, "0") else ""),
    ]
    for commit in git["recent_commits"][:5]:
        lines.append(f"  {commit}")

    ready = ", ".join(state["ready_chunks"]) or "none"
    in_progress = ", ".join(state["in_progress_chunks"]) or "none"
    lines.append(f"chunks READY: {ready}")
    lines.append(f"chunks IN_PROGRESS: {in_progress}")

    active = state["claims"]["active"]
    if active:
        for entry in active:
            lines.append(
                f"  CLAIMED {entry.get('chunk')} by {entry.get('agent', '?')} "
                f"on {entry.get('branch', '?')} ({entry.get('age_hours')}h ago)"
            )
    stale = state["claims"]["stale"]
    if stale:
        lines.append(f"  {len(stale)} stale claim(s), reclaimable")

    verify = state["verification"]
    lines.append(
        f"last suite: {verify.get('result_line')} ({verify.get('source')}, {verify.get('observed_at')})"
        if verify.get("known")
        else "last suite: unknown, run /verify"
    )

    cal = state["calibration"]
    lines.append(
        f"calibration: {cal['slates_graded']}/{cal['slates_recorded']} slates graded; "
        f"{cal['model_status']} / {cal['release_decision']}"
    )

    flags = state["ben_flags"]
    if flags:
        lines.append(f"open [BEN:] flags: {len(flags)}")
        for flag in flags[:3]:
            lines.append(f"  {flag['file']}:{flag['line']} {flag['text'][:90]}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--print", dest="show", action="store_true", help="write, then print the digest")
    parser.add_argument("--stdout", action="store_true", help="print the digest and write nothing")
    args = parser.parse_args(argv)

    state = build_state()
    if not args.stdout:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8", newline="\n")
    if args.show or args.stdout:
        print(digest(state))
    elif not args.stdout:
        print(f"wrote {STATE_FILE.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
