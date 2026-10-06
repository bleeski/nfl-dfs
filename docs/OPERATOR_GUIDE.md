# NFL DFS Operator Guide

This engine is local and manual at the DraftKings boundary. It never signs in,
enters contests, changes money, or uploads a lineup. A green
`RELEASE_DECISION=CERTIFIED_UPLOAD_PACKAGE` result
means that the current evidence, exact Entry IDs, roster legality, template, and
final bytes passed. It does not promise profit and is not an EV label.

## The two surfaces

Claude Code, everywhere. Which one you are on decides the launcher and nothing
else; the commands, gates and release truths are identical.

| | Windows desktop app | Cloud session, including phone |
|---|---|---|
| Launcher | `.\nfl.ps1 <cmd>` | `sh ./nfl.sh <cmd>` |
| Environment | `.venv` | `.venv-linux` |
| DraftKings files | any local path | committed under `data/inbox/slates/<slate-id>/` |
| First run | `.\nfl.ps1 setup` | `sh ./nfl.sh setup` |

Never mix the two in one session.

## Running a slate

Point the engine at the two DraftKings files and let it discover them by schema.
Do not depend on their filenames.

Windows:

```powershell
.\nfl.ps1 run-slate --input-dir '<input-directory>' --label '<short-label>'
```

Cloud session:

```sh
sh ./nfl.sh run-slate --input-dir 'data/inbox/slates/<slate-id>' --label '<short-label>'
```

`run-slate` is the documented name; `cowork-run` still works as an alias. Claude
follows `CLAUDE.md` and `docs/RUNBOOK.md`, snapshots the exact bytes, and creates
the review package.

The two DraftKings files do not contain complete payouts, field size, or current
official activity evidence. Claude gathers permitted public evidence and asks one
focused follow-up only for contest facts it cannot safely obtain. Missing hard
evidence remains `DO_NOT_UPLOAD`.

The generated `run_request.json` is the machine-readable input surface for
subsequent passes. The workbook is a versioned human review artifact. The
DraftKings upload itself is always manual.

## Windows first-time setup

Open PowerShell at the repository root and paste:

```powershell
.\nfl.ps1 setup
```

Setup installs pinned free/open-source packages, checks the Windows machine, and
creates `operator_input.xlsx`. Ben's Windows machine has long-path support turned
off, so keep slate/run labels short and do not move the project into a deeper
folder. The engine checks this every time setup runs.

## Workbook workflow (Windows, optional)

1. Download the DraftKings salary CSV and reserved-entry CSV yourself.
2. Open `operator_input.xlsx`.
3. On `Run Control`, paste full file paths into the pale-yellow cells.
4. Paste contest payout tiers, official status evidence, optional ownership
   brackets, and manual market/weather evidence on `Evidence Paste`.
5. Save and close Excel. The engine intentionally refuses to read an open
   workbook.
6. Paste this one command:

```powershell
.\nfl.ps1 run
```

The command chooses the next safe action:

- Salary and entry paths only: intake and reconcile.
- Hand-created assignment CSV plus payouts and field size: validate and attempt
  certification.
- Team/player model inputs plus payouts and field size: build a diagnostic
  portfolio, then stop for official-status evidence and certification.

Every run writes to a new timestamped folder under `outputs`. The engine never
overwrites a prior review package.

## Classic C3 governed prior-only review

Run `run-slate --profile prior_review --build-priors` with the normal Classic
salary and blank reserved-entry CSVs. Without a policy, the C1 compatibility
path publishes `classic_selection.json` for
the exact Entry-ID-to-roster map and `classic_complete_slate_coverage.json` for
named game/team/position/person coverage, exclusion reasons, unallocated volume,
conservation, and next evidence actions. These files are
`PRIOR_ONLY / DO_NOT_UPLOAD`; they are not DraftKings templates.

