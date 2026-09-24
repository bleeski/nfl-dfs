# Implementation Status

## Capability added: 2026-09-24 (Session 06b)

The baseline leaves out anyone the run's official status file marks `INACTIVE`
(R32). Only identity-valid rows count (exact IDs, team, HTTPS source, aware
time), and a disagreeing row takes its person out; refused rows and an
unreadable file are named limitations, never a stop; the file is snapshotted,
hash-bound and re-checked by the audit. `nfl baseline --official-status` does
the same by hand. Activity is still not certified: freshness and coverage stay
the model path's checks.

## Capability added: 2026-09-24 (Session 06)

`run-slate` is baseline-first. A legal, byte-audited file built from the
DraftKings bytes alone exists before the run touches the network, a policy, a
prior or a solver, and every exit names the file to hand over. Every run still
ends `PRIOR_ONLY / DO_NOT_UPLOAD`. Suite figures are in `changelog.md`.

- **The baseline goes first.** Straight after intake `run-slate` builds
  `baseline/DK_BASELINE_ENTRY_V1_baseline.csv` in its output folder from the
  run's snapshots, honouring the request's exact exclusions and extra
  unavailable statuses, and publishes it as `LATEST_DELIVERABLE.json`, before
  the session probe, policy validation, priors, weather, roles or any solve.
  A hand-run `nfl baseline` takes the same exclusions as `--exclude` and
  `--unavailable-status`.
- **An improvement replaces it only through `delivery.replace`**: the review's
  own readable-review classification, then revalidation from fresh parses,
  the same input hashes and at least as many rows. The baseline stays on disk.
- **Every failure after it leaves it named**: a blocked stage (weather,
  identity, policy), the pre-review blocked exit, a withheld CSV, a refused C1
  export and the outer handler. `DELIVERY_STATE` and the delivery half of
  `release_truths` describe the pointer's file, with `IMPROVEMENT_NOT_DELIVERED`
  when it is the baseline. Exit codes are unchanged.
- **Rung 4 ends with a CSV.** Classic C1 exports its own lineups through the
  baseline's writer and audit (`DK_REVIEW_ENTRY_C1_<run_id>.csv`) and replaces
  the baseline; a refused export leaves the baseline.
- **Not yet:** the deadline controller (Session 07), weather and activity as
  limitations on the model path (Session 09), prefilled rows and contest groups
  (Session 11), the delivery record (Session 14).

## Capability added: 2026-09-23 (Session 05)

A review CSV that passed independent validation now survives a failure of its
readable review, in both modes, and every `run-slate` exit says whether a file
exists to hand over. Every run still ends `PRIOR_ONLY / DO_NOT_UPLOAD`. Suite
figures are in `changelog.md`.

- **Presentation failures keep the CSV.** A readable-review failure is
  classified code by code through the gate registry. A presentation code keeps
  the Showdown or Classic C3 CSV in the result and both indexes, with the code
  as a limitation and exit 2. A roster, Entry ID or byte code, or one the
  registry cannot classify, still withholds it.
- **C3 keeps its export and audit** when its own JSON or HTML fails, after
  re-checking both by hash, reparse and the `DK_UPLOAD` check, and removes only
  the two display files.
- **`LATEST_DELIVERABLE.json`** (`delivery.py`, `nfl_latest_deliverable_v1`)
  names the run's validated file, written with `os.replace`, bound to the file's
  and both inputs' SHA-256, and revalidated from fresh parses before it is
  written and whenever it is read. A changed, remapped, illegal or repeated
  lineup is refused under any label.
- **`run-slate` reports `DELIVERY_STATE` and `nfl_release_truths_v2`** on every
  `prior_review` exit; Classic C1 and C2 are `NO_DELIVERABLE`, since they write
  no entry file. After a crash the outer handler names a deliverable that still
  revalidates and never deletes it.
- **Not yet:** the baseline published first and replaced by an improvement
  (Session 06), the delivery record (Session 14).

## Capability added: 2026-09-23 (Session 04)

A file can be built from the two DraftKings downloads alone, before any
evidence, prior or model: `nfl baseline`. It is a separate command until
Session 06 puts it first in `run-slate`. Every run still ends
`PRIOR_ONLY / DO_NOT_UPLOAD`. Suite figures are in `changelog.md`.

- **`nfl baseline --salaries --entries [--out-dir]`** (`baseline.py`) writes a
  new run folder with snapshots, `DK_BASELINE_ENTRY_V1_<run_id>.csv`
  (`nfl_baseline_entry_csv_v1`) and `baseline_report.json`
  (`nfl_baseline_report_v1`, carrying `nfl_release_truths_v2`). Exit 0, 3 or 2.
- **Verified on the supplied fixtures**: Classic (719 rows) and Showdown (126)
  at 1, 20 and 150 entries are `DELIVERABLE`, byte-identical on replay; 150
  entries take about 3.6 s Classic and 6.5 s Showdown. A pool with too few
  distinct lineups is `DELIVERABLE_PARTIAL` and names every unfilled row.
- **Lineups rank by DraftKings salary only** (`BASELINE_SALARY_RANK_V1`), with
  DraftKings `OUT`/`IR`/`D` people excluded. They are legal, distinct and
  byte-audited, not tuned: at 150 Showdown entries one person is in 139 lineups.
- **Every gap is a registered limitation**, never silent: no official activity,
  role, weather or model evidence; a salary file short of the entries table; a
  template with no table; a run past the earliest lock.
- **Every `dk.py` and `lineups.py` refusal has a registered code**, and
  `DeliveryLimitation` accepts only the three class/stops pairs.
- **Not yet:** the lock clock (Session 07), prefilled rows and per-contest groups
  (Session 11), `run-slate` baseline-first (Session 06).

