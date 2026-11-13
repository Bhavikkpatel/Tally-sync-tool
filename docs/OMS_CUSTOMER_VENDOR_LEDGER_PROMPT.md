# Prompt: Map Tally ledger parties → OMS customers & vendors

Use this prompt with the Pluschwood / AutoSync application codebase (backend + OMS UI).

---

## Goal

The Windows Tally Sync agent already exports:

1. **All ledgers** as `phase: "masters"`, `master_type: "Ledger"` (chart of accounts).
2. **Party ledgers only** as a separate `phase: "parties"` batch for OMS.

You must update the web app so `parties` upsert into **OMS Customers** and **OMS Vendors**.

## Contract (agent → API)

Endpoint (existing): `POST /api/integrations/tally/import`  
Auth: `X-Tally-Installation-Token`  
Contract: `pluschwood_tally_v2` (see `docs/PLUSCHWOOD_PAYLOAD_CONTRACT.md`).

### New / required phase

```json
{
  "phase": "parties",
  "contract_version": "pluschwood_tally_v2",
  "company": { "name": "…", "guid": "…" },
  "parties": [ /* party objects */ ],
  "masters": [],
  "vouchers": [],
  "done": false
}
```

### Party object (important fields)

- `stable_id` / `guid` — Tally ledger GUID (primary upsert key)
- `name` — ledger name
- `parent` — Tally group (often `Sundry Debtors` / `Sundry Creditors` or a nested subgroup)
- `party_role` / `oms_entity`:
  - `customer` → create/update **OMS Customer**
  - `vendor` → create/update **OMS Vendor**
  - also accept legacy `supplier` as **Vendor**
- Contact: `contact_name`, `phone`, `email`
- Tax: `pan`, `gstin`, `state`
- `addresses[]` — billing lines / state / pincode / country
- `gst_registrations[]` — GSTIN history
- `banking` — optional; HTTPS Pluschwood only; store securely; never log full account numbers
- `cancelled` / `deleted` — soft-disable the OMS party when true

## Backend tasks

1. **Import router**
   - Accept `phase == "parties"` (do not reject unknown phase).
   - Resolve installation → organization / brand / company from the token + `company.guid`.
   - Process `parties[]` in the same request transactionally where practical (or per-party upsert with clear errors).

2. **Upsert rules**
   - Key: `(tally_company_guid, tally_ledger_guid)` on Customer / Vendor.
   - If GUID missing (should not happen): fall back to `(tally_company_guid, normalized name)` and then write GUID when available.
   - Map fields:
     - name ← `name`
     - GSTIN ← `gstin` (or first `gst_registrations[].gstin`)
     - phone / email / PAN / state / addresses / banking as your schema allows
   - If `deleted` or `cancelled`: mark inactive / archived; do not hard-delete if invoices reference the party.

3. **Do not confuse with chart-of-accounts ledgers**
   - `masters` + `Ledger` may still create/update accounting ledger rows.
   - `parties` is the **OMS CRM/procurement** projection only (Customer / Vendor).
   - Prefer linking Customer/Vendor → Tally ledger GUID for later voucher party matching (`party_name` / future `party_ledger_id`).

4. **Idempotency**
   - Re-posting the same `alter_id`/payload must not create duplicates.
   - Return counts in the import response, e.g. `{ "customers_upserted": n, "vendors_upserted": m, "skipped": k }`.

5. **Validation**
   - Skip parties with empty `name` or empty `oms_entity`/`party_role`.
   - Unknown `oms_entity` → 400 with clear detail (do not fail the whole batch unless you already do that for masters).

6. **Multi-company**
   - One installation may send parties for multiple Tally companies over time; always scope by `company.guid`.

## OMS UI tasks

1. Customers / Vendors list: show **Tally sync** badge when `tally_ledger_guid` is set.
2. Detail page: show linked Tally ledger name/GUID, last sync time, GSTIN from Tally.
3. Optional filter: “Synced from Tally” / “Manual only”.
4. Prevent editing Tally-owned identity fields (name/GSTIN) if you treat Tally as source of truth — or show “Updated from Tally” and allow override with a clear flag.

## Acceptance tests

1. Post a `parties` batch with 1 customer + 1 vendor → both appear under the correct OMS company/org.
2. Re-post same GUIDs with changed phone → updates in place (no duplicate).
3. Nested Tally group under Sundry Debtors still maps to Customer (`parent` may not be exactly `Sundry Debtors`).
4. `oms_entity: "supplier"` still creates/updates a Vendor.
5. Voucher import later can resolve `party_name` to the synced Customer/Vendor.

## Out of scope

- Changing Tally agent export format beyond `pluschwood_tally_v2` parties phase (already shipped in the agent).
- Mapping non-party ledgers (Sales, CGST, Bank) to OMS customers/vendors.

---

Implement against the existing Tally device-session / installation import pipeline. Prefer extending the current import handler rather than a new public endpoint unless routing already splits by phase.
