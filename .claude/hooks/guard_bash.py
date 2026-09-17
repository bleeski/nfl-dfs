#!/usr/bin/env python3
"""Deny destructive git commands that prefix matching cannot see.

`.claude/settings.json` permission rules match a prefix of the command string.
That is enough for `git push --force ...`, and not enough for two shapes that
reach the same place:

    git push -u origin claude/x --force     # flag after an allowed prefix
    git status && git push --force          # second command in a chain

This hook reads the whole command and refuses on a pattern, wherever in the
string it appears. It is the backstop under `.claude/rules/git-authority.md`,
not a replacement for the deny list: settings.json still refuses the plain
forms, and a denial is never something to work around.

Quoted strings and here-document bodies are stripped before matching, because
otherwise writing a document or a test that merely mentions one of these
commands would be refused. That is the scope of this hook: it catches the
destructive command typed by accident, not a determined bypass. What forbids
the bypass is the rule, not the regex.

Fails open by design. A crash here must not block ordinary work, so anything
unexpected exits 0 and lets the normal permission flow decide.
"""

from __future__ import annotations

import json
import re
import sys

# `cmd <<'EOF' ... EOF` and `cmd <<-EOF ... EOF`, body included.
_HEREDOC = re.compile(
    r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1.*?^\s*\2\s*$",
    re.DOTALL | re.MULTILINE,
)
# Quoted runs. Single quotes first: inside them nothing escapes.
_SINGLE_QUOTED = re.compile(r"'[^']*'")
_DOUBLE_QUOTED = re.compile(r'"(?:[^"\\]|\\.)*"')


def strip_literals(command: str) -> str:
    """Remove here-document bodies and quoted strings from a command.

    What remains is the part a shell would treat as words and operators, which
    is the only part worth matching a destructive-command pattern against.
    """
    without_heredocs = _HEREDOC.sub(" ", command)
    without_single = _SINGLE_QUOTED.sub(" ", without_heredocs)
    return _DOUBLE_QUOTED.sub(" ", without_single)

# (compiled pattern, what to say). Ordered most-specific first so the message
# a person sees names the actual problem.
FORBIDDEN: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"\bgit\s+push\b[^|;&]*?(?:--force\b|--force-with-lease\b|(?<!\w)-f(?!\w))"),
        "force push. History on a shared branch is never rewritten; open a new "
        "commit instead.",
    ),
    (
        # A leading `+` on a refspec is a force push with no `--force` token
        # anywhere in the command. `git push origin +HEAD:main` is the shape.
        re.compile(r"\bgit\s+push\b[^|;&]*?(?<![\w/+-])\+[\w./-]+:"),
        "force push by `+refspec`. A leading `+` forces the update just as "
        "`--force` does.",
    ),
    (
        # `origin main`, and every refspec form that lands on main whatever the
        # source ref is called: `HEAD:main`, `feature:main`, `+HEAD:main`,
        # `feature:refs/heads/main`.
        re.compile(
            r"\bgit\s+push\b[^|;&]*?(?:"
            r"\borigin\s+main\b"
            r"|(?<![\w/-])\+?[\w./-]*:(?:refs/heads/)?main(?![\w/-])"
            r")"
        ),
        "push to main. main changes only through a merged pull request.",
    ),
    (
        re.compile(r"\bgit\s+commit\b[^|;&]*?--amend\b"),
        "amend. An amended commit rewrites history a reviewer may already hold.",
    ),
    (
        re.compile(r"\bgit\s+add\b[^|;&]*?(?:--all\b|(?<!\w)-A(?!\w)|(?<!\w)-u(?!\w))"),
        "stage everything. Stage an explicit path list so the diff is the one "
        "you reviewed.",
    ),
    (
        re.compile(r"\bgit\s+add\s+\.\s*$|\bgit\s+add\s+\.\s*[|;&]"),
        "`git add .`. Stage an explicit path list.",
    ),
    (
        re.compile(r"\bgit\s+(?:rebase|filter-branch|filter-repo)\b"),
        "rewrite history.",
    ),
    (
        re.compile(r"\bgit\s+reset\b[^|;&]*?--hard\b"),
        "hard reset. The working tree is often intentionally dirty with "
        "user-owned work.",
    ),
    (
        re.compile(r"\bgit\s+(?:clean|stash)\b"),
        "discard uncommitted work.",
    ),
    (
        re.compile(r"\bgit\s+branch\b[^|;&]*?(?<!\w)-D(?!\w)"),
        "force-delete a branch. `-d` refuses an unmerged branch, which is the "
        "point.",
    ),
)


def forbidden_reason(command: str) -> str | None:
    """Return why this command is refused, or None if nothing matches."""
    inspectable = strip_literals(command)
    for pattern, reason in FORBIDDEN:
        if pattern.search(inspectable):
            return reason
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        command = str(payload.get("tool_input", {}).get("command", ""))
    except Exception:  # noqa: BLE001 - never block ordinary work on a parse error
        return 0

    reason = forbidden_reason(command)
    if reason is None:
        return 0

    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": (
                    f"Refused by .claude/hooks/guard_bash.py: {reason} "
                    "See .claude/rules/git-authority.md. Do not work around this."
                ),
            }
        },
        sys.stdout,
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001
        sys.exit(0)
