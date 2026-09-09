# Next-session prompt — SD1 kicker roles and scoring

Implement **SD1 only** in `C:\Users\benja\Documents\Claude\nfl-dfs`. Carry the
bounded work through implementation, regression tests, review and tracker update;
do not stop at a plan. The operating workflow is two files attached in Claude
Cowork (salary CSV and reserved-entry CSV), followed by a request for a Showdown
portfolio. Supporting role evidence should be obtained/prepared by the workflow,
not invented or required as a third user-authored numerical CSV.

Read first:

- `CLAUDE.md` and any applicable `AGENTS.md`.
- `docs/SHOWDOWN_PRIORITY_TRACKER_2026-09-09.md`, especially SD1 and its closeout
  protocol. This is the current sequence for these six priority chunks; older
  W/S backlog next-task notes do not replace it.
- `changelog.md`, `backlog.md`, `docs/READINESS_REVIEW_2026-09-09.md`.
- Relevant sections of `plan.md`, `docs/DATA_CONTRACTS.md`,
  `docs/COWORK_RUNBOOK.md` and `IMPLEMENTATION_STATUS.md`.

## Starting state and safeguards

At prompt creation, the branch was
`codex/s6a-deterministic-projection-producer`, HEAD
`6b5d4625b6fa3234a07680ca27dafc819fbd05ab` (Harden Showdown review workflow and live
preflight). Tracked files were clean. Existing untracked work included
`Claude outputs/`, `docs/session-prompts/W2-expiry-and-selection-objective.md` and
`docs/session-prompts/W4-cowork-prior-only-profile.md`. The new priority documents
may also be uncommitted. Verify the actual current state; preserve every existing
change. Do not check out an old HEAD or assume this snapshot is still current.

No reset, clean, stash, broad formatting, dependency upgrades, staging, commit,
push or account action. No `git add .` or `git add -A`. Use the configured pinned
runtime, Python 3.13.7 and locked dependencies. The last recorded full Windows
suite was 332 passed, 1 skipped in 63.06 seconds; the skip was symlink permission.
That is a historical baseline to verify, not a result to copy into your closeout.

Mark SD1 `IN_PROGRESS` and record starting state before code edits. Resolve normal
implementation choices yourself within this scope. Do not ask permission for
routine reversible changes needed to complete SD1.

## Defect to reproduce

Inspect `src/nfl_dfs/prior_score.py:score_pool`. Its K branch currently builds
the full team kicking stat line separately for each eligible kicker. Two eligible
kickers can therefore both receive all projected team kicking production.
`role_capacity` is a historical mean offensive snap share; zero is normal for
a kicker and cannot establish inactivity or select a starting kicker.

Inspect the actual current code before adopting the finding. Add a small failing
regression with two eligible kickers on the same team, exact CPT/FLEX identities,
known team kicking volume and known scoring splits. Verify the incorrect
allocation numerically; do not rely on whether the final solver happens to pick
both kickers. Preserve raw supplied inputs and existing byte-sensitive fixtures.

## Required implementation

1. Introduce a minimal versioned kicker-role evidence contract. Reuse suitable
   existing identity/provenance types where their semantics fit. It must bind the
   current salary SHA-256, game/team, underlying person resolved through exact
   current DraftKings IDs, and captured supporting source artifacts with hashes,
   source URI, observation time, capture time, expiry and transformation version.
   Do not treat a bare URL or a new timestamp as evidence. Document the schema
   and what a source must establish before it can declare a sole kicker or a
   numerical split. Follow `sources.py` for retrieval; no allowlist bypasses.
2. Validate declarations strictly: unique person/team-role bindings, known
   current-slate IDs, CPT/FLEX identity consistency, finite nonnegative shares
   and a declared team allocation totaling one within an explicit tolerance.
   Reject conflicting, malformed, future, expired, wrong-team, hash-mismatched
   or unbound declarations. A qualitative source can establish a sole role only
   when its captured content supports that fact; prose does not supply invented
   fractional shares. Synthetic evidence is for tests and must be labelled so.
3. Evaluate roles after existing salary, official inactive and operator
   exclusions. Role evidence must never reactivate an excluded person. Where
   multiple kickers remain eligible and no supported role allocation is supplied,
   stop selection with a named error such as `KICKER_ROLE_UNRESOLVED` and a
   precise next evidence action. Do not pick by salary, infer starter from salary
   status, silently divide evenly, or infer inactivity from zero offensive snaps.
4. With exactly one eligible kicker and no supplied artifact, retain compatibility
   only as an explicitly recorded prior-only sole-listed assumption. This does
   not prove a confirmed role or official ACTIVE status. A supplied invalid role
   artifact must fail, even if that fallback could otherwise apply. With no
   eligible kicker, allocate no production to a nonexistent player and report
   that gap; legal K-free lineups may still proceed diagnostically.
5. Allocate the existing team kicker projection exactly once across supported
   recipients. Specify whether you allocate the team score or scoring events;
   preserve total team points and avoid accidentally applying nonlinear scoring
   or the Captain multiplier twice. Zero-share kickers are excluded from this
   selection path. An inactive declared starter or invalidated share set requires
   refreshed role resolution, not automatic transfer to an unsupported backup.
   Apply CPT 1.5 only after the underlying person's base allocation.
6. Thread the auxiliary artifact through `CoworkRunRequest`, CLI/request input
   handling, path confinement, immutable snapshots, prior_review, selection and
   score reporting. A suggested field name is `role_evidence_json`; choose and
   document one consistent name after inspecting the contracts. Preserve the
   two-CSV intake experience: discover or prepare the role artifact through the
   documented evidence step and rerun the generated request when necessary.
