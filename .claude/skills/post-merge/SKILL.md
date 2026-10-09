---
name: post-merge
description: Run the after-merge routine in the nfl-dfs repo: clean up merged branches and check local and GitHub agree, write the next session's handoff prompt, give Ben PowerShell blocks, then archive the session. Use right after a pull request that closes a roadmap dev session has merged, or when Ben types /post-merge. Never started by a lineup run on its own.
disable-model-invocation: true
---

Run the routine in `docs/claude/post_merge.md`, from step 1.

Roadmap dev sessions only (Ben, 2026-10-08). A lineup run never starts the post-merge
routine; a typed command works in any session, because Ben typing it is an explicit request.
Ben typing `/post-merge` is the trigger and also his acknowledgement, so it never
counts as him writing after the merge. Everything else in that file applies:

- `python3 scripts/post_merge.py` reads and never writes; run each printed
  command as its own Bash call.
- A denial stops that step. Give Ben the exact command and do not retry in
  pieces or by another tool.
- Archive last, and only when every condition in step 8 holds, and say which one
  held it open when it does not. Typing `/post-merge` alone does not ask for the
  archive: the routine archives only when this session's own merged pull request
  (found by `head.ref`, never the newest merged one) carries the `Session close:`
  marker, or Ben asks for it in this session after the merge. In a lineup run it
  stops after the report and the session stays open.
- Never delete an unmerged branch, a `codex/*` branch, a stash or a worktree.
