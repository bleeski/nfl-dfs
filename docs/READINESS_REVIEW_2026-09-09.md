# Showdown readiness review — September 9, 2026

The real NE–SEA salary and entry files now complete automatic prior-only lineup
generation and a repeatable, independently audited review export. **The system
is not ready to deliver the fully automated, ceiling/ownership/drawdown portfolio
in the project mandate, or to certify generated lineups for upload today.**

The remaining model limitation is substantive. The active Showdown review
selector maximizes DraftKings points of an expected stat line. It does not
maximize true 99th-percentile outcome density or use calibrated ownership,
duplication, leverage, or slate-level ruin. Passing legality and software tests
does not establish those capabilities. The release gate remains intact.

## Verified result

| Check | Result |
|---|---|
| Runtime | Windows, pinned Python 3.13.7; doctor PASS |
| Baseline automated suite | 307 passed, 1 skipped; 81.14 seconds |
| Final automated suite | **332 passed, 1 skipped; 63.06 seconds** |
| New regression coverage | 24 readiness cases plus frozen-package portability |
| Real source acquisition | Approved nflverse downloads and an NWS forecast captured successfully |
| Actual salary pool | 136 CPT/FLEX rows, 68 underlying people, NE–SEA |
| Actual reserved entries | 2 entries in contest 193391013, $20 each |
| Generated review portfolio | 2 legal, canonically distinct lineups |
| Independent final-byte audit | PASS; no problems |
| Changed template lines | Exactly lines 2 and 3 |
| Template length | 144 lines in, 144 lines out |
| Repeated run | Identical exported bytes and SHA-256 |
| Frozen scoring-source resolution | IN_PACKAGE; no original proposal directory needed |
| Windows preflight launcher | Help and argument routing verified |
| Diff whitespace check | PASS |

Final export SHA-256:
`87156b8c108bfe1585c4dc1c689258ee3fd24f525543ae19667be2017cee359e`.

The immutable input hashes remained:

- Salary: `6bc5209f6e2f9e3e44e36efe608fe28dfe3b52248c11e6325001dea73e6e4a73`
- Entries: `797bb9342f0516c373195e236720a783fef9b11e7469c8a46e747a8bea45d02d`

The final review reports these independent truths:

```text
FILE_VALID = true
EVIDENCE_STATE = UNKNOWN
MODEL_STATUS = PRIOR_ONLY
RELEASE_DECISION = DO_NOT_UPLOAD
```

The forecast was generated at 14:00:40 UTC and expires at 20:00:40 UTC
(3:00:40 PM Central). This morning's review package expires before tonight's
kickoff. A live evening run must refresh its sources. No current official
game-day activity report was invented or substituted in this rehearsal.

## Defects repaired

