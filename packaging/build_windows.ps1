<#
Builds the Windows artifacts: the PyInstaller folder, the portable zip and,
when Inno Setup is available, the installer. Run from anywhere:
  powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1
Pass -SkipTests to skip the test suite.
#>
param([switch]$SkipTests)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

# Native commands do not stop the script on failure by themselves.
function Invoke-Checked {
    param([string]$Exe, [string[]]$Arguments)
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Exe $($Arguments -join ' ') failed with exit code $LASTEXITCODE"
    }
}

$initText = Get-Content -Raw -Path (Join-Path $Root 'madtracker\__init__.py')
if ($initText -notmatch '(?m)^__version__\s*=\s*"([^"]+)"') {
    throw 'Could not read __version__ from madtracker\__init__.py'
}
$Version = $Matches[1]
Write-Host "Building MadTracker $Version"

$VenvDir = Join-Path $Root '.venv-build'
$VenvPython = Join-Path $VenvDir 'Scripts\python.exe'
if (-not (Test-Path $VenvPython)) {
    Invoke-Checked 'python' @('-m', 'venv', $VenvDir)
}
Invoke-Checked $VenvPython @('-m', 'pip', 'install', '--upgrade', 'pip')
# Pinned packages first (requirements.txt includes PyInstaller), then the app.
Invoke-Checked $VenvPython @('-m', 'pip', 'install', '-r', 'requirements.txt')
Invoke-Checked $VenvPython @('-m', 'pip', 'install', '-e', '.')

if (-not $SkipTests) {
    $env:QT_QPA_PLATFORM = 'offscreen'
    # A test stuck on a dialog nobody can click reports where it is after
    # 90 seconds instead of sitting silent.
    Invoke-Checked $VenvPython @('-m', 'pytest', '-q', '-p', 'no:cacheprovider', '-o', 'faulthandler_timeout=90')
    Remove-Item Env:\QT_QPA_PLATFORM
}

Invoke-Checked $VenvPython @('-m', 'PyInstaller', 'packaging\madtracker.spec', '--noconfirm', '--clean')

# The windowed exe has no console, so a plain call returns before the app
# exits. Start-Process -Wait gives a reliable exit code.
$Exe = Join-Path $Root 'dist\MadTracker\MadTracker.exe'
$selfTest = Start-Process -FilePath $Exe -ArgumentList '--self-test' -Wait -PassThru
if ($selfTest.ExitCode -ne 0) {
    throw "Self-test failed with exit code $($selfTest.ExitCode)"
}
Write-Host 'Self-test passed'

$Zip = Join-Path $Root "dist\MadTracker-$Version-portable.zip"
if (Test-Path $Zip) { Remove-Item $Zip }
Compress-Archive -Path (Join-Path $Root 'dist\MadTracker') -DestinationPath $Zip

$Setup = $null
$iscc = Get-Command 'ISCC.exe' -ErrorAction SilentlyContinue
$isccPath = if ($iscc) { $iscc.Source } else { $null }
if (-not $isccPath) {
    # Any version's default folder, newest first: the installer does not
    # add itself to PATH, and the script must not care whether it is 6 or 7.
    $roots = @("${env:ProgramFiles(x86)}", $env:ProgramFiles, "$env:LOCALAPPDATA\Programs")
    $found = foreach ($r in $roots) {
        if ($r) { Get-ChildItem -Path $r -Directory -Filter 'Inno Setup*' -ErrorAction SilentlyContinue }
    }
    $isccPath = $found |
        Sort-Object Name -Descending |
        ForEach-Object { Join-Path $_.FullName 'ISCC.exe' } |
        Where-Object { Test-Path $_ } |
        Select-Object -First 1
}
if ($isccPath) {
    # The wizard's pictures are drawn from the app icon at build time, not
    # committed; installer.iss uses them when they exist.
    Invoke-Checked $VenvPython @('tools\make_installer_images.py')
    Invoke-Checked $isccPath @("/DAppVersion=$Version", 'packaging\installer.iss')
    $Setup = Join-Path $Root "dist\MadTracker-$Version-setup.exe"
} else {
    Write-Warning 'Inno Setup (ISCC.exe) not found. Skipping the installer.'
}

Write-Host ''
Write-Host 'Artifacts:'
Write-Host "  Folder:    $(Join-Path $Root 'dist\MadTracker')"
Write-Host "  Portable:  $Zip"
if ($Setup) { Write-Host "  Installer: $Setup" }
