# Debrief: DAL @ NYG showdown, contest 195520918

Source: `contest-standings-195520918.zip`, the $0.25 Winner Take All
[$100 to 1st], 475 entries. Observations only. Nothing here is a fix; these are
candidates for the backlog.

---

## 0. Read this before drawing any conclusion about performance

**The standings are a live mid-game snapshot, not settlement.** Every one of the
475 entries reports the identical `TimeRemaining` of 281.22, the file was written
at 00:55 UTC against a 00:20 UTC kickoff, and the leading score is 33.02 with a
median of 12.03. That is roughly one quarter of football.

So: **the ranks and points in this file say nothing about whether the build
worked.** Our entry sitting 426th is a first-quarter reading, not a result. Pull
the final standings after the game settles and the performance questions can be
answered then.

What *is* final and complete is the `%Drafted` column. Ownership locks at lock.
That column is the first real field-ownership dataset this project has ever had,
and it is the reason this file matters.

---

## 1. The finding that matters most

**25 of the top 25 lineups roster at least one DST. We rostered a DST in 0 of 20.**

Five of the top 25 roster *both* DSTs. The leader captained the Giants DST at
0.63% captain ownership. Captains in the top 25: Cam Skattebo 12, Jaxson Dart 6,
Cowboys DST 3, Giants DST 2, Malik Nabers 1, George Pickens 1.

This is not variance and it is not a scoring miss. It is structural. A defensive
or special-teams score is a large, cheap, correlated chunk of showdown points,
and two facts in the engine guarantee we never touch it:

- `simulation.py` does not model defensive return touchdowns, safeties or blocked
  kicks at all. That limitation is already documented. Its practical consequence
  was never stated: **DSTs are systematically underpriced by our own objective**,
  so mean-max will not select one, let alone captain one.
- There is no way to express "this lineup is a defensive-script lineup," which is
  the same missing-constraint problem the retrospective already flagged.

A single low-scoring first quarter is exactly the script where this costs the most,
and it is the script the field was clearly prepared for and we were not.

## 2. Field ownership, measured

Captain ownership, all 24 people who drew any:

| Captain | Own% | | Captain | Own% |
|---|---:|---|---|---:|
| Javonte Williams | 19.58 | | Cowboys DST | 2.74 |
| Jaxson Dart | 16.84 | | Brandon Aubrey | 1.68 |
| Dak Prescott | 12.84 | | Malachi Fields | 1.26 |
| CeeDee Lamb | 12.00 | | Ryan Flournoy | 1.05 |
| George Pickens | 9.05 | | Jake Ferguson | 0.84 |
| Cam Skattebo | 6.95 | | Theo Johnson | 0.84 |
| Malik Nabers | 6.53 | | Giants DST | 0.63 |
| Isaiah Likely | 3.79 | | eight others | < 0.7 each |

**Max captain ownership was 19.6%, not the 20 to 35 percent the skill asserts.**
Top three captains sum to 49.3%, HHI 0.118. The field is more spread at captain
than our documentation claims. That assumption should be corrected rather than
carried forward.

**The salary-derived ownership prior is viable and incomplete.** Regressing
captain ownership on log(CPT salary): slope 6.08, **R-squared 0.492**, n=24. Half
the variance from the salary file alone, zero licensing cost. The residuals are
where it breaks: Javonte Williams at $13,500 drew the *highest* captain ownership
(19.58%) while CeeDee Lamb at $16,200 drew 12.00%. Salary gets the shape; it
misses who the field actually likes. Adding a projection term is the obvious v2,
and the honest test is whether it beats 0.492 out of sample.

## 3. Our leverage profile, measured

Twenty entries means each lineup is 5% of our exposure.

**Where we were genuinely contrarian and correct to be:**

| Player | Slot | Field | Ours | Leverage |
|---|---|---:|---:|---:|
| Theo Johnson | FLEX | 17.05% | 55% | +38.0 |
| Tyrone Tracy Jr. | FLEX | 14.53% | 50% | +35.5 |
| Javonte Williams | FLEX | 35.16% | 65% | +29.8 |
| Jake Ferguson | FLEX | 16.84% | 45% | +28.2 |
| Tyrone Tracy Jr. | CPT | 0.42% | 10% | +9.6 |
| Ryan Flournoy | CPT | 1.05% | 10% | +8.9 |

