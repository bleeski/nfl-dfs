# Next-session prompt — SD2 offensive roles and missing history

Implement **SD2 only** in `C:\Users\benja\Documents\Claude\nfl-dfs`. Carry the
bounded work through implementation, regression tests, review and tracker
update; do not stop at a plan. The operating workflow remains two files attached
in Claude Cowork (salary CSV and reserved-entry CSV), followed by a request for
a Showdown portfolio. Supporting evidence must be obtained and frozen by the
workflow, not invented or requested as a user-authored numerical CSV.

Read first:

- `CLAUDE.md` and any applicable `AGENTS.md`.
- `docs/SHOWDOWN_PRIORITY_TRACKER_2026-09-09.md`, especially SD2 and its
  closeout protocol. This is the active six-chunk sequence.
- `docs/session-prompts/SD1-current-role-and-kicker-scoring.md` and the completed
  SD1 record, to preserve its exact-ID, source, expiry, snapshot and reporting
  boundaries.
- `changelog.md`, `backlog.md`, `docs/READINESS_REVIEW_2026-09-09.md`,
  `docs/DATA_CONTRACTS.md`, `docs/COWORK_RUNBOOK.md`, `IMPLEMENTATION_STATUS.md`
  and the relevant opportunity/role sections of `plan.md`.

## Starting state and safeguards

At SD2 prompt creation, the branch is
`codex/s6a-deterministic-projection-producer`, HEAD
`6b5d4625b6fa3234a07680ca27dafc819fbd05ab`; SD1 is implemented but uncommitted.
Its final Windows verification was 357 passed, 1 skipped in 69.05 seconds on
Python 3.13.7. The skip was the existing Windows symlink-permission case. Verify
the actual current state rather than copying this snapshot into the closeout.

Preserve every existing change. In particular, do not overwrite or discard the
uncommitted SD1 implementation, the modified backlog/changelog, the untracked
priority/session documents, `Claude outputs/`, or the older W2/W4 session
prompts. No reset, clean, stash, checkout of an old HEAD, broad formatting,
dependency upgrade, staging, commit, push or account action. Never use
`git add .` or `git add -A`. Use the pinned Python 3.13.7 runtime and locked
dependencies.

Before code edits, mark SD2 `IN_PROGRESS` and record the date, actual start HEAD,
scope and pre-existing dirt in the priority tracker. Resolve routine reversible
implementation choices yourself within SD2.

## Defects to reproduce

Inspect the actual current `priors.py`, `projection.py`, `opportunity.py`,
`participation.py`, `prior_score.py`, `selection.py` and prior-review flow before
adopting these findings:

1. Prior-season opportunity rows can make a currently promoted backup retain his
   former backup workload, and the existing generic redistribution is not a
   source-supported current-role model.
2. A rookie or newly introduced current-slate player without prior-season
   support can be conflated with an observed zero. Missing history is an unknown
   basis, not a zero projection.
3. A player who changed teams can carry an old-team historical basis into a new
   team without an explicit current-team role declaration.

Add small failing regressions that demonstrate the actual current behavior
numerically and in the machine-readable findings. Do not rely on whichever six
players the solver happens to choose. Preserve supplied bytes and byte-sensitive
fixtures.

## Required implementation

1. Extend SD1's evidence approach with the smallest versioned offensive-role
   contract that fits the current architecture. Bind the exact salary SHA-256,
   game/team, underlying person and current exact DraftKings FLEX/CPT identities,
   captured source artifacts and hashes, source URI, observation/capture/expiry
   times, transformation version, and the precise declared role fact. Reuse the
   existing content-addressed package and source-policy validation; do not create
   an allowlist bypass or accept a bare URL/timestamp as evidence.
2. Represent and report these states distinctly for every affected offensive
   person: `OBSERVED_HISTORY_ZERO`, `MISSING_HISTORY`, `CURRENT_ROLE_UNKNOWN`,
   `EXPLICIT_NONPARTICIPATION`, and `SOURCE_SUPPORTED_ADJUSTMENT`. Choose exact
   serialized names once, document them, and do not silently map one state to
   another. Synthetic evidence is test-only and must stay visibly labelled.
3. Accept a numerical opportunity adjustment only when captured source content
   explicitly supports that number through a validated deterministic
   transformation. Qualitative evidence may establish bounded facts such as a
   named starter/backup or a material unresolved change, but prose alone cannot
   invent carry, target, route, red-zone, touchdown or snap shares.
4. Resolve current roles after salary status, official inactive and operator
   exclusions. Evidence cannot reactivate an excluded person. An inactive or
   removed source-supported recipient invalidates the declared allocation and
   requires refreshed evidence; never transfer volume automatically to an
   unsupported backup.
5. Apply supported adjustments before scoring and conserve each declared team
   opportunity total. Normalize or redistribute only inside the explicit
   declaration and eligible current-team group. Do not cap a promoted player at
   historical `role_capacity`, silently use an old-team denominator, infer a
   starter from salary, or manufacture an equal split. Record before/after
   shares and any deliberately unallocated volume.
6. A material current-role change without adequate evidence, a missing
   historical basis, or an incompatible transfer must produce one precise named
   finding per affected person with the smallest next evidence action. Decide
   and test which conditions block selection versus permit only a clearly
   understated diagnostic; never allow an unresolved player to become a
   zero-valued punt or let missingness manufacture `PASS`.
