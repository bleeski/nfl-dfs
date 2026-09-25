# Code review, 2026-09-25

Full read of `src/nfl_dfs/`, `scripts/`, `.claude/hooks/`, the launchers and the
workflows at `bedf6a3` (`main`, Session 11c merged), by five read-only passes
partitioned by module, each verified against the code path it names. The suite
on that commit: `1762 passed, 1 skipped in 338.00s` (Linux). Every finding
here is queued in `docs/ROADMAP.md` §2.2; the session column says where. This
file is evidence, not status.

Severity: BLOCKER means a wrong or duplicate entry file, a lost delivered file
or a lost entry fee is reachable; HIGH a wrong truth, a silent failure or a
boundary violation; MEDIUM a wrong number, a strategy defect or drift; LOW dead
code and style. No BLOCKER was found: every path that writes a DraftKings entry
file goes through `lineups.write_upload_bytes` (refuses prefilled cells), the
byte audit in `referee.py`, a fresh reparse and R29 distinctness, and the
latest-deliverable pointer revalidates all of it before it is advertised. The
findings marked "verified in this review" were confirmed a second time by
reading or probing the code; the rest were confirmed once by the reviewing pass.

## 1. What the operating path is, in one paragraph

`run-slate` builds and publishes a baseline from the DraftKings bytes, then runs
`prior_review`: cold-start priors from the frozen nflverse package, a point
projection per person (`prior_score.py`), and a solve that maximises summed
prior points under the policy's structural rules. **No scenario bank, no
ownership term and no ceiling statistic reach selection.** `simulation.py`,
`ownership.py`, `field.py`, `economics.py` and `portfolio.py` run only inside the
legacy `build` command (`cli.py:1347`), which nothing on the operating path
calls. That is the largest gap between this engine and a large-field winner,
and it is why the prize-tail sessions are ordered as they are.

## 2. Findings that can cost a file or an entry fee (V)

