# NFL DFS Implementation Changelog

This file records completed implementation work and verification evidence for the sessions in `docs/ROADMAP.md`. Keep entries factual and append new dated sections beneath `Unreleased`. Do not describe planned, diagnostic, synthetic, or structurally legal work as live-certified or upload-ready.

## Unreleased

### 2026-09-23: no plan-approval wait; the plan goes in the task file

Not a roadmap session: no claim, no status change, no ledger row. Ben's
ruling, on the recommendation in the entry below: "Do what you recommend",
then "#1", choosing the option that read "Remove the plan-approval wait from
CLAUDE.md and /dev-session step 6, and update the CLAUDE.md test count."
Touches `CLAUDE.md`, a protected path, so the pull request carries
`ben-review` and Ben merges it.

Why: Ben's 2026-09-20 ruling found that a non-engineer's review of a diff
produces a signature rather than a check, and a plan is the same. The
Quick-Start prompt in `docs/ROADMAP.md` §1 already ran without the wait, so
the two ways into a session disagreed. The plan is still written, to the task
file Ben can read at any point, and the `reviewer` subagent checks scope
against the card before close-out.

#### Changed

- `CLAUDE.md` § Session protocol: "plan mode first" becomes "the plan, with
  assumptions and tradeoffs, goes in the task file and work starts; no
  plan-approval wait". The known-failing-test line gives the current count,
  `1177 passed, 1 skipped`, in three lines instead of four, so the file stays
  at 199 lines.
- `.claude/skills/dev-session/SKILL.md` step 6: write the plan to
  `state/tasks/$ARGUMENTS.md` and start. The one stop left at that step is an
  open `[BEN: ...]` question that blocks the whole card.

#### Not changed

- `.claude/rules/stops-and-reports.md` still defers to any stop `CLAUDE.md` or
  a skill names; none now names the wait. Archived session prompts that say
  "start in plan mode" are history and stay as written.
- The permission classifier refused this change four times before Ben's "#1",
  and after it refused one read-only check on the result; the edits themselves
  went through.

#### Verification

- `sh ./nfl.sh test tests/test_repo_boundaries.py tests/test_roadmap_queue.py tests/test_harness_orientation.py`:
  `204 passed in 1.91s`.
- Complete pinned suite, Linux: `1177 passed, 1 skipped in 153.31s (0:02:33)`,
  recorded with `scripts/record_verify.py`. The skip is the junction test.
- `sh ./nfl.sh doctor`: `pass_status: true`. `git diff --check`: clean.
  `scripts/check_protected_paths.py` flags `CLAUDE.md`, as it should.

### 2026-09-23: every session names its stops, keeps a task file, and reports what Ben owes first

Not a roadmap session: no claim, no status change, no ledger row. A second
review of the Claude Code configuration, at Ben's request, against Anthropic's
prompting guide for the model this repository runs (claude.dev blog,
2026-09-22). The entry below this one covered model inheritance, effort and the
slate-run stops; this one covers what the guide adds: named stops for every
session, a task list in a file that survives compaction, and a final report
that leads with what Ben owes. No engine module, contract, evidence gate,
release truth or protected path changed.

#### Added

- `.claude/rules/stops-and-reports.md`, loaded for every path. When to keep
  going (status goes in the same message as the next command), the four turn
  endings that stall a session, the stops a session does want, the task file,
  and the end-of-run order: **Needs Ben**, **Changed**, **Found**. The four
  endings were in `slate-operation.md` only, which loads for the runbook, the
  operator guide and `scripts/`, so a development session saw them only if it
  happened to read one of those. The list of stops defers to any stop
  `CLAUDE.md` or the running skill names, and says asking never makes a
  permanent boundary or a `git-authority.md` refusal allowed.
- `state/tasks/<SNN>.md`, the task file. Already gitignored by `state/*`.
  `scripts/repo_state.py` gains `task_files()`, and the session-start digest
  lists up to three unfinished ones with their tick counts. The hook runs on
  `compact` and `clear`, so a compacted session is pointed back at its own
  list. It skips a non-regular file (a FIFO would block the hook) and returns
  nothing on a directory error. Nine tests in
  `tests/test_harness_orientation.py`: counting, the finished-list exclusion,
  order, the three-line cap, the `build_state` wiring (a mutation removing it
  fails), and that the directory stays ignored.

#### Changed

- `.claude/rules/slate-operation.md`: the four endings now point at the new
  rule instead of repeating it; the slate's own stops stay, and the handoff
  leads with **Needs Ben**.
- `.claude/skills/onboard/SKILL.md`: "Do not start work until that is said out
  loud" made the orientation report end the turn. The report is now the answer
  when Ben asked only where things stand, and otherwise rides in the same
  message as the first command. The previous review left this for Ben after a
  refusal; this time the edit was allowed.
