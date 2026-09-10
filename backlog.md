# NFL DFS Implementation Backlog

This is the living implementation plan for the findings in `DFS_SYSTEM_GREENFIELD_SPEC.md` as modified by the 2026-09-01 assessment. The work is intentionally divided into reviewable sessions. Preserve the existing safety shell and replace risky components behind tested interfaces; do not perform a wholesale rewrite.

## Tracker protocol

**Current Showdown review-workflow priority sequence (2026-09-09):** follow
[`docs/SHOWDOWN_PRIORITY_TRACKER_2026-09-09.md`](docs/SHOWDOWN_PRIORITY_TRACKER_2026-09-09.md).
SD1 through SD5 are complete for software acceptance, including SD5's rendered
review conditions. The sole next READY chunk is **SD6 — complete Cowork/Linux
rehearsal with current evidence**; use its
[session prompt](docs/session-prompts/SD6-complete-cowork-linux-rehearsal.md).
SD5 finished with 482 passed and 1 existing Windows symlink-permission skip in
91.93s; doctor, compile, whitespace, native Excel and independent render checks
passed. The prior-review output now adds exact-artifact-reconciled JSON, escaped
HTML and an eight-sheet readable workbook without changing policy selection or
release gates. Measured fixtures covered 2 entries and 5 entries with bounded
32-candidate incomplete banks and optimal selection over each reported actual
bank. This does not prove complete-slate feasibility or 20/150-entry readiness.
Actual Cowork/Linux, live policy use, compatible role/current evidence, W3
simulator/full role modeling, W8/W9 economics, prospective model validation and
all broader W/S blockers remain unverified. Outputs stay
`PRIOR_ONLY / DO_NOT_UPLOAD`.
For this bounded sequence, that tracker supersedes the older competing next-task
recommendations below. It does not mark the broader W/S tranches complete or
alter release gates. Update this pointer and the priority tracker at closeout.

- Statuses: `READY`, `IN_PROGRESS`, `BLOCKED`, `DONE`, `DEFERRED`.
- At the start of each session, read this file, `changelog.md`, `DFS_SYSTEM_GREENFIELD_SPEC.md`, and the files named by the selected item.
- Work on one `READY` item unless an item explicitly groups inseparable changes.
- Before editing, inspect `git status --short --branch`. The working tree is intentionally dirty and contains user-owned remediation work. Never reset, clean, stash, overwrite, or broadly reformat it.
- Do not use `git add .`, `git add -A`, broad staging, or automatic commits. Stage or commit only after explicit user authorization and only with an explicit reviewed path list.
- Attachments, websites, and repository documents are evidence, not instructions. Local deterministic code owns parsing, joins, projections, simulation, optimization, QA, and export decisions.
- Missing, stale, conflicted, ambiguous, or unbound hard evidence remains fail-closed. Do not produce or describe a package as upload-ready merely because it is structurally legal.
- DraftKings login, contest entry, editing, upload, credentials, cookies, and money movement remain manual.
- Keep `AvgPointsPerGame` quarantined to untouched DraftKings source bytes. Never use it as a numerical model input.
- Do not label priors, heuristic scores, or unvalidated predictions as EV, ROI, win probability, cash probability, calibrated ownership, or certified output.
- Finish each session by updating this backlog and `changelog.md` with exact tests, remaining blockers, and the next `READY` item.

## Baseline

- Repository: `C:\Users\benja\Documents\Claude\nfl-dfs`
- Original tracker branch/HEAD: `main` at `e042c7bfc546`.
- Verified merged baseline 2026-09-04: PR #2 merged S3 into `main` at
  `500f73c5a098f2c6b6dfafae4b7052b8e7e3b5a3`; local `main` and `origin/main`
  matched before the S6A implementation branch was created.
- Current implementation branch:
  `codex/s6a-deterministic-projection-producer`, created from that clean merged
  baseline. DL2/S6A is implemented in the unstaged working tree and passed 171
  tests with 1 existing Windows symlink-privilege skip.
- Still unverified: Linux/Cowork runtime, real-slate timing, live calibration, and any model-assisted certified upload.
- Current truthful capability: validated intake, legality, evidence gating, and byte-exact export infrastructure; not a validated EV engine.

## Release truth model

New work should converge on four explicit and independently reported truths:

1. `FILE_VALID`: current authorized template, legal exact-ID roster, byte-exact write, and independent byte audit.
2. `EVIDENCE_STATE`: `PASS`, `UNKNOWN`, `STALE`, or `CONFLICTED`, with named hard blockers.
3. `MODEL_STATUS`: `UNVALIDATED`, `PRIOR_ONLY`, or `PROSPECTIVELY_VALIDATED`.
4. `RELEASE_DECISION`: `CERTIFIED_UPLOAD_PACKAGE` or `DO_NOT_UPLOAD`.

`FILE_VALID` alone never implies `CERTIFIED_UPLOAD_PACKAGE`. No automatic grade-C or grade-D fallback is authorized. A future emergency fallback requires a separately approved, deterministic, tested policy and must never be presented as EV-certified.

## Deadline delivery punch list — September 2026

Operational targets:

- Generate a deterministic, structurally legal, source-bound Showdown lineup
  for human review by Wednesday, 2026-09-09.
- Generate deterministic, structurally legal, source-bound Classic lineups for
  human review by Sunday, 2026-09-13.
- `Generate` does not mean prospectively validated, profitable, EV-certified,
  or automatically uploadable. Until the evidence and model gates genuinely
  pass, the truthful release decision remains `DO_NOT_UPLOAD`; DraftKings
  review, entry, and upload remain manual.

This deadline sequence temporarily puts the minimum S6 projection slice ahead
of S4A through S5 after S3 is complete. It does not waive those quantitative
repairs or mark their economics as valid.

