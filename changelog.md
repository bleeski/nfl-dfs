# NFL DFS Implementation Changelog

This file records completed implementation work and verification evidence for `backlog.md`. Keep entries factual and append new dated sections beneath `Unreleased`. Do not describe planned, diagnostic, synthetic, or structurally legal work as live-certified or upload-ready.

## Unreleased

### 2026-09-17 (harness): Claude Code as the only surface, CI, autonomous git authority, session orientation

Phase 1 of the Claude Code migration. No engine module, contract, run artifact
or release truth changed; every current path still ends `MODEL_STATUS=PRIOR_ONLY`
and `RELEASE_DECISION=DO_NOT_UPLOAD`. No run was executed.

Added:

- `.github/workflows/ci.yml`: three jobs on every push and pull request.
  `suite` (full pinned pytest, `compileall src scripts`, ranged
  `git diff --check`), `boundaries` (the new boundary file alone, so a broken
  permanent boundary is legible without reading 747 results), and
  `protected-paths` (pull requests only). Python 3.13.7 via `astral-sh/setup-uv`
  with a `uv.lock`-keyed cache. The suite job writes `state/last-ci.json` as an
  artifact and a job summary; CI never pushes to the repository, because a
  workflow that writes to `main` would have to bypass the branch protection that
  makes autonomous merge safe.
- `.github/protected-paths.txt`: one definition of what Ben still reviews, read
  by the CI job, by `scripts/check_protected_paths.py` and asserted by
  `tests/test_repo_boundaries.py`, so the three cannot drift. Covers `CLAUDE.md`,
  `.claude/rules/*.md`, `release.py`, `certification.py`, `preflight.py`,
  `evidence.py`, `sources.py`, `config/evidence_policy.json`,
  `config/metric_registry_*.json`, and the authority model itself.
- `scripts/check_protected_paths.py`: fails a pull request touching a protected
  path without the `ben-review` label. Exit 2 when the check cannot run, because
  an unrunnable gate is not a passing gate.
- `tests/test_repo_boundaries.py`: 45 tests (12 plus 33 parametrized) turning
  `CLAUDE.md` § Permanent boundaries into assertions. Protected-list loadability and matcher behaviour;
  `DK_UPLOAD` confined to a pinned four-module set; `prior_review`'s transitive
  import closure reaching neither a `DK_UPLOAD` writer nor `field.py` /
  `economics.py` (previously only claimed as a report string);
  `AvgPointsPerGame` confined to `dk.py` and `cowork.py`; `ALLOWED_HOSTS` and
  `PROHIBITED_HOSTS` pinned; no module naming a value `ev`, `roi`,
  `win_probability`, `cash_probability`, `edge` or lowercase `calibrated` (the
  uppercase `CALIBRATED` influence tier in `learning.py` is exempt and the test
  says why); the four release truths and the CERTIFIED-requires-
  PROSPECTIVELY_VALIDATED guard intact. Plus 18 refused and 15 allowed command
  shapes against the Bash guard, so its patterns are themselves verified in both
  directions.
- `.claude/hooks/session_start.py` plus the `SessionStart` hook wiring in
  `.claude/settings.json`, matching `startup|resume|clear|compact`. Emits 33
  lines in 55 ms: boundaries, release truths, branch, recent commits, chunk
  queue, active and stale claims, last suite result, calibration state, open
  `[BEN: ...]` flags. Exits 0 unconditionally.
- `scripts/repo_state.py`: derives `state/repo-state.json` from the files that
  are already authoritative (backlog Queue table, `state/claims.json`, the
  recorded suite result, `records/slates/`, `[BEN:]` flags). Hand-maintained
  status rots once two instances disagree; this does not.
- `scripts/record_verify.py`: records a suite result at
  `state/last-verify.json`. A log with no recognizable pytest summary is a
  refusal, not a guess, so a run killed by a tool timeout can never be recorded
  as a result. `ci.yml` imports its `summary_line` so CI and a local terminal
  share one definition.
- `state/claims.json`, the chunk-claim primitive between concurrent instances,
  tracked; the rest of `state/` is derived and gitignored.
- `docs/START_HERE.md` (108 lines): the orientation page the hook points at.
- `docs/CLAUDE_CODE_SETUP.md`: what only Ben can do. Branch protection steps,
  the `ben-review` label, and the documented constraint that
  `permissions.defaultMode` values `auto` and `bypassPermissions` are ignored
  from project settings and must be set in `~/.claude/settings.json`.
- `.claude/rules/git-authority.md`: replaces the reviewed-path-list rule.
- `.claude/skills/onboard/SKILL.md`: cold-start orientation when the hook did
  not run.
- `.claude/hooks/guard_bash.py`, wired as a `PreToolUse` hook on `Bash`. The
  permission grammar matches a prefix, which cannot see a flag arriving after an
  allowed prefix (`git push -u origin claude/x --force` matches the allow rule
  and no deny rule) or a second command in a chain. The guard reads the whole
  command and refuses on a pattern wherever it appears, stripping quoted strings
  and here-document bodies first so that writing a document or a test about a
  refused command still works. It caught that false positive on itself the first
  time it ran, which is why the stripping exists and why
  `ALLOWED_COMMANDS` covers it. Fails open: a crash hands the decision back to
  the normal permission flow.

