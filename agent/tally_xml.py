from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any
from xml.sax.saxutils import escape

from agent.xml_sanitize import sanitize_xml


MASTER_COLLECTIONS = (
    "Group",
    "Ledger",
    "Unit",
    "Godown",
    "StockGroup",
    "StockItem",
    "VoucherType",
)

LEDGER_FETCH = (
    "NAME, GUID, ALTERID, PARENT, LEDGERPHONE, PHONE, EMAIL, EMAILID, "
    "INCOMETAXNUMBER, PRIORSTATENAME, LEDGERCONTACT, CONTACTPERSON, "
    "LEDGSTREGDETAILS, ADDRESS, PINCODE, COUNTRYOFRESIDENCE, "
    "BANKDETAILS, BANKNAME, BRANCHNAME, ACCOUNTNUMBER, IFSCODE, BSRCODE, BENEFICIARYCODE"
)

STOCK_ITEM_FETCH = "NAME, GUID, ALTERID, PARENT, BASEUNITS, GSTDETAILS, HSNDETAILS, HSNCODE, GSTAPPLICABLE"

VOUCHER_TYPE_FETCH = "NAME, GUID, ALTERID, PARENT, NUMBERINGMETHOD, ISDEEMEDPOSITIVE, NORMALBALANCE"

VOUCHER_FETCH = (
    "DATE, VOUCHERTYPENAME, VOUCHERNUMBER, GUID, ALTERID, MASTERID, PARTYLEDGERNAME, "
    "PERSISTEDVIEW, ISCANCELLED, ISDELETED, ALLLEDGERENTRIES, LEDGERENTRIES, "
    "ALLINVENTORYENTRIES, INVENTORYENTRIES, BASICBUYERADDRESS, BASICSHIPPEDBY, "
    "IRN, BASICWAYBILLNO, REFERENCE, NARRATION, CURRENCYNAME, EXCHANGERATE"
)

VOUCHER_BASE_TYPES = {"sales", "purchase", "receipt", "payment"}
# Extra types Pluschwood accepts and ignores for trade projection (prefer send over drop).
EXTENDED_VOUCHER_BASES = VOUCHER_BASE_TYPES | {
    "journal",
    "contra",
    "credit note",
    "debit note",
    "delivery note",
    "receipt note",
    "stock journal",
}

_TAX_LEDGER_RE = re.compile(r"(?:\b|^)(cgst|sgst|igst|ugst|gst|vat|cess|tds|tcs)(?:\b|$)", re.I)
_ROUND_OFF_RE = re.compile(r"round\s*off|rounding", re.I)
_BANK_CASH_RE = re.compile(
    r"\b(bank|cash|petty\s*cash|cash[- ]?in[- ]?hand|od\s*a/?c|overdraft)\b",
    re.I,
)

BANKING_FIELD_KEYS = {
    "bankdetails",
    "bankname",
    "branchname",
    "accountnumber",
    "ifscode",
    "bsrcode",
    "beneficiarycode",
    "banking",
}


def _text(node: ET.Element | None, default: str | None = "") -> str | None:
    if node is None:
        return default
    if node.text is None:
        return default if default is None else default
    value = node.text.strip()
    if value == "":
        return default if default is None else default
    return value


def _child(node: ET.Element, *names: str) -> ET.Element | None:
    wanted = {name.upper() for name in names}
    for child in node:
        if child.tag.split("}")[-1].upper() in wanted:
            return child
    return None


def _attr(node: ET.Element, *names: str) -> str | None:
    for name in names:
        if name in node.attrib:
            value = (node.attrib[name] or "").strip()
            return value or None
        for key, value in node.attrib.items():
            if key.upper() == name.upper():
                text = (value or "").strip()
                return text or None
    return None


def _tag(node: ET.Element) -> str:
    return node.tag.split("}")[-1].upper()


def _direct_text(node: ET.Element, *names: str) -> str | None:
    wanted = {name.upper() for name in names}
    for child in list(node):
        if _tag(child) in wanted and not list(child):
            return _text(child, None)
    return None


def company_info_request() -> str:
    return """
<ENVELOPE>
 <HEADER>
  <VERSION>1</VERSION>
  <TALLYREQUEST>Export</TALLYREQUEST>
  <TYPE>Collection</TYPE>
  <ID>AutoSyncCompany</ID>
 </HEADER>
 <BODY>
  <DESC>
   <STATICVARIABLES>
    <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
   </STATICVARIABLES>
   <TDL>
    <TDLMESSAGE>
     <COLLECTION NAME="AutoSyncCompany" ISMODIFY="No" ISFIXED="No" ISINITIALIZE="Yes" ISOPTION="No" ISINTERNAL="No">
      <TYPE>Company</TYPE>
      <FETCH>NAME, GUID, STATENAME, COMPANYNUMBER, INCOMETAXNUMBER, GSTREGISTRATIONNUMBER, ADDRESS</FETCH>
     </COLLECTION>
    </TDLMESSAGE>
   </TDL>
  </DESC>
 </BODY>
</ENVELOPE>
""".strip()


def default_fetch_for(collection: str) -> str | None:
    key = collection.lower()
    if key == "ledger":
        return LEDGER_FETCH
    if key == "stockitem":
        return STOCK_ITEM_FETCH
    if key == "vouchertype":
        return VOUCHER_TYPE_FETCH
    if key == "voucher":
        return VOUCHER_FETCH
    return "NAME, GUID, ALTERID, PARENT"


