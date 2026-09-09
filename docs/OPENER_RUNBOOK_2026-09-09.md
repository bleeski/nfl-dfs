# Opener runbook: NE@SEA Showdown, 2026-09-09

**September 9 review update:** `nfl.ps1 preflight` is now available. The
preflight check validates the manifest contract and policy, includes the
model-specific evidence requirements when applicable, and reconciles activity
IDs to the actual exported roster. Official-status parsing now rejects reserved
or local hosts, embedded credentials, and conflicting CPT/FLEX statuses, and
certification retains the asserted source URL. The `.invalid` acceptance
described in the historical rehearsal section below is repaired. Source content
is still operator-attested; a plausible URL is not verification of the page.
See `READINESS_REVIEW_2026-09-09.md` for the separate automatic review workflow.

Execute this yourself between **17:50 and 19:20 CT**. Every step below was
rehearsed end to end on 2026-09-08 evening against the real salary CSV and the
real entry template, with stand-in contest facts and a deliberately synthetic
official-status file. The rehearsal's measured stage times are at the bottom.

## What tonight is, and what it is not

This is a **MANUAL_GUARDRAIL rehearsal with a manual upload of a lineup you
picked yourself**. The engine checks legality, template authorization, evidence
freshness and exact bytes. It does not pick the lineup and it makes no claim
that the lineup is good.

`RELEASE_DECISION=CERTIFIED_UPLOAD_PACKAGE` means the exact bytes passed every
current hard gate. It is not validation, not EV, not an edge.

`prior_review` output is not eligible tonight. `prior_review` refuses an
`assignment_csv` for exactly that reason, and its output stays `PRIOR_ONLY` /
`DO_NOT_UPLOAD`.

Do not run `audit` and treat a green result as permission to upload. `audit` is
now historical artifact integrity only: it tells you the recorded bytes still
match the recorded hashes, it reports the manifest's stored decision labelled as
stored, and its own `RELEASE_DECISION` is always `DO_NOT_UPLOAD`. The live
pre-upload check is `preflight`, added by W6 on 2026-09-08, and it re-derives
every hard gate at the current clock. **Certify fresh, then run `preflight`,
then upload.**

## Slate facts, read from the files

| Fact | Value | Where it came from |
|---|---|---|
| Kickoff / lock | **2026-09-09 19:20 CT** (20:20 ET, 2026-09-10 00:20 UTC) | salary CSV `Game Info`: `NE@SEA 09/09/2026 08:20PM ET` |
| Contest | NFL Showdown $2.25M Wednesday Kickoff Millionaire [$1M to 1st TD Throne Eligible] (NE @ SEA) | DKEntries template |
| Contest ID | 193391013 | DKEntries template |
| Entry fee | $20 | DKEntries template |
| Reserved Entry IDs | 5232816721, 5238395397 | DKEntries template |
| Salary cap | 50000, one CPT plus five FLEX, both teams required | engine contract |

## Open flags

- **[BEN: payout table]** Contiguous, non-overlapping `rank_start,rank_end,prize_type,value`.
- **[BEN: advertised prize value]** Must reconcile to the payout table within **$0.01** or certification raises `PayoutContractError`. If DK's advertised headline does not equal the sum of the tiers, the table wins and the advertised number has to be the table's true total.
- **[BEN: ticket face value]** Required only if any tier pays `TICKET`.
- **[BEN: field size]** Integer, at least 2, and at least the largest paid rank.
- **[BEN: fresh DK salary CSV and DKEntries template]** Re-downloaded on 2026-09-09 and their paths.
- **[BEN: your two lineups]** One CPT and five FLEX per entry, or say if you are entering only one reservation.

## The three-hour window, which is the part that bites

For tonight's pre-lock path (`--official-statuses`), `_official_status_evidence`
in `cli.py` uses a **three-hour** window, not 90 minutes:

- Every selected DK ID must appear in the file, or the state is `UNKNOWN`.
- The oldest selected-player observation must be **no earlier than 16:20 CT**
  (kickoff minus three hours), or the state is `STALE`.
- The certify run must happen **within three hours of that oldest
  observation**, or the state is `STALE`.
- No observation may be in the future by more than five minutes, or the state
  is `CONFLICTED`.
- No selected player may already be locked, or the state is `FAIL`.

The T-90 (17:50 CT) figure is the due time for
`evidence.team_inactive_report_evidence`, which governs **governed late swap**,
a different path with a different file shape. Tonight's path is the three-hour
one. Starting at 17:50 keeps you comfortably inside it either way.

## Checklist

**1. 17:45 CT. Confirm the runtime.**

```powershell
cd C:\Users\benja\Documents\Claude\nfl-dfs
.\nfl.ps1 doctor
```

