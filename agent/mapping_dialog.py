from __future__ import annotations

import subprocess
from typing import Callable


FIELDS = (
    ("sales_voucher_type", "Sales voucher type", "Sales"),
    ("sales_ledger", "Sales ledger", "Sales"),
    ("cgst_ledger", "CGST ledger", "CGST"),
    ("sgst_ledger", "SGST ledger", "SGST"),
    ("igst_ledger", "IGST ledger", "IGST"),
    ("round_off_ledger", "Round-off ledger", "Round Off"),
    ("receipt_ledger", "Receipt bank/cash ledger", "Cash"),
)


def ask_ledger_mapping(existing: dict | None = None, on_save: Callable[[dict], None] | None = None) -> dict | None:
    existing = existing or {}
    result = _tk_ledger_mapping(existing)
    if result is None and _tkinter_available():
        return None
    if result is None:
        result = _windows_ledger_mapping(existing) or _console_ledger_mapping(existing)
    if result and on_save:
        on_save(result)
    return result


def ask_pairing_code() -> str | None:
    result = ask_destination_pair()
    return result["code"] if result else None


def ask_destination_pair(presets: list[dict] | None = None) -> dict | None:
    """Return {label, base_url, code}. The Base URL field is always the value used to pair."""
    presets = presets or []
    for asker in (_tk_destination_pair, _windows_destination_pair, _console_destination_pair):
        try:
            result = asker(presets)
        except Exception:
            result = None
        if result is None:
            continue
        if not result:
            return None
        base_url = (result.get("base_url") or "").strip()
        code = (result.get("code") or "").strip()
        if not base_url or not code:
            return None
        print(f"Pairing with base URL: {base_url}", flush=True)
        return {
            "label": (result.get("label") or "Custom").strip() or "Custom",
            "base_url": base_url,
            "code": code,
        }
    return None


def ask_destination_login(presets: list[dict] | None = None) -> dict | None:
    """Return {label, base_url} for browser login registration (no pairing code)."""
    presets = presets or []
    for asker in (_tk_destination_login, _windows_destination_login, _console_destination_login):
        try:
            result = asker(presets)
        except Exception:
            result = None
        if result is None:
            continue
        if not result:
            return None
        base_url = (result.get("base_url") or "").strip()
        if not base_url:
            return None
        print(f"Browser login with base URL: {base_url}", flush=True)
        return {
            "label": (result.get("label") or "Custom").strip() or "Custom",
            "base_url": base_url,
        }
    return None


def _tkinter_available() -> bool:
    try:
        import tkinter  # noqa: F401

        return True
    except ModuleNotFoundError:
        return False


def _tk_ledger_mapping(existing: dict) -> dict | None:
    if not _tkinter_available():
        return None
    import tkinter as tk
    from tkinter import ttk

    result: dict | None = None
    cancelled = {"value": True}

    root = tk.Tk()
    root.title("Tally ledger mapping")
    root.resizable(False, False)

    frame = ttk.Frame(root, padding=16)
    frame.grid(row=0, column=0)
    entries: dict[str, tk.StringVar] = {}

    ttk.Label(
        frame,
        text="Choose the Tally ledger and voucher names used when AutoSync posts sales and receipts.",
        wraplength=420,
    ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))

    for index, (key, label, default) in enumerate(FIELDS, start=1):
        ttk.Label(frame, text=label).grid(row=index, column=0, sticky="w", pady=4)
        value = tk.StringVar(value=str(existing.get(key) or default))
        entries[key] = value
        ttk.Entry(frame, textvariable=value, width=36).grid(row=index, column=1, sticky="ew", pady=4)

    def save() -> None:
        nonlocal result
        mapping = {key: var.get().strip() for key, var in entries.items()}
        if not all(mapping.values()):
            return
        result = mapping
        cancelled["value"] = False
        root.destroy()

    def cancel() -> None:
        root.destroy()

    buttons = ttk.Frame(frame)
    buttons.grid(row=len(FIELDS) + 1, column=0, columnspan=2, sticky="e", pady=(16, 0))
    ttk.Button(buttons, text="Cancel", command=cancel).grid(row=0, column=0, padx=(0, 8))
    ttk.Button(buttons, text="Save", command=save).grid(row=0, column=1)

    root.protocol("WM_DELETE_WINDOW", cancel)
    root.attributes("-topmost", True)
    root.mainloop()
    if cancelled["value"]:
        return {}
    return result