Four of our eleven captains were sub-1.1% field captains. That is real
differentiation and it happened by accident, as a byproduct of the captain-cap
mechanics, not because anything in the build was aiming at leverage.

**Where we had nothing and the field did:**

| Player | Slot | Field | Ours | Gap |
|---|---|---:|---:|---:|
| Isaiah Likely | FLEX | 24.84% | 0% | -24.8 |
| Malik Nabers | FLEX | 22.95% | 0% | -22.9 |
| Cam Skattebo | FLEX | 34.11% | 15% | -19.1 |
| Cowboys DST | FLEX | 18.11% | 0% | -18.1 |
| Brandon Aubrey | FLEX | 26.53% | 10% | -16.5 |
| Giants DST | FLEX | 13.68% | 0% | -13.7 |
| Emari Demercado | FLEX | 13.26% | 0% | -13.3 |

Isaiah Likely and Malik Nabers were both `SELECTABLE` with no gate against them,
and both were kept out by the 80-candidate bank truncation already documented.
The field had a combined 29.5% on Nabers across both slots while our engine
carried him at a 0.098 target share. That is independent confirmation that the
`TARGET_SHARE` unit defect is costing real exposure to the right players, not
just producing an odd-looking number.

## 4. The contest-allocation error, now concrete

Our single entry in this contest was `5254932025`:
**Dak Prescott (CPT) | Pickens, Javonte Williams, Ferguson, Aubrey, Theo Johnson.**

That was lineup 1, the highest-objective lineup in the portfolio, and it contains
a kicker. **We put our chalkiest, most floor-oriented lineup into the one
Winner-Take-All on the slate.**

Entries were assigned to contests in template order with no contest awareness.
The WTA is the single contest where only first place pays and where a dart is
strictly correct. It received the opposite. This is the "why is this one
portfolio" question from the retrospective, and this file turns it from a
hypothesis into a measured mistake.

## 5. What this validates, and what it corrects

**Validates:**

- The bank-truncation defect. Likely and Nabers were both heavily owned by the
  field and neither could reach our bank.
- The `TARGET_SHARE` unit mismatch. The field independently priced Nabers far
  above our engine.
- The contest-aware allocation gap, now with a named entry and a named contest.

**Corrects:**

- Showdown captain chalk tops near 20%, not 20 to 35 percent. Fix the claim in
  the skill.
- Our stated concern that 9 of 20 lineups rostering both QBs was a weakness looks
  overstated. Dak drew 58.95% and Dart 52.63% in FLEX, so the field was doing the
  same thing at scale. Both-QB was closer to the field's baseline than to a
  contrarian position.
- My assumption that the engine's DST handling was a minor documented limitation.
  It is the largest single structural gap this file exposes.

## 6. Candidate backlog items

Not fixes. Items to slot.

| Item | Note |
|---|---|
| Model defensive/ST scoring, or add an explicit DST floor adjustment | 25 of 25 top lineups had a DST; we had none in 20 |
| Capture final standings after every contest settles | This snapshot cannot answer performance; a settled file can |
| Build the ownership capture into a repeatable step | `%Drafted` is free, final, and per-slate |
| Fit ownership v1 on log(salary), R^2 0.492 baseline to beat | Already computed here |
| Contest-aware entry allocation: WTA gets ceiling, satellites get threshold, GPP gets diversity | Measured error in section 4 |
| Correct the captain-chalk figure in the showdown skill | 19.6% observed, not 20-35% |
| Re-check the bank cap against field-owned players | Likely and Nabers both missed |

## 7. What I could not determine

- Any performance conclusion. The file is mid-game.
- Why the game was scoring so low through one quarter. Worth a look at the final
  box score, since our weather read was CLEAR and the low first quarter may have
  a cause the model should know about.
- Ownership for the other seven contests holding our remaining 19 entries. Each
  contest has its own standings export, and the entry-level leverage read changes
  by contest.
