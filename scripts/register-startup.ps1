# Register the Tally sync agent to start at Windows logon for the current user.
$project = Split-Path -Parent $PSScriptRoot
$python = (Get-Command python -ErrorAction SilentlyContinue)?.Source
if (-not $python) {
    Write-Error "Python was not found on PATH."
    exit 1
}
$startup = [Environment]::GetFolderPath("Startup")
$shortcutPath = Join-Path $startup "AutoSync Tally Sync.lnk"
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $python
$shortcut.Arguments = "-m agent"
$shortcut.WorkingDirectory = $project
$shortcut.WindowStyle = 7
$shortcut.Description = "AutoSync Tally Sync Agent"
$shortcut.Save()
Write-Output "Created $shortcutPath"
