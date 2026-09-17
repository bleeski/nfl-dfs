#!/usr/bin/env python3
"""Seed every session with the repository's real state before the first prompt.

Several Claude Code instances work this repository and none of them knows about
the others. A CLAUDE.md can be skimmed; this cannot. It runs on startup, resume,
clear and compact, and prints the few facts a session is most likely to get
wrong: which branch it is on, which chunks are claimed, whether the suite was
last green, and how much graded evidence exists.

Two hard rules. It finishes well under two seconds, and it exits 0 no matter
what happens: a hook that can fail a session start is worse than no hook.

Wired in `.claude/settings.json`. Emits plain text on stdout, which Claude Code
adds to the session context.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MAX_LINES = 60

PREAMBLE = """\
=== nfl-dfs, session start =======================================================
Read docs/START_HERE.md before acting. It is one page and it is the whole brief.

Never: automate or fetch DraftKings; let AvgPointsPerGame reach a projection;
call a prior EV, ROI, win probability or calibrated; weaken an evidence gate to
finish a run; overwrite an uploaded file or anything under data/standings/inbox/.

Every current path ends MODEL_STATUS=PRIOR_ONLY, RELEASE_DECISION=DO_NOT_UPLOAD.
Exit code 0 means review generation completed, not that uploading is cleared.

Commit, push, PR and merge authority: .claude/rules/git-authority.md.
Another instance may be working here now. Check the claims below before you start.
"""

FOOTER = """\
Chunk work: /dev-session <ID>.  Evidence: /verify.  Finish: /close-out.
Regenerate this: python3 scripts/repo_state.py --stdout
=================================================================================\
"""


def _state_digest() -> str:
    script = PROJECT_ROOT / "scripts" / "repo_state.py"
    spec = importlib.util.spec_from_file_location("repo_state", script)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {script}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.digest(module.build_state())


def main() -> int:
    try:
        body = _state_digest()
    except Exception as error:  # noqa: BLE001 - never fail a session start
        body = (
            f"repo state unavailable ({type(error).__name__}: {error}).\n"
            "Run `python3 scripts/repo_state.py --stdout` by hand."
        )

    text = f"{PREAMBLE}\n{body}\n\n{FOOTER}"
    lines = text.splitlines()
    if len(lines) > MAX_LINES:
        keep = MAX_LINES - 2
        lines = lines[:keep] + [f"... {len(lines) - keep} more lines, see state/repo-state.json"]
        text = "\n".join(lines)
    print(text)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001 - belt and braces
        sys.exit(0)
