# Slate Runbook

Operating a slate in Claude Code, on the Windows desktop app or in a cloud
session. `docs/OPERATOR_GUIDE.md` is the manual command reference;
`docs/START_HERE.md` is the orientation page.

Three names in here still say "cowork": the subcommand alias `cowork-run`, the
artifacts `cowork_run.json` and `NFL_DFS_Cowork_Review_<run-id>.xlsx`, and the
request schema `nfl_cowork_run_request_v1`. They are bytes on disk and a wire
format that `cowork.py` validates, not labels. `run-slate` is the name to use.

## Classic C3 governed prior review: current operating path (2026-09-11)

The same normal two-CSV command now accepts a multi-game DraftKings NFL Classic
salary file and matching blank reserved-entry file:

```sh
sh ./nfl.sh run-slate --input-dir '<input-directory>' --profile prior_review --build-priors --label '<slate-label>'
```

Classic C1 validates and binds the exact salary and entry bytes, draft group,
complete game/team/opponent/lock set, contest and Entry IDs, and blank-cell
authority. It builds or reuses the shared frozen prior package, produces the
shared deterministic projection package, applies full-slate participation,
official activity, current role, weather and expiry gates. With no policy, the
byte-compatible C1 sequential selection remains in place. To invoke governed
C2 joint selection, supply the exact-input C2 policy on the command line or in
the generated request:

```sh
sh ./nfl.sh run-slate \
  --request '<full-path-to-run_request.json>' \
  --portfolio-policy-json '<full-path-to/classic_portfolio_policy.json>'
```

The policy must use `nfl_classic_portfolio_policy_c2_v1` and bind the current
salary and entry hashes, complete identity, registered objective/seed, direct
integer bounds, and exact ordered Entry IDs. C2 snapshots and canonically
normalizes it, generates a deterministic bounded legal candidate bank, jointly
selects one unique lineup per Entry ID without cycling, and independently
reparses and audits the canonical artifacts. It never calls the field,
ownership, duplication, payout/economics, or production portfolio selector.

C2 success writes canonical `classic_candidate_bank.json`,
`classic_assignment.json`, and `classic_portfolio_audit.json`, then extends
`classic_selection.json` and `classic_complete_slate_coverage.json` with their
hashes, policy facts, actual-bank solve status and independent audit. Canonical
hashes reproduce across new run IDs from identical immutable inputs. These are
review JSON, not DraftKings templates: C2 writes no `assignments.csv`, HTML,
readable review workbook, `DK_REVIEW_ENTRY_*.csv`, or `DK_UPLOAD_*.csv`.
`FILE_VALID=true` describes the bound machine-readable JSON only.
`EVIDENCE_STATE` is separately derived; `MODEL_STATUS=PRIOR_ONLY` and
`RELEASE_DECISION=DO_NOT_UPLOAD` are invariant.

C3 then independently reparses every canonical input and C2 output, recomputes
the complete ordered portfolio and every hard count/overlap/evidence fact, and
only after audit `PASS` writes `DK_REVIEW_ENTRY_<label>.csv`, canonical readable
JSON, self-contained escaped HTML, and the eight-sheet review workbook. The
review CSV is an exact template copy with only the nine previously blank roster
cells for each authorized Entry ID changed; all non-roster bytes and physical
line geometry remain exact. It is a review artifact, never an upload package.

Since Session 09 (R28) Classic treats missing official activity as Showdown
does: a selected person with no exact-ID row publishes with the gap named
(`OFFICIAL_STATUS_INCOMPLETE_FOR_SELECTED`, or `OFFICIAL_STATUS_REQUIRED` when
no file was supplied; `P`, stops certification) and `EVIDENCE_STATE=UNKNOWN`.
C3's audit reports `selected_activity` as `INCOMPLETE` with the people, never
`PASS`. An `INACTIVE` row still takes the person out before selection, and an
invalid, empty, stale, future or changed file still stops the run. Uncertainty
for nonselected people remains visible in complete-slate coverage.

Current offensive roles follow the Showdown rule since 2026-09-12 (R21, Ben's
ruling extending R17 to Classic). The role resolver decides: an unresolved or
declared-changed role blocks before selection, a person with no prior-season row
is excluded with zero share, and a history-derived prior selects. Every selected
person resting on one is named in `selected_evidence_gate.unverified_role_people`
and in the review's `SELECTED_CURRENT_OFFENSIVE_ROLE` observation, which reports
state `UNKNOWN` in that case. A `nfl_classic_offensive_role_evidence_c1_v1`
package is still the only thing that makes a role a current fact; supply one for
a role you actually doubt, and note that any person the gate recorded as
source-supported must still be covered by that package when C3 re-audits.

A multi-game weather capture uses `--weather-evidence-json`; its
`nfl_classic_weather_evidence_c1_v1` payload binds `salary_sha256` and maps the
exact complete game set to `weather_state`, approved `source_uri`, and
timezone-aware `observed_at`, plus the relative content-addressed capture path,
SHA-256, license/parser decision, capture time and expiry. Build it with
`scripts/make_classic_weather_evidence.py` rather than by hand:

```sh
python scripts/make_classic_weather_evidence.py \
  --salaries <run>/inputs/DKSalaries.csv \
  --plan <run>/weather/plan.json \
  --out-dir <run>/weather
```

The plan is one entry per game keyed by home team abbreviation (or exact
`game_id`), each naming the `api.weather.gov` gridpoint forecast URI and the
saved response. Three facts that cost time otherwise: the engine's `game_id` is
the `AWAY@HOME` matchup alone and not the whole `Game Info` cell; the package
must cover every game including the domes the schedule already resolves (R22);
and `observed_at` must be the forecast's own `generatedAt`, which the script
reads for you. The capture expires six hours after capture, so take them close
to the slate. Scalar weather flags remain the single-game Showdown interface.

Official activity on a Classic slate: `scripts/make_official_status.py` accepts
`--whole-pool` for a first pass with no selection yet, and `--selection
<classic_selection.json>` once a run has produced one, because Classic C1/C2
write no assignment CSV. Its slate-lock warning uses the earliest kickoff on the
slate. Inactives publish about ninety minutes before each kickoff and the
observation window is the three hours ending at the earliest kickoff, so the
final Classic pass is a narrow window on Sunday morning.

Build the C2 policy with `scripts/make_classic_policy.py` rather than by hand.
The registered template's defaults are the worst configuration the engine
supports: all four stack rules ship `ADVISORY` with `minimum_entries: 0`, which
the solver does not enforce, and the bank defaults to `max(32, entries + 24)`.
Measured on the supplied 719-person fixture, 811 of 1000 generated candidates
were `NAKED_QB`.

```sh
python scripts/make_classic_policy.py \
  --salaries <run>/inputs/DKSalaries.csv \
  --entries  <run>/inputs/DKEntries.csv \
  --out      <run>/policy/classic_portfolio_policy.json \
  --rung 0 --minutes 5
```

