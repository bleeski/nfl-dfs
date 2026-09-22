# C3 session prompt — Classic audit, readable review, export, and scale acceptance

Work in `C:\Users\benja\Documents\Claude\nfl-dfs`.

Complete only authoritative backlog chunk **C3 — Classic audit, review, export,
and scale acceptance**. Do not begin C4 current-real-slate rehearsal, C5 Classic
late swap, or any Q2-Q5 quantitative, ownership, field, duplication, payout,
economics, or EV work.

## Start safely

1. Read all applicable `AGENTS.md` files, `CLAUDE.md`, the authoritative queue
   and C2/C3 sections of `backlog.md`, `IMPLEMENTATION_STATUS.md`, `changelog.md`,
   `docs/DATA_CONTRACTS.md`, the C2 session prompt, and the current
   Cowork/operator runbooks.
2. Inspect the branch, full HEAD, `main`, `origin/main`, status, and complete
   diff before edits. Preserve every existing tracked, untracked, generated,
   and user-owned file, including the separate `codex/qa-work-preservation`
   branch. Never reset, clean, stash, rebase, broadly format, or use
   `git add .`/`git add -A`.
3. Begin only after the reviewed C2 implementation is present on the current
   merged `main`. Confirm C2 is `DONE`, C3 is the sole `READY` item, the C2
   golden/replay/mutation tests pass, and the full pinned baseline is green.
   Reconcile drift rather than assuming it.
4. After the baseline is safe, use branch
   `codex/c3-classic-audit-review-export`. Do not stage, commit, push, open a
   pull request, or merge without separate authorization.
5. Change C3 from `READY` to the sole `IN_PROGRESS` item at implementation
   start. Leave C4, C5, and Q2 onward `BLOCKED` until all C3 acceptance passes.

## Preserve C1 and C2 exactly

C1 owns immutable multi-game intake, frozen priors/projections, exact identity,
participation, selected activity/current-role evidence, weather/expiry gates,
and the no-policy compatibility artifacts. C2 owns the canonical Classic
policy, deterministic bounded candidate bank, joint exact Entry-ID assignment,
and independent selection audit. Preserve direct integer semantics, hard versus
advisory rules, no cycling, exact ordered Entry IDs, all mutation stops, and the
distinction between bounded-bank optimality and full-slate optimality.

C2 output remains `MODEL_STATUS=PRIOR_ONLY /
RELEASE_DECISION=DO_NOT_UPLOAD` and contains no DraftKings-shaped assignment,
`DK_REVIEW_ENTRY`, or `DK_UPLOAD` CSV. Do not weaken current evidence, reuse
APPG, accept fuzzy identity, impute shares, relax a hard bound, or route Classic
through production field/economics functions. Preserve Showdown behavior and
all Q1 settlement/metric-registration contracts.

## Objective

Turn an accepted C2 machine-readable portfolio into a human-verifiable Classic
review package and an exact-template review CSV only after a new downstream
independent audit reconciles every authoritative byte and semantic fact. Prove
registered behavior at 1, 3, 20, and 150 entries on the full supplied
24-team/719-person fixture. This remains a prior-only review package, not a
calibrated tournament strategy or upload authorization.

## Required implementation

### Downstream independent export audit

- Independently read and strictly reparse the immutable salary and entry CSVs,
  source and normalized C2 policy, candidate bank, C2 assignment, C2 selection
  audit, selection report, complete-slate coverage, and proposed review-export
  bytes. Do not accept producer in-memory objects as the audit authority.
- Re-hash every artifact at intake, before review rendering, immediately before
  export, and after the final write. Bind all expected hashes and refuse source,
  normalized-policy, candidate, assignment, audit, selection, coverage,
  template, or proposed-output mutation.
- Recompute exact mode/draft group/game/team/person/position/roster-slot
  identity, ordered Entry-ID coverage, blank-cell authority, every selected
  roster's eligibility/salary/two-game rule, all C2 hard counts and stack/group
  semantics, exact exclusions, canonical uniqueness, every pairwise overlap,
  selected current-evidence facts, and unchanged non-roster template bytes.
- Keep this audit independent of the C2 producer/audit implementation. Any
  byte, schema, identity, evidence, policy, assignment, selection, or export
  disagreement must withhold all new review/export artifacts and name the
  smallest exact next action.

### Readable Classic review

- Extend the existing artifact-bound readable JSON, self-contained escaped
  HTML, and workbook pattern to Classic without changing Showdown output.
