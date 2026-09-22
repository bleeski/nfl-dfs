# Classic C4 retrospective, 2026-09-13 Week 1 main slate

> **Appendices A and B superseded 2026-09-22.** Every backlog item there was absorbed into a session
> of `docs/ROADMAP.md` or retired; §3 of that file maps each item. The retrospective itself stays as evidence.

First live Classic slate. This was the C4 operator rehearsal the plan said would
be a rehearsal, and it behaved like one. Twenty legal lineups were uploaded with
nine minutes to spare. Almost none of the value came from where the design
assumed it would.

Window: 10:46 ET start, 13:00 ET lock, 134 minutes.
First portfolio delivered 12:23 (97 minutes in). Final upload file 12:51.
22 engine runs. 6 engine source files modified, none committed.

---

## 1. Where the time actually went

| Phase | Wall clock | Produced |
|---|---|---|
| Stage repo, environment, test suite | ~24 min | working runtime |
| Weather evidence (12 games) | ~5 min | complete, passed first time |
| Engine gate cascade (5 blockers, serial) | ~41 min | one working chain at 11:32 |
| **C2 candidate-bank solver, 6 attempts** | **~43 min** | **nothing** |
| Score extraction + external construction | ~10 min | the actual portfolio |
| Adversarial QA + two rebuilds + darts | ~28 min | every quality gain |

The two numbers that matter: **43 minutes produced nothing**, and **10 minutes
produced the portfolio**.

### The C2 solver is not usable on this host for a full Classic pool
Six attempts, every one failed:

| Run | Config | Result |
|---|---|---|
| c2r0 11:35 | rung 0, bank 642 | `CANDIDATE_BANK_TIMEOUT` 82/642 |
| c2final 11:42 | rung 0, bank 90 | `INCOMPLETE_BANK_EXHAUSTION` kInfeasible |
| c2rung1 11:49 | rung 1, bank 110 | `CANDIDATE_BANK_TIMEOUT` 99/110 |
| FINAL 11:57 | rung 2, bank 80 | `CANDIDATE_BANK_TIMEOUT` 78/80 |
| STACKED 12:05 | rung 2, bank 50 | `CANDIDATE_BANK_TIMEOUT` 50/50, wall clock |
| GO 12:13 | rung 2, bank 40 | `INCOMPLETE_BANK_EXHAUSTION` kInfeasible |

Measured cost is roughly **4 to 6 seconds per candidate** on a 2-core container
against a 746-person pool. The ladder in `make_classic_policy.py` relaxes
*structure* when the binding constraint is *time*, so walking down it does not
help: rung 0 and rung 2 both timed out at the same rate. Note the squeeze at
bank 50 and bank 40: 50 candidates exhausts the wall clock, 40 candidates is
infeasible for the assignment. There is no bank size that both builds in time
and satisfies 20 entries under exposure and overlap caps.

The rung ladder's premise is sound and should stay. Its failure mode detection is
wrong: it treats `CANDIDATE_BANK_TIMEOUT` as a structure problem when it is a
throughput problem.

### The probe loop was a reasoning failure, not a tooling one
Eight runs in 90 seconds (`probe1`-`probe8`), all returning the identical
`PLAYER_EVIDENCE_NOT_PASS:00-0035228`. I wrote a loop to iteratively discover
blocked players via `--exclude` without first checking that `--exclude` acts at
selection, not at projection. Cheap in wall clock, but it is the shape of error
worth naming: I automated a premise I had not verified.

---

## 2. What worked and should not be touched

**Weather capture.** `api.weather.gov` is blocked from the container; the browser
pane runs same-origin `fetch`, so one `javascript_tool` call pulled all 12
gridpoint forecasts, and a gzip+base64 round trip moved 99 KB back as 9 KB. Five
minutes, passed the gate on the first attempt. Keep exactly as is.

**Parallel research agents.** Two agents, launched simultaneously, both returned
source-cited work with honest gaps marked as gaps. The inactives agent caught a
site publishing a **fabricated** inactives list naming Tee Higgins as out, which
appeared in no legitimate source and would have been slate-defining. It also
caught two prior-season articles surfacing as current. That single catch justifies
the whole pattern.

**The adversarial QA agent.** Highest value per minute in the session by a wide
margin. It found, in eight minutes, three things my own QA script could not see
because my script tested what I had thought to test:
- Achane ∪ Flowers ∪ Bijan covered **17 of 20 lineups**, concentrated on the two
  lowest-implied-total offenses on the slate.
- **Four lineups** paired a DST against skill players in its own game, including
  a QB stacked with his own TE opposite that game's DST.
- Only **9 of 20** lineups carried a bring-back.

None of that was illegal. That is the entire point.

**Deterministic legality checking.** Zero failures on every version shipped, and
the byte-diff against the entry template (nothing outside the nine authorized
roster cells) held every time. Keep.

**Clock-first discipline.** Reading the earliest kickoff out of `Game Info` before
anything else was correct and should stay the first action.

---

## 3. What did not work

**Serial gate discovery.** Five blockers surfaced one at a time, each costing a
full investigate-patch-rerun cycle: `DraftKingsParseError`, identity gate,
`PLAYER_EVIDENCE_NOT_PASS`, `ZERO_OR_MISSING_SHARE_GROUP`, opportunity coverage.
Four of the five were the *same underlying assumption* (the pool is complete and
every person resolves) expressed in four different modules. A preflight that
re-derives all of them against the actual inputs before the first run would have
collapsed ~41 minutes into one report.

