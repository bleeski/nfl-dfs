Work in:

`C:\Users\benja\Documents\Claude\nfl-dfs`

Your task is to complete the next authoritative backlog chunk: **C1 — Classic
intake, projection, and one-command prior review**. Do not stop at a plan:
inspect the current implementation, make the bounded changes, test them
thoroughly, update the project trackers, and provide a complete handoff. Do not
begin C2 policy/candidate/portfolio implementation during this session.

## Start safely

1. Read `CLAUDE.md`, the authoritative reprioritized section of `backlog.md`,
   `changelog.md`, `IMPLEMENTATION_STATUS.md`, `docs/DATA_CONTRACTS.md`, and the
   Q1 settlement/metric documentation.
2. Inspect Git state before modifying anything. Q1 was developed on
   `codex/q1-settlement-reference-economics` from merged-main commit
   `7f083fbd77620d96e3f0571f09d93fdaeb32e377`, but it was intentionally not
   committed, pushed, or merged in that session. Record the actual reviewed
   Q1 commit on current `main`; do not assume the development-branch base is
   the final Q1 commit.
3. Switch to `main` and run `git pull --ff-only` only when doing so cannot
   overwrite tracked work. Confirm the Q1 bundle, referee, replay, metric
   registry, and final verification are present. If Q1 is not merged or there
   are unexpected tracked changes, stop and report the exact state.
4. Preserve every existing untracked/generated/user-owned file, especially
   `Claude outputs/`,
   `docs/session-prompts/W2-expiry-and-selection-objective.md`, and
   `docs/session-prompts/W4-cowork-prior-only-profile.md`.
5. Never reset, clean, stash, overwrite, broadly format, or use `git add .` or
   `git add -A`. Do not commit, push, open a PR, or merge without separate
   authorization.
6. Once synchronized, create `codex/c1-classic-intake-prior-review`.

## Tracker transition

At the start, confirm Q1 is `DONE`, make C1 the sole `IN_PROGRESS` item, and
leave C2 and everything after it `BLOCKED`. Do not mark C1 done or unlock C2
unless every acceptance criterion below passes.

## Objective

Extend the safe Showdown `prior_review` operating pattern to multi-game
DraftKings NFL Classic. The normal Cowork surface remains one salary CSV plus
one reserved-entry CSV. It must produce deterministic legal exact-ID review
assignments without calling the known-unvalidated field, duplication, or payout
economics path.

The result remains:

- `MODEL_STATUS=PRIOR_ONLY`
- `RELEASE_DECISION=DO_NOT_UPLOAD`

It is a useful review workflow, not calibrated EV, ROI, ownership, win/cash
probability, or upload readiness.

## Required implementation

### 1. Immutable multi-game Classic intake

- Detect Classic from exact salary and reserved-entry schema.
- Validate DraftKings roster geometry, $50,000 salary cap, at least two games,
  teams/opponents, per-player locks, exact DK IDs, underlying-person uniqueness,
  Entry IDs, blank-cell authority, and one-contest compatibility.
- Bind the salary and entry bytes/hashes, draft group, complete game set, mode,
  parser/scoring versions, and contest facts needed by the prior-review path.
- Fail before assignments on wrong mode, mixed or mismatched draft groups,
  mismatched entries, unknown games, duplicate/ambiguous identities, mutation,
  or stale/unbound source evidence.
- Preserve DraftKings `AvgPointsPerGame` only in untouched raw bytes; it may not
  become a numerical input.

### 2. One immutable multi-game prior/projection package

- Reuse the frozen-source S6A and current prior adapters rather than creating a
  disconnected Classic engine.
- Consume only approved captured sources with exact hashes, timestamps,
  coverage, expiry, parser/transformation versions, license decisions, and an
  exact provider-to-current-DK identity map.
- Produce deterministic team/player inputs across every game with conservation
  and complete team/position/person coverage reporting.
- Do not impute, fuzzy-match, use APPG, invent shares, or type numerical priors
  from prose. Missing or invalid material inputs stay explicit and fail closed.

### 3. Participation and evidence across the full slate

- Apply salary status, current official exact-ID activity evidence, transfers,
  rookies/missing history, current role evidence, weather where material, and
  source-expiry rules across every game rather than only a Showdown pair.
