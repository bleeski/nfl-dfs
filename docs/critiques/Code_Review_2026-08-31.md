# Code Review, 2026-08-31

Full review of the nfl-dfs engine at commit `e042c7b` (single commit, "Initial NFL DFS engine with Cowork workflow"), all 29 modules in `src/nfl_dfs/` (7,021 lines), all 22 test files, both launchers, config, templates, and fixtures, read in full against `plan.md`, `docs/DATA_CONTRACTS.md`, `docs/COWORK_RUNBOOK.md`, and `IMPLEMENTATION_STATUS.md`. Reviewer: Claude, acting as solution architect. Numeric findings were verified empirically where the sandbox allowed; the pinned test suite could not run here (see F-M12) and should be re-confirmed with `./nfl.ps1 test` on Windows.

## Verdict

The safety architecture is real and mostly well built. Byte preservation, fail-closed gating, schema-driven discovery, strict ID identity, and honest labeling are implemented with care, and the code quality is high: typed contracts, frozen dataclasses, deterministic seeds, atomic writes. Two acceptance runs from tonight (Windows, Python 3.13.7) confirm the two-file first pass behaves exactly as documented.

The review still found six issues I rate HIGH. Three are contract violations the docs claim are already handled (exact tie/duplication economics, REFEREE blocking, the registered QA pass), one is a data-integrity trap that will fire on the next clone (git normalized the "immutable" fixtures), and two are missing fail-closed checks on inputs the engine already trusts (multi-contest entry files, evidence freshness). None of them can cause a bad upload today because certification blocks on missing official status anyway and uploads are manual, but each one either falsifies a documented guarantee or will bite when the missing evidence is finally supplied and the gates open.

## What is solid

Worth stating plainly so the findings below read in proportion.

- `lineups.write_upload_bytes` + `referee.audit_output_bytes` + `certification.certify_upload` form a genuinely strong three-layer output path: fill only blank cells of authorized Entry IDs, refuse prefilled rows entirely, independent parse-level audit of every line, reparse and SHA-256 of final bytes, atomic write with fsync, deletion of any upload-shaped CSV when a blocker exists. Verified the fixture geometry assumptions against the real DKEntries file (fee at index 3, roster at 4..12, Instructions marker at 13/14).
- `cowork.py` schema classification is order-correct (entry prefix beats salary subset), rejects ambiguity instead of guessing, resolves and snapshots everything content-addressed, and `required_next_inputs` names each missing hard fact with an instruction not to infer it.
- `dk.py` parsing is strict where it matters: exact CPT=1.5x salary reconciliation, distinct role IDs, template/slate mode reconciliation, duplicate ID rejection, timezone-aware lock times.
- `sources.py` is HTTPS-only, allowlist-first, refuses odds API without an explicit key, and (verified against httpx 0.28.1 semantics) a redirect response raises rather than being captured as evidence.
- Determinism holds end to end: single seeded `default_rng` per bank, stable sorts everywhere ties matter, deterministic no-good perturbation in the optimizer, largest-remainder apportionment with stable tie-break in `scale_field_multiplicities`.
- The MILP is correctly formulated for both modes (position bounds with FLEX arithmetic, min-two-games and min-two-teams via indicator variables, per-person uniqueness across CPT/FLEX rows) and `_slot_roster`'s FLEX recovery is provably total given the bounds.
- Honest labeling is pervasive: `DIAGNOSTIC_ASSIGNMENTS_READY_DO_NOT_UPLOAD`, `COLD_START_FIELD_MODEL`, the "not an EV claim" strings, and `IMPLEMENTATION_STATUS.md` is candid about what is gated.

## HIGH findings

### F-H1. The registered QA layer is never executed

`qa.audit_selected_portfolio`, `qa.decide_repair`, and `qa.run_three_pass_audit` implement the plan §4 trigger list (exposure envelopes, negative dependence, duplication-chops-below-fee, salary-left range, sensitivity, solver gap, final-byte match). Nothing calls them. Verified:

