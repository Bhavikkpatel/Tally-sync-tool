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
from agent.destinations import Destination
from agent.import_runner import ImportRunner
from agent.mapping_dialog import ask_ledger_mapping, ask_pairing_code
from agent.outbound_runner import OutboundRunner
from agent.product import (
    APP_NAME,
    DESTINATION_BASE_URL,
    DESTINATION_ID,
    DESTINATION_LABEL,
    PRODUCT_ID,
)
from agent.scheduler import IntervalScheduler
from agent.security import load_token, save_token
from datetime import datetime, timedelta, timezone

from agent.main_window import AppController, MainWindow
from agent.storage import LocalStore
from agent.tally_client import TallyClient
from agent.tray import open_sync_log, run_tray
from agent.updater import check_for_update
from agent.version import __version__

IST = timezone(timedelta(hours=5, minutes=30))


def _product_base_url() -> str:
    """Hardcoded product URL, with optional env override for local testing."""
    if PRODUCT_ID == "autosync" and os.environ.get("AUTOSYNC_BASE_URL"):
        return os.environ["AUTOSYNC_BASE_URL"].rstrip("/")
    if PRODUCT_ID == "pluschwood" and os.environ.get("PLUSCHWOOD_BASE_URL"):
        return os.environ["PLUSCHWOOD_BASE_URL"].rstrip("/")
    return DESTINATION_BASE_URL


