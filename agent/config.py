from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def default_data_dir() -> Path:
    from agent.product import DATA_DIR_NAME

    root = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    path = Path(root) / DATA_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def _default_product_base_url() -> str:
    from agent.product import DESTINATION_BASE_URL, PRODUCT_ID

    if PRODUCT_ID == "autosync" and os.environ.get("AUTOSYNC_BASE_URL"):
        return os.environ["AUTOSYNC_BASE_URL"].rstrip("/")
    if PRODUCT_ID == "pluschwood" and os.environ.get("PLUSCHWOOD_BASE_URL"):
        return os.environ["PLUSCHWOOD_BASE_URL"].rstrip("/")
    return DESTINATION_BASE_URL


@dataclass
class AgentConfig:
    autosync_base_url: str = field(default_factory=_default_product_base_url)
    tally_url: str = field(
        default_factory=lambda: os.environ.get("TALLY_URL", "http://127.0.0.1:9000").rstrip("/")
    )
    data_dir: Path = field(default_factory=default_data_dir)
    import_page_size: int = 200
    default_interval_hours: int = 6
    poll_seconds: int = 30
    import_from_date: str | None = field(default_factory=lambda: os.environ.get("TALLY_IMPORT_FROM_DATE") or None)
    import_to_date: str | None = field(default_factory=lambda: os.environ.get("TALLY_IMPORT_TO_DATE") or None)

    @property
    def db_path(self) -> Path:
        return self.data_dir / "agent.sqlite3"

    @property
    def token_path(self) -> Path:
        return self.data_dir / "installation.token"