| ID | Target | Status | Required outcome |
|---|---|---|---|
| DL1 | S3 truth states, target 2026-09-05 | `DONE` | Report `FILE_VALID`, `EVIDENCE_STATE`, `MODEL_STATUS`, and `RELEASE_DECISION` independently; keep hard gates binding; make style and bank-coverage preferences advisory. |
| DL2 | Minimum S6A projection producer, target 2026-09-07 | `DONE` | Deterministically transform frozen approved source artifacts into both model-input CSVs and a validated source ledger with no freehand numerical inputs or APPG use. |
| DL3 | Prior-only review lineup profile, target 2026-09-07 | `DONE` (landed 2026-09-08 as `cowork-run --profile prior_review`) | Generate legal projection-led review assignments without using or relabeling the known-unvalidated field, duplication, or payout economics. It must remain `MODEL_STATUS=PRIOR_ONLY` and `DO_NOT_UPLOAD`; this does not complete S5. |
| DL4 | Showdown exact-template acceptance, target 2026-09-08 | `BLOCKED` on operator contest facts only; mechanics rehearsed 2026-09-08 | Rehearse with a matching Showdown salary CSV, reserved-entry CSV, contest/payout facts, and current evidence; verify exact CPT/FLEX IDs, one Captain multiplier, underlying-person uniqueness, assignments, workbook, blockers, and final bytes. |
| DL5 | Showdown operational run, target 2026-09-09 | `BLOCKED` on DL4. Retargeted: 2026-09-09 is the manual-guardrail rehearsal in `docs/OPENER_RUNBOOK_2026-09-09.md`, not a model-generated upload | Refresh approved inputs and evidence, generate the review lineup, and make no feature changes beyond demonstrated blocker repairs. |
| DL6 | Classic projection/selection extension, target 2026-09-11 | `BLOCKED` on DL2 and DL3 | Use the same source-bound projection contract across the multi-game Classic pool and produce exact-ID legal review assignments. |
| DL7 | Classic full rehearsal, target 2026-09-12 | `BLOCKED` on DL6 plus operator files | Execute the complete intended operator path, record wall time and blockers, and preserve every exact input/output hash. |
| DL8 | Classic operational run, target 2026-09-13 | `BLOCKED` on DL7 | Refresh current official evidence, generate and review the lineups, and retain manual DraftKings upload as the final boundary. |

Operator-supplied deadline prerequisites:

- Matching Showdown salary and reserved-entry CSVs no later than 2026-09-07.
- Showdown payout table, advertised value, field size, entry fee, and contest ID
  no later than 2026-09-08. Without the matching entry template, DL5 can
  produce only a review lineup for manual transcription, not an exact-template
  export.
- Matching Classic salary and reserved-entry CSVs no later than 2026-09-10,
  followed by its contest facts and current official activity evidence.
- An actual Cowork/Linux rehearsal before DL4, or an explicit decision to use
  the verified Windows launcher as the deadline fallback.

Work deliberately deferred until after the deadline slice: S4A/S4B field-tail
economics, full S5 candidate/portfolio repair, S7 calibration, the full S8/S9
redesign, and dependency-complete S10. Their known blockers must not be hidden
by the deadline profile.

## Session backlog

### S0 — Preserve and establish the implementation baseline

- Priority: P0
- Status: `DONE`
- Completion: the reviewed remediation/safety checkpoint is pushed on `main`;
  a clean temporary clone reproduced all supplied fixture hashes and the full
  87-passed, 1-skipped checkpoint suite without generated artifacts.
- Scope:
  - Preserve the current dirty working tree and byte-sensitive fixtures.
  - Review `.gitattributes` and the supplied-fixture manifest.
  - When authorized, stage only explicit paths and verify the exact staged set, fixture bytes, full tests, doctor, and staged whitespace.
  - Never use broad staging.
- Acceptance:
  - Fresh-clone or clean-worktree verification reproduces fixture hashes and the full test result.
  - No generated runs, workbooks, credentials, caches, or upload files are committed.

### S1 — Bounded safety and evidence foundation

- Priority: P0
- Status: `DONE`
- Findings: D-04, D-13, D-14, D-24, D-25.
- Goal: repair bounded correctness and security defects without changing lineup selection or quantitative behavior.
- Scope:
  - Make ticket/satellite payout parsing accept a validated ticket face value through every parser and CLI caller.
  - Guarantee a compact machine-readable failure result after intake, plus an internal diagnostic artifact when possible; do not swallow user interrupts.
  - Make the writer and independent referee operate on byte lines rather than `str.splitlines` semantics.
  - Replace hash-only source-ledger acceptance with a strict versioned schema that validates approved source URIs, timestamps, license decisions, artifact hashes, parser versions, and derived-output hashes.
  - Restrict request paths to explicitly supplied attachment, managed data, and per-run roots. Reject traversal, external absolute paths, and symlink/reparse escapes before snapshotting.
- Required tests:
  - Ticket CSV parses with a face value and fails without one.
  - Arbitrary JSON, unknown ledger fields, missing artifacts, mismatched hashes, and mismatched derived hashes fail closed.
  - Valid ledger evidence binds both model-input hashes.
  - External and escaping request paths are rejected before any copy; valid relative paths still work.
  - Unicode non-CSV line separators inside quoted content cannot change source row geometry.
  - Representative build/certification failures still write a truthful `DO_NOT_UPLOAD` result and no upload-shaped CSV.
  - Full Windows suite, doctor, and `git diff --check` pass.
- Non-goals:
  - No field-model, candidate, projection, portfolio-objective, late-swap, or release-label redesign.
  - No staging, commit, remote, or push.

### S2 — Governed late-swap writer and lock evidence

- Priority: P0
- Status: `DONE`
- Depends on: S1.
- Findings: D-05 and the hard-evidence portion of D-08.
- Scope:
  - Derive replaceable cells from exact player/game lock times, never caller assertion.
  - Bind the prior certified assignment and entry-template hashes.
  - Require locked cells to remain byte-identical and reject locked-player additions or removals.
  - Support DraftKings bulk-edit output only for contests verified as late-swap eligible.
  - Represent official team inactive reports as team-scoped negative lists with lock-relative freshness.
  - Keep `NOT_YET_DUE` provisional; it must not silently clear the final release gate.
- Acceptance:
  - End-to-end late-swap fixture writes a valid changed-entry CSV, preserves locked cells, and passes an independent byte audit.
  - Tampered prior assignments, stale templates, non-late-swap contests, and locked-player changes fail closed.
- Completion: the shared CLI now binds prior state, derives cell authority from
  exact lock times, requires contest eligibility and team negative-list
  evidence, preserves unauthorized bytes, and writes only after independent
  audit, reparse, hash, and final-release gates pass. Windows verification:
  123 passed, 1 skipped; Linux/Cowork execution remains unverified because only
  the Docker Desktop internal WSL distribution is installed.

### S3 — Certification truth states and QA policy

- Priority: P0
- Status: `DONE`
- Depends on: S1 and S2.
- Findings: D-06 and D-09; modifies the proposed `UPLOAD_SAFE / MODEL_GRADE` doctrine.
- Scope:
  - Introduce the four release truths defined above without weakening existing hard gates.
  - Move truly mandatory construction rules into solver constraints.
  - Make construction preferences and candidate-family coverage advisory.
  - Separate pool-wide model uncertainty from selected-player evidence while retaining named model-certification blockers.
  - Preserve `DO_NOT_UPLOAD` for incomplete hard evidence or an unvalidated model package.
