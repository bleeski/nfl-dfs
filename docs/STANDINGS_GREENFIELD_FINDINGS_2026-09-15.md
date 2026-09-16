# NFL contest standings: greenfield findings

**Prepared September 15, 2026.** Analysis of every contest export in [data/standings/inbox](<C:/Users/benja/Documents/Claude/nfl-dfs/data/standings/inbox>), joined to the supplied DraftKings contest-entry history and the matching local salary/entry records.

## Executive findings

1. **The most actionable issue is player coverage and ownership measurement.** Our 51 Showdown entries used no defenses. Our DAL–NYG portfolio omitted Isaiah Likely, who appeared in every top-1% lineup in the representative contest. Our DEN–KC portfolio omitted Kenneth Walker III, who appeared in every paid lineup in the representative contest. These are observed portfolio gaps that warrant tracing back through eligibility, projections, candidate generation, and selection. They do not establish that those players were certain plays before kickoff.
2. **The archived Classic ownership inputs are not coherent probabilities.** Eleven quarterback estimates sum to 200.6%; 17 defense estimates sum to 186.5%. Each position occupies exactly one roster slot. Fix the source/column interpretation and validation before treating the figures as ownership. On the 86 covered players, mean absolute error was 7.82 percentage points and rank correlation was only 0.128.
3. **There is no universal winning Showdown team split.** In the largest contest for each game, 3–3 was overrepresented in the top 1% for NE–SEA and DAL–NYG. The 5–1 split was overrepresented for SF–LAR and DEN–KC. Winning first place and merely reaching the paid places often favored different constructions.
4. **Classic stacking showed useful associations, with strong player/game dependence.** QB plus two same-team pass catchers reached the top 1% at a 1.47% rate versus 0.85% for QB plus one. But double-or-larger stacks helped some quarterbacks and hurt others. This is one Classic slate, not a general stacking law.
5. **Our Classic entries were unusually contrarian.** Eighteen of 20 fell in the bottom half of the field by summed actual ownership. They averaged 3.4 players below 5% ownership versus 2.23 in the field and 1.44 in the top 1%. All 20 were unique in the contest; additional differentiation was not the obvious missing ingredient.
6. **Showdown duplication materially changes the problem.** Only 6.5–9.8% of entries in the four representative Showdown fields had a lineup nobody else used. The DEN–KC mini-MAX had 206 entries tied first with the exact same lineup. Ownership estimates alone do not capture this payout dilution.
7. **We cannot yet identify a contest type in which we have a durable advantage.** Our 71 entries cost $154.25 and returned $98.70, a $55.55 loss and −36.0% realized ROI. Showdown's +15.6% ROI is driven by two $20 NE–SEA entries. Excluding them, Showdown ROI was −81.1%. No entry finished first or in the top 1%.

**Evidence strength:** excellent coverage of these particular fields; limited evidence of repeatable strategy. The 26 contests represent just five slate groups: one Classic slate and four Showdown games. Repeated contests and identical winning lineups do not create additional independent football outcomes.

## 1. Evidence, definitions, and scope

### 1.1 Corpus and reconciliation

- 26 distinct contest IDs: 25 ZIP archives and one standalone CSV. No contest was counted twice.
- 1,870,717 entry rows: 832,342 Classic and 1,038,375 Showdown.
- 1,865,110 submitted lineups; 5,607 entries have a blank lineup. Blank entries remain in contest-size and rank denominators and are excluded from construction analysis.
- All exports report zero time remaining. All 1,870,717 ranks reproduce exactly after rounding exported scores to two decimals to remove floating-point export noise.
- Every submitted lineup resolves to a unique player identity in the corresponding salary pool after trimming surrounding whitespace. No fuzzy name matching was used. All reconstructed salary totals are at or below $50,000.
- Every submitted lineup's score reconstructs from the same game's player/role points, including the Captain multiplier. Two incomplete player side tables were supplemented from other supplied contests on the same game; existing scores agree across those sources.
- Contest history matches all 26 field sizes, all 71 owned Entry IDs, and every owned rank and score. All matched account labels resolve to `bleeski`. No ticket winnings occurred in these 71 entries.

The history file contains other contests and sports. Only the 26 inbox contest IDs enter this report. Production code, existing run files, standings, and trackers were not changed. This report is an exploratory retrospective, not a model-promotion or upload-certification artifact.

### 1.2 What the reported measures mean

**Top 1%:** reported rank ≤ floor(1% × all contest entries), including the complete tie group at the boundary. For fields below 100, the all-contest appendix uses first place as the smallest available cohort; the main strategy tables use large fields. This tie-inclusive definition can include more than 1% of entries.

**Paid finish:** rank reaches a paid place recorded in the supplied contest history, including ties crossing that boundary. This is an actual contest-specific threshold, not a top-20% proxy. For ordinary tournaments it indicates a share of cash prizes; for satellites it indicates a share of the award positions. Our winnings are directly observed in history. Other entrants' dollar winnings generally cannot be calculated because the complete payout ladder is available locally for only one contest.

**Field share / top-1% share:** how common a construction is among submitted lineups / among top-1% entries. **Lift** is top-1% share divided by field share. A 2× lift describes this observed field; it is not a forecast of doubling future returns.

**Ownership:** counted directly from submitted lineups and divided by all entries in that contest, preserving Captain and FLEX separately. Classic person ownership aggregates base-position and FLEX appearances. Lineup ownership sum adds those marginal percentages; it is neither a lineup probability nor a duplication estimate. Construction/player-exposure tables use submitted-lineup denominators, so small differences from exported ownership percentages are expected.

**Team shapes:** Showdown 5–1, 4–2, or 3–3 counts both teams including Captain, kickers, and defenses; the label is unordered. Classic QB+2 means the quarterback plus two same-team WR/TE players, excluding running backs and defense. A bring-back is an opposing RB/WR/TE. Team assignments come from the same-slate salary records.

**Duplication:** exact scoring-equivalent roster, with Captain identity preserved. Reordering FLEX slots does not create a new lineup. Classic FLEX placement changes do not create a new scoring lineup. “Unique entry” means its lineup occurs once, not distinct-lineup count divided by field size.

**Our performance:** actual account entries, not an assertion that a particular local build produced every submitted lineup. Submission edits, build versions, and historical provenance must be reconciled before attributing a result to a specific engine version.

### 1.3 Controlling the most important sources of bias

The main construction comparisons use the largest supplied contest for each game/slate. All 26 contests still enter the inventory, account results, and contest comparisons. This avoids pooling the same football outcome eight times and presenting it as eight replications.

I checked sensitivity to (a) fractional weighting of the top-1% boundary tie, and (b) counting each distinct lineup once while retaining the same score threshold. I also examined Classic stacks within quarterback. No significance claims or broad confidence intervals are warranted with four Showdown games and one Classic slate. These are exploratory comparisons across many features, not preregistered discoveries.

| Representative contest | Slate/game | All entries | Submitted | Top-1% entries, ties included | Paid places in history | Entries sharing paid positions |
|---|---|---|---|---|---|---|
| 193028206 | Classic, Sep 13 | 832,342 | 831,028 | 8,347 | 173,275 | 173,354 |
| 193391013 | NE–SEA, Sep 9 | 126,020 | 125,800 | 1,261 | 26,495 | 26,495 |
| 195390868 | SF–LAR, Sep 10 | 178,359 | 177,958 | 1,831 | 37,455 | 37,689 |
| 195526142 | DAL–NYG, Sep 13 | 59,453 | 59,161 | 722 | 15,950 | 16,005 |
| 195526229 | DEN–KC, Sep 14 | 237,812 | 236,835 | 2,420 | 49,940 | 50,084 |

## 2. Our actual performance

### 2.1 Results by slate/game

ROI below is `(observed cash + ticket face value − entry fees) / entry fees`. Ticket winnings were zero. “Median field beaten” gives half-credit for a tie and is independent of the payout structure.

| Slate/game | Our entries | Paid | Fees | Cash returned | Net | ROI | Median field beaten |
|---|---|---|---|---|---|---|---|
| Classic, Sep 13 | 20 | 4 | $100.00 | $36.00 | -$64.00 | -64.0% | 61.5% |
| NE–SEA, Sep 9 | 2 | 2 | $40.00 | $60.00 | $20.00 | 50.0% | 86.2% |
| SF–LAR, Sep 10 | 11 | 2 | $4.20 | $2.20 | -$2.00 | -47.6% | 39.0% |
| DAL–NYG, Sep 13 | 20 | 1 | $5.15 | $0.50 | -$4.65 | -90.3% | 29.6% |
| DEN–KC, Sep 14 | 18 | 0 | $4.90 | $0.00 | -$4.90 | -100.0% | 12.8% |

