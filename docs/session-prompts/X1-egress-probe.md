# X1 — Replace asserted environment facts with a per-session egress probe

Paste this whole file as the first message of a fresh Claude Code session in the
`nfl-dfs` repo root. It touches `doctor`, one document and tests. No contract,
no evidence gate, no DraftKings file, no engine module on the selection path.
Either surface works. Safe on a slate day.

`CLAUDE.md` loads automatically and is binding. Read `docs/START_HERE.md` first.

---

You are doing chunk **X1**. Its brief is `docs/chunks/X1-egress-probe.md` and it
is the specification; this prompt is the orientation.

Run `python3 scripts/repo_state.py --stdout` first. If `X1` is claimed and the
claim is under six hours old, stop and say so. Otherwise claim it with
`scripts/claim.py` before writing code.

## Read, in this order, and nothing else by default

1. `docs/START_HERE.md`.
2. `docs/chunks/X1-egress-probe.md`, the brief. It has the full scope,
   constraints and acceptance statement.
3. `src/nfl_dfs/sources.py` — `ALLOWED_HOSTS`, `PROHIBITED_HOSTS`,
   `GITHUB_RELEASE_ASSET_HOSTS` and the comment explaining the single permitted
   release-asset hop.
4. The `doctor` subcommand in `src/nfl_dfs/cli.py`.
5. `docs/CLAUDE_CODE_SETUP.md` § "Known environment facts" — the prose this
   chunk replaces.
6. `changelog.md`, first 80 lines.

## Runtime

Linux: `sh ./nfl.sh setup|test <pytest args>|doctor|<cli>` on `.venv-linux`.
Windows: `.\nfl.ps1 <same>` on `.venv`. Never mix the two venvs in one session.

The suite is `917 passed, 1 skipped in 174.05s` on Linux as of `c6c73e7`, and
there is no known failing test. It needs an extended tool timeout (600000 ms) or
a background run; a run killed at two minutes is a tooling artifact, not a
failure. Record it with `python3 scripts/record_verify.py --from-log <log>`.

The `NFL_DFS_PYTEST_TMP` workaround is retired — #19 fixed the `--basetemp`
parent and the suite runs clean in a fresh container without it. If you see
hundreds of fixture-setup errors, that is a real finding, not the old bug.

## Why this chunk exists

`docs/CLAUDE_CODE_SETUP.md` asserts which approved hosts are reachable, as
settled fact, measured once on 2026-09-17. On 2026-09-19, in a cloud container,
three of the six `ALLOWED_HOSTS` answered 403 at CONNECT. The document says the
opposite.

Reachability of an approved source decides whether an evidence gate can be
cleared before lock. Under the lock-clock ruling a gate no real source can ever
clear is a defect to take to Ben, and a gate a reachable source *could* clear
must never be relaxed. A session that trusts a false reachability claim
mis-sorts its running order and finds out at lock time that a capture was never
possible. That is how you miss a lock.

The same section also still reports a suite line that has been wrong since #19
merged. Same defect, same fix: stop writing measured numbers into prose when
something already derives them.

## The two things most likely to go wrong

- **Probing a prohibited host.** `PROHIBITED_HOSTS` contains DraftKings. A probe
  that iterates a host list must exclude them explicitly, and the test must
  assert on the injected client's call list, not on output text. Contacting
  DraftKings by any path, for any reason, is a permanent boundary.
- **Letting the probe become evidence.** Reachable is not captured. Only a real
  capture with bytes, hash, source URI, observed time, parser version and
  license decision is a model input. The probe reports and nothing else: it must
  not set `EVIDENCE_STATE`, and an unreachable host must not by itself stop a
  run.

## Out of scope

No new approved host. No change to any evidence gate, release truth or
`EVIDENCE_STATE` computation. No retrieval of real artifacts during the probe.
No change to `PROHIBITED_HOSTS`. Do not start `X2`, `X3` or `X4`.

Touching `src/nfl_dfs/sources.py` is possible but not expected. It came off the
protected list on 2026-09-20, so it merges on green, but it is still the
allowlist and the probe does not obviously belong in it. Prefer putting the
probe beside `doctor` instead.

## Acceptance

The brief's Acceptance section is the contract. Write or extend the tests for it
before the code, per `CLAUDE.md`. Summary: per-host reachability in `doctor`
with observed status and a timezone-aware time; nothing printed for a prohibited
host; a test proving none is contacted; offline behaviour clean and labelled;
the asserted-reachability sentences and the stale suite line gone from
`docs/CLAUDE_CODE_SETUP.md`; measured `doctor` wall time before and after; full
suite green.

## Close-out

Run `/close-out`. Branch `claude/x1-egress-probe`. Update `backlog.md` (status,
what was relaxed or left open, the next `READY` chunk), `changelog.md` under
`Unreleased` with the exact numbers, and `IMPLEMENTATION_STATUS.md` if capability
changed. Open the pull request and merge it on green CI under
`.claude/rules/git-authority.md`, unless it touches a protected path, in which
case it waits for Ben's label.

Release the claim at close-out.

Report in a few lines: the measured `doctor` cost, which hosts were actually
reachable from your container, and any `[BEN: ...]` flag you left.
