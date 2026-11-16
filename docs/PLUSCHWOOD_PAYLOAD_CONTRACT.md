# Pluschwood Tally import payload contract

Contract version: `pluschwood_tally_v2`

The Windows agent posts JSON batches to `POST /api/integrations/tally/import` with header `X-Tally-Installation-Token`.

## Batch envelope

```json
{
  "phase": "masters",
  "master_type": "Ledger",
  "contract_version": "pluschwood_tally_v2",
  "company": {"name": "PLUSCHWOOD INDUSTRIES", "guid": "5b7e1f37-..."},
  "from_date": "2024-04-01",
  "to_date": "2026-03-31",
  "masters": [],
  "vouchers": [],
  "done": false
}
```

Phases: `company`, `masters`, `parties`, `vouchers`, `complete`.

Missing values are JSON `null` (or omitted). Do not treat missing as zero.

## Stable identity

- Company: `company.guid`, `company.name`
- Masters/vouchers/parties: `stable_id` / `guid` from Tally
- Use these IDs to upsert; do not key only on voucher number

## Ledger masters (chart of accounts)

`phase: "masters"` + `master_type: "Ledger"` still sends **all** ledgers (sales, tax, bank, parties, etc.) for accounting sync.

Party classification on each ledger:

- `party_role` / `oms_entity`: `customer` if under **Sundry Debtors** (including nested groups)
- `party_role` / `oms_entity`: `vendor` if under **Sundry Creditors** (including nested groups)
- otherwise `party_role` is `null` (not an OMS party)

Legacy note: older agents used `supplier` for creditors; treat `supplier` as `vendor`.

## Parties phase (OMS customers / vendors)

After ledger masters, the agent sends a dedicated batch for OMS mapping:

```json
{
  "phase": "parties",
  "contract_version": "pluschwood_tally_v2",
  "company": {"name": "PLUSCHWOOD INDUSTRIES", "guid": "5b7e1f37-..."},
  "masters": [],
  "vouchers": [],
  "parties": [
    {
      "stable_id": "co-guid-0001-ledger-acme",
      "guid": "co-guid-0001-ledger-acme",
      "alter_id": 12,
      "name": "Acme Motors",
      "parent": "Sundry Debtors",
      "party_role": "customer",
      "oms_entity": "customer",
      "contact_name": null,
      "phone": "9999999999",
      "email": "accounts@acme.example",
      "pan": "ABCDE1234F",
      "gstin": "29ABCDE1234F1Z5",
      "state": "Karnataka",
      "addresses": [
        {
          "kind": "billing",
          "lines": ["Peenya Industrial Area", "Bengaluru"],
          "state": "Karnataka",
          "pincode": "560058",
          "country": "India"
        }
      ],
      "gst_registrations": [
        {
          "applicable_from": "2024-04-01",
          "registration_type": "Regular",
          "gstin": "29ABCDE1234F1Z5",
          "state": "Karnataka",
          "place_of_supply": "Karnataka"
        }
      ],
      "banking": {
        "account_holder": "Acme Motors",
        "bank_name": "HDFC Bank",
        "branch": "Peenya",
        "account_number": "REDACTED",
        "ifsc": "HDFC0001234"
      },
      "cancelled": false,
      "deleted": false
    },
    {
      "stable_id": "co-guid-0001-ledger-board",
      "guid": "co-guid-0001-ledger-board",
      "alter_id": 18,
      "name": "Board Mills",
      "parent": "Sundry Creditors",
      "party_role": "vendor",
      "oms_entity": "vendor",
      "gstin": "33AACCZ6291R1ZI",
      "cancelled": false,
      "deleted": false
    }
  ],
  "done": false
}
```

OMS should upsert:

| `oms_entity` / `party_role` | OMS record |
| --- | --- |
| `customer` | Customer |
| `vendor` (or legacy `supplier`) | Vendor |

Match on `(company.guid, party.guid/stable_id)` first; fall back to `(company.guid, name)` only when migrating.

Banking is included only for Pluschwood destinations over HTTPS. It must not appear in logs, diagnostics, or fixtures committed to git.

## Stock item

```json
{
  "stable_id": "co-guid-0001-stock-box",
  "guid": "co-guid-0001-stock-box",
  "alter_id": 44,
  "name": "Corrugated Box 12x10",
  "parent": "Primary",
  "unit": "NOS",
  "hsn": "4819",
  "gst_rates": [
    {"applicable_from": "2024-04-01", "state": "Any", "duty_head": "IGST", "rate": "18"}
  ]
}
```

## Sales / Purchase voucher

