# NFL DFS Implementation Changelog

This file records completed implementation work and verification evidence for `backlog.md`. Keep entries factual and append new dated sections beneath `Unreleased`. Do not describe planned, diagnostic, synthetic, or structurally legal work as live-certified or upload-ready.

## Unreleased

### 2026-09-10: Classic and quantitative development backlog reprioritized

Planning/documentation only; no engine, test, configuration, source, run, or
lineup artifact changed.

- Replaced the competing `S*`, `W*`, `DL6`-`DL8`, and Showdown `sole next`
  development recommendations with one authoritative, dependency-ordered
  program in `backlog.md`. The historical findings remain in place and are
  mapped into the new chunks rather than discarded or relabeled complete.
- Added a bounded Classic track: C1 multi-game immutable intake/projection and
  one-command prior review; C2 exact policy/candidate/joint selection; C3
  independent audit/readable export and 1/3/20/150-entry benchmarks; C4 current
  real-file Cowork/Linux rehearsal; and C5 lock-aware slot ordering/governed
  mechanical late swap. This track delivers useful review lineups while staying
  `MODEL_STATUS=PRIOR_ONLY` and `RELEASE_DECISION=DO_NOT_UPLOAD`.
- Added the quantitative repair track for the engine's largest product gap: Q1
  immutable settlement/reference economics and predeclared metrics; Q2 joint
  calibrated player/team outcomes and participation; Q3 contest-conditioned
  ownership/legal fields/exact duplication; Q4 production payout/tie
  economics; Q5 candidate coverage and shared-scenario payout/risk portfolio
  utility; Q6 rolling-origin holdout promotion/registry/rollback; Q7
  registered-scale shadow/game-week acceptance; and QC1 governed integration
  across Classic, Showdown, and conditional late swap.
- Added DEV0 as the sole current `READY` chunk because the current 2026-09-10
  repairs are a large uncommitted layer on a deleted-upstream SD5 branch. DEV0
  preserves and reconciles that state before feature work. It allows no new
  model/Classic code and no commit, push, PR, or generated-file staging without
  separate authorization.
- Retained SD6 as the Showdown tracker's final current-file/Cowork acceptance
  item while making explicit that it is an operational acceptance task, not the
  next code-development tranche and not a prerequisite for the Classic or
  quantitative program.

### 2026-09-10: pre-slate end-to-end test and code review in the Cowork/Linux container

Full-suite and end-to-end verification of the Showdown `prior_review` path
ahead of the 2026-09-10 slate, run in the cloud container because the device
shell failed to mount (`sandbox-helper: no Plan9 drive shares mounted`, same as
2026-09-09). `sh ./nfl.sh setup` completed in 7.5s with `uv sync`. Baseline
suite: 482 passed, 1 skipped (Windows junction). Byte-exact replay of the live
excl20 run (`--request .../20260909T222153Z-ne-sea-live-excl20/run_request.json
--as-of 2026-09-09T22:21:53+00:00`) reproduced export SHA-256
`cf33f3e598270d40ea117d86ccac4ebce640b479baa8539b630f828aed585b96` before and
after every change below. Five independent reviewers covered orchestration,
priors/identity/weather, the SD2 role gate, selection/policy, and export/review.

Repairs, each pinned by `tests/test_cowork_rerun_regressions.py` (13 tests):

- `cowork.resolve_request_inputs`: an explicit `--input-dir` now outranks a
  reloaded `--request`'s snapshot paths. Before, fresh uploads on a rerun were
  silently ignored and the review CSV was built from the earlier snapshot.
  `cowork_run.json` reports `superseded_request_inputs`.
- `cli._command_cowork_run`: `--exclude`, `--unavailable-status` and
  `--available-status` merge with the reloaded request's lists
  (`LIST_MERGE_REQUEST_FIELDS`) instead of replacing them.
- `cli`: a reused `--run-id` is refused as `RUN_ID_COLLISION` before any write;
  the failure handler no longer rewrites an earlier run's `cowork_run.json`.
- `prior_review`: `lineup_count` below the reserved-entry count blocks at
  SELECT (`LINEUP_COUNT_BELOW_RESERVED_ENTRIES`) instead of exporting duplicate
  rosters that SD5 then rejected with the CSV already on disk; a surplus is
  reported in `assignment_summary`. On a READABLE_REVIEW failure the artifact
  and hash indexes no longer name the withheld CSV; `READABLE_REVIEW_FAILED.json`
  is written beside it.
- `selection.select_prior_lineups`: when the distinct-captain rule exhausts the
  selectable pool, the legacy path rebuilds without captain no-goods and
  continues with repeats, reported as
  `DISTINCT_UNTIL_POOL_EXHAUSTED_THEN_REPEATED` with
  `captain_repeats_from_index` and `captain_exposure`. Measured on the real
  26-person NE@SEA pool: 50 lineups in 16.4s (was `INFEASIBLE` at index 27).
  Time-limited (`FEASIBLE_LIMIT`) lineups are listed as `non_optimal_lineups`
  and surface as `SOLVER_TIME_LIMIT_ACCEPTED_LINEUPS`.
- `prior_review`: `PRIOR_PACKAGE_SALARY_MISMATCH` with `build_priors` set now
  re-proposes (`REBUILDING_SALARY_MISMATCHED_PACKAGE`); a frozen-artifact hash
  mismatch is still never rebuilt over.
- `prior_review`: export filename uses a sanitized label
  (`DK_REVIEW_ENTRY_<label>.csv`; `a/b c` no longer creates a subdirectory).
  Failed exports report stage `EXPORT` (was `EXPORT_BLOCKED_BLOCKED`).
- `prior_review`/`readable_review`/`workbook`: new `pool_coverage` in the
  selection report and review JSON/HTML/workbook: every person's exclusion
  reason (DK status, official INACTIVE, operator fade, role gate), FLEX and CPT
  salary by reason, per-team position coverage, and `unallocated_by_team`.
  The readable layer recomputes the salary totals from the exact salary bytes
  (`READABLE_REVIEW_POOL_COVERAGE_*` on mismatch). Exposure rows carry the
  specific `exclusion_source`. Sole-kicker assumptions from
  `selection.kicker_roles` now appear on the kicker's slot and in the evidence
  table (were `NO_NAMED_ROLE_FINDING`). A reused frozen package reports its
  inherited weather basis. The workbook Upload sheet names the review CSV and
  SHA-256 as `REVIEW ONLY (not certified)`.
- `cli`: new `--official-status-csv` on `cowork-run`; a supplied file that omits
  selected people reports `OFFICIAL_STATUS_INCOMPLETE_FOR_SELECTED` with names,
  instead of clearing the requirement on presence alone.
- `scripts/make_official_status.py`: Eastern via `ZoneInfo`, not a fixed -4.

Verification after repairs: 495 passed, 1 skipped in 109.5s on Python 3.13.7;
replay export hash unchanged; the readable HTML shows the pool-coverage
section and kicker assumption; the eight-sheet workbook opens with the new
Exposure section. Environment facts this session: `github.com` and
`api.github.com` fail Python 3.13 strict X.509 verification behind the container
egress proxy (CA lacks Key Usage) while `raw.githubusercontent.com` passes, so
`--build-priors` stops at `PRIORS_PROPOSE_FAILED` in the container without the
previously approved venv-level relaxation; `api.weather.gov` is denied (403).
Owner decisions taken the same day, and landed:

- TLS (`src/nfl_dfs/sources.py`, `tests/test_sources_tls.py`): opt-in
  `NFL_DFS_TLS_ALLOW_NONSTRICT_CA=1` clears only `ssl.VERIFY_X509_STRICT`;
  `CERT_REQUIRED` and hostname checking stay on, and every captured artifact
  records `coverage.tls_verify_x509_strict`. Default strict. Verified: strict
  still fails in the container; opt-in fetched all seven nflverse artifacts in
  9s with the flag stamped on each, and the live chain proceeded to the
  expected `WEATHER_CAPTURE_REQUIRED` stop for the outdoor NE@SEA row.
- R17, per Ben's direction to use prior-team stats (`src/nfl_dfs/priors.py`
  `transfer_prior_from_old_team`, `_team_week_totals`;
  `src/nfl_dfs/offensive_roles.py`; `docs/DATA_CONTRACTS.md`; `CLAUDE.md`):
  a transfer carries his own prior-season share of his old team's volume (own
  count over the old team's count in the weeks he had a row, per column, from
  the same frozen `player_stats` bytes) into the current pool's normalization
  as a pseudo-count; incumbents scale by `1/(1+Σs)`. Record keeps
  `EVIDENCE_STATE=UNKNOWN`; the gate reports `TRANSFER_PRIOR_UNVERIFIED`
  (diagnostic) or `TRANSFER_PRIOR_ZERO` (exclude). `MISSING_HISTORY` is now a
  visible zero-share exclusion (`OFFENSIVE_MISSING_HISTORY`) named with salary
  in `pool_coverage`, not a stop; a person with no prior record at all still
  blocks (`OFFENSIVE_PRIOR_ROW_MISSING`), and a declared material role change
  still blocks. Packages frozen before this change carry no `transfer_prior`
  and their transfers still block, which is the rebuild signal. Offline replay
  of the live NE@SEA chain against the frozen 2026-09-09 raw captures with no
  operator excludes: completes, 33 selectable people (was 26 after 20 manual
  excludes); A.J. Brown 0.175 NE target share (0.295 at PHI), Doubs 0.112,
  Emanuel Wilson 0.203 SEA carry share, Kiner 0.135; 12 rookies excluded
  visibly; Latu `TRANSFER_PRIOR_ZERO`. Rookie priors from approved draft or
  combine artifacts remain open (no captured mapping to usage exists).
- R18 (`src/nfl_dfs/portfolio_enforcement.py`, `optimizer.add_required_row`,
  the policy branch of `selection.py`, `tests/test_portfolio_enforcement.py`):
  the SD4 candidate bank is now policy-aware: per-captain strata, per-capped-
  person exclusion strata, a greedy policy-feasible chain, then top-K fill;
  bounds scale as `max(32, 4×entries)` candidates, `max(30s, 2s×entries)`
  generation, `max(10s, 1s×entries)` joint solve, with per-stratum counts in
  the report. Verified on the real 68-person pool: 20 entries, captain cap
  0.25, combined cap 0.6 on JSN and Maye, overlap 4 →
  `ENFORCED_AND_INDEPENDENTLY_AUDITED` in 7.3s (was
  `CANDIDATE_BANK_EXHAUSTED_INCOMPLETE`), captains Maye 5 / JSN 5 / Henry 4 /
  Darnold 4 / Stevenson 1 / Myers 1, JSN and Maye at exactly 12/20, max pairwise
  overlap 4, audit PASS, byte-identical on repeat. The 5-entry cases from the
  backlog (captain 0.2; combined 0.8) also pass.

Final verification: 516 passed, 1 skipped in 79.8s; no-policy replay export
SHA-256 `cf33f3e5…` unchanged after every change. Truths remain
`PRIOR_ONLY` / `DO_NOT_UPLOAD`; nothing here is a projection, ownership or
edge claim.

### 2026-09-09 — SD5 readable, exact-artifact-bound review

Closes SD5 for software and rendered-review acceptance. Added
`src/nfl_dfs/readable_review.py` and `tests/test_readable_review.py`; extended
the prior-review selection record, CLI and workbook writer; and updated the
Showdown tracker, backlog, Cowork/contract/implementation documentation and the
complete SD6 handoff prompt.

After a valid Showdown prior-review export, the new presentation boundary
strictly reparses the exact salary, entry, assignment, exported review CSV and
selection-report bytes. Policy-bearing runs also reparse the normalized policy
and independent audit. It checks every applicable SHA-256 binding and
independently recomputes exact Entry-ID order, roster/person/role identity,
legality, salary and remaining salary, prior-only points, combined-person and
Captain counts/percentages/maxima, exclusions, canonical uniqueness and every
pairwise overlap. Only a discrepancy-free result publishes canonical JSON,
escaped self-contained HTML and an eight-sheet readable workbook. Markup and
spreadsheet-active prefixes are inert at display boundaries without changing
exact source bytes. Any mismatch stops at `READABLE_REVIEW`, reports a named
blocker, preserves earlier artifacts and withholds a top-level review-export
path.

