from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent.destinations import (
    import_done,
    list_destinations,
    normalize_base_url,
    set_import_done,
    upsert_destination,
)
from agent.security import save_token
from agent.storage import LocalStore


class DestinationTests(unittest.TestCase):
    def test_normalize_and_upsert(self):
        with tempfile.TemporaryDirectory() as folder:
            store = LocalStore(Path(folder) / "agent.sqlite3")
            self.assertEqual(normalize_base_url("console.pluschwood.com"), "https://console.pluschwood.com")
            first = upsert_destination(store, label="Pluschwood Console", base_url="https://console.pluschwood.com")
            second = upsert_destination(store, label="Pluschwood Console", base_url="https://console.pluschwood.com/")
            self.assertEqual(first.id, second.id)
            self.assertEqual(len(list_destinations(store)), 1)
            set_import_done(store, first.id, True)
            self.assertTrue(import_done(store, first.id))
            save_token(Path(folder) / f"destination-{first.id}.token", "secret-token")


if __name__ == "__main__":
    unittest.main()
