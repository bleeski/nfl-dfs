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
  failure. Record the result: `python3 scripts/record_verify.py --from-log <log>`. Start a background suite once: the
  `Tee-Object` log appears only when pytest's pipe first flushes, so a missing log is not a failed start (check
  `Get-CimInstance Win32_Process` for `pytest` before relaunching, or two suites run). Another repository's pytest on this host
  can double the wall time (Session 57's baseline: 20:35 against 11 to 12).
- Python 3.13.7 under `uv.lock`; `uv sync` needs `README.md` present.
  `NFL_DFS_TLS_ALLOW_NONSTRICT_CA=1` is the approved opt-in and clears only
  `VERIFY_X509_STRICT`. Container facts: `docs/CLAUDE_CODE_SETUP.md`.
- CI runs the pinned suite and `tests/test_repo_boundaries.py` on every push,
  and the protected-path check on every pull request event, labels included.
  Green CI replaced Ben reading each diff, so never push speculatively.
- Three traps that cost Sessions 61 and 62 time (added by Session 63). **Delete the old suite log before any Monitor is armed on it:**
  a Monitor on a log an earlier run left reports that run's result (it did in Session 62). **PowerShell 5.1 cannot pipe
  `git commit -F -`:** write the message with the Write tool to a file and commit from Bash with `git commit -F <file>`. **Edit
  scripts, commit messages and PR bodies go through the Write tool, never a Bash heredoc:** the shell layer rewrites backslashes (a
  `\f` became a form feed) and a script heavy with apostrophes fails to parse. Run the script with `.venv\Scripts\python.exe`, and
  write the ledgers with `write_bytes` so their LF endings survive.

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

## After a merge (Ben, 2026-10-08)

When the pull request that closes the session's work merges (its body carries the `Session close:` line, or Ben types
`/post-merge`), run `docs/claude/post_merge.md` before ending the turn: branch cleanup and a sync check (`scripts/post_merge.py`,
read-only, so each command it prints is its own Bash call), the next session's handoff prompt in the Session 23d format
(`scripts/next_prompt.py`, then `--check`), PowerShell for Ben in copy-paste blocks, the report, and `archive_session` last. A
merge that does not close the session gets one line saying so and nothing else. Whether Ben has allowed the archive call without a
prompt, and the other unverified items, are listed at the end of that file.

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

Runs on every Showdown slate, before the first handoff message, without being asked. History: `changelog.md` 2026-09-28 and
2026-10-01, R35 and R36 (`docs/ROADMAP.md` §2.5). The engine scores only people it has a row for, so a starter without one never
reaches selection. Sessions 51, 53 and 54 rate in-season rows, keep every backup quarterback out (`showdown_backup_qb_default`;
list the backups the report names rather than rebuilding that rule) and select a depth-declared starter with no history. This
pass is for whoever is still left out: a true cold start or a same-day promotion. A limitation named `QB_DEPTH_CAPTURE_*` or
`SHOWDOWN_BACKUP_QB_UNEVALUATED` means the backup rule did not run for that team, and the check is yours.

- **Left-out starters.** List every person a role gate or DK status kept out of the pool whom a source names a starter, the
  depth-chart quarterback first. Roster each by construction or write why not in the handoff. A starting quarterback is Captain
  in at least 2 rows (about 10%) and FLEX where the thesis fits, rotated across contests. Use `scripts/showdown_value_add.py`
  (Session 55; `docs/OPERATOR_GUIDE.md` § Showdown value-add swap): his exact DK ID, one swap per row, `--captain` for a
  Captain, then `qa_showdown_portfolio.py`. It refuses a row that already holds him and publishes no file when any row is
  invalid, which `data/inbox/slates/phi-chi-sd-2026-09-28/keenum_swap.py` did not (a record, never a tool).
  `swap_inactives.py value-add` is the Classic analogue and takes only scored players. Never write a projection: he adds 0
  prior points, his gate stays unmet and is named as a limitation, and the file stays `DO_NOT_UPLOAD`. Research informs the
  choice, never a number.
