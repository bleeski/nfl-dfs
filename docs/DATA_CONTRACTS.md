# Data Contracts

All headers and identities are strict. Files are UTF-8 CSV unless the original
DraftKings input is CP1252. Times must be timezone-aware ISO 8601 values.

## Cowork run request

`cowork-run` (aliased `run-slate`) emits `nfl_cowork_run_request_v3` and accepts
`v1`, `v2` and `v3`. Unknown keys are rejected.

**v3, added 2026-09-24 (Session 07), adds exactly one field:**
`delivery_deadline_utc`, when the run's file is due, an ISO-8601 moment with a
UTC offset, stored in UTC; a naive or unparseable value is refused. Absent, the
deadline is the earliest relevant lock minus 5 minutes (R31); § Deadline budget
says what the run does with it. The CLI flag is `--delivery-deadline-utc`. A
`v1` or `v2` request carrying it is refused, naming `v3`; a later version may
carry every earlier version's fields. A command-line value for a field a later
version added, given on a reloaded older request, makes this run's
`run_request.json` that later version; the file it was loaded from is untouched.

**v2, added 2026-09-19 (P1b), adds exactly one field:**
`qb_depth_role_evidence_json`, the optional quarterback depth-chart package
documented below under *Quarterback depth-chart role evidence*. Nothing else
changed, and v1 keeps precisely the fields it always had.

Both versions are accepted because every `run_request.json` already on disk
declares v1 and they must stay replayable; `docs/START_HERE.md` records that the
schema string is deliberately stable for the same reason. A **v1 request that
carries `qb_depth_role_evidence_json` is refused**, naming the version that
introduced the field. That refusal is what makes "v1 is never mutated" a
property of the code rather than a statement in a document: a v1 request means
today exactly what it meant when it was written.

New fields follow the same pattern — add the field, bump the emitted version,
add the old version to the accepted set, and register the field in
`cowork.REQUEST_FIELDS_ADDED_AFTER_V1` so an older schema cannot carry it.

Where the package is bound: the CLI flag is `--qb-depth-role-evidence-json` on
both `run-slate` and `select`; the path is confined like every other request
path; the hash is bound into the pre-lock manifest as
`qb_depth_role_evidence_sha256` and re-verified at all three `prior_review`
success exits; and on the Classic C3 exit it is an optional immutable binding
alongside `weather_evidence_sha256`, not a required artifact. Relative paths resolve inside the explicitly supplied
attachment/request directory. Absolute paths are accepted only for the exact
supplied files, managed project data, or the current immutable run; traversal
and symlink/reparse escapes are rejected before hashing or copying.
The request records salary, entries, payouts, assignment or paired model inputs,
official status, optional `role_evidence_json`, optional
`offensive_role_evidence_json`, optional `portfolio_policy_json`, optional
ownership brackets, the source ledger, exact contest economics, objective,
guardrail mode, and profile.

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
weather_state           games.csv roof: dome/closed/open only; otherwise an attributed
                        operator capture, or UNOBSERVED (Session 09) when there is none
