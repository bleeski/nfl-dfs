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
and a bounded `parser_version`; producer-created entries also record exact
coverage and the deterministic transformation name. DraftKings salary URLs are
accepted only as non-fetching provenance references for operator-supplied bytes
parsed by `dk_csv_v1`; the retrieval policy remains prohibited. Unknown fields,
missing/tampered artifacts, and partial or mismatched derived hashes fail
certification closed. This validates
provenance structure and binding; it does not independently establish that a
source is true, complete, current enough for every use, or commercially fit.

## W1 nflverse prior adapter (producer of the S6A sources)

`priors-propose` and `priors-freeze` produce the three JSON artifacts the next
section consumes. Nothing else in the repository produces them. Both commands
are prior-only: their output is not EV, ROI, win probability, cash probability,
calibrated ownership, or edge.

The adapter reads exactly seven approved public artifacts, each retrieved
through `sources.fetch_public_artifact` and archived by content hash under
`<package>/raw/`:

```text
raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv   12h
raw.githubusercontent.com/nflverse/nfldata/master/data/teams.csv   30d
github.com/nflverse/nflverse-data/releases/download/stats_team/stats_team_week_<prior>.csv      7d
github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_<prior>.csv  7d
github.com/nflverse/nflverse-data/releases/download/snap_counts/snap_counts_<prior>.csv         7d
github.com/nflverse/nflverse-data/releases/download/players/players.csv                         7d
github.com/nflverse/nflverse-data/releases/download/weekly_rosters/roster_weekly_<season>.csv  24h
```

Per-source expiry reflects real staleness, not a shared default: market lines
move intraday, in-season rosters churn daily, a season abbreviation crosswalk is
static, and a completed season changes only through stat corrections. An emitted
artifact expires at the earliest expiry among its contributing sources, capped at
the game's lock time.

Transformations, all over the prior regular season and all in `Decimal` at six
decimal places:

```text
plays_mean              (attempts + sacks_suffered + carries) / games
pass_rate               (attempts + sacks_suffered) / plays
pass_yards_per_attempt  passing_yards / attempts
rush_yards_per_attempt  rushing_yards / carries
touchdowns_mean         (passing_tds + rushing_tds) / games
field_goals_mean        fg_made / games
turnovers_mean          (passing_interceptions + fumbles_lost_total) / games
sacks_allowed_mean      sacks_suffered / games
uncertainty             stdev(weekly plays) / mean(weekly plays), capped at 1
market_total            games.csv total_line
market_spread           games.csv spread_line, negated for the home team
weather_state           games.csv roof: dome/closed/open only; otherwise operator-supplied
```

Player weights are each person's share of their DraftKings pool team's eligible
group, so the denominators match the sets `projection.py` renormalizes over:
`qb_attempt_weight` from attempts, `carry_weight` from carries, `target_weight`
from targets, `rushing_td_weight` and `receiving_td_weight` from those TD counts.
`catch_rate` is receptions/targets and `yards_per_target` is
receiving_yards/targets, both zero outside RB/WR/TE. `role_capacity` is the mean
regular-season `offense_pct`, joined on Pro Football Reference id. Player usage
joins on provider player id alone, never on current team, because players move.
A group whose eligible members have no prior-season support fails closed with
`PRIOR_SUPPORT_MISSING`; uniform filling is never applied.

Identity is a two-phase gate because DraftKings and nflverse share no key.
`priors-propose` writes `nfl_prior_identity_proposal_v1` plus a reviewable
`identity_review.csv`, and emits only normalized match methods. `priors-freeze`
requires that file's SHA-256, requires `DECISION=ACCEPT` on every row, refuses an
altered row or a duplicated provider id, and only then writes
`match_method="EXACT"`. Team identity binds the DraftKings team abbreviation to
the nflverse code through the DST row's nickname against `teams.csv`, which is
how `LAR` resolves to `LA` without a hand-written mapping. A Showdown pool lists
each person twice; one person gets one mapping and one record, keyed to the FLEX
row, and both roles are reconciled in `coverage`.

