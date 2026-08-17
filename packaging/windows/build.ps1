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

    if (-not (Test-Path $InnoSetup)) {
        throw "Inno Setup not found at $InnoSetup. Install it or pass -InnoSetup."
    }
    $env:RUNTIME_VERSION = $version
    & $InnoSetup packaging\windows\installer.iss
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed." }

    Write-Host "==> dist\LocalRuntimeSetup-$version.exe" -ForegroundColor Green
} finally { Pop-Location }
