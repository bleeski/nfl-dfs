---
name: close-out
description: Close a Claude Code development session in the nfl-dfs repo: verification evidence, ledger updates, next READY prompt, then commit, push, open the pull request and merge it on green CI. Use when the chunk is done or the session is ending.
disable-model-invocation: true
---

Close out the current chunk.

1. Verification, with output pasted, not summarized: focused tests for the
   changed modules; the complete pinned suite under an extended timeout;
   `doctor`; `python -m compileall` (or import) of every changed module;
   `git diff --check`. If anything is red, the chunk is not `DONE`; say so.
2. `backlog.md` (LF): read only its head (`limit` ~230). Set the chunk's
   status in the Queue table and the chunk index; add a dated status paragraph
   under the index entry with what landed, what was relaxed or left open, and any
   `[BEN: ...]` flags; set the next dependency-satisfied chunk `READY`. The brief
   in `docs/chunks/` is not edited at close-out.
3. `changelog.md` (LF): read its first 80 lines only, then insert a dated
   `###` section directly under `## Unreleased` with
   Added / Changed / Verification, exact test counts and timings, artifact
   hashes, and the branch name.
4. `IMPLEMENTATION_STATUS.md` (LF): only if working capability changed.
5. Write `docs/session-prompts/<NEXT-ID>-<slug>.md` for the next `READY` chunk in
   the house format (see `Q1B-settlement-intake.md`).
6. Run the `reviewer` subagent on the diff against the chunk brief; fix or
   record what it finds before committing.
7. Record the suite result where the next session will see it:
   `python3 scripts/record_verify.py --from-log <log>`.
8. Release the chunk claim in `state/claims.json`.
9. Commit and ship, per `.claude/rules/git-authority.md`:
   - `git add` an explicit path list, grouped as source / tests / docs / ledger.
     Never `git add .` or `-A`. Say in one line what you deliberately left out.
   - Commit, push to `claude/<id>-<slug>`, open the pull request.
   - `python3 scripts/check_protected_paths.py`. If it flags anything, add the
     `ben-review` label, say so, and stop: that pull request is Ben's to merge.
   - Otherwise wait for `suite`, `boundaries` and `protected-paths` to go green,
     then merge and delete the branch. A red check is work, not a reason to stop.
10. Report to Ben in a few lines: what landed, the exact suite result, the pull
   request link and whether it merged, anything relaxed, and any open
   `[BEN: ...]` flag.
