# Q1B — settlement intake: from a DraftKings standings export to a capture request

Paste this whole file as the first message of a fresh Claude Code session started
in the `nfl-dfs` repo root. It touches no selection, policy or evidence-gate
code, so it is safe on a slate day, but it is a full dev tranche and should not
be started under a lock clock.

---

You are implementing tranche **Q1B** in Ben's personal `nfl-dfs` repo. Read
`CLAUDE.md` in full even though it loaded automatically; it is binding, including
the section "Shipping under a lock clock". Then read `backlog.md` (the
"Reprioritized development program — 2026-09-10" table and the Q1 entry),
`docs/COWORK_RUNBOOK.md`, `docs/DATA_CONTRACTS.md` (the `nfl_standings_csv_v2`
and `nfl_settlement_request_v1` sections), and `IMPLEMENTATION_STATUS.md`. Finish
the session by updating `backlog.md` and `changelog.md`. Never `git add .`, and
never commit, push or open a PR without an explicit reviewed path list from Ben.

Q1B is not in the numbered program table. Add it there as a row under Q1 (the
`S4A`/`S4B` split is the precedent for a lettered sub-tranche) before you start,
with its dependency recorded as Q1 only. It does not displace C3, C4 or Q2.

## Runtime, before anything else

This session runs natively on Ben's Windows machine with direct access to the
repo. Ignore every Cowork instruction in `backlog.md`, `changelog.md` and the
older session prompts about staging the tree into a cloud container,
`device_bash`, `device_stage_files`, `device_commit_files`, `/mnt/user-data/`
paths, or redirecting `NFL_DFS_VENV_DIR` and the uv caches at a scratchpad. None
of it applies. Edit files in place.

- **Launcher.** Use the Windows launcher `.\nfl.ps1 <command>` against the
  Windows `.venv`, or `.venv\Scripts\python.exe -m pytest -q` directly. Do not
  use `sh ./nfl.sh`; it builds and expects the isolated Linux `.cowork-venv`.
  (If this session is actually running under WSL or Git Bash rather than
  PowerShell, use `sh ./nfl.sh` consistently instead and say so in the changelog,
  but do not mix the two venvs in one session.)
- **The suite takes longer than the default command timeout.** The complete
  pinned suite last measured 364.86s on Windows (it is ~150s in the Linux
  container, which is the number most of the changelog records). Run it with an
  explicit extended timeout of 600000ms, or in the background and poll. A suite
  run that gets killed at two minutes is a tooling artifact, not a failure, and
  must not be reported as one.
- **`git status` is safe here.** The standing prohibition on running it came from
  the Cowork mount leaving an unremovable `.git/index.lock`, which does not
  happen natively. The commit rules above are unchanged.
- **No network is required by this tranche.** Both new tools are standard library
  only and read files already on disk.

Baseline: run the suite before you change anything and record what it actually
returns. Expect **644 passed, 1 skipped**: the last recorded full-suite run was
630 passed, 1 skipped on 2026-09-12, and the 2026-09-14 session added
`tests/test_standings_checklist.py` (14 tests) without ever running the complete
suite in the project venv. If you get 630, the checklist tests are not
collecting, and that is a defect to fix before anything else. This is also the
first full-suite confirmation on Ben's box since 2026-09-12, so record the number
in `changelog.md` whatever it is.

## Why this tranche exists

Q1 built the entire settlement and reference-economics plane: the immutable
`nfl_settlement_bundle_v1`, the exact independent `nfl_reference_settlement_v1`,
the predeclared `nfl_metric_promotion_registry_v1`, the canonical
`nfl_run_settlement_brief_v1`, and complete-field copied-package replay. It has
been finished since 2026-09-10 and it has consumed **zero real contests**.

