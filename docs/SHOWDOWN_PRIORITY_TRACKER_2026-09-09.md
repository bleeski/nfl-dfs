# Showdown priority work — session tracker

Created: 2026-09-09. Owner: the session implementing the active item.

**Use multiple sessions: five bounded implementation sessions and one acceptance
session. Start with SD1.** This is a scope estimate, not a deadline guarantee.
If a chunk uncovers a larger dependency, record it and split the remaining work
instead of declaring a partial result complete.

The intended workflow remains: Ben attaches a salary CSV and reserved-entry CSV
in Cowork and requests a Showdown portfolio. Cowork obtains and freezes approved
supporting evidence, runs deterministic code, and returns an understandable
review package with exact entry assignments and explicit blockers.

These six chunks improve the **prior-only review workflow**. They do not finish
the full tournament engine or authorize a generated upload. Keep
`MODEL_STATUS=PRIOR_ONLY` and `RELEASE_DECISION=DO_NOT_UPLOAD` throughout.
Software completion, current evidence, and model validation are separate facts.

## Verified starting point

| Item | Baseline |
|---|---|
| Repository | `C:\Users\benja\Documents\Claude\nfl-dfs` |
| Branch | `codex/s6a-deterministic-projection-producer` |
| HEAD verified when this tracker was created | `6b5d4625b6fa3234a07680ca27dafc819fbd05ab` — Harden Showdown review workflow and live preflight |
| Tracked working-tree changes at inspection | None |
| Existing untracked work to preserve | `Claude outputs/`; `docs/session-prompts/W2-expiry-and-selection-objective.md`; `docs/session-prompts/W4-cowork-prior-only-profile.md` |
| Last recorded code verification | 332 passed, 1 skipped in 63.06 seconds; Python 3.13.7 on Windows. The skip was Windows symlink-creation permission. Tests were not rerun for this planning-only change. |
| Last actual-file rehearsal | NE–SEA, 136 salary rows / 68 people, two entries; legal, independently audited, repeatable review bytes on Windows |
| Rehearsal release truths | `FILE_VALID=true`; `EVIDENCE_STATE=UNKNOWN`; `MODEL_STATUS=PRIOR_ONLY`; `RELEASE_DECISION=DO_NOT_UPLOAD` |
| Still unverified | Actual Cowork/Linux execution of the complete latest workflow, current live evidence, larger portfolios, prospective model quality |

Evidence and repaired findings: [readiness review](READINESS_REVIEW_2026-09-09.md).
The recorded September 9 forecast expired at 20:00:40 UTC that day. It is historical
test evidence, never a reusable assertion that a future run has current weather.
Recheck HEAD, dirt, runtime and relevant code at every session start.

## Queue

Only one item in **this priority sequence** is `READY` at a time. Historical W/S
backlog items remain separate; their statuses do not override this queue.

| Order | ID | Priority | One-session deliverable | Status | Dependency |
|---|---|---|---|---|---|
| 1 | SD1 | P0 | Kicker-role evidence contract and conserved kicker scoring | `DONE` | None |
| 2 | SD2 | P0 | Offensive-role evidence and explicit missing-history handling | `DONE` | SD1 |
| 3 | SD3 | P1 | Precise, validated portfolio-control contract | `DONE` | SD2 |
| 4 | SD4 | P1 | Enforced portfolio controls and independent assignment audit | `DONE` | SD3 |
| 5 | SD5 | P1 | Readable, artifact-bound lineup and exposure review | `READY` | SD4 |
| 6 | SD6 | P0 acceptance | Complete Cowork/Linux rehearsal with current evidence | `BLOCKED` | SD5 and access to the actual environment and matching files |

Priority indicates consequence; order reflects dependencies. Do not attempt all
six in one session. If there is too little time before lock, report what remains
unverified instead of relaxing validation or promising same-day readiness.

## SD1 — Resolve kicker roles and conserve projected production

**Why first:** `prior_score.score_pool` gives every eligible kicker the entire
team kicking stat line. With two selectable kickers, the scorer duplicates team
production. Historical offensive snap share cannot identify a starting kicker.

Scope:

- Add a small, versioned, source-bound current-role contract for kickers. Bind
  exact current-slate identity, team/game, salary hash, captured evidence hashes,
  observation/expiry times, and either an evidenced sole role or an explicitly
  supported numerical split. Cowork can prepare this auxiliary artifact from
  approved evidence; the normal user workflow still starts with two CSVs.
- Resolve CPT/FLEX records to the underlying person, after existing salary,
  official inactive and operator exclusions. Role evidence cannot reactivate an
  excluded person. A zero offensive snap share is not proof of inactivity.
- Apply team kicking production once across supported roles. Multiple eligible
  kickers without adequate role evidence must stop selection with a named role
  blocker. Never fabricate an equal split or pick a starter by salary.
- With no supplied role artifact and exactly one eligible kicker, preserve only
  an explicit prior-only sole-listed assumption, visibly distinguished from
  confirmed starter/activity evidence. No eligible kicker means no allocation
  to a nonexistent person; it need not invalidate a legal roster without a K.
- Thread the artifact through request parsing, path confinement, immutable
  snapshotting, scoring, provenance reporting, replay and final freshness checks.

Acceptance:

- Reproduce the two-kicker duplication before fixing it. Deterministic tests
  verify sole-role allocation, supported split conservation, ambiguous-role
  blocking, zero-kicker handling and CPT exactly 1.5 times the person's score.
- Positive-share recipients are eligible; zero-share or officially inactive
  kickers cannot enter selection as fabricated value. Never silently renormalize
  a stale role declaration after its named starter becomes inactive.
- Reject unknown/wrong-team IDs, conflicting roles, duplicate declarations,
  malformed/nonfinite shares, unbound or modified evidence, future/stale times,
  and expiry during selection. Verify an immutable copied package can replay.
- Integration tests reach `cowork-run --profile prior_review`; valid diagnostic
  output retains the four independent truths. Invalid evidence leaves named
  blockers and no newly generated review-entry CSV.
- Relevant regressions, full pinned-runtime suite, doctor and whitespace checks
  pass; record exact results and any environment limitations.

Non-goals: offensive role forecasting, simulator repairs, ownership, portfolio
policy, calibrated model promotion, Classic or any upload-gate change.
This completes the kicker slice, not current-role modeling as a whole.

Primary areas: `prior_score.py`, `participation.py`, `prior_review.py`,
`cowork.py`, `cli.py`, input contracts and their tests. Full instructions:
[next-session prompt](session-prompts/SD1-current-role-and-kicker-scoring.md).