| ID | Where | Defect | Fix | Session |
|---|---|---|---|---|
| V1 (HIGH, verified in this review) | `src/nfl_dfs/portfolio_policy.py:997-1007`, `portfolio_enforcement.py:725-729`, `:1288-1296` | A Showdown policy may set `require_unique_lineups: false`; the joint solve then raises the count bound to the entry count and the audit skips its duplicate check, so identical rows reach `DK_REVIEW_ENTRY_*.csv`; only `readable_review.py:1119` catches it, after the file is on disk. Classic refuses the flag (`classic_portfolio_policy.py:922`). `tests/test_portfolio_enforcement.py:541` defaults the audit helper to `false`. R29 says never. | Refuse `false` in the Showdown validator; delete `repetition_allowed`; audit unconditionally; flip the test default. S | 37 |
| V2 (HIGH, probed) | `scripts/qa_showdown_portfolio.py:45-50` | The byte-fidelity loop exempts roster columns on every numbered row, prefilled or not, so an export that overwrote a prefilled row passes (`exit 0, VERDICT PASS` on a synthetic case). The Classic twin fails such rows (`qa_classic_portfolio.py:150-160`). It also compares parsed cells, not raw lines. | Exempt only the template's blank rows; compare raw lines with `byte_lines`. S | 37 |
| V3 (HIGH, verified in this review) | `src/nfl_dfs/cli.py:1142`, `:1180`, `:1220-1223`, `:4299-4300` | `certify_upload` writes the CERTIFIED file and manifest, then `create_review_workbook` can raise `WorkbookLockedError` (Excel open). The handler re-derives the run id and unlinks the certified CSV, or files the diagnostic under a new id; `run-slate`'s sweep removes every `DK_UPLOAD_*.csv` in the output root. The manifest still says `CERTIFIED_UPLOAD_PACKAGE`. | Build the workbook before certifying, or never delete a file whose manifest hash matches; use the resolved run id. S-M | 38 |
| V4 (MEDIUM, verified in this review) | `nfl.ps1:4` | `ValidateSet` omits `baseline`, so `.\nfl.ps1 baseline`, the runbook's hand-run fallback (`docs/RUNBOOK.md:1210-1212`), is refused by PowerShell before Python runs. `nfl.sh` passes anything through. | Add it, or drop the set. S | 38 |
| V5 (MEDIUM, verified in this review) | `src/nfl_dfs/cli.py:3704` | `outputs/<run_id>` is created with `exist_ok=True` while `data/runs/<run_id>` is refused (`:3652`); a retry after a removed run folder overwrites an earlier `cowork_run.json` and can report the earlier run's pointer as this run's. | Refuse an existing output root. S | 38 |
| V6 (MEDIUM) | `src/nfl_dfs/cli.py:2216-2240` | `status` prints stored manifest truths as current and exits 0 on a stored `CERTIFIED` with no file or hash check; `audit` fixed this pattern (R09), `status` kept it. | Route through `historical_artifact_integrity` or label fields stored and pin `DO_NOT_UPLOAD`. S | 38 |
| V7 (MEDIUM) | `src/nfl_dfs/certification.py:108`, `cli.py:863-887` | `certify` and `validate` use whole-template authority; with any prefilled row, `certify` cannot succeed (`ENTRY_AUTHORIZATION_MISMATCH` or `ENTRY_BLANK_CELL_AUTHORITY_REQUIRED`). Fail-closed but unusable, and the code misleads. | Pass `plan_entries(...).fillable` as `review_export.py:153` does. M | 38 |
| V8 (MEDIUM) | `src/nfl_dfs/cli.py:4251-4367` | The exception exit of a `prior_review` run reports `MODEL_STATUS=UNVALIDATED`; every normal exit pins `PRIOR_ONLY`. | Pass the profile's model status to `_blocked_truth_values`. S | 38 |
| V9 (MEDIUM) | `src/nfl_dfs/prior_review.py:2152`, `:2209-2213` | Showdown without a policy re-parses the entries file after intake with no `ENTRY_INPUT_CHANGED_BEFORE_SELECTION` stop (Classic-only); the manifest binds the new hash, the pointer the old one. The CSV is still audited against disk. | Drop the re-parse; apply the hash stop in every mode. S | 37 |
| V10 (MEDIUM) | `src/nfl_dfs/prior_review.py:3207` | C3 packaging failures are caught only as `(OSError, ValueError)`; a `KeyError` or `TypeError` escapes without `prior_review.json`; the baseline survives, the stage record is lost. | `except Exception`. S | 37 |
| V11 (MEDIUM) | `scripts/qa_showdown_portfolio.py:63-65`, `:103`, `:120` | A sanctioned unfilled row (R29 exhaustion) is `INCOMPLETE_ROSTER`, exit 2; `OVERLAP_*` and `STARTER_WITH_OWN_BACKUP` (operator limits) exit 2 beside roster defects; identity by `Name` alone. | Exit 3 for partial like Classic; strategy findings out of the validity exit; identity by ID. S | 37 |
| V12 (HIGH, verified in this review) | `src/nfl_dfs/cli.py:2058`, `late_swap.py:136-138`, `:583` | Governed late swap's lock clock is `--as-of` alone; nothing compares it to the wall clock, so a stale timestamp makes locked slots "replaceable" and the byte audit, which audits against the same authorization, passes a `DK_UPLOAD` that edits locked cells. Not reachable today (nothing is certified), reachable the day Session 12 lands. | Refuse when `as_of` and `release_clock()` differ past a registered tolerance. S | 12 |
| V13 (HIGH) | `src/nfl_dfs/late_swap.py:397-400`, `lineups.py:323-334` | Late swap compares raw current cells, so the registered `Name (ID)` prefilled form (`docs/DATA_CONTRACTS.md:2359`, `entry_groups.prefilled_cell_id`) reads as "missing from the pool". A gate no re-export clears. | Resolve through `prefilled_cell_id`; compare IDs. M | 12 |
| V14 (MEDIUM) | `src/nfl_dfs/cli.py:1852-1889`, `selection.py:894-910` | Legacy `select` maps every template row, lets `--count` fall below it and cycles lineups; caught only at certify. | Use `plan_entries(...).fillable`; drop the cycling helper. S | 46 |

## 3. Findings that change which lineups get built (S)