Q6 (rolling-origin validation, holdout, model registry, promotion) depends on
"Q5, settled-slate accrual". Accrual is the one dependency in the whole program
that no amount of later engineering can shorten. Ben has now entered 18 real
contests across three slates (2026-09-09 NE@SEA, 2026-09-10 SF@LAR, 2026-09-13
Week 1 main plus DAL@NYG) and `data/standings/inbox/` is empty. Every week that
passes without an intake path is a week of validation corpus that has to be
recovered from DraftKings history later, or not at all.

`scripts/standings_checklist.py` (2026-09-14) already answers which contests need
a pull and writes `data/standings/CONTESTS_AWAITING_STANDINGS.md` plus a
clickable HTML page. It is the front half of a pipeline with no back half:
dropping a file into `data/standings/inbox/` currently satisfies that checklist
and nothing else.

## What exists today, precisely

- `.\nfl.ps1 settle --request <json>` calls
  `settlement.capture_settlement_bundle` and is the only Q1-complete path. There
  is **no builder for `nfl_settlement_request_v1`**. Writing one today means
  hand-authoring a strict hash-bound JSON carrying contest facts, versions, six
  artifact requests, release truths, evidence issues and a reference budget.
- `.\nfl.ps1 settle --entries <csv> --standings <csv>` returns
  `LEGACY_PARTIAL_SETTLEMENT_CAPTURE` with `q1_complete: false`. It parses and
  proves entry coverage and nothing more. It is useful as a smoke test on a fresh
  pull and it cannot close Q1B.
- `settlement.parse_standings` requires the columns `EntryId`, `Rank`, `Points`,
  `Prize`, `Lineup`, refuses ragged rows, non-numeric or duplicate Entry IDs, an
  empty lineup, a negative or sub-cent prize, and a rank below 1.
- `settlement._prepare_settlement` refuses unless
  `len(standings.rows) == contest.field_size` (`INCOMPLETE_STANDINGS_FIELD`),
  every authorized Entry ID appears, every owned standings lineup matches the
  selected assignment (`OWNED_LINEUP_MISMATCH`), and the reference evaluator's
  own rank and prize agree with the file (`STANDINGS_RANK_MISMATCH`,
  `STANDINGS_PRIZE_MISMATCH`).
- Precedent to follow: `scripts/make_classic_weather_evidence.py` and
  `scripts/make_official_status.py` are the house pattern for a standard-library,
  no-network builder that derives identity from exact bytes.
  `tests/test_settlement_bundle.py`, `tests/test_reference_settlement.py` and
  `tests/test_governance_qa_settlement.py` are the existing coverage.

## The three design questions you must answer before writing code

Write each answer into `backlog.md` before implementing it.

**1. Where does `Prize` come from?** The contract requires a per-entry prize in
exact cents. Verify against the first real pull whether DraftKings' full
standings export carries one. If it does not, the prize is a joined fact from the
contest's payout table, not an observed one, and the intake must say so: bind the
payout source by hash, label the prize column's provenance in the normalized
file, and never compute a prize from a payout model and then present it as
observed. If the two disagree, that is a finding, not a repair.

**2. Which contests can the reference evaluator actually settle?** Q1 measured
50,000 entries in 4.229390s and **refused a 100,000-entry run at its declared
10-second budget rather than approximating**. Contest 193028206 is the $3.5M
Fantasy Football Millionaire; its field is far above that line, and the
complete-field rule means there is no partial option. Decide and record: either
raise the registered reference budget with a fresh measurement at the real field
size, or scope the first corpus to the contests the evaluator can settle exactly
and name the excluded ones with the measured reason. Do not quietly relax the
complete-field check; it is a truth claim, not a construction preference.

**3. What happens to the 8 loose-only contests?** The 2026-09-13 DAL@NYG slate
(195520918 plus seven satellites) was built under a lock clock through scratch
scripts and exists only as loose CSVs in the repo root and `Claude outputs/`.
There is no `data/runs/` snapshot, so no pre-lock prediction manifest and no
hash-bound assignment, and `_validate_prelock_manifest` will refuse. **This one
needs Ben's ruling**: either they enter the corpus at an explicitly declared
lower evidence tier that Q6 can filter on, or they are dispositioned out. Do not
reconstruct a pre-lock manifest after the fact under any circumstances; a
fabricated prediction is worse than a missing slate. Ask, and if Ben is not
available, implement the disposition path and leave the tier question open with
a `[BEN: ...]` flag.

