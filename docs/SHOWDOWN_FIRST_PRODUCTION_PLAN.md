# Showdown-first production plan

Companion to `docs/PRODUCTION_READINESS_REVIEW_2026-09-08.md`. That document says
what is broken. This one says what to build, in what order, for Showdown, and what
"production ready" can and cannot mean before the season produces settled slates.

Written 2026-09-08 against `codex/s6a-deterministic-projection-producer` at `f86fd9e`.

## 1. Two products, not one

The review's findings collapse into two deliverables with different completion clocks.

**Product A: source-bound prior-only Showdown review lineups.** Legal exact-ID
assignments, real names and Captain, reproducible frozen inputs, injury exclusions
applied before selection, honest blockers. Ends at `MODEL_STATUS=PRIOR_ONLY`,
`RELEASE_DECISION=DO_NOT_UPLOAD`. Ben reads the workbook and decides whether to
upload by hand. Reachable this week. This is DL3 through DL5.

**Product B: certified model-generated Showdown uploads.** Requires the field and
payout estimator to be correct (R05), the selection objective to stop depending on
compute budget (R07), the candidate bank to stop pruning to chalk (R06), the
simulator to reconcile events and honor participation (R10), and a validated model
artifact with a temporal holdout (R11, R12).

Product B is not reachable this week, and not because of coding capacity. R11
requires prospective validation against observed outcomes. There are no settled
2026 slates yet. Until several game weeks are captured and joined to the pre-lock
model version that produced each assignment, no promotion evidence can exist, and
`release.py` will keep blocking model-assisted certification, correctly. Writing
code faster does not move that date. Starting the capture loop does.

## 2. Why Showdown first is the right call

Verified in this checkout, not taken from the review:

- Showdown legality is done and covered: distinct CPT/FLEX DK IDs, exactly one 1.5
  multiplier (`economics.py:104`), underlying-person uniqueness, both-team
  requirement, salary cap.
- One game means no cross-game correlation structure to calibrate. The hardest part
  of R10 shrinks to intra-game dependence.
- The identity map is tractable. Showdown is roughly 63 people over two teams. The
  Classic pool in the same fixtures is 719 rows over 24 teams. R01 requires an exact
  frozen DK-ID mapping for every person including backups and kickers. Doing that by
  hand once for two teams is a morning; doing it for 24 teams is not.
- The two most damaging estimator defects are reachable through configuration on a
  single-game pool, which means they can be measured before they are redesigned.

Counterweight, stated plainly: Showdown is the format where field composition and
duplication matter most. The lineup space is small, ownership concentrates on a few
Captains, and exact-lineup duplicates are common. Showdown-first defers R05 for
Product A only. For Product B it makes R05 the center of the work, not a deferral.

Also: the registered Showdown workload in `config/runtime.json` is larger than
Classic (20k/50k/50k scenarios versus 10k/20k/20k) and the only measured run used
1k/2k/2k with 250 candidates against a 20,000 default bank. Showdown timing at
registered size is unknown, not fast.

## 3. What the review understates

**R05 cloning is a default, not an architecture.** `cli.py:1314` computes
`sample_size = min(opponent_count, args.field_sample_size)` and then calls
`scale_field_multiplicities(sampled, opponent_count)`. `--field-sample-size`
defaults to 1000 (`cli.py:2396`), and the Cowork paths hardcode 1000
(`cli.py:2031`, `cli.py:2275`). When the sample size reaches the true opponent
count, the scaling step becomes identity and the sample-as-population bias
disappears. `economics.py:115` already streams one scenario at a time with a
chunked field (`--field-chunk-size` default 128) and never materializes a
field-by-scenario matrix, so the ceiling here is CPU time, not memory.

Consequence for sequencing: measure the existing evaluator at true Showdown field
size with cloning off before committing to the S4A/S4B rewrite. If a 20,000-entry
Showdown contest settles in acceptable wall time, the remaining R05 work is the
sampler's ownership realism and the duplication model, not the settlement code.
That is a much smaller job than the review implies. Confirm it by measurement.

**R06's shortlist is worse for Showdown than for Classic.** `--shortlist-limit`
defaults to 250 (`cli.py:2398`) out of a 20,000-lineup bank, ranked by mean
projection then summed player p90 (`cli.py:1302`). In a six-slot single-game pool,
that prunes to chalk before economics ever runs. The code already permits 5,000
(`cli.py:1308`). Raising the shortlist is cheap; choosing the right diversity
criterion is the actual work.

