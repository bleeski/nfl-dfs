# NFL DFS

This is a local, evidence-first DraftKings NFL Classic and Showdown engine. It
preserves source bytes, validates exact DraftKings IDs and template geometry,
keeps official game-day evidence operator-controlled, and fails closed when a
hard requirement is missing, stale, conflicted, or unverifiable.

The application never logs in to DraftKings, enters contests, moves money, or
uploads lineups. The operator performs those actions manually after reviewing a
hash-bound package whose certification covers legality and evidence—not profit.

The primary operator surface is Claude Cowork. Select this repository as the
Cowork folder, attach one DraftKings salary CSV and one reserved-entry CSV, and
ask Claude to run the slate. `CLAUDE.md` and `docs/COWORK_RUNBOOK.md` define the
agent workflow. Cowork uses `sh ./nfl.sh`; the manual Windows fallback uses
`./nfl.ps1`. `IMPLEMENTATION_STATUS.md` separates working capabilities from
external-data and calibration gates that cannot be truthfully cleared by code
alone.

The first Cowork pass discovers the two attachments by schema, snapshots their
exact bytes, reconciles the slate and authorized entries, and writes a versioned
review package plus machine-readable run request. Two files alone do not contain
complete payouts, field size, or current official activity evidence, so that
first pass normally ends `DO_NOT_UPLOAD` with the smallest missing next action.

For Showdown or Classic prior-only review generation, Cowork should use
`--profile prior_review --build-priors`. Classic C1 without a policy produces
deterministic machine-readable selection and complete-slate coverage JSON only.
A governed C2 policy adds the bounded candidate bank, exact Entry-ID assignment
and independent portfolio audit. C3 independently re-audits those bytes and,
only on `PASS`, produces an exact-template `DK_REVIEW_ENTRY` CSV plus readable
JSON, self-contained HTML and an eight-sheet workbook. Every Classic output
remains `PRIOR_ONLY / DO_NOT_UPLOAD`; C3 currently awaits native Excel
open/recalculate/save/reopen acceptance before it can be called complete.
That profile can generate legal review lineups from source-bound priors after
weather and identity gates are resolved. It retains a review CSV, with
`MODEL_STATUS=PRIOR_ONLY` and `RELEASE_DECISION=DO_NOT_UPLOAD`. It does not yet
optimize calibrated ceiling/ownership leverage or slate-level drawdown.

Until a live slate has complete payouts, current official inactive evidence,
weather/market evidence when required, and fully calibrated model artifacts,
the system will label field and simulation output diagnostic and will emit
`DO_NOT_UPLOAD` rather than imply readiness.

## Current verification

- Python 3.13.7 and pinned `uv.lock` environment.
- A cross-platform Cowork launcher and schema-driven `cowork-run` command; the
  PowerShell workflow remains available as a fallback.
- Current test counts and the real NE–SEA two-entry rehearsal are documented in
  `docs/READINESS_REVIEW_2026-09-09.md`. Older fixture counts below describe the
  original acceptance data, not the current real-slate pool.
- Supplied acceptance fixtures: 719 Classic IDs, 24 teams, 12 games, two
  reserved entries, and 63 Showdown people represented by 126 CPT/FLEX rows.
- The five-sheet operator input workbook and eight-sheet prior-review output
  workbook have independent render/error-scan coverage. Current C3 native Excel
  save/reopen acceptance remains pending.