- **Concentration.** Since Session 56 the engine applies the defaults itself (`config/showdown_concentration_defaults_v1.json`: no
  person above 60% of lineups, no Captain above 20%, overlap 4) to a Showdown run that supplied no policy, relaxes them by name (0.80
  and 0.40, then rung 4) when the pool, the entry count or the window cannot hold them, and reports `concentration` in the result:
  requested, effective, the steps taken and the delivered file's own counts. Read that block first. `AS_REQUESTED` needs nothing
  more. `RELAXED`, `NOT_APPLIED` or `NOT_APPLICABLE` (under five entries) is the by-hand case: count Captains and each person's
  share of lineups in the delivered file. A breach of the defaults is a construction failure, not a finding to report: rotate rows by
  hand (replace the most shared row, check distinctness and overlap with `qa_showdown_portfolio.py`) before the handoff, unless the
  selectable pool cannot meet them, and then say so with the pool size. The defaults are mine to set under the lock-clock ruling and
  Ben's to overturn.
- **Theses stay (Session 23c).** When the run built the file from a portfolio of theses (policy v4: `theses` in the selection report
  and `portfolio_policy_audit.theses`, which names each Entry ID's thesis and whether the lineup follows it), every swap in this
  pass keeps its row's thesis: the team counts, position counts and Captain set of the thesis that row fills. A Captain swap, a
  quarterback given to a WR or TE Captain, a FLEX swap or a `showdown_value_add.py` row that breaks one turns the row into a
  different bet under the old name (P8 principle 6), so refuse it, or move the row to a thesis it follows and say so. Re-read the
  audit's per-Entry-ID `follows` after the pass. **Since Session 66 the two scripts do that check when you pass `--policy` (the
  run's normalized policy) and `--claim` (the run's `selection_report.json`).** `showdown_value_add.py` never takes a swap that
  breaks its row's thesis (`--count` takes the next swap that keeps it or skips the row and names it; `--entry-id` refuses the run,
  `SWAP_BREAKS_THESIS`, and writes nothing). `qa_showdown_portfolio.py` names each broken row's Entry ID, thesis and rule (exit 2),
  so run it after any hand edit (a ceiling-pass Captain swap, a quarterback given to a WR or TE Captain) and move a row it flags to
  a thesis it follows. Both read each Entry ID's thesis from the claim, never from the edited roster, and refuse by name when the
  files do not bind (a salary, policy or Entry ID mismatch, a v2 or v3 policy, lineups moved between Entry IDs by hand); a refusal
  is never a PASS. `backup_quarterback: NOT_EVALUATED` in their output means the run had no depth evidence, so that one rule did
  not run. Without the flags neither script checks a thesis, so pass them on every v4 run.
- **Tie-break: large prizes win (Ben, 2026-10-04).** "Err on side of trying to win large prizes if at odds with minimizing the
  washout factor." After the engine's file, run a ceiling pass: every WR or TE Captain gets his own team's starting quarterback,
  then take FLEX swaps that raise a row's prior by a point or more, Captains untouched. That pass may exceed the person default up
  to 75% of lineups and the overlap default up to 5; the Captain cap and R29 never move. Report every measure before and after.
  Then search whole-lineup swaps between Entry IDs that worsen no contest measure. Record: DET@CAR,
  `data/inbox/slates/det-car-sd-2026-10-04/construction/` (`DK_REVIEW_ENTRY_det-car-sd_final_v4_record.json`).
  The fastest route (TB@DAL, 2026-10-08, about four minutes end to end): rerun with `--request` and
  `NFL_DFS_DUMP_SCORES=<construction>/pool_scores.json` (the practice-squad `--exclude` list rides the same rerun), run
  `data/inbox/slates/tb-dal-sd-2026-10-08/construction/ceiling_pass.py` on the rerun's file (edit its `STARTING_QB` map), then
  `scripts/diversify_showdown_contests.py`, then QA. Every row keeps both teams: that pass's first version had no such check, one
  FLEX upgrade made an all-Dallas row, and only `qa_showdown_portfolio.py` (`SINGLE_TEAM_LINEUP`) caught it.
