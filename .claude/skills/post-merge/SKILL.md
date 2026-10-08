---
name: post-merge
description: Run the after-merge routine in the nfl-dfs repo: clean up merged branches and check local and GitHub agree, write the next session's handoff prompt, give Ben PowerShell blocks, then archive the session. Use right after a pull request that closes the session's work has merged, or when Ben types /post-merge.
disable-model-invocation: true
---

Run the routine in `docs/claude/post_merge.md`, from step 1.

Ben typing `/post-merge` is the trigger and also his acknowledgement, so it never
counts as him writing after the merge. Everything else in that file applies:

- `python3 scripts/post_merge.py` reads and never writes; run each printed
  command as its own Bash call.
- A denial stops that step. Give Ben the exact command and do not retry in
  pieces or by another tool.
- Archive last, only when every condition in step 8 holds, and say which one
  held it open when it does not.
- Never delete an unmerged branch, a `codex/*` branch, a stash or a worktree.
