from __future__ import annotations

from typing import Any, Callable

from agent import tally_xml
from agent.autosync_client import AutoSyncClient, SyncPaused
from agent.storage import LocalStore
from agent.tally_client import TallyClient, TallyError


ProgressCallback = Callable[[str], None]


REQUIRED_MAPPING = (
    "sales_voucher_type",
    "sales_ledger",
    "cgst_ledger",
    "sgst_ledger",
    "igst_ledger",
    "round_off_ledger",
    "receipt_ledger",
)

class OutboundRunner:
    def __init__(
        self,
        store: LocalStore,
        tally: TallyClient,
        autosync: AutoSyncClient,
        on_progress: ProgressCallback | None = None,
    ):
        self.store = store
        self.tally = tally
        self.autosync = autosync
        self.on_progress = on_progress or (lambda _message: None)

    def mapping_ready(self, mapping: dict | None = None) -> bool:
        data = mapping if mapping is not None else (self.store.get_meta("ledger_mapping") or {})
        return all(str(data.get(key) or "").strip() for key in REQUIRED_MAPPING)

    def run(self) -> dict[str, Any]:
        run_id = self.store.begin_run("outbound")
        acknowledgements: list[dict] = []
        summary = {"pushed": 0, "failed": 0, "skipped": 0}

        try:
            feed = self.autosync.outbound_feed(limit=50)
            if feed.get("outbound_enabled") is False:
                self.on_progress("Outbound sync is paused for this connection")
                summary["paused"] = True
                self.store.set_meta("last_outbound_summary", summary)
                self.store.finish_run(run_id, "ok", summary)
                return summary
            items = feed.get("items") or []
            feed_mapping = feed.get("mapping") or {}
            if feed_mapping:
                self.store.set_meta("ledger_mapping", feed_mapping)
            mapping = {**(self.store.get_meta("ledger_mapping") or {}), **feed_mapping}
            self.on_progress(f"Outbound feed: {len(items)} item(s)")

            if items and not self.mapping_ready(mapping):
                missing = [key for key in REQUIRED_MAPPING if not str(mapping.get(key) or "").strip()]
                reason = f"Ledger mapping incomplete: missing {', '.join(missing)}"
                for item in items:
                    acknowledgements.append(self._error_ack(item, reason))
                    summary["failed"] += 1
                self.autosync.acknowledge(acknowledgements)
                self.store.set_meta("last_outbound_summary", summary)
                self.store.finish_run(run_id, "failed", {"error": reason, **summary})
                return summary

            for item in items:
                entity_type = str(item.get("entity_type") or "").strip()
                entity_id = str(item.get("entity_id") or "").strip()
                payload = item.get("payload") or {}
                try:
                    prior = self._prior_write(entity_type, entity_id)
                    if prior and prior.get("tally_guid"):
                        acknowledgements.append(
                            {
                                "entity_type": entity_type,
                                "entity_id": entity_id,
                                "status": "ok",
                                "tally_guid": prior.get("tally_guid"),
                                "tally_name": prior.get("tally_name"),
                                "payload": payload,
                            }
                        )
                        summary["skipped"] += 1
                        continue
                    result = self._push_one(entity_type, payload, mapping, item.get("tally_guid"))
                    tally_guid = result.get("guid") or item.get("tally_guid")
                    tally_name = result.get("tally_name") or payload.get("voucher_number") or payload.get("number")
                    self._remember_write(entity_type, entity_id, tally_guid, tally_name)
                    acknowledgements.append(
                        {
                            "entity_type": entity_type,
                            "entity_id": entity_id,
                            "status": "ok",
                            "tally_guid": tally_guid,
                            "tally_name": tally_name,
                            "payload": payload,
                        }
                    )
                    summary["pushed"] += 1
                except Exception as exc:
                    summary["failed"] += 1
                    acknowledgements.append(self._error_ack(item, str(exc)))

            if acknowledgements:
                try:
                    self.autosync.acknowledge(acknowledgements)
                except SyncPaused as exc:
                    self.on_progress(str(exc))
                    summary["paused"] = True
                    self.store.set_meta("last_outbound_summary", summary)
                    self.store.finish_run(run_id, "ok", summary)
                    return summary
            self.store.set_meta("last_outbound_summary", summary)
            self.store.finish_run(run_id, "ok" if summary["failed"] == 0 else "partial", summary)
            return summary
        except Exception as exc:
            self.store.finish_run(run_id, "failed", {"error": str(exc), **summary})
            raise

    def _error_ack(self, item: dict, error: str) -> dict:
        return {
            "entity_type": item.get("entity_type"),
            "entity_id": str(item.get("entity_id") or ""),
            "status": "error",
            "error": error,
            "tally_guid": item.get("tally_guid"),
        }

    def _prior_key(self, entity_type: str, entity_id: str) -> str:
        return f"outbound_written_{entity_type}_{entity_id}"

    def _prior_write(self, entity_type: str, entity_id: str) -> dict | None:
        if not entity_type or not entity_id:
            return None
        value = self.store.get_meta(self._prior_key(entity_type, entity_id))
        return value if isinstance(value, dict) else None

    def _remember_write(
        self,
        entity_type: str,
        entity_id: str,
        tally_guid: str | None,
        tally_name: str | None,
    ) -> None:
        if not entity_type or not entity_id:
            return
        self.store.set_meta(
            self._prior_key(entity_type, entity_id),
            {"tally_guid": tally_guid, "tally_name": tally_name},
        )

    def _push_one(
        self,
        entity_type: str,
        payload: dict,
        mapping: dict,
        existing_guid: str | None,
    ) -> dict:
        kind = entity_type.strip().lower()

        # Legacy AutoSync entity types kept for dual-product builds.
        if kind == "customer":
            xml = tally_xml.ledger_xml(payload)
            result = self.tally.import_objects(xml)
            return {"guid": existing_guid or payload.get("name"), "result": result, "tally_name": payload.get("name")}

        if kind == "stock_item":
            unit = payload.get("unit") or "NOS"
            try:
                self.tally.import_objects(tally_xml.unit_xml(unit))
            except TallyError:
                pass
            result = self.tally.import_objects(tally_xml.stock_item_xml(payload))
            return {"guid": existing_guid or payload.get("name"), "result": result, "tally_name": payload.get("name")}

        if kind in {"sales", "sales_invoice"}:
            return self._push_sales(payload, mapping, existing_guid)

        if kind == "receipt":
            return self._push_receipt(payload, mapping, existing_guid)

        raise ValueError(f"Unsupported outbound entity type: {entity_type}")

    def _push_sales(self, payload: dict, mapping: dict, existing_guid: str | None) -> dict:
        if not self.mapping_ready(mapping):
            missing = [key for key in REQUIRED_MAPPING if not str(mapping.get(key) or "").strip()]
            raise ValueError(f"Ledger mapping incomplete: missing {', '.join(missing)}")
        sales = (
            tally_xml.normalize_timber_sales_payload(payload)
            if payload.get("voucher_number") or payload.get("lines")
            else payload
        )
        # Packaging-shaped payloads already use number/lines/cgst; Timber uses voucher_number.
        if not sales.get("number"):
            sales = tally_xml.normalize_timber_sales_payload(payload)
        number = sales.get("number")
        voucher = None
        if existing_guid:
            voucher = self._voucher_by_guid(existing_guid)
        if voucher is None and number:
            voucher = self.tally.find_voucher_by_reference(str(number))
        if voucher and (voucher.get("irn") or "").strip():
            raise ConflictError(
                f"Invoice {number} already has an IRN in Tally and cannot be altered"
            )
        result = self.tally.import_objects(tally_xml.sales_voucher_xml(sales, mapping))
        refreshed = self.tally.find_voucher_by_reference(str(number)) if number else None
        return {
            "guid": (refreshed or voucher or {}).get("guid") or existing_guid,
            "tally_name": (refreshed or voucher or {}).get("voucher_number") or number,
            "result": result,
        }

    def _push_receipt(self, payload: dict, mapping: dict, existing_guid: str | None) -> dict:
        receipt_ledger = str(mapping.get("receipt_ledger") or "").strip()
        if not receipt_ledger:
            raise ValueError("Receipt ledger not configured in mapping.receipt_ledger")
        # Fail clearly if mapped bank/cash ledger name is empty — never invent Cash.
        prepared = dict(payload)
        prepared["number"] = payload.get("voucher_number") or payload.get("number") or (
            f"RCPT-{payload['id']}" if payload.get("id") is not None else None
        )
        prepared["allocations"] = self._resolve_receipt_allocations(payload.get("allocations") or [])
        if not prepared["allocations"] and payload.get("invoice_number"):
            prepared["invoice_number"] = payload.get("invoice_number")
        result = self.tally.import_objects(tally_xml.receipt_voucher_xml(prepared, mapping))
        number = prepared.get("number")
        refreshed = self.tally.find_voucher_by_reference(str(number)) if number else None
        return {
            "guid": (refreshed or {}).get("guid") or existing_guid,
            "tally_name": (refreshed or {}).get("voucher_number") or number,
            "result": result,
        }

    def _resolve_receipt_allocations(self, allocations: list[dict]) -> list[dict]:
        resolved: list[dict] = []
        for row in allocations:
            item = dict(row)
            bill_name = (
                item.get("bill_name")
                or item.get("invoice_number")
                or item.get("voucher_number")
                or item.get("tally_name")
            )
            if not bill_name and item.get("voucher_guid"):
                voucher = self._voucher_by_guid(str(item["voucher_guid"]))
                if voucher:
                    bill_name = voucher.get("voucher_number") or voucher.get("reference")
            if bill_name:
                item["bill_name"] = bill_name
            resolved.append(item)
        return resolved

    def _voucher_by_guid(self, guid: str) -> dict | None:
        for voucher in self.tally.export_collection("Voucher", rich=True):
            if voucher.get("guid") == guid:
                return voucher
        return None


class ConflictError(RuntimeError):
    pass


def build_sales_payload_from_invoice(metadata: dict, party_name: str) -> dict:
    """Helper used by tests and optional local queueing."""
    totals = metadata.get("totals") or {}
    lines = []
    for line in metadata.get("lines") or []:
        lines.append(
            {
                "item_name": line.get("description") or line.get("hsn") or "Goods",
                "quantity": line.get("quantity"),
                "rate": line.get("rate"),
                "amount": line.get("amount"),
                "unit": line.get("unit") or "NOS",
                "hsn": line.get("hsn") or "",
            }
        )
    return {
        "number": metadata.get("number"),
        "date": metadata.get("invoice_date") or metadata.get("date"),
        "party_name": party_name,
        "lines": lines,
        "cgst": totals.get("cgst", "0"),
        "sgst": totals.get("sgst", "0"),
        "igst": totals.get("igst", "0"),
        "round_off": totals.get("round_off", "0"),
        "total": totals.get("total", "0"),
        "vehicle_no": metadata.get("vehicle_no") or "",
        "delivery_address": metadata.get("delivery_address") or "",
    }