```
$ grep -rn "audit_selected_portfolio|run_three_pass_audit|decide_repair" src tests
# only tests/test_governance_qa_settlement.py (decide_repair, run_three_pass_audit)
# audit_selected_portfolio: zero callers anywhere, including tests
```

`cli._certify` builds its QA sheet by relabeling manifest blockers (cli.py:404-414); `command_build` runs only `coverage_report` and the referee sign check. Consequently no exposure, dependence, duplication, salary-left, sensitivity, or solver-gap trigger can ever block or even surface in a run, and the inputs those triggers need (duplicate_p95, divided_payout_p95, exposure envelopes) are never computed anywhere. `IMPLEMENTATION_STATUS.md` lists REFEREE QA in the chained flow; the flow actually contains no quantitative QA pass. Wire `audit_selected_portfolio` into `command_build` after selection, feed its blocking findings into certification as blockers, and compute the duplication/divided-payout inputs from `CandidateEconomics` (they are one quantile away from data already in memory).

### F-H2. REFEREE cannot block anything

Plan §4: REFEREE "never causes reselection" but "a sign disagreement ... blocks promotion". `IMPLEMENTATION_STATUS.md`: "can block on a sign or safety disagreement". In `command_build` (cli.py:648-654, 691-697) `referee_blocks(...)` is computed with `uncertainty=0.0`, `safety_failure=False`, `hard_constraint_failure=False`, stored in the JSON report, and then ignored: the function returns 0, `command_cowork_run` proceeds straight to `_certify`, and `certify_upload` receives no referee evidence. A REFEREE sign disagreement today changes one boolean in a report nobody gates on. Minimal fix: when `referee_blocked` is true, append a `REFEREE_SIGN_DISAGREEMENT` hard-gate evidence record (state FAIL) to the certification evidence, and pass a real uncertainty (the paired standard error is already computable from the two economics banks) instead of 0.0, which currently makes any sign flip block-worthy in the report even when both LCBs are statistical noise.

### F-H3. Candidate and field scores are computed through different float paths, so exact ties and self-duplication division do not work

`economics.evaluate_candidates_against_field` ranks a candidate against the field by comparing scores rounded to 6 decimals. But candidate scores come from `lineup_score_matrix`, which accumulates in float32 (simulation.py:303-309, `matrix[:, column] +=` on a float32 matrix), while field scores are computed in float64 from the same float32 person outcomes (economics.py:79-84). At NFL score magnitudes (~100-160 points) float32 accumulation error is ~1e-5 to 1e-4, far above the 1e-6 rounding grain. Empirical repro (pure-Python float32 emulation, 9 slots, values U(0,35), 20,000 trials):

```
mismatch rate: 18985/20000 = 94.9%
example cand vs field: (94.589386, 94.589388, -2.0e-06)
example cand vs field: (130.032974, 130.032984, -1.0e-05)
```

So a candidate lineup that also exists in the field (exactly the duplication case the engine is supposed to price) fails to tie with its own copies ~95% of the time; it lands randomly above or below them and receives an undivided payout for whichever rank it gets. `duplicate_counts` (canonical-key based) is correct, but nothing feeds it into the payout math, and the QA trigger that would consume it is unwired (F-H1). `plan.md` ("exact duplication/ties") and `IMPLEMENTATION_STATUS.md` ("exact duplication/ties") both claim this works. Fix: score candidates through the identical field path (float64 gather-and-sum of float32 outcomes, then the same round), or better, handle self-duplication structurally: for each candidate with `duplicate_counts > 0`, add the duplicate multiplicity into `tie_counts` and remove those copies from the strictly-above count by key rather than by score.

### F-H4. Multi-contest entry files are silently averaged into one contest

