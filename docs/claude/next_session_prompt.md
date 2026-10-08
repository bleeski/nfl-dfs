/plan

You are starting {{SESSION}} in the nfl-dfs repo ({{TITLE}}). You have no memory of earlier sessions: re-read, do not assume. Your first action is plan mode (EnterPlanMode, if /plan did not already put you there). Stay in it and change nothing until I approve a plan. That overrides working.md's "no plan-approval wait" for this session only.

## 0. Preflight, read-only, before the plan
- `git fetch origin main`, then `git log --oneline -5 origin/main`. The last session's merge ({{LAST_MERGE}}) must be on origin/main, and ROADMAP §1 must name {{SESSION}}. If either is not, stop and tell me.{{QUICK_START_NOTE}}
- `python3 scripts/claim.py show`. A claim under six hours old means another session is on it: stop and ask.
- Linux: `sh ./nfl.sh <cmd>` on `.venv-linux` (`sh ./nfl.sh setup` first in a fresh container). Windows: `.\nfl.ps1 <cmd>`. Never mix them.
- Orient: docs/START_HERE.md; ROADMAP §1, §2.1 and the "#### {{SESSION}}" card (grep, never read whole);{{BRIEFS_CLAUSE}} the first 80 lines of changelog.md; .claude/rules/contracts.md, operating-path.md, tests.md, ledger.md. Grep docs/DATA_CONTRACTS.md and docs/RUNBOOK.md, never read them. At most one `explorer` agent for anything wider.
- Last session: {{LAST_ENTRY}}
- Housekeeping owed from the last merge: {{HOUSEKEEPING}}

## 1. What to do
Execute the {{SESSION}} card exactly as §2.3 specifies it. {{ACCEPTANCE_LINE}}
{{BREAKPOINT_LINE}}

In code, that is: <<CLAUDE:what-to-do: turn the acceptance into numbered items of code from the card's Scope and the brief, naming the files, versions and contracts each touches.>>

Decide these in the plan, recommendation first, with the reason:
<<CLAUDE:decisions: the judgment calls this card leaves open, one bullet each, naming the files that show how the code treats the case today. Cover missing versus bad input (a named refusal or a named limitation; the lock-clock ruling says a gap never stops delivery), where the data enters the run, which prior_review exits carry the change, edge cases, and the gate registry if blocker-shaped code is added.>>

Out of scope, mention and do not touch: <<CLAUDE:out-of-scope: what this card and its neighbors leave to other sessions.>> If the planned diff passes about 1,000 changed lines (tests count), stop at the seam the plan names; the breakpoint is 1,500.

## 2. How much effort
The card says: {{SIZE}} Spend like it. <<CLAUDE:effort: the expected non-test, test and doc line counts, and why if the plan runs past twice that.>> The effort is:
- Orientation: about ten targeted reads and at most one `explorer`.
- The plan: acceptance in code, files to touch, tests to write first, decisions, assumptions, tradeoffs, the seam, a checklist, and any `[BEN: ...]` flag. Write it to the plan file and to state/tasks/{{SHORT}}.md.
- After approval: tests first, then code, one full-suite run in the background once the code is final (again only if src/ changes after that), one fresh-context `reviewer` agent on the diff, and one mutation pass on a copy of the tree.
- Decide judgment calls yourself and record why. Ask me only for a fact only I have, as a `[BEN: ...]` flag, not a stop.

