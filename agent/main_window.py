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


HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>Tally Sync</title>
<style>
  :root {
    --bg: #f0f2f5;
    --panel: #ffffff;
    --text: #1f2937;
    --muted: #6b7280;
    --line: #d1d5db;
    --menu: #f8fafc;
    --accent: #0f766e;
    --ok: #15803d;
    --bad: #b91c1c;
    --blue: #1d4ed8;
  }
  * { box-sizing: border-box; }
  html, body { height: 100%; }
  body {
    margin: 0;
    font: 13px/1.45 "Segoe UI", system-ui, sans-serif;
    background: var(--bg);
    color: var(--text);
    display: flex;
    flex-direction: column;
  }

  /* Classic Windows-style top menu bar */
  .menubar {
    display: flex;
    align-items: stretch;
    background: var(--menu);
    border-bottom: 1px solid var(--line);
    user-select: none;
    flex: 0 0 auto;
  }
  .menu {
    position: relative;
  }
  .menu > button {
    appearance: none;
    border: 0;
    background: transparent;
    padding: 7px 12px;
    font: inherit;
    color: var(--text);
    cursor: default;
  }
  .menu:hover > button,
  .menu.open > button {
    background: #e8eef7;
  }
  .dropdown {
    display: none;
    position: absolute;
    top: 100%;
    left: 0;
    min-width: 220px;
    background: #fff;
    border: 1px solid var(--line);
    box-shadow: 0 8px 24px rgba(15, 23, 42, 0.12);
    z-index: 50;
    padding: 4px 0;
  }
  .menu.open .dropdown { display: block; }
  .dropdown button {
    display: block;
    width: 100%;
    text-align: left;
    appearance: none;
    border: 0;
    background: transparent;
    padding: 8px 14px;
    font: inherit;
    cursor: pointer;
  }
  .dropdown button:hover { background: #e8eef7; }
  .dropdown .sep {
    height: 1px;
    background: var(--line);
    margin: 4px 0;
  }
  .menubar .spacer { flex: 1; }
  .menubar .version {
    align-self: center;
    padding: 0 12px;
    color: var(--muted);
    font-size: 12px;
  }

  .content {
    flex: 1;
    padding: 28px 32px;
    overflow: auto;
  }
  .view { display: none; max-width: 860px; }
  .view.active { display: block; }

  h1 {
    margin: 0 0 6px;
    font-size: 22px;
    font-weight: 600;
  }
  .lead {
    margin: 0 0 24px;
    color: var(--muted);
  }

  .summary {
    display: grid;
    grid-template-columns: 1.2fr 1fr;
    gap: 16px;
  }
  .summary-card {
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: 10px;
    padding: 20px 22px;
    min-height: 140px;
  }
  .summary-card .label {
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--muted);
    margin-bottom: 10px;
  }
  .summary-card .value {
    font-size: 20px;
    font-weight: 650;
    word-break: break-word;
  }
  .summary-card .meta {
    margin-top: 10px;
    color: var(--muted);
    font-size: 13px;
  }
  .ok { color: var(--ok); }
  .bad { color: var(--bad); }

  .settings-panel {
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: 10px;
    padding: 20px 22px;
  }
  form { display: grid; gap: 14px; max-width: 520px; }
  label { display: grid; gap: 6px; }
  input, select {
    padding: 9px 10px;
    border: 1px solid var(--line);
    border-radius: 6px;
    font: inherit;
    background: #fff;
  }
  .actions { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
  .btn {
    appearance: none;
    border: 1px solid var(--line);
    background: #fff;
    border-radius: 6px;
    padding: 8px 14px;
    font: inherit;
    cursor: pointer;
  }
  .btn:hover { background: #f8fafc; }
  .btn.primary {
    background: var(--accent);
    border-color: var(--accent);
    color: #fff;
  }
  #flash { color: var(--blue); min-height: 1.2em; }
  .statusbar {
    flex: 0 0 auto;
    border-top: 1px solid var(--line);
    background: #f8fafc;
    padding: 6px 12px;
    color: var(--muted);
    font-size: 12px;
  }
</style>
</head>
<body>
  <nav class="menubar" id="menubar">
    <div class="menu" data-menu="file">
      <button type="button">File</button>
      <div class="dropdown">
        <button type="button" data-action="home">Home</button>
        <button type="button" data-action="hide">Hide to tray</button>
        <div class="sep"></div>
        <button type="button" data-action="quit">Quit</button>
      </div>
    </div>
    <div class="menu" data-menu="connection">
      <button type="button">Connection</button>
      <div class="dropdown">
        <button type="button" data-action="sign_in">Sign in to connect…</button>
        <button type="button" data-action="pair">Enter pairing code…</button>
        <div class="sep"></div>
        <button type="button" data-action="import">Run full import</button>
        <button type="button" data-action="sync">Sync now</button>
        <button type="button" data-action="mapping">Ledger mapping…</button>
        <div class="sep"></div>
        <button type="button" data-action="log">Open sync log</button>
      </div>
    </div>
    <div class="menu" data-menu="settings">
      <button type="button">Settings</button>
      <div class="dropdown">
        <button type="button" data-action="show_settings">Preferences…</button>
        <button type="button" data-action="update">Check for updates…</button>
      </div>
    </div>
    <div class="menu" data-menu="help">
      <button type="button">Help</button>
      <div class="dropdown">
        <button type="button" data-action="github">GitHub repository</button>
        <button type="button" data-action="releases">Releases</button>
      </div>
    </div>
    <div class="spacer"></div>
    <div class="version" id="version"></div>
  </nav>

  <main class="content">
    <section class="view active" id="view-home">
      <h1>Home</h1>
      <p class="lead">Summary of the current Tally connection and the last successful sync.</p>
      <div class="summary">
        <div class="summary-card">
          <div class="label">Summary</div>
          <div class="value" id="summary-title">—</div>
          <div class="meta" id="summary-meta">—</div>
        </div>
        <div class="summary-card">
          <div class="label">Last sync</div>
          <div class="value" id="last-sync">—</div>
          <div class="meta" id="last-sync-meta">—</div>
        </div>
      </div>
    </section>

    <section class="view" id="view-settings">
      <h1>Settings</h1>
      <p class="lead">Configure Tally HTTP access, import date range, and outbound interval.</p>
      <div class="settings-panel">
        <form onsubmit="return saveSettings(event)">
          <label>Tally HTTP URL<input id="tally_url" /></label>
          <label>Import from date (YYYY-MM-DD)<input id="from_date" placeholder="YYYY-MM-DD" /></label>
          <label>Import to date (YYYY-MM-DD)<input id="to_date" placeholder="YYYY-MM-DD" /></label>
          <label>Outbound interval (hours)
            <select id="interval"><option>3</option><option selected>6</option></select>
          </label>
          <div class="muted" id="data_dir" style="color:var(--muted)"></div>
          <div class="actions">
            <button class="btn primary" type="submit">Save</button>
            <button class="btn" type="button" onclick="showView('home')">Back to Home</button>
            <span id="flash"></span>
          </div>
        </form>
      </div>
    </section>
  </main>

  <footer class="statusbar" id="statusbar">Ready</footer>

<script>
  function showView(name) {
    document.querySelectorAll('.view').forEach(el => el.classList.remove('active'));
    const view = document.getElementById('view-' + name);
    if (view) view.classList.add('active');
    closeMenus();
  }

  function closeMenus() {
    document.querySelectorAll('.menu').forEach(el => el.classList.remove('open'));
  }

  document.getElementById('menubar').addEventListener('click', (event) => {
    const menuBtn = event.target.closest('.menu > button');
    const actionBtn = event.target.closest('[data-action]');
    if (menuBtn) {
      const menu = menuBtn.parentElement;
      const wasOpen = menu.classList.contains('open');
      closeMenus();
      if (!wasOpen) menu.classList.add('open');
      event.stopPropagation();
      return;
    }
    if (actionBtn) {
      const action = actionBtn.getAttribute('data-action');
      closeMenus();
      if (action === 'home') showView('home');
      else if (action === 'show_settings') showView('settings');
      else api(action);
      event.stopPropagation();
    }
  });

  document.addEventListener('click', () => closeMenus());

  async function api(name, payload) {
    const flash = document.getElementById('flash');
    const bar = document.getElementById('statusbar');
    bar.textContent = 'Working…';
    try {
      const result = await window.pywebview.api.call(name, payload || null);
      const message = (result && result.message) || 'Done';
      bar.textContent = message;
      if (flash) flash.textContent = message;
      if (result && result.alert) alert(result.alert);
      if (result && result.open_url) window.open(result.open_url, '_blank');
      await refresh();
      return result;
    } catch (err) {
      bar.textContent = String(err);
      if (flash) flash.textContent = String(err);
      alert(String(err));
    }
  }

  async function refresh() {
    const data = await window.pywebview.api.call('refresh', null);
    if (!data) return;
    const summaryTitle = document.getElementById('summary-title');
    summaryTitle.textContent = data.tally || 'Tally offline';
    summaryTitle.className = 'value ' + (data.tally_ok ? 'ok' : 'bad');
    document.getElementById('summary-meta').textContent =
      (data.destinations || 'no destinations') + ' · ' + (data.mapping || 'mapping needed');
    document.getElementById('last-sync').textContent = data.last_sync_display || 'Never';
    document.getElementById('last-sync-meta').textContent = data.last_message || data.status || '';
    document.getElementById('version').textContent = 'v' + (data.version || '');
    document.getElementById('statusbar').textContent = data.status || 'Ready';
    document.getElementById('tally_url').value = data.tally_url || '';
    document.getElementById('from_date').value = data.import_from_date || '';
    document.getElementById('to_date').value = data.import_to_date || '';
    document.getElementById('interval').value = String(data.interval_hours || 6);
    document.getElementById('data_dir').textContent = 'Data folder: ' + (data.data_dir || '');
  }

  async function saveSettings(event) {
    event.preventDefault();
    await api('save', {
      tally_url: document.getElementById('tally_url').value,
      import_from_date: document.getElementById('from_date').value || null,
      import_to_date: document.getElementById('to_date').value || null,
      interval_hours: Number(document.getElementById('interval').value || 6)
    });
    return false;
  }

  window.addEventListener('pywebviewready', () => {
    refresh();
    setInterval(refresh, 5000);
  });
</script>
</body>
</html>
"""


class _Api:
    def __init__(self, controller: AppController, window: "MainWindow"):
        self.controller = controller
        self.window = window

    def call(self, name: str, payload: dict | None = None) -> dict[str, Any]:
        payload = payload or {}
        if name == "refresh":
            detail = self.controller.get_detail()
            detail["status"] = self.controller.get_status()
            return detail
        if name == "hide":
            self.window.hide_to_tray()
            return {"message": "Hidden to tray"}
        if name == "quit":
            self.window.quit_app()
            return {"message": "Quitting"}
        if name == "save":
            self.controller.save_settings(payload)
            return {"message": "Settings saved", "alert": "Settings saved"}
        if name in {"sign_in", "pair", "import", "sync", "mapping", "log"}:
            actions = {
                "sign_in": (self.controller.on_sign_in, "Sign-in started — complete approval in the browser"),
                "pair": (self.controller.on_pair, "Pairing dialog opened"),
                "import": (self.controller.on_import, "Import started"),
                "sync": (self.controller.on_sync_now, "Sync started"),
                "mapping": (self.controller.on_mapping, "Mapping dialog opened"),
                "log": (self.controller.on_open_log, "Opened sync log"),
            }
            fn, message = actions[name]
            threading.Thread(target=fn, daemon=True).start()
            return {"message": message}
        if name == "github":
            webbrowser.open(GITHUB_REPO_URL)
            return {"message": "Opened GitHub"}
        if name == "releases":
            webbrowser.open(GITHUB_RELEASES_URL)
            return {"message": "Opened releases"}
        if name == "update":
            info = self.controller.on_check_update()
            result: dict[str, Any] = {
                "message": info.get("message") or "Update check complete",
                "alert": info.get("message") or "Update check complete",
            }
            if info.get("update_available") and info.get("release_url"):
                result["open_url"] = info["release_url"]
                result["alert"] = f"Update available: v{info.get('latest_version')}. Opening release page."
            return result
        return {"message": f"Unknown action: {name}"}


class MainWindow:
    """Native Windows app window (WebView2 via pywebview). Close/hide keeps tray running."""

    def __init__(self, controller: AppController):
        self.controller = controller
        self._window = None
        self._hidden = False
        self._quitting = False
        self._api = _Api(controller, self)

    def hide_to_tray(self) -> None:
        self._hidden = True
        if self._window is not None:
            self._window.hide()

    def show(self) -> None:
        self._hidden = False
        if self._window is not None:
            self._window.show()
            try:
                self._window.restore()
            except Exception:
                pass

    def quit_app(self) -> None:
        self._quitting = True
        try:
            self.controller.on_quit()
        finally:
            if self._window is not None:
                try:
                    self._window.destroy()
                except Exception:
                    pass

    def run(self) -> None:
        import webview

        self._window = webview.create_window(
            APP_NAME,
            html=HTML,
            js_api=self._api,
            width=920,
            height=640,
            min_size=(760, 520),
        )

        def on_closing() -> bool:
            if self._quitting:
                return True
            self.hide_to_tray()
            return False

        try:
            self._window.events.closing += on_closing
        except Exception:
            pass

        try:
            webview.start(gui="edgechromium", debug=False)
        except Exception:
            webview.start(debug=False)


SettingsController = AppController