```

Since Session 09 (R28) a game whose weather nobody observed no longer fails
the freeze (`WEATHER_STATE_REQUIRED`, and for Classic an unsourced state,
`CLASSIC_WEATHER_SOURCE_REQUIRED`). It is written `UNOBSERVED` under the basis
`WEATHER_UNOBSERVED:roof=<roof>` (`...:UNATTRIBUTED_STATE_NOT_WRITTEN` when a
Classic state came with no source, which is never written), and `run-slate`
names it per game as `WEATHER_UNOBSERVED` (`P`, stops certification). An open
roof with no capture keeps its schedule-derived `ROOF_OPEN` and is named the
same way. `UNOBSERVED` is not an operator state and moves no number (R24). A
conflicting or unsupported supplied state, and a supplied capture that fails its
source, time or hash checks, still stop.

Player weights are each person's share of their DraftKings pool team's eligible
group, so the denominators match the sets `projection.py` renormalizes over:
`qb_attempt_weight` from attempts, `carry_weight` from carries, `target_weight`
from targets, `rushing_td_weight` and `receiving_td_weight` from those TD counts.
`catch_rate` is receptions/targets and `yards_per_target` is
receiving_yards/targets, both zero outside RB/WR/TE. `role_capacity` is the mean
regular-season `offense_pct`, joined on Pro Football Reference id. Since SD2,
opportunity and receiving efficiency use exact provider-person **current-team
rows only**, using the frozen team crosswalk. Old-team rows are counted in
history coverage but never enter a new-team denominator. A missing or transferred
person has an explicit unknown basis, zero placeholders and `EVIDENCE_STATE=UNKNOWN`;
those placeholders cannot enter selection without supported current opportunity.
An entirely missing group may survive projection as unknown for role resolution;
an observed all-zero group still fails with `PRIOR_SUPPORT_MISSING`. No uniform
filling occurs. Adapter version: `nflverse_prior_adapter_v2`.

### The `roof` column is retrospective (R26, 2026-09-21)

nflverse writes `games.csv` `roof` only after the game is played, so an unplayed
game at a retractable-roof venue carries an empty cell, not `closed`. Measured on
the 2026-09-20 frozen artifact: 177 `outdoors`, 52 `dome`, 2 `closed` and 41
blank across the 2026 rows, with every blank at ARI, ATL, DAL, HOU or IND, and no
blank at all in the completed 2025 rows.

`venues.py` resolves that one case and nothing else. It counts the venue's own
completed home games by recorded roof state, out of the same frozen artifact the
run has bound, over the prior-plus-current season window, and resolves a blank to
`closed` only when that window is unanimous and holds at least eight games. The
basis string carries the counts and the window
(`DERIVED_FROM_VENUE_ROOF_HISTORY:retractable:closed=8/8:seasons=2025,2026`).

Three things it does not do. It never touches a cell the artifact filled in, so
`outdoors` stays `outdoors`. It never resolves a venue with one recorded `open`
game in the window, which is why the window is two seasons and not four: at four,
all five venues show an `open` game. And an operator observation always outranks
it, because a capture is an observation and this is a count.

Identity is a two-phase gate because DraftKings and nflverse share no key.
`priors-propose` writes `nfl_prior_identity_proposal_v2` plus a reviewable
`identity_review.csv`, and emits only normalized match methods. v2 added
`markets[].venue_roof_history` and `markets[].venue_roof_history_seasons`, which
carry the counts above; a v1 proposal reads correctly with the keys absent and
resolves nothing from them. `priors-freeze`
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
2. `nfl_team_projection_source_v1` JSON, or `nfl_team_projection_source_v2`
   (Session 09), which is v1 plus the `weather_state` value `UNOBSERVED`. The
   freeze declares v2 only when a record carries it, so every other package is
   byte-identical v1, and a v1 file holding `UNOBSERVED` is refused;
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
`ROOF_OPEN`, `SNOW`, or `WIND` (`nfl_team_projections_csv_v1`).

`nfl_team_projections_csv_v2` (Session 09, R28) is v1 with one more
`WEATHER_STATE` value, `UNOBSERVED`: a game nobody observed. The header is
unchanged, and v1 stays as written. A manifest declares v2 only for a file with
at least one `UNOBSERVED` row, so any other file is still exactly v1.
`UNOBSERVED` moves no number, and certification never reads it as weather
evidence (`weather_if_required` is `UNKNOWN`).

## Player opportunity

Exact header:

```text
DK_ID,TEAM,POSITION,QB_ATTEMPT_SHARE,CARRY_SHARE,TARGET_SHARE,CATCH_RATE,YARDS_PER_TARGET,RUSHING_TD_SHARE,RECEIVING_TD_SHARE,ROLE_CAPACITY,EVIDENCE_STATE
```

There must be one row per underlying person. For Showdown, use that person's
FLEX role-row DraftKings ID; for Classic, use the sole exact salary-row ID and a
null `dk_role` identity mapping. Shares are bounded to `[0,1]` and are deterministically
normalized within team/role. `EVIDENCE_STATE` is `PASS`, `UNKNOWN`, `STALE`, or
`CONFLICTED`; every modeled salary-pool player must be `PASS` for model-assisted
certification because every modeled outcome can affect field ranks. An eligible
team/role share group cannot be all zero, because the
engine will not invent a uniform allocation. Route participation is not present
and remains `UNKNOWN` unless a separately approved timely source is introduced.

## C1 Classic intake and prior-review artifacts

Classic is detected only from the exact nine-slot reserved-entry schema and a
salary roster-position set contained in `QB`, `RB/FLEX`, `WR/FLEX`, `TE/FLEX`,
and `DST`. The salary parser requires exact position/roster compatibility,
positive salaries, at least two games, every team in exactly one game, unique DK
IDs and underlying people, legal position depth, and the fixed $50,000 cap. If a
salary file includes one of `Draft Group`, `Draft Group ID`, or `DraftGroup`,
exactly one nonblank value must cover every row and must match any explicitly
required draft group. With no embedded field, the full salary SHA-256 is the
draft-group identity fallback. Intake binds that hash plus the untouched entry
hash, exact game/team/opponent/lock set, mode, parser/scoring versions, contest
facts, Entry IDs, and blank-cell authority. `AvgPointsPerGame` remains only in
those untouched raw bytes and has no parsed numerical field.

The shared S6A prior and projection schemas cover every Classic game, team, and
person. The prior package records ordered `dk_game_ids`, exact lock times,
nflverse game IDs, per-game market/weather basis, full team mappings and one
null-role player mapping per exact Classic DK ID. A game resolves only through
the exact season, local game date, oriented away/home pair and injective team
crosswalk. Team/player share validation, missing-history/observed-zero/transfer
states, source metadata, approved license decisions, expiry, archived source
hashes and deterministic projection ledger remain the existing S6A contracts.

Per-game operator weather uses `nfl_classic_weather_evidence_c1_v1`:

| Field | Contract |
|---|---|
| `schema_version` | Exactly `nfl_classic_weather_evidence_c1_v1` |
| `salary_sha256` | Exact untouched current Classic salary bytes |
| `games` | Object whose keys exactly equal the complete salary game set |
| each game value | `weather_state`; relative content-addressed `path` and exact `sha256`; approved `source_uri`, `license_decision`, and `parser_version`; ordered timezone-aware `observed_at`, `captured_at`, and `expires_at` |

The existing six-hour weather expiry applies independently; the earliest
material observation expires the team package. Unknown games, incomplete game
coverage, scalar/per-game conflicts, invalid states, unapproved sources, stale
observations and input mutation fail before publication. Schedule-authoritative
fixed/closed/open roof state is not overwritten by an operator state.

Classic current offensive allocation uses
`nfl_classic_offensive_role_evidence_c1_v1`. It shares SD2's source,
transformation, conservation, position-mask, freshness and numerical-support
rules, but has `game_ids` exactly equal to the full slate and each person binds
the sole exact `dk_id` rather than CPT/FLEX IDs. Every declaration's team and
game must match the salary contract. Every selected offensive person must have
state `SOURCE_SUPPORTED_ADJUSTMENT`; a selected person with historical-only,
missing, transfer-unknown, synthetic, stale, or absent current role evidence
stops publication and reports the smallest evidence action. A selected person
with no fresh exact-ID official ACTIVE/INACTIVE row is named, not stopped, since
Session 09 (below); an `INACTIVE` row still takes him out first. Nonselected
uncertainty stays visible and can keep overall `EVIDENCE_STATE=UNKNOWN` without
creating an upload file.

A successful Classic C1 run writes two atomic canonical JSON artifacts:

- `nfl_classic_prior_review_selection_c1_v1` in `classic_selection.json`, with
  exact Entry-ID assignments, legal roster IDs, salaries, prior-only score,
  canonical identity, solver status, immutable hashes and limitations;
- `nfl_classic_slate_coverage_c1_v1` in
  `classic_complete_slate_coverage.json`, with every person, team, position,
  game, salary, activity state, inclusion/exclusion reason, unallocated share,
  conservation totals and smallest evidence action.

The coverage record embeds the selected-evidence gate. Since Session 09 (R28) it is
`nfl_classic_selected_evidence_gate_c1_v3`; v2 stays as written. v3 keeps
`gaps` for what still blocks (synthetic role sources, a selected unavailable
person, a missing or unselectable current role) and adds `activity_gaps`, one
per selected person with no exact-ID official activity row: `person`,
`evidence` `OFFICIAL_ACTIVITY`, `state` (`NO_EXACT_ID_ROW_IN_SUPPLIED_FILE` or
`NO_OFFICIAL_STATUS_FILE`), the `limitation` code `run-slate` names
(`OFFICIAL_STATUS_INCOMPLETE_FOR_SELECTED` or `OFFICIAL_STATUS_REQUIRED`) and
the smallest evidence action. `status` is `BLOCKED` with any gap,
`PASS_WITH_NAMED_LIMITATIONS` with activity gaps only, and `PASS` with neither.
Coverage's `official_status_coverage` is `null` when no official status file
was supplied.

Runtime paths, run IDs, timestamps and solver elapsed seconds are excluded from
these canonical payloads, so identical immutable inputs reproduce both hashes.
`FILE_VALID` describes these two review JSON files only. `EVIDENCE_STATE`,
`MODEL_STATUS=PRIOR_ONLY`, and `RELEASE_DECISION=DO_NOT_UPLOAD` are separate.
`prior_review` itself writes no `DK_REVIEW_ENTRY_*.csv` or `DK_UPLOAD_*.csv` for
C1. Since Session 06 `run-slate` exports C1's `assignments.csv` as a review CSV
(rung 4; § `run-slate` result, baseline first). C2 adds policy/candidates/joint
selection as documented below, and C3 owns readable review, downstream
independent export audit, and exact-template export.

## C2 Classic policy, candidate bank, assignment, and selection audit

`nfl_classic_portfolio_policy_c2_v1` is the only Classic policy source schema.
It binds the exact untouched salary and entry SHA-256 values, draft group,
complete ordered Entry IDs, complete games/teams/people/positions/roster slots,
registered stack-rule set, `classic_prior_points_expected_stat_line_c2_v1`
objective, maximize direction, and seed zero. Search limits are direct JSON
integers: candidate limit, total candidate milliseconds, per-solve milliseconds,
and joint-selection milliseconds. Fractions, percentages, inferred rounding,
unknown fields, duplicate JSON keys, nonfinite values, incomplete identity,
source mutation, and unregistered objective or rule names fail validation.

The validated source is normalized to canonical
`nfl_classic_portfolio_policy_normalized_c2_v1` bytes. All exposure limits use
inclusive direct lineup counts with the exact requested Entry-ID count as the
denominator (since Session 11b, the policy's own bound rows; below):

- a player count is the number of selected lineups containing the exact bound
  underlying person/DK ID;
- a team or game count is the number of selected lineups containing at least
  one member of that exact team or game;
- an exact exclusion gives that person effective maximum zero, with current
  source/participation exclusions taking precedence;
- a group qualifies one lineup when the count of its exact members is inside
  `minimum_players..maximum_players`; its entry bounds count qualifying
  lineups;
- canonical lineup uniqueness is mandatory, and every unordered lineup pair
  must be at or below `max_pairwise_person_overlap`.

Groups and stack rules declare `strength=HARD` or `strength=ADVISORY`. Hard
rules enter the joint portfolio model and are never relaxed. Advisory rules
affect candidate coverage and reporting only. Registered stack values are:

| Rule type | Per-lineup integer value |
|---|---|
| `QB_PASS_CATCHER` | Selected same-team WR/TE count for the selected QB |
| `QB_BRINGBACK` | Selected opponent RB/WR/TE count for the selected QB |
| `RB_DST_PAIR` | Selected RB count whose team also supplies the selected DST |
| `SECONDARY_GAME_CORRELATION` | Count of non-QB games where selected non-DST players cover both teams |

Every stack rule supplies inclusive `minimum_value..maximum_value` per lineup
and `minimum_entries..maximum_entries` across qualifying lineups. Policy
validation checks exact references, ordered integer domains, direct
contradictions, position/skill/player capacity, team/game capacity, exclusions,
and loose uniqueness/overlap capacity before candidate solving.

`nfl_classic_candidate_bank_c2_v1` contains the normalized-policy hash,
requested and produced counts, canonical-unique count, explicit bounded versus
exhaustive state, family/group/stack coverage, every documented stratum and
termination reason, policy-feasible-chain candidate indexes, and every exact
candidate roster with its canonical identity and prior-only central estimate.
Runtime diagnostics separately report elapsed seconds, peak traced Python
bytes, solve count, nodes, maximum reported gap, terminal model status, and
(since Session 08) `limit_incumbent_candidates`.
The bank distinguishes `EXHAUSTIVE_COMPLETION`, `BOUNDED_COMPLETION`,
`BOUNDED_TIME_LIMIT_STOP`, `BOUNDED_SEARCH_LIMIT_STOP`,
`CANDIDATE_BANK_TIMEOUT`, `CANDIDATE_BANK_SEARCH_LIMIT`,
`CANDIDATE_BANK_SOLVER_ERROR`, and `STRUCTURAL_INFEASIBILITY`. A bounded bank
never asserts full-slate optimality.

Since Session 08 a per-candidate solve that a time or search limit
(`kTimeLimit`, `kIterationLimit`, `kSolutionLimit`) stops with a roster
`validate_lineup` accepts keeps it: the candidate records
`source_solver_status` `FEASIBLE_LIMIT`, its model status, gap and nodes, and
counts toward its stratum like any other. A bank stopped by its total budget, or
by a limit that left no roster, is `BOUNDED_TIME_LIMIT_STOP` or
`BOUNDED_SEARCH_LIMIT_STOP` when it holds at least the entry count and a
`POLICY_FEASIBLE` witness, and is not blocking; without either it is
`CANDIDATE_BANK_TIMEOUT` or `CANDIDATE_BANK_SEARCH_LIMIT` as before, and those
two still block. A solver error always blocks, and so does a roster the
optimizer itself rejected as illegal, whatever the model status
(`ILLEGAL_SOLVER_ROSTER`, `CANDIDATE_BANK_SOLVER_ERROR`).

The joint MILP chooses exactly the Entry-ID count from the actual canonical
bank under all hard player/team/game/group/stack, uniqueness, and pair-overlap
bounds, starting from the bank's `POLICY_FEASIBLE` witness as a MIP start when
there is one (`mip_start` `POLICY_FEASIBLE_WITNESS`; the witness is a feasible
point of the same model). Two solver statuses are accepted.
`OPTIMAL_ACTUAL_CANDIDATE_BANK` means optimal only over that reported bank, with
`optimality_scope` `ACTUAL_CANDIDATE_BANK`. `FEASIBLE_LIMIT_ACTUAL_CANDIDATE_BANK`
(Session 08, shared with SD3) means a time or search limit stopped the solve
holding a valid integer incumbent that passed the optimum's own integrality,
count and bound checks; it reports its gap and nodes, its `optimality_scope` is
null, it is never called optimal, and it travels as the `S` limitation
`PORTFOLIO_SELECTION_LIMIT_INCUMBENT`. A C2 limit never delivers less than the
witness: when HiGHS's incumbent scores below it, or HiGHS stops at a limit with
no incumbent (as it can with presolve off and a limit reached early), the
witness is the incumbent, and `incumbent_source` says `POLICY_FEASIBLE_WITNESS`
rather than `JOINT_SOLVE`. The selection record's `objective_limits` says
`OPTIMAL_ONLY_OVER_ACTUAL_CANDIDATE_BANK` for an optimum and
`LIMIT_INCUMBENT_NOT_PROVEN_OPTIMAL_OVER_ACTUAL_CANDIDATE_BANK` for an
incumbent. No gap threshold applies: the incumbent is
legal under every hard bound, and a threshold would be a construction
preference the lock-clock ruling relaxes. `MODELED_BANK_INFEASIBILITY` applies
only to an exhaustive modeled bank; `INCOMPLETE_BANK_EXHAUSTION` is the distinct
bounded-bank result. A limit with no valid incumbent keeps its code
(`PORTFOLIO_SELECTION_TIMEOUT`, `PORTFOLIO_SELECTION_SEARCH_LIMIT`), and
non-optimal, invalid-integrality and solver-error results fail closed. Selected
lineups are paired one-to-one with `entry_ids` in exact template order; cycling
is prohibited.

**Subset binding (a rule change dated Session 11b, 2026-09-24; no new version).**
`bindings.entry_ids` may be the plan's fillable blank rows (§ Entry groups) or a
non-empty subset of them in template order, each once. The validator takes the
fillable rows as the rows a policy may bind; a bound row that is prefilled,
partly filled, unresolved, unknown, repeated or out of order is
`CLASSIC_POLICY_ENTRY_ID_BINDING_MISMATCH` (`V`, `policy_binding`), and an empty
or malformed fillable list is still `CLASSIC_POLICY_ENTRY_SET_INVALID`. The
bound list is the denominator: every integer bound's domain, the default bounds,
the template's default stack rules and `default_search_limits` count it. The
document's shape is unchanged, every policy valid before stays valid with the
same meaning, and a reader that predates the rule refuses a subset (it compared
the list with every fillable row). A policy that binds every fillable row gives
the same file as before, byte for byte.

Rule change (Session 11c, 2026-09-25): `run-slate` and `prior_review` run a
Classic subset (the `CLASSIC_POLICY_SUBSET_UNSUPPORTED` refusal and its
registry entry are gone). C2's joint solve fills the bound rows; then C1 fills
the fillable rows the policy leaves unbound, every C2 lineup and prefilled
roster a no-good, under the run's own exclusions only (a policy's exclusions
and zero caps bind its rows). The fill is all or nothing, as SD3's is: one that
runs out of distinct lineups raises `SOLVER_RETURNED_NO_LINEUP` with
`stage=UNBOUND_FILL` and the baseline stays the file. The selection report's
`unbound_fill` records it, with `source: "C1"`. Each fill solve
gets what the policy's declared bank and joint-solve limits leave of the
window, split across its solves, from 0.5 s to 10 s. `classic_assignment.json`
and the C2 audit keep their versions and cover the policy's rows only; the C1
rows are C3's to check. `classic_selection.json` keeps
`nfl_classic_prior_review_selection_c2_v1`: its `entry_assignments` are the
policy's rows, as before, and `assignments_by_entry_id` and `lineups` every
filled row, which is where C3 reads the C1 rows from.

These are new values of existing v1 fields, not a new version (Session 08): no
key is added to or removed from `nfl_classic_candidate_bank_c2_v1` or
`nfl_classic_portfolio_assignment_c2_v1`, and every value an existing artifact
can hold keeps its meaning. A reader that predates the change fails closed on
the new bank and joint statuses, since C3 refused every bank status but the two
completions and every joint status but the optimum. It does accept a candidate
whose `source_solver_status` is the new `FEASIBLE_LIMIT` inside a completed
bank, because C3 never read that label; that is safe, since C3 re-validates
every selected roster from its exact IDs and the label claims nothing about
legality. The selection report's `mip_start` and `incumbent_source` and the
bank report's `limit_incumbent_candidates` are runtime diagnostics beside the
artifact, not artifact keys.

A successful governed C2 run writes three additional atomic canonical JSON
artifacts before extending the C1 selection and coverage records:

- `classic_candidate_bank.json` using `nfl_classic_candidate_bank_c2_v1`;
- `classic_assignment.json` using
  `nfl_classic_portfolio_assignment_c2_v1`, bound to the normalized policy and
  candidate-bank hashes with ordered exact Entry-ID/roster pairs;
- `classic_portfolio_audit.json` using
  `prior_only_classic_portfolio_audit_c2_v1`.

The independent selection audit reparses the canonical normalized policy and
assignment, verifies source/normalized policy, salary, entry, prior, projection,
current-evidence, candidate-bank and assignment hashes, and recomputes complete
identity, roster legality, every hard integer count, exclusions, canonical
uniqueness and every pairwise overlap from selected roster IDs. Only audit
`PASS` extends `classic_selection.json` to
`nfl_classic_prior_review_selection_c2_v1` and coverage to
`nfl_classic_slate_coverage_c2_v1`. These remain machine-readable review JSON,
not DraftKings templates. C2 creates no `assignments.csv`,
`DK_REVIEW_ENTRY_*.csv`, `DK_UPLOAD_*.csv`, HTML, or readable workbook; C3 owns
the downstream independent export audit, readable surfaces, and exact-template
export. `FILE_VALID`, `EVIDENCE_STATE`, `MODEL_STATUS=PRIOR_ONLY`, and
`RELEASE_DECISION=DO_NOT_UPLOAD` remain separate truths.

## C3 Classic downstream audit, readable review, and exact-template export

C3 runs only for a governed C2 Classic prior-review result. The downstream
auditor does not import or trust the C2 candidate producer, selector, or audit
implementation and does not accept their in-memory objects as authority. It
strictly reads the immutable salary and entry CSVs plus the canonical source
and normalized policy, candidate bank, assignment, C2 portfolio audit,
selection, complete-slate coverage, selected-score snapshot, source ledger,
priors/projections, identity, current official activity, current offensive-role
manifest and every bound role-source capture.

Every tracked input has an expected SHA-256 and is hashed at four named
boundaries: `intake`, `immediately_before_export`, `after_final_write`, and
`immediately_before_render`. Unknown fields, duplicate JSON keys, noncanonical
JSON bytes, nonfinite numbers, missing expected hashes, or any hash change fail
closed. The C3 audit independently recomputes:

- exact Classic mode, draft group, games, teams, opponents, people, positions,
  roster slots, ordered Entry IDs, and blank-cell authority;
- candidate membership, ordered assignment, exact nine-slot roster legality,
  $50,000 salary cap, two-game rule, exclusions, and selected prior-only score;
- every direct player/team/game/group/stack count and limit, canonical lineup
  uniqueness, and every unordered pairwise underlying-person overlap; and
- selected exact-ID official activity plus selected current-team offensive-role
  evidence, including source paths, source hashes, observation and expiry.
  Since Session 09 (R28) the official status file is optional: a selected
  person with no row, or a run with no file, is a named limitation, while a
  row that is not `ACTIVE` still refuses, and so does any disagreement between
  C3's re-read and the coverage or gate about who lacks a row
  (`CLASSIC_C3_SELECTED_ACTIVITY_COVERAGE_MISMATCH`), or a coverage that names a
  file the review does not track (`CLASSIC_C3_OFFICIAL_STATUS_ARTIFACT_REQUIRED`).

Since Session 11c the policy may bind a subset of the fillable rows, and C1
filled the rest (§ C2). C3 takes the policy's rows from `classic_assignment.json`
and the C1 rows from `classic_selection.json`'s `assignments_by_entry_id`, whose
rows outside the policy must be exactly the unbound rows
(`CLASSIC_C3_UNBOUND_ROWS_MISMATCH`, `V`, `audited_selection`). Candidate-bank
membership and identity, every count and bound, the policy's exact exclusions,
the pairwise overlap cap, the comparison with the C2 audit and the exposure
denominator cover the policy's rows. Roster legality, the selection record's
roster, salary and score, canonical uniqueness (R29, whatever the policy flag
says when rows are unbound), the prefilled repeat, official activity, role
evidence and the template bytes cover every filled row, and so do the run's own
exclusions: no filled row may hold a person the bound coverage's `pool_coverage`
names with any reason but `SELECTABLE`
(`CLASSIC_C3_SELECTED_PERSON_EXCLUDED_BY_RUN`, `V`, `operator_restriction`). A
policy binding every fillable row passes the same checks as before and gives the
same CSV bytes.

C3 re-validates the source policy with the run's own exclusions, the people the
normalized policy marks `SOURCE_OR_PARTICIPATION_PRECEDENCE` (fixed in Session
11c). Intake validates with them, so a re-validation without them could never
reproduce the normalized bytes: every C2 run that excluded anyone (an official
inactive, an operator exclusion) ended
`CLASSIC_C3_SOURCE_NORMALIZED_POLICY_DISAGREEMENT` and shipped the baseline.
The marked people only add zero caps, and the canonical-bytes comparison still
binds the rest.

Only `ENFORCED_AND_INDEPENDENTLY_AUDITED`, C2 audit `PASS`, bank status
`EXHAUSTIVE_COMPLETION`, `BOUNDED_COMPLETION`, `BOUNDED_TIME_LIMIT_STOP` or
`BOUNDED_SEARCH_LIMIT_STOP`, a `POLICY_FEASIBLE` chain, and joint status
`OPTIMAL_ACTUAL_CANDIDATE_BANK` over `ACTUAL_CANDIDATE_BANK` or (Session 08)
`FEASIBLE_LIMIT_ACTUAL_CANDIDATE_BANK` with a null optimality scope can reach C3
publication. A limit incumbent that claims the bank's optimality scope is
`CLASSIC_C3_C2_OPTIMALITY_SCOPE_MISMATCH`. A limit-stopped bank or a limit
incumbent adds `CANDIDATE_BANK_STOPPED_AT_LIMIT:...` or
`PORTFOLIO_SELECTION_LIMIT_INCUMBENT:...` to the export audit's and the readable
review's `limitations`, and `run-slate` reports each as an `S` delivery
limitation (family `search_budget`). A bounded bank remains explicitly
incomplete and never implies full-slate optimality.

Successful C3 publication is atomic and adds:

| Artifact | Contract |
|---|---|
| `classic_review_export_audit.json` | Canonical `prior_only_classic_export_audit_c3_v3` since Session 11c (v2 and v1 stay as written). v3 adds `bound_entry_ids`, `unbound_entry_ids`, `row_sources` (each filled row, `POLICY` or `C1`) and the `checks_run` item `POLICY_AND_C1_ROW_PARTITION_AND_THE_RUN_S_EXCLUSIONS_OVER_EVERY_ROW`; `entry_ids` and `output.entries` are every filled row, `recomputed`'s counts and `pairwise_person_overlap` the policy's rows, and `recomputed.canonical_lineups` every filled row. v2 since Session 09: every boundary hash, recomputed fact, exact output hash, status, limitations, truths, and one next action. v2 reports `recomputed.selected_activity` as `PASS` or `INCOMPLETE` (v1 always wrote `PASS`), adds `recomputed.selected_activity_without_row`, lists `SELECTED_CURRENT_ACTIVITY_AND_ROLE_EVIDENCE` in `checks_run` only when every selected person has an `ACTIVE` row (otherwise `SELECTED_CURRENT_ROLE_EVIDENCE_AND_NO_SELECTED_NON_ACTIVE_ROW`), and names the gap in `limitations` as `OFFICIAL_STATUS_INCOMPLETE_FOR_SELECTED:NO_EXACT_ID_ROW_IN_SUPPLIED_FILE:<n>_of_<m>_selected_people` or `OFFICIAL_STATUS_REQUIRED:NO_OFFICIAL_STATUS_FILE_SUPPLIED:<n>_of_<m>_selected_people` |
| `DK_REVIEW_ENTRY_<label>.csv` | Exact reserved-entry template bytes with only nine previously blank authorized roster cells rewritten for each exact Entry ID in template order |
| `prior_only_readable_review.json` | Canonical `prior_only_readable_review_classic_c3_v2` display data independently reconstructed from the accepted artifacts, since Session 11c (v1 stays as written and was never produced for a subset policy). v2 adds each entry's `source` (`POLICY` or `C1`) and `unbound_rows`: `null` when the policy binds every fillable row, otherwise the C1 rows' `entry_ids`, `source`, `basis`, `checks`, `person_exposure` and `maximum_person_overlap_with_any_filled_row` (C1 cuts only exact rosters, so no overlap cap covers them). `exposure.entry_count_denominator` is the policy's rows; `reconciliation.entry_count` is every filled row |
| `prior_only_readable_review.html` | Self-contained escaped rendering of the canonical readable JSON |
| `NFL_DFS_Cowork_Review_<run-id>.xlsx` | Eight sheets: Run Control, Evidence Paste, Portfolio, QA, Upload, Exposure, Review Evidence, and Artifacts |

The CSV writer preserves BOM/encoding, header, line endings, row order,
quoting, physical-line geometry, unrelated rows, contest facts, and every
non-roster byte. It reparses and byte-diffs both proposed and final bytes and
binds the final SHA-256 into the audit, readable package, and run record. A
partial write, existing/stale target, mismatched Entry ID, prefilled roster
cell, unauthorized row, mutation, audit failure or post-write disagreement
removes or withholds all new C3 artifacts. A failure of the readable review
alone, after the export and its audit passed (R28, Session 05), keeps both once
they re-verify by hash, reparse and the `DK_UPLOAD` check
(`CLASSIC_C3_FINAL_OUTPUT_*`), removes only the JSON and HTML, and raises
`ClassicReviewPresentationError` with the presentation code, or
`CLASSIC_C3_READABLE_RENDER_FAILED` for an exception that carries none.
`prior_review` lists the kept pair; `run-slate` classifies the failure as
below.

The readable surfaces enumerate every exact Entry ID and roster ID, underlying
person, slot, game/team/opponent, salary, lineup total/remaining salary,
prior-only central estimate, player/team/game/group/stack counts and limits,
every overlap pair, exclusions, unallocated volume, evidence observation,
artifact path/hash, candidate-bank status/completeness, joint solve scope,
independent audit state, and all four release truths. HTML markup is escaped;
spreadsheet-active prefixes are written as inert display values. A readable
`PASS` proves only that the display reconciles to the exact accepted artifacts.

`FILE_VALID` describes the exact C3 review artifacts only.
`EVIDENCE_STATE` remains separately derived. `MODEL_STATUS=PRIOR_ONLY` and
`RELEASE_DECISION=DO_NOT_UPLOAD` remain invariant. C3 never creates
`DK_UPLOAD_*.csv` and never calls ownership, field, duplication, payout,
economics, EV, production portfolio selection, C4, C5, or Q2-Q5 paths.

`config/classic_c3_scale_acceptance_v1.json` registers the full supplied
719-person/24-team/12-game fixture matrix before execution. Each 1/3/20/150
case records candidate request/production, bank completeness/status, family and
policy coverage, solve status, elapsed time, nodes, gap, process peak RSS and
traced Python peak memory. The objective is explicitly test-only deterministic
fixture rank, never model performance, and `uses_draftkings_appg=false`. The
complete package is copied to a separate short path and rerun; canonical source
and copy hashes must match for policy, bank, assignment, C2/C3 audit, selection,
coverage, selected-score snapshot, readable JSON/HTML, and review CSV. Runtime
metrics and workbook container timestamps remain outside canonical bytes.

## SD2 Showdown offensive history and current roles

`offensive_role_evidence_json` is an optional adjacent package; SD1's
`role_evidence_json` retains its kicker-specific v1 semantics. Cowork captures
approved supporting artifacts, prepares this manifest, adds its path to the
generated request and reruns. Ben still supplies only salary and reserved-entry
CSVs. Numerical fields must never be authored from an LLM estimate or prose.

The `nfl_offensive_role_evidence_v1` manifest contains:

| Field | Contract |
|---|---|
| `schema_version` | `nfl_offensive_role_evidence_v1` |
| `transformation_version` | Exactly `offensive_explicit_team_shares_v1` |
| `salary_sha256`, `game_id` | Exact current salary bytes and single game |
| `sources` | Nonempty SD1-style captured-source records, described below |
| `declarations` | Zero or more unique current-team numerical allocations |
| `facts` | Zero or more unique underlying-person qualitative facts |

Sources use `path` (`sources/<sha256>.txt`), `sha256`, approved HTTPS
`source_uri`, `observed_at`, `captured_at`, `expires_at`, `license_decision`,
`parser_version`, the exact transformation version above, `support_kind`,
`supporting_excerpt` and a strict Boolean `synthetic`. SD1's captured-source
validator enforces policy, content addressing, relative-path confinement, hash
integrity, excerpt presence and aware ordered timestamps. Sources must already
be observed/captured, and remain unexpired. No URL-only evidence, renewed expiry
or allowlist exception is accepted. Every source must be used. Synthetic
fixtures are reported as `TEST_ONLY_SYNTHETIC_EVIDENCE` and remain `UNKNOWN`.
The offensive excerpt limit is 100,000 characters to accommodate a complete
current-team declaration; SD1's smaller kicker-excerpt limit is unchanged.

A numerical declaration has `team`, `game_id`, `source_sha256`, `totals`,
`unallocated`, and `recipients`. Each recipient binds `underlying_id`,
`cpt_dk_id`, `flex_dk_id`, `shares`, and optionally `receiving_efficiency`.
Every `shares`, `totals` and `unallocated` object contains exactly these five
unit-fraction fields: `qb_attempt_share`, `carry_share`, `target_share`,
`rushing_td_share`, `receiving_td_share`. All must be finite JSON numbers in
`[0,1]`; Booleans and numeric strings are rejected. Each total must be exactly
1.0. Recipient sums plus explicitly unallocated shares must equal each total
within absolute tolerance `0.000001` (no relative tolerance). The engine does
not normalize the declaration or silently allocate the remainder.

All eligible offensive people on a declared team must be listed, except
explicit nonparticipants. Position masks match the existing opportunity
contract. Only QBs receive passing attempts, and only RB/WR/TE receive targets
or receiving touchdowns. Each team declaration replaces all five share groups
before scoring. A zero allocation excludes the person from selection without
claiming inactivity. Positive recipients excluded by salary status, official
inactive evidence, operator exclusions or explicit nonparticipation invalidate
the whole allocation and require refreshed evidence.

`support_kind=NUMERICAL_ALLOCATION` requires the captured excerpt to be a JSON
object identical to the declaration with `source_sha256` omitted. This is the
registered deterministic identity transformation; there is no freeform
numerical extractor. `receiving_efficiency`, when supplied, is an object with
`catch_rate` in `[0,1]` and `yards_per_target` in `[0,30]`, subject to the same
source-content equality check. Positive targets without an observed receiving
efficiency basis require these explicit captured values. Thus a rookie cannot
receive made-up efficiency after a role adjustment. These strict source formats
are intentionally narrow; a live compatible numerical source has not yet been
demonstrated, and no broader scraper or transformation is implied.

A qualitative fact has `team`, `game_id`, the three exact identity fields,
`source_sha256`, and `fact`. `support_kind=QUALITATIVE_FACT` supports only exact
captured sentences of the following registered forms, where name, team and
game ID come from the salary contract:

```text
<name> is the starter for <team> in <game_id>.
<name> is the backup for <team> in <game_id>.
<name> has an unresolved role change for <team> in <game_id>.
<name> will not participate for <team> in <game_id>.
```

They map respectively to `NAMED_STARTER`, `NAMED_BACKUP`,
`MATERIAL_ROLE_CHANGE`, and `EXPLICIT_NONPARTICIPATION`. A different phrase needs
a separately validated transformation in future work; do not rewrite a capture
to fit. Starter/backup/change facts require a supported numerical allocation
before selection. They never imply any snap, route, target or carry share.

Producer coverage stores `offensive_history_by_person` with version
`offensive_current_team_history_v1`, exact current team/provider team,
historical teams, season, prior/current-team row counts, incompatible-transfer
flag and receiving-efficiency coverage. Blank required historical counts are
missing, not observed zeros. `OBSERVED_HISTORY` is the additional baseline state
for nonzero current-team historical support. A legacy frozen prior package
without complete SD2 coverage must be rebuilt (`OFFENSIVE_HISTORY_COVERAGE_REQUIRED`).

The current-role report contains exactly one finding per offensive person:

| State | Selection treatment |
|---|---|
| `OBSERVED_HISTORY_ZERO` | Exclude; historical zero does not establish current nonparticipation |
| `MISSING_HISTORY` | Exclude with zero share (2026-09-10); no prior-season row exists anywhere, so there is no source-bound number to carry. The person is named with FLEX/CPT salary in `pool_coverage` (`OFFENSIVE_ROLE_GATE_EXCLUDED:OFFENSIVE_MISSING_HISTORY`). A person with no prior record at all still blocks (`OFFENSIVE_PRIOR_ROW_MISSING`) |
| `TRANSFER_PRIOR_UNVERIFIED` | Keep as a diagnostic (2026-09-10): the producer carried the person's own prior-team share (see below); `EVIDENCE_STATE=UNKNOWN`, never a role fact, cannot certify |
| `TRANSFER_PRIOR_ZERO` | Exclude: the person's own prior-team share was zero in every column |
| `CURRENT_ROLE_UNKNOWN` | Block a transfer whose frozen package carries no `transfer_prior` (rebuild the package), or any declared material change; unchanged positive history may remain an explicitly unconfirmed diagnostic |
| `EXPLICIT_NONPARTICIPATION` | Exclude before allocations; cannot be reactivated by role evidence |
| `SOURCE_SUPPORTED_ADJUSTMENT` | Use the validated current-team allocation; zero-share people remain excluded |

Transfer prior (`transfer_prior_own_old_team_share_v1`, 2026-09-10, R17). For a
person whose prior-season rows all sit on other teams, the producer computes his
own share of each old team's volume, per raw column, over the weeks he had a
row: own count divided by the old team's count summed over all of that team's
players in those weeks, from the same frozen `player_stats` bytes as every other
share. That share enters the current team's pool normalization as a pseudo-count
equal to the share times the current team's incumbent pool total for the column,
so incumbents scale by `1/(1+Σs)` and the transfer receives `s/(1+Σs)`.
Receptions and receiving yards are scaled from the pseudo-targets by his own
catch rate and yards per target. The history entry records `transfer_prior` with
`basis` (`OWN_OLD_TEAM_SHARE` or `OWN_OLD_TEAM_SHARE_ZERO`), old teams and week
count, own and old-team counts, `own_old_share`, own efficiency and the injected
`pseudo_counts`. The record keeps `EVIDENCE_STATE=UNKNOWN` and the history state
`CURRENT_ROLE_UNKNOWN`; the gate reports it as `TRANSFER_PRIOR_UNVERIFIED`. It is
a cold-start prior from the person's own source-bound history, not a current-team
role, not qualitative evidence turned into a number, and it does not change
`PRIOR_ONLY` / `DO_NOT_UPLOAD`. A qualitative fact naming the person still
blocks. Rookies have no such number; a registered rookie prior from approved
draft or combine artifacts is open work.

Each finding retains `history_state`, `history_basis`, `declared_fact`, before/
after shares, exact IDs, selection action and smallest next evidence action.
The report also records coverage, assumptions, declared totals, unallocated
volume, captured metadata, hashes and original expiry. Unchanged historical
shares remain unconfirmed; excluding people leaves their volume unallocated,
so no unsupported backup inherits it. This is an understated retained-volume
diagnostic, not a guaranteed lower bound on fantasy points or a current-role
forecast. Historical `role_capacity` is never a forward ceiling.

An unresolved transfer the market prices far above his prior (the P1 gate,
`unresolved_material_role_change_gate_v2` since Session 09) no longer stops the
run (R28, Ben 2026-09-23). Scoring adds him to the resolution's excluded people,
his finding's selection action becomes `EXCLUDE` with `material_role_change`
`OFFENSIVE_UNRESOLVED_MATERIAL_ROLE_CHANGE`, `excluded_by_finding` lists him
under that key, `evidence_state` is `UNKNOWN`, and `material_role_change_exclusions`
carries one code per person, which `run-slate` names as a `P` limitation
(family `unresolved_role_change`). Every prior stays as scored; v1 raised
instead.

Selection/scoring reports retain this under `offensive_roles`; failed selection
retains it directly under `prior_review_reports.offensive_roles`. Source/manifest
bytes and freshness are rechecked after selection and immediately before export.
The immutable manifest and its `sources/` directory travel with snapshots and
copied packages. Invalid evidence writes no new `DK_REVIEW_ENTRY` CSV and leaves
earlier outputs intact. The prior-review path always reports independent
`FILE_VALID`, `EVIDENCE_STATE`, `MODEL_STATUS=PRIOR_ONLY` and
`RELEASE_DECISION=DO_NOT_UPLOAD`. SD2 does not change upload gates or W3's simulator.

## SD3 Showdown portfolio policy

`portfolio_policy_json` is an optional `nfl_showdown_portfolio_policy_v1`
artifact. It is a user preference contract, not evidence, calibrated risk, or a
claim of optimal tournament behavior. It binds the exact immutable salary bytes,
the one Showdown game, the complete salary person/CPT/FLEX identity map, and
every requested Entry ID in template order. The complete shape is:

```json
{
  "schema_version": "nfl_showdown_portfolio_policy_v1",
  "bindings": {
    "salary_sha256": "<64 lowercase hex characters>",
    "game_id": "AWAY@HOME",
    "entry_ids": ["<Entry ID 1>", "<Entry ID 2>"],
    "person_identities": [
      {
        "underlying_id": "TEAM|POSITION|DraftKings name",
        "cpt_dk_id": "<exact CPT row ID>",
        "flex_dk_id": "<exact FLEX row ID>"
      }
    ]
  },
  "controls": {
    "fraction_unit": "FRACTION_0_TO_1",
    "max_combined_person_exposure": {
      "default_fraction": null,
      "overrides": []
    },
    "max_captain_exposure": {
      "default_fraction": null,
      "overrides": []
    },
    "excluded_people": [],
    "max_pairwise_person_overlap": null,
    "require_unique_lineups": true
  }
}
```

Every override and excluded-person item repeats the exact three identity fields
shown above; an override also has a numeric `fraction`. Names, salaries, or one
role ID are never used to infer the other identity. Unknown, duplicated, missing,
cross-person or CPT/FLEX-reversed identities fail. `entry_ids` is the plan's
fillable blank rows (§ Entry groups) or, since Session 11b, a non-empty subset
of them in template order, each once; a duplicate, reordered, prefilled, partly
filled, unresolved or unknown row is `PORTFOLIO_POLICY_ENTRY_ID_BINDING_MISMATCH`
(`V`), with `PORTFOLIO_POLICY_DUPLICATE_ENTRY_ID` for a repeat. The request's
`lineup_count` still describes the file, every fillable row, and
`PORTFOLIO_POLICY_LINEUP_COUNT_MUST_MATCH_ENTRIES` still refuses any other
value. This is a rule change dated Session 11b, not a new version: the shape is
unchanged, a policy valid before keeps its meaning, and an older reader refuses
a subset.

Fractions are JSON numbers in `[0,1]`, with the required unit
`FRACTION_0_TO_1`. Booleans, numeric strings, nonfinite numbers, negative values,
bare values such as `50`, and any alternative unit fail. The denominator is the
policy's own bound entries (every fillable row, or its subset since Session
11b; 0.5 over 4 bound rows of 10 fillable rows allows 2). Each integer maximum is
`floor(fraction * bound_entry_count)` using exact decimal arithmetic:

| Entries | Fraction | Integer maximum |
|---:|---:|---:|
| 2 | `0.49` | 0 |
| 2 | `0.50` | 1 |
| 2 | `1.00` | 2 |
| 3 | `0.66` | 1 |
| 3 | `0.67` | 2 |

An omitted exposure object, omitted `default_fraction`, or explicit `null`
means no additional cap (effective maximum 100% of requested entries). Numeric
zero means zero entries; numeric one means every requested entry. A per-person
override replaces its default for that exact person. Captain count is a subset
of combined-person count. When a declared Captain maximum is looser than the
combined maximum, normalization reports
`PORTFOLIO_POLICY_CAPTAIN_TIGHTENED_BY_COMBINED` and uses the stricter combined
integer maximum. It never relaxes the combined control. Policy exclusions and
existing salary-status, official-activity, operator, and participation
exclusions take precedence and make both maxima zero; the normalization report
names that tightening.

Canonical Showdown identity is the exact underlying Captain person plus the
sorted set of five underlying FLEX people. FLEX order is irrelevant; changing
the Captain changes the canonical lineup. Pairwise overlap compares the two
six-person underlying-person sets regardless of role. Combined exposure counts
a person at most once per entry. `max_pairwise_person_overlap=null` means no
additional overlap cap (effective six); otherwise it is an integer from zero
through six. `require_unique_lineups` defaults to `true` when omitted. Repeated
Captains are not implicitly prohibited: SD4 will govern them only through the
explicit effective Captain maxima.

Validation emits `nfl_showdown_portfolio_policy_normalized_v1`, an exact-decimal
canonical serialization and a stable normalized SHA-256. The run also retains
the exact source-policy SHA-256. Whitespace and object/list ordering that do not
change semantics leave the normalized hash stable, while immutable replay still
requires the same source bytes, salary bytes, person identities, and Entry IDs.
Necessary person-slot, Captain-slot, two-team, salary, unique-lineup and
pairwise-overlap capacity checks return named findings with a smallest next
action. These checks do not run a solver and are not proof that the full policy
is feasible.

SD4 enforces this contract only on the Showdown `prior_review` profile. The
selector consumes the already-normalized exact integer maxima; it never reparses
fractions, changes the all-entry denominator or rounds a zero cap upward. It
generates a bounded bank of legal lineups after all source, participation,
official-inactive, operator, kicker-role and offensive-role exclusions, then
solves one deterministic MILP over that actual bank for the exact requested
Entry-ID count. The MILP enforces combined-person and Captain maxima, policy
exclusions, configured pairwise overlap and canonical uniqueness. Repeated
Captains are legal only when their explicit effective maximum permits them.

**The unbound rows (Session 11b).** When the policy binds a subset, its joint
solve fills its own rows first; then sequential Showdown (the no-policy
selector) fills the fillable rows it leaves unbound, in template order, with
every policy lineup and every preserved prefilled roster as a no-good and its
own rules among the fill (a distinct Captain per lineup until the pool runs out,
the request's `max_person_overlap`). The run's own exclusions bind every row
(request, DraftKings status, official inactive, kicker and offensive role); the
policy's exclusions and caps bind only its rows. Each fill solve's limit is what
the bank and joint solve leave of the window, split across its solves, at most
10 s and at least 0.5 s. A fill that runs out of distinct lineups raises
`SOLVER_RETURNED_NO_LINEUP` (`stage=UNBOUND_FILL`, `V`, `distinct_lineups`) and
the review delivers nothing: all or nothing, as before, with the baseline the
file and the reason named. The selection report's policy section (counts,
exposure, overlap, `selected_lineup_count`) covers the policy's rows; its
`unbound_fill` section records the fill (`source`, `lineups`, `lineup_indexes`,
`no_good_rosters`, `exclusions`, `differentiation`, `person_exposure`), and the
review's `row_sources` maps every filled row to `POLICY` or
`SHOWDOWN_SEQUENTIAL`.

The bank is generated in policy-aware strata with the same lineup MILP, exact
no-good cuts and deterministic vanishing perturbation throughout. Captain
strata pin one eligible Captain row at a time, in descending CPT prior order,
and enumerate its best `k` lineups until the seeded Captains' summed effective
Captain maxima cover the entry count plus two spare slots, with
`k = ceil(entries / seeded) + 1`. Exclusion strata enumerate the best
`entries - combined_max + 1` lineups without each person whose combined
maximum is below the entry count, skipped when the bank already holds that
many lineups without them. A chain stratum then walks the policy greedily,
retiring a person's rows once its combined or Captain maximum is reached and
applying the configured pairwise overlap against every earlier chain lineup,
so the joint MILP always receives at least one candidate portfolio that is
legal under every cap; its slots are reserved while the earlier strata run.
The remaining budget is the plain top-K fill. Candidates are deduplicated by
canonical identity across strata, and the report lists per-stratum targets,
enumerated and added counts and each stratum's terminal state; a sub-problem
that runs out of legal lineups (for example a person who cannot legally
captain) is recorded as `MODEL_INFEASIBLE`, not raised. Requests without a
policy keep the plain top-K enumeration.

Bounds scale with the requested entry count: `max(32, 4 x entries)` canonical
candidates, `max(30 s, 2 s x entries)` of total generation time, two seconds
per lineup solve and `max(10 s, 1 s x entries)` for the joint solve. This is
still a bounded search over an actual bank, not a full-slate enumeration.
Reports distinguish `COMPLETE_MODELED_BANK` from
`CANDIDATE_LIMIT_REACHED_INCOMPLETE`, candidate time/search limits and solver
errors. Since Session 08 a lineup solve a time or search limit stops with a
legal roster keeps it (`source_solver_status` `FEASIBLE_LIMIT`, counted in
`limit_incumbent_candidates`); a bank a limit stops with no roster, or whose
total budget runs out, still blocks under `CANDIDATE_BANK_TIME_LIMIT` or
`CANDIDATE_BANK_SEARCH_LIMIT`, because SD3 has no jointly solved witness to
show the kept bank can fill the entries. An optimal result is explicitly scoped
to the actual candidate bank. A joint solve a time or search limit stops with a
valid integer incumbent returns it as `FEASIBLE_LIMIT_ACTUAL_CANDIDATE_BANK`
(Session 08, the C2 name) after the optimum's own integrality and count checks,
with its gap and nodes and no optimality scope; the independent audit then
checks it like any selection, and `run-slate` names it
`PORTFOLIO_SELECTION_LIMIT_INCUMBENT`. Without an incumbent the codes stay
`PORTFOLIO_SELECTION_TIME_LIMIT` and `PORTFOLIO_SELECTION_SEARCH_LIMIT`.
Only an infeasible joint MILP over a bank whose fill enumeration ended in a
proven lineup-model `INFEASIBLE` state is `MODELED_BANK_INFEASIBLE_PROVEN`;
infeasibility over a bounded incomplete bank is
`CANDIDATE_BANK_EXHAUSTED_INCOMPLETE`, never a full-slate mathematical claim.

Assignment never cycles for policy-bearing requests. The output must retain the
exact policy Entry-ID order once each; `assignments.csv` holds every fillable row
in template order, the policy's and the fill's. Immediately before export, an independent
audit strictly reparses the canonical normalized-policy artifact, re-reads the
assignment artifact and recomputes DraftKings legality, canonical lineup
identities, combined-person counts, Captain counts, uniqueness and every pairwise
underlying-person overlap from exact roster IDs. It uses the independently read
limits and binds the current salary, entry, source-policy, normalized-policy and
assignment bytes to their SHA-256 values; it reconciles, but never trusts,
selector summaries. Since Session 11b the audit (`prior_only_showdown_portfolio_audit_sd4_v1`,
unchanged) covers the policy's rows: its entry IDs, counts, caps, uniqueness and
overlap are theirs, and the artifact's other rows must be exactly the unbound
rows (`PORTFOLIO_AUDIT_ASSIGNMENT_ARTIFACT_MISMATCH` otherwise). The readable
review checks the rows the fill wrote (§ SD5).

Only `enforcement_status=ENFORCED_AND_INDEPENDENTLY_AUDITED` may write a new
`DK_REVIEW_ENTRY` CSV. Invalid policies, the unsupported diagnostic profile,
necessary-capacity failures, timeout/search/solver states without a valid
incumbent, incomplete-bank
exhaustion, assignment coverage/order failures, audit disagreement or artifact
mutation preserve earlier outputs and write no new review CSV. Every outcome
remains `MODEL_STATUS=PRIOR_ONLY` / `RELEASE_DECISION=DO_NOT_UPLOAD`; an audited
review file is not an upload package or an economics/model-quality claim.
Requests without a policy retain their SD1/SD2 selection and assignment behavior.

## SD5 prior-only readable review

A successful Showdown `prior_review` creates canonical
`prior_only_readable_review.json` with schema
`prior_only_readable_review_sd5_v2` (since Session 11b; v1 below), a
self-contained escaped HTML rendering, and an extended review workbook. This is a presentation contract, not a new
selection, evidence, model or release contract. The JSON records:

- all four independent release truths and the explicit prior-only warning;
- exactly one next operator action and every named blocker;
- `reconciliation.status=PASS` with basis
  `INDEPENDENT_EXACT_BYTE_REPARSE_AND_RECOMPUTATION`;
- each requested Entry ID in original order, contest metadata, exact CPT/FLEX
  DraftKings roster IDs, underlying-person IDs, names, teams, positions, slot
  and lineup salaries, remaining salary, prior-only central estimates,
  official-activity state and named role findings;
- actual combined-person and Captain counts and percentages, exact integer
  maxima, exclusions, canonical uniqueness, configured/effective overlap and
  every requested-entry pair's actual underlying-person overlap;
- source, expiry, model-omission and role observations; and
- portable artifact paths, hyperlinks where local, exact artifact hashes and
  every upstream hash label supplied by the prior-review outcome.

Before publishing `PASS`, the writer independently reparses the exact salary
CSV, reserved-entry CSV, assignment CSV, exported `DK_REVIEW_ENTRY` CSV and
selection report. For policy-bearing runs it also reparses the normalized policy
and independent audit, rechecks their embedded salary, entry, source-policy,
normalized-policy and assignment hashes, and recomputes legality, salaries,
canonical identities, person/Captain counts, limits, uniqueness and pairwise
overlap from exact roster IDs. Names are display-only and never join people.
Repeated names and distinct CPT/FLEX IDs retain exact identity and entry order.

**`prior_only_readable_review_sd5_v2` (Session 11b).** Adds each entry's
`source` (`POLICY`, or `SHOWDOWN_SEQUENTIAL` for a row the fill wrote, and for
every row without a policy) and a top-level `unbound_rows`: `null` when the
policy binds every fillable row or there is no policy, else `source`,
`entry_ids`, `basis`, `checks`, the fill's configured and effective overlap,
`pairwise_overlap` among its rows and `person_exposure`. With a subset policy the
policy's checks (its normalized entry IDs, which must be the fillable rows or a
subset of them in order, denominator, limits, counts, percentages, overlap and
the audit's entry IDs and canonical lineups) cover its rows, and
`exposure.entry_count_denominator` is their count; `reconciliation.entry_count`
is every filled row. Every filled row is checked for legality, exact bytes and
distinctness against every other filled row and every prefilled roster
(`READABLE_REVIEW_CANONICAL_DUPLICATE`, `ENTRY_PREFILLED_LINEUP_REPEATED`); the
unbound rows also for the run's own exclusions
(`READABLE_REVIEW_UNBOUND_ROW_EXCLUDED_PERSON`, `V`), official inactives
(`READABLE_REVIEW_UNBOUND_ROW_NOT_ACTIVE`, `P`) and the fill's overlap
(`READABLE_REVIEW_PAIRWISE_OVERLAP_EXCEEDED`, `S`). The selection report's
`row_sources` must agree (`READABLE_REVIEW_ROW_SOURCE_MISMATCH`, `V`; a record
from before Session 11b names none and the review derives them), and so must its
`unbound_fill` (`READABLE_REVIEW_UNBOUND_FILL_REPORT_MISMATCH`, `V`). A reader of
v1 sees no `source` and no `unbound_rows`; for a run without a subset every
other field means what it meant, and v1 files stay readable as written. v1 was
never produced for a subset policy.

Canonical JSON and HTML are written atomically and reported with independent
SHA-256 values. HTML markup is escaped. Every user/provider-controlled workbook
string is stripped of illegal control characters for display and prefixed with
an apostrophe when a leading or whitespace-prefixed `=`, `+`, `-` or `@` could
be spreadsheet-active. This display escaping never rewrites the bound source
bytes or exact IDs in JSON/CSV artifacts.

Any missing file, hash change, malformed record, semantic disagreement, policy
or audit mismatch, roster mutation, entry-order/metadata change or post-write
hash failure raises a named `READABLE_REVIEW_*` discrepancy, several joined by
`;`. The Cowork command names it `READABLE_REVIEW_FAILED` (Classic C3:
`CLASSIC_C3_READABLE_REVIEW_FAILED`), stops at stage `READABLE_REVIEW` and exits
2. Since Session 05 (R28) it classifies each joined code through the gate
registry (`delivery.discrepancy_limitations`):

- a `V` code (a roster, Entry ID, byte or audited-selection disagreement), a
  code the registry does not hold, or an exception that carries no code
  (`GATE_CODE_UNCLASSIFIED`) withholds the CSV: `FILE_VALID=false`, no
  top-level `bulk_entry_csv`, and neither index names it. Showdown keeps the
  bytes on disk under `withheld_artifacts`; Classic C3 removes its four outputs;
- anything else keeps the CSV in the result and both indexes with each code as a
  limitation, `FILE_VALID=true` in its v1 meaning (the export CSV), stage
  suffix `_READABLE_REVIEW_FAILED`, once `delivery.publish` has revalidated it
  (`LATEST_DELIVERABLE.json`, below).

A `publish` refusal, or a `V` code among the run's blockers, withholds the CSV at
stage `DELIVERY` in either mode: unlisted, preserved on disk, never deleted, and
named under `delivery_withheld`. Showdown writes `READABLE_REVIEW_FAILED.json`
once that decision is final, with `withheld_artifacts` or `kept_artifacts`; a
display record that said "kept" is rewritten to say withheld. No readable-review outcome may alter
`MODEL_STATUS=PRIOR_ONLY` or `RELEASE_DECISION=DO_NOT_UPLOAD`.

## Showdown kicker-role evidence

`role_evidence_json` is an optional auxiliary package manifest using schema
`nfl_kicker_role_evidence_v1`. It is prepared by the evidence workflow, not
authored as a third numerical CSV by the operator. The manifest binds the exact
current salary SHA-256 and game, then declares one complete allocation for each
team that still has an eligible kicker after salary status, official inactive,
and operator exclusions.

```json
{
  "schema_version": "nfl_kicker_role_evidence_v1",
  "allocation_version": "kicker_team_scoring_event_allocation_v1",
  "salary_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "game_id": "NE@SEA",
  "share_tolerance": 0.000001,
  "sources": [
    {
      "path": "sources/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb.txt",
      "sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
      "source_uri": "https://raw.githubusercontent.com/example/repository/main/kicker-role.txt",
      "observed_at": "2026-09-09T18:00:00+00:00",
      "captured_at": "2026-09-09T18:01:00+00:00",
      "expires_at": "2026-09-09T21:00:00+00:00",
      "license_decision": "PERMITTED_REPOSITORY_LICENSE",
      "parser_version": "current_kicker_role_v1",
      "transformation_version": "kicker_role_extract_v1",
      "support_kind": "QUALITATIVE_SOLE",
      "supporting_excerpt": "Example Player is the sole kicker for NE.",
      "synthetic": false
    }
  ],
  "declarations": [
    {
      "game_id": "NE@SEA",
      "team": "NE",
      "allocation_kind": "SOLE",
      "recipients": [
        {
          "underlying_id": "NE|K|Example Player",
          "cpt_dk_id": "12345601",
          "flex_dk_id": "12345602",
          "share": 1.0
        }
      ],
      "source_sha256s": [
        "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
      ]
    }
  ]
}
```

Every source path is package-relative, content-addressed, and confined beneath
the manifest directory. The bytes are rehashed during parsing and immediately
before review export. Source URIs, licenses, and parser versions must pass the
same policy used by `sources.py`; observations and captures cannot be in the
future, and original expiry is retained through snapshot and replay. A copied
Cowork package includes the adjacent `sources/` directory and needs no original
external path. `--as-of` is a replay clock and never renews expired evidence.

Each recipient binds the underlying person to both exact current CPT and FLEX
DraftKings IDs. Shares must be finite and nonnegative and total one per declared
team within the fixed `0.000001` tolerance. `SOLE` has exactly one recipient at
one. `SPLIT` has at least two recipients, explicitly covers every currently
eligible kicker on that team (including zero shares), and requires a
`NUMERICAL_SPLIT` capture whose exact JSON excerpt repeats the scoped IDs and
shares. Qualitative prose can support only a sole role when the captured excerpt
contains that player's salary-file name plus an explicit sole/only/starting
kicker statement; it cannot create fractional shares. Synthetic captures are
labelled `synthetic: true` and are test-only.

An invalid supplied manifest always fails. It cannot fall back to an assumption.
Without a manifest, exactly one eligible kicker per team receives the team line
only under the visible `PRIOR_ONLY_SOLE_LISTED_ASSUMPTION`; that is not confirmed
role or official ACTIVE evidence. Multiple eligible kickers stop with
`KICKER_ROLE_UNRESOLVED`. No eligible kicker receives no allocation and produces
a coverage gap, while a legal K-free diagnostic lineup may still proceed. A
positive-share person made inactive or excluded invalidates the allocation and
requires refreshed role evidence; production is never transferred silently.

The allocation splits the existing team kicker scoring events before DraftKings
scoring. The team's base kicker points are conserved exactly once; the Captain
multiplier is applied afterward to the same person's base allocation. Zero-share
kickers are scoreless and excluded from selection.

## Quarterback depth-chart role evidence (P1)

`qb_depth_role_evidence_json` is an optional auxiliary package using schema
`nfl_qb_depth_role_evidence_v1` and allocation
`qb_depth_chart_attempt_share_allocation_v1`. It exists because a depth chart
establishes an ordering and nothing else, which the complete
`nfl_offensive_role_evidence_v1` contract cannot express: that one requires all
five share fields to total 1.0 across every eligible offensive person on the
team, so routing a depth chart through it would mean writing target and carry
numbers no source supports. This contract can only ever move
`qb_attempt_share`, and the validator enforces that.

It is applied **before** `resolve_offensive_roles` and therefore before
`score_pool`, which is the point: on 2026-09-14 the only way to stop a backup
quarterback taking 46% of his team's attempts was a portfolio-policy exclusion
landing after scoring, where it never reached the projection.

```json
{
  "schema_version": "nfl_qb_depth_role_evidence_v1",
  "allocation_version": "qb_depth_chart_attempt_share_allocation_v1",
  "transformation_version": "qb_depth_chart_order_v1",
  "salary_sha256": "aaaa…aaaa",
  "game_ids": ["DET@BUF"],
  "sources": [
    {
      "path": "sources/bbbb…bbbb.csv",
      "sha256": "bbbb…bbbb",
      "upstream_sha256": "cccc…cccc",
      "source_uri": "https://github.com/nflverse/nflverse-data/releases/download/depth_charts/depth_charts_2026.csv",
      "observed_at": "2026-09-18T12:12:55+00:00",
      "captured_at": "2026-09-18T12:17:55+00:00",
      "expires_at": "2026-09-20T00:12:55+00:00",
      "license_decision": "PERMITTED_REPOSITORY_LICENSE",
      "parser_version": "nflverse_depth_charts_csv_v1",
      "transformation_version": "qb_depth_chart_order_v1",
      "support_kind": "DEPTH_CHART_ORDER",
      "supporting_excerpt": "dt,team,player_name,…\n2026-09-18T12:12:55Z,BUF,Josh Allen,…,1\n…",
      "synthetic": false
    }
  ],
  "declarations": [
    {
      "team": "BUF",
      "game_id": "DET@BUF",
      "declared_observed_at": "2026-09-18T12:12:55+00:00",
      "starter":  {"underlying_id": "BUF|QB|Josh Allen", "cpt_dk_id": "…", "flex_dk_id": "…",
                   "provider_player_id": "00-0034857", "player_name": "Josh Allen", "pos_rank": 1},
      "backups":  [{"underlying_id": "BUF|QB|Kyle Allen", "…": "…", "pos_rank": 2}],
      "unlisted": [{"underlying_id": "BUF|QB|Shane Buechele", "cpt_dk_id": "…",
                    "flex_dk_id": "…", "player_name": "Shane Buechele"}],
      "source_sha256": "bbbb…bbbb"
    }
  ]
}
```

**The capture is a verbatim slice**, not the whole file: the published season
artifact is ~50MB holding one snapshot per `dt` (184 of them in the 2026 file on
2026-09-19) for all 32 teams, and each team needs its own excerpt. The slice is
the header line plus that team's quarterback rows at one `dt`, in `pos_rank`
order. `upstream_sha256` and `source_uri` keep it traceable to the exact
published bytes it was cut from.

**One snapshot, pinned.** `declared_observed_at` names the `dt`, and every row
in the excerpt must carry it. A capture mixing two snapshots is
`QB_DEPTH_EXCERPT_DT_MIXED`; a package whose declared order is not the order the
capture shows is `QB_DEPTH_ORDER_NOT_SUPPORTED_BY_CAPTURE`.

**Three placements, and every listed quarterback gets one.** `starter` is
`pos_rank` 1. `backups` are ranked below him. `unlisted` are quarterbacks
DraftKings sells whom the chart does not name at all — measured on the real
2026-09-17 DET@BUF slate, where DraftKings listed three Buffalo quarterbacks and
the chart named two. That is a weaker claim than "backup" and is recorded
separately; the validator refuses a person declared unlisted who does appear in
the capture (`QB_DEPTH_UNLISTED_IS_ON_THE_CAPTURE`), so it cannot be used to
hide a named starter. A quarterback placed nowhere is
`QB_DEPTH_TEAM_COVERAGE_MISMATCH`: omission and a zero share are different
claims.

**Conservation.** The starter receives exactly the sum of `qb_attempt_share` the
team's quarterbacks already held; backups and unlisted receive zero. The package
never increases team passing volume, never reaches a non-quarterback, and never
invents a fractional split. A real committee needs measured numbers, which is
the complete contract's job.

**Identity.** The two sides share no identifier, so each entry carries the
provider's `gsis_id` and the exact DraftKings binding, and the names must match
under `normalize_person_name` within the one team
(`QB_DEPTH_PROVIDER_NAME_MISMATCH`). The producer checks this and the consumer
re-checks it independently.

`does_not_establish`: `TARGET_SHARE`, `CARRY_SHARE`,
`RUSHING_OR_RECEIVING_TOUCHDOWN_SHARE`, `RECEIVING_EFFICIENCY`,
`OFFICIAL_ACTIVE_STATUS`, `MODEL_VALIDATION`,
`HOW_MANY_ATTEMPTS_THE_TEAM_WILL_THROW`.

Producer: `scripts/make_offensive_role_evidence.py`, with `--fetch` (through
`nfl_dfs.sources`, the only approved retrieval client) or `--capture` for bytes
already on disk.

### Effective depth rank (P7, R25, 2026-09-21)

`effective_depth_rank_v1`, in `src/nfl_dfs/depth_roles.py`. Not a new input
contract: `nfl_qb_depth_role_evidence_v1` is unchanged and is never mutated. A
supplied package still declares the **published** order, exactly as before. What
is new is what the engine derives from it, and two report keys that carry the
derivation.

**The rank.** The published `pos_rank` at one `(team, position)`, with everyone
the bound salary bytes flag unavailable removed from above and the survivors
renumbered from 1 in the same relative order. Positions: `QB`, `RB`, `WR`, `TE`.

**Why it exists.** `qb_depth_roles.py` refused with
`QB_DEPTH_STARTER_NOT_SELECTABLE` when the rank-1 quarterback was not
selectable, and named the remedy "refresh the depth chart after the inactive or
exclusion change". Measured on the published 2026 artifact (sha256
`e6ba0a08dc40c164eb02ce7654a247c8eb5c2d189c92d993d028524eb0494c02`, read
2026-09-21): 190 snapshots, the last before the 2026-09-20 13:00 ET lock at
`2026-09-20T12:14:30Z`, which is 08:14 ET. Official inactives publish about
11:30 ET. No depth chart is ever published between the two, so the remedy did
not exist inside the window where it was needed. `CLAUDE.md` classes a gate no
real source can clear as a defect; Ben ruled it one on 2026-09-20 (`R25`).

**Keyed `(person, position)`, never person alone.** The published file gives one
row per position a person appears at, and return lines carry their own
`pos_rank`. On the 2026-09-20T12:14:30Z snapshot Brian Robinson Jr. is `KR` 1
and `RB` 2; Devin Duvernay is `KR` 1, `PR` 1 and `WR` 6. Taking a person's best
row would make them a lead back and a WR1 on the strength of a kick-return line.
Only the four skill positions are read.

**Bounds, from R25 and binding.**

- Availability is re-derived from the bound salary bytes on every run
  (`ParticipationContract.unavailable_people`), never from the supplied package,
  so a package can never widen the set stepped over.
- Nobody becomes selectable who was not already. Promotion changes which
  available person holds a role; it never adds a person to the pool.
- A person the salary bytes still show as available is never promoted past, even
  when an operator exclusion made him unselectable. Availability is a fact;
  an exclusion is a preference, and a preference must not reassign a job.
  Refusal: `QB_DEPTH_PROMOTION_OVER_AVAILABLE_PERSON`.
- Nobody selectable anywhere in the order is still a refusal:
  `QB_DEPTH_NO_SELECTABLE_PERSON_AT_POSITION`.
- The identity gate's auto-accept rule is untouched.

**Report keys** added to the `qb_depth_roles` block of the run record:
`effective_starter_promotions` (one row per promotion, carrying `team`,
`position`, `published_starter`, `effective_starter`, `promoted_over` and
`basis=SALARY_STATUS_UNAVAILABLE_ABOVE`) and `promotion_rule`. Both are present
and empty on an ordinary slate, so a portfolio built on a promotion says so.

**Redistribution.** `participation.redistribute_opportunity` takes an optional
`depth_ranks`. Supplied, a vacated share goes to the effective-rank-1 survivor
at the vacating position (`vacancy_rule=DEPTH_CHART_SUCCESSOR_INHERITS_V1`);
omitted, the measured proportional rule is unchanged
(`PROPORTIONAL_TO_PRIOR_NO_SUCCESSOR_KNOWN`). It is off by default because the
proportional rule was forced by measurements on the real NE@SEA pool and nothing
has yet graded inheritance against it; that needs `P0`.

### `depth_charts` registered as a frozen source (P7)

`depth_charts` is the eighth entry in `priors.source_specifications()`:
`https://github.com/nflverse/nflverse-data/releases/download/depth_charts/depth_charts_<season>.csv`,
`parser_version=nflverse_depth_charts_csv_v1`, `expires_after=36h`,
`staleness_basis=DEPTH_CHART_REPUBLISHED_ABOUT_TWICE_DAILY_NEVER_BETWEEN_INACTIVES_AND_LOCK`,
required columns the twelve in `qb_depth_roles.DEPTH_CHART_COLUMNS`. It is now
frozen into the prior package and hash-bound like the other seven, rather than
living only in the producer script with its own expiry. The 36-hour expiry is
the producer's existing number, kept rather than tightened so the two paths
cannot disagree about whether one capture is fresh. Expiry is not a freshness
guarantee here and must not be read as one: an unexpired chart is still blind to
inactives, which is what the effective rank above exists to handle.

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
the separately supplied ticket face value. Cash and advertised values must be
exact cents; ticket counts must be whole numbers. A contest with no paid ranks
uses a header-only payout file and exact advertised value `0.00`; this explicit
zero-payout contract is accepted only by the Q1 settlement path.

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