Nothing anywhere checks that the reserved entries share one contest. `parse_entries` accepts any mix; `command_build` uses `entries.authorizations[0].entry_fee` (cli.py:609, 644) for every entry, one `field_size`, one payout table, and one portfolio selection zipped across all Entry IDs sorted as strings (cli.py:614-621). Real DKEntries exports routinely contain reservations in several contests with different fees, sizes, and payout curves. Today's fixture happens to be single-contest (the early-exit report even prints the distinct `contest_ids`), but the build and certify paths never assert it. This violates the engine's own fail-closed rule ("Missing ... ambiguous ... is DO_NOT_UPLOAD"). Add a hard stop in `command_build` and `certify_upload` when `len({e.contest_id}) > 1` or `len({e.entry_fee}) > 1`, until per-contest portfolios exist. Note `ContestContract` (contracts.py:160-170) was designed to carry exactly this structure and is never constructed anywhere.

### F-H5. Git normalized the "immutable" fixtures; a fresh clone fails the hash manifest

The five supplied artifacts are CRLF on disk and match `tests/fixtures/supplied/manifest.json` (verified: `sha256sum "DKEntries CSV.csv"` = `bae82934...` = manifest, 83,852 bytes). The committed blobs are LF-normalized (`git show HEAD:...` = 83,125 bytes = exactly one CR per line stripped; `git diff --stat` shows all 2,071 lines of the five fixtures "changed"). There is no `.gitattributes`. Anyone cloning this repo gets fixtures whose bytes and hashes are wrong, `test_fixture_hashes_match_manifest` fails, and the byte-preservation guarantees are tested against corrupted ground truth. The working tree is only correct because the original files never left it. Fix now, while the working tree is still authoritative: add `.gitattributes` with `* -text` (this repo has no use for EOL conversion anywhere; CSVs, xlsx, and outputs all need exact bytes), then re-commit the fixtures so the blobs match the manifest.

### F-H6. Official activity evidence has no freshness gate

`parse_official_inactives` validates OBSERVED_AT for timezone-awareness and discards it (evidence.py:72-77). `_official_status_evidence` sets the EvidenceRecord's `observed_at` to `datetime.now()` at certification time, not the observation time, and never sets `expires_at` (cli.py:200, 226-235), so `EvidenceRecord.state_at`'s staleness logic can never fire. A paste with OBSERVED_AT from three weeks ago certifies as current. CLAUDE.md requires "timezone-aware observation time" and the plan makes official inactives the "current-lock hard gate"; currency is checked nowhere. Fix: carry the maximum row OBSERVED_AT into the record's `observed_at`, set `expires_at` relative to it (the T-110/T-60 cadence in plan §4 implies a few hours), and separately require OBSERVED_AT to fall within a registered window of the earliest unlocked game's `lock_at`. The slate's lock times are already parsed and available.

## MEDIUM findings

### F-M1. Late swap allows swapping in players whose games already started

`audit_late_swap` (late_swap.py:36-44) locks slots whose original player's game has locked, and re-validates legality, but never checks that replacement players in unlocked slots have `lock_at > now`. DK rejects adding a locked player; this audit passes it. One added loop over changed slots fixes it.

### F-M2. Weather and market hard gates pass on column presence

In model-assisted runs `_base_evidence` marks `weather_if_required` and `market_line` PASS with reasons "model input contains explicit weather state" / "timestamped manual market lines" (cli.py:163-190), where the source artifact is just the hash of the operator CSVs. `load_opportunity_model` validates only that WEATHER_STATE is a non-empty string and MARKET_OBSERVED_AT is tz-aware; MARKET_OBSERVED_AT freshness is unchecked (same class of gap as F-H6), values like TOTAL/SPREAD are unbounded, and the plan's NWS-plus-roof-metadata requirement for outdoor games has no code path at all. These two gates are currently assertions dressed as evidence. Either validate (enumerate WEATHER_STATE values, bound totals/spreads, check market observation age) or relabel the reasons to say presence-only.

### F-M3. Config files are hashed into manifests but never read

`grep -rn "runtime.json|scoring.json|evidence_policy" src/` returns nothing. `certify_upload` hashes `config/*.json` into `config_hashes` while every value they contain is duplicated as a code literal: scenario counts (cli.py:488-490), salary cap (contracts.py:136), captain multipliers (dk.py:247, scoring.py:113, simulation.py:307), required hard fields (certification.py:58-65), memory limit (system.py:130). Editing config changes the manifest hash and nothing else, which is the worst combination: it looks configurable and audited but is neither. Either load them as the single source of truth or move them to `docs/` as descriptive records.