## SD2 — Apply supported offensive roles and distinguish missing history

**Problem:** prior-season shares can misvalue active backups, rookies and players
with changed teams or roles. A missing record is not observed zero production.

Scope:

- Extend SD1's evidence interface to the current single-game offensive pool.
  Separate observed historical zero, missing history, current role unknown,
  explicit nonparticipation, and a source-supported changed opportunity share.
- Accept numerical opportunity adjustments only through a validated, versioned
  contract tied to captured approved evidence. Qualitative reports may supply
  bounded role flags or review blockers; prose alone cannot invent a share.
- Apply supported adjustments before scoring and normalize/redistribute within
  the declared team opportunity totals. Do not cap a promoted backup at his
  historical mean snaps or transfer a player's old-team denominator silently.
- For an unresolved material role or missing historical basis, emit a precise
  diagnostic and required next evidence; never silently turn uncertainty into
  a zero-valued punt, presumed starter, or a claim that the pool is complete.
- Integrate coverage and assumption reporting into prior_review and document
  how Cowork obtains the supporting artifact without requesting freehand model
  values from Ben.

Acceptance: fixtures for a promoted backup, rookie without history, transfer,
missing versus observed-zero history, conflicting sources, invalid share totals,
expired adjustments and inactive precedence; conserved team totals; exact-ID
joins and deterministic replay; no APPG input or invented replacement values.
Maintain one current-role finding per affected person for later review.

Non-goals: a new projection model, broad depth-chart scraping, route/air-yard
feature research, sharp-market feeds, simulator participation or calibration.
If an approved numerical source is absent, complete and test the evidence gate
and report that live role resolution remains blocked; do not label it solved.

Primary areas: `priors.py`, `projection.py`, `participation.py`, `prior_score.py`,
`prior_review.py`, SD1's contract and tests.

## SD3 — Define portfolio controls without ambiguous percentages

Scope:

- Define a versioned policy for maximum combined-person exposure across CPT/FLEX,
  maximum Captain exposure, maximum pairwise person overlap and canonical lineup
  uniqueness. Retain supported explicit exclusions. Bind policy to the requested
  entry set and salary identity map.
- State percentage units, denominator (all requested entries), conversion to
  integer maxima (`floor(fraction * entry_count)`), zero/100% behavior, override
  precedence and validation. A small-portfolio cap that rounds to zero means
  zero; never silently round it up or weaken it.
- Supply deterministic normalization and necessary feasibility checks with clear
  errors. Necessary checks are not a proof that a feasible portfolio exists.
- Make repetition of a Captain a configurable outcome under caps, not an
  implicit demand that every entry have a different Captain. Do not claim these
  preferences minimize modeled drawdown.

Acceptance: malformed units, unknown IDs, invalid ranges, contradictory caps,
rounding at two/three entries, CPT/FLEX person aggregation, policy hashing and
request round-trip tests. Document examples with exact integer limits.

Boundary: SD3 delivers the contract/validator. Do not advertise active enforcement
or silently accept a production request with unenforced controls. Until SD4 is
complete, execution must explicitly refuse that new policy as unsupported.
Do not alter the existing selection objective in this session.

Primary areas: a focused portfolio-policy module, `cowork.py`, CLI contracts,
`docs/DATA_CONTRACTS.md` and tests.

## SD4 — Enforce and independently audit the portfolio

Scope:

- Connect SD3's policy to candidate generation and joint assignment/selection.
  Enforce global person and Captain caps, exact requested-entry coverage,
  canonical uniqueness and configured pairwise overlap. Preserve DK legality.
- Replace default forced-distinct-Captain behavior with the explicit policy.
  Remove silent cycling of fewer lineups across more entries. An incomplete or
  contradictory request must produce an actionable failure, not partial success.
- Retain deterministic projection-led review scoring. Use bounded MILP selection
  and report solve status, budget and candidate-bank coverage. Candidate-bank
  exhaustion or a time limit must not be reported as mathematical infeasibility
  of the full slate.
- Independently recompute all controls from the final assigned roster IDs before
  review export; do not trust the selector's exposure summary or success flag.

Acceptance: a case where greedy selection misses a feasible portfolio; allowed
repeated Captain; combined CPT/FLEX cap violation; exact rounding boundaries;
infeasible controls; bank exhaustion; timeout; duplicate/partial assignments;
tampered summary; deterministic replay and exact exported-byte legality.
Rehearse the two-entry case and a declared modest multi-entry fixture. Record
measured runtime and supported size; do not assert 20/150-max readiness without
testing those sizes. No relaxing user caps to finish.

Non-goals: W8/W9 field economics, ownership/duplication estimates, probabilistic
drawdown objectives, exhaustive bank completeness or large-field benchmarks.

Primary areas: `selection.py`, `optimizer.py`, prior_review integration and
independent review/assignment validation.

## SD5 — Make the review package understandable

Scope:

- Extend the existing review package instead of building a new application.
  Show each entry/contest, Captain and FLEX names, exact IDs, individual and total
  salaries, remaining salary, projection label, and any role/activity concerns.
- Show actual portfolio exposure as counts and percentages, separate Captain
  exposure and combined-person exposure, policy limits, overlap and uniqueness.
- Show source observations/expiry, unsupported role assumptions and missing
  evidence. Keep role confidence separate from official active status.
- Include the four release truths, named blockers, input/policy/output hashes,
  provenance links and one next operator action. State that scores are prior-only
  central estimates and that the exported CSV is for review.

Acceptance: independently reconcile every displayed roster, salary and exposure
against the exact exported artifact; repeated names and CPT/FLEX IDs work;
escape untrusted text and prevent spreadsheet formula injection; inspect the
rendered report/workbook on a two-entry and a larger fixture; stale/missing
evidence and `DO_NOT_UPLOAD` are visible without reading raw JSON.

Non-goals: new UI framework, polished product redesign, payout/EV dashboard or
W7's settlement ingestion. Save a sample output in an ignored run directory.

Primary areas: existing workbook/report writer, `review_export.py`, `cowork.py`
and report tests; operating documentation where its output instructions change.

## SD6 — Rehearse the complete Cowork workflow

Scope:

- In the actual Claude Cowork/Linux environment, start from matching salary and
  reserved-entry CSVs and the documented command. Exercise setup, schema-based
  discovery, frozen approved sources, roles/activity evidence, projection,
  portfolio controls, review report and independently audited CSV bytes.
- Use fresh game-specific evidence; obtain supporting data through approved
  adapters and preserve artifacts. Never substitute old NE–SEA evidence for
  another slate. Ask only for an essential fact unavailable through authorized
  sources, and retain a named blocker when it cannot be established.
