# Build Tally Sync Windows app (PyInstaller) and optional Inno Setup installer.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$version = (Get-Content -Raw (Join-Path $root "VERSION")).Trim()
$env:TALLY_SYNC_VERSION = $version
Write-Host "Building Tally Sync v$version"

$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) { throw "Python not found on PATH" }
$python = $pythonCmd.Source

& $python -m pip install -r requirements.txt pyinstaller
& $python -m PyInstaller --noconfirm --clean (Join-Path $root "packaging\tally_sync.spec")

$dist = Join-Path $root "dist\TallySync"
if (-not (Test-Path (Join-Path $dist "TallySync.exe"))) {
    throw "PyInstaller output missing: $dist\TallySync.exe"
}
Write-Host "App folder: $dist"

$iscc = @(
    "${env:LocalAppData}\Programs\Inno Setup 6\ISCC.exe",
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if ($iscc) {
    New-Item -ItemType Directory -Force -Path (Join-Path $root "packaging\output") | Out-Null
    & $iscc (Join-Path $root "packaging\installer.iss")
    Write-Host "Installer written under packaging\output\"
} else {
    Write-Warning "Inno Setup (ISCC.exe) not found. App build succeeded; install Inno Setup 6 to create TallySyncSetup-$version.exe"
}

Write-Host "Done."
