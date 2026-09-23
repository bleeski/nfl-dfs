# NFL DFS master roadmap

The single authoritative queue for every piece of remaining engineering work.
Every open task, defect and initiative lives in one row of the table in §2. If
something is not in that table, it has been retired in §3. Status lives here and
nowhere else. `changelog.md` holds the evidence for each status change (exact
test counts, hashes, timings), and chunk briefs in `docs/chunks/` hold the
detailed specifications the cards cite.

Created 2026-09-22 by Session 00 from the 2026-09-22 deadline-delivery QA audit
(issue #40, audited at `f8c6942`), the archived backlog, and every tracker,
retrospective and session prompt in the repository.

## 1. Next Session Quick-Start

Paste this into a fresh Claude Code session:

> Read `docs/ROADMAP.md` and execute Session 04 exactly as its card in §2.3 specifies, after `python3 scripts/claim.py take S04`, on the branch your session was assigned or `claude/s04-baseline-command`. Run the card's verification command and then the full suite (`sh ./nfl.sh test` on Linux, `.\nfl.ps1 test` on Windows), and when both pass, update the status board, the progress ledger and `changelog.md` and open the pull request under `.claude/rules/git-authority.md`.

Session 05 is startable too but shares `src/nfl_dfs/cli.py` with Session 04, so
it runs after it. Session 21 (prior-model triage) shares no file with Session 04
and may run beside it in a separate worktree
(`git worktree add ../nfl-dfs-s21 -b claude/s21-prior-triage`). Session 04's card
carries what Session 03b found for it.

Every close-out rewrites the session number in this block to the next
startable row. `python3 scripts/repo_state.py --stdout` derives the same answer
from the table, so if the two ever disagree, the table wins.

## 2. Master Session Roadmap

### 2.1 How to read and run it

- **Order is priority.** Take the first `Pending` row whose `Depends on`
  entries are all satisfied. Delivery work (Sessions 01 to 16) comes before
  measurement and modelling, per Ben's 2026-09-22 instruction: a valid,
  accessible lineup file on time overrides optional modelling, simulation and
  quality gates.
- **Status** is one of `Pending`, `In Progress`, `Complete`, `Deferred`.
  `Deferred` means intentionally parked, and its card names what reactivates it.
- **Depends on** holds `none`, `Session NN`, an operator item `O<n>` from §2.6,
  or `BEN ruling`. A session dependency is satisfied when that row is
  `Complete`. An operator item is satisfied when its row in §2.6 is `Done`. A
  `BEN ruling` is satisfied only when the open BEN flag in that session's card
  has been answered and removed.
- **Type.** `Standalone` sessions are one high-risk or solver-heavy item.
  `Batched` sessions hold two to four items that share files.
- **Classification** follows the audit's §4. `V` is submission validity,
  authority or integrity. `S` is strategy or construction preference. `P` is
  process, model quality or tooling.
- **Session IDs** in claims and branch names are the short form: `S01` for
  Session 01. A split session takes a letter suffix (`Session 04b`) and gets its
  own row directly below the original.
- **Concurrency.** Two sessions may run at once only in separate worktrees, and
  only when their Target Files do not overlap. Each card names its known
  conflicts.
- **Commands** are shown in the Linux form. On Windows, `sh ./nfl.sh test ...`
  is `.\nfl.ps1 test ...`.

Every session follows this protocol, and the cards only add to it:

1. Orient: `git status --short --branch`, `git log --oneline -15`,
   `python3 scripts/repo_state.py --stdout`, then
   `python3 scripts/claim.py take SNN`. Commit and push the claim.
2. Read §1, the session's card, the briefs its Source names, and the first
   80 lines of `changelog.md`. Set the row to `In Progress` and add a ledger row
   in §4.
3. Write or extend the tests for the card's acceptance before the code. Never
   delete or weaken a test to get a pass. A test whose expectation a ruling
   changes is edited as its own visible change and named in the changelog.
4. Verify: the card's command, then the full suite
   (`sh ./nfl.sh test 2>&1 | tee /tmp/pytest.log`, with a 600000 ms tool
   timeout, then `python3 scripts/record_verify.py --from-log /tmp/pytest.log`),
   `sh ./nfl.sh doctor`, `git diff --check`, and
   `python3 scripts/check_protected_paths.py`.
5. Breakpoint: if the diff passes about 1,500 changed lines, or the session
   would need a compaction, stop at the card's named seam. Land what is tested,
   add a `b` row for the rest, and say so in the changelog.
6. Close out: set the row `Complete` (or back to `Pending` with what is left),
   add a ledger row, write a dated `changelog.md` entry with the exact numbers,
   update `IMPLEMENTATION_STATUS.md` when capability changed, rewrite §1 to the
   next startable session, and run `python3 scripts/claim.py release SNN`.
7. Ship under `.claude/rules/git-authority.md`: explicit path list, pull
   request, merge on green. A pull request that touches `CLAUDE.md`,
   `.github/protected-paths.txt` or `.claude/settings.json` waits for Ben's
   `ben-review` label, and Ben merges it. The next session records the merge
   commit SHA in §4.

### 2.2 Status board

<!-- roadmap-table:start -->
| Session ID | Type | Work Unit & Scope | Source Origin | Target Files | Classification | Depends on | Verification Command / Breakpoint | Status |
|---|---|---|---|---|---|---|---|---|
| Session 00 | Batched | Roadmap cutover: write this file; archive `backlog.md` verbatim behind a stub; `repo_state.py`, the queue test, the skills, the ledger rule and the chunk headers read this file; archive the session prompts; banner the superseded trackers; archive old changelog entries | This request; audit §8; `.claude/rules/ledger.md` | `docs/ROADMAP.md`, `backlog.md`, `scripts/repo_state.py`, `tests/test_roadmap_queue.py`, `.claude/skills/`, `.claude/rules/ledger.md` | P | none | `sh ./nfl.sh test tests/test_roadmap_queue.py tests/test_harness_orientation.py -x --tb=short` | Complete |
| Session 01 | Batched | Governance: write rulings R28 to R31 and the roadmap pointer into `CLAUDE.md`; correct its false claims (rung 4 "always produces a legal portfolio", both generators "encode the rung ladder", "nothing writes `DK_UPLOAD`", evidence gates first in the running order) and the stale Excel and "P0 repairs" lines elsewhere; H3, so `ben-review` can clear this pull request | R28 to R31; audit D2, D5, D8, DD-7 (documents); chunk H3 | `CLAUDE.md` (protected), `docs/START_HERE.md`, `docs/RUNBOOK.md`, `docs/OPERATOR_GUIDE.md`, `docs/CLAUDE_CODE_SETUP.md`, `.claude/rules/`, `IMPLEMENTATION_STATUS.md`, `README.md`, `.github/workflows/ci.yml`, new `.github/workflows/protected-paths.yml`, `scripts/check_protected_paths.py`, `scripts/file_standings.py`, `tests/test_repo_boundaries.py` | P | Session 00 | `python3 scripts/check_protected_paths.py`; `sh ./nfl.sh test tests/test_repo_boundaries.py -x --tb=short`; seam: H3 alone | Complete |
| Session 02 | Batched | Fallback CSV correctness: the writer refuses unknown Entry IDs, fills every blank authorized row or exits non-zero naming the rest, validates each exported roster and never overwrites; QA checks each exported roster against its assignment; the builder's shortfall exits non-zero; Showdown strategy findings stop failing the validity exit code | Audit D6, DD-5, §4 standalone-QA rows | `scripts/write_dk_entries.py`, `scripts/qa_classic_portfolio.py`, `scripts/build_classic_portfolio.py`, `scripts/qa_showdown_portfolio.py` | V | Session 00 | `sh ./nfl.sh test tests/test_write_dk_entries.py tests/test_qa_classic_portfolio.py tests/test_build_classic_portfolio.py tests/test_qa_showdown_portfolio.py -x --tb=short`; seam: writer and Classic QA first | Complete |
| Session 02b | Batched | Fallback builder and Showdown QA, split from Session 02 at its seam: the builder's shortfall exits 3 naming the unfilled Entry IDs and never repeats a lineup; a real ratchet ceiling; an existing output refused; DraftKings `OUT`/`IR`/`D` rows leave the pool; Showdown strategy findings stop failing the validity exit code | Audit D6, DD-5, §4 standalone-QA rows; Session 02 breakpoint | `scripts/build_classic_portfolio.py`, `scripts/qa_showdown_portfolio.py` | V | Session 02 | `sh ./nfl.sh test tests/test_build_classic_portfolio.py tests/test_qa_showdown_portfolio.py -x --tb=short` | Complete |
| Session 03 | Standalone | `DELIVERY_STATE` contract: the fifth truth, derived only from file validity, coverage and integrity blockers, with structured limitations; `nfl_release_truths_v2`; the non-numerical-gate test that R24 was conditional on. The registry split to Session 03b | R28; audit D1, DD-1, §4; archive § R24 recommendation and R26 coupling | `src/nfl_dfs/release.py`, `src/nfl_dfs/contracts.py`, `docs/DATA_CONTRACTS.md`, new `tests/test_delivery_state.py`, new `tests/test_gate_registry.py` | V | Session 01 | `sh ./nfl.sh test tests/test_release_truths.py tests/test_gate_registry.py tests/test_delivery_state.py -x --tb=short` | Complete |
| Session 03b | Standalone | Gate registry, split from Session 03 at its seam: `config/gate_registry_v1.json` gives every blocker code emitted under `src/` a class (`V`, `S`, `P`; audit §4 seed, R29 makes cross-entry uniqueness `V`), provenance and `stops`; `gate_registry.py` loads and validates it and builds `DeliveryLimitation`s from codes; a completeness test fails on any unregistered code | R28; audit D1, DD-1, §4; Session 03 breakpoint | new `src/nfl_dfs/gate_registry.py`, new `config/gate_registry_v1.json`, `tests/test_gate_registry.py`, `docs/DATA_CONTRACTS.md` | V | Session 03 | `sh ./nfl.sh test tests/test_gate_registry.py tests/test_delivery_state.py -x --tb=short`; seam: schema, loader and completeness with every code listed, then classification by module | Complete |
| Session 04 | Standalone | Baseline command: `nfl baseline --salaries --entries` builds distinct legal lineups from the DraftKings bytes alone, fills blank authorized rows through the exact-byte writer into a new versioned file, and reports `DELIVERY_STATE` and every unfilled Entry ID; no network | R28, R29; audit D2, DD-2 | new `src/nfl_dfs/baseline.py`, `src/nfl_dfs/cli.py`, `src/nfl_dfs/lineups.py`, `docs/DATA_CONTRACTS.md`, `docs/RUNBOOK.md` | V | Session 02, Session 03 | `sh ./nfl.sh test tests/test_baseline.py -x --tb=short`; fixture runs at 1, 20 and 150 entries with wall time | Pending |
| Session 05 | Batched | Artifact preservation: a validated CSV survives later presentation failures in both modes and in the outer exception handler; a roster, Entry ID or byte discrepancy still invalidates; an atomic, hash-bound latest-deliverable pointer | Audit D4, DD-2, DD-8 | `src/nfl_dfs/classic_review.py`, `src/nfl_dfs/cli.py`, `src/nfl_dfs/review_export.py`, new `src/nfl_dfs/delivery.py` | V | Session 03 | `sh ./nfl.sh test tests/test_classic_review_c3.py tests/test_classic_portfolio_c2.py tests/test_cowork_rerun_regressions.py tests/test_artifact_preservation.py -x --tb=short` | Pending |
| Session 06 | Standalone | Baseline-first `run-slate`: the baseline is built and published right after intake, before priors, weather, roles or solves; an improvement replaces it only after independent validation; any improvement failure leaves the baseline reachable; C1 (rung 4) ends with a CSV | Audit D2, DD-2 | `src/nfl_dfs/cli.py`, `src/nfl_dfs/cowork.py`, `src/nfl_dfs/prior_review.py`, `src/nfl_dfs/delivery.py` | V | Session 04, Session 05 | `sh ./nfl.sh test tests/test_run_slate_baseline_first.py tests/test_prior_review_profile.py tests/test_classic_prior_review.py -x --tb=short` | Pending |
| Session 07 | Standalone | Deadline controller: run request v3 with an optional delivery deadline (default: earliest lock minus 5 minutes); one budget passed through every stage; retries, solver limits and bank sizes set from remaining time; dead `runtime.json` keys consumed or removed; measured stage durations | R31; audit D3, DD-3; C4 retro #3 | `src/nfl_dfs/cowork.py`, new `src/nfl_dfs/deadline.py`, `src/nfl_dfs/sources.py`, `scripts/fetch_weather_captures.py`, `scripts/make_classic_policy.py`, `config/runtime.json` | P | Session 06 | `sh ./nfl.sh test tests/test_deadline_controller.py tests/test_cowork.py tests/test_fetch_weather_captures.py -x --tb=short` | Pending |
| Session 08 | Standalone | Timeout incumbents: validated time-limited candidates are kept; a bank with a feasible witness does not block; both joint selectors validate and return an integer incumbent on a time or search limit under a non-optimal status; C3 accepts it labelled; the timing-sensitive C2 status test becomes deterministic | Audit D5, DD-4, §1 test failure | `src/nfl_dfs/classic_portfolio.py`, `src/nfl_dfs/portfolio_enforcement.py`, `src/nfl_dfs/selection.py`, `src/nfl_dfs/classic_review.py` | P | Session 06 | `sh ./nfl.sh test tests/test_classic_portfolio_c2.py tests/test_portfolio_enforcement.py tests/test_classic_review_c3.py -x --tb=short`; then the C2 status test 20 times in a row | Pending |
| Session 09 | Batched | R28 on the model path: missing weather (including a derived roof) and missing Classic official activity become named limitations, not stops; a real identity or timestamp conflict still invalidates its evidence; `build_priors` authority persists for the run; weather pre-capture becomes optional in the runbook | R28; audit D8, DD-7; archive § R23, R24, F7 | `src/nfl_dfs/priors.py`, `src/nfl_dfs/prior_review.py`, `src/nfl_dfs/cowork.py`, `docs/RUNBOOK.md` | P | Session 03b, Session 06 | `sh ./nfl.sh test tests/test_prior_review_profile.py tests/test_classic_prior_review.py tests/test_gate_registry.py -x --tb=short` | Pending |
| Session 10 | Batched | Relaxation controller: the engine, not printed advice, walks a bounded rung ladder inside the cumulative budget; the full trigger list; bank timeouts shrink the bank before relaxing structure; Showdown gets a real ladder; uniqueness is never on it; every relaxation is a structured record | R29; audit D5, DD-4; Showdown retro #6; C4 retro #3 | new `src/nfl_dfs/relaxation.py`, `scripts/make_classic_policy.py`, `scripts/make_showdown_policy.py`, `src/nfl_dfs/cli.py` | S | Session 07, Session 08 | `sh ./nfl.sh test tests/test_relaxation_controller.py tests/test_classic_policy_generator.py -x --tb=short` | Pending |
| Session 11 | Standalone | Entry groups: prefilled rows are preserved byte-identical instead of refusing the file; blank rows are filled; each Contest ID group is delivered on its own; unresolved Entry IDs are listed; distinctness covers prefilled lineups; `entry_ids` may bind a subset | R29; audit D7, DD-6; Showdown retro #4 | `src/nfl_dfs/lineups.py`, `src/nfl_dfs/prior_review.py`, `src/nfl_dfs/baseline.py`, `src/nfl_dfs/dk.py` | V | Session 06 | `sh ./nfl.sh test tests/test_entry_groups.py tests/test_byte_line_fidelity.py -x --tb=short` | Pending |
| Session 12 | Standalone | Late-swap bridge and C5: a hash-bound record of the entries actually submitted (Ben's post-upload DKEntries download) anchors governed late swap without claiming certification; multi-contest by group; locked cells byte-identical; later-lock players preferred in flexible slots | Audit D9, DD-6; archive § C5 | `src/nfl_dfs/late_swap.py`, `src/nfl_dfs/lineups.py`, `docs/DATA_CONTRACTS.md` | V | Session 11 | `sh ./nfl.sh test tests/test_governed_late_swap.py tests/test_late_swap_learning.py -x --tb=short` | Pending |
| Session 13 | Batched | Run-start preflight report (identity, pool completeness, evidence and participation vocabulary against the actual inputs, one report before the first solve) and the scored player pool as a first-class hash-bound artifact | C4 retro #2, #4; Showdown retro #7; audit §5 | `scripts/session_probe.py`, `src/nfl_dfs/selection.py`, `src/nfl_dfs/prior_review.py` | P | Session 09 | `sh ./nfl.sh test tests/test_session_probe_gate.py tests/test_prior_selection.py tests/test_preflight_report.py -x --tb=short` | Pending |
| Session 14 | Batched | Delivery record: `delivery_outcome`, timing, coverage, artifact identity, recovery, relaxation and intervention fields in one versioned run record; "presented" means path and hash in the handoff; submission receipt only from an operator-downloaded file | Audit §9, DD-8 | `src/nfl_dfs/delivery.py`, `src/nfl_dfs/cli.py`, `docs/DATA_CONTRACTS.md` | P | Session 07, Session 10 | `sh ./nfl.sh test tests/test_delivery_record.py -x --tb=short` | Pending |
| Session 15 | Standalone | Delivery acceptance: the audit's twelve failure scenarios end to end with an injected clock and faults and no operator rescue; the §10 impossible cases end in an honest partial or `NO_DELIVERY` | Audit §6, §10, DD-8 | new `tests/test_delivery_scenarios.py` and its fixtures | V | Session 09, Session 11, Session 12, Session 13, Session 14 | `sh ./nfl.sh test tests/test_delivery_scenarios.py -x --tb=short`, then the full suite | Pending |
| Session 16 | Standalone | Real-slate rehearsal on Windows, Classic and Showdown, on current files: time to baseline, improvement, deadline and record; the P7 replay on the 2026-09-20 snapshot | Archive § C4 and operator item 6; Showdown tracker SD6 | the run folder, a new `docs/RUN_RECORD_<date>.md`, `changelog.md` | V | Session 15, O8 | `.\nfl.ps1 test` green; the run record shows five truths, time to baseline and delivery time against the deadline | Pending |
| Session 17 | Standalone | X2: the 26 standings exports become private GitHub release assets, fetched with authentication through `sources.py` and hash-bound on arrival | Chunk X2; archive § R27 | `src/nfl_dfs/sources.py`, a retrieval script, `docs/DATA_CONTRACTS.md` | P | Session 00 | `sh ./nfl.sh test tests/test_source_ledger.py tests/test_sources_tls.py tests/test_standings_transport.py -x --tb=short`; acceptance needs O1 | Pending |
| Session 18 | Standalone | P0: one deterministic command grades a slate from its standings; DAL@NYG and DEN@KC snapshots filed | Chunk P0 | new `src/nfl_dfs/standings_grade.py`, `src/nfl_dfs/cli.py`, new `scripts/grade_standings.py` | P | Session 17, O2 | `sh ./nfl.sh test tests/test_standings_grade.py -x --tb=short`; the grade command reproduces the brief's numbers in under 3 minutes | Pending |
| Session 19 | Standalone | X3: automatic run postmortem on success and failure, abandoned-run recovery sweep, compaction continuity, and the rule that MCP output is never evidence | Chunk X3 | `.claude/hooks/`, `.claude/rules/`, `.claude/settings.json` (protected) | P | Session 00 | `sh ./nfl.sh test tests/test_harness_orientation.py tests/test_repo_boundaries.py -x --tb=short`; `grep -rn "MCP" .claude/rules/` finds the rule | Pending |
| Session 20 | Batched | X1 per-host egress lines in `doctor` with a prohibited-host test; `docs/CLAUDE_CODE_SETUP.md` facts replaced by the probe; a test for `sync.ps1` | Chunk X1; changelog 2026-09-22 "left open" | `src/nfl_dfs/cli.py`, `scripts/session_probe.py`, `docs/CLAUDE_CODE_SETUP.md`, `sync.ps1` | P | Session 00 | `sh ./nfl.sh test tests/test_session_probe.py -x --tb=short`; `sh ./nfl.sh doctor` completes offline | Pending |
| Session 21 | Batched | Prior-model triage: confirm or refute the per-game `TARGET_SHARE` against season `ROLE_CAPACITY` unit mismatch, then fix it or close it with evidence; F8 alternate-name identity proposals for review, with auto-accept unchanged | Showdown retro §9 #2; archive § F8 | `src/nfl_dfs/opportunity.py`, `src/nfl_dfs/prior_score.py`, `src/nfl_dfs/priors.py` | P | Session 00 | `sh ./nfl.sh test tests/test_offensive_roles.py tests/test_priors_adapter.py -x --tb=short` | Pending |
| Session 22 | Standalone | P0b: run-folder provenance completeness, manifests for hand-built entries, a pre-registration record per slate | Chunk P0b | `src/nfl_dfs/prelock_manifest.py`, `src/nfl_dfs/prior_review.py`, new `src/nfl_dfs/preregistration.py` | P | Session 18 | `sh ./nfl.sh test tests/test_prelock_manifest.py -x --tb=short` | Pending |
| Session 23 | Standalone | P2: contest-aware assignment, structural hygiene bounds and `max_person_share`, plus the Showdown policy constraints (captain team, per-team bounds, pair rules) | Chunk P2; Showdown retro #1; debrief §6 | both policy contracts, `src/nfl_dfs/portfolio_enforcement.py`, `src/nfl_dfs/selection.py`, both policy generators | S | Session 18, Session 10 | `sh ./nfl.sh test tests/test_portfolio_policy.py tests/test_classic_policy_generator.py -x --tb=short` | Pending |
| Session 24 | Standalone | P3a: bounded DESIGN scenario bank on the `prior_review` path, with p50, p90 and p99 per lineup | Chunk P3a | `src/nfl_dfs/simulation.py`, `src/nfl_dfs/prior_review.py`, the review writers | P | Session 18 | `sh ./nfl.sh test tests/test_simulation.py -x --tb=short` | Pending |
| Session 25 | Standalone | P3b: registered tail objective and tail sleeve, including captain strata on a ceiling statistic, the dart rules and DST-inclusive families | Chunk P3b; Showdown retro #5; C4 retro #6, #9, #16; debrief §6 | `src/nfl_dfs/selection.py`, `src/nfl_dfs/candidate_families.py`, both policy contracts | S | Session 23, Session 24 | `sh ./nfl.sh test tests/test_prior_selection.py -x --tb=short` | Pending |
| Session 26 | Standalone | P4a: mass-conserving ownership challenger graded by slate, with projected against realized ownership logged | Chunk P4a; C4 retro #11, #12, #15 | `src/nfl_dfs/ownership.py`, `src/nfl_dfs/prior_review.py` | P | Session 18 | `sh ./nfl.sh test tests/test_ownership_field.py -x --tb=short` | Pending |
| Session 27 | Standalone | P4b: exact-lineup copy-count predictor | Chunk P4b | `src/nfl_dfs/field.py`, `src/nfl_dfs/prior_review.py` | P | Session 26 | `sh ./nfl.sh test tests/test_ownership_field.py -x --tb=short` | Pending |
| Session 28 | Standalone | P6: scenario-cluster coverage, bank-estimated P(zero paid), sleeve-size frontier | Chunk P6 | `src/nfl_dfs/portfolio.py`, `src/nfl_dfs/prior_review.py`, `src/nfl_dfs/readable_review.py` | S | Session 25 | `sh ./nfl.sh test tests/test_readable_review.py -x --tb=short` | Pending |
| Session 29 | Standalone | P5: dilution-aware first-place value with real payout ladders | Chunk P5 | `src/nfl_dfs/payouts.py`, `src/nfl_dfs/economics.py`, `src/nfl_dfs/selection.py` | P | Session 25, Session 27, O4 | `sh ./nfl.sh test tests/test_payouts.py -x --tb=short` | Pending |
| Session 30 | Standalone | Standings contract v3: represent field members who never submitted a lineup and exact tie splits that are not whole cents, so a contest with ties can settle | Archive § 2026-09-14 close-out; Q1B | `src/nfl_dfs/settlement.py`, `scripts/file_standings.py`, `docs/DATA_CONTRACTS.md` | P | BEN ruling | `sh ./nfl.sh test tests/test_standings_normalizer.py tests/test_reference_settlement.py -x --tb=short` | Pending |
| Session 31 | Standalone | QA1: adversarial QA whose findings are policy deltas, with a Pareto filter and at most three iterations | Archived QA1 prompt; archive § QA1 | new `src/nfl_dfs/adversarial_qa.py` | S | Session 25 | Reactivate when Session 25 is `Complete` | Deferred |
| Session 32 | Standalone | Late-swap strategy aids: a swap QA gate, a salary reserve, swap-flexible entry tags, points per $1,000 of locked salary | C4 retro #5, #7, #8, #14 | `scripts/qa_classic_portfolio.py`, `src/nfl_dfs/late_swap.py` | S | Session 12, Session 25 | Reactivate when both are `Complete` | Deferred |
| Session 33 | Standalone | P4c: contest-conditioned field effects with shrinkage | Chunk P4c | `src/nfl_dfs/field.py` | P | Session 27, O10 | Reactivate at about 20 more Showdown games with standings | Deferred |
| Session 34 | Standalone | X4: greenfield spec report and subagent cost contract | Chunk X4 | a new report in `docs/` | P | Session 17, Session 19, Session 20 | Re-scope first: the audit and this roadmap now cover most of its report | Deferred |
| Session 35 | Standalone | C3X: native Excel open, recalculate, save and reopen acceptance | R30 | `src/nfl_dfs/workbook.py` | P | none | Reactivate only on Ben's word | Deferred |
| Session 36 | Standalone | Promotion track Q2 to Q7 and QC1, absorbing the P-track acceptance and the R17 rookie prior | Archive § 2026-09-10 program | re-planned when reactivated | P | Session 29, O5 | Re-plan into sessions when settled-slate accrual meets Q6's registered minimum | Deferred |
<!-- roadmap-table:end -->

### 2.3 Session cards

#### Session 00: roadmap cutover

- **Scope.** Everything in the Session 00 row, executed 2026-09-22 in the
  session that wrote this file. The `CLAUDE.md` pointer is protected, so it
  moves to Session 01. Until then `backlog.md` is a stub that points here.
- **Acceptance.** `scripts/repo_state.py` reads this table; it fails loudly if
  the markers are missing and never falls back to "none". The session-start
  digest names Session 01 as startable. The only open BEN flag is the one in
  Session 30.
- **Verification.** The row's command, then the full suite.
- **Breakpoint.** Changelog archival was the named seam. It did not have to be
  used.

#### Session 01: governance (rulings into `CLAUDE.md`, false claims corrected, H3)

- **Depends on.** Session 00. Protected: this pull request carries `ben-review`,
  and Ben merges it (O7).
- **Scope.**
  1. H3, per `docs/chunks/H3-protected-paths-label-freshness.md`: read labels at
     job runtime and add the `labeled` and `unlabeled` pull-request types, so a
     label applied after CI can turn `protected-paths` green.
  2. `CLAUDE.md`: record R28 to R31 (§2.5) in "Release truths" and "Shipping
     under a lock clock"; take uniqueness off the construction-preference list;
     point "Developing the engine" and the authority order at this file; update
     the status vocabulary and the stale suite count ("789 passed", now
     `1070 passed, 1 skipped` on Linux CI).
  3. Correct the claims the audit and its verification found false:
     - Rung 4 "always produces a legal portfolio". C1 writes JSON only
       (`prior_review.py:3016`) and raises on a shortfall (`selection.py:538-542`).
     - "Both generators encode the rung ladder". `make_showdown_policy.py:68-82`
       has none.
     - "Nothing writes `DK_UPLOAD`". `certify` and governed late swap both can.
       The accurate statement is that the operating profiles do not.
     - Evidence gates "go first because they are the only things that can make
       you miss a lock". After R28 the baseline goes first.
  4. Mirror the changes into `docs/START_HERE.md` (boundary 5 wording, five
     truths), `docs/RUNBOOK.md` (Excel gate at `:151-155` and `:800-801`; "P0
     repairs" the failing test at `:196-198` and `:685`, fixed on 2026-09-17),
     `.claude/rules/slate-operation.md`, `.claude/rules/operating-path.md`,
     `IMPLEMENTATION_STATUS.md:184` and its `backlog.md` pointers, `README.md:18`,
     and the `file_standings.py` refusal text that cites "Q1B in `backlog.md`".
- **Out of scope.** Any engine behaviour. The rulings are recorded now and
  implemented by Sessions 03 to 12. Until then, runs report four truths.
- **Acceptance.** `CLAUDE.md` states R28 to R31 in plain English. Permanent
  boundaries 1 to 4 and 6 to 8 are unchanged. Boundary 5 still says missing hard
  evidence is `DO_NOT_UPLOAD`, and adds that under R28 it stops certification,
  not construction or delivery. This pull request, labelled after CI ran, goes
  green with no new commit (timestamps pasted into the changelog).
- **Breakpoint.** If H3 cannot be proven on this pull request, land H3 alone as
  `Session 01b` first. Do not split the `CLAUDE.md` change to dodge the label.
- **2026-09-23, Complete.** H3 landed as a new
  `.github/workflows/protected-paths.yml` (live labels, reruns on `labeled` and
  `unlabeled`), with `scripts/check_protected_paths.py --live-labels` and 37
  boundary tests. `CLAUDE.md` carries R28 to R31 and the four corrections, 11 of
  12 boundaries byte-identical, at 199 lines. The RUNBOOK's full lock-clock text
  is amended in place, each amendment marked, and the other stale Excel,
  "P0 repairs" and `backlog.md` lines are corrected. Left open:
  `scripts/make_classic_policy.py` still prints the old rung-4 claim (Sessions
  06 and 10 own that file). H3 proven on PR #42 at `32b9135`: `protected-paths`
  red at 00:46:50Z, `ben-review` applied at 00:47:14Z, green at 00:47:26Z on
  the same SHA with no new commit (timestamps in `changelog.md`).

#### Session 02: fallback CSV correctness

- **Depends on.** Session 00. It can run alongside Session 01 because the files
  do not overlap. `docs/RUNBOOK.md` is touched by both, but in different
  sections.
- **Why first among the code sessions.** The standalone fallback is the path
  Ben used at lock on 2026-09-13 and 2026-09-20, and its three stages can each
  exit 0 while reserved rows go out blank and QA prints PASS
  (`build_classic_portfolio.py:254-279`, `write_dk_entries.py:49`,
  `qa_classic_portfolio.py:231`).
- **Scope.**
  1. `write_dk_entries.py`:
     - Refuse assignment IDs absent from the template, by name.
     - Fill every blank authorized row, or exit non-zero listing the unresolved
       Entry IDs.
     - Validate each exported roster against the salary file (slot and FLEX
       eligibility, cap, unique people, DraftKings ID in pool) with named
       refusals, not `assert`.
     - Preserve untouched lines' raw bytes, as `lineups.py:148-153` does.
     - Refuse an existing output path and output equal to the template. Write
       to a temporary file and `os.replace`.
  2. `qa_classic_portfolio.py`:
     - Reparse the final CSV and compare each exported roster to its assignment
       by Entry ID.
     - Coverage is unconditional: every authorized row is filled or listed.
     - Rename or strengthen "byte fidelity" so the claim matches the check.
     - Keep the validity exit code apart from strategy observations.
  3. `build_classic_portfolio.py`:
     - A shortfall exits non-zero with the unfilled Entry IDs and never repeats
       a lineup (R29).
     - Fix the ratchet ceiling `min(EXP + 1, max(EXP + 1, 9))` (`:217-223`).
     - Refuse an existing output.
     - Check whether the pool filter should also drop DraftKings-unavailable
       statuses (`:130`), and fix it or record why not.
  4. `qa_showdown_portfolio.py`: `ZERO_QB`, `MULTIPLE_KICKERS`, `MULTIPLE_DST`
     and `DST_WITH_OWN_OFFENSE` become strategy observations. True roster
     defects keep exit 2. New `tests/test_qa_showdown_portfolio.py`.
- **Tests to change, visibly.** `tests/test_write_dk_entries.py:139-147`
  expects exit 0 on a missing ID. It becomes a refusal test. The CRLF and
  byte-identity tests are reconciled with the raw-line behaviour.
- **Adversarial fixtures.** An extra ID, a missing ID, a QB in FLEX, over the
  cap, a duplicate person, output equal to the template, a pre-existing output,
  and 18 of 20 filled. QA must fail every one.
- **Breakpoint.** Items 1 and 2 are the validity core. Items 3 and 4 are the
  seam for `Session 02b`.
- **2026-09-23, Complete (items 1 and 2).** The writer refuses by name
  (exit 2, nothing written) an unknown Entry ID, a prefilled row, a roster that
  fails the salary file and a repeated lineup, and writes the file with exit 3
  naming each unfilled Entry ID. Untouched lines keep their raw bytes, and the
  write is a verified temporary file and `os.replace`. Classic QA audits the
  export on bytes, compares each exported roster to its assignment by Entry ID,
  and exits 1 validity, 3 partial, 2 operator limits. The card's command fails
  on `tests/test_qa_showdown_portfolio.py`, which Session 02b creates; the other
  three files pass. Suite `1168 passed, 1 skipped`. Items 3 and 4 moved to
  Session 02b at this card's breakpoint (1,378 changed lines after items 1 and
  2). Nothing relaxed.

#### Session 02b: fallback builder and Showdown QA

- **Depends on.** Session 02: the builder's shortfall emits the exit-3 contract
  that Session 02's writer and QA already honour.
- **Split from Session 02** at its breakpoint on 2026-09-23: the writer and
  Classic QA alone reached 1,378 changed lines.
- **Scope.** Items 3 and 4 of the Session 02 card, with what Session 02 found:
  1. `build_classic_portfolio.py`:
     - A shortfall writes the partial map plus `unfilled_entry_ids`, names them
       on stderr and exits 3; it never repeats a lineup (R29). Add an explicit
       distinctness check, because `--max-overlap 9` can repeat one today.
     - Fix the ratchet ceiling `min(EXP + 1, max(EXP + 1, 9))`, which is always
       `EXP + 1`. Session 02's proposal: `min(EXP + 1, max(a.max_exposure, N))`,
       because a ceiling of 9 would create shortfalls at large N and the attempt
       budget already bounds the walk.
     - Refuse an existing `--out`; temp file and `os.replace`. The tests' `run()`
       helper then needs a unique `--out` per call.
     - Pool filter (`:130`): fix it. `selection.py:228-230` writes `scores.json`
       before the exclusion set at `:231-254`, so DraftKings `OUT`, `IR` and `D`
       rows reach the builder with positive scores (33 such rows in the supplied
       Classic salary file). Drop them with
       `nfl_dfs.contracts.UNAVAILABLE_DK_STATUSES`, the engine's one vocabulary.
     - `reserved_entry_ids` returns blank rows only, so a prefilled row is never
       assigned and refused by the writer; `--lineups` defaults to their count
       when `--entries` is given.
  2. `qa_showdown_portfolio.py`: `ZERO_QB`, `MULTIPLE_KICKERS`, `MULTIPLE_DST`
     and `DST_WITH_OWN_OFFENSE` become strategy observations. True roster
     defects keep exit 2. New `tests/test_qa_showdown_portfolio.py`.
- **Noted, not in scope.** Showdown QA's default-on `OVERLAP_*` and
  `STARTER_WITH_OWN_BACKUP` still exit 2. `scores.json` also omits selection's
  kicker zero-share and offense exclusions, for the same ordering reason
  (Session 13 makes the scored pool first-class).
- **2026-09-23, Complete.** Both items, no breakpoint. The builder exits 0,
  2 (refused by name, nothing written) or 3 (written, `unfilled_entry_ids`
  naming every blank row without a lineup); it never repeats a lineup,
  prefilled ones included; the ratchet stops at `max(--max-exposure, N)` and
  `max(--max-overlap, 6)` and never tightens a cap; `OUT`, `IR` and `D` leave
  the pool (`--available-status` as in the engine); only blank rows are
  reserved; `--out` must be new. On the supplied 719-row salary file and
  20-entry template, builder, writer and Classic QA all exit 0 with the 33
  flagged rows out. Showdown QA's four findings are `OBSERVATIONS` that never
  change the exit code. The template is read as the writer reads it, and an
  unknown DraftKings status leaves the pool by name. Suite `1235 passed,
  1 skipped`. Nothing relaxed. Left open: the two Showdown QA limits above;
  `--min-salary` above `--cap` builds nothing and exits 3 rather than
  refusing; zero lineups exits 3 in the builder and 2 in the writer.

#### Session 03: `DELIVERY_STATE` contract and gate registry

- **Depends on.** Session 01, because `CLAUDE.md` must permit the state before
  code emits it.
- **Scope.**
  1. A fifth truth, `DELIVERY_STATE`, with the values:
     - `DELIVERABLE`: every authorized blank row filled, the file valid, no
       integrity blocker.
     - `DELIVERABLE_PARTIAL`: valid rows delivered and the rest listed by
       Entry ID.
     - `NO_DELIVERABLE`: nothing valid to hand over.

     It carries a structured `delivery_limitations` list (gate code, class,
     provenance, affected Entry IDs or people). It is derived only from file
     validity, coverage and integrity blockers, never from model or evidence
     state. `RELEASE_DECISION` derivation does not change, and
     `tests/test_release_truths.py` is only extended.
  2. `config/gate_registry_v1.json` and `src/nfl_dfs/gate_registry.py`. Every
     blocker code emitted under `src/` gets:
     - a class, `V`, `S` or `P`, seeded from audit §4, with R29 moving
       cross-entry uniqueness to `V` by authority;
     - provenance: a `CLAUDE.md` boundary, a ruling or a contract;
     - `stops`: `FILE`, `CERTIFICATION` or `CONSTRUCTION_PREFERENCE`.
  3. Tests:
     - Completeness: every blocker literal in `src/` has an entry.
     - A `V` gate can never have `stops=CERTIFICATION`.
     - `DELIVERABLE` never co-occurs with an integrity blocker.
     - The R24 condition: `weather_state`, including a value carrying
       `DERIVED_FROM_VENUE_ROOF_HISTORY`, is read by no scoring, projection or
       opportunity arithmetic.
  4. Register `nfl_release_truths_v2` (or the next free name) in
     `docs/DATA_CONTRACTS.md`. Version 1 is never mutated.
- **Out of scope.** Changing what any path does. Sessions 04 to 09 wire it in.
- **Breakpoint.** The registry file plus its completeness test can land as
  `Session 03b` if the truth record runs long.
- **2026-09-23, Complete (items 1 and 4, the `DELIVERABLE` and R24 tests).**
  `derive_delivery_state` and `nfl_release_truths_v2` land in `release.py` and
  `contracts.py`, with no path emitting them yet. Only a `V` gate stops the
  file, and a `V` gate stops nothing less. `DELIVERABLE` occurs exactly when no
  `V` limitation does, checked exhaustively. R24: weather or a roof value may
  be read only in named plumbing and at 10 pinned reads, no arithmetic takes
  one, and every weather state, derived roof included, scores identically. The
  registry file, loader and completeness test split to Session 03b before any
  registry code: 805 codes to classify. Suite `1369 passed, 1 skipped`.
  Nothing relaxed.

#### Session 03b: gate registry

- **Depends on.** Session 03, which added `GateClass`, `GateStops`,
  `GateProvenance` and `DeliveryLimitation` to `contracts.py`. A limitation
  already refuses a `V` gate that stops anything but `FILE`, and a non-`V` gate
  that stops `FILE`; registry entries obey the same rule.
- **Split from Session 03** at its breakpoint on 2026-09-23, before any
  registry code: 805 distinct codes had to be classified.
- **Scope.**
  1. `config/gate_registry_v1.json` (new versioned contract in
     `docs/DATA_CONTRACTS.md`): every blocker code emitted under `src/` gets a
     `class`, `provenance` (`kind` and `ref`, as `GateProvenance`) and `stops`.
     Seed the classes from audit §4 (issue #40); R29 makes cross-entry
     uniqueness `V` by authority. Families with shared metadata and a
     code-to-family map keep it reviewable, one code per line.
  2. `src/nfl_dfs/gate_registry.py`: load and validate the file (hash, schema,
     the class rule above, no duplicate or orphan code) and build a
     `DeliveryLimitation` from a code, Entry IDs and people.
  3. Tests in `tests/test_gate_registry.py`, beside the R24 tests Session 03
     put there: completeness (every blocker literal in `src/` has an entry, and
     every entry is still emitted); a `V` entry never has `stops=CERTIFICATION`;
     the audit §4 rows land in the classes it names.
- **What Session 03 measured.** An AST scan over `src/nfl_dfs/*.py` finds 805
  distinct upper-snake leading tokens (808 with Session 03's own
  `DELIVERY_*` refusals) either in the first argument of a raised exception
  (470 after Session 03) or passed to `append`, `extend` or `add` on a name
  matching `block|reason|limitation|failure|problem|refus|error`, or in a
  keyword argument named like `blocker` or `reason` (343). The heaviest modules
  are `classic_review.py` (102), `priors.py` (73), `prior_review.py` (71),
  `readable_review.py` (60), `projection.py` and `kicker_roles.py` (54 each).
  Some tokens are messages that open with an enum name rather than codes;
  fixing the exact definition is this session's first decision. The scan does
  not see the three codes `release.derive_delivery_state` builds through
  `_integrity()` (`UNFILLED_AUTHORIZED_ROWS`, `FILE_VALIDATION_INCOMPLETE`,
  `NO_AUTHORIZED_ROWS`), which hard-code `V`, `FILE` and a provenance the
  registry must match.
- **Also decide.** Which class and `stops` pairs are allowed besides the two
  rules already enforced: may a `P` gate stop only a construction preference,
  or an `S` gate stop certification.
- **Out of scope.** Changing what any path does, and any gate's behaviour.
- **Breakpoint.** Schema, loader and the completeness test with every code
  listed come first. If classification runs past the breakpoint, land the
  modules classified so far, list the rest in an `UNCLASSIFIED` family that no
  limitation may be built from, and add a `Session 03c` row for them.
- **2026-09-23, Complete (items 1 to 3).** `config/gate_registry_v1.json` gives
  1,088 exact codes 43 families (15 `V`, 3 `S`, 25 `P`); only the pairs
  (`V`, `FILE`), (`S`, `CONSTRUCTION_PREFERENCE`), (`P`, `CERTIFICATION`) load.
  `gate_registry.py` loads, hashes and validates it and builds a limitation
  from an exact code only. The completeness scan follows the emitting shapes
  and resolves interpolations from call sites and literal loops; 13 codes it
  cannot see, 7 non-blocking reasons it reads and 4 Entry-ID-in-the-code
  templates are pinned. The review found 44 codes the scan missed and 21
  misclassified, and templates that resolved unregistered codes; all fixed.
  Every module was classified, so no `03c`. Suite and the P1 hard-stop
  question: `changelog.md`.

#### Session 04: baseline command

- **Depends on.** Session 02 (shared validators) and Session 03 (the state it
  reports).
- **Scope.** A new `src/nfl_dfs/baseline.py` behind `nfl baseline --salaries
  <csv> --entries <csv> [--out-dir]`. It:
  - classifies inputs by schema;
  - reconciles exact current-slate IDs;
  - hard-stops on a Classic/Showdown mismatch;
  - excludes DraftKings-unavailable people through the availability contract,
    derived exactly as `freeze_prior_package` does (`priors.py:2139`);
  - ranks by a registered `BASELINE_SALARY_RANK_V1` objective, with
    `does_not_establish` text;
  - builds distinct lineups (R29) with exact-roster cuts, a per-solve limit and
    a whole-run budget;
  - fills only blank authorized rows through the core exact-byte writer, into a
    new versioned file registered in `docs/DATA_CONTRACTS.md` (never
    `DK_UPLOAD_*`);
  - reparses and audits that file independently;
  - reports `DELIVERY_STATE` and every unfilled Entry ID.

  No network, no priors, no weather, no roles. The runbook's lock-clock section
  gains "run `baseline` first".
- **Must hold.** A test asserts `AvgPointsPerGame` is never read (CLAUDE.md
  boundary). Prefilled rows are refused exactly as today until Session 11.
- **Acceptance.** Supplied Classic (719 people) and Showdown fixtures at 1, 20
  and 150 entries produce `DELIVERABLE` files in a measured, pasted wall time.
  A pool too small for distinct lineups yields `DELIVERABLE_PARTIAL` with exact
  unfilled IDs.
- **Breakpoint.** Classic first, Showdown as `Session 04b`.
- **From Session 03b.** Build every limitation with
  `gate_registry.load_gate_registry().limitation(code, ...)`. `dk.py` and
  `lineups.py` raise prose, not codes, so the registry cannot name the parse and
  roster gates the baseline meets: give each a code and register it, which the
  completeness test demands. `contracts.DeliveryLimitation` built by hand still
  accepts `S`/`CERTIFICATION` and `P`/`CONSTRUCTION_PREFERENCE`; holding it to
  the registry's three pairs is one validator, and belongs with the first
  session that emits limitations. `certification.py` and `review_export.py`
  emit `LINEUP_{entry_id}:...`, with the Entry ID inside the code, so no
  registry can hold it: write a fixed code with the ID in the detail when this
  session touches the shared validator (late swap's `{label}_{entry_id}:` is
  Session 12's).

#### Session 05: artifact preservation

- **Depends on.** Session 03.
- **Scope.**
  - `classic_review.py:1282-1284`: keep the validated CSV and its export audit,
    and remove only the failed presentation files.
  - `cli.py:2370-2418` (Classic readable-review discrepancy): classify the
    discrepancy.
    - A roster, Entry ID or byte disagreement invalidates the CSV.
    - Any other disagreement keeps the CSV and records a presentation
      limitation.
  - `cli.py:2484-2520` (Showdown): the CSV stays in the artifact and hash
    indexes.
  - `cli.py:3169-3173`: do not delete a CSV that passed independent validation
    earlier in the run.
  - A new `src/nfl_dfs/delivery.py` writes an atomic (`os.replace`), hash-bound
    `LATEST_DELIVERABLE.json` that is revalidated before it is advertised.
- **Tests to change, visibly.** The display-failure regressions in
  `tests/test_classic_portfolio_c2.py` and `tests/test_cowork_rerun_regressions.py`
  change expectation under R28. New corruption cases prove withholding still
  happens when bytes or mapping are wrong.

#### Session 06: baseline-first `run-slate`

- **Depends on.** Sessions 04 and 05.
- **Scope.**
  - `run-slate` calls the baseline straight after intake and publishes it as
    the latest deliverable.
  - Only then does it run priors, weather, roles and solves.
  - An improvement replaces the pointer only after independent validation, with
    equal or better coverage and portfolio-wide distinctness.
  - Any failure after the baseline leaves it reachable and named in the handoff.
  - C1 (no policy, rung 4) exports through the same writer or falls back to the
    baseline, which is what makes the rung-4 promise true.
- **Acceptance.** Three runs, each producing a `DELIVERABLE` baseline, and
  `RELEASE_DECISION=DO_NOT_UPLOAD` wherever evidence is missing:
  - blocked weather with no network;
  - a forced improvement crash;
  - an improvement success that replaces the pointer.
- **Breakpoint.** Classic wiring first, Showdown as `Session 06b`.

#### Session 07: deadline controller

- **Depends on.** Session 06.
- **Scope.**
  - `nfl_cowork_run_request_v3` adds an optional `delivery_deadline_utc`. The
    default is the earliest relevant lock minus 5 minutes (R31). v2 stays
    accepted and unchanged.
  - A `Budget` object from a new `src/nfl_dfs/deadline.py` passes through every
    stage.
  - Weather retries (`fetch_weather_captures.py:108-127`, up to about 93 s per
    URL today), `sources.fetch_public_artifact` (30 s fixed, `sources.py:194`),
    solver limits and `make_classic_policy._limits` (about 480 s at the default
    `--minutes 4`) all take their allowance from the time remaining.
  - `stop_discretionary_optimization_minutes_before_lock` and
    `full_refresh_seconds` in `config/runtime.json` are read by nothing today.
    Consume them or remove them.
  - Record measured stage durations and a per-host candidate rate. The
    generator assumes 0.28 s per candidate; the C4 retrospective measured 4 to
    6 s.
- **Tests.** Pinned `now` and injected slow fetchers only. No live network.
- **Conflict.** It touches `sources.py`, so it must not run concurrently with
  Session 17.

#### Session 08: timeout incumbents

- **Depends on.** Session 06.
- **Scope.**
  - Stop discarding validated per-candidate `FEASIBLE_LIMIT` results
    (`classic_portfolio.py:542-545`).
  - Do not mark a bank blocking when it holds enough candidates and a
    policy-feasible witness (`:830-852` computes one and then throws it away).
  - `solve_classic_portfolio` (`:641-642`, `:711-720`) and
    `portfolio_enforcement.solve_policy_portfolio` (`:805-827`) extract the
    integer incumbent on a time or search limit, validate it independently, and
    return it under a non-optimal status. `OPTIMAL` stays scoped to the bank.
  - The C3 audit accepts a labelled non-optimal selection.
  - Make `test_nonoptimal_and_solver_error_selection_states_fail_closed`
    deterministic. It failed once under load in the audit, with
    `CANDIDATE_BANK_TIMEOUT` raised before its stub ran.
  - Add the missing case: a time limit with a valid incumbent
    (`value_valid=True`).
- **Acceptance.** A real HiGHS time-limited instance returns a validated
  incumbent through to export. The C2 status test passes 20 runs in a row
  (`for i in $(seq 20); do sh ./nfl.sh test tests/test_classic_portfolio_c2.py -k nonoptimal -x --tb=short || break; done`).

#### Session 09: R28 on the model path

- **Depends on.** Sessions 03b and 06. Its truth-claim limitations take their class,
  provenance and `stops` from the Session 03b registry.
- **Scope.**
  - `priors.resolve_weather_state` stops raising for a missing enum. The model
    path continues with a `WEATHER_UNOBSERVED` limitation, and the Session 03
    non-numerical test must still pass.
  - For Classic, missing official activity for a selected person becomes a
    limitation, as Showdown already treats it. A real identity or timestamp
    inconsistency still invalidates that evidence.
  - `build_priors` authority persists for the whole run request, so no mid-run
    authorization question is asked (`prior_review.py:1578-1608`).
  - The runbook's weather pre-capture (`RUNBOOK.md:758-771`) becomes an
    improvement, not a precondition.
- **Must hold.** Never fabricate an observation. `RELEASE_DECISION` stays
  `DO_NOT_UPLOAD`. The provider identity gate keeps its current behaviour; the
  baseline does not consume it.
- **[BEN: does R28 absorb the 2026-09-19 P1 hard stop?]**
  `OFFENSIVE_UNRESOLVED_MATERIAL_ROLE_CHANGE` fires for a person in
  `TRANSFER_PRIOR_UNVERIFIED` who also trips `SALARY_RANK_DIVERGENCE`; you ruled
  it stops the run. §2.5 keeps that ruling in force beside R28 without saying
  R28 amends it, so the Session 03b registry classes it `V` (stops the file) on
  that ruling. If R28 absorbs it, it becomes a current-role truth claim: the
  person is left out, the file ships, and the gap is named. Recommendation:
  absorb it, excluding the person rather than selecting him on the old-team
  share, which is the stop's own remedy text. Until you rule, no session turns
  it into a travelling limitation. It blocks nothing else on this card.

#### Session 10: relaxation controller

- **Depends on.** Sessions 07 and 08.
- **Scope.**
  - A new `src/nfl_dfs/relaxation.py` owns the rung ladder inside the Session 07
    budget.
  - The trigger list adds `PORTFOLIO_SELECTION_TIMEOUT`, the `*_SEARCH_LIMIT`
    and `*_SOLVER_ERROR` states, and `STRUCTURAL_INFEASIBILITY` to the four in
    `make_classic_policy.py:233-235`.
  - `CANDIDATE_BANK_TIMEOUT` shrinks the bank or raises the budget before it
    relaxes structure (C4 retro #3).
  - `make_showdown_policy.py` gets a real ladder.
  - Uniqueness is never on either ladder (R29).
  - Each relaxation is recorded with the constraint, class, provenance, original
    and final value, reason, time and affected entries.
- **Acceptance.** An impossible exposure cap relaxes to feasible and exports. A
  pool too small for distinct lineups reports unfilled IDs and never repeats a
  lineup. Budget exhaustion stops with the baseline intact.

#### Session 11: entry groups

- **Depends on.** Session 06.
- **Scope.**
  - Replace the whole-file `ENTRY_BLANK_CELL_AUTHORITY_REQUIRED` refusal
    (`prior_review.py:1271-1281`) with per-row authority. Prefilled rows are
    preserved byte-identical; blank rows are filled.
  - `lineups.py:143-147, 163-166` accepts a subset with preserved rows.
  - Groups by Contest ID are delivered independently, and unresolved Entry IDs
    are listed.
  - Distinctness is checked across the whole portfolio, prefilled lineups
    included.
  - `entry_ids` may bind a subset (Showdown retro #4).
- **Must hold.** Blank-cell authority is still `V`. No filled cell is ever
  changed.

#### Session 12: late-swap bridge and C5

- **Depends on.** Session 11.
- **Scope.**
  - A new contract, `nfl_submitted_entry_state_v1`: Ben's DKEntries download
    taken after upload, hash-bound and matched to the delivered file by
    Entry ID.
  - `late_swap._validate_prior_manifest` (`:249-256`, `:297-320`) accepts either
    a certified manifest or a verified submitted-state record. It never
    manufactures a certification.
  - Multi-contest handling by group replaces the single-contest refusal
    (`:400-411`).
  - Lock state comes from exact kickoff times. Locked cells stay byte-identical.
  - C5's slot ordering: prefer later-lock players in flexible slots when
    legality and the lineup are unchanged.
- **Out of scope.** Strategy aids (Session 32). The conditional-EV reoptimizer
  (Session 36).

#### Session 13: preflight report and scored player pool

- **Depends on.** Session 09.
- **Scope.**
  - A single run-start report re-derives the following against the actual
    inputs before the first solve (C4 retro #2, Showdown retro #7):
    - identity resolution;
    - pool completeness;
    - evidence states;
    - share coverage;
    - participation vocabulary.
  - `selection.write_pool_scores` output becomes a first-class, hash-bound
    artifact written as soon as scoring completes (C4 retro #4), so the
    standalone builder can consume it even if a later stage fails.
- **Note.** `preflight.py` already exists for the upload preflight. Name the
  new module so the two cannot be confused.

#### Session 14: delivery record

- **Depends on.** Sessions 07 and 10.
- **Scope.** One versioned run record holding the audit §9 fields:
  - `delivery_outcome` (`USABLE_ON_TIME`, `USABLE_LATE`, `NO_DELIVERY`) plus a
    separate invalid-attempt count;
  - requested, lock and effective deadlines, with stage timestamps;
  - coverage, including preserved, new and unresolved rows;
  - artifact identity and the supersedes chain;
  - recovery and relaxation records;
  - the intervention log: every question asked of Ben, and whether it was
    avoidable.

  "Presented" means the path and hash are in the handoff. A submission receipt
  exists only when Ben supplies a post-upload download. DraftKings is never
  fetched.

#### Session 15: delivery acceptance

- **Depends on.** Sessions 09, 11, 12, 13 and 14.
- **Scope.** A new `tests/test_delivery_scenarios.py` runs every scenario in
  audit §6 end to end, with no operator rescue:
  1. a short window;
  2. an optional feed unavailable;
  3. an infeasible exposure cap;
  4. uniqueness impossible (unfilled IDs, no repeats);
  5. a timeout with an incumbent;
  6. QA with no improvement;
  7. an optional certification failure;
  8. an enhancement crash after the baseline;
  9. one group failing;
  10. weaker diversification needed;
  11. a source that keeps timing out;
  12. presentation eating the window.

  Plus the §10 cases (missing authoritative files, no legal roster, all cells
  locked, deadline passed, corrupt bytes), each ending in an honest partial or
  `NO_DELIVERY`.
- **Acceptance.** Every scenario asserts `DELIVERY_STATE`, file validity,
  coverage and delivery before the injected deadline. It closes issue #40.

#### Session 16: real-slate rehearsal

- **Depends on.** Session 15 and O8. It runs in the Windows desktop app on Ben's
  checkout.
- **Scope.** A current Classic slate and a current Showdown slate through
  `run-slate`, measuring:
  - time to baseline;
  - improvement outcome;
  - the deadline behaviour;
  - the delivery record;
  - `.\nfl.ps1 test` on the same commit.

  Also the P7 replay on the 2026-09-20 salary snapshot (formerly operator
  item 6): Wentz and Lock at effective QB1; Mayer, Hutchinson and Bateman at
  rank 1; byte-identical replay. Absorbs C4 and SD6. Cowork is retired, so
  SD6's Cowork half is dropped.
- **Acceptance.** A `docs/RUN_RECORD_<date>.md` with the five truths, input and
  output hashes, timings, and one next action.

#### Session 17: X2 standings corpus transport

- **Depends on.** Session 00. Acceptance needs O1.
- **Spec.** `docs/chunks/X2-standings-corpus-transport.md` and archive § R27.
  The bounds there are binding: every capture invariant, hash-bind on arrival,
  credentials from the environment only, `data/standings/inbox/` never
  overwritten, no DraftKings contact.
- **Breakpoint.** If O1 is still open, stop after the authenticated fetch and
  its byte-mismatch refusal test. Leave the row `Pending` and name the
  unfinished acceptance step.

#### Session 18: P0 standings grading harness

- **Depends on.** Session 17 and O2 (O3 completes the NE@SEA era).
- **Spec.** `docs/chunks/P0-standings-grading-harness.md`. Its "repair the
  daily-failing preflight test" item is already done (2026-09-17). Drop it.
- **Acceptance.** As in the brief: 71 entries with Rank equal to Place, the
  206-way DEN@KC tie, $54,065.22 on NE@SEA, the pass-catcher lifts, under
  3 minutes on 26 files. Hand-back: Sessions 22, 23, 24 and 26 become
  startable.

#### Session 19: X3 execution postmortem

- **Depends on.** Session 00.
- **Spec.** `docs/chunks/X3-execution-postmortem.md`. If the hooks must be
  registered in `.claude/settings.json`, the pull request is protected and
  carries `ben-review`. The MCP rule lands in `.claude/rules/` unless it must go
  in `CLAUDE.md`.

#### Session 20: environment truth

- **Depends on.** Session 00.
- **Scope.**
  - X1's remaining half, per `docs/chunks/X1-egress-probe.md`:
    - per-host lines in `doctor`;
    - a `PROHIBITED_HOSTS` test asserted on the injected client's call list;
    - an offline `doctor` demonstration;
    - replacing the asserted facts at `docs/CLAUDE_CODE_SETUP.md:152-163`.

    `run-slate` already covers the run-record half.
  - The 2026-09-22 changelog's open items: `sync.ps1` has no test, and there is
    no `sync.sh`.
- **Conflict.** It touches `cli.py`, so it must not run concurrently with
  Sessions 04 to 07.

#### Session 21: prior-model triage

- **Depends on.** Session 00.
- **Scope.**
  1. The DAL@NYG Showdown retrospective (§9 #2) reported a per-game
     `TARGET_SHARE` read against a season-aggregate `ROLE_CAPACITY`, which
     would understate every player who missed time. No fix is recorded
     anywhere. Measure it on a fixture, then fix it or close it with the
     evidence.
  2. F8: propose identity matches from the alternate name fields nflverse
     ships (`first_name`/`last_name`, `football_name`, accent-folded forms) as
     **candidates for review**. The auto-accept rule is unchanged. That is why
     this needs no ruling: it adds proposals and changes no gate.

#### Sessions 22 to 29: the prize-tail program

Each card is its brief in `docs/chunks/`, unchanged except as noted here. The
program's basis is archive § "Reprioritized development program, 2026-09-15"
and `docs/STANDINGS_DUAL_OPTIMIZATION_FINDINGS_2026-09-15.md`.

- **Session 22 (P0b).** `docs/chunks/P0b-provenance-completeness.md`.
- **Session 23 (P2).** `docs/chunks/P2-contest-aware-policy.md`, plus the
  Showdown policy constraints from the DAL@NYG retrospective §9 #1 and the
  debrief's bank-cap point. Depends on Session 10 because both generators
  change there first. Uniqueness is fixed by R29 and stays off its ladder.
- **Session 24 (P3a).** `docs/chunks/P3a-scenario-bank.md`. Depends on
  Session 18, not "none": its acceptance uses P0's top-1% proxy
  (`P3a-scenario-bank.md:17-18`). The brief wins over the old queue row.
- **Session 25 (P3b).** `docs/chunks/P3b-tail-objective.md`, plus captain
  strata on a ceiling statistic, the dart specification rewrite (C4 retro #6,
  #9, #16) and DST-inclusive families.
- **Session 26 (P4a).** `docs/chunks/P4a-ownership-challenger.md`, logging
  projected against realized ownership and leverage P&L (C4 retro #11, #12,
  #15).
- **Session 27 (P4b).** `docs/chunks/P4b-copy-count.md`. If the data is too
  thin, it closes `Complete` with the accrual shortfall named. The old
  `DONE_PENDING_ACCRUAL` was never a declared status.
- **Session 28 (P6).** `docs/chunks/P6-survival-controls.md`.
- **Session 29 (P5).** `docs/chunks/P5-dilution-economics.md`. Needs O4
  ladders.

#### Session 30: standings contract v3

- **Depends on.** A ruling.
- **Open question.** [BEN: rule on the two `nfl_standings_csv_v2` contract defects found on your exports. The contract cannot represent a field member who never submitted a lineup, and it cannot hold an exact tie split that is not a whole number of cents, so `settlement._prepare_settlement` can never settle a contest with an uneven tie. Claude's recommendation: a v3 contract that carries blank field members explicitly and stores tie splits as exact fractions. Recommendations in archive § Q1B.]
- **Scope once ruled.** A new contract version (v2 never mutated), the
  normalizer, and settlement's exact comparison.

#### Sessions 31 to 36: deferred

Each row names what reactivates it. Session 34 (X4) needs re-scoping before it
runs, because the 2026-09-22 audit and this roadmap now cover most of what its
greenfield report was for. Its subagent cost contract is the part that
survives. Session 35 (C3X) stays parked by R30.

### 2.4 Audit triage

Verified by three read-only passes against `f8c6942`. None of the audit's
claims were false. Two were stronger than stated. Evidence is file:line at that
commit.

| Item | Verdict | Verified evidence | Change from the audit | Lands in |
|---|---|---|---|---|
| D1 release coupling | Modify | `release.py:115-121` adds `MODEL_NOT_PROSPECTIVELY_VALIDATED` for `MODEL_ASSISTED` only; nothing in `src/` ever sets `PROSPECTIVELY_VALIDATED`; `certification.py:182-202` writes only when certified; `prior_review.py:2336-2338` hardcodes `DO_NOT_UPLOAD` | R28 adds a fifth truth instead of loosening `RELEASE_DECISION` | Sessions 01, 03 |
| D2 no early baseline | Modify | Rung-4 print at `make_classic_policy.py:165-171`; the C1 exit sets `bulk_entry_csv: None` (`prior_review.py:3016`); exact-roster cuts and a raise (`selection.py:538-542, 572`); `CLASSIC_POLICY_UNIQUENESS_REQUIRED` (`classic_portfolio_policy.py:905-910`) | Baseline accepted; lineup reuse rejected by R29 | Sessions 01, 04, 06 |
| D3 no effective deadline | Accept | No deadline field and unknown fields rejected (`cowork.py:194-245`); two `runtime.json` keys read nowhere; weather up to about 93 s per URL; `_limits` gives about 480 s at the default | Default reserve 5 minutes (R31) | Session 07 |
| D4 CSV removed after presentation failure | Accept | `classic_review.py:1282-1284`; `cli.py:2370-2418`, `2484-2520`, `3169-3173`; `open(..., "w")` in both scripts | none | Sessions 05, 02 |
| D5 timeout incumbents rejected | Accept, stronger | `classic_portfolio.py:123-129, 542-545`, and a computed witness discarded at `830-852`; `:641-642`, `:711-720`; `portfolio_enforcement.py:805-827`; ladder triggers omit portfolio timeout (`make_classic_policy.py:233-235`); no Showdown ladder (`make_showdown_policy.py:68-82`) | none | Sessions 08, 10; documents in 01 |
| D6 fallback correctness | Accept, stronger | `build_classic_portfolio.py:254-279`; `write_dk_entries.py:49` and `assert`s at `:24, 41, 57, 67`; `qa_classic_portfolio.py:231`; `tests/test_write_dk_entries.py:139-147` expects exit 0 on a missing ID; ratchet ceiling is a no-op | The chain can ship blank rows with QA PASS; moved ahead of every other code session | Session 02 |
| D7 one blocked row blocks all | Modify | `prior_review.py:1271-1281`; `lineups.py:143-147, 163-166`; `certification.py:98-107`; `priors.py:2197-2202` | Partition accepted. The single-contest limit stays on legacy `certify`, which the operating path does not use. Provider identity keeps its gate on the model path, and the baseline does not consume it | Session 11 |
| D8 runtime handbacks | Modify | `prior_review.py:1578-1608`; `RUNBOOK.md:758-771`, `151-155`, `800-801` | "A gate no real source can clear goes to Ben" stays for development; at runtime the engine ships and names the gap | Sessions 01, 09 |
| D9 late swap needs certification | Modify | `late_swap.py:249-256`, `297-320`, `400-411` | Merged with C5; anchored on Ben's post-upload download; certification is never forged | Session 12 |
| DD-1 | Accept | as D1 | Fifth truth plus a registry | Session 03 |
| DD-2 | Accept, split | as D2 and D4 | Command, preservation, orchestration | Sessions 04, 05, 06 |
| DD-3 | Accept | as D3 | none | Session 07 |
| DD-4 | Accept, split | as D5 | Incumbents, then the controller | Sessions 08, 10 |
| DD-5 | Accept, moved first | as D6 | The fallback is the live lock-time path | Session 02 |
| DD-6 | Accept, split | as D7 and D9 | Groups, then late swap | Sessions 11, 12 |
| DD-7 | Accept, split | as D8 | Documents, then runtime | Sessions 01, 09 |
| DD-8 | Accept, split | audit §9 | Record, then scenarios; artifact identity lands with Session 05 | Sessions 05, 14, 15 |
| §4 gate register | Accept as seed | audit §4 | Seeds `config/gate_registry_v1.json`; R29 makes cross-entry uniqueness `V` by authority | Session 03 |
| §9 telemetry | Modify | audit §9 | Receipt only from operator-downloaded files; DraftKings never fetched | Session 14 |
| §10 impossible cases | Accept | audit §10 | none | Session 15 |
| Preamble: older instructions "must be reconsidered" | Modify | audit §0 | Reconsidered only through R28 to R31 and a `ben-review` pull request. Permanent boundaries 1 to 4 and 6 to 8 are unchanged | Session 01 |
| Lineup reuse "where the contest permits" (D2, §4) | Reject | none | R29: Ben keeps every lineup in a portfolio distinct | none |
| C4 retro #10, "take QB leverage first" | Reject | `STANDINGS_DUAL_OPTIMIZATION_FINDINGS_2026-09-15.md` | Each sub-5% player lowered the Classic top-1% rate; no contrarian quotas | none |

### 2.5 Rulings in force

Ben ruled the first four on 2026-09-22, in the session that wrote this file.
Session 01 writes them into `CLAUDE.md`, which outranks this file.

- **R28, delivery state.** Add `DELIVERY_STATE`, a fifth independent run truth.
  - A baseline CSV built only from the DraftKings salary and entries bytes ships
    first.
  - Truth-claim gates (official activity, current role, weather) stop
    certification and travel with the file as named limitations. They no
    longer stop construction or delivery.
  - Integrity gates (exact DraftKings IDs, hashes, entry mapping, blank-cell
    authority, locked cells, Classic/Showdown mode) still stop the file they
    protect.
  - `RELEASE_DECISION`, `CERTIFIED` and the rule against calling a prior EV,
    ROI or a probability are unchanged.
  - Absorbs R24, answers the gate half of R23, and answers F7. Whether weather
    should ever feed the model is a Q2 question (Session 36).
- **R29, distinct lineups.** Ben's words: "within a given portfolio keep all
  submitted lineups distinct and unique."
  - Uniqueness leaves the relaxable construction-preference list and is never
    relaxed.
  - When distinct lineups run out, the unfilled Entry IDs are reported and no
    lineup is repeated.
  - Lineup identity stays the existing exact-roster definition, where a
    different Showdown captain makes a different lineup.
- **R30, C3X.** Native Excel acceptance is deferred (Session 35), and C3 is
  `Complete` for software acceptance. Nothing waits on Excel.
- **R31, handoff reserve.** The default delivery deadline is 5 minutes before
  the earliest relevant lock.

Still in force from earlier, with full text in the backlog archive:

- the 2026-09-12 lock-clock ruling, amended by R28 and R29;
- the 2026-09-19 P1 hard stop on `TRANSFER_PRIOR_UNVERIFIED` with
  `SALARY_RANK_DIVERGENCE`;
- R25, depth-chart promotion (implemented by P7);
- R26, the retrospective roof column (implemented);
- R27, standings as private release assets (Session 17).

### 2.6 Operator checklist

Things only Ben can do. A session that depends on one checks its status here.

<!-- operator-table:start -->
| ID | Item | Unblocks | Status |
|---|---|---|---|
| O1 | Publish the 26 standings exports as private GitHub release assets (R27) | Session 17 acceptance | Open |
| O2 | Copy the DAL@NYG and DEN@KC salary and entry CSVs from Downloads into their `data/runs/` snapshot folders (exact names in archive § operator item 2) | Session 18 | Open |
| O3 | Pull standings for NE@SEA contests 193391019 and 193391038 | Session 18 completeness | Open |
| O4 | Paste each payout ladder at intake into `contest/payouts_<id>.csv` on the 193391013 schema | Session 29 | Open |
| O5 | Enter at least one contest per slate from a single-contest reserved-entry file | Session 36 (Q6 accrual) | Open |
| O6 | Allow `api.weather.gov` in the cloud environment's egress policy (optionally `api.sleeper.app` and `api.the-odds-api.com`) | Model-path quality in cloud sessions; after Session 06 it no longer blocks delivery | Open |
| O7 | Apply `ben-review` to the Session 01 pull request and merge it | Session 03 onward | Open |
| O8 | Current Classic and Showdown salary and entry files for a rehearsal slate, on Windows | Session 16 | Open |
| O9 | From Session 12 on, save the post-upload DKEntries download into the run folder | Session 12 on real data | Open |
| O10 | About 20 more Showdown games of standings in the inbox | Session 33 | Open |
<!-- operator-table:end -->

### 2.7 Carried-in completed work

Complete before this roadmap. Records are in the archives:

- DEV0, Q1, Q1B, Q1C, C1, C2;
- C3, closed by R30;
- P1, P1b;
- P7, whose two unmet acceptance lines moved to Session 16;
- X0, X5, H2;
- SD1 to SD5;
- R26;
- the `test_w6_live_preflight` clock pin, fixed 2026-09-17.

## 3. Retired Artifacts Log

Each entry says what the artifact held, what happened to it, and where its live
items went. Historical records stay in place as evidence. A two-line banner at
the top of each marks it superseded, and its content is unchanged.

| Artifact | What it held | Disposition | Live items went to |
|---|---|---|---|
| `backlog.md` (1,074 lines) | The 2026-09-15 and 2026-09-10 programs, the Queue table, operator items, R24 to R27, F7, F8, Next action, and three BEN flags (two C3X, one standings contract) | Moved verbatim to `docs/backlog-archive/backlog-through-2026-09-22.md`; `backlog.md` is now a pointer stub | Sessions 01 to 36; O1 to O5; C3X closed by R30; the standings flag to Session 30 |
| `tests/test_backlog_queue.py` | Pinned the backlog queue's shape | Replaced by `tests/test_roadmap_queue.py`, which pins this file's shape | Session 00 |
| `docs/SHOWDOWN_PRIORITY_TRACKER_2026-09-09.md` | SD1 to SD6; `backlog.md:17` still called it authoritative | Banner; historical | SD6 to Session 16, Cowork half dropped |
| `docs/SHOWDOWN_FIRST_PRODUCTION_PLAN.md` | Track 2 (R05 to R15) and §7 BEN items | Banner; superseded by the W tranches, then the 2026-09-15 program | Nothing open |
| `docs/PRODUCTION_READINESS_REVIEW_2026-09-08.md` | R01 to R15 and a dated week plan | Banner; expired | Nothing open |
| `docs/READINESS_REVIEW_2026-09-09.md` | A gaps table | Historical; no live items | Nothing open |
| `docs/OPENER_RUNBOOK_2026-09-09.md` | Six BEN items for the NE@SEA opener | Banner; the slate is past | Nothing open |
| `docs/CLASSIC_C4_RETROSPECTIVE_2026-09-13.md` Appendices A and B | A 19-item backlog and a session plan; code comments cite it as a tracker | Banner on Appendix A; the code comments still resolve, because the document stays | #2 and #4 to Session 13; #3 to Sessions 07 and 10; #5, #7, #8 and #14 to Session 32; #6, #9 and #16 to Session 25; #11, #12 and #15 to Session 26; #13 to Session 18; #10 rejected; #1 and #17 to #19 already done |
| `docs/SHOWDOWN_RETROSPECTIVE_2026-09-13_DAL_NYG.md` §9 | An 11-item ranked backlog | Banner on §9 | #1 to Session 23; #2 to Session 21; #4 to Session 11; #5 to Session 25; #6 (script exists, no ladder) to Session 10; #7 to Session 13; #8 to Session 18; #9 to Session 26; #3, #10 and #11 already done |
| `docs/DEBRIEF_2026-09-13_DAL_NYG_contest_195520918.md` §6 | Next-slate recommendations | Banner on §6 | DST scoring and floor to Session 25; bank cap against field-owned players to Session 23; the captain-chalk figure lived in the retired Cowork skill and retires with it |
| `docs/RUN_RECORD_20260914_DEN_KC.md` | Five open defects and a stale "Next" | Banner | P1 and P7 done; the rest to Sessions 23 to 25 |
| `plan.md` Phases 0 to 5 | An unstatused phase sequence under a "governing implementation plan" label | Banner; the architecture and safety sections stay authority #4 | This roadmap |
| `red-team-critique.md` and `docs/critiques/` (4 files) | 2026-08-28 to 2026-09-01 critiques, resolved in `plan.md` §1 | Unchanged; historical. Its "D6" is not the audit's D6 | Nothing open |
| `docs/STANDINGS_DUAL_OPTIMIZATION_FINDINGS_2026-09-15.md` and `docs/STANDINGS_GREENFIELD_FINDINGS_2026-09-15.md` | The prize-tail program's research basis | Unchanged; evidence. Greenfield §8 was dispositioned in the archived backlog | Dual §9 items to O3, O4, Sessions 22, 25, 26, 27 |
| `docs/session-prompts/` (22 files) | Paste prompts; 16 for finished work and 8 still citing `COWORK_RUNBOOK` | Moved to `docs/session-prompts/archive/`; the Quick-Start and session cards replace them | P0 to Session 18, P3a to 24, X1 to 20, X3 to 19, H3 to 01, SD6 to 16; QA1 (orphaned since 2026-09-14) to Session 31; H1 superseded by Session 00 |
| `changelog.md` entries dated 2026-09-14 to 2026-09-21 | Evidence for finished work (2,317 lines); the live file was 2,584 lines against the ledger rule's ~500-line trigger | Moved verbatim to `docs/changelog-archive/changelog-2026-09-14-through-2026-09-21.md` | Nothing open |
| `changelog.md` entries dated 2026-09-22 before the cutover (3 entries) | Evidence for the depth-role capture fix, the Windows sync command and the roof-set guard (228 lines); the live file was 567 lines against the ~500-line trigger | Moved verbatim to `docs/changelog-archive/changelog-2026-09-22.md` by Session 02, proven with `cmp` against `git show HEAD:changelog.md` | Nothing open |
| `changelog.md` entries from the 2026-09-22 cutover to Session 02 (4 entries) | Evidence for Sessions 00, 01, the Session 01 follow-up and 02 (480 lines); the live file was 904 lines against the ~500-line trigger | Moved verbatim to `docs/changelog-archive/changelog-2026-09-22-cutover-to-2026-09-23.md` after Session 02b, proven with `cmp` against `git show HEAD:changelog.md` | Nothing open |
| `docs/chunks/` (17 briefs) | Specifications | Kept as specs; the status line of each now points here | Cited by the cards |
| GitHub issue #21 | One cloud session's claim on X0 and P1, open since 2026-09-19 | Closed 2026-09-22 with a comment: both chunks done, both blockers it named resolved | none |
| GitHub issue #40 | The 2026-09-22 audit | Stays open; Session 15 closes it | Sessions 01 to 15 |
| Not found | No `_to_delete/`, backlog-inbox fragment, scratch or migration directory exists at `f8c6942` | The only `inbox` directories (`data/inbox/`, `data/standings/inbox/`) hold data, not plans | none |

## 4. Living Changelog and Progress Ledger

One row per status change, newest last. The evidence for each row is the dated
`changelog.md` entry of the same session. A merge SHA is recorded by the next
session, because a commit cannot contain its own merge.

| Date | Session ID | Status Change | Commit SHA | Operator Notes |
|---|---|---|---|---|
| 2026-09-22 | none | Audited baseline | `f8c6942` | QA audit (issue #40) ran against this commit; Linux CI `1070 passed, 1 skipped` |
| 2026-09-22 | Session 00 | Pending to In Progress | `ab54970` | Claim pushed |
| 2026-09-22 | Session 00 | In Progress to Complete | `46de154` | Rulings R28 to R31 recorded; backlog, prompts and old changelog archived; merged as PR #41 |
| 2026-09-23 | Session 01 | Pending to In Progress | `5c15bb8` | Claim pushed on `claude/determined-knuth-6hklql` |
| 2026-09-23 | Session 01 | In Progress to Complete | `1817d57` | R28 to R31 in `CLAUDE.md`; H3 live-label check; merged as PR #42; wording follow-up merged as `23bd2d8` (PR #43) |
| 2026-09-23 | Session 02 | Pending to In Progress | `a9ab747` | Claim pushed on `claude/s02-fallback-csv-l62fjm` |
| 2026-09-23 | Session 02 | In Progress to Complete | `7c5a45b` | Writer and Classic QA (items 1 and 2); merged as PR #44 |
| 2026-09-23 | Session 02b | Added as Pending | `7c5a45b` | Builder and Showdown QA (items 3 and 4), split at the card's seam; merged with PR #44 |
| 2026-09-23 | Session 02b | Pending to In Progress | `30da519` | Claim pushed on `claude/sharp-faraday-wqc7m5` |
| 2026-09-23 | Session 02b | In Progress to Complete | `d40b686` | Builder exit 3 and R29, pool filter, ratchet ceiling; Showdown QA observations; merged as PR #48 |
| 2026-09-23 | Session 03 | Pending to In Progress | `2373057` | Claim pushed on `claude/sharp-faraday-wqc7m5` |
| 2026-09-23 | Session 03 | In Progress to Complete | `b6c54d2` | `DELIVERY_STATE`, `nfl_release_truths_v2`, the R24 test; merged as PR #50 |
| 2026-09-23 | Session 03b | Added as Pending | `b6c54d2` | Gate registry, split at the card's seam; merged with PR #50 |
| 2026-09-23 | Session 03b | Pending to In Progress | `adc5b99` | Claim pushed on `claude/blissful-carson-kzkdcd` |
| 2026-09-23 | Session 03b | In Progress to Complete | recorded by the next session | 1,088 codes in 43 families, exact-code loader, completeness both ways; PR #51 |