Rung 0 puts `QB_PASS_CATCHER` at `HARD` on every entry and `QB_BRINGBACK` at
`HARD` on 70% of them, caps pairwise person overlap at 5 of 9 and player exposure
at half the entries, and sizes the bank from the minutes you are willing to
spend. Measured at 20 entries on the fixture: a 1000-candidate bank in 273.6s,
the joint MILP in 0.39s, `OPTIMAL_ACTUAL_CANDIDATE_BANK` with all 20 entries
selected, and the selected portfolio carried `qb-pass-catcher` on 20 of 20 and
`qb-bringback` on 14 of 20 with zero naked-QB lineups.

Since Session 07b the bank also fits the lock clock. The generator reads this
host's measured seconds per candidate from `data/runs/host_candidate_rates.json`
(`--host-rates`; `run-slate` writes it after every C2 bank; 0.28 s when there is
none) and the delivery deadline (`--delivery-deadline-utc`, default the earliest
lock minus 5 minutes), and keeps the declared bank and joint solve within 75% of
the window before the improvement stops. When even the floor bank does not fit
it writes nothing, exits 2 and names rung 4; when the window has closed it says
the baseline is the file. For a replay of a past slate, pass a later
`--delivery-deadline-utc`.

If a run reports `MODELED_BANK_INFEASIBILITY`, `INCOMPLETE_BANK_EXHAUSTION`,
`CANDIDATE_BANK_TIMEOUT` or `CANDIDATE_BANK_SEARCH_LIMIT`, regenerate one rung
lower and rerun immediately. Since Session 08 the last two mean the bank
stopped at a limit without the entry count or a policy-feasible witness; a bank
that stopped with both reports `BOUNDED_TIME_LIMIT_STOP` or
`BOUNDED_SEARCH_LIMIT_STOP`, delivers, and names `CANDIDATE_BANK_STOPPED_AT_LIMIT`,
which is not a reason to drop a rung. Do not stop to ask; see "Shipping under a lock
clock", summarized in `CLAUDE.md` and reproduced in full at the end of this runbook. Rung 4 emits no policy and runs C1 sequential selection.
It is the last structural rung, not a guaranteed file: C1 writes review JSON
only (`prior_review.py:3016`) and raises when distinct lineups run out
(`selection.py:538-542`). When it hands you no file, the Classic fallback path
below does.

C2 reports the bank as exhaustive or bounded and names timeout, search-limit,
solver-error, structural-infeasibility, modeled-bank-infeasibility, and
incomplete-bank-exhaustion states separately. Accept
`OPTIMAL_ACTUAL_CANDIDATE_BANK` (optimal over the reported bank only) or, since
Session 08, `FEASIBLE_LIMIT_ACTUAL_CANDIDATE_BANK` (a time or search limit
stopped the joint solve holding a validated incumbent: legal under every bound,
not proven optimal, named `PORTFOLIO_SELECTION_LIMIT_INCUMBENT`), each with
independent audit `PASS`. Before accepting the display, require
`classic_review_export_audit.json` status `PASS`,
`DISPLAY_RECONCILIATION=PASS`, the exact review CSV SHA-256, and all four
release truths. Start with the workbook or HTML; inspect every exact Entry ID,
limit, overlap, evidence observation, prominent bounded-bank limitation and
provenance hash. `FILE_VALID=true` never changes
`MODEL_STATUS=PRIOR_ONLY` or `RELEASE_DECISION=DO_NOT_UPLOAD`.

The C3 code, copied-package replay, exact-byte diff, rendering, mutation matrix,
and registered full-fixture 1/3/20/150 acceptance have passed on Windows. Under
R30 (Ben, 2026-09-22) C3 is complete for software acceptance. Native Excel
open/recalculate/save/reopen acceptance is deferred to Session 35 of
`docs/ROADMAP.md`, and nothing waits on it.

## Continuity: getting the repo into a session (2026-09-17)

GitHub is the only route now, and it is the whole answer. The device bridge,
`git bundle` handoffs and patch-back-through-chat are all retired along with
Cowork; this section replaces the 2026-09-12 ordering entirely.

**Every surface clones the same repository.**

- Windows desktop app: the local checkout, `.\nfl.ps1`, `.venv`.
- Cloud session, including from a phone: a fresh clone, `sh ./nfl.sh`,
  `.venv-linux`. First command is `sh ./nfl.sh setup`.

**Push before you rely on a clone.** A cloud session sees committed work and
nothing else. Uncommitted work on the Windows box is invisible to it. Claude now
commits and pushes on its own authority to a `claude/*` branch and merges to
`main` once CI is green, so the gap between the working tree and `origin` should
be short-lived by default; see `.claude/rules/git-authority.md`. Never
`git add .` or `-A`; stage an explicit path list.

**What a clone does not carry.** `.gitignore` excludes `data/runs`,
`data/registry`, `data/models`, `data/standings/inbox`, `data/standings/normalized`,
`outputs` and `operator_input.xlsx`. A cloud session therefore starts with the
engine, the docs and the ledgers, and with none of the bytes any previous run
produced. Three consequences worth knowing before you plan work in one:

- `scripts/standings_checklist.py` scans `data/runs/*/inputs/` and loose root
  CSVs. In a fresh clone both are empty, so it returns an empty checklist rather
  than an error. That is not a finding about the corpus.
- `data/registry/` is a real SQLite database and does not travel. A cloud
  session starts with a blank registry.
- `late-swap --prior-manifest` and `settle --replay` need artifacts from an
  earlier run. Neither is possible in a fresh clone.

Derived records under `records/` are tracked on purpose, so grading and
calibration do work from a clone. Raw standings exports never are: one is 167 MB
and they carry other DraftKings users' names and lineups.

**Container facts, measured 2026-09-17.** `uv sync --all-groups --locked
--python 3.13.7` completes. `sh ./nfl.sh doctor` returns `pass_status: true`
with an empty `sqlite_probe_error`; the 2026-09-08 bridge-mount failures below
do not reproduce. Full suite `1 failed, 735 passed, 1 skipped in 155.56s`, the
one failure being the hardcoded-expiry test in `tests/test_w6_live_preflight.py`,
fixed later that day by pinning its clock (changelog, 2026-09-17 CI unblock).


## Showdown generation: current operating path (2026-09-09)

For the normal request to generate a Showdown portfolio from the two attached
CSV files, run:

```sh
sh ./nfl.sh run-slate --input-dir '<input-directory>' --profile prior_review --build-priors --label '<slate-label>'
```

This generates prior-only review lineups. It does not implement the full
ceiling/ownership/drawdown mandate and cannot certify generated lineups for
upload. A successful review run exits 0 with `FILE_VALID=true`,
`MODEL_STATUS=PRIOR_ONLY`, and `RELEASE_DECISION=DO_NOT_UPLOAD`.

The success package contains `prior_only_readable_review.json`, a self-contained
`prior_only_readable_review.html`, and
`NFL_DFS_Cowork_Review_<run-id>.xlsx`. Open the workbook or HTML first. Confirm
the exact Entry IDs and CPT/FLEX roster IDs, salary totals/remaining salary,
combined-person and Captain exposure, policy maxima, overlap, role/activity
concerns, evidence expiry, provenance hashes and the one next action. The
workbook's `Upload` sheet must show all four release truths and
`DISPLAY_RECONCILIATION=PASS`. That pass means the display agrees with exact
artifacts; it never changes `DO_NOT_UPLOAD`. The input workbook contract remains
five sheets, while this successful output copy has eight sheets: Run Control,
Evidence Paste, Portfolio, QA, Upload, Exposure, Review Evidence and Artifacts.

