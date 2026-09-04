# NFL DFS Implementation Changelog

This file records completed implementation work and verification evidence for `backlog.md`. Keep entries factual and append new dated sections beneath `Unreleased`. Do not describe planned, diagnostic, synthetic, or structurally legal work as live-certified or upload-ready.

## Unreleased

### 2026-09-04 — S3: certification truth states and QA policy

Changed:

- Added a centralized release policy for independent `FILE_VALID`,
  `EVIDENCE_STATE`, `MODEL_STATUS`, and `RELEASE_DECISION` reporting. Legacy
  `status` is derived from the release decision and validated for consistency.
- Certification now constructs, independently byte-audits, reparses, and
  hashes proposed output in memory before release. Evidence/model blockers can
  therefore coexist with `FILE_VALID=true`, while `DO_NOT_UPLOAD` persists no
  upload-shaped CSV. Proposed hashes and categorized file/evidence/model
  blockers remain available in manifests and review artifacts.
- Manual guardrail certification remains explicitly `MODEL_STATUS=UNVALIDATED`
  without becoming a model-performance claim. Model-assisted inputs are
  currently `PRIOR_ONLY`; both `UNVALIDATED` and `PRIOR_ONLY` are barred from
  `CERTIFIED_UPLOAD_PACKAGE`.
- Applied the truth model to certification and late-swap manifests, direct CLI
  results, status/audit output, Cowork reports and diagnostics, build reports,
  and the review workbook Upload sheet. Governed late swap inherits the prior
  certification basis/model status and preserves all S2 authority and byte
  guarantees.
- Limited hard opportunity evidence to selected players. Non-PASS unselected
  pool members are reported by count and exact underlying IDs as a prior-only
  model limitation.
- Downgraded `DST_OPPOSING_PASS_STACK` and incomplete candidate-family coverage
  to advisory findings. Genuine solver proof, simulation accounting, REFEREE,
  hard-evidence, authorization, legality, and final-byte failures remain
  blocking.
- Updated operator/runtime documentation to describe the four truths and the
  manual DraftKings boundary.

Verification:

- Focused certification, QA, Cowork, workbook, build-pipeline, truth-table, and
  governed-late-swap tests: pass.
- Complete Windows suite through `nfl.ps1 test` with a project-local pytest
  temp directory and cache disabled: 144 passed, 1 skipped in 31.93 seconds.
  The skip is the existing Windows symlink-privilege case.
- `nfl.ps1 doctor`: pass on Python 3.13.7; SQLite integrity `ok`, WAL mode,
  Excel lock `CLOSED_OR_ABSENT`, and no sync/reparse detection.
- Python `compileall` over `src` and `tests`: pass.
- `git diff --check`: pass.

Remaining blockers:

- Linux/Cowork runtime, real-slate timing, live calibration, and any
  prospectively validated model-assisted package remain unverified.
- No deterministic projection producer exists yet; DL2/S6A is the next item.
- Matching Showdown/Classic operator templates, contest facts, and current
  official evidence are still required on the delivery schedule.

Tracker updates:

- S3: `READY` -> `DONE`.
- DL1: `READY` -> `DONE`.
- DL2: `BLOCKED` -> `READY`; it is the only next deadline item.

Claims explicitly not made:

- No EV, ROI, win probability, calibrated ownership, profitability,
  live-slate, Linux/Cowork acceptance, or DraftKings upload-readiness claim.

### 2026-09-04 — Deadline delivery punch list and S3 handoff

Changed:

- Updated `backlog.md` to the verified post-merge baseline at `0339914` and the
  current `codex/s3-certification-truth-states` branch.
- Added the living DL1-DL8 punch list for a Showdown review lineup by
  2026-09-09 and Classic review lineups by 2026-09-13, including dependencies,
  operator-supplied inputs, deadline fallback, and explicit deferred work.
- Made S3 the single next implementation item. The minimum deterministic
  projection producer remains blocked until S3 stabilizes its contracts.

Verification:

- Documentation-only tracker update; no production code or numerical model
  behavior changed.
- Before the update, the branch was clean at merged baseline
  `033991452ce655923ff37f48b06c90746ab41ce3`.

Remaining blockers:

- S3 has not been implemented.
- No autonomous deterministic projection producer exists.
- No matching Showdown reserved-entry template or contest facts are stored in
  the repository.
- Linux/Cowork execution, real-slate timing, live calibration, and any
  model-assisted certified upload remain unverified.