- **Practice-squad punts (DET@CAR, 2026-10-04).** A practice-squad player who was not elevated cannot play, and no inactive list
  names him, so a blank DraftKings status and an old-team prior keep him selectable. Check every rostered player under about $1,000
  against the team's elevations for the game (the club's Saturday transaction post); exclude any who was not elevated with
  `--exclude <CPT id> --exclude <FLEX id>` on a `--request` rerun. Casey Washington ($200) was in 7 of 28 rows before this check.
  Since ATL@NO (2026-10-05) run it first, right after the `--build-priors` run: `scripts/practice_squad_check.py --salaries <csv>
  --run-dir data/runs/<run_id>` lists everyone the run's own nflverse roster file marks not `ACT` (practice squad `DEV`, reserve
  `RES`) with both IDs and the `--exclude` arguments. Confirm against the elevation post (a Monday game's comes Monday afternoon),
  then rerun. It found 13 of 54 that night, and it settles a two-kicker `KICKER_ROLE_UNRESOLVED` stop too: the second kicker was
  one of them.
- **Order.** Do all three before the first handoff message, with the clock measured. A lock inside five minutes ships what is
  built and names the gaps.

## Classic judgment pass (Ben, 2026-10-04, R37; the Showdown correction, made again for Classic)

Runs on every Classic slate before the handoff, without being asked. Ben: do not blindly exclude players, starting quarterbacks
above all, because they lack history; do not blindly roster them either. The engine scores only what its history supports, so a
starter whose role is new today (a promoted backup, a transfer, a rookie, an injury replacement) can sit at or near zero. Strategy
and the engine work that replaces each step: `docs/chunks/P9-judgment-layer.md`, Sessions 60 to 62.

**Since Session 61 `run-slate` does the steps that need no judgment** and hands over the rest. Read the pass first: it is
`prior_review_reports.selection.judgment_pass` in `cowork_run.json` (and `judgment_pass` in
`classic_complete_slate_coverage.json`, and a section of the C3 review): `starters_check`, `injury_rooms`, `candidates`,
`late_swap_watch` and `protected_people`. `python scripts/judgment_pass_report.py <cowork_run.json>` prints it as the handoff text.
Contract: `docs/DATA_CONTRACTS.md` § Classic judgment pass and construction judgment. A Classic run with no portfolio policy (rung 4,
or none supplied) builds the thesis portfolio, which is where a judgment applies.

- **Starting quarterbacks first (engine, then you).** `starters_check` names each team's effective starter (the promoted backup of a
  DraftKings-`OUT` starter included) with whether the pool scored him and why not. Every other quarterback the depth evidence lists
  is out of every Classic row by default (`classic_backup_qb_default`), so Week 4's Mullens case no longer needs a by-hand drop.
  **The run captures the QB depth package itself** (Session 63) from the depth chart the prior package froze: read
  `reports["qb_depth_capture"]` (`declared_teams`, `undeclared_teams` with each reason) and the `QB_DEPTH_CAPTURE_*` limitations. A team
  the chart cannot build is named and left `unevaluated` (`CLASSIC_BACKUP_QB_UNEVALUATED`), nobody of his is guessed out, and the
  other teams are declared; an operator or official exclusion on a rank-1 starter DraftKings still lists as available drops that team
  (R25), not the package. Supply `--qb-depth-role-evidence-json` only to override; a supplied package R25 refuses raises,
  `run-slate`'s outer handler finishes with the baseline, and the improvement is lost, not the file: rebuild it with `--teams` naming
  the other teams and rerun. A starter in `missing_from_scored_pool` is yours: roster him by judgment or write why not.