- Test a portable copied frozen package and identical-input replay. Exercise
  expired source, ambiguous role, changed inactive status, insufficient policy
  capacity and byte tampering. Record actual commands, environment, timing,
  memory where measurable, hashes, entry count and output paths.
- Publish a concise readiness decision and final Cowork instruction. Keep the
  PowerShell fallback accurate. Do not commit generated evidence or CSV outputs.

Acceptance is split: (1) automated fixture mechanics; (2) actual Cowork/Linux
execution; (3) current real-file/evidence review. Mark each independently.
Windows tests, a launcher check or simulated Linux fixtures cannot substitute
for actual Cowork acceptance. If that environment or essential evidence is
unavailable, retain `BLOCKED`, state the exact missing prerequisite and hand off
the smallest remaining check. All generated outputs remain prior-only.

Non-goals: model certification, automated DraftKings account actions, a deadline
promise or broad new feature development. Repair demonstrated scope-local
acceptance defects; record larger defects as new bounded work.

## Relationship to the full project mandate

| Goal | What this sequence supplies | Work still required afterward |
|---|---|---|
| Volume/current-role integrity | Explicit supported roles, uncertainty handling and conserved kicker/opportunity allocation | Validated forward role/volume model, route/air-yard/high-value-touch and scheme features |
| Reliable sources and context | Versioned, hash-bound role adjustments and current evidence gates | Broader approved telemetry, sharp-book/prop consensus, discrepancy thresholds and validated qualitative mappings |
| True contest ceiling | More accurate inputs and explicit model limitations | W3/W11 participation/event accounting; validated joint tails, scoring bonuses and correlations; strategic stacks and exclusions |
| Ownership and leverage | No new claims | Calibrated ownership, ceiling probabilities, field composition, duplication and W8 economics |
| Portfolio drawdown | Enforced deterministic exposure/overlap preferences | W9 risk-aware allocation on validated joint outcomes and contest economics; measured workload W10 |
| Model and operational readiness | Auditable review and actual environment acceptance | W7 settlement data, W12 temporal validation/registry, sufficient prospective history and all live release gates |

SD1/SD2 are adjacent to W3 but do not finish its simulator mask. SD3/SD4 are a
prior-review subset adjacent to W9, not completion of W8/W9 economics. SD5 helps
W7's operator brief but not settlement capture. SD6 supplies a bounded W5
rehearsal, not full economic/model certification. Preserve the broader backlog.

## Required session protocol and closeout

1. Read `CLAUDE.md`, this tracker, relevant contracts and the latest changelog.
   Inspect current Git state and applicable `AGENTS.md` instructions before edits.
2. Mark the selected row `IN_PROGRESS`; record date, starting HEAD, scope and
   pre-existing changes. Implement only that chunk and necessary integration.
3. Preserve all unrelated edits, raw inputs and prior outputs. No reset, clean,
   stash, broad formatting, dependency upgrades, staging, commit or push unless
   separately authorized. Never use `git add .` or `git add -A`.
4. Reproduce defects where applicable, run relevant checks and the required
   suite in the pinned runtime, and independently inspect final artifacts.
   Report skipped or unrun checks as limitations, not successes.
5. **Update this document before finishing**, including failed or partial work.
   Mark `DONE` only when every acceptance condition is met. Otherwise retain
   `IN_PROGRESS` with a bounded remainder, or `BLOCKED` with the actual external
   dependency. Do not promote the next row while a dependency remains incomplete.
6. Append the completion record below. Update `changelog.md` and the narrow
   current-priority pointer in `backlog.md`; do not mark a larger W/S tranche done
   on the strength of a subset. When done, promote the next dependency-satisfied
   row to `READY` and write its complete prompt under `docs/session-prompts/`.
7. Return changes, exact verification results, remaining blockers, four release
   truths for any generated run, and the next prompt path. If Ben needs to commit,
   provide copy/paste PowerShell using an explicit reviewed path list; never stage
   untracked user artifacts, raw captures, generated workbooks or entry CSVs.

### 2026-09-09 — SD2 implementation session started

Actual start HEAD: `09bb9bdc71359d667aa55273575c4dd14f30bba3`, branch
`codex/s6a-deterministic-projection-producer`. SD1 is now committed, unlike
the SD2 prompt creation snapshot. Tracked files are clean. Preserve untracked
`Claude outputs/`, `docs/session-prompts/W2-expiry-and-selection-objective.md`
and `docs/session-prompts/W4-cowork-prior-only-profile.md`.
Scope: SD2 offensive-role evidence, historical-basis distinctions, deterministic
allocation, request/review integration, regressions and mandatory documentation.
Python 3.13.7 verified. No staging, commit, push, reset, clean, stash, dependency
change or account action is authorized. SD3 remains blocked pending acceptance.

### Completion record template

Copy and fill this section for each session; retain prior records.

```text
Session/date:
Chunk and final status:
Start HEAD / end HEAD (or uncommitted):
Pre-existing changes preserved:
Implemented behavior and changed paths:
Defect reproduction / before-and-after evidence:
Checks: exact commands, runtime, pass/fail/skip counts, durations:
Artifact paths / immutable input and final-output hashes, if applicable:
FILE_VALID / EVIDENCE_STATE / MODEL_STATUS / RELEASE_DECISION, if a run exists:
Acceptance criteria still unmet and precise blockers:
Scope changes / follow-up items:
Next READY chunk and prompt path:
```

### 2026-09-09 — Planning baseline

Created this queue and the SD1 implementation prompt after checking HEAD, working
tree, active scoring/selection/request code and the retained readiness report.
Added navigation to the main backlog and a planning-only changelog entry.
Document link, fence, whitespace and six-row queue checks passed; `git diff
--check` passed. No runtime behavior changed, no test suite rerun, no staging or
commit. SD1 is the next `READY` item; all implementation and live acceptance
remain outstanding.

### 2026-09-09 — SD1 implementation session started

SD1 was moved to `IN_PROGRESS` before code edits. Starting branch/HEAD:
`codex/s6a-deterministic-projection-producer` /
`6b5d4625b6fa3234a07680ca27dafc819fbd05ab`. Scope is limited to the versioned
kicker-role evidence contract, conserved team kicking allocation, bounded
request/review integration, tests and documentation required by SD1.

Pre-existing changes preserved: modified `backlog.md` and `changelog.md`, plus
untracked `Claude outputs/`, this tracker, the SD1 prompt,
`docs/session-prompts/W2-expiry-and-selection-objective.md`, and
`docs/session-prompts/W4-cowork-prior-only-profile.md`. No staging, commit,
push, reset, clean or stash is authorized. This start record will be replaced
or supplemented by the mandatory completion record with actual results.

