#Requires -Version 5.1
[CmdletBinding()]
param([string]$InnoSetup = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe")

$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path "$PSScriptRoot\..\..").Path
Push-Location $repo
try {
    $version = (Select-String -Path pyproject.toml -Pattern '^version = "(.+)"').Matches[0].Groups[1].Value
    Write-Host "==> Building Local Runtime $version"

    & .venv\Scripts\python.exe -m PyInstaller --noconfirm --clean `
        packaging\windows\runtime.spec
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed." }

    # Only runtime.exe is smoke-tested: setup.exe is the same code frozen for the
    # GUI subsystem, which PowerShell neither waits on nor reads output from.
    if (-not (Test-Path dist\LocalRuntime\setup.exe)) { throw "setup.exe was not built." }

    & dist\LocalRuntime\runtime.exe version
    if ($LASTEXITCODE -ne 0) { throw "Smoke test failed: runtime.exe version." }
    # version never touches disk, so it can pass on a bundle that's missing a
    # datas entry; selfcheck resolves each bundled asset the way the real
    # code does and catches that class of failure before it reaches a user.
    & dist\LocalRuntime\runtime.exe selfcheck
    if ($LASTEXITCODE -ne 0) { throw "Smoke test failed: runtime.exe selfcheck reported a missing bundled asset." }

    if (-not (Test-Path $InnoSetup)) {
        throw "Inno Setup not found at $InnoSetup. Install it or pass -InnoSetup."
    }
    $env:RUNTIME_VERSION = $version
    & $InnoSetup packaging\windows\installer.iss
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed." }

    Write-Host "==> dist\LocalRuntimeSetup-$version.exe" -ForegroundColor Green
} finally { Pop-Location }