Q1 uses normalized complete-field standings with columns including:

```text
EntryId,Rank,Points,Prize,Lineup
```

All operated Entry IDs must be present before the portfolio can be called settled.
Every field Entry ID must be unique, points finite, prize an exact non-negative
cent amount, and `Lineup` a nonempty complete-lineup canonical key. For an
operated entry, `Lineup` must exactly equal the canonical key independently
reconstructed from the frozen salary file and selected assignment. A
Q1-complete settlement requires exactly `field_size` rows and rejects a rank or
prize that disagrees with the independent reference evaluator. Original
standings bytes and their SHA-256 remain the authority.

## Q1C pre-lock run manifest

`nfl_prelock_run_manifest_v1` is the record, written *before* the games start, of
what a run predicted and which lineups it selected, bound by SHA-256 so a
settlement written days later cannot quietly disagree with it. The ordering is
the whole point: a manifest written after the outcome is known proves nothing.
`src/nfl_dfs/prelock_manifest.py` builds it, and `prior_review` emits one from
each of its three success paths — Showdown, Classic C1/C2 and Classic C3.

It is emitted for a `DO_NOT_UPLOAD` run, which is every prior-only run, and which
is the case that matters: those are the review lineups Ben enters by hand.
Emitting one changes no release truth and unlocks nothing. It is never
backfilled; a run that cannot be described truthfully produces a named `SKIPPED`
stage and no file.

