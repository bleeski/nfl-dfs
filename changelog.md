# NFL DFS Implementation Changelog

This file records completed implementation work and verification evidence for `backlog.md`. Keep entries factual and append new dated sections beneath `Unreleased`. Do not describe planned, diagnostic, synthetic, or structurally legal work as live-certified or upload-ready.

## Unreleased

### 2026-09-08 — One gated `cowork-run --profile prior_review` command

Closes `W4` / R02. Files added: `src/nfl_dfs/prior_review.py`,
`tests/test_prior_review_profile.py`. Files modified: `src/nfl_dfs/cowork.py`
(third profile, prior-chain request fields, per-profile blocker gating),
`src/nfl_dfs/cli.py` (the `prior_review` branch and its flags), `backlog.md`.
`projection.py`, `contracts.py`, `evidence.py`, `priors.py`, `selection.py`,
`participation.py`, `prior_score.py` and `review_export.py` untouched. Nothing
staged or committed.

#### Commands run and what they returned

Runtime, from a local-disk working copy at `/tmp/w4` (see the runtime note
below), with `NFL_DFS_VENV_DIR=/tmp/nfl-cowork-venv`,
`NFL_DFS_UV_CACHE_DIR=/tmp/nfl-uv-cache`,
`NFL_DFS_UV_PYTHON_DIR=/tmp/nfl-uv-python` and `PYTHONPATH=/tmp/w4/src`:

```text
sh ./nfl.sh test -p no:cacheprovider --ignore=.pytest_cache tests
  before any change : 244 collected, 243 passed, 0 failed, 1 skipped, exit 0
  after  every change: 279 collected, 278 passed, 0 failed, 1 skipped, exit 0
python -m compileall -q src                                        exit 0
```

The 35 new tests are all in `tests/test_prior_review_profile.py`. No existing
test was edited, which is the evidence that `diagnostic` and `registered` are
unchanged.

Regression baseline and acceptance, all against the frozen operator downloads in
`data/runs/20260909-showdown-ne-sea/inputs/`
(salary `6bc5209f6e2f9e3e44e36efe608fe28dfe3b52248c11e6325001dea73e6e4a73`,
entries `797bb9342f0516c373195e236720a783fef9b11e7469c8a46e747a8bea45d02d`):

```text
1. cowork-run --input-dir <inputs> --label baseline                  exit 2
   stage RECONCILED, FILE_VALID false, UNVALIDATED, DO_NOT_UPLOAD, 6 blockers.
   Re-run after every change: byte-identical blocker list.

2. cowork-run --input-dir <inputs> --profile prior_review            exit 0
   stage PRIOR_ONLY_REVIEW_EXPORT, FILE_VALID true, problems [],
   EVIDENCE_STATE UNKNOWN, MODEL_STATUS PRIOR_ONLY, DO_NOT_UPLOAD.
   Export SHA-256 87156b8c108bfe1585c4dc1c689258ee3fd24f525543ae19667be2017cee359e.
   Diff against the source template: 145 lines in, 145 out, exactly lines 2 and
   3 changed, which are the two reserved Entry IDs 5232816721 and 5238395397.

3. cowork-run --profile prior_review --build-priors
     --as-of 2026-09-09T06:00:00Z                                    exit 2
   The frozen package expired at 2026-09-09T04:37:46Z, so the run rebuilt rather
   than reused, fetched and froze all seven nflverse artifacts, auto-accepted 8
   identities and 0 blocked, then stopped on
   WEATHER_CAPTURE_REQUIRED:roof=outdoors. No export written.

4. the same command plus --weather-state CLEAR
     --weather-source-uri https://api.weather.gov/gridpoints/SEW/125,67/forecast
     --weather-observed-at 2026-09-08T16:37:07+00:00                 exit 0
   Full rebuild from a fresh fetch: 2 teams, 68 people, weather_basis
   OPERATOR_SUPPLIED:roof=outdoors|OPERATOR_CAPTURE:...  New package expires
   2026-09-09T09:16:27Z. Export SHA-256 identical to run 2, from independently
   re-fetched sources.

5. one byte changed in a copy of team_prior.json                     exit 2
   PRIOR_ARTIFACT_HASH_MISMATCH:team_prior.json:expected=0d1139c6...:actual=f590cd36...
   Review workbook written, zero CSVs written under the output root.
```

Run 4 reused the `api.weather.gov` capture already recorded in this repository's
frozen `team_prior.json` for this game. It is a test of the rebuild machinery,
not a new weather observation.

#### What the profile does

`cowork-run --profile prior_review` drives `priors-propose`, the identity gate,
`priors-freeze`, `project`, `select` and `review-export` itself. Each stage keeps
its artifacts and hashes under `data/runs/<run_id>/prior_review/`, and a stage
failure returns that stage's own named error with no partial export.

It stops at three gates, and only three, because only these three need a human:

1. **Identity.** `projection.py` accepts only `match_method="EXACT"`, so a
   package cannot be frozen on a guess. The one automatic acceptance is a unique
   league-wide normalized name and position match for a person DraftKings flags
   `OUT` or `IR`, because the availability contract makes those people
   unselectable and an accepted-but-uncertain identity then cannot reach a
   lineup. On the real pool that is exactly the 8 rows the operator accepted by
   hand on 2026-09-08, and 0 others. Anything unresolved and still selectable
   stops the run and reports the candidate provider ID, the conflicting nflverse
   team, the roster status and the first four candidates. Every auto-accept and
   its reason is written to `identity_decisions.json` beside the
   `identity_reviewed.csv` that `priors-freeze` consumes.
2. **Weather.** The enum has no `UNKNOWN` member and `api.weather.gov` is
   unreachable from a session. `roof=dome` and `roof=closed` resolve from the
   schedule artifact alone; every other value, `outdoors` and blank and `open`
   included, blocks for the capture URI and its `generatedAt`. Nothing defaults.
3. **Staleness.** The team prior inherits `MARKET_LINE_MOVES_INTRADAY` from
   `games.csv` and expires twelve hours after capture, so a same-day re-run is
   the normal case. An expired package blocks without `build_priors` and is
   rebuilt with it. No path widens an expiry.

`--exclude`, `--unavailable-status` and `--available-status` are wired through so
an operator fade or a DraftKings status code the vocabulary has not seen does not
force a fall back to the six-call sequence.

#### Which blockers gate, and which are only reported

`required_next_inputs` raises five blocker families. Four of them exist for
certification: payout table, advertised prize value, field size, ticket face
value, and official activity evidence, plus the two that this profile produces
itself, model inputs and the source ledger. `_cowork_core_blockers` already
filtered `OFFICIAL_STATUS_REQUIRED` out of the gating set while leaving it in the
reported list; that pattern is now a per-profile filter in
`cowork.gating_blockers`, and `prior_review` gates on none of them. All seven
still appear in the report's `blockers` list and in the review workbook, because
a reader has to be able to see what this file has not been checked against.

#### Why it cannot be talked into certifying

