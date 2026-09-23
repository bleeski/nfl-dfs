# X1 — A per-session egress probe replaces asserted environment facts

Brief for chunk `X1` of the cloud-operability track. Status and dependencies are
tracked in `docs/ROADMAP.md` (status board and session card); this file is the
specification. Written 2026-09-20 from the cloud audit's finding F2.

Hand-back lines below that name a `docs/session-prompts/` file or a `READY`
status predate the roadmap. At close-out follow `.claude/skills/close-out/SKILL.md`
instead: the session card and the §1 Quick-Start replace per-chunk prompts.

- Goal: a session learns which approved sources it can actually reach *now*,
  by probing, instead of reading a sentence somebody measured once.
- Evidence: `docs/CLAUDE_CODE_SETUP.md` § "Known environment facts" (lines
  152-163 as of `ebf5797`) asserts reachability as settled fact, dated
  2026-09-17. In the audit's own cloud container on 2026-09-19, three of the six
  entries in `sources.ALLOWED_HOSTS` answered **403 at CONNECT** through the
  agent proxy. The document says the opposite. That section also still reports
  `1 failed, 735 passed, 1 skipped in 155.56s` as the suite result, which has
  been wrong since #19 merged (`917 passed, 1 skipped`). Both are the same
  defect: a measured number frozen into prose, with nothing re-measuring it.
- Why it is more than tidiness: reachability of an approved source decides
  whether an evidence gate can be cleared before lock. Under the lock-clock
  ruling, a gate no real source can clear is a defect to take to Ben, and a gate
  a reachable source *could* clear must never be relaxed. A session that
  believes a false reachability claim mis-sorts its running order and can burn
  the clock discovering at lock time that the weather capture was never
  possible. A wrong fact about evidence reachability costs a lock.
- Read first: `src/nfl_dfs/sources.py` (`ALLOWED_HOSTS`,
  `GITHUB_RELEASE_ASSET_HOSTS`, `PROHIBITED_HOSTS`, and the single permitted
  release-asset hop), the `doctor` subcommand in `src/nfl_dfs/cli.py`, and
  `docs/CLAUDE_CODE_SETUP.md` § Known environment facts.
- Files: `src/nfl_dfs/cli.py` (the `doctor` path), a new probe module or a
  function beside it, `docs/CLAUDE_CODE_SETUP.md`, tests. `sources.py` came off
  the protected list on 2026-09-20 and now merges on green, but it is still the
  allowlist: touch it only if the probe genuinely needs to live there.

## Scope

1. **Probe, do not assert.** `doctor` reports, per host in `ALLOWED_HOSTS`,
   whether it is reachable from this container right now, with the observed
   status and a timezone-aware observation time. The probe is a reachability
   check, not a data fetch: it must not retrieve, parse or retain an artifact,
   and it must not count as a capture.
2. **Record it into the run record** so a run's own artifacts say what was
   reachable when it ran, rather than leaving it in terminal scrollback.
3. **Replace the prose.** `docs/CLAUDE_CODE_SETUP.md` § Known environment facts
   stops asserting per-host reachability and points at the probe. Delete the
   stale suite line from that section too; the live number is already derived by
   `scripts/repo_state.py` from `state/last-verify.json` and printed at session
   start, so a second hand-maintained copy can only rot.

## Constraints

- **Never fetch a prohibited host, even to probe it.** `PROHIBITED_HOSTS` exists
  because DraftKings must never be contacted by any path. A probe that walks a
  host list must exclude them explicitly, and a test must prove it does.
- **A failed probe is never a cleared gate, and never a blocked run.** The probe
  is diagnostic. It reports; it does not decide `EVIDENCE_STATE`, and a host
  being unreachable must not by itself stop a run. Conversely a reachable host
  is not evidence of anything — only a capture with bytes, hash, source URI,
  observed time, parser version and license decision is.
- **`doctor` must stay fast and must not hang.** It runs at the head of a slate.
  Give every probe a short timeout and run them concurrently; state the measured
  wall time in the changelog. An offline container must get a clean "could not
  reach, here is why", not a stack trace and not a thirty-second stall.
- **No network in tests**, per `.claude/rules/tests.md`. Exercise the probe
  through injected fakes covering: 200, 403 at CONNECT, DNS failure, timeout,
  and the prohibited-host exclusion.
- Do not widen `ALLOWED_HOSTS`, and do not add a new source in this chunk.

## Acceptance

- `doctor` prints a per-host reachability line for every entry in
  `ALLOWED_HOSTS`, with observed status and a timezone-aware time, and prints
  nothing for any entry in `PROHIBITED_HOSTS`.
- A test proves no prohibited host is contacted, by asserting on the injected
  client's call list rather than on output text.
- Offline behaviour demonstrated: `doctor` still completes, still reports
  `pass_status`, and labels every host unreachable with a reason.
- `grep -n "answers HTTP 200\|are both" docs/CLAUDE_CODE_SETUP.md` returns
  nothing: the asserted reachability sentences are gone.
- The stale suite line is gone from § Known environment facts.
- Measured `doctor` wall time pasted into the changelog, before and after.
- Full suite green.

## Non-goals

No new approved host. No change to any evidence gate, release truth, or
`EVIDENCE_STATE` computation. No retrieval of actual artifacts during the probe.
No change to `PROHIBITED_HOSTS`.

## Hand-back

Set `X3` or `X4` per the queue's dependency column, and write the next session
prompt under `docs/session-prompts/`.