Expect `pass_status: true`. *Stop rule:* if `pass_status` is false, read the
named probe error. Do not proceed on a false `pass_status`; `cowork-run` gates
on it and certify's results are not trustworthy without it.

**2. 17:45 CT. Re-download both DraftKings files.** Salary CSV and the DKEntries
template for contest 193391013, downloaded today. *Stop rule:* if the DKEntries
template already has roster cells filled, stop. The pre-lock writer rejects a
prefilled authorized row by design, and a prefilled template belongs to the
late-swap path, not this one.

**3. 17:50 CT. Write your assignment CSV.** Exact header, exact current-slate
DraftKings IDs, one row per Entry ID you are entering:

```text
Entry ID,CPT,FLEX,FLEX,FLEX,FLEX,FLEX
5232816721,<cptId>,<id>,<id>,<id>,<id>,<id>
5238395397,<cptId>,<id>,<id>,<id>,<id>,<id>
```

The CPT slot must use the player's **CPT-row ID**, which is a different ID and a
different salary from his FLEX row. *Stop rules:*

- **Both entries cannot carry the same six IDs.** The rehearsal hit
  `DUPLICATE_SELECTED_LINEUPS`, a CRITICAL blocking QA finding, and the run
  ended `DO_NOT_UPLOAD`. Change at least one slot, or enter only one
  reservation.
- Entry-ID coverage must exactly equal the reserved entries you are filling.
- If a name is ambiguous or an ID is outside the pool, certify names the slot
  and stops. Fix the ID, do not fuzzy-match.

**4. 17:55 CT. Read official statuses and generate the evidence file.** Open the
official source, read the status of all six players per lineup, then:

```powershell
python scripts\make_official_status.py `
  --salaries .\DKSalaries.csv `
  --assignments .\assignments.csv `
  --source-url https://www.nfl.com/injuries/ `
  --observed-at now `
  --out .\official_status.csv
```

Add `--inactive <id>,<id>` for anyone reported out. The script resolves TEAM
from the salary CSV so a player/team conflict cannot be typed by hand, prints
the observation window derived from `Game Info`, and warns before certify does
if the timestamp falls outside it. *Stop rules:*

- If the script prints the stale warning, you read the source too early.
  Re-read it and regenerate.
- If you marked anyone `INACTIVE` and he is still in a lineup, certification
  reports `FAIL` with `selected players are officially inactive`. Replace him,
  regenerate the assignment CSV, and regenerate this file.
- `--source-url` must be `https://` with a real hostname. The gate checks the
  shape of that URL and the freshness of the timestamp. **It does not fetch the
  page and it cannot tell whether what you typed is true.** The honesty of this
  file is entirely on you.

**5. 18:00 CT. Certify.** Run this within three hours of the observation in
step 4, and immediately before uploading:

```powershell
.\nfl.ps1 certify `
  --salaries .\DKSalaries.csv `
  --entries .\DKEntries.csv `
  --assignments .\assignments.csv `
  --payouts .\payouts.csv `
  --advertised-prize-value <BEN> `
  --field-size <BEN> `
  --official-statuses .\official_status.csv `
  --manual-guardrail `
  --label opener `
  --run-id OPENER-20260909-NE-SEA `
  --output-dir .\outputs
```

Add `--ticket-face-value <BEN>` only if a tier pays `TICKET`.

**6. Read exactly these fields from the JSON on stdout.**

| Field | Required value |
|---|---|
| `FILE_VALID` | `true` |
| `EVIDENCE_STATE` | `PASS` |
| `MODEL_STATUS` | `UNVALIDATED` (correct here; the model is not used) |
| `RELEASE_DECISION` | `CERTIFIED_UPLOAD_PACKAGE` |
| `status` | `CERTIFIED` |
| `blockers` | `[]` |
| `upload_csv` | a path, not `null` |
| `sha256` | a digest, not `null` |
| exit code | `0` |

`FILE_VALID: true` on its own is **not** permission to upload. Only
`RELEASE_DECISION=CERTIFIED_UPLOAD_PACKAGE` with an empty `blockers` list is.
When the run blocks, `upload_csv` and `sha256` are `null` and no upload-shaped
CSV is written to disk; `proposed_sha256` may still be reported, and that is a
hash computed in memory, not a file you may upload.

**7. Verify the bytes before uploading.** The upload CSV is the entry template
with only your roster cells filled:

```powershell
Get-FileHash .\outputs\OPENER-20260909-NE-SEA\DK_UPLOAD_OPENER-20260909-NE-SEA.csv -Algorithm SHA256
```

It must equal the `sha256` in the JSON. In the rehearsal the output was 144
lines in and 144 out, with exactly lines 2 and 3 changed, the two reserved Entry
IDs. *Stop rule:* if the hashes differ, or any line other than your entries
changed, do not upload.

**7b. Run the live pre-upload check.** This is the last gate before you touch
DraftKings, and unlike `audit` its exit code is the release decision:

```powershell
.\nfl.ps1 preflight `
  --manifest .\outputs\OPENER-20260909-NE-SEA\DK_UPLOAD_OPENER-20260909-NE-SEA.manifest.json `
  --salaries .\DKSalaries.csv `
  --entries .\DKEntries.csv `
  --assignments .\assignments.csv
