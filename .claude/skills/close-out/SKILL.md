---
name: close-out
description: Close a Claude Code development session in the nfl-dfs repo: verification evidence, ledger updates, next READY prompt, and the reviewed path list for Ben. Use when the chunk is done or the session is ending.
disable-model-invocation: true
---

Close out the current chunk.

1. Verification, with output pasted, not summarized: focused tests for the
   changed modules; the complete pinned suite under an extended timeout;
   `doctor`; `python -m compileall` (or import) of every changed module;
   `git diff --check`. If anything is red, the chunk is not `DONE`; say so.
2. `backlog.md` (CRLF): read only its head (`limit` ~230). Set the chunk's
   status in the Queue table and the chunk index; add a dated status paragraph
   under the index entry with what landed, what was relaxed or left open, and any
   `[BEN: ...]` flags; set the next dependency-satisfied chunk `READY`. The brief
   in `docs/chunks/` is not edited at close-out.
3. `changelog.md` (CRLF): read its first 80 lines only, then insert a dated
   `###` section directly under `## Unreleased` with
   Added / Changed / Verification, exact test counts and timings, artifact
   hashes, and the branch name.
4. `IMPLEMENTATION_STATUS.md` (CRLF): only if working capability changed.
5. Write `docs/session-prompts/<NEXT-ID>-<slug>.md` for the next `READY` chunk in
   the house format (see `Q1B-settlement-intake.md`).
6. Run the `reviewer` subagent on the diff against the chunk brief; fix or
   record what it finds before the path list.
7. Print for Ben: the exact `git status --short` of changed and new paths as a
   reviewed path list, grouped as source / tests / docs / ledger, plus one line on
   anything that should not be committed. Do not stage or commit.
