# W4 session prompt: R02 prior-only `cowork-run` profile (paste into a new session)

Work tranche W4 in `backlog.md`, the half that is still open. The selection and
export halves are `DONE`: `select` and `review-export` exist, are tested, and ran
the real NE@SEA opener end to end in 0.48 seconds. What is missing is the single
gated entry point. Today the path is six CLI calls that a session has to
orchestrate by hand from a skill, and `cowork-run` cannot express it at all.

Read `CLAUDE.md`, `backlog.md` (tranche table, and "Verified runtime constraints
for every session below"), `docs/PRODUCTION_READINESS_REVIEW_2026-09-08.md`
finding R02, the `nfl-showdown-lineups` skill, `src/nfl_dfs/cowork.py`, and
`_command_cowork_run` in `src/nfl_dfs/cli.py` before writing anything.

Goal: `cowork-run --profile prior_review` takes a DK Showdown salary CSV and a
DKEntries CSV and produces the byte-audited bulk-entry CSV, stopping only where a
human decision is genuinely required. No new economics, no new model.

## Step 0: runtime

```sh
export NFL_DFS_VENV_DIR=/tmp/nfl-cowork-venv
export NFL_DFS_UV_CACHE_DIR=/tmp/nfl-uv-cache
export NFL_DFS_UV_PYTHON_DIR=/tmp/nfl-uv-python
sh ./nfl.sh setup
sh ./nfl.sh test -q -p no:cacheprovider --ignore=.pytest_cache tests
```

Expect 244 collected, 243 passed, 1 skipped. Report the counts. The three env
vars are required: the Cowork bridge refuses deletion inside a mounted folder, so
`uv` cannot extract an interpreter there. If `device_bash` reports "Failed to
create bridge sockets", the device shell is down for the session: stage the repo
into the cloud container, build the venv with `pip` (not `uv`, which is throttled
there to uselessness), and commit changed files back with `device_commit_files`.

Do not run the engine in place in the mounted folder. `doctor` correctly reports
`pass_status: false` there because `registry.py` cannot open a SQLite database in
any journal mode but `MEMORY`, and `cowork-run` gates on `pass_status`. Work from
a local-disk copy of `src`, `tests`, `templates`, `config`, `pyproject.toml` and
`uv.lock`, keeping the mounted repo as the source of truth for edits.

## Step 1: measure the gate before you move it

`required_next_inputs` (`cowork.py:377`) raises five blockers. Four of them exist
only for certification: `CONTEST_PAYOUT_REQUIRED`,
`ADVERTISED_PRIZE_VALUE_REQUIRED`, `FIELD_SIZE_REQUIRED` and
`OFFICIAL_STATUS_REQUIRED`. A prior-only review export needs none of them:
`review_export.py` runs legality, an independent byte audit against the source
template, a reparse and a SHA-256, and never touches a payout table or field size.

`_cowork_core_blockers` (`cli.py:2021`) already filters `OFFICIAL_STATUS_REQUIRED`
out of the gating set while leaving it in the reported list. That is the pattern
to extend, not to duplicate: decide per profile which blockers gate, and keep the
full list visible in the report and the review workbook.

Write down, before changing anything, the exact current behaviour of
`cowork-run` on the frozen NE@SEA inputs in
`data/runs/20260909-showdown-ne-sea/inputs/`. That is your regression baseline.

## Step 2: the profile

1. Add `prior_review` to the accepted profile set at `cowork.py:214`. The default
   stays `diagnostic`. `registered` behaviour must not change in any way.
2. Under `prior_review`, the required inputs are the prior chain, not economics:
   salary CSV, entries CSV, and either a resolvable frozen prior package or
   permission to build one. Emit named blockers in the same style when they are
   missing.
3. Orchestrate the chain that the skill currently drives by hand:
   `priors-propose` → identity gate → `priors-freeze` → `project` → `select` →
   `review-export`. Each stage keeps its own artifacts and hashes in the run
   folder. A stage failure stops the run with that stage's own named error; no
   partial export is ever written.
4. Honour the two-phase identity gate. `projection.py` accepts only
   `match_method="EXACT"`, so a package cannot be frozen on a guess. Auto-accept a
   unique league-wide name and position match **only when the person is
   DK-flagged `OUT` or `IR`**, because the availability contract makes those
   people unselectable and an accepted-but-uncertain identity can then never
   reach a lineup. Anything unresolved and available stops the run and reports the
   candidate provider ID, the conflicting nflverse team and the roster status.
   Record every auto-accept and its reason.
5. Re-fetch rather than reuse a stale package. Measured on 2026-09-08: the frozen
   team prior carried `expiry_basis: MARKET_LINE_MOVES_INTRADAY` and
   `expires_at: 2026-09-09T04:37:46Z`, roughly twenty hours before the
   2026-09-09 20:20 ET kickoff. A same-day re-run is therefore the normal case,
   not the exception. Detect the expiry against `as_of` and rebuild; never widen
   an expiry to make a run succeed.
6. Weather still has no reachable source from a session and the enum has no
   `UNKNOWN` member. Under `prior_review`, resolve `roof` from `games.csv` on its
   own, and where the roof is open or blank, block with a named blocker asking for
   the `api.weather.gov` capture and its URI and `generatedAt`. Do not default the
   enum.

## Non-negotiables

- `MODEL_STATUS` stays `PRIOR_ONLY` and `RELEASE_DECISION` stays `DO_NOT_UPLOAD`
  on every path through the new profile, including the success path. There is no
  argument, flag, or profile value that can make this profile emit anything else.
- Never route a generated assignment into the manual-guardrail path to bypass the
  model gate, and never relabel prior-only output as certified.
- Do not edit `projection.py`, `contracts.py` or `evidence.py` without checking
  current ownership in `backlog.md`. Tranche W2 held them on 2026-09-08.
- Do not add an ownership, leverage, correlation or duplication model here. That
  gap is real and it is the largest one against the product objective, but it is
  not this tranche and mixing it in will make both unreviewable.
- `AvgPointsPerGame` stays quarantined to untouched raw DK bytes.
- Uploading to DraftKings stays a manual operator action.

## Acceptance before you call W4 done

1. One `cowork-run --profile prior_review` invocation, given only the two CSVs in
   `data/runs/20260909-showdown-ne-sea/inputs/`, produces a bulk-entry CSV with
   `FILE_VALID: true` and empty `problems`, and a diff against the source
   template shows only the reserved entry rows changed.
2. The same invocation with the identity gate unresolved for an available person
   stops with that named blocker, writes the review workbook, and writes no
   export.
3. An expired prior package triggers a rebuild, and a hash mismatch in any frozen
   artifact fails closed.
4. `profile=diagnostic` and `profile=registered` behaviour is unchanged, proven by
   the existing tests still passing untouched.
5. New pytest coverage for the profile's blocker set, the auto-accept rule, the
   expiry rebuild, and the success path. Report the full suite counts.
6. The `nfl-showdown-lineups` skill is updated to call the one command, with the
   six-call sequence kept as the documented fallback.

## Finish the session by

Updating `backlog.md` (W4 status, next `READY` tranche, any new constraint
learned) and appending a dated `changelog.md` entry under `Unreleased` with the
exact commands run, their counts, remaining blockers, and open `[BEN: ...]`
flags. Do not stage or commit anything without my explicit path list.
