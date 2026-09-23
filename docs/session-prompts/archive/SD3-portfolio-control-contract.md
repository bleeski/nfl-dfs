# Next-session prompt — SD3 portfolio-control contract

Implement **SD3 only** in `C:\Users\benja\Documents\Claude\nfl-dfs`.
Carry the bounded work through implementation, focused regressions, full tests,
review and mandatory tracker updates. Do not stop at a plan. Execute only when
SD2 is `DONE` and SD3 is the sole next `READY` item in the priority tracker.

The operating surface remains two CSV attachments in Claude Cowork: DraftKings
salaries and reserved entries. Supporting role/history evidence is obtained and
frozen by the workflow. Portfolio preferences are explicit user controls; they
are not a substitute for evidence or a claim about optimal tournament risk.

## Read first

- `CLAUDE.md` and every applicable `AGENTS.md`.
- `docs/SHOWDOWN_PRIORITY_TRACKER_2026-09-09.md`, especially SD3, the SD2
  completion record and the mandatory closeout protocol.
- `docs/session-prompts/SD2-offensive-roles-and-history.md`.
- `backlog.md`, `changelog.md`, `IMPLEMENTATION_STATUS.md`,
  `docs/DATA_CONTRACTS.md`, `docs/COWORK_RUNBOOK.md` and relevant `plan.md`
  portfolio/control sections.
- Actual `cowork.py`, CLI request handling, `selection.py`, `optimizer.py`,
  `review_export.py` and related tests before adopting design assumptions.

## Actual baseline and Git safeguards