`MODEL_STATUS` and `RELEASE_DECISION` are not parameters of this path.
`_run_prior_review_profile` pins `ModelStatus.PRIOR_ONLY`,
`ReleaseEvidenceState.UNKNOWN` and `CertificationBasis.MODEL_ASSISTED`, and
`derive_release_policy` adds `MODEL_NOT_PROSPECTIVELY_VALIDATED` for every
`MODEL_ASSISTED` package that is not `PROSPECTIVELY_VALIDATED`, so
`CERTIFIED_UPLOAD_PACKAGE` is unreachable regardless of `file_valid` or evidence
state. The function re-asserts that before writing anything and raises if it ever
derived something else. A supplied `assignment_csv` is refused by name rather
than routed into the manual-guardrail path.

#### Runtime note for the next session

The device VM's `$HOME` (`/sessions`) was 100% full, with 794MB free on `/`. The
working copy went to `/tmp/w4`. `sh ./nfl.sh setup` could not run: the
`/tmp/nfl-cowork-venv` left by an earlier session is owned by a different uid and
is not writable, and a second 603MB venv would not have fit. Its installed
versions match `pyproject.toml` pin for pin, and its editable `.pth` points at a
dead prior-session path, so the suite ran against it with `PYTHONPATH` set to the
working copy. `backlog.md` records this. nflverse retrieval from the device shell
worked, including the GitHub release-asset redirect.

#### Open `[BEN: ...]` flags

- `[BEN: nflverse roof=open]` `priors._ROOF_WEATHER` maps `open` to the
  schedule-derived state `ROOF_OPEN`, and `resolve_weather_state` rejects a
  conflicting operator value. `prior_review` still demands the weather capture
  for that roof, but it cannot attach the capture to the artifact metadata
  without tripping `WEATHER_STATE_CONFLICT`, so the capture is recorded only in
  the run report. Closing the gap means editing `_ROOF_WEATHER`, which is `W1`
  territory. Say whether to open it.
- `[BEN: chat-attachment runs]` The sibling `priors/` folder is auto-discovered
  only when it sits inside an already allowed root, which is true for
  `data/runs/<slate>/` and false for a Cowork attachment directory. A run started
  from two files attached in chat therefore needs `--build-priors` plus the
  weather capture, which is roughly ninety seconds and one paste. Confirm that is
  the flow you want, or say where a per-slate package should be cached.
- `[BEN: lineup count]` `--lineup-count` defaults to the number of reserved Entry
  IDs and `assignments_for_entries` cycles when there are fewer lineups than
  entries. Two entries gave two distinct lineups here. Say what you want above
  about twenty entries, where `--max-person-overlap 4` will stop separating them.

### 2026-09-08 — Prior-only Showdown selection and a byte-audited review export

Closes R03 on the selection side and R02's selection half. Files added:
`src/nfl_dfs/participation.py`, `src/nfl_dfs/prior_score.py`,
`src/nfl_dfs/selection.py`, `src/nfl_dfs/review_export.py`,
`tests/test_participation.py`, `tests/test_prior_selection.py`. Files modified:
`src/nfl_dfs/optimizer.py` (one new public method), `src/nfl_dfs/cli.py` (two
subcommands), `nfl.ps1` (two names). `projection.py`, `contracts.py` and
`evidence.py` untouched. Nothing staged or committed.

```text
244 collected, 243 passed, 0 failed, 1 skipped, exit 0
```

Run on the pinned 3.13.7. Note the runtime change below: the device shell died
mid-session and the suite now runs in the cloud container.

#### Availability contract, `participation.py`

`dk.py` has always parsed `status_raw` onto every `SalaryPlayer` and nothing ever
read it. On the real NE@SEA pool that leaves 21 of 68 people `OUT` or `IR` and
fully selectable, including Zach Charbonnet at 44.88% of Seattle's prior carries
and $8,200. The contract classifies from the salary file's own bytes, moves both
Showdown roles of a person together, reports `Q` without excluding it, and
**refuses an unrecognized status rather than assuming it means available**, which
is the failure mode that puts a scratch in a lineup. `--unavailable-status` and
`--available-status` let the operator classify a new DraftKings code explicitly.

Redistribution took three iterations, each forced by a measurement:

1. `opportunity.remove_inactive_and_redistribute` refuses this pool outright.
   Renormalizing over all survivors pushes George Holani past a 0.055
   `role_capacity` built from a 5.5% snap share.
2. Capping at capacity and spilling the remainder gave quarterbacks the carries,
   because their snap share leaves enormous headroom: Sam Darnold measured 0.0854
   to 0.2891 carry share, and a tight end inherited a fifth of the rushing
   touchdowns. Fixed by scoping absorption to the vacating position and removing
   quarterbacks from carry absorption.
3. The cap itself is wrong. **`role_capacity` is a mean prior-season snap share,
   so it describes the role a person held while someone was ahead of him, which
   makes it invalid in the one situation redistribution exists for.** Emanuel
   Wilson's 0.3112 capacity is his share as Charbonnet's backup. Capacity is now
   reported against, never enforced.

Final rule: proportional to prior share, scoped to the vacating position,
uncapped. On the real pool Wilson lands at 66.45% of carries and 70.59% of
rushing touchdowns, Holani at 11.69%, Darnold unchanged, nothing unallocated.

Two data-quality findings are reported rather than enforced. A share above
capacity is usually real football: Charbonnet holds 70.6% of Seattle's rushing
touchdowns on a 48.4% snap share, which is an ordinary goal-line back. A capacity
of exactly zero beside a nonzero share is a snap-artifact join gap, not someone
who never played; Cody White is one, and a false zero is treated as unknown.

#### Prior score, `prior_score.py`

`SCORE_VERSION = prior_points_of_expected_statline_v1`, named for what it is.
Scoring an expected stat line is not the same quantity as an expected score,
because `scoring.score_offense` pays flat yardage bonuses and
`scoring.score_defense` steps between points-allowed tiers. Everyone within 20
yards of a step is reported as threshold-sensitive instead of quietly scored: on
this pool that is Jaxon Smith-Njigba at 103.4 receiving yards and Emanuel Wilson
at 81.9 rushing yards.

Nothing is fitted or hand-typed. Volumes come from the team prior; the three
splits the model-input contract has no field for come from the hash-pinned
prior-season team-week artifact inside the prior package: passing versus rushing
touchdowns, interceptions versus lost fumbles, and the field-goal distance mix.
Kickers score from `field_goals_mean` weighted by the team's own 2025 distance
distribution plus PATs at the team's own conversion rate. Defences score from the
opponent's sacks allowed and giveaways plus the implied total from the market
line. Return touchdowns, safeties and blocked kicks are omitted and declared,
which understates a defence.

Reconciliation verified: attempts plus sacks plus carries equals `plays_mean`,
the touchdown split sums to `touchdowns_mean`, the turnover split sums to
`turnovers_mean`, and the two implied totals sum to `market_total`.

#### Selection, `selection.py`

`PROFILE_VERSION = prior_only_showdown_selection_v1`. Calls the existing MILP
against the prior score over the permitted pool and never imports `field.py`,
`economics.py` or the portfolio objective, which is asserted in the report.

`optimizer.py` gains `add_person_overlap_limit`. `add_no_good` alone forbids only
an exact roster, and in a six-slot pool that left the same six people available
with a rotated captain: the first two-entry solve returned identical personnel.
The new constraint counts people, so both salary rows of a person count once. The
default cap is 4 of 6 plus a distinct captain per entry, which on the real pool
gives 8 distinct people across 2 entries for 5.2 prior points.

