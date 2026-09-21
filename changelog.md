# NFL DFS Implementation Changelog

This file records completed implementation work and verification evidence for `backlog.md`. Keep entries factual and append new dated sections beneath `Unreleased`. Do not describe planned, diagnostic, synthetic, or structurally legal work as live-certified or upload-ready.

## Unreleased

### 2026-09-21: P7, the engine can tell who is starting today

Chunk `P7`, on `claude/next-implementation-priorities-ptjksf`. Release truths
unchanged: every path still ends `MODEL_STATUS=PRIOR_ONLY` and
`RELEASE_DECISION=DO_NOT_UPLOAD`. No run was executed and no gate's authority
changed.

#### What landed

- **`src/nfl_dfs/depth_roles.py`** (new). Effective depth rank for `QB`, `RB`,
  `WR` and `TE`: the published `pos_rank` at one `(team, position)` with
  everyone the bound salary bytes flag unavailable removed from above, and the
  survivors renumbered from 1. Keyed `(person, position)` and never by person
  alone, so a return line cannot become an offensive role.
- **`qb_depth_roles.py`**: `QB_DEPTH_STARTER_NOT_SELECTABLE` is replaced by
  promotion, under `R25`'s bounds. Availability is re-derived from
  `contract.unavailable_people` (the salary Status bytes) rather than from
  `selectable_people`, so an operator exclusion can never promote a backup; that
  case keeps a refusal, now `QB_DEPTH_PROMOTION_OVER_AVAILABLE_PERSON`. A team
  with nobody selectable anywhere in the order still refuses, as
  `QB_DEPTH_NO_SELECTABLE_PERSON_AT_POSITION`. Every promotion is reported in
  `effective_starter_promotions` alongside a `promotion_rule` string.
- **`priors.py`**: `depth_charts` registered as the eighth `NflverseSource`, so
  the chart is frozen into the prior package and hash-bound like the other
  seven instead of living only in a producer script. 36-hour expiry, matching
  the producer's existing number so the two paths cannot disagree about whether
  one capture is fresh.
- **`participation.py`**: `redistribute_opportunity` takes an optional
  `depth_ranks`. Supplied, a vacated share goes to the effective-rank-1 survivor
  at the vacating position; omitted, the measured proportional rule is
  unchanged. **Off by default on purpose.** The proportional rule was forced by
  measurements on the real NE@SEA pool and nothing has graded inheritance
  against it; that needs `P0`. Switching the default should follow a number.
- **`docs/DATA_CONTRACTS.md`**: `effective_depth_rank_v1` and the
  `depth_charts` registration documented. `nfl_qb_depth_role_evidence_v1` is
  **not** mutated; a package still declares the published order and the engine
  derives the effective one.

#### Evidence, measured rather than recalled

The real nflverse artifact was captured on 2026-09-21 through
`sources.fetch_public_artifact` (the only approved client), 51,864,767 bytes,
sha256 `e6ba0a08dc40c164eb02ce7654a247c8eb5c2d189c92d993d028524eb0494c02`. It
holds 190 snapshots. The fetch needed `NFL_DFS_TLS_ALLOW_NONSTRICT_CA=1`, the
approved opt-in, because this container's proxy CA has no key-usage extension.

Confirming the chunk's premise: the last snapshot before the 2026-09-20 13:00 ET
lock is `2026-09-20T12:14:30Z`, which is 08:14:30 ET, against inactives at about
11:30 ET. The brief's cadence table is correct.

At that snapshot: `SEA` QB Darnold 1, Lock 2, Milroe 3; `MIN` QB Murray 1,
Wentz 2, McCarthy 3; `LV` TE Bowers 1, Mayer 2; `HOU` WR Collins 1,
Hutchinson 2; `BAL` WR Flowers 1, Bateman 2. Every promotion the `R25` stanza
named is reproduced by the resolver from those ranks.

The kick-return hazard is real and is now covered: Brian Robinson Jr. (ATL) is
`KR` 1 and `RB` 2, and Devin Duvernay (ARI) is `KR` 1, `PR` 1 and `WR` 6.
Keying by person and taking the best row would have made them a lead back and a
WR1.

#### A test this changed, and why

`tests/test_backlog_queue.py::test_the_blocker_ben_actually_owns_is_flagged`
failed after `R27` closed operator item 1b. It asserted the literal words
"standings exports" appeared in an open `[BEN: ...]` flag. That assertion was
wrong once Ben ruled, in the same way its previous version was wrong once the
pull request it named merged: both pinned a fact with an expiry date rather than
the invariant. It now asserts the invariant that does not expire, that any
queue row `BLOCKED` on Ben has a flag a session start can show. The test was not
deleted, skipped or loosened; it asserts strictly more than before, across every
blocked row rather than one hardcoded phrase.

No test asserted `QB_DEPTH_STARTER_NOT_SELECTABLE`, so replacing that refusal
weakened no existing coverage. The behaviour had none.

#### What this does not prove

The acceptance line "on the 2026-09-20 salary snapshot" is **not** met here and
is not claimed. `data/runs/` is gitignored, so that salary export is on Ben's
Windows checkout and is not in this container; DraftKings is never fetched. The
`Status` bytes in these fixtures are chosen to reproduce the documented
situation, not read from that export. The depth-chart half is real published
bytes; the DraftKings half is a fixture. The snapshot-bound replay and the
byte-identical-replay-on-the-frozen-snapshot line stay open as Windows-session
acceptance items and are recorded as such in `backlog.md`.

#### Verification

- Complete pinned suite on `.venv-linux`, watched to completion:
  `1048 passed, 1 skipped in 159.46s (0:02:39)`. That is the 1023 the branch
  inherited from PR #34 plus the 25 tests this chunk adds, and the one skip is
  the expected Windows symlink-permission case.
- Focused first: `tests/test_depth_roles.py` 17 passed;
  `tests/test_qb_depth_roles.py` 43 passed; `tests/test_participation.py`
  26 passed; `tests/test_priors_adapter.py` and
  `tests/test_classic_prior_review.py` 66 passed together.
- `sh ./nfl.sh doctor`: `pass_status: true`.
- `git diff --check` clean; `python3 scripts/check_protected_paths.py` reports
  `No protected path touched (3 changed)`; changed modules compile.

### 2026-09-21: R27 ruled, X2 unblocked, and PR #34 merged

Ledger only, no code.

- **PR #34 merged** (`803618a`) on green CI for head `f4165ef`: `suite`,
  `boundaries` and `protected-paths` all success on run 35553889624. It brought
  `R26` (a retractable venue's blank `roof` resolved from the venue's own
  completed-game history) and the session probe at the head of `run-slate`.
- **`R27` ruled by Ben**: the 26 standings exports live as private GitHub
  release assets with authenticated retrieval added to `sources.py`. Options B
  (commit the corpus, 1.5MB to ~80MB and growing) and C (leave `P0`
  Windows-only) rejected. `X2` moves `BLOCKED` to `READY`; operator item 1b is
  closed. Its bounds are in the `R27` stanza and are binding on the chunk.
- The flag's claim that option A needs a `ben-review` pull request is corrected.
  `src/nfl_dfs/sources.py` left the protected list on 2026-09-20, so `X2` merges
  on green like any other chunk.

#### Egress measured, and it contradicts a document and a sibling session

`scripts/session_probe.py` in this container, 2026-09-21: all six allowlisted
hosts reachable, `VERDICT: CAN_COMPLETE_A_RUN`. PR #34, written the same day,
measured `api.weather.gov` at 403 on CONNECT and called it "organization policy,
not routable around". Both measurements are correct; egress varies per session.

That is `X1`'s whole case, now with same-day evidence on both sides, and it
means `docs/CLAUDE_CODE_SETUP.md` § Known environment facts cannot be fixed by
editing the value: it asserts a per-session fact as a standing one. It is also
stale on a second count, claiming a suite of `1 failed, 735 passed, 1 skipped`
against a measured 984 passed at that commit. `X1` owns both.


### 2026-09-21: the weather gate stops demanding a forecast for a game played under a roof

Raised by Ben after the Week 2 afternoon Classic slate: "why do we keep having
issues with weather and how can we get around that". Three causes, separated by
measurement rather than theory. Two are fixed here; the third is R24 and remains
Ben's ruling to make. Every path still ends `MODEL_STATUS=PRIOR_ONLY` and
`RELEASE_DECISION=DO_NOT_UPLOAD`.

#### Cause 1: nflverse's `roof` column is retrospective (fixed)

`games.csv` records `roof` only after the game is played. An unplayed game at a
retractable-roof venue therefore carries an empty cell, and both
`priors.resolve_weather_state` and `prior_review.decide_weather` read a blank as
"the schedule cannot resolve this roof" and demanded an `api.weather.gov`
capture, for a game played under a roof.

Measured on the frozen artifact of run `20260920T195344Z-week2-aft2`:

    2026 rows  177 outdoors, 52 dome, 2 closed, 41 BLANK
    2025 rows  193 outdoors, 50 dome, 42 closed, 0 blank
    blank-roof home teams  ATL 9, ARI 9, DAL 9, HOU 7, IND 7  (41 games)
    HOU week 1 'closed' (played), week 2+ BLANK (unplayed)   <- the mechanism

That is 15% of a season's games routed to a host this container cannot reach. On
the 2026-09-20 afternoon slate it was 2 of 5 games, SEA@ARI and WAS@DAL.

New `src/nfl_dfs/venues.py` resolves that one case. It counts the venue's own
completed home games by recorded roof state, out of the same frozen artifact the
run has already bound, and resolves a blank to `closed` only when the window is
unanimous and holds at least eight games. The basis names the counts and the
window: `DERIVED_FROM_VENUE_ROOF_HISTORY:retractable:closed=8/8:seasons=2025,2026`.

**The season window is load-bearing, and finding that out changed the design.**
The first version counted the whole artifact and resolved nothing, because over
all seasons ARI reads 144 `closed`, 21 `open` and 58 `outdoors`. Scoped to the
prior and current seasons every one of the five venues is unanimous `closed` (8
to 10 completed games); widened to four seasons every one of them shows an `open`
game. These roofs do open sometimes. The window is therefore the prior-plus-
current pair the rest of the prior package already treats as relevant, it is
declared in the basis string, and one `open` game in it stops the venue
resolving anything. This was caught by running against the real artifact instead
of trusting the two-season sample the fix was first written from.

Three bounds keep it a prior and not an invented observation: it is counted from
the bound artifact rather than hardcoded, one `open` game or fewer than eight
completed games resolves nothing, and an operator capture always outranks it.
`outdoors` is a recorded observation and is never overridden.

Replayed against the real artifact, the afternoon slate's captures required went
from **4 of 5 games to 2 of 5**:

    BLOCKED JAX@DEN   roof=outdoors  OPERATOR_CAPTURE_REQUIRED:outdoors
    clear   LV@LAC    roof=dome      SCHEDULE_ROOF_IS_AUTHORITATIVE:dome
    BLOCKED MIA@SF    roof=outdoors  OPERATOR_CAPTURE_REQUIRED:outdoors
    clear   SEA@ARI   roof=BLANK     DERIVED_FROM_VENUE_ROOF_HISTORY:...closed=8/8
    clear   WAS@DAL   roof=BLANK     DERIVED_FROM_VENUE_ROOF_HISTORY:...closed=8/8

The proposal artifact is now `nfl_prior_identity_proposal_v2`: `markets[]` gained
`venue_roof_history` and `venue_roof_history_seasons`. A v1 proposal still reads
correctly, with the keys absent and nothing resolved from them.

#### Cause 2: the probe only ran when somebody remembered it (fixed)

`api.weather.gov` is refused by this container's egress proxy (403 at CONNECT),
which is organization policy and not routable around. `scripts/session_probe.py`
has answered that in three seconds since 2026-09-20 and ran on neither lost
slate. `run-slate` now runs it at the head of every slate, writes
`data/runs/<run_id>/session_probe.json`, and prints the verdict to stderr.

It cannot fail a run: a crash, a timeout, a missing script or non-object output
all report `PROBE_UNAVAILABLE` rather than raising, and a blocked host is a
routing decision for the operator, never a refusal. `--no-session-probe` skips
it. The suite skips it through `NFL_DFS_SKIP_SESSION_PROBE=1`, set once in
`tests/conftest.py`, because the probe is a network call and
`.claude/rules/tests.md` says the suite makes none.

The probe also now prints the two `fetch_weather_captures.py` /
`make_classic_weather_evidence.py` commands when `api.weather.gov` is the blocked
host. That chain was already stdlib-only and already able to run on a machine
that reaches the host; it went unused on two lost slates because nothing named
it at the moment of the block. `docs/RUNBOOK.md` step 0 now carries the same
procedure with the six-hour freshness window, as operator work to do *before*
the session rather than inside it.

This is adjacent to chunk `X1` and does not close it. `X1` still owns the
per-host lines in `doctor`, the `PROHIBITED_HOSTS` exclusion test, and removing
the asserted-reachability prose from `docs/CLAUDE_CODE_SETUP.md`.

#### Cause 3: the gate blocks on a value that changes no number (R24, unchanged)

