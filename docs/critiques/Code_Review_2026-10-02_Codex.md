# Independent code review: nfl-dfs

## 1. Header

**Reviewer/model:** Codex / GPT-6, independent reviewer. **Date:** 2026-10-02. **Reviewed commit:** `ab50652fae16cfb52b377c94a9865cfabbb640d8`. Every source location below refers to that commit, not a moving branch. Findings are ordered by ROADMAP §2.8 tier, then severity. This final version contains eight findings, including three added after the full-corpus standings study. Original finding IDs are preserved; new findings are inserted at their ranked positions.

Work was performed in a fresh, detached managed worktree at `C:\Users\benja\.codex\worktrees\independent-review-oct02\nfl-dfs`. No tracked implementation, test, configuration, input, or ledger file was changed. No claim, commit, push, pull request, or DraftKings fetch was performed. The report is also placed in the original checkout for triage. Test/runtime environments and review evidence remain ignored artifacts in the worktree.

### Execution and limits

Host: Windows, PowerShell, Python **3.13.7**, locked dependency set, eight reported processors. There was no Linux execution environment available through the requested shell: Git Bash invokes Windows Python. Consequently, this is native Windows verification, not Linux acceptance.

| Command or check | Result |
|---|---|
| `git rev-parse HEAD` | SHA above, checked in the review worktree |
| `sh ./nfl.sh setup`, using `C:/Program Files/Git/bin/sh.exe` | Exit 1 after installing the locked dependencies: `project environment is missing`. Windows Python populated `.venv-linux/Scripts`, while this Linux launcher expects `.venv-linux/bin/python`. Package preparation took 26.47 s and installation 5.26 s; total setup wall time was not recorded. |
| `sh ./nfl.sh test --durations=25`, through the same shell | Exit 1, same missing-environment error; no tests ran through this launcher. |
| `uv sync --all-groups --locked --python 3.13.7 --offline`, reusing the downloaded cache | Created the native `.venv`; 39 locked packages installed, installation 4.52 s. |
| `pwsh -NoProfile -File ./nfl.ps1 test --durations=25` | **2,269 passed, 1 failed, 1 skipped**; pytest **987.79 s**, outer wall **991.906 s**, exit 1. |
| `pwsh -NoProfile -File ./nfl.ps1 run-slate --help` | Help available; replay flags checked against it and the runbook. |
| Two historical `run-slate` invocations, below | Both exit 2; both deliver complete legal, distinct, exact-template baselines. Neither reaches model selection. |
| Focused defect reproductions | F-01, F-02 and F-03 reproduced; original shipped Showdown versions independently checked. The follow-up also reproduces F-06/F-07 through the actual structural auditor and optimizer. |
| Full-corpus standings follow-up | 61 inbox files: 56 nonempty contests, 3,200,551 rows, 139 owned entries; all ranks and submitted-lineup joins checked. Four hindsight diagnostic solves optimal at zero gap; chronological salary-only ownership benchmark evaluated on the later PHI–CHI game. Detailed methods, results and limitations below. |
| Three repeated Classic thesis shape tests, timed separately | All three pass; 0.42, 0.43 and 0.42 s call time. Consolidation would save only about 0.85 s; no cleanup finding proposed. |

The full-suite failure is `tests/test_standings_transport.py::test_a_symlink_at_an_inbox_name_is_never_bound`, at line 520. Windows raises **`WinError 1314: A required privilege is not held by the client`** while the test creates its symlink, before exercising the transport. This is an environment-conditioned test failure, not evidence that transport accepted a symlink. The suite is nevertheless **not green** on this host. I did not elevate Windows privileges, alter the test, or reinterpret the failure as a pass. The requested output did not record the skipped test's reason.

The 25 slowest full-suite calls were:

| Seconds | Test (`tests/` prefix omitted) |
|---:|---|
| 22.75 | `test_entry_groups.py::test_the_c2_and_sd3_banks_never_hold_a_forbidden_roster` |
| 19.21 | `test_relaxation_controller.py::test_an_sd3_bank_that_ran_out_is_deepened_before_any_structure` |
| 17.60 | `test_classic_review_c3.py::test_registered_full_fixture_scale_and_exact_entry_order[150]` |
| 16.63 | `test_portfolio_policy.py::test_cowork_policy_is_enforced_audited_snapshotted_and_replays_identically` |
| 13.23 | `test_baseline.py::test_the_supplied_fixtures_deliver_at_1_20_and_150_entries[150-CLASSIC]` |
| 11.92 | `test_relaxation_controller.py::test_rung_4_drops_a_subset_policy_and_fills_every_fillable_row` |
| 11.67 | `test_classic_review_c3.py::test_registered_full_fixture_scale_and_exact_entry_order[1]` |
| 11.62 | `test_baseline.py::test_the_supplied_fixtures_deliver_at_1_20_and_150_entries[150-SHOWDOWN]` |
| 11.28 | `test_classic_review_c3.py::test_registered_full_fixture_scale_and_exact_entry_order[3]` |
| 10.54 | `test_partial_fill.py::test_the_showdown_readable_review_catches_a_fill_that_forgets_the_policys_exclusions` |
| 10.51 | `test_entry_groups.py::test_a_showdown_subset_policy_fills_its_rows_and_sequential_showdown_the_rest` |
| 9.88 | `test_entry_groups.py::test_a_showdown_review_with_a_prefilled_row_ships_and_never_repeats_it[sd3]` |
| 9.79 | `test_classic_review_c3.py::test_registered_full_fixture_scale_and_exact_entry_order[20]` |
| 7.79 | `test_portfolio_enforcement.py::test_run_slate_delivers_an_sd3_limit_incumbent_through_the_showdown_export` |
| 7.70 | `test_contest_assignment_run_slate.py::test_the_policy_audit_reads_a_filled_row_from_the_template_bytes` |
| 7.59 | `test_partial_fill.py::test_the_readable_review_takes_a_named_unfilled_row_and_refuses_an_unnamed_or_forbidden_one` |
| 7.05 | `test_portfolio_enforcement.py::test_five_entry_combined_cap_on_the_top_person_is_satisfied` |
| 6.80 | `test_artifact_preservation.py::test_c3_success_and_c1_exits_report_their_delivery` |
| 6.57 | `test_relaxation_controller.py::test_a_showdown_subset_policy_relaxes_on_its_own_rows_and_the_fill_covers_the_rest` |
| 6.35 | `test_relaxation_controller.py::test_a_showdown_captain_cap_infeasibility_relaxes_and_exports` |
| 6.25 | `test_portfolio_policy.py::test_an_unbound_fill_that_runs_out_of_distinct_lineups_delivers_the_rows_it_built` |
| 6.21 | `test_entry_groups.py::test_a_policys_exclusion_binds_its_rows_and_the_c1_rows_too` |
| 5.91 | `test_portfolio_enforcement.py::test_policy_selection_is_deterministic_end_to_end` |
| 5.81 | `test_relaxation_controller.py::test_a_structural_failure_at_selection_takes_the_next_rung_exactly` |
| 5.39 | `test_contest_assignment_classic.py::test_the_same_inputs_give_the_same_delivered_bytes[c2-c3]` |

Some small investigative computations overlapped the long suite; these durations are observations, not isolated host benchmarks. Both real replays and the final F-02 counterfactual ran after the suite finished.

### Real-slate replays

Only each tracked folder's salary and reserved-entry CSVs were copied into a separate scratch input directory. No reviewed identity file, policy, thesis, manual replacement, or historical run package was supplied to the engine.

The common command was `.venv/Scripts/python.exe -m nfl_dfs.cli run-slate --input-dir <scratch> --profile prior_review --build-priors --label <label> --run-id review-oct02-<label> --as-of <as-of> --delivery-deadline-utc <deadline>`.

| Item | Classic | Showdown |
|---|---|---|
| Label | `wk3-classic-2026-09-27` | `phi-chi-sd-2026-09-28` |
| Scratch input | `data/runs/review-input-wk3-classic-2026-09-27` | `data/runs/review-input-phi-chi-sd-2026-09-28` |
| Salary file | `698b37a9-DKSalaries_117.csv` | `bdc34f2b-DKSalaries_119.csv` |
| Entry file | `de631c27-DKEntries_95.csv` | `5ed750e7-DKEntries_97.csv` |
| `--as-of` | `2026-09-27T15:00:00Z` | `2026-09-28T22:00:00Z` |
| `--delivery-deadline-utc` | `2026-09-27T16:50:00Z` | `2026-09-29T00:05:00Z` |
| Earliest lock parsed from salary bytes | `2026-09-27T17:00:00Z` | `2026-09-29T00:15:00Z` |
| Salary rows / games / authorized entries | 671 / 13 / 25 | 112 / 1 / 36 |
| Outer wall seconds / exit | **6.689 / 2** | **6.240 / 2** |
| Independently checked legal / distinct / template-exact | **25 / 25 / PASS** | **36 / 36 / PASS** |
| Delivered file | `outputs/review-oct02-wk3-classic-2026-09-27/baseline/DK_BASELINE_ENTRY_V1_baseline.csv` | `outputs/review-oct02-phi-chi-sd-2026-09-28/baseline/DK_BASELINE_ENTRY_V1_baseline.csv` |
| Delivered SHA-256 | `463b05abc8a30ff030cc23a1bbaa94f922842d58b5aa91f7757282fc49fb2930` | `cdd0bd92a475af052bf4a962aff6cc7e0a775b28e47b905fdf294e7b047604ec` |

Each delivered CSV was separately reparsed and checked against its original template with `parse_salaries`, `parse_entries`, `validate_lineup`, captain-sensitive `roster_canonical_key`, and `audit_output_bytes`. These are independent invocations of the repository validators, not a claim of a separately implemented certification engine. All authorized rows were accounted for; no duplicate canonical lineup or invalid roster was found.

Recorded stage times, in seconds:

| Stage | Classic | Showdown |
|---|---:|---:|
| Intake | 0.119 | 0.084 |
| Baseline, budget record | 1.575 | 1.760 |
| Baseline, producer's inner measurement | 1.505 | 1.730 |
| Session probe | 0.988 | 1.116 |
| Evidence fetch | 1.018 | 0.643 |
| Review | 1.087 | 0.677 |
| Finish | 0.783 | 0.793 |
| Project / candidate bank / selection / improved export | Not reached | Not reached |

Evidence-fetch time is nested within review; these rows must not be added as disjoint stages. Negative intake start offsets remain the already-queued September review R9 / Session 40 issue.

Both probes reported `CAN_COMPLETE_A_RUN`. The games artifact was fetched, then **PRIORS** stopped at `PriorsBuildError:FETCH_CLOCK_AHEAD_OF_AS_OF:games`. `src/nfl_dfs/priors.py:708-711` rejects an artifact captured more than five minutes after the supplied historical clock. This is a working temporal-evidence gate, not a network outage. I did not backdate a capture, change the clock to post-lock, reuse unrelated source bytes, or bypass the gate. Full model-path performance and real-slate savings from candidate-generation changes therefore remain **unmeasured**.