A prior-only manifest records:

- `input_hashes` for the salary bytes, the reserved-entry bytes, the assignment,
  and each frozen prediction (`team_projections`, `player_opportunities`,
  `source_ledger`);
- `artifact_versions` for the same set — and nothing else, because
  `settlement._validate_prelock_manifest` derives the expected prediction set by
  subtracting the fixed artifact roles and the scenario names from this mapping,
  so anything listed here becomes a prediction the request must bind;
- `contest_parameters` with `contest_id`, `draft_group`, `mode` and `entry_fee`,
  all four read straight out of the two CSVs;
- the four release truths, copied from the run's own result;
- `selected_entry_ids` and `assignment_sha256`.

It declares what it does not have, rather than omitting the key and leaving "did
not know" indistinguishable from "forgot": `scenario_artifacts` is `{}`,
`field_size` is `null` with a `field_size_basis` of
`UNKNOWN_PRIOR_ONLY_RUN_READS_NO_CONTEST_ECONOMICS`, and
`model_status_limitations` names the absent prospective validation, scenarios and
contest economics.

Two properties make it replayable. The `created_at` stamp is the run's own
`as_of`, not a wall clock, and the recorded assignment path is run-relative, never
absolute. A run replayed at a pinned `as_of` therefore writes byte-identical
bytes.

