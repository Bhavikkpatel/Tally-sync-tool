from __future__ import annotations

import os
import sys
from pathlib import Path


PRODUCTS = {
    "pluschwood": {
        "id": "pluschwood",
        "app_name": "Pluschwood Tally Sync",
        "app_id": "PluschwoodTallySync",
        "exe_name": "PluschwoodTallySync",
        "label": "Pluschwood Console",
        "base_url": "https://console.pluschwood.com",
        "data_dir_name": "PluschwoodTallySync",
    },
    "autosync": {
        "id": "autosync",
        "app_name": "AutoSync Tally Sync",
        "app_id": "AutoSyncTallySync",
        "exe_name": "AutoSyncTallySync",
        "label": "AutoSync",
        "base_url": "https://autosync.app",
        "data_dir_name": "AutoSyncTallySync",
    },
}


def _read_product_file() -> str | None:
    candidates: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "PRODUCT")
    candidates.append(Path(__file__).resolve().parents[1] / "PRODUCT")
    candidates.append(Path.cwd() / "PRODUCT")
    for path in candidates:
        try:
            if path.is_file():
                text = path.read_text(encoding="utf-8").strip().lower()
                if text:
                    return text
        except OSError:
            continue
    return None


def resolve_product_id() -> str:
    raw = (os.environ.get("TALLY_SYNC_PRODUCT") or _read_product_file() or "pluschwood").strip().lower()
    if raw not in PRODUCTS:
        raise RuntimeError(f"Unknown product '{raw}'. Use: {', '.join(PRODUCTS)}")
    return raw


PRODUCT_ID = resolve_product_id()
PRODUCT = PRODUCTS[PRODUCT_ID]
APP_NAME = PRODUCT["app_name"]
APP_ID = PRODUCT["app_id"]
EXE_NAME = PRODUCT["exe_name"]
DESTINATION_ID = PRODUCT["id"]
DESTINATION_LABEL = PRODUCT["label"]
DESTINATION_BASE_URL = PRODUCT["base_url"]
DATA_DIR_NAME = PRODUCT["data_dir_name"]
