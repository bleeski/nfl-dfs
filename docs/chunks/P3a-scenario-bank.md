# P3a — Bounded scenario bank on the prior_review path

Brief for chunk `P3a` of the prize-tail program. Status, dependencies and hand-back are tracked in `backlog.md` (Queue table and chunk index); this file is the specification. Moved verbatim from `backlog.md` on 2026-09-15.

- Goal: every selected lineup and every candidate has a distribution, not a
  point, and the review reports it.
- Read first: `src/nfl_dfs/simulation.py` (`simulate_factor_bank`, the
  DESIGN/SELECT/REFEREE purposes, the t(5) game factor), `config/runtime.json`
  (registered scenario counts: Showdown 20k/50k/50k, Classic 10k/20k/20k),
  `feedback_dfs_adversarial_qa.md` in project memory (measured 0.004 cross-team
  correlation, no covariance), `src/nfl_dfs/scenario_store.py`, Q2 in the 09-10
  program.
- Files: `simulation.py`, `prior_review.py` (diagnostic emission only),
  `readable_review.py`/`classic_review.py` (three quantile columns), tests.
- Scope:
  - Run a DESIGN bank of the registered size inside `prior_review` and report
    per-lineup p50/p90/p99 and P(score ≥ the field's registered top-1% proxy,
    which P0's harness supplies per mode as the median of the observed top-1%
    thresholds) for every selected lineup and every candidate. Diagnostic
    columns; no selection change.
  - Measure and report the bank's correlation structure: same-team QB to WR1,
    QB to team total, opposing team totals, K to own team total, DST to opposing
    team total. Compare against the empirical values computed from the approved
    2025 weekly stats already in the frozen team-stats artifact; the report names
    each gap.
  - Conservation checks (passing yards equal receiving yards per team,
    touchdown counts integral) already in the simulator must pass on the
    registered size within the registered wall time and RSS.
- Non-goals: no objective change, no calibration claim, no promotion; the bank is
  `DIAGNOSTIC` and the review says so.
- Acceptance: on the SF@LAR and NE@SEA snapshots the ranking of our lineups by
  p90 differs from the ranking by prior mean (if it does not, the bank has no
  covariance and the chunk has failed); the correlation table prints with its
  empirical comparison; replay is byte-identical under the registered seed. Full
  suite green.
- Hand-back: `docs/session-prompts/P3b-tail-objective.md`; P3b `READY` if P2 has
  closed.