#### Review export, `review_export.py`

`certify` requires the payout table, advertised value and field size, and still
ends `DO_NOT_UPLOAD` while the model is unvalidated, so it costs the operator an
afternoon of data entry for no change in outcome. `review-export` separates the
questions: legality and byte fidelity need no economics and run in full (exact
salary-row identity per slot, one captain, person uniqueness, salary cap, both
teams, independent byte audit against the source template, reparse, SHA-256).
Economics are declared not run, and the decision is `DO_NOT_UPLOAD` by
construction rather than by failure.

#### End-to-end rehearsal on the real contest

Two CSVs in, bulk-entry CSV out, 0.48 seconds. Contest 193391013,
`NFL Showdown $2.25M Wednesday Kickoff Millionaire`, $20, 2 reserved entries.

```text
lineup 1  49500/50000  prior 110.246  CPT Jaxon Smith-Njigba
          Jason Myers | Drake Maye | Sam Darnold | Emanuel Wilson | Hunter Henry
lineup 2  49200/50000  prior 105.047  CPT Emanuel Wilson
          Jason Myers | Drake Maye | TreVeyon Henderson | A.J. Brown | Jaxon Smith-Njigba
```

`FILE_VALID: true`, `problems: []`, output SHA-256
`87156b8c108bfe1585c4dc1c689258ee3fd24f525543ae19667be2017cee359e`. Diffed
against the source template: exactly the two reserved entry rows changed, the
trailing instruction column preserved, every other byte identical. No `OUT` or
`IR` person appears in either lineup.

#### Runtime constraint learned

`device_bash` failed with "Failed to create bridge sockets after 5 attempts" and
did not recover, while `get_device_info`, `device_list_dir`, `device_stage_files`
and `device_commit_files` kept working. The documented cloud-container fallback
was used for the rest of the session: stage the sources, build a venv on the
pinned 3.13.7, run the suite there, commit changed files back. One correction to
that fallback: **`uv` is unusable in the container**, managing 268KB of cache in
ten minutes before timing out, while `pip` installed the full pinned dependency
set in 39 seconds. Use `uv` only to fetch the interpreter, which comes from
GitHub and is instant.


#### Windows verification, and the launcher fix that made it possible

The first Windows run of this work errored every test at setup, inside pytest's
own temporary-directory machinery and never inside `nfl_dfs`:

```text
_pytest/pathlib.py:176 find_prefixed -> os.scandir(root)
PermissionError: [WinError 5] Access is denied:
  'C:\Users\benja\AppData\Local\Temp\pytest-of-benja'
```

Two directories had become unreadable to the operator's own Windows account: the
default pytest basetemp root, and the repository's `.pytest_cache`, which is the
same `.pytest_cache` this session had already had to skip with `--ignore` from
the Linux side. Both are consequences of the bridge delete-permission constraint
recorded above, not of any change in this repository. The ERROR set covered
`test_appg`, `test_build_pipeline`, `test_certification`, `test_cowork`,
`test_governed_late_swap`, `test_payouts`, `test_source_ledger` and
`test_workbook_system`, none of which this session touched.

Passing the repair as flags is not possible through the launcher. `nfl.ps1`
declares `[CmdletBinding()]`, so PowerShell adds the common parameters and
prefix-matches them before the script sees its arguments: `-p no:cacheprovider`
binds to `-PipelineVariable` and fails validation. The `test` branch of
`nfl.ps1` now pins both writable roots itself, `%TEMP%\nfl-dfs-pytest` for
`--basetemp` and `%TEMP%\nfl-dfs-pytest-cache` for `cache_dir`, with
`@RemainingArgs` passed last so an explicit operator flag still overrides.
Earlier sessions had been passing a project-local `--basetemp` by hand for the
same reason, visible in the 2026-09-04 entries below; this makes it the default
and keeps the cache plugin enabled.

```text
.\nfl.ps1 test -q
244 collected, 243 passed, 1 skipped, exit 0
```

Windows, pinned 3.13.7. The skip is the pre-existing symlink-privilege case, the
same one in the 171-passed baseline at `f86fd9e`.


### 2026-09-08 — Real NE@SEA Showdown prior package built; weather provenance added

Operator supplied the real contest files. Ran the full W1 pipeline on them and
delivered the package. Files touched: `src/nfl_dfs/priors.py`,
`src/nfl_dfs/cli.py`, `tests/test_priors_adapter.py`, `backlog.md`,
`changelog.md`. `projection.py`, `contracts.py` and `evidence.py` still
untouched. Nothing staged or committed.

Inputs, committed byte-exact to `data/runs/20260909-showdown-ne-sea/inputs/`:

```text
DKSalaries_NE_SEA.csv  6bc5209f6e2f9e3e44e36efe608fe28dfe3b52248c11e6325001dea73e6e4a73  13477 bytes
DKEntries_NE_SEA.csv   797bb9342f0516c373195e236720a783fef9b11e7469c8a46e747a8bea45d02d  15634 bytes
```

Contest 193391013, `NFL Showdown $2.25M Wednesday Kickoff Millionaire`, $20
entry, 2 reserved entries, both blank. 136 salary rows, 68 people.

#### Weather provenance, new

`api.weather.gov` is unreachable from a session but reachable from the operator
browser, and it is already allowlisted as `PUBLIC_DOMAIN`. `priors-freeze` now
accepts `--weather-source-uri` and `--weather-observed-at`, held to the same host
and licence policy as every other source reference through
`validate_source_reference_policy`. An unapproved host is refused even when the
operator types it in, and a URI without an observation time is refused. Without a
URI the basis records `OPERATOR_SUPPLIED_UNATTRIBUTED` rather than silently
implying provenance.

For this game the value is `CLEAR`, from gridpoint `SEW/125,67` generated
`2026-09-08T16:37:07+00:00`: the periods spanning a 17:20 PT kickoff are
`Mostly Sunny` (N 6 mph, precipitation 0%) into `Partly Cloudy` (N 5 mph,
precipitation 3%). Recorded basis:

```text
OPERATOR_SUPPLIED:roof=outdoors|OPERATOR_CAPTURE:https://api.weather.gov/gridpoints/SEW/125,67/forecast:observed_at=2026-09-08T16:37:07+00:00
```

#### Identity: 60 of 68 automatic, 8 accepted on review

57 matched on name/team/position, 1 through the canonical player index, 2 team
defences. The 8 needing a decision were all cases where nflverse's week-1 2026
roster places the person on another team, and **all 8 are DraftKings-flagged
`OUT`**: CJ Dippre, Jack Westover, Mitch Van Vooren, Kayshon Boutte, Kobe
Prentice, Lance Mason, Nick Vannett, Cody White. All accepted, on the reasoning
that each league-wide match is unique, player usage joins on provider person id
rather than current team, and the identity map takes team from DraftKings. The
reviewed decision file is retained at
`data/runs/20260909-showdown-ne-sea/review/identity_reviewed.csv`.

#### Published package

