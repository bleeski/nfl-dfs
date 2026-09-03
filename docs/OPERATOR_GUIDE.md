# NFL DFS Operator Guide

This engine is local and manual at the DraftKings boundary. It never signs in,
enters contests, changes money, or uploads a lineup. A green `CERTIFIED` result
means that the current evidence, exact Entry IDs, roster legality, template, and
final bytes passed. It does not promise profit and is not an EV label.

## Primary Claude Cowork workflow

The normal workflow no longer requires editing Excel. In Claude Cowork Desktop,
select `C:\Users\benja\Documents\Claude\nfl-dfs` as the local project folder,
attach the DraftKings salary CSV and reserved-entry CSV, and ask Claude to run
the complete slate workflow. Claude follows `CLAUDE.md` and
`docs/COWORK_RUNBOOK.md`, discovers the files by schema, snapshots them, and
creates the review package.

The two DraftKings files do not contain complete payouts, field size, or current
official activity evidence. Claude gathers permitted public evidence and asks
one focused follow-up only for contest facts it cannot safely obtain. Missing
hard evidence remains `DO_NOT_UPLOAD`.

The command Claude drives is:

```text
sh ./nfl.sh cowork-run --input-dir '<attachment-directory>' --label '<short-label>'
```

The generated `run_request.json` is the machine-readable input surface for
subsequent passes. The workbook is a versioned human review artifact. DraftKings
upload remains manual.

## Manual Windows fallback: first-time setup

Open PowerShell in `C:\Users\benja\Documents\Claude\nfl-dfs` and paste:

```powershell
.\nfl.ps1 setup
```

Setup installs pinned free/open-source packages, checks the Windows machine, and
creates `operator_input.xlsx`. The current machine has long-path support turned
off, so keep slate/run labels short and do not move the project into a deeper
folder. The engine checks this every time setup runs.

## Manual Windows fallback: weekly workflow

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

## Official status evidence

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
the result is `DO_NOT_UPLOAD` and no upload-shaped CSV is left behind.

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
- `Upload`: status, exact CSV path, SHA-256, and operator action.

Only a green `CERTIFIED` cell permits consideration of manual upload. Recheck the
Entry IDs and lineups in DraftKings before clicking upload.

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

For late swap, the original and proposed assignment CSVs must have identical
Entry IDs. Locked roster cells are immutable:

```powershell
.\nfl.ps1 late-swap --salaries 'C:\full\path\DKSalaries.csv' --original 'C:\full\path\original.csv' --proposed 'C:\full\path\proposed.csv' --as-of '2026-09-13T14:30:00-04:00'
```

## Safe failure behavior

- Excel open: readable stop message; no partial workbook.
- Missing or changed evidence: `DO_NOT_UPLOAD`; upload CSV removed.
- Classic/Showdown mismatch: rejected before selection.
- Unauthorized Entry ID or prefilled reserved row: rejected.
- Output-byte change: the manifest audit fails.
- Interruption: prior timestamped outputs remain intact; rerun creates a new run.