### 2026-09-09 — SD1 completion record

Session/date: 2026-09-09, Windows local workspace.

Chunk and final status: SD1 `DONE` for its software acceptance. This does not
establish live role evidence, calibrated model quality or upload readiness.

Start HEAD / end HEAD (uncommitted):
`6b5d4625b6fa3234a07680ca27dafc819fbd05ab` /
`6b5d4625b6fa3234a07680ca27dafc819fbd05ab` on
`codex/s6a-deterministic-projection-producer`.

Pre-existing changes preserved: modified `backlog.md` and `changelog.md`; untracked
`Claude outputs/`, this tracker, the SD1 prompt,
`docs/session-prompts/W2-expiry-and-selection-objective.md`, and
`docs/session-prompts/W4-cowork-prior-only-profile.md`. No reset, clean, stash,
staging, commit, push, dependency change, account action or DraftKings action.

Implemented behavior and changed paths: added
`src/nfl_dfs/kicker_roles.py` and `tests/test_kicker_roles.py`; integrated the
contract and conserved scoring through `src/nfl_dfs/prior_score.py`,
`src/nfl_dfs/selection.py`, `src/nfl_dfs/prior_review.py`,
`src/nfl_dfs/cowork.py`, `src/nfl_dfs/cli.py`, and
`src/nfl_dfs/workbook.py`. Updated regression/integration coverage in
`tests/test_prior_selection.py`, `tests/test_prior_review_profile.py`, and
`tests/test_readiness_regressions.py`. Updated `CLAUDE.md`,
`IMPLEMENTATION_STATUS.md`, `docs/DATA_CONTRACTS.md`,
`docs/COWORK_RUNBOOK.md`, `backlog.md`, `changelog.md`, this tracker, and added
`docs/session-prompts/SD2-offensive-roles-and-history.md`.

The new `nfl_kicker_role_evidence_v1` manifest binds the current salary hash,
game/team, exact underlying-person CPT/FLEX identities, content-addressed
captured sources and hashes, approved URI/license/parser policy, observation,
capture and expiry times, transformation version and fixed share tolerance.
Source content must support a qualitative sole role or repeat an exact structured
numerical split. Resolution occurs after every existing exclusion. Ambiguity,
invalidity, staleness, tampering or a newly ineligible positive-share person
fails closed. A one-kicker fallback is visibly `UNKNOWN`; zero-share people are
scoreless and excluded; no eligible kicker receives no fabricated production.
Team scoring events are allocated exactly once before DraftKings scoring and the
Captain multiplier.

Defect reproduction / before-and-after evidence: before the repair,
`tests/test_prior_selection.py::test_two_eligible_kickers_do_not_duplicate_team_kicking_points`
failed with 16.8 combined New England kicker points versus the one-team-line
expectation of 8.4. After the repair, an evidenced 0.625/0.375 split yields
5.25 + 3.15 = 8.4, and each person's CPT row is exactly 1.5 times FLEX. An
unevidenced two-kicker team now stops with `KICKER_ROLE_UNRESOLVED`.

Checks:

- Pre-fix probe: `& .\.venv\Scripts\python.exe -B -m pytest -p
  no:cacheprovider
  tests/test_prior_selection.py::test_two_eligible_kickers_do_not_duplicate_team_kicking_points
  -q` — expected 1 failure, measured 16.8 versus 8.4.
- Final SD1/adjacent focus: `& .\.venv\Scripts\python.exe -B -m pytest -o
  addopts='' -p no:cacheprovider -q tests/test_kicker_roles.py
  tests/test_prior_selection.py tests/test_prior_review_profile.py
  tests/test_readiness_regressions.py` — 104 passed in 15.37 seconds.
- Complete pinned Windows suite: `& .\.venv\Scripts\python.exe -B -m pytest
  -p no:cacheprovider --basetemp
  .\outputs\pytest-sd1-final-60f0e081b34b4d05af7520709eaa6228 --durations=5`
  — 357 passed, 1 skipped in 69.05 seconds. The one skip is the existing Windows
  symlink-creation permission case.
- `& .\nfl.ps1 doctor` — PASS on Python 3.13.7; SQLite integrity `ok`, workbook
  probe cleaned, 8 processors, and no sync/reparse detected. Long paths remain
  disabled as reported environment state.
- `git diff --check` — PASS. SD2 prompt file/link/content self-check — PASS.

Artifact paths / immutable input and final-output hashes: no live slate or
user artifact was executed. Synthetic source-bound Cowork fixtures and their
hash assertions ran inside the isolated pytest base directory above; no
generated CSV/workbook/source capture belongs in a commit.

FILE_VALID / EVIDENCE_STATE / MODEL_STATUS / RELEASE_DECISION: the synthetic
full `cowork-run --profile prior_review` integration asserted `true` / `UNKNOWN`
/ `PRIOR_ONLY` / `DO_NOT_UPLOAD`. It is test evidence, not a live-slate release
decision. No live slate run was generated in this session.

Acceptance criteria still unmet and precise blockers: no SD1 code acceptance
criterion remains. Current approved game-specific kicker-role evidence was not
retrieved, so a live multi-kicker slate still requires a captured, valid package.
The actual Cowork/Linux environment was not run, and the Windows symlink test
remains skipped for OS privilege. Current activity, offensive roles, prospective
model validation, ceiling/ownership/economics and upload certification remain
separate blockers.

Scope changes / follow-up items: none outside necessary request, snapshot,
review reporting, workbook guidance and documentation integration. W3 and all
broad simulator/model tranches remain incomplete. The source allowlist was not
widened.

Next READY chunk and prompt path: SD2 is the sole `READY` item;
`docs/session-prompts/SD2-offensive-roles-and-history.md`.

### 2026-09-09 — SD2 completion record

Session/date: 2026-09-09, local Windows workspace, Python 3.13.7 with the existing
locked environment. SD2 is `DONE` for software acceptance. No live slate was run.

Start HEAD / end HEAD: `09bb9bdc71359d667aa55273575c4dd14f30bba3` /
`09bb9bdc71359d667aa55273575c4dd14f30bba3`, branch
`codex/s6a-deterministic-projection-producer`; SD2 remains uncommitted. Unlike
the SD2 prompt's creation snapshot, SD1 was already committed at session start.
Tracked files were initially clean. Preserved all pre-existing untracked work:
`Claude outputs/`, `docs/session-prompts/W2-expiry-and-selection-objective.md`
and `docs/session-prompts/W4-cowork-prior-only-profile.md`. No staging, commit,
push, reset, clean, stash, dependency upgrade or account action was performed.
The existing Git global-ignore permission warning was left unchanged.

