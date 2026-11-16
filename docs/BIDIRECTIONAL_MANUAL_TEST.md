# Manual test notes — bidirectional Tally sync

Sandbox: open Tally company with HTTP on `127.0.0.1:9000`, Pluschwood agent paired to a Timber brand installation.

## Mapping

1. In console **Tally sync settings** (or agent **Ledger mapping…**), set all required fields including `receipt_ledger` to real ledger names in the company.
2. Save; confirm agent status shows mapping (or re-sync).

## Inbound

1. Create a Payment: Account = bank, Particulars = supplier with Agst Ref.
2. Sync / import. Console should show `party_name` = supplier (not the bank).
3. Create a GST remittance Payment: Bank → CGST + SGST only. Sync; voucher should upload and not stick pending on “Party master has not been linked” after console classify.
4. Confirm Sales / Purchase / Receipt / Cash Payment still import.

## Outbound sales

1. Complete a Pluschwood sales order with client + stock items already linked to Tally GUIDs.
2. Sync. Agent log should show outbound item(s); Tally should gain a Sales voucher.
3. Sync again — same `entity_id` must not reappear on `GET /outbound` after acknowledge.

## Outbound receipt

1. Record a customer receipt in Pluschwood against an exported order (or on account).
2. Sync. Receipt voucher in Tally must use `mapping.receipt_ledger` as Account and the customer as Particulars.
3. Force a bad `receipt_ledger` name → acknowledge `status: "error"`; console link shows error; do not mark exported.
