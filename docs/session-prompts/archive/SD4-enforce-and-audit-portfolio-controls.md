# Next-session prompt — SD4 enforce and audit portfolio controls

Implement **SD4 only** in `C:\Users\benja\Documents\Claude\nfl-dfs`.
Carry the bounded work through implementation, focused regressions, full tests,
review and mandatory tracker updates. Do not stop at a plan. Execute only when
SD3 is `DONE` and SD4 is the sole next `READY` item in
`docs/SHOWDOWN_PRIORITY_TRACKER_2026-09-09.md`.

The operating surface remains two CSV attachments in Claude Cowork. The SD3
policy is an explicit user-control contract, not current evidence, model
validation, calibrated drawdown or a profitability claim. SD4 may generate a
prior-only review CSV only after it has enforced and independently re-audited
every supplied policy control. It does not authorize an upload.

## Read first

- `CLAUDE.md` and every applicable `AGENTS.md`.
- `docs/SHOWDOWN_PRIORITY_TRACKER_2026-09-09.md`, especially SD4, the SD3
  completion record and the mandatory closeout protocol.
- `docs/session-prompts/SD3-portfolio-control-contract.md`.
- `backlog.md`, `changelog.md`, `IMPLEMENTATION_STATUS.md`,
  `docs/DATA_CONTRACTS.md`, `docs/COWORK_RUNBOOK.md` and relevant `plan.md`
  portfolio/control sections.
- Actual `portfolio_policy.py`, `cowork.py`, CLI request handling,
  `selection.py`, `optimizer.py`, `prior_review.py`, `lineups.py`,
  `review_export.py` and related tests before adopting design assumptions.

## Actual SD3 baseline and Git safeguards

SD3 implementation commit
`e71961485dbfcdae299caaa325c35efc866427cd` was merged on 2026-09-09. A live
read-only remote check after the merge verified GitHub `main` at
`2e045d53afcc5d9f1d2363f09d8778e77f1b4284` and confirmed that
`refs/heads/codex/sd3-portfolio-control-contract` no longer exists remotely.
Treat that merge commit as the expected SD4 base, but recheck the live remote
and ancestry before editing. The final SD3 pinned Windows suite was 440 passed
and 1 skipped in 57.57s. The skip was the existing Windows symlink-creation
privilege case. Doctor and `git diff --check` passed. A first full run under a
261-character GUID-derived path failed one copied-package test at the disabled
Windows long-path boundary; the same test passed in both subsequent short-path
complete runs. This is an environment limitation, not Linux/Cowork acceptance.

SD3 added `src/nfl_dfs/portfolio_policy.py` and
`tests/test_portfolio_policy.py`, request/CLI/path/snapshot/workbook integration,
and the documented `nfl_showdown_portfolio_policy_v1` contract. It currently
blocks every policy-bearing execution at
`PORTFOLIO_POLICY_ENFORCEMENT_UNSUPPORTED_SD3` and writes no new
`DK_REVIEW_ENTRY` CSV. Source-policy bytes and the exact canonical normalized
bytes have separate SHA-256 values; the normalized hash equals the normalized
file's exact bytes. Requests without a policy retain SD1/SD2 behavior.

Recheck actual HEAD, branch, index and working-tree state before editing. At
this handoff the local checkout still uses the now-merged local branch
`codex/sd3-portfolio-control-contract` at the SD3 implementation commit, its
deleted remote branch is still present only as stale local tracking metadata,
and local `main`/`origin/main` metadata is stale. The index is empty. Preserve
**every** existing change, including this refreshed tracked SD4 prompt and the
untracked `Claude outputs/`,
`docs/session-prompts/W2-expiry-and-selection-objective.md` and
`docs/session-prompts/W4-cowork-prior-only-profile.md`. Do not edit, delete or
absorb those unrelated untracked paths into SD4.

