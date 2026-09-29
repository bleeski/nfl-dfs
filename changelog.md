# NFL DFS Implementation Changelog

This file records completed implementation work and verification evidence for the sessions in `docs/ROADMAP.md`. Keep entries factual and append new dated sections beneath `Unreleased`. Do not describe planned, diagnostic, synthetic, or structurally legal work as live-certified or upload-ready.

## Unreleased

### 2026-09-29: Session 21 -- prior-model triage: per-game rate shares, the transfer pool, alternate-name proposals

Branch `claude/s21-prior-model-triage` (no branch was assigned; restarted from `origin/main` at
`ce7eeaf`), task file `state/tasks/S21.md`, pull request recorded in the ledger. Started after PR #86
(Session 50c, merge `ce7eeaf`, now recorded on its ledger row) was on `main`. Every path still ends
`MODEL_STATUS=PRIOR_ONLY / RELEASE_DECISION=DO_NOT_UPLOAD`; no protected path touched. The
`/dev-session` and `/advisor` skills were not invoked as skills: this session followed
`dev-session/SKILL.md` and `advisor/SKILL.md` directly (the advisor as an `Agent` call with
`model: "fable"`), per the session prompt's note on the harness hook.

#### The default flipped

New prior freezes (`freeze_prior_package`, `priors-freeze`, and so every `--build-priors` run) now
write player transformation v2 by default. This changes model values for every new package: a
player who missed games no longer carries a smaller share, and a transfer into a thin room no longer
gets `s / (1 + s)` of the group. `--player-transformation NFLVERSE_PRIOR_SEASON_POOL_NORMALIZED_OPPORTUNITY_SHARES_V1`
(or `player_transformation=PLAYER_TRANSFORMATION_V1`) reproduces v1 byte for byte. Frozen v1 packages
are read as written and need no rebuild (see Verification). RUNBOOK and `docs/DATA_CONTRACTS.md`
say so. Why default rather than opt-in: the card mandates the fix, priors are `PRIOR_ONLY`
diagnostics, and a known-biased default kept for safety is the defect the card names (advisor
agreed after arguing the opt-in side).

#### Added

- `PLAYER_TRANSFORMATION_V2` (`NFLVERSE_PRIOR_SEASON_PER_GAME_RATE_OPPORTUNITY_SHARES_V2`): each
  person's current-team counts divided by `max(games, MINIMUM_PRIOR_GAMES)` (`games` = distinct
  weeks with a row, floor 4), share = rate over the pool's summed rates. A person with four or more
  rows projects at exactly his per-game rate. The floor is a judgment, not a calibration: it
  reuses the existing team-rate constant so no new number appears, and it stops a one-game player
  from outranking a starter (pure rates would give him a larger share than v1 did). Recorded per
  person (`games`, `effective_denominator`, `thin_sample`, `rate_basis`) and in
  `coverage.transformation_does_not_establish`.
- Transfer prior v2 (`transfer_prior_own_old_team_share_v2`): the pseudo-rate is the transfer's old
  share (floored by the same rule over his old-team weeks) times the current team's per-game total
  over all of that team's rows, from the same frozen `player_stats` bytes. Full room: identical to
  v1. Thin room: fixture SEA receiving room, v1 0.333333, v2 0.888889. Empty group (the Miami
  quarterback shape): v1 weight 0, v2 weight 1.
- F8: `ALTERNATE_NAME_TEAM_POSITION` and `ALTERNATE_NAME_TEAM` proposal methods (nflverse
  `first_name`/`last_name`/`football_name`, accent-folded), placed after every existing tier so only
  an `AMBIGUOUS` or `UNMATCHED` outcome can change. Never in `IdentityProposal.resolved`; the review
  file leaves `DECISION` blank; `apply_identity_gate` blocks them; `AUTO_ACCEPT_MATCH_METHOD` is
  untouched (the `resolved` source is hash-pinned in a test).
- `priors-freeze --player-transformation`. Blocker `PLAYER_TRANSFORMATION_UNKNOWN` in
  `config/gate_registry_v1.json` (family `prior_package`); `REGISTRY_SHA256` re-pinned in
  `tests/test_gate_registry.py` and `docs/DATA_CONTRACTS.md` to
  `b532b806c52c1b47dbafb62bfea9aab0a9ce1aab6ec487284dc5052535efc56f`.
- `tests/test_prior_rate_transformation.py` (16 tests) and `tests/test_identity_alternate_names.py`
  (9 tests).

#### Changed

- `tests/test_priors_adapter.py`: `AS_OF` is derived from the fixture's Game Info lock (lock minus
  6h25m, evaluates to the same `2026-09-13T14:00:00+00:00`), and `CAPTURED` from `AS_OF`; the
  hardcoded literals are gone (C4 retro #17).
- `tests/test_offensive_history.py:50`: the one existing test edited. It asserted the transfer
  prior's `basis_version` equals `TRANSFER_PRIOR_VERSION` (v1) under the default; the default is now
  v2, so it expects `TRANSFER_PRIOR_VERSION_V2`. The v1 string is still asserted, under an explicit
  v1 selection, in the new module. No assertion was loosened.
- `docs/DATA_CONTRACTS.md`: a v2 subsection, a transfer-prior v2 paragraph and the F8 methods;
  `docs/RUNBOOK.md`: the default flip. Adapter version stays `nflverse_prior_adapter_v2`.

#### Verification

- Baseline before any edit: `1967 passed, 1 skipped in 682.24s (0:11:22)`.
- Reproduced first: the new tests failed on the old code (no `PLAYER_TRANSFORMATION_*`, no
  `alternate_name_keys`). The v1 goldens `0f05ee0d...d77e` (base) and `6ce291b8...61b6` (a receiver
  moved to another team) were computed on the unedited `priors.py`, before the first source edit.
- First full run with the change: `1 failed, 1991 passed, 1 skipped in 668.71s (0:11:08)`; the
  failure was `test_the_quick_start_names_the_first_startable_session`, expected while §1 still
  named S21, cleared by this close-out.
- Final full run: `1992 passed, 1 skipped in 662.45s (0:11:02)`.
- Size and split: `src` +279/-18 and `tests` +538/-8 (843 changed lines, under the 900 line the brief set for
  a split); docs, config and state +213/-6. Not split into a Session 21b: F8 is independent of the rate
  work but the total stayed under the bound.
- Reviewer agent on the diff: no correctness gap. It found the new registry key out of sort order
  (fixed, hash re-pinned) and a blank line at EOF (fixed).
- No pinned hash moves: nothing in `src`, `scripts`, `tests` or `data` pins a prior-package or
  player-artifact hash or reads the `transformation` string or `basis_version`
  (`prior_score.py` never reads the player artifact); `projection.py` reads only the frozen
  records, so a v1 and a v2 package go through one path.

#### Left open

- Advisor (Fable) rounds: versioning, the team pool, the sample floor. It moved two things:
  every basis string follows the selector, and the transfer's old-team weeks get the same floor.
- A game counts as a full game if it has any stats row; a partial game counts whole, and a game
  with no row is not a game (snap data joins on the PFR id, not `player_id`; noted, not built).
  `games` is distinct weeks while counts sum every row: nflverse ships one row per player-week, so
  a duplicate is theoretical. A blank `week` cell counts as one week.
- The rate-scale pseudo is quantized to 1e-6; below about 1e-4 relative loss in realistic cases.
- No gate-level test runs a transfer-only room through `offensive_roles`. V2 turns such a group
  from `TRANSFER_PRIOR_ZERO` (excluded) into `TRANSFER_PRIOR_UNVERIFIED` (diagnostic, `UNKNOWN`);
  the record-level change is pinned, and the reviewer found no route to a new
  `ZERO_OR_MISSING_SHARE_GROUP` or `PRIOR_SUPPORT_MISSING`.
- The `[BEN: ...]` flags are unchanged (four, none new).

### 2026-09-29: Session 50c -- intra-contest diversification, the Classic exits and the baseline

Branch `claude/s50c-classic-contest-diversity` (no branch was assigned), task file
`state/tasks/S50c.md`, pull request recorded in the ledger. Started after PR #85 (Session 50,
merge `4adfd43`, recorded in the roadmap ledger) was on `main`. Every path still ends
`PRIOR_ONLY / DO_NOT_UPLOAD`; no protected path touched.

#### Added

- `contest_assignment.apply_step` runs on all three Classic exits in `prior_review`: C1
  (one `all` pool), C2 with its C3 package and export (`bound` pool for the policy's
  rows, `fill` pool for the rows C1 fills beside a subset policy), each right after
  selection and before any artifact. The C2 selector's `pairwise_person_overlap` is
  relabelled. `restarts` is a new optional argument (the baseline passes 0).
- New hashed record `selection/contest_assignment.json` (`nfl_contest_assignment_step_v1`,
  the step's report without wall-clock `seconds`), so C3 reconciles its block against an
  artifact. Chosen over adding a key to `nfl_classic_prior_review_selection_c2_v1`, which
  a versioned contract forbids.
- `audit_classic_portfolio` takes the exact `assignments.csv` bytes, their hash and the
  claim: per-pool multiset (`MULTISET_CHANGED`, `V`), filled rows from the template bytes
  (`FIXED_ROW_MOVED`, `V`), contest readings (`STATS_MISMATCH`, `P`, audit still passes),
  and the policy's CSV rows equal to `classic_assignment.json` row for row
  (`CLASSIC_AUDIT_ASSIGNMENT_ARTIFACT_MISMATCH`, `V`; the advisor's point: a multiset check
  cannot see two artifacts disagree). C3 holds `assignments.csv` to the selection record
  (`CLASSIC_C3_ASSIGNMENT_CSV_DISAGREEMENT`) and builds the block through `review_block`,
  in the readable JSON, the HTML (`_render_classic_html`) and the workbook's `Exposure`
  sheet. `portfolio_enforcement.contest_assignment_reading` is now public and shared.
- C1's export (`cli._export_classic_c1_csv`) audits with the claim, carried in memory on
  `PriorReviewOutcome.contest_claim` (never serialized). C1 has no readable review: its
  block is the step's report in the selection report, the run result and
  `export.c1_export.contest_assignment`.
- The baseline (`run_baseline`, both modes): no restarts, at most 0.4 s and never past the
  run's budget, `nfl_baseline_report_v4` (`contest_assignment`, `report["lineups"]` now in
  file order, `audit.contest_assignment`); `audit_baseline_bytes` takes the claim. R28: if
  the audit refuses only because of the step's claim (every problem a `CONTEST_ASSIGNMENT_*`
  code, or the reading raised), the baseline falls back to the salary order, re-audits
  without the claim and names `CONTEST_ASSIGNMENT_STEP_FAILED` (`P`). The reviewer found
  the first version withheld the whole baseline in that case; fixed with two tests.
- Registry: seven codes (`CLASSIC_AUDIT_ASSIGNMENT_ARTIFACT_MISMATCH`, `..._CSV_INVALID`,
  `..._CSV_SHA256_MISMATCH`, `CLASSIC_C3_ASSIGNMENT_CSV_DISAGREEMENT`,
  `CLASSIC_C3_CONTEST_ASSIGNMENT_{BYTES_NOT_CANONICAL,JSON_INVALID,OBJECT_REQUIRED}`);
  `REGISTRY_SHA256` re-pinned to `9e7c13ed...ae13` in `tests/test_gate_registry.py` and
  `docs/DATA_CONTRACTS.md`. A dict splat in the audit's hash table hid a template from the
  registry scan; the CSV hash is checked outside it.
- `docs/DATA_CONTRACTS.md`: Classic wiring and audits, the step record's fields,
  `nfl_baseline_report_v4` (v3 untouched), the baseline objective's order note (a
  multi-contest baseline is in salary order as a set, no longer row by row); RUNBOOK
  paragraph updated.

#### Changed tests (their own visible change)

- `tests/test_baseline.py`: the schema assertion moves from `nfl_baseline_report_v3` to
  `v4` and asserts the block. `tests/test_gate_registry.py`: the registry hash pin.
  Nothing else edited; no test deleted, skipped or loosened.

#### Acceptance evidence

- **Week 3 Classic, real bytes, through the baseline** (25 entries, eight two-entry
  contests and nine one-entry, `data/inbox/slates/wk3-classic-2026-09-27/`, offline):
  three contests repeated a QB before (`195922612`, `195922629`, `195922640`), none after;
  worst shared count 3 to 0 (contest `196104830`), every contest at 0; total score 104 to
  0; recomputed from the delivered bytes and equal to the step's report; audit `PASS`; step
  0.001 s, run 0.54 s; `DELIVERABLE`, `PRIOR_ONLY / DO_NOT_UPLOAD`. Same numbers Session 50
  measured.
- **Model path on the real Week 3 bytes was not run**: no frozen prior package, role
  evidence or official status for it is in the repository (`data/runs/` and `data/models/`
  are empty). The model path is shown on the synthetic Classic fixtures: C1 total score
  278 to 126 (three contests, QB-repeat template), C2/C3 242 to 194, no contest repeating a
  QB after, audit `PASS`, block reconciled, recomputed from the delivered bytes in the
  tests.
- Tests added: `tests/test_contest_assignment_classic.py` (22: one `run-slate` test per
  exit, the subset pools, determinism, a failed step on each exit, a single-contest run,
  the audit refusing an outsider, a row exchange in the CSV alone, a wrong hash, a moved
  filled row and a lying report, C1 and C3 lying-report `P`, an outsider through C1 and
  C2, C3 replays including the mutation test of the new artifact) and
  `tests/test_contest_assignment_baseline.py` (11: both modes, v4, determinism, single
  contest, the cap, failed step, lying report, the R28 fallback, a raising reading, a moved
  filled row).

#### Decisions

- **Size.** About 1,320 changed lines with tests (354 non-test source), past the 900-line
  breakpoint that says to split the baseline into Session 50d. Not split: the baseline
  slice is about 85 source lines, already verified on the real Week 3 bytes, and C1's export
  audit shares `audit_baseline_bytes` with it, so a seam would leave C1 half-wired. Ben can
  overturn this.
- **Baseline timeout keeps the best climb** (the card's rule). It is machine-dependent when
  it trips; `timed_out` is recorded. A `max_evaluations` counter in `assign_contests` would
  make it reproducible; not done.
- **Advisor** (a Fable subagent; the `/advisor` and `/dev-session` skill calls fail on the
  harness's skill hook, `set: Illegal option -o pipefail`, so both SKILL.md files were
  followed directly): agreed with reading `assignments.csv` in the C2 audit and with the
  step inside `run_baseline`; added the row-for-row CSV/JSON check and the
  `report["lineups"]` rebuild, both taken.

#### Left open

- A `P` `STATS_MISMATCH` seen only by the C2 audit surfaces as a named limitation through
  C3's reconciliation; C3 removes its JSON and HTML for it, not just the block.
- `cli.py` `selection` command (outside `run-slate`) still maps lineups in solver order.
- `assign_contests` builds its cost matrix before checking the deadline (O(n squared)).

#### Verification

- Baseline before any edit: `1934 passed, 1 skipped in 409.78s (0:06:49)`.
- Final: `sh ./nfl.sh test`: `1967 passed, 1 skipped in 435.64s (0:07:15)` (1934 before, 33 added).
- `git diff --check` clean; `python3 scripts/check_protected_paths.py`: no protected path touched.

### 2026-09-29: Session 50 -- intra-contest diversification, the shared module and the Showdown exits

Branch `claude/youthful-mccarthy-df7yml` (the assigned branch, in place of the
prompt's `claude/s50-contest-diversity`), pull request
[bleeski/nfl-dfs#85](https://github.com/bleeski/nfl-dfs/pull/85), task file
`state/tasks/S50.md`. Started after PR #83 was on `main` (merge `4530733`).
Every path still ends `PRIOR_ONLY / DO_NOT_UPLOAD`; no protected path touched.

**Split at the mode seam, as the card ordered.** The module, its tests, the
wrapper and the Showdown wiring passed the card's 900-line breakpoint, so this
session lands the shared module and the Showdown exits (policy, sequential,
subset-fill) and Session 50c takes Classic C1, C2, C3 and the baseline.

#### Added

- `src/nfl_dfs/contest_assignment.py` (standard library only), registered
  `contest_assignment_version = within_contest_diversity_v1` with
  `does_not_establish` text; documented in `docs/DATA_CONTRACTS.md`. Per contest,
  over every lineup pair: `shared_people**2` + 12 same Captain (Classic: QB) + 6
  same Classic primary stack team + 3 same thesis.
- **Contest-size weighting, decided:** a contest scores its worst pair cost plus
  its mean pair cost, every contest weighted equally, a one-entry contest 0. The
  raw sum let 21-pair contests crowd out the two-entry ones (PHI@CHI v4 left a
  two-entry pair at 3 shared). Worst-plus-mean keeps one bad pair in a small
  contest fully counted and stops the search ignoring the other pairs. On PHI@CHI
  v1 it left two seven-entry means higher than v2's raw-sum result (2.76 and 3.05
  against 2.48 and 2.24; the third is level at 2.43) in exchange for every two-entry
  pair at 1 and one worst pair at 3: a stated tradeoff, inside the acceptance.
- **Classic primary stack team, defined:** the team with the most rostered QB, RB,
  WR and TE (never DST or kicker), ties to the QB's team then the lower
  abbreviation, undefined below two players. It names the game script a lineup
  bets on, which the QB term alone misses (two QBs, one team's stack).
- **Search:** cross-contest pairwise swaps from the solver's order (a swap inside a
  contest cannot change a score), seeded restarts (seed 20260929) with a count fixed
  by the entries (`restarts_for`: 300 at 36 rows, 44 at 150 rows in contests of 5,
  none at 150 rows in contests of 50), all inside a time allowance of a fifth of the
  `Budget` improvement window (at most 20 s). A timeout keeps the best found. The
  solver's order is always a candidate; by default no contest scores worse than in
  the solver's order (a Pareto climb, and restarts filtered for dominance).
- **Pools and fixed rows:** filled rows never move but count in their contest;
  a policy's bound rows and the fill rows are separate pools (C3 and the policy
  caps are defined per set); rows of a one-entry contest stay where the solver put
  them.
- **Wiring** (`prior_review.py`, Showdown only): after selection and before any
  artifact, only the values of `assignments` move, so `assignments.csv`, the
  pre-lock manifest, the audit and the review all see the diversified assignment.
  Failure leaves the solver's order and names `CONTEST_ASSIGNMENT_STEP_FAILED` (`P`,
  registry family `contest_assignment`); `cli.py` carries it as a delivery
  limitation. The selector's `pairwise_person_overlap` labels follow the lineups.
- **Audit:** `audit_policy_assignments` recomputes, from the exact bytes of
  `assignments.csv` (filled rows from the template's bytes), the per-pool lineup
  multiset (`CONTEST_ASSIGNMENT_MULTISET_CHANGED`, `V`), filled rows
  (`CONTEST_ASSIGNMENT_FIXED_ROW_MOVED`, `V`) and each contest's readings
  (`CONTEST_ASSIGNMENT_STATS_MISMATCH`, `P`: recomputed numbers kept, audit passes).
- **Review:** a `contest_assignment` block in the readable review JSON and HTML and
  on the workbook's `Exposure` sheet (per contest: entries, worst pair and mean
  shared before and after, distinct Captains before and after, distinct theses,
  people in every lineup, score before and after). Both readings are recomputed from
  the delivered rosters and the selection order, then reconciled with the step's
  report under `DISPLAY_RECONCILIATION`.
- Registry: one family and nine codes; `REGISTRY_SHA256` re-pinned to
  `4a40d3f2...115d` in `tests/test_gate_registry.py` and `docs/DATA_CONTRACTS.md`.
- `scripts/diversify_showdown_contests.py` is a thin wrapper over the module, gains
  Classic (mode read from the template header), keeps its flags (the penalty flags
  override the weights and the record says so) and writes
  `nfl_contest_diversification_v2`; v1 (the committed `assignment_v*.json`) is never
  mutated. It loads the stdlib-only module by path, so it runs under any Python 3.
  Its `assignment_v2.json` bytes are no longer reproduced: the objective changed.

#### Checks before wiring, answered

- No audit or test asserts prior-descending or solver order of assignments; they
  check Entry-ID sequence and coverage. `tests/test_classic_review_c3.py:613` and
  `tests/test_classic_portfolio_c2.py:170` do not (the second is policy
  canonicalisation). No rule changed.
- C1 and sequential Showdown take solver order from `_sequential_lineups`
  (`selection.py:690`, called at `:595`); the joint solvers sort at
  `portfolio_enforcement.py:953-968` and `classic_portfolio.py:862`.

#### Acceptance (evidence)

- **PHI@CHI** (`DK_REVIEW_ENTRY_phi-chi-sd-v1.csv`, `theses_v1.json`, the script, 300
  restarts, 3.9 s wall): 7 distinct Captains of 7 in each seven-entry contest,
  worst pairs 4, 3, 4 (v2: 4, 4, 4), every two-entry pair at 1 (v2 left one at 3);
  score 255.24 to 81.57. The reviewer reran it twice: byte-identical files.
- **DET@BUF** and **Week 3 Classic** have no committed portfolio, so the module ran
  on `nfl baseline` portfolios built from their DraftKings bytes (not the model's
  lineups, no network): DET@BUF's seven-entry contest went from 6 to 7 distinct
  Captains; Week 3's eight two-entry contests went from three repeating a QB and a
  worst shared count of 3 to no repeated QB and 0 in every contest (score 104 to 0).
  Classic `run-slate` acceptance is Session 50c's.
- Run-slate tests through `run-cowork`: sequential, policy and subset policy each
  diversify (`IMPROVED`), the file, `assignments.csv`, the audit and the review agree
  and the bytes recompute the reported total; a prefilled row stays byte-identical;
  a failed step ships the solver order with the `P` limitation; a tampered
  assignment (a legal lineup the selection never held) is refused by the policy
  audit (`MULTISET_CHANGED`) and, on the sequential exit, by the readable review;
  a moved filled row is refused; a lying report is `P`; `lineup_count` above the
  entries still ships.

#### Baseline decision

Included in 50c, not here. Measured on synthetic 150-entry portfolios: 0.06 s for
the single climb from the baseline's order in contests of at most 5, 0.3 s at 10
entries a contest, 4.3 s at 50, so it needs a cap (0.4 s, no restarts) to stay well
under a second, and it needs `nfl_baseline_report_v4` and the baseline audit to carry
the block. It shares its writer with C1, so it lands with C1.

#### Fixed in review

The reviewer found `review_block` compared the delivered row count with every
selected lineup, so sequential Showdown with `lineup_count` above the entry count
would have withheld a valid CSV as a false `V`; it now compares with the first N (test
added). It also found the filled-row check could not bite on the production audit
path (`assignments.csv` holds fillable rows only); the audit now reads filled rows
from the template bytes. The first full run failed two tests that pin the workbook's
sheet list, so the block sits on the existing `Exposure` sheet and no test changed. The
baseline run at the start of the session caught one failure of my own making:
`tests/test_repo_boundaries.py::test_no_module_names_a_value_ev_roi_or_edge`
flagged `WIN_PROBABILITY`/`CASH_PROBABILITY` literals in the new module's
`does_not_establish`, which now reads `WIN_OR_CASH_LIKELIHOOD`.

#### Verification

- Baseline before the change: `1871 passed, 1 failed, 1 skipped in 441.46s (0:07:21)`;
  the failure is the boundary test above, caused by the new module created while the
  run was in progress. The last recorded clean suite was `1872 passed, 1 skipped`.
- Final: `sh ./nfl.sh test`: `1934 passed, 1 skipped in 442.05s (0:07:22)`; `git diff --check` clean; `python3 scripts/check_protected_paths.py`: no protected path touched.

#### Left open

- Session 50c: Classic C1, C2, C3 and the baseline.
- Prior points are not in the objective, so the step does not keep the strongest
  lineups out of the weakest contests; Session 23d's `contest_facts_csv` is where
  per-contest value would enter.
- DET@BUF and Week 3 acceptance ran on baseline portfolios, not model portfolios.
- Under `no_regression` most restarts are rejected; a wider search is possible if a
  slate shows a contest the climb left worse than a random assignment would.

### 2026-09-28 (slate run): PHI@CHI Showdown, 36 entries, six thesis sleeves, prior-only review

Cloud session, branch `claude/mnf-showdown-lineups-t7zjls`, task file
`state/tasks/phi-chi-sd-0928.md`. Every run ended `PRIOR_ONLY / DO_NOT_UPLOAD`;
no evidence gate was relaxed and no observation was invented. 36 blank reserved
entries across 12 contests; lock 20:15 ET, delivery deadline 20:10 ET (R31).
Inputs, committed under `data/inbox/slates/phi-chi-sd-2026-09-28/`:

    salary  322d7acf2266bb57c9d8aab419e542bf48cb6971dbadd49beb0591aa3973138a
    entries 3d1f911a00968ee2413b8d988364e4b3fe3fb1e9341bde45327ac07b257ac5b4

#### Running order

- `session_probe.py` exit 0, every allowlisted host reachable, 218.6 minutes to
  lock. The run's own probe then reported `github.com` blocked: the proxy CA
  fails `VERIFY_X509_STRICT` and the first run lacked the approved opt-in.
- Run `20260928T203657Z-phi-chi-sd-0928`: baseline published first
  (`de6b29c5…656b`, 36 rows), then priors failed on that TLS check. Rerun with
  `NFL_DFS_TLS_ALLOW_NONSTRICT_CA=1`.
- Run `20260928T203727Z-phi-chi-sd-r2`: `PRIOR_REVIEW_IDENTITY_BLOCKED` on two
  people, both exact name-and-team rows in that morning's nflverse depth chart
  (snapshot 2026-09-28T15:17:44Z): Scotty Miller `00-0035298` (CHI) and
  Hollywood Brown `00-0035662` (PHI, `OUT`). Resolved through the reviewed
  crosswalk (`identity_reviewed_phi_chi.csv`, `0c05b722…4274`), then
  `priors-freeze` (`data/runs/phi-chi-sd-0928-frozen`).
- QB depth package from the same depth chart through `sources.py`
  (`make_offensive_role_evidence.py --fetch`). It promotes Tyson Bagent, the
  rank-2 quarterback, over DraftKings-`OUT` Caleb Williams.
- NWS capture for Soldier Field (`generatedAt` 2026-09-28T20:39:57Z; tonight
  58°F, wind 0 to 5 mph, 0% precipitation). The frozen package's
  `UNOBSERVED` still won over the run-slate weather flags (Found, below).
- Research, informing construction only: the Bears' site called the QB a
  game-time decision between Bagent and Case Keenum; CBS Sports, NBC Sports
  Philadelphia and ABC7 Chicago reported Keenum expected to start. The Eagles
  elevated Zach Ertz (with Goedert `OUT`). No Bears elevation was found.
  Excluded by exact ID as practice-squad or cut with no elevation: Zavier
  Scott, Scotty Miller, Jaydon Blue, Dameon Pierce, Xavier Gipson, Josiah
  Deguara; Tanner McKee as a backup quarterback (the ATL@GB precedent).
- Run `20260928T204130Z-phi-chi-sd-r3` (no policy):
  `READABLE_REVIEW_ASSIGNMENT_ENTRY_ORDER_MISMATCH`, fixed below.
- One joint policy over all 36 rows (A, then B with overlap 5): the bank's
  chain stratum reached 30 of 38 and went `MODEL_INFEASIBLE`, twice, then the
  ladder took rung 4. Measured against the bank directly, the binder was the
  salary floor together with the exposure caps. Policy E1 (no floor) delivered
  at the supplied rung (`b12d0873…ce86`) with an eight-row barbell tail
  ($32,300 to $40,400) and no thesis structure; kept as the safety file and
  not handed over.

#### Delivered

`DK_REVIEW_ENTRY_phi-chi-sd-v1.csv` `7ba0c88b…a668` (run
`20260928T211255Z-sd-S3R2`), 36 rows. It was built in prefilled rounds: each
round's policy binds one thesis's rows, and the earlier rounds' rows are
prefilled in a byte-verified template copy (the procedure is now in
`docs/RUNBOOK.md`, under the subset-policy paragraph).

| Sleeve | Rows | Thesis | Rung |
|---|---|---|---|
| S1 | 11 | PHI wins big: CHI pass game out, Eagles DST allowed with PHI offense | supplied |
| S2 | 10 | Close game, both passing games alive, Bagent at most 1 row | supplied |
| S3 | 5 | Shootout: one QB or more, two or more pass catchers with him, no DST | supplied |
| S4 | 5 | CHI upset: PHI pass game out, Bears DST allowed with CHI offense | 1 (Captain caps widened to 0.25, salary band dropped) |
| S5 | 4 | Low-scoring: kicker or DST Captain only, Hurts and Swift out | supplied |
| S6 | 1 | Eagles defense: DST Captain | supplied |

One S3 row shared all six people with an S2 row (captain swap). It was blanked
and refilled by a one-row policy excluding Swift (`sd-S3R2`).
`qa_showdown_portfolio.py` against the original template: `VERDICT PASS`, 0
defects, 0 limit breaches, max overlap 5, salary 40,500 to 50,000, 11 distinct
captains (Hurts 8, Barkley 5, Smith 5, Loveland 4, Swift 4, Santos 2, Ertz 2,
Elliott 2, Odunze 2, Bagent 1, Eagles DST 1). The template byte check: 36 of
121 lines changed, six roster cells each, nothing else. Exposure: Hurts 24,
Smith 22, Santos 21, Loveland 20, Barkley 20, Swift 19, Odunze 19, Monangai
18, Ertz 16, Burden 12, Elliott 11. Seven people in more than half the rows,
structural in a pool of about 11 viable players. Team splits PHI-CHI: 3-3 14,
2-4 10, 4-2 6, 1-5 4, 5-1 2. Bagent is in 3 rows.

#### Changed

- **`prior_review.py`: the no-policy Showdown assignment is written in
  template order.** It was sorted by Entry ID, and the readable review, which
  checks template order, withheld the file whenever the template's Entry IDs
  were not ascending, as a multi-contest DKEntries download usually is. That
  made rung 4 undeliverable on this slate. `assignments` is already keyed in
  `entry_ids` order on both paths. New test
  `tests/test_entry_groups.py::test_a_showdown_template_whose_entry_ids_are_not_ascending_ships_in_template_order`
  (sequential and SD3); the sequential case fails on the old code with the
  exact slate error, and both pass on the fix.
- `docs/RUNBOOK.md`: the prefilled-round sleeve method and its three measured
  limits.

#### Found, not fixed

- **The ladder skipped rungs 1 to 3** on the 36-row joint policy: attempt 1
  (bank resized to 216) hit `CANDIDATE_BANK_TIME_LIMIT` at the 72 s budget, and
  the next step was rung 4, not a structural rung. On the small sleeves the
  same failure class walked rung 1 and rung 2 as designed. Worth a look in
  `relaxation._bank`: a time limit after a resize may deserve a structural
  rung before no policy.
- **Captain strata ignore the other caps.** Every K or DST Captain candidate
  in the S5 bank carried Hurts and Swift, both capped at 2 of 5 rows, so the
  sleeve was infeasible at every rung until they were excluded. This is Session
  23b's "a thesis that requires a kicker captain builds one" acceptance.
- **The overlap cap does not reach prefilled rows.** A one-row refill at
  overlap 5 rebuilt the exact lineup it replaced. Cross-sleeve overlap is
  unchecked until QA; Session 23c's joint assembly is the real fix.
- **`--prior-package-dir` keeps the package's frozen weather.** The run-slate
  weather flags were ignored and the game ran `WEATHER_UNOBSERVED` beside a
  valid capture. It moves no number (R24); re-freeze with the weather flags to
  clear it.
- **Keenum, the likely starter, has no score.** He has no prior-season row,
  and the depth chart ranks him third, so the engine can only model Bagent.
  Research cannot write a number. Bagent was capped at 3 rows as the hedge;
  Keenum is absent from the portfolio. Makai Lemon (rookie, PHI WR3 with
  Hollywood Brown `OUT`) is excluded the same way.
- **26 of 36 entries sit in contests whose names say satellite.** No payout
  table was supplied and a contest name is never evidence, so they were not
  built differently. Session 23d's `contest_facts_csv` is where that belongs.
- The Chicago Bears' page for the QB decision said "game-time decision"; the
  post-inactives check at 18:50 ET re-reads it and replaces Bagent rows if
  Keenum is confirmed.

#### Verification

- `sh ./nfl.sh test tests/test_entry_groups.py -x --tb=short -k not_ascending`:
  2 passed; with the fix reverted, 1 failed
  (`READABLE_REVIEW_ASSIGNMENT_ENTRY_ORDER_MISMATCH`), 1 passed.
- Full suite `sh ./nfl.sh test`: `1864 passed, 1 skipped in 373.24s (0:06:13)`.

#### Addendum: v2, the same lineups diversified within each contest

Ben asked for more diversification inside the contests holding several
lineups (three satellites hold 7 each; six contests hold 2). In v1 one of
those contests had DeVonta Smith as Captain in 3 of its 7 lineups, each
seven-entry contest had pairs sharing five of six people, and three
two-entry contests paired lineups sharing four.

- **`scripts/diversify_showdown_contests.py`** (new, standard library).
  It reassigns a filled file's lineups to Entry IDs, never moving a row the
  template already filled. Per contest, summed over every lineup pair, it
  minimizes `shared_people**2 + 12 * same_captain + 3 * same_thesis`, by
  deterministic pairwise swaps from the input assignment and 300 seeded
  restarts. Before writing, it verifies against the template: only blank
  roster cells differ, the lineup multiset is unchanged, and a quoted field
  is refused. 8 tests in `tests/test_diversify_showdown_contests.py`.
  Captain penalty 12, not 6: at 6, one seven-entry contest still held a
  repeated Captain; at 25, a two-entry contest paired two lineups from one
  thesis.
- **v2:** `DK_REVIEW_ENTRY_phi-chi-sd-v2.csv` `c14a2c38…4c04d`, written from
  v1 with `theses_v1.json` (the sleeve plan, with the repair row labelled as
  its sleeve). The committed script reproduces it byte for byte. Record:
  `assignment_v2.json`, score 726 to 443, 35 rows moved. Same 36 lineups as
  v1; the template byte check again shows 36 of 121 lines changed, roster
  cells only. `qa_showdown_portfolio.py`: `VERDICT PASS`, 0 defects, 0 limit
  breaches. Full suite `sh ./nfl.sh test`: `1872 passed, 1 skipped in 359.60s (0:05:59)`.

| Contest | Rows | Worst pair (people), v1 to v2 | Mean shared | Distinct captains |
|---|---|---|---|---|
| 196040036 | 7 | 5 to 4 | 2.86 to 2.48 | 6 to 7 |
| 196040050 | 7 | 5 to 4 | 2.62 to 2.43 | 5 to 7 |
| 196172224 | 7 | 5 to 4 | 2.81 to 2.24 | 5 to 7 |
| 196036243 | 2 | 3 to 3 | | 2 to 2 |
| 196036244 | 2 | 3 to 2 | | 2 to 2 |
| 196039118 | 2 | 4 to 1 | | 2 to 2 |
| 196039211 | 2 | 4 to 1 | | 2 to 2 |
| 196040020 | 2 | 4 to 1 | | 2 to 2 |
| 196040037 | 2 | 2 to 2 | | 2 to 2 |

The three Bagent lineups now sit one per seven-entry contest (5274842409,
5274843147, 5274846776); the 18:50 ET check-in replaces them if Keenum is
confirmed.

#### Addendum: v3, Keenum assumed to start (Ben's call, 17:40 ET)

Ben: "basically every media outlet is reporting Keenum is expected to start.
Let's make this assumption and update the portfolio as needed." That makes
Bagent a backup, so his three lineups were rebuilt without him. A re-fetch of
the nflverse depth chart at 17:40 ET returned the same 15:17Z snapshot (same
hash), which still ranks Keenum third. The source's own staleness basis says
it is not republished between inactives and lock, and Sleeper is allowlisted
for status only. So Keenum stays unscored and absent: no source can give him
an attempt share before lock.

- Each Bagent row was blanked byte-exactly and refilled by a one-row policy in
  its own thesis, with Bagent excluded and the Captain limited to people not
  already captaining that contest (`K1b` shootout, `K2` CHI upset without
  Hurts, `K3` close game), all at the supplied rung. `K1`'s first result was
  the six-person copy the S3 repair had removed (captain swap), so `K1b`
  excluded Swift as that repair did.
- Then `diversify_showdown_contests.py` ran on the whole file
  (`theses_v2.json`, record `assignment_v3.json`, score 528 to 490).
- **v3:** `DK_REVIEW_ENTRY_phi-chi-sd-v3.csv` `ed120be9…7c90`. QA
  `VERDICT PASS`, 0 defects, 0 limit breaches, max overlap 5, salary 40,500
  to 50,000; the template byte check shows 36 of 121 lines, roster cells only.
  The three seven-entry contests have 7 distinct Captains of 7, worst pairs
  5, 4 and 4. The two-entry pairs share at most 2 people. A 1,500-restart
  search on three seeds reached 486, but each run repeated a Captain
  somewhere and still left one five-person pair, so v3 stands.
- Exposure: Hurts 24, Smith 23, Barkley 22, Santos 21, Loveland 20, Odunze
  20, Monangai 18, Swift 18, Ertz 17, Burden 12, Elliott 10; Bagent 0.

