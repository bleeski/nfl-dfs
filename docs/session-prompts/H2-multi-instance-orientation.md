# H2 — Make a starting session see what other instances changed

Paste this whole file as the first message of a fresh Claude Code session in the
`nfl-dfs` repo root. It touches the harness only: hooks, the state script, the
session skills, CI comments and two authority documents. No engine module, no
contract, no evidence gate, no DraftKings file. Either surface works. Safe on a
slate day.

**This pull request will need Ben's `ben-review` label.** Three of the five
items touch protected paths (`.claude/settings.json`, `.claude/rules/git-authority.md`,
`.github/workflows/ci.yml`). That is expected, not a mistake. Do not split the
work across pull requests to dodge the label.

---

You are doing chunk **H2**, a harness chunk. It is not part of the prize-tail
program and does not belong in the `P` queue. `CLAUDE.md` loaded automatically
and is binding.

**Start in plan mode.** Read the files below, produce a plan, and wait for Ben's
approval before editing. Two of the five items have a real design tradeoff that
is cheaper to argue in a plan than in a diff; they are called out under
*Constraints*.

Run `python3 scripts/repo_state.py --stdout` first. If `H2` is claimed and the
claim is under six hours old, stop and say so.

## Read, in this order, and nothing else until the plan is approved

1. `docs/START_HERE.md`.
2. `scripts/repo_state.py` in full. It is the thing being fixed.
3. `.claude/hooks/session_start.py` and `.claude/hooks/guard_bash.py`.
4. `.claude/settings.json`, and `.claude/rules/git-authority.md`.
5. `.claude/skills/dev-session/SKILL.md`, specifically its claim step.
6. `changelog.md`, first 120 lines, for the 2026-09-17 entries describing what
   the harness already does and the two known `guard_bash.py` false positives.

## Runtime

Either surface. The suite is `790 passed, 1 skipped in 147.37s` on Linux and
there is no known failing test. Extended tool timeout (600000 ms) or a
background run.

## Why

Ben runs several Claude Code instances against this repository. A starting
instance is supposed to learn what the others changed before it writes code.
Today it mostly cannot.

**The orientation number is read from a cache.** `scripts/repo_state.py:79`
computes the distance to `origin/main` with `git rev-list --left-right --count
origin/main...HEAD` and never fetches. `origin/main` is a remote-tracking ref
that only moves on fetch or pull, so a session that cloned an hour ago, or one
resuming after an idle stretch, prints `behind origin/main by 0` while another
instance has merged three pull requests. The single number meant to say "someone
else changed things" is the one number guaranteed to be stale.

**The prose record is never shown.** Every session must write a dated
`Unreleased` entry in `changelog.md` saying what changed and why. That is exactly
the artifact a new instance needs, written by the instance that made the change,
and nothing surfaces it at startup. A commit subject is not a substitute.

**Drift mid-session is invisible.** Startup orientation cannot help when another
instance merges forty minutes into your work. Nothing checks before you push.

**Two instances can take the same chunk.** `state/claims.json` exists and
`.claude/skills/dev-session/SKILL.md` step 7 already tells a session to write a
claim, but no code writes or reads one. The instruction is currently decorative.

