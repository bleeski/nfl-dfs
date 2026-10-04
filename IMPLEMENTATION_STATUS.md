# Implementation Status

## Capability added: 2026-10-04 (Session 56, concentration defaults in the engine)

Working and verified through synthetic fixtures (`tests/test_concentration_defaults.py`, `test_concentration_ladder.py`,
`test_concentration_run_slate.py`, `test_concentration_counterexample.py`), the review's own counterexample, a mutation pass and the full
suite: one registered default set (`config/showdown_concentration_defaults_v1.json`: no person above 0.60 of the lineups, no Captain above
0.20, overlap 4) is read by `scripts/make_showdown_policy.py` and applied by `run-slate` to a Showdown run that supplied no policy, as a
hash-bound policy through the existing SD3 bank, joint solve and independent audit of the delivered bytes. The ladder gives the caps way by name
(0.80 and 0.40, then rung 4 for the engine's own default; also `CAPS_OFF` for a generated policy at the default pair) before any structural rung,
carries a relaxed cap forward, and a window that cannot hold the capped search starts at rung 4. The result's `concentration` block reports
requested and effective caps, the steps, and the delivered file's own counts recomputed from its bytes. It never adds a stop: whatever keeps it
from applying is a named `SHOWDOWN_CONCENTRATION_NOT_APPLIED` limitation and the run is what it was before. **Not done, named:** under five
entries the default binds nothing (reported, not applied); a small portfolio's scaled bank can be too shallow to keep 0.60/0.20 (the ladder
relaxes to 0.80/0.40 by name); the by-hand rotation in `docs/claude/working.md` stays for what the pool cannot meet; no full `run-slate` replay of
a real slate was run. Still `MODEL_STATUS=PRIOR_ONLY`, `RELEASE_DECISION=DO_NOT_UPLOAD`.

## Capability added: 2026-10-02 (Session 54, a depth-declared starter with no usable history is selectable)

Working and verified through synthetic fixtures (`tests/test_declared_starter_selectable.py`, 18 tests), a `run-slate` replay of PIT@CLE on its
saved frozen package (Watson scored, in 10 of 22 rows, Captain once) and the full suite: a quarterback the QB depth evidence declares the
starter, with no prior-season row and no current-season rate, is selectable as a `DIAGNOSTIC` on the depth resolution's attempt share, carry and
target shares zero (`src/nfl_dfs/offensive_roles.py`, `selection.py`). Participation precedence, backups, non-quarterbacks and a zero share still
exclude, and so does a hash-bound fact that calls him a backup or says his role changed. A backup R25 promotes over a DraftKings-unavailable
starter is the effective starter and is selectable. This closes the Keenum and Watson misses for a declared starter. **Not done, named:** a person no source declares (a same-day
promotion the chart has not caught) is Session 52; on the replay Rodgers is in every row and Fannin in 91%, so concentration is still manual until
Session 52. Still `MODEL_STATUS=PRIOR_ONLY`, `RELEASE_DECISION=DO_NOT_UPLOAD`.

## Capability added: 2026-10-02 (Session 53, backup-quarterback default and the depth package captured by `run-slate`)

Working and verified through synthetic fixtures (`tests/test_qb_depth_capture.py`, `tests/test_showdown_backup_qb_default.py`, `tests/test_prior_review_depth_capture.py`, 44 tests), a
`run-slate` replay of PIT@CLE on its saved frozen package (`--as-of` before lock; the 22 exported rows hold no backup quarterback) and the
full suite: for a Showdown run with no supplied package, `run-slate` builds the QB depth package from the `depth_charts` bytes the prior
package already froze (`src/nfl_dfs/qb_depth_capture.py`), and every Showdown selection, with or without a policy or thesis, keeps every
quarterback behind the resolver's effective starter out of every row (`selection.py`). This closes Session 51's "run-slate does not
capture the QB depth package". A stale, refused or missing chart, and a team the chart does not declare, are named `P` limitations
(`QB_DEPTH_CAPTURE_*`, `SHOWDOWN_BACKUP_QB_UNEVALUATED`) and never stop a run. When R25 refuses one team's evidence (an operator excluded a
starter DraftKings still lists as available), that team alone is dropped and named; the other team keeps the default.
**Not done, named:** the chart does not say the starter is playing (official activity is a separate gate); a starter with no row anywhere
is Session 54; the concentration and left-out-starter judgment is manual until Session 52 (on the PIT@CLE replay Fannin and Rodgers are each
in 91% of rows and Watson in none). Still `MODEL_STATUS=PRIOR_ONLY`, `RELEASE_DECISION=DO_NOT_UPLOAD`.

## Capability added: 2026-10-01 (Session 51, in-season gap-fill for the player prior)

Working and verified through synthetic fixtures (`tests/test_prior_current_season_gap_fill.py`, 29 tests), a records-level replay of PIT@CLE
on the real frozen inputs and the real 2026 weeks 1 to 3, and the full suite: a new prior freeze writes player transformation v3 by
default (`src/nfl_dfs/priors.py`). A person v2 cannot rate (no prior-season row, a historically zero person, a transfer with rows on his
new team) is rated from this season's current-team rows played before the slate's week, from an optional nflverse in-season source;
everyone else keeps v2's per-game rate, and with no usable in-season file every record equals v2's. A row at or after the slate's week
is never read, a team missing a completed game falls back to v2 by name, and a thin-sample value that cannot be taken from the rows is
refused by name rather than clamped or allowed to fail the build. On the replay Watson, Boston and Concepcion are rated and selectable.
**Not done, named:** `run-slate` does not capture the QB depth package, so a benched backup's rate persists unless one is passed;
the judgment input for people no source can rate is Session 52; no recency weight, no calibration; a player traded in 2026 with no
rows yet on his new team is unchanged. Still `MODEL_STATUS=PRIOR_ONLY`, `RELEASE_DECISION=DO_NOT_UPLOAD`.

## Capability added: 2026-10-01 (Session 23b, Showdown thesis structures)

Working and verified through the synthetic NE@SEA and DEN@KC Showdown fixtures and the supplied NE@SEA 20-entry bytes
(`tests/test_showdown_theses.py`, 32 tests, 31 of which fail on the code before it) and the full suite: a Showdown policy
can carry one named game thesis Ben chooses (`nfl_showdown_portfolio_policy_v3`, `controls.theses`;
`src/nfl_dfs/showdown_theses.py`, `showdown_single_thesis_sd3_v1`). Its Captain set (kickers and DSTs included), team and
position counts and exclusions are MILP rows and excluded rows on every SD3 stratum, the SD4 audit recomputes each from
the roster bytes, and each bound Entry ID names its thesis in the selection and audit reports. The ladder never loosens
it: every rung carries it byte for byte and a rung that changes it is refused; caps that starve it loosen instead. A
thesis no lineup can follow (an inactive required Captain, at validation; any proved infeasibility, at selection) is
dropped and named (`THESIS_DROPPED`, by the ladder from the policy itself) and the policy builds without it. Under a thesis, quarterbacks the depth evidence
puts behind a starter are out unless the thesis names them; a team with no depth evidence keeps every quarterback and
the gap is named (`THESIS_BACKUP_QB_UNEVALUATED`). **Not done, named:** one thesis per policy (the multi-thesis
portfolio is Session 23c); rows the unbound fill writes follow no thesis; rung 4 (sequential Showdown) carries no
thesis, so a thesis that survives the pre-check but cannot fill every row distinctly is dropped there by name; the
backup-quarterback default applies only under a thesis (`[BEN: ...]` flag on the 23b card); the review workbook and
readable review do not show the thesis yet (23c). Still `MODEL_STATUS=PRIOR_ONLY`, `RELEASE_DECISION=DO_NOT_UPLOAD`.

## Capability added: 2026-09-30 (Session 49, thesis builder as the rung-4 path)

Working and verified through the Classic fixtures (`tests/test_classic_theses.py`, the rung-4 and no-policy `run-slate`
runs on a four-team pool wide enough to hold the cap, and `tests/test_relaxation_controller.py`) and the full suite:
Classic rung 4 (no policy in force: the ladder's floor, or a `run-slate` that supplied none) no longer repeats one
construction. `src/nfl_dfs/classic_theses.py` (`classic_thesis_sequential_v1`) builds rows as several stack theses, one per
primary stack team ranked from the run's own prior objective, each with its QB from that team, a teammate WR/TE and a
bring-back, round robin under one person cap (40% of the rows) and the Session 39 overlap cap, every earlier row and
prefilled roster cut exactly (R29). On a 266-player synthetic pool the 150-row build took 64 s with nobody over 40% and
150 of 150 stacked; plain C1 took 508 s with a person in 88% of the rows and 61 of 150 stacked. Preferences relax in a
reported order (bring-back, the shared overlap cap, the person share, then the stack) and a run that cannot build row k
delivers the k rows and names the rest as `unfilled_entry_ids`. **Not done, named:** a short thesis file cannot replace a
fuller baseline (`DELIVERY_POINTER_COVERAGE_REGRESSION`), so a rung 4 that stops short still leaves the baseline the
file, with the gap named; a composite of thesis rows and baseline rows is not built. The theses are team stacks only: the
operator script's market-total flips, bust overrides and salary-ranked fade need inputs the run does not have. The
subset-policy unbound fill, `run_prior_review` called directly (its default stays C1) and Showdown rung 4 are unchanged. Still
`MODEL_STATUS=PRIOR_ONLY`, `RELEASE_DECISION=DO_NOT_UPLOAD`.

## Capability added: 2026-09-30 (Session 39b, partial fill)

Working and verified through the Showdown and Classic fixtures (`tests/test_partial_fill.py`, a real infeasible-pool stop
in `tests/test_portfolio_policy.py` and `tests/test_classic_diversification.py`) and the full suite: a subset policy's
unbound fill that runs out of distinct lineups at row k returns the k rows it built instead of raising
`SOLVER_RETURNED_NO_LINEUP`; `prior_review` names the unbound Entry IDs left (template order, the last ones), builds
`assignments` for the bound rows and the k filled rows only (`assignments_for_entries`, which cycles, stays on the
no-policy path), and every layer takes the named gap: `exact_assignments_for_entries`, the SD3 and C2 audits, the
Showdown export writer, C3, the readable review and the review's release truths (`unfilled_entry_ids`,
`DELIVERY_STATE=DELIVERABLE_PARTIAL`, a `SOLVER_RETURNED_NO_LINEUP` limitation scoped to those rows). A blank row nobody
named still fails each layer. C3 and the readable review now also re-check that a fill row holds no person the policy
excludes, and C3 that it shares no more people than the cap the record names with each policy lineup and each other
fill row. **Not done, named:** the run-level pointer never regresses coverage, so a partial review does not replace a
baseline that fills more rows (`DELIVERY_POINTER_COVERAGE_REGRESSION`); it is kept in the run's `review` folder. Showdown
fill rows are capped only among themselves (the selector anchors only Classic fill rows to the policy's lineups). A fill
solve that ended without a roster and without proof (a time limit) is delivered as a partial fill and says so.
Sequential selection with no policy (C1 with no fill, rung 4) still raises when it runs out. Still
`MODEL_STATUS=PRIOR_ONLY`, `RELEASE_DECISION=DO_NOT_UPLOAD`.

## Capability added: 2026-09-30 (Session 39, Classic diversification)

Working and verified through the Classic fixture, unit tests on the C2 fixture, and the full suite: Classic C1 and
the rows a subset policy leaves unbound share at most 6 people with each earlier row (and a fill row with each policy
lineup), the cap stepping up one person at a time, on a proven infeasible model only, to 8 and staying there, each step
reported (selection report, the ladder record as `OVERLAP_CAP`, or a limitation for a run with no ladder); the C2
witness chain round-robins the MILP seeds and slots and holds the policy's pairwise overlap (20 of 20 at overlaps 4
to 9, 150 of 150 at 3 to 9 on the fixture), where the old chain never gave a feasible witness at 7 or below; the fill
applies the policy's own exact exclusions and zero caps. C1's selection profile is
`prior_only_classic_selection_c1_v2`; `C2_FULL_FILLABLE_SHA256` moved on purpose. **Not done, named:** the partial
fill (a fill that runs out at row k delivering k rows and naming the rest) is Session 39b; until then it still
raises `SOLVER_RETURNED_NO_LINEUP` and the baseline is the file. No review layer re-checks the policy's exclusions on
fill rows (39b). Still `MODEL_STATUS=PRIOR_ONLY`, `RELEASE_DECISION=DO_NOT_UPLOAD`.