The workbook exposes exact assignments, exposure, evidence/role observations,
provenance links and hashes, all four independent truths and one next operator
action. Its output-only print areas, repeated headings and normalized freeze
views do not change the five-sheet input contract. Native Excel initially found
and repaired stale right-pane selection metadata inherited by Portfolio; the
writer now emits one valid selection view, and final two-entry and five-entry
samples both open normally without repair.

Verification on pinned Python 3.13.7: focused SD5/prior-review/policy/Cowork
regressions 120 passed, 1 skipped in 48.32s; a post-review missing-artifact
regression passed in 4.10s; final complete suite 482 passed, 1 skipped in 91.93s.
The skip is the existing Windows symlink-privilege case. Doctor
passed with SQLite `ok`/WAL, no Excel lock or sync/reparse finding; Windows long
paths remain disabled. The independent spreadsheet renderer found zero formula
errors and rendered all eight sheets for both fixtures. Native Excel exported
and visual review accepted all 18 pages of the two-entry workbook and all 20
pages of the five-entry workbook, including continued headings and warning
hierarchy.

Ignored accepted closeout samples are
`outputs/sd5-render-bfcf2ed5/two-entry-closeout.xlsx` (SHA-256
`2f374cbc66c702b5da075f9f559d7ccd5ab49b8ee87ea2ae128ef67dd66f4d62`)
and `five-entry-closeout.xlsx` (SHA-256
`69028b0acc5352fce409bd11f6249dbd42acb63f3c2c7d768062d1718e9c38bd`).
Their readable JSON/HTML reconciliation status was `PASS`; exact hashes are
recorded in the Showdown tracker. Representative truths remained
`FILE_VALID=true`, `EVIDENCE_STATE=UNKNOWN`, `MODEL_STATUS=PRIOR_ONLY`, and
`RELEASE_DECISION=DO_NOT_UPLOAD`. Actual Cowork/Linux, current game evidence,
larger portfolios and prospective model/economic quality remain unverified.
SD6 is the sole next READY item.

### 2026-09-09 — First live NE@SEA Showdown run through Cowork (operations record, no code change)

Live run at 22:06Z against the 22:06Z DraftKings salary download and the
2026-09-08 reserved-entry template, run in the Cowork cloud container because
the device shell never mounted the repository this session. Full record in
`data/runs/20260909-showdown-ne-sea-live-2206z/RUN_NOTES.md`.

Changed:

- No source change. Three managed run folders added under `data/runs/`:
  `20260909T221133Z-ne-sea-live` (`PRIORS_PROPOSE_FAILED`, TLS),
  `20260909T221851Z-ne-sea-live` (fresh priors frozen, projection OK,
  `SELECTION_FAILED` at the SD2 gate with 20 named people) and
  `20260909T222153Z-ne-sea-live-excl20` (same frozen package, the 20 people
  operator-excluded, exit 0, `DK_REVIEW_ENTRY` written).

Verification:

- Suite on the working tree, pinned 3.13.7, pip-built venv: 475 passed,
  1 skipped, 39.6s.
- Export byte audit: 144 lines in and out, only lines 2 and 3 changed, SHA-256
  `cf33f3e598270d40ea117d86ccac4ebce640b479baa8539b630f828aed585b96`, size
  15,730 bytes identical on the container and on Ben's disk.
- Independent legality re-check of both entries from the salary bytes: LEGAL,
  $49,100 and $48,800, both teams, no OUT/IR, 4 shared people.

Remaining blockers:

- `FILE_VALID=true`, `EVIDENCE_STATE=UNKNOWN`, `MODEL_STATUS=PRIOR_ONLY`,
  `RELEASE_DECISION=DO_NOT_UPLOAD`. No official activity evidence was supplied.
- SD2 blocked 20 selectable people (14 NE, 6 SEA) for missing 2025 history or
  a team transfer, and the only exit the contract offers is a
  `NUMERICAL_ALLOCATION` source that `docs/DATA_CONTRACTS.md` itself says has
  not been demonstrated live. See the proposed `R17` in `backlog.md`.

Environment findings (not defects in this repository):

- Python 3.13 `VERIFY_X509_STRICT` rejects the Cowork container's egress-proxy
  CA (no Key Usage extension); `sources.fetch_public_artifact` fails with
  `CERTIFICATE_VERIFY_FAILED`. Ben approved a venv-local `sitecustomize.py`
  shim that drops only that flag; chain and hostname verification stayed on.
- `api.weather.gov` is denied by the container proxy; the forecast was read
  through the Claude browser pane and retained as text with its hash.

Claims explicitly not made:

- No live-slate, calibrated-EV, ownership, leverage, ceiling or
  upload-readiness claim. The two lineups are the chalkiest legal build over a
  26-person pool with the run games of both teams mostly unallocated.

### 2026-09-09 — SD4 bounded portfolio enforcement and independent audit

Closes SD4 for software acceptance. Added
`src/nfl_dfs/portfolio_enforcement.py` and
`tests/test_portfolio_enforcement.py`; connected the validated SD3 policy to
bounded Showdown `prior_review` candidate generation, joint MILP selection,
exact Entry-ID assignment and an independent final-assignment audit; and updated
the CLI, optimizer, selection, prior-review/export integration, Cowork guidance,
contract/implementation documentation, tracker and backlog.

Policy-bearing runs enforce effective combined-person and Captain maxima,
exclusions, canonical uniqueness and configured pairwise underlying-person
overlap across the complete requested assignment. Explicit Captain maxima
replace the policy-free forced-distinct-Captain convention only when a policy is
supplied. Assignment cycling is prohibited. The final audit reparses the exact
normalized policy and assignment bytes immediately before export, recomputes DK
legality and every policy control from roster IDs, and binds salary, entry,
source-policy, normalized-policy and assignment SHA-256 values. Failed or
unknown selection/audit, stale or changed bytes, incomplete assignments and
unsupported profiles write no new review CSV and preserve earlier outputs.

Candidate generation defaults to a 32-lineup cap, 30-second total budget and
2-second per-solve budget; joint selection has a 10-second budget. Reports keep
complete-bank infeasibility distinct from candidate-limit exhaustion, incomplete
coverage, time/search limits and solver errors. An `OPTIMAL` result applies only
to the explicitly reported actual candidate bank. A two-entry replay produced
32 candidates, selected 2 entries, passed the independent audit and reproduced
identical review bytes and assignment/policy hashes. A five-entry rehearsal
produced 32 candidates in 2.361s, solved the actual-bank MILP in 0.013s at a zero
reported gap and one node, and measured 66,797,568 peak process working-set
bytes. Both banks were truthfully `CANDIDATE_LIMIT_REACHED_INCOMPLETE`; neither
run proves complete-slate feasibility or 20/150-entry readiness.

Verification: focused SD4 and related regressions 116 passed in 44.86s; broader
regressions 225 passed, 1 skipped in 111.25s; post-review artifact-reparse focus
59 passed in 17.95s; final complete pinned-runtime suite 475 passed, 1 skipped
in 71.33s. The skip is the existing Windows
symlink-privilege case. Doctor and `git diff --check` passed. A representative
synthetic success remained `FILE_VALID=true`, `EVIDENCE_STATE=UNKNOWN`,
`MODEL_STATUS=PRIOR_ONLY`, `RELEASE_DECISION=DO_NOT_UPLOAD`. Actual Cowork/Linux,
live evidence/policy use, larger portfolios and prospective model or economic
quality remain unverified. SD5 is the sole next READY item; its prompt is
`docs/session-prompts/SD5-readable-artifact-bound-review.md`.

### 2026-09-09 — SD3 exact-bound portfolio-policy contract

Closes SD3 for software acceptance. Added
`src/nfl_dfs/portfolio_policy.py` and `tests/test_portfolio_policy.py`; integrated
the optional contract through `cowork.py`, CLI parsing/confinement/snapshots,
generated run requests and `workbook.py`; and updated `CLAUDE.md`,
`IMPLEMENTATION_STATUS.md`, `docs/DATA_CONTRACTS.md`,
`docs/COWORK_RUNBOOK.md`, the Showdown tracker and backlog.

`nfl_showdown_portfolio_policy_v1` binds the exact salary SHA-256, single game,
complete underlying-person/CPT/FLEX map and all requested Entry IDs. It accepts
only explicit numeric fractions in `[0,1]` and converts them with exact-decimal
`floor(fraction * requested_entry_count)`. Defaults, overrides, zero/one,
Captain-as-subset tightening, exclusions, canonical uniqueness and underlying-
person overlap are deterministic and explicit. Necessary capacity findings do
not claim solver infeasibility. `nfl_showdown_portfolio_policy_normalized_v1`
has stable canonical bytes; its reported normalized hash equals the exact file
hash, separately from the original source-policy hash.

SD3 does not change selection or implement enforcement. Every policy-bearing
execution stops before selection/export at
`PORTFOLIO_POLICY_ENFORCEMENT_UNSUPPORTED_SD3`, retains validation/normalized
artifacts and both hashes, preserves earlier outputs and writes no new
`DK_REVIEW_ENTRY` CSV. Policy-free SD1/SD2 behavior is unchanged. The retained
synthetic boundary run reports `FILE_VALID=false`, `EVIDENCE_STATE=UNKNOWN`,
`MODEL_STATUS=PRIOR_ONLY`, `RELEASE_DECISION=DO_NOT_UPLOAD`.

Verification: focused contract/Cowork suite 76 passed, 1 skipped in 10.04s;
broad regressions 120 passed, 1 skipped in 19.13s; post-review hash-binding
focus 76 passed, 1 skipped in 10.73s. A first complete run recorded 439 passed,
1 failed, 1 skipped in 94.18s because its GUID-derived test path reached 261
characters while Windows long paths are disabled. The same copied-package test
passed under short isolated roots. Final complete pinned-runtime suite: 440
passed, 1 skipped in 57.57s; doctor and `git diff --check` passed. The skip is
the existing Windows symlink-privilege case. Actual Cowork/Linux, live policy
use and multi-entry enforcement remain unverified. SD4 is now the sole next
READY item; its prompt is
`docs/session-prompts/SD4-enforce-and-audit-portfolio-controls.md`.

### 2026-09-09 — SD2 offensive roles and explicit historical basis

Added `nfl_offensive_role_evidence_v1` alongside the unchanged SD1 kicker
contract. Exact salary/game/team/CPT/FLEX person bindings, captured approved
source bytes/hashes, original times and the registered deterministic numerical
transformation govern complete team opportunity allocations. Qualitative facts
cannot invent shares. Supported allocations conserve five team share groups,
retain deliberately unallocated volume, require missing receiving efficiency,
and are never capped at historical snap share. Every exclusion takes precedence;
an excluded positive recipient requires refreshed evidence.

Prior adapter v2 now uses current-team historical rows for opportunity and
efficiency. Missing/blank history and incompatible transfers remain `UNKNOWN`;
an old-team receiver's reproduced `0.535714` target weight cannot enter his new
team denominator. The promoted-backup regression moves from 0.15 to a supported
0.75 carry share above an unchanged 0.20 historical capacity. One finding per
offensive person distinguishes observed zero, missing history, unknown current
role, explicit nonparticipation and source-supported adjustment. Missing/material
unresolved roles block selection; unknown after values are null. Observed-zero
people cannot become punts. Prior review retains excluded volume unallocated
instead of automatically redistributing it. Older frozen packages without SD2
history coverage must be rebuilt; Classic's previous gates remain unchanged.