| Priority | Root cause and repair | Evidence |
|---|---|---|
| P1 | Live Cowork froze its clock before downloading sources, then rejected newly captured sources as future evidence. Live stages now advance the clock after acquisition/freezing and before projection. Explicit historical replay remains fixed. | Actual fresh-source run first failed `FUTURE_EVIDENCE:team_source`, then completed; advancing-clock regression passes. |
| P1 | A supplied official-status CSV was discovered and snapshotted but never passed to prior-review selection. It is now hashed, validated for usable provenance and freshness, and INACTIVE people are excluded across both salary roles before redistribution and optimization. | Inactive-kicker and stale-report regressions. Partial ACTIVE coverage never certifies the remaining pool. |
| P1 | Preflight treated an unreadable or malformed policy file as an empty requirement set and omitted model-specific hard fields. Policy errors now block; model-assisted packages must retain their additional required evidence. | Missing-policy and missing-model-evidence probes failed before the repair and pass afterward. |
| P1 | Preflight validated only a version string and coerced truth values, allowing malformed certification data and omitted basis fields. It now validates the complete manifest contract and explicit truth fields. Recorded blockers cannot disappear. | Missing basis, string Boolean and stored-blocker regressions. |
| P1 | Preflight derived selected IDs solely from an evidence dictionary. An omitted player or an INACTIVE value marked PASS could evade the roster check. It now compares ACTIVE evidence IDs with the actual exported roster before checking locks. | Both corruption probes reproduced before the repair. |
| P1 | Official-status parsing accepted `.invalid`, local/IP endpoints and embedded credentials, missed contradictory CPT/FLEX rows, and certification discarded the asserted URL. These inputs now fail; asserted source URLs are retained. | Source-shape, cross-role conflict and source-retention regressions. The gate still relies on operator-attested page contents. |
| P1 | Source freshness could lapse during selection. Projection and supplied official-status freshness/hash binding are checked again immediately before review export. | Expiry-during-selection regression leaves no review CSV. |
| P1 | An old weather capture could gain a longer lifetime from newly frozen priors. Supplied captures now reject ages over six hours and cap the team-prior expiry, which remains bound through projection and selection. | Stale-weather and downstream expiry tests; final real package expires at its forecast deadline. |
| P1 | Frozen priors referenced raw scoring files outside the package. Freeze now copies and verifies every contributing raw artifact inside its own content-addressed directory. | All frozen sources resolve IN_PACKAGE; actual package reuse completes. |
| P1 | Validation could report PASS while skipping interval/tail checks for insufficient data. Insufficient samples now block a validated result. | One-observation regression. |
| P1 | Challenger promotion ignored inadequate slate history and failed prospective field gates. Both now block promotion. | Zero-history and failed-field-gate probes. |
| P1 | Rolling-origin folds split identical outcome timestamps and could train on outcomes unavailable at the validation prediction cutoff. Folds now keep timestamps together and require training outcomes to precede that cutoff. | Same-time and unavailable-outcome probes. An untouched final holdout and real validation history are still required. |
| P2 | `nfl.ps1` rejected the documented `preflight` command. The launcher now accepts it. Relative CLI attachment/package paths also resolve correctly while request confinement remains enforced. | Launcher help and relative-path regression. |
| P2 | Cowork instructions routed a normal Showdown generation request into the older diagnostic economics profile. Instructions now explicitly select `prior_review --build-priors`, document NWS acquisition and current activity handling, and explain the review-only exit status. | Updated CLAUDE contract and Cowork runbook. |

Source changes are in
[prior_review.py](C:/Users/benja/Documents/Claude/nfl-dfs/src/nfl_dfs/prior_review.py),
[preflight.py](C:/Users/benja/Documents/Claude/nfl-dfs/src/nfl_dfs/preflight.py),
[evidence.py](C:/Users/benja/Documents/Claude/nfl-dfs/src/nfl_dfs/evidence.py),
[priors.py](C:/Users/benja/Documents/Claude/nfl-dfs/src/nfl_dfs/priors.py),
[cli.py](C:/Users/benja/Documents/Claude/nfl-dfs/src/nfl_dfs/cli.py),
[cowork.py](C:/Users/benja/Documents/Claude/nfl-dfs/src/nfl_dfs/cowork.py),
[model_validation.py](C:/Users/benja/Documents/Claude/nfl-dfs/src/nfl_dfs/model_validation.py),
[learning.py](C:/Users/benja/Documents/Claude/nfl-dfs/src/nfl_dfs/learning.py), and
[training.py](C:/Users/benja/Documents/Claude/nfl-dfs/src/nfl_dfs/training.py).

## Remaining gaps against the mandate

