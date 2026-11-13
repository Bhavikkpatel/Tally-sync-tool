from __future__ import annotations

import os
import sys
import threading
import time
import traceback
import webbrowser
from pathlib import Path

# Allow `python -m agent` from the project root.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent import destinations as destination_store
from agent import sync_log
from agent.autosync_client import AutoSyncClient
from agent.config import AgentConfig
from agent.destinations import PRESETS, Destination
from agent.import_runner import ImportRunner
from agent.mapping_dialog import ask_destination_login, ask_destination_pair, ask_ledger_mapping
from agent.outbound_runner import OutboundRunner
from agent.scheduler import IntervalScheduler
from agent.security import load_token, save_token
from datetime import datetime, timedelta, timezone

from agent.main_window import AppController, MainWindow
from agent.storage import LocalStore
from agent.tally_client import TallyClient
from agent.tray import open_sync_log, run_tray
from agent.updater import check_for_update
from agent.version import APP_NAME, __version__

IST = timezone(timedelta(hours=5, minutes=30))


class SyncApp:
    def __init__(self):
        sync_log.ensure_stdio()
        self.config = AgentConfig()
        self.presets = [
            {
                **preset,
                "base_url": (
                    os.environ["AUTOSYNC_BASE_URL"].rstrip("/")
                    if preset["id"] == "autosync" and os.environ.get("AUTOSYNC_BASE_URL")
                    else preset["base_url"]
                ),
            }
            for preset in PRESETS
        ]
        self.store = LocalStore(self.config.db_path)
        destination_store.migrate_legacy_destination(
            self.store,
            self.config.data_dir,
            self.config.autosync_base_url,
            self.config.token_path,
        )
        saved_tally = self.store.get_meta("tally_url")
        if saved_tally:
            self.config.tally_url = str(saved_tally).rstrip("/")
        saved_from = self.store.get_meta("import_from_date")
        saved_to = self.store.get_meta("import_to_date")
        if saved_from:
            self.config.import_from_date = str(saved_from)
        if saved_to:
            self.config.import_to_date = str(saved_to)
        self.tally = TallyClient(self.config.tally_url)
        interval = int(self.store.get_meta("interval_hours", self.config.default_interval_hours) or 6)
        self.scheduler = IntervalScheduler(interval, self.scheduled_tick, self.config.poll_seconds)
        self.last_message = "Starting"
        self._stop = False
        self._tray_stop = threading.Event()
        self.window: MainWindow | None = None
        sync_log.log_event(
            f"{APP_NAME} started · v{__version__} · log={sync_log.log_path(self.config.data_dir)}",
            data_dir=self.config.data_dir,
            counts={"interval_hours": interval, "paired": len(self.paired())},
        )

    def paired(self) -> list[tuple[Destination, str]]:
        return destination_store.paired_destinations(self.store, self.config.data_dir)

    def targets(self) -> list[tuple[Destination, AutoSyncClient]]:
        return [
            (destination, destination.client(self.config.data_dir, token))
            for destination, token in self.paired()
        ]

    def status_text(self) -> str:
        health = self.tally.health()
        tally_bit = health["company"] if health["ok"] else "Tally offline"
        dest_bit = destination_store.status_summary(self.store, self.config.data_dir)
        mapping_bit = (
            "mapped"
            if OutboundRunner(self.store, self.tally, self._primary_client()).mapping_ready()
            else "mapping needed"
        )
        # Keep tray/menu short; full IST count lines live in sync.log only.
        activity = (self.last_message or "").strip()
        if activity.startswith("[") and "] " in activity:
            activity = activity.split("] ", 1)[1]
        if " | " in activity:
            activity = activity.split(" | ", 1)[0]
        if len(activity) > 48:
            activity = activity[:47].rstrip() + "…"
        return f"{tally_bit} · {dest_bit} · {mapping_bit} · {activity}"

    def _primary_client(self) -> AutoSyncClient:
        paired = self.paired()
        if paired:
            destination, token = paired[0]
            return destination.client(self.config.data_dir, token)
        return AutoSyncClient(self.config.autosync_base_url)

    def _finish_registration(self, destination: Destination, result: dict) -> None:
        save_token(destination.token_path(self.config.data_dir), result["installation_token"])
        self.store.set_meta(f"installation_id_{destination.id}", result.get("installation_id"))
        self.store.set_meta(f"organization_id_{destination.id}", result.get("organization_id"))
        if result.get("brand_id") is not None:
            self.store.set_meta("brand_id", result.get("brand_id"))
        if result.get("interval_hours"):
            self.store.set_meta("interval_hours", result["interval_hours"])
            self.scheduler.set_interval_hours(int(result["interval_hours"]))
        if result.get("mapping"):
            self.store.set_meta("ledger_mapping", result["mapping"])
        destination_store.set_import_done(self.store, destination.id, False)
        self.store.set_meta("initial_import_done", False)
        self.last_message = f"Connected {destination.label}"
        self._progress(self.last_message)
        self._progress("Starting initial import (this can take a while)")
        self.run_import(force=True)

    def sign_in_connect(self) -> None:
        """Browser login registration — preferred over pairing codes."""
        try:
            choice = ask_destination_login(self.presets)
            if not choice:
                self.last_message = "Sign-in cancelled"
                return
            self._progress(f"Checking Tally at {self.config.tally_url}")
            health = self.tally.health()
            if not health["ok"]:
                self.last_message = f"Open Tally and load the company first ({health.get('error') or 'offline'})"
                self._progress(self.last_message)
                return
            company = health["detail"] or {}
            if not company.get("guid") or not company.get("name"):
                self.last_message = "Tally did not return a company ID and name"
                self._progress(self.last_message)
                return
            destination = destination_store.upsert_destination(
                self.store,
                label=choice["label"],
                base_url=choice["base_url"],
            )
            client = AutoSyncClient(destination.base_url)
            try:
                session = client.create_device_session(company, agent_version="autosync-tally-agent")
            except Exception as exc:
                text = str(exc)
                if "404" in text:
                    raise RuntimeError(
                        f"{destination.base_url} has no /api/integrations/tally/device-sessions yet. "
                        "Deploy the Pluschwood/AutoSync backend with browser-login support, "
                        "or use tray → Enter pairing code… until then."
                    ) from exc
                raise
            user_code = session.get("user_code") or ""
            verify_url = session.get("verification_uri_complete") or session.get("verification_uri")
            poll_seconds = max(3, int(session.get("interval") or 5))
            sync_log.log_event(
                f"{destination.label} · browser login started",
                data_dir=self.config.data_dir,
                counts={"user_code": user_code, "poll_seconds": poll_seconds},
            )
            self._progress(f"Open browser and approve user code {user_code}")
            if verify_url:
                webbrowser.open(verify_url)
            device_code = session["device_code"]
            deadline = time.time() + 15 * 60
            result = None
            while time.time() < deadline:
                result = client.poll_device_token(device_code)
                if result:
                    break
                self.last_message = f"Waiting for browser approval ({user_code})"
                time.sleep(poll_seconds)
            if not result:
                raise RuntimeError("Browser approval timed out or was not completed")
            sync_log.log_event(
                f"{destination.label} · browser login approved",
                data_dir=self.config.data_dir,
                counts={"installation_id": result.get("installation_id"), "organization_id": result.get("organization_id")},
            )
            self._finish_registration(destination, result)
        except Exception as exc:
            self.last_message = f"Sign-in failed: {exc}"
            self._progress(self.last_message)
            traceback.print_exc()

    def pair(self) -> None:
        """Fallback pairing-code registration."""
        try:
            choice = ask_destination_pair(self.presets)
            if not choice:
                self.last_message = "Pairing cancelled"
                return
            self._progress(f"Checking Tally at {self.config.tally_url}")
            health = self.tally.health()
            if not health["ok"]:
                self.last_message = f"Open Tally and load the company first ({health.get('error') or 'offline'})"
                self._progress(self.last_message)
                return
            self._progress(f"Tally company: {health.get('company') or '(loaded)'}")
            destination = destination_store.upsert_destination(
                self.store,
                label=choice["label"],
                base_url=choice["base_url"],
            )
            brand_id = self.store.get_meta("brand_id")
            client = AutoSyncClient(destination.base_url)
            self._progress(f"Calling {client.base_url}/api/integrations/tally/pair")
            result = client.pair(
                choice["code"],
                health["detail"],
                int(self.store.get_meta("interval_hours", self.config.default_interval_hours) or 6),
                brand_id=brand_id,
            )
            self._finish_registration(destination, result)
        except Exception as exc:
            self.last_message = f"Pair failed: {exc}"
            self._progress(self.last_message)
            traceback.print_exc()

    def run_import(self, force: bool = False, force_destination_ids: set[str] | None = None) -> None:
        targets = self.targets()
        if not targets:
            self.last_message = "Pair a destination first"
            return
        self.config.import_from_date = self.store.get_meta("import_from_date", self.config.import_from_date)
        self.config.import_to_date = self.store.get_meta("import_to_date", self.config.import_to_date)
        forced = set(force_destination_ids or ())
        if force:
            forced.update(
                destination.id
                for destination, _token in self.paired()
                if destination_store.is_pluschwood(destination)
            )
        try:
            range_bit = ""
            if self.config.import_from_date or self.config.import_to_date:
                range_bit = f" ({self.config.import_from_date or '…'} → {self.config.import_to_date or '…'})"
            self.last_message = f"Importing from Tally{range_bit}"
            self._progress(self.last_message)
            summary = ImportRunner(
                self.store,
                self.tally,
                targets,
                self.config,
                self._progress,
                force_destination_ids=forced,
            ).run(force=False)
            self._mark_synced("import")
            self.last_message = f"Import complete: {summary.get('destinations') or summary}"
            self._progress(self.last_message)
            if not OutboundRunner(self.store, self.tally, self._primary_client()).mapping_ready():
                self.configure_mapping()
        except Exception as exc:
            self.last_message = f"Import failed: {exc}"
            self._progress(self.last_message)
            traceback.print_exc()

    def configure_mapping(self) -> None:
        if not self.paired():
            self.last_message = "Pair a destination first"
            return
        existing = self.store.get_meta("ledger_mapping") or {}
        mapping = ask_ledger_mapping(existing)
        if not mapping:
            self.last_message = "Mapping cancelled"
            return
        self.store.set_meta("ledger_mapping", mapping)
        errors = []
        for destination, token in self.paired():
            try:
                destination.client(self.config.data_dir, token).update_mapping(mapping)
            except Exception as exc:
                errors.append(f"{destination.label}: {exc}")
        self.last_message = "Mapping saved" if not errors else f"Mapping saved locally ({errors[0]})"

    def sync_now(self) -> None:
        try:
            sync_log.log_event("Sync now started", data_dir=self.config.data_dir)
            self.scheduled_tick()
            self._mark_synced("sync")
            if not self.last_message.startswith("["):
                self.last_message = "Synced"
        except Exception as exc:
            self.last_message = f"Sync failed: {exc}"
            sync_log.log_event(f"Sync failed: {exc}", data_dir=self.config.data_dir)
            traceback.print_exc()

    def scheduled_tick(self) -> None:
        health = self.tally.health()
        if not health["ok"]:
            raise RuntimeError(health.get("error") or "Tally offline")
        targets = self.targets()
        if not targets:
            raise RuntimeError("No paired destinations")

        needs_import = False
        for destination, client in targets:
            try:
                remote = client.status()
            except Exception as exc:
                self._progress(f"{destination.label} status failed: {exc}")
                continue
            installation = remote.get("installation") or {}
            if installation.get("mapping"):
                self.store.set_meta("ledger_mapping", installation["mapping"])
            if installation.get("interval_hours"):
                hours = int(installation["interval_hours"])
                self.store.set_meta("interval_hours", hours)
                self.scheduler.set_interval_hours(hours)
            if not installation.get("import_complete", True) or not destination_store.import_done(
                self.store, destination.id
            ):
                destination_store.set_import_done(self.store, destination.id, False)
                needs_import = True

        if needs_import or not self.store.get_meta("initial_import_done"):
            self.run_import(force=True)
            return

        runner = OutboundRunner(self.store, self.tally, self._primary_client(), self._progress)
        if not runner.mapping_ready():
            raise RuntimeError("Ledger mapping incomplete")

        summaries = []
        for destination, client in targets:
            try:
                feed = client.outbound_feed()
                items = feed.get("items") or []
                if not items:
                    sync_log.log_event(
                        f"{destination.label} · outbound idle",
                        data_dir=self.config.data_dir,
                        counts={"outbound": 0},
                    )
                    summaries.append(f"{destination.label}: nothing outbound")
                    continue
                summary = OutboundRunner(self.store, self.tally, client, self._progress).run()
                sync_log.log_event(
                    f"{destination.label} · outbound synced",
                    data_dir=self.config.data_dir,
                    counts={"outbound": len(items), **(summary if isinstance(summary, dict) else {})},
                )
                summaries.append(f"{destination.label}: {summary}")
            except Exception as exc:
                sync_log.log_event(
                    f"{destination.label} · outbound failed: {exc}",
                    data_dir=self.config.data_dir,
                )
                summaries.append(f"{destination.label}: failed ({exc})")
        self.last_message = "; ".join(summaries) or "Outbound idle"
        self._mark_synced("outbound")

    def _progress(self, message: str) -> None:
        # ImportRunner already writes IST count lines via sync_log; avoid double-logging those.
        if message.startswith("["):
            self.last_message = message
            return
        self.last_message = sync_log.log_event(message, data_dir=self.config.data_dir)

    def _mark_synced(self, kind: str = "sync") -> None:
        stamp = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")
        self.store.set_meta("last_sync_at", stamp)
        self.store.set_meta("last_sync_kind", kind)

    def status_detail(self) -> dict:
        health = self.tally.health()
        last_sync = self.store.get_meta("last_sync_at") or ""
        last_kind = self.store.get_meta("last_sync_kind") or "sync"
        return {
            "version": __version__,
            "tally": health.get("company") if health.get("ok") else (health.get("error") or "offline"),
            "tally_ok": bool(health.get("ok")),
            "destinations": destination_store.status_summary(self.store, self.config.data_dir),
            "mapping": (
                "mapped"
                if OutboundRunner(self.store, self.tally, self._primary_client()).mapping_ready()
                else "mapping needed"
            ),
            "data_dir": str(self.config.data_dir),
            "tally_url": self.config.tally_url,
            "import_from_date": self.config.import_from_date or self.store.get_meta("import_from_date") or "",
            "import_to_date": self.config.import_to_date or self.store.get_meta("import_to_date") or "",
            "interval_hours": int(self.store.get_meta("interval_hours", self.config.default_interval_hours) or 6),
            "last_message": self.last_message,
            "last_sync_at": last_sync,
            "last_sync_display": last_sync or "Never",
            "last_sync_kind": last_kind,
        }

    def save_settings(self, values: dict) -> None:
        tally_url = (values.get("tally_url") or "").strip().rstrip("/")
        if tally_url:
            self.config.tally_url = tally_url
            self.store.set_meta("tally_url", tally_url)
            self.tally = TallyClient(tally_url)
        from_date = values.get("import_from_date") or None
        to_date = values.get("import_to_date") or None
        self.config.import_from_date = from_date
        self.config.import_to_date = to_date
        self.store.set_meta("import_from_date", from_date)
        self.store.set_meta("import_to_date", to_date)
        hours = int(values.get("interval_hours") or 6)
        if hours not in {3, 6}:
            raise ValueError("Interval must be 3 or 6 hours")
        self.store.set_meta("interval_hours", hours)
        self.scheduler.set_interval_hours(hours)
        self.last_message = "Settings saved"
        sync_log.log_event(
            "Settings saved",
            data_dir=self.config.data_dir,
            counts={"interval_hours": hours, "tally_url": tally_url or self.config.tally_url},
        )

    def open_ui(self) -> None:
        if self.window is not None:
            self.window.show()

    def check_update_info(self) -> dict:
        info = check_for_update()
        sync_log.log_event(
            f"Update check · {info.message}",
            data_dir=self.config.data_dir,
            counts={
                "current": info.current_version,
                "latest": info.latest_version,
                "update_available": info.update_available,
            },
        )
        return {
            "current_version": info.current_version,
            "latest_version": info.latest_version,
            "update_available": info.update_available,
            "release_url": info.release_url,
            "release_notes": info.release_notes,
            "asset_name": info.asset_name,
            "asset_url": info.asset_url,
            "message": info.message,
        }

    def check_update_tray(self) -> None:
        try:
            info = self.check_update_info()
            self.last_message = info["message"]
            if info.get("update_available") and info.get("release_url"):
                webbrowser.open(info["release_url"])
        except Exception as exc:
            self.last_message = f"Update check failed: {exc}"
            sync_log.log_event(self.last_message, data_dir=self.config.data_dir)

    def quit(self) -> None:
        self._stop = True
        self._tray_stop.set()
        self.scheduler.stop()
        if self.window is not None:
            try:
                self.window.root.after(0, self.window.quit_app)
            except Exception:
                pass

    def run(self) -> None:
        self.scheduler.start()
        controller = AppController(
            get_status=self.status_text,
            get_detail=self.status_detail,
            save_settings=self.save_settings,
            on_sign_in=self.sign_in_connect,
            on_pair=self.pair,
            on_import=lambda: self.run_import(force=True),
            on_sync_now=self.sync_now,
            on_mapping=self.configure_mapping,
            on_open_log=open_sync_log,
            on_check_update=self.check_update_info,
            on_quit=self._quit_from_ui,
        )
        self.window = MainWindow(controller)

        if sys.platform.startswith("win"):
            threading.Thread(
                target=run_tray,
                kwargs={
                    "get_status": self.status_text,
                    "on_open_ui": self.open_ui,
                    "on_quit": self._quit_from_ui,
                    "stop_event": self._tray_stop,
                },
                daemon=True,
            ).start()

        # Main Windows application loop (not tray-first).
        self.window.run()

    def _quit_from_ui(self) -> None:
        self._stop = True
        self._tray_stop.set()
        self.scheduler.stop()
        if self.window is not None:
            try:
                self.window.root.quit()
            except Exception:
                pass



def main() -> None:
    SyncApp().run()


if __name__ == "__main__":
    main()
