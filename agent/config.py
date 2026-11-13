from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def default_data_dir() -> Path:
    root = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    path = Path(root) / "AutoSyncTallySync"
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class AgentConfig:
    autosync_base_url: str = field(
        default_factory=lambda: os.environ.get("AUTOSYNC_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    )
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