Threaded `offensive_role_evidence_json` through request/CLI parsing, confinement,
immutable snapshots, scoring, selection, reporting and final hash/expiry checks.
Invalid evidence leaves named blockers and no new review CSV, preserving earlier
outputs. A real freeze/project/Cowork synthetic integration exposed and repaired
the LA/LAR team-split lookup through the frozen exact identity map; original and
portable replay now produce identical final CSV bytes. Review also covered the
larger excerpt needed for a complete offensive-team declaration.

Final pinned Windows suite: **416 passed, 1 skipped in 61.58s**; the skip is the
existing Windows symlink-creation privilege case. Doctor and `git diff --check`
passed. All 15 implementation/test files match the hashes frozen before the
final suite. Complete commands, review findings, artifact hashes and logs are
in the SD2 completion record in the Showdown priority tracker.

Successful synthetic full-chain output retained `FILE_VALID=true`,
`EVIDENCE_STATE=UNKNOWN`, `MODEL_STATUS=PRIOR_ONLY` and
`RELEASE_DECISION=DO_NOT_UPLOAD`. No live slate or actual Cowork/Linux run was
performed. Compatible live numerical offensive-role captures, current official
evidence, the full forward-role model, W3 simulator mask and model/economic
validation remain open. SD2 is DONE; SD3 is the sole next READY priority and its
prompt is written. SD4–SD6 remain blocked. Nothing was staged, committed or pushed;
pre-existing untracked user artifacts and older prompts were preserved.

### 2026-09-09 — SD1 source-bound kicker roles and conserved scoring

Reproduced the two-kicker scoring defect numerically: adding a second eligible
New England kicker changed one 8.4-point team kicking line into 16.8 combined
points. Added the strict `nfl_kicker_role_evidence_v1` contract and applied its
allocation to team kicking events once, before DraftKings scoring and the 1.5x
Captain multiplier. Exact current salary/game/team and CPT/FLEX person identity,
content-addressed captured bytes, hashes, approved source policy, observation/
capture/expiry times, transformation version and a fixed share tolerance are
validated. Qualitative captures may establish only a supported sole role;
fractional splits require matching structured numerical source content.

Role resolution now runs after salary, official inactive and operator
exclusions. Ambiguous multi-kicker teams stop with `KICKER_ROLE_UNRESOLVED`;
zero-share people are excluded from selection; an excluded declared recipient
requires refreshed evidence; no eligible kicker receives no fabricated points.
Exactly one eligible kicker without an artifact remains compatible only through
a visible `PRIOR_ONLY_SOLE_LISTED_ASSUMPTION`, which does not establish current
role or official ACTIVE status. Invalid supplied evidence never falls back.

Threaded `role_evidence_json` through Cowork/CLI request parsing, path
confinement, immutable manifest/source snapshots, copied-package replay,
prior-review selection, machine-readable reports, operator workbook guidance and
final hash/freshness checks. Invalid, tampered or expired evidence leaves a named
blocker and no new review-entry CSV. The synthetic full Cowork integration kept
`FILE_VALID=true`, `EVIDENCE_STATE=UNKNOWN`, `MODEL_STATUS=PRIOR_ONLY`, and
`RELEASE_DECISION=DO_NOT_UPLOAD` independently.

Pinned Windows verification: 357 passed, 1 skipped in 69.05 seconds; the skip is
the existing symlink-permission case. `nfl.ps1 doctor`, SD2 prompt self-check and
`git diff --check` passed. No live approved kicker-role capture or actual
Cowork/Linux run was performed, so live role evidence and Linux acceptance remain
unverified. SD2 is now the sole next READY priority; broader W3 and model/
economic readiness remain blocked. Nothing was staged, committed or pushed.

### 2026-09-09 — Showdown priority session plan (documentation only)

Added `docs/SHOWDOWN_PRIORITY_TRACKER_2026-09-09.md` with six bounded chunks,
dependencies, acceptance checks, full-mandate limitations and required session
closeout records. SD1 is the next READY item: source-bound kicker roles and
conservation of team kicking production. Added its complete implementation
prompt under `docs/session-prompts/SD1-current-role-and-kicker-scoring.md` and a
current-priority pointer in `backlog.md`'s tracker protocol.

Verified branch/HEAD `codex/s6a-deterministic-projection-producer` /
`6b5d4625b6fa3234a07680ca27dafc819fbd05ab`, inspected current code and retained
readiness evidence, and preserved existing untracked work. No runtime changes,
test-suite rerun, staging, commit or push. The 332-passed/1-skipped result belongs
to the preceding implementation review. All six chunks remain unimplemented;
generated portfolios remain `PRIOR_ONLY / DO_NOT_UPLOAD`. Document link, fence,
whitespace and queue-consistency checks passed, as did `git diff --check`.

### 2026-09-09 — Real Showdown workflow review and readiness repairs

User-authorized end-to-end review, retaining all pre-existing W6/runbook and
other work. Baseline suite: 307 passed, 1 skipped in 81.14 seconds. Final suite:
332 passed, 1 skipped in 63.06 seconds, using pinned Python 3.13.7, a unique
project-local `--basetemp`, and `-p no:cacheprovider`. Machine-readable result:
`outputs/readiness-20260909-verified.xml`; full log beside it. `git diff --check`
passes. No staging, commits, pushes or cleanup of prior work.

Fixed live source-acquisition clock handling, current supplied inactive
exclusions across CPT/FLEX, export-time freshness checks, official provenance
shape/role conflicts/URL retention, strict preflight manifest/policy/model
requirements and actual-roster activity reconciliation, Windows preflight
launcher support, relative CLI paths, raw-source portability, six-hour weather
expiry, minimum validation samples, history/field promotion gates and temporal
training leakage. The complete detail is in
`docs/READINESS_REVIEW_2026-09-09.md`; operating instructions now route normal
Showdown generation through the prior-review profile.

Approved nflverse and NWS retrieval succeeded from Windows. The actual NE–SEA
136-row/68-person pool and two-entry template completed generation and repeated
review export. Independent QA found two legal distinct lineups, 144 lines
preserved, only lines 2 and 3 changed, and identical repeated SHA-256
`87156b8c108bfe1585c4dc1c689258ee3fd24f525543ae19667be2017cee359e`.
Result: `FILE_VALID=true`, `EVIDENCE_STATE=UNKNOWN`, `MODEL_STATUS=PRIOR_ONLY`,
`RELEASE_DECISION=DO_NOT_UPLOAD`. The captured forecast expires at
2026-09-09T20:00:40Z, before kickoff, so evening evidence must be refreshed.

Remaining: full ceiling/ownership/drawdown modeling, W3 simulator participation,
W8/W9 economics/exposure controls, live official activity, prospective model
validation/registry, and actual Cowork/Linux and large-portfolio acceptance.
No generated portfolio was certified; no DraftKings account action occurred.

### 2026-09-08 — W6: `audit` is historical only, and `preflight` is the live pre-upload check

Closes `W6` / R09. Files added: `src/nfl_dfs/preflight.py`,
`tests/test_w6_live_preflight.py`, `scripts/make_official_status.py`,
`docs/OPENER_RUNBOOK_2026-09-09.md`. Files modified: `src/nfl_dfs/cli.py`
(the `command_audit` body, the new `command_preflight`, one import, and the
`preflight` subparser), `backlog.md`, `changelog.md`. Nothing staged or
committed. `MODEL_STATUS` and `RELEASE_DECISION` are unchanged on every path
that had them, no gate was weakened, no expiry was widened, and
`AvgPointsPerGame` remains confined to untouched raw DraftKings bytes.

HEAD at session start: `6cd710e5b3a02af163d3ae029eb849c0d1e2a92b` on
`codex/s6a-deterministic-projection-producer`, matching
`origin/codex/s6a-deterministic-projection-producer`. `W2` was pushed.

#### R09, reproduced first

Fifteen probes in `tests/test_w6_live_preflight.py`. All fifteen fail on
`6cd710e` (`nfl_dfs.preflight` and `command_preflight` do not exist, so the
module does not import). The behavioral reproduction, run against a copy of
`6cd710e` with only `command_audit` restored:

```text
certified at build time: CERTIFIED_UPLOAD_PACKAGE
evidence rewritten to expire 2026-01-15; output bytes untouched, hash matches
--- pre-W6 audit ---
  exit code        : 0
  status           : PASS
  EVIDENCE_STATE   : PASS
  RELEASE_DECISION : CERTIFIED_UPLOAD_PACKAGE
  problems         : []
```

That is the review's own reproduction: a stored green result stays green after
its evidence expires, because `audit` fed the manifest's stored
`EVIDENCE_STATE` and `MODEL_STATUS` straight into `derive_release_policy` and
never re-derived anything at a clock.

#### The split

`audit` now answers only the archival question through
`preflight.historical_artifact_integrity`: the manifest parses, its
`manifest_version` is one this code understands, and the bytes it names still
hash to what it recorded. It reports `ARTIFACT_INTEGRITY`, surfaces the
manifest's own claim as `manifest_stored_RELEASE_DECISION`, and pins its own
`RELEASE_DECISION` to `DO_NOT_UPLOAD` with
`release_decision_basis: HISTORICAL_ONLY`. Its exit code is the integrity
verdict, which is now a well-defined thing to be, because the payload can no
longer be misread as permission.

`preflight` is the live check, `preflight.live_pre_upload_check`. At
`evidence.release_clock()` by default, or any clock the caller supplies, it:

- validates the manifest schema and rebuilds every `EvidenceRecord` through
  `model_validate`, so a malformed record is a blocker rather than a silent
  skip;
- requires the surviving hard fields to cover every entry in
  `config/evidence_policy.json`, the same policy certification read, so
  deleting the inconvenient record is refused as `MANIFEST_EVIDENCE_SCOPE`;
- re-derives each state through `EvidenceRecord.state_at(when)` and aggregates
  with `release.aggregate_evidence_state(..., final_release=True)`;
- rebinds `salary`, `entries`, `assignments` and the output CSV by SHA-256
  against files on disk;
- re-derives selected-player locks from the current salary pool, so a package
  certified before lock is refused after it, and refuses to certify at all
  without a salary CSV (`LIVE_BINDING_INCOMPLETE`), because locks cannot be
  re-derived without one;
- reports `checked_at` and a per-check `scope` of `MANIFEST_SCHEMA`,
  `LIVE_RECOMPUTE` or `FILE_BINDING`;
- exits 0 only on `CERTIFIED_UPLOAD_PACKAGE`.

The same expired package, after the repair:

```text
audit (historical):  ARTIFACT_INTEGRITY=PASS  RELEASE_DECISION=DO_NOT_UPLOAD
                     manifest_stored_RELEASE_DECISION=CERTIFIED_UPLOAD_PACKAGE
preflight (live):    EVIDENCE_STATE=STALE     RELEASE_DECISION=DO_NOT_UPLOAD
  blockers: selected.official_inactive_status:STALE:official exact IDs
  checks:   manifest_readable   MANIFEST_SCHEMA  PASS
            manifest_schema     MANIFEST_SCHEMA  PASS
            evidence_schema     MANIFEST_SCHEMA  PASS
            evidence_scope      LIVE_RECOMPUTE   PASS
            evidence_states_at_current_clock     LIVE_RECOMPUTE  FAIL
            output_bytes        FILE_BINDING     PASS
            input_salary        FILE_BINDING     PASS
            selected_player_locks                LIVE_RECOMPUTE  PASS
```

`preflight` is built on what `W2` left: `evidence.release_clock()` is the live
clock, `EvidenceRecord.state_at()` re-derives staleness from a stored
`expires_at`, and `release.aggregate_evidence_state` already took both a
`required_hard_fields` set and a `now`. Nothing new was written to decide
freshness.

#### Verification

