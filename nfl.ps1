[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('setup','run','cowork-run','priors-propose','priors-freeze','project','select','review-export','doctor','status','intake','workbook','validate','certify','build','late-swap','settle','learn','audit','test')]
    [string]$Command = 'run',

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$RemainingArgs
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$TaskCache = Join-Path $ProjectRoot '.uv-cache'
$PythonExe = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$env:UV_CACHE_DIR = $TaskCache

Push-Location $ProjectRoot
try {
    if ($Command -eq 'setup') {
        uv sync --all-groups --locked --python 3.13.7
        if ($LASTEXITCODE -ne 0) { throw 'Setup could not install the pinned free packages.' }
    }
    if (-not (Test-Path -LiteralPath $PythonExe)) {
        throw 'The project environment is missing. Run: .\nfl.ps1 setup'
    }
    if ($Command -eq 'test') {
        # PowerShell binds a bare -p to the common parameter -PipelineVariable
        # before this script sees it, so pytest plugin and path flags cannot be
        # passed through here. Both writable roots pytest needs are therefore
        # fixed to per-user temp locations: the default basetemp root and the
        # repo-local .pytest_cache have both been left unreadable by bridge
        # mounts before, which fails every test at fixture setup.
        $PytestTmp = Join-Path $env:TEMP 'nfl-dfs-pytest'
        $PytestCache = Join-Path $env:TEMP 'nfl-dfs-pytest-cache'
        & $PythonExe -m pytest '--basetemp' $PytestTmp '-o' "cache_dir=$PytestCache" @RemainingArgs
    }
    else {
        & $PythonExe -m nfl_dfs.cli $Command @RemainingArgs
    }
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
    Pop-Location
}
