# X3 — Execution postmortem, recovery sweep, and continuity across compaction

Brief for chunk `X3` of the cloud-operability track. Status and dependencies are
tracked in `backlog.md` (Queue table and chunk index); this file is the
specification. Written 2026-09-20 from the cloud audit's findings F7 and F8.

- Goal: every run reviews itself without being asked, an abandoned run leaves a
  trace somebody finds, and a compacted session does not lose the facts that
  make its work safe.
- Evidence (F7): nothing reviews a run today. A run that half-finished, hit a
  refusal it should have reported, or died with its container leaves no
  postmortem and no marker. The next session cannot tell a clean stop from an
  abandonment.
- Evidence (F8): an attached MCP server, `DFS_Architect_MCP`, exposes
  `get_weather` and it **returns stub data**. That is the single most dangerous
  thing the audit found, because its shape is exactly the shape of the answer to
  the blocked weather evidence gate. Nothing in the repository currently says
  MCP output is not evidence. A future session under lock-clock pressure could
  reach for it in good faith.

## Scope

1. **Execution postmortem, automatic, per run.** A `PostToolUse` hook **and** a
   `PostToolUseFailure` hook. Both are needed: `PostToolUse` fires only on
   success, so a failure-only path is invisible to it, and the failures are the
   ones worth reviewing. The postmortem records what ran, what refused, what was
   relaxed under the lock-clock ladder, and the four release truths as reported.
2. **Recovery sweep for abandoned runs.** Something that, at session start,
   notices a run directory under `data/runs/` that was begun and never reached a
   terminal release decision, and says so. A dead container is the normal cause;
   the point is that it stops being silent.
3. **Continuity across compaction.** A `PreCompact`/`PostCompact` block carrying
   what `CLAUDE.md` already requires be preserved: the chunk ID, the branch, the
   list of modified files, the last full-suite result line, and every open
   `[BEN: ...]` flag. **Note the constraint measured during the audit:
   `PreCompact` cannot inject text that survives into the compacted context.**
   Design around that; do not assume it works and discover later that it did not.
   Writing to a file that `PostCompact` or the session-start digest reads back is
   the shape that actually survives.
4. **A rule that MCP output is never a model input and never evidence.** This is
   the F8 fix. It belongs in `.claude/rules/` with `paths:` frontmatter, or in
   `CLAUDE.md` if it must be universal. Both are **protected paths**, so this
   pull request carries `ben-review`. Say plainly in the description that the
   trigger was a live MCP server returning stub weather.

## Constraints

- **A hook may never fail a session or a tool call.** Both existing hooks
  (`session_start.py`, `guard_bash.py`) exit 0 unconditionally and fall back to
  the normal permission flow on any error. `push_freshness.py` fails open when
  the network is unavailable. Keep all of that. A crash in postmortem code must
  not stop a slate.
- **`PostToolUse` fires on every tool call.** Decide cheaply whether a call is
  run-related before doing any real work, and state in the changelog what a
  non-run call costs. The same lesson `push_freshness.py` learned for `Bash`.
- **Output stays small.** The session-start hook prints at most 60 lines and
  that ceiling protects context. A recovery-sweep line has to fit inside it.
- **The postmortem is a record, not a gate.** It never changes
  `RELEASE_DECISION`, never clears an evidence gate, and never re-runs
  selection. It reports what happened.
- **Never describe a postmortem's green result as upload-ready.** Every current
  path still ends `MODEL_STATUS=PRIOR_ONLY` and
  `RELEASE_DECISION=DO_NOT_UPLOAD`.
- No network in tests. Exercise hooks through injected fakes and fixture
  directories.

## Acceptance

- A run that fails mid-way produces a postmortem naming the failure; demonstrate
  with a real failing run, not a unit test alone.
- A run that succeeds produces a postmortem naming the four release truths.
- A `data/runs/` directory left without a terminal decision is reported at
  session start, once, inside the 60-line ceiling.
- Compaction continuity demonstrated end to end: compact a session and show the
  chunk ID, branch, modified files, last suite line and open flags surviving.
  If `PreCompact` injection does not survive, show the mechanism that does.
- `grep -rn "MCP" .claude/rules/ CLAUDE.md` finds the rule, and it says plainly
  that MCP output is never a model input and never evidence.
- A non-run tool call costs nothing measurable; paste the numbers.
- Full suite green, `doctor` green.

## Non-goals

No engine module, no contract, no change to any evidence gate or release truth.
No outcome postmortem against settled results; that needs graded slates and
belongs with `P0` and the `Q` tranche. Do not remove or reconfigure the MCP
server: the rule is what makes it safe, and the server is not this repository's
to manage.

## Hand-back

Set `X4` per the queue's dependency column, and write
`docs/session-prompts/X4-greenfield-spec.md`.