## Scope

1. **A normalizer**, suggested `scripts/file_standings.py`, standard library
   only, no network. It reads a raw DraftKings export from
   `data/standings/inbox/`, identifies the contest from the file, strips
   DraftKings' trailing per-player ownership block if one is present, emits a
   `nfl_standings_csv_v2`-shaped file under a content-addressed path, and records
   the SHA-256 of the raw file alongside the normalized one. The raw file is
   never edited in place and never deleted.
2. **A request builder**, suggested `scripts/make_settlement_request.py`. Given a
   contest ID and a `data/runs/` snapshot it assembles the
   `nfl_settlement_request_v1` JSON: contest facts, the six artifact requests
   resolved to real paths, versions, release truths copied from the frozen
   pre-lock run rather than re-derived, evidence issues, and a reference budget
   consistent with the answer to question 2. It refuses rather than guesses any
   field it cannot resolve from bytes already on disk.
3. **Round trip.** `.\nfl.ps1 settle --request` runs clean on at least one real
   contest end to end, and `settle --replay` reproduces the copied package.
4. **Close the checklist loop.** `scripts/standings_checklist.py` currently marks
   a contest filed when any file lands in the inbox. Teach it the difference
   between filed (raw present), normalized, and settled (a bundle exists), and
   surface the three states separately. Its 14 tests must still pass.
5. **Dispositions.** A contest that cannot be settled for a recorded reason
   (field too large for the registered budget, no pre-lock snapshot, export no
   longer available) gets an explicit disposition through the existing
   `--mark-unrecoverable` / `--mark-placeholder` mechanism, with the reason. It
   must stop appearing as pending work without ever looking settled.

## Out of scope

Never fetch DraftKings. The export is Ben's click in his own logged-in browser,
exactly as `CLAUDE.md` requires, and this tranche only ever reads a file he
already downloaded. No ownership, field generation, duplication, EV, ROI or
calibration work, and no promotion: landing a settled slate changes no release
truth and `MODEL_STATUS=PRIOR_ONLY` / `RELEASE_DECISION=DO_NOT_UPLOAD` are
invariant. Do not touch `prior_review.py`, any evidence gate, C3, or the C2
policy contracts. Do not start C4. Do not modify `settlement.py`'s parsing or
complete-field rules to make a real file fit; if a real export does not satisfy
the contract, report the mismatch and fix the intake or raise a defect.

## Acceptance

- One real contest settles end to end through `--request`, and the package
  replays byte-identically through `--replay`.
- The normalizer has golden coverage plus adversarial cases: a truncated export,
  a duplicate Entry ID, a missing `Prize` column, a trailing ownership block, a
  row whose lineup is blank, and an export whose field size disagrees with the
  contest facts. Each produces a named refusal, not a repaired file.
- A determinism test: the same raw export produces a byte-identical normalized
  file and request JSON.
- A test proving the raw inbox file is unchanged after a full run.
- The complete pinned suite passes with no regression from the baseline you
  measured at the top of the session, run to completion under an extended
  timeout.
- `.\nfl.ps1 doctor`, changed-module compile/import, and `git diff --check` pass.
- `backlog.md` carries the Q1B row, the three recorded design answers, and the
  current corpus count; `changelog.md` records the measured evidence, including
  the full-suite number on Windows and how many of the 18 contests are settled,
  normalized, pending and dispositioned.

## Tone of the finished work

Say plainly what a settled slate is and is not. It is one real contest's outcome
entering a validation corpus that currently holds nothing, which is the only
prerequisite of Q6 that dev work cannot accelerate later. It is not evidence that
the engine picks good lineups, it does not license an EV or ROI claim, and one
slate is not a sample. Report the corpus as a count with the slates named, and
let the number speak.