Changed:

- `.claude/settings.json`: `defaultMode` `acceptEdits`; commit, push to
  `claude/*`, pull request creation and merge, and merged-branch deletion moved
  from `ask` to `allow`. Deny now also covers `git push origin main`,
  `--force-with-lease`, `branch -D`, `rebase`, `filter-branch`, `reflog expire`,
  `gc --prune`, `commit -a`, `add -u`, `Edit(.git/**)`, and the GitHub API write
  tools (`create_or_update_file`, `push_files`, `delete_file`) that would bypass
  local verification. The 16 `PowerShell(...)` entries were deleted: that is not
  a Claude Code tool name, so they had never matched anything and the Windows
  path was unguarded.
- `docs/COWORK_RUNBOOK.md` renamed to `docs/RUNBOOK.md`. Three sections
  rewritten against measurement rather than relabelled: Continuity (the device
  bridge, `git bundle` handoff and PAT discussion are gone; GitHub is the only
  route, with an explicit list of what a clone does not carry), Prerequisites,
  and the Linux runtime. The 2026-09-08 bridge-mount notes are kept as a
  historical subsection because the launcher overrides they produced still work.
  The 2026-09-12 lock-clock ruling is untouched.
- `docs/OPERATOR_GUIDE.md`: the Cowork Desktop section is replaced by a
  two-surface table and a `run-slate` invocation for each. `C:\Users\benja\...`
  replaced by `<repo root>` in both places.
- `CLAUDE.md`: single-surface statement; authority pointer; `Commands` and
  `Token discipline` compressed to stay under the 200-line body limit; session
  protocol item 8 rewritten; branch prefix `codex/` to `claude/`; corrected
  container egress claim.
- `README.md`: Cowork removed from the operating-surface paragraph; CI listed
  under current verification.
- `nfl.sh`: `.cowork-venv` and `.cowork-uv-cache` renamed to `.venv-linux` and
  `.uv-cache-linux`. `test` now pins pytest's basetemp and cache directory under
  `TMPDIR` the way `nfl.ps1` has always pinned them, closing a live
  failure-at-fixture-setup mode on Linux. Overridable with
  `NFL_DFS_PYTEST_TMP` and `NFL_DFS_PYTEST_CACHE`.
- `cli.py`: the subcommand is `run-slate`, with `cowork-run` kept as an alias.
  `COWORK_REQUEST_VERSION` is deliberately unchanged: `cowork.py` hard-rejects a
  mismatched `schema_version`, so renaming the string would invalidate every
  `run_request.json` on disk. `nfl.ps1`'s ValidateSet gained `run-slate`.
- `skills/nfl-standings-pull-checklist/` moved to
  `.claude/skills/standings-checklist/` and renamed to match its directory. It
  was an orphan: referenced by no document, and predating `.claude/` by a day.
- `.claude/skills/{dev-session,verify,close-out}/SKILL.md`: claim the chunk
  before writing code; record the suite result; check protected paths; and at
  close-out commit, push, open the pull request and merge it on green rather
  than printing a path list.
- Three script error strings and `docs/session-prompts/P0-standings-grading-harness.md`
  repointed at `.venv-linux`. Older session prompts are dated records and were
  left alone.

Corrected:

- `CLAUDE.md` said `api.weather.gov` is unreachable from a container. It answers
  HTTP 200. Measured 2026-09-17 alongside `raw.githubusercontent.com` and
  nflverse GitHub release downloads, all reachable.
- `docs/RUNBOOK.md` said `doctor` reports `pass_status: false` with
  `sqlite_probe_error` in a container. It returns `pass_status: true` with an
  empty probe error and WAL journaling; the bridge-mount symptoms do not
  reproduce in a Claude Code container.

Verification:

- Baseline before any change, Linux container:
  `1 failed, 735 passed, 1 skipped in 155.56s (0:02:35)`.
- After: `1 failed, 780 passed, 1 skipped in 149.33s (0:02:29)`. The 45 added
  tests are all in `tests/test_repo_boundaries.py`. The single failure is the
  documented `test_live_check_refuses_once_a_selected_player_has_locked`
  hardcoded-expiry case that chunk P0 repairs; it is unchanged by this work.
- Each boundary assertion was mutation-tested: AvgPointsPerGame appended to
  `ownership.py`, `example.com` added to `ALLOWED_HOSTS`, `_LABEL = "roi"` added
  to `ownership.py`, an `economics` import added to `prior_review.py`,
  `DK_UPLOAD` added to `ownership.py`, and a non-existent path added to the
  protected list. All six failed the intended test and only that test; the tree
  was restored and `git diff --stat -- src/ .github/` was empty afterwards.
- `sh ./nfl.sh doctor`: `pass_status: true`.
- `.venv-linux/bin/python -m compileall -q src scripts .claude/hooks`: clean.
- `git diff --check`: clean.
- `.github/workflows/ci.yml` parses; jobs `boundaries`, `suite`,
  `protected-paths`.
