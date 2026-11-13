from __future__ import annotations

import json
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
  :root { color-scheme: light; --bg:#f3f4f6; --card:#fff; --text:#111827; --muted:#6b7280; --line:#e5e7eb; --accent:#15803d; --danger:#b91c1c; --blue:#1d4ed8; }
  * { box-sizing: border-box; }
  body { margin:0; font:14px/1.45 "Segoe UI", system-ui, sans-serif; background:var(--bg); color:var(--text); }
  header { display:flex; align-items:center; gap:12px; padding:18px 22px 8px; }
  h1 { margin:0; font-size:22px; font-weight:650; }
  .muted { color:var(--muted); }
  .wrap { padding:0 22px 22px; }
  .sub { margin:0 0 16px; color:var(--muted); max-width:820px; }
  .cards { display:grid; grid-template-columns:repeat(3,1fr); gap:12px; margin-bottom:14px; }
  .card, .panel { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:14px; }
  .card h2, .panel h2 { margin:0 0 8px; font-size:12px; text-transform:uppercase; letter-spacing:.04em; color:var(--muted); }
  .value { font-size:16px; font-weight:650; word-break:break-word; }
  .ok { color:var(--accent); } .bad { color:var(--danger); }
  .actions { display:grid; grid-template-columns:repeat(3,1fr); gap:8px; }
  button { appearance:none; border:1px solid var(--line); background:#fff; border-radius:8px; padding:10px 12px; font:inherit; cursor:pointer; }
  button:hover { background:#f9fafb; }
  button.primary { background:var(--accent); color:#fff; border-color:var(--accent); }
  button.primary:hover { filter:brightness(.95); }
  form { display:grid; gap:10px; margin-top:8px; }
  label { display:grid; gap:4px; font-size:13px; }
  input, select { padding:9px 10px; border:1px solid var(--line); border-radius:8px; font:inherit; }
  .row { display:flex; flex-wrap:wrap; gap:8px; align-items:center; margin-top:12px; }
  #flash { color:var(--blue); min-height:1.2em; }
  footer { margin-top:14px; color:var(--muted); font-size:12px; }
</style>
</head>
<body>
  <header>
    <h1>Tally Sync</h1>
    <span class="muted" id="version"></span>
    <div style="flex:1"></div>
    <button onclick="api('hide')">Hide to tray</button>
    <button onclick="api('quit')">Quit</button>
  </header>
  <div class="wrap">
    <p class="sub">Sync the open Tally company with Pluschwood or AutoSync. Closing or hiding keeps the app in the system tray.</p>
    <div class="cards">
      <div class="card"><h2>Tally</h2><div class="value" id="tally">—</div><div class="muted">Open company via HTTP</div></div>
      <div class="card"><h2>Destinations</h2><div class="value" id="dest">—</div><div class="muted" id="mapping">Mapping: —</div></div>
      <div class="card"><h2>Activity</h2><div class="value" id="activity">—</div><div class="muted" id="status">—</div></div>
    </div>
    <div class="panel" style="margin-bottom:14px">
      <h2>Connection</h2>
      <div class="actions">
        <button class="primary" onclick="api('sign_in')">Sign in to connect</button>
        <button onclick="api('pair')">Enter pairing code</button>
        <button onclick="api('import')">Run full import</button>
        <button onclick="api('sync')">Sync now</button>
        <button onclick="api('mapping')">Ledger mapping</button>
        <button onclick="api('log')">Open sync log</button>
      </div>
    </div>
    <div class="panel">
      <h2>Settings</h2>
      <form onsubmit="return saveSettings(event)">
        <label>Tally HTTP URL<input id="tally_url" /></label>
        <label>Import from date (YYYY-MM-DD)<input id="from_date" placeholder="YYYY-MM-DD" /></label>
        <label>Import to date (YYYY-MM-DD)<input id="to_date" placeholder="YYYY-MM-DD" /></label>
        <label>Outbound interval (hours)
          <select id="interval"><option>3</option><option selected>6</option></select>
        </label>
        <div class="muted" id="data_dir"></div>
        <div class="row">
          <button class="primary" type="submit">Save settings</button>
          <button type="button" onclick="api('update')">Check for updates</button>
          <button type="button" onclick="refresh()">Refresh</button>
          <button type="button" onclick="api('github')">GitHub</button>
          <span id="flash"></span>
        </div>
      </form>
    </div>
    <footer>Tray menu: Open window · Open sync log · Quit</footer>
  </div>
<script>
  async function api(name, payload) {
    document.getElementById('flash').textContent = 'Working…';
    try {
      const result = await window.pywebview.api.call(name, payload || null);
      document.getElementById('flash').textContent = (result && result.message) || 'Done';
      if (result && result.alert) alert(result.alert);
      if (result && result.open_url) window.open(result.open_url, '_blank');
      await refresh();
      return result;
    } catch (err) {
      document.getElementById('flash').textContent = String(err);
      alert(String(err));
    }
  }
  async function refresh() {
    const data = await window.pywebview.api.call('refresh', null);
    if (!data) return;
    const tally = document.getElementById('tally');
    tally.textContent = data.tally || '—';
    tally.className = 'value ' + (data.tally_ok ? 'ok' : 'bad');
    document.getElementById('dest').textContent = data.destinations || 'none';
    document.getElementById('mapping').textContent = 'Mapping: ' + (data.mapping || '—');
    document.getElementById('activity').textContent = data.last_message || data.status || '—';
    document.getElementById('status').textContent = data.status || '';
    document.getElementById('version').textContent = 'v' + (data.version || '');
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
  window.addEventListener('pywebviewready', () => { refresh(); setInterval(refresh, 5000); });
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
            height=700,
            min_size=(780, 560),
        )

        def on_closing() -> bool:
            if self._quitting:
                return True
            # Cancel OS close and keep running in the tray.
            self.hide_to_tray()
            return False

        try:
            self._window.events.closing += on_closing
        except Exception:
            pass

        # Prefer Edge WebView2 on Windows; fall back to default if unavailable.
        try:
            webview.start(gui="edgechromium", debug=False)
        except Exception:
            webview.start(debug=False)


SettingsController = AppController