def _tk_destination_pair(presets: list[dict]) -> dict | None:
    if not _tkinter_available():
        return None
    import tkinter as tk
    from tkinter import ttk

    result: dict[str, str] = {"cancelled": "1"}
    root = tk.Tk()
    root.title("Pair a destination")
    root.resizable(False, False)
    frame = ttk.Frame(root, padding=16)
    frame.grid(row=0, column=0)

    ttk.Label(
        frame,
        text="Pick a destination. The Base URL below is what the agent will call.",
        wraplength=460,
    ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))

    choices = [item["label"] for item in presets] + ["Custom URL"]
    choice = tk.StringVar(value=choices[0] if choices else "Custom URL")
    base_url = tk.StringVar(value=(presets[0]["base_url"] if presets else "https://console.pluschwood.com"))
    label_var = tk.StringVar(value=(presets[0]["label"] if presets else "Custom"))
    code = tk.StringVar()

    def apply_preset(*_args) -> None:
        selected = choice.get()
        for item in presets:
            if item["label"] == selected:
                base_url.set(item["base_url"])
                label_var.set(item["label"])
                return
        label_var.set("Custom")

    ttk.Label(frame, text="Destination").grid(row=1, column=0, sticky="w", pady=4)
    combo = ttk.Combobox(frame, textvariable=choice, values=choices, width=48, state="readonly")
    combo.grid(row=1, column=1, sticky="ew", pady=4)
    combo.bind("<<ComboboxSelected>>", apply_preset)

    ttk.Label(frame, text="Base URL").grid(row=2, column=0, sticky="w", pady=4)
    ttk.Entry(frame, textvariable=base_url, width=48).grid(row=2, column=1, sticky="ew", pady=4)

    ttk.Label(frame, text="Label").grid(row=3, column=0, sticky="w", pady=4)
    ttk.Entry(frame, textvariable=label_var, width=48).grid(row=3, column=1, sticky="ew", pady=4)

    ttk.Label(frame, text="Pairing code").grid(row=4, column=0, sticky="w", pady=4)
    ttk.Entry(frame, textvariable=code, width=48).grid(row=4, column=1, sticky="ew", pady=4)

    def save() -> None:
        url = base_url.get().strip()
        value = code.get().strip()
        if not url or not value:
            return
        result.update(
            {
                "label": label_var.get().strip() or "Custom",
                "base_url": url,
                "code": value,
                "cancelled": "0",
            }
        )
        root.destroy()

    def cancel() -> None:
        root.destroy()

    buttons = ttk.Frame(frame)
    buttons.grid(row=5, column=0, columnspan=2, sticky="e", pady=(16, 0))
    ttk.Button(buttons, text="Cancel", command=cancel).grid(row=0, column=0, padx=(0, 8))
    ttk.Button(buttons, text="Pair", command=save).grid(row=0, column=1)
    root.protocol("WM_DELETE_WINDOW", cancel)
    root.attributes("-topmost", True)
    root.mainloop()
    if result.get("cancelled") == "1":
        return {}
    return {"label": result["label"], "base_url": result["base_url"], "code": result["code"]}


