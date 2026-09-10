# Next-session prompt — SD6 complete Cowork/Linux rehearsal

Execute **SD6 only** in `C:\Users\benja\Documents\Claude\nfl-dfs`, using the
actual Claude Cowork/Linux environment for the environment-acceptance portion.
Carry the bounded work through immutable intake, current evidence acquisition,
projection, role/activity gates, portfolio controls, readable review,
independent byte QA, copied-package replay, fault rehearsals, verification and
mandatory tracker closeout. Do not stop at a plan.

Execute only when SD5 is `DONE` and SD6 is the sole next `READY` item in
`docs/SHOWDOWN_PRIORITY_TRACKER_2026-09-09.md`. Windows tests, an `nfl.sh`
syntax check, a simulated Linux fixture or an older Cowork run cannot satisfy
actual Cowork/Linux acceptance. If this session is not running in the real
Cowork/Linux environment, or matching current files/evidence are unavailable,
do every safe prerequisite check possible, keep the acceptance dimensions
separate, record the smallest exact missing prerequisite and do not call SD6
complete.

The intended operating surface remains two user-attached DraftKings CSV files:
one Showdown salary export and one matching reserved-entry export. Supporting
evidence and portfolio policy are narrow, versioned, source-bound auxiliary
artifacts produced by the workflow. Do not ask the operator to invent numerical
priors. Every generated lineup remains `MODEL_STATUS=PRIOR_ONLY` and
`RELEASE_DECISION=DO_NOT_UPLOAD`. DraftKings login, entry editing, upload and
money movement remain manual and outside this session.

## Git and preservation safeguards

Before any edit or run:

1. Read `CLAUDE.md`, `docs/COWORK_RUNBOOK.md`, `docs/DATA_CONTRACTS.md`,
   `IMPLEMENTATION_STATUS.md`, `backlog.md`, the latest `changelog.md`, and the
   complete Showdown priority tracker. Inspect applicable `AGENTS.md` files.
2. Record branch, exact HEAD, upstream, staged paths, tracked modifications and
   untracked paths. Preserve every pre-existing change and user-owned/generated
   file. In particular, do not assume `Claude outputs/` or untracked W2/W4
   prompts are disposable.
3. Confirm SD5's code and documentation are present in the current tree. Recheck
   current code/runtime rather than treating its older Windows closeout as live
   evidence.
4. Mark SD6 `IN_PROGRESS` in the tracker with date, environment, start HEAD,
   bounded scope and preserved dirt.

No reset, clean, stash, rebase, pull, merge, broad formatting, dependency
upgrade, staging, commit, push or account action. Never use `git add .` or
`git add -A`. Do not overwrite attachments, frozen evidence, earlier runs,
review files or entry exports. Use a new run ID for every attempt and keep
samples in ignored run directories. Do not change any release gate to make the
rehearsal pass.

## Acceptance dimensions — report independently

SD6 has three separate dimensions. Never collapse them into one green label.

1. **Automated fixture mechanics** — pinned-runtime tests cover the full
   SD1-SD5 path and the required failure cases.
2. **Actual Cowork/Linux execution** — the real mounted repository and Cowork
   runtime execute the documented `nfl.sh` path, including setup/runtime
   constraints, approved source access, immutable snapshots and readable output.
3. **Current real-file/evidence review** — matching current DraftKings files,
   current game-specific evidence, exact identity/role/activity facts and the
   requested portfolio controls reconcile without borrowed or fabricated facts.

Mark SD6 `DONE` only if every applicable acceptance condition below passes in
the actual environment with matching current files. A structurally correct or
attractive report is not current-evidence or model certification.

## Bounded execution

### 1. Establish the actual Cowork runtime

Do not use the Windows `.venv` from Linux. Follow the measured mounted-filesystem
workaround in `docs/COWORK_RUNBOOK.md` and keep mutable runtime/cache state on
Cowork-local disk:

```sh
export NFL_DFS_VENV_DIR=/tmp/nfl-cowork-venv
export NFL_DFS_UV_CACHE_DIR=/tmp/nfl-uv-cache
export NFL_DFS_UV_PYTHON_DIR=/tmp/nfl-uv-python
sh ./nfl.sh setup
sh ./nfl.sh doctor
```

