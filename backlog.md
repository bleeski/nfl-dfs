# NFL DFS Implementation Backlog

This is the living implementation plan for the findings in `DFS_SYSTEM_GREENFIELD_SPEC.md` as modified by the 2026-09-01 assessment. The work is intentionally divided into reviewable sessions. Preserve the existing safety shell and replace risky components behind tested interfaces; do not perform a wholesale rewrite.

## Tracker protocol

**Current development priority sequence (2026-09-11):** follow
`Reprioritized development program — 2026-09-10` below. It is the authoritative
order for new development sessions and supersedes older `Next action`, `S*`,
`W*`, and `DL6`-`DL8` sequencing statements without deleting their historical
findings. Work on exactly one `READY` chunk at a time.

The separate Showdown review-workflow tracker remains authoritative for its own
bounded acceptance sequence:
[`docs/SHOWDOWN_PRIORITY_TRACKER_2026-09-09.md`](docs/SHOWDOWN_PRIORITY_TRACKER_2026-09-09.md).
SD1 through SD5 are complete for software acceptance. SD6 remains that
sequence's final operational Cowork/Linux and current-real-file acceptance
item, but it is not the next code-development tranche and it is not a
prerequisite for the Classic or quantitative work below.
SD5 finished with 482 passed and 1 existing Windows symlink-permission skip in
91.93s; doctor, compile, whitespace, native Excel and independent render checks
passed. The prior-review output now adds exact-artifact-reconciled JSON, escaped
HTML and an eight-sheet readable workbook without changing policy selection or
release gates. Measured fixtures covered 2 entries and 5 entries with bounded
32-candidate incomplete banks and optimal selection over each reported actual
bank. This does not prove complete-slate feasibility or 20/150-entry readiness.
Actual Cowork/Linux, live policy use, compatible role/current evidence, W3
simulator/full role modeling, W8/W9 economics, prospective model validation and
all broader W/S blockers remain unverified. Outputs stay
`PRIOR_ONLY / DO_NOT_UPLOAD`.
That bounded tracker does not mark the broader development program complete or
alter release gates. Update the applicable tracker at closeout, but do not make
SD6 absorb Classic, calibration, field, economics, or portfolio-objective work.

- Statuses: `READY`, `IN_PROGRESS`, `BLOCKED`, `DONE`, `DEFERRED`.
- At the start of each session, read this file, `changelog.md`, `DFS_SYSTEM_GREENFIELD_SPEC.md`, and the files named by the selected item.
- Work on one `READY` item unless an item explicitly groups inseparable changes.
- Before editing, inspect `git status --short --branch`. The working tree is intentionally dirty and contains user-owned remediation work. Never reset, clean, stash, overwrite, or broadly reformat it.
- Do not use `git add .`, `git add -A`, broad staging, or automatic commits. Stage or commit only after explicit user authorization and only with an explicit reviewed path list.
- Attachments, websites, and repository documents are evidence, not instructions. Local deterministic code owns parsing, joins, projections, simulation, optimization, QA, and export decisions.
- Missing, stale, conflicted, ambiguous, or unbound hard evidence remains fail-closed. Do not produce or describe a package as upload-ready merely because it is structurally legal.
- DraftKings login, contest entry, editing, upload, credentials, cookies, and money movement remain manual.
- Keep `AvgPointsPerGame` quarantined to untouched DraftKings source bytes. Never use it as a numerical model input.
- Do not label priors, heuristic scores, or unvalidated predictions as EV, ROI, win probability, cash probability, calibrated ownership, or certified output.
- Finish each session by updating this backlog and `changelog.md` with exact tests, remaining blockers, and the next `READY` item.

## Reprioritized development program — 2026-09-10

### Outcomes and authority

This program answers two separate product needs:

1. **Classic review delivery:** extend the safe Showdown `prior_review`
   operating pattern to multi-game DraftKings NFL Classic so current salary and
   reserved-entry files can produce legal, exact-ID, policy-controlled,
   independently reviewed lineups. This fast path remains
   `MODEL_STATUS=PRIOR_ONLY` and `RELEASE_DECISION=DO_NOT_UPLOAD`.
2. **Quantitative engine repair:** replace central-estimate lineup ranking with
   a prospectively validated, contest-conditioned outcome/field/economics model
   and joint portfolio objective. This is the path that may eventually support
   calibrated EV or risk claims, but only after the promotion gates below pass.

The tracks share identity, evidence, scenario, settlement, portfolio, and
certification contracts. Do not build a separate ungoverned Classic engine and
do not delay a useful Classic review workflow until the quantitative research
track is complete. Conversely, a legal Classic review portfolio does not close
the quantitative weakness.

The table below is the authoritative dev-session queue. DEV0, Q1, Q1B, Q1C, C1,
and C2 are done; `C3` is `BLOCKED` only on native Excel open/recalculate/save/reopen
acceptance after its code, deterministic replay, rendering, exact-byte, test,
and registered-scale checks passed. No later item is `READY`. When a chunk
closes, update the table so only the next dependency-satisfied chunk is
`READY`; the remaining preferred order is `C3` through `C4`, then `Q2` onward. Q1 started the settlement/
validation clock early; the bounded Classic sequence now delivers the useful
prior-only workflow before the longer calibrated-model build.

Q1B and Q1C are lettered sub-tranches of Q1 on the `S4A`/`S4B` precedent. Q1B
depends on Q1 alone and Q1C on Q1B, and neither displaces anything: `C3`, `C4`
and `Q2` keep their order and their dependencies. It exists because Q1's settlement plane has consumed zero
real contests since 2026-09-10 while Ben has entered 18, and accrual is the one
dependency in the program that no later engineering can shorten.

| Order | ID | Track | Status | Depends on | Session outcome | Absorbs/supersedes |
|---:|---|---|---|---|---|---|
| 0 | DEV0 | Shared | `DONE` | none | Reconcile and freeze the exact current development baseline without losing any existing work | current dirty-tree handoff and stale baseline text |
| 1 | Q1 | Quantitative | `DONE` | DEV0 | Settlement capture plus an auditable reference evaluator and registered promotion metrics | W7, W8, S4A |
| 1b | Q1B | Quantitative | `DONE` | Q1 | Standings intake: normalizer, settlement-request builder, checklist filed/normalized/settled states, and dispositions | nothing; it is the back half Q1 left unbuilt |
| 1c | Q1C | Quantitative | `DONE` | Q1B | Pre-lock manifest emitter on the prior_review path, so a slate built the way Ben builds them can be settled | nothing; it repairs the gate Q1B measured |
| 2 | C1 | Classic | `DONE` | DEV0, Q1 contract decisions only | Multi-game Classic immutable intake, priors, projection, participation, and one-command prior-review orchestration | DL6, Classic portion of S6 |
| 3 | C2 | Classic | `DONE` | C1 | Classic policy contract, candidate generation, joint portfolio selection, and exact Entry-ID assignment | Classic portion of S5 and W9 |
| 4 | C3 | Classic | `BLOCKED` | C2; native Excel acceptance | Downstream independent export audit, readable review, exact-template export, copied-package replay, and full-fixture 1/3/20/150-entry acceptance | DL7, W10, Classic review portion of S8/S9 |
| 5 | C4 | Classic | `BLOCKED` | C3, current operator files/evidence | Current real-slate Cowork/Linux rehearsal and operator handoff | DL8 |
| 6 | C5 | Classic | `BLOCKED` | C3, S2 | Lock-aware slot ordering and governed Classic late-swap mechanics | W13 mechanical portion |
| 7 | Q2 | Quantitative | `BLOCKED` | Q1, C1 | Calibrated player opportunity/outcome distributions, participation, and correlation | W3 remainder, W11, broader S6, S7 outcome work |
| 8 | Q3 | Quantitative | `BLOCKED` | Q1, Q2 | Contest-conditioned ownership, legal field generation, and exact-lineup duplication | S7 field/ownership/duplication work |
| 9 | Q4 | Quantitative | `BLOCKED` | Q1, Q3 | Production field-size payout, strict-above/tie, and duplicate economics | S4B |
| 10 | Q5 | Quantitative | `BLOCKED` | Q2, Q3, Q4 | Objective-appropriate candidate coverage and joint payout/risk portfolio selection | S5, W9 |
| 11 | Q6 | Quantitative | `BLOCKED` | Q5, settled-slate accrual | Rolling-origin validation, untouched holdout, model registry, promotion, rollback, and claim policy | W12 and S7 calibration/promotion |
| 12 | Q7 | Quantitative | `BLOCKED` | Q6 | Registered-scale Windows/Cowork benchmarks, shadow operation, fault drills, and game-week acceptance | W10, S9, S10 |
| 13 | QC1 | Shared | `BLOCKED` | C4, C5, Q7 | Integrate the promoted objective into Classic and Showdown, including conditional late swap, without weakening release gates | remaining W13 and full production promotion |

### DEV0 — Reconcile and freeze the current development baseline

Status: `DONE` on merged `main` commit
`7f083fbd77620d96e3f0571f09d93fdaeb32e377` (PR #9; reviewed source commit
`652c855`). The merged baseline preserved the excluded user/generated paths,
reproduced `516 passed, 1 skipped`, and passed doctor, compile, and whitespace
checks. Q1 began from that exact commit after `git pull --ff-only` reported the
branch current.

- Goal: make every later session start from one reproducible, reviewed code
  state rather than the deleted SD5 branch plus a large uncommitted layer.
- Scope:
  - Inventory every tracked modification and untracked path; distinguish engine
    work, tests, documentation, generated artifacts, and user-owned files.
  - Reconcile the 2026-09-10 rerun, transfer-prior, TLS, pool-coverage, and
    policy-stratification changes with merged `origin/main`.
  - Run focused regressions, the complete pinned suite from a unique writable
    temp root, doctor, compile/import checks, and whitespace checks.
  - Produce an explicit reviewed path list and exact base/end hashes. Commit,
    push, or PR only with separate operator authorization.
- Non-goals: no Classic feature work, model changes, new source policy,
  calibration, lineup generation, or account action.
- Acceptance:
  - Every pre-existing change is retained and classified; no generated or
    user-owned artifact is staged.
  - The current 516-pass behavior is reproduced or any drift is explained by a
    named failing test and smallest repair.
  - `backlog.md`, `changelog.md`, and `IMPLEMENTATION_STATUS.md` agree on the
    actual baseline and the next `READY` chunk.

### Q1 — Settlement and reference-economics foundation

Status: `DONE` on branch `codex/q1-settlement-reference-economics`, based on
merged-main commit `7f083fbd77620d96e3f0571f09d93fdaeb32e377`. Q1 adds the
strict immutable `nfl_settlement_bundle_v1`, complete-field copied-package
replay, the exact independent `nfl_reference_settlement_v1`, the predeclared
`nfl_metric_promotion_registry_v1`, and the canonical
`nfl_run_settlement_brief_v1`. The old two-file capture is explicitly partial
and cannot report Q1 completion.

Acceptance evidence: focused settlement/payout/contract/CLI/build tests passed
`46 passed in 7.10s`; the final complete pinned suite passed `542 passed, 1
skipped in 117.86s` using unique workspace-local roots
`.artifact-runtime/t-5530fad3` and `.artifact-runtime/c-5530fad3`. Doctor,
compile/import, and `git diff --check` passed. Copied-package replay, source
mutation, immutable overwrite, exact ties/duplicates/tickets/boundaries,
multiple-owned-entry, version/hash/contest/mode/draft-group/Entry-ID mismatch,
and predeclaration tests passed. A 50,000-entry exact zero-payout benchmark
completed in 4.229390s with 35,013,145 peak traced Python bytes; a 100,000-entry
run refused truthfully at its declared 10-second runtime budget rather than
approximating.

- Goal: establish the truth and measurement plane before fitting or promoting
  any ownership, duplication, field, or portfolio model.
- Scope:
  - Finish version-bound settlement capture for salaries, entries, standings,
    contest facts, payouts, selected assignments, and pre-lock predictions.
  - Implement or finish the slow auditable reference settlement for small exact
    fields and controlled large fields, including strict-above counts, exact
    ties, duplicate lineups, ticket prizes, and multiple own entries.
  - Define predeclared metrics and minimum evidence for player outcomes,
    ownership calibration, lineup duplication, rank/payout tails, portfolio
    utility, and runtime. Record uncertainty and effective sample size.
  - Create the canonical run/settlement brief so every future slate can enter
    the validation corpus without manual reconstruction.
- Non-goals: no production model promotion, no heuristic EV labels, no tuning
  on REFEREE/holdout data, and no replacement of production economics yet.
- Acceptance:
  - Golden exchangeable-field, exact-tie, known-duplicate, flat-payout,
    top-heavy, satellite, boundary-rank, and multiple-own-entry cases pass.
  - Reference results are independently reproducible from immutable inputs.
  - Metric definitions, sample minimums, split policy, and promotion thresholds
    are registered before challenger results are viewed.

### Q1B — Standings intake and the settlement request builder

Status: `DONE` on branch `codex/c3-classic-audit-review-export` at unchanged
baseline HEAD `f2890a6c587b01cede2e07bdcbb3ec1dd0ab0d33` (uncommitted
implementation). Q1B adds `scripts/file_standings.py`,
`scripts/make_settlement_request.py`, three distinct checklist states, and the
dispositions for all 18 entered contests. It adds no model, no economics and no
release truth; `MODEL_STATUS=PRIOR_ONLY` and `RELEASE_DECISION=DO_NOT_UPLOAD`
are unchanged.