def collection_request(
    collection: str,
    *,
    from_alter_id: int | None = None,
    page_size: int = 200,
    fetch: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    company_name: str | None = None,
) -> str:
    fetch_value = fetch if fetch is not None else default_fetch_for(collection)
    fetch_xml = f"<FETCH>{escape(fetch_value)}</FETCH>" if fetch_value else ""
    filters_xml = ""
    formula_xml = ""
    if from_alter_id is not None:
        filters_xml = "<FILTERS>AlterIdFilter</FILTERS>"
        formula_xml = (
            f'<SYSTEM TYPE="Formulae" NAME="AlterIdFilter">'
            f"$AlterID &gt; {int(from_alter_id)}</SYSTEM>"
        )
    static = ["<SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>"]
    if company_name:
        static.append(f"<SVCURRENTCOMPANY>{escape(company_name)}</SVCURRENTCOMPANY>")
    if from_date:
        static.append(f'<SVFROMDATE TYPE="Date">{escape(_tally_date(from_date))}</SVFROMDATE>')
    if to_date:
        static.append(f'<SVTODATE TYPE="Date">{escape(_tally_date(to_date))}</SVTODATE>')
    collection_id = f"AutoSync{collection}"
    return f"""
<ENVELOPE>
 <HEADER>
  <VERSION>1</VERSION>
  <TALLYREQUEST>Export</TALLYREQUEST>
  <TYPE>Collection</TYPE>
  <ID>{escape(collection_id)}</ID>
 </HEADER>
 <BODY>
  <DESC>
   <STATICVARIABLES>
    {''.join(static)}
   </STATICVARIABLES>
   <TDL>
    <TDLMESSAGE>
     <COLLECTION NAME="{escape(collection_id)}" ISMODIFY="No" ISFIXED="No" ISINITIALIZE="No" ISOPTION="No" ISINTERNAL="No">
      <TYPE>{escape(collection)}</TYPE>
      {fetch_xml}
      {filters_xml}
     </COLLECTION>
     {formula_xml}
    </TDLMESSAGE>
   </TDL>
  </DESC>
 </BODY>
</ENVELOPE>
""".strip()


def _tally_date(value: str) -> str:
    text = (value or "").strip()
    if re.fullmatch(r"\d{8}", text):
        return text
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return text.replace("-", "")
    return text


