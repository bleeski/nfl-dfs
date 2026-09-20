# P7 — current-role depth resolution

Paste this whole file as the first message of a fresh Claude Code session
started in the `nfl-dfs` repo root. It changes an evidence-adjacent refusal and
registers a new approved source, so it is a full dev tranche and must not be
started under a lock clock.

**R25 was ruled APPROVED by Ben on 2026-09-20.** Implement the OUT-promotion.
The bounds in the R25 stanza of `backlog.md` are binding on this chunk, not
advisory: availability is re-derived from the bound salary bytes every run, a
supplied depth package can never widen it, nobody becomes selectable who was not
already, the identity gate's auto-accept rule is untouched, and every promotion
is named in the run record and the handoff.

---

## Read, in this order, and nothing else until the plan is approved

1. `CLAUDE.md` in full. It is binding, including "Shipping under a lock clock"
   and the Permanent boundaries.
2. `docs/chunks/P7-current-role-depth.md` — the specification. Its Acceptance
   section is the definition of done, all of it.
3. `backlog.md`: the R25 stanza and the P7 entries in the Queue table and the
   chunk index.
4. `changelog.md`, the `Unreleased` head: the two 2026-09-20 entries.
5. `src/nfl_dfs/qb_depth_roles.py` in full, then
   `scripts/make_offensive_role_evidence.py`,
   `src/nfl_dfs/participation.py:409-480`, and
   `src/nfl_dfs/priors.py:132-269`.
6. `docs/DATA_CONTRACTS.md:913-1010`, the existing QB depth contract. A schema
   change is a new version; v1 is never mutated.

## Runtime

`sh ./nfl.sh setup|test|doctor|<cli>` on `.venv-linux`; `.\nfl.ps1` on Windows
with `.venv`. Never mix them. Point `NFL_DFS_VENV_DIR`, `NFL_DFS_UV_CACHE_DIR`
and `NFL_DFS_UV_PYTHON_DIR` at the scratchpad. The complete suite needs an
extended tool timeout or a background run; a run killed at two minutes is a
tooling artifact, not a failure. Baseline to reproduce before changing anything
is the last line recorded in `changelog.md`.

Run `python3 scripts/session_probe.py` first. `github.com` and
`raw.githubusercontent.com` must be reachable or the depth chart cannot be
fetched and this chunk cannot be verified against real bytes.

## Why this exists

On 2026-09-20 a live Classic slate rejected Carson Wentz, Drew Lock and Malik
Willis as backups on a prior-season workload filter. All three were starting.
The nflverse depth chart carried the answer, on an allowlisted host, reachable
throughout, with a snapshot from 08:14 ET that morning.

The engine would not have helped. It reads a depth chart for quarterbacks only,
passes the published rank straight through, and refuses outright when the rank-1
quarterback is `OUT` — which is precisely the case that matters. The measurement
that makes this a defect rather than a preference is in the R25 stanza: no depth
chart is ever published between the ~11:30 ET inactive announcement and a 13:00
lock, so "refresh the depth chart" cannot be done.

## Scope

As `docs/chunks/P7-current-role-depth.md` § Scope. In short: register the source,
compute an effective depth rank for QB/RB/WR/TE keyed by `(person, position)`,
promote on `OUT` under the R25 bounds, and feed the rank to
`redistribute_opportunity`.

## Out of scope

- The identity gate's auto-accept rule. Widening it is a different risk.
- Ownership, leverage and correlation. That is Q3 and P4.
- Any change to the availability contract, or any new route to selectability.
- The Classic fallback scripts. X5 finished those on 2026-09-20.

## Acceptance

Verbatim from the brief, all of it. The load-bearing cases: Wentz and Lock
resolve to effective QB1 on the 2026-09-20 snapshot and the run does not stop;
Mayer, Hutchinson and Bateman resolve to effective rank 1 at their positions; a
kick-return depth row never becomes a player's rank at his salary-file position;
a supplied package cannot promote anyone the salary bytes still show available
above; replay is byte-identical; full suite green.

## Close-out

Update `backlog.md` (P7 status, R25 outcome), `changelog.md` under `Unreleased`
with the exact suite line and wall time, `IMPLEMENTATION_STATUS.md` if working
capability changed, and write the next `READY` chunk's prompt. Commit, push,
open a pull request and merge it on green CI under
`.claude/rules/git-authority.md`. `docs/DATA_CONTRACTS.md` is not a protected
path; `CLAUDE.md` and `.claude/rules/*.md` are, and a pull request touching them
waits for Ben's `ben-review` label.