### F-M4. Simulation diagnostics are hardcoded constants

`simulate_factor_bank` returns `"passing_receiving_accounting": 1.0, "share_conservation": 1.0` unconditionally (simulation.py:283-284), and `test_simulation.py` asserts the constant. The invariants happen to hold structurally today (receiving TDs are allocated from the same `passing_tds` draw; receiver yards distribute the same team passing yards), but the diagnostic will keep reporting 1.0 through any future regression. Compute them (one einsum each) or delete them.

### F-M5. Portfolio selection blows up at its own default sizes

For `entry_count <= 3`, `select_portfolio` evaluates every combination from the shortlist (portfolio.py:157-159): C(250,2) = 31,125 full five-state evaluations, then `_nondominated` does O(n²) Python-level dominance checks, ~9.7e8 comparisons, before Nash selection. For 3 entries it is C(250,3) ≈ 2.6M evaluations plus ~6.7e12 comparisons: effectively a hang. The reduced test uses shortlist 8, so this is untested at defaults; the Cowork diagnostic profile (shortlist 250) with a 2-entry template is already minutes-to-tens-of-minutes in `_nondominated` alone, and a 3-entry reservation never finishes. plan §3 itself demands exhaustive singles/pairs/triples, so the fix is implementation, not policy: batch-evaluate all pairs in one vectorized pass (gross payouts are a (scenarios × candidates) matrix; pair sums are one broadcast), and prune the frontier incrementally (sort by one axis, single sweep for the other) instead of all-pairs dominance.

### F-M6. Economics evaluation is a per-scenario Python loop

`evaluate_candidates_against_field` loops `for scenario in range(scenarios)` with an inner `for candidate_index in range(len(rosters))` doing two `searchsorted` calls each (economics.py:74-95), then a second scenarios × candidates Python loop for `divided_payout` (economics.py:99-106). At the registered profile (20k scenarios × 250 shortlist × 5 states) that is ~25M Python iterations of the first loop and 25M `divided_payout` calls, each re-scanning the tier list. The 10-minute Classic gate is very unlikely to survive this plus F-M5; `IMPLEMENTATION_STATUS.md` already declines to claim the registered gates, and this is the concrete reason it should stay unclaimed. `np.searchsorted` accepts vectorized needles, ranks/ties for all candidates per scenario are two array calls, and `divided_payout` over integer ranks/tie-counts can be a cumulative-payout lookup table built once per contest.

### F-M7. Our own entries do not compete with each other

Ranks and ties are computed against field lineups only; when the portfolio holds several entries, each is priced as if the others do not exist (economics.py evaluates candidates independently; `_state_metrics` just sums their payouts). In a 100-entry small-field contest with 2 reserved entries this misprices materially; at 150 entries in a 235k-field GPP it is noise. Worth a one-line caveat in the build report now and a real fix (add selected portfolio mates into the tie/rank computation) when small-field play starts.

### F-M8. Ownership brackets are unvalidated and silently rescaled

`_read_brackets` (cli.py:459-472) accepts any floats: no `low <= base <= high`, no [0,1] bound (DATA_CONTRACTS specifies decimal percentages), and the workbook formats bracket cells as percentages, inviting "25" (=2500%) vs "0.25" entry errors that nothing catches. Then `cold_start_states` renormalizes each position group to its roster target after applying brackets (ownership.py:88-94), so a supplied BASE of 0.25 generally does not survive as 25%: it is rescaled by whatever the rest of the group sums to. The renormalization is a legitimate legality constraint, but the operator is never told their pinned value moved. Validate on read; report post-normalization deltas above some threshold in the build report.

### F-M9. The inactive-redistribution feature is dead and incompatible with the simulator

`remove_inactive_and_redistribute` has zero callers (grep: only its definition). If it were wired, its output cannot be simulated: it removes people from the model, and `simulate_factor_bank` raises "opportunity model does not cover the salary pool" whenever model people != salary people (simulation.py:73-76). The plan's game-day flow (inactives arrive, roles redistribute, rebuild) therefore has no executable path: today an inactive player can only be handled by editing the player opportunity CSV by hand to zero shares while keeping the row. Decide the semantics (keep the person with zeroed shares rather than removing the row) and either wire it or delete it.

