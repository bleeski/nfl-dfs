# Claude Code setup

Everything in this file is something only Ben can do. Claude cannot set branch
protection, cannot create a label in a repository it does not administer, and
cannot change the permission mode that governs itself.

## What changed, in plain terms

Claude now commits, pushes, opens pull requests, and merges them into `main` on
its own, once CI is green. It deletes its own merged branches. It does not ask
first.

Three things still stop it:

1. **CI.** `suite`, `boundaries` and `protected-paths` must all pass on the
   pull request's head commit. A red or missing check is a hard stop.
2. **The protected list.** A pull request touching anything in
   `.github/protected-paths.txt` is never merged by Claude, green or not. It
   gets the `ben-review` label and waits for you.
3. **The permanent boundaries**, now asserted by `tests/test_repo_boundaries.py`
   rather than relying on you reading the diff.
4. **A command guard.** `.claude/hooks/guard_bash.py` runs before every Bash
   call and refuses forced pushes, amends, whole-tree staging, rebases, hard
   resets, `clean`, `stash`, forced branch deletion, and any push to `main`,
   including when the flag arrives after an allowed prefix or sits in a chained
   second command. Permission rules match a prefix and can see neither.

`.claude/rules/git-authority.md` is the full rule.

## One-time, in GitHub

### Branch protection on `main`

Without this, "merge only when green" is a promise rather than a rule. Anyone
with push access, Claude included, could push straight to `main`.

Settings → Branches → Add branch ruleset (or classic branch protection) for
`main`:

- Require a pull request before merging.
- Require status checks to pass: add `suite`, `boundaries`, `protected-paths`.
- Require branches to be up to date before merging.
- Block force pushes.
- Do not allow bypassing the above settings.

Leave "require approvals" at zero. Requiring a human approval would put you back
in the loop on every change, which is the thing this removes. The protected list
is the targeted version of that control.

### The review label

Issues → Labels → New label, named exactly `ben-review`. The CI job looks for
that string. Any colour.

The first pull request that touches a protected path will fail
`protected-paths` until the label exists, which is the correct failure.

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

## The protected list, and why each entry is on it

`.github/protected-paths.txt` is the definition. The categories:

- **`CLAUDE.md` and `.claude/rules/*.md`.** The boundaries themselves. If Claude
  could edit the rule that constrains it, the rule is decorative.
- **`release.py`, `certification.py`, `preflight.py`, `evidence.py`,
  `sources.py`.** What may be released, what counts as proof, and what the
  engine is allowed to fetch.
- **`config/evidence_policy.json`, `config/metric_registry_*.json`.** The
  pre-declared thresholds. A metric registry edited after seeing the data is not
  a pre-registration, it is a story.
- **`.claude/settings.json`, `.github/protected-paths.txt`,
  `.github/workflows/*.yml`.** The authority model. Changing the gate is not
  something the thing being gated decides.

## Revoking authority

Set `"defaultMode": "default"` in `.claude/settings.json` and move the git
entries from `allow` back to `ask`. Claude will ask again on every commit. The
CI and the protected list keep working either way.

## Known environment facts

Measured in a cloud container on 2026-09-17:

- `uv sync --all-groups --locked --python 3.13.7` completes; `.venv-linux` holds
  Python 3.13.7.
- Full suite: `1 failed, 735 passed, 1 skipped in 155.56s`. The one failure is
  the documented hardcoded-expiry test that chunk P0 repairs.
- `api.weather.gov` answers HTTP 200 from the container. An older note in
  `CLAUDE.md` said it did not; that note was wrong and is corrected.
- `raw.githubusercontent.com` and nflverse GitHub release downloads are both
  reachable.