**No relaxation rung fired.** No policy was supplied, and priors failed before model construction. Both runs named these delivery limitations: `OFFICIAL_STATUS_REQUIRED`, `OFFENSIVE_CURRENT_ROLE_UNRESOLVED`, `WEATHER_CAPTURE_REQUIRED`, `MODEL_NOT_PROSPECTIVELY_VALIDATED`, `IMPROVEMENT_NOT_DELIVERED`, and `DEADLINE_WALL_CLOCK_PAST_DEADLINE`. Their truths were `DELIVERY_STATE=DELIVERABLE`, `delivered_file_valid=true`, top-level `FILE_VALID=false`, `EVIDENCE_STATE=UNKNOWN`, `MODEL_STATUS=PRIOR_ONLY`, `RELEASE_DECISION=DO_NOT_UPLOAD`. The top-level validity value belongs to the unsuccessful review; it must not be substituted for the delivered-file audit or vice versa.

The observed stop required no intervention to preserve or deliver the baseline. Advancing this particular historical replay would require a legitimately frozen pre-lock source package. Later identity/project/select stages were not reached, so their success on these real inputs is not claimed. Traced additional stops include ambiguous identity decisions (`prior_review.py:1993-2045`), unavailable evidence and policy failures; R28 leaves the baseline available. Exact contest payout, advertised value and field size remain Ben-supplied certification facts, not prerequisites for the prior-review baseline. Manual account actions remain outside the engine. F-02 concerns the extra construction work still needed before a satisfactory Showdown handoff.

### Engine output versus shipped work

The Classic folder contains the two inputs and `identity_reviewed_wk3.csv`, but no shipped review-entry CSV or policy. Its reviewed identity file has 671 accepted rows, including six `UNMATCHED` method labels. I did not reuse those historical decisions or infer a shipped Classic portfolio from them. The engine's baseline has a largest person exposure of 7/25 (28%); the folder does not support an exact shipped-versus-generated comparison beyond that.

The Showdown folder contains four review-entry versions, ten policy files, three thesis maps, a sleeve plan, three contest-assignment records, a reviewed identity file, and `keenum_swap.py`. Script summaries, not raw input dumps, produced the comparison:

| Portfolio | Legal / distinct / exact-template | Highest person count | Highest Captain count | Keenum FLEX / Captain | Mean pairwise person overlap |
|---|---|---:|---:|---:|---:|
| Engine's two-file baseline | 36 / 36 / PASS | Smith 35/36 | Keenum 8/36 | Not used as a model-quality claim | Not measured |
| Shipped v1 | 36 / 36 / PASS | Hurts 24/36 | Not needed for comparison | 0 / 0 | 2.929 |
| Shipped v2 | 36 / 36 / PASS | Hurts 24/36 | Not needed for comparison | 0 / 0 | 2.929 |
| Shipped v3 | 36 / 36 / PASS | Hurts 24/36 | Not needed for comparison | 0 / 0 | 3.035 |
| Shipped v4 | 36 / 36 / PASS | Hurts 24/36 | Hurts 8/36 | 9 / 0 | 2.846 |

The automatic baseline also contains Hurts and Barkley in 32/36 each and Bagent in 10/36; it had no depth evidence. The final shipped file has Smith in 21/36, multiple thesis assignments and nine Keenum FLEX appearances. This demonstrates substantial manual construction and iteration, not improved winnings: no outcome comparison was run. R35's 60%/20% defaults were introduced after this September 28 slate, so I do **not** label the historical v4 exposures a retroactive violation. F-01 is a newly reproduced failure when the still-recommended helper is reused, not an allegation that v4 was invalid.

### Context cost, measured in bytes

These are UTF-8 source/output byte budgets at the reviewed checkout, not tokenizer counts or a capture of Claude Code's private prompt assembly. The SessionStart hook was executed with its Git-fetch operation suppressed to keep this review from changing refs; the digest read the actual local state. Description visibility depends on the harness, so both automatic-only and all-description totals are shown.

| Always-present component | Bytes |
|---|---:|
| `CLAUDE.md` | 9,956 |
| Its `@` import, `docs/claude/working.md` | 7,977 |
| `.claude/rules/git-authority.md`, `paths: "**"` | 7,324 |
| `.claude/rules/stops-and-reports.md`, `paths: "**"` | 3,611 |
| Source-file subtotal | **28,868** |
| Measured SessionStart output, 35 lines | 2,056 |
| Automatically eligible skill descriptions | 1,745 |
| All six skill descriptions, including manual-only skills | 2,438 |
| Resulting budget, before other harness metadata | **32,669–33,362** |
| Mandatory `docs/START_HERE.md` read | +7,211 |

Description bytes are advisor 484, close-out 262, dev-session 209, onboard 280, standings-checklist 981 and verify 222. This excludes agent-description metadata, tool definitions and any harness wrappers. File frontmatter/newlines can also change actual injected bytes.

A representative **Showdown operation** reads another 21,512 bytes: START_HERE, the 8,740-byte slate-operation rule, and RUNBOOK lines 280–369 (5,561 bytes). Total is **54,181–54,874 bytes before source inspection or run output**. Reading the older preparation and lock-clock sections adds about 24,900 bytes. The real replay's ordinary console output then adds **36,521 bytes**; Classic adds **40,950 bytes**. Those full reports already exist on disk. F-04 addresses this repeatable output cost.

A representative **S23c development session**, counting the prescribed quick-start/card/brief, first 80 changelog lines, START_HERE, dev-session, verify and close-out skill bodies, adds approximately **38,043 bytes**, or **70,712–71,405 total before code, tests and diffs**. Re-reading CLAUDE.md as the dev-session skill literally requests adds another 9,956 bytes unless the session reuses its loaded copy. This is a procedural estimate, not an observed Claude conversation; additional scoped rules depend on the files touched.

The duplication is concrete: permanent-boundary reminders appear in CLAUDE, START_HERE and the hook; Git authority is summarized in CLAUDE, the always-loaded rule and development/close-out procedures; operating habits repeat the runbook in `slate-operation.md`; the entire Showdown judgment history and procedure is loaded in every session through `working.md`. F-05 removes the last duplication without changing permanent boundaries. Large ledgers are already supposed to be section-read: ROADMAP 252,294 bytes, RUNBOOK 90,514, IMPLEMENTATION_STATUS 87,352 and changelog 386,819. Their total sizes are **not** counted as automatically loaded context, and this review does not recommend reading them whole.

### Coverage and overlap screening

**Read in full:** CLAUDE.md, START_HERE, the September 25 review, working.md; `nfl.sh`, `nfl.ps1`; `src/nfl_dfs/scoring.py`, `byte_lines.py`, `referee.py`, `classic_theses.py`; the Keenum helper; SessionStart hook; Git-authority and stops/report rules; both agent definitions; both GitHub workflow files. Small files were not treated as proof that their callers were safe.

**Read by relevant sections / traced:** ROADMAP §§1, 2.1, 2.2, 2.5 and 2.8 plus affected cards; both required standings reports' findings, definitions and strategy/concentration sections; current IMPLEMENTATION_STATUS and RUNBOOK operating/fallback sections; `cli`, `prior_review`, `selection`, `dk`, `lineups`, `priors`, `offensive_roles`, `qb_depth_roles`, `qb_depth_capture`, `prior_score`, `deadline`, `delivery`, `baseline`, policy generation/enforcement, relaxation, entry groups and contest assignment. Also settings, remaining relevant rules/skills and hook checks, `config/runtime.json`, test inventories and targeted test bodies for these paths. Salary, entry, policy, thesis and run artifacts were processed into summaries. The follow-up programmatically processed every nonempty inbox standings file, all submitted lineups, all 139 owned entries, and the eight same-slate salary sources; raw CSV rows were not loaded into conversational context. `ownership.py` and the structural-bound implementations were also read in full or traced through their callers for this follow-up.

**Not read exhaustively:** the remaining source/scripts bodies, all 93 test files, entire ledgers/contracts, archived changelog/backlog, native Excel internals, external service implementations, or every legacy CLI route. Source/scripts inventory is 94 Python files, about 2.56 MB; the test inventory is about 1.92 MB. Passing tests do not expand this into an exhaustive semantic review. Native Excel acceptance, future live-slate evidence freshness, post-lock operation and Linux execution were not performed.

No new finding duplicates the functional scope of these still-queued items: Session 12 late-swap clock/token work; 40/47 solver budgets, SD3 bank behavior and candidate-rate calibration; 41/42 retrieval and identity/activity discipline; 43 harness holes; 44/44b decomposition and shared truth/report helpers; 45 documentation drift; 46 dead code, legacy commands and workbook duplication; 23c/23d multi-thesis selection and contest economics; 24–29 scenario, tail, survival, ownership and measurement work. F-03 explicitly reopens an incomplete **Complete** session; F-02 identifies a current default absent from the narrowed, deferred S52 card. F-06/F-07 challenge defaults delivered by completed S23/S23e, and F-08 disputes the existing measurement dependencies/ranking rather than requesting a second implementation.

**EDGE/STRATEGY assessment of the existing queue:** the September finding remains true: prior-review selection maximizes deterministic prior points (`selection.py:490`, `:644`, `:712`); no scenario bank, ownership term or ceiling statistic reaches that operating selection. Classic's automatic thesis construction is a real improvement (`cli.py:3095-3099`), but it is a structural diversification heuristic. Pairwise overlap, exposure caps and contest redistribution are not measurements of portfolio P(zero paid), lineup duplication in the field, or leverage.

Judgment: the cheapest defensible path already represented in Sessions 24/24b/25 is a small shared-outcome bank feeding a fixed candidate-scoring seam, followed by a tail-statistic selector and a separate untouched evaluation sample. Fix the registered simulator defects needed by that slice first; increasing scenario counts or inventing an ownership penalty before that does not create an edge. A fixed candidate bank bounds both the engineering scope and any optimization claim. No new general simulator or ownership finding is opened here.

The standings follow-up below supersedes the original review's reliance on the September summaries: all 3.20 million currently available entry rows were regraded. The corpus now has eight slate groups, seven with a large-field reference contest, but still only one complete local payout ladder and no paid-place evidence for the 30 newer contests. It supports addressing concentration and candidate coverage, not precisely calibrating 60%/20% or claiming prospective tail lift. Several apparent construction advantages reverse by game; F-06/F-07 identify specific current exclusions with independently reproduced consequences.

**Categories with no separate new finding:** PERF—real replay timings above, but model-stage savings unmeasured and known solver costs queued; LOW-VALUE—legacy/report duplication already in S46; TEST—retain meaningful baseline, partial-fill, exclusion, mutation and deterministic replay coverage, and do not spend a session merging subsecond shape tests; AUTONOMY—the actual source-clock failure preserved both full baselines, while F-01/F-02 capture the newly actionable manual-construction risks. STRATEGY now has F-08, a dependency/ranking correction grounded in the new local grading, while the scenario/ownership implementations remain in their existing queue. No permanent boundary change is proposed.

Review evidence in the worktree: `outputs/review-audit/pytest.log`, `pytest-meta.json`, the two `review-oct02-*.log` and `*-meta.json` files, `replay-qa.json`, `keenum-repro/result.json`, `cap-repro.json`, `zero-history-repro.json`, `context-bytes.json`, and `thesis-shape-tests.log`. These are diagnostic artifacts, not release artifacts.

### Full-corpus standings study added on 2026-10-02

**Main conclusion.** The newer evidence supports correlated Classic stacks, but rejects treating the original Showdown hygiene bundle as a universal winning shape. PHI–CHI exposes two different failure mechanisms: a hard one-QB policy can exclude the best-performing family, and our actual submitted player union could not reach the reference contest's top 1% even with perfect hindsight. Diversification is necessary for R34, but spreading entries across an inadequate player pool cannot manufacture a competitive ceiling. F-06/F-07 are narrow changes to completed construction work; F-08 corrects the measurement queue's dependencies. The broader scenario/ownership agenda remains in its existing sessions.

