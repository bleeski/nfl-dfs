# After a merge: the next prompt, the cleanup, the archive

Ben's request, 2026-10-08, and the standing acknowledgement for the last step: "Once a PR is merged (1) Claude automatically writes the prompt for the new chunk of work for me to copy and paste into a new dev session in the same format (2) claude does any necessary repo cleanup to remove extraneous branches, make sure local and github are in sync etc. If anything requires powershell commands it should present them in copy and paste format. Once all this is done the session should auto archive." His second ruling the same day (below, under "When it runs") narrows all of it to roadmap dev sessions: the standing acknowledgement covers the archive of a roadmap dev session and is not a request to archive any other session.

This file is Claude's own procedure under CLAUDE.md "Getting better". It changes no permanent boundary. `scripts/post_merge.py` and `scripts/next_prompt.py` are its instruments; `tests/test_post_merge.py` and `tests/test_next_prompt.py` pin them.

## When it runs

**Roadmap dev sessions only (Ben, 2026-10-08, second ruling).** The next prompt, the sync check, the branch cleanup, the PowerShell blocks and the archive belong to a roadmap dev session: one `docs/ROADMAP.md` row, started by `/dev-session SNN` or by the pasted handoff prompt, and ended by `/close-out`. The mechanical test is the marker below, because only `/close-out` writes it and only a roadmap card reaches `/close-out`. A lineup run never starts the post-merge routine on its own. A lineup run is operating a slate: `run-slate`, the baseline, a review file, late swap, the judgment passes, the ceiling pass, QA. None of the eight steps runs for it on its own, and the session stays open for late swap. A pull request a lineup run opens or merges (slate inputs, records, a procedure fix) is a mid-session merge: one line saying so and nothing else. Never write the `Session close:` line outside `/close-out`, and never in a lineup run's pull request. Grading, the standings checklist and one-off procedure work are not roadmap dev sessions either.

The routine runs when the merged pull request closes a roadmap dev session's work. A session can merge several pull requests from one branch (Session 66 merged #119 and #120 from the same head), so a count of open pull requests proves nothing. The signal is a marker: `/close-out` puts this line in the PR body, on a line of its own

    Session close: post-merge routine runs when this merges (docs/claude/post_merge.md).

and the routine runs when any of these happens:

1. I merge a pull request whose body carries that line.
2. Ben merges one, and the `pull_request.closed` wake says `merged`. Read the body with `pull_request_read get` first. No marker means a mid-session merge: say so in one line and do nothing else.
3. Ben types `/post-merge`. That runs the routine in any session, a lineup run included, because a typed command is an explicit request. It does not archive by itself (step 8).

The marker is checked strictly for 1 and 2, and again for step 8's first condition whatever triggered the routine, because a pull request body is text anyone can write and another pull request may quote it: one line of the body must equal the marker exactly, and the merged pull request's `head.ref` must equal this session's branch (`git branch --show-current`). A body that merely mentions the marker, or a pull request from another branch, is a mid-session merge. A typed `/post-merge` finds its pull request by that `head.ref`, never as the newest merged pull request, which may be another session's close-out: Ben can merge one in a dev tab and type `/post-merge` in a lineup tab.

## The routine, in order

1. **Read the state.** List the open pull requests (`list_pull_requests`, state open) and note the merged one's `head.ref` and `head.sha`. Then run

       python3 scripts/post_merge.py --no-open-prs --merged-pr-head <branch>=<sha>

   (use `--open-pr-head <branch>` once per open pull request instead of `--no-open-prs`). It fetches with no cache, so a merge made a second ago is visible. Exit 0 means in sync, 1 means commands are pending, 2 means blocked. A cloud clone is shallow, and ancestry in a shallow history can be wrong, so the first command it prints is `git fetch --unshallow origin` (a fetch that only adds history, about a second here): run it, then run the check again.

   What blocks (exit 2), because work could be lost or the answer cannot be trusted: `DIRTY_TREE`; `UNPUSHED_COMMITS` (commits on no remote); `HEAD_NOT_IN_ORIGIN_MAIN` (the checkout holds commits `origin/main` lacks, which includes a follow-up pushed after the merge); `LOCAL_ONLY_COMMITS` (a local `claude/*` branch with commits on no remote); `MAIN_HAS_LOCAL_COMMITS`; `FETCH_FAILED`; `OPEN_PRS_UNKNOWN`. A merge by squash or rebase leaves the original commits unmerged by ancestry, so it blocks until Ben decides; this repository merges with merge commits. What never blocks but is listed under `for_ben`: an unmerged branch, a stash, a worktree, a branch that is not `claude/*`.