## Capability added: 2026-09-23 (Session 03b)

Every blocker code the engine emits has a class, what it stops and its
authority, in one validated file; no operating path reads it yet (Sessions 04 to
09), and no gate's behaviour changed. Suite figures are in `changelog.md`.

- **`config/gate_registry_v1.json`** (`nfl_gate_registry_v1`): 1,088 exact
  codes in 43 families, 15 `V` (stop the file), 3 `S` (construction
  preferences) and 25 `P` (stop certification). Its SHA-256 is pinned.
- **`gate_registry.load_gate_registry`** hashes and validates it: only the pairs
  `V`/`FILE`, `S`/`CONSTRUCTION_PREFERENCE`, `P`/`CERTIFICATION`; no duplicate,
  orphan or unused entry. `GateRegistry.limitation(code, ...)` builds a
  `DeliveryLimitation` from an exact code and refuses anything else.
- **Completeness is test-backed** both ways over `src/nfl_dfs/`: a new blocker
  code without an entry fails, and so does an entry nothing emits. The scan is
  syntactic; what it cannot see is pinned to the source that emits it.
- **Not yet:** codes for the prose-only gates in `lineups.py`, `dk.py` and late
  swap's locked-cell checks; fixed codes for the four emitters that put an Entry
  ID inside the code; any path that builds limitations from the registry.

## Capability added: 2026-09-23 (Session 03)

The fifth truth exists as a contract and a derivation; no operating path emits
it yet (Sessions 04 to 09). No path's behaviour changed, and every run still
ends `PRIOR_ONLY / DO_NOT_UPLOAD`. Suite figures are in `changelog.md`.

- **`release.derive_delivery_state`** gives `DELIVERABLE`,
  `DELIVERABLE_PARTIAL` or `NO_DELIVERABLE` from file validity, the authorized
  and delivered Entry IDs, and the limitations that fired. It takes no model or
  evidence input. Only a `V` limitation (integrity) can withhold a row or the
  file; `S` and `P` ones travel with it. An unfilled row nothing names gets
  `UNFILLED_AUTHORIZED_ROWS`. `release.release_truths_v2` puts the four v1
  truths, unchanged, beside it as `nfl_release_truths_v2`.
- **`contracts.DeliveryLimitation`** (code, class, stops, provenance, Entry IDs,
  people) refuses a `V` gate that stops anything but the file, and a non-`V`
  gate that stops the file.
- **The R24 condition is test-backed** (`tests/test_gate_registry.py`). Weather
  or a roof value is read only in named plumbing (request, gates, evidence
  records, the roof resolver, the weather scripts) and at ten pinned reads in
  numeric code that validate it or copy it into a row; any other read under
  `src/nfl_dfs/` or `scripts/` fails. No arithmetic anywhere takes one as an
  operand, index or branch test beyond four named counting and text sites. Every
  weather state, derived roof included, gives identical prior scores. Not
  caught: plumbing that turns weather into a number under a name that does not
  say weather.
- **`contracts.DeliveryTruth`** carries `delivered_file_valid`, the validity of
  the file it describes, apart from v1 `FILE_VALID`.
- **Not yet:** the per-code gate registry (Session 03b), and any path that
  emits `DELIVERY_STATE`.

## Capability added: 2026-09-23 (Session 02b)

The Classic fallback's first stage and Showdown QA now share the file-first
exit contract. No release truth changed; the fallback's output is still
`PRIOR_ONLY / DO_NOT_UPLOAD`. Suite figures are in `changelog.md`.

- **`scripts/build_classic_portfolio.py`** exits 0 when every blank authorized
  row has a lineup, 2 when it refuses by name with nothing written, and 3 when
  it writes a shortfall with `unfilled_entry_ids` naming each row. It never
  repeats a lineup (R29), including one already prefilled in the template,
  whatever `--max-overlap` allows. DraftKings `OUT`, `IR` and `D` rows leave the
  pool through `nfl_dfs.contracts.UNAVAILABLE_DK_STATUSES`
  (`--available-status D` restores doubtful players, as in the engine); a
  status outside the engine's vocabulary also leaves it and is named. Only
  blank template rows are reserved, read as the writer reads them (a repeated
  Entry ID is refused, a narrow blank row is named unfilled), and `--lineups`
  defaults to their count. The
  ratchet stops at `max(--max-exposure, N)` exposure and `max(--max-overlap, 6)`
  overlap and never tightens a cap. `--out` must be new; the write is a verified
  temporary file and `os.replace`. A Showdown template or salary file, a
  repeated salary ID, an unreadable salary and a truncated scores file are
  refused by name.
- **`scripts/qa_showdown_portfolio.py`** reports `ZERO_QB`, `MULTIPLE_KICKERS`,
  `MULTIPLE_DST` and `DST_WITH_OWN_OFFENSE` as `OBSERVATIONS`, which never
  change the exit code. Roster, identity, cap, one-team, repeated-lineup, byte
  and Entry ID defects keep exit 2.
- **Not yet:** Showdown QA's `--max-overlap` (default 4) and `--backup-pairs`
  limits still exit 2 alongside true defects; Classic QA splits them to exit 2
  apart from validity exit 1.

## Capability added: 2026-09-23 (Session 02)