class SyncApp:
    def __init__(self):
        sync_log.ensure_stdio()
        self.config = AgentConfig()
        self.destination_label = DESTINATION_LABEL
        self.destination_base_url = _product_base_url()
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
        self._import_lock = threading.Lock()
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
        companies = health.get("companies") or []
        if health["ok"] and len(companies) > 1:
            tally_bit = f"{len(companies)} companies"
        elif health["ok"]:
            tally_bit = health["company"] or "Tally online"
        else:
            tally_bit = "Tally offline"
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

    def _choose_company(self, companies):
        companies = [company for company in companies if company.get("guid") and company.get("name")]
        if not companies:
            raise RuntimeError("Open a Tally company with an ID and name first")
        if len(companies) == 1:
            return companies[0]
        import tkinter as tk
        from tkinter import simpledialog
        root = tk.Tk()
        root.withdraw()
        try:
            root.attributes("-topmost", True)
            options = "\n".join(f"{i}. {company['name']}" for i, company in enumerate(companies, 1))
            selected = simpledialog.askinteger("Choose Tally company", options, minvalue=1, maxvalue=len(companies), parent=root)
            return companies[selected - 1] if selected is not None else None
        finally:
            root.destroy()

    def _finish_registration(self, company: dict, result: dict) -> None:
        with self._import_lock:
            list(self._company_targets())
            destination = destination_store.upsert_destination(
                self.store, label=company["name"], base_url=self.destination_base_url,
                company_guid=company["guid"], company_name=company["name"],
            )
            save_token(destination.token_path(self.config.data_dir), result["installation_token"])
            self.store.set_meta(f"installation_id_{destination.id}", result.get("installation_id"))
            self.store.set_meta(f"organization_id_{destination.id}", result.get("organization_id"))
            self.store.set_meta(f"interval_hours_{destination.id}", result.get("interval_hours") or 6)
            self.store.set_meta(f"ledger_mapping_{destination.id}", result.get("mapping") or {})
            self._progress(f"Connected {destination.label}")
        self.run_import(force_destination_ids={destination.id})

    def _company_targets(self):
        """Bind old tokens to the company identified by the server, retaining their local IDs."""
        for destination, client in self.targets():
            if not destination.company_guid and destination_store.is_pluschwood(destination):
                try:
                    remote = client.status().get("installation") or {}
                    if not remote.get("company_guid"):
                        continue
                    rows = destination_store.list_destinations(self.store)
                    if any(item.id != destination.id and item.base_url == destination.base_url
                           and item.company_guid == remote["company_guid"] for item in rows):
                        continue
                    for item in rows:
                        if item.id == destination.id:
                            item.company_guid = remote["company_guid"]
                            item.company_name = remote.get("company_name") or ""
                            destination = item
                    destination_store.save_destinations(self.store, rows)
                except Exception:
                    continue
            yield destination, client

    def _heartbeat_loop(self):
        while not self._tray_stop.is_set():
            health = self.tally.health()
            loaded = {company.get("guid") for company in health.get("companies", [])}
            for destination, client in self.targets():
                if not destination.company_guid or not destination_store.is_pluschwood(destination):
                    continue
                state = ("tally_unavailable" if not health["ok"] else
                         "online" if destination.company_guid in loaded else "company_closed")
                try:
                    client.heartbeat(state, bool(self.store.get_meta(f"import_failed_{destination.id}")))
                except Exception:
                    continue
            self._tray_stop.wait(30)

    def sign_in_connect(self) -> None:
        """Browser login registration — preferred over pairing codes."""
        try:
            self._progress(f"Checking Tally at {self.config.tally_url}")
            health = self.tally.health()
            if not health["ok"]:
                self.last_message = f"Open Tally and load the company first ({health.get('error') or 'offline'})"
                self._progress(self.last_message)
                return
            company = self._choose_company(health["companies"])
            if company is None:
                return
            if not company.get("guid") or not company.get("name"):
                self.last_message = "Tally did not return a company ID and name"
                self._progress(self.last_message)
                return
            client = AutoSyncClient(self.destination_base_url)
            try:
                session = client.create_device_session(company, agent_version="autosync-tally-agent")
            except Exception as exc:
                text = str(exc)
                if "404" in text:
                    raise RuntimeError(
                        f"{self.destination_base_url} has no /api/integrations/tally/device-sessions yet. "
                        "Deploy the backend with browser-login support, "
                        "or use Connection → Enter pairing code… until then."
                    ) from exc
                raise
            user_code = session.get("user_code") or ""
            verify_url = session.get("verification_uri_complete") or session.get("verification_uri")
            poll_seconds = max(3, int(session.get("interval") or 5))
            sync_log.log_event(
                f"{company['name']} · browser login started",
                data_dir=self.config.data_dir,
                counts={"poll_seconds": poll_seconds},
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
                self.last_message = "Waiting for browser approval"
                time.sleep(poll_seconds)
            if not result:
                raise RuntimeError("Browser approval timed out or was not completed")
            sync_log.log_event(
                f"{company['name']} · browser login approved",
                data_dir=self.config.data_dir,
                counts={"installation_id": result.get("installation_id"), "organization_id": result.get("organization_id")},
            )
            self._finish_registration(company, result)
        except Exception as exc:
            self.last_message = f"Sign-in failed: {exc}"
            self._progress(self.last_message)
            traceback.print_exc()

    def pair(self) -> None:
        """Fallback pairing-code registration."""
        try:
            code = ask_pairing_code(f"Pair with {self.destination_label}")
            if not code:
                self.last_message = "Pairing cancelled"
                return
            self._progress(f"Checking Tally at {self.config.tally_url}")
            health = self.tally.health()
            if not health["ok"]:
                self.last_message = f"Open Tally and load the company first ({health.get('error') or 'offline'})"
                self._progress(self.last_message)
                return
            self._progress(f"Tally company: {health.get('company') or '(loaded)'}")
            company = self._choose_company(health["companies"])
            if company is None:
                return
            client = AutoSyncClient(self.destination_base_url)
            self._progress(f"Calling {client.base_url}/api/integrations/tally/pair")
            result = client.pair(
                code,
                company,
                int(self.store.get_meta("interval_hours", self.config.default_interval_hours) or 6),
            )
            self._finish_registration(company, result)
        except Exception as exc:
            self.last_message = f"Pair failed: {exc}"
            self._progress(self.last_message)
            traceback.print_exc()

    def run_import(self, force: bool = False, force_destination_ids: set[str] | None = None) -> None:
        with self._import_lock:
            targets = list(self._company_targets())
            forced = set(force_destination_ids or ())
            if force and targets:
                companies = [{"guid": item.id, "name": item.company_name or item.label} for item, _ in targets]
                choice = self._choose_company(companies)
                if not choice:
                    return
                forced.add(choice["guid"])
            if forced:
                targets = [(item, client) for item, client in targets if item.id in forced]
            self._import_companies(targets, forced)

    def _import_companies(self, targets, forced, *, incremental=False, companies=None):
        if not targets:
            return
        self.config.import_from_date = self.store.get_meta("import_from_date", self.config.import_from_date)
        self.config.import_to_date = self.store.get_meta("import_to_date", self.config.import_to_date)
        summary = ImportRunner(self.store, self.tally, targets, self.config, self._progress,
                               force_destination_ids=forced).run(incremental=incremental, companies=companies)
        by_company = summary.get("destinations", {})
        for item, _ in targets:
            result = by_company.get(item.id)
            if result:
                self.store.set_meta(f"import_failed_{item.id}", bool(result.get("error")))
            if result and not result.get("error"):
                self.store.set_meta(f"last_import_{item.id}", time.time())
                self._mark_synced("import", {"guid": item.company_guid, "name": item.company_name})
        self._progress(f"Import results: {by_company or summary}")

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
            self.scheduled_tick(force_due=True)
            self._mark_synced("sync")
            if not self.last_message.startswith("["):
                self.last_message = "Synced"
        except Exception as exc:
            self.last_message = f"Sync failed: {exc}"
            sync_log.log_event(f"Sync failed: {exc}", data_dir=self.config.data_dir)
            traceback.print_exc()

    def scheduled_tick(self, force_due=False) -> None:
        if PRODUCT_ID != "pluschwood":
            self._legacy_scheduled_tick()
            return
        with self._import_lock:
            health = self.tally.health()
            if not health["ok"]:
                return
            loaded = {company.get("guid") for company in health["companies"]}
            due, forced = [], set()
            for destination, client in self._company_targets():
                if destination.company_guid not in loaded:
                    continue
                try:
                    remote = client.status().get("installation") or {}
                except Exception:
                    continue
                if remote.get("company_guid") != destination.company_guid:
                    continue
                hours = remote.get("interval_hours") or 6
                last = self.store.get_meta(f"last_import_{destination.id}", 0) or 0
                if not remote.get("import_complete", True) and destination_store.import_done(self.store, destination.id):
                    forced.add(destination.id)
                if force_due or destination.id in forced or time.time() - last >= hours * 3600:
                    due.append((destination, client))
            self._import_companies(due, forced, incremental=True, companies=health["companies"])

    def _legacy_scheduled_tick(self) -> None:
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

    def _company_sync_key(self, company: dict | None) -> str | None:
        if not company:
            return None
        guid = (company.get("guid") or "").strip()
        if guid:
            return f"guid:{guid}"
        name = (company.get("name") or "").strip()
        if name:
            return f"name:{name.lower()}"
        return None

    def _mark_synced(self, kind: str = "sync", company: dict | None = None) -> None:
        stamp = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")
        self.store.set_meta("last_sync_at", stamp)
        self.store.set_meta("last_sync_kind", kind)
        key = self._company_sync_key(company)
        if not key and self.tally:
            try:
                key = self._company_sync_key(self.tally.company_info())
            except Exception:
                key = None
        if key:
            self.store.set_meta(f"last_sync_at_{key}", stamp)
            self.store.set_meta(f"last_sync_kind_{key}", kind)

    def _company_last_sync(self, company: dict) -> tuple[str, str]:
        key = self._company_sync_key(company)
        if not key:
            return "", "sync"
        stamp = self.store.get_meta(f"last_sync_at_{key}") or ""
        kind = self.store.get_meta(f"last_sync_kind_{key}") or "sync"
        # Migrate legacy single last_sync onto the first known company once.
        if not stamp:
            legacy = self.store.get_meta("last_sync_at") or ""
            if legacy and not self.store.get_meta("last_sync_migrated"):
                stamp = legacy
                kind = self.store.get_meta("last_sync_kind") or "sync"
                self.store.set_meta(f"last_sync_at_{key}", stamp)
                self.store.set_meta(f"last_sync_kind_{key}", kind)
                self.store.set_meta("last_sync_migrated", True)
        return stamp, kind

    def status_detail(self) -> dict:
        health = self.tally.health()
        last_sync = self.store.get_meta("last_sync_at") or ""
        last_kind = self.store.get_meta("last_sync_kind") or "sync"
        companies_out: list[dict] = []
        for company in health.get("companies") or []:
            stamp, kind = self._company_last_sync(company)
            companies_out.append(
                {
                    "name": company.get("name") or "—",
                    "guid": company.get("guid") or "",
                    "gstin": company.get("gstin") or "",
                    "last_sync_at": stamp,
                    "last_sync_display": stamp or "Never",
                    "last_sync_kind": kind,
                }
            )
        tally_label = (
            f"{len(companies_out)} companies"
            if len(companies_out) > 1
            else (health.get("company") if health.get("ok") else (health.get("error") or "offline"))
        )
        return {
            "version": __version__,
            "tally": tally_label,
            "tally_ok": bool(health.get("ok")),
            "companies": companies_out,
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
            download = info.get("asset_url") or info.get("release_url")
            if info.get("update_available") and download:
                webbrowser.open(download)
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

    def _company_scheduler_loop(self):
        while not self._tray_stop.is_set():
            try:
                self.scheduled_tick()
            except Exception as exc:
                self._progress(f"Sync check failed: {exc}")
            self._tray_stop.wait(30)

    def run(self) -> None:
        if PRODUCT_ID == "pluschwood":
            # Check per-company due times and re-import requests on each scheduler tick.
            threading.Thread(target=self._heartbeat_loop, name="tally-heartbeat", daemon=True).start()
            threading.Thread(target=self._company_scheduler_loop, name="tally-company-sync", daemon=True).start()
        else:
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
