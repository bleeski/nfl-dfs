# P1 — Salary-divergence diagnostic and current-team role evidence producer

Brief for chunk `P1` of the prize-tail program. Status, dependencies and hand-back are tracked in `backlog.md` (Queue table and chunk index); this file is the specification. Moved verbatim from `backlog.md` on 2026-09-15.

- Goal: a person the market prices as the slate's best cannot be scored at
  backup levels without the run saying so, and the evidence that resolves it can
  be produced from approved source bytes instead of typed.
- Evidence: Walker 0 of 18 at 0.687 pts/$1k (29th of 32) on a $10,600 tag;
  `opportunity.py` split KC attempts Mahomes 0.5395 / Fields 0.4605 while the
  policy exclusion of Fields lands after `score_pool` and never reaches
  projection (`docs/RUN_RECORD_20260914_DEN_KC.md` defects 2 and 3); SF@LAR
  rostered Mac Jones (backup, 9.45 prior) beside Purdy.
- Read first: `src/nfl_dfs/priors.py` (transfer prior, `TRANSFER_PRIOR_UNVERIFIED`),
  `src/nfl_dfs/offensive_roles.py`, `src/nfl_dfs/kicker_roles.py` (the pattern
  for a registered allocation with `allocation_version` and `does_not_establish`),
  `src/nfl_dfs/sources.py` (allowlist), `docs/DATA_CONTRACTS.md` for
  `nfl_classic_offensive_role_evidence_c1_v1`, and the R17/R21 rulings (the 2026-09-10 and
  2026-09-12 entries in `docs/backlog-archive/backlog-history-through-2026-09-14.md`).
- Files: `src/nfl_dfs/prior_score.py` or `selection.py` (diagnostic emission),
  `src/nfl_dfs/offensive_roles.py`, new `scripts/make_offensive_role_evidence.py`,
  `src/nfl_dfs/sources.py` only if a new approved host is needed, tests.
- Scope:
  - Emit `SALARY_RANK_DIVERGENCE` in the selection report and readable review:
    every selectable person whose DK salary rank within position is at least 10
    places better than his prior-points rank, with both ranks, salary, prior, and
    the evidence state that produced the prior. Diagnostic, named, never silent.
  - `scripts/make_offensive_role_evidence.py`: fetch the current depth chart
    through `sources.fetch_public_artifact` from the approved nflverse host,
    retain raw bytes and hash, and write the versioned
    `offensive_role_evidence_json` package with a registered allocation rule
    (starter gets the team's QB attempt share; listed backups zero unless the
    package declares otherwise), `allocation_version`, observed time, and
    `does_not_establish`. A depth chart establishes who starts, not how many
    targets a receiver gets; the package must say so and must not invent
    receiving shares.
  - Route the QB attempt-share allocation through that package before
    `score_pool`, so a policy exclusion is no longer the only way to stop a
    backup QB from taking 46% of the attempts.
  - **Gate semantics — RULED 2026-09-19: hard stop.** (This was an open operator
    flag; the ruling closed it, and the marker is removed rather than left to
    inflate the open count. Writing the marker out in full here, even to say it
    is closed, would re-raise it: the scanner matches the literal token.)
    Before the ruling, a transfer with no current-team evidence was
    selectable on his old-team share (R17/R21). Now: when such a person also
    trips `SALARY_RANK_DIVERGENCE`, the run treats it as an unresolved material
    role change and stops, naming the smallest evidence action — the same
    treatment a declared role change already gets. The gate is conjunctive, so
    an unverified transfer priced where his prior puts him stays a diagnostic.
    Shipped in `offensive_roles.enforce_material_role_change_gate`.
- Non-goals: no numerical share typed by anyone; no change to kicker roles; no
  retrospective forcing of Walker or anyone else into a lineup; no ownership.
- Acceptance: a fixture reproducing DEN@KC (Walker on KC with SEA history, Fields
  behind Mahomes) shows Walker in `SALARY_RANK_DIVERGENCE`, Mahomes at the full
  attempt share once the package is supplied, Fields at zero, and byte-identical
  output on replay; a fixture without the package behaves per Ben's ruling
  (stop, or diagnostic only). Full suite green.
- Hand-back: `docs/session-prompts/P3a-scenario-bank.md` written; P3a set
  `READY` once P0 has also closed.