- **Then the injury rooms (engine lists, you research).** `injury_rooms` shows who vacated, who inherits and each inheritor's prior
  before and after Session 60. `candidates` is the ranked list to research, never a selection: people the engine could not reprice
  (a transfer in a room with a vacancy, whose prior is still the old role's), the absorbers, and anyone DraftKings prices far
  above his prior. Read each one's `history_state` before calling him repriced. Research the role (web tools, never a prohibited
  host), then write a construction judgment (`nfl_classic_construction_judgment_v1`: exact DraftKings ID and name, minimum rows, a
  reason, sources, author, bound to the salary SHA-256) naming who to place, and rerun with `--construction-judgment-json`. The thesis
  build rosters each in at least his minimum rows, distinct and stacked; it writes no number and refuses by name a person DraftKings
  marks `OUT`, an official or operator exclusion, a `BLOCK`, an unresolved material role change, or anyone outside the scored pool
  (`refused` in the report; the rest still apply). This replaces the by-hand swap (Week 4:
  `data/inbox/slates/wk4-classic-2026-10-04/construction/manual_add_record.py`); rerun `qa_classic_portfolio.py` on the written file.
  Placing a person the role gate left out of the pool is not built (Session 52).
- **Salary: redeploy only as a Pareto gain; unused salary is fine.** Ben: leaving salary on the table can be strategic; the goal is
  to find out whether it can buy a gain on both goals at once, not to spend the cap. Take a swap only when it raises the row's
  prior, leaves the QB, his stack, the bring-back, the DST and every hand-placed person alone, and leaves no washout measure worse
  (max exposure, top-3 union, mean pairwise overlap no higher; distinct people no fewer). Since Session 62 the tool does it:
  `swap_inactives.py --mode redeploy --protect-from <cowork_run.json>` (`judgment_pass.protected_people`) plus `--protect NAME` for
  anyone you placed by hand, and `build_thesis_portfolio.py` runs the same rule at its fill step. It checks the proxies on the whole
  portfolio after each swap (the incoming person used 2 fewer times, Week 4's `construction/pareto_redeploy_record.py`, is a quick
  screen, not the proof), scans to a fixed point (`PASS_BOUND_REACHED` means rerun it), and prints both goals before and after and
  every rejected swap with the goal it would have hurt. Compare QA Tier 2 before and after, show both in the handoff, and keep the earlier file when nothing passes.
  **Since Session 64 the rule is engine code** (`src/nfl_dfs/classic_redeploy.py`, `pareto_redeploy_v2`), and `run-slate`'s own rung-4 thesis
  build runs it at the end of the build with no hand step: protected people are the accepted placements, the report is
  `construction.pareto_redeploy` (and `pareto_redeploy` in the coverage artifact; `scripts/judgment_pass_report.py` prints it), and a
  stage that did not run to its end (`DEADLINE_STOP`, `NOT_RUN_WINDOW_SPENT`, `FAILED`) travels as `CLASSIC_PARETO_REDEPLOY_INCOMPLETE`.
  Read the block first: on the engine's own rows the rule usually takes nothing (the solver already spends the cap; Week 4: 0 swaps),
  and "0 swaps, no worse" is the guarantee and the report, not a gain. The script imports the same rule and adds `--now`: with it a
  person whose game has locked is never outgoing and never incoming, so it is also safe after the first window.
- **Late windows need no active list at the early lock (engine).** Ben: late swap covers it. `late_swap_watch` lists every rostered
  later-window person with no official row and his DraftKings status (`Q`, illness, a depth-chart call); put that list in the handoff,
  not under Needs Ben as an open gap. Confirm the early-window players (`early_window_without_official_row`) against the posted
  official inactive lists. `OFFICIAL_STATUS_*` still stops certification; the watch list changes none of it.
- **Say who was passed over and why** in the handoff, alongside who was added. Late-game candidates can wait for late swap.

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