**R07 should move earlier than P1.** `portfolio.py:128` builds the selection
objective as `mean - 1.96 * standard_error`, and `portfolio.py:189` picks the worst
state by that same quantity. The penalty shrinks with the square root of the
scenario count, so the compute budget is a hidden risk-aversion parameter. The
retained probe reproduces a selection reversal from replicating identical rows
(`.artifact-runtime/review-20260908/probe-results.json`,
`scenario_replication_changes_selection`: 1.5 chosen at 100 scenarios, 2.0 chosen at
10,000 replications of the same empirical distribution). Fixing this is small and it
silently corrupts every comparison made while measuring anything else. Do it before
the measurement work, not after.

**The manual-guardrail fallback has a live defect on its verification path.** The
retained probe `expired_evidence_audit` returned exit code 0, `EVIDENCE_STATE=PASS`
and `RELEASE_DECISION=CERTIFIED_UPLOAD_PACKAGE` on a stored manifest carrying
expired January evidence, on the `MANUAL_GUARDRAIL` basis. So the fallback path is
usable, but only by running a fresh certification immediately before upload. Never
treat an `audit` result as current readiness until R09 is fixed.

**Zero opportunity does not mean zero score.** The retained probe
`zero_capacity_kicker` shows a kicker with capacity 0 still averaging 7.99 points
across 984 of 1,000 scenarios. Combined with `simulation.py:84` requiring
`salary_people == model_people` exactly, this is the whole of R03: an unavailable
player cannot be removed from the model and cannot be zeroed by weight. It needs an
explicit participation mask. For Showdown the mask must cover both the CPT and FLEX
rows of the same person.

## 4. Track 1: pre-kickoff scope

Wednesday's opener is New England at Seattle, Wednesday September 9, 7:20 p.m.
Central. It is a single-game slate, so there is no Classic fallback that night.

Ordered by dependency. Nothing outside this list should be written before kickoff.

**T1.1 R01 real priors adapter (critical path).** `sources.py:18` allows exactly
four usable hosts, and they are sufficient for a single game:
`raw.githubusercontent.com` / `github.com` / `api.github.com` for nflverse
historical usage feeding player opportunity weights; `api.the-odds-api.com` for the
game total and spread feeding plays, pass rate and touchdowns; `api.weather.gov` for
weather; `api.sleeper.app` for activity and `injury_status`. The nflverse injuries
feed is dead after the 2024 season, so Sleeper is the activity source. DraftKings
hosts are prohibited (`sources.py:26`) and `AvgPointsPerGame` may not enter any
numerical path.
Exit condition: a deterministic adapter under `scripts/` produces the team-prior
JSON, the player-prior JSON and the frozen identity map for exactly the current DK
IDs, archives raw response bytes with hashes and captured times, and a repeat run
reproduces the derived bytes. Missing coverage fails with the named producer error.
No hand-typed numbers anywhere in the chain.

**T1.2 R07 objective repair.** Replace the LCB objective with a declared fixed risk
measure. Report Monte Carlo error separately. Small, and it unblocks trustworthy
measurement later.

**T1.3 R02 DL3 prior-only profile.** A third profile alongside `diagnostic` and
`registered` (`cowork.py:214`) that generates and selects on a declared, versioned
projection score and never touches `field.py`, `economics.py` or the portfolio
economics. Deterministic tie-breaking, canonical de-duplication, retained solver
status and input hashes, explicit behavior when the requested count exceeds the
legal bank.
Exit condition: an end-to-end Showdown request yields readable legal unique
assignments at `PRIOR_ONLY` / `DO_NOT_UPLOAD` with no field or payout call in the
trace.

**T1.4 R03 participation contract.** One exclusion contract consumed by projections,
solver, candidate generation and the sampler. Salary identities stay immutable;
unavailable people become ineligible for selection and score zero. Both Showdown
roles of a person move together. Redistribution only under a deterministic
evidence-backed rule with capacity checks, or not at all.
Exit condition: a high-projection inactive is excluded before selection, its CPT and
FLEX rows both, and a scratch refresh either produces a legal replacement or reports
explicit infeasibility. Test QB, WR, RB and K separately. The kicker case is the one
that currently fails silently.

