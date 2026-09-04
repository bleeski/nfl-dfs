# Implementation Status

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
- Classic and Showdown salary contracts enforce exact IDs, geometry, salary
  cap, underlying-person identity, distinct CPT/FLEX IDs, and exact 1.5x Captain
  salary/scoring behavior.
- One build/certification package is deliberately limited to one Contest ID and
  one entry fee. Mixed-contest exports fail closed until per-contest economics
  and allocation are implemented.
- Payouts enforce contiguous paid ranks, monotonic tiers, advertised-value
  reconciliation, finite values, field-size bounds, cash/ticket distinction,
  and exact tied-rank division.
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
- The five-sheet workbook is a generated Cowork review artifact and remains a
  separate staged-input/timestamped-output design for the manual fallback; it
  detects Excel locks and renders cleanly.
- Parquet scenario storage, rolling-origin challenger fitting, model promotion
  tiers, multi-slate rollback rules, standings capture, and locked-cell late-swap
  audit are implemented. The SQLite registry and lifecycle transition guard are
  library components exercised by tests but are not yet wired into live runs.

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
- Weekly rolling-origin fitting, promotion, influence caps, and rollback logic
  are implemented, but automatic deployment correctly has nothing eligible to
  promote before settled-slate history accumulates.

These are evidence gates, not silent fallbacks. Their operational result is
`SIMULATION_DIAGNOSTIC_ONLY` or `DO_NOT_UPLOAD`, never a misleading readiness claim.