- Distinguish observed zero, missing history, unknown current role, explicit
  nonparticipation, and source-supported adjustment.
- A selected unavailable player or selected player missing required current
  evidence must block assignments/export. Nonselected uncertainty remains
  visible in coverage and model limitations.
- Produce a concise complete-slate coverage view with named people, teams,
  positions, games, salaries, exclusion reasons, unallocated volume, and the
  smallest evidence action.

### 4. One-command Classic prior review

- Extend `cowork-run --profile prior_review --build-priors` to Classic while
  preserving the existing Showdown behavior.
- Generate deterministic legal prior-only Classic assignments for every exact
  reserved Entry ID without calling field generation, ownership, duplication,
  payout evaluation, `evaluate_candidates_against_field`, or the portfolio EV/
  utility selector.
- Persist versioned machine-readable selection/coverage artifacts and all four
  release truths. A review artifact must remain clearly named as review-only;
  no `DK_UPLOAD_*.csv` may be emitted.
- Rerunning from the same immutable inputs under a new run ID must reproduce the
  same assignment and relevant report hashes.

## Reuse and Q1 boundaries

- Preserve the Q1 `nfl_settlement_request_v1`,
  `nfl_settlement_bundle_v1`, `nfl_reference_settlement_v1`, versioned scenario
  store, canonical brief, and `nfl_metric_promotion_registry_v1` contracts.
- C1 may emit the pre-lock hashes/versions that later settlement needs, but it
  must not settle a contest, view challenger/holdout results, tune registered
  thresholds, or promote a model.
- Do not replace production economics, implement calibrated player/ownership/
  field/duplication models, build the C2 Classic policy/candidate/joint-
  selection layer, add Classic review export redesign from C3, or implement
  Classic late swap.
- DraftKings login, contest entry, editing, upload, credentials, cookies, and
  money movement remain manual.

## Required tests

Add focused golden coverage for at least:

- multi-game Classic schema/mode detection and legal roster geometry;
- exact ID, Entry-ID, contest, draft-group, game, team/opponent, and lock
  reconciliation;
- APPG quarantine and deterministic source-bound projection replay;
- full-slate team/position/person coverage, conservation, and source expiry;
- current exact-ID inactive/unavailable exclusion before selection;
- transfer, rookie/missing-history, role, and weather states across multiple
  games;
- wrong mode, mixed draft group, unknown game, duplicate identity, stale
  evidence, source mutation, and selected-unavailable hard stops;
- 1-entry and multiple-entry deterministic Classic assignments;
- a one-command Cowork Classic run that produces review-only artifacts and no
  upload-shaped CSV;
- regression protection for the complete existing Showdown `prior_review`
  path; and
- independent confirmation that the C1 path never invokes field, ownership,
  duplication, payout, or production-economics functions.

## Verification

Run:

1. Focused Classic intake, prior, projection, participation, selection, Cowork,
   contract, and regression tests.
2. The complete pinned test suite using a new short unique workspace-local
   `--basetemp` and separate cache directory. Long paths are disabled on this
   Windows host; keep the unique names short and do not treat the known fixed-
   temp/long-path issue as a code failure.
3. `.\nfl.ps1 doctor`.
4. Compile/import checks for changed modules.
5. `git diff --check`.
6. Deterministic repeat and source/artifact mutation tests.
7. An adversarial review of the complete diff, including confirmation that the
   production economics path cannot be reached.

## Closeout

Update `backlog.md`, `changelog.md`, `IMPLEMENTATION_STATUS.md`,
`docs/DATA_CONTRACTS.md`, and affected Cowork/operator documentation. If C1
fully passes, mark it `DONE`, make C2 the sole `READY` item, and create a
self-contained C2 session prompt. Otherwise leave C1 `IN_PROGRESS` or
`BLOCKED`, name the precise blocker, and do not unlock C2.

Finish by reporting starting and ending commit hashes, exact files changed,
implementation decisions and rejected alternatives, focused/full tests,
runtime/memory measurements, limitations, the four release truths, the sole
next `READY` item, and an explicit reviewed path list suitable for a later
commit.
