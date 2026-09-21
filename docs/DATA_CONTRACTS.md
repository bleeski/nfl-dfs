# Data Contracts

All headers and identities are strict. Files are UTF-8 CSV unless the original
DraftKings input is CP1252. Times must be timezone-aware ISO 8601 values.

## Cowork run request

`cowork-run` (aliased `run-slate`) emits `nfl_cowork_run_request_v2` and accepts
both `v1` and `v2`. Unknown keys are rejected.

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
weather_state           games.csv roof: dome/closed/open only; otherwise operator-supplied
```

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
stops publication and reports the smallest evidence action. Every selected
person also needs a fresh exact-ID official ACTIVE/INACTIVE row. Nonselected
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

Runtime paths, run IDs, timestamps and solver elapsed seconds are excluded from
these canonical payloads, so identical immutable inputs reproduce both hashes.
`FILE_VALID` describes these two review JSON files only. `EVIDENCE_STATE`,
`MODEL_STATUS=PRIOR_ONLY`, and `RELEASE_DECISION=DO_NOT_UPLOAD` are separate.
C1 writes no Classic assignment CSV, `DK_REVIEW_ENTRY_*.csv`, or
`DK_UPLOAD_*.csv`; C2 adds policy/candidates/joint selection as documented
below, and C3 owns readable review, downstream independent export audit, and
exact-template export.

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
denominator:

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
bytes, solve count, nodes, maximum reported gap, and terminal model status.
The bank distinguishes `EXHAUSTIVE_COMPLETION`, `BOUNDED_COMPLETION`,
`CANDIDATE_BANK_TIMEOUT`, `CANDIDATE_BANK_SEARCH_LIMIT`,
`CANDIDATE_BANK_SOLVER_ERROR`, and `STRUCTURAL_INFEASIBILITY`. A bounded bank
never asserts full-slate optimality.

The joint MILP chooses exactly the Entry-ID count from the actual canonical
bank under all hard player/team/game/group/stack, uniqueness, and pair-overlap
bounds. `OPTIMAL_ACTUAL_CANDIDATE_BANK` is the only accepted solver status and
means optimal only over that reported bank. `MODELED_BANK_INFEASIBILITY` applies
only to an exhaustive modeled bank; `INCOMPLETE_BANK_EXHAUSTION` is the distinct
bounded-bank result. Timeout, search-limit, non-optimal, invalid-integrality,
and solver-error results fail closed. Selected lineups are paired one-to-one
with `entry_ids` in exact template order; cycling is prohibited.

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

Only `ENFORCED_AND_INDEPENDENTLY_AUDITED`, C2 audit `PASS`, bank status
`EXHAUSTIVE_COMPLETION` or `BOUNDED_COMPLETION`, and joint status
`OPTIMAL_ACTUAL_CANDIDATE_BANK` over `ACTUAL_CANDIDATE_BANK` can reach C3
publication. A bounded bank remains explicitly incomplete and never implies
full-slate optimality.

Successful C3 publication is atomic and adds:

| Artifact | Contract |
|---|---|
| `classic_review_export_audit.json` | Canonical `prior_only_classic_export_audit_c3_v1`; every boundary hash, recomputed fact, exact output hash, status, limitations, truths, and one next action |
| `DK_REVIEW_ENTRY_<label>.csv` | Exact reserved-entry template bytes with only nine previously blank authorized roster cells rewritten for each exact Entry ID in template order |
| `prior_only_readable_review.json` | Canonical `prior_only_readable_review_classic_c3_v1` display data independently reconstructed from the accepted artifacts |
| `prior_only_readable_review.html` | Self-contained escaped rendering of the canonical readable JSON |
| `NFL_DFS_Cowork_Review_<run-id>.xlsx` | Eight sheets: Run Control, Evidence Paste, Portfolio, QA, Upload, Exposure, Review Evidence, and Artifacts |

The CSV writer preserves BOM/encoding, header, line endings, row order,
quoting, physical-line geometry, unrelated rows, contest facts, and every
non-roster byte. It reparses and byte-diffs both proposed and final bytes and
binds the final SHA-256 into the audit, readable package, and run record. A
partial write, existing/stale target, mismatched Entry ID, prefilled roster
cell, unauthorized row, mutation, audit failure, post-write disagreement, or
display disagreement removes or withholds all new C3 artifacts.

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
cross-person or CPT/FLEX-reversed identities fail. `entry_ids` must be the exact
full requested sequence, with no duplicate, subset, reordered entry or silent
`lineup_count` reduction.

Fractions are JSON numbers in `[0,1]`, with the required unit
`FRACTION_0_TO_1`. Booleans, numeric strings, nonfinite numbers, negative values,
bare values such as `50`, and any alternative unit fail. The denominator is all
requested entries. Each integer maximum is
`floor(fraction * requested_entry_count)` using exact decimal arithmetic:

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
errors. An optimal result is explicitly scoped to the actual candidate bank.
Only an infeasible joint MILP over a bank whose fill enumeration ended in a
proven lineup-model `INFEASIBLE` state is `MODELED_BANK_INFEASIBLE_PROVEN`;
infeasibility over a bounded incomplete bank is
`CANDIDATE_BANK_EXHAUSTED_INCOMPLETE`, never a full-slate mathematical claim.

Assignment never cycles for policy-bearing requests. The output must retain the
exact policy Entry-ID order once each. Immediately before export, an independent
audit strictly reparses the canonical normalized-policy artifact, re-reads the
assignment artifact and recomputes DraftKings legality, canonical lineup
identities, combined-person counts, Captain counts, uniqueness and every pairwise
underlying-person overlap from exact roster IDs. It uses the independently read
limits and binds the current salary, entry, source-policy, normalized-policy and
assignment bytes to their SHA-256 values; it reconciles, but never trusts,
selector summaries.

Only `enforcement_status=ENFORCED_AND_INDEPENDENTLY_AUDITED` may write a new
`DK_REVIEW_ENTRY` CSV. Invalid policies, the unsupported diagnostic profile,
necessary-capacity failures, timeout/search/solver states, incomplete-bank
exhaustion, assignment coverage/order failures, audit disagreement or artifact
mutation preserve earlier outputs and write no new review CSV. Every outcome
remains `MODEL_STATUS=PRIOR_ONLY` / `RELEASE_DECISION=DO_NOT_UPLOAD`; an audited
review file is not an upload package or an economics/model-quality claim.
Requests without a policy retain their SD1/SD2 selection and assignment behavior.

## SD5 prior-only readable review

A successful Showdown `prior_review` creates canonical
`prior_only_readable_review.json` with schema
`prior_only_readable_review_sd5_v1`, a self-contained escaped HTML rendering,
and an extended review workbook. This is a presentation contract, not a new
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

Canonical JSON and HTML are written atomically and reported with independent
SHA-256 values. HTML markup is escaped. Every user/provider-controlled workbook
string is stripped of illegal control characters for display and prefixed with
an apostrophe when a leading or whitespace-prefixed `=`, `+`, `-` or `@` could
be spreadsheet-active. This display escaping never rewrites the bound source
bytes or exact IDs in JSON/CSV artifacts.

Any missing file, hash change, malformed record, semantic disagreement, policy
or audit mismatch, roster mutation, entry-order/metadata change or post-write
hash failure raises a named `READABLE_REVIEW_*` discrepancy. The Cowork command
then reports `FILE_VALID=false`, stops at stage `READABLE_REVIEW`, exits 2,
preserves artifacts already written earlier in the run, and does not expose a
new top-level `bulk_entry_csv` path. No readable-review success may alter
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
