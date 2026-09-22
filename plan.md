# NFL DFS Greenfield Engine Blueprint — Red-Team Revision

> **Phase 0 to 5 sequence superseded 2026-09-22.** The architecture and safety sections below stay
> authoritative (authority #4); the work queue is `docs/ROADMAP.md`, and its §3 retires the phase list.

This document is the governing implementation plan for the local NFL DFS engine.

## 1. Critique Dispositions

| Critique recommendation | Decision | Revision |
|---|---|---|
| Replace Top-1%/break-even GPP frontier | **Accept diagnosis; modify remedy** | GPP frontier becomes robust scenario net payout versus elite-finish probability. Top-1% and washout remain reported; washout becomes a safety tiebreak, not a co-primary GPP objective. |
| Optimize one pure simulated-ROI score | **Reject** | A scalar built on an uncalibrated field would create false precision. Preserve a transparent Pareto frontier and uncertainty intervals. |
| Stress cold-start ownership | **Accept** | Use operator ownership brackets, multiple news/field states, and worst-state selection until calibration matures. |
| Start with a complex partial-pooling ownership model | **Modify** | Begin with an interpretable heuristic constrained to roster totals; introduce partial pooling only after standings evidence accumulates. |
| Replace live possession simulation with a copula/factor model | **Accept** | Use a vectorized heavy-tailed latent-factor simulator for live operation. Possession simulation becomes a deferred research challenger. |
| Require 25,000 scenarios in 15 seconds | **Reject as unverified** | Use end-to-end budgets measured on the operator machine: Classic rebuild at most 10 minutes, late swap at most 5 minutes, certification at most 2 minutes. |
| Prevent Excel locking failures | **Accept** | Workbooks are versioned outputs; operator input uses a separate staged file and explicit lock detection. No background workbook writes. |
| Treat route participation as unavailable in-season | **Accept** | Use explicitly named snap/target/air-yard proxies and manual role evidence. Never claim route fidelity from those proxies. |
| Model Showdown payout chopping | **Accept** | Score canonical lineup duplication and exact divided payouts. |
| Force Showdown salary no more than $49,600 | **Reject** | Salary left is a duplication feature, not a universal rule. Exact divided-payout simulation decides whether spending $50,000 is worthwhile. |
| Hard-code all QB stacks, bring-backs, DST rules, and game-total thresholds | **Modify** | Ensure candidate-bank coverage through registered construction families; do not universally exclude naked rushing QBs, no-bring-back outcomes, or rare coherent scripts. |
| Permit an LLM to assign role deltas | **Reject** | Qualitative tools may collect evidence only. Numerical role allocation is deterministic, source-bound, conserved, and bounded. |
| Freeze all model weights for the season | **Reject** | Automatically refit weekly using expanding historical data, but stage field-model influence and prohibit one-slate performance from driving deployment or rollback. |
| Make every promotion manual | **Reject per selected operating policy** | Retain automatic deployment with reproducibility, rolling-origin, calibration, drift, and multi-slate rollback gates. |
| Automate NFL.com injury/inactive retrieval | **Reject** | NFL.com prohibits systematic retrieval absent permission. Official game-day evidence is an operator paste; automation is corroborative only. [NFL.com terms](https://www.nfl.com/legal/terms/). |
| Use nflverse injuries as fallback | **Reject** | Its injury source died after 2024. Participation is also unavailable in-season, and depth charts use a changed timestamped schema after 2024. [nflverse availability schedule](https://nflreadr.nflverse.com/articles/nflverse_data_schedule.html). |
| Use Sleeper for daily injury data | **Modify** | Its free player endpoint is a once-daily secondary status signal, never the official inactive authority. [Sleeper API](https://docs.sleeper.com/). |
| Assume an existing The Odds API key | **Reject** | Manual market entry is the no-key primary path. An optional user-supplied free key may use the current 500-credit tier, but paid service is never required. [The Odds API](https://the-odds-api.com/). |
| Use direct `highspy` instead of SciPy’s wrapper | **Accept** | Use persistent models, MIP starts, objective updates, explicit deadlines, and incumbent retention. SciPy remains available for non-MILP statistics. [SciPy MILP limits](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.milp.html), [HiGHS MIP starts](https://ergo-code.github.io/HiGHS/dev/guide/further/). |
| Collapse evidence states and remove governance | **Reject** | `STALE`, `CONFLICTED`, and `UNKNOWN` have different operational remedies. Keep semantic states while implementing them in one local process. |
| Add degraded early releases | **Accept** | Deliver a useful legality/certification guardrail before simulation and field-model completion. |
| Upload a safe package early | **Accept with safety modification** | Upload a baseline after current-window inactives, target T-60, then make strict upgrades before T-10. An invalidated package can never remain “last certified.” |
| Add numeric QA and REFEREE semantics | **Accept** | Repairs require registered triggers and paired improvement. REFEREE can block but never trigger reselection. |
| Check OneDrive, long paths, and Excel locks | **Accept** | Setup preflight verifies all three. The current workspace is an ordinary directory, but this remains a recurring gate. |
| Copy “four DK CSVs” into fixtures | **Correct and accept** | There are five supplied artifacts: three CSVs and two rules text files. Preserve all five as content-addressed fixtures. |

## 2. Revised Architecture and Evidence Plane

### Local runtime

Build a single-process Windows application under `C:\Users\benja\Documents\Claude\nfl-dfs` using:

- Pinned Python 3.13.7 and `uv`.
- NumPy, Polars, and PyArrow for vectorized computation.
- `highspy` for persistent bounded lineup MILPs.
- scikit-learn and statsmodels for opportunity, calibration, and ownership models.
- Pydantic for contracts.
- SQLite plus Parquet for registries and large artifacts.
- openpyxl for versioned review workbooks.
- pytest and Hypothesis for conventional, property, and metamorphic tests.

Setup must detect sync/reparse status, available memory and processors, long-path support, Excel locking behavior, and SQLite safety. If sync software is detected, disable WAL and use atomic, closed-run transactions.

### Stable contracts

- `SourceArtifact`: raw-byte hash, source, license/terms decision, capture/effective times, per-record source timestamp when available, parser version, and coverage audit.
- `EvidenceRecord`: subject, field, value, source, expiration, hard/soft gate, reason, and `PASS | FAIL | UNKNOWN | STALE | CONFLICTED | NOT_YET_DUE | NOT_APPLICABLE`.
- `SlateContract`: site, mode, games, locks, scoring rules, salary hash, and player pool.
- `ContestContract`: Contest/Entry IDs, entry count, field size, fee, payout ranks, prize type/value, roster geometry, and contest objective.
- `PlayerIdentity` and `RoleVariant`: exact current DraftKings ID, underlying-person identity, team/position, CPT/FLEX identity, salary, and multiplier.
- `PredictionSnapshot`: frozen pre-lock features, opportunity distributions, fantasy-point scenarios, model version, and uncertainty.
- `ScenarioBank`: immutable purpose, seed, sample/importance weights, input/model hashes, and scenario counts.
- `PortfolioAssignment`: exact Entry-ID allocation, contest objective, exposures, stress-state results, and late-swap state.
- `CertificationManifest`: source/config/model/output hashes, evidence, solver proof, runtime/memory use, blockers, and final-byte hash.
- `SettlementBundle` and `ModelRegistryEntry`: immutable pre-lock forecasts, standings, evaluation results, challenger history, deployment tier, and rollback pointer.

Workflow:

`NEW → SNAPSHOTTED → RECONCILED → MODELLED → CANDIDATES_READY → SELECTED → QA_REVIEWED → CERTIFIED | DO_NOT_UPLOAD → LOCKED → SETTLED → GRADED`

The serialized `CERTIFIED` compatibility state is derived only from
`RELEASE_DECISION=CERTIFIED_UPLOAD_PACKAGE`. Every decision reports
`FILE_VALID`, `EVIDENCE_STATE`, `MODEL_STATUS`, and `RELEASE_DECISION`
independently. `FILE_VALID` proves only authorized legal exact bytes; a manual
guardrail package is a safety result, not an EV or model-performance claim.

### Source and operator policy

| Need | Operational source | Gate |
|---|---|---|
| DK salaries, entries, and rules | Operator-downloaded files only | Exact hashes, draft-group/template match, and roster-contract validation |
| Payouts and field size | Operator supplies contest details for the Cowork run request, or uses the fallback workbook/strict payout CSV | Complete rank coverage; monotonic tiers; advertised prize-pool or ticket-value reconciliation |
| Historical PBP, rosters, stats, snaps, schedules | Immutable nflverse releases through a pinned adapter | Schema, population, timestamp, and license audit |
| Weekly depth priors | Timestamp-aware 2025+ nflverse depth-chart adapter | Weekly prior only, never game-day authority |
| Practice/injury information | Operator-captured official team/NFL evidence | Source URL, capture time, exact identity, and structured status |
| Secondary injury corroboration | Sleeper player endpoint, at most once daily | Cannot independently produce `PASS` for game-day activity |
| Official inactives | Strict operator paste from official report | Primary current-lock hard gate; fuzzy identity is rejected |
| Weather | NWS API plus verified roof/stadium metadata | Required for outdoor/open-roof selected games |
| Market lines | Operator-entered book, spread, total, and observed time | Required for full model; optional free API adapter only when configured |
| Ownership | Cold-start heuristic plus operator ranges, later standings-derived model | Always uncertainty-banded; contest-conditioned |
| Qualitative news | Structured evidence packet | Cannot directly alter projections or evidence state without deterministic validation |

The inactive paste schema is:

`TEAM, PLAYER_OR_GSIS_ID, STATUS, SOURCE_URL, OBSERVED_AT`

It must validate against the frozen DK pool in under two minutes. Exact IDs are preferred; normalized/fuzzy name matches are proposal-only.

The five supplied artifacts become preserved fixtures with their original hashes. The supplied Classic template remains incompatible with Showdown, and Showdown export remains blocked until matching entries and payout details exist.

## 3. Modeling, Simulation, Fields, and Selection

### Opportunity model

DraftKings `AvgPointsPerGame` remains raw-only. Changing APPG must be proven unable to affect any downstream artifact.

Model opportunity separately from efficiency:

- Team plays, drives, pace, situation-adjusted pass rate, market scoring, spread, rest, weather, and era.
- QB dropbacks, designed rushes, scrambles, completion/air-yard efficiency, sacks, interceptions, and touchdown shares.
- RB carries, targets, snaps, inside-10 work, goal-line equity, two-minute role, and high-value touches.
- WR/TE target and air-yard shares, aDOT, red-zone/end-zone work, snap share, team dropbacks, and depth role.
- K drive-scoring and field-goal-distance processes.
- DST opponent dropbacks, sacks, turnovers, scoring drives, returns, and points-allowed outcomes.

Route participation is optional only when a timely, licensed source is supplied. Otherwise the model exposes `ROUTE_PARTICIPATION=UNKNOWN` and uses clearly named proxies with added uncertainty.

Role changes use deterministic team-share conservation:

- Removing an inactive player creates a bounded opportunity pool.
- Redistribution uses active depth, historical role capacity, position, game environment, and operator-approved evidence.
- Allocated carry, target, route-proxy, red-zone, and goal-line shares remain within `[0,1]` and reconcile to team totals.
- No natural-language output can write numerical shares or fantasy projections.

Add rule-era fields for kickoff/return regimes, overtime/scoring changes, and upstream schema eras. Rolling validation must never mix era-sensitive features without these flags.

### Fast live simulator

Use a vectorized heavy-tailed factor model rather than a live play-by-play engine:

1. Draw correlated team plays, pass/rush lean, scoring, yardage, and game-environment factors.
2. Draw team touchdowns, field goals, turnovers, and sacks using count models.
3. Allocate attempts, carries, targets, yards, and touchdowns through role-conditioned Dirichlet or logistic-normal shares.
4. Couple QB and receiver outcomes, opponents in shootouts, favored RB/DST scripts, and weather-sensitive positions through fitted latent factors.
5. Enforce aggregate accounting: team/player shares reconcile, passing/receiving touchdowns pair, and Showdown uses the same person outcome with the Captain multiplier once.
6. Convert outcomes through exact Classic or Showdown scoring.

Default scenario banks:

- Classic: `DESIGN=10,000`, `SELECT=20,000`, `REFEREE=20,000`.
- Showdown: `DESIGN=20,000`, `SELECT=50,000`, `REFEREE=50,000`.
- DESIGN uses stratified tail oversampling with recorded importance weights.
- SELECT and REFEREE use separate ordinary draws and RNG streams.
- Banks extend only when paired uncertainty can change the decision and runtime budget permits.

Acceptance requires:

- Rolling holdout proper scores better than salary/position and independent-marginal baselines.
- 50th/80th/90th/95th predictive interval coverage within five percentage points by position where sample size supports it.
- 95th/99th tail exceedance error within 20% relative on registered position/salary strata.
- QB–pass-catcher, opposing shootout, RB–DST, and negative DST/opponent correlation signs and magnitudes inside historical holdout bands.
- Failure produces `SIMULATION_DIAGNOSTIC_ONLY`.

A possession simulator is deferred unless this model cannot meet registered marginal-tail and dependency targets.

### Candidate construction

Use persistent `highspy` models, objective changes, MIP starts, and strict time/node/gap limits.

Candidate coverage families include:

- QB plus one and two pass catchers.
- Zero-, one-, and two-player bring-backs.
- Secondary game correlations.
- Rushing-QB and justified naked-QB lineups.
- Favored RB–DST scripts.
- Deliberately low-owned correlated alternatives.
- Showdown team splits, CPT archetypes, K/DST, low-total, shootout, and domination scripts.
- Salary-left and duplication-diverse Showdown constructions.

These are bank-coverage families, not universal rules. Hard constraints are limited to DraftKings legality, explicit contest policy, status exclusions, and independently justified safety constraints.

Showdown duplication is determined from complete canonical lineups, CPT identity, salary usage, construction archetype, and simulated field counts. Exact divided payouts replace any fixed salary-left penalty.

### Cold-start ownership and fields

Cold-start ownership is transparent:

- Player utility from salary/position rank, projection rank, points-per-dollar rank, team total, role change, injury-created value, and contest archetype.
- Constrained normalization ensures expected roster totals match legal roster sizes.
- Operator supplies low/base/high ownership brackets for important chalk and late-value players.
- Registered stress states include base, chalk surge, chalk fade, late-value surge, and sharper/smaller-field construction.
- Complete legal opponent lineups are generated using construction templates and canonical hashes.

Selection evaluates every portfolio in every field state. While `COLD_START_FIELD_MODEL` is active:

- Use the worst-state robust scenario net payout.
- Credit ownership, duplication, and field-leverage edges only when their direction is stable across all registered states.
- Do not call field-derived outputs EV, ROI, win probability, or calibrated ownership.

Field evaluation must never materialize a field-by-scenario matrix. Score unique opponent lineups in chunks, retain multiplicities and canonical hashes, and reduce each scenario to payout-rank thresholds and tie groups. Candidate scenarios are also chunked; only a bounded shortlist retains full float32 scenario vectors.

Default live limits:

- 20,000–50,000 generated candidates.
- At most 5,000 candidates retain full SELECT vectors for portfolio optimization.
- Peak live memory no greater than the smaller of 4 GiB or 50% of memory available at run start.

### Contest objectives

#### Large-field GPP

For fields of at least 50,000:

- Elite threshold: `K_elite = max(1, ceil(0.001 × field_size))`.
- Continue reporting top-1% probability and expected top-1% count.
- Primary frontier axes:
  - Robust scenario net payout after fees, exact ties, and duplication.
  - `P(any lineup reaches K_elite)`.
- Select the normalized Nash-product point on the statistically nondominated frontier.
- Within one paired standard error of that point, prefer the lower probability of a net portfolio loss and then the lower probability of losing more than 80% of fees.

#### Small-field GPP

- Elite threshold: `K_elite = max(1, ceil(0.01 × field_size))`.
- Use the same robust-net-payout versus elite-finish frontier.

#### WTA and satellites

- Maximize seat/prize probability and robust expected ticket value.
- Ticket face value enters portfolio payout; seat probability remains separately reported.

#### Cash

- Maximize probability of finishing above the exact cash line and robust net payout.
- Break-even and lower-tail risk remain primary rather than tertiary.

For one to three entries, evaluate all feasible singletons/pairs/triples from the bounded shortlist and avoid heuristic frontier search. Larger portfolios use marginal construction and bounded exchange search.

## 4. QA, Learning, Operations, and Delivery

### Quantitative QA

Each QA finding must have a registered trigger:

- Any selected-player hard evidence not `PASS` when due.
- Player/game exposure outside the robust optimal-exposure envelope without an explicit cap decision.
- Pairwise negative dependence below the registered historical band without stable tail contribution.
- Simulated p95 duplicate count that reduces divided payout below the entry fee.
- Salary left outside the field model’s p5–p95 range without robust scenario support.
- Ownership or market perturbation that changes the selected portfolio materially.
- Solver gap/deadline evidence outside the accepted limit.
- Final-byte or Entry-ID mismatch.

A repair is accepted once only when:

- The paired 95% confidence interval for robust SELECT net-payout improvement is above zero.
- Elite-finish probability does not deteriorate by more than one paired standard error.
- The improvement remains directionally consistent across every cold-start field state.
- The repair does not weaken evidence, legality, or deadline safety.

REFEREE is report-only and binding in one direction:

- It never causes reselection or tuning.
- A sign disagreement with SELECT on robust net payout, a safety condition, or a hard constraint blocks promotion.
- Differences within registered uncertainty are logged without repair.

### Automatic learning with guarded influence

After every operated slate:

1. Freeze standings, ownership, lineups, pre-lock predictions, scenario metadata, sources, models, and output bytes.
2. Reconstruct scoring and grade projections, opportunity, correlations, ownership, stack shapes, salary use, duplication, thresholds, payouts, and swaps.
3. Automatically create versioned challengers.
4. Use rolling-origin validation and proper scoring; realized ROI remains descriptive before 200 settled slates.
5. Automatically deploy only when reproducibility, integrity, calibration, and no-regression gates pass.
6. Never roll back from one anomalous slate. Statistical rollback requires a registered multi-slate degradation; integrity/hash failures may roll back immediately.

Field-model influence tiers:

- `COLD`: fewer than three comparable settled slates; worst-state stable-sign use only.
- `PROVISIONAL`: at least three comparable slates and out-of-sample improvement over the heuristic; field components capped at 25% influence.
- `GRADED`: at least ten comparable slates with ownership and construction reliability passing; capped at 50%.
- `CALIBRATED`: at least twenty comparable slates with prospective ownership, stack, duplication, and threshold calibration passing; full registered influence.

Contest archetypes back off to broader priors when their own sample is insufficient.

### Operator surface

Claude Cowork is the primary operator surface. The operator attaches one salary
CSV and one reserved-entry CSV; Claude discovers them by schema, preserves exact
bytes, gathers permitted public evidence, drives deterministic code, and returns
a versioned review package. The PowerShell/workbook path remains a supported
manual fallback.

Provide one Cowork `cowork-run` workflow with explicit checkpoints:

1. Intake and reconcile.
2. Write a machine-readable run request and name missing hard facts.
3. Gather and freeze permitted evidence; accept the smallest unavailable
   contest facts from the operator.
4. Build or refresh using validated deterministic inputs.
5. Select and QA.
6. Certify exact final bytes.
7. Display the manual-upload package and blockers.

The legacy `run` workflow retains these checkpoints for manual operation:

1. Intake and reconcile.
2. Accept staged operator evidence.
3. Build or refresh.
4. Select and QA.
5. Certify.
6. Display the manual-upload package and blockers.

Specialized commands remain for setup, status, audit, build, late swap, settlement, and learning.

MVP workbook sheets:

- `Run Control`
- `Evidence Paste`
- `Portfolio`
- `QA`
- `Upload`

For Cowork, the versioned run request is the primary input and the workbook is a
timestamped review artifact. For the manual fallback, operator changes are made
in a separate staged input workbook/CSV that must be closed before ingestion. A
lock produces a readable stop message, never a crash or partial update.

### Game-day cadence

- T-24 to T-3 hours: build baseline projections, ownership states, candidates, and contingency swaps.
- Approximately T-110: operator pastes official early-game inactives.
- Target T-60: build, certify, and manually upload a conservative baseline package.
- T-60 to T-10: later news or model refreshes may produce strict upgrade packages.
- At T-10: stop discretionary optimization; accept only evidence-required emergency contingencies.
- If evidence invalidates the last package, it is no longer certified. Use a separately validated contingency excluding unresolved players; otherwise emit `DO_NOT_UPLOAD`.
- After early lock: run conditional late swap for future games using locked-cell immutability and operator-supplied current contest state.
- Post-contest: settle, grade, and run the versioned weekly learning cycle.

### Delivery sequence

0. **Cowork operationalization**
   - Add root `CLAUDE.md`, the Cowork runbook, and a Linux launcher pinned to the
     same Python and lockfile as Windows.
   - Discover uploaded CSVs by schema rather than filename; reject duplicate or
     ambiguous candidates and snapshot recognized inputs before work begins.
   - Drive intake, build, QA, and certification from a strict versioned run
     request. A two-file-only run must create a useful review package while
     remaining `DO_NOT_UPLOAD` when contest or current evidence is missing.
   - Keep the workbook and PowerShell flow as the manual fallback, not a hidden
     requirement for Cowork operation.

1. **Safety guardrail**
   - Preserve all five fixtures.
   - Implement rule/scoring contracts, payout intake, manual-lineup validation, exact ID/template checks, independent final-byte certification, and the minimal operator workflow.
   - Usable result: hand-created lineups can be safely checked and exported before predictive modeling is complete.

2. **Classic manual-mode MVP**
   - Add nflverse snapshots, opportunity projections, role overrides, market/weather inputs, vectorized factor simulation, candidate families, and exhaustive two-entry selection.
   - Field-dependent metrics remain cold-start diagnostics.

3. **Field and contest economics**
   - Add ownership brackets, complete opponent fields, order-statistics payout evaluation, exact duplication/ties, GPP/WTA/cash objectives, and larger portfolios.

4. **Late swap and Showdown**
   - Add conditional Classic recourse.
   - Activate Showdown selection/export only when matching Showdown entries and payout evidence exist.

5. **Settlement and learning**
   - Add immutable standings settlement, model grading, tiered ownership/field influence, versioned weekly refits, automatic deployment gates, and rollback.

No later phase may weaken the safety guardrail delivered in Phase 1.

### Acceptance and performance gates

- Supplied fixtures parse to 719 Classic IDs, 24 teams, 12 games, two authorized Classic entries, and 63 Showdown people with 126 valid CPT/FLEX rows.
- Classic/Showdown template mismatch is rejected.
- APPG mutation changes no downstream artifact.
- Payout tables cover all paid ranks, reconcile advertised value, and support cash and ticket prizes.
- Scoring fixtures cover every supplied rule, bonuses, K, DST, returns, ties, and Captain multiplication.
- Every selected-player identity and current status is exact and source-bound.
- Simulation passes marginal, tail, dependency, era, and reproducibility tests.
- Ownership fields are legal and reproduce registered player, role, stack, salary, pair, and duplication targets appropriate to their calibration tier.
- Exact toy-field settlement matches exhaustive payout and tie calculations.
- No field-by-scenario matrix is materialized.
- Full Classic refresh completes within 10 minutes; late swap within 5 minutes; independent certification within 2 minutes on the operator machine.
- Excel-open, sync, long-path, interruption, restart, and insufficient-memory tests fail safely.
- A fresh Cowork session can accept arbitrarily named salary and entry CSVs,
  preserve exact hashes, reject ambiguous/mismatched inputs, and leave a
  versioned `DO_NOT_UPLOAD` review package without requiring Excel edits.
- Cowork/Linux and Windows launchers execute the same CLI and contracts; neither
  may silently use an incompatible environment or reduce the legal player pool.
- Locked late-swap cells and unauthorized Entry IDs remain byte-identical.
- The certifier reparses exact final bytes and records their SHA-256.
- Qualitative evidence without a verifiable source remains `UNKNOWN`.
- Automatic learning cannot promote leakage, schema drift, one-slate ROI noise, or an unreproducible artifact.

### Locked defaults

- Broad contest support remains: GPP, WTA/satellites, and cash.
- Reserved entries only; contest choice and money movement remain manual.
- A manual contest-screening checklist will show rake, overlay, payout concentration, field size, maximum entries, and ticket utility because contest selection materially affects returns even though it remains out of scope.
- Satellite tickets use face value.
- Field-dependent outputs remain diagnostic until their tier gates pass.
- Exposure caps are guardrails; scenario contribution drives diversification.
- DraftKings login, entry, editing, and upload remain manual.
- The current workspace contains this plan, both preserved critiques, source code, tests, immutable supplied fixtures, templates, and operator documentation.
