# W2 session prompt: R08 source expiry, R07 selection objective (paste into a new session)

Work tranche `W2` in `backlog.md`. It is `READY`, it owns `projection.py`,
`contracts.py` and `evidence.py`, and nothing else may touch those three until it
lands. `W4` is `DONE` and pushed at `f318882` on
`codex/s6a-deterministic-projection-producer`, so `cowork-run --profile
prior_review` is now the live consumer of everything you are about to change.

Read `CLAUDE.md`, `backlog.md` (tranche table, and "Verified runtime constraints
for every session below"), `docs/PRODUCTION_READINESS_REVIEW_2026-09-08.md`
findings R07 and R08, then `src/nfl_dfs/projection.py`,
`src/nfl_dfs/contracts.py`, `src/nfl_dfs/evidence.py`, `src/nfl_dfs/portfolio.py`
and `src/nfl_dfs/prior_review.py` before writing anything.

Goal: a frozen package carries its own expiry across every boundary and goes
stale at its real expiry no matter who copies it, and portfolio selection stops
changing when the scenario count changes. No new economics beyond R07's stated
repair, no ownership model, no new sources.

## Step 0: runtime

```sh
export NFL_DFS_VENV_DIR=/tmp/nfl-cowork-venv
export NFL_DFS_UV_CACHE_DIR=/tmp/nfl-uv-cache
export NFL_DFS_UV_PYTHON_DIR=/tmp/nfl-uv-python
sh ./nfl.sh setup
sh ./nfl.sh test -q -p no:cacheprovider --ignore=.pytest_cache tests
```

Expect 279 collected, 278 passed, 1 skipped. Report the counts.

Two runtime facts measured on 2026-09-08, both recorded in `backlog.md`:

- The device VM's `$HOME` (`/sessions`) was 100% full with 794MB free on `/`.
  Check `df -h /` first and put the local-disk working copy in `/tmp`, not
  `$HOME`. If `/tmp/nfl-cowork-venv` exists but is owned by another uid,
  `sh ./nfl.sh setup` fails with `Permission denied` and a fresh venv needs about
  603MB. Compare that venv's installed versions against `pyproject.toml`; when
  they match pin for pin, run the suite against it with
  `PYTHONPATH=<working copy>/src` instead of rebuilding.
- Never run the engine in place in the mounted folder. `doctor` reports
  `pass_status: false` there because the bridge refuses deletion and
  `registry.py` cannot open SQLite in any journal mode but `MEMORY`. Work from a
  local-disk copy of `src`, `tests`, `templates`, `config`, `pyproject.toml`,
  `uv.lock` and `nfl.sh`, keeping the mounted repo as the source of truth for
  edits. Do not run `git status` inside the mount; it leaves a `.git/index.lock`
  it cannot unlink.

If `device_bash` reports "Failed to create bridge sockets", the device shell is
down for the session: stage the repo into the cloud container, build the venv
with `pip` (not `uv`, which is throttled there to uselessness), and commit
changed files back with `device_commit_files`.

## Step 1: reproduce both defects before you repair them

Write both probes down as failing tests first. They are your regression baseline.

**R08.** `LedgerEntry` in `contracts.py:97` has `captured_at` and `observed_at`
and no `expires_at` and no `evidence_state`. `projection.py:276`
(`_validate_metadata`) checks `expires_at` and evidence state against the
supplied `as_of`, and `projection.py:580` (`_ledger_entry`) then drops both on
the floor. `evidence.py:311` (`validate_source_ledger`) checks URI policy,
hashes and future timestamps, never staleness. The review's own probe: a package
whose source metadata expired September 5 was accepted at a September 8 clock.
Reproduce that exactly.

**R07.** `portfolio.py:123` and `portfolio.py:281` both compute
`mean - 1.96 * standard_error` as the selection objective. The penalty shrinks
with the square root of scenario count, so the computation budget is part of the
economic preference. The review's probe: two candidates on a fixed 100-scenario
payout distribution selected the constant-1.5 candidate; replicating those same
rows 100 times, with the empirical distribution unchanged, selected the variable
candidate with mean 2.0. Reproduce that reversal.

## Step 2: R08, preserve expiry across every boundary

1. Extend the consumed contract so a ledger entry carries source expiry,
   evidence scope and state, transformation version, and its input dependency
   bindings. Version the contract; a schema bump is expected here.
2. Re-evaluate freshness at selection and certification time against a live
   release clock, and keep historical replay time separate from it. A copied
   ledger and a fresh market timestamp must not renew old player evidence.
3. Archive referenced raw sources under managed content-addressed paths inside
   the package, so a copied package resolves without the original attachment
   paths and without a Windows-to-Linux path rewrite. `projection.py` currently
   references originals by absolute path and archives nothing.
4. `prior_review.py` is the first real consumer of this and shows exactly where
   it hurts. `resolve_frozen_artifact` searches four candidate directories for
   `<sha256>.csv` because a frozen package is not self-contained; once packages
   archive their own sources, that resolver should shrink to a lookup inside the
   package with the search kept only as a documented fallback.
   `resolve_prior_package` also reads `expires_at` straight out of artifact
   metadata, which is a second implementation of the freshness rule. Route it
   through the shared contract instead of leaving two.

## Step 3: R07, separate risk preference from estimation uncertainty

1. Replace the LCB objective with a fixed, declared risk measure and risk
   preference that does not move with scenario count. Report Monte Carlo
   uncertainty separately rather than folding it into the objective.
2. Account for dependent and repeated samples and effective sample size.
   Duplicated rows are not new information and must not change the answer.
3. Preserve paired comparisons where uncertainty genuinely is the question.
4. Do not change what the objective is trying to maximize beyond removing the
   scenario-count dependence. R05 and R06 own the field economics and the
   candidate and diversity repairs, and they are `BLOCKED` behind this tranche.

## Non-negotiables

- `MODEL_STATUS` stays `PRIOR_ONLY` and `RELEASE_DECISION` stays
  `DO_NOT_UPLOAD` everywhere it is today. No gate is weakened to make a run
  succeed, and no expiry is ever widened.
- `cowork-run --profile prior_review` must still produce a `FILE_VALID` export
  from the two frozen NE@SEA CSVs, and `diagnostic` and `registered` behaviour
  must not change. `tests/test_prior_review_profile.py` stubs the projection
  producer through `_StubProjection`, which mirrors the `ProjectionPackage`
  attribute surface (`output_dir`, `team_projections`, `player_opportunities`,
  `source_ledger`, `hashes`, `input_hashes`). Change that surface and you update
  the stub in the same commit.
- Do not add an ownership, leverage, correlation or duplication model here. That
  gap is real and it is the largest one against the product objective, but it is
  R05, R06 and S7 work.
- `AvgPointsPerGame` stays quarantined to untouched raw DK bytes.
- Uploading to DraftKings stays a manual operator action.
- Do not stage or commit anything without an explicit path list from Ben.

## Acceptance before you call W2 done

1. A package valid at creation becomes stale at its real expiry. Neither a
   copied ledger nor a new market timestamp renews old player evidence.
2. A copied, self-contained package validates on the supported runtime with the
   original attachment paths deleted.
3. Duplicating scenario rows leaves the economic selection unchanged. Increasing
   genuinely independent precision changes the reported uncertainty and not the
   selection.
4. Both Step 1 probes are tests, and both fail on `f318882` and pass after.
5. `cowork-run --profile prior_review` still exports from
   `data/runs/20260909-showdown-ne-sea/inputs/` with `FILE_VALID: true` and empty
   `problems`, and a diff against the source template shows only the reserved
   entry rows changed.
6. Every existing test still passes untouched. Report the full suite counts.

## Finish the session by

Updating `backlog.md` (W2 status, whether `W8` is now unblocked, the next
`READY` tranche, any new constraint learned) and appending a dated
`changelog.md` entry under `Unreleased` with the exact commands run, their
counts, remaining blockers, and open `[BEN: ...]` flags. Do not stage or commit
anything without my explicit path list.