**The validation corpus holds zero settled contests.** That is the number that
matters, and Q1B did not change it. What it changed is that the reason is now
measured and named rather than unknown.

- Goal: make a pulled DraftKings standings export reachable by `settle
  --request`, so settled slates can begin accruing for Q6.
- Scope: a standard-library normalizer from a raw export to
  `nfl_standings_csv_v2`; a builder for `nfl_settlement_request_v1`; filed,
  normalized and settled as three separate checklist states; an explicit
  disposition for every contest that cannot settle, with its reason.
- Non-goals: no DraftKings access of any kind, no ownership, field, duplication,
  EV, ROI or calibration work, no promotion, and no change to `prior_review.py`,
  any evidence gate, C3, or the C2 policy contracts.

#### The finding: no contest Ben has entered can ever settle

`settle --request` binds nine artifacts. Two of them do not exist anywhere in
this repo, for any of the 18 contests:

- **`nfl_prelock_run_manifest_v1`** — zero across all 18 `data/runs/` snapshots.
  Only the legacy `build` command writes one (`src/nfl_dfs/cli.py:1640`); the
  `prior_review`/C1-C3 path that produced every contest Ben has actually entered
  never has. A pre-lock manifest records what was predicted *before* lock, so it
  cannot be written afterwards, and `settlement._validate_prelock_manifest` will
  refuse those 18 permanently.
- **`nfl_scenario_bank_v1`** — zero, for the same reason.

Reconstructing either after the fact is forbidden outright: a fabricated
prediction silently poisons every later replay, which is worse than a missing
slate. The repair is an emitter on the path Ben actually uses. It makes the
*next* slate settleable and recovers none of the eighteen already played.

Three further blockers were measured on the real files, all independent of the
above, and each would have been enough on its own:

- 16 of 18 contests came from multi-contest reserved-entry templates, which
  `settlement.require_single_contest` refuses.
- 17 of 18 have no payout table on disk, and payout tiers must never be inferred
  from a contest name.
- 193028206 settled **832,342** entries, over four times the registered
  `max_entries` of 200,000, and the complete-field rule allows no partial option.

**Resolved by Q1C, 2026-09-14.** Ben ruled that the emitter was the next
settlement-plane tranche and it landed the same day: `prior_review` now freezes a
pre-lock manifest on every success path, and the four settlement gates that no
honest producer could clear were corrected with his sign-off. See `Q1C — The
pre-lock manifest emitter` below. It changes nothing for these eighteen
contests — a pre-lock prediction cannot be written after the fact — so they stay
dispositioned; it is future slates that can now accrue.

#### Design answer 1 — where `Prize` comes from

**It is derived, never observed.** A real DraftKings full standings export has no
`Prize` column at all. Measured across all 18 of Ben's exports, the header is
uniformly:

```text
Rank,EntryId,EntryName,TimeRemaining,Points,Lineup,,Player,Roster Position,%Drafted,FPTS
```

So the prize is necessarily joined from the contest's payout table. The
normalizer binds the payout bytes by SHA-256, labels the column
`provenance: DERIVED_REFERENCE_SETTLEMENT_V1` and `observed_in_export: false` in
its manifest, and derives the value with the registered reference evaluator
rather than a second tie-splitting implementation.

The consequence is stated rather than hidden: because the column is produced by
the same evaluator that `settlement._prepare_settlement` later checks it against,
**`STANDINGS_PRIZE_MISMATCH` cannot fire on a file this tool wrote.** That check
is independent evidence only for a standings file carrying an externally observed
prize, which DraftKings does not supply. It is not a working check on real data.

#### Design answer 2 — which contests the reference evaluator can settle

Scope the first corpus to the contests the evaluator settles exactly, and name
the excluded ones with a measured reason. The registered `max_entries` of 200,000
stays as it is; `max_runtime_seconds` is raised from 10.0 to 180.0 on fresh
measurement, and the builder records the budget it used.

Measured on this Windows box:

| field | budget | outcome | work units | peak traced bytes |
|---:|---:|---|---:|---:|
| 133,000 synthetic | 10.0s | refused `REFERENCE_RUNTIME_BUDGET_EXCEEDED` | — | 61,632,179 |
| 133,000 synthetic | 30.0s | exact in **27.868447s** | 177,477 | 95,515,201 |
| 200,000 synthetic | 120.0s | exact in **22.582837s** | 244,496 | 142,015,359 |
| 126,020 real (193391013) | 300.0s | exact; whole normalization 5.908s wall | — | — |

Two things in that table are worth keeping. Runtime is **not** monotonic in field
size — 200,000 settled faster than 133,000 — because it tracks tie-group and
duplication structure rather than row count, so field size alone never predicts
whether a contest will settle within budget. And the real 126,020-entry field
settled far faster than the synthetic one of similar size, so the synthetic
benchmark is a conservative bound, not a forecast.

Excluded, with its reason: **193028206** at 832,342 entries. Not approximated,
not sampled, not partially settled.

#### Design answer 3 — the 8 loose-only DAL@NYG contests

Ben's ruling, 2026-09-14: **dispositioned out with a recorded reason.** They are
marked `placeholder` naming the absent `data/runs` snapshot, the absent pre-lock
manifest and scenario bank, and the absent payout table. They stop appearing as
pending work and never look settled. No pre-lock manifest was reconstructed for
them or for any other contest.

The same ruling covers the other 10: all 18 are dispositioned, because the
pre-lock gap is not specific to the loose-only slate.

#### Two contract defects found on real bytes

Both are places where `nfl_standings_csv_v2` cannot represent a real DraftKings
contest. Neither was worked around silently: the normalizer refuses by default
and offers an explicit, default-off, fully labelled opt-in so the path can be
exercised once ruled on.

1. **Entries that never submitted a lineup.** 11 of 18 exports carry them — 220
   in 193391013, 1,314 in 193028206. They are real paid field members, tied at
   the last rank, scoring 0. The contract requires a nonempty canonical key and
   `settlement.parse_standings` refuses an empty one. Opt-in:
   `--unsubmitted-entry-policy sentinel`, which writes
   `NO_LINEUP_SUBMITTED:<entry_id>` — unique per entry, so the row forms its own
   duplication group of one, which is the true statement that it duplicates
   nothing. An *operated* entry with no lineup is always refused, whatever the
   policy: it means the portfolio never reached DraftKings.
2. **Exact tie splits that are not whole cents.** In 193391013 alone, **757
   entries across 9 tie groups**, beginning with a 23-way tie for first. The
   reference evaluator keeps money as exact rational cents by design; the
   contract requires an integer. `settlement._prepare_settlement` compares the
   evaluator's `Fraction` against the file's integer cents for *every* field row,
   so **a contest with any uneven tie split can never clear
   `STANDINGS_PRIZE_MISMATCH`, whatever the intake writes.** Opt-in:
   `--prize-rounding half-even`, which records the residual — 33 cents on that
   contest, reconciling 224,999,967 paid cents against the advertised
   $2,250,000.00.

**[BEN: both need your ruling on the contract, not on the tool.** My
recommendation is that `nfl_standings_csv_v2` gains an explicit representation
for a non-submitting field member, and that the prize comparison in
`_prepare_settlement` either carries the exact rational or compares against a
declared rounding. Neither is a change I should make unilaterally: both alter
what a column in a versioned artifact means.]

#### Points rounding, and why it is load-bearing

DraftKings exports float round-trip noise in `Points`: `85.850006` sits beside
`85.85`, and DraftKings ranks both entries 2nd. Across all **1,415,500** entry
rows in the 18 exports the largest gap between a raw value and its 2-decimal
rounding is **0.00003**, and `ROUND_HALF_EVEN` and `ROUND_HALF_UP` disagree on
**zero** rows, so no true midpoint exists and the rounding mode is immaterial.

Rounding is not cosmetic. DraftKings' own `Rank` is computed from the true
2-decimal score, so ranking the raw values splits tie groups DraftKings did not:

| contest | rank agreement, raw | rank agreement, 2dp |
|---|---:|---:|
| 195384501 | 70/71 | 71/71 |
| 195379585 | 223/237 | 237/237 |
| 195520918 | 430/475 | 475/475 |
| 195390889 | 6415/9512 | 9512/9512 |
| 195526163 | 4195/5945 | 5945/5945 |

A row that would move further than the declared float-noise tolerance is a
refusal, not a repair: past that point the assumption has stopped holding.

#### One thing that did work, independently verified

The normalizer rebuilds each field entry's lineup into the engine's own canonical
key by resolving DraftKings' slot-tagged names against the frozen salary
snapshot. Checked against contest 193391013, the reconstructed keys for Ben's two
entries match, exactly, the keys `lineups.validate_lineup` builds from the
`excl20` review export — and **differ** from the keys built from
`data/runs/20260909-showdown-ne-sea/review/assignments.csv`. The standings export
is therefore able to identify which of the repo's several assignment artifacts
actually reached DraftKings, which is precisely what `OWNED_LINEUP_MISMATCH`
exists to catch. Ben's two entries finished 17,298th and 17,328th of 126,020 for
$30.00 each on $20.00 entries, with 23 and 35 duplicate lineups in the field.

That is one contest's outcome, reported because it was measured. It is not
evidence that the engine picks good lineups, it licenses no EV or ROI claim, and
one slate is not a sample.

#### Corpus as of 2026-09-14

**0 settled.** 18 entered contests tracked across three slates — 2026-09-09
NE@SEA (1), 2026-09-10 SF@LAR (8), 2026-09-13 Week 1 main plus DAL@NYG (9). All
18 raw exports are pulled and preserved on disk; 1 is normalized to
`nfl_standings_csv_v2`; 18 are dispositioned `placeholder`. Q6's accrual
dependency remains entirely unmet.

- Acceptance met:
  - The normalizer reads all 18 real exports and normalizes 193391013's
    126,020-entry field end to end; golden, adversarial, determinism and
    raw-unchanged coverage passes.
  - The builder assembles a complete request that `settle --request` captures and
    `settle --replay` reproduces, on a synthetic complete slate. **Not on a real
    contest** — none can reach capture, for the reasons above.
  - The checklist distinguishes filed, normalized and settled, and reports raw,
    normalized and bundle presence independently of status so a disposition never
    reads as "the bytes are gone".
  - Every contest that cannot settle carries an explicit disposition and reason.

### Q1C — The pre-lock manifest emitter

Status: `DONE` on branch `codex/c3-classic-audit-review-export` at unchanged
baseline HEAD `f2890a6c587b01cede2e07bdcbb3ec1dd0ab0d33` (uncommitted
implementation). Q1C adds `src/nfl_dfs/prelock_manifest.py` and emits
`nfl_prelock_run_manifest_v1` from every `prior_review` success path, so a slate
built on the path Ben actually uses can now be settled. It adds no model, no
economics and no release truth; `MODEL_STATUS=PRIOR_ONLY` and
`RELEASE_DECISION=DO_NOT_UPLOAD` are unchanged, and a manifest is emitted for a
`DO_NOT_UPLOAD` run precisely because those are the review lineups Ben enters by
hand.

- Goal: close the gap Q1B measured — no `data/runs/` snapshot held a pre-lock
  manifest, so no contest could ever reach `settle --request`.
- Scope: a deterministic emitter bound to the hashes a run already computed; the
  nine-slot Classic assignment record settlement reads; and the four contract
  corrections below, each ruled on by Ben before it was made.
- Non-goals: no backfill of the eighteen contests already played, no scenario
  simulation, no contest economics on the prior-review path, and no change to any
  evidence gate.

**It recovers nothing already played.** A pre-lock manifest records what was
predicted *before* lock; writing one afterwards would be a fabricated prediction,
which is worse than a missing slate because it silently poisons every later
replay. The eighteen contests dispositioned under Q1B stay dispositioned.

#### Four contract corrections, each on Ben's ruling of 2026-09-14

Every one of these was a gate no honest producer could clear. They were measured
against Q1's own passing fixture by removing, one at a time, exactly what a
prior-only run does not have.

1. **`field_size` is no longer compared.** This was the serious one, and it was
   never `prior_review`-specific. `_validate_prelock_manifest` required the
   manifest's `contest_parameters.field_size` to equal the request's, and
   `_prepare_settlement` separately required that to equal the settled standings
   row count — so the pre-lock manifest had to record the *settled* field size,
   which no producer can know before lock. The legacy `build` path records the
   operator's `--field-size` assumption and would have failed identically the
   first time a contest did not fill: 193391013 was advertised at 133,000 and
   settled 126,020. Q1's fixture only ever passed because its synthetic contest
   has `field_size` 2 and the operator owns both entries. The manifest now
   records the assumption a portfolio was built against, labelled
   `field_size_basis`, and the run brief reports `assumed_field_size` beside
   `settled_field_size` as a Q6 diagnostic. Contest id, draft group, mode and
   entry fee remain hard identity checks, unchanged.
2. **The payout hash and version are optional in the manifest.** A prior-only run
   never reads a payout table — `CLAUDE.md` keeps contest economics off that path
   deliberately — so it has none to record. A `build` manifest that records them
   is still checked exactly as before. Nothing is unbound: the request binds the
   payout bytes by SHA-256 either way; only the manifest's second copy of that
   binding may be absent.
