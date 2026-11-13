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
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(root / "packaging" / "tally_sync.ico") if (root / "packaging" / "tally_sync.ico").exists() else None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=exe_name,
)
