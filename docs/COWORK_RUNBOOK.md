# Claude Cowork Runbook

## Showdown generation: current operating path (2026-09-09)

For the normal request to generate a Showdown portfolio from the two attached
CSV files, run:

```sh
sh ./nfl.sh cowork-run --input-dir '<attachment-directory>' --profile prior_review --build-priors --label '<slate-label>'
```

This generates prior-only review lineups. It does not implement the full
ceiling/ownership/drawdown mandate and cannot certify generated lineups for
upload. A successful review run exits 0 with `FILE_VALID=true`,
`MODEL_STATUS=PRIOR_ONLY`, and `RELEASE_DECISION=DO_NOT_UPLOAD`.

For outdoor weather, capture the relevant NWS gridpoint forecast through
`sources.fetch_public_artifact`, retain the original response and hash, and
populate the request's `weather_state`, `weather_source_uri`, and
`weather_observed_at` from that capture. NWS was reachable during the September
9 Windows rehearsal; availability must be checked in the actual Cowork session.
Use the forecast's `generatedAt`, never the time you typed the request. The
six-hour weather expiry survives freezing, projection, selection and export.

Rerun using the generated request with the completed weather fields. If the
command stops for identity decisions, resolve only the named ambiguities from
verifiable identity evidence. Current `official_status_csv` rows are used to
exclude INACTIVE people across both Captain and Flex before selection; missing
status rows do not imply ACTIVE. Refresh near kickoff. Never set `--as-of` to
an earlier time for a live run: that flag is historical replay only.

Offensive history is now explicit. Rebuild older frozen prior packages that
lack SD2 coverage. A missing historical basis, incompatible transfer or material
role change blocks selection with one named finding per person. Capture approved
evidence through `sources.fetch_public_artifact`, prepare the narrow
`nfl_offensive_role_evidence_v1` package in `docs/DATA_CONTRACTS.md`, and set
`offensive_role_evidence_json` in the generated request. Keep the manifest beside
its content-addressed `sources/` directory, inside the managed run folder. Rerun
the generated request after resolving the named evidence action. Do not ask Ben
to type numerical priors. If the approved source does not explicitly supply the
required numbers, retain the blocker; qualitative starter/backup prose is not
an opportunity forecast. Compatible live numerical captures remain unverified.

Without a supported replacement, excluded players' volume remains unallocated;
unchanged positive historical shares are visibly unconfirmed diagnostics.
Observed-zero players are excluded without claiming inactivity. Review
`prior_review_reports.selection.prior_scores.offensive_roles`, or
`prior_review_reports.offensive_roles` for a selection failure. These include
before/after shares, history coverage, assumptions, source hashes, expiry and
the next evidence action. The same optional CLI input is
`--offensive-role-evidence-json '<path-to-offensive_roles.json>'`.
The main operating workflow remains two attached CSV files.

Kicker roles are resolved after those exclusions. When one eligible kicker is
listed for a team and no role artifact is supplied, the review may continue only
with a visible prior-only sole-listed assumption; it does not prove a confirmed
role or ACTIVE status. When two or more remain, the run stops with
`KICKER_ROLE_UNRESOLVED`. Use an approved adapter from `sources.py` to capture
the supporting bytes, keep the content-addressed capture under `sources/`, and
prepare `nfl_kicker_role_evidence_v1` as documented in `DATA_CONTRACTS.md`.
Qualitative evidence may establish a sole kicker; only a source that explicitly
publishes a numerical allocation may support a split. Never divide evenly, use
salary as a depth chart, or use zero offensive snap share as inactivity.

The resulting report names the reviewed assignments and `DK_REVIEW_ENTRY` file.
Show its limitations alongside the lineups. `DK_REVIEW_ENTRY` is a retained
diagnostic artifact, not a certified upload package. A separately supplied
manual lineup can follow the manual guardrail route, subject to all its gates;
generated prior lineups cannot be relabeled as manual to bypass validation.

The older diagnostic/certification procedure below still applies to that
explicitly selected path and to Classic. Use `preflight`, rather than historical
`audit`, immediately before any certified manual upload.

This is Claude's operating procedure for the two-file NFL DFS workflow. The
operator's intended interaction is: attach a DraftKings salary CSV and
reserved-entry CSV, ask Claude to run the slate, review the result, and upload
manually only after `RELEASE_DECISION=CERTIFIED_UPLOAD_PACKAGE`. The legacy
`CERTIFIED` status is derived from that decision for compatibility.

## What the two DraftKings files establish

