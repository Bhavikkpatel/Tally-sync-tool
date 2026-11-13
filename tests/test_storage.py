from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent.storage import LocalStore


class StorageTests(unittest.TestCase):
    def test_meta_and_outbound_queue(self):
        with tempfile.TemporaryDirectory() as folder:
            store = LocalStore(Path(folder) / "agent.sqlite3")
            store.set_meta("interval_hours", 3)
            self.assertEqual(store.get_meta("interval_hours"), 3)
            store.enqueue_outbound("customer", "1", {"name": "Acme"}, "hash-1")
            pending = store.pending_outbound()
            self.assertEqual(len(pending), 1)
            store.mark_outbound(pending[0]["id"], "ok")
            self.assertEqual(store.pending_outbound(), [])


if __name__ == "__main__":
    unittest.main()