- Acceptance:
  - Every output reports all four truths and named blockers.
  - Legal bytes with incomplete evidence report `FILE_VALID` but still end `DO_NOT_UPLOAD`.
  - QA style preferences cannot delete an otherwise valid diagnostic file or masquerade as safety failures.
- Completion: one centralized, truth-table-tested release policy now derives
  the compatibility status and release decision for certification and governed
  late swap. Decision JSON, manifests, Cowork reports, and review workbooks
  report all four truths. Proposed bytes are independently audited, reparsed,
  and hashed in memory before release; blocked packages persist no upload CSV.
  Selected-player opportunity evidence remains hard, unselected pool
  uncertainty is counted as a model limitation, and unvalidated/prior-only
  model-assisted packages cannot certify. Construction preferences and
  candidate-family coverage are advisory; solver, accounting, REFEREE,
  evidence, authorization, and byte failures remain blocking. Windows
  verification: 144 passed, 1 skipped; doctor, compileall, and diff check pass.

### S4A — Tail-economics reference model and truth tests

- Priority: P0
- Status: `BLOCKED`
- Depends on: S3.
- Findings: D-01 and D-17.
- Scope:
  - Build a slow, auditable reference settlement for small exact fields and controlled synthetic large fields.
  - Define joint probabilities/counts for opponents strictly above and tied, including payout chops.
  - Evaluate tail-stratified or importance-sampling estimators; do not assume a Gaussian extreme tail without empirical acceptance.
  - Do not replace production economics in this session.
- Acceptance:
  - Exchangeable-field, known-duplicate, exact-tie, flat-payout, top-heavy, satellite, and boundary-rank golden tests.
  - Written error analysis across field size and sample size with explicit promotion thresholds.

### S4B — Production field economics

- Priority: P0
- Status: `BLOCKED`
- Depends on: S4A acceptance.
- Findings: D-01, D-15, D-17, D-23.
- Scope:
  - Replace cloned multiplicities with the accepted tail estimator.
  - Price strict-above and tied outcomes jointly; do not divide by a standalone expected-duplicates scalar as a substitute for tie settlement.
  - Enforce process-RSS memory budgets before allocation and use an explicit degraded profile or fail closed.
  - Keep ownership and duplication coefficients as versioned, hash-bound priors until prospective validation promotes challengers.
- Acceptance:
  - Meets S4A accuracy thresholds on held-out truth cases.
  - Memory and runtime budgets are measured on target hardware and recorded, not inferred.
  - REFEREE independently recomputes the same registered objective on a disjoint bank.

### S5 — Candidate generation and portfolio selection

- Priority: P1
- Status: `BLOCKED`
- Depends on: S4B.
- Findings: D-02, D-03, and remaining D-06 work.
- Scope:
  - Add multiple independent candidate families, including scenario-optimal and ownership-tilted families.
  - Evaluate candidates only on disjoint SELECT scenarios.
  - Replace the scenario-count-dependent LCB objective.
  - Evaluate portfolio outcomes jointly on shared field/outcome scenarios; do not assume own-lineup elite events are independent.
  - Keep risk preferences explicit, scenario-count-independent, and contest-specific.
- Acceptance:
  - Selection is stable within registered Monte Carlo error when scenario counts change.
  - Synthetic contests with known optimal portfolios select the expected result.
  - Candidate-family reporting is informative but non-blocking unless a registered solver constraint is violated.

### S6 — Deterministic projection producer

- Priority: P1
- Status: `BLOCKED`
- Depends on: S1 and stable input contracts from S3.
- Findings: D-07 and remaining D-24 work.
- Scope:
  - Produce team and player-opportunity contracts from frozen, approved source artifacts using local deterministic code.
  - Keep external-source fetch, parsing, license decisions, transformations, and output hashes explicit in the ledger.
  - Use stable provider identities; normalized or fuzzy crosswalk matches are proposal-only until human-reviewed and frozen.
  - Runtime never fits coefficients and the LLM never supplies numeric values.
- Acceptance:
  - End-to-end fixture build creates both model inputs and a valid ledger with zero freehand numeric input.
  - Missing, ambiguous, stale, conflicted, or hash-mismatched identity/source evidence fails closed.
  - `AvgPointsPerGame` remains absent from all numerical transformations.
- Minimum S6A/DL2 completion: `nfl.ps1 project` and `nfl.sh project` now accept
  four explicit hash-pinned frozen artifacts; validate approved provenance,
  timestamps, coverage, bounds, and exact provider-to-current-DK identity;
  conserve documented position-eligible team weights; and atomically publish
  loader-valid team/player CSVs plus a reconciled `nfl_source_ledger_v1` file.
  Classic fixture coverage is 24 teams/719 people, Showdown uses 63 distinct
  FLEX IDs, repeat runs are byte-identical, APPG mutation leaves both derived
  CSVs unchanged, and failures publish no partial package. Verification: 39
  focused tests passed; 112 integration tests passed with 1 existing skip; full
  Windows suite 171 passed with 1 existing skip; doctor and compileall passed.
- Broader S6 remains `BLOCKED`: the full Section 4.4 historical ingestion,
  offline fitting/holdout reports, live-source refresh, and prospective model
  validation are not part of S6A and remain unimplemented/unverified.

### S7 — Simulator, ownership, duplication, and calibration

- Priority: P1
- Status: `BLOCKED`
- Depends on: S4B, S5, and S6.
- Findings: D-10, D-16, D-18, D-22, D-23.
- Scope:
  - Correct or remove DESIGN importance sampling.
  - Vectorize count allocation and points-allowed scoring with deterministic regression coverage.
  - Replace tautological accounting diagnostics with checks on simulated allocations.
  - Fit ownership, duplication, and correlation challengers offline with rolling-origin validation.
  - Do not promote after an arbitrary three-contest threshold; require documented sample size, calibration, stability, and holdout improvement.
- Acceptance:
  - Prospective acceptance report beats registered priors on predeclared metrics without degrading tail/dependency gates.
  - DESIGN, SELECT, and REFEREE remain disjoint and hash-bound.

### S8 — State, retention, brief, and workbook boundary

- Priority: P2
- Status: `BLOCKED`
- Depends on: S3.
- Findings: D-19 and D-20.
- Scope:
  - Add content-addressed stage caching and per-slate state without discarding immutable run evidence.
  - Persist scenario evidence for certified and settled runs; allow diagnostic retention to follow a declared policy.
  - Make `brief.json` the canonical agent contract.
  - Retain the review workbook and Windows fallback as secondary human surfaces; fix timezone round-tripping.