```text
team_prior.json     0d1139c6ae9ed2a2df2f10a07b26c7d2f5b813e4bd584e9c90db4029aac654c9
player_prior.json   04e8b4bb24f4657294a0c2e7984fe1c0c4739a8faadeadad90c445aaa5ec1618
identity_map.json   de395d9ce3d0acee1511587f16089da51ef78b58ea62b56b503cae47a37d714b
prior_package.json  312ee5d1dc9ce5c3d42576961417f8b0ca4596ace8594a7855ad3ae684a0ed13
```

A second freeze from the same frozen artifacts reproduced all three
byte-identically. `project` accepted the package and published
`team_projections.csv` (2 rows), `player_opportunities.csv` (68 rows) and a
reconciled ledger at `MODEL_STATUS=PRIOR_ONLY` / `RELEASE_DECISION=DO_NOT_UPLOAD`.
Derived team rows: NE 61.41 plays, 0.5268 pass rate, 8.882 Y/A, 3.12 TD, market
44.5 / +3; SEA 59.71 plays, 0.5005 pass rate, 8.447 Y/A, 2.59 TD, market 44.5 / -3.

Market cross-check against a book, through the operator browser: Action Network
shows this game opened NE +4.5 / SEA -4.5 and currently sits NE +3 to +3.5 /
SEA -3 to -3.5 across bet365, DraftKings, Fanatics and Caesars. The artifact's
`spread_line` of 3 agrees with the current market. **The total of 44.5 was not
independently verified**; the Action Network total tab did not open under
automation and was not pursued further.

#### R03 quantified on the real pool, and it is disqualifying for a generated lineup

21 of the 68 people are `OUT` or `IR` and 2 are `Q`, leaving 47 selectable. The
participation contract does not exist, so every one of those 21 remains
selectable by the solver and scoreable by the simulator:

```text
Zach Charbonnet  SEA RB OUT  $8200  capacity 0.484  carry share 44.88%
Kayshon Boutte   NE  WR OUT  $5600  capacity 0.675  target share  7.80%
Terrell Jennings NE  RB OUT  $2400  capacity 0.083  carry share   4.82%
Julian Hill      NE  TE IR    $200  capacity 0.550  target share  3.39%
```

Charbonnet carries the second-highest carry share in the Seattle pool at a
mid-range price. A projection-maximizing solver rosters him, and the retained
review probe shows a zero-capacity person still averaging 7.99 points across 984
of 1,000 scenarios. Worse, his 44.88% of carries should redistribute to Emanuel
Wilson (30.49%) and George Holani (5.37%) and does not.
`opportunity.py:308 remove_inactive_and_redistribute` exists but is not wired to
the DraftKings `Status` column or to any evidence contract. That wiring is `W3`.

Operator-facing table joining every person's derived opportunity shares to the
DraftKings status is retained at
`data/runs/20260909-showdown-ne-sea/review/opportunity_review.csv`.

#### Tests

```text
206 collected, 205 passed, 0 failed, 1 skipped, exit 0
```

Two added: the weather source URI held to source policy (approved host accepted,
`actionnetwork.com` refused, missing observation time refused, future observation
refused), and an outdoor freeze recording the capture URI in coverage.


### 2026-09-08 — W1: R01 nflverse prior adapter, and the Linux/Cowork runtime unblocked

Tranche `W1` per `docs/session-prompts/W1-priors-adapter.md`. Files touched:
`src/nfl_dfs/priors.py` (new), `tests/test_priors_adapter.py` (new),
`src/nfl_dfs/cli.py`, `src/nfl_dfs/sources.py`, `src/nfl_dfs/system.py`,
`nfl.sh`, `nfl.ps1`, `docs/DATA_CONTRACTS.md`, `docs/COWORK_RUNBOOK.md`,
`backlog.md`, `changelog.md`. `projection.py`, `contracts.py` and `evidence.py`
were left untouched for `W2`; verified with `git diff --quiet` on each.

Nothing was staged or committed.

#### Step 0: the Linux runtime now works, and the cause was not disk space

`sh ./nfl.sh setup` first failed with
`failed to create directory .../.local/share/uv/python: No space left on device`
(`/sessions` is 9.8G, 9.4G used, 0 available). Relocating the interpreter did not
fix it either: extraction failed with `Operation not permitted` on
`share/terminfo/2/2621a`.

One root cause explains every symptom: **the Cowork device bridge refuses file
deletion inside a mounted folder**, `unlink` and `rmdir` returning `EPERM`.
Confirmed directly. It breaks `uv` extraction (it cleans its own `.temp`),
SQLite in both `WAL` and `DELETE` mode (`disk I/O error`; `journal_mode=MEMORY`
is the only mode that works there), and `tempfile.TemporaryDirectory`, whose
cleanup handler retries `rmtree` on every `PermissionError` and recurses to
`RecursionError`. `ignore_cleanup_errors=True` does not help, because the
recursion happens below it.

Repairs:

- `nfl.sh` honours `NFL_DFS_VENV_DIR`, `NFL_DFS_UV_CACHE_DIR` and
  `NFL_DFS_UV_PYTHON_DIR`. Every default is unchanged and `nfl.ps1` is untouched
  apart from two new subcommand names. With the runtime on local disk `uv sync`
  completes in 17 seconds instead of exceeding 178 seconds unfinished.
- `system.py` `doctor()` owns its probe lifecycle with `mkdtemp` plus
  `shutil.rmtree(ignore_errors=True)`, which never recurses, and reports a
  surviving probe directory in a new `workspace_probe_cleanup` field.
- `system.py` tries the preferred SQLite journal mode, falls back to `DELETE`,
  and records the real failure in a new `sqlite_probe_error` field. Reporting
  what the workspace supports is the purpose of that probe.

**A session can now execute the suite, which unblocks every later tranche.** The
invocation is
`sh ./nfl.sh test -q -p no:cacheprovider --ignore=.pytest_cache tests`; the
ignore is required because `.pytest_cache` in the mounted repository is
unreadable.

Still open: `nfl.sh doctor` against the mounted repository reports
`pass_status: false` with `sqlite_probe_error: DELETE:OperationalError:disk I/O
error`. That is correct, not a defect. `cowork-run` gates on `pass_status` and
`registry.py:30` opens a real database under `data/registry/`, so the engine
cannot run in place in a mounted folder. Either the session is granted delete
permission on the folder (requested this session and auto-denied by the
permission classifier before reaching the operator), or runs execute from a
local-disk working copy with the mounted repository as the source of truth for
edits. Running the suite in place also leaves undeletable temporary directories
behind.

#### Step 2: reachability, measured from the device VM and the cloud container

| Host | Result |
|---|---|
| `raw.githubusercontent.com` | 200 |
| `api.github.com` | 200 |
| `github.com/.../releases/download/...` | 302 to `release-assets.githubusercontent.com`, which then serves 200 |
| `api.weather.gov` | no connect |
| `api.sleeper.app` | no connect |
| `api.the-odds-api.com` | no connect |
| `actionnetwork.com` | no connect |

The 2026-09-08 constraint that release assets are unreachable was wrong: they
are reachable, and the block was policy. `release-assets.githubusercontent.com`
is not in `ALLOWED_HOSTS` and `fetch_public_artifact` set
`follow_redirects=False`. The api.github.com octet-stream asset endpoint
redirects to the same host, so there was no allowlisted route to the bytes.
Confirmed code-only, no player data: `nflverse-data` (28 blobs),
`nflverse-pbp` (123), `nflverse-players` (59), `nflverse-rosters` (46),
`nflverse-data-archives` (1). Only `nflverse/nfldata` publishes data in a repo
tree.