3. **`objective`, `advertised_prize_value` and `ticket_face_value` are compared
   when present.** Same reasoning: stable facts, but an operator supplies them
   and a prior-only run never sees them.
4. **A request may bind zero scenario banks if and only if `MODEL_STATUS` is
   `PRIOR_ONLY`.** `prior_review` runs no simulation, so it has no bank of any
   purpose to emit, and `inspect_scenario_bank` only accepts DESIGN, SELECT or
   REFEREE. The alternative — a degenerate one-scenario bank holding the point
   estimates — was rejected because a bank with no distribution invites being
   read as one. `SettlementCaptureRequest` enforces the condition, so the
   relaxation cannot reach a prospectively-validated model, where the banks do
   real work.

#### What the emitter records, and what it refuses to

Only what the run genuinely observed: the exact salary and reserved-entry bytes
it read, the frozen projections that *are* the prediction (`team_projections`,
`player_opportunities`, `source_ledger`), the assignment it selected, contest
identity read straight out of those CSVs, and the four release truths unchanged.
Every hash is one the run already computed while doing the work, never recomputed
from a path, because a path can be swapped between the run and the emitter and a
recomputed hash would silently bless the swap.

Absence is declared rather than left to be inferred from a missing key:
`scenario_artifacts: {}`, `field_size: null` with its basis, and a
`model_status_limitations` block naming all three gaps. It refuses a naive clock,
a manifest with no prediction or no selected entry, a prediction named after a
reserved artifact role, duplicate prediction names, and incomplete release
truths. It also stops if a JSON prediction declares a schema version other than
the one the emitter expects, which turns a confusing capture-time refusal days
later into an obvious one at the run. It never fails a run: a slate it cannot describe truthfully produces a
named `SKIPPED` stage and no file, because a run that produced a portfolio is
still a good run even when its manifest cannot be written. The clearest such case
is a multi-contest reserved-entry template, which `settlement` refuses anyway and
which covers 16 of Ben's 18 entered contests.

#### Classic now writes the assignment settlement reads

Classic previously left its selection only as `classic_assignment.json`, which
`lineups.read_assignment_csv` cannot read, so a Classic run could not bind an
assignment into a manifest at all. `write_assignments_csv` gained a `mode`
parameter and Classic writes the nine-slot `nfl_assignment_csv_v1` record that
`certify` and `settle` already accept.

Two existing Classic assertions changed as a result, and the reasoning is worth
keeping. `assignments.csv` is **not** an upload shape: it carries no Contest ID,
Contest Name, Entry Fee or instructions block, so DraftKings would reject it, and
Showdown's prior review has always written the same file. The `DK_UPLOAD_*` and
`DK_REVIEW_ENTRY_*` prohibitions are unchanged and still checked. The C2
prohibited-path guard that banned `write_assignments_csv` outright became a spy
asserting the writer is called with `mode=CLASSIC` — a strictly stronger check,
because it also proves the geometry is right rather than only that nothing
happened.

#### Verified composition

On a realistic `cowork-run` tree the Q1B request builder now resolves
`prelock_manifest`, `predictions`, `assignments`, `scenarios`, `release_truths`,
`salary`, `entries`, `entry_fee`, `draft_group`, `mode`, `scoring`,
`metric_registry` and `owned_entry_ids`, leaving exactly two blockers:
`PAYOUT_TABLE_ABSENT` and `NORMALIZED_STANDINGS_ABSENT`. Both are facts only Ben
can supply at settlement time — the payout table and the standings pull — and
both are correct refusals rather than gaps.

- Acceptance met:
  - A real Classic `prior_review` run freezes a manifest bound to the hashes the
    run computed, and a replayed run at a pinned `as_of` freezes byte-identical
    bytes.
  - That manifest captures through `settle --request` and reproduces through
    `settle --replay`, with no scenario bank, no payout hash in the manifest, and
    a field size the run never claimed to know.
  - The manifest's release truths equal the run's own, so the capture cannot
    report a better decision than the slate shipped with.
  - The Classic assignment CSV reads back through `read_assignment_csv` and
    matches the canonical selection report roster for roster.
  - The Showdown exit freezes a manifest too, asserted separately: emitting from
    only one of the three success paths would leave the other two unsettleable,
    which is the exact failure Q1B found.
  - A prediction whose declared schema version drifts from the emitter's
    expectation produces a named `SKIPPED` stage at the run rather than a
    confusing capture-time refusal days later.
  - Complete pinned suite `735 passed, 1 failed, 1 skipped in 198.190s` (737
    collected); doctor, compile/import and `git diff --check` pass. The single
    failure is the pre-existing `test_w6_live_preflight` time bomb described in
    the close-out note under `Next action`.

#### What is still required before a slate accrues

Q1C makes the next slate settleable; it does not settle one. For a real contest
Ben still needs to supply the contest's payout table and pull its standings
export, and the contest must have come from a single-contest reserved-entry
template. The corpus still holds **zero settled contests**, and it will until a
slate is run, entered, and settled end to end.

### C1 — Classic intake, projection, and one-command prior review

Status: `DONE` on `codex/c1-classic-intake-prior-review` at unchanged baseline
HEAD `9d25ad75f6fd08a22b700e3062b7304158e5c0c8` (uncommitted implementation).
Final verification collected 555 tests: `554 passed, 1 skipped`; doctor,
compile/import, whitespace, deterministic replay, mutation, prohibited-path,
and runtime/memory checks passed. C1 emits canonical review JSON only and does
not unlock any upload claim.

- Goal: make the normal two-CSV Cowork surface work for NFL Classic across all
  games on the slate without routing through the known-defective economics
  path.
- Scope:
  - Detect Classic from schema and validate exact DraftKings roster geometry,
    salary cap, game set, per-player locks, teams, Entry IDs, blank-cell
    authority, and contest compatibility.
  - Build/reuse one immutable multi-game prior package from approved frozen
    sources with exact provider-to-current-DK identity and source expiry.
  - Extend participation, official-status, team/position coverage, transfers,
    rookies/missing history, weather, and material-role findings across the
    entire slate. Missing selected-player evidence stays fail-closed.
  - Add a one-command Classic prior-review path that produces projection and
    selection inputs without calling field, duplication, or payout economics.
- Non-goals: no calibrated ownership, ceiling, field, duplication, payout or
  EV objective; no portfolio policy or export redesign in this chunk.
- Acceptance:
  - Supplied Classic fixtures and a synthetic multi-game fixture pass exact
    identity, geometry, lock, evidence, APPG-quarantine, and deterministic
    replay tests.
  - Wrong mode, mixed draft groups, mismatched entries, unknown games,
    duplicate identities, stale sources, and selected unavailable players stop
    before assignments.
  - The result reports all four release truths and remains
    `PRIOR_ONLY / DO_NOT_UPLOAD`.

### C2 — Classic policy, candidates, and joint portfolio selection

Status: `DONE` on `codex/c2-classic-policy-candidates-portfolio` at unchanged
baseline HEAD `90361980959916333cbd4b820680166a7e4fe6a2` (uncommitted
implementation). The final focused regression passed `203 passed, 1 skipped`
in 214.21s and the complete pinned suite passed `581 passed, 1 skipped` in
312.25s. Doctor, compile/import, whitespace, deterministic replay, mutation,
prohibited-path, adversarial diff, and synthetic 1/3/20/150-entry runtime/memory
checks passed. The bounded banks remain prior-only and make no full-slate
optimality or upload claim.

- Goal: select an explicit, bounded Classic portfolio rather than cycle a list
  of individually strong lineups.
- Scope:
  - Define a versioned Classic policy bound to exact salary, game, person,
    roster-slot, and Entry-ID identities.
  - Support explicit player/team/game exposure bounds, group constraints,
    canonical uniqueness, pairwise overlap, and registered stack rules. Treat
    construction preferences as advisory unless the policy makes them hard.
  - Generate multiple deterministic candidate strata/families appropriate to
    Classic and report bank completeness, coverage, time, nodes, gap, and
    memory. Never call a bounded-bank result full-slate optimality.
  - Jointly assign exactly one unique lineup to every requested Entry ID and
    independently reparse/audit all effective integer limits.
- Non-goals: no ownership leverage or payout-aware objective until Q2-Q5; no
  automatic relaxation of a requested limit.
- Acceptance:
  - Feasible 1-, 3-, 20-, and 150-entry policy fixtures meet every declared bound;
    infeasible, time-limited, incomplete-bank, and solver-error states remain
    distinct and fail closed where required.
  - Repeated runs select byte-identical assignments under the same registered
    limits and seed.

### C3 — Classic audit, review, export, and scale acceptance

Status: `BLOCKED` on branch `codex/c3-classic-audit-review-export` at unchanged
baseline HEAD `f2890a6c587b01cede2e07bdcbb3ec1dd0ab0d33`. The downstream
audit, exact-template review export, readable JSON/HTML/eight-sheet workbook,
copied-package replay, mutation matrix, and full supplied-fixture 1/3/20/150
scale matrix pass. Independent artifact-tool rendering covered all eight sheets
and the HTML rendered to a readable nine-page PDF. Native Excel refused the
required open/recalculate/save/reopen operation on this host; C3 cannot be
marked `DONE`, no C4 prompt is prepared, and no later item is `READY` until that
single acceptance step passes.

- Goal: deliver a human-verifiable Classic portfolio package with the same
  exact-artifact discipline as SD5.
- Scope:
  - Independently reparse/hash salary, entries, assignments, normalized policy,
    policy audit, selection report, and review export.
  - Recompute every roster slot, salary, game/team stack, exposure, uniqueness,
    overlap, selected-player evidence fact, and unchanged template byte.
  - Extend readable JSON/HTML/workbook views for Classic and render-inspect all
    sheets/pages. Preserve formula-injection defenses.
  - Benchmark 1, 3, 20, and 150 entries on the full supplied 24-team/719-person
    fixture with registered time/RSS budgets and deterministic copied-package
    replay.
- Non-goals: no EV claim, no release-gate waiver, and no inference that a
  successful 20-entry run proves 150-entry capacity.
- Acceptance:
  - Only an independently audited assignment may create a new
    `DK_REVIEW_ENTRY`; any mutation or semantic disagreement withholds it.
  - Exact Entry-ID order, blank-cell authority, physical-line geometry, output
    hash, policy facts, and readable display all reconcile.
  - Each scale has an explicit `PASS`, `FEASIBLE_LIMIT`,
    `CANDIDATE_BANK_INCOMPLETE`, or named failure with measured timing/memory.

### C4 — Current real-slate Classic rehearsal

- Goal: prove the intended Cowork/Linux workflow on the actual contest files
  and current evidence before relying on it operationally.
- Scope: immutable two-file intake, current source capture, exact identities,
  all game/lock/evidence checks, requested policy, build, selection, independent
  audit, readable review, copied replay, status-change and mutation faults,
  complete pinned tests, and one operator handoff.
- External prerequisites: matching current Classic salary and reserved-entry
  CSVs; requested contest/portfolio facts; current official activity and any
  required role/weather evidence.
- Acceptance: the exact run records input/output hashes, all four truths,
  candidate-bank scope, solver proof, rendered review, repeated-byte results,
  blockers, and one next action. Until Q6/Q7 promotion, successful lineups are
  still prior-only review artifacts and not calibrated upload packages.

### C5 — Classic slot ordering and governed late swap

- Goal: complete the mechanical Classic lifecycle without claiming a
  conditional-EV reoptimizer.
- Scope: prefer later-lock players in flexible slots when legality and the
  selected lineup are unchanged; bind the prior certified assignment and exact
  contest eligibility; preserve locked/unauthorized cells; revalidate remaining
  players and independently audit every changed byte.
- Non-goals: no current-score/ownership-aware conditional portfolio objective;
  that waits for QC1.
- Acceptance: multi-wave lock fixtures prove that only eligible unlocked cells
  change, all locked cells remain byte-identical, and stale/conflicted evidence
  or an ineligible contest writes no late-swap output.

### Q2 — Calibrated opportunity, outcome, participation, and dependence

- Goal: replace one central expected stat line with calibrated joint player and
  team outcome distributions suitable for downstream contest evaluation.
- Scope: finish the unified simulator availability mask; model volume separately
  from efficiency; represent uncertainty for roles, injuries, rookies and
  transfers; reconcile all team events and DraftKings scoring; estimate and
  stress within-team, opponent, game-script, kicker and DST dependence using
  rolling-origin training data.
- Acceptance: held-out coverage, calibration, scoring/event conservation,
  sensitivity, dependence, and tail tests beat registered priors without
  leaking future, SELECT, or REFEREE information. Until then outputs remain
  challenger/diagnostic only.

### Q3 — Contest-conditioned ownership, field, and duplication

- Goal: model who the contest field selects and how often exact lineups are
  duplicated, separately for contest type, size, entry limit, slate geometry,
  and Classic/Showdown roles.
- Scope: calibrate player/role ownership distributions; generate only legal
  correlated field lineups; preserve underlying-person and role identity; model
  exact-lineup multiplicity and uncertainty; back off hierarchically when data
  are sparse.
- Acceptance: slate-grouped holdout calibration, count conservation, legal-field
  audits, exact-duplicate accuracy, tail diagnostics, and prior-vs-challenger
  comparisons pass registered thresholds. Ownership sums or marginal fit alone
  cannot promote the field model.

