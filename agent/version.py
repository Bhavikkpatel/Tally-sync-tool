from __future__ import annotations

import sys
from pathlib import Path

APP_NAME = "Tally Sync"
APP_ID = "TallySync"
GITHUB_REPO = "Bhavikkpatel/Tally-sync-tool"
GITHUB_RELEASES_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
GITHUB_REPO_URL = f"https://github.com/{GITHUB_REPO}"
GITHUB_RELEASES_URL = f"{GITHUB_REPO_URL}/releases"


def _read_version_file() -> str:
    candidates: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "VERSION")
    candidates.append(Path(__file__).resolve().parents[1] / "VERSION")
    candidates.append(Path.cwd() / "VERSION")
    for path in candidates:
        try:
            if path.is_file():
                text = path.read_text(encoding="utf-8").strip()
                if text:
                    return text.lstrip("vV")
        except OSError:
            continue
    return "0.0.0"


__version__ = _read_version_file()
