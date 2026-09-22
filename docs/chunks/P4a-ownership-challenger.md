# P4a — Mass-conserving ownership challenger

Brief for chunk `P4a` of the prize-tail program. Status, dependencies and hand-back are tracked in `docs/ROADMAP.md` (status board and session card); this file is the specification. Moved verbatim from `backlog.md` on 2026-09-15.

Hand-back lines below that name a `docs/session-prompts/` file or a `READY`
status predate the roadmap. At close-out follow `.claude/skills/close-out/SKILL.md`
instead: the session card and the §1 Quick-Start replace per-chunk prompts.

- Goal: the engine has an ownership estimate on the operating path that is a
  probability distribution and is graded by slate.
- Evidence: the only archived pre-lock vector summed QB to 200.6% and DST to
  186.5%, MAE 7.82 pp, Spearman 0.13; the greenfield report's salary-only
  baseline reached CPT MAE 0.87 pp and FLEX MAE 4.87 pp held out by game.
- Read first: `src/nfl_dfs/ownership.py` (`cold_start_states`, the fixed
  softmax scale 2.1, roster totals), greenfield report section 3.3 and 3.5, Q3.
- Files: `ownership.py`, `prior_review.py` (emit the vector and its validity
  report), P0's harness (a `--ownership` grading mode), tests.
- Scope: salary-logistic Captain and FLEX models with an eligibility mask from
  participation and official status; per-slot mass conservation enforced (one
  Captain, five FLEX; Classic slot totals from one learned FLEX-position mix,
  observed RB 42.5 / WR 36.1 / TE 21.4 on the one Classic slate, replacing the
  fixed `ownership.py` targets and shared with `field.py` in P4b); the fixed
  softmax scale of 2.1 becomes a fitted, registered parameter; a validity
  report rejects any vector whose slot totals are off by more than 5%, and the
  same validator refuses an externally supplied `ownership_brackets_csv` at
  request validation; grading by slate through the harness with MAE by
  ownership band, top-five recall, and calibration slope; states remain
  `COLD_START_OWNERSHIP_PRIOR`. Add an advisory policy control
  `max_low_owned_players` (count of rostered persons under a declared estimated
  ownership) so the chalk-core-versus-contrarian experiment can be configured;
  advisory until the challenger has been graded on at least eight more games.
- Non-goals: no leverage tilt in the objective, no field generation, no
  duplication.
- Acceptance: on the four Showdown games, held out one at a time, the challenger
  beats uniform and matches or beats the greenfield salary baseline on both MAE
  figures; every emitted vector passes the validity report; full suite green.
- Hand-back: `docs/session-prompts/P4b-copy-count.md`; P4b `READY`.
