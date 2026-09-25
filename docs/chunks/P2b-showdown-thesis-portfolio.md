# P2b: Showdown thesis portfolio

Brief for Session 23b. Status, dependencies and hand-back live in
`docs/ROADMAP.md`; this file is the specification. It sets the strategy only.
The implementing session designs the mechanics on the Showdown policy contract
and Session 23's primitives. Written 2026-09-24 from R33, R34 and the ATL@GB
Showdown slate.

## Goal

Ben's two goals (R34): win large prizes and minimize washouts. Both come from
leverage and diversification. In Showdown, the way to get both is to build
every lineup for a specific game script and spread the portfolio across
scripts.

## What it fixes

The ATL@GB slate (2026-09-24, 20 entries) showed that a legal, QA-clean
portfolio can fail both goals:

- The first file had five captains at 25% each and four people in 13 of 20
  lineups.
- Capping each captain at 10% gave 11 captains, but the same four-player FLEX
  core sat in 14 to 15 of 20 lineups: one bet placed 20 times with a rotating
  captain.
- No kicker or DST ever captained. The optimizer maximizes total mean prior
  points, and one mean per person pulls every lineup back to the same core
  whatever the constraint.
- Six thesis sleeves assembled by hand collapsed onto that core and repeated
  lineups across sleeves.

## The discipline

1. **Script first, players second.** Every lineup is built for one named
   thesis: an outcome of the game under which all six players score together.
   The starting menu, not exhaustive, for teams A and B:
   - A wins big; B wins big;
   - A wins close; B wins close;
   - shootout, both offenses;
   - defensive battle, low total.

   Each has variants: a high or low total, and which unit carries it (passing,
   rushing, or defense and special teams).
2. **The thesis sets the roster's shape.**
   - Captain: the player whose big night the script depends on most. Every
     thesis has its own captain list: the winner's RB or defense in a
     blowout, a QB or top pass catcher in a shootout, a kicker or DST in a
     low-scoring win.
   - Team balance: a blowout leans to the winner and keeps only the loser's
     catch-up passing; a close game carries both offenses and both kickers.
   - Pieces that score together: a QB with his pass catchers, a defense with
     the opposing offense left out, a kicker with a low-scoring win.
   - Players the script contradicts stay out: the losing team's RB in a
     blowout, a DST in a shootout.
3. **Cover the scripts.** Every entry carries one thesis, and the portfolio
   covers every plausible script, weighted by how plausible each is. Coverage
   is the washout control: whatever the game does, some lineups were built for
   it.
4. **Captains diversify through theses.** Each thesis brings its own captains,
   so captain spread follows from the theses. A per-captain cap stays as a
   backstop, not the mechanism.
5. **Leverage inside each thesis.** Within a script, prefer the path the field
   underweights: a kicker or DST captain in a low-scoring win, the second pass
   catcher in a shootout. That needs an ownership input (Session 26). Until one
   exists the review says leverage is unmeasured and never calls a cheap
   player leverage.
6. **No shared failure point.** A person's exposure follows the share of
   scripts in which he scores, not his mean. A FLEX core in most lineups is the
   washout the portfolio exists to avoid.
7. **Standing pool rules (R33).** Backup quarterbacks are out by default: they
   need an injury to matter. DSTs and kickers are never excluded by default,
   Captain included.
8. **Distinct across the whole portfolio.** R29 holds across theses, not only
   within one.
9. **Contests.** Which thesis goes to which contest follows the contest's
   supplied payout structure (Session 29). A contest name never implies payout
   tiers or field size; without payout data, theses spread evenly across
   contests.

## What the review shows

For each Entry ID: its thesis, its captain, and a one-line reason. For the
portfolio:

- rows per thesis, and every plausible script with none;
- each captain's count;
- every person in more than half the rows, named as a shared failure point;
- leverage: measured, or "unmeasured";
- every thesis relaxed under the lock clock and what it lost. A thesis that
  loses its captain list is reported as lost, never kept under its label.

## Acceptance

On a real Showdown salary file with at least 20 entries:

- every row carries a thesis, and the portfolio uses at least four;
- lineups under different theses differ in captain, team balance and
  correlated pieces, not in captain alone;
- a low-scoring thesis can produce a kicker or DST captain;
- no lineup repeats (R29);
- no person sits in more than half the rows unless the review names the
  scripts that justify it;
- the review carries the read above.

## Boundaries

- A thesis never moves a projection by a typed multiplier (R33). Until a
  registered scenario model conditions projections on a game script (Session
  24's bank), a thesis acts only through the roster's shape: captain list,
  team balance, required pieces and exclusions. Script-conditioned
  projections are a later stage with their own row.
- Thesis rules are construction preferences: relaxable under the lock clock
  and reported per thesis. Distinct lineups and every evidence gate are not.
- Every output stays `PRIOR_ONLY / DO_NOT_UPLOAD`. A thesis is a construction
  choice, never reported as EV or a probability.

## Depends on

- Session 23: per-lineup structural bounds, the captain team, per-team bounds
  and several rule sets in one policy.
- Session 24: the scenario bank, for the script-conditioned stage.
- Session 26: ownership, for leverage.
- Session 28: P(zero paid), the washout measure.
