# Tally Sync

Two Windows apps that sync an open TallyPrime company:

| App | Connects to | Installer |
| --- | --- | --- |
| **Pluschwood Tally Sync** | `https://console.pluschwood.com` | `PluschwoodTallySyncSetup-*.exe` |
| **AutoSync Tally Sync** | `https://autosync.app` | `AutoSyncTallySyncSetup-*.exe` |

Each build hardcodes its destination — no destination picker or base URL prompt.

- **Windows application window** (home summary, connection, settings) with menu bar
- System tray companion: close window hides to tray; **Open window** restores it
- Browser sign-in to register the tool with your org (pairing codes as fallback)
- Rich Pluschwood import payload (`pluschwood_tally_v2`)
- In-app **Check for updates…** downloads the matching product installer

## Requirements

- Windows 10/11
- TallyPrime open with a company loaded and HTTP on `http://127.0.0.1:9000`
- For development: Python 3.11+

## Install (end users)

1. Download the Setup EXE for your product from the release page for this repository.
2. Run the installer (optional: start at Windows sign-in).
3. Launch the app — the main window opens and a tray icon appears.
4. **Connection → Sign in to connect…** (or Enter pairing code), then run import.

State lives under:

- Pluschwood: `%LOCALAPPDATA%\PluschwoodTallySync\`
- AutoSync: `%LOCALAPPDATA%\AutoSyncTallySync\`

Tokens are DPAPI-protected. Sync counts go to `sync.log`.

## Develop

```powershell
cd "M:\Projects\Sync tool"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Default PRODUCT file is pluschwood. Switch with:
#   $env:TALLY_SYNC_PRODUCT="autosync"
# or edit the PRODUCT file at the repo root.
python -m agent
```

Optional date range / local URL overrides:

```powershell
$env:TALLY_IMPORT_FROM_DATE="2024-04-01"
$env:TALLY_IMPORT_TO_DATE="2026-03-31"
$env:PLUSCHWOOD_BASE_URL="http://127.0.0.1:8000"   # Pluschwood build only
$env:AUTOSYNC_BASE_URL="http://127.0.0.1:8000"      # AutoSync build only
```

Tests:

```powershell
python -m unittest discover -s tests -v
```

## Build Windows installers

1. Install [Inno Setup 6](https://jrsoftware.org/isinfo.php) (for the Setup EXE).
2. Run:

```powershell
python packaging\make_icon.py
powershell -ExecutionPolicy Bypass -File packaging\build.ps1 -Product both
# or: -Product pluschwood | -Product autosync
```

Outputs:

- `dist\PluschwoodTallySync\` / `dist\AutoSyncTallySync\` — portable app folders
- `packaging\output\PluschwoodTallySyncSetup-<version>.exe`
- `packaging\output\AutoSyncTallySyncSetup-<version>.exe`

Bump `VERSION`, push a `v*` tag, and let the release workflow publish both Setup EXEs. **Check for updates** picks the installer for the current product.

## App + tray

- Main window: home summary + last sync; Connection / Settings / Help menus
- Close / Hide to tray: keeps syncing in the background
- Tray: Open window · Open sync log · Quit
- Full Quit: File → Quit or tray → Quit

## Docs

- [Pluschwood payload contract](docs/PLUSCHWOOD_PAYLOAD_CONTRACT.md)
