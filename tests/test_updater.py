from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from agent.updater import check_for_update, is_newer


class UpdaterTests(unittest.TestCase):
    def test_is_newer(self):
        self.assertTrue(is_newer("1.0.1", "1.0.0"))
        self.assertTrue(is_newer("v2.0.0", "1.9.9"))
        self.assertFalse(is_newer("1.0.0", "1.0.0"))
        self.assertFalse(is_newer("1.0.0", "1.0.1"))

    def test_check_for_update_parses_release(self):
        payload = {
            "tag_name": "v1.2.0",
            "html_url": "https://example.com/releases/tag/v1.2.0",
            "body": "Bug fixes",
            "assets": [
                {
                    "name": "AutoSyncTallySyncSetup-1.2.0.exe",
                    "browser_download_url": "https://example.com/AutoSyncTallySyncSetup-1.2.0.exe",
                },
                {
                    "name": "PluschwoodTallySyncSetup-1.2.0.exe",
                    "browser_download_url": "https://example.com/PluschwoodTallySyncSetup-1.2.0.exe",
                },
            ],
        }
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = payload
        with patch("agent.updater.httpx.get", return_value=response), patch("agent.updater.__version__", "1.0.0"), patch(
            "agent.updater.PRODUCT_ID", "pluschwood"
        ):
            info = check_for_update()
        self.assertTrue(info.update_available)
        self.assertEqual(info.latest_version, "1.2.0")
        self.assertEqual(info.asset_name, "PluschwoodTallySyncSetup-1.2.0.exe")
        self.assertEqual(info.asset_url, "https://example.com/PluschwoodTallySyncSetup-1.2.0.exe")
        self.assertEqual(info.release_url, info.asset_url)

    def test_check_for_update_detects_newer_than_current(self):
        payload = {
            "tag_name": "v1.0.1",
            "html_url": "https://example.com/releases/tag/v1.0.1",
            "body": "Dual product builds",
            "assets": [
                {
                    "name": "PluschwoodTallySyncSetup-1.0.1.exe",
                    "browser_download_url": "https://example.com/PluschwoodTallySyncSetup-1.0.1.exe",
                },
                {
                    "name": "AutoSyncTallySyncSetup-1.0.1.exe",
                    "browser_download_url": "https://example.com/AutoSyncTallySyncSetup-1.0.1.exe",
                },
            ],
        }
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = payload
        with patch("agent.updater.httpx.get", return_value=response), patch("agent.updater.__version__", "1.0.0"), patch(
            "agent.updater.PRODUCT_ID", "autosync"
        ):
            info = check_for_update()
        self.assertTrue(info.update_available)
        self.assertEqual(info.latest_version, "1.0.1")
        self.assertEqual(info.asset_name, "AutoSyncTallySyncSetup-1.0.1.exe")
        self.assertEqual(info.message, "Update available")

    def test_check_for_update_latest_when_same_version(self):
        payload = {
            "tag_name": "v1.0.1",
            "html_url": "https://example.com/releases/tag/v1.0.1",
            "body": "",
            "assets": [
                {
                    "name": "PluschwoodTallySyncSetup-1.0.1.exe",
                    "browser_download_url": "https://example.com/PluschwoodTallySyncSetup-1.0.1.exe",
                }
            ],
        }
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = payload
        with patch("agent.updater.httpx.get", return_value=response), patch("agent.updater.__version__", "1.0.1"), patch(
            "agent.updater.PRODUCT_ID", "pluschwood"
        ):
            info = check_for_update()
        self.assertFalse(info.update_available)
        self.assertEqual(info.message, "You are on the latest version")


if __name__ == "__main__":
    unittest.main()