**Classic:** 4/20 paid, with $36 returned on $100. The best entry scored 196.96 and ranked 23,887/832,342, approximately the top 2.9%. The top-1% score threshold was 209.00 and the paid threshold was 165.46. Our best result was competitive, but well short of the extreme tail.

**Showdown:** 5/51 paid, with $62.70 returned on $54.25. The two NE–SEA entries both won $30; their $60 return supplies 95.7% of all Showdown winnings. The remaining 49 entries cost $14.25 and returned $2.70. DAL–NYG paid once in 20 entries; DEN–KC paid zero times in 18.

Across all contests, nine paid finishes compare with **9.72 expected paid finishes for uniformly selected entries in those exact fields**, calculated as the sum of our entry count × each field's observed paid fraction. This expectation does not assume our entries are independent and is not an expected-dollar-return model. Raw cash rate alone misses payout size and the large differences in contest thresholds.

### 2.2 Do we do better in a particular contest type?

The descriptive results are:

| Contest type | Contests | Our entries | Paid | Fees | Returned | ROI |
|---|---|---|---|---|---|---|
| 150-max GPP | 2 | 2 | 0 | $1.00 | $0.00 | -100.0% |
| 20-max GPP | 3 | 3 | 0 | $3.00 | $0.00 | -100.0% |
| 40x booster | 2 | 2 | 0 | $0.50 | $0.00 | -100.0% |
| Other GPP | 7 | 32 | 8 | $141.60 | $96.70 | -31.7% |
| Satellite | 7 | 26 | 0 | $4.40 | $0.00 | -100.0% |
| Single-entry GPP | 3 | 3 | 1 | $3.00 | $2.00 | -33.3% |
| Unspecified $0.25 contest | 1 | 2 | 0 | $0.50 | $0.00 | -100.0% |
| Winner take all | 1 | 1 | 0 | $0.25 | $0.00 | -100.0% |

“Other GPP” includes the two Millionaires and Dime/Quarter tournaments whose exact maximum-entry limits are not established by the local contest names. I did not infer those limits. The generic $0.25 contest remains separate because its name does not establish its entry limit or full payout shape. There are no identified head-to-heads or double-ups here.

**Interpretation:**

- Single-entry GPP results are one cash in three attempts, a −33.3% return, and a median field-beaten percentage of 49.3%. That is too little evidence to prefer single-entry contests on expected return.
- The 20-max and 150-max examples are all Showdown and include only five owned entries combined. Their losses cannot identify entry-limit effects separately from the games and lineups played.
- Satellites produced 0/26 awards, but uniformly selected field entries would produce only **0.23 expected paid finishes** across those same 26 attempts. Zero awards is therefore weak evidence of poor satellite skill on its own. Our low ranks supply more diagnostic information than the zero-win headline.
- Classic plus NE–SEA accounts for $140 of $154.25 in fees, or 90.8%. Dollar-weighted performance is concentrated in two contests. Entry-weighted and dollar-weighted comparisons tell different stories.

**The useful next decision is to improve contest-specific measurement and allocation, not to declare a winning buy-in or entry-limit niche from this sample.**

### 2.3 Satellites and boosters are extreme-rank objectives

Five of seven satellite contests pay one place; two pay two places. Their paid fractions range from 0.42% to 4.26%. The two 40x boosters pay five places out of 237, about 2.11%; the winner-take-all pays one out of 475, about 0.21%.

A flat award at a very high score threshold is not a conventional “cash-game” objective. An allocation policy should maximize the probability of reaching that threshold, with ties and award rules represented. It should not automatically send a conservative, lower-ceiling lineup to a satellite simply because all awarded tickets have the same value. Full payout/award schedules remain necessary for exact field prize calculations.

## 3. Ownership: concrete improvements and a first benchmark

### 3.1 Repair the archived Classic input before calibrating it

The local [data/runs/20260913-week1-portfolio/build_portfolio.py](<C:/Users/benja/Documents/Claude/nfl-dfs/data/runs/20260913-week1-portfolio/build_portfolio.py>) contains an 86-player `MODEL` dictionary described as a transcribed public model snapshot at 11:12:08 EDT on September 13. Its second value is used as ownership. This is an archived research input, distinct from [src/nfl_dfs/ownership.py](<C:/Users/benja/Documents/Claude/nfl-dfs/src/nfl_dfs/ownership.py>).

The values fail basic roster arithmetic even before considering omitted players:

| Position | Sum of archived estimates | Constraint |
|---|---:|---|
| QB, 11 covered players | 200.6% | Exactly one QB: no more than 100% across any subset |
| DST, 17 covered teams | 186.5% | Exactly one DST: no more than 100% across any subset |
| All 86 covered players | 910.0% | Nine roster slots, with additional pool members omitted |

Against the final field, the 86 common players have **7.82 percentage points mean absolute error**, **10.29 points root mean squared error**, **+3.37 points mean bias**, and **0.128 Spearman rank correlation**. These are diagnostics of the stored numbers, not a verified prospective grade of the external provider or the current engine. Source-column interpretation, transcription, contest/slate alignment, update time, and units must be checked first.

| Player | Stored estimate | Observed ownership | Stored minus observed |
|---|---|---|---|
| Jahmyr Gibbs | 5.90% | 42.75% | -36.85 pp |
| Trevor Lawrence | 35.10% | 4.95% | +30.15 pp |
| Josh Allen | 31.60% | 3.05% | +28.55 pp |
| Colston Loveland | 35.80% | 12.88% | +22.92 pp |
| Ja'Marr Chase | 10.40% | 30.12% | -19.72 pp |
| Tyler Shough | 27.50% | 8.88% | +18.62 pp |
| Chris Olave | 7.30% | 24.77% | -17.47 pp |

Jahmyr Gibbs is the most consequential example: the stored figure was 5.9%, actual field ownership was about 42.75%, and 74.6% of the top-1% submitted lineups included him. We used him in 6/20 entries. An apparently low-owned player can be a core field play when the input itself is wrong. Renormalizing an incoherent vector would repair its sum but would not establish that it measures the correct quantity.

### 3.2 Current ownership code: model structure versus submitted-lineup path

The current `ownership.py` combines salary rank, projection rank, value rank, and team implied points, then applies a fixed softmax scale of 2.1. It returns `COLD_START_OWNERSHIP_PRIOR` states. Its function does not accept contest size, entry fee, entry limit, or payout shape.

Two specific improvements follow from the data and code:

1. **Estimate position totals consistently with FLEX usage.** Current Classic targets are QB 1.0, RB 2.5, WR 3.5, TE 1.0, DST 1.0. In the observed submitted field, FLEX was RB 42.5%, WR 36.1%, TE 21.4%, implying average roster totals RB 2.425, WR 3.361, TE 1.214. A TE total of 1.0 leaves no ownership mass for a second tight end. Separately, `field.py` samples FLEX using 42% RB / 48% WR / 10% TE, so its construction assumptions are different again. Learn a common FLEX-position distribution and validate the resulting sampled field marginals after salary/legality filtering.
2. **Fit concentration and eligibility rather than treating rank weights as calibrated probabilities.** Role-specific scaling, active-player evidence, and coverage matter. A salary pool contains backups and unavailable players as well as likely participants. An eligibility mask must be based on information available before lock, never on who later scored or happened to be rostered.

The prior-only selection path explicitly does not use the ownership/field/economics modules. Improving `ownership.py` by itself will therefore not change that path's submitted lineups. A later integration needs explicit calibration status, matching prediction provenance, and a measured selection objective. There is no complete matched pre-lock ownership ledger here with which to grade every current-engine prediction; I have not substituted hindsight projections for missing forecasts.

### 3.3 A salary-only benchmark already gives a useful test target

I ran a small retrospective benchmark using the four representative Showdown fields. For each held-out game, the other three games selected one salary-concentration parameter. Captain probabilities were proportional to salary raised to that parameter. FLEX used a logistic salary curve with an intercept chosen so inclusion probabilities sum to five and each remains below one. All salary-pool players were retained. No fantasy outcomes, actual ownership of the held-out game, or `AvgPointsPerGame` entered its predictions.

