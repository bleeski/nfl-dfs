# NFL DFS Implementation Changelog

This file records completed implementation work and verification evidence for the sessions in `docs/ROADMAP.md`. Keep entries factual and append new dated sections beneath `Unreleased`. Do not describe planned, diagnostic, synthetic, or structurally legal work as live-certified or upload-ready.

## Unreleased

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
  error or an illegal solver roster still blocks.
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
  report `mip_start` `POLICY_FEASIBLE_WITNESS`). Probed on highspy 1.11.0 on
  the C2 fixture bank at 10 entries: with the start, `mip_max_nodes=0` returns
  `kSolutionLimit` with the start as a valid incumbent (objective 3598.931
  against the optimum's 3599.102), and a time limit of 1e-9 s returns
  `kTimeLimit` with it; without a start, `mip_max_nodes=0` returns
  `kSolutionLimit` with no valid solution.
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
- Tests, none decided by a wall clock:
  `tests/test_classic_portfolio_c2.py` +12: a limit with a valid incumbent at
  each of the three statuses (labelled, gap 0.0125 and 37 nodes reported, the
  witness start recorded, the C2 audit passes); an incumbent failing the
  optimum's checks (fractional, short) fails closed; real HiGHS at
  `mip_max_nodes=0` returns the weakest-three witness start, below the
  optimum, audited, and with no witness `PORTFOLIO_SELECTION_SEARCH_LIMIT`;
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
  `tests/test_classic_review_c3.py` +5: the incumbent accepted and named, the
  over-claimed scope withheld, both stop statuses accepted and named, and the
  card's acceptance through `run-slate` (below).

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
- The witness chain can be the selection: as the joint solve's MIP start, it is
  the incumbent HiGHS returns when a limit stops it first, so the joint solve
  never delivers less than the witness and "no incumbent" can happen only
  without one. The witness is a feasible point of the final model because every
  bound counts selected lineups and the final bank extends the witness's.
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
  Session 10 gives Showdown its ladder.
- Session 07b's open item, "the generator's 5 s per-solve limit is not scaled
  to a measured rate", closes as a delivery risk: a per-solve limit that
  returns a roster now keeps it and the bank goes on, so it no longer costs a
  rung. Only a per-solve limit that returns nothing still stops the bank, and
  that blocks only without the entry count and a witness. Sizing the limit to
  a measured rate stays a construction preference for Session 10.

#### Verification

- The card's command,
  `sh ./nfl.sh test tests/test_classic_portfolio_c2.py tests/test_portfolio_enforcement.py tests/test_classic_review_c3.py -x --tb=short`:
  `128 passed in 73.81s (0:01:13)`.
- The card's loop,
  `for i in $(seq 20); do sh ./nfl.sh test tests/test_classic_portfolio_c2.py -k nonoptimal -x --tb=short || break; done`:
  20 of 20 runs `9 passed, 31 deselected`, 0.43 to 0.53 s each.
- Full suite before the change: `1647 passed, 1 skipped in 238.33s (0:03:58)`.
  After: `1669 passed, 1 skipped in 228.44s (0:03:48)` (+22; the skip is the Windows junction test), recorded. `doctor` exit 0 (`pass_status: true`), `git diff --check` clean,
  `compileall` of the eight changed modules clean, `check_protected_paths.py`:
  no protected path touched.
- The card's acceptance, `test_run_slate_delivers_a_node_limited_incumbent_from_a_time_stopped_bank`:
  `run-slate` on the Classic fixture with the template policy, the joint solve
  on real HiGHS at `mip_max_nodes=0` (presolve off; with presolve on HiGHS
  solves the one-entry model outright and the test fails, checked), the bank's
  total budget spent two solves into its fill. Exit 0,
  `PRIOR_ONLY_CLASSIC_C3_REVIEW_EXPORT`, improvement `DELIVERED`, the C3 CSV
  the deliverable, both codes `S` limitations, the export audit's joint record
  `FEASIBLE_LIMIT_ACTUAL_CANDIDATE_BANK` with a null scope, bank
  `BOUNDED_TIME_LIMIT_STOP`, host rate `BANK_REPORT`.

#### Left open

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
