#!/usr/bin/env python3
"""Read a checkout after a merge and say what it left behind. Never writes.

`docs/claude/post_merge.md` is the procedure. This is its instrument: it
fetches `origin`, classifies every local and remote branch, and reports what is
owed, as data (`--format json`), as one Bash command per line for Claude
(`--format commands`), as copy-paste PowerShell for Ben's Windows checkout
(`--format powershell`), or as names for `sync.ps1 -Clean`
(`--format local-merged-names`).

It is read-only on purpose. `.claude/settings.json` allows
`Bash(python3 scripts/:*)`, so a script that ran `git push --delete` or
`git branch -d` would hide those commands from the deny list, from
`.claude/hooks/guard_bash.py` and from the permission classifier, which are the
layers `.claude/rules/git-authority.md` relies on. So every git call goes
through `git()`, which refuses anything but a short read-only list, and the
mutating commands are printed for someone to run where those layers can see
them: Claude as its own Bash calls, Ben through `sync.ps1`.

Exit code: 0 in sync, 1 commands for Claude are pending, 2 blocked (a dirty
tree, unpushed commits, a failed fetch, an unknown open-PR list). A branch only
Ben can judge (unmerged, a stash, a worktree) is reported under `for_ben` and
never makes the run non-zero: it is his to decide, outside this session.

Output is ASCII so it survives Windows PowerShell 5.1.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = "nfl_post_merge_check_v1"
# Ben's Windows checkout, from docs/CLAUDE_CODE_SETUP.md "Keeping a Windows checkout in sync".
WINDOWS_CHECKOUT = r"C:\Users\benja\Documents\Claude\nfl-dfs"
# The last line of a closing pull request's body. `/close-out` writes it and the routine looks
# for it, because a session can merge several pull requests from one branch (Session 66: #119
# and #120) and only the last one means the work is finished.
SESSION_CLOSE_MARKER = "Session close: post-merge routine runs when this merges (docs/claude/post_merge.md)."
MINE_PREFIX = "claude/"
SAFE_BRANCH_NAME = re.compile(r"^[A-Za-z0-9._/-]+$")
FORMATS = ("json", "text", "commands", "powershell", "local-merged-names")

_READ_ONLY_VERBS = frozenset({"rev-parse", "rev-list", "for-each-ref", "merge-base", "log", "status", "show"})


class ForbiddenGit(RuntimeError):
    """A git command this read-only script is not allowed to run."""


def _allowed(args: tuple[str, ...]) -> bool:
    if not args:
        return False
    verb = args[0]
    if verb in _READ_ONLY_VERBS:
        return True
    if verb == "fetch":
        # Only the remote-tracking refs move; never a refspec into a local branch.
        return args == ("fetch", "--prune", "origin")
    if verb == "stash":
        return args == ("stash", "list")
    if verb == "worktree":
        return args[:2] == ("worktree", "list")
    return False


def run(repo: Path, *args: str) -> subprocess.CompletedProcess:
    if not _allowed(args):
        raise ForbiddenGit("git " + " ".join(args))
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def git(repo: Path, *args: str) -> str:
    return run(repo, *args).stdout.strip()


def _ascii(text: object) -> str:
    return str(text).encode("ascii", "replace").decode("ascii")


def _empty_report(repo: Path) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "repo": str(repo),
        "verdict": "BLOCKED",
        "fetch": {"attempted": False, "ok": None, "reason": None},
        "shallow": False,
        "current_branch": None,
        "head": None,
        "origin_main": None,
        "dirty_paths": 0,
        "unpushed_commits": 0,
        "branches": [],
        "blockers": [],
        "claude_commands": [],
        "for_ben": [],
    }


def _item(code: str, **detail: object) -> dict:
    return {"code": code, **{key: _ascii(value) for key, value in detail.items()}}


def _parse_evidence(values: list[str]) -> dict[str, str]:
    evidence: dict[str, str] = {}
    for value in values:
        name, _, sha = value.partition("=")
        if name and len(sha) >= 7:
            evidence[name] = sha.lower()
    return evidence


def collect(
    repo: Path,
    *,
    fetch: bool,
    open_prs: list[str] | None,
    merged_pr_heads: dict[str, str],
    now: datetime,
) -> dict:
    report = _empty_report(repo)
    if run(repo, "rev-parse", "--is-inside-work-tree").stdout.strip() != "true":
        report["blockers"].append(_item("NOT_A_REPO", detail=repo))
        return report

    if fetch:
        fetched = run(repo, "fetch", "--prune", "origin")
        reason = (fetched.stderr.strip().splitlines() or [""])[-1][:120]
        report["fetch"] = {"attempted": True, "ok": fetched.returncode == 0, "reason": _ascii(reason) or None}
        if fetched.returncode != 0:
            report["blockers"].append(_item("FETCH_FAILED", detail=reason))

    report["shallow"] = git(repo, "rev-parse", "--is-shallow-repository") == "true"
    current = git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    report["current_branch"] = None if current in ("", "HEAD") else current
    report["head"] = git(repo, "rev-parse", "--short", "HEAD") or None
    origin_main = git(repo, "rev-parse", "--verify", "--quiet", "origin/main")
    report["origin_main"] = origin_main or None
    if not origin_main:
        report["blockers"].append(_item("NO_ORIGIN_MAIN", detail="origin/main is not a known ref"))

    dirty = [line for line in git(repo, "status", "--porcelain").splitlines() if line.strip()]
    report["dirty_paths"] = len(dirty)
    if dirty:
        report["blockers"].append(_item("DIRTY_TREE", detail=f"{len(dirty)} path(s) not committed"))
    counted = run(repo, "rev-list", "--count", "HEAD", "--not", "--remotes=origin")
    unpushed = int(counted.stdout.strip()) if counted.returncode == 0 and counted.stdout.strip().isdigit() else 0
    report["unpushed_commits"] = unpushed
    if unpushed:
        report["blockers"].append(_item("UNPUSHED_COMMITS", detail=f"{unpushed} commit(s) exist only here"))

    listing = git(
        repo,
        "for-each-ref",
        "--format=%(refname)%00%(objectname)%00%(creatordate:unix)%00%(contents:subject)",
        "refs/heads",
        "refs/remotes/origin",
    )
    rows = []
    for line in listing.splitlines():
        refname, sha, stamp, subject = (line.split("\x00") + ["", "", "", ""])[:4]
        if refname.startswith("refs/heads/"):
            scope, name = "local", refname[len("refs/heads/"):]
        elif refname.startswith("refs/remotes/origin/"):
            scope, name = "remote", refname[len("refs/remotes/origin/"):]
        else:
            continue
        if name in ("main", "HEAD"):
            continue
        rows.append((scope, name, sha, int(stamp) if stamp.isdigit() else 0, subject))

    remote_names = {name for scope, name, *_ in rows if scope == "remote"}
    open_known = open_prs is not None
    open_set = set(open_prs or [])
    commands: list[str] = []
    open_prs_needed = False

    for scope, name, sha, stamp, subject in sorted(rows, key=lambda row: (row[1], row[0])):
        row = {"name": name, "scope": scope, "sha": sha, "subject": _ascii(subject), "ahead": 0, "age_days": 0}
        if stamp:
            row["age_days"] = max(0, int((now.timestamp() - stamp) // 86400))
        if name == report["current_branch"]:
            row["state"] = "CURRENT"
        elif name in open_set:
            row["state"] = "OPEN_PR"
        elif not name.startswith(MINE_PREFIX):
            row["state"] = "NOT_MINE"
        elif report["shallow"] or not origin_main:
            row["state"] = "UNKNOWN_SHALLOW"
        else:
            ancestor = run(repo, "merge-base", "--is-ancestor", sha, origin_main).returncode
            if ancestor == 0:
                row["state"] = "MERGED"
            else:
                row["state"] = "UNMERGED"
                ahead = git(repo, "rev-list", "--count", f"{origin_main}..{sha}")
                row["ahead"] = int(ahead) if ahead.isdigit() else 0
        report["branches"].append(row)

        if name.startswith(MINE_PREFIX) and not SAFE_BRANCH_NAME.match(name):
            report["for_ben"].append(_item("UNSAFE_BRANCH_NAME", branch=name, detail="left out of every command"))
            continue
        if row["state"] == "UNMERGED" and not (scope == "local" and name in remote_names):
            report["for_ben"].append(
                _item(
                    "UNMERGED_BRANCH",
                    branch=name,
                    scope=scope,
                    ahead=row["ahead"],
                    subject=row["subject"],
                    age_days=row["age_days"],
                )
            )
        if row["state"] == "MERGED" and scope == "remote":
            evidence = merged_pr_heads.get(name)
            if evidence is None:
                report["for_ben"].append(
                    _item("MERGED_NO_PR_EVIDENCE", branch=name, detail="merged by ancestry only, so not deleted")
                )
            elif not sha.lower().startswith(evidence):
                report["for_ben"].append(
                    _item("PR_EVIDENCE_MISMATCH", branch=name, detail="the tip is not the merged pull request's head")
                )
            elif not open_known:
                open_prs_needed = True
            else:
                commands.append(f"git push origin --delete {name}")

    if open_prs_needed:
        report["blockers"].append(_item("OPEN_PRS_UNKNOWN", detail="pass --open-pr-head or --no-open-prs"))
    report["claude_commands"] = commands

    if report["shallow"]:
        # Cloud clones are shallow, and ancestry in a shallow history can be wrong, so no branch is
        # called merged or not until the history is whole. A fetch only adds objects (1.4 s on this
        # repository), and Claude runs it as its own Bash call like every other command.
        commands.insert(0, "git fetch --unshallow origin")
        report["claude_commands"] = commands
    for stash in git(repo, "stash", "list").splitlines():
        report["for_ben"].append(_item("STASH", detail=stash[:120]))
    worktrees = [
        line[len("worktree "):]
        for line in git(repo, "worktree", "list", "--porcelain").splitlines()
        if line.startswith("worktree ")
    ]
    for path in worktrees[1:]:
        report["for_ben"].append(_item("WORKTREE", detail=path))

    if report["blockers"]:
        report["verdict"] = "BLOCKED"
    elif commands:
        report["verdict"] = "ACTIONS_PENDING"
    else:
        report["verdict"] = "IN_SYNC"
    return report


def exit_code(report: dict) -> int:
    return {"IN_SYNC": 0, "ACTIONS_PENDING": 1}.get(report["verdict"], 2)


def _safe(row: dict) -> bool:
    return bool(SAFE_BRANCH_NAME.match(row["name"]))


def render_text(report: dict) -> str:
    lines = [
        f"post-merge check: {report['verdict']}",
        f"branch {report['current_branch'] or '(detached)'} at {report['head']}; "
        f"origin/main {str(report['origin_main'] or 'unknown')[:7]}; dirty {report['dirty_paths']}; "
        f"unpushed {report['unpushed_commits']}; shallow {'yes' if report['shallow'] else 'no'}",
    ]
    fetch = report["fetch"]
    if fetch["attempted"]:
        lines.append("fetch: ok" if fetch["ok"] else f"fetch: FAILED ({fetch['reason']})")
    else:
        lines.append("fetch: skipped")
    for blocker in report["blockers"]:
        lines.append(f"BLOCKED {blocker['code']}: {blocker.get('detail', '')}")
    for command in report["claude_commands"]:
        lines.append(f"RUN {command}")
    for item in report["for_ben"]:
        detail = " ".join(f"{key}={value}" for key, value in item.items() if key != "code")
        lines.append(f"FOR BEN {item['code']}: {detail}")
    for row in report["branches"]:
        lines.append(f"  {row['scope']:6} {row['state']:15} {row['name']}")
    return _ascii("\n".join(lines)) + "\n"


def render_commands(report: dict) -> str:
    if not report["claude_commands"]:
        return "# nothing to run\n"
    return "\n".join(report["claude_commands"]) + "\n"


def render_local_merged_names(report: dict) -> str:
    names = [row["name"] for row in report["branches"] if row["scope"] == "local" and row["state"] == "MERGED" and _safe(row)]
    return "".join(f"{name}\n" for name in names)


def _block(command: str) -> str:
    return f"```powershell\n{command}\n```\n"


def render_powershell(report: dict) -> str:
    lines = [
        "Run these in PowerShell on your Windows checkout. Each block is one command.\n",
        "Sync and clean. It leaves a merged branch for main, fast-forwards main, deletes merged claude/* "
        "branches with git branch -d, and prints IN SYNC or what is left:\n",
        _block("Sync-NflDfs -Clean"),
        "If Sync-NflDfs is not in your PowerShell profile, run the script by its path:\n",
        _block(f"& '{WINDOWS_CHECKOUT}\\sync.ps1' -Clean"),
    ]
    unmerged = [
        row
        for row in report["branches"]
        if row["state"] == "UNMERGED" and _safe(row) and not (row["scope"] == "local" and any(
            other["scope"] == "remote" and other["name"] == row["name"] for other in report["branches"]
        ))
    ]
    if unmerged:
        lines.append(
            "Left for you to decide. Nothing below runs on its own, and Claude never deletes an unmerged branch.\n"
        )
    for row in unmerged:
        count = row["ahead"]
        lines.append(
            f"{row['name']} ({row['scope']}): {count} commit(s) not on main, last \"{row['subject']}\", "
            f"{row['age_days']} day(s) old. See what is on it:\n"
        )
        if row["scope"] == "remote":
            lines.append(_block(f"git log origin/main..origin/{row['name']} --oneline"))
            lines.append("Delete it on GitHub only if you do not want it:\n")
            lines.append(_block(f"git push origin --delete {row['name']}"))
        else:
            lines.append(_block(f"git log main..{row['name']} --oneline"))
    notes = [item for item in report["for_ben"] if item["code"] in ("STASH", "WORKTREE", "UNSAFE_BRANCH_NAME")]
    for item in notes:
        lines.append(f"{item['code']}: {item.get('detail', '')} (listed, never touched)\n")
    return _ascii("\n".join(lines))


RENDERERS = {
    "json": lambda report: json.dumps(report, indent=2, sort_keys=True) + "\n",
    "text": render_text,
    "commands": render_commands,
    "powershell": render_powershell,
    "local-merged-names": render_local_merged_names,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", default=".", help="the checkout to read (default: the current directory)")
    parser.add_argument("--no-fetch", action="store_true", help="skip `git fetch --prune origin` (tests, offline)")
    parser.add_argument("--open-pr-head", action="append", default=[], metavar="BRANCH", help="head branch of an open pull request (repeatable)")
    parser.add_argument("--no-open-prs", action="store_true", help="the open pull request list was read and is empty")
    parser.add_argument("--merged-pr-head", action="append", default=[], metavar="BRANCH=SHA", help="a merged pull request's head branch and its head sha (repeatable)")
    parser.add_argument("--format", choices=FORMATS, default="text")
    parser.add_argument("--now", help="ISO timestamp used for ages (tests)")
    args = parser.parse_args(argv)

    now = datetime.now(timezone.utc)
    if args.now:
        now = datetime.fromisoformat(args.now.replace("Z", "+00:00"))
    open_prs: list[str] | None = None
    if args.open_pr_head or args.no_open_prs:
        open_prs = list(args.open_pr_head)

    report = collect(
        Path(args.repo),
        fetch=not args.no_fetch,
        open_prs=open_prs,
        merged_pr_heads=_parse_evidence(args.merged_pr_head),
        now=now,
    )
    sys.stdout.write(RENDERERS[args.format](report))
    return exit_code(report)


if __name__ == "__main__":
    sys.exit(main())