Implemented behavior:

- Added the adjacent `nfl_offensive_role_evidence_v1` package. It shares SD1's
  captured-source policy, content addressing, hashes, time and confinement
  checks, while preserving SD1 compatibility. Numerical declarations bind exact
  salary/game/team/person/CPT/FLEX identities and all five team share groups.
  Only matching captured JSON supplies numbers; narrow qualitative facts cannot
  manufacture shares. The offensive excerpt bound accommodates a full team.
- Historical counts and efficiency now use current-team rows through the frozen
  provider crosswalk. Missing/blank counts and incompatible transfers retain
  explicit unknown basis and `EVIDENCE_STATE=UNKNOWN` placeholders. Old-team
  counts never enter a new-team denominator. Legacy frozen packages without SD2
  coverage must be rebuilt. This exception is Showdown-only; Classic's previous
  non-PASS rejection is preserved and tested.
- Reports distinguish `OBSERVED_HISTORY_ZERO`, `MISSING_HISTORY`,
  `CURRENT_ROLE_UNKNOWN`, `EXPLICIT_NONPARTICIPATION` and
  `SOURCE_SUPPORTED_ADJUSTMENT`, with one finding per offensive person. They
  retain history, exact IDs, before/after shares, assumptions, coverage, explicit
  unallocated volume and smallest next evidence action. An unresolved after
  basis is `null`, never an asserted adjusted zero.
- Salary, official inactive and operator exclusions take precedence. An excluded
  positive recipient invalidates the allocation. Unresolved missing history or
  a material change blocks selection; observed zero is excluded from selection.
  Unchanged positive history is only an unconfirmed diagnostic, with excluded
  volume unallocated. No unsupported proportional redistribution or snap-cap
  ceiling remains in prior-review/standalone prior selection. Legacy generic
  helpers and the simulator are outside this change.
- Cowork/CLI requests, immutable snapshots, copied-package replay, scoring and
  selection reports carry the new artifact. Final source/manifest/expiry/history
  checks prevent a newly written review CSV on failure; prior outputs survive.
  The real freeze/project/select/export integration also exposed and repaired
  `LAR`/`LA` scoring-input lookup through the existing exact frozen team map.

Changed paths (reviewed, not staged):

```text
src/nfl_dfs/offensive_roles.py
src/nfl_dfs/opportunity.py
src/nfl_dfs/priors.py
src/nfl_dfs/projection.py
src/nfl_dfs/prior_score.py
src/nfl_dfs/selection.py
src/nfl_dfs/prior_review.py
src/nfl_dfs/cowork.py
src/nfl_dfs/cli.py
src/nfl_dfs/workbook.py
tests/test_offensive_history.py
tests/test_offensive_roles.py
tests/test_offensive_role_integration.py
tests/test_priors_adapter.py
tests/test_prior_review_profile.py
CLAUDE.md
IMPLEMENTATION_STATUS.md
docs/DATA_CONTRACTS.md
docs/COWORK_RUNBOOK.md
docs/SHOWDOWN_PRIORITY_TRACKER_2026-09-09.md
docs/session-prompts/SD3-portfolio-control-contract.md
backlog.md
changelog.md
```

Defect reproduction / numerical evidence:

- The initial `tests/test_offensive_history.py` regressions failed 3/3 in 0.50s:
  missing and observed-zero rows lacked distinct machine-readable basis, and a
  transferred receiver incorrectly retained `0.535714` target weight from his
  old team. Those same cases now pass, with the transferred record excluded
  from current-team weights and a named current-role blocker at selection.
- The promoted-backup fixture records before/after carry shares `0.15 -> 0.75`
  against unchanged historical capacity `0.20`. Captured allocations conserve
  all five team share totals, before scoring and the exactly-once 1.5x Captain
  multiplier. An explicit 0.25 unallocated carry fraction remains unallocated.
- Full real-code synthetic integration initially exposed
  `TEAM_SPLIT_COVERAGE_MISSING:LAR:2025`; the exact frozen LA/LAR crosswalk repair
  now passes original and portable replay, with identical final CSV bytes.
- Final local diff/artifact review checked identity/position masks, exclusion
  precedence, source-only numbers, version/Classic boundaries, unknown reporting,
  team-sized captures, original expiry, source hashes, output preservation and
  release truths. No unresolved SD2 software finding remains.

Verification (all commands from the repository root):

- Pre-fix: `& .\.venv\Scripts\python.exe -B -m pytest -o addopts='' -p
  no:cacheprovider tests/test_offensive_history.py -q --basetemp
  outputs/pytest-sd2-prefixed-20260909` — expected 3 failures in 0.50s.
- Broad focused regressions: `& .\.venv\Scripts\python.exe -B -m pytest -o
  addopts='' -p no:cacheprovider tests/test_offensive_history.py
  tests/test_offensive_roles.py tests/test_offensive_role_integration.py
  tests/test_prior_selection.py tests/test_prior_review_profile.py
  tests/test_priors_adapter.py tests/test_readiness_regressions.py -q
  --basetemp outputs/pytest-sd2-focus-final-20260909 --durations=5` —
  177 passed in 60.59s. Log: `outputs/sd2-focus-final-20260909.log`.
- Final review-boundary focus: history/role tests plus the unknown-group
  projection regression — 45 passed in 1.87s. Final whole-team capture check
  included in `tests/test_offensive_roles.py` — 40 passed in 1.77s using
  `-o addopts='' -p no:cacheprovider -q --basetemp
  outputs/pytest-sd2-review-final-20260909`.
- **Final complete suite:** `& .\.venv\Scripts\python.exe -B -m pytest -p
  no:cacheprovider --basetemp outputs/pytest-sd2-closeout-20260909 --durations=5
  --junitxml=outputs/sd2-closeout-20260909.xml` — **416 passed, 1 skipped in
  61.58s**. Log: `outputs/sd2-closeout-20260909.log`. The sole skip is
  `test_request_rejects_symlink_escape_when_supported`, Windows error 1314
  (symlink-creation privilege unavailable). No failing tests.
- Earlier complete checks passed 408/1 in 80.23s and 414/1 in 92.44s; subsequent
  review fixes and added cases are covered by the final result above. Interim
  logs remain in `outputs/sd2-*.log`; they do not replace the final result.
- `& .\nfl.ps1 doctor` — PASS; Python 3.13.7, SQLite integrity `ok`, WAL,
  closed/absent Excel lock, cleaned workbook probe, 8 processors, no detected
  sync/reparse. Long paths remain disabled as an environment fact. Log:
  `outputs/sd2-doctor-20260909.log`.
