#!/usr/bin/env python3
"""Fail a pull request that touches a protected path without Ben's label.

The protected list lives in ``.github/protected-paths.txt`` so that the CI job,
this script, and ``tests/test_repo_boundaries.py`` all read one file and cannot
drift. ``docs/CLAUDE_CODE_SETUP.md`` explains why each entry is on it.

Run locally with no environment to check the working branch against
``origin/main``. ``PR_LABELS`` (a JSON array, or comma-separated text) may name
labels by hand. This path never touches the network:

    python3 scripts/check_protected_paths.py
    python3 scripts/check_protected_paths.py --base origin/main --head HEAD

In CI, ``.github/workflows/protected-paths.yml`` runs it with ``--live-labels``
(H3, 2026-09-23). The labels then come from the pull request as it is when the
job runs, read from ``GET /repos/{repo}/pulls/{n}``, and ``PR_LABELS`` is
ignored. The event payload is frozen when the event fires and replayed verbatim
on a re-run, so a label added after CI ran was never in it, and on PR #32 the
check stayed red with the label on. The lookup needs ``GITHUB_API_URL`` (only
``https://api.github.com``, which must also be in ``sources.ALLOWED_HOSTS``),
``GITHUB_REPOSITORY``, ``PR_NUMBER`` and ``GITHUB_TOKEN``. It runs every time
the flag is set, retries once, and any failure exits 2 whatever the diff
touches.

Exit codes: 0 clear, 1 protected paths touched without the label, 2 the check
could not be performed (which is a failure too; an unrunnable gate is not a
passing gate).
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROTECTED_LIST = PROJECT_ROOT / ".github" / "protected-paths.txt"
SOURCES_PY = PROJECT_ROOT / "src" / "nfl_dfs" / "sources.py"
REVIEW_LABEL = "ben-review"

LIVE_LABEL_API_HOST = "api.github.com"
LOOKUP_TIMEOUT_SECONDS = 10
RETRY_DELAY_SECONDS = 2
_REPOSITORY = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]*)/[A-Za-z0-9._-]+")
_PR_NUMBER = re.compile(r"[1-9][0-9]*")


class LabelLookupError(RuntimeError):
    """The live label set could not be read or trusted. The check fails."""


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


def allowed_hosts(sources_path: Path = SOURCES_PY) -> frozenset[str]:
    """Read ``ALLOWED_HOSTS`` from ``sources.py`` by parsing it, never importing.

    ``sources.py`` imports ``httpx`` and the CI job has no environment, and the
    lookup has to answer to the one allowlist rather than a second copy of it.
    """
    tree = ast.parse(sources_path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "ALLOWED_HOSTS":
                    return frozenset(ast.literal_eval(node.value))
    raise LabelLookupError(f"ALLOWED_HOSTS not found in {sources_path}")


class _RefuseRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect would leave the host that was checked; treat it as an error."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        return None


def _fetch_json(url: str, token: str) -> object:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "nfl-dfs-protected-paths",
        },
        method="GET",
    )
    opener = urllib.request.build_opener(_RefuseRedirect)
    try:
        with opener.open(request, timeout=LOOKUP_TIMEOUT_SECONDS) as response:
            status = response.status
            body = response.read()
    except urllib.error.HTTPError as error:
        raise LabelLookupError(f"HTTP {error.code} from {url}") from error
    except (urllib.error.URLError, OSError) as error:
        raise LabelLookupError(f"could not reach {url}: {error}") from error
    if status != 200:
        raise LabelLookupError(f"HTTP {status} from {url}")
    try:
        return json.loads(body)
    except (ValueError, UnicodeDecodeError) as error:
        raise LabelLookupError(f"response from {url} is not JSON") from error


def _pull_request_url(environ) -> tuple[str, str, int]:
    """Validate every input before anything is sent. Returns url, token, number."""
    api_url = (environ.get("GITHUB_API_URL") or "").strip()
    repository = (environ.get("GITHUB_REPOSITORY") or "").strip()
    number = (environ.get("PR_NUMBER") or "").strip()
    token = (environ.get("GITHUB_TOKEN") or "").strip()
    if not api_url:
        raise LabelLookupError("GITHUB_API_URL is not set")
    parsed = urllib.parse.urlsplit(api_url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != LIVE_LABEL_API_HOST
        or parsed.netloc != LIVE_LABEL_API_HOST
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        raise LabelLookupError(f"GITHUB_API_URL must be https://{LIVE_LABEL_API_HOST}, got {api_url!r}")
    if LIVE_LABEL_API_HOST not in allowed_hosts():
        raise LabelLookupError(f"{LIVE_LABEL_API_HOST} is not in sources.ALLOWED_HOSTS")
    if not _REPOSITORY.fullmatch(repository):
        raise LabelLookupError(f"GITHUB_REPOSITORY is not owner/name: {repository!r}")
    if not _PR_NUMBER.fullmatch(number):
        raise LabelLookupError(f"PR_NUMBER is not a pull request number: {number!r}")
    if not token:
        raise LabelLookupError("GITHUB_TOKEN is not set")
    url = f"https://{LIVE_LABEL_API_HOST}/repos/{repository}/pulls/{number}"
    return url, token, int(number)


def _labels_from_pull(payload: object, number: int) -> tuple[str, ...]:
    if not isinstance(payload, dict):
        raise LabelLookupError("pull request response is not an object")
    found = payload.get("number")
    if isinstance(found, bool) or not isinstance(found, int) or found != number:
        raise LabelLookupError(f"response is for pull request {found!r}, not #{number}")
    labels = payload.get("labels")
    if not isinstance(labels, list):
        raise LabelLookupError("response has no labels list")
    names = []
    for label in labels:
        if not isinstance(label, dict) or not isinstance(label.get("name"), str):
            raise LabelLookupError(f"malformed label in response: {label!r}")
        names.append(label["name"])
    return tuple(names)


def live_labels(environ=os.environ) -> tuple[int, tuple[str, ...], str]:
    """Return the pull request number, its labels now, and when they were read."""
    url, token, number = _pull_request_url(environ)
    try:
        payload = _fetch_json(url, token)
    except LabelLookupError:
        time.sleep(RETRY_DELAY_SECONDS)
        payload = _fetch_json(url, token)
    observed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return number, _labels_from_pull(payload, number), observed_at


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default=os.environ.get("BASE_SHA") or "origin/main")
    parser.add_argument("--head", default=os.environ.get("HEAD_SHA") or "HEAD")
    parser.add_argument(
        "--live-labels",
        action="store_true",
        help="read the pull request's labels from the GitHub API now (CI only)",
    )
    args = parser.parse_args(argv)

    try:
        globs = load_protected_globs()
        paths = changed_paths(args.base, args.head)
    except (OSError, RuntimeError, ValueError) as error:
        print(f"PROTECTED_PATHS_CHECK_FAILED: {error}", file=sys.stderr)
        return 2

    if args.live_labels:
        try:
            number, labels, observed_at = live_labels()
        except (LabelLookupError, OSError, SyntaxError, ValueError) as error:
            print(f"PROTECTED_PATHS_CHECK_FAILED: live label lookup: {error}", file=sys.stderr)
            return 2
        print(f"Live labels on pull request #{number} at {observed_at}: {json.dumps(list(labels))}")
    else:
        labels = labels_from_env()

    hits = protected_matches(paths, globs)
    if not hits:
        print(f"No protected path touched ({len(paths)} changed).")
        return 0

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