Training selected the parameter by equal-game mean absolute ownership error over a 0–4 grid in 0.1 steps, separately for Captain and FLEX. Labels were normalized to submitted lineups for the one-/five-slot totals. Uniform ownership over the same pool was the comparison. Results, in percentage points:

| Held-out game | Salary CPT MAE | Uniform CPT MAE | Salary FLEX MAE | Uniform FLEX MAE |
|---|---|---|---|---|
| NE–SEA, Sep 9 | 1.02 | 2.22 | 5.09 | 10.32 |
| SF–LAR, Sep 10 | 0.79 | 2.60 | 5.63 | 10.76 |
| DAL–NYG, Sep 13 | 1.03 | 2.77 | 4.51 | 11.27 |
| DEN–KC, Sep 14 | 0.64 | 2.59 | 4.25 | 11.15 |
| Equal-game average | 0.87 | 2.54 | 4.87 | 10.87 |

This is a promising baseline to beat, not a promoted model and not a comparison against a fully replayed current engine. Average error over the whole pool includes many near-zero players. In NE–SEA the salary model still underpredicted the five most-owned FLEX players by 17.3 percentage points on average. One selected Captain parameter reached the edge of the tested grid. Four games cannot establish reliable tail calibration. The folds also include later games when predicting earlier games, so this is grouped retrospective validation, not a chronological deployment test.

**Recommended next challenger:** eligibility-aware salary baseline plus projection/value features and a restrained position effect; fit separate Captain/FLEX scales. Add contest effects only with shrinkage toward a shared slate estimate. Require chronological held-out slates and report error by ownership band, top-five-player recall, calibration slope, and role/position totals. Compare against this salary baseline as well as the existing prior.

### 3.4 Contest conditioning is measurable

Same-game ownership differs materially between the large multi-entry field and the single-entry field. Examples use all-entry ownership denominators:

| Game | Player/role | Large field | Single entry | Difference |
|---|---|---|---|---|
| SF | Brock Purdy FLEX | 49.8% | 32.9% | -16.9 pp |
| SF | Christian McCaffrey FLEX | 46.8% | 57.4% | +10.6 pp |
| DAL | Isaiah Likely FLEX | 27.4% | 33.3% | +5.9 pp |
| DEN | Patrick Mahomes FLEX | 55.4% | 48.2% | -7.2 pp |
| DEN | Kenneth Walker III FLEX | 42.1% | 48.5% | +6.4 pp |
| DEN | Chiefs FLEX | 13.6% | 7.5% | -6.1 pp |

These contrasts come from fields of thousands, not just tiny satellites. They support a contest-conditioned model, but they do not prove that single-entry entrants are always sharper or chalkier. The direction varies by player. Measure entry-limit, fee, field-size, and payout effects across many independent games before assigning permanent adjustments.

### 3.5 Learn joint construction, not just marginal ownership

A field generator should reproduce Captain shares, team splits, QB counts, salary remaining, FLEX-position mix, conditional pairings, and exact-lineup multiplicities. Current `field.py` uses fixed Classic teammate/opponent sampling boosts and independently samples Showdown FLEX players after Captain selection, subject to legality. Those mechanics need empirical validation against the field they actually generate.

For example, the most-owned Captain in the representative Showdown fields ranged from about 15.8% to 21.4%, after excluding blank submissions. There is no evidence here for a universal maximum of 20% or a universal 20–35% band. Likewise, multiplying six marginal ownerships cannot explain why a particular roster appears 206 times. Model construction and repeated optimizer-like choices explicitly, then compare simulated and observed duplication histograms.

## 4. Classic: which shapes reached the top 1% and paid?

These comparisons cover **831,028 submitted lineups on one 12-game slate**. The field top-1% rate is about 1.004% after boundary ties and removal of blank submissions; the paid-finish rate is about 20.86%.

### 4.1 Pass-catching stacks

| Construction | Entries | Field share | Share of top 1% | Top-1% rate | Paid-finish rate | Our entries |
|---|---|---|---|---|---|---|
| 0 | 159,260 | 19.2% | 10.0% | 0.5% | 17.0% | 0 |
| 1 | 440,753 | 53.0% | 44.9% | 0.8% | 19.7% | 12 |
| 2 | 217,200 | 26.1% | 38.4% | 1.5% | 25.2% | 7 |
| 3 | 13,500 | 1.6% | 6.7% | 4.2% | 34.6% | 1 |

Larger stacks were overrepresented near the top, but rare constructions require caution. QB+3 was only 1.62% of the field, and this one slate cannot justify making it a default. QB+4/5 existed in 315 entries and had no top-1% finishes.

Within-quarterback comparisons reveal the confounding: using at least two pass catchers versus zero or one had a top-1% rate ratio of **2.81× for Tyler Shough** and **2.17× for Bryce Young**, but **0.19× for Caleb Williams** and **0.46× for Jared Goff**. Stack success depends on which teammates generated the points, the quarterback's scoring profile, and the rest of the lineup. A hard universal stacking count loses that distinction.

### 4.2 Bring-backs and combined shapes

| Construction | Entries | Field share | Share of top 1% | Top-1% rate | Paid-finish rate | Our entries |
|---|---|---|---|---|---|---|
| 0 | 465,087 | 56.0% | 34.7% | 0.6% | 18.1% | 0 |
| 1 | 298,588 | 35.9% | 45.5% | 1.3% | 22.4% | 13 |
| 2 | 61,598 | 7.4% | 18.3% | 2.5% | 32.4% | 7 |
| 3 | 5,372 | 0.6% | 1.4% | 2.2% | 42.1% | 0 |

Selected combined constructions:

| Construction | Entries | Field share | Share of top 1% | Top-1% rate | Paid-finish rate | Our entries |
|---|---|---|---|---|---|---|
| QB+1 / back 0 | 253,895 | 30.6% | 19.9% | 0.7% | 18.0% | 0 |
| QB+1 / back 1 | 157,979 | 19.0% | 20.3% | 1.1% | 20.9% | 9 |
| QB+2 / back 0 | 93,204 | 11.2% | 8.1% | 0.7% | 19.5% | 0 |
| QB+2 / back 1 | 94,641 | 11.4% | 19.3% | 1.7% | 26.7% | 3 |
| QB+2 / back 2 | 26,530 | 3.2% | 10.4% | 3.3% | 38.0% | 4 |
| QB+3 / back 2 | 2,525 | 0.3% | 3.1% | 10.2% | 57.9% | 0 |

QB+2 with two bring-backs reached the top 1% at 3.29% and paid at 38.00%, versus 0.73% and 19.47% for QB+2 without a bring-back. QB+3 with two bring-backs looks still stronger, but consists of only 2,525 entries selected around a few realized games. Treat these as scenarios to ensure the candidate bank can represent, not estimates of future win probability.

Our 20 entries already all had a bring-back, and eight had at least two pass catchers. More stacking alone is unlikely to resolve the full performance gap.

### 4.3 FLEX, secondary correlations, and salary

| Construction | Entries | Field share | Share of top 1% | Top-1% rate | Paid-finish rate | Our entries |
|---|---|---|---|---|---|---|
| RB | 353,245 | 42.5% | 53.0% | 1.3% | 22.3% | 5 |
| TE | 177,548 | 21.4% | 16.0% | 0.8% | 21.9% | 6 |
| WR | 300,235 | 36.1% | 31.0% | 0.9% | 18.6% | 9 |

RB FLEX had the strongest top-1% association. TE FLEX paid almost as often as RB FLEX, despite having a lower top-1% rate. This is an example of cashing and extreme-tail success favoring different constructions. Our mix was five RB, nine WR, and six TE FLEX lineups.

Secondary opposing-team mini-stacks outside the QB game showed only a small association: 51.1% of the field versus 52.7% of the top 1%. RB paired with its own defense did not show a positive signal on this slate: 14.8% of the field versus 12.2% of the top 1%. Rostering offense against one's selected defense was associated with a lower top-1% rate, 0.59% versus 1.04%, but these are observational comparisons.

Salary use was much less ambiguous descriptively: **96.4% of top-1% entries left $500 or less**, versus 94.7% of the field. Entries leaving more than $2,000 had only a 0.15% top-1% rate and 6.92% paid rate. This does not justify forcing exactly $50,000; it argues against sacrificing substantial projected value merely to create uniqueness in Classic.

### 4.4 Ownership and contrarianism

