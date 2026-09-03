# NFL DFS Implementation Changelog

This file records completed implementation work and verification evidence for `backlog.md`. Keep entries factual and append new dated sections beneath `Unreleased`. Do not describe planned, diagnostic, synthetic, or structurally legal work as live-certified or upload-ready.

## Unreleased

### 2026-09-02 — S1: bounded safety and evidence foundation

Changed:

- `src/nfl_dfs/payouts.py` and both build/certification paths in
  `src/nfl_dfs/cli.py` now pass a validated ticket face value into payout CSV
  parsing; ticket rows still fail closed when no face value is supplied.
- `src/nfl_dfs/cli.py` now returns compact `DO_NOT_UPLOAD` JSON for unexpected
  CLI failures, writes a durable Cowork run result plus an internal traceback
  diagnostic after post-intake build/certification failures when storage is
  writable, preserves `KeyboardInterrupt`, and removes upload-shaped CSVs when
  certification fails.
- Added `src/nfl_dfs/byte_lines.py`; `src/nfl_dfs/lineups.py` and
  `src/nfl_dfs/referee.py` now split only on LF bytes and independently preserve
  untouched field bytes, encoding, physical line endings, quoted Unicode
  content, and final-newline state.
- Added strict `LedgerEntry` and `SourceLedger` contracts in
  `src/nfl_dfs/contracts.py` and deterministic validation in
  `src/nfl_dfs/evidence.py`. Certification now rejects arbitrary/unknown JSON,
  unapproved URIs, invalid timezone/license/parser metadata, missing or
  hash-mismatched artifacts, and partial or mismatched hashes for either model
  input.
- `src/nfl_dfs/cowork.py` and the Cowork CLI now confine request inputs to the
  explicitly supplied attachment/request directory, managed project data, the
  specific immutable run directory, or exact explicitly supplied files.
  Traversal, external paths, and symlink/junction escapes fail before hashing or
  copying.
- Updated `docs/COWORK_RUNBOOK.md` and `docs/DATA_CONTRACTS.md` to describe the
  enforced ledger, path, and byte-fidelity contracts.
- Added or expanded regressions in `tests/test_payouts.py`,
  `tests/test_build_pipeline.py`, `tests/test_cowork.py`,
  `tests/test_byte_line_fidelity.py`, and `tests/test_source_ledger.py`.

Verification:

- Pre-change Windows baseline: `65 passed in 13.17s`.
- Targeted S1 tests: pass, including parser and end-to-end ticket handling,
  actual certification-ledger binding, failure artifacts/cleanup, Unicode NEL
  and line/paragraph separators, external/traversal rejection, and a Windows
  junction escape.
- Full Windows suite: `87 passed, 1 skipped in 18.71s`. The one skip is the
  optional symbolic-link test because this Windows account lacks symlink
  privilege; the Windows junction/reparse escape test passed.
- `.\nfl.ps1 doctor`: pass on Python 3.13.7; SQLite integrity `ok`, WAL mode,
  Excel lock `CLOSED_OR_ABSENT`, and no synchronized/reparse workspace detected.
- `git diff --check`: pass.

Remaining blockers:

- None for S1.

Tracker updates:

- S1: `READY` -> `IN_PROGRESS` -> `DONE`.
- S2: `BLOCKED` -> `READY`.

Claims explicitly not made:

- No live-slate readiness, calibrated EV, ROI, win probability, calibrated
  ownership, profitability, or DraftKings upload-readiness claim.

### 2026-09-01 — Multi-session implementation tracking

Added:

- Created `backlog.md` with session-sized work items S0 through S10, dependencies, non-goals, and acceptance criteria.
- Established four separate release truths: `FILE_VALID`, `EVIDENCE_STATE`, `MODEL_STATUS`, and `RELEASE_DECISION`.
- Set S1 as the first implementation tranche: D-04, D-13, D-14, D-24, and D-25.
- Preserved the manual DraftKings boundary and the fail-closed `DO_NOT_UPLOAD` policy.

Verified baseline:

- Branch: `main`.
- HEAD: `e042c7bfc546`.
- Windows test suite: 65 passed on 2026-09-01 using the project virtual environment with pytest cache disabled.
- The working tree remained intentionally dirty; no existing remediation, fixture, review, or user-owned file was reset, cleaned, staged, committed, or overwritten.

Not verified:

- Linux/Cowork runtime.
- Real-slate performance or calibration.
- A model-assisted certified upload path.
- Live-slate or DraftKings upload readiness.

Files changed by this tracker-creation session:

- `backlog.md`
- `changelog.md`

Production code changes: none.

## Entry template for future sessions

Copy this structure under `Unreleased` and replace every placeholder:

```markdown
### YYYY-MM-DD — Sx: short outcome

Changed:

- Exact behavior changed and files involved.

Verification:

- Exact command or check: exact result.
- Full suite: exact pass/fail count.
- `git diff --check`: pass/fail.

Remaining blockers:

- Named blocker, or `None for this backlog item`.

Tracker updates:

- Sx: `OLD_STATUS` -> `NEW_STATUS`.
- Sy: `BLOCKED` -> `READY`, if dependencies and acceptance gates genuinely passed.

Claims explicitly not made:

- No live-slate, calibrated-EV, or upload-readiness claim unless independently proven by the work recorded here.
```