The salary CSV establishes the slate, mode, player IDs, salaries, eligibility,
teams, games, and lock times. The entry CSV establishes the exact contest IDs,
names, fees, roster geometry, reserved Entry IDs, and which roster cells are
authorized to change.

They do not establish the complete payout table, field size, ticket face value,
current official activity evidence, or validated opportunity/model inputs.
Those facts must come from separately frozen evidence. Their absence is a
normal `DO_NOT_UPLOAD` result, not permission to infer them.

## Cowork prerequisites

- Start the task from Claude Desktop with this repository selected as the local
  folder and with write access that does not permit deletion when that option is
  available.
- Keep Claude Desktop open while the task needs local files.
- Use the repository's Linux runtime through `nfl.sh`. Never attempt to execute
  `.venv\Scripts\python.exe` from Cowork's Linux environment. The launcher uses
  `.cowork-venv` and `.cowork-uv-cache`, leaving the Windows environment intact.
- Run `sh ./nfl.sh setup` only when the project environment is missing. Setup is
  pinned by `.python-version`, `pyproject.toml`, and `uv.lock`.

## First pass: discover, freeze, and reconcile

When both attachments are in one directory:

```sh
sh ./nfl.sh cowork-run \
  --input-dir '/full/path/to/attachments' \
  --label '2026-W02-MAIN'
```

When they are in different locations:

```sh
sh ./nfl.sh cowork-run \
  --salaries '/full/path/to/salary.csv' \
  --entries '/full/path/to/entries.csv' \
  --label '2026-W02-MAIN'
```

The command examines the first-row schema rather than the filenames. It rejects
multiple files of the same recognized type instead of guessing. Unrecognized
CSV files are reported and ignored. It then:

1. Parses and reconciles Classic or Showdown geometry.
2. Hashes and snapshots every recognized supplied artifact under the new run.
3. Writes `intake.json` and an editable `run_request.json`.
4. Runs the local environment checks.
5. Creates a versioned review workbook and `cowork_run.json`.
6. Leaves no upload-shaped CSV when required evidence is missing.

An exit code of 2 means `DO_NOT_UPLOAD`; it is the expected result for a
two-file-only first pass.

## Complete the run request

The generated request uses schema `nfl_cowork_run_request_v1`. Paths written by
the first pass point to immutable snapshots, so later reruns do not depend on
the original attachment location.

```json
{
  "schema_version": "nfl_cowork_run_request_v1",
  "label": "2026-W02-MAIN",
  "input_dir": null,
  "salary_csv": "<immutable snapshot path>",
  "entry_csv": "<immutable snapshot path>",
  "payout_csv": null,
  "assignment_csv": null,
  "team_projection_csv": null,
  "player_opportunity_csv": null,
  "official_status_csv": null,
  "role_evidence_json": null,
  "offensive_role_evidence_json": null,
  "ownership_brackets_csv": null,
  "source_ledger_json": null,
  "advertised_prize_value": null,
  "ticket_face_value": null,
  "field_size": null,
  "objective": "LARGE_GPP",
  "manual_guardrail": true,
  "profile": "diagnostic"
}
```

Populate only source-backed values:

- `payout_csv`: complete contiguous tiers using the contract in
  `docs/DATA_CONTRACTS.md`.
- `advertised_prize_value`: exact advertised cash plus ticket face value.
- `ticket_face_value`: required for a satellite.
- `field_size`: exact total contest entries; required for manual and
  model-assisted certification.
- `objective`: `LARGE_GPP`, `SMALL_GPP`, `CASH`, `WTA`, or `SATELLITE`.
- `team_projection_csv` and `player_opportunity_csv`: both are required for a
  model-assisted build. They must be produced by validated deterministic
  transformations of frozen evidence, never by freehand LLM estimates.
- `ownership_brackets_csv`: optional uncertainty brackets, explicitly treated
  as cold-start priors until calibrated.
- `source_ledger_json`: required for a Cowork model-assisted build. It must use
  schema `nfl_source_ledger_v1`; unknown fields, unapproved source URIs,
  invalid timestamps/license decisions/parser versions, missing or tampered
  artifacts, and missing or mismatched hashes for either model-input CSV fail
  certification closed.
- `official_status_csv`: current, source-bound, exact-ID activity evidence.
- `role_evidence_json`: optional source-bound Showdown kicker-role package. Add
  it to the generated request when a team has multiple eligible kickers, then
  rerun the request. Its salary/game/ID bindings, source bytes, hashes, times,
  expiry, and allocation must all validate; an invalid supplied package blocks.
- `assignment_csv`: optional manual lineup path. When present, the workflow
  validates/certifies it instead of running the model-assisted build.