- `.claude/skills/dev-session/SKILL.md` step 6: the approved plan is copied
  into the task file. The approval wait itself is unchanged (below).
- `.claude/skills/close-out/SKILL.md` step 9: the report opens with **Needs
  Ben** (a `ben-review` label, open `[BEN: ...]` flags) instead of ending on it.
- `.claude/agents/explorer.md`: say what could not be confirmed and where you
  looked, which is the guide's wording for research answers.
- `.claude/skills/verify/SKILL.md`: step 7 ran the complete suite a second
  time only to record it (155 s on Linux, up to 365 s on Windows); it now
  records step 2's log, or `--result-line` on Windows. Step 6 named the Windows
  skip as the only expected one, so a Linux run's junction skip read as a
  finding; it now names both, matching `CLAUDE.md`.
- `docs/CLAUDE_CODE_SETUP.md` § Model and effort: a flagged message can move
  the session to an older model, and subagents inherit it; `/model` switches
  back and `/config` can make it ask first. `/fast` for back-and-forth near a
  lock. Requests to reproduce reasoning in a reply can be declined; none exist
  here.

#### Not changed

- The plan-approval wait (`CLAUDE.md` "plan mode first"; `/dev-session` step
  6). The guide recommends stopping only when a step cannot continue without
  the operator, and Ben's 2026-09-20 ruling found that a non-engineer's review
  of a diff produces a signature rather than a check; the same may hold for a
  plan. Removing the wait was refused by the session's permission classifier
  as self-modification, and so was a first attempt at a line in the new rule
  naming the wait. The fresh-context review then found the rule's closed list
  of stops left the wait out, which would have removed it by implication; the
  list now defers to every stop `CLAUDE.md` or the running skill names. The
  wait stands until Ben rules: `CLAUDE.md` and the skill still require it, and
  plan mode blocks edits mechanically.
- `CLAUDE.md` still gives `1121 passed, 1 skipped` as the Linux count; the
  suite is now larger. It is a protected file, so the count is left for the
  next change that carries `ben-review`.

#### Verification

- `sh ./nfl.sh test tests/test_harness_orientation.py tests/test_repo_boundaries.py tests/test_roadmap_queue.py`:
  `204 passed in 1.41s`.
- Complete pinned suite, Linux: `1177 passed, 1 skipped in 141.05s (0:02:21)`,
  recorded with `scripts/record_verify.py`. The skip is
  `tests/test_cowork.py:115: Windows junction behavior`. The run before the
  review fixes was `1174 passed, 1 skipped in 148.31s`.
- The session-start hook, run offline with a task file present, printed
  `state/tasks/config-review.md: 6/12 done` inside its 60-line budget.
- `sh ./nfl.sh doctor`: `pass_status: true`. `git diff --check`: clean.
  `scripts/check_protected_paths.py`: no protected path touched.
- The `reviewer` subagent reviewed the diff. Its one blocking finding (the
  closed list of stops) is fixed as described under *Not changed*; its
  changelog corrections and test gaps are applied.

### 2026-09-23: subagents follow the session's model; slate runs name the early stops

Not a roadmap session: no claim, no status change, no ledger row. A review of
the repository's Claude Code configuration against Anthropic's current
prompting and effort guidance, at Ben's request. No engine module, contract,
evidence gate or release truth changed. Nothing under `src/` or `scripts/`
calls a model API, so the guidance's API changes have nothing to migrate here.

#### Changed

- `.claude/agents/explorer.md`, `.claude/agents/reviewer.md`: the fixed model
  pin is replaced by `model: inherit`, so both run on the model Ben chose for
  the session. `explorer` declares `effort: low`, the level the effort guide
  lists for subagents; `reviewer` runs at the session's level.
- `.claude/rules/slate-operation.md`: *Measure the clock* now puts the measured
  minutes to the delivery deadline (R31) in every progress note, re-measured at
  each stage boundary. *Decide what is yours to decide* names four turn endings
  that stall a run while Ben is away, the 2026-09-20 question among them, and
  the three stops a run does want.
- `docs/CLAUDE_CODE_SETUP.md`: a *Model and effort* section (nothing pins a
  model or effort; subagents inherit; thinking is always on, so effort is the
  control; stay at the default for slates). *The protected list* section still
  described the twelve-entry list and said `.claude/rules/*.md` was protected,
  which contradicted the top of the same file and `git-authority.md`; it now
  describes the three entries.

#### Not changed

- `CLAUDE.md` and `.claude/settings.json`. Neither conflicts with the guidance:
  verification here means pasted evidence, which the guidance keeps; no
  "think carefully" or "double-check your answer" line exists in `.claude/` or
  `CLAUDE.md`; plan mode first for multi-file work is a defined check-in, not
  an early stop.