For C2, add `--portfolio-policy-json '<full-path-to/classic_policy.json>'` or
set `portfolio_policy_json` in the generated request. The policy must bind the
exact current salary and entry hashes, full Classic identity, direct integer
bounds, and exact Entry IDs in template order. Require all of the following in
the completed report: policy enforcement `PASS`, candidate bank
`BOUNDED_COMPLETION` or `EXHAUSTIVE_COMPLETION` (or, since Session 08,
`BOUNDED_TIME_LIMIT_STOP` or `BOUNDED_SEARCH_LIMIT_STOP`, named as a limitation),
joint selection `OPTIMAL_ACTUAL_CANDIDATE_BANK` (or a named
`FEASIBLE_LIMIT_ACTUAL_CANDIDATE_BANK` incumbent a limit left, feasible and not
proven optimal), and independent audit `PASS`. An actual-bank optimum is not a
full-slate optimum.

Every selected person requires a fresh exact-ID official activity row, and every
selected QB/RB/WR/TE requires a source-supported numerical current-team role
allocation. Missing current evidence stops publication. C2 additionally writes
canonical candidate-bank, ordered assignment, and independent selection-audit
JSON. C3 independently reparses and re-hashes the entire accepted package,
recomputes legality, all hard policy counts, uniqueness, every overlap pair and
selected evidence, then writes `DK_REVIEW_ENTRY_<label>.csv`, readable JSON,
self-contained escaped HTML, and an eight-sheet workbook only after downstream
audit `PASS`.

Open the workbook or HTML first. Confirm every exact Entry ID and roster ID,
salary total, player/team/game/group/stack limit, overlap pair, current
activity/role observation, source hash, bounded-bank warning and the four
independent truths. The review CSV preserves the original template byte-for-
byte except for the nine previously blank roster cells per authorized Entry ID.
It is explicitly review-only: `MODEL_STATUS=PRIOR_ONLY` and
`RELEASE_DECISION=DO_NOT_UPLOAD`; no `DK_UPLOAD_*.csv` is created.

Current C3 code, deterministic copied-package replay, full supplied-fixture
1/3/20/150 acceptance and independent workbook/HTML rendering pass. Under R30
(Ben, 2026-09-22) C3 is complete for software acceptance; native Excel
open/recalculate/save/reopen acceptance is deferred to Session 35 in
`docs/ROADMAP.md`, and nothing waits on it.

## Manual-lineup safety guardrail

Prepare an assignment CSV with the exact header for the mode:

Classic:

```text
Entry ID,QB,RB,RB,WR,WR,WR,TE,FLEX,DST
```

Showdown:

```text
Entry ID,CPT,FLEX,FLEX,FLEX,FLEX,FLEX
```

Use the role-row DraftKings IDs from the supplied salary file. Showdown Captain
and FLEX IDs are different. A player may appear only once by underlying person.

You can validate before certification:

```powershell
.\nfl.ps1 validate --salaries 'C:\full\path\DKSalaries.csv' --entries 'C:\full\path\DKEntries.csv' --assignments 'C:\full\path\assignments.csv'
```

## Official status evidence before lock

Certification uses exact IDs only. Each selected player must have a current row:

```text
TEAM,PLAYER_OR_GSIS_ID,STATUS,SOURCE_URL,OBSERVED_AT
```

- `STATUS` is `ACTIVE` or `INACTIVE`.
- `SOURCE_URL` must be an HTTPS official source reviewed by the operator.
- `OBSERVED_AT` must include a timezone, for example
  `2026-09-13T11:35:00-04:00`.
- The oldest selected-player observation must be no more than three hours old
  and inside the three-hour window before the earliest selected-player lock.
- Names are not accepted as automatic identity joins.
- Sleeper or another corroborating source cannot independently clear this gate.

If a selected player is inactive, missing, fuzzy-matched, conflicted, or stale,
the result is `DO_NOT_UPLOAD` and no upload-shaped CSV of that selection is left
behind. Since Session 06 `run-slate`'s baseline, built before the selection from
the DraftKings bytes alone, stays in `<output>/<run_id>/baseline/` and is named
as `latest_deliverable`, `PRIOR_ONLY / DO_NOT_UPLOAD`.

