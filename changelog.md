# NFL DFS Implementation Changelog

This file records completed implementation work and verification evidence for the sessions in `docs/ROADMAP.md`. Keep entries factual and append new dated sections beneath `Unreleased`. Do not describe planned, diagnostic, synthetic, or structurally legal work as live-certified or upload-ready.

## Unreleased

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

### 2026-09-22: the depth-role package refused its own capture on Windows

Found by Ben running `.\nfl.ps1 test` on his own machine after a sync:
**`25 failed, 1045 passed, 1 skipped in 303.33s`**. The Linux suite was green at
`1070 passed, 1 skipped` on the same commit. No release truth changed.

#### The defect

`scripts/make_offensive_role_evidence.py:239-242` took a digest over an
excerpt's bytes and then wrote the file in text mode:

```python
digest = hashlib.sha256(excerpt.encode("utf-8")).hexdigest()
capture.write_text(excerpt, encoding="utf-8")
```

`Path.write_text` opens with `newline=None`, which translates `\n` to
`os.linesep`. On Windows the bytes on disk are therefore **not** the bytes that
were hashed, so `sha256_file()` disagrees and the package refuses the capture it
had just written: `QB_DEPTH_SOURCE_HASH_MISMATCH`. 24 of the 25 failures.

This is not cosmetic. `P7` exists to resolve who is actually starting, after the
2026-09-20 slate rejected three starting quarterbacks as backups. It could not
run at all on Windows, which is the only surface that operates slates. Every
other hash in that module already read bytes (`:104`, `:124`, `:420`); the write
was the lone inconsistency, and `make_classic_weather_evidence.py` was never
affected because it uses `shutil.copyfile`.

The 25th failure was a test asserting a path `.endswith("scripts/session_probe.py")`,
which is backslashes on Windows.

#### Changed

- `scripts/make_offensive_role_evidence.py`: `write_bytes(excerpt.encode("utf-8"))`.
  Bytes in, identical bytes out, on every platform.
- `tests/test_qb_depth_roles.py`: the two helpers that build packages the same
  way, so fixtures stay byte-faithful.
- `tests/test_session_probe_gate.py`: compares `Path.parts` instead of a joined
  string, so it still catches the rename it exists for without failing on a
  separator.

#### The structural finding, and the fix that matters

`.github/workflows/ci.yml` ran `ubuntu-latest` only. **Windows is the slate
environment and had never been tested.** A byte, path or newline assumption that
breaks only on Windows was invisible to every check this repository ran, and
this one survived from P1 through P7 being merged green.

A `windows` job on `windows-latest` now runs the pinned suite. It gates nothing
the Linux job already gates; it exists so the next defect of this class is found
by CI rather than at a lock clock.

#### Verification

- Complete pinned suite on Linux: `1070 passed, 1 skipped in 156.21s (0:02:36)`,
  unchanged from before the fix, which is exactly the point below.
- Focused before the CI job was added:
  `tests/test_qb_depth_roles.py tests/test_session_probe_gate.py` green.
- `.github/workflows/ci.yml` parses; jobs are `boundaries`, `suite`, `windows`,
  `protected-paths`.

**Not verified here, and stated rather than implied:** this container is Linux,
and the tests that failed pass on Linux both before and after the change. A
Linux run is therefore *not* evidence the fix works. The proof is the new
`windows` CI job on this pull request, and Ben re-running `.\nfl.ps1 test`,
where the expected result is `1070 passed, 1 skipped` with zero failures.
### 2026-09-22: the Windows checkout gets a sync command that keeps itself current

No engine module, contract or evidence gate changed. Every path still ends
`MODEL_STATUS=PRIOR_ONLY` and `RELEASE_DECISION=DO_NOT_UPLOAD`. No run executed.

#### Why

Measured on Ben's machine on 2026-09-22: the Windows checkout was **59 commits
behind** `main`, sitting on `codex/p1-salary-divergence-role-evidence` with 13
modified files from an abandoned session, and had never seen the CI workflow,
the hooks, the rules directory, `repo_state.py`, or any chunk from P1 onward.
Nothing told it to catch up and nothing told Ben how.