def iso_date(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    if re.fullmatch(r"\d{8}", text):
        return f"{text[0:4]}-{text[4:6]}-{text[6:8]}"
    return text


def import_envelope(objects_xml: str) -> str:
    return f"""
<ENVELOPE>
 <HEADER>
  <VERSION>1</VERSION>
  <TALLYREQUEST>Import</TALLYREQUEST>
  <TYPE>Data</TYPE>
  <ID>All Masters</ID>
 </HEADER>
 <BODY>
  <DESC>
   <STATICVARIABLES>
    <SVIMPORTDUPS>@@DUPCOMBINE</SVIMPORTDUPS>
   </STATICVARIABLES>
  </DESC>
  <DATA>
   <TALLYMESSAGE>
{objects_xml}
   </TALLYMESSAGE>
  </DATA>
 </BODY>
</ENVELOPE>
""".strip()


def ledger_xml(payload: dict) -> str:
    name = escape(payload["name"])
    parent = escape(payload.get("parent") or "Sundry Debtors")
    gstin = escape(payload.get("gstin") or "")
    state = escape(payload.get("state") or "")
    address = escape(payload.get("address") or "")
    return f"""
<LEDGER NAME="{name}" ACTION="Alter" RESERVEDNAME="">
 <NAME.LIST>
  <NAME>{name}</NAME>
 </NAME.LIST>
 <PARENT>{parent}</PARENT>
 <LEDGERPHONENUMBER>{escape(payload.get("phone") or "")}</LEDGERPHONENUMBER>
 <EMAIL>{escape(payload.get("email") or "")}</EMAIL>
 <LEDGSTREGDETAILS.LIST>
  <APPLICABLEFROM>20240401</APPLICABLEFROM>
  <GSTREGISTRATIONTYPE>Regular</GSTREGISTRATIONTYPE>
  <GSTIN>{gstin}</GSTIN>
  <STATE>{state}</STATE>
 </LEDGSTREGDETAILS.LIST>
 <ADDRESS.LIST>
  <ADDRESS>{address}</ADDRESS>
 </ADDRESS.LIST>
</LEDGER>
""".strip()


def unit_xml(name: str) -> str:
    safe = escape(name)
    return f"""
<UNIT NAME="{safe}" ACTION="Create">
 <NAME>{safe}</NAME>
 <ISSIMPLEUNIT>Yes</ISSIMPLEUNIT>
</UNIT>
""".strip()


def stock_item_xml(payload: dict) -> str:
    name = escape(payload["name"])
    parent = escape(payload.get("parent") or "Primary")
    unit = escape(payload.get("unit") or "NOS")
    hsn = escape(payload.get("hsn") or "")
    rate = escape(str(payload.get("rate") or "0"))
    gst = escape(str(payload.get("gst_rate") or "18"))
    return f"""
<STOCKITEM NAME="{name}" ACTION="Alter">
 <NAME.LIST>
  <NAME>{name}</NAME>
 </NAME.LIST>
 <PARENT>{parent}</PARENT>
 <BASEUNITS>{unit}</BASEUNITS>
 <GSTAPPLICABLE>&#xb;&#xb;Applicable</GSTAPPLICABLE>
 <GSTDETAILS.LIST>
  <APPLICABLEFROM>20240401</APPLICABLEFROM>
  <HSNCODE>{hsn}</HSNCODE>
  <TAXABILITY>Taxable</TAXABILITY>
  <GSTNATUREOFTRANSACTION>Sales Taxable</GSTNATUREOFTRANSACTION>
  <STATEWISEDETAILS.LIST>
   <STATEENAME>&#xb;&#xb;Any</STATEENAME>
   <RATEDETAILS.LIST>
    <GSTRATEDUTYHEAD>CGST</GSTRATEDUTYHEAD>
    <GSTRATE>{gst}</GSTRATE>
   </RATEDETAILS.LIST>
   <RATEDETAILS.LIST>
    <GSTRATEDUTYHEAD>SGST/UTGST</GSTRATEDUTYHEAD>
    <GSTRATE>{gst}</GSTRATE>
   </RATEDETAILS.LIST>
   <RATEDETAILS.LIST>
    <GSTRATEDUTYHEAD>IGST</GSTRATEDUTYHEAD>
    <GSTRATE>{gst}</GSTRATE>
   </RATEDETAILS.LIST>
  </STATEWISEDETAILS.LIST>
 </GSTDETAILS.LIST>
 <STANDARDPRICELIST.LIST>
  <DATE>20240401</DATE>
  <RATE>{rate}/{unit}</RATE>
 </STANDARDPRICELIST.LIST>
</STOCKITEM>
""".strip()


def _require_mapping(mapping: dict, *keys: str) -> dict[str, str]:
    missing = [key for key in keys if not str(mapping.get(key) or "").strip()]
    if missing:
        raise ValueError(f"Ledger mapping incomplete: missing {', '.join(missing)}")
    return {key: str(mapping[key]).strip() for key in keys}


def _nonzero_amount(value: Any) -> bool:
    if value in {None, ""}:
        return False
    try:
        return float(value) != 0
    except (TypeError, ValueError):
        return True


def normalize_timber_sales_payload(payload: dict) -> dict:
    """Map Pluschwood Timber outbound sales payload → sales_voucher_xml shape."""
    lines = []
    for line in payload.get("lines") or []:
        lines.append(
            {
                "item_name": line.get("item_name") or line.get("description") or "Goods",
                "quantity": line.get("quantity") if line.get("quantity") not in {None, ""} else "1",
                "rate": line.get("rate") if line.get("rate") not in {None, ""} else (line.get("amount") or "0"),
                "amount": line.get("amount") or "0",
                "unit": line.get("unit") or "NOS",
                "hsn": line.get("hsn") or "",
            }
        )
    return {
        "number": payload.get("voucher_number") or payload.get("number"),
        "date": payload.get("date"),
        "party_name": payload.get("party_name"),
        "lines": lines,
        "cgst": payload.get("cgst_amount") if payload.get("cgst_amount") is not None else payload.get("cgst", "0"),
        "sgst": payload.get("sgst_amount") if payload.get("sgst_amount") is not None else payload.get("sgst", "0"),
        "igst": payload.get("igst_amount") if payload.get("igst_amount") is not None else payload.get("igst", "0"),
        "round_off": payload.get("charges") or payload.get("round_off") or "0",
        "total": payload.get("amount") or payload.get("total") or "0",
        "vehicle_no": payload.get("vehicle_no") or "",
        "delivery_address": payload.get("delivery_address") or "",
        "narration": payload.get("bill_reference") or payload.get("narration") or "",
    }


def sales_voucher_xml(payload: dict, mapping: dict) -> str:
    required = _require_mapping(
        mapping,
        "sales_voucher_type",
        "sales_ledger",
        "cgst_ledger",
        "sgst_ledger",
        "igst_ledger",
        "round_off_ledger",
    )
    party_name = payload.get("party_name")
    number = payload.get("number") or payload.get("voucher_number")
    if not party_name or not number or not payload.get("date"):
        raise ValueError("Sales payload requires party_name, number/voucher_number, and date")
    party = escape(str(party_name))
    number_esc = escape(str(number))
    date = escape(str(payload["date"]).replace("-", ""))
    voucher_type = escape(required["sales_voucher_type"])
    sales_ledger = escape(required["sales_ledger"])
    cgst_ledger = escape(required["cgst_ledger"])
    sgst_ledger = escape(required["sgst_ledger"])
    igst_ledger = escape(required["igst_ledger"])
    round_off_ledger = escape(required["round_off_ledger"])
    vehicle = escape(payload.get("vehicle_no") or "")
    delivery = escape(payload.get("delivery_address") or "")
    narration = escape(payload.get("narration") or "")
    inventory_lines = []
    for line in payload.get("lines") or []:
        item_name = line.get("item_name") or line.get("description")
        if not item_name:
            raise ValueError("Sales line missing item_name")
        unit = line.get("unit") or "NOS"
        qty = line.get("quantity") if line.get("quantity") not in {None, ""} else "1"
        rate = line.get("rate") if line.get("rate") not in {None, ""} else (line.get("amount") or "0")
        amount = line.get("amount") or "0"
        inventory_lines.append(
            f"""
  <ALLINVENTORYENTRIES.LIST>
   <STOCKITEMNAME>{escape(str(item_name))}</STOCKITEMNAME>
   <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
   <RATE>{escape(str(rate))}/{escape(str(unit))}</RATE>
   <AMOUNT>{escape(str(amount))}</AMOUNT>
   <ACTUALQTY>{escape(str(qty))} {escape(str(unit))}</ACTUALQTY>
   <BILLEDQTY>{escape(str(qty))} {escape(str(unit))}</BILLEDQTY>
   <ACCOUNTINGALLOCATIONS.LIST>
    <LEDGERNAME>{sales_ledger}</LEDGERNAME>
    <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
    <AMOUNT>{escape(str(amount))}</AMOUNT>
   </ACCOUNTINGALLOCATIONS.LIST>
  </ALLINVENTORYENTRIES.LIST>
""".strip()
        )
    if not inventory_lines:
        raise ValueError("Sales payload has no inventory lines")
    tax_lines = []
    for ledger, amount in (
        (cgst_ledger, payload.get("cgst") or "0"),
        (sgst_ledger, payload.get("sgst") or "0"),
        (igst_ledger, payload.get("igst") or "0"),
        (round_off_ledger, payload.get("round_off") or "0"),
    ):
        if not _nonzero_amount(amount):
            continue
        tax_lines.append(
            f"""
  <LEDGERENTRIES.LIST>
   <LEDGERNAME>{ledger}</LEDGERNAME>
   <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
   <AMOUNT>{escape(str(amount))}</AMOUNT>
  </LEDGERENTRIES.LIST>
""".strip()
        )
    party_amount = escape(str(payload.get("total") or payload.get("amount") or "0"))
    return f"""
<VOUCHER VCHTYPE="{voucher_type}" ACTION="Alter" OBJVIEW="Invoice Voucher View">
 <DATE>{date}</DATE>
 <VOUCHERTYPENAME>{voucher_type}</VOUCHERTYPENAME>
 <VOUCHERNUMBER>{number_esc}</VOUCHERNUMBER>
 <REFERENCE>{number_esc}</REFERENCE>
 <NARRATION>{narration}</NARRATION>
 <PARTYLEDGERNAME>{party}</PARTYLEDGERNAME>
 <BASICBASEPARTYNAME>{party}</BASICBASEPARTYNAME>
 <PERSISTEDVIEW>Invoice Voucher View</PERSISTEDVIEW>
 <BASICBUYERADDRESS.LIST>
  <BASICBUYERADDRESS>{delivery}</BASICBUYERADDRESS>
 </BASICBUYERADDRESS.LIST>
 <BASICSHIPPEDBY>{vehicle}</BASICSHIPPEDBY>
 <LEDGERENTRIES.LIST>
  <LEDGERNAME>{party}</LEDGERNAME>
  <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
  <AMOUNT>-{party_amount}</AMOUNT>
  <BILLALLOCATIONS.LIST>
   <NAME>{number_esc}</NAME>
   <BILLTYPE>New Ref</BILLTYPE>
   <AMOUNT>-{party_amount}</AMOUNT>
  </BILLALLOCATIONS.LIST>
 </LEDGERENTRIES.LIST>
 {chr(10).join(inventory_lines)}
 {chr(10).join(tax_lines)}
</VOUCHER>
""".strip()


def _receipt_bill_type(allocation_type: str | None) -> str:
    kind = (allocation_type or "").strip().lower()
    if kind in {"against_reference", "agst ref", "against"}:
        return "Agst Ref"
    if kind in {"advance"}:
        return "Advance"
    return "On Account"


def receipt_voucher_xml(payload: dict, mapping: dict) -> str:
    required = _require_mapping(mapping, "receipt_ledger")
    party_name = payload.get("party_name")
    if not party_name or payload.get("date") is None or payload.get("amount") is None:
        raise ValueError("Receipt payload requires party_name, date, and amount")
    party = escape(str(party_name))
    number = escape(str(payload.get("number") or payload.get("voucher_number") or f"RCPT-{payload.get('id') or 'X'}"))
    date = escape(str(payload["date"]).replace("-", ""))
    amount = escape(str(payload["amount"]))
    bank = escape(required["receipt_ledger"])
    allocations = list(payload.get("allocations") or [])
    if not allocations and payload.get("invoice_number"):
        allocations = [
            {
                "type": "against_reference",
                "bill_name": payload.get("invoice_number"),
                "amount": payload.get("amount"),
            }
        ]
    allocation_xml = []
    for row in allocations:
        bill_type = _receipt_bill_type(row.get("type") or row.get("bill_type"))
        bill_name = row.get("bill_name") or row.get("invoice_number") or row.get("voucher_number") or ""
        row_amount = row.get("amount")
        if row_amount in {None, ""}:
            continue
        # Party credit side on Receipt uses positive amount in BILLALLOCATIONS.
        name_xml = f"<NAME>{escape(str(bill_name))}</NAME>" if bill_name else "<NAME></NAME>"
        allocation_xml.append(
            f"""
  <BILLALLOCATIONS.LIST>
   {name_xml}
   <BILLTYPE>{bill_type}</BILLTYPE>
   <AMOUNT>{escape(str(row_amount))}</AMOUNT>
  </BILLALLOCATIONS.LIST>
""".strip()
        )
    return f"""
<VOUCHER VCHTYPE="Receipt" ACTION="Alter" OBJVIEW="Accounting Voucher View">
 <DATE>{date}</DATE>
 <VOUCHERTYPENAME>Receipt</VOUCHERTYPENAME>
 <VOUCHERNUMBER>{number}</VOUCHERNUMBER>
 <PARTYLEDGERNAME>{party}</PARTYLEDGERNAME>
 <LEDGERENTRIES.LIST>
  <LEDGERNAME>{party}</LEDGERNAME>
  <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
  <AMOUNT>{amount}</AMOUNT>
  {chr(10).join(allocation_xml)}
 </LEDGERENTRIES.LIST>
 <LEDGERENTRIES.LIST>
  <LEDGERNAME>{bank}</LEDGERNAME>
  <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
  <AMOUNT>-{amount}</AMOUNT>
 </LEDGERENTRIES.LIST>
</VOUCHER>
""".strip()


def classify_ledger_role(name: str | None) -> str:
    text = (name or "").strip()
    if not text:
        return "other"
    if _ROUND_OFF_RE.search(text):
        return "round_off"
    if _TAX_LEDGER_RE.search(text):
        return "tax"
    if _BANK_CASH_RE.search(text):
        return "bank_cash"
    return "other"


def resolve_payment_receipt_party(
    ledger_entries: list[dict[str, Any]],
    declared_party: str | None,
    base_type: str | None,
) -> tuple[str | None, Any]:
    """
    Payment/Receipt: Account = bank/cash, Particulars = party/expense/tax.
    Prefer the single non-tax, non-round-off Particulars ledger when Account is bank/cash.
    """
    base = (base_type or "").strip().lower()
    if base not in {"payment", "receipt"}:
        return declared_party, None
    bankish = [entry for entry in ledger_entries if classify_ledger_role(entry.get("ledger_name")) == "bank_cash"]
    particulars = [
        entry
        for entry in ledger_entries
        if classify_ledger_role(entry.get("ledger_name")) == "other"
    ]
    if bankish and len(particulars) == 1:
        return particulars[0].get("ledger_name"), None
    if declared_party and classify_ledger_role(declared_party) == "bank_cash" and len(particulars) == 1:
        return particulars[0].get("ledger_name"), None
    return declared_party, None


def parse_objects(
    xml_text: str,
    tag: str,
    *,
    rich: bool = False,
    include_banking: bool = False,
    voucher_type_bases: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    root = ET.fromstring(sanitize_xml(xml_text))
    results = []
    for node in root.iter():
        if _tag(node) != tag.upper():
            continue
        # Skip CMPINFO count nodes like <COMPANY>0</COMPANY>
        if not list(node) and (node.text or "").strip().isdigit():
            continue
        guid = _direct_text(node, "GUID") or _attr(node, "GUID")
        alter_raw = _direct_text(node, "ALTERID", "AlterID") or "0"
        name = _attr(node, "NAME") or _direct_text(node, "NAME")
        cancelled = (_direct_text(node, "ISCANCELLED") or "").lower() in {"yes", "true", "1"}
        deleted = _attr(node, "ACTION") == "DELETE" or (_direct_text(node, "ISDELETED") or "").lower() in {
            "yes",
            "true",
            "1",
        }
        fields = _flatten(node)
        payload: dict[str, Any] = {
            "guid": guid or f"{tag}:{name}:{alter_raw}",
            "stable_id": guid or f"{tag}:{name}:{alter_raw}",
            "alter_id": int(re.sub(r"\D", "", alter_raw or "0") or "0"),
            "name": name,
            "cancelled": cancelled,
            "deleted": deleted,
            "fields": fields,
        }
        if tag.upper() == "LEDGER":
            payload.update(_ledger_fields(node, fields, include_banking=include_banking))
        elif tag.upper() == "STOCKITEM":
            payload.update(_stock_item_fields(node, fields))
        elif tag.upper() == "VOUCHERTYPE":
            payload.update(_voucher_type_fields(node, fields))
        elif tag.upper() == "VOUCHER":
            payload.update(_voucher_fields(node, fields, voucher_type_bases=voucher_type_bases or {}))
        if not include_banking:
            payload = strip_banking(payload)
        if not rich:
            payload.pop("gst_registrations", None)
            payload.pop("addresses", None)
            payload.pop("inventory_lines", None)
            payload.pop("ledger_entries", None)
            payload.pop("bill_allocations", None)
            payload.pop("gst_rates", None)
            payload.pop("banking", None)
        results.append(payload)
    return results


def strip_banking(payload: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(payload)
    cleaned.pop("banking", None)
    fields = dict(cleaned.get("fields") or {})
    for key in list(fields):
        if key.lower() in BANKING_FIELD_KEYS or any(part in key.lower() for part in ("accountnumber", "ifscode", "bankname")):
            fields.pop(key, None)
    cleaned["fields"] = fields
    return cleaned


def _flatten(node: ET.Element, prefix: str = "") -> dict[str, Any]:
    data: dict[str, Any] = {}
    for child in list(node):
        key = f"{prefix}{_tag(child)}".lower()
        children = list(child)
        if children:
            if _tag(child).endswith(".LIST"):
                continue
            nested = _flatten(child, f"{key}.")
            for nested_key, value in nested.items():
                data.setdefault(nested_key, value)
        else:
            text = _text(child, None)
            if text is not None:
                data[key] = text
    return data


def _list_children(node: ET.Element, *names: str) -> list[ET.Element]:
    wanted = {name.upper() for name in names}
    return [child for child in list(node) if _tag(child) in wanted]


def group_parent_map(groups: list[dict[str, Any]]) -> dict[str, str]:
    """Map group name (lower) → immediate parent name for party-role ancestry."""
    mapping: dict[str, str] = {}
    for item in groups or []:
        name = (item.get("name") or "").strip()
        if not name:
            continue
        parent = (item.get("parent") or (item.get("fields") or {}).get("parent") or "").strip()
        mapping[name.lower()] = parent
    return mapping


def resolve_party_role(parent: str | None, group_parents: dict[str, str] | None = None) -> str | None:
    """
    Map Tally ledger groups to OMS entities.
    - under Sundry Debtors → customer
    - under Sundry Creditors → vendor
    Walks nested groups when group_parents is provided.
    """
    current = (parent or "").strip()
    seen: set[str] = set()
    for _ in range(24):
        if not current:
            return None
        key = current.lower()
        if key in seen:
            break
        seen.add(key)
        if "sundry debtor" in key or key in {"debtors", "customer", "customers"}:
            return "customer"
        if "sundry creditor" in key or key in {"creditors", "supplier", "suppliers", "vendor", "vendors"}:
            return "vendor"
        if not group_parents:
            break
        current = (group_parents.get(key) or "").strip()
    return None


def enrich_party_roles(ledgers: list[dict[str, Any]], group_parents: dict[str, str] | None = None) -> list[dict[str, Any]]:
    for item in ledgers or []:
        parent = item.get("parent") or (item.get("fields") or {}).get("parent")
        role = resolve_party_role(parent, group_parents)
        item["party_role"] = role
        if role:
            item["oms_entity"] = role  # customer | vendor
        else:
            item.pop("oms_entity", None)
    return ledgers


def party_payload(ledger: dict[str, Any]) -> dict[str, Any]:
    """Strip chart-of-accounts noise; keep fields OMS needs for customers/vendors."""
    role = ledger.get("party_role") or ledger.get("oms_entity")
    payload = {
        "stable_id": ledger.get("stable_id") or ledger.get("guid"),
        "guid": ledger.get("guid"),
        "alter_id": ledger.get("alter_id"),
        "name": ledger.get("name"),
        "parent": ledger.get("parent"),
        "party_role": role,
        "oms_entity": role,
        "contact_name": ledger.get("contact_name"),
        "phone": ledger.get("phone"),
        "email": ledger.get("email"),
        "pan": ledger.get("pan"),
        "gstin": ledger.get("gstin"),
        "state": ledger.get("state"),
        "addresses": ledger.get("addresses") or [],
        "gst_registrations": ledger.get("gst_registrations") or [],
        "banking": ledger.get("banking"),
        "cancelled": bool(ledger.get("cancelled")),
        "deleted": bool(ledger.get("deleted")),
    }
    if not payload.get("banking"):
        payload.pop("banking", None)
    return payload


def _ledger_fields(node: ET.Element, fields: dict[str, Any], *, include_banking: bool) -> dict[str, Any]:
    parent = _direct_text(node, "PARENT") or fields.get("parent")
    role = resolve_party_role(parent)
    addresses = []
    for block in _list_children(node, "ADDRESS.LIST"):
        lines = [_text(item, None) for item in list(block) if _tag(item) == "ADDRESS"]
        lines = [line for line in lines if line]
        if lines:
            addresses.append(
                {
                    "kind": "billing",
                    "lines": lines,
                    "state": _direct_text(node, "PRIORSTATENAME"),
                    "pincode": _direct_text(node, "PINCODE"),
                    "country": _direct_text(node, "COUNTRYOFRESIDENCE"),
                }
            )
    gst_registrations = []
    for block in _list_children(node, "LEDGSTREGDETAILS.LIST"):
        gst_registrations.append(
            {
                "applicable_from": iso_date(_direct_text(block, "APPLICABLEFROM")),
                "registration_type": _direct_text(block, "GSTREGISTRATIONTYPE"),
                "gstin": _direct_text(block, "GSTIN"),
                "state": _direct_text(block, "STATE") or _direct_text(block, "PLACEOFSUPPLY"),
                "place_of_supply": _direct_text(block, "PLACEOFSUPPLY"),
            }
        )
    banking = None
    if include_banking:
        banking = {
            "account_holder": _direct_text(node, "BENEFICIARYCODE") or _attr(node, "NAME"),
            "bank_name": _direct_text(node, "BANKNAME") or fields.get("bankdetails"),
            "branch": _direct_text(node, "BRANCHNAME"),
            "account_number": _direct_text(node, "ACCOUNTNUMBER"),
            "ifsc": _direct_text(node, "IFSCODE"),
        }
        if not any(banking.get(key) for key in ("bank_name", "account_number", "ifsc", "branch")):
            banking = None
    payload = {
        "parent": parent,
        "party_role": role,
        "contact_name": _direct_text(node, "LEDGERCONTACT", "CONTACTPERSON"),
        "phone": _direct_text(node, "LEDGERPHONE", "PHONE", "LEDGERPHONENUMBER"),
        "email": _direct_text(node, "EMAIL", "EMAILID"),
        "pan": _direct_text(node, "INCOMETAXNUMBER"),
        "state": _direct_text(node, "PRIORSTATENAME"),
        "gstin": next((item.get("gstin") for item in gst_registrations if item.get("gstin")), None),
        "addresses": addresses,
        "gst_registrations": gst_registrations,
        "banking": banking,
    }
    if role:
        payload["oms_entity"] = role
    return payload


def _stock_item_fields(node: ET.Element, fields: dict[str, Any]) -> dict[str, Any]:
    gst_rates = []
    hsn = _direct_text(node, "HSNCODE")
    for details in _list_children(node, "GSTDETAILS.LIST"):
        hsn = hsn or _direct_text(details, "HSNCODE", "HSN")
        applicable_from = iso_date(_direct_text(details, "APPLICABLEFROM"))
        for state in _list_children(details, "STATEWISEDETAILS.LIST"):
            for rate in _list_children(state, "RATEDETAILS.LIST"):
                gst_rates.append(
                    {
                        "applicable_from": applicable_from,
                        "state": _direct_text(state, "STATENAME", "STATEENAME"),
                        "duty_head": _direct_text(rate, "GSTRATEDUTYHEAD"),
                        "rate": _direct_text(rate, "GSTRATE"),
                    }
                )
    # TallyPrime often stores the working HSN under HSNDETAILS.LIST, with empty HSNCODE on GSTDETAILS.
    for details in _list_children(node, "HSNDETAILS.LIST"):
        hsn = hsn or _direct_text(details, "HSNCODE", "HSN")
    return {
        "parent": _direct_text(node, "PARENT") or fields.get("parent"),
        "unit": _direct_text(node, "BASEUNITS"),
        "hsn": hsn,
        "gst_rates": gst_rates,
    }


def _voucher_type_fields(node: ET.Element, fields: dict[str, Any]) -> dict[str, Any]:
    parent = _direct_text(node, "PARENT") or fields.get("parent")
    base = None
    if parent:
        base = parent.strip()
    elif (_attr(node, "NAME") or "").strip().lower() in VOUCHER_BASE_TYPES:
        base = _attr(node, "NAME")
    return {"parent": parent, "voucher_type_base": base}


def _split_qty(value: str | None) -> tuple[str | None, str | None]:
    if value is None:
        return None, None
    text = value.strip()
    if not text:
        return None, None
    match = re.match(r"^([+-]?\d+(?:\.\d+)?)\s*(.*)$", text)
    if not match:
        return text, None
    quantity, unit = match.group(1), (match.group(2) or "").strip() or None
    return quantity, unit


def _split_rate(value: str | None) -> tuple[str | None, str | None]:
    if value is None:
        return None, None
    text = value.strip()
    if not text:
        return None, None
    if "/" in text:
        amount, unit = text.split("/", 1)
        return amount.strip() or None, unit.strip() or None
    return text, None


def _voucher_fields(
    node: ET.Element,
    fields: dict[str, Any],
    *,
    voucher_type_bases: dict[str, str],
) -> dict[str, Any]:
    voucher_type = _direct_text(node, "VOUCHERTYPENAME") or _attr(node, "VCHTYPE")
    base = None
    if voucher_type:
        base = voucher_type_bases.get(voucher_type.strip().lower()) or (
            voucher_type if voucher_type.strip().lower() in VOUCHER_BASE_TYPES else None
        )
    inventory_lines = []
    for entry in _list_children(node, "ALLINVENTORYENTRIES.LIST", "INVENTORYENTRIES.LIST"):
        qty_text = _direct_text(entry, "BILLEDQTY") or _direct_text(entry, "ACTUALQTY")
        quantity, qty_unit = _split_qty(qty_text)
        rate_text = _direct_text(entry, "RATE")
        rate, rate_unit = _split_rate(rate_text)
        item_name = _direct_text(entry, "STOCKITEMNAME")
        if item_name is None and quantity is None and _direct_text(entry, "AMOUNT") is None:
            continue
        inventory_lines.append(
            {
                "item_name": item_name,
                "description": _direct_text(entry, "NARRATION") or item_name,
                "quantity": quantity,
                "unit": qty_unit or rate_unit,
                "rate": rate,
                "discount": _direct_text(entry, "DISCOUNT"),
                "amount": _direct_text(entry, "AMOUNT"),
                "hsn": _direct_text(entry, "GSTHSNNAME", "HSNCODE"),
                "godown": _direct_text(entry, "GODOWNNAME"),
                "is_deemed_positive": _direct_text(entry, "ISDEEMEDPOSITIVE"),
            }
        )
    ledger_entries = []
    bill_allocations = []
    party_amount = None
    for entry in _list_children(node, "ALLLEDGERENTRIES.LIST", "LEDGERENTRIES.LIST"):
        ledger_name = _direct_text(entry, "LEDGERNAME")
        amount = _direct_text(entry, "AMOUNT")
        deemed = _direct_text(entry, "ISDEEMEDPOSITIVE")
        allocations = []
        for bill in _list_children(entry, "BILLALLOCATIONS.LIST"):
            allocation = {
                "bill_name": _direct_text(bill, "NAME"),
                "bill_type": _direct_text(bill, "BILLTYPE"),
                "amount": _direct_text(bill, "AMOUNT"),
                "ledger_name": ledger_name,
            }
            if allocation["bill_name"] is None and allocation["bill_type"] is None and allocation["amount"] is None:
                continue
            allocations.append(allocation)
            bill_allocations.append(allocation)
        if ledger_name is None and amount is None:
            continue
        ledger_entries.append(
            {
                "ledger_name": ledger_name,
                "amount": amount,
                "is_deemed_positive": deemed,
                "bill_allocations": allocations,
            }
        )
        declared = _direct_text(node, "PARTYLEDGERNAME")
        if declared and ledger_name == declared and amount is not None:
            party_amount = amount
    declared_party = _direct_text(node, "PARTYLEDGERNAME")
    party_name, party_ledger_id = resolve_payment_receipt_party(ledger_entries, declared_party, base)
    if party_name and party_name != declared_party:
        for entry in ledger_entries:
            if entry.get("ledger_name") == party_name and entry.get("amount") is not None:
                party_amount = entry["amount"]
                break
    if party_amount is None:
        for entry in ledger_entries:
            if entry.get("amount") is not None:
                party_amount = entry["amount"]
                break
    return {
        "voucher_number": _direct_text(node, "VOUCHERNUMBER"),
        "voucher_type": voucher_type,
        "voucher_type_base": base,
        "base_type": base,
        "date": iso_date(_direct_text(node, "DATE")),
        "party_ledger_id": party_ledger_id,  # Tally voucher XML exposes party by name; Pluschwood joins on ledger masters.
        "party_name": party_name,
        "amount": party_amount,
        "currency": _direct_text(node, "CURRENCYNAME") or "INR",
        "reference": _direct_text(node, "REFERENCE"),
        "narration": _direct_text(node, "NARRATION"),
        "irn": _direct_text(node, "IRN"),
        "eway_bill": _direct_text(node, "BASICWAYBILLNO"),
        "master_id": _direct_text(node, "MASTERID"),
        "inventory_lines": inventory_lines,
        "ledger_entries": ledger_entries,
        "bill_allocations": bill_allocations,
    }


def parse_import_response(xml_text: str) -> dict[str, Any]:
    created = re.findall(r"<CREATED>(\d+)</CREATED>", xml_text, flags=re.I)
    altered = re.findall(r"<ALTERED>(\d+)</ALTERED>", xml_text, flags=re.I)
    errors = re.findall(r"<ERRORS>(\d+)</ERRORS>", xml_text, flags=re.I)
    line_errors = re.findall(r"<LINEERROR>(.*?)</LINEERROR>", xml_text, flags=re.I | re.S)
    return {
        "created": int(created[-1]) if created else 0,
        "altered": int(altered[-1]) if altered else 0,
        "errors": int(errors[-1]) if errors else 0,
        "messages": [item.strip() for item in line_errors if item.strip()],
        "raw": xml_text,
    }


def _company_from_object(item: dict[str, Any]) -> dict[str, Any]:
    fields = item.get("fields") or {}
    return {
        "name": item.get("name") or fields.get("name"),
        "guid": item.get("guid") or fields.get("guid"),
        "gstin": (
            fields.get("gstregistrationnumber")
            or fields.get("companynumber")
            or fields.get("gstin")
            or fields.get("incometaxnumber")
        ),
        "state": fields.get("statename") or fields.get("priorstatename") or fields.get("state"),
        "address": fields.get("address"),
        "raw": item,
    }


def parse_companies(xml_text: str) -> list[dict[str, Any]]:
    """Return every company Tally reports (open/loaded companies)."""
    objects = [
        item
        for item in parse_objects(xml_text, "COMPANY", rich=True)
        if (item.get("name") or "").strip() and not str(item.get("name")).isdigit()
    ]
    if objects:
        seen: set[str] = set()
        companies: list[dict[str, Any]] = []
        for item in objects:
            company = _company_from_object(item)
            key = (company.get("guid") or company.get("name") or "").strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            companies.append(company)
        return companies
    root = ET.fromstring(sanitize_xml(xml_text))
    name = None
    for node in root.iter():
        if _tag(node) == "COMPANY":
            attr = _attr(node, "NAME")
            if attr and not attr.isdigit():
                name = attr
                break
        if _tag(node) in {"COMPANYNAME", "NAME"}:
            text = _text(node, None)
            if text and not text.isdigit():
                name = text
                break
    if name:
        return [{"name": name, "guid": None, "gstin": None, "state": None, "address": None, "raw_xml": xml_text}]
    return []


def parse_company_info(xml_text: str) -> dict[str, Any]:
    companies = parse_companies(xml_text)
    if companies:
        return companies[0]
    return {"name": None, "guid": None, "gstin": None, "state": None, "address": None, "raw_xml": xml_text}


def voucher_type_base_map(voucher_types: list[dict[str, Any]]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for item in voucher_types:
        name = (item.get("name") or "").strip()
        if not name:
            continue
        parent = (item.get("voucher_type_base") or item.get("parent") or "").strip()
        if parent.lower() in VOUCHER_BASE_TYPES:
            mapping[name.lower()] = parent
        elif name.lower() in VOUCHER_BASE_TYPES:
            mapping[name.lower()] = name
    return mapping