- `.claude/skills/onboard/SKILL.md`. Its last line, "Do not start work until
  that is said out loud", invites a turn that ends on the orientation report.
  The replacement was refused by the session's permission classifier as
  self-modification and is left for Ben.
- `docs/CLAUDE_CODE_SETUP.md` still gives `1070 passed, 1 skipped` as the
  Windows result, below the Linux count in `CLAUDE.md`. Left as is: the current
  Windows count was not measured here.

#### Verification

- `sh ./nfl.sh test tests/test_roadmap_queue.py tests/test_repo_boundaries.py`:
  `149 passed in 1.94s`.
- Complete pinned suite, Linux: `1168 passed, 1 skipped in 164.00s (0:02:43)`,
  recorded with `scripts/record_verify.py`. The skip is the junction test.
- `sh ./nfl.sh doctor`: `pass_status: true`. `git diff --check`: clean.
  `scripts/check_protected_paths.py`: no protected path touched.

### 2026-09-23: the fallback writer and Classic QA check the file, not the JSON (Session 02)

Items 1 and 2 of the Session 02 card, on `claude/s02-fallback-csv-l62fjm`, PR
#44, claim `a9ab747`. Items 3 and 4 (the builder and Showdown QA) are split to
`Session 02b` at the card's breakpoint: the first two alone reached 1,378
changed lines. No engine module, contract, evidence gate or release truth
changed. The fallback's output is still `PRIOR_ONLY` / `DO_NOT_UPLOAD`, with
four truths until Session 03.

#### Changed: `scripts/write_dk_entries.py` (rewritten, same positional CLI)

- **Exit codes.**
  - 0: every blank authorized row is filled and verified.
  - 2: refused by name, and nothing is written.
  - 3: the file is written, and every unfilled Entry ID is named on stdout and
    stderr. R29: a row is never filled with a repeated lineup.
- **Named refusals** replace the `assert`s the audit cited (`:24, 41, 57, 67`):
  `UNKNOWN_ENTRY_ID`, `PREFILLED_ROW_ASSIGNED`, `ROSTER_SIZE`,
  `DK_ID_NOT_IN_POOL`, `DUPLICATE_PLAYER`, `ROSTER_SHAPE`, `SLOT_INELIGIBLE`,
  `OVER_SALARY_CAP`, `TWO_GAME_RULE`, `DUPLICATE_LINEUP`,
  `NOT_A_CLASSIC_TEMPLATE`, `ROW_NARROWER_THAN_ROSTER`, `NO_ASSIGNMENTS`,
  `OUTPUT_IS_TEMPLATE`, `OUTPUT_IS_AN_INPUT` and `OUTPUT_EXISTS`. Every problem
  in a file is reported in one run.
- **Raw bytes.** Lines are split with `nfl_dfs.byte_lines`, the helpers
  `lineups.write_upload_bytes` uses. Untouched lines are copied byte for byte,
  and a filled line changes only inside its nine roster spans. An LF template
  now comes back LF; the old writer rewrote every line as CRLF.
- **Output.** The bytes go to a temporary file beside the target, are re-read
  and verified (line count, untouched lines identical, filled rows reparse to
  their assignment), then `os.replace`d. A refusal leaves no file and no
  temporary.
- It reads seven named salary columns and nothing else.

#### Changed: `scripts/qa_classic_portfolio.py`

- **The export audit is on bytes.** `byte_fidelity` compared cell values, so its
  name claimed more than it checked (audit D6 point 5). `export_audit` compares
  raw lines: a changed line must be a blank authorized row, with the same field
  count, the same line ending and identical bytes outside its roster spans.
- **Each exported roster** is compared to its Entry ID's assignment,
  slot-checked against the salary file's `Roster Position`, and run through
  Tier 1. Coverage no longer depends on `if rosters`. An assigned row left
  blank, an assignment Entry ID the template lacks, an export byte-identical to
  the template, and an export with no Entry ID map to check against are all
  failures.