**Branch protection does not exist and never will.** Ben is on a GitHub free
plan, where rulesets and branch protection are unavailable on a private
repository. Three places assert or imply otherwise and are now false:
`docs/CLAUDE_CODE_SETUP.md:32-49` (the whole "Branch protection on `main`"
section, ending where "The review label" begins at `:50`),
`.github/workflows/ci.yml:3` ("`main` is protected and changes only through a
merged pull request"), and the framing in `.claude/rules/git-authority.md`.
Nothing server-side enforces merge-on-green.
The controls that remain are entirely client-side: the deny list in
`.claude/settings.json`, `guard_bash.py`, and the rules documents. They do bind
every instance, because every instance clones them, and that is worth saying
plainly rather than leaving a reader to assume a server is watching.

## Scope

1. **Fetch before deriving state.** `scripts/repo_state.py` refreshes
   `origin/main` before measuring distance, and reports when it could not. An
   offline or air-gapped session must still start, with the staleness labelled
   rather than silently wrong.
2. **Surface the changelog.** `.claude/hooks/session_start.py` prints the most
   recent three dated `###` headings under `## Unreleased`, newest first. Read
   the headings only; never the whole file.
3. **A freshness gate before push.** A `PreToolUse` check that refuses a push
   when `main` has moved since this branch's merge base, naming what moved and
   telling the session to merge `origin/main` first. Wire it in
   `.claude/settings.json`.
4. **Finish the claim protocol.** Code that writes and reads `state/claims.json`:
   claim a chunk, see an existing claim, release at close-out, and treat a claim
   older than six hours as reclaimable with a recorded note. Wire it into
   `/dev-session` and `/close-out` so the skills' existing instructions become
   true. `state/claims.json` is tracked on purpose; the rest of `state/` is not.
5. **Correct the branch-protection claims** in the three places above. Say what
   is actually true: the gate is client-side and convention-backed, CI is
   advisory rather than blocking, and what that means for an instance about to
   merge its own work.

   Keep the `ben-review` label. `docs/CLAUDE_CODE_SETUP.md:50` onward is still
   correct and still needed: `protected-paths` runs as a CI job regardless of
   branch protection, and the label is how a protected change passes it. Only
   the claim that a server blocks the merge is wrong.

While you are in `guard_bash.py`, fix the two false positives the 2026-09-17
changelog records: `git add -u <explicit path>` is refused though a scoped `-u`
is an explicit path list, and `git stash list` and `git stash show` are refused
though both are read-only. Both currently fail in the safe direction, so this is
a usability fix, not a safety one. Keep the refused-and-allowed test pairs.

## Constraints that bound the design

**A hook may never fail a session or a tool call.** Both existing hooks exit 0
unconditionally and fall back to the normal permission flow on any error. Keep
that. A crash in orientation code must not stop work.

**The `PreToolUse` matcher is tool-level, not command-level.** It fires on every
single `Bash` call. A fetch on every Bash call would be crippling, so the script
must decide cheaply whether the command is a push before doing anything that
touches the network. Say in the plan how you detect that and what it costs on a
non-push call.

**Startup latency is a real budget.** `session_start.py` currently runs in about
55 ms and the hook is capped at 10 seconds in `.claude/settings.json`. A network
fetch can take seconds and fires on `startup`, `resume`, `clear` and `compact`.
Decide in the plan how to keep startup fast: a short fetch timeout, a
time-to-live so a fetch happens at most once every few minutes, doing it in the
background, or something better. State the tradeoff and pick one; do not just
add a blocking network call and hope.

**Output stays small.** The hook prints at most 60 lines today and that ceiling
exists to protect context. Three changelog headings plus a staleness line must
fit inside it, not extend it.

**Determinism and offline.** No test may reach the network.
`.claude/rules/tests.md` requires approved-source adapters to be exercised
through captured fixture bytes; the same applies here. Test the fetch and
freshness logic through injected fakes, not a live remote.

## Out of scope

No engine module, no contract, no `config/` file, no evidence gate, no change to
any release truth. Do not start `P0`, `P0b` or `P1`. Do not do H1's work: the
`backlog.md`, `plan.md`, `IMPLEMENTATION_STATUS.md` and session-prompt cleanup
belongs to `docs/session-prompts/H1-ledger-authority-alignment.md`. Do not build
the fragment-ledger migration (`changelog.d/`, chunk status in brief
frontmatter); H2 owns claims, and fragments stay deferred until a real collision
is observed. Do not attempt to configure branch protection, and do not suggest
making the repository public to obtain it.

## Acceptance

- In a clone whose `origin/main` ref is deliberately stale, the digest reports
  the true distance. Demonstrate it: rewind the local `origin/main` ref, run the
  script, and show it recovering the real number.
- With the network unavailable, the digest still prints and labels the staleness
  instead of reporting a false zero. Demonstrate that too.
- The digest shows the three most recent dated changelog headings, and the whole
  hook output is still 60 lines or fewer.
- Startup stays fast. Paste the measured time and say which of the latency
  strategies you chose and why.
- A push attempted when `main` has moved is refused with a named reason; a push
  when `main` has not moved is unaffected. Both directions demonstrated.
- A non-push `Bash` call costs nothing measurable. Paste the numbers.
- Two `/dev-session` runs on the same chunk: the second reports the first's
  claim rather than proceeding. Demonstrate with a real `state/claims.json`.
- A claim older than six hours is reclaimable and the reclaim is recorded.
- `grep -rn "branch protection" docs/ .claude/ .github/` returns nothing
  asserting that protection is configured.
- `guard_bash.py` accepts `git add -u src/nfl_dfs/ownership.py` and
  `git stash list`, still refuses `git add -u` bare, `git stash push`,
  `git push origin +HEAD:main` and the rest of `REFUSED_COMMANDS`.
- Full suite green with the new tests added, `doctor` green,
  `git diff --check` clean.

## Close-out

Run `/close-out`. Branch `claude/h2-multi-instance-orientation`. Open the pull
request, then **stop and tell Ben it needs the `ben-review` label**; do not merge
it yourself even when all three checks pass, because it touches protected paths.

Report in a few lines: the latency strategy you chose, whether the claim
protocol is now genuinely enforced or only recorded, what the freshness gate
costs on an ordinary Bash call, and any `[BEN: ...]` flag you left.
