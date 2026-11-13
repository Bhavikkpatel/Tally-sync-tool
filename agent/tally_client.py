from __future__ import annotations

from typing import Any

import httpx

from agent import tally_xml


class TallyError(RuntimeError):
    pass


class TallyClient:
    def __init__(self, base_url: str = "http://127.0.0.1:9000", timeout: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.health_timeout = min(float(timeout), 10.0)

    def post(self, xml: str, timeout: float | None = None) -> str:
        try:
            response = httpx.post(
                self.base_url,
                content=xml.encode("utf-8"),
                headers={"Content-Type": "application/xml"},
                timeout=self.timeout if timeout is None else timeout,
            )
        except httpx.HTTPError as exc:
            raise TallyError(f"Tally is unreachable at {self.base_url}: {exc}") from exc
        if response.status_code >= 400:
            raise TallyError(f"Tally returned HTTP {response.status_code}")
        return response.text

    def health(self) -> dict[str, Any]:
        try:
            info = self.company_info()
            return {"ok": True, "company": info.get("name") or "", "detail": info}
        except Exception as exc:
            return {"ok": False, "company": "", "error": str(exc)}

    def company_info(self) -> dict[str, Any]:
        return tally_xml.parse_company_info(self.post(tally_xml.company_info_request(), timeout=self.health_timeout))

    def export_collection(
        self,
        collection: str,
        *,
        from_alter_id: int | None = None,
        page_size: int = 200,
        fetch: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        company_name: str | None = None,
        rich: bool = False,
        include_banking: bool = False,
        voucher_type_bases: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        xml = tally_xml.collection_request(
            collection,
            from_alter_id=from_alter_id,
            page_size=page_size,
            fetch=fetch,
            from_date=from_date,
            to_date=to_date,
            company_name=company_name,
        )
        response = self.post(xml)
        tag = "VOUCHER" if collection.lower() == "voucher" else collection
        objects = tally_xml.parse_objects(
            response,
            tag,
            rich=rich,
            include_banking=include_banking and collection.lower() == "ledger",
            voucher_type_bases=voucher_type_bases,
        )
        if from_alter_id is not None:
            objects = [item for item in objects if item.get("alter_id", 0) > from_alter_id]
            objects.sort(key=lambda item: item.get("alter_id", 0))
            objects = objects[:page_size]
        return objects

    def export_voucher_type_bases(self, *, company_name: str | None = None) -> dict[str, str]:
        types = self.export_collection(
            "VoucherType",
            from_alter_id=None,
            page_size=5000,
            rich=True,
            company_name=company_name,
        )
        return tally_xml.voucher_type_base_map(types)

    def import_objects(self, objects_xml: str) -> dict[str, Any]:
        result = tally_xml.parse_import_response(self.post(tally_xml.import_envelope(objects_xml)))
        if result["errors"]:
            message = "; ".join(result["messages"]) or "Tally rejected the import"
            raise TallyError(message)
        return result

    def find_voucher_by_reference(self, reference: str) -> dict[str, Any] | None:
        vouchers = self.export_collection("Voucher", rich=True)
        for voucher in vouchers:
            fields = voucher.get("fields") or {}
            if (
                voucher.get("voucher_number") == reference
                or fields.get("reference") == reference
                or fields.get("vouchernumber") == reference
            ):
                return voucher
        return None