**Blind salary maximization.** I ran two "spend to the cap" passes, 45 upgrades
then 19 more, optimizing prior points per marginal dollar with no ownership or
correlation term. The first pass dropped bring-backs from 12/20 to 8/20; the
repair pass then cost real projected points (-6.1, -4.3, -3.2 on individual
swaps) buying that correlation back. Net negative, and self-inflicted. DraftKings
prices on projected output and so does the field's optimizer, so salary
exhaustion is a chalk-generating mechanism. Ben's framing is the correct one:
leaving salary on the table is fine when it buys leverage, and the discipline is
that it must be *intentional*, meaning the saved dollars buy another piece of a
correlated block rather than sitting unused.

**My own clock arithmetic.** I drifted roughly 45 minutes at one point and told
Ben the wrong time-to-lock. Every time-to-lock statement should come from a
`date` call in the same turn, never from mental arithmetic.

**Test-suite noise.** 18 failures traced to `AS_OF = "2026-09-13T14:00:00+00:00"`
in `tests/test_priors_adapter.py`, a hardcoded wall-clock constant that today's
date passed at 10:00am ET. The engine behavior under test is correct; the test's
fixed clock is stale. It cost ~5 minutes to prove that on slate day.

---

## 4. The ugly

**Six engine files modified under a lock clock, uncommitted, full suite never
re-run after the changes.** `dk.py`, `priors.py`, `projection.py`,
`opportunity.py`, `selection.py`, plus a regression test. One is an unambiguous
bug fix. Four are the identity/pool-completeness alignment Ben authorized in the
moment. One is a debug hook. This is real risk carried into the next slate and it
needs a deliberate accept-or-revert pass with the suite green, not a quiet carry
forward.

**The engine contributed one artifact to the final portfolio.** Per-player
`prior_points_of_expected_statline_v3` scores, extracted through a debug hook I
added at 12:21. Every property that made the portfolio good, stacking,
bring-backs, exposure caps, anti-correlation, leverage, darts, was built outside
the engine in about ten minutes. That is worth sitting with before investing more
in C2.

**I shipped v1 confidently and it had an 85% concentration defect.** My QA passed
it. I described it as strong. It took an adversarial agent to find the problem.
The lesson is not "my script was buggy", it is that a checker written by the
person who built the thing inherits that person's blind spots.

---

## 5. Formalization: the QA gate

Added `scripts/qa_classic_portfolio.py`. Two tiers.

**Tier 1, legality, blocking.** Nine players, slot eligibility, salary cap,
two-game rule, no duplicates, no inactive rostered, exactly one QB and one DST,
no QB beside his own backup. Exit code 1 on any failure. This is what already
worked and is unchanged in substance.

**Tier 2, portfolio coherence, scored and must be shown at handoff.** Does not
block, but a run may not be handed off without printing it:

- **Concentration**: max single-player exposure, **top-3 union coverage**,
  distinct players, max and mean pairwise overlap. Top-3 union is the metric that
  would have caught v1 (85%, meaning a 4-lineup portfolio wearing a 20-lineup
  costume).
- **Anti-correlation**, all must be zero: DST against skill players in its own
  game, DST against its own lineup's QB, QB against the opposing DST.
- **Stack integrity**: QB + own pass catcher rate, bring-back rate.
- **Game environment**: mean implied team total per lineup, weakest lineups named.
- **Leverage**: summed projected ownership per lineup, chalkiest and leanest named.

Suggested thresholds to argue about rather than adopt silently: max exposure
<= 40%, top-3 union <= 75%, anti-correlation == 0, stacked == 100%,
bring-back >= 70%.

**Process change that matters more than the script:** the adversarial agent runs
**once, early, in parallel**, immediately after the first legal portfolio exists,
not as a final polish. It needs only the portfolio, implied totals, ownership,
the out-list, and the stated model limitations. Everything but the portfolio is
available before the build starts.

---

## 6. Formalization: darts

A **dart** is a lineup built to win first place outright, not to cash. In an
832,000-entry field paying 173,275 places with $1M to first, the core portfolio
is competing for a few hundred dollars and the darts are the only entries with a
realistic path to the top prize. Treat them as a separate product with their own
rules.

**Qualifying conditions, all must hold:**
1. **Correlated block**: at least 4 players from one game, structured as
   QB + >= 2 same-team pass catchers or skill + >= 1 from the opposing side.
   Five or more from one game is better.
2. **Environment**: that game's total is top-4 on the slate, or >= slate median
   + 2.0 points. This is the condition that separates a dart from a bad lineup.
   Cheap and low-owned in a 40-point game is not leverage, it is just bad.
3. **Ownership**: at least two players in the block under 10% projected
   ownership, and the block's summed ownership materially below the portfolio
   mean.
4. **Salary**: punting to the cap is permitted and expected, but the saved money
   must buy another block piece. Unspent salary that buys nothing is waste, not
   leverage.

**Allocation**: 20-25% of entries. Five of twenty on 2026-09-13.