- **Exit codes.** 1 validity, 3 partial coverage with each unfilled Entry ID
  named, 2 an operator-requested limit, 0 pass; Tier 2 never changes it.
  - Moved from 2 to 1: duplicate lineups (R29), byte and Entry ID failures, and
    `--template` without `--export`.
  - Moved from 1 to 2: `--backup-pairs`. It is the operator's assertion about
    who starts, with no evidence bound to it (audit #40 §4, "S/P").
  - Unchanged at 1: officially `INACTIVE` players.
- A JSON-only run prints that the export was not checked. An empty portfolio
  fails as `NO_LINEUPS` instead of crashing in Tier 2. The operator's limits
  apply to the portfolio once, not again per exported row.
- JSON report: `tier1_failures` is renamed `validity_failures`, and
  `unfilled_entry_ids` and `export_checked` are added. Nothing in the
  repository read the old key.

#### Tests changed visibly

- `tests/test_write_dk_entries.py`:
  - `test_an_entry_id_not_in_the_template_is_simply_not_written` (`:139-147`,
    exit 0) is now `test_an_entry_id_not_in_the_template_is_refused_by_name`
    (exit 2, `UNKNOWN_ENTRY_ID`).
  - `test_output_is_crlf_like_a_draftkings_export` is now
    `test_line_endings_follow_the_template`: LF in gives LF out, and CRLF in
    gives CRLF out.
  - The fill test asserts "bytes changed outside the nine roster cells: 0"; the
    old line said "cells".
  - The fixture gives each entry a distinct roster, because the old one
    assigned one roster to both entries, which R29 now refuses. It uses real
    DraftKings roster positions (`QB`, `DST`, `RB/FLEX`), not `QB/FLEX`.
  - The prefilled-cell test also asserts exit 2 and no output.
- `tests/test_qa_classic_portfolio.py`:
  - Exit codes changed: backup pairs from 1 to 2; duplicate lineups, a mutated
    identity cell and template without export from 2 to 1; the Entry ID
    coverage test from 2 to 1, renamed `..._is_a_failure`.
  - `test_byte_fidelity_passes_on_an_untouched_template` is now
    `test_export_audit_passes_on_a_correct_fill`, because an export is now
    compared to an Entry ID map.

#### Added

- The card's eight adversarial fixtures (an extra ID, a missing ID, a QB in
  FLEX, over the cap, a duplicate person, output equal to the template, a
  pre-existing output, 18 of 20 filled):
  - The writer refuses each by name, or exits 3 naming the unfilled rows.
  - `test_qa_fails_every_adversarial_export` exits 1 or 3 on all eight, and
    none prints PASS.
- A byte test on the supplied 20-entry DKEntries export, copied first: all 707
  non-entry lines are byte-identical, and the 20 entry lines differ only inside
  the nine roster cells, CRLF kept.
- QA cases the old code passed: swapped rosters between two rows, right people
  in the wrong slots, a quoted `"$1"` and a CRLF rewrite that a cell comparison
  cannot see, an all-blank export.
- `test_the_writer_and_qa_agree`: writer then QA on 20 of 20 (0 and 0) and 18 of
  20 (3 and 3).
- Writer file: 33 cases (was 8). QA file: 41 cases (was 19).

#### Documents

- `docs/RUNBOOK.md`: the fallback listing, Tier 1's exit codes and that QA runs
  on the written file, and the Running order sentence. The Running order now
  says the builder's shortfall still exits 0 until Session 02b.
- `docs/ROADMAP.md`:
  - Session 02 is `Complete`, and `Session 02b` has a row and a card.
  - The card records the answer to the pool-filter question.
    `selection.py:228-230` writes `scores.json` before the exclusion set at
    `:231-254`, so DraftKings `OUT`, `IR` and `D` rows reach the builder with
    positive scores. The supplied Classic salary file has 33 such rows.
  - The ledger records the claim at `a9ab747`, and §1 names Session 02b.
  - §3 has a row for the archive move.
- `IMPLEMENTATION_STATUS.md`: a capability entry for this session.
- `changelog.md` was 567 lines. Its three oldest entries (2026-09-22, before
  the cutover, 228 lines) moved verbatim to
  `docs/changelog-archive/changelog-2026-09-22.md`.
  `cmp` against `git show HEAD:changelog.md | sed -n 307,534p` found them
  byte-identical, with sha256 prefix `b294c1c25f88957e` on both sides.

#### Verification

- Baseline before any change, in a fresh `.venv-linux`:
  `1121 passed, 1 skipped in 175.83s (0:02:55)`.
- The card's command as written stops at
  `ERROR: file or directory not found: tests/test_qa_showdown_portfolio.py`.
  That file is Session 02b's. The other three files: `79 passed in 5.48s`.
- Complete pinned suite on the finished tree:
  `1168 passed, 1 skipped in 129.53s (0:02:09)`. That is 47 above the baseline:
  the writer and QA files now hold 74 cases, against 27 before. Recorded with
  `scripts/record_verify.py`. Before the review fixes below it was
  `1161 passed, 1 skipped in 126.44s`.
- `sh ./nfl.sh doctor`: `pass_status: true`. `python -m compileall` on both
  scripts and both test files: clean. `git diff --check`: clean.
  `scripts/check_protected_paths.py`: no protected path touched.
- Neither script names or reads the salary file's points-per-game column.

#### Review

The `reviewer` subagent read the diff against the card and ran the two focused
files (`67 passed in 5.36s`).

- **Blocking, fixed.** QA passed an export in which an assigned Entry ID's
  template row was already prefilled with a different roster. The row never
  entered the comparison. It now fails as `ASSIGNED_ROW_WAS_PREFILLED`. The
  writer already refused that input.