- Acceptance:
  - Identical inputs reuse unchanged stages.
  - Certified assignments, prior hashes, branches, briefs, and retained evidence are reproducible and independently auditable.
  - JSON and workbook agree on status, blockers, paths, and hashes.

### S9 — Runtime compatibility and code reduction

- Priority: P2
- Status: `BLOCKED`
- Depends on: S1 and S8.
- Findings: D-12 and D-21.
- Scope:
  - Define a tested Python compatibility policy, record the exact interpreter in manifests, and separate diagnostic compatibility from certification requirements.
  - Remove only proven dead code after migration review; move fitting and validation harnesses under `research/` where appropriate.
  - Declare direct dependencies explicitly and remove unused declarations only after full verification.
- Acceptance:
  - Windows and Linux/Cowork acceptance matrix passes on every supported interpreter.
  - Fresh-environment setup is locked, reproducible, and does not weaken evidence gates.

### S10 — Simulated game-week acceptance and operations

- Priority: P2
- Status: `BLOCKED`
- Depends on: S2 through S9.
- Scope:
  - Execute a complete synthetic or historical game week: intake, projection, early build, final evidence, certification decision, scratch drill, late swap, settlement, and calibration intake.
  - Add scheduled automation only after the dry run passes and only for local computation and approved public-source collection.
  - Keep DraftKings account actions manual.
- Acceptance:
  - Exact artifacts, wall-clock timings, process RSS, blockers, hashes, and operator touches are recorded.
  - No live-slate or upload-readiness claim is made from synthetic evidence.

## Post-review work tranches — 2026-09-08

Source: `docs/PRODUCTION_READINESS_REVIEW_2026-09-08.md` (findings R01-R15) and
`docs/SHOWDOWN_FIRST_PRODUCTION_PLAN.md` (sequencing). The R-* list supersedes the
D-* list in `DFS_SYSTEM_GREENFIELD_SPEC.md` as the current defect inventory. These
`W*` tranches are Cowork-session-sized chunks; each names its own findings, and
each has a paste-ready prompt under `docs/session-prompts/`.

### Completed and not to be re-litigated

`S0`, `S1`, `S2`, `S3`/`DL1`, `S6A`/`DL2`, `W1`/`R01`, and core Classic/Showdown
legality are `DONE` with passing regression coverage (203 passed, 1 Windows
junction skip, 204 collected, run by a Cowork session on the pinned 3.13.7
runtime). Repaired findings from the 2026-08-31 and 2026-09-01 documents are not
carried forward. What remains open is exactly R02-R15.

### Verified runtime constraints for every session below

Measured 2026-09-08 from a Cowork session with the repo folder mounted, and
revised during `W1` where the earlier measurement was wrong:

- **A session can now execute the test suite.** `sh ./nfl.sh test -q
  -p no:cacheprovider --ignore=.pytest_cache tests` runs on the pinned Python
  3.13.7 runtime once `NFL_DFS_VENV_DIR`, `NFL_DFS_UV_CACHE_DIR` and
  `NFL_DFS_UV_PYTHON_DIR` point off the mounted folder. Ben no longer has to run
  `.\nfl.ps1 test` and paste results. The `--ignore` is required because
  `.pytest_cache` in the mounted repository is unreadable.
- **The Cowork device bridge refuses file deletion inside a mounted folder**
  (`unlink` and `rmdir` return `EPERM`). This one fact caused every runtime
  failure previously attributed to disk space: `uv` cannot extract an
  interpreter, SQLite cannot open a database in `WAL` or `DELETE` mode
  (`journal_mode=MEMORY` is the only mode that works), and
  `tempfile.TemporaryDirectory` recurses to `RecursionError` on cleanup.
- **The engine therefore cannot run in place in a mounted folder.** `nfl.sh
  doctor` correctly reports `pass_status: false` with `sqlite_probe_error`;
  `cowork-run` gates on `pass_status` and `registry.py:30` opens a real database
  under `data/registry/`. Either grant the session delete permission on the
  folder, or execute from a local-disk working copy of `src`, `tests`,
  `templates`, `config`, `pyproject.toml` and `uv.lock`, keeping the mounted
  repository as the source of truth for edits. Running the suite in place leaves
  undeletable temporary directories behind.
- **GitHub release assets are reachable.** The earlier claim that only
  `raw.githubusercontent.com` and `github.com` work understated it: a
  `releases/download/...` URL 302s to `release-assets.githubusercontent.com`,
  which serves the bytes from both the device VM and the cloud container.
  `api.github.com` also resolves. The former block was policy, not network:
  that host was not in `ALLOWED_HOSTS` and `fetch_public_artifact` set
  `follow_redirects=False`. `W1` added a single permitted hop confined to
  GitHub's own release-asset hosts. Every nflverse dataset is published this way,
  so this is what makes the adapter self-sufficient.
- `api.sleeper.app`, `api.weather.gov` and `api.the-odds-api.com` still fail to
  connect from both the device VM and the cloud container, so activity, weather
  and sportsbook market captures remain operator-supplied. `api.weather.gov` is
  allowlisted and reachable from a browser, which is a usable route not yet
  wired up.
- `actionnetwork.com` and other commercial odds sites cannot be artifact sources
  at all: not in `ALLOWED_HOSTS`, and the `OPERATOR_SUPPLIED` escape in
  `sources.py` is hardcoded to DraftKings, so even a hand-supplied number fails
  `_validate_metadata`. `nfldata/games.csv` is the market artifact of record
  until that policy changes.
- A session cannot invoke PowerShell or the Windows `.venv`. The device shell is
  Linux with the repo mounted, not a Windows shell.
- **The device VM's own `$HOME` filled up on 2026-09-08.** `/sessions` was 100%
  used with 794MB free on `/`, so the local-disk working copy went to `/tmp/w4`
  instead of `$HOME`. A `/tmp/nfl-cowork-venv` left by an earlier session is
  owned by a different uid and is not writable, so `sh ./nfl.sh setup` fails with
  `Permission denied` and building a second 603MB venv would not have fit. That
  venv's installed versions match `pyproject.toml` exactly (numpy 2.3.2, polars
  1.32.3, pyarrow 21.0.0, pydantic 2.11.7, highspy 1.11.0, scikit-learn 1.7.1,
  statsmodels 0.14.5, openpyxl 3.1.5, hypothesis 6.138.2, pytest 8.4.1), and its
  editable `.pth` points at a dead prior-session path, so the suite runs against
  it with `PYTHONPATH` set to the working copy's `src`. If a session needs a
  clean environment, free `/` first or work in the cloud container.
