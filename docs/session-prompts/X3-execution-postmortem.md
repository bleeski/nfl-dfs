# X3 — execution postmortem, recovery sweep, compaction continuity

Paste this whole file as the first message of a fresh Claude Code session
started in the `nfl-dfs` repo root. It adds hooks and one behavioural rule. It
touches no engine module, no contract and no evidence gate, and it must not be
started under a lock clock.

**Item 4 is the reason this chunk is near the front of the queue.** An attached
MCP server returns stub weather, shaped exactly like the answer to the evidence
gate that cost the 2026-09-20 Week 2 Classic slate. Nothing in the repository
currently says MCP output is not evidence. If you can only land one thing in
this session, land item 4.

---

## Read, in this order, and nothing else until the plan is approved

1. `CLAUDE.md` in full, including "Shipping under a lock clock" and the
   Permanent boundaries.
2. `docs/chunks/X3-execution-postmortem.md` — the specification. Its Acceptance
   section is the definition of done, all of it.
3. `backlog.md`: the Queue table row for `X3` and its chunk index entry.
4. `changelog.md`, the `Unreleased` head.
5. The three existing hooks, which are the pattern to follow and the constraint
   to respect: `.claude/hooks/session_start.py`,
   `.claude/hooks/guard_bash.py`, `.claude/hooks/push_freshness.py`.
6. `.claude/settings.json` for how hooks are registered. It is a protected path:
   read it freely, and if the chunk needs it changed, that pull request carries
   Ben's `ben-review` label.

## Runtime

`sh ./nfl.sh setup|test|doctor|<cli>` on `.venv-linux`; `.\nfl.ps1` on Windows
with `.venv`. Never mix them. The complete suite needs an extended tool timeout
(600000 ms) or a background run; a run killed at two minutes is a tooling
artifact, not a failure. A fresh container needs `sh ./nfl.sh setup` before the
suite will run at all — it fails with `project environment is missing`, which is
not a test failure. Baseline to reproduce before changing anything is the last
line recorded in `changelog.md`.

## Why this exists

Two findings from the cloud audit, F7 and F8.

**F7:** nothing reviews a run. A run that half-finished, hit a refusal it should
have reported, or died with its container leaves no postmortem and no marker.
The next session cannot tell a clean stop from an abandonment.

**F8:** `DFS_Architect_MCP` exposes `get_weather` and it returns stub data. The
2026-09-20 slate was lost to an unreachable `api.weather.gov`, and every route
to a portfolio needed a weather enum per non-dome game. A session under lock
pressure could reach for that MCP tool in good faith and produce twelve
observations it never made. The only thing that stopped it that day was a
session treating `CLAUDE.md`'s "never fabricate an observation to clear a gate"
as binding. That is a rule holding, not a mechanism.

## Scope

As `docs/chunks/X3-execution-postmortem.md` § Scope, all four items: the
`PostToolUse` and `PostToolUseFailure` postmortem, the recovery sweep for
abandoned runs, the `PreCompact`/`PostCompact` continuity block, and the rule
that MCP output is never a model input and never evidence.

Since the protected list narrowed on 2026-09-20, a rule file in
`.claude/rules/` merges on green. Only the `CLAUDE.md` route carries
`ben-review`. Prefer the rule file unless the rule must be universal.

## Out of scope

- Removing or reconfiguring the MCP server. The rule is what makes it safe, and
  the server is not this repository's to manage.
- Any engine module, contract, evidence gate or release truth.
- Outcome postmortems against settled results. That needs graded slates and
  belongs with `P0` and the `Q` tranche.

## Constraints that will bite

- **A hook may never fail a session or a tool call.** All three existing hooks
  exit 0 unconditionally and fall back to the normal permission flow on error.
  A crash in postmortem code must not stop a slate.
- **`PostToolUse` fires on every tool call.** Decide cheaply whether a call is
  run-related before doing real work, and state in the changelog what a non-run
  call costs.
- **`PreCompact` cannot inject text that survives into the compacted context.**
  This was measured during the audit. Design around it; writing to a file that
  `PostCompact` or the session-start digest reads back is the shape that
  survives. Do not assume injection works and discover later that it did not.
- Session-start output has a 60-line ceiling that protects context. A
  recovery-sweep line has to fit inside it.
- No network in tests. Exercise hooks through injected fakes and fixture
  directories.

## Acceptance

Verbatim from the brief, all of it. The load-bearing cases: a mid-way failure
produces a postmortem naming the failure, demonstrated with a real failing run
rather than a unit test alone; a `data/runs/` directory with no terminal
decision is reported once at session start inside the ceiling; compaction
continuity demonstrated end to end with the chunk ID, branch, modified files,
last suite line and open `[BEN:]` flags surviving;
`grep -rn "MCP" .claude/rules/ CLAUDE.md` finds the rule; a non-run tool call
costs nothing measurable, with the numbers pasted; full suite and `doctor`
green.

## Close-out

Update `backlog.md` (`X3` status, what was relaxed or left open, the next
`READY` chunk), `changelog.md` under `Unreleased` with the exact suite line and
wall time, `IMPLEMENTATION_STATUS.md` if working capability changed, and write
`docs/session-prompts/X4-greenfield-spec.md` per the brief's Hand-back. Commit,
push, open a pull request and merge it on green CI under
`.claude/rules/git-authority.md`. Nothing here is a protected path except
`.claude/settings.json`; if you change that, the pull request waits for Ben's
label.