- `profile`: `diagnostic` uses the bounded Cowork scenario/candidate sizes;
  `registered` requests the larger registered banks and may take materially
  longer. Neither setting changes evidence gates.

Unknown request keys, missing files, invalid enum values, partial team/player
model pairs, traversal, external absolute paths, and symlink/reparse escapes
fail closed. Request paths are limited to the explicitly supplied attachment
directory, managed project data, and that run's immutable directory.

For a prepared role package on the command line, the equivalent rerun is:

```sh
sh ./nfl.sh cowork-run \
  --request '<full-path-to-run_request.json>' \
  --role-evidence-json '<full-path-to-kicker-role-package/kicker_roles.json>'
```

Cowork snapshots both the manifest and its adjacent `sources/` captures before
selection. Review `prior_review_reports.selection.prior_scores.kicker_roles` for
the team allocation, sole-listed assumptions, zero-share exclusions, coverage
gaps, source hashes and expiry. A source-bound role does not change
`MODEL_STATUS=PRIOR_ONLY` or `RELEASE_DECISION=DO_NOT_UPLOAD`.

## Produce prior-only model inputs

When approved team/player prior artifacts and a human-reviewed exact identity
map have been frozen, run the local deterministic producer. Every hash argument
is required and must be obtained independently from the frozen input bytes:

```sh
sh ./nfl.sh project \
  --salaries '/full/path/to/frozen-salaries.csv' \
  --salary-sha256 '<64-lowercase-hex>' \
  --team-source '/full/path/to/frozen-team-source.json' \
  --team-source-sha256 '<64-lowercase-hex>' \
  --player-source '/full/path/to/frozen-player-source.json' \
  --player-source-sha256 '<64-lowercase-hex>' \
  --identity-map '/full/path/to/frozen-identity-map.json' \
  --identity-map-sha256 '<64-lowercase-hex>' \
  --as-of '2026-09-09T12:00:00-05:00' \
  --output-dir '/full/path/to/new-projection-package'
```

The destination must not exist. Success atomically publishes exactly
`team_projections.csv`, `player_opportunities.csv`, and `source_ledger.json`.
Use those paths in `run_request.json`. Missing, changed, expired, future,
conflicted, non-PASS, unapproved, incomplete, non-exact, or role-conflicted
inputs fail with a named error and no partial package. The command performs no
download and never reads DraftKings APPG numerically.

A successful projection package still reports `MODEL_STATUS=PRIOR_ONLY` and
`RELEASE_DECISION=DO_NOT_UPLOAD`. It supplies deterministic inputs to the
existing build; it does not establish calibration, EV, profitability, or upload
readiness.

## Research and evidence rules

Claude should gather permitted public evidence autonomously, but this does not
authorize improvising missing data.

- Use the allowlisted adapters in `src/nfl_dfs/sources.py` for automated
  downloads. Never work around a prohibited or unapproved host.
- Keep the original bytes and a source ledger with URL, capture/observation
  time, hash, parser version, coverage, and license decision.
- Use DraftKings IDs from the current salary snapshot. Exact name/team evidence
  may support a human-reviewable identity proposal; fuzzy matching cannot enter
  certification.
- Do not use DraftKings `AvgPointsPerGame` downstream.
- Payouts and field size are contest-specific and normally require a screenshot
  or paste from the operator. Ask once for the smallest missing set of facts.
- Do not use browser control to log in to, navigate, or extract data from
  DraftKings.

## Rerun and finish

After updating the request:

```sh
sh ./nfl.sh cowork-run --request '/full/path/to/run_request.json'
```

If the request supplies a manual assignment, the workflow validates it and
attempts certification. If it supplies both model-input files plus contest
economics, it builds diagnostic or registered candidate/scenario banks,
selects exact Entry-ID assignments, runs quantitative and REFEREE QA, and then
attempts certification. One run supports exactly one Contest ID and one entry
fee; split a multi-contest DraftKings export into separate immutable runs.

## Governed late swap

Late swap is a separate immutable release decision built on a prior `CERTIFIED`
package. In Cowork, use the same shared launcher and logic as the Windows
fallback:

```sh
sh ./nfl.sh late-swap \
  --run-id '2026-W02-LATE-1' \
  --salaries '/full/path/to/frozen-salaries.csv' \
  --current-entries '/full/path/to/current-prefilled-bulk-edit.csv' \
  --prior-manifest '/full/path/to/prior-certified.manifest.json' \
  --prior-assignments '/full/path/to/prior-assignments.csv' \
  --proposed-assignments '/full/path/to/proposed-assignments.csv' \
  --eligibility-evidence '/full/path/to/late-swap-eligibility.json' \
  --inactive-reports '/full/path/to/team-inactive-reports.json' \
  --output-dir '/full/path/to/outputs' \
  --as-of '2026-09-13T15:00:00-04:00'
```