## Capability added: 2026-09-29 (Session 17, standings corpus transport)

Working and verified against a fixture transport only: `scripts/fetch_standings_corpus.py fetch` brings
the standings exports from a private repository's release into `data/standings/inbox/` through
authenticated GitHub API retrieval, binds each to a committed manifest's sha256 and byte count, refuses a
mismatch (no partial file remains), never replaces an existing inbox file, and writes an
`nfl_standings_transport_v1` record. The token is never printed, recorded or raised, and
`Authorization` reaches only `api.github.com`, never the signed CDN hop. Also verified live on
2026-09-29 (read-only, scratch directory): the new client authenticates through the cloud proxy, refuses
`bleeski/nfl-dfs` because it is public, and gets a 404 for a release that does not exist.
**Not done, named:** no release exists (`list_releases` returned `[]` on 2026-09-29) and no manifest is
committed, so the real corpus has not been fetched, and `P0` cannot yet run in a cloud session (Session 17b,
O1). The repository is public, so the release must live in a private repository (`[BEN: ...]`). Still
`MODEL_STATUS=PRIOR_ONLY`, `RELEASE_DECISION=DO_NOT_UPLOAD`.

## Capability added: 2026-09-29 (Session 48, depth-chart QB transfer starter)

Working and verified: a declared rank-1 quarterback whose team had no allocated quarterback
pool now receives the whole pool (1.0) under `qb_depth_chart_order_v2`, where v1 left him at zero
(fixture: KC starter 0.0 on the unfixed code, 1.0 with v2, the same as DEN's starter). His carried
prior-team share never changes the number (0.0, 0.3, 0.9 and 1.0 all give 1.0). The manifest's
version pair selects the rule; frozen v1 manifests are read as written and name the gap under
`declared_starters_without_allocated_pool`; the producer writes v2 by default. A model whose team
pool is neither empty nor 1.0 is refused (`QB_DEPTH_POOL_NOT_UNIT`). Not fixed, named: a
declared starter with no history is still excluded by the offensive role gate
(`MISSING_HISTORY`, `OWN_OLD_TEAM_SHARE_ZERO`), and a transfer starter's carry share is still his
old-team history. No live slate has run under v2. Still `MODEL_STATUS=PRIOR_ONLY`,
`RELEASE_DECISION=DO_NOT_UPLOAD`.

## Capability added: 2026-09-29 (Session 21, per-game prior shares, transfer pool, alternate-name proposals)

Working and verified: a new prior freeze writes player transformation v2 by default. Each
person's prior-season counts on his current team become a per-game rate over the weeks he has
a stats row (denominator floored at `MINIMUM_PRIOR_GAMES`, 4) before the pool is normalized, so a
player who missed games projects at his per-game rate and his teammates' shares no longer absorb
them (fixture: a receiver with 8 of 16 games and one with 16 both at ten targets a game get equal
weights; v1 gave the first half). A transfer's pseudo-rate scales by the current team's per-game
total, so a thin room no longer holds a transfer starter to `s / (1 + s)` of the group. v1 stays
selectable (`--player-transformation`) and reproduces its bytes; frozen v1 packages are read as
written. F8 proposes same-team matches from `first_name`/`last_name`/`football_name` and
accent-folded forms for review; they are never resolved, never auto-accepted and never reach a
runtime join. Not verified: any calibration of the rate or the floor (`does_not_establish`), and no
live slate has run under v2. Still `MODEL_STATUS=PRIOR_ONLY`, `RELEASE_DECISION=DO_NOT_UPLOAD`.

## Capability added: 2026-09-29 (Session 50c, contest assignment, Classic exits and the baseline)

Working and verified: the Session 50 step (`within_contest_diversity_v1`) now runs on
every Classic exit and on the baseline, on by default. C1 (one `all` pool), C2 with
its C3 package and export (a `bound` pool for the policy's rows, a `fill` pool for the
rows C1 fills beside a subset policy) and `nfl baseline`/`run-slate`'s baseline
(`nfl_baseline_report_v4`, no restarts, at most 0.4 s) decide which Entry ID holds
which selected lineup contest by contest. It never changes which lineups exist (R29),
never moves a filled row, and on any failure leaves the solver's order with the `P`
limitation `CONTEST_ASSIGNMENT_STEP_FAILED`; a single-contest template is
`NOT_APPLICABLE`. `audit_classic_portfolio` recomputes, from the exact
`assignments.csv` bytes, the lineups each pool holds, the rows the template filled and
each contest's readings, and holds the policy's rows in the CSV to
`classic_assignment.json` row for row; C3 builds the per-contest block (JSON, HTML and
the `Exposure` sheet) from the delivered rosters and a new hashed record,
`selection/contest_assignment.json`; the C1 export and the baseline audit the same
claim through `baseline.audit_baseline_bytes`. Week 3 Classic on its real bytes through
the baseline: 25 entries, eight two-entry contests, three repeated a QB and the worst
shared count was 3; after, none repeat and every contest is at 0 (score 104 to 0).

Not yet: the model path on the real Week 3 bytes was not run (no frozen prior
package, role evidence or official status for it is in the repository, and the run
needs them), so the model path is shown on the synthetic Classic fixtures only. The
objective still ignores prior points (Session 23d's contest facts would steer the
strongest lineups). A baseline whose 0.4 s cap trips returns the best climb found,
which depends on the machine's speed; the report says `timed_out`. It establishes
nothing about expected value, win or cash likelihood, ownership or payouts, and every
path still ends `PRIOR_ONLY / DO_NOT_UPLOAD`.

## Capability added: 2026-09-29 (Session 50, contest assignment, Showdown exits)

Working and verified: `src/nfl_dfs/contest_assignment.py`,
`contest_assignment_version = within_contest_diversity_v1` (`docs/DATA_CONTRACTS.md`).
`run-slate` now decides which Entry ID holds which selected lineup contest by contest
on every Showdown exit (policy, sequential, subset policy with a fill), on by
default: it never changes which lineups exist, never moves a filled row, permutes
bound and fill rows only within their own pool, and on any failure leaves the solver's
order with a named `P` limitation. `audit_policy_assignments` recomputes the multiset,
the filled rows (from the template's bytes) and each contest's readings from the
assignment bytes; the readable review JSON and HTML and the workbook's `Exposure`
sheet carry a per-contest block recomputed from the delivered rosters.
`scripts/diversify_showdown_contests.py` wraps the same module for files built
outside `run-slate` and now handles Classic. On PHI@CHI v1 it reaches 7 distinct
Captains of 7 in each seven-entry contest, worst pairs 4, 3 and 4, every two-entry
pair at 1.

Not yet (closed by Session 50c, above): Classic C1, C2, C3 and the baseline kept the solver's order.
The objective ignores prior points, so it does not steer the strongest lineups toward
any contest (Session 23d's contest facts would). DET@BUF and Week 3 were checked on
baseline portfolios only, not model portfolios. It establishes nothing about expected
value, win or cash likelihood, ownership or payouts, and every path still ends
`PRIOR_ONLY / DO_NOT_UPLOAD`.

## Capability added: 2026-09-28 (Session 23e, Classic half)

Structural hygiene bounds and the share cap for Classic C2 (P2), the Classic half
of Session 23's card.

- `classic_portfolio_policy.py` adds `nfl_classic_portfolio_policy_c2_v2` (v1
  unchanged) with `controls.structural_bounds` (`salary_left` inclusive range,
  `offense_against_own_dst` Boolean, Session 23's "own" reading) and
  `controls.max_person_share` (a fraction in (0, 1]; the integer is
  floor(fraction x bound entries), the default maximum of every person without an
  explicit exposure row). The normalized schema is
  `nfl_classic_portfolio_policy_normalized_c2_v2`.
- Both bounds bind `_Enumerator.enumerate` as MILP rows (`add_salary_band`,
  `add_no_offense_with_dst`, reused from Session 23), are checked directly on
  validated neighbours, and are recomputed from roster bytes by
  `audit_classic_portfolio` and the C3 review (`CLASSIC_AUDIT_` and
  `CLASSIC_C3_STRUCTURAL_BOUND_VIOLATED`). The share is reported with the
  person(s) named in the audit and in `exposure.max_person_share`.
- `relaxation.py`: rung 1 drops the salary band, rung 2 `offense_against_own_dst`,
  and the 0.80 share stays through rung 3, dropped only by rung 4.
  `make_classic_policy.py` writes v2 on every rung.
- Seven gate codes registered; registry re-pinned.

Verified: `tests/test_classic_structural_hygiene.py` (23 tests, including the
supplied 719-person Classic pool at rung 0 and an impossible band failing closed),
`test_relaxation_controller.py` (one test's supplied policy opens the structural
bounds, named in the changelog), full suite
`1862 passed, 1 skipped in 356.97s (0:05:56)`. Not yet: a full C2 bank on the
supplied pool through `run-slate` (Session 47: 4 to 20 s a candidate on this
host, so the bank, not the bounds, dominates); grading against standings
(Session 18b); the DAL@NYG/DEN@KC fixtures (`[BEN: ...]` flag on Session 23's card).

## Capability added: 2026-09-28 (Week 3 slate follow-up)

Three staged scratch scripts from the 2026-09-27 Week 3 slate promoted to
supported tools, two small engine fixes, and `.claude/rules/working.md`
moved to `docs/claude/working.md`. No roadmap session number.

- **`scripts/filter_pool_scores.py`** removes a run's own role-gated
  exclusions from an `NFL_DFS_DUMP_SCORES` dump before construction sees it.
  Prefers the dump's own `excluded_dk_ids` (below); falls back to the run's
  selection report for an older dump. 11 tests.
- **`scripts/swap_inactives.py`** replaces a newly inactive player (single
  swap, then a two-player fallback), works a named value add into up to a
  target count of lineups, redeploys freed salary as one upgrade per changed
  lineup, or edits only cells whose game has not locked (`--mode late-swap`).
  Every mode preserves an existing stack or bring-back and enforces the
  portfolio's exposure and overlap caps and R29 uniqueness. 10 tests.
- **`scripts/build_thesis_portfolio.py`** builds several named theses (a
  market read, a flip, a bust, a flat-priced "priors wrong" fade) as
  independent `build_classic_portfolio.py` calls, then selects across all of
  them under one global cap. Every builder call gets a fresh `--out` path and
  its exit code is checked before the file is read (the 2026-09-27 stale-read
  slip, now a regression test). 16 tests, including one real subprocess call.
- **`scripts/showdown_value_add.py`** (Session 55) works one named person (exact
  DraftKings ID, either role row) into up to N rows of a filled Showdown review
  file by one FLEX swap each, or the Captain with `--captain`. Only rows the
  supplied `--template` left blank can change; a row already holding him is never
  edited; every row passes `validate_lineup`, every `roster_canonical_key` is
  distinct across the file, and no new pair shares all six people. The output is
  rebuilt, reparsed, audited against the template and created exclusively, so one
  invalid row refuses the whole publication. It writes no projection (0 prior
  points; the file stays `DO_NOT_UPLOAD`). Replaces the unvalidated
  `keenum_swap.py`, which stays as a record. 49 tests.
- **`selection.write_pool_scores`** now writes after the run's own exclusion
  set is computed and names it (`excluded_dk_ids`), instead of before. Two
  regression tests, both confirmed to fail against the pre-fix ordering.
- **`scripts/session_probe.py`** now honors `NFL_DFS_TLS_ALLOW_NONSTRICT_CA`,
  matching `sources.py`'s own opt-in, instead of reporting a reachable host
  `TLS_FAILED`.

Verified: full suite `1839 passed, 1 skipped in 359.24s (0:05:59)`. Not yet:
Sessions 47 to 49 (`docs/ROADMAP.md`) are proposals from this session's
findings, not implemented.

## Capability added: 2026-09-27 (Session 23, Showdown half)

Structural hygiene bounds and the portfolio-wide share cap for Showdown (P2),
the one construction change with measured lift in every graded game
(`docs/STANDINGS_DUAL_OPTIMIZATION_FINDINGS_2026-09-15.md` §5.4, §7, §8.1 C,
§8.2 H/I). Classic's half is Session 23e.

- `portfolio_policy.py` adds `nfl_showdown_portfolio_policy_v2`: an optional
  `controls.structural_bounds` object (`qb_count`, `pass_catchers_with_
  rostered_qb`, `salary_left` inclusive ranges; `kicker_count`, `dst_count`
  nullable maxima; `offense_against_own_dst` Boolean). `v1` is never mutated
  and still validates unchanged, normalizing with every bound fully open.
  `structural_bound_violations()` recomputes any of them from exact roster
  DraftKings IDs.
- Every bound binds `LineupOptimizer` as a real MILP row (`optimizer.py`:
  `add_salary_band`, `add_no_offense_with_dst`, both new; `add_selected_
  count_bounds`, existing, reused for `qb_count`/`kicker_count`/`dst_count`;
  `add_classic_qb_correlation_bounds`, existing, its Classic-only restriction
  dropped and now shared for `pass_catchers_with_rostered_qb`) — not a
  post-solve filter. A first post-filter design (reject a violating roster,
  no-good it, resolve) timed out at 30s with 0 candidates on a forced
  DST-captain stratum under three combined bounds on the small synthetic test
  pool; the MILP rows return the same scenario's full bank in 0.09s.
- SD4's independent audit (`portfolio_enforcement.py`) recomputes every bound
  from the exact assigned roster IDs, never from the selector's own claim
  (`PORTFOLIO_AUDIT_STRUCTURAL_BOUND_VIOLATED`), and reports `max_person_share`
  (the already-existing `max_combined_person_exposure.default_fraction`, not
  a new field) with the person(s) named.
- `readable_review.py` reports `exposure.captain_spread` and `exposure.
  max_person_share` in both the JSON and the rendered HTML (review S7: a
  default Captain cap alone doesn't show the resulting spread).
- `relaxation.py`'s `ShowdownRung`/`SHOWDOWN_RUNGS` fold the brief's relaxable
  order (salary band, pass-catcher band, K/DST caps, QB count,
  `max_person_share`) into the existing 3-rung ladder: rung 1 adds the salary
  band; rung 2 adds the pass-catcher band, the K/DST caps and
  `offense_against_own_dst`; rung 3 adds the QB-count band (`max_person_share`
  already dropped there via the pre-existing `uncapped` mechanism).
- `scripts/make_showdown_policy.py` v2 defaults: one QB, one to two pass
  catchers with him, $1 to $500 left, at most one kicker and one DST,
  `offense_against_own_dst=true`; kickers and DSTs stay in the combined pool
  (only their Captain fraction zeroes by default); `--captain-default` now
  defaults to 0.4 instead of requiring an explicit value every call.
- Five new gate codes (alphabetical, class `S`/`P` per the existing family
  split between a runtime breach and a malformed-input shape), registry
  re-pinned in `tests/test_gate_registry.py` and `docs/DATA_CONTRACTS.md`.

Verified with new unit tests (`test_portfolio_policy.py`, `test_portfolio_
enforcement.py`, `test_relaxation_controller.py`, `test_lineups_optimizer.py`)
and a new acceptance test
(`test_showdown_structural_hygiene_acceptance.py`) proven end to end on the
two Showdown fixtures the repo has, NE@SEA and DET@BUF (the card's own
DAL@NYG/DEN@KC bytes are not in the repo, `[BEN: ...]` flag in the Session 23
card). The full suite green apart from the one expected
`test_the_quick_start_names_the_first_startable_session` mismatch while this
session's row was `In Progress`. Not yet: Classic's `salary_left`/
`offense_against_own_dst`/`max_person_share` (Session 23e); grading the
rerun against the archived fields (Session 18b).

## Capability added: 2026-09-26 (Session 38)

Run-path integrity: six defects the 2026-09-25 code review found (V3 to V8)
that could put a deleted or unbound file in front of Ben, or refuse a
legitimate certification.

- `certify` (`command_certify`, and the model-assisted certify profile inside
  `run-slate`) no longer deletes a `DK_UPLOAD_*.csv` its own manifest still
  binds when a later stage (the review workbook) raises after the CERTIFIED
  write; it also no longer resolves a second, different `run_id` when
  `--run-id` is omitted, which used to make that handler unlink the wrong
  path. `nfl.ps1`'s `ValidateSet` accepts `baseline`, and a permanent test
  keeps it synchronized with the CLI's real subcommands. A second `run-slate`
  into an existing `outputs/<run_id>` is refused by name, the same as
  `data/runs/<run_id>`. `status` re-derives through the same historical
  artifact integrity check `audit` uses (R09): it pins
  `RELEASE_DECISION=DO_NOT_UPLOAD` and never exits 0 on a stored `CERTIFIED`
  manifest whose file has moved or been deleted. `prior_review`'s exception
  exit reports `MODEL_STATUS=PRIOR_ONLY`, matching every one of its normal
  exits.
- `certify_upload` and `command_validate` take `plan_entries(...).fillable` as
  their authorized set, as `review_export.py` already did: a template an
  operator partly filled by hand (some rows prefilled through DK's own site)
  can now certify or validate its remaining blank rows, instead of failing
  closed either way (`ENTRY_AUTHORIZATION_MISMATCH` leaving a prefilled row
  out of the assignment, `ENTRY_BLANK_CELL_AUTHORITY_REQUIRED` including it).
  Both also refuse a fillable row that repeats a prefilled row's already-
  resolved roster (R29, `ENTRY_PREFILLED_LINEUP_REPEATED`), matching
  `review_export.py`.

Verified with new unit tests per finding, each first shown to fail against the
pre-fix code in a scratch worktree; the full suite green apart from the one
expected `test_the_quick_start_names_the_first_startable_session` mismatch
while this session's row is `In Progress`. Not yet: native Windows execution
of `nfl.ps1 baseline` was not observed (no Windows in this container); the
new test reads the script's text instead.

## Capability added: 2026-09-25 (Session 11c)

A Classic policy may bind a subset of the fillable blank rows, as a Showdown
policy may since Session 11b. C2's joint solve fills the bound rows; then C1
fills the rest, every C2 lineup and prefilled roster a no-good, under the run's
own exclusions only, all or nothing. The `CLASSIC_POLICY_SUBSET_UNSUPPORTED`
refusal is gone from intake, `prior_review` and selection. The C2 audit covers
the policy's rows; C3 takes the C1 rows from the hash-bound selection record and
checks the partition, then bank membership, counts, bounds and overlap over the
policy's rows, and legality, distinctness (R29), activity, the run's exclusions
and the template bytes over every filled row. Its readable review
(`prior_only_readable_review_classic_c3_v2`) and export audit
(`prior_only_classic_export_audit_c3_v3`) name each row's `source`. A C2 policy
binding every fillable row gives the same file as before (the C2 golden hash).
Also fixed: C3 re-validates the source policy with the run's own exclusions, so
a C2 run that excluded anyone (an official inactive, an operator exclusion) now
reaches C3; before, every such run ended
`CLASSIC_C3_SOURCE_NORMALIZED_POLICY_DISAGREEMENT` and shipped the baseline.
Verified through `run-slate` on the Classic fixture with a prefilled row and
with an official inactive, by replaying C3 with each bound artifact mutated,
and at unit level. Not yet: C1 cuts only exact rosters, so no overlap cap
covers the C1 rows (done in Session 39, below).

## Capability added: 2026-09-24 (Session 11b)

A Showdown policy may bind a subset of the fillable blank rows, in template
order: a thesis or dart sleeve. Both validators accept the fillable rows or a
non-empty ordered subset of them and refuse anything else (`V`), and the bound
list is the denominator for every integer cap (0.5 over 4 bound rows of 10
allows 2). After the SD3 joint solve, sequential Showdown fills the unbound
rows with every policy lineup and prefilled roster as a no-good, under the
run's own exclusions only (since Session 39 also the policy's exact ones); a fill
that runs out of distinct lineups at row k delivered nothing until Session 39b, which
delivers the bound rows and the k it built and names the rest. The SD3 audit covers the
policy's rows, the readable review (`prior_only_readable_review_sd5_v2`) checks
the fill's rows (exclusions, inactives, overlap, distinctness against every row
and every prefilled roster) and names each row's `source`, and the result
carries `row_sources`. The relaxation ladder binds the supplied subset at every
rung, and rung 4 budgets for and fills every fillable row. Both generators take
a repeatable `--entry-id`. A policy binding every fillable row gives the same
file as before, byte for byte (SD3 and C2 hashes captured on `main`). Verified
through `run-slate` on the Showdown fixture with a prefilled row, the ladder at
rung 2 and rung 4, and at unit level. Not yet: a Classic subset validates and
the Classic generator writes one, but `run-slate` refuses it by name
(`CLASSIC_POLICY_SUBSET_UNSUPPORTED`, `P`) and the baseline ships; C2 with a C1
fill, the C2 records and C3's package over both are Session 11c.

## Capability added: 2026-09-24 (Session 11)

A template with rows already entered ships instead of refusing the file.
`src/nfl_dfs/entry_groups.py` reads every row against the slate: a blank row is
fillable, a prefilled row is preserved byte for byte when its cells are exact
current-slate DraftKings IDs (a bare ID or `Name (ID)`), and a partly filled
row, a prefilled roster that does not resolve or repeats another, and every row
of a Contest ID whose rows disagree on name or fee are left as they are and
named unresolved. The baseline, C1's export, the Showdown review export and C3
fill only fillable rows through `lineups.write_upload_bytes`, whose rule is now
per row; writing into a prefilled cell is still refused (`V`), and the byte
audit refuses one too. Distinctness covers the whole portfolio: the baseline
and C1 cut every prefilled roster from every solve, the C2 and SD3 banks never
hold one, and every export audit refuses a filled roster equal to one. Rows
group by Contest ID: `entry_groups` in the baseline report, the `run-slate`
result and the pointer reports each group's filled, unfilled, preserved and
unresolved rows with reasons, and `delivery.replace` refuses a replacement that
delivers fewer rows in any group. New records: `nfl_release_truths_v3`,
`nfl_latest_deliverable_v2`, `nfl_baseline_report_v3`. Verified through
`run-slate` on the Classic fixture (C1 and C2 with the producers' own first
lineups prefilled, damaged rows, two contests) and at unit level for the SD3
bank. Not yet: a policy binding a subset of the blank rows (Session 11b); the
prefilled cell form is unverified against a real DraftKings download with
entered rows; prior_review still fills all of its fillable rows or none.

## Capability added: 2026-09-24 (Session 10)

The engine walks the rung ladder itself. `src/nfl_dfs/relaxation.py` owns the
Classic table (moved from `scripts/make_classic_policy.py`, now a wrapper) and a
Showdown one (`scripts/make_showdown_policy.py --rung`), and `run-slate`
re-enters its review when a policy's selection fails on a trigger read from the
review's structured `selection_failure`: an infeasible bank or joint solve
takes the next rung; a bank or joint solve at its limit, a solver error, or a
hash-bound search the window cannot hold re-sizes the bank at the same rung
first and relaxes no structure, then takes rung 4 (C1, or sequential
Showdown); an SD3 bank that ran out is deepened before any structure; a
supplied policy whose only problems are `S` bounds enters the ladder at intake.
Each rung's policy is the loosest of the one it replaces and the rung's table,
written into the run folder, hashed, validated and normalized like a supplied
one, and every step is an `nfl_relaxation_record_v1` record and an `S`
limitation (`RELAXATION_*`). Uniqueness, exact exclusions and zero caps are
never on the ladder; rung 4 carries a dropped policy's exclusions. Every rung
must fit the deadline's window, and a window that cannot hold rung 4 stops the
ladder by name with the baseline delivered. Verified through `run-slate` on
the Classic fixture (an impossible cap, a bank timeout, a structural failure,
a one-lineup slate, a spent window) and the Showdown fixture (a Captain cap, a
short bank). Not yet: a prior_review shortfall still delivers all or nothing,
so a pool too small for every entry ships the baseline with its unfilled
Entry IDs (Session 11); the fallback builder keeps its own ladder.

## Capability added: 2026-09-24 (Session 09)

R28 on the model path: three stops that held back the engine's own portfolio
are named limitations now, and the file ships. A game nobody observed freezes
as `UNOBSERVED` (team source and team CSV v2, declared only when a game needs
it), is named per game as `WEATHER_UNOBSERVED` (`P`), moves no number (R24
scan and score tests) and never reads as weather evidence in certification. A
Classic selected person with no official activity row, or a run with no file,
publishes through C1, C2 and C3 with `OFFICIAL_STATUS_INCOMPLETE_FOR_SELECTED`
or `OFFICIAL_STATUS_REQUIRED`, as Showdown already did; C3's audit (v2) reports
`selected_activity` `INCOMPLETE` with the people. The P1 unresolved role change
leaves the selectable pool and is named (`OFFENSIVE_UNRESOLVED_MATERIAL_ROLE_CHANGE`,
`P`); every prior stays as scored. Verified end to end through `run-slate` on
the Classic replay fixture, one run per changed exit, each delivering C1's file
with `DO_NOT_UPLOAD`. A `build_priors` request never stops for authority,
including on a plain `--request` rerun, and a test holds it. Not yet: role
gaps (synthetic sources, a missing or unselectable current role) and a selected
unavailable person still block the Classic gate, and present-but-invalid
weather or activity evidence (stale, conflicted, unsupported, hash-mismatched)
still stops the review; the session probe still counts a blocked
`api.weather.gov` as a blocking host.

## Capability added: 2026-09-24 (Session 08)

A time or search limit no longer throws away what the Classic C2 bank built.
A per-candidate solve a limit stops with a legal roster keeps it, labelled
`FEASIBLE_LIMIT`; a bank stopped by its total budget or a limit is
`BOUNDED_TIME_LIMIT_STOP` or `BOUNDED_SEARCH_LIMIT_STOP`, and not blocking,
when it holds the entry count and a `POLICY_FEASIBLE` witness. Both joint
selectors (C2 and SD3) return a limit's valid integer incumbent after the
optimum's own checks as `FEASIBLE_LIMIT_ACTUAL_CANDIDATE_BANK`, with gap and
nodes and no optimality scope; the C2 solve starts from the witness and, on a
limit, returns whichever of HiGHS's incumbent and the witness scores higher. C3 and SD3's review export accept both, and the
file ships naming `CANDIDATE_BANK_STOPPED_AT_LIMIT` and
`PORTFOLIO_SELECTION_LIMIT_INCUMBENT` (`S`). Verified end to end through
`run-slate` on real HiGHS stopped by a node limit and by a time limit, and for
SD3 through the Showdown export. Not yet: a stopped SD3 bank
still blocks (no joint-solved witness), and nothing walks the rung ladder when
a bank does block (Session 10, since done).

## Capability added: 2026-09-24 (Session 07b)

The three clocks Session 07 left fixed keep the run's deadline.
`sources.fetch_public_artifact` takes its timeout from the budget passed or the
one `deadline.activated` set, which `run-slate` wraps around its review:
`min(30 s, the improvement window)`, and no request under 1 s
(`SourceDeadlineError`, `DEADLINE_FETCH_WINDOW_SPENT`, `S`). Each fetch is a
measured `evidence_fetch` stage, one that raises included.
`scripts/fetch_weather_captures.py` stops requests 5 minutes before the delivery
deadline (default the earliest `Game Info` lock minus 5 minutes) and caps each
timeout and retry pause at the time left; without IANA data it says so and
keeps its fixed clocks. `scripts/make_classic_policy.py` sizes the bank to the
window at this host's measured candidate rate and exits 2, writing nothing,
when even the floor bank does not fit. Not yet: the engine walking the rung
ladder (Session 10, since done); an evidence fetch outside `run-slate` (the role-evidence
script) still has only the fixed 30 s.

## Capability added: 2026-09-24 (Session 07)

`run-slate` keeps a delivery deadline (R31): the request's
`delivery_deadline_utc` (`nfl_cowork_run_request_v3`, `--delivery-deadline-utc`)
or the earliest lock minus 5 minutes. One budget, built right after intake,
gives the baseline 30 to 60 s whatever the clock says, stops optimization 5
minutes before the deadline, and sizes the session probe and the C1 and SD3
solver limits from the time left. A passed deadline or a spent window stops
the review and leaves the baseline as the file, named by a `DEADLINE_*`
limitation (`S`). A C2 policy's hash-bound limits either fit or stop the
review. Every result carries measured stage durations, and `run-slate` records
this host's candidate rate after every C2 bank. Not yet: the `diagnostic` and
`registered` profiles' build and certify limits (only their start is gated),
the relaxation ladder inside the budget (Session 10, since done).

## Capability added: 2026-09-24 (Session 06b)

The baseline leaves out anyone the run's official status file marks `INACTIVE`
(R32). Only identity-valid rows count (exact IDs, team, HTTPS source, aware
time), and a disagreeing row takes its person out; refused rows and an
unreadable file are named limitations, never a stop; the file is snapshotted,
hash-bound and re-checked by the audit. `nfl baseline --official-status` does
the same by hand. Activity is still not certified: freshness and coverage stay
the model path's checks.

## Capability added: 2026-09-24 (Session 06)

`run-slate` is baseline-first. A legal, byte-audited file built from the
DraftKings bytes alone exists before the run touches the network, a policy, a
prior or a solver, and every exit names the file to hand over. Every run still
ends `PRIOR_ONLY / DO_NOT_UPLOAD`. Suite figures are in `changelog.md`.

- **The baseline goes first.** Straight after intake `run-slate` builds
  `baseline/DK_BASELINE_ENTRY_V1_baseline.csv` in its output folder from the
  run's snapshots, honouring the request's exact exclusions and extra
  unavailable statuses, and publishes it as `LATEST_DELIVERABLE.json`, before
  the session probe, policy validation, priors, weather, roles or any solve.
  A hand-run `nfl baseline` takes the same exclusions as `--exclude` and
  `--unavailable-status`.
- **An improvement replaces it only through `delivery.replace`**: the review's
  own readable-review classification, then revalidation from fresh parses,
  the same input hashes and at least as many rows. The baseline stays on disk.
- **Every failure after it leaves it named**: a blocked stage (weather,
  identity, policy), the pre-review blocked exit, a withheld CSV, a refused C1
  export and the outer handler. `DELIVERY_STATE` and the delivery half of
  `release_truths` describe the pointer's file, with `IMPROVEMENT_NOT_DELIVERED`
  when it is the baseline. Exit codes are unchanged.
- **Rung 4 ends with a CSV.** Classic C1 exports its own lineups through the
  baseline's writer and audit (`DK_REVIEW_ENTRY_C1_<run_id>.csv`) and replaces
  the baseline; a refused export leaves the baseline.
- **Not yet:** the deadline controller (Session 07), weather and activity as
  limitations on the model path (Session 09), prefilled rows and contest groups
  (Session 11), the delivery record (Session 14).

## Capability added: 2026-09-23 (Session 05)

A review CSV that passed independent validation now survives a failure of its
readable review, in both modes, and every `run-slate` exit says whether a file
exists to hand over. Every run still ends `PRIOR_ONLY / DO_NOT_UPLOAD`. Suite
figures are in `changelog.md`.

- **Presentation failures keep the CSV.** A readable-review failure is
  classified code by code through the gate registry. A presentation code keeps
  the Showdown or Classic C3 CSV in the result and both indexes, with the code
  as a limitation and exit 2. A roster, Entry ID or byte code, or one the
  registry cannot classify, still withholds it.
- **C3 keeps its export and audit** when its own JSON or HTML fails, after
  re-checking both by hash, reparse and the `DK_UPLOAD` check, and removes only
  the two display files.
- **`LATEST_DELIVERABLE.json`** (`delivery.py`, `nfl_latest_deliverable_v1`)
  names the run's validated file, written with `os.replace`, bound to the file's
  and both inputs' SHA-256, and revalidated from fresh parses before it is
  written and whenever it is read. A changed, remapped, illegal or repeated
  lineup is refused under any label.
- **`run-slate` reports `DELIVERY_STATE` and `nfl_release_truths_v2`** on every
  `prior_review` exit; Classic C1 and C2 are `NO_DELIVERABLE`, since they write
  no entry file. After a crash the outer handler names a deliverable that still
  revalidates and never deletes it.
- **Not yet:** the baseline published first and replaced by an improvement
  (Session 06), the delivery record (Session 14).

## Capability added: 2026-09-23 (Session 04)

A file can be built from the two DraftKings downloads alone, before any
evidence, prior or model: `nfl baseline`. It is a separate command until
Session 06 puts it first in `run-slate`. Every run still ends
`PRIOR_ONLY / DO_NOT_UPLOAD`. Suite figures are in `changelog.md`.

- **`nfl baseline --salaries --entries [--out-dir]`** (`baseline.py`) writes a
  new run folder with snapshots, `DK_BASELINE_ENTRY_V1_<run_id>.csv`
  (`nfl_baseline_entry_csv_v1`) and `baseline_report.json`
  (`nfl_baseline_report_v1`, carrying `nfl_release_truths_v2`). Exit 0, 3 or 2.
- **Verified on the supplied fixtures**: Classic (719 rows) and Showdown (126)
  at 1, 20 and 150 entries are `DELIVERABLE`, byte-identical on replay; 150
  entries take about 3.6 s Classic and 6.5 s Showdown. A pool with too few
  distinct lineups is `DELIVERABLE_PARTIAL` and names every unfilled row.
- **Lineups rank by DraftKings salary only** (`BASELINE_SALARY_RANK_V1`), with
  DraftKings `OUT`/`IR`/`D` people excluded. They are legal, distinct and
  byte-audited, not tuned: at 150 Showdown entries one person is in 139 lineups.
- **Every gap is a registered limitation**, never silent: no official activity,
  role, weather or model evidence; a salary file short of the entries table; a
  template with no table; a run past the earliest lock.
- **Every `dk.py` and `lineups.py` refusal has a registered code**, and
  `DeliveryLimitation` accepts only the three class/stops pairs.
- **Not yet:** the lock clock (Session 07), prefilled rows and per-contest groups
  (Session 11), `run-slate` baseline-first (Session 06).

## Capability added: 2026-09-23 (Session 03b)

Every blocker code the engine emits has a class, what it stops and its
authority, in one validated file; no operating path reads it yet (Sessions 04 to
09), and no gate's behaviour changed. Suite figures are in `changelog.md`.

- **`config/gate_registry_v1.json`** (`nfl_gate_registry_v1`): 1,088 exact
  codes in 43 families, 15 `V` (stop the file), 3 `S` (construction
  preferences) and 25 `P` (stop certification). Its SHA-256 is pinned.
- **`gate_registry.load_gate_registry`** hashes and validates it: only the pairs
  `V`/`FILE`, `S`/`CONSTRUCTION_PREFERENCE`, `P`/`CERTIFICATION`; no duplicate,
  orphan or unused entry. `GateRegistry.limitation(code, ...)` builds a
  `DeliveryLimitation` from an exact code and refuses anything else.
- **Completeness is test-backed** both ways over `src/nfl_dfs/`: a new blocker
  code without an entry fails, and so does an entry nothing emits. The scan is
  syntactic; what it cannot see is pinned to the source that emits it.
- **Not yet:** codes for the prose-only gates in `lineups.py`, `dk.py` and late
  swap's locked-cell checks; fixed codes for the four emitters that put an Entry
  ID inside the code; any path that builds limitations from the registry.

## Capability added: 2026-09-23 (Session 03)

The fifth truth exists as a contract and a derivation; no operating path emits
it yet (Sessions 04 to 09). No path's behaviour changed, and every run still
ends `PRIOR_ONLY / DO_NOT_UPLOAD`. Suite figures are in `changelog.md`.

- **`release.derive_delivery_state`** gives `DELIVERABLE`,
  `DELIVERABLE_PARTIAL` or `NO_DELIVERABLE` from file validity, the authorized
  and delivered Entry IDs, and the limitations that fired. It takes no model or
  evidence input. Only a `V` limitation (integrity) can withhold a row or the
  file; `S` and `P` ones travel with it. An unfilled row nothing names gets
  `UNFILLED_AUTHORIZED_ROWS`. `release.release_truths_v2` puts the four v1
  truths, unchanged, beside it as `nfl_release_truths_v2`.
- **`contracts.DeliveryLimitation`** (code, class, stops, provenance, Entry IDs,
  people) refuses a `V` gate that stops anything but the file, and a non-`V`
  gate that stops the file.
- **The R24 condition is test-backed** (`tests/test_gate_registry.py`). Weather
  or a roof value is read only in named plumbing (request, gates, evidence
  records, the roof resolver, the weather scripts) and at ten pinned reads in
  numeric code that validate it or copy it into a row; any other read under
  `src/nfl_dfs/` or `scripts/` fails. No arithmetic anywhere takes one as an
  operand, index or branch test beyond four named counting and text sites. Every
  weather state, derived roof included, gives identical prior scores. Not
  caught: plumbing that turns weather into a number under a name that does not
  say weather.
- **`contracts.DeliveryTruth`** carries `delivered_file_valid`, the validity of
  the file it describes, apart from v1 `FILE_VALID`.
- **Not yet:** the per-code gate registry (Session 03b), and any path that
  emits `DELIVERY_STATE`.

## Capability added: 2026-09-23 (Session 02b)

The Classic fallback's first stage and Showdown QA now share the file-first
exit contract. No release truth changed; the fallback's output is still
`PRIOR_ONLY / DO_NOT_UPLOAD`. Suite figures are in `changelog.md`.

- **`scripts/build_classic_portfolio.py`** exits 0 when every blank authorized
  row has a lineup, 2 when it refuses by name with nothing written, and 3 when
  it writes a shortfall with `unfilled_entry_ids` naming each row. It never
  repeats a lineup (R29), including one already prefilled in the template,
  whatever `--max-overlap` allows. DraftKings `OUT`, `IR` and `D` rows leave the
  pool through `nfl_dfs.contracts.UNAVAILABLE_DK_STATUSES`
  (`--available-status D` restores doubtful players, as in the engine); a
  status outside the engine's vocabulary also leaves it and is named. Only
  blank template rows are reserved, read as the writer reads them (a repeated
  Entry ID is refused, a narrow blank row is named unfilled), and `--lineups`
  defaults to their count. The
  ratchet stops at `max(--max-exposure, N)` exposure and `max(--max-overlap, 6)`
  overlap and never tightens a cap. `--out` must be new; the write is a verified
  temporary file and `os.replace`. A Showdown template or salary file, a
  repeated salary ID, an unreadable salary and a truncated scores file are
  refused by name.
- **`scripts/qa_showdown_portfolio.py`** reports `ZERO_QB`, `MULTIPLE_KICKERS`,
  `MULTIPLE_DST` and `DST_WITH_OWN_OFFENSE` as `OBSERVATIONS`, which never
  change the exit code. Since Session 37 (2026-09-26) it uses Classic QA's
  exits: 1 for a roster, identity, cap, one-team, repeated-lineup, byte or
  Entry ID defect; 3 when a template-blank row is left unfilled; 2 only for
  the operator's `--max-overlap` and `--backup-pairs`. It audits raw lines,
  exempts only template-blank rows, and identifies people by DraftKings ID.

## Capability added: 2026-09-23 (Session 02)

The Classic fallback's last two stages now check the file, not the JSON. No
release truth changed; the fallback's output is still `PRIOR_ONLY /
DO_NOT_UPLOAD`. Suite figures are in `changelog.md`.

- **`scripts/write_dk_entries.py`** refuses by name (exit 2, nothing written) an
  assignment Entry ID the template lacks, a prefilled row, a roster that fails
  the salary file (size, pool, repeated person, slot or FLEX eligibility, cap,
  two games), a repeated lineup (R29), a Showdown template, and an output path
  that exists or is an input. It fills every blank authorized row or writes the
  file and exits 3 naming each unfilled Entry ID. Untouched lines keep their raw
  bytes; the write is a verified temporary file and `os.replace`.
- **`scripts/qa_classic_portfolio.py --template --export`** audits raw bytes,
  compares each exported roster to its assignment by Entry ID, checks each cell's
  slot, and lists every unfilled authorized row. Exit 1 validity, 3 partial
  coverage, 2 an operator-requested limit, 0 pass.
- **Not yet:** the builder's shortfall still exits 0 and its pool still admits
  DraftKings `OUT`/`IR`/`D` rows, and Showdown QA still fails its exit code on
  strategy findings. Both are Session 02b.

## Capability added — 2026-09-19 (P1)

Three things work that did not, none of them changing a release truth. Suite
`822 passed, 1 skipped in 149.40s` before the review fixes below; see
`changelog.md` for the final figure.

**All three are now live on the operating `prior_review` path.** The
depth-chart contract reached it in chunk `P1b` (same day) via
`nfl_cowork_run_request_v2` and the `--qb-depth-role-evidence-json` flag; before
that it was library-only, and an adversarial review rightly caught this
paragraph overstating it.

- **`SALARY_RANK_DIVERGENCE`.** Every scored person the market prices far above
  this scorer is named in `PriorScores`, in `score_pool`'s report and in the
  selection report, with both ranks, salary, prior, and the evidence state that
  produced the prior. Implemented and tested. Live on the operating path. It
  decides nothing: `does_not_establish` includes `WHICH_SIDE_IS_WRONG`.
- **The unresolved-material-role-change gate.** A person in
  `TRANSFER_PRIOR_UNVERIFIED` who also trips that divergence now stops the run
  and the message names the action that clears it, chosen by position. Ben's
  ruling of 2026-09-19. Implemented and tested. Live on the operating path: it
  runs at the tail of `score_pool`, and both callers that produce lineups go
  through it. This is the Kenneth Walker failure, previously silent and now a
  named stop. For anyone who is not a quarterback the remedy it names is the
  full numerical allocation, which is already plumbed. **Since Session 09
  (R28)** the stop is an exclusion: he leaves the selectable pool and is named.
- **Quarterback depth-chart evidence**, contract
  `nfl_qb_depth_role_evidence_v1`, producer
  `scripts/make_offensive_role_evidence.py`. Binds `qb_attempt_share` to a
  published depth chart, conserving the team's existing total onto the rank-1
  quarterback and zeroing backups, applied before `score_pool` rather than after
  it. Implemented, tested, and **verified end to end against real bytes**: the
  live nflverse artifact and the committed DET@BUF salary file, producer to
  consumer, through `resolve_qb_depth_roles`. Reachable from `run-slate` and
  `select` since `P1b`, with its hash bound into the pre-lock manifest at all
  three exits.

What it does not do. It moves `qb_attempt_share` and nothing else — a depth
chart establishes who starts, not target or carry share, and the contract says
so and enforces it. It does not touch the objective, ownership, the candidate
bank, or `MODEL_STATUS`. Output remains `PRIOR_ONLY` / `DO_NOT_UPLOAD`.

- **Effective depth rank and OUT-promotion**, `src/nfl_dfs/depth_roles.py`,
  chunk `P7` (2026-09-21), under Ben's `R25` ruling. A published rank-1 who the
  salary bytes flag unavailable no longer stops the run: the next available
  person in the published order inherits the role, and every promotion is named
  in the run record. Ranks are derived for `QB`, `RB`, `WR` and `TE`, keyed
  `(person, position)` so a kick-return line cannot become an offensive role.
  `depth_charts` is now the eighth registered `NflverseSource`, frozen and
  hash-bound into the prior package.

  Verified against real published bytes (artifact sha256 `e6ba0a08…0494c02`,
  snapshot `2026-09-20T12:14:30Z`) for the depth-chart half. **The DraftKings
  half is fixture bytes, not the 2026-09-20 salary export**, which is under a
  gitignored path on Ben's Windows checkout. So this is verified to the same
  standard as a unit-tested contract, not "end to end against real bytes" in the
  sense the entry above means it. The snapshot replay is operator item 6 in
  the archived backlog, now part of Session 16 in `docs/ROADMAP.md`.

  Only the quarterback path is wired into the resolver today. The non-quarterback
  ranks are derived and tested but reach a projection only through
  `redistribute_opportunity`'s optional `depth_ranks`, which is **off by
  default**: the proportional rule it would replace was set by measurement and
  inheritance has not been graded against it. That grading is `P0`.

### Known environment limits, measured the same day

These bound what a cloud session can do and are not claims about Ben's Windows
box. Evidence in `changelog.md` 2026-09-19 and issue #21.

- `data/standings/inbox/` is gitignored, so a fresh cloud clone has no standings
  corpus. `P0`, `P0b`, `P4a`, `P4b` and `P5` cannot run in a cloud session until
  chunk `X2` (Session 17 in `docs/ROADMAP.md`) lands. The archived backlog's
  claim that the corpus is "in the repo" is true only on the Windows checkout.
- Three of the six hosts in `sources.ALLOWED_HOSTS` answer 403 at CONNECT in a
  cloud session: `api.weather.gov`, `api.sleeper.app`, `api.the-odds-api.com`.
  `docs/CLAUDE_CODE_SETUP.md:114-125` asserts otherwise and is being replaced by
  a per-session probe in chunk `X1`. nflverse over GitHub is reachable.
  Re-measured 2026-09-20 and 2026-09-21: unchanged. Since 2026-09-21 `run-slate`
  runs `scripts/session_probe.py` itself and writes
  `data/runs/<run_id>/session_probe.json`, so a run records what it could reach
  instead of leaving it in scrollback. The `doctor` half of `X1` is still open.
- A blank `roof` cell at a retractable-roof venue (ARI, ATL, DAL, HOU, IND) no
  longer demands an `api.weather.gov` capture. nflverse writes `roof` only after
  the game, and `src/nfl_dfs/venues.py` resolves the blank from that venue's own
  completed history in the run's frozen artifact, over the prior-plus-current
  season window, when unanimous and at least eight games. On the 2026-09-20
  afternoon slate this took captures required from 4 of 5 games to 2 of 5. It
  resolves nothing for an outdoor venue, nothing when the window records an open
  roof, and an operator capture still outranks it. Genuinely outdoor games still
  need a real capture, and in a cloud session that capture must be taken
  elsewhere (`docs/RUNBOOK.md` step 0).
- `nfl.sh` as shipped fails the entire suite in a fresh container
  (`2 failed, 226 passed, 1 skipped, 562 errors`) because pytest does not create
  the parent of the `--basetemp` it is handed. Fixed in PR #19, unmerged at the
  time of writing; `NFL_DFS_PYTEST_TMP` is the documented workaround.
- The `DFS_Architect_MCP` server attached to these sessions returns **stub**
  weather. It is never a model input.

## Validation corpus — 2026-09-14 (Q1B and Q1C)

Both tranches are merged to `main` in `4313455fcd8fd722b699a799dbe19dff19c1be68`
(PR #13), together with the previously uncommitted C3 tranche. C3 is merged but
**not accepted**: it stays `BLOCKED` on native Excel acceptance, so it is not
`DONE`, no C4 prompt is prepared, and no later item is `READY`.

**The validation corpus holds zero settled contests.** Ben has entered 18 real
contests across three slates since 2026-09-09; all 18 raw DraftKings standings
exports are now pulled and preserved, one is normalized to
`nfl_standings_csv_v2`, and all 18 are dispositioned as unsettleable with
recorded reasons. Q6's accrual dependency is entirely unmet, and no amount of
later engineering shortens it.

The reason was measured rather than left unknown. No `data/runs/` snapshot held
an `nfl_prelock_run_manifest_v1` or an `nfl_scenario_bank_v1` for any contest:
only the legacy `build` command wrote them, and every contest Ben has actually
entered came through `prior_review`/C1-C3. A pre-lock manifest records what was
predicted *before* lock, so it cannot be written afterwards and was not. Those 18
are permanently unsettleable.

**Q1C closed that gap going forward.** `prior_review` now emits a pre-lock
manifest from every success path, and four settlement gates that no honest
producer could clear were corrected on Ben's ruling — chief among them
`field_size`, which required the pre-lock manifest to record the *settled* entry
count. On a realistic `cowork-run` tree the request builder now resolves
everything except the payout table and the standings pull, which are the two
facts only Ben supplies at settlement time. The next slate he runs, enters and
pulls can settle. None of the 18 already played can, and none was backfilled.

What Q1B does and does not establish:

- **Working, on real bytes:** the normalizer reads all 18 real exports and
  converted contest 193391013's full 126,020-entry field in 5.908s, with its
  reconstructed canonical lineup keys independently matching those
  `lineups.validate_lineup` builds from the review export Ben actually uploaded.
- **Working, on a synthetic slate only:** the `--request` → `--replay` round
  trip, now including a manifest frozen by a real `prior_review` run. The
  settlement itself is still a synthetic complete field where the operator owns
  every entry; no real contest has been settled.
- **Not established:** anything about model quality. One contest's measured
  result (two entries, 17,298th and 17,328th of 126,020, $30.00 each on $20.00
  entries) is a recorded outcome, not evidence that the engine picks good
  lineups, and licenses no EV, ROI, ownership or calibration claim. One slate is
  not a sample, and zero settled slates are not a corpus.
- **Unchanged:** `MODEL_STATUS=PRIOR_ONLY` and
  `RELEASE_DECISION=DO_NOT_UPLOAD`. Landing a settled slate would change no
  release truth, and none landed.

Two defects in `nfl_standings_csv_v2` were found on real bytes and left open for
Ben's ruling rather than worked around: it cannot represent a field member who
never submitted a lineup (11 of 18 exports carry them), and it cannot hold an
exact tie split that is not a whole number of cents (757 entries in 193391013
alone), which means a contest with any uneven tie split can never clear
`STANDINGS_PRIZE_MISMATCH`. Both are detailed under Q1B in
`docs/backlog-archive/backlog-through-2026-09-22.md`; the fix is Session 30 in
`docs/ROADMAP.md`, waiting on Ben's ruling.

One pre-existing test failure is now permanent and unrelated to Q1B:
`tests/test_w6_live_preflight.py::test_live_check_refuses_once_a_selected_player_has_locked`
hardcodes an evidence expiry of 2026-09-14T00:00Z that has now passed, so
`certify_upload` correctly refuses and the test's own helper assertion fails. It
is identical in `HEAD` and will fail every day from now on.

## Pre-slate state — 2026-09-12

The C3 working tree was executed on Cowork/Linux for the first time and
reproduced the Windows result exactly: `sh ./nfl.sh setup` in 9.171s, doctor
`pass_status: true` on Python 3.13.7, and `618 passed, 1 skipped in 152.12s`.
That closes the "actual Cowork/Linux acceptance remains unverified" caveat for
suite execution; it does not close C4, which is a real-slate operator rehearsal
with current evidence.

R21 landed: the Classic selected-evidence gate demanded
`SOURCE_SUPPORTED_ADJUSTMENT` for every selected offensive person, which only a
captured numerical allocation produces and no approved host publishes, so no live
Classic slate could publish a selection. Every Classic test supplied a synthetic
role package, so the suite never saw it. On Ben's 2026-09-12 ruling the gate now
matches Showdown exactly and names every history-derived role it selects on. The
suite after the change and its new coverage is `623 passed, 1 skipped in
144.64s`. The four truths are unchanged: `FILE_VALID` remains artifact-specific,
`EVIDENCE_STATE` remains separately derived, `MODEL_STATUS=PRIOR_ONLY`, and
`RELEASE_DECISION=DO_NOT_UPLOAD`.

C3 was `BLOCKED` on native Excel open/recalculate/save/reopen acceptance until
2026-09-22, when Ben's R30 closed it for software acceptance and deferred the
Excel step to Session 35 in `docs/ROADMAP.md`. Nothing waits on Excel.

`device_bash` has been unusable since a Windows update released 2026-09-08; the
other device tools work, so the repo is staged into the cloud container, built
and tested there, and changed files are written back.

## Current development program — 2026-09-15

Superseded 2026-09-22: the only queue is now `docs/ROADMAP.md`, and this
program is archived verbatim in `docs/backlog-archive/backlog-through-2026-09-22.md`.
The queue was `Reprioritized development program — 2026-09-15
(prize tail first)` in `backlog.md`, built on
`docs/STANDINGS_DUAL_OPTIMIZATION_FINDINGS_2026-09-15.md` and
`docs/STANDINGS_GREENFIELD_FINDINGS_2026-09-15.md`. `P0` (standings grading
harness) and `P1` (salary-divergence diagnostic and current-team role evidence
producer) were `READY` on that date. **Superseded 2026-09-19:** `P1` is `DONE`
(see the section at the head of this file); `P0` is the only `READY` chunk left
and is blocked in cloud sessions on chunk `X2`. `C3`'s software acceptance passed on 2026-09-14; the
program proposes splitting its native Excel step out as `C3X` (`DEFERRED`) and
re-sequencing `C4` behind `P2`, pending Ben's ruling, and until he rules `C3`
keeps its `BLOCKED` status. Every other item is `BLOCKED` on the chunks named
there. Nothing in the program
changes a release truth: all output remains `MODEL_STATUS=PRIOR_ONLY` and
`RELEASE_DECISION=DO_NOT_UPLOAD` until Q6 promotion, which still waits on
settled-slate accrual. What the standings established about the current engine,
in one line each: the expectation objective cannot target the tail and its
priors overshoot 1.5 to 2x; a transfer with no current-team evidence can carry a
backup-level prior while priced as the slate's best player; exposure caps as the
only diversifier produce single-thesis portfolios; Showdown first place is
shared 5 to 200 ways and the objective does not know; expectation lineups were
assigned to first-place contests by construction.

## Current development program — 2026-09-11

DEV0 is complete on merged `main` commit
`7f083fbd77620d96e3f0571f09d93fdaeb32e377` (PR #9; reviewed source
`652c855`). That baseline retained the excluded user/generated paths and
recorded `516 passed, 1 skipped` plus doctor, compile, and whitespace checks. Q1
is now complete on `codex/q1-settlement-reference-economics`: focused tests
passed 46/46 and the final full suite passed `542 passed, 1 skipped` in 117.86s;
doctor, compile/import, whitespace, mutation, overwrite, and copied-package
replay checks passed. C1 is complete on
`codex/c1-classic-intake-prior-review` at unchanged baseline HEAD
`9d25ad75f6fd08a22b700e3062b7304158e5c0c8`: the shared frozen prior/projection
path now covers multi-game Classic, selected activity/current-role evidence
fails closed, and one-command prior review emits deterministic selection and
complete-slate coverage JSON without an upload-shaped CSV. Final verification
collected 555 tests (`554 passed, 1 skipped`) and passed doctor, compile/import,
whitespace, replay, mutation, prohibited-path, and benchmark checks.

C2 is complete on `codex/c2-classic-policy-candidates-portfolio` at unchanged
baseline HEAD `90361980959916333cbd4b820680166a7e4fe6a2`. Classic now has a
canonical exact-input policy with direct integer player/team/game bounds,
exclusions, hard/advisory groups and registered stack rules, uniqueness and
pairwise overlap. Deterministic documented construction strata produce a
bounded legal candidate bank; one joint MILP assigns one unique lineup to every
ordered reserved Entry ID; a separate canonical-artifact audit reparses policy
bytes and recomputes identity, legality, every hard count and all overlaps.
Candidate, assignment and audit output is machine-readable JSON only. It never
calls ownership, field, duplication, payout/economics, production portfolio, or
C3 review/export code and never emits a Classic assignment or upload-shaped
CSV. Final verification passed `203 passed, 1 skipped` focused and `581 passed,
1 skipped` full, plus doctor, compile/import, whitespace, replay, mutation,
prohibited-path, adversarial-diff, and synthetic scale checks. The 150-entry
synthetic case built 174 candidates and selected the portfolio in 4.015856s
total with 432,880 bytes peak traced Python memory. This is optimal only over
the reported actual bounded bank; it is not the C3 full 719-person acceptance,
not a calibrated objective, and not upload-ready.

C3 is implemented on `codex/c3-classic-audit-review-export` at unchanged
baseline HEAD `f2890a6c587b01cede2e07bdcbb3ec1dd0ab0d33`. A new downstream
auditor strictly reparses and re-hashes every authoritative C1/C2 artifact at
four boundaries, independently recomputes Classic identity, legality, salary,
policy counts, stack/group semantics, evidence, uniqueness and every pairwise
overlap, and byte-diffs the proposed and final exact-template review CSV. Only
audit `PASS` can publish `DK_REVIEW_ENTRY`; every tested mutation, stale or
partial output, prefilled or unauthorized row, unavailable/current-role stop,
non-optimal state, and display disagreement withholds all new C3 output. The
successful package adds canonical audit/readable JSON, escaped self-contained
HTML, and a Classic eight-sheet workbook while preserving Showdown behavior.

The supplied 719-person/24-team/12-game fixture passed registered 1/3/20/150
entry acceptance and short-path copied-package replay with byte-identical
canonical policy, bank, assignment, audit, selection, coverage, readable
JSON/HTML, and review CSV hashes. Independent rendering inspected all eight
workbook sheets and every page of the nine-page HTML PDF. C3 nevertheless
remains `BLOCKED`: the installed Excel automation endpoint refused the required
native open/recalculate/save/reopen operation. No C4 prompt was created and no
later item is `READY`. The four truths remain independent and fixed at
`FILE_VALID=true`, `EVIDENCE_STATE=PASS`, `MODEL_STATUS=PRIOR_ONLY`, and
`RELEASE_DECISION=DO_NOT_UPLOAD` for the test-only acceptance packages.
Golden/adversarial C3 coverage passed 36/36; the combined focused regression
passed `217 passed, 1 skipped` in 265.42 seconds; and the complete pinned suite
collected 619 tests and passed `618 passed, 1 skipped` in 364.86 seconds. Doctor,
changed-module compile/import, whitespace, exact-byte, Entry-ID order,
copied-package hash, render, mutation, and no-`DK_UPLOAD` checks passed.

## Current Showdown readiness — 2026-09-09

The recorded pre-SD2 real NE–SEA two-entry template completed `cowork-run --profile
prior_review` through source acquisition, projection, selection and independent
review export. The repeated export is byte-identical; only the two reserved
entry rows change. See `docs/READINESS_REVIEW_2026-09-09.md` for the current
verification, fixes and limitations. SD2 requires fresh history coverage and
role evidence when roles changed; that older rehearsal does not establish
current live SD2 readiness. Older supplied-fixture counts below are
historical. This verifies Windows execution, not the actual Cowork/Linux VM.

The generated portfolio is still `PRIOR_ONLY / DO_NOT_UPLOAD`. Its objective
maximizes points of an expected stat line, with structural differentiation;
it is not the required calibrated ceiling/ownership/drawdown engine. Current
official activity, prospective validation and the quantitative redesign remain
blocking work. Supplied current official inactive rows now affect both roles
before prior-review selection. The older simulation/build path still needs its
own participation and economics repairs.

SD1 now gives the prior-review scorer one conserved team kicker event line.
Exact, source-bound current-role evidence can declare a sole kicker or an
explicit numerical split; ambiguous multi-kicker teams block, zero-share and
excluded people cannot be selected, and the single-kicker compatibility path is
reported only as an `UNKNOWN` prior assumption. This is a scoring/input-integrity
repair, not completion of offensive roles or live current-role modeling.

SD2 adds `nfl_offensive_role_evidence_v1`, strict captured numerical allocations,
five distinct current-role states, current-team-only historical denominators,
missing-efficiency gates and preserved unallocated volume. It removes generic
historical redistribution from the prior-review and standalone prior-selection
paths. Historical snap share is diagnostic only. Source-supported adjustments
run after all existing exclusions, and expiry/hash changes block review export.
The real freeze/project/select/export code has been exercised on portable,
clearly labelled synthetic captures, including the frozen LA/LAR team crosswalk.
See the Showdown priority tracker for final verification results. Live compatible
numerical offensive-role captures and actual Cowork/Linux acceptance remain
unverified. W3's simulator mask and full forward-role model remain incomplete.

SD3 adds the exact-bound `nfl_showdown_portfolio_policy_v1` contract. It binds
the immutable salary SHA-256, single game, complete underlying-person/CPT/FLEX
identity map and full requested Entry-ID sequence; normalizes numeric fractions
with exact-decimal floor rounding; reports declared and effective combined-person
and Captain limits; and defines canonical lineup, uniqueness and pairwise-person
overlap semantics. Necessary capacity findings do not claim solver infeasibility.
SD4 now enforces the normalized contract in the Showdown `prior_review` profile
through a bounded legal candidate bank and one joint MILP, assigns the exact
Entry-ID sequence without cycling, and independently re-audits every control and
bound artifact immediately before export. Feasible results remain optimal only
over the reported actual bank; incomplete-bank exhaustion is not called full-
slate infeasibility. Policy-free SD1/SD2 behavior is unchanged.

SD5 adds a readable review layer without changing selection or release policy.
After a valid prior-review export, it independently reparses the exact salary,
entry, assignment, exported review CSV, selection report, normalized policy and
policy audit; rechecks every bound hash; and recomputes lineups, salaries,
combined-person/Captain exposure, uniqueness and pairwise overlap before any
display is marked `PASS`. The generated package contains canonical JSON, escaped
self-contained HTML and an eight-sheet workbook with exact assignments,
exposure, evidence/role observations, provenance, all four release truths and
one next action. A mismatch fails closed at `READABLE_REVIEW`, preserves earlier
artifacts and returns no top-level review-export path. The layer remains
`PRIOR_ONLY / DO_NOT_UPLOAD`; actual Cowork/Linux and current real-evidence
acceptance are SD6.

## Working and locally verified

- The red-team revision has replaced the prior `plan.md`.
- All five supplied DraftKings/rules artifacts are preserved byte-for-byte with
  a checked SHA-256 manifest. Repository attributes now disable text conversion
  for byte-sensitive CSV, workbook, and supplied-fixture paths. Both critiques
  remain preserved.
- `nfl.ps1` provides setup, guided run, intake, validation, build,
  certification, audit, governed late swap, settlement capture, learning gates,
  and tests through one Windows launcher.
- `nfl.sh` provides the pinned Linux/Cowork launcher. `cowork-run` discovers
  arbitrarily named CSV attachments by first-row schema, rejects ambiguous
  duplicates, snapshots every recognized input, and writes a normalized
  `nfl_cowork_run_request_v1` request for deterministic reruns.
- The Cowork path can chain a complete supplied request through diagnostic or
  registered build, REFEREE QA, and certification. An incomplete two-file run
  produces a versioned review workbook and `cowork_run.json`, names every
  blocker, and leaves no upload-shaped CSV.
- Cowork model-assisted runs require a frozen source-ledger artifact; the
  ledger, team projections, and player opportunities are independently hashed
  into the certification manifest. Hash binding does not by itself validate an
  external source's truth or license.
- `nfl.ps1 project` / `nfl.sh project` now provide the minimum S6A producer.
  Four immutable hash-pinned inputs (salary, team prior, player prior, and exact
  frozen identity map) are validated without network access; position-eligible
  weights are deterministically conserved to team shares; exact Classic or
  Showdown FLEX identities are enforced; and both loader-valid CSVs plus the
  strict source ledger are atomically published only after independent hash and
  contract reconciliation. DraftKings APPG remains raw-only.
- Classic and Showdown salary contracts enforce exact IDs, geometry, salary
  cap, underlying-person identity, distinct CPT/FLEX IDs, and exact 1.5x Captain
  salary/scoring behavior.
- Showdown kicker-role evidence binds the salary hash, game/team, underlying
  person, exact CPT/FLEX IDs, allowlisted captured source bytes and hashes,
  observation/capture/expiry times, and transformation version. Allocation is
  applied to team scoring events before DraftKings scoring and the Captain
  multiplier, conserving base team kicker points exactly once. Supplied invalid,
  stale, future, tampered, incomplete, or newly ineligible allocations fail
  before assignments/review export; Cowork snapshots the manifest and sources
  for path-independent replay.
- Showdown portfolio-policy inputs are path-confined, copied into immutable
  content-addressed snapshots, validated against all requested entries and exact
  role identities, and written as stable normalized bytes with source and
  normalized SHA-256 values. The `prior_review` selector uses the exact SD3
  integer maxima over a default 32-candidate bank, reports generation and joint-
  solve budgets/status/coverage, and permits Captain repetition only when the
  effective Captain maximum allows it. Immediately before export, a separate
  audit strictly reparses the canonical normalized-policy artifact, re-reads exact
  assignment bytes, recomputes legality, exposure, Captain, canonical-uniqueness
  and pairwise-overlap facts, reconciles selector summaries, and binds salary,
  entry, source-policy, normalized-policy and assignment hashes.
  Only `ENFORCED_AND_INDEPENDENTLY_AUDITED` can reach the review-entry writer.
- One build/certification package is deliberately limited to one Contest ID and
  one entry fee. Mixed-contest exports fail closed until per-contest economics
  and allocation are implemented.
- Payouts enforce contiguous paid ranks, monotonic tiers, advertised-value
  reconciliation, finite exact-cent cash values, whole ticket counts,
  field-size bounds, cash/ticket distinction, and exact tied-rank division.
- Q1 settlement capture consumes a strict hash- and version-bound request and
  atomically publishes a never-overwritten copied package containing every
  salary, reserved-entry, payout, assignment, pre-lock prediction/model,
  scenario, metric-registry, and complete standings artifact. It rejects
  contest, draft-group, mode, Entry-ID, artifact, version, rank, prize, and
  source-mutation disagreement. The generated machine-readable brief and
  package-relative replay request reconstruct without conversation history.
- The Q1 reference evaluator is independent of the vectorized production
  economics path. Decimal six-place score rounding, strict-above ranks, exact
  tie occupancy, rational-cent cash/ticket division, complete-lineup
  duplication, and multiple owned entries are evaluated exactly within an
  explicit size/work/runtime budget or refused with a named blocker. A copied
  package must reproduce the same semantic assignment and reference-result
  hashes.
- `config/metric_registry_q1_v1.json` predeclares player-outcome,
  participation, ownership, duplication, rank/payout-tail, portfolio-risk,
  runtime, and memory metrics with uncertainty, ESS, temporal split, sample,
  promotion, noninferiority, demotion, and rollback requirements. `learn`
  refuses a registry that did not precede challenger evaluation. No model was
  promoted.
- Manual assignments can be independently validated and exported into only the
  blank, authorized Entry-ID rows. Untouched lines preserve their exact bytes,
  including original BOM state. The final CSV is reparsed and SHA-256 bound.
- Certification reports `FILE_VALID`, `EVIDENCE_STATE`, `MODEL_STATUS`, and
  `RELEASE_DECISION` independently. Legal proposed bytes are constructed,
  audited, reparsed, and hashed in memory even when evidence or model blockers
  require `DO_NOT_UPLOAD`; no upload-shaped CSV is persisted in that case.
- Governed late swap has a separate fail-closed writer for fully prefilled
  DraftKings bulk-edit templates. It binds a prior `CERTIFIED` manifest and
  assignment, derives replaceable cells only from exact IDs and lock times,
  preserves locked and unauthorized bytes, independently audits and reparses
  the candidate bytes, and writes a new immutable output only after every gate
  passes. The ordinary pre-lock writer writes only blank rows and passes
  prefilled rows through byte for byte (Session 11).
- Hard evidence is typed and fail-closed. Current official status uses exact IDs
  and operator-controlled source evidence; fuzzy names cannot certify. Official
  activity rows retain their real observation times and expire after the
  registered three-hour lock window. Market/weather rows are bounded,
  enumerated, source-ledger-bound, and expire after six hours.
- Late swap additionally requires source-bound eligibility for the exact
  Contest ID and versioned team-scoped official inactive negative lists.
  Explicitly empty team reports are supported; missing teams remain unknown,
  report freshness is T-90/lock-relative, and `NOT_YET_DUE` cannot clear a
  final late-swap release decision.
- Model-assisted certification requires `PASS` opportunity evidence for every
  selected player. Non-PASS uncertainty elsewhere in the salary pool is
  counted and retained as a prior-only model limitation rather than mislabeled
  as selected-player hard evidence. The build report is bound to the exact salary, entry,
  payout, team, and player input hashes plus the contest parameters; a report
  from a different build cannot clear certification.
- The live model path uses explicit opportunity inputs, deterministic team-share
  conservation, a vectorized heavy-tailed simulator, separate DESIGN/SELECT/
  REFEREE banks, direct persistent HiGHS MILPs, candidate-family coverage,
  cold ownership stress states, complete legal opponent lineups with
  multiplicities, exact duplication/ties, and contest-aware portfolio metrics.
  Multiple reserved entries are settled against one another as well as against
  the simulated opponent field.
- The field evaluator retains no field-by-scenario matrix. Full candidate banks
  are reduced before scenario/economics arrays are retained. Candidate and field
  scores use the same float64 gather/sum path, ranks are vectorized, and divided
  payouts use a vectorized cumulative prize table.
- Quantitative QA is executed after selection, persisted in the build report,
  and hash-bound into certification. REFEREE remains report-only in the sense
  that it cannot tune or reselect, but its independent confidence-aware sign or
  genuine safety disagreement is a binding promotion blocker. Solver proof is
  persisted. Construction preferences such as `DST_OPPOSING_PASS_STACK` and
  candidate-family coverage are advisory unless a registered hard policy is
  enforced by the solver and validator.
- Exact one-to-three-entry search is exhaustive only inside an explicit bounded
  shortlist (maximum 50,000 combinations); combinations are evaluated in
  vectorized batches and the effective search size is reported.
- The five-sheet operator-input workbook remains the stable staged-input
  contract. A successful Showdown `prior_review` output extends its copied
  review workbook to eight sheets: exact Portfolio rows, Exposure, Review
  Evidence and Artifacts sit beside Run Control, Evidence Paste, QA and Upload.
  Formula-active prefixes and markup are inert at the display boundary; exact
  identities and source bytes stay in the hash-bound artifacts. The output has
  explicit print areas, repeated headings and normalized freeze panes, opens
  normally in native Excel, and renders without formula errors.
- Versioned Parquet scenario storage, rolling-origin challenger fitting, model
  promotion tiers, multi-slate rollback rules, Q1 settlement capture, and
  locked-cell late-swap audit are implemented. The SQLite registry and lifecycle
  transition guard are library components exercised by tests but are not yet
  wired into live runs.

## Deliberately diagnostic or externally gated

- No supplied contest payout table, field size, or official current activity
  evidence exists. Therefore no real supplied-slate upload is certified.
- The Cowork instruction and orchestration layer does not manufacture those
  missing facts. A salary-plus-entry first pass is expected to remain
  `DO_NOT_UPLOAD` until Claude freezes approved evidence and the operator
  supplies any unavailable contest-specific facts.
- The supplied entry template is Classic. Showdown upload remains hard-blocked
  until matching Showdown entries and payouts are supplied.
- Opportunity, field, ownership, duplication, and payout predictions remain
  diagnostic until prospective historical/live validation clears the registered
  sample and calibration gates. The engine does not label them EV, ROI, win
  probability, or calibrated ownership.
- SD1 does not produce current offensive roles. A live slate still needs current
  approved kicker-role captures when multiple kickers remain eligible, and
  synthetic role fixtures prove mechanics only. A sole-listed assumption does
  not establish official activity or model readiness.
- S6A creates source-bound `PRIOR_ONLY` inputs but does not implement the full
  Section 4.4 historical ingestion, offline fitting, prospective validation, or
  live-source refresh architecture. A successful producer run therefore
  remains `DO_NOT_UPLOAD` until the separate evidence and model gates pass.
- nflverse, NWS, and Sleeper are policy-bound source adapters, but a live season
  backfill and license/schema audit have not been run from the supplied files.
- A synthetic full-width Classic benchmark built 20,000 candidates in 144
  seconds, covered every registered Classic construction family, retained a
  250-lineup economics shortlist, and respected the 4 GiB memory cap. It used
  only 50 scenarios in each DESIGN/SELECT/REFEREE bank. The complete registered
  10,000/20,000/20,000 refresh and real-data 10/5-minute gates therefore remain
  unclaimed until the operator supplies complete model inputs.
- Late swap can safely write an operator-proposed, evidence-cleared change to a
  current prefilled bulk-edit template. A calibrated joint conditional
  contest-state reoptimizer remains gated on live standings, ownership, scores,
  and validated remaining-game models; S2 does not implement or claim one.
- Runtime scenario defaults and certification deadlines come from
  `config/runtime.json`; hard-evidence requirements come from
  `config/evidence_policy.json`; `config/scoring.json` is validated against the
  executable salary-cap and Captain rules before a build or certification.
- Exposure envelopes, historical pair-dependence bands, and material
  ownership/market sensitivity thresholds are not yet registered inputs. The
  active QA pass leaves those triggers unasserted instead of inventing limits.
- The portfolio policy remains a user-control contract, not model evidence or a
  calibrated risk claim. Its SD4 solve is bounded to the actual reported bank
  and has not been benchmarked at 20 or 150 entries. Actual Cowork/Linux use,
  current live policies/evidence and prospective model quality remain unverified.
- Weekly rolling-origin fitting, promotion, influence caps, and rollback logic
  are implemented, but automatic deployment correctly has nothing eligible to
  promote before settled-slate history accumulates.

These are evidence gates, not silent fallbacks. Their operational result is
`SIMULATION_DIAGNOSTIC_ONLY` or `DO_NOT_UPLOAD`, never a misleading readiness claim.
