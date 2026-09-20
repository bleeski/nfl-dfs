---
paths:
  - "**"
---

# Git authority

Replaces the old rule that every commit needed a reviewed path list from Ben.
Ben is not a software engineer and does not want to be the gate. The gate is now
automated: see `.github/workflows/ci.yml` and `.github/protected-paths.txt`.

It is a client-side gate, and that distinction matters enough to state before
anything else. This repository is private on a GitHub free plan, where branch
protection and rulesets do not exist, so no server refuses a merge over red CI
and no server refuses a push to `main`. Every control below lives in files this
repository ships: the deny list in `.claude/settings.json`,
`.claude/hooks/guard_bash.py`, `.claude/hooks/push_freshness.py`, and this
document. They bind every instance because every instance clones them.

What follows from that: the rules here are kept, not enforced. "Merge only when
green" is something Claude does because it is written here, not something that
becomes impossible otherwise. Breaking one of these is a rule violation that
will succeed. That is exactly why they are written as rules rather than left to
judgement.

## What Claude may do without asking

- Create a branch `claude/<id>-<slug>`. That prefix, not `codex/`.
- Stage an explicit path list, commit, and push to a `claude/*` branch.
- Open a pull request, keep it green, and reply to review comments.
- Merge that pull request into `main` once every required check is green.
- Delete the branch after the merge, with `git branch -d` and
  `git push origin --delete`.
- Merge `origin/main` into the branch to clear a conflict.

## What Claude never does

- Push to `main`. `main` changes only through a merged pull request.
- Force push, amend, rebase, `git add -A`, `git add .`, `reset --hard`, `clean`,
  `stash`, `restore`, or `checkout --`. `.claude/settings.json` denies all of
  these; do not work around a denial.
- Delete an unmerged branch (`git branch -D`).
- Merge a pull request that touches a protected path without Ben's
  `ben-review` label, whatever the check status says.
- Merge with a red or missing check. "It is only the flaky one" is not a reason.
- Write to the repository through the GitHub API (`create_or_update_file`,
  `push_files`). Every change goes through a local commit that CI has verified.

## Two layers, not one

`.claude/settings.json` denies the plain forms by prefix. Prefix matching cannot
see a flag that arrives after an allowed prefix, and it cannot see a second
command in a chain at all, so `.claude/hooks/guard_bash.py` reads the whole
command and refuses on a pattern wherever it appears. It strips quoted strings
and here-document bodies first, so writing a document or a test that mentions a
refused command still works. `tests/test_repo_boundaries.py` checks both halves:
that the destructive shapes are refused, and that ordinary work is not.

A third check rides the same hook. `.claude/hooks/push_freshness.py` refuses a
push when `origin/main` has moved past this branch's merge base, naming the
commits and telling you to `git merge origin/main` first. Startup orientation
cannot see a merge that happens forty minutes into a session; this can. It
fetches only on a command that is actually a push, and fails open when the
network is unavailable, so an offline session is never blocked by it.

Some shapes only the guard can catch. A refspec push reaches `main` with no
`main` token after `origin` (`git push origin feature:main`) and forces with no
`--force` token at all (`git push origin +HEAD:main`). Neither is expressible as
a prefix, so `.claude/settings.json` cannot see them and only the guard refuses
them. An adversarial review found both after the first version shipped without
them; `REFUSED_COMMANDS` now covers them.

The guard fails open on purpose. If it crashes, the normal permission flow
decides. It catches the destructive command typed by accident; what forbids a
deliberate bypass is this rule, not the regex. Never phrase a command to slip
past either layer.

## Green means green

A pull request is mergeable when `suite`, `boundaries` and `protected-paths`
have all passed on its head commit, and the branch has no conflict with `main`.
Nothing else counts. A test that fails is never skipped, quarantined or
loosened to get there; if a test is wrong, fix the test as its own visible
change and say so in the changelog.

Read that as a rule Claude keeps, not a door that stays shut. Nothing stops the
merge button on a red pull request, so "it went through" is never evidence the
checks passed. Look at them.

## The protected list

`.github/protected-paths.txt` is the single definition, read by the CI job, by
`scripts/check_protected_paths.py`, and asserted by
`tests/test_repo_boundaries.py`. It covers `CLAUDE.md`, the rules directory,
the release and evidence modules, the registered policy JSON, and the authority
model itself.

Touching one of those is not forbidden. It means the pull request carries
`ben-review`, Claude says plainly in the description what changed and why, and
Ben merges it. Do not split a protected change across pull requests to avoid
the label.

## Commit messages

One chunk per commit where possible. Subject in the imperative, under 72
characters. Body says what changed and what verified it, with the exact suite
result line. Never name a model in a commit message, a pull request, or any
other artifact pushed to the repository.

## Before every push

Run the checks locally first. One validated push beats three speculative ones,
and a red pull request costs a full CI cycle.

    sh ./nfl.sh test tests/<changed>.py -x --tb=short
    sh ./nfl.sh test 2>&1 | tee /tmp/pytest.log
    python3 scripts/record_verify.py --from-log /tmp/pytest.log
    sh ./nfl.sh doctor
    git diff --check
    python3 scripts/check_protected_paths.py
