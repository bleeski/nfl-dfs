# P5 — Dilution-aware first-place value and real ladders

Brief for chunk `P5` of the prize-tail program. Status, dependencies and hand-back are tracked in `docs/ROADMAP.md` (status board and session card); this file is the specification. Moved verbatim from `backlog.md` on 2026-09-15.

- Goal: the tail objective counts dollars: first place net of predicted copies,
  satellites and WTA as P(first), ordinary GPPs on the supplied ladder.
- Read first: `payouts.py` (`parse_payout_csv`, `divided_payout`), `economics.py`,
  `reference_settlement.py`, Q4.
- Files: `payouts.py`, `economics.py`, `selection.py` (objective term),
  `portfolio_policy` contracts (`contest_objective`), tests.
- Scope: per-entry contest objective from `contest_facts_csv` plus ladder;
  expected prize of a lineup at each rank threshold divided by
  `1 + predicted_copies`; the tail sleeve maximizes that quantity for
  `FIRST_PLACE_OBJECTIVE` entries; ladders missing means the entry keeps the P3b
  rank objective and the review says why.
- Acceptance: the NE@SEA ladder reproduces the $54,065.22 tie pooling; a
  synthetic contest where the chalk lineup has the highest P(first) but 200
  predicted copies prefers a lower-P(first) lineup with 3 copies when and only
  when the arithmetic says so; full suite green. `MODEL_STATUS` still
  `PRIOR_ONLY`; no EV wording anywhere in the output.