## 3. How to verify
The plan must name each check and its command.
- **Real fixtures first.** Before any assertion depends on a real run, print a key-and-count summary of one with a scratch script named `{{SHORT_LOWER}}_*.py` in the scratchpad. <<CLAUDE:fixtures: which real fixture or run the card's claims rest on (a test file, a helper, a run directory) and what to confirm about its keys and counts.>>
- **Tests first, new files only.** Run them red and paste the first failure. Existing tests stay unedited. A red test elsewhere is a finding: name it and the reason in the changelog before any fix.
- **Acceptance clauses.** <<CLAUDE:acceptance-checks: one named test per clause of the acceptance and per bad-input kind, with the boundary cases the card implies.>>
- **No new input behaves as before.** Load `git show origin/main:<file>` as a second copy and run both over real runs in every mode the change could touch. Compare stdout, exit code and written bytes, and show the output.
- **Windows CI runs the suite.** Session 66 lost two CI cycles to fixtures that depended on the platform: a JSON-escaped Windows path in a hashed stdout, and `write_text` giving CRLF, which changed a printed SHA-256. Write fixtures with `write_bytes`, and never compare a raw `str(path)` against JSON text.
- **Run order.** Focused tests with `-x --tb=short`; then neighbors (<<CLAUDE:neighbors: the test files that touch the same modules, from the card and a grep>>); then the full suite once, in the background. Delete the old log first. The last recorded full suite: {{LAST_SUITE}}. Record the result with `python3 scripts/record_verify.py --from-log <log>`.
- **Mutation pass on a COPY of the tree, never the repository.** Use `shutil.copytree` into the scratchpad (rsync is absent), `PYTHONPATH=<copy>/src`, and confirm `nfl_dfs.__file__` resolves into the copy. The driver records the FAILED test name that kills each mutant. Fix a survivor with a test, or explain why it is equivalent. Delete the copy.
- **Final checks:** `git diff --check`; `python3 scripts/check_protected_paths.py` (expect none touched); `sh ./nfl.sh doctor`; compile every edited script; zero CR bytes in ROADMAP, changelog, IMPLEMENTATION_STATUS and backlog; never a bare `[BEN:]` token in a ledger row.
- **Close-out (/close-out):** status board row, card Landed paragraph, ledger row, a dated changelog section under `## Unreleased` with exact counts and what was measured, IMPLEMENTATION_STATUS, §1 rewritten to the next startable row (`python3 scripts/repo_state.py --stdout` derives it), and the claim released. Open the PR with the `Session close:` line (see the close-out skill) as its last body line, subscribe, and merge only when `suite`, `boundaries` and `protected-paths` are green on the head commit (and the `windows` job too). After the merge, run the post-merge routine in docs/claude/post_merge.md: cleanup, the next prompt, then archive.
- **Show evidence, never assert it.** Never summarize a run you did not see end.

## 4. /advisor
- **Before you present the plan.** Write it to the plan file, then call /advisor (Skill tool, skill "advisor") with the draft in context. Brief it to refute, not confirm: name the claims to attack (<<CLAUDE:attack: the claims in this plan most likely to be wrong, for example the acceptance mapping, the intake path, the missing-versus-bad semantics, the seam.>>). Fold in its corrections, add an "Advisor said / what changed" note, then present with ExitPlanMode.
- **After I approve, call it whenever any of these holds:**
  - a test fails twice with no clear cause, or a result does not fit the plan;
  - you are about to guess, or about to retry the same fix a third time;
  - a design choice with real tradeoffs turns up that the plan did not settle (a development question counts);
  - you need guidance on strategy or tactics, for example when the diff nears 800 lines and you must decide between splitting and pushing on;
  - once before close-out.
  Not for routine calls. Record each consult (question, answer, what changed) in the task file.
- **If the skill errors.** In cloud sessions it has failed on a hook (`set: Illegal option -o pipefail`). Do not retry it in a loop. Say so, and use a fresh-context read-only agent (Agent tool, `Plan` type, model fable) briefed to refute your draft, and tell me.

## 5. Rules that cost time before
- Lessons: <<CLAUDE:lessons: what the session just ended taught that this one should not relearn: the findings in its changelog entry, the CI cycles it lost and why, and any rule it added. Fewer than eight words is a failed fill.>>
- One session per branch: the one assigned, or `claude/{{SHORT_LOWER}}-<slug>`. Claim with `python3 scripts/claim.py take {{SHORT}}`. The claim commit turns `test_the_quick_start_names_the_first_startable_session` red, so rewrite §1 in that commit or accept that one red. Never merge on the claim commit.
- If the auto-mode classifier denies a command, do not retry it in pieces or by another tool. Finish what does not depend on it, then give me exact copy-and-paste commands and wait. Editing `.claude/settings.json`, your own permissions, or anything on `.github/protected-paths.txt` is mine to decide, so a denial there is final.
- A change that reaches one of the three exits of `prior_review` (Showdown, Classic C1/C2, Classic C3) must reach all three, with a test per exit (`.claude/rules/operating-path.md`).
- No Bash heredocs for scripts, commit messages or PR bodies: use the Write tool and `git commit -F <file>`. Trailer: `Co-Authored-By: Claude <noreply@anthropic.com>`. Name no model in any commit or PR.
- Never `git add -A` or `.`, force-push, amend, rebase, stash, or push to main. Never read a standings export, salary CSV, run artifact or fixture into context; print a schema-level summary.
- Everything stays PRIOR_ONLY / DO_NOT_UPLOAD. DraftKings login, entry and upload stay manual. Nothing fetches DraftKings data.
- End with **Needs Ben** (first), **Changed** (PR link, merged or not, exact suite line), and **Found**.