7. Preserve portability and time semantics. Capture and hash every consumed
   artifact, resolve it from a copied immutable package without original external
   paths, retain original source expiry through derivation, and check hashes and
   freshness again immediately before review export. Historical replay clocks
   must not make a live run appear current or renew expired evidence.
8. Add role-allocation/assumption/coverage findings to the existing machine-readable
   reports and minimal operator instructions. Leave the polished review report
   for SD5. Failure must retain a named blocker and truthful run result; no new
   `DK_REVIEW_ENTRY` CSV is written for invalid/ambiguous role evidence. Preserve
   earlier outputs rather than deleting unrelated files.

Likely integration areas are `prior_score.py`, `participation.py`,
`selection.py`, `prior_review.py`, `cowork.py`, `cli.py`, a focused new role-contract
module, relevant tests and data/runbook documentation. This is a scope guide,
not an instruction to edit all these files or a reason to ask permission for
necessary adjacent wiring. Avoid a general source-ledger or projection rewrite.

## Acceptance and testing

Run focused regressions first, then the complete pinned-runtime suite and doctor.
Tests should establish behavior across module boundaries, not mirror helpers.
Cover at least:

- The pre-fix two-kicker defect; sole declared kicker; supported split conserving
  total team points; two unresolved eligible kickers blocked; no eligible kicker.
- One eligible kicker without external role evidence is visibly only an
  assumption; invalid supplied evidence cannot fall back silently.
- Captain score exactly 1.5 times the same person's FLEX score and person
  uniqueness across slots; zero-share and inactive people never selected.
- Zero offensive snap share does not imply kicker inactivity; a late inactive
  change affecting the supported allocation requires fresh role resolution.
- Unknown/wrong-team IDs, duplicate/conflicting declarations, invalid totals,
  NaN/infinite/negative values, future/stale observations, changed source bytes,
  path escapes and expiry during selection all fail with truthful artifacts.
- Request round-trip, immutable snapshots, copied-package replay and full
  `cowork-run --profile prior_review` integration with synthetic fixtures.
- Generated review output retains `FILE_VALID`, `EVIDENCE_STATE`, `MODEL_STATUS`
  and `RELEASE_DECISION` independently; missing role/activity evidence cannot
  manufacture `PASS`, and model status remains prior-only even with valid roles.

For Windows, the following is a copyable full-suite pattern that avoids the
previous inaccessible system-temp issue. Use the current working checkout.

```powershell
Set-Location -LiteralPath 'C:\Users\benja\Documents\Claude\nfl-dfs'
$sd1TestRoot = Join-Path (Get-Location) ('outputs\pytest-sd1-' + [guid]::NewGuid().ToString('N'))
& .\.venv\Scripts\python.exe -B -m pytest -p no:cacheprovider --basetemp $sd1TestRoot
if ($LASTEXITCODE -ne 0) { throw 'SD1 full test suite failed. Diagnose before continuing.' }
& .\nfl.ps1 doctor
if ($LASTEXITCODE -ne 0) { throw 'SD1 doctor check failed.' }
git diff --check
if ($LASTEXITCODE -ne 0) { throw 'Whitespace check failed.' }
```

If running in Cowork/Linux, use its own pinned environment and `nfl.sh`; do not
reuse the Windows `.venv`. Record the actual environment and exact commands.
Do not claim a Linux acceptance run from Windows results. Live retrieval is not
required to prove the regression fix; if current approved role evidence cannot
be obtained, document that limitation and keep live role readiness blocked.

## Scope and release boundaries

Do not start SD2–SD6. No offensive-role model, simulator/field/economics work,
portfolio objectives or caps, new strategy constraints, calibration/promotion,
Classic extension, broad refactor or dependency upgrade. Do not widen expiry,
weaken exact-ID checks, use DraftKings APPG, fabricate model values or change
upload gates. Keep numerical work local and deterministic.

This is a prior-only review generator. Keep `MODEL_STATUS=PRIOR_ONLY` and
`RELEASE_DECISION=DO_NOT_UPLOAD`; valid bytes do not prove evidence or model
quality. Never transfer generated assignments into manual-guardrail certification
to bypass the model gate. DraftKings login, entry edits, upload and money actions
remain manual. Completing SD1 does not complete current-role modeling or make
the system a calibrated GPP/portfolio engine.

## Mandatory closeout — update the tracking document

Before finishing, update
`docs/SHOWDOWN_PRIORITY_TRACKER_2026-09-09.md` with SD1's actual status and append
a completion record: date, starting/ending HEAD, changed paths, preserved dirt,
defect reproduction, exact commands/results/timings/skips, artifact hashes where
applicable, unmet acceptance criteria, live evidence limitations and next action.
Do this even if the work fails or remains partial. Mark SD1 `DONE` only when all
its code acceptance conditions pass; distinguish this from live slate readiness.

Update `changelog.md` and the current-priority pointer in `backlog.md`. Do not
mark W3 or other broad tranches complete. If SD1 is done, make SD2 the sole next
`READY` item in this queue and create
`docs/session-prompts/SD2-offensive-roles-and-history.md` with a self-contained
bounded implementation prompt and the same tracker-update obligation. If SD1
is incomplete, record its smallest remaining chunk and keep SD2 blocked.

Final response: summarize the repaired behavior, verification and limitations;
link the updated tracker and next prompt. Report the four truths for any run you
generated, without inventing a run status if no slate was executed. Do not stage
or commit. If a user-side commit is needed, give exact copy/paste PowerShell
instructions with only the reviewed changed paths, followed by staged-diff
inspection and the commit command. Never include user artifacts or generated
CSV/workbook/source captures in the commit list.