| Construction | Entries | Field share | Share of top 1% | Top-1% rate | Paid-finish rate | Our entries |
|---|---|---|---|---|---|---|
| Q1 low | 207,757 | 25.0% | 10.8% | 0.4% | 14.7% | 11 |
| Q2 | 207,760 | 25.0% | 17.9% | 0.7% | 17.6% | 7 |
| Q3 | 207,754 | 25.0% | 31.8% | 1.3% | 23.9% | 2 |
| Q4 high | 207,757 | 25.0% | 39.5% | 1.6% | 27.2% | 0 |

The highest-ownership quarter generated 39.5% of top-1% entries and paid at about 27.24%, while the lowest quarter generated 10.8% and paid at about 14.70%. This describes this slate's outcomes, not a mandate to maximize ownership.

Our average ownership sum was **89.65 percentage points**, versus **112.11** for the field, **123.72** in the top 1%, and **118.68** among paid entries. Only one of our lineups had as few as one sub-5% player; 16/20 had at least three. The archive does not support forcing additional low-owned plays into an already differentiated Classic portfolio.

There is a useful exception: the outright winning lineup had an ownership sum of 100.69 and three sub-5% players. A moderately contrarian winner can coexist with a chalkier overall top-1% cohort. Copying only the winner would obscure the much broader distribution of successful lineups.

## 5. Showdown: game-specific shapes, Captain choice, and paid finishes

### 5.1 Team split: top 1% and cashing diverge

Each cell below is **field share → top-1% share → paid-entry share**, among submitted lineups.

| Game | 3–3 | 4–2 | 5–1 |
|---|---|---|---|
| NE–SEA, Sep 9 | 38.7% → 56.2% → 37.1% | 47.7% → 42.0% → 48.1% | 13.5% → 1.7% → 14.8% |
| SF–LAR, Sep 10 | 31.2% → 8.5% → 38.1% | 48.1% → 36.3% → 46.6% | 20.7% → 55.2% → 15.4% |
| DAL–NYG, Sep 13 | 35.4% → 54.3% → 43.8% | 46.5% → 35.0% → 46.5% | 18.1% → 10.7% → 9.7% |
| DEN–KC, Sep 14 | 34.8% → 16.2% → 27.4% | 47.6% → 41.9% → 44.2% | 17.5% → 41.9% → 28.4% |

- **NE–SEA:** 3–3 had a 1.45× top-1% lift. The 5–1 split paid reasonably often but rarely reached the top 1%.
- **SF–LAR:** 5–1 had a 2.67× top-1% lift, yet its paid rate was only 15.75%, compared with 25.82% for 3–3. A construction can carry more extreme upside and still cash less often.
- **DAL–NYG:** 3–3 had a 1.53× tie-inclusive top-1% lift. Both distinct first-place lineups were 4–2. The shape that produced the winner was not the most overrepresented shape across the whole top cohort.
- **DEN–KC:** 5–1 had a 2.39× top-1% lift and a 34.26% paid rate. Its first-place lineup had five Kansas City players and one Denver player.

The 4–2 split was roughly 47–48% of three representative fields and 46.5% of DAL–NYG. It was below its field share in the top-1% cohort in all four games. That is worth investigating as a popular default, but four games do not justify excluding it. Several first-place lineups used it, and unique-lineup weighting moves DEN–KC's 4–2 lift from 0.88× to approximately 1.03×.

**Sensitivity:** fractional boundary-tie weighting leaves 5–1 strongly positive in SF–LAR and DEN–KC and negative in NE–SEA/DAL–NYG. DAL–NYG's 3–3 lift falls from 1.53× to 1.25× because a large tied score group crosses the cutoff, but its direction remains positive. Counting distinct lineups once also preserves these broad 3–3/5–1 conclusions.

### 5.2 Captain position varies with the realized scoring route

| Game | Largest Captain group in top 1% | Field share | Top-1% share | Paid-entry share | Paid rate for this Captain position |
|---|---|---|---|---|---|
| NE–SEA, Sep 9 | WR | 36.8% | 84.6% | 43.0% | 24.6% |
| SF–LAR, Sep 10 | QB | 16.3% | 40.7% | 21.6% | 28.1% |
| DAL–NYG, Sep 13 | TE | 6.9% | 44.9% | 13.3% | 51.7% |
| DEN–KC, Sep 14 | RB | 24.1% | 88.6% | 50.1% | 43.9% |

Captain position should be a consequence of scoring scenarios and salary opportunity cost. This sample does not support a fixed QB/RB/WR/TE Captain mix. In NE–SEA, 92.8% of top-1% entries used a Captain owned at least 10%; in DEN–KC, every top-1% entry did. DAL–NYG instead had a major contribution from Isaiah Likely at approximately 4% Captain ownership. A low-owned Captain is useful only when the player has a credible route to the relevant score.

### 5.3 Quarterbacks, kickers, and defenses

Shares below again compare the submitted field with top-1% and paid entries. “Two QB” counts rostered QB-position players; the overwhelming majority are the two starters, with a small number of backup-QB constructions also present.

| Game | Two QB: field → top 1% → paid | Any kicker: field → top 1% → paid | Any defense: field → top 1% → paid |
|---|---|---|---|
| NE–SEA, Sep 9 | 33.7% → 3.6% → 15.6% | 37.7% → 44.9% → 45.7% | 31.8% → 67.7% → 56.9% |
| SF–LAR, Sep 10 | 28.6% → 0.8% → 17.8% | 43.6% → 67.6% → 47.5% | 32.5% → 40.7% → 33.5% |
| DAL–NYG, Sep 13 | 44.6% → 64.8% → 53.8% | 43.2% → 0.1% → 37.0% | 23.2% → 5.3% → 16.9% |
| DEN–KC, Sep 14 | 46.8% → 44.5% → 45.7% | 43.3% → 17.7% → 45.6% | 31.1% → 81.9% → 37.6% |

The two-QB story changes sharply: Sam Darnold scored 0.52 FLEX points in NE–SEA, Matthew Stafford 5.10 in SF–LAR, and both QB constructions were rare in those top cohorts. Two quarterbacks worked much better in DAL–NYG. A blanket “both starting QBs” rule would have captured only one of these game patterns well.

Kickers appeared in 44.9% of NE–SEA's and 67.6% of SF–LAR's top-1% entries, but only 0.1% of DAL–NYG's. For DEN–KC, kicker use was much more common among paid entries than in the top 1%. Excluding the position altogether discards plausible paths to cashing and to winning on some games.

Defenses were present in 67.7% of NE–SEA's and 81.9% of DEN–KC's top-1% entries, versus only 5.3% of DAL–NYG's. Our zero-defense exposure across **all 51 Showdown entries** is therefore a coverage concern. The right response is to represent defensive scoring and game scripts, then evaluate the resulting portfolios. This archive cannot identify a universally optimal defense minimum.

### 5.4 Player coverage explains important failures

Field/top/paid shares here combine Captain and FLEX into person exposure. Our exposure uses the full portfolio for that game; comparison cohorts use the representative contest.

| Game | Player | Our exposure | Field | Top 1% | Paid |
|---|---|---|---|---|---|
| NE | Seahawks | 0.0% | 21.4% | 57.4% | 41.9% |
| SF | Brock Purdy | 27.3% | 58.0% | 99.5% | 93.2% |
| SF | Matthew Stafford | 72.7% | 59.4% | 0.8% | 18.9% |
| DAL | Isaiah Likely | 0.0% | 31.5% | 100.0% | 67.2% |
| DAL | George Pickens | 65.0% | 45.8% | 6.4% | 15.5% |
| DEN | Kenneth Walker III | 0.0% | 58.1% | 100.0% | 100.0% |
| DEN | Chiefs | 0.0% | 14.8% | 81.9% | 31.3% |

**DEN–KC is the clearest failure to diagnose.** Kenneth Walker III scored 37.10 FLEX points and 55.65 Captain points. Every one of the mini-MAX's 50,084 paid entries included him, while all 18 of our game entries omitted him. The best of the 99,349 observed submitted lineups without him scored 87.73, below the 92.30 paid threshold; its rank was 66,556. This is a statement about the observed field, not proof about all mathematically possible lineups.

**DAL–NYG:** Isaiah Likely appeared in all 722 top-1% entries and 67.2% of paid entries, but in none of ours. Conversely, George Pickens appeared in 65% of our entries but just 6.4% of the top 1% and 15.5% of paid entries. A revised team split alone cannot repair a missing scorer or an overconcentrated failing scorer.