#### Corpus, joins and limits

I processed every `.csv` and `.zip` in the requested inbox: **61 files, 56 nonempty contests, 3,200,551 entry rows, 3,190,495 submitted lineups and 10,056 blank entries**. There are eight distinct slate groups: two Classic slates and six Showdown games. DET–BUF is represented only by a 237-entry satellite; the primary large-field comparisons use the largest contest on each of the other seven slates. The 17 Week 3 contests and 12 PHI–CHI contests are repeated observations of the same football outcomes, not 29 independent trials.

The empty placeholders are contests **195677829, 195698960, 195771144, 195777556 and 195779756**. They contain no outcome evidence and were not fetched. Thus this covers all locally available nonempty exports, not every contest ever entered. All 56 exports report `TimeRemaining = 0`; all 3,200,551 ranks reproduce from scores rounded to two decimals, with zero repeated Entry IDs within a contest.

Same-slate salary sources join **100% of submitted rosters**, with no ambiguous name/role keys. I reconstructed position, team, salary and role from those sources, rather than guessing from names or using today's NFL roster. The eight source paths are listed below. DAL–NYG and DEN–KC use their archived entries files' embedded salary tables; those tables support this descriptive join, but are not substitutes for the original downloads' intake provenance or a model replay. All nonblank lineups satisfy the reconstructed salary, person-distinctness and team/game rules. An additional pass checked slot eligibility for **1,882,056 contest-local distinct lineup strings**, finding zero failures. All lineup scores reconstruct from same-slate exported player FPTS within 0.031 points, with no missing score joins; Captain FPTS already include the multiplier and are not multiplied twice.

Ownership is counted from the lineups. In Classic, base-position and FLEX appearances are combined for person exposure; in Showdown, Captain and FLEX retain separate marginals, and their sum is person exposure. The denominator for exported ownership comparisons is all contest entries, while model slot-mass targets condition on submitted lineups. The side tables agree to rounding in 55 contests. In the 47-entry SF–LAR CSV, **195379668**, the only side-table role is `FLEX`, but its percentages represent combined person ownership: Christian McCaffrey is shown at 74.47%, versus 46.81% actually in FLEX. Combining his roles resolves the 27.66-point discrepancy; this is a source-semantics difference, not an instruction to train Captain/FLEX labels from that column. Reconstructed labels avoid it.

`bleeski` is confirmed by 71 exact Entry-ID matches to the existing contest-history export. Across the inbox there are **139 owned entries: 132 submitted, seven blank, zero top-1% finishes**. The history matches all 71 older ranks/scores and the 26 older contests' field sizes. It supplies exact paid-place cutoffs for those 26 contests, with **9/71 paid, $154.25 in observed fees and $98.70 in cash returned**, no ticket winnings. Those figures cover that older subset only. The other **30 contests / 68 owned entries lack current paid-place and winnings evidence**. Their cashing, dollars returned and portfolio P(zero paid) are **DATA BLOCKED**, not zero and not a guessed top-20% cutoff. The newer history file requested during this review was not available when this version was written.

The history source is `C:/Users/benja/Downloads/draftkings-contest-entry-history.csv`, SHA-256 `84ce7a814de29f8939e5ecf7b60a5f32844dfe7c8d079910bb5c1132c9cba6d4`; the `-nfl.csv` copy has identical bytes. All 61 inbox hashes and all eight salary-source hashes were checked again after analysis, with zero changes. The diagnostic `raw-manifest.json` hash is `2a785b07050ab122e5a0152a48ef4c6375930f3a7ae11f22e2d6b6c1e47e2a72`.

| Slate group | Contests / all entries | Our submitted / blank | Our paid | Largest person share | Our best / reference top-1% score |
|---|---:|---:|---:|---:|---:|
| Classic Week 1 | 1 / 832,342 | 20 / 0 | 4 | 35.0% | 196.96 / 209.00 |
| Classic Week 3 | 17 / 891,410 | 25 / 0 | unknown | 32.0% | 181.22 / 187.68 |
| NE–SEA | 1 / 126,020 | 2 / 0 | 2 | 100.0% | 78.84 / 90.52 |
| SF–LAR | 8 / 319,259 | 11 / 0 | 2 | 72.7% | 78.80 / 92.15 |
| DAL–NYG | 8 / 137,879 | 20 / 0 | 1 | 80.0% | 99.80 / 122.10 |
| DEN–KC | 8 / 455,217 | 18 / 0 | 0 | 94.4% | 72.75 / 114.93 |
| DET–BUF satellite | 1 / 237 | 0 / 7 | unknown | not applicable | blank entries |
| PHI–CHI | 12 / 438,187 | 36 / 0 | unknown | 66.7% | 83.71 / 101.71 |

Top 1% means `Rank <= max(1, floor(0.01 * all_entries))`, including the complete boundary tie; top 0.1% uses 0.001. Paid means reaching the contest-history `Places_Paid` cutoff, including a boundary tie. A **lift** below is a feature group's observed top-1% rate divided by the entire submitted field's observed top-1% rate. It is descriptive association, not causal improvement, prospective probability or EV. No row-level significance tests are reported: millions of correlated entries cannot turn seven football outcomes into a large independent sample. No post-lock ownership, points or winner identity is proposed as an operating input.

#### Classic: stack correlation repeats; positional and ownership shortcuts do not

Largest fields: Week 1 **193028206**, Week 3 **195921959**. A pass catcher is a WR/TE on the rostered QB's team; a bring-back is an opposing RB/WR/TE in that QB's game. The table is marginal, not adjusted for player quality, salaries, ownership or other correlated construction choices.

| Construction feature | Week 1 top-1% lift | Week 3 top-1% lift | Week 1 paid lift |
|---|---:|---:|---:|
| QB with no teammate WR/TE | 0.52x | 0.21x | 0.81x |
| QB + one teammate WR/TE | 0.85x | 0.71x | 0.94x |
| QB + two teammate WR/TE | 1.47x | 1.62x | 1.21x |
| QB + three teammate WR/TE | 4.15x | 3.11x | 1.66x |
| No bring-back | 0.62x | 0.78x | 0.87x |
| One bring-back | 1.27x | 1.21x | 1.07x |
| Two bring-backs | 2.47x | 1.95x | 1.55x |
| FLEX = RB | 1.25x | 0.77x | 1.07x |
| FLEX = TE | 0.75x | 1.37x | 1.05x |
| Highest quarter of summed person ownership | 1.58x | 1.91x | 1.31x |
| Lowest quarter of summed person ownership | 0.43x | 0.24x | 0.70x |

**Action for the existing construction/tail queue:** preserve double-stack plus bring-back candidate families and test a bounded triple-stack/two-bring-back family. Do not make every lineup a triple stack: Week 1 has 563 top-1% entries among 13,500 triples; Week 3 has 339 among 10,868. That is two favorable game environments, not an estimated universal benefit. Keep different primary games across the portfolio, then let a shared-outcome scorer compare ceiling and shared failure rather than maximizing the count of stacks.

Do not hardwire RB at FLEX or a universal low-ownership count. TE was **16.0% of top-1% FLEX slots in Week 1, then 60.8% in Week 3**. Zero sub-5%-owned people had 2.07x top-1% lift in Week 1 but 0.73x in Week 3; two such people moved from 0.89x to 1.17x. The repeatable warning is against a blanket ownership penalty: the highest ownership-sum quarter beat the lowest on both slates. Differentiation can come from the correlated combination and Captain role; it does not require filling a lineup with unlikely participants.

Our Classic portfolios were already broadly diversified: mean pairwise people shared **1.13 in Week 1 and 0.93 in Week 3**, with largest person shares 35% and 32%. Week 3's best actual result was 181.22, but a hindsight legal solve over the **103 people we used** reached **247.02**, versus **256.80** over the 646 people with observed scores in the salary pool. Both solves were optimal at zero gap (0.049 s / 0.298 s). This is a diagnostic of available combinations, not an achievable forecast: player coverage was sufficient for a high finish; further global spreading by itself does not address selecting and combining the productive players. It also does not show the current, later S49 implementation caused the historical result.

#### Showdown: captain role, game shape and the current filters

Reference contests are NE–SEA **193391013**, SF–LAR **195390868**, DAL–NYG **195526142**, DEN–KC **195526229**, and PHI–CHI **196036210**. The first four were available to the September study; PHI–CHI is the later temporal check. Captain outcomes vary enough that a universal positional ranking is not supported.

| Game | Most common Captain in top 1% | Share of top-1% entries | Winning Captain | Rank-1 entries / distinct rosters |
|---|---|---:|---|---:|
| NE–SEA | Jaxon Smith-Njigba | 84.6% | Jaxon Smith-Njigba | 23 / 1 |
| SF–LAR | Brock Purdy | 40.7% | Demarcus Robinson | 1 / 1 |
| DAL–NYG | Isaiah Likely | 44.9% | Isaiah Likely | 7 / 2 |
| DEN–KC | Kenneth Walker III | 88.6% | Kenneth Walker III | 206 / 1 |
| PHI–CHI | Case Keenum | 27.4% | Case Keenum | 12 / 1 |

SF–LAR demonstrates why top 1% and winning the tournament are different targets: Purdy dominated the larger cohort while Robinson captained the sole winner. Likewise, a 206-way rank-1 tie is not a 206-way full first prize. In PHI–CHI, Keenum, Luther Burden III and Kalif Raymond captained **1,810/2,552 top-1% entries (70.9%)**, while their actual Captain ownership was **2.82%, 4.25% and 1.45%**. Their combined-person ownership was about **34.1%, 23.9% and 22.5%**: this was leverage in roster role among credible field plays, not a lineup of six obscure people. **2,532/2,552** PHI–CHI top-1% lineups contained no person below 5% combined ownership. Our 36 entries had no Keenum, Burden or Raymond Captain; Burden did appear in FLEX 12 times and Keenum nine times. This is historical evidence for R35's role-coverage judgment, not permission to override R36's evidence gates or a claim those winners were knowable.

| Game | One-QB top-1% lift | Two-QB top-1% lift | Top-1% entries rejected by same-team DST veto | Top-1% entries passing full default single-lineup filter |
|---|---:|---:|---:|---:|
| NE–SEA | 1.50x | 0.11x | 67.7% | 21.7% |
| SF–LAR | 1.64x | 0.03x | 40.1% | 30.5% |
| DAL–NYG | 0.73x | 1.45x | 5.3% | 8.9% |
| DEN–KC | 1.15x | 0.95x | 81.9% | 1.4% |
| PHI–CHI | 0.38x | 2.97x | 24.9% | 3.3% |

The reconstructed default filter is one QB, one to two teammate WR/TE, at most one K and one DST, $1–$500 left, no K/DST Captain, and no non-DST person on a rostered DST's team. It omits portfolio caps and evidence exclusions, so its retention is an upper bound before those restrictions. It admits **none of the winning rosters in these five reference fields**. That does not prove every part should be removed: passing lineups still had roughly 2.3x top-1% lift in the first two games, but only **0.15x in DEN–KC and 0.33x in PHI–CHI**. The actual implemented bundle does not support ROADMAP's universal favorable-lift description. F-06 isolates the teammate-DST veto; F-07 opens the two-QB family. Do not silently reinterpret an old policy or relax evidence/distinctness.

