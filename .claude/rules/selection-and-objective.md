---
paths:
  - "src/nfl_dfs/selection.py"
  - "src/nfl_dfs/prior_score.py"
  - "src/nfl_dfs/opportunity.py"
  - "src/nfl_dfs/simulation.py"
  - "src/nfl_dfs/portfolio.py"
  - "src/nfl_dfs/portfolio_enforcement.py"
  - "src/nfl_dfs/classic_portfolio.py"
  - "src/nfl_dfs/candidate_families.py"
  - "src/nfl_dfs/optimizer.py"
  - "src/nfl_dfs/ownership.py"
  - "src/nfl_dfs/field.py"
  - "src/nfl_dfs/economics.py"
  - "src/nfl_dfs/payouts.py"
---

# Scoring, selection, and objective code

- Every objective, allocation, scoring and ownership rule is a registered version
  string (`objective_version`, `allocation_version`, `score_version`) and every
  report carries `does_not_establish`. Adding behavior means adding a version,
  not editing the semantics behind an existing one.
- The operating path is `prior_review`; it must never import `field.py`,
  `economics.py` or production portfolio economics (the `never_calls` list in the
  selection report is asserted by tests). New diagnostics land there as
  clearly-labelled columns first, then become objective terms in a later chunk.
- Determinism: registered seeds from `config/runtime.json`, byte-identical
  replay under the same inputs, and a copied-package replay test for anything
  that writes an artifact.
- `OPTIMAL` is always `OPTIMAL_ACTUAL_CANDIDATE_BANK`, scoped to the reported
  bank with its completeness statement. Never a full-slate claim.
- DESIGN, SELECT and REFEREE banks are disjoint; REFEREE recomputes and may
  block; it never tunes. Effective sample size is DECLARED (a stated standard
  error that is too large widens REFEREE tolerance, which is the failure mode).
- Vocabulary in code, logs and JSON: `prior_points`, `p90`, `predicted_copies`,
  `DIAGNOSTIC`. Never `EV`, `ROI`, `win_probability`, `cash_probability`,
  `calibrated`, `edge`.
- `AvgPointsPerGame` must remain unreachable from any function in these files;
  the mutation tests that prove it stay green.
- Showdown Captain scoring is 1.5x and CPT salary comes from the CPT row; the
  underlying person is the identity for exposure, uniqueness and overlap.
- Ben's two goals (R34) are large prizes and minimizing washouts, through
  leverage and diversification. A change that raises total mean prior points
  by concentrating captains or exposure moves away from both. Measure both,
  captain spread and shared failure points first, as named diagnostic columns
  before either becomes an objective term.
