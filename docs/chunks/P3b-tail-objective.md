# P3b — Registered tail objective and the tail sleeve

Brief for chunk `P3b` of the prize-tail program. Status, dependencies and hand-back are tracked in `backlog.md` (Queue table and chunk index); this file is the specification. Moved verbatim from `backlog.md` on 2026-09-15.

- Goal: the selector can be told to maximize the upper tail for a declared
  number of entries while the rest of the portfolio keeps the expectation
  objective.
- Read first: `selection.py:select_prior_lineups` (objective construction at
  the three `MAXIMIZE_PRIOR_POINTS…` sites), `candidate_families.py`,
  `optimizer.py`, `portfolio.py` (`portfolio_objective`, `RISK_MEASURE`), Q5 in
  the 09-10 program.
- Files: `selection.py`, `candidate_families.py`, both policy contracts
  (`objective_version`, `tail_sleeve_entries`, `tail_statistic`), enforcement
  audit, `docs/DATA_CONTRACTS.md`, tests.
- Scope:
  - Register `TAIL_QUANTILE_OF_DESIGN_BANK` with a declared quantile (default
    p90) as an `objective_version`. Candidate generation adds tail-family strata
    (5-1 tilt, DST-inclusive, single-QB single-stack, secondary-game stack for
    Classic) so the bank contains tail candidates before the objective ranks
    them; bank completeness reporting unchanged.
  - `tail_sleeve_entries = k`: the joint assignment selects k lineups under the
    tail objective and the rest under the expectation objective, all under the
    same P2 controls and `max_person_share`; the review names which entries are
    sleeve entries and which contests they landed in (`tail_proxy_desc` assignment
    puts them on `FIRST_PLACE_OBJECTIVE` rows first).
  - REFEREE bank re-scores the final assignment; any disagreement with the SELECT
    ranking beyond the registered tolerance is a named blocker.
  - Champion/challenger: every run that uses a sleeve also builds the
    expectation-only portfolio from the same bank under the same controls, writes
    it to the run folder as `control_assignment.json` with its own manifest
    entry, and never exports it. P0's harness grades both against the standings,
    so the sleeve's effect is measured on every slate rather than argued.
  - Classic tail families include QB+2 and QB+3 same-team stacks and the RB
    bring-back as explicit strata, so the greenfield report's stacking
    experiment can be run as a sleeve configuration rather than as a rule.
- Non-goals: no EV, no ownership term yet (P5), no claim that p90 is calibrated;
  `MODEL_STATUS` stays `PRIOR_ONLY`.
- Acceptance: synthetic contest with a known tail optimum is recovered; on the
  DEN@KC snapshot with P1's evidence supplied, a k=6 sleeve contains at least one
  lineup with a DST and at least one 5-1 on each side (mechanism check, not a
  hindsight claim); replay byte-identical; full suite green.
- Hand-back: `docs/session-prompts/P6-survival-controls.md` and, when P4b has
  closed, `P5-dilution-economics.md`.