Broader game shapes also trade the two R34 goals differently. A 5–1 team split had **2.67x top-1% lift but 0.74x paid lift in SF–LAR**; in DEN–KC it had **2.39x / 1.62x**; in NE–SEA **0.13x / 1.09x**. A balanced split is not intrinsically safer in every game, nor is an onslaught intrinsically higher ceiling. For S23c, test separate game-thesis families against the same simulated outcomes; do not assign a winning-family percentage from this five-game sample. The salary-left evidence also does not justify treating $50,000 spent as invalid: that group had 2.06x top-1% lift in DAL–NYG and 1.06x in PHI–CHI, but zero top-1% entries in NE–SEA and DEN–KC. Keep salary usage a measured feature and thesis preference, never a substitute for projected quality and copy-count estimation.

#### Our PHI–CHI player pool could not reach the tail

An Entry-ID and Captain-aware comparison finds **36/36 submitted PHI–CHI rosters match `DK_REVIEW_ENTRY_phi-chi-sd-v4.csv`**, versus 0/36 in v1, 0/36 in v2 and 2/36 in v3. This confirms which archived artifact actually reached the contest. It does not contradict F-01: that finding concerns reusing the helper, not illegality in the original v4.

I solved one hindsight diagnostic with only DraftKings lineup constraints, actual same-slate FPTS, zero MIP gap, and every Captain/FLEX role for the **16 people present anywhere in our submitted portfolio**. All their role scores are observed. The best possible score was **96.14**, below the reference top-1% cutoff **101.71**. The actual best entry was **83.71**. Opening the pool to all 53 people with observed scores yielded **115.64**, matching the winning score. The solves took 0.182 s / 0.064 s and validated as legal. Unobserved-score people were excluded from the wider comparison rather than assigned fabricated points; the restricted-pool upper bound covers every role of all 16 people we actually used.

Kalif Raymond and the Bears defense were absent from all 36 entries, while both appear in the winning roster. Our exposures included Odunze **55.6% versus 13.0% field person ownership**, Loveland **55.6% versus 21.2%**, and Santos **58.3% versus 22.9%**. These are realized exposure comparisons, not ex ante leverage estimates. The group had 16 people, ten different Captains, 36 distinct rosters and only 2.85 people shared on average—yet no rearrangement of that pool could reach the reference top 1%. **Player-union coverage, Captain-role coverage and lineup combination quality deserve separate diagnostics from exposure concentration.** Add these retrospective decompositions to S18b; they identify where to inspect eligibility, projection, bank generation and selection without pretending hindsight winners should have been forced in.

Seven of our DET–BUF satellite entries have a blank lineup, zero points and rank 230/237. Their reserved-entry template lists $0.10 per entry, but the available history does not establish whether fees were charged, refunded or awarded. This is a concrete historical failure to field a lineup in the export, not proof of a defect in today's baseline-first path or authority to infer a lost fee. Investigate the local handoff/upload history under S14/O9; no new code bug is assigned without the missing provenance.

#### Ownership and duplication: measured challenger, limited validation

The existing ownership and copy-count sessions remain necessary, but should consume correct role labels and archived forecasts. A simple chronological benchmark here used salary only, no FPTS, future participation information or held-out ownership as a feature. For each Showdown role, probabilities were proportional to `salary^beta`, normalized to mass 1 for Captain and 5 for FLEX with each marginal capped at 1. All salary-pool people were retained. A fixed beta grid 0–8 by 0.25 minimized equal-game mean squared error on **NE–SEA, SF–LAR, DAL–NYG and DEN–KC**; PHI–CHI was used only for evaluation. The fitted exponents were **3.75 Captain and 1.75 FLEX**.

| Ownership model | PHI–CHI Captain MAE / RMSE, percentage points | PHI–CHI FLEX MAE / RMSE, percentage points |
|---|---:|---:|
| Uniform over the same salary pool | 2.63 / 4.51 | 11.29 / 14.40 |
| Salary squared, fixed before fitting | 1.52 / 3.13 | 6.11 / 10.76 |
| Role-specific exponent fitted on four earlier games | 1.21 / 2.69 | 6.24 / 10.53 |

This is a **retrospectively reconstructed chronological benchmark**, not prospective calibration of the current engine. The salary-only models rank the same expensive players, so top-five recall does not demonstrate added discrimination; FLEX MAE is slightly worse after fitting even though the selected MSE improves. The fitted Captain model assigns 16.1 percentage points of mass to people actually captained zero times. Salary alone cannot distinguish an active starter from an unavailable player or backup, but zero realized ownership does not prove which explanation applies. Actual zero ownership is an evaluation label, never an eligibility rule. S26 should compare against this cheap baseline, then add pre-lock, hash-bound participation/depth and opportunity information. Maintain separate Captain and FLEX calibration and report errors over the full eligible pool, not just the people selected by our engine. One later game is insufficient to promote the exponents to production.

Classic needs a shared, slate-dependent FLEX model rather than its hardwired ownership mass. The two submitted fields' average `(RB, WR, TE)` counts were **(2.425, 3.361, 1.214)** and **(2.321, 3.234, 1.445)**; `ownership.py:59-61` fixes them at **(2.5, 3.5, 1.0)**. TE mass 1.0 cannot describe a field using a second TE. This was already identified in the September greenfield work, so it is not a duplicate new finding. Extend S26's acceptance to both slates, fit a common FLEX distribution used by ownership and field generation, and grade the resulting marginals after salary/legality filtering. Do not simply hardcode either observed week's mix.

Uniqueness against opponents is not automatically valuable. In the five Showdown reference contests only **2.4%, 3.8%, 1.9%, 0.45% and 1.49%** of top-1% entries were unique in their field; Week 1 and Week 3 Classic were both about **85.1%**. Our PHI–CHI entries were 80.6% unique and still all missed the reference tail. R29's rule against duplicating our own lineups stands. For S27/S29, estimate opponent copy counts and eventual payout dilution conditional on being competitive; do not reward arbitrary rarity or use ownership-sum as a lineup probability. Only NE–SEA has a complete local payout ladder, so no new dollar-return claims are made for the other fields.

#### Cashing, washout and the next experiment

Historical concentration correlates with washout, but this sample does not identify an optimal universal cap. Among reference-contest entrants with at least ten submitted lineups, observed zero-paid portfolio rates for **largest person share below 70% versus at least 85%** were: Week 1 Classic **6.9% / 20.1%**, NE–SEA **2.4% / 11.1%**, SF–LAR **1.0% / 18.9%**, DAL–NYG **2.0% / 6.7%**, DEN–KC **2.1% / 16.1%**. These bands differ in entry count, player choices and skill; they are not randomized equal-budget portfolios. DAL–NYG also shows the tradeoff: the higher-concentration band more often reached top 1% (**18.5% versus 9.2%**), despite more washouts. The later PHI–CHI any-top-1% rates were **64.4% versus 29.6%**, but cashing cannot be graded there without its paid places.

For the queued S18b/S25b/S28 measurement, use **slate as the holdout unit**, retain the Captain/FLEX roles, and compare equal entry counts and budgets. Freeze candidate banks and pre-lock projection/ownership artifacts before outcomes. Report top 1%, top 0.1%, best rank and tie/copy counts separately from the exact paid-line cutoff and zero-paid portfolio rate; add dollars only with the full ladder. A simulated P(zero paid) remains a bank estimate, not validated real-world probability. Keep September 27–28 as the fixed historical temporal test already inspected, then use later untouched slates for genuine forward evaluation—these results can no longer be an untouched holdout for a new rule designed from them.

**Recommended sequence, as judgment:** fix F-01's publishing hazard; remove the two narrow search-space restrictions in F-06/F-07 and close F-02/F-03's default/eligibility gaps; unblock local grading under F-08; then implement the smallest already-queued shared-outcome/tail-scoring slice and a role-aware ownership challenger. R35's deterministic/judgment split is workable if Claude names evidenced candidate people or game theses and the engine evaluates every candidate on the same numeric basis. This evidence does not support allowing Claude to write numeric projections from prose. Stop adding static captain quotas, copying the full historical hygiene bundle into new modes, or polishing exposure displays as though those measured washout. Preserve the early legal distinct baseline and every evidence gate throughout.

#### Reproduction and all-contest audit

The data work ran locally; no DraftKings URL, account state or contest API was accessed. Scripts and diagnostic summaries are in the isolated review worktree at `outputs/review-audit/standings-20261002/`: `inventory.py`, `core.py`, `analyze.py`, `supplement.py`, `challenger.py`, `engine_repro.py`; outputs include `raw-manifest.json`, `contests.json`, `feature-stats.json`, `checks.json`, `ownership-challenger.json`, `engine-structural-repro.json`, `submission-match.json` and `final-qa.json`. They are ignored analysis artifacts, not production modules or release artifacts. Source inputs and production code were not changed. Overall study wall time was not captured, so no runtime benchmark is inferred from the exploratory scripts; the solver diagnostic times above are measured.

To rerun, use the worktree as the working directory. Run `inventory.py`, `analyze.py`, `supplement.py`, then `challenger.py` with a Python environment containing pandas and NumPy; run `engine_repro.py` with the pinned `.venv/Scripts/python.exe`. The audit used the bundled analysis Python for the former and the repository's installed HiGHS runtime for the latter. The scripts explicitly read the user's primary inbox path. Expected totals: 56 contests, 139 owned rows, 132 submitted owned rows, zero rank/identity/score/slot failures, and the 96.14 PHI–CHI own-pool bound. These scripts preserve raw inputs and write only beneath the ignored audit directory. The report's definitions and findings' acceptance criteria are self-contained so the maintainer can implement a production grader without adopting the exploratory scripts.

Same-slate source paths, relative to the primary checkout:

| Group | Salary or embedded salary source |
|---|---|
| CLASSIC_W1 | `data/runs/20260913-week1-portfolio/inputs/DKSalaries.csv` |
| CLASSIC_W3 | `data/inbox/slates/wk3-classic-2026-09-27/698b37a9-DKSalaries_117.csv` |
| NE_SEA | `data/runs/20260909-showdown-ne-sea/inputs/DKSalaries_NE_SEA.csv` |
| SF_LAR | `data/runs/20260910-showdown-sf-lar/inputs/DKSalaries_SF_LAR.csv` |
| DAL_NYG | `Claude outputs/DKEntries_DAL_NYG_20lineups_REVIEW_v6.csv` (embedded table) |
| DEN_KC | `DKEntries_DEN_KC_18lineups_v6.csv` (embedded table) |
| DET_BUF | `data/inbox/slates/det-buf-2026-09-17/7c85ca11-DKSalaries_97.csv` |
| PHI_CHI | `data/inbox/slates/phi-chi-sd-2026-09-28/bdc34f2b-DKSalaries_119.csv` |

Every nonempty contest is listed below; the five empty placeholders are identified above. Our top-1% count is zero in every row. A paid-place number indicates evidence availability, not a reconstructed payout ladder. For small fields, the stated top-1% convention becomes rank 1 and is not used to extrapolate large-field strategy.

