# Data Contracts

All headers and identities are strict. Files are UTF-8 CSV unless the original
DraftKings input is CP1252. Times must be timezone-aware ISO 8601 values.

## Cowork run request

`cowork-run` emits and accepts JSON schema `nfl_cowork_run_request_v1`. Unknown
keys are rejected. Relative paths resolve inside the explicitly supplied
attachment/request directory. Absolute paths are accepted only for the exact
supplied files, managed project data, or the current immutable run; traversal
and symlink/reparse escapes are rejected before hashing or copying.
The request records salary, entries, payouts, assignment or paired model inputs,
official status, optional ownership brackets, the source ledger, exact contest
economics, objective, guardrail mode, and diagnostic/registered profile.

The first pass rewrites recognized file paths to immutable content-addressed
snapshots. A model-assisted Cowork run requires both team and player inputs, a
source-ledger artifact, payout evidence, advertised value, and field size.
Current official exact-ID activity evidence remains required for certification.
The source ledger must use schema `nfl_source_ledger_v1` with a nonempty
`entries` array and exact `derived.team_projections` and
`derived.player_opportunities` SHA-256 values. Every entry requires the source
artifact SHA-256 as `artifact_id`, a path, an allowlisted HTTPS `source_uri`,
timezone-aware capture/observation timestamps, an approved `license_decision`,
and a bounded `parser_version`. Unknown fields, missing/tampered artifacts, and
partial or mismatched derived hashes fail certification closed. This validates
provenance structure and binding; it does not independently establish that a
source is true, complete, current enough for every use, or commercially fit.

## Team projections

Exact header:

```text
TEAM,GAME_ID,PLAYS_MEAN,PASS_RATE,PASS_YARDS_PER_ATTEMPT,RUSH_YARDS_PER_ATTEMPT,TOUCHDOWNS_MEAN,FIELD_GOALS_MEAN,TURNOVERS_MEAN,SACKS_ALLOWED_MEAN,UNCERTAINTY,MARKET_TOTAL,MARKET_SPREAD,MARKET_OBSERVED_AT,WEATHER_STATE,ERA
```

There must be one row per slate team. `GAME_ID` uses the salary-file form such
as `NO@DET`. `UNCERTAINTY` is in `[0,1]`. Market fields are manual, timestamped
evidence; they are not silently pulled from stale schedule rows. Market totals
must be in `[20,100]`, spreads in `[-40,40]`, and certification treats the oldest
team observation as stale after six hours. `WEATHER_STATE` must be one of
`CLEAR`, `INDOOR`, `INDOOR_OR_CLEAR`, `MIXED`, `RAIN`, `ROOF_CLOSED`,
`ROOF_OPEN`, `SNOW`, or `WIND`.

## Player opportunity

Exact header:

```text
DK_ID,TEAM,POSITION,QB_ATTEMPT_SHARE,CARRY_SHARE,TARGET_SHARE,CATCH_RATE,YARDS_PER_TARGET,RUSHING_TD_SHARE,RECEIVING_TD_SHARE,ROLE_CAPACITY,EVIDENCE_STATE
```

There must be one row per underlying person. For Showdown, use that person's
FLEX role-row DraftKings ID. Shares are bounded to `[0,1]` and are deterministically
normalized within team/role. `EVIDENCE_STATE` is `PASS`, `UNKNOWN`, `STALE`, or
`CONFLICTED`; every modeled salary-pool player must be `PASS` for model-assisted
certification because every modeled outcome can affect field ranks. An eligible
team/role share group cannot be all zero, because the
engine will not invent a uniform allocation. Route participation is not present
and remains `UNKNOWN` unless a separately approved timely source is introduced.

## Ownership brackets

```text
DK_ID,LOW,BASE,HIGH
```

Values use decimal percentages (`0.25` means 25%). These are operator uncertainty
brackets, not calibrated ownership claims.

## Payouts

```text
rank_start,rank_end,prize_type,value
```

`prize_type` is `CASH` or `TICKET`. Ranges are contiguous and non-overlapping.
For `TICKET`, `value` is the number of tickets; certification multiplies it by
the separately supplied ticket face value.

## Pre-lock official activity evidence (compatibility path)

```text
TEAM,PLAYER_OR_GSIS_ID,STATUS,SOURCE_URL,OBSERVED_AT
```

The current implementation requires an exact current-slate DraftKings ID for
every selected player. Any name normalization or fuzzy matching is proposal-only.
The oldest selected-player observation controls freshness and expires after
three hours; it must also fall inside the three-hour window preceding the
earliest selected-player lock. This positive-row CSV remains available for the
existing pre-lock diagnostic/certification workflow. It is not accepted as an
official negative-list report for governed late swap.