Use a fetch rather than a pull to refresh remote metadata. Verify that live
`main` still contains `e71961485dbfcdae299caaa325c35efc866427cd`, then create
or use local branch `codex/sd4-enforce-and-audit-portfolio-controls` from the
verified `origin/main` while carrying the refreshed prompt and all unrelated
dirt unchanged. If ancestry or checkout safety cannot be established, stop
with the exact Git blocker rather than rebasing, merging, stashing or
overwriting anything. Preserve supplied bytes, byte-sensitive fixtures, prior
outputs and generated evidence. No reset, clean, stash, broad formatting,
dependency upgrade, staging, commit, push or account action. Never use
`git add .` or `git add -A`.

Before code edits, mark SD4 `IN_PROGRESS` and record the date, actual starting
HEAD/branch, scope and all existing dirt in the priority tracker. Use pinned
Python 3.13.7 and locked dependencies. Resolve routine reversible SD4 choices
yourself.

## Required SD4 implementation

1. Connect the validated SD3 normalized policy to prior-only candidate
   generation and **joint** selection/assignment across every requested Entry
   ID. Enforce effective combined-person counts across CPT/FLEX, effective
   Captain counts, policy exclusions, configured maximum pairwise
   underlying-person overlap and canonical lineup uniqueness. Preserve all
   DraftKings legality, salary, team, status, official-inactive, operator,
   kicker-role and offensive-role gates.
2. Use the SD3 exact integer maxima without reparsing floats, rounding up a zero
   cap, substituting a subset denominator or relaxing any user control. Source
   and participation exclusions remain stricter. The selector must consume the
   exact snapshotted salary/person identities, source-policy bytes, normalized
   policy bytes and full requested Entry-ID sequence already validated by SD3.
3. Replace the current implicit forced-distinct-Captain behavior **only for a
   supplied policy** with explicit Captain maxima. A repeated Captain is legal
   when the effective policy cap permits it. Preserve policy-free behavior.
4. Remove silent cycling of fewer selected lineups across more requested entries
   for policy-bearing runs. The output assignment must cover the exact requested
   Entry IDs once each. Duplicate, missing, extra, reordered/subset or partial
   assignments are named blockers, never partial success.
5. Use deterministic bounded MILP selection over the actual candidate bank, not
   a greedy approximation. Retain projection-led `PRIOR_ONLY` scoring; do not add
   field, payout, ownership, duplication, EV or drawdown objectives. Persist the
   solve status, time/budget, candidate counts, canonical counts and coverage.
   Prove and report infeasibility only when the optimization model establishes
   it for the complete modeled bank. Candidate-bank exhaustion, incomplete bank,
   time limit, solver error or search limit must have separate named states and
   must not be called full-slate mathematical infeasibility.
6. After final Entry-ID assignment and immediately before review export, run an
   independent policy audit from exact roster IDs and the normalized artifact.
   Independently recompute legality, canonical identities, combined-person and
   Captain counts, uniqueness and every pairwise overlap. Do not trust selector
   summaries, success flags or cached exposure counts. Bind the audit to exact
   salary, entry, source-policy, normalized-policy and assignment hashes.
7. Replace `PORTFOLIO_POLICY_ENFORCEMENT_UNSUPPORTED_SD3` only after both the
   selector and independent audit pass. A valid policy plus failed/unknown audit,
   timeout, bank exhaustion, tampered summary, stale/mutated input or any other
   blocker leaves no newly generated `DK_REVIEW_ENTRY` CSV and preserves earlier
   outputs. Policy-free requests retain existing behavior.
8. Keep all outputs `MODEL_STATUS=PRIOR_ONLY` and
   `RELEASE_DECISION=DO_NOT_UPLOAD`. A legal, enforced, independently audited
   review file is still not a certified upload package and makes no EV, ROI,
   win/cash probability, ownership, edge or drawdown claim.

## Acceptance and verification

Cover at least:

- A deterministic fixture where the current greedy sequence misses a feasible
  joint portfolio but the bounded MILP finds it.
- An allowed repeated Captain under an explicit Captain maximum, and a rejected
  Captain excess.
- Combined-person aggregation across CPT/FLEX and an exact cap violation.
- SD3's two- and three-entry floor boundaries, including a zero cap that stays
  zero.
