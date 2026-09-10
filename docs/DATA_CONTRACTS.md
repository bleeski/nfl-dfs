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
least one frozen prediction/model artifact and one versioned scenario bank.
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