For outdoor weather, capture the relevant NWS gridpoint forecast through
`sources.fetch_public_artifact`, retain the original response and hash, and
populate the request's `weather_state`, `weather_source_uri`, and
`weather_observed_at` from that capture. NWS was reachable during the September
9 Windows rehearsal; availability must be checked in the actual session.
Use the forecast's `generatedAt`, never the time you typed the request. The
six-hour weather expiry survives freezing, projection, selection and export.

Rerun using the generated request with the completed weather fields. If the
command stops for identity decisions, resolve only the named ambiguities from
verifiable identity evidence.

Rerun semantics, fixed 2026-09-10 and pinned by
`tests/test_cowork_rerun_regressions.py`:

- `--request <run_request.json> --input-dir <fresh uploads>` uses the fresh
  files and reports them under `superseded_request_inputs`. Without
  `--input-dir`, the request's immutable snapshots are used. This is the
  re-run after actives are announced: point `--input-dir` at the new salary CSV.
- `--exclude`, `--unavailable-status` and `--available-status` on a rerun are
  added to the saved request's lists, never substituted for them.
- `--official-status-csv <file>` supplies current exact-ID activity rows. Any
  selected person the file omits is named under
  `OFFICIAL_STATUS_INCOMPLETE_FOR_SELECTED`; a file never implies ACTIVE for
  people it does not list.
- `--lineup-count` below the reserved-entry count is refused at SELECT; above
  it, the surplus lineups stay in the selection report and fill no entry.
- A `--run-id` that already exists is refused (`RUN_ID_COLLISION`) before any
  file is written; omit it and the timestamped id is generated.
- An out-of-tree `--prior-package-dir` must be repeated on every `--request`
  rerun; the request's recorded copy is not trusted on its own. After a
  `--build-priors` run the generated request keeps `prior_package_dir: null`,
  so a plain `--request` rerun re-fetches nflverse. To reuse the frozen
  package, pass `--prior-package-dir <repo>/data/runs/<run_id>/prior_review/priors/frozen`.
  A package whose bound salary bytes no longer match the current upload is
  rebuilt automatically when `--build-priors` is also set.
- More reserved entries than selectable people no longer fails: the legacy
  path captains every selectable person once, then repeats captains and says
  so (`captain_repeats_from_index`). Read the pool-coverage section and the
  captain exposure before accepting a portfolio that large. For 4 or more
  entries, supply a `portfolio_policy_json` with the captain and exposure caps
  you want; since 2026-09-10 the stratified bank supports real caps (verified:
  20 entries, captain cap 0.25, combined cap 0.6 on the top two people,
  overlap 4, in about 8 seconds).
- Container fallback for nflverse fetch: if the device shell is down and the
  container's egress proxy fails Python's strict X.509 check, run with
  `NFL_DFS_TLS_ALLOW_NONSTRICT_CA=1`. Only the strictness flag is cleared;
  certificate and hostname verification stay on and every captured artifact
  records `tls_verify_x509_strict=false`. Approved 2026-09-10.

The readable review, workbook Exposure sheet and `selection_report.json` now
carry `pool_coverage`: every person's exclusion reason (DK status, official
INACTIVE, operator fade, role gate), the FLEX and CPT salary of each excluded
group, per-team position coverage, and the prior-season volume left
unallocated. The kicker slot shows the sole-listed assumption when no role
evidence was supplied. Current `official_status_csv` rows are used to
exclude INACTIVE people across both Captain and Flex before selection; missing
status rows do not imply ACTIVE. Refresh near kickoff. Never set `--as-of` to
an earlier time for a live run: that flag is historical replay only.

Offensive history is now explicit. Rebuild older frozen prior packages that
lack SD2 coverage (a package frozen before 2026-09-10 has no `transfer_prior`
and its transfers still block; rebuild with `--build-priors`). A transfer
carries his own prior-team share as an unverified cold-start prior and is
reported as `TRANSFER_PRIOR_UNVERIFIED`; a rookie or never-recorded person is
excluded with zero share and listed with salary in pool coverage; a declared
material role change blocks selection with one named finding per person. Capture approved
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

For Showdown, the workflow accepts a versioned `portfolio_policy_json` with
exact salary, game, full person/CPT/FLEX identity, and requested Entry-ID
bindings. That mode's contract uses explicit fractions in `[0,1]` and
exact-decimal floor rounding; see `docs/DATA_CONTRACTS.md`. SD4 enforces it on
the Showdown `prior_review`
profile through a bounded, policy-stratified candidate bank (`max(32, 4 x
entries)` candidates, seeded per captain and per capped person, then a
policy-feasible chain and top-K fill) and one joint MILP, assigns the
exact requested Entry IDs without cycling, and runs an independent audit that
reparses the normalized-policy and assignment artifacts immediately before
review export. Read the reported candidate-bank
coverage: `CANDIDATE_LIMIT_REACHED_INCOMPLETE` can support a feasible audited
review but is not a complete-slate search. If no portfolio is found in that
bank, the run reports incomplete-bank exhaustion rather than full-slate
infeasibility. A supplied policy on another profile is refused, not ignored.
Only `ENFORCED_AND_INDEPENDENTLY_AUDITED` may create a new `DK_REVIEW_ENTRY`
CSV, and it remains `PRIOR_ONLY / DO_NOT_UPLOAD`. Requests omitting the policy
continue through the existing SD1/SD2 behavior.

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

The resulting report names the reviewed assignments and `DK_REVIEW_ENTRY` file,
plus the readable JSON, HTML and workbook with their SHA-256 values. Show its
limitations alongside the lineups. `DK_REVIEW_ENTRY` is a retained diagnostic
artifact, not a certified upload package. If display reconciliation finds any
byte or semantic mismatch, the command stops at `READABLE_REVIEW`, returns exit
2 with a named discrepancy, preserves earlier artifacts, and withholds the
top-level review-export path; do not review or upload the failed display. A
separately supplied manual lineup can follow the manual guardrail route, subject
to all its gates; generated prior lineups cannot be relabeled as manual to
bypass validation.

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

## Prerequisites

- Work from a checkout of this repository, on either surface. Windows desktop
  app uses `.\nfl.ps1` and `.venv`; a cloud session uses `sh ./nfl.sh` and
  `.venv-linux`. Never mix the two in one session, and never try to execute
  `.venv\Scripts\python.exe` from Linux.
- Run `sh ./nfl.sh setup` (or `.\nfl.ps1 setup`) only when the environment is
  missing. Setup is pinned by `.python-version`, `pyproject.toml` and `uv.lock`.
- Confirm `doctor` returns `pass_status: true` before a slate run. The run path
  gates on it.
- Run `python3 scripts/session_probe.py --salaries '<salary CSV>'` first, before
  the run itself. `doctor` checks the environment; this checks whether the
  session can reach the hosts its evidence gates need, and reports the measured
  minutes to lock. Exit 2 means a full run cannot complete here. See step 0 of
  “When Ben says ‘run the slate’”.
