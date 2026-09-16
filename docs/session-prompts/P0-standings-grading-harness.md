# P0 — standings grading harness, snapshots, and the failing preflight test

Paste this whole file as the first message of a fresh Claude Code session started
in the `nfl-dfs` repo root on Ben's Windows machine. It touches no selection,
policy, evidence-gate or export code and is safe on a slate day. Do not start it
inside the last hour before a lock.

---

You are implementing chunk **P0** of the prize-tail program in Ben's personal
`nfl-dfs` repo. `CLAUDE.md` loaded automatically and is binding. Run
`/dev-session P0` first; it performs the start-of-session checks (git status and
log, the reads below, the baseline suite, the branch, plan mode). If the skill is
unavailable, do those steps by hand from `CLAUDE.md` § Session protocol.

## Read, in this order, and nothing else until the plan is approved

1. `backlog.md`, first ~230 lines only (tracker protocol, then the 2026-09-15
   program's *Basis*, *Claude Code session conventions*, *Queue* and operator
   items), then the **P0 brief** at `docs/chunks/P0-standings-grading-harness.md`.
   The brief is the specification; this prompt does not restate it. Do not read
   the archives under `docs/backlog-archive/` or `docs/changelog-archive/`.
2. `docs/STANDINGS_DUAL_OPTIMIZATION_FINDINGS_2026-09-15.md` sections 2.2
   (definitions), 4.3 (feature table), 5.3 (concentration), 5.4 (bootstrap) and
   appendix B (method). These are the numbers the harness must reproduce.
3. `changelog.md`, the `## Unreleased` head: the 2026-09-15 entry and the two
   2026-09-14 Q1C/Q1B entries (the whole live file is under 400 lines).
4. `src/nfl_dfs/settlement.py` (`parse_standings`, the `nfl_standings_csv_v2`
   normalizer and its two open contract defects), `scripts/file_standings.py`,
   `scripts/standings_checklist.py`, `tests/test_standings_checklist.py`, and
   `tests/test_w6_live_preflight.py`.

## Runtime

Native Windows, `.\nfl.ps1`, the Windows `.venv`. Ignore every Cowork or
container instruction in older ledger entries (`device_bash`, staging,
`/mnt/user-data/`, `.cowork-venv`); none of it applies. `git status` is safe.
The complete suite last ran **735 passed, 1 failed, 1 skipped in 198s** on this
box on 2026-09-14; the one failure is the preflight clock test this chunk
repairs. Run the suite with an extended tool timeout (600000 ms) or in the
background; a run killed at two minutes is not a result. No network is needed:
everything this chunk reads is on disk.

## Operator prerequisite (check before writing code)

`data/runs/20260913-showdown-dal-nyg/inputs/` and
`data/runs/20260914-showdown-den-kc/inputs/` should contain the DAL@NYG and
DEN@KC salary and entry CSVs copied from Downloads (operator item 2 in the
program; DEN@KC salary SHA-256 `e5224b694004836f13beb3cb8f78ce75483f62c60a343bae0f496fd8d3442204`).
If they are missing, do not go looking for them and do not substitute another
slate's file: build and test the harness on the three slates that have snapshots
(NE@SEA, SF@LAR, Week 1 Classic), leave a `[BEN: copy the two Downloads pairs
into the snapshot folders]` flag in the close-out, and write the two `intake.json`
files as soon as the bytes appear.

## Goal

One deterministic command, `nfl grade-standings`, that turns
`data/standings/inbox/` plus the contest-entry history into the tables every
later chunk is graded by, and reproduces the report's numbers to the printed
precision. Plus: the metric definitions in one registered module, the two
snapshot folders filed with hashes, and the preflight test pinned to a clock.

## Constraints that bound the design

- Standard library plus what `pyproject.toml` already pins (`numpy`, `openpyxl`,
  `highspy`). pandas is not a dependency; do not add one for this chunk.
- Read raw exports directly (zips and loose CSVs). Do not route through the
  `nfl_standings_csv_v2` normalizer: its blank-lineup and fractional-cent
  defects are open and this harness must not inherit them or work around them
  silently. Name the two defects in the grading output's limitations block.
- The parsing rules in the program's *Claude Code session conventions* are
  verified against DraftKings' own `%Drafted` column; reproduce them, then prove
  the reconciliation (MAE ≤ 0.005 pp on the Classic contest after summing base
  and FLEX rows) as a test, not a comment.
- Exports with `TimeRemaining > 0` are `LIVE`: listed, never graded.
- Every table states its denominator (`N` including blanks), the reference
  contest, and that lifts describe this field only. Nothing in the output may use
  the words EV, ROI, win probability, calibrated, or edge.
- Grades, not settlement: the harness writes nothing under `data/standings/
  normalized/`, changes no disposition, and is not a settlement bundle. Say so in
  the module docstring and the CLI help.
- Raw inbox files are never modified; a test proves their hashes are unchanged
  after a full run.

## Acceptance (verbatim from the brief; all of it)

The harness reproduces, to the printed precision: 71 owned entries with
`Rank == Place`; DEN@KC 195526229 rank-1 tie 206 and top-1% dup≥6 share 0.983;
NE@SEA 193391013 23-way tie paying $54,065.22 per entry with the supplied ladder;
pass-catcher=1 top-1% lift 1.60 / 1.53 / 2.08 / 1.39 across the four reference
contests; Classic sub-5% count 0 top-1% rate 2.08%; 8,007 user-portfolios with
≥10 entries in the four reference contests. Runtime under three minutes on the
26 files. `test_live_check_refuses_once_a_selected_player_has_locked` passes by
pinning `now`, not by moving its date. Full suite green apart from the expected
Windows symlink skip.

## Out of scope

No ownership model, no field or duplication model, no change to selection,
policy, export or any evidence gate, no settlement request, no promotion, no
renaming or deleting the loose root-level CSV/JSON artifacts (copy only). Do not
start P0b, P1 or P2. Do not refactor `settlement.py`.

## Close-out

Run `/close-out`. It requires the pasted verification evidence, the ledger
updates (`backlog.md` P0 status and hand-back, `changelog.md` under
`Unreleased`, `IMPLEMENTATION_STATUS.md` if capability changed), and the next
prompts: `docs/session-prompts/P2-contest-aware-policy.md` and
`docs/session-prompts/P0b-provenance-completeness.md`, both in this format, with
P2 and P0b set `READY`. Finish with the reviewed path list for Ben, grouped
source / tests / docs / ledger. Never `git add .` or `-A`; never commit, push or
open a PR without Ben's explicit path list.