```text
export NFL_DFS_VENV_DIR=/tmp/w6-venv
export NFL_DFS_UV_CACHE_DIR=/tmp/w6-uvcache
export NFL_DFS_UV_PYTHON_DIR=/tmp/w6-uvpython
sh ./nfl.sh setup                                                  SETUP_COMPLETE
sh ./nfl.sh test -p no:cacheprovider --ignore=.pytest_cache tests -rs
```

```text
1. baseline on 6cd710e, device shell, 3.13.7, local-disk working copy
   293 collected, 292 passed, 1 skipped, exit 0, 9.89s
   The one skip is tests/test_cowork.py:115, the Windows junction test.

2. the 15 W6 probes on 6cd710e     collection error, module does not exist
   the same 15 after the repair    15 passed, 2.96s

3. full suite after the repair
   308 collected, 307 passed, 1 skipped, exit 0, 19.15s
   No existing test was changed, deleted or disabled.

4. doctor pass_status true; compileall clean on preflight.py and cli.py;
   no trailing whitespace and no tabs in any changed file.
```

The prescribed `sh ./nfl.sh test -q ...` was run first and is what produced the
293/292/1 count, but it prints no summary line: `pyproject.toml` already sets
`addopts = "-q"`, so the extra flag is `-qq`. The counts above come from the
same invocation without the duplicate flag.

#### The opener rehearsal, 2026-09-08

Full MANUAL_GUARDRAIL certify path driven end to end on the real
`DKSalaries_NE_SEA.csv` and `DKEntries_NE_SEA.csv` under
`data/runs/20260909-showdown-ne-sea/inputs/`, with two mechanically constructed
stand-in lineups, a stand-in payout table, and a deliberately synthetic
official-status file. Lock read from the salary CSV's `Game Info`:
`NE@SEA 09/09/2026 08:20PM ET`, so 2026-09-09 19:20 CT.

```text
run A   live clock, both entries identical
        450 ms, exit 2, DO_NOT_UPLOAD, FILE_VALID false
        blockers: DUPLICATE_SELECTED_LINEUPS
                  official_inactive_status:STALE (3-hour lock window)

run A2  live clock, two distinct lineups
        868 ms, exit 2, DO_NOT_UPLOAD, FILE_VALID true
        one blocker: official_inactive_status:STALE
        proposed_sha256 08004c25...8df2, no upload CSV written

run B   simulated 18:00 CT release clock, observation 17:55 CT
        48 ms, exit 0, CERTIFIED_UPLOAD_PACKAGE, EVIDENCE_STATE PASS
        sha256 08004c25...8df2, identical to run A2's proposed bytes
        144 template lines in, 144 out, exactly lines 2 and 3 changed
```

Run B used a harness that injects a clock into `_official_status_evidence`
alone. It weakens nothing: the same three-hour window rules are evaluated, at a
simulated 18:00 CT. The certify path has no clock flag and should not get one.

**Run B reached `CERTIFIED_UPLOAD_PACKAGE` on invented evidence, and that is
reported as a finding, not kept.** Its `SOURCE_URL` was
`https://rehearsal.invalid/SYNTHETIC-NOT-OFFICIAL-EVIDENCE`. The synthetic
package and its upload CSV were deleted; no upload-shaped CSV survived the
rehearsal. See the proposed `R16` note in `backlog.md`: the gate checks
`https://` plus a hostname, consults no allowlist, and then discards the URL,
so the certified manifest records `"source_url": null` under a `reason` that
says "source-bound".

`docs/OPENER_RUNBOOK_2026-09-09.md` is the numbered checklist Ben executes
himself between 17:50 and 19:20 CT, with the certify command spelled out
literally, the expected output fields named, and a stop rule for each failure
mode. `scripts/make_official_status.py` generates the official-status CSV from
the salary CSV and the assignment CSV, resolving `TEAM` so a player/team
conflict cannot be typed by hand, and warning when the observation falls
outside the window derived from `Game Info`. Standard library only, so it runs
under any Python 3.9+ without the project environment.

#### Remaining blockers and open flags

- `[BEN: payout table]`, `[BEN: advertised prize value]`,
  `[BEN: ticket face value]`, `[BEN: field size]`,
  `[BEN: fresh DK salary CSV and DKEntries template for 2026-09-09]`,
  `[BEN: the two lineups]`. All six were asked for in one message and none has
  been answered yet. DL4 and DL5 stay `BLOCKED` on them.
- Contest facts already read from the entry template and therefore not asked
  for: contest ID `193391013`, entry fee `$20`, reserved entries `5232816721`
  and `5238395397`.
- The frozen NE@SEA prior package expired at `2026-09-09T04:37:46Z`. Nothing in
  the manual-guardrail path needs it. Any path that does needs a rebuild, and
  the rebuild stops at `WEATHER_CAPTURE_REQUIRED:roof=outdoors` for an operator
  capture.
- R03's simulator availability mask, the absent ownership/leverage/correlation
  and duplication models, and
  `projection.py`'s `SALARY_PERSON_IDENTITY_COVERAGE_MISMATCH` are all still
  open and untouched by `W6`.

#### What this does not do

`preflight` re-derives states from what a manifest recorded and from files on
disk. It does not reopen a source, refetch a page, or judge whether recorded
evidence was true when it was recorded. R16 is exactly that gap on the
official-status path and is not repaired here. A `CERTIFIED_UPLOAD_PACKAGE`
from `preflight` still means the exact bytes passed every current hard gate at
`checked_at`, and still says nothing about whether a lineup is any good.


### 2026-09-09 — W2: source expiry preserved across every boundary, and a selection objective independent of scenario count

Closes `W2` / R07 and R08. Files added:
`tests/test_w2_source_expiry_and_objective.py`. Files modified:
`src/nfl_dfs/contracts.py`, `src/nfl_dfs/evidence.py`,
`src/nfl_dfs/projection.py`, `src/nfl_dfs/portfolio.py`,
`src/nfl_dfs/prior_review.py`, `src/nfl_dfs/cli.py`, `src/nfl_dfs/qa.py`,
`tests/test_projection_producer.py`, `tests/test_priors_adapter.py`,
`tests/test_prior_review_profile.py`, `tests/test_build_pipeline.py`,
`backlog.md`, `changelog.md`.

`MODEL_STATUS` stays `PRIOR_ONLY` and `RELEASE_DECISION` stays `DO_NOT_UPLOAD`
on every path that had them. No gate was weakened, no expiry was widened, no
ownership, leverage, correlation or duplication model was added, and
`AvgPointsPerGame` remains confined to untouched raw DraftKings bytes.

#### The two defects, reproduced first

Both were written as failing tests before anything was repaired, and both
reproduce the review's own independent reproductions. All fourteen probes in
`tests/test_w2_source_expiry_and_objective.py` fail on `f318882` and pass now.

```text
R08  validate_source_ledger on a package whose sources expired 2026-09-05,
     asked at a 2026-09-08 clock          -> DID NOT RAISE
R08  the same ledger copied to a new directory, same clock
                                          -> DID NOT RAISE
R08  a copied package with the original attachments deleted
     -> EvidenceError: source ledger artifact is missing:
        .../build/DKSalaries.csv
R07  two candidates, one fixed 100-scenario payout distribution
     100 rows      -> selected candidate 0, the constant 1.5
     same rows x100 -> selected candidate 1, mean 2.0, sd 4.0
     assert (0,) == (1,)
```

#### R08 — the consumed contract now carries its own expiry

`nfl_source_ledger_v2`. A ledger entry carries `expires_at`,
`evidence_state`, `evidence_scope`, `transformation_version` and
`depends_on`, and addresses its bytes by a package-relative POSIX path.
`nfl_source_ledger_v1` stays readable as the legacy shape and may not carry
any of those fields, so a producer cannot half-migrate. One freshness rule
lives in `contracts.SourceFreshness`; the producer, the ledger validator and
`prior_review.resolve_prior_package` all evaluate it instead of keeping three
copies. The declared state and the expiry verdict compose worst-first, so a
`NOT_APPLICABLE` or `NOT_YET_DUE` label cannot suppress staleness, and the
reported window is always the earliest expiry in the set.

`build_projection_package` archives all four consumed sources
content-addressed under `<package>/sources/<sha256><ext>` and re-verifies them
after publish, so a copied package resolves with every original attachment
deleted and needs no Windows-to-Linux path rewrite. `_snapshot_inputs` carries
that subtree alongside a snapshotted ledger, which is the boundary Cowork
crosses on every run.

`validate_source_ledger` re-evaluates each entry at the clock it is given:
`projection.py` passes the run's `as_of`, a replay clock, and anything that
omits a clock gets `evidence.release_clock()`, the live one. Certification
routes through the new `evidence.source_ledger_evidence`, whose hard-gate
`EvidenceRecord` carries the earliest source expiry so `evaluate_hard_gates`
re-derives `STALE` at final release without reopening a source. A stale
package reports `STALE`, a tampered one `CONFLICTED`, and a legacy `v1`
package `UNKNOWN`: a shape that cannot express an expiry cannot clear the
gate.

`projection.verify_projection_package` closes the other half. The ledger is a
plain JSON file, so every declared expiry, state, observation time and source
URI is checked back against the archived source's own metadata, whose bytes
are hash-bound, and the entry set must cover all four scopes. Forging an
expiry and deleting the inconvenient entry are both refused.

`prior_review` re-evaluates the produced package's expiry before selection and
blocks `PROJECTION_PACKAGE_NOT_FRESH` rather than selecting on stale inputs.
`resolve_frozen_artifact` now looks inside the package first and records
whether it answered `IN_PACKAGE` or by `FALLBACK_SEARCH`.

#### R07 — a declared risk preference instead of a confidence bound

`RISK_MEASURE = "MEAN_CVAR_05_CONVEX_V1"` with `RISK_AVERSION = 0.0`:
`(1 - a) * E[net] + a * CVaR_5%(net)`, a fixed preference declared in
`portfolio.py` rather than one emerging from `S`. At the default it is the
expectation, which is what `mean - 1.96 * SE` was estimating all along, so the
objective's target is unchanged and only the scenario-count dependence is
gone. `_nondominated`, the worst-state aggregation and `_choose_nash` all rank
on it. `robust_net_payout_lcb` is still computed and still reported, as an
uncertainty statement rather than a ranking axis.

Monte Carlo uncertainty is reported separately as
`objective_standard_error` against `effective_scenario_count`. Effective
sample size is **declared by the caller**, never inferred from outcomes: an
earlier draft derived multiplicity from identical outcome rows, and on a bank
whose scenarios collide that understates precision, which through
`qa.referee_blocks` (it blocks only when `abs(delta) > uncertainty`) *widens*
the REFEREE tolerance instead of tightening it. With nothing declared the
divisor is the row count, which is exactly what production has:
`economics.evaluate_candidates_against_field` refuses a non-uniform scenario
bank. Verified bit-identical to the previous formula:

```text
all-distinct bank, 4000 scenarios
  classical sd(ddof=1)/sqrt(S) = 0.066792527375
  reported objective SE        = 0.066792527375   equal=True
declared multiplicity
  100 rows, one draw each      ESS 100.0  objective 2.000000  SE 0.402015
  same rows x100, 100 each     ESS 100.0  objective 2.000000  SE 0.402015
  4000 rows, 40 each           ESS 100.0
```

The paired comparison is preserved where uncertainty genuinely is the
question: `qa.decide_repair` still takes a per-scenario difference and keeps
the pairing, and now accepts a declared effective sample size, refusing as
"paired sample is too small" at or below one effective observation rather than
computing a zero-width interval. `_referee_uncertainty` is the unpaired case
by construction, two banks with separate seeds and no scenario in common.

#### Verification

Runtime, on the pinned 3.13.7:

```text
export NFL_DFS_VENV_DIR=/tmp/nfl-cowork-venv
export NFL_DFS_UV_CACHE_DIR=/tmp/nfl-uv-cache
export NFL_DFS_UV_PYTHON_DIR=/tmp/nfl-uv-python
sh ./nfl.sh setup                                                  SETUP_COMPLETE
sh ./nfl.sh test -q -p no:cacheprovider --ignore=.pytest_cache tests
```

