#Requires -Version 5.1
[CmdletBinding()]
param([string]$InnoSetup)

$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path "$PSScriptRoot\..\..").Path

# PowerShell's call operator rejects bare relative paths: `& .venv\...` is
# parsed as a module name, not a program. Every invocation below is absolute.
$venvPython = Join-Path $repo '.venv\Scripts\python.exe'
$cliExe     = Join-Path $repo 'dist\LocalRuntime\runtime.exe'
$setupExe   = Join-Path $repo 'dist\LocalRuntime\setup.exe'
$specFile   = Join-Path $repo 'packaging\windows\runtime.spec'
$issFile    = Join-Path $repo 'packaging\windows\installer.iss'

function Resolve-Iscc {
    # Inno's install location moves between versions and install modes: 6.3+
    # ships a 64-bit build under Program Files, and winget may install per-user.
    # The registry key it writes is the only stable answer; paths are fallbacks.
    foreach ($hive in 'HKLM:', 'HKCU:') {
        foreach ($view in 'SOFTWARE', 'SOFTWARE\WOW6432Node') {
            $key = "$hive\$view\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1"
            $loc = (Get-ItemProperty -Path $key -Name InstallLocation -ErrorAction SilentlyContinue).InstallLocation
            if ($loc) {
                $candidate = Join-Path $loc 'ISCC.exe'
                if (Test-Path $candidate) { return $candidate }
            }
        }
    }
    $paths = @(
        (Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'),
        (Join-Path $env:ProgramFiles 'Inno Setup 6\ISCC.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe')
    )
    foreach ($p in $paths) { if ($p -and (Test-Path $p)) { return $p } }
    $cmd = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
}

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

    if (-not $InnoSetup) { $InnoSetup = Resolve-Iscc }
    if (-not $InnoSetup -or -not (Test-Path $InnoSetup)) {
        throw ("ISCC.exe not found. Install Inno Setup 6 " +
               "(winget install -e --id JRSoftware.InnoSetup), or pass its path " +
               "with -InnoSetup. Searched the Inno Setup 6_is1 registry key under " +
               "HKLM and HKCU, Program Files, Program Files (x86), " +
               "%LOCALAPPDATA%\Programs, and PATH.")
    }
    Write-Host "==> ISCC: $InnoSetup"
    $env:RUNTIME_VERSION = $version
    & $InnoSetup $issFile
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed." }

    Write-Host "==> dist\LocalRuntimeSetup-$version.exe" -ForegroundColor Green
} finally { Pop-Location }