`sources.py` now follows exactly one redirect hop, only from a
`github.com/{owner}/{repo}/releases/download/...` URL, and only onto
`release-assets.githubusercontent.com` or `objects.githubusercontent.com`. Every
other host keeps `follow_redirects=False`. The recorded `source_uri` stays the
canonical `github.com` URL, already approved under
`PERMITTED_REPOSITORY_LICENSE`. A related latent defect is fixed in the same
place: an unfollowed redirect previously passed `raise_for_status` and produced
an empty artifact that would have been hashed as data.

**This widens a security boundary and needs explicit operator sign-off before
any certified run depends on it.**

#### Step 3: the adapter

`src/nfl_dfs/priors.py`, `ADAPTER_VERSION = nflverse_prior_adapter_v1`, reachable
as `priors-propose` and `priors-freeze` from both launchers. It reads seven
approved artifacts, archives their raw bytes content-addressed under
`<package>/raw/`, and records hashes, source URIs, captured and observed times,
per-source expiry with its staleness basis, license decision and parser version
in `source_manifest.json`. The package resolves without any file outside it.
Contracts and transformations are documented in `docs/DATA_CONTRACTS.md`.

Design decisions taken and their reasons:

- **Two phases, because DraftKings and nflverse share no key.**
  `projection.py:374` accepts only `match_method="EXACT"`, and the backlog holds
  that a normalized crosswalk match is a proposal until reviewed and frozen.
  `priors-propose` emits only normalized match methods; `priors-freeze` requires
  the reviewed file's SHA-256, `DECISION=ACCEPT` on every row, an unaltered row
  and a unique provider id, and only then writes `EXACT`.
- **Team identity from the DST nickname.** DraftKings names its DST row after the
  team nickname and `nfldata/teams.csv` publishes that nickname per season, so
  `LAR` resolves to nflverse `LA` from data rather than a hand-written mapping.
  Cross-checked against a unique schedule row matched on season, the crosswalked
  team pair and the DraftKings kickoff date.
- **Expiry composes.** An emitted artifact expires at the earliest expiry among
  its contributing sources, capped at the game's lock time.
- **Zero prior support fails closed.** `PRIOR_SUPPORT_MISSING` names the team and
  the weight group. Uniform filling and imputation are never applied.
- **Player usage joins on person, not team**, because players move; filtering by
  current team would silently zero someone productive elsewhere.
- **`uncertainty` is the coefficient of variation of weekly offensive plays.** A
  dispersion indicator over the same frozen bytes, explicitly not a calibrated
  variance or a confidence interval.
- **A custom canonical serializer.** `json.dumps(default=str)` quotes every
  `Decimal` and `TeamSourceRecord` rejects a quoted number. Floats are refused
  outright so no unstable repr reaches a derived artifact.
- **Weather.** `roof` of `dome`, `closed` or `open` derives the enum from the
  frozen artifact. Anything else requires `--weather-state`, because the enum has
  no `UNKNOWN` member and `api.weather.gov` is unreachable from a session.

#### Verified against the real NE@SEA Showdown pool

`tests/fixtures/supplied/DKSalaries Salary CSV Showdown.csv`, SHA-256
`86a837c50eb36130a4e2bf2642a9457f08c6487dde8a4c2bccd793c91a7f6309`, 126 rows and
63 people, against live nflverse artifacts.

`priors-propose` resolved 55 of 63 people automatically: 52 on
name/team/position, 1 through the canonical player index, 2 team defences. The
remaining 8 are people the DraftKings pool places on NE or SEA while the nflverse
week-1 2026 roster places them on another team (TB, WAS, DAL, HOU, NYG, PIT, BAL,
LV), 6 of them at `DEV` or `CUT` status. Each is reported as
`NAME_POSITION_OTHER_TEAM` with its candidate provider id, the conflicting team
and the roster status, so the review file is actionable rather than blank. They
are not bound automatically; that is the gate working.

A rehearsal `priors-freeze` in a scratch directory, accepting those 8 to exercise
the path, then confirmed on real bytes:

- Two freezes from the same frozen artifacts produced byte-identical JSON:
  `team_prior.json d3cd26b5…`, `player_prior.json 1d960973…`,
  `identity_map.json 25965a4b…`.
- 63 people, one mapping and one record each, all keyed to FLEX ids, no captain
  id mapped, both roles reconciled in `coverage`. Kickers and both defences
  included.
- `project` accepted all three artifacts and published
  `team_projections.csv` (2 rows), `player_opportunities.csv` (63 rows) and a
  reconciled `nfl_source_ledger_v1`, reporting `MODEL_STATUS=PRIOR_ONLY` and
  `RELEASE_DECISION=DO_NOT_UPLOAD`.
- The outdoor game refused to freeze without a weather state, with
  `WEATHER_STATE_REQUIRED:roof=outdoors`.
- Derived team values spot-checked against the raw artifact: NE 4459 passing
  yards on 502 attempts is 8.882 Y/A, matching the emitted value exactly; plays
  61.41, pass rate 0.5268, rush 4.435 all reconcile. Both teams sit at the high
  end of historical Y/A, which is a property of the 2025 dataset rather than the
  transformation, and is worth an operator sanity check.
- Market fields came from `games.csv`: total 44.5, `spread_line` 3 emitted as NE
  `+3` and SEA `-3`. `coverage.market_attribution` is
  `NFLVERSE_SCHEDULE_NO_BOOK_NO_PUBLISHER_TIMESTAMP`, because that artifact
  carries neither.

#### Tests

`sh ./nfl.sh test -q -p no:cacheprovider --ignore=.pytest_cache tests`, run by
the session on the pinned Python 3.13.7 runtime, on both a local-disk working
copy and the mounted repository:

```text
204 collected, 203 passed, 0 failed, 1 skipped, exit 0
```

The single skip is the pre-existing `test_cowork.py:115` Windows junction case.
The Windows baseline at `f86fd9e` was 171 passed with the same skip;
`tests/test_priors_adapter.py` adds 32. `git diff --check` and `compileall` pass.

New coverage: byte-identical reproducibility; `AvgPointsPerGame` mutation leaving
both derived artifacts unchanged; one record and one mapping per person with K
and DST present and both Showdown roles reconciled; shares normalized over the
pool and provably non-uniform; postseason and other seasons excluded; salary,
review-file and frozen-artifact hash mismatches; insufficient team coverage;
unaccepted, altered and duplicated review rows; output-directory reuse; refusal
to uniform-fill an unsupported group; `project` consuming the package; stale
sources refused by `project`; zero-capacity people reported; per-team spread
sign; weather derivation and refusal; proposals never claiming `EXACT`; a
cross-team person reported with its candidate; ambiguity left unresolved; the
player-index fallback tier; expiry composition and the lock cap; and the
`sources.py` redirect being confined to GitHub release downloads.

#### Reported, not repaired

- **R03 stands.** A `role_capacity` of zero does not remove a person from
  scoring. On the NE@SEA pool the adapter reports 4 such people, both kickers and
  both defences, in `zero_role_capacity_people`. Tranche `W3` owns the
  participation mask. Not papered over here.