- `git diff --check` — PASS. All 15 implementation/test hashes matched the
  pre-suite freeze in `outputs/sd2-code-closeout-hashes-20260909.json` after
  testing; documentation-only closeout followed. Queue/prompt/link checks passed.

Retained synthetic artifact evidence is under
`outputs/pytest-sd2-closeout-20260909/test_full_frozen_prior_project0/`:

| Artifact | SHA-256 |
|---|---|
| Salary input | `6094dedbcf06c1ae4030753194bcb5175734888dc2ae6d1655ea0a2fbfb8b6bb` |
| Entry input | `5ab3fc4fe4985803a0d5a8f9e094d5f881e01a859f119881a067b2c397968199` |
| Offensive role manifest | `531732bb516f9031265c09a1e5334634e1feb8e5f55073ae0627533001519316` |
| First and portable-repeat review CSV | `d2a8b9090a8db64cc97ffc00943446f8c43b977d134b8bcc27184737cf3f9d43` |

The two run reports are `outputs/prior-review-test/cowork_run.json` and
`outputs/portable-repeat/cowork_run.json` beneath that fixture root; each retains
all source, history, identity, projection and assignment hashes. Test captures,
CSV/workbook files, logs and other generated outputs are not commit candidates.

Four truths for the successful **synthetic** full-chain run:
`FILE_VALID=true`, `EVIDENCE_STATE=UNKNOWN`, `MODEL_STATUS=PRIOR_ONLY`,
`RELEASE_DECISION=DO_NOT_UPLOAD`. Invalid-role integration runs assert
`FILE_VALID=false`, the same other three truths, no new review CSV and unchanged
earlier output bytes. No live-slate release status is claimed.

Remaining blockers / limits: no SD2 software acceptance criterion remains.
Live approved game-specific numerical offensive-role captures were not obtained;
the deliberately narrow structured numerical source format and exact qualitative
forms remain a live acquisition limitation. Do not synthesize a conforming
capture, invent efficiency or widen expiry to bypass that limitation. Actual
Claude Cowork/Linux was not executed. Live activity/evidence, full forward-role
modeling, W3 simulator participation, ceiling/ownership/economics, portfolio
enforcement and prospective model validation remain open. No broader tranche
was marked done and no upload gate changed.

Next READY chunk: **SD3 only**, with
`docs/session-prompts/SD3-portfolio-control-contract.md`. SD4–SD6 remain blocked.

### 2026-09-09 — SD3 implementation session started

Actual start HEAD: `7f9ae4d200baf624b63ceb001e12eb318010146a`, branch
`codex/sd3-portfolio-control-contract`, created in place from the completed SD2
checkout without changing working-tree bytes. Scope: SD3's versioned
portfolio-policy contract, deterministic validation, exact identity and Entry-ID
bindings, exposure rounding, canonical uniqueness/overlap semantics, request and
immutable-snapshot integration, necessary capacity checks, and explicit refusal
before SD4 enforcement. No selection or enforcement changes are authorized.

Pre-existing changes preserved: the refreshed tracked
`docs/session-prompts/SD3-portfolio-control-contract.md`, plus untracked
`Claude outputs/`, `docs/session-prompts/W2-expiry-and-selection-objective.md`
and `docs/session-prompts/W4-cowork-prior-only-profile.md`. The stale local
remote-tracking reference for the deleted SD2 remote branch was not treated as
remote state. No staging, commit, push, reset, clean, stash, dependency change
or account action is authorized. SD4 remains blocked pending full SD3 acceptance.

### 2026-09-09 — SD3 completion record

Session/date: 2026-09-09, local Windows workspace, pinned Python 3.13.7 and
existing locked dependencies. SD3 is `DONE` for software acceptance. No live
slate, DraftKings action or actual Cowork/Linux run occurred.

Start HEAD / end HEAD: `7f9ae4d200baf624b63ceb001e12eb318010146a` /
`7f9ae4d200baf624b63ceb001e12eb318010146a`, branch
`codex/sd3-portfolio-control-contract`; all SD3 work remains uncommitted and
unstaged. The refreshed tracked SD3 prompt and the pre-existing untracked
`Claude outputs/`, `docs/session-prompts/W2-expiry-and-selection-objective.md`
and `docs/session-prompts/W4-cowork-prior-only-profile.md` were preserved. No
reset, clean, stash, broad formatting, dependency upgrade, stage, commit, push
or account action occurred. The stale local remote-tracking SD2 reference and
the Git global-ignore permission warning were left unchanged.

Implemented behavior:

- Added strict `nfl_showdown_portfolio_policy_v1` parsing and
  `nfl_showdown_portfolio_policy_normalized_v1` output. The contract binds exact
  salary SHA-256, one game, the complete underlying-person/CPT/FLEX identity map
  and the full requested Entry-ID sequence. Numeric fractions require the exact
  `[0,1]` unit; Booleans, numeric strings, nonfinite/negative/out-of-range values,
  duplicate JSON keys, entries, identities and overrides fail closed.
- Exact-decimal `floor(fraction * all_requested_entries)` produces the tested
  2-entry `0.49 -> 0`, `0.50 -> 1`, `1.00 -> 2` and 3-entry `0.66 -> 1`,
  `0.67 -> 2` boundaries. Omitted/null means no added cap, zero remains zero,
  one permits all entries, and exact overrides beat defaults. Captain maxima are
  explicitly tightened to stricter combined-person maxima; policy and existing
  participation/source exclusions take precedence and are reported, never
  relaxed.
- Defined canonical identity as Captain person plus sorted FLEX people, so FLEX
  order is irrelevant and Captain identity matters. Pairwise overlap uses
  underlying-person sets regardless of role; combined exposure counts once per
  person/entry. Necessary slot, Captain, team, salary, uniqueness and pairwise
  capacity checks have named smallest next actions and make no solver
  infeasibility claim.
- Added stable exact-decimal canonical serialization. The source-policy hash
  binds original bytes; the normalized hash equals the normalized file's exact
  bytes. Requests, CLI `--portfolio-policy-json`, path confinement, immutable
  snapshots, generated requests, replay and the staged/status workbook carry the
  artifact. A conflicting `lineup_count` is named rather than silently reducing
  the denominator.