The prior manifest must be `CERTIFIED`, its referenced output must still exist
and match its hash, and its salary, assignment, original-template, and evidence
bindings must reconcile. The current DraftKings bulk-edit template must be
fully prefilled and cover exactly the same Entry IDs. Replaceable cells are
computed from exact player IDs and lock times; neither the request nor an
operator-provided unlocked flag can authorize a cell.

The eligibility and team-report JSON contracts are defined in
`docs/DATA_CONTRACTS.md`. Missing or non-`PASS` contest eligibility, inactive
evidence that is `UNKNOWN`, `STALE`, `CONFLICTED`, or `NOT_YET_DUE`, a selected
inactive player, any locked-player change, an input hash change, or a byte-audit
failure produces exit code 2, a versioned `DO_NOT_UPLOAD` manifest, and no
upload-shaped CSV. Stop there; fix the first named blocker and use a new run ID.

A passing late-swap run contains:

- `late_swap_<run_id>.manifest.json`: prior-state, evidence, allowed-cell,
  input, and final-byte hashes.
- `DK_UPLOAD_<run_id>.csv`: present only after lock, legality, evidence,
  independent byte audit, reparse, and post-write hash gates pass.

The status covers authorization, evidence, legality, and exact bytes. It is not
an EV, ROI, profitability, or live-slate validation claim. DraftKings login,
editing, and upload remain manual.

The result folder contains, as applicable:

- `cowork_run.json`: top-level status and artifact index.
- `build_<run_id>.json`: diagnostic build, solver proof, quantitative QA, and
  binding REFEREE report. Its assignment hash, exact build-input hashes, and
  contest parameters are checked during model-assisted certification.
- `assignments_<run_id>.csv`: generated exact-ID assignments.
- `NFL_DFS_Review_*.xlsx`: versioned human review workbook.
- `DK_UPLOAD_<run_id>.manifest.json`: certification record.
- `DK_UPLOAD_<run_id>.csv`: present only when every hard gate passes.

Always report:

1. `FILE_VALID`, `EVIDENCE_STATE`, `MODEL_STATUS`, and `RELEASE_DECISION`, plus
   the derived compatibility status (`CERTIFIED` or `DO_NOT_UPLOAD`).
2. The exact blocker list.
3. Review workbook and manifest paths.
4. Output SHA-256 when an upload CSV exists.
5. One next operator action.

The operator manually reviews Entry IDs and lineups and performs any DraftKings
upload. A generated file is never permission to upload by itself.

## Linux/Cowork runtime, measured 2026-09-08

A Cowork session mounts this repository through a bridge that refuses file
deletion. `unlink` and `rmdir` return `EPERM`, which breaks three things that
look unrelated: `uv` cannot extract a managed interpreter, SQLite cannot open a
database in `WAL` or `DELETE` mode (`disk I/O error`, because `DELETE` journaling
deletes the journal on commit), and `tempfile.TemporaryDirectory` recurses until
`RecursionError` because its cleanup handler retries `rmtree` on every
`PermissionError`.

`nfl.sh` therefore honours three overrides, all defaulting to the previous
in-repository paths so Windows behaviour is unchanged:

```sh
export NFL_DFS_VENV_DIR=/tmp/nfl-cowork-venv
export NFL_DFS_UV_CACHE_DIR=/tmp/nfl-uv-cache
export NFL_DFS_UV_PYTHON_DIR=/tmp/nfl-uv-python
sh ./nfl.sh setup
```

With the runtime on local disk, `uv sync` completes in about 17 seconds instead
of exceeding a 178-second shell limit unfinished.

Two further constraints follow from the same cause. `.pytest_cache` in the
mounted repository is unreadable, so the suite needs
`--ignore=.pytest_cache tests`. And running the suite in place leaves temporary
directories behind that the session cannot remove, so execute it from a
local-disk working copy of `src`, `tests`, `templates`, `config`,
`pyproject.toml` and `uv.lock`, keeping the mounted repository as the source of
truth for edits.

`nfl.sh doctor` against the mounted repository reports `pass_status: false` with
`sqlite_probe_error`, which is correct rather than a defect: `cowork-run` gates
on `pass_status` and `registry.py` opens a real database under `data/registry/`.
Either grant the session delete permission on the folder, or run from a
local-disk working copy.
