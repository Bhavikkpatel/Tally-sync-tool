from __future__ import annotations

from typing import Any, Callable

from agent import destinations as destination_store
from agent import sync_log
from agent import tally_xml
from agent.autosync_client import AutoSyncClient
from agent.config import AgentConfig
from agent.destinations import Destination
from agent.storage import LocalStore
from agent.tally_client import TallyClient


ProgressCallback = Callable[[str], None]

RELEVANT_VOUCHER_BASES = {"sales", "purchase", "receipt", "payment"}


class ImportRunner:
    def __init__(
        self,
        store: LocalStore,
        tally: TallyClient,
        targets: list[tuple[Destination, AutoSyncClient]],
        config: AgentConfig,
        on_progress: ProgressCallback | None = None,
        *,
        force_destination_ids: set[str] | None = None,
    ):
        self.store = store
        self.tally = tally
        self.targets = targets
        self.config = config
        self.on_progress = on_progress or (lambda _message: None)
        self.force_destination_ids = force_destination_ids or set()

    def _log(self, message: str, counts: dict[str, Any] | None = None) -> None:
        line = sync_log.log_event(message, data_dir=self.config.data_dir, counts=counts)
        self.on_progress(line)

    def run(self, force: bool = False) -> dict[str, Any]:
        active = []
        for destination, client in self.targets:
            forced = destination.id in self.force_destination_ids or (
                force and destination_store.is_pluschwood(destination)
            )
            if forced:
                destination_store.reset_import(self.store, destination.id)
                active.append((destination, client))
            elif not destination_store.import_done(self.store, destination.id):
                active.append((destination, client))
        if not active:
            self._log("Import skipped — already complete for all destinations")
            return {"skipped": True, "reason": "initial import already completed for all destinations"}

        run_id = self.store.begin_run("import")
        company = self.tally.company_info()
        summary: dict[str, Any] = {
            "company": {"name": company.get("name"), "guid": company.get("guid"), "gstin": company.get("gstin")},
            "destinations": {},
            "from_date": self.config.import_from_date,
            "to_date": self.config.import_to_date,
        }
        self._log(
            f"Import start · company={company.get('name') or 'unknown'}",
            {
                "destinations": len(active),
                "from_date": self.config.import_from_date or "all",
                "to_date": self.config.import_to_date or "all",
            },
        )
        try:
            for destination, client in active:
                summary["destinations"][destination.id] = self._import_destination(
                    destination,
                    client,
                    company,
                )
            if all(destination_store.import_done(self.store, destination.id) for destination, _ in self.targets):
                self.store.set_meta("initial_import_done", True)
            self.store.finish_run(run_id, "ok", summary)
            self._log("Import complete")
            return summary
        except Exception as exc:
            self.store.finish_run(run_id, "failed", {"error": str(exc), **summary})
            self._log(f"Import failed: {exc}")
            raise

    def _import_destination(
        self,
        destination: Destination,
        client: AutoSyncClient,
        company: dict[str, Any],
    ) -> dict[str, Any]:
        rich = destination_store.is_pluschwood(destination)
        include_banking = rich and destination.base_url.lower().startswith("https://")
        if rich and not include_banking:
            self._log(f"{destination.label}: banking omitted (destination is not HTTPS)")
        company_name = company.get("name")
        dest_summary: dict[str, Any] = {
            "label": destination.label,
            "rich": rich,
            "masters": {},
            "vouchers": {},
            "vouchers_with_party": 0,
            "vouchers_with_amount": 0,
            "vouchers_with_lines": 0,
            "vouchers_with_allocations": 0,
            "purchase_vouchers": 0,
            "warnings": [],
        }

        self._send(
            client,
            destination,
            {
                "phase": "company",
                "company": company,
                "contract_version": "pluschwood_tally_v2" if rich else "autosync_tally_v1",
                "masters": [],
                "vouchers": [],
                "done": False,
            },
            batch_counts={"phase": "company", "records": 1},
        )

        voucher_type_bases: dict[str, str] = {}
        for collection in tally_xml.MASTER_COLLECTIONS:
            imported = 0
            while True:
                cursor = destination_store.get_cursor(self.store, destination.id, collection)
                page = self.tally.export_collection(
                    collection,
                    from_alter_id=cursor,
                    page_size=self.config.import_page_size,
                    company_name=company_name,
                    rich=rich,
                    include_banking=include_banking and collection.lower() == "ledger",
                )
                if collection.lower() == "vouchertype":
                    voucher_type_bases.update(tally_xml.voucher_type_base_map(page))
                if not page:
                    break
                self._send(
                    client,
                    destination,
                    {
                        "phase": "masters",
                        "master_type": collection,
                        "company": {"name": company_name, "guid": company.get("guid")},
                        "masters": page,
                        "vouchers": [],
                        "done": False,
                    },
                    batch_counts={
                        "type": collection,
                        "synced": len(page),
                        "after_alter_id": cursor,
                    },
                )
                imported += len(page)
                next_cursor = max(item.get("alter_id", cursor) for item in page)
                destination_store.set_cursor(self.store, destination.id, collection, next_cursor)
                if len(page) < self.config.import_page_size:
                    break
            dest_summary["masters"][collection] = imported
            self._log(
                f"{destination.label} · master {collection} total",
                {"synced": imported},
            )
            if collection.lower() in {"ledger", "stockitem"} and imported == 0:
                dest_summary["warnings"].append(f"{collection} export returned zero records for the selected company")

        if not voucher_type_bases:
            voucher_type_bases = self.tally.export_voucher_type_bases(company_name=company_name)

        voucher_counts: dict[str, int] = {}
        while True:
            cursor = destination_store.get_cursor(self.store, destination.id, "voucher")
            page = self.tally.export_collection(
                "Voucher",
                from_alter_id=cursor,
                page_size=self.config.import_page_size,
                from_date=self.config.import_from_date,
                to_date=self.config.import_to_date,
                company_name=company_name,
                rich=rich,
                voucher_type_bases=voucher_type_bases,
            )
            if not page:
                break
            filtered = []
            batch_by_type: dict[str, int] = {}
            for item in page:
                base = (item.get("voucher_type_base") or "").strip().lower()
                name = (item.get("voucher_type") or "").strip().lower()
                if base not in RELEVANT_VOUCHER_BASES and name not in RELEVANT_VOUCHER_BASES:
                    continue
                if not item.get("voucher_type_base") and name in RELEVANT_VOUCHER_BASES:
                    item["voucher_type_base"] = item.get("voucher_type")
                filtered.append(item)
                key = str(item.get("voucher_type_base") or item.get("voucher_type") or "Unknown")
                voucher_counts[key] = voucher_counts.get(key, 0) + 1
                batch_by_type[key] = batch_by_type.get(key, 0) + 1
                if item.get("party_name"):
                    dest_summary["vouchers_with_party"] += 1
                if item.get("amount") is not None:
                    dest_summary["vouchers_with_amount"] += 1
                if item.get("inventory_lines"):
                    dest_summary["vouchers_with_lines"] += 1
                if item.get("bill_allocations"):
                    dest_summary["vouchers_with_allocations"] += 1
                if (item.get("voucher_type_base") or "").lower() == "purchase":
                    dest_summary["purchase_vouchers"] += 1

            next_cursor = max(item.get("alter_id", cursor) for item in page)
            if filtered:
                self._send(
                    client,
                    destination,
                    {
                        "phase": "vouchers",
                        "company": {"name": company_name, "guid": company.get("guid")},
                        "from_date": self.config.import_from_date,
                        "to_date": self.config.import_to_date,
                        "masters": [],
                        "vouchers": filtered,
                        "done": False,
                    },
                    batch_counts={
                        "type": "Voucher",
                        "synced": len(filtered),
                        "after_alter_id": cursor,
                        **batch_by_type,
                    },
                )
            else:
                self._log(
                    f"{destination.label} · vouchers page skipped (no Sales/Purchase/Receipt/Payment)",
                    {"scanned": len(page), "after_alter_id": cursor},
                )
            destination_store.set_cursor(self.store, destination.id, "voucher", next_cursor)
            if len(page) < self.config.import_page_size:
                break

        dest_summary["vouchers"] = voucher_counts
        if dest_summary["purchase_vouchers"] == 0:
            dest_summary["warnings"].append(
                "Selected company/date range returned zero Purchase vouchers"
            )

        self._send(
            client,
            destination,
            {
                "phase": "complete",
                "company": {"name": company_name, "guid": company.get("guid")},
                "summary": {
                    "masters": dest_summary["masters"],
                    "vouchers": voucher_counts,
                    "warnings": dest_summary["warnings"],
                },
                "masters": [],
                "vouchers": [],
                "done": True,
            },
            batch_counts={"phase": "complete", "records": 0},
        )
        destination_store.set_import_done(self.store, destination.id, True)
        self._log(
            f"{destination.label} · import summary",
            {
                **{f"master_{k}": v for k, v in dest_summary["masters"].items()},
                **{f"voucher_{k}": v for k, v in voucher_counts.items()},
                "with_party": dest_summary["vouchers_with_party"],
                "with_amount": dest_summary["vouchers_with_amount"],
                "with_lines": dest_summary["vouchers_with_lines"],
                "with_allocations": dest_summary["vouchers_with_allocations"],
            },
        )
        for warning in dest_summary["warnings"]:
            self._log(f"{destination.label}: {warning}")
        return dest_summary

    def _send(
        self,
        client: AutoSyncClient,
        destination: Destination,
        payload: dict,
        *,
        batch_counts: dict[str, Any],
    ) -> None:
        # Never log banking or record payloads — counts only.
        _ = tally_xml.strip_banking(payload) if isinstance(payload, dict) else payload
        client.import_batch(payload)
        self._log(
            f"{destination.label} · accepted {payload.get('phase')}",
            batch_counts,
        )
