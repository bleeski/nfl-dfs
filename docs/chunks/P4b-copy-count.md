# P4b — Exact-lineup copy-count predictor

Brief for chunk `P4b` of the prize-tail program. Status, dependencies and hand-back are tracked in `docs/ROADMAP.md` (status board and session card); this file is the specification. Moved verbatim from `backlog.md` on 2026-09-15.

- Goal: predict how many field entries will share each of our lineups, because
  that number is the denominator of a Showdown first prize.
- Read first: `src/nfl_dfs/field.py` (`generate_opponent_field`,
  `scale_field_multiplicities`), report section 4.2 and 8.1 F, greenfield
  section 3.5.
- Files: `field.py`, `prior_review.py` (per-lineup `predicted_copies`), harness
  grading mode, tests.
- Scope: a legal correlated field sampler driven by P4a's marginals plus
  Captain-conditional pairing, the shared FLEX-position mix, team-split and
  QB-count distributions, and salary-left distribution, each validated against
  the observed field histograms from the harness (Captain shares, splits, QB
  counts, salary left, duplication) rather than assumed; exact-lineup
  multiplicity estimated by sampling at the contest's field size;
  `predicted_copies` for every selected lineup in the review with its
  uncertainty.
- Acceptance: over every contest in the inbox with our entries present,
  Spearman between `predicted_copies` and observed copies is at least 0.5, and
  the predicted duplicated share of the field's top 1% is within 15 points of
  observed on the four reference contests. If the inbox is too thin for 0.5 to be
  meaningful, the acceptance is recorded as accruing and the chunk closes as
  `DONE_PENDING_ACCRUAL` with the metric wired.
- Hand-back: `docs/session-prompts/P5-dilution-economics.md` when P3b has closed.
