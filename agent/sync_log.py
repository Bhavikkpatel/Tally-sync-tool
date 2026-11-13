from __future__ import annotations

import sys
import threading
from collections import deque
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from agent.config import default_data_dir

IST = timezone(timedelta(hours=5, minutes=30), name="IST")
_LOCK = threading.Lock()
_RECENT: deque[str] = deque(maxlen=500)


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


def _remember(line: str) -> None:
    with _LOCK:
        _RECENT.append(line)


def recent_lines(limit: int = 200, *, data_dir: Path | None = None) -> list[str]:
    """Return the newest log lines for the in-app live viewer."""
    limit = max(1, min(int(limit or 200), 500))
    with _LOCK:
        buffered = list(_RECENT)
    if len(buffered) >= limit:
        return buffered[-limit:]
    path = log_path(data_dir)
    file_lines: list[str] = []
    try:
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace")
            file_lines = [line.rstrip("\r\n") for line in text.splitlines() if line.strip()]
    except OSError:
        file_lines = []
    if not file_lines:
        return buffered[-limit:]
    # Prefer file history, then append any newer buffered lines not already present.
    merged = file_lines[-limit:]
    if buffered:
        tail = merged[-1] if merged else ""
        extras = []
        for line in buffered:
            if not merged or line != tail:
                extras.append(line)
            if line == tail:
                extras = []
        if extras:
            merged.extend(extras)
    return merged[-limit:]


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
    _remember(line)
    try:
        print(line, flush=True)
    except OSError:
        pass
    return line
