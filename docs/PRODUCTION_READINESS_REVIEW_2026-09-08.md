# NFL DFS production readiness review — September 8, 2026

> **Superseded 2026-09-22, historical record.** Its R01 to R15 items and week plan are expired;
> `docs/ROADMAP.md` §3 records the disposition. Do not work from the lists below.

## Decision

**The project is not production ready for model-generated Showdown or Classic lineups that can be certified for upload.** It has a functioning diagnostic lineup generator, a substantially improved evidence and validation layer, and guarded export infrastructure. The numerical selection engine, live input preparation, and operational acceptance remain incomplete.

The practical deadline deliverable is a **source-bound, prior-only lineup review workflow**: legal lineups, clear player names and Captain assignments, reproducible inputs, injury exclusions, and an honest review package. This is the existing DL3–DL8 deadline scope. It remains `MODEL_STATUS=PRIOR_ONLY` and `RELEASE_DECISION=DO_NOT_UPLOAD` under the current release policy. It is not a completed production model.

A separate existing manual guardrail workflow can certify an operator-supplied assignment when its legality, authorization, and current evidence pass. That certification does not validate lineup quality. Do not move generated assignments into that path merely to bypass the model gate or describe that as completing production readiness.

Tomorrow's opener is New England at Seattle, Wednesday September 9, at **7:20 p.m. Central**. The weekend target is Sunday September 13. The opener timing was checked against the [Patriots' game preview](https://www.patriots.com/news/game-preview-patriots-at-seahawks-week-1). The supplied Showdown fixture also describes NE@SEA at that time; it still needs a current-download check and matching actual reserved entries.

| Intended use | Readiness today | What is missing |
|---|---|---|
| Parse salary files; validate roster legality and exact IDs | Working in Windows tests | Acceptance on the actual current contest downloads |
| Produce diagnostic Showdown assignments | Working in a synthetic rehearsal | Trustworthy live priors, an appropriate deadline selection profile, and activity handling |
| Produce prior-only lineups for human review this week | Incomplete; feasible implementation target, not a readiness claim | DL3, actual inputs, source freshness, and complete rehearsals |
| Certify an operator-supplied manual assignment | Existing guarded capability | Actual assignment, matching contest facts, and current official evidence |
| Certify model-generated uploads | Blocked | Quantitative repairs, validation evidence, and a real validated-model loading/promotion path |
| Optimize across several contests in one export | Unsupported | Per-contest contracts and joint allocation, or separately downloaded one-contest files |
| Reoptimize after a Sunday game has locked | Only a guarded writer exists | Operator-proposed replacement, eligible contest evidence, prior certified state; conditional optimization is unfinished |

No real-slate package was certified in this review. Real-package `FILE_VALID` has not been established; required live evidence is incomplete; available model inputs are prior-only; the release decision is `DO_NOT_UPLOAD`.

## Scope and current verification

Reviewed the active Windows checkout, operator entry points, parsing/contracts, source and projection flow, simulator, optimizer, candidate generation, ownership/field economics, portfolio selection, certification, late swap, workbook flow, settlement, validation/training, and runtime/state infrastructure. Inspected tests and ran the full suite plus independent adversarial probes and a synthetic Showdown workload. This is a workflow and code readiness assessment, not a live-slate model validation study.

Current checkout:

- Branch: `codex/s6a-deterministic-projection-producer`.
- HEAD: `f86fd9e` — `Implement S6A deterministic projection producer`.
- The tracked working tree was clean at review start.
- Local `main` is `500f73c`; remote-tracking refs show the same local baseline. GitHub's current merge state was not refreshed, so this is a local-checkout observation, not a claim about the current remote PR.
- No production source, test, configuration, supplied input, or existing tracker was edited. This report and isolated review artifacts were added. No staging, commits, pushes, installations, or DraftKings account actions occurred.

| Check executed in this review | Result | What it establishes |
|---|---|---|
| Full pinned Windows test suite | **171 passed, 1 skipped; 29.52 seconds** | Existing conventional, property, integration, and safety regression tests pass; the skip is the existing Windows symlink privilege case |
| Environment doctor through the Windows launcher | **PASS**, Python 3.13.7, SQLite integrity `ok`, WAL, workbook closed/absent | Local runtime can execute; long paths remain disabled |
| Whitespace/diff check | PASS | No tracked diff problems |
| Synthetic two-entry Showdown build, default Cowork diagnostic workload sizes | **74.52 seconds**, 250 candidates, 64 MILP seeds, 31,125 candidate pairs; 1,000/2,000/2,000 DESIGN/SELECT/REFEREE scenarios | The existing numerical build completes this reduced synthetic workload |
| Independent check of those Showdown assignments and proposed entry bytes | Both rosters legal; canonical lineups distinct; byte audit and reparse PASS | Showdown geometry and byte-writing work with a synthetic matching entry template |
| Independent quantitative and governance probes | Multiple defects reproduced below | Passing current tests does not settle these missing acceptance cases |

The synthetic proposed file was 251 bytes, SHA-256 `850eafd2148c7de871a0c069e780bfcb9ccf8518417610625eea321860f30f32`. It was checked in memory; no DraftKings upload CSV was persisted. The synthetic benchmark used invented test projections, entries, and payouts solely to exercise code. Its payout/probability numbers are not football forecasts or evidence of edge.

Still unverified: the actual Cowork/Linux runtime; a clean setup on that runtime; the real contest files; real-source acquisition and transformation; registered-size full refreshes; the intended entry count; process peak memory; complete official-evidence refresh; a real manual or model-assisted release package; and a real game-week settlement cycle. The system-level process-memory query was unavailable in this environment, so this review makes no measured peak-memory claim.

## What is already completed

The earlier review should not be treated as an unchanged defect list. The following work is present and has passing regression coverage:

- S1: ticket face-value plumbing, strict source-ledger shape and hash checks, request-path confinement, durable failure handling, and byte-line fidelity.
- S2: lock-derived late-swap cell authorization, prior-state binding, eligibility and team inactive evidence, and independent changed-byte audits.
- S3/DL1: centralized release policy, separate file/evidence/model/release truths, selected-player opportunity evidence, and advisory treatment of construction preferences.
- S6A/DL2: strict frozen-input projection transformation, exact provider-to-current-DK mapping checks, team-share normalization, atomic package publication, and APPG quarantine.
- Core Classic and Showdown legality: salary cap, slot eligibility, team/game requirements, underlying-person uniqueness, distinct Captain/Flex IDs, and one Captain scoring multiplier.

The supplied fixtures currently contain 719 Classic salary rows across 24 teams/12 games, 126 Showdown role rows representing 63 people, and two **Classic** reserved entries in one contest. The managed `data/runs`, `data/models`, and `outputs` locations had no live production packages beyond placeholders. Test caches and synthetic review artifacts are not live inputs or model history.

## Prioritized findings and completion criteria

P0 below means a blocker for the intended reliable live workflow. P1 means a required correctness or operational repair before the relevant production capability can be claimed. P2 means supporting work that can follow a tightly bounded, supervised deadline rehearsal. The priorities do not imply that existing release protections should be weakened.

### R01 — P0: The new producer starts from priors that still have to be obtained

**Evidence:** [projection.py:94](C:/Users/benja/Documents/Claude/nfl-dfs/src/nfl_dfs/projection.py:94), [projection.py:155](C:/Users/benja/Documents/Claude/nfl-dfs/src/nfl_dfs/projection.py:155), [projection.py:605](C:/Users/benja/Documents/Claude/nfl-dfs/src/nfl_dfs/projection.py:605), and [sources.py:106](C:/Users/benja/Documents/Claude/nfl-dfs/src/nfl_dfs/sources.py:106).

S6A is a genuine improvement, but it consumes custom team-prior JSON, player-prior JSON, and an exact frozen identity map. The team source already must contain plays, pass rate, efficiency, touchdowns, turnovers, sacks, markets, and weather. The player source already must contain opportunity weights and efficiency assumptions. The implementation validates and transforms those values; it does not derive them from raw historical or live provider data. Generic fetch/capture helpers do not complete that upstream workflow. The producer's tests supply synthetic priors and synthetic provider IDs.

**Required completion:** choose and implement the approved source-to-prior transformation, or obtain an appropriately permitted, already prepared source package and implement its deterministic adapter. Freeze its real raw evidence, version the transformation, cover every required person including backups and special positions, and resolve the current DraftKings identity map. Do not create plausible-looking numerical values in prose or substitute the synthetic fixtures.

**Acceptance:** a real NE@SEA source package, then the real Classic pool, produces the two input CSVs and reconciled ledger; missing source/mapping or unknown coverage fails with actionable errors. A repeated run reproduces the derived bytes. The inputs are still explicitly prior-only.

### R02 — P0: DL3 has not isolated deadline selection from defective economics

**Evidence:** [cli.py:1145](C:/Users/benja/Documents/Claude/nfl-dfs/src/nfl_dfs/cli.py:1145), [cli.py:1275](C:/Users/benja/Documents/Claude/nfl-dfs/src/nfl_dfs/cli.py:1275), [cli.py:1314](C:/Users/benja/Documents/Claude/nfl-dfs/src/nfl_dfs/cli.py:1314), [cowork.py:133](C:/Users/benja/Documents/Claude/nfl-dfs/src/nfl_dfs/cowork.py:133).

The current request supports `diagnostic` and `registered`. Both use the same ownership, field, payout, and portfolio machinery. Reducing scenarios does not remove the known errors in that machinery. Existing diagnostic lineup generation therefore is not the separate projection-led review profile called for by DL3.

**Required completion:** implement an explicit prior-only profile that uses a declared, versioned projection score to generate and select review assignments. Keep field payout estimates, duplication estimates, and return/probability objectives out of that profile. Make tie-breaking deterministic; retain meaningful solver status/gap and exact input hashes; canonicalize duplicates. Define what happens when the requested count exceeds the legal or supported bank.

**Acceptance:** end-to-end Showdown and Classic requests produce readable, legal, unique assignments with `PRIOR_ONLY`/`DO_NOT_UPLOAD`; the profile never invokes field/payout selection; repeated inputs reproduce the result; blocked runs retain useful diagnostics and no upload CSV. Include the activity and freshness work in R03/R08 in this deadline slice.

### R03 — P0: Official inactive evidence does not update the generation pool

**Evidence:** [cli.py:1190](C:/Users/benja/Documents/Claude/nfl-dfs/src/nfl_dfs/cli.py:1190), [cli.py:383](C:/Users/benja/Documents/Claude/nfl-dfs/src/nfl_dfs/cli.py:383), [opportunity.py:308](C:/Users/benja/Documents/Claude/nfl-dfs/src/nfl_dfs/opportunity.py:308), [simulation.py:83](C:/Users/benja/Documents/Claude/nfl-dfs/src/nfl_dfs/simulation.py:83).

The build loads the complete salary/model pool without applying official activity evidence. Activity is checked at certification after lineups have been selected. This correctly blocks a selected inactive, but does not regenerate a viable lineup or reallocate the inactive player's workload. The redistribution helper has no live caller. An independent probe removed a receiver with that helper and then called the simulator: it failed with `opportunity model does not cover the salary pool` because the simulator requires equality with the original pool.

**Required completion:** create one explicit participation/exclusion contract used by projections, solver, candidate generation, and any sampler. Preserve immutable salary identities while setting unavailable persons ineligible for selection and zero for simulated opportunity. Redistribute only under a deterministic, evidence-backed rule with capacity checks; keep both Showdown roles synchronized. Refresh lineup assignments when activity changes. A zero opportunity weight is not a sufficient eligibility flag; the current sampler clips zero weights upward and the simulator has no participation mask.

**Acceptance:** a high-projection inactive is excluded before selection; its CPT and FLEX variants are both excluded; active-player opportunity conservation passes; a missing/ambiguous official report remains blocked; a scratch refresh actually produces a legal replacement or an explicit infeasibility result. Test QB, receiver, RB, and kicker cases separately.

### R04 — P0: Actual contest acceptance is missing

**Evidence:** current fixture inventory; [dk.py:54](C:/Users/benja/Documents/Claude/nfl-dfs/src/nfl_dfs/dk.py:54); [cli.py:1879](C:/Users/benja/Documents/Claude/nfl-dfs/src/nfl_dfs/cli.py:1879); deadline items DL4–DL8 in the backlog.

The repository has a matching-game Showdown salary fixture but no actual matching Showdown reserved-entry template. It also lacks the live priors, approved current identity mappings, contest payout facts, and current official activity evidence required for an operational run. Today's synthetic byte test does not substitute for the real template.

**Required completion:** obtain fresh salary and reserved-entry downloads for each intended slate/contest, confirm contest-to-slate correspondence, and supply complete payout tiers, advertised prize value, field size, fee, contest ID, and any ticket face value. Establish the desired entry count and contest objective. Run the exact selected operator path on those files.

**Acceptance:** all requested Entry IDs receive one valid assignment, input/output hashes are retained, original bytes and prefilled/unauthorized cells are preserved, review workbook and JSON agree, and a near-lock rerun demonstrates the correct activity and freshness gates. Use separate original downloads for separate contests unless a governed splitting workflow has been implemented.

### R05 — P0 for economic optimization: Cloning sampled opponents distorts payouts

**Evidence:** [field.py:178](C:/Users/benja/Documents/Claude/nfl-dfs/src/nfl_dfs/field.py:178), [cli.py:1314](C:/Users/benja/Documents/Claude/nfl-dfs/src/nfl_dfs/cli.py:1314), [economics.py:126](C:/Users/benja/Documents/Claude/nfl-dfs/src/nfl_dfs/economics.py:126). This revalidates the earlier D-01 root cause.

The build samples up to 1,000 opponents, scales their multiplicities to the full contest, and settles candidates against those cloned scores. Multiplicity scaling does not estimate the unsampled upper tail. Artificial copies also enter exact-lineup duplicate counts.

**Independent reproduction:** using legal Classic rosters with controlled exchangeable scores, ten sampled opponents were expanded into 1,000 by making 100 copies each. For a winner-take-all prize of 1,001, the actual evaluator returned mean gross **92.26** across 12,000 scenarios. With 1,000 independent exchangeable opponents, the reference expectation is **1.00**. The measured first-place rate was 9.22%, versus the reference 0.0999%. This is a synthetic diagnosis of the estimator, not a claim about real NFL returns.

**Required completion:** S4A reference settlement and acceptance thresholds, then S4B production estimation. Model opponents strictly above, ties, actual lineup duplication, and payout chopping together. Keep exact enumerated-field settlement where appropriate. Validate a sampled estimator across field sizes and payout shapes before promotion; do not substitute an unvalidated Gaussian tail assumption.

**Acceptance:** exchangeable-field expected payout, exact ties, known duplicates, cash, top-heavy, satellite, and boundary ranks agree with reference calculations within predeclared Monte Carlo error. Increasing the opponent sample must converge toward the reference instead of changing the effective contest definition. This repair may be deferred only if R02's deadline profile does not use these economics.

### R06 — P1: Candidate generation and portfolio controls need a bounded redesign

**Evidence:** [cli.py:1275](C:/Users/benja/Documents/Claude/nfl-dfs/src/nfl_dfs/cli.py:1275), [cli.py:1303](C:/Users/benja/Documents/Claude/nfl-dfs/src/nfl_dfs/cli.py:1303), [portfolio.py:343](C:/Users/benja/Documents/Claude/nfl-dfs/src/nfl_dfs/portfolio.py:343), [qa.py:90](C:/Users/benja/Documents/Claude/nfl-dfs/src/nfl_dfs/qa.py:90).

Only 64 candidates are MILP seeds by default; most of a registered 20,000-candidate bank comes from the same sampler used for opponents. The economics shortlist is selected by mean projection, then summed player p90. That removes lower-mean alternatives before their contest contribution can be evaluated. Candidate merging uses raw roster tuples, while certification rejects duplicates by canonical lineup. A probe confirmed that swapping two legal WR slots produces different tuples with the same canonical lineup; the merge rule can count such permutations separately.

The selector supports one through 150 entries, no more than the shortlist. Exhaustive search is limited to one–three entries and at most 50,000 combinations; more entries use greedy additions and two exchange passes. Exposure envelopes are optional QA arguments and are not supplied by the live build. There is no complete user-facing portfolio cap contract, including combined person exposure across CPT/FLEX. One package supports one contest and one fee.

**Required completion:** canonical uniqueness at every bank boundary; objective-appropriate candidate diversity; explicit supported entry counts, exclusions, locks, exposure limits and Captain/person limits; enforce mandatory controls during construction/selection rather than hoping QA repairs them. Repair selection under S5 after S4B; reuse only the bounded legal pieces for DL3.

**Acceptance:** permutations cannot increase candidate count, repeated Captain variants count correctly by person, requested caps and entry counts are met or fail clearly, and a requested large portfolio is timed at its actual size. A single-entry or two-entry result cannot certify 20-max or 150-max operation.

### R07 — P1: Selection changes with simulation count for the same empirical outcomes

**Evidence:** [portfolio.py:123](C:/Users/benja/Documents/Claude/nfl-dfs/src/nfl_dfs/portfolio.py:123), [portfolio.py:281](C:/Users/benja/Documents/Claude/nfl-dfs/src/nfl_dfs/portfolio.py:281).

The selection utility uses mean net payout minus 1.96 standard errors. Its penalty shrinks with the square root of scenario count, so computation budget becomes part of the economic preference.

**Independent reproduction:** two candidates were given a fixed 100-scenario payout distribution. The selector chose the constant-1.5 candidate. Repeating those same rows 100 times, without changing the empirical distribution, made it choose the variable candidate with mean 2.0. This is a reproducible selection reversal, not merely a reporting change.

**Required completion:** separate the economic objective and risk preference from estimation uncertainty. Use fixed, declared risk measures/preferences for selection and report Monte Carlo uncertainty separately; account for dependent/repeated samples and effective sample size.

**Acceptance:** duplicating scenario rows leaves the economic selection unchanged; increased independent precision affects uncertainty, not a hidden risk-aversion parameter. Preserve paired comparisons where uncertainty is actually needed.

### R08 — P1, immediate for live input reuse: Source expiry is lost after production

**Evidence:** [projection.py:276](C:/Users/benja/Documents/Claude/nfl-dfs/src/nfl_dfs/projection.py:276), [projection.py:580](C:/Users/benja/Documents/Claude/nfl-dfs/src/nfl_dfs/projection.py:580), [contracts.py:104](C:/Users/benja/Documents/Claude/nfl-dfs/src/nfl_dfs/contracts.py:104), [evidence.py:311](C:/Users/benja/Documents/Claude/nfl-dfs/src/nfl_dfs/evidence.py:311).

The producer checks `expires_at` and evidence state against its supplied `as_of`, but its ledger entries omit that expiry/state. The downstream ledger validator checks URI policy, hashes, and future timestamps, not whether the original priors or mapping have expired. The input CSV retains `PASS` without the per-source expiry. Separate six-hour market checks do not cover every player or mapping expiry.

**Independent reproduction:** a package whose source metadata expired September 5 was accepted by `validate_source_ledger` at a September 8 clock. This did not make the whole model certify—the prior-only model gate still blocks it—but proves freshness is not preserved across this boundary.

The producer also references original source files through absolute paths; it does not archive those raw files inside its output package. Cowork snapshots the ledger itself but does not recursively freeze/rebase its referenced artifacts. Moving the package, removing the originals, or moving from Windows to Linux therefore needs explicit handling.

**Required completion:** preserve source expiry, evidence scope/state, transformation version, and input dependency bindings in a versioned consumed contract. Re-evaluate freshness at selection and certification time. Archive referenced sources under managed content-addressed paths and make resolution work in the chosen runtime. Keep historical replay time separate from a live release clock.

**Acceptance:** a package valid at creation becomes stale at its real expiry; neither a copied ledger nor a new market timestamp renews old player evidence. A copied self-contained package validates on the supported runtime without original attachment paths.

### R09 — P1: The audit command does not establish current upload readiness

**Evidence:** [cli.py:1765](C:/Users/benja/Documents/Claude/nfl-dfs/src/nfl_dfs/cli.py:1765), [cli.py:1792](C:/Users/benja/Documents/Claude/nfl-dfs/src/nfl_dfs/cli.py:1792).

`status` displays stored truth fields. `audit` checks output existence/hash, then feeds stored evidence/model truth into the release policy. It does not parse and re-evaluate all evidence expiry, current locks, the current assignment/template, or the full manifest contract. A stored green result can remain green after evidence expires. Its exit code also describes audit problems, not whether the release decision permits upload.

**Independent reproduction:** a deliberately constructed stored manifest with expired January evidence and a matching output hash produced `status=PASS`, `EVIDENCE_STATE=PASS`, and `CERTIFIED_UPLOAD_PACKAGE`. This probe tests the audit's trust in stored fields; it is not a real certified package.

**Required completion:** distinguish historical artifact integrity from a live pre-upload check. The live check must validate the manifest schema, recompute the appropriate evidence state at the current clock, and bind the actual assignment, template and locks. Surface the time and scope of each check clearly.

**Acceptance:** expired evidence or locked new assignments cannot receive a current upload-ready result; malformed manifests fail; a historical integrity check can remain useful without being represented as renewed certification. Until repaired, rerun the full appropriate certification workflow on refreshed inputs immediately before action.

### R10 — P1: Simulator realism and accounting do not support production probability claims

**Evidence:** [simulation.py:39](C:/Users/benja/Documents/Claude/nfl-dfs/src/nfl_dfs/simulation.py:39), [simulation.py:93](C:/Users/benja/Documents/Claude/nfl-dfs/src/nfl_dfs/simulation.py:93), [simulation.py:170](C:/Users/benja/Documents/Claude/nfl-dfs/src/nfl_dfs/simulation.py:170), [simulation.py:207](C:/Users/benja/Documents/Claude/nfl-dfs/src/nfl_dfs/simulation.py:207), [simulation.py:254](C:/Users/benja/Documents/Claude/nfl-dfs/src/nfl_dfs/simulation.py:254), and [scoring.py:43](C:/Users/benja/Documents/Claude/nfl-dfs/src/nfl_dfs/scoring.py:43).

The simulator uses hand-set factor distributions/correlations and an unvalidated DESIGN tail-weight adjustment. It awards fractional expected receptions and distance-averaged kicker scoring within individual scenarios, allocates all team turnovers to QBs as interceptions, and omits several categories handled by the separate scoring functions. These may be approximations for priors, but they change floor, ceiling, ties, and player relationships. Equal splitting across listed kickers is not a starter model. Exact zero opportunity is softened to a positive number, and there is no availability mask.

Accounting has improved: receiving touchdowns are actually checked against team passing touchdowns. However, the share-conservation diagnostic still checks normalized input totals rather than complete simulated stat/event conservation. Passing means and finite arrays do not establish calibrated outcome distributions.

**Required completion:** S7 event/count and scoring consistency, appropriate participation modeling, measured dependence and tail behavior, and a validated treatment of DESIGN oversampling. For the deadline profile, label projection scores as priors and do not reuse these draws as validated probabilities.

**Acceptance:** actual simulated count/event reconciliation, scorer parity on deterministic event fixtures, zero activity for excluded players, same underlying Showdown outcome across roles with one 1.5 multiplier, and separate Classic/Showdown temporal holdout calibration reports.

### R11 — P1: Validation and promotion helpers can pass inadequate evidence

**Evidence:** [model_validation.py:73](C:/Users/benja/Documents/Claude/nfl-dfs/src/nfl_dfs/model_validation.py:73), [learning.py:38](C:/Users/benja/Documents/Claude/nfl-dfs/src/nfl_dfs/learning.py:38), [training.py:27](C:/Users/benja/Documents/Claude/nfl-dfs/src/nfl_dfs/training.py:27).

Independent probes found:

- `validate_simulation_draws` returned `PASS` on **one observation**, skipping interval and tail evaluation with sample warnings.
- `evaluate_challenger` returned `promote=true`, tier `COLD`, and influence 0 with **zero comparable slates and prospective field gates false**, when the other caller-supplied booleans were true.
- `rolling_origin_splits` put observations with the **same outcome timestamp** into both training and validation. Checking only whether each feature precedes its own outcome does not prove that training outcomes were available at the validation prediction cutoff. The alpha-selection validation score is also not a separate untouched final holdout.

These helpers are not currently a path around the live `PRIOR_ONLY` block. They must be fixed before wiring them into production authority.

**Required completion:** minimum evidence must be binding for a validated claim; promotion must include sample/tier and field gates; split at slate/time groups and enforce strict train-outcome availability before validation prediction time. Add an untouched temporal holdout and hash-bound reports, instead of accepting operator booleans as model proof.

**Acceptance:** insufficient sample cannot pass, zero-history/failed-field-gate promotion is false, same-slate leakage fixtures fail, and every promoted artifact is tied to its data cutoff, mode, model version, and validation report.

### R12 — P1: Model-assisted certification has no validated-model loading path

**Evidence:** [cli.py:748](C:/Users/benja/Documents/Claude/nfl-dfs/src/nfl_dfs/cli.py:748), [cli.py:760](C:/Users/benja/Documents/Claude/nfl-dfs/src/nfl_dfs/cli.py:760), [release.py:99](C:/Users/benja/Documents/Claude/nfl-dfs/src/nfl_dfs/release.py:99).

The live CLI sets successfully loaded model inputs to `PRIOR_ONLY`. It does not load a prospectively accepted model registry artifact and derive `PROSPECTIVELY_VALIDATED`. The centralized release policy then correctly blocks model-assisted certification. Supplying every missing CSV cannot, by itself, produce a certified model package.

**Required completion:** after quantitative and validation repairs, implement the actual model artifact registry/loader and independently derived promotion status. Validate source/training cutoff, current mode, score/field model versions, accepted reports, and hashes. Do not add a command-line switch that merely asserts validation.

**Acceptance:** a correctly registered, independently validated test artifact follows the complete positive certification path; missing, tampered, stale, wrong-mode, or insufficient reports fail. A synthetic positive path proves software behavior only; live promotion still requires real validation evidence.

### R13 — P1: Registered workload deadlines and resource limits are not enforced

**Evidence:** [config/runtime.json](C:/Users/benja/Documents/Claude/nfl-dfs/config/runtime.json), [portfolio.py:384](C:/Users/benja/Documents/Claude/nfl-dfs/src/nfl_dfs/portfolio.py:384), [portfolio.py:402](C:/Users/benja/Documents/Claude/nfl-dfs/src/nfl_dfs/portfolio.py:402), [cli.py:1615](C:/Users/benja/Documents/Claude/nfl-dfs/src/nfl_dfs/cli.py:1615).

Registered counts are 10,000/20,000/20,000 scenarios for Classic and 20,000/50,000/50,000 for Showdown, plus 20,000 candidates by default. Today's 74.5-second Showdown run used only 1,000/2,000/2,000 scenarios and 250 candidates. It does not certify the registered workload.

The ten-minute refresh and pre-lock stop settings are not an enforced end-to-end build budget. `memory_limit_bytes` is reported after work; it is not a process memory cap. Large-entry selection repeatedly evaluates growing portfolios and pairwise entry comparisons without a wall-clock stop, making 20-max/150-max particularly important to measure. The bounded one–three-entry combination count is useful but does not bound the other branches' execution time.

**Required completion:** stage budgets, predictable failure/diagnostic results, cancellation/restart behavior, pre-lock computation cutoff, measured peak memory, and a real benchmark for each supported entry-count profile. Use the pinned Windows path for the immediate rehearsal unless actual Cowork/Linux acceptance is completed first.

**Acceptance:** the actual chosen workload completes within its declared refresh budget on the target machine; exceeding time or memory stops truthfully with retained diagnostics; no stale earlier output is presented as the new result. Registered-size and Linux timing remain unclaimed until measured.

### R14 — P1 for Sunday operations: Late-swap writing is not late-swap optimization

**Evidence:** [late_swap.py:241](C:/Users/benja/Documents/Claude/nfl-dfs/src/nfl_dfs/late_swap.py:241), [late_swap.py:324](C:/Users/benja/Documents/Claude/nfl-dfs/src/nfl_dfs/late_swap.py:324), [optimizer.py:227](C:/Users/benja/Documents/Claude/nfl-dfs/src/nfl_dfs/optimizer.py:227).

The implemented writer needs a prior certified manifest/output, a current fully prefilled template, a proposed assignment, verified contest eligibility, and current team inactive evidence. It preserves locked cells and rejects unauthorized changes. It does not generate the conditional replacement portfolio. A prior-only review package cannot seed this certified lineage. Do not assume all Showdown or Classic contests support the same edit rules.

Classic roster placement also sorts by position and salary, not lock flexibility; an early player can occupy FLEX while a later same-position player occupies a restrictive slot. This is legal, but can reduce available swaps. It belongs in the Classic deadline rehearsal.

**Required completion:** establish the exact Sunday operating path, including how the initial accepted assignment is recorded and how proposed replacements are generated/reviewed. Implement or explicitly defer conditional optimization; arrange equivalent pre-lock slots to preserve late-game flexibility. Keep actual eligibility authoritative.

**Acceptance:** an early/late-window drill preserves every locked byte, forbids locked-player additions/removals, handles one late scratch, and returns a truthful result when no legal replacement exists. Human changes on DraftKings must be reflected in a newly reconciled current state before subsequent governed operations.

### R15 — P2: State, settlement, and the operator handoff are incomplete

**Evidence:** [cli.py:1720](C:/Users/benja/Documents/Claude/nfl-dfs/src/nfl_dfs/cli.py:1720), [cli.py:1735](C:/Users/benja/Documents/Claude/nfl-dfs/src/nfl_dfs/cli.py:1735), [registry.py:21](C:/Users/benja/Documents/Claude/nfl-dfs/src/nfl_dfs/registry.py:21), [workbook.py:406](C:/Users/benja/Documents/Claude/nfl-dfs/src/nfl_dfs/workbook.py:406).

`settle` parses and hashes a supplied standings file and prints coverage; it does not persist a complete version-bound settlement/training dataset. The registry/state machine is exercised in tests but is not wired into live runs. There is no completed cache/invalidation/restart and observed-slate learning loop.

The workbook exposes slot IDs and diagnostic economic labels, with no complete names/role/exposure explanation for a prior-only review profile. Input paste ranges and output table formatting are sized for relatively small examples; large portfolios need actual review acceptance. README still reports 65 tests, and backlog baseline text describes S6A as uncommitted even though HEAD now contains it. The manual workbook path also needs timezone-input verification; an Excel date cell does not inherently preserve a timezone.

**Required completion:** a canonical run brief with current truths and one next action, robust state persistence and input-driven invalidation, frozen post-contest capture joined to pre-lock model/assignment versions, and a readable deadline report. Update operating documentation around the exact accepted profile and checkout. Keep research promotion inactive until its evidence exists.

**Acceptance:** interruption/rerun does not overwrite evidence or silently change a prior selection; settled outputs reconcile to the frozen run; the operator sees names, roles, IDs, salaries, exclusions, exposures, blockers and hashes; timezone and maximum-size workbook cases are verified. No weekly learning or calibration claim should follow from the current `SETTLEMENT_CAPTURED` message alone.

## Minimum completion sequence for this week

This order addresses the existing deadlines while preserving the release boundary. It is an implementation sequence, not an estimate that every item is already achievable from the available data.

| When | Required work | Concrete exit condition |
|---|---|---|
| Tuesday, September 8 | Obtain actual Showdown entries/contest facts and real source priors/mappings; preserve current salary download; confirm operator runtime and entry count | A complete, immutable input inventory with explicit missing-evidence list |
| Tuesday into Wednesday | Implement DL3 plus activity exclusions, canonical uniqueness, source expiry propagation, and readable prior-only output | Focused Showdown and Classic tests pass; no field economics used by the deadline profile |
| Before Wednesday's operational run | DL4 real-template rehearsal, including byte audit, repeated run, stale-source case, inactive-player refresh, and expected failures | Exact actual entry coverage; no duplicate people or role mistakes; timing and blockers recorded |
| Wednesday, September 9 | DL5 refresh approved sources and official reports; rerun the accepted profile; review every assignment; freeze implementation changes after rehearsal | Current review package and truthful release decision. A remaining hard blocker stays blocked |
| Thursday/Friday, September 10–11 | DL6 on the exact Classic slate; cover every required team/player, selected contest count, entry count, and caps | Legal source-bound Classic review assignments with per-game participation/lock handling |
| Saturday, September 12 | DL7 full Classic rehearsal at the intended size, plus early/late-window scratch and restart drills | Complete artifacts, measured timing, independent bytes, current-state and manual-action handoff |
| Sunday, September 13 | DL8 refresh and execute the accepted process; use only demonstrated repairs | Every entry accounted for; current evidence and exact hashes; explicit release/late-swap status |

For Wednesday, the highest-value work is **R01 + R02 + R03 + R08 + R04**, in that dependency order, with source preparation and profile implementation able to progress independently. Rehearsal must be the last gate before the operational run. For Sunday, add realistic entry-count/exposure support, per-game lock handling and the late-scratch drill. Do not spend the entire available window on a wholesale field-model rewrite while the real entry template and priors are still missing.

The full production path continues through S4A/S4B field economics, S5 candidate/portfolio repair, broader S6 real ingestion and model production, S7 calibration, relevant S8/S9 runtime/state work, validated-artifact certification wiring, and S10 complete game-week acceptance. Statistical evidence must actually exist; it cannot be replaced by passing unit tests or a calendar deadline.

## Inputs required from the operator or approved providers

- Current Showdown salary and reserved-entry CSVs, followed by the exact Classic files for each selected contest/slate.
- Contest ID, complete payouts, advertised value, field size, fee, and ticket value where applicable; desired count/objective and any user-mandated exposures or exclusions.
- Real approved source artifacts for team and player priors and an exact current-DK identity map. Approved deterministic preparation should gather what it can; ask the operator only for genuinely unavailable facts.
- Current official team reports at the relevant game windows, preserving observation times and exact player identities. The pre-lock compatibility parser accepts operator-supplied HTTPS references; it does not independently establish official-source authority. A probe using a nonofficial HTTPS domain passed that syntax check, so human verification of that source boundary remains necessary until strengthened.
- For any planned late swap: verified eligibility for the exact contest, a reconciled current filled template, and the required prior-state lineage.

## Evidence retained for follow-up implementation

- [Independent probe results](C:/Users/benja/Documents/Claude/nfl-dfs/.artifact-runtime/review-20260908/probe-results.json): field-cloning bias, scenario replication, canonical identity, inactive-helper incompatibility, expiry, audit, promotion, validation sample size, and same-time splitting.
- [Synthetic Showdown timing summary](C:/Users/benja/Documents/Claude/nfl-dfs/.artifact-runtime/review-20260908/synthetic-showdown-benchmark/benchmark-summary.json): actual diagnostic workload sizes and measured completion.
- [Synthetic Showdown byte QA](C:/Users/benja/Documents/Claude/nfl-dfs/.artifact-runtime/review-20260908/synthetic-showdown-benchmark/synthetic-byte-qa.json): legal unique assignments and exact in-memory byte verification.

The report's conclusions are based on current code and current probes. Earlier audit IDs and completed tranche names provide history only; repaired findings have not been carried forward as current defects.
