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
    * it stops rather than act when you are not on `main`.

    It lives in the repository rather than in a PowerShell profile so that it
    updates itself: improvements arrive with the next sync. The profile holds
    one line pointing here, not a copy that goes stale. `$PSScriptRoot` is the
    folder this file sits in, so there is no path to configure.

    Setup and the profile one-liner: docs/CLAUDE_CODE_SETUP.md, "Keeping a
    Windows checkout in sync".
#>

[CmdletBinding()]
param()

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

    if ($branch -ne 'main') {
        Write-Host "On '$branch', not main. Nothing pulled." -ForegroundColor Yellow
        Write-Host ""
        Write-Host "  If that branch has work you want to keep, save it first:" -ForegroundColor Yellow
        Write-Host "    git add -A"
        Write-Host "    git commit -m 'work in progress'"
        Write-Host ""
        Write-Host "  Then:" -ForegroundColor Yellow
        Write-Host "    git checkout main"
        Write-Host "    Sync-NflDfs"
        return
    }

    $incoming = git log --oneline "$before..origin/main"
    if (-not $incoming) {
        Write-Host "Already current at $($before.Substring(0,7))." -ForegroundColor Green
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
    if (Get-Command python -ErrorAction SilentlyContinue) {
        python scripts\repo_state.py --stdout
    }
}
finally {
    Pop-Location
}
