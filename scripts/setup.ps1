$ErrorActionPreference = 'Stop'
Push-Location (Join-Path $PSScriptRoot '..')
try {
    foreach ($tool in @('git', 'docker')) {
        if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { throw "$tool is required; see handbook/operator/setup.md" }
    }
    $setupPython = $env:TUEKA_SETUP_PYTHON
    $setupPythonArgs = @()
    if (-not $setupPython) {
        if (Get-Command py -ErrorAction SilentlyContinue) { $setupPython = 'py'; $setupPythonArgs = @('-3.13') }
        else { $setupPython = 'python' }
    }
    & $setupPython @setupPythonArgs -c 'import sys; assert sys.version_info[:2] == (3, 13), "Python 3.13 required; see handbook/operator/setup.md"'
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    if (-not (Test-Path '.venv-operator/Scripts/python.exe')) {
        & $setupPython @setupPythonArgs -m venv .venv-operator
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
    & .venv-operator/Scripts/python.exe -c 'import sys; assert sys.version_info[:2] == (3, 13)'
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & .venv-operator/Scripts/python.exe -m pip install --require-hashes -r requirements.lock
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & .venv-operator/Scripts/python.exe scripts/setup.py @args
    exit $LASTEXITCODE
} finally { Pop-Location }