| ID | Where | Defect | Fix | Session |
|---|---|---|---|---|
| S1 (HIGH, verified in this review) | `src/nfl_dfs/priors.py:1541-1565` vs `:1661-1680`, `:1795-1812` | Shares are `person season sum / pool season sum` with no per-game normalisation; role capacity is a per-game mean. A player who missed eight of seventeen games carries about half his true share and his teammates inherit the rest. `prior_score.py:83-99` (`salary_rank_divergence`) is the visible symptom. This is the Session 21 question, confirmed, direction: season-sum shares against per-game capacity. | Per-game rates over weeks with a row; a new transformation version, v1 never mutated. M | 21 |
| S2 (MEDIUM) | `src/nfl_dfs/priors.py:1773-1776` | A transfer's pseudo-count is his old share times the **incumbents'** pool total: one 60-attempt backup incumbent gives a 95%-share transfer starter about half; no incumbent gives zero. | Scale by the team's expected pool, not the incumbents'. M | 21 |
| S3 (MEDIUM, verified in this review) | `src/nfl_dfs/selection.py:701-703` | `effective_overlap` is `None` for Classic, so C1 (rung 4) and every unbound fill row are constrained only by exact-roster no-goods: each next optimum is the previous lineup minus one player. This is the "one lineup with 17 perturbations" washout mechanism the 2026-09-15 findings measured. | A Classic overlap cap on the ladder, default about 6. S | 39 |
| S4 (MEDIUM) | `src/nfl_dfs/classic_portfolio.py:397-503`, `:767-772`, `:805-822` | The C2 witness chain expands seed 0, slot 0 (the QB) first, so the witness, the MIP start and the portfolio delivered at a time limit are N copies of the best lineup with the QB swapped. | Enforce the policy overlap while adding neighbours; round-robin seeds and slots. M | 39 |
| S5 (MEDIUM) | `src/nfl_dfs/selection.py:735-745`, `prior_review.py:2318-2320` | The unbound fill is all or nothing: one unfillable row discards a legal C2 or SD3 portfolio. R29's own text is "report the unfilled Entry IDs". | Return the partial fill; name the unfilled rows. M | 39 |
| S6 (MEDIUM) | `src/nfl_dfs/selection.py:282-301` | Policy `excluded_people` bind the policy's rows but the fill uses `run_excluded`, so an operator `--exclude` can be rostered in an unbound row while `relaxation.py:472-474` calls exclusions never relaxed. | Apply policy exclusions to the fill. S | 39 |
| S7 (MEDIUM) | `src/nfl_dfs/portfolio_policy.py:356-368`, `portfolio_enforcement.py:518-558`, `:744-749` | With no captain cap (template default `None`), the captain strata seed one captain and the summed-points objective puts every entry under him. | A default captain cap in the generator and a captain-spread column in every review. S | 23 |
| S8 (MEDIUM) | `src/nfl_dfs/portfolio_enforcement.py:383-389`, `:413-416`, `relaxation.py:760-771` | A Showdown bank that hits its time limit always blocks, however many candidates it holds; Classic converts the same stop to `BOUNDED_TIME_LIMIT_STOP` (Session 08). The ladder then halves the bank and re-runs everything. | Port the "enough plus a witness" rule. M | 40 |
| S9 (LOW) | `src/nfl_dfs/classic_portfolio.py:721-725`, `portfolio_enforcement.py:746-748` | Tie-break perturbations of 1e-9 sit below HiGHS's `mip_abs_gap`, so ties resolve by search order, not the stated rule. | `mip_abs_gap=0` or 1e-4-scale perturbation. S | 40 |
| S10 (LOW) | `src/nfl_dfs/classic_portfolio.py:300-302`, `:851-853`, `:975-977`; changelog 2026-09-23 (Session 08) | `stack_value` rebuilds `by_id` per call; bank generation runs under `tracemalloc`; the C2 witness solve and the final joint solve solve the same candidates twice. Lock-clock minutes. | S | 40 |

## 4. The simulator, before it becomes the operating bank (P, Session 24)

`simulation.py` runs only in legacy `build` today, so none of these reaches a
lineup now. Session 24b puts the bank on the `prior_review` path; these land
first, in Session 24.

