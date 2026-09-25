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
Consolidated and re-ranked by expected winnings on 2026-09-25 (§2.8), from a
full code review and a sweep of every plan, brief, archive and ledger.

## 1. Next Session Quick-Start

Paste this into a fresh Claude Code session:

> Read `docs/ROADMAP.md` and execute Session 37 exactly as its card in §2.3 specifies, after `python3 scripts/claim.py take S37`, on the branch your session was assigned or `claude/s37-showdown-file-integrity`. Run the card's verification command and then the full suite (`sh ./nfl.sh test` on Linux, `.\nfl.ps1 test` on Windows), and when both pass, update the status board, the progress ledger and `changelog.md` and open the pull request under `.claude/rules/git-authority.md`.

On 2026-09-25 a full code review (`docs/critiques/Code_Review_2026-09-25.md`)
and a sweep of every plan, brief, retrospective, archive and ledger were
consolidated into this board, and Ben re-prioritized it by expected winnings
(§2.8). Sessions 37, 38, 23, 21 and 17 are startable. Take 37 and 38 first:
each is a day of small fixes to defects that can put a duplicate or deleted
file in front of Ben. Session 23 (the hygiene bounds and the share cap, the
one construction change with measured lift in every graded game) and Session
21 (the prior-model unit mismatch, now confirmed) share no file with 37, 38 or
each other, so a second instance may take either. Session 17 needs only a
cloud session and O1 for its acceptance. Sessions 23b, 23c and 23d (Ben's game
theses and contest-aware assignment) follow 23 and run one at a time.

Every close-out rewrites the session number in this block to the next
startable row. `python3 scripts/repo_state.py --stdout` derives the same answer
from the table, so if the two ever disagree, the table wins.

## 2. Master Session Roadmap

### 2.1 How to read and run it