- **`projection.py` requires a prior record for every person in the pool**
  (`SALARY_PERSON_IDENTITY_COVERAGE_MISMATCH`). A DraftKings pool routinely
  contains a practice-squad elevation or a just-signed person with no honest
  prior. Today the whole package fails rather than publishing without them. This
  is a real design tension between fail-closed and pool reality, and it needs a
  decision before the Sunday run.

#### Open `[BEN: ...]` flags

- **[BEN: weather_state]** for NE@SEA. Lumen Field is `roof=outdoors`,
  `games.csv` carries no weather, and `api.weather.gov` is unreachable from a
  session though it is allowlisted and reachable from a browser. Required before a
  real freeze.
- **[BEN: current Showdown salary CSV]**. The repository fixture is a 2026-09-01
  download. A real run needs the current file for the exact contest.
- **[BEN: 8 identity decisions]** in `identity_review.csv`, listed above.
- **[BEN: sources.py redirect sign-off]** before a certified run depends on it.
- **[BEN: market source]**. `actionnetwork.com` cannot be an artifact source:
  it is not in `ALLOWED_HOSTS`, and the `OPERATOR_SUPPLIED` escape at
  `sources.py` is hardcoded to DraftKings, so even an operator-supplied number
  fails the gate. `games.csv` is the artifact of record until that changes.


### 2026-09-08 — Production readiness review triage, Showdown-first sequencing, backlog restructure

No production source, test, or configuration file was changed. Documentation and
tracking only.

Added:

- `docs/SHOWDOWN_FIRST_PRODUCTION_PLAN.md`. Splits readiness into a reachable
  prior-only Showdown review product and a certified-upload product that cannot
  exist before settled slates provide prospective validation evidence. Sequences
  R01-R15 for Showdown and records four places the review's own sequencing is off.
- `docs/session-prompts/W1-priors-adapter.md`. Paste-ready session prompt for the
  R01 adapter.
- A `Post-review work tranches` section in `backlog.md` mapping every open finding
  R01-R15 onto session-sized tranches W1-W13, with dependencies, plus a dated
  deadline reality check.

Verified in this session against `codex/s6a-deterministic-projection-producer` at
`f86fd9e`:

- R05 cloning is a default, not an architecture. `cli.py:1314` takes
  `min(opponent_count, args.field_sample_size)` and `--field-sample-size` defaults
  to 1000 (`cli.py:2396`, hardcoded at `cli.py:2031` and `cli.py:2275`), then
  `scale_field_multiplicities` inflates to field size. `economics.py:115` already
  streams one scenario at a time against a chunked field and never materializes a
  field-by-scenario matrix, so the constraint is CPU time, not memory.
- R07 confirmed at `portfolio.py:128` (`mean - 1.96 * standard_error`) and
  `portfolio.py:189` (worst state chosen by the same quantity).
- R03 confirmed at `simulation.py:84`: `salary_people != model_people` raises, so an
  unavailable person cannot be removed from the model.
- R06 confirmed at `cli.py:1302` and `cli.py:2398`: a 20,000-lineup bank is cut to
  250 by mean projection then summed p90, against a 5,000 ceiling at `cli.py:1308`.
- R12 confirmed: `cli.py` sets `ModelStatus.PRIOR_ONLY` on successful model load and
  no registry or loader exists.
- Session egress reaches `raw.githubusercontent.com` and `github.com` only.
  `api.sleeper.app`, `api.weather.gov`, and `api.the-odds-api.com` fail to connect
  from both the device-side Linux VM and the cloud container.
- The device-side Linux VM has `uv` and Python 3.10.12, no `.cowork-venv`, and a
  `/sessions` mount at 100% capacity. The Linux runtime remains unbootstrapped and a
  session cannot currently execute the suite or invoke the Windows launcher.

Tests: none run. The 171-passed/1-skipped baseline is carried from the review, not
re-executed here.

Blockers unchanged: R01-R15 all open. Operator prerequisites for DL4 and DL5 (a
matching Showdown reserved-entry template, contest facts, approved prior artifacts,
current official activity evidence) are still missing, so DL4 and DL5 are retargeted
from the 2026-09-09 opener to a Sunday 2026-09-13 single-game contest, with the
opener run as a manual-guardrail rehearsal only.

### 2026-09-04 — DL2/S6A: deterministic prior projection producer

Changed:

- Added a local `project` command to both launchers. It requires the untouched
  salary CSV, versioned team-prior and player-prior JSON, an exact frozen
  provider-to-DraftKings identity map, the independently recorded SHA-256 of
  all four artifacts, an explicit timezone-aware `as_of`, and a new output
  directory.
- Added strict S6A contracts and deterministic transformation code. Approved
  source/license/parser combinations, capture/observation/expiry times,
  evidence states, declared and computed coverage, finite bounds, unique stable
  provider identities, complete team/person coverage, and exact team/position/
  underlying-person/DK-ID mappings all fail closed. Normalized/fuzzy mappings
  never assemble. Showdown emits one FLEX ID per underlying person and rejects
  CPT/FLEX identity conflicts.
- Team fields are direct bounded frozen source fields. Player share outputs are
  position-masked source weights divided by their eligible team totals; an
  all-zero or missing group is rejected rather than filled uniformly. No
  coefficient fitting, clipping, imputation, or LLM-authored number exists in
  the runtime path, and DraftKings APPG is never read numerically.
- Outputs are built in a temporary sibling directory, checked through
  `load_opportunity_model`, hashed, bound into a four-entry
  `nfl_source_ledger_v1`, validated through `validate_source_ledger`, and only
  then atomically published as `team_projections.csv`,
  `player_opportunities.csv`, and `source_ledger.json`. Existing destinations
  and any failed build publish no package.
- Extended ledger entries with deterministic coverage records and separated
  non-fetching operator-supplied DraftKings provenance references from the
  still-prohibited DraftKings retrieval path.
- Updated Cowork/operator/data-contract/status documentation and the missing-
  input handoff to use the new producer while preserving
  `MODEL_STATUS=PRIOR_ONLY` and `RELEASE_DECISION=DO_NOT_UPLOAD`.

Verification:

- Focused producer, source-ledger, and APPG suite: 39 passed in 2.37 seconds.
- Producer plus existing build, Cowork, certification, governed late-swap,
  late-swap learning, and release-truth suite: 112 passed, 1 skipped in 27.08
  seconds. The skip is the existing Windows symbolic-link privilege case.
- Complete Windows suite with a unique project-local `--basetemp` and pytest
  cache disabled: 171 passed, 1 skipped in 31.33 seconds.
- Independent Classic fixture inspection: exact headers, 24 team rows, 719
  person rows, four ledger entries, loader success, ledger-validator success,
  and exact reconciliation of team SHA-256
  `f9370dbb20ce78a40ffe159f4d78a7abf76e9248858ffb08f4ef8ac6931ff279`
  and player SHA-256
  `603237a30367c9f8f9cba577e6fdda2414fd13e78e4cb635fe931ddcc2081f6c`.
- A separate same-input/two-directory run produced byte-identical team, player,
  and ledger files. Mutating every salary APPG cell left both derived CSV hashes
  unchanged.
