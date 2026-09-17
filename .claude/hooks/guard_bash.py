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
        # `--all` and `-A` stage the whole tree whatever follows them, so a path
        # argument does not narrow either one.
        re.compile(r"\bgit\s+add\b[^|;&]*?(?:--all\b|(?<!\w)-A(?!\w))"),
        "stage everything. Stage an explicit path list so the diff is the one "
        "you reviewed.",
    ),
    (
        # `-u` is different: given any pathspec it *is* an explicit path list,
        # and only the bare form stages the whole tree. Refusing
        # `git add -u <path>` was a false positive recorded on 2026-09-17.
        # So this matches `git add` whose arguments narrow nothing: flags, and
        # the pathspecs that are themselves the whole tree. `git add -u`,
        # `git add -v -u`, `git add -u -v`, and `git add -u .`, which from the
        # repository root stages every tracked change exactly like the bare
        # form. Only a pathspec that actually narrows (`git add -u src/x.py`,
        # or the equivalent `git add src/x.py -u`) stops the match.
        re.compile(
            r"\bgit\s+add(?:\s+(?:-{1,2}[\w-]+|\.{1,2}/?|\*|:/))*"
            r"\s+-u(?!\w)"
            r"(?:\s+(?:-{1,2}[\w-]+|\.{1,2}/?|\*|:/))*\s*(?=$|[|;&])"
        ),
        "stage every tracked change. `git add -u` with no path stages the whole "
        "tree; name the paths instead.",
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
        re.compile(r"\bgit\s+clean\b"),
        "discard uncommitted work.",
    ),
    (
        # Everything except the two read-only verbs. Refusing `git stash list`
        # and `git stash show` was a false positive recorded on 2026-09-17; the
        # repair is to name what is allowed, not what is forbidden.
        #
        # Naming the mutating verbs instead was tried first and was wrong: git
        # takes flags in place of the `push` keyword, so `git stash -u`,
        # `--include-untracked`, `-a`, `-p` and `-k` are all `stash push` and
        # all slipped through. An allowlist fails safe, including for a
        # subcommand git has not grown yet.
        re.compile(r"\bgit\s+stash\b(?!\s+(?:list|show)\b)"),
        "discard or move uncommitted work. The working tree is often "
        "intentionally dirty with user-owned work. `git stash list` and "
        "`git stash show` are read-only and allowed.",
    ),
    (
        re.compile(r"\bgit\s+branch\b[^|;&]*?(?<!\w)-D(?!\w)"),
        "force-delete a branch. `-d` refuses an unmerged branch, which is the "
        "point.",
    ),
)


def forbidden_reason(command: str) -> str | None:
    """Return why this command is refused, or None if nothing matches.

    Pattern matching only. No git, no network, no file system: this is called
    on every Bash call, and `tests/test_repo_boundaries.py` runs it over every
    allowed and refused shape, which it could not do offline otherwise.
    """
    inspectable = strip_literals(command)
    for pattern, reason in FORBIDDEN:
        if pattern.search(inspectable):
            return reason
    return None


def stale_push_reason(command: str) -> str | None:
    """Return why this push is refused as out of date, or None.

    Separate from `forbidden_reason` on purpose. This one can fetch, so it must
    never run on a command that is not a push, and it is imported lazily so a
    non-push Bash call does not even pay the import.
    """
    if "git" not in command or "push" not in command:
        return None  # Two substring checks, cheaper than compiling a match.
    inspectable = strip_literals(command)
    try:
        # Imported here, not at module scope: `pathlib` alone costs several
        # milliseconds on every Bash call, and a non-push call must pay nothing.
        from pathlib import Path

        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import push_freshness

        if not push_freshness.mentions_push(inspectable):
            return None
        return push_freshness.evaluate(inspectable)
    except Exception:  # noqa: BLE001 - fail open, exactly like the rest of this hook
        return None


def _deny(source: str, reason: str) -> None:
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": (
                    f"Refused by .claude/hooks/{source}: {reason} "
                    "See .claude/rules/git-authority.md. Do not work around this."
                ),
            }
        },
        sys.stdout,
    )


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        command = str(payload.get("tool_input", {}).get("command", ""))
    except Exception:  # noqa: BLE001 - never block ordinary work on a parse error
        return 0

    reason = forbidden_reason(command)
    if reason is not None:
        _deny("guard_bash.py", reason)
        return 0

    stale = stale_push_reason(command)
    if stale is not None:
        _deny("push_freshness.py", stale)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001
        sys.exit(0)