The Classic fallback's last two stages now check the file, not the JSON. No
release truth changed; the fallback's output is still `PRIOR_ONLY /
DO_NOT_UPLOAD`. Suite figures are in `changelog.md`.

- **`scripts/write_dk_entries.py`** refuses by name (exit 2, nothing written) an
  assignment Entry ID the template lacks, a prefilled row, a roster that fails
  the salary file (size, pool, repeated person, slot or FLEX eligibility, cap,
  two games), a repeated lineup (R29), a Showdown template, and an output path
  that exists or is an input. It fills every blank authorized row or writes the
  file and exits 3 naming each unfilled Entry ID. Untouched lines keep their raw
  bytes; the write is a verified temporary file and `os.replace`.
- **`scripts/qa_classic_portfolio.py --template --export`** audits raw bytes,
  compares each exported roster to its assignment by Entry ID, checks each cell's
  slot, and lists every unfilled authorized row. Exit 1 validity, 3 partial
  coverage, 2 an operator-requested limit, 0 pass.
- **Not yet:** the builder's shortfall still exits 0 and its pool still admits
  DraftKings `OUT`/`IR`/`D` rows, and Showdown QA still fails its exit code on
  strategy findings. Both are Session 02b.

## Capability added — 2026-09-19 (P1)

Three things work that did not, none of them changing a release truth. Suite
`822 passed, 1 skipped in 149.40s` before the review fixes below; see
`changelog.md` for the final figure.

**All three are now live on the operating `prior_review` path.** The
depth-chart contract reached it in chunk `P1b` (same day) via
`nfl_cowork_run_request_v2` and the `--qb-depth-role-evidence-json` flag; before
that it was library-only, and an adversarial review rightly caught this
paragraph overstating it.

- **`SALARY_RANK_DIVERGENCE`.** Every scored person the market prices far above
  this scorer is named in `PriorScores`, in `score_pool`'s report and in the
  selection report, with both ranks, salary, prior, and the evidence state that
  produced the prior. Implemented and tested. Live on the operating path. It
  decides nothing: `does_not_establish` includes `WHICH_SIDE_IS_WRONG`.
- **The unresolved-material-role-change gate.** A person in
  `TRANSFER_PRIOR_UNVERIFIED` who also trips that divergence now stops the run
  and the message names the action that clears it, chosen by position. Ben's
  ruling of 2026-09-19. Implemented and tested. Live on the operating path: it
  runs at the tail of `score_pool`, and both callers that produce lineups go
  through it. This is the Kenneth Walker failure, previously silent and now a
  named stop. For anyone who is not a quarterback the remedy it names is the
  full numerical allocation, which is already plumbed.
- **Quarterback depth-chart evidence**, contract
  `nfl_qb_depth_role_evidence_v1`, producer
  `scripts/make_offensive_role_evidence.py`. Binds `qb_attempt_share` to a
  published depth chart, conserving the team's existing total onto the rank-1
  quarterback and zeroing backups, applied before `score_pool` rather than after
  it. Implemented, tested, and **verified end to end against real bytes**: the
  live nflverse artifact and the committed DET@BUF salary file, producer to
  consumer, through `resolve_qb_depth_roles`. Reachable from `run-slate` and
  `select` since `P1b`, with its hash bound into the pre-lock manifest at all
  three exits.

What it does not do. It moves `qb_attempt_share` and nothing else — a depth
chart establishes who starts, not target or carry share, and the contract says
so and enforces it. It does not touch the objective, ownership, the candidate
bank, or `MODEL_STATUS`. Output remains `PRIOR_ONLY` / `DO_NOT_UPLOAD`.

- **Effective depth rank and OUT-promotion**, `src/nfl_dfs/depth_roles.py`,
  chunk `P7` (2026-09-21), under Ben's `R25` ruling. A published rank-1 who the
  salary bytes flag unavailable no longer stops the run: the next available
  person in the published order inherits the role, and every promotion is named
  in the run record. Ranks are derived for `QB`, `RB`, `WR` and `TE`, keyed
  `(person, position)` so a kick-return line cannot become an offensive role.
  `depth_charts` is now the eighth registered `NflverseSource`, frozen and
  hash-bound into the prior package.

  Verified against real published bytes (artifact sha256 `e6ba0a08…0494c02`,
  snapshot `2026-09-20T12:14:30Z`) for the depth-chart half. **The DraftKings
  half is fixture bytes, not the 2026-09-20 salary export**, which is under a
  gitignored path on Ben's Windows checkout. So this is verified to the same
  standard as a unit-tested contract, not "end to end against real bytes" in the
  sense the entry above means it. The snapshot replay is operator item 6 in
  the archived backlog, now part of Session 16 in `docs/ROADMAP.md`.

  Only the quarterback path is wired into the resolver today. The non-quarterback
  ranks are derived and tested but reach a projection only through
  `redistribute_opportunity`'s optional `depth_ranks`, which is **off by
  default**: the proportional rule it would replace was set by measurement and
  inheritance has not been graded against it. That grading is `P0`.

### Known environment limits, measured the same day

These bound what a cloud session can do and are not claims about Ben's Windows
box. Evidence in `changelog.md` 2026-09-19 and issue #21.

- `data/standings/inbox/` is gitignored, so a fresh cloud clone has no standings
  corpus. `P0`, `P0b`, `P4a`, `P4b` and `P5` cannot run in a cloud session until
  chunk `X2` (Session 17 in `docs/ROADMAP.md`) lands. The archived backlog's
  claim that the corpus is "in the repo" is true only on the Windows checkout.
- Three of the six hosts in `sources.ALLOWED_HOSTS` answer 403 at CONNECT in a
  cloud session: `api.weather.gov`, `api.sleeper.app`, `api.the-odds-api.com`.
  `docs/CLAUDE_CODE_SETUP.md:114-125` asserts otherwise and is being replaced by
  a per-session probe in chunk `X1`. nflverse over GitHub is reachable.
  Re-measured 2026-09-20 and 2026-09-21: unchanged. Since 2026-09-21 `run-slate`
  runs `scripts/session_probe.py` itself and writes
  `data/runs/<run_id>/session_probe.json`, so a run records what it could reach
  instead of leaving it in scrollback. The `doctor` half of `X1` is still open.
- A blank `roof` cell at a retractable-roof venue (ARI, ATL, DAL, HOU, IND) no
  longer demands an `api.weather.gov` capture. nflverse writes `roof` only after
  the game, and `src/nfl_dfs/venues.py` resolves the blank from that venue's own
  completed history in the run's frozen artifact, over the prior-plus-current
  season window, when unanimous and at least eight games. On the 2026-09-20
  afternoon slate this took captures required from 4 of 5 games to 2 of 5. It
  resolves nothing for an outdoor venue, nothing when the window records an open
  roof, and an operator capture still outranks it. Genuinely outdoor games still
  need a real capture, and in a cloud session that capture must be taken
  elsewhere (`docs/RUNBOOK.md` step 0).
- `nfl.sh` as shipped fails the entire suite in a fresh container
  (`2 failed, 226 passed, 1 skipped, 562 errors`) because pytest does not create
  the parent of the `--basetemp` it is handed. Fixed in PR #19, unmerged at the
  time of writing; `NFL_DFS_PYTEST_TMP` is the documented workaround.
- The `DFS_Architect_MCP` server attached to these sessions returns **stub**
  weather. It is never a model input.

## Validation corpus — 2026-09-14 (Q1B and Q1C)

Both tranches are merged to `main` in `4313455fcd8fd722b699a799dbe19dff19c1be68`
(PR #13), together with the previously uncommitted C3 tranche. C3 is merged but
**not accepted**: it stays `BLOCKED` on native Excel acceptance, so it is not
`DONE`, no C4 prompt is prepared, and no later item is `READY`.

**The validation corpus holds zero settled contests.** Ben has entered 18 real
contests across three slates since 2026-09-09; all 18 raw DraftKings standings
exports are now pulled and preserved, one is normalized to
`nfl_standings_csv_v2`, and all 18 are dispositioned as unsettleable with
recorded reasons. Q6's accrual dependency is entirely unmet, and no amount of
later engineering shortens it.

The reason was measured rather than left unknown. No `data/runs/` snapshot held
an `nfl_prelock_run_manifest_v1` or an `nfl_scenario_bank_v1` for any contest:
only the legacy `build` command wrote them, and every contest Ben has actually
entered came through `prior_review`/C1-C3. A pre-lock manifest records what was
predicted *before* lock, so it cannot be written afterwards and was not. Those 18
are permanently unsettleable.

**Q1C closed that gap going forward.** `prior_review` now emits a pre-lock
manifest from every success path, and four settlement gates that no honest
producer could clear were corrected on Ben's ruling — chief among them
`field_size`, which required the pre-lock manifest to record the *settled* entry
count. On a realistic `cowork-run` tree the request builder now resolves
everything except the payout table and the standings pull, which are the two
facts only Ben supplies at settlement time. The next slate he runs, enters and
pulls can settle. None of the 18 already played can, and none was backfilled.

What Q1B does and does not establish:

- **Working, on real bytes:** the normalizer reads all 18 real exports and
  converted contest 193391013's full 126,020-entry field in 5.908s, with its
  reconstructed canonical lineup keys independently matching those
  `lineups.validate_lineup` builds from the review export Ben actually uploaded.
- **Working, on a synthetic slate only:** the `--request` → `--replay` round
  trip, now including a manifest frozen by a real `prior_review` run. The
  settlement itself is still a synthetic complete field where the operator owns
  every entry; no real contest has been settled.
- **Not established:** anything about model quality. One contest's measured
  result (two entries, 17,298th and 17,328th of 126,020, $30.00 each on $20.00
  entries) is a recorded outcome, not evidence that the engine picks good
  lineups, and licenses no EV, ROI, ownership or calibration claim. One slate is
  not a sample, and zero settled slates are not a corpus.
- **Unchanged:** `MODEL_STATUS=PRIOR_ONLY` and
  `RELEASE_DECISION=DO_NOT_UPLOAD`. Landing a settled slate would change no
  release truth, and none landed.

Two defects in `nfl_standings_csv_v2` were found on real bytes and left open for
Ben's ruling rather than worked around: it cannot represent a field member who
never submitted a lineup (11 of 18 exports carry them), and it cannot hold an
exact tie split that is not a whole number of cents (757 entries in 193391013
alone), which means a contest with any uneven tie split can never clear
`STANDINGS_PRIZE_MISMATCH`. Both are detailed under Q1B in
`docs/backlog-archive/backlog-through-2026-09-22.md`; the fix is Session 30 in
`docs/ROADMAP.md`, waiting on Ben's ruling.

One pre-existing test failure is now permanent and unrelated to Q1B:
`tests/test_w6_live_preflight.py::test_live_check_refuses_once_a_selected_player_has_locked`
hardcodes an evidence expiry of 2026-09-14T00:00Z that has now passed, so
`certify_upload` correctly refuses and the test's own helper assertion fails. It
is identical in `HEAD` and will fail every day from now on.

## Pre-slate state — 2026-09-12

The C3 working tree was executed on Cowork/Linux for the first time and
reproduced the Windows result exactly: `sh ./nfl.sh setup` in 9.171s, doctor
`pass_status: true` on Python 3.13.7, and `618 passed, 1 skipped in 152.12s`.
That closes the "actual Cowork/Linux acceptance remains unverified" caveat for
suite execution; it does not close C4, which is a real-slate operator rehearsal
with current evidence.

R21 landed: the Classic selected-evidence gate demanded
`SOURCE_SUPPORTED_ADJUSTMENT` for every selected offensive person, which only a
captured numerical allocation produces and no approved host publishes, so no live
Classic slate could publish a selection. Every Classic test supplied a synthetic
role package, so the suite never saw it. On Ben's 2026-09-12 ruling the gate now
matches Showdown exactly and names every history-derived role it selects on. The
suite after the change and its new coverage is `623 passed, 1 skipped in
144.64s`. The four truths are unchanged: `FILE_VALID` remains artifact-specific,
`EVIDENCE_STATE` remains separately derived, `MODEL_STATUS=PRIOR_ONLY`, and
`RELEASE_DECISION=DO_NOT_UPLOAD`.

C3 was `BLOCKED` on native Excel open/recalculate/save/reopen acceptance until
2026-09-22, when Ben's R30 closed it for software acceptance and deferred the
Excel step to Session 35 in `docs/ROADMAP.md`. Nothing waits on Excel.

`device_bash` has been unusable since a Windows update released 2026-09-08; the
other device tools work, so the repo is staged into the cloud container, built
and tested there, and changed files are written back.

## Current development program — 2026-09-15

Superseded 2026-09-22: the only queue is now `docs/ROADMAP.md`, and this
program is archived verbatim in `docs/backlog-archive/backlog-through-2026-09-22.md`.
The queue was `Reprioritized development program — 2026-09-15
(prize tail first)` in `backlog.md`, built on
`docs/STANDINGS_DUAL_OPTIMIZATION_FINDINGS_2026-09-15.md` and
`docs/STANDINGS_GREENFIELD_FINDINGS_2026-09-15.md`. `P0` (standings grading
harness) and `P1` (salary-divergence diagnostic and current-team role evidence
producer) were `READY` on that date. **Superseded 2026-09-19:** `P1` is `DONE`
(see the section at the head of this file); `P0` is the only `READY` chunk left
and is blocked in cloud sessions on chunk `X2`. `C3`'s software acceptance passed on 2026-09-14; the
program proposes splitting its native Excel step out as `C3X` (`DEFERRED`) and
re-sequencing `C4` behind `P2`, pending Ben's ruling, and until he rules `C3`
keeps its `BLOCKED` status. Every other item is `BLOCKED` on the chunks named
there. Nothing in the program
changes a release truth: all output remains `MODEL_STATUS=PRIOR_ONLY` and
`RELEASE_DECISION=DO_NOT_UPLOAD` until Q6 promotion, which still waits on
settled-slate accrual. What the standings established about the current engine,
in one line each: the expectation objective cannot target the tail and its
priors overshoot 1.5 to 2x; a transfer with no current-team evidence can carry a
backup-level prior while priced as the slate's best player; exposure caps as the
only diversifier produce single-thesis portfolios; Showdown first place is
shared 5 to 200 ways and the objective does not know; expectation lineups were
assigned to first-place contests by construction.

## Current development program — 2026-09-11

DEV0 is complete on merged `main` commit
`7f083fbd77620d96e3f0571f09d93fdaeb32e377` (PR #9; reviewed source
`652c855`). That baseline retained the excluded user/generated paths and
recorded `516 passed, 1 skipped` plus doctor, compile, and whitespace checks. Q1
is now complete on `codex/q1-settlement-reference-economics`: focused tests
passed 46/46 and the final full suite passed `542 passed, 1 skipped` in 117.86s;
doctor, compile/import, whitespace, mutation, overwrite, and copied-package
replay checks passed. C1 is complete on
`codex/c1-classic-intake-prior-review` at unchanged baseline HEAD
`9d25ad75f6fd08a22b700e3062b7304158e5c0c8`: the shared frozen prior/projection
path now covers multi-game Classic, selected activity/current-role evidence
fails closed, and one-command prior review emits deterministic selection and
complete-slate coverage JSON without an upload-shaped CSV. Final verification
collected 555 tests (`554 passed, 1 skipped`) and passed doctor, compile/import,
whitespace, replay, mutation, prohibited-path, and benchmark checks.

C2 is complete on `codex/c2-classic-policy-candidates-portfolio` at unchanged
baseline HEAD `90361980959916333cbd4b820680166a7e4fe6a2`. Classic now has a
canonical exact-input policy with direct integer player/team/game bounds,
exclusions, hard/advisory groups and registered stack rules, uniqueness and
pairwise overlap. Deterministic documented construction strata produce a
bounded legal candidate bank; one joint MILP assigns one unique lineup to every
ordered reserved Entry ID; a separate canonical-artifact audit reparses policy
bytes and recomputes identity, legality, every hard count and all overlaps.
Candidate, assignment and audit output is machine-readable JSON only. It never
calls ownership, field, duplication, payout/economics, production portfolio, or
C3 review/export code and never emits a Classic assignment or upload-shaped
CSV. Final verification passed `203 passed, 1 skipped` focused and `581 passed,
1 skipped` full, plus doctor, compile/import, whitespace, replay, mutation,
prohibited-path, adversarial-diff, and synthetic scale checks. The 150-entry
synthetic case built 174 candidates and selected the portfolio in 4.015856s
total with 432,880 bytes peak traced Python memory. This is optimal only over
the reported actual bounded bank; it is not the C3 full 719-person acceptance,
not a calibrated objective, and not upload-ready.

C3 is implemented on `codex/c3-classic-audit-review-export` at unchanged
baseline HEAD `f2890a6c587b01cede2e07bdcbb3ec1dd0ab0d33`. A new downstream
auditor strictly reparses and re-hashes every authoritative C1/C2 artifact at
four boundaries, independently recomputes Classic identity, legality, salary,
policy counts, stack/group semantics, evidence, uniqueness and every pairwise
overlap, and byte-diffs the proposed and final exact-template review CSV. Only
audit `PASS` can publish `DK_REVIEW_ENTRY`; every tested mutation, stale or
partial output, prefilled or unauthorized row, unavailable/current-role stop,
non-optimal state, and display disagreement withholds all new C3 output. The
successful package adds canonical audit/readable JSON, escaped self-contained
HTML, and a Classic eight-sheet workbook while preserving Showdown behavior.

The supplied 719-person/24-team/12-game fixture passed registered 1/3/20/150
entry acceptance and short-path copied-package replay with byte-identical
canonical policy, bank, assignment, audit, selection, coverage, readable
JSON/HTML, and review CSV hashes. Independent rendering inspected all eight
workbook sheets and every page of the nine-page HTML PDF. C3 nevertheless
remains `BLOCKED`: the installed Excel automation endpoint refused the required
native open/recalculate/save/reopen operation. No C4 prompt was created and no
later item is `READY`. The four truths remain independent and fixed at
`FILE_VALID=true`, `EVIDENCE_STATE=PASS`, `MODEL_STATUS=PRIOR_ONLY`, and
`RELEASE_DECISION=DO_NOT_UPLOAD` for the test-only acceptance packages.
Golden/adversarial C3 coverage passed 36/36; the combined focused regression
passed `217 passed, 1 skipped` in 265.42 seconds; and the complete pinned suite
collected 619 tests and passed `618 passed, 1 skipped` in 364.86 seconds. Doctor,
changed-module compile/import, whitespace, exact-byte, Entry-ID order,
copied-package hash, render, mutation, and no-`DK_UPLOAD` checks passed.

## Current Showdown readiness — 2026-09-09

The recorded pre-SD2 real NE–SEA two-entry template completed `cowork-run --profile
prior_review` through source acquisition, projection, selection and independent
review export. The repeated export is byte-identical; only the two reserved
entry rows change. See `docs/READINESS_REVIEW_2026-09-09.md` for the current
verification, fixes and limitations. SD2 requires fresh history coverage and
role evidence when roles changed; that older rehearsal does not establish
current live SD2 readiness. Older supplied-fixture counts below are
historical. This verifies Windows execution, not the actual Cowork/Linux VM.

The generated portfolio is still `PRIOR_ONLY / DO_NOT_UPLOAD`. Its objective
maximizes points of an expected stat line, with structural differentiation;
it is not the required calibrated ceiling/ownership/drawdown engine. Current
official activity, prospective validation and the quantitative redesign remain
blocking work. Supplied current official inactive rows now affect both roles
before prior-review selection. The older simulation/build path still needs its
own participation and economics repairs.

SD1 now gives the prior-review scorer one conserved team kicker event line.
Exact, source-bound current-role evidence can declare a sole kicker or an
explicit numerical split; ambiguous multi-kicker teams block, zero-share and
excluded people cannot be selected, and the single-kicker compatibility path is
reported only as an `UNKNOWN` prior assumption. This is a scoring/input-integrity
repair, not completion of offensive roles or live current-role modeling.

SD2 adds `nfl_offensive_role_evidence_v1`, strict captured numerical allocations,
five distinct current-role states, current-team-only historical denominators,
missing-efficiency gates and preserved unallocated volume. It removes generic
historical redistribution from the prior-review and standalone prior-selection
paths. Historical snap share is diagnostic only. Source-supported adjustments
run after all existing exclusions, and expiry/hash changes block review export.
The real freeze/project/select/export code has been exercised on portable,
clearly labelled synthetic captures, including the frozen LA/LAR team crosswalk.
See the Showdown priority tracker for final verification results. Live compatible
numerical offensive-role captures and actual Cowork/Linux acceptance remain
unverified. W3's simulator mask and full forward-role model remain incomplete.

SD3 adds the exact-bound `nfl_showdown_portfolio_policy_v1` contract. It binds
the immutable salary SHA-256, single game, complete underlying-person/CPT/FLEX
identity map and full requested Entry-ID sequence; normalizes numeric fractions
with exact-decimal floor rounding; reports declared and effective combined-person
and Captain limits; and defines canonical lineup, uniqueness and pairwise-person
overlap semantics. Necessary capacity findings do not claim solver infeasibility.
SD4 now enforces the normalized contract in the Showdown `prior_review` profile
through a bounded legal candidate bank and one joint MILP, assigns the exact
Entry-ID sequence without cycling, and independently re-audits every control and
bound artifact immediately before export. Feasible results remain optimal only
over the reported actual bank; incomplete-bank exhaustion is not called full-
slate infeasibility. Policy-free SD1/SD2 behavior is unchanged.

SD5 adds a readable review layer without changing selection or release policy.
After a valid prior-review export, it independently reparses the exact salary,
entry, assignment, exported review CSV, selection report, normalized policy and
policy audit; rechecks every bound hash; and recomputes lineups, salaries,
combined-person/Captain exposure, uniqueness and pairwise overlap before any
display is marked `PASS`. The generated package contains canonical JSON, escaped
self-contained HTML and an eight-sheet workbook with exact assignments,
exposure, evidence/role observations, provenance, all four release truths and
one next action. A mismatch fails closed at `READABLE_REVIEW`, preserves earlier
artifacts and returns no top-level review-export path. The layer remains
`PRIOR_ONLY / DO_NOT_UPLOAD`; actual Cowork/Linux and current real-evidence
acceptance are SD6.

## Working and locally verified

- The red-team revision has replaced the prior `plan.md`.
- All five supplied DraftKings/rules artifacts are preserved byte-for-byte with
  a checked SHA-256 manifest. Repository attributes now disable text conversion
  for byte-sensitive CSV, workbook, and supplied-fixture paths. Both critiques
  remain preserved.
- `nfl.ps1` provides setup, guided run, intake, validation, build,
  certification, audit, governed late swap, settlement capture, learning gates,
  and tests through one Windows launcher.
- `nfl.sh` provides the pinned Linux/Cowork launcher. `cowork-run` discovers
  arbitrarily named CSV attachments by first-row schema, rejects ambiguous
  duplicates, snapshots every recognized input, and writes a normalized
  `nfl_cowork_run_request_v1` request for deterministic reruns.
- The Cowork path can chain a complete supplied request through diagnostic or
  registered build, REFEREE QA, and certification. An incomplete two-file run
  produces a versioned review workbook and `cowork_run.json`, names every
  blocker, and leaves no upload-shaped CSV.
- Cowork model-assisted runs require a frozen source-ledger artifact; the
  ledger, team projections, and player opportunities are independently hashed
  into the certification manifest. Hash binding does not by itself validate an
  external source's truth or license.
- `nfl.ps1 project` / `nfl.sh project` now provide the minimum S6A producer.
  Four immutable hash-pinned inputs (salary, team prior, player prior, and exact
  frozen identity map) are validated without network access; position-eligible
  weights are deterministically conserved to team shares; exact Classic or
  Showdown FLEX identities are enforced; and both loader-valid CSVs plus the
  strict source ledger are atomically published only after independent hash and
  contract reconciliation. DraftKings APPG remains raw-only.
- Classic and Showdown salary contracts enforce exact IDs, geometry, salary
  cap, underlying-person identity, distinct CPT/FLEX IDs, and exact 1.5x Captain
  salary/scoring behavior.
- Showdown kicker-role evidence binds the salary hash, game/team, underlying
  person, exact CPT/FLEX IDs, allowlisted captured source bytes and hashes,
  observation/capture/expiry times, and transformation version. Allocation is
  applied to team scoring events before DraftKings scoring and the Captain
  multiplier, conserving base team kicker points exactly once. Supplied invalid,
  stale, future, tampered, incomplete, or newly ineligible allocations fail
  before assignments/review export; Cowork snapshots the manifest and sources
  for path-independent replay.
- Showdown portfolio-policy inputs are path-confined, copied into immutable
  content-addressed snapshots, validated against all requested entries and exact
  role identities, and written as stable normalized bytes with source and
  normalized SHA-256 values. The `prior_review` selector uses the exact SD3
  integer maxima over a default 32-candidate bank, reports generation and joint-
  solve budgets/status/coverage, and permits Captain repetition only when the
  effective Captain maximum allows it. Immediately before export, a separate
  audit strictly reparses the canonical normalized-policy artifact, re-reads exact
  assignment bytes, recomputes legality, exposure, Captain, canonical-uniqueness
  and pairwise-overlap facts, reconciles selector summaries, and binds salary,
  entry, source-policy, normalized-policy and assignment hashes.
  Only `ENFORCED_AND_INDEPENDENTLY_AUDITED` can reach the review-entry writer.
- One build/certification package is deliberately limited to one Contest ID and
  one entry fee. Mixed-contest exports fail closed until per-contest economics
  and allocation are implemented.
- Payouts enforce contiguous paid ranks, monotonic tiers, advertised-value
  reconciliation, finite exact-cent cash values, whole ticket counts,
  field-size bounds, cash/ticket distinction, and exact tied-rank division.
- Q1 settlement capture consumes a strict hash- and version-bound request and
  atomically publishes a never-overwritten copied package containing every
  salary, reserved-entry, payout, assignment, pre-lock prediction/model,
  scenario, metric-registry, and complete standings artifact. It rejects
  contest, draft-group, mode, Entry-ID, artifact, version, rank, prize, and
  source-mutation disagreement. The generated machine-readable brief and
  package-relative replay request reconstruct without conversation history.
- The Q1 reference evaluator is independent of the vectorized production
  economics path. Decimal six-place score rounding, strict-above ranks, exact
  tie occupancy, rational-cent cash/ticket division, complete-lineup
  duplication, and multiple owned entries are evaluated exactly within an
  explicit size/work/runtime budget or refused with a named blocker. A copied
  package must reproduce the same semantic assignment and reference-result
  hashes.
- `config/metric_registry_q1_v1.json` predeclares player-outcome,
  participation, ownership, duplication, rank/payout-tail, portfolio-risk,
  runtime, and memory metrics with uncertainty, ESS, temporal split, sample,
  promotion, noninferiority, demotion, and rollback requirements. `learn`
  refuses a registry that did not precede challenger evaluation. No model was
  promoted.
- Manual assignments can be independently validated and exported into only the
  blank, authorized Entry-ID rows. Untouched lines preserve their exact bytes,
  including original BOM state. The final CSV is reparsed and SHA-256 bound.
- Certification reports `FILE_VALID`, `EVIDENCE_STATE`, `MODEL_STATUS`, and
  `RELEASE_DECISION` independently. Legal proposed bytes are constructed,
  audited, reparsed, and hashed in memory even when evidence or model blockers
  require `DO_NOT_UPLOAD`; no upload-shaped CSV is persisted in that case.
- Governed late swap has a separate fail-closed writer for fully prefilled
  DraftKings bulk-edit templates. It binds a prior `CERTIFIED` manifest and
  assignment, derives replaceable cells only from exact IDs and lock times,
  preserves locked and unauthorized bytes, independently audits and reparses
  the candidate bytes, and writes a new immutable output only after every gate
  passes. The ordinary pre-lock writer still rejects prefilled rows.
- Hard evidence is typed and fail-closed. Current official status uses exact IDs
  and operator-controlled source evidence; fuzzy names cannot certify. Official
  activity rows retain their real observation times and expire after the
  registered three-hour lock window. Market/weather rows are bounded,
  enumerated, source-ledger-bound, and expire after six hours.
- Late swap additionally requires source-bound eligibility for the exact
  Contest ID and versioned team-scoped official inactive negative lists.
  Explicitly empty team reports are supported; missing teams remain unknown,
  report freshness is T-90/lock-relative, and `NOT_YET_DUE` cannot clear a
  final late-swap release decision.
- Model-assisted certification requires `PASS` opportunity evidence for every
  selected player. Non-PASS uncertainty elsewhere in the salary pool is
  counted and retained as a prior-only model limitation rather than mislabeled
  as selected-player hard evidence. The build report is bound to the exact salary, entry,
  payout, team, and player input hashes plus the contest parameters; a report
  from a different build cannot clear certification.
- The live model path uses explicit opportunity inputs, deterministic team-share
  conservation, a vectorized heavy-tailed simulator, separate DESIGN/SELECT/
  REFEREE banks, direct persistent HiGHS MILPs, candidate-family coverage,
  cold ownership stress states, complete legal opponent lineups with
  multiplicities, exact duplication/ties, and contest-aware portfolio metrics.
  Multiple reserved entries are settled against one another as well as against
  the simulated opponent field.
- The field evaluator retains no field-by-scenario matrix. Full candidate banks
  are reduced before scenario/economics arrays are retained. Candidate and field
  scores use the same float64 gather/sum path, ranks are vectorized, and divided
  payouts use a vectorized cumulative prize table.
- Quantitative QA is executed after selection, persisted in the build report,
  and hash-bound into certification. REFEREE remains report-only in the sense
  that it cannot tune or reselect, but its independent confidence-aware sign or
  genuine safety disagreement is a binding promotion blocker. Solver proof is
  persisted. Construction preferences such as `DST_OPPOSING_PASS_STACK` and
  candidate-family coverage are advisory unless a registered hard policy is
  enforced by the solver and validator.
- Exact one-to-three-entry search is exhaustive only inside an explicit bounded
  shortlist (maximum 50,000 combinations); combinations are evaluated in
  vectorized batches and the effective search size is reported.
- The five-sheet operator-input workbook remains the stable staged-input
  contract. A successful Showdown `prior_review` output extends its copied
  review workbook to eight sheets: exact Portfolio rows, Exposure, Review
  Evidence and Artifacts sit beside Run Control, Evidence Paste, QA and Upload.
  Formula-active prefixes and markup are inert at the display boundary; exact
  identities and source bytes stay in the hash-bound artifacts. The output has
  explicit print areas, repeated headings and normalized freeze panes, opens
  normally in native Excel, and renders without formula errors.
- Versioned Parquet scenario storage, rolling-origin challenger fitting, model
  promotion tiers, multi-slate rollback rules, Q1 settlement capture, and
  locked-cell late-swap audit are implemented. The SQLite registry and lifecycle
  transition guard are library components exercised by tests but are not yet
  wired into live runs.

## Deliberately diagnostic or externally gated

- No supplied contest payout table, field size, or official current activity
  evidence exists. Therefore no real supplied-slate upload is certified.
- The Cowork instruction and orchestration layer does not manufacture those
  missing facts. A salary-plus-entry first pass is expected to remain
  `DO_NOT_UPLOAD` until Claude freezes approved evidence and the operator
  supplies any unavailable contest-specific facts.
- The supplied entry template is Classic. Showdown upload remains hard-blocked
  until matching Showdown entries and payouts are supplied.
- Opportunity, field, ownership, duplication, and payout predictions remain
  diagnostic until prospective historical/live validation clears the registered
  sample and calibration gates. The engine does not label them EV, ROI, win
  probability, or calibrated ownership.
- SD1 does not produce current offensive roles. A live slate still needs current
  approved kicker-role captures when multiple kickers remain eligible, and
  synthetic role fixtures prove mechanics only. A sole-listed assumption does
  not establish official activity or model readiness.
- S6A creates source-bound `PRIOR_ONLY` inputs but does not implement the full
  Section 4.4 historical ingestion, offline fitting, prospective validation, or
  live-source refresh architecture. A successful producer run therefore
  remains `DO_NOT_UPLOAD` until the separate evidence and model gates pass.
- nflverse, NWS, and Sleeper are policy-bound source adapters, but a live season
  backfill and license/schema audit have not been run from the supplied files.
- A synthetic full-width Classic benchmark built 20,000 candidates in 144
  seconds, covered every registered Classic construction family, retained a
  250-lineup economics shortlist, and respected the 4 GiB memory cap. It used
  only 50 scenarios in each DESIGN/SELECT/REFEREE bank. The complete registered
  10,000/20,000/20,000 refresh and real-data 10/5-minute gates therefore remain
  unclaimed until the operator supplies complete model inputs.
- Late swap can safely write an operator-proposed, evidence-cleared change to a
  current prefilled bulk-edit template. A calibrated joint conditional
  contest-state reoptimizer remains gated on live standings, ownership, scores,
  and validated remaining-game models; S2 does not implement or claim one.
- Runtime scenario defaults and certification deadlines come from
  `config/runtime.json`; hard-evidence requirements come from
  `config/evidence_policy.json`; `config/scoring.json` is validated against the
  executable salary-cap and Captain rules before a build or certification.
- Exposure envelopes, historical pair-dependence bands, and material
  ownership/market sensitivity thresholds are not yet registered inputs. The
  active QA pass leaves those triggers unasserted instead of inventing limits.
- The portfolio policy remains a user-control contract, not model evidence or a
  calibrated risk claim. Its SD4 solve is bounded to the actual reported bank
  and has not been benchmarked at 20 or 150 entries. Actual Cowork/Linux use,
  current live policies/evidence and prospective model quality remain unverified.
- Weekly rolling-origin fitting, promotion, influence caps, and rollback logic
  are implemented, but automatic deployment correctly has nothing eligible to
  promote before settled-slate history accumulates.

These are evidence gates, not silent fallbacks. Their operational result is
`SIMULATION_DIAGNOSTIC_ONLY` or `DO_NOT_UPLOAD`, never a misleading readiness claim.