Governed late swap uses a different contract matching the NFL's official
team-scoped negative list. Do not convert the old positive-row CSV into fake
`ACTIVE` rows. The late-swap JSON requires one explicit report per relevant
unlocked team, and `inactive_dk_ids: []` represents a verified report with zero
inactive players. See `docs/DATA_CONTRACTS.md` for the exact eligibility and
team-report shapes.

## Payout evidence

The payout header is exact:

```text
rank_start,rank_end,prize_type,value
```

Ranks must be contiguous from first place through the final paid rank, and prize
values must not increase as rank worsens. `prize_type` is `CASH` or `TICKET`.
For `TICKET`, `value` is the ticket count. For satellites, enter one ticket's
face value on `Run Control`. The payout total must match the advertised contest
value to the cent. The final paid rank cannot exceed the supplied field size,
which is required for both manual and model-assisted certification.

## Model-assisted build inputs

The strict headers are documented in `docs/DATA_CONTRACTS.md`. These files use
opportunity and team environment, never DraftKings `AvgPointsPerGame`.

Create them only from already frozen, approved artifacts with the S6A producer:

```powershell
.\nfl.ps1 project `
  --salaries 'C:\full\path\frozen-salaries.csv' `
  --salary-sha256 '<64-lowercase-hex>' `
  --team-source 'C:\full\path\frozen-team-source.json' `
  --team-source-sha256 '<64-lowercase-hex>' `
  --player-source 'C:\full\path\frozen-player-source.json' `
  --player-source-sha256 '<64-lowercase-hex>' `
  --identity-map 'C:\full\path\frozen-identity-map.json' `
  --identity-map-sha256 '<64-lowercase-hex>' `
  --as-of '2026-09-09T12:00:00-05:00' `
  --output-dir 'C:\full\path\new-projection-package'
```

The four input hashes are mandatory. The command does not download anything or
fit a model. It checks approved provenance, timestamps, coverage, exact stable
provider-to-DraftKings mappings, complete team/person coverage, numerical
bounds, share conservation, unchanged input hashes, generated file hashes, and
the final source ledger before atomically publishing. The destination cannot
already exist. Any failure leaves no apparently valid partial package.

The published files are always named `team_projections.csv`,
`player_opportunities.csv`, and `source_ledger.json`. They are deterministic
prior inputs only: `MODEL_STATUS=PRIOR_ONLY` and
`RELEASE_DECISION=DO_NOT_UPLOAD` remain binding. They do not establish EV, ROI,
profitability, calibrated ownership, win/cash probability, or upload readiness.

The default workbook-driven build is intentionally a smaller diagnostic run
(2,000 scenarios, 250 candidates, and a 1,000-lineup field sample). It verifies
the workflow quickly. Field output is labeled `COLD_START_FIELD_MODEL`, not EV,
ROI, win probability, or calibrated ownership. Full registered banks can be run
from the specialized `build` command after the data/model validation gates pass.

## Reading the result

The versioned review workbook contains:

- `Run Control`: frozen operator inputs.
- `Evidence Paste`: the pasted source evidence.
- `Portfolio`: exact Entry-ID assignments and mode-aware roster slots.
- `QA`: registered triggers and binding blockers.
- `Upload`: all four release truths, compatibility status, certification basis,
  proposed/final SHA-256, exact CSV path, and operator action.

A Showdown run that supplied no policy also reports `concentration` (Session 56): the registered defaults (no person above 0.60 of
the lineups, no Captain above 0.20), what was requested and what the delivered file was built under, any relaxation by name, and
that file's own most-shared person and most frequent Captain recounted from its bytes. `AS_REQUESTED` needs nothing; anything else
is a named gap to read before the handoff.

Only a green `RELEASE_DECISION=CERTIFIED_UPLOAD_PACKAGE` cell permits
consideration of manual upload. Recheck the Entry IDs and lineups in DraftKings
before clicking upload.

## Game-day cadence

