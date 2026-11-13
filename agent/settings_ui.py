from __future__ import annotations

import threading
import webbrowser
from typing import Any, Callable

from agent.version import APP_NAME, GITHUB_REPO_URL, GITHUB_RELEASES_URL, __version__


Progress = Callable[[str], None]


class SettingsController:
    """Callbacks the settings window uses to talk to SyncApp without circular imports."""

    def __init__(
        self,
        *,
        get_status: Callable[[], str],
        get_detail: Callable[[], dict[str, Any]],
        save_settings: Callable[[dict[str, Any]], None],
        on_sign_in: Callable[[], None],
        on_pair: Callable[[], None],
        on_import: Callable[[], None],
        on_sync_now: Callable[[], None],
        on_mapping: Callable[[], None],
        on_open_log: Callable[[], None],
        on_check_update: Callable[[], dict[str, Any]],
    ):
        self.get_status = get_status
        self.get_detail = get_detail
        self.save_settings = save_settings
        self.on_sign_in = on_sign_in
        self.on_pair = on_pair
        self.on_import = on_import
        self.on_sync_now = on_sync_now
        self.on_mapping = on_mapping
        self.on_open_log = on_open_log
        self.on_check_update = on_check_update


_window_lock = threading.Lock()
_active_root = None


def open_settings(controller: SettingsController) -> None:
    """Open (or focus) the settings window on the main/UI thread-safe path."""
    global _active_root
    with _window_lock:
        if _active_root is not None:
            try:
                _active_root.lift()
                _active_root.focus_force()
                return
            except Exception:
                _active_root = None

    def runner() -> None:
        global _active_root
        try:
            import tkinter as tk
            from tkinter import messagebox, ttk
        except ModuleNotFoundError:
            print("tkinter is required for the settings UI", flush=True)
            return

        root = tk.Tk()
        _active_root = root
        root.title(f"{APP_NAME} — Settings")
        root.geometry("720x560")
        root.minsize(640, 480)

        style = ttk.Style(root)
        if "vista" in style.theme_names():
            style.theme_use("vista")

        outer = ttk.Frame(root, padding=16)
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer)
        header.pack(fill="x")
        ttk.Label(header, text=APP_NAME, font=("Segoe UI", 16, "bold")).pack(side="left")
        version_var = tk.StringVar(value=f"v{__version__}")
        ttk.Label(header, textvariable=version_var, foreground="#555").pack(side="right")

        status_frame = ttk.LabelFrame(outer, text="Status", padding=12)
        status_frame.pack(fill="x", pady=(12, 8))
        status_var = tk.StringVar(value="Loading…")
        detail_var = tk.StringVar(value="")
        ttk.Label(status_frame, textvariable=status_var, wraplength=660, justify="left").pack(anchor="w")
        ttk.Label(status_frame, textvariable=detail_var, wraplength=660, justify="left", foreground="#444").pack(
            anchor="w", pady=(6, 0)
        )

        settings_frame = ttk.LabelFrame(outer, text="Configuration", padding=12)
        settings_frame.pack(fill="x", pady=8)

        tally_url = tk.StringVar()
        from_date = tk.StringVar()
        to_date = tk.StringVar()
        interval = tk.StringVar(value="6")

        def row(parent, label: str, variable: tk.StringVar, r: int, width: int = 48) -> None:
            ttk.Label(parent, text=label).grid(row=r, column=0, sticky="w", pady=4, padx=(0, 8))
            ttk.Entry(parent, textvariable=variable, width=width).grid(row=r, column=1, sticky="ew", pady=4)

        settings_frame.columnconfigure(1, weight=1)
        row(settings_frame, "Tally HTTP URL", tally_url, 0)
        row(settings_frame, "Import from date (YYYY-MM-DD)", from_date, 1)
        row(settings_frame, "Import to date (YYYY-MM-DD)", to_date, 2)
        ttk.Label(settings_frame, text="Outbound interval (hours)").grid(row=3, column=0, sticky="w", pady=4)
        ttk.Combobox(settings_frame, textvariable=interval, values=("3", "6"), width=8, state="readonly").grid(
            row=3, column=1, sticky="w", pady=4
        )

        actions = ttk.LabelFrame(outer, text="Actions", padding=12)
        actions.pack(fill="x", pady=8)

        update_var = tk.StringVar(value="")
        ttk.Label(actions, textvariable=update_var, wraplength=660, foreground="#0b57d0").pack(anchor="w", pady=(0, 8))

        buttons = ttk.Frame(actions)
        buttons.pack(fill="x")

        def spawn(fn: Callable[[], None], label: str) -> None:
            def wrapped() -> None:
                update_var.set(f"Running {label}…")

                def work() -> None:
                    try:
                        fn()
                        root.after(0, lambda: (refresh(), update_var.set(f"{label} finished")))
                    except Exception as exc:
                        root.after(0, lambda: (update_var.set(str(exc)), messagebox.showerror(APP_NAME, str(exc))))

                threading.Thread(target=work, daemon=True).start()

            return wrapped

        def refresh() -> None:
            try:
                status_var.set(controller.get_status())
                detail = controller.get_detail()
                lines = [
                    f"Tally: {detail.get('tally') or '—'}",
                    f"Destinations: {detail.get('destinations') or 'none'}",
                    f"Mapping: {detail.get('mapping') or '—'}",
                    f"Data folder: {detail.get('data_dir') or '—'}",
                ]
                detail_var.set("\n".join(lines))
                tally_url.set(str(detail.get("tally_url") or ""))
                from_date.set(str(detail.get("import_from_date") or ""))
                to_date.set(str(detail.get("import_to_date") or ""))
                interval.set(str(detail.get("interval_hours") or "6"))
                version_var.set(f"v{detail.get('version') or __version__}")
            except Exception as exc:
                status_var.set(f"Status error: {exc}")

        def save() -> None:
            try:
                controller.save_settings(
                    {
                        "tally_url": tally_url.get().strip(),
                        "import_from_date": from_date.get().strip() or None,
                        "import_to_date": to_date.get().strip() or None,
                        "interval_hours": int(interval.get() or 6),
                    }
                )
                refresh()
                messagebox.showinfo(APP_NAME, "Settings saved")
            except Exception as exc:
                messagebox.showerror(APP_NAME, str(exc))

        def check_update() -> None:
            update_var.set("Checking GitHub for updates…")

            def work() -> None:
                try:
                    info = controller.on_check_update()
                except Exception as exc:
                    root.after(0, lambda: (update_var.set(str(exc)), messagebox.showerror(APP_NAME, str(exc))))
                    return

                def done() -> None:
                    update_var.set(
                        f"{info.get('message')} (current v{info.get('current_version')}, latest v{info.get('latest_version')})"
                    )
                    if info.get("update_available"):
                        if messagebox.askyesno(
                            APP_NAME,
                            f"Version {info.get('latest_version')} is available.\n\nOpen the release page to download?",
                        ):
                            webbrowser.open(info.get("release_url") or GITHUB_RELEASES_URL)
                    else:
                        messagebox.showinfo(APP_NAME, info.get("message") or "No update available")

                root.after(0, done)

            threading.Thread(target=work, daemon=True).start()

        grid = [
            ("Sign in to connect", spawn(controller.on_sign_in, "Sign in")),
            ("Enter pairing code", spawn(controller.on_pair, "Pairing")),
            ("Run full import", spawn(controller.on_import, "Import")),
            ("Sync now", spawn(controller.on_sync_now, "Sync")),
            ("Ledger mapping", spawn(controller.on_mapping, "Mapping")),
            ("Open sync log", spawn(controller.on_open_log, "Open log")),
            ("Save settings", save),
            ("Check for updates", check_update),
            ("Refresh status", refresh),
            ("GitHub repo", lambda: webbrowser.open(GITHUB_REPO_URL)),
        ]
        for index, (label, command) in enumerate(grid):
            ttk.Button(buttons, text=label, command=command).grid(
                row=index // 3, column=index % 3, sticky="ew", padx=4, pady=4
            )
        for col in range(3):
            buttons.columnconfigure(col, weight=1)

        footer = ttk.Frame(outer)
        footer.pack(fill="x", pady=(12, 0))
        ttk.Label(
            footer,
            text="Tray icon stays available while this window is open. Quit from the tray menu.",
            foreground="#666",
        ).pack(side="left")

        def on_close() -> None:
            global _active_root
            _active_root = None
            root.destroy()

        root.protocol("WM_DELETE_WINDOW", on_close)
        refresh()
        root.after(15000, lambda: _auto_refresh(root, refresh))
        root.mainloop()
        _active_root = None

    threading.Thread(target=runner, daemon=True).start()


def _auto_refresh(root, refresh: Callable[[], None]) -> None:
    try:
        if root.winfo_exists():
            refresh()
            root.after(15000, lambda: _auto_refresh(root, refresh))
    except Exception:
        pass
