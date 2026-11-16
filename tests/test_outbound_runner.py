from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from agent.outbound_runner import OutboundRunner
from agent.storage import LocalStore


COMPLETE_MAPPING = {
    "sales_voucher_type": "Sales",
    "sales_ledger": "Sales",
    "cgst_ledger": "CGST",
    "sgst_ledger": "SGST",
    "igst_ledger": "IGST",
    "round_off_ledger": "Round Off",
    "receipt_ledger": "HDFC Bank Ltd",
}


class OutboundRunnerTests(unittest.TestCase):
    def _runner(self, store, tally, client):
        return OutboundRunner(store, tally, client)

    def test_sales_and_receipt_write_and_acknowledge(self):
        with tempfile.TemporaryDirectory() as folder:
            store = LocalStore(Path(folder) / "agent.sqlite3")
            tally = MagicMock()
            tally.import_objects.return_value = {"created": 1, "altered": 0, "errors": 0, "messages": []}
            tally.find_voucher_by_reference.return_value = {
                "guid": "tv-sale-1",
                "voucher_number": "PI-100",
            }
            tally.export_collection.return_value = []
            client = MagicMock()
            client.outbound_feed.return_value = {
                "mapping": COMPLETE_MAPPING,
                "items": [
                    {
                        "entity_type": "sales",
                        "entity_id": "123",
                        "action": "create",
                        "payload": {
                            "voucher_number": "PI-100",
                            "date": "2026-11-01",
                            "party_name": "Acme Motors",
                            "amount": "1180.00",
                            "cgst_amount": "90.00",
                            "sgst_amount": "90.00",
                            "igst_amount": "0",
                            "lines": [
                                {
                                    "item_name": "Teak Plank",
                                    "quantity": "10",
                                    "unit": "NOS",
                                    "rate": "100",
                                    "amount": "1000",
                                }
                            ],
                        },
                    },
                    {
                        "entity_type": "receipt",
                        "entity_id": "45",
                        "action": "create",
                        "payload": {
                            "voucher_number": "RC-45",
                            "date": "2026-11-02",
                            "party_name": "Acme Motors",
                            "amount": "500.00",
                            "allocations": [
                                {"type": "against_reference", "bill_name": "PI-100", "amount": "500.00"}
                            ],
                        },
                    },
                ],
            }
            summary = self._runner(store, tally, client).run()
            self.assertEqual(summary["pushed"], 2)
            self.assertEqual(summary["failed"], 0)
            client.acknowledge.assert_called_once()
            acks = client.acknowledge.call_args[0][0]
            self.assertEqual(acks[0]["status"], "ok")
            self.assertEqual(acks[0]["entity_type"], "sales")
            self.assertEqual(acks[0]["tally_guid"], "tv-sale-1")
            self.assertEqual(acks[1]["entity_type"], "receipt")
            self.assertEqual(acks[1]["status"], "ok")
            self.assertEqual(tally.import_objects.call_count, 2)

    def test_incomplete_mapping_acknowledges_error(self):
        with tempfile.TemporaryDirectory() as folder:
            store = LocalStore(Path(folder) / "agent.sqlite3")
            tally = MagicMock()
            client = MagicMock()
            client.outbound_feed.return_value = {
                "mapping": {"sales_voucher_type": "Sales"},
                "items": [{"entity_type": "sales", "entity_id": "1", "payload": {"voucher_number": "X"}}],
            }
            summary = self._runner(store, tally, client).run()
            self.assertEqual(summary["failed"], 1)
            acks = client.acknowledge.call_args[0][0]
            self.assertEqual(acks[0]["status"], "error")
            self.assertIn("mapping incomplete", acks[0]["error"].lower())
            tally.import_objects.assert_not_called()

    def test_idempotent_skip_on_second_run(self):
        with tempfile.TemporaryDirectory() as folder:
            store = LocalStore(Path(folder) / "agent.sqlite3")
            store.set_meta(
                "outbound_written_sales_99",
                {"tally_guid": "existing-guid", "tally_name": "PI-99"},
            )
            tally = MagicMock()
            client = MagicMock()
            client.outbound_feed.return_value = {
                "mapping": COMPLETE_MAPPING,
                "items": [
                    {
                        "entity_type": "sales",
                        "entity_id": "99",
                        "payload": {"voucher_number": "PI-99", "party_name": "A", "date": "2026-01-01", "lines": []},
                    }
                ],
            }
            summary = self._runner(store, tally, client).run()
            self.assertEqual(summary["skipped"], 1)
            tally.import_objects.assert_not_called()
            acks = client.acknowledge.call_args[0][0]
            self.assertEqual(acks[0]["tally_guid"], "existing-guid")
            self.assertEqual(acks[0]["status"], "ok")

    def test_outbound_disabled_does_not_write_or_acknowledge(self):
        with tempfile.TemporaryDirectory() as folder:
            store = LocalStore(Path(folder) / "agent.sqlite3")
            tally = MagicMock()
            client = MagicMock()
            client.outbound_feed.return_value = {
                "outbound_enabled": False,
                "inbound_enabled": True,
                "mapping": COMPLETE_MAPPING,
                "items": [],
            }
            summary = self._runner(store, tally, client).run()
            self.assertTrue(summary["paused"])
            tally.import_objects.assert_not_called()
            client.acknowledge.assert_not_called()


if __name__ == "__main__":
    unittest.main()
