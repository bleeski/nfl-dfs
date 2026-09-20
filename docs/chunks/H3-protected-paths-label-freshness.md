# H3 — the `ben-review` label cannot clear the check that demands it

Brief for chunk `H3` of the harness track. Status and dependencies are tracked
in `backlog.md` (Queue table and chunk index); this file is the specification.
Written 2026-09-20 from a defect found while merging PR #32.

- Goal: labelling a protected-path pull request with `ben-review` turns
  `protected-paths` green, which is what every document in this repository says
  it does.
- Evidence: it does not. `.github/workflows/ci.yml` passes
  `PR_LABELS: ${{ toJSON(github.event.pull_request.labels.*.name) }}` and
  `scripts/check_protected_paths.py:113` reads that environment variable. Both
  are the **event payload**, which GitHub freezes when the event fires and
  replays verbatim on a re-run. A label added after CI ran is not in that
  payload and never will be. `on: pull_request` with no `types:` defaults to
  `opened, synchronize, reopened`, so labelling fires no new run either.

  Measured on PR #32: `suite` and `boundaries` green on `f78390b`,
  `protected-paths` failed at 18:29:44, Ben applied `ben-review` at 18:36:55,
  and the check stayed red with no route to green. Both re-run calls returned
  403, because the session token carries Actions read-only.

## Why it is more than cosmetic

`.claude/rules/git-authority.md` states two rules that this defect puts in
direct conflict:

- never merge a protected-path pull request without the label;
- never merge with a red or missing check.

With the label on and the check frozen red, both cannot be satisfied. The
session that hit this merged on the label plus green `suite` and `boundaries`,
and said so in the merge commit. That was a judgement call made under a rule
that should not have required one. `docs/CLAUDE_CODE_SETUP.md` tells Ben "the
`ben-review` label is how a protected change clears it", which is the behaviour
this chunk makes true.

The workaround that does work is undocumented and counterintuitive: label, then
push a commit, because only `synchronize` refreshes the payload. Nobody should
have to know that, and pushing a commit purely to refresh a label is close
enough to the empty-commit-to-kick-CI shape that the rules forbid that it should
not be the sanctioned path.

## Scope

1. Read the label set **at job runtime** rather than from the frozen payload.
   The workflow already grants `pull-requests: read`, so the job can query the
   pull request's current labels and pass them to the script.
2. Keep `scripts/check_protected_paths.py` runnable locally and offline exactly
   as it is today. `PR_LABELS` stays supported as an input; the change is where
   CI sources it, not the script's contract. A local run with no network must
   still work and must still report `No protected path touched` or name the
   files.
3. Add `labeled` and `unlabeled` to the workflow's `pull_request` types so
   applying the label re-runs the check on its own.
4. Correct `docs/CLAUDE_CODE_SETUP.md` and `.claude/rules/git-authority.md`
   wherever they describe the label as clearing the check, so the documents and
   the mechanism agree once the fix lands.

## Constraints

- `.github/workflows/*.yml` came off the protected list on 2026-09-20, so this
  merges on green. `.claude/settings.json` is still protected; do not touch it.
- The check must keep failing closed. If the label lookup fails for any reason
  (network, permission, a deleted pull request), the job fails rather than
  passing. A protected-path check that passes on error is worse than the
  defect it replaces.
- Do not widen what counts as a clearing label. `ben-review` is the only one.
- The job must stay fast; it completed in six seconds and should stay in that
  range.

## Acceptance

- A pull request touching a protected path, labelled **after** its first CI run,
  reaches green `protected-paths` without any new commit. Demonstrate on a real
  pull request and paste the timestamps.
- The same pull request without the label is still red, naming each protected
  file.
- A pull request touching no protected path is green with or without the label.
- `python3 scripts/check_protected_paths.py` still runs locally with no network
  and no `PR_LABELS` set, with its current output and exit codes.
- A simulated label-lookup failure fails the job rather than passing it; cover
  it with a test.
- `tests/test_repo_boundaries.py` still pins the exact three-entry list.
- Full suite green, `doctor` green.

## Non-goals

No change to the protected list itself, to `.claude/settings.json`, or to which
pull requests need the label. This chunk changes only how the job learns whether
the label is present.