### What settlement requires of a manifest, after Ben's 2026-09-14 ruling

Four checks were relaxed because no honest producer could clear them. Each was
measured against Q1's own passing fixture by removing exactly what a prior-only
run lacks.

- **`field_size` is not compared.** The manifest's copy is the pre-lock
  *assumption* a portfolio was built against; the request's is the *settled*
  entry count, which must equal the standings row count. These are different
  quantities and they routinely differ — contest 193391013 was advertised at
  133,000 and settled 126,020 — so requiring equality made the gate unclearable
  by any producer, the legacy `build` path included. `run_settlement_brief.json`
  reports `assumed_field_size` beside `settled_field_size` instead, which is
  signal for Q6 rather than a fault.
- **The payout hash and `artifact_versions` entry are optional**, and only in the
  manifest. A prior-only run reads no payout table, by design. The request binds
  the payout bytes by SHA-256 regardless, so no binding is lost; only the
  manifest's second copy of it may be absent.
- **`objective`, `advertised_prize_value` and `ticket_face_value` are compared
  when present.** Stable facts, but operator-supplied and never seen by a
  prior-only run.
- **`scenario_artifacts` may be `{}`**, and a request may bind zero scenario
  banks, if and only if `MODEL_STATUS` is `PRIOR_ONLY`.
  `SettlementCaptureRequest` enforces that condition, so a prospectively
  validated model still must bind its banks.

`contest_id`, `draft_group`, `mode` and `entry_fee` remain hard identity checks,
unchanged: they are what prove the manifest describes this contest and not
another, and a pre-lock run reads all four from bytes.

### The Classic assignment record

`write_assignments_csv` takes a `mode`. Classic writes the nine-slot
`nfl_assignment_csv_v1` file `lineups.read_assignment_csv`, `certify` and
`settle` all read; Showdown writes the six-column form it always has. Classic
previously left its selection only as `classic_assignment.json`, which that
reader cannot parse, so a Classic run could not bind an assignment into a
manifest at all.

`assignments.csv` is not an upload shape and never has been: it carries no
Contest ID, Contest Name, Entry Fee or instructions block, so DraftKings would
reject it. The prohibition on `DK_UPLOAD_*` and `DK_REVIEW_ENTRY_*` in a
prior-only Classic run is unchanged.

## Q1B standings normalization

A raw DraftKings standings export is not `nfl_standings_csv_v2` and cannot be
made into one by renaming it. `scripts/file_standings.py` performs the
conversion and writes an `nfl_standings_normalization_v1` manifest beside every
artifact it produces, recording each decision and its binding.

The real export header, measured across all 18 of Ben's 2026-09-09/10/13 pulls,
is uniformly:

```text
Rank,EntryId,EntryName,TimeRemaining,Points,Lineup,,Player,Roster Position,%Drafted,FPTS
```

Four properties of that shape drive the contract.

- **The ownership table is columns, not a trailing block.** It occupies columns 7
  to 10 of the same rows, separated by one unnamed spacer column, and runs out
  long before the standings do. Everything from the first unnamed header onward
  is dropped. A row with no `EntryId` is the ownership table outliving the
  standings, not a standings row.
- **There is no `Prize` column.** DraftKings exports no per-entry prize, so the
  column is joined from the contest's payout table and can never be an
  observation. The manifest records `observed_in_export: false`,
  `provenance: DERIVED_REFERENCE_SETTLEMENT_V1`, and the payout file's SHA-256.
  Because the value is produced by the same evaluator that
  `settlement._prepare_settlement` checks it against, `STANDINGS_PRIZE_MISMATCH`
  cannot fire on a file this tool writes; it is independent evidence only for a
  standings file carrying an externally observed prize.
- **`Points` carries float round-trip noise** and is quantized to two decimal
  places with `ROUND_HALF_EVEN`. Across 1,415,500 real entry rows the largest
  adjustment is 0.00003 and no row is a true midpoint. The rounding is required,
  not cosmetic: DraftKings computes its own `Rank` from the true 2-decimal score,
  and ranking the raw values splits tie groups DraftKings did not split. A row
  that would move further than the declared tolerance is a named refusal.
- **`Lineup` carries names, not identifiers.** It is rebuilt into the engine's
  own canonical key by resolving DraftKings' slot-tagged names against the frozen
  salary snapshot for that slate, whose SHA-256 the manifest binds. The recovered
  slot multiset is checked against the mode's required roster shape, and any name
  that does not resolve to exactly one person is a refusal.

Both inputs are therefore mandatory: without the payout table there is no prize,
and without the salary snapshot there is no canonical key. A raw export alone
produces a named refusal and no file.

Outputs are content-addressed at
`data/standings/normalized/<contest_id>/<sha256>.csv`, with
`<sha256>.manifest.json` beside them. The raw export in `data/standings/inbox/`
is never edited, moved, renamed or deleted, and its bytes are re-hashed after
every run to prove it.

### Two cases this contract cannot represent

Both are real and both are refused by default. Each has an explicit, default-off
opt-in so the path can be exercised, and neither changes the contract.

- **A field member who never submitted a lineup.** 11 of the 18 real exports
  carry them: paid entries tied at the last rank, scoring zero, with an empty
  `Lineup` cell. This contract requires a nonempty canonical key.
  `--unsubmitted-entry-policy sentinel` writes
  `NO_LINEUP_SUBMITTED:<entry_id>`, unique per entry so the row forms its own
  duplication group of one. An *operated* entry with no lineup is refused under
  every policy: it means the selected assignment never reached DraftKings.
- **An exact tie split that is not a whole number of cents.** The reference
  evaluator keeps money as exact rational cents; this contract requires an exact
  cent amount. Contest 193391013 has 757 such entries across 9 tie groups.
  Because `settlement._prepare_settlement` compares the evaluator's `Fraction`
  against the file's integer cents for every field row, a contest with any uneven
  tie split can never clear `STANDINGS_PRIZE_MISMATCH` whatever the intake
  writes. `--prize-rounding half-even` records the residual in the manifest.

## Q1B settlement request builder

`scripts/make_settlement_request.py` assembles `nfl_settlement_request_v1` from
frozen bytes. It resolves nothing it cannot bind and defaults nothing:

- salary and reserved-entry snapshots are classified by the engine's own parser,
  never by filename, because `data/runs/*/inputs/` is content-addressed;
- prediction and scenario artifacts are located by the exact SHA-256 the pre-lock
  manifest declares, and the prediction *names* come from the manifest's
  `artifact_versions`, since `settlement._validate_prelock_manifest` refuses on
  `PRELOCK_PREDICTION_COVERAGE_MISMATCH` if the request coins its own;
- `field_size` is the observed row count of the normalized standings, which is
  the only place a contest's true settled field size exists;
- the four release truths are **copied** from the frozen pre-lock run, never
  re-derived, so a settlement cannot report a better release decision than the
  slate actually shipped with;
- an assignment CSV is never chosen automatically when a run holds more than one,
  because the wrong one settles a lineup that was never entered.

`--report` resolves and names every blocker without writing anything, and exits
`2` while any remain.

## Q1 settlement request and immutable bundle

The complete one-command capture is:

```powershell
.\nfl.ps1 settle --request '<path>\settlement_request.json' --output-dir 'outputs\settlements'
```

The request is strict JSON schema `nfl_settlement_request_v1`. It contains:

```json
{
  "schema_version": "nfl_settlement_request_v1",
  "settlement_id": "unique-never-reused-id",
  "run_id": "the-frozen-prelock-run-id",
  "captured_at": "2026-09-13T16:00:00-04:00",
  "settled_at": "2026-09-14T00:30:00-04:00",
  "contest": {
    "contest_id": "193028206",
    "draft_group": "exact-draft-group",
    "mode": "CLASSIC",
    "entry_fee": "5.00",
    "field_size": 2,
    "objective": "SMALL_GPP",
    "advertised_prize_value": "20.00",
    "ticket_face_value": null
  },
  "versions": {
    "salary_parser": "dk_csv_v1",
    "entry_parser": "dk_csv_v1",
    "payout_parser": "nfl_payout_csv_v2",
    "standings_parser": "nfl_standings_csv_v2",
    "assignment_parser": "nfl_assignment_csv_v1",
    "scoring": "draftkings_nfl_scoring_2026_fixture_v1",
    "settlement": "nfl_reference_settlement_v1",
    "bundle_schema": "nfl_settlement_bundle_v1",
    "brief_schema": "nfl_run_settlement_brief_v1",
    "metric_registry_schema": "nfl_metric_promotion_registry_v1"
  },
  "artifacts": {
    "salary": {"name": "salary", "path": "salary.csv", "sha256": "<64 lower hex>", "artifact_version": "dk_salary_csv_v1"},
    "entries": {"name": "entries", "path": "entries.csv", "sha256": "<64 lower hex>", "artifact_version": "dk_entry_csv_v1"},
    "payouts": {"name": "payouts", "path": "payouts.csv", "sha256": "<64 lower hex>", "artifact_version": "nfl_payout_contract_v1"},
    "assignments": {"name": "assignments", "path": "assignments.csv", "sha256": "<64 lower hex>", "artifact_version": "nfl_assignment_csv_v1"},
    "prelock_manifest": {"name": "prelock_manifest", "path": "build.json", "sha256": "<64 lower hex>", "artifact_version": "nfl_prelock_run_manifest_v1"},
    "standings": {"name": "standings", "path": "standings.csv", "sha256": "<64 lower hex>", "artifact_version": "nfl_standings_csv_v2"},
    "metric_registry": {"name": "metric_registry", "path": "metric_registry.json", "sha256": "<64 lower hex>", "artifact_version": "nfl_metric_promotion_registry_v1"},
    "predictions": [{"name": "team_projections", "path": "team.csv", "sha256": "<64 lower hex>", "artifact_version": "nfl_team_projections_csv_v1"}],
    "scenarios": [{"name": "REFEREE", "path": "referee.parquet", "sha256": "<64 lower hex>", "artifact_version": "nfl_scenario_bank_v1"}]
  },
  "release_truths": {
    "FILE_VALID": true,
    "EVIDENCE_STATE": "UNKNOWN",
    "MODEL_STATUS": "PRIOR_ONLY",
    "RELEASE_DECISION": "DO_NOT_UPLOAD"
  },
  "evidence_issues": [
    {"state": "MISSING", "code": "PROSPECTIVE_VALIDATION_ABSENT", "detail": "No prospective validation corpus yet."}
  ],
  "reference_budget": {"max_entries": 200000, "max_work_units": 1000000, "max_runtime_seconds": 10.0}
}
```

All artifact paths may be relative to the request. The request must include at
least one frozen prediction/model artifact. It must also include at least one
versioned scenario bank unless `MODEL_STATUS` is `PRIOR_ONLY`, which simulates
nothing and so has no bank of any purpose to bind; see "Q1C pre-lock run
manifest" above for that ruling and the three others made with it.
The pre-lock manifest must be `nfl_prelock_run_manifest_v1` and independently
bind the run, contest facts, release truths, input and assignment hashes,
artifact versions, and scenario hashes. The capture rejects contest, mode,
draft-group, Entry-ID, hash, version, field-completeness, rank, prize, or source-
mutation disagreement. Missing, stale, conflicted, or mismatched model evidence
is recorded explicitly in `evidence_issues`; settlement capture never changes
the pre-lock release decision.

The command creates `outputs/settlements/<settlement_id>/` only when it does not
already exist. It copies every immutable input under `artifacts/` and writes:

- `settlement_bundle.json` (`nfl_settlement_bundle_v1`);
- `reference_settlement.json` (exact referee output);
- `run_settlement_brief.json` (`nfl_run_settlement_brief_v1`); and
- `replay_request.json` with package-relative paths.

No file in an existing package is overwritten. Copying that directory does not
change its meaning. Verify either original or copied bytes with:

```powershell
.\nfl.ps1 settle --replay '<path>\<settlement_id>'
```

`DETERMINISTIC_REPLAY_PASS` means every copied input hash, version, semantic
assignment, rank, tie, duplication, prize, reference-result hash, and canonical
brief was independently reconstructed. It is not an upload or model-promotion
decision. The old `settle --entries ... --standings ...` form remains only as a
`LEGACY_PARTIAL_SETTLEMENT_CAPTURE`, exits `2`, reports `DO_NOT_UPLOAD`, and can
never claim Q1 completeness.

## Q1 independent reference economics

`nfl_reference_settlement_v1` is deliberately separate from the NumPy
production evaluator. It rounds scores with decimal `ROUND_HALF_EVEN` to
`0.000001`, assigns rank as one plus the exact number of entries strictly above,
forms exact tie groups, and divides every cash cent and ticket-face-value cent
across all occupied tied ranks. Money is retained as rational cents so even a
three-way split of one dollar is exact rather than a binary-float approximation.
Complete-lineup duplication is counted from the full canonical lineup key, and
all operated entries are present in the same field, so they affect one another's
ranks, ties, duplicates, and payouts.

Evaluation is exact or refused. `max_entries`, `max_work_units`, and
`max_runtime_seconds` are persisted in the request and result. An exceeded
budget produces a named `REFERENCE_*_BUDGET_EXCEEDED` error; there is no sampled
or extrapolated fallback.

## Q1 metric and promotion registration

`config/metric_registry_q1_v1.json` is the predeclared
`nfl_metric_promotion_registry_v1` artifact. It registers player-outcome
accuracy/calibration, participation, ownership calibration, complete-lineup
duplication, rank/payout tails, portfolio utility/downside, runtime, and memory.
Every metric declares its definition, direction, unit, interval method,
effective-sample-size report, minimum sample, practical promotion delta,
noninferiority margin, demotion threshold, rollback threshold, and rationale.
The registry also fixes slate-grouped temporal splits, holdout embargo,
multiple-testing control, runtime/memory caps, and fail-closed missing-metric
behavior.

The `learn` command hashes and validates this artifact and requires its
timezone-aware `registered_at` to precede `--challenger-evaluated-at` (or the
current command time). A registry created after evaluation is rejected as
`METRIC_REGISTRY_NOT_PREDECLARED`. Until Q6 implements the complete registered
metric-result artifact, `learn` also reports
`REGISTERED_METRIC_RESULTS_REQUIRED_Q6`, keeps `promote=false`, and cannot use
legacy boolean diagnostics to promote. This registration does not promote any
model.

## Baseline entry file and report (Session 04)

Registered 2026-09-23 by Session 04 (R28, R29). `nfl baseline --salaries <csv>
--entries <csv> [--out-dir] [--run-id] [--per-solve-seconds] [--budget-seconds]
[--exclude <DK ID>]... [--unavailable-status <code>]... [--official-status <csv>]`
(`baseline.run_baseline`) builds distinct legal lineups from the two DraftKings
files, less the people an exclusion or an official `INACTIVE` row takes out
(Sessions 06 and 06b): no network, no prior, no weather, no role evidence. It is the
file R28 ships first. Exit 0 fills every blank authorized row, 3 fills some and
names the rest, 2 fills none; no exit clears an upload.

### The run folder

`<out-dir>/<run_id>/`, default `data/runs/`. `run_id` defaults to
`baseline-<UTC stamp>-<first 8 hex of the SHA-256 over both input hashes>`. A
folder that exists refuses the run (`RUN_ID_COLLISION`) and nothing is written
into it. Inside:

| File | Contents |
|---|---|
| `inputs/<sha256>.csv` | Byte copies of the two supplied files, hash-checked on arrival; everything after intake reads these |
| `intake.json` | Each input's supplied flag, original path, SHA-256, snapshot path and schema |
| `DK_BASELINE_ENTRY_V1_<run_id>.csv` | The delivered file, `nfl_baseline_entry_csv_v1`, only when the audit passes |
| `baseline_report.json` | `nfl_baseline_report_v2` since Session 06b (`v1` before) |

Inputs are bound by schema (`cowork.classify_csv`), not by flag or file name,
so swapped flags still bind correctly and the report says which flag carried
which file. Anything other than exactly one salary CSV and one entries CSV is
`BASELINE_INPUT_SCHEMA_UNRESOLVED`.

Since Session 06 `run_baseline` also takes `operator_excluded_dk_ids` and
`extra_unavailable_statuses`, which `run-slate` fills from its request's
`exclude_dk_ids` and `unavailable_statuses`, and `nfl baseline` takes as the
repeatable `--exclude` and `--unavailable-status`. `baseline.pool_exclusions` turns them into people: every salary row of a
person an excluded ID belongs to leaves the pool, and so does everyone whose
raw DraftKings status is an extra unavailable one. They only narrow the pool;
`available_statuses` is not read. An excluded ID the salary file lacks is
`OPERATOR_EXCLUSION_NOT_IN_POOL` (`V`), as in `participation`, and nothing is
built.