### Q4 — Production payout and tie economics

- Goal: price each candidate against full-size simulated fields using exact
  payout/tie/duplicate rules within measured runtime and memory limits.
- Scope: promote only an estimator that passes Q1 truth thresholds; jointly
  model strict-above and tied counts; include every selected entry in the same
  contest settlement; retain disjoint SELECT and REFEREE evaluation.
- Acceptance: held-out Q1 truth cases, production-scale field sizes, top-heavy
  and flat/ticket structures, and duplicate-heavy stress cases meet registered
  accuracy/RSS/time thresholds. A degraded profile must be explicit and cannot
  silently change the objective.

### Q5 — Candidate coverage and joint portfolio utility

- Goal: optimize a portfolio on contest payout outcomes and explicit risk—not
  on isolated central projections.
- Scope: generate scenario-optimal, leverage/ownership-tilted, construction,
  and tail-regime candidate families; evaluate them only on disjoint SELECT
  scenarios; choose entries jointly on shared outcome/field scenarios; register
  the contest-specific utility and risk measure, including drawdown/concentration
  limits and Monte Carlo uncertainty.
- Acceptance: known-optimum synthetic contests, scenario-count stability,
  candidate-family ablations, correlation stress, exposure constraints, and
  independent REFEREE recomputation pass. `OPTIMAL` is always scoped to the
  actual bank and solver evidence.

### Q6 — Prospective validation, registry, promotion, and rollback

- Goal: make `PROSPECTIVELY_VALIDATED` an evidence-derived state rather than a
  manual label.
- Scope: immutable prediction snapshots and settlements; slate-grouped
  rolling-origin splits; untouched temporal holdout; champion/challenger
  comparisons; sample/effective-sample minimums; influence caps; uncertainty;
  model registry, rollback pointer, and automatic demotion on drift.
- Acceptance: the complete Q2-Q5 bundle beats registered priors on every hard
  metric without degrading calibration, tail, dependence, or operational gates.
  Fewer observations than the registered minimum remain `PRIOR_ONLY` or
  `UNVALIDATED`; ROI alone never promotes.

### Q7 — Registered-scale shadow and game-week acceptance

- Goal: prove the promoted quantitative bundle is reproducible, fast enough,
  fault-tolerant, and operationally understandable before release use.
- Scope: 1/3/20/150-entry Classic and Showdown benchmarks on Windows and actual
  Cowork/Linux; full game-week dry run; source expiry/status-change drills;
  cancellation/deadline/incumbent behavior; copied replay; readable review;
  settlement and rollback; exact runtime/RSS/operator-touch recording.
- Acceptance: every registered deadline, memory, accuracy, reproducibility,
  evidence, audit, and rollback condition passes prospectively. Structural or
  synthetic success alone cannot clear the release gate.

### QC1 — Promoted objective integration across modes

- Goal: make one governed quantitative plane serve both Classic and Showdown,
  including late swap, while roster contracts retain mode-specific geometry.
- Scope: route the currently promoted Q2-Q7 bundle through the C1-C5 and SD
  workflows; preserve exact identities, locks, contest boundaries, scenario-bank
  separation, independent audit, and manual DraftKings actions.
- Acceptance: mode-specific real-slate shadow runs reproduce registered metrics
  and all final-byte/evidence gates. Only then may model-assisted output become
  eligible for `PROSPECTIVELY_VALIDATED`; profitability is never guaranteed.

## Baseline

- Repository: `C:\Users\benja\Documents\Claude\nfl-dfs`
- Original tracker branch/HEAD: `main` at `e042c7bfc546`.
- Verified merged baseline 2026-09-04: PR #2 merged S3 into `main` at
  `500f73c5a098f2c6b6dfafae4b7052b8e7e3b5a3`; local `main` and `origin/main`
  matched before the S6A implementation branch was created.
- Current checkout on 2026-09-10: deleted-upstream branch
  `codex/sd5-readable-artifact-bound-review` at `a9aa423`; its committed tree is
  merged on `origin/main` at `dbafe58`, but the working tree also contains the
  uncommitted 2026-09-10 rerun, TLS, transfer-prior, pool-coverage, and
  policy-stratification layer plus pre-existing user/generated paths.
- Current-tree verification: 516 passed and 1 existing Windows
  symlink-permission skip from a unique workspace-local temp root; doctor passed
  on Python 3.13.7 with SQLite integrity `ok`/WAL and no Excel lock. The default
  Windows test launcher encountered a pre-existing inaccessible fixed temp root;
  that operational issue does not invalidate the isolated green suite and must
  be recorded in DEV0.
- Still unverified: reproducibility from a committed current baseline,
  registered-scale Classic portfolio execution, live calibration, and any
  model-assisted certified upload.
- Current truthful capability: validated intake, legality, evidence gating, and byte-exact export infrastructure; not a validated EV engine.

## Release truth model

New work should converge on four explicit and independently reported truths:

1. `FILE_VALID`: current authorized template, legal exact-ID roster, byte-exact write, and independent byte audit.
2. `EVIDENCE_STATE`: `PASS`, `UNKNOWN`, `STALE`, or `CONFLICTED`, with named hard blockers.
3. `MODEL_STATUS`: `UNVALIDATED`, `PRIOR_ONLY`, or `PROSPECTIVELY_VALIDATED`.
4. `RELEASE_DECISION`: `CERTIFIED_UPLOAD_PACKAGE` or `DO_NOT_UPLOAD`.

`FILE_VALID` alone never implies `CERTIFIED_UPLOAD_PACKAGE`. No automatic grade-C or grade-D fallback is authorized. A future emergency fallback requires a separately approved, deterministic, tested policy and must never be presented as EV-certified.

## Deadline delivery punch list — September 2026

Operational targets:

- Generate a deterministic, structurally legal, source-bound Showdown lineup
  for human review by Wednesday, 2026-09-09.
- Generate deterministic, structurally legal, source-bound Classic lineups for
  human review by Sunday, 2026-09-13.
- `Generate` does not mean prospectively validated, profitable, EV-certified,
  or automatically uploadable. Until the evidence and model gates genuinely
  pass, the truthful release decision remains `DO_NOT_UPLOAD`; DraftKings
  review, entry, and upload remain manual.

This deadline sequence temporarily puts the minimum S6 projection slice ahead
of S4A through S5 after S3 is complete. It does not waive those quantitative
repairs or mark their economics as valid.

| ID | Target | Status | Required outcome |
|---|---|---|---|
| DL1 | S3 truth states, target 2026-09-05 | `DONE` | Report `FILE_VALID`, `EVIDENCE_STATE`, `MODEL_STATUS`, and `RELEASE_DECISION` independently; keep hard gates binding; make style and bank-coverage preferences advisory. |
| DL2 | Minimum S6A projection producer, target 2026-09-07 | `DONE` | Deterministically transform frozen approved source artifacts into both model-input CSVs and a validated source ledger with no freehand numerical inputs or APPG use. |
| DL3 | Prior-only review lineup profile, target 2026-09-07 | `DONE` (landed 2026-09-08 as `cowork-run --profile prior_review`) | Generate legal projection-led review assignments without using or relabeling the known-unvalidated field, duplication, or payout economics. It must remain `MODEL_STATUS=PRIOR_ONLY` and `DO_NOT_UPLOAD`; this does not complete S5. |
| DL4 | Showdown exact-template acceptance, target 2026-09-08 | `BLOCKED` on operator contest facts only; mechanics rehearsed 2026-09-08 | Rehearse with a matching Showdown salary CSV, reserved-entry CSV, contest/payout facts, and current evidence; verify exact CPT/FLEX IDs, one Captain multiplier, underlying-person uniqueness, assignments, workbook, blockers, and final bytes. |
| DL5 | Showdown operational run, target 2026-09-09 | `BLOCKED` on DL4. Retargeted: 2026-09-09 is the manual-guardrail rehearsal in `docs/OPENER_RUNBOOK_2026-09-09.md`, not a model-generated upload | Refresh approved inputs and evidence, generate the review lineup, and make no feature changes beyond demonstrated blocker repairs. |
| DL6 | Classic projection/selection extension, target 2026-09-11 | `DEFERRED` to C1-C2; not complete | Use the same source-bound projection contract across the multi-game Classic pool and produce exact-ID legal review assignments. |
| DL7 | Classic full rehearsal, target 2026-09-12 | `DEFERRED` to C3-C4; not complete | Execute the complete intended operator path, record wall time and blockers, and preserve every exact input/output hash. |
| DL8 | Classic operational run, target 2026-09-13 | `DEFERRED` to C4-C5 and QC1; not complete | Refresh current official evidence, generate and review the lineups, and retain manual DraftKings upload as the final boundary. |

Operator-supplied deadline prerequisites:

- Matching Showdown salary and reserved-entry CSVs no later than 2026-09-07.
- Showdown payout table, advertised value, field size, entry fee, and contest ID
  no later than 2026-09-08. Without the matching entry template, DL5 can
  produce only a review lineup for manual transcription, not an exact-template
  export.
- Matching Classic salary and reserved-entry CSVs no later than 2026-09-10,
  followed by its contest facts and current official activity evidence.
- An actual Cowork/Linux rehearsal before DL4, or an explicit decision to use
  the verified Windows launcher as the deadline fallback.

The dated deadline rows are retained as historical targets. Current development
now follows DEV0, Q1, C1-C5, Q2-Q7, and QC1 above. The older S4A/S4B, S5,
S7-S10 and W-tranche findings are mapped into those chunks and remain open
unless the new table explicitly says otherwise.

## Session backlog

### S0 — Preserve and establish the implementation baseline

- Priority: P0
- Status: `DONE`
- Completion: the reviewed remediation/safety checkpoint is pushed on `main`;
  a clean temporary clone reproduced all supplied fixture hashes and the full
  87-passed, 1-skipped checkpoint suite without generated artifacts.
- Scope:
  - Preserve the current dirty working tree and byte-sensitive fixtures.
  - Review `.gitattributes` and the supplied-fixture manifest.
  - When authorized, stage only explicit paths and verify the exact staged set, fixture bytes, full tests, doctor, and staged whitespace.
  - Never use broad staging.
- Acceptance:
  - Fresh-clone or clean-worktree verification reproduces fixture hashes and the full test result.
  - No generated runs, workbooks, credentials, caches, or upload files are committed.

### S1 — Bounded safety and evidence foundation

- Priority: P0
- Status: `DONE`
- Findings: D-04, D-13, D-14, D-24, D-25.
- Goal: repair bounded correctness and security defects without changing lineup selection or quantitative behavior.
- Scope:
  - Make ticket/satellite payout parsing accept a validated ticket face value through every parser and CLI caller.
  - Guarantee a compact machine-readable failure result after intake, plus an internal diagnostic artifact when possible; do not swallow user interrupts.
  - Make the writer and independent referee operate on byte lines rather than `str.splitlines` semantics.
  - Replace hash-only source-ledger acceptance with a strict versioned schema that validates approved source URIs, timestamps, license decisions, artifact hashes, parser versions, and derived-output hashes.
  - Restrict request paths to explicitly supplied attachment, managed data, and per-run roots. Reject traversal, external absolute paths, and symlink/reparse escapes before snapshotting.
- Required tests:
  - Ticket CSV parses with a face value and fails without one.
  - Arbitrary JSON, unknown ledger fields, missing artifacts, mismatched hashes, and mismatched derived hashes fail closed.
  - Valid ledger evidence binds both model-input hashes.
  - External and escaping request paths are rejected before any copy; valid relative paths still work.
  - Unicode non-CSV line separators inside quoted content cannot change source row geometry.
  - Representative build/certification failures still write a truthful `DO_NOT_UPLOAD` result and no upload-shaped CSV.
  - Full Windows suite, doctor, and `git diff --check` pass.
- Non-goals:
  - No field-model, candidate, projection, portfolio-objective, late-swap, or release-label redesign.
  - No staging, commit, remote, or push.

### S2 — Governed late-swap writer and lock evidence

- Priority: P0
- Status: `DONE`
- Depends on: S1.
- Findings: D-05 and the hard-evidence portion of D-08.
- Scope:
  - Derive replaceable cells from exact player/game lock times, never caller assertion.
  - Bind the prior certified assignment and entry-template hashes.
  - Require locked cells to remain byte-identical and reject locked-player additions or removals.
  - Support DraftKings bulk-edit output only for contests verified as late-swap eligible.
  - Represent official team inactive reports as team-scoped negative lists with lock-relative freshness.
  - Keep `NOT_YET_DUE` provisional; it must not silently clear the final release gate.
- Acceptance:
  - End-to-end late-swap fixture writes a valid changed-entry CSV, preserves locked cells, and passes an independent byte audit.
  - Tampered prior assignments, stale templates, non-late-swap contests, and locked-player changes fail closed.
- Completion: the shared CLI now binds prior state, derives cell authority from
  exact lock times, requires contest eligibility and team negative-list
  evidence, preserves unauthorized bytes, and writes only after independent
  audit, reparse, hash, and final-release gates pass. Windows verification:
  123 passed, 1 skipped; Linux/Cowork execution remains unverified because only
  the Docker Desktop internal WSL distribution is installed.

### S3 — Certification truth states and QA policy

