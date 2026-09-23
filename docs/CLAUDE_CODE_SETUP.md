# Claude Code setup

Everything in this file is something only Ben can do. Claude cannot create a
label in a repository it does not administer, and cannot change the permission
mode that governs itself.

## What changed, in plain terms

Claude now commits, pushes, opens pull requests, and merges them into `main` on
its own, once CI is green. It deletes its own merged branches. It does not ask
first.

Four things still stop it. The last one is mechanical, enforced by a hook on
this machine. The first three are rules Claude keeps, for the reason in
"Where the gate actually lives" below.

1. **CI.** `suite`, `boundaries` and `protected-paths` must all pass on the
   pull request's head commit. A red or missing check is a hard stop.
2. **The protected list.** A pull request touching anything in
   `.github/protected-paths.txt` is never merged by Claude, green or not. It
   gets the `ben-review` label and waits for you.

   Narrowed from twelve entries to three on 2026-09-20, on your instruction:
   `CLAUDE.md`, `.github/protected-paths.txt` and `.claude/settings.json`. The
   release and evidence modules, the registered policy JSON, the workflows and
   `.claude/rules/*.md` came off it and now merge on green like everything else.
   You were right that a diff to `evidence.py` is not something you can
   meaningfully review, and a signature is a weaker gate than the suite.

   What the three have in common is not that they are hard to review. It is the
   opposite: each one is a plain-English question about what the machine may do,
   which is the judgement you are qualified to make. They exist so that Claude
   cannot quietly change what Claude is not allowed to do. Expect to see them
   rarely — three files, a paragraph of explanation, yes or no.
3. **The permanent boundaries**, now asserted by `tests/test_repo_boundaries.py`
   rather than relying on you reading the diff.
4. **A command guard.** `.claude/hooks/guard_bash.py` runs before every Bash
   call and refuses forced pushes, amends, whole-tree staging, rebases, hard
   resets, `clean`, the mutating `stash` verbs, forced branch deletion, and any
   push to `main`, including when the flag arrives after an allowed prefix or
   sits in a chained second command. Permission rules match a prefix and can see
   neither. It also refuses a push whose branch is behind a `main` that moved,
   which is how a session finds out another instance merged while it worked.

`.claude/rules/git-authority.md` is the full rule.

## Where the gate actually lives

The gate is client-side, and it is worth being exact about that, because a
reader who assumes a server is watching will draw the wrong conclusion from a
green check.

This repository is private on a GitHub free plan. Rulesets and branch protection
are not available there, so **nothing server-side blocks anything**: not a push
straight to `main`, not a merge over red CI, not a force push. There is no
setting to turn on, and making the repository public to obtain one is not worth
the trade.

What does bind, and why it is not nothing:

- `.claude/settings.json` denies the destructive command shapes by prefix.
- `.claude/hooks/guard_bash.py` denies the shapes a prefix cannot express, and
  refuses a stale push.
- `.claude/rules/git-authority.md` states the rules the hooks cannot check.

These bind every instance because every instance clones them. That is a real
control over the failure this is actually protecting against, which is a Claude
Code session doing something destructive by accident. It is not a control
against a determined bypass, and it never was.

So for an instance about to merge its own work: **CI is advisory.** It reports;
it does not block. The green check is evidence you are meant to act on, not a
door that refuses to open. Merging red is possible and is a rule violation, not
an impossibility. The honest summary is that merge-on-green is a convention
Claude keeps, not a rule a server enforces.

`protected-paths` is advisory in exactly the same way, and it is worth not
overclaiming for it: a red `protected-paths` does not stop the merge button any
more than a red `suite` does. What it does is make the touch visible and
unambiguous. It runs as a CI job regardless of branch protection, and it turns
"this pull request changes something Ben decides" from a judgement Claude has to
make into a check that either passes or names the file. The `ben-review` label
is how a protected change clears it. The check runs from
`.github/workflows/protected-paths.yml`, which reruns on `labeled` and
`unlabeled` and reads the labels from the pull request at job runtime, so
applying the label turns it green with no new commit (H3, 2026-09-23; until then
the job read the frozen event payload and a late label could never clear it).
Claude not merging that pull request is still a rule Claude keeps rather than a
door that is locked.

## One-time, in GitHub

### The review label

Issues → Labels → New label, named exactly `ben-review`. The `protected-paths`
job looks for that string. Any colour. It exists as of 2026-09-23.

A pull request that touches a protected path fails `protected-paths` until the
label is on it, which is the correct failure. Applying the label reruns the
check by itself and it goes green on the same commit; removing it turns the
check red again. If the job cannot read the labels (network, permission, a
deleted pull request) it fails rather than passes.

## One-time, per machine

### Permission mode

`.claude/settings.json` sets `defaultMode` to `acceptEdits`, which is as far as
a project settings file is allowed to go. The modes `auto` and
`bypassPermissions` are ignored when they come from project or local settings,
by design. If you want fewer prompts than `acceptEdits` gives you, set it
yourself in `~/.claude/settings.json`:

```json
{ "permissions": { "defaultMode": "auto" } }
```

That is your call, not the repository's. `deny` rules still apply in every mode.

### Folder trust

`permissions.allow` and `additionalDirectories` from a project settings file
only take effect after you trust the folder. Until then you will still see a
prompt for things the file allows. `deny` and `ask` apply immediately, so the
safety half is never waiting on trust.

### Environments

| Surface | Launcher | Environment | Use it for |
|---|---|---|---|
| Windows desktop app | `.\nfl.ps1 <cmd>` | `.venv` | Operating slates, the full suite |
| Cloud session, including phone | `sh ./nfl.sh <cmd>` | `.venv-linux` | Development, review, grading, pull requests |