**Build order, and this is the real change**: build darts **first**, then fill the
core around them with exposure caps that already account for what the darts
consumed. On this slate I built darts last by replacing the weakest lineups,
which meant the core build had already spent the exposure budget and the dart
fills had to take leftovers. Reversing the order is free and strictly better.

**What the five darts were**, for the record: TB@CIN 50.5 (Mayfield 2% owned,
Irving 1.5%, seven of nine in the game), ARI@LAC (LAC 28.50, the slate's highest
implied total), the New Orleans side of NO@DET 49.5 (field was stacking Detroit),
BAL@IND 47.5 (Lamar 5.5% owned, closing a gap where the portfolio held 24 skill
slots in that game and no QB), and CHI@CAR 47.5 (Coker ~3%). The QA scorecard
confirmed the design: the darts are the three leanest lineups in the book at
34-42 summed ownership points against a portfolio mean of 69.6.

---

> Backlog items from this section are consolidated in **Appendix A: prioritized backlog** at the end of this document.

## 8. Keep exactly as is

Weather capture path. Parallel research agents with source citation and explicit
gap marking. Deterministic legality checking and the byte-diff against the entry
template. Clock-first discipline. The rung ladder's premise, that a portfolio
that never gets built is the worst outcome. The prior-only honesty discipline:
nothing in this slate's handoff claimed EV, ceiling, or edge, and the blind spots
were named rather than smoothed over.

---

# Addendum: late-swap phase and realized ownership

Written 15:30 ET, after the 1:00pm games completed and before the 4:25pm lock.
Source: the DraftKings contest-standings export for contest 193028206 (826,515
rows, realized `%Drafted` and live FPTS for 439 players) plus the re-exported
entries file showing per-slot lock state.

## 9. Published ownership projections compress toward the mean

Projected against realized, for the 19 players where I had both. Realized numbers
are from the contest itself, not another projection.

| Player | Projected | Actual | Error |
|---|---|---|---|
| Jahmyr Gibbs | 47.2% | 38.58% | **-8.62** |
| Ja'Marr Chase | 32.4% | 28.28% | -4.12 |
| Chris Olave | 26.2% | 23.65% | -2.55 |
| **Bijan Robinson** | 24.2% | **12.88%** | **-11.32** |
| Amon-Ra St. Brown | 21.2% | 16.60% | -4.60 |
| Derrick Henry | 13.0% | 8.03% | -4.97 |
| Tyler Warren | 9.4% | 4.26% | -5.14 |
| **Bucky Irving** | 1.5% | **10.82%** | **+9.32** |
| Baker Mayfield | 2.0% | 6.24% | +4.24 |
| Jalen Coker | 3.0% | 6.59% | +3.59 |

**The pattern is systematic, not noise:**
- Players projected **>= 20%**: n=5, mean error **-6.24 points**. The chalk was
  consistently *less* chalky than advertised.
- Players projected **< 10%**: n=11, mean error **+0.99 points**. The
  contrarian plays were *more* owned than advertised.

Two consequences, both of which cut against how I reasoned on this slate:

1. **Leverage from fading chalk is smaller than the projections imply.** Fading
   Gibbs bought less uniqueness than a 47% number suggested, because the real
   number was 38.6%.
2. **Dart uniqueness is smaller than the projections imply.** The TB@CIN dart was
   sold on "Mayfield 2%, Irving 1.5%". Realized: **6.24% and 10.82%**, three to
   seven times the projection. The lineup was still contrarian, but I overstated
   how contrarian when I described it.

**Action:** treat published ownership as *ranks*, not levels. If levels are needed,
shrink toward the mean before using them: scale projections above 20% down by
roughly a quarter and floor sub-5% projections at around 5%. Re-measure this
every slate; one sample sets a direction, not a coefficient.

## 10. When a published number contradicts structure, trust the structure

The one place my two sources openly disagreed was Bijan Robinson. Stokastic
published 23-24%; FantasyPros argued qualitatively that he would be *low* owned
because Tua was out, Cooper Rush was starting, and Atlanta's implied total was
17.25, second-worst on the slate. I noted the conflict, flagged it to Ben, and
then used the number.

**Realized: 12.88%.** The qualitative read was right and the published figure was
off by 11 points, the largest single error in the table. The field correctly
faded a good running back in a dead offense, exactly as the structural argument
predicted.

Rule to carry forward: when a published ownership figure conflicts with a clear
structural reason (a backup quarterback, a bottom-three implied total, a role
change), weight the structure. The projection was likely built before the news or
on a stale prior.

## 11. Unspent salary is late-swap option value

This is the mechanical argument for Ben's point that neither of us made at the
time, and it is stronger than the leverage argument.

The portfolio shipped at a **$49,900 mean salary**. At the late-swap window the
remaining room per entry was **$0 to $800, across all twenty entries**. That made
every available swap lateral or downward in price. De'Von Achane ($7,000) to
Omarion Hampton ($6,800) was possible; any upgrade *into* a higher-priced player
in a better spot was impossible everywhere.

Spending to the cap does not merely correlate with chalk. It **forecloses the
late-swap option** before the news that would justify using it has broken.

**Action:** lineups carrying meaningful late-window exposure should deliberately
hold roughly **$300-600** unspent. That is not waste, it is the premium on an
option that expires at the late lock, and on this slate the option would have
been worth having. Lineups that are fully locked by the early window can spend to
the cap, because they have no option to preserve.

