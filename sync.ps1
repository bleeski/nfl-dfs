<#
.SYNOPSIS
    Bring this checkout up to date with GitHub, without touching your own work.

.DESCRIPTION
    Ben runs this at the start of a working session. Cloud Claude Code sessions
    merge into `main` through pull requests, so a Windows checkout only ever
    needs a fast-forward; this performs that and refuses anything else.

    It is deliberately conservative, because `CLAUDE.md` says this working tree
    is often intentionally dirty with user-owned work:

    * it never stashes, resets, cleans or discards anything;
    * `git pull --ff-only` cannot invent a merge commit or rewrite history, and
      git itself refuses rather than overwrite a file you have edited, so the
      worst case is that it stops and says why;
    * it stops rather than act when you are not on `main`, except under -Clean
      when the branch you are on is a merged `claude/*` branch and the tree is
      clean (see below).

    It lives in the repository rather than in a PowerShell profile so that it
    updates itself: improvements arrive with the next sync. The profile holds
    one line pointing here, not a copy that goes stale. `$PSScriptRoot` is the
    folder this file sits in, so there is no path to configure.

    Setup and the profile one-liner: docs/CLAUDE_CODE_SETUP.md, "Keeping a
    Windows checkout in sync".

.PARAMETER Clean
    After a merge, also clean up. In order: if you are on a `claude/*` branch
    that is merged into origin/main and the tree is clean, switch to `main`;
    fast-forward `main`; delete each local `claude/*` branch that
    scripts\post_merge.py reports as merged, with `git branch -d` (which refuses
    an unmerged branch, so nothing unmerged is ever lost); then print IN SYNC or
    what is left. It never touches `codex/*` branches, stashes or worktrees, and
    it never deletes an unmerged branch. docs/claude/post_merge.md is the
    procedure.
#>

[CmdletBinding()]
param(
    [switch]$Clean
)

function Get-RepoPython {
    # The venv interpreter first: `Get-Command python` can resolve to the
    # Microsoft Store stub in WindowsApps, which prints "Python was not found".
    $venv = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
    if (Test-Path $venv) { return $venv }
    $found = Get-Command python -ErrorAction SilentlyContinue
    if ($found -and $found.Source -notlike '*WindowsApps*') { return $found.Source }
    return $null
}

function Invoke-Clean {
    $py = Get-RepoPython
    if (-not $py) {
        Write-Host "No Python found, so nothing was cleaned. Run .\nfl.ps1 setup, then Sync-NflDfs -Clean again." -ForegroundColor Yellow
        return
    }
    $current = (git rev-parse --abbrev-ref HEAD).Trim()
    $names = & $py scripts\post_merge.py --no-fetch --no-open-prs --format local-merged-names
    foreach ($name in $names) {
        $name = "$name".Trim()
        if ($name -and $name -ne $current) {
            Write-Host "Deleting merged branch $name" -ForegroundColor Cyan
            git branch -d $name
        }
    }

    Write-Host ""
    # --strict: anything left for you (an unmerged branch, a stash, a worktree) is exit 1, so IN SYNC
    # below is never printed above a list of things that are not.
    & $py scripts\post_merge.py --no-fetch --no-open-prs --strict --format text
    $verdict = $LASTEXITCODE

    $localMain = (git rev-parse main).Trim()
    $remoteMain = (git rev-parse origin/main).Trim()
    if ($localMain -ne $remoteMain) {
        Write-Host "Local main ($($localMain.Substring(0,7))) is not at origin/main ($($remoteMain.Substring(0,7)))." -ForegroundColor Yellow
        $verdict = 1
    }
    if ($verdict -eq 0) {
        Write-Host "IN SYNC." -ForegroundColor Green
    }
    else {
        Write-Host "Not fully in sync. What is left is listed above; none of it was touched." -ForegroundColor Yellow
    }
}

Push-Location $PSScriptRoot
try {
    $branch = (git rev-parse --abbrev-ref HEAD).Trim()
    $before = (git rev-parse HEAD).Trim()

    if (git status --porcelain) {
        Write-Host "You have local changes. Nothing below touches them:" -ForegroundColor Yellow
        git status --short
        Write-Host ""
    }

    git fetch origin --prune
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Fetch failed. Check the network, then run this again." -ForegroundColor Red
        return
    }

    if ($Clean -and $branch -ne 'main' -and $branch -like 'claude/*') {
        git merge-base --is-ancestor $branch origin/main
        $merged = ($LASTEXITCODE -eq 0)
        $dirty = git status --porcelain
        if ($merged -and -not $dirty) {
            Write-Host "On '$branch', which is merged into origin/main. Switching to main." -ForegroundColor Cyan
            git switch main
            if ($LASTEXITCODE -ne 0) {
                Write-Host "Could not switch to main. Nothing changed." -ForegroundColor Red
                return
            }
            $branch = 'main'
            $before = (git rev-parse HEAD).Trim()
        }
    }

    if ($branch -ne 'main') {
        Write-Host "On '$branch', not main. Nothing pulled." -ForegroundColor Yellow
        Write-Host ""
        Write-Host "  If that branch has work you want to keep, save it first:" -ForegroundColor Yellow
        Write-Host "    git status --short"
        Write-Host "    git add <the files you want, by name>"
        Write-Host "    git commit -m 'work in progress'"
        Write-Host ""
        Write-Host "  Then:" -ForegroundColor Yellow
        Write-Host "    git checkout main"
        Write-Host "    Sync-NflDfs -Clean"
        return
    }

    $incoming = git log --oneline "$before..origin/main"
    if (-not $incoming) {
        Write-Host "Already current at $($before.Substring(0,7))." -ForegroundColor Green
        if ($Clean) { Invoke-Clean }
        return
    }

    Write-Host "Incoming:" -ForegroundColor Cyan
    $incoming | ForEach-Object { Write-Host "  $_" }
    Write-Host ""

    # --ff-only is the safety. It refuses if local `main` has commits the remote
    # does not, which under this repository's rules should never happen: `main`
    # changes only through a merged pull request.
    git pull --ff-only origin main
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "Fast-forward refused. Nothing changed, which is the safe outcome." -ForegroundColor Red
        Write-Host "See docs/CLAUDE_CODE_SETUP.md, 'Keeping a Windows checkout in sync'." -ForegroundColor Red
        return
    }

    $after = (git rev-parse HEAD).Trim()

    # `uv sync --locked` fails outright when the lock moved and the environment
    # did not, and the error does not say that is what happened.
    if (git diff --name-only $before $after -- uv.lock pyproject.toml) {
        Write-Host ""
        Write-Host "Dependencies changed. Run this before the next slate:" -ForegroundColor Yellow
        Write-Host "  .\nfl.ps1 setup"
    }

    Write-Host ""
    Write-Host "Synced to $($after.Substring(0,7))." -ForegroundColor Green

    # The same digest a Claude Code session sees when it starts.
    $python = Get-RepoPython
    if ($python) {
        & $python scripts\repo_state.py --stdout
    }

    if ($Clean) { Invoke-Clean }
}
finally {
    Pop-Location
}