Re-verified in code, not taken from the docs. `weather_state` has 62 references
across seven modules and every one is plumbing: a `Literal`, a CSV column, a
membership check, a dataclass field, a display row.

    $ grep -rn "weather" src/nfl_dfs/*.py | grep -E "\*|multip|adjust|penal|factor"
    (no output)

No arithmetic reads it. A field that moves no projection could still stop the
engine producing any lineup at all. That is exactly R24, already filed and
`BLOCKED` on Ben's ruling, and it is not implemented here: it changes behaviour
that fails closed on purpose, and the ruling is his.

#### Verification

    sh ./nfl.sh test tests/test_venues.py -x --tb=short          14 passed
    sh ./nfl.sh test tests/test_session_probe_gate.py -x          9 passed
    sh ./nfl.sh test tests/test_priors_adapter.py                49 passed
    sh ./nfl.sh test tests/test_prior_review_profile.py          49 passed
    sh ./nfl.sh test tests/test_repo_boundaries.py               88 passed
    sh ./nfl.sh test tests/test_cowork.py tests/test_classic_prior_review.py \
        tests/test_classic_portfolio_c2.py \
        tests/test_cowork_rerun_regressions.py    71 passed, 1 skipped in 35.43s
    sh ./nfl.sh test                        1023 passed, 1 skipped in 137.46s
    sh ./nfl.sh doctor                      pass_status: true
    git diff --check                        clean
    python3 scripts/check_protected_paths.py  No protected path touched

The one skip is the expected Windows symlink-permission case
(`tests/test_cowork.py:115`, "Windows junction behavior"). 32 tests added; no
test was deleted, skipped or loosened. Two of them exercise
`freeze_prior_package` itself, because the freeze keeps its own `outdoor_games`
list, the `CLASSIC_WEATHER_SCOPE_AMBIGUOUS` check and the capture-expiry
accounting, and the resolver test alone would not have proved the resolution
reaches them. The mixed-history case still raises and still writes no output
directory. Three of my own basis-string assertions
failed when the season window was introduced and were updated to assert the
window, which is the change they exist to pin.

### 2026-09-20: session close-out — two pull requests merged, R24 recommended, X3 and H3 made runnable

No code changed. Documentation and ledgers only; every current path still ends
`MODEL_STATUS=PRIOR_ONLY` and `RELEASE_DECISION=DO_NOT_UPLOAD`. No run was
executed.

#### Merged

- **PR #32** (`ebf5797`), the protected list narrowed from twelve entries to
  three, on Ben's label and his explicit instruction to merge.
- **PR #27** (`baf19a0`), the X-track chunk briefs, brought current from
  `c6c73e7` after sitting eleven commits behind.

Both were open at the start of this stretch; neither is now. No pull request is
open against this repository.

#### A defect in the protected-path gate, filed as `H3`

PR #32 could not reach a green `protected-paths` check. The job passes
`PR_LABELS: ${{ toJSON(github.event.pull_request.labels.*.name) }}` and
`scripts/check_protected_paths.py:113` reads it. Both are the pull-request
**event payload**, which GitHub freezes at event time and replays verbatim on a
re-run, and `on: pull_request` without a `types:` list does not fire on
`labeled`. So a label applied after CI ran can never turn that check green.

Measured: `suite` and `boundaries` green on `f78390b`; `protected-paths` failed
at 18:29:44; Ben labelled at 18:36:55; the check stayed red. Both re-run calls
returned 403, the session token carrying Actions read-only, and a re-run would
have replayed the same label-free payload regardless.

This puts two rules in `.claude/rules/git-authority.md` in direct conflict:
never merge a protected-path pull request without the label, and never merge
with a red check. The merge went ahead on the label plus green `suite` and
`boundaries`, with the reason stated in the merge commit rather than glossed.
`H3` makes the label do what every document here says it does, and is `READY`
with both a brief and a session prompt.

#### Ledger and handoff gaps closed

- `docs/session-prompts/X3-execution-postmortem.md` written. `X3` was `READY`
  with a brief and no prompt, the only `READY` chunk in that state.
- `backlog.md` X1 queue row re-pinned from
  `docs/CLAUDE_CODE_SETUP.md:114-125` to `152-163` at `ebf5797`. The row had
  been stale since H2 rewrote that file, independently of the brief's own
  pointer, which PR #27 corrected.
- R24 gains a recorded recommendation. Ben asked for one in conversation; a
  recommendation that lives only in a conversation is the exact defect the
  X-track briefs were created to fix, so it is written into the stanza. R24
  remains `BLOCKED` on Ben and nothing is implemented against it.

#### An open gap recorded rather than fixed

Regenerating `state/repo-state.json` shows seven queue rows with `brief=None`.
`P1b`, `X0` and `X5` are `DONE` and `C3X` is `DEFERRED`, which is fine. But
`C4`, `C5` and the aggregate `Q2 to Q7, QC1` row are `BLOCKED` **without
briefs**. That is the same defect the X track just closed, still open on the C
and Q tracks: when those unblock, whoever runs them inherits a table cell. It is
outside every branch merged today and is recorded here so it is not rediscovered
a third time.

#### Verification

- Complete pinned suite, watched to completion on `.venv-linux`, twice: at the
  #27 merge `984 passed, 1 skipped in 160.94s (0:02:40)`, and again on this
  close-out `984 passed, 1 skipped in 155.21s (0:02:35)`.
- `python3 scripts/repo_state.py`: all five `READY` chunks (P0, X1, X3, P7, H3)
  bind to both a brief and a session prompt that exist on disk. Checked
  mechanically, not by eye.
- CI on PR #27 head `cf17421`: `suite`, `boundaries` and `protected-paths` all
  green; `suite` completed 19:12:26Z.
- CI on PR #32 head `f78390b`: `suite` and `boundaries` green,
  `protected-paths` red for the reason above.
- `sh ./nfl.sh doctor`: `pass_status: true`, Python 3.13.7, SQLite integrity ok.
- `git diff --check` clean; `backlog.md` and `changelog.md` both still LF.

A fresh container needed `sh ./nfl.sh setup` before the suite would run at all;
without it `nfl.sh test` exits 0 and prints `project environment is missing`,
which is not a suite result and must not be recorded as one. It was nearly
recorded as one here.

#### Left open

- `git push origin --delete claude/narrow-protected-paths` fails with
  `the remote end hung up unexpectedly` on every attempt through this session's
  proxy, and the GitHub MCP server exposes no delete-branch tool. That merged
  branch is still on the remote. Cosmetic; it needs the GitHub UI.
- R24 and the `C3X` and standings-corpus items remain `BLOCKED` on Ben.

### 2026-09-20: the protected list narrows from twelve entries to three

Ben's instruction: "remove the ben-review label requirement since I am not a
software engineer. I'd like Claude to be more autonomous and use its
judgement." This implements it, with one disagreement stated and kept.

No engine module, contract, `config/` file or evidence gate changed. Every path
still ends `MODEL_STATUS=PRIOR_ONLY` and `RELEASE_DECISION=DO_NOT_UPLOAD`.

#### What came off the list, and why he was right

`src/nfl_dfs/release.py`, `certification.py`, `preflight.py`, `evidence.py`,
`sources.py`, `config/evidence_policy.json`, `config/metric_registry_*.json`,
`.github/workflows/*.yml` and `.claude/rules/*.md`. Nine of twelve.

The gate asked a non-engineer to review a diff to an evidence module. That
produces a signature, not a check. The real gate on that code is CI,
`tests/test_repo_boundaries.py` and the pinned suite, and those are stronger
than a signature. The label had become a queue Ben serviced without being able
to add signal to it, which is the definition of a bottleneck.

The rules directory coming off means **Claude may now write, edit and merge its
own behavioural rules without asking.** That is deliberate and it is bounded:
`CLAUDE.md` stays on the list, so a rule file can refine how Claude works but
cannot loosen a permanent boundary, because the file stating those boundaries is
one Claude cannot merge alone. A rule change that would in effect relax a
boundary belongs in `CLAUDE.md`, where it gets the label.

#### What stayed, and the disagreement

`CLAUDE.md`, `.github/protected-paths.txt`, `.claude/settings.json`.

Ben asked whether to drop all three. The recommendation was to keep them and he
took it. The reason is not caution in the abstract and not code review: it is
that **Claude must not be able to quietly change what Claude is not allowed to
do.** Reviewing these three is one plain-English question — do I want the
machine to be allowed to do this — which is the judgement he is qualified to
make and the only one on the old list that was ever load-bearing.

The concrete case is from the same day. A session three messages into being told
to ship a portfolio could have produced one in ninety seconds by typing twelve
`api.weather.gov` observations it had not made. What stopped it was a sentence
in `CLAUDE.md` it treated as binding. A self-editable boundary is a suggestion.

Two harness refusals landed on this work before the permission was granted, both
classifying it as self-modification: one on running the tests that validate the
narrowed list, one on editing `.claude/rules/git-authority.md`. The partial
state was reverted rather than shipped, because a list saying three while the
governing rule said twelve is worse than either. Recorded because a second,
independent system reaching the same conclusion is evidence worth keeping.

#### Changed

- `.github/protected-paths.txt`: twelve entries to three, with the reasoning
  inline so the next reader does not have to reconstruct it.
- `tests/test_repo_boundaries.py`: the three assertions that required
  `release.py`, `evidence_policy.json` and `.claude/rules/ledger.md` to be
  flagged are **inverted, not deleted**, so the narrowing is pinned in both
  directions. A new test,
  `test_the_protected_list_stays_short_enough_to_actually_read`, pins the exact
  three-entry set so a fourth has to be justified in the same commit rather than
  accreting quietly. Per `.claude/rules/tests.md`, the changed test is named
  here with its reason ahead of the change.
- `.claude/rules/git-authority.md` § The protected list: rewritten to name the
  three, say what came off and why, and state plainly that Claude may now merge
  its own rule changes and what bounds that.
- `CLAUDE.md` step 8, `backlog.md` tracker protocol,
  `docs/CLAUDE_CODE_SETUP.md` § Where the gate lives, and
  `docs/session-prompts/P7-current-role-depth.md` close-out: all four described
  the old list and now name the three.

#### Verification

- `tests/test_repo_boundaries.py`: `88 passed in 1.16s`, up one for the new
  pinning test.
- Full suite, watched to completion: `984 passed, 1 skipped in 156.97s
  (0:02:36)`, recorded with `scripts/record_verify.py --from-log`. Exactly one
  above the `983 passed, 1 skipped` baseline, which is the pinning test added
  here.
- `scripts/check_protected_paths.py` is expected to exit 1 on this branch naming
  `CLAUDE.md` and `.github/protected-paths.txt`, which is the gate working on
  its own narrowing. This pull request carries `ben-review` and Ben merges it.
- `git diff --check` clean; ledgers LF.

### 2026-09-20: R25 ruled, and P7 goes READY

Ben ruled on three open items in one message: merge PR #30, approve R25, and
narrow the protected-path list. This entry covers the R25 ruling. The narrowing
is a separate pull request because it touches protected paths and therefore
needs his label one last time.

No engine module, contract, `config/` file or evidence gate changed here. This
is `backlog.md` and two `docs/` files: a ruling recorded and a chunk unblocked.

#### R25: APPROVED

**Promote a backup to effective rank 1 when the depth-chart starter is flagged
`OUT` by the bound salary bytes.** This replaces the
`QB_DEPTH_STARTER_NOT_SELECTABLE` refusal at `qb_depth_roles.py:382-386`.

The measurement the ruling rests on, restated because it is the whole argument:
the refusal tells the operator to "refresh the depth chart after the inactive or
exclusion change", and the last `depth_charts_2026.csv` snapshot published on
Week 1 Sunday was 08:42 ET and on Week 2 Sunday 08:14 ET, while official
inactives publish about 11:30 ET for a 13:00 lock. No depth chart is ever
published inside the window. The refusal named a remedy that cannot be
performed, which `CLAUDE.md` classes as a defect rather than a constraint, the
same shape as R21.

This is not an evidence gate being weakened. The replacement is stricter in the
direction that matters: it re-derives availability from the bound salary bytes
rather than trusting the supplied package. Bounds, binding on P7:

- Availability re-derived from the bound salary bytes every run, exactly as
  `freeze_prior_package` does at `priors.py:2139`. A supplied depth package can
  never widen it.
- Nobody becomes selectable who was not already. Promotion changes which
  available person holds a role; it never adds a person to the pool.
- The identity gate's auto-accept rule is untouched.
- Every promotion is named in the run record and in the handoff.

On the 2026-09-20 snapshot the ruling promotes Carson Wentz (MIN) and Drew Lock
(SEA) to effective QB1, both correct on the day, and surfaces Michael Mayer
(LV TE 2→1), Xavier Hutchinson (HOU WR 2→1) and Rashod Bateman (BAL WR 2→1).

#### Changed

- `backlog.md`: the R25 stanza records the ruling and makes its bounds binding
  rather than proposed; `P7` moves `BLOCKED` to `READY` in the Queue table and
  the chunk index.
- `docs/session-prompts/P7-current-role-depth.md`: the "do not begin until Ben
  has ruled" stop is replaced by the ruling and its bounds, so the prompt is
  paste-ready.
- `docs/chunks/P7-current-role-depth.md`: the conditional in § Scope becomes
  unconditional; § Hand-back now asks the closing session to name the promotions
  its acceptance snapshot produced.

#### Verification

- Full suite, watched to completion: `983 passed, 1 skipped in 158.15s
  (0:02:38)`, recorded with `scripts/record_verify.py --from-log`. Unchanged
  count against the `983 passed, 1 skipped` baseline, which is the expectation:
  no code changed.
- `scripts/check_protected_paths.py` exits 0; `git diff --check` clean; ledgers
  LF.

### 2026-09-20: X5 — the Classic fallback path becomes real, correct and findable

Second post-mortem tranche on the lost Week 2 slate. No engine module, contract,
`config/` file or evidence gate changed; `scripts/**`, `docs/**` and `tests/**`
only. `MODEL_STATUS=PRIOR_ONLY` and `RELEASE_DECISION=DO_NOT_UPLOAD` throughout.

The first tranche fixed the network half of "did not look at what was already
there". This fixes the repository half, which turned out to be worse.

#### What the inventory found

- **The fallback path existed and was invisible.**
  `scripts/build_classic_portfolio.py`, `scripts/qa_classic_portfolio.py` and
  `scripts/write_dk_entries.py` appear in
  `docs/CLASSIC_C4_RETROSPECTIVE_2026-09-13.md` and in no operating document at
  all: not `docs/RUNBOOK.md`, not `docs/OPERATOR_GUIDE.md`, not the
  `nfl-classic-lineups` skill. The Week 1 session solved "engine blocked, ship
  anyway" and wrote it into a ~900-line file nothing tells the next operator to
  open. That is the structural cause of finding 3 in the entry below.
- **The pipeline was broken in the middle.** The builder emitted
  `"assignments_by_entry_id": {}` as a literal empty dict while
  `write_dk_entries.py` reads exactly that key and iterates it. There was no
  entry-ID assignment step anywhere in `scripts/`, so both live slates filled
  the mapping by hand.
- **The QA gate would have caught the Week 2 portfolio and was never run.** Its
  Tier 2 already scores bring-back rate against a suggested 70% floor; the
  shipped portfolio was 12/18 = 67%.
- **Its backup-quarterback check was dead code.** It looked for a second
  `Position == "QB"` on the same team, which legal DK Classic cannot produce
  (FLEX is RB/WR/TE only) and which the `exactly one QB` check already rejects.
  Nothing verified that the rostered quarterback was his team's starter — the
  exact hole the Wentz miss went through.
- **`qb_vs_opposing_dst` was declared and never appended to**, so it printed 0
  on every run since it was written. In a nine-man lineup with one QB and one
  DST it is the same relation as `dst_vs_own_qb`.
- **Three slate-specific tables were hardcoded** in the builder: `ITT` (24
  teams), `OWN` (31 names) and `BOOST` (7 names), all literal 2026-09-13 values
  including role boosts keyed to Week 1 absences. Retyping them weekly is where
  a mistake gets made; on 2026-09-20 they were patched with a regex that
  silently removed eight lines of code.
- **None of the three scripts had a single test.**

#### Changed

- `docs/RUNBOOK.md`: new **step 0** in the binding running order — run
  `scripts/session_probe.py --salaries <csv>` before anything else, with what
  exit 2 means and what to do about it. A matching bullet in `## Prerequisites`
  beside the existing `doctor` line. A new section, **"The Classic fallback
  path: a blocked engine is not a blocked slate"**, naming the four-script chain
  and making `qa_classic_portfolio.py` a required pre-handoff step with Tier 2
  shown. The existing "Do not claim NWS is universally unreachable: test the
  current session" is generalised to every source, with the depth-chart miss as
  the worked example.
- `scripts/build_classic_portfolio.py`: argparse; emits a populated
  `assignments_by_entry_id` from the DKEntries template in template order;
  `--slate-context` replaces the three hardcoded tables and defaults to empty
  rather than to last week; `--lineups`, `--seed`, `--min-salary`,
  `--max-exposure`, `--max-overlap` and `--require-bringback` are flags; records
  what it landed on in a `construction` block. The construction algorithm is
  unchanged — it ran on two live slates and was not touched.
- `scripts/qa_classic_portfolio.py`: `--backup-pairs STARTER>BACKUP` replaces
  the dead check; byte fidelity against the template, duplicate-lineup
  detection and entry-ID coverage ported from the Showdown twin; `--min-salary`,
  `--max-overlap` and `--max-exposure` enforced when given; exit 2 on an
  enforcement defect, 1 on a legality failure, 0 on pass; `qb_vs_opposing_dst`
  removed rather than faked; absent ownership is now stated as a named gap.
- `scripts/make_slate_context.py`, new: derives implied team totals from the
  run's own frozen `nfldata` `games.csv` (`total_line`, `spread_line`). It never
  invents ownership or a role boost, because no approved source carries either.
- `backlog.md`: `X5` (this work) and `P7` added to the Queue; `P7` chunk stanza
  and the new `R25` ruling proposal; the `### P1b` stanza that was duplicated
  verbatim at two places is reduced to the one in the P-series index.
- `docs/chunks/P7-current-role-depth.md` and
  `docs/session-prompts/P7-current-role-depth.md`, new.

#### Verification

- **End-to-end on the real 2026-09-20 slate, which is the honest test.** The
  rewired chain — `make_slate_context.py` → `build_classic_portfolio.py`
  (`--entries --slate-context --min-salary 47500 --require-bringback`) →
  `write_dk_entries.py` — reproduced the portfolio that had been assembled by
  hand **byte for byte**:
  `de5a6d4d348e55ae1cccdc7eb27a35e0dab529ffa0c760ef088256a391b7bddc`. That one
  hash verifies the entry-ID mapping, the derived slate context and determinism
  under the seed at once.
- Implied totals derived for all 26 teams on the slate, matching the values
  computed by hand during the slate.
- `qa_classic_portfolio.py` on that portfolio: 0 legality failures, 0
  enforcement defects, bring-back 18/18, anti-correlation 0/0, top-3 union
  13/18, max overlap 4, exit 0.
- The same gate run against the portfolio actually shipped first on 2026-09-20
  returns exit 1 and names all four backup-quarterback starts (Mac Jones,
  Carson Wentz, Tyler Huntley, Quinn Ewers) plus eight lineups under a 47,500
  floor. It would have blocked that handoff.
- New tests: `tests/test_make_slate_context.py` (8),
  `tests/test_build_classic_portfolio.py` (12),
  `tests/test_qa_classic_portfolio.py` (19),
  `tests/test_write_dk_entries.py` (8).
- Full suite, watched to completion: `983 passed, 1 skipped in 165.36s
  (0:02:45)`, recorded with `scripts/record_verify.py --from-log`. Exactly 47
  above the `936 passed, 1 skipped` baseline, matching 8 + 12 + 19 + 8 added
  here. The one skip remains the expected Windows symlink-permission case.
- `scripts/check_protected_paths.py`: `No protected path touched (0 changed)`.
  `git diff --check` clean; `backlog.md` and `changelog.md` remain LF.

### 2026-09-20: a pre-run capability probe, and a weather capture that can run elsewhere

Post-mortem work on the lost Week 2 Classic slate recorded in the entry below.
Two new scripts and their tests. No engine module, contract, `config/` file or
evidence gate changed, and no gate was relaxed: both additions make a gate
easier to *clear*, never easier to *pass*.

#### What actually cost the slate

The egress block was the constraint. These were the process failures on top of
it, recorded because they are the reusable part:

1. **Session capability was never established first.** The block was found by
   walking into it about twenty minutes in. Nothing in the repository answered
   "can this session reach the hosts its gates need", and
   `src/nfl_dfs/preflight.py` answers a different question: it is a pre-upload
   check on a built package, not a pre-run check on session capability.
2. **The lock clock was estimated rather than measured.** After one real
   reading at 11:05 ET, elapsed time was extrapolated and drifted about 45
   minutes, and the drifted figure was reported to Ben as fact. Every clock
   statement must come from a measurement taken at that moment.
3. **`scripts/build_classic_portfolio.py` was not found until far too late.**
   It is the construction layer that shipped the Week 1 portfolio when the C2
   solver failed, it is named for the job, and it has a retrospective attached.
   Survey `scripts/` before concluding a path does not exist.
4. **A structural defect was reported before it was verified.** Three of the six
   identity blockers were called genuinely absent from nflverse; a later grep
   found all six under name variants. See F8 in the entry below.

#### The design flaw the loss exposed

`weather_state` reaches no arithmetic. It is written to a row in
`projection.py:651` and validated in `opportunity.py:188`, and nothing else
reads it (R23, open). Yet a missing weather enum has total veto power over
output: every route to lineups runs through the freeze, the freeze requires the
enum for each non-dome game, and `priors.resolve_weather_state` raises.

So a field that moves no number can stop the engine producing anything. The
gate is right to block release, which is `DO_NOT_UPLOAD` on every path anyway.
It should not also block construction. A proposal to separate the two is filed
in `backlog.md` and is **not** implemented here, because it changes deliberate
fail-closed behaviour and is Ben's ruling to make.

#### Added

- **`scripts/session_probe.py`.** Standard library only, imports nothing from
  `nfl_dfs`, runs in a cold container in about three seconds. Reads
  `ALLOWED_HOSTS` out of `src/nfl_dfs/sources.py` by parsing the source rather
  than importing it, probes every host concurrently, and separates an egress
  policy refusal from a TLS misconfiguration from a dead host. With
  `--salaries` it also reports slate shape and the measured minutes to lock,
  taking the lock from the **earliest** kickoff. Exit 2 means a full run cannot
  complete in this session.
  Run against the lost slate it returns `CANNOT_COMPLETE_A_RUN`, naming
  `api.weather.gov` and the gate it feeds, in three seconds.
- **`scripts/fetch_weather_captures.py`.** Companion to
  `make_classic_weather_evidence.py`, which formats captures but never fetches.
  This fetches and never judges. Standard library only, so it runs on any
  machine that can reach the host: the capture does not have to happen in the
  session that builds, which is what makes a blocked build session survivable.
  Carries coordinates for all 32 DraftKings teams, prefers the already-checked
  gridpoints in `scripts/nws_gridpoints.json`, reports the city NWS returned for
  every point it resolves, and writes `REPLACE_ME` for retractable roofs rather
  than guessing whether a roof is open. A fetch failure is a named stop.

#### Verification

- `tests/test_session_probe.py`: 9 tests. Asserts the parsed host list equals
  the real `ALLOWED_HOSTS` so the two cannot drift, that every allowlisted host
  has a declared role, that `api.weather.gov` is required for Classic, that a
  proxy 403 reports as `EGRESS_BLOCKED` rather than a dead host, and that the
  lock is the earliest kickoff.
- `tests/test_fetch_weather_captures.py`: 10 tests. Asserts coverage of all 32
  DraftKings teams, that the home team comes from the `AWAY@HOME` matchup and
  not the whole `Game Info` cell, that retractables are flagged for a human,
  that the enum has no `UNKNOWN` member, and that a fetch failure raises with
  "Never invent a value" in the message.
- Both files together: `19 passed in 0.30s`.
- Full suite, watched to completion: `936 passed, 1 skipped in 155.10s
  (0:02:35)`, recorded with `scripts/record_verify.py --from-log`. Exactly 19
  above the `917 passed, 1 skipped` baseline, which is the count added here.
  The one skip remains the expected Windows symlink-permission case.
- `scripts/check_protected_paths.py` exits 0; `git diff --check` clean.

### 2026-09-20: Week 2 Classic slate attempt, stopped by an unreachable weather host

Second live Classic attempt, and the first run of any kind from a cloud session
whose egress policy blocks `api.weather.gov`. No portfolio was produced. No
engine module, contract, `config/` file or evidence gate was changed; the
findings below are recorded, not acted on. `MODEL_STATUS=PRIOR_ONLY` and
`RELEASE_DECISION=DO_NOT_UPLOAD` throughout.

#### The slate and the run

- DraftKings Classic main slate, 13 games, 670 salary rows, 26 teams. Earliest
  kickoff `CAR@ATL 09/20/2026 01:00PM ET`, which is the lock. `DKEntries`
  carried exactly 18 reserved Entry IDs, all nine roster cells blank, spread
  across 12 contests from `$0` to `$1`.
- Input hashes: salary
  `d0adb9dee552e89967ef6c51b60694f2dcb325969377a605dea5848c2972ee78`, entries
  `6b3292ee34b4b23bf0efef439c007323fa8b1b52d3ba921d68973a65e3f091d7`.
- `run-slate --profile prior_review --build-priors`, `run_id`
  `20260920T150819Z-week2`. Reached `PRIOR_REVIEW_IDENTITY_BLOCKED` with
  `FILE_VALID=false`, `EVIDENCE_STATE=UNKNOWN`, `MODEL_STATUS=PRIOR_ONLY`,
  `RELEASE_DECISION=DO_NOT_UPLOAD` and 36 blockers: 24 weather (12 games times
  two codes), 6 identity, and 6 belonging to the certification path the
  prior-only chain never reaches.
- The nflverse prior build itself succeeded. Seven artifacts captured from
  `raw.githubusercontent.com` and the GitHub release-asset hop, hash-bound,
  license-decided, at `2026-09-20T15:08:20Z` and after.

#### Finding F7: `api.weather.gov` is blocked by this session's egress policy

The host answers `403` to `CONNECT` at the agent proxy. Confirmed three ways:
`curl` returned `CONNECT tunnel failed, response 403`; the proxy's own
`recentRelayFailures` recorded `connect_rejected … api.weather.gov:443`; and
`WebFetch` returned `EGRESS_BLOCKED`. `list_environments` returns exactly one
environment, so a sibling session cannot route around it.

This contradicts the note in `docs/CLAUDE_CODE_SETUP.md` § Known environment
facts, measured 2026-09-17, which records `api.weather.gov` answering HTTP 200
from a container. Both measurements are recorded rather than reconciled: the
2026-09-17 one is not re-run here, and which of policy, environment or date
changed is not established. `github.com`, `raw.githubusercontent.com` and
`api.github.com` all remain reachable, so the prior build is unaffected.

Every route to a Classic portfolio was tested and each one stops at the same
gate:

1. `run-slate --profile prior_review` stops at `WEATHER`.
2. `priors-freeze` with a scalar `--weather-state` stops at
   `WEATHER_STATE_REQUIRED:roof=blank`, and would in any case be refused by
   `CLASSIC_WEATHER_SCOPE_AMBIGUOUS`, since this slate has 12 non-dome games
   and one scalar cannot bind to more than one.
3. Per-game evidence needs `api.weather.gov` captures, which is F7.
4. The frozen `nfldata` `games.csv` carries `temp` and `wind` columns, but both
   are empty for every 2026-09-20 row; nfldata populates them after kickoff.
   `total_line` and `spread_line` are populated.
5. `scripts/build_classic_portfolio.py` consumes `scores.json`, which requires
   a frozen prior package, which requires 1 or 2.

`priors.resolve_weather_state` fails closed here by explicit design; its
docstring states the intent as "rather than invent a value". The one remaining
door, `_weather_evidence_basis` returning `OPERATOR_SUPPLIED_UNATTRIBUTED` for a
state supplied with no source URI, requires stating a weather enum nobody
observed. It was not used. Twelve invented observations would have produced a
portfolio in about ninety seconds and made every hash in the package a false
claim.

#### Finding F8: the identity proposer matches display name only, and it is brittle

All six identity blockers resolved to real nflverse people under spelling
variants, verified against the frozen artifacts by `gsis_id`, position and 2025
game rows. None was a missing person:

| DK name | DK ID | nflverse name | gsis_id | variant |
|---|---|---|---|---|
| Matt Hibner | 44133630 | Matthew Hibner | `00-0040879` | full legal name |
| Scotty Miller | 44133214 | Scott Miller | `00-0035298` | nickname |
| Mitch Tinsley | 44133436 | Mitchell Tinsley | `00-0038839` | full legal name |
| Audric Estime | 44132872 | Audric Estimé | `00-0039373` | diacritic |
| Hollywood Brown | 44133108 | Marquise Brown | `00-0035662` | known alias |
| Nick Singleton | 44132762 | Nicholas Singleton | `00-0040886` | full legal name |

`00-0035298` is a judgment call and is recorded as one: nflverse carries two
`Scott Miller` WRs, and the other was born 1968. The 2025 PIT game rows
distinguish them.

Two mechanical facts came out of the attempt. `--exclude` does not clear the
identity gate: `apply_identity_gate` runs over every proposal from
`priors-propose` (`prior_review.py:1673`) and operator exclusions never reach
it. `EXCLUDE_UNRESOLVED_UNAVAILABLE` does not help either, because
`priors.py:2139` re-derives availability from the bound salary bytes and
refuses the token for anyone still selectable; five of the six carried a blank
DraftKings status.

A reviewed crosswalk covering all 670 rows with these six set to `ACCEPT` was
produced and hashed
(`17452ea562e243b10597c21ff8bddad99380c6bd814b2b97ee19c76ccd3fbe4a`). It was
never frozen, because the freeze stops at F7.

#### Verification

- `run-slate` exit 0, `run_id` `20260920T150819Z-week2`, report at
  `outputs/20260920T150819Z-week2/cowork_run.json`, review workbook
  `59d39383badce3f6ec950db0a27240e862e06f3da6b9323354b70a7da5b64329`.
- `priors-freeze` with the reviewed crosswalk: `PriorsBuildError`,
  `WEATHER_STATE_REQUIRED:roof=blank`, `stage=CLI_FAILED`,
  `RELEASE_DECISION=DO_NOT_UPLOAD`.
- Six `gsis_id` values checked present in the frozen artifacts and checked for
  collisions against the 664 already-accepted rows; zero collisions.
- Full suite on this branch: `917 passed, 1 skipped in 160.22s (0:02:40)`,
  recorded with `scripts/record_verify.py --from-log`. Matches the 2026-09-20
  baseline of `917 passed, 1 skipped`; the one skip is the expected Windows
  symlink-permission case.
- No test was written, changed, skipped or weakened. Only `changelog.md` and
  `backlog.md` changed, so the suite result confirms the branch is clean rather
  than exercising anything new.
### 2026-09-20: the X-track chunks get briefs, so the audit survives the session

No code changed. Documentation, ledgers and one state file only; every current
path still ends `MODEL_STATUS=PRIOR_ONLY` and
`RELEASE_DECISION=DO_NOT_UPLOAD`. No run was executed.

#### The gap this closes

`X1`, `X2`, `X3` and `X4` existed only as one-line rows in the `backlog.md`
Queue table. `scripts/repo_state.py` reported `brief=None` for all four. Every
fact behind them — the 403-at-CONNECT measurement, the stub-weather MCP finding,
the candidate-bank reasoning, the three transport options and why (A) is
recommended — lived in one session's context and in a plan file under
`/root/.claude/plans/`, which is outside the repository and dies with its
container. A fresh cloud session told "do X1" would have had a single table cell.

This is the same defect class as the two found on 2026-09-19 (a status written
where the deriving script cannot read it; a flag count that meant "mentioned"
rather than "open"): work recorded somewhere the next session does not look.

#### Added

- `docs/chunks/X1-egress-probe.md`. Carries finding F2 with the corrected
  location: `docs/CLAUDE_CODE_SETUP.md` § "Known environment facts" is lines
  139-150 as of `c6c73e7`, not 114-125 as the queue row said — H2 rewrote that
  file. Also records that the same section's suite line
  (`1 failed, 735 passed, 1 skipped in 155.56s`) has been wrong since #19
  merged, which is a second instance of the same defect.
- `docs/chunks/X2-standings-corpus-transport.md`. The three options (A) private
  release assets, (B) commit the corpus, (C) Windows-only, stated with their
  real costs so the decision does not have to be reconstructed.
- `docs/chunks/X3-execution-postmortem.md`. Carries F7 and F8, and the measured
  constraint that `PreCompact` cannot inject text surviving into the compacted
  context, so the next session designs around it instead of rediscovering it.
- `docs/chunks/X4-greenfield-spec.md`. Carries F1–F9 with disposition, including
  the three findings no chunk absorbed: F3 (the candidate bank is generated by
  the same objective that selects from it), F4 (three dead candidate keys in
  `config/runtime.json`), F5 (the `build` path has simulation and is
  unreachable; `run-slate` runs and has no distribution).
- `docs/session-prompts/X1-egress-probe.md`, the paste-in prompt for the next
  session.

#### Changed

- `backlog.md`: the chunk index gains `X1`–`X4` entries naming their briefs.
  `scripts/repo_state.py` now binds a brief to every live chunk; it reported
  `brief=None` for all four X rows before this change.
- `state/claims.json`: cleared the H2 claim from 2026-09-17T18:39:47Z. Its
  branch `claude/h2-multi-instance-orientation` is merged (`0caec47`) and the
  claim was six hours stale and being reported at every session start.

#### Verification

- `python3 scripts/repo_state.py` then reading `state/repo-state.json`:
  `X1 READY brief=docs/chunks/X1-egress-probe.md`,
  `X2 BLOCKED brief=docs/chunks/X2-standings-corpus-transport.md`,
  `X3 READY brief=docs/chunks/X3-execution-postmortem.md`,
  `X4 BLOCKED brief=docs/chunks/X4-greenfield-spec.md`. No `brief=None` on a
  live chunk.
- The stale-claim line is gone from the session-start digest.
- Open `[BEN:]` flags remain 4; no flag was added or removed by this entry.

#### Brought current on 2026-09-20 before merge

The branch was opened at `c6c73e7` and sat eleven commits behind. `origin/main`
was merged in; `backlog.md` and `changelog.md` both conflicted and both were
additive on each side, so both sides were kept rather than either discarded. In
`backlog.md` the chunk index now reads P6, P7, X1-X4, then the R25 ruling. In
`changelog.md` this entry sits after the five entries `main` added later the
same day, since the file is newest first and this branch was opened at 14:58Z.

Four claims in the X-track briefs went stale between `c6c73e7` and the merge,
all from the protected list narrowing to three entries that afternoon. They were
true when written and are corrected here rather than left to mislead the session
that runs the chunk:

- `docs/chunks/X1-egress-probe.md` said `sources.py` is a protected path needing
  `ben-review`. It came off the list; it now merges on green. Its pointer at
  `docs/CLAUDE_CODE_SETUP.md` § Known environment facts is re-pinned from lines
  139-150 at `c6c73e7` to 152-163 at `ebf5797`. Both defects that section is
  cited for are still present, so the chunk's premise is unchanged: the stale
  `1 failed, 735 passed, 1 skipped in 155.56s` line, and the claim that
  `api.weather.gov` answers HTTP 200, which this session measured as 403 at the
  agent proxy.
- `docs/chunks/X2-standings-corpus-transport.md` costed option (A) partly on
  `sources.py` being protected. That cost is gone; the remaining cost, new
  authenticated-retrieval surface in the allowlist module, is unchanged.
- `docs/chunks/X3-execution-postmortem.md` said a rule file and `CLAUDE.md` are
  both protected. Only `CLAUDE.md` is now, so the `.claude/rules/` route merges
  on green and only the `CLAUDE.md` route carries the label. The `backlog.md`
  X3 entry said the same thing and is corrected with it.
- `docs/session-prompts/X1-egress-probe.md` carried the same `sources.py` claim.

No brief's scope, acceptance or constraints changed. Nothing was added to any
chunk and no status moved.

Verified after the merge, on `.venv-linux` in a rebuilt container:

- Complete pinned suite: `984 passed, 1 skipped in 160.94s (0:02:40)`. Identical
  pass count to `main` at `ebf5797`, which is the expected result for a branch
  that changes no code.
- `sh ./nfl.sh doctor`: `pass_status: true`, Python 3.13.7, SQLite integrity ok.
- `python3 scripts/repo_state.py`: `X1`, `X2`, `X3` and `X4` each bind to their
  brief; `READY` is unchanged at P0, X1, X3, P7. Seven queue rows still report
  `brief=None`, none of them this branch's: `P1b`, `X0` and `X5` are `DONE`,
  `C3X` is `DEFERRED`, and `C4`, `C5` and the aggregate `Q2 to Q7, QC1` row are
  `BLOCKED` without briefs. That last group is a live gap of the same kind this
  entry closed for the X track, and it is recorded here rather than fixed,
  because it is outside this branch.
- `git diff --check` clean; `backlog.md` and `changelog.md` both still LF.

### 2026-09-20: PR #18 and PR #19 merged, and the fresh-container suite is repaired

No engine module, contract, `config/` file or evidence gate changed in this
entry's own work; every current path still ends `MODEL_STATUS=PRIOR_ONLY` and
`RELEASE_DECISION=DO_NOT_UPLOAD`. No run was executed.

#### Changed

- **PR #18** (`4ee1654`) merged: the H2 session prompt,
  `docs/session-prompts/H2-multi-instance-orientation.md`, one added file,
  no protected path, clean against `main`, all three checks green.
- **PR #19** (`0caec47`) merged carrying Ben's `ben-review` label. It touches
  three protected paths (`.claude/rules/git-authority.md`,
  `.claude/settings.json`, `.github/workflows/ci.yml`), which is why the label
  is on it. Ben applied the label and directed the merge.
- #19 was branched from `44bff83` and `main` had moved to `b21351d`, so
  `origin/main` was merged into its head first (`1f3aafd`). One conflict, in
  `changelog.md`: both sides had appended under `## Unreleased`. Resolved by
  date order, newest first, with the 2026-09-17 H2 entry placed above the
  2026-09-17 slate-run entry. `scripts/repo_state.py` auto-merged: the
  fetch-before-deriving work from #19 and the `ben_flags()` scoping from
  `abb1f3e` are both present and do not overlap.
- `backlog.md`: `X1` and `X3` move `BLOCKED` to `READY`. Operator item 1a is
  closed and its marker written out, so the open-flag count drops from 5 to 4.

#### Verification

- Full suite on the merged head, with the `NFL_DFS_PYTEST_TMP` workaround:
  `917 passed, 1 skipped in 152.15s (0:02:32)`.
- Full suite on the same head **without** the workaround, which is what #19's
  `nfl.sh` `mkdir -p` fix exists to make possible:
  `917 passed, 1 skipped in 152.82s (0:02:32)`. The fresh-container failure
  recorded on 2026-09-19 (`2 failed, 226 passed, 1 skipped, 562 errors`) does
  not reproduce. Finding F6 is closed.
- `doctor`: `"pass_status": true`, python 3.13.7, sqlite integrity `ok`,
  journal mode WAL, workspace probe `REMOVED`.
- `git diff --check` clean.
- `scripts/check_protected_paths.py` exits 1 locally on #19's branch, naming
  the three protected files, which is correct: the local script cannot see the
  label. The CI `protected-paths` job, which does read it, passed on `1f3aafd`.
- CI on `1f3aafd`: `suite`, `boundaries` and `protected-paths` all green
  (run 35468597692).

#### Test corrected, named before the fix

`tests/test_backlog_queue.py::test_the_blockers_ben_actually_owns_are_flagged`
asserted that `#19` appears in the open-flag text. That was true on 2026-09-19
and became false the moment #19 merged, so the test failed on a ledger that is
now correct. The test was wrong, not the ledger. It is narrowed to the one
operator blocker that still gates a chunk, the standings corpus choice behind
`X2` and `P0`, and renamed
`test_the_blocker_ben_actually_owns_is_flagged`. It was not deleted, skipped or
loosened past that: it still fails if the standings flag disappears while `X2`
is `BLOCKED`, which is the invariant worth keeping. A named pull-request number
does not belong in a standing assertion; the thing it was really guarding is
that a chunk `BLOCKED` on Ben has a visible flag.

#### Left open

- `git push origin --delete` for the two merged branches returned HTTP 403
  through the session's git proxy, so `claude/h2-multi-instance-orientation`
  and `claude/multi-instance-orientation` still exist on the remote. Both are
  fully merged into `main`; deleting them is cosmetic.
- `state/claims.json` carries one stale claim, reclaimable.

### 2026-09-19: the operator-flag count said 10 when 3 were open

Immediate follow-on from the tracker consolidation below, found by reading the
digest that consolidation had just made authoritative. Same class of defect: a
derived number that was wrong and that nothing was checking.

`ben_flags()` scanned `changelog.md` and `IMPLEMENTATION_STATUS.md` as well as
`backlog.md`. Those two are the historical record — they quote flags that were
raised, ruled on and closed — and worse, every sentence *about* a flag matched
as if it were one. The list contained entries whose whole text was `'] flags'`
and `']\` question:`. It reported 10 open when 3 were genuinely open.

A count wrong in the direction of more is worse than no count: the two blockers
that gate every remaining chunk were sitting in a list of ten, most of it noise.

**Changed**

- `scripts/repo_state.py:ben_flags()` scans `backlog.md` and the live chunk
  briefs only. `.claude/rules/ledger.md` says a flag lives in `backlog.md` and
  is listed again in the handoff, so those are the only places an *open* one
  can be. The docstring records why, at length, because the next person to
  "fix" the count by widening the scan will reintroduce it.
- `docs/chunks/P1-salary-divergence-role-evidence.md`: its gate-semantics flag
  is marked **RULED 2026-09-19: hard stop** and the literal marker removed. It
  was closed when Ben ruled; leaving the marker kept it in the open count.
  Writing the marker out in full even to say it is closed re-raises it, which
  is noted in the brief so the next edit does not undo this.
- `state/claims.json` back to `{"claims": []}`. The `P1` claim was stale and
  `P1` is merged, so the digest was reporting a reclaimable claim on finished
  work.

Open flags: **10 → 5**, all five in `backlog.md` and all genuinely open (two are
the same `C3X` ruling referenced twice, which is real cross-referencing).

**Added: 3 tests in `tests/test_backlog_queue.py`** (now 10 there). The count
must mean "open", not "mentioned": no flag may come from `changelog.md` or
`IMPLEMENTATION_STATUS.md`; every reported flag must have real text rather than
a stray bracket; and the two blockers Ben actually owns — merge #18/#19, pick
where the standings corpus lives — must be present, so they cannot quietly stop
being visible on startup.

**Verification**

```
full suite              838 passed, 1 skipped in 151.93s (0:02:31), exit 0
before this change      835 passed, 1 skipped in 168.64s
repo_state.py           21 queue rows, READY: P0, 5 [BEN:] flags, 0 claims
doctor                  pass_status true
compileall src scripts  clean
git diff --check        clean
check_protected_paths   No protected path touched (0 changed)
```

### 2026-09-19: one tracker, and a test that keeps it one

Ben's point, and he was right: however we track progress against a plan, it has
to be something I can maintain. The plan artifact I had been keeping lives in
`/root/.claude/plans/`, outside the repository — a fresh cloud session never
sees it, no other instance can read it, and it dies with the container. Anything
I recorded there was a second copy of the truth, maintained by hand.

**It had already drifted, silently.** On 2026-09-19 I added a second status
table to `backlog.md` — the "Cloud-operability chunks" table — with its own
column layout. `scripts/repo_state.py`'s `_QUEUE_ROW` requires a leading order
column, so it matched **none** of those rows. The session-start hook, which is
the only status a cold session ever sees, kept printing the old queue while
`X0`, `P1b` and three new blocked chunks came and went. Nothing failed, because
nothing was checking. `.claude/rules/ledger.md` already says status lives only
in the queue table; I broke that rule and the drift was the direct consequence.

**Changed**

- The `X0`–`X4` cloud-operability chunks and `P1b` are now rows 13–18 of the one
  Queue table, in its format, and the second table is gone. All 21 rows parse.
  The prose section that remains says explicitly that its statuses live in the
  Queue table, not in it.
- The two operator blockers are now `[BEN: ...]` flags rather than prose, so the
  startup hook counts and prints them without anyone remembering to: merge #18
  and #19, and pick A/B/C for the standings corpus. Flags went 7 → 9.
- The `P1` gate half of the existing `C3X` flag is marked ruled, since Ben ruled
  it on 2026-09-19; only the Excel half is still open.

**Added: `tests/test_backlog_queue.py`, 7 tests.** The guard that makes the
drift impossible rather than merely discouraged. Any markdown row in the live
program carrying a backticked status must be readable by `_QUEUE_ROW`; every
queue status must be one of `VALID_STATUSES`; `X0`–`X4` and `P1b` must be
present; the ledger stays LF. Plus a regression asserting the *exact* invisible
row shape is caught and its replacement is read — without it the guard could be
weakened to a tautology and nothing would notice.

**One finding I did not plant.** The guard immediately failed on the superseded
2026-09-10 program table, whose rows carry an extra `Track` column the parser
has also never read. Those statuses are historical record, not the tracker, so
the guard is scoped to the live program and a second test asserts the superseded
section actually says it is superseded — unreadable-by-design is fine for
history and dangerous for anything that looks live.

**What the plan file is now.** A pointer: where the tracker lives, the audit's
F1–F9 findings, and the two blockers. No status. The test of whether this works
is that `python3 scripts/repo_state.py --stdout` prints the truth without me
narrating it; a status in prose but not in that output is decoration.

**Verification**

```
full suite              835 passed, 1 skipped in 168.64s (0:02:48), exit 0
before this change      828 passed, 1 skipped in 128.35s
new tests               tests/test_backlog_queue.py, 7 passed
repo_state.py           21 queue rows parsed, READY: P0, 9 [BEN:] flags
doctor                  pass_status true
compileall src scripts  clean
git diff --check        clean
check_protected_paths   No protected path touched (0 changed)
```

### 2026-09-19: P1b — the depth-chart package reaches the operating path

The seam `P1` stopped at, crossed. `P1` shipped
`nfl_qb_depth_role_evidence_v1` and its producer but left the package reachable
only through the `select_prior_lineups` keyword, because wiring it into
`run-slate` means changing a versioned wire format and `P1`'s brief did not
scope that. It does now. No release truth changed; every path still ends
`MODEL_STATUS=PRIOR_ONLY` and `RELEASE_DECISION=DO_NOT_UPLOAD`. No protected
path touched.

**The contract, and why both versions are accepted**

`nfl_cowork_run_request_v2` adds exactly one field,
`qb_depth_role_evidence_json`. v1 is still accepted and still has precisely the
fields it always had, because every `run_request.json` on disk declares v1 and
must stay replayable — `docs/START_HERE.md` records that the schema string is
deliberately stable for that reason.

A **v1 request carrying the v2 field is refused**, naming the version that
introduced it (`cowork.REQUEST_FIELDS_ADDED_AFTER_V1`). That refusal is the
point: it makes "v1 is never mutated" a property of the code rather than a
sentence in a document. A v1 request means today what it meant when it was
written. The same pattern is documented for the next field.

**Bound everywhere the sibling package is bound.**
`.claude/rules/operating-path.md` requires a change reaching one `prior_review`
success exit to reach all three, so: the CLI flag
`--qb-depth-role-evidence-json` on `run-slate` and `select`; request-path
confinement identical to every other path field; the artifact and its per-source
hashes bound after selection; re-verification in both hash-recheck sets with the
`qb_depth_source:` prefix; `qb_depth_role_evidence_sha256` in the pre-lock
manifest; and on the Classic C3 exit an optional immutable binding beside
`weather_evidence_sha256`. Deliberately **not** added to
`classic_review._REQUIRED_ARTIFACTS` — a slate whose quarterbacks need no depth
chart is a normal slate, not an incomplete one.

**One test expectation changed, named here first.**
`tests/test_portfolio_policy.py::test_cowork_policy_is_enforced_audited_snapshotted_and_replays_identically`
asserted the Run Control print area was `$A$1:$D$21`. The sheet gained a
documented `QB_DEPTH_ROLE_EVIDENCE_JSON` row, so the correct value is `$D$22`.
The assertion stays hardcoded rather than derived: the print area is what an
operator sees on paper, and a row appearing or vanishing should fail loudly.

**Verification**

```
full suite              828 passed, 1 skipped in 128.35s (0:02:08), exit 0
before this chunk       823 passed, 1 skipped in 151.03s, exit 0
doctor                  pass_status true
compileall src scripts  clean
git diff --check        clean
check_protected_paths   No protected path touched (0 changed)
```

Five new tests cover v1 loading unchanged, v1 refusing the v2 field, v2 carrying
and confining it, an unknown version still refused, and a structural check that
the package is bound at every site the offensive package is.

### 2026-09-19: P1 — salary-rank divergence, the material-role-change gate, and quarterback depth-chart evidence

Chunk `P1` of the prize-tail program, on `claude/dfs-engine-cloud-audit-617aaj`.
Ben's ruling of 2026-09-19 on the brief's open `[BEN:]` question: the gate is a
**hard stop**, not a diagnostic. No release truth changed; every path still ends
`MODEL_STATUS=PRIOR_ONLY` and `RELEASE_DECISION=DO_NOT_UPLOAD`. No protected
path touched.

The failure this closes, from the DEN@KC run record and the 26-contest
standings: Kenneth Walker III priced at $10,600 (the slate's most expensive
FLEX) carried a 7.3-point prior because his history was on another team, and
`opportunity.py` split Kansas City's attempts Mahomes 0.5395 / Fields 0.4605
from prior-season history. Nothing stopped, and 0 of 18 lineups paid.

**Added**

- `salary_rank_divergence` in `prior_score.py`, reported on `PriorScores`, in
  `as_report()` and in all five selection-report shapes. Names every scored
  person whose DraftKings salary rank beats his prior-points rank, carrying both
  ranks, salary, prior and the evidence state that produced the prior.
- `enforce_material_role_change_gate` / `material_role_change_blockers` in
  `offensive_roles.py`, run at the end of `score_pool`. A person in
  `TRANSFER_PRIOR_UNVERIFIED` who **also** trips divergence stops the run and
  the message names the script that clears it.
- `src/nfl_dfs/qb_depth_roles.py`: contract `nfl_qb_depth_role_evidence_v1`,
  allocation `qb_depth_chart_attempt_share_allocation_v1`, applied before
  `resolve_offensive_roles` and therefore before `score_pool`. Moves only
  `qb_attempt_share`, conserving the team's existing total onto the rank-1
  quarterback. Registered in `docs/DATA_CONTRACTS.md`.
- `scripts/make_offensive_role_evidence.py`, with `--fetch` (through
  `nfl_dfs.sources`, no other client) and `--capture` for bytes already on disk.
- `qb_depth_role_evidence_json` on `select_prior_lineups`, with
  `verify_qb_depth_resolution` called wherever `verify_offensive_resolution` is.

**Two deviations from the brief, both measured rather than preferred**

1. The brief ranks "within position". That cannot catch the case it was written
   for: Walker was the dearest FLEX on the board and 29th of 32 by prior points,
   yet among six running backs he was a place or two out of line, and a
   ten-place gap cannot occur in a six-person group at all. Both populations are
   now ranked, both reported, either one trips it.
2. "At least 10 places" is not scale-free — most of a 15-person Showdown slate,
   a rounding error on a Classic slate. The rule is now a places floor **or** a
   share of the population: `gap >= 10`, or `gap >= 3` and `gap/population >=
   0.25`. Walker is 28 places and 88% of his slate; both arms agree on him.

**One design change forced by real data.** The first version required the
declared quarterbacks to equal exactly the quarterbacks DraftKings lists. Run
against the committed DET@BUF salary file and the live depth chart, that
refused: DraftKings sells three Buffalo quarterbacks and the published chart
names two. A third-stringer the chart does not place is now declared `unlisted`
— a weaker claim than "backup", recorded separately, zeroed, and refused if he
does appear in the capture, so it cannot hide a named starter.

**What the adversarial review caught, before the push**

A `reviewer` pass over the diff found three things worth recording, two of them
real defects of mine:

1. **Duplicate keys in two of the three selection-report dict literals**
   (`selection.py:343` and `:480`). Self-inflicted: I applied an 8-space string
   replacement that is a substring of the 12-space one it had just written, so
   it matched inside its own output. Python keeps the last value and the values
   were identical, so nothing behaved wrongly — it was dead duplicated code.
   Removed, and an AST check now confirms zero dict literals in the file carry a
   duplicate string key. I had already hit this exact bug once on the
   `verify_*` lines in the same edit and fixed only that instance.
2. **A tautological test.** `test_a_capture_mixing_two_snapshots_is_refused`
   called only `parse_depth_chart_excerpt`, which performs no single-`dt` check,
   and asserted a trivial property of its own fixture. The refusal it was named
   for lives in `_derived_order` and was never reached. Rewritten to mutate a
   real package and assert `QB_DEPTH_EXCERPT_DT_MIXED` actually fires.
3. **An overclaim in `IMPLEMENTATION_STATUS.md`**, which said all three new
   capabilities were "on the operating `prior_review` path". Two are; the
   depth-chart contract is reachable from `select_prior_lineups` only. Corrected
   per item, and the producer's own stdout now says so rather than pointing at a
   `run-slate` flag that does not exist.

It also flagged that a declared backup present on the slate but absent from the
opportunity model was silently skipped — not zeroed, not reported, not scored,
which looks like success. Now `QB_DEPTH_PRIOR_ROW_MISSING` for any placed
quarterback, not just the starter, with a test.

**Verification**

```
full suite            823 passed, 1 skipped in 151.03s (0:02:31), exit 0
baseline before       790 passed, 1 skipped in 152.53s, exit 0
new tests             tests/test_qb_depth_roles.py, 33 passed
doctor                pass_status true, python 3.13.7
compileall src scripts  clean
git diff --check      clean
check_protected_paths No protected path touched (0 changed)
```

End to end against real bytes, not fixtures: the producer fetched
`depth_charts_2026.csv` (sha256 `aaa4bc16…78ec`, snapshot
`2026-09-18T12:12:55Z`) through `sources.fetch_public_artifact`, bound it to the
committed DET@BUF salary file, and the consumer accepted its own producer's
output — Josh Allen and Jared Goff to 1.0, Kyle Allen and Joshua Dobbs to 0.0,
Shane Buechele and Luke Altmyer recorded `UNLISTED_ON_DEPTH_CHART`,
`verify_qb_depth_resolution` clean.

**Also recorded, from the cloud audit that preceded this chunk**

- `nfl.sh` as shipped fails the whole suite in a fresh container:
  `2 failed, 226 passed, 1 skipped, 562 errors in 39.75s`, reproducing PR #19's
  measurement exactly. `--basetemp "${TMPDIR:-/tmp}/nfl-dfs-pytest/$$"` is passed
  to a pytest whose `TempPathFactory.getbasetemp` calls `basetemp.mkdir(mode=0o700)`
  with no `parents=True`. Verified against pytest's own source. **Fixed by PR
  #19, not duplicated here**; every run above used `NFL_DFS_PYTEST_TMP`.
- Egress in this session refuses three of the six hosts in `sources.ALLOWED_HOSTS`
  with a 403 at CONNECT: `api.weather.gov`, `api.sleeper.app`,
  `api.the-odds-api.com`. `docs/CLAUDE_CODE_SETUP.md:122` asserts the first
  answers 200 from the container; it does not answer 200 from this one. Chunk
  `X1` replaces the asserted facts with a probe. nflverse over GitHub is
  reachable, which is why the end-to-end test above could run.
- `data/standings/inbox/` is gitignored, so a fresh cloud clone holds only
  `.gitkeep`. `backlog.md` says the 26 exports are "in the repo"; they are on
  Ben's Windows checkout. `P0`, `P0b`, `P4a`, `P4b` and `P5` all grade against
  that corpus and cannot run in a cloud session until chunk `X2` lands. This is
  why `P1` ran before `P0`, inverting the queue order.
- The `DFS_Architect_MCP` server attached to these sessions returns **stub**
  weather (`"source": "stub"`, worker `chunk-3-mlb-fetchers`). It is shaped like
  the answer to the blocked weather gate and must never be used as one. A rule
  making that explicit lands in `X3`.

**The seam this chunk stopped at, named rather than half-crossed**

`qb_depth_role_evidence_json` reaches the engine through the
`select_prior_lineups` keyword only. The operating path is `run-slate`, whose
request is the versioned wire format `nfl_cowork_run_request_v1`, and a schema
change is a new version. P1's brief names `prior_score.py`/`selection.py`,
`offensive_roles.py`, the producer and tests — not `cowork.py`, `cli.py` or
`prior_review.py`. Filed as `P1b`, `READY`.

This does not leave the gate unclearable. The stop fires on an unresolved
transfer, and for anyone who is not a quarterback the remedy is the full
numerical allocation, which is already plumbed; the gate message now says so
per-position rather than offering a depth chart that cannot resolve a running
back. The depth chart fixes the Fields half of DEN@KC (a backup at 46% of his
team's attempts), not the Walker half.

**Open**

- `[BEN: C3X]` unchanged and still open; it blocks nothing on the prize path.
- Hand-back per the brief is `docs/session-prompts/P3a-scenario-bank.md`; P3a
  stays `BLOCKED` until `P0` also closes. `P1b` is `READY` now.

### 2026-09-17 (harness, H2): multi-instance orientation, a push freshness gate, and the branch-protection correction

Harness only. No engine module, contract, `config/` file, evidence gate or
release truth changed; every current path still ends `MODEL_STATUS=PRIOR_ONLY`
and `RELEASE_DECISION=DO_NOT_UPLOAD`. No run was executed.

Several Claude Code instances work this repository. A starting instance was
supposed to learn what the others changed before writing code, and mostly could
not.

Added:

- `scripts/repo_state.py` fetches `origin/main` before measuring distance from
  it. `origin/main` is a remote-tracking ref: it moves on fetch and on nothing
  else, so a session that cloned an hour ago printed `behind origin/main by 0`
  while another instance had merged three pull requests. The single number meant
  to say "someone else changed things" was the one number guaranteed to be
  stale. Demonstrated in an isolated clone with a real moving remote: with the
  local ref rewound the digest printed no distance at all, and after the fetch
  `behind origin/main by 3`.
- The staleness is labelled rather than absorbed. When the fetch fails the digest
  prints `origin/main NOT fetched (<reason>); distance is last fetched <age>`,
  and a clone that never fetched says so. Measured against an unreachable remote
  (`https://10.255.255.1/...`, 2 s timeout): the digest still printed and the
  script still exited 0.
- `changelog_headings()`, and three headings in the digest under
  `recent changelog entries (newest first)`. Every session writes a dated
  `###` entry saying what changed and why; that is the artifact a new instance
  needs, written by the instance that made the change, and nothing surfaced it.
  The file is streamed and abandoned at the first heading past `Unreleased`, so
  it is never read whole.
- `.claude/hooks/push_freshness.py`: refuses a push when `origin/main` has moved
  past this branch's merge base, naming the commits and saying
  `git merge origin/main`. Startup orientation cannot help when another instance
  merges forty minutes into a session. Demonstrated both directions in an
  isolated clone: refused naming three commits, then allowed after the merge.
  A deletion, a `--dry-run` and a failed fetch all pass: the gate fails open,
  because a gate that blocks work when it cannot see is worse than no gate.
- `scripts/claim.py`: the writer for `state/claims.json`. The reader in
  `repo_state.py` and the `dev-session` instruction to claim a chunk have both
  existed since 2026-09-17, and nothing ever wrote a claim, so the file stayed
  `{"claims": []}` and the instruction was decorative. `take` refuses a chunk
  another instance holds (exit 1, naming holder, branch and age); a claim older
  than six hours is reclaimable and records `reclaimed_from` in the tracked
  file. Wired into `/dev-session` step 7 and `/close-out` step 8.
- `tests/test_harness_orientation.py`: 44 tests. Every one offline, with the one
  function that would reach the network injected, per `.claude/rules/tests.md`,
  and every clock passed in rather than hardcoded.

Changed:

- `.claude/hooks/guard_bash.py`, the two false positives recorded in the
  2026-09-17 entry below. `git add -u <path>` is allowed, because a scoped `-u`
  is an explicit path list; bare `git add -u` is still refused. `git stash list`
  and `git stash show` are allowed, because both are read-only; the pattern now
  matches the mutating verbs (`push`, `save`, `pop`, `apply`, `drop`, `clear`,
  `branch`, `create`, `store`) and bare `git stash` rather than the subcommand
  name. Both failed in the safe direction, so this is a usability repair.
  Narrowing these took three attempts, and the intermediate versions are worth
  recording because two of them failed in the *unsafe* direction, which is the
  opposite of the defect being repaired:

  1. The first `-u` pattern keyed on `-u` being last, so `git add src/x.py -u`
     (identical in effect to `git add -u src/x.py`) was still refused. A third
     false positive of the same family. Caught reviewing the diff.
  2. The second `-u` pattern accepted any trailing pathspec as narrowing, so
     `git add -u .`, `-u ./`, `-u *` and `-u :/` were all allowed, though from
     the repository root every one of them stages the whole tree exactly like
     the bare form. Found by the `reviewer` subagent.
  3. Naming the mutating stash verbs was the wrong shape outright. Git takes
     flags in place of the `push` keyword, so `git stash -u`,
     `--include-untracked`, `-a`, `-p` and `-k` are all `stash push` and all
     slipped through both the guard and the narrowed deny list. Also found by
     the `reviewer` subagent, and a genuine regression against the overbroad
     pattern it replaced.

  The shipped versions: `git stash` is refused unless the next token is `list`
  or `show`, so an allowlist that fails safe for a subcommand git has not grown
  yet; and `git add` is refused when `-u` appears among arguments that narrow
  nothing, counting flags and the whole-tree pathspecs as not narrowing. 15
  refused and 4 allowed shapes were added to the test pairs to pin all three.
- `.claude/settings.json` deny list, which was the other half of both. It denied
  `Bash(git add -u:*)` and `Bash(git stash:*)` by prefix, so repairing only the
  guard would have left both still refused. Now `Bash(git add -u)` exactly, and
  the ten mutating stash verbs individually.
- The freshness gate rides the existing `guard_bash.py` wiring rather than a
  second `PreToolUse` entry. The matcher is tool-level, so a second hook would
  mean a second `python3` process on every Bash call: measured ~20 ms, of which
  ~10 ms is interpreter startup. `guard_bash.py` instead runs two substring
  checks and imports the gate only on a push. `forbidden_reason()` stays pure
  and network-free, which is load-bearing: `tests/test_repo_boundaries.py` runs
  it over every allowed shape including `git push -u origin claude/...`, so
  merging the two would have put the network in the suite.

Corrected, and this one was false rather than stale:

- Branch protection on `main` does not exist and never will. This repository is
  private on a GitHub free plan, where rulesets and branch protection are
  unavailable. Three places asserted or implied otherwise:
  `docs/CLAUDE_CODE_SETUP.md` (the whole "Branch protection on `main`" section,
  replaced by "Where the gate actually lives"), `.github/workflows/ci.yml`'s
  header comment, and the framing in `.claude/rules/git-authority.md`. What is
  true: nothing server-side blocks a push to `main` or a merge over red CI. The
  controls are entirely client-side (the deny list, the two hooks, the rules
  documents) and they bind every instance because every instance clones them.
  CI is advisory: it reports, it does not block. The `ben-review` label is
  unchanged and still needed, because `protected-paths` runs as a CI job
  regardless of branch protection.
  `grep -rni "branch protection" docs/ .claude/ .github/` now returns two hits,
  both stating it is unavailable.
- `docs/START_HERE.md` pointed at `state/repo-state.json` for an active claim.
  Claims live in `state/claims.json`, which is tracked; `repo-state.json` is the
  derived digest and is gitignored, so it could never have carried another
  instance's claim.

Repaired outside the brief, because it blocked every verification in this
chunk and every fresh clone:

- `nfl.sh` and `nfl.ps1` now create the parent of pytest's `--basetemp`. pytest
  creates basetemp itself but not the directories above it, so the per-process
  path introduced on 2026-09-17 (`<temp>/nfl-dfs-pytest/<pid>`) fails every test
  at fixture setup with `FileNotFoundError` whenever `<temp>/nfl-dfs-pytest` is
  absent, which is the state of any fresh container. Measured here on a fresh
  container before the repair: `2 failed, 226 passed, 1 skipped, 562 errors in
  35.16s`, all 562 being `FileNotFoundError: .../nfl-dfs-pytest/442` at fixture
  setup. Probed both directions afterwards: raw pytest with a nested basetemp
  whose parent is absent still errors, and the same path through `nfl.sh`
  passes. This is the same class of defect as the basetemp collision recorded
  below, and from the same commit.

Verification:

- Baseline on this branch before any change, after the launcher repair:
  `790 passed, 1 skipped in 134.44s (0:02:14)`.
- Complete pinned suite after the chunk:
  `869 passed, 1 skipped in 135.69s (0:02:15)`. The 79 added tests are the 46 in
  the new file plus 31 parametrized command shapes and two drift guards in
  `tests/test_repo_boundaries.py`, which goes from 54 tests to 87. The one skip
  is the expected Windows symlink-permission case.
- The `reviewer` subagent ran against the diff before the commit and found the
  two unsafe-direction regressions recorded above. Both were reproduced
  independently before being fixed, rather than taken on the report alone.
- `doctor`: `pass_status: true`. `git diff --check`: clean.
  `python3 -m compileall scripts .claude/hooks`: clean.
- Focused: `tests/test_harness_orientation.py` `44 passed in 0.24s`; with
  `tests/test_repo_boundaries.py`, `118 passed in 1.14s`.
- Latency, measured rather than asserted. Non-push Bash call through the hook:
  19 to 22 ms across 12 runs, against a 19 to 22 ms measurement of the same
  hook before this chunk and a 10 to 14 ms bare interpreter floor. The first
  version of the change put `from pathlib import Path` at module scope and cost
  25 to 30 ms; making it lazy returned it to the floor.
- Session start: 42 to 46 ms warm (fetch inside the TTL) and offline, against
  43 to 46 ms before this chunk; 515 to 812 ms cold, when the TTL has expired
  and the fetch actually runs. The strategy is a synchronous fetch, TTL-gated at
  300 s and timed out at 3 s, overridable with `NFL_DFS_FETCH_TTL`,
  `NFL_DFS_FETCH_TIMEOUT` and `NFL_DFS_NO_FETCH`. A background fetch was
  rejected: the acceptance is that rewinding the ref and running the script
  *now* recovers the true number, and a background fetch consumed by the next
  startup leaves this run wrong, which is the bug.
- Hook output is 35 lines against the unchanged 60-line ceiling, asserted by a
  test so it cannot regress silently.

### 2026-09-17 (slate run): DET@BUF Showdown, 13 entries, prior-only review

First operated slate in a cloud session. `RELEASE_DECISION=DO_NOT_UPLOAD` and
`MODEL_STATUS=PRIOR_ONLY` throughout; no gate was relaxed and no observation was
invented. Run id `20260917T232331Z-detbuf917c`.

Inputs, committed under `data/inbox/slates/det-buf-2026-09-17/`:

    salary  2593bb4b54b021a48e614b614f22c7256a5ada3031517f8129842b8fdbc8de89
    entries f26648d8fff03e6a7fff072ace72955d1377acf13b251bb5d78c6994c21c6d2d

SHOWDOWN, one game, 13 reserved entries, 47 people, classified by schema.

Two evidence gates stopped the first pass at `PRIOR_REVIEW_IDENTITY_BLOCKED`:

- `WEATHER_CAPTURE_REQUIRED:roof=outdoors`. `api.weather.gov` answers 403 at
  this session's egress proxy (organization policy; confirmed over three
  attempts and two clients, while `raw.githubusercontent.com` answers 200 and
  the nflverse fetch succeeded). `api.sleeper.app` is refused the same way.
  Resolved by operator-supplied state only: Ben attested the Buffalo forecast
  was not a factor, `--weather-state CLEAR` was passed with no source URI and no
  `generatedAt`, and the engine recorded it as
  `OPERATOR_SUPPLIED:roof=outdoors|OPERATOR_SUPPLIED_UNATTRIBUTED`. There are no
  retained raw bytes or hash behind the weather in this run. That label is the
  honest record and it travels into the readable review.
- `IDENTITY_UNRESOLVED_AND_AVAILABLE:44138452:Joshua Palmer`. DraftKings spells
  him "Joshua Palmer"; the frozen `roster_weekly_2026.csv`
  (`698183b8...fad9d8`) spells him "Josh Palmer", `00-0036988`, WR, BUF, ACT,
  week 2, and Buffalo lists no other Palmer. `normalize_person_name` has no
  given-name-variant rule, so the proposal was `UNMATCHED`. An operator
  `--exclude` does not reach the identity gate; tested, the blocker survived it.
  Resolved through the documented reviewed-crosswalk path rather than a code
  change: `REVIEWED_PROVIDER_PLAYER_ID=00-0036988` with `DECISION=ACCEPT` in the
  reviewed file (`f09c06a1...26fda`), then `priors-freeze`. `_resolve_reviewed`
  checks DK name, team and position against the proposal verbatim before
  accepting the row, and `prior_review.py:1797` then reports identity as
  `INHERITED_FROM_FROZEN_PACKAGE` instead of re-running the gate.

Portfolio, from a generated `nfl_showdown_portfolio_policy_v1`
(`scripts/make_showdown_policy.py`, source `93e89238...2ca02`, normalized
`8edec314...1810a`): combined-person cap 0.62, captain cap 0.25, captains zeroed
for K/DST and for any FLEX salary at or below 900 (21 people), max pairwise
person overlap 4, unique lineups required. No rung was dropped; the policy held
as written on the first solve.

    SELECT                 13 lineups, solver OPTIMAL (kOptimal)
    enforcement            ENFORCED_AND_INDEPENDENTLY_AUDITED
    independent audit      PASS (prior_only_showdown_portfolio_audit_sd4_v1)
    DISPLAY_RECONCILIATION PASS
    candidate bank         CANDIDATE_LIMIT_REACHED_INCOMPLETE
    DK_REVIEW_ENTRY        e58a9b0e2a8a50f183fefe56bd7bafeb109ae45545240ec0ce9aa3401e6c3c6e
    readable JSON          8151e52264e4f8bf7954b7b7cd3430f01889ec74036f3e31ceb4d0cfc41a1454
    readable HTML          a7d285b45d36d532b1d4ded8bb9ea958171503901cbe4ebde21e9aa15cc85727
    workbook               d39ba977ee87f17424f2d43b90b6e78093b0ba8f3d88dc760e7bdbdda195b4ac

Captains held at 3 of 13 (Gibbs, St. Brown, Goff), combined at 8 of 13. The bank
status is not a full-slate search and `OPTIMAL` is scoped to the bank actually
built.

Named gaps in the delivered portfolio, none of them cleared: no
`official_status_csv`, so `official_status_coverage` is null and every selected
person reads `BLANK_NOT_OFFICIAL_ACTIVITY`; Ty Johnson carries DraftKings status
`Q` and appears in 5 of 13 lineups with nothing confirming him; every selected
skill player is `CURRENT_ROLE_UNKNOWN`, with two `TRANSFER_PRIOR_UNVERIFIED` and
one `MISSING_HISTORY`; the kicker rests on
`PRIOR_ONLY_SOLE_LISTED_ASSUMPTION`; no payout, prize value or field size. The
prior-score objective buys opportunity share per dollar with no ownership or
ceiling model, and it salary-dumped into minimum-priced bench players: Greg
Dortch at $1,000 in 7 of 13, Jackson Hawes at $600 in 3.

Repository change in this session, `.gitattributes` only:

- `data/inbox/** -text whitespace=cr-at-eol`. DraftKings exports are CRLF.
  `*.csv -text` already preserved the bytes, which is why the committed blobs
  still hash to the uploads, but it does not tell `git diff --check` that a CR
  at end of line is expected, so the `suite` job failed at its whitespace step
  with 394 complaints and exit 2, before `compileall` or pytest ran. Same rule
  `tests/fixtures/supplied/**` already carries. Before: 394 lines, exit 2.
  After: 0 lines, exit 0.

Verification: `790 passed, 1 skipped in 244.18s (0:04:04)`, exit 0.
`compileall src scripts` clean, `doctor` `pass_status` true,
`git diff --cached --check` clean, `check_protected_paths.py` reports no
protected path touched.

Three findings for the queue, none fixed here:

- `nfl.sh:57` and the PowerShell twin pass
  `--basetemp "${TMPDIR:-/tmp}/nfl-dfs-pytest/$$"` but never create that parent,
  and pytest creates basetemp with `os.mkdir` rather than `makedirs`. The first
  suite run in a cold container fails 562 tests with `FileNotFoundError` before
  any test body runs. Introduced by 625e869. CLAUDE.md's
  `789 passed, 1 skipped` is not reproducible from a fresh clone without
  `mkdir -p` on that path first. Measured count is now 790.
- `normalize_person_name` cannot bridge a given-name variant (Joshua/Josh), so a
  correctly rostered person reaches the identity gate as `UNMATCHED`. Ben
  declined a matcher change on 2026-09-17 and the reviewed-crosswalk path was
  used instead; the underlying gap stands and will recur on any slate where
  DraftKings and nflverse disagree on a first name.
- This session type's egress policy allows GitHub hosts only.
  `docs/CLAUDE_CODE_SETUP.md` records `api.weather.gov` answering 200 from a
  container on 2026-09-17, which was true of that container and is not true of
  this one. Outdoor weather cannot be captured here at all, so the note should
  say the reachable set is per-session and must be tested each time.

### 2026-09-17 (CI unblock): the preflight clock test, and a pytest basetemp collision

Two test-infrastructure repairs. No engine module, contract, run artifact or
release truth changed, and no run was executed.

The wrong test, named before the fix as `.claude/rules/tests.md` requires:
`tests/test_w6_live_preflight.py::test_live_check_refuses_once_a_selected_player_has_locked`.
It hardcoded `expires_at=datetime(2026, 9, 14)`, so from 2026-09-14 onward the
package it builds could no longer be certified at the live clock and the test
failed every day after, for a reason unrelated to what it asserts. The test was
wrong, not the engine. This is the defect its own `_before_fixture_lock` helper
documents, and the same class as the hardcoded `AS_OF` in `test_priors_adapter.py`.

Changed:

- That test now derives every clock from the fixture's own lock times: certify
  30 minutes before the earliest lock, expire the evidence six hours after it,
  run the live check one hour after it. The helper `_before_fixture_lock` and
  the `monkeypatch`/`now` hook in `_certified` already existed for exactly this
  and were simply not used here. The evidence deliberately stays valid past the
  check clock, so the package is refused for the lock and nothing else, and a
  new assertion pins that (`not any("EXPIRED" in b for b in blockers)`).
- `nfl.sh` and `nfl.ps1` now give each run its own pytest `--basetemp`
  (`<temp>/nfl-dfs-pytest/<pid>`). pytest deletes basetemp at the start of every
  run, so the fixed path introduced on 2026-09-17 meant two concurrent suites
  wiped each other mid-flight. `cache_dir` stays shared on purpose: pytest does
  not clear it at startup, and one path is what makes `--lf` and `--ff` work
  across runs. `nfl.ps1` had carried the same fixed path since before the Linux
  launcher copied it.

Added:

- `test_launchers_give_each_run_its_own_pytest_basetemp` in
  `tests/test_repo_boundaries.py`. A grep rather than a behavioural test, and
  labelled as such in its docstring: racing two real suites would cost five
  minutes and be flaky by construction.

Evidence for the collision, measured rather than inferred: a suite running in
the background while a second pytest process started against the same pinned
basetemp produced `3 failed, 786 passed, 1 skipped in 147.82s` with failures in
`test_classic_review_c3::test_registered_full_fixture_scale_and_exact_entry_order[20]`,
the same test at `[150]`, and
`test_cowork_rerun_regressions::test_review_surface_shows_pool_coverage_and_the_kicker_assumption`.
All three write into basetemp. None was a real failure. Several Claude Code
instances work this repository, so that collision is expected rather than exotic.

Verification:

- Before: `1 failed, 788 passed, 1 skipped in 149.38s` locally, and the same
  result in GitHub Actions run 35178873587 on the pull request for #15, which
  is what made the new `suite` job permanently red.
- After the clock repair, on isolated temp roots:
  `789 passed, 1 skipped in 148.43s (0:02:28)`. First fully green run.
- After both repairs: `790 passed, 1 skipped in 147.37s (0:02:27)`. The extra
  test over the previous run is the launcher guard.
- The repaired test was probed on both sides rather than trusted: at one hour
  after the earliest fixture lock the decision is `DO_NOT_UPLOAD` with the
  `SELECTED_PLAYER_ALREADY_LOCKED` blocker and no expiry blocker; at ten minutes
  before it the same package is `CERTIFIED_UPLOAD_PACKAGE` with no blockers.
- The one remaining skip is the expected Windows symlink-permission case.

Chunk `P0`'s brief lists the clock repair in its scope. It is done here because
it blocked CI for every chunk, `P0` included; `P0`'s acceptance loses that one
item and is otherwise unchanged.


### 2026-09-17 (harness): Claude Code as the only surface, CI, autonomous git authority, session orientation

Phase 1 of the Claude Code migration. No engine module, contract, run artifact
or release truth changed; every current path still ends `MODEL_STATUS=PRIOR_ONLY`
and `RELEASE_DECISION=DO_NOT_UPLOAD`. No run was executed.

Added:

- `.github/workflows/ci.yml`: three jobs on every push and pull request.
  `suite` (full pinned pytest, `compileall src scripts`, ranged
  `git diff --check`), `boundaries` (the new boundary file alone, so a broken
  permanent boundary is legible without reading 747 results), and
  `protected-paths` (pull requests only). Python 3.13.7 via `astral-sh/setup-uv`
  with a `uv.lock`-keyed cache. The suite job writes `state/last-ci.json` as an
  artifact and a job summary; CI never pushes to the repository, because a
  workflow that writes to `main` would have to bypass the branch protection that
  makes autonomous merge safe.
- `.github/protected-paths.txt`: one definition of what Ben still reviews, read
  by the CI job, by `scripts/check_protected_paths.py` and asserted by
  `tests/test_repo_boundaries.py`, so the three cannot drift. Covers `CLAUDE.md`,
  `.claude/rules/*.md`, `release.py`, `certification.py`, `preflight.py`,
  `evidence.py`, `sources.py`, `config/evidence_policy.json`,
  `config/metric_registry_*.json`, and the authority model itself.
- `scripts/check_protected_paths.py`: fails a pull request touching a protected
  path without the `ben-review` label. Exit 2 when the check cannot run, because
  an unrunnable gate is not a passing gate.
- `tests/test_repo_boundaries.py`: 53 tests (12 plus 41 parametrized) turning
  `CLAUDE.md` § Permanent boundaries into assertions. Protected-list loadability and matcher behaviour;
  `DK_UPLOAD` confined to a pinned four-module set; `prior_review`'s transitive
  import closure reaching neither a `DK_UPLOAD` writer nor `field.py` /
  `economics.py` (previously only claimed as a report string);
  `AvgPointsPerGame` confined to `dk.py` and `cowork.py`; `ALLOWED_HOSTS` and
  `PROHIBITED_HOSTS` pinned; no module naming a value `ev`, `roi`,
  `win_probability`, `cash_probability`, `edge` or lowercase `calibrated` (the
  uppercase `CALIBRATED` influence tier in `learning.py` is exempt and the test
  says why); the four release truths and the CERTIFIED-requires-
  PROSPECTIVELY_VALIDATED guard intact. Plus 30 refused and 17 allowed command
  shapes against the Bash guard, so its patterns are themselves verified in both
  directions rather than only against the destructive ones.
- `.claude/hooks/session_start.py` plus the `SessionStart` hook wiring in
  `.claude/settings.json`, matching `startup|resume|clear|compact`. Emits 33
  lines in 55 ms: boundaries, release truths, branch, recent commits, chunk
  queue, active and stale claims, last suite result, calibration state, open
  `[BEN: ...]` flags. Exits 0 unconditionally.
- `scripts/repo_state.py`: derives `state/repo-state.json` from the files that
  are already authoritative (backlog Queue table, `state/claims.json`, the
  recorded suite result, `records/slates/`, `[BEN:]` flags). Hand-maintained
  status rots once two instances disagree; this does not.
- `scripts/record_verify.py`: records a suite result at
  `state/last-verify.json`. A log with no recognizable pytest summary is a
  refusal, not a guess, so a run killed by a tool timeout can never be recorded
  as a result. `ci.yml` imports its `summary_line` so CI and a local terminal
  share one definition.
- `state/claims.json`, the chunk-claim primitive between concurrent instances,
  tracked; the rest of `state/` is derived and gitignored.
- `docs/START_HERE.md` (108 lines): the orientation page the hook points at.
- `docs/CLAUDE_CODE_SETUP.md`: what only Ben can do. Branch protection steps,
  the `ben-review` label, and the documented constraint that
  `permissions.defaultMode` values `auto` and `bypassPermissions` are ignored
  from project settings and must be set in `~/.claude/settings.json`.
- `.claude/rules/git-authority.md`: replaces the reviewed-path-list rule.
- `.claude/skills/onboard/SKILL.md`: cold-start orientation when the hook did
  not run.
- `.claude/hooks/guard_bash.py`, wired as a `PreToolUse` hook on `Bash`. The
  permission grammar matches a prefix, which cannot see a flag arriving after an
  allowed prefix (`git push -u origin claude/x --force` matches the allow rule
  and no deny rule) or a second command in a chain. The guard reads the whole
  command and refuses on a pattern wherever it appears, stripping quoted strings
  and here-document bodies first so that writing a document or a test about a
  refused command still works. It caught that false positive on itself the first
  time it ran, which is why the stripping exists and why
  `ALLOWED_COMMANDS` covers it. Fails open: a crash hands the decision back to
  the normal permission flow.

Changed:

- `.claude/settings.json`: `defaultMode` `acceptEdits`; commit, push to
  `claude/*`, pull request creation and merge, and merged-branch deletion moved
  from `ask` to `allow`. Deny now also covers `git push origin main`,
  `--force-with-lease`, `branch -D`, `rebase`, `filter-branch`, `reflog expire`,
  `gc --prune`, `commit -a`, `add -u`, `Edit(.git/**)`, and the GitHub API write
  tools (`create_or_update_file`, `push_files`, `delete_file`) that would bypass
  local verification. The 16 `PowerShell(...)` entries were deleted: that is not
  a Claude Code tool name, so they had never matched anything and the Windows
  path was unguarded.
- `docs/COWORK_RUNBOOK.md` renamed to `docs/RUNBOOK.md`. Three sections
  rewritten against measurement rather than relabelled: Continuity (the device
  bridge, `git bundle` handoff and PAT discussion are gone; GitHub is the only
  route, with an explicit list of what a clone does not carry), Prerequisites,
  and the Linux runtime. The 2026-09-08 bridge-mount notes are kept as a
  historical subsection because the launcher overrides they produced still work.
  The 2026-09-12 lock-clock ruling is untouched.
- `docs/OPERATOR_GUIDE.md`: the Cowork Desktop section is replaced by a
  two-surface table and a `run-slate` invocation for each. `C:\Users\benja\...`
  replaced by `<repo root>` in both places.
- `CLAUDE.md`: single-surface statement; authority pointer; `Commands` and
  `Token discipline` compressed to stay under the 200-line body limit; session
  protocol item 8 rewritten; branch prefix `codex/` to `claude/`; corrected
  container egress claim.
- `README.md`: Cowork removed from the operating-surface paragraph; CI listed
  under current verification.
- `nfl.sh`: `.cowork-venv` and `.cowork-uv-cache` renamed to `.venv-linux` and
  `.uv-cache-linux`. `test` now pins pytest's basetemp and cache directory under
  `TMPDIR` the way `nfl.ps1` has always pinned them, closing a live
  failure-at-fixture-setup mode on Linux. Overridable with
  `NFL_DFS_PYTEST_TMP` and `NFL_DFS_PYTEST_CACHE`.
- `cli.py`: the subcommand is `run-slate`, with `cowork-run` kept as an alias.
  `COWORK_REQUEST_VERSION` is deliberately unchanged: `cowork.py` hard-rejects a
  mismatched `schema_version`, so renaming the string would invalidate every
  `run_request.json` on disk. `nfl.ps1`'s ValidateSet gained `run-slate`.
- `skills/nfl-standings-pull-checklist/` moved to
  `.claude/skills/standings-checklist/` and renamed to match its directory. It
  was an orphan: referenced by no document, and predating `.claude/` by a day.
- `.claude/skills/{dev-session,verify,close-out}/SKILL.md`: claim the chunk
  before writing code; record the suite result; check protected paths; and at
  close-out commit, push, open the pull request and merge it on green rather
  than printing a path list.
- Three script error strings and `docs/session-prompts/P0-standings-grading-harness.md`
  repointed at `.venv-linux`. Older session prompts are dated records and were
  left alone.

Corrected:

- `CLAUDE.md` said `api.weather.gov` is unreachable from a container. It answers
  HTTP 200. Measured 2026-09-17 alongside `raw.githubusercontent.com` and
  nflverse GitHub release downloads, all reachable.
- `docs/RUNBOOK.md` said `doctor` reports `pass_status: false` with
  `sqlite_probe_error` in a container. It returns `pass_status: true` with an
  empty probe error and WAL journaling; the bridge-mount symptoms do not
  reproduce in a Claude Code container.

Verification:

- Baseline before any change, Linux container:
  `1 failed, 735 passed, 1 skipped in 155.56s (0:02:35)`.
- After: `1 failed, 788 passed, 1 skipped in 149.38s (0:02:29)`. The 53 added
  tests are all in `tests/test_repo_boundaries.py`. The single failure is the
  documented `test_live_check_refuses_once_a_selected_player_has_locked`
  hardcoded-expiry case that chunk P0 repairs; it is unchanged by this work.
- Each boundary assertion was mutation-tested: AvgPointsPerGame appended to
  `ownership.py`, `example.com` added to `ALLOWED_HOSTS`, `_LABEL = "roi"` added
  to `ownership.py`, an `economics` import added to `prior_review.py`,
  `DK_UPLOAD` added to `ownership.py`, and a non-existent path added to the
  protected list. All six failed the intended test and only that test; the tree
  was restored and `git diff --stat -- src/ .github/` was empty afterwards.
- `sh ./nfl.sh doctor`: `pass_status: true`.
- `.venv-linux/bin/python -m compileall -q src scripts .claude/hooks`: clean.
- `git diff --check`: clean.
- `.github/workflows/ci.yml` parses; jobs `boundaries`, `suite`,
  `protected-paths`.
- `python3 .claude/hooks/session_start.py`: 33 lines, 0.055 s.
- `sh ./nfl.sh run-slate` and `sh ./nfl.sh cowork-run` both reach the same
  handler and return the same four release truths.

Repaired after an adversarial review of the diff, all three findings confirmed
before acting:

- `ci.yml`'s `suite` job checked out at the default depth 1, so the whitespace
  and conflict-marker step would have died with `fatal: bad object` under
  `bash -e` on every pull request (the base commit is not in a shallow clone)
  and silently skipped on every push (`HEAD~1` does not resolve either). The job
  now checks out with `fetch-depth: 0`, verifies the base object exists with
  `git cat-file -e` before using it, and diffs from the merge base. A check that
  cannot fail is not a check.
- `guard_bash.py` and the deny list both missed refspec pushes. `git push origin
  feature:main` reaches `main` with no `main` token after `origin`, and
  `git push origin +HEAD:main` forces with no `--force` token anywhere. Two
  patterns added, plus six refused and two allowed shapes in the tests (a
  non-forced refspec onto a `claude/*` branch, and a branch whose name merely
  contains "main", both of which must still pass). Prefix rules cannot express
  the source-ref form at all, so the guard is the only layer that sees it, and
  the rule now says so.
- `backlog.md`'s session-conventions paragraph still said `codex/<id>-<slug>`
  and "commit only on an explicit reviewed path list", contradicting the policy
  this same commit introduces two sections above it. Consequential rather than
  cosmetic: the push-allow rules are scoped to `claude/*`, so a session
  following the stale text would have created a branch it could not push.

Known issues in `guard_bash.py`, found by the guard firing on the session that
wrote it, and left in place because both fail in the safe direction:

- `git add -u <explicit path>` is refused, though a scoped `-u` is an explicit
  path list and the rule only means to refuse whole-tree staging. Workaround:
  plain `git add <path>` stages a deletion just as well.
- `git stash list` and `git stash show` are refused, though both are read-only.
  The pattern matches the `stash` subcommand rather than its verb.

Neither was repaired in this commit: the Claude Code auto-mode classifier
refuses to let a session edit the guard that governs it, which is the correct
posture and not something to work around. Narrowing both patterns is a small
follow-up that needs Ben's go-ahead.

Not done in this phase, and why: the fragment-ledger migration
(`changelog.d/`, chunk status in brief frontmatter) is the remaining
multi-instance collision fix and is deliberately separate, being the most
invasive change in the plan. Branch protection on `main` and the `ben-review`
label are Ben's to create; until they exist, "merge only when green" is a
convention rather than an enforced rule.


### 2026-09-16 (repository hygiene): branch consolidation, Showdown scripts tracked, root run outputs ignored

Repository hygiene only. No source module, test, contract, run artifact or
release truth changed, and no run was executed.

Added:

- `scripts/make_showdown_policy.py` and `scripts/qa_showdown_portfolio.py`,
  written 2026-09-14 per the SHOWDOWN_RETROSPECTIVE_2026-09-13
  recommendations but never committed. Unchanged from the versions used on
  the 2026-09-13 and 2026-09-14 slates. CLAUDE.md cites
  `make_showdown_policy.py` as encoding the Showdown rung ladder, so a script
  the lock-clock ladder depends on had been living outside version control
  while its Classic twins (`make_classic_policy.py`, `qa_classic_portfolio.py`)
  were tracked.
- `docs/RUN_RECORD_20260914_DEN_KC.md`,
  `docs/STANDINGS_GREENFIELD_FINDINGS_2026-09-15.md` and
  `data/standings/standings_pulls_2026-09-15.html`. The findings document was
  already recorded as Added by the 2026-09-15 entry above but had never been
  committed; its SHA-256 was verified to match the
  `d7250f0d575e1e957c1bad25da7dd9a5ff0edc2aec3c66c463661380d4751543` that
  entry records. The standings pull follows the tracked
  `standings_pulls_2026-09-14.html` precedent.
- `data/standings/inbox/.gitkeep` and `data/standings/normalized/.gitkeep`.
  Both were present on disk but never tracked, which is why git reported both
  directories as untracked even though `.gitignore` already un-ignores exactly
  those two paths. Matches the tracked `.gitkeep` in `data/runs/`, `outputs/`,
  `data/models/` and `data/registry/`.

Changed:

- `.gitignore`: root-anchored ignores for the 15 operator run outputs that had
  accumulated at the repo root instead of under `data/runs/`
  (`/DKEntries_*.csv`, `/*_official_status.csv`, `/*_portfolio_policy_v*.json`),
  plus `/patches/` and `/Claude outputs/`. The leading slash confines every
  pattern to the root, so the same filenames stay visible under `data/runs/`,
  `tests/fixtures/` or anywhere else in the tree.
- `.gitattributes`: `docs/*_FINDINGS_*.md -text whitespace=cr-at-eol`, extending
  the existing byte-sensitive section and matching the flags already used for
  `tests/fixtures/supplied/**`. The `whitespace=cr-at-eol` half is required:
  without it `git diff --check` reports every line of a preserved CRLF document
  as trailing whitespace. Under the default `* text=auto eol=lf` a CRLF findings
  document is normalized on the way into git. Staging
  `STANDINGS_GREENFIELD_FINDINGS_2026-09-15.md` produced a blob hashing
  `30f69d9703b4bab6af585b852554fbf9cd724ecd49d2616bc6e0d99a41c4fc12` against the
  `d7250f0d...` the 2026-09-15 entry records: the commit meant to preserve that
  document would silently have invalidated its recorded hash. With the rule in
  place the staged blob hashes `d7250f0d...` again. The already committed
  `STANDINGS_DUAL_OPTIMIZATION_FINDINGS_2026-09-15.md` was LF on disk and is
  unaffected; its recorded `664e64c3...` verifies both on disk and in git.
- Corrected a false rule in five places that the 2026-09-15 harness commit had
  introduced: `CLAUDE.md` "Repo etiquette", `.claude/rules/ledger.md`,
  `.claude/skills/close-out/SKILL.md` (three references),
  `.claude/skills/dev-session/SKILL.md` and `.claude/agents/reviewer.md` all
  stated the three ledgers are CRLF. They are LF, and have been since
  `.gitattributes` set `* text=auto eol=lf`: measured 0 CRLF against 481, 614
  and 436 lines respectively. A session obeying the old rule would have rewritten
  every line of a ledger and buried its real change in a whole-file diff. The
  rules now say LF, cite the measurement, and tell the session to read the bytes
  rather than assume. The two CRLF references in
  `DFS_SYSTEM_GREENFIELD_SPEC.md` are correct and untouched: DK CSVs and
  `tests/fixtures/supplied/**` really are byte-preserved by `.gitattributes`.
- PR #14 merged to `main` as `970fea1`; the local checkout moved from
  `docs/claude-code-setup-2026-09-15` to `main`. The branch still exists on
  origin and locally; nothing was deleted.

Verification:

- `patches/slate-day-engine-changes.patch` was audited before being ignored,
  not assumed stale. It applies in neither direction, but every marker from
  all six of its hunks is present in `main`: `embedded_pool_start` (`dk.py`),
  `EXCLUDE_UNRESOLVED_UNAVAILABLE` (`priors.py`), `write_pool_scores` and
  `DIAGNOSTIC_NOT_AN_UPLOAD_AUTHORIZATION` (`selection.py`), the unavailable
  vocabulary in `contracts.py`, and
  `tests/fixtures/supplied/DKEntries CSV 20 entries.csv`. The work landed
  under `7edddee`, not as its own commit, which is why the patch no longer
  lines up in either direction.
- The two documents in `Claude outputs/` are byte-identical (`diff -q`) to the
  tracked `docs/session-prompts/QA1-adversarial-qa-agent.md` and
  `W4-cowork-prior-only-profile.md`.
- `git ls-files --cached --ignored --exclude-standard` empty after each
  `.gitignore` change: no tracked file became invisible.
- `py_compile` clean and `--help` runs on both Showdown scripts;
  `git diff --check` clean.
- Full suite NOT run: no `src/` module changed in this work.

Left open:

- Nothing was deleted. `patches/` and `Claude outputs/` remain on disk and are
  now ignored, per this repo's never-delete posture; they can be removed by
  hand at any time.
- `tests/test_w6_live_preflight.py::test_live_check_refuses_once_a_selected_player_has_locked`
  still fails on its hardcoded 2026-09-14 expiry until `P0` pins its clock.

### 2026-09-15 (research and reprioritization): standings evidence, the prize-tail program, no code changed

Two research reports were added under `docs/` and the development queue was
reprioritized on their evidence. No source, test, contract, run artifact or
release truth changed.

Added:

- `docs/STANDINGS_DUAL_OPTIMIZATION_FINDINGS_2026-09-15.md` (SHA-256
  `664e64c37061b83cdeb5e6bbd0209e05cba307ea9d1c463607e0e3943e3ef065`). All 26
  exports in `data/standings/inbox` (1,870,717 entries, five slate groups)
  joined to the contest-entry history and the same-slate salary files; every one
  of our 71 standings entries traced byte-for-byte to the file that produced it
  (NE@SEA to the replay-anchored review CSV `cf33f3e5…`, SF@LAR to
  `review_final`, Week 1 Classic to `DKEntries_NFL_Week1_LATESWAP_FINAL.csv`
  and not to `build_portfolio.py`, DAL@NYG to `REVIEW_v6`, DEN@KC to
  `v8_FINAL`). Lineup-derived ownership reconciles to DraftKings `%Drafted` at
  0.002 pp once Classic base and FLEX rows are summed and blanks are kept in the
  denominator. Headline measurements: Walker-less DEN@KC lineups paid 0 of
  99,349; the NE@SEA 23-way tie paid $54,065.22 per entry; ≥85% single-player
  concentration carried 1.4x to 12x the zero-paid rate across 8,007 multi-entry
  field portfolios in four games; exactly one pass catcher with the rostered QB
  and $1 to $500 left were the only construction features with top-1% lift ≥1.1
  and below-median lift <1 in all four Showdown games.
- `docs/STANDINGS_GREENFIELD_FINDINGS_2026-09-15.md` (SHA-256
  `d7250f0d575e1e957c1bad25da7dd9a5ff0edc2aec3c66c463661380d4751543`), the
  same-day ownership, coverage and construction report; the two agree on every
  shared figure.

Changed:

- `backlog.md`: new `Reprioritized development program — 2026-09-15 (prize tail
  first)` inserted above the 2026-09-10 program, which is marked superseded in
  ordering only. New chunks P0, P0b, P1, P2, P3a, P3b, P4a, P4b, P4c, P5, P6,
  each sized for one Claude Code session with read list, files, scope,
  acceptance and hand-back; C3's native Excel acceptance split out as `C3X`
  (`DEFERRED`, pending Ben's ruling); C4 re-sequenced behind P2; Q2 to Q7 and
  QC1 retained as the promotion track absorbing the P chunks. A disposition
  table records accept/modify/defer for each greenfield recommendation; none
  rejected outright, item 7 deferred to accrual. Tracker-protocol pointer
  updated; a 2026-09-15 `Next action` entry names `P0` and `P1` as `READY`.
- `IMPLEMENTATION_STATUS.md`: pointer paragraph for the 2026-09-15 program.
- `CLAUDE.md` restructured for Claude Code as the development surface (306 →
  183 lines): permanent boundaries, release truths and a compressed lock-clock
  ruling stay; the eight-step "run the slate" procedure and the full 2026-09-12
  ruling text moved verbatim into `docs/COWORK_RUNBOOK.md` ("Moved from
  CLAUDE.md on 2026-09-15"), whose one pointer to the ruling was updated; a new
  "Developing in Claude Code" section carries commands, the eight-step session
  protocol, etiquette and gotchas. Maintainer notes sit in a stripped HTML
  comment.
- New `.claude/settings.json` (allow: status/diff/log/test/doctor; ask: add,
  commit, push, merge, rebase, setup; deny: `git add -A`/`.`, reset --hard,
  checkout --, restore, clean, stash, force push, amend, `rm -r`, and `Edit` on
  `data/standings/inbox/**`, `data/runs/**/inputs/**`, `tests/fixtures/supplied/**`,
  `uv.lock`). New path-scoped `.claude/rules/` (immutable-data, contracts,
  selection-and-objective, operating-path, tests, ledger). New skills
  `/dev-session`, `/verify`, `/close-out` in `.claude/skills/`, all
  `disable-model-invocation`.
- `.gitignore`: `CLAUDE.local.md`, `.claude/settings.local.json`.
- `backlog.md` tracker protocol: the session-start read list now names
  `CLAUDE.md`, the current program and chunk brief, and the changelog head,
  with the spec opened on citation rather than by default.
- `docs/session-prompts/P0-standings-grading-harness.md`: the first prize-tail
  session prompt, written thin (goal, constraints, pointers, acceptance) against
  the thick brief in `backlog.md`.
- Token discipline (same day, after measuring that a session following the
  old read list spent ~80,000 tokens on ledgers before touching code):
  `backlog.md` split into a live queue (160 KB → 45 KB) plus
  `docs/backlog-archive/backlog-history-through-2026-09-14.md` (DONE briefs
  DEV0/Q1/Q1B/Q1C/C1/C2, Baseline, punch list, S0-S10, post-review tranches,
  pre-09-14 Next-action entries and the R16-R18 proposals, all verbatim); the
  eleven P-chunk briefs moved verbatim to `docs/chunks/<ID>-<slug>.md` with a
  status/brief index left in place; `changelog.md` split into live (163 KB →
  24 KB) plus `docs/changelog-archive/changelog-through-2026-09-14.md`. A
  line-by-line conservation check found zero original lines missing from the
  union of live and archive files. `CLAUDE.md` gained a *Token discipline*
  subsection (read ledgers by section, never Read a data export, `explorer` and
  `reviewer` subagents, `git diff --stat` first) and stays at 200 lines.
  `.claude/settings.json` now also denies `Read(data/standings/inbox/**)`;
  `.claude/agents/explorer.md` (read-only, sonnet) and `reviewer.md` (fresh-context
  diff review) added; the ledger and immutable-data rules and the session skills
  point at the new locations.

Verification: report tables checked for pipe consistency; every quoted figure
re-derived from the standings pickles in the research session (device VM,
Python 3.10, pandas 2.3.3, numpy 2.2.6); backlog and status files rewritten
with their original CRLF line endings intact.

### 2026-09-14 (Q1C): the pre-lock manifest emitter, and four gates no producer could clear

Merged to `main` on 2026-09-14 in `4313455fcd8fd722b699a799dbe19dff19c1be68`
(PR #13), in one commit `7edddee` with Q1B below and the previously uncommitted
C3 tranche. The three were not separable: `prior_review.py` imports
`classic_review.py`, which had never been committed, and nine files carry changes
from more than one tranche. **Merging C3 was not accepting it** — it remains
`BLOCKED` on native Excel open/recalculate/save/reopen acceptance.

Ran natively on Ben's Windows machine against the Windows `.venv` throughout.

Added:

- `src/nfl_dfs/prelock_manifest.py` — builds and writes
  `nfl_prelock_run_manifest_v1`. Every hash it records is one the run already
  computed while doing the work, never recomputed from a path: a path can be
  swapped between the run and the emitter, and a recomputed hash would silently
  bless the swap. Canonical sorted-key JSON through a temporary file, so the same
  run writes byte-identical bytes.
- `tests/test_prelock_manifest.py` (19 tests), including the end-to-end proof:
  a real Classic `prior_review` run freezes a manifest, a settlement request
  binds it, `settle` captures the package and `settle --replay` reproduces it.
  A separate test proves the Showdown exit freezes one too, because a manifest
  emitted from only one of the three success paths would leave the other two
  unsettleable — the exact failure Q1B found in the repo.

Changed:

- `src/nfl_dfs/prior_review.py` emits the manifest from all three success exits
  — Showdown, Classic C1/C2 and Classic C3. Emitting from only one would have
  left the other two unsettleable, which is the exact failure Q1B found. It is
  emitted for a `DO_NOT_UPLOAD` run on purpose: every prior-only run ends that
  way, and those are the review lineups Ben actually enters by hand, so a
  manifest gated on an uploadable package would never be emitted at all. It
  changes no release truth. The run also now records the salary and entry
  *paths* beside the hashes it already kept, so a request can bind the exact
  bytes the manifest names.
- Classic writes `assignments.csv`. `write_assignments_csv` gained a `mode`
  parameter and Classic uses the nine-slot geometry `lineups.read_assignment_csv`
  reads. Without it a Classic run could not bind an assignment into a manifest at
  all, because its selection existed only as `classic_assignment.json`.
- `scripts/make_settlement_request.py` resolves zero scenario banks for a
  `PRIOR_ONLY` manifest and still blocks, naming the status, for any other.
- The emitter refuses when a JSON prediction declares a schema version other than
  the one it expects. Settlement re-reads those files and compares versions, so
  without this check a drifted expectation would write a manifest asserting
  something false and fail at capture days later rather than at the run.

Contract corrections, each on Ben's explicit ruling before it was made. All four
were gates that no honest producer could clear, measured against Q1's own passing
fixture by removing, one at a time, exactly what a prior-only run lacks:

- **`field_size` is no longer compared** between the manifest and the request.
  This was never `prior_review`-specific. `_validate_prelock_manifest` required
  the manifest to record a field size equal to the request's, and
  `_prepare_settlement` separately required that to equal the settled standings
  row count — so a pre-lock manifest had to record the *settled* field size,
  which nothing can know before lock. The legacy `build` path records the
  operator's `--field-size` assumption and would have failed identically the
  first time a contest did not fill; 193391013 was advertised at 133,000 and
  settled 126,020. Q1's fixture only passed because its synthetic contest has
  `field_size` 2 and the operator owns both entries. The manifest now records the
  assumption with a `field_size_basis` label, and the run brief reports
  `assumed_field_size` beside `settled_field_size` as a Q6 diagnostic. Contest
  id, draft group, mode and entry fee stay hard identity checks, unchanged.
- **The payout hash and version are optional in the manifest**, and only in the
  manifest. The request still binds the payout bytes by SHA-256 either way.
- **`objective`, `advertised_prize_value` and `ticket_face_value` are compared
  when the manifest records them**, and not required when it does not.
- **A request may bind zero scenario banks if and only if `MODEL_STATUS` is
  `PRIOR_ONLY`**, enforced by a `SettlementCaptureRequest` validator so the
  relaxation cannot reach a prospectively-validated model. A degenerate
  one-scenario bank carrying the point estimates was considered and rejected: a
  bank with no distribution invites being read as one.

Test changes, with their reasoning:

- Two Classic suites asserted that no `assignments.csv` existed, and the C2
  prohibited-path guard banned `write_assignments_csv` outright. That file is not
  an upload shape — no Contest ID, Contest Name, Entry Fee or instructions block,
  so DraftKings would reject it, and Showdown's prior review has always written
  the same file. The `DK_UPLOAD_*` and `DK_REVIEW_ENTRY_*` prohibitions are
  unchanged and still checked. The blanket ban became a spy asserting the writer
  is called with `mode=CLASSIC`, which is strictly stronger: it proves the
  geometry is right rather than only that nothing happened.

Measured evidence:

- Complete pinned suite: **735 passed, 1 failed, 1 skipped in 198.190s** (737
  collected, 0 errors), against the Q1B measurement of 715 passed, 1 failed, 1
  skipped (717 collected). Exactly the 20 tests this tranche adds — 19 new
  pre-lock manifest tests plus one net from splitting a builder scenario test in
  two — with the same single pre-existing failure and no regression. That failure
  is the `test_live_check_refuses_once_a_selected_player_has_locked` time bomb
  described in the Q1B entry below: a hardcoded evidence expiry of
  2026-09-14T00:00Z that has now passed, identical in `HEAD`, unrelated to this
  work and still unfixed.
- Composition on a realistic `cowork-run` tree: the request builder resolves
  `prelock_manifest`, `predictions`, `assignments`, `scenarios`,
  `release_truths`, `salary`, `entries`, `entry_fee`, `draft_group`, `mode`,
  `scoring`, `metric_registry` and `owned_entry_ids`, leaving exactly two
  blockers — `PAYOUT_TABLE_ABSENT` and `NORMALIZED_STANDINGS_ABSENT`. Both are
  facts only Ben supplies at settlement time, and both are correct refusals.
- A replayed run at a pinned `as_of` freezes a byte-identical manifest. The
  emitter stamps the run's own clock rather than `now()` for exactly this reason,
  and the assignment path it records is run-relative, never absolute — both were
  real determinism defects caught by that test.

Limitations:

- **The corpus still holds zero settled contests.** Q1C makes the next slate
  settleable; it settles nothing. A real contest still needs its payout table and
  its standings pull, and must have come from a single-contest reserved-entry
  template — 16 of Ben's 18 did not.
- **It recovers none of the eighteen contests already played.** A pre-lock
  manifest records what was predicted before lock; writing one afterwards would
  be a fabricated prediction. Those contests stay dispositioned.
- The end-to-end capture and replay is proven on a synthetic complete field where
  the operator owns every entry. No real contest has been settled.
- `MODEL_STATUS=PRIOR_ONLY` and `RELEASE_DECISION=DO_NOT_UPLOAD` are unchanged,
  and emitting a manifest changes neither. Nothing here says anything about model
  quality.

### 2026-09-14 (Q1B): standings intake, the settlement request builder, and why no contest can settle

Ran natively on Ben's Windows machine against the Windows `.venv` throughout, via
`.\nfl.ps1 test` and `.venv\Scripts\python.exe`. No Cowork container, no
`.cowork-venv`, no staging. The two Cowork venvs were never mixed.

Added:

- `scripts/file_standings.py` — standard-library, no-network normalizer from a
  raw DraftKings standings export to `nfl_standings_csv_v2`, content-addressed
  under `data/standings/normalized/<contest_id>/<sha256>.csv` with a sibling
  `nfl_standings_normalization_v1` manifest recording the raw SHA-256, the
  normalized SHA-256, the bound salary and payout hashes, and every
  normalization decision. The raw inbox file is read, hashed and left byte-
  identical; a test asserts both its bytes and its mtime are unchanged after a
  full run. `--survey` reads an export without any binding and reports the
  observed field size, which is otherwise nowhere on disk.
- `scripts/make_settlement_request.py` — builder for `nfl_settlement_request_v1`.
  Resolves every field from frozen bytes and refuses by name for anything it
  cannot. Release truths are copied out of the frozen pre-lock run rather than
  re-derived, so settlement can never report a better decision than the slate
  shipped with. Salary and entry snapshots are classified by parser, never by
  filename; prediction and scenario artifacts are located by the SHA-256 the
  pre-lock manifest itself declares, so the wrong file cannot be bound.
- `tests/test_standings_normalizer.py` (25 tests) and
  `tests/test_settlement_request_builder.py` (18 tests).

Changed:

- `scripts/standings_checklist.py` now distinguishes `filed` (a raw export in the
  inbox), `normalized` (an `nfl_standings_csv_v2` on disk) and `settled` (a
  complete Q1 settlement bundle, read out of the bundle rather than inferred from
  a directory name). Before this, dropping any file into the inbox satisfied the
  checklist and nothing else. It also now reports raw, normalized and bundle
  presence per contest *independently of status*, because a disposition is a
  ruling about workflow and not a claim that the bytes are gone — all 18 raw
  exports are on disk and every contest is dispositioned.
- `tests/test_standings_checklist.py` grew from 14 to 22 tests. One existing
  assertion changed because the section heading did (`Filed or dispositioned` →
  `Filed, normalized, settled or dispositioned`). The fixture now also isolates
  `NORMALIZED_DIR` and `SETTLEMENTS_DIR`; without that the tests read the real
  repo's state and were only passing because the synthetic contest IDs did not
  collide with a real one.
- `.gitignore` ignores `data/standings/inbox/*` and `data/standings/normalized/*`
  on the existing `data/runs/*` precedent, keeping a `.gitkeep` in each. The 18
  raw exports and one normalized field are ~58MB of bulk operator data. The small
  records — `dispositions.json` and the rendered checklists — stay visible.
- All 18 entered contests dispositioned `placeholder` with per-contest reasons,
  per Ben's 2026-09-14 ruling.

Measured evidence:

- **Complete pinned suite, Windows, first confirmation on this box since
  2026-09-12.** Baseline before any change: **664 passed, 1 failed, 1 skipped**
  (666 collected). After Q1B: **715 passed, 1 failed, 1 skipped in 368.732s**
  (717 collected, 0 errors) — exactly the 51 tests this tranche adds (25
  normalizer, 18 builder, 8 checklist), with the same single pre-existing
  failure and no regression. The expected 644 in the session prompt was low: the
  tree carries 22 more uncommitted tests than that estimate.
  The bare `pytest -q` invocation errors at fixture setup on this box and must be
  run through `.\nfl.ps1 test`, which supplies the `--basetemp` and `cache_dir`
  the default locations cannot provide; a run killed that way is a tooling
  artifact and is not a failure.
- **The one baseline failure is pre-existing and is a time bomb that came due
  today.** `tests/test_w6_live_preflight.py::test_live_check_refuses_once_a_selected_player_has_locked`
  hardcodes `expires_at=datetime(2026, 9, 14, tzinfo=timezone.utc)` and calls its
  `_certified` helper without pinning the certification clock. `certify_upload`
  grades evidence at the live clock, so as of today that evidence has expired and
  certification correctly returns `DO_NOT_UPLOAD`, failing the helper's own
  `assert manifest.release_decision.value == "CERTIFIED_UPLOAD_PACKAGE"`. The
  line is identical in `HEAD`, so it is not a Q1B regression, and it will fail
  every day from now on. The fixture's own docstring already documents the
  repair: pass `monkeypatch` and `now`. Left unfixed — it is a certification test
  and outside Q1B's stated scope — and raised here rather than patched quietly.
- **Reference evaluator, fresh measurement** (design answer 2): 133,000 synthetic
  entries refused `REFERENCE_RUNTIME_BUDGET_EXCEEDED` at the registered 10.0s
  budget and settled exactly in **27.868447s** at 30.0s (177,477 work units,
  95,515,201 peak traced bytes); 200,000 synthetic settled in **22.582837s**
  (244,496 work units, 142,015,359 peak traced bytes). Runtime is not monotonic
  in field size — it tracks tie and duplication structure — so field size alone
  does not predict whether a contest settles in budget. The builder's default
  `max_runtime_seconds` is raised 10.0 → 180.0 on that evidence; `max_entries`
  stays at the registered 200,000.
- **Real normalization**: contest 193391013, 126,020 entries, normalized end to
  end in 5.908s wall including the reference settlement. 36,274 `Points` rows
  rounded, largest adjustment 0.00001. 220 entries never submitted a lineup. 757
  entries across 9 tie groups settle to a fractional cent share; half-even
  rounding leaves a 33-cent residual, reconciling 224,999,967 paid cents against
  the advertised $2,250,000.00.
- **Points rounding justified, not assumed**: across all **1,415,500** entry rows
  in the 18 exports, the largest raw-to-2dp gap is **0.00003** and
  `ROUND_HALF_EVEN` never disagrees with `ROUND_HALF_UP` on any row. Rank
  agreement against DraftKings' own `Rank` column is 100% at 2dp on every contest
  checked (71/71, 237/237, 475/475, 9512/9512, 5945/5945) and partial on the raw
  values (70/71, 223/237, 430/475, 6415/9512, 4195/5945).
- **Lineup reconstruction verified against the engine**: the canonical keys the
  normalizer rebuilds for Ben's two entries in 193391013 match exactly those
  `lineups.validate_lineup` builds from the `excl20` review export, and differ
  from those built from `data/runs/20260909-showdown-ne-sea/review/assignments.csv`.
  The standings export can therefore identify which stored assignment actually
  reached DraftKings.
- **Observed field sizes** (from the export row counts, which is the only place
  the true settled field size exists): 193028206 832,342; 195390868 178,359;
  193391013 126,020; 195390867 83,234; 195526142 59,453; 195390870 47,562;
  195526144 and 195526145 35,671 each; 195390889 9,512; 195526163 5,945;
  195520918 475; 195379585, 195507184, 195521582 and 195641911 237 each;
  195642262 190; 195384501 71; 195379668 47. 193391013's observed 126,020
  disagrees with the operator-stated 133,000 recorded in
  `data/runs/20260909-showdown-ne-sea-live-2206z/contest/contest_facts_operator_supplied.json`;
  the observed count is the settled field and the disagreement is reported, not
  reconciled away.

Findings, all recorded under Q1B in `backlog.md`:

- **No `data/runs/` snapshot holds an `nfl_prelock_run_manifest_v1` or an
  `nfl_scenario_bank_v1`, for any of the 18 contests.** Only the legacy `build`
  command writes them; the `prior_review`/C1-C3 path that produced every contest
  Ben has entered never has. Those 18 are permanently unsettleable, and a
  pre-lock prediction record cannot be written after the fact. The repair is an
  emitter on the path Ben actually uses; it makes the next slate settleable and
  recovers none of these. Flagged `[BEN: ...]` as its own tranche because it
  touches `prior_review.py`, which Q1B was scoped out of.
- **`nfl_standings_csv_v2` cannot represent a real DraftKings field, in two
  independent ways.** Entries that paid in and never submitted a lineup (11 of 18
  exports carry them) have no valid representation, and exact tie splits that are
  not whole cents (757 entries in 193391013 alone) cannot be held in a cent-exact
  column. The second is the more serious: `settlement._prepare_settlement`
  compares the evaluator's exact `Fraction` against the file's integer cents for
  every field row, so any contest with an uneven tie split can never clear
  `STANDINGS_PRIZE_MISMATCH` whatever the intake writes. Both are refused by
  default with an explicit, default-off, fully labelled opt-in; neither contract
  was changed. Flagged `[BEN: ...]`.
- **DraftKings exports no per-entry prize**, so the `Prize` column is derived
  from the payout table by the reference evaluator and labelled as such. The
  downstream `STANDINGS_PRIZE_MISMATCH` check is therefore not independent
  evidence on any file this tool writes, and that is stated rather than implied.
- **16 of 18 contests** came from multi-contest reserved-entry templates that
  `settlement.require_single_contest` refuses, and **17 of 18** have no payout
  table on disk.

Limitations:

- **The validation corpus holds zero settled contests.** Q1B did not change that
  number and could not: the missing pre-lock manifests are unrecoverable. It
  changed the corpus from "zero for unknown reasons" to "zero for four named,
  measured reasons, one of which has a known repair".
- The `--request` → `--replay` round trip is proven on a **synthetic** complete
  slate, not on a real contest. No real contest can reach capture.
- One contest's result was measured and is reported as such. It is not evidence
  that the engine picks good lineups, it licenses no EV, ROI or calibration
  claim, and one slate is not a sample.
- `MODEL_STATUS=PRIOR_ONLY` and `RELEASE_DECISION=DO_NOT_UPLOAD` are unchanged.
  Landing a settled slate would change no release truth, and none landed.
Entries dated 2026-09-14 (follow-up and checklist) and earlier, back to 2026-09-01, moved verbatim to `docs/changelog-archive/changelog-through-2026-09-14.md` on 2026-09-15. Append new entries directly under `## Unreleased`; when this file passes roughly 500 lines, move the oldest entries to the archive rather than letting sessions read them.

## Entry template for future sessions

Copy this structure under `Unreleased` and replace every placeholder:

```markdown
### YYYY-MM-DD — Sx: short outcome

Changed:

- Exact behavior changed and files involved.

Verification:

- Exact command or check: exact result.
- Full suite: exact pass/fail count.
- `git diff --check`: pass/fail.

Remaining blockers:

- Named blocker, or `None for this backlog item`.

Tracker updates:

- Sx: `OLD_STATUS` -> `NEW_STATUS`.
- Sy: `BLOCKED` -> `READY`, if dependencies and acceptance gates genuinely passed.

Claims explicitly not made:

- No live-slate, calibrated-EV, or upload-readiness claim unless independently proven by the work recorded here.
```