## 12. Mid-contest rank is a completion artifact, not a leaderboard

At 15:15 ET our twenty entries ranged from **$49,900 of locked salary** (fully
scored) down to **$16,300 locked with $33,500 still to play**. Comparing their
ranks directly is close to meaningless: a lineup shows a high score partly
because its players have already played.

The metric that actually compares like with like mid-contest is **points per
$1,000 of locked salary**:

| | n | pts / $1k locked | unscored salary |
|---|---|---|---|
| Core lineups | 15 | **2.16** | $6,847 |
| Darts | 5 | **1.74** | $13,100 |

This also produced a structural consequence I did not anticipate:
**late-swap flexibility is inversely correlated with mid-contest rank.** Our five
best entries had **0 to 1** unlocked slots; our worst had **six**. That is
mechanical, not unlucky. Entries that look good at the early lock look good
*because* they are early-game-heavy, which is exactly why they have nothing left
to change.

**Action, and this belongs at build time rather than swap time:** decide up front
which entries are meant to carry swap optionality, and give those entries both
late-window exposure and the salary room from section 11. Deciding at 3:15pm
which lineups you wish were flexible is too late; the answer is already fixed.

## 13. Darts underperformed on this slate, and that is close to uninformative

On scored salary the darts returned **1.74** against the core's **2.16**, about
19% worse. Recorded for honesty, and it should not drive a change.

Judging a deliberately high-variance allocation by its mean outcome in a single
sample is the wrong test. The darts exist to buy a thin chance at a $1M outcome,
and the correct evaluation is the shape of the tail across many slates, not the
average of five lineups on one. **Track dart performance as a running series over
the season** — hit rate on top-1% finishes, not slate-by-slate mean. If after
fifteen or twenty slates the darts have produced no top-1% finishes, that is the
signal worth acting on.

One genuine diagnostic did fail, and it is the ownership premise rather than the
structure: the TB@CIN block was chosen because nobody was on it, and 10.82%
ownership on Bucky Irving says the field partly was. Section 9's shrink factor
addresses that directly.

## 14. Operational note: recovering a truncated standings export

The uploaded contest-standings zip had a valid local file header and **no
end-of-central-directory record**, so `unzip` and Python's `zipfile` both refused
it. Reading the local header manually and streaming the member through
`zlib.decompressobj(-15)` recovered **153,056,335 of 153,885,051 bytes**, about
99.5%, which was every row that mattered.

Two limitations worth knowing before relying on this file at swap time:
- The `%Drafted` and FPTS block only covers players whose games have **completed**.
  Late-window ownership is not available while the late-swap decision is being
  made, which is precisely when it would be most useful.
- Realized ownership is contest-specific. These figures are the Millionaire's, not
  the slate's.

> Backlog items from this section are consolidated in **Appendix A: prioritized backlog** at the end of this document.

---

# Addendum 2: what if the priors are wrong

Ben's question, 2026-09-13. It is a sharper version of the concentration defect
the adversarial agent found, and I think it is the more important one.

## 16. The portfolio diversifies in player space, not in belief space

The adversarial pass found correlated ruin among *players*: three players covered
17 of 20 lineups. We fixed that. But every input to the build came from the same
place:

| Input | Whose view it is |
|---|---|
| Implied team totals | the betting market's |
| Projected ownership | the DFS industry's consensus |
| Player projections | prior-season usage, i.e. the past's |
| Salary | DraftKings' model |

So the finished portfolio is **twenty draws from one model of the world.** Player
exposure is diversified; *worldview* exposure is 100%. If the consensus is right,
the chalk beats us because chalk is chalk for a reason. If the consensus is
wrong, we are not positioned for the specific way it is wrong, because we
inherited its priors when we built the alternatives.

**Worse, the dart specification in section 6 codified the consensus.** Condition 2
requires the dart's game to be a top-4 total on the slate. That rule guarantees
every dart *agrees with Vegas about where the points will be*. A lineup that is
low-owned but consensus-aligned on environment is not a dart. It is chalk that
nobody happened to click.

## 17. The payoff asymmetry runs the other way

This is the technical argument, and it inverts section 6's condition 2.

If a 50.5-total game goes twenty points over, a large share of 832,000 entries
hold those players, because the market told everyone to be there. If a
**38.5-total game** goes twenty points over, almost nobody does. The *same
magnitude of forecast error* pays far more where the market said it would not
happen.

On this slate the four lowest totals were NYJ@TEN 38.5, CLE@JAX 40.0, MIA@LV 40.5
and ATL@PIT 41.0. We required darts to avoid exactly those games. For an entry
whose only objective is first place out of 832,000, a low-total game that goes
nuclear is the single highest-leverage outcome available, and we ruled it out by
construction.

The correct framing is not "avoid low totals." It is that **a dart should be
short a prior, and which prior it is short should be an explicit choice.**

## 18. Week 1 is when the priors are weakest

The engine excluded **188 selectable players** for having no prior-season row,
including Jeremiyah Love ($6,400), Carnell Tate ($5,300), Makai Lemon ($5,100),
Fernando Mendoza ($5,000) and Jonathon Brooks ($5,000). I reported that as a
limitation to apologize for.