### F-M10. The two launchers install different environments

`nfl.sh setup`: `uv sync --all-groups --locked --python 3.13.7`. `nfl.ps1 setup`: `uv sync --all-groups` (nfl.ps1:19), no `--locked`, no interpreter pin beyond `.python-version`. An edited pyproject on Windows silently re-locks instead of failing closed, violating the acceptance item "neither may silently use an incompatible environment". Add `--locked --python 3.13.7` to nfl.ps1.

### F-M11. Doctor measures long-path support and then ignores it

`doctor.pass_status` is only `sqlite_integrity == "ok" and not Excel-locked` (system.py:114). Tonight's acceptance run shows `"long_paths_enabled": false` on your machine with `pass_status: true`. Snapshot filenames are 64-hex-prefixed (`data/runs/<26-char id>/inputs/<64>_name.csv`); current depth is ~140-180 chars, headroom under MAX_PATH is real but thin, and one long attachment filename eats it. Fail or at least surface a named blocker when long paths are off, or truncate snapshot basenames.

### F-M12. The Cowork-primary surface cannot bootstrap in the current sandbox, so the pinned suite was not run here

Evidence from this session: `/sessions` is at 100% (uv's default dirs are there), and after redirecting `UV_PYTHON_INSTALL_DIR` the CPython 3.13.7 download from `github.com/astral-sh/python-build-standalone` is blocked by the sandbox network policy ("tunnel error"). The sandbox Python is 3.10.12 and the code requires 3.11+ at import time (`enum.StrEnum`), so no fallback interpreter exists; `.cowork-venv` has never been created (only the Windows `.venv` exists). Conclusions: the "Cowork/Linux launcher" acceptance item has not actually been exercised end to end in this environment, and the review's dynamic checks were limited to pure-stdlib repros. Mitigations worth considering: have `nfl.sh` fall back to any system CPython matching `3.13.*` before downloading; document `UV_PYTHON_INSTALL_DIR`/offline bootstrap; and keep `.cowork-venv` out of the mounted Windows folder (a venv over a 9p mount is slow and symlink-hostile) by defaulting it to `$HOME` keyed by the lock hash. Please run `./nfl.ps1 test` on Windows to reconfirm the suite; README records 49 passing as of the last Windows verification.

## LOW findings

- **F-L1.** `CertificationManifest.solver_proof` is always `{}` (certification.py:157); `SolverResult` gap/node data from the build never reaches the manifest or even the build report. The plan lists solver proof as manifest content, and the QA solver-gap trigger (unwired, F-H1) would need it.
- **F-L2.** `sources.sleeper_daily_player_snapshot` re-serializes the payload and returns an artifact pointing at the normalized copy (sources.py:122-130); the raw content-addressed bytes exist on disk but nothing references them. Return the raw artifact and record the marker as derived.
- **F-L3.** `write_upload_bytes` and `audit_output_bytes` hardcode roster cells at columns 4..4+width (lineups.py:153-156, referee.py:32-33) while `parse_entries` locates "Entry Fee" dynamically. Consistent with the current DK format (verified against the fixture) but the two assumptions will drift apart silently if DK inserts a column; derive the offset from the parsed header. Related nit: a final source line without a trailing newline gains a CRLF if rewritten (`ending or "\r\n"`, lineups.py:158).
- **F-L4.** `underlying_id = team|position|name` (dk.py:197) conflates same-name teammates at a position. Showdown fails closed (role reconciliation errors), Classic conflates silently: lineup validation would wrongly bar rostering both, and opportunity coverage counts them as one person. Rare, but DK IDs exist precisely because names collide; consider requiring explicit disambiguation when the triple collides.
- **F-L5.** Scaffolding vs wired: `ContestContract`, `PlayerIdentity`, `PredictionSnapshot`, `ScenarioBank`, `PortfolioAssignment`, `SettlementBundle`, `ModelRegistryEntry` are never constructed; `RunRegistry`/`lifecycle.transition` are used only by tests (no run lifecycle is persisted in real runs); `assignment_hash` has no callers; `by_gsis` is created and deleted (evidence.py:37-38); `polars` and `statsmodels` are declared dependencies never imported (verified by grep); `scripts/verify_operator_workbook.mjs` imports `@oai/artifact-tool` (unavailable) next to a broken `scripts/node_modules` symlink. `IMPLEMENTATION_STATUS.md` phrases like "SQLite registry ... implemented" are true of the library, misleading about the pipeline; a "library-only, not wired" list there would keep it honest. Trim the deps and the dead script.
- **F-L6.** Rerunning `cowork-run` with an existing `--run-id` raises `FileExistsError` from `_snapshot_inputs` (`mkdir(exist_ok=False)`, cli.py:88), which `main` does not catch (it catches `FileNotFoundError`, not `FileExistsError`), producing a traceback instead of the promised readable JSON stop. Immutability behavior is correct; the reporting is not. Similarly `certify_upload` unlinks an existing file at the output path on a blocked rerun of the same run_id (certification.py:110-111), which is fine within a run but worth a comment given the "never overwrite an earlier output" rule keys on run-scoped paths.
- **F-L7.** Payout TICKET semantics: `validate_payout_tiers` checks monotonicity on the raw `value` column across mixed CASH/TICKET tiers and then ignores a TICKET tier's `value` in favor of face value (payouts.py:56-63). A tier meaning "2 tickets" is mispriced, and a ticket tier's placeholder value can falsely trip or mask the monotonicity check. Define `value` for TICKET (ticket count, probably) and validate against it.
- **F-L8.** `evidence_hashes` keys collide by field name (`f"evidence:{record.field}"`, certification.py:137-141): two records for one field keep only the last artifact id in `input_hashes`.
- **F-L9.** `appg_is_absent_from_model_contract` (opportunity.py:288-291) searches for the substring `"avgpoints"` in snake_case field names, which can never match a field like `avg_points_per_game`; as a guard it is decorative. The real assurance is the mutation test in `test_appg.py` (parse + optimizer equality) plus the structural fact that model inputs are operator CSVs; extend the mutation test through `simulate_factor_bank` output hashes if you want the full downstream claim, and delete or fix the substring check.
- **F-L10.** A short row in a team/player model CSV makes `DictReader` fill `None`, and `_strict_dict_rows`' `value.strip()` raises `AttributeError` (opportunity.py:102) rather than a clean `OpportunityError`; `main` doesn't catch it (traceback, exit code still nonzero). Same pattern risk in `_read_brackets`. Guard for `None`.
- **F-L11.** Field generation realism caveats, fine for a labeled cold-start prior but worth recording: rejection sampling against salary-cap legality skews accepted lineups cheaper than the ownership marginals imply; DST selection is uncorrelated with the QB/stack choice (real fields avoid DSTs opposing their stacks); the FLEX position split (0.42/0.48/0.10) and stack boosts (2.5/1.6) are unregistered magic numbers; and `field_sample_size` stays 1000 unique lineups even in the registered profile, so duplication tails in a 235k field rest on 1000 support points scaled by multiplicity.
- **F-L12.** Simulation realism caveats (all diagnostic-tier, plan already labels them): every team turnover is charged to QBs as an interception (QB absorbs fumble penalties, skill players never lose fumble points; DST side splits INT/fumble but caps INTs at 4 while the QB penalty is uncapped); receptions and kicker points are expectations rather than sampled counts, understating PPR and kicker variance and making reception bonuses impossible; XPs are always made; the opponent score driving points-allowed ignores return/defensive TDs, 2-point tries, and safeties; `_softmax_perturb` gives zero-share players epsilon shares. None of these break accounting; together they narrow tails, which matters most exactly where GPP selection lives. Record them in the build report's warning block or a MODEL_NOTES doc.
- **F-L13.** Workbook brittleness: validations pinned to `B17`/`B18` and `populate_operator_run_control`'s `range(5, 19)` depend on the exact row list (workbook.py:123-130, 324-327); a single added Run Control row silently shifts them. Also `create_review_workbook` accepts `portfolio_metrics` but `_certify` never passes it, so the review workbook's Worst State / Robust LCB / Elite columns are always blank even after a model build whose JSON has the numbers (cli.py:419-425).
- **F-L14.** `ownership.cold_start_states` recomputes `median_utility` per state inside the loop (invariant), applies bracket HIGH to every bracketed player under LATE_VALUE_SURGE regardless of whether the player is late value, and `_rank_percentile` breaks ties by salary-file order; all fine for a prior, all worth a comment.
- **F-L15.** `portfolio._state_metrics` ignores `SimulationResult.weights`. Correct for SELECT/REFEREE (uniform by construction, tail oversampling is DESIGN-only), but nothing enforces that the economics bank it receives is unweighted; one assertion (`purpose != "DESIGN"` or `weights` uniform) would make the invariant structural.

## Plan-vs-claims audit

Where the governing docs say something the code does not yet do (beyond the findings above): `plan.md` §2's contract set is partially decorative (F-L5); §3's role-change redistribution using "active depth, historical role capacity, position, game environment" is a proportional renorm with a capacity ceiling that fails instead of reallocating, and is unreachable anyway (F-M9); §4's repair loop (`run_three_pass_audit`/`decide_repair`) is library-only (F-H1); the workflow state machine is enforced only inside the test-only registry, and real runs record state as strings in JSON reports ("RECONCILED", "CERTIFIED") without the transition guard. `DATA_CONTRACTS.md` matches the code closely; one omission is that it does not document the silent within-team renormalization forcing shares to sum to exactly 1.0 including the uniform-fallback-when-all-zero behavior (opportunity.py:230-262), which can quietly invent shares for a position group supplied as all zeros. `IMPLEMENTATION_STATUS.md` overstates three items: "exact duplication/ties" (F-H3), "REFEREE ... can block" (F-H2), and the implied active QA pass (F-H1); it is otherwise accurate and unusually honest.

## Test coverage gaps

The 22 files are good smoke, property, and contract tests (fixture hashes, fail-closed certification, APPG mutation, schema discovery, locked-cell immutability, learning-gate logic, parquet round-trip). Missing, in priority order: any test of `audit_selected_portfolio` (zero coverage of the QA trigger layer); a test that a candidate identical to a field lineup receives the divided payout (would have caught F-H3); a multi-contest DKEntries rejection test (F-H4); a stale OBSERVED_AT rejection test (F-H6); a late-swap test adding an already-locked player (F-M1); `write_upload_bytes` refusing a prefilled row and preserving a BOM'd template (the BOM path is asserted only in the negative); `select_portfolio` at realistic shortlist sizes under a time budget (F-M5); and an end-to-end cowork-run completion test through certification with model inputs plus official statuses (the current e2e stops at the two-file DO_NOT_UPLOAD and `command_build` is tested only via reduced sizes without the certify chain).

## Recommended fix order

1. `.gitattributes` + recommit fixtures (F-H5): five minutes, protects everything else.
2. Unify candidate/field scoring paths and key self-duplication by canonical key (F-H3).
3. Single-contest hard stop (F-H4) and locked-player swap-in check (F-M1): both are small fail-closed guards.
4. Evidence currency: carry real OBSERVED_AT, set expires_at, add a lock-relative window (F-H6); same treatment for MARKET_OBSERVED_AT (F-M2).
5. Wire QA and REFEREE into certification (F-H1, F-H2), persisting solver proof (F-L1) while you are in there.
6. Vectorize economics and pair selection before attempting the registered profile (F-M5, F-M6).
7. Housekeeping batch: pin nfl.ps1 setup, config load-or-demote, dead deps and script, diagnostics computed not asserted, bracket validation (F-M3, F-M4, F-M8, F-M10, F-L5).

Items 1-5 are correctness and contract integrity and are all small, bounded changes. Item 6 is the only one with real engineering weight.