#### Added

`sync.ps1` at the repository root. Fetches, reports what is incoming, and
fast-forwards `main`. It is deliberately conservative, because `CLAUDE.md` says
this tree is often intentionally dirty with user-owned work: it never stashes,
resets, cleans or discards, and `git pull --ff-only` can neither invent a merge
commit nor rewrite history, so every failure mode ends with nothing changed. It
stops rather than act when the checkout is not on `main`, and it names
`.\nfl.ps1 setup` when `uv.lock` or `pyproject.toml` moved, because
`uv sync --locked` fails outright in that case without saying why.

#### The design decision worth recording

**The PowerShell profile holds a pointer, not a copy.** The profile line is
`function Sync-NflDfs { & '<path>\sync.ps1' @args }`, so the script arrives with
every sync and improves itself. A copy pasted into a profile freezes on the day
it was pasted, and a second machine starts from nothing. `$PSScriptRoot` locates
the repository, so the profile line holds the only path anywhere.

#### Changed

`docs/CLAUDE_CODE_SETUP.md` gains "Keeping a Windows checkout in sync" under
`## One-time, per machine`, with the profile line, the three stop conditions and
what each means, and why this is not put on a schedule.

A separate `docs/SYNCING.md` was considered and rejected. That file already
exists for things only Ben does on his own machine, and X5's finding on
2026-09-20 was that a document nothing tells the operator to open may as well
not exist; a fifth setup file would repeat it.

#### Verification

- `sync.ps1` is **not executed by any test**, and this container has no
  PowerShell, so it is not machine-verified here. What it does carry is a live
  run: the identical logic was pasted into Ben's PowerShell on 2026-09-22 and
  performed the real 59-commit fast-forward, including correctly refusing while
  the checkout was on a feature branch and correctly leaving 13 modified files
  untouched. `sync.ps1` differs from what ran only in taking its path from
  `$PSScriptRoot` instead of a parameter default.
- The git commands it relies on were checked against this repository:
  `git status --porcelain` for the dirty test, and
  `git diff --name-only <before> <after> -- uv.lock pyproject.toml` for the
  dependency test, whose negative result is a true negative because only the
  initial commit has ever touched either file.
- Complete pinned suite: `1070 passed, 1 skipped in 158.01s (0:02:38)`.

#### Left open

No `sync.sh`. A cloud session clones fresh and is current by definition.
`sync.ps1` has no test; a PowerShell script cannot be exercised by this
repository's pytest suite on Linux, and inventing a fake for it would test the
fake.

### 2026-09-22: a guard for the one part of the roof resolution that cannot keep itself current

Follows a post-merge review of PR #34 (`803618a`, R26). The review found the
change sound and is summarized below; two follow-ups came out of it and are
implemented here. No release truth changed. Every path still ends
`MODEL_STATUS=PRIOR_ONLY` and `RELEASE_DECISION=DO_NOT_UPLOAD`.

#### What the review checked, and what it found

R26 resolves a blank `roof` from a retractable venue's own recorded history, so
a game played indoors stops demanding an `api.weather.gov` capture. That is
close enough to "inventing an observation to clear a gate" that it was verified
in code rather than taken from the description.

It does not invent one. `prior_review.py:696-708` returns the resolved roof with
`freeze_weather_state=None`, `freeze_source_uri=None` and
`freeze_observed_at=None`: it answers whether a roof is over the game and leaves
every observation field null, so nothing claims a human looked at the weather.
Precedence is right in both consumers, `priors.py:1482`
(`if not roof and not operator_weather_state`) and `prior_review.py:693`
(`if not normalized and not attributed and not state`), so a schedule-recorded
roof and a real operator capture each outrank the derived value. It fails closed
on every edge: `closed != total` rejects an `outdoors` game as well as an `open`
one, under eight completed games resolves nothing, and an unlisted venue
resolves nothing.

