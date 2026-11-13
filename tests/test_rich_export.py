from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from agent import destinations as destination_store
from agent import tally_xml
from agent.config import AgentConfig
from agent.destinations import Destination
from agent.import_runner import ImportRunner
from agent.storage import LocalStore
from agent.xml_sanitize import sanitize_xml


FIXTURES = Path(__file__).parent / "fixtures"


class RichExportTests(unittest.TestCase):
    def test_sanitize_strips_illegal_tally_char_refs(self):
        dirty = "<PARENT>&#4; Primary</PARENT><OK>&#10;keep</OK>"
        clean = sanitize_xml(dirty)
        self.assertNotIn("&#4;", clean)
        self.assertIn("&#10;", clean)

    def test_ledger_addresses_gst_and_banking_scope(self):
        xml = (FIXTURES / "rich_ledger.xml").read_text(encoding="utf-8")
        rich = tally_xml.parse_objects(xml, "LEDGER", rich=True, include_banking=True)
        customer = next(item for item in rich if item["name"] == "Acme Motors")
        self.assertEqual(customer["party_role"], "customer")
        self.assertEqual(customer["gstin"], "29ABCDE1234F1Z5")
        self.assertEqual(len(customer["addresses"]), 1)
        self.assertEqual(customer["addresses"][0]["lines"][0], "Peenya Industrial Area")
        self.assertEqual(customer["gst_registrations"][0]["registration_type"], "Regular")
        self.assertEqual(customer["banking"]["ifsc"], "HDFC0001234")

        lean = tally_xml.parse_objects(xml, "LEDGER", rich=False, include_banking=False)
        lean_customer = next(item for item in lean if item["name"] == "Acme Motors")
        self.assertNotIn("banking", lean_customer)
        self.assertNotIn("accountnumber", lean_customer["fields"])

    def test_stock_item_hsn_and_rates(self):
        xml = (FIXTURES / "rich_stock_item.xml").read_text(encoding="utf-8")
        items = tally_xml.parse_objects(xml, "STOCKITEM", rich=True)
        self.assertEqual(items[0]["hsn"], "4819")
        self.assertEqual(items[0]["unit"], "NOS")
        heads = {row["duty_head"] for row in items[0]["gst_rates"]}
        self.assertIn("IGST", heads)

        hsn_only = """
        <ENVELOPE><BODY><DATA><COLLECTION>
          <STOCKITEM NAME="Door">
            <GUID>g1</GUID><ALTERID>1</ALTERID><PARENT>Primary</PARENT><BASEUNITS>NOS</BASEUNITS>
            <GSTDETAILS.LIST><HSNCODE/></GSTDETAILS.LIST>
            <HSNDETAILS.LIST><HSNCODE>39211200</HSNCODE></HSNDETAILS.LIST>
          </STOCKITEM>
        </COLLECTION></DATA></BODY></ENVELOPE>
        """
        self.assertEqual(tally_xml.parse_objects(hsn_only, "STOCKITEM", rich=True)[0]["hsn"], "39211200")

    def test_vouchers_preserve_lines_allocations_and_purchase(self):
        xml = (FIXTURES / "rich_vouchers.xml").read_text(encoding="utf-8")
        bases = {"sales": "Sales", "purchase": "Purchase", "receipt": "Receipt", "payment": "Payment"}
        vouchers = tally_xml.parse_objects(xml, "VOUCHER", rich=True, voucher_type_bases=bases)
        sales = next(item for item in vouchers if item["voucher_number"] == "INV-100")
        self.assertEqual(sales["party_name"], "Acme Motors")
        self.assertEqual(sales["amount"], "-1463.20")
        self.assertEqual(len(sales["inventory_lines"]), 2)
        self.assertEqual(sales["inventory_lines"][0]["quantity"], "100")
        self.assertEqual(sales["inventory_lines"][0]["unit"], "NOS")
        self.assertEqual(sales["bill_allocations"][0]["bill_type"], "New Ref")

        purchase = next(item for item in vouchers if item["voucher_number"] == "PUR-10")
        self.assertEqual(purchase["voucher_type_base"], "Purchase")
        self.assertEqual(purchase["party_name"], "Board Mills")
        self.assertEqual(len(purchase["inventory_lines"]), 1)

        receipt = next(item for item in vouchers if item["voucher_number"] == "RCPT-7")
        self.assertEqual(len(receipt["bill_allocations"]), 2)
        self.assertEqual(receipt["bill_allocations"][0]["bill_name"], "INV-100")
        self.assertEqual(receipt["bill_allocations"][0]["bill_type"], "Agst Ref")
        self.assertEqual(receipt["bill_allocations"][1]["bill_type"], "On Account")
        self.assertIsNone(receipt["bill_allocations"][1]["bill_name"])

        payment = next(item for item in vouchers if item["voucher_number"] == "PAY-3")
        self.assertEqual(payment["ledger_entries"][0]["is_deemed_positive"], "Yes")
        self.assertEqual(payment["bill_allocations"][0]["bill_name"], "PUR-10")

    def test_pluschwood_reimport_does_not_reset_other_destination_cursor(self):
        with tempfile.TemporaryDirectory() as folder:
            store = LocalStore(Path(folder) / "agent.sqlite3")
            plus = Destination(id="pluschwood", label="Pluschwood Console", base_url="https://console.pluschwood.com")
            other = Destination(id="autosync", label="AutoSync", base_url="https://autosync.app")
            destination_store.save_destinations(store, [plus, other])
            destination_store.set_import_done(store, plus.id, True)
            destination_store.set_import_done(store, other.id, True)
            destination_store.set_cursor(store, plus.id, "voucher", 50)
            destination_store.set_cursor(store, other.id, "voucher", 50)

            tally = MagicMock()
            company = {"name": "Demo Co", "guid": "co-1", "gstin": None}
            tally.company_info.return_value = company
            tally.list_companies.return_value = [company]
            tally.export_voucher_type_bases.return_value = {
                "sales": "Sales",
                "purchase": "Purchase",
                "receipt": "Receipt",
                "payment": "Payment",
            }

            def export_collection(collection, **kwargs):
                if collection == "Voucher":
                    return []
                if collection == "VoucherType":
                    return [
                        {"name": "Sales", "voucher_type_base": "Sales", "alter_id": 1},
                        {"name": "Purchase", "voucher_type_base": "Purchase", "alter_id": 2},
                    ]
                return []

            tally.export_collection.side_effect = export_collection
            plus_client = MagicMock()
            other_client = MagicMock()
            config = AgentConfig(data_dir=Path(folder), import_page_size=50)
            ImportRunner(
                store,
                tally,
                [(plus, plus_client), (other, other_client)],
                config,
                force_destination_ids={plus.id},
            ).run(force=False)

            self.assertEqual(destination_store.get_cursor(store, other.id, "voucher"), 50)
            self.assertTrue(destination_store.import_done(store, other.id))
            self.assertTrue(destination_store.import_done(store, plus.id))
            self.assertTrue(plus_client.import_batch.called)
            self.assertFalse(other_client.import_batch.called)

    def test_cursor_advances_only_after_destination_accepts_batch(self):
        with tempfile.TemporaryDirectory() as folder:
            store = LocalStore(Path(folder) / "agent.sqlite3")
            plus = Destination(id="pluschwood", label="Pluschwood Console", base_url="https://console.pluschwood.com")
            destination_store.save_destinations(store, [plus])
            tally = MagicMock()
            company = {"name": "Demo Co", "guid": "co-1"}
            tally.company_info.return_value = company
            tally.list_companies.return_value = [company]
            tally.export_voucher_type_bases.return_value = {"sales": "Sales"}
            pages = {
                "Ledger": [
                    [{"guid": "l1", "alter_id": 5, "name": "Acme", "party_role": "customer"}],
                    [],
                ]
            }

            def export_collection(collection, **kwargs):
                if collection == "Ledger":
                    return pages["Ledger"].pop(0)
                return []

            tally.export_collection.side_effect = export_collection
            client = MagicMock()
            client.import_batch.side_effect = [None, RuntimeError("reject"), None]
            config = AgentConfig(data_dir=Path(folder), import_page_size=50)
            runner = ImportRunner(store, tally, [(plus, client)], config, force_destination_ids={plus.id})
            result = runner.run(force=False)
            self.assertEqual(result["destinations"][plus.id]["error"], "reject")
            self.assertEqual(destination_store.get_cursor(store, plus.id, "ledger", company_guid="co-1"), 0)

    def test_one_connection_imports_all_open_companies(self):
        with tempfile.TemporaryDirectory() as folder:
            data = Path(folder)
            store = LocalStore(data / "agent.sqlite3")
            dest = destination_store.upsert_destination(
                store,
                label="Pluschwood Console",
                base_url="https://console.pluschwood.com",
                destination_id="pluschwood",
            )
            destination_store.set_cursor(store, dest.id, "ledger", 27, company_guid="second")
            tally = MagicMock()
            tally.list_companies.return_value = [
                {"guid": "first", "name": "First Timber"},
                {"guid": "second", "name": "Second Timber"},
            ]
            tally.export_collection.return_value = []
            tally.export_voucher_type_bases.return_value = {}
            client = MagicMock()
            runner = ImportRunner(
                store,
                tally,
                [(dest, client)],
                AgentConfig(data_dir=data),
                force_destination_ids={dest.id},
            )
            result = runner.run(
                companies=[
                    {"guid": "first", "name": "First Timber"},
                    {"guid": "second", "name": "Second Timber"},
                ]
            )
            companies = result["destinations"][dest.id]["companies"]
            self.assertIn("first", companies)
            self.assertIn("second", companies)
            guids = [call.args[0]["company"]["guid"] for call in client.import_batch.call_args_list]
            self.assertIn("first", guids)
            self.assertIn("second", guids)
            # Force reset clears the second company ledger cursor.
            self.assertEqual(destination_store.get_cursor(store, dest.id, "ledger", company_guid="second"), 0)


if __name__ == "__main__":
    unittest.main()