2. **Clean up.** Run each line of `--format commands` as its own Bash call. They are `git push origin --delete claude/...` for a head that was a merged pull request's head, with its sha matching, and nothing else: GitHub already deletes a merged head, so this is a safety net. If the harness denies one, stop that step, hand Ben the exact command, and do not retry in pieces. The script never runs a mutating git command itself, because `Bash(python3 scripts/:*)` would hide it from the deny list, the Bash guard and the classifier. Never delete an unmerged branch, a `codex/*` branch, a stash or a worktree: they go to Ben under `for_ben`.
3. **Fix what blocks.** A dirty tree, unpushed commits or a failed fetch is work, not a reason to archive.
4. **Read main's CI on the merge commit.** `actions_list` with `list_workflow_runs`, `perPage` 3 (each run repeats its whole commit message) and `workflow_runs_filter` `{"branch": "main", "event": "push"}`; take the run whose `head_sha` is the merge commit. One `CI` run holds the `boundaries`, `suite` and `windows` jobs. `protected-paths` runs on pull requests only, so it is not on `main`: it was green on the pull request. If the run is `completed`, read its `conclusion`. If it is still going, `list_workflow_jobs` on the run id and judge `suite` and `boundaries`; `windows` is reported and never waited on, because it runs up to 45 minutes and gates nothing. Pending: `send_later` for 20 minutes, at most twice. `cancelled` (a second merge cancelled the run): read the newest run. Red: it is work, so fix it under `.claude/rules/git-authority.md` and keep the session open.
5. **Write the next prompt.** `python3 scripts/next_prompt.py --out <scratchpad>/next_prompt.md`. It names the first startable session from `origin/main` and fills what is mechanical. Replace every `<<CLAUDE:slot: ...>>` marker after reading the card, its brief, the closing changelog entry and the task file, then `python3 scripts/next_prompt.py --check <file>` until it prints OK. Deliver it three ways: in chat as a four-backtick block (the transcript is what survives the archive), as a `SendUserFile` card with `status: proactive`, and regenerable. A session whose card is not startable yet says so instead. Ben's rule for these prompts: no em dashes. The standing parts live in `docs/claude/next_session_prompt.md`; when a session teaches a lesson the next one would relearn, put it in that file in the same pull request.
6. **PowerShell for Ben.** `python3 scripts/post_merge.py ... --format powershell`, pasted into the reply as is: one command per fenced block. When the merge that just landed changed `sync.ps1` (the report says so), Ben's checkout still has the old script, which has no `-Clean`, so the first block is plain `Sync-NflDfs` and the second `Sync-NflDfs -Clean`; otherwise `Sync-NflDfs -Clean` comes first. `sync.ps1 -Clean` leaves a merged branch for `main`, fast-forwards, deletes merged local `claude/*` branches with `git branch -d`, and prints IN SYNC or what is left. It cannot be run from a cloud session, so say so rather than claiming the Windows checkout is clean. The blocks that list an unmerged branch use `git -C` with Ben's checkout path, so they work from any folder, and the delete command appears only when the open-PR list was read.
7. **Report** in the standing order (`.claude/rules/stops-and-reports.md`): Needs Ben, Changed, Found. The prompt block and the PowerShell blocks go in this message text, before the archive.
8. **Archive last.** `get_session` with no id for this session's id, then `archive_session`. Archive only if all of these hold, and otherwise say which one held it open:
   - this session's merged pull request carries the `Session close:` marker (the strict check above), or Ben asks for the archive in this session after the merge (typing `/post-merge` alone does not ask for it, and neither does the standing quote at the top of this file, so a lineup run he ran it in stays open for late swap);
   - the last `post_merge.py` run exits 0;
   - main's CI on the merge commit is green;
   - Ben has not written since the merge. A message that invokes or acknowledges this routine, or asks for the archive, is not a write;
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
- PowerShell cannot run in a cloud container. `sync.ps1` is parsed by the `boundaries` CI job (PowerShell 7) and checked statically by `tests/test_sync_ps1.py` for 5.1-safe syntax, but nothing has run it under Windows PowerShell 5.1: Ben's first `-Clean` is the real test.
- The housekeeping list in the next prompt reads only the closing merge's own diff and matches the literal phrase "recorded by the next session". A ledger row that says "recorded by Session NN" is treated as done, and the merge SHA of a close-out pull request is not recorded anywhere by this routine.
- The lessons slot in the prompt is checked for length only; it is not pre-filled from the session's changelog entry.