- **Order is priority.** Take the first `Pending` row whose `Depends on`
  entries are all satisfied. Row order, not the session number, is the rank:
  a number is a session's stable name (the rulings, the changelog and the
  chunk briefs cite it), and a new session takes the next free number wherever
  its row sits. Since 2026-09-25 the rank is expected winnings under R34
  (large prizes, fewer washouts), with the two integrity sessions the code
  review produced (37, 38) first because a wrong file loses the entry fee
  outright; §2.8 states the rule and what it reversed. Before that, per Ben's
  2026-09-22 instruction, every delivery session came before construction.
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
| Session 04 | Standalone | Baseline command: `nfl baseline --salaries --entries` builds distinct legal lineups from the DraftKings bytes alone, fills blank authorized rows through the exact-byte writer into a new versioned file, and reports `DELIVERY_STATE` and every unfilled Entry ID; no network | R28, R29; audit D2, DD-2 | new `src/nfl_dfs/baseline.py`, `src/nfl_dfs/cli.py`, `src/nfl_dfs/lineups.py`, `docs/DATA_CONTRACTS.md`, `docs/RUNBOOK.md` | V | Session 02, Session 03 | `sh ./nfl.sh test tests/test_baseline.py -x --tb=short`; fixture runs at 1, 20 and 150 entries with wall time | Complete |
| Session 05 | Batched | Artifact preservation: a validated CSV survives later presentation failures in both modes and in the outer exception handler; a roster, Entry ID or byte discrepancy still invalidates; an atomic, hash-bound latest-deliverable pointer | Audit D4, DD-2, DD-8 | `src/nfl_dfs/classic_review.py`, `src/nfl_dfs/cli.py`, `src/nfl_dfs/review_export.py`, new `src/nfl_dfs/delivery.py` | V | Session 03 | `sh ./nfl.sh test tests/test_classic_review_c3.py tests/test_classic_portfolio_c2.py tests/test_cowork_rerun_regressions.py tests/test_artifact_preservation.py -x --tb=short` | Complete |
| Session 06 | Standalone | Baseline-first `run-slate`: the baseline is built and published right after intake, before priors, weather, roles or solves; an improvement replaces it only after independent validation; any improvement failure leaves the baseline reachable; C1 (rung 4) ends with a CSV | Audit D2, DD-2 | `src/nfl_dfs/cli.py`, `src/nfl_dfs/cowork.py`, `src/nfl_dfs/prior_review.py`, `src/nfl_dfs/delivery.py` | V | Session 04, Session 05 | `sh ./nfl.sh test tests/test_run_slate_baseline_first.py tests/test_prior_review_profile.py tests/test_classic_prior_review.py -x --tb=short` | Complete |
| Session 06b | Standalone | R32 on the baseline: the run's official status CSV takes every person a valid `INACTIVE` row names out of the baseline's pool, before the baseline is built; only identity-valid rows count (a disagreeing row takes its person out), refused rows and an unreadable file are named, the file is snapshotted, hash-bound and re-checked by the audit; `nfl baseline --official-status` | R32; Session 06 open question | `src/nfl_dfs/baseline.py`, `src/nfl_dfs/cli.py`, `config/gate_registry_v1.json`, `docs/DATA_CONTRACTS.md`, `docs/RUNBOOK.md` | V | Session 06 | `sh ./nfl.sh test tests/test_run_slate_baseline_first.py tests/test_baseline.py -x --tb=short` | Complete |
| Session 07 | Standalone | Deadline controller: run request v3 with an optional delivery deadline (default: earliest lock minus 5 minutes); one budget passed through every stage; retries, solver limits and bank sizes set from remaining time; dead `runtime.json` keys consumed or removed; measured stage durations | R31; audit D3, DD-3; C4 retro #3 | `src/nfl_dfs/cowork.py`, new `src/nfl_dfs/deadline.py`, `src/nfl_dfs/sources.py`, `scripts/fetch_weather_captures.py`, `scripts/make_classic_policy.py`, `config/runtime.json` | P | Session 06 | `sh ./nfl.sh test tests/test_deadline_controller.py tests/test_cowork.py tests/test_fetch_weather_captures.py -x --tb=short` | Complete |
| Session 07b | Standalone | Deadline allowances, split from Session 07 at its breakpoint: `sources.fetch_public_artifact` takes its timeout from the run's budget and refuses to start a fetch the window cannot hold; the weather capture script's timeouts and retry pauses stop at the deadline; `make_classic_policy._limits` sizes the bank to the window from this host's measured candidate rate | R31; audit D3; C4 retro #3; Session 07 breakpoint | `src/nfl_dfs/sources.py`, `src/nfl_dfs/deadline.py`, `src/nfl_dfs/cli.py`, `scripts/fetch_weather_captures.py`, `scripts/make_classic_policy.py`, `config/gate_registry_v1.json` | P | Session 07 | `sh ./nfl.sh test tests/test_deadline_controller.py tests/test_fetch_weather_captures.py tests/test_classic_policy_generator.py tests/test_sources_tls.py -x --tb=short` | Complete |
| Session 08 | Standalone | Timeout incumbents: validated time-limited candidates are kept; a bank with a feasible witness does not block; both joint selectors validate and return an integer incumbent on a time or search limit under a non-optimal status; C3 accepts it labelled; the timing-sensitive C2 status test becomes deterministic | Audit D5, DD-4, §1 test failure | `src/nfl_dfs/classic_portfolio.py`, `src/nfl_dfs/portfolio_enforcement.py`, `src/nfl_dfs/selection.py`, `src/nfl_dfs/classic_review.py` | P | Session 06 | `sh ./nfl.sh test tests/test_classic_portfolio_c2.py tests/test_portfolio_enforcement.py tests/test_classic_review_c3.py -x --tb=short`; then the C2 status test 20 times in a row | Complete |
| Session 09 | Batched | R28 on the model path: missing weather (including a derived roof) and missing Classic official activity become named limitations, not stops; a real identity or timestamp conflict still invalidates its evidence; `build_priors` authority persists for the run; weather pre-capture becomes optional in the runbook | R28; audit D8, DD-7; archive § R23, R24, F7 | `src/nfl_dfs/priors.py`, `src/nfl_dfs/prior_review.py`, `src/nfl_dfs/offensive_roles.py`, `src/nfl_dfs/cowork.py`, `docs/RUNBOOK.md` | P | Session 03b, Session 06 | `sh ./nfl.sh test tests/test_prior_review_profile.py tests/test_classic_prior_review.py tests/test_gate_registry.py -x --tb=short` | Complete |
| Session 10 | Batched | Relaxation controller: the engine, not printed advice, walks a bounded rung ladder inside the cumulative budget; the full trigger list; bank timeouts shrink the bank before relaxing structure; Showdown gets a real ladder; uniqueness is never on it; every relaxation is a structured record | R29; audit D5, DD-4; Showdown retro #6; C4 retro #3 | new `src/nfl_dfs/relaxation.py`, `scripts/make_classic_policy.py`, `scripts/make_showdown_policy.py`, `src/nfl_dfs/cli.py` | S | Session 07, Session 07b, Session 08 | `sh ./nfl.sh test tests/test_relaxation_controller.py tests/test_classic_policy_generator.py -x --tb=short` | Complete |
| Session 11 | Standalone | Entry groups: prefilled rows are preserved byte-identical instead of refusing the file; blank rows are filled; each Contest ID group is delivered on its own; unresolved Entry IDs are listed; distinctness covers prefilled lineups; `entry_ids` may bind a subset | R29; audit D7, DD-6; Showdown retro #4 | `src/nfl_dfs/lineups.py`, `src/nfl_dfs/prior_review.py`, `src/nfl_dfs/baseline.py`, `src/nfl_dfs/dk.py` | V | Session 06 | `sh ./nfl.sh test tests/test_entry_groups.py tests/test_byte_line_fidelity.py -x --tb=short` | Complete |
| Session 11b | Standalone | Subset binding, split from Session 11 at its breakpoint: a policy's `entry_ids` may bind a subset of the fillable blank rows, in template order (a bound prefilled or unknown row is still a `V` refusal); after the policy's joint solve C1 fills the unbound blank rows with every policy lineup and every prefilled roster as no-goods; the relaxation ladder and each rung's document bind the same subset | Showdown retro #4 and §7c; Session 11 breakpoint | `src/nfl_dfs/portfolio_policy.py`, `src/nfl_dfs/classic_portfolio_policy.py`, `src/nfl_dfs/prior_review.py`, `src/nfl_dfs/selection.py`, `src/nfl_dfs/relaxation.py`, `src/nfl_dfs/cli.py`, `docs/DATA_CONTRACTS.md` | S | Session 11 | `sh ./nfl.sh test tests/test_entry_groups.py tests/test_relaxation_controller.py tests/test_portfolio_policy.py -x --tb=short` | Complete |
| Session 11c | Standalone | C2 and C3 over a subset policy, split from Session 11b at its breakpoint: C2's joint solve fills the policy's rows and C1 the unbound rows, with every C2 lineup and prefilled roster as no-goods; prior_review's C2 records, the C2 audit and C3's package split policy rows from C1 rows; C3 names each row's source; the three `CLASSIC_POLICY_SUBSET_UNSUPPORTED` refusals go | Showdown retro #4 and §7c; Session 11b breakpoint | `src/nfl_dfs/selection.py`, `src/nfl_dfs/prior_review.py`, `src/nfl_dfs/classic_review.py`, `src/nfl_dfs/classic_portfolio.py`, `src/nfl_dfs/cli.py`, `docs/DATA_CONTRACTS.md` | S | Session 11b | `sh ./nfl.sh test tests/test_entry_groups.py tests/test_classic_review_c3.py tests/test_classic_portfolio_c2.py -x --tb=short` | Complete |
| Session 37 | Batched | Showdown file integrity: the Showdown policy validator refuses `require_unique_lineups: false` and the audit's duplicate check is unconditional (R29); `qa_showdown_portfolio.py` exempts only the template's blank rows, compares raw lines, exits 3 on a sanctioned unfilled row, keeps operator limits out of the validity exit and identifies people by ID; the Showdown no-policy entry re-parse goes and the entry-hash stop applies in every mode; C3 packaging catches every exception; `referee.py` names an empty physical line | Code review 2026-09-25 V1, V2, V9, V10, V11, E12; changelog 2026-09-23 (Session 02b) | `src/nfl_dfs/portfolio_policy.py`, `src/nfl_dfs/portfolio_enforcement.py`, `scripts/qa_showdown_portfolio.py`, `src/nfl_dfs/prior_review.py`, `src/nfl_dfs/referee.py`, `tests/test_portfolio_enforcement.py`, `tests/test_qa_showdown_portfolio.py` | V | none | `sh ./nfl.sh test tests/test_portfolio_policy.py tests/test_portfolio_enforcement.py tests/test_qa_showdown_portfolio.py tests/test_prior_review_profile.py -x --tb=short`; seam: the policy flag and the QA script first | Pending |
| Session 38 | Batched | Run-path integrity: the review workbook is built before `certify_upload` and no handler deletes a file whose manifest hash matches; `nfl.ps1` accepts `baseline`; an existing `outputs/<run_id>` is refused like `data/runs/<run_id>`; `status` re-derives or labels stored truths and never exits 0 on a stored `CERTIFIED`; the exception exit of a `prior_review` run reports `PRIOR_ONLY`; `certify` and `validate` take per-row authority from `plan_entries` | Code review V3 to V8 | `src/nfl_dfs/cli.py`, `nfl.ps1`, `src/nfl_dfs/certification.py`, `tests/test_certification.py`, `tests/test_cowork.py`, `tests/test_artifact_preservation.py` | V | none | `sh ./nfl.sh test tests/test_certification.py tests/test_cowork.py tests/test_artifact_preservation.py tests/test_run_slate_baseline_first.py -x --tb=short`; seam: per-row certify authority last | Pending |
| Session 23 | Standalone | P2 part 1, structural hygiene: Showdown policy v2 and Classic bounds (`qb_count`, `pass_catchers_with_rostered_qb`, `salary_left`, `kicker_count`, `dst_count`, `offense_against_own_dst`), each recomputed in the audit from roster bytes; portfolio-wide `max_person_share` (default 0.80; the one share limit Sessions 23b and 23c reuse) audited and reported with the person named; generator defaults from the four-game-stable set, kickers and DSTs never excluded; a default captain cap and a captain-spread column; the new bounds on the relaxation ladder in the brief's order | Chunk P2; standings findings §8.1 C, §8.2 H and I; code review S7; R33, R34 | `src/nfl_dfs/portfolio_policy.py`, `src/nfl_dfs/classic_portfolio_policy.py`, `src/nfl_dfs/portfolio_enforcement.py`, `src/nfl_dfs/classic_portfolio.py`, `scripts/make_showdown_policy.py`, `scripts/make_classic_policy.py`, `src/nfl_dfs/relaxation.py`, `docs/DATA_CONTRACTS.md` | S | Session 10 | `sh ./nfl.sh test tests/test_portfolio_policy.py tests/test_classic_policy_generator.py tests/test_portfolio_enforcement.py tests/test_relaxation_controller.py -x --tb=short`; acceptance on the supplied fixtures; grading the rerun against standings is Session 18b | Pending |
| Session 21 | Batched | Prior-model triage: the season-sum share against per-game capacity mismatch, confirmed by the 2026-09-25 review at `priors.py:1541-1565` and `:1661-1680`, becomes per-game rates under a new transformation version; the transfer pseudo-count scales by the team's expected pool, not the incumbents'; F8 alternate-name identity proposals for review with auto-accept unchanged; `tests/test_priors_adapter.py:44`'s hardcoded `AS_OF` pins `now` | Showdown retro §9 #2; archive § F8; code review S1, S2 | `src/nfl_dfs/priors.py`, `src/nfl_dfs/prior_score.py`, `src/nfl_dfs/opportunity.py`, `docs/DATA_CONTRACTS.md`, `tests/test_priors_adapter.py` | P | none | `sh ./nfl.sh test tests/test_priors_adapter.py tests/test_offensive_roles.py tests/test_prior_selection.py -x --tb=short`; a fixture player who missed games projects at his per-game rate | Pending |
| Session 17 | Standalone | X2: the 26 standings exports become private GitHub release assets, fetched with authentication through `sources.py` and hash-bound on arrival | Chunk X2; archive § R27 | `src/nfl_dfs/sources.py`, a retrieval script, `docs/DATA_CONTRACTS.md` | P | Session 00 | `sh ./nfl.sh test tests/test_source_ledger.py tests/test_sources_tls.py tests/test_standings_transport.py -x --tb=short`; acceptance needs O1 | Pending |
| Session 39 | Batched | Classic diversification: a Classic person-overlap cap on C1 and every unbound fill row (a construction preference on the ladder, default 6); the C2 witness chain honours the policy overlap and round-robins seeds and slots; policy exclusions bind fill rows; a fill that runs out of distinct lineups delivers the bound rows and names the unfilled Entry IDs (R29) | Code review S3 to S6; standings findings §5.1, §5.5; `IMPLEMENTATION_STATUS.md` Session 11c "not yet" | `src/nfl_dfs/selection.py`, `src/nfl_dfs/classic_portfolio.py`, `src/nfl_dfs/prior_review.py`, `src/nfl_dfs/relaxation.py`, `scripts/make_classic_policy.py` | S | Session 23 | `sh ./nfl.sh test tests/test_prior_selection.py tests/test_classic_portfolio_c2.py tests/test_entry_groups.py tests/test_relaxation_controller.py -x --tb=short`; seam: the overlap cap and exclusions first, the partial fill second | Pending |
| Session 23b | Standalone | P8 part 1, thesis structures: a Showdown thesis contract (name, teams, a required captain set with kickers and DSTs allowed, per-team and per-position bounds, exclusions) validated as a policy sleeve; a single-thesis build whose captain comes from the thesis's set and whose structure the ladder never relaxes (a thesis that cannot be built is dropped and named); backup quarterbacks out of the pool by default from depth evidence; each lineup names its thesis | Chunk P8; R33, R34; ATL@GB 2026-09-24; Showdown retro §7c | `src/nfl_dfs/portfolio_policy.py`, `src/nfl_dfs/portfolio_enforcement.py`, `src/nfl_dfs/selection.py`, `src/nfl_dfs/relaxation.py`, `scripts/make_showdown_policy.py`, `docs/DATA_CONTRACTS.md` | S | Session 23 | `sh ./nfl.sh test tests/test_portfolio_policy.py tests/test_portfolio_enforcement.py tests/test_relaxation_controller.py -x --tb=short`, plus the tests it adds; a fixture thesis that requires a kicker captain builds one | Pending |
| Session 23c | Standalone | P8 part 2, the thesis portfolio: rows allotted across Ben's theses; one joint assembly with every lineup distinct across theses and prefilled rows (R29), the one share limit from Session 23, captains spread across theses; the review reports per Entry ID the thesis, captain counts per thesis, every person in more than half the rows and the most rows one player's bad night sinks; ATL@GB and NE@SEA replays | Chunk P8 "Done looks like"; R34 | `src/nfl_dfs/selection.py`, `src/nfl_dfs/portfolio_enforcement.py`, `src/nfl_dfs/prior_review.py`, `src/nfl_dfs/readable_review.py`, `docs/DATA_CONTRACTS.md` | S | Session 23b | `sh ./nfl.sh test tests/test_portfolio_policy.py tests/test_entry_groups.py tests/test_readable_review.py -x --tb=short`, plus the tests it adds; the 20-row fixture spreads across six theses with no repeat and no player over the share limit | Pending |
| Session 23d | Batched | P2 part 2, contest-aware assignment: assignment order as a policy input (`prior_points_desc`, `round_robin_by_contest` as the default, `tail_proxy_desc` once a tail statistic exists); `contest_facts_csv` (contest id, field size, places paid, entry fee) tags each entry's paid fraction and labels entries under 5% `FIRST_PLACE_OBJECTIVE`, never from a contest name; a contest-screening checklist (rake, overlay, payout shape, field size, max entries) in the runbook | Chunk P2; debrief §4, §6; RUN_RECORD DEN@KC defect 5; `plan.md:395`; critique V9 | `src/nfl_dfs/selection.py`, `src/nfl_dfs/portfolio_policy.py`, `src/nfl_dfs/classic_portfolio_policy.py`, `src/nfl_dfs/contracts.py`, `docs/DATA_CONTRACTS.md`, `docs/RUNBOOK.md` | S | Session 23 | `sh ./nfl.sh test tests/test_prior_selection.py tests/test_portfolio_policy.py -x --tb=short`; the satellite rows no longer receive the lowest-prior lineups on the DEN@KC fixture | Pending |
| Session 12 | Standalone | Late-swap bridge and C5: a hash-bound record of the entries actually submitted (Ben's post-upload DKEntries download) anchors governed late swap without claiming certification; multi-contest by group; locked cells byte-identical; later-lock players preferred in flexible slots; the `--as-of` clock is refused when it disagrees with the wall clock past a registered tolerance; current cells in the `Name (ID)` form resolve through `prefilled_cell_id`; a post-kickoff salary export parses | Audit D9, DD-6; archive § C5; code review V12, V13, E11 | `src/nfl_dfs/late_swap.py`, `src/nfl_dfs/lineups.py`, `src/nfl_dfs/cli.py`, `src/nfl_dfs/dk.py`, `docs/DATA_CONTRACTS.md` | V | Session 11 | `sh ./nfl.sh test tests/test_governed_late_swap.py tests/test_late_swap_learning.py -x --tb=short`; seam: the clock bound and the `(ID)` form first, the submitted-state contract second | Pending |
| Session 41 | Batched | Weather and retrieval boundary: `fetch_weather_captures.py` obeys `sources.ALLOWED_HOSTS` on every resolved URL, refuses redirects, writes the response bytes verbatim and records the fetch time; weather expiry is `min(observed_at + 6h, lock)` in the formatter and re-derived in `prior_review`; one retractable-roof set, pinned by a test | Code review E1, E2, E3; `CLAUDE.md` retrieval boundary | `scripts/fetch_weather_captures.py`, `scripts/make_classic_weather_evidence.py`, `src/nfl_dfs/prior_review.py`, `src/nfl_dfs/venues.py`, `tests/test_fetch_weather_captures.py` | V | none | `sh ./nfl.sh test tests/test_fetch_weather_captures.py tests/test_venues.py tests/test_prior_review_profile.py tests/test_repo_boundaries.py -x --tb=short`; a redirect to another host is refused in a test | Pending |
| Session 44 | Standalone | `prior_review` decomposition part 1: the Classic publication block (`:2667-3157`) and the C3 export block (`:3159-3299`) move to `classic_publish.py` behind a frozen context dataclass; every blocker text and artifact byte unchanged; the early-return exits keep the INTAKE stage and the profile variable | Code review R1, R5 | new `src/nfl_dfs/classic_publish.py`, `src/nfl_dfs/prior_review.py` | P | Session 23c | `sh ./nfl.sh test tests/test_classic_prior_review.py tests/test_classic_review_c3.py tests/test_entry_groups.py tests/test_prior_review_profile.py -x --tb=short`, then the full suite; fixture artifact hashes byte-identical before and after | Pending |
| Session 44b | Standalone | Decomposition part 2: intake and evidence binding (`:1439-1706`) to `review_intake.py`, priors and projection (`:1723-2121`) to `review_priors.py`; `EVIDENCE_STATE` computed once above the mode split; one truths builder replaces the five `FILE_VALID` literals; `review_common.py` holds hash-alias resolution, strict JSON loading and canonical bytes; the status workbook takes the run clock | Code review R1 to R4, R6 | new `src/nfl_dfs/review_intake.py`, new `src/nfl_dfs/review_priors.py`, new `src/nfl_dfs/review_common.py`, `src/nfl_dfs/prior_review.py`, `src/nfl_dfs/review_export.py`, `src/nfl_dfs/readable_review.py`, `src/nfl_dfs/classic_review.py`, `src/nfl_dfs/workbook.py`, `src/nfl_dfs/cli.py` | P | Session 44 | `sh ./nfl.sh test tests/test_prior_review_profile.py tests/test_readable_review.py tests/test_release_truths.py -x --tb=short`, then the full suite; `run_prior_review` under 600 lines | Pending |
| Session 24 | Batched | Simulator correctness before it becomes the operating bank: sacks subtracted from attempts; a zero-share group stays zero and is named; turnovers split by the registered interception fraction; kicker mix, PAT rate and return touchdowns from the frozen artifact; the dead importance weights and tail oversampling go; `SIMULATION_VERSION`, `OWNERSHIP_PRIOR_VERSION` and `FIELD_MODEL_VERSION` registered with `does_not_establish`; a test per fixed defect | Code review M1, M2, M4, M5, M8, M9; PRR R10 | `src/nfl_dfs/simulation.py`, `src/nfl_dfs/ownership.py`, `src/nfl_dfs/field.py`, `src/nfl_dfs/cli.py`, `config/runtime.json`, `tests/test_simulation.py` | P | none | `sh ./nfl.sh test tests/test_simulation.py tests/test_ownership_field.py -x --tb=short`; a 560-attempt, 42-sack fixture yields attempts, not dropbacks | Pending |
| Session 24b | Standalone | P3a: a bounded DESIGN scenario bank on the `prior_review` path, with p50, p90 and p99 per lineup and candidate, the correlation table against the frozen team stats, conservation checks within the registered wall time and RSS; the top-1% proxy is a registered constant from the 2026-09-15 findings until Session 18b replaces it | Chunk P3a; code review §1 | `src/nfl_dfs/simulation.py`, `src/nfl_dfs/prior_review.py`, `src/nfl_dfs/readable_review.py`, `src/nfl_dfs/classic_review.py`, `config/runtime.json` | P | Session 24, Session 44b | `sh ./nfl.sh test tests/test_simulation.py tests/test_readable_review.py -x --tb=short`; the p90 ranking differs from the mean ranking on the supplied fixtures; replay byte-identical | Pending |
| Session 24c | Batched | Market-anchored team scoring and a field that spends the cap: a registered rate that scales prior-season scoring by the implied total and spread; per-player reception and yardage variance; one FLEX mix shared by ownership and field; cap-targeted field sampling | Code review M3, M6, M7 | `src/nfl_dfs/simulation.py`, `src/nfl_dfs/field.py`, `src/nfl_dfs/ownership.py`, `docs/DATA_CONTRACTS.md` | P | Session 24 | `sh ./nfl.sh test tests/test_simulation.py tests/test_ownership_field.py -x --tb=short`; a 7-point favourite in a 52 total scores above its prior-season rate | Pending |
| Session 25 | Standalone | P3b part 1: `TAIL_QUANTILE_OF_DESIGN_BANK` registered as an objective version; tail-family strata (5-1, DST-inclusive, single-QB single-stack, QB+2, QB+3, RB bring-back, secondary-game stack); the expectation-only control portfolio written as `control_assignment.json`, never exported | Chunk P3b; C4 retro #6, #9, #16 | `src/nfl_dfs/selection.py`, `src/nfl_dfs/candidate_families.py`, both policy contracts, `docs/DATA_CONTRACTS.md` | S | Session 23d, Session 24b | `sh ./nfl.sh test tests/test_prior_selection.py tests/test_candidate_sources_store.py -x --tb=short`; a synthetic contest with a known tail optimum is recovered | Pending |
| Session 25b | Standalone | P3b part 2: `tail_sleeve_entries = k` in the joint assignment under the Session 23 controls; captain strata on a ceiling statistic; the dart rules (short one named prior, a defined role, 2 to 12% ownership when an estimate exists); the REFEREE bank re-scores the assignment with a registered tolerance | Chunk P3b; Showdown retro §7b, §7e; C4 retro §16 to §20 | `src/nfl_dfs/selection.py`, `src/nfl_dfs/portfolio_enforcement.py`, `src/nfl_dfs/classic_portfolio.py`, `src/nfl_dfs/prior_review.py`, `docs/DATA_CONTRACTS.md` | S | Session 25 | `sh ./nfl.sh test tests/test_prior_selection.py tests/test_portfolio_enforcement.py -x --tb=short`; a k=6 sleeve on the DEN@KC fixture holds a DST lineup and a 5-1 on each side | Pending |
| Session 28 | Standalone | P6: scenario-cluster coverage, bank-estimated P(zero paid), sleeve-size frontier | Chunk P6; R34 | `src/nfl_dfs/portfolio.py`, `src/nfl_dfs/prior_review.py`, `src/nfl_dfs/readable_review.py` | S | Session 25b | `sh ./nfl.sh test tests/test_readable_review.py -x --tb=short` | Pending |
| Session 18 | Standalone | P0 part 1: `nfl grade-standings` normalises the corpus, classifies mode from roster geometry, joins names to the same-slate salary file with zero tolerance, writes per-contest thresholds, our entries' rank, percentile and copy count, and tie-pooled prizes when a ladder exists; metric definitions in one registered module; the DAL@NYG and DEN@KC snapshots filed | Chunk P0 | new `src/nfl_dfs/standings_grade.py`, new `src/nfl_dfs/standings_metrics.py`, `src/nfl_dfs/cli.py`, new `scripts/grade_standings.py`, new `tests/test_standings_grade.py` | P | Session 17, O2 | `sh ./nfl.sh test tests/test_standings_grade.py -x --tb=short`; 71 entries with Rank equal to Place, the 206-way DEN@KC tie, $54,065.22 on NE@SEA | Pending |
| Session 18b | Standalone | P0 part 2: field feature lifts, duplication share of the top 1%, the concentration table, the seeded hygiene bootstrap, our exposure against the field; grades the Session 23 rerun and Session 24b's bank on the archived fields and replaces the proxy constant | Chunk P0; chunks P2 and P3a acceptance | `src/nfl_dfs/standings_grade.py`, `src/nfl_dfs/standings_metrics.py`, `tests/test_standings_grade.py` | P | Session 18, Session 23, Session 24b | `sh ./nfl.sh test tests/test_standings_grade.py -x --tb=short`; the pass-catcher lifts 1.60/1.53/2.08/1.39, the Classic sub-5% rate 2.08%, 8,007 portfolios, under 3 minutes on 26 files | Pending |
| Session 26 | Standalone | P4a: mass-conserving ownership challenger graded by slate, with projected against realized ownership logged | Chunk P4a; C4 retro #11, #12, #15 | `src/nfl_dfs/ownership.py`, `src/nfl_dfs/prior_review.py` | P | Session 18b | `sh ./nfl.sh test tests/test_ownership_field.py -x --tb=short` | Pending |
| Session 27 | Standalone | P4b: exact-lineup copy-count predictor | Chunk P4b | `src/nfl_dfs/field.py`, `src/nfl_dfs/prior_review.py` | P | Session 26 | `sh ./nfl.sh test tests/test_ownership_field.py -x --tb=short` | Pending |
| Session 29 | Standalone | P5: dilution-aware first-place value with real payout ladders | Chunk P5 | `src/nfl_dfs/payouts.py`, `src/nfl_dfs/economics.py`, `src/nfl_dfs/selection.py` | P | Session 25b, Session 27, O4 | `sh ./nfl.sh test tests/test_payouts.py -x --tb=short` | Pending |
| Session 13 | Batched | Run-start preflight report (identity, pool completeness, evidence and participation vocabulary against the actual inputs, one report before the first solve) and the scored player pool as a first-class hash-bound artifact that names kicker zero-shares and offense exclusions; the session probe stops counting `api.weather.gov` as blocking | C4 retro #2, #4; Showdown retro #7; audit §5; changelog 2026-09-23 and 2026-09-24 open items | `scripts/session_probe.py`, `src/nfl_dfs/selection.py`, `src/nfl_dfs/prior_review.py` | P | Session 44b | `sh ./nfl.sh test tests/test_session_probe_gate.py tests/test_prior_selection.py tests/test_preflight_report.py -x --tb=short` | Pending |
| Session 14 | Batched | Delivery record: `delivery_outcome`, timing, coverage, artifact identity, recovery, relaxation and intervention fields in one versioned run record; "presented" means path and hash in the handoff; submission receipt only from an operator-downloaded file | Audit §9, DD-8 | `src/nfl_dfs/delivery.py`, `src/nfl_dfs/cli.py`, `docs/DATA_CONTRACTS.md` | P | Session 44b | `sh ./nfl.sh test tests/test_delivery_record.py -x --tb=short` | Pending |
| Session 15 | Standalone | Delivery acceptance part 1: audit §6 scenarios 1 to 6 (short window, optional feed unavailable, infeasible cap, uniqueness impossible, timeout with an incumbent, QA with no improvement) and the §10 impossible cases end to end with an injected clock and faults and no operator rescue | Audit §6, §10, DD-8 | new `tests/test_delivery_scenarios.py` and its fixtures | V | Session 12, Session 13, Session 14, Session 38 | `sh ./nfl.sh test tests/test_delivery_scenarios.py -x --tb=short` | Pending |
| Session 15b | Standalone | Delivery acceptance part 2: scenarios 7 to 12 (optional certification failure, enhancement crash after the baseline, one group failing, weaker diversification needed, a source that keeps timing out, presentation eating the window); closes issue #40 | Audit §6, DD-8 | `tests/test_delivery_scenarios.py` and its fixtures | V | Session 15 | `sh ./nfl.sh test tests/test_delivery_scenarios.py -x --tb=short`, then the full suite | Pending |
| Session 16 | Standalone | Real-slate rehearsal on Windows, Classic and Showdown, on current files: time to baseline, improvement, deadline and record; the P7 replay on the 2026-09-20 snapshot; the hooks confirmed to fire under the desktop app's shell | Archive § C4 and operator item 6; Showdown tracker SD6; code review H4 | the run folder, a new `docs/RUN_RECORD_<date>.md`, `changelog.md` | V | Session 15b, O8 | `.\nfl.ps1 test` green; the run record shows five truths, time to baseline and delivery time against the deadline | Pending |
| Session 42 | Batched | Official-status and identity discipline: a registered official-source host list for the activity, eligibility and inactive-report gates; `make_official_status.py` exits non-zero outside its window and gets a test; the depth-chart binding is labelled a normalised-name proposal; naive clocks raise in `kicker_roles`; inactives are checked before the due-time branch; timezone validators on every contract timestamp; `verify_projection_package` runs where the ledger is validated | Code review E4 to E8, M10; OPENER_RUNBOOK §261-273; PRR :268 | `src/nfl_dfs/evidence.py`, `scripts/make_official_status.py`, `scripts/make_offensive_role_evidence.py`, `src/nfl_dfs/qb_depth_roles.py`, `src/nfl_dfs/kicker_roles.py`, `src/nfl_dfs/contracts.py`, `src/nfl_dfs/projection.py`, `src/nfl_dfs/cli.py` | V | none | `sh ./nfl.sh test tests/test_source_ledger.py tests/test_kicker_roles.py tests/test_qb_depth_roles.py tests/test_projection_producer.py tests/test_governed_late_swap.py -x --tb=short` | Pending |
| Session 43 | Batched | Harness holes: `check_protected_paths.py` diffs with `--no-renames`; the guard refuses global options before the verb, a quoted `main`, `commit -a`, `restore`, `checkout --`, `gc --prune`, `reflog expire`, `git add -N .` and a redirected `git add .`; a test for `record_verify.summary_line`; the session-start truncation note names a file that exists | Code review H1, H2, H4, H5; changelog 2026-09-23 (Session 03) | `scripts/check_protected_paths.py`, `.claude/hooks/guard_bash.py`, `.claude/hooks/session_start.py`, `scripts/record_verify.py`, `tests/test_repo_boundaries.py`, `tests/test_harness_orientation.py` | P | none | `sh ./nfl.sh test tests/test_repo_boundaries.py tests/test_harness_orientation.py -x --tb=short`; `python3 scripts/check_protected_paths.py` | Pending |
| Session 19 | Standalone | X3: automatic run postmortem on success and failure, abandoned-run recovery sweep, compaction continuity, the rule that MCP output is never evidence, and the merge gate: a PreToolUse hook that refuses `merge_pull_request` unless the head's `suite`, `boundaries` and `protected-paths` runs are green, with `windows` named in the green rule | Chunk X3; code review H3 | `.claude/hooks/`, `.claude/rules/`, `.claude/settings.json` (protected) | P | none | `sh ./nfl.sh test tests/test_harness_orientation.py tests/test_repo_boundaries.py -x --tb=short`; `grep -rn "MCP" .claude/rules/` finds the rule | Pending |
| Session 20 | Batched | X1 per-host egress lines in `doctor` with a prohibited-host test; `docs/CLAUDE_CODE_SETUP.md` facts replaced by the probe; a test for `sync.ps1` | Chunk X1; changelog 2026-09-22 "left open" | `src/nfl_dfs/cli.py`, `scripts/session_probe.py`, `docs/CLAUDE_CODE_SETUP.md`, `sync.ps1` | P | none | `sh ./nfl.sh test tests/test_session_probe.py -x --tb=short`; `sh ./nfl.sh doctor` completes offline | Pending |
| Session 40 | Batched | Solver time under the lock clock: a Showdown bank that stops at its limit with enough candidates and a witness is `BOUNDED`, not blocking; tie-breaks above the solver gap; `stack_value` indexes once and bank generation runs without `tracemalloc`; the C2 witness solve is reused by the final joint solve; the rate ledger's temp name is per process; the baseline runs on the budget clock | Code review S8, S9, S10, R9; changelog 2026-09-24 (Session 08) | `src/nfl_dfs/portfolio_enforcement.py`, `src/nfl_dfs/classic_portfolio.py`, `src/nfl_dfs/relaxation.py`, `src/nfl_dfs/deadline.py`, `src/nfl_dfs/cli.py` | P | Session 39 | `sh ./nfl.sh test tests/test_portfolio_enforcement.py tests/test_classic_portfolio_c2.py tests/test_relaxation_controller.py tests/test_deadline_controller.py -x --tb=short`; the 20-entry Showdown fixture's bank time measured before and after | Pending |
| Session 22 | Standalone | P0b: run-folder provenance completeness, manifests for hand-built entries, a pre-registration record per slate | Chunk P0b | `src/nfl_dfs/prelock_manifest.py`, `src/nfl_dfs/prior_review.py`, new `src/nfl_dfs/preregistration.py` | P | Session 18 | `sh ./nfl.sh test tests/test_prelock_manifest.py -x --tb=short` | Pending |
| Session 45 | Batched | Ledger and contract truth: `docs/DATA_CONTRACTS.md` documents the v2 source ledger and the seven undocumented version strings; `make_classic_policy.py:174` stops claiming rung 4 always produces a legal portfolio; `sync.ps1` stops printing `git add -A`; the runbook states each command's exit-code semantics; `make_settlement_request` requires a schema version on the truths it copies; the X4 report location settled on `docs/` | Code review E9, E10, H6, §8; changelog 2026-09-23 | `docs/DATA_CONTRACTS.md`, `scripts/make_classic_policy.py`, `sync.ps1`, `docs/RUNBOOK.md`, `scripts/make_settlement_request.py`, `docs/chunks/X4-greenfield-spec.md` | P | none | `sh ./nfl.sh test tests/test_settlement_request_builder.py tests/test_classic_policy_generator.py -x --tb=short`; `grep -n "always produces" scripts/make_classic_policy.py` is empty | Pending |
| Session 46 | Batched | Dead code and the legacy path: remove the unreferenced functions, contract classes, runtime keys, imports and dependencies the review lists; wire legacy `select` to per-row authority or retire it; decide `build`, `project` and `run`; the status workbook and the HTML render from one row model; the registered profile's build sized by the budget | Code review §8, V14, R7, R8 | `src/nfl_dfs/cli.py`, `src/nfl_dfs/opportunity.py`, `src/nfl_dfs/participation.py`, `src/nfl_dfs/priors.py`, `src/nfl_dfs/field.py`, `src/nfl_dfs/payouts.py`, `src/nfl_dfs/sources.py`, `src/nfl_dfs/evidence.py`, `src/nfl_dfs/late_swap.py`, `src/nfl_dfs/lifecycle.py`, `src/nfl_dfs/depth_roles.py`, `src/nfl_dfs/contracts.py`, `src/nfl_dfs/workbook.py`, `config/runtime.json`, `pyproject.toml`, `uv.lock`, `scripts/verify_operator_workbook.mjs` | P | Session 24c | `sh ./nfl.sh test -x --tb=short` (the full suite is the test); `python3 -c "import nfl_dfs.cli"` | Pending |
| Session 30 | Standalone | Standings contract v3: represent field members who never submitted a lineup and exact tie splits that are not whole cents, so a contest with ties can settle | Archive § 2026-09-14 close-out; Q1B | `src/nfl_dfs/settlement.py`, `scripts/file_standings.py`, `docs/DATA_CONTRACTS.md` | P | BEN ruling | `sh ./nfl.sh test tests/test_standings_normalizer.py tests/test_reference_settlement.py -x --tb=short` | Pending |
| Session 31 | Standalone | QA1: adversarial QA whose findings are policy deltas, with a Pareto filter and at most three iterations | Archived QA1 prompt; archive § QA1 | new `src/nfl_dfs/adversarial_qa.py` | S | Session 25b | Reactivate when Session 25b is `Complete` | Deferred |
| Session 32 | Standalone | Late-swap strategy aids: a swap QA gate, a salary reserve, swap-flexible entry tags, points per $1,000 of locked salary | C4 retro #5, #7, #8, #14 | `scripts/qa_classic_portfolio.py`, `src/nfl_dfs/late_swap.py` | S | Session 12, Session 25b | Reactivate when both are `Complete` | Deferred |
| Session 33 | Standalone | P4c: contest-conditioned field effects with shrinkage | Chunk P4c | `src/nfl_dfs/field.py` | P | Session 27, O10 | Reactivate at about 20 more Showdown games with standings | Deferred |
| Session 34 | Standalone | X4: greenfield spec report and subagent cost contract | Chunk X4 | a new report in `docs/` | P | Session 17, Session 19, Session 20 | Re-scope first: the audit, the 2026-09-25 review and this roadmap now cover most of its report | Deferred |
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
- **2026-09-23, Complete (Classic and Showdown).** `nfl baseline` in
  `baseline.py`: schema binding, snapshots, exact IDs cross-checked against the
  entries player table, `unavailable_people`, `BASELINE_SALARY_RANK_V1` (salary
  levels, a per-lineup seed), a 5 s solve limit and 60 s run budget,
  `DK_BASELINE_ENTRY_V1_<run_id>.csv` through `write_upload_bytes(unfilled=)`,
  an audit of the bytes on disk, `nfl_release_truths_v2`. All six fixture runs
  `DELIVERABLE` (Classic 150 in 3.6 s, Showdown 150 in 6.5 s); the small pool is
  `DELIVERABLE_PARTIAL` naming its two rows. Every `dk.py` and `lineups.py`
  refusal has a code; `LINEUP_INVALID:<entry_id>:`; `DeliveryLimitation` held to
  three pairs. Nothing relaxed. Not done here: the lock clock (Session 07,
  named as `BASELINE_EARLIEST_LOCK_PASSED`), prefilled preservation and contest
  groups (Session 11). Breakpoint not taken: Showdown adds no source line.
  Numbers: `changelog.md`.

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
- **2026-09-23, Complete (both modes).** A readable-review failure is classified
  code by code through the registry: `V`, unregistered or code-less withholds,
  anything else keeps the Showdown or C3 CSV listed with the code as a
  limitation (exit 2). C3 keeps its export and audit after re-verifying them and
  removes only its JSON and HTML; `prior_review.py`'s C3 branch lists them.
  `delivery.py` writes `LATEST_DELIVERABLE.json` (`nfl_latest_deliverable_v1`)
  with `os.replace` and revalidates the file before any write and on every read;
  `publish`, `read_latest`, `replace` are Session 06's API. `run-slate` reports
  `DELIVERY_STATE` and `nfl_release_truths_v2` on every `prior_review` exit (C1
  and C2 `NO_DELIVERABLE`). The outer handler names a revalidated deliverable and
  never deletes it; `certify`'s is unchanged. 27 codes registered, none
  reclassified. Breakpoint not taken (2,342 changed lines, 1,128 of them source
  and registry; the pointer's revalidation is what makes the keep path fail
  closed). Nothing relaxed. Numbers: `changelog.md`.

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
- **2026-09-24, Complete (Classic and Showdown).** `run-slate` builds
  `nfl baseline`'s file into `<output-dir>/<run_id>/baseline/` straight after
  intake and the request snapshot, with the request's exact exclusions, and
  publishes it before the probe, policy validation, priors, weather, roles or
  any solve. The review CSV replaces it only through `delivery.replace`. Every
  exit (a blocked stage, the pre-review blocked exit, a withheld CSV, a refused
  C1 export, the outer handler) reads the pointer back and reports the file it
  names, with `IMPROVEMENT_NOT_DELIVERED` (`P`) while that is the baseline. C1
  exports its own lineups through the baseline's writer and audit
  (`DK_REVIEW_ENTRY_C1_<run_id>.csv`) and falls back to the baseline on any
  refusal. Exit codes unchanged; a partial improvement never replaces a full
  baseline. `nfl baseline` gains `--exclude` and `--unavailable-status`. Eight
  codes registered. The weather block itself stays a stop
  (Session 09); no deadline logic (Session 07). Nothing relaxed. Breakpoint not
  taken: the wiring is mode-agnostic, so Showdown adds no source line. Out of
  the card's list: `baseline.py` (exclusions) and the three docs the card
  omitted. `CLAUDE.md`'s stale rung-4 and running-order sentences go in a
  separate `ben-review` pull request. Numbers: `changelog.md`.

#### Session 06b: the run's official `INACTIVE` rows bind the baseline (R32)

- **Depends on.** Session 06.
- **Why.** Session 06 left one question open: when a run's official status
  file marks someone `INACTIVE` and the review then stops (weather, identity),
  the delivered baseline could hold that person. Ben ruled on 2026-09-24 (R32)
  to take the recommendation: the run's validated `INACTIVE` IDs bind the
  baseline.
- **Scope.** `baseline.run_baseline(official_status_csv=)` snapshots the file,
  parses it with `evidence.parse_official_inactive_snapshot` (exact
  current-slate DK IDs, team, status, HTTPS source, aware time), and takes
  every person an identity-valid `INACTIVE` row names out of the pool, a row
  that disagrees with another included. Refused rows and
  an unreadable file are named as `P` limitations and never stop the file. The
  audit re-derives those people; a changed snapshot withholds. `run-slate`
  passes its request's file, the C1 export audit checks it, and `nfl baseline`
  takes `--official-status`.
- **Not here.** Freshness and per-person coverage stay certification checks
  (`OFFICIAL_STATUS_REQUIRED` stays on every baseline); Session 09 still owns
  activity on the model path.
- **2026-09-24, Complete (both modes).** The baseline takes out every person an
  identity-valid official row marks `INACTIVE`, a disagreeing row included;
  refused rows and an unreadable file (a CSV-reader error included) are named
  `P` and never stop it; the snapshot is hash-bound and the audit re-checks
  it. `run-slate` and the C1 export audit read the run's snapshot (C1 also
  checks its hash); `nfl baseline --official-status`. The baseline report
  moves to `nfl_baseline_report_v2`. Five codes. Nothing relaxed. Numbers:
  `changelog.md`.

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
- **2026-09-24, Complete (breakpoint taken).** Request v3 carries
  `delivery_deadline_utc` (v1 and v2 unchanged; `--delivery-deadline-utc`).
  `deadline.Budget`, built right after intake, gives the baseline
  `min(60, max(30, time to deadline))`, stops optimization 5 minutes before the
  deadline (`stop_discretionary_optimization_minutes_before_lock` consumed;
  `full_refresh_seconds` removed), shortens or skips the probe, and passes C1
  and SD3 solver limits through `select_prior_lineups`' own parameters; a C2
  policy's hash-bound limits fit or stop the review. A passed deadline or spent
  window leaves the baseline as the file, exit 2, `DEADLINE_*` (`S`). Stage
  durations and the host's C2 candidate rate are recorded. Seven codes: five
  `S` in a new `delivery_deadline` family, two `P`. The diff reached about 2,000
  lines, so the fetch, weather-script and generator allowances went to Session
  07b, built and tested first. None of Session 08's files was edited. Numbers:
  `changelog.md`.

