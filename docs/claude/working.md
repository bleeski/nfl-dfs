<!-- Moved verbatim from CLAUDE.md on 2026-09-27 (Ben: relax self-modification,
allow recursive self-improvement). Claude may change this file on its own
authority and merges on green; the boundaries stay in CLAUDE.md. -->

# Developing in Claude Code

## Commands

- Windows: `.\nfl.ps1 setup|test <pytest args>|doctor|<cli>` on `.venv`. Linux:
  `sh ./nfl.sh <same>` on `.venv-linux`. Both pin pytest's temp and cache roots;
  pass pytest flags after `test`, never a bare `-p`, never a second `-q`. Never
  mix the two venvs in one session.
- Focused tests first (`-x --tb=short`), then the complete suite: ~5 min on Linux,
  ~10 on Windows (CI, 2026-09-25), past the 600000 ms tool maximum. Run it in
  the background on Windows; a run killed by a timeout is a tooling artifact, not a
  failure. Record the result: `python3 scripts/record_verify.py --from-log <log>`.
- Python 3.13.7 under `uv.lock`; `uv sync` needs `README.md` present.
  `NFL_DFS_TLS_ALLOW_NONSTRICT_CA=1` is the approved opt-in and clears only
  `VERIFY_X509_STRICT`. Container facts: `docs/CLAUDE_CODE_SETUP.md`.
- CI runs the pinned suite and `tests/test_repo_boundaries.py` on every push,
  and the protected-path check on every pull request event, labels included.
  Green CI replaced Ben reading each diff, so never push speculatively.

## Session protocol: `docs/ROADMAP.md` §2.1, plus these

- Never reset, clean, stash or reformat a dirty tree; it is often user-owned work.
- The claim commit (row `In Progress`) turns `tests/test_roadmap_queue.py::test_the_quick_start_names_the_first_startable_session`
  red, because §1 still names the row just claimed and an `In Progress` row is not startable (Session 17's claim
  commit, 2026-09-29: `suite` red on that one test). Either rewrite §1 to the next startable row in the claim
  commit, or accept that one red and let the close-out push, which rewrites it, clear it. Never merge on the claim commit.
- Multi-file session: the plan, with assumptions and tradeoffs, goes in the task
  file and work starts; no plan-approval wait (Ben, 2026-09-23). Ask Ben only for
  facts he alone has (a ruling, a file, an unset threshold), or leave a
  `[BEN: ...]` flag and continue; decide judgment calls and record why.
- One session per branch (`claude/<sNN>-<slug>` or the one assigned). Touch only
  what the card names; mention adjacent dead code instead of fixing it. Open the
  spec and contracts only when the card names them.
- Fixtures whose freshness matters pin their clock (`now`). Verify with
  evidence, compile/import included; never summarize a run you did not see end.

## Token discipline

- Ledgers by section, never whole: `docs/ROADMAP.md` §1, §2.1 and the one card;
  `changelog.md` first 80 lines. Big references (`DFS_SYSTEM_GREENFIELD_SPEC.md`,
  `docs/DATA_CONTRACTS.md`, `docs/RUNBOOK.md`) and the archive directories are
  grepped, never read.
- Never Read a standings export, salary CSV, run artifact or test fixture into
  context; print a schema-level summary with a script. `.claude/settings.json`
  denies `Read` on the inbox for this reason.
- A wide multi-file sweep, when you need the conclusion and not the text:
  `explorer`. Pre-close-out diff review: `reviewer`. Both answer from their own context.
- `git diff --stat` before `git diff`; one session per conversation, then `/clear`.

## Showdown judgment pass (Ben, 2026-10-01; second correction)

