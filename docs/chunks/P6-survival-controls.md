# P6 — Survival controls

Brief for chunk `P6` of the prize-tail program. Status, dependencies and hand-back are tracked in `backlog.md` (Queue table and chunk index); this file is the specification. Moved verbatim from `backlog.md` on 2026-09-15.

- Goal: the review states, from the bank, how many independent shots the
  portfolio has and what it loses if its dominant thesis fails.
- Read first: report sections 5.3 to 5.5 and 7; `portfolio.py`
  (`evaluate_portfolio`, CVaR tail fraction).
- Files: `portfolio.py`, `prior_review.py`, `readable_review.py`, both policy
  contracts (`min_scenario_clusters`, `max_zero_paid_probability` as advisory),
  tests.
- Scope: cluster DESIGN scenarios by script (which team leads, pass/rush split,
  DST scoring) and report how many clusters contain at least one of our lineups
  above the paid proxy; bank-estimated P(zero paid) and P(all below median) for
  the portfolio; the frontier of those two against the sleeve's P(≥1 top-1%
  proxy) for sleeve sizes 0 to k, printed so Ben picks the size rather than the
  engine.
- Acceptance: the DEN@KC v6 portfolio replayed through the bank reports a
  single dominant cluster and a P(zero paid) far above a P2-controlled rerun of
  the same slate; frontier table renders in HTML and workbook; full suite green.
