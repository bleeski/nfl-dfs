---
name: onboard
description: Orient a Claude Code session in the nfl-dfs repo from cold. Use at the start of any session where the SessionStart hook did not run, after /clear or a compaction, when picking up work another instance started, or whenever Ben asks "where are we" or "what's the state of the repo".
---

Get oriented before doing anything else. This takes one tool call and about a
minute of reading, and it is cheaper than a wrong assumption about what another
instance already did.

1. `python3 scripts/repo_state.py --stdout`. This is derived from the files, not
   from anyone's memory: branch, dirty count, the startable roadmap sessions in
   priority order, active and stale claims, the last recorded suite result, how many slates are
   graded, and open `[BEN: ...]` flags.
2. Read `docs/START_HERE.md`. One page, and it is the whole brief: the permanent
   boundaries, the four release truths, the lock-clock ruling, and where
   authority lives.
3. Only then read for the task in front of you:
   - developing: `docs/ROADMAP.md` §1 and the session's card in §2.3, then
     `/dev-session <SNN>`
   - operating a slate: `docs/RUNBOOK.md`
   - committing, merging, branches: `.claude/rules/git-authority.md`
   - what actually works today: `IMPLEMENTATION_STATUS.md`, not the spec

Three things a cold session gets wrong most often:

- **You are probably not alone.** Check the claims before starting a session. A
  claim under six hours old belongs to someone else.
- **A cloud clone has no run history.** `data/runs`, `data/registry`,
  `data/models`, `data/standings/inbox` and `outputs` are all gitignored. An
  empty standings checklist in a fresh clone is the tooling working correctly,
  not a finding about the corpus.
- **Status in prose is stale by default.** The latest run artifacts and their
  hashes are authoritative for slate state. `docs/ROADMAP.md` §2.2 is
  authoritative for work status. Neither another document nor an earlier
  conversation is.

Report back in a few lines: branch, what is claimed, what is startable, last suite
result, and what you propose to do. Do not start work until that is said out
loud.