Since Session 06b (R32) `run_baseline` also takes `official_status_csv`, which
`run-slate` fills from its request and `nfl baseline` takes as
`--official-status`. The file is snapshotted into `inputs/` and bound in the
report's `inputs.official_status` (`path`, `sha256`, `snapshot`), then parsed by
`evidence.parse_official_inactive_snapshot`, the exact-ID parser the model path
uses, through `baseline.official_inactive_people`. A row counts only when it
passes the parser's checks: an exact current-slate DraftKings ID on its own
team, `ACTIVE` or `INACTIVE`, from a public HTTPS source at a timezone-aware
time. Every person with such an `INACTIVE` row leaves the pool, all of their
salary rows included. That includes a row the parser set aside only because it
disagreed with an earlier row for the same ID, and salary roles that disagree:
the baseline only narrows, so disagreement takes the person out
(`official_status_conflicts`). Nothing else in the file is read: freshness and
whether it covers every selected person stay certification checks, so
`OFFICIAL_STATUS_REQUIRED` stays, its detail saying what was applied. A row
that fails those checks is `BASELINE_OFFICIAL_STATUS_ROWS_NOT_APPLIED` and a
file that cannot be read at all (a wrong header, a decode or CSV error) is
`BASELINE_OFFICIAL_STATUS_UNREADABLE`, both `P`: the baseline still ships,
without them. A snapshot that changes before the write is
`BASELINE_OFFICIAL_STATUS_CHANGED_DURING_RUN` (`V`).

### `nfl_baseline_entry_csv_v1`

The entries template's exact bytes with the roster cells of assigned blank rows
written by `lineups.write_upload_bytes`, which since Session 04 takes the rows
left blank on purpose as `unfilled`. Every other byte, including an unfilled
row, the embedded player table and its `AvgPointsPerGame` cells, the line
endings and the encoding, is the template's. The name never begins `DK_UPLOAD`.

Before the file is kept, `baseline.audit_baseline_bytes` reads the bytes back
from disk and, from fresh parses of both snapshots: runs `referee.audit_output_bytes`
against the template; reparses them and reconciles the mode; checks the Entry
IDs, their order, and that exactly the assigned rows are filled and exactly the
unfilled rows are blank; runs `lineups.validate_lineup` on every filled row;
checks exact-roster distinctness; and re-derives the exclusions to check no
filled row holds a DraftKings-unavailable person (`BASELINE_AUDIT_UNAVAILABLE_PERSON`),
an operator-excluded one (`BASELINE_AUDIT_OPERATOR_EXCLUDED_PERSON`) or one the
official status snapshot marks inactive (`BASELINE_AUDIT_OFFICIAL_INACTIVE_PERSON`). A failure, or an audit that cannot finish
(`BASELINE_AUDIT_FAILED`), withholds the file (`BYTE_AUDIT`, `BASELINE_AUDIT_*`,
`REPARSE_ASSIGNMENT_MISMATCH`), and the temporary copy never outlives the run.
Both snapshots are re-hashed before the write (`ENTRY_TEMPLATE_BYTES_CHANGED_AFTER_PARSE`,
`SALARY_CHANGED_BEFORE_ARTIFACT_PUBLISH`) and the file after it (`POST_WRITE_HASH_MISMATCH`).

Integrity gates that stop the file: an input of the wrong schema or an
unreadable one; any DraftKings parse refusal (`DK_*`, `dk.py`); a
Classic/Showdown mismatch (`DK_TEMPLATE_MODE_MISMATCH`); a salary ID the
entries file's player table lacks, which a lineup could hold and the contest
would refuse (`BASELINE_ENTRY_POOL_ID_MISMATCH`). Until Session 11 a prefilled
row refused the whole template; since then authority is per row (§ Entry
groups): a prefilled row passes through byte for byte, only the plan's
fillable blank rows are written, the audit refuses a filled roster equal to a
prefilled one (`ENTRY_PREFILLED_LINEUP_REPEATED`, on the generated row) and a
row outside the fillable set (`ENTRY_AUTHORIZATION_MISMATCH`), and writing into
a prefilled cell still refuses the file (`ENTRY_BLANK_CELL_AUTHORITY_REQUIRED`,
`V`). These ship and say so
(`P`): a table ID the salary file lacks, which no lineup can hold
(`BASELINE_SALARY_FILE_MISSING_ENTRY_TABLE_IDS`); a template with no player
table (`BASELINE_ENTRY_POOL_CROSS_CHECK_UNAVAILABLE`); and a run whose clock is
at or past the earliest lock (`BASELINE_EARLIEST_LOCK_PASSED`), since the
baseline does not enforce the lock clock (Session 07).

### `BASELINE_SALARY_RANK_V1`, the objective

Registered in `baseline.OBJECTIVE` and carried in every report. Each salary
row scores its DraftKings salary, a captain row at its own 1.5x price, over the
rows left after `contracts.unavailable_people` (DraftKings `OUT`, `IR`, `D`,
derived from the salary bytes exactly as `freeze_prior_package` derives it).
Lineups come in non-increasing total salary: each is a highest-salary legal
lineup not already chosen, with an exact no-good cut against every earlier one
(R29: a different Showdown captain is a different lineup). One
salary-maximizing solve finds a level; zero-objective solves with a salary floor
at that level (`LineupOptimizer.set_salary_floor`) take its other lineups; when
the level is spent, the next maximizing solve finds the next. Ties within a
level fall in the deterministic solver's order, with HiGHS's `random_seed` set
to the number of lineups already built (`seed_rule`): the same bytes give the
same file while no solve reaches its time limit, and each solve starts its
search somewhere new. Measured on the
supplied Classic pool at 150 entries, that seed rule alone took the most-used
salary row from 149 lineups to 37 at no cost in time. Lineup `i` fills the
template's `i`-th blank row.

Each solve has a limit (default 5 s) and the run a budget from its start
(default 60 s); the audit and write after construction always run. A
level-finding solve that stops at its limit may set a level below the best
remaining salary, so from that lineup on every lineup is marked `time_limited`
and the order is no longer proven; legality and distinctness never depend on
the limit. When
lineups stop short, the rows past the last one stay blank and are named:
`BASELINE_DISTINCT_LINEUPS_EXHAUSTED` (`V`, R29) when the solver proves no
further distinct legal lineup exists; `BASELINE_RUN_BUDGET_EXHAUSTED` or
`BASELINE_SOLVE_LIMIT_WITHOUT_LINEUP` (`S`) when time ran out, with
`UNFILLED_AUTHORIZED_ROWS` naming the rows.

Does not establish: `EXPECTED_POINTS`, `PROJECTION`, `CONTEST_ECONOMICS`,
`WIN_OR_CASH_LIKELIHOOD`, `OWNERSHIP_OR_LEVERAGE`, `OFFICIAL_ACTIVE_STATUS`,
`CURRENT_TEAM_ROLE`, `WEATHER`, `MODEL_VALIDATION`, `UPLOAD_CLEARANCE`. Salary
is DraftKings' price and the only number in its bytes the engine may read.

### `nfl_baseline_report_v1`

| Field | Meaning |
|---|---|
| `schema_version`, `generated_at`, `run_id`, `run_dir` | Identity and clock (UTC) |
| `gate_registry_sha256` | The registry bytes every limitation was built from |
| `command` | `per_solve_seconds`, `budget_seconds` |
| `inputs` | `salaries` and `entries`: `supplied_as`, `path`, `sha256`, `snapshot`, `classified_by`; `supplied_schemas` by flag |
| `slate` | Mode, draft group, both hashes, salary rows, games, `earliest_lock_at`, entry rows, blank and prefilled rows, Contest IDs |
| `pool` | The availability contract, its statuses, `excluded_people`, excluded and eligible salary rows, `entry_pool_cross_check` (`PASS`, `ABSENT`, `MISMATCH`, `SALARY_SUBSET`) |
| `objective` | `BASELINE_SALARY_RANK_V1`, as above |
| `construction` | `stop_reason` (`FILLED`, `DISTINCT_LINEUPS_EXHAUSTED`, `BUDGET_EXHAUSTED`, `SOLVE_LIMIT_WITHOUT_LINEUP`, `SOLVER_PRODUCED_ILLEGAL_LINEUP`, `SOLVER_REPEATED_A_LINEUP`), lineups built, solves, salary levels, `people_used` and `most_used_person_lineups` (a concentration count for late-swap exposure, not a preference), `elapsed_seconds` |
| `lineups` | Per filled row: `entry_id`, `roster`, `salary`, `found_by`, `time_limited`, `solve_seconds` |
| `output` | `path`, `sha256`, `bytes`, `contract_version`, filled and unfilled rows; `null` when withheld |
| `audit` | `status` (`PASS`, `FAIL`, `NOT_RUN`), `problems`, `checks_run` |
| `release_truths` | `nfl_release_truths_v2`: the five truths, delivered and unfilled Entry IDs, every limitation |
| `status`, `warning`, `checks_not_run`, `timing` | `DO_NOT_UPLOAD`; the `PRIOR_ONLY / DO_NOT_UPLOAD` warning; what was not consulted; `wall_seconds` |

Every limitation is built by `GateRegistry.limitation` from an exact
registered code. Every run carries four `P` limitations, since the baseline
consults none of their evidence: `OFFICIAL_STATUS_REQUIRED`,
`OFFENSIVE_CURRENT_ROLE_UNRESOLVED`, `WEATHER_CAPTURE_REQUIRED` and
`MODEL_NOT_PROSPECTIVELY_VALIDATED`. A several-contest or mixed-fee template
carries `MULTI_CONTEST_ENTRY_FILE_UNSUPPORTED` or `MIXED_ENTRY_FEES_UNSUPPORTED`
(`P`), and its lineups are distinct across the whole file. The truths are
`FILE_VALID` true only when the file was written and audited,
`EVIDENCE_STATE=UNKNOWN`, `MODEL_STATUS=PRIOR_ONLY`,
`RELEASE_DECISION=DO_NOT_UPLOAD`, and `DELIVERY_STATE` derived by
`release.derive_delivery_state`. The lock clock is not enforced here
(Session 07); `earliest_lock_at` is reported and printed, and a run at or past
it carries `BASELINE_EARLIEST_LOCK_PASSED`.

Does not establish: upload clearance, certification, lineup quality, or any
expected-points, return, win, cash, ownership or edge claim.

### `nfl_baseline_report_v2`

Registered 2026-09-24 by Session 06b. Every `v1` field, unchanged in meaning,
plus the exclusions Sessions 06 and 06b added. Session 06 wrote its fields into
reports still labelled `v1`; those reports are read as `v2` without the
official-status fields.

| Field | Added |
|---|---|
| `pool.operator_excluded_dk_ids`, `pool.operator_excluded_people`, `pool.extra_unavailable_statuses` | The operator's exact exclusions and extra unavailable statuses, as applied |
| `pool.official_status_applied` | Whether an official status file was read and applied |
| `pool.official_inactive_people` | Every person it took out |
| `pool.official_status_conflicts` | The disagreeing rows whose people it took out |
| `pool.official_status_rows_not_applied` | The rows it refused |
| `inputs.official_status` | `path`, `sha256` and `snapshot` of the file, when one was given |
| `audit.checks_run` | Adds `NO_OPERATOR_EXCLUDED_PERSON` and `NO_OFFICIAL_INACTIVE_PERSON` |

### `nfl_baseline_report_v3`

Registered 2026-09-24 by Session 11. Every `v2` field, unchanged in meaning,
plus the template's rows by kind and outcome (§ Entry groups). A reader of a
`v2` report sees no prefilled row, because a `v2` baseline refused any template
that had one.

| Field | Added or changed |
|---|---|
| `slate.blank_rows`, `slate.prefilled_rows`, `slate.partly_filled_rows` | The template's rows by kind, in template order (`prefilled_rows` was already a list) |
| `slate.fillable_rows`, `slate.preserved_rows`, `slate.unresolved_rows` | The plan's outcomes; `blank_authorized_rows` is now the fillable count |
| `slate.contest_ids` | Contest IDs in template order, one per group |
| `entry_groups` | One record per Contest ID (§ Entry groups) |
| `release_truths` | `nfl_release_truths_v3` |

A several-contest or mixed-fee template no longer carries
`MULTI_CONTEST_ENTRY_FILE_UNSUPPORTED` or `MIXED_ENTRY_FEES_UNSUPPORTED` in the
baseline: its rows are groups now. Legacy `certify` keeps both
(`certification.py`, ROADMAP §2.4 D7).

## Release truths

Registered 2026-09-23 by Session 03 (R28). Every run reports independent
truths; `FILE_VALID` never implies release, and `DELIVERY_STATE` never implies
upload clearance.

### `nfl_release_truths_v1`, the four truths as they stand

The name is given here for the first time, so that v2 has a predecessor; no v1
byte, field or derivation changes. v1 is `FILE_VALID`, `EVIDENCE_STATE`,
`MODEL_STATUS` and `RELEASE_DECISION`, derived only by
`release.derive_release_policy` and carried by `certification_manifest_v1`,
the pre-lock run manifest and settlement's `release_truths`. `FILE_VALID`
describes the artifacts the producing contract names (the C1 review JSON, the
C3 export, a certified CSV). `CERTIFIED` derives only from
`RELEASE_DECISION=CERTIFIED_UPLOAD_PACKAGE`.

### `nfl_release_truths_v2`, adding `DELIVERY_STATE`

`contracts.ReleaseTruthsV2`, built by `release.release_truths_v2` from a v1
result and a `release.derive_delivery_state` result. `nfl baseline` (Session
04) emits it. Since Session 05 every `run-slate` `prior_review` exit carries it
as `release_truths`, with `DELIVERY_STATE` beside the four truths: its
`delivery_limitations` are the run's blockers and any readable-review codes,
each built by `delivery.blocker_limitations` or `discrepancy_limitations`
through the registry, and a blocker the registry does not hold is
`GATE_CODE_UNCLASSIFIED` (`V`, fail closed). Since Session 06 every `run-slate`
exit reads the latest-deliverable pointer back and takes the delivery half from
the file it names: when that is the review's own CSV, its truths are the
review's; when it is still the baseline, the four v1 fields are the run's own
and `DELIVERY_STATE`, `delivered_file_valid`, coverage and limitations are the
baseline's, plus `IMPROVEMENT_NOT_DELIVERED` (`P`) naming why the review did not
replace it. That is the case `delivered_file_valid` exists for: `FILE_VALID` can
be false while a valid baseline ships. With no pointer, nothing is delivered and
the run's blockers are the limitations (`PROFILE_WRITES_NO_ENTRY_FILE` when a
review completed without a file). The pre-review blocked exit carries it too
since Session 06.

| Field | Meaning |
|---|---|
| `schema_version` | Exactly `nfl_release_truths_v2` |
| `FILE_VALID`, `EVIDENCE_STATE`, `MODEL_STATUS`, `RELEASE_DECISION` | The v1 values, copied unchanged, with their v1 meaning |
| `DELIVERY_STATE` | `DELIVERABLE`, `DELIVERABLE_PARTIAL` or `NO_DELIVERABLE` |
| `delivered_file_valid` | Whether the file `DELIVERY_STATE` describes passed its own validation. It differs from `FILE_VALID` when an improvement fails and a valid baseline ships |
| `delivered_entry_ids` | The authorized rows the file fills, in template order |
| `unfilled_entry_ids` | The authorized rows it leaves blank, in template order |
| `delivery_limitations` | Every gate that fired, structured (below) |

`DELIVERY_STATE` is derived from file validity, coverage and integrity blockers
only; the derivation takes no model or evidence input:

- `DELIVERABLE`: the file is valid, every authorized blank row is filled, and no
  integrity limitation exists.
- `DELIVERABLE_PARTIAL`: the file is valid, some rows are filled, every
  unfilled row is named by Entry ID in an integrity limitation, and no
  integrity limitation names a row that is not unfilled.
- `NO_DELIVERABLE`: nothing valid to hand over. The file is invalid, a
  file-wide integrity gate fired, no row is filled, or the template authorizes
  none.

