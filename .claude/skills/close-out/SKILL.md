---
name: close-out
description: Close a Claude Code development session in the nfl-dfs repo: verification evidence, roadmap and ledger updates, the next Quick-Start, then commit, push, open the pull request and merge it on green CI. Use when the session's work is done or the session is ending.
disable-model-invocation: true
---

Close out the current roadmap session.

1. Verification, with output pasted, not summarized: the card's verification
   command; the complete pinned suite under an extended timeout; `doctor`;
   `python -m compileall` (or import) of every changed module;
   `git diff --check`. If anything is red, the session is not `Complete`; say so.
2. `docs/ROADMAP.md` (LF):
   - §2.2: set the row `Complete`, or back to `Pending` with what is left. If
     the card's breakpoint was used, add a `Session NNb` row directly below
     for the remainder.
   - §2.3: add one dated line to the card saying what landed and what was
     relaxed or left open. A question only Ben can answer becomes a
     `[BEN: ...]` flag in the card of the session it blocks, with that
     session's `Depends on` set to `BEN ruling`.
   - §2.6: mark operator items `Done` only on evidence (a file present, a
     hash, Ben's word).
   - §4: add a ledger row (date, session, status change, commit SHA,
     one-line note). Fill in the previous session's merge SHA if it is
     still "recorded by".
   - §1: rewrite the Quick-Start to name the next startable session.
     `tests/test_roadmap_queue.py` fails if it names anything else.
3. `changelog.md` (LF): read its first 80 lines only, then insert a dated
   `###` section directly under `## Unreleased` with
   Added / Changed / Verification, exact test counts and timings, artifact
   hashes, and the branch name.
4. `IMPLEMENTATION_STATUS.md` (LF): only if working capability changed.
5. Run the `reviewer` subagent on the diff against the session's card and
   briefs; fix or record what it finds before committing.
6. Record the suite result where the next session will see it:
   `python3 scripts/record_verify.py --from-log <log>`.
7. Release the claim: `python3 scripts/claim.py release <SNN>`. Commit the
   changed `state/claims.json` with the rest, or the next instance still sees
   the session held.
8. Commit and ship, per `.claude/rules/git-authority.md`:
   - `git add` an explicit path list, grouped as source / tests / docs / ledger.
     Never `git add .` or `-A`. Say in one line what you deliberately left out.
   - Commit, push, open the pull request.
   - `python3 scripts/check_protected_paths.py`. If it flags anything, add the
     `ben-review` label, say so, and stop: that pull request is Ben's to merge.
   - Otherwise wait for `suite`, `boundaries` and `protected-paths` to go green,
     then merge and delete the branch. A red check is work, not a reason to stop.
9. Report to Ben in a few lines, in the order
   `.claude/rules/stops-and-reports.md` sets. **Needs Ben** first: a
   `ben-review` label, any open `[BEN: ...]` flag, anything else he owes, or
   "nothing". Then **Changed**: what landed, the exact suite result, the pull
   request link and whether it merged. Then **Found**: anything relaxed or
   left open, and the next session.