## Contest late-swap eligibility

The governed late-swap path requires a JSON file with exactly this versioned
shape:

```json
{
  "schema_version": "nfl_late_swap_eligibility_v1",
  "contest_id": "193028206",
  "bulk_late_swap_eligible": true,
  "evidence_state": "PASS",
  "source_url": "https://operator-reviewed.example/contest-details",
  "observed_at": "2026-09-13T14:20:00-04:00",
  "expires_at": "2026-09-13T20:30:00-04:00"
}
```

The Contest ID must exactly equal the one in the current bulk-edit template.
The source must be a valid HTTPS URL, both times must include a timezone, the
observation cannot be in the future, and the evidence cannot be expired.
`bulk_late_swap_eligible` must be true and `evidence_state` must be `PASS`.
NFL mode, a user boolean, or a prefilled template never establishes eligibility.

## Team-scoped official inactive reports for late swap

Late swap uses the NFL's team negative-list semantics, not hand-entered
positive `ACTIVE` attestations:

```json
{
  "schema_version": "nfl_team_inactive_reports_v1",
  "reports": [
    {
      "team": "ARI",
      "game_id": "ARI@LAC",
      "inactive_dk_ids": [],
      "evidence_state": "PASS",
      "source_url": "https://operator-reviewed.example/inactives/ARI",
      "observed_at": "2026-09-13T14:56:00-04:00"
    }
  ]
}
```

`inactive_dk_ids` is required even when it is empty; an absent team report is
never interpreted as an empty report. Each relevant team may appear once.
Every inactive ID must be an exact current-slate DraftKings ID belonging to the
reported team and game. URLs must be valid HTTPS, observations cannot be in the
future or after lock, and a `PASS` report must be observed no earlier than 90
minutes before that team's game lock. Unknown IDs, team/game conflicts,
duplicates, stale or future times, invalid URLs, and non-`PASS` states fail
closed. Before T-90, missing final evidence is reported as `NOT_YET_DUE`; that
state is useful provisionally but cannot authorize a final late-swap file.

Players in already locked cells need no new inactive report only when the
current cell and proposed cell both exactly match the bound certified prior.

## Assignments

Classic:

```text
Entry ID,QB,RB,RB,WR,WR,WR,TE,FLEX,DST
```

Showdown:

```text
Entry ID,CPT,FLEX,FLEX,FLEX,FLEX,FLEX
```

Entry-ID coverage must exactly equal the supplied reserved entries. The exporter
changes only those blank roster cells; independent QA requires every untouched
field, physical line ending, unauthorized line, encoding, and final-newline
state to remain byte-identical.

For late swap, the prior and proposed assignment CSVs use the same headers. The
current DraftKings bulk-edit template must be fully prefilled. A dedicated
late-swap writer changes only cells independently derived as replaceable from
the certified prior, exact current-slate IDs, game lock times, and a
timezone-aware `as_of`. The ordinary pre-lock writer continues to reject every
prefilled authorized row.

## Late-swap manifest

Every new writable run records `nfl_late_swap_manifest_v1`, including hashes of
the salary pool, current prefilled template, prior certification manifest,
prior and proposed assignments, eligibility evidence, and inactive reports.
The prior `certification_manifest_v1` must be `CERTIFIED`; its salary,
assignment, original-entry-template, final-output, and evidence hashes must
reconcile with the supplied artifacts. A successful manifest additionally
binds the final CSV SHA-256 and the exact zero-based replaceable cell indexes.
Ordinary blocked runs retain the manifest but no `DK_UPLOAD_*.csv`.

Both `certification_manifest_v1` and `nfl_late_swap_manifest_v1` report the
four independent release truths: boolean `FILE_VALID`, `EVIDENCE_STATE` as
`PASS | UNKNOWN | STALE | CONFLICTED`, `MODEL_STATUS` as
`UNVALIDATED | PRIOR_ONLY | PROSPECTIVELY_VALIDATED`, and `RELEASE_DECISION` as
`CERTIFIED_UPLOAD_PACKAGE | DO_NOT_UPLOAD`. The legacy `status` field is
derived from `RELEASE_DECISION`. Blocked manifests may retain a proposed byte
hash and byte count, but `output_path` and `output_sha256` remain empty unless
the release decision is `CERTIFIED_UPLOAD_PACKAGE`.

## Standings settlement

The normalized standings adapter currently requires columns including:

```text
EntryId,Rank,Points,Prize,Lineup
```

All operated Entry IDs must be present before the portfolio can be called settled.
Original standings bytes and their SHA-256 remain the authority.