In Week 1 it is closer to a feature list. "No 2025 usage" means the model cannot
price them, which means the *field's* models mostly cannot either, which is
exactly where unpriced upside lives. A prior-only engine is structurally
incapable of rostering a rookie in the week when rookies carry their highest
variance of the season.

This is a seasonal gradient, not a constant. Week 1 has no current-season
information and maximal role churn, so prior fragility is at its peak. By Week 8
the priors are carrying real 2026 data and this argument weakens considerably.
**Allocate the prior-breaking darts heaviest in Weeks 1-3 and taper.**

## 19. A dart taxonomy: diversify by which prior fails

Five darts that all assume "the market is right about where points will be" die
together on the one axis that matters. Replace the game-based split with a
belief-based one. One dart per failure mode:

| # | Short this prior | Concrete expression |
|---|---|---|
| 1 | **Vegas totals are right** | Full game stack in a **bottom-4 total** game. Pays most precisely because nobody is there. |
| 2 | **Prior-season usage predicts current roles** | Roster the players the model cannot see at all: rookies, new starters, the 188-name exclusion list. |
| 3 | **DK salary reflects expected output** | Salary lag. Prices locked July 31 against September roles. This is the one we actually ran. |
| 4 | **Published ownership is accurate** | Section 9 proved it is biased. Also avoid *second-order chalk*: the low-owned players every leverage article names are themselves owned. Chase Brown was the published leverage play at 8.8% projected and came in at 9.78%. |
| 5 | **Game shape follows game total** | Blowout scripts: a favorite covering by thirty makes its DST and its lead back hit together, a pairing almost nobody builds. Or garbage-time volume for the losing side's pass catchers. |

## 20. The limit of this idea

Contrarianism is not edge on its own. Being deliberately wrong-footed only pays
where the consensus is genuinely fragile, and most of the time it is not. A
portfolio built to be short every prior at once is just a bad portfolio with a
story attached.

The discipline is: **the core stays consensus-aligned, and the darts are each
short exactly one named prior.** Twenty-five percent of entries, five darts, five
different failure modes. If the consensus holds, the core cashes and the darts
lose their small allocation, which is the expected outcome. If one prior breaks,
one dart is positioned for precisely that break rather than all five being
positioned for none of them.

## 21. Applied today, in the late-swap window

I acted on this rather than only writing it down. Of the three dead entries with
swappable slots, I had proposed the same consensus bet in all three: De'Von
Achane to Omarion Hampton, on the reasoning that LAC carried the slate's highest
implied total. That is three copies of "the market is right."

Changed entry **5248989803** to **Jeremiyah Love** instead: a rookie making his
debut, confirmed active by the Cardinals, headlining their backfield, on a team
implied for 19.00 as a 9.5-point underdog, whose ownership is suppressed because
he carried a questionable tag all week, **and whom our engine scored at zero
because he has no 2025 history.** Negative game script gives a rookie back
receptions. If the priors are wrong, that is a shape they are wrong in.

The entry now sits at **$48,600**, $1,400 under the cap, which is the section 11
reserve policy applied deliberately rather than as an accident.

Two of three remain on Hampton. That is the point: not all short, not all long.

> Backlog items from this section are consolidated in **Appendix A: prioritized backlog** at the end of this document.

---

# Addendum 3: what the realized data says about leverage

Measured from the contest's own `%Drafted` and FPTS for the 439 players whose
games completed. The 4:25pm games are excluded because they had not scored. One
slate, early window only, 11 total ceiling games: the directions below are clear,
the exact thresholds are not established by a single sample.

## 23. Our leverage worked, and not for the reason I would have guessed

Net leverage P&L, defined as the sum over players of
`(our exposure - field ownership) x FPTS`, i.e. how much our average lineup beat
a field-weighted lineup on scored players:

**+30.90 DK points per lineup.**

Where it came from:

| Player | Ours | Field | FPTS | P&L |
|---|---|---|---|---|
| Zay Flowers | 35% | 10.41% | 29.0 | **+7.13** |
| Derrick Henry | 35% | 8.03% | 21.2 | **+5.72** |
| Bijan Robinson | 30% | 12.88% | 23.5 | **+4.02** |
| Amon-Ra St. Brown | 35% | 16.60% | 16.6 | +3.05 |
| ... | | | | |
| Garrett Wilson | 5% | 14.57% | 13.9 | -1.33 |
| Jaguars DST | 5% | 17.80% | 14.0 | **-1.79** |
| Jahmyr Gibbs | 30% | 38.58% | 24.5 | **-2.10** |

Nearly all of the gain came from being **three to four times overweight good
players at moderate ownership**, in the 8-13% band. Almost none came from
finding unowned players. Our two largest losses were both from *fading* chalk
that hit.

## 24. The field is mostly right, and that is the real constraint

| Ownership | n | mean FPTS | median |
|---|---|---|---|
| >= 15% | 5 | 14.2 | 14.0 |
| 5-15% | 33 | 11.5 | 10.0 |
| < 5% | 401 | **1.4** | **0.0** |

Ownership was strongly predictive of production. This is the single most
important correction to how I was reasoning: **low ownership is overwhelmingly a
signal that a player has no role, not that he is undervalued.** Naive
contrarianism is a losing strategy, and "nobody is on him" is usually correct
rather than exploitable.