```text
1. baseline on f318882, device shell, 3.13.7
   279 collected, 277 passed, 1 failed, 1 skipped
   The failure is pre-existing and clock-driven, not a regression: see the
   constraint below.

2. the 14 W2 probes on f318882                       14 failed
   the same 14 probes after the repair               14 passed

3. full suite after the repair
   device shell, 3.13.7, after round one   288 collected, 287 passed, 1 skipped
   cloud container, 3.13.7, final          293 collected, 292 passed, 1 skipped
   The one skip is the Windows junction test. No test was deleted or disabled.

4. cowork-run --input-dir <the two frozen NE@SEA CSVs>
     --profile prior_review --prior-package-dir <the frozen package>   exit 0
   stage PRIOR_ONLY_REVIEW_EXPORT, FILE_VALID true, problems [],
   EVIDENCE_STATE UNKNOWN, MODEL_STATUS PRIOR_ONLY, DO_NOT_UPLOAD.
   Export SHA-256 87156b8c108bfe1585c4dc1c689258ee3fd24f525543ae19667be2017cee359e,
   byte-identical to the pre-W2 run recorded on 2026-09-08.
   Diff against the source template: 145 lines in, 145 out, exactly lines 2
   and 3 changed, the two reserved Entry IDs 5232816721 and 5238395397.
   Run four times across the session, identical every time.

5. the package that run produced, ledger schema nfl_source_ledger_v2,
   scopes IDENTITY_MAP PLAYER_PRIOR SLATE_GEOMETRY TEAM_PRIOR,
   binding expiry 2026-09-09T04:37:46.639672+00:00
   basis TEAM_PRIOR:team_source:MARKET_LINE_MOVES_INTRADAY
   verify_projection_package one minute before that expiry   verified
   verify_projection_package one minute after                refused,
     PACKAGE_LEDGER_INVALID:source ledger entry is stale
   source_ledger_evidence before/after/tampered              PASS/STALE/CONFLICTED

6. doctor pass_status true; compileall clean; no trailing whitespace or tabs
   in any changed file.
```

Four existing tests changed, each because it pinned the pre-repair contract.
Nothing was relaxed:

- `test_projection_producer.py` asserted the package directory held exactly
  three files, and validated the ledger at the game's lock time, which is past
  the fixture's source expiry. It now asserts the `sources/` archive and its
  four entries, validates at the production clock, and asserts that the
  lock-time clock is refused as stale.
- `test_priors_adapter.py` asserted `schema_version == nfl_source_ledger_v1`.
- `test_prior_review_profile.py` `_StubProjection` mirrors the new
  `ProjectionPackage` surface, and its expiry follows the caller's clock.
- `test_build_pipeline.py` supplied a `v1` ledger and asserted no
  `SOURCE_LEDGER_` blocker. The fixture is now `v2`; the assertion is unchanged.

#### An independent adversarial review ran against the first round

It found six real defects, all repaired before this entry: the `v1` downgrade
that bypassed the freshness gate while two new functions had no caller; a
deleted ledger entry evading both the expiry and the tamper check; the
inferred-multiplicity standard error widening the REFEREE tolerance; a
zero-width paired interval accepting a repair at one effective observation; a
non-PASS label suppressing staleness and widening the reported window; and
`..\..\x` and `\Windows\x` escaping the v2 package-relative path check.
Each has a regression test.

#### What this does not do

R07's repair removes the scenario-count dependence and nothing else. The
objective still maximizes a central estimate, which in a large-field GPP is
chalk, and the field, payout and duplication economics under it are still the
known-defective ones. R05, R06 and S7 own that. `RISK_AVERSION` is a real
economic preference and it is set to zero deliberately: weighting a tail
computed by the current field model would be weighting a tail that R05 has not
validated.

### 2026-09-08 — One gated `cowork-run --profile prior_review` command

Closes `W4` / R02. Files added: `src/nfl_dfs/prior_review.py`,
`tests/test_prior_review_profile.py`. Files modified: `src/nfl_dfs/cowork.py`
(third profile, prior-chain request fields, per-profile blocker gating),
`src/nfl_dfs/cli.py` (the `prior_review` branch and its flags), `backlog.md`.
`projection.py`, `contracts.py`, `evidence.py`, `priors.py`, `selection.py`,
`participation.py`, `prior_score.py` and `review_export.py` untouched. Nothing
staged or committed.

#### Commands run and what they returned

Runtime, from a local-disk working copy at `/tmp/w4` (see the runtime note
below), with `NFL_DFS_VENV_DIR=/tmp/nfl-cowork-venv`,
`NFL_DFS_UV_CACHE_DIR=/tmp/nfl-uv-cache`,
`NFL_DFS_UV_PYTHON_DIR=/tmp/nfl-uv-python` and `PYTHONPATH=/tmp/w4/src`:

```text
sh ./nfl.sh test -p no:cacheprovider --ignore=.pytest_cache tests
  before any change : 244 collected, 243 passed, 0 failed, 1 skipped, exit 0
  after  every change: 279 collected, 278 passed, 0 failed, 1 skipped, exit 0
python -m compileall -q src                                        exit 0
```

The 35 new tests are all in `tests/test_prior_review_profile.py`. No existing
test was edited, which is the evidence that `diagnostic` and `registered` are
unchanged.

Regression baseline and acceptance, all against the frozen operator downloads in
`data/runs/20260909-showdown-ne-sea/inputs/`
(salary `6bc5209f6e2f9e3e44e36efe608fe28dfe3b52248c11e6325001dea73e6e4a73`,
entries `797bb9342f0516c373195e236720a783fef9b11e7469c8a46e747a8bea45d02d`):

```text
1. cowork-run --input-dir <inputs> --label baseline                  exit 2
   stage RECONCILED, FILE_VALID false, UNVALIDATED, DO_NOT_UPLOAD, 6 blockers.
   Re-run after every change: byte-identical blocker list.

2. cowork-run --input-dir <inputs> --profile prior_review            exit 0
   stage PRIOR_ONLY_REVIEW_EXPORT, FILE_VALID true, problems [],
   EVIDENCE_STATE UNKNOWN, MODEL_STATUS PRIOR_ONLY, DO_NOT_UPLOAD.
   Export SHA-256 87156b8c108bfe1585c4dc1c689258ee3fd24f525543ae19667be2017cee359e.
   Diff against the source template: 145 lines in, 145 out, exactly lines 2 and
   3 changed, which are the two reserved Entry IDs 5232816721 and 5238395397.

3. cowork-run --profile prior_review --build-priors
     --as-of 2026-09-09T06:00:00Z                                    exit 2
   The frozen package expired at 2026-09-09T04:37:46Z, so the run rebuilt rather
   than reused, fetched and froze all seven nflverse artifacts, auto-accepted 8
   identities and 0 blocked, then stopped on
   WEATHER_CAPTURE_REQUIRED:roof=outdoors. No export written.

4. the same command plus --weather-state CLEAR
     --weather-source-uri https://api.weather.gov/gridpoints/SEW/125,67/forecast
     --weather-observed-at 2026-09-08T16:37:07+00:00                 exit 0
   Full rebuild from a fresh fetch: 2 teams, 68 people, weather_basis
   OPERATOR_SUPPLIED:roof=outdoors|OPERATOR_CAPTURE:...  New package expires
   2026-09-09T09:16:27Z. Export SHA-256 identical to run 2, from independently
   re-fetched sources.

5. one byte changed in a copy of team_prior.json                     exit 2
   PRIOR_ARTIFACT_HASH_MISMATCH:team_prior.json:expected=0d1139c6...:actual=f590cd36...
   Review workbook written, zero CSVs written under the output root.
```

Run 4 reused the `api.weather.gov` capture already recorded in this repository's
frozen `team_prior.json` for this game. It is a test of the rebuild machinery,
not a new weather observation.

#### What the profile does

`cowork-run --profile prior_review` drives `priors-propose`, the identity gate,
`priors-freeze`, `project`, `select` and `review-export` itself. Each stage keeps
its artifacts and hashes under `data/runs/<run_id>/prior_review/`, and a stage
failure returns that stage's own named error with no partial export.

It stops at three gates, and only three, because only these three need a human:

1. **Identity.** `projection.py` accepts only `match_method="EXACT"`, so a
   package cannot be frozen on a guess. The one automatic acceptance is a unique
   league-wide normalized name and position match for a person DraftKings flags
   `OUT` or `IR`, because the availability contract makes those people
   unselectable and an accepted-but-uncertain identity then cannot reach a
   lineup. On the real pool that is exactly the 8 rows the operator accepted by
   hand on 2026-09-08, and 0 others. Anything unresolved and still selectable
   stops the run and reports the candidate provider ID, the conflicting nflverse
   team, the roster status and the first four candidates. Every auto-accept and
   its reason is written to `identity_decisions.json` beside the
   `identity_reviewed.csv` that `priors-freeze` consumes.
2. **Weather.** The enum has no `UNKNOWN` member and `api.weather.gov` is
   unreachable from a session. `roof=dome` and `roof=closed` resolve from the
   schedule artifact alone; every other value, `outdoors` and blank and `open`
   included, blocks for the capture URI and its `generatedAt`. Nothing defaults.
3. **Staleness.** The team prior inherits `MARKET_LINE_MOVES_INTRADAY` from
   `games.csv` and expires twelve hours after capture, so a same-day re-run is
   the normal case. An expired package blocks without `build_priors` and is
   rebuilt with it. No path widens an expiry.

`--exclude`, `--unavailable-status` and `--available-status` are wired through so
an operator fade or a DraftKings status code the vocabulary has not seen does not
force a fall back to the six-call sequence.

#### Which blockers gate, and which are only reported

`required_next_inputs` raises five blocker families. Four of them exist for
certification: payout table, advertised prize value, field size, ticket face
value, and official activity evidence, plus the two that this profile produces
itself, model inputs and the source ledger. `_cowork_core_blockers` already
filtered `OFFICIAL_STATUS_REQUIRED` out of the gating set while leaving it in the
reported list; that pattern is now a per-profile filter in
`cowork.gating_blockers`, and `prior_review` gates on none of them. All seven
still appear in the report's `blockers` list and in the review workbook, because
a reader has to be able to see what this file has not been checked against.

#### Why it cannot be talked into certifying

`MODEL_STATUS` and `RELEASE_DECISION` are not parameters of this path.
`_run_prior_review_profile` pins `ModelStatus.PRIOR_ONLY`,
`ReleaseEvidenceState.UNKNOWN` and `CertificationBasis.MODEL_ASSISTED`, and
`derive_release_policy` adds `MODEL_NOT_PROSPECTIVELY_VALIDATED` for every
`MODEL_ASSISTED` package that is not `PROSPECTIVELY_VALIDATED`, so
`CERTIFIED_UPLOAD_PACKAGE` is unreachable regardless of `file_valid` or evidence
state. The function re-asserts that before writing anything and raises if it ever
derived something else. A supplied `assignment_csv` is refused by name rather
than routed into the manual-guardrail path.

#### Runtime note for the next session

The device VM's `$HOME` (`/sessions`) was 100% full, with 794MB free on `/`. The
working copy went to `/tmp/w4`. `sh ./nfl.sh setup` could not run: the
`/tmp/nfl-cowork-venv` left by an earlier session is owned by a different uid and
is not writable, and a second 603MB venv would not have fit. Its installed
versions match `pyproject.toml` pin for pin, and its editable `.pth` points at a
dead prior-session path, so the suite ran against it with `PYTHONPATH` set to the
working copy. `backlog.md` records this. nflverse retrieval from the device shell
worked, including the GitHub release-asset redirect.

#### Open `[BEN: ...]` flags

