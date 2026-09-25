# P8: Showdown game theses as sleeves

Brief for chunk `P8`. Status, dependencies and hand-back are tracked in
`docs/ROADMAP.md` (status board and the Session 23b card); this file is the
strategy. How to build it is the implementing session's call. Written
2026-09-25 from the DAL@NYG Showdown retrospective
(`docs/SHOWDOWN_RETROSPECTIVE_2026-09-13_DAL_NYG.md` §7b, §7c, §7e, §9) and the
2026-09-15 standings findings (`docs/STANDINGS_DUAL_OPTIMIZATION_FINDINGS_2026-09-15.md`
§1, §8.1 C, §8.2 G to I).

## The idea

A single-game Showdown is decided by how the game plays out. Instead of building
every entry to the same average expectation, build the portfolio as a **core**
of sound lineups plus a few small **sleeves**. Each sleeve bets on one game
script and follows it in every lineup. If the game goes a sleeve's way, that
sleeve holds the lineups the field lacks. If it doesn't, the core still carries
the portfolio.

## Why

- **Every engine portfolio so far has been one thesis.** DAL@NYG, DEN@KC,
  SF@LAR and NE@SEA were all built to one expectation with exposure caps as the
  only diversification. Our biggest single-player shares were 0.80, 0.94, 0.73
  and 1.00. DEN@KC's 18 lineups all sat in the one cell of the field (with Nix,
  without Walker) that paid 0 of 84,483.
- **Concentration is a ruin mechanism in this field.** Across 8,007 field
  portfolios of 10 or more entries, those with 85% or more on one player had
  1.4x to 12x the zero-paid rate in 4 of 4 games, and a lower chance of a top-1%
  finish than portfolios at 70 to 85%. Concentration costs both the ceiling and
  the floor.
- **A core plus a bounded sleeve looked better on both.** In the four games it
  raised P(at least one top-1%) from 0.19 to 0.28 and cut P(zero paid) from
  0.007 to 0.002. That is fitted to those games: a hypothesis to test, not a
  proven edge. Script features had 1.5x to 6.5x lift in the game where they hit
  and 0.00x to 0.25x where they missed, so a sleeve must be small enough that
  its total failure leaves the portfolio paid.
- **The first attempt collapsed, and the retro says why.** Five theses run over
  all 20 entries and merged gave Dak Prescott 20 of 20 and only five distinct
  captains. That was worse than the single-policy build. Every thesis still
  chased the same average, and a thesis written as a list of exclusions never
  touched the captain: the "Giants blowout" captained Dak.

## The theses

These are the retro's game scripts for one NFL game. Each is a bet Ben names,
with the teams he names.

| Thesis | The game script | What its lineups look like |
|---|---|---|
| Blowout (favorite) | The favorite wins big | Captain and most of the roster from the favorite, with its defense and running back; the loser appears only through garbage-time passing |
| Blowout (upset) | The underdog wins big | The mirror: the underdog's defense and backfield live |
| Shootout | Both offenses score all game | Both quarterbacks and both top receivers; no defense or kicker |
| One-sided explosion | One offense does everything | That offense stacked five deep; the other team's top receiver as the lone bring-back |
| Low-scoring grind | Defenses and field goals | Both kickers, a defense, backs and tight ends; no receiver at captain |
| Ground and clock control | Both teams run and drain the clock | Both backfields, tight ends, a kicker, at most one receiver |
| Defensive score | A defense or return touchdown decides it | That defense at captain, the opposing quarterback left out |

## Principles

1. **A thesis is a structure, not an exclusion list.** It shapes the whole
   lineup, captain first. A thesis that leaves the captain free is not a thesis.
2. **Ben chooses the thesis and its teams.** The engine never decides who is
   the favorite or how the game will go, from a spread, a total, a contest name
   or a model.
3. **The core carries the paid count and the sleeves carry the tail.** Sleeves
   stay small. The findings' test used about a quarter of the portfolio in
   sleeves; the sizes are Ben's risk choice for each slate.
4. **Sleeves must actually differ.** Each sleeve's lineups follow its own script,
   and no player may exceed a portfolio-wide share: about 0.80, the field median.
   That limit covers the whole portfolio, core and sleeves together, so the theses
   cannot all fall back onto the same chalk.
5. **A thesis is never bent to fit.** When a thesis cannot be built, its sleeve
   is dropped and named, and the core takes its entries. Loosening the script
   would ship a different bet under the old name.
6. **Every lineup is distinct** across the whole portfolio: core, sleeves and
   rows Ben already entered (R29).
7. **A thesis is a choice, not a forecast.** Nothing calls a thesis likely,
   calibrated or +EV. Whether theses pay is measured afterwards against
   standings (Session 18), with each slate's plan recorded before lock
   (Session 22).

## Not part of this

- **Darts and captain breadth** built on a ceiling statistic instead of the
  average (retro §7b and §7e; Session 25). A sleeve that also needs its own
  objective, such as the favorite quarterback at reduced weight, waits for it.
- **Ownership and leverage** (Sessions 26 and 27).
- **Which contest each sleeve's entries land in** (Session 23).
- **Classic theses.** Classic already has groups and stack rules; this comes
  after Session 11c.

## Done looks like

On the supplied NE@SEA Showdown fixture, one run builds a core plus four
sleeves (a shootout, a blowout each way and a grind):

- every sleeve's lineups visibly follow their script;
- no lineup repeats;
- no player exceeds the portfolio-wide share;
- the portfolio uses more distinct captains than a single-policy build of the
  same entries.

A thesis that cannot be built is named and its entries go to the core. The
result is still review-only and `DO_NOT_UPLOAD`.
