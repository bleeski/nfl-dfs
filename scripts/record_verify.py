#!/usr/bin/env python3
"""Record a suite result at ``state/last-verify.json`` so the next session sees it.

`/verify` and `/close-out` run the pinned suite and are supposed to paste the
exact result line into the changelog. This stores the same line where the
SessionStart hook can read it, which is how a fresh session in a different
container learns whether the tree was last green.

    sh ./nfl.sh test 2>&1 | tee /tmp/pytest.log
    python3 scripts/record_verify.py --from-log /tmp/pytest.log

It records what the log says, pass or fail. It never infers a result it did not
see, and a log with no recognizable summary line is a refusal, not a guess.
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
STATE_FILE = PROJECT_ROOT / "state" / "last-verify.json"

# `735 passed, 1 skipped in 155.56s (0:02:35)` or `1 failed, 735 passed, ...`
_SUMMARY = re.compile(
    r"^(?=.*\bin\s[0-9.]+s)(?:[0-9]+\s+(?:passed|failed|skipped|error|errors|xfailed|xpassed|deselected|warning|warnings)[,\s].*)$"
)


def summary_line(log_text: str) -> str | None:
    for line in reversed(log_text.splitlines()):
        stripped = line.strip()
        if _SUMMARY.match(stripped):
            return stripped
    return None


def _head_commit() -> str:
    result = subprocess.run(
        ("git", "rev-parse", "--short", "HEAD"),
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--from-log", type=Path, help="a pytest log to read the summary line from")
    source.add_argument("--result-line", help="the exact summary line, when you already have it")
    parser.add_argument("--source", default="local", choices=("local", "ci"))
    args = parser.parse_args(argv)

    if args.result_line:
        line = args.result_line.strip()
    else:
        try:
            line = summary_line(args.from_log.read_text(encoding="utf-8", errors="replace")) or ""
        except OSError as error:
            print(f"VERIFY_LOG_UNREADABLE: {error}", file=sys.stderr)
            return 2
        if not line:
            print(
                "VERIFY_SUMMARY_NOT_FOUND: no pytest summary line in that log. A run "
                "killed by a tool timeout is not a result; rerun it.",
                file=sys.stderr,
            )
            return 2

    payload = {
        "schema_version": "nfl_verify_result_v1",
        "result_line": line,
        "commit": _head_commit(),
        "source": args.source,
        "observed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"recorded: {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