- **`git status` inside the mounted repository leaves `.git/index.lock` behind.**
  Git writes the lock, refreshes the index, then cannot unlink it, so the next
  git command reports a stale lock. On 2026-09-08 the leftover was renamed to
  `.git/index.lock.stale-from-cowork`, which git ignores; delete it from Windows.
  Prefer reading the working-tree state some other way, and if a session does run
  `git status`, move the lock aside before finishing.
- **nflverse retrieval works from the device shell.** Confirmed again on
  2026-09-08: a full `priors-propose` fetched and froze all seven artifacts in
  under a minute from `/tmp`, including the GitHub release-asset redirect.
- **`_ROOF_WEATHER` in `priors.py` treats nflverse `roof=open` as the
  schedule-derivable state `ROOF_OPEN`.** `prior_review` still asks for the
  `api.weather.gov` capture for that roof, because a retractable roof left open
  is played in the weather, but it cannot pass the operator's state to
  `priors-freeze` without tripping `WEATHER_STATE_CONFLICT`, so the capture is
  recorded in the run report and the artifact metadata still says
  `DERIVED_FROM_SCHEDULE_ROOF:open`. Closing that gap means editing
  `_ROOF_WEATHER`, which is `W1` territory and was left alone.
- **The delete-permission constraint also leaves Windows-side residue.** Bridge
  writes can leave directories the operator's own Windows account cannot
  enumerate. On 2026-09-08 that was `%LOCALAPPDATA%\Temp\pytest-of-benja` and
  the repository's `.pytest_cache`, which errored every test at setup with
  `WinError 5` from `os.scandir` inside `_pytest/pathlib.py`, in code that never
  reaches `nfl_dfs`. The `test` branch of `nfl.ps1` now pins both writable roots
  under `%TEMP%` so a session cannot poison them again, and the equivalent flags
  cannot be passed by hand anyway: `[CmdletBinding()]` makes PowerShell bind
  `-p` to `-PipelineVariable` before the script sees it. If a repository path is
  left unreadable, `takeown /F <path> /R /D Y` then `icacls <path> /grant
  "$env:USERNAME:(OI)(CI)F" /T` from an elevated prompt is the repair.

### Tranche table

| ID | Findings | Status | Depends on | Chunk |
|---|---|---|---|---|
| W1 | R01 | `DONE` (5 operator flags open) | operator DK Showdown salary CSV for the identity map | Linux runtime bootstrap check, then the nflverse-only deterministic prior adapter for one game |
| W2 | R07, R08 | `DONE` | none | Selection objective independent of scenario count; source expiry and evidence scope preserved and re-evaluated |
| W3 | R03 | `PARTIAL` (selection side `DONE`, simulator mask open) | none | One participation/exclusion contract with a simulator availability mask |
| W4 | R02 | `DONE` | none | DL3 prior-only review profile that never calls field, payout, or duplication economics |
| W5 | R04 | `READY` once the operator files land | contest facts | Showdown exact-template rehearsal on real downloads, byte audit, repeated run, stale-source and inactive-refresh cases |
| W6 | R09 | `DONE` | none | Split historical artifact integrity from a live pre-upload check that recomputes at the current clock. Owns `src/nfl_dfs/preflight.py` (new), the `command_audit`/`command_preflight` block and the `preflight` subparser in `src/nfl_dfs/cli.py`, and `tests/test_w6_live_preflight.py` (new) |
| W7 | R15 | `READY` | none | Version-bound settlement capture and the canonical operator run brief. Start before the first settled slate; the validation clock starts here |
| W8 | R05 | `READY` (W2 landed) | none | Measure the existing evaluator at true field size with cloning off, then S4A reference settlement and thresholds |
| W9 | R06 | `BLOCKED` on W8 | none | Canonical uniqueness at every bank boundary, objective-appropriate diversity, enforced exposure and Captain-per-person caps |
| W10 | R13 | `BLOCKED` on W8, W9 | none | Stage budgets, cancellation, measured peak memory, per-entry-count benchmarks |
| W11 | R10 | `BLOCKED` on W3 | none | Event and scoring reconciliation, participation modeling, measured dependence, DESIGN oversampling treatment |
| W12 | R11, R12 | `BLOCKED` on W7 data accrual | settled slates | Binding evidence minimums, slate-grouped splits, untouched temporal holdout, then the model artifact registry and derived promotion status |
| W13 | R14 | `BLOCKED` on W5 | none | Conditional late-swap portfolio generation and Classic lock-aware slot ordering |

### Deadline reality check

The 2026-09-07 and 2026-09-08 operator prerequisites in the punch list above were
not met: no matching Showdown reserved-entry template, contest facts, or approved
prior artifacts exist in the repository. R01 through R04 and R08 cannot all land
and be rehearsed before the 2026-09-09 opener at 19:20 CT.

Retarget: the Wednesday opener is a manual-guardrail rehearsal only. Ben selects
the lineup; the engine certifies legality, evidence, and exact bytes, with a fresh
certification run immediately before upload because R09 makes `audit` untrustworthy.
The first prior-only model-generated Showdown review run targets a Sunday
2026-09-13 single-game contest. DL4 and DL5 keep their scope and move to that date.
Classic (DL6 through DL8) stays behind Showdown; the 719-row, 24-team identity map
is the reason.

## Next action

### 2026-09-09 SD5 readable-review closeout

The bounded Showdown priority sequence in
`docs/SHOWDOWN_PRIORITY_TRACKER_2026-09-09.md` has completed SD5 software and
rendered-review acceptance. A valid `prior_review` export now produces
canonical readable JSON, escaped self-contained HTML and an eight-sheet workbook
only after independent exact-byte display reconciliation. The review exposes
exact entry/roster/person identity, salary, prior-only points, combined and
Captain exposure, policy maxima, overlap, evidence/role limitations, provenance,
all four release truths and one next action. Any mismatch stops at
`READABLE_REVIEW`, preserves earlier artifacts and remains `DO_NOT_UPLOAD`.

**Sole next READY item in that sequence: SD6**, the actual Cowork/Linux complete
workflow rehearsal using matching files and current game-specific evidence.
Windows acceptance cannot satisfy it. The self-contained prompt is
`docs/session-prompts/SD6-complete-cowork-linux-rehearsal.md`. W3, W7, W8, W9
and the larger S-tranche dependencies below remain separate and are not marked
complete by SD5.

### 2026-09-09 readiness review update

