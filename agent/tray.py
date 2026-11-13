from __future__ import annotations

import os
import subprocess
import threading
from typing import Callable

from PIL import Image, ImageDraw

from agent import sync_log
from agent.version import APP_NAME

WIN_TIP_MAX = 128


def _clip(text: str, limit: int = WIN_TIP_MAX) -> str:
    text = (text or "").replace("\n", " ").strip()
    if len(text) <= limit:
        return text
    if limit <= 1:
        return text[:limit]
    return text[: limit - 1].rstrip() + "…"


def open_sync_log() -> None:
    path = sync_log.log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("", encoding="utf-8")
    try:
        os.startfile(str(path))  # type: ignore[attr-defined]
    except AttributeError:
        subprocess.Popen(["xdg-open", str(path)])


def make_icon(connected: bool = False) -> Image.Image:
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    color = (22, 163, 74, 255) if connected else (234, 88, 12, 255)
    draw.ellipse((8, 8, 56, 56), fill=color)
    draw.rectangle((20, 28, 44, 36), fill=(255, 255, 255, 255))
    return image


def run_tray(
    *,
    get_status: Callable[[], str],
    on_open_ui: Callable[[], None],
    on_quit: Callable[[], None],
    stop_event: threading.Event | None = None,
) -> None:
    """Background tray companion for the main window app."""
    import pystray

    stop = stop_event or threading.Event()

    def spawn(action: Callable[[], None]):
        return lambda icon, item: threading.Thread(target=action, daemon=True).start()

    def menu_status(_item=None) -> str:
        return _clip(get_status(), 96)

    menu = pystray.Menu(
        pystray.MenuItem(menu_status, None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Open window", spawn(on_open_ui), default=True),
        pystray.MenuItem("Open sync log", spawn(open_sync_log)),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(
            "Quit",
            lambda icon, item: (stop.set(), on_quit(), icon.stop()),
        ),
    )
    icon = pystray.Icon(APP_NAME.replace(" ", ""), make_icon(False), _clip(APP_NAME), menu)

    def refresh_loop() -> None:
        while not stop.wait(10):
            try:
                text = get_status()
                icon.title = _clip(f"{APP_NAME} — {text}", WIN_TIP_MAX)
                connected = any(token in text.lower() for token in ("paired", "synced", "ok", "ready", "✓"))
                icon.icon = make_icon(connected)
                icon.update_menu()
            except Exception:
                pass

    threading.Thread(target=refresh_loop, daemon=True).start()
    try:
        icon.run()
    finally:
        stop.set()