- `python3 .claude/hooks/session_start.py`: 33 lines, 0.055 s.
- `sh ./nfl.sh run-slate` and `sh ./nfl.sh cowork-run` both reach the same
  handler and return the same four release truths.

Known issues in `guard_bash.py`, found by the guard firing on the session that
wrote it, and left in place because both fail in the safe direction:

- `git add -u <explicit path>` is refused, though a scoped `-u` is an explicit
  path list and the rule only means to refuse whole-tree staging. Workaround:
  plain `git add <path>` stages a deletion just as well.
- `git stash list` and `git stash show` are refused, though both are read-only.
  The pattern matches the `stash` subcommand rather than its verb.

Neither was repaired in this commit: the Claude Code auto-mode classifier
refuses to let a session edit the guard that governs it, which is the correct
posture and not something to work around. Narrowing both patterns is a small
follow-up that needs Ben's go-ahead.

Not done in this phase, and why: the fragment-ledger migration
(`changelog.d/`, chunk status in brief frontmatter) is the remaining
multi-instance collision fix and is deliberately separate, being the most
invasive change in the plan. Branch protection on `main` and the `ben-review`
label are Ben's to create; until they exist, "merge only when green" is a
convention rather than an enforced rule.


### 2026-09-16 (repository hygiene): branch consolidation, Showdown scripts tracked, root run outputs ignored

Repository hygiene only. No source module, test, contract, run artifact or
release truth changed, and no run was executed.

Added:

- `scripts/make_showdown_policy.py` and `scripts/qa_showdown_portfolio.py`,
  written 2026-09-14 per the SHOWDOWN_RETROSPECTIVE_2026-09-13
  recommendations but never committed. Unchanged from the versions used on
  the 2026-09-13 and 2026-09-14 slates. CLAUDE.md cites
  `make_showdown_policy.py` as encoding the Showdown rung ladder, so a script
  the lock-clock ladder depends on had been living outside version control
  while its Classic twins (`make_classic_policy.py`, `qa_classic_portfolio.py`)
  were tracked.
- `docs/RUN_RECORD_20260914_DEN_KC.md`,
  `docs/STANDINGS_GREENFIELD_FINDINGS_2026-09-15.md` and
  `data/standings/standings_pulls_2026-09-15.html`. The findings document was
  already recorded as Added by the 2026-09-15 entry above but had never been
  committed; its SHA-256 was verified to match the
  `d7250f0d575e1e957c1bad25da7dd9a5ff0edc2aec3c66c463661380d4751543` that
  entry records. The standings pull follows the tracked
  `standings_pulls_2026-09-14.html` precedent.
- `data/standings/inbox/.gitkeep` and `data/standings/normalized/.gitkeep`.
  Both were present on disk but never tracked, which is why git reported both
  directories as untracked even though `.gitignore` already un-ignores exactly
  those two paths. Matches the tracked `.gitkeep` in `data/runs/`, `outputs/`,
  `data/models/` and `data/registry/`.

Changed:

- `.gitignore`: root-anchored ignores for the 15 operator run outputs that had
  accumulated at the repo root instead of under `data/runs/`
  (`/DKEntries_*.csv`, `/*_official_status.csv`, `/*_portfolio_policy_v*.json`),
  plus `/patches/` and `/Claude outputs/`. The leading slash confines every
  pattern to the root, so the same filenames stay visible under `data/runs/`,
  `tests/fixtures/` or anywhere else in the tree.
- `.gitattributes`: `docs/*_FINDINGS_*.md -text whitespace=cr-at-eol`, extending
  the existing byte-sensitive section and matching the flags already used for
  `tests/fixtures/supplied/**`. The `whitespace=cr-at-eol` half is required:
  without it `git diff --check` reports every line of a preserved CRLF document
  as trailing whitespace. Under the default `* text=auto eol=lf` a CRLF findings
  document is normalized on the way into git. Staging
  `STANDINGS_GREENFIELD_FINDINGS_2026-09-15.md` produced a blob hashing
  `30f69d9703b4bab6af585b852554fbf9cd724ecd49d2616bc6e0d99a41c4fc12` against the
  `d7250f0d...` the 2026-09-15 entry records: the commit meant to preserve that
  document would silently have invalidated its recorded hash. With the rule in
  place the staged blob hashes `d7250f0d...` again. The already committed
  `STANDINGS_DUAL_OPTIMIZATION_FINDINGS_2026-09-15.md` was LF on disk and is
  unaffected; its recorded `664e64c3...` verifies both on disk and in git.
- Corrected a false rule in five places that the 2026-09-15 harness commit had
  introduced: `CLAUDE.md` "Repo etiquette", `.claude/rules/ledger.md`,
  `.claude/skills/close-out/SKILL.md` (three references),
  `.claude/skills/dev-session/SKILL.md` and `.claude/agents/reviewer.md` all
  stated the three ledgers are CRLF. They are LF, and have been since
  `.gitattributes` set `* text=auto eol=lf`: measured 0 CRLF against 481, 614
  and 436 lines respectively. A session obeying the old rule would have rewritten
  every line of a ledger and buried its real change in a whole-file diff. The
  rules now say LF, cite the measurement, and tell the session to read the bytes
  rather than assume. The two CRLF references in
  `DFS_SYSTEM_GREENFIELD_SPEC.md` are correct and untouched: DK CSVs and
  `tests/fixtures/supplied/**` really are byte-preserved by `.gitattributes`.