- T-24 to T-3 hours: baseline model, ownership states, candidates, contingencies.
- About T-110 minutes: paste official early-game activity evidence.
- Target T-60: certify and manually upload the conservative baseline.
- T-60 to T-10: accept only strict upgrades backed by current evidence.
- At T-10: stop discretionary optimization.
- If later evidence invalidates a package, it is no longer certified. Use a
  separately validated contingency or do not upload.

## Useful commands

```powershell
.\nfl.ps1 doctor
.\nfl.ps1 status --manifest 'C:\full\path\manifest.json'
.\nfl.ps1 audit --manifest 'C:\full\path\manifest.json'
.\nfl.ps1 test
```

For governed late swap, first download the current prefilled bulk-edit template
manually. Use the same salary snapshot and prior `CERTIFIED` manifest and
assignment CSV, prepare a proposed assignment CSV with identical Entry IDs, and
provide contest-bound eligibility plus team inactive-report JSON. Locked
roster cells are immutable. Paste this in PowerShell with full paths:

```powershell
.\nfl.ps1 late-swap `
  --run-id '2026-W02-LATE-1' `
  --salaries 'C:\full\path\frozen-salaries.csv' `
  --current-entries 'C:\full\path\current-prefilled-bulk-edit.csv' `
  --prior-manifest 'C:\full\path\prior-certified.manifest.json' `
  --prior-assignments 'C:\full\path\prior-assignments.csv' `
  --proposed-assignments 'C:\full\path\proposed-assignments.csv' `
  --eligibility-evidence 'C:\full\path\late-swap-eligibility.json' `
  --inactive-reports 'C:\full\path\team-inactive-reports.json' `
  --output-dir 'C:\full\path\outputs' `
  --as-of '2026-09-13T15:00:00-04:00'
```

Expected result:

- `CERTIFIED`: the new run folder contains a late-swap manifest and one
  `DK_UPLOAD_<run_id>.csv` with a SHA-256. Review its Entry IDs and changed
  cells before any manual upload.
- `DO_NOT_UPLOAD` (exit code 2): the manifest names every blocker and the run
  folder contains no upload-shaped CSV. Stop, resolve the first blocker, and
  rerun with a new run ID.

The command never accepts an unlocked-player boolean or caller-supplied slot
list. It derives replaceable cells from exact DraftKings IDs, the certified
prior assignment, game lock times, the current prefilled template, and the
timezone-aware `--as-of` value.

## Classic judgment pass and construction judgment

Since Session 61 a Classic `run-slate` does the parts of Ben's judgment rule (R37) that need no judgment and hands over the rest.
Print it with `scripts/judgment_pass_report.py` on the run's `cowork_run.json` (or the Classic coverage artifact):

```powershell
.\.venv\Scripts\python.exe scripts\judgment_pass_report.py 'C:\full\path\cowork_run.json'
```

The report names each team's starting quarterback and whether the pool scored him; each injury room (who vacated, who inherits,
the inheritors' prior points before and after Session 60, salaries); a ranked **candidate list to research, never a selection**;
and a **late-swap watch list** of rostered later-window people with no official row. Since Session 63 the run captures the QB
depth package itself from the depth chart the prior package froze: a backup behind a declared starter is out of every Classic row,
a team the chart cannot build is named (`QB_DEPTH_CAPTURE_TEAM_UNDECLARED:<TEAM>:<reason>`) and left unevaluated while the others are
declared, and an operator or official exclusion on a rank-1 starter DraftKings still lists as available drops that one team (R25) instead
of the package. Supply your own (`--qb-depth-role-evidence-json`, with a request base or a full path) only to override the capture; a
supplied package R25 refuses still stops the improvement and leaves the baseline: rebuild it with `--teams` naming the other teams and rerun.

To place a person the research supports, write a **construction judgment** and rerun with `--construction-judgment-json`:

```json
{"schema_version": "nfl_classic_construction_judgment_v1", "salary_sha256": "<the salary file's SHA-256>",
 "author": "claude", "authored_at": "2026-10-04T15:30:00+00:00",
 "placements": [{"dk_id": "44312345", "name": "Braelon Allen", "min_rows": 6,
                 "reason": "Breece Hall is out and Allen is the reported starter; the prior still prices his old role.",
                 "sources": [{"uri": "https://www.example.org/report", "observed_at": "2026-10-04T15:10:00+00:00"}]}]}
```

- It applies to the thesis construction (rung 4, or a Classic run with no policy). The build rosters him in at least `min_rows`
  rows, distinct and stacked, and writes no number: he keeps the prior he has. A person DraftKings marks `OUT`, an official or
  operator exclusion, a role-gate `BLOCK` or an unresolved material role change, and anyone outside the scored pool, is **refused by
  name** and the rest still apply. A file for other salary bytes, unreadable or expired at lock is dropped by name and the run goes
  on. Every one of these travels with the file as a `CLASSIC_JUDGMENT_*` limitation.
- `judgment_pass.protected_people` lists who was placed: the people a redeploy must never remove. `swap_inactives.py --mode
  redeploy --protect-from <that run json>` reads it (see Classic Pareto redeploy, below).
- The file stays `PRIOR_ONLY / DO_NOT_UPLOAD`. A placement is a construction choice, not a current-role fact. Contract:
  `docs/DATA_CONTRACTS.md` § Classic judgment pass and construction judgment.

## Classic Pareto redeploy

Since Session 62 (R37) `scripts/swap_inactives.py --mode redeploy` takes a salary-driven swap **only as a Pareto gain**, and
`scripts/build_thesis_portfolio.py` runs the same rule at its fill step. Ben: unused salary is never a defect, so nothing chases
the cap and no tool in the chain has a salary floor by default (`--min-salary` is an opt-in; QA reports a lineup under it as a Tier 2
note, never a defect). The rule works on an operator-layer portfolio JSON (what `build_thesis_portfolio.py` or
`build_classic_portfolio.py` writes), not on `run-slate`'s own file: wiring it into the run's rung-4 thesis build is Session 64.

```powershell
.\.venv\Scripts\python.exe scripts\swap_inactives.py --portfolio 'C:\path\portfolio.json' --scores 'C:\path\scores.json' `
  --salaries 'C:\path\DKSalaries.csv' --mode redeploy --protect-from 'C:\full\path\cowork_run.json' --out 'C:\path\portfolio_pareto.json'
```

- A swap is taken only when it raises the row's prior, fits the cap, keeps the row legal and distinct (R29), leaves the QB, the
  DST, his stack, the bring-back and every protected person alone, and leaves **no washout proxy worse** on the whole portfolio:
  max exposure, top-3 union and mean pairwise overlap no higher, distinct people no fewer. The incoming person has a blank
  DraftKings status and is not one the scores file excludes (pass `--status official_status.csv` to keep an official INACTIVE
  person out too; the thesis build always does). "Used at least two fewer times" is a quick screen, not the proof; the
  portfolio-level recount is, and it also takes a swap whose incoming person is used one fewer time.
- It scans every row (`--changed-entry-id` restricts it) until a whole pass takes nothing, so a rerun on its own output changes
  nothing (`fixed_point=True`; `PASS_BOUND_REACHED` means its 25-pass bound stopped it first, so rerun it). Run it **before the
  earliest lock**: it has no lock awareness, so after a lock use late swap. The thesis build leaves the priors-wrong thesis's rows
  alone (that thesis bets against the prior this ranks by). `--protect NAME_OR_ID` (repeatable) and `--protect-from <cowork_run.json | coverage.json>` name who never moves; an
  unknown or ambiguous name, an ID the salary file does not hold, or a run with no `judgment_pass` is refused, nothing written.
- Read the printed report (also `construction.pareto_redeploy` in the new file): **both goals before and after** (prior sum;
  max exposure, top-3 union, mean overlap, distinct people), every swap taken, and **every swap it refused**, each with the goal it
  would have hurt (`REJECTED entry: A -> B (+gain) would hurt: mean_overlap, ...`). A swap refused for concentration is information,
  not a failure. Where no gain exists the report says `NO_PARETO_GAIN` and the portfolio is the same.
- It is construction only: it writes no number, calls nothing EV or a win probability, and clears no gate. Re-run
  `qa_classic_portfolio.py` on the new file and keep the earlier file when nothing passes.

## Showdown value-add swap

`scripts/showdown_value_add.py` (Session 55) works one person the engine left out, such as a depth-chart starter with no
prior row, into rows of an already-filled Showdown review file by one swap each. It is construction only. He adds 0 prior
points, no projection is written, his evidence gate stays unmet, and the file stays `DO_NOT_UPLOAD`; the report says so.

```powershell
.\.venv\Scripts\python.exe scripts\showdown_value_add.py `
  --salaries 'C:\full\path\DKSalaries.csv' --template 'C:\full\path\DKEntries.csv' `
  --review 'C:\full\path\DK_REVIEW_ENTRY_v4.csv' --out 'C:\full\path\DK_REVIEW_ENTRY_v5.csv' `
  --dk-id 44282409 --count 6
```