| Slate | Contest | Entries | Our submitted / blank | Known paid places | Our paid | Top-1% cutoff |
|---|---:|---:|---:|---:|---:|---:|
| CLASSIC_W1 | 193028206 | 832,342 | 20 / 0 | 173275 | 4 | 209.00 |
| CLASSIC_W3 | 195905123 | 148,632 | 1 / 0 | unknown | unknown | 186.50 |
| CLASSIC_W3 | 195914853 | 55,872 | 1 / 0 | unknown | unknown | 180.06 |
| CLASSIC_W3 | 195914862 | 58,890 | 1 / 0 | unknown | unknown | 178.84 |
| CLASSIC_W3 | 195921959 | 416,171 | 1 / 0 | unknown | unknown | 187.68 |
| CLASSIC_W3 | 195921960 | 95,124 | 2 / 0 | unknown | unknown | 186.30 |
| CLASSIC_W3 | 195921961 | 89,179 | 2 / 0 | unknown | unknown | 185.10 |
| CLASSIC_W3 | 195921991 | 17,835 | 1 / 0 | unknown | unknown | 184.90 |
| CLASSIC_W3 | 195922612 | 71 | 2 / 0 | unknown | unknown | 199.48 |
| CLASSIC_W3 | 195922629 | 92 | 2 / 0 | unknown | unknown | 199.48 |
| CLASSIC_W3 | 195922640 | 74 | 2 / 0 | unknown | unknown | 188.94 |
| CLASSIC_W3 | 195922662 | 85 | 2 / 0 | unknown | unknown | 188.94 |
| CLASSIC_W3 | 195956083 | 59 | 1 / 0 | unknown | unknown | 178.94 |
| CLASSIC_W3 | 196104830 | 95 | 2 / 0 | unknown | unknown | 198.92 |
| CLASSIC_W3 | 196114372 | 200 | 1 / 0 | unknown | unknown | 186.26 |
| CLASSIC_W3 | 196123932 | 57 | 1 / 0 | unknown | unknown | 187.00 |
| CLASSIC_W3 | 196125845 | 57 | 1 / 0 | unknown | unknown | 176.90 |
| CLASSIC_W3 | 196128137 | 8,917 | 2 / 0 | unknown | unknown | 184.70 |
| DAL_NYG | 195520918 | 475 | 1 / 0 | 1 | 0 | 122.10 |
| DAL_NYG | 195521582 | 237 | 7 / 0 | 1 | 0 | 120.80 |
| DAL_NYG | 195526142 | 59,453 | 1 / 0 | 15950 | 0 | 122.10 |
| DAL_NYG | 195526144 | 35,671 | 2 / 0 | 8550 | 1 | 122.10 |
| DAL_NYG | 195526145 | 35,671 | 2 / 0 | 8545 | 0 | 122.10 |
| DAL_NYG | 195526163 | 5,945 | 1 / 0 | 1543 | 0 | 122.10 |
| DAL_NYG | 195641911 | 237 | 1 / 0 | 5 | 0 | 121.20 |
| DAL_NYG | 195642262 | 190 | 5 / 0 | 2 | 0 | 122.10 |
| DEN_KC | 195521607 | 95 | 2 / 0 | 1 | 0 | 119.31 |
| DEN_KC | 195526229 | 237,812 | 1 / 0 | 49940 | 0 | 114.93 |
| DEN_KC | 195526255 | 89,179 | 1 / 0 | 24076 | 0 | 115.51 |
| DEN_KC | 195526256 | 59,453 | 2 / 0 | 14265 | 0 | 114.41 |
| DEN_KC | 195526257 | 59,453 | 2 / 0 | 14240 | 0 | 112.95 |
| DEN_KC | 195526271 | 8,917 | 1 / 0 | 2305 | 0 | 111.35 |
| DEN_KC | 195663904 | 237 | 7 / 0 | 1 | 0 | 119.51 |
| DEN_KC | 195665148 | 71 | 2 / 0 | 1 | 0 | 116.05 |
| DET_BUF | 195778307 | 237 | 0 / 7 | unknown | unknown | 171.91 |
| NE_SEA | 193391013 | 126,020 | 2 / 0 | 26495 | 2 | 90.52 |
| PHI_CHI | 196036210 | 237,812 | 1 / 0 | unknown | unknown | 101.71 |
| PHI_CHI | 196036242 | 83,234 | 1 / 0 | unknown | unknown | 100.40 |
| PHI_CHI | 196036243 | 47,562 | 2 / 0 | unknown | unknown | 100.90 |
| PHI_CHI | 196036244 | 59,453 | 2 / 0 | unknown | unknown | 100.40 |
| PHI_CHI | 196036260 | 8,917 | 1 / 0 | unknown | unknown | 97.60 |
| PHI_CHI | 196039118 | 237 | 2 / 0 | unknown | unknown | 96.30 |
| PHI_CHI | 196039211 | 95 | 2 / 0 | unknown | unknown | 104.38 |
| PHI_CHI | 196040020 | 71 | 2 / 0 | unknown | unknown | 103.00 |
| PHI_CHI | 196040036 | 237 | 7 / 0 | unknown | unknown | 108.84 |
| PHI_CHI | 196040037 | 95 | 2 / 0 | unknown | unknown | 97.00 |
| PHI_CHI | 196040050 | 237 | 7 / 0 | unknown | unknown | 100.90 |
| PHI_CHI | 196172224 | 237 | 7 / 0 | unknown | unknown | 96.30 |
| SF_LAR | 195379585 | 237 | 2 / 0 | 55 | 0 | 86.30 |
| SF_LAR | 195379668 | 47 | 1 / 0 | 2 | 0 | 81.30 |
| SF_LAR | 195384501 | 71 | 2 / 0 | 1 | 0 | 94.75 |
| SF_LAR | 195390867 | 83,234 | 1 / 0 | 22471 | 0 | 90.55 |
| SF_LAR | 195390868 | 178,359 | 1 / 0 | 37455 | 0 | 92.15 |
| SF_LAR | 195390870 | 47,562 | 2 / 0 | 11405 | 1 | 90.30 |
| SF_LAR | 195390889 | 9,512 | 1 / 0 | 2247 | 1 | 89.35 |
| SF_LAR | 195507184 | 237 | 1 / 0 | 5 | 0 | 94.35 |


## 2. Summary table

| ID | Category | Severity | Tier | Effort | Confidence | One line | Overlap |
|---|---|---|---|---|---|---|---|
| F-01 | BUG | BLOCKER | 1 | S | REPRODUCED | Reusing the Keenum helper can publish a roster containing the same person twice. | New helper defect; S37 does not cover it. |
| F-02 | EDGE | MEDIUM | 2 | M | REPRODUCED | Automatic Showdown selection can retain 100% exposures despite feasible R35 caps. | S23 Complete; narrowed S52 Deferred does not implement concentration. |
| F-06 | EDGE | MEDIUM | 2 | S | REPRODUCED | Default policies exclude defenses paired with their own productive teammates. | S23/S23e Complete; implemented default challenged with field evidence. |
| F-07 | EDGE | MEDIUM | 2 | S | REPRODUCED | One-QB default excludes the leading PHI–CHI tail family until relaxation. | S23 Complete; distinct from S23c multi-thesis allocation. |
| F-03 | BUG | MEDIUM | 3 | S | REPRODUCED | A depth-declared QB with observed zero history is still excluded. | S54 Complete, incomplete coverage of the R36 case. |
| F-08 | STRATEGY | MEDIUM | 7 | S | INFERRED | Local strategy grading waits unnecessarily for cloud publication and scenarios. | S18/S18b/S26 dependency and ranking correction; requires BEN ruling. |
| F-04 | TOKEN | LOW | 9 | M | REPRODUCED | Console output repeats 36–41 KB reports that can have a bounded handoff. | New; distinct from S44b report internals. |
| F-05 | TOKEN | LOW | 9 | S | REPRODUCED | Every session loads 3,275 bytes of Showdown-only procedure and history. | New post-September-review addition. |

## 3. Findings

### F-01: Validate every Keenum substitution before publishing

| Field | Value |
|---|---|
| Category | BUG |
| Severity | BLOCKER |
| Class | V |
| Tier | 1 (docs/ROADMAP.md §2.8) |
| Effort | S |
| Confidence | REPRODUCED |
| Location | `data/inbox/slates/phi-chi-sd-2026-09-28/keenum_swap.py:22-55` at ab50652fae16cfb52b377c94a9865cfabbb640d8; active recommendation `docs/claude/working.md:70-75` |
| Overlap | New. This September 28 helper postdates the September 25 review. Session 37's completed Showdown writer repairs do not protect this writer; deferred Session 52 leaves its manual route in use. |
| Requires | none |
| Depends on | none |
| Decision | **Accepted, modified** (2026-10-02 triage). Session 55. Re-graded HIGH, tier 1 kept: DraftKings refuses a repeated person at upload, so the reachable harm is a refused file under the lock clock, not a lost fee. The fix is a `scripts/` tool (validate every row, captain-sensitive canonical keys, exclusive create, no file on any invalid row), and `docs/claude/working.md` points at it; `keenum_swap.py` stays untouched as the record of what shipped on 2026-09-28. Verified here: `keenum_swap.py:32` builds the new roster without checking the person is already in it. |

**Issue.** `options()` can replace another FLEX with Keenum even when that lineup already contains him. The helper checks salary, teams, inter-lineup overlap and ordered roster tuples, but never checks that a roster contains six distinct people. It writes the new CSV and exits successfully; the operating instructions still recommend this helper for left-out starters.

**Evidence.** Reusing the helper on the tracked, independently valid v4 produces **two invalid rows**, Entry IDs `5274843728` and `5274846778`, both `LINEUP_PERSON_REPEATED`, while exiting **0**. Thirteen rows were selected for edits. The synthetic empty score map below is accepted by the helper's explicit missing-score default; it supplies no invented projection and isolates the missing validity check. Run this Python from the repo root with the pinned environment:

```python
import csv, json, subprocess, sys, tempfile
from pathlib import Path
from nfl_dfs.dk import parse_salaries
from nfl_dfs.lineups import validate_lineup
d = Path('data/inbox/slates/phi-chi-sd-2026-09-28')
o = Path(tempfile.mkdtemp(prefix='review-keenum-', dir='outputs'))
(o/'scores.json').write_text('{"by_dk_id":{}}')
salary = next(d.glob('*DKSalaries*'))
cmd = [sys.executable, str(d/'keenum_swap.py'), str(salary), str(d/'DK_REVIEW_ENTRY_phi-chi-sd-v4.csv'), str(d/'theses_v3.json'), str(o/'scores.json'), '36', str(o/'repeat.csv')]
r = subprocess.run(cmd, capture_output=True, text=True)
s = parse_salaries(salary)
rows = list(csv.reader((o/'repeat.csv').open(encoding='utf-8-sig', newline='')))
bad = [(x[0], validate_lineup(s, x[4:10]).errors) for x in rows if x and x[0].isdigit() and not validate_lineup(s, x[4:10]).valid]
print(r.returncode, len(json.loads(r.stdout)['chosen']), bad)
```

**Why it matters.** The reachable result is a wrong entry file placed in front of Ben on the manual rescue path, precisely when there is little time for another iteration. It is not merely a concentration preference or an unmet evidence gate. The original shipped v4 remains valid; this is the helper's failure to make reuse safe.

**Recommendation.** In this helper, reject a substitution when the underlying Keenum person is already present, and run `validate_lineup` over every resulting row before opening the output path. Enforce cross-row distinctness with `roster_canonical_key`, not the order of FLEX cells. Refuse the whole new publication on validation failure, retaining its existing exclusive-create behavior and the prior file. This is a bounded safety repair while the helper remains an active operating route.

