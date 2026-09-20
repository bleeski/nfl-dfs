#!/usr/bin/env python3
"""Derive the repository's current state, so no session has to be told it.

Several Claude Code instances work this repository without knowing about each
other. Hand-maintained status rots the moment two of them disagree; this script
reads the state back out of the files that are already authoritative and writes
one small machine-readable summary at ``state/repo-state.json``.

It is a reader of the repository's own files. It edits no ledger and never
touches ``data/``. The one network call it makes is a ``git fetch`` of
``origin/main``, because the number this script exists to report is a distance
from a remote-tracking ref, and such a ref only moves on fetch. Without it the
single number meant to say "another instance changed things" is the one number
guaranteed to be stale. The fetch is bounded, cached, and never fatal: when it
cannot run, the digest says so rather than reporting a false zero.

    python3 scripts/repo_state.py            # write state/repo-state.json
    python3 scripts/repo_state.py --print    # write it and print the digest
    python3 scripts/repo_state.py --stdout   # digest only, write nothing

The digest is what ``.claude/hooks/session_start.py`` injects at session start.
"""

from __future__ import annotations

import argparse
import json
import os
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
LAST_FETCH_FILE = STATE_DIR / "last-fetch.json"
BACKLOG = PROJECT_ROOT / "backlog.md"
CHANGELOG = PROJECT_ROOT / "changelog.md"
CHUNKS_DIR = PROJECT_ROOT / "docs" / "chunks"
RECORDS_DIR = PROJECT_ROOT / "records" / "slates"

SCHEMA_VERSION = "nfl_repo_state_v1"
VALID_STATUSES = ("READY", "IN_PROGRESS", "BLOCKED", "DONE", "DEFERRED")
STALE_CLAIM_HOURS = 6

# Fetch bounds. A session start runs on `startup|resume|clear|compact`, so the
# TTL is what keeps a `/clear` from paying for the network again; the timeout is
# what keeps a bad network from eating the hook's 10-second budget. Measured
# 2026-09-17 in a container: a network read of `origin/main` costs 0.62 to
# 0.89 s, so 3 s is roughly four times the worst case seen.
FETCH_TTL_SECONDS = 300.0
FETCH_TIMEOUT_SECONDS = 3.0
# Only `main`, and explicitly onto the tracking ref. Relying on git's
# opportunistic update of `refs/remotes/*` would be an assumption; this is not.
FETCH_ARGS = (
    "fetch",
    "--quiet",
    "--no-tags",
    "origin",
    "+refs/heads/main:refs/remotes/origin/main",
)

# Changelog headings: `### 2026-09-17 (harness): what changed`. The prose record
# a new instance needs is written by the instance that made the change, and
# nothing surfaced it before.
_UNRELEASED = re.compile(r"^##\s+Unreleased\s*$")
_SECTION = re.compile(r"^##(?!#)")
_ENTRY = re.compile(r"^###\s+(?P<heading>.+?)\s*$")
CHANGELOG_HEADINGS = 3
CHANGELOG_HEADING_WIDTH = 78

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


def _env_float(name: str, fallback: float) -> float:
    try:
        return float(os.environ[name])
    except (KeyError, TypeError, ValueError):
        return fallback