Record the resolved workspace, OS/runtime identity, Python version, locked
dependency state, processor/memory facts where measurable, SQLite result,
mount/reparse behavior, long-path behavior and exact setup/doctor timings.
Do not bypass TLS, allowlists or source policy silently. If the Cowork egress
proxy exposes a certificate problem, record the exact failure and use only an
explicitly approved, narrowly scoped environment remedy that retains chain and
hostname verification; do not weaken repository source validation.

### 2. Classify and preserve the two current attachments

Use schema-based discovery. Verify that the salary file is Showdown and that the
entry file has matching Showdown roster geometry and reserved entries. Record
original paths, byte counts, encodings, physical-line geometry and SHA-256
values before the workflow snapshots them. Reject ambiguous duplicate CSVs,
wrong mode, mixed game, mismatched contest/slate, prefilled unauthorized cells
or missing reserved entries. Never infer matching files from their filenames.

Start the intended one-command path with a new label:

```sh
sh ./nfl.sh cowork-run \
  --input-dir '<attachment-directory>' \
  --profile prior_review \
  --build-priors \
  --label '<current-slate-label>'
```

Record command, exit code, wall time, run ID, generated request path, immutable
input snapshot paths/hashes and all named blockers. Exit 2 on a two-file first
pass may be correct; it is not a failed rehearsal when the report truthfully
identifies missing current evidence and the next action.

### 3. Obtain only approved current evidence

Use approved adapters and retain raw captured bytes, source URI, license
decision, parser/transformation versions, observed/captured/expiry times and
SHA-256 values. Reconcile every source to the exact current game and salary
identity. Never reuse the historical NE-SEA weather, roles, statuses, policies
or prior package for a different slate or a later clock.

As applicable:

- acquire/freeze the current prior package and exact identity map;
- capture outdoor weather from the approved NWS path using the source's actual
  observation/generated time and game-period conditions;
- provide exact current official activity rows. Missing rows remain unknown;
  salary status never proves current ACTIVE status;
- resolve ambiguous multi-kicker teams with `nfl_kicker_role_evidence_v1`;
- resolve missing history, transfers, rookies or material offensive-role changes
  only with compatible `nfl_offensive_role_evidence_v1` numerical allocations;
  qualitative depth-chart prose cannot invent a share; and
- author/validate `nfl_showdown_portfolio_policy_v1` against the exact salary
  hash, game, full CPT/FLEX person map and requested Entry-ID order. Record
  declared fractions, exact floor-derived integer maxima, exclusions,
  uniqueness and overlap. Never relax a requested cap to obtain feasibility.

If an authorized source cannot establish a required fact, retain its precise
blocker and stop that acceptance dimension. Ask the operator one concise
question only for an essential contest fact that authorized sources cannot
provide. Do not access DraftKings programmatically or through browser control.

### 4. Rerun the immutable request and inspect all stages

Add only validated auxiliary artifact paths to the generated request and rerun:

```sh
sh ./nfl.sh cowork-run --request '<full-path-to-run_request.json>'
```

Verify and record:

- original and snapshotted input hashes, frozen-source hashes and portable path
  bindings;
- exact identity coverage, participation/exclusion precedence, kicker scoring
  conservation and offensive allocation findings;
- projection artifact and ledger hashes, source expiry and live release clock;
- candidate-bank count, coverage/status, generation time and memory where
  measurable. `CANDIDATE_LIMIT_REACHED_INCOMPLETE` remains incomplete;
- one joint policy solve over the actual bank, exact requested Entry-ID coverage
  and order, no cycling, solver status/scope/gap/nodes/time where reported;
- independent final policy audit and its salary, entry, source-policy,
  normalized-policy and assignment hashes;
- exact review-export byte audit, physical-line preservation, legal lineups and
  output SHA-256; and
- SD5 display reconciliation, readable JSON/HTML/workbook hashes, exact lineup
  and exposure facts, evidence/role observations, provenance links, four
  independent truths, named blockers and one next action.

