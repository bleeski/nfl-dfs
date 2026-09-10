# Implementation Status

## Current development program — 2026-09-10

DEV0 is complete on merged `main` commit
`7f083fbd77620d96e3f0571f09d93fdaeb32e377` (PR #9; reviewed source
`652c855`). That baseline retained the excluded user/generated paths and
recorded `516 passed, 1 skipped` plus doctor, compile, and whitespace checks. Q1
is now complete on `codex/q1-settlement-reference-economics`: focused tests
passed 46/46 and the final full suite passed `542 passed, 1 skipped` in 117.86s;
doctor, compile/import, whitespace, mutation, overwrite, and copied-package
replay checks passed. C1 is the sole `READY` item. Every later item remains
blocked.

## Current Showdown readiness — 2026-09-09

The recorded pre-SD2 real NE–SEA two-entry template completed `cowork-run --profile
prior_review` through source acquisition, projection, selection and independent
review export. The repeated export is byte-identical; only the two reserved
entry rows change. See `docs/READINESS_REVIEW_2026-09-09.md` for the current
verification, fixes and limitations. SD2 requires fresh history coverage and
role evidence when roles changed; that older rehearsal does not establish
current live SD2 readiness. Older supplied-fixture counts below are
historical. This verifies Windows execution, not the actual Cowork/Linux VM.

The generated portfolio is still `PRIOR_ONLY / DO_NOT_UPLOAD`. Its objective
maximizes points of an expected stat line, with structural differentiation;
it is not the required calibrated ceiling/ownership/drawdown engine. Current
official activity, prospective validation and the quantitative redesign remain
blocking work. Supplied current official inactive rows now affect both roles
before prior-review selection. The older simulation/build path still needs its
own participation and economics repairs.

SD1 now gives the prior-review scorer one conserved team kicker event line.
Exact, source-bound current-role evidence can declare a sole kicker or an
explicit numerical split; ambiguous multi-kicker teams block, zero-share and
excluded people cannot be selected, and the single-kicker compatibility path is
reported only as an `UNKNOWN` prior assumption. This is a scoring/input-integrity
repair, not completion of offensive roles or live current-role modeling.

SD2 adds `nfl_offensive_role_evidence_v1`, strict captured numerical allocations,
five distinct current-role states, current-team-only historical denominators,
missing-efficiency gates and preserved unallocated volume. It removes generic
historical redistribution from the prior-review and standalone prior-selection
paths. Historical snap share is diagnostic only. Source-supported adjustments
run after all existing exclusions, and expiry/hash changes block review export.
The real freeze/project/select/export code has been exercised on portable,
clearly labelled synthetic captures, including the frozen LA/LAR team crosswalk.
See the Showdown priority tracker for final verification results. Live compatible
numerical offensive-role captures and actual Cowork/Linux acceptance remain
unverified. W3's simulator mask and full forward-role model remain incomplete.

SD3 adds the exact-bound `nfl_showdown_portfolio_policy_v1` contract. It binds
the immutable salary SHA-256, single game, complete underlying-person/CPT/FLEX
identity map and full requested Entry-ID sequence; normalizes numeric fractions
with exact-decimal floor rounding; reports declared and effective combined-person
and Captain limits; and defines canonical lineup, uniqueness and pairwise-person
overlap semantics. Necessary capacity findings do not claim solver infeasibility.
SD4 now enforces the normalized contract in the Showdown `prior_review` profile
through a bounded legal candidate bank and one joint MILP, assigns the exact
Entry-ID sequence without cycling, and independently re-audits every control and
bound artifact immediately before export. Feasible results remain optimal only
over the reported actual bank; incomplete-bank exhaustion is not called full-
slate infeasibility. Policy-free SD1/SD2 behavior is unchanged.

SD5 adds a readable review layer without changing selection or release policy.
After a valid prior-review export, it independently reparses the exact salary,
entry, assignment, exported review CSV, selection report, normalized policy and
policy audit; rechecks every bound hash; and recomputes lineups, salaries,
combined-person/Captain exposure, uniqueness and pairwise overlap before any
display is marked `PASS`. The generated package contains canonical JSON, escaped
self-contained HTML and an eight-sheet workbook with exact assignments,
exposure, evidence/role observations, provenance, all four release truths and
one next action. A mismatch fails closed at `READABLE_REVIEW`, preserves earlier
artifacts and returns no top-level review-export path. The layer remains
`PRIOR_ONLY / DO_NOT_UPLOAD`; actual Cowork/Linux and current real-evidence
acceptance are SD6.