## 25. Zero ceiling games came from the bottom of the ownership distribution

Where 20+ point games actually came from:

| Ownership | n | P(20+) | share of all ceiling games |
|---|---|---|---|
| 20%+ | 3 | 33.3% | 9% |
| 10-20% | 14 | 21.4% | 27% |
| 5-10% | 21 | 14.3% | 27% |
| 2-5% | 27 | 14.8% | **36%** |
| **< 2%** | **374** | **0.0%** | **0%** |

**374 players were owned under 2%. Not one scored 20 points.** Median zero.

Two-thirds of all ceiling games came from the **2-10%** band. That is the
leverage zone. Below 2% is not a leverage zone, it is the part of the player pool
with no role, and a dart drawn from it is a dead roster spot rather than a
lottery ticket.

This partly indicts how I pitched the darts. I sold the TB@CIN block on
"Mayfield 2%, Irving 1.5%." Realized ownership was **6.24% and 10.82%**, which
put them in the productive band — the darts were better constructed than my
own description of them. The pitch was worse than the build.

**Revised dart condition:** a dart player must have a **defined role**, and should
sit in roughly the **2-12%** ownership band. Michael Mayer with Bowers out
qualifies. Jeremiyah Love headlining a backfield qualifies. A 1%-owned WR4 does
not, however good the story is.

## 26. Quarterback is the structural leverage position

Of the four sub-5%-owned players who scored 20+, **three were quarterbacks**:
Trevor Lawrence (4.95%, 26.1), Josh Allen (3.05%, 26.0), Bryce Young (3.31%,
21.4). The fourth was DJ Moore (4.01%, 24.0).

The mechanism is structural rather than lucky: QB ownership spreads across a
dozen viable starters, so no quarterback on this slate was projected above ~12%.
That makes QB the one position where genuinely low ownership and a genuinely
high ceiling coexist routinely. Everywhere else, low ownership mostly means no
role.

**Action:** take leverage at QB first. It is the cheapest place to buy uniqueness
without buying a player who cannot score.

## 27. My Bijan override was wrong, in an instructive way

In the v1 handoff I named 30% Bijan Robinson exposure as "the thing I'd change
with another hour," reasoning that Atlanta's 17.25 implied total with a backup
quarterback made him the worst chalk on the board.

Realized: **12.88% owned, 23.5 points, our third-largest leverage gain.**

The instructive part is that the structural argument was right about one thing
and wrong about another. Section 10 concluded that when a published ownership
number conflicts with structure, trust the structure — and that held, since the
field did fade him to 12.88% against a 24.2% projection. But the same structural
reasoning was **wrong about his production.** A bad offense suppresses ownership
reliably; it predicts an individual player's output far less reliably, because a
lead back on a bad team still gets the touches.

Rule: use structural reasoning to predict **the field's behavior**, which it does
well. Do not let it override a player's **projection**, which it does badly. Those
are two different questions and I ran them together.

> Backlog items from this section are consolidated in **Appendix A: prioritized backlog** at the end of this document.

---

# Appendix A: prioritized backlog

Consolidated from sections 7, 15, 22 and 28. Ordering principle: **minutes saved
or points gained on the next Classic slate**, with anything that leaves the repo
in an unverified state ranked first regardless of size. Each item names the
evidence section it comes from.

## Already done in this session

| Item | Where |
|---|---|
| Two-tier QA gate: legality blocking, coherence scored | `scripts/qa_classic_portfolio.py` |
| Dart specification v1 | §6 |
| Parser fix for the embedded pool table, with regression test | `src/nfl_dfs/dk.py`, `tests/test_byte_line_fidelity.py` |
| Identity / pool-completeness alignment across 4 modules | §4, uncommitted |

---

## P0 — do before the next slate

These either block a clean start or waste the largest blocks of time.

**1. Resolve the six modified engine files.** `dk.py`, `priors.py`,
`projection.py`, `opportunity.py`, `selection.py`, `test_byte_line_fidelity.py`.
Re-run the full suite, accept or revert each change deliberately, commit. Right
now the next slate would start from an unverified working tree carrying
slate-day edits nobody has reviewed. *(§4. Blocking, everything else assumes it.)*

**2. Build a gate preflight.** Re-derive identity resolution, pool completeness,
player evidence states, per-group share coverage and participation vocabulary
against the actual inputs **before** the first run, and emit one report. Four of
the five blockers hit today were the same assumption expressed in four modules,
discovered serially. *(§3. Est. 40 minutes saved per slate — the single largest
time win available.)*

**3. Settle C2's fate with a measurement, not another attempt.** Benchmark
whether the candidate-bank solver can finish a 700+ person Classic pool on this
host at all. Six attempts consumed 43 minutes and produced nothing; the squeeze
between "bank too large to build in time" and "bank too small to assign" had no
feasible point. Also fix the failure routing: `CANDIDATE_BANK_TIMEOUT` is a
throughput signal and should reduce the bank or raise the budget, **not** relax
structure, which is what the rung ladder currently does. If the answer is that it
cannot finish, write that into the skill so nobody burns slate time on it again.
*(§1.)*

---

## P1 — changes the quality of the output

