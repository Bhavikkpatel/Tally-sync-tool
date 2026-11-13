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
            "html_url": "https://github.com/Bhavikkpatel/Tally-sync-tool/releases/tag/v1.2.0",
            "body": "Bug fixes",
            "assets": [
                {
                    "name": "TallySyncSetup-1.2.0.exe",
                    "browser_download_url": "https://example.com/TallySyncSetup-1.2.0.exe",
                }
            ],
        }
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = payload
        with patch("agent.updater.httpx.get", return_value=response), patch("agent.updater.__version__", "1.0.0"):
            info = check_for_update()
        self.assertTrue(info.update_available)
        self.assertEqual(info.latest_version, "1.2.0")
        self.assertEqual(info.asset_name, "TallySyncSetup-1.2.0.exe")


if __name__ == "__main__":
    unittest.main()