- SD4 enforcement remains deliberately absent. Every policy-bearing production
  request stops at `PORTFOLIO_POLICY_ENFORCEMENT_UNSUPPORTED_SD3` before
  selection/export, leaves no new `DK_REVIEW_ENTRY` CSV, retains earlier outputs,
  and records `enforcement_status=NOT_IMPLEMENTED_SD3`. Policy-free requests
  retain SD1/SD2 behavior. No selection objective, greedy sequence, Captain rule,
  lineup cycling, optimizer constraint or upload gate changed in SD3.

Changed paths (reviewed, not staged):

```text
src/nfl_dfs/portfolio_policy.py
src/nfl_dfs/cowork.py
src/nfl_dfs/cli.py
src/nfl_dfs/workbook.py
tests/test_portfolio_policy.py
CLAUDE.md
IMPLEMENTATION_STATUS.md
docs/DATA_CONTRACTS.md
docs/COWORK_RUNBOOK.md
docs/SHOWDOWN_PRIORITY_TRACKER_2026-09-09.md
docs/session-prompts/SD4-enforce-and-audit-portfolio-controls.md
backlog.md
changelog.md
```

The pre-existing modified
`docs/session-prompts/SD3-portfolio-control-contract.md` remains preserved dirt,
not an SD3 implementation edit from this session.

Verification (all commands from the repository root):

- Initial contract/Cowork focus (`tests/test_portfolio_policy.py`,
  `tests/test_cowork.py`, `tests/test_prior_review_profile.py`) with `-o
  addopts='' -p no:cacheprovider -q` and a unique project-local base: 76 passed,
  1 skipped in 10.04s.
- Broad policy/request/selection/lineup/participation/workbook/APPG regressions:
  120 passed, 1 skipped in 19.13s.
- Review found the normalized writer had appended a byte not covered by its
  reported semantic hash. The writer was repaired so the normalized artifact's
  exact file hash equals `normalized_policy_sha256`, and a regression was added.
  Post-repair contract/Cowork focus: 76 passed, 1 skipped in 10.73s.
- First complete suite used the prompt's long GUID-derived base and recorded
  439 passed, 1 failed, 1 skipped in 94.18s. The sole failure was the existing
  copied-prior-package integration trying to create a 261-character temporary
  source path while doctor reports Windows long paths disabled. The same code
  and test passed in a new short isolated root: 440 passed, 1 skipped in 78.02s.
- **Final complete pinned-runtime suite:** `& .\.venv\Scripts\python.exe -B -m
  pytest -p no:cacheprovider --basetemp outputs\p3c-aade35ce --durations=10
  --junitxml=outputs\sd3-closeout-20260909.xml` — **440 passed, 1 skipped in
  57.57s**. No failures. The sole skip is the existing Windows symlink-creation
  privilege case; this does not prove Linux behavior.
- `& .\nfl.ps1 doctor` — PASS: Python 3.13.7, SQLite integrity `ok`, WAL,
  `CLOSED_OR_ABSENT` Excel lock, cleaned probe, 8 processors, no detected
  sync/reparse; Windows long paths remain disabled. `git diff --check` — PASS.
- Final diff review confirmed no changes to `selection.py`, `optimizer.py`,
  `prior_review.py`, `review_export.py`, field/economics/simulation code,
  dependencies or upload gates. All SD3 acceptance cases and existing no-policy
  regressions passed; no unresolved SD3 software finding remains.

Representative retained synthetic policy-boundary evidence under
`outputs/p3c-aade35ce/test_cowork_policy_is_snapshot0/`:

| Artifact | SHA-256 |
|---|---|
| Exact source policy snapshot | `9ccebfbf27b7f20fc668e0e603ef121892381365eb716f7997b1ff02c7718e63` |
| Exact normalized policy bytes | `5635b472b175c48f0a3e9f61e1bfdbc922aa79ba1f788c92f7b728718ba09d61` |
| Validation report file | `6911adecca9efbc6ab923a53a0b56dce9f27490aae83f486572090f1bedf04eb` |
| Frozen run request | `0410d7f5093a9cb24a4f0b655d0c6dd8fe899f28b921416db54363c46feded44` |
| Cowork result | `17d8a4b2bc4eb6c5b80c04877fd1e3dd6a924ccd3703ef8ba4387214e249c7f1` |

The original policy was deliberately mutated after the first snapshot; copied
replay retained the snapshot source hash and the same normalized hash. The
synthetic policy-bearing execution truthfully records `FILE_VALID=false`,
`EVIDENCE_STATE=UNKNOWN`, `MODEL_STATUS=PRIOR_ONLY`,
`RELEASE_DECISION=DO_NOT_UPLOAD`, stage
`PORTFOLIO_POLICY_ENFORCEMENT_BLOCKED`, and `bulk_entry_csv=null`. No live-run
truths are claimed.

Remaining blockers / limits: no SD3 software acceptance criterion remains.
SD4 must implement bounded joint enforcement and independent final-assignment
audit before a policy-bearing request may reach review export. Actual
Cowork/Linux, live policy authoring, live evidence, modest/large multi-entry
runtime, W3 simulator participation, W8/W9 economics and prospective model
validation remain unverified. No broader tranche or upload gate was marked done.

Next READY chunk: **SD4 only**, with
`docs/session-prompts/SD4-enforce-and-audit-portfolio-controls.md`. SD5 and SD6
remain blocked.

### 2026-09-09 — SD4 implementation session started

Actual start HEAD: `2e045d53afcc5d9f1d2363f09d8778e77f1b4284`, branch
`codex/sd4-enforce-and-audit-portfolio-controls`, created from live verified
`origin/main` after `git fetch --prune origin`. The verified merge commit contains
SD3 implementation commit `e71961485dbfcdae299caaa325c35efc866427cd` and has the
same tree as that implementation commit. Scope is limited to SD4's bounded MILP
joint policy enforcement, exact Entry-ID assignment, named solver/bank outcomes,
and an independent final-assignment policy audit before prior-review export.
Policy-free behavior and every `PRIOR_ONLY` / `DO_NOT_UPLOAD` boundary remain in
force; SD5, field/payout economics, ownership, calibrated drawdown, simulation,
Classic expansion and upload automation are excluded.

Pre-existing changes preserved: modified tracked
`docs/session-prompts/SD4-enforce-and-audit-portfolio-controls.md` (starting
SHA-256 `d964d2e0e79c8ee49076f39b2f8fa2142b32b34481a76e256e5d55c5e3d3a578`),
plus untracked `Claude outputs/`,
`docs/session-prompts/W2-expiry-and-selection-objective.md` and
`docs/session-prompts/W4-cowork-prior-only-profile.md`. The index was empty.
No reset, clean, stash, rebase, pull, broad formatting, dependency change,
staging, commit, push or account action is authorized. SD5 remains blocked
pending every SD4 software acceptance condition.