A `role_capacity` of zero does not remove a person from scoring. That is R03 and
tranche W3 owns it; the adapter reports every zero-capacity person in
`zero_role_capacity_people` rather than working around it.

## S6A deterministic projection sources

`project` requires four existing local artifacts and the independently recorded
lowercase SHA-256 of each artifact:

1. the untouched DraftKings salary CSV;
2. `nfl_team_projection_source_v1` JSON;
3. `nfl_player_opportunity_source_v1` JSON; and
4. `nfl_projection_identity_map_v1` JSON.

The two source JSON files and the identity map each contain `metadata` with
exactly `source_uri`, `captured_at`, `observed_at`, `expires_at`,
`license_decision`, `parser_version`, `evidence_state`, and nonempty `coverage`.
All timestamps are timezone-aware. The accepted parser versions are
`team_projection_source_v1`, `player_opportunity_source_v1`, and
`projection_identity_map_v1`. Metadata and every record/mapping must be `PASS`
at the explicit `--as-of`; future, expired, unknown, stale, or conflicted input
fails closed. The source URI/license pair must match the repository source
policy. No network access occurs in this command.

The team source has a nonempty `records` array with these exact fields:

```text
provider_team_id, game_id, plays_mean, pass_rate,
pass_yards_per_attempt, rush_yards_per_attempt, touchdowns_mean,
field_goals_mean, turnovers_mean, sacks_allowed_mean, uncertainty,
market_total, market_spread, market_observed_at, weather_state, era,
evidence_state
```

Every value is copied through the existing team bounds without fitting,
clipping, or imputation. Provider team IDs must be unique and must resolve
through one exact frozen team mapping to every salary-pool team/game.

The player source has a nonempty `records` array with these exact fields:

```text
provider_player_id, provider_team_id, position, qb_attempt_weight,
carry_weight, target_weight, catch_rate, yards_per_target,
rushing_td_weight, receiving_td_weight, role_capacity, evidence_state
```

Weights must be finite JSON numbers in `[0,1]`; `yards_per_target` is in
`[0,30]`. The producer applies the same position masks as the opportunity
loader, then computes each eligible share as `source_weight / sum of the
team's eligible source weights`. An all-zero or missing eligible group is an
error; the producer never invents uniform shares. Catch rate, yards per target,
and role capacity are direct bounded source fields. There are no runtime-fitted
coefficients or freehand numerical parameters in S6A.

The identity map contains `salary_artifact`, `team_mappings`, and
`player_mappings`. `salary_artifact.artifact_id` must match both the supplied
salary hash and its current bytes; its only accepted provenance combination is
an operator-supplied DraftKings HTTPS reference with parser `dk_csv_v1`.
Mappings bind stable provider IDs to exact current salary-pool team, position,
underlying-person, and DraftKings IDs. `match_method` must be exactly `EXACT`.
Normalized, fuzzy, duplicate, ambiguous, incomplete, team-conflicted, or
position-conflicted mappings never assemble. Showdown mappings must select the
person's distinct `FLEX` row; a CPT ID or duplicate CPT/FLEX person fails.

The producer writes LF-terminated UTF-8 bytes to a run-scoped temporary
directory, validates both CSVs through `load_opportunity_model`, validates the
ledger through `validate_source_ledger`, rechecks every input/output hash, and
only then atomically publishes this exact package:

```text
<output-dir>/team_projections.csv
<output-dir>/player_opportunities.csv
<output-dir>/source_ledger.json
```

The output directory must not already exist. Team rows use game-lock order and
away/home order; player rows use ascending numerical FLEX/current DK ID. The
same frozen inputs and explicit `as_of` produce byte-identical CSV and ledger
content in different output directories. A failed build publishes none of the
three files. The package is always `MODEL_STATUS=PRIOR_ONLY` and
`RELEASE_DECISION=DO_NOT_UPLOAD`; it is not predictive validation or upload
authorization.

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