Open the readable HTML and workbook in the actual Cowork-accessible workflow.
Render and inspect every workbook sheet and every continued page at readable
zoom. Check exact IDs/names/salaries, non-ASCII text, wrapping, widths/heights,
repeated headings, pagination, paths/hashes and visible warning hierarchy. Scan
for formula errors. `DISPLAY_RECONCILIATION=PASS` proves agreement with exact
artifacts only; it never makes the file upload-ready.

### 5. Rehearse portability and deterministic replay

Copy the frozen package and request into a new ignored run root without changing
their bytes. Rebind only paths through the documented portable mechanism. Run
from the copy after removing access to the original package where safely
possible; never delete user data. Require the copied package to validate using
its archived content-addressed sources. Repeat an identical-input request with a
new run ID and compare all artifacts whose format is designed to be stable,
including assignment and review-export bytes, normalized policy, canonical
readable JSON and HTML. Explain any deliberately variable timestamps or
workbook container bytes instead of claiming byte stability for them.

### 6. Exercise named fail-closed cases safely

Use copied fixtures or dedicated test run roots, never mutate the accepted live
artifacts in place. Cover at least:

- an expired frozen source at the live clock;
- ambiguous multi-kicker or unsupported offensive role evidence;
- a current inactive/status change that invalidates a selected person;
- policy capacity that is necessary-failure, incomplete-bank exhaustion or
  proven modeled-bank infeasibility, keeping those states distinct;
- mutation of salary, entry, policy, assignment, independent audit or exported
  review bytes; and
- mutation of readable JSON/HTML after publication.

Each case must name the discrepancy, preserve earlier output bytes, write no new
top-level review CSV after the failure point, and remain
`RELEASE_DECISION=DO_NOT_UPLOAD`. Do not weaken evidence, selection, audit,
display or release logic to convert an expected blocker into success.

Scope-local defects demonstrated by the actual Cowork path may be repaired with
focused regression coverage. Do not expand SD6 into a new model, source system,
UI framework or portfolio objective. Record larger defects as a smallest
bounded follow-up while keeping the affected acceptance dimension incomplete.

## Verification and closeout

Run focused tests first, then the complete pinned Cowork/Linux suite from a
Cowork-local temporary root so the mounted repository does not need recursive
deletion. Follow the exact current runbook syntax; do not reuse a Windows test
count as the Linux result. Also run `sh ./nfl.sh doctor`, compile/import checks
appropriate to any code changed, formula/error scans, and whitespace checks.

Before finishing, inspect the entire diff and update:

- `docs/SHOWDOWN_PRIORITY_TRACKER_2026-09-09.md`;
- `backlog.md`;
- `changelog.md`;
- `CLAUDE.md`, `IMPLEMENTATION_STATUS.md`, `docs/DATA_CONTRACTS.md` and
  `docs/COWORK_RUNBOOK.md` wherever actual operating behavior or limitations
  changed.

The tracker completion record must include date, actual environment, start/end
HEAD, changed paths, preserved dirt, exact commands, exit/pass/fail/skip counts,
timings, memory where measured, all immutable input/output paths and hashes,
portable replay comparison, fault-rehearsal results, rendered page/sheet review,
formula scan, doctor, whitespace result and every unmet criterion. Report the
three acceptance dimensions independently.

Mark SD6 `DONE` only when automated mechanics, actual Cowork/Linux execution and
current real-file/evidence review all pass. Otherwise use `IN_PROGRESS` for
remaining in-scope work or `BLOCKED` for an actual external prerequisite, state
the exact smallest remainder, and do not manufacture a successor READY item.
SD6 is the final item in this bounded priority sequence; do not infer completion
of W3, W7-W12 or the larger S4-S10 backlog.

Final response: actual environment and commands, current files/evidence used,
stage results, readable output paths/hashes, independent audit/reconciliation,
rendered review, copied replay, fault cases, exact verification, limitations,
tracker status and smallest next action. For every generated run report
`FILE_VALID`, `EVIDENCE_STATE`, `MODEL_STATUS` and `RELEASE_DECISION`
separately. Do not stage or commit.