- A cloud session needs the DraftKings files committed under
  `data/inbox/slates/<slate-id>/`; a desktop session can point at any local
  directory. Either way the two files are Ben's own downloads, and nothing in
  this repository ever fetches them.


## First pass: discover, freeze, and reconcile

When both attachments are in one directory:

```sh
sh ./nfl.sh run-slate \
  --input-dir '/full/path/to/attachments' \
  --label '2026-W02-MAIN'
```

When they are in different locations:

```sh
sh ./nfl.sh run-slate \
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
  "portfolio_policy_json": null,
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
- `source_ledger_json`: required for a model-assisted build. It must use
  schema `nfl_source_ledger_v1`; unknown fields, unapproved source URIs,
  invalid timestamps/license decisions/parser versions, missing or tampered
  artifacts, and missing or mismatched hashes for either model-input CSV fail
  certification closed.
- `official_status_csv`: current, source-bound, exact-ID activity evidence.
- `role_evidence_json`: optional source-bound Showdown kicker-role package. Add
  it to the generated request when a team has multiple eligible kickers, then
  rerun the request. Its salary/game/ID bindings, source bytes, hashes, times,
  expiry, and allocation must all validate; an invalid supplied package blocks.
- `portfolio_policy_json`: optional mode-specific exact-bound preference
  contract. Showdown uses the SD3 fractional source schema; C2 Classic uses
  direct integer lineup counts with exact entry-byte and full multi-game
  identity bindings. It is snapshotted, deterministically normalized, jointly
  enforced, and independently audited only by `prior_review`. A `valid=true`
  validation report alone is not enforcement; require the final
  `ENFORCED_AND_INDEPENDENTLY_AUDITED` status and audit `PASS`. Even then the
  artifact is prior-only review output, never a certified upload package.
- `assignment_csv`: optional manual lineup path. When present, the workflow
  validates/certifies it instead of running the model-assisted build.
- `profile`: `diagnostic` uses the bounded scenario/candidate sizes;
  `registered` requests the larger registered banks and may take materially
  longer. Neither setting changes evidence gates.

Unknown request keys, missing files, invalid enum values, partial team/player
model pairs, traversal, external absolute paths, and symlink/reparse escapes
fail closed. Request paths are limited to the explicitly supplied attachment
directory, managed project data, and that run's immutable directory.

For a prepared role package on the command line, the equivalent rerun is:

```sh
sh ./nfl.sh run-slate \
  --request '<full-path-to-run_request.json>' \
  --role-evidence-json '<full-path-to-kicker-role-package/kicker_roles.json>'
```

The run path snapshots both the manifest and its adjacent `sources/` captures before
selection. Review `prior_review_reports.selection.prior_scores.kicker_roles` for
the team allocation, sole-listed assumptions, zero-share exclusions, coverage
gaps, source hashes and expiry. A source-bound role does not change
`MODEL_STATUS=PRIOR_ONLY` or `RELEASE_DECISION=DO_NOT_UPLOAD`.

For policy-contract validation, use the generated request or the explicit CLI
field:

```sh
sh ./nfl.sh run-slate \
  --request '<full-path-to-run_request.json>' \
  --portfolio-policy-json '<full-path-to/portfolio_policy.json>'
```

With valid supporting inputs and a feasible, audited policy portfolio, the
expected exit is 0 with `FILE_VALID=true`, `MODEL_STATUS=PRIOR_ONLY` and
`RELEASE_DECISION=DO_NOT_UPLOAD`. Exit 0 means review generation completed, not
upload permission. A named policy, bank, solver, assignment, audit or mutation
failure exits 2, preserves earlier outputs, and creates no accepted Classic
portfolio or new Showdown review-entry CSV.

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
sh ./nfl.sh run-slate --request '/full/path/to/run_request.json'
```

If the request supplies a manual assignment, the workflow validates it and
attempts certification. If it supplies both model-input files plus contest
economics, it builds diagnostic or registered candidate/scenario banks,
selects exact Entry-ID assignments, runs quantitative and REFEREE QA, and then
attempts certification. One run supports exactly one Contest ID and one entry
fee; split a multi-contest DraftKings export into separate immutable runs.

## Governed late swap

Late swap is a separate immutable release decision built on a prior `CERTIFIED`
package. On Linux, use the same shared launcher and logic as the Windows
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
- `review/prior_only_readable_review.json` and `.html`: independently
  reconciled prior-review display data and escaped human rendering; present
  only after display reconciliation passes.
- `NFL_DFS_Cowork_Review_<run-id>.xlsx`: prior-review workbook. A successful
  copy has eight sheets and safe, wrapped display text.
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
3. Readable JSON/HTML/workbook and manifest paths, with their exact hashes and
   display-reconciliation status where present.
4. Output SHA-256 when an upload CSV exists.
5. One next operator action.

The operator manually reviews Entry IDs and lineups and performs any DraftKings
upload. A generated file is never permission to upload by itself.

## Linux runtime, measured 2026-09-17

Current measurements, from a Claude Code cloud container. These supersede the
2026-09-08 Cowork bridge-mount notes kept below them for history.

```sh
sh ./nfl.sh setup     # uv sync --all-groups --locked --python 3.13.7, completes
sh ./nfl.sh doctor    # pass_status: true, sqlite_probe_error empty, WAL ok
sh ./nfl.sh test      # 1 failed, 735 passed, 1 skipped in 155.56s
```

The one failure was the hardcoded-expiry test in `tests/test_w6_live_preflight.py`,
fixed later that day by pinning its clock.
Reachable from the container: `raw.githubusercontent.com`, nflverse GitHub
release downloads, and `api.weather.gov` (HTTP 200; an older note said otherwise
and was wrong).

`nfl.sh test` pins pytest's basetemp and cache directory under `TMPDIR`, the
same way `nfl.ps1` does, so a repository mounted on a filesystem that cannot
host them does not fail every test at fixture setup. Override with
`NFL_DFS_PYTEST_TMP` and `NFL_DFS_PYTEST_CACHE`.

### Historical: the 2026-09-08 Cowork bridge mount

Kept because the escape hatches it produced are still in the launcher and still
work. A Cowork session mounted the repository through a bridge that refused file
deletion: `unlink` and `rmdir` returned `EPERM`, which broke `uv` extracting a
managed interpreter, SQLite opening a database in `WAL` or `DELETE` mode, and
`tempfile.TemporaryDirectory` cleanup. `nfl.sh` honours three overrides for
exactly that case:

```sh
export NFL_DFS_VENV_DIR=/tmp/nfl-venv
export NFL_DFS_UV_CACHE_DIR=/tmp/nfl-uv-cache
export NFL_DFS_UV_PYTHON_DIR=/tmp/nfl-uv-python
sh ./nfl.sh setup
```

None of those symptoms reproduce in a Claude Code container.


## Moved from CLAUDE.md on 2026-09-15 (verbatim)

CLAUDE.md was restructured on 2026-09-15 so that it holds boundaries, release
truths and the development protocol only. The two operating sections below are
the exact text it carried until then, headings demoted one level, and remain in
force for every slate run. Rulings attributed to Ben keep their dates.

### When Ben says “run the slate”