- `nfl.ps1 doctor`: pass on Python 3.13.7; SQLite integrity `ok`, WAL mode,
  Excel lock `CLOSED_OR_ABSENT`, and no sync/reparse detection.
- Python `compileall` over `src` and `tests`: pass.
- `git diff --check`: pass.

Remaining blockers:

- The broader S6 historical ingestion, offline fitting/holdout validation,
  live-source refresh, Linux/Cowork execution, real-slate timing, and
  prospective model calibration remain unverified.
- Matching Showdown/Classic reserved-entry templates, contest facts, and
  current official evidence are still required on the September 9/13 delivery
  sequence.

Tracker updates:

- DL2/S6A: `READY` -> `DONE`.
- DL3: `BLOCKED` on DL2 -> `READY`; it is the sole next action.
- Broader S6 remains `BLOCKED`; no later quantitative tranche was started.

Claims explicitly not made:

- No live-slate, Linux/Cowork, calibrated-EV, ROI, profitability, ownership,
  win/cash probability, prospectively validated model, or DraftKings upload-
  readiness claim.

### 2026-09-04 — S3: certification truth states and QA policy

Changed:

- Added a centralized release policy for independent `FILE_VALID`,
  `EVIDENCE_STATE`, `MODEL_STATUS`, and `RELEASE_DECISION` reporting. Legacy
  `status` is derived from the release decision and validated for consistency.
- Certification now constructs, independently byte-audits, reparses, and
  hashes proposed output in memory before release. Evidence/model blockers can
  therefore coexist with `FILE_VALID=true`, while `DO_NOT_UPLOAD` persists no
  upload-shaped CSV. Proposed hashes and categorized file/evidence/model
  blockers remain available in manifests and review artifacts.
- Manual guardrail certification remains explicitly `MODEL_STATUS=UNVALIDATED`
  without becoming a model-performance claim. Model-assisted inputs are
  currently `PRIOR_ONLY`; both `UNVALIDATED` and `PRIOR_ONLY` are barred from
  `CERTIFIED_UPLOAD_PACKAGE`.
- Applied the truth model to certification and late-swap manifests, direct CLI
  results, status/audit output, Cowork reports and diagnostics, build reports,
  and the review workbook Upload sheet. Governed late swap inherits the prior
  certification basis/model status and preserves all S2 authority and byte
  guarantees.
- Limited hard opportunity evidence to selected players. Non-PASS unselected
  pool members are reported by count and exact underlying IDs as a prior-only
  model limitation.
- Downgraded `DST_OPPOSING_PASS_STACK` and incomplete candidate-family coverage
  to advisory findings. Genuine solver proof, simulation accounting, REFEREE,
  hard-evidence, authorization, legality, and final-byte failures remain
  blocking.
- Updated operator/runtime documentation to describe the four truths and the
  manual DraftKings boundary.

Verification:

- Focused certification, QA, Cowork, workbook, build-pipeline, truth-table, and
  governed-late-swap tests: pass.
- Complete Windows suite through `nfl.ps1 test` with a project-local pytest
  temp directory and cache disabled: 144 passed, 1 skipped in 31.93 seconds.
  The skip is the existing Windows symlink-privilege case.
- `nfl.ps1 doctor`: pass on Python 3.13.7; SQLite integrity `ok`, WAL mode,
  Excel lock `CLOSED_OR_ABSENT`, and no sync/reparse detection.
- Python `compileall` over `src` and `tests`: pass.
- `git diff --check`: pass.

Remaining blockers:

- Linux/Cowork runtime, real-slate timing, live calibration, and any
  prospectively validated model-assisted package remain unverified.
- No deterministic projection producer exists yet; DL2/S6A is the next item.
- Matching Showdown/Classic operator templates, contest facts, and current
  official evidence are still required on the delivery schedule.

Tracker updates:

- S3: `READY` -> `DONE`.
- DL1: `READY` -> `DONE`.
- DL2: `BLOCKED` -> `READY`; it is the only next deadline item.

Claims explicitly not made:

- No EV, ROI, win probability, calibrated ownership, profitability,
  live-slate, Linux/Cowork acceptance, or DraftKings upload-readiness claim.

### 2026-09-04 — Deadline delivery punch list and S3 handoff

Changed:

- Updated `backlog.md` to the verified post-merge baseline at `0339914` and the
  current `codex/s3-certification-truth-states` branch.
- Added the living DL1-DL8 punch list for a Showdown review lineup by
  2026-09-09 and Classic review lineups by 2026-09-13, including dependencies,
  operator-supplied inputs, deadline fallback, and explicit deferred work.
- Made S3 the single next implementation item. The minimum deterministic
  projection producer remains blocked until S3 stabilizes its contracts.

Verification:

- Documentation-only tracker update; no production code or numerical model
  behavior changed.
- Before the update, the branch was clean at merged baseline
  `033991452ce655923ff37f48b06c90746ab41ce3`.

Remaining blockers:

- S3 has not been implemented.
- No autonomous deterministic projection producer exists.
- No matching Showdown reserved-entry template or contest facts are stored in
  the repository.
- Linux/Cowork execution, real-slate timing, live calibration, and any
  model-assisted certified upload remain unverified.

Tracker updates:

- Added DL1-DL8; DL1 is the only `READY` deadline item.
- Corrected the stale next action from S2 to S3.

Claims explicitly not made:

- No live-slate, calibrated-EV, profitability, or upload-readiness claim.

### 2026-09-03 — S2: governed late-swap writer and lock evidence

Changed:

- `src/nfl_dfs/late_swap.py` now runs an immutable, fail-closed late-swap
  certification path. It validates a prior `CERTIFIED` manifest and referenced
  output, binds prior/current/proposed artifacts, requires exact Entry-ID
  coverage, derives every replaceable cell from the certified prior, exact
  current-slate IDs, game lock times, and timezone-aware `as_of`, and rejects
  locked-player removal, addition, or movement.
- `src/nfl_dfs/contracts.py` and `src/nfl_dfs/evidence.py` add strict versioned
  contest-eligibility, team inactive negative-list, and late-swap manifest
  contracts. Explicitly empty team reports are distinct from missing reports;
  unknown IDs, team/game conflicts, duplicates, invalid URLs, future/stale
  observations, selected inactives, and non-`PASS` evidence fail closed.
  `NOT_YET_DUE` remains nonblocking for provisional evaluation but explicitly
  blocks a final late-swap release.
- `src/nfl_dfs/lineups.py` adds a dedicated late-swap writer without weakening
  the existing pre-lock writer. Only the lock-derived changed cells may be
  rewritten; all metadata, locked cells, unauthorized rows/fields, BOM state,
  line endings, quoted content, Unicode separators, and final-newline state are
  preserved.
- `src/nfl_dfs/referee.py` independently verifies the late-swap allowlist and
  proves every unauthorized field's physical bytes are unchanged.
  `src/nfl_dfs/dk.py` can reparse candidate entry bytes before an upload-shaped
  file is written.
- `src/nfl_dfs/cli.py` upgrades the shared `late-swap` command used by
  `nfl.ps1` and `nfl.sh`. It requires a unique run ID and explicit salary,
  current prefilled template, prior manifest/assignment, proposed assignment,
  eligibility, inactive-report, output, and timezone-aware `as_of` inputs. It
  returns compact status, blockers, hashes, paths, and one next action.
