---
name: dev-session
description: Start a Claude Code development session on one roadmap session (S01, S02, ...) in the nfl-dfs repo. Use at the top of a session when Ben names a session ID or says "start the next session" or "the next chunk".
disable-model-invocation: true
---

Start development on roadmap session `$ARGUMENTS` (short form, e.g. `S04` for
the row `Session 04`) of `docs/ROADMAP.md`.

0. `python3 scripts/repo_state.py --stdout`. It fetches `origin/main` first, so
   the distance it reports is the real one, and it prints the startable
   sessions in priority order and the three most recent changelog headings:
   that is what the other instances did. Another Claude Code instance may be
   working this repository right now.
1. `git status --short --branch` and `git log --oneline -15`. Report the branch and whether the tree is
   dirty. Do not reset, clean, stash or reformat anything.
2. Read, in this order and nothing else yet: `CLAUDE.md`; `docs/ROADMAP.md`
   §1, §2.1, the session's row in §2.2 and its card in §2.3; every brief its
   Source Origin names in `docs/chunks/`; the first 80 lines of `changelog.md`.
   Never read `docs/backlog-archive/`, `docs/changelog-archive/` or
   `docs/session-prompts/archive/` whole; grep them for the section a card cites.
3. Confirm the row is `Pending` and every entry in its `Depends on` is
   satisfied (`Session NN` rows `Complete`, `O<n>` items `Done` in §2.6, no
   `BEN ruling`). `repo_state.py` reports this as "startable". If not, stop and
   say which dependency is open.
4. Run the baseline before changing anything: `.\nfl.ps1 test` on Windows or
   `sh ./nfl.sh test` on Linux, with an extended timeout. Record the exact
   result line. Any failure is reported before work starts.
5. Use the branch the session was assigned, or create `claude/<sNN>-<slug>`
   from the current HEAD.
6. Enter plan mode. Produce a plan that names: files to touch (only those the
   card and its briefs list), tests to add first, the card's acceptance
   verbatim, its breakpoint, open `[BEN: ...]` questions, and what is
   explicitly out of scope. Wait for approval before editing. Once approved,
   copy the plan into `state/tasks/$ARGUMENTS.md` as one `- [ ]` line per item
   (`.claude/rules/stops-and-reports.md`) and tick items as they land.
7. Claim the session before writing code, so a concurrent instance can see it:

       python3 scripts/claim.py take $ARGUMENTS --branch <branch>

   It exits 1 and names the holder if another instance claimed this session
   less than six hours ago: stop there and say so. An older claim is stale;
   taking it is allowed, records `reclaimed_from` in `state/claims.json`, and
   goes in the changelog too. Then set the row `In Progress` in
   `docs/ROADMAP.md` §2.2, add a ledger row in §4 (LF; match the file's
   endings), and push the claim.

Never `git add .` or `-A`. Commit, push, pull request and merge authority is in
`.claude/rules/git-authority.md`; it is yours on green CI, except for the
protected paths, which are Ben's.