| ID | Where | Defect | Fix |
|---|---|---|---|
| M1 (HIGH) | `simulation.py:127`, `:162-166`, `:207-211` | `pass_attempts` is a dropback count (`priors.py:1330`) multiplied by yards per attempt excluding sacks (`:1338`); `sacks_allowed` is drawn and never subtracted. Every passing yard, reception and receiving yard is inflated by dropbacks over attempts (1.075 on 560/42) while rushing is not. `prior_score.py:241` subtracts sacks. | Subtract sacks before yards and catches. S |
| M2 (HIGH) | `simulation.py:39-50` | `_softmax_perturb` clips zero shares to 1e-9 and softmaxes, so an all-zero group becomes exactly uniform (four zero QBs at 0.25 each), the "uniform filling" `priors.py:1818-1821` prohibits. | Return zeros for a zero group. S |
| M3 (MEDIUM) | `simulation.py:129-147` | `market_total` and `market_spread` are carried and never read; team scoring is last season's TD and FG rates. `prior_score.py:262`, `:321` use the market for DST only. | A registered market-anchored scoring rate. M (Session 24c) |
| M4 (MEDIUM) | `cli.py:1253`, `:1419-1425`, `:1441-1443`, `simulation.py:94-101` | The DESIGN bank is tail-oversampled with importance weights no consumer reads; the objectives are the unweighted mean and p90 of a fattened distribution. | Score on the SELECT bank or drop the oversampling; delete the dead weights. S |
| M5 (MEDIUM) | `simulation.py:170-172`, `:254-262`, `:285` | Every team turnover is charged to the QB as an INT; kicker distance mix, a 100% PAT rate and `return_tds ~ Poisson(0.08)` are freehand values in a scoring path; kicker points split evenly across every K row. | Registered constants from the frozen artifact, as `prior_score` does. S-M |
| M6 (MEDIUM) | `simulation.py:199-215` | Receptions and receiving yards are deterministic slices of team totals; the only per-player variance is share noise, so WR and TE ceilings are compressed. | Per-player variance. M |
| M7 (MEDIUM) | `field.py:112`, `:151` vs `ownership.py:60` | The field's FLEX mix (0.42/0.48/0.10) does not match the ownership targets it was sampled from; rejection sampling is salary-blind, so the synthetic field under-spends and duplication estimates are off. | One FLEX constant; cap-targeted sampling. M (Session 24c) |
| M8 (MEDIUM) | `simulation.py`, `ownership.py:41-79`, `field.py:76-84` | No registered `*_version` or `does_not_establish` for the simulator, the cold-start ownership prior or the field model; loadings, sigmas, softmax scales and stack boosts are unregistered constants. `CLAUDE.md` requires registration. | `SIMULATION_VERSION`, `OWNERSHIP_PRIOR_VERSION`, `FIELD_MODEL_VERSION`. S |
| M9 (MEDIUM) | `ownership.py:96-103` | An operator bracket is renormalised away with its group. | Renormalise the unbracketed remainder only. S |
| M10 (MEDIUM) | `projection.py:790-880`, `cli.py:979` | `verify_projection_package` (the ledger cross-check against archived sources) has no runtime caller; a hand-edited `expires_at` passes. | Call it where the ledger is validated. S (Session 42) |

`config/scoring.json` and `scoring.py` match DraftKings NFL scoring exactly
(checked line by line: yards, touchdowns, bonuses, PPR, turnovers, kicker
distances, every DST tier, the 1.5x captain). `AvgPointsPerGame` is a header
token only (`dk.py:291`, `cowork.py:62`) and `tests/test_appg.py` pins it. No
prior is labelled EV, ROI, a probability or calibrated.

## 5. Evidence and retrieval (V and P)