**Acceptance.** Add a focused helper test that starts with Keenum already in FLEX, and another with him in Captain; neither may publish a repeated person. Test an invalid resulting roster and a FLEX-permuted duplicate: nonzero result, no new CSV. A valid substitution must retain the original entry metadata and non-roster bytes, all rows legal, and all captain-sensitive canonical keys distinct. The reproduction above must no longer produce any invalid published row. Keep the test under five seconds; it needs no solver or network.

**Risk.** Some currently accepted helper outputs will be refused, and fewer substitutions may be possible. Do not respond by loosening R29 or deleting the previous delivered file. The general blank-template writer cannot simply be applied to this filled-template edit without explicitly preserving the helper's authorized cells.

### F-02: Apply R35 caps to automatic Showdown construction

| Field | Value |
|---|---|
| Category | EDGE |
| Severity | MEDIUM |
| Class | S |
| Tier | 2 (docs/ROADMAP.md §2.8) |
| Effort | M |
| Confidence | REPRODUCED |
| Location | `src/nfl_dfs/selection.py:870-1095`, `scripts/make_showdown_policy.py:126-129`, `src/nfl_dfs/cli.py:3095-3099` at ab50652fae16cfb52b377c94a9865cfabbb640d8 |
| Overlap | Session 23 is Complete, but its generator still defaults to 80% person / 40% Captain. S52 is Deferred and now concerns adding excluded people, not applying concentration limits. This is distinct from pending S23c's multi-thesis allocation and old review S7's single-Captain defect. |
| Requires | none; implements existing R35/R36 concentration preferences |
| Depends on | none |
| Decision | **Accepted** (2026-10-02 triage). Session 56: the 60%/20% defaults registered once, applied to the no-policy Showdown path and the generator, relaxed by the ladder (0.80/0.40, then off) before any structural rung, requested and effective caps reported. Session 23c now depends on it. Verified here: generator defaults 0.80/0.40 at `make_showdown_policy.py:126-129`; `selection.py` only reports `captain_exposure`. |

**Issue.** R35 requires action on concentration before handoff, with current defaults of 60% per person and 20% per Captain. The automatic no-policy Showdown selector has exact-roster and overlap/Captain-diversification machinery but no aggregate person/Captain caps, while the supplied policy generator still uses 80%/40%. As a result, deterministic code leaves a known, numeric construction rule to manual row surgery even when a feasible capped portfolio exists.

**Evidence.** A synthetic, hash-bound depth-evidence fixture already in `test_declared_starter_selectable` produces 20 legal, distinct lineups with **two receivers in 20/20** and a Captain in **7/20**. The same model/pool with the existing policy mechanism set to 60%/20% produces **20 legal, distinct**, maximum person **12/20**, maximum Captain **4/20**. Measured separately after the suite: 1.297 s unbound and 14.037 s capped; this demonstrates feasibility, not a real-slate speed promise. Reproduction:

```python
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
from tests import test_declared_starter_selectable as t
from tests.test_portfolio_enforcement import _policy
with TemporaryDirectory() as tmp:
    w = t._world(Path(tmp)); ids = {p.dk_id:p.underlying_id for p in w[0].players}
    p, _ = _policy(w[0], tuple(str(i) for i in range(20)), max_combined_person_exposure={'default_fraction':.6,'overrides':[]}, max_captain_exposure={'default_fraction':.2,'overrides':[]}, max_pairwise_person_overlap=4)
    for kw in ({}, dict(portfolio_policy=p, policy_candidate_limit=120, policy_candidate_seconds=30, policy_selection_seconds=15)):
        ls, _, _ = t._select(w, count=20, **kw)
        people = Counter(ids[x] for l in ls for x in l.roster)
        captains = Counter(ids[l.roster[0]] for l in ls)
        print(len(ls), len({l.canonical_key for l in ls}), max(people.values()), max(captains.values()))
```

The real two-file Showdown replay stops earlier and retains a baseline with Smith in 35/36; that establishes fallback concentration, not model-selector performance. R35/R36 are explicit at `docs/ROADMAP.md:2337-2364`; the manual repair is at `docs/claude/working.md:76-82`.

**Why it matters.** One player can remain a failure point shared by every nominally distinct entry. The dual-objective report's concentration comparison (`docs/STANDINGS_DUAL_OPTIMIZATION_FINDINGS_2026-09-15.md:11`, `:245-260`) associates 85%+ exposure with higher zero-paid rates in all four Showdown games, while acknowledging skill confounding. That supports a diversification control, not a claim that exactly 60% maximizes winnings. The practical cost is repeated manual rebuilding before each handoff.

**Recommendation.** Register the current defaults once and apply them automatically to the ordinary no-policy Showdown improvement path, using bounded construction with the same controls the policy audit reads. Make the policy generator use those defaults too. Record requested and effective caps and any named relaxation; carry an already-relaxed rung forward so it does not silently reapply tighter defaults. Preserve the immediate baseline, and allow deadline/pool infeasibility to leave it as the delivered file with a named concentration limitation. Do not wait for S52's excluded-player trigger to implement this deterministic rule.

**Acceptance.** Add a no-policy Showdown `run-slate` acceptance case using synthetic pre-lock sources and enough time: all 20 rows legal/distinct, person count at most 12, Captain count at most 4, with the audit recomputing both from delivered bytes. Test explicit policy overrides, a genuinely infeasible small pool, and a short deadline; the last two must deliver an available legal distinct baseline and explain the relaxed preference, without weakening activity/identity gates. Retain the feasible counterexample above, and budget its bounded selection test at 30 seconds on the pinned host rather than an unbounded full bank.

**Risk.** Tighter preferences can reduce total prior points, exhaust a bounded bank, or increase solve time. Those are reasons for explicit relaxation and baseline retention, not reasons to certify a constrained portfolio as optimal or to relax distinctness. This is not a substitute for shared-outcome washout measurement.

### F-06: Stop banning defenses with their own teammates

| Field | Value |
|---|---|
| Category | EDGE |
| Severity | MEDIUM |
| Class | S |
| Tier | 2 (docs/ROADMAP.md §2.8) |
| Effort | S |
| Confidence | REPRODUCED |
| Location | `scripts/make_showdown_policy.py:151-154`, `src/nfl_dfs/relaxation.py:248-255`, `src/nfl_dfs/relaxation.py:349-358`, `src/nfl_dfs/portfolio_policy.py:102-139`, `src/nfl_dfs/optimizer.py:325-344` at ab50652fae16cfb52b377c94a9865cfabbb640d8 |
| Overlap | ROADMAP Sessions 23 and 23e are Complete. This challenges their implemented default using reconstructed field results; it is not the still-pending multi-thesis or tail-selector work, and is absent from the 2026-09-25 review. |
| Requires | none |
| Depends on | none |
| Decision | **Accepted** (2026-10-02 triage). Session 57, with F-07: new default policies in both modes leave `offense_against_own_dst` open; explicit and frozen policies, the auditors and the relaxation table keep their meaning. The §2.8 endorsement of the hygiene bundle is narrowed in that section to the bundle, not this component. Verified here: default on at `make_showdown_policy.py:151-154`; the Showdown ladder drops it only at rung 2 (`relaxation.py:519`). The field counts are the review's; Session 18's local mode reproduces them. |

**Issue.** The default `offense_against_own_dst` control prohibits any non-DST player—including a kicker—from sharing the selected defense's team. It does not mean an offensive player facing the opposing defense. This intentionally implemented preference rules out useful game-script combinations before either projection quality or a future tail objective can evaluate them; the roadmap's favorable hygiene claim does not validate this particular restriction.

**Evidence.** The auditor and optimizer agree on the same-team predicate. The smallest consequential code is:

```python
dst_teams = {row.team for row in rows if row.position == "DST"}
if any(row.team in dst_teams and row.position != "DST" for row in rows):
    violations.append("offense_against_own_dst")
```

In the isolated worktree, `.venv/Scripts/python.exe outputs/review-audit/standings-20261002/engine_repro.py` reconstructs the rank-1 NE–SEA and PHI–CHI rosters from their exports and same-slate salaries, validates them with `validate_lineup`, then fixes all six IDs in `LineupOptimizer`. With only this structural bound enabled, both return **`dk_valid=True`, violations `['offense_against_own_dst']`, solve `INFEASIBLE`**; with open bounds, both solve `OPTIMAL`. Independently counted field exclusions are **854/1,261 top-1% entries in NE–SEA, 1,982/2,420 in DEN–KC and 636/2,552 in PHI–CHI**. All rank-1 entries in those three games violate the restriction. Classic Week 1 and Week 3 also lose 22.1% and 13.0% of their top-1% entries to this predicate, though that alone does not establish positive correlation in every Classic game.

**Why it matters.** The engine can leave defenses nominally in its pool while forbidding the teammate combinations that made them useful. A feasible restricted bank never reaches the rung that drops this preference. This is an R34 search-space loss on completed construction work, not a statement that any particular defense would have been predictable or that including it would guarantee a prize.

**Recommendation.** Set the same-team veto to **false for newly generated default policies in both modes**. Change the Showdown argument default and the Classic generator's emitted `classic_rung_controls` bounds; leave the existing policy field, auditors, MILP interpretation and relaxation table semantics intact for explicitly supplied/frozen policies. Do not silently invert the old Boolean to mean opposing offense: that would change saved policies' meaning. Document the default change and retire the roadmap's blanket endorsement of this component. A separately named opponent-correlation preference can be considered later from evidence.

**Acceptance.** Add a focused generator/constraint test for each mode: default generated controls leave this bound open, an explicitly true legacy policy still forbids same-team non-DST players, and a false policy permits them. Use the legal NE–SEA winner as a fixed-roster Showdown regression and a legal Classic RB-plus-own-DST fixture; assert legality and the bound's isolated behavior, not a whole golden portfolio. Re-run the actual engine reproduction and retain its legacy-true rejection while the new default accepts the same roster subject to its other independently specified controls. Frozen-policy replay anchors, R29 keys and all evidence decisions remain unchanged. Target under five seconds for these focused tests.

**Risk.** New candidate banks and selected rosters change, and a larger admissible space can use more solver time. Monitor existing deadline limits and compare bank coverage. Applying the change inside the old Boolean's parser or relaxation interpretation would break replay meaning; changing only new defaults avoids that. F-07 independently changes QB eligibility and is not required to prove this predicate's defect.

### F-07: Admit two quarterbacks in default Showdown candidate banks

| Field | Value |
|---|---|
| Category | EDGE |
| Severity | MEDIUM |
| Class | S |
| Tier | 2 (docs/ROADMAP.md §2.8) |
| Effort | S |
| Confidence | REPRODUCED |
| Location | `scripts/make_showdown_policy.py:142-146`, `src/nfl_dfs/portfolio_policy.py:115-126`, `src/nfl_dfs/portfolio_enforcement.py:308-338`, `src/nfl_dfs/relaxation.py:495-526` at ab50652fae16cfb52b377c94a9865cfabbb640d8 |
| Overlap | Session 23 Complete; its one-QB default survives. Session 23c is Pending and covers multiple explicit game theses, not correction of the ordinary generator's default candidate eligibility. The later PHI–CHI result is new temporal evidence beyond the September review. |
| Requires | none |
| Depends on | none |
| Decision | **Accepted** (2026-10-02 triage). Session 57: the Showdown generator's `--qb-count-max` default becomes 2, minimum 1; explicit one-QB policies unchanged. Verified here: default 1 at `make_showdown_policy.py:143`; the QB band drops only at rung 3 (`relaxation.py:524`). |