7. Thread the artifact and findings through `CoworkRunRequest`, CLI/request
   handling, confinement, immutable snapshots, copied-package replay,
   prior_review, selection/scoring reports and final hash/freshness checks.
   Preserve the two-CSV intake: Cowork discovers or prepares the auxiliary role
   package, updates the generated request, and reruns. If SD1's
   `role_evidence_json` should remain kicker-specific, introduce one clearly
   named adjacent field; if it is safely generalized, version that change and
   retain SD1 compatibility.
8. Add minimal operator guidance and machine-readable coverage/assumption
   reporting. Leave the polished lineup/exposure presentation to SD5. Invalid or
   ambiguous evidence must leave a truthful named blocker and no newly written
   `DK_REVIEW_ENTRY` CSV. Preserve prior outputs.

## Acceptance and testing

Run focused regressions first, then the complete pinned-runtime suite, doctor and
whitespace check. Cover at least:

- A promoted backup with source-supported opportunity, with conserved team
  totals and no historical-cap ceiling.
- A rookie/current-slate person with no history, proving missing is distinct
  from observed zero and cannot silently score as established zero.
- A transferred player whose old-team history cannot enter a new-team
  denominator without an explicit current-team binding.
- Explicit nonparticipation and official inactive/operator exclusions taking
  precedence over every role declaration.
- Exact CPT/FLEX person identity; unknown/wrong-team IDs; duplicate/conflicting
  declarations; malformed, nonfinite, negative or invalid-total shares.
- Qualitative-only evidence refusing numerical adjustments; valid numerical
  source content conserving the declared carry/target/touchdown groups.
- Future/stale sources, changed source/manifest bytes, path escape, and expiry
  during selection all failing with named reports and no review CSV.
- Request round-trip, immutable snapshots, copied-package replay, deterministic
  repeat, and full `cowork-run --profile prior_review` integration using clearly
  labelled synthetic fixtures.
- One current-role finding per affected person and visible before/after basis,
  assumption, coverage and unallocated-volume reporting.
- Generated output retaining `FILE_VALID`, `EVIDENCE_STATE`, `MODEL_STATUS` and
  `RELEASE_DECISION` independently. Current-role evidence must not promote
  `MODEL_STATUS` beyond `PRIOR_ONLY` or change `DO_NOT_UPLOAD`.
- DraftKings APPG mutations remaining unable to affect any numerical output.

Windows full-suite pattern:

```powershell
Set-Location -LiteralPath 'C:\Users\benja\Documents\Claude\nfl-dfs'
$sd2TestRoot = Join-Path (Get-Location) ('outputs\pytest-sd2-' + [guid]::NewGuid().ToString('N'))
& .\.venv\Scripts\python.exe -B -m pytest -p no:cacheprovider --basetemp $sd2TestRoot
if ($LASTEXITCODE -ne 0) { throw 'SD2 full test suite failed. Diagnose before continuing.' }
& .\nfl.ps1 doctor
if ($LASTEXITCODE -ne 0) { throw 'SD2 doctor check failed.' }
git diff --check
if ($LASTEXITCODE -ne 0) { throw 'Whitespace check failed.' }
```

In Cowork/Linux use its pinned environment and `nfl.sh`; do not reuse the
Windows `.venv`. Record the actual environment. Windows results do not establish
Linux acceptance. Live approved numerical offensive-role evidence is not
required to prove the gate and transformations; if it cannot be obtained,
document that live limitation and keep readiness blocked.

## Scope and release boundaries

Do not start SD3-SD6. No portfolio-policy definition or enforcement, simulator
or field/economics rewrite, ownership/leverage work, new strategy constraints,
calibration/promotion, Classic extension, broad depth-chart scraper, dependency
upgrade or upload-gate change. Do not mark W3 complete: SD2 does not add the
simulator participation mask or finish the full current-role model.

Keep numerical work local and deterministic. Do not use DraftKings APPG,
freehand model values, widened expiry or fuzzy runtime identity. This remains a
prior-only review generator: `MODEL_STATUS=PRIOR_ONLY` and
`RELEASE_DECISION=DO_NOT_UPLOAD`. DraftKings login, editing, upload and money
actions remain manual.

## Mandatory closeout

Before finishing, update `docs/SHOWDOWN_PRIORITY_TRACKER_2026-09-09.md` with
SD2's actual final status and append the complete session record: date,
start/end HEAD, changed paths, preserved dirt, reproduced defects, exact
commands/results/timings/skips, relevant hashes, unmet criteria, live-evidence
limits and next action. Update `changelog.md` and the current-priority pointer in
`backlog.md`. Do not mark W3 or another broad tranche done.

Mark SD2 `DONE` only if every software acceptance condition passes. If done,
make SD3 the sole next `READY` queue item and create
`docs/session-prompts/SD3-portfolio-control-contract.md` with the same
self-contained safeguards and tracker-update obligation. Otherwise keep SD3
blocked and record SD2's smallest remaining chunk.

Final response: summarize repaired behavior, exact verification, limitations,
updated tracker and next prompt. Report the four truths for any generated run;
do not invent a run status if no slate was executed. Do not stage or commit. If
a user-side commit is requested, provide an explicit reviewed path list,
staged-diff inspection and commit command; never include generated artifacts,
source captures, entry CSVs or unrelated user files.
