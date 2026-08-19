#Requires -Version 5.1
[CmdletBinding()]
param([string]$InnoSetup = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe")

$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path "$PSScriptRoot\..\..").Path

# PowerShell's call operator rejects bare relative paths: `& .venv\...` is
# parsed as a module name, not a program. Every invocation below is absolute.
$venvPython = Join-Path $repo '.venv\Scripts\python.exe'
$cliExe     = Join-Path $repo 'dist\LocalRuntime\runtime.exe'
$setupExe   = Join-Path $repo 'dist\LocalRuntime\setup.exe'
$specFile   = Join-Path $repo 'packaging\windows\runtime.spec'
$issFile    = Join-Path $repo 'packaging\windows\installer.iss'

Push-Location $repo
try {
    if (-not (Test-Path $venvPython)) {
        throw "No virtualenv at $venvPython. Run: py -3.12 -m venv .venv"
    }
    & $venvPython -c "import PyInstaller" 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller missing. Run: .\.venv\Scripts\python.exe -m pip install -e `".[dev]`""
    }

    $version = (Select-String -Path (Join-Path $repo 'pyproject.toml') `
        -Pattern '^version = "(.+)"').Matches[0].Groups[1].Value
    Write-Host "==> Building Local Runtime $version"

    & $venvPython -m PyInstaller --noconfirm --clean $specFile
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed." }

    # Only runtime.exe is smoke-tested: setup.exe is the same code frozen for the
    # GUI subsystem, which PowerShell neither waits on nor reads output from.
    if (-not (Test-Path $setupExe)) { throw "setup.exe was not built." }

    & $cliExe version
    if ($LASTEXITCODE -ne 0) { throw "Smoke test failed: runtime.exe version." }
    # version never touches disk, so it can pass on a bundle that's missing a
    # datas entry; selfcheck resolves each bundled asset the way the real
    # code does and catches that class of failure before it reaches a user.
    & $cliExe selfcheck
    if ($LASTEXITCODE -ne 0) { throw "Smoke test failed: runtime.exe selfcheck reported a missing bundled asset." }

    if (-not (Test-Path $InnoSetup)) {
        throw "Inno Setup not found at $InnoSetup. Install it or pass -InnoSetup."
    }
    $env:RUNTIME_VERSION = $version
    & $InnoSetup $issFile
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed." }

    Write-Host "==> dist\LocalRuntimeSetup-$version.exe" -ForegroundColor Green
} finally { Pop-Location }