One concern was formed and then withdrawn. The two-season window looked
possibly post-hoc, since PR #34's own measurement shows a four-season window has
every one of these venues opening the roof, making unanimity an artifact of the
narrow window. It is not post-hoc: `venues.season_window()` returns
`{prior_season, season}`, the same pair the prior package already uses for its
era string `{season}_REG_PRIOR_FROM_{prior_season}_REG`. The window is inherited
from the run's own era definition rather than chosen because it resolves.

#### Added

- `venues.unlisted_blank_roof_teams()`. Names home teams carrying an **unplayed**
  game with no recorded roof that are absent from `RETRACTABLE_ROOF_HOME_TEAMS`.
  A played row with a blank roof is missing data, not a signal about the venue,
  and is ignored.
- `scripts/check_venue_roof_set.py`. Runs that against a current schedule.
  Exit 0 names the listed set and the row count; exit 1 names the unlisted
  venues; exit 2 covers a missing file, an empty file and a file with no `roof`
  column, so a broken invocation is never mistaken for a clean run. It reads
  bytes already on disk and fetches nothing.
- `tests/test_check_venue_roof_set.py`, 14 test functions collecting 18 cases
  (one is parametrized over the five listed venues): the listed venues, an
  unlisted venue, a played blank, a recorded roof, a blank home team, duplicate
  and lower-cased teams, the season window, no rows, and the script's four exit
  codes.

#### Why a script and not a test

`RETRACTABLE_ROOF_HOME_TEAMS` is a hand-maintained stadium fact. It is correct
for the five venues that exist today (ARI, ATL, DAL, HOU, IND; SoFi's fixed
canopy is correctly excluded) and goes stale silently the day a sixth
retractable roof opens, because that venue's blanks would resolve to nothing and
the engine would quietly go back to demanding a capture for an indoor game. That
is a miss rather than a wrong answer, which is why this is a diagnostic and not
a refusal.

A test cannot catch it. A committed fixture is a snapshot and a snapshot cannot
contain a stadium that does not exist yet, so a fixture-based subset assertion
would only re-prove what was true when the fixture was written. Only a run
against a current schedule catches it. Surfacing it inside the run path instead
was rejected as disproportionate: the proposal manifest is the contracted
`nfl_prior_identity_proposal_v2`, so an added key means a v3 bump, and
`priors.py` is a pure library with no stderr or logging to borrow. A script
matches how this repository already handles this class of check
(`session_probe.py`, `check_protected_paths.py`, `record_verify.py`).

#### Changed

`backlog.md`: the R24 stanza gains a coupling note. R26 narrows how often R24's
gate bites but does not answer it, and it changes what R24 would be built on.
Before R26 a blocked gate meant a missing enum, an obvious absence. After R26 a
resolved-from-history roof is a plausible value nobody observed, so if weather
ever reaches a number, a derived roof would feed it silently, which is harder to
notice than no number. The registry that the R24 recommendation is conditional
on must therefore cover the derived-roof path, not only the capture path. R24
stays `BLOCKED` on Ben; nothing is implemented against it.

#### Verification

- Focused: `sh ./nfl.sh test tests/test_check_venue_roof_set.py tests/test_venues.py`
  `34 passed in 0.20s`.
- Complete pinned suite: `1070 passed, 1 skipped in 158.55s (0:02:38)`, exactly
  18 above the baseline, which is the 18 cases added.
- Baseline on `cdf7865` before this change, measured in this container:
  `1052 passed, 1 skipped in 170.72s (0:02:50)`.

Not done, and stated rather than implied: the script has not been run against a
live schedule. This container holds no frozen `games.csv`, and fetching one
would go through `sources.py` with the capture obligations that carries, which
is not worth incurring for a demonstration. The exit codes are proven by tests
against written files.

Entries dated 2026-09-14 to 2026-09-21 moved verbatim to `docs/changelog-archive/changelog-2026-09-14-through-2026-09-21.md` on 2026-09-22; entries dated 2026-09-14 (follow-up and checklist) and earlier, back to 2026-09-01, moved to `docs/changelog-archive/changelog-through-2026-09-14.md` on 2026-09-15. Append new entries directly under `## Unreleased`; when this file passes roughly 500 lines, move the oldest entries to the archive rather than letting sessions read them.

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