- `[BEN: nflverse roof=open]` `priors._ROOF_WEATHER` maps `open` to the
  schedule-derived state `ROOF_OPEN`, and `resolve_weather_state` rejects a
  conflicting operator value. `prior_review` still demands the weather capture
  for that roof, but it cannot attach the capture to the artifact metadata
  without tripping `WEATHER_STATE_CONFLICT`, so the capture is recorded only in
  the run report. Closing the gap means editing `_ROOF_WEATHER`, which is `W1`
  territory. Say whether to open it.
- `[BEN: chat-attachment runs]` The sibling `priors/` folder is auto-discovered
  only when it sits inside an already allowed root, which is true for
  `data/runs/<slate>/` and false for a Cowork attachment directory. A run started
  from two files attached in chat therefore needs `--build-priors` plus the
  weather capture, which is roughly ninety seconds and one paste. Confirm that is
  the flow you want, or say where a per-slate package should be cached.
- `[BEN: lineup count]` `--lineup-count` defaults to the number of reserved Entry
  IDs and `assignments_for_entries` cycles when there are fewer lineups than
  entries. Two entries gave two distinct lineups here. Say what you want above
  about twenty entries, where `--max-person-overlap 4` will stop separating them.

### 2026-09-08 — Prior-only Showdown selection and a byte-audited review export

Closes R03 on the selection side and R02's selection half. Files added:
`src/nfl_dfs/participation.py`, `src/nfl_dfs/prior_score.py`,
`src/nfl_dfs/selection.py`, `src/nfl_dfs/review_export.py`,
`tests/test_participation.py`, `tests/test_prior_selection.py`. Files modified:
`src/nfl_dfs/optimizer.py` (one new public method), `src/nfl_dfs/cli.py` (two
subcommands), `nfl.ps1` (two names). `projection.py`, `contracts.py` and
`evidence.py` untouched. Nothing staged or committed.

```text
244 collected, 243 passed, 0 failed, 1 skipped, exit 0
```

Run on the pinned 3.13.7. Note the runtime change below: the device shell died
mid-session and the suite now runs in the cloud container.

#### Availability contract, `participation.py`

`dk.py` has always parsed `status_raw` onto every `SalaryPlayer` and nothing ever
read it. On the real NE@SEA pool that leaves 21 of 68 people `OUT` or `IR` and
fully selectable, including Zach Charbonnet at 44.88% of Seattle's prior carries
and $8,200. The contract classifies from the salary file's own bytes, moves both
Showdown roles of a person together, reports `Q` without excluding it, and
**refuses an unrecognized status rather than assuming it means available**, which
is the failure mode that puts a scratch in a lineup. `--unavailable-status` and
`--available-status` let the operator classify a new DraftKings code explicitly.

Redistribution took three iterations, each forced by a measurement:

1. `opportunity.remove_inactive_and_redistribute` refuses this pool outright.
   Renormalizing over all survivors pushes George Holani past a 0.055
   `role_capacity` built from a 5.5% snap share.
2. Capping at capacity and spilling the remainder gave quarterbacks the carries,
   because their snap share leaves enormous headroom: Sam Darnold measured 0.0854
   to 0.2891 carry share, and a tight end inherited a fifth of the rushing
   touchdowns. Fixed by scoping absorption to the vacating position and removing
   quarterbacks from carry absorption.
3. The cap itself is wrong. **`role_capacity` is a mean prior-season snap share,
   so it describes the role a person held while someone was ahead of him, which
   makes it invalid in the one situation redistribution exists for.** Emanuel
   Wilson's 0.3112 capacity is his share as Charbonnet's backup. Capacity is now
   reported against, never enforced.

Final rule: proportional to prior share, scoped to the vacating position,
uncapped. On the real pool Wilson lands at 66.45% of carries and 70.59% of
rushing touchdowns, Holani at 11.69%, Darnold unchanged, nothing unallocated.

Two data-quality findings are reported rather than enforced. A share above
capacity is usually real football: Charbonnet holds 70.6% of Seattle's rushing
touchdowns on a 48.4% snap share, which is an ordinary goal-line back. A capacity
of exactly zero beside a nonzero share is a snap-artifact join gap, not someone
who never played; Cody White is one, and a false zero is treated as unknown.

#### Prior score, `prior_score.py`

`SCORE_VERSION = prior_points_of_expected_statline_v1`, named for what it is.
Scoring an expected stat line is not the same quantity as an expected score,
because `scoring.score_offense` pays flat yardage bonuses and
`scoring.score_defense` steps between points-allowed tiers. Everyone within 20
yards of a step is reported as threshold-sensitive instead of quietly scored: on
this pool that is Jaxon Smith-Njigba at 103.4 receiving yards and Emanuel Wilson
at 81.9 rushing yards.

Nothing is fitted or hand-typed. Volumes come from the team prior; the three
splits the model-input contract has no field for come from the hash-pinned
prior-season team-week artifact inside the prior package: passing versus rushing
touchdowns, interceptions versus lost fumbles, and the field-goal distance mix.
Kickers score from `field_goals_mean` weighted by the team's own 2025 distance
distribution plus PATs at the team's own conversion rate. Defences score from the
opponent's sacks allowed and giveaways plus the implied total from the market
line. Return touchdowns, safeties and blocked kicks are omitted and declared,
which understates a defence.

Reconciliation verified: attempts plus sacks plus carries equals `plays_mean`,
the touchdown split sums to `touchdowns_mean`, the turnover split sums to
`turnovers_mean`, and the two implied totals sum to `market_total`.

#### Selection, `selection.py`

`PROFILE_VERSION = prior_only_showdown_selection_v1`. Calls the existing MILP
against the prior score over the permitted pool and never imports `field.py`,
`economics.py` or the portfolio objective, which is asserted in the report.

`optimizer.py` gains `add_person_overlap_limit`. `add_no_good` alone forbids only
an exact roster, and in a six-slot pool that left the same six people available
with a rotated captain: the first two-entry solve returned identical personnel.
The new constraint counts people, so both salary rows of a person count once. The
default cap is 4 of 6 plus a distinct captain per entry, which on the real pool
gives 8 distinct people across 2 entries for 5.2 prior points.

#### Review export, `review_export.py`

`certify` requires the payout table, advertised value and field size, and still
ends `DO_NOT_UPLOAD` while the model is unvalidated, so it costs the operator an
afternoon of data entry for no change in outcome. `review-export` separates the
questions: legality and byte fidelity need no economics and run in full (exact
salary-row identity per slot, one captain, person uniqueness, salary cap, both
teams, independent byte audit against the source template, reparse, SHA-256).
Economics are declared not run, and the decision is `DO_NOT_UPLOAD` by
construction rather than by failure.

#### End-to-end rehearsal on the real contest

Two CSVs in, bulk-entry CSV out, 0.48 seconds. Contest 193391013,
`NFL Showdown $2.25M Wednesday Kickoff Millionaire`, $20, 2 reserved entries.

```text
lineup 1  49500/50000  prior 110.246  CPT Jaxon Smith-Njigba
          Jason Myers | Drake Maye | Sam Darnold | Emanuel Wilson | Hunter Henry
lineup 2  49200/50000  prior 105.047  CPT Emanuel Wilson
          Jason Myers | Drake Maye | TreVeyon Henderson | A.J. Brown | Jaxon Smith-Njigba
```

`FILE_VALID: true`, `problems: []`, output SHA-256
`87156b8c108bfe1585c4dc1c689258ee3fd24f525543ae19667be2017cee359e`. Diffed
against the source template: exactly the two reserved entry rows changed, the
trailing instruction column preserved, every other byte identical. No `OUT` or
`IR` person appears in either lineup.

#### Runtime constraint learned

`device_bash` failed with "Failed to create bridge sockets after 5 attempts" and
did not recover, while `get_device_info`, `device_list_dir`, `device_stage_files`
and `device_commit_files` kept working. The documented cloud-container fallback
was used for the rest of the session: stage the sources, build a venv on the
pinned 3.13.7, run the suite there, commit changed files back. One correction to
that fallback: **`uv` is unusable in the container**, managing 268KB of cache in
ten minutes before timing out, while `pip` installed the full pinned dependency
set in 39 seconds. Use `uv` only to fetch the interpreter, which comes from
GitHub and is instant.


#### Windows verification, and the launcher fix that made it possible

The first Windows run of this work errored every test at setup, inside pytest's
own temporary-directory machinery and never inside `nfl_dfs`:

```text
_pytest/pathlib.py:176 find_prefixed -> os.scandir(root)
PermissionError: [WinError 5] Access is denied:
  'C:\Users\benja\AppData\Local\Temp\pytest-of-benja'
```

Two directories had become unreadable to the operator's own Windows account: the
default pytest basetemp root, and the repository's `.pytest_cache`, which is the
same `.pytest_cache` this session had already had to skip with `--ignore` from
the Linux side. Both are consequences of the bridge delete-permission constraint
recorded above, not of any change in this repository. The ERROR set covered
`test_appg`, `test_build_pipeline`, `test_certification`, `test_cowork`,
`test_governed_late_swap`, `test_payouts`, `test_source_ledger` and
`test_workbook_system`, none of which this session touched.

Passing the repair as flags is not possible through the launcher. `nfl.ps1`
declares `[CmdletBinding()]`, so PowerShell adds the common parameters and
prefix-matches them before the script sees its arguments: `-p no:cacheprovider`
binds to `-PipelineVariable` and fails validation. The `test` branch of
`nfl.ps1` now pins both writable roots itself, `%TEMP%\nfl-dfs-pytest` for
`--basetemp` and `%TEMP%\nfl-dfs-pytest-cache` for `cache_dir`, with
`@RemainingArgs` passed last so an explicit operator flag still overrides.
Earlier sessions had been passing a project-local `--basetemp` by hand for the
same reason, visible in the 2026-09-04 entries below; this makes it the default
and keeps the cache plugin enabled.

```text
.\nfl.ps1 test -q
244 collected, 243 passed, 1 skipped, exit 0
```

Windows, pinned 3.13.7. The skip is the pre-existing symlink-privilege case, the
same one in the 171-passed baseline at `f86fd9e`.


### 2026-09-08 — Real NE@SEA Showdown prior package built; weather provenance added

Operator supplied the real contest files. Ran the full W1 pipeline on them and
delivered the package. Files touched: `src/nfl_dfs/priors.py`,
`src/nfl_dfs/cli.py`, `tests/test_priors_adapter.py`, `backlog.md`,
`changelog.md`. `projection.py`, `contracts.py` and `evidence.py` still
untouched. Nothing staged or committed.

Inputs, committed byte-exact to `data/runs/20260909-showdown-ne-sea/inputs/`:

```text
DKSalaries_NE_SEA.csv  6bc5209f6e2f9e3e44e36efe608fe28dfe3b52248c11e6325001dea73e6e4a73  13477 bytes
DKEntries_NE_SEA.csv   797bb9342f0516c373195e236720a783fef9b11e7469c8a46e747a8bea45d02d  15634 bytes
```

Contest 193391013, `NFL Showdown $2.25M Wednesday Kickoff Millionaire`, $20
entry, 2 reserved entries, both blank. 136 salary rows, 68 people.

#### Weather provenance, new

`api.weather.gov` is unreachable from a session but reachable from the operator
browser, and it is already allowlisted as `PUBLIC_DOMAIN`. `priors-freeze` now
accepts `--weather-source-uri` and `--weather-observed-at`, held to the same host
and licence policy as every other source reference through
`validate_source_reference_policy`. An unapproved host is refused even when the
operator types it in, and a URI without an observation time is refused. Without a
URI the basis records `OPERATOR_SUPPLIED_UNATTRIBUTED` rather than silently
implying provenance.

For this game the value is `CLEAR`, from gridpoint `SEW/125,67` generated
`2026-09-08T16:37:07+00:00`: the periods spanning a 17:20 PT kickoff are
`Mostly Sunny` (N 6 mph, precipitation 0%) into `Partly Cloudy` (N 5 mph,
precipitation 3%). Recorded basis:

