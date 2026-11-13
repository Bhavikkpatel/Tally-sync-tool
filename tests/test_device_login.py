from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from agent.autosync_client import AutoSyncClient, AutoSyncError
from agent.config import AgentConfig
from agent.destinations import Destination
from agent import destinations as destination_store
from agent.security import load_token
from agent.storage import LocalStore


class DeviceLoginTests(unittest.TestCase):
    def test_poll_device_token_pending_vs_ready(self):
        client = AutoSyncClient("https://console.pluschwood.com")
        with patch("agent.autosync_client.httpx.request") as request:
            pending = MagicMock()
            pending.status_code = 400
            pending.json.return_value = {"detail": {"error": "authorization_pending"}}
            pending.text = "pending"
            ready = MagicMock()
            ready.status_code = 200
            ready.content = b"{}"
            ready.json.return_value = {
                "installation_id": 9,
                "organization_id": 1,
                "installation_token": "secret-token",
                "mapping": {},
                "interval_hours": 6,
                "brand_id": 1,
            }
            request.side_effect = [pending, ready]
            self.assertIsNone(client.poll_device_token("device-code"))
            result = client.poll_device_token("device-code")
            self.assertEqual(result["installation_token"], "secret-token")

    def test_poll_device_token_raises_on_deny(self):
        client = AutoSyncClient("https://console.pluschwood.com")
        with patch("agent.autosync_client.httpx.request") as request:
            denied = MagicMock()
            denied.status_code = 401
            denied.json.return_value = {"detail": "Device authorization was denied."}
            denied.text = "denied"
            request.return_value = denied
            with self.assertRaises(AutoSyncError):
                client.poll_device_token("device-code")

    def test_sign_in_connect_saves_token_and_starts_import(self):
        from agent.__main__ import SyncApp

        with tempfile.TemporaryDirectory() as folder:
            data_dir = Path(folder)
            app = SyncApp.__new__(SyncApp)
            app.config = AgentConfig(data_dir=data_dir)
            app.store = LocalStore(data_dir / "agent.sqlite3")
            app.destination_label = "Pluschwood Console"
            app.destination_base_url = "https://console.pluschwood.com"
            app.tally = MagicMock()
            app.tally.health.return_value = {
                "ok": True,
                "company": "Demo Co",
                "companies": [{"guid": "co-1", "name": "Demo Co"}],
                "detail": {"guid": "co-1", "name": "Demo Co", "gstin": None},
            }
            import threading
            app._import_lock = threading.Lock()
            app.scheduler = MagicMock()
            app.last_message = ""
            app._progress = lambda message: None
            import_calls = []
            app.run_import = lambda force_destination_ids: import_calls.append(force_destination_ids)

            with patch("agent.__main__.webbrowser.open") as open_browser, patch(
                "agent.__main__.AutoSyncClient"
            ) as client_cls, patch("agent.__main__.time.sleep"):
                client = client_cls.return_value
                client.create_device_session.return_value = {
                    "device_code": "device-abc",
                    "user_code": "ABCD-EFGH",
                    "verification_uri_complete": "https://console.pluschwood.com/oms/settings/tally-sync/connect?user_code=ABCD-EFGH",
                    "interval": 1,
                }
                client.poll_device_token.return_value = {
                    "installation_id": 3,
                    "organization_id": 1,
                    "brand_id": 2,
                    "interval_hours": 3,
                    "installation_token": "install-token",
                    "mapping": {"sales_ledger": "Sales"},
                }
                app.sign_in_connect()

            open_browser.assert_called_once()
            destinations = destination_store.list_destinations(app.store)
            self.assertEqual(len(destinations), 1)
            token = load_token(destinations[0].token_path(data_dir))
            self.assertEqual(token, "install-token")
            self.assertEqual(import_calls, [{destinations[0].id}])
            self.assertEqual(app.store.get_meta("installation_id_console-pluschwood-com") or app.store.get_meta(
                f"installation_id_{destinations[0].id}"
            ), 3)


if __name__ == "__main__":
    unittest.main()
