# W1 session prompt: R01 prior adapter (paste into a new session)

Work tranche W1 in `backlog.md`. Read `CLAUDE.md`, `backlog.md`,
`docs/PRODUCTION_READINESS_REVIEW_2026-09-08.md` (finding R01),
`docs/SHOWDOWN_FIRST_PRODUCTION_PLAN.md` sections 3 and 4, and
`src/nfl_dfs/projection.py` before writing anything.

Goal: close R01. The `project` command already validates and transforms frozen
prior artifacts. Nothing in the repository produces those artifacts. Build the
deterministic adapter that does, scoped to a single Showdown game.

## Step 0: runtime

Try `sh ./nfl.sh setup` once and report the result. GitHub egress from the session
is confirmed working, so the CPython download that blocked this on 2026-09-01 may
now succeed; the device VM's `/sessions` mount is 100% full, which may still block
it. If it works, you can run `sh ./nfl.sh test` yourself, and say so in the
changelog because that unblocks every later tranche. If it fails, stop retrying:
you cannot execute the suite. Write the code and its tests, then ask me to run
`.\nfl.ps1 test -q` in PowerShell and paste the output, and iterate until green.

## Step 1: ask me for what only I have

Ask once, batched, before designing anything:

1. The DraftKings Showdown salary CSV for the target contest. Without it there are
   no DK IDs to map, so the live identity map cannot be produced.
2. The market total and spread. Decide with me between nflverse schedule fields
   (reachable, but they carry no per-line timestamp or book, and
   `TeamSourceRecord.market_observed_at` requires a timezone-aware value) and a
   sportsbook capture I run myself and hand you.
3. `weather_state` for the game. The enum has no UNKNOWN member and
   `api.weather.gov` is unreachable from the session.
4. Confirmation of the target contest. The plan retargets the first prior-only
   Showdown review run to a Sunday 2026-09-13 single-game contest, not the
   2026-09-09 opener.

Do not invent a value for any of these. Use a `[BEN: ...]` flag and stop the
affected branch instead.

## Step 2: confirm which sources are actually reachable

Session egress reaches `raw.githubusercontent.com` and `github.com` only.
`api.sleeper.app`, `api.weather.gov`, and `api.the-odds-api.com` all fail to
connect, so three of the four non-GitHub hosts allowlisted at `sources.py:18` are
unavailable to you. Before designing the transformation, enumerate the candidate
nflverse URLs and record which ones resolve, including whether GitHub release
assets resolve or only `raw.githubusercontent.com` paths do. Report the list.
Design only against what you proved reachable. Never bypass `sources.py`.

## Step 3: build the adapter

Implement it as a new module in `src/nfl_dfs/` with a launcher subcommand, not a
loose script, so it carries a `parser_version`, is covered by pytest, and is
reachable from both launchers. It must emit exactly the three artifacts `project`
consumes, validated by the existing contracts in `src/nfl_dfs/projection.py`:

- Team prior, `schema_version: nfl_team_projection_source_v1`. Per team:
  `provider_team_id`, `game_id`, `plays_mean` [35,95], `pass_rate` [0.2,0.85],
  `pass_yards_per_attempt` [2,15], `rush_yards_per_attempt` [1,10],
  `touchdowns_mean` [0,10], `field_goals_mean` [0,8], `turnovers_mean` [0,6],
  `sacks_allowed_mean` [0,10], `uncertainty` [0,1], `market_total` [20,100],
  `market_spread` [-40,40], `market_observed_at`, `weather_state`, `era`,
  `evidence_state`.
- Player prior, `schema_version: nfl_player_opportunity_source_v1`. Per person:
  `provider_player_id`, `provider_team_id`, `position`, `qb_attempt_weight`,
  `carry_weight`, `target_weight`, `catch_rate`, `yards_per_target` [0,30],
  `rushing_td_weight`, `receiving_td_weight`, `role_capacity`, `evidence_state`.
  All weights are [0,1]. The producer masks each weight to its eligible positions
  and normalizes it against the eligible team total, and it rejects an all-zero or
  missing group rather than filling it uniformly, so every eligible group present
  in the pool needs real non-zero support.
- Identity map, `schema_version: nfl_projection_identity_map_v1`, with
  `salary_artifact` carrying the salary CSV's SHA-256 as `artifact_id`, one
  `team_mappings` entry per team, and one `player_mappings` entry per person
  (`provider_player_id`, `provider_team_id`, `dk_id`, `underlying_id`, `team`,
  `position`, optional `dk_role`, `match_method`, `evidence_state`).

Every artifact needs `ArtifactMetadata`: `source_uri`, `captured_at`,
`observed_at`, `expires_at`, an approved `license_decision`, `parser_version`,
`evidence_state`, and non-empty `coverage`. `observed_at` may not follow
`captured_at` by more than five minutes and `expires_at` may not precede
`observed_at`. Set expiry from the real staleness of each source, not a
convenient default.

Rules that are not negotiable:

- Every number traces to a fetched artifact through a documented transformation.
  No hand-typed values, no LLM-authored numbers, no coefficient fitting, no
  imputation, no uniform filling.
- Archive the raw fetched bytes under a content-addressed path in `data/`, with
  hashes, source URIs, captured and observed times, parser version, and license
  decision. The package must resolve without depending on files outside it.
- `AvgPointsPerGame` stays quarantined to untouched raw salary bytes.
- Do not edit the ledger emission code in `projection.py` or the validators in
  `contracts.py` / `evidence.py`. Tranche W2 owns those files for the R08 expiry
  repair, and concurrent edits will collide.
- Showdown pools list each person twice, as CPT and FLEX. One person gets one
  player mapping and one prior record. Verify how the producer and loader treat K
  and DST rows before assuming they work: the review's retained probe shows a
  zero-capacity kicker still averaging 7.99 points across 984 of 1,000 scenarios,
  which is the R03 defect that tranche W3 owns. Report what you find rather than
  papering over it.

## Acceptance before you call W1 done

1. Two runs from the same frozen raw artifacts produce byte-identical JSON.
2. Every person in the supplied Showdown pool resolves to exactly one mapping and
   one prior record, kickers and DST included, with both DK roles reconciled.
3. Missing coverage, an ambiguous provider ID, an unmapped DK ID, or a hash
   mismatch fails with a named actionable error and publishes no partial package.
4. `project` accepts the three artifacts and publishes `team_projections.csv`,
   `player_opportunities.csv`, and a reconciled `source_ledger.json`.
5. New pytest coverage exists for the reproducibility, coverage-failure, and
   role-reconciliation cases, and the full suite passes (report the counts).
6. The output is still explicitly prior-only. Do not call it a projection model,
   EV, ROI, win probability, or edge.

## Finish the session by

Updating `backlog.md` (W1 status, next `READY` tranche, any new constraint learned)
and appending a dated `changelog.md` entry under `Unreleased` with the exact tests
run, their counts, remaining blockers, and open `[BEN: ...]` flags. Do not stage or
commit anything without my explicit path list.