- Show every exact Entry ID in template order; slot, exact DK ID, underlying
  person, team/opponent/game, salary, lineup salary, prior-only central estimate,
  player/team/game/group/stack counts and limits, uniqueness, pairwise overlap,
  current activity/role evidence, exclusions, unallocated volume, source paths,
  hashes, candidate-bank completion/status, joint solve status, audit status,
  and all four release truths.
- Make bounded-bank scope and every limitation prominent. Do not label the
  prior score as ceiling, leverage, EV, ROI, win probability, cash probability,
  edge, calibrated ownership, or validated performance.
- Preserve HTML escaping and workbook formula-injection defenses. Render and
  inspect every workbook sheet and every HTML/PDF page at readable scale; no
  clipped columns, hidden blockers, ambiguous IDs, raw active formulas, or
  contradictory status labels may remain.

### Exact-template review export

- Only downstream audit `PASS` may create a new
  `DK_REVIEW_ENTRY_<label>.csv`. Rewrite only the nine blank roster cells for
  each exact authorized Entry ID using exact C2 assignment order and DraftKings
  IDs. Preserve BOM/encoding, header, line endings, row order, quoting, physical
  line geometry, unrelated rows, contest facts, and every non-roster byte.
- Independently reparse and byte-diff the final file, verify its SHA-256, and
  bind it into the readable review/run record. A partial write, stale file,
  mismatched Entry ID, prefilled cell, unauthorized row, mutation, audit
  failure, or post-write disagreement must remove/withhold the new review CSV.
- Never create `DK_UPLOAD_*.csv`, never certify upload, and never touch a
  DraftKings account. Manual review remains outside the engine.

### Scale and copied-package acceptance

- Run registered 1-, 3-, 20-, and 150-entry C2 policies against the full
  supplied 24-team/719-person Classic fixture. Record candidate requested and
  produced counts, bank status/completeness, family/policy coverage, solve
  status, elapsed time, nodes, gap, process peak RSS and traced Python peak
  memory for each scale.
- Register explicit time/RSS limits before accepting results. Report each scale
  as `PASS`, `FEASIBLE_LIMIT`, `CANDIDATE_BANK_INCOMPLETE`, or a named failure;
  never infer 150-entry readiness from a smaller case.
- Copy the complete immutable package to a different short workspace-local
  path and rerun. Source and copied runs must produce byte-identical canonical
  policy, bank, assignment, audit, selection, coverage, readable JSON/HTML, and
  exact-template review CSV hashes. Runtime-only metrics must stay outside
  canonical bytes.

## Required tests and verification

Add golden and adversarial tests for 1/3/20/150 exact Entry-ID export order;
full-fixture identity and scale; legal rosters and hard policy recomputation;
blank-cell authority and non-roster byte preservation; copied-package replay;
candidate/assignment/audit/selection/coverage/template/output mutation at every
boundary; partial/stale/unauthorized/prefilled exports; selected unavailable or
current-role evidence stops; incomplete/timeout/non-optimal/solver/audit states;
HTML injection; workbook formula injection; readable-display reconciliation;
no `DK_UPLOAD`; Showdown regression; and proof that field, ownership,
duplication, payout/economics, production portfolio selection, C4/C5, and Q2-Q5
paths are unreachable.

Run focused C1/C2/C3/Classic/Showdown tests, then the complete pinned suite using
a new short workspace-local `--basetemp` and separate cache because Windows long
paths are disabled. Run `./nfl.ps1 doctor`, compile/import checks for every
changed module, `git diff --check`, deterministic source-versus-copy replay,
all mutation matrices, native workbook open/recalculate/save/reopen QA,
independent rendered workbook/HTML inspection, exact final-byte diff, the full
registered 1/3/20/150 runtime/RSS/memory matrix, and an adversarial complete-diff
review.

## Closeout

Update `backlog.md`, `changelog.md`, `IMPLEMENTATION_STATUS.md`,
`docs/DATA_CONTRACTS.md`, and affected Cowork/operator docs. Mark C3 `DONE` and
make C4 the sole `READY` item only if every applicable acceptance criterion
passes; otherwise leave C3 `IN_PROGRESS` or `BLOCKED` with the smallest exact
remaining blocker. Create the complete C4 next-session prompt only after C3 is
truly done.

Finish with starting/ending branch and full hashes; exact files changed;
implementation decisions and rejected alternatives; focused/full test results;
doctor, compile/import, whitespace, replay, mutation, render, native workbook,
byte-diff, adversarial, and full-fixture benchmark results; limitations/
blockers; the four independent release truths; the sole next `READY` item; and
an explicit reviewed path allowlist for a later commit. Do not stage, commit,
push, open a PR, or merge.
