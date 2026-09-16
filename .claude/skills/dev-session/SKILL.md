---
name: dev-session
description: Start a Claude Code development session on one backlog chunk (P0, P1, ...) in the nfl-dfs repo. Use at the top of a session when Ben names a chunk ID or says "start the next chunk".
disable-model-invocation: true
---

Start development on chunk `$ARGUMENTS` of `backlog.md`.

1. `git status --short --branch` and `git log --oneline -15`. Report the branch and whether the tree is
   dirty. Do not reset, clean, stash or reformat anything.
2. Read, in this order and nothing else yet: `CLAUDE.md`; `backlog.md` with
   `limit` set to its first ~230 lines (tracker protocol, program basis, queue,
   chunk index); the brief `docs/chunks/$ARGUMENTS-*.md`; the first 80 lines of
   `changelog.md`; the prompt `docs/session-prompts/$ARGUMENTS-*.md` if it
   exists. Never open `docs/backlog-archive/` or `docs/changelog-archive/`.
3. Confirm the chunk is `READY` and its dependencies are `DONE`. If not, stop
   and say which dependency is open.
4. Run the baseline before changing anything: `.\nfl.ps1 test` on Windows or
   `sh ./nfl.sh test` on Linux, with an extended timeout. Record the exact
   result line. A known failure is listed in `CLAUDE.md`; any other failure is
   reported before work starts.
5. Create branch `codex/<id>-<slug>` from the current HEAD.
6. Enter plan mode. Produce a plan that names: files to touch (only those the
   brief lists), tests to add first, the acceptance statement verbatim, open
   `[BEN: ...]` questions, and what is explicitly out of scope. Wait for
   approval before editing.
7. Set the chunk `IN_PROGRESS` in `backlog.md` (CRLF preserved).

Never `git add .` or `-A`, never commit, push or open a PR without an explicit
reviewed path list from Ben.