Baseline refreshed and verified on 2026-09-09: SD2 commit
`7f9ae4d200baf624b63ceb001e12eb318010146a` was merged through
[PR #5](https://github.com/bleeski/nfl-dfs/pull/5). GitHub `main` is at merge
commit `a8363de237bad78d35150b1febbd4a036a8278a7`; the remote branch
`codex/sd2-offensive-roles-and-history` was deleted. The local checkout remains
on that SD2 branch at `7f9ae4d200baf624b63ceb001e12eb318010146a`. Tracked files
were clean before this prompt refresh; this refreshed prompt may itself be an
uncommitted change. Do not assume local `main` is synchronized or recreate the
deleted remote branch. Recheck actual HEAD, branch, index and working-tree
state before editing, and verify the checkout contains completed SD2.

SD2's final Windows suite was 416 passed, 1 skipped in 61.58s; doctor and
whitespace checks passed. The skip was Windows symlink privilege. These are
SD2 baseline results, not SD3 verification. Consult the SD2 completion record
for exact commands, hashes and changed paths.

Preserve **every** existing change, including this refreshed prompt, any new
source/test/documentation edits, the tracker and prompts, `Claude outputs/`,
`docs/session-prompts/W2-expiry-and-selection-objective.md` and
`docs/session-prompts/W4-cowork-prior-only-profile.md`. Preserve all supplied
bytes, byte-sensitive fixtures, source captures and prior outputs. No reset,
clean, stash, checkout of an old HEAD, broad formatting, dependency upgrade,
staging, commit, push or account action. Never use `git add .` or `git add -A`.

Before code edits, mark SD3 `IN_PROGRESS` and record date, actual starting HEAD,
scope and existing dirt in the priority tracker. Use pinned Python 3.13.7 and
locked dependencies. Resolve routine reversible SD3 choices yourself.

## Required SD3 implementation

1. Create a small versioned portfolio-policy contract, bound to exact salary
   SHA-256, single-game identity and exact requested Entry IDs. Define maximum
   combined-person exposure across CPT/FLEX, maximum Captain exposure, maximum
   pairwise underlying-person overlap and canonical lineup uniqueness. Preserve
   supported explicit person exclusions and source/participation precedence.
2. State percentage units unambiguously. Prefer explicit fractions in `[0,1]`,
   rejecting bare ambiguous percentages and numeric strings. The denominator
   is **all requested entries**. Convert to integer maxima by
   `floor(fraction * entry_count)` using exact decimal arithmetic. A two-entry
   0.49 cap is zero, 0.50 is one and 1.00 is two; never round up a zero cap.
   At three entries, 0.66 allows one and 0.67 allows two. Test these boundaries.
3. Define default versus per-person override precedence, omitted versus zero
   versus 100% behavior, and contradictions. Captain count is a subset of the
   combined-person count. Define whether contradictory declared maxima are
   rejected or normalized into an explicitly reported effective constraint;
   never silently relax a stricter control. Use exact current person/CPT/FLEX
   identity, not a name match or salary-based inference.
4. Define canonical lineup identity precisely: Captain identity matters, FLEX
   order does not. Pairwise overlap compares the sets of underlying people
   regardless of role. Combined exposure counts a person once per entry.
5. Implement deterministic normalization, stable policy serialization/hash and
   necessary capacity checks with precise named findings and smallest next
   actions. Necessary feasibility checks are not a proof that a feasible
   portfolio exists; do not claim solver infeasibility without its proof.
6. Thread the policy artifact through request parsing/round-trip, CLI input,
   path confinement and immutable snapshots. Bind all requested entry IDs,
   not a selected subset or silently reduced lineup count. Replays must bind
   the same salary/person identities and policy bytes.
7. **SD3 defines and validates the contract; SD4 implements enforcement.**
   A production execution request supplying the new controls must explicitly
   stop with a named unsupported-policy/enforcement blocker and no newly written
   `DK_REVIEW_ENTRY` CSV. Validation can return a normalized policy/report, but
   no success message may imply that the selector enforced it. Existing requests
   without the new policy should preserve their current behavior.
8. Document examples and future Captain repetition semantics. Repeated Captains
   will be governed by explicit maxima in SD4, rather than an implicit demand
   that every entry have a different Captain. Do not change current selection
   objectives, greedy selection, lineup cycling or enforcement in SD3.

Keep numerical parsing, identity, integer limits, hashes and checks local and
deterministic. Do not add calibrated drawdown, ownership, EV, field modeling or
economics claims. Do not weaken SD1/SD2 source, freshness, missing-history,
exclusion or role gates to obtain a legal lineup.

## Acceptance and verification

Cover at least malformed units/types, Booleans/nonfinite/negative values,
out-of-range fractions, unknown IDs, conflicting CPT/FLEX identities, duplicate
entries/overrides, contradictory constraints, missing/default/zero/100% caps,
two- and three-entry rounding, combined-person/Captain aggregation, canonical
uniqueness, overlap bounds, policy hash stability, input mutation, path escape,
request round-trip, copied-package replay and necessary capacity blockers.

Test the full Cowork prior-review boundary: a supplied validated but unenforced
policy is refused explicitly, earlier outputs survive, no new review CSV is
written, and the four truths remain independent. Existing requests without
policy must retain SD1/SD2 behavior. APPG cannot influence any numerical result.

Run focused tests first, then the complete pinned-runtime suite, doctor and
whitespace check. Use a new isolated test directory each time:

```powershell
Set-Location -LiteralPath 'C:\Users\benja\Documents\Claude\nfl-dfs'
$sd3TestRoot = Join-Path (Get-Location) ('outputs\pytest-sd3-' + [guid]::NewGuid().ToString('N'))
& .\.venv\Scripts\python.exe -B -m pytest -p no:cacheprovider --basetemp $sd3TestRoot
if ($LASTEXITCODE -ne 0) { throw 'SD3 suite failed. Diagnose before continuing.' }
& .\nfl.ps1 doctor
if ($LASTEXITCODE -ne 0) { throw 'SD3 doctor failed.' }
git diff --check
if ($LASTEXITCODE -ne 0) { throw 'Whitespace check failed.' }
```

Record actual environment, exact commands, pass/fail/skip counts and timing.
The existing Windows symlink-permission skip does not prove Linux acceptance.
Actual Cowork/Linux uses its own pinned runtime and `nfl.sh`; never reuse the
Windows `.venv` or label Windows tests as Linux verification.

## Scope boundaries and mandatory closeout

Do not implement SD4–SD6, portfolio enforcement, candidate-bank redesign,
joint allocation, simulator participation, ownership/economics, new strategy
constraints, calibration, Classic extension or upload-gate changes. W3, W8 and
W9 remain broader unfinished work. DraftKings login, edits, upload and money
actions remain manual. All generated runs stay `PRIOR_ONLY / DO_NOT_UPLOAD`.

Before finishing, update `docs/SHOWDOWN_PRIORITY_TRACKER_2026-09-09.md`,
`backlog.md` and `changelog.md` with actual status and results, including date,
start/end HEAD, changed paths, preserved dirt, exact verification and timing,
hashes, review findings, unmet criteria and live/environment limitations.
Mark SD3 `DONE` only when every software acceptance condition passes. If done,
make SD4 the sole next `READY` item and create
`docs/session-prompts/SD4-enforce-and-audit-portfolio-controls.md` with the same
self-contained safeguards and mandatory tracker-update obligation. Otherwise
keep SD4 blocked and record SD3's smallest remaining chunk.

Final response: repaired behavior, exact verification, limitations, updated
tracker and next prompt. Report `FILE_VALID`, `EVIDENCE_STATE`, `MODEL_STATUS`
and `RELEASE_DECISION` for any generated run; do not invent live run status.
Do not stage or commit.