## Working and locally verified

- The red-team revision has replaced the prior `plan.md`.
- All five supplied DraftKings/rules artifacts are preserved byte-for-byte with
  a checked SHA-256 manifest. Repository attributes now disable text conversion
  for byte-sensitive CSV, workbook, and supplied-fixture paths. Both critiques
  remain preserved.
- `nfl.ps1` provides setup, guided run, intake, validation, build,
  certification, audit, governed late swap, settlement capture, learning gates,
  and tests through one Windows launcher.
- `nfl.sh` provides the pinned Linux/Cowork launcher. `cowork-run` discovers
  arbitrarily named CSV attachments by first-row schema, rejects ambiguous
  duplicates, snapshots every recognized input, and writes a normalized
  `nfl_cowork_run_request_v1` request for deterministic reruns.
- The Cowork path can chain a complete supplied request through diagnostic or
  registered build, REFEREE QA, and certification. An incomplete two-file run
  produces a versioned review workbook and `cowork_run.json`, names every
  blocker, and leaves no upload-shaped CSV.
- Cowork model-assisted runs require a frozen source-ledger artifact; the
  ledger, team projections, and player opportunities are independently hashed
  into the certification manifest. Hash binding does not by itself validate an
  external source's truth or license.
- `nfl.ps1 project` / `nfl.sh project` now provide the minimum S6A producer.
  Four immutable hash-pinned inputs (salary, team prior, player prior, and exact
  frozen identity map) are validated without network access; position-eligible
  weights are deterministically conserved to team shares; exact Classic or
  Showdown FLEX identities are enforced; and both loader-valid CSVs plus the
  strict source ledger are atomically published only after independent hash and
  contract reconciliation. DraftKings APPG remains raw-only.
- Classic and Showdown salary contracts enforce exact IDs, geometry, salary
  cap, underlying-person identity, distinct CPT/FLEX IDs, and exact 1.5x Captain
  salary/scoring behavior.
- Showdown kicker-role evidence binds the salary hash, game/team, underlying
  person, exact CPT/FLEX IDs, allowlisted captured source bytes and hashes,
  observation/capture/expiry times, and transformation version. Allocation is
  applied to team scoring events before DraftKings scoring and the Captain
  multiplier, conserving base team kicker points exactly once. Supplied invalid,
  stale, future, tampered, incomplete, or newly ineligible allocations fail
  before assignments/review export; Cowork snapshots the manifest and sources
  for path-independent replay.
- Showdown portfolio-policy inputs are path-confined, copied into immutable
  content-addressed snapshots, validated against all requested entries and exact
  role identities, and written as stable normalized bytes with source and
  normalized SHA-256 values. The `prior_review` selector uses the exact SD3
  integer maxima over a default 32-candidate bank, reports generation and joint-
  solve budgets/status/coverage, and permits Captain repetition only when the
  effective Captain maximum allows it. Immediately before export, a separate
  audit strictly reparses the canonical normalized-policy artifact, re-reads exact
  assignment bytes, recomputes legality, exposure, Captain, canonical-uniqueness
  and pairwise-overlap facts, reconciles selector summaries, and binds salary,
  entry, source-policy, normalized-policy and assignment hashes.
  Only `ENFORCED_AND_INDEPENDENTLY_AUDITED` can reach the review-entry writer.
- One build/certification package is deliberately limited to one Contest ID and
  one entry fee. Mixed-contest exports fail closed until per-contest economics
  and allocation are implemented.
- Payouts enforce contiguous paid ranks, monotonic tiers, advertised-value
  reconciliation, finite exact-cent cash values, whole ticket counts,
  field-size bounds, cash/ticket distinction, and exact tied-rank division.
