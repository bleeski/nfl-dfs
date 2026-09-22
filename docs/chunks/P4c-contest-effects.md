# P4c — Contest-conditioned field effects

Brief for chunk `P4c` of the prize-tail program. Status, dependencies and hand-back are tracked in `docs/ROADMAP.md` (status board and session card); this file is the specification. Moved verbatim from `backlog.md` on 2026-09-15.

- Goal: let ownership and duplication depend on entry limit, fee and field size
  where the data say they do.
- Evidence (hypothesis only): same-game ownership differed between the large
  multi-entry field and the single-entry field by 6 to 17 points for named
  players in three games; 150-max users' Classic entries reached the top 1% at
  1.28% against 0.67% for single-entry users.
- Scope when unblocked: contest effects as shrinkage toward the slate estimate,
  graded by held-out game with P0's harness; promotion only if the conditioned
  model beats the unconditioned P4a/P4b pair on every held-out game.
- Why deferred: four games cannot separate a contest effect from the game's
  script, and the greenfield report says the same.