**Issue.** The Showdown generator fixes QB count at exactly one until a late relaxation rung. That makes two-QB construction an infeasibility fallback instead of a legitimate candidate family on a normal successful run. A game-dependent empirical preference has become a universal exclusion, preventing the scorer from comparing both starting quarterbacks when both have productive outcomes.

**Evidence.** The current defaults are `--qb-count-min=1` and `--qb-count-max=1`. In the later PHI–CHI reference contest, two-QB lineups are **58,539/236,836 submitted entries (24.7%)**, but **1,875/2,552 top-1% entries (73.5%)**: 2.97x observed lift versus 0.38x for one QB. Earlier two-QB lifts range from 0.03x in SF–LAR to 1.45x in DAL–NYG, so replacing one universal shape with another is unjustified. The fixed PHI–CHI winner reproduction runs the real structural auditor and MILP with all other structural bounds open: `(minimum=1, maximum=1)` yields only `qb_count` and `INFEASIBLE`; `(1,2)` yields no violation and `OPTIMAL`, with ordinary DraftKings validation passing in both audit inputs. Command: `.venv/Scripts/python.exe outputs/review-audit/standings-20261002/engine_repro.py`.

**Why it matters.** A feasible one-QB bank can omit the dominant observed tail family without raising an error or relaxing. PHI–CHI is one new game, not proof of a future two-QB advantage; it is sufficient to disprove the premise that one QB is a harmless universal search restriction. More Captain variety within the same excluded family does not repair that loss.

**Recommendation.** Change only the new-policy generator's maximum QB default to **2**, retaining minimum 1, current depth/participation exclusions and independently enforced per-QB pass-catcher bounds. Preserve explicitly supplied one-QB policies and frozen policy bytes. Let the existing scorer compare the enlarged bank; reserve forced family allocations and shared-outcome evaluation for S23c/S25. Do not force both QBs into every lineup, add a guessed point bonus, or treat a backup as a starter without R36 evidence.

**Acceptance.** Extend the generator test to assert `qb_count={minimum:1, maximum:2}` for an ordinary new policy and `{1,1}` when explicitly requested. Add one fixed legal two-starting-QB roster with the necessary pass catchers: it passes new default QB bounds, fails an explicit one-QB policy for `qb_count`, and retains distinctness and evidence checks. Repeat the PHI–CHI isolated constraint reproduction. Exercise small deterministic bank fixtures favoring one QB and two QBs respectively; neither should require a relaxation solely to admit that QB count. Target under five seconds for the focused tests. No assertion should require a historical winner to be selected by pre-lock projections.

**Risk.** More candidates can increase runtime or worsen a points-only selector's concentration on quarterbacks. Existing caps and deadlines must continue to hold; monitor that tradeoff under F-02 and the queued tail-scoring work. This change opens a choice rather than estimating the correct portfolio fraction. F-06 is separately needed for the PHI–CHI winning roster's defense combination, but is not a dependency of this isolated QB-count fix.

### F-03: Honor depth declarations for zero-history starters

| Field | Value |
|---|---|
| Category | BUG |
| Severity | MEDIUM |
| Class | P |
| Tier | 3 (docs/ROADMAP.md §2.8) |
| Effort | S |
| Confidence | REPRODUCED |
| Location | `src/nfl_dfs/offensive_roles.py:385-413`, `:454-460`; call order `src/nfl_dfs/selection.py:316-343` at ab50652fae16cfb52b377c94a9865cfabbb640d8 |
| Overlap | Session 54 is marked Complete and closes the R36 “no usable history” question. Its implementation handles only MISSING_HISTORY; observed-zero history still defeats the current depth declaration. This is an incomplete completed fix, not a duplicate request to build deferred S52. |
| Requires | none; narrow application of R36's existing depth-declared-starter ruling |
| Depends on | none |
| Decision | **Accepted** (2026-10-02 triage). Session 58 (tier 3): the Session 54 branch extends to `OBSERVED_HISTORY_ZERO` under the same guards, carry and target shares zero, the actual history state kept in the finding. Verified here: `offensive_roles.py:385` guards `historical_state == "MISSING_HISTORY"` only, and the observed-zero branch below it excludes. |

**Issue.** The depth resolver can validly assign a declared starter attempt share 1.0, but the subsequent offensive-role gate erases that share when his history is tagged `OBSERVED_HISTORY_ZERO`. The new exception applies only to `MISSING_HISTORY`. Two otherwise identical declared starters therefore get opposite eligibility decisions based on whether the historical feed contains an all-zero record or no record.

**Evidence.** With the existing synthetic S54 fixture, changing only the history state gives: `MISSING_HISTORY → DIAGNOSTIC, attempt share 1.0 → 1.0`; `OBSERVED_HISTORY_ZERO → EXCLUDE, attempt share 1.0 → 0`. The current-role-unknown control still blocks. Reproduce the two primary cases:

```python
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from tests import test_declared_starter_selectable as t
with TemporaryDirectory() as tmp:
    w = t._world(Path(tmp)); person = w[-1]
    for state in ('MISSING_HISTORY', 'OBSERVED_HISTORY_ZERO'):
        m = replace(w[1], offensive_history_by_person={person:{'state':state,'incompatible_transfer':False}})
        r = t._resolve((w[0], m, *w[2:]), {person})
        f = next(x for x in r.report['findings'] if x['person'] == person)
        print(state, f['selection_action'], f['before']['qb_attempt_share'], f['after']['qb_attempt_share'])
```

This state is a recognized producer/gate state, not malformed input. S51's current-season gap-fill cannot resolve the case when there are no usable rows before the slate. R36 says “no usable history,” and permits the hash-bound depth declaration as an unconfirmed diagnostic (`docs/ROADMAP.md:2354-2359`).

**Why it matters.** A historically unused backup who is now the declared starter can disappear from every candidate, including Captain, despite fresh depth evidence. This recreates the coverage problem R35/R36 were intended to address and forces a manual workaround such as the route implicated in F-01. The reproduction establishes the exclusion mechanism; it does not assert that either reviewed real slate contains this exact history state.

**Recommendation.** Extend the declared-QB exception narrowly to `OBSERVED_HISTORY_ZERO` when the effective hash-bound depth resolution supplies positive attempt share, participation permits selection, and there is no conflicting role fact or unresolved material role change. Keep carry/target shares at zero, preserve the actual history state in the finding, and retain `EVIDENCE_STATE=UNKNOWN`. Do not extend this to arbitrary transfer/role-unknown or BLOCK cases.

**Acceptance.** Parameterize the existing S54 acceptance case over missing and observed-zero history; both must remain scored/selectable after a valid current starter declaration, including their Captain and FLEX identities. A backup, DK-OUT/officially inactive/operator-excluded player, conflicting role fact and unresolved material role change must retain their existing exclusion/block behavior. Assert the finding's depth hash, zero carry/target shares and unconfirmed evidence status. Resolver cases should run in under two seconds without network; retain one bounded selection test to prove the person reaches the selectable pool.

**Risk.** An observed zero may describe a truly unused player. Only a current, accepted effective starter declaration justifies this exception; broadening based merely on a zero projection would erase useful gate distinctions. Preserve transformation/provenance labels and do not mutate frozen historical artifacts.

### F-08: Unblock local grading before expanding construction policies

| Field | Value |
|---|---|
| Category | STRATEGY |
| Severity | MEDIUM |
| Class | P |
| Tier | 7 (docs/ROADMAP.md §2.8; proposed sequencing change below) |
| Effort | S |
| Confidence | INFERRED |
| Location | `docs/ROADMAP.md:1005-1017`, `docs/ROADMAP.md:1699-1743`, `docs/ROADMAP.md:2441-2465` at ab50652fae16cfb52b377c94a9865cfabbb640d8 |
| Overlap | Sessions 18/18b/26 are already Pending. This finding disputes their dependency and ranking rationale under R34; it does not re-queue their implementation. S18 waits for S17b/O2, and all of S18b waits for S24b even though its descriptive field grading does not consume a scenario bank. |
| Requires | BEN ruling (ROADMAP §2.8 measurement sequencing) |
| Depends on | none |
| Decision | **Accepted in part; sequencing flagged to Ben** (2026-10-02 triage). Session 18's dependency on Session 17b and O2 is removed (local mode on the inbox corpus; 17b stays the cloud-transport acceptance; the O2 downloads scope only their two slates' provenance and replay results) and its acceptance names this corpus with the 26-file set as the regression subset; Session 18b drops Session 24b (the bank grading returns when 24b lands). Whether the local grading slice runs before Sessions 56 and 57 is Ben's §2.8 ruling: `[BEN: ...]` flag in §2.8 with the recommendation to run it first. |

**Issue.** The roadmap permits construction defaults justified by standings to ship before their actual predicates are graded, while tying local descriptive grading to cloud corpus publication and the future scenario bank. The available local data already supports the relevant field joins and disproves a universal benefit for the implemented Showdown filter. Delaying this feedback lets more construction work depend on an unverified claim; judging that a ranking error under R34 is the reviewer's recommendation, not a measured dollar benefit.

**Evidence.** Session 18's dependency is `Session 17b and O2`; Session 18b's is `Session 18, Session 23, Session 24b`. Section 2.8 ranks construction ahead of measurement because the hygiene bundle supposedly improved both goals in every graded game. This review processed **56 local contests**, joined **3,190,495 submitted lineups** with no unresolved names/roles and measured the implemented filter's top-1% lift at about **0.15x in DEN–KC and 0.33x in PHI–CHI**, while preserving unknown paid outcomes as unknown. All of those checks ran without publishing an asset, fetching DraftKings or building scenarios. Full original-download provenance and model replay remain separate unmet work where applicable.

**Why it matters.** The delay prevents inexpensive falsification of strategy assumptions already shaping real candidate banks. PHI–CHI's selected player union was mathematically incapable of reaching its reference top-1% score even in hindsight; a repeatable local grader can distinguish coverage loss from uniqueness or assignment changes. More construction features without that distinction can consume sessions without improving either R34 objective.

**Recommendation.** Revise the existing cards, not the production engine, in this finding: make S18's local manifest/hash-bound grading mode startable without S17b, preserving S17b as cloud-transport acceptance; scope missing original downloads to the affected provenance/replay results instead of blocking all available descriptive rows. Split S18b's field-feature and exposure grading from its scenario-bank calibration acceptance so the former does not depend on S24b, and allow S26 to depend on that completed descriptive/ownership-label slice. Ask Ben to authorize running this bounded measurement slice before further ungraded construction expansion despite its present tier-7 position. Keep private-export handling and permanent boundaries intact.

**Acceptance.** The roadmap dependency graph must permit a local grading session given the existing inbox and same-slate sources, without a cloud publication or scenario-bank prerequisite, while separately retaining each original-download and cloud acceptance item. Replace the stale 26-contest-only descriptive acceptance with a versioned manifest reference for this corpus: 56 nonempty contests, five named empty placeholders, 139 owned entries, seven owned blanks, exact 26-contest paid coverage, and no cash classification for the remaining 30. Retain the older 26-contest fixture as a regression subset. The already-planned grader implementation must reproduce F-06/F-07's counts; this finding's changed lines are the dependency, scope and acceptance edits, not a second grader build.

