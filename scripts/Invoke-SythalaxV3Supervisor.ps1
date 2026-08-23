[CmdletBinding()]
param(
    [ValidateSet('plan', 'run', 'status', 'resume', 'approve')]
    [string]$Command = 'plan',

    [string]$ConfigPath,

    [string]$RunId,

    [string]$RecommendationSha,

    [string]$Approver,

    [string]$Dispositions,

    [string]$Note = ''
)

# Wrapper for the autonomous V3 model-run supervisor.
#
# Same shape as Invoke-SythalaxDynamicWeeklyMCV3.ps1: resolve the repository
# root, default the config, put src on PYTHONPATH, prefer the py launcher and
# pass the process exit code straight through. Exit 2 means a governance refusal
# or a halted run; a run that stops at the human approval gate exits 0, because
# stopping there is the design rather than a failure of it.

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot

if (-not $ConfigPath) {
    $ConfigPath = Join-Path $RepoRoot 'config' |
        Join-Path -ChildPath 'dynamic_weekly_mc_v3' |
        Join-Path -ChildPath 'supervisor' |
        Join-Path -ChildPath 'v3_autonomous_run.json'
}

if (-not (Test-Path -LiteralPath $ConfigPath)) {
    throw "Supervisor config not found: $ConfigPath"
}

$Arguments = @($Command, '--config', $ConfigPath)

if ($Command -in @('status', 'resume', 'approve')) {
    if (-not $RunId) {
        throw "$Command requires -RunId."
    }
    $Arguments += @('--run-id', $RunId)
}

if ($Command -eq 'approve') {
    if (-not $RecommendationSha) {
        throw 'approve requires -RecommendationSha. An approval binds to the exact recommendation digest.'
    }
    if (-not $Approver) {
        throw 'approve requires -Approver. The parameter gate is the one step a person performs.'
    }
    $Arguments += @('--recommendation-sha', $RecommendationSha, '--approver', $Approver)
    if ($Dispositions) {
        # Answers to the questions the recommendation raises, as JSON or a path
        # to JSON. Required exactly when it raises any; the CLI refuses the
        # approval rather than proceeding with a question unanswered.
        $Arguments += @('--dispositions', $Dispositions)
    }
    if ($Note) {
        $Arguments += @('--note', $Note)
    }
}

$env:PYTHONPATH = Join-Path $RepoRoot 'src'
$Module = 'ncaaf_engine.simulation.dynamic_weekly_mc_v3.supervisor'

$PyLauncher = Get-Command py -ErrorAction SilentlyContinue
if ($PyLauncher) {
    & py -3.12 -m $Module @Arguments
}
else {
    $Python = Get-Command python -ErrorAction Stop
    & $Python.Source -m $Module @Arguments
}

if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
