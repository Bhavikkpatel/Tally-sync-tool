from __future__ import annotations

import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from agent.config import default_data_dir

IST = timezone(timedelta(hours=5, minutes=30), name="IST")


def ist_now() -> datetime:
    return datetime.now(IST)


def ist_stamp() -> str:
    return ist_now().strftime("%Y-%m-%d %H:%M:%S IST")


def log_path(data_dir: Path | None = None) -> Path:
    root = data_dir or default_data_dir()
    root.mkdir(parents=True, exist_ok=True)
    return root / "sync.log"


def ensure_stdio() -> None:
    """Best-effort line buffering so tray threads flush progress immediately."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(line_buffering=True, write_through=True)  # type: ignore[attr-defined]
        except Exception:
            pass


def format_counts(counts: dict[str, Any] | None) -> str:
    if not counts:
        return "count=0"
    parts = []
    for key, value in counts.items():
        if value is None:
            continue
        parts.append(f"{key}={value}")
    return " ".join(parts) if parts else "count=0"


def log_event(
    message: str,
    *,
    data_dir: Path | None = None,
    counts: dict[str, Any] | None = None,
) -> str:
    """Append a single sync line (counts only — never record payloads) and print it."""
    stamp = ist_stamp()
    count_bit = f" | {format_counts(counts)}" if counts is not None else ""
    line = f"[{stamp}] {message}{count_bit}"
    path = log_path(data_dir)
    try:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except OSError:
        pass
    try:
        print(line, flush=True)
    except OSError:
        pass
    return line