These facts point to a review order: verify player identity and availability; inspect projected opportunities/scoring; inspect which eligible players and combinations reach the candidate bank; then inspect objective and allocation decisions. Existing local notes provide possible explanations, but this report does not treat an old diagnosis as verified causation for every submitted entry.

## 6. What first-place and top-1% lineups have in common

### 6.1 Representative winning constructions

| Slate/game | Winning score | Construction | Salary left | Copies of this lineup |
|---|---|---|---|---|
| Classic, Sep 13 | 273.98 | QB Jordan Love, QB+1, 0 bring-backs, RB FLEX | $0 | 1 |
| NE–SEA, Sep 9 | 101.02 | Jaxon Smith-Njigba CPT (WR), 3-3, 1 QB, 1 DST | $500 | 23 |
| SF–LAR, Sep 10 | 105.80 | Demarcus Robinson CPT (WR), 5-1, 1 QB, 0 DST | $500 | 1 |
| DAL–NYG, Sep 13 | 135.80 | Isaiah Likely CPT (TE), 4-2, 1 QB, 0 DST | $1,200 | 6 |
| DAL–NYG, Sep 13 | 135.80 | Isaiah Likely CPT (TE), 4-2, 2 QB, 0 DST | $1,600 | 1 |
| DEN–KC, Sep 14 | 124.61 | Kenneth Walker III CPT (RB), 5-1, 1 QB, 1 DST | $300 | 206 |

The Classic winner used Jordan Love with Christian Watson, plus Jahmyr Gibbs, Derrick Henry, D'Andre Swift, DJ Moore, Jalen Coker, Dallas Goedert, and Steelers DST. It spent all $50,000 and had no bring-back in the quarterback's game. Thus the outright winner is an important counterexample to treating the strongest cohort-level stacking association as a mandatory rule.

The NE–SEA winner captained Jaxon Smith-Njigba while omitting his own quarterback. The SF–LAR winner captained Demarcus Robinson with Brock Purdy. DAL–NYG's first-place score was reached by two different Isaiah Likely Captain lineups. DEN–KC's winner captained Kenneth Walker III with Mahomes, Rashee Rice, Travis Kelce, Chiefs DST, and Evan Engram.

**Commonality:** successful lineups captured the players through whom the actual scoring concentrated, while fitting the salary structure of that game. Their Captain positions, team splits, ownership levels, quarterback counts, and salary usage were not uniform. That favors scenario coverage and sound player projections over rigid lineup templates.

### 6.2 Ownership commonalities differ by mode

Classic's top cohort was broadly more owned than the field. Showdown had no consistent direction: SF–LAR's lowest ownership-sum quarter supplied about 62% of the top 1%, while DAL–NYG's highest quarter supplied about 63%. NE–SEA favored the middle quarters; DEN–KC spread across the middle and upper quarters. Low ownership is not a substitute for a path to points.

### 6.3 Duplication is a first-class outcome in Showdown

| Slate/game | Distinct lineups | Distinct / submitted | Entries with no duplicate | Median copies: field | Median copies: top 1% | Entries tied first |
|---|---|---|---|---|---|---|
| Classic, Sep 13 | 773,891 | 93.1% | 89.8% | 1 | 1 | 1 |
| NE–SEA, Sep 9 | 18,620 | 14.8% | 6.9% | 26 | 43 | 23 |
| SF–LAR, Sep 10 | 26,392 | 14.8% | 6.9% | 24 | 27 | 1 |
| DAL–NYG, Sep 13 | 12,064 | 20.4% | 9.8% | 14 | 32 | 7 |
| DEN–KC, Sep 14 | 31,932 | 13.5% | 6.5% | 30 | 107 | 206 |

For DAL–NYG, “20.4% distinct lineups per entry” and “9.8% of entries were unique” are different statistics. The latter is the relevant answer to whether an entrant shared a lineup. Preserve that distinction in future debriefs.

The DEN–KC mini-MAX's 206-way first-place tie is one football outcome and one roster, not 206 independent demonstrations of an archetype. The same winning roster also tied first in four other supplied DEN–KC tournaments. Exact returns require pooling the prizes across all occupied tied ranks and dividing correctly; dividing only the advertised first prize by 206 is wrong.

### 6.4 Salary left is a trade-off, not a shortcut to uniqueness

The representative Showdown winners left $500 in NE–SEA, $500 in SF–LAR, $1,200 or $1,600 in DAL–NYG, and $300 in DEN–KC. Median salary left among top-1% entries was $700, $300, $400, and $700 respectively. Many lineups still duplicated despite leaving salary.

There were no exact-$50,000 lineups in NE–SEA's or DEN–KC's top 1%, but they made up 29.5% of DAL–NYG's top cohort. This argues for modeling salary opportunity cost and duplication jointly, with multiple feasible constructions. It does not establish a universal Showdown salary cap below $50,000.

## 7. Classic versus Showdown: practical differences

| Dimension | Classic observation | Showdown observation | Modeling consequence |
|---|---|---|---|
| Independent evidence | One slate with 12 games | Four games, repeated across 25 contests | Separate models and validation units; do not train/test by contest row |
| Roster construction | QB/pass-catcher stacks and FLEX mix mattered | Captain identity, team split, and QB/K/DST combinations changed by game | Represent mode-specific joint construction |
| Extreme scores versus paid finishes | Larger stacks/RB FLEX were more prominent near the top | A 5–1 split could improve top-1% representation while reducing cash rate | Use the actual payout objective rather than one ranking for every contest |
| Uniqueness | 89.8% of submitted entries were singletons | Only 6.5–9.8% were singletons in representative fields | Duplication has much greater practical importance in Showdown |
| Ownership | Top-1% cohort generally chalkier; our entries much less owned | Direction varied by game and Captain role | Calibrate ownership and avoid automatic contrarian quotas |
| Salary | 96.4% of top-1% entries left at most $500 | Winners and top cohorts used varied remaining salary | Keep salary usage flexible where value/duplication justify it |
| Our account | 20% paid, −64.0% ROI | 9.8% paid, +15.6% ROI, driven by two entries | Do not infer a mode advantage from aggregate ROI |

## 8. Recommended work, in priority order

These are proposals arising from the report; no production changes were implemented.

### Priority 1: fix measurement and diagnose coverage

1. **Validate ownership inputs as probabilities.** Record source, timestamp, contest/slate, identity, role, and units. Reject impossible QB/DST/Captain totals; validate complete role/position mass and the unavailable-player mask. Resolve the archived Classic source interpretation before using or fitting its values.
2. **Create one frozen prediction-to-outcome record per run and contest.** Store the pre-lock salary/entry snapshots, model versions, projections, ownership vector, candidate bank, submitted Entry IDs, contest facts, and later standings/history. Preserve late-swap versions and identify the exact submitted lineup. This enables truthful attribution and chronological evaluation.
3. **Trace the missing Showdown scorers and zero-defense portfolio.** Review Likely, Walker, and defensive scoring through the full eligibility→projection→candidate→selection chain. Flag a material market/field-consensus player absent from the candidate bank or selected portfolio for review. A flag prompts diagnosis; it does not force retrospective winners into every future lineup.
4. **Use history to attach the actual objective to every contest.** Satellites, boosters, winner-take-all, and ordinary GPPs have different paid fractions. Do not apply a generic cash-game policy to one-seat satellites. Obtain full payout/award ladders when optimizing expected dollars or ticket awards.

### Priority 2: test ownership and field challengers

5. **Use the salary benchmark as a minimum useful reference.** Add validated active roles and projection/value features, then evaluate Captain and FLEX separately. Report held-out absolute error, ownership-band bias, top-player recall, and mass conservation. Require better performance across new games, not just a lower fitted error on these four.
6. **Fit one coherent Classic FLEX distribution.** Use it to inform position ownership totals and field construction. The current ownership and sampler assumptions differ, and actual TE FLEX was substantially more common than either reflects.
7. **Condition fields on contest characteristics and player combinations.** Use restrained, pooled estimates for small contests. Validate conditional teammate/opponent pair rates, team splits, QB counts, salary-left distributions, and duplication after constructing legal lineups. Exact field reproduction on training games is insufficient; score new games.

### Priority 3: test strategy changes without turning hindsight into rules

