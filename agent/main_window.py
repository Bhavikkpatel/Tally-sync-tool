from __future__ import annotations

import threading
import webbrowser
from dataclasses import dataclass
from typing import Any, Callable

from agent.version import APP_NAME, GITHUB_RELEASES_URL, GITHUB_REPO_URL, __version__


@dataclass
class AppController:
    get_status: Callable[[], str]
    get_detail: Callable[[], dict[str, Any]]
    save_settings: Callable[[dict[str, Any]], None]
    on_sign_in: Callable[[], None]
    on_pair: Callable[[], None]
    on_import: Callable[[], None]
    on_sync_now: Callable[[], None]
    on_mapping: Callable[[], None]
    on_open_log: Callable[[], None]
    on_check_update: Callable[[], dict[str, Any]]
    on_quit: Callable[[], None]


class MainWindow:
    """Primary Windows application window. Close hides to tray; Quit exits."""

    def __init__(self, controller: AppController):
        import tkinter as tk
        from tkinter import messagebox, ttk

        self.controller = controller
        self.tk = tk
        self.messagebox = messagebox
        self.root = tk.Tk()
        self.root.title(APP_NAME)
        self.root.geometry("900x640")
        self.root.minsize(780, 560)
        self.root.configure(bg="#f3f4f6")

        style = ttk.Style(self.root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("Title.TLabel", font=("Segoe UI Semibold", 18))
        style.configure("Sub.TLabel", font=("Segoe UI", 10), foreground="#4b5563")
        style.configure("Card.TLabelframe", padding=14)
        style.configure("Card.TLabelframe.Label", font=("Segoe UI Semibold", 10))
        style.configure("Accent.TButton", font=("Segoe UI", 10))
        style.configure("StatusOk.TLabel", foreground="#15803d", font=("Segoe UI Semibold", 11))
        style.configure("StatusBad.TLabel", foreground="#b91c1c", font=("Segoe UI Semibold", 11))

        self.status_var = tk.StringVar(value="Starting…")
        self.tally_var = tk.StringVar(value="—")
        self.dest_var = tk.StringVar(value="—")
        self.mapping_var = tk.StringVar(value="—")
        self.activity_var = tk.StringVar(value="")
        self.version_var = tk.StringVar(value=f"Version {__version__}")
        self.update_var = tk.StringVar(value="")
        self.tally_url = tk.StringVar()
        self.from_date = tk.StringVar()
        self.to_date = tk.StringVar()
        self.interval = tk.StringVar(value="6")
        self.data_dir_var = tk.StringVar(value="")
        self._hidden = False

        self._build_menu()
        self._build_layout(ttk)
        self.root.protocol("WM_DELETE_WINDOW", self.hide_to_tray)
        self.root.bind("<Map>", lambda _e: setattr(self, "_hidden", False))
        self.refresh()
        self.root.after(5000, self._tick)

    def _build_menu(self) -> None:
        menubar = self.tk.Menu(self.root)
        file_menu = self.tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Hide to tray", command=self.hide_to_tray)
        file_menu.add_separator()
        file_menu.add_command(label="Quit", command=self.quit_app)
        menubar.add_cascade(label="File", menu=file_menu)

        connect_menu = self.tk.Menu(menubar, tearoff=0)
        connect_menu.add_command(label="Sign in to connect…", command=lambda: self._run(self.controller.on_sign_in, "Sign in"))
        connect_menu.add_command(label="Enter pairing code…", command=lambda: self._run(self.controller.on_pair, "Pairing"))
        connect_menu.add_separator()
        connect_menu.add_command(label="Run full import", command=lambda: self._run(self.controller.on_import, "Import"))
        connect_menu.add_command(label="Sync now", command=lambda: self._run(self.controller.on_sync_now, "Sync"))
        connect_menu.add_command(label="Ledger mapping…", command=lambda: self._run(self.controller.on_mapping, "Mapping"))
        menubar.add_cascade(label="Connection", menu=connect_menu)

        tools_menu = self.tk.Menu(menubar, tearoff=0)
        tools_menu.add_command(label="Open sync log", command=lambda: self._run(self.controller.on_open_log, "Open log"))
        tools_menu.add_command(label="Check for updates…", command=self.check_update)
        tools_menu.add_command(label="Refresh status", command=self.refresh)
        menubar.add_cascade(label="Tools", menu=tools_menu)

        help_menu = self.tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="GitHub repository", command=lambda: webbrowser.open(GITHUB_REPO_URL))
        help_menu.add_command(label="Releases", command=lambda: webbrowser.open(GITHUB_RELEASES_URL))
        help_menu.add_command(label="About", command=self._about)
        menubar.add_cascade(label="Help", menu=help_menu)
        self.root.config(menu=menubar)

    def _build_layout(self, ttk) -> None:
        shell = ttk.Frame(self.root, padding=18)
        shell.pack(fill="both", expand=True)

        header = ttk.Frame(shell)
        header.pack(fill="x")
        ttk.Label(header, text=APP_NAME, style="Title.TLabel").pack(side="left")
        ttk.Label(header, textvariable=self.version_var, style="Sub.TLabel").pack(side="right", padx=(8, 0))
        ttk.Button(header, text="Hide to tray", command=self.hide_to_tray).pack(side="right")

        ttk.Label(
            shell,
            text="Sync the open Tally company with Pluschwood or AutoSync. Closing this window keeps the app in the tray.",
            style="Sub.TLabel",
            wraplength=820,
        ).pack(anchor="w", pady=(4, 14))

        # Dashboard cards
        dash = ttk.Frame(shell)
        dash.pack(fill="x")
        for col in range(3):
            dash.columnconfigure(col, weight=1, uniform="cards")

        card1 = ttk.LabelFrame(dash, text="Tally", style="Card.TLabelframe")
        card1.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self.tally_status_label = ttk.Label(card1, textvariable=self.tally_var, style="StatusOk.TLabel")
        self.tally_status_label.pack(anchor="w")
        ttk.Label(card1, text="Open company over HTTP gateway", style="Sub.TLabel").pack(anchor="w", pady=(4, 0))

        card2 = ttk.LabelFrame(dash, text="Destinations", style="Card.TLabelframe")
        card2.grid(row=0, column=1, sticky="nsew", padx=4)
        ttk.Label(card2, textvariable=self.dest_var, style="StatusOk.TLabel").pack(anchor="w")
        ttk.Label(card2, textvariable=self.mapping_var, style="Sub.TLabel").pack(anchor="w", pady=(4, 0))

        card3 = ttk.LabelFrame(dash, text="Activity", style="Card.TLabelframe")
        card3.grid(row=0, column=2, sticky="nsew", padx=(8, 0))
        ttk.Label(card3, textvariable=self.status_var, wraplength=240, justify="left").pack(anchor="w")
        ttk.Label(card3, textvariable=self.activity_var, style="Sub.TLabel", wraplength=240, justify="left").pack(
            anchor="w", pady=(4, 0)
        )

        # Connection actions
        actions = ttk.LabelFrame(shell, text="Connection", style="Card.TLabelframe")
        actions.pack(fill="x", pady=(14, 0))
        row = ttk.Frame(actions)
        row.pack(fill="x")
        for i, (label, cmd) in enumerate(
            [
                ("Sign in to connect", lambda: self._run(self.controller.on_sign_in, "Sign in")),
                ("Enter pairing code", lambda: self._run(self.controller.on_pair, "Pairing")),
                ("Run full import", lambda: self._run(self.controller.on_import, "Import")),
                ("Sync now", lambda: self._run(self.controller.on_sync_now, "Sync")),
                ("Ledger mapping", lambda: self._run(self.controller.on_mapping, "Mapping")),
                ("Open sync log", lambda: self._run(self.controller.on_open_log, "Open log")),
            ]
        ):
            ttk.Button(row, text=label, command=cmd, style="Accent.TButton").grid(
                row=0, column=i, sticky="ew", padx=3, pady=2
            )
            row.columnconfigure(i, weight=1)

        # Settings
        settings = ttk.LabelFrame(shell, text="Settings", style="Card.TLabelframe")
        settings.pack(fill="both", expand=True, pady=(14, 0))
        settings.columnconfigure(1, weight=1)

        def field(r: int, label: str, var, widget="entry") -> None:
            ttk.Label(settings, text=label).grid(row=r, column=0, sticky="w", pady=5, padx=(0, 10))
            if widget == "combo":
                ttk.Combobox(settings, textvariable=var, values=("3", "6"), width=10, state="readonly").grid(
                    row=r, column=1, sticky="w", pady=5
                )
            else:
                ttk.Entry(settings, textvariable=var).grid(row=r, column=1, sticky="ew", pady=5)

        field(0, "Tally HTTP URL", self.tally_url)
        field(1, "Import from date (YYYY-MM-DD)", self.from_date)
        field(2, "Import to date (YYYY-MM-DD)", self.to_date)
        field(3, "Outbound interval (hours)", self.interval, widget="combo")
        ttk.Label(settings, text="Data folder").grid(row=4, column=0, sticky="w", pady=5, padx=(0, 10))
        ttk.Label(settings, textvariable=self.data_dir_var, style="Sub.TLabel").grid(row=4, column=1, sticky="w", pady=5)

        bottom = ttk.Frame(settings)
        bottom.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        ttk.Button(bottom, text="Save settings", command=self.save).pack(side="left")
        ttk.Button(bottom, text="Check for updates", command=self.check_update).pack(side="left", padx=8)
        ttk.Button(bottom, text="Refresh", command=self.refresh).pack(side="left")
        ttk.Label(bottom, textvariable=self.update_var, style="Sub.TLabel").pack(side="left", padx=12)

    def _about(self) -> None:
        self.messagebox.showinfo(
            APP_NAME,
            f"{APP_NAME}\nVersion {__version__}\n\nGitHub: {GITHUB_REPO_URL}\n\n"
            "Keep Tally open with a company loaded. Use Sign in to connect to register this PC.",
        )

    def hide_to_tray(self) -> None:
        self._hidden = True
        self.root.withdraw()
        self.update_var.set("Running in the system tray. Use Open window to restore.")

    def show(self) -> None:
        self._hidden = False
        try:
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
            self.refresh()
        except Exception:
            pass

    def quit_app(self) -> None:
        try:
            self.controller.on_quit()
        finally:
            try:
                self.root.quit()
            except Exception:
                pass
            try:
                self.root.destroy()
            except Exception:
                pass

    def _run(self, fn: Callable[[], None], label: str) -> None:
        self.update_var.set(f"Running {label}…")

        def work() -> None:
            try:
                fn()
                self.root.after(0, lambda: (self.refresh(), self.update_var.set(f"{label} finished")))
            except Exception as exc:
                self.root.after(0, lambda: (self.update_var.set(str(exc)), self.messagebox.showerror(APP_NAME, str(exc))))

        threading.Thread(target=work, daemon=True).start()

    def refresh(self) -> None:
        try:
            self.status_var.set(self.controller.get_status())
            detail = self.controller.get_detail()
            tally_ok = bool(detail.get("tally_ok"))
            self.tally_var.set(str(detail.get("tally") or "—"))
            self.tally_status_label.configure(style="StatusOk.TLabel" if tally_ok else "StatusBad.TLabel")
            self.dest_var.set(str(detail.get("destinations") or "none"))
            self.mapping_var.set(f"Mapping: {detail.get('mapping') or '—'}")
            self.activity_var.set(str(detail.get("last_message") or ""))
            self.tally_url.set(str(detail.get("tally_url") or ""))
            self.from_date.set(str(detail.get("import_from_date") or ""))
            self.to_date.set(str(detail.get("import_to_date") or ""))
            self.interval.set(str(detail.get("interval_hours") or "6"))
            self.data_dir_var.set(str(detail.get("data_dir") or ""))
            self.version_var.set(f"Version {detail.get('version') or __version__}")
        except Exception as exc:
            self.status_var.set(f"Status error: {exc}")

    def save(self) -> None:
        try:
            self.controller.save_settings(
                {
                    "tally_url": self.tally_url.get().strip(),
                    "import_from_date": self.from_date.get().strip() or None,
                    "import_to_date": self.to_date.get().strip() or None,
                    "interval_hours": int(self.interval.get() or 6),
                }
            )
            self.refresh()
            self.messagebox.showinfo(APP_NAME, "Settings saved")
        except Exception as exc:
            self.messagebox.showerror(APP_NAME, str(exc))

    def check_update(self) -> None:
        self.update_var.set("Checking GitHub for updates…")

        def work() -> None:
            try:
                info = self.controller.on_check_update()
            except Exception as exc:
                self.root.after(0, lambda: (self.update_var.set(str(exc)), self.messagebox.showerror(APP_NAME, str(exc))))
                return

            def done() -> None:
                self.update_var.set(
                    f"{info.get('message')} (current v{info.get('current_version')}, latest v{info.get('latest_version')})"
                )
                if info.get("update_available"):
                    if self.messagebox.askyesno(
                        APP_NAME,
                        f"Version {info.get('latest_version')} is available.\n\nOpen the release page to download?",
                    ):
                        webbrowser.open(info.get("release_url") or GITHUB_RELEASES_URL)
                else:
                    self.messagebox.showinfo(APP_NAME, info.get("message") or "No update available")

            self.root.after(0, done)

        threading.Thread(target=work, daemon=True).start()

    def _tick(self) -> None:
        if not self._hidden:
            self.refresh()
        try:
            self.root.after(5000, self._tick)
        except Exception:
            pass

    def run(self) -> None:
        self.root.mainloop()


# Back-compat alias used by older imports
SettingsController = AppController


def open_settings(controller: AppController) -> None:
    """Focus an existing main window if present; otherwise no-op (window owns the process)."""
    # Kept for tray "Open window" — SyncApp holds the MainWindow instance.
    raise RuntimeError("Use MainWindow.show() from SyncApp")