| ID | Where | Defect | Fix | Session |
|---|---|---|---|---|
| E1 (HIGH, verified in this review) | `scripts/fetch_weather_captures.py:64-65`, `:175-182`, `:328-339` | Retrieval through `urllib.request.urlopen`, not `sources.py`: no allowlist check on the forecast URL taken from `nws_gridpoints.json` or the `/points` response, redirects followed to any host, and the "capture" is `json.dumps(forecast)`, a re-serialisation, not the response bytes, with no capture time. `CLAUDE.md`: never bypass the allowlist; every capture keeps raw bytes. | Host check and no-redirect handler; write `response.read()` verbatim; record the fetch time. S-M | 41 |
| E2 (HIGH) | `scripts/make_classic_weather_evidence.py:157-165`, `:239`; `prior_review.py:1605-1609` | Weather expiry is the formatter's run time plus six hours, not the observation time, with no lock cap, and `prior_review` trusts the JSON's `expires_at`. | `min(observed_at + 6h, lock)`; re-derive in `prior_review`. S | 41 |
| E3 (MEDIUM) | `scripts/fetch_weather_captures.py:135` vs `src/nfl_dfs/venues.py:288` | Two hand-kept retractable-roof sets disagree (LV). | A test pinning equality. S | 41 |
| E4 (MEDIUM) | `src/nfl_dfs/evidence.py` `_valid_https_source`; `scripts/make_official_status.py:230-243` | Official-status, eligibility and inactive-report sources accept any public HTTPS host, so nothing distinguishes official from corroborating; the status script has no test and exits 0 after its stale warning. | A registered official-host list; non-zero outside the window; a test. S-M | 42 |
| E5 (MEDIUM) | `scripts/make_offensive_role_evidence.py:329-366`, `qb_depth_roles.py:284`, `:574` | The DK-to-depth-chart binding is a normalised-name match reported as `evidence_state: PASS`. It feeds a prior only and cannot certify, but the label is wrong. | Label it a proposal. S | 42 |
| E6 (MEDIUM) | `src/nfl_dfs/kicker_roles.py:409`, `:636` | `astimezone(utc)` silently localises a naive clock; the sibling modules raise. | Raise. S | 42 |
| E7 (MEDIUM) | `src/nfl_dfs/evidence.py:281-290` | A supplied PASS report naming a selected player inactive before lock minus 90 minutes reports `NOT_YET_DUE`, not `FAIL`; still blocks under `final_release`. | Check inactives first. S | 42 |
| E8 (MEDIUM) | `src/nfl_dfs/contracts.py:498-502`, `:514`, `:619-627`, `:667` | Timestamps without timezone validators; `late_swap.py:251` hand-checks `tzinfo` because of it. | Validators. S | 42 |
| E9 (MEDIUM) | `docs/DATA_CONTRACTS.md:57` | Says the source ledger uses `nfl_source_ledger_v1`; the freshness gate needs v2 (`contracts.py:115-119`, `evidence.py:494-507`); v2 and seven other version strings are undocumented (`depth_chart_effective_rank_v1`, `dk_status_participation_v1`, `nws_gridpoint_forecast_v1`, `nfl_standings_normalizer_q1b_v1`, `nfl_classic_slate_context_v1`, `score_pool_people_v1`, the uncapped redistribution rule). No v1 was mutated. | Docs. S | 45 |
| E10 (LOW) | `scripts/make_settlement_request.py:228-244`; `scripts/file_standings.py:222-240` | Release truths taken from the first sorted JSON with the four keys; standings bound to a contest by filename digits (the export carries no id). | Require a schema version; keep the entry-coverage refusal. S | 45 |
| E11 (LOW) | `src/nfl_dfs/dk.py:184`, `:189`, `:353`, `:427`, `:265-268` | `isdigit()` accepts non-ASCII digits; `scoring_version` is a constant written as a parsed fact; any `Game Info` cell outside the regex refuses the file, which a post-kickoff export may trigger (unverifiable without one). | `isdecimal()`; a real post-kickoff export for Session 12. S | 12, 46 |
| E12 (LOW) | `src/nfl_dfs/referee.py:43`, `:115` | `next(csv.reader(...))` on an empty physical line raises `StopIteration` instead of a named problem. | S | 37 |

## 6. Truths, review chain and orchestration (P)

