# Build Pluschwood and/or AutoSync Windows apps (PyInstaller) + Inno installers.
param(
    [ValidateSet("pluschwood", "autosync", "both")]
    [string]$Product = "both"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$version = (Get-Content -Raw (Join-Path $root "VERSION")).Trim()
$env:TALLY_SYNC_VERSION = $version

$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) { throw "Python not found on PATH" }
$python = $pythonCmd.Source

& $python -m pip install -r requirements.txt pyinstaller

$iscc = @(
    "${env:LocalAppData}\Programs\Inno Setup 6\ISCC.exe",
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

function Build-Product([string]$Name) {
    $exeName = if ($Name -eq "pluschwood") { "PluschwoodTallySync" } else { "AutoSyncTallySync" }
    $env:TALLY_SYNC_PRODUCT = $Name
    $env:TALLY_SYNC_EXE_NAME = $exeName
    Set-Content -Path (Join-Path $root "PRODUCT") -Value $Name -NoNewline
    Write-Host "Building $Name ($exeName) v$version"

    & $python -m PyInstaller --noconfirm --clean (Join-Path $root "packaging\tally_sync.spec")

    $dist = Join-Path $root "dist\$exeName"
    if (-not (Test-Path (Join-Path $dist "$exeName.exe"))) {
        throw "PyInstaller output missing: $dist\$exeName.exe"
    }
    Write-Host "App folder: $dist"

    if ($iscc) {
        New-Item -ItemType Directory -Force -Path (Join-Path $root "packaging\output") | Out-Null
        & $iscc (Join-Path $root "packaging\installer.iss")
        Write-Host "Installer written under packaging\output\"
    } else {
        Write-Warning "Inno Setup (ISCC.exe) not found. App build succeeded; install Inno Setup 6 to create setup exe."
    }
}

$targets = if ($Product -eq "both") { @("pluschwood", "autosync") } else { @($Product) }
foreach ($target in $targets) {
    Build-Product $target
}

Write-Host "Done."