**Risk.** Removing a prerequisite carelessly could make local success look like authenticated cloud-transport acceptance or treat embedded salary tables as original-input provenance. Keep those statuses separate and name missing evidence per metric. The later construction and ownership changes still need untouched forward slates; this retrospective corpus must not become a repeatedly tuned "holdout." Ben may prefer the current cloud-first sequencing, in which case record that decision explicitly and retain the measured limitations.

### F-04: Add a compact console handoff for slate runs

| Field | Value |
|---|---|
| Category | TOKEN |
| Severity | LOW |
| Class | P |
| Tier | 9 (docs/ROADMAP.md §2.8) |
| Effort | M |
| Confidence | REPRODUCED |
| Location | `src/nfl_dfs/cli.py:4203-4232`, `:3632-3633`, `:4366-4367`; `docs/RUNBOOK.md:19`, `:286` at ab50652fae16cfb52b377c94a9865cfabbb640d8 |
| Overlap | New. S44b consolidates truth/report implementation and S46 addresses workbook duplication; neither supplies a bounded console handoff or changes the normal operator command's output volume. |
| Requires | none |
| Depends on | none |
| Decision | **Accepted** (2026-10-02 triage). Session 59 (tier 9): opt-in `--console-summary`, full JSON stays the default, runbook and operator-guide examples use the flag. |

**Issue.** The normal slate command writes `cowork_run.json` and then prints the entire report. The two short, failed-improvement replays alone emitted 40,950 and 36,521 bytes, repeating entry groups, IDs, intake details and nested truths. Claude needs the delivered file, result, limitations and next action to proceed; the repeated detail is already a named artifact.

**Evidence.** Raw captured console sizes were Classic **40,950 bytes**, Showdown **36,521 bytes**. A measured JSON projection retaining run ID, mode, stage, status, release truths, delivered-file validity, path/hash/row count, all delivery limitation codes, the priors error, report path and current `next` text was **1,516 / 1,513 bytes**, respectively. This saves **39,434 / 35,008 bytes**, approximately 96% of these two outputs. The measurement is a serialization comparison over the actual runs, not an estimated tokenizer conversion.

**Why it matters.** Each ordinary run or retry can inject more context than the entire always-loaded instruction set, before the agent has opened any diagnostic. This consumes attention under the lock clock and encourages accidental whole-artifact reads. No runtime or winnings benefit is claimed.

**Recommendation.** Add an explicit `run-slate --console-summary` option and use it in the normal runbook/operator examples. Keep current full JSON output as the default for compatibility, and always retain the complete report artifact. The compact object must distinguish top-level review validity from `delivered_file_valid`, name the actual latest deliverable and its hash, include every limitation/blocker code and a diagnostic/report pointer, and keep the exit code unchanged. Apply the same formatter to success, blocked-improvement and error exits.

**Acceptance.** For synthetic successful, baseline-only and partial-fill runs, compare full and compact modes: identical persisted report/delivered bytes and exit status, and identical truth values, delivered counts and code sets in the summary. Confirm the latest-file pointer is not replaced by an absent improvement path. On these two replay reports, compact output should stay below 4 KiB while the full report remains available. This requires serialization/CLI tests, not another slow solver bank.

**Risk.** Consumers may parse stdout, hence the opt-in flag and unchanged default. An over-aggressive summary could hide limitations or conflate the unsuccessful review with a valid baseline. Preserve codes and explicit report pointers; do not silently truncate unique problems just to hit a byte target.

### F-05: Load the Showdown judgment procedure only when needed

| Field | Value |
|---|---|
| Category | TOKEN |
| Severity | LOW |
| Class | P |
| Tier | 9 (docs/ROADMAP.md §2.8) |
| Effort | S |
| Confidence | REPRODUCED |
| Location | `docs/claude/working.md:54-83` and the import at `CLAUDE.md:143` at ab50652fae16cfb52b377c94a9865cfabbb640d8 |
| Overlap | New. This always-loaded October judgment/history block postdates the prior review; S43's hook repairs and S45's contract documentation do not remove it. |
| Requires | none |
| Depends on | none |
| Decision | **Modified, done in this triage.** The block stays in the always-loaded file: Ben's double correction is why it exists, and a path-scoped rule does not fire for an operator who has not opened that path. Its history left it (`changelog.md` 2026-09-28 and 2026-10-01 and R35/R36 already hold it) and the live rules stayed; the block went from 3,275 bytes to about 2,300. Sessions 55 and 56 shrink it further when they land. |

**Issue.** Every session imports the full Showdown judgment narrative and procedure, including two past corrections, session history, the deferred-card explanation and a specific old swap script. Most development sessions do not operate a Showdown slate. The live rules need a clear trigger and one authoritative procedure, while the history already has roadmap/changelog homes.

**Evidence.** `len(b''.join(Path('docs/claude/working.md').read_bytes().splitlines(keepends=True)[53:83]))` is **3,275 bytes**, about 41% of this imported file. The earlier normalized-text measurement was 3,252 bytes; the difference is checkout line endings. Moving this block behind a mandatory Showdown-specific pointer of at most 200 bytes saves **at least 3,075 always-loaded source bytes**, about 10.7% of the four-file 28,868-byte subtotal.

**Why it matters.** The same operating incident history is paid for on every startup, clear and development conversation even when changing unrelated engine code. The benefit is modest per session but recurring; it belongs after the tier-1/2/3 findings, not ahead of construction work.

**Recommendation.** Put the current left-out-starter and concentration procedure in the runbook's Showdown operating section. Replace the imported block with a short mandatory instruction to read that exact section before any Showdown build or handoff; retain the deadline exception and evidence/number boundaries in the operating procedure. Link to existing R35/R36 and changelog history rather than copying that narrative again. This needs no change to CLAUDE.md or a permanent boundary.

**Acceptance.** Recount raw bytes: the replacement imported block is at most 200 bytes. Manually trace the documented two-file Showdown workflow and verify it still necessarily reaches the left-out-starter check, 60%/20% concentration action, deadline exception and evidence restrictions before handoff. Update any stale section pointers; no expensive test suite or literal-string test is needed for this documentation move.

**Risk.** Moving the instruction can make the judgment pass easier to miss. An explicit always-loaded trigger is essential; relying solely on a path-scoped rule is insufficient when the operator has not opened that path. F-02 reduces manual concentration work, but does not remove the need for a judgment pass.

## 4. Verified sound

- All 56 nonempty standings exports are final; every rank reproduces, and every submitted lineup joins the correct same-slate salary/role source. Score, slot, salary, distinct-person and team/game checks pass.
- All 71 older owned entries reconcile by Entry ID, rank and score to history; newer paid outcomes remain unknown. Seven DET–BUF blanks remain visible rather than disappearing from coverage.
- The 47-entry SF–LAR CSV's combined-person side ownership is identified and handled by reconstructing role ownership from lineups; it is not silently treated as FLEX-only ownership.
- Actual PHI–CHI submissions match v4 in all 36 entries. Hindsight diagnostics are explicitly separated from pre-lock model performance and from evidence clearance.
- The isolated optimizer and structural auditor agree on both new constraint reproductions; F-06/F-07 concern the defaults' strategy, not an audit/MILP mismatch.

- Both required two-file replays delivered every authorized row before the failing optional improvement: 25 Classic and 36 Showdown, each legal, distinct and byte-exact to its source template outside roster cells.
- The games-capture clock guard refused present-day evidence in a historical pre-lock replay; it was not bypassed, and the prior baseline remained available.
- The replay clock limitation and `DO_NOT_UPLOAD` remained explicit; baseline delivery was not presented as evidence clearance, calibrated quality or a win probability.
- All four tracked PHI–CHI shipped review files passed independent validator invocations for legality, captain-sensitive distinctness and exact-template preservation.
- Showdown canonical identity includes Captain identity and sorts FLEX people; ordinary FLEX permutations do not evade the common validator's duplicate key (`lineups.py:43-64`).
- The common roster validator rejects one underlying person in multiple slots, including CPT/FLEX duplication (`lineups.py:107-109`); F-01 bypasses this validator rather than exposing a defect in it.
- The byte auditor preserves non-roster field bytes and line endings and rejects unauthorized filled-template writes; a whole-file CSV rewrite is not required for ordinary blank-entry export.
- S54's true missing-history starter case works: hash-bound depth share is retained as an unconfirmed diagnostic, with carry/target zero; the corresponding role-unknown control still blocks.
- Explicit Showdown exposure controls can satisfy the 60%/20% counterexample with 20 legal distinct rows, so F-02 is an automatic-path/default gap, not a demonstrated inability of the policy solver.
- Classic no-policy review now requests thesis construction, correcting the old single-construction fallback shape; the concentrated legacy C1 fixture is not proof that this new path is absent.
- Existing expensive tests exercise different entry counts, subset policies, preservation, forbidden rosters and mutation boundaries; their runtime alone is not a reason to delete them.
- The three superficially repetitive Classic shape tests cost only 1.27 s together on an isolated rerun; a separate consolidation task is not justified by that measurement.
- `config/runtime.json`'s scenario sizes do not establish scenario use by prior-review selection. Their unwired/legacy aspects are already represented in the existing queue.
- The SessionStart digest is bounded and relatively small in this checkout (35 lines, 2,056 bytes); its known truncation-pointer defect remains S43 rather than a new finding.
- The large ledgers have explicit section-reading guidance. Their full file sizes were not mistaken for unavoidable session context.

## 5. Questions for Ben

- **F-02:** For the slates you actually enter next, what are the usual entry counts and how many entries share each contest? Global 60%/20% defaults are already authorized; these facts determine useful small-portfolio rounding and contest-local acceptance fixtures.
- **F-02:** How much prior-point sacrifice is acceptable to reduce shared failure points, and should satellites/qualifiers have the same concentration preference as large-field cash GPPs? This affects later relaxation and assignment policy, not whether the current feasible counterexample should obey existing defaults.
- **F-02 and the existing tail/measurement queue:** What does your intended contest mix look like by entry fees, payout shape and bankroll allocation, and are exact paid-place/payout records retained for each? Without those facts, one cannot evaluate portfolio washout across that mix or decide whether a proposed tail preference helped your actual objective.
- **F-04/F-05:** Do you ordinarily read the console JSON, the HTML review, or the workbook at handoff? That determines which human-facing details the compact handoff should emphasize. It does not justify deleting machine reports or skipping any validity/evidence check.

- **F-02/F-07 and S23c/S28:** What is the acceptable tradeoff between blanking a slate and pursuing an extreme finish, measured at your actual entry budget? This determines game-thesis sleeve sizes; the five Showdown outcomes cannot supply your risk preference.
- **F-08 and the standings study:** Where is the contest-history export covering September 17, 27 and 28, including paid places and cash/ticket winnings? Those 30 contests currently cannot support cashing or washout conclusions.
- **F-08 and S14/O9:** Were the seven blank DET–BUF satellite entries intentionally abandoned, missed during handoff/upload, or later refunded? The export proves the blanks, not their cause or financial settlement.
- **F-08:** Can the bounded local grading slice run ahead of further ungraded construction work while cloud publication and original-download provenance remain separate acceptance items? This is the requested §2.8 sequencing ruling.

F-01, F-03, F-06 and F-07 need no additional personal facts to reproduce. F-08 requires the named BEN sequencing ruling; no permanent boundary change is requested. `Decision` cells are intentionally blank for Claude Code's accept/reject/modify triage.
