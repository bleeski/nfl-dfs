# Code Review Remediation, 2026-09-01

## Outcome

The repository was reviewed across the executable NFL DFS pipeline, contracts,
configuration, launchers, source adapters, persistence boundaries, and tests.
The active correctness and fail-closed defects found in the reviewed paths were
repaired. The system still makes no claim that cold-start projections are EV,
ROI, calibrated ownership, win probability, or upload-ready without the
registered external evidence.

## Repaired defects

- Candidate and opponent scores now use the same float64 scoring path, so exact
  ties and field duplication divide payouts correctly.
- Multiple reserved entries now compete with one another during rank, tie, and
  payout settlement.
- Portfolio search is bounded and batch-evaluated instead of entering an
  effectively unbounded pair/triple dominance loop at default shortlist sizes.
- Quantitative QA and the independent REFEREE result are binding certification
  inputs. Incomplete candidate-family coverage and failed simulation accounting
  diagnostics are also hard blockers.
- Mixed-contest entry files, stale or post-lock status evidence, locked-player
  swap-ins, incomplete salary geometry, and invalid payout coverage fail closed.
- Build reports are bound to the exact assignment, salary, entry, payout, team,
  player, contest-size, and objective inputs used for certification.
- Salary, entry, assignment, payout, model, status, and source-ledger inputs are
  rehashed around parsing/certification to detect mid-run mutation.
- Run IDs are path-safe, build/scenario/certification artifacts are immutable,
  and same-ID reruns stop instead of overwriting prior evidence.
- CSV readers now reject duplicate required columns, short or over-wide rows,
  blank identity fields, non-finite values, negative economics, and conflicting
  game-lock metadata with explicit errors.
- Model, ownership, field, optimizer, settlement, and training numeric inputs now
  reject NaN, infinity, invalid bounds, and inconsistent dimensions.
- Official evidence carries its actual observation timestamp and expiry; market
  and weather inputs are enumerated, bounded, and freshness checked.
- Ticket payouts use ticket count times face value, while advertised prize and
  field-size reconciliation are enforced.
- The raw Sleeper response is the frozen source artifact; source suffixes are
  sanitized before use in local paths.
- Windows setup uses the locked Python 3.13.7 environment, doctor failures stop
  setup, and byte-sensitive supplied fixtures are protected by `.gitattributes`.
- The final manifest retains solver proof, portfolio metrics, distinct evidence
  hashes, and the assignment hash used to produce the upload candidate.
- Economics now rejects non-uniform scenario banks because the downstream
  portfolio estimators are deliberately unweighted.

## Verification

- `nfl.ps1 test`: 65 passed.
- Branch coverage run: 75% total over 4,075 statements and 1,362 branches.
- Python bytecode compilation: passed for `src` and `tests`.
- Git whitespace/error check: passed.
- `nfl.ps1 doctor`: passed on Python 3.13.7; SQLite integrity was `ok`, Excel was
  closed or absent, 8 processors and roughly 10.9 GB available memory were
  detected. Windows long-path support is disabled and remains a visible advisory.

## Remaining evidence and product gates

These are intentionally not papered over as bugs or readiness claims:

- Real contest payouts, field size, exact current activity evidence, and approved
  source-ledger inputs are still required before a real slate can certify.
- The cold-start opportunity, ownership, field, duplication, and payout models
  remain diagnostic until prospective validation and calibration gates pass.
- The complete registered scenario-count runtime benchmark has not been run on
  supplied real model inputs.
- Exposure envelopes, historical pair-dependence bands, and material sensitivity
  thresholds do not yet have approved inputs, so those QA dimensions remain
  explicitly unasserted.
- The SQLite lifecycle registry is tested as a library but is not yet wired into
  live runs; late swap remains a locked-cell reachability audit rather than a
  calibrated conditional contest reoptimizer.
- Live-season source backfill and source-license/schema review remain external
  evidence tasks.

No upload file was certified or produced by this review.
