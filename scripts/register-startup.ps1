# Register the selected product for Windows startup (current user).
param(
    [ValidateSet("pluschwood", "autosync")]
    [string]$Product = "pluschwood"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

$exeName = if ($Product -eq "pluschwood") { "PluschwoodTallySync" } else { "AutoSyncTallySync" }
$appName = if ($Product -eq "pluschwood") { "Pluschwood Tally Sync" } else { "AutoSync Tally Sync" }

$candidates = @(
    (Join-Path $root "dist\$exeName\$exeName.exe"),
    (Join-Path ${env:ProgramFiles} "$exeName\$exeName.exe"),
    (Join-Path ${env:LOCALAPPDATA} "Programs\$exeName\$exeName.exe")
)
$target = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $target) {
    throw "Could not find $exeName.exe. Build or install the app first."
}

$startup = [Environment]::GetFolderPath("Startup")
$shortcutPath = Join-Path $startup "$appName.lnk"
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $target
$shortcut.WorkingDirectory = Split-Path $target
$shortcut.Description = $appName
$shortcut.Save()
Write-Host "Startup shortcut: $shortcutPath -> $target"
