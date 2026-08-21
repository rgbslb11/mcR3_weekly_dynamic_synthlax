[CmdletBinding()]
param(
    [ValidateSet('validate', 'show-blockers', 'run')]
    [string]$Command = 'validate',

    [string]$ConfigPath,

    [string]$OutputRoot
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot

if (-not $ConfigPath) {
    $ConfigPath = Join-Path $RepoRoot 'config\dynamic_weekly_mc_v3\v3_experimental.json'
}
if (-not $OutputRoot) {
    $OutputRoot = Join-Path $RepoRoot 'output\dynamic_weekly_mc_v3'
}

if (-not (Test-Path -LiteralPath $ConfigPath)) {
    throw "V3 config not found: $ConfigPath"
}

$env:PYTHONPATH = Join-Path $RepoRoot 'src'

$PyLauncher = Get-Command py -ErrorAction SilentlyContinue
if ($PyLauncher) {
    & py -3.12 -m ncaaf_engine.simulation.dynamic_weekly_mc_v3.cli $Command --config $ConfigPath --output-root $OutputRoot
}
else {
    $Python = Get-Command python -ErrorAction Stop
    & $Python.Source -m ncaaf_engine.simulation.dynamic_weekly_mc_v3.cli $Command --config $ConfigPath --output-root $OutputRoot
}

if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
