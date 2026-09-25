# P8: Showdown game theses (R33, R34)

Brief for chunk `P8`. Status, dependencies and hand-back are tracked in
`docs/ROADMAP.md` (status board and the Session 23b card); this file is the
strategy. How to build it is the implementing session's call. Written
2026-09-25 from Ben's rulings R33 and R34 (`docs/ROADMAP.md` §2.5, the ATL@GB
Showdown of 2026-09-24), the DAL@NYG Showdown retrospective
(`docs/SHOWDOWN_RETROSPECTIVE_2026-09-13_DAL_NYG.md` §7c, §9) and the
2026-09-15 standings findings
(`docs/STANDINGS_DUAL_OPTIMIZATION_FINDINGS_2026-09-15.md` §1, §8.1 C, §8.2 G).

## The idea

Build every Showdown lineup around one named game thesis: a script for how the
game plays out in which all six players hit together. Spread the portfolio's
rows across theses, and above all spread its captains. Ben's two goals set the
test (R34): win large prizes and minimize washouts. Both come from leverage and
diversification.

## Ben's rulings

- **R33.** "Ideally, each lineup should adhere to a specific game thesis. this
  isn't an exhaustive list but here are some examples: GB win big, ATL win big,
  GB win close, ATL win close, defensive battle, offensive shootout. You can
  have sub variants of each of those for example, high scoring or low scoring,
  etc.."
  The purpose is captain diversification: "on a Green Bay win with a low
  scoring game it might make sense to captain their kicker or DST." Backup
  quarterbacks are out by default, since they generally need an injury. Kickers
  and DSTs are never excluded, Captain included.
- **R34.** Ben's two goals: "winning large prizes, and minimizing washouts.
  Both require identifying leverage and diversification, and this is a way
  within showdown contests to do that."

## Why

- **A legal portfolio can fail both goals.** The first ATL@GB file passed every
  gate and QA with 0 defects. Ben rejected it: five captains at 25% each, and
  four people in 13 of 20 lineups. The replacement spread captains using caps,
  not theses.
- **Theses built by hand broke in three ways.**
  - At ATL@GB, six sleeves run as one policy each and assembled by row failed
    QA three times with lineups repeated across sleeves.
  - A sleeve whose captains had to be a kicker, a DST or a backup back lost its
    thesis when relaxation let the excluded captains back in.
  - Nothing can force a kicker or DST captain, because the mean prior never
    chooses one.
- **Theses that chase one average collapse.** At DAL@NYG, five theses run over
  all 20 rows and merged gave Dak Prescott 20 of 20 and five captains. A thesis
  written as exclusions never touched the captain: the Giants-blowout thesis
  captained Dak.
- **Concentration is a ruin mechanism in this field.** Across 8,007 field
  portfolios of 10 or more entries, those with 85% or more on one player had
  1.4x to 12x the zero-paid rate in 4 of 4 games. They also had a lower chance
  of a top-1% finish than portfolios at 70 to 85%. Script features had 1.5x to
  6.5x lift in the game where they hit and 0.00x to 0.25x where they missed:
  each thesis is a real bet that loses when its game doesn't happen.

## The theses

Ben's list, with the sub-variants he allowed. Each is a bet he names, on the
teams he names.

| Thesis | The game script | What its lineups look like | Captains it opens |
|---|---|---|---|
| Team wins big | One side runs away with it | The winner's offense and defense; the loser only through garbage-time passing | The winner's QB, RB, WR or DST |
| Team wins close, high scoring | Both offenses score; one edges it | The winner holds the majority; both quarterbacks or top receivers live | Either QB, the winner's receivers |
| Team wins close, low scoring | Few touchdowns; field goals and defense decide it | The winner's kicker, defense and backs; few receivers | The winner's kicker or DST (Ben's example) |
| Defensive battle | Neither offense moves the ball | Both kickers, a defense, backs and tight ends | A kicker or a DST; no receiver |
| Offensive shootout | Both offenses score all game | Both quarterbacks and both top receivers; no defense or kicker | The QBs and the top receivers |

The DAL@NYG retro's other scripts fit as sub-variants of these: one offense
does everything, ground and clock control, or a defensive or return score.

## Principles

1. **Every lineup carries one named thesis, reported per Entry ID.** No row is
   filler. The theses Ben rates likelier get more rows. They are never an
   unconstrained fill: at ATL@GB, a row filled outside the policy broke its
   overlap cap.
2. **A thesis is a structure, not an exclusion list.** It shapes the whole
   lineup, captain first. It may require its captain from a named set, kicker
   and DST included.
3. **Ben chooses each thesis and its teams.** The engine never infers a
   favorite or a script from a spread, a total, a contest name or a model. A
   thesis never moves a projection by a typed multiplier.
4. **Captains carry Showdown leverage.** Spread them across theses. The same
   core with a rotating captain is one bet placed many times.
5. **No shared failure point.** One portfolio-wide limit on any player's
   share, across every thesis: about 0.80 by the field median, or tighter if
   Ben chooses. Every person in more than half the rows is named.
6. **A thesis is never bent to fit.** A cap may loosen under the lock clock;
   the thesis's structure may not. A thesis that cannot be built is dropped and
   named, and its rows go to the other theses. Relaxing it into chalk ships a
   different bet under the old name, as ATL@GB showed.
7. **Every lineup is distinct** across the whole portfolio: across theses and
   against rows Ben already entered (R29).
8. **The pool follows R33.** Backup quarterbacks are out by default, from
   depth-chart evidence. Kickers and DSTs stay in, as captains too.
9. **A thesis is a choice, not a forecast.** Nothing calls a thesis likely,
   calibrated or +EV. With no ownership input, say that leverage is unmeasured.

## How a build is judged (R34)

Each build reports, before handoff:

- **Captains:** each captain's count and the thesis it serves.
- **Washouts:** every person in more than half the rows, and the most rows any
  one player's bad night would sink.
- **Thesis adherence:** each lineup's thesis, and whether it follows it.

Whether theses pay is measured afterwards against standings (Session 18),
with each slate's theses recorded before lock (Session 22). Script-conditioned
scenarios and thesis coverage are Sessions 24 and 28.

## Not part of this

- **Ceiling objectives, darts and ceiling-ranked captains** (Session 25). So is
  a thesis that needs an objective weight rather than a structure, such as a
  quarterback at reduced weight.
- **Measuring leverage** (Sessions 26 and 27).
- **Which contest each thesis's rows land in** (Session 23).
- **Classic theses.** Classic already has groups and stacks; this comes after
  Session 11c.

## Done looks like

The same 20-row Showdown, whether the supplied NE@SEA fixture or an ATL@GB
replay, is spread across Ben's theses: each team wins big, each team wins close
(high and low scoring), a defensive battle and a shootout. In that build:

- every lineup follows its thesis and names it;
- kicker and DST captains appear where a thesis calls for them;
- no lineup repeats, and no player exceeds the share limit;
- captains spread well beyond the first ATL@GB file's five at 25%;
- a thesis that cannot be built is named, never quietly relaxed.

The result is still review-only and `DO_NOT_UPLOAD`.
