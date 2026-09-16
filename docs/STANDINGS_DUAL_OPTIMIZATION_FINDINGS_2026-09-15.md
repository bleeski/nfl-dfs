# NFL standings research: contest ceiling and portfolio survival

**Prepared 2026-09-15.** Greenfield analysis of the 26 DraftKings contest exports in `data/standings/inbox`, joined to `draftkings-contest-entry-history.csv` (Downloads, SHA-256 `84ce7a81…9cba6d4`) and to the same-slate salary files, entry templates, submitted review CSVs, portfolio policies and run reports. Every calculation ran locally in Python on the device VM; nothing in the repo was modified except the addition of this file. The same-day report `docs/STANDINGS_GREENFIELD_FINDINGS_2026-09-15.md` was read only after the analysis below was finished; where the two overlap they agree on every shared number, and section 8 treats its recommendations as hypotheses.

The frame is the dual objective: at the contest level, the probability that an entry clears the field's top 1%, top 0.1% and first place, net of ties and duplication; at the portfolio level, the probability and severity of slate-level loss. Historical standings give one realized outcome per slate. Five slate groups (one Classic slate, four Showdown games) cannot estimate a ceiling distribution or a ruin probability. What they can do, and what this report does, is measure the field, measure us against it, trace what produced our lineups, and separate the patterns that held in all four games from the ones that flipped.

## 1. Executive findings

**1. The engine's objective cannot express either arm of the dual objective, and the caps that stand in for it produce single-thesis portfolios.** Every engine-built portfolio in the corpus (NE@SEA, SF@LAR, DAL@NYG, DEN@KC) was selected under `MAXIMIZE_PRIOR_POINTS_OF_THE_EXPECTED_STAT_LINE` with exposure caps as the only diversification control. The DEN@KC v6 policy raised Bo Nix's combined-exposure cap to 0.95 and Mahomes's to 0.89 to make the solve feasible; the shipped portfolio had Nix in 17 of 18 lineups, Kelce in 14, Mahomes in 13, Waddle in 11, and a mean pairwise overlap of 3.46 players out of 6. Seventeen of 18 finished below the field median; zero paid. In the reference contest, field lineups with Nix and without Kenneth Walker III paid at 0.0% (0 of 84,483; the best of the 99,349 lineups without Walker scored 87.73 against a 92.30 cash line). Our 18 were all in that cell. Evidence: byte-exact provenance (section 2.3), policy JSON, run record, standings. Strength: high for the mechanism, one game for the outcome.

**2. Portfolio concentration is measurably a ruin mechanism in this field, not only in ours.** Across 8,007 user-portfolios with 10 or more entries in the four reference Showdown contests, portfolios with 85% or more of entries on one player had zero-paid rates of 16.1%, 18.9%, 6.7% and 11.1% (DEN@KC, SF@LAR, DAL@NYG, NE@SEA) against 3.7%, 1.6%, 2.7% and 7.8% for everyone else (1.4x to 12x), and a lower probability of at least one top-1% finish in all four games than the 70-85% band (DEN@KC 0.22 vs 0.50; SF@LAR 0.11 vs 0.50; DAL@NYG 0.17 vs 0.19; NE@SEA 0.19 vs 0.27). Our max single-player share was 0.94 (DEN@KC), 0.80 (DAL@NYG), 0.73 (SF@LAR), 1.00 (NE@SEA). Strength: four independent games, thousands of portfolios per game, direction consistent; confounded by entrant skill.

**3. Only three Showdown construction features helped the top 1% in all four games, and all three also reduced the below-median rate.** Exactly one pass catcher stacked with the rostered QB (top-1% lift 1.39 to 2.08 across games, geometric mean 1.63, below-median lift 0.72 to 0.85), $1 to $500 of salary left (lift 1.12 to 1.35), and one QB (lift ≥1 in three games, 0.73 in DAL@NYG). Consistently harmful in all four: three or more pass catchers with the QB (max lift 0.57), more than $3,000 left (max 0.73), zero QBs (geometric mean 0.01), unique lineups (max 0.56, and a higher below-median rate in all four), two or more sub-5%-owned players (max 0.46), a captain owned under 3% (0.00 to 0.19 in three games). Everything else, including captain position, team split, two-QB builds, kickers, defenses and chalk versus contrarian ownership sums, changed sign across games. Strength: four games; the stable set is small and structural, the volatile set is where the ceiling actually lives.

**4. Setting the next game's policy from the last game's standings is itself a ruin mechanism.** The DEN@KC run record derived its structure targets from the DAL@NYG standings (two QBs in 64.8% of the top 1%, kickers 0.1%, DST 5.3%) and shipped 12 two-QB lineups, zero kickers and zero defenses. In DEN@KC the winning lineup had one QB and a DST; DST=1 had a 2.87x top-1% lift and two-QB lineups reached the top 0.1% at 0.0%. The cross-game table in section 4.3 shows the same flip for the split (5-1 dead in NE@SEA and DAL@NYG, 2.6 to 2.8x in SF@LAR and DEN@KC) and for the chalkiest ownership band (0.00x in SF@LAR, 1.99x in DAL@NYG).

**5. In Showdown the top 1% is a duplicated cohort and first place is a shared prize.** Duplicated lineups (6 or more copies) made up 83% to 98% of top-1% entries in the large contests; unique lineups were 0.5% to 16%. In the NE@SEA $20 Millionaire, 23 entries tied for first with the same lineup and each received $54,065 instead of $1,000,000 (the only contest with a supplied payout ladder). The DEN@KC mini-MAX had 206 entries tied for first. Prize-weighted, unique lineups were 6.9% of the NE@SEA field and took 1.4% of the money. A ceiling objective that ignores duplication overstates first-place value by an order of magnitude in Showdown.

**6. The Week 1 Classic portfolio, 64% of the era's fees, has no engine provenance.** The 20 lineups that ran (byte-identical to `DKEntries_NFL_Week1_LATESWAP_FINAL.csv`) differ in every lineup from the 20 produced by `data/runs/20260913-week1-portfolio/build_portfolio.py`, and no C1/C2/C3 artifact exists for the slate. The only archived pre-lock ownership vector (an 86-player transcription of a public board) is not a probability distribution (QB ownership sums to 200.6%, DST to 186.5%) and correlated 0.18 with the final field. Account results for Week 1 cannot be attributed to any model version.

**7. Realized account results.** All-time NFL: 145 entries, 95 contests, 58 slate-days, $235.47 in fees, $136.60 back, no tickets, net −$98.87, 17 paid entries. The 2026 engine era (2026-09-09 to 09-14): 74 entries in 28 contests over four slate-days, $155.75 in fees, $98.70 back, −36.6% ROI, 9 paid, 0 top-1% finishes; 89.9% of fees sat in two contests. Showdown's +12.5% ROI is two $20 min-cashes in NE@SEA; the other 52 Showdown entries returned $2.70 on $15.75. Our 0 top-1% finishes in 71 entries is not distinguishable from random field draws (expected 0.7; P(0) ≈ 0.49 under independence), but our paid counts in DAL@NYG (1 of 20) and DEN@KC (0 of 18) are far below what 20 independent field draws produce (P(0 paid of 18) ≈ 1%), which is the signature of correlated entries rather than of bad luck.

## 2. Corpus and data quality

### 2.1 Inventory

| Item | Count / value |
|---|---|
| Contest exports in `data/standings/inbox` | 26 (25 `.zip`, 1 loose `.csv`); SHA-256 for each in appendix A |
| Entry rows | 1,870,717 (832,342 Classic; 1,038,375 Showdown) |
| Blank lineups (reserved, never filled) | 5,607 (1,314 Classic; 4,293 Showdown); kept in field-size and rank denominators, excluded from construction tables |
| Independent slate groups | 5: Classic 2026-09-13 (12 games), NE@SEA 09-09, SF@LAR 09-10, DAL@NYG 09-13, DEN@KC 09-14 |
| Exports with `TimeRemaining` > 0 | 0 (all final) |
| Duplicate representations of one contest | 0 |
| Our entries in the 26 contests | 71; `Rank` equals history `Place` in 71 of 71 |
| 2026-era entries missing standings | 3, in contests 193391019 (2) and 193391038 (1), NE@SEA; $1.50 fees, $0 winnings; excluded from field analysis, included in account totals |
| Lineup names unresolved against the same-slate salary file | 0 of 1,865,110 lineups; 0 ambiguous names in any salary pool |
| Payout ladders available | 1 of 26 (193391013, operator-supplied); all other prize arithmetic is blocked |