def _windows_input(prompt: str, title: str, default: str = "") -> str | None:
    """Native Windows prompt that works from a tray background thread."""
    safe_prompt = prompt.replace("'", "''")
    safe_title = title.replace("'", "''")
    safe_default = default.replace("'", "''")
    script = (
        "Add-Type -AssemblyName Microsoft.VisualBasic; "
        f"[Microsoft.VisualBasic.Interaction]::InputBox('{safe_prompt}','{safe_title}','{safe_default}')"
    )
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def _windows_destination_pair(presets: list[dict]) -> dict | None:
    import sys

    if not sys.platform.startswith("win"):
        return None
    lines = ["Enter destination number:"]
    for index, item in enumerate(presets, start=1):
        lines.append(f"{index} = {item['label']} ({item['base_url']})")
    lines.append(f"{len(presets) + 1} = Custom URL")
    choice = _windows_input("\r\n".join(lines), "Pair destination", "1")
    if choice is None:
        return None
    if choice == "":
        return {}
    try:
        selected = int(choice.strip())
    except ValueError:
        return {}
    if selected == len(presets) + 1:
        base_url = _windows_input("Base URL", "Pair destination", "https://console.pluschwood.com")
        if base_url is None:
            return None
        if not base_url.strip():
            return {}
        label = _windows_input("Label", "Pair destination", "Custom") or "Custom"
        if label is None:
            return None
    elif 1 <= selected <= len(presets):
        preset = presets[selected - 1]
        # Always confirm/edit the URL so the value used is visible.
        base_url = _windows_input(
            f"Base URL for {preset['label']}",
            "Pair destination",
            preset["base_url"],
        )
        if base_url is None:
            return None
        if not base_url.strip():
            return {}
        label = preset["label"]
    else:
        return {}
    code = _windows_input("Pairing code from Settings → Tally Sync", "Pair destination", "")
    if code is None:
        return None
    if not code.strip():
        return {}
    return {"label": label.strip() or "Custom", "base_url": base_url.strip(), "code": code.strip()}


def _windows_ledger_mapping(existing: dict) -> dict | None:
    import sys

    if not sys.platform.startswith("win"):
        return None
    mapping: dict[str, str] = {}
    for key, label, default in FIELDS:
        suggested = str(existing.get(key) or default)
        value = _windows_input(label, "Tally ledger mapping", suggested)
        if value is None:
            return None
        if not value.strip():
            return {}
        mapping[key] = value.strip()
    return mapping


def _console_destination_pair(presets: list[dict]) -> dict | None:
    print("Pair a sync destination")
    for index, item in enumerate(presets, start=1):
        print(f"  {index}. {item['label']} ({item['base_url']})")
    print(f"  {len(presets) + 1}. Custom URL")
    try:
        raw = input("Choose destination number: ").strip()
        selected = int(raw)
    except (EOFError, ValueError):
        return None
    if selected == len(presets) + 1:
        try:
            base_url = input("Base URL (e.g. https://console.pluschwood.com): ").strip()
            label = input("Label [Custom]: ").strip() or "Custom"
        except EOFError:
            return None
    elif 1 <= selected <= len(presets):
        preset = presets[selected - 1]
        try:
            edited = input(f"Base URL [{preset['base_url']}]: ").strip()
        except EOFError:
            return None
        base_url = edited or preset["base_url"]
        label = preset["label"]
    else:
        return None
    try:
        code = input("Pairing code: ").strip()
    except EOFError:
        return None
    if not base_url or not code:
        return None
    return {"label": label, "base_url": base_url, "code": code}


def _console_ledger_mapping(existing: dict) -> dict | None:
    print("Tally ledger mapping")
    print("Press Enter to keep the suggested value.")
    mapping: dict[str, str] = {}
    for key, label, default in FIELDS:
        suggested = str(existing.get(key) or default)
        try:
            value = input(f"{label} [{suggested}]: ").strip() or suggested
        except EOFError:
            return None
        if not value:
            return None
        mapping[key] = value
    return mapping


