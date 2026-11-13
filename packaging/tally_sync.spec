# -*- mode: python ; coding: utf-8 -*-
import os
from pathlib import Path

# SPECPATH is the folder that contains this .spec file (packaging/).
root = Path(SPECPATH).resolve().parent
block_cipher = None

product = (os.environ.get("TALLY_SYNC_PRODUCT") or "pluschwood").strip().lower()
exe_name = (os.environ.get("TALLY_SYNC_EXE_NAME") or "").strip()
if not exe_name:
    exe_name = "PluschwoodTallySync" if product == "pluschwood" else "AutoSyncTallySync"

product_file = root / "PRODUCT"
product_file.write_text(product + "\n", encoding="utf-8")

version_info = root / "packaging" / f"version_info_{product}.txt"
version_arg = str(version_info) if version_info.exists() else None
icon_path = root / "packaging" / "tally_sync.ico"
icon_arg = str(icon_path) if icon_path.exists() else None

a = Analysis(
    [str(root / "packaging" / "run_app.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[
        (str(root / "VERSION"), "."),
        (str(product_file), "."),
    ],
    hiddenimports=["pystray._win32", "webview", "bottle", "clr_loader"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=exe_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # UPX packing triggers many Defender Trojan heuristics — never enable for release builds.
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_arg,
    version=version_arg,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=exe_name,
)
