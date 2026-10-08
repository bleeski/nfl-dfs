<!-- Provenance: the handoff prompt for Session 23d, written by hand in the Session 66
     development session on 2026-10-08. Ben then asked for every later handoff "in the same
     format", which is why this is the golden for the structure of scripts/next_prompt.py's
     output. It is not a file to paste: the card and the repository move, and the generator
     rebuilds the prompt from them. -->
/plan

You are starting Session 23d in the nfl-dfs repo (P2 part 2: contest facts and screening). You have no memory of earlier sessions: re-read, do not assume. Your first action is plan mode (EnterPlanMode, if /plan did not already put you there). Stay in it and change nothing until I approve a plan. That overrides working.md's "no plan-approval wait" for this session only.

## 0. Preflight, read-only, before the plan
- `git fetch origin main`, then `git log --oneline -5 origin/main`. PR #120 ("Close out Session 66") must be merged, so ROADMAP §1 names Session 23d and the board shows 66 Complete. If it is not on main, stop and tell me.
- `python3 scripts/claim.py show`. A claim under six hours old means another session is on it: stop and ask.
- Linux: `sh ./nfl.sh <cmd>` on `.venv-linux` (`sh ./nfl.sh setup` first in a fresh container). Windows: `.\nfl.ps1 <cmd>`. Never mix them.
- Orient: docs/START_HERE.md; ROADMAP §1, §2.1 and the "#### Session 23d" card (grep, never read whole); docs/chunks/P2-contest-aware-policy.md; the first 80 lines of changelog.md; .claude/rules/contracts.md, operating-path.md, tests.md, ledger.md. Grep docs/DATA_CONTRACTS.md and docs/RUNBOOK.md, never read them. At most one `explorer` agent for anything wider.

## 1. What to do
Execute the Session 23d card as Session 50 narrowed it. Acceptance, verbatim: "A `contest_facts_csv` with a bad row is refused by name; the DEN@KC fixture's entries under 5% paid are labelled `FIRST_PLACE_OBJECTIVE` from supplied numbers only; suite green."

In code, that is three things:
1. A versioned contract `nfl_contest_facts_v1` (docs/DATA_CONTRACTS.md) and a strict parser for `contest_facts_csv`: contest id, field size, places paid, entry fee. Bind exact bytes with a SHA-256. Every bad row is a named refusal, per .claude/rules/tests.md: truncated file, missing column, duplicate contest id, non-numeric, zero or negative, places paid above field size, and the rest you find.
2. Paid fraction = places paid / field size per contest id, tagged on each reserved entry through its Contest ID. An entry whose contest pays under 5% is labelled `FIRST_PLACE_OBJECTIVE` in the review. The numbers come from the supplied file only. Never infer field size, payout tiers or ticket value from a contest name (CLAUDE.md permanent boundary). The label is a fact about the contest, not a forecast: it never reads EV, ROI, win probability or edge, and it carries a registered version string and `does_not_establish` text.
3. The manual contest-screening checklist in docs/RUNBOOK.md (rake, overlay, payout shape, field size, max entries; plan.md:395, critique V9).

Decide these in the plan, recommendation first, with the reason:
- **Missing or bad facts must not stop delivery.** CLAUDE.md's lock-clock ruling and R28 say the worst outcome is no lineup. A missing file should mean no labels and a named limitation. A malformed file should be refused by name and dropped, with delivery continuing. Check this against how src/nfl_dfs/cowork.py handles `CONTEST_PAYOUT_REQUIRED` today (around lines 160 and 603) and say how the two relate.
- **How the file reaches the run.** The card names no intake file, but files are classified by schema, not filename, and hashed. Find the smallest path (cowork.py intake, cli) and say so.
- **Which reviews carry the label.** `.claude/rules/operating-path.md`: a change that reaches one `prior_review` exit must reach all three (Showdown, Classic C1/C2, Classic C3), with a test per exit.
- **Edge cases.** A contest id with no facts row, and a facts row with no entry: reject or ignore, but named either way.
- **Gate registry.** Any new blocker-shaped code in src/ must be classified (V, S or P) in config/gate_registry_v1.json, or tests/test_gate_registry.py fails. It changes `REGISTRY_SHA256` (Session 23f precedent).

Out of scope, mention and do not touch: Session 50's contest step and its objective (a per-contest weight would be a later term in it), the superseded assignment-order policy input, any ownership, field or duplication model, and anything the card does not name. If the planned diff passes about 1,000 changed lines (tests count), stop at the seam: contract, parser and the pure label function with their tests first as their own pull request, intake and review wiring second. The breakpoint is 1,500.

## 2. How much effort
The card says Small: one session, about 300 changed lines after the narrowing. Spend like it. Expect roughly 300 non-test lines, 500 of tests and 100 of docs. If your plan is more than twice that, say why in the plan. The effort is:
- Orientation: about ten targeted reads and at most one `explorer`.
- The plan: acceptance in code, files to touch, tests to write first, decisions, assumptions, tradeoffs, the seam, a checklist, and any `[BEN: ...]` flag. Write it to the plan file and to state/tasks/S23d.md.
- After approval: tests first, then code, one full-suite run in the background once the code is final (again only if src/ changes after that), one fresh-context `reviewer` agent on the diff, and one mutation pass on a copy of the tree.
- Decide judgment calls yourself and record why. Ask me only for a fact only I have, as a `[BEN: ...]` flag, not a stop.