- Q1 settlement capture consumes a strict hash- and version-bound request and
  atomically publishes a never-overwritten copied package containing every
  salary, reserved-entry, payout, assignment, pre-lock prediction/model,
  scenario, metric-registry, and complete standings artifact. It rejects
  contest, draft-group, mode, Entry-ID, artifact, version, rank, prize, and
  source-mutation disagreement. The generated machine-readable brief and
  package-relative replay request reconstruct without conversation history.
- The Q1 reference evaluator is independent of the vectorized production
  economics path. Decimal six-place score rounding, strict-above ranks, exact
  tie occupancy, rational-cent cash/ticket division, complete-lineup
  duplication, and multiple owned entries are evaluated exactly within an
  explicit size/work/runtime budget or refused with a named blocker. A copied
  package must reproduce the same semantic assignment and reference-result
  hashes.
- `config/metric_registry_q1_v1.json` predeclares player-outcome,
  participation, ownership, duplication, rank/payout-tail, portfolio-risk,
  runtime, and memory metrics with uncertainty, ESS, temporal split, sample,
  promotion, noninferiority, demotion, and rollback requirements. `learn`
  refuses a registry that did not precede challenger evaluation. No model was
  promoted.
- Manual assignments can be independently validated and exported into only the
  blank, authorized Entry-ID rows. Untouched lines preserve their exact bytes,
  including original BOM state. The final CSV is reparsed and SHA-256 bound.
- Certification reports `FILE_VALID`, `EVIDENCE_STATE`, `MODEL_STATUS`, and
  `RELEASE_DECISION` independently. Legal proposed bytes are constructed,
  audited, reparsed, and hashed in memory even when evidence or model blockers
  require `DO_NOT_UPLOAD`; no upload-shaped CSV is persisted in that case.
- Governed late swap has a separate fail-closed writer for fully prefilled
  DraftKings bulk-edit templates. It binds a prior `CERTIFIED` manifest and
  assignment, derives replaceable cells only from exact IDs and lock times,
  preserves locked and unauthorized bytes, independently audits and reparses
  the candidate bytes, and writes a new immutable output only after every gate
  passes. The ordinary pre-lock writer still rejects prefilled rows.
- Hard evidence is typed and fail-closed. Current official status uses exact IDs
  and operator-controlled source evidence; fuzzy names cannot certify. Official
  activity rows retain their real observation times and expire after the
  registered three-hour lock window. Market/weather rows are bounded,
  enumerated, source-ledger-bound, and expire after six hours.
- Late swap additionally requires source-bound eligibility for the exact
  Contest ID and versioned team-scoped official inactive negative lists.
  Explicitly empty team reports are supported; missing teams remain unknown,
  report freshness is T-90/lock-relative, and `NOT_YET_DUE` cannot clear a
  final late-swap release decision.
- Model-assisted certification requires `PASS` opportunity evidence for every
  selected player. Non-PASS uncertainty elsewhere in the salary pool is
  counted and retained as a prior-only model limitation rather than mislabeled
  as selected-player hard evidence. The build report is bound to the exact salary, entry,
  payout, team, and player input hashes plus the contest parameters; a report
  from a different build cannot clear certification.
- The live model path uses explicit opportunity inputs, deterministic team-share
  conservation, a vectorized heavy-tailed simulator, separate DESIGN/SELECT/
  REFEREE banks, direct persistent HiGHS MILPs, candidate-family coverage,
  cold ownership stress states, complete legal opponent lineups with
  multiplicities, exact duplication/ties, and contest-aware portfolio metrics.
  Multiple reserved entries are settled against one another as well as against
  the simulated opponent field.
- The field evaluator retains no field-by-scenario matrix. Full candidate banks
  are reduced before scenario/economics arrays are retained. Candidate and field
  scores use the same float64 gather/sum path, ranks are vectorized, and divided
  payouts use a vectorized cumulative prize table.
- Quantitative QA is executed after selection, persisted in the build report,
  and hash-bound into certification. REFEREE remains report-only in the sense
  that it cannot tune or reselect, but its independent confidence-aware sign or
  genuine safety disagreement is a binding promotion blocker. Solver proof is
  persisted. Construction preferences such as `DST_OPPOSING_PASS_STACK` and
  candidate-family coverage are advisory unless a registered hard policy is
  enforced by the solver and validator.
