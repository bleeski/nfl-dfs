# After a merge: the next prompt, the cleanup, the archive

Ben's request, 2026-10-08, and the standing acknowledgement for the last step: "Once a PR is merged (1) Claude automatically writes the prompt for the new chunk of work for me to copy and paste into a new dev session in the same format (2) claude does any necessary repo cleanup to remove extraneous branches, make sure local and github are in sync etc. If anything requires powershell commands it should present them in copy and paste format. Once all this is done the session should auto archive."

This file is Claude's own procedure under CLAUDE.md "Getting better". It changes no permanent boundary. `scripts/post_merge.py` and `scripts/next_prompt.py` are its instruments; `tests/test_post_merge.py` and `tests/test_next_prompt.py` pin them.

## When it runs

Only when the merged pull request closes the session's work. A session can merge several pull requests from one branch (Session 66 merged #119 and #120 from the same head), so a count of open pull requests proves nothing. The signal is a marker: `/close-out` ends the PR body with the line

    Session close: post-merge routine runs when this merges (docs/claude/post_merge.md).

and the routine runs when any of these happens:

1. I merge a pull request whose body carries that line.
2. Ben merges one, and the `pull_request.closed` wake says `merged`. Read the body with `pull_request_read get` first. No marker means a mid-session merge: say so in one line and do nothing else.
3. Ben types `/post-merge`.

## The routine, in order

1. **Read the state.** List the open pull requests (`list_pull_requests`, state open) and note the merged one's `head.ref` and `head.sha`. Then run

       python3 scripts/post_merge.py --no-open-prs --merged-pr-head <branch>=<sha>

   (use `--open-pr-head <branch>` once per open pull request instead of `--no-open-prs`). It fetches with no cache, so a merge made a second ago is visible. Exit 0 means in sync, 1 means commands are pending, 2 means blocked. A cloud clone is shallow, and ancestry in a shallow history can be wrong, so the first command it prints is `git fetch --unshallow origin` (a fetch that only adds history, about a second here): run it, then run the check again.
2. **Clean up.** Run each line of `--format commands` as its own Bash call. They are `git push origin --delete claude/...` for a head that was a merged pull request's head, with its sha matching, and nothing else: GitHub already deletes a merged head, so this is a safety net. If the harness denies one, stop that step, hand Ben the exact command, and do not retry in pieces. The script never runs a mutating git command itself, because `Bash(python3 scripts/:*)` would hide it from the deny list, the Bash guard and the classifier. Never delete an unmerged branch, a `codex/*` branch, a stash or a worktree: they go to Ben under `for_ben`.
3. **Fix what blocks.** A dirty tree, unpushed commits or a failed fetch is work, not a reason to archive.
4. **Read main's CI on the merge commit** (`actions_list` for runs on `main`). `suite`, `boundaries` and `protected-paths` must be green. Pending: `send_later` for 20 minutes, at most twice. `cancelled` (a second merge cancelled the run): read the newest run. Red: it is work, so fix it under `.claude/rules/git-authority.md` and keep the session open. `windows` is reported and never waited on; it runs up to 45 minutes and gates nothing.
5. **Write the next prompt.** `python3 scripts/next_prompt.py --out <scratchpad>/next_prompt.md`. It names the first startable session from `origin/main` and fills what is mechanical. Replace every `<<CLAUDE:slot: ...>>` marker after reading the card, its brief, the closing changelog entry and the task file, then `python3 scripts/next_prompt.py --check <file>` until it prints OK. Deliver it three ways: in chat as a four-backtick block (the transcript is what survives the archive), as a `SendUserFile` card with `status: proactive`, and regenerable. A session whose card is not startable yet says so instead. Ben's rule for these prompts: no em dashes. The standing parts live in `docs/claude/next_session_prompt.md`; when a session teaches a lesson the next one would relearn, put it in that file in the same pull request.
6. **PowerShell for Ben.** `python3 scripts/post_merge.py ... --format powershell`, pasted into the reply as is: one command per fenced block, `Sync-NflDfs -Clean` first. `sync.ps1 -Clean` leaves a merged branch for `main`, fast-forwards, deletes merged local `claude/*` branches with `git branch -d`, and prints IN SYNC or what is left. It cannot be run from a cloud session, so say so rather than claiming the Windows checkout is clean.
7. **Report** in the standing order (`.claude/rules/stops-and-reports.md`): Needs Ben, Changed, Found. The prompt block and the PowerShell blocks go in this message text, before the archive.
8. **Archive last.** `get_session` with no id for this session's id, then `archive_session`. Archive only if all of these hold, and otherwise say which one held it open:
   - the merged pull request carries the `Session close:` marker, or Ben typed `/post-merge`;
   - the last `post_merge.py` run exits 0;
   - main's CI on the merge commit is green;
   - Ben has not written since the merge. A message that invokes or acknowledges this routine is not a write;
   - the next prompt passed `--check` and was delivered in chat and as a file card.

   Items Ben does outside the session (a `ben-review` label, a PowerShell block, a `[BEN: ...]` flag in a card) do not hold the archive: the transcript stays readable and `unarchive_session` reverses it. A question whose answer has to come back into this session does. `delete_trigger` any `send_later` still pending when the routine stops. If `archive_session` errors or asks for approval, report that once under Needs Ben and leave the session open; do not retry.

## One-time, Ben

Claude cannot make its own permissions looser, and the auto-mode classifier refuses the attempt ("Self-Modification"), so this is Ben's. `.claude/settings.json` lists no `mcp__claude-code-remote__*` tool, and its two subscribe entries name a tool that does not exist (`mcp__github__subscribe_pr_activity`). Unattended, the archive and the wake-up scheduling may stop on a prompt. To allow them, replace those two entries under `permissions.allow` with:

    "mcp__claude-code-remote__get_session",
    "mcp__claude-code-remote__archive_session",
    "mcp__claude-code-remote__send_later",
    "mcp__claude-code-remote__delete_trigger",
    "mcp__claude-code-remote__subscribe_pr_activity",
    "mcp__claude-code-remote__unsubscribe_pr_activity",

That file is on the protected list, so the pull request needs the `ben-review` label and Ben merges it. The question to answer: may Claude archive its own session, and schedule and cancel its own wake-ups, without a prompt? Until then the routine ends at step 8 with "archive needs your approval" under Needs Ben.

## Not yet verified

- `archive_session` on the session that is running. The tool is documented for finished child sessions. The first live use is the pull request that introduced this file; record what the tool answered here.
- That a wake reaches a session whose container was reclaimed while Ben was away.
- PowerShell cannot run in a cloud container. `sync.ps1` is parsed by the `boundaries` CI job and tested by hand on Windows only.