Ben then asked whether Keenum's historical stats could score him. Not on this
engine, for three reasons:

- The prior reads the prior season only, and Keenum has no 2025 row.
- A quarterback's projection is an attempt share, and only the depth-chart
  ordering can move one.
- Writing one from older seasons or media reports would clear the
  current-role gate with research, which `CLAUDE.md` forbids.

The same defect family as Session 48 (a starter the prior gives zero attempt
share); a starter promoted by news with no prior-season row belongs on that
card.

#### Addendum: v4, Keenum rostered by operator direction (17:50 ET)

Ben: "so do we not have Keenum in any lineup???" He had none. Rostering an
unscored player is a construction choice research may inform (the Classic
`swap_inactives.py value-add` mode is the same move); only his number is off
limits. So Keenum was worked in by FLEX swap, with no projection written
(he adds 0 prior points).

- **The swap rule** (`keenum_swap.py`, committed with the slate). It runs
  only on close-game, shootout and CHI-upset rows that hold a CHI pass
  catcher. It removes the lowest-scored FLEX that keeps salary within 50,000,
  and never the Captain, a CHI WR or TE, or Hurts outside the CHI-upset rows.
  Each result must be distinct, share at most five people with every other
  row, and include both teams.
- **9 rows (25%)**, CHI-upset first, then shootout, then close game.
- **The first build failed QA.** Two rows became single-team
  (`SINGLE_TEAM_LINEUP`) when the swap removed the only Eagle from a CHI 5-1.
  The both-teams check was added and the build rerun. The failed file was
  never sent and is kept in the session scratchpad, not in the slate folder.
- `diversify_showdown_contests.py` then re-spread the file (score 415 to
  406, record `assignment_v4.json`).
- **v4:** `DK_REVIEW_ENTRY_phi-chi-sd-v4.csv` `967f0872…c4`. QA
  `VERDICT PASS`, 0 defects, 0 limit breaches, max overlap 5, salary 44,900 to
  50,000; the template byte check shows 36 of 121 lines, roster cells only.
  Every seven-entry contest: 7 distinct Captains of 7, worst pair 4 people.
  Two-entry pairs share at most 3.
- Keenum sits in 196040036 2/7, 196040050 2/7, 196172224 3/7, 196040020 1/2
  and 196040037 1/2.
- Exposure: Hurts 24, Santos 21, Smith 21, Loveland 20, Odunze 20, Monangai
  18, Swift 17, Ertz 17, Barkley 17, Burden 12, Elliott 10, Keenum 9. The Bears
  DST row gave up the DST, so no Bears DST remains.
- **Named limitation:** nine rows carry a quarterback the model cannot
  score, so their prior totals understate them by his whole output. Nothing
  here is an estimate of what he scores.

#### Addendum: inactives checked, v4 stands (19:26 ET)

The 18:51 ET check-in found the official lists not yet indexed; the 19:25 ET
pass found both.

