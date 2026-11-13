# Build Pluschwood and/or AutoSync Windows apps (PyInstaller) + Inno installers.
param(
    [ValidateSet("pluschwood", "autosync", "both")]
    [string]$Product = "both",
    [switch]$Sign
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

$shouldSign = $Sign.IsPresent -or ($env:SIGN_CERT_PFX -and (Test-Path $env:SIGN_CERT_PFX))
if ($shouldSign) {
    $env:TALLY_SYNC_SIGN = "1"
} else {
    Remove-Item Env:TALLY_SYNC_SIGN -ErrorAction SilentlyContinue
}

function Invoke-Sign([string[]]$Paths) {
    if (-not $shouldSign) { return }
    & (Join-Path $root "packaging\sign.ps1") -Paths $Paths
}

function Build-Product([string]$Name) {
    $exeName = if ($Name -eq "pluschwood") { "PluschwoodTallySync" } else { "AutoSyncTallySync" }
    $env:TALLY_SYNC_PRODUCT = $Name
    $env:TALLY_SYNC_EXE_NAME = $exeName
    Set-Content -Path (Join-Path $root "PRODUCT") -Value $Name -NoNewline
    Write-Host "Building $Name ($exeName) v$version"

    $versionInfo = Join-Path $root "packaging\version_info_$Name.txt"
    & $python (Join-Path $root "packaging\write_version_info.py") `
        --product $Name `
        --version $version `
        --output $versionInfo

    & $python -m PyInstaller --noconfirm --clean (Join-Path $root "packaging\tally_sync.spec")

    $dist = Join-Path $root "dist\$exeName"
    $exePath = Join-Path $dist "$exeName.exe"
    if (-not (Test-Path $exePath)) {
        throw "PyInstaller output missing: $exePath"
    }
    Write-Host "App folder: $dist"
    Invoke-Sign @($exePath)

    if ($iscc) {
        New-Item -ItemType Directory -Force -Path (Join-Path $root "packaging\output") | Out-Null
        $iss = Join-Path $root "packaging\installer.iss"
        if ($shouldSign -and $env:SIGN_CERT_PFX) {
            # Configure Inno SignTool alias "tallysync" for this build.
            $pwdArg = if ($env:SIGN_CERT_PASSWORD) { "/p `"$($env:SIGN_CERT_PASSWORD)`"" } else { "" }
            $signCmd = "signtool.exe sign /fd SHA256 /td SHA256 /tr http://timestamp.digicert.com /f `"$($env:SIGN_CERT_PFX)`" $pwdArg `$f"
            & $iscc "/Satalysync=$signCmd" $iss
        } else {
            & $iscc $iss
        }
        $setupName = if ($Name -eq "pluschwood") {
            "PluschwoodTallySyncSetup-$version.exe"
        } else {
            "AutoSyncTallySyncSetup-$version.exe"
        }
        $setup = Get-Item (Join-Path $root "packaging\output\$setupName") -ErrorAction SilentlyContinue
        if ($setup) {
            Invoke-Sign @($setup.FullName)
            Write-Host "Installer: $($setup.FullName)"
        } else {
            Write-Host "Installer written under packaging\output\"
        }
    } else {
        Write-Warning "Inno Setup (ISCC.exe) not found. App build succeeded; install Inno Setup 6 to create setup exe."
    }
}

$targets = if ($Product -eq "both") { @("pluschwood", "autosync") } else { @($Product) }
foreach ($target in $targets) {
    Build-Product $target
}

if (-not $shouldSign) {
    Write-Host ""
    Write-Host "NOTE: Build is unsigned. Windows Defender/SmartScreen often flags unsigned PyInstaller installers."
    Write-Host "      Obtain an Authenticode certificate (OV/EV) and rebuild with:"
    Write-Host "      `$env:SIGN_CERT_PFX='C:\path\code-sign.pfx'"
    Write-Host "      `$env:SIGN_CERT_PASSWORD='...'"
    Write-Host "      .\packaging\build.ps1 -Product both -Sign"
}

Write-Host "Done."
