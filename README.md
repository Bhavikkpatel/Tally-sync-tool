# Tally Sync

Windows tray application that syncs an open TallyPrime company with **Pluschwood Console** or **AutoSync**.

- System tray status + **Open settings** UI for configuration
- Browser sign-in to register the tool with your org (pairing codes as fallback)
- Rich Pluschwood import payload (`pluschwood_tally_v2`)
- Check for updates from [GitHub Releases](https://github.com/Bhavikkpatel/Tally-sync-tool/releases)

## Requirements

- Windows 10/11
- TallyPrime open with a company loaded and HTTP on `http://127.0.0.1:9000`
- For development: Python 3.11+

## Install (end users)

1. Download `TallySyncSetup-*.exe` from [Releases](https://github.com/Bhavikkpatel/Tally-sync-tool/releases).
2. Run the installer (optional: start at Windows sign-in).
3. Launch **Tally Sync** — settings open and a tray icon appears.
4. **Sign in to connect…** (or Enter pairing code), then run import.

State lives under `%LOCALAPPDATA%\AutoSyncTallySync\` (tokens are DPAPI-protected). Sync counts go to `sync.log`.

## Develop

```powershell
cd "M:\Projects\Sync tool"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m agent
```

Optional date range:

```powershell
$env:TALLY_IMPORT_FROM_DATE="2024-04-01"
$env:TALLY_IMPORT_TO_DATE="2026-03-31"
```

Tests:

```powershell
python -m unittest discover -s tests -v
```

## Build Windows installer

1. Install [Inno Setup 6](https://jrsoftware.org/isinfo.php) (for the Setup EXE).
2. Run:

```powershell
python packaging\make_icon.py
powershell -ExecutionPolicy Bypass -File packaging\build.ps1
```

Outputs:

- `dist\TallySync\` — portable app folder
- `packaging\output\TallySyncSetup-<version>.exe` — installer (when ISCC is available)

Bump `VERSION` before tagging a release. Publish the Setup EXE as a GitHub Release asset so **Check for updates** can find it.

## Tray menu

- Open settings…
- Sign in to connect… / Enter pairing code…
- Run initial import / Sync now / Ledger mapping…
- Open sync log / Check for updates…
- Quit

## Docs

- [Pluschwood payload contract](docs/PLUSCHWOOD_PAYLOAD_CONTRACT.md)