The user authorized a full workflow review and verified repairs across tranches
for today's Showdown run. Preserve the pre-existing uncommitted W6 and runbook
work. Current results and acceptance are in
`docs/READINESS_REVIEW_2026-09-09.md`.

- W4 now passes supplied current official inactive rows into prior selection;
  both roles are excluded. Live acquisition advances its clock before projection
  and checks source expiry again before export. The actual 136-row NE–SEA pool
  and two-entry template produced two legal, unique review lineups repeatedly.
- W6 now rejects malformed truth fields/manifests, unavailable policy files,
  missing model-specific evidence and activity/output-roster mismatches. The
  Windows launcher exposes preflight.
- Priors archive their raw inputs inside the frozen package; six-hour weather
  expiry is retained downstream. New NWS captures worked from Windows.
- R11's minimum-sample, cold-promotion, same-timestamp-fold and prediction-cutoff
  defects are repaired. W12 remains BLOCKED on real settled-slate evidence and
  an independently validated model registry; these repairs do not promote it.
- W3's simulator mask, W8/W9 economics/exposure redesign, calibrated ceiling and
  ownership, and actual Cowork/Linux live acceptance remain incomplete. No
  generated lineup has been certified for upload. W5 has real-file Windows
  review acceptance; complete live official-evidence acceptance remains open.

Next implementation: finish W3's simulator/build participation contract, then
W8/W9 economics and portfolio controls. Today's practical next operator step is
a fresh official-evidence review near kickoff. The current automatic profile
continues to report `PRIOR_ONLY / DO_NOT_UPLOAD`.

`W2` is `DONE` as of 2026-09-09, which unblocks `W8`. A frozen projection
package now carries its own per-source expiry, evidence scope and state,
transformation version and input dependency bindings on
`nfl_source_ledger_v2`; it archives its consumed sources content-addressed
inside itself, so a copied package validates with the originals deleted and
needs no Windows-to-Linux path rewrite; freshness is re-evaluated at whichever
clock the caller supplies, with the run's `as_of` as the replay clock and
`evidence.release_clock()` as the live one; and a legacy `nfl_source_ledger_v1`
package can no longer clear certification, because a shape that cannot express
an expiry cannot be called fresh. Portfolio selection ranks on a declared,
scenario-count-independent risk measure with Monte Carlo uncertainty reported
separately against a declared effective sample size. `MODEL_STATUS` stays
`PRIOR_ONLY` and `RELEASE_DECISION` stays `DO_NOT_UPLOAD` everywhere they were,
and the NE@SEA review export is byte-identical to the pre-W2 run. See
`changelog.md` for commands, counts and hashes.

`W6` (R09) is `DONE` as of 2026-09-08. `audit` is now historical artifact
integrity only: it reports the manifest's stored decision labelled as stored and
pins its own `RELEASE_DECISION` to `DO_NOT_UPLOAD`, so it can never be read as
renewed certification. The new `preflight` command is the live pre-upload check.
It validates the manifest schema, rebuilds every `EvidenceRecord` and re-derives
its state at `evidence.release_clock()`, requires the manifest to still cover
every hard field in `config/evidence_policy.json`, rebinds the salary, entry,
assignment and output files by hash, re-derives selected-player locks from the
current salary pool, reports the clock and scope of every check, and exits 0
only on `CERTIFIED_UPLOAD_PACKAGE`. The standing instruction is now: **run
`preflight` immediately before upload**, not `audit`.

**Recommended next: `W7` (R15) or `W8` (R05).** `W7` starts the validation
clock, so the sooner the better. `W8` begins the field-economics rebuild and
unblocks `W9` and `W10`. Neither is a same-day change.

`W1` and `W4` are `DONE`. `cowork-run --profile prior_review` now takes a
DraftKings Showdown salary CSV and a DKEntries CSV and returns the byte-audited
bulk-entry CSV in one command, driving `priors-propose`, the identity gate,
`priors-freeze`, `project`, `select` and `review-export` itself and stopping only
at the three gates that are genuinely human: an identity that is unresolved and
still selectable, a weather capture the schedule artifact cannot supply, and an
expired prior package with no permission to rebuild. `MODEL_STATUS` stays
`PRIOR_ONLY` and `RELEASE_DECISION` stays `DO_NOT_UPLOAD` on every path,
including the success path, and the release policy makes any other decision
unreachable for a `MODEL_ASSISTED` `PRIOR_ONLY` package. Verified end to end on
the real NE@SEA opener twice, once reusing the frozen package and once rebuilding
it from a fresh nflverse fetch; both produced the same export bytes. See
`changelog.md` for commands, counts and hashes.

**Next `READY` tranches, all touching disjoint files, in any order:**

- `W7` (R15): version-bound settlement capture and the canonical operator run
  brief. The validation clock starts here, so the sooner the better.
- `W8` (R05): measure the existing evaluator at true field size with cloning
  off, then the S4A reference settlement and its promotion thresholds. Newly
  `READY`; it unblocks `W9` and `W10`. Start from
  `portfolio.RISK_MEASURE`/`RISK_AVERSION`, which are now a declared preference
  rather than an artifact of the scenario count, and from
  `portfolio.resolve_effective_sample_size`, which is where a bank declares
  repeated or dependent draws.
- `W5` (R04) is unblocked by code and now waits only on operator contest facts:
  a matching reserved-entry template for the contest actually entered, the payout
  table, advertised prize value, field size, entry fee and contest ID.

What is still open and must not be papered over:

- **R03 simulator mask.** `simulation.py` still has no availability mask, so the
  zero-capacity scoring defect is untouched. Never route a pool through `build`
  expecting exclusions to hold. The selection path avoids it by never simulating,
  and `prior_review` never calls `build`.
- **No ownership, leverage, correlation or duplication model anywhere.** The
  objective maximizes a central estimate, which in a large-field GPP is chalk.
  This is the largest gap against the stated product objective and it is R05,
  R06 and S7 work, not a selection problem. `prior_review` does not narrow it
  and does not pretend to. `W2` removed the scenario-count dependence from the
  objective and nothing else: the field, payout and duplication economics under
  it are still the known-defective ones, and `RISK_AVERSION` is deliberately
  zero because weighting a tail the current field model computes would be
  weighting a tail R05 has not validated.
- **`projection.py` still requires a prior record for every person in the salary
  pool** (`SALARY_PERSON_IDENTITY_COVERAGE_MISMATCH`). A practice-squad elevation
  with no honest prior fails the whole package. Unchanged by `W4`.