**4. Publish the scored player pool as a first-class artifact.** Today it came
out of a debug hook added at 12:21. The engine's real product is the gated,
evidence-bound score; construction should be a fast independent consumer of it.
This is the architectural split the whole session argues for, and it partly
dissolves item 3. *(§4.)*

**5. Add a swap / optimization gate to the QA tool.** Reject any change that
lowers projected points without a stated justification, and reject any that
raises projected ownership. **This is the highest-value single item in P1**
because it catches an error I made twice in one session: the Bijan override at
12:23 and then the Achane-to-Hampton swaps at 15:23, where I traded 15.94
projected points for 9.75 points of team implied total. Writing the rule down at
15:30 did not stop me breaking it at 15:32. It has to be mechanical.
*(§27, §"Anything we should change on the late swap".)*

**6. Rewrite the dart specification.** Two edits to §6:
   - Condition 2 becomes **"names the prior it is short"** rather than "top-4
     game total". The old rule guaranteed every dart agreed with Vegas about
     where points would be scored. *(§17.)*
   - The ownership condition becomes **"defined role, 2-12% projected"** rather
     than "lowest available ownership". 374 players were owned under 2% and not
     one scored 20 points. *(§25.)*

**7. Salary reserve policy.** Lineups carrying meaningful late-window exposure
hold **$300-600** unspent, and no optimization pass may spend below that reserve.
Building to a $49,900 mean left $0-800 of room across all twenty entries and
foreclosed every upward late swap. *(§11.)*

**8. Tag entries at build time as early-locked or swap-flexible**, and route both
late-window exposure and the salary reserve to the flexible ones. Late-swap
capacity is inversely correlated with mid-contest rank, mechanically, so this
cannot be decided at 3pm. *(§12.)*

**9. Publish the exclusion list as a build input.** The players the prior model
cannot see are the candidate pool for the type-2 dart, not a limitation to
apologize for. 188 selectable players were dropped for having no prior-season
row, in the week when that is least informative about ability. *(§18.)*

**10. Take QB leverage first in every build.** Three of the four sub-5%-owned
players who scored 20+ were quarterbacks. QB ownership spreads across a dozen
viable starters, making it the one position where low ownership and a real
ceiling reliably coexist. *(§26.)*

---

## P2 — measurement that compounds over a season

None of these change next week's portfolio much. All of them decide whether the
approach is working, and none can be answered from one slate.

**11. Log leverage P&L every slate**: `(our exposure − field ownership) × FPTS`,
summed. This slate returned **+30.9 points per lineup**, which is encouraging and
proves nothing. *(§23.)*

**12. Log projected against realized ownership every slate** and derive the shrink
factor from data rather than assuming one. Current single-sample reading:
projections ≥20% came in 6.24 points low, projections <10% came in 0.99 high.
*(§9.)*

**13. Track dart outcomes as a season series**, measured on top-1% finish rate,
not slate mean. Darts returned 1.74 points per $1,000 of locked salary against
the core's 2.16 today; judging a variance strategy on one sample's mean is the
wrong test. *(§13.)*

**14. Add points per $1,000 of locked salary to the QA tool** as the mid-contest
metric, so a late-swap review never reads raw rank. Entries ranged from $49,900
locked to $16,300 locked; their ranks were not comparable. *(§12.)*

**15. Screen darts against second-order chalk.** Check whether a low-owned player
is being publicly recommended as *the* leverage play before treating his
projection as real. Chase Brown was the published leverage play at 8.8% projected
and realized 9.78%. *(§19.)*

**16. Weight prior-breaking darts by week.** Heaviest in Weeks 1-3, tapering as
current-season data accumulates. By Week 8 the priors carry real information and
this argument weakens. *(§18.)*

---

## P3 — hygiene

**17. Un-hardcode `AS_OF`** in `tests/test_priors_adapter.py`. A fixed wall-clock
constant fired 18 test failures at 10:00am ET today and cost five minutes to
prove innocent. *(§3.)*

**18. Handle the DraftKings `D` status natively** rather than requiring the
operator to remember `--unavailable-status D`. *(§3.)*

**19. Add a 20-entry fixture.** `tests/fixtures/supplied` carries two entry rows,
which is the only reason the embedded pool-table parse defect survived to a live
slate. *(§3.)*

---

## Sequencing note

P0 items 1-3 are roughly a half day and should happen midweek, not on a Sunday.
P1 items 5, 6 and 7 are small edits with disproportionate effect and could ship
alongside them. P1 item 4 is the largest piece of work here and the one most
worth doing properly; it is also the item that makes every future slate faster,
so it should start as soon as P0 is clear rather than waiting for a quiet week.

P2 is pure instrumentation. It costs little and it is the only way any of the
conclusions in this document graduate from one-slate observations to something
worth trusting.

---

# Appendix B: session chunking

The binding constraint on this repo is not developer time, it is **read cost**.
Three files dominate everything:

| File | Bytes | ~tokens |
|---|---|---|
| `cli.py` | 149,874 | **39,400** |
| `prior_review.py` | 128,675 | **33,900** |
| `priors.py` | 104,058 | **27,400** |

Reading those three together is ~100K tokens **before any work starts**. That
single fact determines the chunking: no session may require deep reads of more
than one of them.

## Pairing rules used below