- **Blocking, already resolved.** It found two placeholder strings and no
  recorded verify. It had read the tree before the placeholders were filled and
  `record_verify.py` ran. Both are in `82abbdc`.
- **Open, fixed.** A new lineup repeating a prefilled row escaped R29 in both
  scripts. Both now compare against prefilled rows, reading a cell as `123` or
  `Name (123)`.
- **Open, recorded.**
  - `split_byte_lines` splits on LF, so a quoted field holding a newline would
    split in two. DraftKings exports have none.
  - `assignments_by_entry_id` has no contract in `docs/DATA_CONTRACTS.md`.
    That gap predates this session.
- Added with the fixes: two mutation tests, as `.claude/rules/tests.md` asks of
  a writer. A non-UTF-8 byte fails as `TEMPLATE_NOT_UTF8`, and an unterminated
  quote as `UNREADABLE_TEMPLATE_ROW`; the writer's template parser now checks
  each entry row's field spans. Both withhold the file.

#### Decided, and why

- **A partial file is written, not withheld** (exit 3). Under R28 a file with
  named gaps beats no file. An integrity failure (a bad roster, an unknown
  Entry ID, an overwrite) still refuses the whole file, because integrity
  gates stop the file they protect.
- **The writer and QA share `nfl_dfs.byte_lines`** rather than a second span
  parser. QA's comparison logic is its own.
- Nothing was relaxed.

#### Left open

- Session 02b: the builder's shortfall and pool filter, the ratchet ceiling, its
  output overwrite, and Showdown QA's four strategy findings.
- Showdown QA's default-on `OVERLAP_*` and `STARTER_WITH_OWN_BACKUP` still exit
  2. The card names only the four findings.
- `scores.json` also omits selection's kicker zero-share and offense exclusions,
  for the same ordering reason (Session 13).

### 2026-09-23: the R28 boundary sentence names its subject (Session 01 follow-up)

Wording only. No boundary's meaning, release truth, gate or engine behaviour
changed. Branch `claude/determined-knuth-6hklql`, restarted from `main` at
`1817d57` after PR #42 merged there.

- `CLAUDE.md` boundary 7 and `docs/START_HERE.md` boundary 5 each ended with a
  sentence starting "Under R28 it stops certification". In `CLAUDE.md`, "it"
  followed a sentence about construction preferences; in `START_HERE.md`, it
  followed "never weaken an evidence gate". Either could be read as the
  subject.
- Both now read "Under R28 missing hard evidence stops certification", which
  is the subject the bullet opens with. The rest of the sentence is unchanged
  and re-wrapped to the same four lines; `CLAUDE.md` stays at 199.
- `CLAUDE.md` is protected, so this pull request carries `ben-review` and Ben
  merges it.

### 2026-09-23: rulings R28 to R31 into `CLAUDE.md`, four false claims corrected, and a label that clears its check (Session 01)

No engine module, contract, evidence gate or release truth changed; no run
executed. Every path still ends `PRIOR_ONLY` / `DO_NOT_UPLOAD`, with four truths
until Session 03. Branch `claude/determined-knuth-6hklql`, PR #42. `CLAUDE.md`
is protected: the PR carries `ben-review` and Ben merges it.

#### Changed: `CLAUDE.md` (199 lines, was 214)

- **Boundary 7 of 12.** Its text is kept, with the R28 sentence appended:
  missing hard evidence stops certification, not construction or delivery, and
  integrity gates still stop the file they protect. The other 11 boundaries are
  byte-identical to `HEAD`.
- **Release truths:** R28 in force, implemented by Sessions 03 to 12, with
  four truths until Session 03; R30. "Nothing writes `DK_UPLOAD`" becomes "no
  operating profile writes it; `certify` and governed `late-swap` can".
- **Lock clock:**
  - Uniqueness leaves the relaxable list; R29 gets its own class, in Ben's
    words.
  - The ladder is `make_classic_policy.py --rung`, walked by hand; Showdown has
    none.
  - Rung 4 is the last structural rung, not a guaranteed file
    (`prior_review.py:3016`, `selection.py:538-542`).
  - The baseline goes first, with the Classic fallback chain until Sessions 04
    and 06.
  - R31's deadline, and D8's runtime clause on the third bound.
- **Pointers and vocabulary:**
  - The queue, the authority order, token discipline and the LF list point at
    `docs/ROADMAP.md`.
  - Status becomes `Pending` / `In Progress` / `Complete` / `Deferred`.
  - The suite line is now `1121 passed, 1 skipped` on Linux. The old line
    called the skip the Windows symlink case; on Linux it is the junction test
    (`tests/test_cowork.py:115`), and `.claude/rules/tests.md` now says both.