#### Session 07b: fetch, weather-capture and policy-generator allowances

- **Depends on.** Session 07.
- **Why.** Session 07 passed about 1,500 changed lines. At Ben's named seam
  it landed request v3, `deadline.py`, the budget through `run-slate`, the
  baseline and the review's solver limits, and moved these three here. It had
  built and tested all three first (suite `1623 passed, 1 skipped` with them);
  the design below is that tested version.
- **Scope.**
  - `sources.fetch_public_artifact(budget=None)` uses `budget` or the one
    `deadline.activated(budget)` set (a `ContextVar`; `run-slate` wraps
    `run_prior_review` in it, so `priors.freeze_sources` needs no change). The
    timeout is `Budget.fetch_seconds(default, host)`: `min(30, window)`, not
    started under 1 s, which raises
    `SourceDeadlineError("DEADLINE_FETCH_WINDOW_SPENT:<host>:...")` (register it
    in `delivery_deadline`). Each fetch is measured as stage `evidence_fetch`.
  - `scripts/fetch_weather_captures.py` stays standard library:
    `--delivery-deadline-utc` (default: the earliest `Game Info` lock minus 5
    minutes through `zoneinfo`, or none, said so, where the IANA data is
    missing); requests stop at the deadline minus 5 minutes; each `urlopen`
    timeout is `min(30, left)` and each retry pause `min(2**n, left)`; under
    1 s it exits `FETCH_DEADLINE_REACHED` and invents nothing. Test that its
    reserves equal `deadline.py`'s.
  - `make_classic_policy.py`: `--delivery-deadline-utc` and `--host-rates`
    (default `data/runs/host_candidate_rates.json`); the rate is
    `deadline.read_candidate_rate(..., mode="CLASSIC")` or 0.28 s; `_limits`
    takes `seconds_per_candidate` and `window_seconds` and keeps the declared
    bank plus joint solve within 75% of the window (joint at most 20% of it,
    the 2x generation headroom kept); exit 2 naming rung 4 when even the floor
    bank does not fit. Read the stop from `config/runtime.json`
    (`deadline.runtime_stop_minutes`), not the default 10, and name the flag
    again in `DEADLINE_POLICY_SEARCH_EXCEEDS_WINDOW`'s detail once it exists.