- Canonical duplicates with reordered FLEX slots, same-person-set/different-CPT
  overlap, and configured overlap from zero through six.
- Exact full Entry-ID coverage; duplicate, missing, extra, subset and partial
  assignments; no cycling.
- Necessary-capacity failure versus proven modeled-bank infeasibility versus
  candidate-bank exhaustion, incomplete bank, timeout and solver error.
- A tampered selector exposure/overlap summary caught by the independent audit.
- Salary/person/policy/assignment mutation, path confinement, copied-package
  replay, stable hashes and deterministic repeated output bytes.
- Full Cowork prior-review integration: successful enforcement reaches a legal,
  byte-audited review CSV with the four independent truths; every failed policy
  run preserves earlier outputs and writes no new review CSV.
- Existing no-policy SD1/SD2 behavior and APPG quarantine.

Rehearse the existing exact two-entry synthetic fixture and a declared modest
multi-entry fixture. Record candidate-bank size, entry count, solver status,
runtime and memory where available. Do not claim support for 20 or 150 maximum
entries without actually testing those exact sizes under the registered budget.

Run focused tests first, then the complete pinned-runtime suite, doctor and
whitespace check. Windows long paths are disabled on the measured host, so use
a new short isolated project-local directory each time:

```powershell
Set-Location -LiteralPath 'C:\Users\benja\Documents\Claude\nfl-dfs'
$sd4Id = [guid]::NewGuid().ToString('N').Substring(0,8)
$sd4TestRoot = Join-Path (Get-Location) ('outputs\p4-' + $sd4Id)
& .\.venv\Scripts\python.exe -B -m pytest -p no:cacheprovider --basetemp $sd4TestRoot
if ($LASTEXITCODE -ne 0) { throw 'SD4 suite failed. Diagnose before continuing.' }
& .\nfl.ps1 doctor
if ($LASTEXITCODE -ne 0) { throw 'SD4 doctor failed.' }
git diff --check
if ($LASTEXITCODE -ne 0) { throw 'Whitespace check failed.' }
```

Record actual environment, exact commands, pass/fail/skip counts, timings,
candidate/entry sizes, solver statuses and artifact hashes. The Windows skip and
passing Windows suite do not establish actual Cowork/Linux acceptance. Actual
Cowork/Linux uses its own pinned runtime and `nfl.sh`; never reuse `.venv` there.

## Scope boundaries and mandatory closeout

Do not implement SD5 or SD6, redesign the review UI, add W8/W9 field economics,
ownership/duplication estimates, probabilistic drawdown, new strategy controls,
candidate-bank completeness claims, large-field benchmarking, simulator
participation, calibration, Classic extension or upload-gate changes. W3, W8 and
W9 remain broader unfinished work. DraftKings login, edits, upload and money
actions remain manual.

Before finishing, update `docs/SHOWDOWN_PRIORITY_TRACKER_2026-09-09.md`,
`backlog.md` and `changelog.md` with actual status and results, including date,
start/end HEAD, changed paths, preserved dirt, exact verification/timing, solver
states, hashes, review findings, unmet criteria and live/environment limitations.
Update `CLAUDE.md`, `IMPLEMENTATION_STATUS.md`, `docs/DATA_CONTRACTS.md` and
`docs/COWORK_RUNBOOK.md` wherever enforced operating behavior changes.

Mark SD4 `DONE` only when every software acceptance condition passes. If done,
make SD5 the sole next `READY` item and create its complete self-contained prompt
under `docs/session-prompts/`, with the same Git safeguards and mandatory tracker
obligation. Otherwise keep SD5 blocked and record SD4's smallest remaining chunk.

Final response: enforced behavior, independent audit behavior, exact verification,
measured supported sizes, limitations, updated tracker and next prompt. Report
`FILE_VALID`, `EVIDENCE_STATE`, `MODEL_STATUS` and `RELEASE_DECISION` for every
generated run; do not invent live status. Do not stage or commit.