Ben corrected the same thing twice: PHI@CHI left Case Keenum out and PIT@CLE left Deshaun Watson out, each because he has no
prior-season row. The engine scores only people it has a row for, so a starter without one never reaches selection
(`selection.py` puts every role-gated person in `run_excluded`, which binds every row, and a thesis whose only Captain is excluded is
dropped, `portfolio_policy.py`). The deterministic layer cannot be asked to add him. The judgment is yours, it runs every slate, and
it runs before the handoff without being asked. Since Session 51 the engine rates a starter who has current-season rows before the
slate (nflverse in-season file, no look-ahead), so this pass is for whoever v3 still leaves out: a true cold start or a same-day
promotion. Since Session 53 `run-slate` captures the QB depth package itself and keeps every backup quarterback out of every Showdown
row, so list the backups the report names (`showdown_backup_qb_default`) rather than rebuilding that rule by hand; a limitation named
`QB_DEPTH_CAPTURE_*` or `SHOWDOWN_BACKUP_QB_UNEVALUATED` means the rule did not run for that team and the check is yours. Since Session 54 a
quarterback the depth evidence declares the starter is selectable with no history (finding
`OFFENSIVE_DEPTH_DECLARED_STARTER_NO_HISTORY`), so the left-out list is now whoever the chart does not declare. Until Session 52 gives the
rest an input channel, it is manual.

- **Left-out starters.** List every person a role gate or DK status kept out of the pool who a source names a starter, the depth-chart
  quarterback first. Roster each by construction or write why not in the handoff. A starting quarterback is Captain in at least 2 rows
  (about 10%) and FLEX where the thesis fits, rotated across contests. Use a one-row replacement or the Keenum swap rule
  (`data/inbox/slates/phi-chi-sd-2026-09-28/keenum_swap.py`, `changelog.md` 2026-09-28 v4; `swap_inactives.py value-add` is the
  Classic analogue and takes only scored players). Never write a projection: he adds 0 prior points, his gate stays unmet and is named
  as a limitation, and the file stays `DO_NOT_UPLOAD`. Research informs the choice, never a number.
- **Concentration.** After the build, count Captains and each person's share of lineups. Defaults, mine to set under the lock-clock
  ruling and Ben's to overturn: no person above 60% of lineups and no Captain above 20%, unless the selectable pool cannot meet it, and
  then say so with the pool size. A breach is a construction failure, not a finding to report: rotate rows by hand (replace the most
  shared row, check distinctness and overlap with `qa_showdown_portfolio.py`) before the handoff. PIT@CLE shipped Warren, Metcalf and
  Pittman at 82% each with the breach named and not acted on; that is the miss this rule closes.
- **Order.** Do both before the first handoff message, with the clock measured. A lock inside five minutes ships what is built and
  names both gaps.

## Repo etiquette and gotchas

- `docs/ROADMAP.md`, `changelog.md`, `IMPLEMENTATION_STATUS.md` and `backlog.md`
  are LF (`tests/test_roadmap_queue.py`): match endings, append under existing
  headings, never delete history. Status: `Pending`, `In Progress`, `Complete`,
  `Deferred`.
- Versioned contracts and claim scoping (`OPTIMAL`, sample size) are boundaries:
  `CLAUDE.md` § Release truths.
- `data/standings/inbox/`, `data/runs/**/inputs/`, and
  `tests/fixtures/supplied/` are immutable snapshots; a new run is a new folder.
- No known failing test; the session-start digest carries the last recorded
  suite line. The one skip is the junction test (symlink permission on Windows).
  Any other failure or skip is a finding, not a known issue: `.claude/rules/tests.md`.
- When Ben corrects the same thing twice, add the rule here or to another file
  in `.claude/rules/`, and say that you did.
- When compacting, preserve the session ID, the branch, the list of modified
  files, the last full-suite result line, and every open `[BEN: ...]` flag.
- Keep `CLAUDE.md` short and limited to the boundaries. Procedures go here, to
  `docs/` or `.claude/skills/`; rules for one part of the tree go to
  `.claude/rules/` with `paths:` frontmatter; anything that must happen every
  time goes to `.claude/settings.json` permissions or hooks, not prose.
