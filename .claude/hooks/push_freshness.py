#!/usr/bin/env python3
"""Refuse a push when `main` has moved since this branch's merge base.

Startup orientation cannot help when another instance merges forty minutes into
your work. Several Claude Code instances work this repository, and nothing
checked for that drift before the push that has to be reconciled anyway.

This is not a separate hook. `guard_bash.py` already runs before every `Bash`
call, and the `PreToolUse` matcher is tool-level rather than command-level, so a
second hook entry would mean a second `python3` process (measured ~20 ms, of
which ~10 ms is interpreter startup) on every Bash call forever. Instead
`guard_bash.py` matches `git push` against a string it has already built and
imports this module only then. A non-push call never loads it and pays nothing.

Fails open, like every hook here. A network problem, a missing ref or an
unreadable repository hands the decision back to the normal permission flow: a
gate that blocks work when it cannot see is worse than no gate.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REMOTE_REF = "refs/remotes/origin/main"
# A push is already a multi-second network operation, so it pays for a fresh
# answer rather than a cached one: a five-minute-old fetch could miss the merge
# that happened four minutes ago, which is the case this exists to catch.
FETCH_TTL_SECONDS = 0.0
FETCH_TIMEOUT_SECONDS = 5.0
NAMED_COMMITS = 3

_PUSH = re.compile(r"\bgit\s+push\b")
# Deleting a branch and a dry run cannot conflict with anything, so neither is
# worth a fetch. `--delete`/`-d`, or a refspec with an empty source (`:branch`).
_DELETE = re.compile(r"\bgit\s+push\b[^|;&]*?(?:--delete\b|(?<!\w)-d(?!\w)|\s:[\w./-]+)")
_DRY_RUN = re.compile(r"\bgit\s+push\b[^|;&]*?--dry-run\b")


def mentions_push(command: str) -> bool:
    """Cheap enough to run on every Bash call: one compiled regex, no I/O."""
    return bool(_PUSH.search(command))


def _git(*args: str) -> str | None:
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
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def _load_repo_state():
    """Reuse `scripts/repo_state.py`'s fetch rather than writing a second one.

    One definition of how `origin/main` is refreshed, one TTL marker, so a fetch
    the session start already paid for is visible here too.
    """
    import importlib.util

    script = PROJECT_ROOT / "scripts" / "repo_state.py"
    spec = importlib.util.spec_from_file_location("repo_state_for_freshness", script)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {script}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def evaluate(command: str, git=_git, fetcher=None) -> str | None:
    """Return why this push is refused, or None to let it through.

    `git` and `fetcher` are injected so the whole decision can be tested without
    a repository and without the network, per `.claude/rules/tests.md`.
    """
    if not mentions_push(command):
        return None
    if _DELETE.search(command) or _DRY_RUN.search(command):
        return None

    if fetcher is None:
        try:
            fetcher = _load_repo_state().fetch_origin_main
        except Exception:  # noqa: BLE001 - fail open
            return None
    try:
        fetch = fetcher(ttl_seconds=FETCH_TTL_SECONDS, timeout_seconds=FETCH_TIMEOUT_SECONDS)
    except Exception:  # noqa: BLE001 - fail open
        return None
    if not (isinstance(fetch, dict) and fetch.get("ok")):
        return None  # Could not see. Never block work on a network problem.

    remote = git("rev-parse", "--verify", "--quiet", REMOTE_REF)
    if not remote:
        return None  # No origin/main to be behind.
    base = git("merge-base", REMOTE_REF, "HEAD")
    if not base or base == remote:
        return None  # main has not moved past where this branch started.

    count = git("rev-list", "--count", f"{base}..{REMOTE_REF}")
    subjects = git("log", "--oneline", f"-{NAMED_COMMITS}", f"{base}..{REMOTE_REF}") or ""
    named = "\n".join(f"  {line}" for line in subjects.splitlines() if line.strip())
    plural = "" if count == "1" else "s"
    return (
        f"origin/main has moved {count or 'some'} commit{plural} ahead of this "
        f"branch's merge base since it was created.\n"
        f"{named}\n"
        "Merge it before pushing:  git merge origin/main"
    )


def main() -> int:
    command = " ".join(sys.argv[1:])
    reason = evaluate(command)
    if reason:
        print(reason)
        return 1
    print("push is current with origin/main")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001 - fail open
        sys.exit(0)