- Eagles inactive: Goedert, Hollywood Brown, Fred Johnson, Tanner McKee,
  Cole Payton, A.J. Epenesa (search summary citing
  [philadelphiaeagles.com](https://www.philadelphiaeagles.com/news/eagles-at-bears-inactives-week-3-2026-nfl-regular-season-monday-night-football-caleb-williams)
  and [SI](https://www.si.com/nfl/eagles/onsi/complete-eagles-inactives-for-week-3-at-bears-training-camp-standout-to-make-season-debut-01m3n09ap15n)).
- Bears inactive: Caleb Williams, Jamree Kromah, Jordan McFadden, Jayden
  Loving, Ozzy Trapilo (the [SI Bears
  page](https://www.si.com/nfl/bears/onsi/bears-eagles-week-3-inactives-monday-night-football)).
  Keenum starts; Bagent is active as the backup.
- None of the 16 people rostered in v4 is inactive (checked by name against
  every row). The five inactive names on the salary file were already
  excluded, so v4 (`967f0872…c4`) stands.

This is research informing construction, not an `official_status_csv`. No
exact-ID activity rows were captured, so `OFFICIAL_STATUS_REQUIRED` stays a
named limitation on every file, and `RELEASE_DECISION` stays
`DO_NOT_UPLOAD`.

### 2026-09-28: Session 23e -- Classic structural bounds and the share cap (C2 v2)

Cloud session, branch `claude/sleepy-hawking-fe4yk4`, task file
`state/tasks/S23e.md`. Classic half of Session 23's card (chunk P2).

#### Added

- **`nfl_classic_portfolio_policy_c2_v2`** (v1 never mutated; still validates and
  normalizes with both controls open). `controls.structural_bounds.salary_left`
  (inclusive range on cap minus roster salary), `.offense_against_own_dst`
  (Boolean, Session 23's "any non-DST person on a rostered DST's team" reading), and
  `controls.max_person_share` (a fraction in (0, 1]; floor of fraction times bound
  entries is the default maximum of every person without an explicit
  `player_exposure_bounds` row, so `0.8` of 25 is 20 and it rides the existing
  player-bound audit). Normalized schema bumps to
  `nfl_classic_portfolio_policy_normalized_c2_v2`. Seven gate codes registered;
  `REGISTRY_SHA256` re-pinned in `tests/test_gate_registry.py` and
  `docs/DATA_CONTRACTS.md` (new § C2 v2).
- **Enforcement as rows, not a filter.** `_Enumerator.enumerate` adds
  `add_salary_band` and `add_no_offense_with_dst` to every stratum's optimizer;
  `expand_validated_neighbors` (single-slot swaps, not solver output) checks the
  bounds directly; a solver roster that breaks one blocks the bank as
  `ILLEGAL_SOLVER_ROSTER`. Measured on the 719-person supplied pool: a solve with
  both rows takes 0.26 s against 0.36 s open, so the bounds do not slow the bank.
- **Audit and review.** `audit_classic_portfolio` and `classic_review` recompute
  both bounds from roster bytes (`CLASSIC_AUDIT_STRUCTURAL_BOUND_VIOLATED`,
  `CLASSIC_C3_STRUCTURAL_BOUND_VIOLATED`) and report `max_person_share`
  (`share_percentage`, `entries`, `people`, `declared_fraction`,
  `declared_maximum_entries`) beside each entry's `structural_bound_violations`;
  the Classic HTML review prints the share line.
- **Ladder** (`relaxation.py`). Rung 0: `salary_left` 0 to 1000,
  `offense_against_own_dst`, share 0.80 (with the existing 0.50 per-person rows).
  Rung 1 drops the salary band, rung 2 the own-DST rule, and the share stays
  through rung 3 (no per-person row there, so it is the cap that binds) and goes
  only with rung 4. `classic_relaxed_controls` keeps "loosest of policy and table"
  per dimension: `salary_left` the wider range, own-DST only while both hold, the
  share the higher fraction (0.50, 0.50, 0.65, 0.80 by rung), and a policy with no
  share keeps none, so a supplied v1 policy gains no cap. A rung-k generator
  policy still relaxes to exactly rung k+1 (the existing parametrized test).
  `make_classic_policy.py` writes v2 on every rung and prints the new lines.
- `tests/test_classic_structural_hygiene.py`, 23 tests: contract (v1 unchanged,
  v2-only controls, eight refusals, round trip, share default with an explicit row
  winning), rows-not-filter with a bounds-open control, fail-closed on an impossible
  band, audit recomputation and share reporting, the rung table's monotone
  loosening, the generator's output, the C3 review's fields, and the supplied
  Classic pool at rung 0 (every proposed roster inside the bounds; a band no roster
  can meet fails closed with `MODEL_INFEASIBLE`).

#### Changed

- `tests/test_relaxation_controller.py::test_a_structural_failure_at_selection_takes_the_next_rung_exactly`:
  the supplied policy now opens `structural_bounds` (edited as its own visible
  change). Its synthetic pool cannot meet rung 0's salary band (about $16,000 left
  per roster), so the bank was `STRUCTURAL_INFEASIBILITY` before the test's
  injected failure and the ladder stepped past rung 1. The test is about the
  bring-back step and still asserts exactly that.
- `docs/RUNBOOK.md` names v2 as an accepted policy schema.

#### Judgment calls

- `offense_against_own_dst` keeps Session 23's same-team reading for Classic
  rather than the 2026-09-15 findings' possible "opposing offense" reading, so
  the name means one thing in both modes. It also forces `RB_DST_PAIR` to zero
  (advisory, harmless). If Ben wants the opposing-offense rule instead, it is a
  new bound, not a change to this one.
- The share stays through rung 3 rather than dropping there as Showdown's does,
  because Classic rungs 0 to 2 carry tighter explicit fractions, so dropping it at
  rung 3 would make the share cap inert at every rung. Table share per rung is
  the explicit fraction where the rung has one, else 0.80.
- `offense_against_own_dst` drops at rung 2 with the bring-back rule, the analogue
  of Session 23 grouping it with the K/DST caps; the pass-catcher band is the
  existing `QB_PASS_CATCHER` rule and Classic has no K or QB-count row.
- Generated documents carry the share as a JSON number; `_materialize` turns it
  into its exact decimal before hashing.

#### Verification

- Card command: `sh ./nfl.sh test tests/test_classic_policy_generator.py tests/test_relaxation_controller.py -x --tb=short` passed.
- Full suite: `1862 passed, 1 skipped in 356.97s (0:05:56)` (the junction test).

#### Found

- A 20-entry rung-0 bank on the real 719-person pool did not finish in 240 s
  (12 candidates), with or without these bounds (single solves are 0.3 to 1.4 s,
  so the time is in the strata's search bound and no-good growth): Session 47's
  finding, unfixed here.
- A default 32-candidate bank cannot satisfy a share cap on even three entries
  (`INCOMPLETE_BANK_EXHAUSTION`): the `player_cap_exclusion` strata need about two
  candidates per capped person. Generated banks are sized in the hundreds; a
  hand-written v2 policy with a share needs a bank to match.
- The DAL@NYG and DEN@KC bytes are still not in the repo; acceptance was proven on the supplied Classic fixture.
- Reviewer pass (fresh context, no blocking items; its own sweep of rung k relaxed to
  k+1 against the generator matched for k = 0..2 at 1 to 150 entries). Two open notes:
  (1) rung 3 now runs a `player_cap_exclusion` stratum per pool person, because the
  share default puts every person's maximum below the entry count; rungs 0 to 2 already
  paid this through their 0.50 and 0.65 rows. The strata are what let a bank satisfy a
  cap at all (a bank without them was `INCOMPLETE_BANK_EXHAUSTION` above), but on a
  full pool at Session 47's measured rate rung 3 may hit its bank limit and fall to
  rung 4, where the baseline still ships. Not timed on the full pool; Session 47's
  calibration is the place to measure it. (2) The normalized schema bump means
  `parse_normalized_classic_policy_bytes` refuses a `..._normalized_c2_v1` file, so
  "v1 unchanged" holds for the source schema only; no committed v1 normalized artifact
  exists and each run writes and reads its own. A hand-written `max_person_share` past
  about 17 significant digits can gain one entry of cap through `float`; it loosens
  only and no generator writes one.

### 2026-09-28: Week 3 slate follow-up -- staged scripts promoted, two engine fixes, a protected-path move

Cloud session, branch `claude/advisor-usage-sohf7n`, working from the
uploaded `NEXT_SESSION_PROMPT.md` (PRs #76 to #79 already on `main`). No
roadmap session number; tracked in `state/tasks/advisor-usage.md`.

#### Added

- **`scripts/filter_pool_scores.py`.** Removes a run's own role-gated
  exclusions from an `NFL_DFS_DUMP_SCORES` dump before it reaches
  `build_classic_portfolio.py`'s pool filter, which keeps anyone scored above
  zero. Prefers the dump's own `excluded_dk_ids` (below) when present; falls
  back, for an older dump, to the run's selection report
  (`offensive_roles.excluded_by_finding` plus `material_role_change_
  exclusions`, mapped to dk_ids through the salary file's own
  `{team}|{position}|{name}` formula), refusing unless the removed count
  equals the report's `excluded_rows`. 11 tests
  (`tests/test_filter_pool_scores.py`).
- **`scripts/swap_inactives.py`.** Four modes on an already-built Classic
  portfolio: `inactive` (single swap ranked by score, then a two-player
  fallback when no single swap is both legal and cap-fitting), `value-add`
  (work a named player into up to `--target-count` lineups), `redeploy`
  (one upgrade per changed lineup, spending cap room a cheaper swap freed),
  and `late-swap` (the `inactive` search, restricted to cells whose game has
  not locked as of `--now`; a locked cell is never touched). Every mode
  shares one legality gate mirroring `build_classic_portfolio.py`'s own
  (shape, cap, games, DST/QB anti-correlation) plus a `preserves_shape` check
  new to this tool: a stack or bring-back the roster already had must survive
  the edit, in every mode, not only construction. 10 tests
  (`tests/test_swap_inactives.py`), including the two-player fallback and the
  late-swap lock boundary.
- **`scripts/build_thesis_portfolio.py`.** Generalizes the staged
  `build_theses.py`: a JSON thesis config (quotas, team-total variants --
  market, a flip-pairs swap, a bust override, a flat number -- per-team score
  multipliers passed through as `role_boosts`, a salary-ranked "priors wrong"
  thesis that fades the `fade_count` most-rostered non-DST players), global
  caps (exposure, overlap, a per-thesis QB cap), seeds. Every
  `build_classic_portfolio.py` call gets a fresh, monotonically-numbered
  `--out` path and its exit code is checked before the file is read -- the
  2026-09-27 stale-read slip named in the staged copy's README, now a
  regression test that fails without the fix
  (`test_a_refused_builder_call_is_never_read_as_a_success`). 16 tests
  (`tests/test_build_thesis_portfolio.py`), including one real subprocess
  call into `build_classic_portfolio.py` and not only an injected fake.
  `scripts/staging/slate_2026_09_27/` deleted; git keeps its history.

#### Changed

- **`selection.write_pool_scores`** (the 2026-09-27 defect: 65 role-gated
  people were still scored above zero in the dump because it was written
  before the run's own exclusion set was computed). The write now happens
  after `excluded` is computed and carries it as a new `excluded_dk_ids`
  field -- the same set `select_prior_lineups` passes to its own objective,
  covering kicker zero-share, official status, offensive role and
  material-role-change findings alike, not only the offensive-role gate.
  Two regression tests, both confirmed to fail against the pre-fix code:
  `tests/test_kicker_roles.py::test_the_scored_pool_export_names_its_own_
  role_gated_exclusions` and
  `tests/test_r28_model_path.py::test_the_pool_scores_dump_names_a_
  material_role_change_exclusion` (the sharper case: a person scored above
  zero on purpose, per the ruling in `prior_score.py`, whose exclusion the
  dump must still name).
- **`scripts/session_probe.py`** ignored `NFL_DFS_TLS_ALLOW_NONSTRICT_CA` and
  reported `github.com`/`raw.githubusercontent.com` as `TLS_FAILED` in this
  container on 2026-09-27 while the same run's `sources.py` fetches
  succeeded on the same hosts. `probe()` now passes the same relaxed
  `ssl.SSLContext` (`VERIFY_X509_STRICT` cleared, nothing else) `urlopen`
  gets when the opt-in is set, mirroring `sources.build_verify_context`
  without importing it (the probe stays standard-library only, so it still
  runs before `setup`). 2 new tests in `tests/test_session_probe.py`.
- **`docs/RUNBOOK.md` § The Classic fallback path** names the full chain in
  order (score dump, filter, slate context, either single-construction or
  thesis build, writer, QA, `swap_inactives.py`), and a fourth "not optional"
  bullet: re-run QA after every `swap_inactives.py` edit.
- **`.claude/rules/slate-operation.md`** adds a rule: a Tier 2 QA failure on
  the engine's own file (a player over 40% of lineups, or stacks under 100%)
  goes straight to `build_thesis_portfolio.py`, no stop to ask.
- **`docs/ROADMAP.md`** adds Sessions 47 to 49 (§2.2, §2.3, §2.8): C2
  bank-rate calibration (this host measured 4.41s per candidate against the
  0.28s default, so a 2000-candidate bank reached 254 and every rung failed
  to C1), a depth-chart QB transfer bug (a starter who arrived from another
  team gets zero attempt share -- Malik Willis, Geno Smith), and the thesis
  builder as rung 4's replacement (the 2026-09-27 fallback file concentrated
  three players in 25 of 25 lineups with zero stacks).
- **Protected-path move.** `.claude/rules/working.md` moved to
  `docs/claude/working.md` (`git mv`, history preserved), loaded every
  session by a new `@docs/claude/working.md` import in `CLAUDE.md`. Confirmed
  first, against `code.claude.com/docs/en/memory.md`: an `@path` import in
  `CLAUDE.md` is expanded and loaded into context at launch, alongside
  `CLAUDE.md` itself, with no extra action needed (up to 4 hops, both
  relative and absolute paths, skipped inside a fenced code block). This
  touches `CLAUDE.md`, so the pull request carries `ben-review`; Ben
  approved the move itself in the request that asked for it. Every
  gate-registry and boundary-test citation of the old path checked and
  resolving (`tests/test_repo_boundaries.py`, `tests/test_gate_registry.py`,
  `tests/test_harness_orientation.py`, all green); `scripts/repo_state.py`'s
  own docstring pointer updated.

#### Verification

`1839 passed, 1 skipped in 359.24s (0:05:59)` (full suite, Linux;
`scripts/record_verify.py`). `sh ./nfl.sh doctor` `pass_status: true`;
`git diff --check` clean; `python3 scripts/check_protected_paths.py` run
again after commit, before push. Both `write_pool_scores` regression tests
and the `build_thesis_portfolio.py` stale-read regression test independently
confirmed to fail against the pre-fix code, not only pass against the fix.

#### Found, not fixed

- **[BEN: which file did you actually upload for the Week 3 slate, v6 (salary
  redeploy) or v7 (the Flowers swap)?]** See the addendum to the 2026-09-27
  slate entry above; neither hash was recorded at the time.
- `filter_pool_scores.py`'s fallback-path invariant (removed count must equal
  the report's `excluded_rows`) only holds when the run has no kicker,
  official-status or portfolio-policy exclusion alongside the offensive-role
  gate; it refuses rather than guess when it does not, which is correct but
  means an operator on such a run needs a dump already carrying
  `excluded_dk_ids` (every run since this session) rather than the fallback.
- Sessions 47 to 49 are proposals with acceptance criteria, not implemented
  fixes; C2 bank-rate calibration in particular is flagged in its own card as
  probably under-ranked given its measured effect on this host.

### 2026-09-27: research allowed, procedure split out of CLAUDE.md (Ben's ruling)

Ben, 2026-09-27, after a live slate where the retrieval boundary stopped an
inactives search: "relax the self modification rules ... You need to have
flexibility to get better, you search, be creative, etc. and I want to have
some element of recursive self-improvement." He asked for this pull request and
approved it in the session; it touches `CLAUDE.md`, so it carries `ben-review`.

#### Changed

- **Research clause** (`CLAUDE.md` permanent boundaries, mirrored in
  `docs/START_HERE.md` item 8). "Automated retrieval obeys
  `src/nfl_dfs/sources.py`" stays, and still binds every model input. Research
  (news, inactives, forecasts) may now use Claude Code's own web tools, never
  on a host `sources.py` prohibits (nfl.com and DraftKings stay off-limits, per
  `plan.md`); it informs exclusions and construction, never a number or a gate.
- **Procedure moved out of the protected file.** `CLAUDE.md`'s "Developing in
  Claude Code" section (commands, session protocol, token discipline, repo
  etiquette) moved verbatim to `.claude/rules/working.md`, which loads every
  session and which Claude may change and merge on green. Two lines changed
  wording to fit the new home. The versioned-contract bullet stayed in
  `CLAUDE.md` under Release truths, because `config/gate_registry_v1.json`
  cites its "`OPTIMAL` is scoped to the reported bank" as a boundary.
- **Getting better** (new `CLAUDE.md` section): Claude owns every procedure,
  rule, skill, script, test and doc outside the permanent boundaries, release
  truths and lock-clock bounds; a procedural rule that blocks a clearly better
  result outside those bounds is fixed, not obeyed into a corner; every slate or
  session ends with the change that would have made it better. The boundaries
  themselves still need `ben-review`. `scripts/repo_state.py`'s docstring
  pointer to "Token discipline" follows the move.

The protected list is unchanged (`CLAUDE.md`, `.github/protected-paths.txt`,
`.claude/settings.json`). `CLAUDE.md` is 154 lines, down from 199.

### 2026-09-27 (slate run): Week 3 main slate Classic, 25 entries, prior-only review

Cloud session, branch `claude/week-three-classic-lineups-fzggt8`.
`RELEASE_DECISION=DO_NOT_UPLOAD` and `MODEL_STATUS=PRIOR_ONLY` throughout; no
evidence gate was relaxed and no observation was invented. 13 games, 671
people, 25 blank reserved entries across 17 contests; lock 13:00 ET (earliest
kickoff), delivery deadline 12:55 ET (R31).

Inputs, committed under `data/inbox/slates/wk3-classic-2026-09-27/`:

    salary  9085e030800d78f4d3588f71134e3990e7141b2ec59b1f772f5972c5503ad2e8
    entries 582b502c9e4bdf25c53a50a22d0367e0c968bfd44bca1ae182313707192865f3

Running order and what each step returned:

- `session_probe.py` exit 2: `api.weather.gov`, `api.sleeper.app` and
  `api.the-odds-api.com` are `EGRESS_BLOCKED` at the organization proxy. The
  nine outdoor games ran `WEATHER_UNOBSERVED`; BAL@DAL and HOU@IND resolved
  `ROOF_CLOSED` from venue history, LV@NO and NYJ@DET `INDOOR`.
- QB depth package from nflverse `depth_charts_2026.csv` through
  `sources.py` (`NFL_DFS_TLS_ALLOW_NONSTRICT_CA=1`; the proxy CA fails
  `VERIFY_X509_STRICT`), observed 2026-09-27T12:56:55Z, package
  `b63dafc4...21d3`.
- Run `20260927T145947Z-wk3-classic`: baseline published first
  (`3dc1eb28...3d51`, 25 rows), then `PRIOR_REVIEW_IDENTITY_BLOCKED` on seven
  available people. Six are spelling variants and one a stale team row, each a
  unique name, team and position match in the captured
  `roster_weekly_2026.csv`: Matt/Matthew Hibner `00-0040879`, Joshua/Josh
  Palmer `00-0036988` (as on 2026-09-17), Mitch/Mitchell Tinsley
  `00-0038839`, Drew/Andrew Ogletree `00-0037292`, Audric Estime/Estimé
  `00-0039373`, Nick/Nicholas Singleton `00-0040886`, and Ihmir
  Smith-Marsette `00-0036635` (ARI in week 2; `players.csv` still says CAR).
  Resolved through the reviewed-crosswalk path, `DECISION=ACCEPT` with
  `REVIEWED_PROVIDER_PLAYER_ID` (`identity_reviewed_wk3.csv`,
  `85318fbd...0a9b`, committed with the inputs), then `priors-freeze`.
- Run `20260927T150249Z-wk3-classic-r2`, frozen package plus the rung-0 C2
  policy (bank 2000, QB pass-catcher HARD 25/25, bring-back HARD 18/25,
  overlap 5, exposure 13). The ladder walked every rung: attempt 0
  `CANDIDATE_BANK_TIMEOUT` at 254 of 2000 candidates in 1120 s, then
  `INCOMPLETE_BANK_EXHAUSTION` on a 54-candidate bank at the supplied rung and
  rungs 1 to 3 (49 at rung 3), then rung 4. Ten `RELAXATION_*` records. It
  delivered C1's export, `cd2a6005...f17d`, 39 minutes into the run.
- The C1 file is legal and was not good enough: QA Tier 1 PASS, Tier 2
  De'Von Achane, Jaxon Smith-Njigba and Harold Fannin Jr. in 25 of 25, 27
  distinct players, QB pass-catcher 0 of 25, bring-back 0 of 25, four
  DST-against-own-skill lineups.
- Fallback path (RUNBOOK § The Classic fallback path). A separate C1 run
  (`20260927T152540Z-wk3-c1`, same frozen package, 19.5 s) dumped the pool
  scores; 65 role-gated people were still scored above zero, so every person
  in the run's exclusion report was removed (351, equal to `excluded_rows`),
  leaving 317 positive. `make_slate_context.py` derived implied totals from
  the frozen nfldata `games.csv`. `build_classic_portfolio.py` with
  `--max-exposure 10 --max-overlap 5 --require-bringback --min-salary 48500`
  built 25 of 25 with no ratchet step; `write_dk_entries.py` filled 25 rows,
  0 bytes changed outside the roster cells, `ae7690b1...11cd`.
- `qa_classic_portfolio.py --template --export --backup-pairs` (25 pairs from
  the depth chart; WAS left out because Jayden Daniels is DraftKings `OUT`)
  Tier 1 PASS with those limits enforced. Tier 2: max exposure 10 of 25
  (Christian McCaffrey), top-3 union 17 of 25, 103 distinct players, overlap
  max 4 and mean 0.83, anti-correlation 0, QB pass-catcher 25 of 25,
  bring-back 25 of 25, mean implied total of skill slots 24.37, salary 48,500
  to 50,000. Twelve QBs across nine games; Josh Allen 5, LAC@BUF 6.

Named gaps in the delivered file, none cleared: no official activity file
(`OFFICIAL_STATUS_REQUIRED`); four DraftKings `Q` players selected (Zay
Flowers 4, Jaylen Warren 3, Keon Coleman 1, Michael Pittman Jr. 1); nine
games `WEATHER_UNOBSERVED`; every selected skill player rests on a
prior-season role; no ownership input, so no leverage model; no payout, prize
value or field size, and contest names were not read for any of them.

Found, not fixed (slate session, no code change):

- The in-run session probe reports `github.com` and
  `raw.githubusercontent.com` as `TLS_FAILED` in this container because it
  does not honor `NFL_DFS_TLS_ALLOW_NONSTRICT_CA`; the same run's nflverse
  fetches succeeded. A system `python3` probe run by hand reported both
  reachable.
- This host measured 4.41 s per Classic candidate against the 0.28 s default
  that sized the rung-0 bank, so the bank reached 13% of its size and every
  re-sized bank was too small for the policy.
- The depth-chart rule gives the rank-1 QB only the attempt share his team's
  current QBs already held, so a starter who arrived from another team stays
  gated as a material role change: Malik Willis (MIA) and Geno Smith (NYJ)
  were unselectable with the package supplied. Deshaun Watson (CLE) was
  excluded as missing history.

Superseded before lock by two instructions from Ben (the 25-row file above was
never the final handoff):

- **Leave out `NFL FREE 200-Player` (contest 196114372, Entry 5272123785).**
  Rebuilt at 24 with the same limits (exposure 9 of 24);
  `DK_REVIEW_ENTRY_wk3_fallback_24.csv`, `9fc6a8b9...4c77`. That row is left
  blank on purpose, so the writer and QA exit 3 naming it; nothing else is
  unfilled.
- **Odds and a nor'easter.** Ben supplied an ESPN page of DraftKings lines as a
  PDF (`6b7ad115...e692`; its text layer carries only the open column, the
  current columns were read from a render). Current totals and spreads equal
  the frozen nfldata lines except KC -10 and CAR -2.5, so implied totals moved
  by a quarter point at most. The open-to-current moves locate the weather:
  TEN@NYG 45.5 to 37.5, SEA@WAS 46.5 to 40.5, CIN@PIT 47.5 to 42.5, while
  LAC@BUF rose 2 and NE@JAX 1; part of the first two is QB news (Jaxson Dart
  IR, Jayden Daniels OUT). The NOAA WPC discussion Ben linked was not fetched:
  `wpc.ncep.noaa.gov` is not in `sources.py`'s allowlist. No weather state was
  written anywhere; every outdoor game stays `WEATHER_UNOBSERVED`.
- **Final file: five theses, 24 lineups**, built by calling
  `build_classic_portfolio.py` per thesis (three seeds each) on the gated
  scores and selecting across all candidates under one cap set: exposure 7 of
  24, overlap 5, unique rosters, at most two lineups per QB within a thesis.
  Core with a storm tilt (8: TEN/NYG/SEA/WAS QB and pass catchers x0.80, RB
  x1.05, DST x1.15; CIN/PIT passing x0.92), storm-proof indoor stacks with a
  storm-team DST (4), storm-bust stacks in the storm games (4), underdog flip
  with swapped totals for LAC, ARI, NE and PIT (4), and priors-wrong ranked on
  DraftKings salary with flat totals and the 12 most-used players faded (4).
  The multipliers and swapped totals are construction choices, not model
  values; no engine score or exclusion changed.
  `DK_REVIEW_ENTRY_wk3_theses_24_v4.csv`, `7ddac0e2...9d95`, 0 bytes changed
  outside the roster cells. QA with `--max-exposure 7 --max-overlap 5
  --min-salary 48500 --backup-pairs`: Tier 1 no validity failure and no limit
  exceeded, the one intended blank row. Tier 2: max exposure 7 of 24 (Henry,
  Achane, Pickens, Gibbs, McCaffrey), top-3 union 16 of 24, 102 distinct
  players, overlap max 5 and mean 0.89, anti-correlation 0, QB pass-catcher
  and bring-back 24 of 24, 15 QBs across 10 games. `Q` players: Zay Flowers 2,
  Jaylen Warren 2.
- One construction slip, caught before handoff: `build_classic_portfolio.py`
  refuses an existing `--out`, and the selection script read the earlier file
  when it did, so two re-runs silently reused the first candidates. The final
  run used fresh paths and checks the builder's exit code.

**Addendum, 2026-09-27b** (a later cloud session, no new engine run;
construction-only edits to the v4 file above, applied with the staging
scripts this session promoted to `scripts/filter_pool_scores.py`,
`scripts/swap_inactives.py` and `scripts/build_thesis_portfolio.py`):

- **v5: value adds.** Isaiah Williams, Hutchinson and Boutte worked into the
  portfolio as named value adds, from an inactive report Ben pasted into the
  session. Construction only; no engine score or exclusion changed.
- **v6: salary redeploy.** One upgrade per lineup the inactive swaps had
  already changed, spending the cap room a cheaper replacement freed.
- **v7: the Flowers swap.** Zay Flowers was DraftKings-active but limited to
  about 20 to 30 plays; swapped for Bateman plus Ferguson in Entry
  `5268345867` and for Olave in Entry `5272530124`.
- **Research rule in use.** Web search for inactives (CLAUDE.md's 2026-09-27
  research clause, above), never `nfl.com` or DraftKings; findings informed
  construction only, never a score or a gate.

[BEN: which file did you actually upload for this slate, v6 (salary
redeploy) or v7 (the Flowers swap)? The session that built v5 through v7 ran
them as scratch edits under `/tmp`, never committed a hash for either, and
nothing else in the repo's artifacts settles it. Flagged here rather than
guessed.]

### 2026-09-27: structural hygiene and the share cap, Showdown half (Session 23)

Branch `claude/s23-structural-hygiene-izyvah`. Chunk P2; standings findings
§5.4, §7, §8.1 C, §8.2 H/I; code review S7; R33, R34. No release truth moved:
every path still ends `PRIOR_ONLY / DO_NOT_UPLOAD`. Classic's half of the
card is split to **Session 23e** at the card's own named seam ("the seam is
Showdown first, Classic bounds second"); Showdown alone reached about 1,120
changed lines, near the card's 900-line estimate for the whole thing.

#### Changed

- **Showdown portfolio policy v2** (`nfl_showdown_portfolio_policy_v2`,
  `portfolio_policy.py`). `v1` is never mutated and still validates exactly
  as before. A new optional `controls.structural_bounds`: `qb_count`,
  `pass_catchers_with_rostered_qb` and `salary_left` as inclusive integer
  ranges; `kicker_count` and `dst_count` as nullable integer maxima;
  `offense_against_own_dst` as a Boolean (forbids any non-DST person sharing
  a rostered DST's team, which also covers a DST on the rostered QB's team).
  Omitted on v2, or absent because the source is v1, means fully open —
  identical to v1 behaviour. `structural_bound_violations()` recomputes any
  of them from exact roster DraftKings IDs.
- **Every bound is a real MILP row, not a post-solve filter.** First attempt
  post-filtered: reject a violating roster from `_StratifiedEnumerator`,
  no-good it, resolve. Measured on the small synthetic pool
  (`tests/test_participation.py`), a captain-seeded stratum forced to a DST
  captain under `qb_count`+`kicker_count`+`offense_against_own_dst` timed out
  at 30s with 0 candidates (a forced DST captain leaves almost no same-team
  slack, and an unconstrained "next best" solve rarely lands in that narrow
  feasible region by chance). Replaced with real constraints on
  `LineupOptimizer` (`optimizer.py`): `qb_count`/`kicker_count`/`dst_count`
  via the existing `add_selected_count_bounds`; `salary_left` via a new
  `add_salary_band`; `pass_catchers_with_rostered_qb` via the existing
  `add_classic_qb_correlation_bounds(kind="PASS_CATCHER")` — its
  Classic-only restriction dropped, since the math never depended on Classic
  structure and only one call site exists; `offense_against_own_dst` via a
  new `add_no_offense_with_dst` (pairwise "not both" rows, one DST row
  against every other same-team row). Same scenario: 0.09s, 10/10 candidates,
  zero violations.
- **SD4's independent audit recomputes every bound from the exact assigned
  roster IDs** (`portfolio_enforcement.py`, `PORTFOLIO_AUDIT_STRUCTURAL_
  BOUND_VIOLATED`), never trusting the selector, and reports `max_person_
  share` — not a new field, it is `max_combined_person_exposure.default_
  fraction`, which already existed and already does exactly this job (share
  of entries containing one underlying person, CPT or FLEX) — with the
  denominator and the person(s) named.
- **Review S7: a real default Captain cap and a captain-spread column.**
  `scripts/make_showdown_policy.py --captain-default` now defaults to 0.4
  instead of requiring an explicit value on every call (an unbounded default
  let the captain strata and the summed-points objective put every entry
  under one Captain). `readable_review.py`'s `exposure` section gets
  `captain_spread` and `max_person_share` (distinct-person count, per-person
  counts, the max share and who holds it), in both the JSON and the rendered
  HTML.
- **Relaxation ladder** (`relaxation.py`, `SHOWDOWN_RUNGS`). The brief's
  relaxable order (salary band, pass-catcher band, K/DST caps, QB count,
  `max_person_share`) is folded into the existing 3-rung Showdown ladder
  rather than adding rungs: rung 1 additionally drops the salary band; rung 2
  additionally drops the pass-catcher band, the K/DST caps and
  `offense_against_own_dst` (not named in the brief's 5-item order; grouped
  here with the K/DST caps it sits next to — a session judgment call); rung 3
  additionally drops the QB-count band. `max_person_share` already drops at
  rung 3 through the pre-existing `uncapped` combined-exposure mechanism,
  which matches its place last in the brief's order with no new mechanism
  needed.
- **Generator defaults** (`scripts/make_showdown_policy.py`, v2): one QB, one
  to two pass catchers with him, $1 to $500 left, at most one kicker and one
  DST, `offense_against_own_dst=true`. Kickers and DSTs stay in the combined
  pool by default (`--captain-zero-pos K,DST` only zeroes their Captain
  fraction, decided and recorded here rather than excluding them: they were
  in 45%/68% and 68%/82% of the top 1% in the graded games).
  `--combined-default` (this generator's name for `max_person_share`)
  defaults to 0.80, the field median.
- **Five new gate codes**, alphabetical:
  `PORTFOLIO_AUDIT_STRUCTURAL_BOUND_VIOLATED` (class `S`,
  `portfolio_bounds`, a runtime bound breach, same family as the existing
  cap-exceeded audit codes); `PORTFOLIO_POLICY_STRUCTURAL_BOUND_
  {CONTRADICTORY, INTEGER_REQUIRED, OUT_OF_RANGE, TYPE_INVALID}` (class `P`,
  `showdown_policy_input`, malformed-input shape, same family as every other
  policy-shape code). `config/gate_registry_v1.json` and its SHA-256 re-pin
  in `tests/test_gate_registry.py`/`docs/DATA_CONTRACTS.md`.
- **Roadmap.** Session 23's row narrowed to the Showdown half and marked
  Complete; new **Session 23e** row for the Classic half, depending on
  Session 23; Session 39's dependency re-pointed from Session 23 to Session
  23e (it needs the Classic ladder ordering, which only 23e settles).
- **`[BEN: ...]`.** The card's own DAL@NYG and DEN@KC fixtures are not in the
  repo, only their hashes (`docs/RUN_RECORD_20260914_DEN_KC.md`). Flag added
  to the Session 23 card asking for both slates' DKSalaries and DKEntries
  bytes.

#### Verification

New tests: `tests/test_portfolio_policy.py` (v2 validate/normalize, v1
refuses `structural_bounds`, a contradictory bound refused, bound violations
recomputed from roster bytes on the synthetic pool),
`tests/test_portfolio_enforcement.py` (bank generation never proposes a
violating candidate, the audit catches a hand-forced violation the selector
never reported), `tests/test_relaxation_controller.py` (the ladder drops the
new bounds in the brief's order across rungs 1 to 3),
`tests/test_lineups_optimizer.py` (the three new/generalized `LineupOptimizer`
methods directly), and a new
`tests/test_showdown_structural_hygiene_acceptance.py` proving the card's
acceptance end to end on the two Showdown fixtures the repo has: NE@SEA
(`tests/fixtures/supplied/`) and DET@BUF
(`data/inbox/slates/det-buf-2026-09-17/`) — `max_person_share` ≤ 0.80, 100%
hygiene pass at rung 0, kickers and DSTs reach the candidate bank, more than
one captain, and an infeasible bound (three rostered QBs on a two-team pool)
fails closed rather than delivering an illegal portfolio.

Focused command
(`sh ./nfl.sh test tests/test_portfolio_policy.py tests/test_classic_policy_
generator.py tests/test_portfolio_enforcement.py tests/test_relaxation_
controller.py -x --tb=short`) green, then the full suite:
`1797 passed, 1 skipped in 374.79s (0:06:14)`. A first full run, before this
close-out's own §1 rewrite, caught two bugs of its own: the card's insertion
of Session 23e's card accidentally deleted the `#### Session 21` heading
(`test_every_session_has_a_card`), and §1 still named Session 23
(`test_the_quick_start_names_the_first_startable_session`, expected while the
row was `In Progress`, but this session closed 23 out in the same commit as
adding 23e, so it needed a real fix, not just the known mismatch); both fixed
and reverified above. Rerun clean after the reviewer's fix (the two new
`test_readable_review.py` assertions/test above):
`1798 passed, 1 skipped in 378.56s (0:06:18)`.

`sh ./nfl.sh doctor`, `git diff --check` and
`python3 scripts/check_protected_paths.py` are clean; no protected path
touched.

The `reviewer` subagent read the diff against the card (its snapshot predated
the suite-line fix above, which it flagged as still a placeholder; already
fixed by the time its report landed). It found one real blocking gap, fixed:
review S7's new `exposure.captain_spread`/`exposure.max_person_share`
(`readable_review.py`) had no test — added a direct unit test of
`_spread_summary` (ties, zero denominator) and extended the existing
Showdown readable-review integration test to cross-check both fields against
the same run's already-verified per-person exposure rows, plus an HTML-text
assertion. Two open, non-blocking findings recorded in `docs/DATA_CONTRACTS.md`
rather than changed: `offense_against_own_dst`'s "own team" reading (matches
the pre-existing `DST_WITH_OWN_OFFENSE` QA observation this bound promotes,
not a new interpretation, but worth Ben's eyes given the 5-1 split it forces
whenever a DST is rostered), and the generator defaults' salary/QB-count
figures following the Session 23 card's own restated numbers over the P2
brief's older text (the brief's two-QB-quota mechanism is a portfolio-level
allotment, not implemented here — different from the per-lineup bounds this
session built, and a natural fit for Session 23b/23c's thesis machinery
instead).

### 2026-09-27: run-path integrity (Session 38)

Branch `claude/s38-run-path-integrity`. The 2026-09-25 code review's V3 to V8.
No release truth moved: every path still ends `PRIOR_ONLY / DO_NOT_UPLOAD`.

#### Changed

- **A workbook lock after certification no longer deletes the certified file
  (V3).** `command_certify` resolves `run_id` once and reuses it in its
  except branch, instead of calling `_resolved_run_id` again with
  `args.run_id` still `None` and getting a fresh timestamp. A new
  `_certified_and_intact(manifest_path, output_path)` helper (reusing
  `historical_artifact_integrity`, the same check `audit` and `status` run)
  gates both that except branch's `upload_path.unlink` and
  `command_cowork_run`'s except-handler sweep of `DK_UPLOAD_*.csv`: a file
  whose manifest still says `CERTIFIED_UPLOAD_PACKAGE` with a matching hash
  is left alone and named in the diagnostic (`certified_upload_preserved`,
  `preserved_uploads`); anything else is still removed as before.
- **`nfl.ps1` accepts `baseline` (V4).** Its `ValidateSet` omitted it, so
  `.\nfl.ps1 baseline`, the runbook's documented hand-run fallback, was
  refused by PowerShell before Python ran. `tests/test_repo_boundaries.py`
  gained a permanent regression test that statically diffs the `ValidateSet`
  against `build_parser()`'s real subcommands, so this cannot drift silently
  again.
- **A second `run-slate` into an existing `outputs/<run_id>` is refused (V5).**
  `output_root.mkdir(parents=True, exist_ok=True)` let a retry after a
  removed `data/runs/<run_id>` silently reuse an earlier run's output
  folder, overwriting its `cowork_run.json`. The collision check now covers
  both directories together, before `args._resolved_cowork_run_id` is
  stashed (so the exception handler cannot still write into the folder the
  check just refused to reuse), and the `mkdir` no longer takes
  `exist_ok=True`.
- **`status` re-derives through historical artifact integrity, like `audit`
  (V6).** It used to print the manifest's stored truths as current with no
  file or hash check at all, and exit 0 on a stored `CERTIFIED` regardless.
  R09 fixed this pattern in `audit`; `status` kept the old shape. It now
  routes through the same `historical_artifact_integrity` call, labels its
  fields as stored, pins `RELEASE_DECISION=DO_NOT_UPLOAD`, and exits 0 only
  when `ARTIFACT_INTEGRITY=PASS`.
- **`prior_review`'s exception exit reports `MODEL_STATUS=PRIOR_ONLY` (V8).**
  Every normal exit already pinned it; the exception exit fell back to the
  blanket `UNVALIDATED` because the resolved profile lived on a local inside
  `_command_cowork_run`, invisible to the outer handler. `snapshotted.profile`
  is now stashed onto `args._cowork_resolved_profile`, mirroring
  `_resolved_cowork_run_id`, and threaded through `_handler_release_truths`
  and both `_blocked_truth_values()` calls in the exception handler.
- **`certify_upload` and `command_validate` take the plan's fillable rows,
  not every reserved entry (V7, the card's seam).** Before this, any
  prefilled row made certification fail closed but unusable: leaving it out
  of `assignments` failed here (`ENTRY_AUTHORIZATION_MISMATCH`), and
  including it failed inside `write_upload_bytes`
  (`ENTRY_BLANK_CELL_AUTHORITY_REQUIRED`) instead. Both now compute
  `plan_entries(template, slate)` and use `set(plan.fillable)` as the
  authorized set, as `review_export.py` already does, so a template an
  operator partly filled by hand can certify or validate its remaining blank
  rows. Both also refuse a fillable row that repeats a prefilled row's
  already-resolved roster (R29, `ENTRY_PREFILLED_LINEUP_REPEATED`), checked
  against `plan.forbidden_keys`. `certify_upload`'s reparse-consistency check
  (`FINAL_REPARSE_ASSIGNMENT_MISMATCH`) is narrowed to compare only the
  assigned rows, since a prefilled row is no longer in `assignments` at all
  (`review_export.py`'s own reparse check already does this).
- Total diff about 570 changed lines, comfortably under the card's
  1,500-line split point; V7 shipped in this session rather than a 38b
  split.

#### Verification

Per finding: wrote the test first, confirmed it fails against the pre-fix
code in a scratch `git worktree` at the claim commit
(`PYTHONPATH=<worktree>/src`, the working tree's own venv), then implemented
the fix and confirmed the test passes. New or extended coverage:
`tests/test_cowork.py`, `tests/test_certification.py`,
`tests/test_artifact_preservation.py`, `tests/test_repo_boundaries.py`. Full
suite (with the row still `In Progress`): `1783 passed, 1 skipped in 388.68s`,
apart from the one expected `test_the_quick_start_names_the_first_startable_session`
mismatch, which clears once the row and Quick-Start are rewritten below.
Rerun clean after this close-out's own edits and the reviewer's fix (next
paragraph): `1784 passed, 1 skipped in 394.54s (0:06:34)`. The
`reviewer` subagent found no blocking gaps; it caught one real slip this
session made on its own (an unrelated pre-existing assertion in
`test_manifest_audit_rederives_do_not_upload_after_output_tamper` displaced
and then dropped while inserting a new test nearby), restored before this
close-out. `sh ./nfl.sh doctor`, `git diff --check` and
`python3 scripts/check_protected_paths.py` are clean; no protected path
touched.

### 2026-09-26: Showdown file integrity (Session 37)

Branch `claude/eager-ramanujan-5ylyix`. The 2026-09-25 code review's V1, V2,
V9, V10, V11 and E12. No release truth moved: every path still ends
`PRIOR_ONLY / DO_NOT_UPLOAD`.

#### Changed

- **A Showdown policy can no longer switch off distinct lineups (V1, R29).**
  `portfolio_policy.py` refuses `require_unique_lineups: false` as
  `PORTFOLIO_POLICY_UNIQUENESS_REQUIRED`, as Classic's validator already did.
  In `portfolio_enforcement.py` the joint solve's count bound is 1 on every
  candidate (`repetition_allowed` is gone), the one-per-canonical-lineup rows
  are unconditional, and the independent audit's
  `PORTFOLIO_AUDIT_CANONICAL_DUPLICATE` check no longer reads the flag. A
  normalized policy stored before this session that says `false` still loads,
  and its duplicates are still named. The new code is registered as
  `showdown_policy_input` in `config/gate_registry_v1.json`, re-pinned at
  `6a528c7809145fe2b6d3fb556dfcbc38e2642920bd99aada9014ae5f8d5e2cad` in `tests/test_gate_registry.py` and
  `docs/DATA_CONTRACTS.md`. The contract's two sentences on the flag say it is
  refused. Treated as a validation tightening inside
  `nfl_showdown_portfolio_policy_v1`, not a schema change: the field and its
  type are unchanged, and Classic's policy v1 already refused `false`. A
  `run-slate` given such a policy drops it by name (`showdown_policy_input` is
  class P, stops certification only) and the baseline still ships.
- **`scripts/qa_showdown_portfolio.py` audits bytes and exempts only blank rows
  (V2, V11).** It now mirrors `qa_classic_portfolio.py`: raw lines through
  `nfl_dfs.byte_lines`; only a row whose six roster cells are blank in the
  template may change, and only inside them. An export that overwrote a
  prefilled row, which printed `PASS` before, fails with
  `LINE_n_BYTES_CHANGED on prefilled entry`. A prefilled row still counts for
  R29 duplicates. People are the salary row's `team|position|name` for the DK
  ID, never a bare `Name`; a lineup is its Captain ID and sorted FLEX IDs;
  `--backup-pairs` takes an ID or a name. Exit codes are Classic's: 1 validity,
  3 a sanctioned unfilled blank row (each named in `unfilled_entry_ids`), 2
  only the operator's `--max-overlap` and `--backup-pairs` (now under
  `LIMIT_BREACHES`), 0 otherwise. This closes Session 02b's open item.
- **Showdown's entry file is held to intake's bytes (V9).** `prior_review.py`
  no longer re-parses the entries file before SELECT; the intake parse is the
  one the plan, pointer and export use. `ENTRY_INPUT_CHANGED_BEFORE_SELECTION`
  now applies in both modes, not Classic alone.
- **C3 packaging names any failure (V10).** The handler around
  `create_classic_review_package` catches `Exception`, so a `KeyError` or
  `TypeError` writes `prior_review.json` with `FAILED_C3_DOWNSTREAM_AUDIT` and
  `CLASSIC_C3_REVIEW_EXPORT_FAILED:<type>:<message>` instead of escaping.
- **The referee names a line with no CSV record (E12).** Both byte audits in
  `referee.py` parse through `_first_record`; a changed line that decodes to
  nothing (a lone byte-order mark) is
  `line N: empty physical line holds no CSV record`, not `StopIteration`. The
  pre-lock audit now also names a `csv.Error` or decode error as the late-swap
  audit did.

#### Tests

Edited expectations, named here because a ruling-level change moved them:
`tests/test_qa_showdown_portfolio.py`'s validity cases read exit 1 and verdict
`FAIL` (exit 2 and `DEFECT` before); `_blank_cell`, `_contest_cell_changed` and
`_row_dropped` read `PARTIALLY_FILLED_ROW`, `LINE_2_BYTES_CHANGED_OUTSIDE_ROSTER`
and `LINE_COUNT_CHANGED`, the byte audit's names; the overlap and backup-pair
test now pins exit 2 apart from validity. `tests/test_portfolio_enforcement.py`'s
`_audit` helper defaults to `require_unique_lineups: true`. Each still fails
what it failed before.

New: the Showdown refusal by name; the audit naming a duplicate under a stored
`false`; the joint solve never repeating a lineup under a waived policy; eight
QA cases (prefilled overwrite fails, untouched prefilled passes and counts for
R29, a sanctioned blank row exits 3, an export identical to the template fails,
a changed line ending fails, identity by ID, a backup pair by ID, validity
outranks a limit); a Showdown run whose entry file changes before SELECT stops
by name; a C3 `KeyError` keeps the stage record; the referee's empty line.
Every new or edited case was run against the pre-session code in a scratch
worktree: all 27 failed there.

#### Verification

- Card command: `sh ./nfl.sh test tests/test_portfolio_policy.py tests/test_portfolio_enforcement.py tests/test_qa_showdown_portfolio.py tests/test_prior_review_profile.py -x --tb=short`: `165 passed in 51.66s`.
- Full suite: `1776 passed, 1 skipped in 493.37s (0:08:13)` on Linux (1,762 before; the one skip is the junction test).
- `sh ./nfl.sh doctor`, `git diff --check`, `python3 scripts/check_protected_paths.py`: doctor `pass_status: true`; diff check clean; `No protected path touched`.

#### Found

- The salary-hash stop before SELECT (`SALARY_INPUT_CHANGED_BEFORE_SELECTION`)
  is still Classic-only; a Showdown run with no policy has no salary stop at
  SELECT (the policy path has its own). The card names only the entry stop.
- The policy path's `PORTFOLIO_POLICY_ENTRY_BYTES_CHANGED_BEFORE_SELECTION`
  is now shadowed by the general entry stop, which runs first on the same
  condition. Left in place as a registered, still-emitted code.

### 2026-09-25: full code review and one consolidated, money-ranked board

Ben's instruction: review the code, review every plan, backlog and fragment,
consolidate them into one backlog in chunks a single session finishes before a
compaction, and rank each chunk by what wins large amounts of money, with
dependencies respected. `docs/ROADMAP.md` stays the one queue (its 2026-09-22
charter and `backlog.md`'s stub test both say so); this entry records what
changed in it. No engine code changed. Every path still ends
`PRIOR_ONLY / DO_NOT_UPLOAD`.

#### Added

- **`docs/critiques/Code_Review_2026-09-25.md`**: five read-only review passes
  over `src/`, `scripts/`, the hooks, the launchers and the workflows at
  `bedf6a3`, partitioned by module and each verified against the code path it
  names, with the highest findings confirmed a second time in this session.
  No BLOCKER: every writer of a DraftKings entry file goes through the
  exact-byte writer, the byte audit, a reparse and R29 distinctness. Findings
  by class: 14 that can cost a file or an entry fee (a Showdown policy may
  switch off distinctness and the duplicate reaches the CSV; the Showdown QA
  passes an export that overwrote a prefilled row; a certified upload is
  deleted when the workbook throws after certification; `nfl.ps1` refuses
  `baseline`; late swap's clock is `--as-of` alone), 10 that change which
  lineups get built (the Session 21 unit mismatch confirmed at
  `priors.py:1541-1565` against `:1661-1680`; no Classic overlap cap at
  `selection.py:701-703`; the C2 witness chain is QB-swap clones), 10 in the
  simulator that must land before it becomes the operating bank (sacks
  counted as attempts, a zero group becoming uniform, market lines never read,
  no registered versions), 12 in evidence and retrieval (the weather script
  bypasses the allowlist and re-serialises its capture), 9 in the review
  chain (a 2,090-line orchestrator and three copies of the truths), 6 in the
  harness (a rename evades the protected-path check; the guard misses
  `git -C`, a quoted `main`, `commit -a`, `restore`), plus dead code and
  test gaps. `config/scoring.json` matches DraftKings scoring line by line;
  `AvgPointsPerGame` is confined; nothing labels a prior EV.
- **Ten new sessions, 37 to 46**, and eight split rows (15b, 18b, 23c, 23d,
  24b, 24c, 25b, 44b), each with a card that states its files, its
  changed-line estimate and what it must read. Session 37 (Showdown file
  integrity) and 38 (run-path integrity) are first.
- **`docs/ROADMAP.md` §2.8**, the ranking rule in nine tiers under R34, what
  it reversed, the dependency re-cuts, and where every review finding and
  every orphaned archive item landed.

#### Changed

- **Row order is priority; session numbers are stable names** (§2.1,
  `.claude/rules/ledger.md`). Renumbering would have invalidated the rulings,
  `CLAUDE.md` and 200 KB of changelog that cite the numbers.
  `tests/test_roadmap_queue.py::test_session_ids_are_unique_and_in_order`
  required ascending numbers, which made the number the rank; it is now
  `test_session_ids_are_unique_and_session_00_leads` and keeps uniqueness,
  the id shape and Session 00 first. The dependency test, which forbids a
  row depending on a later row, is the invariant the ordering protects and is
  unchanged.
- **The order.** Pending rows now run 37, 38, 23, 21, 17, 39, 23b, 23c, 23d,
  12, 41, 44, 44b, 24, 24b, 24c, 25, 25b, 28, 18, 18b, 26, 27, 29, 13, 14,
  15, 15b, 16, 42, 43, 19, 20, 40, 22, 45, 46, 30, then the six deferred rows.
  This reverses the 2026-09-22 order that put Sessions 12 to 16 ahead of all
  construction and model work: the construction changes with measured lift on
  graded standings (the hygiene bounds and the 0.80 share cap, Classic
  diversification, Ben's game theses, contest-aware assignment) and the
  confirmed prior-model defect now precede the delivery scaffolding, because
  R28's baseline-first already ships a file before any model stage.
- **Dependencies re-cut.** Session 23 no longer waits on Session 18: its
  mechanism is accepted on the supplied fixtures and its standings grading is
  Session 18b. Session 24b's top-1% proxy is a registered constant from the
  2026-09-15 findings until Session 18b replaces it. Session 12 absorbs the
  late-swap clock bound and the `Name (ID)` form; Session 13 absorbs the
  session-probe and scored-pool open items; Session 19 absorbs the merge gate.
- **Consolidated from the archives and ledgers**: 25 items open only in
  `changelog.md`, the backlog and changelog archives or the retired prompts,
  and about 40 open recommendations from `plan.md`, the critiques, the two
  retrospectives, the debrief, the two standings findings and
  `IMPLEMENTATION_STATUS.md`, each now in a session card or in §2.8. Nothing
  was deleted from any of them.
- The Session 11c merge SHA (`bedf6a3`) is recorded in §4.

#### Verification

- Suite on `bedf6a3` before any edit: `1762 passed, 1 skipped in 338.00s
  (0:05:37)` on Linux, recorded with `scripts/record_verify.py`. The one skip
  is the junction test.
- After the edits: `tests/test_roadmap_queue.py`,
  `tests/test_harness_orientation.py` and `tests/test_repo_boundaries.py`
  `204 passed in 1.73s`; the full suite `1762 passed, 1 skipped in 321.20s
  (0:05:21)`; `sh ./nfl.sh doctor` `SETUP_COMPLETE`; `git diff --check` clean;
  `python3 scripts/check_protected_paths.py` "No protected path touched".
- `python3 scripts/repo_state.py --stdout` reports `sessions startable: S37,
  S38, S23 (+10 more)` and three open `[BEN:]` flags (Sessions 12, 46, 30).

#### Left open

- The findings are queued, not fixed; the engine on `main` is as the review
  describes it until Sessions 37 and 38 land.
- Two questions in the Session 12 and Session 46 cards and the Session 30
  ruling wait on Ben and block nothing; §2.8 lists five more that are
  bankroll or spending decisions.

### 2026-09-25: a Classic policy may bind some of the rows (Session 11c)

Session 11b let a Showdown policy bind a subset of the fillable rows; a Classic
subset validated but was refused by name. Now C2's joint solve fills the
policy's rows, C1 fills the rest, and C3 audits and packages the mixed file,
naming each row's source. On `claude/laughing-keller-b7cr5q`, claim `e2d5e57`.
Every run still ends `PRIOR_ONLY / DO_NOT_UPLOAD`; exit codes keep their
meaning.

#### Added

- **The C1 fill after C2** (`selection.py`): the C2 branch calls the fill SD3
  already used (`_fill_unbound`, C1 through `_sequential_lineups`). Every C2
  lineup and prefilled roster is a no-good, only the run's own exclusions
  apply, and it is all or nothing. The selection report's `unbound_fill`
  records it with `source: "C1"`; the policy's
  exposure and overlap stay its own rows.
- **Fill time for C2** (`prior_review._fill_solve_seconds`): each fill solve
  gets what the policy's declared bank and joint-solve limits leave of the
  window, split across its solves, from 0.5 s to 10 s. SD3's shares are
  unchanged.
- **C3 over a mixed portfolio** (`classic_review.py`): the policy binds the
  fillable rows or a template-order subset. The policy's rows come from
  `classic_assignment.json`, C1's from `classic_selection.json`'s
  `assignments_by_entry_id`, whose rows outside the policy must be exactly the
  unbound rows (`CLASSIC_C3_UNBOUND_ROWS_MISMATCH`, `V`).
  - Over the policy's rows: bank membership and candidate identity, every count
    and bound, the policy's exact exclusions, the pairwise cap, the C2-audit
    comparison and the exposure denominator.
  - Over every filled row: legality, the selection record's roster, salary and
    score, canonical uniqueness (R29, forced whenever rows are unbound), the
    prefilled repeat, activity, role evidence, the template bytes, and the
    run's own exclusions: no filled row may hold a person the bound coverage's
    `pool_coverage` names with any reason but `SELECTABLE`
    (`CLASSIC_C3_SELECTED_PERSON_EXCLUDED_BY_RUN`, `V`).
- **Records**: the readable review is `prior_only_readable_review_classic_c3_v2`
  (each entry's `source`, and `unbound_rows` for the C1 rows: ids, checks,
  person exposure, and the most people one shares with any filled row). The
  export audit is `prior_only_classic_export_audit_c3_v3` (`bound_entry_ids`,
  `unbound_entry_ids`, `row_sources`, one more `checks_run` item). The HTML shows
  each row's source and a C1 section. v1 and v2 stay as written.
- **Registry**: `CLASSIC_POLICY_SUBSET_UNSUPPORTED` removed (nothing emits it);
  `CLASSIC_C3_UNBOUND_ROWS_MISMATCH`, `CLASSIC_C3_POOL_COVERAGE_PEOPLE_ARRAY_REQUIRED`
  and `CLASSIC_C3_SELECTION_ASSIGNMENT_ROSTER_ARRAY_REQUIRED` (`audited_selection`,
  `V`), and `CLASSIC_C3_SELECTED_PERSON_EXCLUDED_BY_RUN` (`operator_restriction`,
  `V`) added. 1,226 codes in 46 families; SHA-256
  `685d7109291e2d903097bb648c0b73787456cd6f06254f2bf24c55247cbb0f25`, re-pinned
  in `tests/test_gate_registry.py` and `docs/DATA_CONTRACTS.md`.
- **Tests**:
  - in `tests/test_entry_groups.py`: the acceptance through `run-slate` (five
    rows, one prefilled, two bound, two C1); `prior_review` called directly; a
    C2 run with an official inactive; and C3 replayed from the run's own call
    with one bound artifact mutated per case (a C1 row repeating a policy row or
    the prefilled roster, a missing or extra unbound row, an inactive and a
    run-excluded person in a C1 row, a policy row outside the bank);
  - in `tests/test_classic_portfolio_c2.py`: the C2 audit on a subset;
  - in `tests/test_portfolio_policy.py`: the C2 fill-time arithmetic.

#### Fixed

- **C3 never ran when the run excluded anyone.** Intake validates a Classic
  policy with the run's own exclusions (official inactives, operator
  exclusions) and marks them `SOURCE_OR_PARTICIPATION_PRECEDENCE` in the
  normalized policy. C3 re-validated the source without them, so it could never
  reproduce those bytes. Every such C2 run ended
  `CLASSIC_C3_SOURCE_NORMALIZED_POLICY_DISAGREEMENT`, and the baseline shipped
  in its place.
  - Confirmed on `main` (`adf4ef2`) with a full policy and the fixture's
    inactive DST: exit 2, producer `run-slate:baseline`.
  - No test had run C2 with an exclusion.
  - C3 now re-validates with the people the normalized policy marks. They only
    add zero caps, and the canonical-bytes comparison still binds everything
    else.
  - It is in `classic_review.py`, a file the card names. Without the fix, the
    card's capability could not deliver on a slate with official inactives.

#### Changed

- **The refusals are gone**: `run-slate` intake, `prior_review` and
  `selection` no longer refuse a Classic subset. With the intake refusal gone,
  an S-only subset policy may take the relaxation ladder at intake, which
  already binds the subset (Session 11b).
- **`scripts/make_classic_policy.py`** prints what C1 will fill instead of the
  refusal, and its docstring says a subset runs.
- **Contracts and runbook**: `docs/DATA_CONTRACTS.md` C2 (a rule change dated
  Session 11c, no new policy version), C3 (the split, the fix, both new record
  versions) and the `run-slate` result's `row_sources`; `docs/RUNBOOK.md`'s
  Classic policy step.
- **Visible test edits, each one the card's rule moved**:
  - `test_a_classic_subset_policy_is_refused_by_name_until_session_11c` became
    the acceptance test;
  - `test_a_classic_subset_is_refused_by_prior_review_and_selection_called_directly`
    became `..._is_filled_by_prior_review_and_selection_called_directly`;
  - the generator test's `"Session 11c" in printed` now checks the fill line;
  - `test_every_prior_review_exit_names_its_row_sources`'s docstring no longer
    says a Classic file is one source or the other;
  - `test_c2_required_player_without_current_activity_is_delivered_and_named`
    checks export audit v3.

#### Decided

- **The C2 audit is unchanged.** Its artifact and its expected entries were
  always the policy's list, which is now the bound list, so it already covered
  exactly the policy's rows. A test proves it passes on a subset and refuses an
  artifact that lists an unbound row. C1's rows are C3's to check, as SD3
  leaves the fill's rows to the readable review.
- **`classic_selection.json` keeps its version.** Its `assignments_by_entry_id`
  and `lineups` already held every filled row; its `entry_assignments` and
  embedded C2 audit are the policy's rows and say so by their `entry_ids`.
- **Export audit v3 as well as readable v2.** The card named only the readable
  record. An integrity record whose counts cover some rows and whose
  `entry_ids` cover all of them cannot say which is which without the row map.
- **Run exclusions from `pool_coverage`.** It is the only bound C3 input that
  names the run's own exclusions with a reason. The synthetic scale-acceptance
  coverage lists no people, so it names none, and a malformed list refuses.
- **C1 rows have no overlap cap.** C1 cuts only exact rosters, as it does with
  no policy. The C1 section reports the largest overlap rather than capping it
  (R34: concentration is measured before it becomes a rule).

#### Review

The `reviewer` subagent read the diff against the card. It found no path that
writes a wrong or repeated lineup, and no check that a policy binding every
row now evaluates differently. What it raised, and what became of each:

1. `docs/DATA_CONTRACTS.md` and this entry put the fill's record at
   `portfolio_policy.unbound_fill`; it is the selection report's
   `unbound_fill`. Fixed in both.
2. The C2 window check counts only the policy's declared limits, not the fill,
   so a tight window could run the fill's 0.5 s solves past the deadline. This
   stays as 11b decided for SD3: a late fill is named
   `DEADLINE_PASSED_DURING_REVIEW` like any late stage.
3. C3's run-exclusion check has nothing to check when the coverage lists no
   people. Only the synthetic scale-acceptance record lacks the list; every
   `prior_review` coverage writes it, and a malformed list refuses. Stays.
4. The card asked for "a C1 section" in `classic_selection.json`; none was
   added. The C1 rows are already there, hash-bound, in
   `assignments_by_entry_id` and `lineups`, and C3 derives each row's source
   from the policy's binding and the plan, not from a label the selection
   writes about itself. A section would be a new selection schema version,
   which `classic_scale_acceptance.py` pins as well, for a self-description
   C3 does not need. On Ben's list to overturn.
5. Missing tests.
   - Added `test_a_policys_exclusion_binds_its_rows_and_never_the_c1_rows`:
     the person C1 chose for both of its rows is excluded by the policy; he
     stays out of the policy's rows, stays in a C1 row, and C3 passes.
   - Added a clean replay of the mixed package to the mutation test: the CSV
     and the export audit come out byte for byte. Its capture now snapshots the
     call's dicts, which `prior_review` extends after C3 returns.
   - Renamed the direct test to `..._filled_by_prior_review_called_directly`,
     since it no longer calls selection itself.
   - Not added: a Classic fill that runs out of distinct lineups. The
     fixture's pool is too large to exhaust; the all-or-nothing path is
     `_fill_unbound`, shared with SD3 and tested there.
6. Rung 4 carries a subset policy's exclusions to every row. That was 11b's
   decision and is on Ben's list; a Classic subset can now reach it too.
7. The ledger's placeholder SHAs were filled in place. That is the protocol
   (the next session records the merge commit), as 11b did.

#### Verification

- Full suite before changes: `1758 passed, 1 skipped in 384.59s (0:06:24)`.
  After: `1761 passed, 1 skipped in 371.42s (0:06:11)`. The three added tests
  are the official-inactive C2 run, the C3 mutation replay and the C2 audit on
  a subset; the two refusal tests were replaced in place. The skip is the
  junction test. After the review's additions (the policy-exclusion test, and
  the clean replay inside the mutation test):
  `1762 passed, 1 skipped in 370.74s (0:06:10)`. CI on the first push
  (`fc256c5`): `suite`, `boundaries`, `protected-paths` and `windows` green.
- The card's command plus the registry, policy and ladder files
  (`tests/test_entry_groups.py tests/test_classic_review_c3.py
  tests/test_classic_portfolio_c2.py tests/test_gate_registry.py
  tests/test_portfolio_policy.py tests/test_relaxation_controller.py`):
  `344 passed in 190.66s (0:03:10)`. That run predates the C3 re-validation
  fix; the two tests that cover the fix then passed on their own
  (`2 passed, 32 deselected in 3.99s`), and the full suite above covers all of
  it.
- `test_a_classic_policy_binding_every_fillable_row_gives_the_same_file_as_before`
  reproduces `C2_FULL_FILLABLE_SHA256` (`48027a40…f8ce`, captured on `main` at
  `bd5a97f`), so a policy binding every row gives the same bytes.
- `doctor` `pass_status` true; `git diff --check` clean;
  `check_protected_paths.py`: no protected path touched.

### 2026-09-25: Showdown game theses are queued as Session 23b (chunk P8)

Ben asked for a backlog item for the Showdown discipline behind R33 and R34
(the ATL@GB slate), with the strategy and theory only, not the implementation.
On `claude/affectionate-bohr-mnr8vz`. Documents only; no code, contract or gate
changed.

#### Added

- **`docs/chunks/P8-showdown-thesis-sleeves.md`**: every Showdown lineup
  follows one named game thesis Ben chooses, and the portfolio spreads its rows
  and captains across theses, judged against R34's two goals (large prizes, no
  washouts). It gives:
  - R33 and R34 in Ben's words;
  - the evidence (the rejected ATL@GB file, the hand-built ATL@GB sleeves that
    repeated lineups and lost their theses to relaxation, DAL@NYG's collapse to
    Dak 20 of 20, and concentration as a ruin mechanism across 8,007 field
    portfolios);
  - Ben's theses as game scripts: each team wins big, each team wins close
    (high or low scoring), a defensive battle, a shootout;
  - nine principles, among them: no filler rows; a thesis shapes the lineup
    captain first, kicker and DST included; Ben names the teams and the engine
    never infers a script; one portfolio-wide share limit; a thesis is never
    bent to fit; backup quarterbacks out by default.

  How to build it is the implementing session's call.
- **`docs/ROADMAP.md`**: the Session 23b row and card, and its ledger row.

#### Changed

- **Session 23** keeps P2 (contest-aware assignment, hygiene bounds,
  `max_person_share`, the debrief's bank-cap point). R33's thesis target and
  the retrospective's §9 #1 Showdown constraints moved to Session 23b, and R33's
  routing line in §2.5 says so. The two sessions share one constraint vocabulary
  and one share limit.
- **Ledger**: Session 11b's close and Session 11c's addition record `6394eda`
  (PR #66).

#### Decided

- **Placement.** 23b follows Session 23 in priority, behind the delivery
  sessions (Ben's 2026-09-22 order). It depends only on Sessions 10 and 11b,
  both complete, so it is startable now and does not wait on the standings
  chain (Sessions 17 and 18, O1, O2) that Session 23 needs. Moving it up is
  Ben's call.

#### Verification

- `sh ./nfl.sh test tests/test_roadmap_queue.py tests/test_harness_orientation.py -x --tb=short`:
  `79 passed in 0.62s`. `repo_state.py` lists Session 23b as startable.
### 2026-09-25: prompt audit of the Claude Code surface

Not a roadmap session. An audit of every file Claude Code loads as text
(`CLAUDE.md`, `docs/START_HERE.md`, `.claude/rules/`, the skills, the agents)
for instructions that are stale or were tuned for an earlier model, then the
fixes Ben approved ("Implement all"). On `claude/api-prompt-audit-4h51qe`. No
code changed. `CLAUDE.md` is touched, so the pull request carries
`ben-review`.

#### Changed

- **Slate rules reach a slate.** `.claude/rules/slate-operation.md` loads only
  on a Read of `docs/RUNBOOK.md`, `docs/OPERATOR_GUIDE.md` or `scripts/**`
  (Claude Code loads path-scoped rules on Read, not on Grep or Bash), and a
  slate greps the runbook and runs scripts through Bash. `stops-and-reports.md`,
  which always loads, now says to Read it before a slate's first command.
- **Stale facts in `CLAUDE.md`.** "Four independent truths until Session 03"
  now names the five truths and the exits that report `DELIVERY_STATE`
  (Sessions 03 to 11b are `Complete`). `selection.py:577-584`, which had
  drifted to 736-746, is now the status code `SOLVER_RETURNED_NO_LINEUP`.
  `1177 passed` and 155s are gone: the session-start digest carries the last
  recorded suite line, and the suite takes about five minutes on Linux.
- **Standings skill.** Its description and "This is not" section named
  `nfl-classic-lineups` and `nfl-showdown-lineups`, which exist only in the
  archives; both now name `run-slate`. Rule 5 said `prior_review` never emits
  `nfl_prelock_run_manifest_v1`; it has since `7edddee` (2026-09-14). "Run it"
  now leads with the Windows command, where `data/runs/` lives.
- **Delegation.** "More than five files: `explorer`" becomes a wide multi-file
  sweep where the conclusion, not the text, is needed (`CLAUDE.md`,
  `START_HERE.md`, `explorer.md`). Close-out runs `reviewer` only when the
  diff changes `src/`, `scripts/`, `tests/` or `config/`.
- **Wording.** `git-authority.md` states the protected list as it is, without
  "It was twelve", "now" and "no longer"; Ben's 2026-09-20 quote and both
  reasons are kept. `reviewer.md` drops "no praise".

#### Found, not changed

- Session-number tags ("since Session 07", "(Session 10)") across `CLAUDE.md`,
  `START_HERE.md` and `operating-path.md`: accurate, left for their next edit.
- `explorer.md` and `reviewer.md` tell the subagent to Read `CLAUDE.md`, which
  subagents already inherit.
- Windows suite time: CI's `windows` job ran pytest 06:45:42 to 06:55:59
  (about 617s), past the 600000 ms tool maximum. `CLAUDE.md` and `/verify` now
  say to run the complete suite in the background on Windows.

#### Verification

- `python3` check: all 16 `CLAUDE_MD_BOUNDARY` provenance refs in
  `config/gate_registry_v1.json` still appear in the edited `CLAUDE.md`.
- `sh ./nfl.sh test tests/test_gate_registry.py tests/test_repo_boundaries.py tests/test_roadmap_queue.py tests/test_harness_orientation.py -x --tb=short`: 367 passed in 8.78s.
- Full suite `sh ./nfl.sh test`: `1758 passed, 1 skipped in 378.14s` (the skip is `tests/test_cowork.py:115`, Windows junction behavior); `doctor` `pass_status: true`.
- `git diff --check` clean; `CLAUDE.md` 199 lines.

### 2026-09-24: ATL@GB Showdown slate, and R33 (game theses)

A slate operation, not a roadmap session. Twenty reserved Showdown entries,
salary `74b5ffd6…`, entries `c7e400f5…`, lock 20:15 ET. On
`claude/atl-gb-showdown-lineups-u7zsba`. Every run ended
`PRIOR_ONLY / DO_NOT_UPLOAD`; no code changed.

#### Delivered

- Baseline first (`20260924T231305Z-atl-gb-sd-0924`), then the review stopped
  at `KICKER_ROLE_UNRESOLVED` (GB lists Krieg and Smack).
- First file handed over: `20260924T232352Z-atl-gb-sd-A-c75`,
  `DK_REVIEW_ENTRY_atl-gb-sd-A-c75.csv` `6842f5c9…`, 20 rows, supplied rung,
  no relaxation. `qa_showdown_portfolio.py`: PASS, 0 defects, max overlap 4,
  salary 46,900 to 50,000, every lineup one or two starting quarterbacks.
  Ben rejected its captain concentration: five captains at 25% each.
- The file that replaced it: `20260924T234658Z-atl-gb-sd-E-cpt10`,
  `DK_REVIEW_ENTRY_atl-gb-sd-E-cpt10.csv` `05b1698f…`: Captain 0.1, combined
  0.75, kickers 0.3, overlap 4, no Captain at FLEX salary 1,600 or less, K and
  DST Captain allowed. Supplied rung. QA PASS, 0 defects, 11 captains at 2 or
  fewer, salary 43,800 to 50,000, one zero-quarterback row. Combined 0.6 held
  the rung but left four zero-quarterback rows at 34,000 to 39,300.
- Inputs: the nflverse depth chart captured through `sources.py`
  (`depth_charts_2026.csv` `8ca09ff7…`, snapshot 2026-09-24T12:42:08Z) as a
  `nfl_qb_depth_role_evidence_v1` package (ATL Penix, GB Love). Krieg excluded
  by exact ID: that snapshot lists Smack as GB's only place kicker and Krieg on
  no GB row since NYJ in March. Backup quarterbacks (Taylor, Slovis, Tua)
  excluded at Ben's direction.
- Policy: Captain 0.25, combined 0.75, both kickers 0.3, overlap 4. Combined
  0.65 left the last row with no quarterback and $10,700 unspent; a policy
  binding 19 rows with the 20th filled sequentially failed QA (overlap 5), since
  the fill is outside the policy's overlap cap by design.

#### Found

- **A gate no allowlisted source clears.** `kicker_roles._SOLE_CUES` holds
  "placekicker", but nflverse writes `pos_name` as "Place kicker", so a
  depth-chart excerpt can never satisfy `QUALITATIVE_SOLE`. Recommendation:
  accept "place kicker". The run used an exact-ID exclusion and still shows
  Smack under the sole-listed assumption.
- `scripts/make_offensive_role_evidence.py` still prints that `run-slate` has
  no QB-depth flag; `--qb-depth-role-evidence-json` exists and worked.
- MarShawn Lloyd, GB's depth-chart RB1 with Jacobs `OUT`, had zero exposure:
  Jacobs' prior volume goes to nobody without a numerical role source.
- No kicker or DST Captain can be forced. The prior never chooses one, and a
  sleeve whose only allowed captains were K, DST or a backup RB (GB win low,
  ATL win low) was attempted at rung 2 only, with no supplied attempt, so the
  zeroed captains came back and the sleeve lost its thesis. A GB win big sleeve
  with Lloyd among four required captains went to rung 3. Unexplained; it
  belongs to Session 23's per-thesis rule sets.
- R33 (`docs/ROADMAP.md` §2.5): six thesis sleeves, run one policy each and
  assembled by row, failed QA three times with repeated lineups across
  sleeves (the third also lost its captains to rung 2), and were not handed
  over.
- R34 (`docs/ROADMAP.md` §2.5): Ben's two goals, large prizes and minimizing
  washouts, through leverage and diversification. Written into
  `.claude/rules/slate-operation.md` (a pre-handoff read against both goals)
  and `.claude/rules/selection-and-objective.md`.

#### Verification

- `sh ./nfl.sh test tests/test_roadmap_queue.py -x --tb=short`: 24 passed.
- Full suite `sh ./nfl.sh test`: `1758 passed, 1 skipped in 307.12s`.

### 2026-09-24: a Showdown policy may bind some of the rows (Session 11b)

A policy bound every fillable row or none. Now a Showdown policy may bind a
subset, a thesis or dart sleeve (Showdown retro #4 and §7c): its joint solve
fills its rows, and sequential Showdown fills the rest without repeating any
lineup. A Classic subset validates but is refused by name until Session 11c.
On `claude/affectionate-bohr-mnr8vz`, claim `6d24bc3`. Every run still ends
`PRIOR_ONLY / DO_NOT_UPLOAD`; exit codes keep their meaning.

#### Added

- **The subset rule**, `entry_groups.subset_binding_problems`: a policy binds
  the plan's fillable rows or a non-empty subset of them in template order,
  each once. Both validators take the fillable rows as the rows a policy may
  bind; a prefilled, partly filled, unresolved, unknown, repeated or
  out-of-order row is still `PORTFOLIO_POLICY_ENTRY_ID_BINDING_MISMATCH` or
  `CLASSIC_POLICY_ENTRY_ID_BINDING_MISMATCH` (`V`). The bound list is the
  denominator: Showdown's `floor(fraction x bound rows)` (0.5 over 4 bound rows
  of 10 fillable allows 2, not 5), Classic's integer domains, default bounds,
  default stack rules and `default_search_limits`.
- **The unbound fill**, `selection._fill_unbound`: after the SD3 joint solve,
  sequential Showdown fills the unbound rows (`fill_count`), every policy
  lineup and prefilled roster a no-good, under the run's own exclusions only.
  The sequential loop moved into `_sequential_lineups`, shared with the
  no-policy path unchanged. The policy report's `unbound_fill` records it;
  `prior_review` merges the two into one assignment in template order, never
  cycled, and `selection_report.row_sources` names each row's source.
- **The readable review, `prior_only_readable_review_sd5_v2`**: each entry's
  `source`, and `unbound_rows` (the fill's rows, checks, overlap and exposure).
  With a subset the policy's checks cover its rows and the denominator is
  theirs; every filled row is checked for legality, bytes and distinctness
  against every other row and every prefilled roster; the unbound rows also for
  the run's exclusions, official inactives and the fill's overlap.
- **The result** carries `row_sources`; `portfolio_policy` adds
  `bound_entry_ids` and `unbound_entry_ids`, and its `entry_count_denominator`
  is the bound rows.
- **Generators**: a repeatable `--entry-id` in `scripts/make_showdown_policy.py`
  and `scripts/make_classic_policy.py` binds those rows in template order; a
  row that is not fillable is `ENTRY_ID_NOT_FILLABLE`, a repeat
  `ENTRY_ID_REPEATED`. The Showdown generator's `--rung` keeps the subset.
- **Registry**: `CLASSIC_POLICY_SUBSET_UNSUPPORTED` (`implementation_limit`,
  `P`); `READABLE_REVIEW_ROW_SOURCE_MISMATCH` and
  `READABLE_REVIEW_UNBOUND_FILL_REPORT_MISMATCH` (`audited_selection`, `V`);
  `READABLE_REVIEW_UNBOUND_ROW_EXCLUDED_PERSON` (`operator_restriction`, `V`);
  `READABLE_REVIEW_UNBOUND_ROW_NOT_ACTIVE` (`official_activity`, `P`, as C3's
  own). 1,223 codes in 46 families; SHA-256
  `7343565244853db9a14fb3b0163d8b236adb30c200eebbb725c7c4ce683ee932`, re-pinned
  in `tests/test_gate_registry.py` and `docs/DATA_CONTRACTS.md`.
- **Tests**: 10 in `tests/test_entry_groups.py` (the Showdown subset through
  `run-slate` with a prefilled row, a bound prefilled row refused `V` with the
  baseline shipping, both validators' refusals, the Classic refusal, both
  generators, the two full-fillable golden hashes, and the three added after
  review), 7 in `tests/test_portfolio_policy.py` (bound-count caps in both
  modes, the fill under the run's exclusions and not the policy's, all or
  nothing, the audit's artifact rule, the fill's time arithmetic), 4 in
  `tests/test_relaxation_controller.py` (rung documents and records bind the
  subset, rung 4's window counts every fillable row, a subset relaxing to rung
  2 through `run-slate`, and rung 4 filling every row).

#### Changed

- **The SD3 audit** (`audit_policy_assignments`, record unchanged) takes the
  policy's rows and the new `unbound_entry_ids`: the assignment artifact's
  policy rows must equal the audited assignment, and its other rows must be
  exactly the unbound rows. For a policy binding every row this is the old
  check, row for row.
- **The ladder** binds the supplied policy's list: `Ladder.entry_ids` is it,
  every rung's document and each record's `entry_ids` carry it, and the
  validator gets `Ladder.fillable`. Rung 4 has no policy and fills every
  fillable row, so its window check counts them all.
- **`assignments.csv`** under a policy is every fillable row in template order
  (the policy's order before; the same bytes when the policy binds every row).
- **A Classic subset is refused by name** at `run-slate` intake, in
  `prior_review` and in `selection` (`CLASSIC_POLICY_SUBSET_UNSUPPORTED`); the
  baseline ships and the pre-review exit names why.
- **Contracts**: `docs/DATA_CONTRACTS.md` C2 and SD3 (a rule change dated
  Session 11b, no new policy version), SD4's unbound rows and audit, SD5 v2,
  the `run-slate` result, the relaxation record's `entry_ids` and rung 4's
  exclusions; `docs/RUNBOOK.md` for both policy steps.
- **One test edited, a visible change the card's rule moved**:
  `test_portfolio_policy.py::test_duplicate_and_subset_entry_bindings_are_rejected`
  became `test_duplicate_reordered_and_unknown_entry_bindings_are_rejected`. It
  pinned a one-row subset as refused; that subset now validates. The duplicate
  case is unchanged, and reordered, unknown and empty bindings are refused in
  its place.

#### Decided (Ben's leans, recorded)

- **Order of the solves**: the policy's joint solve first, then the fill,
  seeded with the policy lineups and prefilled rosters as no-goods. The fill is
  the no-policy selector's rules among its own rows (a distinct Captain per
  lineup until the pool runs out, the request's `max_person_overlap`); it does
  not inherit the policy's caps, overlap or Captain rule, because those are
  the thesis, not the portfolio.
- **Exclusions**: a policy's exclusions and zero caps bind only its rows. At
  rung 4 the dropped policy has no rows of its own, so a subset's exclusions
  carry to every row, as Session 10's never-relaxed rule says: widening a fade
  only tightens.
- **Audits**: the SD3 audit over the bound rows, record unchanged; the readable
  review is the second section for the unbound rows, because it already
  re-derives every filled row independently. v2 because a field was added.
- **`lineup_count`** still describes the file, every fillable row; the policy's
  own count is its list.
- **Partial fill**: all or nothing, as before. A fill that runs out of distinct
  lineups raises `SOLVER_RETURNED_NO_LINEUP` with `stage=UNBOUND_FILL`, the
  review delivers nothing and the baseline stays the file, named. A partial
  review file could never replace a fuller baseline anyway.
- **Fill time**: each fill solve gets what the bank (70%) and joint solve (20%)
  leave of the window, split across its solves, at most 10 s and at least
  0.5 s. The SD3 rung window checks do not add the fill; a late fill is named
  by `DEADLINE_PASSED_DURING_REVIEW` like any late stage.
- **Generator flag**: repeatable `--entry-id`; the rows are bound in template
  order whatever order they were given, and a row that is not fillable stops
  the script.
- **Policy contracts**: no new version (the shape is unchanged, a valid policy
  keeps its meaning, an older reader refuses a subset).
- **Breakpoint used.** With the Showdown path the diff passed about 1,500
  changed lines, so C2 with a C1 fill and C3 over a mixed portfolio moved to
  Session 11c. Selection refuses a Classic fill rather than carrying a C2 path
  nothing exercises. C3's export names no row source yet; a Classic file is
  still all C2 or all C1, and the result's `row_sources` says which.

#### Review

The `reviewer` subagent read the diff against the card and found nothing
blocking: the full-fillable path is row for row the old one, every cap counts
the bound rows, the SD3 audit is the old check when nothing is unbound, the
ladder binds the subset, and the Classic refusal cannot be walked around (the
intake blocker keeps the ladder from triggering; `prior_review` and `selection`
refuse on their own). Its open list, and what became of each:

1. The readable review's new checks never fired in a test. Now
   `test_the_readable_reviews_second_section_refuses_each_mutation` replays the
   run's own call with one input changed and gets each code:
   `READABLE_REVIEW_ROW_SOURCE_MISMATCH`, `..._UNBOUND_FILL_REPORT_MISMATCH`,
   `..._UNBOUND_ROW_EXCLUDED_PERSON`, `..._UNBOUND_ROW_NOT_ACTIVE`, and
   `ENTRY_PREFILLED_LINEUP_REPEATED`.
2. Nothing showed the run's own exclusions binding the fill. Added.
3. The `prior_review` and `selection` Classic refusals were untested. Added,
   calling each directly.
4. `row_sources` was tested only on the Showdown exit. Added for C1 and C2.
5. The fill has no stop of its own inside the window: each solve is floored at
   0.5 s, and the SD3 rung window checks leave the fill out. That stays as
   decided above (a late fill is named like any late stage); the arithmetic now
   has a test.
6. Rung 4 carries a subset policy's exclusions to every row. That stays as
   decided above; it is on Ben's list to overturn if he wants a fade confined
   to the thesis rows even at rung 4.
7. The golden hashes were not recomputed by the reviewer; they were captured
   twice on `main` and hold on the Windows CI job too.
8. The one edited test landed in the code commit rather than its own; it is
   named here and in the pull request. History is never rewritten to split it.
9. `src/nfl_dfs/entry_groups.py` is outside the card's named files: it holds
   the shared subset rule (`subset_binding_problems`, `unbound_rows`) that both
   validators, `prior_review`, the readable review and the ladder read.

#### Verification

- Golden hashes captured on `main` (bd5a97f) in a scratch worktree, twice, the
  same both times: SD3 full-fillable `1918820d…eed1`, C2 full-fillable
  `48027a40…f8ce`. This branch reproduces both
  (`test_a_policy_binding_every_fillable_row_gives_the_same_file_as_before`,
  and its Classic twin).
- `sh ./nfl.sh test tests/test_entry_groups.py tests/test_relaxation_controller.py tests/test_portfolio_policy.py -x --tb=short`:
  `82 passed in 92.94s (0:01:32)`; after the review's additions
  `87 passed in 100.31s (0:01:40)`.
- Full suite before changes: `1737 passed, 1 skipped in 295.12s (0:04:55)`.
  After the first push: `1753 passed, 1 skipped in 309.81s (0:05:09)`. After the
  review's additions: `1758 passed, 1 skipped in 318.75s (0:05:18)` (21 new
  tests; the skip is the junction test). `doctor` `pass_status` true. CI on the
  first push (`767e080`): `suite`, `boundaries`, `protected-paths` and
  `windows` green.

### 2026-09-24: rows already entered ship, and every group is reported (Session 11)

One prefilled row used to refuse the whole file on five paths (prior_review
intake, the baseline, the writer, C3's package and its export audit). Authority
is per row now: a row Ben already entered is kept byte for byte, only blank rows
are filled, no generated lineup repeats a kept one, and each Contest ID group is
reported on its own. On `claude/festive-lovelace-ffryd8`, claim `3cf7537`.
Every run still ends `PRIOR_ONLY / DO_NOT_UPLOAD`; exit codes keep their
meaning.

#### Added

- **`src/nfl_dfs/entry_groups.py`**, `plan_entries(template, slate)`: every row
  is `BLANK`, `PREFILLED` or `PARTLY_FILLED`, and one of four outcomes, never
  two: **fillable** (blank, outside an unresolved group), **preserved** (a
  prefilled row whose cells are exact current-slate DraftKings IDs and whose
  roster the shared validator passes), **unresolved** (named: a partly filled
  row, a prefilled roster that does not resolve or repeats an earlier row's,
  every row of a group whose contest cannot be stated), or left for the
  producer to fill or name unfilled. A prefilled cell resolves as a bare ID or
  as text ending `(ID)`, the form `scripts/write_dk_entries.py` already reads;
  anything else does not, and is never guessed. Every preserved roster joins
  the forbidden set; one that does not resolve stays out (the brief's rule,
  and a Showdown roster with a FLEX-role ID as Captain would otherwise share a
  legal lineup's key without the no-good cut removing it).
  `group_report` gives each Contest ID's name, fee, rows by kind and outcome,
  and each undelivered row's codes.
- **Distinctness across the portfolio (R29).** `baseline.build_distinct_lineups`
  and C1 (both `LineupOptimizer` builds in `selection.py`) cut every forbidden
  roster before the first solve; the C2 enumerator and the SD3 enumerator hold
  them as already seen and cut them from every stratum, so the joint solve
  never sees one; `selection` refuses a selected repeat as a backstop. The
  baseline audit, the Showdown export, C3 and the pointer's revalidation refuse
  a filled roster equal to a prefilled one, on the generated row.
- **Records.** `nfl_release_truths_v3` (v2 plus `preserved_entry_ids` and
  `unresolved_entry_ids`), `nfl_latest_deliverable_v2` (`coverage` adds both
  lists and `entry_groups`; `supersedes` adds `delivered_rows_by_group`; v1
  pointers stay readable, and `delivery.as_v3` writes v2 truths as v3), and
  `nfl_baseline_report_v3` (rows by kind and outcome, `entry_groups`). The
  `run-slate` result carries `entry_groups` on every exit. `docs/DATA_CONTRACTS.md`
  § Entry groups, with what a reader of each old version sees.
- **Registry**: a `P` family `entry_rows` with `ENTRY_ROW_PARTLY_PREFILLED` and
  `ENTRY_PREFILLED_ROSTER_UNRESOLVED`; `ENTRY_GROUP_UNRESOLVED`,
  `DELIVERY_ROW_KIND_OVERLAP` and `DELIVERY_UNRESOLVED_ROW_UNNAMED`
  (`entry_authority`, `V`); `ENTRY_PREFILLED_LINEUP_REPEATED`
  (`distinct_lineups`, `V`). 1,218 codes in 46 families; SHA-256
  `214c1898cc15412c14767b512bd13c5792a3a5f66d5e910e97ef26693c123855`, re-pinned
  in `tests/test_gate_registry.py` and `docs/DATA_CONTRACTS.md`.
- **`tests/test_entry_groups.py`**, 22 tests, seven of them driving
  `run-slate` (Classic C1 and C2, damaged rows, two contests twice, Showdown
  sequential and SD3, each producer shown its own first lineup prefilled),
  plus the generators, the revalidation mutations and a v1 pointer read back.

#### Changed

- **The writer's rule is per row.** `lineups.write_upload_bytes`: every blank
  row is assigned or named `unfilled`, never both; every other row is in
  neither and passes through byte for byte; a row with any cell set in either
  list is still `ENTRY_BLANK_CELL_AUTHORITY_REQUIRED` (`V`). The byte audit
  (`referee.audit_output_bytes`) now also refuses an assigned row whose source
  cells were set. `CLASSIC_C3_EXPORT_PREFILLED_AUTHORIZED_ENTRY` stays as that
  backstop in C3.
- **Every producer fills the plan's fillable rows.** The baseline (its
  `ENTRY_BLANK_CELL_AUTHORITY_REQUIRED` limitation is gone, and so are its
  `MULTI_CONTEST_ENTRY_FILE_UNSUPPORTED` and `MIXED_ENTRY_FEES_UNSUPPORTED`
  limitations: several contests are groups now; legacy `certify` keeps both),
  prior_review (its intake refusal is now only "no blank row at all"), C1's
  export, the Showdown export and readable review, and C3
  (`CLASSIC_C3_BLANK_CELL_AUTHORITY_REQUIRED` likewise). A policy binds exactly
  the fillable rows, and so does every relaxation rung (`Ladder.entry_ids`)
  and both generators (`scripts/make_classic_policy.py`,
  `scripts/make_showdown_policy.py`), which read the plan instead of every row.
  The Showdown readable review treats the fillable rows as the portfolio
  (selection, policy, denominators, overlap, audit) and the template's order
  as the output's.
- **`derive_delivery_state`** takes `preserved_entry_ids` and
  `unresolved_entry_ids`. A `V` gate covers the file when it names no row or a
  row that is neither fillable nor unresolved; an unresolved row keeps the
  state `DELIVERABLE_PARTIAL`; an unresolved row nothing names, or a row in two
  lists, refuses the record.
- **`delivery.replace` compares coverage per Contest ID.** A replacement that
  delivers fewer rows in any group than a current file that still revalidates
  is `DELIVERY_POINTER_COVERAGE_REGRESSION`, naming the group, whatever its
  total. Revalidation checks the plan's preserved and unresolved rows, that
  only fillable rows differ from the template, and prefilled distinctness.
- **Tests edited, each a visible change a ruling moved:**
  `test_baseline.py::test_a_prefilled_row_is_refused_as_today` became
  `test_a_prefilled_row_is_preserved_and_the_blank_rows_ship` (the old test pinned
  the whole-file refusal naming row 4880000002); the report and truths
  versions in `test_baseline.py`, `test_artifact_preservation.py` (pointer v2
  too) and `test_run_slate_baseline_first.py`; the derivation's parameter set
  in `test_delivery_state.py`; in `test_classic_review_c3.py`, the prefilled
  case now expects `CLASSIC_C3_SOURCE_POLICY_INVALID` (the edit makes the row
  partly filled and moves the bytes the policy is bound to; still withheld,
  nothing written) and a monkeypatched writer lambda takes the new `unfilled`
  keyword; `test_gate_registry.py`'s hash and its audit §4 "mixed prefilled and
  blank rows" `P` row, which gains the two `entry_rows` codes. The `V` row for
  replacing prefilled cells is unchanged.

#### Decided (Ben's leans, recorded)

- **Delivered independently** means each group stands or falls inside one file
  per producer, with per-group coverage in `replace`; rows are never merged
  across producers (Session 06's rule). No new merged-file contract.
- **Unparseable prefilled and partly filled rows** are `P`, preserved and
  named, and the rest ships. A prefilled roster repeating an earlier prefilled
  row is named the same way: the engine never changes a filled cell, so the
  repeat is Ben's to fix on DraftKings.
- **A group left unresolved** is a Contest ID whose rows disagree on the contest
  name or fee: which contest those rows enter cannot be stated, so the entry
  mapping gate holds them (`V`, scoped to those rows) and every other group
  ships. It is the only group-scoped problem the engine finds today; row
  problems stay row-scoped.
- **Release truths** get the smallest change that lets a row be neither
  delivered nor unfilled: v3 adds two lists. Groups are derived from the
  template plus the truths, so they live in reports and on the pointer, not in
  the truths.
- **C2 and SD3 exclusion** is by canonical key at the bank, plus a no-good cut
  in every stratum so the enumerator does not keep finding the same roster.
- **Breakpoint used.** The diff passed about 1,500 changed lines before subset
  binding, so `entry_ids` binding a subset moved to Session 11b with Ben's lean
  for the unbound rows (C1 fills them after the joint solve).

#### Review

The `reviewer` subagent found three blocking gaps after the first push, each
fixed with a test that fails without the fix:

1. A Showdown run with any prefilled row withheld its own review file: the
   readable review compared the selection's `reserved_entries` (the fillable
   rows) with every template row (`READABLE_REVIEW_SELECTION_ENTRY_ORDER_MISMATCH`,
   `V`), and with a policy the policy, denominator and audit checks too. Fixed
   in `readable_review.py`; the Showdown `run-slate` tests reproduce it.
2. A Showdown prefilled row with a FLEX-role ID in the Captain cell entered the
   forbidden set by its person-level key, which the DraftKings-ID no-good cut
   cannot enforce, so the baseline stopped on `SOLVER_REPEATED_A_LINEUP` and
   delivered nothing. Only a resolved roster enters the set now, as the brief
   says.
3. The policy generators bound every template row, so C2 and SD3 could not run
   on a prefilled template. They bind the fillable rows now.

Also added from its open list: revalidation mutation tests, a v1 pointer read
back, and a C3 unit test for the `CLASSIC_C3_EXPORT_PREFILLED_AUTHORIZED_ENTRY`
backstop. Left as noted: `authorized_entries` in the intake summary still
counts every row, prefilled ones included, beside `entry_groups`.

#### Verification

- `sh ./nfl.sh test tests/test_entry_groups.py tests/test_byte_line_fidelity.py -x --tb=short`:
  `29 passed in 63.69s (0:01:03)`.
- Full suite before changes: `1715 passed, 1 skipped in 393.80s`. After the
  first push: `1730 passed, 1 skipped in 432.18s`. After the review fixes:
  `1737 passed, 1 skipped in 444.63s (0:07:24)` (the 22 new tests; the skip is
  the junction test). `doctor` `pass_status` true.
- Left open: the prefilled cell form is unverified against a real DraftKings
  download with entered rows (none in `tests/fixtures/supplied` or any
  `data/` snapshot; a schema-level scan found only blank rows), so Session 12's
  card carries a `[BEN: ...]` request for one. prior_review still fills all of
  its fillable rows or none. The upload `preflight.py` compares exported cells
  as bare IDs; it serves legacy certified packages only, which never hold a
  prefilled row.

### 2026-09-24: the engine walks the rung ladder itself (Session 10)

Until now the relaxation ladder was printed advice: `make_classic_policy.py`
said "regenerate at --rung N+1", a person reran, and Showdown had no ladder at
all. `run-slate` now walks both inside one run, inside the run's deadline
budget, and records every step. On `claude/epic-planck-3jxp20`, claim
`328166a`. Every run still ends `PRIOR_ONLY / DO_NOT_UPLOAD`; no evidence gate,
no integrity gate and no uniqueness rule is on the ladder.

#### Added

- **`src/nfl_dfs/relaxation.py`** owns the ladder. The Classic table (stack
  rules, overlap, exposure fraction, `classic_limits`, the bank halved at rung
  3) moved here verbatim; `scripts/make_classic_policy.py` is a wrapper that
  keeps its names (`_stack_rules`, `_limits`, `BankDoesNotFit`) and output. A
  Showdown table, `SHOWDOWN_RUNGS`: 1 widens every capped Captain fraction to at
  least 0.25 (zeroed Captains stay zero), 2 lifts zeroed Captains and widens to
  at least 0.5, 3 drops every exposure cap and raises the overlap cap to at
  least 5; rung 4 in both modes is no policy. `make_showdown_policy.py --rung`
  writes one by hand. A rung's policy is the loosest of the policy it replaces
  and the rung's table, dimension by dimension, so a relaxation never tightens:
  a generator's rung-k policy becomes rung k+1 exactly (tested at k = 0, 1, 2
  on the 719-person fixture), and a supplied policy starts at the first rung
  that changes it.
- **The controller in `run-slate`.** `cli._run_prior_review_profile` loops at
  its `run_prior_review` call: attempt 0 in `prior_review/`, attempt n in
  `prior_review_attempt_<n>/` reusing attempt 0's frozen priors when it built
  them, each on its rung's own policy, all inside the same budget. The pointer
  logic below the loop is unchanged and sees the last attempt, so the baseline
  stays on the pointer unless that attempt's file replaces it. A supplied
  policy whose only validation problems are `S` codes (a capacity or bound it
  cannot meet) takes its first rung at intake instead of stopping the run; any
  other problem still stops it.
- **Triggers**, read from the review's new structured `selection_failure`
  (`SelectionError(status=, facts=)` at the bank, joint-solve and C1 raises;
  `prior_review` records it, and its deadline stop too). `STRUCTURE`:
  `MODELED_BANK_INFEASIBILITY`, `INCOMPLETE_BANK_EXHAUSTION`,
  `STRUCTURAL_INFEASIBILITY`, `MODELED_BANK_INFEASIBLE_PROVEN`. `THROUGHPUT`:
  `CANDIDATE_BANK_TIMEOUT`, `CANDIDATE_BANK_SEARCH_LIMIT`,
  `CANDIDATE_BANK_TIME_LIMIT`, `PORTFOLIO_SELECTION_TIMEOUT`,
  `PORTFOLIO_SELECTION_SEARCH_LIMIT`, `PORTFOLIO_SELECTION_TIME_LIMIT`,
  `DEADLINE_POLICY_SEARCH_EXCEEDS_WINDOW`. `SOLVER_ERROR`:
  `CANDIDATE_BANK_SOLVER_ERROR`, `PORTFOLIO_SELECTION_SOLVER_ERROR`.
  `BANK_DEPTH`: `CANDIDATE_BANK_EXHAUSTED_INCOMPLETE`. Never:
  `BOUNDED_TIME_LIMIT_STOP`, `BOUNDED_SEARCH_LIMIT_STOP`,
  `FEASIBLE_LIMIT_ACTUAL_CANDIDATE_BANK` (their names
  `CANDIDATE_BANK_STOPPED_AT_LIMIT`, `PORTFOLIO_SELECTION_LIMIT_INCUMBENT`), and
  `SOLVER_RETURNED_NO_LINEUP`.
- **Bank before structure** (C4 retro #3). A throughput failure re-sizes the
  bank at the same rung, once: Classic through `classic_limits` at the slowest
  of this host's ledger rate and this run's measured one (its bank budget over
  what it built), to the window left, halved for a joint-solve limit or a
  solver error; SD3 to half what it built (its budget is the deadline's). A
  re-size that changes nothing, or does not fit, and a second throughput
  failure, take rung 4: structure does not fix throughput. An SD3 bank that ran
  out is deepened once to `max(6 x entries, 1.5 x its size)` before any rung
  (DAL@NYG retro §6, §7e), through the new `run_prior_review(showdown_candidate_limit=)`.
- **The window.** Each rung must fit the improvement window less the last
  attempt's measured pre-selection time: a C2 rung its `classic_limits` search,
  an SD3 rung 2.5 s, rung 4 0.5 s per lineup plus one. A C2 or SD3 rung that
  does not fit takes rung 4; rung 4 not fitting stops the ladder,
  `RELAXATION_LADDER_STOPPED`, with the baseline delivered. A rung that cannot
  be written or validated at all ends the ladder the same way, named.
- **Records and artifacts.** `nfl_relaxation_record_v1` (`docs/DATA_CONTRACTS.md`
  § Relaxation record) is the result's `relaxation` and
  `data/runs/<run_id>/relaxation/relaxation.json`: every attempt, every rung the
  validator refused, and one record per relaxed constraint with its class,
  family, provenance, original and final value, trigger, rung, time, Entry IDs
  and the new policy's binding. Each rung's policy is written to
  `relaxation/attempt_<n>_rung_<r>[_bank]/` (source, validation, normalized),
  validated by the supplied-policy validator against the hash of the bytes
  written, and re-checked by the review before selection.
- **Registry**: `RELAXATION_STRUCTURE_RELAXED` and `RELAXATION_POLICY_DROPPED`
  (`portfolio_bounds`), `RELAXATION_BANK_RESIZED` (`search_budget`),
  `RELAXATION_LADDER_STOPPED` (`delivery_deadline`), all `S`, and
  `RELAXATION_RUNG_UNBUILDABLE` (`stage_failure`, `P`); the four families'
  `covers` say so. 1,212 codes in 45 families, SHA-256
  `4ec6b604ad71ef2e16c72b6c6477f1f4367d35a1f3acd8f9e8a004c9fc8dae95`, re-pinned
  in `tests/test_gate_registry.py` and `docs/DATA_CONTRACTS.md`. They reach
  `release_truths` on the delivered file's exit and, beside the baseline's own,
  on the baseline's exits after the review and before it. The result's
  `portfolio_policy` adds `enforced_rung`, `enforced_policy` and
  `enforced_policy_is_supplied`, since its enforcement status describes the
  policy the last attempt ran, not the supplied one.

#### Changed

- `deadline.bank_rate_observation(reports, *, declared_bank_seconds)` reads a
  timed-out bank's count from `selection_failure`; the `candidates=(\d+)` regex
  over blocker text and `import re` are gone.
- `DEADLINE_POLICY_SEARCH_EXCEEDS_WINDOW`'s text no longer says the baseline is
  the deliverable: inside `run-slate` the ladder then re-sizes the bank or takes
  rung 4, and its record names which file ships.
- Runbook: the ladder passages (the policy section, "Shipping under a lock
  clock", the deadline paragraph) describe the engine walking it; the stale
  `selection.py:538-542` cite is `:577-584`, where C1's raise sits after this change. `IMPLEMENTATION_STATUS.md` has a
  Session 10 entry and its three "Session 10" not-yets say "since done".

#### Decided, and why

- **Solver errors** (Ben's lean): no structural rung. A solver error is a claim
  failure, not a preference, so its registry family stays `selection_claims`
  (`P`). It gets one smaller bank and then rung 4, the same as throughput.
- **Rung policies are imported** from `relaxation.py`, never produced by
  running the script (Ben's lean): no subprocess, one code path, and the
  engine's validator checks the result.
- **Structured failure** (Ben's lean): `SelectionError` carries `status` and
  `facts`; the controller and the host-rate ledger read them. The deadline stop
  is recorded structured too, its status the head of the budget's own
  `CODE:detail` event.
- **`DEADLINE_POLICY_SEARCH_EXCEEDS_WINDOW` is a trigger** though it is not a
  selection status: its own text prescribed exactly the ladder's step
  (re-size the bank to the window, or take rung 4), and the card's first line
  is that the engine, not printed advice, takes it.
- **Contract**: one name, `nfl_relaxation_record_v1`, for the run's record and
  its items, in the result's `relaxation`. A relaxation's limitation family is
  what it relaxed: the bank or its budget is `search_budget`, a bound or the
  whole policy is `portfolio_bounds`, the window's stop is `delivery_deadline`.
- **Showdown order** (DAL@NYG retro §6): the bank and the Captain strata bind
  first, so after the bank step Captain caps widen, then zeroed Captains
  captain, then every exposure cap and the tight overlap go.
- **"The window cannot hold the next rung"** (Ben's lean): its declared
  search from `classic_limits` against `improvement_remaining`, less the last
  attempt's measured pre-selection time, since each retry repeats projection
  and scoring before it selects.
- **A zero cap is an exclusion.** A Classic `maximum_entries` of 0, a team or
  game capped at 0, or a Showdown combined fraction of 0 is kept at every rung
  and carried into rung 4, because the selector already treats a zero maximum
  as an exclusion; relaxing it would put back a person someone took out. A
  fraction that only floors to zero entries (0.04 at 20) is a cap the author
  wrote as a cap, and is relaxed. A zeroed Showdown Captain is a Captain cap and
  rung 2 relaxes it (Ben's list names zeroed Captains).
- **A rung the validator refuses on a code no rung loosens** is a generator
  defect, not a preference: it is named `RELAXATION_RUNG_UNBUILDABLE`
  (`stage_failure`, `P`) and rung 4, which needs no generated policy, is still
  tried, because the worst outcome is no lineup. `RELAXATION_LADDER_STOPPED`
  stays the window's alone.
- **A joint-solve retry keeps its joint budget.** The bank step on a joint
  limit halves the bank and keeps at least the joint budget that ran out
  (within the window's 20%), so the retry is never shorter than the failure.
  A structural rung sizes its bank by the generator's rule, as regenerating it
  by hand would, and can be smaller than a large supplied bank.
- **Uniqueness on a supplied Showdown policy.** The Showdown validator accepts
  `require_unique_lineups: false`; every rung writes it true (R29) and the
  record keeps the supplied value, so the change is visible.
- **Classic `INCOMPLETE_BANK_EXHAUSTION` takes a structural rung**, as the
  generator always advised, while SD3's `CANDIDATE_BANK_EXHAUSTED_INCOMPLETE`
  deepens the bank first: the DAL@NYG retro showed the SD3 bank binding, and the
  C4 retro showed a Classic bank bound by throughput, which a deeper bank makes
  worse.
- **Intake**: a supplied policy whose only problems are `S` enters the ladder;
  search-budget codes ask for the bank step, bound codes for structure.
- **No 10b split.** The diff passed the 1,500-line breakpoint (about 1,900
  changed lines), but the Classic controller alone passes it too, so moving the
  already tested Showdown ladder to a later row would not have brought the diff
  under it and would have left Showdown on printed advice.
- **Unfilled Entry IDs** come from the baseline, as Ben expected: prior_review
  is still all or nothing, so a pool too small for every entry walks to rung 4,
  C1 runs out of distinct lineups, and the baseline ships with its unfilled
  Entry IDs. Partial delivery by entry group stays Session 11's.

#### Review

The `reviewer` subagent found four blocking items, all fixed before merge: the
result's `portfolio_policy` reported the enforced rung's audit under the
supplied policy's hashes (now `enforced_*`); the new writers had no
determinism or mutation test (added: byte-identical rung policies from the same
inputs, a folder never written over, a rung policy changed after writing
refused before selection); `DEADLINE_POLICY_SEARCH_EXCEEDS_WINDOW` said "the
baseline is the deliverable" on a run C1 then delivered (reworded); and the
pre-review exit left the ladder's texts out of `blockers` and wrote no
`relaxation.json` (both fixed, and tested). Its open items: the joint-budget
floor, zero team and game caps, the unbuildable-rung code and the uniqueness
record were fixed as above; the Showdown `READABLE_REVIEW_FAILED.json` marker
now follows the last attempt's run root; `make_showdown_policy.py --rung` has a
test and reports the controls it wrote. `CLAUDE.md`'s stale ladder lines go to
the `ben-review` follow-up.

#### Tests whose expectation changed (each its own edit)

- `tests/test_deadline_controller.py`:
  `test_a_c2_policy_whose_declared_search_does_not_fit_stops_the_review` is now
  `test_a_c2_policy_whose_declared_search_does_not_fit_takes_rung_4`. The stop's
  advice is the engine's now: no re-sized bank fits the 20 s window, so the
  ladder drops the policy, C1 delivers (exit 0), and both
  `DEADLINE_POLICY_SEARCH_EXCEEDS_WINDOW` and `RELAXATION_POLICY_DROPPED` are
  named `S`. `test_a_bank_rate_is_read_from_its_report_or_from_a_bank_time_limit`
  passes the structured failure in place of blocker text.
- `tests/test_classic_portfolio_c2.py`: the bank-rate call drops its blockers
  argument.
- `tests/test_gate_registry.py`: `test_the_rung_ladder_triggers_are_construction_preferences`
  covers the full trigger list, the solver errors' `P` family, the never-triggers
  and the four new codes.

#### Verification

- New `tests/test_relaxation_controller.py`, 17 tests, each acceptance a
  `run-slate` run on a fake monotonic clock: an impossible exposure cap (every
  person at one of three entries) is refused at rungs 0 to 2 and exports at 3;
  a bank timeout re-sizes the bank (200 to fewer candidates, budget raised) with
  identical controls and exports through C3; a one-lineup slate (a salary
  squeeze, so no evidence gate is involved) walks to rung 4, C1 runs out of
  distinct lineups, and the baseline ships one lineup and names the two
  unfilled Entry IDs; a retry that leaves one second stops the ladder with
  `RELAXATION_LADDER_STOPPED` and the baseline delivered (exit 2); a Showdown
  10% Captain cap over two entries is refused at rung 1 and exports at 2. Also a
  structural failure at selection takes rung 1 exactly, an SD3 bank that ran out
  is deepened from 32 to 48 before any rung, and three unit tests of the merge.
  After the review, five more: a rung policy mutated after writing is refused
  before selection; the same inputs write byte-identical rung policies and never
  over an existing folder; a validator refusal on a code no rung loosens is
  named and rung 4 still runs; an intake relaxation with no window stops by
  name on the pre-review exit and writes its record; the Showdown generator
  writes each rung and nothing at 4.
- Card command `sh ./nfl.sh test tests/test_relaxation_controller.py tests/test_classic_policy_generator.py -x --tb=short`:
  `35 passed` (`28 passed` before the review's tests). The complete pinned
  suite on Linux: `1715 passed, 1 skipped in 226.85s` (`1710 passed` before the
  review's fixes; baseline before any change `1698 passed, 1 skipped in
  212.05s`; the skip is the junction test).
- `sh ./nfl.sh doctor` passes; `compileall` on every changed module;
  `git diff --check` clean; `python3 scripts/check_protected_paths.py` clean.

### 2026-09-24: missing weather, Classic activity and the P1 role change ship named (Session 09, R28)

Three stops on the model path held back the engine's own portfolio for evidence
R28 moves from "stops the run" to "stops certification": a game nobody observed
the weather for, a Classic selected person with no official activity row, and
the 2026-09-19 P1 unresolved role change (Ben, 2026-09-23: "Absorb it"). Each
now ships the model's file with the gap named. On
`claude/roadmap-session-09-jizzh0`, claim `82014e5`. Every run still ends
`PRIOR_ONLY / DO_NOT_UPLOAD`; no integrity gate changed, the provider identity
gate is untouched, and the baseline consumes none of this.

#### Changed

- **Weather.** `priors.resolve_weather_state` no longer raises
  `WEATHER_STATE_REQUIRED`: a game with no state resolves to the new
  `WEATHER_STATES` member `UNOBSERVED` under the basis
  `WEATHER_UNOBSERVED:roof=<roof>`. The Classic freeze no longer raises
  `CLASSIC_WEATHER_SOURCE_REQUIRED` for a state with no captured source: the
  state is never written, and the game is `UNOBSERVED`
  (`...:UNATTRIBUTED_STATE_NOT_WRITTEN`). `prior_review.decide_weather` no
  longer blocks (`WEATHER_CAPTURE_REQUIRED`, `WEATHER_STATE_REQUIRED`): a game
  without an attributed capture gets a `WEATHER_UNOBSERVED` limitation, an
  unattributed typed state is dropped rather than passed to the freeze, and an
  open roof keeps its schedule-derived `ROOF_OPEN`. `WeatherDecision.blockers`
  became `limitations`; the WEATHER stage reports `UNOBSERVED_GAMES_NAMED`.
  After the priors stage, on the build and the reuse path alike, the run reads
  the frozen team prior and names each game frozen `UNOBSERVED`, or under an
  open roof nobody captured, as `WEATHER_UNOBSERVED:<game_id>:...`; `run-slate`
  puts each on a delivered file as a `P` limitation, and Classic
  `EVIDENCE_STATE` is no longer `PASS` with one. The R26 derived-roof path is
  unchanged. Certification's `weather_if_required` record reads `UNKNOWN` when
  any team is `UNOBSERVED`, so it can never certify.
- **Classic official activity.** The selected-evidence gate
  (`nfl_classic_selected_evidence_gate_c1_v3`) keeps in `gaps`, and still
  blocks on, synthetic role sources, a selected unavailable person and a missing
  or unselectable current role (`prior_review.py`, the `CURRENT_OFFENSIVE_ROLE`
  and `PARTICIPATION` entries). A selected person with no exact-ID row, or a run
  with no activity file, goes to the new `activity_gaps` and the run publishes;
  `run-slate` names `OFFICIAL_STATUS_INCOMPLETE_FOR_SELECTED` or
  `OFFICIAL_STATUS_REQUIRED`, the codes it already named for Showdown. The
  inconsistency checks (invalid, empty, future, stale, changed during read,
  before publish or during selection, and C1's export re-check) stay stops.
- **C3.** The official status file is optional. A row that is not `ACTIVE`
  still refuses (`CLASSIC_C3_SELECTED_ACTIVITY_NOT_ACTIVE`); a missing row does
  not. The gate must read `PASS_WITH_NAMED_LIMITATIONS` exactly when C3's own
  re-read finds a selected person without a row, and any disagreement between
  that re-read and the coverage or the gate is
  `CLASSIC_C3_SELECTED_ACTIVITY_COVERAGE_MISMATCH`; a coverage naming a file the
  review does not track is still `CLASSIC_C3_OFFICIAL_STATUS_ARTIFACT_REQUIRED`.
  The export audit (`prior_only_classic_export_audit_c3_v2`) reports
  `selected_activity` `PASS` or `INCOMPLETE` with
  `selected_activity_without_row` in place of the hard-coded `PASS`, lists
  `SELECTED_CURRENT_ACTIVITY_AND_ROLE_EVIDENCE` only when every selected person
  has an `ACTIVE` row, and names the gap in `limitations`; the readable review's
  `SELECTED_OFFICIAL_ACTIVITY` observation reads `UNKNOWN` with the people.
- **P1.** `prior_score.score_pool` no longer raises through
  `enforce_material_role_change_gate` (removed). `offensive_roles.
  exclude_material_role_changes` adds every person
  `material_role_change_blockers` names to `OffensiveResolution.excluded_people`,
  sets his finding to `EXCLUDE`, lists him under `excluded_by_finding`,
  sets `evidence_state` `UNKNOWN` and records each code under
  `material_role_change_exclusions` (`unresolved_material_role_change_gate_v2`).
  `select_prior_lineups` now reads the resolution scoring returns, so every
  selector (C1, the C2 bank, Showdown) honours the exclusion; `run-slate` names
  each code as a `P` limitation (family `unresolved_role_change`). Every prior
  stays as scored. Too few distinct lineups after an exclusion is the existing
  R29 path: C1 raises out of distinct lineups and the baseline stays the file
  with its own unfilled Entry IDs; nothing repeats a lineup.
- **Registry.** `WEATHER_UNOBSERVED`, `CLASSIC_C3_SELECTED_ACTIVITY_COVERAGE_MISMATCH`
  and `CLASSIC_C3_ACTIVITY_GAPS_ARRAY_REQUIRED` added; `WEATHER_STATE_REQUIRED`,
  `CLASSIC_WEATHER_SOURCE_REQUIRED` and `CLASSIC_C3_SELECTED_ACTIVITY_COVERAGE_INCOMPLETE`
  removed, as nothing emits them. `WEATHER_CAPTURE_REQUIRED` stays: the
  baseline still names it. 1,208 codes in 45 families, SHA-256
  `941f6d471a39c8170529b2691f2f297445ef1f18c060b3e7c97910f50cfd9ce1`, re-pinned in `tests/test_gate_registry.py` and
  `docs/DATA_CONTRACTS.md`.
- **Contracts** (`docs/DATA_CONTRACTS.md`): `nfl_team_projection_source_v2` and
  `nfl_team_projections_csv_v2` are v1 plus `UNOBSERVED`, declared only when a
  record or row carries it, so every other package and team CSV is
  byte-identical v1, and a v1 team source holding `UNOBSERVED` is refused; the
  gate v3, the C3 audit v2 and the P1 gate v2 are described beside their v1/v2.
- **Runbook**: the weather pre-capture ("Capture the weather before the
  session, not inside it") is an improvement, not a precondition, as are the
  outdoor-weather step, step 4 and the running-order note; Classic missing
  activity publishes named; the P1 "and stops" now says he leaves the pool and
  is named. `scripts/make_classic_weather_evidence.py`'s docstring and the P1
  brief say the same.

#### Decided, and why

- **Representation: a new `UNOBSERVED` member** (Ben's lean). It is explicit,
  it can never be read as an observation, the R24 loop over `WEATHER_STATES`
  covers it automatically (and a new test names it), and it is not in the
  operator vocabulary, so nobody can type it. It needs new contract versions for
  the team source and team CSV; declaring v2 only when a game is unobserved
  keeps every existing package byte-identical and every v1 reader safe.
- **A conflicting or unsupported weather state still stops**, and so does a
  supplied capture that fails its source, time or hash checks. R28 moves missing
  evidence; the card says a real conflict "still invalidates its evidence"; and
  Ben's brief keeps the matching official-activity checks as stops, so both
  kinds of evidence are treated alike. `WEATHER_STATE_CONFLICT` cannot be
  reached through the freeze at all (it passes no operator state for a schedule
  roof), and the scalar path refuses an unsupported state at request parse, so
  only a malformed per-game evidence file reaches `WEATHER_STATE_UNSUPPORTED`.
  Since Session 06 the baseline ships before either can fire. Recommendation for
  a later card: weather moves no number, so present-but-invalid weather could
  degrade to `UNOBSERVED` safely; that is a ruling on invalid evidence, wider
  than this card.
- **Classic activity codes are reused**, not new: they are the ones Showdown and
  `run-slate` already emit (family `official_activity`, `P`), so the two modes
  read the same. C3's `selected_activity` reports `INCOMPLETE` and the people.
- **Versions**: the selected-evidence gate (v3), the C3 export audit (v2), the
  P1 gate (v2), the team source and team CSV (v2) are new versions because each
  field's domain changed. The C1/C2 selection and coverage schemas are
  unchanged: their fields are the same, and the embedded gate carries its own
  version.
- **`build_priors`**: the audit's D8 text names no stop that still exists. A
  request's `to_dict` saves `build_priors`, so a plain `--request` rerun keeps
  it; `PRIOR_PACKAGE_EXPIRED` and `PRIOR_PACKAGE_REQUIRED` fire only when the
  request never authorized the rebuild, and the review then leaves the baseline
  as the file. A new test runs a `build_priors` request and a plain `--request`
  rerun of what it saved, and both reach the (stubbed) rebuild without a stop.
  The runbook's note that a rebuilt run's request keeps `prior_package_dir:
  null`, so a rerun re-fetches, is not this defect: it asks nothing and costs
  only fetch time, which the deadline budget already bounds.

#### Tests whose expectation changed (each its own edit)

- `tests/test_classic_prior_review.py`:
  `test_missing_selected_activity_blocks_before_any_selection_artifact` is now
  `test_missing_selected_activity_is_a_named_limitation_not_a_stop`, for a file
  missing rows and for no file; `test_classic_frozen_prior_producer_covers_every_game_team_and_person`
  gains an outdoor case. `test_unselectable_or_missing_role_finding_still_blocks_classic`
  (:772, :814) is a role gap and is unchanged.
- `tests/test_classic_portfolio_c2.py`:
  `test_c2_required_player_without_current_activity_stops_before_publish` is now
  `test_c2_required_player_without_current_activity_is_delivered_and_named`,
  through C3, for both cases.
- `tests/test_classic_review_c3.py` :491/:508 is the `INACTIVE` case and is
  unchanged; two tests added for artifacts that disagree about missing
  activity and an untracked status file.
- `tests/test_cowork_rerun_regressions.py` :496, :537-542 is the Showdown
  activity case and is unchanged.
- `tests/test_prior_review_profile.py`: the weather-gate tests at :218-244 and
  :1120-1174 now assert `limitations` and `WEATHER_UNOBSERVED` where they
  asserted `WEATHER_CAPTURE_REQUIRED` blockers; two cases added.
- `tests/test_priors_adapter.py`: the nine `WEATHER_STATE_REQUIRED` raises now
  assert `UNOBSERVED`; the freeze tests assert the v2 and v1 team source.
- `tests/test_qb_depth_roles.py`:
  `test_an_unresolved_transfer_the_market_disagrees_with_stops_the_run` is now
  `..._leaves_the_pool`, and asserts the same lineups as an operator fade of the
  same person; the `_prior_points` helper no longer patches the gate out.
- `tests/test_run_slate_baseline_first.py`:
  `test_blocked_weather_with_no_network_still_delivers_the_baseline` is now
  `test_an_unobserved_game_with_no_network_still_delivers_the_baseline`; its
  improvement now fails at the freeze, after WEATHER names the game.
- `tests/test_gate_registry.py`: the audit §4 weather and activity rows name the
  new codes; the `weather_blockers + gate.blockers` site left `NON_NUMERIC_SITES`
  with the code that held it; `projection.v1_never_holds_an_unobserved_game`
  joined `PLUMBING_FUNCTIONS`; `test_an_unobserved_game_moves_no_prior_score`
  added. The R24 scan, `test_a_derived_roof_moves_no_prior_score` and
  `test_r28_absorbs_the_p1_hard_stop` are unchanged and green.
- New `tests/test_r28_model_path.py`: a `run-slate` test per changed exit, all
  Classic C1 on the replay fixture pinned before lock, each delivering C1's file
  with `DO_NOT_UPLOAD`: an unobserved game (same rosters as the observed run,
  team CSV declared v2), a selected person without a row and a run with no
  activity file, and a P1 person (absent from every delivered roster); plus the
  `build_priors` rerun test, the v1 team source refusal and the certification
  weather record.

#### Verification

- Baseline before any change: `1 failed, 1676 passed, 1 skipped in 268.95s`;
  the failure was `tests/test_roadmap_queue.py::test_the_quick_start_names_the_first_startable_session`,
  tripped by this session's own claim edit landing mid-run (Section 1 still
  named Session 09); `5a1ab0b` moved it to Session 10 and it passes.
- Part 1 (`10ff660`), full suite: `1685 passed, 1 skipped in 265.00s`.
- The card's command plus every test file the brief names
  (`test_prior_review_profile`, `test_classic_prior_review`, `test_gate_registry`,
  `test_classic_portfolio_c2`, `test_classic_review_c3`,
  `test_cowork_rerun_regressions`, `test_priors_adapter`, `test_qb_depth_roles`,
  `test_r28_model_path`, `test_run_slate_baseline_first`,
  `test_projection_producer`, `test_prelock_manifest`, `test_deadline_controller`):
  `538 passed in 132.68s`.
- Complete pinned suite on `020708e`: `1692 passed, 1 skipped in 274.35s`.
- After the review round (`ea74fb4`), the three touched files: `103 passed in
  53.10s`; complete pinned suite: `1698 passed, 1 skipped in 272.90s`, recorded
  with `scripts/record_verify.py`; the skip is the junction test.
- `sh ./nfl.sh doctor` `pass_status: true`; `compileall` and import of every
  changed module; `git diff --check` clean; `scripts/check_protected_paths.py`:
  no protected path touched, so no `ben-review` label.
- Diff about 1,320 changed lines before the close-out documents, at the card's
  breakpoint with every item done, so no Session 09b row.

#### Review round (the `reviewer` subagent, fresh context)

- **Fixed, blocking.** `decide_weather` passed a typed state with no source on
  for a dome or closed roof, and the legacy (scalar) freeze reads the
  first-locking game's fields as the capture: a Classic request with an
  unsourced `weather_state`, a dome first and two outdoor games stopped the
  freeze on `CLASSIC_WEATHER_SCOPE_AMBIGUOUS`, while the same request with an
  outdoor game first ran `UNOBSERVED`. Nothing unattributed is passed on for a
  schedule roof now, and an open roof no longer passes a URI without its time
  (it stopped at `WEATHER_OBSERVED_AT_REQUIRED`).
  `test_an_unsourced_state_never_reaches_a_multi_game_classic_freeze` and
  `test_nothing_unattributed_is_passed_on_for_a_schedule_roof` hold both.
- **Fixed.** An unsourced state no longer keeps a retractable venue's blank
  roof from resolving from its history, so the weather report agrees with the
  freeze. A reused package whose state was typed without a source (Showdown's
  standalone `priors freeze --weather-state` still writes one) is named
  `WEATHER_UNOBSERVED`. `run-slate` names a P1 exclusion only on a file the
  review delivered, as it does weather. The standalone `select` command lists
  P1 exclusions under `limitations`. C3's no-file branch, which could never
  fire, now refuses a tracked status file whose coverage says none was supplied.
  Stale text corrected in the `prior_review` docstring and roof comment,
  `docs/DATA_CONTRACTS.md` (the per-person activity sentence; only the coverage
  embeds the gate) and `scripts/make_offensive_role_evidence.py`.
- **Left open, with where it stands.** Showdown's readable review builds its
  "named blockers" before `run-slate` inserts the activity, weather and P1
  codes, so it lists none of them; that ordering predates this session (it
  already omitted `OFFICIAL_STATUS_INCOMPLETE_FOR_SELECTED`), and the delivery
  limitations and `cowork_run.json` carry all three. Certification's weather
  record reads an uncaptured `ROOF_OPEN` as `PASS`: nflverse writes `open` only
  after a game is played, so no pre-lock game carries it, and `PRIOR_ONLY`
  never certifies. The coverage schemas keep their versions though
  `official_status_coverage` may now be `null` (documented), and the C3
  readable review's activity observation may read `UNKNOWN` with a null
  `observed_at` (its `state` already took `UNKNOWN` for roles). No `run-slate`
  test drives the build path through a real Classic freeze, or weather and P1
  through C2/C3 or Showdown; the pieces are covered at the freeze, the review
  and the reuse-path `run-slate` levels.

#### Found and left open

- Still blocking the Classic selected-evidence gate, for a later card:
  synthetic role sources, a selected person with a missing or unselectable
  current role (`CURRENT_OFFENSIVE_ROLE`), and a selected unavailable person
  (`PARTICIPATION`). Current role is a truth-claim gate under R28 too.
- Present-but-invalid weather evidence still stops the review (above).
- `scripts/session_probe.py` still lists `api.weather.gov` as a blocking host
  (exit 2), though a blocked host now costs only the observation. Session 13
  owns that script.
- The C3 export audit does not name `WEATHER_UNOBSERVED` or a P1 exclusion in
  its own `limitations`; `run-slate`'s delivery limitations and the coverage's
  pool rows do.

### 2026-09-24: limit-stopped banks and joint solves keep what they built (Session 08)

Until now one per-candidate HiGHS solve that hit its time or search limit set
`CANDIDATE_BANK_TIMEOUT` or `CANDIDATE_BANK_SEARCH_LIMIT` and broke, and
`solve_classic_portfolio` then returned `NOT_RUN_BLOCKING_BANK`, so every
candidate already built was lost; a bank that ran out of total budget did the
same with no solve at all; and both joint selectors discarded a valid integer
incumbent on a limit. On `claude/session-08-nonoptimal-bank-gkusm7`, claim
`d236025`. Every run still ends `PRIOR_ONLY / DO_NOT_UPLOAD`; no evidence gate
changed, and distinct lineups (R29) are untouched.

#### Added

- The C2 bank keeps a per-candidate roster a time or search limit
  (`kTimeLimit`, `kIterationLimit`, `kSolutionLimit`) stopped with, once
  `validate_lineup` accepts it again: `source_solver_status` `FEASIBLE_LIMIT`,
  its model status, gap and nodes, counted toward its stratum. The bank report
  adds `limit_incumbent_candidates`. A limit with no roster, or the total
  budget running out, stops the bank (`_Enumerator.limit_stop`); later solver
  strata record `NOT_RUN_AFTER_LIMIT_STOP`, while the solver-free witness chain
  and the witness solve still run.
- Bank statuses `BOUNDED_TIME_LIMIT_STOP` and `BOUNDED_SEARCH_LIMIT_STOP`: a
  stopped bank holding at least the entry count and a `POLICY_FEASIBLE`
  witness is not blocking. Without either it is `CANDIDATE_BANK_TIMEOUT` or
  `CANDIDATE_BANK_SEARCH_LIMIT` as before, and those still block. A solver
  error still blocks, and so does a roster the optimizer itself rejected as
  illegal at any model status (`ILLEGAL_SOLVER_ROSTER`,
  `CANDIDATE_BANK_SOLVER_ERROR`); before this session an illegal roster at a
  limit reported `CANDIDATE_BANK_TIMEOUT` or `CANDIDATE_BANK_SEARCH_LIMIT`,
  which would now have let a stopped bank through.
- Both joint selectors accept a limit that leaves a valid incumbent:
  `optimizer.LIMIT_INCUMBENT_STATUS` = `FEASIBLE_LIMIT_ACTUAL_CANDIDATE_BANK`,
  shared by C2 (`solve_classic_portfolio`) and SD3
  (`portfolio_enforcement.solve_policy_portfolio`). The rounded `col_value`
  goes through the optimum's own integrality, count and bound checks; the
  status reports gap, nodes and model status, `passed` is true, the new
  `ClassicPortfolioSelection.proven_optimal` is false, and `optimality_scope`
  is null. With no incumbent the codes stay (`PORTFOLIO_SELECTION_TIMEOUT`,
  `PORTFOLIO_SELECTION_SEARCH_LIMIT`, `PORTFOLIO_SELECTION_TIME_LIMIT`).
- The C2 joint solve starts from the bank's witness chain (`setSolution`,
  report `mip_start` `POLICY_FEASIBLE_WITNESS`), and a limit never delivers
  less than it: when HiGHS's incumbent scores below the witness, or HiGHS stops
  at a limit with none, the witness is the incumbent (`incumbent_source`
  `POLICY_FEASIBLE_WITNESS`, otherwise `JOINT_SOLVE`). Probed on highspy
  1.11.0 on the C2 fixture bank at 10 entries: with the start,
  `mip_max_nodes=0` returns `kSolutionLimit` with the start as a valid
  incumbent (objective 3598.931 against the optimum's 3599.102); without a
  start it returns `kSolutionLimit` with no valid solution. Under time limits
  of 1e-9, 1e-6, 1e-4 and 1e-3 s, five solves each on a 12-candidate and a
  34-candidate bank, HiGHS's default presolve returned the start every time;
  with presolve off it returned no incumbent at 1e-9 and 1e-6 s, sometimes at
  1e-4 s, which is why the selector does not rely on HiGHS keeping the start.
- The C2 selection record's `objective_limits` says
  `LIMIT_INCUMBENT_NOT_PROVEN_OPTIMAL_OVER_ACTUAL_CANDIDATE_BANK` for an
  incumbent in place of `OPTIMAL_ONLY_OVER_ACTUAL_CANDIDATE_BANK`.
- The SD3 bank keeps a limit-stopped roster the same way. A stopped SD3 bank
  still blocks (below).
- C3 (`classic_review.py`) accepts the two stop statuses and the incumbent
  status with a null scope; a limit incumbent claiming `ACTUAL_CANDIDATE_BANK`
  is `CLASSIC_C3_C2_OPTIMALITY_SCOPE_MISMATCH`. Its export audit and readable
  review list `CANDIDATE_BANK_STOPPED_AT_LIMIT:<status>:<n>_of_<m>_candidates`
  and `PORTFOLIO_SELECTION_LIMIT_INCUMBENT:...` as limitations, and the HTML
  says "stopped at a limit: feasible, not proven optimal" where it printed the
  scope. `prior_review.py` and `classic_scale_acceptance.py` take the scope
  from the solve instead of writing `ACTUAL_CANDIDATE_BANK`.
- `run-slate` names both as delivery limitations beside C1's
  `SOLVER_TIME_LIMIT_ACCEPTED_LINEUPS`, for C2 and SD3:
  `CANDIDATE_BANK_STOPPED_AT_LIMIT` and `PORTFOLIO_SELECTION_LIMIT_INCUMBENT`,
  family `search_budget` (`S`, `CONSTRUCTION_PREFERENCE`); the family's
  `covers` says so. Registry SHA-256 now
  `942d43cb9920c5abee29670d20944eb4c38138a71708ff69571af654d5c8e9e1`, 1,207
  codes in 45 families, re-pinned in `tests/test_gate_registry.py` and
  `docs/DATA_CONTRACTS.md`.
- Tests, each decided by a search limit, a script or a time limit a clock can
  only reach sooner; where a real bank is still built, its other clock limits
  are ones a small bank cannot reach (300 s per solve, an hour in total):
  `tests/test_classic_portfolio_c2.py` +18: a limit with a valid incumbent at
  each of the three statuses (labelled, gap 0.0125 and 37 nodes reported, the
  witness start recorded, the C2 audit passes); a limit never delivers less
  than the witness (a weaker incumbent and none both give way to it; a solver
  error does not); an incumbent failing the optimum's checks (fractional,
  short) fails closed; real HiGHS at a 1e-9 s time limit returns the witness
  with presolve on and off; real HiGHS at `mip_max_nodes=0` returns the
  weakest-three witness start, below the optimum, audited, and with no witness
  `PORTFOLIO_SELECTION_SEARCH_LIMIT`; an illegal roster at each limit still
  blocks a bank that holds the entry count and a witness;
  scripted-optimizer banks that keep three limit rosters, stop on the total
  budget two solves into the fill (`BOUNDED_TIME_LIMIT_STOP`, the host rate
  read as `BANK_REPORT` from its report), stop on each search limit
  (`BOUNDED_SEARCH_LIMIT_STOP`, later strata skipped, the chain still built),
  and still block with two candidates or no witness; a real-HiGHS bank at
  `mip_max_improving_sols=1` keeps `kSolutionLimit` rosters and audits.
  `tests/test_portfolio_enforcement.py` +6: SD3's incumbent at each limit and
  its failed checks; real HiGHS from a feasible start at `mip_max_nodes=0`
  (presolve off: presolve alone solves three candidates); a scripted SD3 bank
  keeping two limit rosters; and `run-slate` on the Showdown fixture with SD3's
  joint model re-solved from its own answer at `mip_max_nodes=0`, a genuine
  kSolutionLimit incumbent, delivered through the Showdown review export with
  `PORTFOLIO_SELECTION_LIMIT_INCUMBENT` as an `S` limitation and the
  independent audit `PASS`.
  `tests/test_classic_review_c3.py` +6: the incumbent accepted and named, the
  over-claimed scope withheld, both stop statuses accepted and named, and the
  card's acceptance through `run-slate` at a node limit and at a real time
  limit (below).

#### Changed

- `test_nonoptimal_and_solver_error_selection_states_fail_closed` is
  deterministic and keeps its three assertions. It no longer builds a real
  bank on `_policy(1)`'s template limits (30 s total, 1.5 s per solve, 10 s
  joint), where one per-solve limit under load blocked the bank before the stub
  ran; it selects from a constructed `ClassicCandidateBank` of four hand-built
  legal rosters. Its stub moved to a shared `_StubHighs`, which records
  `setSolution`.
- Tests the brief listed as asserting that a limit blocks, each checked:
  `test_classic_portfolio_c2.py`'s `test_candidate_timeout_search_limit_and_solver_error_are_distinct`,
  `test_portfolio_enforcement.py`'s bank test, `test_classic_review_c3.py`'s
  `CANDIDATE_BANK_TIMEOUT` and `PORTFOLIO_SELECTION_TIMEOUT` cases, and
  `test_gate_registry.py`'s audit-§4 rows and rung-trigger test all keep their
  assertions unedited, because each models a limit with no roster or no
  incumbent, which still blocks under the same code. `test_deadline_controller.py`'s
  `CANDIDATE_BANK_TIMEOUT` blocker text is still emitted by a blocking bank.
- Docs: `docs/DATA_CONTRACTS.md` (the C2 bank and joint-solve rules, C3's
  publication rule, the SD3 bank and joint solve, the host-rate basis, the
  registry hash), `docs/RUNBOOK.md` (the two "accept only" lines and both
  rung-trigger paragraphs, which now say the two bank codes mean a bank that
  stopped without enough), `docs/OPERATOR_GUIDE.md` (the C2 acceptance line).
  `CLAUDE.md`'s trigger list stays true, since the codes are still emitted
  exactly when the bank blocks, so it is unchanged and this needs no
  `ben-review`. `scripts/make_classic_policy.py`'s printed advice stays true
  for the same reason and is untouched (Session 10's file).

#### Decisions

- A limit-stopped per-candidate roster counts toward its stratum's target like
  any other and is labelled, not counted apart. It satisfies the stratum's hard
  constraints (they are MILP rows); what it lacks is proof that it is the best
  roster for the perturbed objective. Counting it apart would spend more
  solves at the same per-solve limit, which is the time the bank ran short of.
- A limit-stopped bank blocks when it holds fewer than the entry count or no
  `POLICY_FEASIBLE` witness. The witness is computed before the top-k fill, so
  a bank that stops in the fill (the usual place) already has it. New status
  names rather than reusing `CANDIDATE_BANK_TIMEOUT` with a non-blocking flag,
  so the two codes keep meaning "blocking" and `CLAUDE.md`'s rung list stays
  exactly true.
- The witness chain can be the selection. It is the joint solve's MIP start,
  and on a limit the selector returns HiGHS's incumbent or the witness,
  whichever scores higher, so "no incumbent" can happen only without a witness.
  The witness is a feasible point of the final model because every bound counts
  selected lineups and the final bank extends the witness's; the C2 audit
  re-checks it like any selection. The fallback is in the selector rather than
  left to the MIP start because HiGHS drops the start under an early limit with
  presolve off (above).
- An illegal roster the optimizer returns at a limit is now
  `CANDIDATE_BANK_SOLVER_ERROR`, as it already was at `kOptimal`, rather than
  the limit's code: a lower rung does not fix a solver that returns an illegal
  lineup, and a limit code would now let a stopped bank deliver. The adversarial
  review found this.
- One status for C2 and SD3, `FEASIBLE_LIMIT_ACTUAL_CANDIDATE_BANK`, the
  portfolio form of the optimizer's `FEASIBLE_LIMIT`, defined once in
  `optimizer.py`, which both modules already import. No `mip_gap` threshold: it
  is a construction preference, the lock-clock ruling would relax it the moment
  it refused a legal portfolio, and the incumbent is validated legal under
  every bound either way. The gap is reported, and HiGHS reports none (`null`)
  when it stops before a bound exists.
- Limitation class and family: `S`, `search_budget`, whose `covers` already
  named a joint selection hitting its budget. C1's
  `SOLVER_TIME_LIMIT_ACCEPTED_LINEUPS` stays in `selection_claims` (`P`); it
  is not reclassified here.
- The real-HiGHS acceptance uses search limits, since a wall-clock limit on a
  real solve cannot be deterministic: `mip_max_nodes=0` for the joint solve
  and `mip_max_improving_sols=1` for candidate solves, both confirmed above on
  highspy 1.11.0. The time-limit branch is the same code path and is covered by
  the `value_valid=True` stub at `kTimeLimit`.
- `docs/DATA_CONTRACTS.md` records this as new values of existing v1 fields,
  not a new version: no key is added to or removed from
  `nfl_classic_candidate_bank_c2_v1` or the assignment artifact, every value an
  existing artifact can hold keeps its meaning, and a reader that predates the
  change fails closed on the new values (C3 refused every bank status but the
  two completions and every joint status but the optimum). `mip_start` and
  `limit_incumbent_candidates` are report diagnostics, not artifact keys.
- SD3's bank keeps limit-stopped rosters but a stopped SD3 bank still blocks:
  SD3 has no jointly solved witness showing the kept bank can fill the entries.
  Session 10 gives Showdown its ladder. Keeping the rosters goes past the card's
  Classic line reference but is its row's first clause ("validated
  time-limited candidates are kept") in a file it names.
- Files outside the card's and the brief's lists, each for one line of the
  change: `optimizer.py` (the shared status constant, beside the per-lineup
  `FEASIBLE_LIMIT` both modules already import), `readable_review.py` (the HTML
  printed the scope, which is null for an incumbent), `selection.py`'s
  `objective_limits` string (a Target File), and
  `.claude/rules/operating-path.md`, whose "time limits write nothing new" the
  change made false.
- Session 07b's open item, "the generator's 5 s per-solve limit is not scaled
  to a measured rate", closes as a delivery risk: a per-solve limit that
  returns a roster now keeps it and the bank goes on, so it no longer costs a
  rung. Only a per-solve limit that returns nothing still stops the bank, and
  that blocks only without the entry count and a witness. Sizing the limit to
  a measured rate stays a construction preference for Session 10.

#### Verification

- The card's command,
  `sh ./nfl.sh test tests/test_classic_portfolio_c2.py tests/test_portfolio_enforcement.py tests/test_classic_review_c3.py -x --tb=short`:
  `136 passed in 80.33s (0:01:20)` (`128 passed in 73.81s` before the review
  fixes).
- The card's loop,
  `for i in $(seq 20); do sh ./nfl.sh test tests/test_classic_portfolio_c2.py -k nonoptimal -x --tb=short || break; done`:
  20 of 20 runs `12 passed, 34 deselected`, 0.55 to 0.67 s each (and 20 of 20
  at `9 passed` before the review added three).
- Full suite before the change: `1647 passed, 1 skipped in 238.33s (0:03:58)`.
  After: `1677 passed, 1 skipped in 250.76s (0:04:10)` (+30; the skip is the
  Windows junction test), recorded. `doctor` exit 0 (`pass_status: true`), `git diff --check` clean,
  `compileall` of the eight changed modules clean, `check_protected_paths.py`:
  no protected path touched.
- The card's acceptance, `test_run_slate_delivers_a_limited_incumbent_from_a_time_stopped_bank`:
  `run-slate` on the Classic fixture with the template policy at limits no
  small bank reaches, the joint solve on real HiGHS at `mip_max_nodes=0` and,
  separately, at a 1e-9 s time limit (presolve off; with presolve on HiGHS
  solves the one-entry model outright and the node-limit case fails, checked),
  the bank's total budget spent two solves into its fill. Exit 0,
  `PRIOR_ONLY_CLASSIC_C3_REVIEW_EXPORT`, improvement `DELIVERED`, the C3 CSV
  the deliverable, both codes `S` limitations, the export audit's joint record
  `FEASIBLE_LIMIT_ACTUAL_CANDIDATE_BANK` with a null scope, bank
  `BOUNDED_TIME_LIMIT_STOP`, host rate `BANK_REPORT`.

#### Left open

- The adversarial review found one blocking defect (an illegal roster at a
  limit, fixed above) and eight smaller items. Fixed: the card's "time-limited"
  acceptance now also runs on a real 1e-9 s limit; SD3 has an end-to-end test;
  `operating-path.md` and the fails-closed claim corrected; the
  `objective_limits` string; the two tests that built real banks on the
  template's clock limits now use limits no small bank reaches. Recorded
  above: the SD3 bank change and the files outside the lists. Not independently
  verified by the reviewer: the full-suite line and the highspy time-limit
  behaviour, both shown above.
- A stopped SD3 bank still blocks; Session 10 gives Showdown its ladder.
- The C2 witness solve and the final joint solve are separate HiGHS runs;
  when the bank stops before its fill they solve the same candidates twice.
  Harmless (the second starts from the first's answer) and not optimized.

### 2026-09-24: fetches, the weather capture and the policy generator keep the deadline (Session 07b, R31)

Session 07 put one delivery budget through `run-slate` and left three clocks
fixed: 30 s per evidence fetch, the weather capture script's 30 s timeouts and
1 s and 2 s pauses (about 93 s per URL), and the policy generator's 0.28 s per
candidate. Session 07's own draft of this work lived only in its container and
is gone, so this was rebuilt from the card. On
`claude/session-07b-deadline-budget-iwheie`, claim `b213492`. Every run still
ends `PRIOR_ONLY / DO_NOT_UPLOAD`; none of this changes an evidence gate.

#### Added

- `deadline.Budget.fetch_seconds(default, host)`, beside `allowance`:
  `min(default, the improvement window)`, `FETCH_MINIMUM_SECONDS` 1 s. Each
  fetch is its own `evidence_fetch` stage record; a shortened one is named once
  (`DEADLINE_STAGE_SHORTENED`); under 1 s the fetch is refused, its record is
  `SKIPPED` with the moment it was refused, and
  `DEADLINE_FETCH_WINDOW_SPENT:<host>: ...` is emitted through
  `_limitation_event`, once per identical detail.
- `deadline.activated(budget)` and `deadline.active_budget()`, a `ContextVar`.
  `run-slate` wraps `run_prior_review` in it, so `priors.freeze_sources`, which
  takes no budget, reaches the run's budget unchanged.
- `sources.fetch_public_artifact(budget=None)` uses `budget` or the activated
  one; with neither, the fixed 30 s as before. A refusal raises
  `sources.SourceDeadlineError` with the budget's text and starts no client.
  The `httpx.Client` block runs inside `budget.stage("evidence_fetch")`
  (`nullcontext()` without one), so a fetch that raises still records its
  elapsed time and `RAISED`. The client is still built from keyword arguments
  only. `sleeper_daily_player_snapshot` fetches through the same function and
  inherits all of this; nothing in `run-slate` calls it today, and
  `scripts/make_offensive_role_evidence.py` calls the function with no budget,
  so it keeps the fixed 30 s.
- `DEADLINE_FETCH_WINDOW_SPENT` in `delivery_deadline` (`S`,
  `CONSTRUCTION_PREFERENCE`, R31); the family's `covers` names a fetch not
  started. Registry SHA-256 now
  `34ac114d295e4bef5bf633e35ed693a75fb0a8023551fe453bd7a1f3dbac6db3`, 1,205
  codes in 45 families, re-pinned in `tests/test_gate_registry.py` and
  `docs/DATA_CONTRACTS.md`. In `run-slate` a refused fetch surfaces twice, by
  design: `propose`'s broad handler makes it the review's
  `PRIORS_PROPOSE_FAILED:SourceDeadlineError:DEADLINE_FETCH_WINDOW_SPENT:...`
  blocker, and the budget's own event puts `DEADLINE_FETCH_WINDOW_SPENT` on
  `release_truths`; the baseline is the file.
- `scripts/fetch_weather_captures.py`, still standard library:
  `--delivery-deadline-utc` (default the earliest `Game Info` lock minus 5
  minutes, parsed as `nfl_dfs.dk` parses it, through `zoneinfo`); requests stop
  5 minutes before the deadline; each `urlopen` timeout is `min(30, left)` and
  each pause `min(2**n, left)`; under 1 s it exits `FETCH_DEADLINE_REACHED`
  without a request, before it creates a directory when the stop has already
  passed. Its two reserves repeat `deadline.py`'s, and a test holds them equal
  to `HANDOFF_RESERVE` and `finish_reserve(runtime_stop_minutes(runtime.json))`.
  A naive flag value is refused (exit 2).
- `scripts/make_classic_policy.py`: `--delivery-deadline-utc` and
  `--host-rates` (default `data/runs/host_candidate_rates.json`). The rate is
  `deadline.read_candidate_rate(..., mode="CLASSIC")` or 0.28 s. The window is
  built by `deadline.Budget.build` with the stop read from `config/runtime.json`
  through `runtime_stop_minutes`, so the generator and `run-slate` agree on
  when the improvement stops. `_limits(..., seconds_per_candidate,
  window_seconds)` keeps the declared bank budget plus joint solve within 75%
  of the window and the joint solve within 20%, with the 2x generation
  headroom; with no window, or a far one, and the default rate it returns
  exactly what it returned before (857 candidates, 480 s, 20 s at 20 entries).
  When even the floor bank does not fit it writes nothing, exits 2 and names
  rung 4. A request deadline after the earliest lock prints
  `WARNING DEADLINE_AFTER_EARLIEST_LOCK`; an unreadable `runtime.json` fails by
  its own error, not as a flag error.
- `deadline.read_candidate_rate` passes over a rate no bank can be sized from
  (zero, negative, non-finite, boolean), and `_limits` refuses one: a
  hand-edited ledger, or a bank reporting 0 s, no longer divides by zero.
- Tests, all on pinned or injected clocks with stubbed clients, no network:
  `tests/test_deadline_controller.py` +5 (unusable rates passed over; the card's 40 s per failed request in
  a 100 s window gives client timeouts 30, 30, 20 and then a refusal with no
  fourth client; an activated budget read, restored and overridden by an
  explicit one; a passed deadline starts no fetch; a `run-slate` run with
  `build_priors` whose first prior-build fetch is refused, asserting the
  blocker, the `S` limitation and the skipped stage);
  `tests/test_fetch_weather_captures.py` +9 (the card's 45 s stop gives
  timeouts `[30, 14]` and pauses `[1, 0]`; the fixed clocks unchanged without
  a stop; a passed deadline writes nothing; the reserves; the default deadline
  equal to `deadline.default_deadline` on both fixture slates; an explicit and
  a naive flag; no IANA data; an unreadable game time; an AST check that it
  imports only the standard library);
  `tests/test_classic_policy_generator.py` +10 (the card's 48 candidates in
  700 s at 5 s each and a refusal at 600 s; the 20% joint cap; the old numbers
  without a window; `main` reading this host's rate and writing a policy the
  validator accepts; a foreign ledger left alone; exit 2 naming rung 4; a
  closed window and a passed deadline; `runtime.json`'s stop and a naive flag;
  unusable rates refused; the after-lock warning and a broken `runtime.json`;
  a generated 700 s policy against `run-slate`'s own `fits_declared_search`,
  which holds it for 196 s of intake-to-selection and refuses it at 197 s).

#### Changed

- `DEADLINE_POLICY_SEARCH_EXCEEDS_WINDOW`'s detail now says to regenerate the
  policy with `make_classic_policy.py --delivery-deadline-utc <the deadline>`
  first, keeping a smaller `--minutes` for a replay pinned by `--as-of` (the
  generator's window is the wall clock's, so the flag cannot size a pinned
  run). `tests/test_deadline_controller.py` asserted the flag was absent
  because it did not exist yet; that assertion is changed, visibly and on its
  own, to require the flag, this run's deadline and the replay wording.
- `tests/test_deadline_controller.py`'s `_classic` helper takes extra request
  fields, so a run can drop the prior package and set `build_priors`.
- Docs: `docs/DATA_CONTRACTS.md` § Deadline budget (fetch, weather-script and
  generator allowances; `evidence_fetch` back in the stage list; the code; the
  rate ledger's reader), `docs/RUNBOOK.md` (the generator and capture usage,
  and the lock-clock paragraph that said these clocks stayed fixed until
  Session 07b), `IMPLEMENTATION_STATUS.md`. `CLAUDE.md` already says "fetches
  and the generator from 07b" and is unchanged, so this needs no `ben-review`.

#### Decisions

- `activated(budget)` wraps only `run_prior_review`. The session probe is a
  subprocess: a context variable cannot reach it, and its timeout is already
  the budget's `session_probe` allowance.
- The weather script, when it cannot derive a deadline (no IANA data on a bare
  Windows Python, or a `Game Info` time it cannot read), keeps its old fixed
  timeouts and pauses, prints `NO DELIVERY DEADLINE` with the reason, and names
  `--delivery-deadline-utc`. Refusing would cost a capture a real source could
  still give, and `run-slate`'s own budget bounds the delivery either way. It
  never takes the earliest of the times it could read when one cell is
  unreadable, since that cell could be earlier.
- The generator exits 2 and writes nothing when even the floor bank does not
  fit: a floor-bank policy `run-slate` is sure to refuse costs the operator a
  rerun, and rung 4 is the useful answer. A closed improvement window or a
  passed deadline also exits 2 and writes nothing, saying `run-slate` will ship
  the baseline without a review; a replay passes a later
  `--delivery-deadline-utc`.
- 75% of the window, the joint solve at most 20%, and the 2x headroom kept
  even when the rate is this host's own measurement. The slowest of the last
  five banks still comes from other slates, entry counts and rungs; a bank
  timeout costs a rung until Session 08 keeps its incumbents; and a declared
  budget is a ceiling, so a bank that finishes early costs nothing. The other
  25% covers what `run-slate` spends before selection (intake, the baseline's
  30 to 60 s, the probe, priors and evidence).
- A refused fetch gets its own `evidence_fetch` record (`SKIPPED`) as well as
  the limitation, as the probe and the review get theirs when skipped: the
  stage list is the run's timeline, and the record shows where the window ran
  out.

#### Left open

- A fetch's timeout is httpx's per-operation timeout (connect, each read,
  write, pool), as the card defines it, not a total: a large file that
  trickles in, or the GitHub release hop's second request, can run past the
  stop. `finished_late("review")` names a review that ends after the
  deadline. The weather script's `urlopen` timeout has the same property.
- `evidence_fetch` joins the `nfl_deadline_budget_v1` stage names in place;
  the record's fields are unchanged and nothing keys stages by name.
- The generator's 5 s per-solve limit is not scaled to a measured rate
  (Session 08 or 10); `scripts/make_classic_policy.py` still prints and
  documents rung 4 as "the proven floor" that "always produces a legal
  portfolio", which Session 01 corrected elsewhere (Session 10 owns the file's
  ladder).
- The adversarial review of the diff found nothing blocking; its five
  correctness and coverage items are fixed above.

#### Verification

- Baseline before changes on `0af6cd4`: `1621 passed, 1 skipped in 252.00s`.
- The card's command, `sh ./nfl.sh test tests/test_deadline_controller.py
  tests/test_fetch_weather_captures.py tests/test_classic_policy_generator.py
  tests/test_sources_tls.py -x --tb=short`: `75 passed in 10.04s`.
- Complete pinned suite: `1647 passed, 1 skipped in 242.28s (0:04:02)`, 26 more than the baseline (the
  first close-out run, before the review's fixes, was `1642 passed, 1 skipped in 243.58s`). The skip is the Windows junction test.
- `sh ./nfl.sh doctor`: `pass_status: true`. `git diff --check` clean; `compileall` of the
  five changed modules and four test files clean;
  `python3 scripts/check_protected_paths.py`: no protected path.
- `python3 scripts/fetch_weather_captures.py --help` runs on the system Python,
  outside the project environment.

### 2026-09-24: `run-slate` keeps a delivery deadline (Session 07, R31)

R31 sets the default delivery deadline at 5 minutes before the earliest
relevant lock; until now nothing enforced it, and every stage kept its own
fixed clock. On `claude/session-07-deadline-budget-hxfvfa`, claim `dd1203d`.
Every run still ends `PRIOR_ONLY / DO_NOT_UPLOAD`; a deadline is a construction
budget and never withholds a valid file.

#### Added

- `nfl_cowork_run_request_v3`: v2 plus an optional `delivery_deadline_utc`
  (aware ISO-8601, stored in UTC; naive or unparseable refused). v1 and v2
  stay accepted and unchanged; either one carrying the field is refused, naming
  v3. `run-slate --delivery-deadline-utc`. A flag for a later field on a
  reloaded older request writes that run's `run_request.json` at the later
  version (`cowork.request_version_for`); the source file is untouched.
- `src/nfl_dfs/deadline.py`: `earliest_lock` (the one helper; `baseline.py`
  uses it), `default_deadline`, and `Budget`, built once by `run-slate` right
  after intake. The baseline gets `min(60, max(30, seconds to the deadline))`
  with 5 s per solve; the session probe `min(45, 10%)` of the improvement
  window, skipped under 3 s; C1 selection `min(10, window / (lineups + 1))` per
  solve and SD3 `min(scaled, 70%)` bank and `min(scaled, 20%)` joint solve,
  passed through `select_prior_lineups`' existing parameters; a C2 policy's
  hash-bound bank and joint limits fit the window or stop the review. A passed
  deadline or a spent window stops the review before it starts or before
  selection, and the baseline stays the file.
- `nfl_deadline_budget_v1`, the result's `deadline` field on every exit:
  deadline and source, the earliest lock, reserves, both clocks, and one
  measured record per stage (`intake`, `baseline`, `session_probe`,
  `policy_validation`, `selection`, `review`, `finish`).
- `nfl_host_candidate_rate_v1`, `data/runs/host_candidate_rates.json`: after
  every Classic C2 bank `run-slate` records this host's seconds per candidate
  (the bank's own count and time, or a `CANDIDATE_BANK_TIMEOUT` count over its
  declared budget). `deadline.read_candidate_rate` returns the slowest of the
  last five; `make_classic_policy.py` reads it in Session 07b.
- Seven codes. New family `delivery_deadline` (`S`, `CONSTRUCTION_PREFERENCE`,
  RULING R31): `DEADLINE_PASSED_AT_START`, `DEADLINE_IMPROVEMENT_WINDOW_SPENT`,
  `DEADLINE_POLICY_SEARCH_EXCEEDS_WINDOW`, `DEADLINE_STAGE_SHORTENED`,
  `DEADLINE_PASSED_DURING_REVIEW` (a review that ends after the deadline). In
  `certification_prerequisite` (`P`): `DEADLINE_AFTER_EARLIEST_LOCK`,
  `DEADLINE_WALL_CLOCK_PAST_DEADLINE`. Registry SHA-256 now
  `e23f7d7c6f3ad6fc2ca7e04de66ed74a31e52f1d6a92f5da1b96d279a0e953bd`, 1,204
  codes in 45 families, re-pinned in `tests/test_gate_registry.py` and
  `docs/DATA_CONTRACTS.md`. They reach `release_truths` on every exit that
  reports them, each once; the certify exit carries them in its `deadline`.
- `tests/test_deadline_controller.py`, 23 tests (25 cases) on a pinned `as_of` and an
  injected monotonic clock, no network: the default deadline on both fixture
  slates; the runtime key; an explicit deadline, one after lock named; the
  pinned clock; the baseline floor; allowances shorten, then skip, each named
  once; selection limits; the C1 default matches `select_prior_lineups`; no
  deadline code is `V`; the rate ledger and bank observations; and six
  `run-slate` runs: a deadline passed at start (the review never called), a
  slow review that spends the window before selection, a 12 s window that
  shortens C1 and still delivers, a C2 policy that does not fit, a replay that
  records its stages, request v3 and the host rate, a review that ends late,
  a manual certification the deadline does not stop, the outer handler, and a
  budget that cannot be built (malformed, non-finite or unreadable
  `runtime.json`) still shipping the baseline first. Also the keyword mapping
  onto `select_prior_lineups` for C1, SD3 and C2, the baseline limits matching
  the baseline's defaults, and a rate ledger that is deterministic and never
  overwrites a foreign file.
- `tests/test_cowork.py`: v3 carries the deadline in UTC and refuses a naive
  one; v1 and v2 load unchanged and may not carry it; a flag on a reloaded v2
  request writes a v3 run request and leaves the file alone.

#### Changed

- `config/runtime.json`: `stop_discretionary_optimization_minutes_before_lock`
  (10) is read: optimization stops at the deadline less (10 - 5) minutes, so
  lock minus 10 by default with delivery at lock minus 5. It must be at least
  5. `full_refresh_seconds` is removed from both profiles: a fixed refresh cap
  would stop an improvement the deadline still has room for. Still unread, not
  widened here: `candidate_generation_min`, `candidate_generation_max`,
  `candidate_vector_shortlist_max`, `memory_limit_bytes` (`cli.py` reports
  `live_memory_limit()` under that name), `classic.late_swap_seconds`
  (`late_swap.py` reports a measured value under that name).
- `BASELINE_EARLIEST_LOCK_PASSED`'s detail no longer promises Session 07; it
  says the baseline is still built, at its floor under the deadline.
- `cli._session_probe` takes a `timeout`; `_run_release_truths` and
  `_handler_release_truths` take the budget's limitations; `run_prior_review`
  takes `budget`.
- Tests changed as their own visible change. The fixture slates locked on
  2026-09-09 and 2026-09-13, so a run on today's clock is past R31's default
  deadline and correctly skips its review. 37 replay runs therefore name a
  deadline: `REPLAY_DEADLINE` (2099) in `test_prior_review_profile._cowork_args`,
  the same in three `test_cowork.py` runs and one in
  `test_run_slate_baseline_first.py`. One probe stub there accepts the new
  `timeout` keyword. `test_qb_depth_roles.py` expected the emitted version
  `v2`; it now expects `v3` beside `v1` and `v2`.
- `docs/DATA_CONTRACTS.md` (request v3, § Deadline budget, the rate ledger,
  the `run-slate` result), `docs/RUNBOOK.md` (the R31 paragraph),
  `IMPLEMENTATION_STATUS.md`.

#### Decisions

- **Earliest relevant lock:** the earliest `lock_at` among the salary file's
  games. Every contest on a draft group locks at its first kickoff, and every
  blank row a pre-lock run fills is on that draft group (reconciliation ties
  the entries to the salary file), so a template whose entries span contests
  takes the same minimum. Showdown: its one game. Governed late swap is not on
  this path.
- **Explicit deadline:** authoritative, including one after the lock, which is
  named `DEADLINE_AFTER_EARLIEST_LOCK` (`P`) rather than clamped.
- **Baseline floor 30 s, cap 60 s:** five times the slowest measured baseline
  (about 6 s for 150 Showdown lineups, Session 04); the cap is its old fixed
  budget. A deadline passed at start builds it at the floor, skips the review
  and names `DEADLINE_PASSED_AT_START`; `BASELINE_EARLIEST_LOCK_PASSED` still
  fires on its own when the run's clock is past the lock.
- **Split:** the probe is shortened, then skipped (it only reports); solves are
  shortened, then stopped; a hash-bound C2 policy is never mutated, so it fits
  or stops the review. Any cut below a default is named once per stage.
- **Clock:** elapsed time is monotonic. The deadline is compared with the run's
  clock: the pinned `--as-of` advanced by elapsed time, else the wall clock. A
  pinned clock before the deadline with the wall clock past it is named
  `DEADLINE_WALL_CLOCK_PAST_DEADLINE` (`P`, a replay), which answers Session
  06's open question about `--as-of` hiding the lock.
- **Host rate:** `data/runs/` is per machine and never committed, which a
  per-host measurement needs; the slowest of the last five is read, because an
  optimistic rate is what cost the C4 slate its rungs.
- **Exit code:** 2 when the deadline skips or stops the review; it did not
  complete, as Session 06 defined. The pre-review exit's stage is
  `DEADLINE_IMPROVEMENT_SKIPPED`.
- **Flag:** `--delivery-deadline-utc`, the field's own name.
- **Breakpoint taken.** With the fetch, weather-script and generator allowances
  built and tested, the diff was 2,030 changed lines before close-out, past Ben's
  1,500. Following his seam, they were removed and Session 07b holds their
  tested design; the full suite passed with them first
  (`1623 passed, 1 skipped in 226.63s`). `DEADLINE_FETCH_WINDOW_SPENT` goes with
  them.
- **Session 08's files untouched:** budgets reach selection only through
  `select_prior_lineups`' existing parameters, so Session 08 may still run beside
  07b.

#### Left open

- The `diagnostic` and `registered` profiles' build and certify limits: only
  their start is gated by the deadline.
- `priors.py:2398` and `preflight.py:381` still compute a lock inline (Session
  09's and another path's files); `deadline.earliest_lock` is there for them.
- `make_classic_policy.py`'s rung-4 message still says C1 "always produces a
  legal portfolio"; noted, not in scope.
- `CLAUDE.md:123` still says the engine enforces the deadline "from Session
  07"; a separate `ben-review` pull request corrects it.

#### Review

The `reviewer` subagent read `dd1203d..f5e225f`. Fixed:

- **Stale flag.** `DEADLINE_POLICY_SEARCH_EXCEEDS_WINDOW` named a
  `make_classic_policy.py --delivery-deadline-utc` flag that went to Session
  07b. It now says a smaller `--minutes`, or rung 4.
- **Baseline-first gaps.** A budget that failed other than by `ValueError`
  (an unreadable `runtime.json`, a non-finite stop that overflowed
  `timedelta`) skipped the baseline. Any failure now builds it first, and
  `finish_reserve` refuses non-finite values.
- **Late finish.** A review that ends after the deadline is now named
  `DEADLINE_PASSED_DURING_REVIEW`. Its file still replaces the baseline (the
  baseline was on the pointer before it); the rule is recorded here.
- **Manual certification.** The deadline gate stopped a manual-guardrail
  certification, which optimizes nothing. It no longer does.
- **Deadline years.** Deadlines outside the years 2000 to 2999, and ones that
  overflow, are refused as input.
- **Rate ledger.** It never costs a finished review, refuses and leaves a
  foreign file alone, and is deterministic.
- **Duplicate codes.** One cause now gives one code (a stopped selection is no
  longer also a shortened stage), and a probe the environment switched off is
  not named.
- **Detail text.** Deadline limitations carry the same `CODE:detail` text on
  every path.
- **Other fixes.**
  - The `BASELINE_EARLIEST_LOCK_PASSED` detail no longer claims a floor
    budget.
  - The weather word is out of `deadline.py`.
  - The release-truths claim now names the certify exit.
- **Tests.**
  - Selection's shortening is asserted by its own detail.
  - No duplicate limitations are allowed.
  - The baseline's own report proves it ran on the budget's limits.
  - The C1, SD3 and C2 keyword mapping is tested.
  - The handler test pins the wall clock.
  - The baseline constants are pinned to the baseline's own.

Left as is: a v2 request may carry `"delivery_deadline_utc": null`, as v1 may
carry a null `qb_depth_role_evidence_json` (the existing precedent). The
`diagnostic` and `registered` build-and-certify limits stay unbudgeted.

#### Verification

- Baseline before any change: `1593 passed, 1 skipped in 228.99s`.
- The card's command (`tests/test_deadline_controller.py tests/test_cowork.py
  tests/test_fetch_weather_captures.py`): `51 passed, 1 skipped in 10.92s`.
- Complete pinned suite: `1621 passed, 1 skipped in 229.23s` (Linux), 28 more
  than the baseline (25 deadline cases, 3 request). Before the review's fixes:
  `1614 passed, 1 skipped in 227.87s`. Recorded with `record_verify.py`.
- `doctor` passes; `compileall` of every changed module, `git diff --check` and
  `check_protected_paths.py` (no protected path) are clean.

### 2026-09-24: the run's official inactives bind the baseline (Session 06b, R32)

Ben's ruling on Session 06's open question, 2026-09-24: "For the ruling that
needs me do your recommendation." The recommendation: a run's validated
official `INACTIVE` IDs take their people out of the baseline. Recorded as R32
in `docs/ROADMAP.md` §2.5, amending R28's "built only from the DraftKings
salary and entries bytes". On `claude/roadmap-session-06-ond9qs`, claim
`3f4ff04`. Every run still ends `PRIOR_ONLY / DO_NOT_UPLOAD`; activity is not
certified by this.

#### Added

- `baseline.run_baseline(official_status_csv=)`: the file is snapshotted into
  the baseline's `inputs/` and bound in `inputs.official_status`, parsed by
  `evidence.parse_official_inactive_snapshot` (exact current-slate DraftKings
  ID on its own team, `ACTIVE`/`INACTIVE`, public HTTPS source, aware time),
  and every person with an identity-valid `INACTIVE` row leaves the pool, all
  their salary rows included, a row that disagrees with another for the same
  ID included. `baseline.official_inactive_people` does the reading for the
  build and, independently, the audit.
- Five codes: `BASELINE_OFFICIAL_STATUS_ROWS_NOT_APPLIED` and
  `BASELINE_OFFICIAL_STATUS_UNREADABLE` (`official_activity`, `P`: named, the
  baseline still ships); `BASELINE_OFFICIAL_STATUS_CHANGED_DURING_RUN`
  (`delivered_bytes`, `V`) and `BASELINE_AUDIT_OFFICIAL_INACTIVE_PERSON`
  (`audited_selection`, `V`), `CLASSIC_C1_EXPORT_OFFICIAL_STATUS_CHANGED`
  (`delivered_bytes`, `V`: the C1 export's status snapshot is not the one C1
  read). Registry SHA-256 now
  `41f6647ed55527b97e510ac86a9de487c2dc285ab9b9a7157e826d05eaf6ce27`, 1,197
  codes, re-pinned in `tests/test_gate_registry.py` and `docs/DATA_CONTRACTS.md`.
- `nfl_baseline_report_v2`: v1 plus the exclusion fields (`pool`
  `official_status_applied`, `official_inactive_people`,
  `official_status_conflicts`, `official_status_rows_not_applied`, and Session
  06's operator fields) and `inputs.official_status`; audit check
  `NO_OFFICIAL_INACTIVE_PERSON`. Session 06 had added its fields to reports
  still labelled `v1`, against the rule that v1 is never mutated; v2 names them.
- `run-slate` passes its request's official status file to the baseline and to
  the C1 export audit; `nfl baseline --official-status <csv>`.
- Nine cases in `tests/test_run_slate_baseline_first.py`: an `INACTIVE` row
  takes its person out, the file hash-bound; refused rows and an unreadable
  file are named `P` and the baseline still ships; a CSV-reader error is
  named, not a stop; disagreeing rows, and Showdown roles that disagree, take
  the person out and are not counted as refused; a snapshot changed before the
  write withholds; the audit refuses a roster holding an official inactive;
  the C1 export audit reads the run's snapshot, and a snapshot changed after
  C1 falls back to the baseline; the hand-run flag; and the case R32 was ruled
  on, a `run-slate` whose review never finishes, delivering a baseline without
  a player the plain baseline held.

#### Changed

- `OFFICIAL_STATUS_REQUIRED` stays on every baseline (`P`); when a file was
  applied its detail says how many people it took out and that freshness and
  coverage were not judged.
- The baseline's warning, `next` text, `IMPROVEMENT_NOT_DELIVERED` detail and
  `nfl baseline` help now say "less every excluded or officially inactive
  person" instead of "the DraftKings bytes alone".
- `tests/test_baseline.py` expected `nfl_baseline_report_v1`; it now expects
  `v2`, and both names in `docs/DATA_CONTRACTS.md` (a visible change for the
  version bump).
- `docs/DATA_CONTRACTS.md` (baseline section, report fields, `run-slate`
  result), `docs/RUNBOOK.md` (what the baseline honours), `IMPLEMENTATION_STATUS.md`.

#### Decisions

- **Now, not Session 09.** The recommendation put it in Session 09 "once
  activity validation runs before the baseline". The exact-ID parser is local,
  needs no network or model and already guards the model path, so it can run
  before the baseline today, and a slate can run before Session 09 lands. That also makes the
  interim step (name, but still ship, an inactive person) unnecessary.
- **Narrowing only.** The parser's row checks decide what applies; freshness is
  not judged, because an `INACTIVE` row can only remove a player: a stale file
  costs the baseline a player at worst. A row the parser set aside only because
  it disagreed with an earlier row for the same ID still takes its person out,
  as do disagreeing salary roles: disagreement is not a reason to keep a player.
- **Named, never a stop.** A refused row or an unreadable file is `P`: the
  baseline ships without what it could not apply, and says so. Only a snapshot
  that changes mid-run (`V`) or an audit failure (`V`) withholds, like every
  other input binding.

#### Review

The `reviewer` subagent found two blockers, both fixed: a status file the CSV
reader cannot read (a stray quote making one oversized field raises
`_csv.Error`, which is not a `ValueError`) stopped the baseline as
`BASELINE_RUN_FAILED`, and the audit check and the C1 export's use of the file
were untested. Also fixed from its list: an `INACTIVE` row the parser set aside
as a conflict left its person in; Showdown role conflicts were counted as
refused rows; the "bytes alone" wording; a run-slate test whose inactive player
the plain baseline never held; the C1 export not checking the status snapshot's
hash; and the report schema change without a version.

#### Verification

- Card command (`tests/test_run_slate_baseline_first.py`, `tests/test_baseline.py`):
  `61 passed in 33.84s`.
- Complete pinned suite, Linux: `1593 passed, 1 skipped in 204.74s`, recorded
  with `scripts/record_verify.py` (1584 before this session). The skip is the
  Windows junction test. Before the review fixes: `1589 passed, 1 skipped in
  219.98s`.
- `sh ./nfl.sh doctor` passes; `git diff --check` clean; no protected path.

### 2026-09-24: `run-slate` is baseline-first (Session 06)

All of the Session 06 card, both modes, on `claude/roadmap-session-06-ond9qs`,
claim `d869e9f`. R28's running order in the engine: a legal, byte-audited file
built from the DraftKings bytes alone is on the latest-deliverable pointer
before `run-slate` touches the network, a policy, a prior or a solver, and
every exit names the file to hand over. Every run still ends
`PRIOR_ONLY / DO_NOT_UPLOAD`; `DELIVERABLE` is not upload clearance.

#### Added

- `cli._build_run_slate_baseline`: straight after `_intake` and the request
  snapshot, `baseline.run_baseline` into `<output-dir>/<run_id>/baseline/`
  (run id `baseline`) from the run's `data/runs/<run_id>/inputs/` snapshots,
  with the pinned `--as-of` as its clock and the default 5 s per solve and 60 s
  budget, then `delivery.publish` under the `run-slate` run id, producer
  `run-slate:baseline`, `file_kind` `nfl_baseline_entry_csv_v1`. It never
  raises: a crash is `BASELINE_RUN_FAILED`, a publish refusal keeps its codes,
  and the run goes on. The output folder is now created here, before the
  session probe and policy work, instead of after them.
- The improvement goes through `delivery.replace` whenever a pointer exists
  (`publish` only when the baseline did not publish): same input hashes, at
  least as many rows, the same revalidation. Producer
  `run-slate:prior_review:SHOWDOWN`, `:CLASSIC` (C3) or `:CLASSIC_C1`.
- Every exit reads the pointer back (`_read_run_pointer`, renamed from
  `_latest_after_failure` now that success paths use it) and reports:
  `baseline` (what the step did), `improvement` (`DELIVERED`, `WITHHELD` or
  `NOT_PRODUCED`, with stage and reasons), `latest_deliverable`,
  `latest_deliverable_problems`, and `DELIVERY_STATE` and `release_truths`
  describing the pointer's file. When that file is still the baseline,
  `release_truths` is the run's own four v1 truths beside the baseline's
  delivery half plus `IMPROVEMENT_NOT_DELIVERED` (`P`), and `next` opens with
  the baseline's path. The status workbook's Upload sheet names the pointer's
  file on the review and pre-review exits. A review CSV that replaced the
  baseline and then fails the read-back is withheld, and the baseline takes the
  pointer back through `replace`. With no pointer at all, the delivery
  limitations carry the baseline step's problems too.
- The pre-review blocked exit (`cli.py`, doctor, contest or policy blockers, or
  a non-review profile missing its inputs) now carries `release_truths`,
  `DELIVERY_STATE`, `latest_deliverable`, `baseline` and `improvement`. The
  certify path names `baseline`, `latest_deliverable` (as the prior-only
  fallback, with `latest_deliverable_meaning`) and `latest_deliverable_problems`
  beside its own package, outside its release decision.
- C1 (rung 4) exports its own lineups: `_export_classic_c1_csv` hash-checks
  `assignments.csv`, writes the entries snapshot through
  `lineups.write_upload_bytes`, keeps the bytes only after
  `baseline.audit_baseline_bytes` passes the copy on disk (exclusions
  included) and lists `review/DK_REVIEW_ENTRY_C1_<run_id>.csv`, which then
  replaces the baseline like any review CSV. Five refusals, all `V`, list
  nothing and leave the baseline: `CLASSIC_C1_EXPORT_OUTPUT_EXISTS`,
  `_ASSIGNMENT_SHA256_MISMATCH`, `_FAILED`, `_AUDIT_FAILED`,
  `_POST_WRITE_HASH_MISMATCH`.
- `baseline.pool_exclusions` and two `run_baseline`/`audit_baseline_bytes`
  parameters, `operator_excluded_dk_ids` and `extra_unavailable_statuses`
  (details under Decisions), and `nfl baseline --exclude` and
  `--unavailable-status` (repeatable) for a hand-run baseline.
- `tests/test_run_slate_baseline_first.py`, 18 cases: the card's three
  acceptance runs; the pointer already naming the baseline when the probe,
  Classic policy validation and the review start; C3 and C1 replacing it; the
  same bytes giving the same baseline and C1 CSV; a changed C1 assignment, a
  refused C1 audit and an existing C1 output each falling back, the earlier
  output untouched; a `V` display failure withheld with the baseline
  delivered; an improvement that stops revalidating after it replaced the
  baseline, withheld with the baseline restored; the pre-review blocked exit,
  with and without a baseline; a baseline that raises never stopping the run;
  the outer handler after a replacement naming the improvement; exclusions by
  ID, by status and an unknown ID, in the builder, through `run-slate` and by
  hand.
- `config/gate_registry_v1.json`: eight codes, no new family, nothing
  reclassified. `IMPROVEMENT_NOT_DELIVERED` in `stage_failure` (`P`), whose
  `covers` sentence now includes an export and a file the baseline ships in
  place of; `BASELINE_RUN_FAILED` in `delivery_coverage`;
  `BASELINE_AUDIT_OPERATOR_EXCLUDED_PERSON` in `operator_restriction`; the five
  C1 export codes in `no_overwrite`, `audited_selection` and
  `delivered_bytes`. SHA-256 now `ac3d3623...6550d5`, re-pinned in
  `tests/test_gate_registry.py` and `docs/DATA_CONTRACTS.md`.
- `docs/DATA_CONTRACTS.md` § `run-slate` result, baseline first; the C1,
  baseline, v2 truths and pointer sections updated to match.

#### Changed

- `docs/RUNBOOK.md` lock-clock section: `run-slate` builds the baseline itself;
  read `latest_deliverable`, not the exit code; `nfl baseline` by hand only
  when `run-slate` cannot start; rung 4 ends with a CSV.
- `.claude/rules/operating-path.md`: the baseline-first rule for every exit,
  and C1's export. `docs/START_HERE.md` and `docs/OPERATOR_GUIDE.md`: the two
  sentences that still said the baseline waited on this session, or that a
  refused selection leaves no upload-shaped CSV behind.
- Tests whose expectation this ruling changes, edited as visible changes:
  - `tests/test_artifact_preservation.py`: the four withheld run-slate cases
    (Showdown roster code, Showdown unclassified and corrupted, C3 unclassified
    and changed CSV) expected no pointer and `NO_DELIVERABLE`; the baseline is
    now on the pointer, so they assert it names the baseline, never the
    withheld CSV, and the withholding code moved to `improvement.reasons`. The
    C1 half of `test_c3_success_and_c1_exits_report_their_delivery` expected
    `NO_DELIVERABLE`; it now expects C1's own CSV delivered.
  - `tests/test_prior_review_profile.py::test_an_unresolved_available_identity_stops_the_command_with_no_export`
    expected no CSV under the outputs folder; the only CSVs are now the
    baseline's, and it asserts that.
  - `tests/test_classic_prior_review.py`: the C1 run-slate test, renamed
    `..._emits_classic_review_json_a_c1_review_csv_and_no_upload_csv`, expected
    no `DK_REVIEW_ENTRY_*`; it now expects exactly C1's and still no
    `DK_UPLOAD_*`.

#### Decisions (judgment calls, recorded for Ben to overturn)

- **Where the baseline sits, and its names.** `<output-dir>/<run_id>/baseline/`,
  a plain `nfl baseline` run folder with run id `baseline`, so the file is
  `DK_BASELINE_ENTRY_V1_baseline.csv`. The pointer names only files inside the
  run's output folder and `run_baseline` refuses an existing folder, so a
  subfolder is the one place that satisfies both; a run id derived from the
  `run-slate` run id could pass the 80-character limit, and the folder already
  carries that id. The result calls it `baseline`; `latest_deliverable` always
  names the file to hand over, with its `producer`; `bulk_entry_csv` stays the
  review's own CSV (null when withheld); the workbook names the pointer's file.
- **Exit codes unchanged.** 0 when the run's own review completed, 2 when it
  did not, baseline or not. Exit 0 has always meant "review generation
  completed", which is pinned in `CLAUDE.md` and asserted across the suite; a
  new code would overload `nfl baseline`'s 3 (some rows filled). The delivery
  signal is `DELIVERY_STATE` and `latest_deliverable`, and `next` says which
  file ships. A refused C1 export is 2.
- **C1 exports its own lineups** rather than leaving the baseline as the
  deliverable. Rung 4 exists to get the model's portfolio out: C1's lineups
  carry official activity, current roles and the operator's exclusions, which
  the salary-ranked baseline does not, and the export meets the same integrity
  bar as the baseline (the same writer, the same audit, then `replace`'s
  revalidation). The export lives in `cli.py`, not in `prior_review.py`'s C1
  exit, because it needs the run's output folder, the request's exclusions and
  the pointer; `prior_review` stays JSON-only for C1 and its pre-lock manifest
  binds the assignment this CSV renders, not the CSV.
- **A partial improvement never replaces a full baseline.** `replace`'s rule
  stands: while the baseline revalidates, the replacement must deliver at least
  as many rows. The worst outcome is no lineup, so trading filled rows for a
  better model is the wrong direction under a lock clock, and a row-by-row merge
  would be a third portfolio neither side validated for distinctness. Today
  `prior_review` fills every row or fails, so this binds only once Session 11
  delivers partial files.
- **Codes.** `IMPROVEMENT_NOT_DELIVERED` is `P`: it travels with a delivered
  baseline, which a `V` code could not (a `DELIVERABLE` record holds no `V`
  limitation). The review's own `V` codes stay in `improvement.reasons` and
  `blockers`, describing the file that was withheld, not the one delivered.
- **The baseline honours the operator's exclusions** (`baseline.py`, outside
  the card's target list). A baseline that ignored `--exclude` would ship the
  person a late-scratch rerun excludes, which `operator_restriction` classes
  `V`. Exact IDs exclude the whole person, extra unavailable statuses add to
  DraftKings' `OUT`/`IR`/`D`, and `available_statuses` is not read: the
  baseline only narrows. An unknown ID refuses the baseline, as in
  `participation`. Official activity reports are still not read: R28's baseline
  is the DraftKings bytes, and the gap stays named as `OFFICIAL_STATUS_REQUIRED`.

#### Review

The `reviewer` subagent found three blockers, all fixed before the pull
request: the runbook said a hand-run baseline applies exclusions, which it
could not (it now takes `--exclude` and `--unavailable-status`); this entry did
not exist yet; and `DATA_CONTRACTS` promised the new fields on every exit while
the certify exit wrote two (the text now says which exits carry what, and the
certify exit also reports pointer problems). From its open list, fixed: an
improvement that fails the read-back after replacing the baseline reported
`DELIVERED` beside `NO_DELIVERABLE` (now withheld, baseline restored); a failed
baseline was missing from a no-deliverable run's limitations; four untested
paths. The rest is under Found.

#### Verification

- Baseline before any change, fresh `.venv-linux`: `1566 passed, 1 skipped in
  203.62s`.
- Card command (`tests/test_run_slate_baseline_first.py`,
  `tests/test_prior_review_profile.py`, `tests/test_classic_prior_review.py`):
  `79 passed in 21.62s`.
- Complete pinned suite, Linux: `1584 passed, 1 skipped in 209.33s`, recorded
  with `scripts/record_verify.py`. The skip is the Windows junction test.
  An earlier full run, before the review fixes: `1579 passed, 1 skipped in
  202.61s`.
- `sh ./nfl.sh doctor`: `pass_status` true. `compileall` of both changed
  modules and the new test file, `git diff --check` and
  `scripts/check_protected_paths.py` clean.
- Time to baseline inside `run-slate` (default profile, which stops at the
  pre-review blocked exit, on the supplied pools; the baseline's own wall time,
  then the whole command): Classic 1, 20, 150 entries 0.12 s / 1.03 s,
  0.43 s / 1.29 s, 3.47 s / 4.46 s; Showdown 0.12 s / 0.93 s, 0.35 s / 1.19 s,
  6.19 s / 7.04 s. All six `DELIVERABLE`, `RELEASE_DECISION=DO_NOT_UPLOAD`, exit 2.
- `config/gate_registry_v1.json` SHA-256
  `ac3d36234f3cfb9b9320c45b0eaf8e0d6c9d8d5e91b260678d720a5bfe6550d5`, 1,192 codes.

#### Found, left open

- **For Ben:** a run whose official status CSV marks someone `INACTIVE` and
  whose review then blocks (weather, identity) ships the baseline, which reads
  no activity evidence and so can hold that person. It carries
  `OFFICIAL_STATUS_REQUIRED` saying no activity evidence was consulted, which
  is true, but the run did hold evidence. R28's text is "built from the
  DraftKings bytes alone", so this session did not apply it. Recommendation:
  have Session 09 apply the run's validated `INACTIVE` IDs to the baseline as
  an exclusion once activity validation runs before the baseline, and until
  then name, as a limitation, any baseline person the run's validated evidence
  marks inactive.
- `--available-status D` puts a doubtful person back in C1's pool, and the C1
  export's audit, which always treats `OUT`/`IR`/`D` as unavailable, then
  refuses the file (`CLASSIC_C1_EXPORT_AUDIT_FAILED:BASELINE_AUDIT_UNAVAILABLE_PERSON`):
  it fails closed to the baseline, untested.
- The baseline keeps every status other than `OUT`/`IR`/`D` (`Q` included),
  where `participation` refuses a status it does not classify. That is Session
  04's rule; the baseline's `OFFICIAL_STATUS_REQUIRED` detail says which flags
  were applied, so the gap is named, but no code lists those people.
- A pinned `--as-of` earlier than the wall clock suppresses
  `BASELINE_EARLIEST_LOCK_PASSED` on a baseline built after lock; Session 07
  owns the clock.
- No test forces `CLASSIC_C1_EXPORT_POST_WRITE_HASH_MISMATCH` (it needs the
  filesystem to change bytes between the rename and the re-hash).

- A malformed `LATEST_DELIVERABLE.json` (not a stale file: bytes that do not
  parse) refuses both `publish` and `replace`, so the review CSV is withheld and
  nothing is delivered. Only a corruption of a file the run wrote atomically can
  cause it; `delivery.py` is Session 05's contract, left unchanged.
- The C1 pre-lock manifest binds `assignments.csv`, not the exported CSV
  (above); P0b (Session 22) owns run-folder provenance.
- `CLAUDE.md` still says rung 4 is "not a guaranteed file, since C1 writes
  JSON only", that "Classic C1/C2 emit no upload-shaped CSV", and that the
  Classic fallback chain is the nearest thing to baseline-first "until Sessions
  04 and 06 land". It is protected; a separate `ben-review` pull request carries
  the three edits (the third, on C1/C2, follows from the C1 export decision).

### 2026-09-23: a validated CSV survives its readable review (Session 05)

All of the Session 05 card, both modes, on
`claude/session-05-artifact-preservation-3cecn4`, claim `79e9c7f`. R28's
preservation half: a review CSV that passed independent validation is no longer
deleted or orphaned when its readable review fails, and wrong bytes or a wrong
Entry ID mapping are still withheld whatever the failure is called. Every run
still ends `PRIOR_ONLY / DO_NOT_UPLOAD`; `DELIVERABLE` is not upload clearance.

#### Added

- `src/nfl_dfs/delivery.py`: `LATEST_DELIVERABLE.json`
  (`nfl_latest_deliverable_v1`), one per run output folder. `publish`,
  `read_latest` (optionally refusing another run's pointer) and `replace` (same
  inputs, equal or better coverage; a current file that no longer revalidates
  gives way to any that does). Written through a synced temporary file and
  `os.replace`; the same claim and clock give the same bytes. `revalidate` checks the bytes on disk
  from fresh parses of both snapshots: name and folder, truths, file and input
  SHA-256, reparse and mode, Entry ID order, filled and blank rows against the
  truths, `referee.audit_output_bytes`, `validate_lineup`, exact-roster
  distinctness (R29). `discrepancy_limitations`, `blocker_limitations` and
  `withholds` build limitations through the registry, failing closed.
- `classic_review.ClassicReviewPresentationError`, carrying the kept export and
  audit, and `CLASSIC_C3_FINAL_OUTPUT_SHA256_MISMATCH`, a final hash check of
  both on every C3 path.
- `run-slate`'s result: `DELIVERY_STATE`, `release_truths`
  (`nfl_release_truths_v2`) and `latest_deliverable` on every `prior_review`
  exit, and the pointer's hash as `latest_deliverable` in `prior_review_hashes`.
  The outer handler adds the same three, plus `latest_deliverable_problems`.
- `tests/test_artifact_preservation.py`, 37 cases: the pointer's write, read,
  atomic replace, byte-identical rewrite under the same clock, another run's
  pointer, and refusals; five corruptions under the producer's own hash
  (Entry ID, a non-roster byte, a person twice, a repeated lineup, a blanked
  row), each refused; name, folder, input-hash, truths and missing-file
  refusals; seven classification cases; C3 keeping its export and audit on a
  JSON write mismatch and a render exception, and removing everything when the
  export or audit changed during rendering or could not be read back; Showdown and Classic run-slate
  success, a `V` code, an unclassified exception and a corrupted CSV under a
  presentation label, with no record left calling it kept; C3's own failure listed and published; C1 reporting
  `NO_DELIVERABLE`; the outer handler naming the deliverable and removing only
  a stray `DK_UPLOAD`, and naming nothing when the file changed.
- `docs/DATA_CONTRACTS.md` § Latest deliverable pointer.

#### Changed

- `classic_review.py`: the display build, render, JSON and HTML writes and the
  readable post-write check are the presentation phase. A failure there
  re-verifies the export and audit (`_verify_kept_export`: reparse, SHA-256,
  no `DK_UPLOAD`), removes only the JSON and HTML, and raises
  `ClassicReviewPresentationError` with the code, or
  `CLASSIC_C3_READABLE_RENDER_FAILED` for an exception without one. A failure
  before it, or a failed re-verification, removes all four outputs as before.
  The readable post-write check now runs before the final reparse.
- `prior_review.py`, not on the card's list: its C3 branch catches
  `ClassicReviewPresentationError` and lists the kept export and audit, with
  `readable_review_failure` and a `CLASSIC_C3_READABLE_REVIEW_FAILED` blocker.
  Without it the kept CSV would sit on disk in no index, the defect this card
  fixes for Showdown. Session 06 owns the rest of that file.
- `cli.py` run-slate: both readable-review handlers classify each `;`-joined
  code through the registry. Any `V`, unregistered or unparseable code
  withholds (Classic removes its four outputs, Showdown keeps the bytes under
  `withheld_artifacts`, as before). Otherwise the CSV stays in the result and
  both indexes, stage suffix `_READABLE_REVIEW_FAILED`, exit 2, and C3's failed
  JSON and HTML are removed. A kept CSV is published only after
  `delivery.publish` revalidates it, with the pinned `--as-of` as its clock. A
  refusal, or a `V` blocker, withholds it at stage `DELIVERY` in either mode:
  unlisted, kept on disk, never deleted, under `delivery_withheld`. Showdown's
  `READABLE_REVIEW_FAILED.json` is written once that decision is final. The
  workbook names the CSV whenever it is listed.
- `cli.py` outer handler: reads this run's pointer; a file it names that
  revalidates is reported, with `release_truths` carrying the failed run's own
  v1 truths beside the pointer's delivery half. The `DK_UPLOAD_*` sweep is
  unchanged: the pointer can never name such a file.
- `config/gate_registry_v1.json`: 27 codes, one family, nothing reclassified.
  `latest_deliverable` (`V`, contract Latest deliverable pointer) takes the
  pointer's ten own refusals; the other 17 join existing families:
  `delivered_bytes` (8), `entry_authority` (2), `slate_mode`, `roster_legality`,
  `distinct_lineups`, `prohibited_artifact`, `delivery_coverage`
  (`PROFILE_WRITES_NO_ENTRY_FILE`), `gate_registry` (`GATE_CODE_UNCLASSIFIED`)
  and `presentation` (`CLASSIC_C3_READABLE_RENDER_FAILED`, the only new `P`).
  1,184 codes in 44 families. SHA-256
  `b800a8f43adc5f0938940ec75f0c4513a6633361294b3c10b00ec56af9b8ffa9`, re-pinned
  in `tests/test_gate_registry.py` and `docs/DATA_CONTRACTS.md`.
- Two tests, edited visibly because R28 changed their expectation:
  - `tests/test_classic_portfolio_c2.py`:
    `test_c3_readable_reconciliation_failure_removes_new_review_outputs` is now
    `test_c3_readable_reconciliation_failure_keeps_the_validated_csv`. Its forced
    code was unregistered, which now fails closed; it forces the real
    `READABLE_REVIEW_JSON_SHA256_MISMATCH` (`P`) and expects the CSV and audit
    kept, listed and published and the readable files gone. The unregistered
    code, still withholding everything, moved to the new file.
  - `tests/test_cowork_rerun_regressions.py`:
    `test_readable_review_failure_withholds_the_artifact_index_too` is now
    `test_readable_review_presentation_failure_keeps_the_csv_in_both_indexes`,
    forcing `READABLE_REVIEW_POOL_COVERAGE_TOTAL_MISMATCH` (`P`). Its old
    `READABLE_REVIEW_SELECTION_SALARY_MISMATCH` is `V` (audited selection) and
    still withholds; that case moved, unchanged, to the new file.
- `tests/test_repo_boundaries.py`, edited visibly: `DK_UPLOAD_MODULES` gains
  `delivery.py`, which names the prefix only to refuse it. The first full run
  failed `test_dk_upload_is_confined_to_a_pinned_set_of_modules` on exactly
  that, as the test's own message asks a refusal to be recorded.
- `.claude/rules/operating-path.md` and `docs/RUNBOOK.md` step 7: "any byte or
  semantic disagreement does not advertise a new CSV" rewritten to R28's split.
  `docs/DATA_CONTRACTS.md` § C3 and § SD5 say the same, and § Release truths
  says `run-slate` carries v2.

#### Decided, and why

- **Classification**: each `;`-joined fragment by its leading code. Only `S` and
  `P` keep the CSV. A `V` code, one the registry lacks, or an exception with no
  code (`KeyError`, a non-review `ValueError`) is `GATE_CODE_UNCLASSIFIED`, `V`:
  what nobody classified cannot be shown to spare the file. Registered in the
  `gate_registry` family, whose cover already says "a code it does not hold was
  asked for". No existing presentation code moved: the five codes Ben named are
  `V`, and the audit's exposure and overlap mismatches that stay `P` disagree
  about construction preferences, not the bytes, which `delivery.revalidate`
  re-checks on the keep path anyway.
- **C3 is classified by phase, not by code**, because the phase is known: an
  exception after the export and audit passed and before the final checks is
  presentation. It is not trusted alone: the kept pair must re-verify, run-slate
  classifies the recorded code again, and `publish` revalidates the CSV.
- **`FILE_VALID` keeps its v1 meaning**, the export CSV for C3 and Showdown, so
  it is true when the CSV survives and false when it is withheld.
  `delivered_file_valid` equals it on these exits. They would differ only when a
  second file ships, which is Session 06's baseline.
- **Exit code stays 2** on any readable-review failure: review generation did
  not complete. The result's `DELIVERY_STATE` and `latest_deliverable` say a
  file exists.
- **`run-slate` gains `nfl_release_truths_v2` now**, not in Session 06, because
  the pointer carries `DELIVERY_STATE` and the result must say the same thing.
  Blockers become limitations by their leading code; on a real Showdown fixture
  run all six are `P`. C1 and C2 report `NO_DELIVERABLE` with
  `PROFILE_WRITES_NO_ENTRY_FILE` (`V`, `delivery_coverage`) rather than the
  derivation's generic `FILE_VALIDATION_INCOMPLETE`, since their JSON is valid
  and there is simply no entry file.
- **The pointer's location** is the run's output folder, and the file it names
  must sit inside it. Runs are immutable folders; a wider pointer could name
  another slate's file, and two instances would race it.
- **"Passed independent validation earlier in the run"** in the outer handler
  means the run's pointer names the file and it revalidates now. Nothing else
  survives an exception, and the handler never deleted a review CSV before
  either: it removes only `DK_UPLOAD_*.csv`, which run-slate never writes.
- **A withhold at delivery never deletes.** A display `V` code keeps each
  mode's old behaviour (C3 removes its four new outputs, Showdown keeps the bytes
  unlisted). A `publish` refusal can come from a stale pointer or a failed write
  as well as from changed bytes, so it only unlists, in both modes; the
  preserve-bytes boundary favours keeping a file nothing advertises.
- **`certify`'s handler (`cli.py:1177-1180` on `336d078`) is unchanged.** It
  deletes a certified `DK_UPLOAD` whose command did not finish; R28 leaves
  `RELEASE_DECISION` and `CERTIFIED` unchanged, the file is not on the operating
  path, and `delivery.py` refuses `DK_UPLOAD_*` names.
- **Classic C1 and C2 write no upload-shaped CSV**, so of the three
  `prior_review` exits only Showdown and C3 have a file to preserve. C1/C2 gained
  only the v2 truths, with a test.
- **Breakpoint not taken.** The diff is 2,342 changed lines against about
  1,500: 1,128 source and registry, 772 tests, 433 documents with this entry.
  It crossed only when the work was written and green. The seam the card names is not clean: `publish`'s
  revalidation is what makes the keep path fail closed on corrupt bytes, so
  landing preservation without it would advertise unrechecked CSVs in the
  interim, and a Session 05b would pass through `cli.py` again.

#### Review

The `reviewer` subagent read the committed diff (`59f1fcb`). Two blocking
findings, both fixed before this entry:

- A Showdown CSV kept after a display failure and then refused by `publish`
  was still described as kept (`FILE_VALID: true`, `kept_artifacts`) in
  `READABLE_REVIEW_FAILED.json` and `prior_review_reports`. The marker is now
  written after the delivery decision and the record rewritten to withheld; the
  corruption test checks both.
- The pointer writer had no determinism test, and `run-slate` published on the
  wall clock under a pinned `--as-of`. Both fixed.

Open findings, fixed: the handler's `release_truths` contradicted its top-level
`FILE_VALID`; a pointer left by another run in a reused `--output-dir` would have
been read as this run's (`DELIVERY_POINTER_OTHER_RUN`); an `OSError` while
writing the pointer escaped to the outer handler and orphaned the CSV
(`DELIVERY_POINTER_WRITE_FAILED`); an `OSError` while C3 re-verified its kept
pair skipped the cleanup. The handler's check that skipped a pointer-named
`DK_UPLOAD` could never match and is gone.

#### Found, not fixed

- `REVIEW_EXPORT`, the prefix of the Showdown export's blockers
  (`prior_review.py`, `REVIEW_EXPORT:{problem}`), is not registered: the scan
  does not see the generator it is built in. It now classifies as
  `GATE_CODE_UNCLASSIFIED`, which withholds, and that path has no file anyway.
- `certify`'s handler removes `DK_UPLOAD_<run>.csv` but leaves its
  `DK_UPLOAD_<run>.manifest.json`, which still names the removed file.
- `prior_review.json`, written before `run-slate` classifies, still names a C3
  or Showdown CSV that `run-slate` later withholds. It is an immutable run
  record and is not rewritten; `cowork_run.json` is the run's answer. Showdown
  had this before Session 05, and C3 had it for every display failure.
- The C2 half of `prior_review`'s JSON-only export note is unreachable: a
  normalized policy always goes through C3. Only C1 exits there.
- `create_readable_review` writes its JSON and HTML before its own JSON hash
  check and never removes them; Showdown leaves them on disk, unindexed, as
  before (`readable_review.py`, not on the card).

#### Verification

- Baseline before any change: `1529 passed, 1 skipped in 254.46s (0:04:14)`.
- Card command, final tree: `114 passed in 114.74s (0:01:54)`
  (`test_classic_review_c3`, `test_classic_portfolio_c2`,
  `test_cowork_rerun_regressions`, `test_artifact_preservation`). The
  timing-sensitive C2 status test passed on every run; Session 08 still owns it.
- First full suite: `1 failed, 1562 passed, 1 skipped in 264.54s`, the
  `DK_UPLOAD_MODULES` pin above.
- Final full suite: `1566 passed, 1 skipped in 265.80s (0:04:25)`, the skip the
  known junction test; recorded with `scripts/record_verify.py`.
- Two mutations, reverted: `delivery.withholds` returning `False` failed 12
  cases; C3's presentation flag never set failed 5.
- `sh ./nfl.sh doctor` `pass_status: true`; `git diff --check` clean;
  `compileall` of every changed module; `check_protected_paths.py`: no
  protected path.

### 2026-09-23: `nfl baseline`, a file from the DraftKings bytes alone (Session 04)

All of the Session 04 card, Classic and Showdown, on
`claude/session-04-nfl-baseline-f7aptz`, PR #53, claim `795de43`. The baseline
is a new command beside `run-slate`, not in it (Session 06 wires it in). Every
run it makes ends `PRIOR_ONLY / DO_NOT_UPLOAD`; `DELIVERABLE` is not upload
clearance.

#### Added

- `src/nfl_dfs/baseline.py` and `nfl baseline --salaries <csv> --entries <csv>
  [--out-dir] [--run-id] [--per-solve-seconds] [--budget-seconds]`. Binds both
  files by schema, snapshots them under `<out-dir>/<run_id>/inputs/`, parses
  only the snapshots, cross-checks the entries export's player table against
  the salary IDs, excludes `contracts.unavailable_people`, builds distinct
  lineups by `BASELINE_SALARY_RANK_V1`, fills only blank authorized rows through
  `lineups.write_upload_bytes` into `DK_BASELINE_ENTRY_V1_<run_id>.csv`, audits
  the bytes read back from disk against fresh parses, and writes
  `baseline_report.json` with `nfl_release_truths_v2`. Exit 0, 3 (partial, names
  every unfilled Entry ID) or 2. No network, priors, weather or roles.
- `tests/test_baseline.py`, 34 cases: the six acceptance runs, the partial
  pool (Classic, every legal lineup enumerated by brute force) and the Showdown
  captain case (R29), `AvgPointsPerGame` scrambled in both files moving no
  lineup, the prefilled refusal, the mode mismatch, schema binding, the player
  table cross-check, four named salary refusals, the run budget, a copied-
  snapshot replay, a mid-run template change, a corrupted write caught by the
  audit, a reused run folder, registry-built limitations, the objective's
  registration, the writer's `unfilled`, the salary floor, the lock clock, a
  salary file short of the player table, an audit that cannot finish, and the CLI.
- `dk.embedded_pool_ids`: the `ID` column of the player table an entries export
  carries, read and nothing else.
- `LineupOptimizer.set_salary_floor` and `set_random_seed` (`optimizer.py`).
- `write_upload_bytes(..., unfilled=...)`: rows left blank on purpose; every
  authorized row is assigned or listed, never both; a prefilled row refuses
  either way. Existing callers pass nothing and behave as before.
- `docs/DATA_CONTRACTS.md` § Baseline entry file and report:
  `nfl_baseline_entry_csv_v1`, `nfl_baseline_report_v1`, `BASELINE_SALARY_RANK_V1`.
- `docs/RUNBOOK.md` § Shipping under a lock clock: run `baseline` first.

#### Changed

- `dk.py`: every refusal opens with a code (29 `DK_*` codes over 45 raises);
  the prose after it is unchanged.
- `lineups.py`: the validator's ten refusals, the assignment reader's four and
  both writers' refusals open with codes; the prefilled refusal is
  `ENTRY_BLANK_CELL_AUTHORITY_REQUIRED`, its prose unchanged.
- `certification.py`, `review_export.py`: `LINEUP_{entry_id}:` is
  `LINEUP_INVALID:{entry_id}:`, a code a registry can hold.
- `contracts.DeliveryLimitation` refuses `S`/`CERTIFICATION` and
  `P`/`CONSTRUCTION_PREFERENCE`: one mapping, `contracts.GATE_CLASS_STOPS`, is
  also the registry loader's `ALLOWED_PAIRS`.
- `config/gate_registry_v1.json`: 69 codes added (64 `V`, 2 `S`, 3 `P`), no
  existing code moved. 1,157 codes: 427 `V` in 14 families, 71 `S` in 3, 659 `P`
  in 26. SHA-256
  `436931e60f7dca3f7eea8d9577d90e7670dc55301bf4348251edbf373f9ffd73`,
  re-pinned in the test and `docs/DATA_CONTRACTS.md`.
- `tests/test_gate_registry.py`: the scan counts `GateRegistry.limitation` as a
  builder (two shape cases added), the `LINEUP_*` unregistrable pin is gone
  because its emitters are fixed, and the hash is re-pinned.
- `tests/test_certification.py`, edited visibly: the illegal-lineup blocker it
  expects now begins `LINEUP_INVALID:<entry_id>:`, because the emitter changed
  as Session 03b's note asked.
- `tests/test_delivery_state.py`: the two pairs `DeliveryLimitation` now refuses.

#### Decided, and why

- **`BASELINE_SALARY_RANK_V1`** (registered in `baseline.OBJECTIVE` and the
  contract): lineups in non-increasing total salary, each a highest-salary legal
  lineup not already chosen, exact no-good cut against every earlier one. Salary
  is the only number in the DraftKings bytes the engine may read. Solved a level
  at a time: one salary-maximizing solve finds the level, zero-objective solves
  with a salary floor take its other lineups. Measured on the supplied Classic
  pool at 150 entries, re-maximizing salary per lineup took 55.5 s (0.3 s of
  root-node work each); the floor method took 2.95 s. Showdown 11.8 s to 8.0 s.
- **Seed rule.** HiGHS `random_seed` is the number of lineups already built, so
  each solve starts somewhere new. With seed 0 throughout, 7 salary rows sat in
  149 of 150 Classic lineups: legal and distinct, but one scratch would touch
  nearly every entry. With the rule, the most-used person is in 37 of 150 and
  253 people are used, at no cost in time. A usage-penalty tie-break spread it
  to 23 of 150 but took 86.8 s, over the budget; rejected. The seed rule is part
  of the registered objective rather than `config/runtime.json`, because it is a
  function of the lineup index, not a tunable; changing it is a new version.
  Showdown at 150 still has one person in 139 lineups: exactly $50,000 in six
  slots leaves few ways to spend it.
- **Output**: `DK_BASELINE_ENTRY_V1_<run_id>.csv` inside a new run folder
  (default `data/runs/`), `nfl_baseline_entry_csv_v1`. The version is in the
  name so a v2 contract's file cannot be mistaken for it, and the run id makes
  the file identifiable once Ben moves it. Never `DK_UPLOAD_*`.
- **Defaults**: 5 s per solve (slowest measured 1.3 s) and a 60 s run budget from
  the run's start (Classic 150 took 3.6 s, Showdown 150 6.5 s). The audit and
  write after construction always run. A time stop is `S`
  (`BASELINE_RUN_BUDGET_EXHAUSTED`, `BASELINE_SOLVE_LIMIT_WITHOUT_LINEUP`) with
  `UNFILLED_AUTHORIZED_ROWS` naming the rows; a proven exhaustion is `V`
  (`BASELINE_DISTINCT_LINEUPS_EXHAUSTED`, R29) naming them.
- **Three pairs: yes.** The card left it to the first session that emits
  limitations. A hand-built `S`/`CERTIFICATION` limitation would be a preference
  the ladder may not relax, and `P`/`CONSTRUCTION_PREFERENCE` a truth claim it
  could; no test or path built either.
- **Gaps carried, not hidden.** Every run carries `OFFICIAL_STATUS_REQUIRED`,
  `OFFENSIVE_CURRENT_ROLE_UNRESOLVED`, `WEATHER_CAPTURE_REQUIRED` and
  `MODEL_NOT_PROSPECTIVELY_VALIDATED` (`P`), existing codes for exactly those
  gaps, because the baseline consults none of that evidence (R28).
- **Several contests or mixed fees** ship with their existing `P` codes; the
  lineups are distinct across the whole file, which R29 allows and is stricter
  than per contest. Per-contest groups are Session 11's.
- **Prefilled**: one prefilled row withholds the whole file, naming the rows,
  as `prior_review` does today; Session 11 changes that.
- **Exact current-slate IDs**: beyond the salary rows themselves, every salary
  ID must be in the entries export's player table
  (`BASELINE_ENTRY_POOL_ID_MISMATCH`, `V`), which catches a salary file from
  another slate of the same mode. A table ID the salary file lacks can never
  reach a lineup, so it ships as `P`
  `BASELINE_SALARY_FILE_MISSING_ENTRY_TABLE_IDS`, and a template without the
  table ships as `P` `BASELINE_ENTRY_POOL_CROSS_CHECK_UNAVAILABLE`. Both
  supplied Classic exports match all 719 salary IDs.
- **Lock clock not enforced** (Session 07), but never silent: the report and the
  console give `earliest_lock_at`, and a run at or past it carries `P`
  `BASELINE_EARLIEST_LOCK_PASSED`. It is `P`, not `V`, because the engine cannot
  know when Ben uploads, and a lock the run's clock has not reached stops nothing.
- **`optimizer.py` touched** though the card does not list it: two small public
  methods, for the 55 s to 3 s measurement above and the seed rule.
- **Breakpoint not taken.** The diff passed 1,500 lines, but Showdown adds no
  line to `src/`: the builder, writer and audit are mode-agnostic through
  `LineupOptimizer` and `validate_lineup`. Splitting it out would drop about 100
  test lines, add a Showdown refusal for a `04b` to remove, and leave the diff
  over 1,500. The size is the scope beyond the card's list that Ben named (the
  `dk.py`/`lineups.py` codes, the registry, `LINEUP_INVALID`), the contract
  section and the tests.

#### Review

The `reviewer` subagent read `227be41` (`31 passed`) and found nothing
blocking. Its findings, all acted on unless marked:

- **Should-fix, fixed.** `LINEUP_ROSTER_WIDTH_INVALID` was neither registered
  nor visible to the scan (returned inside `ValidationResult`). It is now
  collected like the validator's other refusals, and registered.
- **Fixed.** The order and same-file claims held only while no solve reaches its
  limit; the objective (`time_limits`) and the contract now say so, and
  `time_limited` marks every lineup from the first limited solve on.
- **Fixed.** The lock clock was silent on the console: the summary prints
  `earliest_lock_at` and `checks_not_run`, and a run at or past the earliest
  lock carries `P` `BASELINE_EARLIEST_LOCK_PASSED`. The supplied fixtures'
  games locked on 2026-09-09 and 2026-09-13, so their runs carry it.
- **Fixed.** An exception between the temporary write and the audit verdict
  could leave an unaudited `.tmp`; the copy is now removed on every path, and an
  audit that cannot finish withholds the file as `BASELINE_AUDIT_FAILED`.
- **Fixed.** The runbook said exit 2 always names an integrity gate; a budget
  stop is a construction preference, cleared by rerunning with a larger budget,
  and now says so.
- **Fixed.** The player-table cross-check stopped the file in both directions.
  Only a salary ID the table lacks can reach a lineup the contest refuses, so
  that stays `V`; a table ID the salary file lacks ships as `P`
  `BASELINE_SALARY_FILE_MISSING_ENTRY_TABLE_IDS`.
- **Partly fixed.** `ASSIGNMENT_CSV_EMPTY`, `ASSIGNMENT_HEADER_INVALID` and
  `ASSIGNMENT_ROW_WIDTH_INVALID` move to `audited_selection` beside
  `ASSIGNMENT_WIDTH`. `BASELINE_ENTRY_POOL_CROSS_CHECK_UNAVAILABLE` stays in
  `certification_prerequisite`: a cross-check certification would want is
  missing, and no other `P` family fits better.
- It also ran the real 13-entry Showdown pair in `data/inbox/slates/det-buf-2026-09-17`:
  `DELIVERABLE` in 0.59 s with the several-contest and mixed-fee `P` codes, and
  input hashes unchanged.

#### Verification

- Baseline before any change: `1491 passed, 1 skipped in 174.95s (0:02:54)`.
  The claim commit `795de43` left the queue test red (the Quick-Start still
  named Session 04); `86bb872` fixed it before any code.
- Card command `sh ./nfl.sh test tests/test_baseline.py -x --tb=short`: `34 passed in 15.32s`.
- Fixture runs through `sh ./nfl.sh baseline`, each `DELIVERABLE`, exit 0,
  `FILE_VALID` true, `PRIOR_ONLY`, `DO_NOT_UPLOAD`, carrying the four `P`
  evidence limitations and `BASELINE_EARLIEST_LOCK_PASSED`, and nothing else. Engine wall time from the report, and the whole process:

  | Run | Entries | Engine s | Process s | Output SHA-256 |
  |---|---|---|---|---|
  | Classic | 1 | 0.089 | 0.64 | `249219be44c67bb6b29ee7723299015df37df4a4664efff3069ff60a32ef2729` |
  | Classic | 20 | 0.480 | 1.04 | `9c5bc57ff029de249681ed2b809a8028eea468b273d2ee0107c3aea8695f3978` |
  | Classic | 150 | 3.550 | 4.11 | `3543ddf2ffe6062375c82f793455d66b86fc0f0e22965cf2e83727f05e4d269f` |
  | Showdown | 1 | 0.129 | 0.70 | `71aabb67bf101486c0171bc56400ce5d17584236b34ca94a86f830efe4264b39` |
  | Showdown | 20 | 0.376 | 0.98 | `7d60781e9f056e69f09b34211568d8aad239815baa53b9583cc287273dc0b410` |
  | Showdown | 150 | 6.520 | 7.06 | `265339f170f7e1abbe2b8bc4a8af57c6ce76c1517fb69cd4fd124f26407f0faf` |

  Byte-identical on repeat runs in fresh processes, all six, and unchanged by
  the review fixes. The 20-entry Classic file is the supplied template filled.
- Partial, through the CLI: the ten-person Classic pool with 7 blank rows exits
  3, `DELIVERABLE_PARTIAL`, 5 delivered, unfilled `5300000006` and
  `5300000007`, named by `V` `BASELINE_DISTINCT_LINEUPS_EXHAUSTED`.
- Complete pinned suite: `1529 passed, 1 skipped in 183.69s (0:03:03)`, recorded
  with `scripts/record_verify.py`. The run before the review fixes, on `227be41`:
  `1526 passed, 1 skipped in 183.76s (0:03:03)`; CI on that head green
  (`suite`, `boundaries`, `windows`).
- `doctor` `pass_status: true`; compileall clean on every changed module;
  `git diff --check` clean; no protected path.

### 2026-09-23: R28 absorbs the P1 hard stop (Ben's ruling)

Ben's answer to the Session 09 flag, on `claude/blissful-carson-kzkdcd` after PR
#51 merged as `16502c8`: "Absorb it, per your recommendation." No operating path
changed; the run still stops on the gate until Session 09 makes it an
exclusion. Every run still ends `PRIOR_ONLY / DO_NOT_UPLOAD`.

#### Changed

- `docs/ROADMAP.md` §2.5: R28 now names the 2026-09-19 P1 hard stop among what
  it absorbs. A person in `TRANSFER_PRIOR_UNVERIFIED` who trips
  `SALARY_RANK_DIVERGENCE` is left out of the pool, never selected on the
  old-team share; the file ships and `OFFENSIVE_UNRESOLVED_MATERIAL_ROLE_CHANGE`
  names him. The "still in force" line says so too.
- Session 09's card: the `[BEN: ...]` flag is closed. Its scope gains the
  exclusion, with the runbook's "and stops" (`RUNBOOK.md:889-890`) to change,
  and its must-hold gains "never selected on the old-team share". Its target
  files gain `src/nfl_dfs/offensive_roles.py`, which Session 21 also edits.
- `config/gate_registry_v1.json`: the family `role_change_hard_stop` (`V`,
  `FILE`, ruling "2026-09-19 P1 hard stop") becomes `unresolved_role_change`
  (`P`, `CERTIFICATION`, ruling R28). 363 codes `V` in 14 families, 69 `S` in 3,
  656 `P` in 26. SHA-256 `cfa6fda4d0bd7c2406cde9f853ddce94f6605308f4752e5408dab31fd9d947d1`, re-pinned in the test and
  `docs/DATA_CONTRACTS.md`.
- `tests/test_gate_registry.py`: `test_the_p1_hard_stop_stops_the_file_by_its_ruling`
  becomes `test_r28_absorbs_the_p1_hard_stop`, edited because the ruling changed
  its expectation: the code is `P`, stops certification, cites R28.
- `docs/ROADMAP.md` §4: Session 03b's completion row records its merge, `16502c8`.

#### Verification

- The rewritten test failed on the old registry before the reclassification.
- Card command: `253 passed in 4.82s`.
- Complete pinned suite: `1491 passed, 1 skipped in 159.53s (0:02:39)`, recorded.
- `git diff --check` clean; no protected path (`CLAUDE.md` does not name the
  P1 stop).

### 2026-09-23: the gate registry, every blocker code classified (Session 03b)

All three items of the Session 03b card, on `claude/blissful-carson-kzkdcd`, PR
#51, claim `adc5b99`. No operating path changed and nothing reads the registry
yet (Sessions 04 to 09); every run still ends `PRIOR_ONLY / DO_NOT_UPLOAD`.

#### Added

- `config/gate_registry_v1.json` (`nfl_gate_registry_v1`, SHA-256
  `17e83eabbd40fceb2be2a1ccb512b85e0c3e2f78e41e089074f19f0525729b95`): 1,088 exact codes, one per
  line, in 43 families. 364 codes are `V` (15 families), 69 `S` (3) and 655 `P`
  (25). Two templates whose interpolation the source leaves open list their six
  codes under `expansions`.
- `src/nfl_dfs/gate_registry.py`: `load_gate_registry` (hash, schema, pairs, no
  duplicate key, unknown or unused family, blank provenance, undated
  `registered_at`) and `GateRegistry.limitation`, exact codes only.
- `tests/test_gate_registry.py`, 122 cases beside the 38 R24 ones (unchanged):
  the blocker-literal scan and its shapes, completeness both ways, live pins,
  the class rules, provenance refs resolved against `CLAUDE.md`, §2.5 and the
  contract headings, the `release._integrity` codes matched, the R29, P1 and
  rung-trigger rules, the audit §4 rows, and 28 loader refusals.
- `docs/DATA_CONTRACTS.md` § Gate registry, with its known limits.

#### Decided, and why

- **A blocker literal** is the upper-snake token a string opens with, ending it
  or followed by `:`, in an emitting position: raised; built (`*Error`,
  `_problem`, `_issue`, `QAFinding`, `code=`); collected onto, spread beside or
  assigned to a holder; a `"blockers"` value; a tuple slot named for problems,
  or `reason` beside `BLOCK`; a blocker keyword; compared in a blocking
  function. Interpolations resolve from literal call-site arguments and literal
  loops. It is syntactic, so what it cannot follow is pinned with the source
  text that emits it: 13 codes (two `release._integrity` codes, C2 and SD3
  selection statuses, two referee reasons, the C3 scale replay status).
  Session 03's definition (raise, three collectors, two keywords) missed 44
  real codes, among them the four rung triggers `CLAUDE.md` names.
- **Three pairs only:** `V`/`FILE`, `S`/`CONSTRUCTION_PREFERENCE`,
  `P`/`CERTIFICATION`, one per class of rule in `CLAUDE.md`. An `S` gate that
  stopped certification would be a preference the ladder may not relax; a `P`
  gate that stopped only a preference would be a truth claim the ladder could
  relax. Where the audit says "S/P", the pair decides.
- **`V` means withholding the file, or the rows, keeps the boundary.** So the
  delivered bytes, DraftKings inputs, the assignment, selection and audit
  chain, a policy bound to the wrong entries, exclusions, R29 and overwrite
  are `V`; evidence hashes, source refusals of optional evidence, role,
  activity, weather and model gates are `P`, because the file stays legal
  without them (R28).
- **Exact codes only.** Pattern templates resolved codes nobody registered,
  across classes, so every template is expanded, or listed where it cannot be.
- **The P1 hard stop stays `V`** on Ben's 2026-09-19 ruling, which §2.5 keeps
  in force beside R28. The question is on Session 09's card.
- **The `gate_registry` family is `V`:** a broken registry names no integrity
  gate, so no file can be shown clear of one. The completeness test keeps an
  emitted code from being unregistered.
- **Breakpoint not taken.** The diff passed 1,500 lines, but every module was
  classified, so there was nothing to list as `UNCLASSIFIED` and no `03c` row.
  The size is the one-code-per-line map (1,323 lines) and the scan.

#### Review

The `reviewer` subagent read the first version (`238 passed`).

- **Blocking, fixed.** The scan missed codes in comprehensions, tuple targets,
  aliased holders, spread displays, `"blockers"` keys, helper arguments,
  locals and returned tuples: 44 codes, now registered, with mutation checks.
- **Blocking, fixed.** `INPUT_BINDING`, `OUTPUT_BINDING`, `BUILD_INPUT_HASH_MISMATCH`
  and `BUILD_ASSIGNMENT_HASH_MISMATCH` were `P`; they are `V`.
- **Blocking, fixed.** `SOLVER_RETURNED_NO_LINEUP` and
  `LINEUP_COUNT_BELOW_RESERVED_ENTRIES` are R29 (`V`).
- **Blocking, fixed.** Literal templates such as `CLASSIC_C3_*_*_MISMATCH`
  resolved unregistered codes across classes; removed.
- **Blocking, fixed.** Two `DATA_CONTRACTS.md` sentences overclaimed.
- **Open, fixed.** Participation shortfalls were `S`, which would re-admit
  excluded people; they are `P`. A malformed uniqueness or entry-set field
  stopped the file; it drops the optional policy (`P`), and R29 still holds.
  Loader holes (a list as family, an undated `registered_at`, a blank ref) and
  the unpinned hash are closed.
- **Open, recorded.** The P1 hard stop (above). Four emitters put an Entry ID
  inside the code (`LINEUP_{entry_id}:`, late swap's `{label}_{entry_id}:`) and
  `lineups.py`, `dk.py` and the locked-cell checks raise prose; noted on
  Session 04's card. Audit §4 "S/P" rows cannot catch an S/P swap.

#### Verification

- Baseline before any change: `1368 passed, 1 skipped in 158.42s`, with one
  failure the claim caused (the Quick-Start still named S03b), fixed in `7860dd4`.
- Card command: `253 passed in 4.09s`.
- Complete pinned suite: `1491 passed, 1 skipped in 155.71s (0:02:35)`, recorded with `scripts/record_verify.py`.
  The first version's run was `1476 passed, 1 skipped in 157.48s`.
- Mutation checks, each restored byte for byte: a renamed raise, a renamed
  helper argument, a new loop value, a renamed aliased-holder code, a dropped
  code, a stale code, an R29 code moved to `S`, a weather code moved to `V`, and
  a pinned source line changed; each fails its test.
- `doctor` `pass_status: true`; compileall clean; `git diff --check` clean; no
  protected path.
- CI on `09a6fbe` and on the close-out head `0a7cf77` failed before any step
  ran: no runner assigned, no log, all four checks in 2 to 4 seconds. Re-run
  and `workflow_dispatch` were both refused to this session (403, "Resource not
  accessible by integration"). Commented on PR #51. Ben restored Actions; the
  commit carrying this line ran CI again, and the merge waited for it.

### 2026-09-23: `DELIVERY_STATE`, the fifth truth, and the R24 test (Session 03)

Items 1 and 4 of the Session 03 card, its `DELIVERABLE` and R24 tests, on
`claude/sharp-faraday-wqc7m5`, PR #50, claim `2373057`. The gate registry file,
its loader and completeness test (items 2 and 3a) split to `Session 03b` at the
card's named seam, decided before any registry code: an AST scan finds 805
blocker codes to classify, about 1,000 lines of registry alone. No operating
path changed and nothing emits the new record yet (Sessions 04 to 09); every run
still ends `PRIOR_ONLY / DO_NOT_UPLOAD`.

#### Added

- `contracts.py`: `DeliveryState` (`DELIVERABLE`, `DELIVERABLE_PARTIAL`,
  `NO_DELIVERABLE`), `GateClass` (`V`, `S`, `P`), `GateStops` (`FILE`,
  `CERTIFICATION`, `CONSTRUCTION_PREFERENCE`), `ProvenanceKind`,
  `GateProvenance`, `DeliveryLimitation`, `DeliveryTruth` and
  `ReleaseTruthsV2` (`nfl_release_truths_v2`). The record validators keep the
  coverage invariants however a record is built, deserialized included.
- `release.py`: `derive_delivery_state(file_valid, authorized_entry_ids,
  delivered_entry_ids, limitations)`, with no model or evidence parameter, and
  `release_truths_v2`, which copies the four v1 truths unchanged.
  `derive_release_policy` is untouched.
- Rules: only a `V` gate stops `FILE`, and a `V` gate stops nothing less. A `V`
  limitation without Entry IDs, or naming a row outside the template, covers the
  whole file. An unfilled row nothing names gets `UNFILLED_AUTHORIZED_ROWS`;
  an invalid file, `FILE_VALIDATION_INCOMPLETE`; a template with no blank row,
  `NO_AUTHORIZED_ROWS`. Refusals: `DELIVERY_ENTRY_NOT_AUTHORIZED`,
  `DELIVERY_ENTRY_ID_REPEATED`, `DELIVERY_ENTRY_ID_BLANK`,
  `DELIVERY_ROW_BLOCKED_BY_INTEGRITY_GATE`.
- `tests/test_delivery_state.py`, 93 cases: the three values, integrity
  scoping, an exhaustive check over validity × coverage × 64 limitation sets
  that `DELIVERABLE` occurs exactly when no `V` limitation does, the record's
  own invariants, the class and `stops` rules, independence from every
  evidence, model and basis combination, and the v2 round trip.
- `tests/test_gate_registry.py`, 38 cases, the R24 condition:
  - Weather or a roof value may be read only in named plumbing (the CLI, the
    run request, `prior_review`, `venues`, `certification`, the weather scripts,
    and five weather functions of `priors.py`) and at 10 pinned reads in three
    numeric functions that validate it or copy it into a row. Any other read in
    `src/nfl_dfs/` or `scripts/`, a new module included, fails, and a stale pin
    fails too.
  - A flow-sensitive scan of every function: no arithmetic takes a weather
    value as an operand or index, or runs under a branch or `match` that tests
    one, beyond four named sites (a path join, a tuple join, and the R26
    resolver's two game counts). Mutation snippets for each shape.
  - Every weather state, and the `ROOF_CLOSED` that `resolve_weather_state`
    derives from venue history under `DERIVED_FROM_VENUE_ROOF_HISTORY`, gives
    identical `score_pool` scores and `team_volumes`.
  - Proven on real code: wiring weather into `prior_score.team_volumes`, and a
    weather lookup into `projection._team_rows`, each failed the static and the
    behavioural checks; both edits were reverted, `src/` clean.
- `docs/DATA_CONTRACTS.md` § Release truths: names the existing four-truth
  record `nfl_release_truths_v1` (no byte, field or derivation changes) and
  registers v2, with its does-not-establish line.

#### Changed

- `tests/test_release_truths.py`: extended only, 15 to 18 cases.
- `docs/START_HERE.md` and `.claude/rules/operating-path.md` said the fifth
  truth arrives with Session 03; they now say it has a contract and reaches the
  exits in Sessions 04 to 09. `CLAUDE.md`'s "four independent truths until
  Session 03" is protected and left for the session that first emits it.
- `docs/ROADMAP.md`: `Session 03b` row and card (scanner definition, counts,
  the codes the scan cannot see, the class-pair question); Session 09 now
  depends on 03b, since its limitations take their class from the registry.
  Validator messages that opened with an enum name now open in lowercase, so
  the 03b scan does not count them as codes.

#### Verification

- Baseline before any change: `1235 passed, 1 skipped in 147.96s (0:02:27)`.
- Card command: `149 passed in 2.29s`.
- Complete pinned suite: `1369 passed, 1 skipped in 143.37s (0:02:23)`, 134 above the baseline, recorded with `scripts/record_verify.py`.
  Before the review fixes it was `1346 passed, 1 skipped in 143.19s`.
- `sh ./nfl.sh doctor`: `pass_status: true`. `python -m compileall` on both modules and
  the three test files: clean. `git diff --check`: clean. No protected path.
- Diff: 1,558 changed lines with this entry. The card's one seam was taken;
  the rest is tests (134 cases) and the contract text.

#### Review

The `reviewer` subagent read the diff against the card (`126 passed`).

- **Blocking, fixed.** The R24 scan followed operands only: 12 of 14 realistic
  wirings got through, among them a helper `weather_factor()`, a lookup table
  indexed by weather state, `.get(state, 1.0)`, a `match`, an early return, and
  a helper whose parameter is not named for weather. The pinned-read rule now
  catches all of them, and the arithmetic scan follows lookup keys, `.get`
  keys, `match` and numeric indicators. `IMPLEMENTATION_STATUS.md` had
  overclaimed; it now says what is and is not caught.
- **Blocking, fixed.** v2 tied `FILE_VALID` to delivery, so a valid baseline
  beside a failed improvement (Session 06's case) could not be recorded, and a
  valid `FILE_VALID` could sit beside `FILE_VALIDATION_INCOMPLETE`. `FILE_VALID`
  keeps its v1 meaning; `delivered_file_valid` is the delivered file's own.
- **Blocking, fixed.** A partial record could carry an integrity gate naming a
  row outside the template, which the derivation treats as file-wide. A partial
  record's integrity gates now name only unfilled rows.
- **Open, fixed.** Repeated or blank Entry IDs and people are refused. The S03
  row now lists what landed. The 03b card names the codes built through
  `_integrity()` and the class-pair question.
- **Open, recorded.** The scans cover `src/nfl_dfs/*.py` and `scripts/*.py`.
  Plumbing that turns weather into a number under a name that does not say
  weather is not caught, which is why plumbing is short and named.

#### Decided, and why

- **The split was taken up front**, from a measured count, not after running
  long: classifying 805 codes well is its own session, and the card names that
  seam.
- **`V` ⇔ `FILE`**, stronger than the card's "a `V` gate never has
  `stops=CERTIFICATION`": under R28 a truth-claim gate never stops the file and
  a validity gate is never relaxable.
- **Auto-limitations rather than refusals** for an unexplained gap: a derivation
  that raised at lock time would cost the file.
- **Weather reads are pinned rather than parsed for arithmetic**: an operand
  scan will always leak, and a pinned read list fails on any new shape.
- Nothing was relaxed.

#### Left open

- Session 03b: the registry, its loader and completeness test.
- `CLAUDE.md` "four independent truths until Session 03" (protected).
- Nothing emits `nfl_release_truths_v2` yet.
- `.claude/hooks/guard_bash.py` does not refuse `git add -N .` or `git add . 2>/dev/null`:
  its `git add .` pattern allows no flag before the dot and no redirection after
  it. Found when this session ran `git add -N .` to measure the diff, against
  the rule; it staged nothing, since no file was untracked. Piping both commands
  into the hook exits 0. The fix belongs in its own change with refusal tests in
  `tests/test_repo_boundaries.py`.

### 2026-09-23: four changelog entries to the archive (after Session 02b)

Not a roadmap session: no claim, no status change, no ledger row. The Session
02b entry below named this move and deferred it to its own pull request, so that
diff stayed under the breakpoint.

- `changelog.md` was 904 lines against the ~500 in `.claude/rules/ledger.md`.
  Its four oldest entries (Session 00, Session 01, the Session 01 follow-up and
  Session 02; 480 lines) moved verbatim to
  `docs/changelog-archive/changelog-2026-09-22-cutover-to-2026-09-23.md`. `cmp`
  against `git show HEAD:changelog.md | sed -n 396,875p` found them
  byte-identical, sha256 prefix `7dcc8207d8dc59b1` on both sides. The live file
  is now 447 lines, this entry included.
- The pointer paragraph above the entry template names the new archive file.
- `docs/ROADMAP.md`: a §3 row for the move, and the §4 Session 02b completion
  row records its merge, `d40b686` (PR #48).
- Not done: the remote branch `claude/sharp-faraday-wqc7m5` could not be
  deleted after PR #48 merged; the session's git proxy answered the delete with
  HTTP 403. This pull request reuses it.

### 2026-09-23: the fallback builder names its shortfall, and Showdown QA stops failing on strategy (Session 02b)

Both scope items of the Session 02b card, on `claude/sharp-faraday-wqc7m5`, PR
#48, claim `30da519`. No engine module, contract, evidence gate or release
truth changed. The fallback's output is still `PRIOR_ONLY` / `DO_NOT_UPLOAD`,
with four truths until Session 03. No breakpoint was needed: the diff is
1,479 changed lines, this entry included.

#### Changed: `scripts/build_classic_portfolio.py`

- **Exit codes**, the writer's vocabulary:
  - 0: every blank authorized row has a lineup, and every lineup is distinct.
  - 2: refused by name (`REFUSED <CODE>: ...` on stderr), nothing written.
  - 3: written with a shortfall. `unfilled_entry_ids` lists each blank row with
    no lineup, `shortfall` counts the lineups not built, and stderr names both.
- **R29.** A roster already built, or already prefilled in the template, is
  skipped by exact identity before the overlap check. Before this, a pool with
  two legal lineups returned five, two of them distinct, with exit 0, under
  `--max-overlap 9`.
- **Ratchet** (`next_rung`). Exposure stops at `max(--max-exposure, N)`, as
  Session 02 proposed; `min(EXP + 1, max(EXP + 1, 9))` was always `EXP + 1`.
  Overlap stops at `max(--max-overlap, 6)`: `min(OVL + 1, 6)` pulled
  `--max-overlap 9` down to 6. The bring-back target falls by three to 6 and
  never rises; `max(need_bb - 3, 6)` lifted it from 2 to 6 at N = 4.
  `construction` records the asked and landed caps and `ratchet_steps`.
- **Pool filter.** DraftKings `OUT`, `IR` and `D` rows leave the pool through
  `nfl_dfs.contracts.UNAVAILABLE_DK_STATUSES`; `Q` stays. `--available-status`
  (repeatable) restores a status, as `participation.py:131-137` does for the
  engine, so an engine run with `--available-status D` and this builder agree.
  `construction.dk_status_dropped` counts what left. A status outside the
  engine's vocabulary (blank, `Q`, `OUT`, `IR`, `D`) also leaves the pool, is
  listed in `dk_status_unknown` and named on stderr as `UNKNOWN_DK_STATUS`.
- **Template**, read as `write_dk_entries.parse_template` reads it. Only rows
  whose roster cells are all blank, and wide enough to hold nine, are reserved;
  a narrower blank row is left blank and listed in `unfilled_entry_ids`, as the
  writer lists it. A repeated Entry ID is refused, `DUPLICATE_TEMPLATE_ENTRY_ID`.
  `--lineups` defaults to their count with `--entries`, else 20.
  `ENTRY_ID_SHORTFALL` (more lineups asked than blank rows) now refuses before
  the build instead of after it.
- **Output.** `--out` must be new and none of the inputs (`OUTPUT_EXISTS`,
  `OUTPUT_IS_AN_INPUT`). The bytes go to a temporary file beside it, are re-read,
  then `os.replace`d. A refusal leaves no file and no temporary.
- **Inputs.** The salary file is read by eight named columns, `Status` and
  `Roster Position` among them; `AvgPointsPerGame` is never read. Named
  refusals: `TEMPLATE_UNREADABLE`, `SALARY_UNREADABLE` and `STATUS_UNREADABLE`
  for bytes that are not UTF-8 CSV, `SALARY_COLUMNS_MISSING`, `SALARY_DUPLICATE_ID`, `SALARY_UNREADABLE`,
  `NOT_A_CLASSIC_SALARY_FILE` (a `CPT` row), `NOT_A_CLASSIC_TEMPLATE`,
  `SCORES_UNREADABLE`, `STATUS_COLUMNS_MISSING`, `NO_BLANK_ENTRY_ROWS`,
  `LINEUPS_NOT_POSITIVE` and `EMPTY_POOL`. Each used to be a traceback, a
  silent acceptance or, for the last, `SystemExit` with exit 1.
- The construction algorithm (picks, stacks, bring-backs, anti-correlation) is
  unchanged: the same seed on the same pool draws the same lineups.

#### Changed: `scripts/qa_showdown_portfolio.py`

- `ZERO_QB`, `MULTIPLE_KICKERS`, `MULTIPLE_DST` and `DST_WITH_OWN_OFFENSE` move
  to `OBSERVATIONS`, with a count and an `observation_note`, and never change
  the exit code. DraftKings accepts each. Through its own CLI, the old script
  exited 2 on each of the four test lineups.
- Exit 2 is kept for `INCOMPLETE_ROSTER`, `UNKNOWN_DK_ID`, `SLOT1_NOT_CPT_ROW`,
  `FLEX_SLOT_HAS_CPT_ROW`, `DUPLICATE_PERSON`, `SALARY_CAP_EXCEEDED`,
  `SINGLE_TEAM_LINEUP`, `DUPLICATE_LINEUPS`, the byte and row-count checks,
  `ENTRY_ID_ORDER_OR_COVERAGE_MISMATCH` and `OFFICIALLY_INACTIVE_ROSTERED`.
- `main(argv=None)` returns its code, so the tests call it directly.

#### Tests changed visibly

- `tests/test_build_classic_portfolio.py`:
  - `test_too_few_reserved_entry_ids_is_a_named_stop` (`SystemExit` after the
    build) is now `test_too_few_reserved_entry_ids_is_refused_before_the_build`:
    exit 2, `REFUSED ENTRY_ID_SHORTFALL`, no file.
  - `test_empty_pool_is_a_named_stop` (`SystemExit`) is now
    `test_empty_pool_is_a_named_refusal`: exit 2, `REFUSED EMPTY_POOL`, no file.
  - `run()` gives each call its own `--out`, because the builder now refuses an
    existing one, and asserts exit 0.
  - The fixture's salary rows use real DraftKings roster positions (`QB`, `DST`,
    `RB/FLEX`), not `QB/FLEX`, so the writer can check the builder's output.

#### Added

- `tests/test_build_classic_portfolio.py`, 12 cases before, 48 now: the
  shortfall with and without `--entries`; R29 on a pool with exactly two legal
  lineups; the ratchet ceiling and that it never tightens a cap, end to end
  and on `next_rung` directly; an existing output and an output that is an
  input; the `os.replace` write; `OUT`, `IR` and `D` out of the pool, `Q` in,
  `--available-status D`; blank rows only and the `--lineups` default; a
  prefilled roster never built again (same seed, so the first draw is that
  roster), then accepted by the writer; a byte-determinism test; five damaged
  inputs each withholding the file by name; a Showdown template refused; and,
  from the review, a repeated template Entry ID, a narrow blank row (builder
  and writer both exit 3 naming it), a non-UTF-8 template and an unknown
  DraftKings status.
- The chain, builder then writer then Classic QA: a shortfall exits 3, 3 and 3
  with the same unfilled Entry IDs; and on copies of the supplied 719-row
  Classic salary file and 20-entry template, with synthetic positive scores on
  every row, the builder drops exactly the 33 flagged rows (`IR` 24, `OUT` 8,
  `D` 1), fills all 20 with distinct lineups, and the writer and QA both exit
  0. The old builder rostered flagged players on the same inputs.
- New `tests/test_qa_showdown_portfolio.py`, 22 cases: a clean pass; each
  of the four observations alone and together with exit 0; an observation next
  to a defect (exit 2, both reported apart); a different captain is a
  different lineup (R29); eleven roster and file defects and an officially
  inactive player, each exit 2; and the overlap and backup-pair limits pinned
  at exit 2.

#### Documents

- `docs/RUNBOOK.md`: the fallback listing says what the builder now does, and
  the Running order sentence drops "the builder's own shortfall still exits 0
  until Session 02b".
- `IMPLEMENTATION_STATUS.md`: a capability entry for this session.
- `docs/ROADMAP.md`: Session 02b `Complete`; the card's dated line; ledger rows,
  with Session 02's merge `7c5a45b` filled in; §1 names Session 03.

#### Verification

- Baseline before any change, in a fresh `.venv-linux`:
  `1177 passed, 1 skipped in 143.39s (0:02:23)`.
- The card's command:
  `sh ./nfl.sh test tests/test_build_classic_portfolio.py tests/test_qa_showdown_portfolio.py -x --tb=short`:
  `70 passed in 3.15s`.
- The four fallback and Showdown QA files together: `144 passed in 9.84s`.
- Complete pinned suite on the finished tree: `1235 passed, 1 skipped in 140.84s (0:02:20)`, 58 above the baseline (36 builder cases, 22 Showdown QA cases). Before the review fixes below it was `1231 passed, 1 skipped in 143.16s`. Recorded with
  `scripts/record_verify.py`. The skip is the junction test.
- `sh ./nfl.sh doctor`: `pass_status: true`. `python -m compileall` on both scripts and
  both test files: clean. `git diff --check`: clean.
  `scripts/check_protected_paths.py`: no protected path touched.

#### Review

The `reviewer` subagent read the diff against the card and ran the four
focused files (`140 passed in 10.61s`).

- **Blocking, fixed.** The builder read the template differently from the
  writer. A repeated Entry ID collapsed in a dict, so one lineup vanished and
  one ID was both assigned and listed unfilled; the writer then refused the
  file. A blank row too narrow for nine cells was assigned with exit 0, and the
  writer refused it. Both now behave as the writer does, with a test each.
- **Blocking, fixed.** The new `docs/RUNBOOK.md` sentence said QA refuses a wrong
  input with exit 2. Classic QA exits 1 on a validity failure and 2 only for an
  operator limit, so an operator could have read a valid file's exit 2 as a
  wrong one.
- **Open, fixed.** An unknown DraftKings status entered the pool silently: a row
  flagged `O` with a high score landed in 6 of 8 lineups with exit 0. The
  engine refuses such a code. See "Decided" for why the fallback drops and
  names it instead.
- **Open, fixed.** The same runbook sentence said "drop a rung"; the rung ladder
  belongs to `make_classic_policy.py`, not the builder. It now says to relax an
  exposure or overlap cap, and to ship and name the rows once distinct lineups
  run out.
- **Open, recorded.** The portfolio JSON has no contract (below). With a
  template and zero lineups built, the builder exits 3 and the writer exits 2
  `NO_ASSIGNMENTS`, so the two stages report that case differently.
- It found no weakened test: two renamed, the rest added, and `run()` now
  asserts exit 0.

#### Decided, and why

- **One exit vocabulary for the three stages** (0, 2, 3; QA adds 1 for
  validity). The two `SystemExit` refusals exited 1, which Classic QA uses for a
  validity failure, and a lock-clock operator reads the chain by its codes.
- **`unfilled_entry_ids` counts every blank row without a lineup**, whatever the
  cause, so `--lineups` below the blank count also exits 3. Coverage is
  unconditional in Classic QA since Session 02, and the builder agrees with it.
- **The ratchet fixes went past the one line the card named.** The overlap and
  bring-back steps had the same defect, a relaxation that tightens, and the
  card asked for "a real ratchet ceiling". The attempt budget still bounds the
  walk: at the default 900,000 attempts it takes at most five steps.
- **Refusals the card did not list** (a Showdown salary file, a truncated scores
  file, a repeated or unreadable salary row) follow `.claude/rules/tests.md`:
  each parser gets adversarial cases that yield a named refusal. The Showdown
  salary refusal is the Classic/Showdown mismatch hard stop in `CLAUDE.md`.
- **Showdown QA keeps exit 2 for its operator limits** (`--max-overlap`,
  `--backup-pairs`), as the card notes them out of scope. Its default
  `--max-overlap 4` means a plain run can still exit 2 on a portfolio
  DraftKings would accept.
- **An unknown DraftKings status is dropped and named, not refused.** The engine
  refuses it (`participation.py`), a rule written before R28. For the lock-clock
  fallback, a refusal costs the whole file while dropping the row costs one
  player, and an unclassified player is never rostered either way.
  `--available-status CODE` restores one.
- **A narrow blank row is named, not refused**, because the writer names it too
  and exit 3 ships the other rows.
- Nothing was relaxed.

#### Left open

- Showdown QA's `OVERLAP_*` and `STARTER_WITH_OWN_BACKUP` still exit 2; Classic
  QA gives operator limits their own code. No card owns this yet.
- `scores.json` still omits selection's kicker zero-share and offense
  exclusions (Session 13).
- `assignments_by_entry_id` and the builder's new keys have no contract in
  `docs/DATA_CONTRACTS.md`; the gap predates Session 02.
- `--min-salary` above `--cap` is not refused; it builds nothing and exits 3.
- Zero lineups with a template: builder exit 3, writer exit 2 `NO_ASSIGNMENTS`.
- `changelog.md` is 904 lines with this entry, past the ~500 in
  `.claude/rules/ledger.md` (706 before it). The verbatim move of the oldest
  entries to `docs/changelog-archive/` follows in its own pull request, so this
  diff stays under the breakpoint.
- The first code commit's message (`b05776c`) says the builder file holds 45
  cases; it held 44 then, and 48 after the review fixes.

### 2026-09-23: no plan-approval wait; the plan goes in the task file

Not a roadmap session: no claim, no status change, no ledger row. Ben's
ruling, on the recommendation in the entry below: "Do what you recommend",
then "#1", choosing the option that read "Remove the plan-approval wait from
CLAUDE.md and /dev-session step 6, and update the CLAUDE.md test count."
Touches `CLAUDE.md`, a protected path, so the pull request carries
`ben-review` and Ben merges it.

Why: Ben's 2026-09-20 ruling found that a non-engineer's review of a diff
produces a signature rather than a check, and a plan is the same. The
Quick-Start prompt in `docs/ROADMAP.md` §1 already ran without the wait, so
the two ways into a session disagreed. The plan is still written, to the task
file Ben can read at any point, and the `reviewer` subagent checks scope
against the card before close-out.

#### Changed

- `CLAUDE.md` § Session protocol: "plan mode first" becomes "the plan, with
  assumptions and tradeoffs, goes in the task file and work starts; no
  plan-approval wait". The known-failing-test line gives the current count,
  `1177 passed, 1 skipped`, in three lines instead of four, so the file stays
  at 199 lines.
- `.claude/skills/dev-session/SKILL.md` step 6: write the plan to
  `state/tasks/$ARGUMENTS.md` and start. The one stop left at that step is an
  open `[BEN: ...]` question that blocks the whole card.

#### Not changed

- `.claude/rules/stops-and-reports.md` still defers to any stop `CLAUDE.md` or
  a skill names; none now names the wait. Archived session prompts that say
  "start in plan mode" are history and stay as written.
- The permission classifier refused this change four times before Ben's "#1",
  and after it refused one read-only check on the result; the edits themselves
  went through.

#### Verification

- `sh ./nfl.sh test tests/test_repo_boundaries.py tests/test_roadmap_queue.py tests/test_harness_orientation.py`:
  `204 passed in 1.91s`.
- Complete pinned suite, Linux: `1177 passed, 1 skipped in 153.31s (0:02:33)`,
  recorded with `scripts/record_verify.py`. The skip is the junction test.
- `sh ./nfl.sh doctor`: `pass_status: true`. `git diff --check`: clean.
  `scripts/check_protected_paths.py` flags `CLAUDE.md`, as it should.

### 2026-09-23: every session names its stops, keeps a task file, and reports what Ben owes first

Not a roadmap session: no claim, no status change, no ledger row. A second
review of the Claude Code configuration, at Ben's request, against Anthropic's
prompting guide for the model this repository runs (claude.dev blog,
2026-09-22). The entry below this one covered model inheritance, effort and the
slate-run stops; this one covers what the guide adds: named stops for every
session, a task list in a file that survives compaction, and a final report
that leads with what Ben owes. No engine module, contract, evidence gate,
release truth or protected path changed.

#### Added

- `.claude/rules/stops-and-reports.md`, loaded for every path. When to keep
  going (status goes in the same message as the next command), the four turn
  endings that stall a session, the stops a session does want, the task file,
  and the end-of-run order: **Needs Ben**, **Changed**, **Found**. The four
  endings were in `slate-operation.md` only, which loads for the runbook, the
  operator guide and `scripts/`, so a development session saw them only if it
  happened to read one of those. The list of stops defers to any stop
  `CLAUDE.md` or the running skill names, and says asking never makes a
  permanent boundary or a `git-authority.md` refusal allowed.
- `state/tasks/<SNN>.md`, the task file. Already gitignored by `state/*`.
  `scripts/repo_state.py` gains `task_files()`, and the session-start digest
  lists up to three unfinished ones with their tick counts. The hook runs on
  `compact` and `clear`, so a compacted session is pointed back at its own
  list. It skips a non-regular file (a FIFO would block the hook) and returns
  nothing on a directory error. Nine tests in
  `tests/test_harness_orientation.py`: counting, the finished-list exclusion,
  order, the three-line cap, the `build_state` wiring (a mutation removing it
  fails), and that the directory stays ignored.

#### Changed

- `.claude/rules/slate-operation.md`: the four endings now point at the new
  rule instead of repeating it; the slate's own stops stay, and the handoff
  leads with **Needs Ben**.
- `.claude/skills/onboard/SKILL.md`: "Do not start work until that is said out
  loud" made the orientation report end the turn. The report is now the answer
  when Ben asked only where things stand, and otherwise rides in the same
  message as the first command. The previous review left this for Ben after a
  refusal; this time the edit was allowed.
- `.claude/skills/dev-session/SKILL.md` step 6: the approved plan is copied
  into the task file. The approval wait itself is unchanged (below).
- `.claude/skills/close-out/SKILL.md` step 9: the report opens with **Needs
  Ben** (a `ben-review` label, open `[BEN: ...]` flags) instead of ending on it.
- `.claude/agents/explorer.md`: say what could not be confirmed and where you
  looked, which is the guide's wording for research answers.
- `.claude/skills/verify/SKILL.md`: step 7 ran the complete suite a second
  time only to record it (155 s on Linux, up to 365 s on Windows); it now
  records step 2's log, or `--result-line` on Windows. Step 6 named the Windows
  skip as the only expected one, so a Linux run's junction skip read as a
  finding; it now names both, matching `CLAUDE.md`.
- `docs/CLAUDE_CODE_SETUP.md` § Model and effort: a flagged message can move
  the session to an older model, and subagents inherit it; `/model` switches
  back and `/config` can make it ask first. `/fast` for back-and-forth near a
  lock. Requests to reproduce reasoning in a reply can be declined; none exist
  here.

#### Not changed

- The plan-approval wait (`CLAUDE.md` "plan mode first"; `/dev-session` step
  6). The guide recommends stopping only when a step cannot continue without
  the operator, and Ben's 2026-09-20 ruling found that a non-engineer's review
  of a diff produces a signature rather than a check; the same may hold for a
  plan. Removing the wait was refused by the session's permission classifier
  as self-modification, and so was a first attempt at a line in the new rule
  naming the wait. The fresh-context review then found the rule's closed list
  of stops left the wait out, which would have removed it by implication; the
  list now defers to every stop `CLAUDE.md` or the running skill names. The
  wait stands until Ben rules: `CLAUDE.md` and the skill still require it, and
  plan mode blocks edits mechanically.
- `CLAUDE.md` still gives `1121 passed, 1 skipped` as the Linux count; the
  suite is now larger. It is a protected file, so the count is left for the
  next change that carries `ben-review`.

#### Verification

- `sh ./nfl.sh test tests/test_harness_orientation.py tests/test_repo_boundaries.py tests/test_roadmap_queue.py`:
  `204 passed in 1.41s`.
- Complete pinned suite, Linux: `1177 passed, 1 skipped in 141.05s (0:02:21)`,
  recorded with `scripts/record_verify.py`. The skip is
  `tests/test_cowork.py:115: Windows junction behavior`. The run before the
  review fixes was `1174 passed, 1 skipped in 148.31s`.
- The session-start hook, run offline with a task file present, printed
  `state/tasks/config-review.md: 6/12 done` inside its 60-line budget.
- `sh ./nfl.sh doctor`: `pass_status: true`. `git diff --check`: clean.
  `scripts/check_protected_paths.py`: no protected path touched.
- The `reviewer` subagent reviewed the diff. Its one blocking finding (the
  closed list of stops) is fixed as described under *Not changed*; its
  changelog corrections and test gaps are applied.

### 2026-09-23: subagents follow the session's model; slate runs name the early stops

Not a roadmap session: no claim, no status change, no ledger row. A review of
the repository's Claude Code configuration against Anthropic's current
prompting and effort guidance, at Ben's request. No engine module, contract,
evidence gate or release truth changed. Nothing under `src/` or `scripts/`
calls a model API, so the guidance's API changes have nothing to migrate here.

#### Changed

- `.claude/agents/explorer.md`, `.claude/agents/reviewer.md`: the fixed model
  pin is replaced by `model: inherit`, so both run on the model Ben chose for
  the session. `explorer` declares `effort: low`, the level the effort guide
  lists for subagents; `reviewer` runs at the session's level.
- `.claude/rules/slate-operation.md`: *Measure the clock* now puts the measured
  minutes to the delivery deadline (R31) in every progress note, re-measured at
  each stage boundary. *Decide what is yours to decide* names four turn endings
  that stall a run while Ben is away, the 2026-09-20 question among them, and
  the three stops a run does want.
- `docs/CLAUDE_CODE_SETUP.md`: a *Model and effort* section (nothing pins a
  model or effort; subagents inherit; thinking is always on, so effort is the
  control; stay at the default for slates). *The protected list* section still
  described the twelve-entry list and said `.claude/rules/*.md` was protected,
  which contradicted the top of the same file and `git-authority.md`; it now
  describes the three entries.

#### Not changed

- `CLAUDE.md` and `.claude/settings.json`. Neither conflicts with the guidance:
  verification here means pasted evidence, which the guidance keeps; no
  "think carefully" or "double-check your answer" line exists in `.claude/` or
  `CLAUDE.md`; plan mode first for multi-file work is a defined check-in, not
  an early stop.
- `.claude/skills/onboard/SKILL.md`. Its last line, "Do not start work until
  that is said out loud", invites a turn that ends on the orientation report.
  The replacement was refused by the session's permission classifier as
  self-modification and is left for Ben.
- `docs/CLAUDE_CODE_SETUP.md` still gives `1070 passed, 1 skipped` as the
  Windows result, below the Linux count in `CLAUDE.md`. Left as is: the current
  Windows count was not measured here.

#### Verification

- `sh ./nfl.sh test tests/test_roadmap_queue.py tests/test_repo_boundaries.py`:
  `149 passed in 1.94s`.
- Complete pinned suite, Linux: `1168 passed, 1 skipped in 164.00s (0:02:43)`,
  recorded with `scripts/record_verify.py`. The skip is the junction test.
- `sh ./nfl.sh doctor`: `pass_status: true`. `git diff --check`: clean.
  `scripts/check_protected_paths.py`: no protected path touched.

Entries from the 2026-09-22 roadmap cutover (Session 00) to Session 02 on 2026-09-23 moved verbatim to `docs/changelog-archive/changelog-2026-09-22-cutover-to-2026-09-23.md` on 2026-09-23; entries dated 2026-09-22 before the roadmap cutover moved verbatim to `docs/changelog-archive/changelog-2026-09-22.md` on 2026-09-23; entries dated 2026-09-14 to 2026-09-21 moved verbatim to `docs/changelog-archive/changelog-2026-09-14-through-2026-09-21.md` on 2026-09-22; entries dated 2026-09-14 (follow-up and checklist) and earlier, back to 2026-09-01, moved to `docs/changelog-archive/changelog-through-2026-09-14.md` on 2026-09-15. Append new entries directly under `## Unreleased`; when this file passes roughly 500 lines, move the oldest entries to the archive rather than letting sessions read them.

## Entry template for future sessions

Copy this structure under `Unreleased` and replace every placeholder:

```markdown
### YYYY-MM-DD: short outcome (Session NN)

Changed:

- Exact behavior changed and files involved.

Verification:

- Exact command or check: exact result.
- Full suite: exact pass/fail count.
- `git diff --check`: pass/fail.

Remaining blockers:

- Named blocker, or `None for this backlog item`.

Tracker updates:

- `docs/ROADMAP.md` §2.2: Session NN `In Progress` -> `Complete` (or back to `Pending`), with a §4 ledger row.
- §1 Quick-Start rewritten to the next startable session, only if its dependencies and acceptance gates genuinely passed.

Claims explicitly not made:

- No live-slate, calibrated-EV, or upload-readiness claim unless independently proven by the work recorded here.
```
