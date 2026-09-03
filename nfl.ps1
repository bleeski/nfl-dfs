[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('setup','run','cowork-run','doctor','status','intake','workbook','validate','certify','build','late-swap','settle','learn','audit','test')]
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
        & $PythonExe -m pytest @RemainingArgs
    }
    else {
        & $PythonExe -m nfl_dfs.cli $Command @RemainingArgs
    }
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
    Pop-Location
}
