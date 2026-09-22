# C2 session prompt — Classic policy, candidates, and joint portfolio selection

Work in `C:\Users\benja\Documents\Claude\nfl-dfs`.

Complete only authoritative backlog chunk **C2 — Classic policy, candidates,
and joint portfolio selection**. Do not begin C3 readable review, independent
export audit, or exact-template export. Do not begin quantitative Q2-Q5 model,
ownership, field, duplication, payout, or EV work.

## Start safely

1. Read all applicable `AGENTS.md` files, `CLAUDE.md`, the authoritative queue
   and C1/C2 sections of `backlog.md`, `IMPLEMENTATION_STATUS.md`, `changelog.md`,
   `docs/DATA_CONTRACTS.md`, and the current Cowork/operator runbooks.
2. Inspect the branch, full HEAD, `main`, `origin/main`, status, and diff before
   edits. Preserve every existing tracked/untracked/generated/user-owned file.
   Never reset, clean, stash, rebase, broadly format, or use `git add .`/`-A`.
3. Confirm C1 is `DONE`, C2 is the sole `READY` item, and the current baseline
   still passes. The reviewed C1 handoff reported 555 collected tests: 554 passed
   and 1 skipped. Reconcile any drift rather than assuming it.
4. After the baseline is safe, use branch
   `codex/c2-classic-policy-candidates-portfolio`. Do not stage, commit, push,
   open a PR, or merge without separate authorization.
5. Change C2 from `READY` to the sole `IN_PROGRESS` item at implementation
   start. Leave C3 and every later item `BLOCKED` until all C2 acceptance passes.

## Preserve C1 exactly

C1 extends the shared frozen prior/projection path to multi-game Classic and
publishes canonical `nfl_classic_prior_review_selection_c1_v1` and
`nfl_classic_slate_coverage_c1_v1` JSON. It requires immutable exact-ID inputs,
fresh selected-player activity, source-supported selected offensive roles,
per-game weather/expiry controls, and remains
`MODEL_STATUS=PRIOR_ONLY / RELEASE_DECISION=DO_NOT_UPLOAD`. It emits no Classic
assignment, `DK_REVIEW_ENTRY`, or `DK_UPLOAD` CSV. Do not weaken these gates,
reuse APPG, widen expiry, accept fuzzy identity, impute shares, or route Classic
through production field/economics functions. Preserve Showdown behavior and all
Q1 settlement/metric-registration contracts.

## Objective

Replace C1's sequential exact-lineup no-good selection with an explicit,
versioned, exact-bound Classic preference policy, a deterministic bounded
candidate bank, and joint one-lineup-per-Entry-ID portfolio assignment. This is
a governed prior-only review portfolio, not a calibrated tournament strategy or
an upload package.

## Required implementation

### Classic policy contract

- Define a versioned Classic policy schema bound to exact salary and entry
  SHA-256 values, draft group, complete game/team/person/position/roster-slot
  identity, ordered exact Entry IDs, selection objective/version, and all
  integer limits.
- Support explicit player, team, and game exposure bounds; exact exclusions;
  group constraints; canonical lineup uniqueness; pairwise person overlap; and
  registered Classic stack rules. State whether each construction preference is
  hard or advisory. Never silently relax a hard bound.
- Normalize and persist canonical policy bytes. Validate types, domains,
  necessary capacity, identity coverage, contradictory bounds, source-policy
  hash, normalized-policy hash, and input mutation before selection.

### Deterministic candidate bank

- Generate multiple documented Classic construction strata/families, including
  coverage around policy-capped people and a policy-feasible chain before top-K
  objective fill. Use the existing legal Classic MILP and exact IDs; do not add
  field, ownership, duplication, payout, or EV scoring.
- Make seed/tie-breaking deterministic. Record requested/produced candidates,
  canonical uniqueness, family and policy coverage, termination reason, solver
  status, time, nodes and gap where available, and peak memory.
- Distinguish exhaustive completion, bounded completion, timeout, solver error,
  structural infeasibility, modeled-bank infeasibility, and incomplete-bank
  exhaustion. Never call a bounded candidate bank full-slate optimal.

### Joint portfolio assignment

- Select and assign exactly one unique legal lineup to every exact reserved
  Entry ID in template order under every effective integer bound.
- Enforce combined-person/team/game/group/stack counts, canonical uniqueness,
  and every pairwise overlap constraint jointly. Do not cycle a shorter lineup
  list across entries.
- Independently reparse the canonical normalized policy and recompute legality,
  identities, counts, stack/group rules, overlap, Entry-ID coverage/order, and
  every bound from selected roster IDs before accepting the C2 selection
  artifact.
- Re-hash salary, entries, priors, projections, current evidence, source policy,
  normalized policy, candidate bank, and assignment artifact at the applicable
  boundaries. Mutation fails closed and publishes no accepted portfolio.

### C1/C3 boundary

- C2 may extend the versioned machine-readable Classic selection artifact and
  coverage/limitations report with policy, bank, assignment, and independent
  audit facts.
- C2 must not create a DraftKings-shaped assignment CSV, readable HTML/workbook
  redesign, `DK_REVIEW_ENTRY_*.csv`, or `DK_UPLOAD_*.csv`. C3 owns those outputs.
- Keep `FILE_VALID`, `EVIDENCE_STATE`, `MODEL_STATUS=PRIOR_ONLY`, and
  `RELEASE_DECISION=DO_NOT_UPLOAD` independent and prominent.

## Required tests and verification

Add golden and adversarial tests for feasible 1-, 3-, 20-, and 150-entry
policies; all supported bound types; stack/group semantics; deterministic family
coverage and replay; exact Entry-ID order; uniqueness and overlap; conflicting
or impossible policies; incomplete banks; modeled-bank infeasibility; timeout,
non-optimal and solver-error states; source/normalized-policy/input/candidate/
assignment mutation; selected unavailable/current-evidence stops; no upload CSV;
Showdown regression; and proof that field, ownership, duplication, payout,
economics, production portfolio selection, and C3 exporters are unreachable.

Run focused C1/C2/Classic/Showdown tests, then the complete pinned suite using a
new short workspace-local `--basetemp` and separate cache (Windows long paths are
disabled), `./nfl.ps1 doctor`, compile/import checks for every changed module,
`git diff --check`, deterministic repeated-run and mutation checks, runtime and
peak-memory measurements for 1/3/20/150 entries, and an adversarial complete-diff
review.

## Closeout

Update `backlog.md`, `changelog.md`, `IMPLEMENTATION_STATUS.md`,
`docs/DATA_CONTRACTS.md`, and affected Cowork/operator docs. Mark C2 `DONE` and
make C3 the sole `READY` item only if every applicable acceptance criterion
passes; otherwise leave C2 `IN_PROGRESS` or `BLOCKED` with the smallest exact
remaining blocker. Create the complete C3 next-session prompt only after C2 is
truly done.

Finish with starting/ending branch and full hashes; exact files changed;
implementation decisions and rejected alternatives; focused/full test results;
doctor, compile/import, whitespace, replay, mutation, adversarial and benchmark
results; limitations/blockers; the four independent release truths; the sole
next `READY` item; and an explicit reviewed path allowlist for a later commit.
Do not stage, commit, push, open a PR, or merge.
