from __future__ import annotations

import sys
from pathlib import Path

from agent.product import APP_ID, APP_NAME, DESTINATION_BASE_URL, DESTINATION_LABEL


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

__all__ = [
    "APP_NAME",
    "APP_ID",
    "DESTINATION_LABEL",
    "DESTINATION_BASE_URL",
    "__version__",
]
