# P3a — Bounded DESIGN scenario bank on the `prior_review` path

Paste this whole file as the first message of a fresh Claude Code session.

---

You are developing chunk `P3a` of the prize-tail program in `bleeski/nfl-dfs`.

Read, in this order and no further: `docs/START_HERE.md`; `CLAUDE.md`
§ Developing in Claude Code; the head of `backlog.md`; your brief at
`docs/chunks/P3a-scenario-bank.md`; the first 80 lines of `changelog.md`. Then
run `python3 scripts/repo_state.py --stdout` and check `state/claims.json` and
the repository's open issues for an active claim on `P3a` before writing code.

**Do not start unless `P0` and `P1` are both `DONE`.** `P1` closed 2026-09-19.
`P0` is the dependency that may still be open, and it has its own blocker (see
below). If `P0` is not `DONE`, say so and stop.

## Runtime

Linux: `sh ./nfl.sh setup|test <pytest args>|doctor|<cli>` against `.venv-linux`.
The complete suite needs an extended tool timeout (600000 ms) or a background
run; a kill at two minutes is a tooling artifact, not a failure.

Until PR #19 merges, pass `NFL_DFS_PYTEST_TMP=/tmp/nfl-dfs-pytest/<something>`
to every `nfl.sh test` invocation. Without it the suite fails in a fresh
container with `2 failed, 226 passed, 1 skipped, 562 errors`: `nfl.sh` hands
pytest a `--basetemp` whose parent does not exist, and pytest's
`TempPathFactory.getbasetemp` does not create parents. It is not your bug and it
is already fixed in #19.

## Why this chunk

`backlog.md:79`: the objective is the expectation. It has no distribution, no
covariance and no threshold, and the DraftKings yardage bonuses are dead code
under it because an expected stat line never crosses 300 or 100 yards. The tail
cannot be targeted until lineups have a distribution. This chunk gives them one
and reports it; it does **not** change selection. `P3b` is the objective change.

## What P1 left you

- `qb_attempt_share` can now be bound to a published depth chart through
  `nfl_qb_depth_role_evidence_v1` (`src/nfl_dfs/qb_depth_roles.py`,
  `scripts/make_offensive_role_evidence.py`). The starter carries the team's
  attempts; backups are zero. Use it in fixtures rather than hand-setting shares.
- `salary_rank_divergence` on `PriorScores` names every person the market prices
  far above this scorer, with the evidence state that produced the prior.
- A person in `TRANSFER_PRIOR_UNVERIFIED` who also trips that divergence now
  **stops the run** (Ben's ruling, 2026-09-19). Any fixture carrying an
  unresolved transfer priced near the top of the slate must either supply role
  evidence or expect the stop. This bit several P1 tests; see
  `tests/test_qb_depth_roles.py::_setup` for the pattern.

## Carry these two findings into your design

Both were measured during the 2026-09-19 cloud audit and neither is in the P3a
brief, because the brief predates them.

1. **The candidate bank is ~52 lineups and it is collinear with the selector.**
   `portfolio_enforcement.py:50` sizes it `max(32, 4 × entries)` on a
   `max(30s, 2s × entries)` budget, and it is built by sequential HiGHS MILP
   with no-good cuts (`optimizer.py:172`), which returns the *top-k by the prior
   objective*. So every candidate is a near-variant of one
   expectation-maximising thesis, and diversity has to be manufactured
   afterwards by exposure caps — which is exactly the single-thesis collapse the
   standings measured (DEN@KC v6: Nix in 17 of 18, mean pairwise overlap 3.46 of
   6, zero paid). The bank's own archived measurement is ~1.8 candidates/second
   (216 at a 120s budget, `docs/backlog-archive/…:1370`), so simply raising the
   cap costs hours and does not fix the collinearity. A scenario bank that
   scores lineups on a distribution is the first thing that can generate
   candidates on a criterion the selector is not already maximising. Say in your
   plan whether P3a should feed candidate generation or only report, and why.
2. **`config/runtime.json` advertises a bank 400x larger than the code builds.**
   `candidate_generation_min: 20000`, `candidate_generation_max: 50000` and
   `candidate_vector_shortlist_max: 5000` are consumed nowhere in `src/`,
   `scripts/` or `tests/` — only the scenario counts and `certification_seconds`
   are read (`cli.py:212-239`). Those scenario counts *are* live and are yours:
   `design_scenarios`, `select_scenarios`, `referee_scenarios`. Either wire the
   dead candidate keys or delete them in this chunk and say which; leaving them
   is the third session in a row where the first place someone looks for the
   bank size is wrong.

## Scope

Your brief governs. In outline: a bounded DESIGN scenario bank on the
`prior_review` path, with measured within-game covariance, reporting per-lineup
p50/p90/p99 in the review. Registered `objective_version` / seed discipline per
`.claude/rules/selection-and-objective.md`: DESIGN, SELECT and REFEREE banks
stay disjoint, REFEREE is report-only, and `OPTIMAL` stays scoped to the
reported bank. Vocabulary: `prior_points`, `p90`, `DIAGNOSTIC`. Never `EV`,
`ROI`, `win_probability`, `calibrated`, `edge`.

Out of scope: the objective change (`P3b`), ownership (`P4a`), any promotion of
`MODEL_STATUS` above `PRIOR_ONLY`, and the candidate-generator rewrite itself.

## Acceptance

Defined before code, per `CLAUDE.md` step 5. Determinism (same bytes in,
byte-identical bank out) and a mutation test (a changed input byte withholds the
artifact) accompany the new writer, per `.claude/rules/tests.md`. Complete suite
green; paste the exact `N passed, M skipped` line and wall time into
`changelog.md`.

## Close-out

`backlog.md` status, `changelog.md` under `Unreleased` with real numbers,
`IMPLEMENTATION_STATUS.md` if capability changed, the next prompt in
`docs/session-prompts/`, and every open `[BEN: ...]` flag restated. Commit, push
to `claude/P3a-<slug>`, open a pull request, merge on green CI under
`.claude/rules/git-authority.md`.

## Standing blockers you do not own

- `P0` grades against `data/standings/inbox/`, which is gitignored, so it cannot
  run in a cloud session until chunk `X2` gives the corpus a reachable home.
- Three of six hosts in `sources.ALLOWED_HOSTS` answer 403 at CONNECT in a cloud
  session (`api.weather.gov`, `api.sleeper.app`, `api.the-odds-api.com`).
  nflverse over GitHub works. Chunk `X1` replaces the stale claim in
  `docs/CLAUDE_CODE_SETUP.md` with a probe.
- The `DFS_Architect_MCP` server returns **stub** weather. It is never evidence.