### 2026-09-09 — SD4 implementation complete

SD4 is `DONE` for software acceptance. Start and end HEAD remained
`2e045d53afcc5d9f1d2363f09d8778e77f1b4284` on
`codex/sd4-enforce-and-audit-portfolio-controls`; all SD4 changes remain
uncommitted and the index remains empty. The refreshed SD4 prompt is preserved
at its starting SHA-256
`d964d2e0e79c8ee49076f39b2f8fa2142b32b34481a76e256e5d55c5e3d3a578`.
Untracked `Claude outputs/`,
`docs/session-prompts/W2-expiry-and-selection-objective.md` and
`docs/session-prompts/W4-cowork-prior-only-profile.md` remain preserved.

Implemented bounded, deterministic Showdown policy enforcement in new
`src/nfl_dfs/portfolio_enforcement.py`, with integration changes in
`src/nfl_dfs/selection.py`, `src/nfl_dfs/optimizer.py`,
`src/nfl_dfs/prior_review.py`, `src/nfl_dfs/review_export.py`,
`src/nfl_dfs/portfolio_policy.py`, `src/nfl_dfs/cowork.py` and
`src/nfl_dfs/cli.py`. New `tests/test_portfolio_enforcement.py` and expanded
`tests/test_portfolio_policy.py` cover joint feasibility where greedy selection
misses, repeated Captain permission/excess, combined CPT/FLEX caps, overlap
zero through six, canonical duplicates, exact no-cycling assignment, complete-
bank infeasibility versus incomplete/exhausted/time/search/error states,
tampered summaries, byte mutation and Cowork replay. Operating changes are
documented in `CLAUDE.md`, `IMPLEMENTATION_STATUS.md`,
`docs/DATA_CONTRACTS.md`, `docs/COWORK_RUNBOOK.md`, `backlog.md` and
`changelog.md`; the complete SD5 prompt is
`docs/session-prompts/SD5-readable-artifact-bound-review.md`.

Policy-bearing Showdown `prior_review` now applies SD3's exact integer maxima
across a bounded actual candidate bank, chooses all requested assignments in one
MILP and permits a repeated Captain only when the explicit policy permits it.
Exact Entry IDs are assigned once each without cycling. Immediately before
export, an independent audit reparses the normalized policy and assignment
artifact, recomputes legality, canonical identity, combined/Captain counts,
uniqueness and every pairwise overlap from roster IDs, and binds exact salary,
entry, source-policy, normalized-policy and assignment bytes. Any failed or
unknown solve/audit, changed bytes, incomplete assignment or policy on an
unsupported profile is a named blocker and writes no new review CSV. Policy-free
selection behavior is unchanged.

Review found and repaired three material issues. A 128-candidate default exhausted
the 30-second generation budget in the synthetic integration fixture, so the
declared default is now 32 candidates and coverage is explicitly incomplete.
The initial CLI integration could validate then silently ignore a policy on a
non-`prior_review` profile; it now blocks with
`PORTFOLIO_POLICY_PROFILE_UNSUPPORTED_SD4`. A pre-audit assignment-byte mutation
was also exercised and correctly produced a failed audit with no review CSV.
Final review then caught that the auditor compared normalized bytes to the
selector's policy object without reparsing the artifact itself; the auditor now
strictly reparses canonical normalized bytes and uses those independently read
entry IDs, salary binding, limits, uniqueness and overlap controls.

Verification on Windows with pinned Python 3.13.7 and locked dependencies:

- Focused SD4 plus related selection/policy/Cowork regressions: 116 passed in
  44.86s.
- Broader optimizer/lineup/prior-review/CLI/Cowork regressions: 225 passed,
  1 skipped in 111.25s. The skip is the existing Windows symlink-privilege case.
- Post-review normalized-policy artifact-reparse focus: 59 passed in 17.95s.
- Complete pinned-runtime suite using isolated
  `outputs/p4-final2-8c72`: 475 passed, 1 skipped in 71.33s, with JUnit output at
  `outputs/sd4-final2-20260909.xml`.
- `nfl.ps1 doctor` passed: Python 3.13.7, SQLite integrity `ok`, WAL mode,
  8 processors, 11,306,254,336 available bytes, no Excel lock or sync/reparse
  finding; Windows long paths remain disabled.
- Final `git diff --check` passed; no-index whitespace checks for the three new
  SD4/SD5 source, test and prompt files emitted no whitespace errors.

The representative two-entry policy run built 32 distinct canonical candidates,
reported `CANDIDATE_LIMIT_REACHED_INCOMPLETE`, selected 2 assignments with
`OPTIMAL` scoped to `ACTUAL_CANDIDATE_BANK`, passed the independent audit and
replayed identical review bytes. Source-policy SHA-256 was
`9ccebfbf27b7f20fc668e0e603ef121892381365eb716f7997b1ff02c7718e63`,
normalized-policy SHA-256 was
`5635b472b175c48f0a3e9f61e1bfdbc922aa79ba1f788c92f7b728718ba09d61`,
assignment SHA-256 was
`f192e1db2ed23027b7814a51ba523362977fea5c9b2cda97a4e35e8b41e93d7e`,
and review CSV SHA-256 was
`ccdda7307687335825ea71aca4f8e6ae6e38c95e0825dadc2d02899ab8a5a338`.
Its four independent truths were `FILE_VALID=true`,
`EVIDENCE_STATE=UNKNOWN`, `MODEL_STATUS=PRIOR_ONLY` and
`RELEASE_DECISION=DO_NOT_UPLOAD`.

The declared five-entry fixture also built 32 canonical candidates, truthfully
reported `CANDIDATE_LIMIT_REACHED_INCOMPLETE`, and selected all 5 entries with
`OPTIMAL` scoped to the actual bank. Candidate generation took 2.361s; joint
selection took 0.013s with zero reported MIP gap and one node. Peak process
working set was 66,797,568 bytes. These measured 2- and 5-entry fixtures do not
establish complete-slate feasibility, 20-entry support or 150-entry support.

No SD4 software acceptance criterion remains. Actual Cowork/Linux execution,
live policy authoring, current game evidence, larger portfolios, prospective
model quality, field/payout economics, ownership, calibrated drawdown, W3
simulator participation, Classic expansion and upload automation remain
unverified or out of scope. Enforced and audited output is still only
`PRIOR_ONLY / DO_NOT_UPLOAD`; no DraftKings account action occurred.

Next READY chunk: **SD5 only**, with
`docs/session-prompts/SD5-readable-artifact-bound-review.md`. SD6 remains blocked.