- Priority: P0
- Status: `DONE`
- Depends on: S1 and S2.
- Findings: D-06 and D-09; modifies the proposed `UPLOAD_SAFE / MODEL_GRADE` doctrine.
- Scope:
  - Introduce the four release truths defined above without weakening existing hard gates.
  - Move truly mandatory construction rules into solver constraints.
  - Make construction preferences and candidate-family coverage advisory.
  - Separate pool-wide model uncertainty from selected-player evidence while retaining named model-certification blockers.
  - Preserve `DO_NOT_UPLOAD` for incomplete hard evidence or an unvalidated model package.
- Acceptance:
  - Every output reports all four truths and named blockers.
  - Legal bytes with incomplete evidence report `FILE_VALID` but still end `DO_NOT_UPLOAD`.
  - QA style preferences cannot delete an otherwise valid diagnostic file or masquerade as safety failures.
- Completion: one centralized, truth-table-tested release policy now derives
  the compatibility status and release decision for certification and governed
  late swap. Decision JSON, manifests, Cowork reports, and review workbooks
  report all four truths. Proposed bytes are independently audited, reparsed,
  and hashed in memory before release; blocked packages persist no upload CSV.
  Selected-player opportunity evidence remains hard, unselected pool
  uncertainty is counted as a model limitation, and unvalidated/prior-only
  model-assisted packages cannot certify. Construction preferences and
  candidate-family coverage are advisory; solver, accounting, REFEREE,
  evidence, authorization, and byte failures remain blocking. Windows
  verification: 144 passed, 1 skipped; doctor, compileall, and diff check pass.

### S4A — Tail-economics reference model and truth tests

- Priority: P0
- Status: `BLOCKED`
- Depends on: S3.
- Findings: D-01 and D-17.
- Scope:
  - Build a slow, auditable reference settlement for small exact fields and controlled synthetic large fields.
  - Define joint probabilities/counts for opponents strictly above and tied, including payout chops.
  - Evaluate tail-stratified or importance-sampling estimators; do not assume a Gaussian extreme tail without empirical acceptance.
  - Do not replace production economics in this session.
- Acceptance:
  - Exchangeable-field, known-duplicate, exact-tie, flat-payout, top-heavy, satellite, and boundary-rank golden tests.
  - Written error analysis across field size and sample size with explicit promotion thresholds.

### S4B — Production field economics

- Priority: P0
- Status: `BLOCKED`
- Depends on: S4A acceptance.
- Findings: D-01, D-15, D-17, D-23.
- Scope:
  - Replace cloned multiplicities with the accepted tail estimator.
  - Price strict-above and tied outcomes jointly; do not divide by a standalone expected-duplicates scalar as a substitute for tie settlement.
  - Enforce process-RSS memory budgets before allocation and use an explicit degraded profile or fail closed.
  - Keep ownership and duplication coefficients as versioned, hash-bound priors until prospective validation promotes challengers.
- Acceptance:
  - Meets S4A accuracy thresholds on held-out truth cases.
  - Memory and runtime budgets are measured on target hardware and recorded, not inferred.
  - REFEREE independently recomputes the same registered objective on a disjoint bank.

### S5 — Candidate generation and portfolio selection

- Priority: P1
- Status: `BLOCKED`
- Depends on: S4B.
- Findings: D-02, D-03, and remaining D-06 work.
- Scope:
  - Add multiple independent candidate families, including scenario-optimal and ownership-tilted families.
  - Evaluate candidates only on disjoint SELECT scenarios.
  - Replace the scenario-count-dependent LCB objective.
  - Evaluate portfolio outcomes jointly on shared field/outcome scenarios; do not assume own-lineup elite events are independent.
  - Keep risk preferences explicit, scenario-count-independent, and contest-specific.
- Acceptance:
  - Selection is stable within registered Monte Carlo error when scenario counts change.
  - Synthetic contests with known optimal portfolios select the expected result.
  - Candidate-family reporting is informative but non-blocking unless a registered solver constraint is violated.

### S6 — Deterministic projection producer

- Priority: P1
- Status: `BLOCKED`
- Depends on: S1 and stable input contracts from S3.
- Findings: D-07 and remaining D-24 work.
- Scope:
  - Produce team and player-opportunity contracts from frozen, approved source artifacts using local deterministic code.
  - Keep external-source fetch, parsing, license decisions, transformations, and output hashes explicit in the ledger.
  - Use stable provider identities; normalized or fuzzy crosswalk matches are proposal-only until human-reviewed and frozen.
  - Runtime never fits coefficients and the LLM never supplies numeric values.
- Acceptance:
  - End-to-end fixture build creates both model inputs and a valid ledger with zero freehand numeric input.
  - Missing, ambiguous, stale, conflicted, or hash-mismatched identity/source evidence fails closed.
  - `AvgPointsPerGame` remains absent from all numerical transformations.
- Minimum S6A/DL2 completion: `nfl.ps1 project` and `nfl.sh project` now accept
  four explicit hash-pinned frozen artifacts; validate approved provenance,
  timestamps, coverage, bounds, and exact provider-to-current-DK identity;
  conserve documented position-eligible team weights; and atomically publish
  loader-valid team/player CSVs plus a reconciled `nfl_source_ledger_v1` file.
  Classic fixture coverage is 24 teams/719 people, Showdown uses 63 distinct
  FLEX IDs, repeat runs are byte-identical, APPG mutation leaves both derived
  CSVs unchanged, and failures publish no partial package. Verification: 39
  focused tests passed; 112 integration tests passed with 1 existing skip; full
  Windows suite 171 passed with 1 existing skip; doctor and compileall passed.
- Broader S6 remains `BLOCKED`: the full Section 4.4 historical ingestion,
  offline fitting/holdout reports, live-source refresh, and prospective model
  validation are not part of S6A and remain unimplemented/unverified.

### S7 — Simulator, ownership, duplication, and calibration

- Priority: P1
- Status: `BLOCKED`
- Depends on: S4B, S5, and S6.
- Findings: D-10, D-16, D-18, D-22, D-23.
- Scope:
  - Correct or remove DESIGN importance sampling.
  - Vectorize count allocation and points-allowed scoring with deterministic regression coverage.
  - Replace tautological accounting diagnostics with checks on simulated allocations.
  - Fit ownership, duplication, and correlation challengers offline with rolling-origin validation.
  - Do not promote after an arbitrary three-contest threshold; require documented sample size, calibration, stability, and holdout improvement.
- Acceptance:
  - Prospective acceptance report beats registered priors on predeclared metrics without degrading tail/dependency gates.
  - DESIGN, SELECT, and REFEREE remain disjoint and hash-bound.

### S8 — State, retention, brief, and workbook boundary

- Priority: P2
- Status: `BLOCKED`
- Depends on: S3.
- Findings: D-19 and D-20.
- Scope:
  - Add content-addressed stage caching and per-slate state without discarding immutable run evidence.
  - Persist scenario evidence for certified and settled runs; allow diagnostic retention to follow a declared policy.
  - Make `brief.json` the canonical agent contract.
  - Retain the review workbook and Windows fallback as secondary human surfaces; fix timezone round-tripping.
- Acceptance:
  - Identical inputs reuse unchanged stages.
  - Certified assignments, prior hashes, branches, briefs, and retained evidence are reproducible and independently auditable.
  - JSON and workbook agree on status, blockers, paths, and hashes.

### S9 — Runtime compatibility and code reduction

- Priority: P2
- Status: `BLOCKED`
- Depends on: S1 and S8.
- Findings: D-12 and D-21.
- Scope:
  - Define a tested Python compatibility policy, record the exact interpreter in manifests, and separate diagnostic compatibility from certification requirements.
  - Remove only proven dead code after migration review; move fitting and validation harnesses under `research/` where appropriate.
  - Declare direct dependencies explicitly and remove unused declarations only after full verification.
- Acceptance:
  - Windows and Linux/Cowork acceptance matrix passes on every supported interpreter.
  - Fresh-environment setup is locked, reproducible, and does not weaken evidence gates.

### S10 — Simulated game-week acceptance and operations

- Priority: P2
- Status: `BLOCKED`
- Depends on: S2 through S9.
- Scope:
  - Execute a complete synthetic or historical game week: intake, projection, early build, final evidence, certification decision, scratch drill, late swap, settlement, and calibration intake.
  - Add scheduled automation only after the dry run passes and only for local computation and approved public-source collection.
  - Keep DraftKings account actions manual.
- Acceptance:
  - Exact artifacts, wall-clock timings, process RSS, blockers, hashes, and operator touches are recorded.
  - No live-slate or upload-readiness claim is made from synthetic evidence.

## Post-review work tranches — 2026-09-08

Source: `docs/PRODUCTION_READINESS_REVIEW_2026-09-08.md` (findings R01-R15) and
`docs/SHOWDOWN_FIRST_PRODUCTION_PLAN.md` (sequencing). The R-* list supersedes the
D-* list in `DFS_SYSTEM_GREENFIELD_SPEC.md` as the current defect inventory. These
`W*` tranches are Cowork-session-sized chunks; each names its own findings, and
each has a paste-ready prompt under `docs/session-prompts/`.

### Completed and not to be re-litigated

`S0`, `S1`, `S2`, `S3`/`DL1`, `S6A`/`DL2`, `W1`/`R01`, and core Classic/Showdown
legality are `DONE` with passing regression coverage (203 passed, 1 Windows
junction skip, 204 collected, run by a Cowork session on the pinned 3.13.7
runtime). Repaired findings from the 2026-08-31 and 2026-09-01 documents are not
carried forward. What remains open is exactly R02-R15.

### Verified runtime constraints for every session below

Measured 2026-09-08 from a Cowork session with the repo folder mounted, and
revised during `W1` where the earlier measurement was wrong:

- **A session can now execute the test suite.** `sh ./nfl.sh test -q
  -p no:cacheprovider --ignore=.pytest_cache tests` runs on the pinned Python
  3.13.7 runtime once `NFL_DFS_VENV_DIR`, `NFL_DFS_UV_CACHE_DIR` and
  `NFL_DFS_UV_PYTHON_DIR` point off the mounted folder. Ben no longer has to run
  `.\nfl.ps1 test` and paste results. The `--ignore` is required because
  `.pytest_cache` in the mounted repository is unreadable.
- **The Cowork device bridge refuses file deletion inside a mounted folder**
  (`unlink` and `rmdir` return `EPERM`). This one fact caused every runtime
  failure previously attributed to disk space: `uv` cannot extract an
  interpreter, SQLite cannot open a database in `WAL` or `DELETE` mode
  (`journal_mode=MEMORY` is the only mode that works), and
  `tempfile.TemporaryDirectory` recurses to `RecursionError` on cleanup.
- **The engine therefore cannot run in place in a mounted folder.** `nfl.sh
  doctor` correctly reports `pass_status: false` with `sqlite_probe_error`;
  `cowork-run` gates on `pass_status` and `registry.py:30` opens a real database
  under `data/registry/`. Either grant the session delete permission on the
  folder, or execute from a local-disk working copy of `src`, `tests`,
  `templates`, `config`, `pyproject.toml` and `uv.lock`, keeping the mounted
  repository as the source of truth for edits. Running the suite in place leaves
  undeletable temporary directories behind.
- **GitHub release assets are reachable.** The earlier claim that only
  `raw.githubusercontent.com` and `github.com` work understated it: a
  `releases/download/...` URL 302s to `release-assets.githubusercontent.com`,
  which serves the bytes from both the device VM and the cloud container.
  `api.github.com` also resolves. The former block was policy, not network:
  that host was not in `ALLOWED_HOSTS` and `fetch_public_artifact` set
  `follow_redirects=False`. `W1` added a single permitted hop confined to
  GitHub's own release-asset hosts. Every nflverse dataset is published this way,
  so this is what makes the adapter self-sufficient.
- `api.sleeper.app`, `api.weather.gov` and `api.the-odds-api.com` still fail to
  connect from both the device VM and the cloud container, so activity, weather
  and sportsbook market captures remain operator-supplied. `api.weather.gov` is
  allowlisted and reachable from a browser, which is a usable route not yet
  wired up.
- `actionnetwork.com` and other commercial odds sites cannot be artifact sources
  at all: not in `ALLOWED_HOSTS`, and the `OPERATOR_SUPPLIED` escape in
  `sources.py` is hardcoded to DraftKings, so even a hand-supplied number fails
  `_validate_metadata`. `nfldata/games.csv` is the market artifact of record
  until that policy changes.
- A session cannot invoke PowerShell or the Windows `.venv`. The device shell is
  Linux with the repo mounted, not a Windows shell.
- **The device VM's own `$HOME` filled up on 2026-09-08.** `/sessions` was 100%
  used with 794MB free on `/`, so the local-disk working copy went to `/tmp/w4`
  instead of `$HOME`. A `/tmp/nfl-cowork-venv` left by an earlier session is
  owned by a different uid and is not writable, so `sh ./nfl.sh setup` fails with
  `Permission denied` and building a second 603MB venv would not have fit. That
  venv's installed versions match `pyproject.toml` exactly (numpy 2.3.2, polars
  1.32.3, pyarrow 21.0.0, pydantic 2.11.7, highspy 1.11.0, scikit-learn 1.7.1,
  statsmodels 0.14.5, openpyxl 3.1.5, hypothesis 6.138.2, pytest 8.4.1), and its
  editable `.pth` points at a dead prior-session path, so the suite runs against
  it with `PYTHONPATH` set to the working copy's `src`. If a session needs a
  clean environment, free `/` first or work in the cloud container.