- Ordinary blocked runs persist `nfl_late_swap_manifest_v1` when writable and
  leave no `DK_UPLOAD_*.csv`; successful runs atomically publish one hash-bound
  CSV only after writer, independent audit, reparse, input-recheck, and
  post-write hash gates pass.
- Added `tests/test_governed_late_swap.py`; updated `CLAUDE.md`, `docs/COWORK_RUNBOOK.md`,
  `docs/DATA_CONTRACTS.md`, `docs/OPERATOR_GUIDE.md`,
  `IMPLEMENTATION_STATUS.md`, and `backlog.md`.

Verification:

- Focused S2 suite: `36 passed in 14.81s`.
- Full Windows suite: `123 passed, 1 skipped in 26.81s`. The existing optional
  symbolic-link test remained skipped because this Windows account lacks
  symlink privilege; Windows junction/reparse coverage passed in the full suite.
- Clean temporary clone of pushed `main` at
  `1073d4345f0db79c2285fd24b0c61b3f3dcfe36d`: supplied fixture hashes passed;
  full checkpoint suite `87 passed, 1 skipped in 14.73s`.
- `.\nfl.ps1 doctor`: pass on Python 3.13.7; SQLite integrity `ok`, WAL mode,
  Excel lock `CLOSED_OR_ABSENT`, and no synchronized/reparse workspace.
- Python compilation and `git diff --check`: pass.

Remaining blockers:

- None for S0 or S2.
- Genuine Linux/Cowork execution is unverified. WSL 2 is present only through
  Docker Desktop's internal distribution, not a usable Cowork test runtime.

Tracker updates:

- S0: `BLOCKED` -> `DONE` after the pushed clean-checkpoint verification.
- S2: `READY` -> `IN_PROGRESS` -> `DONE`.
- S3: `BLOCKED` -> `READY`; no S3 implementation was started.

Claims explicitly not made:

- No live slate, calibrated EV, ROI, win probability, calibrated ownership,
  profitability, conditional contest-state reoptimization, or DraftKings
  upload-readiness claim.
- No DraftKings login, entry editing, upload, credential/cookie access, or
  money action occurred.

### 2026-09-02 — S1: bounded safety and evidence foundation

Changed:

- `src/nfl_dfs/payouts.py` and both build/certification paths in
  `src/nfl_dfs/cli.py` now pass a validated ticket face value into payout CSV
  parsing; ticket rows still fail closed when no face value is supplied.
- `src/nfl_dfs/cli.py` now returns compact `DO_NOT_UPLOAD` JSON for unexpected
  CLI failures, writes a durable Cowork run result plus an internal traceback
  diagnostic after post-intake build/certification failures when storage is
  writable, preserves `KeyboardInterrupt`, and removes upload-shaped CSVs when
  certification fails.
- Added `src/nfl_dfs/byte_lines.py`; `src/nfl_dfs/lineups.py` and
  `src/nfl_dfs/referee.py` now split only on LF bytes and independently preserve
  untouched field bytes, encoding, physical line endings, quoted Unicode
  content, and final-newline state.
- Added strict `LedgerEntry` and `SourceLedger` contracts in
  `src/nfl_dfs/contracts.py` and deterministic validation in
  `src/nfl_dfs/evidence.py`. Certification now rejects arbitrary/unknown JSON,
  unapproved URIs, invalid timezone/license/parser metadata, missing or
  hash-mismatched artifacts, and partial or mismatched hashes for either model
  input.
- `src/nfl_dfs/cowork.py` and the Cowork CLI now confine request inputs to the
  explicitly supplied attachment/request directory, managed project data, the
  specific immutable run directory, or exact explicitly supplied files.
  Traversal, external paths, and symlink/junction escapes fail before hashing or
  copying.
- Updated `docs/COWORK_RUNBOOK.md` and `docs/DATA_CONTRACTS.md` to describe the
  enforced ledger, path, and byte-fidelity contracts.
- Added or expanded regressions in `tests/test_payouts.py`,
  `tests/test_build_pipeline.py`, `tests/test_cowork.py`,
  `tests/test_byte_line_fidelity.py`, and `tests/test_source_ledger.py`.

Verification:

- Pre-change Windows baseline: `65 passed in 13.17s`.
- Targeted S1 tests: pass, including parser and end-to-end ticket handling,
  actual certification-ledger binding, failure artifacts/cleanup, Unicode NEL
  and line/paragraph separators, external/traversal rejection, and a Windows
  junction escape.
- Full Windows suite: `87 passed, 1 skipped in 18.71s`. The one skip is the
  optional symbolic-link test because this Windows account lacks symlink
  privilege; the Windows junction/reparse escape test passed.
- `.\nfl.ps1 doctor`: pass on Python 3.13.7; SQLite integrity `ok`, WAL mode,
  Excel lock `CLOSED_OR_ABSENT`, and no synchronized/reparse workspace detected.
- `git diff --check`: pass.

Remaining blockers:

- None for S1.

Tracker updates:

- S1: `READY` -> `IN_PROGRESS` -> `DONE`.
- S2: `BLOCKED` -> `READY`.

Claims explicitly not made:

- No live-slate readiness, calibrated EV, ROI, win probability, calibrated
  ownership, profitability, or DraftKings upload-readiness claim.

### 2026-09-01 — Multi-session implementation tracking

Added:

- Created `backlog.md` with session-sized work items S0 through S10, dependencies, non-goals, and acceptance criteria.
- Established four separate release truths: `FILE_VALID`, `EVIDENCE_STATE`, `MODEL_STATUS`, and `RELEASE_DECISION`.
- Set S1 as the first implementation tranche: D-04, D-13, D-14, D-24, and D-25.
- Preserved the manual DraftKings boundary and the fail-closed `DO_NOT_UPLOAD` policy.

Verified baseline:

- Branch: `main`.
- HEAD: `e042c7bfc546`.
- Windows test suite: 65 passed on 2026-09-01 using the project virtual environment with pytest cache disabled.
- The working tree remained intentionally dirty; no existing remediation, fixture, review, or user-owned file was reset, cleaned, staged, committed, or overwritten.

Not verified:

- Linux/Cowork runtime.
- Real-slate performance or calibration.
- A model-assisted certified upload path.
- Live-slate or DraftKings upload readiness.

Files changed by this tracker-creation session:

- `backlog.md`
- `changelog.md`

Production code changes: none.

## Entry template for future sessions

Copy this structure under `Unreleased` and replace every placeholder:

```markdown
### YYYY-MM-DD — Sx: short outcome

Changed:

- Exact behavior changed and files involved.

Verification:

- Exact command or check: exact result.
- Full suite: exact pass/fail count.
- `git diff --check`: pass/fail.

Remaining blockers:

- Named blocker, or `None for this backlog item`.

Tracker updates:

- Sx: `OLD_STATUS` -> `NEW_STATUS`.
- Sy: `BLOCKED` -> `READY`, if dependencies and acceptance gates genuinely passed.

Claims explicitly not made:

- No live-slate, calibrated-EV, or upload-readiness claim unless independently proven by the work recorded here.
```