```

Require `check_scope: LIVE_PRE_UPLOAD`, `RELEASE_DECISION:
CERTIFIED_UPLOAD_PACKAGE`, an empty `blockers` list, and exit code 0. Read
`checked_at`: that is the instant the evidence was re-evaluated, and every
minute after it is a minute closer to the three-hour expiry. The `checks` array
names each thing that was rebound and at what scope, including
`selected_player_locks`, which re-derives from the salary CSV whether any of
your players has already locked. *Stop rule:* anything other than
`CERTIFIED_UPLOAD_PACKAGE` with exit 0 means do not upload, whatever certify
said a moment earlier.

**8. Upload manually.** Log in to DraftKings yourself, upload the CSV, and
confirm the entries on screen. Nothing in this repository logs in, enters,
edits, uploads, or moves money, and nothing should.

## Failure modes and what each one means

| Blocker | Meaning | Action |
|---|---|---|
| `DUPLICATE_SELECTED_LINEUPS` | Two entries carry identical rosters | Change a slot, or enter one reservation |
| `official_inactive_status:STALE` | Oldest observation outside the three-hour window | Re-read the source, regenerate, recertify |
| `official_inactive_status:UNKNOWN` | A selected ID has no row in the status file | Regenerate the status file from the final assignment CSV |
| `official_inactive_status:CONFLICTED` | Future timestamp, bad row, team mismatch, or a non-HTTPS URL | Read the named row number and fix it |
| `official_inactive_status:FAIL` | A selected player is INACTIVE, or already locked | Replace the player and redo steps 3 through 5 |
| `PayoutContractError` | Tiers not contiguous, values not non-increasing, or total does not reconcile the advertised value | Fix the payout CSV; the tier total is authoritative |
| `SALARY_INPUT_CHANGED_DURING_CERTIFICATION` and siblings | An input file changed mid-run | Close whatever has it open and rerun |
| `ENTRY_AUTHORIZATION` problems | Assignment Entry IDs do not match the template | Match them exactly |
| `SELECTED_PLAYER_ALREADY_LOCKED` (preflight) | A selected player's game has started | Too late for that entry; do not upload it |
| `LIVE_BINDING_INCOMPLETE` (preflight) | You did not pass `--salaries` | Pass it; locks cannot be re-derived without the current pool |
| `INPUT_BINDING` (preflight) | A file on disk no longer matches the certified hash | Recertify from the current files |

If the clock passes **19:10 CT** and you are still fighting a blocker, stop.
Upload nothing, or hand-enter a lineup in the DraftKings UI. There is no
fallback that weakens a gate, and none is authorized.

## What the rehearsal measured, 2026-09-08

Cowork/Linux, pinned 3.13.7, local-disk working copy at `/tmp/w6`:

| Stage | Wall time |
|---|---|
| `nfl.sh setup` (fresh venv, interpreter download included) | under 30 s |
| Full test suite | 9.89 s, 292 passed, 1 skipped, 293 collected |
| `certify`, live clock, duplicate lineups | 450 ms, exit 2 |
| `certify`, live clock, distinct lineups | 868 ms, exit 2 |
| `certify`, simulated 18:00 CT clock | 48 ms, exit 0 |

The commands take under a second. Your entire time budget tonight goes to
reading official statuses and typing the assignment CSV, which is why steps 3
and 4 have the stop rules and the generator script.

## One thing the rehearsal proved that you should know

Under a simulated 18:00 CT clock, a run reached `CERTIFIED_UPLOAD_PACKAGE`
using a status file whose `SOURCE_URL` was
`https://rehearsal.invalid/SYNTHETIC-NOT-OFFICIAL-EVIDENCE`. `.invalid` is a
reserved TLD that can never resolve. The gate accepted it because it checks only
that the URL is `https://` with a hostname.

That synthetic package was destroyed and no upload-shaped CSV survived the
rehearsal. The point stands for tonight: **the official-status gate binds the
freshness and the exact IDs, and it binds the hash of the CSV you wrote. It does
not bind the source.** It is a provenance-and-freshness gate, not a truth gate.
Whatever you type in step 4 is the thing being trusted.