| ID | Where | Defect | Fix | Session |
|---|---|---|---|---|
| R1 (MEDIUM) | `src/nfl_dfs/prior_review.py:1392-3482` | `run_prior_review` is 2,090 lines with 27 return sites and about 40 live locals; every session that touches SELECT or EXPORT reads it whole. Largest units elsewhere: `classic_review.create_classic_review_package` (995), `readable_review.create_readable_review` (561). | Extract `:2667-3157` and `:3159-3299` to `classic_publish.py`, `:1439-1706` to `review_intake.py`, `:1723-2121` to `review_priors.py`, each behind a frozen dataclass, every blocker text unchanged. L | 44, 44b |
| R2 (MEDIUM) | `src/nfl_dfs/review_export.py:67`, `prior_review.py:2722-2730`, `cli.py:3017-3022` | `EVIDENCE_STATE` is the literal `UNKNOWN` for Showdown and computed for Classic, in three files. | Hoist `overall_evidence_state` above the mode split. M | 44b |
| R3 (LOW/MEDIUM) | `prior_review.py:3023`, `:3050`, `:3247`, `:3302`; `classic_review.py:760-766`; `classic_scale_acceptance.py:679` | `FILE_VALID: True` is a literal in five places with three meanings; `cli._review_release_truths` (`:2515`) is the only cross-check. | One truths builder. M | 44b |
| R4 (MEDIUM) | `readable_review.py:113`, `classic_review.py:213`, `prior_review._write_canonical_json` | Three hash-alias and canonical-JSON helper copies; `ensure_ascii` differs, so a shared artifact would not round-trip byte-identically between writers. | `review_common.py` for helpers; audits keep their own semantics. M | 44b |
| R5 (LOW) | `prior_review.py:1655`, `:1704`, `:1757`, `:1777`, `:1798`, `:3432` | Early returns replace `stages` and drop INTAKE; one exit uses the `PROFILE_VERSION` literal. | S | 44 |
| R6 (LOW) | `readable_review.py:139`, `:1471`; `workbook.py:1059`; `classic_scale_acceptance.py:679` | Proposal artifacts listed without a hash check; `datetime.now()` in the status workbook makes `workbook_sha256` non-reproducible. | S | 44b |
| R7 (MEDIUM) | `src/nfl_dfs/workbook.py:105-664` | Live (`run-slate` writes the status workbook on every review), and 560 lines mirror the HTML renderers column for column. | Render both from one row model. M | 46 |
| R8 (MEDIUM) | `src/nfl_dfs/cli.py:4111-4141` | The registered and diagnostic profiles' `command_build` runs with no budget allowance after the review gate. | Size candidates and per-solve seconds from the budget, or refuse below a minimum. M | 46 |
| R9 (LOW) | `deadline.py:536-561`; `cli.py:2657-2668`, `:3723` | Shared rate ledger with a fixed temp name and unlocked read-modify-write; the baseline runs on `time.monotonic` not the budget clock; `started_after_seconds` can be negative. | S each | 40 |

## 7. Harness and CI (P)

| ID | Where | Defect | Fix | Session |
|---|---|---|---|---|
| H1 (MEDIUM, demonstrated) | `scripts/check_protected_paths.py:106` | `git diff --name-only` with rename detection lists only `CLAUDE2.md` for a rename of `CLAUDE.md`, so the protected check passes without the label; `tests/test_repo_boundaries.py:83-92` catches it today only because the literal path is asserted to exist. | `--no-renames`. S | 43 |
| H2 (MEDIUM, probed) | `.claude/hooks/guard_bash.py` | Not refused: `git -C <dir> push origin main`, `git -c k=v push`, `git push origin "main"`, `git commit -a` in a chain, `restore`, `checkout --`, `gc --prune`, `reflog expire` in a chain, `git add -N .`, `git add . 2>/dev/null` (changelog 2026-09-23 named the last two). Every shape `REFUSED_COMMANDS` lists is refused. | Allow global options before the verb; match `main` on the unstripped command; add the verbs; tests. S | 43 |
| H3 (LOW/MEDIUM) | `.claude/settings.json:41`; `.claude/rules/git-authority.md` | `mcp__github__merge_pull_request` is on the allow list with no check that the head is green; the `windows` job is outside "green means green". A protected-path change. | A PreToolUse hook that reads the check runs; the rule names `windows`. S-M | 19 |
| H4 (LOW) | `.claude/hooks/session_start.py:72`; `.claude/settings.json:126`, `:138` | The truncation note points at a file the hook never writes; the hook commands are POSIX shell, so on Windows they fire only under a bash. | S; one confirmation on Ben's desktop | 43, 16 |
| H5 (LOW) | `scripts/record_verify.py`; `.github/workflows/ci.yml` | `summary_line` matches only the `-q` summary that `pyproject.toml`'s `addopts` produces and has no test; a future `addopts` change yields `NO_SUMMARY_LINE` silently. | A test. S | 43 |
| H6 (LOW) | `sync.ps1:52` | Prints `git add -A` as advice. | S | 45 |