A `delivery_limitations` entry is `code` (one upper-snake token; detail goes in
`detail`), `class` (`V`, `S` or `P`, the audit's classes), `stops` (`FILE`,
`CERTIFICATION` or `CONSTRUCTION_PREFERENCE`), `provenance` (`kind` one of
`CLAUDE_MD_BOUNDARY`, `RULING`, `CONTRACT`, and `ref` naming it), `entry_ids`,
`people` and `detail`. Only a `V` gate stops the file, and a `V` gate stops
nothing less (R28: truth-claim gates stop certification and construction
preferences are relaxable). Since Session 04 the pair is one of three, however
the entry is built: `V` with `FILE`, `S` with `CONSTRUCTION_PREFERENCE`, `P` with
`CERTIFICATION` (`contracts.GATE_CLASS_STOPS`, the registry's own pairs). A `V` entry with no Entry IDs, or with one the
template does not hold, covers the whole file; with Entry IDs it covers those
rows. `S` and `P` entries never change `DELIVERY_STATE`.

The derivation adds three limitations of its own, so a gap is never silent:
`UNFILLED_AUTHORIZED_ROWS` (R28) for unfilled rows nothing else names,
`FILE_VALIDATION_INCOMPLETE` for an invalid file with no file-wide reason, and
`NO_AUTHORIZED_ROWS` for a template with no blank row. It refuses, with
`DELIVERY_ENTRY_NOT_AUTHORIZED`, `DELIVERY_ENTRY_ID_REPEATED`,
`DELIVERY_ENTRY_ID_BLANK` or `DELIVERY_ROW_BLOCKED_BY_INTEGRITY_GATE`, inputs no
record could describe honestly.

The record keeps the same invariants however it is built, deserialized
included: no repeated or blank Entry ID or person, no row both delivered and
unfilled, `delivered_file_valid=false` only with `NO_DELIVERABLE`, and no
`CERTIFIED_UPLOAD_PACKAGE` unless `DELIVERY_STATE` is `DELIVERABLE`.
`RELEASE_DECISION` is unchanged by v2: every current path still ends
`MODEL_STATUS=PRIOR_ONLY` and `RELEASE_DECISION=DO_NOT_UPLOAD`.

Does not establish: upload clearance, certification, lineup quality, EV, ROI,
win or cash probability, or that any limitation's evidence is sound. It says a
valid file exists and which rows it covers.

### `nfl_release_truths_v3`, adding preserved and unresolved rows

Registered 2026-09-24 by Session 11. `contracts.ReleaseTruthsV3`, built by
`release.release_truths_v3`. Every `v2` field, with its `v2` meaning, plus:

| Field | Meaning |
|---|---|
| `schema_version` | Exactly `nfl_release_truths_v3` |
| `preserved_entry_ids` | Prefilled rows kept byte for byte whose roster resolves (§ Entry groups), in template order |
| `unresolved_entry_ids` | Rows left as they were and named by a limitation of any class: a partly filled row, a prefilled roster that does not resolve or repeats an earlier one, every row of a group whose contest cannot be stated |

A row is delivered, unfilled, preserved or unresolved, never two.
`delivered_entry_ids` and `unfilled_entry_ids` keep their meaning over the
fillable blank rows. The derivation changes in three places: a `V` limitation
covers the whole file when it names no row or a row that is not fillable or
unresolved (a preserved row included); `DELIVERABLE` needs no unfilled and no
unresolved row, so an unresolved row keeps a file `DELIVERABLE_PARTIAL`; and an
unresolved row nothing names refuses the record
(`DELIVERY_UNRESOLVED_ROW_UNNAMED`), as does a row in two lists
(`DELIVERY_ROW_KIND_OVERLAP`). Every `run-slate` exit and `nfl baseline` emit
v3 since Session 11. A reader of `v2` sees no preserved or unresolved row,
because every `v2` producer refused a template with one; `delivery.as_v3` reads
a `v2` record as `v3` with both lists empty.

The per-code class, provenance and `stops` for every blocker the engine can
emit live in `config/gate_registry_v1.json` (below). Session 04's baseline
builds its limitations from a code there, and Sessions 05 to 09 follow. `release._integrity` states its three
itself, and a test holds them equal to their registry entries.

## Gate registry

Registered 2026-09-23 by Session 03b (R28). `config/gate_registry_v1.json`,
schema `nfl_gate_registry_v1`, SHA-256 `685d7109291e2d903097bb648c0b73787456cd6f06254f2bf24c55247cbb0f25`, loaded and validated by
`gate_registry.load_gate_registry`, which hashes the bytes and refuses any other
bytes when given `expected_sha256`. The hash is pinned in
`tests/test_gate_registry.py` and here, so a reclassification moves both.
`nfl baseline` (Session 04) builds its `delivery_limitations` through
`GateRegistry.limitation` and records the hash it used; Sessions 05 to 09 bring
the other paths to it. It changes no gate's behaviour.

| Field | Meaning |
|---|---|
| `schema_version` | Exactly `nfl_gate_registry_v1` |
| `registered_at` | The ISO date the registry was written |
| `families` | Name (lower snake) to `class`, `stops`, `provenance` (`kind`, `ref`, as `GateProvenance`) and `covers`, one sentence |
| `codes` | Every exact blocker code to its family, one per line |
| `expansions` | A template (`*` for an interpolation the source leaves open) to the exact codes it produces |

Rules the loader enforces, each a refusal with its own `GATE_REGISTRY_*` code:

- Exactly three class and `stops` pairs: `V` stops the `FILE`, `S` a
  `CONSTRUCTION_PREFERENCE`, `P` `CERTIFICATION`. They are `CLAUDE.md`'s three
  classes of rule: integrity gates withhold the file or the rows they name,
  construction preferences are relaxable under a lock clock, and truth-claim
  gates stop certification and travel with the file (R28).
- No duplicate key anywhere, no code whose family is missing, no family no code
  uses, no unknown top-level field, no blank provenance `ref` or `covers`.
- Every key of `codes` is one exact upper-snake code. A template appears only as
  a key of `expansions`, and lists codes that match it and are themselves in
  `codes`.

`GateRegistry.limitation(code, entry_ids, people, detail)` looks a code up
exactly and nothing else; no template or pattern resolves a code, so an
unregistered or malformed code refuses. The result is a `DeliveryLimitation`,
so its own rules apply too.

`tests/test_gate_registry.py` holds the registry to the source. A blocker
literal is the leading upper-snake token of a string, ending it or followed by
`:`, in an emitting position: a raised exception's first argument; the first
argument, or `code=`, of a call named for a blocker (`*Error`, `_problem`,
`_issue`, `QAFinding`, and since Session 04 `GateRegistry.limitation`); an item collected onto, spread into a display beside,
or assigned to, a holder named for blockers, or a local that only holds one; the
value of a `"blockers"` key; a tuple slot named for blockers or problems, or
`reason` beside the action `BLOCK`, from a display or a called function's
returned tuples; a keyword named for a blocker or reason, or `code`; a string
compared inside a function named for blocking. The scan follows locals, called
functions' returned displays and comprehensions, and resolves an interpolation
from literal call-site arguments or a literal loop. Every such code under
`src/nfl_dfs/` is registered and every registered code is still emitted. What
the scan cannot see (two codes `release._integrity` builds, the C2 and SD3
selection statuses passed through a `status` field, the referee's reasons and
the C3 scale harness's replay status) is pinned to the source text that emits
it, and so are the seven offensive-role reasons it reads but that block nothing.

Known limits. The scan is syntactic: a code reached only through a shape it
does not follow is missed until it is pinned. Late swap's three emitters put the
Entry ID inside the token (`{PRIOR|CURRENT|PROPOSED}_{entry_id}:`), so no
registry can hold them; the test lists them for Session 12. Session 04 gave
certification and the review export a fixed `LINEUP_INVALID:<entry_id>:` and
gave every refusal in the DraftKings parser and the roster validator and writers
(`dk.py`, `lineups.py`) a code of its own. `scripts/` codes are outside the
registry.

Does not establish: that a gate is correct, that its evidence is sound, upload
clearance, certification or any model claim. It says what each gate, when it
fires, stops and on whose authority.

## Deadline budget (Session 07)

Registered 2026-09-24 (R31). `deadline.Budget`, built once by `run-slate` right
after intake, is the run's one clock and time budget; its record,
`nfl_deadline_budget_v1`, is the result's `deadline` field.

- **Deadline.** The request's `delivery_deadline_utc`, or the earliest relevant
  lock minus 5 minutes (R31). The earliest relevant lock is the earliest
  `lock_at` among the salary file's games (`deadline.earliest_lock`): every
  contest on a draft group locks at its first kickoff and every blank row a
  pre-lock run fills is on it, so a template whose entries span contests takes
  the same minimum. An explicit deadline is authoritative, including one after
  the lock, which is named.
- **Improvement stop.** The deadline less a finishing reserve of
  `stop_discretionary_optimization_minutes_before_lock` (`config/runtime.json`,
  10) minus 5: by default optimization stops at lock minus 10 and delivery is
  due at lock minus 5. The key must be at least 5. `full_refresh_seconds` is
  removed: a fixed cap would stop an improvement the deadline still had room for.
- **Clock.** Elapsed time is monotonic (injected in tests). The deadline is
  compared with the run's clock: the pinned `--as-of` advanced by elapsed time,
  else the wall clock. A pinned run records the wall clock beside it.
- **Allowances.** The baseline gets `min(60, max(30, seconds to the
  deadline))` with 5 s per solve, a deadline already passed included. Against
  the improvement window: the session probe `min(45, 10%)`, skipped under 3 s;
  sequential (C1) selection `min(10, window / (lineups + 1))` per solve,
  stopped under 0.5 s; an SD3 bank `min(scaled, 70%)` and its joint solve
  `min(scaled, 20%)`; a Classic C2 policy's bank and joint limits are
  hash-bound, so they either fit the window or stop the review (inside
  `run-slate` the relaxation controller then re-sizes the bank or takes
  rung 4, § Relaxation record). A passed deadline or a spent window skips
  the review before it starts.
- **Evidence fetches (Session 07b).** `sources.fetch_public_artifact` takes
  `Budget.fetch_seconds`: `min(30, the improvement window)`, from the budget
  passed or the one `deadline.activated` set (`run-slate` wraps its review in
  it, so the prior build's fetches read it; `sleeper_daily_player_snapshot`
  fetches through the same function and inherits this); outside one, the
  fixed 30 s. Under 1 s no request starts and it raises
  `SourceDeadlineError("DEADLINE_FETCH_WINDOW_SPENT:<host>: ...")`. In
  `run-slate` the review's `propose` names that as
  `PRIORS_PROPOSE_FAILED:SourceDeadlineError:DEADLINE_FETCH_WINDOW_SPENT:...`,
  and the budget's own event puts `DEADLINE_FETCH_WINDOW_SPENT` on
  `release_truths`. `scripts/fetch_weather_captures.py` (standard library)
  repeats both 5-minute reserves: its `--delivery-deadline-utc` defaults to the
  earliest `Game Info` lock minus 5 minutes, requests stop 5 minutes before
  it, each timeout is `min(30, left)` and each retry pause `min(2**n, left)`,
  and under 1 s it exits `FETCH_DEADLINE_REACHED` without a request. Without
  IANA data or a readable lock time it says so, names the flag and keeps its
  fixed clocks. `scripts/make_classic_policy.py` sizes the bank to the window
  before the improvement stops (the same deadline and `runtime.json` stop):
  bank budget plus joint solve within 75% of it, the joint solve within 20%,
  at this host's rate or 0.28 s with 2x headroom; when even the floor bank
  does not fit, or the window has closed, it writes nothing and exits 2.

| Field | Meaning |
|---|---|
| `schema_version` | `nfl_deadline_budget_v1` |
| `deadline_utc`, `deadline_source` | The deadline, and `REQUEST` or `DEFAULT_EARLIEST_LOCK_MINUS_R31` |
| `earliest_lock_utc`, `handoff_reserve_seconds` | The earliest relevant lock and R31's 300 s |
| `stop_discretionary_optimization_minutes_before_lock`, `finish_reserve_seconds`, `improvement_stop_utc` | The runtime key, the reserve it gives, and when optimization stops |
| `clock` | `deadline_against` (`PINNED_AS_OF` or `WALL_CLOCK`), `started_utc`, `wall_started_utc`, `elapsed` (`MONOTONIC`) |
| `passed_at_start`, `seconds_to_deadline_at_start`, `elapsed_seconds` | As named |
| `stages` | One per stage in order (`intake`, `baseline`, `session_probe`, `policy_validation`, `evidence_fetch` once per fetch, `selection`, `review`, `finish`): `started_after_seconds`, `elapsed_seconds` (measured), `default_seconds`, `allowance_seconds`, `outcome` (`COMPLETED`, `SKIPPED`, `RAISED`); a refused fetch is `SKIPPED` with the moment it was refused |
| `limitations` | The codes below, in the order they arose |
| `candidate_rate` | The Classic C2 bank observation this run recorded, or `null` |
| `does_not_establish` | Upload clearance, certification, lineup quality, that the deadline is met after the run ends |

Codes. `delivery_deadline` (`S`, `CONSTRUCTION_PREFERENCE`, R31):
`DEADLINE_PASSED_AT_START`, `DEADLINE_IMPROVEMENT_WINDOW_SPENT`,
`DEADLINE_POLICY_SEARCH_EXCEEDS_WINDOW`, `DEADLINE_STAGE_SHORTENED` (a stage
ran under its default or was skipped; once per stage), `DEADLINE_FETCH_WINDOW_SPENT`
(an evidence fetch not started; once per host and moment) and
`DEADLINE_PASSED_DURING_REVIEW` (the review ended after the deadline; a file it
delivered replaces the baseline as usual and is named late).
`certification_prerequisite` (`P`): `DEADLINE_AFTER_EARLIEST_LOCK` and
`DEADLINE_WALL_CLOCK_PAST_DEADLINE` (a pinned clock before the deadline while
the wall clock is past it: a replay). None is `V`: a deadline never withholds a
valid file. They reach `release_truths` on every exit that reports them, beside
the delivered file's own, each once; the certify exit, which reports four
truths, carries them in `deadline.limitations`. Certifying a supplied
manual-guardrail assignment optimizes nothing, so the deadline does not stop
it. A request deadline must fall in the years 2000 to 2999.

### `nfl_host_candidate_rate_v1`

`<runs dir>/host_candidate_rates.json` (`data/runs/`, per machine, never
committed). `hosts` maps `<node>|<system>|<machine>|cpus=<n>|<mode>` to its last
20 observations: `seconds_per_candidate`, `candidates`, `elapsed_seconds`,
`basis` (`BANK_REPORT`: the bank's own count and time, which since Session 08
includes a bank stopped at its time limit that still delivered
(`BOUNDED_TIME_LIMIT_STOP`); `BANK_TIME_LIMIT`: a blocking
`CANDIDATE_BANK_TIMEOUT` count over the policy's declared bank budget),
`pool_people`, `entries`, `run_id`, `measured_at` (wall clock). `run-slate`
appends one after every Classic C2 bank; `deadline.read_candidate_rate` returns
the slowest of this host's last five for a mode. A file there that is not this
ledger is refused and left as it is, and the review goes on. `scripts/make_classic_policy.py`
reads it (`--host-rates`) in place of its 0.28 s constant since Session 07b, and
falls back to 0.28 s when this host has no Classic rate or the file is not
this ledger.

Does not establish: that any stage's allowance was enough, lineup quality,
certification or upload clearance.

## Entry groups (Session 11)

Registered 2026-09-24 by Session 11 (R28, R29). `entry_groups.plan_entries`
reads a reconciled template against its slate, and every producer (the
baseline, C1's export, the Showdown review export, C3) and `delivery.revalidate`
take their rows from it:

- a **blank** row (every roster cell empty) is **fillable** unless its group is
  unresolved;
- a **prefilled** row (every cell set) is **preserved** when each cell is an
  exact current-slate DraftKings ID, as a bare ID or text ending `(ID)`, and the
  shared validator passes the roster; otherwise it is unresolved
  (`ENTRY_PREFILLED_ROSTER_UNRESOLVED`, `P`, family `entry_rows`), as is a
  prefilled roster that repeats an earlier row's;
- a **partly filled** row is unresolved (`ENTRY_ROW_PARTLY_PREFILLED`, `P`):
  filling around set cells is governed late swap's (Session 12);
- rows group by Contest ID, and a group whose rows disagree on the contest name
  or entry fee leaves every row in it unresolved (`ENTRY_GROUP_UNRESOLVED`, `V`,
  `entry_authority`, scoped to those rows); every other group ships.

Every preserved roster (resolved: exact current-slate IDs the shared validator
passes) joins the forbidden set: the baseline and C1 cut each from every solve, the C2
and SD3 banks never hold one, and every export audit refuses a filled roster
equal to one (`ENTRY_PREFILLED_LINEUP_REPEATED`, `V`, `distinct_lineups`, on
the generated row). A row that does not resolve stays out of the set: it is
no legal lineup, and a Showdown roster with a FLEX-role ID in the Captain cell
would share a legal lineup's person-level key without the DraftKings-ID cut
removing that lineup. The cell form is unverified against a real
DraftKings download with entered rows (ROADMAP Session 12).

One file per producer carries every group; each group stands or falls inside
it, and rows are never merged across producers. A group record, in `nfl baseline`'s report, the `run-slate` result and the pointer's
`coverage`: `contest_id`; `contest_name` and `entry_fee` (`null` when the rows
disagree) and the lists `contest_names`, `entry_fees`; `rows`; the Entry IDs by
kind (`blank`, `prefilled`, `partly_filled`) and by outcome (`filled`,
`unfilled`, `preserved`, `unresolved`); and `reasons`, each unfilled or
unresolved row's limitation codes (a file-wide gate's codes when none names it).

Does not establish: that a preserved lineup is a good one, or anything about a
contest beyond its ID, name and fee as the template states them.

## Latest deliverable pointer

Registered 2026-09-23 by Session 05 (R28). `LATEST_DELIVERABLE.json`,
`nfl_latest_deliverable_v1`, written by `delivery.py`, names the one entry file
a run would hand over. It sits in the run's output folder
(`<output-dir>/<run_id>/`), one per run: runs are immutable folders, and a
pointer wider than its run could name another slate's file. Since Session 06
`run-slate` publishes the baseline through it right after intake, and a review
CSV (Showdown, C3, or C1's export) replaces it through `replace` once the
readable review has been classified and before the workbook is written, so a
later failure cannot unpublish it. A run whose baseline did not publish
publishes the review CSV instead. Session 14 adds the delivery record.

| Field | Meaning |
|---|---|
| `schema_version` | Exactly `nfl_latest_deliverable_v1` |
| `published_at`, `run_id`, `producer` | UTC time, the run, and what built the file: `run-slate:baseline`, `run-slate:prior_review:SHOWDOWN`, `run-slate:prior_review:CLASSIC` (C3) or `run-slate:prior_review:CLASSIC_C1` (C1's export) |
| `file` | `path` relative to the pointer's folder (never absolute, never `..`), `sha256`, `bytes`, `file_kind` (`DK_REVIEW_ENTRY_CSV`; the baseline's is `nfl_baseline_entry_csv_v1`) |
| `inputs` | `salaries` and `entries`: the snapshot `path` and `sha256` the file was built from |
| `mode` | `CLASSIC` or `SHOWDOWN`, from a fresh parse of the entries snapshot |
| `coverage` | `delivered_entry_ids` and `unfilled_entry_ids`, in template order |
| `release_truths` | The file's `nfl_release_truths_v2`, with every limitation |
| `revalidation` | `status` `PASS` and the `checks_run` below |
| `supersedes` | `null` for a first pointer; after `replace`, the old pointer's and file's SHA-256, producer, delivered rows and whether it still revalidated |
| `warning` | `DELIVERY_STATE` is not upload clearance; `RELEASE_DECISION` still decides that |

The pointer is written to a temporary file in the same folder, flushed and
synced, then put in place with `os.replace`, so a reader sees the old pointer or
the new one and never part of either. A failed write leaves the old pointer
byte for byte and no temporary file. `run-slate` records the pointer's own
SHA-256 as `latest_deliverable` in `prior_review_hashes`.

Revalidation (`delivery.revalidate`) runs before every write and again on every
read, independent of whoever built the file, from fresh parses of both
snapshots. Each failure is a registered `V` code, and any one refuses:

| Check | Code |
|---|---|
| The name is not `DK_UPLOAD_*` and the file is inside the pointer's folder | `DELIVERABLE_UPLOAD_NAME_PROHIBITED`, `DELIVERABLE_OUTSIDE_RUN_FOLDER` |
| The truths deliver something from a valid file | `DELIVERABLE_STATE_NOT_DELIVERABLE` |
| The file exists and hashes to `file.sha256` | `DELIVERABLE_FILE_MISSING`, `DELIVERABLE_SHA256_MISMATCH` |
| Both snapshots hash to `inputs` and parse, in one mode | `DELIVERABLE_INPUT_SHA256_MISMATCH`, `DELIVERABLE_INPUT_PARSE_FAILED` |
| The file reparses in the template's roster columns | `DELIVERABLE_REPARSE_FAILED`, `DELIVERABLE_MODE_MISMATCH` |
| Its Entry IDs are the template's, in order | `DELIVERABLE_ENTRY_ORDER_MISMATCH` |
| Its filled and blank authorized rows are exactly the truths' delivered and unfilled rows | `DELIVERABLE_COVERAGE_MISMATCH` |
| `referee.audit_output_bytes` against the template: only filled roster cells differ | `DELIVERABLE_BYTE_AUDIT_FAILED` |
| `lineups.validate_lineup` passes every filled row | `DELIVERABLE_LINEUP_INVALID` |
| No two filled rows hold the same exact roster (R29; a different captain differs) | `DELIVERABLE_LINEUP_DUPLICATE` |
| The check itself finished | `DELIVERABLE_REVALIDATION_FAILED` |

It judges no evidence, model or policy; those travel in `release_truths`.

- `publish(root, deliverable)` writes a run's first pointer and refuses one that
  exists (`DELIVERY_POINTER_EXISTS`).
- `read_latest(root)` returns `None` when there is no pointer, refuses a
  malformed one (`DELIVERY_POINTER_INVALID`), and returns it only when its file
  revalidates.
- `replace(root, deliverable)` needs a pointer (`DELIVERY_POINTER_MISSING`),
  the same two input hashes (`DELIVERY_POINTER_INPUTS_DIFFER`) and, while the
  current file still revalidates, at least as many delivered rows
  (`DELIVERY_POINTER_COVERAGE_REGRESSION`). A current file that no longer
  revalidates gives way to any file that does, and `supersedes` says so.
- A pointer that cannot be built or written is `DELIVERY_POINTER_WRITE_FAILED`,
  and one whose bytes on disk are not the bytes written is
  `DELIVERY_POINTER_WRITE_MISMATCH`.
- `read_latest(root, run_id=...)` refuses a pointer another run left in a
  reused folder (`DELIVERY_POINTER_OTHER_RUN`).
- The same deliverable and the same `now` write byte-identical pointers;
  `run-slate` passes its pinned `--as-of` as `now`, the wall clock otherwise.

After a failure `run-slate`'s outer handler reads this run's pointer. A file
passed independent validation earlier in the run exactly when the pointer names
it and it revalidates now; the handler reports that file (`DELIVERY_STATE`,
`latest_deliverable`, and `release_truths` with the failed run's own v1 truths
beside the pointer's delivery half, plus `IMPROVEMENT_NOT_DELIVERED` when it is
the baseline) and never deletes it. It still removes every
`DK_UPLOAD_*.csv`, a name the pointer can never hold. A pointer that does not revalidate is reported under
`latest_deliverable_problems`, and its file is left on disk, unadvertised.

`delivery.discrepancy_limitations` splits a `;`-joined discrepancy and
`blocker_limitations` takes one blocker each; both build every limitation
through `GateRegistry.limitation` by the leading code, and a code the registry
does not hold is `GATE_CODE_UNCLASSIFIED` (`V`, fail closed).
`delivery.withholds` is true when any limitation is `V`.

Does not establish: upload clearance, certification, lineup quality, or any EV,
ROI, win, cash, ownership or edge claim. It says which validated file to hand
over and what it covers.

### `nfl_latest_deliverable_v2`

Registered 2026-09-24 by Session 11. `delivery.py` writes only v2 since then
and reads v1 and v2 (a v1 pointer's truths are `nfl_release_truths_v2`).

| Field | Added or changed |
|---|---|
| `schema_version` | Exactly `nfl_latest_deliverable_v2` |
| `coverage` | Adds `preserved_entry_ids`, `unresolved_entry_ids` and `entry_groups` (§ Entry groups) |
| `release_truths` | `nfl_release_truths_v3`; `v2` truths handed to `publish` or `replace` are written as `v3` with both new lists empty |
| `supersedes` | Adds `delivered_rows_by_group`, the replaced file's delivered rows per Contest ID (empty when it no longer revalidated) |

Revalidation adds three checks, each under an existing code: only the plan's
fillable rows may differ from the template, and every other row, prefilled or
partly filled or of an unresolved group, is its bytes exactly
(`DELIVERABLE_BYTE_AUDIT_FAILED`; the byte audit now also refuses a written
prefilled cell); the truths' preserved and unresolved rows are the plan's
(`DELIVERABLE_COVERAGE_MISMATCH`); and no filled roster equals a prefilled one
(`DELIVERABLE_LINEUP_DUPLICATE`). `replace` compares coverage per Contest ID: a
replacement that delivers fewer rows in any group than a current file that
still revalidates is refused (`DELIVERY_POINTER_COVERAGE_REGRESSION`, naming
the group), whatever its total. A reader of v1 sees delivered and unfilled rows
only, which was the whole template then.

## `run-slate` result, baseline first (Session 06)

Registered 2026-09-24 by Session 06 (R28, R29). The `prior_review` exits, the
pre-review blocked exit and the outer handler write `cowork_run.json` with
these fields beside the ones they always had. The `diagnostic` and `registered`
profiles' certify exit writes `baseline`, `latest_deliverable`,
`latest_deliverable_problems` and `latest_deliverable_meaning` beside its own
package: there a certified package, when `RELEASE_DECISION` says so, is
`certification`'s file, and `latest_deliverable` names the prior-only baseline
as the fallback. None changes a release truth or an exit code.

| Field | Meaning |
|---|---|
| `baseline` | The baseline step: `published`, `producer` (`run-slate:baseline`), `objective`, `path`, `sha256`, `DELIVERY_STATE`, `delivered_rows`, `unfilled_entry_ids`, its limitation codes, `report`, `wall_seconds` and `problems` (a publish refusal's codes, or `BASELINE_RUN_FAILED` when the step raised) |
| `improvement` | The run's own review file: `status` `DELIVERED` (it is the pointer's file; `replaced` is the pointer's `supersedes`), `WITHHELD` (it produced a CSV that a `V` code or a pointer refusal stopped; `withheld_by`, and the `V` codes as `reasons`) or `NOT_PRODUCED` (it blocked, crashed, never ran or wrote no file; its blockers as `reasons`), with its `stage` |
| `latest_deliverable` | The pointer read back and revalidated at the end of the run: the file to hand over, with its `producer`; `null` when there is none |
| `latest_deliverable_problems` | Why a pointer that exists did not revalidate |
| `DELIVERY_STATE`, `release_truths` | As § `nfl_release_truths_v2`: the delivery half describes `latest_deliverable`. With no pointer, the limitations also carry the pointer's and the baseline step's problems (`BASELINE_RUN_FAILED`, a publish refusal) |
| `next` | Opens with the baseline's path whenever it is the deliverable |

The baseline sits at `<output-dir>/<run_id>/baseline/`, a `nfl baseline` run
folder with run id `baseline`: `inputs/`, `intake.json`,
`DK_BASELINE_ENTRY_V1_baseline.csv` and `baseline_report.json`. It is built from
the run's `data/runs/<run_id>/inputs/` snapshots (its own copies hash the same),
with the pinned `--as-of` as its clock, the budget's 5 s per solve and 30 to
60 s (§ Deadline budget), the request's exclusions, and its official status file (R32). The pointer's `run_id` is the `run-slate`
run's, so the outer handler reads it back. A replaced baseline stays on disk,
byte for byte. The status workbook's Upload sheet names the pointer's file.

C1's export (rung 4) is `<output-dir>/<run_id>/review/DK_REVIEW_ENTRY_C1_<run_id>.csv`,
`file_kind` `DK_REVIEW_ENTRY_CSV`: the entries snapshot with C1's hash-checked
`assignments.csv` written in by `lineups.write_upload_bytes`, kept only after
`baseline.audit_baseline_bytes` passes the bytes on disk, the request's
exclusions and official status file included, and listed in `export.c1_export`. Refusals list nothing and
leave the baseline: `CLASSIC_C1_EXPORT_OUTPUT_EXISTS`,
`CLASSIC_C1_EXPORT_ASSIGNMENT_SHA256_MISMATCH`,
`CLASSIC_C1_EXPORT_OFFICIAL_STATUS_CHANGED` (the status snapshot is not the one
C1 read), `CLASSIC_C1_EXPORT_FAILED`,
`CLASSIC_C1_EXPORT_AUDIT_FAILED`, `CLASSIC_C1_EXPORT_POST_WRITE_HASH_MISMATCH`
(all `V`). The pre-lock manifest binds the assignment this file renders, not the
file. A run with a policy goes to C3, and takes this path only when the
relaxation controller drops its policy for rung 4 (§ Relaxation record).

A replacement never delivers fewer rows than the baseline while the baseline
still revalidates (`DELIVERY_POINTER_COVERAGE_REGRESSION`); a partial review
file never replaces a full baseline, and rows are never merged across the two.
A review CSV that replaced the baseline and then fails the read-back is
withheld like any refusal, and the baseline is put back through `replace`
(a current file that no longer revalidates gives way), so `supersedes` then
records the review file with `revalidation` `FAIL`.

Exit codes are unchanged: 0 when the run's own review completed, 2 when it did
not. A shipped baseline never turns a failed review into 0, and a refused C1
export is 2. A review the deadline skipped or stopped is 2 (Session 07).

Since Session 11 every `prior_review` exit and the pre-review exit carry
`entry_groups` (§ Entry groups) for the file the result describes, the outer
handler the pointer's; `baseline` adds `preserved_entry_ids` and
`unresolved_entry_ids`, and `latest_deliverable` adds those and `entry_groups`.
A policy (supplied, or a rung's) binds the plan's fillable rows in template
order, or since Session 11b a subset of them, and
`PORTFOLIO_POLICY_LINEUP_COUNT_MUST_MATCH_ENTRIES` counts every fillable row
(the request's `lineup_count` describes the file).

Since Session 11b every `prior_review` exit carries `row_sources`, each row the
review's own selection filled mapped to `POLICY`, `C1` or `SHOWDOWN_SEQUENTIAL`
(`null` when selection did not run), and a run with a policy adds to
`portfolio_policy`: `entry_count_denominator` is the policy's bound rows,
`bound_entry_ids` and `unbound_entry_ids` the rows it binds and the fillable rows
the fill covers (`null` when the policy did not validate far enough to say). Since
Session 11c a Classic file may mix `POLICY` and `C1` rows, as a Showdown file
mixes `POLICY` and `SHOWDOWN_SEQUENTIAL` ones.

Since Session 10 a run with a policy also carries `relaxation`, the run's
`nfl_relaxation_record_v1` record (§ Relaxation record); the pre-review exit
carries it only when the ladder relaxed or stopped at intake.

Since Session 07 every exit's result also carries `deadline`, the run's
`nfl_deadline_budget_v1` record (§ Deadline budget; `null` from the outer
handler when the budget itself could not be built), and the pre-review exit's
`stage` is `DEADLINE_IMPROVEMENT_SKIPPED` when the deadline, not an input,
stopped the review.

Does not establish: upload clearance, certification, lineup quality, or any EV,
ROI, win, cash, ownership or edge claim. It says which file to hand over, which
step made it, and why the other did not.

## Relaxation record (Session 10)

Registered 2026-09-24 by Session 10 (the 2026-09-12 lock-clock ruling, R28,
R29, R31). `nfl_dfs.relaxation` owns the rung ladder and `run-slate` walks it
inside one run when the run has a policy. The record, `nfl_relaxation_record_v1`,
is the result's `relaxation` field and `data/runs/<run_id>/relaxation/relaxation.json`.

**The ladder.** Classic rungs 0 to 3 are the generator's table (stack rules,
overlap, exposure fraction, bank halved at 3; `scripts/make_classic_policy.py`
is a wrapper over it); Showdown rungs 1 to 3 are `SHOWDOWN_RUNGS` (1: every
capped Captain fraction at least 0.25, zeroed Captains kept; 2: zeroed Captains
lifted and Captain caps at least 0.5; 3: no exposure caps, overlap at least 5;
`scripts/make_showdown_policy.py --rung`); rung 4 is no policy (C1, or
sequential Showdown selection). A rung's policy is the loosest of the policy it
replaces and the rung's table, dimension by dimension, so it never tightens: a
generator's rung-k policy becomes rung k+1 exactly. A supplied policy is
`SUPPLIED` and starts at the first rung that changes it.

**Triggers.** Read from the review's structured `selection_failure`
(`{status, origin, facts, error}` in `prior_review_reports`; `SelectionError`
carries `status` and `facts`), never from text.

| Step | Statuses | What the ladder does |
|---|---|---|
| `STRUCTURE` | `MODELED_BANK_INFEASIBILITY`, `INCOMPLETE_BANK_EXHAUSTION`, `STRUCTURAL_INFEASIBILITY`, `MODELED_BANK_INFEASIBLE_PROVEN`; a supplied policy whose only validation problems are `S` codes | The next rung that changes the policy; one the validator refuses on `S` codes is recorded in `attempts` and the next is tried |
| `THROUGHPUT` | `CANDIDATE_BANK_TIMEOUT`, `CANDIDATE_BANK_SEARCH_LIMIT`, `CANDIDATE_BANK_TIME_LIMIT`, `PORTFOLIO_SELECTION_TIMEOUT`, `PORTFOLIO_SELECTION_SEARCH_LIMIT`, `PORTFOLIO_SELECTION_TIME_LIMIT`, `DEADLINE_POLICY_SEARCH_EXCEEDS_WINDOW`; intake `search_budget` codes | Once per rung, the same structure on a re-sized bank (Classic: `classic_limits` at the slowest of this host's rate and this run's measured one, to the window left; a joint limit halves the bank and keeps at least the joint budget that ran out, within the window's 20%. SD3: half what it built). Then rung 4 |
| `SOLVER_ERROR` | `CANDIDATE_BANK_SOLVER_ERROR`, `PORTFOLIO_SELECTION_SOLVER_ERROR` (`selection_claims`, `P`) | As `THROUGHPUT`: one smaller bank, then rung 4; never a structural rung |
| `BANK_DEPTH` | `CANDIDATE_BANK_EXHAUSTED_INCOMPLETE` (SD3) | Once, the SD3 bank deepened to `max(6 x entries, 1.5 x its size)`, then `STRUCTURE` |

Never a trigger: `BOUNDED_TIME_LIMIT_STOP`, `BOUNDED_SEARCH_LIMIT_STOP`,
`FEASIBLE_LIMIT_ACTUAL_CANDIDATE_BANK` (Session 08 delivers and names them), and
`SOLVER_RETURNED_NO_LINEUP` (C1 or Showdown out of distinct lineups: rung 4 is
the floor, and the baseline stays the file with its unfilled Entry IDs).

**Never relaxed.** `require_unique_lineups` (R29) is true in every rung's
policy; a Classic policy's `exact_exclusions`, a Showdown policy's
`excluded_people`, and any person a policy caps at zero entries (a Classic
`maximum_entries` of 0, a team or game capped at 0, a Showdown combined fraction
of 0) stay excluded at every rung, and rung 4 passes their exact DraftKings IDs
to the review as operator exclusions. A subset policy's exclusions bind only its
rows at every policy rung; rung 4 cannot tell rows apart, so it carries them to
every row (Session 11b: widening a fade only tightens, and an exclusion is never
relaxed). A fraction that only floors to zero
entries is a cap, not an exclusion, and is relaxed. A supplied Showdown policy
with `require_unique_lineups: false` runs every rung with it true (R29), and the
record says so (`supplied_require_unique_lineups`). Official inactives and request exclusions are re-derived by the
validator from the same run. No evidence gate is on the ladder.

**The window.** Each rung must fit the improvement window less the last
attempt's measured pre-selection time: a C2 rung's declared bank and joint
budget (`classic_limits` against that window), an SD3 rung 2.5 s (the joint
solve's 20% share must reach 0.5 s), rung 4 0.5 s per lineup plus one. A C2 or
SD3 rung that does not fit takes rung 4; rung 4 not fitting stops the ladder
(`RELAXATION_LADDER_STOPPED`) and the baseline stays the file. A rung the
validator refuses on a code no rung loosens is a defect
(`RELAXATION_RUNG_UNBUILDABLE`, in `defects`), and rung 4, which needs no
generated policy, is still tried; a rung that cannot be written or validated at
all stops the ladder under the same code.

**Artifacts.** Each rung's policy is written to
`data/runs/<run_id>/relaxation/attempt_<n>_rung_<r>[_bank]/`:
`portfolio_policy.json` (canonical bytes), `portfolio_policy_validation.json`
and `portfolio_policy.normalized.json`, validated by the supplied-policy
validator against the hash of the bytes written, with the run's outside
exclusions; the review re-checks both hashes before selection as it does a
supplied one. Attempt 0's review root is `prior_review/`; attempt n's is
`prior_review_attempt_<n>/`, reusing attempt 0's frozen priors when it built them.

| Field | Meaning |
|---|---|
| `schema_version` | `nfl_relaxation_record_v1` |
| `mode` | `CLASSIC` or `SHOWDOWN` |
| `started_from`, `final_rung`, `final_policy` | The supplied rung and its binding; the rung the last attempt ran and its binding (`null` for rung 4) |
| `attempts` | One per review attempt: `attempt`, `rung`, `run_root`, `policy`, `showdown_candidate_limit`, `outcome`, `failure` (the trigger, or `null`), `elapsed_seconds`, `pre_selection_seconds`; and one per rung the validator refused: `attempt` `null`, `outcome` `REFUSED_AT_VALIDATION`, `codes`, `policy` |
| `relaxations` | One per relaxed constraint (below) |
| `stop` | `RELAXATION_LADDER_STOPPED:<detail>` when the window ended the ladder, `RELAXATION_RUNG_UNBUILDABLE:<detail>` when the next rung could not be built at all, else `null` |
| `defects` | `RELAXATION_RUNG_UNBUILDABLE:<detail>` for each rung the validator refused on a code no rung loosens |
| `supplied_require_unique_lineups` | The supplied policy's own value; every rung requires distinct lineups whatever it says |
| `never_relaxed`, `does_not_establish` | As named |

Each relaxation: `sequence`, `attempt` (the one it fed), `step` (`BANK`,
`STRUCTURE`, `NO_POLICY`), `constraint` (`stack_rules.<rule_id>`,
`player_exposure_bounds`, `team_exposure_bounds`, `game_exposure_bounds`,
`groups`, `max_pairwise_person_overlap`, `search_limits`,
`max_combined_person_exposure`, `max_captain_exposure`,
`candidate_bank.candidate_limit`, `portfolio_policy`), `class`, `family` and
`provenance` (the registry's), `original`, `final`, `trigger`, `trigger_kind`,
`trigger_origin` (`SELECTION`, `DEADLINE`, `INTAKE`), `trigger_detail`,
`rung_from`, `rung_to`, `why`, `at_utc` (the run's clock), `elapsed_seconds`,
`entry_ids` (the Entry IDs the supplied policy binds, which every rung's policy
binds too: the plan's fillable blank rows, or since Session 11b the subset the
supplied policy names; rung 4 has no policy and fills every fillable row, and
its window check counts every fillable row), `policy`
(the new rung's binding), `limitation_code` and `limitation_text`.

Codes, on every exit that reports the record, the delivered file's or the
baseline's, the pre-review exit included: `RELAXATION_STRUCTURE_RELAXED` and
`RELAXATION_POLICY_DROPPED` (`portfolio_bounds`), `RELAXATION_BANK_RESIZED`
(`search_budget`), `RELAXATION_LADDER_STOPPED` (`delivery_deadline`), each `S`,
`CONSTRUCTION_PREFERENCE`; `RELAXATION_RUNG_UNBUILDABLE` (`stage_failure`, `P`,
`CERTIFICATION`). The result's `portfolio_policy` keeps `valid` and the source
and normalized hashes of the supplied policy, and adds `enforced_rung`,
`enforced_policy` and `enforced_policy_is_supplied`: its `enforcement_status`,
`selector` and `independent_audit` describe the enforced policy.
`RELEASE_DECISION` stays `DO_NOT_UPLOAD`, and exit codes keep their meaning: 0
only when the last attempt's review completed.

Does not establish: upload clearance, certification, lineup quality, or that a
tighter policy was infeasible outside the reported bank.