- **Tests.** A slow `httpx.Client` stub on a fake clock (40 s per failed
  request in a 100 s window: timeouts 30, 30, 20, then refused, no client
  made); a slow `urlopen` stub (a 45 s stop gives timeouts `[30, 14]`, pauses
  `[1, 0]`); a passed deadline starts no request; the generator at 5 s per
  candidate fits 48 candidates in a 700 s window and refuses a 600 s one.
- **Conflict.** `sources.py` (Session 17) and `make_classic_policy.py` (Session 10).
- **2026-09-24, Complete.** Rebuilt from this card (Session 07's draft did not
  survive its container). `Budget.fetch_seconds` and `deadline.activated`:
  every fetch `run-slate`'s review reaches takes `min(30, window)`, none starts
  under 1 s (`DEADLINE_FETCH_WINDOW_SPENT`, `S`, registered; the review's
  `PRIORS_PROPOSE_FAILED` blocker and the limitation both name it), and each is
  a measured `evidence_fetch` stage, a raised one included. The weather
  capture script keeps the deadline with the standard library and says so
  where it cannot derive one; the generator sizes its bank to the window at
  this host's rate and `runtime.json`'s stop, and exits 2 writing nothing when
  the floor bank does not fit or the window has closed. Decisions and numbers:
  `changelog.md`. Left open: fetches outside `run-slate` (the role-evidence
  script) keep the fixed 30 s; the generator's 5 s per-solve limit is not
  scaled to a measured rate (Session 08 or 10).

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
- **2026-09-24, Complete.** The C2 bank keeps a limit-stopped per-candidate
  roster (`FEASIBLE_LIMIT`, counted toward its stratum); a bank stopped by its
  total budget or a limit is `BOUNDED_TIME_LIMIT_STOP` or
  `BOUNDED_SEARCH_LIMIT_STOP`, not blocking, with the entry count and a
  `POLICY_FEASIBLE` witness, and `CANDIDATE_BANK_TIMEOUT` or
  `CANDIDATE_BANK_SEARCH_LIMIT`, still blocking, without. Both joint selectors
  return a limit's valid incumbent as `FEASIBLE_LIMIT_ACTUAL_CANDIDATE_BANK`
  (no optimality scope; C2 starts from the witness and never delivers less). C3 and `run-slate` accept
  and name both (`CANDIDATE_BANK_STOPPED_AT_LIMIT`,
  `PORTFOLIO_SELECTION_LIMIT_INCUMBENT`, `S`). The status test is deterministic
  (20 of 20); the real-HiGHS acceptance runs on a node limit and on a 1e-9 s
  time limit through `run-slate` to the C3 export, and SD3's through the
  Showdown export. Left open: a stopped SD3 bank still blocks, and
  the rung ladder is still walked by hand (Session 10). Decisions and numbers:
  `changelog.md`.

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
  - The P1 hard stop becomes an exclusion (R28, Ben 2026-09-23). A person
    `offensive_roles` names with `OFFENSIVE_UNRESOLVED_MATERIAL_ROLE_CHANGE`
    leaves the selectable pool; the run continues and the code travels as a
    `P` limitation naming him, its class already `P` in the registry. The
    runbook's "and stops" (`RUNBOOK.md:889-890`) changes to match.
- **Must hold.** Never fabricate an observation. `RELEASE_DECISION` stays
  `DO_NOT_UPLOAD`. The provider identity gate keeps its current behaviour; the
  baseline does not consume it. A person the P1 gate names is never selected on
  the old-team share: exclusion is the only construction change.
- **2026-09-24, Complete.** A game nobody observed freezes as `UNOBSERVED`
  (team source and team CSV v2, declared only when a game needs it) and ships
  named per game as `WEATHER_UNOBSERVED` (`P`); it moves no number and never
  certifies. Classic missing official activity, a row or the whole file,
  publishes through C1, C2 and C3 named as Showdown's already was, and C3's
  audit (v2) reports `selected_activity` truthfully. The P1 person leaves the
  selectable pool and is named. `build_priors` already persisted in the saved
  request; a test now holds it through a `--request` rerun. Each changed exit has
  a `run-slate` test delivering C1's file with `DO_NOT_UPLOAD`. Left open, for a
  later card: role gaps and a selected unavailable person still block the
  Classic gate; present-but-invalid weather or activity evidence still stops the
  review; the session probe still counts `api.weather.gov` as blocking (Session
  13). Decisions and numbers: `changelog.md`.

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
- **2026-09-24, Complete.** `src/nfl_dfs/relaxation.py` owns both ladders (the
  Classic table moved out of `make_classic_policy.py`, now a wrapper; Showdown
  rungs from the DAL@NYG retro, `make_showdown_policy.py --rung`), and
  `run-slate` re-enters its review on a trigger read from the structured
  `selection_failure` (`SelectionError` carries its status; `deadline.py`'s
  regex is gone). Throughput failures (bank or joint limits, solver errors, a
  search the window cannot hold) re-size the bank at the same rung first, then
  take rung 4; structural ones take the next rung; an SD3 bank that ran out is
  deepened first; a policy whose only problems are `S` bounds enters at intake.
  Each rung's policy is the loosest of the last and the table, written, hashed,
  validated and normalized in the run folder; every step is an
  `nfl_relaxation_record_v1` record and an `S` limitation (`RELAXATION_*`).
  Uniqueness, exclusions and zero caps are never relaxed; a window that cannot
  hold rung 4 stops the ladder by name with the baseline delivered. Relaxed:
  the diff passed the 1,500-line breakpoint with the Classic controller alone,
  so the tested Showdown ladder stayed in rather than moving to a 10b row. Left
  open: prior_review still delivers all or nothing, so a short pool ships the
  baseline with its unfilled Entry IDs (Session 11). Decisions and numbers:
  `changelog.md`.

#### Session 11: entry groups