- **Length:**
  - The session protocol points at ROADMAP §2.1 and keeps only the rules §2.1
    lacks.
  - The git rules moved into the "Committing" bullet, and "Maintaining this
    file" became the last etiquette bullet.
  - The maintainer HTML comment is removed. It held no rule and named the
    retired `COWORK_RUNBOOK.md`.
  - No rule was dropped.

#### Added: H3

- `.github/workflows/protected-paths.yml`:
  - triggers on `pull_request` types opened, synchronize, reopened, labeled and
    unlabeled;
  - read-only permissions, and concurrency keyed on the PR number;
  - no label filter, because a skipped run would post over the real result.
  It lives in its own file so that a label event never reruns or cancels the
  suite or the Windows job. `ci.yml` loses the job.
- `scripts/check_protected_paths.py --live-labels`:
  - reads `GET /repos/{repo}/pulls/{n}` over stdlib `urllib`, with redirects
    refused, a 10 s timeout and one retry;
  - requires `https://api.github.com`, and that host must appear in
    `ALLOWED_HOSTS`, parsed from `sources.py` as `session_probe.py` does;
  - validates the repo, the PR number, the token and the response shape;
  - ignores `PR_LABELS`, and every failure exits 2;
  - prints the live labels with the UTC read time.
  Without the flag it is unchanged and offline.
- 37 tests in `tests/test_repo_boundaries.py`, written first; 36 failed before
  the script changed. They cover:
  - fail-closed lookup, with and without a protected hit, and the single retry;
  - 8 missing or invalid inputs and 6 refused hosts, none of which sends a
    request;
  - 9 malformed responses;
  - label present, label absent (each file named), and frozen payload against
    live;
  - an unprotected change with and without the label;
  - no API call without the flag, and an offline subprocess run;
  - 3 workflow text checks.
  The three-entry list test is untouched.
- `docs/CLAUDE_CODE_SETUP.md` and `.claude/rules/git-authority.md` describe the
  live read.

#### Changed: mirrors

- `docs/START_HERE.md`: boundary 5 (the other 7 are byte-identical), the truths
  section, the lock-clock paragraph and the "Operate a slate" row.
- `docs/RUNBOOK.md`:
  - the rung-4 claim at the policy section;
  - R30 in two places;
  - "P0 repairs" in two places (fixed 2026-09-17);
  - the full lock-clock text, amended in place with each amendment marked,
    because `CLAUDE.md` cites it as the full ruling.
- `.claude/rules/`: `slate-operation.md` (R28, R29), `operating-path.md` (fifth
  truth, `DK_UPLOAD`) and `tests.md`.
- `IMPLEMENTATION_STATUS.md` (R30, and four `backlog.md` pointers) and
  `README.md` (three lines).
- `docs/OPERATOR_GUIDE.md` (R30) and `docs/CLAUDE_CODE_SETUP.md:214`
  ("P0 repairs").
- `scripts/file_standings.py`: six "Q1B in `backlog.md`" strings and comments
  point at Session 30, text only.
- `docs/ROADMAP.md`:
  - the claim commit `5c15bb8` moved §1 to Session 02 in the same commit,
    because an `In Progress` S01 is not startable and the Quick-Start test
    would otherwise fail;
  - S01's Target Files now list everything it touched;
  - the ledger records Session 00's merge `46de154`.

#### Left open

- `scripts/make_classic_policy.py:29-31` and `:166-168` still print "always
  produces a legal portfolio". That file belongs to Sessions 06 and 10.
- Dated history sections of `IMPLEMENTATION_STATUS.md` keep their original
  Excel wording.
- `changelog.md` is 534 lines, past the ledger rule's ~500. The next close-out
  moves the oldest 2026-09-22 entries to `docs/changelog-archive/` verbatim.
  This PR did not widen for it.

#### Verification

- Baseline at `46de154`: `1084 passed, 1 skipped in 160.30s`.
- Focused: `sh ./nfl.sh test tests/test_repo_boundaries.py
  tests/test_roadmap_queue.py -x --tb=short` gives `149 passed in 1.22s`.
- Full: `sh ./nfl.sh test` gives `1121 passed, 1 skipped in 138.76s`, which is
  1084 + 37, recorded by `record_verify.py`. The skip is
  `tests/test_cowork.py:115`, "Windows junction behavior".
- `doctor` gives `pass_status: true`. `compileall` and `git diff --check` are
  clean.
- `check_protected_paths.py` exits 0 offline before the commit; after the
  commit it flags `CLAUDE.md`.
- Boundary proof (scratch script, `HEAD` against the working tree):
  - `CLAUDE.md`: bullets 1 to 6 and 8 to 12 byte-identical; bullet 7 keeps the
    `HEAD` text as a prefix, plus 4 appended lines.
  - `docs/START_HERE.md`: bullets 1 to 4 and 6 to 8 byte-identical; bullet 5
    has the same 4 lines appended.