8. **Classic:** compare a portfolio that preserves competitive high-owned cores with the current contrarian mix. Include QB+1, QB+2, and selected QB+3 game scenarios; test bring-back choices by game rather than globally. Measure extreme-tail reach and payout together.
9. **Showdown:** test diversified 3–3/4–2/5–1 scenario coverage, realistic defense/kicker scoring, and both one- and two-QB constructions. Choose mixes from pre-lock game/player distributions. Avoid immediate rules such as “always 5–1,” “always two QBs,” “no kickers,” or “Captain below 5%.”
10. **Optimize portfolio allocation for each contest's economics.** Compare probability of reaching the paid threshold, top-tail outcomes, expected prizes when supported, and duplicated-roster payout dilution. Examine portfolio dependence as well as individual lineup quality. A shape with a high top-1% rate need not maximize min-cash frequency or portfolio returns.

### Suggested evaluation design

- Group all contests and entries from the same slate/game together. Use chronological training and validation; keep a genuinely untouched future evaluation period.
- Treat new independent slates as the information budget. A practical first milestone is several dozen Showdown games and several weeks of Classic slates, followed by an uncertainty assessment. That is a collection target, not an automatic sample-size guarantee.
- Freeze the proposed changes, feature definitions, and success metrics before evaluating the next batch. Limit simultaneous strategy experiments and retain a champion/challenger comparison.
- Separate **ownership quality**, **field-construction quality**, **projection calibration**, **candidate coverage**, and **realized account economics**. One good ROI result does not validate all five.
- With reliable payout ladders, test allocation on common simulated game outcomes and an independently evaluated scenario set. Keep “calibrated EV” unavailable until the predictive and settlement pieces have prospective evidence.

## 9. Corrections to earlier local interpretations

The earlier DAL–NYG debrief discussed a live snapshot. The current inbox file for contest 195520918 is final: its leading score is 130.10 and time remaining is zero. Its first-quarter rankings should not be used as final performance evidence.

The DEN–KC run record cites DAL–NYG 4–2 representation of 64.7% in the top 1%. I cannot reproduce that figure from the current export and matching salary-team map: the current tie-inclusive figure is **35.0%**, while 3–3 accounts for **54.3%**. Both distinct first-place lineups remain 4–2. This report uses the currently verified bytes and team assignments rather than carrying the old percentage forward.

Likewise, “flat-prize satellite” does not imply a low-variance, floor-only lineup objective when only 0.42–4.26% of entries reach awards. Paid-place evidence from the supplied history resolves that ambiguity.

## 10. Limits on the conclusions

- This is one week of NFL outcomes, selected from contests we entered and downloaded. It is not a representative sample of all DraftKings contests or all player skill levels.
- The same users, lineups, and game outcomes appear across contests. Entry counts are not independent sample sizes for strategy inference.
- Final ownership is a label for future forecasting, not a pre-lock feature. All retrospective player “must-haves” are hindsight descriptions.
- Only one Classic slate is available. Associations with stacking, ownership, and FLEX may change with salaries, value injuries, and the games on another slate.
- For the field, a paid finish is inferred from actual paid ranks and ties. For our entries, winnings are observed and reconciled. Full peer payouts and ticket tie treatment are not established for most contests.
- An observed absent-player failure does not prove its specific cause or the best counterfactual portfolio. No exhaustive full-slate optimum, calibrated expected return, or general future win probability is claimed.
- The standings show final status at export time; no later scoring-correction feed was checked.

**Conclusion:** the archive is most valuable as the start of a disciplined ownership/field calibration corpus and as a diagnostic of missing scoring paths. It supports fixing source interpretation, player coverage, payout objectives, and duplicate-aware measurement now. It supports testing stack and ownership policies prospectively, with game-specific variation preserved.

## Appendix A. Complete contest inventory and account reconciliation

“Paid places” is the count in the user-supplied history, before expanding boundary ties. “Our best rank” is the platform rank, which may be tied. Short names below identify contest format; exact full names follow in Appendix B.

| Contest ID | Group | Format | Field | Paid places | Fee | Our entries | Our paid | Our return | Our best rank |
|---|---|---|---|---|---|---|---|---|---|
| 193028206 | CLASSIC | Other GPP | 832,342 | 173,275 | $5.00 | 20 | 4 | $36.00 | 23,887 |
| 193391013 | NE | Other GPP | 126,020 | 26,495 | $20.00 | 2 | 2 | $60.00 | 17,298 |
| 195379585 | SF | Unspecified $0.25 contest | 237 | 55 | $0.25 | 2 | 0 | $0.00 | 145 |
| 195379668 | SF | Satellite | 47 | 2 | $0.25 | 1 | 0 | $0.00 | 15 |
| 195384501 | SF | Satellite | 71 | 1 | $0.25 | 2 | 0 | $0.00 | 55 |
| 195390867 | SF | 20-max GPP | 83,234 | 22,471 | $1.00 | 1 | 0 | $0.00 | 75,462 |
| 195390868 | SF | 150-max GPP | 178,359 | 37,455 | $0.50 | 1 | 0 | $0.00 | 138,669 |
| 195390870 | SF | Other GPP | 47,562 | 11,405 | $0.10 | 2 | 1 | $0.20 | 4,845 |
| 195390889 | SF | Single-entry GPP | 9,512 | 2,247 | $1.00 | 1 | 1 | $2.00 | 604 |
| 195507184 | SF | 40x booster | 237 | 5 | $0.25 | 1 | 0 | $0.00 | 137 |
| 195520918 | DAL | Winner take all | 475 | 1 | $0.25 | 1 | 0 | $0.00 | 462 |
| 195521582 | DAL | Satellite | 237 | 1 | $0.10 | 7 | 0 | $0.00 | 52 |
| 195521607 | DEN | Satellite | 95 | 1 | $0.25 | 2 | 0 | $0.00 | 59 |
| 195526142 | DAL | 20-max GPP | 59,453 | 15,950 | $1.00 | 1 | 0 | $0.00 | 42,251 |
| 195526144 | DAL | Other GPP | 35,671 | 8,550 | $0.25 | 2 | 1 | $0.50 | 5,220 |
| 195526145 | DAL | Other GPP | 35,671 | 8,545 | $0.10 | 2 | 0 | $0.00 | 24,851 |
| 195526163 | DAL | Single-entry GPP | 5,945 | 1,543 | $1.00 | 1 | 0 | $0.00 | 5,205 |
| 195526229 | DEN | 150-max GPP | 237,812 | 49,940 | $0.50 | 1 | 0 | $0.00 | 221,219 |
| 195526255 | DEN | 20-max GPP | 89,179 | 24,076 | $1.00 | 1 | 0 | $0.00 | 71,167 |
| 195526256 | DEN | Other GPP | 59,453 | 14,265 | $0.25 | 2 | 0 | $0.00 | 53,940 |
| 195526257 | DEN | Other GPP | 59,453 | 14,240 | $0.10 | 2 | 0 | $0.00 | 35,780 |
| 195526271 | DEN | Single-entry GPP | 8,917 | 2,305 | $1.00 | 1 | 0 | $0.00 | 4,517 |
| 195641911 | DAL | 40x booster | 237 | 5 | $0.25 | 1 | 0 | $0.00 | 223 |
| 195642262 | DAL | Satellite | 190 | 2 | $0.25 | 5 | 0 | $0.00 | 116 |
| 195663904 | DEN | Satellite | 237 | 1 | $0.10 | 7 | 0 | $0.00 | 102 |
| 195665148 | DEN | Satellite | 71 | 1 | $0.25 | 2 | 0 | $0.00 | 62 |

## Appendix B. Source provenance and reproducibility

### B.1 Immutable raw standings

Each archive contains one standings CSV. All 26 files were read in place. The following SHA-256 values bind the analyzed raw files; archives and their uncompressed CSVs were also distinguished during analysis.

