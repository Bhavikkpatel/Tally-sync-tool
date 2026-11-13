from __future__ import annotations

import unittest
from pathlib import Path

from agent import tally_xml
from agent.outbound_runner import build_sales_payload_from_invoice


FIXTURES = Path(__file__).parent / "fixtures"


class TallyXmlTests(unittest.TestCase):
    def test_parse_companies_returns_all(self):
        xml = """
        <ENVELOPE><BODY><DATA><COLLECTION>
          <COMPANY NAME="Alpha Mills"><NAME>Alpha Mills</NAME><GUID>guid-a</GUID><GSTREGISTRATIONNUMBER>29AAAAA0000A1Z5</GSTREGISTRATIONNUMBER></COMPANY>
          <COMPANY NAME="Beta Timbers"><NAME>Beta Timbers</NAME><GUID>guid-b</GUID></COMPANY>
          <COMPANY NAME="12"><NAME>12</NAME><GUID>guid-num</GUID></COMPANY>
        </COLLECTION></DATA></BODY></ENVELOPE>
        """
        companies = tally_xml.parse_companies(xml)
        self.assertEqual([c["name"] for c in companies], ["Alpha Mills", "Beta Timbers"])
        self.assertEqual(companies[0]["guid"], "guid-a")
        self.assertEqual(companies[0]["gstin"], "29AAAAA0000A1Z5")
        info = tally_xml.parse_company_info(xml)
        self.assertEqual(info["name"], "Alpha Mills")

    def test_parse_ledgers(self):
        xml = (FIXTURES / "ledger_page.xml").read_text(encoding="utf-8")
        ledgers = tally_xml.parse_objects(xml, "LEDGER")
        self.assertEqual(len(ledgers), 2)
        self.assertEqual(ledgers[0]["name"], "Acme Motors")
        self.assertEqual(ledgers[0]["guid"], "led-acme-001")
        self.assertEqual(ledgers[0]["alter_id"], 12)
        self.assertEqual(ledgers[0]["gstin"], "29ABCDE1234F1Z5")

    def test_parse_stock_items(self):
        xml = (FIXTURES / "stock_item_page.xml").read_text(encoding="utf-8")
        items = tally_xml.parse_objects(xml, "STOCKITEM")
        self.assertEqual(items[0]["name"], "Corrugated Box 12x10")
        self.assertEqual(items[0]["hsn"], "4819")

    def test_parse_vouchers(self):
        xml = (FIXTURES / "voucher_page.xml").read_text(encoding="utf-8")
        vouchers = tally_xml.parse_objects(xml, "VOUCHER")
        self.assertEqual(len(vouchers), 2)
        self.assertEqual(vouchers[0]["voucher_number"], "INV-100")
        self.assertEqual(vouchers[0]["eway_bill"], "301234567890")
        self.assertEqual(vouchers[1]["irn"], "abcd1234irn")

    def test_parse_import_response(self):
        xml = (FIXTURES / "import_ok.xml").read_text(encoding="utf-8")
        result = tally_xml.parse_import_response(xml)
        self.assertEqual(result["created"], 1)
        self.assertEqual(result["errors"], 0)

    def test_sales_voucher_builder(self):
        payload = build_sales_payload_from_invoice(
            {
                "number": "INV-100",
                "invoice_date": "2026-04-01",
                "vehicle_no": "TN66AF7696",
                "lines": [
                    {
                        "description": "Corrugated Box 12x10",
                        "quantity": "100",
                        "rate": "10",
                        "amount": "1000",
                        "unit": "NOS",
                    }
                ],
                "totals": {"cgst": "90", "sgst": "90", "igst": "0", "total": "1180"},
            },
            "Acme Motors",
        )
        xml = tally_xml.sales_voucher_xml(
            payload,
            {
                "sales_voucher_type": "Sales",
                "sales_ledger": "Sales",
                "cgst_ledger": "CGST",
                "sgst_ledger": "SGST",
                "igst_ledger": "IGST",
            },
        )
        self.assertIn("<VOUCHERNUMBER>INV-100</VOUCHERNUMBER>", xml)
        self.assertIn("<STOCKITEMNAME>Corrugated Box 12x10</STOCKITEMNAME>", xml)
        self.assertIn("<LEDGERNAME>CGST</LEDGERNAME>", xml)
        self.assertIn("<BASICSHIPPEDBY>TN66AF7696</BASICSHIPPEDBY>", xml)

    def test_receipt_builder_allocates_against_invoice(self):
        xml = tally_xml.receipt_voucher_xml(
            {
                "id": 9,
                "number": "RCPT-9",
                "date": "2026-04-05",
                "amount": "1180",
                "party_name": "Acme Motors",
                "invoice_number": "INV-100",
            },
            {"receipt_ledger": "HDFC Bank"},
        )
        self.assertIn("<BILLTYPE>Agst Ref</BILLTYPE>", xml)
        self.assertIn("<NAME>INV-100</NAME>", xml)
        self.assertIn("<LEDGERNAME>HDFC Bank</LEDGERNAME>", xml)


if __name__ == "__main__":
    unittest.main()
