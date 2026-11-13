from __future__ import annotations

from typing import Any, Callable

from agent import tally_xml
from agent.autosync_client import AutoSyncClient
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

    def mapping_ready(self) -> bool:
        mapping = self.store.get_meta("ledger_mapping") or {}
        return all(mapping.get(key) for key in REQUIRED_MAPPING)

    def run(self) -> dict[str, Any]:
        if not self.mapping_ready():
            return {"skipped": True, "reason": "ledger mapping incomplete"}

        run_id = self.store.begin_run("outbound")
        mapping = self.store.get_meta("ledger_mapping") or {}
        acknowledgements: list[dict] = []
        summary = {"pushed": 0, "failed": 0, "conflicts": 0}

        try:
            feed = self.autosync.outbound_feed()
            items = feed.get("items") or []
            self.on_progress(f"Outbound feed: {len(items)} item(s)")

            for item in items:
                entity_type = item["entity_type"]
                entity_id = str(item["entity_id"])
                content_hash = item["content_hash"]
                payload = item["payload"]
                try:
                    result = self._push_one(entity_type, payload, mapping, item.get("tally_guid"))
                    acknowledgements.append(
                        {
                            "entity_type": entity_type,
                            "entity_id": entity_id,
                            "content_hash": content_hash,
                            "status": "ok",
                            "tally_guid": result.get("guid") or item.get("tally_guid"),
                        }
                    )
                    summary["pushed"] += 1
                except ConflictError as exc:
                    summary["conflicts"] += 1
                    acknowledgements.append(
                        {
                            "entity_type": entity_type,
                            "entity_id": entity_id,
                            "content_hash": content_hash,
                            "status": "conflict",
                            "error": str(exc),
                            "tally_guid": item.get("tally_guid"),
                        }
                    )
                except Exception as exc:
                    summary["failed"] += 1
                    acknowledgements.append(
                        {
                            "entity_type": entity_type,
                            "entity_id": entity_id,
                            "content_hash": content_hash,
                            "status": "failed",
                            "error": str(exc),
                            "tally_guid": item.get("tally_guid"),
                        }
                    )

            if acknowledgements:
                self.autosync.acknowledge(acknowledgements)
            self.store.set_meta("last_outbound_summary", summary)
            self.store.finish_run(run_id, "ok", summary)
            return summary
        except Exception as exc:
            self.store.finish_run(run_id, "failed", {"error": str(exc), **summary})
            raise

    def _push_one(self, entity_type: str, payload: dict, mapping: dict, existing_guid: str | None) -> dict:
        if entity_type == "customer":
            xml = tally_xml.ledger_xml(payload)
            result = self.tally.import_objects(xml)
            return {"guid": existing_guid or payload.get("name"), "result": result}

        if entity_type == "stock_item":
            unit = payload.get("unit") or "NOS"
            try:
                self.tally.import_objects(tally_xml.unit_xml(unit))
            except TallyError:
                # Unit may already exist.
                pass
            result = self.tally.import_objects(tally_xml.stock_item_xml(payload))
            return {"guid": existing_guid or payload.get("name"), "result": result}

        if entity_type == "sales_invoice":
            voucher = None
            if existing_guid:
                voucher = self._voucher_by_guid(existing_guid)
            if voucher is None:
                voucher = self.tally.find_voucher_by_reference(payload["number"])
            if voucher and (voucher.get("irn") or "").strip():
                raise ConflictError(
                    f"Invoice {payload['number']} already has an IRN in Tally and cannot be altered"
                )
            result = self.tally.import_objects(tally_xml.sales_voucher_xml(payload, mapping))
            refreshed = self.tally.find_voucher_by_reference(payload["number"])
            return {"guid": (refreshed or {}).get("guid") or existing_guid, "result": result}

        if entity_type == "receipt":
            result = self.tally.import_objects(tally_xml.receipt_voucher_xml(payload, mapping))
            refreshed = self.tally.find_voucher_by_reference(payload.get("number") or f"RCPT-{payload['id']}")
            return {"guid": (refreshed or {}).get("guid") or existing_guid, "result": result}

        raise ValueError(f"Unsupported outbound entity type: {entity_type}")

    def _voucher_by_guid(self, guid: str) -> dict | None:
        for voucher in self.tally.export_collection("Voucher"):
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
        "total": totals.get("total", "0"),
        "vehicle_no": metadata.get("vehicle_no") or "",
        "delivery_address": metadata.get("delivery_address") or "",
    }