- **`git status` inside the mounted repository leaves `.git/index.lock` behind.**
  Git writes the lock, refreshes the index, then cannot unlink it, so the next
  git command reports a stale lock. On 2026-09-08 the leftover was renamed to
  `.git/index.lock.stale-from-cowork`, which git ignores; delete it from Windows.
  Prefer reading the working-tree state some other way, and if a session does run
  `git status`, move the lock aside before finishing.
- **nflverse retrieval works from the device shell.** Confirmed again on
  2026-09-08: a full `priors-propose` fetched and froze all seven artifacts in
  under a minute from `/tmp`, including the GitHub release-asset redirect.
- **`_ROOF_WEATHER` in `priors.py` treats nflverse `roof=open` as the
  schedule-derivable state `ROOF_OPEN`.** `prior_review` still asks for the
  `api.weather.gov` capture for that roof, because a retractable roof left open
  is played in the weather, but it cannot pass the operator's state to
  `priors-freeze` without tripping `WEATHER_STATE_CONFLICT`, so the capture is
  recorded in the run report and the artifact metadata still says
  `DERIVED_FROM_SCHEDULE_ROOF:open`. Closing that gap means editing
  `_ROOF_WEATHER`, which is `W1` territory and was left alone.
- **The delete-permission constraint also leaves Windows-side residue.** Bridge
  writes can leave directories the operator's own Windows account cannot
  enumerate. On 2026-09-08 that was `%LOCALAPPDATA%\Temp\pytest-of-benja` and
  the repository's `.pytest_cache`, which errored every test at setup with
  `WinError 5` from `os.scandir` inside `_pytest/pathlib.py`, in code that never
  reaches `nfl_dfs`. The `test` branch of `nfl.ps1` now pins both writable roots
  under `%TEMP%` so a session cannot poison them again, and the equivalent flags
  cannot be passed by hand anyway: `[CmdletBinding()]` makes PowerShell bind
  `-p` to `-PipelineVariable` before the script sees it. If a repository path is
  left unreadable, `takeown /F <path> /R /D Y` then `icacls <path> /grant
  "$env:USERNAME:(OI)(CI)F" /T` from an elevated prompt is the repair.

### Tranche table

| ID | Findings | Status | Depends on | Chunk |
|---|---|---|---|---|
| W1 | R01 | `DONE` (5 operator flags open) | operator DK Showdown salary CSV for the identity map | Linux runtime bootstrap check, then the nflverse-only deterministic prior adapter for one game |
| W2 | R07, R08 | `DONE` | none | Selection objective independent of scenario count; source expiry and evidence scope preserved and re-evaluated |
| W3 | R03 | `PARTIAL` (selection side `DONE`, simulator mask open) | none | One participation/exclusion contract with a simulator availability mask |
| W4 | R02 | `DONE` | none | DL3 prior-only review profile that never calls field, payout, or duplication economics |
| W5 | R04 | `READY` once the operator files land | contest facts | Showdown exact-template rehearsal on real downloads, byte audit, repeated run, stale-source and inactive-refresh cases |
| W6 | R09 | `DONE` | none | Split historical artifact integrity from a live pre-upload check that recomputes at the current clock. Owns `src/nfl_dfs/preflight.py` (new), the `command_audit`/`command_preflight` block and the `preflight` subparser in `src/nfl_dfs/cli.py`, and `tests/test_w6_live_preflight.py` (new) |
| W7 | R15 | `READY` | none | Version-bound settlement capture and the canonical operator run brief. Start before the first settled slate; the validation clock starts here |
| W8 | R05 | `READY` (W2 landed) | none | Measure the existing evaluator at true field size with cloning off, then S4A reference settlement and thresholds |
| W9 | R06 | `BLOCKED` on W8 | none | Canonical uniqueness at every bank boundary, objective-appropriate diversity, enforced exposure and Captain-per-person caps |
| W10 | R13 | `BLOCKED` on W8, W9 | none | Stage budgets, cancellation, measured peak memory, per-entry-count benchmarks |
| W11 | R10 | `BLOCKED` on W3 | none | Event and scoring reconciliation, participation modeling, measured dependence, DESIGN oversampling treatment |
| W12 | R11, R12 | `BLOCKED` on W7 data accrual | settled slates | Binding evidence minimums, slate-grouped splits, untouched temporal holdout, then the model artifact registry and derived promotion status |
| W13 | R14 | `BLOCKED` on W5 | none | Conditional late-swap portfolio generation and Classic lock-aware slot ordering |

### Deadline reality check

The 2026-09-07 and 2026-09-08 operator prerequisites in the punch list above were
not met: no matching Showdown reserved-entry template, contest facts, or approved
prior artifacts exist in the repository. R01 through R04 and R08 cannot all land
and be rehearsed before the 2026-09-09 opener at 19:20 CT.

Retarget: the Wednesday opener is a manual-guardrail rehearsal only. Ben selects
the lineup; the engine certifies legality, evidence, and exact bytes, with a fresh
certification run immediately before upload because R09 makes `audit` untrustworthy.
The first prior-only model-generated Showdown review run targets a Sunday
2026-09-13 single-game contest. DL4 and DL5 keep their scope and move to that date.
Classic (DL6 through DL8) stays behind Showdown; the 719-row, 24-team identity map
is the reason.

## Next action

### 2026-09-14 close-out: Q1B and Q1C are `DONE`; the corpus is still empty

Two settlement-plane sub-tranches landed the same day. Q1B built the standings
intake and measured why nothing could settle; Q1C built the pre-lock manifest
emitter that fixes it going forward. Complete pinned suite on Ben's Windows box:
**735 passed, 1 failed, 1 skipped in 198.190s** (737 collected). Doctor,
compile/import and `git diff --check` pass. Nothing is staged or committed.

**The next `READY` chunk is unchanged: none.** `C3` is still `BLOCKED` on native
Excel open/recalculate/save/reopen acceptance, which blocks `C4` and everything
after it. Q1B and Q1C were lettered sub-tranches of Q1 and displaced nothing.

Three things are open, in the order they matter.

1. **[BEN: two `nfl_standings_csv_v2` contract defects need your ruling.** Both
   were found on your real exports and neither was worked around silently: the
   contract cannot represent a field member who never submitted a lineup (11 of
   18 exports carry them), and it cannot hold an exact tie split that is not a
   whole number of cents (757 entries in 193391013 alone). The second is the
   serious one — `settlement._prepare_settlement` compares the evaluator's exact
   `Fraction` against the file's integer cents for every field row, so a contest
   with any uneven tie split can never clear `STANDINGS_PRIZE_MISMATCH` whatever
   the intake writes. Recommendations are under Q1B above. The normalizer refuses
   by default with a labelled, default-off opt-in for each, so nothing is blocked
   on this except settling a contest that has ties.]
2. **Landing the first settled contest is operator work, not code.** The engine
   can now do its half. What it needs from Ben: a slate entered from a
   *single-contest* reserved-entry file (16 of the 18 so far were multi-contest,
   which `settlement.require_single_contest` refuses outright), that contest's
   payout table, and its standings export pulled before DraftKings ages it out.
   The contest must also settle inside the registered `max_entries` of 200,000 —
   193028206 settled 832,342 and is excluded for that reason.
3. **A pre-existing test now fails every day.**
   `tests/test_w6_live_preflight.py::test_live_check_refuses_once_a_selected_player_has_locked`
   hardcodes an evidence expiry of `2026-09-14T00:00Z` and does not pin the
   certification clock, so `certify_upload` correctly refuses and the fixture's
   own assertion fails. Identical in `HEAD`, unrelated to either tranche, and
   left unfixed as out of scope. The fixture docstring already documents the
   repair: pass `monkeypatch` and `now`.

The validation corpus holds **zero settled contests**, across 18 entered across
three slates. All 18 raw exports are pulled and preserved, one is normalized, and
all 18 are dispositioned `placeholder` — a pre-lock prediction cannot be written
after the fact, so none of them can ever enter the corpus. Q6's accrual
dependency is unmet and no dev work shortens it.

### 2026-09-12 pre-slate action, Sunday Classic main slate

Ben is entering the 2026-09-13 Sunday Classic main slate. The blocking item was
R21 below, now landed. What remains before the run is operator evidence, not
code: an `api.weather.gov` capture per game (see R22 for why the dome games are
included), and one official-activity observation covering every selected person,
taken after the inactives publish and inside the three-hour window ending at the
earliest kickoff. C3 is still `BLOCKED` on native Excel acceptance; that blocks
calling C3 complete and blocks starting C4, and it does not block generating and
reviewing a Classic package.

**R24 — the registered C2 defaults build the wrong portfolio.** `LANDED
2026-09-12` (as tooling; no engine change). All four default stack rules ship
`strength: ADVISORY` with `minimum_entries: 0`, which the solver does not
enforce, and `default_search_limits` asks for `max(32, entries + 24)` candidates
out of a several-hundred-person pool. Measured on the supplied 719-person
fixture at a 1000-candidate bank: 811 of 1000 candidates `NAKED_QB`, 181 with a
QB and pass catcher. `scripts/make_classic_policy.py` now emits the same
registered contract with `QB_PASS_CATCHER` and `QB_BRINGBACK` at `HARD`,
scaled overlap and exposure caps, and a bank sized from wall-clock minutes.
Verified at 20 entries, rung 0: bank 1000 in 273.62s, joint solve
`OPTIMAL_ACTUAL_CANDIDATE_BANK` in 0.393s, all 20 entries selected, 20/20
`qb-pass-catcher` and 14/20 `qb-bringback`, zero naked-QB lineups selected.
Open question for a later tranche: whether these defaults should change in
`classic_portfolio_policy.py` itself, or stay a generator concern so the
registered contract keeps its current meaning.

**QA1 — the adversarial QA agent is not implemented.** `READY, NEXT DEV
TRANCHE`. Spec section 6 wants an audit that emits MILP constraints rather than
prose, applies a strict Pareto filter (`ΔCeiling >= 0 AND ΔSafety >= 0`, at least
one strict), re-solves, and caps at three iterations with early exit on zero
improvements. Today the pass is a manual subagent whose findings a human retypes
into a policy. The blocking design question is what `ΔCeiling` and `ΔSafety` mean
in an engine with no ceiling and no covariance: both currently have to be proxies
computed from the prior objective and the portfolio's own overlap structure, and
the tranche has to declare them honestly rather than implying a calibrated
quantity. Must not be started the night before a slate; it touches selection.

**R21 — the Classic selected-evidence gate demanded evidence no source
publishes.** `LANDED 2026-09-12`. `prior_review` required every selected
QB/RB/WR/TE to carry `state == "SOURCE_SUPPORTED_ADJUSTMENT"`, which only a
captured `NUMERICAL_ALLOCATION` team-allocation package produces. No approved
host publishes a forward-looking allocation, and `CLAUDE.md` forbids Ben
authoring one, so no live Classic slate could ever publish a selection while the
identical Showdown pool published fine. Every Classic test supplied a synthetic
role package, so the gap never surfaced. Ben ruled on 2026-09-12 that R17 applies
to Classic. The gate now accepts the resolver's own `selection_action` of
`SELECT` or `DIAGNOSTIC`, exactly as Showdown does, and no looser: an unresolved
or declared-changed role still blocks before selection, a person with no
prior-season row is still excluded with zero share, and a missing finding still
blocks. Every selected person resting on a history-derived prior is named in
`selected_evidence_gate.unverified_role_people` and in the C3 review's
`SELECTED_CURRENT_OFFENSIVE_ROLE` observation, whose state is now `UNKNOWN` when
any such person is in the portfolio. C3 re-derives the split from the gate
artifact rather than assuming it, so a package that stops covering a person the
gate claimed is still a hard `CLASSIC_C3_SELECTED_ROLE_EVIDENCE_MISSING`.

**R22 — Classic weather evidence demands a capture for schedule-resolved
games.** `PROPOSED`. `decide_weather` resolves a `dome` or `closed` roof from the
frozen schedule with no capture at all, but the multi-game package validated at
intake requires the exact complete game set, so supplying it at all forces a
capture for every dome as well. On the 2026-09-13 slate that is four unnecessary
`api.weather.gov` reads out of thirteen. The cause is ordering: the package is
validated at intake, before the propose step knows any roof. Cheapest honest
repair is to defer the coverage check until the roofs are known and require a
record only for a roof the schedule cannot resolve, still refusing a package that
omits a game whose roof needs one.

**R23 — the weather enum is a gate with no consumer.** `PROPOSED, NEEDS BEN'S
RULING`. `weather_state` is validated, hash-bound, carried into
`team_projections.csv` and reported, and no projection, opportunity or scoring
path reads it: the only references outside contracts and reporting are the
artifact row in `projection.py` and the report map in `cli.py`. On a
thirteen-game Classic slate it costs roughly half an hour of Sunday-morning
captures and expires six hours later, and it changes no number in the portfolio.
Either it should feed the model or the Classic gate should stop demanding one
capture per game for it. Do not act on this without Ben; it is an evidence-policy
decision, not a cleanup.