0. **Establish what this session can do, before doing anything else.** Since
   2026-09-21 `run-slate` runs the probe itself at the head of every slate,
   writes it to `data/runs/<run_id>/session_probe.json` and prints the verdict to
   stderr, so the answer arrives whether or not anybody remembered to ask.
   `--no-session-probe` skips it; the suite skips it through
   `NFL_DFS_SKIP_SESSION_PROBE=1`, set in `tests/conftest.py`, because the probe
   is a network call. Run it by hand first anyway when the clock is short, because
   three seconds before the run beats finding out inside it:

   `python3 scripts/session_probe.py --salaries '<the salary CSV>'`

   It takes about three seconds, imports nothing from `nfl_dfs`, and answers the
   question nothing in this repository answered before 2026-09-20: can this
   session reach the hosts its gates need. It reads `ALLOWED_HOSTS` out of
   `src/nfl_dfs/sources.py` by parsing the source, so it cannot drift from the
   real allowlist; it separates an organization egress refusal from a TLS
   misconfiguration from a dead host; and with `--salaries` it reports the slate
   shape and the **measured** minutes to lock, taken from the earliest kickoff.

   Exit 0 means a full run can complete here. **Exit 2 means it cannot**, and
   the route has to be decided now rather than discovered at the gate ninety
   minutes later. On 2026-09-20 a thirteen-game Classic slate was lost that way:
   `api.weather.gov` was refused by the egress proxy, the block was found by
   walking into it, and most of the working window went with it.

   `src/nfl_dfs/preflight.py` is a different check and does not substitute: it
   is a pre-**upload** check on an already-built package.

   When exit 2 names a host you cannot reach, the capture does not have to
   happen in the session that builds. `scripts/fetch_weather_captures.py` is
   standard library only and runs anywhere the host is reachable; its output
   feeds `scripts/make_classic_weather_evidence.py` as normal. The probe now
   prints both commands when `api.weather.gov` is the blocked host, because on
   2026-09-20 that chain already existed and went unused on two lost slates.

   **Capture the weather before the session, not inside it.** This is the whole
   fix for a blocked `api.weather.gov`, and it is operator work on a machine that
   reaches the host (the Windows desktop). A capture expires six hours after it is
   taken, capped at lock, so the window for a 1pm ET slate opens at 7am ET. One
   pass, in that window:

       python3 scripts/fetch_weather_captures.py \
           --salaries '<the salary CSV>' --out-dir '<run>/weather'
       python3 scripts/make_classic_weather_evidence.py \
           --salaries '<the salary CSV>' --plan '<run>/weather/plan.json' \
           --out-dir '<run>/weather'

   The capture keeps the lock clock (Session 07b): requests stop 5 minutes
   before the delivery deadline (`--delivery-deadline-utc`, default the
   earliest `Game Info` lock minus 5 minutes), and with under 1 s left it
   exits `FETCH_DEADLINE_REACHED` without a request. A bare Windows Python
   has no IANA time zone data, so there it says so and keeps its fixed 30 s
   timeouts; pass `--delivery-deadline-utc` to bound it.

   Then hand `<run>/weather/weather_evidence.json` to `run-slate` as
   `--weather-evidence-json`. Both scripts are standard library only, so neither
   needs `setup` or the project venv on that machine. Neither invents a state: a
   retractable roof left open is written `REPLACE_ME` for a human to decide, and
   the count of games needing a decision is the script's own output.

   Since R26 the retractable venues (ARI, ATL, DAL, HOU, IND) no longer reach this
   step at all. Their blank `roof` cell resolves from the frozen artifact's own
   record of that venue; `docs/DATA_CONTRACTS.md` § The `roof` column is
   retrospective has the counts and the three bounds. On the 2026-09-20 afternoon
   slate that took the captures required from four of five games to two of five.

1. Locate the attached salary and reserved-entry CSVs. Do not depend on their
   filenames. If both are in one attachment directory, run:

   For prior-only Showdown or Classic review generation, use:

   `sh ./nfl.sh run-slate --input-dir '<input-directory>' --profile prior_review --build-priors --label '<short-label>'`

   This automatically runs the frozen prior, projection, and selection chain.
   It produces review lineups with `PRIOR_ONLY / DO_NOT_UPLOAD`.
   It does not implement calibrated ceiling, ownership leverage, or portfolio
   drawdown optimization. The default `diagnostic` profile is the older
   economics workflow and normally stops on missing contest inputs. For Classic,
   the no-policy C1 compatibility path writes canonical
   `classic_selection.json` and `classic_complete_slate_coverage.json`. A valid
   C2 Classic policy adds canonical candidate-bank, exact ordered assignment,
   and independent selection-audit JSON. C3 independently audits those exact
   bytes and can write a review-only `DK_REVIEW_ENTRY` CSV plus readable
   JSON/HTML/eight-sheet workbook. It never writes `DK_UPLOAD`, and remains
   `PRIOR_ONLY / DO_NOT_UPLOAD`. C3 native Excel save/reopen acceptance is
   deferred under R30 (Session 35); nothing waits on it.

   If they are in different locations, pass `--salaries` and `--entries`
   explicitly. On Windows, use `.\nfl.ps1 run-slate` with the
   same arguments.
2. If the project runtime is absent, run `sh ./nfl.sh setup`, then rerun. Do
   not use the Windows `.venv` from a Linux runtime. `nfl.sh` keeps its
   Linux environment isolated in `.venv-linux`.
3. Read the generated `cowork_run.json`, `run_request.json`, and review
   package. A successful Showdown `prior_review` run includes the readable
   workbook plus `prior_only_readable_review.json` and a self-contained
   `prior_only_readable_review.html`. Start with the workbook or HTML, but use
   the JSON and reported SHA-256 values to identify the exact reviewed bytes.
   `DISPLAY_RECONCILIATION=PASS` means the display was independently rebuilt
   from and reconciled to the exact salary, entry, assignment, policy, audit,
   selection, and review-export artifacts; it is not a release decision. The
   first pass always freezes and reconciles the supplied files. A successful
   Classic C3 starts with its canonical policy/bank/assignment/audit/selection/
   coverage JSON and adds the downstream audit, exact-template review CSV,
   canonical readable JSON, self-contained HTML, and the eight-sheet workbook.
   The review CSV is not an upload authorization.
4. Gather everything discoverable from approved public sources and freeze the
   artifacts. For an outdoor Showdown game, obtain the forecast through the
   approved `sources.fetch_public_artifact` adapter from `api.weather.gov`;
   retain its raw bytes and hash. Use its actual `generatedAt` observation time
   and game-period conditions to populate `weather_state`,
   `weather_source_uri`, and `weather_observed_at` in the request, then rerun.
   For multi-game Classic, use a hash-bound
   `nfl_classic_weather_evidence_c1_v1` JSON file through
   `weather_evidence_json`; it must bind the salary hash and contain exactly one
   source/state/observation record for every game, including the dome games the
   schedule already resolves. Build it with
   `scripts/make_classic_weather_evidence.py`, which derives the exact `game_id`
   set from the salary bytes, content-addresses each capture and reads each
   forecast's own `generatedAt`. The `game_id` is the `AWAY@HOME` matchup alone,
   not the whole `Game Info` cell.
   Do not claim NWS is universally unreachable: test the current session. The
   same rule binds for **every** source, not only NWS: probe it, never assert
   from memory that it is out of reach. On 2026-09-20 a session reported "I have
   no depth chart to check against" and built a quarterback filter out of
   prior-season workload instead. The nflverse depth chart was on `github.com`,
   already proven reachable by that same run's own prior build minutes earlier,
   and carried a snapshot from that morning naming three starters the filter had
   rejected. An unprobed absence is a guess.
   Weather capture expires after six hours. Use a fresh run before kickoff.
   `prior_review` already produces its model inputs; the manual fallback is
   `sh ./nfl.sh project` (or
   `./nfl.ps1 project` on Windows), supplying the exact expected SHA-256 for
   the salary, team-prior, player-prior, and frozen identity-map artifacts. If
   an approved source artifact or exact frozen mapping is unavailable, stop and
   report the named producer error; never type or infer a numerical substitute.