Never mix the two in one session. First run on a new machine or container is
`.\nfl.ps1 setup` or `sh ./nfl.sh setup`, which needs `uv` and `README.md`
present.

### Model and effort

Nothing in the repository pins a model or an effort level. Choose both in the
app, with `/model` and `/effort`, so a new model needs no pull request.

- **Subagents follow the session.** `explorer` and `reviewer` declare
  `model: inherit` (2026-09-23; both were pinned to a smaller model before).
  `explorer` also declares `effort: low`, the level Anthropic's effort guide
  lists for subagents: it looks things up and returns `path:line` references
  the main session can check. `reviewer` runs at the session's level.
- **Effort is the thinking control.** On the model this repository runs,
  thinking is always on: `alwaysThinkingEnabled`, `MAX_THINKING_TOKENS=0` and
  the Alt+T toggle do nothing. `/effort` saves a level per model, so a level
  set for an earlier model may not carry over; check it after switching. Prompt
  lines such as "think carefully" add latency, not quality, and none are in
  this repository (checked 2026-09-23).
- **Which level.** Keep slate operation at the model's default: the engine
  computes every number, so more thinking buys nothing on a slate and costs
  clock. Keep ordinary roadmap sessions at the default too. Raise a
  `Standalone` solver-heavy session only after a run at the default missed
  something, and record that in the changelog. `max` and `ultracode` need a
  measured gain first.

### Keeping a Windows checkout in sync

Cloud sessions merge into `main` through pull requests, so the Windows checkout
only ever needs a fast-forward. `sync.ps1` in the repository root performs it.
Add this one line to your PowerShell profile, once, with your own path:

```powershell
function Sync-NflDfs { & 'C:\Users\benja\Documents\Claude\nfl-dfs\sync.ps1' @args }
```

`notepad $PROFILE` opens that file; `New-Item -ItemType File -Path $PROFILE
-Force` creates it first if it does not exist. Then `Sync-NflDfs` from any
folder, at the start of each working session.

**The profile holds a pointer, not a copy.** That is the point: `sync.ps1`
arrives with every sync, so the tool improves itself, and a copy pasted into a
profile would freeze on the day it was pasted. The script finds the repository
through `$PSScriptRoot`, so the path above is the only one anywhere.

What it will not do, because `CLAUDE.md` says this tree is often intentionally
dirty with user-owned work: it never stashes, resets, cleans or discards
anything. `git pull --ff-only` cannot invent a merge commit or rewrite history,
and git refuses rather than overwrite a file you have edited. Every failure mode
ends with nothing changed.

Three things it stops on, and what each means:

- **"On '<branch>', not main."** You are on a feature branch. If it holds work
  you want, `git add -A` and `git commit` first, then `git checkout main` and
  run it again. Measured 2026-09-22: a Windows checkout was sitting on
  `codex/p1-salary-divergence-role-evidence` with 13 modified files, 59 commits
  behind. Committing them to that branch and switching cost nothing and lost
  nothing.
- **"Fast-forward refused."** Local `main` has commits the remote does not.
  Under this repository's rules that should not happen, because `main` changes
  only through a merged pull request. Move them to a branch rather than forcing
  anything.
- **"Dependencies changed."** `uv.lock` or `pyproject.toml` moved, so run
  `.\nfl.ps1 setup`. Worth the check because `uv sync --locked` fails outright
  in that case and the error does not say why. Rare: as of 2026-09-22 only the
  initial commit has ever touched either file.

Do not put this on a schedule. A background job pulling into a tree you are
mid-edit in is how the dirty-tree rule gets broken by accident. Run it when you
sit down.

There is no `sync.sh`. A cloud session clones fresh and is current by
definition, so it has nothing to sync.

Test results are one thing this never carries. `state/` is gitignored, so
`last suite:` reads `unknown` on a machine that has not run the suite itself.
Run `.\nfl.ps1 test` to fill it in; on Windows the expected result is
`1070 passed, 1 skipped`, the one skip being the symlink-permission case that
cannot run on Windows.

## The protected list, and why each entry is on it

`.github/protected-paths.txt` is the definition. Since 2026-09-20 it holds
three entries:

- **`CLAUDE.md`.** The permanent boundaries. `.claude/rules/*.md` may refine
  how Claude works and merges on green, but a change that would relax a
  boundary belongs in `CLAUDE.md`, where it needs the label.
- **`.claude/settings.json`.** The permission deny list and the hooks that
  enforce it.
- **`.github/protected-paths.txt`.** The list itself. Changing the gate is not
  something the thing being gated decides.

The release and evidence modules, the registered policy JSON, the workflows and
`.claude/rules/*.md` came off on 2026-09-20 (see the top of this file). CI, the
boundary tests and the pinned suite gate them now.

## Revoking authority

Set `"defaultMode": "default"` in `.claude/settings.json` and move the git
entries from `allow` back to `ask`. Claude will ask again on every commit. The
CI and the protected list keep working either way.

## Known environment facts

Measured in a cloud container on 2026-09-17:

- `uv sync --all-groups --locked --python 3.13.7` completes; `.venv-linux` holds
  Python 3.13.7.
- Full suite: `1 failed, 735 passed, 1 skipped in 155.56s`. The one failure was
  the hardcoded-expiry test in `tests/test_w6_live_preflight.py`, fixed later the
  same day by pinning its clock (changelog, 2026-09-17 CI unblock).
- `api.weather.gov` answers HTTP 200 from the container. An older note in
  `CLAUDE.md` said it did not; that note was wrong and is corrected.
- `raw.githubusercontent.com` and nflverse GitHub release downloads are both
  reachable.