**Tooling added 2026-09-12.** `scripts/make_classic_weather_evidence.py` builds
the weather package from saved captures (stdlib only, no network, derives the
`AWAY@HOME` `game_id` set and salary hash from the exact salary bytes, reads each
forecast's own `generatedAt`). `scripts/make_official_status.py` gained
`--selection` (read roster IDs from `classic_selection.json`, since Classic C1/C2
write no assignment CSV) and `--whole-pool`, and its slate-lock warning now
derives the earliest kickoff on a multi-game file instead of silently going
quiet.

### 2026-09-11 current development action

**No item is currently `READY`.** DEV0, Q1, C1, and C2 are done. C3 remains
`BLOCKED` only on native Excel open/recalculate/save/reopen acceptance for its
generated workbook. Resume `docs/session-prompts/C3-classic-audit-review-export.md`
at that exact step; if it passes, finish the complete regression closeout,
mark C3 `DONE`, and then make C4 the sole `READY` item. Preserve the C2
policy/bank/assignment contracts and do not use the production field or payout
economics path or change `PRIOR_ONLY / DO_NOT_UPLOAD` truth.
After Q1's contracts are fixed, execute C1 through C4 in order to deliver the
prior-only Classic review workflow. Then continue Q2 through Q7 and QC1 to fix
the central-estimate/uncalibrated portfolio weakness for both modes. C5 may be
scheduled after C3 when mechanical Classic late swap becomes operationally
necessary, but it must not displace C4 or claim conditional EV.

The dated subsections below are retained as historical decision records. Their
older phrases such as `sole next`, `recommended next`, and `do not begin` are
not current scheduling instructions; the 2026-09-10 program and action above
supersede them.

### 2026-09-09 SD5 readable-review closeout

The bounded Showdown priority sequence in
`docs/SHOWDOWN_PRIORITY_TRACKER_2026-09-09.md` has completed SD5 software and
rendered-review acceptance. A valid `prior_review` export now produces
canonical readable JSON, escaped self-contained HTML and an eight-sheet workbook
only after independent exact-byte display reconciliation. The review exposes
exact entry/roster/person identity, salary, prior-only points, combined and
Captain exposure, policy maxima, overlap, evidence/role limitations, provenance,
all four release truths and one next action. Any mismatch stops at
`READABLE_REVIEW`, preserves earlier artifacts and remains `DO_NOT_UPLOAD`.

**Sole next READY item in that sequence: SD6**, the actual Cowork/Linux complete
workflow rehearsal using matching files and current game-specific evidence.
Windows acceptance cannot satisfy it. The self-contained prompt is
`docs/session-prompts/SD6-complete-cowork-linux-rehearsal.md`. W3, W7, W8, W9
and the larger S-tranche dependencies below remain separate and are not marked
complete by SD5.

### 2026-09-09 readiness review update

The user authorized a full workflow review and verified repairs across tranches
for today's Showdown run. Preserve the pre-existing uncommitted W6 and runbook
work. Current results and acceptance are in
`docs/READINESS_REVIEW_2026-09-09.md`.

- W4 now passes supplied current official inactive rows into prior selection;
  both roles are excluded. Live acquisition advances its clock before projection
  and checks source expiry again before export. The actual 136-row NE–SEA pool
  and two-entry template produced two legal, unique review lineups repeatedly.
- W6 now rejects malformed truth fields/manifests, unavailable policy files,
  missing model-specific evidence and activity/output-roster mismatches. The
  Windows launcher exposes preflight.
- Priors archive their raw inputs inside the frozen package; six-hour weather
  expiry is retained downstream. New NWS captures worked from Windows.
- R11's minimum-sample, cold-promotion, same-timestamp-fold and prediction-cutoff
  defects are repaired. W12 remains BLOCKED on real settled-slate evidence and
  an independently validated model registry; these repairs do not promote it.
- W3's simulator mask, W8/W9 economics/exposure redesign, calibrated ceiling and
  ownership, and actual Cowork/Linux live acceptance remain incomplete. No
  generated lineup has been certified for upload. W5 has real-file Windows
  review acceptance; complete live official-evidence acceptance remains open.

Next implementation: finish W3's simulator/build participation contract, then
W8/W9 economics and portfolio controls. Today's practical next operator step is
a fresh official-evidence review near kickoff. The current automatic profile
continues to report `PRIOR_ONLY / DO_NOT_UPLOAD`.

`W2` is `DONE` as of 2026-09-09, which unblocks `W8`. A frozen projection
package now carries its own per-source expiry, evidence scope and state,
transformation version and input dependency bindings on
`nfl_source_ledger_v2`; it archives its consumed sources content-addressed
inside itself, so a copied package validates with the originals deleted and
needs no Windows-to-Linux path rewrite; freshness is re-evaluated at whichever
clock the caller supplies, with the run's `as_of` as the replay clock and
`evidence.release_clock()` as the live one; and a legacy `nfl_source_ledger_v1`
package can no longer clear certification, because a shape that cannot express
an expiry cannot be called fresh. Portfolio selection ranks on a declared,
scenario-count-independent risk measure with Monte Carlo uncertainty reported
separately against a declared effective sample size. `MODEL_STATUS` stays
`PRIOR_ONLY` and `RELEASE_DECISION` stays `DO_NOT_UPLOAD` everywhere they were,
and the NE@SEA review export is byte-identical to the pre-W2 run. See
`changelog.md` for commands, counts and hashes.

`W6` (R09) is `DONE` as of 2026-09-08. `audit` is now historical artifact
integrity only: it reports the manifest's stored decision labelled as stored and
pins its own `RELEASE_DECISION` to `DO_NOT_UPLOAD`, so it can never be read as
renewed certification. The new `preflight` command is the live pre-upload check.
It validates the manifest schema, rebuilds every `EvidenceRecord` and re-derives
its state at `evidence.release_clock()`, requires the manifest to still cover
every hard field in `config/evidence_policy.json`, rebinds the salary, entry,
assignment and output files by hash, re-derives selected-player locks from the
current salary pool, reports the clock and scope of every check, and exits 0
only on `CERTIFIED_UPLOAD_PACKAGE`. The standing instruction is now: **run
`preflight` immediately before upload**, not `audit`.

**Recommended next: `W7` (R15) or `W8` (R05).** `W7` starts the validation
clock, so the sooner the better. `W8` begins the field-economics rebuild and
unblocks `W9` and `W10`. Neither is a same-day change.

`W1` and `W4` are `DONE`. `cowork-run --profile prior_review` now takes a
DraftKings Showdown salary CSV and a DKEntries CSV and returns the byte-audited
bulk-entry CSV in one command, driving `priors-propose`, the identity gate,
`priors-freeze`, `project`, `select` and `review-export` itself and stopping only
at the three gates that are genuinely human: an identity that is unresolved and
still selectable, a weather capture the schedule artifact cannot supply, and an
expired prior package with no permission to rebuild. `MODEL_STATUS` stays
`PRIOR_ONLY` and `RELEASE_DECISION` stays `DO_NOT_UPLOAD` on every path,
including the success path, and the release policy makes any other decision
unreachable for a `MODEL_ASSISTED` `PRIOR_ONLY` package. Verified end to end on
the real NE@SEA opener twice, once reusing the frozen package and once rebuilding
it from a fresh nflverse fetch; both produced the same export bytes. See
`changelog.md` for commands, counts and hashes.

**Next `READY` tranches, all touching disjoint files, in any order:**

- `W7` (R15): version-bound settlement capture and the canonical operator run
  brief. The validation clock starts here, so the sooner the better.
- `W8` (R05): measure the existing evaluator at true field size with cloning
  off, then the S4A reference settlement and its promotion thresholds. Newly
  `READY`; it unblocks `W9` and `W10`. Start from
  `portfolio.RISK_MEASURE`/`RISK_AVERSION`, which are now a declared preference
  rather than an artifact of the scenario count, and from
  `portfolio.resolve_effective_sample_size`, which is where a bank declares
  repeated or dependent draws.
- `W5` (R04) is unblocked by code and now waits only on operator contest facts:
  a matching reserved-entry template for the contest actually entered, the payout
  table, advertised prize value, field size, entry fee and contest ID.

What is still open and must not be papered over:

- **R03 simulator mask.** `simulation.py` still has no availability mask, so the
  zero-capacity scoring defect is untouched. Never route a pool through `build`
  expecting exclusions to hold. The selection path avoids it by never simulating,
  and `prior_review` never calls `build`.
- **No ownership, leverage, correlation or duplication model anywhere.** The
  objective maximizes a central estimate, which in a large-field GPP is chalk.
  This is the largest gap against the stated product objective and it is R05,
  R06 and S7 work, not a selection problem. `prior_review` does not narrow it
  and does not pretend to. `W2` removed the scenario-count dependence from the
  objective and nothing else: the field, payout and duplication economics under
  it are still the known-defective ones, and `RISK_AVERSION` is deliberately
  zero because weighting a tail the current field model computes would be
  weighting a tail R05 has not validated.
- **`projection.py` still requires a prior record for every person in the salary
  pool** (`SALARY_PERSON_IDENTITY_COVERAGE_MISMATCH`). A practice-squad elevation
  with no honest prior fails the whole package. Unchanged by `W4`.

Do not begin `W8`, `W9`, `W10`, `W11`, `W12`, or `W13`; do not relabel prior-only
output as EV, ROI, or edge; and do not move a generated assignment into the
manual-guardrail path to bypass the model gate. `prior_review` refuses an
`assignment_csv` outright for that reason.

### Operator decisions W1 left open, all now settled

All five were delegated to the implementer on 2026-09-08 and resolved:

1. **`weather_state`**: `CLEAR`, captured from `api.weather.gov` gridpoint
   `SEW/125,67` through the operator browser and attributed in coverage via the
   new `--weather-source-uri` / `--weather-observed-at` arguments.
2. **Salary CSV**: supplied and committed byte-exact under
   `data/runs/20260909-showdown-ne-sea/inputs/`, with the entry template.
3. **Eight identity decisions**: all accepted. Each was a unique league-wide
   match whose nflverse roster team disagreed with DraftKings, and all eight are
   DraftKings-flagged `OUT`. `W4` turned exactly that rule into the automatic
   acceptance in `prior_review.apply_identity_gate` and reproduced all eight.
4. **`sources.py` release-asset redirect**: retained. It is the only route to
   nflverse data, it is confined to one hop onto GitHub's own asset hosts, and
   the recorded provenance stays the canonical `github.com` URL.
5. **Runtime**: the local-disk working-copy pattern is the standing answer. It
   needs no permission prompt, keeps the mounted repository as the single source
   of truth for edits, and produced every green suite run. Delete permission on
   the folder remains a nice-to-have, not a blocker.

### New constraints for later tranches

`projection.py` requires a prior record for every person in the salary pool
(`SALARY_PERSON_IDENTITY_COVERAGE_MISMATCH`). A DraftKings pool routinely
contains a practice-squad elevation or a just-signed person with no honest prior,
and today the entire package fails rather than publishing without them. This
tension between fail-closed and pool reality needs a decision before the Sunday
run; it is adjacent to `W3`'s participation contract but not the same thing.

`role_capacity` cannot be used as a forward ceiling anywhere. It is a mean
prior-season offensive snap share, so it describes the role a person held while
someone was ahead of him, which is invalid in exactly the situation
redistribution addresses. `opportunity.remove_inactive_and_redistribute` enforces
it and therefore refuses a real pool outright. It is now treated as a diagnostic
in `participation.py`; the enforcement in `opportunity.py` remains and should be
revisited when `W3` completes.

The frozen team prior inherits `MARKET_LINE_MOVES_INTRADAY` from `games.csv` and
expires twelve hours after capture, so a prior package built the day before a
slate is stale by kickoff. `prior_review` detects that against `as_of` and
rebuilds; no tranche may widen an expiry to make a run succeed.

`uv` is unusable inside the cloud container: 268KB of cache in ten minutes
before timing out, while `pip` installed the whole pinned dependency set in 39
seconds. Use `uv` only to fetch the interpreter. The device shell
(`device_bash`) can also fail with "Failed to create bridge sockets" while the
other device tools keep working; the container fallback plus
`device_commit_files` is the way through.

### Constraints measured during `W2`, 2026-09-09

- **The local-disk working copy needs `README.md` and `LICENSE`.** The earlier
  list of what to copy omitted them, and `uv sync` fails on the missing readme
  with `OSError: Readme file does not exist: README.md` from hatchling's
  metadata validation, not with anything that names the real cause.
- **`/tmp` had room this session.** `/` reported 3.3GB free rather than the
  794MB measured on 2026-09-08, no `/tmp/nfl-cowork-venv` was left by another
  uid, and `sh ./nfl.sh setup` built the pinned environment cleanly. Check
  `df -h /` rather than assuming either measurement still holds.
- **The device shell died mid-session** with "Failed to create bridge sockets"
  and never recovered, while `device_list_dir`, `device_stage_files` and
  `device_commit_files` kept working. The container fallback is viable but has
  one trap: **the container's default interpreter is 3.11.15, not the pinned
  3.13.7**, and on 3.11 three tests fail for environment reasons alone
  (`ENVIRONMENT_DOCTOR_FAILED` in two `test_prior_review_profile` cases because
  `doctor` pins the runtime, and a float32 `share_conservation_max_abs_error`
  assertion in `test_simulation`). `uv python install 3.13.7` took 1.42 seconds
  and `pip` installed the pinned set into that interpreter in about 40; build
  that venv before trusting any container run.
- **The 2026-09-08 baseline was 277 passed, not 278.**
  `test_prior_review_profile.py::test_one_command_exports_and_reports_all_four_truths`
  was a clock bomb: it pinned a fixed `AS_OF` while `command_cowork_run` stamps
  `as_of` from the live clock, so six hours after `AS_OF` the fixture package
  expired and the run correctly blocked `PRIOR_PACKAGE_EXPIRED`. `W2` made that
  fixture's expiry follow the clock the code under test actually reads. Any
  fixture whose freshness matters must derive from the same clock as its caller.
- **The repository's frozen NE@SEA prior package is not self-contained.** Its
  raw sources live at the run root, `data/runs/<id>/raw/`, not inside
  `data/runs/<id>/priors/`, so `resolve_frozen_artifact` answers
  `FALLBACK_SEARCH` rather than `IN_PACKAGE`. Every run report now records
  which one answered. Making `priors.freeze_prior_package` archive raw inside
  the frozen package would close it; that is a priors-owning tranche, not `W2`.
- **Effective sample size must be declared, never inferred from outcomes.** An
  earlier `W2` draft derived scenario multiplicity by collapsing identical
  per-candidate outcome rows. Independent scenarios routinely settle a
  portfolio at the same value, so that understates precision, and an
  overstated standard error *widens* the REFEREE tolerance, because
  `qa.referee_blocks` blocks only when `abs(delta) > uncertainty`. On the
  W2 fixture bank it reported an effective size of 1.47 for 100 independent
  draws and let a sign disagreement of 10.0 through that the old formula
  blocked. Silence now means independent draws, which is what
  `economics.evaluate_candidates_against_field` guarantees by refusing a
  non-uniform bank.
- **A ledger is a plain JSON file, so preserving an expiry inside it is half a
  gate.** `projection.verify_projection_package` checks every declared expiry,
  state, observation time and source URI back against the archived source's own
  hash-bound metadata, and requires the entry set to cover all four scopes,
  because deleting an expired entry is otherwise as effective as forging its
  expiry.

### Constraints measured during `W6` and the opener rehearsal, 2026-09-08

Runtime, all newly measured and all cheap to trip over again:

- **The `/tmp` paths a session prompt names may be owned by a previous
  session's uid.** `/tmp/nfl-cowork-venv`, `/tmp/nfl-uv-cache` and
  `/tmp/nfl-uv-python` were all `nobody:nogroup` and mode `755`, so the
  prescribed `sh ./nfl.sh setup` died with `Failed to initialize cache at
  /tmp/nfl-uv-cache ... Permission denied (os error 13)` and exit 0, which is
  easy to miss. Point `NFL_DFS_VENV_DIR`, `NFL_DFS_UV_CACHE_DIR` and
  `NFL_DFS_UV_PYTHON_DIR` at fresh per-session directories. A full `uv sync`
  into new directories, interpreter download included, took under 30 seconds on
  3.2GB free.
- **The device VM can restart mid-session and wipe all of `/tmp`.** It happened
  once here, between two tool calls, with no warning beyond a "Workspace still
  starting" error on the next command. It took the working copy, the venv and
  every rehearsal artifact with it. The mounted repository survived untouched.
  **Write source changes into the mounted repository as they are produced and
  build the throwaway working copy from it**, rather than editing in `/tmp` and
  copying back at the end.
- **`pytest` background jobs must be detached.** A plain `nohup ... &` inside a
  `device_bash` call is killed when the call returns, leaving a zero-byte log
  and no process. `setsid nohup sh -c '...' >log 2>&1 </dev/null &` survives.
- **The prescribed `-q` makes the test summary disappear.**
  `pyproject.toml` already sets `addopts = "-q --strict-markers"`, so
  `sh ./nfl.sh test -q ...` is `-qq` and pytest suppresses the
  `N passed, M skipped` line entirely. Drop the extra `-q` when the counts
  matter.

Certification behavior, measured against the real NE@SEA files:

- **Two reserved entries carrying identical rosters block certification.**
  `DUPLICATE_SELECTED_LINEUPS` is a CRITICAL blocking QA finding and the run
  ends `DO_NOT_UPLOAD` with `FILE_VALID` false. Filling every reservation with
  one lineup is not a supported shortcut.
- **The pre-lock official-status window is three hours, not ninety minutes.**
  `cli._official_status_evidence` uses `freshness_window=timedelta(hours=3)`:
  the oldest selected-player observation must be no earlier than kickoff minus
  three hours *and* the certify run must fall within three hours of it. The
  ninety-minute figure belongs to `evidence.team_inactive_report_evidence`,
  which governs governed late swap and is a different file shape and a
  different gate. Do not quote T-90 for the pre-lock path.
- **`FILE_VALID` and the byte path are independent of the evidence verdict.**
  The same two lineups produced export SHA-256
  `08004c252695284ea96c10c291915e9c0cf316aadec944a65ca3389cfbd38df2` both as a
  blocked `proposed_sha256` and as a released `sha256`, 144 template lines in
  and 144 out with exactly lines 2 and 3 changed.

### 2026-09-10 pre-slate review: repairs landed, decisions open

Full record in `changelog.md` (2026-09-10 entry) and
`tests/test_cowork_rerun_regressions.py`. Suite 495 passed, 1 skipped; replay
export hash `cf33f3e5…` unchanged. Repairs landed in `src/nfl_dfs/cowork.py`,
`cli.py`, `prior_review.py`, `selection.py`, `readable_review.py`,
`workbook.py` and `scripts/make_official_status.py`: fresh `--input-dir`
supersedes a reloaded request, list flags merge on rerun, run-id collision is
refused before any write, `lineup_count` below entries blocks before export,
legacy captain exhaustion falls back to repeats, salary-mismatched packages
rebuild under `build_priors`, sanitized export label, pool coverage and kicker
assumptions on every review surface, `--official-status-csv` with selected-
people coverage, Upload sheet names the review CSV.

Operating facts for the next live run:

- `--request` reruns must repeat an out-of-tree `--prior-package-dir`; the
  request's own copy is not trusted (path confinement, by design).
- The generated request keeps `prior_package_dir: null` after a
  `--build-priors` run, so every `--request` rerun re-fetches nflverse (about a
  minute). Pass `--prior-package-dir <run>/prior_review/priors/frozen` to reuse.
- nflverse `games.csv` lists Week 1 2026 as `2026_01_NE_SEA` 09-09 and
  `2026_01_SF_LA` 09-10 20:35 ET at Melbourne Cricket Ground, then Sunday
  09-13. The MCG row carries `roof='dome'`, so the engine derives `INDOOR`
  and asks for no weather capture; `weather_state` is not consumed by scoring,
  so this is a provenance label, not a number.
- Container: `github.com` and `api.github.com` fail Python 3.13 strict X.509
  behind the egress proxy; `raw.githubusercontent.com` passes;
  `api.weather.gov` is denied. The device VM does not have this problem when it
  mounts.

Decisions taken 2026-09-10 (see the changelog entry): TLS opt-in landed;
R17 landed as the transfer prior plus visible missing-history exclusion (Ben's
direction: use prior-team stats; combine/draft-based rookie priors remain open
because no approved captured mapping to usage share exists); R18 landed as the
policy-stratified bank. The two sections below are retained as the record of
the finding; both are `DONE`.

### Proposed `R18`: the SD4 candidate bank is policy-blind (`DONE` 2026-09-10)

Found 2026-09-10 on the real NE@SEA pool. `portfolio_enforcement.
build_policy_candidate_bank` enumerates the top 32 lineups by prior points with
no-good cuts and a 1e-9 perturbation; it never reads the policy. On this pool
JSN and Maye appear in all 32 candidates (and in all 216 at a 120s budget), so
a 5-entry policy with captain cap 0.2, or combined cap 0.8, or a 20-entry
policy with overlap 4 or any captain cap, ends in
`CANDIDATE_BANK_EXHAUSTED_INCOMPLETE`. Validation passes (`valid: true`) and
selection then fails with no next action. Only near-uncapped portfolios
(overlap ≥ 5, no caps) succeed, yielding 16 to 19 of 20 JSN captains. The
legacy path's distinct-captain rule has the opposite failure: by lineup 15 it
captains DSTs and 0.5-point players (prior points 113 → 83 at 20 entries),
and after the 2026-09-10 fallback it repeats captains from index 27.

Smallest repair: make bank generation policy-aware. Seed strata per eligible
captain (fix the CPT row, enumerate top-k) until the seeded captains' summed
`captain_max_entries` covers the entry count with margin; for every person with
`combined_max_entries < entry_count`, enumerate top-k lineups with that person
excluded; then fill the remaining budget with the current top-K enumeration.
Raise `candidate_limit` to scale with entries (e.g. `max(32, 4 × entries)`)
and make it and the budgets request fields. The joint MILP and the
independent audit are unchanged. Report per-stratum counts in
`candidate_bank`. Until this lands, portfolios above a handful of entries are
either near-uncapped (policy) or degrade in the tail (legacy).

### Proposed `R16`: the official-status gate binds provenance, not a source

Found during the opener rehearsal. Not scheduled; it needs a decision before it
becomes a tranche.

A rehearsal run reached `CERTIFIED_UPLOAD_PACKAGE` under a simulated 18:00 CT
clock on an official-status CSV whose every `SOURCE_URL` was
`https://rehearsal.invalid/SYNTHETIC-NOT-OFFICIAL-EVIDENCE`. `.invalid` is an
IANA-reserved TLD that can never resolve. Two separate gaps let that through:

1. **No host check.** `evidence.py:554-556` validates only
   `scheme == "https"` and a non-empty hostname. `sources.py` maintains
   `ALLOWED_HOSTS` for automated retrieval, and nothing on this path consults
   it. Rejecting reserved and non-resolvable TLDs, or requiring an allowlisted
   host, would have refused this exact file.
2. **The validated URL is then discarded.** `parse_official_inactive_snapshot`
   populates `InactiveStatusSnapshot.source_url_by_id`
   (`evidence.py:572-573`), and `cli._official_status_evidence` builds its
   `EvidenceRecord` without a `source_url` (`cli.py:519-529`). The certified
   manifest therefore records `"source_url": null` for
   `official_inactive_status` while that record's own `reason` reads "every
   selected exact DK ID is source-bound". The CSV's bytes are hash-bound; the
   source it claims is not recorded at all, so no later audit can see what was
   asserted.

Neither is a design failure on its own: this path is operator-supplied evidence
by policy, and the operator attests to the content. What is wrong is the word
"source-bound" in a `PASS` reason and in `docs/DATA_CONTRACTS.md`, which
overstates what the gate binds. The honest description is a provenance and
freshness gate, and the cheap repairs are to record `source_url` on the record
and to reject hosts that cannot be real. The synthetic package built during the
rehearsal was destroyed; no upload-shaped CSV survived it.


### Proposed `R17`: SD2 has no live exit for Week 1 transfers and rookies (`DONE` for transfers 2026-09-10; rookie prior open)

Found on the first live NE@SEA run, 2026-09-09 22:18Z. Not scheduled; it needs a
decision before it becomes a tranche.

With fresh nflverse priors and a clean identity gate, `resolve_offensive_roles`
blocked 20 of the 47 selectable people: every 2026 rookie (`MISSING_HISTORY`)
and every player whose 2025 history sits on another team
(`OFFENSIVE_TRANSFER_REQUIRES_CURRENT_TEAM_ROLE`), including A.J. Brown, Romeo
Doubs, Jadarian Price and Emanuel Wilson. The gate's only non-exclusion exit is
a `NUMERICAL_ALLOCATION` source whose excerpt is a JSON object identical to the
declaration. No approved host publishes that for a game not yet played, and
`docs/DATA_CONTRACTS.md` already records that a live compatible numerical
source has not been demonstrated. The run therefore completed only after all
20 were operator-excluded. Correction, 2026-09-10 review: the 20 blocked people
carried exactly zero share before the gate ran (no current-team 2025 rows, so
`priors.build_player_records` gives them zero raw counts), and
`unallocated_by_team` is byte-identical between the blocked run and the excl20
run. The NE carry share 0.455 and SEA carry share 0.650 left unallocated belong
to DK `OUT`/`IR` people (Henderson, Charbonnet, Boutte, Jennings), not to the
block. Excluding the 20 cost the objective nothing; what the block does cost is
their visibility (Brown, Doubs, Price, Wilson have no share at all) and a manual
`--exclude` of every rookie and transfer on every early-season slate.

The gate is behaving as designed. What is missing is a designed outcome for the
case where the required evidence cannot exist yet. Three candidate decisions,
none taken here:

1. Keep the block and document operator exclusion as the Week 1 procedure,
   with the unallocated volume printed in the handoff (what happened tonight).
2. Admit a bounded, versioned "current-team history unavailable" prior for
   transfers that carries `EVIDENCE_STATE=UNKNOWN` into the report and can
   never clear certification, so a transferred WR1 is at least visible to the
   objective.
3. Add an approved numerical source. Candidates within the allowlist are
   nflverse `depth_charts` (qualitative, so it fails today's contract) and
   nothing else; a new host would need its own license decision and adapter.

Whichever is chosen, `prior_review` should report the count and salary of
blocked-and-excluded people next to the lineups so the pool coverage is visible
without reading the offensive-roles report.