## 3. How to verify
The plan must name each check and its command.
- **Real fixtures first.** Before any assertion depends on a real run, print a key-and-count summary of one with a scratch script named `s23d_*.py` in the scratchpad. Use the DEN@KC fixture the card cites (find it in tests/) and the Session 23c run-slate fixture (`tests/test_contest_assignment_run_slate.py::_run` with `INTERLEAVED_CONTESTS`). Confirm which Contest ID values entries carry and how contest_assignment.py reads them.
- **Tests first, new files only.** Run them red and paste the first failure. Existing tests stay unedited. A red test elsewhere is a finding: name it and the reason in the changelog before any fix.
- **Acceptance clauses:**
  - one test per bad-row kind;
  - the 5% boundary just under, exactly at, and just over;
  - a case where the contest name says "satellite" or "single entry" but the numbers disagree, and the label follows the numbers;
  - determinism;
  - a changed input byte changes the bound hash.
- **No facts supplied behaves as before.** Load `git show origin/main:<file>` as a second copy and run both over real runs in both modes (no policy, v2, v3, v4). Compare stdout, exit code and written bytes, and show the output.
- **Windows CI runs the suite.** Session 66 lost two CI cycles to fixtures that depended on the platform: a JSON-escaped Windows path in a hashed stdout, and `write_text` giving CRLF, which changed a printed SHA-256. Write fixtures with `write_bytes`, and never compare a raw `str(path)` against JSON text.
- **Run order.** Focused tests with `-x --tb=short`; then neighbors (test_prior_selection, test_portfolio_policy, test_gate_registry, test_roadmap_queue, test_repo_boundaries, test_contest_assignment*, test_readable_review*, test_cowork*, test_run_slate_baseline_first); then the full suite once, in the background. Delete the old log first. After Session 66 the Linux collection is 2924 tests (2923 passed, 1 skipped), plus yours. Windows skips 2. Record the result with `python3 scripts/record_verify.py --from-log <log>`.
- **Mutation pass on a COPY of the tree, never the repository.** Use `shutil.copytree` into the scratchpad (rsync is absent), `PYTHONPATH=<copy>/src`, and confirm `nfl_dfs.__file__` resolves into the copy. The driver records the FAILED test name that kills each mutant. Fix a survivor with a test, or explain why it is equivalent. Delete the copy.
- **Final checks:** `git diff --check`; `python3 scripts/check_protected_paths.py` (expect none touched); `sh ./nfl.sh doctor`; compile every edited script; zero CR bytes in ROADMAP, changelog, IMPLEMENTATION_STATUS and backlog; never a bare `[BEN:]` token in a ledger row.
- **Close-out (/close-out):** status board row, card Landed paragraph, ledger row, a dated changelog section under `## Unreleased` with exact counts and what was measured, IMPLEMENTATION_STATUS, §1 rewritten to the next startable row (`python3 scripts/repo_state.py --stdout` derives it), and `claim.py release S23d`. Open the PR, subscribe, and merge only when `suite`, `boundaries` and `protected-paths` are green on the head commit (and the `windows` job too).
- **Show evidence, never assert it.** Never summarize a run you did not see end.

## 4. /advisor
- **Before you present the plan.** Write it to the plan file, then call /advisor (Skill tool, skill "advisor") with the draft in context. Brief it to refute, not confirm: name the claims to attack (the acceptance mapping, the intake path, the missing-versus-bad-file semantics, label placement across the three exits, the seam). Fold in its corrections, add an "Advisor said / what changed" note, then present with ExitPlanMode.
- **After I approve, call it whenever any of these holds:**
  - a test fails twice with no clear cause, or a result does not fit the plan;
  - you are about to guess, or about to retry the same fix a third time;
  - a design choice with real tradeoffs turns up that the plan did not settle (a development question counts);
  - you need guidance on strategy or tactics, for example when the diff nears 800 lines and you must decide between splitting and pushing on;
  - once before close-out.
  Not for routine calls. Record each consult (question, answer, what changed) in the task file.
- **If the skill errors.** In cloud sessions it has failed on a hook (`set: Illegal option -o pipefail`). Do not retry it in a loop. Say so, and use a fresh-context read-only agent (Agent tool, `Plan` type, model fable) briefed to refute your draft, and tell me.

## 5. Rules that cost time before
- One session per branch: the one assigned, or `claude/s23d-<slug>`. Claim with `python3 scripts/claim.py take S23d`. The claim commit turns `test_the_quick_start_names_the_first_startable_session` red, so rewrite §1 in that commit or accept that one red. Never merge on the claim commit.
- If the auto-mode classifier denies a git or claim command (it denied `git switch` last time), do not retry it in pieces or by another tool. Finish what does not depend on it, then give me exact copy-and-paste commands and wait.
- No Bash heredocs for scripts, commit messages or PR bodies: use the Write tool and `git commit -F <file>`. Trailer: `Co-Authored-By: Claude <noreply@anthropic.com>`. Name no model in any commit or PR.
- Never `git add -A` or `.`, force-push, amend, rebase, stash, or push to main. Never read a standings export, salary CSV, run artifact or fixture into context; print a schema-level summary.
- Everything stays PRIOR_ONLY / DO_NOT_UPLOAD. DraftKings login, entry and upload stay manual. Nothing fetches DraftKings data; the facts file is an operator-supplied CSV.
- End with **Needs Ben** (first), **Changed** (PR link, merged or not, exact suite line), and **Found**.