Tracker updates:

- Added DL1-DL8; DL1 is the only `READY` deadline item.
- Corrected the stale next action from S2 to S3.

Claims explicitly not made:

- No live-slate, calibrated-EV, profitability, or upload-readiness claim.

### 2026-09-03 — S2: governed late-swap writer and lock evidence

Changed:

- `src/nfl_dfs/late_swap.py` now runs an immutable, fail-closed late-swap
  certification path. It validates a prior `CERTIFIED` manifest and referenced
  output, binds prior/current/proposed artifacts, requires exact Entry-ID
  coverage, derives every replaceable cell from the certified prior, exact
  current-slate IDs, game lock times, and timezone-aware `as_of`, and rejects
  locked-player removal, addition, or movement.
- `src/nfl_dfs/contracts.py` and `src/nfl_dfs/evidence.py` add strict versioned
  contest-eligibility, team inactive negative-list, and late-swap manifest
  contracts. Explicitly empty team reports are distinct from missing reports;
  unknown IDs, team/game conflicts, duplicates, invalid URLs, future/stale
  observations, selected inactives, and non-`PASS` evidence fail closed.
  `NOT_YET_DUE` remains nonblocking for provisional evaluation but explicitly
  blocks a final late-swap release.
- `src/nfl_dfs/lineups.py` adds a dedicated late-swap writer without weakening
  the existing pre-lock writer. Only the lock-derived changed cells may be
  rewritten; all metadata, locked cells, unauthorized rows/fields, BOM state,
  line endings, quoted content, Unicode separators, and final-newline state are
  preserved.
- `src/nfl_dfs/referee.py` independently verifies the late-swap allowlist and
  proves every unauthorized field's physical bytes are unchanged.
  `src/nfl_dfs/dk.py` can reparse candidate entry bytes before an upload-shaped
  file is written.
- `src/nfl_dfs/cli.py` upgrades the shared `late-swap` command used by
  `nfl.ps1` and `nfl.sh`. It requires a unique run ID and explicit salary,
  current prefilled template, prior manifest/assignment, proposed assignment,
  eligibility, inactive-report, output, and timezone-aware `as_of` inputs. It
  returns compact status, blockers, hashes, paths, and one next action.
- Ordinary blocked runs persist `nfl_late_swap_manifest_v1` when writable and
  leave no `DK_UPLOAD_*.csv`; successful runs atomically publish one hash-bound
  CSV only after writer, independent audit, reparse, input-recheck, and
  post-write hash gates pass.
- Added `tests/test_governed_late_swap.py`; updated `CLAUDE.md`, `docs/COWORK_RUNBOOK.md`,
  `docs/DATA_CONTRACTS.md`, `docs/OPERATOR_GUIDE.md`,
  `IMPLEMENTATION_STATUS.md`, and `backlog.md`.

Verification:

- Focused S2 suite: `36 passed in 14.81s`.
- Full Windows suite: `123 passed, 1 skipped in 26.81s`. The existing optional
  symbolic-link test remained skipped because this Windows account lacks
  symlink privilege; Windows junction/reparse coverage passed in the full suite.
- Clean temporary clone of pushed `main` at
  `1073d4345f0db79c2285fd24b0c61b3f3dcfe36d`: supplied fixture hashes passed;
  full checkpoint suite `87 passed, 1 skipped in 14.73s`.
- `.\nfl.ps1 doctor`: pass on Python 3.13.7; SQLite integrity `ok`, WAL mode,
  Excel lock `CLOSED_OR_ABSENT`, and no synchronized/reparse workspace.
- Python compilation and `git diff --check`: pass.

Remaining blockers:

- None for S0 or S2.
- Genuine Linux/Cowork execution is unverified. WSL 2 is present only through
  Docker Desktop's internal distribution, not a usable Cowork test runtime.

Tracker updates:

- S0: `BLOCKED` -> `DONE` after the pushed clean-checkpoint verification.
- S2: `READY` -> `IN_PROGRESS` -> `DONE`.
- S3: `BLOCKED` -> `READY`; no S3 implementation was started.

Claims explicitly not made:

- No live slate, calibrated EV, ROI, win probability, calibrated ownership,
  profitability, conditional contest-state reoptimization, or DraftKings
  upload-readiness claim.
- No DraftKings login, entry editing, upload, credential/cookie access, or
  money action occurred.

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
