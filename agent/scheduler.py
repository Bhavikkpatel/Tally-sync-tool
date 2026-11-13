from __future__ import annotations

import threading
import time
from typing import Callable


class IntervalScheduler:
    """Simple interval runner that keeps backlog until a successful attempt."""

    def __init__(self, interval_hours: int, tick: Callable[[], None], poll_seconds: int = 30):
        self.interval_hours = interval_hours
        self.tick = tick
        self.poll_seconds = poll_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_success = 0.0
        self._lock = threading.Lock()

    def set_interval_hours(self, hours: int) -> None:
        self.interval_hours = max(1, int(hours))

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="tally-sync-scheduler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def run_now(self) -> None:
        threading.Thread(target=self._safe_tick, name="tally-sync-manual", daemon=True).start()

    def _loop(self) -> None:
        while not self._stop.is_set():
            due = (time.time() - self._last_success) >= self.interval_hours * 3600
            if due or self._last_success == 0:
                self._safe_tick()
            self._stop.wait(self.poll_seconds)

    def _safe_tick(self) -> None:
        with self._lock:
            try:
                self.tick()
                self._last_success = time.time()
            except Exception:
                # Keep backlog; next poll retries.
                pass