- PR #14 merged to `main` as `970fea1`; the local checkout moved from
  `docs/claude-code-setup-2026-09-15` to `main`. The branch still exists on
  origin and locally; nothing was deleted.

Verification:

- `patches/slate-day-engine-changes.patch` was audited before being ignored,
  not assumed stale. It applies in neither direction, but every marker from
  all six of its hunks is present in `main`: `embedded_pool_start` (`dk.py`),
  `EXCLUDE_UNRESOLVED_UNAVAILABLE` (`priors.py`), `write_pool_scores` and
  `DIAGNOSTIC_NOT_AN_UPLOAD_AUTHORIZATION` (`selection.py`), the unavailable
  vocabulary in `contracts.py`, and
  `tests/fixtures/supplied/DKEntries CSV 20 entries.csv`. The work landed
  under `7edddee`, not as its own commit, which is why the patch no longer
  lines up in either direction.
- The two documents in `Claude outputs/` are byte-identical (`diff -q`) to the
  tracked `docs/session-prompts/QA1-adversarial-qa-agent.md` and
  `W4-cowork-prior-only-profile.md`.
- `git ls-files --cached --ignored --exclude-standard` empty after each
  `.gitignore` change: no tracked file became invisible.
- `py_compile` clean and `--help` runs on both Showdown scripts;
  `git diff --check` clean.
- Full suite NOT run: no `src/` module changed in this work.

Left open:

- Nothing was deleted. `patches/` and `Claude outputs/` remain on disk and are
  now ignored, per this repo's never-delete posture; they can be removed by
  hand at any time.
- `tests/test_w6_live_preflight.py::test_live_check_refuses_once_a_selected_player_has_locked`
  still fails on its hardcoded 2026-09-14 expiry until `P0` pins its clock.

### 2026-09-15 (research and reprioritization): standings evidence, the prize-tail program, no code changed

Two research reports were added under `docs/` and the development queue was
reprioritized on their evidence. No source, test, contract, run artifact or
release truth changed.

Added:

- `docs/STANDINGS_DUAL_OPTIMIZATION_FINDINGS_2026-09-15.md` (SHA-256
  `664e64c37061b83cdeb5e6bbd0209e05cba307ea9d1c463607e0e3943e3ef065`). All 26
  exports in `data/standings/inbox` (1,870,717 entries, five slate groups)
  joined to the contest-entry history and the same-slate salary files; every one
  of our 71 standings entries traced byte-for-byte to the file that produced it
  (NE@SEA to the replay-anchored review CSV `cf33f3e5…`, SF@LAR to
  `review_final`, Week 1 Classic to `DKEntries_NFL_Week1_LATESWAP_FINAL.csv`
  and not to `build_portfolio.py`, DAL@NYG to `REVIEW_v6`, DEN@KC to
  `v8_FINAL`). Lineup-derived ownership reconciles to DraftKings `%Drafted` at
  0.002 pp once Classic base and FLEX rows are summed and blanks are kept in the
  denominator. Headline measurements: Walker-less DEN@KC lineups paid 0 of
  99,349; the NE@SEA 23-way tie paid $54,065.22 per entry; ≥85% single-player
  concentration carried 1.4x to 12x the zero-paid rate across 8,007 multi-entry
  field portfolios in four games; exactly one pass catcher with the rostered QB
  and $1 to $500 left were the only construction features with top-1% lift ≥1.1
  and below-median lift <1 in all four Showdown games.
- `docs/STANDINGS_GREENFIELD_FINDINGS_2026-09-15.md` (SHA-256
  `d7250f0d575e1e957c1bad25da7dd9a5ff0edc2aec3c66c463661380d4751543`), the
  same-day ownership, coverage and construction report; the two agree on every
  shared figure.

Changed:

- `backlog.md`: new `Reprioritized development program — 2026-09-15 (prize tail
  first)` inserted above the 2026-09-10 program, which is marked superseded in
  ordering only. New chunks P0, P0b, P1, P2, P3a, P3b, P4a, P4b, P4c, P5, P6,
  each sized for one Claude Code session with read list, files, scope,
  acceptance and hand-back; C3's native Excel acceptance split out as `C3X`
  (`DEFERRED`, pending Ben's ruling); C4 re-sequenced behind P2; Q2 to Q7 and
  QC1 retained as the promotion track absorbing the P chunks. A disposition
  table records accept/modify/defer for each greenfield recommendation; none
  rejected outright, item 7 deferred to accrual. Tracker-protocol pointer
  updated; a 2026-09-15 `Next action` entry names `P0` and `P1` as `READY`.
- `IMPLEMENTATION_STATUS.md`: pointer paragraph for the 2026-09-15 program.
- `CLAUDE.md` restructured for Claude Code as the development surface (306 →
  183 lines): permanent boundaries, release truths and a compressed lock-clock
  ruling stay; the eight-step "run the slate" procedure and the full 2026-09-12
  ruling text moved verbatim into `docs/COWORK_RUNBOOK.md` ("Moved from
  CLAUDE.md on 2026-09-15"), whose one pointer to the ruling was updated; a new
  "Developing in Claude Code" section carries commands, the eight-step session
  protocol, etiquette and gotchas. Maintainer notes sit in a stripped HTML
  comment.
- New `.claude/settings.json` (allow: status/diff/log/test/doctor; ask: add,
  commit, push, merge, rebase, setup; deny: `git add -A`/`.`, reset --hard,
  checkout --, restore, clean, stash, force push, amend, `rm -r`, and `Edit` on
  `data/standings/inbox/**`, `data/runs/**/inputs/**`, `tests/fixtures/supplied/**`,
  `uv.lock`). New path-scoped `.claude/rules/` (immutable-data, contracts,
  selection-and-objective, operating-path, tests, ledger). New skills
  `/dev-session`, `/verify`, `/close-out` in `.claude/skills/`, all
  `disable-model-invocation`.
- `.gitignore`: `CLAUDE.local.md`, `.claude/settings.local.json`.
- `backlog.md` tracker protocol: the session-start read list now names
  `CLAUDE.md`, the current program and chunk brief, and the changelog head,
  with the spec opened on citation rather than by default.
- `docs/session-prompts/P0-standings-grading-harness.md`: the first prize-tail
  session prompt, written thin (goal, constraints, pointers, acceptance) against
  the thick brief in `backlog.md`.
- Token discipline (same day, after measuring that a session following the
  old read list spent ~80,000 tokens on ledgers before touching code):
  `backlog.md` split into a live queue (160 KB → 45 KB) plus
  `docs/backlog-archive/backlog-history-through-2026-09-14.md` (DONE briefs
  DEV0/Q1/Q1B/Q1C/C1/C2, Baseline, punch list, S0-S10, post-review tranches,
  pre-09-14 Next-action entries and the R16-R18 proposals, all verbatim); the
  eleven P-chunk briefs moved verbatim to `docs/chunks/<ID>-<slug>.md` with a
  status/brief index left in place; `changelog.md` split into live (163 KB →
  24 KB) plus `docs/changelog-archive/changelog-through-2026-09-14.md`. A
  line-by-line conservation check found zero original lines missing from the
  union of live and archive files. `CLAUDE.md` gained a *Token discipline*
  subsection (read ledgers by section, never Read a data export, `explorer` and
  `reviewer` subagents, `git diff --stat` first) and stays at 200 lines.
  `.claude/settings.json` now also denies `Read(data/standings/inbox/**)`;
  `.claude/agents/explorer.md` (read-only, sonnet) and `reviewer.md` (fresh-context
  diff review) added; the ledger and immutable-data rules and the session skills
  point at the new locations.

Verification: report tables checked for pipe consistency; every quoted figure
re-derived from the standings pickles in the research session (device VM,
Python 3.10, pandas 2.3.3, numpy 2.2.6); backlog and status files rewritten
with their original CRLF line endings intact.

### 2026-09-14 (Q1C): the pre-lock manifest emitter, and four gates no producer could clear

Merged to `main` on 2026-09-14 in `4313455fcd8fd722b699a799dbe19dff19c1be68`
(PR #13), in one commit `7edddee` with Q1B below and the previously uncommitted
C3 tranche. The three were not separable: `prior_review.py` imports
`classic_review.py`, which had never been committed, and nine files carry changes
from more than one tranche. **Merging C3 was not accepting it** — it remains
`BLOCKED` on native Excel open/recalculate/save/reopen acceptance.

Ran natively on Ben's Windows machine against the Windows `.venv` throughout.

Added:

- `src/nfl_dfs/prelock_manifest.py` — builds and writes
  `nfl_prelock_run_manifest_v1`. Every hash it records is one the run already
  computed while doing the work, never recomputed from a path: a path can be
  swapped between the run and the emitter, and a recomputed hash would silently
  bless the swap. Canonical sorted-key JSON through a temporary file, so the same
  run writes byte-identical bytes.
- `tests/test_prelock_manifest.py` (19 tests), including the end-to-end proof:
  a real Classic `prior_review` run freezes a manifest, a settlement request
  binds it, `settle` captures the package and `settle --replay` reproduces it.
  A separate test proves the Showdown exit freezes one too, because a manifest
  emitted from only one of the three success paths would leave the other two
  unsettleable — the exact failure Q1B found in the repo.

Changed:

- `src/nfl_dfs/prior_review.py` emits the manifest from all three success exits
  — Showdown, Classic C1/C2 and Classic C3. Emitting from only one would have
  left the other two unsettleable, which is the exact failure Q1B found. It is
  emitted for a `DO_NOT_UPLOAD` run on purpose: every prior-only run ends that
  way, and those are the review lineups Ben actually enters by hand, so a
  manifest gated on an uploadable package would never be emitted at all. It
  changes no release truth. The run also now records the salary and entry
  *paths* beside the hashes it already kept, so a request can bind the exact
  bytes the manifest names.
- Classic writes `assignments.csv`. `write_assignments_csv` gained a `mode`
  parameter and Classic uses the nine-slot geometry `lineups.read_assignment_csv`
  reads. Without it a Classic run could not bind an assignment into a manifest at
  all, because its selection existed only as `classic_assignment.json`.
- `scripts/make_settlement_request.py` resolves zero scenario banks for a
  `PRIOR_ONLY` manifest and still blocks, naming the status, for any other.
- The emitter refuses when a JSON prediction declares a schema version other than
  the one it expects. Settlement re-reads those files and compares versions, so
  without this check a drifted expectation would write a manifest asserting
  something false and fail at capture days later rather than at the run.

Contract corrections, each on Ben's explicit ruling before it was made. All four
were gates that no honest producer could clear, measured against Q1's own passing
fixture by removing, one at a time, exactly what a prior-only run lacks:

- **`field_size` is no longer compared** between the manifest and the request.
  This was never `prior_review`-specific. `_validate_prelock_manifest` required
  the manifest to record a field size equal to the request's, and
  `_prepare_settlement` separately required that to equal the settled standings
  row count — so a pre-lock manifest had to record the *settled* field size,
  which nothing can know before lock. The legacy `build` path records the
  operator's `--field-size` assumption and would have failed identically the
  first time a contest did not fill; 193391013 was advertised at 133,000 and
  settled 126,020. Q1's fixture only passed because its synthetic contest has
  `field_size` 2 and the operator owns both entries. The manifest now records the
  assumption with a `field_size_basis` label, and the run brief reports
  `assumed_field_size` beside `settled_field_size` as a Q6 diagnostic. Contest
  id, draft group, mode and entry fee stay hard identity checks, unchanged.
- **The payout hash and version are optional in the manifest**, and only in the
  manifest. The request still binds the payout bytes by SHA-256 either way.
- **`objective`, `advertised_prize_value` and `ticket_face_value` are compared
  when the manifest records them**, and not required when it does not.
- **A request may bind zero scenario banks if and only if `MODEL_STATUS` is
  `PRIOR_ONLY`**, enforced by a `SettlementCaptureRequest` validator so the
  relaxation cannot reach a prospectively-validated model. A degenerate
  one-scenario bank carrying the point estimates was considered and rejected: a
  bank with no distribution invites being read as one.

Test changes, with their reasoning:

- Two Classic suites asserted that no `assignments.csv` existed, and the C2
  prohibited-path guard banned `write_assignments_csv` outright. That file is not
  an upload shape — no Contest ID, Contest Name, Entry Fee or instructions block,
  so DraftKings would reject it, and Showdown's prior review has always written
  the same file. The `DK_UPLOAD_*` and `DK_REVIEW_ENTRY_*` prohibitions are
  unchanged and still checked. The blanket ban became a spy asserting the writer
  is called with `mode=CLASSIC`, which is strictly stronger: it proves the
  geometry is right rather than only that nothing happened.

Measured evidence:

- Complete pinned suite: **735 passed, 1 failed, 1 skipped in 198.190s** (737
  collected, 0 errors), against the Q1B measurement of 715 passed, 1 failed, 1
  skipped (717 collected). Exactly the 20 tests this tranche adds — 19 new
  pre-lock manifest tests plus one net from splitting a builder scenario test in
  two — with the same single pre-existing failure and no regression. That failure
  is the `test_live_check_refuses_once_a_selected_player_has_locked` time bomb
  described in the Q1B entry below: a hardcoded evidence expiry of
  2026-09-14T00:00Z that has now passed, identical in `HEAD`, unrelated to this
  work and still unfixed.
- Composition on a realistic `cowork-run` tree: the request builder resolves
  `prelock_manifest`, `predictions`, `assignments`, `scenarios`,
  `release_truths`, `salary`, `entries`, `entry_fee`, `draft_group`, `mode`,
  `scoring`, `metric_registry` and `owned_entry_ids`, leaving exactly two
  blockers — `PAYOUT_TABLE_ABSENT` and `NORMALIZED_STANDINGS_ABSENT`. Both are
  facts only Ben supplies at settlement time, and both are correct refusals.
- A replayed run at a pinned `as_of` freezes a byte-identical manifest. The
  emitter stamps the run's own clock rather than `now()` for exactly this reason,
  and the assignment path it records is run-relative, never absolute — both were
  real determinism defects caught by that test.

Limitations:

- **The corpus still holds zero settled contests.** Q1C makes the next slate
  settleable; it settles nothing. A real contest still needs its payout table and
  its standings pull, and must have come from a single-contest reserved-entry
  template — 16 of Ben's 18 did not.
- **It recovers none of the eighteen contests already played.** A pre-lock
  manifest records what was predicted before lock; writing one afterwards would
  be a fabricated prediction. Those contests stay dispositioned.
- The end-to-end capture and replay is proven on a synthetic complete field where
  the operator owns every entry. No real contest has been settled.
- `MODEL_STATUS=PRIOR_ONLY` and `RELEASE_DECISION=DO_NOT_UPLOAD` are unchanged,
  and emitting a manifest changes neither. Nothing here says anything about model
  quality.

### 2026-09-14 (Q1B): standings intake, the settlement request builder, and why no contest can settle

Ran natively on Ben's Windows machine against the Windows `.venv` throughout, via
`.\nfl.ps1 test` and `.venv\Scripts\python.exe`. No Cowork container, no
`.cowork-venv`, no staging. The two Cowork venvs were never mixed.

Added:

- `scripts/file_standings.py` — standard-library, no-network normalizer from a
  raw DraftKings standings export to `nfl_standings_csv_v2`, content-addressed
  under `data/standings/normalized/<contest_id>/<sha256>.csv` with a sibling
  `nfl_standings_normalization_v1` manifest recording the raw SHA-256, the
  normalized SHA-256, the bound salary and payout hashes, and every
  normalization decision. The raw inbox file is read, hashed and left byte-
  identical; a test asserts both its bytes and its mtime are unchanged after a
  full run. `--survey` reads an export without any binding and reports the
  observed field size, which is otherwise nowhere on disk.
- `scripts/make_settlement_request.py` — builder for `nfl_settlement_request_v1`.
  Resolves every field from frozen bytes and refuses by name for anything it
  cannot. Release truths are copied out of the frozen pre-lock run rather than
  re-derived, so settlement can never report a better decision than the slate
  shipped with. Salary and entry snapshots are classified by parser, never by
  filename; prediction and scenario artifacts are located by the SHA-256 the
  pre-lock manifest itself declares, so the wrong file cannot be bound.
- `tests/test_standings_normalizer.py` (25 tests) and
  `tests/test_settlement_request_builder.py` (18 tests).

Changed:

- `scripts/standings_checklist.py` now distinguishes `filed` (a raw export in the
  inbox), `normalized` (an `nfl_standings_csv_v2` on disk) and `settled` (a
  complete Q1 settlement bundle, read out of the bundle rather than inferred from
  a directory name). Before this, dropping any file into the inbox satisfied the
  checklist and nothing else. It also now reports raw, normalized and bundle
  presence per contest *independently of status*, because a disposition is a
  ruling about workflow and not a claim that the bytes are gone — all 18 raw
  exports are on disk and every contest is dispositioned.
- `tests/test_standings_checklist.py` grew from 14 to 22 tests. One existing
  assertion changed because the section heading did (`Filed or dispositioned` →
  `Filed, normalized, settled or dispositioned`). The fixture now also isolates
  `NORMALIZED_DIR` and `SETTLEMENTS_DIR`; without that the tests read the real
  repo's state and were only passing because the synthetic contest IDs did not
  collide with a real one.
- `.gitignore` ignores `data/standings/inbox/*` and `data/standings/normalized/*`
  on the existing `data/runs/*` precedent, keeping a `.gitkeep` in each. The 18
  raw exports and one normalized field are ~58MB of bulk operator data. The small
  records — `dispositions.json` and the rendered checklists — stay visible.
- All 18 entered contests dispositioned `placeholder` with per-contest reasons,
  per Ben's 2026-09-14 ruling.

Measured evidence:

- **Complete pinned suite, Windows, first confirmation on this box since
  2026-09-12.** Baseline before any change: **664 passed, 1 failed, 1 skipped**
  (666 collected). After Q1B: **715 passed, 1 failed, 1 skipped in 368.732s**
  (717 collected, 0 errors) — exactly the 51 tests this tranche adds (25
  normalizer, 18 builder, 8 checklist), with the same single pre-existing
  failure and no regression. The expected 644 in the session prompt was low: the
  tree carries 22 more uncommitted tests than that estimate.
  The bare `pytest -q` invocation errors at fixture setup on this box and must be
  run through `.\nfl.ps1 test`, which supplies the `--basetemp` and `cache_dir`
  the default locations cannot provide; a run killed that way is a tooling
  artifact and is not a failure.
- **The one baseline failure is pre-existing and is a time bomb that came due
  today.** `tests/test_w6_live_preflight.py::test_live_check_refuses_once_a_selected_player_has_locked`
  hardcodes `expires_at=datetime(2026, 9, 14, tzinfo=timezone.utc)` and calls its
  `_certified` helper without pinning the certification clock. `certify_upload`
  grades evidence at the live clock, so as of today that evidence has expired and
  certification correctly returns `DO_NOT_UPLOAD`, failing the helper's own
  `assert manifest.release_decision.value == "CERTIFIED_UPLOAD_PACKAGE"`. The
  line is identical in `HEAD`, so it is not a Q1B regression, and it will fail
  every day from now on. The fixture's own docstring already documents the
  repair: pass `monkeypatch` and `now`. Left unfixed — it is a certification test
  and outside Q1B's stated scope — and raised here rather than patched quietly.
- **Reference evaluator, fresh measurement** (design answer 2): 133,000 synthetic
  entries refused `REFERENCE_RUNTIME_BUDGET_EXCEEDED` at the registered 10.0s
  budget and settled exactly in **27.868447s** at 30.0s (177,477 work units,
  95,515,201 peak traced bytes); 200,000 synthetic settled in **22.582837s**
  (244,496 work units, 142,015,359 peak traced bytes). Runtime is not monotonic
  in field size — it tracks tie and duplication structure — so field size alone
  does not predict whether a contest settles in budget. The builder's default
  `max_runtime_seconds` is raised 10.0 → 180.0 on that evidence; `max_entries`
  stays at the registered 200,000.
- **Real normalization**: contest 193391013, 126,020 entries, normalized end to
  end in 5.908s wall including the reference settlement. 36,274 `Points` rows
  rounded, largest adjustment 0.00001. 220 entries never submitted a lineup. 757
  entries across 9 tie groups settle to a fractional cent share; half-even
  rounding leaves a 33-cent residual, reconciling 224,999,967 paid cents against
  the advertised $2,250,000.00.
- **Points rounding justified, not assumed**: across all **1,415,500** entry rows
  in the 18 exports, the largest raw-to-2dp gap is **0.00003** and
  `ROUND_HALF_EVEN` never disagrees with `ROUND_HALF_UP` on any row. Rank
  agreement against DraftKings' own `Rank` column is 100% at 2dp on every contest
  checked (71/71, 237/237, 475/475, 9512/9512, 5945/5945) and partial on the raw
  values (70/71, 223/237, 430/475, 6415/9512, 4195/5945).
- **Lineup reconstruction verified against the engine**: the canonical keys the
  normalizer rebuilds for Ben's two entries in 193391013 match exactly those
  `lineups.validate_lineup` builds from the `excl20` review export, and differ
  from those built from `data/runs/20260909-showdown-ne-sea/review/assignments.csv`.
  The standings export can therefore identify which stored assignment actually
  reached DraftKings.
- **Observed field sizes** (from the export row counts, which is the only place
  the true settled field size exists): 193028206 832,342; 195390868 178,359;
  193391013 126,020; 195390867 83,234; 195526142 59,453; 195390870 47,562;
  195526144 and 195526145 35,671 each; 195390889 9,512; 195526163 5,945;
  195520918 475; 195379585, 195507184, 195521582 and 195641911 237 each;
  195642262 190; 195384501 71; 195379668 47. 193391013's observed 126,020
  disagrees with the operator-stated 133,000 recorded in
  `data/runs/20260909-showdown-ne-sea-live-2206z/contest/contest_facts_operator_supplied.json`;
  the observed count is the settled field and the disagreement is reported, not
  reconciled away.

Findings, all recorded under Q1B in `backlog.md`:

- **No `data/runs/` snapshot holds an `nfl_prelock_run_manifest_v1` or an
  `nfl_scenario_bank_v1`, for any of the 18 contests.** Only the legacy `build`
  command writes them; the `prior_review`/C1-C3 path that produced every contest
  Ben has entered never has. Those 18 are permanently unsettleable, and a
  pre-lock prediction record cannot be written after the fact. The repair is an
  emitter on the path Ben actually uses; it makes the next slate settleable and
  recovers none of these. Flagged `[BEN: ...]` as its own tranche because it
  touches `prior_review.py`, which Q1B was scoped out of.
- **`nfl_standings_csv_v2` cannot represent a real DraftKings field, in two
  independent ways.** Entries that paid in and never submitted a lineup (11 of 18
  exports carry them) have no valid representation, and exact tie splits that are
  not whole cents (757 entries in 193391013 alone) cannot be held in a cent-exact
  column. The second is the more serious: `settlement._prepare_settlement`
  compares the evaluator's exact `Fraction` against the file's integer cents for
  every field row, so any contest with an uneven tie split can never clear
  `STANDINGS_PRIZE_MISMATCH` whatever the intake writes. Both are refused by
  default with an explicit, default-off, fully labelled opt-in; neither contract
  was changed. Flagged `[BEN: ...]`.
- **DraftKings exports no per-entry prize**, so the `Prize` column is derived
  from the payout table by the reference evaluator and labelled as such. The
  downstream `STANDINGS_PRIZE_MISMATCH` check is therefore not independent
  evidence on any file this tool writes, and that is stated rather than implied.
- **16 of 18 contests** came from multi-contest reserved-entry templates that
  `settlement.require_single_contest` refuses, and **17 of 18** have no payout
  table on disk.

Limitations:

- **The validation corpus holds zero settled contests.** Q1B did not change that
  number and could not: the missing pre-lock manifests are unrecoverable. It
  changed the corpus from "zero for unknown reasons" to "zero for four named,
  measured reasons, one of which has a known repair".
- The `--request` → `--replay` round trip is proven on a **synthetic** complete
  slate, not on a real contest. No real contest can reach capture.
- One contest's result was measured and is reported as such. It is not evidence
  that the engine picks good lineups, it licenses no EV, ROI or calibration
  claim, and one slate is not a sample.
- `MODEL_STATUS=PRIOR_ONLY` and `RELEASE_DECISION=DO_NOT_UPLOAD` are unchanged.
  Landing a settled slate would change no release truth, and none landed.
Entries dated 2026-09-14 (follow-up and checklist) and earlier, back to 2026-09-01, moved verbatim to `docs/changelog-archive/changelog-through-2026-09-14.md` on 2026-09-15. Append new entries directly under `## Unreleased`; when this file passes roughly 500 lines, move the oldest entries to the archive rather than letting sessions read them.

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