- `wc -l CLAUDE.md` gives 199.
- The `reviewer` pass found one blocking item. A draft card line said the
  label-proof timestamps were already recorded; it now says they are pending.
  Its informational notes: the card's "boundary 5" uses `START_HERE.md`
  numbering, and `ci.yml` keeps a harmless `pull-requests: read`.
- H3 live proof on PR #42, head `32b9135`, no commit in between (UTC,
  2026-09-23):
  - red: run `35803520652` (event `synchronize`) read live labels `[]` at
    00:46:48Z, printed `PROTECTED_PATHS_WITHOUT_REVIEW` naming `CLAUDE.md`,
    exited 1, and completed at 00:46:50Z;
  - label: `ben-review` applied through the API at 00:47:14Z (the pull
    request's `updated_at`);
  - green: run `35803561795` (event `labeled`) was created at 00:47:16Z, read
    live labels `["ben-review"]` at 00:47:23Z, printed "Protected paths
    touched, `ben-review` present: CLAUDE.md", and completed `success` at
    00:47:26Z.
  From label to green took 12 s, and the job step itself under 1 s. The H3
  acceptance clause (labelled after CI, green with no new commit) is met.
  This commit, which records the proof, is a new head; with the label on,
  `protected-paths` should pass on it too.

### 2026-09-22: one roadmap replaces the backlog, and four rulings (Session 00)

No engine module, contract, evidence gate or release truth changed. Every path
still ends `MODEL_STATUS=PRIOR_ONLY` and `RELEASE_DECISION=DO_NOT_UPLOAD`. No run
executed. Branch `claude/brave-babbage-21d8pk`.

#### Why

Ben asked for one authoritative source of truth for all remaining work, built
delivery-first from the 2026-09-22 deadline-delivery QA audit (issue #40,
audited at `f8c6942`). Planning was split across `backlog.md` (two programs,
1,074 lines), the Showdown tracker (still called authoritative), the C4
retrospective's appendix (cited by code comments as a tracker), 22 session
prompts (16 for finished work) and several reviews with task lists.

Three read-only passes verified the audit against the code. None of its claims
were false. Two were understated. The standalone fallback can exit 0 at every
stage while reserved rows go out blank and QA prints PASS
(`build_classic_portfolio.py:254-279`, `write_dk_entries.py:49`,
`qa_classic_portfolio.py:231`). C2 also discards a feasible witness when a bank
times out (`classic_portfolio.py:830-852`). `docs/ROADMAP.md` §2.4 has the
verdicts with file:line evidence.

#### Rulings (Ben, 2026-09-22; recorded in `docs/ROADMAP.md` §2.5, into `CLAUDE.md` in Session 01)

- **R28**: add `DELIVERY_STATE` as a fifth truth. A baseline built from the
  DraftKings bytes ships first. Truth-claim gates (activity, role, weather) stop
  certification, not construction. Integrity gates still stop the file they
  protect. `RELEASE_DECISION` and the no-EV rules are unchanged. Absorbs R24.
- **R29**: "within a given portfolio keep all submitted lineups distinct and
  unique." Uniqueness is never relaxed. Unfilled Entry IDs are reported instead
  of repeating a lineup.
- **R30**: C3X deferred; C3 closes for software acceptance.
- **R31**: the default handoff reserve is 5 minutes before the earliest lock.

#### Added

- `docs/ROADMAP.md`:
  - the Quick-Start;
  - a 37-row status board (Sessions 00 to 36) between parse markers, with
    session cards;
  - the audit triage;
  - the rulings in force;
  - the operator checklist (O1 to O10);
  - the retired-artifacts log;
  - the progress ledger.
- `tests/test_roadmap_queue.py` (24 tests), which replaces
  `tests/test_backlog_queue.py` (10 tests). This is a replacement, not a
  weakening. The old file pinned the retired file's shape. The new one keeps
  every invariant and adds five:
  - an unreadable board is reported by name, never as an empty queue;
  - dependencies resolve and point backwards;
  - every session has a card;
  - the Quick-Start names the first startable session;
  - a session waiting on a ruling carries its question.
- `docs/changelog-archive/changelog-2026-09-14-through-2026-09-21.md`. It holds
  2,317 lines moved verbatim; the live file was 2,584 lines against the ledger
  rule's ~500. Proven byte-identical with `cmp` against `HEAD`.
- `docs/session-prompts/README.md`.

#### Changed

- `scripts/repo_state.py` parses the roadmap's marked table and operator table,
  and derives which sessions are startable. It reports `ROADMAP UNREADABLE`
  instead of an empty queue. It counts flags from the roadmap and chunk briefs.
  The output keys `ready_chunks` and `in_progress_chunks` are kept and now hold
  short session IDs.
- `backlog.md` moved verbatim to
  `docs/backlog-archive/backlog-through-2026-09-22.md`. `backlog.md` is now a
  pointer stub.
- The 22 session prompts moved to `docs/session-prompts/archive/`.
- The `dev-session`, `close-out`, `onboard`, `verify` and `standings-checklist`
  skills, `.claude/rules/ledger.md`, `docs/START_HERE.md`, the session-start
  hook footer, and the status line of all 17 chunk briefs now point at the
  roadmap.
- Supersession banners, with content otherwise unchanged, on:
  - the Showdown tracker;
  - the Showdown-first plan;
  - the 09-08 readiness review;
  - the opener runbook;
  - C4 retrospective appendices A and B;
  - Showdown retrospective §9;
  - debrief §6;
  - the DEN@KC run record;
  - `plan.md`'s phase list.
- Issue #21 (a stale X0/P1 claim) closed with a comment.

#### Left open, on purpose

- `CLAUDE.md` still says the queue is `backlog.md`. It is protected, so the
  pointer and the rulings move to Session 01, which needs `ben-review`. The stub
  redirects until then.
- Decisions made without a ruling, with reasons in the roadmap:
  - P3a depends on P0, because the brief's acceptance uses P0's top-1% proxy.
  - F8 needs no ruling, because it adds review proposals and changes no gate.
  - X4 is deferred for re-scoping.

#### Commit history, stated plainly

- `25d26bb` was committed after a failed `git add`: its pathspec named the
  already-renamed test file, and a `;` let the commit run anyway. It carries
  only the staged renames, although its message describes the whole change.
  `783db36` lands the content and says so. Amend and force-push are forbidden
  here, so both commits stay. The lesson: chain `git add` and `git commit` with
  `&&`, never `;`.
- The `reviewer` pass found nothing blocking. Two of its findings were fixed in
  a third commit:
  - thirteen chunk briefs still told close-out to write a session prompt and
    set `READY`, and each now carries a note pointing at the close-out skill;
  - the changelog entry template used the retired status words.

#### Found by the `windows` CI job

- `ben_flags()` reported paths with `str(path.relative_to(...))`, which gives
  `docs\ROADMAP.md` on Windows, so the flag-source test failed there:
  `1 failed` on PR #41's `windows` job. The Linux job passed.
- The old test only passed on Windows because every flag sat in `backlog.md`,
  a root file with no separator.
- `repo_state.py` now emits `.as_posix()` for flag and brief paths.
- A Linux run cannot prove the fix. The `windows` job on the fix commit is the
  evidence.

#### Verification

- Focused: `sh ./nfl.sh test tests/test_roadmap_queue.py tests/test_harness_orientation.py -x --tb=short`,
  `70 passed in 1.10s`.
- Complete pinned suite on Linux: `1084 passed, 1 skipped in 172.43s (0:02:52)`.
  That is the `1070 passed, 1 skipped` baseline, minus the 10 retired queue
  tests, plus the 24 new ones.
- `sh ./nfl.sh doctor`: `pass_status: true`. `git diff --check`: clean.
- Protected paths: none touched. Compile of the changed Python: clean.
- `python3 scripts/repo_state.py --stdout`: sessions startable
  `S01, S02, S17 (+3 more)`; 1 open flag (Session 30). The session-start hook
  printed 35 of its 60 allowed lines.

Entries dated 2026-09-22 before the roadmap cutover moved verbatim to `docs/changelog-archive/changelog-2026-09-22.md` on 2026-09-23; entries dated 2026-09-14 to 2026-09-21 moved verbatim to `docs/changelog-archive/changelog-2026-09-14-through-2026-09-21.md` on 2026-09-22; entries dated 2026-09-14 (follow-up and checklist) and earlier, back to 2026-09-01, moved to `docs/changelog-archive/changelog-through-2026-09-14.md` on 2026-09-15. Append new entries directly under `## Unreleased`; when this file passes roughly 500 lines, move the oldest entries to the archive rather than letting sessions read them.

## Entry template for future sessions

Copy this structure under `Unreleased` and replace every placeholder:

```markdown
### YYYY-MM-DD: short outcome (Session NN)

Changed:

- Exact behavior changed and files involved.

Verification:

- Exact command or check: exact result.
- Full suite: exact pass/fail count.
- `git diff --check`: pass/fail.

Remaining blockers:

- Named blocker, or `None for this backlog item`.

Tracker updates:

- `docs/ROADMAP.md` §2.2: Session NN `In Progress` -> `Complete` (or back to `Pending`), with a §4 ledger row.
- §1 Quick-Start rewritten to the next startable session, only if its dependencies and acceptance gates genuinely passed.

Claims explicitly not made:

- No live-slate, calibrated-EV, or upload-readiness claim unless independently proven by the work recorded here.
```