```text
OPERATOR_SUPPLIED:roof=outdoors|OPERATOR_CAPTURE:https://api.weather.gov/gridpoints/SEW/125,67/forecast:observed_at=2026-09-08T16:37:07+00:00
```

#### Identity: 60 of 68 automatic, 8 accepted on review

57 matched on name/team/position, 1 through the canonical player index, 2 team
defences. The 8 needing a decision were all cases where nflverse's week-1 2026
roster places the person on another team, and **all 8 are DraftKings-flagged
`OUT`**: CJ Dippre, Jack Westover, Mitch Van Vooren, Kayshon Boutte, Kobe
Prentice, Lance Mason, Nick Vannett, Cody White. All accepted, on the reasoning
that each league-wide match is unique, player usage joins on provider person id
rather than current team, and the identity map takes team from DraftKings. The
reviewed decision file is retained at
`data/runs/20260909-showdown-ne-sea/review/identity_reviewed.csv`.

#### Published package

```text
team_prior.json     0d1139c6ae9ed2a2df2f10a07b26c7d2f5b813e4bd584e9c90db4029aac654c9
player_prior.json   04e8b4bb24f4657294a0c2e7984fe1c0c4739a8faadeadad90c445aaa5ec1618
identity_map.json   de395d9ce3d0acee1511587f16089da51ef78b58ea62b56b503cae47a37d714b
prior_package.json  312ee5d1dc9ce5c3d42576961417f8b0ca4596ace8594a7855ad3ae684a0ed13
```

A second freeze from the same frozen artifacts reproduced all three
byte-identically. `project` accepted the package and published
`team_projections.csv` (2 rows), `player_opportunities.csv` (68 rows) and a
reconciled ledger at `MODEL_STATUS=PRIOR_ONLY` / `RELEASE_DECISION=DO_NOT_UPLOAD`.
Derived team rows: NE 61.41 plays, 0.5268 pass rate, 8.882 Y/A, 3.12 TD, market
44.5 / +3; SEA 59.71 plays, 0.5005 pass rate, 8.447 Y/A, 2.59 TD, market 44.5 / -3.

Market cross-check against a book, through the operator browser: Action Network
shows this game opened NE +4.5 / SEA -4.5 and currently sits NE +3 to +3.5 /
SEA -3 to -3.5 across bet365, DraftKings, Fanatics and Caesars. The artifact's
`spread_line` of 3 agrees with the current market. **The total of 44.5 was not
independently verified**; the Action Network total tab did not open under
automation and was not pursued further.

#### R03 quantified on the real pool, and it is disqualifying for a generated lineup

21 of the 68 people are `OUT` or `IR` and 2 are `Q`, leaving 47 selectable. The
participation contract does not exist, so every one of those 21 remains
selectable by the solver and scoreable by the simulator:

```text
Zach Charbonnet  SEA RB OUT  $8200  capacity 0.484  carry share 44.88%
Kayshon Boutte   NE  WR OUT  $5600  capacity 0.675  target share  7.80%
Terrell Jennings NE  RB OUT  $2400  capacity 0.083  carry share   4.82%
Julian Hill      NE  TE IR    $200  capacity 0.550  target share  3.39%
```

Charbonnet carries the second-highest carry share in the Seattle pool at a
mid-range price. A projection-maximizing solver rosters him, and the retained
review probe shows a zero-capacity person still averaging 7.99 points across 984
of 1,000 scenarios. Worse, his 44.88% of carries should redistribute to Emanuel
Wilson (30.49%) and George Holani (5.37%) and does not.
`opportunity.py:308 remove_inactive_and_redistribute` exists but is not wired to
the DraftKings `Status` column or to any evidence contract. That wiring is `W3`.

Operator-facing table joining every person's derived opportunity shares to the
DraftKings status is retained at
`data/runs/20260909-showdown-ne-sea/review/opportunity_review.csv`.

#### Tests

```text
206 collected, 205 passed, 0 failed, 1 skipped, exit 0
```

Two added: the weather source URI held to source policy (approved host accepted,
`actionnetwork.com` refused, missing observation time refused, future observation
refused), and an outdoor freeze recording the capture URI in coverage.


### 2026-09-08 — W1: R01 nflverse prior adapter, and the Linux/Cowork runtime unblocked

Tranche `W1` per `docs/session-prompts/W1-priors-adapter.md`. Files touched:
`src/nfl_dfs/priors.py` (new), `tests/test_priors_adapter.py` (new),
`src/nfl_dfs/cli.py`, `src/nfl_dfs/sources.py`, `src/nfl_dfs/system.py`,
`nfl.sh`, `nfl.ps1`, `docs/DATA_CONTRACTS.md`, `docs/COWORK_RUNBOOK.md`,
`backlog.md`, `changelog.md`. `projection.py`, `contracts.py` and `evidence.py`
were left untouched for `W2`; verified with `git diff --quiet` on each.

Nothing was staged or committed.

#### Step 0: the Linux runtime now works, and the cause was not disk space

`sh ./nfl.sh setup` first failed with
`failed to create directory .../.local/share/uv/python: No space left on device`
(`/sessions` is 9.8G, 9.4G used, 0 available). Relocating the interpreter did not
fix it either: extraction failed with `Operation not permitted` on
`share/terminfo/2/2621a`.

One root cause explains every symptom: **the Cowork device bridge refuses file
deletion inside a mounted folder**, `unlink` and `rmdir` returning `EPERM`.
Confirmed directly. It breaks `uv` extraction (it cleans its own `.temp`),
SQLite in both `WAL` and `DELETE` mode (`disk I/O error`; `journal_mode=MEMORY`
is the only mode that works there), and `tempfile.TemporaryDirectory`, whose
cleanup handler retries `rmtree` on every `PermissionError` and recurses to
`RecursionError`. `ignore_cleanup_errors=True` does not help, because the
recursion happens below it.

Repairs:

- `nfl.sh` honours `NFL_DFS_VENV_DIR`, `NFL_DFS_UV_CACHE_DIR` and
  `NFL_DFS_UV_PYTHON_DIR`. Every default is unchanged and `nfl.ps1` is untouched
  apart from two new subcommand names. With the runtime on local disk `uv sync`
  completes in 17 seconds instead of exceeding 178 seconds unfinished.
- `system.py` `doctor()` owns its probe lifecycle with `mkdtemp` plus
  `shutil.rmtree(ignore_errors=True)`, which never recurses, and reports a
  surviving probe directory in a new `workspace_probe_cleanup` field.
- `system.py` tries the preferred SQLite journal mode, falls back to `DELETE`,
  and records the real failure in a new `sqlite_probe_error` field. Reporting
  what the workspace supports is the purpose of that probe.

**A session can now execute the suite, which unblocks every later tranche.** The
invocation is
`sh ./nfl.sh test -q -p no:cacheprovider --ignore=.pytest_cache tests`; the
ignore is required because `.pytest_cache` in the mounted repository is
unreadable.

Still open: `nfl.sh doctor` against the mounted repository reports
`pass_status: false` with `sqlite_probe_error: DELETE:OperationalError:disk I/O
error`. That is correct, not a defect. `cowork-run` gates on `pass_status` and
`registry.py:30` opens a real database under `data/registry/`, so the engine
cannot run in place in a mounted folder. Either the session is granted delete
permission on the folder (requested this session and auto-denied by the
permission classifier before reaching the operator), or runs execute from a
local-disk working copy with the mounted repository as the source of truth for
edits. Running the suite in place also leaves undeletable temporary directories
behind.

#### Step 2: reachability, measured from the device VM and the cloud container

| Host | Result |
|---|---|
| `raw.githubusercontent.com` | 200 |
| `api.github.com` | 200 |
| `github.com/.../releases/download/...` | 302 to `release-assets.githubusercontent.com`, which then serves 200 |
| `api.weather.gov` | no connect |
| `api.sleeper.app` | no connect |
| `api.the-odds-api.com` | no connect |
| `actionnetwork.com` | no connect |

The 2026-09-08 constraint that release assets are unreachable was wrong: they
are reachable, and the block was policy. `release-assets.githubusercontent.com`
is not in `ALLOWED_HOSTS` and `fetch_public_artifact` set
`follow_redirects=False`. The api.github.com octet-stream asset endpoint
redirects to the same host, so there was no allowlisted route to the bytes.
Confirmed code-only, no player data: `nflverse-data` (28 blobs),
`nflverse-pbp` (123), `nflverse-players` (59), `nflverse-rosters` (46),
`nflverse-data-archives` (1). Only `nflverse/nfldata` publishes data in a repo
tree.

`sources.py` now follows exactly one redirect hop, only from a
`github.com/{owner}/{repo}/releases/download/...` URL, and only onto
`release-assets.githubusercontent.com` or `objects.githubusercontent.com`. Every
other host keeps `follow_redirects=False`. The recorded `source_uri` stays the
canonical `github.com` URL, already approved under
`PERMITTED_REPOSITORY_LICENSE`. A related latent defect is fixed in the same
place: an unfollowed redirect previously passed `raise_for_status` and produced
an empty artifact that would have been hashed as data.

**This widens a security boundary and needs explicit operator sign-off before
any certified run depends on it.**

#### Step 3: the adapter

`src/nfl_dfs/priors.py`, `ADAPTER_VERSION = nflverse_prior_adapter_v1`, reachable
as `priors-propose` and `priors-freeze` from both launchers. It reads seven
approved artifacts, archives their raw bytes content-addressed under
`<package>/raw/`, and records hashes, source URIs, captured and observed times,
per-source expiry with its staleness basis, license decision and parser version
in `source_manifest.json`. The package resolves without any file outside it.
Contracts and transformations are documented in `docs/DATA_CONTRACTS.md`.

Design decisions taken and their reasons:

- **Two phases, because DraftKings and nflverse share no key.**
  `projection.py:374` accepts only `match_method="EXACT"`, and the backlog holds
  that a normalized crosswalk match is a proposal until reviewed and frozen.
  `priors-propose` emits only normalized match methods; `priors-freeze` requires
  the reviewed file's SHA-256, `DECISION=ACCEPT` on every row, an unaltered row
  and a unique provider id, and only then writes `EXACT`.
- **Team identity from the DST nickname.** DraftKings names its DST row after the
  team nickname and `nfldata/teams.csv` publishes that nickname per season, so
  `LAR` resolves to nflverse `LA` from data rather than a hand-written mapping.
  Cross-checked against a unique schedule row matched on season, the crosswalked
  team pair and the DraftKings kickoff date.
- **Expiry composes.** An emitted artifact expires at the earliest expiry among
  its contributing sources, capped at the game's lock time.
- **Zero prior support fails closed.** `PRIOR_SUPPORT_MISSING` names the team and
  the weight group. Uniform filling and imputation are never applied.
- **Player usage joins on person, not team**, because players move; filtering by
  current team would silently zero someone productive elsewhere.
- **`uncertainty` is the coefficient of variation of weekly offensive plays.** A
  dispersion indicator over the same frozen bytes, explicitly not a calibrated
  variance or a confidence interval.
- **A custom canonical serializer.** `json.dumps(default=str)` quotes every
  `Decimal` and `TeamSourceRecord` rejects a quoted number. Floats are refused
  outright so no unstable repr reaches a derived artifact.
- **Weather.** `roof` of `dome`, `closed` or `open` derives the enum from the
  frozen artifact. Anything else requires `--weather-state`, because the enum has
  no `UNKNOWN` member and `api.weather.gov` is unreachable from a session.

#### Verified against the real NE@SEA Showdown pool

`tests/fixtures/supplied/DKSalaries Salary CSV Showdown.csv`, SHA-256
`86a837c50eb36130a4e2bf2642a9457f08c6487dde8a4c2bccd793c91a7f6309`, 126 rows and
63 people, against live nflverse artifacts.