def _tk_destination_login(presets: list[dict]) -> dict | None:
    if not _tkinter_available():
        return None
    import tkinter as tk
    from tkinter import ttk

    result: dict[str, str] = {"cancelled": "1"}
    root = tk.Tk()
    root.title("Sign in to connect")
    root.resizable(False, False)
    frame = ttk.Frame(root, padding=16)
    frame.grid(row=0, column=0)
    ttk.Label(
        frame,
        text="Choose Pluschwood or AutoSync. Your browser will open so you can sign in and approve this PC.",
        wraplength=420,
    ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))
    choice = tk.IntVar(value=1 if presets else 0)
    url_var = tk.StringVar(value=(presets[0]["base_url"] if presets else "https://console.pluschwood.com"))
    label_var = tk.StringVar(value=(presets[0]["label"] if presets else "Custom"))

    def apply_preset() -> None:
        index = choice.get()
        if 1 <= index <= len(presets):
            preset = presets[index - 1]
            url_var.set(preset["base_url"])
            label_var.set(preset["label"])
        else:
            label_var.set("Custom")

    for index, preset in enumerate(presets, start=1):
        ttk.Radiobutton(
            frame,
            text=f"{preset['label']} ({preset['base_url']})",
            variable=choice,
            value=index,
            command=apply_preset,
        ).grid(row=index, column=0, columnspan=2, sticky="w")
    custom_row = len(presets) + 1
    ttk.Radiobutton(frame, text="Custom URL", variable=choice, value=0, command=apply_preset).grid(
        row=custom_row, column=0, columnspan=2, sticky="w", pady=(8, 0)
    )
    ttk.Label(frame, text="Base URL").grid(row=custom_row + 1, column=0, sticky="w", pady=4)
    ttk.Entry(frame, textvariable=url_var, width=42).grid(row=custom_row + 1, column=1, sticky="ew", pady=4)
    ttk.Label(frame, text="Label").grid(row=custom_row + 2, column=0, sticky="w", pady=4)
    ttk.Entry(frame, textvariable=label_var, width=42).grid(row=custom_row + 2, column=1, sticky="ew", pady=4)

    def save() -> None:
        result.clear()
        result.update({"label": label_var.get().strip() or "Custom", "base_url": url_var.get().strip()})
        root.destroy()

    def cancel() -> None:
        result.clear()
        result["cancelled"] = "1"
        root.destroy()

    buttons = ttk.Frame(frame)
    buttons.grid(row=custom_row + 3, column=0, columnspan=2, sticky="e", pady=(16, 0))
    ttk.Button(buttons, text="Cancel", command=cancel).grid(row=0, column=0, padx=(0, 8))
    ttk.Button(buttons, text="Open browser", command=save).grid(row=0, column=1)
    root.protocol("WM_DELETE_WINDOW", cancel)
    root.attributes("-topmost", True)
    root.mainloop()
    if result.get("cancelled"):
        return {}
    return result


def _windows_destination_login(presets: list[dict]) -> dict | None:
    import sys

    if not sys.platform.startswith("win"):
        return None
    lines = ["Enter destination number:"]
    for index, item in enumerate(presets, start=1):
        lines.append(f"{index}. {item['label']}")
    lines.append(f"{len(presets) + 1}. Custom URL")
    choice = _windows_input("\r\n".join(lines), "Sign in to connect", "1")
    if choice is None:
        return None
    if not choice.strip():
        return {}
    try:
        selected = int(choice.strip())
    except ValueError:
        return {}
    if selected == len(presets) + 1:
        base_url = _windows_input("Base URL", "Sign in to connect", "https://console.pluschwood.com")
        if base_url is None:
            return None
        if not base_url.strip():
            return {}
        label = _windows_input("Label", "Sign in to connect", "Custom") or "Custom"
    elif 1 <= selected <= len(presets):
        preset = presets[selected - 1]
        base_url = _windows_input("Base URL", "Sign in to connect", preset["base_url"])
        if base_url is None:
            return None
        if not base_url.strip():
            return {}
        label = preset["label"]
    else:
        return {}
    return {"label": label.strip() or "Custom", "base_url": base_url.strip()}


def _console_destination_login(presets: list[dict]) -> dict | None:
    print("Sign in to connect a sync destination")
    for index, item in enumerate(presets, start=1):
        print(f"  {index}. {item['label']} ({item['base_url']})")
    print(f"  {len(presets) + 1}. Custom URL")
    try:
        raw = input("Choose destination number: ").strip()
        selected = int(raw)
    except (EOFError, ValueError):
        return None
    if selected == len(presets) + 1:
        try:
            base_url = input("Base URL (e.g. https://console.pluschwood.com): ").strip()
            label = input("Label [Custom]: ").strip() or "Custom"
        except EOFError:
            return None
    elif 1 <= selected <= len(presets):
        preset = presets[selected - 1]
        try:
            edited = input(f"Base URL [{preset['base_url']}]: ").strip()
        except EOFError:
            return None
        base_url = edited or preset["base_url"]
        label = preset["label"]
    else:
        return None
    if not base_url:
        return None
    return {"label": label, "base_url": base_url}