```json
{
  "stable_id": "co-guid-0001-vch-sale-1",
  "guid": "co-guid-0001-vch-sale-1",
  "alter_id": 120,
  "voucher_number": "INV-100",
  "voucher_type": "Sales",
  "voucher_type_base": "Sales",
  "date": "2025-04-12",
  "party_ledger_id": null,
  "party_name": "Acme Motors",
  "amount": "-1463.20",
  "inventory_lines": [
    {
      "item_name": "Corrugated Box 12x10",
      "quantity": "100",
      "unit": "NOS",
      "rate": "10.00",
      "discount": "0",
      "amount": "1000.00",
      "is_deemed_positive": null
    }
  ],
  "ledger_entries": [
    {
      "ledger_name": "Acme Motors",
      "amount": "-1463.20",
      "is_deemed_positive": "Yes",
      "bill_allocations": [
        {"bill_name": "INV-100", "bill_type": "New Ref", "amount": "-1463.20", "ledger_name": "Acme Motors"}
      ]
    }
  ],
  "bill_allocations": [
    {"bill_name": "INV-100", "bill_type": "New Ref", "amount": "-1463.20", "ledger_name": "Acme Motors"}
  ],
  "cancelled": false,
  "deleted": false
}
```

Custom voucher types are included when their Tally parent/base type is Sales, Purchase, Receipt, or Payment.
Journal / Contra / Credit Note / Debit Note / Delivery Note / Receipt Note / Stock Journal are also collected when present (`base_type` / `voucher_type_base` set); the console may skip projecting them into trade records.

For Payment / Receipt, Tally **Account** is the bank/cash ledger and **Particulars** are party / expense / tax lines. When Account is bank/cash and Particulars has exactly one non-tax, non-round-off ledger, the agent sets `party_name` to that Particulars ledger (even if `PARTYLEDGERNAME` was the bank). GST remittance vouchers (bank → CGST/SGST/IGST only) are still sent without inventing a trade party.

## Receipt / Payment voucher

```json
{
  "stable_id": "co-guid-0001-vch-rcpt-1",
  "voucher_number": "RCPT-7",
  "voucher_type": "Receipt",
  "voucher_type_base": "Receipt",
  "date": "2025-04-15",
  "party_name": "Acme Motors",
  "amount": "1463.20",
  "ledger_entries": [
    {
      "ledger_name": "Acme Motors",
      "amount": "1463.20",
      "is_deemed_positive": "No",
      "bill_allocations": [
        {"bill_name": "INV-100", "bill_type": "Agst Ref", "amount": "1000.00", "ledger_name": "Acme Motors"},
        {"bill_name": null, "bill_type": "On Account", "amount": "463.20", "ledger_name": "Acme Motors"}
      ]
    },
    {
      "ledger_name": "HDFC Bank",
      "amount": "-1463.20",
      "is_deemed_positive": "Yes",
      "bill_allocations": []
    }
  ],
  "bill_allocations": [
    {"bill_name": "INV-100", "bill_type": "Agst Ref", "amount": "1000.00", "ledger_name": "Acme Motors"},
    {"bill_name": null, "bill_type": "On Account", "amount": "463.20", "ledger_name": "Acme Motors"}
  ]
}
```

A voucher number alone is not enough to allocate a receipt/payment. Prefer `bill_allocations[].bill_name` + `bill_type` + signed `amount`.

## Compatibility

Older receivers can ignore new array fields and keep using `guid`, `alter_id`, `name`, `voucher_number`, `voucher_type`, `date`, `party_name`, `amount`, `cancelled`, and `deleted`.

## Install and full re-import

1. Install the agent (see root `README.md`) and open Tally with the target company loaded.
2. Tray → **Sign in to connect…** (browser login). Pairing codes remain a fallback via **Enter pairing code…**.
3. Optionally set `TALLY_IMPORT_FROM_DATE` / `TALLY_IMPORT_TO_DATE`.
4. Tray → **Run initial import** — Pluschwood replays from AlterID 0; other destinations keep their cursors.
5. Confirm the complete-phase summary: master counts, voucher counts by base type, and any zero-Purchase warning.

## Outbound (Pluschwood → Tally)

Timber installations: after inbound, the agent polls `GET /api/integrations/tally/outbound?limit=50`, writes `entity_type` `sales` / `receipt` using the feed `mapping` (required; no guessed ledger names), then `POST /api/integrations/tally/acknowledge` with `status` `ok` or `error`. See root README bidirectional section.

## Live gaps

- Tally voucher XML does not embed a party ledger GUID; `party_ledger_id` is usually `null` and Pluschwood should join on `party_name` ↔ ledger `stable_id`/`name` after masters import.
- Stock-item HSN may live under `HSNDETAILS.LIST` (parsed) while invoice lines carry `GSTHSNNAME`.
- Purchase vouchers are exported when present; a company with none yields a warning, not an error.