- **Depends on.** Session 06.
- **Scope.**
  - Replace the whole-file `ENTRY_BLANK_CELL_AUTHORITY_REQUIRED` refusal
    (`prior_review.py:1407-1417` as of Session 09's merge) with per-row authority. Prefilled rows are
    preserved byte-identical; blank rows are filled.
  - `lineups.py:143-147, 163-166` accepts a subset with preserved rows.
  - Groups by Contest ID are delivered independently, and unresolved Entry IDs
    are listed.
  - Distinctness is checked across the whole portfolio, prefilled lineups
    included.
  - `entry_ids` may bind a subset (Showdown retro #4).
- **Must hold.** Blank-cell authority is still `V`. No filled cell is ever
  changed.
- **2026-09-24, Complete.** `src/nfl_dfs/entry_groups.py` plans every row
  against the slate: blank rows are fillable, prefilled rows whose cells are
  exact current-slate IDs (bare or `Name (ID)`) are preserved byte for byte,
  and partly filled rows, prefilled rosters that do not resolve or repeat
  another, and every row of a Contest ID whose rows disagree on name or fee are
  left as they are and named unresolved. The baseline, C1's export, the
  Showdown export and C3 fill only fillable rows through the per-row
  `write_upload_bytes`; writing into a prefilled cell is still `V`. The
  baseline and C1 cut every prefilled roster, the C2 and SD3 banks never hold
  one, and every export audit and the pointer refuse a repeat. `entry_groups`
  reports each Contest ID in the baseline report, the result and the pointer,
  and `replace` compares coverage per group. New records:
  `nfl_release_truths_v3`, `nfl_latest_deliverable_v2`,
  `nfl_baseline_report_v3`. Breakpoint used: subset binding moved to Session
  11b; here a policy binds exactly the fillable rows. Left open: the prefilled
  cell form is unverified on a real download (Session 12's open question);
  prior_review still fills all of its fillable rows or none. Decisions and
  numbers: `changelog.md`.

#### Session 11b: subset binding

- **Depends on.** Session 11.
- **Scope.** Split from Session 11 at Ben's breakpoint (2026-09-24).
  - A policy's `entry_ids` may bind a subset of the plan's fillable blank rows,
    in template order (Showdown retro #4 and §7c: thesis and dart sleeves). A
    bound prefilled, unresolved or unknown row is still a `V` refusal.
  - Today both validators refuse anything but the fillable rows in order:
    `PORTFOLIO_POLICY_ENTRY_ID_BINDING_MISMATCH` (`portfolio_policy.py`),
    `CLASSIC_POLICY_ENTRY_ID_BINDING_MISMATCH` and
    `CLASSIC_POLICY_ENTRY_SET_INVALID` (`classic_portfolio_policy.py`), and
    `PORTFOLIO_POLICY_LINEUP_COUNT_MUST_MATCH_ENTRIES` (`cli.py`).
  - The unbound blank rows: after the policy's joint solve, C1 fills them with
    every policy lineup and every prefilled roster as no-goods (Ben's lean,
    2026-09-24); leaving them unfilled would never replace a fuller baseline.
  - `relaxation.Ladder.entry_ids`, each relaxation record's `entry_ids` and
    DATA_CONTRACTS § Relaxation record become the policy's bound list, and a
    rung's document binds the same subset.
- **Acceptance.** A policy binding a subset validates and fills its rows; the
  unbound blank rows are filled distinctly; a bound prefilled row is refused `V`.
- **2026-09-24, Complete (Showdown; Classic C2/C3 split to Session 11c).** Both
  validators accept the fillable rows or a non-empty subset of them in template
  order (`entry_groups.subset_binding_problems`); anything else is the `V`
  binding refusal, and the bound list is every integer cap's denominator. After
  the SD3 joint solve, sequential Showdown fills the unbound rows with every
  policy lineup and prefilled roster as a no-good, under the run's own
  exclusions only (`selection._fill_unbound`); all or nothing. The SD3 audit
  covers the policy's rows; the readable review (`sd5_v2`) checks the fill's
  rows and names each row's `source`; the result carries `row_sources` and the
  bound and unbound lists. The ladder binds the supplied subset at every rung
  and rung 4 budgets for every fillable row. Both generators take a repeatable
  `--entry-id`. A policy binding every fillable row gives `main`'s bytes (SD3
  and C2 hashes pinned). Breakpoint used: the diff passed about 1,500 lines with
  the Showdown path, so a Classic subset is refused by name
  (`CLASSIC_POLICY_SUBSET_UNSUPPORTED`, `P`) and C2/C3 moved to Session 11c.
  Decisions and numbers: `changelog.md`.

#### Session 11c: C2 and C3 over a subset policy

- **Depends on.** Session 11b.
- **Scope.** Split from Session 11b at Ben's breakpoint (2026-09-24).
  - Remove the three `CLASSIC_POLICY_SUBSET_UNSUPPORTED` refusals (`cli.py`
    intake, `prior_review.py` before selection, `selection.py`) and call
    `_fill_unbound` after the C2 joint solve, as the SD3 branch does: C1 fills
    the unbound rows with every C2 lineup and prefilled roster as no-goods,
    under the run's own exclusions only.
  - Split every Classic record that equates the policy's rows with the fillable
    rows: `prior_review.py`'s `stable_selection` (`entry_assignments` over the
    policy's rows, a C1 section for the rest), the C2 audit
    (`classic_portfolio.py` `exact_classic_assignments`, the audit's expected
    entries), and C3 (`classic_review.py`: the policy entry-order check, the
    assignment coverage and order check, uniqueness and the pairwise loop, the
    denominator, and `CLASSIC_C3_ASSIGNMENT_OUTSIDE_CANDIDATE_BANK`, which a C1
    row is by construction). Policy counts, bounds and overlap over the bound
    rows; legality, distinctness, exclusions, activity and the byte audit over
    every filled row.
  - C3's package names each row's source (a new version of its readable review
    record), as Session 11b's Showdown review does.
- **Must hold.** No filled cell changes; a bound prefilled or unknown row stays
  a `V` refusal; R29 across policy, C1 and prefilled rows; a C2 policy binding
  every fillable row gives the same file (`C2_FULL_FILLABLE_SHA256` in
  `tests/test_entry_groups.py`).
- **Acceptance.** Through `run-slate`: a Classic policy binding a subset fills
  its rows by C2 and the rest by C1, distinctly, on a template with a prefilled
  row; C3 accepts the mixed portfolio and names each row's source.
- **2026-09-25, Complete.** The three refusals and their registry entry are
  gone. After the C2 joint solve, C1 fills the unbound rows with every C2 lineup
  and prefilled roster as a no-good, under the run's own exclusions only, all or
  nothing; each fill solve gets what the policy's declared limits leave of the
  window. The C2 audit needed no change: its artifact was always the policy's
  list. C3 takes the C1 rows from the selection record's
  `assignments_by_entry_id`, checks the partition
  (`CLASSIC_C3_UNBOUND_ROWS_MISMATCH`), scopes bank, counts, bounds, overlap and
  the denominator to the policy's rows, and checks legality, distinctness,
  activity, the run's exclusions (`CLASSIC_C3_SELECTED_PERSON_EXCLUDED_BY_RUN`)
  and the bytes over every row. The readable review (`classic_c3_v2`) and export
  audit (`c3_v3`) name each row's source. The C2 golden hash holds. Also fixed:
  C3 re-validated the source policy without the run's own exclusions, so every
  C2 run with an official inactive or operator exclusion shipped the baseline
  (`CLASSIC_C3_SOURCE_NORMALIZED_POLICY_DISAGREEMENT`, confirmed on `main`).
  Decisions and numbers: `changelog.md`.

#### Session 37: Showdown file integrity

- **Depends on.** Nothing. Startable now; runs alone with Session 38 only by
  file (no overlap).
- **Why first.** Two of the 2026-09-25 review's findings can put a wrong file
  in front of Ben: a Showdown policy can switch off R29 distinctness and the
  Showdown QA passes an export that overwrote a prefilled row. Neither is
  reachable through `run-slate`'s own writers today, both are reachable through
  a hand-authored policy or the fallback chain, and both are small.
- **Scope.** Each item is in `docs/critiques/Code_Review_2026-09-25.md` §2.
  - V1: `portfolio_policy.py:997-1007` refuses `require_unique_lineups: false`
    as `classic_portfolio_policy.py:922` does; `portfolio_enforcement.py:725-729`
    loses `repetition_allowed`; the audit's duplicate check at `:1288-1296`
    runs unconditionally; `tests/test_portfolio_enforcement.py:541` flips its
    default.
  - V2 and V11: `scripts/qa_showdown_portfolio.py` derives the blank rows from
    the template and exempts only those, compares raw lines through
    `byte_lines` as the Classic twin does, exits 3 on a sanctioned unfilled
    row, moves `OVERLAP_*` and `STARTER_WITH_OWN_BACKUP` out of the validity
    exit (the Session 02b open item), and identifies people by DraftKings ID.
  - V9: `prior_review.py:2152`'s re-parse goes; the
    `ENTRY_INPUT_CHANGED_BEFORE_SELECTION` stop at `:2209-2213` applies in
    every mode.
  - V10: `prior_review.py:3207` catches `Exception`.
  - E12: `referee.py:43`, `:115` name an empty physical line.
- **Size.** Five source files, two test files, about 400 changed lines; read
  `portfolio_enforcement.py` (1,342), the QA script (about 250) and the two
  `prior_review.py` sites. One session.
- **Acceptance.** A Showdown policy with `require_unique_lineups: false` is
  refused by name; the QA script fails an export that touched a prefilled row
  and passes one with a sanctioned blank row at exit 3; a Showdown run whose
  entries file changes between intake and SELECT stops by name; the suite is
  green.

#### Session 38: run-path integrity

- **Depends on.** Nothing. Startable now.
- **Scope.** Review §2, V3 to V8.
  - V3: `cli.py:1180` builds the review workbook before `certify_upload`
    (`:1142`), or the handlers at `:1220-1223` and `:4299-4300` read the
    manifest and never delete a file whose hash it binds; the handler uses the
    resolved run id. A test injects `WorkbookLockedError` after certification.
  - V4: `nfl.ps1:4` accepts `baseline` (or drops `ValidateSet` so the two
    launchers cannot drift again).
  - V5: `cli.py:3704` refuses an existing `outputs/<run_id>` as `:3652` refuses
    the run folder.
  - V6: `command_status` (`cli.py:2216-2240`) re-derives through
    `historical_artifact_integrity` or labels every field stored, pins
    `RELEASE_DECISION=DO_NOT_UPLOAD` and never exits 0 on a stored `CERTIFIED`.
  - V8: the exception exit of a `prior_review` run (`cli.py:4251-4367`)
    reports `MODEL_STATUS=PRIOR_ONLY`.
  - V7 (last, the seam): `certify_upload` and `command_validate` take
    `plan_entries(...).fillable` as `review_export.py:153` does, so a
    partially entered template can be certified by hand.
- **Size.** Three source files, three test files, about 500 changed lines.
  One session; stop before V7 if the diff passes 1,500 lines.
- **Acceptance.** A certification that raises after the CERTIFIED write leaves
  the file and its manifest intact; `.\nfl.ps1 baseline` reaches Python; a
  second run into an existing output folder is refused by name; `status` on a
  deleted certified file is not `CERTIFIED` and not exit 0; the suite is green.

#### Session 23: P2 part 1, structural hygiene and the share cap

- **Depends on.** Session 10 (the ladder both generators consume). The brief's
  dependency on P0 was for grading the rerun against standings; that is
  Session 18b's acceptance, not this session's.
- **Why here.** The 2026-09-15 findings measured one construction rule set that
  held in all four graded Showdown games: exactly one pass catcher with the
  rostered quarterback, one quarterback, $1 to $500 left, at most one kicker
  and one DST, no offense against its own DST and no DST on the quarterback's
  team, with no player in more than 80% of the rows. That set alone raised
  P(at least one top-1% finish) at 20 entries from 0.19 to 0.28 and cut
  P(nothing paid) from 0.007 to 0.002 in every game
  (`docs/STANDINGS_DUAL_OPTIMIZATION_FINDINGS_2026-09-15.md` §5.4, §7, §8.2).
  Every engine portfolio to date excluded kickers and DSTs, which were in the
  top 1% at 1.3x to 2.9x in three of four games. Nothing else on this board
  has that evidence and costs one session.
- **Scope.** `docs/chunks/P2-contest-aware-policy.md`, the bounds, the share
  cap and the generator defaults only; assignment order and `contest_facts_csv`
  are Session 23d. Plus review S7: the Showdown generator's default captain
  cap stops being `None` (`portfolio_policy.py:356-368`) and every review
  reports each captain's count. The relaxable rung order for the new bounds is
  the brief's (salary band, pass-catcher band, K/DST caps, QB count,
  `max_person_share`), expressed in `relaxation.py`'s ladder, not in the
  generators. Uniqueness stays off the ladder (R29).
- **Size.** Eight files, about 900 changed lines; read the two policy contracts
  (2,270 lines), `portfolio_enforcement.py` (1,342) and `relaxation.py` (1,022).
  One session at the edge; the seam is Showdown first, Classic bounds second.
- **Acceptance.** The DAL@NYG and DEN@KC fixtures rerun under the new
  generators give `max_person_share` at or below 0.80, a 100% hygiene pass at
  rung 0, kickers and DSTs in the pool, more than one captain, and infeasible
  bounds fail closed naming the rung. Every new bound is recomputed in the
  audit from roster bytes. Suite green.

#### Session 21: prior-model triage

- **Depends on.** Nothing. Startable now; no file overlaps Session 23.
- **Scope.**
  1. The unit mismatch is confirmed (review S1): `priors.py:1541-1565` sums a
     person's prior season with no per-game normalisation and `:1795-1812`
     divides by the pool's season sum, while `:1661-1680` averages snap share
     per game played. A player who missed eight of seventeen games carries
     about half his true share and his teammates inherit the rest, in
     `prior_score` and in the simulator. Fix: per-game rates over the weeks a
     person has a row, share as rate over the pool's rates, under a new
     transformation version (`docs/DATA_CONTRACTS.md:128-133` defines v1 as
     pool share of counts; v1 is never mutated). A fixture with a player who
     missed games projects at his per-game rate.
  2. The transfer pseudo-count (review S2, `priors.py:1773-1776`) scales a
     transfer's old share by the incumbents' pool total, so a thin room gives a
     transfer starter near zero. Scale by the team's expected pool.
  3. F8: propose identity matches from the alternate name fields nflverse
     ships (`first_name`/`last_name`, `football_name`, accent-folded forms) as
     candidates for review. The auto-accept rule is unchanged, so no ruling.
  4. `tests/test_priors_adapter.py:44` derives its clock from the fixture
     instead of a hardcoded `AS_OF` (C4 retro #17 was recorded done; it is not).
- **Size.** Three source files, about 500 changed lines; read `priors.py`
  `:1300-1900` and `prior_score.py`. One session.

#### Session 17: X2 standings corpus transport

- **Depends on.** Session 00. Acceptance needs O1.
- **Spec.** `docs/chunks/X2-standings-corpus-transport.md` and archive § R27.
  The bounds there are binding: every capture invariant, hash-bind on arrival,
  credentials from the environment only, `data/standings/inbox/` never
  overwritten, no DraftKings contact.
- **Why here.** It is the gate to every graded number on this board (Sessions
  18, 18b, 26, 27, 29) and it is cheap. It runs in a cloud session while a
  Windows session takes Session 23.
- **Size.** Two source files, one script, one test file, about 400 lines.
- **Breakpoint.** If O1 is still open, stop after the authenticated fetch and
  its byte-mismatch refusal test. Leave the row `Pending` and name the
  unfinished acceptance step.

#### Session 39: Classic diversification

- **Depends on.** Session 23, because the Classic overlap cap is a rung on the
  ladder Session 23 orders.
- **Why here.** Review S3: `selection.py:701-703` sets the Classic overlap cap
  to `None`, so C1 (rung 4) and every unbound fill row are cut only by exact
  rosters: each next optimum is the previous lineup minus one player. The
  findings named that shape, "one lineup with 17 perturbations", as the
  washout mechanism in our own Classic portfolio (§5.1, §5.5). S4: the C2
  witness chain is N copies of the best lineup with the quarterback swapped,
  and it is what ships when the joint solve stops at a limit.
- **Scope.** S3, a Classic person-overlap cap on the ladder, default 6, applied
  by `_sequential_lineups` and `_fill_unbound`; S4,
  `classic_portfolio.expand_validated_neighbors` (`:397-503`) enforces the
  policy overlap and round-robins seeds and slots; S6, `fill()` (`:294-301`)
  applies the policy's exclusions; S5 (the seam), the fill returns what it
  built and `prior_review.py:2318-2320` names the unfilled unbound rows instead
  of discarding the bound portfolio (R29's own words).
- **Size.** Five files, about 600 changed lines; read `selection.py` (910) and
  `classic_portfolio.py` `:380-980`. One session.
- **Acceptance.** On the 20-entry Classic fixture no two C1 rows share more
  than the cap; the witness chain's rows respect the policy overlap; a fill
  that runs out at row k delivers k rows and names the rest; suite green.

#### Session 23b: P8 part 1, thesis structures

- **Depends on.** Session 23 (the share limit and the bounds vocabulary).
  Runs alone: it edits the files Sessions 23c, 23d and 44 edit.
- **Spec.** `docs/chunks/P8-showdown-thesis-sleeves.md`, the strategy behind
  R33 and R34: every Showdown lineup follows one named game thesis Ben
  chooses, captain first, kickers and DSTs included. How to build it is this
  session's call; the brief holds the theory, the evidence and the principles.
- **Scope, this half.** A thesis contract (name, teams, a required captain set,
  per-team and per-position bounds, exclusions) validated as a policy sleeve;
  a single-thesis build whose captain comes from the thesis's set and whose
  structure the ladder never relaxes (principle 6: a thesis that cannot be
  built is dropped and named, never bent); backup quarterbacks out by default
  from depth evidence (R33); each lineup names its thesis. The multi-thesis
  assembly is Session 23c.
- **Size.** Six files, about 900 changed lines; read `portfolio_policy.py`
  (1,180), `portfolio_enforcement.py` (1,342), `relaxation.py` `:400-800`.
  One session.
- **Acceptance.** A fixture thesis that requires a kicker captain builds one;
  a thesis whose required captain is inactive is dropped and named, not
  relaxed; a backup quarterback is out of the pool unless the request names
  him; suite green.

#### Session 23c: P8 part 2, the thesis portfolio

- **Depends on.** Session 23b.
- **Scope.** Rows allotted across Ben's theses; one joint assembly with every
  lineup distinct across theses and against prefilled rows (R29); the one
  portfolio-wide share limit from Session 23; captains spread across theses
  (principle 4: the same core with a rotating captain is one bet placed many
  times). The review reports, per Entry ID, the thesis and whether the lineup
  follows it, each captain's count and thesis, every person in more than half
  the rows, and the most rows one player's bad night sinks (R34's judgement).
  ATL@GB (2026-09-24) and the NE@SEA fixture replayed.
- **Size.** Five files, about 800 changed lines; read `selection.py`
  `:160-560`, `readable_review.py` `:980-1543`. One session.
- **Acceptance.** The brief's "Done looks like": the 20-row fixture spread
  across each team wins big, each team wins close (high and low scoring), a
  defensive battle and a shootout; kicker and DST captains where a thesis
  calls for them; no repeat, no player over the share limit, captains well
  beyond five at 25%; still `DO_NOT_UPLOAD`.

#### Session 23d: P2 part 2, contest-aware assignment

- **Depends on.** Session 23.
- **Scope.** The assignment half of `docs/chunks/P2-contest-aware-policy.md`:
  assignment order as a policy input with three registered values
  (`prior_points_desc`, `round_robin_by_contest` as the new default,
  `tail_proxy_desc` accepted only when a lineup tail statistic exists, which
  Session 25 provides); `contest_facts_csv` (contest id, field size, places
  paid, entry fee) as a versioned contract that tags each entry's paid
  fraction and labels entries under 5% `FIRST_PLACE_OBJECTIVE` in the review,
  from supplied numbers only, never from a contest name. Plus the manual
  contest-screening checklist `plan.md:395` promised and the critique (V9)
  says moves ROI more than lineup micro-decisions: rake, overlay, payout shape,
  field size, max entries, in `docs/RUNBOOK.md`.
- **Size.** Six files, about 500 changed lines. One session.
- **Acceptance.** On the DEN@KC fixture the satellite rows no longer receive
  the lowest-prior lineups; a `contest_facts_csv` with a bad row is refused by
  name; suite green.

#### Session 12: late-swap bridge and C5

- **Depends on.** Session 11. Runs on real data only after O9.
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
  - Review V12 (first): `cli.py:2058` refuses an `--as-of` that disagrees with
    `release_clock()` past a registered tolerance, because today a stale
    timestamp makes locked slots replaceable and the byte audit, which audits
    against the same authorization, would pass a `DK_UPLOAD` that edits them.
  - Review V13: `late_swap.py:397-400` and `lineups.py:323-334` resolve
    current cells through `entry_groups.prefilled_cell_id`, so the registered
    `Name (ID)` form is not read as a missing player.
  - Review E11: a post-kickoff salary export, whose `Game Info` cells for
    started games are unverified, parses; that needs one real export (the
    open question below).
  - C5's slot ordering: prefer later-lock players in flexible slots when
    legality and the lineup are unchanged.
- **Size.** Five files, about 900 changed lines; read `late_swap.py` (858) and
  `lineups.py` `:180-360`. One session; the seam is after V12 and V13.
- **Out of scope.** Strategy aids (Session 32). The conditional-EV reoptimizer
  (Session 36).
- **Open question.** [BEN: drop one DKEntries download that has some rows
  already entered into `data/inbox/` (any slate), and one salary export taken
  after a game has kicked off. No fixture or run snapshot holds either, so
  Session 11 accepts a prefilled cell as a bare DraftKings ID or as text ending
  `(ID)`, and treats anything else as unresolved; one real file confirms which
  form DraftKings writes, and the post-kickoff export shows what `Game Info`
  holds for a started game. Neither blocks Session 12.]

#### Session 41: weather and retrieval boundary

- **Depends on.** Nothing.
- **Scope.** Review §5, E1 to E3. `scripts/fetch_weather_captures.py:175-182`
  fetches through `urllib.request.urlopen` with no allowlist check on the
  forecast URL it takes from `nws_gridpoints.json` or the `/points` response,
  follows redirects to any host, and writes `json.dumps(forecast)` (a
  re-serialisation, not the response bytes) with no capture time. That is the
  retrieval boundary in `CLAUDE.md`. The script obeys `sources.ALLOWED_HOSTS`
  on every resolved URL (imported, or pinned equal by a test if it stays
  stdlib-only), refuses redirects the way `check_protected_paths.py:139` does,
  writes `response.read()` verbatim and records the fetch time in `plan.json`.
  E2: `make_classic_weather_evidence.py:157-165` sets `expires_at` to
  `min(observed_at + 6h, game lock)` instead of formatter time plus six hours,
  and `prior_review.py:1605-1609` re-derives it rather than trusting the JSON.
  E3: `fetch_weather_captures.py:135` and `venues.py:288` disagree on Las
  Vegas; one set, pinned by a test.
- **Size.** Five files, about 300 changed lines. One session.

#### Session 44: `prior_review` decomposition, part 1

- **Depends on.** Session 23c, only so the thesis work lands before the
  refactor moves the file under it; there is no code dependency.
- **Why.** `run_prior_review` (`prior_review.py:1392-3482`) is 2,090 lines with
  27 return sites and about 40 live locals (review R1). Every session that
  touches SELECT or EXPORT reads it whole, which is most of the context a
  single session has. Sessions 24b, 13, 14, 25b and 28 all edit it.
- **Scope.** The Classic publication block (`:2667-3157`: mutation checks,
  `overall_evidence_state`, the C2 bank, assignment and audit writes,
  `immutable_bindings`, `stable_selection`, `stable_coverage`) and the C3
  export block (`:3159-3299`) move to `classic_publish.py` behind a frozen
  `SelectContext` dataclass. Every blocker text and every artifact byte is
  unchanged. R5: the early returns at `:1655`, `:1704`, `:1757`, `:1777`,
  `:1798` keep the INTAKE stage; `:3432` uses the profile variable.
- **Size.** About 1,100 lines moved, 100 changed. One session; the moved code
  is read once, in place.
- **Acceptance.** Fixture artifact hashes byte-identical before and after; the
  340 `prior_review` tests unchanged and green; the full suite green.

#### Session 44b: decomposition, part 2, and one set of truths

- **Depends on.** Session 44.
- **Scope.** Intake and evidence binding (`:1439-1706`) to `review_intake.py`
  returning a `ReviewInputs` dataclass or a blocked outcome; priors,
  identity and projection (`:1723-2121`) to `review_priors.py`. R2:
  `EVIDENCE_STATE` is computed once above the mode split and passed into
  `review_export.as_report`, instead of the literal `UNKNOWN` for Showdown
  (`review_export.py:67`, `cli.py:3017-3022`). R3: one truths builder replaces
  the five `FILE_VALID` literals. R4: `review_common.py` holds hash-alias
  resolution, strict JSON loading and canonical bytes (today three copies with
  differing `ensure_ascii`); each audit keeps its own semantics. R6: the
  status workbook takes the run clock, not `datetime.now()`.
- **Size.** Nine files, about 1,200 lines moved and 300 changed. One session;
  `run_prior_review` ends under 600 lines.

#### Session 24: simulator correctness

- **Depends on.** Nothing; it edits files no other startable session touches.
- **Why.** `simulation.py` runs only in the legacy `build` command today, so
  none of this reaches a lineup yet. Session 24b puts the bank on the
  operating path; these land first so the bank is right when it does.
- **Scope.** Review §4. M1: `simulation.py:127` subtracts `sacks_allowed` from
  dropbacks before yards and catches (every passing yard, reception and
  receiving yard is inflated by about 7% against rushing today). M2:
  `_softmax_perturb` (`:39-50`) returns zeros for a zero-share group instead of
  a uniform split. M4: the DESIGN tail oversampling and its unread importance
  weights (`cli.py:1253`, `simulation.py:94-101`) go. M5: turnovers split by
  the registered interception fraction; kicker distance mix, PAT rate and
  return touchdowns from the frozen artifact, as `prior_score` does. M8:
  `SIMULATION_VERSION`, `OWNERSHIP_PRIOR_VERSION`, `FIELD_MODEL_VERSION` with
  `does_not_establish`, threaded into the diagnostics. M9: an operator
  bracket is honoured as a fraction. `config/runtime.json`'s three dead keys go.
- **Size.** Six files, about 500 changed lines; read `simulation.py` (357),
  `ownership.py`, `field.py`. One session.
- **Acceptance.** A test per defect (a 560-attempt, 42-sack fixture yields
  attempts; a four-zero quarterback group projects zero; a bracket of 0.40
  stays 0.40); `test_simulation.py` grows from two tests to one per drawn
  quantity.

#### Session 24b: P3a, the scenario bank on the operating path

- **Depends on.** Session 24 and Session 44b.
- **Spec.** `docs/chunks/P3a-scenario-bank.md`. Its acceptance uses P0's
  top-1% proxy; until Session 18b supplies it, the proxy is a registered
  constant per mode from `docs/STANDINGS_DUAL_OPTIMIZATION_FINDINGS_2026-09-15.md`,
  labelled as such, and Session 18b replaces it.
- **Scope.** A DESIGN bank of the registered size inside `prior_review`,
  per-lineup and per-candidate p50, p90, p99 and P(score at or above the
  proxy) as diagnostic columns in both readable reviews; the correlation table
  against the frozen team stats with each gap named; conservation checks
  within the registered wall time and RSS. No selection change.
- **Size.** Five files, about 700 changed lines. One session.
- **Acceptance.** On the supplied fixtures the p90 ranking differs from the
  mean ranking (if it does not, the bank has no covariance and the session has
  failed); replay byte-identical under the registered seed; suite green.

#### Session 24c: market anchoring and a field that spends the cap

- **Depends on.** Session 24.
- **Scope.** Review M3: `TeamProjection.market_total` and `market_spread` are
  carried and never read (`simulation.py:129-147`); a registered rate scales
  prior-season scoring by the implied total and spread, `does_not_establish`
  a calibrated total. M6: per-player reception and yardage variance
  (`:199-215` are deterministic slices today, so receiver ceilings are
  compressed). M7: one FLEX mix shared by `ownership.py:60` and
  `field.py:112`; cap-targeted field sampling at `:151` so the synthetic field
  spends what real fields spend (about 99% of the cap).
- **Size.** Four files, about 500 changed lines. One session.

#### Session 25: P3b part 1, the tail objective and its families

- **Depends on.** Session 23d (assignment order accepts `tail_proxy_desc`) and
  Session 24b (the bank).
- **Spec.** `docs/chunks/P3b-tail-objective.md`, the objective and families
  half. `TAIL_QUANTILE_OF_DESIGN_BANK` with a declared quantile (default p90)
  registered as an `objective_version`; tail-family strata so the bank holds
  tail candidates before the objective ranks them (5-1 tilt, DST-inclusive,
  single-QB single-stack, QB+2 and QB+3 same-team stacks, the RB bring-back,
  secondary-game stack for Classic); every run that uses the tail objective
  also builds the expectation-only portfolio from the same bank under the same
  controls and writes it as `control_assignment.json`, never exported, so the
  effect is measured (Session 18b) rather than argued.
- **Size.** Four files, about 800 changed lines. One session.
- **Acceptance.** A synthetic contest with a known tail optimum is recovered;
  replay byte-identical; `MODEL_STATUS` stays `PRIOR_ONLY`; suite green.

#### Session 25b: P3b part 2, the sleeve, captains on a ceiling, darts

- **Depends on.** Session 25.
- **Scope.** `tail_sleeve_entries = k`: the joint assignment selects k lineups
  under the tail objective and the rest under the expectation objective, under
  the Session 23 controls and share limit, and the review names the sleeve
  entries; captain strata on a ceiling statistic (Showdown retro §7b, §7e: a
  captain earns a slot if 1.5 times his ceiling can win); the dart rules
  (C4 retro §16 to §20, #6, #9, #16: a dart is short exactly one named prior,
  has a defined role, and sits at 2 to 12% ownership when an estimate exists;
  the no-prior pool is the type-2 dart pool); the REFEREE bank re-scores the
  assignment and a disagreement beyond the registered tolerance is a named
  blocker (report-only, never a reselect).
- **Size.** Five files, about 900 changed lines. One session.
- **Acceptance.** On the DEN@KC fixture a k=6 sleeve holds at least one DST
  lineup and at least one 5-1 on each side (a mechanism check, not a hindsight
  claim); the sleeve entries land on `FIRST_PLACE_OBJECTIVE` rows first.

#### Session 28: P6 survival controls

- **Depends on.** Session 25b.
- **Spec.** `docs/chunks/P6-survival-controls.md`. R34 makes this the washout
  measurement: bank-estimated P(zero paid) and P(all below median), cluster
  coverage by script, and the frontier against the sleeve's P(at least one
  top-1% proxy) for sleeve sizes 0 to k, printed so Ben picks the size.
- **Size.** Three files, about 500 lines. One session.

#### Session 18: P0 part 1, the grading command

- **Depends on.** Session 17 and O2 (O3 completes the NE@SEA era).
- **Spec.** `docs/chunks/P0-standings-grading-harness.md`, the first half.
  `nfl grade-standings` reads zips and loose CSVs, classifies mode from roster
  geometry, joins names to the same-slate salary file with zero tolerance for
  misses, and writes per-contest thresholds (score to cash, top 1%, top 0.1%,
  first, tie size at rank 1), our entries with rank, percentile and copy count,
  and, with `--payouts`, tie-pooled prize per entry. Metric definitions (the
  top-1% rule, tie handling, the paid rule, hygiene filters, concentration
  bands) live in `standings_metrics.py`, one registered module every later
  session imports, so no challenger is graded on a metric defined after the
  fact. Exports with `TimeRemaining > 0` are `LIVE` and never graded. The
  DAL@NYG and DEN@KC snapshots are filed with `intake.json` hashes.
- **Size.** Four new files, one CLI hook, about 900 lines. One session.
- **Acceptance.** 71 owned entries with `Rank == Place`; DEN@KC 195526229
  rank-1 tie 206; NE@SEA 193391013's 23-way tie paying $54,065.22.

#### Session 18b: P0 part 2, the field, and the graded reruns

- **Depends on.** Session 18, Session 23, Session 24b.
- **Scope.** The second half of the brief: field feature lifts on the reference
  contest per slate (findings §4.3), duplication share of the top 1%, the
  user-portfolio concentration table (§5.3), the seeded hygiene bootstrap
  (§5.4), our exposure against the field. Then the two acceptances this board
  moved here: the Session 23 rerun scored against the archived fields (report
  both; never present a rerun as achievable pre-lock), and Session 24b's proxy
  constant replaced by the harness's per-mode median.
- **Size.** Three files, about 700 lines. One session.
- **Acceptance.** Pass-catcher = 1 top-1% lifts 1.60/1.53/2.08/1.39; Classic
  sub-5% count 0 top-1% rate 2.08%; 8,007 user portfolios with 10 or more
  entries; under three minutes on the 26 files. Hand-back: Sessions 26 and 22
  become startable.

#### Session 26: P4a ownership challenger

- **Depends on.** Session 18b (the corpus and the harness's `--ownership`
  mode).
- **Spec.** `docs/chunks/P4a-ownership-challenger.md`, logging projected
  against realized ownership and leverage P&L (C4 retro #11, #12, #15). The
  `ownership_brackets_csv` request input, unused on the operating path, is
  validated by the same mass-conservation report. One session.

#### Session 27: P4b copy-count predictor

- **Depends on.** Session 26.
- **Spec.** `docs/chunks/P4b-copy-count.md`. If the data is too thin, it
  closes `Complete` with the accrual shortfall named. One session.

#### Session 29: P5 dilution economics

- **Depends on.** Session 25b, Session 27, and O4 ladders.
- **Spec.** `docs/chunks/P5-dilution-economics.md`. One session.

#### Session 13: preflight report and scored player pool

- **Depends on.** Session 44b (it edits `prior_review.py`).
- **Scope.**
  - A single run-start report re-derives the following against the actual
    inputs before the first solve (C4 retro #2, Showdown retro #7): identity
    resolution, pool completeness, evidence states, share coverage,
    participation vocabulary.
  - `selection.write_pool_scores` output becomes a first-class, hash-bound
    artifact written as soon as scoring completes (C4 retro #4), naming
    kicker zero-shares and offense exclusions (the Session 02b open item), so
    the standalone builder can consume it even if a later stage fails.
  - `scripts/session_probe.py:67` stops counting a blocked `api.weather.gov`
    as a blocking exit (the Session 09 open item).
- **Note.** `preflight.py` already exists for the upload preflight. Name the
  new module so the two cannot be confused.
- **Size.** Three files, about 600 lines. One session.

#### Session 14: delivery record

- **Depends on.** Session 44b.
- **Scope.** One versioned run record holding the audit §9 fields:
  `delivery_outcome` (`USABLE_ON_TIME`, `USABLE_LATE`, `NO_DELIVERY`) plus a
  separate invalid-attempt count; requested, lock and effective deadlines with
  stage timestamps; coverage, including preserved, new and unresolved rows;
  artifact identity and the supersedes chain; recovery and relaxation records;
  the intervention log, every question asked of Ben and whether it was
  avoidable. "Presented" means the path and hash are in the handoff. A
  submission receipt exists only when Ben supplies a post-upload download.
  DraftKings is never fetched.
- **Size.** Three files, about 600 lines. One session.

#### Session 15: delivery acceptance, part 1

- **Depends on.** Sessions 12, 13, 14 and 38.
- **Scope.** A new `tests/test_delivery_scenarios.py` runs audit §6 scenarios
  1 to 6 end to end with an injected clock and faults and no operator rescue:
  a short window; an optional feed unavailable; an infeasible exposure cap;
  uniqueness impossible (unfilled IDs, no repeats); a timeout with an
  incumbent; QA with no improvement. Plus the §10 cases (missing authoritative
  files, no legal roster, all cells locked, deadline passed, corrupt bytes),
  each ending in an honest partial or `NO_DELIVERY`.
- **Size.** One test file and fixtures, about 900 lines. One session.
- **Acceptance.** Every scenario asserts `DELIVERY_STATE`, file validity,
  coverage and delivery before the injected deadline.

#### Session 15b: delivery acceptance, part 2

- **Depends on.** Session 15.
- **Scope.** Scenarios 7 to 12: an optional certification failure; an
  enhancement crash after the baseline; one group failing; weaker
  diversification needed; a source that keeps timing out; presentation eating
  the window. It closes issue #40.
- **Size.** About 700 lines. One session.

#### Session 16: real-slate rehearsal

- **Depends on.** Session 15b and O8. It runs in the Windows desktop app on
  Ben's checkout.
- **Scope.** A current Classic slate and a current Showdown slate through
  `run-slate`, measuring time to baseline, the improvement outcome, the
  deadline behaviour, the delivery record, and `.\nfl.ps1 test` on the same
  commit. Also the P7 replay on the 2026-09-20 salary snapshot (formerly
  operator item 6): Wentz and Lock at effective QB1; Mayer, Hutchinson and
  Bateman at rank 1; byte-identical replay. Absorbs C4 and SD6. And one
  check the review could not make from Linux (H4): `.claude/settings.json`'s
  hook commands are POSIX shell, so the session confirms the guard and the
  session-start digest fire under the desktop app's shell.
- **Acceptance.** A `docs/RUN_RECORD_<date>.md` with the five truths, input and
  output hashes, timings, and one next action.

#### Session 42: official-status and identity discipline

- **Depends on.** Nothing.
- **Scope.** Review §5, E4 to E8, and §4 M10. E4: `evidence._valid_https_source`
  accepts any public HTTPS host for the activity, eligibility and
  inactive-report gates, so nothing distinguishes an official source from a
  corroborating one (`CLAUDE.md` says the latter cannot clear the gate); a
  registered official-host list; `scripts/make_official_status.py` exits
  non-zero outside its window and gets its first test. E5: the DK-to-depth-chart
  binding (`make_offensive_role_evidence.py:329-366`, `qb_depth_roles.py:574`)
  is a normalised-name match reported as `PASS`; label it a proposal. E6:
  `kicker_roles.py:409`, `:636` raise on a naive clock as the sibling modules
  do. E7: `evidence.py:281-290` checks a selected inactive before the due-time
  branch. E8: timezone validators on `contracts.py` timestamps. M10:
  `verify_projection_package` (`projection.py:790`) runs where `cli.py:979`
  validates the ledger, so a hand-edited `expires_at` is caught.
- **Size.** Eight files, about 500 changed lines. One session.

#### Session 43: harness holes

- **Depends on.** Nothing. Touches no protected path.
- **Scope.** Review §7. H1: `scripts/check_protected_paths.py:106` passes
  `--no-renames`, since a rename of `CLAUDE.md` lists only the new name and
  the check passes without the label (demonstrated). H2:
  `.claude/hooks/guard_bash.py` allows global options between `git` and the
  verb, matches `main` on the unstripped command, and adds `commit -a`,
  `restore`, `checkout --`, `gc --prune`, `reflog expire`, `git add -N .` and a
  redirected `git add .` (the Session 03 open item), each with a refusal test
  and an allowed-shape test. H5: a test for `record_verify.summary_line`. H4:
  `session_start.py:72` names a file that exists.
- **Size.** Six files, about 300 lines. One session.

#### Session 19: X3 execution postmortem and the merge gate

- **Depends on.** Nothing.
- **Spec.** `docs/chunks/X3-execution-postmortem.md`. Plus review H3:
  `mcp__github__merge_pull_request` is on the allow list with nothing that
  reads the head's check runs; a PreToolUse hook refuses the merge unless
  `suite`, `boundaries` and `protected-paths` are green on the head, and
  `git-authority.md` names the `windows` job in "green means green". The hook
  registration in `.claude/settings.json` makes the pull request protected and
  carries `ben-review`; the rules and hook files land first, the registration
  as its own pull request. The MCP rule lands in `.claude/rules/` unless it must
  go in `CLAUDE.md`.
- **Size.** Two sessions' worth of files but one session of code, about 500
  lines; the seam is the settings registration.

#### Session 20: environment truth

- **Depends on.** Nothing.
- **Scope.**
  - X1's remaining half, per `docs/chunks/X1-egress-probe.md`: per-host lines
    in `doctor`; a `PROHIBITED_HOSTS` test asserted on the injected client's
    call list; an offline `doctor` demonstration; replacing the asserted facts
    at `docs/CLAUDE_CODE_SETUP.md:260-262` (they drifted from the brief's line
    numbers and are still present). `run-slate` already covers the run-record
    half.
  - The 2026-09-22 changelog's open items: `sync.ps1` has no test, and there is
    no `sync.sh`.
- **Conflict.** It touches `cli.py`, so it must not run concurrently with
  Session 38 or 46.

#### Session 40: solver time under the lock clock

- **Depends on.** Session 39 (shared files).
- **Scope.** Review S8: a Showdown bank that hits its limit with at least the
  entry count of candidates and a joint-solved witness is `BOUNDED`, as
  Classic has been since Session 08 (`portfolio_enforcement.py:383-389`,
  `:413-416`); today `relaxation.py:760-771` halves a sufficient bank and
  re-runs everything. S9: tie-break perturbations of 1e-9 sit below HiGHS's
  `mip_abs_gap`; set the gap to zero or perturb at 1e-4. S10: `stack_value`
  indexes the pool once, bank generation runs without `tracemalloc`, and the
  C2 witness solve's result seeds the final joint solve instead of solving the
  same candidates twice (the Session 08 open item). R9: `deadline.py:536-561`'s
  rate ledger uses a per-process temp name; `cli.py:2657-2668` passes the
  budget clock to `run_baseline`; `:3723` no longer records a negative start.
- **Size.** Five files, about 400 changed lines. One session.
- **Acceptance.** The 20-entry Showdown fixture's bank and joint-solve wall
  time recorded before and after in the changelog.

#### Session 22: P0b provenance completeness

- **Depends on.** Session 18.
- **Spec.** `docs/chunks/P0b-provenance-completeness.md`: run-folder
  provenance completeness, `nfl record-manual-entries` for hand-built entries,
  a pre-registration record per slate (the findings' "control stored, not
  entered" protocol, §9). One session.

#### Session 45: ledger and contract truth

- **Depends on.** Nothing.
- **Scope.** Review E9: `docs/DATA_CONTRACTS.md:57` says the source ledger
  uses `nfl_source_ledger_v1` while the freshness gate needs v2; v2 and seven
  other version strings are undocumented. E10: `make_settlement_request.py:228-244`
  requires a schema version on the truths it copies. H6: `sync.ps1:52` stops
  printing `git add -A`. §8: `scripts/make_classic_policy.py:174` stops
  claiming rung 4 always produces a legal portfolio (Session 01 corrected it
  everywhere else). The runbook states each command's exit-code semantics
  (`nfl baseline` exits 3 on a partial; `run-slate` exits 0). The X4 report
  location is `docs/`, as the board says; the brief follows.
- **Size.** Six files, about 200 lines. One session.

#### Session 46: dead code and the legacy path

- **Depends on.** Session 24c (it edits `field.py`, `ownership.py`, `cli.py`).
- **Scope.** Review §8 lists the unreferenced functions, contract classes,
  runtime keys, imports and dependencies; each goes with its import, and the
  full suite is the test. V14: legacy `select` takes per-row authority from
  `plan_entries` and loses the cycling helper, or is retired. R7: the status
  workbook and the HTML render from one row model instead of two hand-mirrored
  column lists. R8: the registered and diagnostic profiles' `command_build`
  sizes candidates and per-solve seconds from the budget, or refuses below a
  declared minimum.
- **Open question.** [BEN: the legacy `build`, `project` and `run` commands run
  the old simulate-and-select path that nothing on the operating path calls
  (`cli.py:1347`). Sessions 24 to 24c reuse `simulation.py`, `field.py` and
  `economics.py` as libraries on the `prior_review` path, so the library code
  stays either way. Claude's recommendation: retire the three commands and
  their tests once Session 24b is complete, and keep `certify`, `late-swap`,
  `preflight`, `audit`, `settle` and `learn`. It does not block this session;
  without a ruling the commands stay and only the dead functions go.]
- **Size.** Many files, small diffs, about 600 lines removed. One session.

#### Session 30: standings contract v3

- **Depends on.** A ruling.
- **Open question.** [BEN: rule on the two `nfl_standings_csv_v2` contract defects found on your exports. The contract cannot represent a field member who never submitted a lineup, and it cannot hold an exact tie split that is not a whole number of cents, so `settlement._prepare_settlement` can never settle a contest with an uneven tie. Claude's recommendation: a v3 contract that carries blank field members explicitly and stores tie splits as exact fractions. Recommendations in archive § Q1B.]
- **Scope once ruled.** A new contract version (v2 never mutated), the
  normalizer, and settlement's exact comparison.

#### Sessions 31 to 36: deferred

Each row names what reactivates it. Session 34 (X4) needs re-scoping before it
runs, because the 2026-09-22 audit, the 2026-09-25 code review and this
roadmap now cover most of what its greenfield report was for. Its subagent cost
contract is the part that survives. Session 35 (C3X) stays parked by R30.

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
  - Absorbs the 2026-09-19 P1 hard stop (Ben, 2026-09-23: "Absorb it"). A
    person in `TRANSFER_PRIOR_UNVERIFIED` who trips `SALARY_RANK_DIVERGENCE`
    is left out of the pool, never selected on the old-team share; the file
    ships and `OFFENSIVE_UNRESOLVED_MATERIAL_ROLE_CHANGE` names him. Session 09
    makes the code do it; until then the run still stops.
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
- **R32, official inactives bind the baseline** (Ben, 2026-09-24, on Session
  06's open question: "do your recommendation"). Amends R28's "built only from
  the DraftKings salary and entries bytes": when a run carries an official
  status file, every person an identity-valid row marks `INACTIVE` (exact
  current-slate DraftKings ID, team, HTTPS source, aware time, as the exact-ID
  parser checks) leaves the baseline's pool, a disagreeing row included. It
  only narrows the pool; freshness and coverage remain certification checks,
  and a row or file that cannot be applied is a named limitation, never a
  stop. Session 06b.
- **R33, Showdown game theses** (Ben, 2026-09-24, on the ATL@GB Showdown).
  - "Ideally, each lineup should adhere to a specific game thesis. this isn't
    an exhaustive list but here are some examples: GB win big, ATL win big, GB
    win close, ATL win close, defensive battle, offensive shootout. You can
    have sub variants of each of those for example, high scoring or low
    scoring, etc.." Every Showdown lineup carries one named thesis, reported
    per Entry ID, and the portfolio spreads rows across theses.
  - The purpose is Captain diversification: "The fundamental problem with
    your build is that there is incredible concentration risk. Especially
    within the captain ranks. The goal of the game thesis adherence is to make
    sure there's diversification in captains for example, on a Green Bay win
    with a low scoring game it might make sense to captain their kicker or
    DST." A thesis may require its Captain from a named set, K and DST
    included, which no policy on 2026-09-24 could force.
  - "Backup quarterbacks, generally requiring an injury, which is why I would
    exclude them." A quarterback below his team's depth-chart starter is out
    of the pool by default.
  - "I would not exclude DST just like I would not exclude kickers." DSTs and
    kickers stay eligible, Captain included.
  - Not buildable on 2026-09-24. A policy has no per-team bounds, no required
    pieces and one rule set per run, and the prior is one mean per person, so
    six thesis sleeves assembled by hand collapsed onto the same core and
    repeated lineups across sleeves (R29). Session 23b adds the per-thesis rule
    sets (moved from Session 23 on 2026-09-25, `docs/chunks/P8-showdown-thesis-sleeves.md`);
    Sessions 24 and 28 add script-conditioned scenarios and thesis coverage. A
    thesis never moves a projection by a typed multiplier.
- **R34, the two portfolio goals** (Ben, 2026-09-24, after R33). "This is the
  type of thought process I want you to have one building these lineups and
  ultimately implementing this engine are two goals are winning large prizes,
  and minimizing washouts. Both require identifying leverage and
  diversification, and this is a way within showdown contests to do that."
  - Every build and every engine change is judged against both: the prize
    tail (Session 25) and washouts, a portfolio where nothing cashes (Session
    28's bank-estimated P(zero paid)). Leverage needs an ownership input
    (Session 26); until one exists, say leverage is unmeasured.
  - A legal, QA-clean portfolio can fail both. The first ATL@GB file had five
    captains at 25% each and four people in 13 of 20 lineups.
  - The no-EV rule is unchanged: these are goals, never reported as EV or a
    probability of winning.

Still in force from earlier, with full text in the backlog archive:

- the 2026-09-12 lock-clock ruling, amended by R28 and R29;
- the 2026-09-19 P1 hard stop on `TRANSFER_PRIOR_UNVERIFIED` with
  `SALARY_RANK_DIVERGENCE`, absorbed by R28 on 2026-09-23 (above): the person
  is excluded rather than the run stopped;
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
| O7 | Apply `ben-review` to the Session 01 pull request and merge it (merged as PR #42) | Session 03 onward | Done |
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

### 2.8 Priority basis and the 2026-09-25 consolidation

Ben's instruction, 2026-09-25: review the code, consolidate every plan,
backlog and fragment into this board, cut the work into chunks one session
finishes before a compaction, and rank each chunk by what wins large amounts
of money, respecting dependencies. This section is the ranking rule and the
audit trail; the rows above are the result. R34 is the yardstick: win large
prizes and avoid washouts, both through leverage and diversification.

**The rule, in tiers.** A row ranks by the first tier it belongs to, then by
the evidence for its lift, then by cost.

1. **A wrong file loses the entry fee outright.** Defects that can put a
   duplicate, overwritten, deleted or mislabelled file in front of Ben, and
   the Windows fallback command the runbook names but the launcher refuses.
   Sessions 37 and 38. Small, first.
2. **Construction changes with measured lift on graded standings.** The
   hygiene bounds and the 0.80 share cap (Session 23) are the only rule set
   that lifted P(at least one top-1%) and cut P(nothing paid) in every graded
   game; Classic diversification (39) removes the one-player-variant washout
   shape from our own portfolio; Ben's game theses (23b, 23c) are R33's answer
   to captain concentration; contest-aware assignment (23d) stops sending the
   weakest lineups to the first-place contests.
3. **Projection correctness on the live path.** The confirmed unit mismatch
   (21) misprices every player who missed games, every week, and costs one
   session.
4. **Late swap** (12) is the Classic slate's second decision point and the
   only path that can write an upload file, so its clock bound goes with it.
5. **The boundary** (41, 42): a second HTTP client and unbounded source hosts
   are rule violations in `CLAUDE.md`'s terms; they do not cost money this
   week, so they sit behind the construction sessions but ahead of scaffolding.
6. **The scenario bank and the tail objective** (24 to 25b, 28): the correct
   way to build a large-field portfolio, and a large build. It is ordered
   after the cheap construction wins because the simulator has to be fixed
   first (24), it needs the decomposition (44, 44b) to be editable in one
   session, and its acceptance is a mechanism check until the harness exists.
7. **Measurement** (17, 18, 18b, 26, 27, 29): the feedback loop. Cheap where
   it is code (17, 18) and gated by Ben's operator items (O1 to O4), so it
   runs in a cloud session alongside the construction work rather than ahead
   of it. Nothing in this tier changes a lineup until Session 29.
8. **Delivery scaffolding** (13, 14, 15, 15b, 16): R28's baseline-first
   already ships a file before any model stage, so the remaining delivery
   sessions are insurance and a record, not edge. They follow the money.
9. **Process** (43, 19, 20, 40, 22, 45, 46, 30): harness holes, tooling,
   cleanup, a ruling.

**What it reversed.** The 2026-09-22 order put Sessions 12 to 16 ahead of
every construction and model session. Sessions 13 to 16 now follow the
construction, prior-model and scenario-bank sessions; Session 12 keeps its
place near the top for the clock bound. Ben can overturn any of it by moving a
row; the table is the ruling.

**Session sizing.** Every card states its files, its changed-line estimate and
what it must read. The bound is §2.1 step 5: about 1,500 changed lines, or the
reading a single context can hold. Four briefs were split on that bound (P2
into 23 and 23d, P8 into 23b and 23c, P3b into 25 and 25b, P0 into 18 and
18b), the delivery scenarios into 15 and 15b, and the `prior_review`
decomposition into 44 and 44b.

**Dependencies re-cut.** Session 23 no longer waits on Session 18: its
mechanism is accepted on the supplied fixtures and its standings grading moved
to Session 18b. Session 24b's top-1% proxy is a registered constant from the
2026-09-15 findings until Session 18b replaces it. Session 39 depends on 23
(the ladder), 44 on 23c (order only), 13 and 14 on 44b (they edit the file it
splits), 46 on 24c (shared files).

**Where the 2026-09-25 code review landed.** `docs/critiques/Code_Review_2026-09-25.md`
holds every finding with file and line. By its IDs: V1, V2, V9, V10, V11, E12
in Session 37; V3 to V8 in 38; V12, V13, E11 in 12; V14 in 46; S1, S2 in 21;
S3 to S6 in 39; S7 in 23; S8 to S10 in 40; M1, M2, M4, M5, M8, M9 in 24; M3,
M6, M7 in 24c; M10 in 42; E1 to E3 in 41; E4 to E8 in 42; E9, E10 in 45; R1,
R5 in 44; R2 to R4, R6 in 44b; R7, R8 in 46; R9 in 40; H1, H2, H4, H5 in 43;
H3 in 19; H4's Windows half in 16; H6 in 45; §8 dead code in 46; §9 test gaps
in the session that owns each module.

**Where the archived and ledger items landed.** The 2026-09-25 sweep of
`changelog.md`, the two backlog archives, the four changelog archives, the 22
retired prompts, `plan.md`, the critiques, every retrospective and both
standings findings found these open items with no row: the Showdown QA exit
codes (Session 02b) in 37; the guard's `git add -N` gap (Session 03) in 43;
`make_classic_policy.py:174`'s stale claim in 45; the Showdown readable
review's missing named blockers, the C3 audit's missing weather and P1
limitations, and the untested `--available-status D` and post-write hash
paths in 44b; `session_probe`'s weather.gov exit and the scored pool's
omissions (Sessions 02b, 09) in 13; the per-operation fetch timeouts and the
start-gated build limits (Sessions 07, 07b) in 46; the inline lock derivation
in `priors.py:2398` and `preflight.py:381` in 42; the double C2 solve
(Session 08) in 40; the C1 overlap gap (Session 11c) in 39; R16 (the
official-status gate binds provenance, not a source) in 42; `nws_gridpoints.json`'s
14-stadium coverage in 41; the W3 simulator availability mask in 24; the
contest-screening checklist, the market-source question and the belief-space
dart taxonomy in 23d and 25b; the standings checklist's 8 awaiting contests
against O3's 2 stays with the checklist skill; the peak-memory and
per-entry-count benchmarks in 40 and 16. Contradictions the documents carry
and this board settles: the DEN@KC run record's "4-2 = 64.7% of the top 1%"
is wrong (35.0%; 3-3 was 54.3%, `docs/STANDINGS_GREENFIELD_FINDINGS_2026-09-15.md`
§9) and it drove the v6 policy; C4 retro #10 (QB leverage first) stays
rejected on the aggregate evidence, with the position-specific claim untested
until Session 18b can test it; the Showdown salary rule is "$1 to $500 left"
as a construction preference, not the audit's hard cap.

**Questions for Ben that block nothing.** Sleeve size and risk tolerance
(findings §7); a paid ownership-capture source (Showdown retro §7d, a
spending decision); Week-by-week stake sizing (retro §8 Q3); an odds-API
credit budget (`docs/SHOWDOWN_FIRST_PRODUCTION_PLAN.md` §7); whether Q1's
70-slate minimum is realistic against about 36 slates a season
(`docs/Q1_METRIC_REGISTRATION.md`); the open flags in the Session 12 and Session 46
cards; and Session 30's ruling.

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
| 2026-09-23 | Session 03b | In Progress to Complete | `16502c8` | 1,088 codes in 43 families, exact-code loader, completeness both ways; merged as PR #51 |
| 2026-09-23 | Session 04 | Pending to In Progress | `795de43` | Claim pushed on `claude/session-04-nfl-baseline-f7aptz` |
| 2026-09-23 | Session 04 | In Progress to Complete | `336d078` | `nfl baseline`, Classic and Showdown, six fixture runs `DELIVERABLE`; merged as PR #53 |
| 2026-09-23 | Session 05 | Pending to In Progress | `79e9c7f` | Claim pushed on `claude/session-05-artifact-preservation-3cecn4` |
| 2026-09-23 | Session 05 | In Progress to Complete | `e0eb4a7` | Preservation in both modes, `LATEST_DELIVERABLE.json`, v2 truths in `run-slate`; merged as PR #54 |
| 2026-09-24 | Session 06 | Pending to In Progress | `d869e9f` | Claim pushed on `claude/roadmap-session-06-ond9qs` |
| 2026-09-24 | Session 06 | In Progress to Complete | `f96bf6e` | Baseline-first `run-slate`, both modes; C1 exports its own CSV; merged as PR #55; `CLAUDE.md` follow-up merged by Ben as `f810349` (PR #56) |
| 2026-09-24 | Session 06b | Added as In Progress | `3f4ff04` | R32 (Ben, 2026-09-24); claim pushed on `claude/roadmap-session-06-ond9qs` |
| 2026-09-24 | Session 06b | In Progress to Complete | `1afd006` | Official inactives bind the baseline; baseline report v2; merged as PR #57 |
| 2026-09-24 | Session 07 | Pending to In Progress | `dd1203d` | Claim pushed on `claude/session-07-deadline-budget-hxfvfa` |
| 2026-09-24 | Session 07 | In Progress to Complete | `7b8997c` | Request v3, the run's budget through `run-slate`, the baseline and the review's solves; merged as PR #58; `CLAUDE.md` follow-up merged as `0af6cd4` (PR #59) |
| 2026-09-24 | Session 07b | Added as Pending | `7b8997c` | Fetch, weather-script and generator allowances, split at Ben's breakpoint; merged with PR #58 |
| 2026-09-24 | Session 07b | Pending to In Progress | `b213492` | Claim pushed on `claude/session-07b-deadline-budget-iwheie` |
| 2026-09-24 | Session 07b | In Progress to Complete | `e6673c2` | Fetch, weather-capture and generator allowances; `DEADLINE_FETCH_WINDOW_SPENT`; suite `1647 passed, 1 skipped`; merged as PR #60 |
| 2026-09-24 | Session 08 | Pending to In Progress | `d236025` | Claim pushed on `claude/session-08-nonoptimal-bank-gkusm7` |
| 2026-09-24 | Session 08 | In Progress to Complete | `b0066f8` | Limit-stopped banks and joint solves keep validated incumbents; C3 and SD3 exports name them; suite `1677 passed, 1 skipped`; merged as PR #61 |
| 2026-09-24 | Session 09 | Pending to In Progress | `82014e5` | Claim pushed on `claude/roadmap-session-09-jizzh0` |
| 2026-09-24 | Session 09 | In Progress to Complete | `c2e2d8c` | Weather `UNOBSERVED`, Classic activity and P1 ship named; suite `1698 passed, 1 skipped`; merged as PR #62 |
| 2026-09-24 | Session 10 | Pending to In Progress | `328166a` | Claim pushed on `claude/epic-planck-3jxp20` |
| 2026-09-24 | Session 10 | In Progress to Complete | `1f7efcf` | Relaxation controller, both ladders, `nfl_relaxation_record_v1`; suite `1715 passed, 1 skipped`; merged as PR #63 |
| 2026-09-24 | Session 11 | Pending to In Progress | `3cf7537` | Claim pushed on `claude/festive-lovelace-ffryd8` |
| 2026-09-24 | Session 11 | In Progress to Complete | `bd5a97f` | Per-row authority, prefilled rows preserved and forbidden, `entry_groups` by Contest ID, truths v3, pointer v2; suite `1737 passed, 1 skipped`; merged as PR #65 |
| 2026-09-24 | Session 11b | Added as Pending | `bd5a97f` | Subset binding, split at Ben's breakpoint; merged with PR #65 |
| 2026-09-24 | Session 11b | Pending to In Progress | `6d24bc3` | Claim pushed on `claude/affectionate-bohr-mnr8vz` |
| 2026-09-24 | Session 11b | In Progress to Complete | `6394eda` | Showdown subset binding with a sequential fill, the ladder over the subset, `--entry-id`, readable review `sd5_v2`; suite `1758 passed, 1 skipped`; merged as PR #66 |
| 2026-09-24 | Session 11c | Added as Pending | `6394eda` | C2 and C3 over a subset policy, split at Ben's breakpoint; merged with PR #66 |
| 2026-09-25 | Session 23b | Added as Pending | `adf4ef2` | Showdown game theses (chunk P8, R33 and R34), on Ben's request; Session 23 gives it R33's thesis target and the Showdown constraint vocabulary and keeps P2; merged as PR #68 |
| 2026-09-25 | Session 11c | Pending to In Progress | `e2d5e57` | Claim pushed on `claude/laughing-keller-b7cr5q` |
| 2026-09-25 | Session 11c | In Progress to Complete | `bedf6a3` | C2 with a C1 fill, C3 over the mixed portfolio (`classic_c3_v2`, export audit `c3_v3`), and C3's re-validation with the run's exclusions |
| 2026-09-25 | none | Code review and consolidation | recorded by the next session | Five read-only review passes (`docs/critiques/Code_Review_2026-09-25.md`, no BLOCKER) and three document sweeps consolidated into this board; the board re-ranked by expected winnings (§2.8); suite on `bedf6a3` `1762 passed, 1 skipped in 338.00s` |
| 2026-09-25 | Sessions 37 to 46 | Added as Pending | recorded by the next session | Showdown file integrity, run-path integrity, Classic diversification, solver time, weather boundary, official-status discipline, harness holes, `prior_review` decomposition, ledger truth, dead code |
| 2026-09-25 | Sessions 15b, 18b, 23c, 23d, 24b, 24c, 25b, 44b | Added as Pending | recorded by the next session | Splits at the single-session bound (§2.8) |
| 2026-09-25 | Sessions 12 to 36 | Re-ordered | recorded by the next session | Row order is priority; numbers are stable names (§2.1); Sessions 21, 23, 24, 25, 13, 14, 15, 16 re-scoped and their dependencies re-cut (§2.8) |