| Contest ID | Exact contest name | Raw file | SHA-256 |
|---|---|---|---|
| 193028206 | NFL $3.5M Fantasy Football Millionaire [$1M to 1st] | [contest-standings-193028206.zip](<C:/Users/benja/Documents/Claude/nfl-dfs/data/standings/inbox/contest-standings-193028206.zip>) | 0cd410143f258cad86376ba8a211e0fd7eff2b663f896ccb49b16d78faaa5697 |
| 193391013 | NFL Showdown $2.25M Wednesday Kickoff Millionaire [$1M to 1st TD Throne Eligible] (NE @ SEA) | [contest-standings-193391013.zip](<C:/Users/benja/Documents/Claude/nfl-dfs/data/standings/inbox/contest-standings-193391013.zip>) | ee264b8bd9c9b8195a835223752432d8d41f95f356e66ebc9c1ad016c047ba29 |
| 195379585 | NFL Showdown $0.25 Contest (SF vs LAR) | [contest-standings-195379585.zip](<C:/Users/benja/Documents/Claude/nfl-dfs/data/standings/inbox/contest-standings-195379585.zip>) | 57cba3146ef638e055d087e6111398da6d3fdfc1d8774617d692cb0697e75f0a |
| 195379668 | NFL Showdown SUPERSatellite to NFL 9-13 $5 Fantasy Football Millionaire [2x] (SF vs LAR) | [contest-standings-195379668.csv](<C:/Users/benja/Documents/Claude/nfl-dfs/data/standings/inbox/contest-standings-195379668.csv>) | c302f8ae07bbcca065da8f120013cb379374115f4efe6fde66ac1f4e4cb13905 |
| 195384501 | NFL Showdown Satellite to NHL 9-29 $15 Opening Night Puck Drop (SF vs LAR) | [contest-standings-195384501.zip](<C:/Users/benja/Documents/Claude/nfl-dfs/data/standings/inbox/contest-standings-195384501.zip>) | a1b7e2c51fec8bc641f27e94e60e5d5b3810816ddcaf32bea360897ad4a95bb3 |
| 195390867 | NFL Showdown $70K First Down [20 Entry Max] (SF vs LAR) | [contest-standings-195390867.zip](<C:/Users/benja/Documents/Claude/nfl-dfs/data/standings/inbox/contest-standings-195390867.zip>) | 327c3f91f2daa0daa405f556c4de446515a520c4235daf128031344984c39100 |
| 195390868 | NFL Showdown $75K mini-MAX [150 Entry Max] (SF vs LAR) | [contest-standings-195390868.zip](<C:/Users/benja/Documents/Claude/nfl-dfs/data/standings/inbox/contest-standings-195390868.zip>) | 0ef6d0a433336cef58079318976dc7b5f67856688442c49bb662e6c41559893f |
| 195390870 | NFL Showdown $4K Dime Package [Just $0.10!] (SF vs LAR) | [contest-standings-195390870.zip](<C:/Users/benja/Documents/Claude/nfl-dfs/data/standings/inbox/contest-standings-195390870.zip>) | 2e8739947eddd5db6da5b292258bdaf0d9ab0732fefac527a076685831bf35b4 |
| 195390889 | NFL Showdown $8K Daily Dollar [Single Entry] (SF vs LAR) | [contest-standings-195390889.zip](<C:/Users/benja/Documents/Claude/nfl-dfs/data/standings/inbox/contest-standings-195390889.zip>) | e3956d4481d5ef1d260404980b780d6b42d54d67f5feaa030c1c2b73437479fc |
| 195507184 | NFL Showdown 40x Micro Booster [Top 5 Win $10] (SF vs LAR) | [contest-standings-195507184.zip](<C:/Users/benja/Documents/Claude/nfl-dfs/data/standings/inbox/contest-standings-195507184.zip>) | 7dcf5fc9f4ad110dd8c181f01c6856549e35c091371b65c8b651147407e1a8d8 |
| 195520918 | NFL Showdown $0.25 Winner Take All [$100 to 1st] (DAL @ NYG) | [contest-standings-195520918.zip](<C:/Users/benja/Documents/Claude/nfl-dfs/data/standings/inbox/contest-standings-195520918.zip>) | 549da82ec3349a033c444a3443d4dbd3d58e9521af4470219df9a93d26a995df |
| 195521582 | NFL Showdown Satellite to NBA 10-20 $20 Opening Tip Off (DAL @ NYG) | [contest-standings-195521582.zip](<C:/Users/benja/Documents/Claude/nfl-dfs/data/standings/inbox/contest-standings-195521582.zip>) | 3f7a1fec37c6d8230fdf6e8a6cefef24a6017ff0eca4d64be2cdaf123db83e02 |
| 195521607 | NFL Showdown Satellite to NBA 10-20 $20 Opening Tip Off (DEN @ KC) | [contest-standings-195521607.zip](<C:/Users/benja/Documents/Claude/nfl-dfs/data/standings/inbox/contest-standings-195521607.zip>) | 586b49dfe89c0f7b78255c0ecc1d8e6bc0bbb9c59649e352a3c6d28ddb2c9738 |
| 195526142 | NFL Showdown $50K First Down [20 Entry Max] (DAL @ NYG) | [contest-standings-195526142.zip](<C:/Users/benja/Documents/Claude/nfl-dfs/data/standings/inbox/contest-standings-195526142.zip>) | 57a55a8cd1974bfb70fc5a2e42856146e64edc5d419ec4684d78e4fe9441e692 |
| 195526144 | NFL Showdown $7.5K Quarter Jukebox [Just $0.25!] (DAL @ NYG) | [contest-standings-195526144.zip](<C:/Users/benja/Documents/Claude/nfl-dfs/data/standings/inbox/contest-standings-195526144.zip>) | 6f7124bac30ff4969a105b4a971b183357907c5a586419499d0fe2d577cfe656 |
| 195526145 | NFL Showdown $3K Dime Package [Just $0.10!] (DAL @ NYG) | [contest-standings-195526145.zip](<C:/Users/benja/Documents/Claude/nfl-dfs/data/standings/inbox/contest-standings-195526145.zip>) | 9cb08c067fbdb12e9ce4c08f9103c2d2f31208ff3c3795cb655cef110ccff095 |
| 195526163 | NFL Showdown $5K Daily Dollar [Single Entry] (DAL @ NYG) | [contest-standings-195526163.zip](<C:/Users/benja/Documents/Claude/nfl-dfs/data/standings/inbox/contest-standings-195526163.zip>) | b2f3bc11feea31add2247e2bb7521bce04001a71d474f8a36180179f9b3c1ad2 |
| 195526229 | NFL Showdown $100K mini-MAX [150 Entry Max] (DEN @ KC) | [contest-standings-195526229.zip](<C:/Users/benja/Documents/Claude/nfl-dfs/data/standings/inbox/contest-standings-195526229.zip>) | c88213a0b224c77178afa2e62bd970e9e5f08e666b82a8200436366b26e406fb |
| 195526255 | NFL Showdown $75K First Down [20 Entry Max] (DEN @ KC) | [contest-standings-195526255.zip](<C:/Users/benja/Documents/Claude/nfl-dfs/data/standings/inbox/contest-standings-195526255.zip>) | db5f47ccd783762c8f2d18909eff225e01e63ac9a58375b2e635fca1252194c6 |
| 195526256 | NFL Showdown $12.5K Quarter Jukebox [Just $0.25!] (DEN @ KC) | [contest-standings-195526256.zip](<C:/Users/benja/Documents/Claude/nfl-dfs/data/standings/inbox/contest-standings-195526256.zip>) | fff2ba8f5f0194019aaa981f67ada484706e99c29fc28277ab1071a435b68765 |
| 195526257 | NFL Showdown $5K Dime Package [Just $0.10!]  (DEN @ KC) | [contest-standings-195526257.zip](<C:/Users/benja/Documents/Claude/nfl-dfs/data/standings/inbox/contest-standings-195526257.zip>) | 49bb305577a511a2a71509e40ad184b0c39c710e1bdfde787758fc7533720f56 |
| 195526271 | NFL Showdown $7.5K Daily Dollar [Single Entry] (DEN @ KC) | [contest-standings-195526271.zip](<C:/Users/benja/Documents/Claude/nfl-dfs/data/standings/inbox/contest-standings-195526271.zip>) | c0d5ad94f7586ef0d972e3ff797854c75ef671aa3eedf43c8be75a89d0c7decc |
| 195641911 | NFL Showdown 40x Micro Booster [Top 5 Win $10] (DAL @ NYG) | [contest-standings-195641911.zip](<C:/Users/benja/Documents/Claude/nfl-dfs/data/standings/inbox/contest-standings-195641911.zip>) | 49168c79000f466061f0161136dcd38117d71577b0ab1aa7d71d4bb693d61ab6 |
| 195642262 | NFL Showdown SUPERSat to $20 NFL Fantasy Football Millionaire [2x] (DAL @ NYG) | [contest-standings-195642262.zip](<C:/Users/benja/Documents/Claude/nfl-dfs/data/standings/inbox/contest-standings-195642262.zip>) | 00b005b95b5d93e8c20f6c9cdedc410509a4e9f9fef3371c0daac1962cb2222e |
| 195663904 | NFL Showdown Satellite to $20 NFL Fantasy Football Millionaire (DEN @ KC) | [contest-standings-195663904.zip](<C:/Users/benja/Documents/Claude/nfl-dfs/data/standings/inbox/contest-standings-195663904.zip>) | 010502b305d1eeca7f0267664ac9fd58f6dbcf770c32f38d116588a670584e77 |
| 195665148 | NFL Showdown Satellite to NHL 9-29 $15 Opening Night Puck Drop (DEN @ KC) | [contest-standings-195665148.zip](<C:/Users/benja/Documents/Claude/nfl-dfs/data/standings/inbox/contest-standings-195665148.zip>) | b240d4254111302f2b7eefa509c27259e0998226e853a1a873b625c79de72a2d |