## 8. Dead code and drift (LOW)

Unused in `src/` and `scripts/`: `opportunity.remove_inactive_and_redistribute`
(imported by `participation.py:38`, never called), `priors.resolve_nflverse_game`,
`field.field_marginal_ownership`, `payouts.payout_for_rank` and `divided_payout`,
`sources.sleeper_daily_player_snapshot`, `evidence.parse_official_inactives`,
`late_swap.audit_late_swap`, `lifecycle.invalidate_certification`,
`depth_roles.effective_depth_ranks` and its types (never passed to
`redistribute_opportunity`), seven `contracts.py` classes (`PlayerIdentity`,
`PredictionSnapshot`, `ScenarioBank`, `ModelRegistryEntry`,
`PortfolioAssignment`, `RoleVariant`, `ContestContract`), `simulation.qb_attempts`,
three `cli.py` imports; `config/runtime.json` keys `candidate_generation_min`,
`candidate_generation_max`, `candidate_vector_shortlist_max` (0 readers);
`scripts/verify_operator_workbook.mjs` (imports a package the repository does
not carry); `polars` and `statsmodels` (never imported). `scripts/make_classic_policy.py:174`
still says rung 4 "always produces a legal portfolio" (Session 01 corrected the
claim everywhere else). Three private salary and template parsers in
`scripts/` re-derive identity beside `dk.py` and nothing pins them equal.
`selection.py:100` hardcodes `50_000`. `scripts/build_classic_portfolio.py:456`
unpacks `read_template()` under inverted names. Session 46 decides the legacy
`build`, `select`, `project` and `run` commands: wire them to the operating path
or remove them.

## 9. Test gaps worth a test

No test: `scripts/make_official_status.py`; `record_verify.summary_line`;
`command_status`, `command_validate`, `command_late_swap` as CLI paths; a
Showdown entry-mutation stop; a Classic `write_assignments_csv` determinism and
mutation pair; `dk.embedded_pool_ids`, `single_contest_problems`, the DST edge
of `_parse_game_info`, `DK_SALARY_LOCK_CONFLICT`, `DK_IDENTITY_COLLISION`; a
`(ID)`-form prefilled cell in late swap; `qa_showdown_portfolio.py` on a
prefilled row; `simulation.py` beyond two tests (no sack, zero-share, kicker,
DST or distributional case); `ownership.py` and `field.py` beyond two;
`CLASSIC_C1_EXPORT_POST_WRITE_HASH_MISMATCH` and `--available-status D` in C1;
a Classic fill that runs out of distinct lineups; `tests/test_priors_adapter.py:44`
still hardcodes `AS_OF` (C4 retro #17 was marked done).

## 10. Verified sound (so no session is spent on them)

DraftKings parsing (header from bytes, quoted fields, BOM survives, CRLF and LF
preserved per line and audited, aware Eastern locks, CPT 1.5x enforced at
parse, mode mismatch a hard stop); `write_upload_bytes` per-row authority;
Session 05's presentation-failure path in both modes; `delivery.py`'s pointer
(never names `DK_UPLOAD_*`, revalidates, refuses another run's pointer);
`release.derive_delivery_state` and `derive_release_policy`; `deadline.Budget`
(monotonic, injected, S-class allowances); the relaxation ladder (uniqueness
forced true on every rung, exclusions carried, rung folders never reused);
`baseline.py` (hash-named snapshots, `RUN_ID_COLLISION`, forbidden prefilled
rosters cut before the first solve); the gate registry (1,226 codes, unregistered
code fails closed); the Classic MILP slot structure, the Showdown CPT/FLEX rows,
no-goods, overlap limits and limit-incumbent validation; every RNG seeded;
`push_freshness.py` fails open as designed; CI runs the pinned suite that
`nfl.sh test` runs and `protected-paths.yml` reads the live label.
