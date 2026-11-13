# Sign EXE/MSI files with Authenticode when credentials are available.
param(
    [Parameter(Mandatory = $true)]
    [string[]]$Paths
)

$ErrorActionPreference = "Stop"

function Find-SignTool {
    $candidates = @(
        "${env:ProgramFiles(x86)}\Windows Kits\10\bin\*\x64\signtool.exe",
        "${env:ProgramFiles}\Windows Kits\10\bin\*\x64\signtool.exe"
    )
    Get-ChildItem -Path $candidates -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending |
        Select-Object -First 1 -ExpandProperty FullName
}

$existing = @($Paths | Where-Object { $_ -and (Test-Path $_) })
if (-not $existing) {
    Write-Warning "No files to sign."
    return
}

$signtool = Find-SignTool
if (-not $signtool) {
    Write-Warning "signtool.exe not found. Install Windows SDK Signing Tools to enable Authenticode signing."
    return
}

$timestamp = if ($env:SIGN_TIMESTAMP_URL) { $env:SIGN_TIMESTAMP_URL } else { "http://timestamp.digicert.com" }

if ($env:SIGN_CERT_PFX -and (Test-Path $env:SIGN_CERT_PFX)) {
    $passwordArgs = @()
    if ($env:SIGN_CERT_PASSWORD) {
        $passwordArgs = @("/p", $env:SIGN_CERT_PASSWORD)
    }
    foreach ($path in $existing) {
        Write-Host "Signing $path with PFX certificate"
        & $signtool sign /fd SHA256 /td SHA256 /tr $timestamp /f $env:SIGN_CERT_PFX @passwordArgs $path
        if ($LASTEXITCODE -ne 0) { throw "signtool failed for $path" }
        & $signtool verify /pa $path
        if ($LASTEXITCODE -ne 0) { throw "signtool verify failed for $path" }
    }
    Write-Host "Signed $($existing.Count) file(s)."
    return
}

if ($env:AZURE_TRUSTED_SIGNING_ACCOUNT -and $env:AZURE_TRUSTED_SIGNING_ENDPOINT) {
    Write-Warning "Azure Trusted Signing env vars detected but this script currently supports PFX via SIGN_CERT_PFX. Use the Trusted Signing Action in CI or extend sign.ps1."
    return
}

Write-Warning "No SIGN_CERT_PFX provided — outputs remain unsigned (SmartScreen/Defender may warn)."