### B.2 Supporting evidence

- **Account/contest history:** [draftkings-contest-entry-history.csv](<C:/Users/benja/Downloads/draftkings-contest-entry-history.csv>); SHA-256 `84ce7a814de29f8939e5ecf7b60a5f32844dfe7c8d079910bb5c1132c9cba6d4`. Join keys: `Contest_Key` and `Entry_Key`; `Places_Paid` defines the paid threshold. Fields for cash/ticket winnings, fees, ranks, scores, date, and field size were reconciled.
- **Classic ownership research input:** [data/runs/20260913-week1-portfolio/build_portfolio.py](<C:/Users/benja/Documents/Claude/nfl-dfs/data/runs/20260913-week1-portfolio/build_portfolio.py>); SHA-256 `46b3cf1c11af0e7691fccf7cc7514c44f47ced458f1854aecd8a90dbf384a33c`. The dictionary was read as data without executing the build.
- **Complete payout ladder available:** [data/runs/20260909-showdown-ne-sea-live-2206z/contest/payouts_operator_supplied_193391013.csv](<C:/Users/benja/Documents/Claude/nfl-dfs/data/runs/20260909-showdown-ne-sea-live-2206z/contest/payouts_operator_supplied_193391013.csv>); SHA-256 `b4cbaf72d7d8746278b1619cbd1d784b18c432c3f4cdd71bdcc9d1834a0f8b38`. Other contests use history's paid-place counts and observed owned winnings, not guessed prize ladders.
- **Current implementation reviewed:** [src/nfl_dfs/ownership.py](<C:/Users/benja/Documents/Claude/nfl-dfs/src/nfl_dfs/ownership.py>), [src/nfl_dfs/field.py](<C:/Users/benja/Documents/Claude/nfl-dfs/src/nfl_dfs/field.py>), [src/nfl_dfs/selection.py](<C:/Users/benja/Documents/Claude/nfl-dfs/src/nfl_dfs/selection.py>), and relevant ownership calls in [src/nfl_dfs/cli.py](<C:/Users/benja/Documents/Claude/nfl-dfs/src/nfl_dfs/cli.py>).
- **Earlier interpretations checked:** [docs/DEBRIEF_2026-09-13_DAL_NYG_contest_195520918.md](<C:/Users/benja/Documents/Claude/nfl-dfs/docs/DEBRIEF_2026-09-13_DAL_NYG_contest_195520918.md>) and [docs/RUN_RECORD_20260914_DEN_KC.md](<C:/Users/benja/Documents/Claude/nfl-dfs/docs/RUN_RECORD_20260914_DEN_KC.md>). Their conclusions were not used as outcome labels.

Salary/team/position sources used for the final joins:

| Group | Salary source | SHA-256 |
|---|---|---|
| CLASSIC | [data/runs/20260913-week1-portfolio/inputs/DKSalaries.csv](<C:/Users/benja/Documents/Claude/nfl-dfs/data/runs/20260913-week1-portfolio/inputs/DKSalaries.csv>) | 3a1657170f4c92cd8db00aad7404e8913f377d8bc34d72b864152b71c8957c08 |
| NE | [data/runs/20260909-showdown-ne-sea/inputs/DKSalaries_NE_SEA.csv](<C:/Users/benja/Documents/Claude/nfl-dfs/data/runs/20260909-showdown-ne-sea/inputs/DKSalaries_NE_SEA.csv>) | 6bc5209f6e2f9e3e44e36efe608fe28dfe3b52248c11e6325001dea73e6e4a73 |
| SF | [data/runs/20260910-showdown-sf-lar/inputs/DKSalaries_SF_LAR.csv](<C:/Users/benja/Documents/Claude/nfl-dfs/data/runs/20260910-showdown-sf-lar/inputs/DKSalaries_SF_LAR.csv>) | c394480831cb127a0bf1de2e95ef00c5758b3c1763bbeb23aee4f911d385072e |
| DAL | [Claude outputs/DKEntries_DAL_NYG_20lineups_REVIEW_v6.csv](<C:/Users/benja/Documents/Claude/nfl-dfs/Claude outputs/DKEntries_DAL_NYG_20lineups_REVIEW_v6.csv>) | a96f9e704f773d11802679acb6aceb45de5d67a369640653222be2277d540f04 |
| DEN | [DKEntries_DEN_KC_18lineups_v6.csv](<C:/Users/benja/Documents/Claude/nfl-dfs/DKEntries_DEN_KC_18lineups_v6.csv>) | 4f5ab44f7003f5cd9dbad20bd0981d7ae9d08f48c06f557c48fa0b3231321204 |

The DAL and DEN files include a separate embedded salary table. Only salary-table rows supplied player metadata; only numeric reserved-entry rows supplied owned Entry IDs. Template instructions and unrelated cells were ignored. Player-team facts are taken from these 2026 slate records, not from remembered historical NFL rosters.

### B.3 Calculation details and checks

1. Read each CSV with BOM-safe decoding; separate the entry columns from the side-by-side player ownership/points columns. Ignore empty lineup cells only for roster analysis.
2. Reconcile unique Entry IDs, field sizes, final status, two-decimal scores, platform ranks, and history. Preserve rank ties; do not rank raw floating-point noise.
3. Split lineups by slot markers rather than assuming text order. Classic exports can begin with DST/FLEX even though the upload template begins with QB. Resolve player names within the matched slate and role. Trim surrounding whitespace consistently, including defenses.
4. Recount ownership from complete lineups. Classic exported player rows can split the same person across FLEX and base position; aggregate these. In contest 195379668, 11 used Captain identities lack ownership/point rows in that export. Contest 195665148 omits the used Noah Gray Captain row. Reconstructed lineup counts supply the ownership labels; the same game's other exports supply missing player/role points. No player outcome was invented or imputed from a projection.
5. Reconstructed score checks pass for all 1,865,110 submitted lineups. Where side-table values are present, ownership differences are within 0.01 percentage point, consistent with limited export precision. Roster-count totals equal nine or six times the submitted-entry fraction; normalized Captain/FLEX training totals equal one/five.
6. Compute role-aware canonical lineups, multiplicities, salaries, stack features, and contest-specific outcome flags. Require rank/score consistency, exact ID uniqueness, and salary totals no greater than $50,000 before using the data.
7. For fractional top-tail sensitivity, with cutoff `k`, tied group starting at rank `r`, and size `t`, give each entry weight `min(1, max(0, (k-r+1)/t))`. This fixes the cohort mass at exactly `k` without selecting arbitrary entries within a tie. Unique-lineup sensitivity retains the same entry-rank score threshold and gives each roster one observation.
8. Compare one representative field per slate/game for main construction findings. Own exposure is computed from the actual submitted lineups in all matched contests. ROI is reconstructed from history's observed winnings and fees; no estimated prizes enter our account results.
9. All calculation intermediates were kept outside the repository in a temporary analysis directory. Only this Markdown report was added to the workspace. Raw inputs and existing work were left intact.

This report contains the population definitions, source hashes, benchmark recipe, and denominators needed to reproduce the findings. Rounded displayed percentages may not sum to exactly 100%.

**Final verification:** independently recounted all raw CSV entry rows and rejoined owned results using decimal arithmetic. Confirmed 1,870,717 rows, 5,607 blank lineups, 71 owned entries, $154.25 fees, and $98.70 winnings. Category totals, tie weights, ownership masses, and source hashes reconciled. All 26 raw exports, the supplied history, and every local entry/salary source hashed during intake remain unchanged.