Classic and Showdown were classified from roster structure (`QB/RB/WR/TE/FLEX/DST` slots vs `CPT/FLEX`), not from filenames.

### 2.2 Definitions

Top 1% and top 0.1% mean `Rank ≤ ceil(q × N)` with N the full field including blanks; DK ranks are min-rank across ties so a tie group at the boundary is included whole. First place means `Rank == 1`. Paid means `Rank ≤ Places_Paid` from history; satellites, boosters and the winner-take-all therefore mean award positions, not cash. Ownership is counted from submitted lineups with the Captain and FLEX roles kept separate; Classic base-position and FLEX appearances are summed per person. Both reconcile to DraftKings' own `%Drafted` column when the denominator is all entries including blanks: mean absolute difference 0.002 percentage points in Classic (after summing DK's separate base and FLEX rows; Gibbs 38.58% RB plus FLEX equals 42.75% total) and 0.002 to 0.003 in Showdown. Duplication is the count of entries sharing an exact scoring-equivalent roster with Captain identity preserved. Lift is the cohort rate divided by the contest base rate. Construction tables use the largest contest per slate group so that one game is never counted eight times: 193391013 (NE@SEA, 126,020), 195390868 (SF@LAR, 178,359), 193028206 (Classic, 832,342), 195526142 (DAL@NYG, 59,453), 195526229 (DEN@KC, 237,812).

### 2.3 What actually ran: submitted-lineup provenance

Each of our lineups in the standings was compared, set-wise by player, to every candidate file in the repo and Downloads.

| Slate | Standings lineups identical to | Notes |
|---|---|---|
| NE@SEA (2) | `Claude outputs/DK_REVIEW_ENTRY_ne-sea-live-excl20.csv` (2 of 2), SHA-256 `cf33f3e5…585b96`, the replay anchor | Engine SD1/SD2 no-policy path. The other 3 NE@SEA entries were not in the engine's entry template |
| SF@LAR (11) | `data/runs/20260910-showdown-sf-lar/review_final/DK_REVIEW_ENTRY_sflar-final.csv` (11 of 11) | The `review/…loose8.csv` differs in 10 of 11. `policy/portfolio_policy_FINAL.json` excludes Mac Jones, yet the shipped lineup 5249167150 rosters him beside Purdy: the exact policy bytes behind the shipped file are not retained |
| Week 1 Classic (20) | `DKEntries_NFL_Week1_LATESWAP_FINAL.csv` (20 of 20) | `DK_BULK_ENTRY_week1_portfolio.csv` from `build_portfolio.py` differs in 20 of 20. Chain: `Main_20lineups` (0/20 match) → `_v2` (15) → `Main_FINAL` (17) → `Main_UPLOAD` (19) → `LATESWAP` (17, Hampton swaps) → `LATESWAP_v2` (18) → `LATESWAP_FINAL` (20). No engine artifact for this slate |
| DAL@NYG (20) | `DKEntries_DAL_NYG_20lineups_REVIEW_v6.csv` (20 of 20) | No `data/runs` snapshot; policy `DAL_NYG_20260913_portfolio_policy_v6.json` |
| DEN@KC (18) | `DKEntries_DEN_KC_18lineups_v6.csv` = `_v8_FINAL.csv` (18 of 18), SHA-256 `4f5ab44f…321204` | Matches `docs/RUN_RECORD_20260914_DEN_KC.md`; policy v6 |

Consequence: 49 of our 71 standings entries are attributable to a specific engine export and policy; 20 (Week 1, $100 of $155.75 fees) are attributable to no build; 2 SF@LAR-style gaps remain in policy bytes. Account results and engine results are not the same population.

### 2.4 Limitations

Five independent outcomes. One payout ladder. No engine ownership estimates exist on the `prior_review` path (`ownership_brackets_csv` is `None` in every `run_request.json`), so ownership-prediction grading is limited to the one transcribed public vector. All Showdown construction features share the game's realized script within a slate; lifts describe those fields, not future ones. Many features were examined (roughly 50 cells per game); no significance is claimed anywhere below.

## 3. Actual account results

### 3.1 By era and format

| Era | Entries | Contests | Slate-days | Fees | Cash | Net | ROI | Paid |
|---|---|---|---|---|---|---|---|---|
| Pre-2026 (2023-11-19 to 2026-02-08) | 71 | 67 | 54 | $79.72 | $37.90 | −$41.82 | −52.5% | 8 |
| 2026 engine era (09-09 to 09-14) | 74 | 28 | 4 | $155.75 | $98.70 | −$57.05 | −36.6% | 9 |
| All-time | 145 | 95 | 58 | $235.47 | $136.60 | −$98.87 | −42.0% | 17 |

Within the 2026 era: Classic 20 entries, $100 → $36 (−64%); Showdown 54 entries, $55.75 → $62.70 (+12.5%). The Showdown figure is two $20 NE@SEA entries that both min-cashed for $30 (rank 17,298 and 17,328 of 126,020, 13.7th percentile, both duplicated 23 and 35 times in the field). The other 52 Showdown entries returned $2.70 on $15.75 (−82.9%). By type: GPP 45 entries $150.60 → $98.70; satellites and qualifiers 26 entries $4.40 → $0; boosters 2 → $0; winner-take-all 1 → $0. Ticket winnings: none, ever.

### 3.2 By slate, chronologically

| Slate-day | Entries | Contests | Fees | Cash | Net | Cumulative | Paid | Best percentile | Below field median |
|---|---|---|---|---|---|---|---|---|---|
| 09-09 NE@SEA | 5 | 3 | $41.50 | $60.00 | +$18.50 | +$18.50 | 2 | 13.7% | 0 of 2 (in standings) |
| 09-10 SF@LAR | 11 | 8 | $4.20 | $2.20 | −$2.00 | +$16.50 | 2 | 6.3% | 8 of 11 |
| 09-13 Classic + DAL@NYG | 40 | 9 | $105.15 | $36.50 | −$68.65 | −$52.15 | 5 | 2.9% (Classic) | 8 of 20; 15 of 20 |
| 09-14 DEN@KC | 18 | 8 | $4.90 | $0.00 | −$4.90 | −$57.05 | 0 | 43.0% | 17 of 18 |