1. **Same files, same session.** Re-reading a 30K-token module in two sessions is
   the most expensive mistake available.
2. **Same verification cycle, same session.** The full suite is ~200s. Work that
   forces a suite re-run should be batched behind one verification.
3. **Long wall clock + low context pairs with light independent work.**
   Benchmarks and long runs leave the context budget idle; fill it with leaf work.
4. **Never batch two heavy reads.** This is the rule that makes B and D separate
   sessions even though they feel related.

## Dependency graph

```
  A  stabilize  ──────────────┬──> B  preflight        (independent after A)
  (clean tree)                ├──> C  C2 verdict       (independent after A)
                              └──> D  scored pool artifact
                                        │
                                        └──> E  construction rules
  F  instrumentation ── no dependencies, any time
```

Only A is a hard prerequisite for everything. B, C and D are parallel after it.
E is the only item genuinely blocked behind another piece of work.

## The sessions

### Session A — stabilize the tree
**Items:** P0-1, plus P3-17, P3-18, P3-19.
**Why together:** P0-1 already requires running the full suite and touching
`tests/`. P3-17 (`AS_OF` hardcoded) and P3-19 (20-entry fixture) live in exactly
those test files, and P3-18 (`D` status) is a six-line change in
`participation.py`. Batching them means **one** verification cycle instead of
four.
**Read:** diffs of the six modified files plus their test neighbours, not whole
modules. `priors.py` and `projection.py` read targeted, not end to end.
**Context:** ~35-45K. **Done when:** suite green, each of the six changes
explicitly accepted or reverted, committed, and the three hygiene defects closed.
**This is the only session that must happen before the next slate.**

### Session B — the gate preflight
**Items:** P0-2, alone.
**Why alone:** it is the single most expensive read in the backlog. It must
understand the identity gate (`prior_review.py`), pool completeness (`priors.py`,
`projection.py`, `opportunity.py`) and the participation vocabulary, then write
into the existing `preflight.py`. That is ~83K of source before a line is
written. **Do not add anything to this session.**
**Context:** ~90-120K. **Done when:** a single command re-derives every gate
against real inputs and emits one report that would have surfaced all five of
2026-09-13's blockers at once.
**Highest time payback in the backlog: ~40 minutes per slate.**

### Session C — C2 verdict, plus two leaf items
**Items:** P0-3, plus P1-5 (swap gate) and P1-6 (dart spec rewrite).
**Why together:** benchmarking the candidate-bank solver is **wall-clock heavy
and context light** — each run was 6-8 minutes on 2026-09-13 with nothing to read
while it runs. P1-5 touches only `scripts/qa_classic_portfolio.py` (~2.4K tokens,
zero engine dependencies) and P1-6 is documentation plus the skill. Both fit
entirely in the dead time between benchmark runs.
**Context:** ~50K. **Done when:** a measured verdict on whether C2 can finish a
700+ person pool on this host, the failure routing treats
`CANDIDATE_BANK_TIMEOUT` as throughput rather than structure, the swap gate
rejects projection-lowering and ownership-raising changes, and the dart spec
carries both rewrites.

### Session D — publish the scored player pool
**Items:** P1-4, alone.
**Why alone:** adding a command means reading `cli.py`, which is 39K tokens by
itself, plus `prior_score.py`, `selection.py` and `contracts.py` for the schema.
Rule 4 applies.
**Context:** ~70-90K. **Done when:** the engine emits a gated, hash-bound scored
pool as a first-class artifact and `scripts/build_classic_portfolio.py` reads it
instead of the debug hook in `selection.py`. Remove the hook in the same session.

### Session E — construction rules
**Items:** P1-7, P1-8, P1-9, P1-10.
**Why together:** all four are rules inside the *same new module*
(`scripts/build_classic_portfolio.py`), and all four need the scored-pool schema
from D. Doing them separately means re-reading the same file four times for no
benefit.
**Context:** ~30K, almost all of it the new module plus D's schema. **Done when:**
the builder holds a salary reserve, tags entries early-locked versus
swap-flexible, treats the prior model's exclusion list as the type-2 dart
candidate pool, and takes QB leverage first.

### Session F — instrumentation
**Items:** P2-11 through P2-16.
**Why together:** all six are standalone logging and scoring scripts with **no
engine dependencies whatsoever**. They read a run folder and a standings export.
**Context:** ~25K. **Done whenever.** Cheapest session in the list and the only
one that decides whether any conclusion in this document is real.

## What I would actually do

**A** midweek, because it is the only blocker and it is small. Then **C**, because
the C2 verdict either reclaims 43 minutes per slate or tells us to stop trying,
and it carries two high-value leaf items for free. Then **B**, the biggest single
time win. **D** and **E** are the architecture work and deserve a quiet stretch
rather than a Saturday. **F** any time, and sooner is better, because every
number in this retrospective currently rests on one slate.

## Rescued this session

`scripts/build_classic_portfolio.py` and `scripts/write_dk_entries.py` were
promoted out of the session scratchpad, where they would have been lost. That is
the code that produced the shipped portfolio while the engine's own solver could
not, plus the byte-level export verification that ran clean on every version.
Both carry provenance headers naming the backlog items still open against them,
so session E has an explicit starting point rather than a blank file.
