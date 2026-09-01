# Implementation Status

## Working and locally verified

- The red-team revision has replaced the prior `plan.md`.
- All five supplied DraftKings/rules artifacts are preserved byte-for-byte with
  a checked SHA-256 manifest. Both critiques remain preserved.
- `nfl.ps1` provides setup, guided run, intake, validation, build,
  certification, audit, late-swap audit, settlement capture, learning gates,
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
- Payouts enforce contiguous paid ranks, monotonic tiers, advertised-value
  reconciliation, cash/ticket distinction, and exact tied-rank division.
- Manual assignments can be independently validated and exported into only the
  blank, authorized Entry-ID rows. Untouched lines preserve their exact bytes,
  including original BOM state. The final CSV is reparsed and SHA-256 bound.
- Hard evidence is typed and fail-closed. Current official status uses exact IDs
  and operator-controlled source evidence; fuzzy names cannot certify.
- The live model path uses explicit opportunity inputs, deterministic team-share
  conservation, a vectorized heavy-tailed simulator, separate DESIGN/SELECT/
  REFEREE banks, direct persistent HiGHS MILPs, candidate-family coverage,
  cold ownership stress states, complete legal opponent lineups with
  multiplicities, exact duplication/ties, and contest-aware portfolio metrics.
- The field evaluator retains no field-by-scenario matrix. Full candidate banks
  are reduced before scenario/economics arrays are retained.
- REFEREE is report-only and can block on a sign or safety disagreement; it does
  not tune or reselect.
- The five-sheet workbook is a generated Cowork review artifact and remains a
  separate staged-input/timestamped-output design for the manual fallback; it
  detects Excel locks and renders cleanly.
- SQLite registry, Parquet scenario storage, rolling-origin challenger fitting,
  model promotion tiers, multi-slate rollback rules, standings capture, and
  locked-cell late-swap audit are implemented.

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
- Late swap currently provides exact locked-cell reachability/audit. A calibrated
  joint conditional contest-state reoptimizer remains gated on live standings,
  ownership, scores, and validated remaining-game models.
- Weekly rolling-origin fitting, promotion, influence caps, and rollback logic
  are implemented, but automatic deployment correctly has nothing eligible to
  promote before settled-slate history accumulates.

These are evidence gates, not silent fallbacks. Their operational result is
`SIMULATION_DIAGNOSTIC_ONLY` or `DO_NOT_UPLOAD`, never a misleading readiness claim.
