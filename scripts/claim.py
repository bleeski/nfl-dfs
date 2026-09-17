#!/usr/bin/env python3
"""Claim a chunk, so two Claude Code instances do not take the same one.

`state/claims.json` and the reader in `scripts/repo_state.py` have existed since
2026-09-17, and `.claude/skills/dev-session/SKILL.md` has told every session to
write a claim. Nothing ever wrote one, so the file stayed `{"claims": []}` and
the instruction was decorative. This is the writer.

    python3 scripts/claim.py take P0 --branch claude/p0-standings-grading-harness
    python3 scripts/claim.py release P0
    python3 scripts/claim.py show

What this is and is not. It is a coordination primitive: a claim travels in git,
so a concurrent instance can see it, and `take` refuses a chunk somebody else
holds. It is not an enforcement mechanism, and nothing here can stop a session
that ignores the refusal, any more than a rule file can. It is the same class of
control as merge-on-green: a convention every instance clones.

A claim older than six hours is stale and may be taken. Taking it records what
was displaced, in the tracked file rather than only in a terminal, so the
reclaim survives the session that did it.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CLAIMS_FILE = PROJECT_ROOT / "state" / "claims.json"
SCHEMA_VERSION = "nfl_chunk_claims_v1"

sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from repo_state import STALE_CLAIM_HOURS, claims as read_claims  # noqa: E402


def agent_label() -> str:
    """Who holds the claim. A session id where there is one, else host and pid."""
    for name in ("NFL_DFS_AGENT", "CLAUDE_CODE_SESSION_ID", "CLAUDE_SESSION_ID"):
        value = os.environ.get(name)
        if value:
            return value[:64]
    return f"{socket.gethostname()}/{os.getpid()}"


def current_branch() -> str:
    import subprocess

    try:
        result = subprocess.run(
            ("git", "rev-parse", "--abbrev-ref", "HEAD"),
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def load(path: Path = CLAIMS_FILE) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    payload.setdefault("schema_version", SCHEMA_VERSION)
    entries = payload.get("claims")
    payload["claims"] = entries if isinstance(entries, list) else []
    return payload


def save(payload: dict, path: Path = CLAIMS_FILE) -> None:
    """LF, sorted, trailing newline: two instances should produce a small diff."""
    payload["claims"] = sorted(payload["claims"], key=lambda entry: str(entry.get("chunk", "")))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )


def _age_hours(entry: dict, now: datetime) -> float | None:
    raw = entry.get("claimed_at", "")
    try:
        when = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None
    return (now - when).total_seconds() / 3600.0


def take(
    chunk: str,
    branch: str,
    agent: str,
    now: datetime,
    note: str | None = None,
    path: Path = CLAIMS_FILE,
) -> tuple[int, str]:
    """Claim `chunk`. Returns (exit code, what to say)."""
    payload = load(path)
    held = [entry for entry in payload["claims"] if entry.get("chunk") == chunk]
    others = [entry for entry in payload["claims"] if entry.get("chunk") != chunk]

    reclaimed_from = None
    for entry in held:
        age = _age_hours(entry, now)
        if entry.get("agent") == agent:
            continue  # Re-claiming your own chunk is idempotent.
        if age is not None and age <= STALE_CLAIM_HOURS:
            return 1, (
                f"{chunk} is already claimed by {entry.get('agent', '?')} on "
                f"{entry.get('branch', '?')}, {age:.1f}h ago. A claim is stale "
                f"only after {STALE_CLAIM_HOURS}h. Stop, and say so."
            )
        reclaimed_from = {
            "agent": entry.get("agent"),
            "branch": entry.get("branch"),
            "claimed_at": entry.get("claimed_at"),
            "age_hours": round(age, 1) if age is not None else None,
        }

    claim = {
        "chunk": chunk,
        "agent": agent,
        "branch": branch,
        "claimed_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if note:
        claim["note"] = note
    if reclaimed_from:
        claim["reclaimed_from"] = reclaimed_from
    save({**payload, "claims": [*others, claim]}, path)

    if reclaimed_from:
        age = reclaimed_from["age_hours"]
        return 0, (
            f"Reclaimed {chunk} from {reclaimed_from['agent']} on "
            f"{reclaimed_from['branch']}, whose claim was "
            f"{age if age is not None else 'of unreadable age'}h old. "
            "Recorded in state/claims.json as `reclaimed_from`; say so in the "
            "changelog too."
        )
    return 0, f"Claimed {chunk} on {branch} as {agent}. Push the claim before writing code."


def release(chunk: str, agent: str, path: Path = CLAIMS_FILE) -> tuple[int, str]:
    payload = load(path)
    kept = [entry for entry in payload["claims"] if entry.get("chunk") != chunk]
    if len(kept) == len(payload["claims"]):
        return 0, f"No claim on {chunk} to release."
    save({**payload, "claims": kept}, path)
    return 0, f"Released {chunk}."


def show(now: datetime) -> tuple[int, str]:
    state = read_claims(now)
    lines = []
    for entry in state["active"]:
        lines.append(
            f"ACTIVE  {entry.get('chunk')} by {entry.get('agent', '?')} on "
            f"{entry.get('branch', '?')} ({entry.get('age_hours')}h ago)"
        )
    for entry in state["stale"]:
        lines.append(
            f"STALE   {entry.get('chunk')} by {entry.get('agent', '?')} on "
            f"{entry.get('branch', '?')} ({entry.get('age_hours')}h ago), reclaimable"
        )
    return 0, "\n".join(lines) if lines else "No claims."


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)

    taker = sub.add_parser("take", help="claim a chunk before writing code")
    taker.add_argument("chunk")
    taker.add_argument("--branch", default=None)
    taker.add_argument("--agent", default=None)
    taker.add_argument("--note", default=None)

    releaser = sub.add_parser("release", help="release a claim at close-out")
    releaser.add_argument("chunk")
    releaser.add_argument("--agent", default=None)

    sub.add_parser("show", help="print active and stale claims")

    args = parser.parse_args(argv)
    now = datetime.now(timezone.utc)

    if args.action == "take":
        code, message = take(
            args.chunk,
            args.branch or current_branch(),
            args.agent or agent_label(),
            now,
            args.note,
        )
    elif args.action == "release":
        code, message = release(args.chunk, args.agent or agent_label())
    else:
        code, message = show(now)

    print(message)
    return code


if __name__ == "__main__":
    sys.exit(main())