5. Do not access DraftKings programmatically or through browser automation.
   The entry CSV does not contain complete payouts or field size. Ask Ben one
   concise question for the smallest unavailable contest fact, normally a
   contest-details screenshot or pasted payout table. Do not ask him for facts
   that can be obtained safely from approved public evidence.
6. Update the generated machine-readable `run_request.json` with any supplied
   or validated auxiliary files and rerun:

   `sh ./nfl.sh run-slate --request '<full-path-to-run_request.json>'`
7. Continue through build, independent QA, and certification when the request
   is complete. If current official activity evidence is missing, still retain
   useful diagnostic assignments but finish `DO_NOT_UPLOAD`.
   For `prior_review`, discover or supply `official_status_csv` when official
   reports are available. The supplied rows must be current, and an INACTIVE
   row excludes both CPT and FLEX identities before selection. Missing ACTIVE
   rows remain unknown; salary status alone never establishes current activity.
   Since Session 09 (R28) Classic C1/C2 publish with a selected person's
   missing row named, as Showdown does. Classic current-role evidence follows the same rule
   as Showdown (R17, extended to Classic 2026-09-12 on Ben's ruling): the role
   resolver decides, so an unresolved or declared-changed role still blocks
   before selection and a person with no prior-season row is still excluded with
   zero share, but a history-derived prior is a sufficient basis to select. Every
   selected offensive person resting on one is named in
   `selected_evidence_gate.unverified_role_people` and in the review. A
   source-supported numerical current-team allocation in
   `nfl_classic_offensive_role_evidence_c1_v1` is still the only thing that makes
   a role a current fact, and any person the selection gate recorded as
   source-supported must still be covered by that package at C3.
   SD2 distinguishes missing and observed-zero offensive history. Rebuild older
   prior packages without SD2 coverage. A transfer carries his own prior-team
   share as an unverified cold-start prior (`TRANSFER_PRIOR_UNVERIFIED`,
   `EVIDENCE_STATE=UNKNOWN`); a person with no prior-season row anywhere is
   excluded with zero share and named with salary in `pool_coverage`; an
   unresolved transfer the market prices far above his prior (the P1 gate) leaves
   the selectable pool and is named with the smallest evidence action as
   `OFFENSIVE_UNRESOLVED_MATERIAL_ROLE_CHANGE` (`P`), and the run continues
   (R28, Ben 2026-09-23); he is never selected on the old-team share. Capture approved source bytes, prepare the
   versioned auxiliary `offensive_role_evidence_json` package in
   `docs/DATA_CONTRACTS.md`, add it to the generated request and rerun.
   Qualitative starter/backup evidence cannot invent a numerical share. Without
   supported replacements, excluded volume stays visibly unallocated. Never ask
   Ben to author numerical role priors.
   A versioned Showdown `portfolio_policy_json` may bind exact salary bytes, the game,
   the complete person/CPT/FLEX map, and all requested Entry IDs. On the
   Showdown `prior_review` profile, SD4 snapshots and validates the source and
   normalized bytes, generates a bounded legal candidate bank, jointly selects
   exactly one lineup per requested Entry ID under every effective integer cap,
   then independently reparses the canonical normalized-policy artifact and
   recomputes legality, canonical identities, combined and Captain counts,
   uniqueness, overlap and all bound hashes immediately before review export.
   Only `ENFORCED_AND_INDEPENDENTLY_AUDITED` may write a new
   `DK_REVIEW_ENTRY` CSV. Time/search limits, solver errors, incomplete-bank
   exhaustion, modeled-bank infeasibility, assignment mismatch, audit failure
   or input mutation preserve earlier outputs and write no new review CSV.
   The active bank is stratified by the policy (per-captain, per-capped-person
   exclusion, a policy-feasible chain, then top-K fill) and bounded to
   `max(32, 4 x entries)` canonical candidates with a `max(30s, 2s x entries)`
   generation budget, two seconds per candidate solve and `max(10s, 1s x
   entries)` for the joint solve; its completeness is reported and is not a
   full-slate claim.
   Classic C2 uses a distinct direct-integer policy bound to the exact salary
   and entry hashes, draft group, complete multi-game identity, registered
   objective/seed, and ordered Entry IDs. It supports player/team/game bounds,
   exclusions, hard/advisory groups and registered stack rules, uniqueness and
   pairwise person overlap. It creates a deterministic bounded legal candidate
   bank, a policy-feasible chain before top-objective fill, and one joint
   assignment without cycling. Accept
   `OPTIMAL_ACTUAL_CANDIDATE_BANK`, optimal over the reported actual bank only,
   or since Session 08 `FEASIBLE_LIMIT_ACTUAL_CANDIDATE_BANK`, a validated
   incumbent a time or search limit left, feasible and not proven optimal; each
   with independent audit `PASS`. C2 writes machine-readable JSON
   only. C3 independently reparses every bound artifact and proposed/final CSV,
   recomputes the complete portfolio and every hard limit, and publishes the
   exact-template review CSV plus readable JSON/HTML/workbook only after audit
   `PASS`. Only the nine authorized blank roster cells per exact Entry ID may
   change; all non-roster bytes and physical-line geometry remain exact.
   Other profiles refuse a supplied policy instead of ignoring it. Requests
   without the policy retain their existing SD1/SD2 behavior, including the
   legacy sequential Captain differentiation and assignment cycling.
   The SD5 review surface lists every exact Entry ID and roster ID, underlying
   person, slot and salary, prior-only central estimate, actual combined-person
   and Captain exposure, policy maxima, overlap, uniqueness, evidence/role
   observations, provenance paths and hashes. It escapes markup and renders
   spreadsheet-active prefixes inert without changing the exact source bytes.
   Any disagreement is a named `READABLE_REVIEW_FAILED` blocker and returns
   exit code 2. Under R28 (Session 05) its codes are classified through the
   gate registry: a roster, Entry ID or byte disagreement, or a code the
   registry cannot classify, withholds the review CSV, which the top-level
   result does not advertise; any other keeps the CSV listed with a
   presentation limitation, after `LATEST_DELIVERABLE.json` has revalidated it.
   Read `DELIVERY_STATE` and `latest_deliverable` in `cowork_run.json` to see
   which it was.
   Kicker roles are resolved after those exclusions. If more than one kicker
   remains eligible for a team, capture approved source bytes through
   `sources.py`, prepare the versioned `role_evidence_json` package documented
   in `docs/DATA_CONTRACTS.md`, add it to the generated request, and rerun.
   Never choose by salary, split evenly, or infer inactivity from zero offensive
   snap share. A one-kicker fallback is reported only as a prior-only sole-listed
   assumption, not confirmed role or ACTIVE evidence.
   Never send generated prior assignments to manual-guardrail certification.
   Use `preflight` immediately before any separately certified manual upload.
8. Return `FILE_VALID`, `EVIDENCE_STATE`, `MODEL_STATUS`, and
   `RELEASE_DECISION`, plus the compatibility status, blockers,
   readable JSON/HTML/workbook paths and SHA-256 values, manifest path,
   proposed/final SHA-256, display-reconciliation status, and the single next
   operator action. `FILE_VALID` never implies release. A compatibility
   `CERTIFIED` status is derived only from
   `RELEASE_DECISION=CERTIFIED_UPLOAD_PACKAGE` and is not a profitability claim.

### The Classic fallback path: a blocked engine is not a blocked slate

Added 2026-09-20. This chain exists, has run on two live slates, and was
documented only inside `docs/CLASSIC_C4_RETROSPECTIVE_2026-09-13.md` — a file
nothing told the next operator to open. On 2026-09-13 the C2 candidate-bank
solver failed six times across 43 minutes and produced nothing; on 2026-09-20 an
unreachable `api.weather.gov` blocked every route to a frozen prior package. In
both cases the engine could not certify and construction could still build.

The split: the **engine** owns evidence (priors, identity, weather, official
activity, participation) and emits a scored pool. **These scripts** own
construction, which the lock-clock ruling below classes as preferences Claude
may set. Output stays `PRIOR_ONLY / DO_NOT_UPLOAD`; nothing here certifies
anything, and none of it is an upload package.

```
scripts/make_slate_context.py    implied team totals from the run's own frozen
                                 games.csv; never invents ownership or a boost
scripts/build_classic_portfolio.py   stacks, bring-backs, exposure and overlap
                                 caps, anti-correlation; drops DraftKings
                                 OUT/IR/D rows; assigns the template's blank
                                 Entry IDs in order; never repeats a lineup,
                                 and exits 3 naming every one it could not fill
scripts/qa_classic_portfolio.py  two-tier gate, REQUIRED before handoff
scripts/write_dk_entries.py      exact-template fill plus a byte audit; writes
                                 a new file only, and exits 3 naming every
                                 blank authorized row it did not fill
```

Three things that are not optional:

- **Run `qa_classic_portfolio.py` before every handoff**, and show Tier 2. Run it
  on the written file, with `--template` and `--export`; without them it checks
  the JSON, not the file, and says so. Tier 1 exits 1 on a validity failure
  (roster, slot, bytes, export against assignment, a repeated lineup), 3 when
  authorized rows are unfilled, naming each Entry ID, and 2 when only a limit you
  passed (`--min-salary`, `--max-overlap`, `--max-exposure`, `--backup-pairs`)
  is exceeded. Tier 2 does not block and is the
  half that matters: on 2026-09-13 a portfolio passed every legality check with
  three players covering 17 of 20 lineups, and on 2026-09-20 one shipped with
  bring-back at 12 of 18 against a suggested floor of 70%. Tier 2 measured that
  and the script was simply never run.
- **Pass `--backup-pairs STARTER>BACKUP`.** Nothing else checks that the
  rostered quarterback is his team's starter. Build the pairs from the depth
  chart, and leave out any pair whose starter is DraftKings-`OUT`, because then
  the backup *is* the starter.
- **Say what the portfolio does not have.** With no `--ownership` there is no
  leverage model, and mean-max in a large field is chalk. The gate prints this;
  repeat it in the handoff.

Suggested limits, to argue about rather than adopt silently: max exposure ≤ 40%,
top-3 union ≤ 75%, anti-correlation exactly 0, stacked 100%, bring-back ≥ 70%.

### Shipping under a lock clock

Ben's ruling, 2026-09-12. **The worst outcome on this project is not a bad
lineup. It is no lineup.** A weak portfolio can be repaired by late swap; a
missed lock cannot be repaired at all, and those games are gone. Procedure
exists to keep the output honest, not to keep it from existing. When the two
conflict, ship.

Two classes of rule live in this repo and they are not the same thing, and
since 2026-09-22 a third sits between them. Ben's rulings R28, R29 and R31
(`docs/ROADMAP.md` §2.5) amend this section; each amended passage says so.

**Construction preferences** are quality choices: stack rules, exposure and
overlap caps, candidate-bank size and search budgets, the objective's tuning.
They are opinions about what makes a good portfolio. **Claude may relax any of
them, on its own authority, without asking Ben**, whenever they are what stands
between the run and a legal portfolio. Do not stop to request permission, do not
present a menu of options, and do not spend the last hour before lock tuning.
Relax, rerun, and report what was relaxed and why in the handoff.

**Distinct lineups are not a construction preference** (R29, 2026-09-22; this
list named uniqueness until then). Ben's words: "within a given portfolio keep
all submitted lineups distinct and unique." Uniqueness is never relaxed. When
distinct lineups run out, report the unfilled Entry IDs; never repeat a lineup
to fill a row. Lineup identity is the exact roster, so a different Showdown
captain makes a different lineup.

`scripts/make_classic_policy.py` encodes the ladder as a `--rung` flag that
Claude walks by hand. Nothing in the engine walks it yet, and
`scripts/make_showdown_policy.py` has no ladder at all; Session 10 builds both.
Rung 0 is every entry stacked with a bring-back on most of them; each rung
relaxes one class; and rung 4 emits no policy at all and runs C1 sequential
selection. **Rung 4 is the last structural rung.** Until 2026-09-23 this text
called it "the proven floor" that "always produces a legal portfolio", and the
2026-09-22 audit showed that it did not: C1 wrote review JSON only. Since
Session 06 it ends with a CSV. `run-slate` exports C1's own lineups through the
baseline's writer and audit as `review/DK_REVIEW_ENTRY_C1_<run_id>.csv`, which
replaces the baseline as the deliverable; if that export is refused, or C1
raises `SOLVER_RETURNED_NO_LINEUP` when distinct lineups run out
(`selection.py:538-542`), the baseline stays the deliverable. If a run
reports `MODELED_BANK_INFEASIBILITY`, `INCOMPLETE_BANK_EXHAUSTION`,
`CANDIDATE_BANK_TIMEOUT` or `CANDIDATE_BANK_SEARCH_LIMIT`, drop a rung and rerun
immediately rather than diagnosing. Diagnose afterwards, in the changelog.
Since Session 08 the bank keeps the rosters a limit-stopped solve returns, and
those two codes appear only when a limit left the bank without the entry count
or a policy-feasible witness; a bank with both delivers under
`BOUNDED_TIME_LIMIT_STOP` or `BOUNDED_SEARCH_LIMIT_STOP`, and a joint solve a
limit stopped with a valid incumbent delivers it as
`FEASIBLE_LIMIT_ACTUAL_CANDIDATE_BANK`. Both are named limitations, not rung
triggers.

**Evidence gates** are truth claims: official activity, current offensive role,
weather capture and its expiry, identity resolution, prior-package expiry, and
every hash binding. These are not preferences and the ladder does not touch
them. Under R28 the truth-claim gates (official activity, current role, weather)
stop certification, not construction or delivery: the file ships with the gap
named as a limitation. Integrity gates (exact DraftKings IDs, hashes, entry
mapping, blank-cell authority, locked cells, Classic/Showdown mode) still stop
the file they protect.

**Running order (R28, replacing the 2026-09-12 text).** The baseline goes first:
a file built from the DraftKings salary and entries bytes alone, before priors,
weather, roles or solves. This section used to put evidence gates first because
they were the only things that could make you miss a lock. Under R28 they no
longer stop the file, so they no longer lead. Start the weather and
official-activity captures alongside the baseline, not ahead of it: the engine's
improved portfolio still waits on them until Session 09, but the file does not.

**`run-slate` builds the baseline itself** (Session 06). Straight after intake,
before the session probe, policy validation, priors, weather, roles or any
solve, it writes `<output-dir>/<run_id>/baseline/DK_BASELINE_ENTRY_V1_baseline.csv`
from the run's snapshots and publishes it as `LATEST_DELIVERABLE.json`. It honours
the request's exact `--exclude` IDs and extra `--unavailable-status` codes, and
takes out everyone the request's official status file marks `INACTIVE` (R32:
only rows with exact current-slate DraftKings IDs and an HTTPS source count, and
a disagreeing row takes its person out; refused rows are named, never a stop). Nothing else from the request reaches it. The run's own review is the improvement: a review
CSV (Showdown, C3, or C1's export) replaces the baseline only through
`delivery.replace`, after its own readable-review classification and a fresh
revalidation, with the same inputs and at least as many rows. When the review
blocks (weather, identity, a policy gate), is withheld, crashes, or never runs
(the pre-review blocked exit), the baseline is still the deliverable.
Read the result, not the exit code:

- `latest_deliverable` names the file to hand over, with its `producer`
  (`run-slate:baseline`, or the review that replaced it) and SHA-256;
- `DELIVERY_STATE` and `release_truths` describe that file;
  `IMPROVEMENT_NOT_DELIVERED` among its limitations means it is the baseline
  and says why the review did not replace it;
- `baseline` and `improvement` say what each step did;
- `next` opens with the baseline's path whenever it is the deliverable.

Exit codes keep their meaning: 0 when the run's own review completed, 2 when it
did not, whether or not the baseline ships. The workbook's Upload sheet names
the deliverable's path. Both files stay on disk: a replaced baseline is kept,
never rewritten, and a review CSV that stops revalidating after it replaced the
baseline is withheld and the baseline takes the pointer back. On the `diagnostic`
and `registered` profiles, a certified package, when `RELEASE_DECISION` says so,
is `certification`'s own `DK_UPLOAD` file; `latest_deliverable` there names the
prior-only baseline as the fallback.

**Run `baseline` by hand** (Session 04) only when `run-slate` cannot start, for
example an intake it refuses or a request that will not load:

    sh ./nfl.sh baseline --salaries <DKSalaries.csv> --entries <DKEntries.csv>

(`.\nfl.ps1 baseline ...` on Windows). Add `--exclude <DK ID>` and
`--unavailable-status <code>`, each repeatable, for every fade or late scratch
the run request carries, and `--official-status <csv>` for the official status
file: a hand-run baseline knows only what you pass it. It
reads those files and nothing else: no network, priors, weather or roles. It writes a new run folder under
`data/runs/` holding `DK_BASELINE_ENTRY_V1_<run_id>.csv`, byte-audited, and
`baseline_report.json` with the five truths. Exit 0 fills every blank row; exit
3 fills some and names every unfilled Entry ID (hand that list over with the
file); exit 2 fills none and names why. When the reason, on exit 3 or 2, is
`BASELINE_RUN_BUDGET_EXHAUSTED` or `BASELINE_SOLVE_LIMIT_WITHOUT_LINEUP`, the
budget is a construction preference: rerun at once with a larger
`--budget-seconds` or `--per-solve-seconds`. Any other exit-2 reason is an
integrity gate, and the file stays withheld until its input is fixed.
Every exit ends `PRIOR_ONLY / DO_NOT_UPLOAD`, and the report names the gaps it
carries (official activity, current role, weather, model). Lineups rank by
DraftKings salary alone (`BASELINE_SALARY_RANK_V1`), so treat the file as the
baseline a later improvement replaces, not as a tuned portfolio. It applies
DraftKings' own `OUT`, `IR` and `D` flags, the exclusions it is given, and the
`INACTIVE` rows of an official status file (`run-slate` passes the request's; by
hand, the flags above). It does not judge that file's freshness or whether it
covers every player: activity stays uncertified, so say so when it is the file
you hand over.
The Classic fallback path above stays the fallback for anything the baseline
cannot build: since Sessions 02 and 02b its builder and writer refuse a wrong
input by name (exit 2), QA exits 1 on a validity failure, and all three exit 3
naming every authorized row left blank; hand that list over with the file. On a builder
shortfall, relax an exposure or overlap cap and rebuild; when distinct lineups
run out, ship the file and name the rows (R29). Run QA on the written file every
time. The default delivery deadline is the earliest
relevant lock minus 5 minutes (R31), and `run-slate` enforces it (Session 07):
one budget, built right after intake, gives the baseline at least 30 s (a
deadline already passed included), stops discretionary optimization 5 minutes
before the deadline (lock minus 10 by default), and shortens or skips the
probe and the review's solves to fit. `--delivery-deadline-utc` sets another
deadline. A skipped or stopped review exits 2 with `DEADLINE_*` limitations
(`S`) and the baseline as the file: hand it over. A C2 policy whose declared
search no longer fits is refused by name; generate it again with
`make_classic_policy.py --delivery-deadline-utc <the deadline>`, or take rung 4.
Since Session 07b the other clocks keep the same deadline: each evidence fetch
the review makes gets `min(30 s, the window)` and none starts under 1 s
(`DEADLINE_FETCH_WINDOW_SPENT`, `S`; the review stops and the baseline is the
file), the weather capture script stops its requests 5 minutes before the
deadline (`FETCH_DEADLINE_REACHED`), and the policy generator sizes its bank to
the window at this host's measured rate, or writes nothing and exits 2.

Three rules bound the autonomy above.

- **Never fabricate an observation to clear a gate.** Not a weather state, not an
  ACTIVE row, not a role allocation, not a timestamp. An invented observation is
  worse than a missed slate because it silently poisons every later replay.
- **Never relax a gate that a real source could still clear.** If the capture
  exists and you have time, go get it. Relaxation is for the clock and for
  infeasibility, not for saving effort.
- **A gate that no real source can ever clear is a defect, not a constraint.**
  Take it to Ben with a recommendation, the way R21 went. Do not work around it
  silently and do not loosen it unilaterally. That holds for development. At
  runtime, under the clock, the engine ships what it legally can and names the
  gap (audit D8, 2026-09-22); the defect still goes to Ben afterwards.

If the clock beats an evidence gate that a source could have cleared, say so
plainly, ship whatever the engine will legally produce without it, and name the
gap in the handoff. Silence about a gap is the only unrecoverable error.