- Exact one-to-three-entry search is exhaustive only inside an explicit bounded
  shortlist (maximum 50,000 combinations); combinations are evaluated in
  vectorized batches and the effective search size is reported.
- The five-sheet operator-input workbook remains the stable staged-input
  contract. A successful Showdown `prior_review` output extends its copied
  review workbook to eight sheets: exact Portfolio rows, Exposure, Review
  Evidence and Artifacts sit beside Run Control, Evidence Paste, QA and Upload.
  Formula-active prefixes and markup are inert at the display boundary; exact
  identities and source bytes stay in the hash-bound artifacts. The output has
  explicit print areas, repeated headings and normalized freeze panes, opens
  normally in native Excel, and renders without formula errors.
- Versioned Parquet scenario storage, rolling-origin challenger fitting, model
  promotion tiers, multi-slate rollback rules, Q1 settlement capture, and
  locked-cell late-swap audit are implemented. The SQLite registry and lifecycle
  transition guard are library components exercised by tests but are not yet
  wired into live runs.

## Deliberately diagnostic or externally gated

- No supplied contest payout table, field size, or official current activity
  evidence exists. Therefore no real supplied-slate upload is certified.
- The Cowork instruction and orchestration layer does not manufacture those
  missing facts. A salary-plus-entry first pass is expected to remain
  `DO_NOT_UPLOAD` until Claude freezes approved evidence and the operator
  supplies any unavailable contest-specific facts.
- The supplied entry template is Classic. Showdown upload remains hard-blocked
  until matching Showdown entries and payouts are supplied.
- Opportunity, field, ownership, duplication, and payout predictions remain
  diagnostic until prospective historical/live validation clears the registered
  sample and calibration gates. The engine does not label them EV, ROI, win
  probability, or calibrated ownership.
- SD1 does not produce current offensive roles. A live slate still needs current
  approved kicker-role captures when multiple kickers remain eligible, and
  synthetic role fixtures prove mechanics only. A sole-listed assumption does
  not establish official activity or model readiness.
- S6A creates source-bound `PRIOR_ONLY` inputs but does not implement the full
  Section 4.4 historical ingestion, offline fitting, prospective validation, or
  live-source refresh architecture. A successful producer run therefore
  remains `DO_NOT_UPLOAD` until the separate evidence and model gates pass.
- nflverse, NWS, and Sleeper are policy-bound source adapters, but a live season
  backfill and license/schema audit have not been run from the supplied files.
- A synthetic full-width Classic benchmark built 20,000 candidates in 144
  seconds, covered every registered Classic construction family, retained a
  250-lineup economics shortlist, and respected the 4 GiB memory cap. It used
  only 50 scenarios in each DESIGN/SELECT/REFEREE bank. The complete registered
  10,000/20,000/20,000 refresh and real-data 10/5-minute gates therefore remain
  unclaimed until the operator supplies complete model inputs.
- Late swap can safely write an operator-proposed, evidence-cleared change to a
  current prefilled bulk-edit template. A calibrated joint conditional
  contest-state reoptimizer remains gated on live standings, ownership, scores,
  and validated remaining-game models; S2 does not implement or claim one.
- Runtime scenario defaults and certification deadlines come from
  `config/runtime.json`; hard-evidence requirements come from
  `config/evidence_policy.json`; `config/scoring.json` is validated against the
  executable salary-cap and Captain rules before a build or certification.
- Exposure envelopes, historical pair-dependence bands, and material
  ownership/market sensitivity thresholds are not yet registered inputs. The
  active QA pass leaves those triggers unasserted instead of inventing limits.
- The portfolio policy remains a user-control contract, not model evidence or a
  calibrated risk claim. Its SD4 solve is bounded to the actual reported bank
  and has not been benchmarked at 20 or 150 entries. Actual Cowork/Linux use,
  current live policies/evidence and prospective model quality remain unverified.
- Weekly rolling-origin fitting, promotion, influence caps, and rollback logic
  are implemented, but automatic deployment correctly has nothing eligible to
  promote before settled-slate history accumulates.

These are evidence gates, not silent fallbacks. Their operational result is
`SIMULATION_DIAGNOSTIC_ONLY` or `DO_NOT_UPLOAD`, never a misleading readiness claim.