Loss taxonomy for the four fee-bearing 2026 days: zero payout 1 of 4; more than half of fees lost 2 of 4; negative 3 of 4; worst day −$68.65 (65% of that day's fees). Pre-2026: 38 fee-bearing days, 31 with zero payout (82%), largest single-day loss $6. The era's drawdown is dominated by one $100 Classic decision; the 2026 Showdown book ex-NE@SEA lost small amounts on every day.

### 3.3 Concentration

Two contests held 89.9% of 2026 fees: the $5 Classic Millionaire (64.2%, 20 entries) and the $20 NE@SEA Millionaire (25.7%, 2 entries). Entry-weighted, 58% of the era's entries (43 of 74) were $0.10 to $0.25 Showdown tickets. Fee-weighted and entry-weighted views of "how did the system do" therefore describe different portfolios: the fee-weighted answer is "the hand-built Classic portfolio lost $64 and the two engine NE@SEA entries made $20"; the entry-weighted answer is "the engine's Showdown portfolios cashed 5 of 54 and the Week 1 Classic 4 of 20."

### 3.4 Distance to thresholds

| Contest | N | Paid places | Score to cash | Top 1% | Top 0.1% | First | Our best | Gap to cash | Gap to top 1% |
|---|---|---|---|---|---|---|---|---|---|
| Classic 193028206 | 832,342 | 173,275 | 165.46 | 209.00 | 229.60 | 273.98 | 196.96 | +31.5 | −12.0 |
| NE@SEA 193391013 | 126,020 | 26,495 | 75.67 | 90.52 | 97.12 | 101.02 | 78.84 | +3.2 | −11.7 |
| SF@LAR 195390868 | 178,359 | 37,455 | 72.30 | 92.15 | 98.35 | 105.80 | 51.10 | −21.2 | −41.0 |
| DAL@NYG 195526142 | 59,453 | 15,950 | 94.90 | 122.10 | 134.00 | 135.80 | 75.20 | −19.7 | −46.9 |
| DEN@KC 195526229 | 237,812 | 49,940 | 92.30 | 114.93 | 121.51 | 124.61 | 40.46 | −51.8 | −74.5 |

Satellites and small fields: winning a 237-entry single-ticket satellite required 120.9 (DAL@NYG) and 121.7 (DEN@KC), scores between the top-1% and top-0.1% thresholds of the 60,000- to 240,000-entry fields on those games (DAL@NYG 122.1 and 134.0; DEN@KC 114.9 and 121.5). Our best in those satellites: 98.1 and 72.8 (7 entries each). A one-seat satellite is a first-place objective; 29 of our 49 non-Millionaire Showdown entries were in contests paying 0.2% to 4.3% of the field.

## 4. Contest ceiling findings

### 4.1 What the top of a Showdown field looks like

| Reference contest | Entries tied for first | Winning lineup | Split | QBs | DST | Salary left | Own-sum (combined) | Copies |
|---|---|---|---|---|---|---|---|---|
| NE@SEA 193391013 | 23 | CPT Smith-Njigba; Maye, Price, Hollins, Stevenson, Seahawks | 3-3 | 1 | 1 | $500 | 2.80 | 23 |
| SF@LAR 195390868 | 1 | CPT D. Robinson; Purdy, McCaffrey, Deebo, Kyren, Evans | 5-1 | 1 | 0 | $500 | 2.09 | 1 |
| DAL@NYG 195526142 | 7 | CPT Likely; Skattebo, Lamb, Singletary, J. Williams, Dart | 4-2 | 1 | 0 | $1,200 | 2.53 | 6 |
| DEN@KC 195526229 | 206 | CPT K. Walker III; Chiefs, Engram, Mahomes, Rice, Kelce | 5-1 | 1 | 1 | $300 | 2.40 | 206 |

Three of four winners were chalk-built (own-sum 2.4 to 2.8 of a maximum 6.0 slots) with one distinguishing captain or one distinguishing FLEX. The SF@LAR winner was the exception: a captain the field captained 0.18% of the time and rostered 4.6% (Demarcus Robinson, 13.0 FLEX points) on a chalk core, unique in a 178k field, and unshared. All four spent to within $1,200.

### 4.2 Duplication and prize dilution

Share of the top-1% cohort by duplication, reference contests: dup ≥6 was 83.1% (SF@LAR), 92.4% (DAL@NYG), 98.3% (DEN@KC); unique lineups were 3.8%, 1.9%, 0.5%. In the smaller fields, unique lineups reached 10.8% to 15.7%. With the one supplied ladder (NE@SEA, $2.25M pool, 44.4% of the pool to first, 61.9% to the top 1%):

| Duplication bucket | Share of entries | Share of prize money | Prize per $20 entry | ROI |
|---|---|---|---|---|
| 1 (unique) | 6.9% | 1.4% | $3.59 | −82% |
| 2 | 4.2% | 1.2% | $4.98 | −75% |
| 3 to 5 | 8.9% | 3.1% | $6.17 | −69% |
| 6 to 20 | 24.4% | 8.9% | $6.51 | −67% |
| 21 to 100 | 37.7% | 74.6% | $35.36 | +77% |
| >100 | 17.9% | 10.9% | $10.93 | −45% |

The 23-way tie for first pooled ranks 1 to 23 ($1,243,500) and paid $54,065 per entry, 5.4% of the advertised first prize. This is one realized outcome, and it says two things at once: the winning roster was in the 21-to-100 bucket because it was a near-consensus roster, and the same consensus that made it likely to hit made it worth 5% of face value when it did. A first-place objective in Showdown has to be P(unique or lightly shared first), not P(first).

### 4.3 Construction features across the four Showdown games

Top-1% lift by feature and game, reference contests, cells with fewer than 200 entries blank. "Below-median lift" is the rate of finishing under the field median relative to the base rate (>1 means more downside).

| Feature | Level | NE@SEA | SF@LAR | DAL@NYG | DEN@KC | Min lift | Games ≥1 | Below-median lift range |
|---|---|---|---|---|---|---|---|---|
| Pass catchers with rostered QB | 0 | 3.69 | 0.03 | 0.00 | 0.02 | 0.00 | 1 | 0.50 to 1.19 |
| | 1 | 1.60 | 1.53 | 2.08 | 1.39 | **1.39** | **4** | **0.72 to 0.85** |
| | 2 | 0.41 | 1.49 | 0.76 | 1.46 | 0.41 | 2 | 0.89 to 1.22 |
| | 3+ | 0.03 | 0.35 | 0.57 | 0.31 | 0.03 | 0 | 1.09 to 1.43 |
| Salary left | $0 | 0.00 | 0.21 | 2.06 | 0.00 | 0.00 | 1 | 0.85 to 1.28 |
| | $1 to 500 | 1.35 | 1.23 | 1.12 | 1.15 | **1.12** | **4** | **0.86 to 0.98** |
| | $501 to 1,500 | 1.14 | 1.05 | 0.57 | 1.08 | 0.57 | 3 | 0.98 to 1.03 |
| | $1,501 to 3,000 | 1.28 | 0.65 | 0.40 | 1.03 | 0.40 | 2 | 1.07 to 1.14 |
| | $3,001 to 6,000 | 0.71 | 0.26 | 0.05 | 0.73 | 0.05 | 0 | 1.22 to 1.34 |
| | > $6,000 | 0.00 | 0.00 | 0.16 | 0.02 | 0.00 | 0 | 1.54 to 1.77 |
| QBs rostered | 0 | 1.03 | 0.04 | 0.00 | 0.00 | 0.00 | 1 | 0.52 to 1.42 |
| | 1 | 1.50 | 1.64 | 0.73 | 1.15 | 0.73 | 3 | 0.87 to 1.13 |
| | 2 | 0.11 | 0.03 | 1.45 | 0.95 | 0.03 | 1 | 0.80 to 1.32 |
| Defenses | 0 | 0.47 | 0.88 | 1.23 | 0.26 | 0.26 | 1 | 0.94 to 1.13 |
| | 1 | 1.86 | 1.34 | 0.25 | 2.87 | 0.25 | 3 | 0.74 to 1.19 |
| Kickers | 0 | 0.88 | 0.58 | 1.76 | 1.45 | 0.58 | 2 | 0.94 to 1.02 |
| | 1 | 1.24 | 1.66 | 0.00 | 0.46 | 0.00 | 2 | 0.96 to 1.05 |
| | 2 | 0.78 | 0.79 | 0.00 | 0.00 | 0.00 | 0 | 0.94 to 1.42 |
| Team split | 3-3 | 1.45 | 0.27 | 1.53 | 0.46 | 0.27 | 2 | 0.73 to 1.02 |
| | 4-2 | 0.44 | 0.86 | 0.73 | 1.11 | 0.44 | 1 | 1.01 to 1.04 |
| | 5-1 | 0.04 | 2.82 | 0.64 | 2.56 | 0.04 | 2 | 0.93 to 1.45 |
| Captain position | QB | 0.07 | 2.50 | 1.46 | 0.39 | 0.07 | 2 | 0.79 to 1.29 |
| | RB | 0.23 | 0.74 | 0.48 | 3.67 | 0.23 | 1 | 0.45 to 0.91 |
| | WR | 2.30 | 0.86 | 0.00 | 0.00 | 0.00 | 1 | 0.94 to 1.43 |
| | TE | 0.00 | 0.00 | 6.47 | 0.00 | 0.00 | 1 | 0.64 to 1.37 |
| Captain ownership | < 3% | 0.01 | 0.96 | 0.19 | 0.00 | 0.00 | 0 | 0.97 to 1.31 |
| | 3 to 6% | 0.35 | 1.80 | 3.67 | 0.00 | 0.00 | 2 | 0.47 to 1.40 |
| | > 10% | 1.61 | 0.38 | 0.88 | 1.51 | 0.38 | 2 | 0.75 to 1.04 |
| Combined own-sum | 2.0 to 2.5 | 0.15 | 1.36 | 0.34 | 1.02 | 0.15 | 2 | 0.97 to 1.41 |
| | 2.5 to 3.0 | 1.22 | 0.00 | 1.99 | 1.06 | 0.00 | 3 | 0.70 to 1.08 |
| Sub-5% players | 0 | 1.08 | 0.97 | 0.65 | 1.18 | 0.65 | 2 | 1.01 to 1.04 |
| | 1 | 0.51 | 1.16 | 3.60 | 0.00 | 0.00 | 2 | 0.89 to 0.91 |
| | 2+ | 0.25 | 0.46 | (n<200) | 0.00 | 0.00 | 0 | 0.70 to 1.48 |
| Duplication | 1 (unique) | 0.34 | 0.56 | 0.20 | 0.07 | 0.07 | 0 | 1.10 to 1.42 |
| | 21 to 100 | 1.74 | 1.31 | 1.23 | 0.78 | 0.78 | 3 | 0.84 to 0.98 |
| | > 100 | 0.55 | 0.42 | 4.58 | 3.15 | 0.42 | 2 | 0.22 to 1.20 |

Reading: the structural hygiene rows (one pass catcher, spend to within $500, one QB) are the only rows that raised the ceiling rate and lowered the below-median rate in the same game, in every game. The rows that decide who actually wins (captain identity, split, chalk vs contrarian, K/DST) are the game's script, and four games contain four scripts. Two-QB builds were dead in the two games where one QB busted (Darnold 0.52, Stafford 5.10) and the best construction in the game where both QBs produced (DAL@NYG). Uniqueness was the worst single feature on both objectives in all four games: unique lineups are unique because they roster players nobody else wants.

### 4.4 Field fragility, and whether it was knowable

| Game | Shared assumption in the field | Field share | Paid rate with / without | Top-1% rate with / without | Pre-lock observable? |
|---|---|---|---|---|---|
| DEN@KC | Bo Nix produces | 73.1% | 14.6% / 39.1% | 0.62% / 2.11% | Nix's 7.44 was a tail outcome for a starting QB; the market total (42.5) and KC −2.5 did not flag it |
| DEN@KC | Kenneth Walker III is not the slate's best play | omitted by 41.9% | 0.0% without him | 0.0% without him | Yes: $10,600 FLEX, most expensive on the slate; the engine expected 7.3 points (0.687 pts/$1k, 29th of 32) because his history is on another team (transfer prior). This is a scoring defect, not a field read |
| DAL@NYG | George Pickens | 45.8% | 9.2% / 42.2% | 0.17% / 2.11% | Not from public data in this corpus |
| DAL@NYG | Isaiah Likely is a secondary piece | omitted by 68.5% | 57.8% / 12.9% | 3.88% / 0.00% | Partially: 31.5% of the field had him; we had 0 of 20 |
| SF@LAR | Stafford is the QB to roster | 59.4% | 6.8% / 42.3% | 0.01% / 2.51% | Purdy (58.0%) was equally chalk and paid 34.0% vs 3.4% without; the field split the QB question about evenly and one side lost |
| NE@SEA | No defense in a Wednesday shootout | 68.2% no DST | 13.3% / 37.7% (any DST) | 0.47% / 2.14% | Seahawks DST was 21.4% owned; the game went under |

None of these is a "chalk trap" in the sense of a predictable fade. Two are the same event viewed from both sides (Stafford versus Purdy). One (Walker) is an engine scoring defect, not field fragility. The exploitable pattern is narrower: when the field splits nearly evenly on a binary question (which QB, which team's script), a portfolio that also splits nearly evenly is guaranteed half-dead, and a portfolio that goes 94% to one side (ours in DEN@KC) is a coin flip on the whole slate. That is a portfolio-level fact, and section 5 quantifies it.

### 4.5 Classic (one slate, 831,028 lineups)

Winner: Jordan Love with one pass catcher (Watson), no bring-back, RB FLEX, Steelers DST, $0 left, own-sum 1.01, three sub-5% players, unique. The top 10 used four QBs (Love, Shough three times, Bryce Young five times, Allen); all ten had an RB at FLEX; all ten left $300 or less; six of ten had a bring-back.

| Construction | Field share | Top-1% lift | Top-0.1% lift | Paid lift |
|---|---|---|---|---|
| QB + 0 same-team pass catchers | 19.2% | 0.52 | 0.36 | 0.81 |
| QB + 1 | 53.0% | 0.85 | 0.91 | 0.94 |
| QB + 2 | 26.1% | 1.47 | 1.48 | 1.21 |
| QB + 3 | 1.6% | 4.15 | 3.67 | 1.66 |
| QB + 4/5 | 0.04% | 0.00 | 0.00 | 0.55 |
| 0 bring-backs | 56.0% | 0.62 | 0.56 | 0.87 |
| 1 bring-back | 35.9% | 1.27 | 1.43 | 1.07 |
| 2 bring-backs | 7.4% | 2.47 | 2.25 | 1.55 |
| RB bring-back (alone) | 11.9% | 2.20 | 3.14 | 1.37 |
| RB + WR bring-back | 4.1% | 3.46 | 3.28 | 1.67 |
| RB from QB's team (running back in the stack) | 19.8% | 0.66 | 0.47 | 0.90 |
| FLEX RB / WR / TE | 42.5 / 36.1 / 21.4% | 1.25 / 0.86 / 0.75 | 1.47 / 0.78 / 0.44 | 1.07 / 0.89 / 1.05 |
| One offensive player against own DST (two or more: 0.7%, lift ≤0.5) | 6.9% | 0.60 | 0.50 | 0.82 |
| DST on the QB's team | 5.4% | 0.38 | 0.20 | 0.82 |
| Players from 3 / 4 / 5 / 6 / 7+ games | 5.3 / 20.8 / 34.8 / 27.7 / 10.7% | 2.43 / 1.51 / 0.88 / 0.65 / 0.35 to 0.46 | 2.50 / 1.75 / 0.87 / 0.59 / 0.00 to 0.31 | 1.52 / 1.20 / 0.98 / 0.84 / 0.76 to 0.78 |
| Salary left $0 / ≤300 / ≤1,000 / >1,000 | 49.9 / 39.4 / 9.0 / 1.7% | 1.01 / 1.02 / 1.00 / ≤0.47 | 1.02 / 1.00 / 1.04 / ≤0.27 | 1.01 / 1.01 / 0.98 / ≤0.69 |
| Own-sum <0.75 / 0.75 to 1.0 / 1.0 to 1.25 / 1.25 to 1.5 / >1.5 | 10.0 / 26.6 / 30.1 / 21.4 / 11.8% | 0.4 / 0.53 / 0.99 / 1.73 / 1.28 | 0.3 / 0.40 / 1.03 / 2.02 / 1.05 | 0.7 / 0.74 / 1.01 / 1.30 / 1.27 |
| Sub-5% players 0 / 1 / 2 / 3 / 4 / 5+ | 12.1 / 22.8 / 25.2 / 20.2 / 12.2 / 7.6% | 2.07 / 1.49 / 0.89 / 0.57 / 0.43 / ≤0.27 | 2.16 / 1.54 / 0.89 / 0.59 / 0.32 / ≤0.11 | 1.52 / 1.24 / 0.99 / 0.79 / 0.66 / ≤0.61 |
| Duplication 1 / 2 / 3 to 20 / >20 | 89.8 / 4.7 / 4.5 / 0.9% | 0.95 / 1.56 / 1.5 to 1.7 / ≤0.34 | 0.97 / 1.57 / 1.1 to 1.3 / 0.00 | 0.97 / 1.20 / 1.3 to 1.4 / 1.1 to 1.4 |

The stacking gradient is real in aggregate and mostly a QB-selection effect in disaggregate. Within QB, adding pass catchers raised the top-1% rate for Shough (0.56% at 0, 2.41% at 1, 5.16% at 2, 15.1% at 3) and Lamar Jackson (0.76 → 1.50 → 0.96%), and lowered it for Burrow (0.15 → 0.02 → 0.00%), Herbert (0.10 → 0.12 → 0.04%), Mayfield (0.14 → 0.06 → 0.00%) and Goff at 2+ (0.59% at 1, 0.27% at 2). Correlation amplifies the QB outcome in both directions: it raises the variance, and it raises valuable upside only when the QB is right. The cohort-level lift is the field's QB hit rate wearing a stacking costume. The same holds for game concentration: three-game builds had a 2.43x top-1% lift and a 1.52x paid lift, which is variance that paid on this slate.

Ownership ran the other way from Showdown folklore. The top 1% was chalkier than the field (mean own-sum 1.24 vs 1.12; paid entries 1.19); each additional sub-5% player lowered the top-1% rate monotonically from 2.08% (zero) to 0.16% (six); own-sum below 1.0 had a 0.4 to 0.5x lift. Field ownership correlated 0.74 (Spearman) with actual fantasy points across the pool: the crowd was right about who would score, and the winner differentiated with three sub-5% pieces on top of a chalk core (Gibbs 42.8%, Henry, Swift), not instead of one. Burrow (11.3% of QBs, top-1% rate 0.03%) and Herbert (10.2%, 0.10%) were the field's fragile QB assumptions; Shough (8.9%, 4.10%) and Bryce Young (3.3%, 6.40%) were the payoffs.

Entry-count cohorts: entries from 150-max users (22.7% of the field) reached the top 1% at 1.28%, from 21-to-149-entry users at 1.13%, from single-entry users at 0.67%. Skill is visible in this field. Among the 980 users with exactly 20 entries, 19.0% had at least one top-1% finish, the median best rank was 30,861, and 38% cashed fewer than 4 of 20. Our 20 (best 23,887, 4 paid) were a median 20-entry portfolio.

## 5. Portfolio downside findings

### 5.1 Our portfolios as joint objects

| Slate | Entries | Max single-player share (entry / fee weighted) | Top exposures vs field (combined) | Mean pairwise overlap (of 6 or 9) | Two-QB share | 3+ pass catchers share | DST share | Unique-lineup share (ours / field) | Below field median |
|---|---|---|---|---|---|---|---|---|---|
| NE@SEA | 2 | 1.00 / 1.00 | Maye 100% vs 76%; Henry 100% vs 30%; Myers 100% vs 29%; JSN 100% vs 70% | 4.0 | 50% | 50% | 0% | 0% / 7% | 0 of 2 |
| SF@LAR | 11 | 0.73 / 0.68 | McCaffrey, Nacua, Stafford, Kyren 73% each vs 68/65/59/38%; Parkinson 64% vs 19% (1.6 pts) | 2.85 | 0% | 27% | 0% | 55% / 7% | 8 of 11 |
| Classic | 20 | 0.35 / 0.35 | St. Brown, Flowers, Henry 35% vs 18/11/9%; Fannin 30% vs 4% (4.1 pts); Titans DST 20% vs 5% (0 pts) | 1.13 | n/a | n/a | n/a | 100% / 90% | 8 of 20 |
| DAL@NYG | 20 | 0.80 / 0.66 | Dak 80% vs 71%; J. Williams 75% vs 57%; Pickens 65% vs 46% (5.8 pts); Dart 65% vs 67%; Tracy 60% vs 14% (0.4 pts); Ferguson 55% vs 24% (2.6 pts); T. Johnson 55% vs 15% (1.9 pts) | 3.29 | 45% | 15% | 0% | 85% / 10% | 15 of 20 |
| DEN@KC | 18 | 0.94 / 0.95 | Nix 94% vs 73% (7.44 pts); Kelce 78% vs 35%; Mahomes 72% vs 69%; Waddle 61% vs 45% (1.2 pts); Harvey 56% vs 19% (8.1 pts); Franklin 44% vs 5% (0.5 pts); Walker 0% vs 58% (37.1 pts) | 3.46 | 67% | 67% | 0% | 67% / 6% | 17 of 18 |

Two patterns recur. First, differentiation was bought with dead salary: in every slate the players we over-indexed relative to the field by the widest margin (Parkinson, Tracy, Ferguson, Theo Johnson, Franklin, Harvey, Fannin, Titans) scored 0 to 8 points. In the three multi-entry Showdown slates our unique-lineup rate (55% to 85%) was eight to twelve times the field's, and section 4.3 shows uniqueness was the worst feature on both objectives. Second, the core was shared: in DAL@NYG 161 of 190 lineup pairs overlapped in 3 or 4 of 6 players; in DEN@KC 136 of 153. Low player overlap was not the problem; the problem was that the low-overlap positions were filled with players who could not score, so the portfolio's outcome was decided by the 3-player core.

### 5.2 Why the portfolios looked like this

The mechanism is visible in the artifacts. The engine's objective is the sum of prior points of the expected stat line; it has no distribution, no covariance, no ownership and no payout. Its priors overshoot: SF@LAR lineup priors ran 72.6 to 111.6 against actual scores of 43.6 to 78.8, NE@SEA priors 113.2 and 108.2 against 78.84 and 78.83, and the 20 selected SF@LAR person-roles (CPT rows carry the 1.5x) had a mean prior of 16.9 points against a mean actual of 9.1 (correlation 0.34, MAE 10.2). Overshoot on a shared scale does not change rankings, but it makes every marginal salary dollar look like it buys more points than it does, which is one reason the engine fills with mid-salary role players rather than leaving salary for a second premium.

Under that objective the only diversification tools are exposure caps and a pairwise-overlap limit. The DEN@KC run record shows what that produces: v1 emitted a QB-less lineup and a starter-plus-backup lineup, v3 (captain cap tightened to one lineup) was infeasible, v5 zeroed both kickers, and v6 raised Nix's cap to 0.95 (17 of 18) and Mahomes's to 0.89 to reach 12 two-QB lineups, then shipped. The policy's overlap cap of 4 bound 153 entry pairs, of which 128 were cross-contest and constrained nothing that mattered, and the assignment step mapped the weakest lineups by prior points onto template rows 17 and 18, which were the NHL satellite. The DAL@NYG v6 policy (combined cap 0.825, captain 0.125, kickers 0.125) produced 60% of lineups leaving more than $1,500 against 12% in the field.

### 5.3 What concentration costs, measured on the field

For every user with 10 or more entries in a reference contest, the portfolio's maximum single-player share was computed along with its outcomes.

| Game (contest) | Users | Max-share band | Users | Paid fraction | P(≥1 top-1%) | P(zero paid) |
|---|---|---|---|---|---|---|
| DEN@KC mini-MAX (195526229) | 2,693 | 50 to 70% | 400 | 0.170 | 0.358 | 0.032 |
| | | 70 to 85% | 1,236 | 0.218 | 0.498 | 0.040 |
| | | 85 to 100% | 1,046 | 0.204 | 0.223 | 0.163 |
| SF@LAR mini-MAX (195390868) | 2,020 | 50 to 70% | 479 | 0.233 | 0.562 | 0.010 |
| | | 70 to 85% | 843 | 0.218 | 0.498 | 0.021 |
| | | 85 to 100% | 691 | 0.174 | 0.110 | 0.194 |
| DAL@NYG First Down (195526142) | 1,778 | 50 to 70% | 197 | 0.226 | 0.142 | 0.030 |
| | | 70 to 85% | 649 | 0.271 | 0.194 | 0.020 |
| | | 85 to 100% | 929 | 0.310 | 0.173 | 0.081 |
| NE@SEA Millionaire (193391013) | 1,516 | 50 to 70% | 104 | 0.148 | 0.279 | 0.038 |
| | | 70 to 85% | 495 | 0.183 | 0.271 | 0.085 |
| | | 85 to 100% | 915 | 0.234 | 0.193 | 0.113 |

The median multi-entry portfolio in these fields already puts 80% to 90% of its entries on one player; concentration is the norm. Above 85% the zero-paid rate is 1.4x to 12x the rest of the field in all four games (2.5x or more in three), and the probability of at least one top-1% finish is lower than the 70-85% band in all four. Mean paid fraction does not fall (in DAL@NYG and NE@SEA it rises), which is the shape of a bimodal outcome: the concentrated portfolio cashes broadly when its player hits and returns nothing when he does not. Skill confounds this (a sharp entrant who is 90% on the right player looks great), but the direction is the same in four independent games and it matches our own outcomes exactly.

### 5.4 Marginal value of an entry, and what our portfolios forfeited

Random draws from each reference field under its realized outcome (4,000 replications, entries sampled with their field frequency):

| Portfolio size k | Filter | P(≥1 top-1%) | P(≥1 top-0.1%) | Paid fraction | P(zero paid) | P(all below median) |
|---|---|---|---|---|---|---|
| 1 | any field lineup | 0.010 | 0.001 | 0.224 | 0.776 | 0.494 |
| 5 | any | 0.053 | 0.006 | 0.226 | 0.283 | 0.031 |
| 10 | any | 0.104 | 0.013 | 0.226 | 0.077 | 0.001 |
| 20 | any | 0.192 | 0.024 | 0.225 | 0.007 | 0.000 |
| 20 | H1 hygiene (1 QB, 1-2 pass catchers with him, ≤$1,500 left, ≤1 K, ≤1 DST) | 0.281 | 0.039 | 0.272 | 0.002 | 0.000 |
| 20 | H2 (H1 and exactly 1 pass catcher and $1 to 500 left) | 0.303 | 0.036 | 0.345 | 0.001 | 0.000 |

Averages over the four games; per-game values are in the appendix output `L_hygiene_bootstrap.txt`. Our actual portfolios: DEN@KC k=18, zero paid (random draw P ≈ 0.01, H1 draw P ≈ 0.003); DAL@NYG k=20, 1 paid of 20 (random expectation 5.4); SF@LAR k=11, 2 paid of 11 (expectation 2.3); NE@SEA k=2, 2 paid of 2. The DEN@KC and DAL@NYG outcomes are what 18 to 20 entries deliver when their effective independent count is one or two. The structural filter H1 raised P(≥1 top-1%) from 0.19 to 0.28 at k=20 while cutting P(zero paid) by two-thirds, in every game; it passed 28% to 37% of each field and 10% (DAL@NYG), 22% (DEN@KC), 50% (NE@SEA), 55% (SF@LAR) of our lineups. H1 uses no ownership and no outcome, so it was available before lock.

Classic, same method on the one slate: P(≥1 top-1%) at k=20 was 0.180 for any field lineup and 0.274 under a Classic hygiene filter (QB + 1-2 pass catchers, ≥1 bring-back, ≤$1,000 left, no offense against own DST, DST not on the QB's team, no RB from the QB's team; 27.9% of the field passed; 13 of our 20 passed). Zero-paid probability at k=20: 0.008 and 0.002.

### 5.5 Scenario coverage, structurally

Our Showdown portfolios covered one script each. DEN@KC: 94% Nix, 61% Waddle, 56% Harvey, 0% Walker, 0% DST, 67% two-QB, 33% 4-2, 11% 5-1. The one KC-heavy 5-1 (Worthy captain with Mahomes, Rice, Kelce, Thornton and Nix) finished at the 70th percentile without Walker or the Chiefs DST; the script that happened (Walker 37.1, Chiefs DST, Mahomes 22.7) had no lineup. DAL@NYG: 80% Dak, 65% Dart, 61% of slots on DAL, 0% Likely, 0% DST; a Giants-side or defensive script had no lineup. SF@LAR: 73% on the Stafford-Nacua-Kyren-McCaffrey core, 70% of slots on LAR, three Purdy lineups; two of those were our two best finishes (6.3rd and 10.2nd percentile) and the third, which paired Purdy with Parkinson and Corum, finished 57.8th. Classic: 13 different QBs across 20 lineups, mean overlap 1.13 players, 12 games touched; the coverage was wide and the failure was player-level (Fannin, Titans, Waller, Metcalf) rather than scenario-level. The Classic portfolio, which was not engine-built, is the one that looks like a scenario portfolio; the engine-built ones look like one lineup with 17 perturbations.

## 6. Classic versus Showdown, and contest-type differences

| Dimension | Classic (1 slate) | Showdown (4 games) | Consequence for the objective |
|---|---|---|---|
| Uniqueness of the top | Winner unique; 89.8% of field unique; top 1% 90% unique | Winners duplicated 1x, 6x, 23x, 206x; top 1% 83-98% duplicated | Classic first place is roughly face value; Showdown first place must be valued net of an expected 5 to 200-way split |
| Ownership direction | Top 1% chalkier than field; each sub-5% player lowers the rate | Flips by game; sub-5% players hurt everywhere, chalk sum helps in 3 of 4 | Contrarian quotas are wrong in both modes; differentiation has to come from one piece on a chalk core |
| Correlation | Stacks amplify QB outcome both ways; game concentration raised ceiling and paid rate | One pass catcher with QB helped everywhere; three or more hurt everywhere | Correlation is a lever only conditional on the QB being right; over-stacking is a variance purchase that lowered both objectives |
| Salary | ≤$300 left is the field norm and the top's norm | $1-500 left ≥1.1x in all four games; $0 left dead in 3 of 4; >$3,000 dead everywhere | Do not buy uniqueness with salary in either mode |
| Our exposure shape | Wide (13 QBs, overlap 1.13) | Narrow (max share 0.73-1.00) | The engine path produced the narrow shape; the hand path produced the wide one |
| Our results | 4 of 20 paid, −64%, median for 20-entry users | 5 of 54 paid, +12.5% with NE@SEA, −83% without | Neither mode shows an edge; Showdown's number is two entries |

Contest types within the era: GPP 45 entries, $150.60 → $98.70 (−34%); satellites 26 entries, $4.40 → $0; boosters and WTA 3 entries → $0. Uniform field draws would have won 0.23 satellite seats across our 26 attempts, so zero seats is weak evidence of anything. The stronger evidence is the score gap: our best scores were 12 to 71 points below the award line in all ten satellite, booster and winner-take-all contests, and the engine's assignment placed its lowest-prior lineups on those rows by construction. Rake was 14.9% to 15.9% in 26 of the era's 28 contests (Classic Millionaire 15.9%, satellites 14.9% to 15.8%, boosters 15.6%); the two NE@SEA opening-night contests were the exceptions at 9.1% and 10.7%. Type selection is a payout-shape question, not a rake question. Differences between contest types do not survive adjustment for slate: within DAL@NYG our satellite entries averaged 74.5 points and our GPP entries 78.3 with the same construction process; within DEN@KC 49.7 and 53.1.

## 7. Ceiling and downside trade-offs

Where the two objectives agree, from the data above: spend to within $500; stack exactly one pass catcher with the rostered QB; never roster more than two pass catchers with a Showdown QB; never buy uniqueness with a sub-5% player who has no path to points; keep the portfolio's maximum single-player share under about 85%. Each of these raised the top-1% rate and lowered the below-median or zero-paid rate in every game where it could be measured. Two more nearly qualify: one QB (three of four games) and keeping a DST in the candidate space (DST=1 was ≥1.34x in three of four and appeared in two of four winning lineups; the engine portfolios had none).

Where they conflict:

| Lever | Ceiling effect | Downside effect | Evidence | Resolution this corpus supports |
|---|---|---|---|---|
| 5-1 split / game concentration (Classic 3-game builds) | 2.4 to 2.8x top-1% in the games or slate where the concentrated side hit; 0.04 to 0.64x where it did not | Higher below-median rate in 2 of 4 Showdown games | Sections 4.3, 4.5 | A minority sleeve, sized so that its total failure leaves the portfolio's paid count above zero |
| Two-QB Showdown builds | 1.45x when both produce, 0.03 to 0.11x when one busts | Higher below-median rate in NE@SEA and DEN@KC | 4.3 | Cap around the field share (30 to 47%), never 67% |
| Chalk core with one swing piece | Highest P(top 1%) in 3 of 4 games and the shape of 3 of 4 winners | Duplicated 6 to 206x when it hits; first place paid 5.4% of face in the one measurable case | 4.1, 4.2 | For top-heavy and WTA payouts, the swing piece must be one the field is not choosing; for flat payouts (mini-MAX, satellites with 1 seat) the dilution is the price of being right |
| Portfolio concentration ≥85% on one player | Lower P(≥1 top-1%) in 4 of 4 games | 3x to 12x zero-paid rate in 4 of 4 | 5.3 | No trade-off exists in the data; this lever costs both objectives |
| Salary left for uniqueness | 0.0 to 0.73x top-1% above $3,000 | 1.2 to 1.6x below-median rate | 4.3, 4.5 | No trade-off exists; costs both |
| Correlation via 3+ pass catchers | 4.2x in Classic aggregate; 0.03 to 0.57x in every Showdown game; within-QB Classic effect is sign-of-the-QB | 1.1 to 1.4x below-median in Showdown | 4.3, 4.5 | Classic 3-stacks only as an explicit game-script sleeve on QBs the model rates as under-owned; never in Showdown |

The frontier the data supports is not a curve of one score against another. It is a two-part portfolio: a core of hygiene-compliant lineups (H1) that individually reach the top 1% at 1.4 to 2x the field rate and collectively drive P(zero paid) toward zero, plus a bounded sleeve of script bets (5-1, DST-captain, two-QB, secondary game stack) whose combined failure the core absorbs. The sizes are a risk-tolerance choice Ben has not specified; the data says the sleeve should never be 17 of 18.

## 8. Recommended actions

For each item: supporting result and denominator; mechanism; objective served; cost to the other objective; confounders; a prospective test and what would falsify it.

### 8.1 Measurement and confirmed implementation defects

**A. Record the objective and the payout shape per entry, and stop sending expectation-optimized lineups to first-place contests.** Result: 29 of 49 non-Millionaire Showdown entries sat in contests paying 0.2% to 4.3% of the field; the award lines were 80 to 130 points (114 to 130 on the Sunday and Monday games); our best was 12 to 71 points short in all ten; the assignment step placed the lowest-prior lineups on those rows (run record §5). Mechanism: `MAXIMIZE_PRIOR_POINTS` is a cash-game objective; a one-seat satellite is P(first). Serves ceiling. Cost to downside: none if the change is allocation, not construction. Confounders: only one payout ladder; five games. Test: on the next 20 satellites, assign the highest-variance hygiene-compliant lineup (widest prior spread or largest 5-1 tilt) to the seat contest and record seat-threshold score minus our score; falsified if the gap does not shrink relative to these ten.

**B. Fix the transfer-prior scoring that priced Kenneth Walker III at 7.3 points on a $10,600 tag.** Result: 0 of 99,349 field lineups without Walker paid in DEN@KC; we had 0 of 18 with him; engine ranked him 29th of 32 on points per $1k. Mechanism: a person whose prior-season history is on another team carries an unverified old-team share (`TRANSFER_PRIOR_UNVERIFIED`). Serves both objectives (a missing top scorer caps the ceiling and sinks every lineup at once). Cost: none. Confounder: one player, one game; the same rule also keeps unknowns out. Test: for every slate, list persons whose DK salary rank within position exceeds their prior-points rank by 10 or more places; falsified if that list does not contain the slate's top-3 scorers more often than chance over 10 slates.

**C. Add a portfolio concentration gate independent of the policy caps.** Result: max single-player share 0.94 (DEN@KC), 0.80 (DAL@NYG); field portfolios ≥85% had 1.4x to 12x zero-paid rates in 4 of 4 games (8,007 portfolios). Mechanism: caps are the only diversification device and get raised to make the solve feasible. Serves downside. Cost to ceiling: the 70-85% band had the highest P(≥1 top-1%) in 3 of 4 games, so the cost is negative in this data. Confounders: entrant skill; the field's concentrated portfolios may be weaker entrants. Test: emit `max_person_share` in every review package and refuse `ENFORCED_AND_INDEPENDENTLY_AUDITED` above a declared ceiling (0.80 is the field median); falsified if, over 20 portfolios, the gated portfolios' zero-paid rate is not lower than the ungated history.

**D. Preserve one frozen record per slate: policy bytes, prior vector, candidate bank, submitted CSV, and the late-swap chain.** Result: Week 1 (64% of fees) has no build artifact and its script output differs 20/20 from what ran; SF@LAR's shipped policy bytes are not in the run folder; DAL@NYG and DEN@KC have no `data/runs` snapshot. Mechanism: attribution requires the pre-lock object. Serves both. Cost: none. Test: the next slate's review package must reproduce the submitted CSV hash from stored inputs alone.

**E. Treat archived ownership numbers as invalid until they pass mass conservation.** Result: the Week 1 vector sums QB to 200.6% and DST to 186.5%; MAE 7.82 pp, Spearman 0.13, top-10 recall 2 of 10; and it did not feed the submitted lineups anyway. Mechanism: a transcription of a public board with no schema check. Serves ceiling (ownership-relative exposure is undefined without ownership). Cost: none. Test: any ownership input must satisfy per-position slot totals within 5% before it enters a request; falsified never, this is a validation rule.

**F. Score duplication as part of the first-place objective in Showdown.** Result: 23-way tie paid 5.4% of face; DEN@KC 206-way; top-1% cohorts 83-98% duplicated. Mechanism: consensus rosters are both the likeliest to hit and the most shared. Serves ceiling, correctly defined. Cost to downside: none; a duplication penalty shifts which chalk piece is swapped, not whether the core is chalk. Confounder: one ladder. Test: for the next 10 Showdown contests, compute each of our lineups' field copy count from the standings; the objective's predicted copy count (from a field model) must rank-correlate above 0.5 with the observed count, else the field model is not usable for dilution.

### 8.2 Promising hypotheses for controlled testing

**G. A two-part portfolio: hygiene core plus bounded script sleeve.** Result: H1 raised P(≥1 top-1%) at k=20 from 0.19 to 0.28 and cut P(zero paid) from 0.007 to 0.002, in every game; the script features (5-1, DST, two-QB, TE or RB captain) each had 1.5 to 6.5x lift in the game where they hit and 0.00 to 0.25x in the game where they missed. Mechanism: the core carries the paid count; the sleeve carries the tail. Serves both. Cost: sleeve lineups will be below median most slates. Confounders: H1 is fitted to these four games; the sleeve sizes are unspecified. Test: pre-register the H1 rule and a 25% sleeve before the next 8 Showdown slates; compare P(zero paid) and best-percentile against an all-expectation portfolio built from the same bank; falsified if the two-part portfolio's best percentile is worse in 5 or more of 8.

**H. One pass catcher, one QB, spend to $500 as default Showdown construction constraints.** Result: the only two features with top-1% lift ≥1.1 and below-median lift <1 in all four games (pass catcher: 1.39 to 2.08 and 0.72 to 0.85; salary: 1.12 to 1.35 and 0.86 to 0.98), plus the one feature at ≥1 in three of four (one QB). Mechanism: enough correlation to ride the QB, not so much that the lineup dies with him. Serves both. Cost: none observed. Confounders: four games; the DAL@NYG two-QB anomaly. Test: hold out the next 8 games; the three features' top-1% lift must be ≥1 in at least 6 of 8 each.

**I. Cap two-QB Showdown builds near the field share and never above 50%.** Result: 0.03 to 0.11x in two games, 1.45x in one, 0.95x in one; we ran 67% in DEN@KC after reading 64.8% off the DAL@NYG top 1%. Mechanism: two QBs is a "both offenses produce" bet with no hedge. Serves downside primarily. Cost to ceiling: forfeits the DAL@NYG-type game partially. Test: track the share of top-1% entries that are two-QB over the next 8 games; if it exceeds 50% in 6 or more, the cap is wrong.

**J. Classic: keep a chalk core and differentiate with one or two pieces, not three to six.** Result: top-1% rate by sub-5% count 2.08% (0), 1.49% (1), 0.90% (2), 0.58% (3), 0.43% (4) against a 1.00% base; we averaged 3.4. Mechanism: field ownership tracked actual points at Spearman 0.74. Serves both. Cost: more duplication in Classic (still 90% unique field). Confounder: one slate; the winner had three. Test: next 4 Classic slates, compare a 0-to-2 sub-5% portfolio with a 3+ portfolio built from the same projections; falsified if the 3+ portfolio's paid count or best percentile is better in 3 of 4.

**K. Classic RB bring-back and RB FLEX as defaults in the candidate bank.** Result: RB bring-back 2.20x top-1% and 3.14x top-0.1%; RB FLEX 1.25x / 1.47x; 9 of the top 10 had RB at FLEX. Mechanism: opposing RBs pay in both blowout and grind scripts of the stacked game. Serves ceiling. Cost: slight to paid rate (RB FLEX paid lift 1.07 vs TE 1.05). Confounder: one slate, Gibbs at 42.8% and 37.6 points. Test: 4 slates; falsified if RB FLEX top-1% lift is below 1 in 3 of 4.

### 8.3 Unsupported or contradicted ideas

Low ownership as leverage: contradicted in both modes (sections 4.3, 4.5). Unique lineups as ceiling: the worst feature on both objectives in every Showdown game and neutral in Classic. Excluding kickers and defenses: DST=1 had 1.34 to 2.87x lift in 3 of 4 games and was in 2 of 4 winning lineups; kickers had 1.24 to 1.66x in 2 of 4; both were policy-excluded or unused in every engine portfolio. 5-1 as the GPP split: 2 of 4. Both starting QBs as the default: 1 of 4. Captain under 5% as a differentiation play: captains under 3% were 0.00 to 0.19x in three games; the low-owned winning captains were either a 31.5%-rostered player (Likely, captained 4.0%) or a 4.6%-rostered one who won a single unshared first place (Robinson, captained 0.18%); the <3% captain band as a whole was 0.96x in that game and 0.00 to 0.19x in the other three. More Classic stacking as a rule: the aggregate 4.2x for QB+3 is a QB-selection artifact; within Burrow, Herbert and Mayfield more pass catchers meant fewer top-1% finishes. Reading next game's construction targets off last game's top 1%: it is the procedure that produced the DEN@KC v6 policy, and every target it set flipped.

### 8.4 Questions blocked by missing evidence

Expected dollar value of any lineup or portfolio (25 of 26 payout ladders missing). Ownership calibration of the engine (it emits no ownership on the operating path). True ceiling distributions and P(top 1%) for a construction (one outcome per slate; needs a simulator whose lineup and field-threshold respond to the same game outcomes, and 30+ settled slates to check its calibration). Whether the concentration effect in 5.3 survives adjustment for entrant skill (needs user-level history across slates). Why Likely was 0 of 20 in DAL@NYG (no run snapshot; cannot trace eligibility → prior → bank → selection). Whether the SF@LAR policy that shipped excluded Mac Jones (policy bytes not retained).

## 9. Next research cycle

Smallest useful captures, in order. Pull the two missing NE@SEA standings (193391019, 193391038) so the era's 74 entries are complete. Paste the payout ladder for every contest entered from now on into `contest/` at intake; the NE@SEA file is the schema. Emit per-run: the normalized policy bytes, the prior vector, the candidate bank, `max_person_share`, per-entry contest type and paid fraction, and the final submitted CSV hash. Register H1 and a 25% sleeve as the pre-stated challenger for the next 8 Showdown slates, with the incumbent expectation-only build generated from the same bank and stored (not entered) as the control. After each slate, compute the six checks in 8.2 from standings alone; no model is needed for any of them. Build the field-copy-count predictor (8.1 F) and grade it on the next 10 contests before any duplication term enters an objective. Begin the ownership challenger from the salary baseline in the earlier report, graded chronologically by slate, with mass conservation as a hard validity gate.

## 10. Source and methodology appendix

### A. Sources and hashes

Standings exports, `data/standings/inbox` (SHA-256 of the file as stored):

| Contest | Slate | File | SHA-256 (first 16) | Entries |
|---|---|---|---|---|
| 193028206 | Classic 09-13 | contest-standings-193028206.zip | 0cd410143f258cad | 832,342 |
| 193391013 | NE@SEA | contest-standings-193391013.zip | ee264b8bd9c9b819 | 126,020 |
| 195379585 | SF@LAR | .zip | 57cba3146ef638e0 | 237 |
| 195379668 | SF@LAR | .csv (loose) | c302f8ae07bbcca0 | 47 |
| 195384501 | SF@LAR | .zip | a1b7e2c51fec8bc6 | 71 |
| 195390867 | SF@LAR | .zip | 327c3f91f2daa0da | 83,234 |
| 195390868 | SF@LAR | .zip | 0ef6d0a433336cef | 178,359 |
| 195390870 | SF@LAR | .zip | 2e8739947eddd5db | 47,562 |
| 195390889 | SF@LAR | .zip | e3956d4481d5ef1d | 9,512 |
| 195507184 | SF@LAR | .zip | 7dcf5fc9f4ad110d | 237 |
| 195520918 | DAL@NYG | .zip | 549da82ec3349a03 | 475 |
| 195521582 | DAL@NYG | .zip | 3f7a1fec37c6d823 | 237 |
| 195526142 | DAL@NYG | .zip | 57a55a8cd1974bfb | 59,453 |
| 195526144 | DAL@NYG | .zip | 6f7124bac30ff496 | 35,671 |
| 195526145 | DAL@NYG | .zip | 9cb08c067fbdb12e | 35,671 |
| 195526163 | DAL@NYG | .zip | b2f3bc11feea31ad | 5,945 |
| 195641911 | DAL@NYG | .zip | 49168c79000f4660 | 237 |
| 195642262 | DAL@NYG | .zip | 00b005b95b5d93e8 | 190 |
| 195521607 | DEN@KC | .zip | 586b49dfe89c0f7b | 95 |
| 195526229 | DEN@KC | .zip | c88213a0b224c771 | 237,812 |
| 195526255 | DEN@KC | .zip | db5f47ccd783762c | 89,179 |
| 195526256 | DEN@KC | .zip | fff2ba8f5f019401 | 59,453 |
| 195526257 | DEN@KC | .zip | 49bb305577a511a2 | 59,453 |
| 195526271 | DEN@KC | .zip | c0d5ad94f7586ef0 | 8,917 |
| 195663904 | DEN@KC | .zip | 010502b305d1eeca | 237 |
| 195665148 | DEN@KC | .zip | b240d4254111302f | 71 |

Supporting files (full SHA-256): history `84ce7a814de29f8939e5ecf7b60a5f32844dfe7c8d079910bb5c1132c9cba6d4`; salaries NE@SEA `157298d43b5a52edd842d78755bf9c9111495263a5c138e1edbe7344d97c18cc`, SF@LAR `c394480831cb127a0bf1de2e95ef00c5758b3c1763bbeb23aee4f911d385072e`, Classic `3a1657170f4c92cd8db00aad7404e8913f377d8bc34d72b864152b71c8957c08` (identical to Downloads `DKSalaries nfl.csv`), DAL@NYG `cd536f91c2e9febfd3dc28a10a58496ee10deb2d079a8f86293c3a493ba95e55` (Downloads), DEN@KC `e5224b694004836f13beb3cb8f78ce75483f62c60a343bae0f496fd8d3442204` (Downloads `DKSalaries - NFL.csv`); submitted CSVs NE@SEA `cf33f3e598270d40ea117d86ccac4ebce640b479baa8539b630f828aed585b96`, SF@LAR final `4e7a5cfd499fe8b27136e1c35776715e5a3d0e1a6f7f3bccb59468f1efc8a266`, Week 1 LATESWAP_FINAL `34ecfb7e9a1b892755cfd52be2d5b0ff238295206d75ca6d67e1bbc750d63f7d`, Week 1 script output `d99d36926df2d07e60b458c5eb5dc41cb7b17c6f4f7f814e5eb48a9af8a6f845`, `build_portfolio.py` `46b3cf1c11af0e7691fccf7cc7514c44f47ced458f1854aecd8a90dbf384a33c`, DAL@NYG v6 `a96f9e704f773d11802679acb6aceb45de5d67a369640653222be2277d540f04`, DEN@KC v8_FINAL `4f5ab44f7003f5cd9dbad20bd0981d7ae9d08f48c06f557c48fa0b3231321204`; policies DAL@NYG v6 `1da9c48590f5bc8e28b1143f2130de7b8955ab522fd2024b33316c83ff206845`, DEN@KC v6 `119b901ac49d44f6bb74a5fddab6a40abaf3d45b29145d2344b22a9882095bc9`; payout ladder 193391013 `b4cbaf72d7d8746278b1619cbd1d784b18c432c3f4cdd71bdcc9d1834a0f8b38`. Run reports read: `data/runs/20260909T222153Z-ne-sea-live-excl20/prior_review/prior_review.json` and `selection/selection_report.json`, `data/runs/20260910-showdown-sf-lar/review/cowork_run.json`, `data/runs/20260913-week1-portfolio/outputs/PORTFOLIO_QA.json`, `docs/RUN_RECORD_20260914_DEN_KC.md`.

### B. Method

Python 3.10, pandas 2.3.3, numpy 2.2.6 on the device VM; scratch under `/tmp/work` (deleted with the session). Standings parsed with `encoding='utf-8-sig'`, all columns as strings; lineup strings split on `(?:^|\s)(CPT|FLEX|QB|RB|WR|TE|DST)\s`; DST names carry a trailing space in the export and were stripped. Player identity, position, team, salary and game come from the same-slate DK salary file by exact name; Showdown CPT salary from the CPT row. Team split is the count of players (including K and DST) on the Captain's team versus the other team. Pass catchers with QB counts WR/TE on the same team as any rostered QB. Bring-back counts non-DST players on the QB's opponent. Ownership, duplication, own-sum and sub-5% counts use the contest's own submitted lineups. Field-portfolio concentration (5.3) groups entries by the `EntryName` username after stripping the `(i/n)` suffix. Bootstraps use `numpy.random.default_rng(20260915)` and `(7)`, 4,000 replications, sampling entries with replacement so duplicated lineups carry their field frequency. Prize dilution uses DK's rule of pooling the prizes of all ranks occupied by a tie group and dividing equally. No fantasy outcome, final ownership or rank entered any filter labelled pre-lock (H1, H2, Classic H1). Intermediate outputs (`A_account.txt` through `O_ours_vs_field.txt`, `sd_consistency.csv`, `thresholds.csv`, `wk1_ownership_eval.csv`, per-contest ownership tables) were produced in the session scratch and are reproducible from the sources above with the code described here.

### C. Comparison with the same-day greenfield report

Numbers shared with `STANDINGS_GREENFIELD_FINDINGS_2026-09-15.md` agree exactly (corpus counts, 7.82 pp ownership MAE, 206-way tie, Gibbs 42.75%, Classic stacking rates, split tables, zero-DST exposure). This report adds: byte-exact provenance of every submitted lineup and the finding that Week 1 did not come from the archived build; the engine objective, its prior overshoot and the policy-cap mechanism behind the concentration; the cross-game consistency table separating stable hygiene from volatile script features; the field-wide concentration-versus-ruin measurement across 8,007 portfolios; prize dilution in dollars from the one ladder; the hygiene bootstrap frontier; and the finding that the DEN@KC policy was tuned to the prior game's realized script. Its Priority 1 items (validate ownership as probabilities, frozen prediction records, trace the missing scorers, attach the actual objective to each contest) are consistent with 8.1 A, B, D, E here; its salary-only ownership baseline is the right starting challenger for the ownership gap in 8.4.