def _run_fetch(timeout_seconds: float) -> tuple[bool, str | None]:
    """Run the fetch. Returns (ok, reason-it-failed).

    Separated from :func:`fetch_origin_main` so a test can replace the one
    function that touches the network, per `.claude/rules/tests.md`.
    """
    try:
        result = subprocess.run(
            ("git", *FETCH_ARGS),
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, f"timeout after {timeout_seconds:g}s"
    except (OSError, subprocess.SubprocessError) as error:
        return False, f"{type(error).__name__}: {error}"
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip().splitlines()
        return False, (detail[-1][:120] if detail else f"git exit {result.returncode}")
    return True, None


def fetch_origin_main(
    now: datetime | None = None,
    ttl_seconds: float | None = None,
    timeout_seconds: float | None = None,
    runner=_run_fetch,
) -> dict:
    """Refresh `origin/main`, at most once per TTL, and never fatally.

    `origin/main` is a remote-tracking ref: it moves on fetch and on nothing
    else. A session that cloned an hour ago therefore measures its distance
    against an hour-old answer and reports `behind origin/main by 0` while
    another instance has merged three pull requests.

    Three bounds keep this affordable. The TTL means `/clear` and a compaction
    inside five minutes pay nothing, which matters because the session-start
    hook fires on `startup|resume|clear|compact`. The timeout means a bad
    network cannot eat the hook's budget. And a failure is reported, never
    raised: an offline session must still start, with the staleness labelled
    rather than silently wrong.
    """
    now = now or datetime.now(timezone.utc)
    if ttl_seconds is None:
        ttl_seconds = _env_float("NFL_DFS_FETCH_TTL", FETCH_TTL_SECONDS)
    if timeout_seconds is None:
        timeout_seconds = _env_float("NFL_DFS_FETCH_TIMEOUT", FETCH_TIMEOUT_SECONDS)

    previous = _read_json(LAST_FETCH_FILE)
    previous = previous if isinstance(previous, dict) else {}
    last_ok_at = previous.get("fetched_at")
    age_seconds = None
    if isinstance(last_ok_at, str):
        try:
            when = datetime.fromisoformat(last_ok_at.replace("Z", "+00:00"))
            age_seconds = (now - when).total_seconds()
        except ValueError:
            age_seconds = None

    def record(attempted: bool, ok: bool, reason: str | None) -> dict:
        return {
            "attempted": attempted,
            "ok": ok,
            "reason": reason,
            "fetched_at": last_ok_at,
            "age_seconds": age_seconds,
        }

    if os.environ.get("NFL_DFS_NO_FETCH"):
        return record(False, False, "disabled by NFL_DFS_NO_FETCH")
    if age_seconds is not None and 0 <= age_seconds < ttl_seconds:
        return record(False, True, None)

    ok, reason = runner(timeout_seconds)
    if not ok:
        return record(True, False, reason)

    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        LAST_FETCH_FILE.write_text(
            json.dumps({"fetched_at": stamp}, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
    except OSError:
        pass  # A read-only checkout still gets the fetch; it just pays every time.
    last_ok_at, age_seconds = stamp, 0.0
    return record(True, True, None)


def git_state(now: datetime | None = None, fetcher=fetch_origin_main) -> dict:
    fetch = fetcher(now)
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
        "origin_main_fetch": fetch,
        "recent_commits": _git("log", "--oneline", "-5").splitlines(),
    }


def changelog_headings(limit: int = CHANGELOG_HEADINGS, path: Path | None = None) -> list[str]:
    """The most recent dated `###` headings under `## Unreleased`, newest first.

    Every session writes one of these saying what it changed and why. That is
    exactly the artifact a starting instance needs, written by the instance that
    made the change, and nothing surfaced it before; a commit subject is not a
    substitute.

    Headings only. The file is streamed and abandoned at the first heading past
    the `Unreleased` block or at `limit`, so this never reads the whole
    changelog into memory, per `CLAUDE.md` § Token discipline.
    """
    path = path or CHANGELOG
    found: list[str] = []
    try:
        with path.open(encoding="utf-8") as handle:
            in_unreleased = False
            for line in handle:
                line = line.rstrip("\n")
                if not in_unreleased:
                    in_unreleased = bool(_UNRELEASED.match(line))
                    continue
                if _SECTION.match(line):
                    break  # Past `Unreleased`, into a released version.
                match = _ENTRY.match(line)
                if not match:
                    continue
                heading = match.group("heading").strip()
                if len(heading) > CHANGELOG_HEADING_WIDTH:
                    heading = heading[: CHANGELOG_HEADING_WIDTH - 1].rstrip() + "…"
                found.append(heading)
                if len(found) >= limit:
                    break
    except OSError:
        return []
    return found


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
        "git": git_state(now),
        "changelog_headings": changelog_headings(),
        "queue": queue,
        "ready_chunks": [row["chunk"] for row in queue if row["status"] == "READY"],
        "in_progress_chunks": [row["chunk"] for row in queue if row["status"] == "IN_PROGRESS"],
        "claims": claims(now),
        "ben_flags": ben_flags(),
        "verification": verification(),
        "calibration": calibration(),
    }


def _staleness_line(fetch: dict) -> str | None:
    """Say so when the distance below was measured against an unrefreshed ref.

    A digest that cannot stand behind `behind origin/main by 0` has to say
    that, because a false zero is exactly the failure this script exists to
    prevent.
    """
    if not isinstance(fetch, dict) or fetch.get("ok"):
        return None
    reason = str(fetch.get("reason") or "unknown reason")
    # git's own error can run to a paragraph; the digest has a line budget.
    reason = reason.removeprefix("fatal: ")
    if len(reason) > 60:
        reason = reason[:59].rstrip() + "…"
    age = fetch.get("age_seconds")
    if not isinstance(age, (int, float)):
        as_of = "origin/main has never been fetched in this clone"
    elif age < 5400:
        as_of = f"last fetched {age / 60:.0f}m ago"
    else:
        as_of = f"last fetched {age / 3600:.1f}h ago"
    return f"origin/main NOT fetched ({reason}); distance is {as_of}"


def digest(state: dict) -> str:
    git = state["git"]
    lines = [
        f"branch {git['branch']} @ {git['head']}"
        f"  dirty {git['dirty_paths']} ({git['untracked_paths']} untracked)"
        + (f"  behind origin/main by {git['behind_origin_main']}" if git.get("behind_origin_main") not in (None, "0") else ""),
    ]
    stale = _staleness_line(git.get("origin_main_fetch", {}))
    if stale:
        lines.append(f"  {stale}")
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

    headings = state.get("changelog_headings") or []
    if headings:
        lines.append("recent changelog entries (newest first):")
        lines.extend(f"  {heading}" for heading in headings)

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
