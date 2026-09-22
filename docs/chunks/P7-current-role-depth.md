# P7 — Current-role depth resolution

Brief for chunk `P7` of the prize-tail program. Status, dependencies and hand-back are tracked in `docs/ROADMAP.md` (status board and session card); this file is the specification. Written 2026-09-20 from the Week 2 Classic post-mortem.

- Goal: the engine knows who is actually starting today, for every skill
  position, and a backup whose starter is `OUT` inherits the job instead of
  stopping the run.
- Read first: `src/nfl_dfs/qb_depth_roles.py` (the whole file; especially
  `resolve_qb_depth_roles` and the refusal at `:382-386`),
  `scripts/make_offensive_role_evidence.py` (the producer that already fetches
  the depth chart through `sources.fetch_public_artifact`),
  `src/nfl_dfs/participation.py:409-480` (`redistribute_opportunity`, which
  reallocates an `OUT` player's share proportionally and never reads
  `pos_rank`), `src/nfl_dfs/priors.py:132-269` (`source_specifications`, the
  seven registered sources), `docs/DATA_CONTRACTS.md:913-1010` (the existing QB
  depth contract), and the 2026-09-20 entries in `changelog.md`.
- Files: `priors.py` (register the source), `qb_depth_roles.py`, a new
  non-QB depth module or an extension of it, `participation.py`,
  `docs/DATA_CONTRACTS.md` (a new contract version; v1 is never mutated),
  tests.

## Why, with the measurement

On 2026-09-20 the session rejected Carson Wentz, Drew Lock and Malik Willis on a
prior-season workload filter. All three were starting. The nflverse depth chart
carried the answer and was reachable the whole time.

The engine could not have used it either. `qb_depth_roles.py:382-386` refuses
with `QB_DEPTH_STARTER_NOT_SELECTABLE` when the rank-1 QB is not selectable, and
tells the operator to "refresh the depth chart after the inactive or exclusion
change". Measured publication cadence of `depth_charts_2026.csv`:

| Day | Last snapshot that day |
|---|---|
| 2026-09-13 (Week 1 Sunday) | 08:42 ET |
| 2026-09-20 (Week 2 Sunday) | 08:14 ET |

Official inactives publish about 11:30 ET for a 13:00 lock. **No depth chart is
published between the inactive announcement and lock.** The refusal's stated
remedy does not exist inside the window where it is needed.

## Scope

- **Register `depth_charts` as an `NflverseSource`** in
  `source_specifications()`, with `required_columns`, a `parser_version` and a
  `staleness_basis` naming the twice-daily cadence, so it is frozen into the
  prior package and hash-bound like the other seven. Today it lives only in a
  producer script with its own 36h expiry.
- **Effective depth rank**, for QB/RB/WR/TE: published `pos_rank` with everyone
  the bound salary bytes flag unavailable removed from above. Key the rank by
  `(person, position)`, never by person alone — a player's first depth row is
  sometimes his kick-return line, and using it silently mis-slots him.
- **OUT-promotion**, replacing the refusal. **R25 was ruled APPROVED on
  2026-09-20**; its bounds are binding here. The promotion re-derives
  availability from the bound salary bytes, exactly as `freeze_prior_package`
  does at `priors.py:2139`, so it can never be widened by a supplied file alone;
  nobody becomes selectable who was not already; the identity gate's auto-accept
  rule is untouched. Report every promotion in the run record and the handoff.
- **Feed `redistribute_opportunity`** the effective rank so a vacated share goes
  to the person who inherits the role rather than proportionally to everyone at
  the position.

## Non-goals

- No change to the availability contract itself, and no new way for a person to
  become selectable.
- No ownership, leverage or correlation work; that is Q3 and P4.
- Do not touch the auto-accept rule in the identity gate. Widening it is a
  different risk and is not in this chunk.

## Acceptance

- On the 2026-09-20 salary snapshot, with Kyler Murray and Sam Darnold
  DraftKings-`OUT`, the resolver names Carson Wentz and Drew Lock as the
  effective rank-1 quarterbacks and the run does not stop.
- Michael Mayer (LV TE 2→1), Xavier Hutchinson (HOU WR 2→1) and Rashod Bateman
  (BAL WR 2→1) resolve to effective rank 1 on the same snapshot.
- A player whose only depth row is a kick-return line is not given that rank at
  his salary-file position.
- A supplied depth package cannot promote anyone the salary bytes still show as
  available at a higher rank; attempting it is a named refusal with a test.
- Replay is byte-identical on the frozen snapshot. Full suite green.

## Hand-back

`docs/session-prompts/P7-current-role-depth.md`. On close-out, update
`backlog.md` (P7 status, and the next dependency-satisfied chunk set `READY`
with its prompt written) and `changelog.md` with the exact suite line and wall
time. Name every promotion the acceptance snapshot produced, so the first
reader of that entry can see which players the ruling actually moved.