- `--dk-id` is his exact current-slate DraftKings ID, either role row. `--template` is the original DKEntries download: only a
  row it left blank can change, and a row DraftKings prefilled is never edited, though it still counts for distinctness.
- A FLEX cell is swapped; `--captain` swaps the Captain instead. `--count N` is up to N rows (default 3). `--entry-id` names
  exact rows instead, and any named row that cannot take him refuses the whole run. `--theses` with `--thesis` limits the
  rows by label. `--scores` (`by_dk_id`, each cell by its own ID) only orders which cell goes first; without it the
  cheapest goes first. `--entry-id` does not combine with `--count` or `--thesis`.
- A swap is taken only if the row is legal (six distinct people, cap, both teams) and no other row has the same roster
  (R29: a FLEX permutation is the same roster, a different Captain is not). The tool also never creates the same six
  people under another Captain, a construction choice stricter than R29 that `keenum_swap.py` made too. A row that already
  holds him, in either slot, is never edited.
- The output is rebuilt, reparsed and audited against the template before it is created, and created exclusively. Any
  invalid row in the file, including one this tool never touched, exits 2 and writes nothing. Exit 3 means the file was
  written with fewer than N rows. Run `scripts/qa_showdown_portfolio.py` on the result next, then the concentration check.

## Settlement capture and replay

After the contest is final, prepare the strict `nfl_settlement_request_v1`
described in `docs/DATA_CONTRACTS.md`. It must name and hash the frozen salary,
reserved-entry, payout, selected-assignment, pre-lock manifest, prediction,
scenario, complete standings, and predeclared metric-registry artifacts. Then
run one command:

```powershell
.\nfl.ps1 settle `
  --request 'C:\full\path\settlement_request.json' `
  --output-dir 'C:\full\path\outputs\settlements'
```

Use a new `settlement_id`; an existing package is immutable and is never
overwritten. A successful result is `Q1_SETTLEMENT_COMPLETE` and reports the
package path, exact reference-result hash, runtime, memory, and the unchanged
four pre-lock release truths. It does not authorize upload or promote a model.

Copy the complete package anywhere and verify it with:

```powershell
.\nfl.ps1 settle --replay 'C:\full\path\copied-settlement-id'
```

Only `DETERMINISTIC_REPLAY_PASS` establishes that the copied immutable inputs,
versions, assignment semantics, ranks, ties, duplicates, prizes, reference
result, and run/settlement brief reconstruct exactly. The compatibility form
with only `--entries` and `--standings` is partial, exits `2`, and is never a
Q1-complete settlement.

## Safe failure behavior

- Excel open: readable stop message; no partial workbook.
- Missing or changed evidence: `DO_NOT_UPLOAD`; upload CSV removed.
- Classic/Showdown mismatch: rejected before selection.
- Unauthorized Entry ID or prefilled reserved row: rejected.
- Output-byte change: the manifest audit fails.
- Interruption: prior timestamped outputs remain intact; rerun creates a new run.