Do not begin `W8`, `W9`, `W10`, `W11`, `W12`, or `W13`; do not relabel prior-only
output as EV, ROI, or edge; and do not move a generated assignment into the
manual-guardrail path to bypass the model gate. `prior_review` refuses an
`assignment_csv` outright for that reason.

### Operator decisions W1 left open, all now settled

All five were delegated to the implementer on 2026-09-08 and resolved:

1. **`weather_state`**: `CLEAR`, captured from `api.weather.gov` gridpoint
   `SEW/125,67` through the operator browser and attributed in coverage via the
   new `--weather-source-uri` / `--weather-observed-at` arguments.
2. **Salary CSV**: supplied and committed byte-exact under
   `data/runs/20260909-showdown-ne-sea/inputs/`, with the entry template.
3. **Eight identity decisions**: all accepted. Each was a unique league-wide
   match whose nflverse roster team disagreed with DraftKings, and all eight are
   DraftKings-flagged `OUT`. `W4` turned exactly that rule into the automatic
   acceptance in `prior_review.apply_identity_gate` and reproduced all eight.
4. **`sources.py` release-asset redirect**: retained. It is the only route to
   nflverse data, it is confined to one hop onto GitHub's own asset hosts, and
   the recorded provenance stays the canonical `github.com` URL.
5. **Runtime**: the local-disk working-copy pattern is the standing answer. It
   needs no permission prompt, keeps the mounted repository as the single source
   of truth for edits, and produced every green suite run. Delete permission on
   the folder remains a nice-to-have, not a blocker.

### New constraints for later tranches

`projection.py` requires a prior record for every person in the salary pool
(`SALARY_PERSON_IDENTITY_COVERAGE_MISMATCH`). A DraftKings pool routinely
contains a practice-squad elevation or a just-signed person with no honest prior,
and today the entire package fails rather than publishing without them. This
tension between fail-closed and pool reality needs a decision before the Sunday
run; it is adjacent to `W3`'s participation contract but not the same thing.

`role_capacity` cannot be used as a forward ceiling anywhere. It is a mean
prior-season offensive snap share, so it describes the role a person held while
someone was ahead of him, which is invalid in exactly the situation
redistribution addresses. `opportunity.remove_inactive_and_redistribute` enforces
it and therefore refuses a real pool outright. It is now treated as a diagnostic
in `participation.py`; the enforcement in `opportunity.py` remains and should be
revisited when `W3` completes.

The frozen team prior inherits `MARKET_LINE_MOVES_INTRADAY` from `games.csv` and
expires twelve hours after capture, so a prior package built the day before a
slate is stale by kickoff. `prior_review` detects that against `as_of` and
rebuilds; no tranche may widen an expiry to make a run succeed.

`uv` is unusable inside the cloud container: 268KB of cache in ten minutes
before timing out, while `pip` installed the whole pinned dependency set in 39
seconds. Use `uv` only to fetch the interpreter. The device shell
(`device_bash`) can also fail with "Failed to create bridge sockets" while the
other device tools keep working; the container fallback plus
`device_commit_files` is the way through.

### Constraints measured during `W2`, 2026-09-09

- **The local-disk working copy needs `README.md` and `LICENSE`.** The earlier
  list of what to copy omitted them, and `uv sync` fails on the missing readme
  with `OSError: Readme file does not exist: README.md` from hatchling's
  metadata validation, not with anything that names the real cause.
- **`/tmp` had room this session.** `/` reported 3.3GB free rather than the
  794MB measured on 2026-09-08, no `/tmp/nfl-cowork-venv` was left by another
  uid, and `sh ./nfl.sh setup` built the pinned environment cleanly. Check
  `df -h /` rather than assuming either measurement still holds.
- **The device shell died mid-session** with "Failed to create bridge sockets"
  and never recovered, while `device_list_dir`, `device_stage_files` and
  `device_commit_files` kept working. The container fallback is viable but has
  one trap: **the container's default interpreter is 3.11.15, not the pinned
  3.13.7**, and on 3.11 three tests fail for environment reasons alone
  (`ENVIRONMENT_DOCTOR_FAILED` in two `test_prior_review_profile` cases because
  `doctor` pins the runtime, and a float32 `share_conservation_max_abs_error`
  assertion in `test_simulation`). `uv python install 3.13.7` took 1.42 seconds
  and `pip` installed the pinned set into that interpreter in about 40; build
  that venv before trusting any container run.
- **The 2026-09-08 baseline was 277 passed, not 278.**
  `test_prior_review_profile.py::test_one_command_exports_and_reports_all_four_truths`
  was a clock bomb: it pinned a fixed `AS_OF` while `command_cowork_run` stamps
  `as_of` from the live clock, so six hours after `AS_OF` the fixture package
  expired and the run correctly blocked `PRIOR_PACKAGE_EXPIRED`. `W2` made that
  fixture's expiry follow the clock the code under test actually reads. Any
  fixture whose freshness matters must derive from the same clock as its caller.
- **The repository's frozen NE@SEA prior package is not self-contained.** Its
  raw sources live at the run root, `data/runs/<id>/raw/`, not inside
  `data/runs/<id>/priors/`, so `resolve_frozen_artifact` answers
  `FALLBACK_SEARCH` rather than `IN_PACKAGE`. Every run report now records
  which one answered. Making `priors.freeze_prior_package` archive raw inside
  the frozen package would close it; that is a priors-owning tranche, not `W2`.
- **Effective sample size must be declared, never inferred from outcomes.** An
  earlier `W2` draft derived scenario multiplicity by collapsing identical
  per-candidate outcome rows. Independent scenarios routinely settle a
  portfolio at the same value, so that understates precision, and an
  overstated standard error *widens* the REFEREE tolerance, because
  `qa.referee_blocks` blocks only when `abs(delta) > uncertainty`. On the
  W2 fixture bank it reported an effective size of 1.47 for 100 independent
  draws and let a sign disagreement of 10.0 through that the old formula
  blocked. Silence now means independent draws, which is what
  `economics.evaluate_candidates_against_field` guarantees by refusing a
  non-uniform bank.
- **A ledger is a plain JSON file, so preserving an expiry inside it is half a
  gate.** `projection.verify_projection_package` checks every declared expiry,
  state, observation time and source URI back against the archived source's own
  hash-bound metadata, and requires the entry set to cover all four scopes,
  because deleting an expired entry is otherwise as effective as forging its
  expiry.

### Constraints measured during `W6` and the opener rehearsal, 2026-09-08

Runtime, all newly measured and all cheap to trip over again:

- **The `/tmp` paths a session prompt names may be owned by a previous
  session's uid.** `/tmp/nfl-cowork-venv`, `/tmp/nfl-uv-cache` and
  `/tmp/nfl-uv-python` were all `nobody:nogroup` and mode `755`, so the
  prescribed `sh ./nfl.sh setup` died with `Failed to initialize cache at
  /tmp/nfl-uv-cache ... Permission denied (os error 13)` and exit 0, which is
  easy to miss. Point `NFL_DFS_VENV_DIR`, `NFL_DFS_UV_CACHE_DIR` and
  `NFL_DFS_UV_PYTHON_DIR` at fresh per-session directories. A full `uv sync`
  into new directories, interpreter download included, took under 30 seconds on
  3.2GB free.
- **The device VM can restart mid-session and wipe all of `/tmp`.** It happened
  once here, between two tool calls, with no warning beyond a "Workspace still
  starting" error on the next command. It took the working copy, the venv and
  every rehearsal artifact with it. The mounted repository survived untouched.
  **Write source changes into the mounted repository as they are produced and
  build the throwaway working copy from it**, rather than editing in `/tmp` and
  copying back at the end.
- **`pytest` background jobs must be detached.** A plain `nohup ... &` inside a
  `device_bash` call is killed when the call returns, leaving a zero-byte log
  and no process. `setsid nohup sh -c '...' >log 2>&1 </dev/null &` survives.
- **The prescribed `-q` makes the test summary disappear.**
  `pyproject.toml` already sets `addopts = "-q --strict-markers"`, so
  `sh ./nfl.sh test -q ...` is `-qq` and pytest suppresses the
  `N passed, M skipped` line entirely. Drop the extra `-q` when the counts
  matter.

Certification behavior, measured against the real NE@SEA files:

- **Two reserved entries carrying identical rosters block certification.**
  `DUPLICATE_SELECTED_LINEUPS` is a CRITICAL blocking QA finding and the run
  ends `DO_NOT_UPLOAD` with `FILE_VALID` false. Filling every reservation with
  one lineup is not a supported shortcut.
- **The pre-lock official-status window is three hours, not ninety minutes.**
  `cli._official_status_evidence` uses `freshness_window=timedelta(hours=3)`:
  the oldest selected-player observation must be no earlier than kickoff minus
  three hours *and* the certify run must fall within three hours of it. The
  ninety-minute figure belongs to `evidence.team_inactive_report_evidence`,
  which governs governed late swap and is a different file shape and a
  different gate. Do not quote T-90 for the pre-lock path.
- **`FILE_VALID` and the byte path are independent of the evidence verdict.**
  The same two lineups produced export SHA-256
  `08004c252695284ea96c10c291915e9c0cf316aadec944a65ca3389cfbd38df2` both as a
  blocked `proposed_sha256` and as a released `sha256`, 144 template lines in
  and 144 out with exactly lines 2 and 3 changed.

### Proposed `R16`: the official-status gate binds provenance, not a source

Found during the opener rehearsal. Not scheduled; it needs a decision before it
becomes a tranche.

A rehearsal run reached `CERTIFIED_UPLOAD_PACKAGE` under a simulated 18:00 CT
clock on an official-status CSV whose every `SOURCE_URL` was
`https://rehearsal.invalid/SYNTHETIC-NOT-OFFICIAL-EVIDENCE`. `.invalid` is an
IANA-reserved TLD that can never resolve. Two separate gaps let that through:

1. **No host check.** `evidence.py:554-556` validates only
   `scheme == "https"` and a non-empty hostname. `sources.py` maintains
   `ALLOWED_HOSTS` for automated retrieval, and nothing on this path consults
   it. Rejecting reserved and non-resolvable TLDs, or requiring an allowlisted
   host, would have refused this exact file.
2. **The validated URL is then discarded.** `parse_official_inactive_snapshot`
   populates `InactiveStatusSnapshot.source_url_by_id`
   (`evidence.py:572-573`), and `cli._official_status_evidence` builds its
   `EvidenceRecord` without a `source_url` (`cli.py:519-529`). The certified
   manifest therefore records `"source_url": null` for
   `official_inactive_status` while that record's own `reason` reads "every
   selected exact DK ID is source-bound". The CSV's bytes are hash-bound; the
   source it claims is not recorded at all, so no later audit can see what was
   asserted.

Neither is a design failure on its own: this path is operator-supplied evidence
by policy, and the operator attests to the content. What is wrong is the word
"source-bound" in a `PASS` reason and in `docs/DATA_CONTRACTS.md`, which
overstates what the gate binds. The honest description is a provenance and
freshness gate, and the cheap repairs are to record `source_url` on the record
and to reject hosts that cannot be real. The synthetic package built during the
rehearsal was destroyed; no upload-shaped CSV survived it.


### Proposed `R17`: SD2 has no live exit for Week 1 transfers and rookies

Found on the first live NE@SEA run, 2026-09-09 22:18Z. Not scheduled; it needs a
decision before it becomes a tranche.

With fresh nflverse priors and a clean identity gate, `resolve_offensive_roles`
blocked 20 of the 47 selectable people: every 2026 rookie (`MISSING_HISTORY`)
and every player whose 2025 history sits on another team
(`OFFENSIVE_TRANSFER_REQUIRES_CURRENT_TEAM_ROLE`), including A.J. Brown, Romeo
Doubs, Jadarian Price and Emanuel Wilson. The gate's only non-exclusion exit is
a `NUMERICAL_ALLOCATION` source whose excerpt is a JSON object identical to the
declaration. No approved host publishes that for a game not yet played, and
`docs/DATA_CONTRACTS.md` already records that a live compatible numerical
source has not been demonstrated. The run therefore completed only after all
20 were operator-excluded, leaving NE carry share 0.455 and SEA carry share
0.650 unallocated, which is why both review lineups lean on two QBs and a
kicker.

The gate is behaving as designed. What is missing is a designed outcome for the
case where the required evidence cannot exist yet. Three candidate decisions,
none taken here:

1. Keep the block and document operator exclusion as the Week 1 procedure,
   with the unallocated volume printed in the handoff (what happened tonight).
2. Admit a bounded, versioned "current-team history unavailable" prior for
   transfers that carries `EVIDENCE_STATE=UNKNOWN` into the report and can
   never clear certification, so a transferred WR1 is at least visible to the
   objective.
3. Add an approved numerical source. Candidates within the allowlist are
   nflverse `depth_charts` (qualitative, so it fails today's contract) and
   nothing else; a new host would need its own license decision and adapter.

Whichever is chosen, `prior_review` should report the count and salary of
blocked-and-excluded people next to the lineups so the pool coverage is visible
without reading the offensive-roles report.