| Project requirement | Current implementation and remaining work |
|---|---|
| True contest ceiling | Prior review uses central-estimate scoring. The separate simulator has unvalidated distributions, fractional event approximations, turnover/scoring limitations and no complete availability mask. Complete event/scoring accounting and temporal tail calibration before claiming true p99. |
| Portfolio drawdown minimization | Prior review imposes distinct Captains and a maximum personnel overlap. These are structural differentiation rules, not a drawdown model. User-configurable global/person/Captain exposure caps and risk-based allocation are not complete. Distinct Captain per entry also bounds the supported portfolio size. |
| High-integrity market consensus | nflverse provides traceable historical statistics and schedule lines. Those lines carry no sharp-book consensus or publisher timestamp. Sharp market/prop feeds and discrepancy checks are not implemented. |
| Role-change prediction | Prior-season opportunity and snap shares are supported. Current route participation, detailed depth-chart changes, vacated roles and scheme adjustments are not a complete predictive model. Active backups and rookies can be badly valued despite legal output. |
| Ownership and leverage | The active review selector has no ownership, leverage, duplication or field term. The separate economic path still scales sampled field multiplicities and requires the W8/W9 redesign. Do not call its prior outputs EV. |
| LLM contextual adjustments | Source and exact-ID contracts exist. A complete bounded qualitative-evidence-to-numerical-constraint workflow is not deployed. Human interpretation must not manufacture projection numbers. |
| Structural strategy | MILP enforces DraftKings legality and selected diversification constraints. Required strategic stack/bring-back/negative-correlation policies and exposure envelopes are not all wired as solver constraints. |
| Model promotion | The repaired helpers are necessary safeguards. There is still no prospectively validated live artifact/registry path with sufficient settled-slate history. The CLI correctly keeps generated models PRIOR_ONLY. |
| Complete Cowork acceptance | Windows acquisition and execution were tested. The actual Claude Cowork/Linux VM was not available in this environment; only Docker Desktop's WSL distribution was present. One symlink-escape test was skipped because Windows denied symlink-creation privileges. Registered-size 20-max/150-max refresh and peak-memory acceptance remain unverified. |
| Submission | No generated upload package was certified and no DraftKings login, entry edit, upload or money action occurred. Missing live activity/model gates remain binding. |

The full historical architecture review remains useful for W3, W8–W13, but its
repaired findings must be read alongside this report. We did not mark those
larger tranches complete or claim that code changes can manufacture prospective
validation history.

## Cowork operation today

Attach the current matching salary CSV and reserved-entry CSV in the project
folder. Ask Cowork to follow the updated CLAUDE contract and generate a Showdown
portfolio using the prior-review profile. It should discover files by schema,
freeze approved sources, obtain outdoor weather evidence, resolve any named
identity ambiguity, and produce the review package. It should read and apply
current official inactive evidence before the final selection near kickoff.

```sh
sh ./nfl.sh cowork-run --input-dir '<attachment-directory>' --profile prior_review --build-priors --label '<slate-label>'
```

This is now a tested generation-and-review workflow on Windows. It is **not a
promise of an upload-ready or tournament-optimized portfolio**. Supplying more
contest CSVs does not remove the model-validation limitation. The manual
guardrail path is available only for separately operator-supplied lineups and
complete current evidence; generated priors must not be relabeled as manual.

## Retained verification artifacts

- [Final automated test log](C:/Users/benja/Documents/Claude/nfl-dfs/outputs/readiness-20260909-verified.log)
- [Machine-readable test results](C:/Users/benja/Documents/Claude/nfl-dfs/outputs/readiness-20260909-verified.xml)
- [Independent real-file QA](C:/Users/benja/Documents/Claude/nfl-dfs/outputs/readiness-20260909-independent-qa.json)
- [Final prior-review run](C:/Users/benja/Documents/Claude/nfl-dfs/outputs/readiness-20260909-final/cowork_run.json)
- [Repeated prior-review run](C:/Users/benja/Documents/Claude/nfl-dfs/outputs/readiness-20260909-repeat/cowork_run.json)
- [New regression cases](C:/Users/benja/Documents/Claude/nfl-dfs/tests/test_readiness_regressions.py)

Tracked and untracked work present at the start was retained. Nothing was
staged, committed, pushed, reset, cleaned or stashed. Existing run artifacts
remain intact; all rehearsal outputs use new run identifiers.
