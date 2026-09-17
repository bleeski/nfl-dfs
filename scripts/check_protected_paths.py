#!/usr/bin/env python3
"""Fail a pull request that touches a protected path without Ben's label.

The protected list lives in ``.github/protected-paths.txt`` so that the CI job,
this script, and ``tests/test_repo_boundaries.py`` all read one file and cannot
drift. ``docs/CLAUDE_CODE_SETUP.md`` explains why each entry is on it.

In CI the environment supplies ``BASE_SHA``, ``HEAD_SHA`` and ``PR_LABELS``
(a JSON array). Run locally with no environment to check the working branch
against ``origin/main``:

    python3 scripts/check_protected_paths.py
    python3 scripts/check_protected_paths.py --base origin/main --head HEAD

Exit codes: 0 clear, 1 protected paths touched without the label, 2 the check
could not be performed (which is a failure too; an unrunnable gate is not a
passing gate).
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROTECTED_LIST = PROJECT_ROOT / ".github" / "protected-paths.txt"
REVIEW_LABEL = "ben-review"


def load_protected_globs(list_path: Path = PROTECTED_LIST) -> tuple[str, ...]:
    """Return the globs in the protected list, comments and blanks dropped."""
    if not list_path.is_file():
        raise FileNotFoundError(f"protected list is missing: {list_path}")
    globs = []
    for raw in list_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        globs.append(line)
    if not globs:
        raise ValueError(f"protected list has no entries: {list_path}")
    return tuple(globs)


def protected_matches(paths, globs) -> tuple[str, ...]:
    """Return the given repo-relative paths that any protected glob covers."""
    hits = []
    for path in paths:
        normalized = path.strip().replace("\\", "/")
        if not normalized:
            continue
        if any(fnmatch.fnmatch(normalized, pattern) for pattern in globs):
            hits.append(normalized)
    return tuple(sorted(set(hits)))


def _git(*args: str) -> str:
    result = subprocess.run(
        ("git", *args),
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def changed_paths(base: str, head: str) -> tuple[str, ...]:
    merge_base = _git("merge-base", base, head).strip() or base
    diff = _git("diff", "--name-only", f"{merge_base}..{head}")
    return tuple(line for line in diff.splitlines() if line.strip())


def labels_from_env() -> tuple[str, ...]:
    raw = os.environ.get("PR_LABELS", "").strip()
    if not raw:
        return ()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        # A comma-separated fallback, for a local run that passes plain text.
        return tuple(part.strip() for part in raw.split(",") if part.strip())
    if isinstance(parsed, list):
        return tuple(str(item) for item in parsed)
    return ()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default=os.environ.get("BASE_SHA") or "origin/main")
    parser.add_argument("--head", default=os.environ.get("HEAD_SHA") or "HEAD")
    args = parser.parse_args(argv)

    try:
        globs = load_protected_globs()
        paths = changed_paths(args.base, args.head)
    except (OSError, RuntimeError, ValueError) as error:
        print(f"PROTECTED_PATHS_CHECK_FAILED: {error}", file=sys.stderr)
        return 2

    hits = protected_matches(paths, globs)
    if not hits:
        print(f"No protected path touched ({len(paths)} changed).")
        return 0

    labels = labels_from_env()
    listing = "\n".join(f"  {path}" for path in hits)
    if REVIEW_LABEL in labels:
        print(f"Protected paths touched, `{REVIEW_LABEL}` present:\n{listing}")
        return 0

    print(
        "PROTECTED_PATHS_WITHOUT_REVIEW\n"
        f"{listing}\n\n"
        f"These are Ben's call. Add the `{REVIEW_LABEL}` label and let him look,\n"
        "or take the change out of this pull request. Claude never merges this\n"
        "pull request itself. See docs/CLAUDE_CODE_SETUP.md.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
