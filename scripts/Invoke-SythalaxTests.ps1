<#
.SYNOPSIS
    Run the Sythalax test suite deterministically on Windows.

.DESCRIPTION
    Windows adds two failure modes to this suite that have nothing to do with
    the code under test:

      * pytest's default base temp, %TEMP%\pytest-of-<user>, survives the
        session that created it. A stale copy the current user cannot write
        into fails the whole run with WinError 5 before collection starts.
      * That default is deep, this repository's test names are long, and
        Windows refuses paths past MAX_PATH (260 characters). A Board custody
        test has already failed at exactly 260 and passed unchanged under a
        shorter root.

    This script pins the parts of the environment that cause both — the
    interpreter and the temporary root — and then hands control to pytest.

    It repairs nothing outside the root it chooses. A stale, inaccessible
    default temp directory is stepped around rather than deleted or
    re-permissioned, because doing either would require elevation, and this
    must run without it.

    It hides nothing. pytest's own output is passed through untouched and its
    exit code becomes this script's exit code, so a failing suite fails the
    caller. There is no retry, no filtering and no error suppression anywhere
    below.

.PARAMETER BaseTempRoot
    Short directory to use for all test temporary files. Defaults to the same
    resolution conftest.py performs: SYTHALAX_TEST_TMP, then C:\sxt, then
    <repo>\.sxt, taking the first that can actually be written to.

.PARAMETER Python
    Interpreter to use. Defaults to an active virtualenv, then <repo>\.venv,
    then the 3.12 launcher, then whatever `python` resolves to.

.PARAMETER V3Only
    Restrict the run to tests/dynamic_weekly_mc_v3.

.PARAMETER PytestArgs
    Extra arguments forwarded to pytest verbatim. Pass them by name as an
    array. PowerShell tries to bind any bare leading-dash token as a parameter
    of this script, so `-k custody` written directly on the command line is a
    binding error rather than a pytest filter.

.EXAMPLE
    .\scripts\Invoke-SythalaxTests.ps1
    Full suite on a short temporary root.

.EXAMPLE
    .\scripts\Invoke-SythalaxTests.ps1 -V3Only
    The 461 V3 tests only.

.EXAMPLE
    .\scripts\Invoke-SythalaxTests.ps1 -V3Only -PytestArgs @('-k', 'custody', '-x')
    V3 tests, filtered, stopping at the first failure.
#>
[CmdletBinding()]
param(
    [string]$BaseTempRoot,
    [string]$Python,
    [switch]$V3Only,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$PytestArgs
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot

# --- temporary root ----------------------------------------------------------
# Probed by writing a real file. On Windows a directory can be listable and
# still refuse writes, which is precisely the stale-root condition being
# avoided, so existence is never taken as proof of usability.
function Test-WritableRoot {
    param([string]$Path)
    try {
        $null = New-Item -ItemType Directory -Path $Path -Force -ErrorAction Stop
        $probe = Join-Path $Path '.probe'
        [System.IO.File]::WriteAllBytes($probe, @())
        Remove-Item -LiteralPath $probe -Force -ErrorAction Stop
        return $true
    }
    catch {
        return $false
    }
}

$candidates = @()
if ($BaseTempRoot)            { $candidates += $BaseTempRoot }
if ($env:SYTHALAX_TEST_TMP)   { $candidates += $env:SYTHALAX_TEST_TMP }
$candidates += 'C:\sxt'
$candidates += (Join-Path $RepoRoot '.sxt')

$root = $null
foreach ($candidate in $candidates) {
    if (Test-WritableRoot -Path $candidate) { $root = $candidate; break }
}
if (-not $root) {
    throw ("No writable temporary root. Tried: " + ($candidates -join ', ') +
           ". Pass -BaseTempRoot with a short directory you can write to.")
}

# conftest.py performs the same resolution for anyone running pytest directly.
# Exporting the decision keeps both paths on one answer instead of two.
$env:SYTHALAX_TEST_TMP = $root
$scratch = Join-Path $root 't'
$null = New-Item -ItemType Directory -Path $scratch -Force
$env:TMP = $scratch
$env:TEMP = $scratch

# --- interpreter -------------------------------------------------------------
if (-not $Python) {
    $repoVenv = Join-Path $RepoRoot '.venv\Scripts\python.exe'
    if ($env:VIRTUAL_ENV -and (Test-Path -LiteralPath (Join-Path $env:VIRTUAL_ENV 'Scripts\python.exe'))) {
        $Python = Join-Path $env:VIRTUAL_ENV 'Scripts\python.exe'
    }
    elseif (Test-Path -LiteralPath $repoVenv) {
        $Python = $repoVenv
    }
    elseif (Get-Command py -ErrorAction SilentlyContinue) {
        $Python = 'py'
    }
    else {
        $Python = 'python'
    }
}
$pythonArgs = @()
if ($Python -eq 'py') { $pythonArgs += '-3.12' }

# The project requires >= 3.12. Checked here so an unsupported interpreter is
# named now rather than surfacing later as an unrelated-looking test failure.
$versionProbe = & $Python @pythonArgs -c "import sys; print('%d.%d' % sys.version_info[:2])"
if ($LASTEXITCODE -ne 0) {
    throw "Could not run the selected interpreter: $Python"
}
$parsed = [version]$versionProbe
if ($parsed -lt [version]'3.12') {
    throw "Python $versionProbe is too old; this project requires >= 3.12. Pass -Python explicitly."
}

# --- run ---------------------------------------------------------------------
$target = if ($V3Only) { 'tests/dynamic_weekly_mc_v3' } else { 'tests' }
$basetemp = Join-Path $root 'bt'

Write-Host "repo        : $RepoRoot"
Write-Host "interpreter : $Python $($pythonArgs -join ' ') (Python $versionProbe)"
Write-Host "temp root   : $root"
Write-Host "basetemp    : $basetemp"
Write-Host "target      : $target"
Write-Host ''

Push-Location $RepoRoot
try {
    & $Python @pythonArgs -m pytest $target --basetemp $basetemp @PytestArgs
    $code = $LASTEXITCODE
}
finally {
    Pop-Location
}

# pytest's verdict, unmodified. 0 pass, 1 failures, 2 interrupted, 5 nothing
# collected — every one of which the caller needs to see.
exit $code