`priors-propose` resolved 55 of 63 people automatically: 52 on
name/team/position, 1 through the canonical player index, 2 team defences. The
remaining 8 are people the DraftKings pool places on NE or SEA while the nflverse
week-1 2026 roster places them on another team (TB, WAS, DAL, HOU, NYG, PIT, BAL,
LV), 6 of them at `DEV` or `CUT` status. Each is reported as
`NAME_POSITION_OTHER_TEAM` with its candidate provider id, the conflicting team
and the roster status, so the review file is actionable rather than blank. They
are not bound automatically; that is the gate working.

A rehearsal `priors-freeze` in a scratch directory, accepting those 8 to exercise
the path, then confirmed on real bytes:

- Two freezes from the same frozen artifacts produced byte-identical JSON:
  `team_prior.json d3cd26b5…`, `player_prior.json 1d960973…`,
  `identity_map.json 25965a4b…`.
- 63 people, one mapping and one record each, all keyed to FLEX ids, no captain
  id mapped, both roles reconciled in `coverage`. Kickers and both defences
  included.
- `project` accepted all three artifacts and published
  `team_projections.csv` (2 rows), `player_opportunities.csv` (63 rows) and a
  reconciled `nfl_source_ledger_v1`, reporting `MODEL_STATUS=PRIOR_ONLY` and
  `RELEASE_DECISION=DO_NOT_UPLOAD`.
- The outdoor game refused to freeze without a weather state, with
  `WEATHER_STATE_REQUIRED:roof=outdoors`.
- Derived team values spot-checked against the raw artifact: NE 4459 passing
  yards on 502 attempts is 8.882 Y/A, matching the emitted value exactly; plays
  61.41, pass rate 0.5268, rush 4.435 all reconcile. Both teams sit at the high
  end of historical Y/A, which is a property of the 2025 dataset rather than the
  transformation, and is worth an operator sanity check.
- Market fields came from `games.csv`: total 44.5, `spread_line` 3 emitted as NE
  `+3` and SEA `-3`. `coverage.market_attribution` is
  `NFLVERSE_SCHEDULE_NO_BOOK_NO_PUBLISHER_TIMESTAMP`, because that artifact
  carries neither.

#### Tests

`sh ./nfl.sh test -q -p no:cacheprovider --ignore=.pytest_cache tests`, run by
the session on the pinned Python 3.13.7 runtime, on both a local-disk working
copy and the mounted repository:

```text
204 collected, 203 passed, 0 failed, 1 skipped, exit 0
```

The single skip is the pre-existing `test_cowork.py:115` Windows junction case.
The Windows baseline at `f86fd9e` was 171 passed with the same skip;
`tests/test_priors_adapter.py` adds 32. `git diff --check` and `compileall` pass.

New coverage: byte-identical reproducibility; `AvgPointsPerGame` mutation leaving
both derived artifacts unchanged; one record and one mapping per person with K
and DST present and both Showdown roles reconciled; shares normalized over the
pool and provably non-uniform; postseason and other seasons excluded; salary,
review-file and frozen-artifact hash mismatches; insufficient team coverage;
unaccepted, altered and duplicated review rows; output-directory reuse; refusal
to uniform-fill an unsupported group; `project` consuming the package; stale
sources refused by `project`; zero-capacity people reported; per-team spread
sign; weather derivation and refusal; proposals never claiming `EXACT`; a
cross-team person reported with its candidate; ambiguity left unresolved; the
player-index fallback tier; expiry composition and the lock cap; and the
`sources.py` redirect being confined to GitHub release downloads.

#### Reported, not repaired

- **R03 stands.** A `role_capacity` of zero does not remove a person from
  scoring. On the NE@SEA pool the adapter reports 4 such people, both kickers and
  both defences, in `zero_role_capacity_people`. Tranche `W3` owns the
  participation mask. Not papered over here.
- **`projection.py` requires a prior record for every person in the pool**
  (`SALARY_PERSON_IDENTITY_COVERAGE_MISMATCH`). A DraftKings pool routinely
  contains a practice-squad elevation or a just-signed person with no honest
  prior. Today the whole package fails rather than publishing without them. This
  is a real design tension between fail-closed and pool reality, and it needs a
  decision before the Sunday run.

#### Open `[BEN: ...]` flags

- **[BEN: weather_state]** for NE@SEA. Lumen Field is `roof=outdoors`,
  `games.csv` carries no weather, and `api.weather.gov` is unreachable from a
  session though it is allowlisted and reachable from a browser. Required before a
  real freeze.
- **[BEN: current Showdown salary CSV]**. The repository fixture is a 2026-09-01
  download. A real run needs the current file for the exact contest.
- **[BEN: 8 identity decisions]** in `identity_review.csv`, listed above.
- **[BEN: sources.py redirect sign-off]** before a certified run depends on it.
- **[BEN: market source]**. `actionnetwork.com` cannot be an artifact source:
  it is not in `ALLOWED_HOSTS`, and the `OPERATOR_SUPPLIED` escape at
  `sources.py` is hardcoded to DraftKings, so even an operator-supplied number
  fails the gate. `games.csv` is the artifact of record until that changes.


### 2026-09-08 — Production readiness review triage, Showdown-first sequencing, backlog restructure

No production source, test, or configuration file was changed. Documentation and
tracking only.

Added:

- `docs/SHOWDOWN_FIRST_PRODUCTION_PLAN.md`. Splits readiness into a reachable
  prior-only Showdown review product and a certified-upload product that cannot
  exist before settled slates provide prospective validation evidence. Sequences
  R01-R15 for Showdown and records four places the review's own sequencing is off.
- `docs/session-prompts/W1-priors-adapter.md`. Paste-ready session prompt for the
  R01 adapter.
- A `Post-review work tranches` section in `backlog.md` mapping every open finding
  R01-R15 onto session-sized tranches W1-W13, with dependencies, plus a dated
  deadline reality check.

Verified in this session against `codex/s6a-deterministic-projection-producer` at
`f86fd9e`:

- R05 cloning is a default, not an architecture. `cli.py:1314` takes
  `min(opponent_count, args.field_sample_size)` and `--field-sample-size` defaults
  to 1000 (`cli.py:2396`, hardcoded at `cli.py:2031` and `cli.py:2275`), then
  `scale_field_multiplicities` inflates to field size. `economics.py:115` already
  streams one scenario at a time against a chunked field and never materializes a
  field-by-scenario matrix, so the constraint is CPU time, not memory.
- R07 confirmed at `portfolio.py:128` (`mean - 1.96 * standard_error`) and
  `portfolio.py:189` (worst state chosen by the same quantity).
- R03 confirmed at `simulation.py:84`: `salary_people != model_people` raises, so an
  unavailable person cannot be removed from the model.
- R06 confirmed at `cli.py:1302` and `cli.py:2398`: a 20,000-lineup bank is cut to
  250 by mean projection then summed p90, against a 5,000 ceiling at `cli.py:1308`.
- R12 confirmed: `cli.py` sets `ModelStatus.PRIOR_ONLY` on successful model load and
  no registry or loader exists.
- Session egress reaches `raw.githubusercontent.com` and `github.com` only.
  `api.sleeper.app`, `api.weather.gov`, and `api.the-odds-api.com` fail to connect
  from both the device-side Linux VM and the cloud container.
- The device-side Linux VM has `uv` and Python 3.10.12, no `.cowork-venv`, and a
  `/sessions` mount at 100% capacity. The Linux runtime remains unbootstrapped and a
  session cannot currently execute the suite or invoke the Windows launcher.

Tests: none run. The 171-passed/1-skipped baseline is carried from the review, not
re-executed here.

Blockers unchanged: R01-R15 all open. Operator prerequisites for DL4 and DL5 (a
matching Showdown reserved-entry template, contest facts, approved prior artifacts,
current official activity evidence) are still missing, so DL4 and DL5 are retargeted
from the 2026-09-09 opener to a Sunday 2026-09-13 single-game contest, with the
opener run as a manual-guardrail rehearsal only.

### 2026-09-04 — DL2/S6A: deterministic prior projection producer

Changed:

- Added a local `project` command to both launchers. It requires the untouched
  salary CSV, versioned team-prior and player-prior JSON, an exact frozen
  provider-to-DraftKings identity map, the independently recorded SHA-256 of
  all four artifacts, an explicit timezone-aware `as_of`, and a new output
  directory.
- Added strict S6A contracts and deterministic transformation code. Approved
  source/license/parser combinations, capture/observation/expiry times,
  evidence states, declared and computed coverage, finite bounds, unique stable
  provider identities, complete team/person coverage, and exact team/position/
  underlying-person/DK-ID mappings all fail closed. Normalized/fuzzy mappings
  never assemble. Showdown emits one FLEX ID per underlying person and rejects
  CPT/FLEX identity conflicts.
- Team fields are direct bounded frozen source fields. Player share outputs are
  position-masked source weights divided by their eligible team totals; an
  all-zero or missing group is rejected rather than filled uniformly. No
  coefficient fitting, clipping, imputation, or LLM-authored number exists in
  the runtime path, and DraftKings APPG is never read numerically.
- Outputs are built in a temporary sibling directory, checked through
  `load_opportunity_model`, hashed, bound into a four-entry
  `nfl_source_ledger_v1`, validated through `validate_source_ledger`, and only
  then atomically published as `team_projections.csv`,
  `player_opportunities.csv`, and `source_ledger.json`. Existing destinations
  and any failed build publish no package.
- Extended ledger entries with deterministic coverage records and separated
  non-fetching operator-supplied DraftKings provenance references from the
  still-prohibited DraftKings retrieval path.
- Updated Cowork/operator/data-contract/status documentation and the missing-
  input handoff to use the new producer while preserving
  `MODEL_STATUS=PRIOR_ONLY` and `RELEASE_DECISION=DO_NOT_UPLOAD`.

Verification:

- Focused producer, source-ledger, and APPG suite: 39 passed in 2.37 seconds.
- Producer plus existing build, Cowork, certification, governed late-swap,
  late-swap learning, and release-truth suite: 112 passed, 1 skipped in 27.08
  seconds. The skip is the existing Windows symbolic-link privilege case.
- Complete Windows suite with a unique project-local `--basetemp` and pytest
  cache disabled: 171 passed, 1 skipped in 31.33 seconds.
- Independent Classic fixture inspection: exact headers, 24 team rows, 719
  person rows, four ledger entries, loader success, ledger-validator success,
  and exact reconciliation of team SHA-256
  `f9370dbb20ce78a40ffe159f4d78a7abf76e9248858ffb08f4ef8ac6931ff279`
  and player SHA-256
  `603237a30367c9f8f9cba577e6fdda2414fd13e78e4cb635fe931ddcc2081f6c`.
- A separate same-input/two-directory run produced byte-identical team, player,
  and ledger files. Mutating every salary APPG cell left both derived CSV hashes
  unchanged.
- `nfl.ps1 doctor`: pass on Python 3.13.7; SQLite integrity `ok`, WAL mode,
  Excel lock `CLOSED_OR_ABSENT`, and no sync/reparse detection.
- Python `compileall` over `src` and `tests`: pass.
- `git diff --check`: pass.

Remaining blockers:

- The broader S6 historical ingestion, offline fitting/holdout validation,
  live-source refresh, Linux/Cowork execution, real-slate timing, and
  prospective model calibration remain unverified.
- Matching Showdown/Classic reserved-entry templates, contest facts, and
  current official evidence are still required on the September 9/13 delivery
  sequence.

Tracker updates:

- DL2/S6A: `READY` -> `DONE`.
- DL3: `BLOCKED` on DL2 -> `READY`; it is the sole next action.
- Broader S6 remains `BLOCKED`; no later quantitative tranche was started.

Claims explicitly not made:

- No live-slate, Linux/Cowork, calibrated-EV, ROI, profitability, ownership,
  win/cash probability, prospectively validated model, or DraftKings upload-
  readiness claim.

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
