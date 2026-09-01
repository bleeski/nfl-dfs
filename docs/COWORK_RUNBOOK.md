# Claude Cowork Runbook

This is Claude's operating procedure for the two-file NFL DFS workflow. The
operator's intended interaction is: attach a DraftKings salary CSV and
reserved-entry CSV, ask Claude to run the slate, review the result, and upload
manually only after `CERTIFIED`.

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
- `field_size`: exact total contest entries.
- `objective`: `LARGE_GPP`, `SMALL_GPP`, `CASH`, `WTA`, or `SATELLITE`.
- `team_projection_csv` and `player_opportunity_csv`: both are required for a
  model-assisted build. They must be produced by validated deterministic
  transformations of frozen evidence, never by freehand LLM estimates.
- `ownership_brackets_csv`: optional uncertainty brackets, explicitly treated
  as cold-start priors until calibrated.
- `source_ledger_json`: required for a Cowork model-assisted build. Its SHA-256
  is bound into the certification manifest with both model-input files. Binding
  proves which ledger was used; Claude must still validate and report the
  ledger's sources, timestamps, coverage, transformations, and limitations.
- `official_status_csv`: current, source-bound, exact-ID activity evidence.
- `assignment_csv`: optional manual lineup path. When present, the workflow
  validates/certifies it instead of running the model-assisted build.
- `profile`: `diagnostic` uses the bounded Cowork scenario/candidate sizes;
  `registered` requests the larger registered banks and may take materially
  longer. Neither setting changes evidence gates.

Unknown request keys, missing files, invalid enum values, and partial
team/player model pairs fail closed.

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
selects exact Entry-ID assignments, runs REFEREE QA, and then attempts
certification.

The result folder contains, as applicable:

- `cowork_run.json`: top-level status and artifact index.
- `build_<run_id>.json`: diagnostic build and REFEREE report.
- `assignments_<run_id>.csv`: generated exact-ID assignments.
- `NFL_DFS_Review_*.xlsx`: versioned human review workbook.
- `DK_UPLOAD_<run_id>.manifest.json`: certification record.
- `DK_UPLOAD_<run_id>.csv`: present only when every hard gate passes.

Always report:

1. `CERTIFIED` or `DO_NOT_UPLOAD`.
2. The exact blocker list.
3. Review workbook and manifest paths.
4. Output SHA-256 when an upload CSV exists.
5. One next operator action.

The operator manually reviews Entry IDs and lineups and performs any DraftKings
upload. A generated file is never permission to upload by itself.