**T1.5 R08 expiry propagation.** Carry `expires_at`, evidence scope and state,
transformation version and input bindings into the consumed contract, and
re-evaluate freshness at selection and certification time. The retained probe shows
a package whose source metadata expired 2026-09-05 accepted at a 2026-09-08 clock.
Priors built Tuesday for a Wednesday run make this live, not theoretical.

**T1.6 R04 real files and contest facts.** No actual Showdown reserved-entry
template exists in this repo; the review's fixtures were session attachments.
Needed: the Showdown salary CSV and reserved-entry CSV for the exact contest, plus
contest ID, full payout tiers, advertised value, field size, entry fee, ticket face
value if any, intended entry count and objective.
Exit condition: every requested Entry ID receives one valid assignment, original
bytes and prefilled cells preserved, byte audit and reparse pass, workbook and JSON
agree, and a near-lock rerun demonstrates the activity and freshness gates firing.

**Fallback if T1.1 is not producing reconciled inputs by Wednesday afternoon:** run
the manual-guardrail path. Ben picks the lineup, the engine certifies legality,
evidence and exact bytes. That path is built and tested. Certify fresh immediately
before upload and ignore `audit` until R09 lands.

## 5. Track 2: the upload path, ordered

1. **Measure before rewriting.** Run the current evaluator on a real Showdown pool
   at true field size with cloning off. Record wall time and memory at registered
   scenario counts. This decides whether R05 is a rewrite or a parameter plus a
   duplication model.
2. **R05 S4A reference settlement** with exchangeable-field, exact-tie, known-
   duplicate and boundary-rank cases agreeing with closed-form references, then S4B
   production estimation. Model strictly-above, ties, real duplication and chopping
   together.
3. **R06** canonical uniqueness at every bank boundary (the retained
   `candidate_identity` probe shows distinct tuples sharing one canonical lineup),
   objective-appropriate diversity, and enforced exposure and Captain-per-person
   caps during construction rather than in QA.
4. **R09** live pre-upload check that recomputes evidence state at the current clock
   and binds the actual assignment, template and locks.
5. **R13** stage budgets, measured peak memory and a real benchmark per supported
   entry count. A two-entry result does not certify 20-max or 150-max.
6. **R10** event and scoring reconciliation, participation modeling, measured
   dependence, and a validated treatment of DESIGN oversampling.
7. **R15 settlement capture, started Wednesday night.** Persist a version-bound
   settled dataset joined to the pre-lock model and assignment versions. The
   validation clock starts when capture starts, so this is the earliest-value item
   in Track 2 even though it is labeled P2.
8. **R11 and R12** binding minimum-evidence gates, slate-grouped splits with strict
   train-outcome availability, an untouched temporal holdout, then the model artifact
   registry and independently derived promotion status.
9. **R14** Sunday late-swap optimization, and the Classic-side slot-ordering issue.
   Not a Showdown-first item, but required before any Sunday Classic operation.

## 6. Decisions taken here

- Product A is the week's goal. Product B is not attempted before the season
  produces settled slates.
- R07 is pulled ahead of the Track 1 measurement work despite its P1 label.
- R15 settlement capture starts this week despite its P2 label.
- R05 is measured before it is redesigned.
- Classic (DL6 to DL8) stays behind Showdown. The identity-map cost is the reason.
- No feature work after the Wednesday rehearsal gate. Blocker repairs only.

## 7. Open items only Ben can supply

- **[BEN]** Contest ID, full payout tiers, advertised prize value, field size, entry
  fee and ticket face value for the intended Showdown contest.
- **[BEN]** Intended entry count and contest objective (cash, WTA, GPP, satellite).
- **[BEN]** Whether Wednesday is a live-money rehearsal or a dry run.
- **[BEN]** Any mandated exposures or exclusions.
- **[BEN]** the-odds-api credit budget. The free tier is 500 credits per month and
  the MLB skills already draw on the same key; cost is markets times regions per
  pull.

## 8. What not to do

- Do not spend the pre-kickoff window on a field-model rewrite while the priors
  adapter and the real entry template are missing.
- Do not move a prior-only generated assignment into the manual-guardrail path to
  get past the model gate. That certifies legality, not lineup quality, and
  describing it as production readiness would be false.
- Do not call any prior-only output EV, ROI, win probability or edge.
