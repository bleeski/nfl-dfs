# H3 — make the `ben-review` label clear the check that demands it

Paste this whole file as the first message of a fresh Claude Code session
started in the `nfl-dfs` repo root. It changes a CI workflow and the script that
workflow calls. It touches no engine module, no contract and no evidence gate,
and it is small: expect one session, not a tranche.

---

## Read, in this order, and nothing else until the plan is approved

1. `CLAUDE.md` in full. It is binding.
2. `docs/chunks/H3-protected-paths-label-freshness.md` — the specification. Its
   Acceptance section is the definition of done, all of it.
3. `.claude/rules/git-authority.md` in full, especially "Two layers, not one",
   "Green means green" and "The protected list".
4. `.github/workflows/ci.yml`, the `protected-paths` job.
5. `scripts/check_protected_paths.py` in full. It is ~120 lines.
6. `tests/test_repo_boundaries.py`, the protected-path assertions and
   `test_the_protected_list_stays_short_enough_to_actually_read`.
7. `docs/CLAUDE_CODE_SETUP.md` § "Where the gate actually lives" and § "The
   protected list, and why each entry is on it".
8. `changelog.md`, the `Unreleased` head: the 2026-09-20 close-out entry
   describes the defect with its measured timestamps.

## Runtime

`sh ./nfl.sh setup|test|doctor|<cli>` on `.venv-linux`; `.\nfl.ps1` on Windows
with `.venv`. Never mix them. **A fresh container needs `sh ./nfl.sh setup`
first**: without it `nfl.sh test` exits 0 and prints `project environment is
missing`, which is not a suite result and must never be recorded as one. The
complete suite needs an extended tool timeout (600000 ms) or a background run; a
run killed at two minutes is a tooling artifact. Baseline to reproduce before
changing anything is the last line recorded in `changelog.md`.

## Why this exists

On 2026-09-20, PR #32 carried Ben's `ben-review` label and could not reach a
green `protected-paths` check by any route. The job reads
`PR_LABELS: ${{ toJSON(github.event.pull_request.labels.*.name) }}`, and
`scripts/check_protected_paths.py:113` reads that variable. Both are the
pull-request **event payload**, which GitHub freezes when the event fires and
replays verbatim on a re-run. `on: pull_request` with no `types:` list defaults
to `opened, synchronize, reopened`, so labelling fires no new run either.

Measured: `suite` and `boundaries` green on `f78390b`; `protected-paths` failed
at 18:29:44Z; Ben labelled at 18:36:55Z; the check stayed red.

That puts two rules in `.claude/rules/git-authority.md` in direct conflict:
never merge a protected-path pull request without the label, and never merge
with a red check. With the label on and the check frozen red, both cannot hold.
The session that hit it merged on the label plus green `suite` and `boundaries`
and said so in the merge commit, but that was a judgement call forced by a
defect, and `docs/CLAUDE_CODE_SETUP.md` promises Ben the label is what clears
the check.

## Scope

As the brief's § Scope, all four items: read labels at job runtime rather than
from the frozen payload; keep the script runnable locally and offline with its
current contract; add `labeled` and `unlabeled` to the workflow's
`pull_request` types; and correct the two documents that describe the label as
clearing the check.

## Out of scope

- The protected list itself. It is three entries and stays three entries.
- `.claude/settings.json`. It is protected; do not touch it.
- Which pull requests need the label, and any widening of what counts as a
  clearing label. `ben-review` is the only one.
- The client-side hooks and the deny list. This chunk is the CI job only.

## The constraint that decides the design

**The check must keep failing closed.** If the label lookup fails for any reason
(network, permission, a deleted pull request), the job fails rather than passes.
A protected-path check that passes on error is worse than the defect it
replaces. Write that test first.

Note also that the workflow already grants `pull-requests: read`, so no
permission change is needed, and the job completes in about six seconds today.
Keep it in that range.

## Acceptance

Verbatim from the brief, all of it. The load-bearing case is the one that
motivated the chunk: a pull request touching a protected path, labelled **after**
its first CI run, reaches green `protected-paths` with no new commit.
Demonstrate it on a real pull request and paste the timestamps — this cannot be
proven by a unit test alone, because the thing under test is GitHub's event
delivery. The same pull request without the label must still be red and name
each protected file.

## Close-out

Update `backlog.md` (`H3` status, what was relaxed or left open, the next
`READY` chunk), `changelog.md` under `Unreleased` with the exact suite line and
wall time, and `IMPLEMENTATION_STATUS.md` only if working capability changed.
Commit, push, open a pull request and merge it on green CI under
`.claude/rules/git-authority.md`. `.github/workflows/*.yml` came off the
protected list on 2026-09-20, so this merges on green without a label — which is
worth stating in the pull request description, since the chunk is about that
label.
